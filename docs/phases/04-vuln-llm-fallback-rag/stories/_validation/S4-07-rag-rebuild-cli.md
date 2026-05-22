# Validation report: S4-07 — `codegenie rag rebuild [--reembed]`

**Validated:** 2026-05-22
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-07 ships the `codegenie rag rebuild [--reembed]` operator command that reconstructs the
derived chromadb sqlite from the canonical YAML records (ADR-0016: YAML canonical, sqlite
derived; Gap 1: corruption-recovery operator path). The story's core — the byte-identical
golden test (`store.digest()` == `manifest.chain_head` after rebuild) — is strong and
mutation-aware. The validation found **one block** (a stale cross-story assumption that would
break CI the moment the story lands), **six hardens**, and **one nit**. All were fixed in
place; the story is now HARDENED and ready for `phase-story-executor`.

The dominant finding: S4-07's `Notes §1` instructs the executor to "widen the import-linter
contract" that scopes `_phase4_local_capability_mint`. But S4-06 was hardened *away* from an
import-linter contract — import-linter operates at module granularity and cannot target a
function symbol — and now ships an `ast`-walk fence (`tests/fence/test_capability_mint_scoped.py`)
instead. S4-07's rebuild CLI reuses `_phase4_local_capability_mint` from a module
(`src/codegenie/rag/cli.py`) outside that fence's allowlist, so S4-06's fence fails as soon
as S4-07 lands. The story now names the real control and adds AC-13 to widen the fence
allowlist additively.

> Methodology note: this story was validated with inline multi-lens analysis (Coverage,
> Test-Quality, Consistency, Design-Patterns) rather than four separate critic subagents —
> a deliberate efficiency choice made because a concurrent scheduled-task run had already
> consumed S4-06 mid-session and budget was constrained. The four lenses below were each
> applied; the cross-story consistency check against the *hardened* S4-06 was the highest-value
> pass and was done directly against the committed S4-06 acceptance criteria.

## Findings by critic

### Consistency critic

- **C1 (block) — `Notes §1` references a control that does not exist.** `Notes §1` says
  "S4-06's import-linter contract pins the mint symbol … widen the contract." S4-06's
  hardened AC-6/AC-7/AC-8 ship an `ast`-walk fence (`tests/fence/test_capability_mint_scoped.py`,
  allowlist `{src/codegenie/rag/ingest.py, src/codegenie/gates/**}`) and explicitly state
  import-linter *cannot* target the mint function. S4-07's rebuild CLI lives at
  `src/codegenie/rag/cli.py` and reuses `_phase4_local_capability_mint` — outside the fence
  allowlist. An executor following `Notes §1` literally would hunt for a non-existent
  import-linter block; an executor that ships `cli.py` without touching the fence breaks
  `make check`. *Fix:* rewrote `Notes §1` to name the `ast` fence; added **AC-13** (widen the
  fence allowlist to admit `src/codegenie/rag/cli.py`); added the fence file to *Files to touch*.
- **C2 (harden) — AC-2 hedged between two capability-construction approaches.** AC-2 offered
  a new `_rebuild_capability` mint *or* reuse of `_phase4_local_capability_mint`; Implementation
  Outline §4 used `_phase4_local_capability_mint`; `Notes §1` said reuse. Three messages, one
  decision needed. *Fix:* de-hedged AC-2 to a single path — reuse `_phase4_local_capability_mint`
  (one mint inside the Module Boundary, not two). `Notes §1` reinforces: no parallel
  `_rebuild_capability`, no hand-constructed `SolvedExampleWriteCapability(...)` in production.

### Coverage critic

- **Cov1 (harden) — "transactional all-or-nothing" overclaimed for `--reembed`.** The story
  claims rebuild is transactional (Out of scope, `Notes §3`). True for default mode (canonical
  YAML read-only, only derived `chroma/` mutated, and only after the dry-run pass). False for
  `--reembed`, which rewrites each `records/<id>.yaml` *in place mid-loop* — a failure on
  record N leaves `0..N-1` already re-embedded on disk. *Fix:* clarified `Notes §3` and the
  Out-of-scope "Resume-on-failure" item — `--reembed` is **not** atomic but **is** idempotent
  (AC-6 pins same-embedder determinism), so a mid-loop failure is recovered by a full re-run.
- **Cov2 (harden) — destructive-op guard prescribed in `Notes §9` but unenforced.** `Notes §9`
  describes an `rmtree` safety check (path-under-root, not a symlink, not `/`) and invokes
  Rule 12, but no AC verified it — an executor could skip it, leaving an unguarded
  `shutil.rmtree` under an operator-supplied `--root` that can wipe a disk. *Fix:* added
  **AC-12** — observable contract: `rmtree` outside `--root` (symlink / escape) → exit 1 +
  `"refusing to remove"`; unit test `test_rebuild_rmtree_guard.py` drives both rejection cases.
- **Cov3 (nit) — `1`-on-chromadb-write-failure exit code untested.** AC-1 defines exit `1`
  for "YAML *or* chromadb error"; AC-8 exercises only the YAML branch. *Fix:* added a
  follow-on test `test_rag_rebuild_chromadb_write_failure_exit_1`.

### Test-Quality critic

- **TQ1 (harden) — AC-5 "deleted and recreated" not mutation-resistant.** A rebuild that
  *skips* `shutil.rmtree` and re-adds on top of the existing sqlite still passes the digest
  assertion (chroma dedups by ID) and still leaves a `chroma/` dir present. The deletion is
  the corruption-recovery contract of AC-4 and must be proven independently. *Fix:* AC-5 now
  seeds a sentinel file (or corrupt `chroma.sqlite3`) into `chroma/` before rebuild and
  asserts it is gone afterward — kills the "rebuild skips `rmtree`" mutant.
- **TQ2 (harden) — AC-6 `--reembed` test asserts *that* it changed, not *what*.** A bare
  `chain_head_v2 != chain_head_v1` passes for any unrelated cause (record reorder, dropped
  field). *Fix:* AC-6 now also re-reads each record YAML and asserts `embedding_model` equals
  the new embedder digest and `embedding_vector` length is 384 — intent-verifying.
- **TQ3 (harden) — AC-8 "`chroma/` unchanged" unverifiable as worded.** Same gap as TQ1 in
  the failure direction. *Fix:* AC-8 + its follow-on test now seed `_pre_rebuild_sentinel`
  and assert it *survives* the exit-1 abort, proving the dry-run pass aborted before `rmtree`.

### Design-Patterns critic

- Clean. The story already exhibits correct discipline: rule-of-three deferral on
  `ChromaPersistentStore.from_canonical` ("only if the path repeats"); sync wrapper +
  `asyncio.run` body (functional shell); `_dry_run_parse` extraction tied to a real
  contract (AC-8 transactional); explicit YAGNI rejection of a `--dry-run` flag (`Notes §7`)
  and a progress UI (Out of scope). The C2 resolution (reuse the one mint, widen the one
  fence — no parallel `_rebuild_capability`) is also the design-patterns-correct call:
  extension by addition, one symbol inside the Module Boundary. No new abstraction warranted;
  none added.

## Conflict resolutions

No critic-vs-critic conflicts. C2's resolution (reuse `_phase4_local_capability_mint`) was
independently endorsed by the Design-Patterns lens (one mint, additive fence widening) — they
agree, not conflict.

## Edits applied

| # | Edit | Source finding |
|---|---|---|
| 1 | `Status: Ready → HARDENED`; `Validation notes` block added; `Depends on:` now names S4-06 + the fence file | — |
| 2 | `Notes §1` rewritten — names the `ast` fence, not a non-existent import-linter contract; bans parallel `_rebuild_capability` / hand-constructed capability | C1 |
| 3 | AC-2 de-hedged to a single capability path (`_phase4_local_capability_mint` reuse) | C2 |
| 4 | **AC-12 added** — `rmtree` refuses to delete outside `--root` (observable; exit 1 + `"refusing to remove"`) | Cov2 |
| 5 | **AC-13 added** — additively widen `tests/fence/test_capability_mint_scoped.py` allowlist to admit `src/codegenie/rag/cli.py`; fence suite stays green | C1 |
| 6 | AC-5 hardened — seeded sentinel proves `rmtree` actually ran | TQ1 |
| 7 | AC-6 hardened — assert each record's `embedding_model` digest + vector length, not just `chain_head` inequality | TQ2 |
| 8 | AC-8 hardened — seeded sentinel proves the dry-run aborted before `rmtree` | TQ3 |
| 9 | `Notes §3` + Out-of-scope "Resume-on-failure" clarified — `--reembed` is idempotent-recoverable, not atomically transactional | Cov1 |
| 10 | Follow-on tests added — `test_rag_rebuild_chromadb_write_failure_exit_1`, `test_rebuild_rmtree_guard_refuses_escape`; AC-8 follow-on now sentinel-based | Cov3, Cov2, TQ3 |
| 11 | *Files to touch* — added `tests/fence/test_capability_mint_scoped.py` and `tests/unit/rag/test_rebuild_rmtree_guard.py` | C1, Cov2 |

## Verdict rationale

HARDENED, not RESCUE: the story's **goal** (rebuild the derived store from canonical YAML,
proven by a byte-identical digest golden test) is sound, traces cleanly to ADR-0016 + Gap 1,
and is unchanged. The one block finding is a stale *cross-story assumption* (S4-07 was written
against a pre-hardening picture of S4-06's mint-scope control) with a clean, additive in-place
fix — exactly the HARDENED case. The six hardens were ordinary AC-strengthening and
test-mutation-resistance edits. No AC was renumbered; AC-12/AC-13 were appended.

## Cross-story note (for the S6-03 / S4-06 owners — not edited here)

While cross-checking S4-06, the consistency pass surfaced two latent S4-06 ↔ S6-03 mismatches
that are **out of scope for this story** and were not edited: (a) sibling story S6-03 has
`FallbackTier` (`src/codegenie/fallback/tier.py`) import `_phase4_local_capability_mint`, but
that path is **not** in S4-06's fence allowlist `{rag/ingest.py, gates/**}` — S6-03 will need
the same additive fence-widening AC-13 applies here; (b) S6-03's expected `SolvedExampleHarvested`
field set (`{plan_outcome_digest, repo_snapshot_sha, solved_example_id}`) does not match the
class S4-06 AC-9 defines. Both should be reconciled when S6-03 is validated.

## Recommended next step

`phase-story-executor` to implement S4-07. The executor must read the *hardened* S4-06
(`tests/fence/test_capability_mint_scoped.py` is the mint-scope control) and apply AC-13's
additive fence-allowlist widening as part of this story.
