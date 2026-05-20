# ADR-0043: Extension by addition means "no silent edits"

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** architecture · extension-by-addition · fences · contracts · migrations
**Related:** ADR-0007, ADR-0028, ADR-0031, ADR-0033, ADR-0039

## Context

"Extension by addition" is a load-bearing commitment ([design.md §2](../design.md), commitment 5): adding a new language, task type, or tool must not require edits to existing plugins or stable existing behaviour. In practice the rule conflates three different things under one word — *contracts* (interfaces many components depend on), *invariants* (properties that must hold), and *components/implementations* (code that does work). Freezing the first two is correct; freezing the third is not, and taking "no edits" literally has produced three problems:

1. **Per-phase byte-edit allowlists do not scale.** Phase 7 ([Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md)) enumerates ten sanctioned byte-edits to "locked" Phase 0–6.5 files, policed by a phase-specific fence. If every phase adds its own list, by Phase 16 there are 100+ allowlist rows across a dozen fence tests and no one can reason about what is actually protected. An exception list that grows every phase is a sign the rule is mis-stated.
2. **Some edits are loud and compiler-policed — and those are not the danger.** Adding a member to a closed `Literal`, a field to a frozen struct, or an import line to a collection point is a *textual* edit but a *semantic* addition: the compiler (`mypy --strict`) or a snapshot test forces every consumer to confront it. The failure mode the commitment exists to prevent is the *silent*, behaviour-changing edit — a changed function body, a flipped default, a loosened validation — that forces re-verification of everything downstream.
3. **There is no sanctioned path for legitimate horizontal change.** Some cross-cutting changes are necessary and correct — a security fix touching every probe, a logging-format migration, a new required confidence sub-field. The literal rule has no concept of a loud, reviewed, all-at-once sweep distinct from a silent edit, so such work either fights the rule or is avoided — producing parallel near-duplicate components instead of one refactor.

## Options considered

- **Option A — status quo.** Keep "no edits" literal; keep enumerating per-phase byte-edit allowlists. Rejected: does not scale (problem 1) and still has no horizontal-change path (problem 3).
- **Option B — relax the discipline.** Allow edits to existing code with ordinary review. Rejected: destroys the property that makes a green regression suite *mean something* — if existing code can be silently edited, "Phase 3 tests still pass" is weak evidence, and the parallel/agentic execution model (`phase-story-executor`) loses its near-zero-merge-conflict guarantee.
- **Option C — reframe to "no silent edits" + contract-snapshot freezing + a sanctioned migration path.** Keep the freeze where it earns its rent (contracts, invariants, security boundaries); make a protected surface a *contract with a snapshot test* rather than a *frozen file*; give horizontal change an explicit, conformance-gated path. Chosen.

A general *category-based fence* (a tool that classifies an arbitrary diff as a "safe category" or not) was considered as the replacement for per-phase allowlists and rejected as machinery built ahead of need: the buildable, proven form of "did a protected thing change" is a per-contract snapshot test (the probe ABC already works this way), not a general edit-classifier. See **Deferred** below.

## Decision

Extension by addition means **no *silent* edits**, not "no edits." Five concrete commitments:

1. **Restate the rule.** An edit is a violation only when it changes existing behaviour *silently*. Edits the compiler or a snapshot test fully polices — adding a `Literal`/`Enum` member, a field to a frozen struct, an import line to a collection point, a schema `$ref` — are the enforcement mechanism, not violations. They are loud, bounded, and reviewable, and need no special ceremony.
2. **Stop the per-phase allowlist accretion (negative commitment).** Phase 7's ten-row byte-edit allowlist ([Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md)) is the **last** per-phase enumerated allowlist. No future phase adds allowlist rows or a new per-phase allowlist fence.
3. **A frozen surface is a contract with a snapshot test — going forward only.** What replaces the allowlists is the probe-ABC pattern, generalised: a protected surface is a *contract* pinned by a snapshot test (`tests/unit/test_probe_contract.py` against `probe_contract.v1.json` is the exemplar). The file stays freely editable; the snapshot test fails iff the frozen contract changed. Files and components are not frozen — contracts are. This is a **forward rule**: existing Phase 0–7 surfaces are not retrofitted.
4. **Add a sanctioned "migration" concept.** A *migration* is a loud, reviewed, all-at-once horizontal sweep across existing code — explicitly labelled, with the conformance suite and golden files as the safety net. It is the legitimate path for cross-cutting change and is distinct, by construction and by review treatment, from a silent edit.
5. **Freeze discipline.** Freeze only *narrow* contracts — never broad components. Freeze only when *earned* — a surface that has survived ~3 phases of stable use — or state plainly why an early freeze is necessary. Freeze *provisionally*: a freeze ADR uses `Provisional Accepted` with a `Review trigger`, reusing the existing ADR machinery.

This refines [ADR-0039](0039-extension-by-addition-allows-bounded-core-primitives.md); 0039's bounded-additive-primitive carve-out stands unchanged. ADR-0043 governs *what counts as an edit*.

## Deferred — explicitly not part of this decision

These were considered and are deliberately **not** built now; build each only when the triggering problem actually bites, shaped by the real case:

- **A general category-based / semantic-diff fence.** A reliable "did behaviour change" differ is a research project; the buildable form is the per-contract snapshot test in commitment 3, added with each new frozen surface.
- **A codemod harness for migrations.** Build it when the first real migration appears.
- **Contract-versioning / adapter-shim machinery.** Build it when the first contract genuinely needs a `v2`.
- **A capability registry / DI refactor of `ProbeContext`.** `ProbeContext` carries three optional capabilities today; flat optionals are fine until ~6+. Revisit then.

## Tradeoffs

| Gain | Cost |
|---|---|
| Per-phase allowlist accretion stops — Phase 7's is the last; nothing accretes across Phases 8–16 | The contract-snapshot approach requires correctly *identifying* what your contracts are — snapshot too much → brittle, too little → drift slips through |
| Loud compiler/snapshot-policed edits are no longer mislabelled as violations — the discipline matches reality | "No silent edits" requires judgement ("is this edit silent?") where "no edits" was mechanical |
| Files and components become freely editable — generalising a component instead of cloning it is now legal | Non-contract code is protected only by the regression suite + review, not a fence |
| Horizontal change has a real, conformance-gated path instead of fighting the rule | A "migration" is a heavier review artefact than an addition — intentionally |
| Green regression suite keeps meaning what it means (Option B's loss is avoided) | Existing docs that say "never edit existing code" must be reworded (design.md §2, CLAUDE.md, contributing.md, roadmap.md) |

## Consequences

- Phase 7's `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (per [Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md)) is the **terminal** per-phase allowlist; Phase 7 story S5-01 carries a guard asserting no second per-phase allowlist fence is ever added. ADR-0009's statements about Phase 8+ extending the fence are superseded.
- Going forward, any phase that freezes a surface ships a contract + snapshot test (the probe-ABC pattern); no allowlist rows.
- The `LanguagePack` contract (Phase 7.5) is the model case: adding a language is pure addition; growing the `LanguagePack` type itself is a sanctioned, compiler-policed edit.
- Closed `Literal`s (`PackageManager`, `SupportedLanguage`) may be edited to add members without a bespoke ADR — the edit is compiler-policed.
- A new review artefact — the *migration* — is defined in `contributing.md` with its checklist (conformance green, goldens regenerated deliberately, one reviewed sweep).
- Freeze ADRs default to `Provisional Accepted` with a `Review trigger` and justify narrowness + earned-ness.
- `design.md §2`, `CLAUDE.md`, `contributing.md`, and `roadmap.md` carry the "no silent edits" wording.
- **Two problems in this space have no mechanical fence and are not solved by this ADR:** *duplication* (extension-by-addition taken literally produces near-duplicate components) and *freeze-too-early* (a contract frozen on little evidence). They are judgement calls. They are addressed as **standing review criteria in the design-pipeline skills**: `phase-architect` (gap analysis flags near-duplicate components; ADR-extraction enforces the freeze discipline), `phase-story-validator` (the design-patterns critic flags duplication-by-addition; the consistency critic flags premature/over-broad freezes), and `phase-story-executor` (the refactor step flags cross-component copy-paste). This is soft enforcement — it raises the odds the right judgement is made; it does not guarantee it.

## Reversibility

**Medium.** The reframe is wording plus a forward rule; no machinery is built (see Deferred), so there is little to unwind. Reverting to literal "no edits" is cheap textually but reintroduces the allowlist-accretion trajectory the ADR exists to stop. Once Phases 8+ have relied on the negative commitment, reverting means reconstructing per-phase lists retroactively — increasingly costly as phases accumulate.

## Evidence / sources

- `../design.md §2` commitment 5 — the extension-by-addition commitment this ADR refines.
- [ADR-0039](0039-extension-by-addition-allows-bounded-core-primitives.md) — bounded additive core primitives; ADR-0043 refines the definition of "edit" that 0039 assumes.
- [Phase 7 ADR-0009](../../phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — the per-phase byte-edit allowlist whose non-scaling motivated this ADR; now the terminal allowlist.
- [ADR-0007](0007-probe-contract-preserved-poc-to-service.md) — the probe contract, pinned by a snapshot test; the model for commitment 3.
- [ADR-0033](0033-domain-modeling-discipline.md) — closed sum types; compiler-policed `Literal` growth is the canonical "loud edit".
- `docs/roadmap.md §"Phase 7.5"` — the phase that lands the conformance suite and carries this discipline reframe.
