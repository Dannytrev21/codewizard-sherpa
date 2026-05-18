# Story S4-04 — YAML canonical records + `manifest.yaml` with BLAKE3 chain head

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** M
**Depends on:** S4-03 (`SolvedExampleStore` + `ChromaPersistentStore` + `add` lock + `WriteCapability` marker)
**ADRs honored:** ADR-0016 (YAML records as canonical source-of-truth; chromadb sqlite is derived; BLAKE3-rolled `chain_head` over canonical records list; Hypothesis YAML roundtrip property)

## Context

S4-03 lands `ChromaPersistentStore.add()` writing only to chromadb. ADR-0016 §Decision elevates **`.codegenie/rag/records/<id>.yaml` to canonical source** and chromadb sqlite to a **derived index** — rebuildable via `codegenie rag rebuild` (S4-07). This story extends `add()` so a single call atomically writes:

1. **`<root>/records/<id>.yaml`** — the canonical `SolvedExample` body (Pydantic `.model_dump(mode="json")` → PyYAML safe-dump with sorted keys).
2. **chromadb** (existing S4-03 path).
3. **`<root>/manifest.yaml`** — `{records: [<id>...], chain_head: ChainHead}` with `chain_head` rolled BLAKE3 over the **canonical YAML bytes** of each record in insertion order (not just the IDs — the chain head is the **content** head, so a record edit invalidates the chain).

ADR-0016 §"Pattern fit" names this the **content-addressed derived-index** pattern. The integrity property is: given canonical YAML records + the manifest's chain_head, `codegenie rag rebuild` (S4-07) reconstructs a chromadb whose `digest()` is byte-identical to the manifest's chain_head (golden test). The Hypothesis YAML roundtrip property (`from_yaml(to_yaml(x)) == x`) is the load-bearing schema discipline that makes the rebuild deterministic.

This story also lands the **atomic-write contract**: YAML first → chromadb second → manifest update last. If chromadb fails mid-write, the YAML record is on disk (recoverable by `rag rebuild`) but the manifest does **not** include it (manifest reflects what's queryable). On manifest-write failure, the next `add()` recomputes the manifest from scratch.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — SolvedExampleStore + ChromaPersistentStore` — YAML canonical; chromadb derived; per-collection partition; `digest()` = BLAKE3 rolled over canonical records.
  - `../phase-arch-design.md §"On-disk shapes"` — `.codegenie/rag/records/<id>.yaml`, `.codegenie/rag/manifest.yaml` with `chain_head`.
  - `../phase-arch-design.md §"Property tests"` — `tests/property/test_solved_example_yaml_roundtrip.py` — Hypothesis: `from_yaml(to_yaml(x)) == x`.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — full decision; canonical/derived split; rebuild path; storage budget (~6.5 KB/example).
- **Source design:**
  - `../final-design.md §Component 7` — YAML-as-canonical-source framing.
  - `../final-design.md §"Content-addressed cache"` — the toolkit pattern that informs the chain-head computation.
- **Existing code (precedent to mirror):**
  - `src/codegenie/output/sanitizer.py` + Phase-1/2 writers — canonical YAML emission discipline (sorted keys, no trailing whitespace, LF line endings).
  - `src/codegenie/cache/keys.py` — BLAKE3 rolling pattern; mirror exactly.
  - `src/codegenie/probes/layer_a/*.py` — atomic-write idioms (write-to-tmp + rename).

## Goal

Extend `ChromaPersistentStore.add()` to atomically write canonical YAML records + update `manifest.yaml` with a BLAKE3-rolled `chain_head` over the **canonical YAML bytes** of each record (in insertion order); land a Hypothesis property test asserting `SolvedExample.from_yaml(to_yaml(x)) == x` for all valid models; on next-store-open, populate `_record_ids` from `manifest.yaml` (not from chromadb), establishing the manifest as the source-of-truth for ordering.

## Acceptance criteria

- [ ] **AC-1 — Canonical YAML write path.** `add(example, capability)` writes `<root>/records/<example.id>.yaml` **before** the chromadb `collection.add` call:
    - Body: `example.model_dump(mode="json")` → `yaml.safe_dump(body, sort_keys=True, default_flow_style=False, allow_unicode=True)`.
    - Atomic: write to `<root>/records/<id>.yaml.tmp` then `os.replace(tmp, final)`.
    - Trailing newline.
    - `<root>/records/` created with `mkdir(parents=True, exist_ok=True)` on first add.
- [ ] **AC-2 — `manifest.yaml` updated last.** After the chromadb write succeeds:
    - Append `example.id` to `self._record_ids` (S4-03 already does this).
    - Recompute `chain_head = blake3.blake3(b"".join(read_canonical_yaml_bytes(rid) for rid in self._record_ids)).hexdigest()` — the BLAKE3 of the concatenated canonical YAML bytes, in insertion order.
    - Write `manifest.yaml` atomically: `yaml.safe_dump({"records": list(self._record_ids), "chain_head": chain_head, "schema_version": 1}, ...)`.
- [ ] **AC-3 — `_load_existing_record_ids()` reads from `manifest.yaml`.** S4-03's stub loads from chromadb; this story rewires it to read `manifest.yaml`'s `records: [...]` (in order); if the manifest is missing, `_record_ids = []` (fresh store).
- [ ] **AC-4 — Atomic-write failure semantics.** If `collection.add` raises after the YAML write succeeded, the YAML record **remains on disk** (orphan), the manifest is **not** updated, and `add()` re-raises. Test pins this: monkeypatch chromadb's `collection.add` to raise → YAML file exists; `manifest.yaml` does not list `example.id`; `record_ids` does not contain `example.id`. The orphan is recoverable by `codegenie rag rebuild` (S4-07).
- [ ] **AC-5 — `chain_head` matches `digest()`.** The contract is **byte-identical**: `manifest.chain_head == store.digest()` after every successful `add()`. The two computations must use the same input bytes in the same order. **Pick one canonical computation**: define `_compute_chain_head(record_ids: list[SolvedExampleId], records_dir: Path) -> ChainHead` as the single source of truth; both `digest()` and `manifest.write` call it. (This means revising S4-03's AC-6 — `digest()` was rolling over the *IDs*; the canonical roll is now over the *canonical YAML bytes*. Surface this divergence per Rule 7 — see Notes §1.)
- [ ] **AC-6 — YAML roundtrip Hypothesis property.** `tests/property/test_solved_example_yaml_roundtrip.py`:
    - Hypothesis strategy `solved_examples()` produces valid `SolvedExample` instances (use `hypothesis.strategies.builds` over the model fields).
    - Property: `assert SolvedExample.model_validate(yaml.safe_load(yaml.safe_dump(x.model_dump(mode="json"), sort_keys=True))) == x`.
    - The roundtrip must be **exact** for Pydantic equality (`frozen=True, extra="forbid"` makes the model hashable and `__eq__` is structural).
    - At least 50 examples; deadlines off (YAML serialization can be slow under coverage).
- [ ] **AC-7 — `chain_head` deterministic across inserts in same order.** Two fresh stores receiving the same three `SolvedExample` instances in the same order produce **byte-identical** `manifest.yaml` content (after normalization for `created_at` — see Notes §3). Test pins this with explicit byte comparison.
- [ ] **AC-8 — `chain_head` advances monotonically.** A property-style test: starting from empty, sequentially `add()` 10 records; record `chain_head` at each step; assert all 10 distinct AND `len(set(chain_heads)) == 10` (no collision); the **prefix** property — `chain_head_after_N` depends only on records 0..N-1 in order, not on records N..9 (forward-only).
- [ ] **AC-9 — Manifest schema-versioned.** `manifest.yaml` carries `schema_version: 1` (Final[int]). A future format change (Phase 11 pgvector swap may rewrite the manifest) bumps the version; reading an unknown schema_version raises `StoreCorrupted("unknown manifest schema_version")` (handled at next store-open).
- [ ] **AC-10 — `from_yaml(path) -> SolvedExample` classmethod on `SolvedExample`.** Convenience parser used by S4-07's rebuild: reads `<path>.yaml`, validates via `model_validate`, returns. Errors surface as `pydantic.ValidationError` — S4-07 wraps them. (Pure helper; no I/O beyond file read.)
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. PyYAML is a project dep (verify in `pyproject.toml`; if absent, add).

## Implementation outline

1. **Verify PyYAML in `pyproject.toml`.** Phase 1/2 writers use it for `repo-context.yaml`; should be there already (Rule 8).
2. **Add `_compute_chain_head` pure helper** at module-top of `src/codegenie/rag/store.py`:
   ```python
   def _compute_chain_head(record_ids: list[SolvedExampleId], records_dir: Path) -> ChainHead:
       h = blake3.blake3()
       for rid in record_ids:
           h.update((records_dir / f"{rid}.yaml").read_bytes())
       return ChainHead(h.hexdigest())
   ```
3. **Add manifest model** as a small Pydantic frozen-extra-forbid model in `src/codegenie/rag/store.py`:
   ```python
   class _Manifest(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       schema_version: Literal[1] = 1
       records: list[SolvedExampleId]
       chain_head: ChainHead
   ```
4. **Atomic-write helper:**
   ```python
   def _atomic_write_text(path: Path, content: str) -> None:
       path.parent.mkdir(parents=True, exist_ok=True)
       tmp = path.with_suffix(path.suffix + ".tmp")
       tmp.write_text(content, encoding="utf-8")
       os.replace(tmp, path)
   ```
5. **Extend `add()`** (after lock acquired):
   ```python
   # 1. Canonical YAML
   yaml_body = yaml.safe_dump(example.model_dump(mode="json"), sort_keys=True,
                              default_flow_style=False, allow_unicode=True)
   _atomic_write_text(records_dir / f"{example.id}.yaml", yaml_body)

   # 2. chromadb (existing S4-03 path)
   await asyncio.to_thread(collection.add, ids=[example.id], embeddings=[...], ...)

   # 3. Manifest
   self._record_ids.append(example.id)
   chain_head = _compute_chain_head(self._record_ids, records_dir)
   manifest = _Manifest(records=list(self._record_ids), chain_head=chain_head)
   _atomic_write_text(root / "manifest.yaml", yaml.safe_dump(manifest.model_dump(), sort_keys=True))
   ```
6. **Rewire `_load_existing_record_ids`:** read `manifest.yaml`; absent → `[]`; present → validate via `_Manifest.model_validate(yaml.safe_load(...))`; `schema_version != 1` → `StoreCorrupted`.
7. **Update `digest()`:** delegate to `_compute_chain_head(self._record_ids, self._records_dir)` — same function the manifest uses.
8. **`SolvedExample.from_yaml` classmethod:** `cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))`.
9. **Tests:** `tests/unit/rag/test_store_yaml_canonical.py` covers AC-1, AC-2, AC-3, AC-4, AC-5, AC-7, AC-9; `tests/property/test_solved_example_yaml_roundtrip.py` covers AC-6; `tests/unit/rag/test_chain_head_monotonic.py` covers AC-8.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_store_yaml_canonical.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example


@pytest.mark.asyncio
async def test_add_writes_canonical_yaml_record_first(tmp_path: Path) -> None:
    """ADR-0016 §Decision: YAML is canonical, chromadb is derived.
    Catches "skip-yaml-write" and "wrong-write-order" mutants.
    Without YAML on disk, `codegenie rag rebuild` cannot reconstruct."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-canonical-001"))
    example = make_solved_example(id_="ex-canonical-001", cve_id="CVE-2026-1111")
    await store.add(example, cap)

    yaml_path = tmp_path / "records" / "ex-canonical-001.yaml"
    assert yaml_path.is_file(), "canonical YAML record must be written"

    body = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert body["id"] == "ex-canonical-001"
    assert body["cve_id"] == "CVE-2026-1111"
    # Sorted keys: the first non-comment line begins with a key alphabetically earliest
    # among top-level keys (e.g., 'advisory_digest' before 'id'). This catches sort_keys=False mutants.
    first_key = next(iter(body))
    assert first_key == sorted(body.keys())[0]
    store.close()


@pytest.mark.asyncio
async def test_chain_head_equals_digest_after_add(tmp_path: Path) -> None:
    """AC-5 — manifest.chain_head must byte-equal store.digest()."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-chain"))
    await store.add(make_solved_example(id_="ex-a"), cap)
    await store.add(make_solved_example(id_="ex-b"), cap)

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["chain_head"] == store.digest()
    assert manifest["records"] == ["ex-a", "ex-b"]
    assert manifest["schema_version"] == 1
    store.close()
```

Why it fails: S4-03's `add()` doesn't write YAML, doesn't write a manifest, and `digest()` rolls over IDs (not bytes), so AC-5 won't match.

### Green — make it pass

- Extend `add()` per Implementation Outline.
- Rewrite `digest()` to call `_compute_chain_head` (the same function the manifest write uses).
- Add `_load_existing_record_ids` reading the manifest.

### Refactor

- Extract `_canonical_yaml_dump(model: BaseModel) -> str` helper (one-liner; reused for records + manifest).
- Module docstring updates: YAML-canonical contract explicitly named.
- Structured-log emissions: `store.add.yaml_written`, `store.add.chroma_written`, `store.add.manifest_updated`.

### Required follow-on tests

- `test_chromadb_write_failure_leaves_yaml_orphan` (AC-4) — monkeypatch `collection.add` to raise; assert YAML present, manifest absent (or unchanged), `_record_ids` not appended, exception re-raised.
- `test_load_existing_record_ids_from_manifest` (AC-3) — open a fresh `ChromaPersistentStore` against a `tmp_path` containing a hand-written `manifest.yaml` + records; assert `_record_ids` matches.
- `test_unknown_schema_version_raises_store_corrupted` (AC-9) — write `manifest.yaml` with `schema_version: 999`; opening raises `StoreCorrupted`.
- `test_chain_head_monotonic_and_unique` (AC-8) — `tests/unit/rag/test_chain_head_monotonic.py`; 10 sequential adds; collect 10 chain heads; assert distinct.
- `test_two_stores_same_order_produce_identical_manifest_bytes` (AC-7) — normalize `created_at` to a fixed value (use `freezegun` or a `monkeypatch` of `datetime.now`); two `tmp_path` stores receive identical record sequences; resulting `manifest.yaml` bytes are byte-identical.
- Hypothesis property (AC-6) in `tests/property/test_solved_example_yaml_roundtrip.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/store.py` | Extend `add()` for YAML + manifest write; rewire `_load_existing_record_ids`; rewrite `digest()` to share `_compute_chain_head`; add `_Manifest` model + `_compute_chain_head` + `_atomic_write_text` helpers. |
| `src/codegenie/rag/models.py` (or wherever S1-04 lands the `SolvedExample` model) | Add `SolvedExample.from_yaml(path: Path) -> SolvedExample` classmethod. |
| `src/codegenie/rag/errors.py` | (Already has `StoreCorrupted` from S4-03; reuse.) |
| `tests/unit/rag/test_store_yaml_canonical.py` | Red test + AC follow-ons. |
| `tests/unit/rag/test_chain_head_monotonic.py` | AC-8 monotonicity. |
| `tests/property/test_solved_example_yaml_roundtrip.py` | AC-6 Hypothesis roundtrip. |

## Out of scope

- **`RecordProvenance.verify` chain check** — S4-05 (the chain_head computed here is the *store's* chain head; `RecordProvenance.event_chain_head` is a per-record property pointing into the **spanning event log** — a different chain entirely).
- **`codegenie rag rebuild` CLI** — S4-07 (consumes the canonical YAML this story writes).
- **`_phase4_local_capability_mint`** — S4-06.
- **chromadb-corruption recovery (delete + rebuild)** — S4-07.
- **Manifest compaction / pruning** — never; the manifest is append-only by construction.

## Notes for the implementer

### §1 — `digest()` semantics changed; surface per Rule 7

S4-03's AC-6 had `digest()` rolling BLAKE3 over the record-ID **strings**. This story rewrites it to roll over the canonical YAML **bytes**. **Why the change:** the rebuild golden test (S4-07) needs `digest() == manifest.chain_head` **byte-identical** as the conformance bar — and `manifest.chain_head` is content-addressed (rolls over canonical bytes), not ID-addressed. Rolling over IDs would let two stores with the same record IDs but different content disagree on `digest()` only at retrieval time — too late.

Update S4-03's AC-6 prose retroactively (the validator may flag the inconsistency; capture the change in the `_validation/` log when this story is hardened). The fix is one line in `_compute_chain_head`; the rationale is what matters.

### §2 — Atomic-write must be `os.replace`, not `shutil.move`

`os.replace` is atomic on POSIX (rename(2) is); `shutil.move` falls back to copy+unlink across filesystems, which is **not** atomic. The records dir and the tmp file are guaranteed same-filesystem because both live under `<root>/records/`. Document this in the helper's docstring; a contributor who "improves" to `shutil.move` will break crash-safety.

### §3 — `created_at` is non-deterministic; tests normalize

`SolvedExample.created_at: datetime` carries the harvest time. Two stores receiving "the same" record at different wall-clock times will have different `created_at` fields. AC-7's byte-identical comparison must either:

- **(A)** Use `freezegun` / `pytest-freezer` to fix `datetime.now(timezone.utc)`.
- **(B)** Use a fixture that constructs `SolvedExample` instances with explicit `created_at=datetime(2026, 5, 18, tzinfo=timezone.utc)`.

Pick (B) for unit tests (no extra dep) and document that `make_solved_example` accepts a `created_at` kwarg defaulting to a fixed timestamp.

### §4 — Manifest is read on open, not rebuilt

`_load_existing_record_ids` reads `manifest.yaml`'s `records: [...]` as the order-of-truth. Do **not** rescan `<root>/records/*.yaml` and sort by `created_at` — sort-by-time would lose the insertion order that S4-08's monotonic-chain-head test pins. The manifest is the order-of-truth; if it disagrees with the on-disk records, `codegenie rag rebuild` (S4-07) resolves the discrepancy.

### §5 — Don't sanitize the YAML content

`SolvedExample` is **already validated** by Pydantic at construction time (S1-04 lands `extra="forbid"`). The YAML write is a faithful serialization, not a sanitization step. The Phase-2 output sanitizer (`src/codegenie/output/sanitizer.py`) is for probe outputs that may carry absolute paths or secret-shaped fields; `SolvedExample` is bounded by its Pydantic schema and does not need re-sanitization. **Do not** add an extra pass here.

### §6 — Per-collection chromadb vs per-store manifest

The chromadb side is **per-collection** (one collection per `(task_class, language, build_system)` triple). The YAML side is **one flat directory** (`records/<id>.yaml`) — IDs are globally unique (BLAKE3 of canonical body), so collisions are vanishingly unlikely. The manifest is **per-store** (one `manifest.yaml` at the root) and lists records across all partitions in global insertion order. This asymmetry is correct: chromadb partitions for query-time filtering; the YAML side is a flat append-only log. Document in the module docstring so a future reviewer doesn't try to nest records under partition subdirs.

### §7 — Hypothesis strategy for `SolvedExample`

Construct via `hypothesis.strategies.builds(SolvedExample, ...)` with per-field strategies. Tight bounds matter:

- `id: text(min_size=8, max_size=64, alphabet="abcdef0123456789")` — BLAKE3-hex-shaped.
- `cve_id: text(...).map("CVE-2026-".__add__)` — keep it CVE-shaped.
- Numeric fields: `floats(min_value=-1.0, max_value=1.0)` for the score-shaped values.
- `embedding_vector`: `lists(floats(...), min_size=384, max_size=384)`.

Hypothesis deadlines off (`@settings(deadline=None)`) — YAML serialization under coverage instrumentation is slow.

### §8 — schema_version: 1 is intentional

The current `_Manifest` schema is version 1. A Phase-11 pgvector swap may change the manifest format (e.g., add a `backend_kind: Literal["chromadb", "pgvector"]` field). Bumping the version is the upgrade path; a reader at version 1 should **refuse-start** on version 2 with a diagnostic naming the upgrade command. The version is `Final[Literal[1]]` here — the literal is the constraint Pydantic enforces.
