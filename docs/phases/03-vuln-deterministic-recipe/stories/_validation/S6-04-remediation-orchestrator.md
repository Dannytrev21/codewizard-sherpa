# Validation report — S6-04 (`RemediationOrchestrator` + 5-node subgraph + Phase-5 `_validate_stage6` seam + hardened `LocalGitOps`)

**Date:** 2026-05-19
**Validator:** phase-story-validator (inline four-lens analysis — same approach as the S6-03 validation report; the four critic lenses were applied directly against the loaded context after Stage 1 surfaced multiple block-tier Consistency conflicts that the four critics would all collapse onto).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/03-vuln-deterministic-recipe/stories/S6-04-remediation-orchestrator.md`](../S6-04-remediation-orchestrator.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct and well-traced:

- The 5-node `SubgraphNode` flow + the single-`match`-over-`NodeTransition` outer loop is exactly Gap 1's resolution (`phase-arch-design.md §Gap analysis §Gap 1`).
- `_validate_stage6` as the Phase-5 wrap-target (ADR-0001) + `EventLog.flush()` in `finally` (ADR-0005) + `npm install`/`npm test` inside `SubprocessJail` (ADR-0007) + tagged-union `RemediationOutcome` (ADR-0010) are all anchored correctly.
- The git hardening triple (`core.hooksPath=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/false`) per Edge case E14 is in place.

But the story was written *before* S1-03 and S1-04 landed (both GREEN, 2026-05-18) and drifted from shipped reality in multiple block-tier ways: the `Validated` variant's field set is wrong (`trust_outcome` instead of `passed`/`failing`); the variant **class names** are wrong (`NotApplicable` / `Failed` instead of `RemediationNotApplicable` / `RemediationFailed`); `StageOutcome` is named in signatures with no resolution on what type it actually is; the default `ApplyContext()` arg would raise `ValidationError` at import time because `ApplyContext` requires `workflow_id` and `capabilities`; `Stage6ValidateNode` hedges between two contradictory dispatches with a "clarify with reviewer" footnote that an executor cannot resolve; and the original outer-loop `match` test uses fragile `inspect.getsource(...).count("match ")` string-grep.

All in-place fixable. The Goal and the design pattern choices survive — only the specific shapes that conflict with shipped reality need correction.

## Context Brief (Stage 1)

### Story snapshot

- **Goal:** ship `RemediationOrchestrator` (`src/codegenie/transforms/orchestrator.py`) with the exact Phase-5 contract signatures, the 5 `SubgraphNode` concrete classes, the outer `match` loop, `_validate_stage6` as the wrap-target, `LocalGitOps.create_patch_branch` with the three git-hardening primitives, `GitHooksDisabledForRun` emission, and `EventLog.flush()` in `finally`.
- **Status at validation time:** `Ready` — never executed.

### Shipped reality (as of git HEAD `12be345`)

- `src/codegenie/transforms/outcomes.py` (S1-03, GREEN 2026-05-18):
  - `Validated(kind="validated", branch: BranchName, report_path: str, passed: bool, failing: list[SignalKind])` + `_passed_iff_no_failing` invariant.
  - `RequiresHumanReview(kind="requires_human_review", reason: HumanReviewReason, handoff_path: str | None)`.
  - **`RemediationNotApplicable`** (NOT `RemediationOutcome.NotApplicable`) `(kind="not_applicable", reason: NotApplicableReason)`.
  - **`RemediationFailed`** (NOT `RemediationOutcome.Failed`) `(kind="failed", error: RemediationError, partial_report_path: str | None)`.
  - `RemediationOutcome = Annotated[Validated | RequiresHumanReview | RemediationNotApplicable | RemediationFailed, Field(discriminator="kind")]`.
  - `Advance(state: dict[str, str | int | bool | float])` — pre-S6-03; S6-03 widens to `state: SubgraphState`.
  - `EscalationReason = Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]` — pre-S6-03; S6-03 widens to 7 members including `"filesystem_race"`, `"vuln_index_corrupted"`.
- `src/codegenie/transforms/apply_context.py` (S1-04, GREEN):
  - `ApplyContext` requires `workflow_id: WorkflowId` + `capabilities: CapabilityBundle` (no defaults). `ApplyContext()` raises `ValidationError`.
  - `prior_attempts: tuple[AttemptSummary, ...]` (NOT `list`).
- `src/codegenie/transforms/trust_scorer.py` (S6-02): **MISSING** at validation time. S6-02 ships `TrustScorer.score(signals) -> TrustOutcome`.
- `src/codegenie/plugins/events.py` (S6-01): **MISSING** at validation time.
- `src/codegenie/plugins/subgraph.py` (S6-03): **MISSING** at validation time. S6-03 ships `SubgraphNode` Protocol + `SubgraphState` + the widening of `Advance.state` + `EscalationReason`.

### Cross-phase contract (immutable inputs)

- ADR-0001 §Decision + §Consequences — Phase 5's `GateRunner` wraps `_validate_stage6` by name; the named seams (`RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `RemediationOutcome`, `TrustOutcome`) are re-exported from `codegenie.transforms`. S6-06's contract snapshot freezes the signatures verbatim.
- ADR-0005 §Consequences — `flush()` in `finally` is mandatory.
- ADR-0007 §Decision — 5-step `_validate_stage6` body: apply → `SubprocessJail.run(npm install, 180s)` → `SubprocessJail.run(npm test, 300s)` → 5 signals → `TrustScorer.score`.
- ADR-0010 §Decision (3) — `RemediationOutcome` is a discriminated union with 4 variants; every dispatch site uses `match` + `assert_never`.
- ADR-0010 Amendment 2026-05-18 — single canonical declaration site per union.
- `phase-arch-design.md §Gap analysis Gap 1` — `NodeTransition` outer-loop pattern.
- `phase-arch-design.md §Edge cases E14` — git hardening triple.

### Open ambiguities surfaced before critics

- **Q1 — what type is `StageOutcome`?** Story uses it in signatures with no resolution. Final-design line 549 says: "Calls `TrustScorer.score(...)` → `TrustOutcome`. **This is what Phase 5 wraps.**" ADR-0001's named-symbols list does NOT mention `StageOutcome` separately. S6-02 ships `TrustOutcome`. Resolution: `StageOutcome: TypeAlias = TrustOutcome`, declared at S6-02's canonical site, re-exported from `codegenie.transforms.__init__`. Single declaration site (ADR-0010 Amendment 2026-05-18).
- **Q2 — `Stage6ValidateNode` on `passed=False` — Advance or ShortCircuit?** Story hedged in AC text. Resolution: per arch §Control flow step 8 and §Scenarios C — `ShortCircuit(Validated(passed=False, failing=...))`. `WriteBranchNode` is skipped. Phase 5's `GateRunner` retries; Phase 3 returns immediately.
- **Q3 — orchestrator instance reuse?** Story claims "Stateless across runs: a single instance may execute `run(...)` for multiple workflows sequentially." But `event_log` is workflow-scoped at `__init__`. Resolution: orchestrator is bound to ONE workflow; CLI constructs a fresh instance per `codegenie remediate` invocation. AC rewritten.

All three resolved from precedent + shipped code; no user clarification needed.

## Findings

Severity legend: **block** (story unshippable without fix) · **harden** (in-place fix applied) · **nit** (small clarification).

### Consistency lens (highest priority)

#### C-F1 (block → fixed) — `RemediationOutcome` variant shapes diverge from shipped S1-03

- **What was wrong:** AC at original line 80 listed the variants as `Validated(branch, report_path, trust_outcome) | RequiresHumanReview(reason, handoff_path) | NotApplicable(reason) | Failed(error, partial_report_path)`. The shipped variants are `Validated(branch, report_path, passed, failing)` — NO `trust_outcome` field — and the class names are `RemediationNotApplicable` and `RemediationFailed` (NOT `NotApplicable` / `Failed`, and NOT `RemediationOutcome.NotApplicable` / `RemediationOutcome.Failed` as the original implementation outline implied). The integration-test AC at original line 88 asserts `outcome.trust_outcome.passed is True` — `AttributeError` at runtime because `Validated` has no `trust_outcome` field.
- **Source of truth:** `src/codegenie/transforms/outcomes.py:242-300` + S1-03's validation report C-F1 ("the right move is to keep the flat `passed: bool, failing: list[SignalKind]` denormalisation") + S1-03 Implementer notes line 402 ("`Validated.passed` + `Validated.failing` are the flat denormalization of arch's `TrustOutcome.passed` + `TrustOutcome.failing`").
- **Fix applied:** All AC text + Implementation outline + TDD plan + Notes updated to use the shipped variant shapes. New AC-21 lists the four variants verbatim. Integration-test AC-29 asserts `outcome.passed is True` and `outcome.failing == []`. Notes-for-implementer adds a paragraph (top of section) warning about the `RemediationOutcome.NotApplicable` attribute-path mistake.

#### C-F2 (block → fixed) — `StageOutcome` is named without resolution

- **What was wrong:** AC at original line 64 says `_validate_stage6(...) -> StageOutcome`. Implementation outline original line 111 says "Returns `StageOutcome` (a Pydantic model defined here or in S1-03; per ADR-0001 it's the typed return shape Phase 5 reads)." S1-03 did NOT define a `StageOutcome` class. `TrustScorer.score` (S6-02) returns `TrustOutcome`. Without resolution, the executor either (a) defines a new `StageOutcome` class breaking single-declaration discipline, (b) ships nothing and the contract snapshot fails, or (c) silently swaps to `TrustOutcome` and Phase 5's signature inspection breaks.
- **Source of truth:** Final-design.md line 549 ("Calls `TrustScorer.score(...)` → `TrustOutcome`. **This is what Phase 5 wraps.**") + ADR-0001 named-symbols list (`TrustOutcome` is named; `StageOutcome` is not).
- **Fix applied:** New AC-6 pins `StageOutcome: TypeAlias = TrustOutcome` declared at S6-02's canonical site (`src/codegenie/transforms/trust_scorer.py`) and re-exported from `codegenie.transforms.__init__`. Test: `from codegenie.transforms import StageOutcome, TrustOutcome; assert StageOutcome is TrustOutcome`. The Phase-5 contract snapshot reads the alias name; mypy resolves it to TrustOutcome so call-site narrowing works.

#### C-F3 (block → fixed) — `Stage6ValidateNode` hedges on `passed=False` dispatch

- **What was wrong:** Original implementation outline line 105: "on `passed=False` returns `Advance` (so `write_branch` still runs — but writing the branch is conditioned on `trust_outcome.passed`; OR per ADR-0007 returns `ShortCircuit(Validated(passed=False, ...))`; **clarify with reviewer; default: ShortCircuit Validated with passed=False**)." An executor cannot resolve this — the AC doesn't pin the contract.
- **Source of truth:** `phase-arch-design.md §Control flow` step 8 + §Scenarios C — on `passed=False`, Phase 3 alone returns the outcome; Phase 5's `GateRunner` retries.
- **Fix applied:** AC-11 (`passed=True` → `Advance` with `trust_outcome` in `state`) + AC-12 (`passed=False` → `ShortCircuit(Validated(passed=False, failing=...))` — `WriteBranchNode` is skipped). Implementation outline rewrites the `Stage6ValidateNode` step accordingly. Notes-for-implementer documents the decision as final, not "clarify with reviewer."

#### C-F4 (block → fixed) — `Validated` invariant compliance is unconstrained

- **What was wrong:** `Validated` enforces `passed iff len(failing) == 0` via `_passed_iff_no_failing` (`outcomes.py:256-260`). The story constructs `Validated(passed=False, failing=...)` in `Stage6ValidateNode` and `Validated(passed=True, failing=[])` on the happy path, but no AC pins the invariant. A wrong impl that constructs `Validated(passed=True, failing=[SignalKind("tests")])` (consistent with `passed=True` flow but with stale `failing`) raises `ValidationError` at runtime in ways that aren't covered by the story's signature-only tests.
- **Source of truth:** `outcomes.py:256-260` + S1-03 validation report C-Cv2.
- **Fix applied:** New AC-13 — every construction of `Validated` satisfies the invariant; both legal sides + both illegal sides are parametric-tested. `Stage6ValidateNode` AC-12 pins the map `Validated(passed=trust_outcome.passed, failing=list(trust_outcome.failing))`.

#### C-F5 (block → fixed) — `BranchName.parse` Err path is unhandled

- **What was wrong:** AC original line 79 said branch name is validated via `BranchName.parse(...)`. But there's no AC for what happens on `Err(parse_error)` — silent substitution? raise? `BranchName.parse` enforces `^[a-z0-9/_.-]+$`; a transform whose 8-hex prefix is `"BAD!ID"` (synthetic) or whose `CveId.lower()` contains an unexpected character violates the regex.
- **Source of truth:** S1-01 (`BranchName.parse`).
- **Fix applied:** New AC-19 — on `Err`, the workflow returns `RemediationFailed(error=RemediationError(error_id="branch_name.parse_error", ...))` — no silent default. Parametric test in `test_git_local_ops.py`.

#### C-F6 (harden → fixed) — `ApplyContext()` default arg raises `ValidationError`

- **What was wrong:** AC original line 63: `context: ApplyContext = ApplyContext()`. `ApplyContext` requires `workflow_id` and `capabilities` (`apply_context.py:138-141`). The default-arg evaluates at function-definition time → `ValidationError` at import time → `RemediationOrchestrator` cannot be loaded.
- **Source of truth:** `src/codegenie/transforms/apply_context.py:138-141`.
- **Fix applied:** New AC-4 switches the declared default from `ApplyContext()` to `None`; on `context is None` the orchestrator builds a fresh `ApplyContext(workflow_id=<ulid>, capabilities=CapabilityBundle.empty())` inside `run()`. The contract-snapshot test (S6-06) pins the **declared signature** as `context: ApplyContext | None = None` — that's the string the snapshot reads. The None-coalesce is internal.

#### C-F7 (harden → fixed) — `RemediationOutcome` re-export shape

- **What was wrong:** The story does not explicitly re-export `RemediationOrchestrator` from `transforms/__init__.py` (only mentions it in passing). ADR-0001 §Consequences mandates the re-export.
- **Fix applied:** New AC-2 pins the re-export. Implementation outline step 7 lands the edit.

#### C-F8 (harden → fixed) — stateless-across-runs vs per-workflow `EventLog`

- **What was wrong:** AC original line 82: "a single `RemediationOrchestrator` instance may execute `run(...)` for multiple workflows sequentially in the same process". `EventLog` (S6-01) is workflow-scoped at construction (`EventLog(root, workflow_id)`). If the orchestrator is reused, every workflow writes to the same `event_log` (wrong workflow_id), and `TrustScorer` (S6-02) filters `event_log.replay()` by `self._event_log.workflow_id` — also wrong.
- **Source of truth:** S6-02's `TrustScorer.score` reads `self._event_log.workflow_id` to filter `AdapterDegraded` events.
- **Fix applied:** New AC-25 pins the per-workflow lifecycle: the orchestrator is bound to one workflow because `event_log` is wired at `__init__`; reuse is undefined and not tested; CLI constructs a fresh instance per invocation. Notes-for-implementer documents this.

### Coverage lens

#### C-Cv1 (harden → fixed) — no AC for orchestrator's translation of uncaught exceptions

- **What was wrong:** The story says "failure isolation: every stage emits a typed event before raising" but doesn't pin the orchestrator's behaviour on the uncaught exception (does it re-raise? translate to `RemediationFailed`? leave the caller to handle?).
- **Fix applied:** New AC-24 pins the contract: uncaught exception inside `run()` is caught after the `finally` block flushes events, translated to `RemediationFailed(error=RemediationError(error_id="orchestrator.uncaught_exception", ...))`, and returned (not re-raised). The `flush_async_or_sync` selection is also pinned. Test `test_event_log_flushed_in_finally_even_when_node_raises` asserts both.

#### C-Cv2 (harden → fixed) — no AC for `_finalize` / `_escalate` contracts

- **What was wrong:** Implementation outline original lines 112-113 sketch `_finalize` and `_escalate` but no AC pins their contracts (what events emit, what they return).
- **Fix applied:** New AC-22 (`_finalize`: emits `WorkflowCompleted`, writes report via S5-05, returns outcome unchanged; total over all 4 variants) + AC-23 (`_escalate`: emits the matching spanning event, writes a partial report, returns `RemediationFailed` with `error_id=f"escalate.{reason}"`).

#### C-Cv3 (harden → fixed; covered in C-F8) — per-workflow lifecycle

Resolved by C-F8 above.

#### C-Cv4 (harden → fixed) — no AC for pure helper `_collect_stage6_signals`

- **What was wrong:** Original Refactor §line 224 mentions extracting `_collect_stage6_signals` as a clean-up step — not pinned as a Goal-level AC. An executor following the story strictly leaves it inline in `_validate_stage6`, losing the functional-core / imperative-shell discipline (CLAUDE.md).
- **Fix applied:** New AC-7a promotes the pure helper to a Goal-level AC with named test file (`test_collect_stage6_signals.py`).

#### C-Cv5 (harden → fixed) — no AC matrix for `JailedSubprocessResult` variants

- **What was wrong:** `JailedSubprocessResult` is `Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded` (5 variants). The story tests only the happy path (Completed exit 0). For `_validate_stage6` to be correct, the signal mapping for each variant must be pinned.
- **Fix applied:** New AC-7b lists the exact map per variant + uses `assert_never` on the wildcard arm. The pure-helper test (AC-7a) exhaustively parametrises over the 5×2 (variant × install/tests slot) matrix.

#### C-Cv6 (harden → fixed) — no AC for `git` ALLOWED_BINARIES + fence-test interaction

- **What was wrong:** Original AC line 77: "The git CLI must be already on `ALLOWED_BINARIES` (Phase 0 baseline); if not, S4-05's ADR-amendment covers it." But the executor doesn't know whether git is on the list currently, and the story doesn't pin the assertion. If `git` is missing, `make fence` fails silently in CI.
- **Fix applied:** New AC-17 explicitly: if absent, the story's PR adds `git` to `ALLOWED_BINARIES` via the Phase-2-style ADR convention; `make fence` clean is a bar AC. New AC-32 makes `make fence` clean a hard requirement.

#### C-Cv7 (harden → fixed; covered in C-Cv5) — `JailedSubprocessResult` variant handling

Resolved by C-Cv5.

#### C-Cv8 (harden → fixed) — no AC pins per-node test files

- **What was wrong:** Original Files-to-touch said "`tests/unit/transforms/nodes/test_*.py` — one per node, covering its three-transition matrix." But the per-node ACs were elided. A flexible executor might write one big test file instead.
- **Fix applied:** Files-to-touch rewritten with explicit per-node test file names + which ACs each covers. Per-node tests are now numbered (AC-11/12 for `test_stage6_validate_node.py`; AC-18/19/20 for `test_write_branch_node.py`; etc.).

#### C-Cv9 (harden → fixed) — no AC for the fence test that nodes don't import the orchestrator

- **What was wrong:** Original Notes did not include the circular-import-prevention fence. Without it, an executor doing the obvious thing (give `Stage6ValidateNode` a `self._orchestrator` handle) creates a circular import.
- **Fix applied:** New AC-9 + fence file `tests/unit/transforms/nodes/test_no_orchestrator_import.py` AST-scans for `RemediationOrchestrator` references under `nodes/`.

### Test-quality lens

#### T-Q1 (harden → fixed) — TDD plan has elided test bodies

- **What was wrong:** Original lines 171-179 listed 8 tests with bodies elided ("structure indicated"). An executor copy-paste sees this as `...` placeholder code. Several tests (`test_event_log_flushed_in_finally_even_on_exception`, `test_create_patch_branch_includes_git_hardening`, …) had no concrete fixture or assertion.
- **Fix applied:** TDD plan rewritten with fleshed-out per-variant outcome tests (AC-28 mapping), AST-walk outer-loop test (T-Q2), AC-9 import-fence test, AC-24 flush-in-finally test, AC-13 Validated-invariant regression test. Each test names its fixture (e.g., `orchestrator_factory`) which an implementer-side `conftest.py` pins.

#### T-Q2 (harden → fixed) — outer-loop `match` test is fragile string-grep

- **What was wrong:** Original test: `src = inspect.getsource(...); assert src.count("match ") == 1`. A `ruff format` change introducing a string literal `"match "` or a comment with the word `match` perturbs the count. A wrong impl that has `match` blocks inside helper methods on the orchestrator class also slips through.
- **Source of truth:** S1-03's `test_exhaustiveness.py` + S6-03's `test_subgraph_protocol.py` both use AST-walk.
- **Fix applied:** TDD plan replaces the count with `ast.parse(textwrap.dedent(src))` + `ast.walk` looking for exactly one `ast.Match` node with four case arms in order [`Advance`, `ShortCircuit`, `Escalate`, wildcard], + `assert_never` in the wildcard arm body. Mirrors the S6-03 approach.

#### T-Q3 (harden → fixed) — no mutation-thinking test for `_collect_stage6_signals`

- **What was wrong:** If the implementer accidentally flips `passed=True` to `passed=False` in the `_collect_stage6_signals` mapping for `Completed(exit_code=0)`, the happy-path test still passes (the test mocks the helper).
- **Fix applied:** AC-7a + AC-7b push the per-variant mapping into an exhaustive parametric test of the **pure** helper (`test_collect_stage6_signals.py`). The mapping is now constrained by explicit ACs, not by example.

#### T-Q4 (harden → fixed) — git hardening test mentions specifics

- **What was wrong:** TDD plan elided line: "patch run_external_cli; assert `-c core.hooksPath=/dev/null` + env vars."
- **Fix applied:** AC-15 spells out the parametric test (`tests/unit/transforms/test_git_local_ops.py::test_git_hardening_flags_present_per_invocation`) that patches `run_external_cli` and asserts the flag + both env entries are present for every git subcommand the impl issues.

#### T-Q5 (nit → fixed) — integration test path is hard-coded relative to CWD

- **What was wrong:** Original `Path("tests/fixtures/repos/express-cve-2024-21501")` is brittle when pytest runs from a non-repo-root CWD.
- **Fix applied:** Integration test uses `FIXTURE = Path("tests/fixtures/repos/express-cve-2024-21501")` at module scope + `@pytest.mark.skipif(not FIXTURE.exists(), reason="S8-01 lands the full fixture")` until S8-01 lands.

### Design-patterns lens

#### D-P1 (note → surfaced) — `Plugin.build_subgraph()` is NOT consumed by Phase 3

- **Observation:** Per the kernel pattern (CLAUDE.md "Extension by addition"), the cleanest design would be: `Plugin.build_subgraph(registry) -> list[SubgraphNode]`; the orchestrator iterates the plugin-provided list. But Phase 3 ships exactly one node sequence (the 5-node vuln-rem flow) — premature pluggability is the Rule 2 violation.
- **Decision:** Surface as Note, do not change. The 5 nodes are orchestrator-owned scaffolding in Phase 3. Phase 6 (LangGraph wrap) and Phase 7 (distroless plugin with a different sequence) are the real consumers of `Plugin.build_subgraph()`. Notes paragraph documents this.

#### D-P2 (harden → fixed) — circular import via `Stage6ValidateNode` → orchestrator

- **What was wrong:** Original implementation outline line 105: "`Stage6ValidateNode`: calls `self._orchestrator._validate_stage6(transform, ctx)`." If the node imports `RemediationOrchestrator` (to type-annotate `self._orchestrator`), and the orchestrator imports `Stage6ValidateNode` (to instantiate the 5 nodes), the module-import graph cycles.
- **Source of truth:** Codebase precedents — `BundleBuilder.__init__(cache_dir)` (constructor injection); `TrustScorer.__init__(event_log)` (constructor injection). Dependency Inversion + Strategy pattern.
- **Fix applied:** New AC-9 pins constructor-injection for every node. `Stage6ValidateNode(validate_fn: Callable[[Transform, ApplyContext], Awaitable[StageOutcome]])` accepts the orchestrator's bound `_validate_stage6` method as a callable. Wire-up happens in `RemediationOrchestrator.__init__`. Fence test (`tests/unit/transforms/nodes/test_no_orchestrator_import.py`) AST-scans `nodes/*.py` for `RemediationOrchestrator` references and fails loud. Notes-for-implementer documents the decision and the precedent.

#### D-P3 (harden → fixed; covered in C-Cv4) — functional core / imperative shell

Resolved by C-Cv4.

#### D-P4 (note → surfaced) — `LocalGitOps` Protocol-vs-class

- **Observation:** Phase 11's PR-creation + Sigstore-signing flow will want a `GitOps` Protocol so `LocalGitOps` and `GitHubGitOps` can substitute. Phase 3 ships ONE implementation.
- **Decision:** Surface as Note, do not change. Plain class in Phase 3; Protocol extraction is Phase 11's call. Rule 2.

#### D-P5 (note → surfaced) — composition over subclassing for Phase 4 / 5

- **Observation:** A reviewer / future contributor may want `LLMRemediationOrchestrator(RemediationOrchestrator)` for Phase 4. Wrong — Phase 5's wrap-the-method-by-name contract works on a single concrete class; subclassing introduces MRO and override hazards.
- **Decision:** Surface as Note. Phase 4 wraps via fallback recipe registration; Phase 5 wraps via `GateRunner` composition.

#### D-P6 (harden → fixed) — `assert_never` exhaustiveness arm

- **What was wrong:** Original AC line 75 had `case _: assert_never(transition)` — but `transition` was the loop variable, not the matched value. Per S1-03 / S6-03 convention, the wildcard should bind the matched value: `case _ as t: assert_never(t)`.
- **Fix applied:** AC-10 text updated; AST-walk test asserts `assert_never` is present in the wildcard arm body (any binding form is accepted, but the call must be present).

#### D-P7 (covered in AC-24) — `EventLog.flush()` in `finally`

Resolved by AC-24.

#### D-P8 (harden → fixed) — `SubprocessJail` platform selection is hidden

- **What was wrong:** Original AC line 62 said `sandbox=None` "defaults to the platform adapter (`BwrapAdapter` on Linux, `SandboxExecAdapter` on macOS)" without naming the seam Phase 5 reuses to swap.
- **Fix applied:** AC-3 pins the module-level `default_subprocess_jail() -> SubprocessJail` factory. Phase 5 reuses by monkey-patching or by passing `sandbox=FirecrackerAdapter()`. Notes-for-implementer documents.

#### D-P9 (covered in C-F2) — `StageOutcome` alias

Resolved by C-F2.

## Edits applied

All edits in-place. The story file's `Validation notes` block records the changes. Summary:

1. **Status** flipped to `HARDENED` with the `_validation/S6-04-remediation-orchestrator.md` reference.
2. **Depends on** expanded to the full chain (was: S6-02, S6-03, S5-05 only).
3. **ADRs honored** extended with ADR-0010 Amendment 2026-05-18 (single declaration site) and Amendment 2026-05-19 (S6-03's widening).
4. **Validation notes** block (13 numbered points) added after the header.
5. **Acceptance criteria** rewritten and expanded from 18 to 32 numbered ACs. Grouped under Module surface / Phase-5 contract / Stage-6 body / Subgraph / Stage6Validate / LocalGitOps / Branch-name / RemediationOutcome / Durability+lifecycle / Failure isolation / Per-variant tests / Bar.
6. **Implementation outline** rewritten step-by-step with concrete signatures (e.g., `Stage6ValidateNode(validate_fn, event_log)`); the `Stage6ValidateNode` hedge replaced with the decided contract.
7. **TDD plan red test** rewritten: imports corrected, AST-walk outer-loop test, fleshed-out per-variant tests, AC-9 import-fence test, AC-24 flush-in-finally test, AC-13 invariant regression test.
8. **Files to touch** rewritten with explicit per-node test file names + which ACs each covers.
9. **Notes for the implementer** extended with 7 new paragraphs (C-F1 variant-class names, C-F1 Validated.passed/failing, C-F2 StageOutcome alias, C-F3 Stage6Validate decision, D-P2 DI fence, D-P3 pure helper, D-P4 LocalGitOps plain class, D-P5 composition over inheritance, D-P1 Plugin.build_subgraph deferred, D-P8 factory seam, AC-10 AST-walk rationale, AC-25 per-workflow lifecycle, AC-24 no-silent-catches).

## Verdict

**HARDENED.** Ready for `phase-story-executor` once S6-01, S6-02, S6-03, S5-05, S5-04, S5-02, S5-01 are all GREEN on the executor's branch. The block-tier closures (C-F1..C-F8) reconcile the story with shipped S1-03/S1-04 reality + S6-02/S6-03 contracts; the design-patterns closures (D-P2 + D-P3) make the structure easy to maintain and extend by addition; the test-quality closures (T-Q1..T-Q5) ensure a wrong implementation fails an assertion verbatim rather than slipping through a thin test.
