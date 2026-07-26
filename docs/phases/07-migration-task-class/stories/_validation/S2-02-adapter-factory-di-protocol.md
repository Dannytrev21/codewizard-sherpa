# Validation report — S2-02 `AdapterFactory` Protocol + DI kwarg vocabulary

**Story:** [`S2-02-adapter-factory-di-protocol.md`](../S2-02-adapter-factory-di-protocol.md)
**Verdict:** **STRONG (retrospective)** — story shipped `Done` on 2026-05-19 in a single attempt; four-critic pass finds no blockers and only minor documentation drift + edge-case gaps that carry over as `Notes for the implementer` for the S2 story family.
**Validator run:** 2026-07-25
**Depth:** default (Stage 3 research not fired — no `NEEDS RESEARCH` findings)

## Why retrospective

The scheduled `story-validation-corrector` job selects the lowest-numbered story lacking a `_validation/{ID}.md` report. S2-02 was implemented and merged (commit `a6e7071 — feat(phase7/S2-02): GREEN`) before the validator ran on it. This report exercises the four critics against the story-as-written and the shipped code, then applies edits that preserve the checked-off ACs (Rule 12: never invalidate shipped evidence).

## Critics — findings

### Coverage — STRONG (minor gaps)

Every AC traces to the goal's five subgoals; the closed-vocabulary discipline is enforced *structurally* (`for name in _DI_KWARGS if name in parameters`, `factory.py:112`), not by filtering — a name outside the vocabulary is unreachable, not merely rejected.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| C-1 | harden | `**kwargs` VAR_KEYWORD adapter is untested. `inspect.signature` maps it under key `"kwargs"`, so the factory injects nothing — arguably correct (closed vocabulary wins) but unpinned. | Added as `Notes for the implementer` bullet. |
| C-2 | harden | Inherited `__init__` via MRO — subclass that doesn't override inherits DI declarations from the parent. Correct today but not pinned. | Added as `Notes for the implementer` bullet. |
| C-3 | nit | Positional-only DI params (`def __init__(self, sbom_reader, /)`) would `TypeError` at `cls(**kwargs)`. No current adapter shape; worth a one-line convention. | Added as `Notes for the implementer` bullet. |
| C-4 | nit | AC-7 hedges ("clear `TypeError` OR the adapter's own validation error"). Conflates factory behavior with adapter behavior. | Left as-shipped — passing evidence attached; note for future story-writing to split factory ACs from consumer ACs. |
| C-5 | nit | No AC pins `self` handling. Trivially covered by `_DI_KWARGS` never containing `"self"`. | No action. |

### Test Quality — STRONG (minor gaps)

Two highest-value mutants ("passes everything" and "smuggles unknown kwarg") are closed. Suite is intent-encoded via docstrings. The remaining gaps are property/metamorphic reinforcement, not correctness holes.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| TQ-1 | harden | Positional-only `/` in `AdapterFactory.__call__` is untested. Deleting the `/` leaves every current test green — but the marker is load-bearing for future keyword-collision immunity (an adapter with a param literally named `cls`). | Added as `Notes for the implementer`; if a follow-up bench-side story lands, add the `inspect.Parameter.POSITIONAL_ONLY` assertion. |
| TQ-2 | harden | No metamorphic test that two constructions are independent (no cached state / aliasing). A memoizing-mutant would survive. | Added as `Notes for the implementer` for S2 family. |
| TQ-3 | harden | Powerset property test would subsume AC-3/4/5/6. Four subsets are currently untested (`{logger}`, `{image_manifest_cache}`, `{sbom_reader, image_manifest_cache}`, `{logger, image_manifest_cache}`); a "swap sbom_reader with logger in `available`" mutant survives today. | Added as `Notes for the implementer`; deferred until a real bug surfaces (Rule 2). |
| TQ-4 | nit | `**kwargs` shape unpinned (paired with C-1). | Same disposition as C-1. |
| TQ-5 | nit | All-positional adapter (`def __init__(self, sbom_reader, logger, image_manifest_cache):` with no `*`) works today by Python's keyword-to-positional binding but isn't pinned. | Added as `Notes for the implementer`. |
| TQ-6 | nit | `test_default_adapter_factory_singleton_passes_none_to_required_dep` verifies the *adapter's* `None`-rejection, not a factory-owned contract. Reads as re-testing the fixture. | Left as-shipped (evidence attached); note for future story-writing to phrase such ACs as "factory propagates constructor exceptions unwrapped". |

### Consistency — STRONG (minor drift)

Story faithfully implements Phase-7 ADR-0007 §Decision (registry stores classes; factory owns dispatch-time construction with a closed DI vocabulary). ADR-0004 primitive-home placement matches. Dependencies chain to S2-01 is real. The `object | None` deviation raised in the critic prompt is a **false alarm** — AC-3 explicitly permits `object` placeholders and `factory.py`'s module docstring justifies the choice with a full paragraph.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| CN-1 | harden | Evidence line references `_attempts/S2-02-adapter-factory-di-protocol.md` but the file does not exist (`_attempts/` holds only `S2-01-*` and `S2-05-*`). git log shows the story landed in a single commit (`a6e7071`) — no multi-attempt debugging occurred. The line breaks the "read latest attempt log first" convention. | **Edited:** dropped the missing-file reference from Evidence and noted the single-attempt landing inline. |
| CN-2 | nit | The Refactor bullet "Type the private DI attributes on `DefaultAdapterFactory` (`SbomReader \| None`, etc.) — when S1-05's `SbomReader` shape is stable" is stale — S1-05 shipped `SyftSbom` models, not a `SbomReader` port; the shipped module docstring commits to `object \| None` on principle. The deferred refactor precondition will never fire as written. | **Edited:** replaced the stale Refactor bullet with an explicit "deviation accepted" statement. |
| CN-3 | — | No block-severity contradictions. Pattern-fit (Class-as-token + Factory, `@runtime_checkable`, closed enum-shaped vocabulary) matches ADR-0007 §Pattern fit and production ADR-0031/0033. `__init__.py` re-exports match ADR-0004 §Consequences. | No action. |

### Design Patterns — STRONG (one growth-hazard note)

Registry (S2-01) + Factory (S2-02) is a clean Class-as-token + Factory pattern; the Protocol is `@runtime_checkable` (Ports-and-adapters); closed vocabulary is enforced by iteration (structurally, not defensively); `default_adapter_factory` is `Final` and immutable-in-practice. Rule-2-appropriate throughout.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| DP-1 | harden | Growing the DI vocabulary requires editing **three parallel sites**: `_DI_KWARGS` (frozenset), `DefaultAdapterFactory.__init__` parameter list, and the `available` dict in `__call__`. Two adjacent Phase-8 adapter stories will surface this as friction. Not premature-abstraction to signal it; premature-abstraction to *fix* it before a third consumer arrives. | Added as `Notes for the implementer` — recommend a `DIBundle` dataclass or `TypedDict` when the third DI kwarg addition arrives (rule of three). |
| DP-2 | nit | `_DI_KWARGS: frozenset[str]` uses primitive strings; a `StrEnum` would be more type-safe. Given the vocabulary is iterated as dict keys and the `Final` frozenset is the enforcement mechanism, `StrEnum` is aesthetics-only today. | No action (Rule 2). |
| DP-3 | nit | `default_adapter_factory` module-level singleton is a mild global. Justified in existing `Notes for the implementer` as test-convenience; `Final` guarantees no rebinding. Fixture-per-test isolation pattern (ADR-0007 §Consequences) is the real substitution seam. | No action. |
| DP-4 | nit | `available` dict is constructed per `__call__`. Micro-optimization would pre-compute it in `__init__`. Sub-µs cost per adapter; keep as-is. | No action. |

## Edits applied to the story

Two categories, all surgical (Rule 3):

1. **Evidence-block correction** — CN-1: removed the reference to the non-existent `_attempts/S2-02-*.md` file; recorded that the story landed in a single commit.
2. **Refactor bullet freshening** — CN-2: replaced the stale "when S1-05's `SbomReader` shape is stable" refactor bullet with an explicit "deviation accepted" acknowledgment.
3. **`Notes for the implementer` additions** — C-1, C-2, C-3, TQ-1, TQ-2, TQ-3, TQ-5, DP-1: added bullets covering `**kwargs`/MRO/positional-only conventions, metamorphic-and-powerset test-hardening opportunities for the S2 family, and the "three parallel edit-sites" growth hazard.
4. **`Validation notes` block** — appended under the story header documenting the retrospective review.

**Not edited:** every checked-off AC (Rule 12 — shipped evidence is authoritative), the Goal, the Implementation outline (accurate against `factory.py`), the TDD plan's red/green tests (they match what shipped), the Files-to-touch table.

## Verdict rationale

- No critic returned a `block`-severity finding.
- Every `harden` finding is either (a) a documentation drift the retrospective could fix cleanly (CN-1, CN-2) or (b) a `Notes for the implementer` opportunity for the S2 story family that does not undermine what shipped.
- All `nit` findings are Rule-2 acceptable (three-similar-lines beats premature abstraction).
- The shipped implementation is a clean instantiation of Class-as-token + Factory + Ports-and-adapters, faithful to ADR-0007.

**STRONG.** No re-execution needed. Notes are seeded for the next similar-shaped story (S3-01 `npm-adapter-contract-test-first`, S3-02 `npm-vuln-provenance-adapter`) to pick up.
