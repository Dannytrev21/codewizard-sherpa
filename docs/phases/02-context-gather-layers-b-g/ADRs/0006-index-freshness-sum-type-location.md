# ADR-0006: `IndexFreshness` sum type lives at `codegenie.indices.freshness` with one Phase-2 consumer

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** typing · sum-type · domain-modeling · open-closed · schema-with-consumer · honest-confidence
**Related:** 02-ADR-0007, [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0032](../../../production/adrs/0032-language-search-adapters.md), [production design.md §2.3 honest confidence](../../../production/design.md)

## Context

[Production design.md §2.3](../../../production/design.md) names "Honest confidence" as a load-bearing commitment and `IndexHealthProbe` (B2) as its canonical example in the POC. Silent index staleness is the worst failure mode of the entire system: a `RepoContext` slice that *says* it's current but isn't propagates wrong evidence through every downstream consumer. The roadmap's Phase 2 exit criterion is operational: a deliberately-seeded `stale-scip` fixture in `tests/fixtures/portfolio/` must be caught by B2; build FAILS otherwise. The probe is what makes the commitment real.

All three input lenses proposed the same concept under three different names:
- **Performance lens — `AdapterConfidence = Trusted | Degraded(reason) | Unavailable(reason)`**, used for both probes and adapters. Critic finding #3 attacked this as conflating ADR-0033's prescription for ADR-0032 *adapter outputs* (Phase 3) with Phase 2's *probe outputs*.
- **Security lens — `IndexConfidence`**, B2-only. Localized but collides with the human-readable `confidence: "high" | "medium" | "low"` flat string the `localv2.md §5.2 B2` slice already carries.
- **Best-practices lens — `IndexFreshness = Fresh | Stale(reason: StaleReason)`** with four `StaleReason` variants (`CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`). One name, one module, but the proposed module location (`codegenie.indices.freshness`) was **away from** `IndexHealthProbe` itself — defended on grounds that Phase 8 Bundle Builder and ADR-0032 adapters would import it without pulling in the probe registry.

The critic (`critique.md §"Attacks on the best-practices design" #6`) attacked the location choice: Phase 8 doesn't exist yet, ADR-0032 adapters don't exist yet (Phase 3 owns them), so the import-direction argument is hypothetical and the layout decision is speculative. **Co-location in `probes/index_health.py` is the boring default until the second consumer exists.** All three lenses also shared blind spot #1 — pre-shipping a sum type whose only real consumer is the probe that defines it.

The synthesis (`final-design.md §"Components" #1, #2`, §"Conflict-resolution table" row 3, row 11, §"Shared blind spots considered" #1) made two choices: (1) pick `IndexFreshness` as the name; (2) close the schema-without-consumer gap by shipping **one Phase-2-internal consumer** — `src/codegenie/report/confidence_section.py`, which renders a `CONTEXT_REPORT.md` Confidence section by pattern-matching every `IndexFreshness` value with `assert_never`. With a real consumer, the separate-module location earns its keep: the renderer must import `IndexFreshness` without pulling in the probe registry (the renderer runs alongside, not inside, the gather coordinator). The `--warn-unreachable` per-module mypy flag on the renderer makes a missed `match` arm a build error from day 1.

`AdapterConfidence` is a separate concern owned by Phase 3 (ADR-0032). Phase 2 ships `AdapterConfidence = Trusted | Degraded(reason) | Unavailable(reason)` in `codegenie/adapters/confidence.py` as a **placeholder** — the variant set is owned by Phase 3 when the first adapter ships (the placeholder gives Phase 3 a typed target without binding the eventual shape).

## Options considered

- **Option A — `AdapterConfidence` used for both probes and adapters.** **Pattern:** Sum type, but conflated. Performance lens's pick. Contract conflation — probes and adapters have different output contracts; one type for both forces Phase 3 adapter authors to inherit shape constraints set by Phase-2 probes.
- **Option B — `IndexConfidence` B2-only, co-located in `probes/index_health.py`.** **Pattern:** Sum type, narrowly scoped. Security lens's pick. Name collides with the human-readable `confidence: high|medium|low` string; if Phase 3+ adapters need an analogous shape, they'd need a parallel sum type.
- **Option C — `IndexFreshness = Fresh | Stale(reason)` in a separate module (`codegenie.indices.freshness`), with **no Phase-2 consumer**.** Best-practices lens's initial proposal. Critic-attacked as schema-without-consumer + speculative-import-direction.
- **Option D — `IndexFreshness = Fresh | Stale(reason)` in `codegenie.indices.freshness`, with **one Phase-2 consumer** (`report/confidence_section.py` rendering CONTEXT_REPORT.md), `--warn-unreachable` per-module mypy enforcement, and `AdapterConfidence` as a separate placeholder in `codegenie.adapters.confidence` (Phase 3 owns the variant set).** **Pattern:** Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer. Synthesis pick.

## Decision

Adopt **Option D**. `IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]` lives at `src/codegenie/indices/freshness.py` (the only file in the `codegenie.indices` package for Phase 2). The four `StaleReason` variants are `CommitsBehind(n, last_indexed)`, `DigestMismatch(expected, actual)`, `CoverageGap(files_indexed, files_in_repo)`, `IndexerError(message)`. The Phase-2 consumer is `src/codegenie/report/confidence_section.py`, which pattern-matches every `IndexFreshness` value via `match` + `assert_never`. `mypy --warn-unreachable` is enabled per-module on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**` — a missed `case` is a build error. `AdapterConfidence` is a **placeholder** sum (`Trusted | Degraded(reason) | Unavailable(reason)`) at `codegenie/adapters/confidence.py`; the variant set is owned by Phase 3 (revisable when the first adapter ships). **Pattern: Sum type + Make-illegal-states-unrepresentable + schema-paired-with-consumer.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Three competing names ([P]'s `AdapterConfidence` / [S]'s `IndexConfidence` / [B]'s `IndexFreshness`) collapse to **one** name, **one** module, **one** Phase-2 consumer. The "what does freshness mean here?" question has one answer | The separate `indices/` package adds one more top-level directory under `src/codegenie/` (Phase 1 added `parsers/`; Phase 2 adds `indices/`, `adapters/`, `tccm/`, `skills/`, `conventions/`, `depgraph/`, `report/` — package count grows; critic [B] finding #1 noted the ratchet risk) |
| Schema-with-consumer discipline survives — the renderer is real code (not test scaffolding) that exercises every variant on every gather; the variant set is rehearsed continuously | The consumer is *one* module; if the variant set is wrong (e.g., a fifth `StaleReason` is needed), discovery is at Phase 3 land time, requiring an ADR amendment here. Mitigation: Gap 3 improvement adds `@register_index_freshness_check(index_name)` so new index sources extend B2 by addition, not edit |
| `mypy --warn-unreachable` per-module catches a missed `case` at build time on the renderer — exhaustive `match` is enforced, not asserted | Per-module config in `pyproject.toml` (`[[tool.mypy.overrides]]` blocks) — six modules opt in (the listed set); Phase 0/1 modules don't get the discipline. Full-repo rollout is a tracked backlog item |
| `AdapterConfidence` as a placeholder gives Phase 3 a typed target without locking it — the variant set is revisable when the first adapter ships, owned by Phase 3 author | A Phase 3 adapter author may want `AdapterConfidence` to layer over `IndexFreshness` (e.g., "adapter is `Degraded` because its underlying index is `Stale(CommitsBehind(17))`"). Phase 2 does not pre-decide the layering; Phase 3 owns it |
| Phase 3 adapters import `IndexFreshness` without pulling in the probe registry — the renderer is the proof; the import-direction argument is no longer hypothetical | A future "render report from cache without re-running probes" workflow (Phase 9? Phase 13?) is the second real consumer Phase 2's argument anticipated; Phase 2 has only one consumer today |
| Discriminated-union variants are Pydantic-modeled (`frozen=True, extra="forbid"`); round-trips through `model_dump_json` ↔ `model_validate_json` identity-equal (property test) | Pydantic's discriminator-field discipline requires a `Literal["..."]` `kind` field on every variant — slight verbosity vs. a dataclass-based sum, but the JSON round-trip is what consumers need |
| The probe's flat string `confidence: "high" | "medium" | "low"` (slice shape per `localv2.md §5.2 B2`) is derived from the typed value — backward compat preserved at the slice surface | Two representations of the same fact exist at the slice boundary: the typed `IndexFreshness` (for in-process consumers) and the flat string (for `repo-context.yaml`'s human reader). The renderer is the source of truth for the typed value; the flat string is derived |

## Pattern fit

Pattern: **Sum type + Make-illegal-states-unrepresentable** (`design-patterns-toolkit.md §"Tagged union / sum type for state"`, §"Make illegal states unrepresentable", [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) §3–4). The toolkit's prescription — "model state machines, failure-mode taxonomies, edge classifications as discriminated unions; avoid booleans for state" — is honored exactly: `Fresh(indexed_at)` vs `Stale(reason)` is the binary status; the `StaleReason` discriminator captures the *why*, never collapsing to `Optional[str]`. The pattern's failure mode the toolkit warns against ("booleans for state — `is_pending: bool, is_running: bool, is_done: bool` instead of `Status = Literal["pending","running","done"]`") is avoided. Composes with **Schema-with-consumer** (the toolkit's anti-pattern "premature pluggability" generalized to types — "schema before consumer"): the renderer is the consumer that earns the type. Composes with [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)'s newtype + smart-constructor discipline at the variant level (e.g., `CommitsBehind.n: int` is constructed; round-trip identity is tested).

## Consequences

- `src/codegenie/indices/freshness.py` is the single file in `codegenie.indices` for Phase 2. `__init__.py:__all__ = ["IndexFreshness", "Fresh", "Stale", "StaleReason", "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError"]`.
- `src/codegenie/report/confidence_section.py` consumes `IndexFreshness` via exhaustive `match`. Every golden-file test exercises this renderer.
- `pyproject.toml` per-module mypy config enables `--warn-unreachable` on `codegenie.{indices, probes/index_health.py, report, adapters, tccm}/**`. Phase 0/1 modules don't get the flag (Rule 3 — surgical changes); full-repo rollout is a tracked backlog item (Open Q §5).
- `src/codegenie/adapters/confidence.py` ships `AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]` as a **placeholder**, with a module docstring stating "Phase 3 plugin may extend; revise on first concrete adapter."
- `tests/unit/indices/test_freshness.py` asserts round-trip identity (`model_dump_json` → `model_validate_json` = identity) and exhaustive `match` test with `assert_never`. A missing case is a `mypy --warn-unreachable` build error in `confidence_section.py`.
- `tests/property/test_index_freshness_roundtrip.py` (Hypothesis) — any `IndexFreshness` round-trips identity-equal.
- A Phase 3 adapter that needs a fifth `StaleReason` variant requires an ADR amendment to this one (named-trigger discipline mirroring 02-ADR-0002). The `assert_never` in the renderer is the structural enforcement: silent extension via Pydantic `Union` widening is impossible without breaking the renderer's exhaustive match.
- Gap 3 improvement (`@register_index_freshness_check(index_name: IndexName)` decorator-registry in `freshness.py`) closes the Open/Closed gap for new index sources: Phase 3+ adds new index types by **new file + new decorator**, never by editing B2's `run()` method. The decorator-registry pattern symmetry with `@register_probe` and `@register_dep_graph_strategy` is itself a documentation win.

## Reversibility

**Medium.** Renaming `IndexFreshness` to something else later (e.g., `AdapterConfidence` after Phase 3 discovers the shapes are the same) is a `git grep` rewrite — name change, consumer rewrite, exposed in `__all__`. Collapsing the separate `indices/` module into `probes/index_health.py` is a file move + import-path rewrite; the renderer would then need to import from `probes/`, which couples the renderer to the probe registry. The harder reversal is **losing the typed sum** in favor of `Optional[str]` — that's a regression on [production design.md §2.3](../../../production/design.md)'s honest-confidence commitment and a load-bearing test failure (`test_stale_scip_fixture.py` asserts typed `Stale(reason=CommitsBehind(...))`). The typed-sum direction is one-way by Phase 2 commitment.

## Evidence / sources

- `../final-design.md §"Components" #1 IndexHealthProbe`, §"Components" #2 `IndexFreshness sum type module` — name + module + consumer rationale
- `../final-design.md §"Conflict-resolution table" row 3, row 11` — name selection + module location
- `../final-design.md §"Shared blind spots considered" #1` — schema-without-consumer fix
- `../phase-arch-design.md §"Component design" #1, #2` — load-bearing-citizen framing; consumer requirement
- `../phase-arch-design.md §"Data model"` — Pydantic discriminated-union shape
- `../phase-arch-design.md §"Gap analysis & improvements" Gap 3` — `@register_index_freshness_check` Open/Closed extension
- `../critique.md §"Attacks on the best-practices design" #6` — module-location attack and synthesis response
- `../critique.md §"Attacks on the performance-first design" #5` — `AdapterConfidence` conflation attack
- [Production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) §3–4 — make-illegal-states-unrepresentable discipline
- [Production ADR-0032](../../../production/adrs/0032-language-search-adapters.md) — Phase 3 adapter contract that `AdapterConfidence` placeholder anticipates
- [Production design.md §2.3](../../../production/design.md) — honest confidence commitment
