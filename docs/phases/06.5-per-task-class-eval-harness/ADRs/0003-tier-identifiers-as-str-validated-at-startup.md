# ADR-0003: Tier identifiers are `str`, validated at startup against `docs/trust-tiers.yaml`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** extension-by-addition · type-system · contract-data
**Related:** [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md)

## Context

Trust tiers (bronze / silver / gold / platinum) are referenced from `PromotionVerdict.current_tier`, `PromotionVerdict.target_tier`, the `min_cases_for_promotion: Mapping[str, int]` registration argument, and the `docs/trust-tiers.yaml` data file. The three input designs disagreed on the encoding: performance-first used `StrEnum`, security-first used `Literal[...]` per registration, best-practices used `Literal[...]` in three or more Pydantic models plus the YAML *and* an ADR cross-link. All three encodings make the same implicit assumption — that the tier set is closed and Phase 6.5 can enumerate it.

The critic flagged this as a roadmap-level extension-by-addition violation (critic roadmap-level #7): adding a new tier (e.g., `"emerald"` between silver and gold, or `"platinum"` if not present) under any of the three encodings requires editing Pydantic models in `src/codegenie/eval/models.py` *and* the YAML *and* an ADR. That is "extension by editing," not "extension by addition" — the same violation [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) eliminated for signal kinds by widening `TrustSignal.kind` from a closed `Literal` to an open registry-keyed `str`.

The tradeoff at stake is compile-time exhaustiveness vs the load-bearing commitment to extension by addition ([CLAUDE.md §"Extension by addition"](../../../CLAUDE.md)). The fail-loud principle further constrains the choice: if a typo `"silvr"` in a registration silently passes validation and crashes at runtime against an unknown threshold, the system has failed loud at the wrong layer. Validation must happen at startup, against the canonical contract data, with a diagnostic that names both the unknown value and the available options.

## Options considered

- **`Literal["bronze", "silver", "gold", "platinum"]` everywhere** (best-practices). Compile-time exhaustive; mypy catches typos. Adding `"emerald"` is a Pydantic edit, a YAML edit, *and* an ADR amendment. Violates extension by addition (critic roadmap-level #7).
- **`StrEnum`** (performance-first). Single declaration site; readable. Adding a tier is still an enum edit + YAML edit. Mypy treats `Tier.BRONZE` and `"bronze"` as compatible if `StrEnum`, but the enum is still a closed type at the Python layer.
- **`str`, no validation** (none of the inputs proposed). Maximum flexibility; no fail-loud. A typo crashes at threshold-lookup time with a confusing `KeyError`. Rejected.
- **`str`, validated at startup against `docs/trust-tiers.yaml`** (synthesized). The YAML *is* the canonical tier list. `PromotionGate.__init__` loads `TierConfig` and rejects unknown tiers at construction time with `TierConfigInvalid(unknown_tier, available_tiers)`. Adding `"emerald"` is a YAML edit + an ADR amendment to [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) — zero `models.py` edits. Mirrors [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)'s widening pattern.

## Decision

`BenchCase.task_class`, `PromotionVerdict.current_tier`, `PromotionVerdict.target_tier`, and `TaskClass.min_cases_for_promotion: Mapping[str, int]` use plain `str`. Validation lives in `PromotionGate.__init__(tier_config: TierConfig)`: at startup, the gate asserts every tier name referenced in `tier_config.thresholds`, `tier_config.current_tiers`, and every registered `TaskClass.min_cases_for_promotion` exists in `docs/trust-tiers.yaml`. Unknown names raise `TierConfigInvalid(unknown_tier, available_tiers)` at construction time — before any eval runs, before any verdict is computed. `docs/trust-tiers.yaml` is CODEOWNERS-gated (contract data, not configuration).

## Tradeoffs

| Gain | Cost |
|---|---|
| Extension by addition: adding `"emerald"` is one YAML diff + one ADR amendment; zero edits to `src/codegenie/eval/` | Loses compile-time exhaustiveness — mypy will not catch a typo like `"silvr"` at edit time |
| Fail-loud at startup: typos surface as `TierConfigInvalid(unknown_tier="silvr", available_tiers={"bronze","silver","gold","platinum"})` *before* any case runs | Validation is one-shot at `PromotionGate.__init__`; mid-run config drift is not detected (but the config is immutable per process) |
| Mirrors [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)'s open-registry pattern — same discipline reused, lower cognitive cost for readers | Two different "open" patterns coexist now: signal kinds via decorator registry, tiers via YAML-loaded `TierConfig` — readers must understand which is which |
| `docs/trust-tiers.yaml` is the single source of truth for tier identity *and* threshold values — one file, CODEOWNERS-gated, the ADR-0015 calibration ADR can amend it without touching code | If the YAML is unreadable / missing at startup, the gate cannot construct — a deployment-time failure with no fallback |
| The gate's `reasons` tuple can enumerate available tiers in the error message — operator sees the answer to "what tiers exist?" without grepping the codebase | Refactoring tools (rename, find-references) cannot rename a tier across the codebase; the rename is a `git grep` operation across YAML + ADR + docs |

## Consequences

- `src/codegenie/eval/models.py` declares `current_tier: str` and `target_tier: str` on `PromotionVerdict`. No Pydantic `Literal` for tiers.
- `src/codegenie/eval/promotion.py` ships `TierConfig` as `@dataclass(frozen=True)` with `thresholds: Mapping[str, float]` and `current_tiers: Mapping[str, str]`. Both loaded from `docs/trust-tiers.yaml` at CLI startup.
- `PromotionGate.__init__` validates that every key in `thresholds` and every value in `current_tiers` plus every key in every registered `min_cases_for_promotion` are members of the YAML's declared tier set. Unknown tier → `TierConfigInvalid` at startup.
- Adding a new tier is a four-part change: (a) edit `docs/trust-tiers.yaml` to add the tier + threshold; (b) update `current_tiers` for any task class that should move; (c) write or amend a Phase 6.5+ ADR; (d) [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) amendment if the change carries calibration data. Zero `models.py` edits, zero `promotion.py` logic edits.
- The fence-CI is silent on tier names — it does not enumerate the closed tier set. The runtime startup check is the load-bearing structural enforcement.
- Future task classes (Phase 7 migration, Phase 15 recipe authoring) may declare `min_cases_for_promotion={"bronze": 10, "silver": 25, "gold": 50}` with whatever tier slugs are valid at registration time. Unknown slugs fail at startup with a tier-not-in-YAML diagnostic.
- The pattern composes with [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)'s signal-kind registry: signal kinds are *code* (decorator-registered), tiers are *data* (YAML-declared). Both open, both fail-loud, different substrates.

## Reversibility

**Medium-low.** Reverting to `Literal[...]` is a one-file diff in `models.py` but breaks every `TaskClass` registration in `bench/*/registration.py` that declared a tier slug the closed Literal does not include — the change is breaking for every consumer that has registered a non-canonical tier. The contract decision (tier set is open, validated at startup against canonical data) is durable; the encoding is mechanically reversible but the surface-area cost is real. Once Phase 7 ships with a `min_cases_for_promotion` Mapping keyed on tier slugs, reverting requires either narrowing the slug set Phase 7 may use or rewriting Phase 7's registration.

## Evidence / sources

- [final-design.md §Departures from all three inputs #3](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Synthesis ledger row "Tier identifiers"](../final-design.md#conflict-resolution-table)
- [phase-arch-design.md §Data model](../phase-arch-design.md#data-model) ("Tier names are `str`, not `Literal[...]`")
- [critique.md §Roadmap-level critiques #7](../critique.md#roadmap-level-critiques)
- [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) — `@register_signal_kind`'s widening of `TrustSignal.kind` from `Literal` to `str`; this ADR mirrors the discipline for tier slugs
- [CLAUDE.md §"Extension by addition"](../../../CLAUDE.md)
- [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) — the calibration ADR that owns the threshold values this ADR's YAML carries
