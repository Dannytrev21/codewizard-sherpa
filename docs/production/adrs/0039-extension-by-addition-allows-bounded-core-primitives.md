# ADR-0039: Extension by addition allows bounded additive core primitives

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** architecture · extension-by-addition · contracts · phase-7
**Related:** ADR-0007, ADR-0028, ADR-0031, ADR-0038, ADR-0043

## Context

Earlier docs expressed extension-by-addition as a plugin-directory-only rule. Later design work found a genuinely cross-task primitive, `vuln.provenance`, that belongs in the shared layer once base-image workflows arrive.

## Decision

New task classes must not edit existing plugins or stable existing behavior. A bounded additive core primitive is allowed when a genuinely new cross-task capability first appears, but only under explicit ADR control; afterward it becomes part of the stable contract surface.

## Tradeoffs

| Gain | Cost |
|---|---|
| Keeps the important invariant while allowing shared capabilities in the right layer | The older plugin-directory-only wording is no longer literally true |
| Makes healthy reassessment explicit | Reviewers must judge whether a proposed primitive is truly cross-task |

## Consequences

- Phase 7 may add `vuln.provenance` without violating extension-by-addition.
- Future docs must say whether they mean plugin addition only or plugin addition plus an ADR-backed bounded primitive.
- [ADR-0043](0043-extension-by-addition-means-no-silent-edits.md) refines the *definition* of extension-by-addition itself — "no *silent* edits" — and supplies the category-based fence that enforces it. This ADR's bounded-additive-primitive carve-out stands unchanged; ADR-0043 governs what counts as an "edit".
