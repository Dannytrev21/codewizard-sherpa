# Validation report: S7-10 — Phase-5 contract snapshot + ops runbooks

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Reviewer:** automated scheduled run (`story-validation-corrector`)
**Repo HEAD at validation:** `9f3ec45` (master)

## Summary

S7-10 bundles three Phase-4 → Phase-5 handoff deliverables under a single Step-7 owner: extending the Phase-3 S6-06 contract snapshot test with five Phase-4 additive captures, publishing the Phase-6 LangGraph lift fixture, and landing three operator runbooks (`secrets.md`, `cassettes.md`, `embeddings.md`).

The v1 of the story was readable and well-scoped but had several **block-severity** internal contradictions and missing-discipline gaps that would have led the executor to ship a structurally-divergent snapshot from S6-06's hardened baseline. Specifically: the TDD plan created a `_phase4_additions.py` sibling test file (contradicting AC-1's "extended, not rewritten"); used `inspect.signature` string comparisons (contradicting the story's own Notes and S6-06's golden-file discipline); invented a parallel `_sig()` helper instead of consuming S6-06's `snapshot_symbol`; and lacked meta-tests, determinism property, no-silent-rewrite fence, and directive-message-format checks that S6-06 hardened. The ops-docs smoke test was a substring check (passable by putting section names in comments) and the fixture's "structurally matches" assertion was unverifiable.

Edits resolved all blockers in place by inheriting S6-06's discipline wholesale (registry-driven classifier, golden-file format, pure functional-core helpers, directive-message format, Pydantic-version pin, no-silent-rewrite fence) and by pinning the fixture's shape with a `@runtime_checkable FallbackTierCallable` Protocol. The story is now executable; it explicitly requires Phase-3 S6-06 to be **GREEN** before this story can land (a precondition v1 elided).

Verdict: **HARDENED** — 5 block, 11 harden, 6 nit findings; 19 edits applied to the story file.

## Findings by critic

### Coverage critic

```markdown
## Coverage critic findings — S7-10

### F1 — Capture comparison strategy not pinned in ACs
- Severity: harden
- What's wrong: AC list says "assert_signature_unchanged(...) or equivalent inspection helper" — leaves the comparison strategy (inline string vs golden file) ambiguous. The story's Notes say golden-file may be needed for Python-version stability, and S6-06 hardened the golden-file approach.
- Proposed fix: AC pinning golden-file comparison with `tests/golden/phase5-contract/` layout inherited from S6-06.
- Confidence: high
- Source: AC-1 of v1; Notes paragraph 1

### F2 — Classifier-discipline inheritance not specified
- Severity: block
- What's wrong: Phase-3 S6-06 mandates a registry-driven classifier with 6 breaking-delta families. The v1 story extends the snapshot but doesn't say whether the five Phase-4 entries inherit the classifier's discipline. Without that AC, the executor could silently bypass the classifier on the new entries.
- Proposed fix: AC: "the five Phase-4 entries plumb through the existing `@register_delta_rule(SnapshotKind)` registry; no new classifier rules required (else explicit Phase-3 ADR-0001 amendment)".
- Confidence: high
- Source: cross-referenced S6-06's HARDENED-state validation notes #6

### F3 — Directive-message format not inherited
- Severity: harden
- What's wrong: v1's AC about deliberate-violation says "fails-loud with a diagnostic naming the drifted signature" — but doesn't require the diagnostic format match S6-06's `PHASE 5 CANNOT SHIP` directive.
- Proposed fix: AC inheriting S6-06's directive-message-format AC by reference.
- Confidence: high
- Source: S6-06 validation notes #11

### F4 — Interim-name pinning policy ambiguous
- Severity: harden
- What's wrong: ADR-0009 says `_phase4_local_capability_mint` is interim; Phase 5 may rename. The story pins the name in the snapshot but doesn't say whether a Phase-5 rename is a contract event (requiring ADR amendment) or a transparent allowed change.
- Proposed fix: AC explicitly making rename a contract event (matches S6-06 discipline + Phase-3 ADR-0001 §Consequences row 2).
- Confidence: high

### F5 — Missing-lock-file edge case in embeddings.md
- Severity: harden
- What's wrong: AC-13 (embeddings.md "Refuse-to-start on lock drift") covers drift but not absence. Both fail open if undocumented.
- Proposed fix: AC widened to "lock drift AND lock missing entirely".
- Confidence: high
- Source: edge-case brainstorm

### F6 — Refuse-to-start cross-link not bound to executable test
- Severity: nit
- What's wrong: secrets.md's "Refuse-to-start behavior" prose claim isn't bound to an executable test asserting the behavior — a future drift can silently break the doc's claim without a CI signal.
- Proposed fix: AC requires cross-link to the integration test that asserts the behavior.
- Confidence: medium

### F7 — Story bundling concern (3 deliverables in 1 story)
- Severity: nit
- What's wrong: INVEST/Small concern — snapshot + fixture + 3 ops docs is ≥4 deliverables.
- Proposed fix: keep bundled (Rule 2 wins; shared deadline + owner); note rationale in implementer notes.
- Confidence: medium

### F8 — ADR citation accuracy
- Severity: harden
- What's wrong: v1 cites ADR-0006 as the "no env-var fallback" anchor; ADR-0006 is the egress-guard loopback-carveout decision. The no-env-var discipline is in ADR-0005.
- Proposed fix: ADR-0005 primary, ADR-0006 secondary cross-link.
- Confidence: high
```

### Test-Quality critic

```markdown
## Test-Quality critic findings — S7-10

### T1 — TDD plan contradicts AC + Notes (uses inspect.signature inline strings)
- Severity: block
- What's wrong: AC-1 says "extend (not rewrite)" but TDD plan creates a sibling `test_phase5_contract_snapshot_phase4_additions.py`. Plan uses inline `inspect.signature` string comparison; story's own Notes warn about Python-version drift and suggest golden-file. S6-06 hardened the golden-file approach.
- Proposed fix: TDD plan extends the existing file in place; consumes `snapshot_symbol`/`diff_snapshots`; golden lives under `tests/golden/phase5-contract/`.
- Confidence: high
- Source: AC-1 vs §TDD plan red-test block; story Notes §1

### T2 — Substring-based ops doc test is bypassable
- Severity: harden
- What's wrong: `test_ops_doc_exists_with_sections` does `assert s in text` — passable by a section name appearing in a comment with no body.
- Proposed fix: introduce pure `parse_section_body(text, heading)` helper; assert level-2 heading + non-empty body (≥3 lines or fenced code block).
- Confidence: high
- Source: mutation thinking — "what's the laziest impl that passes?"

### T3 — Fixture test only checks iscoroutinefunction
- Severity: harden
- What's wrong: v1 `test_fallback_tier_callable_fixture_published` only checks `iscoroutinefunction`. A pure-pass-through stub returning `None` would satisfy AC-9.
- Proposed fix: behavior test (AC-10) that runs the callable end-to-end and asserts mocks were exercised.
- Confidence: high
- Source: lazy-impl thought experiment

### T4 — No breaking-delta meta-tests for Phase-4 entries
- Severity: block
- What's wrong: S6-06 hardened six breaking-delta meta-tests; this story extends the snapshot but doesn't propagate that discipline to the new entries. A buggy classifier could silently accept a breaking delta on a Phase-4 entry.
- Proposed fix: six new meta-tests, one per Phase-4 capture (AC-5).
- Confidence: high
- Source: S6-06 validation notes #8

### T5 — No determinism property test for Phase-4 entries
- Severity: harden
- What's wrong: S6-06 hardened a determinism test (same source → byte-identical snapshot 10×). Phase-4 entries should inherit.
- Proposed fix: AC-6.
- Confidence: high

### T6 — No no-silent-rewrite fence on Phase-4 captures
- Severity: harden
- What's wrong: S6-06 added an AC asserting the golden is NOT written without `UPDATE_GOLDEN=1`. Phase-4 captures need the same fence.
- Proposed fix: AC-7.
- Confidence: high

### T7 — Mock collaborators in fixture have no observable contract
- Severity: harden
- What's wrong: AC-9 says "wires mock collaborators" but doesn't specify they record invocations. A pure-pass-through impl passes.
- Proposed fix: mocks expose `.call_count` / `.running_total_calls`; AC-10 asserts ≥1 invocation.
- Confidence: high

### T8 — _sig() helper invented in TDD plan parallel to S6-06's snapshot_symbol
- Severity: harden
- What's wrong: v1 introduces a `def _sig(obj)` helper — parallel to S6-06's `snapshot_symbol(name, obj)`. Two helpers do the same job; the new one drifts independently.
- Proposed fix: consume S6-06's helper; remove `_sig()`.
- Confidence: high
- Source: Open/Closed; Rule 11
```

### Consistency critic

```markdown
## Consistency critic findings — S7-10

### C1 — Phase-3 S6-06 dependency not flagged as GREEN-required
- Severity: block
- What's wrong: v1 depends on "S6-01, S3-05, S3-02, S2-05, S4-06, S4-01" but not on S6-06 (the OWNER of the file being extended). At validation time, S6-06 is HARDENED-not-GREEN and `tests/integration/test_phase5_contract_snapshot.py` does not exist on disk. The story is unsafe to execute until S6-06 is GREEN.
- Proposed fix: Add Phase-3 S6-06 GREEN as the primary depends-on; add pre-flight check to TDD plan.
- Confidence: high
- Source: file-system check at HEAD 9f3ec45

### C2 — ADRs-honored line misses several cited ADRs
- Severity: harden
- What's wrong: Story body cites ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0010, ADR-0013, ADR-0014, and Phase-3 ADR-0001; the header `ADRs honored` line names only ADR-0009 + ADR-0002 + production-ADR-0031. Eight ADRs missing from the index.
- Proposed fix: expand the line.
- Confidence: high
- Source: cross-check story-body citations vs header

### C3 — _phase4_local_capability_mint supersession tension not surfaced
- Severity: harden
- What's wrong: ADR-0009 says the mint is interim. Snapshot pins its name. No story-level statement that a Phase-5 rename is a contract event (vs an allowed transparent change).
- Proposed fix: cross-reference Phase-3 ADR-0001 §Consequences row 2 explicitly in story body + add AC-4.
- Confidence: high

### C4 — S6-06 hardened discipline not inherited
- Severity: block
- What's wrong: S6-06's validation notes list 14 specific disciplines (registry classifier, six breaking-delta meta-tests, determinism property, no-silent-rewrite fence, directive-message format, functional-core helpers, Pydantic version pin, `should_update_golden(env)` factor-out). v1 of this story inherits none of them explicitly.
- Proposed fix: ACs that explicitly call each discipline out (AC-1 through AC-7, AC-18).
- Confidence: high

### C5 — S3-06 stub may not exist on disk
- Severity: harden
- What's wrong: AC-12 says "finalize the S3-06 stub or write from scratch" — leaves ambiguity. S3-06 is HARDENED-not-GREEN as of HEAD 9f3ec45; `docs/operations/` directory does not exist.
- Proposed fix: ACs neutral about pre-existence; add S3-06 to Depends-on.
- Confidence: medium

### C6 — ADR-0006 incorrectly attributed to "no env-var fallback"
- Severity: harden
- What's wrong: Phase-4 ADR-0006 is "egress-guard-no-production-loopback-carveout"; the "no env-var fallback for Anthropic key" discipline is in ADR-0005 ("no-spki-pin-egress-defense-in-depth").
- Proposed fix: ADR-0005 primary, ADR-0006 secondary cross-link.
- Confidence: high — verified by reading ADR titles

### C7 — Refuse-to-start-on-lock-missing edge case missing
- Severity: harden
- What's wrong: ADR-0007 (fastembed-onnx-over-sentence-transformers) implies refuse-to-start on lock drift; missing-entirely is a related-but-distinct case. Story addresses drift only.
- Proposed fix: AC-13 widens to lock-drift AND lock-missing.
- Confidence: medium

### C8 — Cassette-discipline ADR-0014 cited inconsistently
- Severity: nit
- What's wrong: ADR-0014 cited in AC-12 but not in the ADRs-honored header line.
- Proposed fix: include in header.
- Confidence: high
```

### Design-Patterns critic

```markdown
## Design-Patterns critic findings — S7-10

### D1 — Three deliverables in one story (single-responsibility concern)
- Severity: nit
- What's wrong: snapshot + fixture + 3 ops docs is ≥4 deliverables. INVEST/Small says split.
- Proposed fix: keep bundled (Rule 2 wins; shared deadline + owner); note in implementer notes.
- Confidence: medium
- Resolution: per editor.md priority — Rule 2 over Design-Patterns; demote to nit and note.

### D2 — TDD plan creates a sibling test file (Open/Closed inverted)
- Severity: block
- What's wrong: AC-1 says "extended, not rewritten"; TDD plan creates `_phase4_additions.py` sibling. Bifurcates the canonical contract surface — exactly the failure mode S6-06's extension-by-addition discipline forbids.
- Proposed fix: TDD plan extends in place.
- Confidence: high

### D3 — Parallel _sig() helper instead of consuming S6-06's snapshot_symbol
- Severity: harden
- What's wrong: v1 introduces `_sig(obj)` parallel to S6-06's `snapshot_symbol`. Open/Closed violation at the helper level.
- Proposed fix: consume `snapshot_symbol`; remove `_sig`.
- Confidence: high

### D4 — REQUIRED_DOCS dict (primitive obsession?)
- Severity: nit
- What's wrong: `dict[path, list[section]]` for the three ops docs. If a 4th doc is ever added, the right shape is `OpsDocSpec` Pydantic model + `@register_ops_doc` registry. Today: three concrete consumers — at the rule-of-three boundary but not over it.
- Proposed fix: keep dict; Notes-for-implementer says "extract registry at fourth ops doc" (CLAUDE.md "Extension by addition" + Rule 2 win).
- Confidence: high

### D5 — Fixture lacks Protocol-typed Phase-6 lift contract
- Severity: harden
- What's wrong: v1 says fixture "structurally matches `FallbackTier.run`" — unverifiable. Phase 6 wants to `isinstance`-check the callable shape.
- Proposed fix: `@runtime_checkable FallbackTierCallable` Protocol + the instance; AC-9.
- Confidence: high

### D6 — Functional-core / imperative-shell discipline not pinned for new helpers
- Severity: nit
- What's wrong: S6-06 hardened pure helpers (`snapshot_symbol`, `diff_snapshots`, `format_breaking_delta_message`). This story adds `parse_section_body` which should also be pure.
- Proposed fix: Notes-for-implementer call this out; the test code itself enforces purity by not importing `pathlib` inside the helper.
- Confidence: high

### D7 — Extension-by-addition fence missing
- Severity: harden
- What's wrong: Without an explicit AC asserting "no new entries in `SNAPSHOT_KIND_REGISTRY` or `DELTA_RULE_REGISTRY`", the executor could silently grow the kernel.
- Proposed fix: AC-18.
- Confidence: high
- Source: CLAUDE.md "Extension by addition", S6-06 §AC-18-equivalent
```

## Research briefs

**None** — every finding had a local resolution traceable to S6-06's hardened validation report (`docs/phases/03-vuln-deterministic-recipe/stories/_validation/S6-06-phase5-contract-snapshot.md`) or to a directly-quotable Phase-4 ADR. Stage 3 skipped.

## Conflict resolutions

1. **D1 (split-the-story) vs editor.md "do not rewrite scope"** — editor.md priority wins; story stays bundled. Note in implementer notes documents the rationale (shared deadline + owner; Rule 2).
2. **D4 (REQUIRED_DOCS abstraction) vs Rule 2 (simplicity)** — Rule 2 wins at 3 consumers; demoted to nit. AC-extracted-registry only mandated when a 4th doc lands.
3. **T1 vs F1 wording** — Test-Quality wins on "use golden file" phrasing; Coverage's "ambiguous comparison strategy" finding is folded into the same AC-1 + AC-2 edit.

## Edits applied

19 edits to the story file. Summary in the story's `Validation notes (2026-05-24)` block (preserved on the story for breadcrumb purposes). Key categories:

| # | Source | What changed |
|---|---|---|
| 1 | meta | Status flipped `Ready` → `HARDENED`. |
| 2 | C1, C5 | Depends-on expanded: Phase-3 S6-06 GREEN required; S3-06 added. |
| 3 | C2, C6, C8 | ADRs-honored expanded from 3 → 11 entries with corrected attribution (ADR-0005 primary for no-env-var). |
| 4 | F1, T1, C4 | AC-1 reframed to inherit S6-06's golden-file + registry discipline. |
| 5 | F1, T1 | AC-2 added: golden-file comparison + Pydantic version pin. |
| 6 | F3 | AC-3 added: `PHASE 5 CANNOT SHIP` directive-message format. |
| 7 | F4, C3 | AC-4 added: interim-name pinning is a contract event. |
| 8 | T4 | AC-5 added: six breaking-delta meta-tests. |
| 9 | T5 | AC-6 added: determinism property test. |
| 10 | T6 | AC-7 added: no-silent-rewrite fence. |
| 11 | T3, T7, D5 | AC-9 hardened: Protocol-pinned fixture + observable mocks; AC-10 added: behavior test. |
| 12 | T2 | AC-11/12/13/16 hardened: level-2 heading + non-empty body; `parse_section_body` helper. |
| 13 | F5, C7 | AC-13 widened: lock missing OR drift. |
| 14 | F6 | AC-11/13 cross-link executable refuse-to-start test. |
| 15 | D7 | AC-18 added: extension-by-addition fence (registry sizes unchanged). |
| 16 | D2 | TDD plan rewritten: extend in place, no `_phase4_additions.py` sibling. |
| 17 | T8, D3 | TDD plan removes `_sig()` helper; consumes S6-06's `snapshot_symbol`. |
| 18 | various | Implementation outline reordered; pre-flight check added. |
| 19 | D1, D4, D6 | Notes-for-implementer expanded with bundling rationale, rule-of-three for ops-doc registry, functional-core discipline. |

## Verdict rationale

**HARDENED.** Five block-severity findings (F2 classifier discipline, T1 sibling-file TDD plan, T4 missing meta-tests, C1 missing S6-06 dependency, D2 Open/Closed inversion). All five had clear in-place fixes by inheriting S6-06's hardened state — no goal rewrite required. The story's intent (extend the snapshot, publish the fixture, land the ops docs) was correct; the failure mode was internal contradictions and missing discipline inheritance, exactly the shape this validator is designed to catch.

Eleven harden + six nit findings folded in alongside.

## Recommended next step

`phase-story-executor` to implement — **but** only once Phase-3 S6-06 is GREEN (the pre-flight check in the TDD plan will catch this; the story is `BLOCKED-PARTIAL` until then). If executor begins while S6-06 is HARDENED-not-GREEN, the attempt log should record `BLOCKED-PARTIAL` and surface to the human.
