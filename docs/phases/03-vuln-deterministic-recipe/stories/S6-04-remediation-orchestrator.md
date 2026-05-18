# Story S6-04 — `RemediationOrchestrator` + 5-node subgraph + Phase-5 `_validate_stage6` seam + hardened `LocalGitOps`

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** L
**Depends on:** S6-02, S6-03, S5-05
**ADRs honored:** ADR-0001 (ship the Phase-5 contract surface; `_validate_stage6` is the named wrap-target — exact signature is load-bearing), ADR-0005 (orchestrator constructs and owns `EventLog` lifecycle; `flush()` in `finally`), ADR-0007 (Phase 3 runs `npm install` + `npm test` inside `SubprocessJail`; Phase 5 wraps the retry envelope), ADR-0010 (`RemediationOutcome` tagged union), [Phase 5 ADR-0001](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md) (the Stage-6 seam Phase 5 wraps)

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

- [ ] `src/codegenie/transforms/orchestrator.py` exists; `from codegenie.transforms.orchestrator import RemediationOrchestrator` succeeds.
- [ ] `RemediationOrchestrator.__init__(self, registry: PluginRegistry, vuln_index: VulnIndex, event_log: EventLog, *, sandbox: SubprocessJail | None = None) -> None` — exact signature. `sandbox=None` defaults to the platform adapter (`BwrapAdapter` on Linux, `SandboxExecAdapter` on macOS).
- [ ] `async def run(self, repo: SandboxedPath, cve: CveId, context: ApplyContext = ApplyContext()) -> RemediationOutcome` — exact signature, default `ApplyContext()` constructable.
- [ ] `async def _validate_stage6(self, transform: Transform, ctx: ApplyContext) -> StageOutcome` — exact signature. This is the **method Phase 5's `GateRunner` wraps by name**. The underscore prefix is intentional and load-bearing; renaming is a contract break.
- [ ] `_validate_stage6` body executes the 5 steps from ADR-0007 §Decision: (1) apply transform to temp worktree; (2) `SubprocessJail.run(npm install)` with `time_budget_s=180`; (3) `SubprocessJail.run(npm test)` with `time_budget_s=300`; (4) collect 5 `TrustSignal`s (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta`); (5) return `Validated(passed=...)` via `TrustScorer.score(signals)`.
- [ ] The 5 subgraph nodes are concrete classes implementing `SubgraphNode` Protocol from S6-03: `IngestCveNode`, `MatchRecipeNode`, `ApplyRecipeNode`, `Stage6ValidateNode`, `WriteBranchNode`. Each `async def run(state: SubgraphState) -> NodeTransition` returns `Advance | ShortCircuit | Escalate`.
- [ ] The outer loop in `RemediationOrchestrator.run` is **one `match` block** over `NodeTransition` (the Gap 1 pattern from S6-03):
  ```python
  for node in self._subgraph_nodes:
      transition = await node.run(state)
      match transition:
          case Advance(state=s):       state = s
          case ShortCircuit(outcome=o): return self._finalize(o)
          case Escalate(reason=r):     return self._escalate(r)
          case _:                      assert_never(transition)
  ```
- [ ] `LocalGitOps.create_patch_branch(repo, transform, branch_name) -> BranchName` lives in `src/codegenie/transforms/git_local_ops.py`; uses `run_external_cli` with **all of**: `-c core.hooksPath=/dev/null`, env `GIT_TERMINAL_PROMPT=0`, env `GIT_ASKPASS=/bin/false`. The git CLI must be already on `ALLOWED_BINARIES` (Phase 0 baseline); if not, S4-05's ADR-amendment covers it.
- [ ] On every git invocation, a `GitHooksDisabledForRun` event is emitted to `event_log.emit_internal(...)` (variant defined in S6-01).
- [ ] Branch name format: `codegenie/cve-{cve_id_lowercase}-{transform_id_short}` (8-char prefix of the BLAKE3 digest); validated via `BranchName.parse(...)` smart constructor (S1-01).
- [ ] `RemediationOutcome` is the tagged union from S1-03: `Validated(branch, report_path, trust_outcome) | RequiresHumanReview(reason, handoff_path) | NotApplicable(reason) | Failed(error, partial_report_path)`. Every code path returns exactly one variant.
- [ ] `EventLog.flush()` is called in a `try / finally` wrapping the entire `run()` body — even on uncaught exceptions, the events written so far are durable.
- [ ] Stateless across runs: a single `RemediationOrchestrator` instance may execute `run(...)` for multiple workflows sequentially in the same process (no shared mutable state across `run` calls).
- [ ] Performance envelope (informational; benched in S9-03): orchestrator overhead (resolution + bundle + scoring + report) under 500 ms; `npm install + npm test` dominate the remaining ~14 s p50 budget.
- [ ] **Failure isolation**: every stage emits a typed event *before* raising; `RemediationOutcome.Failed` is the catch-all variant with a `partial_report_path` (per ADR-0001 §Consequences via S5-05's writer).
- [ ] Unit tests in `tests/unit/transforms/test_orchestrator.py` cover every `RemediationOutcome` variant by mocking the subgraph nodes' transitions.
- [ ] An end-to-end integration test in `tests/integration/test_end_to_end_express_cve.py` runs `codegenie.transforms.orchestrator.RemediationOrchestrator(...).run(...)` against `tests/fixtures/repos/express-cve-2024-21501/` (created by S8-01; if not yet present, a minimal stub fixture is created in this story and extended in S8-01) and asserts:
  - Exit-equivalent: `outcome.kind == "validated"`.
  - `outcome.trust_outcome.passed is True`.
  - A branch matching `codegenie/cve-2024-21501-*` exists.
  - `remediation-report.yaml` exists at the expected path.
  - The internal stream contains all expected `*_stage_outcome` events.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/transforms/test_orchestrator.py` (red) covering all 4 `RemediationOutcome` variants via mocked nodes; confirm `ImportError`.
2. Create `src/codegenie/transforms/git_local_ops.py`:
   - `LocalGitOps.create_patch_branch(repo, transform, branch_name, event_log) -> BranchName` invoking `git -c core.hooksPath=/dev/null checkout -b <name>` etc. via `run_external_cli` with the hardening env vars.
   - Emit `GitHooksDisabledForRun(adapter="local_git_ops", reason="run_isolation")` once per `create_patch_branch` call.
3. Create the 5 subgraph node modules under `src/codegenie/transforms/nodes/`:
   - `ingest_cve.py` — `IngestCveNode`: looks up the CVE in `VulnIndex`; populates `state.resolution` via `registry.resolve(scope)`; returns `Advance(state)` or `Escalate("vuln_index_corrupted")`.
   - `match_recipe.py` — `MatchRecipeNode`: iterates the plugin's `RecipeRegistry.all()` in `(precedence desc, name asc)`; first `Applies(plan)` wins; all-`NotApplies` → `ShortCircuit(RemediationOutcome.NotApplicable(...))`.
   - `apply_recipe.py` — `ApplyRecipeNode`: calls `recipe_engine.apply(plan, bundle, ctx)`; on `Failed` returns `ShortCircuit(RemediationOutcome.Failed(...))`; on `Applied(transform)` returns `Advance(state.model_copy(update={"transform": transform}))`.
   - `stage6_validate.py` — `Stage6ValidateNode`: calls `self._orchestrator._validate_stage6(transform, ctx)`; on `passed=False` returns `Advance` (so `write_branch` still runs — but writing the branch is conditioned on `trust_outcome.passed`; OR per ADR-0007 returns `ShortCircuit(Validated(passed=False, ...))`; **clarify with reviewer; default: ShortCircuit Validated with passed=False, so Phase 5's retry envelope sees the outcome and decides**).
   - `write_branch.py` — `WriteBranchNode`: calls `LocalGitOps.create_patch_branch(...)`; on success returns `ShortCircuit(Validated(branch, report_path, trust_outcome))`; on filesystem race returns `Escalate("filesystem_race")`.
4. Create `src/codegenie/transforms/orchestrator.py`:
   - `class RemediationOrchestrator`:
     - `__init__` stores `registry`, `vuln_index`, `event_log`, `sandbox` (default = platform adapter). Constructs `TrustScorer(event_log=event_log)` and stores it on `self._trust_scorer`.
     - `async def run(...)` — builds initial `SubgraphState`, instantiates the 5 nodes, runs the outer `match` loop (S6-03 pattern). In a `try / finally`, calls `event_log.flush()` regardless.
     - `async def _validate_stage6(self, transform, ctx) -> StageOutcome` — the 5-step body from ADR-0007. Returns `StageOutcome` (a Pydantic model defined here or in S1-03; per ADR-0001 it's the typed return shape Phase 5 reads).
     - `def _finalize(self, outcome) -> RemediationOutcome` — emits `WorkflowCompleted`, writes report via S5-05, returns the outcome.
     - `def _escalate(self, reason) -> RemediationOutcome` — emits the appropriate event, writes a partial report, returns `RemediationOutcome.Failed(...)`.
5. Update `src/codegenie/transforms/__init__.py` to re-export `RemediationOrchestrator` (per ADR-0001 §Consequences).
6. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/transforms/test_orchestrator.py
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codegenie.plugins.events import EventLog
from codegenie.plugins.registry import PluginRegistry
from codegenie.plugins.subgraph import Advance, ShortCircuit, Escalate
from codegenie.transforms.orchestrator import RemediationOrchestrator
from codegenie.transforms.apply_context import ApplyContext
from codegenie.types.identifiers import WorkflowId, CveId


def _wf() -> WorkflowId:
    return WorkflowId("01HFEEDFACE0000000000000000")


def test_init_signature_matches_phase5_contract():
    """ADR-0001: signature is __init__(self, registry, vuln_index, event_log, *, sandbox=None)."""
    sig = inspect.signature(RemediationOrchestrator.__init__)
    params = list(sig.parameters.keys())
    assert params == ["self", "registry", "vuln_index", "event_log", "sandbox"]
    assert sig.parameters["sandbox"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["sandbox"].default is None


def test_run_signature_matches_phase5_contract():
    """ADR-0001: async def run(self, repo, cve, context=ApplyContext()) -> RemediationOutcome."""
    sig = inspect.signature(RemediationOrchestrator.run)
    params = list(sig.parameters.keys())
    assert params == ["self", "repo", "cve", "context"]


def test_validate_stage6_signature_is_phase5_wrap_target():
    """ADR-0001: async def _validate_stage6(self, transform, ctx) -> StageOutcome.

    THIS IS THE PHASE-5 WRAP-TARGET. Renaming the method or changing the
    signature is a CONTRACT BREAK that prevents Phase 5 from shipping.
    """
    assert hasattr(RemediationOrchestrator, "_validate_stage6")
    sig = inspect.signature(RemediationOrchestrator._validate_stage6)
    params = list(sig.parameters.keys())
    assert params == ["self", "transform", "ctx"]
    # Must be async — Phase 5 awaits this method.
    assert inspect.iscoroutinefunction(RemediationOrchestrator._validate_stage6)


# Additional async tests (bodies elided; structure indicated):
# - test_run_returns_validated_on_happy_path — mock 5 nodes; each Advance until WriteBranch ShortCircuits Validated.
# - test_run_returns_not_applicable_when_match_short_circuits — MatchRecipeNode returns ShortCircuit(NotApplicable).
# - test_run_returns_failed_when_apply_short_circuits — ApplyRecipeNode returns ShortCircuit(Failed).
# - test_run_escalates_on_filesystem_race — WriteBranchNode returns Escalate; orchestrator returns Failed.
# - test_event_log_flushed_in_finally_even_on_exception — assert MagicMock(spec=EventLog).flush.called even when a node raises.
# - test_create_patch_branch_includes_git_hardening — patch run_external_cli; assert -c core.hooksPath=/dev/null + env vars.
# - test_git_hooks_disabled_event_emitted_per_branch_write — one GitHooksDisabledForRun per create_patch_branch.
# - test_orchestrator_constructs_trust_scorer_with_injected_event_log — Gap-5 fix verified.


@pytest.mark.asyncio
async def test_outer_loop_is_single_match_over_node_transition():
    """The outer loop must be a `match` over Advance | ShortCircuit | Escalate.

    Verified by source inspection: there must be exactly one `match` statement
    in RemediationOrchestrator.run() with three case arms.
    """
    src = inspect.getsource(RemediationOrchestrator.run)
    assert src.count("match ") == 1
    assert "case Advance" in src
    assert "case ShortCircuit" in src
    assert "case Escalate" in src
    assert "assert_never" in src  # exhaustiveness fallback
```

Plus an end-to-end integration smoke test:

```python
# tests/integration/test_end_to_end_express_cve.py (skeleton; S8-02 extends)
@pytest.mark.integration
async def test_express_cve_end_to_end(tmp_path):
    repo = Path("tests/fixtures/repos/express-cve-2024-21501")
    # ... construct registry, vuln_index, event_log, orchestrator ...
    outcome = await orchestrator.run(repo=repo, cve=CveId("CVE-2024-21501"))
    assert outcome.kind == "validated"
    assert outcome.trust_outcome.passed is True
    assert outcome.branch.startswith("codegenie/cve-2024-21501-")
    assert (tmp_path / ".codegenie" / "context" / "remediation-report.yaml").exists()
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

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
| `src/codegenie/transforms/orchestrator.py` | New file — `RemediationOrchestrator`, the outer `match` loop, `_validate_stage6`, `_finalize`, `_escalate` |
| `src/codegenie/transforms/git_local_ops.py` | New file — `LocalGitOps.create_patch_branch` with `core.hooksPath=/dev/null`, env hardening, `GitHooksDisabledForRun` emit |
| `src/codegenie/transforms/nodes/__init__.py` | New file — package init |
| `src/codegenie/transforms/nodes/ingest_cve.py` | New file — `IngestCveNode` |
| `src/codegenie/transforms/nodes/match_recipe.py` | New file — `MatchRecipeNode` |
| `src/codegenie/transforms/nodes/apply_recipe.py` | New file — `ApplyRecipeNode` |
| `src/codegenie/transforms/nodes/stage6_validate.py` | New file — `Stage6ValidateNode` (delegates to orchestrator's `_validate_stage6`) |
| `src/codegenie/transforms/nodes/write_branch.py` | New file — `WriteBranchNode` |
| `src/codegenie/transforms/__init__.py` | Re-export `RemediationOrchestrator` (ADR-0001 §Consequences) |
| `tests/unit/transforms/test_orchestrator.py` | New file — signature tests (the load-bearing Phase-5 contract checks) + per-variant outcome tests + outer-loop `match` inspection + event-log flush guarantee |
| `tests/unit/transforms/test_git_local_ops.py` | New file — git hardening flags verified per invocation; `GitHooksDisabledForRun` emit per call |
| `tests/unit/transforms/nodes/test_*.py` | New files — one per node, covering its three-transition matrix |
| `tests/integration/test_end_to_end_express_cve.py` | New file — smoke test against `express-cve-2024-21501/` fixture (skeleton; S8-02 hardens) |

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
- **The `Stage6ValidateNode` short-circuit-vs-advance question** for `passed=False`: the architecture spec §Control flow says "On `passed=False` ... Phase 3 alone: no retry, return the outcome." Default implementation: `ShortCircuit(Validated(passed=False, ...))` so the orchestrator's `_finalize` writes the report and returns. The `write_branch` node is **skipped** when `passed=False` (no branch for a known-bad transform). Phase 5's `GateRunner` is the retry wrapper that re-enters `_validate_stage6`; the in-process node graph does not loop.
