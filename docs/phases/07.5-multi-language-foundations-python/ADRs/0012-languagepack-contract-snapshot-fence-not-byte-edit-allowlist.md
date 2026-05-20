# ADR-0012: The category-based extension-by-addition fence is a contract + snapshot test — not a per-phase byte-edit allowlist

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Contract + snapshot test · fences · extension-by-addition · anti-allowlist-accretion
**Related:** [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md), [ADR-0006](0006-typescript-retrofit-by-reference-probes-self-registered.md), [ADR-0010](0010-conformance-tier-parameterized-over-live-registry.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)

## Context

The roadmap's Phase 7.5 exit criteria include "the category-based fence rejects a planted silent edit" ([`roadmap.md` §"Phase 7.5"](../../../roadmap.md)). The best-practices design realized this as a single `LanguagePack` contract-snapshot test — and the critic attacked it as a *silent downgrade* of a roadmap deliverable ([critique.md §Attacks on the best-practices design, problem 4](../critique.md)): a snapshot of the `LanguagePack` field set does *not* catch a planted silent edit to a Node probe body (the canonical silent edit). The critic argued the design "redefined the deliverable to match what it wants to build."

Re-reading the source documents resolves the apparent contradiction ([final-design.md §Components — `LanguagePack` contract-snapshot fence](../final-design.md#components), CONFLICT CR-9). [ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) commitment 3 *explicitly* states the buildable form of a "did a protected thing change" fence is a per-contract snapshot test — "the probe-ABC pattern" (`tests/unit/test_probe_contract.py` against `probe_contract.v1.json`). The roadmap's own test-architecture table row 7.5(c) says verbatim: new frozen surfaces use "a contract + snapshot test (the probe-ABC pattern), **not allowlist rows**." A *general* semantic-diff category fence is explicitly **deferred** by ADR-0043 as a research project. So the "category-based fence" the roadmap exit criterion names *is* the contract-snapshot test in the roadmap's and ADR-0043's own framing — there is no contradiction to paper over; the best-practices design was correct and merely under-explained the equivalence. This ADR states it explicitly so no future reader re-derives the false contradiction.

## Options considered

- **Option A — a per-phase byte-edit allowlist** enumerating sanctioned edits to "locked" files, policed by a phase-specific fence (Phase 7's `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`). **Pattern:** enumeration accretion — ADR-0043 commitment 2 names Phase 7's as the *last*; another would be a forbidden accretion.
- **Option B — a general semantic-diff "category fence"** that classifies an arbitrary diff as a safe category or not. **Pattern:** machinery ahead of need — ADR-0043 defers it as a research project; a reliable "did behaviour change" differ is not buildable now.
- **Option C — a contract + snapshot test pinning the `LanguagePack` field set + types**, exactly as the probe ABC is pinned. **Pattern:** Contract + snapshot test (the probe-ABC pattern).

## Decision

The Phase 7.5 "category-based extension-by-addition fence" is realized as a **contract + snapshot test** — `tests/fence/test_language_pack_contract.py` pinning the `LanguagePack` field set and types into `tests/fence/snapshots/language_pack_contract.v1.json`, exactly as `tests/unit/test_probe_contract.py` pins the probe ABC. The pack *file* stays freely editable; the snapshot test fails iff the *contract* (field names/types) changed — the desired loud signal when a genuinely new capability category is added. **No allowlist rows are added** — Phase 7's byte-edit allowlist is the last per ADR-0043 commitment 2. The roadmap's "planted silent edit" requirement is exercised at **two levels**: a planted `LanguagePack` field-add → `test_language_pack_contract.py` goes red (the *contract* changed); a planted Node-probe-body change → the full Phase 1–7 regression suite (a hard CI gate) goes red (*behavior* changed). Both levels are in the test plan.

This fence pins the `LanguagePack` contract, which is itself frozen `Provisional Accepted` per [ADR-0001](0001-languagepack-total-frozen-value-contract-and-freeze.md); the snapshot file is `language_pack_contract.v1.json` — the `v1` anticipates a `v2` when the third-language review trigger fires.

## Tradeoffs

| Gain | Cost |
|---|---|
| Per-phase byte-edit allowlist accretion stops — Phase 7's is the last; Phase 7.5 ships the model case ADR-0043 commitment 3 names | The snapshot catches a *`LanguagePack`-contract* change, not an arbitrary silent edit anywhere — it is narrow by design |
| The `LanguagePack` *file* stays freely editable — generalizing the pack instead of cloning it is legal; only the *contract* is frozen | A planted Node-probe-body silent edit is *not* caught by this fence — it is caught by the Phase 1–7 regression gate; "the fence" is two mechanisms, not one |
| A genuine new capability *category* is a loud, reviewable red test — exactly the signal extension-by-addition wants | The snapshot must pin the *right* surface — too much and it is brittle, too little and drift slips through (the contract-identification judgement ADR-0043 names) |
| The probe-ABC pattern is reused verbatim — a proven, buildable form, no new machinery, no research project | A general "did any behaviour change" fence is *not* delivered — that is deferred by ADR-0043, and this ADR is explicit that the roadmap criterion never asked for it |

## Pattern fit

This is the **Contract + snapshot test** pattern — ADR-0043 commitment 3's generalization of the probe-ABC pattern. The toolkit's framing is "small modules with deep interfaces" and "make illegal states unrepresentable" at the *contract* level: a frozen surface is not a frozen *file* (files must stay editable, or generalizing a component becomes illegal) but a frozen *contract* — the field set and types — pinned by a snapshot. The anti-pattern explicitly avoided is the per-phase byte-edit allowlist: ADR-0043 commitment 2 calls Phase 7's the *last*, because an exception list that grows every phase is "a sign the rule is mis-stated" — by Phase 16 there would be 100+ allowlist rows no one can reason about. The other tempting move — a general semantic-diff category fence — is the toolkit's **premature pluggability** at the tooling level: a reliable behaviour-differ is a research project, and ADR-0043 defers it. The contract-snapshot test is the buildable, proven form; this ADR commits to it and names the two-level planted-edit test (contract snapshot + regression gate) as the complete realization of the roadmap criterion.

## Consequences

- Phase 7.5 ships the model case ADR-0043 commitment 3 names — every future frozen surface uses a contract + snapshot test, no allowlist rows.
- A planted `LanguagePack` field-add turns `test_language_pack_contract.py` red — the loud signal when a new capability category is added (the `Provisional Accepted` freeze's review trigger may also fire).
- A planted Node-probe-body silent edit turns the Phase 1–7 regression gate red — the canonical silent edit is caught by the regression suite + review, exactly as ADR-0043 commitment 1 prescribes.
- The roadmap's "category-based fence rejects a planted silent edit" exit criterion is satisfied — and this ADR records that the criterion never required a general semantic-diff fence (ADR-0043 defers that); the equivalence is stated so no future reader re-derives a false contradiction.
- The snapshot file is `language_pack_contract.v1.json` — a `v2` is anticipated when the third `LanguagePack` lands and the contract widens.
- No second per-phase allowlist fence is ever added — Phase 7 story S5-01's guard against a second allowlist fence stands.

## Reversibility

**High.** The fence is a single test file plus a JSON snapshot — adding, removing, or re-scoping it is a localized test-only edit. The durable commitment is the *negative* one: not reintroducing per-phase byte-edit allowlists (ADR-0043 commitment 2). Reverting to allowlists is textually cheap but reinstates the accretion trajectory ADR-0043 exists to stop — increasingly costly as phases accumulate. The contract-snapshot mechanism itself is the proven, low-cost form and there is no reason to reverse it.

## Evidence / sources

- [final-design.md §Components — `LanguagePack` contract-snapshot fence](../final-design.md#components), §Synthesis ledger CR-9, §Failure modes & recovery, §Exit-criteria checklist
- [phase-arch-design.md §Component design — `LanguagePack` contract-snapshot fence](../phase-arch-design.md#component-design), §Goals G9, §Scenarios (Scenario 4), §Testing strategy (adversarial)
- [critique.md §Attacks on the best-practices design, problem 4](../critique.md) — the alleged "silent downgrade" of the category fence; §Roadmap-level critiques 3
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — commitments 2 and 3 (allowlist accretion stops; contract + snapshot test); the general category fence deferred
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — the probe contract pinned by a snapshot test, the exemplar; [`roadmap.md` §"Phase 7.5"](../../../roadmap.md) test-architecture row 7.5(c)
