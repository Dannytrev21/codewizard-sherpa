# Story S1-06 — Land per-phase ADRs and the ADR-0028 amendment

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-P7-008 (this phase ADR-0001), every other Phase 7 ADR (0002–0014), production ADR-0028, production ADR-0007

## Context

The six additive seams across Phase 0–6 plus four design constraints (deferred OpenRewrite, kept-forever `RuntimeTraceProbe` stub, advisory-only `dive_efficiency`, parallel `DistrolessLedger`) plus four supporting decisions (operator-only credentials, parallel CLI verb, gate-time strace, wall-clock canary) all need explicit ADRs *before* the snapshot canary (S1-07) compiles — because `tools/snapshot_regen_audit.py` (S1-08) requires every snapshot regen to cite a per-phase ADR. This story verifies all 14 ADRs already exist on disk under `docs/phases/07-migration-task-class/ADRs/`, lands the per-phase ADR README index, cross-links them, and appends the one-paragraph amendment to production ADR-0028 that operationally defines "extension by addition."

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Executive summary` — the amendment text quoted verbatim (the paragraph this story must append to production ADR-0028).
  - `../phase-arch-design.md §Component 13` — the seam-by-seam breakdown that ADR-P7-001..006 record.
  - `../phase-arch-design.md §Path to production end state ›Deferred ADRs sharpened or made resolvable` — explicit text describing the ADR-0028 amendment.
- **Phase ADRs (all 14 are in scope; this story is the "land them all coherently" story):**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — central decision; defines the six allowed shapes.
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — gate registry.
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002.
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003.
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — pure deferral; no source diff.
  - `../ADRs/0006-runtime-trace-probe-stub-kept-forever.md` — ADR-P7-005 — pure preservation; no source diff.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — design constraint (not really a seam).
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — the enforcement mechanism (S1-07 implements).
  - `../ADRs/0010-credentials-via-docker-config-no-secretd-daemon.md` — ADR-P7-010.
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-011 — strike two of ADR-0022.
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-012.
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — ADR-P7-013.
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014.
  - `../ADRs/README.md` — the per-phase ADR index (already exists; verify it lists all 14).
- **Production ADRs (the amendment target):**
  - `../../../production/adrs/0028-task-class-introduction-order.md` — the file this story appends the amendment paragraph to.
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — referenced by ADR-P7-001/005/006 and unchanged by this story.
- **Source design:**
  - `../final-design.md §Synthesis ledger ›Departures #3` — full text the amendment paragraph compresses.
  - `../final-design.md §Roadmap coherence check` — the "Extension by addition. Honored *with explicit, named amendment*." line that ratifies the amendment.

## Goal

All 14 Phase 7 ADRs exist on disk, are linked from the per-phase ADR index, and the one-paragraph "behavior-preserving additive extension" amendment is appended to production ADR-0028 with bidirectional cross-links to ADR-P7-001..007.

## Acceptance criteria

- [ ] All 14 ADR files exist at `docs/phases/07-migration-task-class/ADRs/000{1..14}-<slug>.md`. Each has a `Status: Accepted` header and a non-empty `## Decision` section.
- [ ] `docs/phases/07-migration-task-class/ADRs/README.md` lists all 14 ADRs in numeric order with a one-line summary per ADR, mapping each to its `ADR-P7-NNN` identifier where one exists.
- [ ] `docs/production/adrs/0028-task-class-introduction-order.md` has a new section (e.g., `## Amendment 2026-05-12 (Phase 7) — behavior-preserving additive extension`) containing the verbatim amendment paragraph from `phase-arch-design.md §Executive summary` / `§Path to production end state`: *"Extension by addition permits new files, new registry entries, new optional fields on existing Pydantic models, new default-None kwargs on existing functions, and additive values in previously-closed `Literal`s — each gated by a per-phase ADR that names the exact diff and amends the contract-surface snapshot in the same PR. Behavior-changing edits to existing logic remain forbidden."*
- [ ] The amendment section in production ADR-0028 links *back* to each of ADR-P7-001 through ADR-P7-007 (i.e., relative links to `docs/phases/07-migration-task-class/ADRs/0001..0007`).
- [ ] `tests/integration/test_adr_cross_links.py` is committed and green: walks every Phase 7 ADR file under `docs/phases/07-migration-task-class/ADRs/` and asserts (a) every `[ADR-NNNN](path)` link target exists on disk, (b) every Phase 7 ADR is referenced at least once from another ADR or from `README.md`, (c) the production ADR-0028 file contains the amendment paragraph (literal substring match on a stable anchor phrase like "behavior-preserving additive extension").
- [ ] No source-code file under `src/codegenie/` is modified by this story — it is documentation-only.
- [ ] `ruff` / `mypy` not applicable to Markdown; `markdownlint` (if configured) passes on the amendment and the README.

## Implementation outline

1. List the contents of `docs/phases/07-migration-task-class/ADRs/` and confirm 14 numbered ADR files exist (`0001` through `0014`). The repo already has all 14 — this story verifies them, does not author them.
2. Read the existing `ADRs/README.md` and confirm it indexes all 14. If any ADR is missing from the index or has the wrong slug, fix the README (this is the only authorial work expected in this story).
3. Append the amendment section to `docs/production/adrs/0028-task-class-introduction-order.md`. Use exactly the paragraph text quoted above; add bullet-list links to ADR-P7-001..007 below it.
4. Write the failing test in `tests/integration/test_adr_cross_links.py` (TDD red).
5. Make it green: confirm the cross-link assertions pass after the README/index/amendment edits.
6. Refactor: add a one-line "Amended 2026-05-12 (Phase 7)" entry to the top of production ADR-0028's header if the file has a status/date header convention.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/integration/test_adr_cross_links.py`

```python
# tests/integration/test_adr_cross_links.py
import pathlib
import re

ADR_DIR = pathlib.Path("docs/phases/07-migration-task-class/ADRs")
PRODUCTION_ADR_0028 = pathlib.Path("docs/production/adrs/0028-task-class-introduction-order.md")

ADR_LINK_RE = re.compile(r"\[ADR-(P\d+-\d+|\d{4})\]\(([^)]+)\)")
RELATIVE_LINK_RE = re.compile(r"\]\(([^)]+\.md(#[^)]*)?)\)")


def _all_phase7_adr_files() -> list[pathlib.Path]:
    return sorted(p for p in ADR_DIR.glob("00*.md") if p.name != "README.md")


def test_14_phase7_adrs_exist():
    files = _all_phase7_adr_files()
    assert len(files) == 14, f"expected 14 ADRs, found {len(files)}: {[p.name for p in files]}"
    expected_prefixes = {f"{i:04d}" for i in range(1, 15)}
    actual_prefixes = {p.name.split('-')[0] for p in files}
    assert actual_prefixes == expected_prefixes


def test_every_phase7_adr_has_accepted_status_and_decision_section():
    for adr in _all_phase7_adr_files():
        text = adr.read_text(encoding="utf-8")
        assert "Status:" in text and "Accepted" in text, f"{adr.name} missing Accepted status"
        assert "## Decision" in text, f"{adr.name} missing ## Decision section"


def test_phase7_adr_relative_links_resolve():
    for adr in _all_phase7_adr_files():
        text = adr.read_text(encoding="utf-8")
        for match in RELATIVE_LINK_RE.finditer(text):
            target_str = match.group(1).split("#", 1)[0]
            target = (adr.parent / target_str).resolve()
            assert target.exists(), f"{adr.name} → {target_str} does not exist"


def test_readme_lists_all_14_adrs():
    readme = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    for i in range(1, 15):
        assert f"{i:04d}-" in readme, f"README missing reference to ADR {i:04d}"


def test_production_adr_0028_contains_phase7_amendment():
    text = PRODUCTION_ADR_0028.read_text(encoding="utf-8")
    assert "behavior-preserving additive extension" in text, (
        "Production ADR-0028 missing the Phase 7 amendment paragraph."
    )
    # The amendment must link back to every per-phase ADR-P7-001..007.
    for n in range(1, 8):
        # match either "ADR-P7-00N" or filename-style "000{N+1}-..." since the seam ADRs are 0002..0007
        # (ADR-P7-001 = file 0002, ADR-P7-002 = file 0003, …, ADR-P7-007 = file 0008).
        # Test the path form (more robust to ADR-ID drift in future renames).
        target = f"docs/phases/07-migration-task-class/ADRs/000{n+1}"
        assert target in text or f"ADR-P7-00{n}" in text, (
            f"Production ADR-0028 amendment missing link to ADR-P7-00{n}"
        )
```

Expected red failure mode: `AssertionError: Production ADR-0028 missing the Phase 7 amendment paragraph.` (the literal string "behavior-preserving additive extension" is not yet present in `0028-task-class-introduction-order.md`).

### Green — make it pass

1. Append to `docs/production/adrs/0028-task-class-introduction-order.md`:

```markdown
## Amendment 2026-05-12 (Phase 7)

**Status:** Accepted as part of Phase 7's PR; ratified by per-phase ADR-P7-008.

**Refinement of "extension by addition":** Extension by addition permits new files, new registry entries, new optional fields on existing Pydantic models, new default-None kwargs on existing functions, and additive values in previously-closed `Literal`s — each gated by a per-phase ADR that names the exact diff and amends the contract-surface snapshot in the same PR. Behavior-changing edits to existing logic remain forbidden.

**Phase 7 opens exactly six seams under this rule:**

- ADR-P7-001 — [`gate_registry.py` new file](../../phases/07-migration-task-class/ADRs/0002-register-gate-probe-new-registry.md)
- ADR-P7-002 — [`ObjectiveSignals` widened + `ALLOWED_BINARIES` + egress allowlist](../../phases/07-migration-task-class/ADRs/0003-objective-signals-widening-and-allowlists.md)
- ADR-P7-003 — [`FallbackTier.run(task_type=None)` kwarg](../../phases/07-migration-task-class/ADRs/0004-fallback-tier-task-type-kwarg.md)
- ADR-P7-004 — [OpenRewrite `rewrite-docker` deferred](../../phases/07-migration-task-class/ADRs/0005-openrewrite-rewrite-docker-deferred.md)
- ADR-P7-005 — [Phase 2 `RuntimeTraceProbe` stub preserved](../../phases/07-migration-task-class/ADRs/0006-runtime-trace-probe-stub-kept-forever.md)
- ADR-P7-006 — [`Recipe.engine` `Literal` extended with `"dockerfile"`](../../phases/07-migration-task-class/ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md)
- ADR-P7-007 — [`dive_efficiency` advisory-only design constraint](../../phases/07-migration-task-class/ADRs/0008-dive-efficiency-advisory-only.md)

Enforcement: the contract-surface snapshot canary (`tests/integration/test_contract_surface_snapshot.py` + `tools/contract-surface.snapshot.json` + `tools/snapshot_regen_audit.py`) blocks any PR that drifts the contract surface without a linked per-phase ADR in the same PR.
```

2. Verify `docs/phases/07-migration-task-class/ADRs/README.md` indexes all 14 ADRs with one-line summaries. If the index is incomplete, add the missing entries — the writing was done in earlier steps; this is the verify-and-fix-the-index pass.

### Refactor — clean up

- Add a "See also" link from `ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` to the new amendment section in production ADR-0028 (anchor-link if `0028` has section anchors).
- Run `markdownlint` (or whatever the repo's Markdown linter is) over the touched files; fix only the warnings introduced by this story.
- Confirm `git diff` on `docs/phases/07-migration-task-class/ADRs/` shows zero meaningful content changes for ADRs 0001–0014 (this story does not edit ADR bodies; it edits only README and production ADR-0028).

## Files to touch

| Path | Why |
|---|---|
| `docs/production/adrs/0028-task-class-introduction-order.md` | Append the amendment section with bidirectional links to ADR-P7-001..007. |
| `docs/phases/07-migration-task-class/ADRs/README.md` | Verify/fix the index to list all 14 ADRs with one-line summaries. |
| `tests/integration/test_adr_cross_links.py` | New test — TDD red anchor; verifies all 14 ADRs exist + amendment present + cross-links resolve. |

## Out of scope

- **Authoring any of the 14 ADR files from scratch** — they already exist on disk (the `phase-architect` skill landed them in an earlier pass). This story is the *verify-and-amend* step.
- **Editing ADR bodies (other than fixing the index)** — load-bearing decisions are already recorded; refining wording is a separate task.
- **The contract-surface snapshot or `snapshot_regen_audit`** — S1-07 and S1-08 own those.
- **Linking the amendment from `CLAUDE.md`** — the project-level CLAUDE.md is out of scope for this story; if a reviewer requests it, raise as a follow-up.
- **Adding ADRs from later phases that *also* amend ADR-0028** — Phase 8's first amendment will be Phase 8's PR; this story is Phase 7-only.

## Notes for the implementer

- The amendment paragraph **must** be byte-identical to the wording in `phase-arch-design.md §Executive summary` (and repeated in `§Path to production end state ›Deferred ADRs`). Reviewers will diff. Use the version above verbatim.
- ADR-P7-001..007 are the *seam* ADRs; ADR-P7-008 is ADR-0001 (the parent decision); ADR-P7-009..014 are this-phase-only ADRs (canary, credentials, ledger, CLI verbs, gate-time strace, wall-clock canary). The amendment only needs to link the *seam* ADRs (001..007). ADR-P7-009 (snapshot canary) is referenced from the "Enforcement" sentence at the bottom of the amendment.
- File numbering vs ADR ID is offset by one in this phase: file `0002-register-gate-probe-...` is ADR-P7-001 (the gate registry); file `0008-dive-efficiency-...` is ADR-P7-007 (the advisory-only constraint). The test's link-existence check uses file paths, not ADR IDs — that's the more robust check.
- Production ADR-0028 is a **load-bearing** document. Append cleanly; do not rewrite or restructure the existing body. The amendment section is a *new section appended to the bottom*; everything above it remains byte-stable.
- Reviewer pushback on the amendment is the single biggest risk for this story (per `High-level-impl.md §Implementation-level risks #1`). Pre-write the rationale in the PR description: link to `final-design.md §Departures #3` (which is the synthesizer's deliberation) and to `phase-arch-design.md §Path to production end state` (which carries the verbatim amendment text). If review prefers the strict zero-edit alternative, fall back to `final-design.md §Departures #5` (parallel `MigrationFallbackTier`, parallel engine enum) and re-plan from Step 2 — but that re-plan is a *new story*, not a silent revision of this one.
- The cross-link test's literal substring check on "behavior-preserving additive extension" is the cheapest possible "amendment exists" assertion. It is intentionally fragile-to-wording (so wording drift is loud) and indifferent to formatting (so reflows pass). If the reviewer requests a wording change, update the substring check too.
- Markdown link paths in the amendment use `../../phases/07-migration-task-class/ADRs/...` — relative to `docs/production/adrs/`. Verify the links render on GitHub before merging (some repos use root-relative paths instead — match precedent in `docs/production/adrs/`).
