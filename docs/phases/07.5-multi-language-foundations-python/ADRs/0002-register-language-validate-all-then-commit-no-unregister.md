# ADR-0002: `register_language` is validate-all-then-commit with build-then-publish — no `unregister`, no two-phase commit

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Build-then-publish (staging-then-swap) · Registry · Open/Closed at the file boundary · atomicity · extension-by-addition
**Related:** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md), [ADR-0006](0006-typescript-retrofit-by-reference-probes-self-registered.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

`register_language()` is the one new privileged operation of Phase 7.5: it fans a validated `LanguagePack` into three *existing* decomposed registries — `@register_probe`, `@register_dep_graph_strategy`, and (validate-only) the grammar `_DISPATCH` dict. The three lens designs disagreed sharply on its failure semantics (CONFLICT CR-2 in [final-design.md §Synthesis ledger](../final-design.md#synthesis-ledger)), and the critic named this "the disagreement that matters most for this phase" ([critique.md §Which disagreement matters most](../critique.md)):

- The **security** design wanted a two-phase commit with rollback — but the critic showed the substrate cannot deliver it: `@register_probe` and `DepGraphRegistry.register` (`src/codegenie/depgraph/registry.py`) are append-only, duplicate-loud, and have *no `unregister`*. A two-phase commit names a prepare/abort protocol the registries do not implement.
- The **best-practices** design shipped a flat `for probe_cls in pack.layer_a_probes: register_probe(probe_cls)` fan-out — which the critic showed *crashes on its own first input*: the TypeScript pack's probes already self-registered when their Phase 1 modules imported, so re-registering raises `ProbeError`.
- The **performance** design's straight-line fan-out had the same partial-write hazard with no rollback.

Adding `unregister` to the shipped registries to support rollback would itself be an [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)-forbidden *silent behavior edit* to Phase 1–3 kernel code. So the design cannot have true rollback, and must not pretend to.

## Options considered

- **Option A — two-phase commit with rollback across the three registries.** Stage all writes, commit-all or abort-all. **Pattern:** Two-phase commit — and pattern-as-decoration here: it names an abort protocol the append-only substrate cannot provide. Building it requires editing shipped registries (silent edit, ADR-0043-forbidden).
- **Option B — straight-line fan-out, no rollback, no validation gate.** Call `register_probe` / `register_dep_graph_strategy` in sequence; a mid-sequence failure leaves the kernel half-written. **Pattern:** none — and it ships a known partial-failure hazard.
- **Option C — validate-everything-first, then commit; build-then-publish for the language registry.** `validate_pack()` runs *all* checks before *any* registry write; the language registry write adds the pack to a fresh copy of the dict then swaps it in atomically; the probe/strategy fan-out runs only after validation passes. **Pattern:** Build-then-publish (staging-then-swap) + Registry + Open/Closed at the file boundary.

## Decision

`register_language()` is **validate-all-then-commit**, *not* two-phase commit. `validate_pack(pack)` runs every check — totality, grammar-wired, adapter-import-resolves, no-shadow — *before any registry write*; any failure raises `LanguageRegistryError` with **nothing written**. The language registry write uses **build-then-publish**: the pack is added to a fresh copy of the registry dict, then the copy is swapped in (atomic at the Python-object level). The probe/strategy fan-out into the two append-only registries runs only after validation passes. **No `unregister` is added** to any shipped registry. The one irreducible residual — a mid-fan-out crash on a *genuinely new* pack — is contained, not eliminated: it occurs at import, before any gather, fails the process loudly, and is covered by a unit test asserting the partial state is detectable.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honest atomicity over an append-only substrate — build-then-publish gives the *language registry* real atomicity without a fake abort protocol | The probe/strategy fan-out into the two append-only registries is *not* atomic — a mid-fan-out crash leaves them partly written |
| Zero silent edits to shipped Phase 1–3 registries — no `unregister` bolted onto kernel code | True rollback is impossible by construction; the residual is accepted, not fixed |
| `validate_pack` runs all checks before any write — a collision or un-wired grammar is loud *before* the kernel is touched | A genuinely new pack with a probe-3-of-5 crash needs an import-fix-and-reimport, not an automatic recovery |
| The residual is bounded to process startup, before any gather — it can never silently under-analyze a repo | A unit test must explicitly assert the partial state is detectable; the containment relies on import-time fail-fast, not a clean abort |
| `register_language` stays a *pure addition* — one new function, three existing registries keep their single responsibilities | The function's correctness depends on `validate_pack` being genuinely exhaustive; an under-specified check (e.g. no-shadow, see Gap 1) weakens the guarantee |

## Pattern fit

The toolkit's **Registry pattern** says "keep it dumb; validate on use" — and **Open/Closed at the file boundary** says a new feature should be new files plus a loud collection-point edit, never an edit to existing dispatch code. `register_language` honors both: it is a fan-out across three single-responsibility registries, and a new language is new files plus one import line. The atomicity question is where the critic's "missed pattern" applies: the buildable form of atomicity over an *append-only* substrate is not **Two-phase commit** (which needs an abort protocol) but **Build-then-publish** — construct the new state complete, then swap the reference. The synthesis adopts build-then-publish for the one registry it owns (the language registry) and is honest that the two it merely fans into cannot be made atomic without an ADR-0043-forbidden edit. Naming "two-phase commit" for a substrate with no abort would be pattern-as-decoration — the anti-pattern the critic flagged in the security design.

## Consequences

- The append-only registries (`@register_probe`, `DepGraphRegistry`) stay untouched — Phase 1–3 kernel code is not edited, and the green regression suite keeps meaning what it means.
- `register_language` is idempotent per `Language` — re-registering the same pack is a no-op; tests can re-import freely.
- A `validate_pack` failure names the offending field/key *and* both colliding call sites — a developer locates the conflict without re-running.
- The no-shadow check reads the **live `default_probe_registry`** (not just registered packs) so it catches collisions with Phase 2–7 probes that belong to *no* pack — see [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-analysis--improvements); the check runs only for `probes_self_registered=False` packs.
- An explicit decision is recorded *not* to add `unregister` — the partial-fan-out residual is an accepted, contained risk, not an oversight. A future need for `unregister` is a separate ADR and a sanctioned migration.
- The `PackageManager`-key no-shadow check reads `DepGraphRegistry` and runs for *every* pack — verify at implementation time whether Node strategies are pre-registered via the plugin layer (open question 6, [phase-arch-design.md §Open questions](../phase-arch-design.md#open-questions-deferred-to-implementation)).

## Reversibility

**Medium.** The validate-all-then-commit shape is cheap to keep and cheap to extend (a new check is a new line in `validate_pack`). Adding true rollback later would require either an `unregister` on the shipped registries (a sanctioned migration, not a casual edit) or a larger build-then-publish staging layer spanning all three registries — feasible but a real piece of work. Reverting to a straight-line fan-out would reintroduce the partial-write hazard the ADR exists to contain. The decision *not* to add `unregister` is the most durable part: reversing it is an explicit migration with its own ADR.

## Evidence / sources

- [final-design.md §Components — `register_language()`](../final-design.md#components), §Synthesis ledger CR-2, §Departures item 3, §Risks #3, §Pattern reconciliation (two-phase commit rejected, build-then-publish added)
- [phase-arch-design.md §Component design — `register_language()` + `validate_pack()`](../phase-arch-design.md#component-design), §Process view, §Gap analysis Gap 1
- [critique.md](../critique.md) — "Which disagreement matters most"; security two-phase-commit attack; best-practices flat-fan-out crash; missed pattern (build-then-publish)
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — `unregister` would be a silent edit to shipped kernel code
- [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) — the decomposed-registry / Open-Closed idiom this fans into
