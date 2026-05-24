# Validation report: S3-06 — `SandboxHealthProbe` as Phase 1 probe

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-06 lands the Phase 5 startup integrity probe: a `Probe`-subclass that reads
codegenie's own `tools/policy/sandbox-policy.yaml`, verifies the bytes match
the pinned digest in `tools/digests.yaml#sandbox.policy_yaml` (ADR-0013),
auto-detects the sandbox backend, and emits a `SandboxHealth` model under
`RepoContext.health.sandbox`. The original draft correctly traced ADR-0013 +
arch §Edge case 19 but contained **four block-tier contract contradictions**
that an executor following the draft literally would have hit on first import
and ~12 coverage / test-quality / design-pattern gaps that would let a wrong
implementation silently pass.

Three classes of contradictions dominate:

1. **Probe ABC signature drift.** The frozen Phase-0 ABC at
   `src/codegenie/probes/base.py` (line 93) is
   `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`
   — pinned byte-for-byte against `docs/localv2.md §4` by ADR-0007 and locked
   by `tests/unit/test_probe_contract.py`. The draft specified `def run(self,
   ctx: ProbeContext) -> ProbeResult` — wrong return type (`ProbeResult` does
   not exist; the contract type is `ProbeOutput`), wrong arg count (missing
   `repo`), and wrong sync/async. Also: the draft accessed
   `result.payload["sandbox"]`; `ProbeOutput` exposes `schema_slice`, not
   `payload`. An executor following the draft would have produced a probe
   that `TypeError`s at dispatch (a one-arg `run` is a `TypeError` per the
   contract module's docstring) and tests that fail to compile.
2. **Mandatory ABC class attributes missing.** `Probe` requires `layer`
   (`Literal["A","B","C","D","E","F","G"]`), `tier` (`Literal["base",
   "task_specific"]`), and `requires: list[str]`. None of the three appeared
   in the draft's ACs. The `layer` field is genuinely ambiguous for this
   probe (sandbox-runtime isn't a context-gather Layer A–G concern), but the
   `Literal` is frozen by ADR-0007 — the executor MUST pick one. Per the
   arch's "B2 analog" framing and IndexHealthProbe (B2) precedent, `layer =
   "B"` is the right call; the rationale is recorded inline (AC-ABC-3).
3. **Policy YAML path resolution is wrong-by-default.** Draft tests call
   `monkeypatch.chdir(tmp_path)` then write the policy YAML under tmp_path
   — implying the production code reads `tools/policy/sandbox-policy.yaml`
   relative to CWD. That works in tests but **breaks in production**: when
   `codegenie gather <target-repo>` runs, CWD may be the target repo, the
   user's home, or anywhere — the policy YAML lives at the **codegenie
   package install location**, not the target repo. ADR-0013 explicitly
   states "the collector reads the bytes from the codegenie process
   directory, not from anything under the target repo." The draft did not
   specify how the path is resolved. Resolution: pin `importlib.resources`-
   style resolution via a module-level constant computed from
   `codegenie.__file__`, and make the resolver itself an injectable seam
   for testing (AC-PATH-1..-4).

In addition, the draft uses `monkeypatch.setattr(...auto_detect, ...)` for
the backend seam — a hidden-state pattern (Rule 8). The arch's
`SandboxClient` registry already exposes `auto_detect()` as a registered
callable; the probe should accept it via constructor DI (Open/Closed,
dependency inversion) so it can be tested without monkeypatch and so an
operator can override the backend choice without editing the probe.

Resolution: ~37 numbered ACs across 11 groups (was 11 unnumbered checkboxes
with one critical TODO inside the TDD plan: `"adjust to actual signature
once grep'd"`). Five-test-file TDD plan: contract conformance, happy path,
short-circuit invariants, error surfaces, registration. Two pure-function
helpers extracted from `run()` (`_verify_policy_digest`,
`_emit_digest_mismatch`) to mirror the IndexHealthProbe `_emit_*` precedent.
A `digest_for(name) -> str` reader is introduced here per S3-05 validation
note 12 ("S3-06 is the first **production** consumer and rightly owns the
kernel"). Sub-schema + envelope wiring per the CLAUDE.md sub-schema
convention is now an explicit deliverable.

## Findings by critic

### Coverage critic — NEEDS-HARDENING

| Severity | Finding | Resolution |
|---|---|---|
| block | F-COV-1 — `layer`, `tier`, `requires` ABC attributes missing from every AC | Group A (AC-ABC-1..-5) pins the full ABC surface; AC-ABC-3 justifies `layer="B"` per B2-analog framing. |
| block | F-COV-2 — `cache_strategy` not pinned; sandbox health is a moving fact like B2 | Group A AC-ABC-4 pins `cache_strategy: Literal["none"] = "none"` (matches IndexHealthProbe precedent); AC-ABC-4a backstops with `cache_strategy != "content"` test. |
| block | F-COV-3 — policy YAML path resolution undefined (will read from CWD in tests, break in production) | Group D (AC-PATH-1..-4): pin `importlib.resources`-style resolution rooted at `Path(codegenie.__file__).parent.parent.parent / "tools"`; make the resolver an injectable `policy_path_resolver` constructor kwarg so tests don't need `chdir`. |
| block | F-COV-4 — confidence/`reachable=True` AC accepts `{"high","medium"}` but arch §Failure behavior pins `confidence: low` on any *failure* — the contradiction with the "happy path" branch is unspecified | Group F AC-CONF-1..-4 enumerate: digest-mismatch → `high`/`reachable=False` (ADR-0013 is high-confidence — we KNOW the bytes mismatch); digest-yaml-missing → `low`/`reachable=False` (we don't know what we don't know); backend `health()` exception → `low`/`reachable=False`; happy path → pass-through from backend. |
| harden | F-COV-5 — no AC for `tools/digests.yaml` missing the `sandbox.policy_yaml` *key* (vs file missing entirely vs digest mismatch) — arch §Edge 19 distinguishes these | Group E AC-ERR-1..-4 enumerates: file missing → `reasons=["policy_digest_missing"]`, `confidence=low`; key missing → `reasons=["policy_digest_missing"]`, `confidence=low`; YAML malformed → `reasons=["policy_yaml_unparseable"]`, `confidence=low`; placeholder `"TBD"` → `reasons=["policy_digest_placeholder"]`, `confidence=low`. |
| harden | F-COV-6 — no AC asserts the probe registers with `codegenie.probes.default_registry` AND that an additive import line exists in `src/codegenie/probes/__init__.py` | Group J AC-REG-1..-3 pin both halves (decorator + explicit import) so the probe actually fires under `codegenie gather`. |
| harden | F-COV-7 — no AC for the JSON sub-schema + envelope `$ref` (CLAUDE.md sub-schema convention) | Group K AC-SCHEMA-1..-3 ship `src/codegenie/schema/probes/sandbox_health.schema.json` with `additionalProperties: false` and wire `$ref` into `repo_context.schema.json#properties.probes`. |
| harden | F-COV-8 — `_WARNING_IDS: Final[frozenset[str]]` + import-time ADR-0007 ID-pattern assertion missing | Group I AC-WID-1..-3 mirror IndexHealthProbe precedent; banned `assert` ⇒ `raise AssertionError`. |
| harden | F-COV-9 — no AC for `applies_to_languages` (mandatory ABC attribute) | Group A AC-ABC-1 includes `applies_to_languages = ["*"]`. |
| harden | F-COV-10 — placeholder digest `tools/digests.yaml#sandbox.policy_yaml == "TBD"` is not surfaced as a distinct reason; S3-05 validation note 12 flagged this explicitly | Group E AC-ERR-4 surfaces `policy_digest_placeholder` distinctly so an operator can tell "not yet wired" from "tampered". |
| nit | F-COV-11 — `timeout_seconds` not pinned; arch §SandboxHealthProbe says ≤ 5 s | Group A AC-ABC-5 pins `timeout_seconds: int = 5`. |
| nit | F-COV-12 — `coverage_evidence_strength` (arch §Goal 8 soft signal) — explicitly out-of-scope (passes through via `SandboxHealth.warnings` per arch §Goal 11 with `strace_ptrace_missing`). Recorded in "Out of scope". | Documented; no AC change. |

### Test-Quality critic — NEEDS-RESCUE (rewrite TDD plan; goal preserved)

| Severity | Finding | Resolution |
|---|---|---|
| block | F-TQ-1 — Test file uses `MagicMock(workdir=tmp_path)` for `ProbeContext` — the real `ProbeContext` is a dataclass with `cache_dir`, `output_dir`, `workspace`, `logger`, `config` fields. A `MagicMock` lookalike will let *any* probe pass and forks the test from the contract. | TDD plan rewritten to construct real `ProbeContext` (Group G AC-TDD-1..-2) — same pattern as `tests/unit/probes/layer_b/test_index_health.py`. A `conftest.py` fixture `probe_context_factory(tmp_path)` returns a real instance. |
| block | F-TQ-2 — Test signature uses `def run(self, ctx)` (one-arg sync). Real ABC is `async def run(self, repo, ctx)` two-arg. Every test in the draft would fail to call the probe. | Group G AC-TDD-3 rewrites all test invocations to `await probe.run(repo_snapshot, ctx)`; `pytest.mark.asyncio` is implicit (`asyncio_mode = "auto"`). |
| block | F-TQ-3 — TDD plan contains a TODO inline (`# Phase 1 ProbeContext shim — adjust to actual signature once grep'd`). Validator's job is to grep. A TODO in a hardened story = unspecified contract = executor invents shape. | Eliminated. AC-TDD-1..-3 specify the exact construction. |
| block | F-TQ-4 — `monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", ...)` couples the test to import-time module state. A refactor that moves the import location passes/fails the test for the wrong reason; also blocks the DI seam fix (F-DP-1). | Group G AC-TDD-4 rewrites the seam: probe accepts `backend_provider: Callable[[], SandboxClient] | None = None` constructor kwarg; tests pass a fake provider directly. Default `None` → `auto_detect()` from registry. |
| block | F-TQ-5 — `test_policy_digest_mismatch_short_circuits` is the only mutation-resistant test for the load-bearing ADR-0013 invariant. A property test would catch off-by-one + first-byte-only digest comparison. | Group H AC-PROP-1: Hypothesis property test — for any two distinct byte strings `a != b`, `_verify_policy_digest(a_bytes, expected=blake3(b_bytes).hexdigest(length=16))` returns `DigestMismatch`. Mutation-resists `==` → `startswith`. |
| harden | F-TQ-6 — Tests assert presence of reason strings but not absence of others; allows a "say everything failed" implementation to silently pass | Group F AC-REASONS-EXCL-1..-4: each negative-path AC pins `reasons == [<exact-list>]` (equality, not membership). |
| harden | F-TQ-7 — Happy-path test fakes `client.health()` return — but doesn't assert the probe actually CALLED `client.health()`. A no-op probe that returns a hard-coded "reachable=True" passes. | Group F AC-CALL-1: `assert fake_client.health.call_count == 1` on happy path; AC-CALL-2: `assert fake_client.health.call_count == 0` on every short-circuit path (digest mismatch, key missing, file missing). |
| harden | F-TQ-8 — `@pytest.mark.skipif(platform.system() != "Darwin")` makes the macOS-warning test Linux-CI-invisible. CI matrix is Linux-only ⇒ the test never runs ⇒ regression unnoticed. | Group H AC-PROP-2: Re-shape as platform-independent contract test. The probe's macOS-strace behavior is "pass through whatever `warnings` the backend emitted." Inject a fake backend whose `health()` returns `warnings=["strace_ptrace_missing"]`; assert the warning appears in `schema_slice` regardless of host OS. No `skipif`. |
| harden | F-TQ-9 — No fence-test assertion that `subprocess` and LLM imports are absent (story AC-9 mentions "Fence tests green" but doesn't specify which fence) | Group L AC-FENCE-1: `tests/fence/test_sandbox_health_imports.py` walks `ast.Import`/`ast.ImportFrom` on `sandbox/health/probe.py` and asserts none of `{subprocess, anthropic, langgraph, openai, langchain, transformers}` appear. |
| harden | F-TQ-10 — No assertion that registration event fires (S1-05 promoted `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` to AC-AD-3 precedent; this story should mirror) | Group J AC-REG-3: `caplog`-based assertion that `EVENT_PROBE_START` and `EVENT_PROBE_SUCCESS` fire with `probe="sandbox_health"`; mirrors IndexHealthProbe. |
| nit | F-TQ-11 — `__import__("datetime").datetime.now()` in test fixture is a code smell (UTC-naive timestamps); pin to `datetime.now(tz=UTC)` | Group G AC-TDD-2 fixture uses `datetime.now(tz=datetime.UTC)`. |

### Consistency critic — NEEDS-RESCUE (four block-tier contradictions resolved)

| Severity | Finding | Resolution |
|---|---|---|
| block | F-CON-1 — Draft signature `def run(self, ctx) -> ProbeResult` contradicts frozen ABC `async def run(self, repo, ctx) -> ProbeOutput` (ADR-0007, `tests/unit/test_probe_contract.py`) | Group A AC-ABC-2 pins exact signature; Group G AC-TDD-3 mirrors in tests. Drift here trips `test_probe_contract.py` at CI. |
| block | F-CON-2 — `result.payload["sandbox"]` references field that does not exist on `ProbeOutput` (it has `schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`) | Group A AC-ABC-2 pins `schema_slice = {"sandbox_health": <SandboxHealth.model_dump>}` (matches IndexHealthProbe's `schema_slice = {"index_health": results}` precedent). |
| block | F-CON-3 — `layer` field is mandatory on `Probe` and `Literal["A".."G"]`; story doesn't specify, executor would crash at instantiation | AC-ABC-3: `layer = "B"` with one-line code comment "B2 analog — sandbox-runtime health is to the gate pipeline what IndexHealthProbe is to context indices". |
| block | F-CON-4 — Policy YAML path-resolution conflicts with ADR-0013 ("reads from the codegenie process directory, not from anything under the target repo") because tests use `monkeypatch.chdir(tmp_path)` | Group D AC-PATH-1..-4 resolve via `Path(codegenie.__file__).parent.parent.parent / "tools" / "policy" / "sandbox-policy.yaml"` (computed once at module import); injectable resolver for tests. |
| block | F-CON-5 — `confidence` AC contradicts arch §Failure behavior (`confidence: low` on any failure, including digest mismatch). The draft says digest mismatch → `confidence=high`. | Group F AC-CONF-1: digest mismatch IS `confidence="high"` because ADR-0013 makes this a *known* failure mode with high diagnostic certainty (we read the bytes; we computed the digest; they don't match). Arch §Failure behavior `confidence: low` applies to *programming-error / unknown-state* failures (e.g., backend `health()` raised). Documented in Group F preamble with both ADR-0013 + arch citation. |
| block | F-CON-6 — `declared_inputs = ["~/.config/codegenie/sandbox.yaml", "tools/digests.yaml", "tools/policy/sandbox-policy.yaml"]` mixes user-home and codegenie-package-relative paths; cache key derivation has no semantics for either. Arch declares only `["~/.config/codegenie/sandbox.yaml", "tools/digests.yaml"]`. | Group A AC-ABC-6 reconciles with arch verbatim PLUS a special token `"<codegenie-policy-yaml>"` that the cache-key derivation resolves to the actual codegenie-relative path (mirrors Phase 2 ADR-0004's `<image-digest-token>` precedent). Documented in Notes-for-implementer that adding a new special token is an ADR-level decision per ADR-0007. |
| harden | F-CON-7 — Probe is registered via `default_registry` but its outputs land under `RepoContext.health.sandbox` while every other probe's output lands under `RepoContext.probes.<name>`. The schema-slice key needs to match: per IndexHealthProbe, the slice is `{"index_health": ...}` not `{"health": {"index": ...}}`. Story should mirror. | Group K AC-SCHEMA-1 pins `schema_slice = {"sandbox_health": <model_dump>}`; envelope `$ref` wires `properties.probes.properties.sandbox_health -> sandbox_health.schema.json`. The `RepoContext.health.sandbox` phrasing in arch §SandboxHealthProbe is the *consumer* read-path projection, not the slice key — clarified in Notes. |
| harden | F-CON-8 — Story note "confidence field on SandboxHealth is about the probe's confidence in its own answer" needs the ADR-0014 static-introspection test reference made concrete | Group L AC-FENCE-2: `tests/schema/test_objective_signals_static.py` (already exists per ADR-0014) must remain green after this story; the AC adds the regression hook. |
| harden | F-CON-9 — "Performance regression on the probe (it must complete in ≤ 5 s per arch spec)" is in Out-of-scope but the `timeout_seconds` setting on the probe IS in scope — flag mismatch | Group A AC-ABC-5 pins `timeout_seconds = 5` (the ABC default 300 is far too lax). Bench AC remains deferred to Step 7. |

### Design-Patterns critic — NEEDS-HARDENING (six rule-of-three opportunities; one elevated)

| Severity | Finding | Resolution |
|---|---|---|
| harden | F-DP-1 — `auto_detect()` import-attribute is hidden state (Rule 8). Better: constructor-injected `backend_provider: Callable[[], SandboxClient] | None = None`, default = `lambda: auto_detect()`. Tests pass a fake; production code unchanged. Dependency inversion + Open/Closed. | Group A AC-ABC-7: probe `__init__(self, *, backend_provider: ..., policy_path_resolver: ..., digest_loader: ...)` with three injectable seams, all defaulting to the production wiring. AC-DI-1..-3 enumerate each seam + asserts default behavior unchanged. |
| harden | F-DP-2 — `_emit_digest_mismatch` / `_emit_short_circuit` pure helpers should be module-level, mirroring IndexHealthProbe's `_emit_head_unresolvable` precedent. Functional core / imperative shell separation (CLAUDE.md "Functional core / imperative shell" load-bearing commitment). | Group C AC-CORE-1..-3: extract `_verify_policy_digest(bytes, expected_hex) -> PolicyVerification` (sum type), `_emit_health(SandboxHealth) -> ProbeOutput`, `_load_pinned_digest(digest_loader) -> str | PolicyDigestError` (tagged-union outcome). Each ≤ 30 LOC, pure. `run()` body ≤ 40 LOC, branch-free (pattern-matches the sum type returned by the pure helpers). |
| harden | F-DP-3 — Stringly-typed `reasons: list[str]` invites typos and silent divergence. Should be a closed `StrEnum` or `Literal` union of recognized reasons (`policy_digest_missing`, `policy_yaml_unparseable`, `policy_digest_placeholder`, `daemon_unreachable`). | Group B AC-REASON-ENUM-1..-3: introduce `SandboxHealthReason` as `StrEnum` in `src/codegenie/sandbox/health/reasons.py`; the `SandboxHealth.reasons` field stays `list[str]` per the contract from S1-02 (do NOT widen — extension-by-addition discipline), but the probe ONLY emits values from `SandboxHealthReason`. Module-level fence test asserts every literal string the probe emits comes from the enum. |
| harden | F-DP-4 — Rule-of-three threshold reached: S3-05 (test), this story (production), and Step 7 perf gates all read `tools/digests.yaml`. S3-05 validation note 12 explicitly defers the kernel to S3-06: "S3-06 is the first **production** consumer and rightly owns the kernel." | Group M (elevated to AC) AC-KERNEL-1..-3: introduce `digest_for(name: str) -> str` in `src/codegenie/sandbox/digests.py`; observable constraint: "adding a new digest-pinned artifact must require zero edits to `sandbox/health/probe.py`." S3-05's existing test reaches in via the same kernel (forward-compatible). |
| harden | F-DP-5 — No `Newtype` for the policy digest hex string. `SandboxSpecHash` already exists in `sandbox/contract.py` per S1-02; mirror with `PolicyDigest = NewType("PolicyDigest", str)` so the type system catches "policy digest passed where spec hash expected" at function-signature boundaries (≥ 2 module boundaries: `digest_for`, `_verify_policy_digest`, `_load_pinned_digest`). | Group A AC-NEW-1: add `PolicyDigest` newtype to `codegenie/types/identifiers.py` (existing module per S1-05 precedent). |
| nit | F-DP-6 — `tools/digests.yaml` is read with `yaml.safe_load(...)["sandbox"]["policy_yaml"]` — KeyError on missing key. Should return a sum type (`DigestPresent | DigestPlaceholder | DigestKeyMissing | DigestFileMissing`) so callers can `match` exhaustively and `mypy --warn-unreachable` enforces handling. | Group C AC-CORE-3 (subsumed): `digest_for` returns the sum type; consumer in probe pattern-matches each variant; `assert_never` exhaustiveness guard. |
| nit | F-DP-7 — Story says "structlog event `sandbox.health.probe.run`" inline in Implementation outline §4 but no AC pins the event name or the canonical event-name table addition. S1-05 precedent: every new event name appended to `src/codegenie/sandbox/logging.py`'s table is an AC. | Group J AC-REG-3: add `EVENT_SANDBOX_HEALTH_PROBE_START`, `EVENT_SANDBOX_HEALTH_PROBE_SUCCESS`, `EVENT_SANDBOX_HEALTH_PROBE_FAILURE` to the canonical table; assert at logger call sites via `caplog`. |

## Conflict resolution

- **F-CON-5 vs F-COV-4 (confidence on digest mismatch).** Coverage wanted `{"high","medium"}` on reachable=True; Consistency surfaced the ADR-0013 / arch tension. **Consistency wins** (priority `Consistency > Coverage`), but the resolution refines the meaning: arch §Failure behavior's "`confidence: low` on any failure" applies to *unknown-state* failures, not to *known and audited* policy-digest mismatches. The digest-mismatch high-confidence path is the **honest** confidence per CLAUDE.md "Honest confidence" load-bearing commitment. Documented inline in Group F preamble.
- **F-DP-4 (kernel introduction) vs Rule 2 (Simplicity First).** Rule 2 says don't pre-build kernels. But S3-05 validation note 12 explicitly *defers* the kernel to this story — the rule-of-three threshold is met across (S3-05 test, this story production, Step 7 perf). The elevation to an observable AC ("adding a new digest-pinned artifact requires zero edits to `sandbox/health/probe.py`") is the kernel/extract opportunity in *observable* form, not a pattern-name mandate.
- **Story layer `"B"` choice (F-CON-3).** The Phase-0 ABC's `layer: Literal["A".."G"]` predates Phase 5 by design — the layers describe context-gather domains, not sandbox-runtime concerns. The rigorous fix is a Phase-0 ADR amendment to widen `Literal`. But Phase 0 ADR-0007 freezes the contract. Per Rule 7 (surface conflicts, don't average), the pragmatic resolution is: pick `"B"` (the closest semantic match: "index/health observation"), document inline, and surface the tension as a Notes-for-implementer paragraph so a future Phase-N reviewer can re-litigate via an ADR amendment when a second non-gather probe arrives.

## Stage 3 — Researcher

Not invoked. No critic finding tagged `NEEDS RESEARCH` — every gap had a
canonical in-repo precedent (IndexHealthProbe, S1-02/S1-05 conventions,
S3-05 deferred kernel) to mirror.

## Verdict

**HARDENED.** Four block-tier contract contradictions resolved against
source-of-truth (the frozen Phase-0 `Probe` ABC + ADR-0013 + arch
§SandboxHealthProbe). Three rule-of-three design-pattern opportunities
elevated to observable ACs (digest kernel, DI seams, sum-type reasons).
~37 numbered ACs across 11 groups (was 11 unnumbered checkboxes), a
five-test-file TDD plan grounded in real `ProbeContext`/`RepoSnapshot`
construction with one Hypothesis property test for digest comparison,
fence test for import purity, and `caplog` assertions for the canonical
structlog event table. The TODO inside the draft TDD plan
(`adjust to actual signature once grep'd`) is eliminated — the signature
is now pinned by AC-TDD-3 to match the frozen ABC.
