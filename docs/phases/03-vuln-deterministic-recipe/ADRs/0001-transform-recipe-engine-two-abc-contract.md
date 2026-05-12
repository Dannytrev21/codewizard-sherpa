# ADR-0001: Phase 3 introduces exactly two public ABCs — `Transform` and `RecipeEngine` — and no `Validator` ABC

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** contract · abc · extension-by-addition · synthesizer-departure · phase-3-foundation
**Related:** [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md), ADR-0002, ADR-0003

## Context

Phase 3 ships the first transform — the second load-bearing contract in the system after Phase 1's `Probe`. Phase 4 (LLM fallback), Phase 5 (Trust-Aware gates), Phase 7 (Chainguard migrations), and Phase 15 (agentic recipe authoring) all compose around whatever Phase 3 lands as the public contract surface (`final-design.md "Lens summary"`, `phase-arch-design.md §"Architectural context"`). Three competing lenses proposed three different ABC shapes: performance-first introduced no top-level Transform ABC at all (raw `package.json` mutation registered via YAML manifest); security-first introduced `RecipeRegistry` + `RecipeExecutor` + `LockfilePolicyScanner` without a Transform top-line; best-practices proposed four ABCs (`Transform`, `Validator`, `Recipe`, `RecipeEngine`) plus three registries.

The critic dismantled all three (`critique.md §"Attacks…"`): performance-first leaves Phase 4 with no failure surface to detect-and-fall-back-on and gives Phase 15 no recipe ecosystem to author into; security-first omits the load-bearing `Transform` contract entirely; best-practices proliferates registries against the Phase-0/1/2 single-decorator precedent (`@register_probe`) and risks normalizing "one phase, four registries" sprawl. The synthesis chose best-practices' ABC *shape* but trimmed it to the minimum that survives the four downstream phases (`final-design.md §"Conflict-resolution table"` row "Top-level Transform ABC").

## Options considered

- **No top-level Transform ABC, recipes as YAML data only [P].** Cheapest now. Defeats `production/design.md §2.4` ("recipes as data, engine as code") because the engine *is* the JSON mutation. Phase 4 has no "recipe ran but failed" branch. Phase 15 has nothing recipe-shaped to author.
- **`RecipeRegistry` + `RecipeExecutor` + `LockfilePolicyScanner` as the public contract [S].** Solves the security posture but misses the abstraction that Phase 7 and Phase 15 must extend. The "Transform" concept is implicit, not public.
- **Four ABCs: `Transform` + `Validator` + `Recipe` + `RecipeEngine` [B].** Most explicit. Adds a `Validator` ABC for what is functionally a per-stage pure-function check. Adds a `Recipe` ABC for what is data (YAML). The argument-from-noun-multiplicity sets the wrong precedent for Phase 4–7.
- **Two ABCs only: `Transform` + `RecipeEngine`; validators are functions; recipes are YAML data [synth].** The minimum surface that (a) gives Phase 4 a failure surface, (b) gives Phase 7 a place to add `DockerfileBaseImageSwapTransform` additively, (c) gives Phase 15 a recipe-engine ecosystem to author into, and (d) preserves `recipes-as-data`.

## Decision

**Phase 3 introduces exactly two public ABCs, both frozen at v0.3.0 by snapshot test:**

1. **`Transform`** — modeled byte-for-byte on Phase 1's `Probe` ABC. Fields: `name`, `declared_inputs`, `applies_to_tasks`, `applies_to_languages`, `applies()`, `run()`. `TransformInput(repo_root, worktree_root, branch_name, advisory, recipe, repo_context_path, run_id)` → `TransformOutput(name, diff_path, branch_name, files_changed, confidence, warnings, errors, skipped)`. No `success` field — validators emit `passed` per-signal (facts, not judgments).
2. **`RecipeEngine`** — `apply(recipe: Recipe, repo: Path, ctx: ApplyContext) -> RecipeApplication(diff: bytes, files_changed, engine_stdout, engine_stderr, exit_code)`. Engines are stateless given their context.

**Validators are plain functions** returning `ValidatorOutput(name, passed, stdout_path, stderr_path, duration_ms, confidence, warnings, errors)`. No `Validator` ABC.

**Recipes are YAML data** under `src/codegenie/recipes/catalog/`. No `Recipe` ABC. A `Recipe` Pydantic model defines the schema for the YAML; that is data, not contract.

The `Transform` ABC's public field set is **append-only**: new fields must default to values that preserve v0.3.0 caller behaviour. Breaking changes require an ADR amendment and a sibling-versioned ABC under a deprecation window (`phase-arch-design.md §"Gap analysis" §"Gap 1"`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 4 reads `TransformOutput.errors` + `RecipeSelection.reason` (ADR-0004) for diagnostic context without editing Phase 3 code | The contract is the most consequential review in Phase 3 — once frozen at v0.3.0, every downstream phase composes around it |
| Phase 7 adds `DockerfileBaseImageSwapTransform` purely additively; same registry decorator pattern | The minimum ABC set is opinionated — anyone wanting a `Validator` ABC must show a Phase-3-coverage need it does not solve as a function |
| `recipes-as-data` property preserved — `production/design.md §2.4` honored end-to-end | Recipe YAML schema becomes load-bearing; schema drift is a CI-gated concern |
| Two registries (`@register_transform`, `RecipeEngine` registry) — same pattern as Phase 0/1's `@register_probe` | No `Validator` registry means validators can't be added by decorator at startup; they're called explicitly from `coordinator.py` |
| Snapshot test (`test_transform_contract.py`) freezes the contract; signature drift → CI red — same discipline as Phase 0's `test_probe_contract.py` | The append-only field policy constrains future ABC growth; legitimate breaking changes pay a versioning tax |

## Consequences

- `src/codegenie/transforms/contract.py` defines `Transform` ABC, `TransformInput`, `TransformOutput`.
- `src/codegenie/transforms/registry.py` provides `@register_transform` (mirroring `@register_probe`).
- `src/codegenie/recipes/engine.py` defines `RecipeEngine` ABC.
- `src/codegenie/recipes/models.py` defines `Recipe` Pydantic model (data, not ABC) and `RecipeSelection` (ADR-0004).
- `src/codegenie/transforms/validation/` contains functions, not classes inheriting an ABC.
- `tests/unit/test_transform_contract.py` snapshots the ABC; signature drift fails CI.
- Phase 4's planning coordinator wraps `transforms/coordinator.remediate` on the deterministic-success path; never edits Phase-3 code.
- Phase 7's `DockerfileBaseImageSwapTransform` registers via `@register_transform`; adds a new `RecipeEngine` subclass under `src/codegenie/recipes/engines/`.
- Phase 15's agent-authored recipes are YAML emitted into `catalog/`; the agent never edits Phase 3 code.

## Reversibility

**Low.** Adding a third ABC later (e.g., promoting `Validator` to an ABC) is mechanically possible — but every downstream phase already composes around the two-ABC shape, so adding a third requires (a) refactoring `transforms/validation/` from functions to classes, (b) updating Phase 4–7's wrappers, and (c) re-snapshotting the contract test. Removing one of the two ABCs is even higher cost; the contract is the load-bearing piece. The *internals* of the ABCs (field set, return shape) are append-only-evolvable per the policy above.

## Evidence / sources

- `../final-design.md §"Goals" §"Contract goals"` rows 1–3 — the two-ABC commitment
- `../final-design.md §"Components" #1 "Transform ABC + registry"` and `#2 "RecipeEngine ABC with two impls"`
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Top-level Transform ABC" — the resolution
- `../phase-arch-design.md §"Component design" #1` and `#2`
- `../phase-arch-design.md §"Gap analysis" §"Gap 1 — Cross-phase contract evolution"`
- `../critique.md §"Attacks on the performance-first design" #1` — recipe-engine pick critique
- `../critique.md §"Attacks on the best-practices design" #2` — three-ABC proliferation critique
- [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md) — the precedent
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — POC-to-service contract preservation
