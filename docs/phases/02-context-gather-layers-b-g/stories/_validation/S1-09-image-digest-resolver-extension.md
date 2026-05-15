# Validation report — S1-09 `ProbeContext.image_digest_resolver` extension + contract-freeze regen

**Date:** 2026-05-15
**Validator:** phase-story-validator (scheduled run)
**Verdict:** **HARDENED**
**Story:** `../S1-09-image-digest-resolver-extension.md`

## Inputs read

- Story `S1-09-image-digest-resolver-extension.md`
- Phase 2 ADR `0004-image-digest-as-declared-input-token.md`
- Phase 1 ADR `0002-parsed-manifest-memo-on-probe-context.md` (precedent)
- Phase 0 ADR `0007-probe-contract-frozen-snapshot.md` ("code matches doc, never inverse")
- `phase-arch-design.md` (Component design #6, Data model §"contract — additive", Tradeoffs, Edge cases row 14)
- `High-level-impl.md` Step 1 (this story's parent step)
- `final-design.md` §"Conflict-resolution table" rows 9 & 16
- `docs/localv2.md §4` (current ProbeContext body — current state lacks `image_digest_resolver`)
- `src/codegenie/probes/base.py` (current `ProbeContext` dataclass, 7-field)
- `tests/unit/test_probe_contract.py` (full file — Tier 1 anchoring + Tier 7 ADR-0002 sentinel)
- `scripts/regen_probe_contract_snapshot.py` (existing regen script)
- Sibling validation reports `S1-07-run-external-cli.md`, `S1-08-registry-heaviness-runs-last.md` (idiom + report shape)

## Critic findings (collapsed into one pass)

### Consistency — 3 BLOCK findings

1. **B1 — `docs/localv2.md §4` update missing from the story.** The story's goal mentions only the code edit and snapshot regen. But the contract-freeze CI job's Tier 1 anchor is `test_probe_contract_doc_fingerprint_matches_snapshot`, which re-extracts `localv2.md §4`, normalizes-and-hashes, and compares to the committed `doc_fingerprint`. After the new field is added to the dataclass and the snapshot is regenerated, the new `doc_fingerprint` reflects the post-edit doc — but if the doc edit is skipped, the doc_fingerprint computed at regen time is **identical** to the previous value (the doc didn't change), and Tier 1 still passes locally; a future tree-wide regen by another contributor will then flip the digest and break CI. Per 00-ADR-0007 ("change code to match doc, never the inverse"), the doc edit is part of the amendment. **Resolution:** new AC-3 makes the doc edit explicit, and AC-4 strengthens the snapshot assertion to require `doc_fingerprint` change.

2. **B2 — wrong regen script filename.** Story names `scripts/regen_probe_contract.py`; actual file is `scripts/regen_probe_contract_snapshot.py`. The executor would either create a parallel script (Rule 2 violation) or grep, but ambiguity invites silent divergence. **Resolution:** corrected throughout (ACs, files-to-touch, TDD plan, implementation outline).

3. **B3 — story prescribes a parallel `_ALLOWED_PROBE_CONTEXT_FIELDS` set instead of extending the existing Tier 7 `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` sentinel.** Per Rule 11 (match the codebase's conventions), the right move is to extend the existing pattern — same constant name (or a generalized rename), same `test_probe_context_sentinel_fires_on_synthetic_third_field` mutation-killer shape. Creating a parallel set means two field-list assertions in the same file, plus an opportunity for divergence. **Resolution:** AC-5 renames the existing tuple to `_ALLOWED_PROBE_CONTEXT_FIELDS` (no per-ADR suffix; tuple now spans multiple ADRs), updates the test name, and the failure message names both ADRs.

### Coverage — 5 HARDEN findings

- **C1 — no AC for snapshot diff verification.** Story said "regenerate the snapshot" but didn't constrain *what* should change. A buggy executor could run the script before editing the doc/code and commit a no-op snapshot. New AC-4 requires `doc_fingerprint` changes from the pre-story value and `structural_signature.ProbeContext.fields` gains one trailing entry.
- **C2 — no AC for the `| None` return arm.** ADR-0004 + arch design row 14 are explicit: the resolver may return `None` when no image is yet built. Story only had a single test asserting resolver returns `"sha256:cafef00d"`. New AC-10 + new test `test_probe_context_image_digest_resolver_accepts_callable_returning_none` verifies both arms.
- **C3 — no AC for an ADR-0004-specific synthetic-third-field mutation killer.** Story said "a regression test that explicitly tries to add `_FAKE_THIRD_FIELD`" but used a subprocess-based pseudo-code sketch. The existing codebase pattern is an in-test synthetic dataclass. New AC-6 plus a concrete test in the TDD plan mirroring `test_probe_context_sentinel_fires_on_synthetic_third_field`, with regex `r"ADR-0004"`.
- **C4 — no AC for the annotation mutation-killer.** AC-1 specifies the field signature but doesn't pin its `repr()` against silent retypes (e.g., dropping `| None` from the return). New AC-7 mirrors the existing `test_probe_context_new_field_annotations_pinned`.
- **C5 — no AC for the `localv2.md §4` doc-grep.** The Tier 1 `doc_fingerprint` test catches drift but the failure is opaque. A companion doc-grep test (mirroring `test_localv2_section_4_shows_phase1_probe_context_fields`) names *what* drifted. New AC-8.

### Test-Quality — 4 HARDEN findings

- **T1 — `test_image_digest_resolver_is_optional_with_none_default` was thin.** Rewritten to use `tmp_path` (mirror existing tests) and asserted via `is None` rather than `== None`. Now AC-9's test.
- **T2 — subprocess-based regen-script test was pseudo-code.** Rule 9 (tests verify intent concretely): the test must have a concrete shape. Replaced with the in-test synthetic-dataclass mutation killer (idiomatic to the file). The subprocess pattern is reserved for AC-11's *idempotence* test where actually running the script is the point.
- **T3 — `test_parsed_manifest_unchanged` was redundant.** The existing `test_probe_context_new_field_annotations_pinned` (Tier 7) already pins `parsed_manifest`'s annotation. Removed from the new test set; AC-12 references the existing test instead.
- **T4 — `test_probe_abc_unchanged` was redundant.** The existing Tier 4 `test_structural_signature_captures_required_probe_class_attributes` + `test_structural_signature_preserves_probe_class_attribute_order` already pin the ABC's class attributes and order. Removed from the new test set; AC-2 references the existing tests instead.

### Design-Patterns — 1 HARDEN, 1 NOTE

- **D1 — open/closed at the right boundary (HARDEN).** Story prescribed inlining the allowed-field set inside `scripts/regen_probe_contract_snapshot.py`. That creates two sources of truth (test + script) and makes the script aware of business rules that aren't its concern (the script's job is mechanical: walk dataclass fields and serialize). Resolved: the script is allowed-field-agnostic (no edits required); the allowed-list gate lives only in the test. Files-to-touch updated to mark the script as **read-only** for this story.
- **D2 — rule-of-three kernel extract is queued, NOT in scope (NOTE).** This story is the second precedent of "Phase N adds one optional callable to ProbeContext per its ADR" (ADR-0002 + ADR-0004). When a Phase 3+ ADR adds the third, a `_ALLOWED_PROBE_CONTEXT_FIELDS_BY_ADR: Mapping[ADRId, frozenset[str]]` registry (Open/Closed at the file boundary) becomes the right shape — adding a new ADR amendment is a new entry, never an edit. Phase 3 owns that decision. Notes-for-implementer paragraph added; explicitly does NOT introduce the registry here (Rule 2 — premature abstraction at N=2).

## Conflicts resolved by priority

- Coverage critic wanted "AC requires CODEOWNERS file creation." Consistency wins: there is no `@phase2-architects` GitHub team in this repo, `TODO(S5-02): CODEOWNERS entry required` already exists in `base.py`, and S5-02 / S8-04 own the actual CODEOWNERS landing per the High-level-impl.md. Resolved: AC-7 was removed/reworded; new AC-14 instead verifies the existing TODO is preserved (`test_base_py_carries_codeowners_todo_for_s5_02` already covers this).
- Design-Patterns critic considered proposing the `_ALLOWED_PROBE_CONTEXT_FIELDS_BY_ADR` registry extraction immediately. Rule 2 + Coverage-of-current-scope wins: at N=2, three similar lines is better than premature abstraction. Surfaced as a Notes-for-implementer paragraph (queued trigger), not an AC.
- Test-Quality critic considered adding a property-based test (Hypothesis) over arbitrary 9-field dataclasses asserting the sentinel fires. Rejected as YAGNI — one mutation-killer with one synthetic dataclass is sufficient at this scope; the cost of a property test (Hypothesis dep + shrinker noise) is not worth it for a tuple-equality assertion with exactly one decision boundary.

## Stage 3 (research) — skipped

No critic finding tagged `NEEDS RESEARCH`. The patterns invoked here (in-test synthetic-dataclass mutation killer, doc-grep, annotation-pin, code-matches-doc per ADR-0007) are already canonical in this repo's test suite — see `tests/unit/test_probe_contract.py` Tiers 4 and 7.

## Edits applied to the story

- Header: `Status: Ready (HARDENED 2026-05-15)` + new `Validation notes` block summarizing each change with rationale.
- ADRs honored: extended to include 00-ADR-0007 (probe-contract-freeze) and 01-ADR-0002 (precedent) — these constrain the story even though it's owned by 02-ADR-0004.
- Acceptance criteria: full rewrite. From 12 ACs (several vague/redundant/conflict-with-codebase) to 17 sharper ACs:
  - AC-3 new: localv2.md §4 update
  - AC-4 new: snapshot diff verification (doc_fingerprint changes; fields grows by one)
  - AC-5 reworded: extend existing sentinel rather than create a parallel set
  - AC-6 new: ADR-0004-specific synthetic-third-field mutation killer
  - AC-7 new: annotation mutation-killer (Callable/Path/`str | None`)
  - AC-8 new: localv2.md §4 doc-grep test
  - AC-9 reworded: backward-compat constructor test (concrete)
  - AC-10 new: `| None`-return arm test (the `None` path is part of the contract)
  - AC-11 reworded: idempotence verified by an actual subprocess-based test (the only place subprocess belongs)
  - AC-12: references the *existing* `test_probe_context_new_field_annotations_pinned` for parsed_manifest preservation
  - AC-13 new: forbidden-patterns hook continues to pass
  - AC-14 new: `TODO(S5-02)` comment preserved (CODEOWNERS scope clarified)
  - AC-15 new: Tier 1 anchoring tests pass (named explicitly)
  - AC-17 new: red-state commit in git history (TDD discipline auditability)
  - Old AC-7 (speculative CODEOWNERS file creation): removed
  - Old AC-2 (bespoke `hasattr` checks): replaced by reference to existing Tier 4 tests
- Implementation outline: replaced 6-step sketch with explicit red/green/refactor ordering and the doc-first/code-second/snapshot-third sequence.
- TDD plan: replaced pseudo-code subprocess test and ad-hoc field-equality test with concrete tests mirroring the codebase's idiomatic Tier 7 patterns. Total of 7 new tests + 1 idempotence test; all use `tmp_path`, the existing `LOCALV2_PATH` / `_ADR_0002_PATH` style anchors, and the existing `extract_section_4_body` helper.
- Files to touch: corrected regen script filename; added `docs/localv2.md`; marked the regen script as **read-only**; clarified CODEOWNERS / cache.py / probe-consumer scopes as explicitly out-of-scope.
- Out-of-scope: unchanged + emphasized.
- Notes for the implementer: rewritten with 9 concrete guardrails — three-source-of-truth ordering, all-three-arms-of-the-type matter, no parallel allowed-list in the regen script, rule-of-three kernel-extract queued for Phase 3, why no subprocess sentinel test, CODEOWNERS scope, `==` on the tuple (not subset).

## Outcome

The story is now executable by `phase-story-executor` with:

- An AC set that **collectively** guarantees the goal (every drift mode is covered: doc, code, snapshot, sentinel, annotation, return-arm, idempotence, backward compat, ABC unchanged via existing Tier 4 tests).
- Each AC **individually verifiable** (named test or named CLI invocation produces a binary pass/fail).
- A TDD plan whose tests would **fail** under obviously wrong implementations (silent retype of the annotation; missing the `| None` return arm; skipping the doc edit; widening to a 9th field without ADR amendment).
- Extension-by-addition preserved at the right boundary, with the kernel-extract opportunity explicitly queued (not prematurely taken at N=2).
- No structural conflict with phase arch, ADRs, or CLAUDE.md load-bearing commitments.
