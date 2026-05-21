# Validation report: S1-07 — `test_kernel_frozen.py` guard

**Validated:** 2026-05-21
**Verdict:** RESCUE
**Validator version:** phase-story-validator v1

## Summary

S1-07 asks for a Step-1 structural fence proving "Phase 4 ships zero edits to the
Phase 0/1/2/3 kernel." That *intent* is sound and traces cleanly to arch §Goals
G3. But the story prescribes a **brand-new file** (`tests/fence/test_kernel_frozen.py`,
listed as `NEW` in Files-to-touch) implementing a **brand-new mechanism** — a
BLAKE3 content-snapshot in `tests/fence/_kernel_snapshot.json`, a generator script
`scripts/regenerate_kernel_snapshot.py`, an env-var skip, and a subprocess-tree-copy
mutation guard.

That collides with shipped reality and with the phase's own design:

1. **`tests/fence/test_kernel_frozen.py` already exists.** It was created GREEN by
   **Phase-3 story S1-05** (`feat(phase3/S1-05): GREEN — Phase 3 import-linter
   contracts + AST fences`; Status `Done — GREEN 2026-05-18`). It is a 25 KB,
   git-diff-against-a-pinned-baseline-SHA fence with a `_BASELINES` `Final` tuple
   and a `_KERNEL_ALLOWLIST` frozenset — **not** a BLAKE3 content snapshot.
2. **Phase-4 `final-design.md:680`** says verbatim: *"`tests/fence/test_kernel_frozen.py`
   (Phase 3, extended) — allow-list grows by Phase 4 additions; diff against
   Phase 0/1/2/3 kernel files asserts zero edits."*
3. **Phase-4 `phase-arch-design.md` §CI gates** says: *"`tests/fence/test_kernel_frozen.py`
   (allow-list extension; zero edits to Phase 0/1/2/3 kernel files)."*

Both authoritative design docs say Phase 4's contribution is an **allow-list /
baseline extension of the existing Phase-3 file**. S1-07 instead prescribes a
ground-up rewrite with an incompatible mechanism. The story's goal, all ten ACs,
the entire three-block TDD plan, the Implementation outline, and all four
Files-to-touch entries are built on the wrong mechanism and would have to be
discarded. That is a goal rewrite — `phase-story-writer` territory, not a
validator hardening pass. Hence **RESCUE**; no hardening edits applied to the
story body.

## Method note

The decisive lens here is **Consistency**, and its finding is a hard `block`
backed by primary-source quotes (final-design.md:680, arch §CI gates, the shipped
file's own header + git history). Consistency outranks Coverage, Test-Quality,
and Design-Patterns in the synthesis priority chain, and a RESCUE verdict means
**no story edits** — so the remaining three critics would only critique ACs and a
TDD plan that are about to be thrown away. To respect the token budget (global
Rule 6) the three moot critics were not spawned as separate subagents; their
lenses were applied inline and are summarised below. The Consistency analysis is
the load-bearing one and is given in full.

## Findings by critic

### Consistency critic (decisive)

#### F1 — Story rebuilds a fence that already exists; mechanism contradicts final-design + arch
- **Severity:** block
- **Smell:** Wrong task class / Duplication by addition / Stale references
- **What's wrong:** S1-07's Goal — *"Land `tests/fence/test_kernel_frozen.py` +
  an adjacent `_kernel_snapshot.json` ... capturing the BLAKE3 digest of every
  kernel file in scope"* — and its Files-to-touch table (all four rows marked
  `NEW`) treat `test_kernel_frozen.py` as a greenfield deliverable. It is not.
  Phase-3 S1-05 shipped it GREEN on 2026-05-18. The shipped file is a
  git-diff-against-baseline-SHA design (`_BASELINES`, `_KERNEL_ALLOWLIST`,
  ADR-0011 "audit + lint" framing, shallow-clone self-heal). Phase-4
  `final-design.md:680` and `phase-arch-design.md` §CI gates both state Phase 4's
  job is to **extend** that file's allow-list / baselines — "(Phase 3, extended)",
  "(allow-list extension)". S1-07 instead invents a parallel BLAKE3
  content-snapshot mechanism (`_kernel_snapshot.json` + `regenerate_kernel_snapshot.py`).
  Two fences, two mechanisms, one filename — they cannot both occupy
  `tests/fence/test_kernel_frozen.py`.
- **Proposed fix:** Re-author the story. The goal must become *"extend the
  existing Phase-3 `tests/fence/test_kernel_frozen.py` so it also diffs against
  the Phase-3 kernel state"* — see "Recommended rewrite" below.
- **Confidence:** high
- **Source:** `final-design.md:680`; `phase-arch-design.md` §CI gates (≈line 989);
  `tests/fence/test_kernel_frozen.py:1-35` (header + `_BASELINES`); `git log
  --follow tests/fence/test_kernel_frozen.py` → `feat(phase3/S1-05): GREEN`;
  `docs/phases/03-vuln-deterministic-recipe/stories/S1-05-phase3-fence-tests.md`
  (Status `Done — GREEN`).

#### F2 — Stale / fabricated reference: arch has no "Implementation-level risks" section
- **Severity:** block
- **Smell:** Stale references
- **What's wrong:** The story leans hard on `../phase-arch-design.md
  §Implementation-level risks §1` — cited in the References block, restated in
  Context, and quoted twice ("the `test_kernel_frozen.py` is a Step-1
  deliverable, not a Step-7 one"; "Quote it verbatim in the module docstring").
  `phase-arch-design.md` contains **no section named "Implementation-level
  risks"** (`grep -i risk` finds only two table rows, at lines 887 and 1071,
  neither about kernel-freezing). The story's central justification quotes a
  doc section that does not exist.
- **Proposed fix:** Drop the fabricated citation. The legitimate "land it in
  Step 1" rationale survives on its own merits (see Recommended rewrite — the
  Phase-3 baseline *can* be pinned at Phase-4 Step-1 time because Phase 3's
  kernel is frozen by then).
- **Confidence:** high
- **Source:** `grep -ni "risk" docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md`.

#### F3 — Story misreads its own References block
- **Severity:** harden (subsumed by F1 — recorded for the re-author)
- **What's wrong:** The story's References block *does* cite the corrective
  sources — `§Goals — G3` and `§Testing strategy → CI gates`. Arch §CI gates
  literally reads "(allow-list extension)". The writer had the right text in
  hand and still prescribed a from-scratch BLAKE3 rebuild. The re-author must
  honour the qualifier, not just the filename.
- **Confidence:** high
- **Source:** story References block vs. `phase-arch-design.md` §CI gates.

### Coverage critic (inline — moot under RESCUE, recorded for the re-author)

The AC set is internally well-formed and verifiable *for the wrong mechanism*. If
re-pointed at the existing git-diff fence, most ACs evaporate: AC-1/AC-2
(`_kernel_snapshot.json` shape + regenerator) have no analogue — the existing
fence pins a 40-char SHA in `_phaseN_baseline.txt`, not a per-file digest map;
AC-5's env-var skip and AC-6/AC-7's subprocess-tree-copy mutation guard are
BLAKE3-snapshot-specific. The one coverage idea worth carrying forward: the
existing file's `test_helpful_error_names_baseline_file_and_adr_amendment`
already discharges S1-07's AC-4 intent (fail-loud diagnostic naming the baseline
file + ADR) — the re-authored story should *assert the phase-3 row is covered by
that existing diagnostic*, not re-specify it.

### Test-Quality critic (inline — moot under RESCUE, recorded for the re-author)

The shipped fence is already parametrized over `_BASELINES`
(`test_baseline_file_is_a_real_40_char_sha`,
`test_baseline_resolves_to_ancestor_of_head_and_is_not_head`,
`test_phase3_has_not_modified_phase012_kernel_outside_allowlist`,
`test_diff_status_classification`). Adding a `("phase-3", ...)` row to
`_BASELINES` makes every one of those parametrized cases *automatically* cover
the new baseline — the re-authored story gets mutation-resistant coverage for
free and needs only: (a) a test asserting `_phase3_baseline.txt` exists and
resolves to a real ancestor SHA, and (b) a planted-violation test proving an
out-of-allowlist edit to a Phase-3 kernel file is caught. The story's proposed
bespoke BLAKE3 mutation guard (one pytest subprocess per file, explicitly called
"deliberately slow") is redundant against the existing parametrized suite.

### Design-Patterns critic (inline — moot under RESCUE, recorded for the re-author)

This is the cleanest illustration of the **Duplication-by-addition** anti-pattern
(`critic-design-patterns.md` §3; `production/adrs/0043`). The existing file was
*built to be extended* — its own header comment reads: *"Baselines — `Final`
tuple keyed by phase name so adding `_phase3_baseline.txt` at Phase-4 time is a
one-row append (Open/Closed at the file boundary)."* The Phase-3 author left a
labelled extension seam specifically for this Phase-4 story. S1-07 ignores the
seam and clones the whole fence under a divergent mechanism — "extension by
addition" misread as "never touch the original." The correct move is the
one-row append the seam was designed for. No new abstraction, no new script, no
new dep surface — Rule 2 (Simplicity First) strongly favours the extension over
the rebuild.

## Research briefs

None. No finding was tagged `NEEDS RESEARCH`; the conflict is resolved entirely
by reading shipped docs and code.

## Conflict resolutions

No inter-critic conflict. All four lenses point the same direction: extend the
existing Phase-3 fence; do not rebuild it. Consistency is decisive and the other
three concur.

## Edits applied

None to the story body — RESCUE verdict. Per the skill's RESCUE rule the
validator does not rewrite a story whose goal is wrong. The only change to the
story file is an additive `## Validation notes` marker block under the header and
a `Status:` flip to `RESCUE`, so `phase-story-executor` does not pick up a story
known to contradict the phase design, and a human sees the routing. The Goal,
all ACs, the Implementation outline, the TDD plan, Files-to-touch, Out-of-scope,
and Notes-for-implementer are left byte-for-byte intact for the re-author to use
as raw material.

## Verdict rationale

RESCUE. Three `block`-severity findings, two of them structural: the story
rebuilds a fence that already exists (F1) and justifies itself with a
non-existent doc section (F2). The fix is not an AC tweak — it is a new goal, a
new mechanism, a new Files-to-touch table, and a new TDD plan. That is what
`phase-story-writer` produces, not what `phase-story-validator` edits in place.

## Recommended rewrite (input for `phase-story-writer`)

The genuine Phase-4 S1-07 work is small and additive:

- **Goal:** Extend the existing Phase-3 `tests/fence/test_kernel_frozen.py` so it
  also diffs the working tree against the **Phase-3** kernel state — add a
  `("phase-3", Path("tests/fence/_phase3_baseline.txt"))` row to the `_BASELINES`
  `Final` tuple, and create `tests/fence/_phase3_baseline.txt` pinning the
  40-char SHA of the Phase-3-complete kernel. The mechanism stays git-diff +
  baseline SHA + ADR-0011 audit/lint framing — no BLAKE3 content snapshot, no
  generator script, no env-var skip.
- **`_KERNEL_ALLOWLIST`:** Determine (Rule 8) whether Phase 4 touches *any*
  Phase-0/1/2/3 kernel file at all. It likely does not — `PlanOutcome` is
  Phase-4-local (ADR-0004), the LLM/RAG deps land via a *new* fence file
  `test_pyproject_fence_phase4.py` (ADR-0003), and `src/codegenie/fallback/` +
  `src/codegenie/rag/` are new non-kernel paths. If Phase 4 adds zero kernel
  edits, S1-07 collapses to just the baseline-row append; the allow-list grows
  only for a genuine, ADR-amended kernel edit.
- **Sequencing:** `_phase3_baseline.txt` can only be pinned once Phase 3's kernel
  is final. Phase 3 is the immediately-prior phase, so by Phase-4 Step 1 the
  Phase-3 kernel SHA is knowable — the "Step-1 deliverable" framing holds without
  the fabricated arch citation. Add an explicit `Depends on:` note for Phase-3
  completion.
- **Files to touch:** `tests/fence/test_kernel_frozen.py` (EDIT — one-row append
  to `_BASELINES`) and `tests/fence/_phase3_baseline.txt` (NEW — pinned SHA).
  Drop `scripts/regenerate_kernel_snapshot.py` and `_kernel_snapshot.json`
  entirely.
- **Tests:** Lean on the file's existing `_BASELINES`-parametrized suite (a new
  row is covered automatically). Add only: a baseline-resolves-to-real-ancestor
  assertion for the phase-3 row, and a planted-violation test proving an
  out-of-allowlist edit to a Phase-3 kernel file is caught.
- **Carry forward verbatim:** the original story's References block (it cites the
  right docs), the fail-loud diagnostic intent of AC-4 (already discharged by the
  shipped `test_helpful_error_names_baseline_file_and_adr_amendment`), and the
  Out-of-scope section.

## Recommended next step

RESCUE → re-run `phase-story-writer` for Phase-4 Step-1's `test_kernel_frozen.py`
deliverable using the "Recommended rewrite" section above as the brief, then
re-validate. Do **not** send S1-07 to `phase-story-executor` in its current form
— it would either fail (the file already exists) or, worse, clobber the shipped
Phase-3 fence with an incompatible mechanism.
