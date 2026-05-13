# Story S6-07 — Distroless RAG corpus + top-1 retrieval test

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S6-06
**ADRs honored:** ADR-P7-003 (`task_type` selects the distroless RAG collection), ADR-P7-009 (`DistrolessLedger`)

## Context

S6-06's LLM-fallback test deliberately forces a RAG miss. This story is the *positive* path: with a curated set of solved distroless examples seeded into the `distroless_solved_examples_promoted` vector store collection, a distroless query must retrieve a **distroless** example as top-1 — never a vuln example. This is Risk #2's load-bearing mitigation: cross-task retrieval contamination would produce vuln-shaped patches for distroless queries, and the LLM would happily comply (then fail at the validation gate, burning the retry budget and the LLM cost). Forcing top-1 correctness at the retrieval layer is the cheapest defense.

The story ships two artefacts: the **hand-curated seed corpus** of ≥ 3 distroless solved examples (with embeddings produced by the same model Phase 4 uses, content-addressed), and the **integration test** that issues a distroless-shaped query and asserts the top-1 is from the distroless collection.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #14` — RAG retrieves a vuln-shaped example for a distroless query → LLM produces a vuln-shaped patch → fails at sandbox
  - `../phase-arch-design.md §Testing strategy ›Integration tests ›test_rag_distroless_top1` (line 1239) — Risk #2 mitigation
  - `../phase-arch-design.md §Risks` — Risk #2 is the cross-task retrieval contamination case
  - `../phase-arch-design.md §Development view ›rag/seed_corpus/distroless/` (line 283) — the corpus location
  - `../phase-arch-design.md §Scenarios ›Scenario 2` — `task_type="distroless_migration"` selects the distroless collection in `FallbackTier`
- **Phase ADRs:**
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — `FallbackTier` searches the `{task_type}_solved_examples_promoted` collection (lines 24, 877)
- **Phase 4 prior art (vector store + retrieval pattern — clone, don't reinvent):**
  - `../../04-vuln-llm-fallback-rag/final-design.md` — `vuln_solved_examples_promoted` collection shape, embedding model, similarity threshold (0.85 per the architecture)
  - Phase 4's `chromadb` (or whichever store is pinned) collection creation + seeding pattern
- **Existing code:**
  - `src/codegenie/planner/rag/` (Phase 4) — vector store interface; reuse verbatim
  - `src/codegenie/planner/fallback_tier.py` (Phase 4 + S1-04) — `task_type` kwarg routes to the distroless collection
  - `rag/seed_corpus/` (Phase 4) — existing vuln seed corpus to mirror

## Goal

The `distroless_solved_examples_promoted` vector store collection is seeded with ≥ 3 hand-curated distroless migration examples, and `tests/integration/test_rag_distroless_top1.py` asserts that a representative distroless query retrieves a distroless example as top-1 (Risk #2 mitigation).

## Acceptance criteria

- [ ] `rag/seed_corpus/distroless/` exists with ≥ 3 hand-curated solved-example markdown files. Each example follows Phase 4's existing schema for vuln examples — same frontmatter shape, same body sections (`Problem`, `Diff`, `Validation`), but the content is distroless-shaped (`FROM ... → FROM cgr.dev/chainguard/...`).
- [ ] Each seed example has a frontmatter `task_type: "distroless_migration"`, `language: "node"` / `"go"` / `"python"`, and a `dockerfile_pattern` tag (`"single_stage_swap"` / `"multi_stage_refactor"`).
- [ ] A seed-loader script `src/codegenie/planner/rag/seed_distroless.py` (or extension to an existing Phase 4 seeder) creates the `distroless_solved_examples_promoted` collection if missing and inserts the seed examples with content-addressed IDs and the pinned embedding model.
- [ ] `tests/unit/planner/rag/test_distroless_corpus_schema.py` exists. Iterates `rag/seed_corpus/distroless/*.md`; validates frontmatter against Phase 4's example schema; asserts the corpus has ≥ 3 entries; asserts every entry's `task_type == "distroless_migration"`.
- [ ] `tests/integration/test_rag_distroless_top1.py` exists and is green. It:
  - Initializes / re-seeds the `distroless_solved_examples_promoted` collection.
  - **Also** ensures the existing `vuln_solved_examples_promoted` collection has at least one entry (the worst-case adversarial scenario for Risk #2 is when vuln examples *exist* and could "win" cross-collection).
  - Issues a distroless-shaped query (`"migrate node:20-bullseye-slim Express service to chainguard distroless"`) through `FallbackTier`'s RAG lookup with `task_type="distroless_migration"`.
  - Asserts the top-1 result is from `distroless_solved_examples_promoted` — never from the vuln collection.
  - Asserts the top-1 result's `task_type` frontmatter is `"distroless_migration"`.
  - Repeats for 3 distroless query shapes (node, go, python) — top-1 is a distroless example each time.
- [ ] A negative-case test asserts that a *vuln* query with `task_type="vuln_remediation"` retrieves a *vuln* example, not a distroless one — guards the symmetric case (Risk #2 reverse).
- [ ] `pytest tests/integration/test_rag_distroless_top1.py` is wired into the CI lane.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the seeder + tests.

## Implementation outline

1. Read Phase 4's vuln seed example shape. Pick the frontmatter schema; pick the embedding model (it's pinned in Phase 4's config).
2. Author 3 distroless seed examples. Hand-curate them — they're the production signal for the retrieval graph. Suggested choices: (a) Node Express single-stage swap to `cgr.dev/chainguard/node:20` (mirrors S5-06's happy path); (b) Multi-stage Go static binary to `cgr.dev/chainguard/static` (mirrors S6-03); (c) Python service with multi-stage build to `cgr.dev/chainguard/python:3.12` (a third language to anchor cross-language top-1 correctness).
3. Write the corpus-schema unit test; run; red because the files don't exist.
4. Write the seeder script. Reuse Phase 4's chromadb (or equivalent) client; share the same embedding model; content-addressed IDs (blake3 of the content).
5. Write the top-1 integration test; run; red because the collection isn't seeded.
6. Run the seeder; rerun the test; green.
7. Add the symmetric vuln-top-1 test in the same file (ensures we don't accidentally break Phase 4 retrieval).

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/planner/rag/test_distroless_corpus_schema.py
from pathlib import Path
import yaml
import jsonschema

CORPUS = Path("rag/seed_corpus/distroless")
SCHEMA = Path("rag/seed_corpus/_example_schema.json")  # Phase 4's existing schema

def _examples() -> list[Path]:
    return sorted(CORPUS.glob("*.md"))

def test_distroless_corpus_has_at_least_three_examples():
    assert len(_examples()) >= 3

def test_every_distroless_example_validates_against_phase4_schema():
    schema = __import__("json").loads(SCHEMA.read_text())
    for p in _examples():
        front, _, _ = p.read_text().partition("---\n")
        # parse YAML frontmatter using Phase 4's helper, not ad-hoc
        meta = yaml.safe_load(...)
        jsonschema.validate(meta, schema)
        assert meta["task_type"] == "distroless_migration"
```

```python
# tests/integration/test_rag_distroless_top1.py
import pytest
from codegenie.planner.fallback_tier import FallbackTier
from codegenie.planner.rag import VectorStore

DISTROLESS_QUERIES = [
    "migrate node:20-bullseye-slim Express service to chainguard distroless",
    "swap multi-stage Go build runtime to cgr.dev/chainguard/static",
    "convert python:3.12-slim service to chainguard distroless python",
]

@pytest.fixture(scope="module")
def seeded_vector_store():
    store = VectorStore.bootstrap()
    store.seed_collection("distroless_solved_examples_promoted",
                          source_dir="rag/seed_corpus/distroless")
    store.seed_collection("vuln_solved_examples_promoted",
                          source_dir="rag/seed_corpus/vuln")  # at least one entry
    yield store
    store.teardown_test_collections()

@pytest.mark.parametrize("query", DISTROLESS_QUERIES)
def test_distroless_query_top1_is_distroless_example(seeded_vector_store, query):
    result = seeded_vector_store.search(
        collection="distroless_solved_examples_promoted",
        query=query,
        task_type="distroless_migration",  # via FallbackTier’s API
        k=1,
    )
    assert result.hits, "expected at least one retrieval result"
    top = result.hits[0]
    assert top.collection == "distroless_solved_examples_promoted"
    assert top.metadata["task_type"] == "distroless_migration"

def test_vuln_query_top1_is_vuln_example_symmetric_guard(seeded_vector_store):
    result = seeded_vector_store.search(
        collection="vuln_solved_examples_promoted",
        query="patch CVE-2024-1234 in lodash",
        task_type="vuln_remediation",
        k=1,
    )
    assert result.hits[0].metadata["task_type"] == "vuln_remediation"
```

Red surfaces: corpus directory empty; vector store collection not seeded; `task_type` parameter not threaded through Phase 4's search API (S1-04 should have done this).

### Green — make it pass

- Author the 3 seed examples; run the seeder; rerun.
- If the symmetric vuln-top-1 test fails, surface a regression to Phase 4 — *do not* paper over it.

### Refactor — clean up

- Document the seeder invocation in `rag/seed_corpus/distroless/README.md` (manual reseed: `python -m codegenie.planner.rag.seed_distroless`).
- Add a `tests/fixtures/rag/` directory if test isolation requires sandboxed vector stores (chromadb's `persist_directory` per test).
- Pin the embedding model + dimension in the integration test's setup (read from Phase 4's config; assert via `xfail` if Phase 4 bumps the model).

## Files to touch

| Path | Why |
|---|---|
| `rag/seed_corpus/distroless/01-node-single-stage-swap.md` | New — seed example, Node Express → Chainguard node:20 |
| `rag/seed_corpus/distroless/02-go-multi-stage-static.md` | New — seed example, Go → cgr.dev/chainguard/static |
| `rag/seed_corpus/distroless/03-python-multi-stage.md` | New — seed example, Python → cgr.dev/chainguard/python:3.12 |
| `rag/seed_corpus/distroless/README.md` | New — corpus purpose, reseed command |
| `src/codegenie/planner/rag/seed_distroless.py` | New (or extension to Phase 4's seeder) — collection bootstrap |
| `tests/unit/planner/rag/test_distroless_corpus_schema.py` | New — schema validation |
| `tests/integration/test_rag_distroless_top1.py` | New — Risk #2 mitigation |

## Out of scope

- **Vector-store choice** (`chromadb` vs alternatives). Phase 4 owns that decision; this story reuses.
- **Embedding model choice**. Pinned by Phase 4; this story uses it.
- **Production corpus growth.** ≥ 3 is the floor; Phase 14 owns continuous corpus gathering. Adding more examples in this PR is fine but not required.
- **Per-collection access control.** Out of scope; FallbackTier's `task_type` routing is the contract.
- **The `migration_distroless.v1.yaml` prompt template.** S6-06 owns it; this story is the corpus, not the prompt.
- **LLM fallback E2E.** S6-06's test; this story is the retrieval-only correctness test.
- **Adversarial corpus poisoning.** S6-09 handles typosquat; cross-collection adversarial seeding is deferred to Phase 14.

## Notes for the implementer

- The seed examples are **hand-curated production signal**, not throwaway test data. They are the priors the LLM-fallback path retrieves. Author them with care — re-use prose from S5-06 / S6-03's actual migrations if possible so the corpus mirrors real-world outputs.
- **Risk #2 is symmetric.** A distroless-shaped vuln example would be a smaller blast radius than the reverse, but both fail equally loudly. The negative test guards the symmetric case; do not skip it.
- Content-addressed IDs ensure idempotent reseeding. If you change a seed example's body, its hash changes and the collection update is a delete+insert, not a duplicate.
- **Embedding model pinning.** Phase 4's config pins the model (likely `text-embedding-3-small` or a sentence-transformers model). If S6-06's prompt template references few-shots from this corpus, the embedding-time and retrieval-time models must match exactly.
- The integration test must isolate its vector-store state from other tests. Use a per-test-module `persist_directory` (`tmp_path` scope-`module`), and tear down on session end. Do not pollute the global `.codegenie/rag/` directory.
- The `task_type` parameter routing is from S1-04 (Phase 4 widening). If the test discovers that `FallbackTier.search` does NOT thread `task_type` through to the collection selection, surface a bug to S1-04 — do not patch the test.
- Per `phase-arch-design.md §Risks #2` and `final-design.md` Risk #2 commentary, this test is the cheapest defense against cross-task contamination. Treat its assertions as non-skippable.
- Update story `Status:` to `Done` when complete.
