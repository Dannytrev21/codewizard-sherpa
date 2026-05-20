# ADR-0014: A `RecipeEngine` surfaces its produced `Transform` via a per-workflow `TransformRegistry`

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** registry · contract · open-closed · dependency-inversion · engine-layer-unblock
**Related:** [0001](0001-ship-phase5-contract-surface-by-name.md), [0009](0009-recipe-engine-protocol-with-two-implementations-day-1.md), [0010](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [0002](0002-plugin-registry-kernel-instance-with-default-singleton.md)

## Context

S5-01 shipped the `RecipeEngine` Protocol GREEN on 2026-05-19 at `src/codegenie/transforms/recipe_engine.py:67-91`:

```python
@runtime_checkable
class RecipeEngine(Protocol):
    async def apply(
        self, repo: SandboxedPath, plan: ApplicationPlan,
        capability: NpmInstallCapability,
    ) -> RecipeOutcome: ...
```

`apply` returns a single `RecipeOutcome` discriminated-union value. Its `Applied` variant (`outcomes.py:190-199`) carries `transform_id: TransformId` — a BLAKE3-hex digest — and no `Transform` object. The `Applied` docstring and the `Transform` ABC docstring both name "the S1-04 `Transform` registry" as the lookup mechanism for the produced artifact, but **no such registry was ever built** — S1-04 shipped only the `Transform` ABC (`transform.py`).

This gap blocked the whole engine layer. The phase-story-validator's harden pass on S5-02 (`NpmLockfileRecipeEngine`) and S5-03 (`OpenRewriteRecipeEngine`) independently (a) strengthened an AC to require a `mypy --strict` `RecipeEngine`-Protocol-conformant `apply`, and (b) rewrote `apply` to return a 2-tuple `(RecipeOutcome, Transform | None)` so the engine could hand the `Transform` back to the orchestrator. Those two corrections contradict: `tuple[RecipeOutcome, Transform | None]` is not covariantly assignable to `RecipeOutcome`, so `_engine: RecipeEngine = NpmLockfileRecipeEngine(...)` fails `mypy --strict`. Both stories were marked **BLOCKED** on 2026-05-20 (`_attempts/S5-02.md`, `_attempts/S5-03.md`, cross-story `_lessons.md` #16/#17). No engine, no orchestrator, no end-to-end path can land until the question is answered: **how does a `RecipeEngine` surface its produced `Transform` object?**

The orchestrator genuinely needs the object: S6-04's Phase-5 wrap seam is `async def _validate_stage6(transform, ctx)` — it takes the `Transform`, not the id. Phase 5's `GateContext.transform_output: Transform` is typed against the ABC.

## Options considered

- **Option A — Change `RecipeEngine.apply` to return `tuple[RecipeOutcome, Transform | None]`.** **Pattern:** none — a return-shape widening. Rejected: `RecipeEngine` and `RecipeOutcome` are the ADR-0001 Phase-5 frozen contract surface (ADR-0009 froze the Protocol). A tuple return is not assignable to `RecipeOutcome`; every `_engine: RecipeEngine = ...` site breaks `mypy --strict`. This *is* the S5-02/S5-03 contradiction — adopting it would re-freeze a self-inconsistent surface.
- **Option B — Add a `transform: Transform` field to the `Applied` variant.** **Pattern:** richer sum-type variant. Rejected: `Applied` is a `frozen=True, extra="forbid"` Pydantic `RecipeOutcome` variant frozen by ADR-0001; `Transform` is an ABC (deliberately not Pydantic — ADR-0001 §Tradeoffs, Phase-5 ADR-0006) with `diff_bytes: bytes`, so it has no clean serialization into a `RecipeOutcome` that flows to `remediation-report.yaml` on disk. The id-as-lookup-key was a deliberate progressive-disclosure choice (production design §"Progressive disclosure for context").
- **Option C — Introduce a `TransformRegistry`; `apply` returns plain `RecipeOutcome`, the orchestrator looks the `Transform` up by `Applied.transform_id`.** **Pattern:** Registry + Dependency inversion. The mechanism the `Applied`/`Transform` docstrings already name; adds capability by *addition* (new module + new story) with zero edits to the ADR-0001/0009 frozen surface.

## Decision

Adopt **Option C.** A new `TransformRegistry` (`src/codegenie/transforms/transform_registry.py`, shipped by story **S5-01b**) is the sanctioned channel by which a `RecipeEngine` surfaces its produced `Transform` to the orchestrator.

- `RecipeEngine.apply(...) -> RecipeOutcome` is **unchanged** — the ADR-0001/ADR-0009 frozen surface is preserved verbatim.
- A `RecipeEngine` is **constructor-injected** with a `TransformRegistry`. On a successful apply the engine calls `transform_registry.register(transform)` and returns `Applied(transform_id=transform.transform_id, ...)`.
- The `RemediationOrchestrator` (S6-04) constructs **one `TransformRegistry` per workflow run**, injects it into every engine it builds, and after `apply` returns `Applied` retrieves the object via `transform_registry.get(applied.transform_id)` to feed `_validate_stage6(transform, ctx)`.
- The registry is keyed by `TransformId` (= BLAKE3-hex of `diff_bytes`). `register` raises `TransformAlreadyRegistered` on a duplicate id; `get` raises `TransformNotFound` on a miss — both typed markers subclassing `CodegenieError`, mirroring `RecipeRegistry`'s `RecipeAlreadyRegistered` / `RecipeNotFound`.

**Per-workflow injection, not a process-wide `default_*` singleton.** Unlike `@register_probe` / `@register_recipe`, which register at *import* time into a process-wide `default_registry`, `Transform`s are registered at *runtime* — once per `apply` call. A process-wide singleton would accumulate every workflow's transforms, leak across runs, and need garbage collection. A per-workflow `TransformRegistry`, created by the orchestrator and discarded when `run()` returns, has no global mutable state and no GC surface. The engine module (`transforms/engines/*.py`) therefore keeps its S5-02 AC-Surface-4 fence — "no module-level mutable state" — intact.

**Not a Phase-5 contract symbol.** The `TransformRegistry` is an internal orchestration mechanism, not one of ADR-0001's six named seams. It is **not** re-exported from `codegenie/transforms/__init__.py` and is **not** part of the S6-06 contract snapshot — consumers import it directly (`from codegenie.transforms.transform_registry import TransformRegistry`), mirroring the `sandbox_jail.py` / `recipe_registry.py` precedent for `transforms/`-resident, non-contract-surface modules.

## Tradeoffs

| Gain | Cost |
|---|---|
| The ADR-0001/0009 frozen `RecipeEngine` / `RecipeOutcome` / `Applied` surface is untouched — Phase 5 still wraps the surface it was promised | One more object on the engine constructor (`jail`, `transform_registry`); S5-02/S5-03's `__init__` widens from 1-arg to 2-arg |
| Realizes the design intent already written into the `Applied` and `Transform` docstrings ("lookup into the S1-04 Transform registry") rather than inventing a parallel shape | A two-step `apply` → `get` dance in the orchestrator instead of a one-line tuple destructure |
| Per-workflow scoping — no global mutable state, no cross-workflow leakage, no GC story; functional-shell-friendly | The orchestrator must thread one more object through engine construction |
| Unblocks S5-02 → S5-03 → S5-04 → S6-* by *addition* (new module + new story), the codebase's standing extension discipline | A new story (S5-01b) is inserted into Step 5, shifting the backlog count 43 → 44 |

## Pattern fit

Implements the **Registry pattern** (toolkit §Registry pattern) — the sixth registry in the codebase, the first keyed by a content digest and the first scoped per-workflow rather than process-wide. Implements **Dependency inversion** (toolkit §Composition / coupling): the engine depends on the `TransformRegistry` abstraction passed to its constructor, never on a concrete orchestrator. Preserves **Open/Closed at the contract boundary** — the `RecipeEngine` Protocol is closed for modification; the new capability arrives as an added collaborator. The registration site is the engine's `apply`; the lookup site is the orchestrator — a clean **functional-core / imperative-shell** seam.

## Consequences

- New module `src/codegenie/transforms/transform_registry.py` exposing `TransformRegistry`, `TransformAlreadyRegistered`, `TransformNotFound` — shipped by story **S5-01b** (`S5-01b-transform-registry.md`), slotted between S5-01 and S5-02 in the Step-5 dependency chain.
- **S5-02 and S5-03 are de-contradicted:** `apply` reverts to the as-built `-> RecipeOutcome`; the harden-pass 2-tuple correction is withdrawn; `__init__` widens to `(jail, transform_registry)`; AC-Apply-1 / AC-Contract-1 assert the produced `Transform` is retrievable from the injected registry by `Applied.transform_id`. Both stories return from `BLOCKED` to `HARDENED`. The DAG gains `S5-01b` between `S5-01` and `S5-02`/`S5-03`.
- S6-04's `RemediationOrchestrator` constructs the per-workflow `TransformRegistry`, injects it into engines, and looks the `Transform` up after `apply` for `_validate_stage6`.
- The `TransformRegistry` is **not** added to `codegenie/transforms/__init__.__all__` and **not** snapshotted by S6-06 — it is not a Phase-5 contract symbol.
- New invariant: a `RecipeEngine` implementation never returns a `Transform` object across the `apply` boundary; the only sanctioned channel is `transform_registry.register(...)` + an `Applied(transform_id=...)` outcome.

## Reversibility

**Medium.** The `TransformRegistry` is an internal mechanism — replacing it (e.g., if a future phase makes `Transform` Pydantic-serializable and prefers Option B) touches the engine constructors, the orchestrator's lookup, and story S5-01b, but **not** the ADR-0001 frozen surface and **not** any persisted artifact. No multi-phase coordination is required; the blast radius is the engine layer plus the orchestrator's `apply_recipe` node.

## Evidence / sources

- `_attempts/S5-02.md` Blocker A — the root contradiction and the three-option analysis this ADR resolves.
- `_attempts/S5-03.md` Blocker A / `_attempts/_lessons.md` #16, #17 — the same contradiction across the engine cone; "the fix for the whole cone is one architecture decision, not N executor retries".
- `src/codegenie/transforms/recipe_engine.py:67-91` — the as-built `RecipeEngine` Protocol (`apply -> RecipeOutcome`).
- `src/codegenie/transforms/outcomes.py:190-199` — the `Applied` variant carrying `transform_id` and naming "the S1-04 `Transform` registry".
- `src/codegenie/transforms/transform.py:64-96` — the `Transform` ABC whose docstring names the registry.
- `src/codegenie/plugins/recipe_registry.py` — the typed-error-marker + `register`/`get` registry shape this module mirrors.
- [ADR-0001](0001-ship-phase5-contract-surface-by-name.md) §Decision / §Consequences — the six frozen Phase-5 symbols this decision preserves.
- [ADR-0009](0009-recipe-engine-protocol-with-two-implementations-day-1.md) — the frozen `RecipeEngine` Protocol.
