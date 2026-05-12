# Story S4-07 — `codegenie models fetch` + `solved-examples reindex` + `solved-examples prune --orphans` CLI

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S4-04 (`SolvedExampleStore` — the store ops the CLI invokes), S1-06 (CLI subcommand-group stubs + exit-code catalog)
**ADRs honored:** ADR-P4-006 (model digest pin + first-fetch verification; reindex is the documented recovery for Gap-2 digest drift), ADR-P4-005 (corruption quarantine via store helper; orphan-body recovery)

## Story scope

Three operator workflows, each a single CLI subcommand, wired against primitives the prior stories shipped. None of them invoke an LLM; all three are deterministic operator-facing tools.

1. **`codegenie models fetch [--model bge-small-en-v1.5] [--digest <sha>]`** — downloads (or re-verifies) the embedding model snapshot via `huggingface_hub.snapshot_download(revision=<digest>)`, verifies the observed digest matches `tools/digests.yaml`, idempotent. First-fetch path for new operators; re-verification path on every CI run.
2. **`codegenie solved-examples reindex --model-digest <new_digest> [--from-digest <old_digest>]`** — re-embeds every body JSON under the new digest, swaps the chromadb collection atomically to a new collection name, quarantines the old collection. Gap-2 recovery: after `models fetch` advances the default digest, this is what the operator runs to make the corpus query-able again.
3. **`codegenie solved-examples prune --orphans [--dry-run]`** — scans `.codegenie/rag/bodies/` for JSONs without a corresponding chromadb row and removes them. Edge case #15 recovery path: after a writeback partial-failure (body written, chromadb upsert failed), the orphan body sits on disk; this cleans it up.

## Context

These three subcommands are the operator-facing surface of the RAG-side data lifecycle. They turn three implicit failure modes from earlier stories into explicit, documented recovery workflows: (a) the model is missing or its digest doesn't match — `models fetch`; (b) the operator bumped the model — `solved-examples reindex`; (c) a writeback partial-failure left orphan body files — `solved-examples prune --orphans`. The CLI lands the workflows so the runbook (S7-06) has a deterministic incantation to point at; without this story, every operator gap response is a Python REPL session.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #7 — `models fetch` operator workflow; first-fetch path; airgapped operator note (`HF_HUB_OFFLINE=1`).
  - `../phase-arch-design.md §"Gap analysis" §"Gap 2"` — `solved-examples reindex --model-digest <new>` is the explicit recovery for embedding-model swap.
  - `../phase-arch-design.md §"Edge cases"` rows #2 (digest mismatch), #15 (orphan body recovery).
  - `../phase-arch-design.md §"Goals"` G15 — operator must have a clear recovery path for every observable failure mode.
- **Phase ADRs:**
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `codegenie models fetch` is the documented first-fetch + re-verification workflow; first-write protection on `tools/digests.yaml`.
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — reindex uses an atomic collection-rename swap so the old collection is recoverable.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `task_class` is preserved across reindex; the metadata pre-filter survives.
- **Production ADRs:**
  - `../../../production/adrs/0028-task-class-introduction-order.md` — reindex must be task-class agnostic; Phase 7's Chainguard examples must reindex through the same flow.
- **Source design:**
  - `../final-design.md §"CLI surface"` — `codegenie solved-examples {list,show,promote,prune,health}`; `codegenie auth {set-anthropic-key,fingerprint}`; `codegenie rag ingest` (the seeding helper; out of this story's scope — Phase 7 onward).
  - `../final-design.md §"Components"` #8 — operator first-fetch ergonomics.
- **Existing code:**
  - `src/codegenie/cli/__init__.py` (S1-06) — `codegenie` `click` group + subcommand-group stubs (`solved-examples`, `models`).
  - `src/codegenie/rag/embeddings/local.py` (S4-01) — `SentenceTransformerProvider` is the digest-verification primitive.
  - `src/codegenie/rag/store.py` (S4-04) — `SolvedExampleStore.read()/write()/prune()`.

## Goal

Wire three `click`-based subcommands (`codegenie models fetch`, `codegenie solved-examples reindex`, `codegenie solved-examples prune --orphans`) against the primitives shipped by S4-01 and S4-04, with two integration tests proving the reindex atomic-swap + the prune-orphans recovery work end-to-end.

## Acceptance criteria

### `codegenie models fetch`

- [ ] `codegenie models fetch [--model <id>] [--digest <sha>] [--cache-dir <path>]` — defaults: `--model bge-small-en-v1.5`, `--digest` from `tools/digests.yaml`, `--cache-dir` from `~/.cache/codegenie/models/`.
- [ ] Idempotent: a second run with the same args is a no-op (verification only, no re-download).
- [ ] Hard-fail on digest mismatch (the verification surface from S4-01) — exit code 11 (config_invalid) per S1-06's exit-code catalog; emits `embedding_model.hash_mismatch` audit event before exit.
- [ ] Honors `HF_HUB_OFFLINE=1` — airgapped operators pre-stage the cache and run the command to verify; the command must NOT attempt a network fetch when offline mode is set.
- [ ] On success: prints `model_id`, `digest`, `cache_path`, `size_mb` to stdout in a single line of canonical JSON (so the runbook can pipe it to `jq`).
- [ ] Exit 0 on success; exit 10 (upstream_unavailable) on HF Hub network failure; exit 11 on digest mismatch.

### `codegenie solved-examples reindex --model-digest <new>`

- [ ] `codegenie solved-examples reindex --model-digest <new> [--from-digest <old>] [--dry-run]` re-embeds every body JSON under `<new>` and atomically swaps the chromadb collection.
- [ ] **Atomic swap procedure:**
  1. Construct `SolvedExampleStore` with current `model_digest=<old>` (auto-detected from store if `--from-digest` absent).
  2. Read all bodies from `.codegenie/rag/bodies/`.
  3. Re-embed each body's `fingerprint_to_embedding_text(...)` under the new provider.
  4. Create a new chromadb collection named `solved_examples_<new_digest_short>`.
  5. Upsert every example into the new collection with `embedding_model_digest=<new>` metadata.
  6. Rename the **old** collection to `solved_examples_<old_digest_short>.quarantined-<ts>` (chromadb supports collection rename; if not, atomic-copy + delete).
  7. Active collection name is updated in store config.
- [ ] **Old `example_id`s remain resolvable in the quarantined collection** — operator can downgrade by passing `--use-collection <quarantined_name>` to a future query (this CLI option lands in S6-04 — this story only ships the quarantine *side* of the contract).
- [ ] `--dry-run` reports counts and the swap plan without writing.
- [ ] Reindex acquires the store's exclusive `flock` for the full duration; the stale-lock-breaker from S4-04 applies.
- [ ] Reindex is **task-class agnostic** — every body, regardless of `task_class`, is re-embedded; metadata `task_class` is preserved verbatim.
- [ ] Reindex emits `solved_examples.reindex_started` + `solved_examples.reindex_completed` audit events with `{from_digest, to_digest, count, duration_s}`.
- [ ] On embedding failure mid-reindex: the new collection is `chroma_collection.delete()`d (no half-built state); the old collection remains the active collection; audit `solved_examples.reindex_aborted` with reason.
- [ ] Exit 0 on success; exit 6 (validation_fail equivalent — repurposed for "reindex failed mid-flight") on partial-failure abort; exit 11 on configuration error.

### `codegenie solved-examples prune --orphans`

- [ ] `codegenie solved-examples prune --orphans [--dry-run]` scans `.codegenie/rag/bodies/*.json`, queries chromadb for known `example_id`s, and removes body JSONs whose ID is not in chromadb.
- [ ] `--dry-run` prints the list of orphan paths and counts without deleting.
- [ ] Acquires the store's exclusive `flock`.
- [ ] Emits `solved_examples.prune_orphans` audit with `{deleted_count, dry_run, paths_truncated_at: 50}`.
- [ ] Exit 0 on success.

### Integration tests

- [ ] `tests/integration/test_solved_examples_reindex.py` — seed store with 5 examples under digest `A`; run `codegenie solved-examples reindex --model-digest B` against a mock `SentenceTransformerProvider(digest="B")`; assert new collection has 5 examples with `embedding_model_digest=B`; old collection renamed to `solved_examples_A.quarantined-<ts>`; original `example_id`s resolvable in the quarantined collection.
- [ ] `tests/integration/test_solved_examples_prune_orphans.py` — write 3 body JSONs; chromadb has rows for 2 of them; run `prune --orphans`; assert the third body is deleted; the other two are retained; chromadb is unchanged.
- [ ] `tests/integration/test_models_fetch_idempotent.py` — first run downloads (or verifies cached) snapshot; second run is a no-op (verification only); on digest tampering (mutate the cached SHA), third run exits 11 with `embedding_model.hash_mismatch` audit.
- [ ] `tests/integration/test_models_fetch_offline_refuses_network.py` — set `HF_HUB_OFFLINE=1`; with the model NOT cached, the command exits non-zero without attempting a network fetch (verified via `monkeypatch` on `huggingface_hub.snapshot_download`).

### Generic

- [ ] All subcommands print structured JSON on stdout for machine consumption; human-readable summaries go to stderr.
- [ ] All subcommands use the `click` group from `src/codegenie/cli/__init__.py`; no new top-level entry points.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli/`, `pytest tests/integration/test_solved_examples_* tests/integration/test_models_fetch_*` all pass.

## Implementation outline

1. Write the failing integration tests first (TDD plan below). The tests use a small `SolvedExample` fixture factory from S4-04's test helpers and a mock embedding provider.
2. Create `src/codegenie/cli/models.py` (the `codegenie models` group module):
   - `@models.command("fetch")` — args + flags above.
   - Calls `huggingface_hub.snapshot_download(repo_id, revision=expected_digest, cache_dir=...)`.
   - Verifies observed snapshot SHA matches expected; on mismatch raise `EmbeddingDigestMismatch`.
   - Honors `HF_HUB_OFFLINE` via env var inheritance.
3. Create `src/codegenie/cli/solved_examples.py`:
   - `@solved_examples.command("reindex")` — `--model-digest`, `--from-digest`, `--dry-run`.
   - Loads `SolvedExampleStore`, iterates bodies, re-embeds, builds new collection, atomically swaps.
   - `@solved_examples.command("prune")` — `--orphans`, `--dry-run`.
4. Add `src/codegenie/cli/_reindex.py` for the actual `reindex_pure(store, new_provider, dry_run) -> ReindexReport` function (testable without `click` wiring).
5. Wire entry points: ensure S1-06's stub `solved-examples` and `models` groups now have the new subcommands attached.
6. Run lint / format / mypy / pytest.

## TDD plan — red / green / refactor

### Red

Path: `tests/integration/test_solved_examples_reindex.py`

```python
from pathlib import Path
from click.testing import CliRunner

from codegenie.cli import cli  # the root click group
from tests.fixtures.rag_helpers import seed_store_with_n_examples, fake_provider


def test_reindex_atomic_swap_preserves_count_and_quarantines_old(tmp_path: Path) -> None:
    """Gap-2 recovery: after the operator bumps the embedding model, reindex
    must re-embed the entire corpus under the new digest and leave the OLD
    collection recoverable. If the old collection is deleted, an aborted
    upgrade is unrecoverable."""
    seed_store_with_n_examples(tmp_path, n=5, digest="A" * 40)

    runner = CliRunner()
    with fake_provider(digest="B" * 40):
        result = runner.invoke(cli, [
            "solved-examples", "reindex",
            "--model-digest", "B" * 40,
            "--from-digest", "A" * 40,
            "--root", str(tmp_path),
        ])
    assert result.exit_code == 0, result.stderr_bytes.decode()

    # New collection has 5 examples under digest B.
    from codegenie.rag.store import SolvedExampleStore
    new_store = SolvedExampleStore(
        root=tmp_path, embed_dims=384, model_digest="B" * 40,
        current_repo_url="https://x",
    )
    assert new_store.count() == 5

    # Old collection is quarantined and still queryable for original example_ids.
    quarantined = list((tmp_path / "solved-examples").glob("*.quarantined-*"))
    assert len(quarantined) == 1
```

Path: `tests/integration/test_solved_examples_prune_orphans.py`

```python
from pathlib import Path
from click.testing import CliRunner
from codegenie.cli import cli
from tests.fixtures.rag_helpers import seed_store_with_n_examples


def test_prune_orphans_removes_body_without_chromadb_row(tmp_path: Path) -> None:
    """Edge case #15: a writeback partial-failure leaves a body on disk
    without a chromadb row. Without prune, the orphan body sits forever
    and confuses `solved-examples list` (S6-04). With prune, the recovery
    is a single command."""
    seed_store_with_n_examples(tmp_path, n=2, digest="A" * 40)
    # Manually plant an orphan body — no chromadb row.
    orphan = tmp_path / "bodies" / "orphan-id.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text('{"id": "orphan-id"}')

    runner = CliRunner()
    result = runner.invoke(cli, [
        "solved-examples", "prune", "--orphans",
        "--root", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert not orphan.exists()
    # Non-orphan bodies survive.
    assert len(list((tmp_path / "bodies").glob("*.json"))) == 2
```

Path: `tests/integration/test_models_fetch_idempotent.py`

```python
from click.testing import CliRunner
from codegenie.cli import cli


def test_models_fetch_idempotent(tmp_path) -> None:
    """First run downloads (cassetted); second run is verification-only.
    Operator runs `models fetch` in CI on every job — the second-run cost
    must be near-zero or the CI canary breaks."""
    runner = CliRunner()
    r1 = runner.invoke(cli, ["models", "fetch", "--cache-dir", str(tmp_path)])
    assert r1.exit_code == 0
    r2 = runner.invoke(cli, ["models", "fetch", "--cache-dir", str(tmp_path)])
    assert r2.exit_code == 0
    # Second run does not re-download (no network call in cassette).


def test_models_fetch_digest_tamper_exits_11(tmp_path, monkeypatch) -> None:
    """ADR-P4-006 first-write protection: tampered cache must NOT silently
    re-certify itself. Hard-fail with exit 11 + loud audit."""
    # Tamper the cached SHA (mutate a byte in the digest record).
    ...
    result = runner.invoke(cli, ["models", "fetch", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 11
    assert "hash_mismatch" in result.stderr_bytes.decode()
```

Commit red. All fail (`AttributeError` on `cli` subcommands).

### Green

- `cli/models.py`: ~80 lines.
- `cli/solved_examples.py`: ~120 lines.
- `cli/_reindex.py`: ~70 lines (pure function; the CLI just glues args).

### Refactor

- Extract `_short_digest(digest: str) -> str` helper (first 8 chars) for collection-name suffixes.
- Add docstrings to each subcommand pointing at the runbook section (S7-06).
- Verify all stdout writes go through `click.echo(... )` so output is testable.
- Add a `--quiet` flag if the runbook needs script-friendly output.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/models.py` | New — `fetch` subcommand |
| `src/codegenie/cli/solved_examples.py` | New — `reindex` + `prune` subcommands |
| `src/codegenie/cli/_reindex.py` | New — pure reindex function (no click) |
| `src/codegenie/cli/__init__.py` | Wire the new subcommand modules into the root group |
| `tests/fixtures/rag_helpers.py` | Add `seed_store_with_n_examples`, `fake_provider` helpers (shared with S4-04's tests) |
| `tests/integration/test_solved_examples_reindex.py` | New |
| `tests/integration/test_solved_examples_prune_orphans.py` | New |
| `tests/integration/test_models_fetch_idempotent.py` | New |
| `tests/integration/test_models_fetch_offline_refuses_network.py` | New |

## Out of scope

- **`codegenie solved-examples list` / `show` / `promote` / `calibrate` / `health`** — these land in S6-04 (the operator CLI surface for Step 6).
- **`codegenie rag ingest --from-phase3-runs`** — the seeding helper from `final-design.md §"CLI surface"`; deferred past Step 4 (it depends on Phase-3 run artifacts being discoverable; runbook concern).
- **`codegenie auth set-anthropic-key` / `auth status`** — S2-05 (Step 2).
- **Editing `tools/digests.yaml` via CLI** — ADR-P4-006 mandates this is an operator-driven ADR amendment, not a CLI subcommand; do not add `--update-digest` despite the temptation.
- **Pre-commit hook for `tools/digests.yaml` first-write protection** — S7-06.
- **Reindex against multiple corpora / cross-host** — Phase 9+.

## Notes for the implementer

- **Three subcommands, three near-orthogonal concerns.** Resist the temptation to share helpers across the boundaries; the only legitimate shared helper is `_short_digest`. `reindex` and `prune` share the store dependency, but their core loops are independent.
- **`HF_HUB_OFFLINE=1` is a real operator workflow.** Airgapped operators stage the model cache out-of-band and run `codegenie models fetch` purely for verification. If the command attempts a network fetch in offline mode, the operator's run hangs on DNS timeout. Test the negative path.
- **The reindex collection-name strategy uses short-digest suffixes.** `solved_examples_<first8chars>` keeps names readable; the quarantine rename appends `.quarantined-<utc_iso>`. Collisions are statistically near-zero on SHA-truncations; if observed, surface as a Phase-5 issue.
- **Reindex is the bottleneck command.** With 1k examples at 28ms warm-embed, full reindex takes ~30s; with 5k, ~140s. Show a progress indicator on stderr (`click.progressbar`) so the operator doesn't think the command hung.
- **Reindex must NOT delete the old collection on success.** ADR-P4-005's recovery story requires the old collection to remain queryable until the operator explicitly removes it. The quarantine rename is enough; a `--purge-quarantined` flag can ship in S6-04 if requested.
- **Prune is `os.remove`, not `shutil.move-to-trash`.** The orphan bodies are recoverable from git or the `<root>.corrupt-<ts>` quarantine path if anyone needed them; `prune` is the explicit, audited cleanup.
- **JSON-on-stdout discipline.** Every subcommand prints one line of canonical JSON on stdout (`{"command":"models.fetch","status":"ok",...}`) so the runbook can pipe to `jq`. Human-readable text goes to stderr (also via `click.echo(..., err=True)`).
- **Exit-code reuse.** Per S1-06's exit-code catalog: 0 = success; 10 = upstream_unavailable; 11 = config_invalid (digest mismatch, malformed YAML); 6 = validation_fail (used here for reindex partial-failure abort). Do not introduce new exit codes in this story; if reindex's failure modes need a dedicated code, surface as a S1-06 amendment.
- **No LLM invocation anywhere in this story.** Every command is deterministic. If you find yourself reaching for `LeafLlmAgent`, you've wandered into the wrong story.
