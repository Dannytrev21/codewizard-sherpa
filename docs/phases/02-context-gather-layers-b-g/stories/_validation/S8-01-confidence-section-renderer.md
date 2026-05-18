# Validation report: S8-01 — `ConfidenceSection` renderer

**Validated:** 2026-05-18
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S8-01 implements the only Phase-2 consumer of the `IndexFreshness` sum type: `src/codegenie/report/confidence_section.py`, which renders the Confidence section of `CONTEXT_REPORT.md` by pattern-matching every variant with `assert_never`. The story is the type-level enforcement of B2's load-bearing role (silent index staleness is the worst failure mode per `production/design.md §2.3`).

Four critics produced 23 findings: 4 blocks, 14 hardens, 5 nits. The story file had **factually wrong narrative** in three places (per-module mypy override that doesn't exist; writer wiring described as new work when already shipped; `IndexerError.message` smart-constructor violation in the malformed-slice path), and **mutation-weak ACs** in three more places (single-row-with-all-markers slipping past AC-2; empty-renderer slipping past AC-6; position-based ordering test that doesn't catch reverse-sort). The largest design-level finding was the **flat-vs-nested match** shape — the story prescribed a single 5-arm match, but the same producer module already uses the nested two-level idiom with `assert_never` at BOTH levels, giving a strictly stronger exhaustiveness signal under Python's pattern matching.

All findings were addressable in place. Verdict: HARDENED. No structural/goal-level RESCUE concerns.

## Findings by critic

### Coverage critic

10 findings: 2 block, 1 missing-AC (block), 5 harden, 2 nit.

- **COV-1 (block)** — AC-3 narrative claims "S1-11's per-module override" but `pyproject.toml [tool.mypy] warn_unreachable = true` is global. AC-3 ritual still passes but the story misleads the executor about config shape.
- **COV-2 (block)** — AC-6 contradicts `Writer.write` signature (`RedactedSlice`-only); story says `render_confidence_section(merged_envelope)` without specifying renderer input shape or the envelope path to per-index freshness data.
- **COV-3 (harden)** — AC-5 `slice_malformed:<ValidationError-summary>` underspecified; `str(ValidationError)` is multi-line and patch-version-unstable, making goldens brittle.
- **COV-4 (block, missing AC)** — empty / no-IndexHealth envelope undefined. Lazy impl emitting `## Confidence\n\n` passes every literal AC.
- **COV-5 (harden, missing AC)** — duplicate `index_name` handling undefined.
- **COV-6 (harden)** — naive datetime, long `IndexerError.message`, non-SHA `last_indexed` underspecified.
- **COV-7 (harden)** — AC-8 denylist too narrow (only `codegenie.probes`); doesn't bar adapters / coordinator / tccm.
- **COV-8 (harden)** — AC-2 substring-bag passes for a single-row-with-all-markers mutant.
- **COV-9 (nit)** — AC-6 byte-identical "modulo regen exclusions" handwave doesn't apply to integration tests.
- **COV-10 (nit)** — `ConfidenceSectionRenderer` class has no AC justification.

### Test-Quality critic

11 findings: 3 block, 6 harden, 1 nit, 1 NEEDS RESEARCH.

- **TQ-1 (block)** — `test_exhaustive_match_every_variant` substring-bag passes degenerate single-row impl.
- **TQ-2 (harden)** — `test_row_order_deterministic` on three lowercase ASCII names is coincidental; mutations to casefold/hash/natural-sort survive.
- **TQ-3 (harden)** — `test_malformed_slice_does_not_crash` passes lazy "always-emit-slice_malformed" impl.
- **TQ-4 (nit)** — clean-import test should use `check=False` to surface `ImportError` clearly.
- **TQ-5 (harden)** — AC-3 manual ritual is dead documentation; S1-11's `test_mypy_warn_unreachable_fixture.py` already automates it.
- **TQ-6 (block)** — integration test passes empty-`## Confidence`-only mutant; row count not asserted against producer output.
- **TQ-7 (harden)** — metamorphic property test missing (each row isolates its variant; adding indices doesn't change others).
- **TQ-8 (harden)** — mutation thought experiments uncovered: reverse-sort, missing trailing newline, triple-blank lines.
- **TQ-9 (nit)** — `## Confidence` heading-line exactness not pinned.
- **TQ-10 (harden)** — no test proves renderer doesn't re-sanitize (load-bearing per Out-of-scope).
- **TQ-11 (NEEDS RESEARCH → resolved)** — `ConfidenceSectionRenderer` class wraps the function with no state; YAGNI vs diagram-alignment. Resolved without external research: no Phase 3 extension is planned for the class (verified against `phase-arch-design.md §"Integration with Phase 3"`); drop the class per Rule 2.

### Consistency critic

6 findings: 1 block, 4 harden, 1 nit.

- **CON-1 (harden)** — `warn_unreachable` is global, not per-module; story narrative is factually wrong (multiple places).
- **CON-2 (harden)** — Writer integration already wired in `writer.py:138-156, 233-239`. Story claims it as new work; the architectural decision (writer-side wiring consuming `RedactedSlice.slice`) has already been made.
- **CON-3 (block)** — AC-5 `slice_malformed:<ValidationError-summary>` row may leak field values past the redactor (Pydantic `ValidationError.errors()[0]["input"]` carries the offending value). Violates 02-ADR-0005 / 02-ADR-0010.
- **CON-4 (harden)** — AC-6 byte-identical-across-runs requires deterministic `Fresh.indexed_at`; producer may capture wall-clock per gather. Test needs explicit time-source freeze.
- **CON-5 (harden, NEEDS RESEARCH adjacent → resolved by DP-1)** — Flat 5-arm match vs nested two-level match: mypy exhaustiveness over `Annotated[Union[..], Field(discriminator="kind")]` is more reliable with nested matches. Established Phase-2 precedent in `index_health.py:239-279` uses nested. Resolved: prescribe nested per DP-1.
- **CON-6 (nit)** — `# CONTEXT_REPORT — <repo_path>` heading risks absolute-path leak per 02-ADR-0008; deferred to a follow-up story (the heading is not in Phase 2 scope per Out-of-scope line 56).

### Design-Patterns critic

9 findings: 1 block, 5 harden, 3 nit.

- **DP-1 (harden)** — Flat 5-arm match contradicts the established nested-match precedent in `index_health.py:239-279`. Mirror the precedent (Rule 11). Both `assert_never` arms required.
- **DP-2 (block)** — `IndexerError("slice_malformed:" + str(e))` violates the producer's smart-constructor contract (`freshness.py:73-80` documents `.message` as "a stable identifier — not a free-form human string"). Routes diagnostic detail to structlog instead; row carries sentinel only.
- **DP-3 (harden)** — `ConfidenceSectionRenderer` class is YAGNI; no state, no precedent for stateless renderer classes in the codebase. Drop. Rule 2 / Rule 11.
- **DP-4 (harden)** — Renderer takes untyped `dict`; explicit `Mapping[str, Any]` boundary with `TypeAdapter` re-validation is the typed proof.
- **DP-5 (nit, Notes)** — CLI-vs-writer wiring tradeoff documented; writer-side path retained.
- **DP-6 (nit, Notes)** — `@register_freshness_row_formatter` registry would be the WRONG instinct for consumer extension; pinned as anti-pattern with rationale.
- **DP-7 (harden)** — AC-3 ritual needs to exercise BOTH `assert_never` sites under DP-1's nested shape.
- **DP-8 (harden)** — Purity AC missing; AST-walking guard added.
- **DP-9 (nit, Notes)** — Newtype erasure at slice boundary documented; do not re-promote `IndexName` inside renderer.

## Research briefs

None invoked externally. TQ-11 and CON-5 were tagged `NEEDS RESEARCH`-adjacent but resolved via codebase precedent (`phase-arch-design.md §"Integration with Phase 3"` for TQ-11; `index_health.py:239-279` for CON-5).

## Conflict resolutions

- **CON-1 vs S8-01 narrative** (per-module override) — Consistency wins; source-of-truth is `pyproject.toml`. Story narrative corrected.
- **CON-2 vs Files-to-touch** (writer.py modify) — Consistency wins; writer is already wired. Story shifts from "modify" to "verify already-wired call site exercises renderer."
- **CON-3 / DP-2 / COV-3 vs AC-5 prose** — All three independently flagged the same `str(e)` synthesis. DP-2's smart-constructor framing is the cleanest fix; CON-3's secret-leak concern is the security justification. Both motivations preserved in AC-5 rewrite and AC-12's new negative test.
- **DP-1 vs AC-2 single-match shape** — Established codebase precedent (`index_health.py:239-279`) wins under Rule 11. Story switches to nested two-level match with `assert_never` at both levels. DP-7 cascades AC-3 to a two-pass ritual.
- **DP-3 / TQ-11 / COV-10 vs phase-arch-design.md §"Logical view" UML class** — Rule 2 + Rule 11 win over diagram convenience. Class dropped; the UML diagram in `phase-arch-design.md` documents code, not the reverse — diagram update is a separate concern.
- **Rule 2 (Simplicity First) vs Design-Patterns** — Two Design-Patterns findings (DP-5 CLI-vs-writer; DP-6 registry-of-formatters) were demoted from harden to Notes-for-implementer paragraphs. Single-consumer status of the renderer + Rule-of-three threshold not reached for either pattern.

## Edits applied

### Edit 1 — Status, ADRs, Validation notes block
- Source: synthesis aggregate
- Status: `Ready` → `HARDENED`
- ADRs honored extended: added 02-ADR-0005, 02-ADR-0010
- New `Validation notes` block under header documents all 13 edits.

### Edit 2 — Context (multi-paragraph rewrite)
- Source: CON-1
- Before: "`mypy --warn-unreachable` is enabled per-module on `codegenie.report/**` via the `pyproject.toml` override that landed in S1-11"
- After: "`mypy warn_unreachable = true` is set repo-wide in `pyproject.toml [tool.mypy]` (Phase 0 S1-02; verified by S1-11's `tests/unit/test_mypy_warn_unreachable_fixture.py`)"
- Rationale: factual correction; per-module override never existed.

### Edit 3 — References (pyproject + writer entries rewritten; S1-11 fixture cited)
- Source: CON-1 + CON-2 + DP-1
- Adds: nested-match precedent cite (`index_health.py:239-279`), correct writer wiring (lines 138-156, 233-239), `RedactedSlice.slice` input type, repo-wide-mypy clarification, `IndexerError.message` stable-identifier reminder.

### Edit 4 — Goal rewritten
- Source: DP-1 + COV-2 + DP-4
- Before: "single `match value:` statement... arms for `Fresh(...)` and `Stale(reason=CommitsBehind(...))`..."
- After: "two-level `match` mirroring `_derive_confidence` / `_last_indexed_at`... outer `match value:` ... inner `match reason:`... Both `assert_never` arms required"
- Renderer input type pinned to `Mapping[str, Any]`.
- Writer integration described as already-wired.

### Edit 5 — AC-1 narrowed
- Source: DP-3 + TQ-11 + COV-10
- Before: exports both `ConfidenceSectionRenderer` and `render_confidence_section`
- After: exports only `render_confidence_section`; closed `__all__ = ["render_confidence_section"]`; denylist tightened to 5 forbidden prefixes
- Rationale: Rule 2 (no abstractions for single-use code); no precedent for stateless renderer class; UML diagram describes code, not vice versa.

### Edit 6 — AC-2 strengthened (mutation-resistant)
- Source: TQ-1 + COV-8 + DP-1
- Before: "asserts the rendered string contains the variant-specific marker"
- After: nested two-level match required; tests assert per-row negative-space (each row contains its own marker and NO other variant's marker) + row count == input size + `out.count("- [OK]") == 1`, `out.count("- [STALE]") == 4`
- Rationale: kills single-row-with-all-markers mutant; aligns with established codebase nested-match idiom.

### Edit 7 — AC-3 rewritten
- Source: CON-1 + TQ-5 + DP-7
- Before: "per-module override active on `codegenie.report.*`... delete `case Fresh(...):` arm" (one-pass)
- After: "repo-wide `[tool.mypy] warn_unreachable = true`... two-pass ritual exercising BOTH `assert_never` sites"
- Rationale: factual correction + double-coverage cascading from DP-1's nested shape.

### Edit 8 — AC-4 strengthened (byte-pinned)
- Source: TQ-2 + COV-6
- Before: row-order test asserts `pos_apple < pos_mango < pos_zebra` (positional)
- After: full-sequence regex assertion + three discriminating fixtures (uppercase mix, numeric, lex) + output-ending invariants
- Naive datetime → AC-5 path (preserves Z-suffix invariant)
- `IndexerError.message` longer than 200 chars truncated to `message[:200] + "…"`
- Rationale: positional test was coincidental; reverse/casefold/hash mutations survived original AC.

### Edit 9 — AC-5 REWRITTEN (block)
- Source: CON-3 + DP-2 + COV-3
- Before: "emits a single `- [STALE] <index_name> · indexer_error · slice_malformed:<ValidationError-summary>` row"
- After: emits `IndexerError(message="slice_malformed")` (stable identifier); row reads `slice_malformed` (no error-summary appendix); diagnostic detail to structlog event `report.confidence_section.slice_malformed` with structured fields
- Rationale: preserves `IndexerError.message` smart-constructor contract (`freshness.py:73-80`); protects 02-ADR-0005 / 02-ADR-0010 plaintext-secret invariant — the renderer never constructs new strings from offending-value inputs.

### Edit 10 — AC-6 rewritten
- Source: COV-2 + CON-2 + CON-4 + TQ-6
- Before: "Edit writer.py to call... assert at least one row per `IndexFreshness`... byte-identical (modulo regen exclusions)"
- After: writer wiring described as already in place (with line numbers); renderer input pinned to `Mapping[str, Any]` (`RedactedSlice.slice`); row count == `len(index_health)` precondition; byte-identical-across-runs requires producer time-source determinism (monkeypatch hook OR stale-only fixture); regex-mask fallback if determinism cannot be achieved.

### Edit 11 — AC-7 narrative corrected
- Source: CON-1
- Before: "with the per-module `warn_unreachable = true` override active"
- After: "repo-wide `warn_unreachable = true` is honored (no override silences it)"

### Edit 12 — AC-8 strengthened
- Source: COV-7 + TQ-4
- Denylist extended: `{codegenie.probes, codegenie.coordinator, codegenie.cache, codegenie.adapters, codegenie.tccm, codegenie.output.sanitizer}`
- `subprocess.run(..., check=False)` so `ImportError` surfaces as a meaningful failure.

### Edit 13 — AC-9, AC-10, AC-11, AC-12, AC-13 ADDED
- Source: COV-4 (AC-9), COV-5 (AC-10), DP-8 (AC-11), CON-3 + TQ-10 (AC-12), TQ-7 (AC-13)
- AC-9: empty / no-`index_health` placeholder body byte-pinned.
- AC-10: duplicate `index_name` raises `ValueError`; writer recovers per existing try/except.
- AC-11: AST-walking purity test guards against silent side-effect drift.
- AC-12: secret-shaped offending-value never appears in `slice_malformed` row (negative-space test); but a well-formed `IndexerError(message="AKIA...")` renders verbatim (trust-the-slice contract).
- AC-13: Hypothesis property test — each row isolates its variant; adding/removing rows doesn't change other rows.

### Edit 14 — Files-to-touch updated
- Source: CON-2
- Writer.py moved from "Modified" to "Verify (already wired — DO NOT MODIFY)" with line ranges.
- pyproject.toml moved to "Untouched" with explicit rationale (warn_unreachable is global).
- Test files split: one purity test file added.

### Edit 15 — TDD plan rebuilt
- Source: aggregate
- 17 RED tests (up from 6) covering each AC with mutation-resistant phrasings.
- GREEN steps clarified: no class, no pyproject edit, no writer edit.
- REFACTOR ritual now two-pass per DP-7.

### Edit 16 — Notes-for-implementer extended (5 new paragraphs)
- DP-1 nested-match-mirror-idiom paragraph.
- DP-2 `IndexerError.message` stable-identifier paragraph.
- DP-6 registry-anti-pattern paragraph (with explanation of why producer-side registry is fine but consumer-side registry kills exhaustiveness).
- DP-4 input-type-boundary paragraph.
- DP-5 writer-vs-CLI wiring history paragraph.
- DP-9 newtype-erasure paragraph.

## Verdict rationale

HARDENED. The story's *goal* (one Phase-2 consumer of `IndexFreshness`; exhaustive match + `assert_never`; renders Confidence section) is sound and well-aligned with the phase arch (G4) and 02-ADR-0006 §Decision. The story's *means* had concrete defects — factually wrong config narrative, smart-constructor violation in the defensive path, mutation-weak ACs, and a missed precedent on nested-match shape — but all were patchable in place without rewriting the goal or scope. After edits: every AC is individually verifiable; the AC set collectively guarantees the goal (no escape hatches); the prescribed implementation is consistent with the producer module's established idiom (Rule 11); the renderer's purity, exhaustiveness, and no-leak invariants are testable; and the design-pattern Notes warn future contributors away from two specific anti-patterns (registry-of-formatters; smart-constructor erosion) and one premature abstraction (class wrapper).

## Recommended next step

`phase-story-executor` to implement. The drafted test file in `tests/unit/report/test_confidence_section.py` (untracked) is a useful starting reference but needs the strengthening that this validation prescribes — the executor should treat the hardened ACs and TDD plan as authoritative and bring the drafted tests up to that bar.
