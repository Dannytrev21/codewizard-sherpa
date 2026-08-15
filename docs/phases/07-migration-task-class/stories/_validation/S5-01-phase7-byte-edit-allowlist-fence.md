# Validation report — S5-01 Phase 7 byte-edit allowlist fence

**Date:** 2026-08-14
**Validator:** phase-story-validator (four-critic parallel pipeline + synthesizer)
**Verdict:** **HARDENED** — real fixable weaknesses in AC coverage and internal consistency; edits applied in place; ready for phase-story-executor.
**Story:** [`../S5-01-phase7-byte-edit-allowlist-fence.md`](../S5-01-phase7-byte-edit-allowlist-fence.md)

---

## Stage 1 — Context brief

Read:
- Story (all sections).
- `docs/phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — the ORIGINAL 10-row source of truth. Carries a 2026-05-20 amendment block deferring "grows with each phase" framing to production ADR-0043.
- `docs/phases/07-migration-task-class/ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — dated 2026-05-20; enumerates 8 additional row-categories for the Amendment-A distroless-migration gather pipeline; explicitly says the fence "grows row-by-row, each row gated by the owning ADR."
- `docs/phases/07-migration-task-class/ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md` — dated 2026-05-21; §Consequences explicitly says: *"Whoever implements S5-01 must consult this ADR and enumerate the eight [Layer C/G] files; this ADR is cross-linked from S5-01's story for that reason."* The 8 files are ALREADY in `_KERNEL_ALLOWLIST` (test_kernel_frozen.py lines 279–294) after S19-01 landed.
- `tests/fence/test_kernel_frozen.py` — the precedent fence (git-diff-against-baseline; `_KERNEL_ALLOWLIST`; `_BASELINES` parametrization; `_ensure_baseline_reachable` shallow-clone self-heal).
- `tests/fence/_phase2_baseline.txt`, `_phase3_baseline.txt` — the SHA sidecar format.

Load-bearing findings from the context read:
- The story references ADRs 0001, 0003, 0004, 0005, 0007, 0009, 0013, 0015, 0016 but **not** 0029 or 0030 — both of which materially govern this fence's row-set.
- The story's Depends-on line names S3-03 (BLOCKED per CLAUDE.md) and S4-04 (HARDENED). Rows 1–2 point at a directory that does not yet exist.
- Phase 6.5 is not fully shipped (S2-05 is BLOCKED); "the last merged Phase 6.5 commit on `main`" is not an unambiguous anchor.

## Stage 2 — Four parallel critics

Each critic returned a structured finding list. Full outputs archived in the session transcript. Summary below.

### Coverage critic

- **coverage-1 (block)** — story ignores ADR-0029; AC-2 will block Amendment-A stories.
- **coverage-2 (block)** — `plugins/PLUGINS.lock` "see Notes" is dangling.
- **coverage-3 (harden)** — S3-03 BLOCKED not flagged in story.
- **coverage-4 (harden)** — planted-violation matrix missing `T` (typechange), `C` (copy), `U` (unmerged) statuses; no symlink/submodule case.
- **coverage-5 (harden)** — AC-3.b misses "pinned to main" invariant.
- **coverage-6 (harden)** — AC-12 filename glob fragile; copy-cat file dodges.
- **coverage-7 (nit)** — ADR-parser regex brittle across ADR edits.
- **coverage-8 (nit)** — CI merge-commit HEAD not addressed.

### Test-quality critic

- **test-1 (block)** — AC-5.h "owned-new-trees" case does NOT actually exercise the seam; path is out-of-locked-surface already. Would silently pass with `_PHASE7_OWNED_NEW_TREES = ()`.
- **test-2 (block)** — glob semantics unpinned; nested depth untested; `PurePath.match` breaks silently at depth ≥ 2 on older Pythons.
- **test-3 (harden)** — AC-2.b ADR-parser scope loose; decoy numbered list under `## Consequences` would silently union into the expected set.
- **test-4 (harden)** — per-row `# row N` comments have no test that they're correct; swap catches nothing.
- **test-5 (harden)** — multi-violation error message not tested; `msg = f"...{violations[0]}..."` passes.
- **test-6 (harden)** — no test that live check delegates to `_compute_phase7_violations`; drift possible.
- **test-7 (harden)** — missing property tests (monotonicity, idempotency, metamorphic-owned-new-trees).
- **test-8 (nit)** — AC-5.i evidence has no enforcement mechanism.
- **test-9 (nit)** — AC-12 filename pattern fragile.

### Consistency critic

- **consistency-1 (block)** — ADR-0030's explicit forward-reference to S5-01 not honored; fence would fire on 8 already-shipped Layer C/G files if landed under State B.
- **consistency-2 (block)** — ADR-0029's Amendment-A row-growth not acknowledged; AC-2.a/2.b would block every Amendment-A story.
- **consistency-3 (harden)** — S3-03 BLOCKED-dependency not flagged.
- **consistency-4 (harden)** — Phase 6.5 not fully shipped; "last merged Phase 6.5 commit on main" ambiguous.
- **consistency-5 (harden)** — AC-8 grammatically self-contradicting ("is amended … no: is NOT touched").
- **consistency-6 (harden)** — `plugins/PLUGINS.lock` "see Notes" is a dangling reference.
- **consistency-7 (nit)** — AC-11 comment-only assertion drifts from "verifiable AC" bar.
- **consistency-8 (nit)** — Phase 4/5/6 baseline-skip rationale absent.

### Design-patterns critic

- **design-1 (harden)** — "Reuse the scanner" not operationalised; helpers are module-private in `test_kernel_frozen.py`.
- **design-2 (harden)** — `_LOCKED_SURFACE_GLOBS` shape diverges from `_KERNEL_SCOPE_DIRS` without stated reason.
- **design-3 (harden)** — `status: str` primitive obsession; `Violation` dataclass anaemic.
- **design-4 (nit)** — Two sources of truth handled correctly (single-source direction picked).
- **design-5 (harden)** — `_ensure_baseline_reachable` reuse opportunity pairs with design-1.
- **design-6 (nit)** — Notes' rejection of `Fence` ABC is right call but contains an inaccuracy ("one walks a diff; the other walks an AST" confuses precedent with `_phase3_fence.py`).
- **design-7 (nit)** — Evidence block schema needs template.

## Stage 3 — Researcher

**Not fired.** No critic finding tagged `NEEDS RESEARCH`. All findings had concrete, precedent-grounded proposed fixes (either from `test_kernel_frozen.py` or from the ADRs themselves).

## Stage 4 — Synthesizer + Editor

**Priority:** Consistency > Coverage > Test-Quality > Design-Patterns.

**Conflict resolution:**
- The two blocks from Consistency (ADR-0029 / ADR-0030) subsume Coverage's ADR-0029 finding and are the anchor for the AC-2 rewrite.
- Test-Quality's test-1 + test-2 blocks are independent and both applied (added AC-5.h.i/ii/iii + AC-4.b glob pinning).
- Design-Patterns's `Fence` ABC and copy-paste rationale align with Rule 2 + production ADR-0043; the story's original stance is preserved and clarified (Notes correction).
- Design's `status: str` finding accepted (added `DiffStatus = Literal[...]`); precedent's use of raw `str` is noted but not propagated (new landing has a chance to do better).

**Edits applied** (see story's `## Validation notes` block for the concise summary):
- Front-matter: ADR-0029 + ADR-0030 added.
- New `## Preconditions` section (S3-03 blocked, Phase-6.5 baseline choice, ADR-0030 State-A-vs-B decision, ADR-0029 out-of-scope-for-landing).
- AC-2 rewrite to elastic `_EXPECTED_ROW_COUNT` + `_ROW_SOURCE_ADRS` machinery; added AC-2.c row-comment integrity check.
- AC-3 hardening: origin/main reachability check + sidecar comment.
- AC-4 hardening: all git-diff statuses in scope; AC-4.a PLUGINS.lock exclusion; AC-4.b glob-matcher pinning; AC-4.c submodule doc.
- AC-5 hardening: added AC-5.j/k/l/m; split AC-5.h into three discriminating cases; formalized AC-5.i evidence schema + evidence-check test.
- AC-6 hardening: multi-violation coverage; State-B ADR-0030 string.
- AC-11 rewrite from comment-only to five property invariants.
- AC-12 hardening: added AC-12.b symbol-scan complement.
- Implementation outline: `DiffStatus` Literal alias; `Violation` frozen dataclass with `reason: Literal[...]`; `_compute_phase7_violations` pure helper; `# duplicate-of:` reuse comment; `_parse_decision_section` scoped parser.
- Notes: "terminal allowlist" nuance spelled out (file/symbol terminal but rows may grow via ADR amendment); corrected AST-vs-diff claim; documented glob-shape divergence rationale; added `Violation` dataclass discipline.
- AC-8 rewrite from self-contradicting prose to two clean clauses.
- Out-of-scope: added ADR-0029 Amendment-A rows explanation, PLUGINS.lock non-double-coverage rationale, probe-ABC contract+snapshot precedent for Phase 8+ frozen surfaces.
- Files-to-touch: standardized `_attempts/` path to match the story filename.
- Status line: `Ready` → `HARDENED (phase-story-validator, 2026-08-14)`.

**Not edited** (respect for original scope, Rule 3):
- The story's goal and load-bearing "Ship-of-Theseus defense" framing.
- The Context section (goal-scope narrative belongs to the writer, not the validator).
- The dependency-injected `diff_source` shape (already sound).
- The refusal to extract a `Fence` ABC (already sound per Rule 2 + ADR-0043).

## Strong dimensions (record for future stories to imitate)

- **Dependency injection on `diff_source`** avoids the test-leakage / working-tree-mutation trap the naive fix would fall into; also sidesteps the `subprocess.run(shell=True)` ban.
- **Terminal-allowlist framing (AC-12 + Out-of-scope)** correctly closes the ADR-0043 loop.
- **Single-source-of-truth via ADR-parser (AC-2.b)** turns doc/code drift into a loud CI failure — Fowler-grade discipline.
- **The Rule 2 refusal to extract `Fence` ABC** is exactly right; the added `# duplicate-of:` comment makes the discipline visible to future readers.
- **`_PHASE7_OWNED_NEW_TREES` vs `_PHASE7_BYTE_EDIT_ALLOWLIST` separation** — illegal-states-unrepresentable applied to sets (three cleanly distinguished conditions).

## Provenance / signatures

- Story SHA before validation: (checked HEAD of `ci-health/ruff-pin-aiohttp-uncap-vuln-index-exit-code`, unchanged since commit 48b9812).
- Critic finding-lists archived in the parent conversation transcript (four subagents completed 2026-08-14).
- Editor synthesized findings under priority Consistency > Coverage > Test-Quality > Design-Patterns.
