# ADR-0004: Workflow-determinism enforcement via three layers (import-linter + AST fence + Replayer)

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** determinism · fence · static-analysis · CI-gate
**Related:** [ADR-0010](0010-activity-granularity-asymmetric.md), [production ADR-0033](../../../production/adrs/0033-sum-types-for-domain-state.md)

## Context

Temporal's replay model requires workflow bodies to be deterministic: a recorded history must reproduce the same control flow when replayed on a fresh worker. The Temporal SDK detects non-determinism at runtime via `Replayer`, but by then a buggy workflow may already be in production. The well-known footguns are `random.*`, `time.*`, `datetime.now()`, `uuid.uuid4()`, `os.environ`, network IO, set-literal iteration order, and dict-iteration order under Python version drift.

Phase 9 must catch non-determinism *as early as possible* in the contributor's loop — at pre-commit if possible, at `make test` otherwise — because a CI-only catch surfaces hours after the offending code was written and a production-only catch may not surface until the rare resume path is exercised.

## Options considered

- **Single layer: `Replayer` test only.** Trust the SDK's runtime check. Catches everything, but as late as CI on a fixture history; transitive issues (Python-minor dict-order changes) may slip past until prod. **Pattern:** runtime check only.
- **Single layer: AST walker.** Reject literal `set(`, `random.*` calls, `time.*` calls, `datetime.now()`, etc. Catches direct usage; misses transitive (imported helper calls `random.random()` internally). **Pattern:** static AST analysis.
- **Three layers, defence-in-depth.** (1) `import-linter` contract forbidding `random | time | datetime | uuid | os | socket | httpx | requests | redis | psycopg | asyncpg | subprocess | codegenie.exec | codegenie.transforms | codegenie.probes` from being imported by any module in `codegenie.durable.workflows`. (2) AST fence at `make test` that rejects `set(`, `random.*`, `time.*` calls in workflow source. (3) `temporalio.testing.WorkflowReplayer` test in CI against a fixture workflow history. **Pattern:** layered defence with strictly later layers catching strictly transitive issues.

## Decision

Three layers, strictly ordered: `import-linter` at pre-commit, AST fence at `make test`, `Replayer` at CI. Earlier layers fail fast; later layers catch what earlier ones cannot. **Pattern: defence in depth with strictly increasing coverage and strictly increasing latency.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Pre-commit catches the common cases (importing `random`) — feedback in seconds | Three places to maintain the forbidden vocabulary; vocabulary drift across layers is possible |
| AST fence catches direct calls even when the import is transitive (e.g., `from foo import bar` where `bar` calls `random.random()`) — feedback in ~30 s at `make test` | AST walker is bespoke code; new footguns require AST-fence updates |
| `Replayer` catches transitive non-determinism the AST cannot see (LangGraph version drift, dict-order changes between Python 3.11 and 3.12) | Feedback latency is highest; requires a fixture workflow history checked into the repo |
| Each layer is independently useful and each one's vocabulary is documented | Contributors confused why a `random.choice` import is rejected at pre-commit but their fix (passing the value as an activity arg) is silently fine — needs `docs/contributing.md` paragraph |
| The vocabulary itself is the contract for "what a workflow body cannot import" — auditable | The vocabulary is wider than Temporal's official forbidden list (we add `psycopg | asyncpg | subprocess` etc.) — intentional, but easy to over-add |

## Pattern fit

Defence in depth is the canonical pattern for "the cost of getting this wrong is high; the cost of multiple cheap checks is low". The toolkit's `design-patterns-toolkit.md §Multi-stage validation` argues for "fail at the earliest layer that can see the problem". Each strictly later layer catches strictly more — there is no overlap-wasted check; the AST fence catches what import-linter cannot see (e.g., `eval("random.random()")`-shaped code is rejected by the AST as a `random` token even though no `import random` exists in scope), and `Replayer` catches what neither can see.

## Consequences

- `import-linter` configuration adds a contract `codegenie.durable.workflows-must-be-pure` listing the forbidden module set.
- `tests/fence/test_workflow_determinism.py` is a new AST walker that opens every file under `src/codegenie/durable/workflows/` and rejects forbidden tokens.
- `tests/workflows/test_replay_determinism.py` records a workflow history fixture and runs `WorkflowReplayer.run_replay_workflows([fixture])` against it on every PR. The fixture must be regenerated when activity signatures change — a separate, fenced workflow lives in `Makefile`.
- The fixture history is checked into the repo; its format is Temporal SDK version-pinned; any SDK upgrade requires regenerating the fixture and may surface latent non-determinism (which is the point).
- Contributors who try to add `datetime.now()` to a workflow body see a typed `import-linter` error at pre-commit; suggested fix in the error message: "thread the timestamp as an activity input or use `workflow.now()`".
- Phase 9 ships the per-Python-minor matrix (3.11 + 3.12) for the `Replayer` test so dict-order regressions surface on every PR.
- New forbidden modules (e.g., when Python introduces a new clock library) require updating all three layers — surfaced as a "vocabulary drift" maintenance item.

## Reversibility

**High.** Each layer is independently disable-able. The decision is layered conservatism; relaxing it (removing the AST fence, say) is a one-line config change. The vocabulary is data, not code shape.

## Evidence / sources

- [`../phase-arch-design.md §Scenario 3 — Replay-determinism violation`](../phase-arch-design.md#scenario-3--adversarial-replay-determinism-violation-caught-by-ci-replayer)
- [`../phase-arch-design.md §Harness engineering — Replay`](../phase-arch-design.md#harness-engineering)
- [`../phase-arch-design.md §Edge case 5`](../phase-arch-design.md#edge-cases)
- [`../final-design.md §Test plan — Replay-determinism (CI-gating)`](../final-design.md)
- Temporal docs: *Workflow Determinism* — `https://docs.temporal.io/workflows#deterministic-constraints`
- `tools/import-linter.toml` (existing precedent: `codegenie-no-llm-sdks` contract from production ADR-0005)
