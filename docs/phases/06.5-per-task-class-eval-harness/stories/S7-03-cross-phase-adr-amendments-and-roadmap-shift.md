# Story S7-03 — Cross-phase ADR amendments + roadmap §Phase 7 wording shift

**Step:** Step 7 — Extend fence-CI; lock in end-to-end audit; ship cross-phase amendments
**Status:** BLOCKED-PARTIAL (AC-1 / AC-2 gated on Phase 6.5 ADR-0005 amendment; AC-3 / AC-3b / AC-4 / AC-5a / AC-5b / AC-6 / AC-7 landable now)
**Effort:** M (M-S if AC-1 / AC-2 stay deferred)
**Depends on:**
- S2-05 (canary shim) — **currently BLOCKED per `_validation/S2-05-canary-seed-shim.md`; rescue owed by phase architect: amend Phase 6.5 ADR-0005 to name the actual Phase 4 seam `FenceWrapper(nonce_source: Callable[[], HexNonce])`)** — gates AC-1 / AC-2.
- S2-06 (cost-tag shim) — HARDENED 2026-05-26 — gates AC-3.
- **Phase 5 S7-03** (sandbox `src/codegenie/sandbox/cost.py` GREEN) — gates AC-3 per S2-06 §"Cross-phase amendment train (gated)".
- **Phase 6.5 ADR-0005 amendment** (owner: phase architect; unblock precondition for AC-1 / AC-2). See F-COV-7 / F-CON-1 / AC-14.

**ADRs honored:** ADR-0002 (`lower_bound_95` is Phase 7's exit-criterion stat), ADR-0005 (Phase 4 amendment vehicle — **currently defective; pending amendment**), ADR-0007 (Phase 5 amendment vehicle), ADR-0009 (Phase 5 ADR-0016 demotion-clarification amendment)

---

## Validation notes (2026-07-26)

Full report: [`_validation/S7-03-cross-phase-adr-amendments-and-roadmap-shift.md`](_validation/S7-03-cross-phase-adr-amendments-and-roadmap-shift.md)

Changes applied by validator:

- **Status flipped:** `Ready` → `BLOCKED-PARTIAL`. Two of the four amendments (AC-1 / AC-2, Phase 4 canary) are gated on an owed ADR-0005 amendment; S2-05's RESCUE verdict (2026-05-26) established that ADR-0005 prescribes a phantom Phase 4 API (`Canary.mint(seed=...)`). Phase 4 actually shipped `FenceWrapper(nonce_source: Callable[[], HexNonce])`. The other three amendments (Phase 5 ADR-0010 field, Phase 5 ADR-0016 clarification, roadmap invariant) are landable now.
- **AC-5 rewritten (was factually unlandable):** the original AC assumed `bench_score.mean` appeared in `docs/roadmap.md §"Phase 7"`. Repo-wide grep returns **zero hits** for `bench_score.mean`. The Phase 7 hard precondition text lives at Phase 6.5 §Exit criteria (row 7, currently ~line 189) and already reads `bench_score.lower_bound_95`. AC-5 is now (a) a repo-wide invariant `bench_score\.mean` = 0 hits and (b) a positive-presence anchor on the `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` string. No fragile Phase-7-section slicing regex.
- **AC-4 hardened:** original assertion (`"recommendation" in text.lower()`) passed trivially — the word appears in ADR-0016 already. Now anchored on the ADR-0009-signature substring `"'automatic' refers to the verdict recomputation"`, which appears in no existing Phase 5 ADR.
- **AC-3b added:** Phase 5 ADR-0010 must acquire a `Related` cross-link back to Phase 6.5 ADR-0007 (bidirectional linking discipline, symmetric to ADR-0016 ↔ ADR-0009).
- **AC-2 hardened:** ADR-P4-006 must carry the Phase-6.5-family header block (`Status:`, `Date:`, `Tags:`, `Related:`), not just Nygard section headers.
- **AC-6 rewritten:** commit-message discipline is unverifiable in a squash-merged / clean-checkout CI world. Replaced with a `docs/phases/06.5-per-task-class-eval-harness/CHANGELOG.md` entry (data on disk, grep-verifiable) per amendment. Commit-message hint moves to Notes.
- **AC-7 rescoped:** was "amendments merged before Phase 6.5 closes" — a phase-close checklist gate, not a story test. Now: "all landable amendment files present in the working tree on the branch that ships this story." The phase-close gate stays in `phase-arch-design.md §"What's next"`.
- **TDD plan restructured (Command / Open-Closed at test-file level):** single monolithic `tests/docs/test_cross_phase_amendments_present.py` → `tests/docs/cross_phase_amendments/` package with `_amendment_manifest.py` (data — one row per amendment) + `test_phase65_amendments.py` (iterates the manifest). Adding Phase 7 / Phase 8 amendments in a future story is one manifest row + one file (`test_phase7_amendments.py`), zero edits to Phase 6.5's test file. Manifest pattern is at rule-of-three threshold — Phase 6.5 is site 1, Phase 7 already prescribed as site 2, Phase 8 site 3 per roadmap — so the abstraction earns its keep now (see Rule 2 / rule-of-three note in Design-Patterns critic).
- **AC-14 added:** explicit precondition — AC-1 / AC-2 do not unblock until Phase 6.5 ADR-0005 is amended (or superseded) to name the actual Phase 4 seam. Under the amended ADR, AC-1 / AC-2 will be re-scoped in one of two shapes named in the AC.

---

## Context

Phase 6.5 has four cross-phase edits that must merge before the phase closes: three ADR amendments (Phase 4 canary — currently blocked; Phase 5 ADR-0010; Phase 5 ADR-0016) plus a roadmap consistency invariant on `bench_score.lower_bound_95`. They are all *additive* or *clarifying* — none change observable behavior of already-shipped code — but each crosses a CODEOWNERS boundary (Phase 4 owns Phase 4 ADRs; Phase 5 owns Phase 5 ADRs; the roadmap is project-wide). The risk is calendar, not technical (except for AC-1 / AC-2, which are additionally *factually* blocked on an owed ADR-0005 amendment): an amendment PR can sit for days in cross-team review and block the phase-merge train.

The four amendments:
1. **Phase 4 final-design.md** — canary-seed pinning (currently `Canary.mint(seed: bytes | None = None)` per ADR-0005 — **BLOCKED**; awaiting ADR-0005 amendment to name Phase 4's actual shipped seam).
2. **Phase 5 ADR-0010** — `bench_invocation: bool = False` field on `SandboxCostEntry` + cross-link back to Phase 6.5 ADR-0007 (per ADR-0007).
3. **Phase 5 ADR-0016** — clarify "automatic demotion = recommendation-shift, not side-effect"; `Related` block gains "Amended by: Phase 6.5 ADR-0009" pointer (per ADR-0009).
4. **Roadmap `bench_score` invariant** — `bench_score.mean` must not appear anywhere in `docs/roadmap.md` as a promotion-gate signal; the Phase 7 hard precondition text (currently at Phase 6.5 §Exit criteria row 7) already names `bench_score.lower_bound_95`. This story pins the invariant (per ADR-0002).

Phase 6.5's `Open implementation question` calls out the calendar risk (`High-level-impl.md §"Implementation-level risks #2"`): open the amendment PRs at Step 2, not Step 7, so the calendar work overlaps the code work. This story is the *forcing function* — it's where unmerged amendments (and un-amended blocking ADRs) surface and the phase cannot ship until they land.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"What's next — handoff to Phase 7"` — names the four edits as deliverables.
  - `../phase-arch-design.md §"Cross-phase ADR amendments land with the code that depends on them"` (`stories/README.md §"Cross-cutting concerns"`) — the discipline.
- **Phase ADRs (each maps to one amendment):**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md §"Consequences"` — roadmap invariant.
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §"Consequences"` — **defective per `_validation/S2-05-canary-seed-shim.md`; amendment owed by phase architect before AC-1 / AC-2 unblock.**
  - `../ADRs/0007-bench-invocation-tagging-on-sandbox-cost-entry.md §"Consequences"` — Phase 5 ADR-0010 schema-amendment shape.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md §"Consequences"` — Phase 5 ADR-0016 "amended by" pointer + paragraph addition.
- **Sibling validations (read before touching this story):**
  - `_validation/S2-05-canary-seed-shim.md` — the RESCUE report that gates AC-1 / AC-2 of this story.
  - `_validation/S2-06-cost-tag-shim.md` — §"Cross-phase amendment train (gated)" describes the Phase 5 order-of-operations for AC-3.
- **Upstream files being edited:**
  - `../../04-vuln-llm-fallback-rag/final-design.md` — Phase 4 canary API section (edit gated on AC-14 unblock).
  - `../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` — `SandboxCostEntry` schema.
  - `../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` — automatic-demotion text.
  - `../../../roadmap.md` — global `bench_score.mean` invariant + Phase 6.5 §Exit criteria row 7 preservation.
- **New file landed by this story (only when AC-14 unblocks):**
  - `../../04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md` (or its rescue-path successor; name / scope TBD by ADR-0005 amendment).

## Goal

Land the three currently-landable cross-phase amendments (Phase 5 ADR-0010 field + backlink; Phase 5 ADR-0016 clarification; roadmap invariant) plus the per-amendment CHANGELOG entries and a data-driven amendment manifest, all on the branch that ships Phase 6.5, such that:
- Every landable amendment is present on disk and CI-checkable by grep against ADR-0009-signature substrings, not by prose keywords that appear elsewhere.
- The two currently-blocked amendments (AC-1 / AC-2, Phase 4 canary) are explicitly staged behind the owed ADR-0005 amendment and do not silently drift.
- The pattern (`_amendment_manifest.py` + directory-per-family tests) is set up such that Phase 7's future amendment story adds one manifest row + one file, no edits to Phase 6.5's test file.

## Acceptance criteria

**BLOCKED-PARTIAL — gated on Phase 6.5 ADR-0005 amendment:**

- [ ] **AC-1 (BLOCKED — gated on AC-14):** `docs/phases/04-vuln-llm-fallback-rag/final-design.md` is edited to document the canary-seed pinning API in the shape prescribed by the *amended* ADR-0005. Under a "kwarg" rescue path, the section names the added Phase 4 kwarg + default + behavior note. Under a "consume existing `nonce_source` seam" rescue path (see F-COV-7), AC-1 becomes: the section names the deterministic-nonce injection pattern with a Phase 4 code reference to `FenceWrapper.__init__(nonce_source=...)`. Either way, the section names the authoritative ADR.
- [ ] **AC-2 (BLOCKED — gated on AC-14):** `docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-<slug>.md` exists (new file) documenting the canary-seed strategy in Nygard form (Status, Context, Options, Decision, Tradeoffs, Consequences, Reversibility, Evidence) with the Phase-6.5-family header block (**Status:**, **Date:**, **Tags:**, **Related:** — mirror `Phase 6.5 ADR-0005`'s shape verbatim). Cross-links Phase 6.5 ADR-0005 (post-amendment). Names the structural test that pins the deterministic pinning behavior.
- [ ] **AC-14 (precondition for AC-1 / AC-2 unblock):** Phase 6.5 ADR-0005 is amended (or superseded) to name the actual Phase 4 shipped seam (`FenceWrapper(nonce_source: Callable[[], HexNonce])` per `_validation/S2-05-canary-seed-shim.md`); the amendment ADR-row is present on the branch. On amendment landing, AC-1 / AC-2 are re-scoped in the same PR by the executor, per the two rescue-path shapes named in AC-1.

**Landable now:**

- [ ] **AC-3:** `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` is amended (additive section) to declare `bench_invocation: bool = False` on `SandboxCostEntry` and document the `CODEGENIE_BENCH_INVOCATION_TAG` env-var read in `CostEmitter`. The amendment cites Phase 6.5 ADR-0007 as origin and notes the Phase 13 filter contract. **Precondition:** Phase 5 S7-03 has landed `src/codegenie/sandbox/cost.py` (per S2-06 §"Cross-phase amendment train (gated)").
- [ ] **AC-3b:** Phase 5 ADR-0010's `**Related:**` header line gains a pointer to `../../06.5-per-task-class-eval-harness/ADRs/0007-bench-invocation-tagging-on-sandbox-cost-entry.md`. Grep-asserted independently of the amendment-section presence check (bidirectional-link discipline, symmetric to ADR-0016 ↔ ADR-0009).
- [ ] **AC-4:** `docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md §"Decision §4"` is amended with a paragraph containing the ADR-0009-signature substring `'automatic' refers to the verdict recomputation` (verbatim, single-quoted); the ADR's `**Related:**` header line or "Amended by:" block gains a pointer to `../../06.5-per-task-class-eval-harness/ADRs/0009-automatic-demotion-as-recommendation-shift.md`.
- [ ] **AC-5a (repo-wide invariant):** `bench_score.mean` (regex `bench_score\.mean\b`) returns **zero hits** in `docs/roadmap.md`. Guards against future editors reintroducing the point-estimate signal as a promotion gate.
- [ ] **AC-5b (positive-presence anchor):** The exact substring `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` appears at least once in `docs/roadmap.md` (currently at Phase 6.5 §Exit criteria row 7, ~line 189). Guards against a well-meaning "cleanup" that deletes the Phase 7 hard-precondition anchor.
- [ ] **AC-6 (CHANGELOG audit trail):** `docs/phases/06.5-per-task-class-eval-harness/CHANGELOG.md` exists (create if absent; append if present) and contains one line per amendment matching the pattern `- <YYYY-MM-DD> <ADR-NNNN>: <target relative path> — <one-line rationale>`. Minimum four rows once AC-1/AC-2 unblock; three rows in the meantime (AC-3, AC-4, AC-5a/5b as one row). The doc-level trail is CI-verifiable; commit-message discipline stays a Notes hint.
- [ ] **AC-7 (working-tree presence gate, scope-corrected):** each of the §Files-to-touch paths marked *landable* is present in the working tree on the branch that ships this story. The phase-close gate ("all four amendments merged before Phase 6.5 closes") lives in `phase-arch-design.md §"What's next"`, not here.
- [ ] All ACs' associated tests exist under `tests/docs/cross_phase_amendments/`, were committed at red, and are now green for all landable ACs.
- [ ] `ruff format --check`, `ruff check`, and `pytest tests/docs/cross_phase_amendments/ --no-cov` clean on touched files.

## Implementation outline

1. **Data-first: land the amendment manifest.** Create `tests/docs/cross_phase_amendments/__init__.py` and `tests/docs/cross_phase_amendments/_amendment_manifest.py` with a frozen tuple listing each amendment: `(source_adr: str, target_path: Path, required_substrings: tuple[str, ...], forbidden_substrings: tuple[str, ...])`. Two rows initially LANDABLE, two rows GATED on AC-14 (marked with a `landable: bool` field). This is the *data*; the tests iterate over it.
2. **Land `test_phase65_amendments.py`.** One `@pytest.mark.parametrize` over the manifest, one test per required-substring per amendment. Also one test asserting `_amendment_manifest.py` collects the expected count (regression fence against silent row deletion). Run the suite red *before* touching any upstream file — it must fail for the correct reason (substring missing), not for import errors.
3. **Phase 5 ADR-0010 amendment (AC-3, AC-3b).** Add new section header `## Amendment — bench-invocation tagging (Phase 6.5)` at the bottom of the ADR; document the field + env-var read; cross-link Phase 6.5 ADR-0007. Additive only — do not delete or restructure the original Decision section. Add the backlink in `**Related:**`. Rerun the manifest tests; the AC-3 and AC-3b rows turn green.
4. **Phase 5 ADR-0016 amendment (AC-4).** Insert one paragraph after §"Decision §4" containing the substring `'automatic' refers to the verdict recomputation`. Update the `**Related:**` block to list `Amended by: [Phase 6.5 ADR-0009](../../06.5-per-task-class-eval-harness/ADRs/0009-automatic-demotion-as-recommendation-shift.md)`. Manifest tests for AC-4 turn green.
5. **Roadmap invariant (AC-5a, AC-5b).** No edits should be needed (current roadmap already satisfies both). Add the tests; they should turn green immediately on the current tree. If red: the executor found real drift — fix by restoring the missing text, do not weaken the assertion.
6. **CHANGELOG (AC-6).** Create `docs/phases/06.5-per-task-class-eval-harness/CHANGELOG.md`; add one row per landed amendment.
7. **AC-1 / AC-2 stay BLOCKED.** Do not touch `docs/phases/04-vuln-llm-fallback-rag/final-design.md` or create ADR-P4-006 in this story. Flag the phase architect via a `_lessons.md` entry or spawn-task; the ADR-0005 amendment lands under a separate story (probably a new S2-05a or an executor-authored rescue). When ADR-0005 lands, re-run this story with AC-1 / AC-2 unblocked.

## TDD plan — red / green / refactor

### Files

- `tests/docs/cross_phase_amendments/__init__.py` — empty (package marker).
- `tests/docs/cross_phase_amendments/_amendment_manifest.py` — data:
  ```python
  from __future__ import annotations
  from dataclasses import dataclass
  from pathlib import Path

  REPO = Path(__file__).resolve().parents[3]


  @dataclass(frozen=True)
  class Amendment:
      source_adr: str           # e.g. "0007" (Phase 6.5 ADR-NNNN driving this edit)
      target_path: Path         # absolute path to file being edited
      required_substrings: tuple[str, ...]
      forbidden_substrings: tuple[str, ...] = ()
      landable: bool = True     # False = gated (AC-14 unblock)
      gate: str = ""            # explanation when landable=False


  MANIFEST: tuple[Amendment, ...] = (
      Amendment(
          source_adr="0007",
          target_path=REPO / "docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md",
          required_substrings=(
              "bench_invocation",
              "CODEGENIE_BENCH_INVOCATION_TAG",
              "0007-bench-invocation-tagging-on-sandbox-cost-entry",  # backlink (AC-3b)
          ),
      ),
      Amendment(
          source_adr="0009",
          target_path=REPO / "docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md",
          required_substrings=(
              "'automatic' refers to the verdict recomputation",
              "0009-automatic-demotion-as-recommendation-shift",
          ),
      ),
      Amendment(
          source_adr="0002",
          target_path=REPO / "docs/roadmap.md",
          required_substrings=("bench_score.lower_bound_95 ≥ tier_threshold[bronze]",),
          forbidden_substrings=("bench_score.mean",),
      ),
      # AC-14-gated (Phase 4 final-design edit)
      Amendment(
          source_adr="0005",
          target_path=REPO / "docs/phases/04-vuln-llm-fallback-rag/final-design.md",
          required_substrings=(),  # populated when AC-14 unblocks
          landable=False,
          gate="Phase 6.5 ADR-0005 amendment (see _validation/S2-05-canary-seed-shim.md)",
      ),
      # AC-14-gated (new ADR-P4-006 file)
      Amendment(
          source_adr="0005",
          target_path=REPO / "docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-canary-seed-kwarg.md",
          required_substrings=(),
          landable=False,
          gate="Phase 6.5 ADR-0005 amendment (see _validation/S2-05-canary-seed-shim.md)",
      ),
  )
  ```
- `tests/docs/cross_phase_amendments/test_phase65_amendments.py`:
  ```python
  from __future__ import annotations
  import re
  from pathlib import Path
  import pytest
  from ._amendment_manifest import MANIFEST, REPO


  LANDABLE = [a for a in MANIFEST if a.landable]
  GATED = [a for a in MANIFEST if not a.landable]


  @pytest.mark.parametrize("amendment", LANDABLE, ids=lambda a: a.source_adr + ":" + a.target_path.name)
  def test_landable_amendment_required_substrings(amendment):
      assert amendment.target_path.exists(), f"{amendment.target_path} missing"
      text = amendment.target_path.read_text()
      for needle in amendment.required_substrings:
          assert needle in text, f"required substring {needle!r} not in {amendment.target_path}"


  @pytest.mark.parametrize("amendment", LANDABLE, ids=lambda a: a.source_adr + ":" + a.target_path.name)
  def test_landable_amendment_forbidden_substrings(amendment):
      if not amendment.forbidden_substrings:
          pytest.skip("no forbidden substrings declared")
      text = amendment.target_path.read_text()
      for needle in amendment.forbidden_substrings:
          # Regex \b to avoid false positives on longer identifiers.
          assert re.search(rf"{re.escape(needle)}\b", text) is None, (
              f"forbidden substring {needle!r} present in {amendment.target_path}"
          )


  @pytest.mark.parametrize("amendment", GATED, ids=lambda a: a.source_adr + ":" + a.target_path.name)
  def test_gated_amendment_documented(amendment):
      assert amendment.gate, "gated amendment must document its unblock precondition"
      # Structural check only — no file assertion (the target file may not exist yet).


  def test_phase65_changelog_present_and_named_amendments():
      p = REPO / "docs/phases/06.5-per-task-class-eval-harness/CHANGELOG.md"
      assert p.exists(), "Phase 6.5 CHANGELOG.md missing"
      text = p.read_text()
      # One row per landable amendment (looser: name each source ADR).
      for a in LANDABLE:
          assert f"ADR-{a.source_adr}" in text or a.source_adr in text, (
              f"CHANGELOG missing an entry for ADR-{a.source_adr}"
          )


  def test_manifest_count_matches_expected_shape():
      # Regression fence: manifest was five rows on validation day (three landable + two gated).
      # Any row removal must be a conscious ADR / story action.
      assert len(MANIFEST) >= 5
      assert len(LANDABLE) >= 3
      assert len(GATED) >= 2
  ```

### Red

Before any amendment lands: the LANDABLE manifest rows fail on missing required substrings (Phase 5 ADR-0010 missing `bench_invocation`, Phase 5 ADR-0016 missing the ADR-0009 signature phrase). The roadmap invariant tests pass immediately (already-satisfied state). The CHANGELOG test fails because the file does not exist. Commit at red.

### Green

Land the four (three landable) amendments per §Implementation outline. Each amendment turns exactly the corresponding parametrized test cases green. When all three LANDABLE amendments land + the CHANGELOG rows exist, the LANDABLE test suite is green. GATED tests remain green (they test structural discipline, not file presence).

### Refactor

- Extract the `_amendment_manifest.py` import path to a comment naming the future extension point ("Phase 7 will land `test_phase7_amendments.py` alongside this file, reusing `Amendment` / `MANIFEST` shape from `_amendment_manifest.py` promoted to `tests/docs/cross_phase_amendments/_types.py` if the manifest data across phases is ever mixed").
- Verify the inserted markdown is well-formed (headers in order; no broken cross-links).
- The Phase 5 ADR-0010 amendment is *appended* as a new section, not interleaved into Decision/Tradeoffs — readers should see "Amendment — bench-invocation tagging (Phase 6.5)" as a clearly-bounded addition.
- On AC-14 unblock: land Phase 4's amendment shape (per the amended ADR-0005) + populate the two GATED rows' `required_substrings`, flip `landable=True`; the same parametrized test asserts them. Zero test-code change (Open/Closed at the manifest layer).

## Files to touch

| Path | Landability | Why |
|---|---|---|
| `docs/phases/05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md` | LANDABLE (AC-3, AC-3b) | Append "Amendment — bench-invocation tagging (Phase 6.5)" section; add backlink in `**Related:**` |
| `docs/phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` | LANDABLE (AC-4) | Clarification paragraph after Decision §4 with ADR-0009-signature substring; "Amended by" cross-link |
| `docs/roadmap.md` | LANDABLE (AC-5a, AC-5b) | No edit expected; test suite asserts invariant + positive-presence anchor (already satisfied) |
| `docs/phases/06.5-per-task-class-eval-harness/CHANGELOG.md` | LANDABLE (AC-6) | New file — one line per landed amendment |
| `tests/docs/cross_phase_amendments/__init__.py` | LANDABLE | Package marker (new) |
| `tests/docs/cross_phase_amendments/_amendment_manifest.py` | LANDABLE | Data (new) — one row per amendment |
| `tests/docs/cross_phase_amendments/test_phase65_amendments.py` | LANDABLE | Test suite (new) — iterates the manifest |
| `docs/phases/04-vuln-llm-fallback-rag/final-design.md` | **BLOCKED** (AC-1, gated on AC-14) | Edit — document the amended-ADR-0005 canary-seed strategy |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/ADR-P4-006-<slug>.md` | **BLOCKED** (AC-2, gated on AC-14) | New Nygard ADR (slug TBD by ADR-0005 amendment shape) |

## Out of scope

- **Editing Phase 4's source code** for canary-seed pinning — that landed / will land in S2-05's bundled code work under the *rescued* shape (per `_validation/S2-05-canary-seed-shim.md`). This story is the *documentation* amendment; the code change rides with S2-05's rescue.
- **Editing Phase 5's `SandboxCostEntry` Pydantic model** — same — landed / will land in S2-06 once Phase 5 S7-03 ships `src/codegenie/sandbox/cost.py`.
- **Updating production ADRs** (`docs/production/adrs/*`) — Phase 6.5 does not touch the production-target reference folder for this work; future phases consuming these contracts may.
- **Fence-CI assertions on task-class registration** — S7-01.
- **Audit chain integration** — S7-02.
- **Amending Phase 6.5 ADR-0005** — separate work owned by the phase architect (AC-14 precondition). This story flags the need; it does not perform the amendment.

## Notes for the implementer

- **AC-1 / AC-2 are gated on Phase 6.5 ADR-0005 amendment.** Do NOT invent a Phase 4 kwarg shape on your own. Under the current (defective) ADR-0005, landing `Canary.mint(seed=...)` prose into Phase 4's final-design would put a lie on disk — Phase 4 actually shipped `FenceWrapper(nonce_source: Callable[[], HexNonce])`. If you find yourself editing Phase 4 files during this story, stop and check `_validation/S2-05-canary-seed-shim.md §"Owner of unblock"`.
- **The `_amendment_manifest.py` pattern is intentional and at rule-of-three.** Phase 6.5 is site 1; Phase 7's cross-phase amendments (adapter registry ADR handoffs) are the prescribed site 2; Phase 8 (hierarchical planner) site 3 per roadmap. That means the manifest earns its abstraction now (Rule 2 — three similar lines *is* the trigger, not the ceiling). Do NOT extract to `codegenie.docs.amendment_manifest` production module yet — the manifest is *test infrastructure*, not runtime. Elevation is a Phase 7 or Phase 8 decision.
- **Prefer four PRs over one bundled PR.** Each amendment targets a directory owned by a distinct CODEOWNERS group. A single PR that touches Phase 4 + Phase 5 + roadmap + Phase 6.5 will bounce off cross-team review. Split by target directory; merge in a train. If you must bundle, get pre-review sign-off from both Phase 4 and Phase 5 CODEOWNERS in advance.
- **This story is deliberately data-driven, not schema-parsed.** The amendments are *prose*; the artifact IS the prose. Grep-anchored substring assertions are the honest oracle — parsing the ADRs as structured data would introduce a shell over a core that has no shape (functional core / imperative shell — the "shell" here is one `read_text()` call). Rule 2 (Simplicity First).
- **Cross-phase CODEOWNERS review is the long-pole risk.** If any of the LANDABLE amendments is still under review at Step 7, the phase-close checklist in `phase-arch-design.md §"What's next"` catches it; this story just makes the on-disk state visible in CI.
- **The Phase 5 ADR-0016 amendment is interpretive, not additive.** Reading A vs Reading B in ADR-0009. The clarification paragraph must not appear to *change* what the original ADR said — it must read as "clarifying what was always meant." If the wording suggests retroactive policy change, the Phase 5 CODEOWNERS will (correctly) push back. Anchor phrase: `'automatic' refers to the verdict recomputation` — from ADR-0009's own text.
- **Roadmap AC-5a/AC-5b tests pass on the current tree.** If your first test run has them red, it's real drift — investigate, do not weaken the assertion. The `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` anchor at line ~189 is load-bearing for Phase 7's exit-criterion invariant.
- **Commit-message discipline** (advisory, not gated): each amendment commit should name the originating Phase 6.5 ADR by number. Example: `docs(phase5): amend ADR-0010 with bench_invocation tagging (Phase 6.5 ADR-0007)`. Not verified in CI (F-COV-5 fix); the CHANGELOG.md entry is the CI-verifiable audit trail.
- **`Rule 12 Fail loud` applies to the merge train.** If any LANDABLE amendment isn't green by the time this story is "ready to merge", the phase is not actually ready. Surface it; don't merge ahead of the upstream amendments.
- **When ADR-0005 unblocks:** re-open this story, populate the two GATED manifest rows' `required_substrings` (based on the shape the amended ADR-0005 prescribes), flip `landable=True`, and add ADR-1 / ADR-2 rows to the CHANGELOG. Zero test-code change required (Open/Closed at manifest layer).
