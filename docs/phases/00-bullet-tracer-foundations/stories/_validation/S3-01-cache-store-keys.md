# Validation report: S3-01 — Cache store + two-level keys (Gap 1 anchor)

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S3-01-cache-store-keys.md`](../S3-01-cache-store-keys.md)

## Summary

S3-01 is the Step 3 cache-store landing: it ships `cache/keys.py` (the two-level schema-versioning scheme per ADR-0003), `cache/store.py` (`CacheStore.get/put/key_for` over a JSONL index + sharded blob tree per ADR-0011 mode bits and ADR-0001 hashing), and the Gap-1 regression test that pins per-probe surgical invalidation. The story's goal and shape are correct, and the regression test framing (rewrite probe B's sub-schema `$id`, assert probe A's key is unchanged) is exactly the right anchor.

Three critics returned 18 findings (3 block, 12 harden, 3 nit). Zero `NEEDS RESEARCH` tags — every finding was answerable from in-repo docs (ADR-0001, ADR-0003, ADR-0004, ADR-0011, `phase-arch-design.md` §Component design / §Edge cases / §Gap analysis, S2-03 / S2-05 validated stories). The validator applied 11 in-place edits: a Validation notes block under the header, ADR-0004 added to the honored-ADRs line, AC-5 split into a four-row miss-matrix table (corruption / SHA-256-mismatch / missing-blob / TTL-stale), six new ACs appended (cold-start, round-trip, index-record-schema, fallback, last-write-wins, mode-bits + record-size guard, hashing chokepoint extension, `declared_inputs_for`), the TDD red-section rewritten end-to-end with twelve mutation-resistant snippets, Files-to-touch expanded with `src/codegenie/hashing.py` and `tests/unit/test_hashing.py` as a surgical chokepoint extension, and four implementer-notes additions (declared_inputs_for shape, hashing-helper extension policy, index record schema, `CacheError` policy).

Two architectural inconsistencies surfaced as follow-ups (not auto-fixed — out of scope for in-place editing):
1. `phase-arch-design.md §Component design — CacheStore` (line ~496) references `content_hash_of_declared_inputs` without defining where the glob-to-Path resolution happens.
2. The same section does not name where the blob-content BLAKE3 hash (filename) is computed; the chokepoint discipline implies `hashing.py` extension.

## Findings by critic

### Coverage critic

7 findings:

- **C-F1 (block) — Three of the four AC-5 miss paths are unobservable.** AC-5 names corruption, hash-mismatch, missing-blob, and TTL-stale, but the TDD plan only pins corruption-via-zero-bytes. A `CacheStore` that skips the SHA-256 verification step survives every existing test. A `CacheStore` that ignores TTL survives. A `CacheStore` that returns garbage on orphan-index-record survives. The three paths are independent code paths, each needs its own test.
- **C-F2 (block) — Round-trip happy path unpinned.** No AC or test asserts `put(key, output); got = get(key); got == output`. A `put` that silently returns (no file write, no index append) passes every existing test — the corruption tests are *miss* tests, not *hit* tests. Mutation-killer missing.
- **C-F3 (harden) — Cold-start (`get` against nonexistent `index.jsonl`) not tested.** The first `gather` on a fresh checkout hits this every time. The arch says miss-on-error, but missing-file-on-read is not exception-shaped in Python `open()`; coverage of this path is needed.
- **C-F4 (harden) — `per_probe_schema_version` fallback not tested.** Implementation outline says "fall back to envelope on `FileNotFoundError`" but no test pins it. A fallback that raises (or returns `""`) survives.
- **C-F5 (harden) — Last-write-wins on multi-record not specified.** The implementation step says "find the latest record with matching `key`" but no test asserts that *most-recent* wins over *first*. A `get` walk that breaks on the first match (instead of scanning all and taking the last) passes none of the corruption tests but silently caches stale data.
- **C-F6 (harden) — Record-size guard not testable.** Implementation outline references `PIPE_BUF=4096` B but no AC or test pins what `put` does when a serialized record would exceed that. Silent truncation? Append-and-tear-the-line? Phase 0 doesn't trigger this; Phase 14's webhook fan-out will.
- **C-F7 (nit) — `index.jsonl` mode `0600`.** The existing `test_post_write_modes_are_0700_0600` walks all files; an explicit pin for `index.jsonl` specifically (not just "every file under cache_dir") makes the "forgot to chmod the index" mutant catchable in isolation.

### Test-Quality critic

7 findings:

- **TQ-F1 (block) — `test_get_returns_none_on_corrupt_blob` covers only the truncation case.** The test body uses "truncate to 0 bytes" which produces `json.JSONDecodeError`. The *interesting* corruption is "valid JSON but wrong SHA-256" — that's the case that catches the "implementation forgot to verify SHA-256" mutant. The named AC says "hash mismatch" — needs its own snippet.
- **TQ-F2 (harden) — `test_atomic_write_no_partial_visible` assertion is brittle.** The current snippet says "only the .tmp was left" — but this is implementation-detail leak. The invariant is "no partial file at the FINAL path"; whether `.tmp` is cleaned up on failure or left behind is an orthogonal design choice. Rewritten to assert only the load-bearing invariant.
- **TQ-F3 (harden) — Index-record schema thin.** No test pins what the JSONL line *contains*. A `put` that writes only `{"key": ...}` (no `blob_sha256`) and a `get` that doesn't verify SHA-256 mutually pass — but the artifact contract is broken for S3-06's `AuditWriter`.
- **TQ-F4 (harden) — Cache log events partially pinned.** AC says emit `cache.blob.invalid` / `cache.stale` / `cache.miss`. The existing snippet only checks `cache.blob.invalid`. Cache `cache.stale` and `cache.miss` are downstream-observable signals (Phase 8's Trust gates, Phase 13's cost ledger) — needs explicit log-event assertions.
- **TQ-F5 (harden) — `declared_inputs_for(probe, snapshot)` is undefined.** Implementation outline §1 calls it; no module, no test fixture. Executor will guess. The helper has a clear shape (rglob each pattern against `snapshot.root`, sort + dedupe + skip-missing) and belongs in `cache/keys.py`. Pin it.
- **TQ-F6 (harden) — Hashing-helper gap.** `cache/store.py` needs BLAKE3-of-bytes (filename) and SHA-256-of-bytes (tamper-check). Existing `hashing.py` exports `content_hash(Path)` and `identity_hash(*strings)` — neither takes raw bytes. ADR-0001 chokepoint says no other file imports `blake3` / `hashlib.sha256`. The story must extend `hashing.py` (surgical addition, two functions) or the executor will either bypass the chokepoint or kludge a path-write-then-read.
- **TQ-F7 (nit) — TDD snippets use `...  # detail in implementation` placeholders.** The invalidation-scope tests are *the* load-bearing test of Gap 1; the body cannot be deferred to implementation. Rewritten with arrange/act/assert in-line — even if the synthetic-probe scaffolding stays as comments, the assertion shape must be pinned.

### Consistency critic

4 findings:

- **CN-F1 (block) — ADR-0004 missing from honored list.** The story produces the `blob_sha256` field that S3-06's `AuditWriter` consumes as the audit anchor (ADR-0004 §Decision). The story body mentions blob_sha256 in implementer notes but ADR-0004 is not in the header. Added.
- **CN-F2 (harden) — `content_hash_of_declared_inputs` arch reference under-specifies the helper.** `phase-arch-design.md §Component design — CacheStore` (line ~496) names the cache-key derivation as `identity_hash(probe.name, probe.version, schema_version, content_hash_of_declared_inputs)`. The arch never names where the *glob-to-Path* resolution happens. Story's `declared_inputs_for(probe, snapshot)` closes the gap; surface as a doc-correction follow-up so arch and story align.
- **CN-F3 (harden) — `CacheError` raise policy collides with "never raises to coordinator".** `phase-arch-design.md §Component design / Failure behavior` says CacheStore never raises to the coordinator. New AC-12 (record-size guard) deliberately raises `CacheError` — but only at the in-process `put` precondition layer, before any state mutation. Implementer notes pin this distinction so the coordinator doesn't grow a misleading `except CacheError`.
- **CN-F4 (informational) — All ADR references resolve.** ADR-0001 (BLAKE3 content / SHA-256 identity), ADR-0003 (per-probe schema versioning), ADR-0004 (audit anchor), ADR-0011 (`0700`/`0600` mode bits, re-applied post-write). Decisions match the story's claims; no contradiction.

## Research briefs

**None.** Stage 3 was skipped — zero `NEEDS RESEARCH` tags. Every finding was answerable from in-repo docs and the prior validated stories (S2-03 hashing, S2-05 registry/schema/audit).

## Conflict resolutions

**Coverage F1 ≡ Test-Quality F1** (corruption test only covers truncation): merged into the AC-5 four-row miss-matrix and three distinct test snippets (`test_get_none_on_corrupt_blob_zero_bytes`, `test_get_none_on_blob_sha256_mismatch`, `test_get_none_on_missing_blob`).

**Coverage F2** (round-trip unpinned): one new AC + one new snippet (`test_put_then_get_returns_equivalent_output`).

**Coverage F4 ≡ Test-Quality F5** (fallback + helper undefined): two new ACs and one new snippet each — `per_probe_schema_version` fallback test and `declared_inputs_for` resolution AC.

**Test-Quality F6 ≡ Consistency CN-F1** (hashing-helper gap + ADR-0004 missing): one new AC pins the chokepoint extension; ADR-0004 added to the honored line; the dual cache_key + blob_sha256 anchors story now traces cleanly to S3-06 / ADR-0004.

**Test-Quality F2** (atomic-write assertion brittleness): the rewritten snippet asserts the load-bearing invariant ("final blob path is never visible after a mid-write failure") and drops the implementation-detail ".tmp was left" claim.

## Edits applied

### Edit 1 — `Validation notes` block added under the story header
- **Source:** validator convention.
- **What:** New `## Validation notes` block (verdict, finding totals, summary of edits, surfaced architectural inconsistencies).
- **Rationale:** Breadcrumb for the next reader.

### Edit 2 — ADR-0004 added to `ADRs honored` line
- **Source:** Consistency CN-F1.
- **Rationale:** The `blob_sha256` field this story writes is the audit anchor S3-06 reads (ADR-0004 §Decision). The trace was implicit in implementer notes; making it header-level keeps cross-story dependencies legible.

### Edit 3 — AC-5 split into a four-row miss-matrix table
- **Source:** Coverage F1 + Test-Quality F1.
- **Before:** A single AC bullet collapsing four paths together with one log event tag.
- **After:** A markdown table with one row per path (5a corruption / 5b SHA-256 mismatch / 5c missing blob / 5d TTL-stale), each with its testing recipe and its named log event. Each row becomes a separate snippet in the rewritten TDD plan.
- **Rationale:** Mutation-killing matrix: the executor cannot ship a CacheStore that skips SHA-256 verification, ignores TTL, or doesn't handle orphan records without one of the four tests failing.

### Edit 4 — AC-6: cold-start path pinned
- **Source:** Coverage F3.
- **Rationale:** `get` against a fresh `cache_dir` is hit on every first-run. The path returns `None` + `cache.miss`; the dir is auto-created `0700`. Pinned by `test_get_none_on_cold_start_no_index`.

### Edit 5 — AC-8: round-trip happy path
- **Source:** Coverage F2.
- **Rationale:** Without this, a `put` that silently no-ops passes every other AC's test. The `put → get → equal` assertion is the load-bearing positive case.

### Edit 6 — AC-9: index record schema pinned
- **Source:** Test-Quality F3 + Consistency CN-F1.
- **Rationale:** Names the six required fields and the `json.dumps(..., sort_keys=True, separators=(",", ":"))` serialization shape. `blob_sha256` traces to ADR-0004's audit anchor; `created_at_unix_s` is what AC-5d compares against.

### Edit 7 — AC-10: `per_probe_schema_version` fallback pinned
- **Source:** Coverage F4.
- **Rationale:** Implementation outline mentions the fallback; without an AC, a fallback that raises or returns `""` survives. Test included.

### Edit 8 — AC-11: last-write-wins on multi-record
- **Source:** Coverage F5.
- **Rationale:** A `get` walk that returns the first match passes corruption tests but silently caches stale data after a re-`put`. Tested by `test_last_write_wins_on_multi_record`.

### Edit 9 — AC-12: index.jsonl mode + record-size guard
- **Source:** Coverage F6 + Coverage F7.
- **Rationale:** PIPE_BUF=4096 invariant for atomic `O_APPEND` (edge case #12) is now defended in code, not just in implementer prose. `index.jsonl` mode `0600` is asserted separately from the rglob-everything assertion.

### Edit 10 — AC-13: hashing-chokepoint extension
- **Source:** Test-Quality F6.
- **Rationale:** Resolves the latent ADR-0001 chokepoint violation. `cache/store.py` needs to hash bytes (BLAKE3 for blob filename, SHA-256 for tamper-check); existing `hashing.py` exports only path-based and string-based helpers. Surgical extension: two new functions, two new tests, ADR-0001 invariant ("no other file imports `blake3` / `hashlib.sha256`") preserved.

### Edit 11 — AC-14: `declared_inputs_for(probe, snapshot)` pinned
- **Source:** Test-Quality F5.
- **Rationale:** Story called this helper from Implementation outline §1 but never defined it. Now pinned to `cache/keys.py`, resolved via `rglob` against `snapshot.root`, sorted + de-duped + skip-missing. Phase 1's six probes consume this contract directly.

### Edit 12 — TDD red-section rewritten end-to-end
- **Source:** Coverage F1/F2/F3/F4/F5 + Test-Quality F1/F2/F3/F4/F7.
- **What:** Twelve mutation-resistant snippets replace the four prior placeholder-heavy snippets. Each new snippet pins one mutant (corruption-2-flavors / hash-mismatch / orphan-blob / TTL-stale / cold-start / round-trip / multi-record / index-schema / atomic / mode-bits-incl-index / record-size-guard / fallback). Helper functions (`_store_with_key`, `_make_output`, `_resolve_blob_path`) are named in-line so the executor can scaffold them in one place.
- **Rationale:** Test bodies are no longer `...  # detail in implementation`; each load-bearing invariant has a concrete assertion shape. Mutation thinking: the rewrites enumerate the mutants each test kills.

### Edit 13 — Files-to-touch expanded
- **Source:** Test-Quality F6 + Test-Quality F5.
- **Rationale:** Adds `src/codegenie/hashing.py` (extension), `tests/unit/test_hashing.py` (extension), and annotates that `cache/keys.py` also owns `declared_inputs_for`. The executor sees the full file set at planning time.

### Edit 14 — Implementer notes extended (four additions)
- **Source:** Test-Quality F5/F6 + Consistency CN-F2/F3 + Test-Quality F4.
- **What:** Adds notes on (a) `declared_inputs_for` resolution semantics, (b) hashing-helper extension policy + parity test, (c) full index record schema, (d) log-event policy (`cache.miss` / `cache.stale` / `cache.blob.invalid`), (e) `CacheError` raise policy (only the in-process record-size precondition, never to the coordinator).
- **Rationale:** Surfaces the resolution to every ambiguity the critics flagged, so the executor doesn't guess.

## Verdict rationale

**HARDENED.** The story's goal — landing the Gap-1 surgical-invalidation fix and the JSONL+sharded-blob `CacheStore` — is intact and correctly framed. The findings clustered around (1) three of four miss paths being unobservable from the existing TDD plan, (2) the happy-path round-trip never being pinned, (3) two referenced helpers (`declared_inputs_for`, byte-hash variants of `content_hash` / `identity_hash`) being undefined, and (4) the index record schema being implicit. All four classes are fixable in place: add ACs for the missing invariants, rewrite the TDD red-section with mutation-killing snippets, pin the helper shapes in `cache/keys.py` and `hashing.py`. No `block` finding required rewriting the story's goal or scope. The story is now mutation-resistant on every load-bearing dimension that Phase 14's continuous-gather model and ADR-0004's audit-anchor consumers depend on.

## Recommended next step

`phase-story-executor` to implement.

**Follow-ups (separate work — not blocking this story):**

1. Edit `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md §Component design — CacheStore` (line ~496) to name `declared_inputs_for(probe, snapshot)` as the glob-to-Path resolution helper.
2. Edit the same section to note that the blob-content BLAKE3 hash (filename) is computed via `hashing.content_hash_bytes`, not by re-reading the file after write.
3. Future: consider whether `Probe.declared_resource_budget` (Gap 3 from `phase-arch-design.md`) should land alongside `declared_inputs_for` — both are coordinator-vs-probe contract shapes that the cache layer reads. Out of scope for S3-01.
