# Story S4-04 — YAML canonical records + `manifest.yaml` with BLAKE3 chain head

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S4-04.md`](_attempts/S4-04.md) for the per-AC evidence table + gate log — `_canonical_yaml_dump` shared serialization surface (record + manifest + AC-6 property test) + `_atomic_write_text` (tmp + `os.replace`) + `_validate_record_id_path_safe` (AC-14) + `_roll_chain_head` pure functional core + `_compute_chain_head` `FileNotFoundError → StoreCorrupted`-translating shell + `_Manifest` frozen Pydantic model (`schema_version: Literal[1]`) + `_parse_manifest_or_raise` defensive translator land at `src/codegenie/rag/store.py`; `_load_existing_record_ids` rewired to read `manifest.yaml` (order-of-truth); `add()` writes canonical YAML → chromadb → manifest atomically inside the S4-03 `asyncio.Lock`, with `_record_ids.pop()` self-heal on manifest-write failure (AC-12); `digest()` rerolls over canonical YAML *bytes* (was record-ID strings in S4-03) and re-wraps `ChainHead → StoreDigest` at the Protocol boundary; `SolvedExample.from_yaml` classmethod lands at `src/codegenie/rag/models.py`. Story-scoped gates green: 137 RAG-suite tests passed (17 unit + 4 chain-head + 1 Hypothesis property + the existing S4-03 suite), `ruff check`/`ruff format --check` clean, `mypy --strict src/` 231 files OK, `lint-imports` 11 contracts kept / 0 broken (no new edges — S4-03's existing `chromadb -> codegenie.rag.store` ignore covers the residual `__init__` import). Three new lessons captured (L-S404-1 O(N²) re-read is intentional vs. hidden-state hasher, L-S404-2 `_Manifest` gets no `from_yaml` to preserve the `StoreCorrupted` translation envelope, L-S404-3 raw `schema_version` check sequenced before `_Manifest.model_validate` to keep the diagnostic actionable).
**Effort:** M
**Depends on:** S4-03 (`SolvedExampleStore` + `ChromaPersistentStore` + `add` lock + `WriteCapability` marker)
**ADRs honored:** ADR-0016 (YAML records as canonical source-of-truth; chromadb sqlite is derived; BLAKE3-rolled `chain_head` over canonical records list; Hypothesis YAML roundtrip property)

## Validation notes (2026-05-22 — phase-story-validator v1)

Verdict **HARDENED**. The goal and the content-addressed-derived-index shape (ADR-0016) are sound — no scope rewrite. Four critics surfaced 5 block-severity defects and ~13 harden-severity gaps, all fixable in place. Key changes:

- **AC-5 — type contradiction fixed.** `digest()` is Protocol-pinned `-> StoreDigest` (S4-03 AC-6); `_compute_chain_head` returns `ChainHead` (a *distinct* S1-01 newtype — its mypy-negative suite parametrizes the `StoreDigest ← ChainHead` swap as an error). `digest()` now explicitly re-wraps `StoreDigest(_compute_chain_head(...))`. Returning `ChainHead` from `digest()` was rejected — it would mutate S4-03's frozen Protocol and AC-9 signature fence.
- **AC-5 — self-fulfilling test fixed.** `chain_head == digest()` passes for a *wrong* `_compute_chain_head` (both sides delegate to it). Added a mandatory independent-oracle test recomputing `blake3(b"".join(yaml_bytes))` in the test body, with deliberately non-sorted insertion order.
- **AC-8 — prefix property now actually tested.** "10 distinct heads" could not catch a rehash-all-each-`add` mutant. Split a pure `_roll_chain_head(Iterable[bytes]) -> ChainHead` core (functional core) from the I/O shell `_compute_chain_head`; prefix-stability is pinned against the pure core + a two-store cross-check.
- **Crash-recovery negative space pinned.** New AC-12 (manifest-write failure), AC-13 (manifest references a missing record file → `StoreCorrupted`, not raw `FileNotFoundError`), AC-14 (record-id path-traversal safety), AC-15 (empty-store invariants). AC-9 broadened to cover *all* malformed-manifest cases, with the `schema_version` check sequenced *before* `_Manifest.model_validate` (else `extra="forbid"` + `Literal[1]` make a v2 manifest fail with a generic `ValidationError`).
- **AC-10 `from_yaml` was untested** — added round-trip + negative tests; `_canonical_yaml_dump` promoted from Refactor to the Green path as the single serialization surface so AC-6 guards the real code.
- **Cross-story actions the validator could NOT apply** (one story per invocation — see the `_validation/` report): **(a)** S4-03 AC-6 prose still says `digest()` rolls over record-ID *strings*; S4-04 rerolls over canonical YAML *bytes* — S4-03 AC-6 + Notes §5 + its `digest()` test must be amended before S4-04 executes. **(b)** ADR-0016 §Consequences' manifest shape `{records, chain_head}` is stale — add `schema_version`.

## Context

S4-03 lands `ChromaPersistentStore.add()` writing only to chromadb. ADR-0016 §Decision elevates **`.codegenie/rag/records/<id>.yaml` to canonical source** and chromadb sqlite to a **derived index** — rebuildable via `codegenie rag rebuild` (S4-07). This story extends `add()` so a single call atomically writes:

1. **`<root>/records/<id>.yaml`** — the canonical `SolvedExample` body (Pydantic `.model_dump(mode="json")` → PyYAML safe-dump with sorted keys).
2. **chromadb** (existing S4-03 path).
3. **`<root>/manifest.yaml`** — `{records: [<id>...], chain_head: ChainHead}` with `chain_head` rolled BLAKE3 over the **canonical YAML bytes** of each record in insertion order (not just the IDs — the chain head is the **content** head, so a record edit invalidates the chain).

ADR-0016 §"Pattern fit" names this the **content-addressed derived-index** pattern. The integrity property is: given canonical YAML records + the manifest's chain_head, `codegenie rag rebuild` (S4-07) reconstructs a chromadb whose `digest()` is byte-identical to the manifest's chain_head (golden test). The Hypothesis YAML roundtrip property (`from_yaml(to_yaml(x)) == x`) is the load-bearing schema discipline that makes the rebuild deterministic.

This story also lands the **atomic-write contract**: YAML first → chromadb second → manifest update last. If chromadb fails mid-write, the YAML record is on disk (recoverable by `rag rebuild`) but the manifest does **not** include it (manifest reflects what's queryable). On manifest-write failure the YAML record and the chromadb entry are both on disk but the manifest is stale; an in-process next `add()` rewrites a manifest that re-includes the record, and a cross-process restart is reconciled by `rag rebuild` (see AC-12).

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

- [x] **AC-1 — Canonical YAML write path.** `add(example, capability)` writes `<root>/records/<example.id>.yaml` **before** the chromadb `collection.add` call:
    - Body: serialized via the shared `_canonical_yaml_dump(example)` helper — `yaml.safe_dump(example.model_dump(mode="json"), sort_keys=True, default_flow_style=False, allow_unicode=True)`. The **same** helper serializes the manifest (AC-2), and `from_yaml` (AC-10) shares its inverse parse core, so the roundtrip property (AC-6) guards the real write path, not a hand-inlined dump.
    - Atomic: write to `<root>/records/<id>.yaml.tmp` then `os.replace(tmp, final)`.
    - Trailing newline.
    - `<root>/records/` created with `mkdir(parents=True, exist_ok=True)` **by the caller** before the write — not inside `_atomic_write_text` (a write helper that silently mkdirs is a hidden side effect; see Notes §2).
    - **Sorted-key discipline is observable:** the emitted file's top-level keys appear in ascending order. Verified by a full-ordering assertion over the raw text — every top-level key line — not a single first-key check; a `sort_keys=False` mutant on a model with ≥ 2 top-level fields must fail (see TDD plan).
- [x] **AC-2 — `manifest.yaml` updated last.** After the chromadb write succeeds:
    - Append `example.id` to `self._record_ids` (S4-03 already does this).
    - Recompute `chain_head = _compute_chain_head(self._record_ids, records_dir)` — the BLAKE3 of the concatenated canonical YAML bytes, in insertion order (the single shared computation — see AC-5, Outline §2).
    - Write `manifest.yaml` atomically with serialization options **byte-identical to AC-1's record dump** — `yaml.safe_dump(manifest.model_dump(), sort_keys=True, default_flow_style=False, allow_unicode=True)`. (Divergent options break AC-7's byte-identity guarantee across PyYAML versions.)
- [x] **AC-3 — `_load_existing_record_ids()` reads from `manifest.yaml`.** S4-03's stub loads from chromadb; this story rewires it to read `manifest.yaml`'s `records: [...]` (in order); if the manifest is missing, `_record_ids = []` (fresh store). A manifest that is present but malformed (unparseable YAML, missing keys, unknown `schema_version`, or listing a record id whose `<id>.yaml` is absent) raises `StoreCorrupted` — never a raw library exception (see AC-9, AC-13).
- [x] **AC-4 — chromadb-write failure semantics.** If `collection.add` raises after the YAML write succeeded, the YAML record **remains on disk** (orphan), the manifest is **not** updated, `self._record_ids` is **not** appended, and `add()` re-raises the original exception. Because the `_record_ids.append` and manifest write are sequenced *after* the chromadb call inside the same `asyncio.Lock` hold, no separate rollback is needed — the failed steps simply never run. Tests pin **two** cases (a missing file and an unchanged file are different evidence):
    - **First-ever add fails:** `<root>/records/<id>.yaml` exists; `<root>/manifest.yaml` does **not** exist; `example.id not in store._record_ids`; the *named* concrete exception type is re-raised (not bare `Exception`).
    - **Nth add fails** (one good add first): snapshot `manifest.yaml` bytes → failing add → assert `manifest.yaml` bytes **byte-unchanged**; orphan YAML present; `_record_ids` unchanged.
    - The orphan is recoverable by `codegenie rag rebuild` (S4-07).
- [x] **AC-5 — `chain_head` matches `digest()`; one shared computation; `digest()` re-typed at the boundary.** The value contract is **byte-identical**: `manifest.chain_head == store.digest()` (string-equal) after every successful `add()`. Enforced by a single canonical computation — `_compute_chain_head(record_ids: list[SolvedExampleId], records_dir: Path) -> ChainHead` — that both `digest()` and the manifest write call.
    - **Type boundary (`mypy --strict`).** `digest()` is Protocol-pinned `-> StoreDigest` (S4-03 AC-6, arch §Component 7); `_compute_chain_head` returns `ChainHead`. `StoreDigest` and `ChainHead` are **distinct S1-01 newtypes** (S1-01's mypy-negative suite parametrizes the `StoreDigest ← ChainHead` swap as an error). `digest()` therefore re-wraps: `return StoreDigest(_compute_chain_head(self._record_ids, self._records_dir))` — same BLAKE3 hex, re-typed to the Protocol's domain newtype; comment the lift. (Making `digest()` return `ChainHead` is **rejected** — it would mutate S4-03's frozen Protocol surface and AC-9 `inspect.signature` fence.)
    - **Independent-oracle test (mandatory).** `manifest.chain_head == store.digest()` *alone* is a consistency check, not a correctness check — both sides delegate to `_compute_chain_head`, so a wrong helper (rolls over IDs, sorts records, hashes-each-then-XORs) passes. The TDD plan **must** include `test_chain_head_is_blake3_of_concatenated_canonical_yaml`, which recomputes `blake3(b"".join(read_bytes of each record .yaml, insertion order)).hexdigest()` *in the test body* and asserts equality — with a deliberately non-sorted insertion order (add `ex-b` then `ex-a`) so a `sorted()` mutant fails.
    - **Cross-story divergence (Rule 7).** This rerolls S4-03's `digest()` from record-ID *strings* to canonical YAML *bytes*. S4-03 AC-6 prose + its `digest()` test must be amended to match — see Notes §1; the validator surfaces this in the `_validation/` report (it does not edit sibling stories). Executor: after the rewrite, `make test` must be green for the **whole** `tests/unit/rag/` suite, not only the new files.
- [x] **AC-6 — YAML roundtrip Hypothesis property.** `tests/property/test_solved_example_yaml_roundtrip.py`:
    - Hypothesis strategy `solved_examples()` produces valid `SolvedExample` instances with an **explicit per-field strategy for every field** (mirror the repo's existing sum-type roundtrip property test — `st.builds(SolvedExample, ...)` with a strategy bound for *each* field). A field left to inference will either fail construction on the newtype / `EmbeddingVector` / nested-`RecordProvenance` / `datetime` fields, or generate degenerate values that make the property prove nothing. The property asserts non-degeneracy inline — e.g. `assert len(x.embedding_vector) == 384`.
    - Property: `assert SolvedExample.model_validate(yaml.safe_load(_canonical_yaml_dump(x))) == x` — the serialize side routes through the **same** `_canonical_yaml_dump` helper `add()` uses; the parse side (`model_validate(yaml.safe_load(...))`) is the **same** core `from_yaml` (AC-10) uses. The property thus guards the real code paths, not a hand-inlined `safe_dump`.
    - The roundtrip must be **exact** for Pydantic equality (`frozen=True, extra="forbid"` → structural `__eq__`).
    - **Scope note:** the property is key-order-independent (`safe_load` parses into a dict regardless of key order) — it does **not** guard `sort_keys=True`. The sorted-key discipline is pinned by AC-1's full-ordering assertion, not here.
    - `@settings(max_examples=50, deadline=None, database=None)` — `deadline=None` because YAML serialization under coverage is slow; `database=None` keeps CI hermetic (matches the repo's property-test precedent).
- [x] **AC-7 — `chain_head` deterministic across inserts in same order.** Two fresh stores receiving the same three `SolvedExample` instances in the same order produce **byte-identical** `manifest.yaml` content (after normalization for `created_at` — see Notes §3). The test asserts `(root_a / "manifest.yaml").read_bytes() == (root_b / "manifest.yaml").read_bytes()` — a **raw-bytes** comparison, never `yaml.safe_load(...)` of both sides (parsing into dicts hides `sort_keys` / float-format divergence). `created_at` is normalized via the `make_solved_example(created_at=...)` fixture default (Notes §3).
- [x] **AC-8 — `chain_head` advances monotonically AND is prefix-stable.** Two distinct contracts, two distinct tests:
    - **Monotonic + unique:** sequentially `add()` 10 records; collect `chain_head` at each step; assert `len(set(chain_heads)) == 10` (all distinct — no collision).
    - **Prefix-stable:** `chain_head_after_N` depends only on records 0..N-1, not on later records. Distinctness alone does **not** prove this — a mutant that rehashes all records on every `add()` still yields 10 distinct heads, and the property is genuinely untestable inside one store (you cannot un-add). Pin it **two ways:** (a) against the *pure* `_roll_chain_head(Iterable[bytes]) -> ChainHead` core (Outline §2) — `_roll_chain_head([b0, b1, b2])` equals the 3-prefix of `_roll_chain_head([b0, b1, b2, b3, b4])`'s reduction, table-tested with synthetic bytes, no filesystem; and (b) a two-store cross-check — store A with N records, store B with N+5, assert A's `digest()` equals `blake3` of B's first-N record bytes.
- [x] **AC-9 — Manifest schema-versioned; all malformed-manifest cases fail loud.** `manifest.yaml` carries `schema_version: 1` (`Literal[1]` on `_Manifest`). At store-open, `_load_existing_record_ids` translates **every** corrupt-manifest case to a typed `StoreCorrupted` with a diagnostic message — never a raw `yaml.YAMLError` or `pydantic.ValidationError`:
    - Unparseable / truncated YAML → `StoreCorrupted("manifest.yaml is not valid YAML")`.
    - Parsed value is not a mapping, or `schema_version` is absent / not `1` → `StoreCorrupted("unknown manifest schema_version")`.
    - Structure fails `_Manifest` validation (missing `records` / `chain_head`, wrong types) → `StoreCorrupted`.
    - **Check order matters:** read the raw `schema_version` key and reject unknown versions **before** calling `_Manifest.model_validate(...)`. Because `_Manifest` is `extra="forbid"` with `schema_version: Literal[1]`, a future v2 manifest (new fields, `schema_version: 2`) would otherwise fail `model_validate` with a generic `ValidationError` instead of the intended diagnostic. The genuine Open/Closed version-dispatch seam (a table keyed on `schema_version`) arrives only when Phase 11 ships v2 — not now (Rule 2; see Notes §8).
- [x] **AC-10 — `from_yaml(path) -> SolvedExample` classmethod on `SolvedExample`.** Convenience parser used by S4-07's rebuild: `cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))` — sharing the exact `model_validate(yaml.safe_load(...))` parse core the AC-6 roundtrip property exercises. Errors surface as `pydantic.ValidationError` — S4-07 wraps them. Exercised by **two** tests (the TDD plan previously had none): a round-trip — `from_yaml` of a file written by `add()` equals the original `SolvedExample` — and a negative — `from_yaml` on a YAML file with an unknown extra key (or a missing required field) raises `pydantic.ValidationError`.
- [x] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. PyYAML is a project dep (verify in `pyproject.toml`; if absent, add).
- [x] **AC-12 — `manifest.yaml`-write failure semantics.** If `_atomic_write_text` for `manifest.yaml` raises *after* the chromadb write succeeded, `add()` re-raises; the canonical YAML record **and** the chromadb entry are on disk, but `manifest.yaml` is stale (does not list `example.id`). In-process, `self._record_ids` already holds `example.id`, so the *next* successful `add()` rewrites a manifest that re-includes it; across a process restart the stale manifest under-counts and the chromadb/YAML divergence is reconciled by `codegenie rag rebuild` (S4-07). Test pins: monkeypatch the manifest write to raise → YAML record present, chromadb has the record, `manifest.yaml` does not list `example.id`, `add()` re-raised.
- [x] **AC-13 — Manifest references a missing record file → `StoreCorrupted`.** If `manifest.yaml` lists a record id whose `<root>/records/<id>.yaml` is absent (crashed write, manual deletion, partial restore), the store fails loud: `_load_existing_record_ids` (or the first `_compute_chain_head` it triggers) raises `StoreCorrupted("manifest references missing record: <id>")` — **not** a raw `FileNotFoundError`. Without this guard, `_compute_chain_head`'s `read_bytes()` leaks `FileNotFoundError` out of `digest()` and the next `add()`. Test pins: hand-write a `manifest.yaml` listing `ex-missing` with no `ex-missing.yaml` on disk → opening the store (or its first `digest()`) raises `StoreCorrupted`.
- [x] **AC-14 — Record id is filesystem-path-safe.** `add()` constructs `<root>/records/<example.id>.yaml`; an `example.id` containing `/`, `..`, or a NUL byte would escape `records/`. `SolvedExample.id` is typed `SolvedExampleId`, whose S1-01 smart constructor enforces a BLAKE3-hex shape (`^[0-9a-f]{...}$`). **Verify** that constraint is actually enforced at `SolvedExample` construction (S1-04): if the Pydantic model validates `id` through the smart constructor, no write-path check is duplicated — state that and add one defensive test asserting a non-hex id is unconstructable; if the model does **not** re-validate (a bare `NewType` field accepts any `str`), `add()` must reject a non-`^[0-9a-f]{8,64}$` id with a `ValueError` before any write. Either way a test proves `id="../../etc/passwd"` cannot reach a filesystem write.
- [x] **AC-15 — Empty-store invariants.** A `ChromaPersistentStore` opened against an empty `root_dir` has `_record_ids == []`, **no** `manifest.yaml` on disk, and `digest()` returns `StoreDigest(blake3.blake3(b"").hexdigest())` — the empty-chain constant `af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262` (consistent with S4-03 AC-6's empty-store digest). After the first `add()`, `manifest.yaml` exists with `records: ["<id>"]`. Test pins both states.

## Implementation outline

1. **Verify PyYAML in `pyproject.toml`.** Phase 1/2 writers use it for `repo-context.yaml`; should be there already (Rule 8).
2. **Add the chain-head reduction — pure core + I/O shell** at module-top of `src/codegenie/rag/store.py`. The reduction (`_roll_chain_head`) is the *functional core* — table-testable with synthetic bytes, no filesystem; AC-8's prefix/monotonic contract is pinned against it. `_compute_chain_head` is the thin *imperative shell* that reads files and translates a missing file to `StoreCorrupted` (AC-13):
   ```python
   def _roll_chain_head(record_bytes: Iterable[bytes]) -> ChainHead:
       """Pure: BLAKE3 over the concatenation of record bytes, in iteration order."""
       h = blake3.blake3()
       for b in record_bytes:
           h.update(b)
       return ChainHead(h.hexdigest())

   def _compute_chain_head(record_ids: list[SolvedExampleId], records_dir: Path) -> ChainHead:
       """Shell: read each canonical YAML record, then roll. Raises StoreCorrupted
       (not FileNotFoundError) when a listed record file is absent (AC-13)."""
       def _read(rid: SolvedExampleId) -> bytes:
           try:
               return (records_dir / f"{rid}.yaml").read_bytes()
           except FileNotFoundError as e:
               raise StoreCorrupted(f"manifest references missing record: {rid}") from e
       return _roll_chain_head([_read(rid) for rid in record_ids])
   ```
3. **Add manifest model** as a small Pydantic frozen-extra-forbid model in `src/codegenie/rag/store.py`:
   ```python
   class _Manifest(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       schema_version: Literal[1] = 1
       records: list[SolvedExampleId]
       chain_head: ChainHead
   ```
4. **Atomic-write helper** — mirror the existing idiom at `src/codegenie/probes/layer_d/conventions.py` (`_atomic_write_text`); do **not** redesign it. No `mkdir` inside the helper — a write helper that silently creates directories is hidden state; the caller mkdirs `records/` explicitly (AC-1). The repo already has ~8 per-module copies of this idiom; a shared `codegenie/_fsutil.py` consolidation is a sanctioned-migration candidate but **out of scope** for S4-04 (Rule 3 — surgical; see Notes §2).
   ```python
   def _atomic_write_text(path: Path, content: str) -> None:
       """Write atomically via tmp + os.replace. Caller ensures path.parent exists."""
       tmp = path.with_suffix(path.suffix + ".tmp")
       tmp.write_text(content, encoding="utf-8")
       os.replace(tmp, path)
   ```
5. **Extend `add()`** (after lock acquired; all three writes inside the existing `asyncio.Lock`):
   ```python
   # 1. Canonical YAML — via the shared serialization surface
   records_dir.mkdir(parents=True, exist_ok=True)
   _atomic_write_text(records_dir / f"{example.id}.yaml", _canonical_yaml_dump(example))

   # 2. chromadb (existing S4-03 path) — if this raises, step 3 never runs (AC-4)
   await asyncio.to_thread(collection.add, ids=[example.id], embeddings=[...], ...)

   # 3. Manifest — updated last (AC-2); if this raises, AC-12 semantics apply
   self._record_ids.append(example.id)
   chain_head = _compute_chain_head(self._record_ids, records_dir)
   manifest = _Manifest(records=list(self._record_ids), chain_head=chain_head)
   _atomic_write_text(root / "manifest.yaml",
                      yaml.safe_dump(manifest.model_dump(), sort_keys=True,
                                     default_flow_style=False, allow_unicode=True))
   ```
   where `_canonical_yaml_dump(model: BaseModel) -> str` (on the Green path, not just Refactor) is the **single** serialization surface — `yaml.safe_dump(model.model_dump(mode="json"), sort_keys=True, default_flow_style=False, allow_unicode=True)`.
6. **Rewire `_load_existing_record_ids`:** read `manifest.yaml`; absent → `[]` (fresh store). Present → parse defensively (AC-9): wrap `yaml.safe_load` in `try/except yaml.YAMLError → raise StoreCorrupted(...) from e`; assert the result is a mapping; check the raw `schema_version` is `1` **before** `_Manifest.model_validate(...)`; translate any `pydantic.ValidationError` to `StoreCorrupted`. After a successful parse, verify every listed record id has a `<records_dir>/<id>.yaml` on disk (AC-13) — absent → `StoreCorrupted`. `_Manifest` deliberately gets **no** `from_yaml` classmethod — it is module-private; this inline parse is its only reader. Only the public `SolvedExample` gets a named `from_yaml` (AC-10).
7. **Update `digest()`:** `return StoreDigest(_compute_chain_head(self._record_ids, self._records_dir))` — the same computation the manifest write uses, re-typed from `ChainHead` to the Protocol-pinned `StoreDigest` (AC-5). Comment the cross-newtype lift.
8. **`SolvedExample.from_yaml` classmethod:** `cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))`.
9. **Tests:** `tests/unit/rag/test_store_yaml_canonical.py` covers AC-1..AC-5, AC-7, AC-9, AC-10, AC-12, AC-13, AC-14, AC-15; `tests/property/test_solved_example_yaml_roundtrip.py` covers AC-6; `tests/unit/rag/test_chain_head_monotonic.py` covers AC-8 (both the monotonic-unique store test and the pure `_roll_chain_head` prefix-stability table test).

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
    Catches the "skip-yaml-write" mutant. Without YAML on disk,
    `codegenie rag rebuild` cannot reconstruct. (Write-*order* is proved
    by the AC-4 chromadb-failure test, not here.)"""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-canonical-001"))
    example = make_solved_example(id_="ex-canonical-001", cve_id="CVE-2026-1111")
    await store.add(example, cap)

    yaml_path = tmp_path / "records" / "ex-canonical-001.yaml"
    assert yaml_path.is_file(), "canonical YAML record must be written"

    raw = yaml_path.read_text(encoding="utf-8")
    body = yaml.safe_load(raw)
    assert body["id"] == "ex-canonical-001"
    assert body["cve_id"] == "CVE-2026-1111"
    # Sorted-key discipline (AC-1): assert the FULL top-level key ordering on the
    # raw text, not a single first-key check. A sort_keys=False mutant on a model
    # with >=2 top-level fields fails here.
    top_level_keys = [ln.split(":")[0] for ln in raw.splitlines()
                      if ln and not ln.startswith((" ", "#", "-"))]
    assert top_level_keys == sorted(top_level_keys), "top-level keys must be sorted"
    store.close()


@pytest.mark.asyncio
async def test_chain_head_equals_digest_after_add(tmp_path: Path) -> None:
    """AC-5 — manifest.chain_head must string-equal store.digest(). This is a
    *consistency* invariant — necessary but NOT sufficient on its own (both
    sides delegate to _compute_chain_head). The correctness oracle is the
    next test."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-chain"))
    await store.add(make_solved_example(id_="ex-a"), cap)
    await store.add(make_solved_example(id_="ex-b"), cap)

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["chain_head"] == store.digest()
    assert manifest["records"] == ["ex-a", "ex-b"]
    assert manifest["schema_version"] == 1
    store.close()


@pytest.mark.asyncio
async def test_chain_head_is_blake3_of_concatenated_canonical_yaml(tmp_path: Path) -> None:
    """AC-5 independent oracle. `chain_head == digest()` alone is self-fulfilling
    (both delegate to _compute_chain_head). This recomputes the expected hash
    from a different code path — catches roll-over-IDs, sorted-order, and
    per-record-hash-then-XOR mutants. Insertion order is deliberately NOT sorted
    (b before a) so a `sorted()` mutant produces a||b and fails."""
    import blake3

    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-oracle"))
    await store.add(make_solved_example(id_="ex-b"), cap)   # insert b FIRST
    await store.add(make_solved_example(id_="ex-a"), cap)   # then a

    expected = blake3.blake3(
        (tmp_path / "records" / "ex-b.yaml").read_bytes()
        + (tmp_path / "records" / "ex-a.yaml").read_bytes()
    ).hexdigest()
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["chain_head"] == expected
    assert manifest["records"] == ["ex-b", "ex-a"]  # insertion order, not sorted
    store.close()
```

Why it fails: S4-03's `add()` doesn't write YAML, doesn't write a manifest, and `digest()` rolls over IDs (not bytes), so AC-5 won't match.

### Green — make it pass

- Extend `add()` per Implementation Outline §5 (all three writes inside the lock; `_canonical_yaml_dump` as the serialization surface).
- Rewrite `digest()` to `StoreDigest(_compute_chain_head(...))` — the same computation the manifest write uses, re-typed to the Protocol return type (AC-5).
- Add `_roll_chain_head` (pure) + `_compute_chain_head` (shell, `StoreCorrupted`-translating).
- Rewire `_load_existing_record_ids` to read + defensively validate `manifest.yaml` (AC-9, AC-13).

### Refactor

- `_canonical_yaml_dump(model: BaseModel) -> str` is **not** a refactor-step extraction — it is on the Green path from the start (Outline §5), the single serialization surface shared by the record write, the manifest write, and the AC-6 roundtrip property.
- Module docstring updates: YAML-canonical contract + the single-writer-lock-covers-all-three-writes invariant explicitly named.
- Structured-log emissions: `store.add.yaml_written`, `store.add.chroma_written`, `store.add.manifest_updated` — emitted in write order; an optional log-capture test can assert the ordering.

### Required follow-on tests

- `test_chromadb_write_failure_leaves_yaml_orphan` (AC-4) — **two cases:** (a) first-ever add fails → orphan YAML present, `manifest.yaml` does **not** exist, `example.id` not in `_record_ids`, the *named* exception re-raised; (b) Nth add fails after one good add → snapshot `manifest.yaml` bytes, failing add, assert bytes byte-unchanged. Monkeypatch `collection.add` to raise a *specific* exception type and `pytest.raises(ThatType)` — never bare `Exception`.
- `test_manifest_write_failure_leaves_chroma_and_yaml` (AC-12) — monkeypatch the `manifest.yaml` write to raise; assert YAML record present, chromadb has the record, `manifest.yaml` does not list `example.id`, `add()` re-raised.
- `test_load_existing_record_ids_from_manifest` (AC-3) — open a fresh `ChromaPersistentStore` against a `tmp_path` with a hand-written `manifest.yaml` + records; assert `_record_ids` matches the manifest order.
- `test_unknown_schema_version_raises_store_corrupted` (AC-9) — `manifest.yaml` with `schema_version: 999` → opening raises `StoreCorrupted`.
- `test_malformed_manifest_raises_store_corrupted` (AC-9) — parametrized: truncated / unparseable YAML, a manifest missing the `records` key, a `records` value that is not a list → each raises `StoreCorrupted`, never a raw `yaml.YAMLError` / `pydantic.ValidationError`.
- `test_manifest_references_missing_record_file` (AC-13) — hand-write a `manifest.yaml` listing `ex-missing` with no `ex-missing.yaml`; opening the store (or its first `digest()`) raises `StoreCorrupted`, not `FileNotFoundError`.
- `test_record_id_path_traversal_rejected` (AC-14) — an `id` of `"../../etc/passwd"` cannot reach a filesystem write (unconstructable `SolvedExampleId`, or `add()` raises `ValueError` before writing).
- `test_empty_store_invariants` (AC-15) — fresh store: `_record_ids == []`, no `manifest.yaml`, `digest()` equals the empty-chain constant; after first `add()`, `manifest.yaml` exists.
- `test_chain_head_monotonic_and_unique` (AC-8) — `tests/unit/rag/test_chain_head_monotonic.py`; 10 sequential adds; `len(set(chain_heads)) == 10`.
- `test_roll_chain_head_is_prefix_stable` (AC-8) — pure table test on `_roll_chain_head`: the reduction of `[b0, b1, b2]` equals the 3-prefix reduction within `[b0, b1, b2, b3, b4]`; synthetic bytes, no filesystem.
- `test_chain_head_prefix_stable_across_two_stores` (AC-8) — store A with N records, store B with N+5; A's `digest()` equals `blake3` of B's first-N record bytes.
- `test_two_stores_same_order_produce_identical_manifest_bytes` (AC-7) — `created_at` fixed via the `make_solved_example(created_at=...)` fixture default; two `tmp_path` stores receive identical sequences; `read_bytes()` of both `manifest.yaml` files are equal (raw bytes, no `safe_load`).
- `test_from_yaml_roundtrips_a_written_record` + `test_from_yaml_raises_validation_error_on_malformed` (AC-10).
- Hypothesis property (AC-6) in `tests/property/test_solved_example_yaml_roundtrip.py` — explicit per-field strategy, `@settings(max_examples=50, deadline=None, database=None)`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/store.py` | Extend `add()` for YAML + manifest write; rewire `_load_existing_record_ids` (defensive `StoreCorrupted` translation); rewrite `digest()` to `StoreDigest(_compute_chain_head(...))`; add `_Manifest` model + `_roll_chain_head` (pure) + `_compute_chain_head` (shell) + `_atomic_write_text` (mirror `layer_d/conventions.py`) + `_canonical_yaml_dump` helpers. |
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

The current `_Manifest` schema is version 1. A Phase-11 pgvector swap may change the manifest format (e.g., add a `backend_kind: Literal["chromadb", "pgvector"]` field). Bumping the version is the upgrade path; a reader at version 1 should **refuse-start** on version 2 with a diagnostic naming the upgrade command. The version is `Final[Literal[1]]` here — the literal is the constraint Pydantic enforces. **Do not** build a `schema_version`-keyed dispatch table now — with exactly one version it is premature abstraction (Rule 2); the genuine Open/Closed seam arrives when Phase 11 introduces v2. AC-9's ordering note matters: the raw `schema_version` is checked **before** `_Manifest.model_validate`, because `extra="forbid"` would otherwise reject a v2 manifest with a generic `ValidationError` instead of the intended `StoreCorrupted` diagnostic.

### §9 — A stale `.yaml.tmp` from a crashed write is harmless

`_atomic_write_text` writes `<id>.yaml.tmp` then `os.replace`. A crash between the two leaves an orphan `.tmp`. This is harmless and needs **no** cleanup logic: `os.replace` overwrites the same tmp path on the next `add()` of that id, and `_load_existing_record_ids` reads the **manifest** (not a `records/*.yaml` glob), so `.tmp` files are never enumerated. Do not add a `.tmp` sweeper, and do not write a `records/` glob that would pick `.tmp` files up.

### §10 — The O(N) re-read in `_compute_chain_head` is intentional — do not "optimize" it

`_compute_chain_head` re-reads every prior record file on each `add()` (O(N) per add, O(N²) for a full ingest). This is deliberate, not an oversight. A running `blake3` hasher held on the store would be O(1) amortized but is **hidden mutable state** that must stay byte-exactly in lockstep with the on-disk records — if it ever desyncs, `digest()` silently lies (a Rule 12 violation). The stateless re-read makes `digest()` a pure projection and makes AC-12's "next `add()` recomputes from disk" recovery actually true. At Phase-4 corpus sizes (solved-example RAG, ~6.5 KB/record — ADR-0016) the re-read is well inside the `add() < 50 ms` budget. Revisit **only** if a perf test against that budget fails — never speculatively.
