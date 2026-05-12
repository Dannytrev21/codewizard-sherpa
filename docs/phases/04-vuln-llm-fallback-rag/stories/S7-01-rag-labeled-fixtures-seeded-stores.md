# Story S7-01 — RAG labeled-triples fixture (30) + seeded chromadb stores + cassette corpus structure

**Step:** Step 7 — Harden — adversarial corpus, recall@3, perf canaries, E2E exit criterion, Phase-3 regression, Phase-5 handoff, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S5-03, S4-01
**ADRs honored:** ADR-P4-005, ADR-P4-006, ADR-P4-012, ADR-P4-015

## Context

Every Step 7 quality gate — recall@3, perf canaries, the E2E breaking-change exit-criterion test, adversarial corpus — feeds off three test-fixture artifacts: (1) 30 labeled `(query_text, expected_top1_id, expected_in_top3_ids)` triples that pin RAG retrieval quality, (2) five pre-built `chromadb` stores at sizes 5/20/50/100 plus an empty store for the LLM-cold E2E, and (3) the `tests/fixtures/cassettes/<test_module>/<test_function>.yaml` directory layout the `pytest-recording` discipline (S3-06) writes to. Nothing in Step 7 functions without these — they're the load-bearing test-data substrate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Fixture portfolio"` — names `tests/fixtures/rag_labeled/`, `tests/fixtures/seeded_chromadb/`, `tests/fixtures/cassettes/<test_module>/<test_function>.yaml`.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — recall@3 ≥ 0.85 (G13) audited by `test_rag_retrieval_recall_at_k.py` against this fixture.
  - `../phase-arch-design.md §"CI gates"` — `cassettes-reviewed` PR label + `VCR_BAN_NEW_CASSETTES=1` discipline gates consume the cassette layout.
- **Phase ADRs:**
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005; the seeded stores must be the on-disk shape `SolvedExampleStore` opens.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006; every seeded store records `embedding_model_digest` matching the SHA-pinned `bge-small-en-v1.5` (Gap 2 — digest-mismatch query returns empty).
  - `../ADRs/0012-vcr-cassette-discipline.md` — ADR-P4-012; cassettes content-addressed by `blake3(canonical(system, few_shots, query))`; `before_record_response` rewrites the canary on replay; size budget per directory.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015; each seeded example is a valid `SolvedExample v0.4.0` row.
- **Source design:** `../final-design.md §"Synthesis ledger row" recall corpus row` — 30-triple labeled fixture is the operational closure of G13.
- **Existing code:**
  - `src/codegenie/rag/store.py` (S4-04) — the `SolvedExampleStore` whose on-disk format the seeded stores must match.
  - `src/codegenie/rag/embeddings/local.py` (S4-02) — SHA-pinned `bge-small-en-v1.5` provider whose digest is stamped into store metadata.
  - `src/codegenie/rag/models.py` (S1-03) — `SolvedExample` schema v0.4.0.
  - `tests/conftest.py` (Phase 0) — fixture loader conventions.

## Goal

Land the three fixture-substrate artifacts — 30 labeled retrieval triples, five pre-built `chromadb` stores at sizes 5/20/50/100 + empty, and the documented `tests/fixtures/cassettes/<test_module>/<test_function>.yaml` layout — so every downstream Step 7 story (S7-02 through S7-06) has the data it needs to run.

## Acceptance criteria

- [ ] `tests/fixtures/rag_labeled/triples.yaml` exists with **exactly 30** records; each record has `query_text: str`, `expected_top1_id: str`, `expected_in_top3_ids: list[str]` with `expected_top1_id` ∈ `expected_in_top3_ids` and `|expected_in_top3_ids| == 3`.
- [ ] Triple construction documented in `docs/phases/04-vuln-llm-fallback-rag/runbook.md §"RAG retrieval fixture construction"` (selection criteria, rotation cadence quarterly per ADR-amendment per ADR-P4-015 row).
- [ ] `tests/fixtures/seeded_chromadb/{empty,size_5,size_20,size_50,size_100}/` exist on disk; each readable by `SolvedExampleStore.read()` with no warnings; every example's `embedding_model_digest` matches the SHA pinned in `tools/digests.yaml` for `bge-small-en-v1.5`.
- [ ] A loader fixture in `tests/conftest.py` (or `tests/fixtures/conftest.py`) exposes `pytest.fixture` named `seeded_store_5`, `seeded_store_20`, `seeded_store_50`, `seeded_store_100`, `seeded_store_empty` that yield read-only opened `SolvedExampleStore` handles to copied-to-tmp paths.
- [ ] Per-store size on disk ≤ **5 MB**; size assertion test green; over-budget triggers a documented `git-lfs track 'tests/fixtures/seeded_chromadb/**'` path (call out the threshold in the runbook).
- [ ] `tests/fixtures/cassettes/.gitkeep` plus `tests/fixtures/cassettes/README.md` documenting the content-addressed key formula `blake3(canonical_json(system_blocks, few_shots_block, query_block))[:16].yaml` and the `before_record_response` canary rewrite hook from S3-06.
- [ ] All 30 triples deserialize via a `LabeledTriple` Pydantic model in `tests/fixtures/rag_labeled/loader.py` with `extra="forbid"`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `tests/fixtures/rag_labeled/loader.py` clean.
- [ ] `pytest tests/fixtures/test_rag_labeled_loads.py tests/fixtures/test_seeded_stores_open.py tests/fixtures/test_seeded_store_size_budget.py` green.

## Implementation outline

1. Author `tests/fixtures/rag_labeled/triples.yaml` by selecting 30 representative `query_text` strings that span: peer-dep CVEs, transitive vuln CVEs, breaking-change major-version-bump CVEs, yarn.lock, pnpm-lock.yaml, npm-shrinkwrap.json shapes, plus 5 near-miss negatives. For each, hand-pick the expected top-1 + 2 acceptable top-3 alternates against an existing seeded corpus.
2. Author `tests/fixtures/rag_labeled/loader.py` with a `LabeledTriple` Pydantic model and a `load_all() -> list[LabeledTriple]` helper.
3. Build the five seeded stores by writing a one-shot generator script `tests/fixtures/seeded_chromadb/_build.py` (not run in CI; runs once locally to commit the fixtures). It uses `SolvedExampleStore.write()` against the pinned `bge-small-en-v1.5` digest, never the live SDK. Commit the generated `chroma.sqlite3` + parquet under each size dir.
4. Write `tests/fixtures/seeded_chromadb/README.md` documenting how to regenerate (`python -m tests.fixtures.seeded_chromadb._build`), which digest is pinned, and the rotation policy.
5. Author the cassette directory README and `.gitkeep`; document the content-addressing scheme + the human-review label gate.
6. Register the pytest fixtures in `tests/conftest.py` (copy-to-tmp so tests can mutate without mutating the committed fixture).
7. Extend `docs/phases/04-vuln-llm-fallback-rag/runbook.md` (or create it stubbed if not yet present — full runbook lands in S7-06) with the "RAG retrieval fixture construction" + "Quarterly rotation" sections.

## TDD plan — red / green / refactor

### Red

`tests/fixtures/test_rag_labeled_loads.py`

```python
def test_rag_labeled_triples_well_formed_and_exactly_thirty():
    from tests.fixtures.rag_labeled.loader import load_all

    triples = load_all()

    assert len(triples) == 30, f"expected exactly 30 triples, got {len(triples)}"
    ids_seen: set[str] = set()
    for t in triples:
        assert t.query_text.strip(), "empty query_text"
        assert t.expected_top1_id in t.expected_in_top3_ids, \
            f"top1 {t.expected_top1_id} not in top3 {t.expected_in_top3_ids}"
        assert len(t.expected_in_top3_ids) == 3, \
            f"expected_in_top3_ids must be length 3, got {len(t.expected_in_top3_ids)}"
        assert len(set(t.expected_in_top3_ids)) == 3, "duplicate ids in top3"
        ids_seen.update(t.expected_in_top3_ids)
    # spot-check shape coverage — must include at least one of each lockfile family
    queries = " ".join(t.query_text for t in triples).lower()
    assert "package-lock.json" in queries
    assert "yarn.lock" in queries
    assert "pnpm-lock.yaml" in queries
    assert "major" in queries or "breaking" in queries
```

`tests/fixtures/test_seeded_stores_open.py`

```python
import pytest

@pytest.mark.parametrize("size,expected_count", [(5, 5), (20, 20), (50, 50), (100, 100)])
def test_seeded_store_opens_and_count_matches_size(seeded_store_factory, size, expected_count):
    """Each seeded store opens cleanly, has the right example count, and every
    row carries the pinned bge-small-en-v1.5 digest (Gap-2 invariant: no mixed digests)."""
    from codegenie.rag.embeddings.local import PINNED_BGE_SMALL_DIGEST  # from S4-02

    with seeded_store_factory(size).read() as store:
        rows = store.list_all()
        assert len(rows) == expected_count
        digests = {r.embedding_model_digest for r in rows}
        assert digests == {PINNED_BGE_SMALL_DIGEST}, \
            f"mixed digests in seeded store: {digests}"


def test_seeded_store_empty_opens_with_zero_rows(seeded_store_empty):
    with seeded_store_empty.read() as store:
        assert store.list_all() == []
```

`tests/fixtures/test_seeded_store_size_budget.py`

```python
def test_each_seeded_store_under_5mb():
    """Per-ADR-P4-012 cassette-corpus budget + ADR-P4-005 store budget: each
    seeded store directory must be ≤ 5 MB on disk. Crossing the threshold
    means committing it under git-lfs (documented in the runbook)."""
    from pathlib import Path

    root = Path("tests/fixtures/seeded_chromadb")
    budget_bytes = 5 * 1024 * 1024
    for sub in ("empty", "size_5", "size_20", "size_50", "size_100"):
        size = sum(p.stat().st_size for p in (root / sub).rglob("*") if p.is_file())
        assert size <= budget_bytes, f"{sub} = {size} bytes > {budget_bytes}"
```

### Green

Minimal shape: 30 hand-written YAML records that satisfy the well-formedness asserts; five pre-built `chromadb` directories generated by the build script; loader Pydantic model with `extra="forbid"`.

### Refactor

- Type-annotate the loader. Docstring the `LabeledTriple` model with the rotation cadence reference.
- Add a `tests/fixtures/seeded_chromadb/MANIFEST.json` recording the pinned digest, size, and build timestamp for each store (audit-chain alignment with `EmbeddingDigestMismatch` story).
- Ensure the build script writes deterministically (sorted keys, fixed-order inserts) so regeneration is byte-stable.
- Cross-link the runbook section from `tests/fixtures/rag_labeled/triples.yaml` top-of-file comment.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/rag_labeled/triples.yaml` | 30 labeled `(query, top1, top3)` records. |
| `tests/fixtures/rag_labeled/loader.py` | Pydantic `LabeledTriple` + `load_all()`. |
| `tests/fixtures/seeded_chromadb/{empty,size_5,size_20,size_50,size_100}/` | Pre-built stores. |
| `tests/fixtures/seeded_chromadb/_build.py` | One-shot regenerator (not CI-run). |
| `tests/fixtures/seeded_chromadb/MANIFEST.json` | Per-store digest + size + timestamp. |
| `tests/fixtures/seeded_chromadb/README.md` | Regeneration + rotation docs. |
| `tests/fixtures/cassettes/README.md` | Content-addressing scheme + label gate. |
| `tests/fixtures/cassettes/.gitkeep` | Hold the directory in git. |
| `tests/conftest.py` | Register `seeded_store_*` fixtures. |
| `tests/fixtures/test_rag_labeled_loads.py` | Red test — 30 triples well-formed. |
| `tests/fixtures/test_seeded_stores_open.py` | Red test — open + digest invariant. |
| `tests/fixtures/test_seeded_store_size_budget.py` | Red test — 5 MB per-store budget. |
| `docs/phases/04-vuln-llm-fallback-rag/runbook.md` | Stub or extend with construction + rotation sections. |

## Out of scope

- **Running the recall@3 assertion** — handled by S7-03 (`test_rag_retrieval_recall_at_k.py`).
- **Recording cassettes for any LLM test** — that's S7-02/S7-04 against the directory this story creates.
- **Promotion / pending-vs-promoted seeding** — the size_5/20/50/100 stores hold only `merge_status="promoted"` rows; pending-shelf fixtures are local to whatever test needs them.
- **`git-lfs` migration** — only documented; not executed unless any store crosses 5 MB.
- **`solved-examples reindex` workflow** — operator surface lands in S7-06 runbook.

## Notes for the implementer

- The 30-triple set is the **recall@3 floor**, not the ceiling — over-tuning to it hides real-world drift. Document the quarterly rotation policy explicitly so the next reader knows refresh is gated by ADR amendment, not by whichever engineer is on call.
- The seeded stores must be **deterministically rebuildable**. If the build script is non-deterministic, every regeneration produces a churn-y diff and PR review becomes useless.
- The pinned `bge-small-en-v1.5` digest lives in `tools/digests.yaml` (Phase 0); read from there at fixture-build time, never hard-code the string in `_build.py`.
- The cassette directory is **created here, populated elsewhere**. Do not record any cassette in this story — S7-02 and S7-04 do, under `cassettes-reviewed` label discipline.
- Per Gap 2 (`../phase-arch-design.md §"Gap analysis"`) every seeded row must carry the model digest in chromadb metadata, not just in `SolvedExample.embedding_model_digest`. The seeded store must round-trip through `Store.write()` so this is consistent — do not bypass and write directly to sqlite.
- Per Rule 12 (fail loud): the build script should hard-fail if the pinned digest in `tools/digests.yaml` doesn't match the actually-downloaded model bytes. No silent "regenerated with a different model" path.
- File sizes balloon if the parquet uses default compression. Use `chromadb`'s built-in shape and rely on the 5 MB assertion as the canary; if it fires, switch to git-lfs (don't switch compression schemes silently — that breaks ADR-P4-005's "on-disk format is the contract").
