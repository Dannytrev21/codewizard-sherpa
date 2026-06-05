# Validation report — S2-01 `Layer` + `Ecosystem` enums + `_REGISTRY` + `@register_provenance_adapter` decorator

**Validated:** 2026-06-05 (retrospective; story shipped GREEN 2026-05-19)
**Validator:** phase-story-validator
**Verdict:** **HARDENED**
**Story file:** `docs/phases/07-migration-task-class/stories/S2-01-provenance-adapter-registry.md`

## Context

This is a **retrospective validation** of a story that already shipped GREEN. The phase-story-validator skill was bypassed for Phase 7 starting at S2-01 (S1-01 through S1-06 each have a `_validation/` report; S2-01 through S3-01 do not). The story was executed against a then-unvalidated draft; the implementation landed correctly thanks to the story's already-strong AC discipline (carried over from the Phase 7 architect pass) and the established `@register_dep_graph_strategy` precedent.

Retrospective validation has two purposes:
1. Close the audit gap so the per-story validation trail is complete for Phase 7.
2. Surface tightening that would have hardened the story pre-execution, so sibling stories (Phase 7.5 multi-language registry, Phase 8+ adapter additions) can borrow the discipline.

## Context Brief

**Goal (from story):** Ship `src/codegenie/primitives/vuln_provenance/registry.py` with two string enums (`Layer`, `Ecosystem`), the `_REGISTRY` dict typed by `ProvenanceAdapterId`, the `@register_provenance_adapter(*, layer, ecosystem)` decorator, and the autouse `provenance_registry_reset` fixture.

**Phase-arch constraint:**
- ADR-0007 §Decision pins Option C — registry stores **classes**, not instances. DI happens later via S2-02's `AdapterFactory`.
- ADR-0006 — registry is a plain dict; dispatch ordering lives in `_ADAPTER_DISPATCH_ORDER` (S2-03), not here.
- ADR-0004 — primitive lives at `src/codegenie/primitives/vuln_provenance/`.

**CLAUDE.md commitments:**
- "Extension by addition — no silent edits" (ADR-0043): adding a `Layer` or `Ecosystem` member must require an ADR amendment.
- "Newtype identifiers": `ProvenanceAdapterId` is the typed key.
- Functional core / imperative shell: the decorator is a pure transformation over `_REGISTRY` state; no I/O.

**Precedent (codebase shape to mirror):**
- `src/codegenie/depgraph/registry.py` — single-enum-keyed decorator-registry; closest sibling.
- `src/codegenie/probes/registry.py:154-158` — dual-name collision message format.
- `src/codegenie/indices/registry.py` — explicit `unregister_for_tests` (this story deliberately omits it; tests use autouse snapshot/restore).
- `src/codegenie/plugins/registry.py` — function-call register; this story uses the decorator shape (closer to depgraph) because adapters are classes.

## Critics — findings

### Critic A — Coverage

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-COV-1 | No AC explicitly pinned that *distinct* `(layer, ecosystem)` pairs coexist in `_REGISTRY`. AC-3 pinned shape; AC-4 pinned single-key storage; nothing pinned multi-key independence. The shipped test (`test_distinct_keys_coexist`) covered the contract, but a future executor working from the original AC set could have shipped a `_REGISTRY.clear()`-on-write mutant that passes AC-3/AC-4 individually. | HARDEN | New **AC-14** + a paired test pin distinct-keys-coexist explicitly. |
| F-COV-2 | The decorator's keyword-only invocation contract is implicit in the signature (`*, layer, ecosystem`) but unenforced by any AC. A mutation that drops the `*` (e.g., during a "clean up the kwargs" refactor) would silently widen the contract. | HARDEN | New **AC-13** + `test_decorator_signature_is_keyword_only` pin both branches (positional raises, keyword succeeds). |

### Critic B — Test Quality

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-TQ-1 | AC-6's `str(exc).count(".") >= 2` heuristic is loose: it would pass on a message containing `"foo.bar.baz"` even if neither colliding qualname appeared, or on a message that happened to mention `RegistryError` twice (each dotted access counts). Tightened: AC-6 now requires both literal qualname substrings (`existing_qualname` AND `duplicate_qualname`). The shipped test already used the tighter form; the AC now matches. | HARDEN | AC-6 reworded; TDD-plan red-test snippet already asserts the tight form. |
| F-TQ-2 | The TDD-plan red-test imports `register_provenance_adapter` from the package but never imports `pytest` for the `pytest.raises`. (Cosmetic; shipped test imports it.) | NIT | No edit; the test snippet is illustrative, the executor's red-test landed cleanly. |

### Critic C — Consistency

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-CON-1 | Story spec'd `class Layer(str, Enum)` and `class Ecosystem(str, Enum)`. Shipped code (and Python 3.11+ idiom) uses `class Layer(StrEnum)` / `class Ecosystem(StrEnum)`. The `str, Enum` form is legacy; `StrEnum` is the PEP-663 replacement. Story-vs-code drift would have surfaced as confusion in a future sibling story (Phase 7.5 language enum etc.). | HARDEN | AC-1, AC-2, Implementation outline §2, and the red-test snippet all rewritten to spec `StrEnum`. AC-1 now also adds a load-bearing note: `Layer.APP == "app"` evaluates True, required for YAML-driven catalog readers in S9. |
| F-CON-2 | Implementation outline §2 didn't name the `from enum import StrEnum` import. Trivial but worth pinning so the executor doesn't reach for the legacy form. | NIT | §2 updated. |

### Critic D — Design Patterns

The story already documents the Plugin/Registry kernel pattern, Class-as-token + lazy construction, and the rule-of-three deferral for kernel-extract (now N=5 across `probes`, `indices`, `depgraph`, `plugins`, this). The shipped `registry.py` docstring explicitly records the deferral. CLAUDE.md "Extension by addition" is honored: adding a `Layer` or `Ecosystem` member is an ADR amendment, not a silent edit.

**No new design opportunities** — the story already prescribes the minimal, extension-by-addition shape:

- New layers / ecosystems → additive enum member + ADR amendment (no edits to registry kernel).
- New adapters → `@register_provenance_adapter`-decorated class in a plugin module (no edits to kernel).
- DI dependency growth → ADR amendment to the closed DI-kwarg vocabulary (`sbom_reader`, `logger`, `image_manifest_cache`) per ADR-0007 §Tradeoffs. The registry doesn't know about DI at all.

Endorsed (no edit; surfaced in Notes-for-implementer):

- **Plugin/Registry as kernel + Class-as-token** — the decorator's three-line body (collision-check, assign, return) is exactly the right size. Adding logging, structural validation, or signature inspection would couple the kernel to dispatch-time concerns (S2-02's `AdapterFactory`) or type-check concerns (`mypy --strict`) — defeating the seam.
- **Functional-core / imperative-shell** — `_REGISTRY` mutation is the only impure surface; the decorator factory is pure (a `(layer, ecosystem)` pair maps to a `_wrap` closure). Test isolation via the autouse fixture is the right shell-side discipline.
- **Open/Closed at the declaration-order surface** — `Layer` and `Ecosystem` declaration order is *load-bearing* for S2-03's `_ADAPTER_DISPATCH_ORDER` tuple. AC-1 and AC-2 enforce the order structurally; a PR that adds or reorders members surfaces in code review against the AC contract. This is exactly the structural defense CLAUDE.md "Extension by addition — no silent edits" prescribes.

## Stage 3 — Researcher

Not invoked. No `NEEDS RESEARCH` findings; every pattern is precedented in this repo.

## Stage 4 — Synthesizer / Editor

Edits applied to `docs/phases/07-migration-task-class/stories/S2-01-provenance-adapter-registry.md`:

1. **Status line** updated to `HARDENED (phase-story-validator, 2026-06-05 — retrospective pass …)` — retains the original GREEN ship date for audit clarity.
2. **`Validation notes` block** inserted before `## Context` summarizing the five findings, design endorsements, and the no-research disposition.
3. **AC-1** rewritten: `class Layer(StrEnum)` (Python 3.11+) with explicit `.value` assertions; load-bearing rationale ($Layer.APP == "app"$) called out for S9 YAML-catalog readers.
4. **AC-2** rewritten: `class Ecosystem(StrEnum)` with `.value` assertions.
5. **AC-6** tightened: substring-match on both `__qualname__` instead of dot-count heuristic.
6. **AC-13** added: keyword-only signature contract.
7. **AC-14** added: distinct-keys-coexist invariant.
8. **Implementation outline §2** updated: `from enum import StrEnum`; `class Layer(StrEnum)` + `class Ecosystem(StrEnum)`.
9. **TDD-plan §Required follow-on tests** extended with `test_decorator_signature_is_keyword_only` and `test_distinct_keys_coexist`.

No edits to: Goal (unchanged), References (already comprehensive), Out-of-scope (already names the correct boundaries to S2-02/S2-03/S2-04/S2-05/S3-01), or Notes-for-implementer (already names the load-bearing decisions).

## Verdict

**HARDENED.** Story was already strong (originally GREEN); validator pass added two new ACs (kwarg-only, distinct-keys-coexist), tightened one (AC-6 message format), synced enum syntax with shipped code (`StrEnum`), and documented the audit trail. The story now reflects the discipline applied to all Phase 7 sibling stories.

## Files written

- This report: `docs/phases/07-migration-task-class/stories/_validation/S2-01-provenance-adapter-registry.md`
- Edited story: `docs/phases/07-migration-task-class/stories/S2-01-provenance-adapter-registry.md`
