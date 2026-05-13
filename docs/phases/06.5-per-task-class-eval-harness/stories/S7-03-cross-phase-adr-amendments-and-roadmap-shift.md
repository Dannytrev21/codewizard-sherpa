# Story S7-03 — Cross-phase ADR amendments + roadmap §Phase 7 wording shift

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** Ready
**Effort:** M
**Depends on:** S2-05 (Phase 4 `Canary.mint(seed=...)` shim depends on the kwarg amendment landing), S2-06 (Phase 5 ADR-0010 cost-tag shim depends on the `bench_invocation` field amendment landing)
**ADRs honored:** ADR-0002 (`lower_bound_95` is Phase 7's exit-criterion stat), ADR-0005 (Phase 4 amendment vehicle), ADR-0007 (Phase 5 amendment vehicle), ADR-0009 (Phase 5 ADR-0016 demotion-clarification amendment)

## Context

Phase 6.5 has three cross-phase ADR amendments and one roadmap text edit that must merge before the phase closes. They are all *additive* or *clarifying* — none change observable behavior of already-shipped code — but each crosses a CODEOWNERS boundary (Phase 4 owns Phase 4 ADRs; Phase 5 owns Phase 5 ADRs; the roadmap is project-wide). The risk is calendar, not technical: an amendment PR can sit for days in cross-team review and block the phase-merge train.

The four amendments:
1. **Phase 4 final-design.md** — `Canary.mint(seed: bytes | None = None)` additive kwarg (per ADR-0005).
2. **Phase 5 ADR-0010** — `bench_invocation: bool = False` field on `SandboxCostEntry` (per ADR-0007).
3. **Phase 5 ADR-0016** — clarify "automatic demotion = recommendation-shift, not side-effect" (per ADR-0009).
4. **Roadmap §Phase 7 exit criterion** — `bench_score.mean ≥ tier_threshold[bronze]` → `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` (per ADR-0002).

Phase 6.5's `Open implementation question` calls out the calendar risk (`High-level-impl.md §"Implementation-level risks #2"`): open the amendment PRs at Step 2, not Step 7, so the calendar work overlaps the code work. This story is the *forcing function* — it's where unmerged amendments are blocking and the phase cannot ship until they land.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"What's next — handoff to Phase 7"` — names the four edits as deliverables.
  - `../phase-arch-design.md §"Cross-phase ADR amendments land with the code that depends on them"` (`stories/README.md §"Cross-cutting concerns"`) — the discipline.
- **Phase ADRs (each maps to one amendment):**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §"Consequences"` — roadmap §Phase 7 word substitution mandate.
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §"Consequences"` — Phase 4 `Canary.mint(seed=...)` amendment shape (and the new Phase 4 ADR `ADR-P4-006`).
  - `../ADRs/0007-bench-invocation-tagging-on-sandbox-cost-entry.md §"Consequences"` — Phase 5 ADR-0010 schema-amendment shape.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md §"Consequences"` — Phase 5 ADR-0016 "amended by" pointer + paragraph addition.
- **Upstream files being edited:**
  - `../../04-vuln-llm-fallback-rag/final-design.md` — `Canary.mint(...)` API spec.
  - `../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` — `SandboxCostEntry` schema.
  - `../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` — automatic-demotion text.
  - `../../../roadmap.md §"Phase 7"` — exit criteria.
- **New file landed by this story:**
  - `../../04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md` (created here; ADR-0005 names it).

## Goal

Merge all three cross-phase ADR amendments (Phase 4 final-design + new ADR-P4-006; Phase 5 ADR-0010; Phase 5 ADR-0016) and shift the roadmap §Phase 7 exit criterion from `bench_score.mean` to `bench_score.lower_bound_95` — all in the phase-merge train so Phase 6.5 closes only when the cross-phase contracts are sealed.

## Acceptance criteria

- [ ] `docs/phases/04-vuln-llm-fallback-rag/final-design.md` is edited to document `Canary.mint(seed: bytes | None = None)` — the additive kwarg; default `None` preserves production behavior (cryptographically random 32-byte token); the section names ADR-P4-006 as the authoritative ADR.
- [ ] `docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md` exists (new file) documenting the kwarg in Nygard form (Status, Context, Options, Decision, Tradeoffs, Consequences, Reversibility, Evidence), cross-linking ADR-0005, and noting `tests/canary/test_seed_kwarg_deterministic.py` as the structural test.
- [ ] `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` is amended (additive section) to declare `bench_invocation: bool = False` on `SandboxCostEntry` and document the `CODEGENIE_BENCH_INVOCATION_TAG` env-var read in `CostEmitter`. The amendment cites Phase 6.5 ADR-0007 as origin and notes the Phase 13 filter contract.
- [ ] `docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md §"Decision §4"` is amended with a paragraph reading approximately: "'automatic' refers to the verdict recomputation; tier state in `docs/trust-tiers.yaml` is mutated only via human-authored PR per Phase 6.5 ADR-0009"; the ADR's "Related" / "Amended by" list gains a pointer to ADR-0009.
- [ ] `docs/roadmap.md §"Phase 7"` exit criteria text is edited: every occurrence of `bench_score.mean` in the Phase 7 context becomes `bench_score.lower_bound_95`. Search-and-confirm shows zero remaining `bench_score.mean` strings in the Phase 7 section.
- [ ] Each of the four edits is referenced by a commit message naming the originating Phase 6.5 ADR (so the cross-phase audit trail is preserved).
- [ ] All four amendments are merged (or land in the same merge train) **before** Phase 6.5 itself can close. CI on this story's branch shows the four edited files as present.
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check` clean on touched markdown (if those tools are wired) — at minimum no broken markdown links.

## Implementation outline

1. **Open four PRs early.** Per `High-level-impl.md §"Implementation-level risks #2"`, draft the amendments at Step 2 (when the dependent shims land — S2-05 and S2-06). By Step 7 they should be reviewed; this story is the *gate* that confirms they are merged.
2. **Phase 4 amendment** — edit `final-design.md`'s `Canary.mint` signature section; add the kwarg + default + behavior note. Land `ADR-P4-006-canary-seed-kwarg.md` as a new Nygard ADR.
3. **Phase 5 ADR-0010 amendment** — add a new section header `## Amendment — bench-invocation tagging (Phase 6.5)` at the bottom of the ADR; document the field + env-var read; cross-link Phase 6.5 ADR-0007. The amendment is *additive*: do not delete or restructure the original Decision section.
4. **Phase 5 ADR-0016 amendment** — insert one paragraph after `§"Decision §4"` clarifying "automatic = recommendation-shift"; update the `Related` block to list "Amended by: Phase 6.5 ADR-0009".
5. **Roadmap edit** — open `docs/roadmap.md`, find `§"Phase 7"`, change every `bench_score.mean` to `bench_score.lower_bound_95` in the exit-criteria block. Search the rest of the roadmap to confirm the substitution is *scoped to Phase 7* — Phase 6.5's own exit criteria mention the same statistic; they remain wording-coherent.
6. **Cross-link sanity test** — add `tests/docs/test_cross_phase_amendments_present.py` (or extend the existing doc-validation test if Phase 0 has one) that grep-asserts each of the four expected substrings is present.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/docs/test_cross_phase_amendments_present.py`

```python
# tests/docs/test_cross_phase_amendments_present.py
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_phase4_final_design_documents_canary_seed_kwarg():
    text = (REPO / "docs/phases/04-vuln-llm-fallback-rag/final-design.md").read_text()
    assert "Canary.mint(seed:" in text or "Canary.mint(seed=" in text
    assert "ADR-P4-006" in text  # cross-link to the new ADR


def test_phase4_adr_p4_006_canary_seed_kwarg_exists():
    adr = REPO / "docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md"
    assert adr.exists()
    txt = adr.read_text()
    # Nygard sections.
    for section in ("## Context", "## Decision", "## Tradeoffs", "## Consequences", "## Reversibility"):
        assert section in txt
    # Cross-link to Phase 6.5 ADR-0005.
    assert "0005-cassette-canary-seed-parameterization" in txt


def test_phase5_adr_0010_documents_bench_invocation_field():
    text = (REPO / "docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md").read_text()
    assert "bench_invocation" in text
    assert "CODEGENIE_BENCH_INVOCATION_TAG" in text
    # Cross-link to Phase 6.5 ADR-0007.
    assert "0007-bench-invocation-tagging-on-sandbox-cost-entry" in text


def test_phase5_adr_0016_amended_with_demotion_clarification():
    text = (REPO / "docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md").read_text()
    # The clarification paragraph keyword set:
    assert "recommendation" in text.lower()
    assert "human-authored PR" in text or "human authored PR" in text
    # Cross-link to Phase 6.5 ADR-0009.
    assert "0009-automatic-demotion-as-recommendation-shift" in text


def test_roadmap_phase_7_uses_lower_bound_95_not_mean():
    text = (REPO / "docs/roadmap.md").read_text()
    # Find the Phase 7 section.
    import re
    m = re.search(r"##\s*Phase\s*7\b(.*?)(?=^##\s*Phase\s*\d|\Z)", text, re.S | re.M)
    assert m is not None, "Phase 7 section not found in roadmap.md"
    section = m.group(0)
    # The exit criterion must reference lower_bound_95; mean must not appear in the *exit criterion* prose.
    assert "lower_bound_95" in section
    # Any 'bench_score.mean' substring should be gone from the Phase 7 section.
    assert "bench_score.mean" not in section
```

Run; confirm each assertion fails because the amendments are not yet merged. Commit as the red marker.

### Green

Land the four edits + new ADR file. Each edit is a markdown change; no code changes. The five-test red suite turns green when all four files carry the expected substrings.

### Refactor

- Verify the inserted markdown is well-formed (headers in order; no broken cross-links).
- The new `ADR-P4-006` follows the Nygard template used by every Phase 4 / Phase 5 / Phase 6.5 ADR — copy the section ordering from a recent one (e.g., Phase 6.5 ADR-0005 itself).
- The Phase 5 ADR-0010 amendment is *appended* as a new section, not interleaved into Decision/Tradeoffs — readers should see "Amendment — bench-invocation tagging (Phase 6.5)" as a clearly-bounded addition.
- After the merge: open each upstream phase's docs/CHANGELOG (if it has one) and add a one-line cross-reference, but this is a *nice-to-have*, not blocking.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/04-vuln-llm-fallback-rag/final-design.md` | Edit — document `Canary.mint(seed=...)` |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md` | New — full Nygard ADR for the kwarg |
| `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` | Edit — append "Amendment — bench-invocation tagging (Phase 6.5)" section |
| `docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` | Edit — clarification paragraph after Decision §4; "Amended by" cross-link |
| `docs/roadmap.md` | Edit — Phase 7 exit criterion: `mean` → `lower_bound_95` |
| `tests/docs/test_cross_phase_amendments_present.py` | New — grep-asserts the four edits landed |

## Out of scope

- **Editing Phase 4's source code** for the `Canary.mint(seed=...)` kwarg — that landed in S2-05's bundled Phase 4 amendment. This story is the *documentation* amendment; the code change rode along with S2-05.
- **Editing Phase 5's `SandboxCostEntry` Pydantic model** — same — landed in S2-06.
- **Updating production ADRs** (`docs/production/adrs/*`) — Phase 6.5 does not touch the production-target reference folder for this work; future phases consuming these contracts may.
- **Fence-CI assertions** — S7-01.
- **Audit chain integration** — S7-02.

## Notes for the implementer

- **The four amendments may already be merged** when this story executes (if S2-05/S2-06 followed the discipline of opening PRs early per `High-level-impl.md §"Implementation-level risks #2"`). If so, this story is essentially a *verification* story — the red test passes immediately because the documents already carry the substrings. Do not skip the test; pin the contract.
- **Cross-phase CODEOWNERS review is the long-pole risk.** If any of the four amendments is still under review at Step 7, the phase cannot merge until they land. Escalate early; do not push a Phase 6.5 merge that depends on un-merged amendments.
- **The roadmap edit is the simplest mechanically but the most consequential.** Phase 7's *exit criterion* — what Phase 7 must achieve to ship — changes from "the mean crossed the threshold" to "the lower 95% CI crossed the threshold." That's a strict tightening (`Rule 2 Simplicity First` applies *to the diff*, not to the meaning). Make sure Phase 7's planners read the new criterion *before* they start work.
- **The Phase 5 ADR-0016 amendment is interpretive, not additive.** Reading A vs Reading B in ADR-0009. The clarification paragraph must not appear to *change* what the original ADR said — it must read as "clarifying what was always meant." If the wording suggests retroactive policy change, the Phase 5 CODEOWNERS will (correctly) push back.
- **ADR-P4-006 is the only *new ADR file* in this story.** The other three are edits to existing files. Be careful with the new ADR — the Nygard form is enforced by Phase 0's ADR linter if one exists; mirror the structure of `Phase 6.5 ADR-0005` (the originating ADR) closely.
- **Commit-message discipline.** Each amendment commit should name the originating Phase 6.5 ADR by number. Example: `docs(phase4): amend final-design with Canary.mint(seed=...) kwarg (Phase 6.5 ADR-0005)`. This makes the cross-phase audit trail discoverable by `git log` filters.
- **No code is being changed in this story.** If `pytest` notices any source-file change in the diff, you're doing too much — this is documentation only. Stay within the six paths in §Files to touch.
- **`Rule 12 Fail loud` applies to the merge train.** If the four amendments aren't all green by the time this story is "ready to merge," the phase is not actually ready. Surface that; don't merge ahead of the upstream amendments.
