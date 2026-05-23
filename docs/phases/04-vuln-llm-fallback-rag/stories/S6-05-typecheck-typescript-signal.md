# Story S6-05 — `typecheck.typescript` SignalKind + `tsc` collector

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** M
**Depends on:** S6-04 (bare-name `"tsc"` admitted to `ALLOWED_BINARIES`)
**ADRs honored:** ADR-04-0015 (`typecheck.typescript` SignalKind; Registry + Open/Closed), production ADR-0037 (layered analysis funnel — first `typecheck.<lang>` lands), production ADR-0031 (plugin scoping — signal is plugin-local), production ADR-0010 (open trust-scorer registry — Open/Closed by design)

## Validation notes (2026-05-23)

Hardened by `phase-story-validator`. Major changes:

- **Registration mechanism rewritten (Cluster A, block):** `@register_signal_kind(...)`
  class-decorator form → top-level value-returning function call
  `TYPECHECK_TYPESCRIPT = register_signal_kind("typecheck.typescript")`.
  `src/codegenie/transforms/signal_kinds.py:10-14` is explicit ("function call,
  NOT a class decorator"). Module: `codegenie.transforms.signal_kinds` (not
  `codegenie.gates.signals`); singleton: `signal_kind_registry` (not
  `SIGNAL_KIND_REGISTRY`). No `SignalCollector` Protocol exists in shipped
  Phase 3 — collector is a plain `async` function. ADR-04-0015 +
  `phase-arch-design.md` §Component 11 + `final-design.md` §Component 12 are
  flagged for amendment in this PR (same S6-04 + S1-05 precedent).
- **`TrustSignal` / `TrustOutcome` shape rewritten (Cluster B, block):**
  `TrustSignal` has **no** `confidence` field (`outcomes.py:377-388`; Pydantic
  `extra="forbid"`); `details` accepts `float` (shipped is wider than arch §line
  763 claims). `TrustOutcome.confidence` is `Literal["high", "degraded"]`
  (`outcomes.py:403`), not `["high","medium","low"]`. Arch §line 763 +
  final-design §Type contracts flagged for widening to match shipped.
- **`TrustScorer` construction rewritten (Cluster C, block):** `__init__(event_log)`
  required (`trust_scorer.py:135`); `TrustScorer()` no-args raises `TypeError`.
  Strict-AND test now constructs with an in-memory event-log fixture, asserts
  **both** positive (all-pass → `passed=True`) **and** negative (typecheck-only-
  fail → `passed=False`, `failing == ["typecheck.typescript"]`) — mutation
  barrier on "scorer reads the typecheck signal".
- **Subprocess surface swapped (Cluster D, block):** `SubprocessJail` (per design
  docs) → `run_allowlisted` (shipped Phase 0 seam S6-04 hardened toward).
  Reasons: (1) jail's `Completed.stdout_bytes` is **size** not content — cannot
  parse error count from result (`sandbox_jail.py:215-227`); (2) `JailedEnv` is
  closed sum `NpmEnv | GitEnv | JvmEnv` (`sandbox_jail.py:148`) — adding `TscEnv`
  requires editing `src/codegenie/transforms/sandbox_jail.py`, contradicting
  the story's own AC; (3) jail's result variants don't include a `Missing`
  analog. `run_allowlisted` returns full `stdout: bytes`, takes `env_extra` for
  PATH-scoping (matches S6-04 caller-side narrow admission), and treats timeout
  as `ProbeTimeoutError` + missing-binary as `ToolMissingError` — collector
  catches both and rewrites as degraded-`TrustSignal`. `ProcessResult` fields
  are `returncode` + `stdout: bytes` + `stderr: bytes` (`exec/__init__.py:159-169`)
  — **not** `exit_code` + `stdout: str`. `tsc` admitted **bare** (`"tsc"`) per
  S6-04; `env_extra={"PATH": str(repo / "node_modules" / ".bin")}` pins narrow
  admission. ADR-04-0015 + arch + final-design flagged for amendment.
- **Plugin import path fixed (Cluster E, block):** bare
  `import plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal`
  raises `SyntaxError` (Python parser rejects hyphens, but per S7-01 hardening
  "loader uses the literal hyphenated slug"). Real fence:
  `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`.
- **`test_kernel_frozen` claim corrected (Cluster F, block):**
  `tests/fence/test_kernel_frozen.py` scopes Phase-3 packages
  (`{plugins, transforms, vuln_index, primitives}`) **out** of frozen (lines
  271–286). It does **not** catch edits to `trust_scorer.py`. AC replaced with
  a new Phase-4-scoped fence `tests/fence/test_phase4_no_trust_scorer_edits.py`
  asserting zero diff on the three named Phase-3 trust-scorer files.
- **Baseline-cache semantics pinned (Cluster G, block):** `<repo-sha>` is `git
  rev-parse HEAD` of the **pre-patch** snapshot, supplied by the orchestrator
  via `SignalContext`. Collector **reads**, never **captures**. Missing-baseline
  → degraded-pass `TrustSignal` with explicit `details["degraded_reason"] =
  "no_baseline"` + `details["error_count"] = N` (Phase-3 baseline-bootstrap
  convention). Four boundary tests added.
- **Parser fail-loud (Cluster H, harden):** `_parse_tsc_error_count` returns
  `ErrorCount | UnparseableOutput` sum type. Five+ stdout fixtures: zero-no-
  summary, singular, plural, multi-file, stderr-only failure. `tsc --version`
  captured into `details` for forensics.
- **Event-ordering test tightened (Cluster I, harden):** assert `ts_evt` exists
  AND (no `NpmTestStarted` OR every index > `ts_evt`). Executor must verify
  event-class names against shipped `src/codegenie/plugins/events.py` before
  TDD-Red; if any names are new, scope to S6-08 not S6-05.
- **Mutation barriers added (Cluster J, harden):** positive registry-membership
  assertion, name-coupling test (registered constant equals `TrustSignal.kind`),
  baseline I/O idempotence.
- **Newtype primitives + purity AC added (Cluster L, harden):** `RepoSha`,
  `ErrorCount` newtypes; AST-walking purity test on the pure parser + comparator.
- **Cassette path corrected (Cluster M, nit):**
  `tests/cassettes/anthropic/<test_module>/<test_function>.yaml`.

Future-sibling extract (Notes-for-implementer only — Rule 2, defer): the
second `typecheck.<lang>` (Python in Phase 7.5) triggers the kernel extract
along `(binary, parse_fn, baseline_key)` axes. First sibling ships the
precedent flat.

Full audit log:
[`_validation/S6-05-typecheck-typescript-signal.md`](_validation/S6-05-typecheck-typescript-signal.md).

## Context

Roadmap exit criterion #3 + production ADR-0037 commit Phase 4 to landing the
**first** `typecheck.<lang>` `SignalKind` into Phase 3's open signal-kind
registry. The signal is `typecheck.typescript`; it runs `tsc --noEmit --pretty
false` against the working tree (30 s wall-clock cap); strict-AND folds it
through Phase-3 `TrustScorer` **with zero edits to Phase 3 trust-scorer code**
(registry pattern + Open/Closed). Phase 7's distroless plugin won't have a Node
toolchain and won't register the signal.

The signal lives at
`plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`.
Phase 3 shipped `register_signal_kind` as an **open registry value-returning
function call** (CLAUDE.md §Open/Closed seams; `signal_kinds.py:10-14, 125-145`
— "function call, NOT a class decorator"), so Phase 4 adds one module +
registers the kind at module top-level + provides a plain `async` collector
function — never edits central dispatch.

Strict-AND with baseline (`.codegenie/typecheck/baseline-<repo-sha>.json`)
passes iff `new_errors_after <= new_errors_before` — the LLM only needs to not
*introduce* new type errors; pre-existing repo-level errors don't block the
gate. `<repo-sha>` is `git rev-parse HEAD` of the **pre-patch snapshot** (the
orchestrator captures it; the collector only reads).

The subprocess surface is `codegenie.exec.run_allowlisted` with `argv=["tsc",
...]` (bare name per S6-04's hardening) and `env_extra={"PATH": str(repo /
"node_modules" / ".bin")}` to enforce that the `tsc` resolved at spawn time is
**always** the repo-local copy (`asyncio.create_subprocess_exec` resolves
`argv[0]` via the child's `PATH`). `SubprocessJail` is the wrong surface here:
its `Completed.stdout_bytes` is a size not content, and its `JailedEnv` is a
closed sum that does not admit a `tsc` variant without editing
`src/codegenie/transforms/sandbox_jail.py` (which would contradict this story's
own no-edits-to-Phase-3 AC). ADR-04-0015 §Decision, `phase-arch-design.md`
§Component 11, and `final-design.md` §Component 12 carry "`SubprocessJail` (30
s cap)" framing that is mechanically wrong against shipped code — AC-13 carries
the amendment in the same PR (S6-04 + S1-05 precedent).

This story lands the *base* collector + registration + strict-AND fold-in; the
applicability matrix (`tsconfig.json` + `.ts` files detection per Gap 4) is
S6-06's surgical follow-up.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 11 — TypecheckTypescriptSignal](../phase-arch-design.md) (lines 616–623); §Goals — G10 (line 37); §Deployment view; §Edge case row 9 (missing `tsc`); §Type contracts (line 759 — `TypecheckNodeSignal` Pydantic model); §Design patterns applied row 9 (Registry + Open/Closed). **AC-13 amends §Component 11's "SubprocessJail" → "run_allowlisted" framing.**
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) (the whole story is this ADR's implementation). **AC-13 amends §Decision + §Internal-structure framing of "SubprocessJail" → "run_allowlisted with env_extra PATH-scoping" + "decorator" → "function call".**
- **Production ADRs:** [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) (first `typecheck.<lang>` lands here); [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (TrustSignal shape); [production ADR-0010](../../../production/adrs/0010-pydantic-models.md) (Open/Closed for trust-scorer); [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) (signal is plugin-local).
- **Source design:** [final-design.md §Component 12 — TypecheckTypescriptSignal](../final-design.md); §Goal "typecheck.typescript SignalKind lands". **AC-13 amends Component 12's Internal-design paragraph similarly.**
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered (`TypecheckTypescriptSignal` paragraph).
- **Sibling validations to mirror:**
  [`_validation/S6-04-tsc-allowed-binary.md`](_validation/S6-04-tsc-allowed-binary.md) (bare-name + caller-side `env_extra` PATH-scoping precedent);
  [`../../03-vuln-deterministic-recipe/stories/_validation/S7-01-vuln-node-npm-plugin-scaffold.md`](../../03-vuln-deterministic-recipe/stories/_validation/S7-01-vuln-node-npm-plugin-scaffold.md) (line 32 — "loader uses the literal hyphenated slug").
- **Shipped Phase-3 source-of-truth files:**
  `src/codegenie/transforms/signal_kinds.py` (function-call API; `signal_kind_registry` singleton; `BUILD = register_signal_kind("build")` pattern at line 154);
  `src/codegenie/transforms/outcomes.py` (`TrustSignal` lines 377–388 — three fields, no confidence; `TrustOutcome.confidence: Literal["high","degraded"]` line 403);
  `src/codegenie/transforms/trust_scorer.py` (constructor injection at line 135; `UnregisteredSignalKind` raised on unknown kinds);
  `src/codegenie/exec/__init__.py` (`run_allowlisted` signature lines 235–291; `env_extra` PATH-scoping seam; `ProcessResult` fields at lines 159–169; `ALLOWED_BINARIES` bare-name discipline at lines 105–130);
  `src/codegenie/plugins/events.py` (Phase-3 event taxonomy — executor verifies event names referenced in the integration test);
  `tests/fence/test_kernel_frozen.py` (lines 271–286 — Phase-3 packages scoped out of frozen).

## Goal

Ship `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`
that:

1. Registers `typecheck.typescript` against the shipped Phase-3 `signal_kind_registry`
   via a module-top-level `TYPECHECK_TYPESCRIPT = register_signal_kind("typecheck.typescript")`
   call (the shipped pattern; mirrors `BUILD = register_signal_kind("build")` at
   `signal_kinds.py:154`);
2. Exposes a plain `async` collector function `collect_typecheck_typescript_signal(
   repo_root: Path, baseline_repo_sha: RepoSha, timeout_s: float = 30.0) -> TrustSignal`
   that invokes `["tsc", "--noEmit", "--pretty", "false"]` via
   `codegenie.exec.run_allowlisted` with `env_extra={"PATH": str(repo_root /
   "node_modules" / ".bin")}` and `timeout_s=30.0`;
3. Reads the baseline cache at `.codegenie/typecheck/baseline-<repo-sha>.json`
   (orchestrator-captured pre-patch); compares the post-patch error count via
   `new_errors_after <= new_errors_before`;
4. Emits a `TrustSignal(kind=TYPECHECK_TYPESCRIPT, passed: bool, details:
   dict[str, str|int|bool|float])` value (Pydantic frozen `extra="forbid"`;
   `details` is the shipped wider shape — no `confidence` field on `TrustSignal`);
5. Folds into Phase-3 `TrustScorer` strict-AND with **zero edits** to the three
   named Phase-3 trust-scorer files (asserted by a new
   `tests/fence/test_phase4_no_trust_scorer_edits.py`).

## Acceptance criteria

- [ ] **AC-1: Registered exactly once** — `tests/fence/test_typecheck_signal_registered.py`
  asserts (a) `SignalKind("typecheck.typescript") in signal_kind_registry` (positive
  membership) and (b) the module's `TYPECHECK_TYPESCRIPT` constant `is` the same
  `SignalKind` value (name-coupling — catches "registers one name, emits another"
  mutation). Test uses
  `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`
  to force-load (the loader uses the literal hyphenated slug per S7-01 hardening).
- [ ] **AC-2: Collector is a plain `async` function** with the explicit signature
  `async def collect_typecheck_typescript_signal(repo_root: Path,
  baseline_repo_sha: RepoSha, timeout_s: float = 30.0) -> TrustSignal`. **No
  `SignalCollector` Protocol** is referenced (none exists in Phase 3). `mypy
  --strict` accepts the module.
- [ ] **AC-3: Subprocess invocation shape pinned** — `run_allowlisted` is called
  with `argv == ["tsc", "--noEmit", "--pretty", "false"]`, `cwd=repo_root`,
  `timeout_s=30.0`, and `env_extra` whose `"PATH"` key equals
  `str(repo_root / "node_modules" / ".bin")`. Asserted by
  `tests/unit/typecheck/test_signal.py::test_invokes_tsc_correctly` mocking
  `codegenie.exec.run_allowlisted` with an `AsyncMock` and inspecting `call_args`.
  **Bare-name discipline** (S6-04): the test additionally asserts `argv[0] ==
  "tsc"` (not `"./node_modules/.bin/tsc"`).
- [ ] **AC-4: `TrustSignal` shape conforms to shipped `outcomes.py:377-388`** —
  three fields: `kind: SignalKind`, `passed: bool`, `details: dict[str, str |
  int | bool | float]`. The collector **never** sets a `confidence=` kwarg
  (Pydantic `extra="forbid"` would raise). `tsc --version` capture lives in
  `details["tsc_version"]` for forensics.
- [ ] **AC-5: Strict-AND fold-in (no Phase-3 trust-scorer edits)** —
  `tests/unit/trust_scorer/test_typecheck_kind.py` constructs `TrustScorer(
  event_log=in_memory_event_log_fixture)` (the shipped constructor takes
  `event_log`; no-arg form raises `TypeError`). Asserts **both directions**:
  (a) six signals all with `passed=True` (including a `typecheck.typescript`
  signal) → `outcome.passed is True` AND `outcome.failing == []`;
  (b) six signals with `typecheck.typescript` `passed=False` and the other five
  `passed=True` → `outcome.passed is False` AND `outcome.failing ==
  [SignalKind("typecheck.typescript")]`. **No edits to `src/codegenie/transforms/
  trust_scorer.py`, `src/codegenie/transforms/signal_kinds.py`, or `src/codegenie/
  transforms/outcomes.py`** — asserted by AC-6.
- [ ] **AC-6: New Phase-4 fence test** —
  `tests/fence/test_phase4_no_trust_scorer_edits.py` runs `git diff --name-only
  HEAD~N -- src/codegenie/transforms/trust_scorer.py src/codegenie/transforms/
  signal_kinds.py src/codegenie/transforms/outcomes.py` (where `N` is the depth
  to S6-05's first commit) and asserts the result is empty for any commit in
  the S6-05 PR. (`test_kernel_frozen.py` does **not** catch these — Phase-3
  packages are scoped out of its frozen set; see Validation notes.)
- [ ] **AC-7: Baseline strict-AND boundary cases** — `tests/unit/typecheck/
  test_signal.py::test_baseline_boundary` parametrizes five cases:
  `(baseline=5, after=4) → pass`, `(5,5) → pass`, `(5,6) → fail`,
  `(0,0) → pass`, `(0,1) → fail`. Mutation barrier on `<` vs `<=`.
- [ ] **AC-8: Baseline-cache contract** — `<repo-sha>` is `git rev-parse HEAD`
  of the **pre-patch snapshot**, passed to the collector as a typed `RepoSha`
  newtype. The collector **only reads** `.codegenie/typecheck/baseline-<repo-sha>.json`;
  it never captures the baseline (the orchestrator captures on a clean tree —
  one tier up; out of scope for this story). Missing-baseline → degraded-pass:
  `TrustSignal(kind=TYPECHECK_TYPESCRIPT, passed=True, details={"degraded_reason":
  "no_baseline", "error_count": <current_count>, "tsc_version": "..."})`.
- [ ] **AC-9: Timeout behavior** — `run_allowlisted` raises `ProbeTimeoutError`
  on 30 s expiry. Collector catches and emits `TrustSignal(kind=TYPECHECK_TYPESCRIPT,
  passed=False, details={"timeout": True, "timeout_s": 30.0, "tsc_version":
  <best-effort or "unknown">})`. Asserted via mocked `run_allowlisted` raising
  `ProbeTimeoutError`.
- [ ] **AC-10: Missing `tsc` behavior** (edge case row 9) — `run_allowlisted`
  raises `ToolMissingError` when bare `tsc` cannot be resolved on
  `env_extra["PATH"]` (post-S6-04, `tsc` IS on the allowlist; this is the
  on-PATH-resolution failure path). Collector emits `TrustSignal(kind=
  TYPECHECK_TYPESCRIPT, passed=False, details={"degraded_reason":
  "no_tsconfig_or_tsc"})`. (S6-06 lifts this to the applicability matrix;
  S6-05 ships the degraded path.)
- [ ] **AC-11: Parser is pure + fail-loud** — `_parse_tsc_error_count(
  returncode: int, stdout: bytes) -> ErrorCount | UnparseableOutput` is a
  pure function (no I/O, no module state); unit-tested with five+ stdout
  fixtures: zero-errors-no-summary (returncode==0, empty stdout → `ErrorCount(0)`);
  singular `Found 1 error in 1 file.`; plural `Found 5 errors in 3 files.`;
  multi-file with diagnostics interspersed; non-zero returncode with no
  parseable summary (→ `UnparseableOutput`). An `UnparseableOutput` from the
  parser → `TrustSignal(passed=False, details={"degraded_reason":
  "tsc_unparseable_output", "stderr_head": stderr[:256].decode(errors='replace')})`.
- [ ] **AC-12: Purity AST-fence** — `tests/fence/test_phase4_typecheck_purity.py`
  AST-walks `plugins/vulnerability-remediation--node--npm/adapters/
  ts_typecheck_signal.py` and asserts that `_parse_tsc_error_count` and
  `_passes_strict_and` (whichever names land) contain **no** imports of `os`,
  `pathlib`, `asyncio`, `subprocess`, `json`, and **no** module-level state
  reads. (Functional-core / imperative-shell discipline, CLAUDE.md.)
- [ ] **AC-13: ADR + design-doc amendments in same PR** —
  `docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md`
  §Decision + §Internal structure rewrites "`SubprocessJail`" → "`run_allowlisted`
  with caller-side PATH-scoping via `env_extra`" and "`@register_signal_kind`
  decorator" → "module-top-level `register_signal_kind(...)` function call".
  `docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md` §Component 11 +
  §Type contracts (line 763) update similarly (and widen `details` to
  `dict[str, str|int|bool|float]` to match shipped). `docs/phases/04-vuln-llm-fallback-rag/final-design.md`
  §Component 12 Internal-design paragraph updates similarly. (Same S6-04 +
  S1-05 precedent: shipped code wins; design narrative amendments ride the
  implementing PR.)
- [ ] **AC-14: Plugin import-surface side-effect** — the plugin's bundle import
  surface (per S7-01 — `plugins/vulnerability-remediation--node--npm/api.py`'s
  side-effects, or wherever the eager-import lives) imports
  `ts_typecheck_signal` so `register_signal_kind("typecheck.typescript")` fires
  on plugin load. Asserted by AC-1 (registry membership after `importlib.import_module`).
- [ ] **AC-15: Baseline I/O idempotence** — `tests/unit/typecheck/
  test_baseline_io.py` writes a baseline JSON, reads it back, asserts
  round-trip equality (bytes-identical), then runs **two** concurrent collector
  invocations against the same repo (via `asyncio.gather`) and asserts both
  observe the same baseline (no race, no half-written read). Documents the
  single-writer convention.
- [ ] **AC-16: Integration test — `tests/integration/test_typecheck_signal_catches_signature_drift.py`** —
  cassette-driven test where the LLM emits a `callsite_rewrite` `PlanProposal`
  that calls a *hallucinated* method; `tsc` catches the
  `TS2339 Property 'X' does not exist on type 'Y'` error; signal returns
  `passed=False`; **gate fails before `npm test` runs**. Event-ordering
  assertion: `ts_evt` (the typecheck-signal-evaluated event) MUST exist; any
  `NpmTestStarted` event MUST appear at a strictly greater index. **Executor
  must verify** the four event-class names (`SignalEvaluated`, `LeafReturned`,
  `GateBlocked`, `NpmTestStarted` per the original story draft) against shipped
  `src/codegenie/plugins/events.py` before writing the test. If any name is
  new, scope its addition to S6-08 (attempt-anchor emission) — S6-05 must not
  silently introduce new event types.
- [ ] **AC-17: Cassette path conforms to arch §line 794** —
  `tests/cassettes/anthropic/test_typecheck_signal_catches_signature_drift/test_typecheck_catches_hallucinated_method_before_npm_test.yaml`.
  Cassette recording deferred to `make refresh-cassettes` (S3-06's discipline);
  AC-16 marks the integration test `@pytest.mark.skip(reason="cassette pending S3-06 refresh")`
  until the cassette lands.
- [ ] **AC-18: `make check`, `make typecheck`, `make lint-imports`, `make fence`,
  `make test` all green.**

## Implementation outline

1. Add newtypes (if not already present) to `src/codegenie/types/identifiers.py`:
   - `RepoSha = NewType("RepoSha", str)` — `git rev-parse HEAD` of the pre-patch snapshot.
   - `ErrorCount = NewType("ErrorCount", int)` — tsc error count (non-negative; smart-constructor enforces).
   (Both cross ≥ 2 module boundaries — orchestrator ↔ collector ↔ parser ↔ filesystem — so the newtype carries weight.)

2. Create `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`:

   ```python
   """typecheck.typescript SignalKind + collector for the Node/npm plugin.

   ADR-04-0015: first typecheck.<lang> per production ADR-0037. Registers
   against the shipped Phase-3 signal_kind_registry via a module-top-level
   register_signal_kind call (matches BUILD/INSTALL/TESTS/... pattern at
   signal_kinds.py:154-158 — function call, NOT a decorator).
   """
   from __future__ import annotations

   import json
   import re
   from dataclasses import dataclass
   from pathlib import Path

   from codegenie.errors import ProbeTimeoutError, ToolMissingError
   from codegenie.exec import run_allowlisted
   from codegenie.transforms.outcomes import TrustSignal
   from codegenie.transforms.signal_kinds import register_signal_kind
   from codegenie.types.identifiers import ErrorCount, RepoSha

   TYPECHECK_TYPESCRIPT = register_signal_kind("typecheck.typescript")
   """Module-top-level registration — the import-time side-effect that puts
   "typecheck.typescript" in signal_kind_registry. The plugin's api.py
   must import this module so the side-effect fires on plugin load."""


   # --- pure core ---------------------------------------------------------

   @dataclass(frozen=True)
   class UnparseableOutput:
       """Sum-type sibling of ErrorCount — parser saw stdout it cannot reduce."""
       reason: str  # short token for forensics


   _SUMMARY_RE = re.compile(rb"^Found (\d+) errors? in \d+ files?\.$", re.MULTILINE)


   def _parse_tsc_error_count(returncode: int, stdout: bytes) -> ErrorCount | UnparseableOutput:
       """Pure parser. exit 0 ⇒ ErrorCount(0); else look for summary line."""
       if returncode == 0:
           return ErrorCount(0)
       match = _SUMMARY_RE.search(stdout)
       if match is None:
           return UnparseableOutput("no_summary_line")
       return ErrorCount(int(match.group(1)))


   def _passes_strict_and(baseline: ErrorCount, current: ErrorCount) -> bool:
       """Pure comparator. Pass iff current <= baseline."""
       return current <= baseline


   # --- imperative shell --------------------------------------------------

   async def collect_typecheck_typescript_signal(
       repo_root: Path,
       baseline_repo_sha: RepoSha,
       timeout_s: float = 30.0,
   ) -> TrustSignal:
       """Run tsc and emit a TrustSignal. Reads (never captures) the baseline."""
       baseline_path = repo_root / ".codegenie" / "typecheck" / f"baseline-{baseline_repo_sha}.json"
       try:
           result = await run_allowlisted(
               argv=["tsc", "--noEmit", "--pretty", "false"],
               cwd=repo_root,
               timeout_s=timeout_s,
               env_extra={"PATH": str(repo_root / "node_modules" / ".bin")},
           )
       except ProbeTimeoutError:
           return TrustSignal(
               kind=TYPECHECK_TYPESCRIPT,
               passed=False,
               details={"timeout": True, "timeout_s": timeout_s},
           )
       except ToolMissingError:
           return TrustSignal(
               kind=TYPECHECK_TYPESCRIPT,
               passed=False,
               details={"degraded_reason": "no_tsconfig_or_tsc"},
           )

       parsed = _parse_tsc_error_count(result.returncode, result.stdout)
       if isinstance(parsed, UnparseableOutput):
           return TrustSignal(
               kind=TYPECHECK_TYPESCRIPT,
               passed=False,
               details={
                   "degraded_reason": "tsc_unparseable_output",
                   "stderr_head": result.stderr[:256].decode(errors="replace"),
               },
           )
       current = parsed

       if not baseline_path.exists():
           return TrustSignal(
               kind=TYPECHECK_TYPESCRIPT,
               passed=True,
               details={"degraded_reason": "no_baseline", "error_count": int(current)},
           )
       baseline = ErrorCount(int(json.loads(baseline_path.read_text())["error_count"]))
       passed = _passes_strict_and(baseline, current)
       return TrustSignal(
           kind=TYPECHECK_TYPESCRIPT,
           passed=passed,
           details={"baseline_error_count": int(baseline), "current_error_count": int(current)},
       )
   ```

3. Hook the plugin's import-surface (per S7-01 — `plugins/vulnerability-remediation--node--npm/api.py`)
   so importing the plugin imports `ts_typecheck_signal`, triggering the
   `register_signal_kind` side-effect. The fence (AC-1) asserts this via
   `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`
   directly (the hyphenated slug — Python's `import` parser rejects hyphens;
   `importlib` accepts them when the loader handles the mapping).
4. **Land the new Phase-4 fence** `tests/fence/test_phase4_no_trust_scorer_edits.py`
   asserting `git diff --name-only HEAD~N -- src/codegenie/transforms/trust_scorer.py
   src/codegenie/transforms/signal_kinds.py src/codegenie/transforms/outcomes.py`
   is empty for any commit in the S6-05 PR.
5. **Apply AC-13's documentation amendments** in the same PR:
   ADR-04-0015 §Decision + §Internal-structure; `phase-arch-design.md`
   §Component 11 + §Type contracts line 763; `final-design.md` §Component 12
   Internal-design paragraph.
6. The integration test cassette belongs under
   `tests/cassettes/anthropic/test_typecheck_signal_catches_signature_drift/`;
   record via `make refresh-cassettes` (S3-06). Mark
   `@pytest.mark.skip(reason="cassette pending S3-06 refresh")` until landed.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/fence/test_typecheck_signal_registered.py
import importlib

from codegenie.transforms.signal_kinds import signal_kind_registry
from codegenie.types.identifiers import SignalKind


def test_typecheck_typescript_registered_with_correct_kind():
    """AC-1: positive registry membership + name-coupling between the
    module's TYPECHECK_TYPESCRIPT constant and the SignalKind in TrustSignal.kind.

    Catches the off-by-swap mutation ("typescript.typecheck") that a bare
    list-comprehension equality would miss.
    """
    mod = importlib.import_module(
        "plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal"
    )
    expected = SignalKind("typecheck.typescript")
    assert expected in signal_kind_registry
    assert mod.TYPECHECK_TYPESCRIPT == expected


# tests/unit/typecheck/test_signal.py
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codegenie.exec import ProcessResult
from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.transforms.outcomes import TrustSignal
from codegenie.types.identifiers import ErrorCount, RepoSha
from plugins.vulnerability_remediation__node__npm.adapters import ts_typecheck_signal as mod
# NOTE: the underscored name above is the directory-on-disk Python module path
# IF the loader exposes underscored mirror modules. If not (per S7-01 — loader
# uses literal hyphenated slug), the test imports via importlib.import_module.
# Executor: verify and pick one form before writing the test body.


@pytest.mark.asyncio
async def test_invokes_tsc_correctly(tmp_path):
    """AC-3: argv bare-tsc + env_extra PATH-scoping (S6-04 caller-side narrow admission)."""
    fake_result = ProcessResult(returncode=0, stdout=b"", stderr=b"")
    with patch.object(mod, "run_allowlisted", new=AsyncMock(return_value=fake_result)) as spy:
        await mod.collect_typecheck_typescript_signal(
            repo_root=tmp_path, baseline_repo_sha=RepoSha("deadbeef"), timeout_s=30.0
        )
    call = spy.call_args
    assert call.kwargs["argv"] == ["tsc", "--noEmit", "--pretty", "false"]
    assert call.kwargs["cwd"] == tmp_path
    assert call.kwargs["timeout_s"] == 30.0
    assert call.kwargs["env_extra"]["PATH"] == str(tmp_path / "node_modules" / ".bin")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "baseline,after,expected_pass",
    [(5, 4, True), (5, 5, True), (5, 6, False), (0, 0, True), (0, 1, False)],
)
async def test_baseline_boundary(tmp_path, baseline, after, expected_pass):
    """AC-7: strict-AND boundary cases. Mutation barrier on < vs <=."""
    (tmp_path / ".codegenie" / "typecheck").mkdir(parents=True)
    (tmp_path / ".codegenie" / "typecheck" / "baseline-cafef00d.json").write_text(
        json.dumps({"error_count": baseline})
    )
    stdout = b"" if after == 0 else f"Found {after} errors in 1 file.\n".encode()
    returncode = 0 if after == 0 else 2
    fake_result = ProcessResult(returncode=returncode, stdout=stdout, stderr=b"")
    with patch.object(mod, "run_allowlisted", new=AsyncMock(return_value=fake_result)):
        result = await mod.collect_typecheck_typescript_signal(
            repo_root=tmp_path, baseline_repo_sha=RepoSha("cafef00d")
        )
    assert result.passed is expected_pass
    assert isinstance(result, TrustSignal)


@pytest.mark.asyncio
async def test_timeout_returns_failed_with_typed_details(tmp_path):
    """AC-9: ProbeTimeoutError → degraded TrustSignal with details.timeout."""
    with patch.object(
        mod, "run_allowlisted", new=AsyncMock(side_effect=ProbeTimeoutError("elapsed_ms=30000"))
    ):
        result = await mod.collect_typecheck_typescript_signal(
            repo_root=tmp_path, baseline_repo_sha=RepoSha("cafef00d")
        )
    assert result.passed is False
    assert result.details["timeout"] is True
    assert result.details["timeout_s"] == 30.0
    # AC-4: no `confidence` field on TrustSignal — Pydantic extra='forbid'
    # would have raised at construction if the collector tried to set one.


@pytest.mark.asyncio
async def test_missing_tsc_returns_degraded(tmp_path):
    """AC-10: ToolMissingError → degraded TrustSignal (edge case row 9)."""
    with patch.object(mod, "run_allowlisted", new=AsyncMock(side_effect=ToolMissingError("tsc"))):
        result = await mod.collect_typecheck_typescript_signal(
            repo_root=tmp_path, baseline_repo_sha=RepoSha("cafef00d")
        )
    assert result.passed is False
    assert result.details["degraded_reason"] == "no_tsconfig_or_tsc"


@pytest.mark.parametrize(
    "returncode,stdout,expected",
    [
        (0, b"", ErrorCount(0)),
        (2, b"Found 1 error in 1 file.\n", ErrorCount(1)),
        (2, b"Found 5 errors in 3 files.\n", ErrorCount(5)),
        (2, b"src/foo.ts:1:1 - error TS2339\nFound 7 errors in 2 files.\nextra noise\n", ErrorCount(7)),
        (2, b"crashed with no summary", None),  # → UnparseableOutput
    ],
)
def test_parse_tsc_error_count(returncode, stdout, expected):
    """AC-11: parser is pure + fail-loud on no-summary."""
    out = mod._parse_tsc_error_count(returncode, stdout)
    if expected is None:
        assert isinstance(out, mod.UnparseableOutput)
    else:
        assert out == expected


# tests/unit/typecheck/test_baseline_io.py
@pytest.mark.asyncio
async def test_baseline_io_roundtrip_and_concurrency(tmp_path):
    """AC-15: baseline JSON round-trip + two concurrent collectors observe same baseline."""
    import asyncio
    (tmp_path / ".codegenie" / "typecheck").mkdir(parents=True)
    path = tmp_path / ".codegenie" / "typecheck" / "baseline-c0ffee.json"
    payload = {"error_count": 3}
    path.write_text(json.dumps(payload))
    assert json.loads(path.read_text()) == payload  # byte-identical round-trip

    fake_result = ProcessResult(returncode=2, stdout=b"Found 3 errors in 1 file.\n", stderr=b"")
    with patch.object(mod, "run_allowlisted", new=AsyncMock(return_value=fake_result)):
        results = await asyncio.gather(
            mod.collect_typecheck_typescript_signal(tmp_path, RepoSha("c0ffee")),
            mod.collect_typecheck_typescript_signal(tmp_path, RepoSha("c0ffee")),
        )
    assert all(r.passed is True for r in results)
    assert all(r.details["baseline_error_count"] == 3 for r in results)


# tests/unit/trust_scorer/test_typecheck_kind.py
def test_trust_scorer_strict_and_with_typecheck_signal(in_memory_event_log):
    """AC-5: TrustScorer folds typecheck.typescript via registry — both directions.

    Mutation barrier: a TrustScorer that returns False on every input passes the
    negative case alone. Asserting BOTH directions catches that mutation.
    """
    import importlib
    importlib.import_module(
        "plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal"
    )
    from codegenie.transforms.trust_scorer import TrustScorer
    from codegenie.transforms.outcomes import TrustSignal
    from codegenie.types.identifiers import SignalKind

    scorer = TrustScorer(event_log=in_memory_event_log)  # AC-5: constructor takes event_log
    kinds = [
        SignalKind("build"), SignalKind("install"), SignalKind("tests"),
        SignalKind("lockfile_policy"), SignalKind("cve_delta"),
        SignalKind("typecheck.typescript"),
    ]
    all_pass = [TrustSignal(kind=k, passed=True, details={}) for k in kinds]
    typecheck_fails = [
        TrustSignal(kind=k, passed=(k != SignalKind("typecheck.typescript")), details={})
        for k in kinds
    ]
    assert scorer.score(all_pass).passed is True
    assert scorer.score(all_pass).failing == []
    out = scorer.score(typecheck_fails)
    assert out.passed is False
    assert out.failing == [SignalKind("typecheck.typescript")]


# tests/fence/test_phase4_no_trust_scorer_edits.py
# AC-6: assert zero changes to the three named Phase-3 trust-scorer files
# for any commit in the S6-05 PR. Implementation TBD by executor — likely
# subprocess to git, scoped against the merge-base.


# tests/fence/test_phase4_typecheck_purity.py
# AC-12: AST-walk the collector module; assert _parse_tsc_error_count and
# _passes_strict_and contain no imports of os/pathlib/asyncio/subprocess/json
# and no module-level state reads.


# tests/integration/test_typecheck_signal_catches_signature_drift.py
@pytest.mark.skip(reason="AC-17: cassette pending S3-06 refresh")
@pytest.mark.asyncio
async def test_typecheck_catches_hallucinated_method_before_npm_test(
    fixture_with_bad_llm_cassette, event_stream_capturer,
):
    """AC-16: tsc catches signature drift; gate fails before npm test runs.

    Event ordering: ts_evt (typecheck-signal-evaluated) MUST exist; any
    NpmTestStarted index MUST be strictly greater. Executor verifies the
    four event-class names against shipped src/codegenie/plugins/events.py
    before fleshing this out (and scopes any new event types to S6-08).
    """
    await orchestrator.run(fixture_with_bad_llm_cassette)
    events = event_stream_capturer.recorded
    ts_indices = [i for i, e in enumerate(events) if _is_typecheck_eval(e)]
    npm_indices = [i for i, e in enumerate(events) if _is_npm_test_started(e)]
    assert ts_indices, "typecheck signal was not evaluated"
    ts_evt = ts_indices[-1]
    assert events[ts_evt].passed is False
    for npm_evt in npm_indices:
        assert npm_evt > ts_evt, "npm test started before typecheck signal evaluated"
```

### Green — make it pass

- Land `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`
  with the top-level `TYPECHECK_TYPESCRIPT = register_signal_kind("typecheck.typescript")`
  call (matches `BUILD = register_signal_kind("build")` at `signal_kinds.py:154`).
- Plain `async def collect_typecheck_typescript_signal(repo_root, baseline_repo_sha, timeout_s=30.0) -> TrustSignal`.
- Pure helpers `_parse_tsc_error_count`, `_passes_strict_and` per AC-11 + AC-12.
- Wire `plugins/.../api.py` import-surface so `ts_typecheck_signal` is loaded
  on plugin bundle import (AC-14).
- Land new fences: `tests/fence/test_phase4_no_trust_scorer_edits.py` (AC-6),
  `tests/fence/test_phase4_typecheck_purity.py` (AC-12).
- Apply AC-13 documentation amendments to ADR-04-0015, `phase-arch-design.md`
  §Component 11 + §line 763, `final-design.md` §Component 12 — same-PR.

### Refactor — clean up

- Confirm `_parse_tsc_error_count` returns a sum type (`ErrorCount |
  UnparseableOutput`) — not a sentinel `int` or `Optional[int]`. The discriminated
  union is what makes the shell's `isinstance` branch exhaustive.
- Confirm imperative-shell collector is single-purpose: no parsing logic, no
  comparison logic; just call `run_allowlisted`, switch on the parser's sum
  type, materialize a `TrustSignal`.
- The newtype primitives (`RepoSha`, `ErrorCount`) come from
  `codegenie.types.identifiers` — never raw `str` or `int` for these at
  function boundaries.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `RepoSha`, `ErrorCount` newtypes (AC-8, AC-11). |
| `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` | New — registration + collector + pure helpers (AC-1, AC-2, AC-3, AC-4, AC-9, AC-10, AC-11). |
| `plugins/vulnerability-remediation--node--npm/api.py` (or equivalent eager-import surface per S7-01) | Import `ts_typecheck_signal` so registration fires on plugin load (AC-14). |
| `tests/fence/test_typecheck_signal_registered.py` | Registry-membership + name-coupling fence (AC-1). |
| `tests/fence/test_phase4_no_trust_scorer_edits.py` | New Phase-4-scoped fence asserting zero diff on the three Phase-3 trust-scorer files (AC-6 — `test_kernel_frozen.py` does NOT cover transforms). |
| `tests/fence/test_phase4_typecheck_purity.py` | AST-walk purity fence on `_parse_tsc_error_count` + `_passes_strict_and` (AC-12). |
| `tests/unit/typecheck/test_signal.py` | Subprocess invocation shape, boundary cases, timeout, missing-tsc, parser fixtures (AC-3, AC-7, AC-9, AC-10, AC-11). |
| `tests/unit/typecheck/test_baseline_io.py` | Baseline round-trip + concurrent-collector idempotence (AC-15). |
| `tests/unit/trust_scorer/test_typecheck_kind.py` | Both-directions strict-AND fold-in with constructor-injected event log (AC-5). |
| `tests/integration/test_typecheck_signal_catches_signature_drift.py` | Cassette-driven event-ordering integration (AC-16; skipped until S3-06 cassette refresh — AC-17). |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` | AC-13 — §Decision + §Internal-structure amendments (SubprocessJail → run_allowlisted; decorator → function call). |
| `docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md` | AC-13 — §Component 11 + §Type contracts (line 763) amendments (subprocess surface; widen `details` type). |
| `docs/phases/04-vuln-llm-fallback-rag/final-design.md` | AC-13 — §Component 12 Internal-design paragraph amendments. |

## Out of scope

- The applicability matrix (`tsconfig.json` + `.ts` files detection per Gap 4) — **S6-06**.
- Promotion to a shared `vulnerability-remediation--node--*` base plugin — Phase 7 / Phase 6.5 decision (arch open question 3, 8).
- Phase 15 / LSP-richer interactive type signals — per [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), out of scope.
- The cassette recording for `test_typecheck_signal_catches_signature_drift` (record via `make refresh-cassettes` per S3-06).
- Baseline *capture* on a clean pre-patch snapshot — the orchestrator's responsibility (one tier up); the collector only reads.
- Extracting a `TypecheckSignalKit(kind, binary, parse_fn, baseline_key_fn)` kernel for future `typecheck.<lang>` siblings — defer to the second sibling (Phase 7.5 Python) per rule-of-three.

## Notes for the implementer

- **Zero edits to Phase-3 trust-scorer code.** The strict-AND fold-in is by
  registry lookup; if you find yourself reaching for `src/codegenie/transforms/
  trust_scorer.py`, `signal_kinds.py`, or `outcomes.py` to add a case arm or
  field, you have broken Open/Closed. Surface per Global Rule 7. AC-6's new
  fence asserts zero-diff on those three files.

- **Registration is a function call, NOT a decorator.** Shipped
  `signal_kinds.py:10-14` is explicit about this. The pattern is `TYPECHECK_TYPESCRIPT
  = register_signal_kind("typecheck.typescript")` at module top level (mirrors
  `BUILD = register_signal_kind("build")` at `signal_kinds.py:154`). The
  collector itself is a plain `async` function — there is no `SignalCollector`
  Protocol to implement (none exists in Phase 3).

- **Subprocess surface is `run_allowlisted`, not `SubprocessJail`.** Three
  shipped-code reasons (see Validation notes Cluster D); S6-04 hardened the
  caller-side narrow-admission pattern through `env_extra={"PATH": ...}` to
  exactly this surface. ADR-04-0015's "SubprocessJail" framing is amended in
  the same PR per AC-13.

- **`tsc` is admitted bare per S6-04.** Use `argv[0]="tsc"`, never
  `"./node_modules/.bin/tsc"` — the bare-name discipline is structurally
  enforced by `_KERNEL_ALLOWLIST` and a path-traversal regression
  (`tests/unit/exec/test_allowlist_phase3.py:156-176`). Narrow admission lives
  caller-side in `env_extra["PATH"]` pointing at the repo-local `node_modules/.bin`.

- **The signal is plugin-local on purpose** — Phase 7's distroless plugin simply
  doesn't register it (ADR-0015 §Decision). Don't move the module to
  `src/codegenie/`.

- **Baseline is captured by the orchestrator, NOT by this collector.** The
  collector reads `.codegenie/typecheck/baseline-<repo-sha>.json` keyed by the
  pre-patch HEAD sha. If the file is missing, emit degraded-pass (`details=
  {"degraded_reason": "no_baseline", ...}`) — the orchestrator owns the
  fix-by-capturing. Validator picked "degraded-pass" over "refuse-with-error"
  to match Phase-3 baseline-bootstrap convention; if the operator review prefers
  refuse-with-error, surface before TDD-Red and update AC-8.

- **Baseline-keyed-on-repo-sha (`baseline-<repo-sha>.json`) means aggressive
  rebases leave stale baselines**; ADR-04-0015 §Tradeoffs names the recovery
  path (delete + re-run). Don't try to invalidate baselines cleverly — surfaces
  complexity disproportionate to value.

- **Plugin directory uses hyphens; Python `import` parser does not.** Per
  S7-01's hardening (`_validation/S7-01-vuln-node-npm-plugin-scaffold.md` line
  32), the loader uses the literal hyphenated slug. Use
  `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`
  in the registration fence; never a bare `import` statement.

- **`tsc --pretty false` summary line is one shape; zero errors emits no
  summary at all.** Parser must treat `returncode == 0 ⇒ ErrorCount(0)` as
  authoritative (don't pattern-match on stdout for the zero case — there's
  nothing to match). Non-zero returncode + no parseable summary → fail-loud as
  `UnparseableOutput` → degraded `TrustSignal` (AC-11). Don't introduce a
  TypeScript-output JSON parser dependency.

- **Future-sibling extract — Notes-for-implementer only.** Per ADR-0037,
  `typecheck.python` (Phase 7.5) and `typecheck.java` (later) are designed
  sibling signals. All share the shape `(invoke binary, parse error count,
  compare to baseline, emit TrustSignal)`. Rule of three says defer; the second
  sibling (Phase 7.5 Python) is the trigger to extract a common
  `TypecheckSignalKit(kind, binary, parse_fn, baseline_key_fn)` helper.
  **Do NOT extract on this first sibling** (Rule 2 — three similar lines is
  better than premature abstraction). First sibling ships the precedent flat;
  next sibling carries the extract.

- **Event-class names in the integration test (AC-16) must be verified against
  shipped `src/codegenie/plugins/events.py` before TDD-Red.** The four names
  the original story draft used (`SignalEvaluated`, `LeafReturned`,
  `GateBlocked`, `NpmTestStarted`) may not exist in the shipped event taxonomy.
  If any are new, scope the addition to **S6-08** (attempt-anchor emission —
  which owns event-taxonomy work) rather than letting S6-05 silently introduce
  four new event types.

- **The applicability question (`tsconfig.json` + `.ts` files) is deliberately
  deferred to S6-06** so this story stays single-purpose. If you find yourself
  adding `is_typescript_in_scope(repo)` checks here, stop — that's S6-06's
  surface.

- **The integration test's "event ordering proves the funnel" is the
  load-bearing assurance for ADR-0037's layered-analysis-funnel claim.** The
  cassette must be a *real* recording (S3-06's discipline) — fake cassettes
  here would invalidate the proof. The integration test is marked
  `@pytest.mark.skip` until S3-06 refreshes the cassette (AC-17).

- **ADR + design-doc amendments in the same PR (AC-13)** mirror the precedent
  S6-04 set (ADR-04-0015 §Decision stale "content-hashed path" framing) and
  S1-05 set (ADR-0003 stale framing): when shipped code diverges from the
  design narrative, the implementing PR carries the narrative amendments so
  the design docs stay coherent with the codebase.
