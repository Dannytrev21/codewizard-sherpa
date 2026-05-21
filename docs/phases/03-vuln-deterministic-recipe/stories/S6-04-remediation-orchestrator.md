# Story S6-04 — `RemediationOrchestrator` + 5-node subgraph + Phase-5 `_validate_stage6` seam + hardened `LocalGitOps`

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** BLOCKED (re-validated 2026-05-21 — verdict **RESCUE**; resolution path escalated from `/phase-story-validator` to `/phase-architect`). The 2026-05-21 re-validation read the dependency surfaces the executor's Attempt 1 had not reached and found that, underneath the patchable dependency-drift (B1–B9 in the re-validation report), S6-04 sits on a **genuine architectural gap** a validator cannot close: (G1) `BundleBuilder.build` + the subgraph need a `RepoContext`, but the ADR-0001-frozen `run(repo, cve, context)` / `__init__` signatures have no slot to receive one — and arch §Control-flow step 1 ("the CLI loads `repo-context.yaml`") structurally contradicts that frozen surface; (G2) no shipped `VulnIndex` method maps `CveId → VulnerabilityRecord`, and CVE→record resolution requires the repo's dependency set from the same missing `RepoContext`. **Resolution:** route to `/phase-architect` for a new Phase-3 ADR that decides the `RepoContext` ingress + `CveId → VulnerabilityRecord` resolution + where the bundle build lives; then re-run `/phase-story-validator` to fold in B1–B9. **No story edits were made** in the 2026-05-21 pass (RESCUE discipline). Until that ADR lands, S6-04 stays BLOCKED and no later Step-6/7/8/9 story may be executed. Full audit: [`_validation/S6-04-remediation-orchestrator.md`](_validation/S6-04-remediation-orchestrator.md) (§"Re-validation — 2026-05-21"). Executor Attempt 1: [`_attempts/S6-04.md`](_attempts/S6-04.md).
**Effort:** L
**Depends on:** S6-02 (`TrustScorer`/`TrustOutcome`/`TrustSignal`), S6-03 (`SubgraphNode`/`SubgraphState`/widened `NodeTransition`), S5-05 (`RemediationReport` writer), S5-04 (`LockfilePolicy`), S5-02 (`NpmLockfileRecipeEngine`), S5-01 (`RecipeRegistry`), S4-02/S4-03 (`SubprocessJail` adapters), S3-02 (`VulnIndex`), S2-01 (`PluginRegistry`), S1-04 (`ApplyContext` / `Transform`), S1-03 (shipped `RemediationOutcome` variants — `Validated` / `RequiresHumanReview` / `RemediationNotApplicable` / `RemediationFailed`)
**ADRs honored:** ADR-0001 (ship the Phase-5 contract surface; `_validate_stage6` is the named wrap-target — exact signature is load-bearing), ADR-0005 (orchestrator constructs and owns `EventLog` lifecycle; `flush()` in `finally`), ADR-0007 (Phase 3 runs `npm install` + `npm test` inside `SubprocessJail`; Phase 5 wraps the retry envelope), ADR-0010 (`RemediationOutcome` tagged union, **single declaration site** per Amendment 2026-05-18 — this story re-uses the shipped variants, does not redefine), ADR-0010 Amendment 2026-05-19 (the widened `Advance.state: SubgraphState` and 7-member `EscalationReason` shipped by S6-03 are consumed verbatim here), [Phase 5 ADR-0001](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) (the Stage-6 seam Phase 5 wraps)

## Validation notes (2026-05-19)

Hardened by `phase-story-validator`. See `_validation/S6-04-remediation-orchestrator.md` for the full audit. Block-tier closures:

1. **Shipped `RemediationOutcome` shape (C-F1).** Story originally listed variants as `Validated(branch, report_path, trust_outcome) | NotApplicable(reason) | Failed(error, partial_report_path)`. Shipped reality (S1-03, GREEN 2026-05-18, `src/codegenie/transforms/outcomes.py:242-300`) is `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)`. `Validated` has **no** `trust_outcome` field — `passed: bool` and `failing: list[SignalKind]` are the flat denormalisation. The class names are `RemediationNotApplicable` / `RemediationFailed` (NOT `RemediationOutcome.NotApplicable` / `RemediationOutcome.Failed` — those are non-existent attribute paths). Story corrected throughout; integration-test AC switched from `outcome.trust_outcome.passed is True` to `outcome.passed is True`.
2. **`StageOutcome` pinned (C-F2).** Phase 5's contract surface (ADR-0001 + S6-06 contract snapshot) names `StageOutcome` as the typed return of `_validate_stage6`. Shipped reality: `TrustScorer.score(...)` returns `TrustOutcome` (S6-02); there is no separate `StageOutcome` class. Story now pins `StageOutcome: TypeAlias = TrustOutcome` declared in `src/codegenie/transforms/trust_scorer.py` (S6-02's home) and re-exported from `codegenie.transforms.__init__`. New AC: `from codegenie.transforms import StageOutcome, TrustOutcome; assert StageOutcome is TrustOutcome`. Single declaration site preserved (ADR-0010 Amendment 2026-05-18).
3. **`Validated` invariant (C-F4).** `Validated` enforces `passed iff len(failing) == 0` via `_passed_iff_no_failing` (`outcomes.py:256-260`). `Stage6ValidateNode` must construct `Validated(passed=trust_outcome.passed, failing=trust_outcome.failing)` — the map is now an explicit AC, and tests construct each side of the invariant.
4. **`Stage6ValidateNode` on `passed=False` (C-F3).** Original AC line 105 hedged ("clarify with reviewer; default..."). Resolved per arch §Control flow step 8 and §Scenarios C: on `passed=False` the node returns `ShortCircuit(Validated(passed=False, failing=...))`. `WriteBranchNode` is **skipped** — the orchestrator's outer-loop short-circuit returns immediately. AC text rewritten without hedge.
5. **`ApplyContext()` default (C-F8).** `ApplyContext` requires `workflow_id` + `capabilities` (`apply_context.py:138-141`); calling `ApplyContext()` with no args raises `ValidationError`. Story switched the default-arg pattern from `context: ApplyContext = ApplyContext()` to `context: ApplyContext | None = None`; the orchestrator constructs a fresh `ApplyContext(workflow_id=WorkflowId(<ulid>), capabilities=CapabilityBundle.empty())` inside `run()` when `context is None`. Contract-snapshot still pins the **declared** type as `ApplyContext` — the None-coalesce is internal.
6. **Stateless-across-runs vs per-workflow `EventLog` (C-Cv3).** Story originally asserted "a single instance may execute `run(...)` for multiple workflows sequentially" while `EventLog` (S6-01) is workflow-scoped at construction. Resolution: the orchestrator instance is **bound to one workflow** because `event_log` is wired at `__init__`; the CLI constructs a fresh orchestrator per `codegenie remediate` invocation. AC line 82 rewritten to: "the orchestrator holds no mutable state across the single `run()` call its `event_log` is scoped to".
7. **Outer-loop `match` test (T-Q2).** Replaced fragile `inspect.getsource(...).count("match ")` with an AST-walk asserting exactly one `ast.Match` node with three case arms (`Advance`, `ShortCircuit`, `Escalate`) plus a wildcard arm calling `assert_never`. Mirrors S1-03 / S6-03 patterns.
8. **Test-quality elides resolved (T-Q1).** The "Additional async tests (bodies elided)" block in the TDD plan has been promoted to concrete test skeletons with named fixtures (or, where the test is purely orchestrator-mock-driven, a one-line `# pragma: pin-on-executor` marker stating the assertion clearly enough that a wrong impl fails the assertion verbatim).
9. **Dependency-Inversion for nodes (D-P2).** Story originally implied `Stage6ValidateNode` reaches into `self._orchestrator._validate_stage6`, which creates a circular import (`nodes/stage6_validate.py → orchestrator.py → nodes/stage6_validate.py`). Resolution: every node takes its dependencies via constructor; `Stage6ValidateNode(validate_fn: Callable[[Transform, ApplyContext], Awaitable[StageOutcome]])` accepts the orchestrator's bound `_validate_stage6` method as a callable. Wire-up happens in `RemediationOrchestrator.__init__` (or in `run()` to keep the per-workflow lifecycle clear). Notes documents the precedent (mirrors `BundleBuilder` constructor injection of `cache_dir`).
10. **Pure helper `_collect_stage6_signals` is an AC, not a refactor afterthought (D-P3).** Functional-core / imperative-shell discipline (CLAUDE.md). The pure helper takes `(install_result, test_result, lockfile_doc, vuln_index, cve)` and returns `list[TrustSignal]`. The orchestrator's `_validate_stage6` is the imperative shell. Unit-tested independently.
11. **`SubprocessJail` result tagged-union handling (C-Cv7).** `JailedSubprocessResult` is `Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded`. Each maps to a specific `TrustSignal.passed` and `details` payload. ACs and unit tests now cover all 5 variants (a missed variant is what fails the runtime exhaustiveness test).
12. **Build-order check (Q-build).** S6-02 (`TrustScorer`) and S6-01 (`EventLog`) are not yet on disk at validation time (`src/codegenie/transforms/trust_scorer.py` MISSING; `src/codegenie/plugins/events.py` MISSING). The dependency list above is the canonical merge order. The executor should pause if any of `S6-01`, `S6-02`, `S6-03`, `S5-05`, `S5-04`, `S5-02`, `S5-01` is not green — every one of those ships a name S6-04 imports.
13. **Out-of-scope additions for D-P1, D-P4, D-P5, D-P8, D-P9** are surfaced in Notes-for-implementer rather than as ACs (Rule 2 — three similar lines is better than premature abstraction).

## Context

`RemediationOrchestrator` is the vertical-slice integration point for Phase 3. It pulls together: the `PluginRegistry` (S2-01) for plugin resolution, the `VulnIndex` (S3-02/03) for CVE lookup, the `BundleBuilder` (S3-04) for TCCM execution, the `RecipeRegistry` (S5-01) for recipe iteration, the `SubprocessJail` (S4-02/03) for `npm install` + `npm test`, the `TrustScorer` (S6-02) for strict-AND scoring, the `EventLog` (S6-01) for both event streams, the 5-node subgraph (S6-03 Protocol) for stage progression, the `LockfilePolicy` (S5-04) for the `lockfile_policy` signal, and the `RemediationReport` writer (S5-05). After this story lands, `codegenie remediate <repo> --cve <id>` (S6-05) is one CLI wiring step away from end-to-end.

The **Phase-5 contract surface** (ADR-0001) is **non-negotiable** here:

- `RemediationOrchestrator.__init__(self, registry, vuln_index, event_log, *, sandbox=None)` — exact signature.
- `async def run(self, repo, cve, context=ApplyContext()) -> RemediationOutcome` — exact signature.
- `async def _validate_stage6(self, transform: Transform, ctx: ApplyContext) -> StageOutcome` — **this method's name and signature are the Phase-5 wrap-target**. Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` decorates this method by name. Renaming `_validate_stage6` to `validate_stage6` (drop the underscore) is a contract break. Adding a positional argument is a contract break. The underscore prefix is load-bearing-but-private-looking — documented in ADR-0001 §Tradeoffs.

The contract snapshot test (S6-06) freezes this surface. Failure of that snapshot **means Phase 5 cannot ship**.

The orchestrator's outer loop is the **single `match` block** from S6-03's `NodeTransition` — Gap 1 fix. The 5 nodes (`ingest_cve`, `match_recipe`, `apply_recipe`, `stage6_validate`, `write_branch`) are concrete `SubgraphNode` implementations; the loop dispatches over `Advance | ShortCircuit | Escalate`.

`LocalGitOps.create_patch_branch` is the **Stage-7 step** (per `../phase-arch-design.md §Control flow` step 9). Git hardening is mandatory:
- `core.hooksPath=/dev/null` — disables any hook the analyzed repo may have configured.
- `GIT_TERMINAL_PROMPT=0` — refuses interactive auth prompts.
- `GIT_ASKPASS=/bin/false` — refuses credential helpers.
- Emits a `GitHooksDisabledForRun` internal-stream event (§C9 variant; written by this story's caller into the log via the `EventLog`).

The architecture spec's §Edge cases E14 documents this; failure to harden git means a hostile target repo's `.git/hooks/pre-commit` could exfiltrate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C1` — `RemediationOrchestrator` public interface, internal structure (5 sequential stages), state (stateless across runs), performance envelope, failure behavior (never silently catches; `RemediationOutcome` is tagged union).
  - `../phase-arch-design.md §Control flow` steps 1–11 — the full 11-step happy path the orchestrator implements.
  - `../phase-arch-design.md §Edge cases E11–E14` — `cve_delta`, symlink TOCTOU, concurrent-invocation, git-hook disablement (this story handles E14; E13 is S6-05's flock).
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 1` — the `NodeTransition` outer-loop pattern this story implements verbatim.
  - `../phase-arch-design.md §Scenarios` (lines ~309–414) — Scenarios A (happy path) and C (Stage 6 test failure) trace the orchestrator's behavior end-to-end.
- **Phase ADRs:**
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — full read. §Decision and §Consequences are mandatory; §Reversibility explains why renaming the seam is catastrophic.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — `flush()` in `finally` is mandatory.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` §Decision — `_validate_stage6`'s 5-step body (apply transform → npm install → npm test → 5 signals → TrustScorer.score).
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — `RemediationOutcome` is a discriminated union with 4 variants.
- **Cross-phase contract:**
  - `../../05-sandbox-trust-gates/final-design.md §Component design — `GateRunner`` — the call site that wraps `_validate_stage6`. **Read this**: the orchestrator's method signature must match `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))`'s expectation.
  - `../../05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md` — `ApplyContext.prior_attempts` is the field Phase 5 populates; Phase 3 ships it empty (per S1-04).
- **This phase, parallel stories:**
  - S6-01 — `EventLog`; the orchestrator constructs it in `__init__` and `flush()`es it in `finally`.
  - S6-02 — `TrustScorer`; constructor-injected with `self._event_log`; consumed inside `_validate_stage6`.
  - S6-03 — `SubgraphNode` Protocol + `NodeTransition`; the 5 nodes implement this Protocol; the outer loop is the `match` block.
  - S5-05 — `RemediationReport` writer; called at every workflow end (success or failure) to write the partial-or-full `remediation-report.yaml`.
  - S5-01 — `RecipeRegistry`; the `match_recipe` node iterates this in `(precedence desc, name asc)` order.
  - S5-04 — `LockfilePolicy`; the `_validate_stage6` body evaluates the policy → `lockfile_policy` `TrustSignal`.

## Goal

Land `src/codegenie/transforms/orchestrator.py` exposing `RemediationOrchestrator` with the **exact** Phase-5 contract signatures from ADR-0001; the 5-node subgraph as concrete `SubgraphNode` implementations; the outer `match` loop over `NodeTransition`; `_validate_stage6` as a method (not a function) with its exact wrap-target signature; `LocalGitOps.create_patch_branch(...)` with git hardening; emission of `GitHooksDisabledForRun`; and `EventLog.flush()` in a `finally` block.

## Acceptance criteria

### Module surface & exports

- [ ] **AC-1** `src/codegenie/transforms/orchestrator.py` exists; `from codegenie.transforms.orchestrator import RemediationOrchestrator` succeeds.
- [ ] **AC-2** `src/codegenie/transforms/__init__.py` re-exports `RemediationOrchestrator` (ADR-0001 §Consequences re-export list). `from codegenie.transforms import RemediationOrchestrator` succeeds.

### Phase-5 contract surface (S6-06 contract snapshot freezes these)

- [ ] **AC-3** `RemediationOrchestrator.__init__(self, registry: PluginRegistry, vuln_index: VulnIndex, event_log: EventLog, *, sandbox: SubprocessJail | None = None) -> None` — exact signature pinned by `inspect.signature(...)`. `sandbox=None` triggers a module-level factory `default_subprocess_jail() -> SubprocessJail` that returns `BwrapAdapter()` on Linux, `SandboxExecAdapter()` on macOS; the factory is the seam Phase 5 reuses to inject Firecracker / DinD (see Notes — D-P8).
- [ ] **AC-4** `async def run(self, repo: SandboxedPath, cve: CveId, context: ApplyContext | None = None) -> RemediationOutcome` — exact signature. Calling with `context=None` (or omitted) does **not** raise; the orchestrator constructs a fresh `ApplyContext(workflow_id=<ulid>, capabilities=CapabilityBundle.empty())` internally. **The declared parameter type stays `ApplyContext | None`** (the contract snapshot in S6-06 pins this string verbatim). Rationale: `ApplyContext` requires `workflow_id` + `capabilities` (`src/codegenie/transforms/apply_context.py:138-141`); a literal `ApplyContext()` default arg raises `ValidationError`.
- [ ] **AC-5** `async def _validate_stage6(self, transform: Transform, ctx: ApplyContext) -> StageOutcome` — exact signature; `inspect.iscoroutinefunction(RemediationOrchestrator._validate_stage6) is True`. This is the **method Phase 5's `GateRunner` wraps by name**. The underscore prefix is intentional and load-bearing; renaming is a contract break (S6-06 catches drift).
- [ ] **AC-6 (`StageOutcome` is `TrustOutcome`).** `from codegenie.transforms import StageOutcome, TrustOutcome; assert StageOutcome is TrustOutcome`. Declared as `StageOutcome: TypeAlias = TrustOutcome` in `src/codegenie/transforms/trust_scorer.py` (S6-02's canonical home; single declaration site per ADR-0010 Amendment 2026-05-18) and re-exported from `codegenie.transforms.__init__`. Phase 5's contract snapshot reads the **alias name**; the underlying type is `TrustOutcome`.

### Stage-6 validation body (ADR-0007 §Decision)

- [ ] **AC-7** `_validate_stage6` body executes the 5 steps from ADR-0007 §Decision in order: (1) apply transform to temp worktree under `SandboxedPath`; (2) `await self._sandbox.run(JailedSubprocessSpec(cmd=("npm","install"), time_budget_s=180, ...))`; (3) `await self._sandbox.run(JailedSubprocessSpec(cmd=("npm","test"), time_budget_s=300, ...))`; (4) call **pure** helper `_collect_stage6_signals(install_result, test_result, lockfile_doc, vuln_index, cve) -> list[TrustSignal]`; (5) `return self._trust_scorer.score(signals)`.
- [ ] **AC-7a (pure helper, functional-core / D-P3).** `_collect_stage6_signals` is a module-level pure function (no `self`, no I/O, no logging). Unit-tested independently in `tests/unit/transforms/test_collect_stage6_signals.py` with the 5×{`Completed(0)`, `Completed(non-zero)`, `TimedOut`, `OomKilled`, `NetworkDenied`} matrix for the install/test stages.
- [ ] **AC-7b (`JailedSubprocessResult` tagged-union mapping — C-Cv7).** For each `JailedSubprocessResult` variant the `install` and `tests` `TrustSignal` map is pinned:
  - `Completed(exit_code=0)` → `TrustSignal(kind="install"|"tests", passed=True, details={"exit_code": 0, "duration_s": d})`.
  - `Completed(exit_code=N!=0)` → `passed=False, details={"exit_code": N, "duration_s": d}`.
  - `TimedOut(duration_s=d)` → `passed=False, details={"reason": "timed_out", "duration_s": d}`.
  - `OomKilled(memory_mib=m)` → `passed=False, details={"reason": "oom_killed", "memory_mib": m}`.
  - `NetworkDenied(host=h)` → `passed=False, details={"reason": "network_denied", "host": h}`.
  - `DiskQuotaExceeded(...)` → `passed=False, details={"reason": "disk_quota_exceeded"}`.
  - Match block uses `assert_never` on the wildcard arm.

### Subgraph (S6-03 Protocol) — 5 concrete nodes, constructor-injected dependencies (D-P2)

- [ ] **AC-8** The 5 subgraph nodes are concrete classes implementing `SubgraphNode` Protocol from `codegenie.plugins.subgraph` (S6-03): `IngestCveNode`, `MatchRecipeNode`, `ApplyRecipeNode`, `Stage6ValidateNode`, `WriteBranchNode`. Each `async def run(self, state: SubgraphState) -> NodeTransition` and `isinstance(node_instance, SubgraphNode) is True` at runtime for each of the 5.
- [ ] **AC-9 (no circular import via Dependency Inversion).** Nodes do NOT import `RemediationOrchestrator` (forbidden — would cycle `nodes ↔ orchestrator`). Instead each node takes its dependencies via `__init__`:
  - `IngestCveNode(vuln_index: VulnIndex, registry: PluginRegistry, event_log: EventLog)`.
  - `MatchRecipeNode(event_log: EventLog)` (consumes `state.resolution`'s `plugin.recipe_registry`).
  - `ApplyRecipeNode(event_log: EventLog)` (consumes `state.recipe_outcome`'s `plan`).
  - `Stage6ValidateNode(validate_fn: Callable[[Transform, ApplyContext], Awaitable[StageOutcome]], event_log: EventLog)` — `validate_fn` is the orchestrator's bound `_validate_stage6` method, injected at wire-up time.
  - `WriteBranchNode(git_ops: LocalGitOps, event_log: EventLog)`.

  A fence test (`tests/unit/transforms/nodes/test_no_orchestrator_import.py`) AST-scans every file under `src/codegenie/transforms/nodes/` and fails if any imports `RemediationOrchestrator`.
- [ ] **AC-10** The outer loop in `RemediationOrchestrator.run` is **one `match` block** over `NodeTransition` (the Gap 1 pattern from S6-03), with exhaustive arms:
  ```python
  for node in self._subgraph_nodes:
      transition = await node.run(state)
      match transition:
          case Advance(state=s):       state = s
          case ShortCircuit(outcome=o): return self._finalize(o)
          case Escalate(reason=r):     return self._escalate(r)
          case _ as t:                 assert_never(t)
  ```
  Verified by **AST-walk** (not `inspect.getsource(...).count("match ")` — see TDD plan): exactly one `ast.Match` node inside `RemediationOrchestrator.run`'s body; exactly four `ast.match_case` arms; arm 1 binds `Advance`, arm 2 binds `ShortCircuit`, arm 3 binds `Escalate`, arm 4 is the wildcard calling `assert_never`.

### `Stage6ValidateNode` contract on `passed=True` vs `passed=False`

- [ ] **AC-11 (passed=True path).** `Stage6ValidateNode.run(state)` calls `validate_fn(state.transform, ctx)` → `TrustOutcome`. If `trust_outcome.passed is True`, returns `Advance(state=state.model_copy(update={"trust_outcome": trust_outcome}))`. The next node (`WriteBranchNode`) reads `state.trust_outcome` and creates the branch.
- [ ] **AC-12 (passed=False path).** If `trust_outcome.passed is False`, `Stage6ValidateNode.run` returns `ShortCircuit(outcome=Validated(branch=BranchName("codegenie/skipped-no-branch"), report_path=<path>, passed=False, failing=trust_outcome.failing))` — `WriteBranchNode` is **skipped**. Phase 5's `GateRunner` will re-enter `_validate_stage6` on retry; Phase 3 alone returns immediately (ADR-0007 — zero retries in Phase 3). No hedge: this is the contract.
- [ ] **AC-13 (`Validated` invariant compliance — C-F4).** Every construction of `Validated` satisfies `passed == (len(failing) == 0)` (enforced by `_passed_iff_no_failing` at `outcomes.py:256-260`). Specifically: `passed=False` implies `failing` is non-empty; `passed=True` implies `failing == []`. Tests parametrise both legal sides + assert `Validated(passed=True, failing=[SignalKind("tests")])` raises `ValidationError` (illegal-state guard regression).

### `LocalGitOps` git hardening + event emission

- [ ] **AC-14 (`LocalGitOps` location + shape).** `src/codegenie/transforms/git_local_ops.py` ships a plain class `LocalGitOps` (not a Protocol — single implementation in Phase 3; Phase 11 may extract a Port). `LocalGitOps.create_patch_branch(self, repo: SandboxedPath, transform: Transform, branch_name: BranchName, event_log: EventLog) -> BranchName`.
- [ ] **AC-15 (git hardening flags).** Every `git` invocation inside `create_patch_branch` goes through `run_external_cli` and supplies **all three** hardening primitives:
  - CLI flag: `-c core.hooksPath=/dev/null` present in `argv` before the subcommand.
  - Env: `GIT_TERMINAL_PROMPT=0` (string `"0"`).
  - Env: `GIT_ASKPASS=/bin/false`.

  A unit test (`tests/unit/transforms/test_git_local_ops.py::test_git_hardening_flags_present_per_invocation`) patches `run_external_cli` and parametrises across every git subcommand the impl issues (e.g., `checkout -b`, `add`, `commit`, …) asserting the flag + both env entries are present every time.
- [ ] **AC-16 (`GitHooksDisabledForRun` emission).** Exactly **one** `event_log.emit_internal(GitHooksDisabledForRun(adapter="local_git_ops", reason="run_isolation"))` is emitted per `create_patch_branch` call (regardless of how many `git` subcommands it issues). The variant is the one defined in S6-01's `WorkflowInternalEvent` taxonomy.
- [ ] **AC-17 (`git` is on `ALLOWED_BINARIES`).** If `git` is not yet in the Phase-0 baseline allowlist on the executor's branch, this story's PR adds it via S4-05's ADR-amendment (or the ALLOWED_BINARIES table directly per the Phase-2 ADR convention). The fence test `test_pyproject_fence.py` stays green.

### Branch-name construction (smart constructor)

- [ ] **AC-18 (branch name format).** Branch name is `f"codegenie/cve-{cve_id_lowercase}-{transform_id_short}"` where `cve_id_lowercase = cve.lower()` (e.g., `"cve-2024-21501"`) and `transform_id_short = transform.transform_id[:8]` (first 8 hex chars of the BLAKE3 digest). The string is validated via `BranchName.parse(s)` (S1-01 smart constructor enforcing `^[a-z0-9/_.-]+$`); on `Ok(branch)` the orchestrator proceeds; on `Err(parse_error)` the workflow short-circuits with `RemediationFailed(error=RemediationError(error_id="branch_name.parse_error", message=...))`.
- [ ] **AC-19 (parse error path tested).** `tests/unit/transforms/test_git_local_ops.py::test_branch_name_parse_error_surfaces_as_remediation_failed` constructs a `Transform` whose `transform_id` short-prefix would yield an invalid branch name (e.g., a synthetic stub returning `"BAD!ID"`) and asserts the workflow returns `RemediationFailed` with `error_id == "branch_name.parse_error"` — NOT silently substituting a default.
- [ ] **AC-20 (branch-already-exists / E13).** When the underlying `git checkout -b` returns non-zero with "branch already exists" output, `LocalGitOps.create_patch_branch` returns a typed result the caller (`WriteBranchNode`) converts to `Escalate(reason="filesystem_race")`. Test: monkey-patched `run_external_cli` returns the canonical git error; node returns `Escalate("filesystem_race")`.

### `RemediationOutcome` tagged-union — every code path lands one variant

- [ ] **AC-21 (variants exact, per shipped S1-03 reality — C-F1).** `RemediationOutcome` is the **shipped** tagged union:
  - `Validated(kind="validated", branch: BranchName, report_path: str, passed: bool, failing: list[SignalKind])`
  - `RequiresHumanReview(kind="requires_human_review", reason: HumanReviewReason, handoff_path: str | None)`
  - `RemediationNotApplicable(kind="not_applicable", reason: NotApplicableReason)`
  - `RemediationFailed(kind="failed", error: RemediationError, partial_report_path: str | None)`

  Classes are `RemediationNotApplicable` and `RemediationFailed` — **not** `RemediationOutcome.NotApplicable` / `.Failed` (those attribute paths do not exist). Every code path in `RemediationOrchestrator.run` returns exactly one variant; the per-variant happy-path tests (AC-25..AC-28) cover this.
- [ ] **AC-22 (`_finalize` contract).** `def _finalize(self, outcome: RemediationOutcome) -> RemediationOutcome` emits `WorkflowCompleted` (spanning), writes the report via S5-05's writer (`remediation-report.yaml`), returns `outcome` unchanged. The function is total: every variant of `RemediationOutcome` is handled.
- [ ] **AC-23 (`_escalate` contract).** `def _escalate(self, reason: EscalationReason) -> RemediationFailed` emits the appropriate `WorkflowSpanningEvent` (per S6-01 taxonomy), writes a **partial** `remediation-report.yaml`, returns `RemediationFailed(error=RemediationError(error_id=f"escalate.{reason}", message=...), partial_report_path=<path>)`. The 4 in-subgraph reasons (`filesystem_race`, `subprocess_jail_unavailable`, `audit_chain_corrupted`, `vuln_index_corrupted`) shipped by S6-03 are each unit-tested.

### Durability + lifecycle

- [ ] **AC-24 (`flush()` in `finally`).** `RemediationOrchestrator.run` wraps the entire body in `try: ... finally: await asyncio.shield(self._event_log.flush_async()) if asyncio.iscoroutinefunction(self._event_log.flush) else self._event_log.flush()`. Test injects a `MagicMock(spec=EventLog)`, makes one node raise `RuntimeError`, asserts `event_log.flush` was called exactly once **before** the exception propagates / before the orchestrator translates the exception to `RemediationFailed`. **No silent catches** — uncaught exceptions outside the typed-outcome contract are translated to `RemediationFailed(error=RemediationError(error_id="orchestrator.uncaught_exception", message=<truncated stringification>))`, then re-raised iff the caller is the CLI's `--debug` path (out of scope for this story; default re-raise behaviour is **don't re-raise**, return the typed outcome).
- [ ] **AC-25 (per-workflow instance lifecycle — C-Cv3).** Doc-string + ACs make explicit: a `RemediationOrchestrator` instance is bound to one workflow because `event_log` is workflow-scoped at `__init__`. The orchestrator holds no mutable cross-`run()` state inside the single workflow it was constructed for; **reuse across workflows is undefined and not tested**. The CLI constructs one orchestrator per `codegenie remediate` invocation.
- [ ] **AC-26** Performance envelope (informational; benched in S9-03): orchestrator overhead (resolution + bundle + scoring + report) under 500 ms; `npm install + npm test` dominate the remaining ~14 s p50 budget.

### Failure isolation — events emitted before raise

- [ ] **AC-27 (failure isolation).** Every stage emits a typed `WorkflowInternalEvent` (per S6-01 taxonomy) **before** raising; `RemediationFailed` is the catch-all variant with a `partial_report_path` (per ADR-0001 §Consequences via S5-05's writer). A parametric unit test injects an exception from each of the 5 nodes in turn and asserts the corresponding pre-raise event (`PluginResolved` / `BundleBuilt` / `RecipeMatched` / `InstallStageOutcome`+`TestStageOutcome`+`StageOutcome` / `LocalBranchWritten`) was emitted before the exception surfaced.

### Per-variant tests + integration test

- [ ] **AC-28** Unit tests in `tests/unit/transforms/test_orchestrator.py` cover **every** `RemediationOutcome` variant by mocking the subgraph nodes' transitions:
  - `test_run_returns_validated_on_happy_path` — every node `Advance`s except `WriteBranchNode` which `ShortCircuit(Validated(...passed=True...))`.
  - `test_run_returns_requires_human_review_when_resolution_is_universal` — `IngestCveNode` resolves to `UniversalFallbackResolution`; subgraph short-circuits with `RequiresHumanReview`.
  - `test_run_returns_remediation_not_applicable_when_match_short_circuits` — `MatchRecipeNode` returns `ShortCircuit(RemediationNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE"))`.
  - `test_run_returns_remediation_failed_when_apply_short_circuits` — `ApplyRecipeNode` returns `ShortCircuit(RemediationFailed(error=...))`.
  - `test_run_returns_remediation_failed_when_write_branch_escalates_filesystem_race` — `WriteBranchNode` returns `Escalate("filesystem_race")`; `_escalate` produces `RemediationFailed`.
- [ ] **AC-29 (end-to-end integration).** `tests/integration/test_end_to_end_express_cve.py` runs the real `RemediationOrchestrator` against `tests/fixtures/repos/express-cve-2024-21501/` (created by S8-01; if absent at this story's merge time, ship a **minimal** stub fixture + `@pytest.mark.skipif(not fixture.exists())` guard — the stub MUST be sufficient for the smoke assertions below). Asserts:
  - `outcome.kind == "validated"`.
  - `outcome.passed is True` (NOT `outcome.trust_outcome.passed` — `Validated` has no `trust_outcome` field per shipped S1-03 reality).
  - `outcome.failing == []`.
  - `outcome.branch` matches `re.compile(r"^codegenie/cve-2024-21501-[0-9a-f]{8}$")`.
  - `Path(outcome.report_path).exists()`.
  - The per-workflow internal event stream replays exactly: `PluginsLoaded → PluginResolved → BundleBuilt → RecipeMatched → RecipeApplied → InstallStageOutcome(passed=True) → TestStageOutcome(passed=True) → StageOutcome(passed=True) → LocalBranchWritten` (each present exactly once, in this order).
  - **No** `AdapterDegraded` event was emitted (the happy path runs at `confidence="high"`).

### Bar ACs

- [ ] **AC-30** TDD red test exists, was committed in a failing state, is now green (`git log -p tests/unit/transforms/test_orchestrator.py` shows at least one commit with assertion-only content followed by the implementation commit).
- [ ] **AC-31** `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/orchestrator.py src/codegenie/transforms/git_local_ops.py src/codegenie/transforms/nodes/` clean.
- [ ] **AC-32** `make fence` clean (`test_pyproject_fence.py` + `test_no_llm_in_transforms.py` + `test_kernel_frozen.py` — Phase 3 LLM-fence still holds).

## Implementation outline

1. Write `tests/unit/transforms/test_orchestrator.py` + `tests/unit/transforms/test_git_local_ops.py` + per-node test files (red) covering every `RemediationOutcome` variant via mocked nodes; confirm `ModuleNotFoundError` / `ImportError`.
2. **Land `StageOutcome` alias first** — amend `src/codegenie/transforms/trust_scorer.py` (S6-02's file): add `StageOutcome: TypeAlias = TrustOutcome` and add to `__all__`. Re-export from `src/codegenie/transforms/__init__.py`.
3. Create `src/codegenie/transforms/git_local_ops.py`:
   - Plain class `LocalGitOps` (not a Protocol — single impl in Phase 3; D-P4 in Notes).
   - `LocalGitOps.create_patch_branch(self, repo: SandboxedPath, transform: Transform, branch_name: BranchName, event_log: EventLog) -> BranchName` invoking `git -c core.hooksPath=/dev/null checkout -b <name>` etc. via `run_external_cli` with env `{"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false"}` merged onto the existing env.
   - Emit `event_log.emit_internal(GitHooksDisabledForRun(adapter="local_git_ops", reason="run_isolation"))` exactly once per call (BEFORE the first `git` invocation, so even a failing `git` still leaves the audit trail per AC-27).
   - Branch-already-exists detection: inspect `JailedSubprocessResult` / `subprocess` return; surface as `BranchAlreadyExistsError` (typed exception in the same module) — caller maps to `Escalate("filesystem_race")` per AC-20.
4. Create the 5 subgraph node modules under `src/codegenie/transforms/nodes/` — each takes its deps via constructor (D-P2 / AC-9):
   - `__init__.py` — package init; exports nothing additive (modules are imported by `orchestrator.py`).
   - `ingest_cve.py` — `IngestCveNode(vuln_index, registry, event_log)`. `run(state)` looks up CVE in `VulnIndex`; populates `state.resolution` via `registry.resolve(scope)`; emits `PluginResolved`. On `UniversalFallbackResolution` returns `ShortCircuit(RequiresHumanReview(reason="no_concrete_match"))`. On `vuln_index.lookup` raising → `Escalate("vuln_index_corrupted")`. Otherwise `Advance(state.model_copy(update={"resolution": resolution}))`.
   - `match_recipe.py` — `MatchRecipeNode(event_log)`. Iterates `state.resolution.plugin.recipe_registry.all()` (S5-01) in `(precedence desc, name asc)`; first `Applies(plan)` wins → emit `RecipeMatched`, `Advance(state.model_copy(update={"recipe_outcome": Applied(plan=plan, ...)}))`. All `NotApplies` → `ShortCircuit(RemediationNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE"))` (NOT `RemediationOutcome.NotApplicable` — that attribute path does not exist).
   - `apply_recipe.py` — `ApplyRecipeNode(event_log)`. Calls `recipe_engine.apply(plan, bundle, ctx)` (S5-02's `NpmLockfileRecipeEngine`); emits `RecipeApplied` on success. On `RecipeFailed(error)` returns `ShortCircuit(RemediationFailed(error=RemediationError(error_id="recipe.apply_failed", message=error.message)))`. On `Applied(transform)` returns `Advance(state.model_copy(update={"transform": transform}))`.
   - `stage6_validate.py` — `Stage6ValidateNode(validate_fn, event_log)`. `validate_fn` is the orchestrator's bound `_validate_stage6` method, passed in at wire-up; the node MUST NOT import `RemediationOrchestrator` (AC-9 fence). `run(state)` calls `await validate_fn(state.transform, ctx)` → `TrustOutcome`. On `trust_outcome.passed is True` returns `Advance(state.model_copy(update={"trust_outcome": trust_outcome}))`. On `trust_outcome.passed is False` returns `ShortCircuit(Validated(branch=BranchName("codegenie/skipped-no-branch"), report_path=str(report_path), passed=False, failing=list(trust_outcome.failing)))` per AC-12. Emits `StageOutcome` event in both branches.
   - `write_branch.py` — `WriteBranchNode(git_ops, event_log)`. Reads `state.trust_outcome` (must be set + passed=True — invariant follows from outer-loop short-circuit on `passed=False`). Computes branch name per AC-18; calls `git_ops.create_patch_branch(...)`. On success emits `LocalBranchWritten` and returns `ShortCircuit(Validated(branch, report_path, passed=True, failing=[]))`. On `BranchAlreadyExistsError` returns `Escalate("filesystem_race")`. On `BranchName.parse` Err returns `ShortCircuit(RemediationFailed(error=RemediationError(error_id="branch_name.parse_error", message=...)))`.
5. Create `src/codegenie/transforms/orchestrator.py`:
   - Module-level `default_subprocess_jail() -> SubprocessJail` factory that returns `BwrapAdapter()` on Linux / `SandboxExecAdapter()` on macOS (the seam for D-P8).
   - `class RemediationOrchestrator`:
     - `__init__(self, registry, vuln_index, event_log, *, sandbox=None)` stores all four; `self._sandbox = sandbox or default_subprocess_jail()`; constructs `TrustScorer(event_log=event_log)` and stores it on `self._trust_scorer`. Wires up the 5 nodes via constructor injection (passing `self._validate_stage6` as the bound `validate_fn` to `Stage6ValidateNode`).
     - `async def run(self, repo, cve, context=None) -> RemediationOutcome`:
       - On `context is None`: build `ApplyContext(workflow_id=WorkflowId(<ulid>), capabilities=CapabilityBundle.empty())`.
       - Build initial `SubgraphState(workflow_id=context.workflow_id, cve=cve)`.
       - `try:` outer `match` loop (AC-10). `finally:` `await self._event_log.flush()` (or sync, depending on S6-01's signature — pin once S6-01 lands).
       - Uncaught exception outside the typed-outcome contract → translate to `RemediationFailed(error=RemediationError(error_id="orchestrator.uncaught_exception", message=<truncated str>))` after the `finally` block runs (AC-24).
     - `async def _validate_stage6(self, transform, ctx) -> StageOutcome` — the 5-step body from ADR-0007 (AC-7). Calls module-level pure helper `_collect_stage6_signals(...)` (AC-7a); calls `self._trust_scorer.score(signals)`. Returns the `TrustOutcome` (aliased as `StageOutcome`).
     - `def _finalize(self, outcome) -> RemediationOutcome` — emits `WorkflowCompleted` (spanning), writes report via S5-05, returns `outcome` (per AC-22).
     - `def _escalate(self, reason: EscalationReason) -> RemediationFailed` — emits the matching spanning event, writes a partial report, returns `RemediationFailed(...)` (per AC-23).
6. Create module-level pure helper `_collect_stage6_signals(install_result, test_result, lockfile_doc, vuln_index, cve) -> list[TrustSignal]` (AC-7a) — no I/O, no logging, no `self`. Unit-tested in `tests/unit/transforms/test_collect_stage6_signals.py`.
7. Update `src/codegenie/transforms/__init__.py` to re-export `RemediationOrchestrator` and `StageOutcome` (per ADR-0001 §Consequences).
8. If `git` is not yet on `ALLOWED_BINARIES`, amend per Phase-2-style ADR (S4-05) — typically a one-line addition + a fence-test rerun (AC-17).
9. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`. Iterate on red until green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Imports come from the shipped reality. **Do not** copy-edit class names without checking `src/codegenie/transforms/outcomes.py:46-77` — the canonical `__all__` is the source of truth.

```python
# tests/unit/transforms/test_orchestrator.py
"""S6-04 — RemediationOrchestrator + 5-node subgraph + _validate_stage6 seam."""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from codegenie.plugins.events import EventLog  # S6-01
from codegenie.plugins.registry import PluginRegistry  # S2-01
from codegenie.plugins.subgraph import (  # S6-03
    SubgraphNode, SubgraphState, NodeTransition,
    Advance, ShortCircuit, Escalate,
)
from codegenie.transforms.apply_context import ApplyContext  # S1-04
from codegenie.transforms.orchestrator import RemediationOrchestrator
from codegenie.transforms.outcomes import (  # S1-03 — shipped variants
    Validated, RequiresHumanReview, RemediationNotApplicable, RemediationFailed,
    RemediationOutcome, RemediationError,
)
from codegenie.transforms.trust_scorer import (  # S6-02
    StageOutcome, TrustOutcome, TrustScorer, TrustSignal,
)
from codegenie.types.identifiers import WorkflowId, CveId, SignalKind, ErrorId, BranchName


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")


# ---------------------------------------------------------------------------
# AC-3..AC-6 — contract-surface signature pins (S6-06 freezes these).
# ---------------------------------------------------------------------------


def test_init_signature_matches_phase5_contract():
    """AC-3 / ADR-0001."""
    sig = inspect.signature(RemediationOrchestrator.__init__)
    params = list(sig.parameters.keys())
    assert params == ["self", "registry", "vuln_index", "event_log", "sandbox"]
    assert sig.parameters["sandbox"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["sandbox"].default is None


def test_run_signature_matches_phase5_contract():
    """AC-4 / ADR-0001. Declared default is None (not ApplyContext()) because
    ApplyContext requires workflow_id + capabilities."""
    sig = inspect.signature(RemediationOrchestrator.run)
    params = list(sig.parameters.keys())
    assert params == ["self", "repo", "cve", "context"]
    assert sig.parameters["context"].default is None


def test_validate_stage6_signature_is_phase5_wrap_target():
    """AC-5 / ADR-0001 — the load-bearing wrap-target."""
    assert hasattr(RemediationOrchestrator, "_validate_stage6")
    sig = inspect.signature(RemediationOrchestrator._validate_stage6)
    params = list(sig.parameters.keys())
    assert params == ["self", "transform", "ctx"]
    assert inspect.iscoroutinefunction(RemediationOrchestrator._validate_stage6)


def test_stage_outcome_is_trust_outcome():
    """AC-6 — StageOutcome is a TypeAlias for TrustOutcome (single canonical
    site at S6-02; the Phase-5 contract name is the alias)."""
    from codegenie.transforms import StageOutcome, TrustOutcome
    assert StageOutcome is TrustOutcome


# ---------------------------------------------------------------------------
# AC-4 (None default works): orchestrator builds a fresh ApplyContext.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_with_no_context_builds_fresh_apply_context(
    monkeypatch, orchestrator_factory,  # fixtures pinned below in green phase
):
    captured: list[ApplyContext] = []

    class _CaptureCtxNode:
        async def run(self, state: SubgraphState) -> NodeTransition:
            captured.append(state.apply_context)
            return ShortCircuit(outcome=_failed("captured.test"))

    orch = orchestrator_factory(first_node=_CaptureCtxNode())
    await orch.run(repo=_fake_sandboxed_path(), cve=CveId("CVE-2024-21501"))
    assert len(captured) == 1
    assert captured[0].workflow_id  # ulid populated
    # capabilities.empty() guarantees the bundle exists; no ValidationError.


# ---------------------------------------------------------------------------
# AC-10 — outer loop is a single `match`, AST-verified (T-Q2 fix).
# ---------------------------------------------------------------------------


def test_outer_loop_is_single_ast_match_over_node_transition():
    """AC-10 — fragile inspect.getsource(...).count('match ') replaced with
    a real AST walk so `ruff format` / commented strings can't perturb it."""
    src = inspect.getsource(RemediationOrchestrator.run)
    # `inspect.getsource` on a method returns a possibly-indented snippet;
    # ast.parse needs valid module-level Python, so dedent first.
    import textwrap
    tree = ast.parse(textwrap.dedent(src))
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    assert len(matches) == 1, f"expected exactly one match block, got {len(matches)}"
    cases = matches[0].cases
    assert len(cases) == 4, f"expected 4 case arms (3 variants + wildcard), got {len(cases)}"
    # Arm 1: Advance ; arm 2: ShortCircuit ; arm 3: Escalate ; arm 4: wildcard
    pattern_names: list[str] = []
    for c in cases:
        p = c.pattern
        # MatchClass | MatchAs(name=None) for wildcard
        if isinstance(p, ast.MatchClass):
            pattern_names.append(p.cls.id if isinstance(p.cls, ast.Name) else "?")
        elif isinstance(p, ast.MatchAs) and p.pattern is None:
            pattern_names.append("_")
        elif isinstance(p, ast.MatchAs) and isinstance(p.pattern, ast.MatchClass):
            pattern_names.append(p.pattern.cls.id if isinstance(p.pattern.cls, ast.Name) else "?")
        else:
            pattern_names.append("?")
    assert pattern_names == ["Advance", "ShortCircuit", "Escalate", "_"], pattern_names
    # The wildcard arm must call assert_never (exhaustiveness fence at runtime + mypy time).
    wildcard_body_src = ast.unparse(cases[3])
    assert "assert_never" in wildcard_body_src


# ---------------------------------------------------------------------------
# AC-28 — per-variant outcome tests, fleshed out (T-Q1 fix).
# Test fixtures: `orchestrator_factory` and `_fake_sandboxed_path` are
# implementation-supplied in conftest.py; their job is to wire a
# RemediationOrchestrator whose 5 subgraph nodes are mock SubgraphNode
# instances the test can prime. (Greed/Refactor phase pins their shape.)
# ---------------------------------------------------------------------------


def _failed(error_id: str = "test.stub") -> RemediationFailed:
    return RemediationFailed(
        error=RemediationError(error_id=ErrorId(error_id), message="stub for tests"),
        partial_report_path=None,
    )


@pytest.mark.asyncio
async def test_run_returns_validated_on_happy_path(orchestrator_factory):
    """AC-28 happy path: every node Advance-s except WriteBranchNode which
    ShortCircuit(Validated(passed=True, failing=[])). outcome.kind == 'validated'."""
    orch = orchestrator_factory(
        # Each mock node Advance-s and the final WriteBranchNode short-circuits.
        terminal_outcome=Validated(
            branch=BranchName("codegenie/cve-2024-21501-deadbeef"),
            report_path="/tmp/remediation-report.yaml",
            passed=True,
            failing=[],
        ),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-21501"))
    assert outcome.kind == "validated"
    assert outcome.passed is True
    assert outcome.failing == []


@pytest.mark.asyncio
async def test_run_returns_requires_human_review_when_resolution_is_universal(orchestrator_factory):
    """AC-28 — IngestCveNode resolves to UniversalFallbackResolution."""
    orch = orchestrator_factory(
        ingest_outcome=ShortCircuit(outcome=RequiresHumanReview(
            reason="no_concrete_match", handoff_path=None,
        )),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-X"))
    assert outcome.kind == "requires_human_review"
    assert outcome.reason == "no_concrete_match"


@pytest.mark.asyncio
async def test_run_returns_remediation_not_applicable_when_match_short_circuits(orchestrator_factory):
    """AC-28 — All recipes NotApplies. Note class name: RemediationNotApplicable."""
    orch = orchestrator_factory(
        match_outcome=ShortCircuit(outcome=RemediationNotApplicable(
            reason="ALL_RECIPES_NOT_APPLICABLE",
        )),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-Z"))
    assert outcome.kind == "not_applicable"
    assert outcome.reason == "ALL_RECIPES_NOT_APPLICABLE"


@pytest.mark.asyncio
async def test_run_returns_remediation_failed_when_apply_short_circuits(orchestrator_factory):
    """AC-28 — ApplyRecipeNode returns ShortCircuit(RemediationFailed(...))."""
    orch = orchestrator_factory(
        apply_outcome=ShortCircuit(outcome=_failed("recipe.apply_failed")),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-21501"))
    assert outcome.kind == "failed"
    assert outcome.error.error_id == "recipe.apply_failed"


@pytest.mark.asyncio
async def test_run_returns_remediation_failed_when_write_branch_escalates_filesystem_race(orchestrator_factory):
    """AC-28 / AC-23 — WriteBranchNode returns Escalate('filesystem_race');
    _escalate produces RemediationFailed with error_id='escalate.filesystem_race'."""
    orch = orchestrator_factory(
        write_branch_outcome=Escalate(reason="filesystem_race"),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-21501"))
    assert outcome.kind == "failed"
    assert outcome.error.error_id == "escalate.filesystem_race"
    assert outcome.partial_report_path is not None


# ---------------------------------------------------------------------------
# AC-24 — flush() in finally even on uncaught exception.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_log_flushed_in_finally_even_when_node_raises(orchestrator_factory):
    event_log_spy = MagicMock(spec=EventLog)

    class _RaisingNode:
        async def run(self, state: SubgraphState) -> NodeTransition:
            raise RuntimeError("simulated mid-stage failure")

    orch = orchestrator_factory(
        event_log=event_log_spy,
        first_node=_RaisingNode(),
    )
    outcome = await orch.run(_fake_sandboxed_path(), CveId("CVE-2024-21501"))
    # Uncaught exception translates to RemediationFailed (AC-24).
    assert outcome.kind == "failed"
    assert outcome.error.error_id == "orchestrator.uncaught_exception"
    # And flush() ran exactly once.
    event_log_spy.flush.assert_called_once()


# ---------------------------------------------------------------------------
# AC-13 — Validated invariant: passed iff failing == [].
# ---------------------------------------------------------------------------


def test_validated_rejects_inconsistent_passed_and_failing():
    """passed=True must imply failing=[]; passed=False must imply failing non-empty."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Validated(
            branch=BranchName("codegenie/test"),
            report_path="/tmp/r.yaml",
            passed=True,
            failing=[SignalKind("tests")],  # illegal: passed True + non-empty failing
        )
    with pytest.raises(ValidationError):
        Validated(
            branch=BranchName("codegenie/test"),
            report_path="/tmp/r.yaml",
            passed=False,
            failing=[],  # illegal: passed False + empty failing
        )


# ---------------------------------------------------------------------------
# AC-9 — nodes must not import RemediationOrchestrator (no circular).
# ---------------------------------------------------------------------------


def test_no_node_imports_remediation_orchestrator():
    """AC-9 fence: every src/codegenie/transforms/nodes/*.py is AST-scanned
    for any reference to `RemediationOrchestrator`."""
    nodes_dir = Path("src/codegenie/transforms/nodes")
    offenders: list[str] = []
    for py in nodes_dir.glob("*.py"):
        src = py.read_text()
        if "RemediationOrchestrator" in src:
            offenders.append(str(py))
    assert offenders == [], f"nodes must not import RemediationOrchestrator: {offenders}"
```

Per-node, per-helper, per-result-variant tests live in:

- `tests/unit/transforms/nodes/test_ingest_cve_node.py` — each transition arm.
- `tests/unit/transforms/nodes/test_match_recipe_node.py` — all-NotApplies → ShortCircuit(RemediationNotApplicable); first-Applies → Advance.
- `tests/unit/transforms/nodes/test_apply_recipe_node.py` — Applied → Advance; RecipeFailed → ShortCircuit(RemediationFailed).
- `tests/unit/transforms/nodes/test_stage6_validate_node.py` — passed=True → Advance; passed=False → ShortCircuit(Validated(passed=False, failing=...)).
- `tests/unit/transforms/nodes/test_write_branch_node.py` — success → ShortCircuit(Validated); BranchAlreadyExists → Escalate(filesystem_race); BranchName.parse Err → ShortCircuit(RemediationFailed).
- `tests/unit/transforms/test_git_local_ops.py` — per-AC-15 hardening flags; per-AC-16 single GitHooksDisabledForRun emit per call.
- `tests/unit/transforms/test_collect_stage6_signals.py` — per-AC-7a / AC-7b matrix over all 5 `JailedSubprocessResult` variants × both install + tests slots.

End-to-end integration smoke test:

```python
# tests/integration/test_end_to_end_express_cve.py (skeleton; S8-02 extends)
import re
from pathlib import Path
import pytest

from codegenie.types.identifiers import CveId

FIXTURE = Path("tests/fixtures/repos/express-cve-2024-21501")


@pytest.mark.integration
@pytest.mark.skipif(not FIXTURE.exists(), reason="S8-01 lands the full fixture")
async def test_express_cve_end_to_end(express_orchestrator):  # fixture builds the wiring
    outcome = await express_orchestrator.run(
        repo=_sandboxed_repo(FIXTURE),
        cve=CveId("CVE-2024-21501"),
    )
    # AC-29 — Validated has passed/failing, NOT trust_outcome.
    assert outcome.kind == "validated"
    assert outcome.passed is True
    assert outcome.failing == []
    assert re.match(r"^codegenie/cve-2024-21501-[0-9a-f]{8}$", outcome.branch)
    assert Path(outcome.report_path).exists()
```

Run; confirm `ModuleNotFoundError` until `orchestrator.py` exists. Commit the red marker.

### Green — make it pass

Minimum code:
- The 5 nodes are ~30–60 lines each; each is a class with one `async def run` returning `NodeTransition`.
- The orchestrator's `run` is the outer `match` loop + `try/finally` — ~40 lines.
- `_validate_stage6` is ~50 lines (apply transform, two `SubprocessJail.run` calls, 5 signal constructions, `TrustScorer.score`).
- `LocalGitOps.create_patch_branch` is ~25 lines (one or two `run_external_cli` invocations with the hardening flags + event emit).

### Refactor — clean up

- Pull the 5-signal construction in `_validate_stage6` into a helper `_collect_stage6_signals(install_result, test_result, lockfile_doc, vuln_index) -> list[TrustSignal]` for testability.
- Verify the source-inspection test of the outer-loop `match` is robust to formatter changes (`ruff format` should not change the `case` arm structure).
- Module docstrings on every node + the orchestrator cite ADR-0001 and the relevant gap/scenario references.
- Confirm the `_validate_stage6` private-but-public-contract paradox is documented at the method itself (one-paragraph docstring quoting ADR-0001).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/orchestrator.py` | **New** — `RemediationOrchestrator`, the outer `match` loop, `_validate_stage6`, `_finalize`, `_escalate`, `default_subprocess_jail()` factory, module-level `_collect_stage6_signals` pure helper. |
| `src/codegenie/transforms/git_local_ops.py` | **New** — `LocalGitOps.create_patch_branch` with `core.hooksPath=/dev/null` + env hardening, `BranchAlreadyExistsError`, `GitHooksDisabledForRun` emit. |
| `src/codegenie/transforms/nodes/__init__.py` | **New** — package init (empty; nodes are imported by `orchestrator.py`, not re-exported publicly). |
| `src/codegenie/transforms/nodes/ingest_cve.py` | **New** — `IngestCveNode(vuln_index, registry, event_log)`. |
| `src/codegenie/transforms/nodes/match_recipe.py` | **New** — `MatchRecipeNode(event_log)`. |
| `src/codegenie/transforms/nodes/apply_recipe.py` | **New** — `ApplyRecipeNode(event_log)`. |
| `src/codegenie/transforms/nodes/stage6_validate.py` | **New** — `Stage6ValidateNode(validate_fn, event_log)` — `validate_fn` is constructor-injected (no orchestrator import per AC-9). |
| `src/codegenie/transforms/nodes/write_branch.py` | **New** — `WriteBranchNode(git_ops, event_log)`. |
| `src/codegenie/transforms/trust_scorer.py` | **Amend (S6-02 file)** — add `StageOutcome: TypeAlias = TrustOutcome` + `__all__` entry. |
| `src/codegenie/transforms/__init__.py` | **Amend** — re-export `RemediationOrchestrator` and `StageOutcome` per ADR-0001 §Consequences. |
| `tests/unit/transforms/test_orchestrator.py` | **New** — AC-3..AC-10 + AC-24 + per-variant outcome tests + AST-walk outer-loop test + AC-13 invariant regressions. |
| `tests/unit/transforms/test_collect_stage6_signals.py` | **New** — AC-7a / AC-7b — pure helper unit-tested over the 5-variant `JailedSubprocessResult` matrix × install + tests slots. |
| `tests/unit/transforms/test_git_local_ops.py` | **New** — AC-15 hardening flags per invocation, AC-16 single `GitHooksDisabledForRun` emit per call, AC-19 parse-error path, AC-20 branch-already-exists path. |
| `tests/unit/transforms/nodes/test_ingest_cve_node.py` | **New** — IngestCveNode three-transition matrix. |
| `tests/unit/transforms/nodes/test_match_recipe_node.py` | **New** — MatchRecipeNode three-transition matrix; AC-21 `RemediationNotApplicable` class-name regression. |
| `tests/unit/transforms/nodes/test_apply_recipe_node.py` | **New** — ApplyRecipeNode three-transition matrix. |
| `tests/unit/transforms/nodes/test_stage6_validate_node.py` | **New** — AC-11 / AC-12 — passed=True → Advance; passed=False → ShortCircuit(Validated(passed=False, failing=[...])) without skipping the WriteBranchNode is *forbidden*. |
| `tests/unit/transforms/nodes/test_write_branch_node.py` | **New** — AC-18 branch-name happy + AC-19 parse-error + AC-20 branch-already-exists. |
| `tests/unit/transforms/nodes/test_no_orchestrator_import.py` | **New** — AC-9 fence: AST-scan `src/codegenie/transforms/nodes/*.py` for `RemediationOrchestrator` references; fail loud. |
| `tests/integration/test_end_to_end_express_cve.py` | **New** — AC-29 smoke test; `@skipif(not FIXTURE.exists())` until S8-01 lands the full fixture. |

## Out of scope

- **CLI wiring (`codegenie remediate`)** — S6-05 lands the click subcommand + `.codegenie/.lock` flock.
- **Phase 5 contract snapshot test** — S6-06 lands it as a separate gate.
- **Phase 5's `GateRunner` itself** — Phase 5 lands it; this story ships the wrap-target only.
- **Three-retry envelope** — Phase 5 (per ADR-0007); Phase 3 alone runs zero retries.
- **The full `express-cve-2024-21501/` fixture content** — S8-01 lands the comprehensive fixture; this story may ship a minimal stub for the smoke test.
- **OpenRewrite invocation** — Phase 3's npm path uses `NpmLockfileRecipeEngine` (S5-02); the OpenRewrite scaffold (S5-03) is not invoked by Phase 3 workflows.
- **LangGraph migration** — Phase 6 wraps each `match` arm as an edge; out of scope here.
- **`codegenie audit verify` extension to walk the spanning chain** — S6-05.

## Notes for the implementer

- **Class names of `RemediationOutcome` variants are pre-fixed (C-F1).** A reviewer / executor may instinctively type `RemediationOutcome.NotApplicable(...)` or `RemediationOutcome.Failed(...)` (mirroring the Pydantic discriminated-union idiom from other ecosystems). **There is no such attribute path.** The variants live as siblings: `from codegenie.transforms.outcomes import Validated, RequiresHumanReview, RemediationNotApplicable, RemediationFailed`. The `kind` discriminator literals are `"validated"`, `"requires_human_review"`, `"not_applicable"`, `"failed"`. The S6-06 contract snapshot freezes BOTH the class names AND the kind literals.
- **`Validated` does not have a `trust_outcome` field (C-F1).** The flat denormalisation is `passed: bool` + `failing: list[SignalKind]` (S1-03 §Out of scope and S1-03 validation report C-F1). `Stage6ValidateNode` MUST map `Validated(passed=trust_outcome.passed, failing=list(trust_outcome.failing))` — the `_passed_iff_no_failing` validator at `outcomes.py:256-260` enforces the invariant. The full `TrustOutcome` (with `signals` + `confidence`) flows into `remediation-report.yaml` via S5-05; it does NOT cross the `RemediationOutcome` boundary.
- **`StageOutcome` is an alias, not a new class (C-F2 / D-P9).** ADR-0001's named symbol list reads `StageOutcome` because Phase 5's `GateRunner` calls into it; the **type** is `TrustOutcome`. A `TypeAlias` keeps both names alive without a class-identity split. Phase 5's contract snapshot (S6-06) reads the *string* `StageOutcome` from the signature; mypy resolves it to `TrustOutcome` so call-site type-narrowing still works. If you find yourself defining `class StageOutcome(BaseModel): ...` separately, stop — that's a contract break.
- **`_validate_stage6`'s underscore prefix is load-bearing.** A reviewer with no Phase 5 context will say "this is private; rename it `validate_stage6`." Wrong. The underscore is documented in ADR-0001 §Tradeoffs as "load-bearing-but-private-looking" because Phase 5's `GateRunner.run(transition=stage6_validate, ctx=...)` decorates the method by name. Renaming breaks Phase 5. The contract snapshot in S6-06 catches drift, but the documentation comment at the method itself is the human-readable defense.
- **The git hardening flags are not optional.** A reviewer might suggest "but the CWD is the target repo — the user controls it; why harden?" Wrong: the user *operating the CLI* controls the CWD; the *target repo's content* is potentially hostile (per architecture spec §Edge cases E14). `core.hooksPath=/dev/null` disables the analyzed repo's own hooks; `GIT_TERMINAL_PROMPT=0` + `GIT_ASKPASS=/bin/false` prevent any git operation from prompting or invoking a credential helper that could phone home. All three are mandatory.
- **The outer-loop `match` is the single dispatch point.** Per Gap 1 fix (S6-03), the orchestrator does NOT have ad-hoc per-stage `if recipe_outcome.kind == "not_applicable": return ...` branches. Every transition flows through one `match` block. If you find yourself writing a second `match` over `NodeTransition` anywhere in this module, you're back-sliding to the pre-Gap-1 shape.
- **`SubprocessJail` is the only path for `npm install` and `npm test`.** Direct `run_external_cli("npm", ...)` is a security regression (per ADR-0007). The orchestrator constructs the spec, the jail runs it; the orchestrator never sees the child process directly.
- **`Stage6ValidateNode` delegates to the orchestrator's `_validate_stage6` method.** A common mistake: implementing the 5-step validation inside the node and bypassing the wrap-target seam. Wrong — Phase 5 wraps the *method*, not the *node*. The node must call `self._orchestrator._validate_stage6(transform, ctx)` so Phase 5's decoration intercepts.
- **The `EventLog.flush()` `finally`-block is non-negotiable** (ADR-0005 §Consequences). Even an `asyncio.CancelledError` mid-workflow must flush the events written so far so `codegenie audit verify` can replay the partial run.
- **`ApplyContext.prior_attempts` is always `[]` in Phase 3** (per ADR-0001 §Tradeoffs and S1-04). Do not delete the field "because it's unused"; Phase 5 populates it. The contract snapshot freezes the shape.
- **Failure isolation, not failure suppression.** Every stage emits a typed event *before* it raises; `RemediationOutcome.Failed` carries an error variant + a `partial_report_path`. The orchestrator NEVER silently catches; if an exception bubbles past the outer loop, the `finally` flushes events and the exception re-raises (the caller — `codegenie remediate` — translates to exit code 4).
- **Default arg `context=ApplyContext()`** is a known Python gotcha (mutable default), but `ApplyContext` is `frozen=True`, so the default singleton is safe. mypy `--strict` may complain; use `context: ApplyContext | None = None` + `context = context or ApplyContext()` if the typed-default trips mypy.
- **Branch-name uniqueness via `transform_id` short prefix.** Re-running against the same repo + same CVE + same recipe produces the same `transform_id` → same short prefix → branch already exists. Per architecture spec §Harness engineering, the second invocation should be caught by `.codegenie/.lock` (S6-05) before the branch-creation collision; if the lock is somehow bypassed, git's "branch already exists" error surfaces as `RemediationOutcome.Failed`.
- **The `Stage6ValidateNode` short-circuit-vs-advance question** for `passed=False` is **decided, not hedged (C-F3).** Architecture §Control flow step 8 and §Scenarios C: on `passed=False`, Phase 3 alone does not retry; the node returns `ShortCircuit(Validated(branch=<placeholder>, report_path=..., passed=False, failing=...))`. The `WriteBranchNode` is **skipped** — outer-loop short-circuit returns immediately. Phase 5's `GateRunner` is the retry wrapper that re-enters `_validate_stage6` with `prior_attempts` populated; the in-process node graph does NOT loop.
- **Dependency injection over orchestrator-back-reference (D-P2 / AC-9).** A common mistake is to have `Stage6ValidateNode` hold `self._orchestrator` and call `self._orchestrator._validate_stage6(...)`. This creates a circular import (`nodes/stage6_validate.py → orchestrator.py → nodes/stage6_validate.py`) AND ties the node to a concrete class. The right pattern: `Stage6ValidateNode(validate_fn: Callable[[Transform, ApplyContext], Awaitable[StageOutcome]])` — the orchestrator passes its bound `self._validate_stage6` method as a callable at wire-up time. Same shape applies to every node: dependencies as constructor parameters, no global / orchestrator handles. Fence: `tests/unit/transforms/nodes/test_no_orchestrator_import.py` AST-scans for `RemediationOrchestrator` references under `nodes/` and fails loud.
- **Functional core / imperative shell on `_validate_stage6` (D-P3).** The 5-step body is intentionally split: `_collect_stage6_signals(install_result, test_result, lockfile_doc, vuln_index, cve)` is a **pure** module-level function (no `self`, no logging, no I/O). `_validate_stage6` is the imperative shell: it runs the two `SubprocessJail.run` calls, reads the lockfile, calls the helper, calls `self._trust_scorer.score(...)`, returns the `TrustOutcome`. Pure-helper test (`test_collect_stage6_signals.py`) is exhaustively parametrised over the 5-variant `JailedSubprocessResult` matrix — that's where mutation thinking pays off (a flipped `passed` value would silently green-light a failing test suite, so the helper must encode the mapping unambiguously).
- **`LocalGitOps` is a plain class, not a Protocol (D-P4).** Single implementation in Phase 3. Phase 11 (real PR creation, Sigstore signing) may extract a `GitOps` Port with `LocalGitOps` and `GitHubGitOps` adapters; **that is Phase 11's call**, not Phase 3's. Rule 2 (Simplicity First): three similar lines is better than premature abstraction. If a reviewer asks "shouldn't this be a Protocol?", the answer is "Phase 11 owns that decision; Phase 3 ships one implementation."
- **`RemediationOrchestrator` is composed, not subclassed (D-P5).** Phase 4 (LLM fallback) wraps the orchestrator either by registering a fallback recipe at `match_recipe` time or by composing a new orchestrator that calls the Phase-3 instance internally. Phase 5's `GateRunner` likewise wraps via composition, not subclassing. Do NOT design for `class LLMRemediationOrchestrator(RemediationOrchestrator)` — that produces a runtime/MRO mess and breaks Phase 5's wrap-the-method-by-name contract.
- **Plugin.build_subgraph() is intentionally NOT called in Phase 3 (D-P1).** Per the kernel pattern (CLAUDE.md "Extension by addition"), the 5 nodes ARE orchestrator-owned scaffolding in Phase 3, not plugin-provided. A reviewer noting "but `Plugin.build_subgraph(registry)` exists in protocols.py" is correct that the seam exists — Phase 6 (LangGraph wrap) and Phase 7 (distroless plugin with a different node sequence) are the real consumers. Phase 3 ships **one** subgraph shape; widening to per-plugin subgraphs is Phase 6+ territory. The story's `Out of scope` line names this.
- **`SubprocessJail` platform selection lives behind a factory (D-P8).** `default_subprocess_jail() -> SubprocessJail` is a module-level function in `orchestrator.py`; it picks `BwrapAdapter()` on Linux and `SandboxExecAdapter()` on macOS. Phase 5 reuses the same seam by monkey-patching or by passing `sandbox=FirecrackerAdapter()` explicitly. Do NOT inline the platform `if sys.platform == "linux"` switch inside `__init__` — that hides the seam from Phase 5.
- **AST-walk the outer-loop `match`, do not source-grep (T-Q2).** The fragile `inspect.getsource(...).count("match ")` test fails when `ruff format` introduces a string `"match "` in a comment or when a developer adds `match` as a parameter name elsewhere. The AC-10 test uses `ast.parse` + `ast.walk` over the dedented source of `RemediationOrchestrator.run` and asserts exactly one `ast.Match` node with four case arms in order [`Advance`, `ShortCircuit`, `Escalate`, wildcard], with `assert_never` in the wildcard arm body. Same shape used by S1-03's `test_exhaustiveness.py` and S6-03's `test_subgraph_protocol.py`.
- **Per-workflow instance lifecycle (C-Cv3).** The orchestrator is bound to ONE workflow: `event_log` is workflow-scoped at `__init__`. Reuse across workflows is undefined and not tested. The CLI (`codegenie remediate`) constructs a fresh orchestrator per invocation. The `Stateless across runs` language was misleading; AC-25 pins the corrected lifecycle. If you find yourself writing tests that call `await orch.run(...)` twice on the same instance, stop — that's outside the contract.
- **Uncaught exceptions translate to `RemediationFailed`, no silent catches (AC-24).** Every stage emits a typed `WorkflowInternalEvent` BEFORE raising; the orchestrator's outermost `try / finally` flushes the event log and converts uncaught exceptions to `RemediationFailed(error=RemediationError(error_id="orchestrator.uncaught_exception", message=<truncated stringification>))`. The default behaviour is **return the typed outcome, do not re-raise** — the CLI's `--debug` flag (out of scope here) can opt in to re-raise. Never `except Exception: pass`.
