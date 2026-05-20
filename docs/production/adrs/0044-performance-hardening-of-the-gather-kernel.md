# ADR-0044: Performance hardening of the gather kernel

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** performance · memory · concurrency · kernel · migration · fences
**Related:** ADR-0043, ADR-0011, ADR-0001, ADR-0007

## Context

A performance, memory, and concurrency review of the `codegenie gather`
pipeline and the `vuln-index` ingest path surfaced a set of issues in
already-shipped Phase 0/1/2/3 code:

1. **Redundant filesystem walks.** The cache-key derivation, the per-probe
   input snapshot, and probe bodies each walk the repo tree independently;
   `Path.rglob`/`glob` cannot prune descent, so every walk descends into
   `node_modules`.
2. **`tree-sitter` `Parser`/`Query` rebuilt per file** in the Layer-B AST
   probes — the query S-expression recompiles once per source file.
3. **`CacheStore.put` ran a full `chmod` walk of the whole cache tree on
   every call** — O(cache size) per put.
4. **`CacheStore` carried hidden state** (`_key_meta`) that grew unbounded
   over a process lifetime and coupled `put` to a prior `key_for`.
5. **`get_index_record` re-parsed the entire append-only `index.jsonl`** on
   every cache lookup — O(history) per probe.
6. **The probe cache key was content-blind** — keyed on `(path, st_size)`,
   so a same-size content edit returned a stale cached result.
7. **`vuln-index` ingest committed one transaction per row** plus a separate
   `SELECT changes()` per row, on an autocommit sqlite connection.
8. **The async coordinator serialized in-process work** — the per-probe
   prelude is synchronous blocking I/O on the event loop thread, and
   CPU-bound probe loops never yield, so `asyncio.wait_for` timeouts cannot
   fire.

Fixing these requires editing the existing components. A faster `CacheStore`
is still `CacheStore`; you cannot optimize an existing component by adding a
parallel one without forking behaviour. This is precisely the "genuinely
horizontal change" case [ADR-0043](0043-extension-by-addition-means-no-silent-edits.md)
names: a *migration* — a loud, reviewed, all-at-once sweep across existing
code — is the sanctioned path, distinct from a silent edit.

## Decision

Authorize a bounded **performance migration** of the gather kernel. Every
edit in scope is either behaviour-neutral (byte-identical observable output)
or a strict correctness improvement; none changes a probe's facts. The work
ships as a sequence of independently-reviewable commits, each gated by the
full conformance suite (unit + integration + adversarial + fence + golden).

The migration touches these Phase 0/1/2 kernel files; each is added to
`_KERNEL_ALLOWLIST` in `tests/fence/test_kernel_frozen.py` with an `# adr:`
reference to this ADR:

- `src/codegenie/cache/store.py` — scope the mode re-walk to `__init__`;
  replace the `_key_meta` side-channel with explicit `put` arguments; serve
  the index from an in-memory map guarded by `index.jsonl` size.
- `src/codegenie/cache/keys.py` — derive the cache key from the input
  snapshot's content hashes (content-addressed); add an explicit
  `_CACHE_KEY_VERSION` constant.
- `src/codegenie/coordinator/coordinator.py` — reorder snapshot/key
  derivation; offload the blocking per-probe prelude via `asyncio.to_thread`.
- `src/codegenie/coordinator/input_snapshot.py` — stream file hashes; match
  declared globs against the shared filesystem index.
- `src/codegenie/coordinator/file_index.py` *(new)* — one pruning `os.walk`
  per gather, shared by key derivation and the input snapshot.
- `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`,
  `src/codegenie/probes/layer_b/node_reflection.py` — build `Parser`/`Query`
  once per language; add cooperative yields so the declared timeout fires.

`src/codegenie/hashing.py` (already allowlisted) gains a content-addressed
key helper. The `vuln-index` ingest fix is outside the kernel scope
(`vuln_index/` is a Phase-3 package) and needs no allowlist entry.

Per ADR-0043, this allowlist amendment is interim: when ADR-0043's
category-based `test_no_silent_edits.py` lands, these entries fold into the
`migration` category and the per-file rows are retired.

## Consequences

- **One-time cache invalidation.** Making the cache key content-addressed
  (and adding `_CACHE_KEY_VERSION`) changes every probe's key once. Warm
  caches recompute on the first run after the change; correctness improves —
  same-size content edits are no longer silent stale hits.
- **The conformance suite is the safety net.** Behaviour-neutral edits are
  pinned by existing unit/golden tests; correctness-improving edits add
  regression tests (e.g. a same-size edit must change the key).
- **Timeout enforcement becomes real.** Cooperative yields let
  `asyncio.wait_for` cancel a CPU-bound probe at its budget; a probe that
  previously ran over budget to completion now produces the coordinator's
  low-confidence synthetic output instead. This is the intended ADR-0007
  failure-isolation behaviour.
- **`_phase2_baseline.txt` is unchanged.** The baseline stays a pre-Phase-3
  commit; the migration is recorded in the allowlist, not by moving the
  goalposts.
