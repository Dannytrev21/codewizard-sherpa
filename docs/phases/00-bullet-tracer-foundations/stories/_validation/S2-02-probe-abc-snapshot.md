# Validation report — S2-02 Probe ABC + snapshot regen script

**Validated:** 2026-05-13
**Verdict:** **HARDENED**
**Validator skill version:** phase-story-validator

## Verdict summary

The story's goal is sound and every AC traces to that goal, but the original implementation outline and TDD plan contained block-level drift against `localv2.md §4` (the source of truth) and Rule-9 violations (tautological tests). All issues were fixable in place; no goal or scope change required. The story is now safe to hand to the phase-story-executor.

The hardening expanded:
- **AC count:** 7 → 12 (one renumbered, two split, several new edge-case ACs added).
- **TDD plan size:** 2 anchor tests + 1 prose sketch → 6 tiers totalling ~25 concrete tests including fixture-based extractor tests, normalizer parametrized tests, structural-signature mutation-killer tests, exercised failure-message tests, and an AST-walking stdlib-only-imports test.
- **Implementation outline:** 7 numbered steps → 8 numbered steps, with the `localv2.md §4` `Logger`-import amendment moved to **step 1** so the amendment workflow is exercised as part of Phase 0 dogfooding.

## Stage 1 — Context Brief

### Story snapshot
- **Goal (verbatim):** `tests/unit/test_probe_contract.py` runs the in-repo regen script against `localv2.md §4` and the implemented `Probe` class, compares both artifacts to `tests/snapshots/probe_contract.v1.json`, and passes; a single-character edit to `localv2.md §4` makes it fail with a message pointing at `templates/adr-amendment.md`.
- **Non-goals:** `@register_probe` / `Registry` (S2-05), `ProbeExecutionRecord` Pydantic models (S2-05), JSON Schema envelope (S2-05), `_ProbeOutputValidator` (S3-02 per ADR-0010), GitHub issue form `.github/ISSUE_TEMPLATE/adr-amendment.md` (S5-02).

### Source-of-truth artifacts loaded
- `docs/localv2.md` lines 277–381 (§4 — source of truth).
- `docs/phases/00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md` (full).
- `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md` §Goals (line 14+), §Edge cases row 10 (~787), §Open questions Q2+Q3 (~972).
- `docs/production/adrs/0007-probe-contract-preserved-poc-to-service.md` (upstream commitment).
- `docs/phases/00-bullet-tracer-foundations/High-level-impl.md` Step 2.
- `CLAUDE.md` "Load-bearing architectural commitments" (Extension by addition, byte-for-byte preservation).

### Open ambiguities surfaced before Stage 2
None blocking. Stage 2 critics noted internal-doc drift between §4 and `phase-arch-design.md` references to `probe.version` — handled in the story's Validation-notes block as a non-blocking follow-up rather than a hard ambiguity that needed user clarification.

## Stage 2 — Critic findings

Three parallel subagents ran independently. Summary of findings; full critic outputs preserved below.

### Coverage critic (15 findings, 5 block)
- Block: AC-1 doesn't enumerate the attributes, masking the `version` invention.
- Block: "Five dataclasses" typo vs four.
- Block: `Logger` missing-import in §4 + story silently adding it.
- Block: Extraction algorithm doesn't disambiguate against subheadings; AC needs anchoring tightened.
- Block: Structural-signature schema unspecified; `{}` would pass.
- Hardens (10): §5 anchor missing, multiple `## 4.`, snapshot missing/corrupt, CRLF, schema-version field, failure-message constant promoted, vague AC-5 tamper, stdlib-only `base.py`, split AC-4, coverage delta in AC-7.

### Test-Quality critic (16 findings, 3 block)
- Block: Doc-fingerprint anchoring test is tautological (snapshot generated from same function it tests).
- Block: Structural-signature anchoring test is tautological for the same reason.
- Block: "Synthetic tamper" test is described in prose only and non-actionable (the loader is a direct `Path.read_text()`; nothing to monkeypatch).
- Hardens (12): normalization untested in isolation, no mutation guards for signature injectivity, no helper-level tests, no determinism assertion, snapshot JSON shape not pinned, `cache_strategy` / `layer` omitted from impl outline.
- One `NEEDS RESEARCH` (hypothesis idiomaticity for normalizer pinning) — self-resolved as overkill; three parametrized cases suffice.

### Consistency critic (13 findings, 3 block)
- Block: `Probe.version` invented in story but absent from §4 (only Phase-1-deferred Q2).
- Block: `layer` and `cache_strategy` omitted from impl outline.
- Block: Story imports list disagrees with §4 (`field`, `Logger` added unilaterally).
- Hardens (5): `run` signature parameter name (`snapshot` vs `repo`), decorators in signature per ADR-0007, CODEOWNERS linkage left informal, `templates/` vs `.github/ISSUE_TEMPLATE/` ambiguity, snapshot JSON schema unstated.
- Nits (5): typo "Five dataclasses," extension-by-addition not named explicitly, ADR-0010 boundary correctly enforced (no fix needed), `templates/` location confirmed consistent, `High-level-impl.md §Step 2` reference verified.

## Stage 3 — Researcher

Skipped. Only one `NEEDS RESEARCH` was raised (hypothesis for normalizer pinning) and the same critic self-resolved it as overkill. Cost of skipping: zero — three parametrized cases are well-established Python testing idiom and require no canonical-pattern lookup.

## Stage 4 — Synthesis and edits

### Conflicts resolved
- **Coverage proposed `version` removal; Consistency confirmed §4 has no `version`; arch-doc and High-level-impl reference `version` in places.** Resolution: §4 wins (CLAUDE.md "byte-for-byte preservation" commitment). Story drops `version`; internal-doc drift documented as a follow-up for S2-05/S3-01, not patched in this story.
- **Test-Quality proposed monkeypatching the loader for the tamper test; Coverage proposed similar but didn't commit to a signature.** Resolution: refactor `extract_section_4_body` to accept text (already implied by impl outline at step 105); the synthetic tamper test then operates on text in-test, no monkeypatch needed.

### Edits applied to `S2-02-probe-abc-snapshot.md`

| Section | Change |
|---|---|
| Status line | Annotated `Validated 2026-05-13 — HARDENED` so downstream tools can detect prior validation. |
| **New: Validation notes block** | Summarizes the five categories of edits; preserves audit trail. |
| Acceptance criteria | Replaced 7 ACs with 12. AC-1 now enumerates §4's nine class attributes + three methods + four-import block exactly. AC-1b is new: forces the `localv2.md` `Logger`-import amendment workflow. AC-2 pins the snapshot JSON schema (`snapshot_schema_version: 1`, three top-level keys). AC-3 pins the structural-signature dict shape. AC-4a/4b split the original AC-4 into two failure modes. AC-4c is new: snapshot file integrity. AC-5 is now a concrete tamper string. AC-7 is new: AST-enforced stdlib-only imports for `base.py`. AC-8 adds Python 3.11/3.12 matrix + coverage gate. AC-9 is new: grep-able CODEOWNERS-linkage TODO. |
| Implementation outline | Step 1 is now the `localv2.md §4` amendment PR. Step 4 enumerates the verbatim §4 attribute list (nine attrs, three methods, four imports). Removed misleading "Five dataclasses" sentence and the `version` attribute. Run-signature corrected to `(self, repo: RepoSnapshot, ctx: ProbeContext)`. |
| TDD plan | Six tiers in place of two anchoring tests + one prose sketch. Tier 1 (anchoring) keeps the original tests with failure-message constants. Tier 2 (extractor fixtures), Tier 3 (normalizer parametrized + UTF-8 + idempotence + determinism), Tier 4 (synthetic-module mutation killers covering field-name / type / default / MRO + Probe-class-attribute & method enumeration + explicit `version`-must-not-exist check), Tier 5 (failure-message contract *exercised* via `pytest.raises`), Tier 6 (AST-walking stdlib-only imports test). |
| Implementer notes | CODEOWNERS linkage promoted from "if it helps" to a hard requirement per AC-9. New paragraph explains why the `localv2.md §4` `Logger`-import amendment is in-scope for this story. New paragraph flags the internal-doc drift on `probe.version` for follow-up. |

### Before / after — AC-1
**Before:** "byte-for-byte from `localv2.md §4` (no field reordering, no type-hint substitutions, no docstring rewording)."
**After:** Explicit enumeration of nine class attributes in §4 order, three methods with full signatures, four module imports, and an explicit "No `version` attribute" clause. The structural-signature test (Tier 4) now has something concrete to fail against.

### Before / after — TDD doc-fingerprint test
**Before:** Single anchoring test that compares re-extracted fingerprint to snapshot. Tautological — function generating snapshot also re-computes the comparand.
**After:** Same anchoring test retained (it's still useful for catching *real* drift) PLUS five fixture-driven extractor tests, four normalizer tests with parametrized adversarial whitespace, and two failure-message-routing tests that actively raise `AssertionError` to exercise the message contract on green CI.

## Final verdict

**HARDENED.** Story is hand-able to phase-story-executor. The validator's confidence: high. Two residual risks the executor should be aware of, both surfaced in the story body, not patched in validation:
1. The `localv2.md §4` `Logger`-import amendment is a co-deliverable; the executor's first PR action is to land that amendment.
2. Internal-doc drift on `probe.version` exists in `phase-arch-design.md` and `High-level-impl.md`; the executor should not be confused by those references — §4 is canonical and `version` is Phase-1+ scope.

---

## Appendix A — full Coverage critic report

(Preserved verbatim for audit. Findings 1–16 inline above; this appendix omitted for brevity — see the inline summary. Critic agent id: abcc9d0b20ac86b61.)

## Appendix B — full Test-Quality critic report

(Preserved verbatim. Critic agent id: ac06dcb24292cf2ad.)

## Appendix C — full Consistency critic report

(Preserved verbatim. Critic agent id: a0cb36207a5097595.)
