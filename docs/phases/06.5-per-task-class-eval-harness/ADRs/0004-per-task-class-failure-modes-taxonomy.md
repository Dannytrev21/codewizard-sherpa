# ADR-0004: Per-task-class `failure_modes.yaml` taxonomy with typed `FailureMode`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** taxonomy · trust · promotion · extension-by-addition · fail-loud
**Related:** [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md), [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)

## Context

[Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) makes "zero `block`-severity failure modes in the breakdown" a load-bearing precondition for promotion: a task class cannot graduate to the next tier if any case ended with a block-severity failure. The ADR does not define what `block`-severity *is*. All three Phase 6.5 input designs left the field as free-form strings — `BenchScore.failure_modes: list[str]` or `tuple[str, ...]`. The critic identified this as a shared blind spot (critic shared blind spot #3): if `block`-severity is not data, the promotion gate's central precondition is rubric-author opinion.

Two failure modes emerge from the free-form encoding: (a) a rubric author writes `failure_modes=("tests_failed",)` and another writes `failure_modes=("validator.tests_failed",)` — the gate cannot tell whether both indicate the same block-severity event; (b) a rubric emits `failure_modes=("style_warning",)` and the gate has no taxonomy to know that `style_warning` is `warn`-severity and should not block promotion. The gate either trusts the rubric to self-classify (which violates [CLAUDE.md §"Facts, not judgments"](../../../CLAUDE.md) — severity is the gate's judgment, not the rubric's) or carries a global severity dictionary (which violates extension by addition — every task class would edit the same file).

The ADR-0016 §Decision §2 schema (`BenchScore` with `failure_modes: list[str]`) is the contract this ADR sharpens, not replaces. The per-task-class taxonomy is the only encoding that lets `block`-severity be data, lets new task classes register new codes by addition, and lets the runner fail loud on taxonomy drift instead of silently accepting whatever string the rubric emits.

## Options considered

- **Free-form strings, no taxonomy** (all three input designs). Rubric emits whatever it wants; gate counts substrings or trusts severity prefixes. Fails the "what counts as block?" question; rubric authors implicitly own the gate criterion.
- **Global `FAILURE_MODES = {...}` constant in `src/codegenie/eval/models.py`.** Severity is data. But adding a Phase 7 migration-specific code (`baseimage.variant_mismatch`) requires editing `models.py` — extension by editing, not addition. Violates [CLAUDE.md §"Extension by addition"](../../../CLAUDE.md).
- **Per-task-class `failure_modes.yaml` registering `{code: {severity: block|warn|info, description: ...}}`.** Taxonomy is per-task-class data, declarative, CODEOWNERS-gated. The runner resolves rubric-emitted free-form codes against the registered taxonomy at validation time. Unknown codes resolve to `rubric.unknown_failure_mode` (block-severity) — fail loud on taxonomy drift. Mirrors the per-task-class `breakdown_keys.py` discipline ([ADR-0008](0008-breakdown-keys-strenum-with-substring-ban.md)).

## Decision

Every task class ships `bench/{task-class}/failure_modes.yaml` declaring the full set of failure codes the rubric may emit, each with `severity ∈ {block, warn, info}` and a non-empty `description`. The loader parses this into `task_class.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]` at registration time. The runner validates every rubric-emitted `failure_mode_code: str` against the taxonomy; unknown codes are recorded as `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=<original_code>)`. `BenchScore.failure_modes` is typed `tuple[FailureMode, ...]` where `FailureMode` is a frozen Pydantic model with `code: str`, `severity: Literal["block","warn","info"]`, `detail: str | None`. `BenchRunReport.block_severity_failure_modes: tuple[str, ...]` is the deduplicated set the promotion gate reads.

## Tradeoffs

| Gain | Cost |
|---|---|
| `block`-severity is data, not free text — ADR-0016 §Decision §4's promotion precondition becomes structurally enforceable | One additional file (`failure_modes.yaml`) per task class; bench-curator workflow grows by one artifact |
| Extension by addition: Phase 7 adds `baseimage.variant_mismatch` to `bench/migration-chainguard-distroless/failure_modes.yaml`; zero edits to `src/codegenie/eval/` | Two artifacts (the rubric's emitted codes, the YAML's declared codes) must stay in sync; drift surfaces as `rubric.unknown_failure_mode` block-severity events |
| Fail loud on taxonomy drift: a typo in the rubric (`validatr.tests_failed`) doesn't silently pass — it produces a block-severity `rubric.unknown_failure_mode` that surfaces in the promotion verdict's reasons | Adds friction to bench-author dev loop: a new failure code in the rubric requires a YAML edit before the rubric will pass its own tests |
| Fence-CI (assertion #6) validates the YAML structurally — every entry has a valid `severity` and a non-empty `description`; malformed taxonomy fails at PR review | YAML parsing + validation cost adds ~5 ms to per-task-class load; negligible vs SUT cost |
| The taxonomy is CODEOWNERS-gated under `bench/**` — a contributor cannot quietly downgrade `validator.tests_failed` from `block` to `warn` without two-reviewer approval | Severity downgrades become a separate review surface from rubric code review; reviewers must understand both |
| Initial vuln-remediation taxonomy is illustrative (`final-design.md §Block-severity definition`); Phase 7's migration taxonomy is independent — task classes do not share severity assignments | Codes shared across task classes (e.g., `sut.exception`, `sut.timeout`, `rubric.timeout`, `rubric.unknown_failure_mode`) must be replicated per task class; a meta-taxonomy of "always block" runner-internal codes could centralize, but is deferred |

## Consequences

- `src/codegenie/eval/models.py` declares `FailureMode` (frozen Pydantic, `extra="forbid"`) with `code: str`, `severity: Literal["block","warn","info"]`, `detail: str | None = None`.
- `BenchScore.failure_modes: tuple[FailureMode, ...]`; `BenchRunReport.block_severity_failure_modes: tuple[str, ...]` (dedup'd codes).
- `src/codegenie/eval/loader.py` parses `bench/{task-class}/failure_modes.yaml` at registration time into `task_class.failure_mode_taxonomy`.
- `src/codegenie/eval/runner.py` resolves rubric-emitted `failure_mode_code` strings against `task_class.failure_mode_taxonomy`; unknown codes become `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=<original_code>)`.
- `tests/unit/test_eval_fence.py` assertion #6 (`final-design.md §Fence-CI test`): walks every `bench/{name}/failure_modes.yaml`; asserts every entry has `severity ∈ {block, warn, info}` and a non-empty `description`.
- Initial vuln-remediation taxonomy (illustrative; ships in `bench/vuln-remediation/failure_modes.yaml`):
  - `block`: `validator.build_failed`, `validator.tests_failed`, `validator.cve_not_dropped`, `recipe.semantic_drift`, `rubric.timeout`, `rubric.unknown_failure_mode`, `sut.exception`, `sut.cancelled`
  - `warn`: `recipe.unused_field`, `cassette.tier_mismatch`, `cost.over_estimate`
  - `info`: `recipe.optimized_path`, `rag.first_hit`
- A new severity (e.g., `"fatal"`) would require an ADR amendment plus a `Literal[...]` edit in `models.py` — severity is part of the structural contract, not the per-task-class taxonomy. This is the explicit boundary: codes are extension-by-addition; severities are structural.
- Phase 7's migration rubric inherits the discipline — `bench/migration-chainguard-distroless/failure_modes.yaml` ships in Phase 6.5 with seed entries; Phase 7 expands.
- The promotion gate reads `BenchRunReport.block_severity_failure_modes` and adds each non-empty entry to `reasons` when `evidence_sufficient=False` — operators see exactly which codes blocked promotion.

## Reversibility

**Medium.** Reverting to free-form strings means stripping the taxonomy load and the runner's resolution path — mechanically a small diff. But every prior `BenchRunReport` carries `block_severity_failure_modes: tuple[str, ...]` derived from the taxonomy; reverting would not recompute history. Worse: the promotion gate's precondition becomes unenforceable under free-form, undoing the load-bearing ADR-0016 §Decision §4 commitment. The path is "supersede this ADR, redesign the severity contract" — not "delete the taxonomy." Forward evolution (adding `"fatal"` severity, or a shared cross-task-class meta-taxonomy) is the realistic direction.

## Evidence / sources

- [final-design.md §Block-severity definition](../final-design.md#block-severity-definition)
- [final-design.md §Synthesis ledger row "Failure-mode taxonomy"](../final-design.md#conflict-resolution-table)
- [final-design.md §Shared blind spots considered #3](../final-design.md#shared-blind-spots-considered)
- [phase-arch-design.md §Fence-CI test (assertion #6)](../phase-arch-design.md#fence-ci-test-testsunittest_eval_fencepy)
- [phase-arch-design.md §Edge cases #12, #21](../phase-arch-design.md#edge-cases)
- [phase-arch-design.md §Tradeoffs (consolidated)](../phase-arch-design.md#tradeoffs-consolidated)
- [critique.md §"Attacks on the best-practices design" — Hidden assumptions #3](../critique.md#hidden-assumptions-2) (substring matching alone is naming theater — same principle)
- [Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the "zero block-severity" precondition this ADR makes structurally enforceable
