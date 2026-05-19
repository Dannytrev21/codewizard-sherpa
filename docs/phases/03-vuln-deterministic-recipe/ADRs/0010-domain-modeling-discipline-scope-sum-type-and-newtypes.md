# ADR-0010: Domain-modeling discipline — `PluginScope` as `Concrete | Wildcard` sum type; newtype every domain identifier; tagged-union outcomes everywhere

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** typing · domain-modeling · sum-type · newtype · illegal-states-unrepresentable
**Related:** [0003](0003-plugin-resolution-and-universal-fallback-semantics.md), [0009](0009-recipe-engine-protocol-with-two-implementations-day-1.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

Production ADR-0033 commits the system to **domain-modeling discipline**: newtypes on every domain identifier, smart constructors on external-boundary parsers, tagged-union sum types for state machines, "make illegal states unrepresentable" everywhere it's not aesthetically expensive. Phase 3 is the first phase where this discipline lands across a *plugin contract* — so the choices made here ossify into every future plugin.

The best-practices lens design explicitly **declined** the sum type for `PluginScope` dimensions: it proposed `PluginScope.task_class: NewType("TaskClass", str) | Literal["*"]` with the rationale "YAML still writes `*`" (best-practices design §Open questions #1). The critic correctly attacked this in `critique.md §Best-practices design — concrete problems`: `NewType("Language", str) | Literal["*"]` collapses to `str` at runtime — the typechecker sees `str` and offers zero help; the resolver's `if dim == "*"` branch is back. ADR-0033 beats YAML aesthetics.

Similarly, the critic flagged missing newtypes on `WorkflowId`, `BundleId`, `TransformId`, `EventId` across all three lens designs (`critique.md §Design-pattern critiques §Missed patterns`). A `WorkflowId` ↔ `BundleId` swap at any call site is a runtime bug the type checker cannot catch when both are raw `str`.

And the critic attacked the best-practices' `RecipeProtocol.applies(cve, ctx) -> bool` (open Q #5): a boolean return for "does this recipe match?" cannot carry the `plan` that the engine needs to apply the recipe nor the `reason` the orchestrator needs to escalate — `Applies(plan) | NotApplies(reason)` sum type is the correct shape.

## Options considered

- **Option A — `PluginScope.task_class: str` with `*` as a magic string; raw `str` for `WorkflowId` / `BundleId` / etc.; `bool` returns on state-machine methods (`applies`, etc.).** **Pattern:** Stringly-typed identifiers + boolean flags on state machines — the toolkit's textbook anti-patterns.
- **Option B — `PluginScope.task_class: NewType("TaskClass", str) | Literal["*"]`; newtypes on some identifiers; `bool` for `applies()`; tagged unions for outcomes only.** Best-practices' compromise. Looks safer; collapses to `str` at runtime where the safety would matter. **Pattern:** Newtype, partially applied.
- **Option C — `PluginScope.task_class: ScopeDim = Concrete | Wildcard` (true sum type); newtype every domain primitive (`PluginId`, `RecipeId`, `WorkflowId`, `BundleId`, `EventId`, `TransformId`, `CveId`, `PackageId`, `BranchName`, `BlobDigest`, `RegistryUrl`, `SignalKind`); tagged-union on every state machine (`PluginResolution`, `RecipeOutcome`, `RemediationOutcome`, `TrustOutcome`, `AdapterConfidence`, `JailedSubprocessResult`, `Applicability`); smart constructor on every external-boundary parser (`PluginManifest.from_yaml`, `PluginScope.parse`, `CveRecord.parse_{nvd,ghsa,osv}`, `BranchName.parse`) returning `Result[T, ParseError]`. **Pattern:** Domain-modeling discipline applied uniformly.

## Decision

Adopt **Option C.** Phase 3 ships:

1. **`PluginScope` dimensions as a true sum type:**
   ```python
   @dataclass(frozen=True, slots=True)
   class Concrete: value: str
   @dataclass(frozen=True, slots=True)
   class Wildcard: pass
   ScopeDim: TypeAlias = Concrete | Wildcard
   ```
   YAML serialization writes `*` and `<concrete>` strings via the smart constructor; runtime never sees `str` masquerading as a dim.

2. **Newtype every domain identifier** under `src/codegenie/types/identifiers.py`: `PluginId`, `RecipeId`, `TransformId`, `WorkflowId`, `EventId`, `CveId`, `PackageId`, `BranchName`, `BlobDigest`, `RegistryUrl`, `SignalKind`, `PrimitiveName`, `TransformKind`, `AttemptNumber`.

3. **Tagged-union sum types on every state machine:** `PluginResolution`, `RecipeOutcome` (`Applied | Skipped | NotApplicable | Failed`), `RemediationOutcome` (`Validated | RequiresHumanReview | NotApplicable | Failed`), `TrustOutcome`, `AdapterConfidence` (`Trusted | Degraded(reason) | Unavailable(reason)`), `JailedSubprocessResult` (`Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded`), `Applicability` (`Applies(plan) | NotApplies(reason)`), `ScopeDim`. Every dispatch site uses `match` + `assert_never`.

4. **Smart constructors on every external-boundary parser** returning `Result[T, ParseError]`: `PluginManifest.from_yaml`, `PluginScope.parse`, `CveRecord.parse_{nvd,ghsa,osv}`, `BranchName.parse(s)` enforcing `^[a-z0-9/_.-]+$`, `PackageId.parse`.

## Tradeoffs

| Gain | Cost |
|---|---|
| `WorkflowId` ↔ `BundleId` swap is a mypy error at the call site; the type checker is doing real work | ~14 newtype declarations + smart constructors — boilerplate. Mitigated by central `identifiers.py` module |
| `ScopeDim = Concrete \| Wildcard` makes "did the wildcard match?" a `match` discriminator, not an equality check on a magic string | YAML readers / writers need a `parse(s)` smart constructor for the `*` / `<concrete>` lift — one helper, low cost |
| Tagged unions on every outcome — `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)` carries the reason Phase 4 reads; boolean returns would lose the structured information | `match` blocks at every dispatch site — verbose but exhaustive. `assert_never` catches missed variants at mypy time |
| Smart constructors returning `Result[T, ParseError]` (per [Phase 5 ADR-0006 convention](../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md)) — callers handle parse errors at the boundary, not at every use site | A small `Result` type / convention; not in stdlib. Pydantic's `model_validate` is the idiom for most cases |
| Best-practices' open question #5 (`RecipeProtocol.applies(...) -> bool`) is resolved structurally: `applies(cve, bundle) -> Applicability = Applies(plan) \| NotApplies(reason)` | Recipe authors must construct the plan eagerly even if it's discarded — acceptable cost; the plan is cheap |
| `extra="forbid"` + `frozen=True` on every Pydantic model means any model drift fails CI at the contract layer | Adding a field is an explicit ADR-worthy change; some changes that would be additive in a loose model become structural changes here. Treated as a feature, not a bug |
| Phase 5 and Phase 7 inherit the discipline mechanically — the patterns are uniform | First-time authors must learn the conventions; documentation in this ADR + design-patterns toolkit reference |

## Pattern fit

Implements four toolkit patterns simultaneously:

- **Newtype pattern** (§Structural / typing patterns): every domain identifier wrapped — "swapping a `RepoId` for a `PRNumber` because both are `str`. Type checker can't help. Newtypes make this a compile-time error."
- **Tagged union / sum type for state** (§Structural / typing patterns): every state machine modeled as a discriminated union; rejects "booleans for state" anti-pattern.
- **Smart constructor** (§Structural / typing patterns): external-boundary parsers return `Result[T, ParseError]`; raw constructors private.
- **Make illegal states unrepresentable** (§Structural / typing patterns): `ScopeDim = Concrete | Wildcard` instead of `str | Literal["*"]` — the impossible state ("`*` AND a concrete value") can't be constructed.

## Consequences

- `src/codegenie/types/identifiers.py` centralizes every newtype; a fence test (`tests/fence/test_no_raw_str_for_domain_ids.py`) AST-walks for raw `str` annotations on parameters named `*_id` / `*_digest` / `*_kind` / etc. and fails CI.
- `src/codegenie/plugins/scope.py` ships `ScopeDim`, `Concrete`, `Wildcard`, `PluginScope.parse`, `PluginScope.matches`, `PluginScope.specificity` with `match`-based dispatch.
- `tests/unit/plugins/test_scope.py` exercises `Concrete | Wildcard` algebra; property test on `specificity` partial order.
- Every Pydantic model in `src/codegenie/{plugins,transforms}/` uses `model_config = ConfigDict(frozen=True, extra="forbid")`.
- `dict[str, Any]` is banned under `src/codegenie/{plugins,transforms}/` and `plugins/` by `tests/fence/test_no_any_in_plugin_surface.py` (S1-05 — landed under the manifest name `test_no_any_in_plugin_surface.py`, NOT `test_no_any_in_contract_layer.py`).
- Phase 4 / 5 / 6 / 7 plugins inherit the discipline — TCCM YAML readers go through smart constructors; recipe `apply()` returns `RecipeOutcome` tagged unions; new identifiers go in `identifiers.py`.
- `TrustSignal.details: dict[str, str | int | bool | float]` — primitives only; not `dict[str, Any]`.

## Reversibility

**Low.** Removing newtypes is mechanical (alias to `str`), but every callsite that benefited from the type-checker discrimination would silently degrade. Demoting tagged unions to boolean flags would lose the structured information consumers depend on (especially Phase 4 reading `NotApplicable(reason)`). The chosen discipline is hard to undo cleanly; that's the point.

## Evidence / sources

- `../phase-arch-design.md §Component design C3` + §Data model, §Design patterns applied rows 4–5, §Patterns considered and deliberately rejected
- `../final-design.md §Synthesis ledger rows "PluginScope wildcard encoding"` (score 14/15), "`RecipeProtocol.applies` signature" (score 15/15), §Pattern reconciliation rows (Newtype, Tagged union, Smart constructor, Make illegal states unrepresentable)
- `../critique.md §Best-practices design — concrete problems` (`Literal["*"]` collapse to `str`), §Design-pattern critiques §Missed patterns (`WorkflowId`/`BundleId` newtype gap)
- [production ADR-0033 — domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
- design-patterns-toolkit.md §Newtype, §Tagged union, §Smart constructor, §Make illegal states unrepresentable

## Amendments

### 2026-05-18 — `AdapterConfidence` canonical home + advisory Literal catalogs

**Context.** `Trusted` / `Degraded` / `Unavailable` plus an `AdapterConfidence` discriminated union were declared in two locations: `src/codegenie/adapters/confidence.py` (Phase 2, `reason: str`, 8 consumers including TCCM loader and the four adapter Protocols) and `src/codegenie/transforms/outcomes.py` (Phase 3, `reason: Literal[DegradationReason]` / `Literal[UnavailabilityReason]`, 0 src consumers but 5 test files pinning the contract). The two `reason` taxonomies were *empirically disjoint*: Phase 2 callers emit `"scip_unavailable"`, `"tool_missing"`, `"self_check"`, `"scip_offline"`, `"stale_scip_acceptable_for_self_check"`; Phase 3's Literal set was `"timeout" | "partial_results" | "rate_limited"` / `"binary_missing" | "io_error" | "unsupported_version"`. Zero overlap. The class-name collision was silent type drift: Phase 3's `BundleBuilder` (S3-04) was documented to consume `transforms.outcomes.AdapterConfidence`, while every existing adapter consumed the `adapters.confidence` version. Once S3-04 landed, the two paths would dispatch through different class objects.

**Decision.** Single canonical class hierarchy declared in `codegenie.transforms.outcomes` (kernel-tier, satisfies `tests/unit/transforms/test_outcomes_purity.py` allowlist). `codegenie.adapters.confidence` re-exports the same class objects — identity equality across both layers. `Degraded.reason` and `Unavailable.reason` widen from `Literal[...]` to `str` (Phase 2's empirically-shipped vocabulary is admitted).

`DegradationReason` and `UnavailabilityReason` survive as **advisory orchestrator-domain Literal catalogs**, NOT field types. The aliases continue to be exported and exercised by `tests/unit/transforms/test_outcomes.py::test_reason_literal_sets_pinned`. Orchestrator consumers (`BundleBuilder` S3-04 and any later gate) MAY validate `degraded.reason in get_args(DegradationReason)` and emit a `degraded_with_unknown_reason` audit event when an out-of-catalog reason arrives — this is the documented migration ramp toward strict reasons if a consumer later demonstrates the cost of free-form strings.

**Tradeoffs.** Eliminates the duplication bug before S3-04 ships; preserves all 8 Phase-2 consumers unchanged; preserves Phase 3's S1-03 test contract (Literal members still pinned by membership tests). Cost: Phase 3's `reason` field loses its type-level enforcement — a typo like `Degraded(reason="netwrok_denied")` now constructs successfully and propagates downstream. Mitigation: advisory-catalog validation at the orchestrator boundary is the explicit migration ramp; the Open/Closed direction (tighten later) remains intact.

**Reversibility.** High. Re-narrowing `reason: str` to `reason: DegradationReason` is a one-line type change at the canonical site, conditional on auditing the actual emitted reasons across the codebase and expanding the Literal set to cover them. This amendment does not foreclose the tightening; it defers it to a consumer that pays for it.

**Consequences.**

- `codegenie.transforms.outcomes` is the single declaration site for `Trusted`/`Degraded`/`Unavailable`/`AdapterConfidence`. `codegenie.adapters.confidence` is now a pure re-export module (no class declarations; allowed by `tests/unit/adapters/test_protocols.py::test_adapter_modules_are_pure_typing` because `codegenie.transforms` is not in the forbidden-prefix set).
- S1-03 story file amended at AC-6, AC-7e, AC-7f to reflect `reason: str` + advisory-catalog framing; `_validation/S1-03-tagged-union-outcomes.md` carries the post-validation amendment.
- Phase 2's typed-surface invariant (02-ADR-0007: "Phase 2 ships Protocols + `AdapterConfidence`, never implementations") is honored — the typed surface is still shipped, just from a single source.
- Future amendments to the Literal catalogs (additive members) require an ADR amendment; field-type tightening (`reason: str` → `reason: Literal[...]`) requires a dedicated story + audit.
- Latent ``codegenie.types.identifiers`` ↔ ``codegenie.probes`` import-cycle uncovered while landing the dedup: `types.identifiers` re-exported `PackageManager` from `probes.node_build_system` at module top-level. The transitive chain `probes/__init__ → layer_b/dep_graph → depgraph/registry → types.identifiers.PackageManager` formed a real cycle whenever an outside-`probes` module loaded `types.identifiers` first (which now happens for every `transforms.outcomes` import that comes in via `adapters.confidence`). Fixed by: (a) `types/identifiers.py` resolves `PackageManager` via a module-level `__getattr__` lazy re-export (TYPE_CHECKING import keeps the static-typing contract); (b) `depgraph/registry.py` moves its `PackageManager` import to a TYPE_CHECKING block (no runtime use thanks to `from __future__ import annotations`); (c) `probes/layer_b/dep_graph.py` imports `PackageManager` from the canonical origin module `codegenie.probes.node_build_system` directly (which `probes/__init__.py` finishes loading before reaching `layer_b/dep_graph`). The Phase-1 ADR-0013 "single owner" contract is preserved — `probes.node_build_system` still owns the `Literal`. The test `test_package_manager_imported_from_types_identifiers` is renamed to `test_package_manager_imported_from_canonical_source` and accepts either source.

**Sources.**

- `tests/unit/transforms/test_outcomes_purity.py:_ALLOWED_IMPORT_ROOTS` — kernel-tier constraint forcing the canonical home to be `outcomes.py`.
- `tests/unit/adapters/test_protocols.py::test_adapter_modules_are_pure_typing` — adapter-tier constraint admitting `codegenie.transforms` imports.
