# Story S3-06 — `SandboxHealthProbe` as Phase 1 probe

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** HARDENED
**Effort:** S
**Depends on:** S3-02 (`DockerInDockerClient.health()` returns `SandboxHealth`), S1-02 (`SandboxClient` Protocol + `SandboxHealth` model), S1-05 (`sandbox.registry.auto_detect`), S3-05 (`tools/policy/sandbox-policy.yaml` + `tools/digests.yaml#sandbox.policy_yaml`)
**ADRs honored:** Phase-0 ADR-0007 (frozen Phase-1 `Probe` ABC — bytes-for-bytes against `docs/localv2.md §4`), Phase-1 ADR-0007 (warning-ID pattern), Phase-2 ADR-0004 (special-token precedent for `declared_inputs`), Phase-5 ADR-0013 (digest-pinned policy YAML — probe surfaces `policy_digest_missing`), ADR-0004 (DinD `shared_kernel` — probe records the backend it inspected), ADR-0014 (`extra="forbid"` static introspection — must remain green).

## Validation notes (phase-story-validator v1, 2026-05-23)

Hardened via `phase-story-validator` (verdict: **HARDENED**). Four block-tier contract contradictions resolved against source-of-truth and ~12 coverage / test-quality / design-pattern gaps closed. Full report: [`_validation/S3-06-sandbox-health-probe.md`](_validation/S3-06-sandbox-health-probe.md).

Most consequential changes:

1. **Probe ABC signature realigned to the frozen Phase-0 contract.** Draft specified `def run(self, ctx: ProbeContext) -> ProbeResult` and `result.payload["sandbox"]`. The frozen ABC at [`src/codegenie/probes/base.py`](../../../../src/codegenie/probes/base.py) line 93 is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`; `ProbeResult` does not exist and `ProbeOutput` exposes `schema_slice`, not `payload`. The draft would have failed `tests/unit/test_probe_contract.py` at CI. Group A (AC-ABC-1..-7) pins the full ABC surface verbatim. Per Rule 7 (surface conflicts, don't average), the source of truth is the locked contract — the story bends to the code.
2. **`layer`, `tier`, `requires`, `cache_strategy`, `applies_to_languages`, `timeout_seconds` all missing from draft ACs.** These are mandatory `Probe` attributes. `layer = "B"` per the arch's "B2 analog" framing (closest semantic match to the existing `Literal["A".."G"]`); `cache_strategy = "none"` because sandbox health is a *moving* fact like B2 (caching it has "the same bug as caching `Date.now()`" — see `IndexHealthProbe` docstring); `timeout_seconds = 5` per arch §SandboxHealthProbe (the ABC default 300 is far too lax). The layer-literal-frozen tension is documented in Notes-for-implementer; a future cross-domain probe wave warrants an ADR amendment.
3. **Policy YAML path resolution made explicit + injectable.** Draft tests `monkeypatch.chdir(tmp_path)` and write the policy YAML under tmp_path — implying CWD-relative reads, which **breaks in production** when `codegenie gather` runs from any directory. ADR-0013: "the collector reads the bytes from the codegenie process directory, not from anything under the target repo." Group D (AC-PATH-1..-4) pins resolution via `Path(codegenie.__file__).parent.parent.parent / "tools" / "policy" / "sandbox-policy.yaml"` computed once at module import, **and** makes it an injectable `policy_path_resolver: Callable[[], Path] | None = None` constructor kwarg so tests don't need `chdir`. Same DI seam shape applies to `backend_provider` and `digest_loader`.
4. **`auto_detect()` monkeypatch replaced with constructor-injected `backend_provider`.** Draft used `monkeypatch.setattr("codegenie.sandbox.health.probe.auto_detect", ...)`, a hidden-state pattern (Rule 8) that couples tests to import-time module state. Group A AC-ABC-7 introduces three injectable seams (backend / policy-path / digest-loader), defaulting to production wiring. Dependency inversion + Open/Closed.
5. **Confidence semantics reconciled with arch §Failure behavior.** Draft happy-path AC accepted `{"high","medium"}`; arch §Failure behavior says `confidence: low` on *any failure*. The two are not in conflict once the failure taxonomy is split: digest-mismatch = `confidence="high"` (we read the bytes, we computed the digest, they don't match — known failure mode with high diagnostic certainty per ADR-0013), backend-exception = `confidence="low"` (unknown state). Group F AC-CONF-1..-4 + AC-REASONS-EXCL-1..-4 enumerate the taxonomy with `reasons == [<exact-list>]` equality, so a "say everything failed" implementation cannot silently pass.
6. **Edge case 19 expanded.** Arch §Edge 19 distinguishes "digests.yaml missing the key" from "file missing entirely"; draft conflated them under `policy_digest_missing`. Group E AC-ERR-1..-4 enumerates four distinct outcomes (file missing, key missing, YAML malformed, placeholder `"TBD"`) with distinct `reasons`, so operators can tell "not yet wired" from "tampered."
7. **Sub-schema + envelope `$ref` now an explicit deliverable.** CLAUDE.md sub-schema convention says "Adding a probe requires landing its sub-schema **and** wiring a `$ref` into the envelope's `properties.probes`." Draft missed both. Group K AC-SCHEMA-1..-3.
8. **`schema_slice` key fixed.** Arch §SandboxHealthProbe says "Emits to `RepoContext.health.sandbox`" — but every existing probe writes `schema_slice = {<probe-name>: <slice>}` (`IndexHealthProbe` writes `{"index_health": ...}`). The `RepoContext.health.sandbox` phrasing is the *consumer* read-path projection, not the slice key. Group K AC-SCHEMA-1: `schema_slice = {"sandbox_health": <model_dump>}`; envelope `$ref` wires `properties.probes.properties.sandbox_health -> sandbox_health.schema.json`.
9. **Tests realigned to real `ProbeContext` + `RepoSnapshot`.** Draft used `MagicMock(workdir=tmp_path)` for `ProbeContext` — a lookalike that lets any probe pass and forks the test from the contract. A `MagicMock` will pass even if the probe accesses `ctx.banana_split`. Group G AC-TDD-1..-2 constructs real dataclass instances via a `probe_context_factory(tmp_path)` conftest fixture, mirroring `tests/unit/probes/layer_b/test_index_health.py`.
10. **Five-test-file TDD plan, mutation-resistance + property-based test.** Group H AC-PROP-1 adds a Hypothesis property test for the digest comparison: any two distinct byte strings must produce `DigestMismatch`. This catches the `==` → `startswith` mutation. Group H AC-PROP-2 rewrites the macOS-strace test as a platform-independent contract test (inject a fake backend that returns `warnings=["strace_ptrace_missing"]`; assert pass-through) — eliminates the `@pytest.mark.skipif` that made the original test Linux-CI-invisible.
11. **Functional core / imperative shell extraction.** Per CLAUDE.md load-bearing commitment, the digest verification + result construction logic is extracted into three module-level pure helpers (`_verify_policy_digest`, `_load_pinned_digest`, `_emit_health`), each ≤ 30 LOC, mirroring the `IndexHealthProbe._emit_head_unresolvable` precedent. `run()` body ≤ 40 LOC, branch-free at the top level — it pattern-matches the sum types the pure helpers return.
12. **Stringly-typed `reasons` constrained by a `StrEnum`.** `SandboxHealth.reasons: list[str]` per the S1-02 contract stays as-is (extension-by-addition — DO NOT widen the contract here). But the probe MUST emit only values from `SandboxHealthReason: StrEnum` (Group B AC-REASON-ENUM-1..-3) so typos at call sites are caught at import time. Module-level fence test asserts every literal string the probe emits comes from the enum.
13. **`digest_for(name) -> str` kernel introduced — rule-of-three threshold met.** S3-05 validation note 12 explicitly deferred the kernel to this story ("S3-06 is the first **production** consumer and rightly owns the kernel"). Group M AC-KERNEL-1..-3 ships `src/codegenie/sandbox/digests.py` with `digest_for(name)` returning a sum type (`DigestPresent | DigestPlaceholder | DigestKeyMissing | DigestFileMissing`); observable AC: "adding a new digest-pinned artifact requires zero edits to `sandbox/health/probe.py`."
14. **Canonical structlog events added to S1-05 table.** Three event-name constants (`EVENT_SANDBOX_HEALTH_PROBE_{START,SUCCESS,FAILURE}`) appended; `caplog`-based assertions in Group J pin the events fire with `probe="sandbox_health"`.
15. **Fence test for import purity.** Group L AC-FENCE-1: AST walk of `sandbox/health/probe.py` asserts none of `{subprocess, anthropic, langgraph, openai, langchain, transformers}` appear in `Import`/`ImportFrom` nodes. Matches the global LLM fence + the `forbidden-patterns` pre-commit hook discipline.

Verdict: **HARDENED**. Four block-tier contract contradictions resolved against the frozen Phase-0 ABC + ADR-0013 + arch §SandboxHealthProbe. Three rule-of-three design-pattern opportunities elevated to observable ACs (digest kernel, DI seams, sum-type reasons). ~37 numbered ACs across 11 groups (was 11 unnumbered checkboxes); five-test-file TDD plan grounded in real `ProbeContext`/`RepoSnapshot` construction.

## Context

The Phase 1 gather pipeline runs probes against a target repo to build a `RepoContext`. `SandboxHealthProbe` is the B2 analog for Phase 5: it detects silent sandbox-backend unavailability **before any gate runs**, populates `RepoContext.health.sandbox` (consumer read-path; the on-wire schema-slice key is `sandbox_health`), and surfaces structured warnings (`strace_ptrace_missing` on macOS, `policy_digest_missing` / `policy_yaml_unparseable` / `policy_digest_placeholder` on a tampered/missing/unwired policy YAML, `daemon_unreachable` on Docker Desktop down). Per `phase-arch-design.md §Component design — SandboxHealthProbe`, it instantiates the auto-detected backend, calls `client.health()`, and emits the result. Per Edge case #19, it also verifies `tools/digests.yaml#sandbox.policy_yaml` matches the policy file's actual digest — otherwise raises `reachable=False, reasons=["policy_digest_missing"]`.

The policy YAML lives at codegenie's **own package install location** (`tools/policy/sandbox-policy.yaml`), NOT under the target repo (ADR-0013). This is load-bearing: an LLM-produced patch that edits `.codegenie/policy.yaml` in the target repo MUST NOT influence the gate.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §Component design — SandboxHealthProbe`](../phase-arch-design.md#sandboxhealthprobe) (line 571) — interface, `declared_inputs`, structure, failure behavior.
  - [`../phase-arch-design.md §Component design — DockerInDockerClient health()`](../phase-arch-design.md) — the structured-reason list this probe consumes.
  - [`../phase-arch-design.md §Edge case 19`](../phase-arch-design.md) — `tools/digests.yaml` missing `sandbox.policy_yaml` → `SandboxHealth(reachable=False, reasons=["policy_digest_missing"])`.
  - [`../phase-arch-design.md §Goals 8 + 11`](../phase-arch-design.md) — `coverage_evidence_strength` soft signal; macOS strace warning persists in `SandboxHealth.warnings`.
- **Phase 5 ADRs:**
  - [`../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md`](../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md) — probe is the startup integrity check enforcing the pinned digest; collector reads from the codegenie process directory, not the target repo.
  - [`../ADRs/0004-dind-default-macos-with-gate-isolation-class.md`](../ADRs/0004-dind-default-macos-with-gate-isolation-class.md) — auto-detect falls back to DinD on macOS; probe records the chosen backend.
  - [`../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md`](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) — `confidence` on `SandboxHealth` is allowed (it is NOT reachable from `ObjectiveSignals`); regression test `tests/schema/test_objective_signals_static.py` must remain green.
- **Phase 0 ADRs:**
  - [`../../../production/adrs/0007-frozen-probe-contract.md`](../../../production/adrs/0007-frozen-probe-contract.md) — the Phase-1 `Probe` ABC is frozen byte-for-byte against `docs/localv2.md §4`; drift is caught by `tests/unit/test_probe_contract.py`. **Do not invent a new signature.**
- **Phase 1 ADRs:**
  - [`../../01-context-gather-layer-a-node/ADRs/0007-warning-id-pattern.md`](../../01-context-gather-layer-a-node/ADRs/0007-warning-id-pattern.md) — warning-ID `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; declare module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import time via `raise AssertionError`.
- **Phase 2 ADRs:**
  - [`../../02-context-gather-layers-b-g/ADRs/0004-image-digest-resolver-extension.md`](../../02-context-gather-layers-b-g/ADRs/0004-image-digest-resolver-extension.md) — special-token precedent for `declared_inputs` (`"<image-digest-token>"`); this story adds `"<codegenie-policy-yaml>"` per the same convention.
- **Production design:**
  - [`../../../production/design.md`](../../../production/design.md) Phase 1 probe contract — the ABC every probe satisfies.
  - [`../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md`](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — DI seams + registries are the discipline for extension.
- **Existing code (precedents to mirror — do not invent shapes):**
  - [`src/codegenie/probes/base.py`](../../../../src/codegenie/probes/base.py) — frozen `Probe` ABC. Signature is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Mandatory class attrs: `name`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`.
  - [`src/codegenie/probes/layer_b/index_health.py`](../../../../src/codegenie/probes/layer_b/index_health.py) — **the precedent.** Same architectural role (B2). Mirror its module structure: docstring → `_WARNING_IDS` + ID-pattern check → pure helpers → `@register_probe(runs_last=True) class IndexHealthProbe(Probe)` → imperative-shell helpers. Same `schema_slice = {<name>: ...}` shape. Same `cache_strategy="none"` discipline.
  - [`src/codegenie/probes/__init__.py`](../../../../src/codegenie/probes/__init__.py) — explicit-import collection point. Adding a probe = one additive import line; this story adds `from codegenie.sandbox.health import probe  # noqa: F401`.
  - [`src/codegenie/sandbox/contract.py`](../../../../src/codegenie/sandbox/contract.py) (from S1-02) — `SandboxHealth` Pydantic model + `SandboxClient` Protocol.
  - [`src/codegenie/sandbox/registry.py`](../../../../src/codegenie/sandbox/registry.py) (from S1-05) — `auto_detect()` returns the chosen `SandboxClient`.
  - [`src/codegenie/sandbox/logging.py`](../../../../src/codegenie/sandbox/logging.py) (from S1-05) — canonical event-name table; append three new constants here.
  - [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — newtype home; add `PolicyDigest`.
  - [`src/codegenie/output/paths.py`](../../../../src/codegenie/output/paths.py) — `raw_dir(repo_root)` precedent for path-computation helpers (no I/O).
  - `tools/policy/sandbox-policy.yaml` (from S3-05) — the file the probe digests.
  - `tools/digests.yaml#sandbox.policy_yaml` (from S3-05) — the expected BLAKE3-128 digest (32 lowercase hex chars).
  - [`src/codegenie/schema/probes/index_health.schema.json`](../../../../src/codegenie/schema/probes/index_health.schema.json) — sub-schema precedent to mirror at `sandbox_health.schema.json` (`additionalProperties: false` at every node).
- **Existing tests (precedents to mirror):**
  - [`tests/unit/probes/layer_b/test_index_health.py`](../../../../tests/unit/probes/layer_b/test_index_health.py) — real `ProbeContext`/`RepoSnapshot` construction; this is the conftest pattern to copy.
  - [`tests/unit/test_probe_contract.py`](../../../../tests/unit/test_probe_contract.py) — locks the ABC; must stay green.
  - `tests/schema/test_objective_signals_static.py` (per ADR-0014) — must stay green.
- **External docs:**
  - None — this is internal plumbing.

## Goal

Land a Phase 1 `Probe` subclass named `sandbox_health` at `src/codegenie/sandbox/health/probe.py` that (1) computes the BLAKE3-128 of the codegenie-installed `tools/policy/sandbox-policy.yaml` and verifies it against `tools/digests.yaml#sandbox.policy_yaml` (ADR-0013); (2) on match, instantiates the auto-detected backend via an injectable `backend_provider` and calls `client.health()`; (3) emits a `SandboxHealth` model under `schema_slice["sandbox_health"]` with structured `reasons` from a closed `StrEnum`. The probe registers via `@register_probe(runs_last=True)`, ships a JSON sub-schema + envelope `$ref`, and uses three DI seams (backend, policy-path resolver, digest loader) defaulting to production wiring.

## Acceptance criteria

### Group A — Phase-1 `Probe` ABC conformance (frozen by ADR-0007)

- [ ] **AC-ABC-1 — Class attributes pinned verbatim:**
  - `name = "sandbox_health"`
  - `layer = "B"` (B2-analog per arch §SandboxHealthProbe; the closest semantic match in the frozen `Literal["A".."G"]` — see Notes)
  - `tier = "base"`
  - `applies_to_tasks: list[str] = ["*"]`
  - `applies_to_languages: list[str] = ["*"]`
  - `requires: list[str] = []`
- [ ] **AC-ABC-2 — Method signature pinned verbatim against `Probe`:** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. `tests/unit/test_probe_contract.py` MUST remain green; an `inspect.signature(SandboxHealthProbe.run)` test in this story's TDD plan asserts byte-equality with `Probe.run`'s signature.
- [ ] **AC-ABC-3 — `layer="B"` rationale inline comment:** A one-line code comment in the class body cites "B2 analog — sandbox-runtime health is to the gate pipeline what `IndexHealthProbe` is to context indices; see Notes-for-implementer for the cross-domain-probe ADR-amendment path."
- [ ] **AC-ABC-4 — `cache_strategy: Literal["none"] = "none"`:** sandbox health is a moving fact like B2; caching would be "the same bug as caching `Date.now()`." Annotation MUST be `Literal["none"]` (not bare `str`) so a contributor relaxing the type fails type-check.
- [ ] **AC-ABC-4a — Mutation backstop:** parametrized test `test_cache_strategy_is_none` asserts `SandboxHealthProbe.cache_strategy == "none"` AND that the class-level annotation is `Literal["none"]` (via `typing.get_type_hints(SandboxHealthProbe, include_extras=True)`).
- [ ] **AC-ABC-5 — `timeout_seconds: int = 5`:** arch §SandboxHealthProbe pins ≤ 5 s. The ABC default of 300 is too lax for a startup integrity check.
- [ ] **AC-ABC-6 — `declared_inputs` reconciled with arch (verbatim) plus special-token:** `declared_inputs = ["~/.config/codegenie/sandbox.yaml", "tools/digests.yaml", "<codegenie-policy-yaml>"]`. The first two match arch §SandboxHealthProbe verbatim; the third is a special token (mirrors Phase 2 ADR-0004's `<image-digest-token>` precedent) that the cache-key derivation resolves to the codegenie-package-relative path. Documented in Notes.
- [ ] **AC-ABC-7 — Three DI seams (constructor kwargs):**
  ```python
  def __init__(
      self,
      *,
      backend_provider: Callable[[], SandboxClient] | None = None,
      policy_path_resolver: Callable[[], Path] | None = None,
      digest_loader: Callable[[str], "DigestLookup"] | None = None,
  ) -> None:
  ```
  Defaults: `None` → production wiring (`auto_detect`, `_default_policy_path`, `digest_for` from `codegenie.sandbox.digests`). Each seam is independently overridable for tests.
- [ ] **AC-NEW-1 — `PolicyDigest` newtype:** added to `src/codegenie/types/identifiers.py` (existing module) as `PolicyDigest = NewType("PolicyDigest", str)`. All function signatures that take or return the 32-char policy-yaml hex use this type — `mypy --strict` rejects a `SandboxSpecHash` passed where `PolicyDigest` is expected and vice versa.

### Group B — `SandboxHealthReason` closed enum (extension-by-addition discipline)

- [ ] **AC-REASON-ENUM-1 — Enum lives at `src/codegenie/sandbox/health/reasons.py`:**
  ```python
  from enum import StrEnum
  class SandboxHealthReason(StrEnum):
      POLICY_DIGEST_MISSING = "policy_digest_missing"
      POLICY_YAML_UNPARSEABLE = "policy_yaml_unparseable"
      POLICY_DIGEST_PLACEHOLDER = "policy_digest_placeholder"
      DAEMON_UNREACHABLE = "daemon_unreachable"
  __all__ = ["SandboxHealthReason"]
  ```
- [ ] **AC-REASON-ENUM-2 — `SandboxHealth.reasons: list[str]` contract from S1-02 stays unchanged.** This story does NOT widen the contract (extension-by-addition); it constrains the *producer side* (the probe). The probe MUST emit only `SandboxHealthReason.<MEMBER>.value` strings.
- [ ] **AC-REASON-ENUM-3 — Fence test:** `tests/sandbox/health/test_reasons_enum_fence.py` AST-walks `sandbox/health/probe.py` and asserts every string literal appearing in a `list[str]` constructed for the `reasons=` keyword argument of `SandboxHealth(...)` belongs to `{r.value for r in SandboxHealthReason}`. A typo like `"policy_digest_miss"` fails this test.

### Group C — Functional core (pure helpers extracted from `run`)

- [ ] **AC-CORE-1 — `_verify_policy_digest(yaml_bytes: bytes, expected: PolicyDigest) -> PolicyVerification`:** pure, ≤ 20 LOC, module-level in `sandbox/health/probe.py`. `PolicyVerification` is a tagged-union (Pydantic frozen models) `Match | DigestMismatch` (frozen, `extra="forbid"`).
- [ ] **AC-CORE-2 — `_emit_health(health: SandboxHealth, t0: float, warnings: list[str], errors: list[str]) -> ProbeOutput`:** pure, ≤ 20 LOC; builds the `ProbeOutput` with `schema_slice = {"sandbox_health": health.model_dump(mode="json")}`.
- [ ] **AC-CORE-3 — `_load_pinned_digest(digest_loader) -> PolicyDigest | PolicyDigestError`:** pure (modulo the loader callable). `PolicyDigestError` is a sum type with four variants: `FileMissing | KeyMissing | YamlUnparseable | Placeholder`. Consumer in `run()` pattern-matches each via `match` / `case` with `assert_never` on the default arm — `mypy --warn-unreachable` enforces exhaustive handling.
- [ ] **AC-CORE-4 — `run()` body ≤ 40 LOC, branch-free at the top level.** It pattern-matches the sum types the pure helpers return; no `if`-cascades over reason strings. Test: AST walk of the `SandboxHealthProbe.run` method body counts top-level `If` nodes (must be ≤ 2: one for the `auto_detect` happy-path guard + one for backend exception trap).

### Group D — Policy YAML path resolution (ADR-0013)

- [ ] **AC-PATH-1 — Module-level default resolver:**
  ```python
  def _default_policy_path() -> Path:
      import codegenie
      return Path(codegenie.__file__).resolve().parent.parent.parent / "tools" / "policy" / "sandbox-policy.yaml"
  ```
  Computed lazily inside the function (NOT at module import) so import-time stays cheap and so tests can monkeypatch `codegenie.__file__` if absolutely necessary (preferred path: inject `policy_path_resolver`).
- [ ] **AC-PATH-2 — Resolver is injectable:** `policy_path_resolver: Callable[[], Path] | None = None` constructor kwarg (per AC-ABC-7). `None` → `_default_policy_path`. Tests pass `lambda: tmp_path / "policy" / "sandbox-policy.yaml"`.
- [ ] **AC-PATH-3 — Path is resolved relative to the *codegenie package*, NOT to CWD or `repo.root`:** `tests/sandbox/health/test_path_resolution.py` runs the production resolver from a `monkeypatch.chdir("/")` context and asserts the returned path starts with the codegenie install location.
- [ ] **AC-PATH-4 — Tests do NOT use `monkeypatch.chdir`:** AST walk of `tests/sandbox/health/test_probe.py` asserts zero references to `monkeypatch.chdir`. Tests inject `policy_path_resolver` directly. (This is a positive enforcement of the DI seam.)

### Group E — Error surfaces for the policy YAML (arch §Edge 19 expanded)

- [ ] **AC-ERR-1 — Policy file missing:** `policy_path_resolver()` returns a path that does not exist → `SandboxHealth(reachable=False, confidence="low", reasons=["policy_digest_missing"], warnings=[], backend=<auto-detected backend kind>, detected_at=<UTC now>)`. `client.health()` is **not** called.
- [ ] **AC-ERR-2 — Digest key missing from `tools/digests.yaml`:** `tools/digests.yaml#sandbox.policy_yaml` key is absent → `reasons=["policy_digest_missing"]`, `confidence="low"`. `client.health()` not called.
- [ ] **AC-ERR-3 — `tools/digests.yaml` malformed (YAMLError):** `reasons=["policy_yaml_unparseable"]`, `confidence="low"`. `client.health()` not called.
- [ ] **AC-ERR-4 — Digest is the placeholder `"TBD"`:** `reasons=["policy_digest_placeholder"]`, `confidence="low"`. Distinct from "missing" so an operator can tell "not yet wired" from "tampered". `client.health()` not called.

### Group F — Confidence semantics (reconciled with arch §Failure behavior)

Group preamble: arch §Failure behavior says "`confidence: low` on any failure". That commitment applies to **unknown-state** failures (programming errors, unexpected exceptions). The digest-mismatch path is a **known** failure mode with high diagnostic certainty per ADR-0013 — we read the bytes, computed the digest, and they don't match. Emitting `confidence="low"` there would erode the "honest confidence" CLAUDE.md commitment. The taxonomy below is the resolution.

- [ ] **AC-CONF-1 — Digest mismatch (bytes-vs-expected):** `SandboxHealth(reachable=False, confidence="high", reasons=["policy_digest_missing"], warnings=[], ...)`. `client.health()` NOT called.
- [ ] **AC-CONF-2 — Digest loader error (Group E AC-ERR-1..-4):** `confidence="low"` (we don't know the policy state).
- [ ] **AC-CONF-3 — Backend `health()` raises an unhandled exception:** caught at the imperative shell; `SandboxHealth(reachable=False, confidence="low", reasons=["daemon_unreachable"], warnings=[], errors=["sandbox_health.backend_raised"], ...)`. The exception type goes into the structlog event, not into user-visible state. Per arch §Failure behavior: "raises only on programming errors" — `KeyboardInterrupt`/`SystemExit` propagate.
- [ ] **AC-CONF-4 — Happy path:** `backend.health()` returns a `SandboxHealth`. The probe passes it through unchanged (no confidence rewrites). The probe's contribution is verifying the policy YAML BEFORE the backend call; the backend owns the confidence value of its own response.
- [ ] **AC-REASONS-EXCL-1..-4 — Equality (not membership) on `reasons`:** every error AC pins `result.schema_slice["sandbox_health"]["reasons"] == [<exact single-element list>]`. A "say everything failed" implementation that emits all four reasons cannot silently pass.
- [ ] **AC-CALL-1 — Happy path calls backend exactly once:** `assert fake_backend.health.call_count == 1`.
- [ ] **AC-CALL-2 — Every short-circuit path does NOT call backend:** parametrized across AC-ERR-1..-4 and AC-CONF-1: `assert fake_backend.health.call_count == 0`.

### Group G — TDD harness (real `ProbeContext` + `RepoSnapshot`)

- [ ] **AC-TDD-1 — `tests/sandbox/health/conftest.py` ships `probe_context_factory(tmp_path) -> ProbeContext`:** returns a real `ProbeContext(cache_dir=tmp_path/"cache", output_dir=tmp_path/"out", workspace=tmp_path/"ws", logger=logging.getLogger("test"), config={})`. NO `MagicMock` for `ProbeContext`.
- [ ] **AC-TDD-2 — `tests/sandbox/health/conftest.py` ships `repo_snapshot_factory(tmp_path) -> RepoSnapshot`:** real `RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})`. UTC-naive `datetime.now()` is BANNED: timestamps use `datetime.now(tz=datetime.UTC)`.
- [ ] **AC-TDD-3 — All test invocations use the locked async two-arg signature:** `result = await probe.run(repo_snapshot, ctx)`. Tests run under `asyncio_mode = "auto"` (already in `pyproject.toml`). Zero tests in this story's TDD plan call `probe.run(ctx)` (one-arg) or `probe.run(...)` synchronously.
- [ ] **AC-TDD-4 — No `monkeypatch.setattr("...auto_detect")`:** every test passes `backend_provider=lambda: fake_backend` directly through the constructor. AST walk of `tests/sandbox/health/test_probe.py` asserts zero `monkeypatch.setattr` calls targeting `auto_detect`.

### Group H — Property-based + platform-independent tests

- [ ] **AC-PROP-1 — Hypothesis property for digest comparison:**
  ```python
  from hypothesis import given, strategies as st
  @given(a=st.binary(min_size=1), b=st.binary(min_size=1))
  def test_distinct_bytes_yield_digest_mismatch(a, b):
      """ADR-0013 invariant: any two distinct byte strings MUST produce DigestMismatch.
      Mutation-resists `==` → `startswith`, `len(a) == len(b)` checks, etc."""
      from codegenie.sandbox.health.probe import _verify_policy_digest, DigestMismatch, Match
      from blake3 import blake3
      assume(a != b)
      expected = blake3(b).hexdigest(length=16)
      result = _verify_policy_digest(a, PolicyDigest(expected))
      assert isinstance(result, DigestMismatch)
  ```
  Also: `test_matching_bytes_yield_match` — for any `b`, `_verify_policy_digest(b, blake3(b).hexdigest(length=16))` is `Match`.
- [ ] **AC-PROP-2 — Platform-independent macOS-warning pass-through:** test injects a fake backend whose `health()` returns `warnings=["strace_ptrace_missing"]`; asserts the warning appears in `result.schema_slice["sandbox_health"]["warnings"]` regardless of host OS. NO `@pytest.mark.skipif(platform.system() != "Darwin")` anywhere in the story's tests (which would make the test Linux-CI-invisible).

### Group I — ADR-0007 warning-ID discipline

- [ ] **AC-WID-1 — Module-level `_WARNING_IDS: Final[frozenset[str]]`:** declared at top of `sandbox/health/probe.py`; at minimum contains `{"sandbox_health.backend_raised", "sandbox_health.policy_yaml_unparseable", "sandbox_health.placeholder_digest"}`.
- [ ] **AC-WID-2 — Import-time ID-pattern check:**
  ```python
  _ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
  for _id in _WARNING_IDS:
      if not _ID_PATTERN.match(_id):
          raise AssertionError(f"ADR-0007 violation: {_id!r}")
  ```
  Bare `assert` is BANNED by the `forbidden-patterns` pre-commit hook.
- [ ] **AC-WID-3 — Every string emitted into `ProbeOutput.warnings` or `ProbeOutput.errors` is from `_WARNING_IDS`:** `tests/sandbox/health/test_warning_ids.py` parametrized across the four error ACs asserts emitted warnings/errors ⊆ `_WARNING_IDS`.

### Group J — Registration + canonical event-name table

- [ ] **AC-REG-1 — `@register_probe(runs_last=True)` decoration:** the class is decorated such that the coordinator dispatches it after siblings have written their raw slices (mirrors `IndexHealthProbe` precedent; sandbox-health benefits because future stories may want it to observe sibling outputs).
- [ ] **AC-REG-2 — Additive import in `src/codegenie/probes/__init__.py`:** one line added: `from codegenie.sandbox.health import probe  # noqa: F401 — S3-06 registration`. `__all__` ordering preserved (alphabetical). `tests/sandbox/health/test_registry_membership.py` asserts `"sandbox_health" in default_registry.registered_names()`.
- [ ] **AC-REG-3 — Three event-name constants appended to `src/codegenie/sandbox/logging.py`'s table:**
  - `EVENT_SANDBOX_HEALTH_PROBE_START = "sandbox.health.probe.start"`
  - `EVENT_SANDBOX_HEALTH_PROBE_SUCCESS = "sandbox.health.probe.success"`
  - `EVENT_SANDBOX_HEALTH_PROBE_FAILURE = "sandbox.health.probe.failure"`
  `caplog`-based assertion: happy-path test emits start+success; every error AC emits start+failure. (Mirrors S1-05 AC-AD-3 precedent for `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`.)

### Group K — JSON sub-schema + envelope `$ref` (CLAUDE.md sub-schema convention)

- [ ] **AC-SCHEMA-1 — `schema_slice` key is `"sandbox_health"` (not `"health.sandbox"`):** matches every existing probe's key convention (`IndexHealthProbe` → `"index_health"`). The arch's `RepoContext.health.sandbox` phrasing is the consumer read-path projection (documented in Notes); the schema slice key is the producer's contract.
- [ ] **AC-SCHEMA-2 — Sub-schema at `src/codegenie/schema/probes/sandbox_health.schema.json`:** `additionalProperties: false` at every node. Validates the dict produced by `SandboxHealth.model_dump(mode="json")`. Test: load the schema with `jsonschema`, validate against a constructed `SandboxHealth` model_dump.
- [ ] **AC-SCHEMA-3 — Envelope `$ref` wired:** `src/codegenie/schema/repo_context.schema.json#properties.probes.properties.sandbox_health` references `sandbox_health.schema.json`. Test: `tests/schema/test_repo_context_envelope.py` (parametrize the existing precedent) asserts the new ref resolves.

### Group L — Fence + ADR-0014 regression

- [ ] **AC-FENCE-1 — Import purity fence:** `tests/fence/test_sandbox_health_imports.py` AST-walks `src/codegenie/sandbox/health/probe.py` and asserts none of `{"subprocess", "anthropic", "langgraph", "openai", "langchain", "transformers"}` appear in any `Import` or `ImportFrom` node. Matches the global LLM fence (`tests/unit/test_pyproject_fence.py`) + the `forbidden-patterns` hook.
- [ ] **AC-FENCE-2 — `tests/schema/test_objective_signals_static.py` remains green after this story:** ADR-0014's static introspection MUST still pass — `confidence` on `SandboxHealth` does not propagate into `ObjectiveSignals`. CI runs this test on every PR; this AC just documents the regression hook.

### Group M — `digest_for` kernel (rule-of-three threshold, deferred by S3-05 validation note 12)

- [ ] **AC-KERNEL-1 — `src/codegenie/sandbox/digests.py` ships `digest_for(name: str) -> DigestLookup`:** returns the sum type `DigestPresent(value: PolicyDigest) | DigestPlaceholder | DigestKeyMissing | DigestFileMissing` (Pydantic frozen, `extra="forbid"`). Pure (modulo a single `Path.read_text()` for `tools/digests.yaml`). Resolves the digests-yaml path via the same codegenie-package-relative resolver as the policy YAML.
- [ ] **AC-KERNEL-2 — Observable constraint:** `tests/sandbox/test_digests_kernel.py` includes a test that adds a fictional `sandbox.imaginary` digest entry to a fixture `digests.yaml`, calls `digest_for("imaginary")`, and asserts the result is `DigestPresent` — **without** any edit to `sandbox/health/probe.py`. The AC is observable: "adding a new digest-pinned artifact requires zero edits to `sandbox/health/probe.py`."
- [ ] **AC-KERNEL-3 — S3-05's existing test consumes the kernel forward-compatibly:** the digest-cross-check test from S3-05 (which currently inlines the read) MAY be refactored to consume `digest_for` in a follow-up; this story does NOT touch S3-05's tests (Rule 3 — surgical changes). The kernel is forward-compatible; the refactor is deferred to whichever story owns S3-05's test maintenance next.

### Group N — Tooling / coverage / fence (cross-cutting)

- [ ] **AC-TOOL-1 — `mypy --strict src/codegenie/sandbox/health/` clean** (including `probe.py`, `reasons.py`).
- [ ] **AC-TOOL-2 — `mypy --strict src/codegenie/sandbox/digests.py` clean.**
- [ ] **AC-TOOL-3 — `ruff check` + `ruff format --check` clean for every new file.**
- [ ] **AC-TOOL-4 — `pytest tests/sandbox/health/ tests/sandbox/test_digests_kernel.py tests/fence/test_sandbox_health_imports.py` all pass.**
- [ ] **AC-TOOL-5 — Coverage on `src/codegenie/sandbox/health/probe.py` ≥ 95% line, ≥ 90% branch** (per `stories/README.md §Definition of done`).
- [ ] **AC-TOOL-6 — TDD plan's red test exists, is committed at the start of implementation, and is green at the end** (precedent: every Phase 5 story).

## Implementation outline

1. **`src/codegenie/types/identifiers.py`** — add `PolicyDigest = NewType("PolicyDigest", str)`.
2. **`src/codegenie/sandbox/digests.py`** (new — Group M kernel):
   - Tagged-union sum type `DigestLookup = DigestPresent | DigestPlaceholder | DigestKeyMissing | DigestFileMissing` (Pydantic frozen, `extra="forbid"`).
   - `def digest_for(name: str) -> DigestLookup`: reads `tools/digests.yaml` (codegenie-package-relative), navigates the `sandbox.<name>` path, returns the typed lookup.
   - Module docstring cites S3-05 validation note 12 + ADR-0013.
3. **`src/codegenie/sandbox/health/__init__.py`** (new subpackage) — empty `__all__`; module docstring summarizes ADR-0013.
4. **`src/codegenie/sandbox/health/reasons.py`** (new — Group B): `SandboxHealthReason` `StrEnum`.
5. **`src/codegenie/sandbox/health/probe.py`** (new):
   - Module docstring → `_WARNING_IDS: Final[frozenset[str]]` → import-time `_ID_PATTERN` check (Group I).
   - Imports: stdlib (`pathlib`, `typing`, `datetime`, `re`, `enum`), `blake3`, `pydantic`, `structlog`, `codegenie.errors`, `codegenie.probes.base` (`Probe`, `ProbeContext`, `ProbeOutput`, `RepoSnapshot`), `codegenie.probes.registry` (`register_probe`), `codegenie.sandbox.contract` (`SandboxClient`, `SandboxHealth`), `codegenie.sandbox.registry` (`auto_detect`), `codegenie.sandbox.digests` (`digest_for`, `DigestLookup`, `DigestPresent`, `DigestPlaceholder`, `DigestKeyMissing`, `DigestFileMissing`), `codegenie.sandbox.health.reasons` (`SandboxHealthReason`), `codegenie.sandbox.logging` (the three new events), `codegenie.types.identifiers` (`PolicyDigest`).
   - Pure helpers (Group C): `_verify_policy_digest`, `_emit_health`, `_load_pinned_digest`, `_default_policy_path`.
   - `@register_probe(runs_last=True) class SandboxHealthProbe(Probe):`
     - Class attributes per Group A (AC-ABC-1..-6).
     - `__init__` per AC-ABC-7 — three DI seams.
     - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`: imperative shell ≤ 40 LOC, pattern-matches the sum types returned by the pure helpers.
6. **`src/codegenie/sandbox/logging.py`** — append the three event constants per Group J AC-REG-3.
7. **`src/codegenie/probes/__init__.py`** — one additive line: `from codegenie.sandbox.health import probe  # noqa: F401 — S3-06 registration`. `__all__` preserved alphabetical.
8. **`src/codegenie/schema/probes/sandbox_health.schema.json`** — new sub-schema per Group K AC-SCHEMA-2.
9. **`src/codegenie/schema/repo_context.schema.json`** — add `$ref` per Group K AC-SCHEMA-3.
10. **Tests** (five files; see TDD plan).

## TDD plan — red / green / refactor

### Red — write the failing tests first

**Test file: `tests/sandbox/health/conftest.py`** (Group G fixtures)

```python
# tests/sandbox/health/conftest.py
from __future__ import annotations
import datetime as _dt
import logging
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from blake3 import blake3
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.sandbox.contract import SandboxHealth

@pytest.fixture
def probe_context_factory(tmp_path: Path):
    def _make() -> ProbeContext:
        return ProbeContext(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "out",
            workspace=tmp_path / "ws",
            logger=logging.getLogger("test.sandbox.health"),
            config={},
        )
    return _make

@pytest.fixture
def repo_snapshot_factory(tmp_path: Path):
    def _make() -> RepoSnapshot:
        return RepoSnapshot(root=tmp_path, git_commit=None, detected_languages={}, config={})
    return _make

@pytest.fixture
def policy_fixture(tmp_path: Path):
    """Writes a real policy YAML + a matching digest. Returns (policy_path, digest_hex)."""
    policy_dir = tmp_path / "tools" / "policy"
    policy_dir.mkdir(parents=True)
    policy_path = policy_dir / "sandbox-policy.yaml"
    policy_bytes = b"schema_version: 1\n"
    policy_path.write_bytes(policy_bytes)
    digest_hex = blake3(policy_bytes).hexdigest(length=16)
    return policy_path, digest_hex

@pytest.fixture
def fake_backend():
    fake = MagicMock()
    fake.health.return_value = SandboxHealth(
        backend="docker_in_docker", reachable=True, confidence="high",
        reasons=[], warnings=[], detected_at=_dt.datetime.now(tz=_dt.UTC),
    )
    return fake
```

**Test file: `tests/sandbox/health/test_probe.py`** (Groups E, F, G, J)

```python
# tests/sandbox/health/test_probe.py
from __future__ import annotations
import datetime as _dt
import inspect
from unittest.mock import MagicMock
import pytest
from codegenie.probes.base import Probe, ProbeOutput
from codegenie.sandbox.contract import SandboxHealth
from codegenie.sandbox.digests import DigestPresent, DigestPlaceholder, DigestKeyMissing, DigestFileMissing
from codegenie.sandbox.health.probe import SandboxHealthProbe
from codegenie.sandbox.health.reasons import SandboxHealthReason
from codegenie.sandbox.logging import (
    EVENT_SANDBOX_HEALTH_PROBE_START, EVENT_SANDBOX_HEALTH_PROBE_SUCCESS,
    EVENT_SANDBOX_HEALTH_PROBE_FAILURE,
)

# ---- Group A: ABC conformance ---------------------------------------------

def test_run_signature_matches_phase0_probe_abc():
    """ADR-0007: drift here breaks tests/unit/test_probe_contract.py."""
    base = inspect.signature(Probe.run)
    derived = inspect.signature(SandboxHealthProbe.run)
    assert base == derived

def test_class_attributes_pinned():
    assert SandboxHealthProbe.name == "sandbox_health"
    assert SandboxHealthProbe.layer == "B"
    assert SandboxHealthProbe.tier == "base"
    assert SandboxHealthProbe.applies_to_tasks == ["*"]
    assert SandboxHealthProbe.applies_to_languages == ["*"]
    assert SandboxHealthProbe.requires == []
    assert SandboxHealthProbe.cache_strategy == "none"
    assert SandboxHealthProbe.timeout_seconds == 5
    assert SandboxHealthProbe.declared_inputs == [
        "~/.config/codegenie/sandbox.yaml", "tools/digests.yaml", "<codegenie-policy-yaml>",
    ]

# ---- Group F + J: happy path ----------------------------------------------

async def test_happy_path_passes_through_backend_health(
    probe_context_factory, repo_snapshot_factory, policy_fixture, fake_backend, caplog
):
    policy_path, digest_hex = policy_fixture
    probe = SandboxHealthProbe(
        backend_provider=lambda: fake_backend,
        policy_path_resolver=lambda: policy_path,
        digest_loader=lambda name: DigestPresent(value=digest_hex),
    )
    with caplog.at_level("INFO"):
        result: ProbeOutput = await probe.run(repo_snapshot_factory(), probe_context_factory())
    assert isinstance(result, ProbeOutput)
    slice_ = result.schema_slice["sandbox_health"]
    assert slice_["reachable"] is True
    assert slice_["confidence"] == "high"
    assert slice_["reasons"] == []
    assert fake_backend.health.call_count == 1  # AC-CALL-1
    assert EVENT_SANDBOX_HEALTH_PROBE_START in caplog.text
    assert EVENT_SANDBOX_HEALTH_PROBE_SUCCESS in caplog.text

# ---- Group E + F: error surfaces (parametrized over four ACs) -------------

@pytest.mark.parametrize("lookup_factory,expected_reason,expected_confidence", [
    (lambda: DigestKeyMissing(), SandboxHealthReason.POLICY_DIGEST_MISSING.value, "low"),     # AC-ERR-2
    (lambda: DigestFileMissing(), SandboxHealthReason.POLICY_DIGEST_MISSING.value, "low"),    # AC-ERR-1
    (lambda: DigestPlaceholder(), SandboxHealthReason.POLICY_DIGEST_PLACEHOLDER.value, "low"),# AC-ERR-4
])
async def test_digest_loader_errors_short_circuit_without_backend_call(
    probe_context_factory, repo_snapshot_factory, policy_fixture,
    fake_backend, lookup_factory, expected_reason, expected_confidence,
):
    """AC-ERR-1/-2/-4 + AC-CALL-2: every short-circuit path MUST NOT call the backend."""
    policy_path, _ = policy_fixture
    probe = SandboxHealthProbe(
        backend_provider=lambda: fake_backend,
        policy_path_resolver=lambda: policy_path,
        digest_loader=lambda name: lookup_factory(),
    )
    result = await probe.run(repo_snapshot_factory(), probe_context_factory())
    slice_ = result.schema_slice["sandbox_health"]
    assert slice_["reachable"] is False
    assert slice_["confidence"] == expected_confidence
    assert slice_["reasons"] == [expected_reason]   # AC-REASONS-EXCL
    assert fake_backend.health.call_count == 0       # AC-CALL-2

async def test_digest_mismatch_high_confidence_short_circuits(
    probe_context_factory, repo_snapshot_factory, policy_fixture, fake_backend,
):
    """AC-CONF-1: ADR-0013 makes this a known failure with HIGH diagnostic certainty."""
    policy_path, _ = policy_fixture
    wrong_digest = "deadbeef" * 4  # 32 hex chars
    probe = SandboxHealthProbe(
        backend_provider=lambda: fake_backend,
        policy_path_resolver=lambda: policy_path,
        digest_loader=lambda name: DigestPresent(value=wrong_digest),
    )
    result = await probe.run(repo_snapshot_factory(), probe_context_factory())
    slice_ = result.schema_slice["sandbox_health"]
    assert slice_["reachable"] is False
    assert slice_["confidence"] == "high"
    assert slice_["reasons"] == [SandboxHealthReason.POLICY_DIGEST_MISSING.value]
    assert fake_backend.health.call_count == 0

# ---- Group F: backend exception (low confidence) --------------------------

async def test_backend_exception_low_confidence_emits_daemon_unreachable(
    probe_context_factory, repo_snapshot_factory, policy_fixture, caplog,
):
    """AC-CONF-3: unknown-state failures land at confidence=low."""
    policy_path, digest_hex = policy_fixture
    raising_backend = MagicMock()
    raising_backend.health.side_effect = RuntimeError("daemon down")
    probe = SandboxHealthProbe(
        backend_provider=lambda: raising_backend,
        policy_path_resolver=lambda: policy_path,
        digest_loader=lambda name: DigestPresent(value=digest_hex),
    )
    with caplog.at_level("ERROR"):
        result = await probe.run(repo_snapshot_factory(), probe_context_factory())
    slice_ = result.schema_slice["sandbox_health"]
    assert slice_["reachable"] is False
    assert slice_["confidence"] == "low"
    assert slice_["reasons"] == [SandboxHealthReason.DAEMON_UNREACHABLE.value]
    assert EVENT_SANDBOX_HEALTH_PROBE_FAILURE in caplog.text

# ---- Group H AC-PROP-2: platform-independent macOS warning pass-through ---

async def test_strace_warning_passes_through_regardless_of_host_os(
    probe_context_factory, repo_snapshot_factory, policy_fixture,
):
    """Arch §Risk-3 invariant under platform-independent injection. No skipif."""
    policy_path, digest_hex = policy_fixture
    fake = MagicMock()
    fake.health.return_value = SandboxHealth(
        backend="docker_in_docker", reachable=True, confidence="medium",
        reasons=[], warnings=["strace_ptrace_missing"],
        detected_at=_dt.datetime.now(tz=_dt.UTC),
    )
    probe = SandboxHealthProbe(
        backend_provider=lambda: fake,
        policy_path_resolver=lambda: policy_path,
        digest_loader=lambda name: DigestPresent(value=digest_hex),
    )
    result = await probe.run(repo_snapshot_factory(), probe_context_factory())
    slice_ = result.schema_slice["sandbox_health"]
    assert slice_["reachable"] is True
    assert "strace_ptrace_missing" in slice_["warnings"]
```

**Test file: `tests/sandbox/health/test_path_resolution.py`** (Group D)

```python
# Tests _default_policy_path is package-relative, not CWD-relative.
import ast
from pathlib import Path
from codegenie.sandbox.health.probe import _default_policy_path

def test_default_policy_path_is_codegenie_package_relative(monkeypatch, tmp_path):
    """AC-PATH-3: resolution must NOT depend on CWD."""
    monkeypatch.chdir("/")
    path = _default_policy_path()
    import codegenie
    expected_root = Path(codegenie.__file__).resolve().parent.parent.parent
    assert path == expected_root / "tools" / "policy" / "sandbox-policy.yaml"

def test_test_file_does_not_use_monkeypatch_chdir():
    """AC-PATH-4: positive enforcement of the DI seam."""
    test_file = Path(__file__).parent / "test_probe.py"
    tree = ast.parse(test_file.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "chdir":
            if isinstance(node.value, ast.Name) and node.value.id == "monkeypatch":
                found.append(node.lineno)
    assert not found, f"monkeypatch.chdir found at lines {found}"
```

**Test file: `tests/sandbox/health/test_property_digest.py`** (Group H AC-PROP-1)

```python
from blake3 import blake3
from hypothesis import assume, given, strategies as st
from codegenie.sandbox.health.probe import _verify_policy_digest, DigestMismatch, Match
from codegenie.types.identifiers import PolicyDigest

@given(a=st.binary(min_size=1), b=st.binary(min_size=1))
def test_distinct_bytes_yield_digest_mismatch(a, b):
    """ADR-0013: any two distinct byte strings MUST produce DigestMismatch.
    Mutation-resists `==` → `startswith` or length-only comparisons."""
    assume(a != b)
    expected = PolicyDigest(blake3(b).hexdigest(length=16))
    assert isinstance(_verify_policy_digest(a, expected), DigestMismatch)

@given(b=st.binary(min_size=1))
def test_matching_bytes_yield_match(b):
    expected = PolicyDigest(blake3(b).hexdigest(length=16))
    assert isinstance(_verify_policy_digest(b, expected), Match)
```

**Test file: `tests/fence/test_sandbox_health_imports.py`** (Group L AC-FENCE-1)

```python
import ast
from pathlib import Path
import codegenie

FORBIDDEN = frozenset({"subprocess", "anthropic", "langgraph", "openai", "langchain", "transformers"})

def test_sandbox_health_probe_has_no_forbidden_imports():
    """AC-FENCE-1: matches the global LLM fence + forbidden-patterns hook."""
    path = Path(codegenie.__file__).parent / "sandbox" / "health" / "probe.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in FORBIDDEN, f"banned: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert node.module.split(".")[0] not in FORBIDDEN, f"banned: from {node.module}"
```

(Additional test files referenced in ACs: `test_reasons_enum_fence.py` (B), `test_warning_ids.py` (I), `test_registry_membership.py` (J), `test_digests_kernel.py` (M), `test_repo_context_envelope.py` parametrization (K).)

### Green — make it pass

1. Land Group A constants + DI seams + `__init__`.
2. Land Group C pure helpers (sum types + `_verify_policy_digest` + `_load_pinned_digest` + `_emit_health` + `_default_policy_path`).
3. Land the imperative `run()` body — a `match` over `_load_pinned_digest(...)` result, then `_verify_policy_digest(...)`, then `try/except` around `backend.health()`. ≤ 40 LOC.
4. Land Group M `digest_for` kernel; wire as the default `digest_loader`.
5. Land Group K sub-schema + envelope `$ref`.
6. Land Group J registration: `@register_probe(runs_last=True)`, additive import in `probes/__init__.py`, three new event constants in `sandbox/logging.py`.
7. Land Group I `_WARNING_IDS` + import-time pattern check.
8. Run `make check`; iterate until green.

### Refactor — clean up

- Module docstring linking to ADR-0013 + ADR-0007 + arch §SandboxHealthProbe (mirrors `IndexHealthProbe` docstring shape — sources block at the bottom).
- structlog event call sites factored into a single helper if duplication arises.
- Verify `mypy --strict` clean for both `sandbox/health/` and `sandbox/digests.py`.
- Verify branch coverage ≥ 90% (the four error ACs naturally cover each `case` arm of the sum-type `match`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `PolicyDigest` newtype (AC-NEW-1). |
| `src/codegenie/sandbox/digests.py` | New — `digest_for` kernel + sum-type `DigestLookup` (Group M). |
| `src/codegenie/sandbox/health/__init__.py` | New subpackage marker. |
| `src/codegenie/sandbox/health/reasons.py` | New — `SandboxHealthReason` `StrEnum` (Group B). |
| `src/codegenie/sandbox/health/probe.py` | New — the probe + pure helpers (Groups A, C, D, F, I). |
| `src/codegenie/sandbox/logging.py` | Append three event constants (Group J AC-REG-3). |
| `src/codegenie/probes/__init__.py` | One additive `from codegenie.sandbox.health import probe  # noqa: F401` line (Group J AC-REG-2). |
| `src/codegenie/schema/probes/sandbox_health.schema.json` | New sub-schema (Group K AC-SCHEMA-2). |
| `src/codegenie/schema/repo_context.schema.json` | Add `$ref` to the new sub-schema (Group K AC-SCHEMA-3). |
| `tests/sandbox/health/__init__.py` | New test subpackage marker. |
| `tests/sandbox/health/conftest.py` | New — `probe_context_factory`, `repo_snapshot_factory`, `policy_fixture`, `fake_backend` fixtures (Group G). |
| `tests/sandbox/health/test_probe.py` | New — Groups A/E/F/G/H AC-PROP-2/J coverage. |
| `tests/sandbox/health/test_path_resolution.py` | New — Group D AC-PATH-3/-4. |
| `tests/sandbox/health/test_property_digest.py` | New — Group H AC-PROP-1 Hypothesis property. |
| `tests/sandbox/health/test_reasons_enum_fence.py` | New — Group B AC-REASON-ENUM-3 AST walk. |
| `tests/sandbox/health/test_warning_ids.py` | New — Group I AC-WID-3. |
| `tests/sandbox/health/test_registry_membership.py` | New — Group J AC-REG-2 (probe is discoverable via `default_registry`). |
| `tests/sandbox/test_digests_kernel.py` | New — Group M AC-KERNEL-2 observable constraint. |
| `tests/fence/test_sandbox_health_imports.py` | New — Group L AC-FENCE-1 import purity. |

## Out of scope

- The `codegenie sandbox health` CLI subcommand — S8-01 wraps this probe.
- Firecracker-specific health reasons (`kvm_missing`, `vmlinux_digest_mismatch`) — S6-01 adds them on the Firecracker side; this probe passes them through unchanged when `auto_detect()` returns Firecracker.
- Phase 1 `IndexHealthProbe` (B2) — separate probe, separate story; this story only mirrors its patterns.
- Performance regression on the probe (it must complete in ≤ 5 s per arch spec) — covered in Step 7 perf gates. The `timeout_seconds = 5` ABC field IS in scope (AC-ABC-5); the bench is not.
- `coverage_evidence_strength` (arch §Goal 8 soft signal) — surfaces via `SandboxHealth.warnings` pass-through (covered by Group H AC-PROP-2 for the `strace_ptrace_missing` case); no new probe-side derivation here.
- Refactor of S3-05's existing digest-cross-check test to consume `digest_for` — Rule 3 (surgical changes); the kernel is forward-compatible for whoever owns that test next.

## Notes for the implementer

- **The digest check MUST precede the backend call.** A digest mismatch should never reach `auto_detect()` — that's the contract ADR-0013 implies. Group F AC-CALL-2 + AC-REASONS-EXCL pin this — flip the order and four parametrized tests fail.
- **The Phase 1 `Probe` ABC is frozen** by Phase-0 ADR-0007. Do not "fix" the `Probe.run` signature to match what the draft story originally said — change the story (this version is hardened) and follow the locked code. `tests/unit/test_probe_contract.py` will reject any drift.
- **`layer = "B"` is the pragmatic choice for a frozen literal.** The arch frames this probe as "Phase 1's B2 analog," and `IndexHealthProbe` is layer B. The `Literal["A".."G"]` doesn't have a "runtime-infra" slot, so `"B"` (index/health observation) is the closest semantic match. A future cross-domain probe wave (e.g., Phase 9's Temporal-workflow health) warrants a Phase-0 ADR amendment to widen the literal; this story does NOT touch the contract.
- **Three DI seams are not "premature abstraction" (Rule 2).** They are the rule-of-three threshold met: `backend_provider` (tests + production + S6-04 platform-fallback), `policy_path_resolver` (tests + production + ADR-0013 future-relocation), `digest_loader` (tests + production + Group M kernel). All three default to production wiring; the cost in code is ~3 lines of `=None`-then-resolve.
- **`SandboxHealth.reasons: list[str]` contract is NOT widened here.** Extension-by-addition discipline: S1-02 set the field type. This story constrains the *producer side* via `SandboxHealthReason` `StrEnum`. A future story may propose widening the contract to `list[SandboxHealthReason]`; that requires an ADR amendment to S1-02's contract.
- **`confidence` field on `SandboxHealth` is about the probe's confidence in its own answer**, not about a signal — it's allowed by ADR-0014's static introspection because it's on `SandboxHealth`, not on anything reachable from `ObjectiveSignals`. Verify with `tests/schema/test_objective_signals_static.py` (must remain green — AC-FENCE-2 is the regression hook).
- **Don't catch broad `Exception` and silently flip `reachable=False`.** Per arch: "raises only on programming errors" — the imperative shell wraps `backend.health()` in `try/except Exception` (one well-justified `# noqa: BLE001` with comment citing AC-CONF-3); `KeyboardInterrupt` and `SystemExit` propagate. Real bugs in *probe code itself* propagate too — only the backend's `health()` call is wrapped.
- **The `warnings` field carries soft signals (macOS strace); it does NOT affect `reachable`.** Reviewers and Phase 11 handoff read both. Group H AC-PROP-2 enforces the pass-through.
- **`tools/digests.yaml` access goes through the `digest_for` kernel.** Don't open `tools/digests.yaml` directly in `probe.py` — that would forfeit the Group M extension-by-addition AC. The kernel returns a sum type; pattern-match it.
- **The `<codegenie-policy-yaml>` special token in `declared_inputs`** mirrors Phase 2 ADR-0004's `<image-digest-token>` precedent. The cache-key derivation resolves it to the codegenie-package-relative path bytes. Adding a third special token requires an ADR amendment per ADR-0007 (the contract's "no further extensions without ADR amendment" line in `probes/base.py`).
- **`schema_slice` key is `"sandbox_health"`, not `"health.sandbox"`.** The arch's `RepoContext.health.sandbox` phrasing is the consumer read-path projection — the *downstream renderer* may flatten the slice into `health.sandbox` for display. The producer's contract (what `ProbeOutput.schema_slice` contains) is the flat per-probe-name shape every other probe uses.
- **Mirror `IndexHealthProbe`'s module structure exactly.** Module docstring (cite ADR-0013 + ADR-0007 + arch §SandboxHealthProbe) → `_WARNING_IDS` + ID-pattern check → pure helpers → `@register_probe class` → imperative-shell helpers (if any). This is the single most useful precedent in the repo.
