# Validation report — S6-05 — `TypecheckTypescriptSignal` collector + `register_signal_kind("typecheck.typescript")`

**Story:** [`S6-05-typecheck-typescript-signal.md`](../S6-05-typecheck-typescript-signal.md)
**Validated:** 2026-05-23
**Verdict:** **HARDENED**

The story's underlying intent — land the first `typecheck.<lang>` `SignalKind` per
production ADR-0037, registered Open/Closed against the shipped Phase-3 signal-
kind registry, with strict-AND fold-in — is sound. The drift is in the wiring:
every reference to Phase-3 surface in the story (registration API, registry name,
collector Protocol, `TrustSignal` shape, `TrustScorer` construction, jail return
sum-type, allowlisted-binary form, kernel-frozen test scope, plugin import path)
contradicts what Phase 3 actually shipped.

The validator picks the **shipped Phase-3 surface** as the source of truth, per
Global Rule 7 (surface conflicts; don't average them) and Rule 11 (match the
codebase's conventions). The story is rewritten to compile against
`src/codegenie/transforms/signal_kinds.py` (function-call registration, lowercase
singleton), `src/codegenie/transforms/outcomes.py` (`TrustSignal` has no
`confidence`; `TrustOutcome.confidence` is `Literal["high","degraded"]`),
`src/codegenie/transforms/trust_scorer.py` (`__init__(event_log=...)` required),
and `src/codegenie/exec/__init__.py` `run_allowlisted` (the bare-name +
caller-side PATH-scoping seam S6-04 hardened toward). `SubprocessJail` is **not**
the right surface for this signal — using it would force a `JailedEnv`
discriminated-union widening (an edit to `src/codegenie/transforms/sandbox_jail.py`)
that contradicts the story's own "no edits to Phase-3 code" AC, and would route
the parseable stdout through the `Completed.stdout_bytes` size field instead of
the content.

The verdict is HARDENED not RESCUE because the goal, the ADR motivation, the
extension-by-addition shape, and the integration-test cassette discipline are all
correct. Only the technical wiring needed correction, and every defect was
fixable by reference to existing shipped code or to the S6-04 hardening precedent.

The hardening surfaces three downstream documentation amendments (ADR-04-0015
§Decision/§Internal structure, `phase-arch-design.md §Component 11`, and
`final-design.md §Component 12` Internal-design paragraph) that mirror S6-04 +
S1-05's precedent of carrying ADR/design-doc amendments in the implementing PR
when shipped code diverges from the design narrative.

---

## Stage 1 — Context Brief

| Aspect | Finding |
|---|---|
| What the story promises | Ship `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` that registers `typecheck.typescript` against the Phase-3 open registry, runs `tsc --noEmit --pretty false`, compares against a per-repo baseline cache, and folds into `TrustScorer` strict-AND with zero edits to Phase-3 trust-scorer code. |
| What the phase exit criteria demand | Roadmap exit criterion #3 + production ADR-0037 require the first `typecheck.<lang>` `SignalKind` to land in Phase 4; the signal must fire *before* `npm test` runs so LLM-produced source that doesn't type-check fails strict-AND at the right tier. |
| What the arch + ADRs constrain | ADR-04-0015 §Pattern-fit: "Registry pattern + Open/Closed; zero edits to Phase 3 code." Phase-3 ADR-0010 (Open/Closed for trust-scorer) requires the registration mechanism to be additive — module + one registration call. Phase-3 ADR-0007 freezes the probe contract (the analog for the signal surface). Production ADR-0031 (plugin architecture): signal is plugin-local; Phase-7 distroless plugin opts out by not registering. |
| Source-of-truth files | `src/codegenie/transforms/signal_kinds.py` (lines 10–14 + 125–145: function-call API, `signal_kind_registry` singleton); `src/codegenie/transforms/outcomes.py` (lines 377–403: `TrustSignal` shape + `TrustOutcome.confidence`); `src/codegenie/transforms/trust_scorer.py` (lines 126–161: constructor-injected event log; `score` raises on empty + unregistered); `src/codegenie/transforms/sandbox_jail.py` (lines 148–148 `JailedEnv` closed sum; lines 215–227 `Completed.stdout_bytes` is size, not content; lines 306–309 `JailedSubprocessResult` tagged union); `src/codegenie/exec/__init__.py` (lines 105–130 `ALLOWED_BINARIES` bare-name discipline; lines 235–291 `run_allowlisted` signature + `env_extra` PATH-scoping seam; line 167 `ProcessResult.returncode`); `tests/fence/test_kernel_frozen.py` (lines 271–286: Phase-3 packages `plugins`, `transforms`, `vuln_index`, `primitives` are scoped *out* of frozen); S7-01 validation `_validation/S7-01-vuln-node-npm-plugin-scaffold.md` line 32 ("loader uses the literal hyphenated slug"); S6-04 hardened story `S6-04-tsc-allowed-binary.md` (bare-name + caller-side PATH-scoping). |

**Ambiguity surfaced before proceeding.** Two design-narrative claims contradict
shipped code and must be resolved before the story compiles:

1. **Registration mechanism.** Design (arch §189, final-design §Component 12,
   ADR-04-0015 §Decision) frames `@register_signal_kind` as a **class decorator**.
   Shipped Phase 3 (`signal_kinds.py:10-14`) is explicit: "`register_signal_kind`
   is a function call, NOT a class decorator". Mirrors `register_plugin`, not
   `register_probe`. The validator resolves toward the shipped Phase-3 surface
   per Rule 11; the design narrative is flagged for amendment in the same PR.
2. **Subprocess surface.** Design (ADR-04-0015 §Decision, arch §190, final-design
   §Component 12) names `SubprocessJail (30s cap)`. Shipped `SubprocessJail`
   returns `Completed.stdout_bytes` (size, not content) and requires `JailedEnv`
   to discriminate over `NpmEnv | GitEnv | JvmEnv` (closed sum). Using
   `SubprocessJail` for `tsc` requires editing
   `src/codegenie/transforms/sandbox_jail.py` to add a `TscEnv` variant — an edit
   the story itself forbids (its own AC: "no edits to `src/codegenie/`
   Phase-3 code"). S6-04's hardening already routes narrow-admission discipline
   through `run_allowlisted` + `env_extra={"PATH": ...}`. The validator resolves
   toward `run_allowlisted` per Rule 7; ADR-04-0015 + arch + final-design are
   flagged for amendment in the same PR.

---

## Stage 2 — Critic findings (consolidated)

### Severity legend
- **block** — story cannot ship as written.
- **harden** — real but fixable weakness; would let a wrong implementation through.
- **nit** — minor wording.

### Cluster A — Registration API + registry-name drift (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-1, C-Coverage-1 | block | Story uses `@register_signal_kind("typecheck.typescript")` as a **class decorator**. Shipped API is a **function call** returning a typed `SignalKind` (`signal_kinds.py:10-14, 125-145`). The decorator form will raise `TypeError` at import time. | Consistency + Coverage |
| C-Consistency-2 | block | Story's fence test imports `from codegenie.gates.signals import SIGNAL_KIND_REGISTRY`. Real module is `codegenie.transforms.signal_kinds`; real symbol is `signal_kind_registry` (lowercase singleton, `Final[SignalKindRegistry]`). No `codegenie.gates.signals` exists. | Consistency |
| C-Consistency-3 | block | Story claims to "implement Phase 3's `SignalCollector` Protocol exactly — `mypy --strict` accepts it as a `SignalCollector`." No such Protocol exists in `src/codegenie/`. `grep -rn "class SignalCollector"` returns zero matches. `TrustScorer.score(signals: list[TrustSignal])` takes Pydantic value types, not collector instances. | Consistency |
| T-1 | block | Fence test asserts `typecheck_kinds == ["typecheck.typescript"]` via list comprehension over the registry. Real `SignalKindRegistry.__contains__` and its `_origins` dict are private — no public iteration API. The fence must use `SignalKind("typecheck.typescript") in signal_kind_registry`. | Test-Quality |

**Synthesis:** the entire registration mechanism in the story is wrong against
shipped code. Editor rewrites the collector module to call
`TYPECHECK_TYPESCRIPT = register_signal_kind("typecheck.typescript")` at module
top-level (the shipped pattern; mirrors `BUILD = register_signal_kind("build")`
at `signal_kinds.py:154`). The collector becomes a plain `async` function (not a
class implementing a Protocol that doesn't exist) — composition over inheritance
per CLAUDE.md. The fence test uses `SignalKind("typecheck.typescript") in
signal_kind_registry` plus a positive assertion that the module's `TYPECHECK_TYPESCRIPT`
constant equals that `SignalKind`. ADR-04-0015 + arch §Component 11 + final-design
§Component 12 are flagged for amendment in the same PR (the "decorator" framing
needs to become "function-call registration"); same pattern S6-04 + S1-05 used.

### Cluster B — `TrustSignal` / `TrustOutcome` shape drift (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-4 | block | Story prescribes `TrustSignal(kind, passed, details, confidence)` with `confidence: Literal["high","medium","low"]`. Shipped `TrustSignal` (`outcomes.py:377-388`) has **three** fields — `kind`, `passed`, `details: dict[str, str|int|bool|float]` — with `extra="forbid"`. Passing a `confidence` kwarg raises `pydantic.ValidationError`. | Consistency |
| C-Consistency-5 | block | Where confidence DOES live (`TrustOutcome.confidence: Literal["high","degraded"]` at `outcomes.py:403`), the values are `"high"` or `"degraded"` — not `"high"|"medium"|"low"`. | Consistency |
| C-Consistency-6 | block | Story prescribes `details: dict[str, str|int|bool]` (tighter than shipped `dict[str, str|int|bool|float]`). Asserting the story's tighter shape on the collector blocks legitimate `float` carries (wall-time-s, error-rate). Conform to the wider shipped shape. | Consistency |
| C-Consistency-7 | block | Story's `details={"degraded_reason": "no_tsconfig_or_tsc"}` is a string value — fine — but story claims arch §Type contracts line 763 says `dict[str, str|int|bool]`. Arch line 763 says exactly that (`# carries forward Phase 3 convention; no Phase-4 widening`) — **but Phase 3 actually shipped wider (`float` admitted)**. Two design docs disagree with each other; shipped wins per Rule 7. Arch §line 763 flagged for correction. | Consistency |

**Synthesis:** Editor rewrites every AC that mentions `TrustSignal.confidence`
to drop the field. The "degraded confidence" semantics for the
`no_tsconfig_or_tsc` / `timeout` edge cases are surfaced through
`details["degraded_reason"]` / `details["timeout"]` only (Phase 3 convention —
the `degraded` confidence at `TrustOutcome` level is folded by the scorer from
the workflow event log, not by individual signals). Arch §line 763 +
final-design §Type contracts are flagged for amendment in the same PR (widen the
typed shape from `str|int|bool` to `str|int|bool|float` to match shipped).

### Cluster C — `TrustScorer` construction + strict-AND-test scaffolding (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-8, T-2 | block | Story's `test_trust_scorer_folds_typecheck_without_phase3_edits` constructs `TrustScorer()` with no args. Shipped `TrustScorer.__init__(event_log: EventLog)` (`trust_scorer.py:135`) requires an event log; the no-arg form raises `TypeError`. Test never compiles. | Consistency + Test-Quality |
| C-Consistency-9, T-3 | block | Story's six-signal fixture passes `TrustSignal(kind="build", passed=True, details={}, confidence="high")` to `TrustScorer.score`. Two breakages: (a) `confidence=` kwarg fails Pydantic validation (Cluster B); (b) `kind="build"` is `str`, but shipped `TrustSignal.kind: SignalKind`. The smart constructor needs `SignalKind("build")` or the typed `BUILD` constant exported by `signal_kinds`. | Consistency + Test-Quality |
| T-4 | harden | The strict-AND assertion (`outcome.passed is False`) does not isolate the *reason*. A `TrustScorer` that returns `False` on every input (the trivially-wrong mutation) passes. Add: same six signals but with `passed=True` everywhere — assert `outcome.passed is True` and `"typecheck.typescript"` in `outcome.failing == []`. Mutation barrier: scorer must read the typecheck signal's `.passed`, not return constant. | Test-Quality |
| T-5 | harden | Test name says "without Phase-3 edits" but the assertion only verifies that `outcome.passed is False` — it does not verify the *no-edit* claim. The actual no-edit guarantee is structural (Open/Closed by ADR); add an AC that runs `git diff --stat src/codegenie/transforms/trust_scorer.py src/codegenie/transforms/signal_kinds.py src/codegenie/transforms/outcomes.py` after the story merges and asserts **zero changes** to those three files. (See also Cluster F on the kernel-frozen-fence misuse.) | Test-Quality |

**Synthesis:** Editor rewrites the strict-AND test to construct `TrustScorer(event_log=workflow_log_fixture)` against an in-memory event log (the Phase-3 testing pattern at `tests/unit/transforms/test_trust_scorer.py` — verify the file exists; if not, the fixture lives under `tests/conftest.py`). Add the positive-case assertion (all-passed → `outcome.passed is True`) as the mutation barrier. Replace the story's vague "kernel-frozen test asserts no Phase-3 edits" with an explicit `git diff --stat` AC against three named files.

### Cluster D — Subprocess surface choice + result-shape misuse (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| D-1, C-Consistency-10 | block | Story uses `SubprocessJail` (Phase 3 Port). The Port's `Completed` variant (`sandbox_jail.py:215-227`) carries `stdout_bytes: int` (size) **not** stdout content — the adapter redirects full content to a `SandboxedPath`-rooted log file outside the envelope. The story's mock `MagicMock(exit_code=0, stdout="Found 5 errors in 3 files.")` cannot exist against the real `Completed` schema. Parsing the error count from a `SubprocessJail.run` result requires reading the per-run log file from disk. | Consistency + Design-Patterns |
| D-2 | block | `JailedSubprocessSpec.env` (`sandbox_jail.py:333`) requires a `JailedEnv` variant. `JailedEnv = NpmEnv \| GitEnv \| JvmEnv` is a **closed sum** (`sandbox_jail.py:148`). No `TscEnv` exists. Running `tsc` under `SubprocessJail` therefore requires either (a) editing `src/codegenie/transforms/sandbox_jail.py` to add a `TscEnv` variant — contradicting the story's own AC "no edits to Phase-3 code" — or (b) reusing `NpmEnv` (which forces `npm_config_ignore_scripts=true` into the child — harmless for `tsc` but lying-about-environment). Both are bad. | Design-Patterns |
| D-3 | block | Story's `Missing` return variant does not exist. Shipped `JailedSubprocessResult` (`sandbox_jail.py:306-309`) is `Completed \| TimedOut \| OomKilled \| NetworkDenied \| DiskQuotaExceeded \| JailSetupFailed`. Missing-binary maps to either `Completed(exit_code=127)` (binary on allowlist but not on PATH) or `JailSetupFailed(reason="binary-not-allowlisted")` (binary not on allowlist — won't happen post-S6-04 since `tsc` is allowlisted). | Consistency |
| D-4, T-6 | block | Story's `MagicMock(exit_code=0, stdout="Found 5 errors...")` shape is also wrong against the simpler `run_allowlisted` path: shipped `ProcessResult` (`exec/__init__.py:159-169`) is `returncode: int, stdout: bytes, stderr: bytes` — the field is `returncode` not `exit_code`, and `stdout` is `bytes` not `str` (decode-explicit at the boundary). Mocks must build a real `ProcessResult(returncode=0, stdout=b"Found 5 errors in 3 files.\n", stderr=b"")`. | Consistency + Test-Quality |
| D-5 | block | The S6-04 hardening pinned the bare-name discipline: `tsc` is admitted as `"tsc"` (bare). Story's "Runs `./node_modules/.bin/tsc --noEmit --pretty false`" (AC + Implementation outline §1) inverts this. Bare-name admission + caller-side PATH-scoping via `env_extra={"PATH": str(repo_root / "node_modules" / ".bin")}` is the S6-04 contract. The path-form `argv[0]` will raise `DisallowedSubprocessError` even after S6-04 ships (`exec/__init__.py:274`). | Consistency + Design-Patterns |

**Synthesis (Consistency + Design > Coverage > Test-Quality priority).** Per
Rule 7, surface the conflict and pick the better-tested convention. `SubprocessJail`
loses on three independent axes (D-1 stdout-size, D-2 JailedEnv widening
required, D-3 result-shape mismatch). `run_allowlisted` wins: shipped today,
returns full `stdout: bytes` (D-1), uses `env_extra` for PATH-scoping
(matches S6-04's narrow-admission seam — D-5), no closed-sum widening (D-2). The
30-second cap maps to `timeout_s=30.0`; timeout escalates to `ProbeTimeoutError`
(not a `TimedOut` value variant). Editor rewrites:
- Implementation outline §1: `tsc` (bare) + `env_extra={"PATH": ...}` via `run_allowlisted`;
- AC-3: assert `argv == ["tsc", "--noEmit", "--pretty", "false"]`, `cwd=repo_root`, `timeout_s=30.0`, `env_extra["PATH"]` is the repo-local bin;
- AC-7: timeout maps to `ProbeTimeoutError` caught by the collector and rewritten as `TrustSignal(passed=False, details={"timeout": True})`;
- AC-8: missing `tsc` on PATH maps to `ToolMissingError` (post-S6-04) — rewritten as `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"})`.
- ADR-04-0015 §Decision/§Internal-structure + arch §Component 11 + final-design §Component 12 are flagged for amendment in the same PR — replace "`SubprocessJail` (30 s cap)" with "`run_allowlisted` (timeout_s=30.0) with caller-side PATH-scoping via `env_extra`."

### Cluster E — Plugin import path is a `SyntaxError` (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-11 | block | Story's fence test reads `import plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal` (underscored form). Per S7-01's hardened story (`_validation/S7-01-vuln-node-npm-plugin-scaffold.md` line 32): "**the loader uses the literal hyphenated slug**" — directory is `plugins/vulnerability-remediation--node--npm/`. Python's `import` statement parser rejects hyphens; the underscored form imports a directory that doesn't exist. Real registration must use `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`. | Consistency |

**Synthesis:** Editor replaces every bare `import plugins...` line in the story's
TDD plan with `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`.
Notes-for-implementer documents the hyphen-vs-underscore convention (one line +
link to S7-01 validation).

### Cluster F — `test_kernel_frozen.py` does not cover what the story claims (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-12 | block | Story AC: "**No edits to `src/codegenie/` Phase-3 trust-scorer code** (asserted by `tests/fence/test_kernel_frozen.py` from S1-07)." Shipped `test_kernel_frozen.py` (`tests/fence/test_kernel_frozen.py:271-286`) explicitly scopes Phase-3 packages **out** of frozen: `_TOP_LEVEL_PHASE3_PACKAGES = frozenset({"plugins", "transforms", "vuln_index", "primitives"})`. `_is_in_kernel_scope` returns `False` for any path under `src/codegenie/transforms/`. The fence cannot assert what the story claims; an edit to `trust_scorer.py` would not be caught by it. | Consistency |

**Synthesis:** The "no edits" guarantee is **Open/Closed by design** (ADR-04-0015
+ Phase-3 ADR-0010), not a structural fence. Editor rewrites the AC: ship a new
fence `tests/fence/test_phase4_no_trust_scorer_edits.py` that asserts
`git diff --stat HEAD~1 src/codegenie/transforms/trust_scorer.py
src/codegenie/transforms/signal_kinds.py src/codegenie/transforms/outcomes.py`
returns zero changed lines for any commit in the S6-05 PR. (Or: PR-CI level
check — but a fence test is more durable.) Notes-for-implementer documents the
fence's narrow scope: it asserts the specific Phase-3 trust-scorer surface this
story commits to leaving alone; broader Phase-3 transforms churn (e.g., S6-04's
`exec/__init__.py` amendment) is out of scope.

### Cluster G — Baseline-cache semantics undefined (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Coverage-2, D-6 | block | "`.codegenie/typecheck/baseline-<repo-sha>.json`" — what is `<repo-sha>`? `git rev-parse HEAD`? Working-tree hash? After-patch SHA? If HEAD: the LLM's working-tree patch is never committed, so HEAD doesn't change across attempts — good for "compare to known-good", but the baseline never advances. If working-tree hash: baseline changes on every LLM attempt → strict-AND becomes vacuous. The story does not specify. | Coverage + Design-Patterns |
| C-Coverage-3 | block | "On first run (no baseline file), record current error count as the baseline and return `passed=True`" — admits a baseline-poisoning attack: an LLM that runs `tsc` on a *modified* working tree on first run seeds a baseline that includes its broken changes. Every subsequent attempt then passes trivially. Real Phase-3 contract: baseline must be captured against the **pre-patch** working tree (the orchestrator's snapshot of repo state before the LLM's transform was applied). The collector should *read* the baseline from a caller-supplied path; the *capture* is the orchestrator's responsibility, one tier up. | Coverage |
| T-7 | harden | "Baseline strict-AND" only tests baseline=5/after=5 (equal). A `<` vs `<=` mutation passes. Add boundary cases: baseline=5/after=4 (improvement → pass), baseline=5/after=6 (regression → fail), baseline=0/after=0 (zero-baseline → pass), baseline=0/after=1 (zero-baseline regression → fail). | Test-Quality |

**Synthesis:** Editor adds:
- AC: `<repo-sha>` is defined as `git rev-parse HEAD` of the **pre-patch** snapshot; the orchestrator supplies the SHA via the `SignalContext`. The collector reads the baseline at that key; it does **not** capture the baseline itself.
- AC: collector behavior when baseline file is *missing* is `TrustSignal(passed=True, details={"degraded_reason": "no_baseline", "error_count": N})` with the explicit understanding that the orchestrator (not the collector) is responsible for capturing baselines on a clean tree. This is the same "fail-loud-degraded" pattern used for missing-`tsc`. (Alternative: refuse-with-error; surfacing the choice to the user. Validator picks the degraded-pass form to match Phase-3 baseline-bootstrap convention named in the story's Implementation outline §2 — but this needs operator confirmation before the executor runs.)
- AC: four boundary tests parametrized: `(5,4)→pass, (5,5)→pass, (5,6)→fail, (0,0)→pass, (0,1)→fail`.

### Cluster H — Parser brittleness + missing-summary edge case (harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| T-8 | harden | `_parse_tsc_error_count` is described as "two lines of regex" against `Found N errors in M files.`. Reality: `tsc --noEmit` with **zero** errors emits **no summary line** at all (exit 0, stdout empty). A naive regex returning `0` on no-match conflates "zero errors" with "tsc didn't produce a summary because it crashed." Need: `exit_code == 0 ⇒ 0 errors` (authoritative); `exit_code != 0 + summary parsed ⇒ N`; `exit_code != 0 + no summary ⇒ `TrustSignal(passed=False, details={"degraded_reason": "tsc_unparseable_output", "stderr_head": <first-256-bytes>})`. | Test-Quality |
| T-9 | harden | Singular form: "Found 1 error in 1 file." — regex on plural `errors` misses. Add to parser test corpus. | Test-Quality |
| T-10 | harden | `--pretty false` output is the de-facto format but is not contractually pinned across `tsc` versions. Add a `--version` capture into the signal `details` so a future tsc-output change can be diagnosed without re-running. | Test-Quality |

**Synthesis:** Editor expands the parser AC into a property-style test (5+ fixtures
covering: zero errors with empty stdout, singular `1 error in 1 file`, plural,
multi-file, multi-line interspersed with errors, stderr-only failure). The parser
becomes a pure function `_parse_tsc_error_count(returncode: int, stdout: bytes)
-> ErrorCount | UnparseableOutput` returning a sum type; the impure shell maps
to a `TrustSignal`. This is the functional-core / imperative-shell discipline
CLAUDE.md commits to, and gives the next `typecheck.<lang>` collector (Python in
Phase 7.5) a clean precedent.

### Cluster I — Integration-test event names not pinned to shipped event types (harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-13, T-11 | harden | Story's integration test asserts the event stream contains `SignalEvaluated`, `LeafReturned`, `GateBlocked`, `NpmTestStarted`. These names are not present in Phase-3's shipped event taxonomy (`src/codegenie/plugins/events.py`). Need: enumerate the real event class names the orchestrator emits between leaf return and `npm test` start, or surface these as **new** event types this story must define + register. | Consistency + Test-Quality |
| T-12 | harden | Event-ordering assertion `assert all(i > ts_evt for i in npm_evts) or not npm_evts` is too permissive: empty `npm_evts` always passes even if `tsc` never ran. Add: assert `ts_evt` exists AND (no NpmTestStarted ever OR every NpmTestStarted index > ts_evt). | Test-Quality |

**Synthesis:** Editor flags Cluster I as the executor's first task before TDD —
read `src/codegenie/plugins/events.py` for the shipped event taxonomy; pick the
right four event names; if any are not yet shipped, scope the new event-type
addition to S6-08's "attempt-anchor emission" story (which already owns
event-taxonomy work) rather than letting S6-05 silently introduce four new
event types. The mutation barrier on test ordering is tightened.

### Cluster J — Mutation-weak ACs (harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| T-13 | harden | "Registered exactly once" fence asserts `typecheck_kinds == ["typecheck.typescript"]` — passes even if the kind is registered under a misspelled name like `"typescript.typecheck"` (off-by-swap). Add explicit: `SignalKind("typecheck.typescript") in signal_kind_registry`. | Test-Quality |
| T-14 | harden | No test asserts that the **collector** function references the **same** `SignalKind` it registered (i.e., the module's `TYPECHECK_TYPESCRIPT` constant is what the collector emits in `TrustSignal.kind`). Catches the "registers one name, emits a different name" mutation. | Test-Quality |
| T-15 | harden | No idempotence-property test for the baseline file: writing then reading should round-trip identically, including under concurrent collectors against the same repo (Phase 8 hot-views or Phase 6.5 bench replay race). | Test-Quality |

**Synthesis:** Editor adds three named ACs covering each (positive registry-membership assertion, name-coupling assertion, idempotence property).

### Cluster K — Open/Closed extension path for future `typecheck.<lang>` (harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| D-7 | harden | Per ADR-0037, `typecheck.python` (Phase 7.5) and `typecheck.java` (later) are designed sibling signals. The collector logic for all three is identical in shape: invoke a type-checker; parse its error count; compare against per-repo baseline; emit `TrustSignal`. Rule of three says **defer**, but: the second sibling (`typecheck.python`) is already a known Phase-7.5 deliverable. Surface the kernel-extract opportunity in Notes-for-implementer so the Phase-7.5 executor has a clear extract target. **Do NOT prematurely extract** (Rule 2 — three similar lines is better than premature abstraction). | Design-Patterns |
| D-8 | harden | The "register + collector" pair is a candidate for a `TypecheckSignalKit(kind, binary, parse_fn, baseline_key_fn)` value type at the rule-of-three threshold. Surface in Notes-for-implementer with a single explicit example, do not add as an AC. | Design-Patterns |

**Synthesis:** Notes-for-implementer adds a one-paragraph "Future-sibling note"
documenting that the second `typecheck.<lang>` should extract a common helper
along the `(binary, parse_fn, baseline_key)` axes. No new ACs.

### Cluster L — Newtype primitives + functional-core discipline (harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| D-9 | harden | `<repo-sha>` is raw `str` throughout; same with `error_count: int`, `baseline_count: int`. Both cross module boundaries (orchestrator ↔ collector ↔ parser ↔ filesystem path). Newtype them: `RepoSha = NewType("RepoSha", str)`, `ErrorCount = NewType("ErrorCount", int)`. Catches the "passed baseline-count where current-count expected" swap mutation that strict typing surfaces. | Design-Patterns |
| D-10 | harden | The story's "pure core / impure shell" claim ("the count comparison logic is the pure core") is a paragraph in `Refactor` but not an AC. Add: AST-walking test that `_parse_tsc_error_count` and `_passes_strict_and(baseline, current)` are pure (no imports of `os`, `pathlib`, `asyncio`, `subprocess`, no module-level state read). | Design-Patterns |

**Synthesis:** Editor adds:
- AC: introduce `RepoSha` and `ErrorCount` newtypes under
  `codegenie.types.identifiers` (or the closest existing identifiers module);
  the collector's public surface uses these.
- AC: AST-walking purity test for `_parse_tsc_error_count` + `_compare_to_baseline`
  (whichever name the executor lands on).

### Cluster M — Cassette test wording bug (nit)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-14 | nit | Story's integration-test path `tests/cassettes/anthropic/test_typecheck_signal_catches_signature_drift/` — under `tests/cassettes/anthropic/`, cassette directories key by test-module *and* test-function (per arch §line 794 "`tests/cassettes/anthropic/<test_module>/<test_function>.yaml`"). Story's path is the test-function form; the test-module portion is missing. | Consistency |

**Synthesis:** Editor fixes the path to `tests/cassettes/anthropic/test_typecheck_signal_catches_signature_drift/test_typecheck_catches_hallucinated_method_before_npm_test.yaml` (one file per test, per arch convention).

---

## Stage 3 — Researcher

**Not invoked.** No critic finding required research outside the codebase — every
defect is concretely answerable from `src/codegenie/` shipped code, the
`_validation/S6-04-tsc-allowed-binary.md` + `_validation/S7-01-...md` precedents,
and ADR-04-0015 itself.

The pattern advice (rule-of-three for future `typecheck.<lang>` siblings;
functional-core / imperative-shell at the parser boundary; newtype-the-domain-
primitives) is sourced from CLAUDE.md's load-bearing commitments + the
codebase's prior precedent (`signal_kinds.py` rule-of-three deferral docstring;
`trust_scorer.py` functional-core split; `codegenie.types.identifiers` newtypes
for probe IDs / warning IDs / package managers). Nothing novel; no arXiv lookup
needed.

---

## Stage 4 — Synthesizer + edits applied

**Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns).**
All thirteen Consistency findings resolve toward **shipped Phase-3 code as the
source of truth**. The design narrative (ADR-04-0015 §Decision/§Internal-structure;
phase-arch-design §Component 11; final-design §Component 12 §Type contracts) is
flagged for amendment in the same PR — same precedent S6-04 (ADR-04-0015 stale
"content-hashed path" framing) and S1-05 (ADR-0003 stale framing) used.

The design-pattern opportunities (kernel extract for future `typecheck.<lang>`
siblings; `TypecheckSignalKit` value type) are recorded in Notes-for-implementer
**not** as ACs — per Rule 2 + the validator's rule-of-three threshold, the second
sibling triggers the extract, not the first.

### Edits applied to the story file

1. **Status:** `Ready` → `HARDENED`.
2. **Validation notes** block inserted under the header recording the major changes (see story diff).
3. **Context** paragraph 2 reframed: registration is a function call, not a decorator; subprocess surface is `run_allowlisted` (not `SubprocessJail`) per S6-04's caller-side narrowing precedent; ADR-04-0015 + arch §Component 11 + final-design §Component 12 amendments flagged for same-PR landing.
4. **Goal** paragraph: rewrites prescribed surface to match shipped code.
5. **Acceptance criteria:** every AC rewritten to compile against the shipped APIs surfaced in Clusters A–F; new ACs added for boundary cases (Cluster G T-7), parser fail-loud semantics (Cluster H), event-ordering tightening (Cluster I T-12), mutation barriers (Cluster J T-13–T-15), newtype primitives + purity test (Cluster L), and same-PR ADR + design-doc amendments (Clusters A, B, D synthesis).
6. **Implementation outline** §1 swapped from `SubprocessJail` to `run_allowlisted` with `env_extra={"PATH": ...}`. §2 reframed: collector READS baseline (the orchestrator captures it); §3 rewritten to use `register_signal_kind` as a function call at module top-level; §4 rewritten to point at the new `tests/fence/test_phase4_no_trust_scorer_edits.py`, not `test_kernel_frozen.py`. §5 cassette path corrected per Cluster M.
7. **TDD plan** rewritten to compile against shipped APIs (real `ProcessResult`, real `TrustSignal` shape, real `TrustScorer` constructor, real `signal_kind_registry`, `importlib.import_module` for hyphenated slug). Strict-AND test gains both positive (all-pass) and negative (typecheck-only-fail) cases.
8. **Files to touch** updated: new `tests/fence/test_phase4_no_trust_scorer_edits.py`; `tests/unit/typecheck/test_signal.py` now consolidates parser-purity + boundary cases; cassette path corrected; ADR + arch + final-design amendments listed explicitly.
9. **Notes for the implementer** expanded with:
   - One-paragraph "future-sibling note" for `typecheck.<lang>` extract (rule-of-three deferral; second sibling is the trigger).
   - One-paragraph "ADR-04-0015 amendment in same PR" note mirroring S6-04's pattern.
   - One-line note on the hyphenated-vs-underscored slug convention with a link to S7-01's validation.
   - One-paragraph operator-clarification: baseline-on-missing policy ("degraded-pass" vs "refuse-with-error"). Validator picked degraded-pass; executor surfaces the choice if needed before TDD-Red.

### Validation notes block inserted into the story

```
## Validation notes (2026-05-23)

Hardened by phase-story-validator. Major changes:
- Registration mechanism rewritten (Cluster A, block): @register_signal_kind class-decorator
  form → top-level value-returning function call TYPECHECK_TYPESCRIPT =
  register_signal_kind("typecheck.typescript"). signal_kinds.py:10-14 is explicit
  ("function call, NOT a class decorator"). Module: codegenie.transforms.signal_kinds
  (not codegenie.gates.signals); singleton: signal_kind_registry (not SIGNAL_KIND_REGISTRY).
  No SignalCollector Protocol exists in shipped Phase 3 — collector is a plain async function.
  ADR-04-0015 + arch §Component 11 + final-design §Component 12 are flagged for amendment
  in this PR (same S6-04 + S1-05 precedent).
- TrustSignal/TrustOutcome shape rewritten (Cluster B, block): TrustSignal has no
  confidence field (Pydantic extra="forbid"); details accepts float (shipped is wider
  than arch §line 763 claims). TrustOutcome.confidence is Literal["high", "degraded"]
  not ["high","medium","low"]. Arch §line 763 + final-design §Type contracts flagged
  for widening to match shipped.
- TrustScorer construction rewritten (Cluster C, block): __init__(event_log) required;
  TrustScorer() no-args raises TypeError. Strict-AND test now constructs with an in-memory
  event log fixture, asserts both positive (all-pass → passed=True) and negative
  (typecheck-only-fail → passed=False, failing == ["typecheck.typescript"]) — mutation
  barrier on "scorer reads the typecheck signal".
- Subprocess surface swapped (Cluster D, block): SubprocessJail (per design docs) →
  run_allowlisted (shipped Phase 0 seam S6-04 hardened toward). Reasons: (1) jail's
  Completed.stdout_bytes is size not content — can't parse error count from result;
  (2) JailedEnv is closed sum NpmEnv | GitEnv | JvmEnv — adding TscEnv requires editing
  src/codegenie/transforms/sandbox_jail.py, contradicting the story's own AC; (3) jail's
  result variants don't include a Missing analog. run_allowlisted returns full stdout
  bytes, takes env_extra for PATH-scoping (matches S6-04 caller-side narrow admission),
  and treats timeout as ProbeTimeoutError + missing-binary as ToolMissingError —
  collector catches both and rewrites as degraded-TrustSignal. ProcessResult fields are
  returncode + stdout: bytes + stderr: bytes (not exit_code + stdout: str). tsc admitted
  bare ("tsc") per S6-04; env_extra={"PATH": str(repo / "node_modules" / ".bin")} pins
  narrow admission. ADR-04-0015 + arch + final-design flagged for amendment.
- Plugin import path fixed (Cluster E, block): bare import plugins.vulnerability_remediation
  __node__npm.adapters.ts_typecheck_signal raises SyntaxError (Python parser rejects
  hyphens, but per S7-01 hardening "loader uses the literal hyphenated slug"). Real
  fence: importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal").
- Kernel-frozen claim corrected (Cluster F, block): tests/fence/test_kernel_frozen.py
  scopes Phase-3 packages ({plugins, transforms, vuln_index, primitives}) OUT of frozen
  (lines 271-286). It does NOT catch edits to trust_scorer.py. AC replaced with a new
  Phase-4-scoped fence tests/fence/test_phase4_no_trust_scorer_edits.py asserting zero
  diff on the three named Phase-3 trust-scorer files.
- Baseline-cache semantics pinned (Cluster G, block): <repo-sha> is git rev-parse HEAD
  of the pre-patch snapshot, supplied by the orchestrator via SignalContext. Collector
  reads, never captures. Missing-baseline → degraded-pass TrustSignal with explicit
  details (Phase-3 baseline-bootstrap convention). Four boundary tests added.
- Parser fail-loud (Cluster H, harden): _parse_tsc_error_count returns ErrorCount |
  UnparseableOutput sum type. Five+ stdout fixtures: zero-no-summary, singular, plural,
  multi-file, stderr-only failure. tsc --version captured into details for forensics.
- Event-ordering test tightened (Cluster I, harden): assert ts_evt exists AND (no
  NpmTestStarted OR every index > ts_evt). Executor must verify event-class names against
  shipped src/codegenie/plugins/events.py before TDD-Red; if any names are new, scope
  to S6-08 not S6-05.
- Mutation barriers added (Cluster J, harden): positive registry-membership assertion,
  name-coupling test (registered constant == TrustSignal.kind), baseline I/O idempotence.
- Newtype primitives + purity AC added (Cluster L, harden): RepoSha, ErrorCount newtypes;
  AST-walking purity test on the pure parser + comparator.
- Cassette path corrected (Cluster M, nit): tests/cassettes/anthropic/<test_module>/<test_function>.yaml.

Future-sibling extract (Notes-for-implementer only — Rule 2, defer): the second
typecheck.<lang> (Python in Phase 7.5) triggers the kernel extract along
(binary, parse_fn, baseline_key) axes. First sibling ships the precedent flat.

Full audit log: [`_validation/S6-05-typecheck-typescript-signal.md`](_validation/S6-05-typecheck-typescript-signal.md).
```

---

## Verdict — **HARDENED**

Story rewritten in place. All thirteen Consistency-block findings resolved
toward shipped Phase-3 code with companion ADR / design-doc amendments flagged
for same-PR landing (S6-04 + S1-05 precedent). All Coverage + Test-Quality
hardenings applied as new or rewritten ACs. Design-pattern opportunities
recorded in Notes-for-implementer per Rule 2.

The executor's first task is to verify event-class names against shipped
`src/codegenie/plugins/events.py` (Cluster I) and to confirm the baseline-on-
missing operator policy (Cluster G synthesis). Both are explicitly called out
in Notes-for-implementer; neither blocks Red-Green-Refactor entry.
