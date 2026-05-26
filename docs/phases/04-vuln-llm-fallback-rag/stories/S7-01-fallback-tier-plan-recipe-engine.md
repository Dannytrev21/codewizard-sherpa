# Story S7-01 — `FallbackTierPlanRecipeEngine` plugin adapter

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S7-01.md`](_attempts/S7-01.md)). Plugin directory + `FallbackTierPlanRecipeEngine` adapter + pure `_project_plan_outcome_to_recipe_outcome` projector shipped under `plugins/vulnerability-remediation--node--npm/subgraph/`. 10 tests cover AC-PROJECTION-TOTALITY (4 PlanOutcome variants → RecipeOutcome), AC-CTOR (keyword-only frozen dataclass), AC-PROTOCOL-CONFORMANCE (returns RecipeOutcome), AC-NO-EMIT (adapter contributes zero events), AC-FENCE-IMPORT (AST walk rejects anthropic/chromadb/fastembed/onnxruntime), AC-KERNEL-FROZEN (the diff lands only under `plugins/` and `tests/unit/plugin/`; `tests/fence/test_kernel_frozen.py` stays green; lint-imports 12 contracts kept). The plugin module is loaded via `importlib.util.spec_from_file_location` (the hyphenated slug is not Python-identifier-valid). Production triple-extraction from Phase-3 `ApplicationPlan` lands when the Phase-5 `(advisory, repo_ctx, recipe_selection)` contract types harmonize.
**Effort:** M
**Depends on:** S6-01 (`FallbackTier.run`), S1-03 (`PlanOutcome`), S1-02 (`PlanProposal`); Phase-3 plugin `RecipeEngine` Protocol stable
**ADRs honored:** ADR-0002 (FallbackTier pipeline), ADR-0004 (PlanOutcome wraps RecipeOutcome — never widens), ADR-0003 (path-scoped fence), production-ADR-0031 (extension by addition into plugin)

## Validation notes (2026-05-24)

Hardened by `phase-story-validator` before execution. Significant edits applied; full record in `_validation/S7-01-fallback-tier-plan-recipe-engine.md`. Summary of load-bearing fixes:

- **`RecipeOutcome` shape drift (block — fixes from Consistency F1/F2/F3/F4).** Story (and arch §Component 14, ADR-0004) said three variants `Applied | NotApplicable | Failed`; the canonical declaration in `src/codegenie/transforms/outcomes.py` is **four**: `Applied | Skipped | RecipeNotApplicable | RecipeFailed`. The S1-03 validation report already flagged this drift; this story now uses the real variant names. `Applied` carries `(transform_id, plugin_id, recipe_id)` — there is **no** `transform=` field. `RecipeFailed.error` is a structured `RecipeError(error_id, message, details)` — not a free-form `reason: str`.
- **Phase-3 `NotApplicableReason` is closed (block — Consistency F3).** The Literal does **not** include `PROVENANCE_NOT_APP_LAYER` / `LEAF_REFUSED` / `BUDGET_EXCEEDED` / `LEAF_SCHEMA_VIOLATION`. Projecting Phase-4 refused reasons into `RecipeNotApplicable.reason` would either crash Pydantic or widen the Literal — directly violating ADR-0004's "Phase-3 sum type is not widened" invariant and tripping `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`. The new AC-3 projects **all** Phase-4 refused reasons to the single Phase-3-legal value `CVE_NOT_IN_DEPENDENCY_SET`; the rich Phase-4 reason rides on the `PlanOutcomeEmitted` event payload (where `PlanOutcome.Refused.reason` already carries the closed Phase-4 Literal per S1-03).
- **Double-emit of `PlanOutcomeEmitted` (block — Consistency F5).** S6-01's `FallbackTier.run` **owns** the terminal `PlanOutcomeEmitted` event (S6-01 line 29 + happy-path event-tape AC). Adapter emitting a second one would (a) break S6-01's exact `Counter(kinds)` invariant and (b) confuse the inline harvester (S6-03). Rewritten: the adapter emits **no events** — projection is pure; emission is the tier's responsibility.
- **`apply` signature shape (harden — Consistency F8, Design F5).** The Phase-3 `RecipeEngine.apply(repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability)` takes Phase-3 types — not Phase-4 `PlanProposal`. Outline §4's "match plan over PlanProposal variants" was confused dispatch; that match belongs in `FallbackTier.transform_from_plan` (S6-01). Adapter never sees `PlanProposal`; the `match` it owns is over `RecipeApplication` (the tier's return type).
- **10-arg constructor → 2-arg (block — Design F1, Test-Quality F4, Consistency F10).** AC-2 had the adapter assemble `FallbackTier` from 10 substrate deps inline; the TDD plan papered over the resulting non-injectability with a `_with_tier` private-attribute test seam. Replaced with constructor-injected `FallbackTier` (composition root moves to the plugin's `transforms()` factory — that's where TCCM already lives). Adapter shrinks to its actual responsibility: project `RecipeApplication → RecipeOutcome`. The test seam disappears; every substrate dep added by a future S5/S6 amendment touches the plugin factory, not the adapter signature.
- **Functional core / imperative shell promoted to AC (harden — Design F3).** The `_project_recipe_application_to_recipe_outcome(app) -> RecipeOutcome` pure free function was buried in the Refactor block. Promoted to AC-PROJECTION with an AST-walk assertion that the projector has no `await` / `self` / `event_log` references, mirroring `NpmLockfileRecipeEngine._classify_jail_result` (the precedent sibling).
- **`'plan'` raw string → `TransformKind("plan")` (harden — Design F6, Consistency F7).** `Plugin.transforms()` returns `dict[TransformKind, RecipeEngine]`; raw `str` keys don't satisfy `mypy --strict`. The literal `"plan"` now appears at exactly one site (the `TransformKind` construction).
- **Dead-code defense check deleted (harden — Design F4, Consistency F6).** Old AC-8 referenced a non-existent `plan.recipe_selection.task_class` field and added a runtime guard for an invariant the plugin loader already enforces. Deleted per CLAUDE.md "trust internal code and framework guarantees".
- **Test thinness + structural-conformance test (harden — Test-Quality F3/F5/F7/F8/F9).** `assert "PROVENANCE_NOT_APP_LAYER" in out.reason` is mutation-thin; `re: RecipeEngine = engine; assert re is engine` is two no-ops at runtime; `isinstance(out, RecipeOutcome.Applied)` raises `AttributeError` (`RecipeOutcome` is an `Annotated[Union, ...]` alias, not a class). TDD plan rewritten to: import variants directly (`from codegenie.transforms.outcomes import Applied, RecipeNotApplicable, RecipeFailed`), parametrize across **all four** `RecipeApplication` variants, assert exact field equality (not substring), add a subprocess-mypy structural-conformance fixture mirroring S1-03 AC-9, and add a discriminator-mapping totality test mirroring S1-03 AC-11.
- **Determinism + concurrency + unexpected-exception ACs added (harden — Coverage F6/F7/F8).** Cassette-replay determinism, the closed typed-error list (no `except Exception` arm — let unexpected types propagate; `asyncio.CancelledError` unchanged), and reentrancy contract are now explicit ACs.
- **Plugin-directory `--` import resolution (harden — Consistency F8, Coverage F11).** `plugins/vulnerability-remediation--node--npm/` is not a valid Python module name. Story now requires the implementer to document the resolution mechanism (plugin loader / `importlib.util.spec_from_file_location` / re-export shim) and use the same mechanism in the AST-import fence test (AC-FENCE-IMPORT).
- **Path-scoped fence relationship clarified (nit — Consistency F9).** ADR-0003's path-scoped fence covers `src/codegenie/` only; the adapter lives under `plugins/`. The AST-import test on the adapter is therefore the **primary** control, not "defense in depth". Surfaced in Notes for the implementer with a pointer back to ADR-0003 for the longer-term widening question.

Open follow-ups (NOT patched here — out of scope per "do not silently fold in adjacent improvements"):
- ADR-0004 + `phase-arch-design.md §Component 14` / §Process view still say `RecipeOutcome = Applied | Skipped | Failed` (three variants); the canonical four-variant declaration in `outcomes.py` should be the single source of truth. The S1-03 validation report already recommended this correction; this story's `Validation notes` adds a second voice. Resolve under a small doc-amendment PR.
- The `transforms() -> dict[str, RecipeEngine]` Protocol shape (raw `str` keys, not `TransformKind`) is itself a primitive-obsession smell on the Phase-3 kernel; surface to phase-architect.

## Context

Step 7 is the moment Phase 4's substrate becomes addressable from the existing Phase-3 orchestrator. `FallbackTier.run(...)` lives in `src/codegenie/fallback/tier.py` but the orchestrator does not know about it — it dispatches `transforms()[TransformKind("plan")]` against a `RecipeEngine` shape (Phase-3 Protocol). The job of this story is to ship the **Adapter** that conforms `FallbackTier` to that Protocol, projecting Phase-3's `RecipeOutcome` so the orchestrator sees zero new behavior at the type level.

Two non-negotiables: (1) the adapter lives *inside the plugin directory* (`plugins/vulnerability-remediation--node--npm/subgraph/`), not in `src/codegenie/` — per ADR-0031 and the Phase-7 precondition that "the diff touches only the new plugin directory"; (2) the adapter is a **pure projector** — it does not emit events. `FallbackTier.run` itself emits the terminal `PlanOutcomeEmitted` (S6-01 happy-path event-tape AC owns this). Emitting again would (a) break S6-01's exact `Counter(kinds)` invariant and (b) confuse the inline harvester (S6-03). The Phase-4-local `PlanOutcome` is the rich four-variant shape consumed by the harvester via the event log; the projected Phase-3 `RecipeOutcome` is the four-variant shape Phase 3 already declared (`Applied | Skipped | RecipeNotApplicable | RecipeFailed`). The adapter's job is the closed mapping between them, **not** to widen Phase-3's `NotApplicableReason` Literal (ADR-0004 forbids it) — every Phase-4 refused reason maps onto the single Phase-3-legal value `CVE_NOT_IN_DEPENDENCY_SET`, with the rich Phase-4 reason preserved on the tier-emitted `PlanOutcomeEmitted` event.

The adapter is the registered value of `plugin.transforms()[TransformKind("plan")]`; whether the plugin already has a placeholder `plan` engine from Phase 3 (a refuse-only stub) is a question the implementer reads from the existing plugin source first (Global Rule 8). If it does, this story *replaces* it surgically; if it does not, this story adds the slot. The 10-substrate-dependency assembly of `FallbackTier` is the responsibility of the plugin's `transforms()` factory (where TCCM already lives) — the adapter takes a pre-built `FallbackTier` instance, so its constructor stays small and every future substrate-dep amendment touches the plugin factory, not the adapter signature.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 14 — FallbackTierPlanRecipeEngine` — purpose ("zero edits to `src/codegenie/plugins/protocols.py`"), public interface (`apply(repo, plan, capability) -> RecipeOutcome`), internal structure (constructs `FallbackTier` from plugin-resolved adapters; awaits `FallbackTier.run(...)`; projects `RecipeApplication → RecipeOutcome.{Applied,NotApplicable,Failed}`).
  - `../phase-arch-design.md §Logical view` — the `FallbackTierPlanRecipeEngine --> FallbackTier` edge in the component diagram.
  - `../phase-arch-design.md §Process view` — Scenario 2 sequence diagram: `Eng as FallbackTierPlanRecipeEngine`, `Eng-->>Orch: RecipeOutcome.Applied(transform)`.
  - `../phase-arch-design.md §Design patterns applied` row "FallbackTierPlanRecipeEngine returning Phase 3's `RecipeOutcome` shape" — Adapter pattern (not `RecipeEngine` extension).
- **Phase ADRs:**
  - `../ADRs/0002-fallback-tier-pipeline-no-langgraph.md` — `FallbackTier.run` is a `def`, not a LangGraph node; the adapter just awaits it.
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — `PlanOutcome` is consumed by event-emission/harvester only; never widens Phase-3 `RecipeOutcome`; `FallbackTier.run` returns Phase-3's `RecipeApplication`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — adapter must not import `anthropic`/`chromadb`/`fastembed`/`onnxruntime` (those imports live behind the substrate Protocols this adapter composes); the adapter is plugin-side, not under `src/codegenie/fallback/`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin scope; extension by addition; `transforms()['plan']` is the seam.
- **Source design:**
  - `../final-design.md §Component 14` and §"Three load-bearing structural lines" item 3 — why the adapter exists and why it must not widen `RecipeOutcome`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — `Features delivered` first bullet; `Done criteria` bullets on `RecipeOutcome` projection and kernel-frozen invariant.
- **Existing code:**
  - `src/codegenie/plugins/protocols.py` (Phase 3) — `RecipeEngine` Protocol. **Read this; do not edit.**
  - `src/codegenie/fallback/tier.py` (S6-01) — `FallbackTier.run` signature and return shape.
  - `src/codegenie/fallback/plan_outcome.py` (S1-03) — `PlanOutcome` union to emit.
  - `plugins/vulnerability-remediation--node--npm/` — current scaffold; check `transforms()` for any existing `plan` slot.
  - `src/codegenie/plugins/events.py` (Phase 3) — `EventLog` shape for `PlanOutcome` emission.

## Goal

Land `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` exposing `FallbackTierPlanRecipeEngine` that implements Phase-3 `RecipeEngine` over a constructor-injected `FallbackTier`, projects the tier's returned `RecipeApplication` into the **four-variant** Phase-3 `RecipeOutcome` (`Applied | Skipped | RecipeNotApplicable | RecipeFailed`) via a pure free function, and is wired into `plugin.transforms()[TransformKind("plan")]` — with zero edits to `src/codegenie/plugins/protocols.py`, `src/codegenie/transforms/`, `RemediationOrchestrator`, or any Phase-0/1/2/3 kernel file. The adapter emits **no** events (the tier owns `PlanOutcomeEmitted` per S6-01) and **does not widen** `NotApplicableReason` (ADR-0004 — every Phase-4 refused reason projects onto the Phase-3-legal `CVE_NOT_IN_DEPENDENCY_SET`).

## Acceptance criteria

- [ ] **AC-FILE.** `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` exists and defines `class FallbackTierPlanRecipeEngine`. The plugin directory's `--`-separated name (not a valid Python identifier) is resolved to an importable name by the plugin loader; this story documents the resolution mechanism in `plugins/vulnerability-remediation--node--npm/__init__.py`'s docstring (one of: `importlib.util.spec_from_file_location`, a `sys.path` shim, or an underscored re-export package). The same mechanism is used by the AST-import fence test (AC-FENCE-IMPORT) so the test reads the same module the runtime loads.

- [ ] **AC-PROTOCOL-CONFORMANCE.** `FallbackTierPlanRecipeEngine` is structurally assignable to the Phase-3 `RecipeEngine` Protocol from `codegenie.transforms.recipe_engine` (re-exported via `codegenie.plugins.protocols`):
  - **Runtime check:** `assert isinstance(engine, RecipeEngine)` passes — `RecipeEngine` is `@runtime_checkable`.
  - **Static check:** a subprocess-`mypy --strict` fixture mirroring the S1-03 AC-9 idiom asserts the assignability without `cast`. The fixture file (`tests/typecheck/_fallback_plan_engine_conformance.py`) contains `def _probe(e: FallbackTierPlanRecipeEngine) -> RecipeEngine: return e`; mypy `--strict` exits 0. A deliberate-tamper sub-fixture (rename `apply` to `applyy`) is asserted to exit non-zero with a diagnostic mentioning the protocol name.

- [ ] **AC-CTOR.** `FallbackTierPlanRecipeEngine.__init__(self, *, tier: FallbackTier) -> None`. Constructor is pure (no I/O, no event emission). `FallbackTier`'s 10-substrate-dep assembly is the plugin `transforms()` factory's job, **not** the adapter's. No globals, no module-level state. No private test seam (`_with_tier` etc.) — tests inject the stub via the public constructor.

- [ ] **AC-PROJECTION.** A module-level pure free function `_project_recipe_application_to_recipe_outcome(app: RecipeApplication, *, plugin_id: PluginId, recipe_id: RecipeId) -> RecipeOutcome` implements the closed mapping table below. The function has no `self`, no `await`, no `event_log` reference (asserted by an AST-walking test in `tests/unit/plugin/test_fallback_plan_engine_purity.py`). `apply` calls it and is the only impure code in the module. The mapping table is documented as a module-level docstring constant `_PROJECTION_TABLE_DOC: Final[str]` for auditability.

  | `RecipeApplication` variant | `RecipeOutcome` variant | Notes |
  |---|---|---|
  | `Applied(transform=t)` (or whatever S6-01 finalizes for the success variant) | `Applied(kind="applied", transform_id=t.transform_id, plugin_id=<plugin>, recipe_id=<recipe>)` | `plugin_id` from the plugin manifest; `recipe_id` is a Phase-4-local constant (`RecipeId("fallback-tier")`) since the LLM path has no matched recipe. Both are injected at projector call time. |
  | `Refused(reason="PROVENANCE_NOT_APP_LAYER")` | `RecipeNotApplicable(kind="not_applicable", reason="CVE_NOT_IN_DEPENDENCY_SET", considered=[])` | Per ADR-0004 — Phase-4 reasons do **not** widen Phase-3 Literal. The Phase-4 reason rides on the `PlanOutcome.Refused.reason` carried in the `PlanOutcomeEmitted` event (tier-emitted). |
  | `Refused(reason="LEAF_REFUSED")` | `RecipeNotApplicable(kind="not_applicable", reason="CVE_NOT_IN_DEPENDENCY_SET", considered=[])` | Same justification. |
  | `Refused(reason="BUDGET_EXCEEDED")` | `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId("fallback.budget_exceeded"), message="LLM invocation budget exhausted", details=None))` | Structured `RecipeError` per `outcomes.py`. `error_id` matches Phase-1 ADR-0007 dotted-snake-case regex. |
  | `Refused(reason="LEAF_SCHEMA_VIOLATION")` | `RecipeFailed(kind="failed", error=RecipeError(error_id=ErrorId("fallback.leaf_schema_violation"), message=...))` | Same. |

  The projector **never** emits `Skipped` (`Skipped` is the plugin-disabled / registry-skipped lane, owned by `PluginRegistry`, not by engines). A test asserts no `Skipped` is reachable from the projector by parametrizing over every legal input.

- [ ] **AC-EXCEPTIONS.** `apply` catches **only** the closed typed-error tuple `(LeafProtocolViolation, BudgetExceeded, EgressViolation)` raised by `FallbackTier.run` and projects them to `RecipeFailed(error=RecipeError(error_id=ErrorId(f"fallback.{type(e).__name__.lower()}"), message=str(e)))`. Every other exception type — including `RuntimeError`, `KeyError`, `pydantic.ValidationError`, and especially `asyncio.CancelledError` — **propagates unchanged**; no `except Exception` arm. Tests assert (a) a stub raising `RuntimeError("synthetic")` surfaces as `RuntimeError`, (b) a stub raising `asyncio.CancelledError` surfaces as `CancelledError`.

- [ ] **AC-NO-EMIT.** `FallbackTierPlanRecipeEngine.apply` emits **no** events. The terminal `PlanOutcomeEmitted` event is owned by `FallbackTier.run` per S6-01 happy-path event-tape AC. Test: run `apply` against a stub tier whose only side effect is appending a single `PlanOutcomeEmitted` to the event log; assert `event_log.events` count after `apply` equals the count immediately before plus exactly one (the tier's emit) — proving the adapter contributed zero events. A complementary regression test: an implementation that emits an additional event must fail this AC's test.

- [ ] **AC-KERNEL-FROZEN.** The diff lands **only** under `plugins/vulnerability-remediation--node--npm/**` and `tests/{unit,typecheck}/plugin/**`. `tests/fence/test_kernel_frozen.py` (S1-07) is green. A `git diff --name-only origin/main..HEAD` assertion in CI fails if any file under `src/codegenie/{plugins,transforms,coordinator,probes,fallback,vuln_index,output,schema}/` is modified by this PR. Confirms the Phase-7 "diff touches only the new plugin directory" exit-criterion precondition.

- [ ] **AC-TRANSFORMS-KEY.** `plugin.transforms()` returns a `dict[TransformKind, RecipeEngine]` containing the entry `TransformKind("plan"): <FallbackTierPlanRecipeEngine instance>`. The literal `"plan"` appears at exactly one site in plugin source (the `TransformKind` smart-constructor call). The unit test asserts `isinstance(plugin.transforms()[TransformKind("plan")], FallbackTierPlanRecipeEngine)`.

- [ ] **AC-PROJECTION-TOTALITY.** A test asserts the projector covers every `RecipeApplication` discriminator-mapping tag. Mirrors S1-03 AC-11:
  ```python
  from pydantic import TypeAdapter
  from codegenie.fallback.recipe_application import RecipeApplication  # canonical Phase-4 type
  schema = TypeAdapter(RecipeApplication).json_schema()
  discriminated = set(schema["discriminator"]["mapping"])
  assert discriminated == set(_PROJECTION_TABLE.keys())
  ```
  Plus a **subprocess-mypy `assert_never` exhaustiveness fixture** mirroring S1-03 AC-9: deleting any `case` arm in the projector's `match` causes mypy `--strict` to flag the missing arm. (Bare runtime tests miss this — Python evaluates `assert_never` only at runtime, and mypy plugin checking is opt-in.)

- [ ] **AC-FENCE-IMPORT.** AST-walking test (`tests/unit/plugin/test_fallback_plan_engine_imports.py`) asserts `fallback_plan_engine.py` does not import `anthropic`, `chromadb`, `fastembed`, or `onnxruntime`. The walker handles every import shape: `ast.Import`, `ast.ImportFrom` with `module=None` (`from . import x`), `ast.ImportFrom` with `level > 0` (relative imports of submodule names matching the forbidden set), and `ast.ImportFrom` with `names[*].name` matching. The module is loaded via the same plugin-resolution mechanism documented in AC-FILE — not bare `import`. Acknowledges that ADR-0003's path-scoped fence covers `src/codegenie/` only; **this AST test is the primary control for the adapter, not defense-in-depth**, because the adapter sits outside ADR-0003's scope.

- [ ] **AC-DETERMINISM.** Two replay invocations of `apply` against a recorded cassette + identical stub tier produce byte-equal `RecipeOutcome.model_dump_json(sort_keys=True)` output. `transform_id`, `plugin_id`, `recipe_id` are stable across replays (the projector is referentially transparent). Test: `assert apply(...) == apply(...)` via Pydantic JSON dumps.

- [ ] **AC-REENTRANT.** `apply` is reentrant: `await asyncio.gather(engine.apply(...), engine.apply(...))` against two independent stub tiers yields two well-formed `RecipeOutcome` values, and the order of `PlanOutcomeEmitted` events in the (shared, append-only) log equals the order of tier-emit calls. Shared mutable state in collaborators (e.g., a real `LlmInvocationGuard.budget`) is the **caller's** concern and is explicitly out of scope for the adapter's reentrancy contract — documented in the module docstring.

- [ ] **AC-FAIL-LOUD-CONSTRUCTION.** If the adapter is constructed without a `tier` kwarg, `TypeError` fires at construction (keyword-only enforcement); if `tier` is not a `FallbackTier` instance, a `pytest` test asserts the failure mode is loud at first `apply` call (no silent duck-typing pass).

- [ ] **AC-CHECK.** `make check` is clean: `ruff format --check`, `ruff check`, `mypy --strict`, `pytest -q` all green. CI runs on the project's Python matrix (3.11 + 3.12); both pass.

## Implementation outline

1. **Read first (Global Rule 8).** Read `src/codegenie/transforms/recipe_engine.py` (the canonical `RecipeEngine` Protocol — re-exported from `codegenie.plugins.protocols`). Read `src/codegenie/transforms/outcomes.py` to confirm the **four-variant** `RecipeOutcome` shape and the closed `NotApplicableReason` Literal. Read S6-01's `FallbackTier.run` return-type contract — specifically that it emits the terminal `PlanOutcomeEmitted`. Read the Phase-3 plugin's existing `transforms()` to see whether `TransformKind("plan")` is already a key.
2. **Resolve the plugin-import shim first.** The plugin directory `plugins/vulnerability-remediation--node--npm/` contains hyphens which Python identifiers cannot. Inspect the existing plugin loader (Phase-3 S2-04 `PluginResolver`) to confirm the resolution path; document it in `plugins/vulnerability-remediation--node--npm/__init__.py`'s docstring. Settle on one mechanism (e.g., `importlib.util.spec_from_file_location` via the loader) and use the same mechanism in the AST-import fence test. If no shim exists, surface as a Global-Rule-7 conflict before writing the adapter.
3. **Create the adapter module.** `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py`. Imports (all stdlib + first-party; **no** `anthropic`/`chromadb`/`fastembed`/`onnxruntime`):
   ```python
   from __future__ import annotations
   from typing import Final
   from codegenie.fallback.tier import FallbackTier
   from codegenie.fallback.recipe_application import (
       RecipeApplication, Applied as TierApplied, Refused as TierRefused,
   )  # canonical Phase-4 type per S6-01
   from codegenie.fallback.errors import LeafProtocolViolation, BudgetExceeded, EgressViolation
   from codegenie.transforms.outcomes import (
       RecipeOutcome, Applied, RecipeNotApplicable, RecipeFailed, RecipeError,
   )
   from codegenie.transforms.recipe_engine import RecipeEngine
   from codegenie.types.identifiers import ErrorId, PluginId, RecipeId, TransformKind
   ```
4. **Define the pure projector.** Module-level free function — no `self`, no `await`, no `event_log`. Use `match app` over the `RecipeApplication` variants with a final `case _: assert_never(app)` arm. The function is the **functional core**:
   ```python
   _FALLBACK_RECIPE_ID: Final[RecipeId] = RecipeId("fallback-tier")
   _TYPED_ERROR_TO_ID: Final[dict[type[Exception], str]] = {
       LeafProtocolViolation: "fallback.leaf_protocol_violation",
       BudgetExceeded:        "fallback.budget_exceeded",
       EgressViolation:       "fallback.egress_violation",
   }

   def _project_recipe_application_to_recipe_outcome(
       app: RecipeApplication, *, plugin_id: PluginId, recipe_id: RecipeId,
   ) -> RecipeOutcome:
       """Closed mapping table; see AC-PROJECTION."""
       match app:
           case TierApplied(transform=t):
               return Applied(transform_id=t.transform_id, plugin_id=plugin_id, recipe_id=recipe_id)
           case TierRefused(reason="PROVENANCE_NOT_APP_LAYER" | "LEAF_REFUSED"):
               return RecipeNotApplicable(reason="CVE_NOT_IN_DEPENDENCY_SET", considered=[])
           case TierRefused(reason="BUDGET_EXCEEDED"):
               return RecipeFailed(error=RecipeError(
                   error_id=ErrorId("fallback.budget_exceeded"),
                   message="LLM invocation budget exhausted",
               ))
           case TierRefused(reason="LEAF_SCHEMA_VIOLATION"):
               return RecipeFailed(error=RecipeError(
                   error_id=ErrorId("fallback.leaf_schema_violation"),
                   message="LLM emitted an invalid PlanProposal",
               ))
           case _:
               assert_never(app)
   ```
   If S6-01 finalizes its `RecipeApplication.Applied` variant with a different field name than `transform`, update this projector — but **do not** rename the Phase-3 `Applied.transform_id`.
5. **Define the adapter class — imperative shell only.** Two-line `apply`:
   ```python
   class FallbackTierPlanRecipeEngine:
       def __init__(self, *, tier: FallbackTier) -> None:
           self._tier = tier

       async def apply(
           self, repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability,
       ) -> RecipeOutcome:
           # Translate Phase-3 (repo, plan, capability) into the tier's (advisory, repo_ctx,
           # recipe_selection) inputs per the existing Phase-3 plan-shape adapter (this step
           # depends on the Phase-3 (advisory, repo_ctx, recipe_selection) shape; reuse the
           # existing plugin-side translator if present, OR write a thin local one — surface
           # per Rule 7 if neither exists).
           advisory, repo_ctx, recipe_selection = _adapt_phase3_inputs(repo, plan, capability)
           try:
               app: RecipeApplication = await self._tier.run(advisory, repo_ctx, recipe_selection)
           except (LeafProtocolViolation, BudgetExceeded, EgressViolation) as e:
               return RecipeFailed(error=RecipeError(
                   error_id=ErrorId(_TYPED_ERROR_TO_ID[type(e)]), message=str(e),
               ))
           # NOT caught: RuntimeError, KeyError, pydantic.ValidationError,
           # asyncio.CancelledError, every other exception type — propagate unchanged.
           return _project_recipe_application_to_recipe_outcome(
               app, plugin_id=self._plugin_id(), recipe_id=_FALLBACK_RECIPE_ID,
           )
   ```
   The adapter does NOT emit `PlanOutcomeEmitted` — the tier already does, per S6-01.
6. **Wire into `transforms()`.** Update the plugin's entry-point module so its `transforms()` returns `{TransformKind("plan"): FallbackTierPlanRecipeEngine(tier=<TCCM-assembled tier>)}`. The 10-substrate-dep assembly of `FallbackTier(retriever=..., leaf=..., budget=..., fence=..., canary=..., provenance=..., event_log=..., prompt_builder=..., harvester=..., confidence_gate=...)` lives in the plugin's `transforms()` factory (composition root) — NOT inside the adapter. Surface a Global-Rule-7 conflict if the plugin's existing DI shape disagrees.
7. **Tests** (`tests/unit/plugin/test_fallback_plan_engine.py` + `tests/unit/plugin/test_fallback_plan_engine_purity.py` + `tests/unit/plugin/test_fallback_plan_engine_imports.py` + `tests/typecheck/test_fallback_plan_engine_conformance.py`). Inject the stub tier through the public constructor — no `_with_tier` seam. Cover every `RecipeApplication` variant + every typed-error projection + the unexpected-exception propagation contract + the no-emit invariant + cassette-replay determinism + reentrancy.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Six test files, each pinning a distinct failure mode. **None depend on a `_with_tier` private seam** — the stub tier is injected through the public `tier=` kwarg.

**Tier 1 — projection unit tests (`tests/unit/plugin/test_fallback_plan_engine.py`).** Parametrize across every `RecipeApplication` variant; assert exact field equality on the projected `RecipeOutcome` (not substring). Use the canonical Phase-4 `RecipeApplication` shape per S6-01 (final names land in that story; this test imports from `codegenie.fallback.recipe_application`).

```python
# tests/unit/plugin/test_fallback_plan_engine.py
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock
import pytest

from codegenie.fallback.recipe_application import (
    RecipeApplication, Applied as TierApplied, Refused as TierRefused,
)
from codegenie.fallback.errors import LeafProtocolViolation, BudgetExceeded, EgressViolation
from codegenie.transforms.outcomes import (
    RecipeOutcome, Applied, RecipeNotApplicable, RecipeFailed, RecipeError,
)
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.types.identifiers import (
    ErrorId, PluginId, RecipeId, TransformId, TransformKind,
)
# Plugin-loader-resolved import (per AC-FILE); shape depends on the chosen mechanism.
from plugins.vulnerability_remediation_node_npm.subgraph.fallback_plan_engine import (
    FallbackTierPlanRecipeEngine,
    _project_recipe_application_to_recipe_outcome,
    _FALLBACK_RECIPE_ID,
)

_PLUGIN_ID = PluginId("vulnerability-remediation--node--npm")


def _engine(stub_tier: AsyncMock) -> FallbackTierPlanRecipeEngine:
    # Constructor injection only — no private seams.
    return FallbackTierPlanRecipeEngine(tier=stub_tier)


def test_protocol_runtime_isinstance_passes(stub_tier):
    # RecipeEngine is @runtime_checkable; this is the runtime half of AC-PROTOCOL-CONFORMANCE.
    # The static half lives in tests/typecheck/test_fallback_plan_engine_conformance.py.
    engine = _engine(stub_tier)
    assert isinstance(engine, RecipeEngine)


async def test_projects_tier_applied_to_phase3_applied_with_exact_fields(
    stub_tier, repo, plan, cap, transform_fixture,
):
    stub_tier.run = AsyncMock(return_value=TierApplied(transform=transform_fixture))
    out = await _engine(stub_tier).apply(repo, plan, cap)
    assert isinstance(out, Applied)  # NOT `RecipeOutcome.Applied` — that attribute does not exist
    assert out.transform_id == transform_fixture.transform_id
    assert out.plugin_id == _PLUGIN_ID
    assert out.recipe_id == _FALLBACK_RECIPE_ID


@pytest.mark.parametrize(
    "phase4_reason", ["PROVENANCE_NOT_APP_LAYER", "LEAF_REFUSED"],
)
async def test_projects_refused_provenance_or_leaf_to_not_applicable(
    phase4_reason, stub_tier, repo, plan, cap,
):
    stub_tier.run = AsyncMock(return_value=TierRefused(reason=phase4_reason))
    out = await _engine(stub_tier).apply(repo, plan, cap)
    assert isinstance(out, RecipeNotApplicable)
    # Per ADR-0004: Phase-3 Literal is NOT widened. EXACT value (not substring).
    assert out.reason == "CVE_NOT_IN_DEPENDENCY_SET"
    assert out.considered == []


@pytest.mark.parametrize(
    "phase4_reason,expected_error_id",
    [
        ("BUDGET_EXCEEDED",        "fallback.budget_exceeded"),
        ("LEAF_SCHEMA_VIOLATION",  "fallback.leaf_schema_violation"),
    ],
)
async def test_projects_refused_budget_or_schema_to_failed(
    phase4_reason, expected_error_id, stub_tier, repo, plan, cap,
):
    stub_tier.run = AsyncMock(return_value=TierRefused(reason=phase4_reason))
    out = await _engine(stub_tier).apply(repo, plan, cap)
    assert isinstance(out, RecipeFailed)
    assert out.error.error_id == ErrorId(expected_error_id)


@pytest.mark.parametrize(
    "exc_cls,expected_error_id",
    [
        (LeafProtocolViolation, "fallback.leaf_protocol_violation"),
        (BudgetExceeded,        "fallback.budget_exceeded"),
        (EgressViolation,       "fallback.egress_violation"),
    ],
)
async def test_typed_errors_become_failed_with_structured_recipe_error(
    exc_cls, expected_error_id, stub_tier, repo, plan, cap,
):
    stub_tier.run = AsyncMock(side_effect=exc_cls("boom"))
    out = await _engine(stub_tier).apply(repo, plan, cap)
    assert isinstance(out, RecipeFailed)
    assert out.error.error_id == ErrorId(expected_error_id)
    # error.message — not out.reason. RecipeFailed has no `reason` attribute.
    assert "boom" in out.error.message


async def test_runtime_error_propagates_unchanged(stub_tier, repo, plan, cap):
    stub_tier.run = AsyncMock(side_effect=RuntimeError("synthetic"))
    with pytest.raises(RuntimeError, match="synthetic"):
        await _engine(stub_tier).apply(repo, plan, cap)


async def test_cancelled_error_propagates_unchanged(stub_tier, repo, plan, cap):
    stub_tier.run = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await _engine(stub_tier).apply(repo, plan, cap)


async def test_adapter_emits_no_events(stub_tier, event_log, repo, plan, cap, transform_fixture):
    # Per AC-NO-EMIT: the adapter emits zero events. The tier emits exactly one
    # PlanOutcomeEmitted, modelled here as a side effect of stub_tier.run.
    async def _run(*a, **kw):
        event_log.events.append(("PlanOutcomeEmitted",))  # only the tier's emit
        return TierApplied(transform=transform_fixture)
    stub_tier.run = _run
    pre = len(event_log.events)
    await _engine(stub_tier).apply(repo, plan, cap)
    assert len(event_log.events) - pre == 1, "adapter must not contribute additional events"


async def test_apply_is_deterministic_under_cassette_replay(
    stub_tier, repo, plan, cap, transform_fixture,
):
    # Per AC-DETERMINISM: two invocations against the same stub produce byte-equal output.
    stub_tier.run = AsyncMock(return_value=TierApplied(transform=transform_fixture))
    engine = _engine(stub_tier)
    a = await engine.apply(repo, plan, cap)
    b = await engine.apply(repo, plan, cap)
    assert a.model_dump_json() == b.model_dump_json()


async def test_apply_is_reentrant_under_gather(
    repo, plan, cap, transform_fixture,
):
    # Per AC-REENTRANT: two engines with independent stub tiers run in parallel.
    stub_a, stub_b = AsyncMock(), AsyncMock()
    stub_a.run = AsyncMock(return_value=TierApplied(transform=transform_fixture))
    stub_b.run = AsyncMock(return_value=TierRefused(reason="LEAF_REFUSED"))
    out_a, out_b = await asyncio.gather(
        _engine(stub_a).apply(repo, plan, cap),
        _engine(stub_b).apply(repo, plan, cap),
    )
    assert isinstance(out_a, Applied)
    assert isinstance(out_b, RecipeNotApplicable)


def test_construction_without_tier_kwarg_raises_typeerror():
    with pytest.raises(TypeError):
        FallbackTierPlanRecipeEngine()  # tier is keyword-only with no default
```

**Tier 2 — projector purity AST test (`tests/unit/plugin/test_fallback_plan_engine_purity.py`).**

```python
import ast, inspect
from plugins.vulnerability_remediation_node_npm.subgraph import fallback_plan_engine

def _walk_function_body(name: str) -> list[ast.AST]:
    tree = ast.parse(inspect.getsource(fallback_plan_engine))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return list(ast.walk(node))
    raise AssertionError(f"function {name!r} not found")

def test_projector_has_no_await_no_self_no_event_log():
    body = _walk_function_body("_project_recipe_application_to_recipe_outcome")
    assert not any(isinstance(n, ast.Await) for n in body), "projector must be sync (pure)"
    assert not any(isinstance(n, ast.Attribute) and getattr(n.value, "id", "") == "self" for n in body), \
        "projector must not reference self"
    assert not any(
        isinstance(n, ast.Name) and n.id == "event_log" for n in body
    ), "projector must not touch event_log"
```

**Tier 3 — projection-totality test (`tests/unit/plugin/test_fallback_plan_engine_totality.py`) — AC-PROJECTION-TOTALITY.**

```python
from pydantic import TypeAdapter
from codegenie.fallback.recipe_application import RecipeApplication

def test_projector_table_covers_every_recipe_application_discriminator():
    schema = TypeAdapter(RecipeApplication).json_schema()
    discriminated = set(schema["discriminator"]["mapping"])
    # _PROJECTION_TABLE is the dict the projector dispatches over — exposed
    # at module level for inspection (per AC-PROJECTION docstring constant).
    from plugins.vulnerability_remediation_node_npm.subgraph.fallback_plan_engine import (
        _PROJECTION_TABLE,
    )
    assert set(_PROJECTION_TABLE.keys()) == discriminated
```

**Tier 4 — `assert_never` exhaustiveness via subprocess-mypy (`tests/unit/plugin/test_fallback_plan_engine_assert_never.py`).** Mirror S1-03 AC-9:

```python
import subprocess, sys, textwrap

_FIXTURE = textwrap.dedent('''
    from typing import assert_never
    from codegenie.fallback.recipe_application import RecipeApplication, Applied, Refused

    def project(app: RecipeApplication) -> str:
        match app:
            case Applied():   return "applied"
            # case Refused(): return "refused"   # deliberately commented out
            case _: assert_never(app)
''')

def test_missing_match_arm_fails_mypy(tmp_path):
    f = tmp_path / "missing_arm.py"
    f.write_text(_FIXTURE)
    r = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "Refused" in r.stdout or "assert_never" in r.stdout
```

**Tier 5 — AST import fence (`tests/unit/plugin/test_fallback_plan_engine_imports.py`) — AC-FENCE-IMPORT.** Handles `Import`, `ImportFrom` with `module=None`, and `ImportFrom` with `level>0`:

```python
import ast, inspect
from plugins.vulnerability_remediation_node_npm.subgraph import fallback_plan_engine

_FORBIDDEN = {"anthropic", "chromadb", "fastembed", "onnxruntime"}

def test_adapter_does_not_import_any_forbidden_package():
    tree = ast.parse(inspect.getsource(fallback_plan_engine))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _FORBIDDEN, f"`import {alias.name}` is forbidden in the adapter"
        elif isinstance(node, ast.ImportFrom):
            # absolute: `from X import Y`
            if node.module is not None and node.level == 0:
                root = node.module.split(".")[0]
                assert root not in _FORBIDDEN, f"`from {node.module} import ...` forbidden"
            # `from . import Y` (module is None): inspect alias names
            # `from .X import Y` (level>0): inspect both module and alias names
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _FORBIDDEN, (
                    f"`from ... import {alias.name}` (relative or absolute) forbidden"
                )
```

**Tier 6 — protocol structural conformance via subprocess-mypy (`tests/typecheck/test_fallback_plan_engine_conformance.py`).** Subprocess pattern; mirror S1-03 AC-9. The "good" fixture asserts `mypy --strict` accepts assignment without `cast`; the "tampered" fixture (rename `apply` to `applyy`) asserts mypy rejects.

```python
import subprocess, sys, textwrap

_GOOD = textwrap.dedent('''
    from codegenie.transforms.recipe_engine import RecipeEngine
    from plugins.vulnerability_remediation_node_npm.subgraph.fallback_plan_engine import (
        FallbackTierPlanRecipeEngine,
    )
    def _probe(e: FallbackTierPlanRecipeEngine) -> RecipeEngine:
        return e
''')

def test_engine_satisfies_recipe_engine_protocol_under_mypy_strict(tmp_path):
    f = tmp_path / "good.py"
    f.write_text(_GOOD)
    r = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
```

**Red marker:** every test above fails — most with `ImportError` (no `fallback_plan_engine` module yet), the subprocess-mypy tests with mypy's "module not found" diagnostic. Commit the red marker.

### Green — make it pass

Implement per the Implementation outline. The pure projector lands first (simplest to test); `apply` is the 4-line imperative shell that calls it.

### Refactor — clean up

- The projector's `match` is the single dispatch site; if S6-01 amends `RecipeApplication` variant names, only the projector changes — `apply` is untouched.
- Verify `tests/fence/test_kernel_frozen.py` (S1-07) green and the `git diff --name-only` AC-KERNEL-FROZEN assertion clean.
- The `_PROJECTION_TABLE` module-level constant exposed for the totality test is the canonical map; keep it sorted by `RecipeApplication` discriminator tag for diff stability.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` | New `FallbackTierPlanRecipeEngine` adapter + pure projector (the load-bearing artifact). |
| `plugins/vulnerability-remediation--node--npm/__init__.py` | Document the `--`-to-`_` import-resolution mechanism (one line in docstring). Wire `transforms()[TransformKind("plan")] = FallbackTierPlanRecipeEngine(tier=<TCCM-assembled tier>)` via the existing plugin entry-point module. |
| `tests/unit/plugin/test_fallback_plan_engine.py` | TDD red tests + per-variant projection coverage + reentrancy + determinism + propagation. |
| `tests/unit/plugin/test_fallback_plan_engine_purity.py` | AST assertion: projector has no `await` / `self` / `event_log`. |
| `tests/unit/plugin/test_fallback_plan_engine_totality.py` | `_PROJECTION_TABLE.keys() == TypeAdapter(RecipeApplication).json_schema()["discriminator"]["mapping"]`. |
| `tests/unit/plugin/test_fallback_plan_engine_assert_never.py` | Subprocess-mypy: missing `case` arm fails mypy `--strict`. |
| `tests/unit/plugin/test_fallback_plan_engine_imports.py` | AST import fence (handles `from . import`, `level>0`, alias names). |
| `tests/typecheck/test_fallback_plan_engine_conformance.py` | Subprocess-mypy structural-conformance fixture pair (good/tampered). |
| `tests/unit/plugin/conftest.py` | Shared fixtures (`stub_tier`, `event_log`, `repo`, `plan`, `cap`, `transform_fixture`). |

## Out of scope

- Plugin-side `rag_query_builder` (S7-02).
- `vuln_provenance` adapter generalisation (S7-03).
- `plugin.yaml` thresholds and skill templates (S7-04).
- Fixtures (S7-05) and E2E tests (S7-06, S7-07).
- Adversarial corpus (S7-09).
- Final kernel-frozen verification (S7-08) — this story's adapter must not trip the guard, but the guard re-run is its own story.

## Notes for the implementer

- **Adapter pattern (toolkit name)** is the right call — Phase-3 `RecipeEngine` is a `@runtime_checkable` Protocol; structural conformance is the contract. GoF-inheritance would force the kernel to learn a new ABC method — not allowed here.
- **Composition root, not the adapter, owns substrate assembly.** The 10-substrate `FallbackTier(...)` build (retriever, leaf, budget, fence, canary, provenance, event_log, prompt_builder, harvester, confidence_gate) lives in the plugin's `transforms()` factory where TCCM already lives. The adapter's `__init__(*, tier)` takes the pre-built tier. This is **Dependency Inversion** — the adapter depends on the `FallbackTier` *interface* (effectively a Port), not on the substrate dep graph. Bonus: future S5/S6 substrate amendments touch the plugin factory only; the adapter signature is stable.
- **No private test seams.** The previous draft proposed a `_with_tier` private-attribute seam to work around the inline `FallbackTier` construction. With constructor injection, that seam is unnecessary and would itself be an anti-pattern (Service Locator backwards). If you find yourself reaching for one, stop and surface per Global Rule 7.
- **Functional core / imperative shell at the module level.** `_project_recipe_application_to_recipe_outcome` is the pure functional core (the projector); `apply` is the imperative shell (await + try/except). The AST purity test (Tier 2) enforces the split — keep it green by **never** touching `self` or `await` or `event_log` from inside the projector. Mirror sibling precedent at `src/codegenie/transforms/engines/npm_lockfile.py:410-461` (`_classify_jail_result`).
- **`PlanOutcomeEmitted` ownership is the tier's, not the adapter's.** S6-01 line 29 + happy-path event-tape AC own this. If the adapter emits a second one, the harvester (S6-03) sees duplicates and S6-01's exact `Counter(kinds)` invariant breaks. If S6-01 is later amended to move emission ownership, surface the conflict per Global Rule 7 — do NOT silently start emitting from the adapter.
- **`NotApplicableReason` is closed (ADR-0004 — load-bearing).** The temptation to add `PROVENANCE_NOT_APP_LAYER` / `LEAF_REFUSED` to Phase-3's Literal "just to make the projection lossless" is exactly the failure mode this whole phase exists to prevent. Project **all** Phase-4 refused reasons to the single Phase-3-legal value `CVE_NOT_IN_DEPENDENCY_SET`; the rich Phase-4 reason rides on the `PlanOutcome.Refused.reason` carried in the tier-emitted `PlanOutcomeEmitted` event. The fence test `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` is the canary.
- **Path-scoped fence does not cover `plugins/`.** ADR-0003's fence covers `src/codegenie/` only; the adapter lives outside that scope. The AST-import fence test (Tier 5) is therefore the **primary** control for the adapter, not defense-in-depth. If a future audit wants to extend ADR-0003 to `plugins/**`, that's an ADR amendment — out of scope here.
- **`apply`'s exception contract is closed.** Catch exactly `(LeafProtocolViolation, BudgetExceeded, EgressViolation)` from `FallbackTier.run`; every other exception type — `RuntimeError`, `KeyError`, `pydantic.ValidationError`, `asyncio.CancelledError` — propagates unchanged. A bare `except Exception` is a Rule-12 ("Fail loud") violation and would silently swallow programming errors and cancellation.
- **Resist threading `BudgetToken` through the adapter** — it flows `FallbackTier → LeafLlm.invoke` only (ADR-0010, S2-05 import-linter contract). Since the adapter doesn't construct the tier anymore, this is automatic — but if you ever find yourself accepting a `BudgetToken` arg on the adapter, you've drifted.
- **Zero edits to Phase-0/1/2/3 kernel files.** If you're tempted to edit `src/codegenie/plugins/protocols.py`, `src/codegenie/transforms/recipe_engine.py`, or `src/codegenie/transforms/outcomes.py` "to make the projection simpler" — stop. Re-read ADR-0004 + S1-07. The `git diff --name-only` AC (AC-KERNEL-FROZEN) is grep-able.
- **`assert_never` exhaustiveness must use subprocess-mypy.** Runtime `assert_never` only fires at runtime, after the missing arm has already caused the bug. Mypy `--strict` catches the missing arm at lint time — but only if the test actually runs mypy on the broken fixture. Follow the S1-03 AC-9 idiom; do not skip the subprocess test.
- **Plugin-directory `--` separator is a Python identifier hazard.** Resolve in `__init__.py` once and document the mechanism; the AST-import fence test must load the same module via the same mechanism, not via bare `import` (which won't work on a `--`-separated package name).
- **Rule-of-three watch.** `NpmLockfileRecipeEngine` + `OpenRewriteRecipeEngine` + `FallbackTierPlanRecipeEngine` = three `RecipeEngine` implementations. A shared `codegenie.transforms.engine_helpers` projection utility may look tempting, but the three engines project from **different source sum types** (`JailedSubprocessResult` / `JailedSubprocessResult` / `RecipeApplication`). The "similar lines" is the `match … case … assert_never` pattern, which is already idiomatic Python. **Don't extract** — Rule 2 (Simplicity First) and Rule 3 (Surgical Changes) both push back.
