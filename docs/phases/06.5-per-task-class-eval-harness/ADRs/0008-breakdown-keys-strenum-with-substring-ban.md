# ADR-0008: Per-task-class `BreakdownKey` StrEnum + fence-CI substring ban at value level

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** llm-judgment-smuggling · type-safety · static-introspection · fence-ci
**Related:** [ADR-0004](0004-per-task-class-failure-modes-taxonomy.md), [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

`BenchScore.breakdown` is `dict[str, float]` — a per-task-class score decomposition emitted by the rubric. [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) bans the substrings `confidence`, `llm`, `self_reported`, `model_says` from any Pydantic *field name* reachable from `ObjectiveSignals` — the structural defense against LLM-self-confidence smuggling into the trust score. The ban honors [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)'s commitment that the trust score consumes objective signals only.

The critic surfaced the load-bearing escape hatch (critic roadmap-level #5): `BenchScore.breakdown` is `dict[str, float]`, and the static-introspection test walks *Pydantic field names*, not *dict-key string values at runtime*. A rubric author can write `BenchScore(breakdown={"llm_confidence": 0.9, ...})` and the Phase 5 ADR-0014 ban is silent — the field name is `breakdown`, which is innocuous. The promotion gate then reads `BenchScore.breakdown` as evidence, and the LLM-judgment smuggling that ADR-0014 was supposed to prevent at the structural layer is back, one indirection deeper.

Two failure surfaces emerge: (a) a rubric author who *wants* to expose LLM self-confidence as a score component does it by naming a dict key with the banned substrings; (b) a rubric author who *does not realize* this is banned reproduces the pattern by accident, and the promotion gate quietly consumes LLM judgment as if it were a fact. Both fail the [CLAUDE.md §"Facts, not judgments"](../../../CLAUDE.md) commitment that [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) structurally enforces at the Phase 5 layer.

The defense must work *at* the dict-key layer, *before* the runner accepts the `BenchScore`, *and* before the PR merges. Type-system-only fixes (typed-dict, `TypedDict`) are not sufficient — they require a closed key set at the model declaration site, but `breakdown` is *per-task-class* (vuln-remediation scores on different components than migration). The defense must let each task class declare its own valid keys, ban the smuggling substrings *in the declared values*, and validate runtime emissions against the declaration.

## Options considered

- **Free-form `dict[str, float]` keys** (all three input designs). LLM-judgment smuggling unblocked. Critic roadmap-level #5.
- **Global `BreakdownKey` StrEnum in `src/codegenie/eval/models.py`** (closed set). Compile-time exhaustive; mypy catches typos. Adding a Phase 7 migration-specific key (`baseimage.variant_match`) requires editing `models.py` — extension by editing, not addition. Same anti-pattern as [ADR-0003](0003-tier-identifiers-as-str-validated-at-startup.md) avoided for tier slugs.
- **Per-task-class `BreakdownKey` StrEnum in `bench/{task-class}/breakdown_keys.py`** + fence-CI substring ban applied at the *value level* (the StrEnum's member values, not member names). Phase 7 declares its own keys; the runner validates `BenchScore.breakdown` against `task_class.breakdown_keys: frozenset[str]`; the fence walks each StrEnum's values and rejects banned substrings before merge. Mirrors [ADR-0004](0004-per-task-class-failure-modes-taxonomy.md)'s per-task-class data discipline.

## Decision

Every task class ships `bench/{task-class}/breakdown_keys.py` declaring a `StrEnum BreakdownKey` whose members enumerate the valid score-decomposition keys for that task class. The loader extracts the member values into `task_class.breakdown_keys: frozenset[str]` at registration time. The runner validates every key in `BenchScore.breakdown` against this set; unknown keys become `FailureMode(code="rubric.unknown_breakdown_key", severity="block", detail=<key>)`. Fence-CI assertion #5 (`final-design.md §Fence-CI test`) walks the `BreakdownKey` AST and rejects any member *value* containing `confidence`, `llm`, `self_reported`, or `model_says` — the same substrings [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) bans on field names.

## Tradeoffs

| Gain | Cost |
|---|---|
| Closes the dict-key LLM-judgment-smuggling escape hatch the critic identified (critic roadmap-level #5) | Adds one file per task class (`breakdown_keys.py`); bench-curator workflow grows |
| Extension by addition: each task class declares its own valid keys; adding `baseimage.variant_match` for Phase 7 is a Phase 7 edit, not a `src/codegenie/eval/` edit | Two artifacts (rubric-emitted dict keys + StrEnum-declared keys) must stay in sync; drift surfaces as `rubric.unknown_breakdown_key` block-severity events |
| The substring ban applies *at the value level*, where the smuggling actually happens — a member named `STYLE_QUALITY = "llm_confidence"` is caught even though the member *name* is innocuous | The fence-CI assertion is AST-based; a developer who computes member values dynamically (e.g., `f"{prefix}_quality"`) bypasses the AST check. Mitigation: StrEnum values must be `ast.Constant` literals (a Phase 6.5 convention; reviewable in PR) |
| Defense-in-depth at three layers: fence-CI at PR time, runner validation at runtime, `FailureMode(code="rubric.unknown_breakdown_key")` recorded in the audit chain | Three layers means three places to update if the ban substrings change; the substring list is a single source-of-truth shared with [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) |
| Mirrors the per-task-class data discipline of [ADR-0004](0004-per-task-class-failure-modes-taxonomy.md) — failure modes and breakdown keys are both task-class-declared, both CODEOWNERS-gated, both fence-CI-validated | Two parallel per-task-class artifacts (failure_modes.yaml, breakdown_keys.py) carry different formats (YAML, Python); the format split is intentional (StrEnum is the natural shape for "set of strings used as enum-typed dict keys") but readers must understand why one is YAML and one is `.py` |
| Adversarial test (`test_breakdown_key_smuggling.py`) provides concrete enforcement: a synthetic `breakdown_keys.py` declaring `LLM_CONFIDENCE = "llm_confidence"` fails fence-CI at parse time | Naming theater risk persists: a rubric author who names a key `evidence_strength` to smuggle a confidence score is not caught — the substring ban is not a semantic check. Defense is "structural smuggling is blocked; semantic smuggling requires review" |

## Consequences

- `bench/{task-class}/breakdown_keys.py` declares `class BreakdownKey(StrEnum): ...` with members whose values are the valid keys for `BenchScore.breakdown`.
- `src/codegenie/eval/loader.py` imports `breakdown_keys.py` at registration time and extracts `frozenset({member.value for member in BreakdownKey})` into `task_class.breakdown_keys`.
- `src/codegenie/eval/runner.py` validates every key in `BenchScore.breakdown` against `task_class.breakdown_keys`; unknown keys produce `FailureMode(code="rubric.unknown_breakdown_key", severity="block", detail=<key>)` per case (the case completes; the run continues).
- `tests/unit/test_eval_fence.py` assertion #5 (`final-design.md §Fence-CI test`): walks every `bench/{name}/breakdown_keys.py` AST, collects `StrEnum` member values (constraint: must be `ast.Constant`), asserts no value contains `confidence`, `llm`, `self_reported`, or `model_says`. Wall-clock budget shared with the other five fence assertions (≤ 2 s total).
- `tests/unit/test_breakdown_keys_static.py` is the runtime-counterpart (`final-design.md §Unit`): walks every *registered* `BreakdownKey` StrEnum value and rejects the same substrings. Defense-in-depth against AST-bypass scenarios.
- `tests/adv/test_breakdown_key_smuggling.py` ships a synthetic `breakdown_keys.py` with `LLM_CONFIDENCE = "llm_confidence"`; the adversarial test asserts fence-CI fails at parse time.
- Phase 7's `bench/migration-chainguard-distroless/breakdown_keys.py` declares migration-specific keys (e.g., `BASEIMAGE_VARIANT_MATCH`, `RUNTIME_CAPABILITY_MATCH`); the substring ban applies uniformly.
- The substring list (`confidence|llm|self_reported|model_says`) is shared with [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) — any future expansion of the ban list amends both ADRs.
- The fence assertion's strictness (StrEnum values must be `ast.Constant` literals) is a Phase 6.5 invariant; dynamic-value computation in `breakdown_keys.py` is rejected at PR review with a specific diagnostic.
- `BenchScore.breakdown` remains `dict[str, float]` at the type level; the typed-enum-at-the-edge pattern (Pydantic permits the dict, runner validates) keeps the wire type stable while the structural defense lives at the loader.

## Reversibility

**Low.** Reverting the ban removes the structural defense against LLM-judgment smuggling at the `breakdown` layer — the exact escape hatch [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) was designed to close one layer up. Removing the per-task-class StrEnum is mechanically easy; replacing it with a free-form `dict[str, float]` re-opens the smuggling vector across every task class. Forward evolution (expanding the substring ban list, adding semantic-key validation via a per-task-class semantic-key registry) is the realistic direction. The contract decision is durable; the encoding is mechanically reversible but the trust posture would degrade.

## Evidence / sources

- [final-design.md §`BenchScore.breakdown` key smuggling defense](../final-design.md#benchscorebreakdown-key-smuggling-defense)
- [final-design.md §Synthesis ledger row "`breakdown` key smuggling"](../final-design.md#conflict-resolution-table)
- [final-design.md §Departures from all three inputs #5](../final-design.md#departures-from-all-three-inputs)
- [phase-arch-design.md §Fence-CI test (assertion #5)](../phase-arch-design.md#fence-ci-test-testsunittest_eval_fencepy)
- [phase-arch-design.md §Testing strategy — Unit (`test_breakdown_keys_static.py`)](../phase-arch-design.md#test-pyramid)
- [phase-arch-design.md §Edge cases #12](../phase-arch-design.md#edge-cases)
- [critique.md §"Attacks on the best-practices design" — Hidden assumptions #3](../critique.md#hidden-assumptions-2) ("substring matching alone is naming theater" — acknowledged residual)
- [critique.md §Roadmap-level critiques](../critique.md#roadmap-level-critiques)
- [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) — the field-name ban this ADR extends to dict-key values
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — the commitment both bans preserve
