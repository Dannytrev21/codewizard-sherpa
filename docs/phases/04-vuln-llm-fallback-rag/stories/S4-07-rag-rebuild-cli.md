# Story S4-07 — `codegenie rag rebuild [--reembed]` reconstructs chroma deterministically from canonical YAML

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** M
**Depends on:** S4-03 (chromadb adapter + `digest()` projection), S4-04 (canonical YAML records + manifest with `chain_head`)
**ADRs honored:** ADR-0016 (canonical YAML + derived sqlite; `codegenie rag rebuild` is the operational-recovery command; `--reembed` triggers re-embedding for model upgrade), Gap 1 (operator path for chromadb-corruption recovery)

## Context

ADR-0016 §Decision elevates YAML records to canonical and chromadb sqlite to derived — **rebuildable** via `codegenie rag rebuild`. Gap 1 (arch §Gap analysis) names the operator path: when chromadb is corrupted, schema-upgraded, or model-upgraded, the operator runs `rag rebuild` to reconstruct chromadb from the canonical `<root>/records/*.yaml` + `manifest.yaml` files.

Two modes:

- **`codegenie rag rebuild`** (default) — reads each canonical YAML, re-inserts into chromadb using the **stored** `embedding_vector` from the record (no embed work). Fast — bounded by chromadb's `collection.add` cost.
- **`codegenie rag rebuild --reembed`** — re-embeds each record's `query_text` via the current `Embedder` (`FastembedEmbedder.embed_batch` from S4-01 + S4-02's cache); used when an embedding-model upgrade has happened (edge case #3) and existing records carry stale `embedding_model` digests. Slower (~80 ms per uncached record; cache helps re-runs).

The load-bearing **golden test** (`tests/integration/test_phase4_rag_rebuild_idempotent.py`): after `rag rebuild`, `store.digest()` is byte-identical to the pre-rebuild value (and to `manifest.chain_head`). This pins the design's content-addressed integrity claim.

This story also covers chromadb-corruption recovery shape:

- **Corruption detected** at next `ChromaPersistentStore` open → log + raise `StoreCorrupted`; operator runs `codegenie rag rebuild` (which deletes `<root>/chroma/` first, then reconstructs).
- The CLI exit codes: `0` on success; `1` on YAML parse error or chromadb-write failure; `2` on `manifest.yaml` missing (operator nudge: nothing to rebuild from).

The CLI lives under `src/codegenie/rag/cli.py` (extends S4-01's `embeddings bootstrap` module) — keep the path-scoped fence green; `chromadb` and `fastembed` admitted there.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7` — "Canonical source is YAML at `.codegenie/rag/records/<id>.yaml`; chroma sqlite is **derived** (rebuildable via `codegenie rag rebuild`)"; `digest()` = BLAKE3-rolled head over canonical records.
  - `../phase-arch-design.md §"Resilience and operations"` (line 839) — `codegenie rag rebuild` reconstructs chromadb from canonical YAML.
  - `../phase-arch-design.md §"Gap 1"` (line 1086 area) — explicit operator path: rebuild reads canonical YAML; carries embedding_model digest + vector; reconstructs sqlite **without re-embedding**; `--reembed` is the explicit opt-in for model-upgrade scenarios.
  - `../phase-arch-design.md §Edge case #3` — embedding model drift → operator runs bootstrap + `rag rebuild` (no `--reembed` if vectors carry the new model already; `--reembed` if migrating from old vectors).
  - `../phase-arch-design.md §Failure modes` — chromadb sqlite corrupted → `SolvedExampleStore.open()` raises `StoreCorrupted` → RagDegraded path; operator runs `codegenie rag rebuild`.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — full decision; rebuild is the operational-recovery contract.
- **Source design:**
  - `../final-design.md §Component 7` — rebuild path; storage budget.
- **Existing code (precedent to mirror):**
  - `src/codegenie/rag/cli.py` (S4-01's `embeddings bootstrap`) — extend with the `rag rebuild` subcommand here; the CLI module already lives under the path-scoped admission.
  - `src/codegenie/cli/__init__.py` (or equivalent) — top-level CLI entry-point.
  - Phase-1/2 CLI subcommand precedents (`codegenie gather`, `codegenie audit verify`).

## Goal

Ship `codegenie rag rebuild [--reembed]` CLI that reads `<root>/records/*.yaml` + `manifest.yaml`, deletes `<root>/chroma/`, reconstructs each chromadb collection in **insertion order** (per `manifest.records`), and asserts the post-rebuild `store.digest()` byte-equals `manifest.chain_head` — golden integration test pins the byte-identity.

## Acceptance criteria

- [ ] **AC-1 — `codegenie rag rebuild` CLI subcommand wired.** New subcommand under `src/codegenie/rag/cli.py`, exposed via the top-level CLI as `codegenie rag rebuild`:
    ```
    codegenie rag rebuild [--root <path>] [--reembed]
    ```
    Defaults: `--root .codegenie/rag/`. Exit codes: `0` success; `1` on YAML / chromadb error; `2` on manifest missing (no-op-with-message).
- [ ] **AC-2 — Default mode reuses stored vectors.** Without `--reembed`:
    - Reads `manifest.yaml`; iterates `manifest.records` in order.
    - For each record ID: reads `<root>/records/<id>.yaml` → `SolvedExample.from_yaml(...)` (S4-04 added).
    - Calls `await store.add(example, capability=_rebuild_capability(example.provenance.workflow_id, example.provenance.event_chain_head))` — using a **rebuild-only** capability mint that lives **in the CLI module** so the import-linter contract continues to admit it (or alternatively reuses `_phase4_local_capability_mint`, scoped via the existing contract since `src/codegenie/rag/cli.py` is under `src/codegenie/rag/` — see Notes §1).
    - Uses the **stored** `example.embedding_vector` field — does **not** call `embedder.embed()`. (Pass the vector to a per-rebuild internal `store._add_with_precomputed_vector(example, vec, capability)` helper, or rely on `SolvedExample.embedding_vector` being persisted in the YAML and consumed by `store.add` — verify S4-04's posture.)
- [ ] **AC-3 — `--reembed` re-embeds and updates the record's `embedding_model` digest.** With `--reembed`:
    - Constructs the current `FastembedEmbedder` (S4-01) and `CachedEmbedder` wrapper (S4-02).
    - For each record: re-derives `query_text` from the record (the indexed text; persisted in YAML per S4-04 schema), calls `embedder.embed(text)`, writes the new vector + updates `record.embedding_model = embedder.model_digest()`, re-writes the canonical YAML (via `_atomic_write_text`), then adds to chromadb.
    - **`manifest.chain_head` recomputes** after re-embedding because canonical YAML bytes changed (vectors and `embedding_model` digest both in the YAML) — write the updated manifest at the end.
- [ ] **AC-4 — Pre-rebuild chromadb is fully removed.** Before re-inserting records:
    - If `<root>/chroma/` exists → `shutil.rmtree(<root>/chroma/)`; log `store.rebuild.chroma_removed`.
    - Then construct a fresh `ChromaPersistentStore(root_dir=<root>)` and proceed with adds.
    - This is the corruption-recovery path: even a corrupted sqlite is replaced wholesale.
- [ ] **AC-5 — Post-rebuild golden: `store.digest() == manifest.chain_head` (byte-identical).** `tests/integration/test_phase4_rag_rebuild_idempotent.py`:
    - Seeds a fresh store with 3 hand-built `SolvedExample` instances (`make_solved_example` from S4-03's fixture); records the pre-rebuild `manifest.chain_head` and `store.digest()`.
    - Runs `codegenie rag rebuild` (invoke the CLI function directly, not via subprocess — keeps the test fast).
    - Re-opens the store; asserts the post-rebuild `store.digest() == pre_rebuild_chain_head == pre_rebuild_digest` (transitive byte-identity).
    - Asserts the `chroma/` directory was deleted and recreated.
- [ ] **AC-6 — `--reembed` updates digest deterministically.** Same integration shape as AC-5 but with `--reembed`:
    - Pre-rebuild: capture `manifest.chain_head_v1`.
    - Run `rag rebuild --reembed` with the (potentially new) embedder digest.
    - Post-rebuild: assert `store.digest() == manifest.chain_head_v2` (the new chain head after canonical YAML rewrite); assert `chain_head_v2 != chain_head_v1` (the YAML bytes changed — embedding_model digest column updated).
    - **Run the rebuild twice consecutively**: assert the second run is a no-op in the sense that the post-second-run digest equals the post-first-run digest (re-embedding the same texts with the same embedder produces the same vectors; idempotent).
- [ ] **AC-7 — Manifest missing → exit 2 with diagnostic.** Empty `<root>/`:
    - CLI exits with code 2.
    - stderr contains the literal substring `"no manifest.yaml found"` and a pointer to `docs/operations/rag.md`.
    - chromadb directory **not** created (rebuild is meaningless without canonical source).
- [ ] **AC-8 — YAML parse error → exit 1, name the offending file.** Corrupt one `<root>/records/<id>.yaml` (e.g., `b"\xff\xff malformed"`):
    - CLI exits with code 1.
    - stderr names the offending file path verbatim.
    - chromadb directory **not** modified — the rebuild is transactional at the directory level (delete-then-add; the delete happens only after all YAML records are successfully parsed in a dry-run pass). See Implementation Outline §4.
- [ ] **AC-9 — `StoreCorrupted` raised on next-open is the operator nudge.** `tests/unit/rag/test_store_corruption_on_open.py`:
    - Write a 1-byte garbage file to `<root>/chroma/chroma.sqlite3` (the chromadb sqlite location).
    - Construct `ChromaPersistentStore(root_dir=<root>)`; expect `StoreCorrupted` from the lazy-open path (or `_load_existing_record_ids` if it touches chromadb).
    - Diagnostic includes `"codegenie rag rebuild"` literally.
- [ ] **AC-10 — `make` target.** Add `make rag-rebuild` target (or document the `python -m codegenie rag rebuild` invocation) for operator convenience; mirror Phase 1/2 CLI exposure patterns.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **`src/codegenie/rag/cli.py`** gains a `rebuild` Typer/click command (matching the existing CLI framework choice). Subcommand signature:
   ```python
   def rebuild(root: Path = Path(".codegenie/rag/"), reembed: bool = False) -> int: ...
   ```
   Returns the exit code; the top-level CLI translates to `sys.exit`.
2. **Phase 1 — dry-run parse all YAML records.** Before deleting chromadb:
   ```python
   manifest_path = root / "manifest.yaml"
   if not manifest_path.is_file():
       sys.stderr.write("no manifest.yaml found at <root>; see docs/operations/rag.md\n")
       return 2
   manifest = _Manifest.model_validate(yaml.safe_load(manifest_path.read_text("utf-8")))
   parsed: list[SolvedExample] = []
   for rid in manifest.records:
       yaml_path = root / "records" / f"{rid}.yaml"
       try:
           parsed.append(SolvedExample.from_yaml(yaml_path))
       except Exception as e:
           sys.stderr.write(f"yaml parse error in {yaml_path}: {e}\n")
           return 1
   ```
   (The dry-run pass is what AC-8 hinges on — if any record fails to parse, we abort *before* touching chromadb.)
3. **Phase 2 — delete chromadb.** `shutil.rmtree(root / "chroma", ignore_errors=False)` if present (with try/except → exit 1).
4. **Phase 3 — re-insert in order.** Construct `ChromaPersistentStore(root_dir=root)` (fresh — empty chroma dir). If `--reembed`:
   - Build `embedder = CachedEmbedder(inner=FastembedEmbedder(), db_path=root / "embeddings.cache.sqlite")` (S4-01 + S4-02).
   - For each `example in parsed`: `vec = embedder.embed(example.query_text)`; update `example.embedding_model = embedder.model_digest()`; update `example.embedding_vector = vec` (Pydantic frozen → `example.model_copy(update={...})`); rewrite the canonical YAML.
   Else: reuse `example.embedding_vector` as stored in the YAML.
   - `cap = _phase4_local_capability_mint(workflow_id=example.provenance.workflow_id, chain_head=example.provenance.event_chain_head)` — see Notes §1.
   - `await store.add(example, cap)`.
5. **Phase 4 — verify.** After all adds: assert `store.digest() == _read_manifest(root / "manifest.yaml").chain_head`. Mismatch → log `rebuild.digest_mismatch` + return 1 (a rebuild that doesn't reproduce the chain head is a bug). For `--reembed`, the manifest was rewritten by `store.add` (S4-04) at each step; the final manifest's chain_head reflects the new content.
6. **Tests:**
   - `tests/integration/test_phase4_rag_rebuild_idempotent.py` — AC-5, AC-6.
   - `tests/integration/test_phase4_rag_rebuild_missing_manifest.py` — AC-7.
   - `tests/integration/test_phase4_rag_rebuild_corrupt_yaml.py` — AC-8.
   - `tests/unit/rag/test_store_corruption_on_open.py` — AC-9.
7. **Operations doc** — `docs/operations/rag.md`: stub naming `rag rebuild`, when to use it (corruption, model upgrade), `--reembed` semantics, exit codes. S7-10 finalizes.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/integration/test_phase4_rag_rebuild_idempotent.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codegenie.rag.cli import rebuild
from codegenie.rag.store import ChromaPersistentStore, SolvedExampleWriteCapability
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example


@pytest.mark.asyncio
async def test_rag_rebuild_reproduces_byte_identical_digest(tmp_path: Path) -> None:
    """ADR-0016 §Decision: chromadb is the derived index; canonical YAML rebuilds
    it byte-identically.  Catches "rebuild reshuffles record order" and
    "rebuild drops records" mutants — both would change the digest."""
    root = tmp_path / "rag"
    store = ChromaPersistentStore(root_dir=root)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-rebuild"))
    for i, cve in enumerate(["CVE-2026-1111", "CVE-2026-2222", "CVE-2026-3333"]):
        await store.add(make_solved_example(id_=f"ex-{i:03d}", cve_id=cve), cap)
    pre_digest = store.digest()
    pre_chain_head = yaml.safe_load((root / "manifest.yaml").read_text("utf-8"))["chain_head"]
    assert pre_digest == pre_chain_head  # contract from S4-04 AC-5
    store.close()

    exit_code = rebuild(root=root, reembed=False)
    assert exit_code == 0

    reopened = ChromaPersistentStore(root_dir=root)
    post_digest = reopened.digest()
    post_chain_head = yaml.safe_load((root / "manifest.yaml").read_text("utf-8"))["chain_head"]
    assert post_digest == pre_digest, "rebuild MUST reproduce the chain head byte-identically"
    assert post_chain_head == pre_chain_head
    reopened.close()
```

Why it fails: `codegenie.rag.cli.rebuild` doesn't exist (S4-01 ships `embeddings bootstrap`; this story adds `rebuild`).

### Green — make it pass

- Land the `rebuild` function per Implementation Outline (Phases 1–4).
- Wire the top-level CLI to expose `codegenie rag rebuild`.

### Refactor

- Extract `_dry_run_parse(root) -> list[SolvedExample]` for the AC-8 transactional contract.
- Module docstring: explicit "rebuild is transactional at the directory level" framing.

### Required follow-on tests

- `test_rag_rebuild_missing_manifest_exit_2` (AC-7) — empty `<root>/`; assert exit 2 + stderr contains `"no manifest.yaml found"`.
- `test_rag_rebuild_corrupt_yaml_aborts_before_chromadb_touch` (AC-8) — write valid manifest + 2 valid records + 1 corrupt record; run rebuild; assert exit 1, stderr names the corrupt path, `<root>/chroma/` directory is **unchanged** (the dry-run pass aborted before the delete).
- `test_rag_rebuild_reembed_updates_chain_head` (AC-6) — pre-rebuild chain head; run `--reembed` with a "different" model digest (monkeypatch `FastembedEmbedder.model_digest` to return a new digest while keeping `embed` deterministic); assert chain head changed; second `--reembed` is idempotent (chain head unchanged).
- `test_store_open_on_corrupt_sqlite_raises_store_corrupted` (AC-9) — `tests/unit/rag/test_store_corruption_on_open.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/cli.py` | Add `rebuild` subcommand alongside S4-01's `embeddings bootstrap`. |
| `src/codegenie/cli/__init__.py` (or top-level CLI entry) | Wire `codegenie rag rebuild` via `codegenie rag <subcommand>` group. |
| `src/codegenie/rag/store.py` | Optional: surface `ChromaPersistentStore.from_canonical(root: Path) -> ChromaPersistentStore` classmethod if the rebuild path repeats more than once; otherwise the CLI constructs directly. |
| `tests/integration/test_phase4_rag_rebuild_idempotent.py` | AC-5 red test + AC-6 reembed follow-on. |
| `tests/integration/test_phase4_rag_rebuild_missing_manifest.py` | AC-7. |
| `tests/integration/test_phase4_rag_rebuild_corrupt_yaml.py` | AC-8 transactional. |
| `tests/unit/rag/test_store_corruption_on_open.py` | AC-9 corruption detection. |
| `docs/operations/rag.md` | Stub runbook (S7-10 finalizes). |
| `Makefile` | Optional `rag-rebuild` target. |

## Out of scope

- **Burst-harvest contention test** (`test_phase4_harvest_contention.py`) — S4-08.
- **Phase-11 pgvector adapter rebuild path** — Phase 11; the same canonical YAML + manifest survives the swap.
- **Cross-machine rebuild migration** (moving a `<root>/` from one host to another) — works by construction (YAML is portable); not a CLI feature.
- **Rebuild progress UI / TUI** — single line per record at INFO level is enough; no progress bar.
- **Resume-on-failure** — rebuild is transactional (all or nothing); if a chromadb add fails mid-stream, the operator re-runs from scratch. The wholesale `rmtree` + re-add posture is intentionally simple.

## Notes for the implementer

### §1 — `_phase4_local_capability_mint` reuse from the CLI

S4-06's import-linter contract pins the mint symbol to `{src/codegenie/gates/, src/codegenie/rag/ingest.py}`. The rebuild CLI module is `src/codegenie/rag/cli.py` — **outside** that allowlist. Two clean options:

- **(A) Widen the contract to include `src/codegenie/rag/cli.py`.** Surgical; the CLI is part of the RAG package; consistent with ADR-0003 §Decision ("only `src/codegenie/rag/` may import"). Update the import-linter block to add `src/codegenie/rag/cli.py` as a third allowed source.
- **(B) Have `cli.py` import from `ingest`** (`from codegenie.rag.ingest import _phase4_local_capability_mint`). Same effective access but goes through the boundary the contract names — and is the **wrong direction** semantically (the CLI is doing rebuild work, not ingestion).

**Pick (A).** Surface in this story's `_validation/` log: the import-linter contract gains one allowlist entry; S4-06's executor's AC-3 contract evolves additively. The rebuild capability is **conceptually a write capability** (it's calling `store.add`); making the CLI a legitimate mint site is honest.

### §2 — Don't make `rebuild` async unless the CLI framework forces it

`store.add` is async (S4-03's Protocol). The CLI command body needs to drive an event loop (`asyncio.run(_rebuild_body(...))`). Keep the top-level `rebuild` function **sync** (returns `int` exit code); it `asyncio.run`s the body internally. Tests can call `rebuild(...)` directly or call the internal `_rebuild_body(...)` coroutine; choose what's simpler — the integration tests above call the sync entry-point and `asyncio.run` inside.

### §3 — Why the dry-run parse pass

AC-8 hinges on rebuild being **transactional at the directory level**: a corrupt YAML must abort before chromadb is deleted. The dry-run parse-all-records-first pass costs ~ms per record (Pydantic validate from already-loaded YAML); doing it twice (once dry, once for-real) doubles the parse cost but makes the failure-recovery semantics clean. Without the dry-run, a partial rebuild followed by a corrupt-YAML error leaves the operator with a half-rebuilt chromadb — strictly worse than the pre-rebuild state.

### §4 — Reembed changes the canonical bytes; manifest must be updated

When `--reembed` runs, each record's `embedding_model` and `embedding_vector` fields change, the canonical YAML changes, the chain_head changes. S4-04's `_compute_chain_head` rolls over canonical YAML bytes; after `--reembed`, the manifest chain_head must reflect the new bytes. The natural place: `store.add` already updates `manifest.yaml` per S4-04 AC-2. So if `--reembed` issues all `store.add` calls after rewriting the YAMLs, the manifest converges to the new chain head naturally. Verify the test flow lands this; if not, write the manifest one final time at the end of `--reembed`'s loop.

### §5 — `SolvedExample.embedding_vector` field placement

If S1-04 / S4-04 did **not** include `embedding_vector` on the `SolvedExample` Pydantic model (because the vector lives in chromadb's index), the rebuild has no source-of-truth for the vector — it must either re-embed always (force `--reembed`) or persist the vector in YAML. ADR-0016 §Decision is explicit: "records carry their embedding model digest + vector" — the vector is **on** the canonical record. Surface this if S4-04's executor missed the field; revisit S4-04 to add `embedding_vector: list[float]` (length 384) to `SolvedExample` and to the YAML body.

### §6 — Logging shape

`structlog.get_logger(__name__)` (Phase 0 convention). Event keys: `rebuild.start`, `rebuild.dry_run_parsed`, `rebuild.chroma_removed`, `rebuild.record_inserted` (one per record at DEBUG; mute under default verbosity), `rebuild.completed`, `rebuild.digest_match` (or `rebuild.digest_mismatch` on the AC-5 assertion failure). The CLI's stdout is human-friendly (`"Rebuilt 100 records in 4.2s. chain_head=ab12..."`); stderr is for errors.

### §7 — Don't add a `--dry-run` mode

Tempting to add `--dry-run` that prints what *would* be rebuilt. The dry-run parse pass already exists internally; surfacing it as a flag is YAGNI for Phase 4. Operators who need to inspect the manifest can `cat .codegenie/rag/manifest.yaml`. Surface per Rule 2 if a future story asks for it.

### §8 — Subprocess vs in-process for tests

The AC-5 / AC-6 / AC-7 / AC-8 integration tests invoke `rebuild(...)` as an in-process function call — fastest, no subprocess overhead, easy to assert exit codes. The actual `codegenie rag rebuild` shell invocation is exercised by a single smoke test (one subprocess.run; verifies the CLI entry-point is wired) — keep that under `tests/integration/` with an `@pytest.mark.cli` marker so it can be skipped under fast lanes.

### §9 — `rmtree` safety check

Before `shutil.rmtree(<root>/chroma/)`: verify the path is under the expected root, not a symlink to elsewhere, and not the literal filesystem root. Use `(root / "chroma").resolve().is_relative_to(root.resolve())` as a paranoid check; if False, exit 1 with a "refusing to remove" diagnostic. The cost is one syscall; the win is preventing a misconfigured `--root /` invocation from wiping the disk. (Phase-0 conventions name "fail loud" — Rule 12.)
