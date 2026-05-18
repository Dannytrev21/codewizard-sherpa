# Story S4-01 — `Embedder` Protocol + `FastembedEmbedder` + `codegenie embeddings bootstrap`

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (`SolvedExample`, `Query`, `BlobDigest`, `ModelId`, `EmbeddingVector` Newtypes), S1-05 (path-scoped fence admits `fastembed`/`onnxruntime` only under `src/codegenie/rag/`), S1-06 (import-linter contract mirrors the fence)
**ADRs honored:** ADR-0007 (fastembed ONNX over `sentence_transformers`/`torch`), ADR-0003 (path-scoped fence), ADR-0008 (cross-arch float drift mitigated by Step-5 band — referenced framing only)

## Context

The RAG substrate kernel needs deterministic local-CPU embeddings with **zero network at runtime**, zero `torch`, and a content-addressed weight-bootstrap path so a contributor who fat-fingers a model upgrade halts the worker rather than silently embedding into a different vector space. ADR-0007 picks `fastembed.TextEmbedding("BAAI/bge-small-en-v1.5")` as the only embedding adapter Phase 4 ships, behind an `Embedder` Protocol whose `model_digest() -> BlobDigest` method is the embedding-cache key contract (S4-02 consumes).

This story lands **(a)** the `Embedder` Protocol in `src/codegenie/rag/embedder.py`, **(b)** the single `FastembedEmbedder` adapter wrapping `fastembed.TextEmbedding`, **(c)** a `codegenie embeddings bootstrap` CLI that downloads weights from a content-addressed URL and writes `.codegenie/rag/embeddings_model.lock` (`{model_name, sha256}`), and **(d)** a runtime-`__init__` refuse-start guard that compares the on-disk weight sha256 to the lock and raises `EmbeddingModelMismatch` on drift (edge case #3). S4-02 lands the BLAKE3-keyed embedding cache; this story ships the cache-miss path (`embed` returns a fresh vector). The `embed_batch` method is exposed but minimally implemented (delegate to repeated `embed`) — S4-07's `rag rebuild --reembed` is the first caller that needs the batched path and may refine it.

The `Embedder` Protocol is **acknowledged borderline-premature pluggability** (arch §"Anti-patterns avoided"; ADR-0007 §Pattern fit) — kept because `model_digest()` is the cache-key contract S4-02 depends on, not because a Voyage/Cohere adapter is imminent.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 8 — Embedder + FastembedEmbedder` — public interface (`embed`, `embed_batch`, `model_digest`), 384-dim BGE-small, `~180 MB RSS`, `~500 ms load`, refuse-start on lock-hash drift.
  - `../phase-arch-design.md §Edge case #3` — embeddings model drift on upgrade → refuse-start + `EmbeddingModelMismatch`.
  - `../phase-arch-design.md §"Anti-patterns avoided"` — borderline pluggability framing.
  - `../phase-arch-design.md §Failure modes` — `fastembed` ONNX session load failure → exit at startup; no silent fallback.
- **Phase ADRs:**
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — full decision; weight bootstrap with content-addressed sha256; `EgressGuard` as defense-in-depth.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — `fastembed` / `onnxruntime` admitted **only** under `src/codegenie/rag/`.
- **Source design:**
  - `../final-design.md §Component 8 — FastembedEmbedder` — bootstrap-only weight fetch + refuse-start.
- **Existing code (precedent to mirror):**
  - `src/codegenie/cli/` — CLI subcommand registration pattern (existing `codegenie gather`, `codegenie audit verify` shapes); mirror the `Typer` / `click` choice already in use.
  - `src/codegenie/exec/run_allowlisted.py` — *not* used here directly; the bootstrap reaches over HTTP (the **only** authorized runtime download in Phase 4) and **must be gated behind a CLI subcommand, never invoked from `FastembedEmbedder.__init__`** — the runtime path refuses-start, the operator path bootstraps.
  - `src/codegenie/types/identifiers.py` (S1-01 lands `ModelId`, `BlobDigest`).
  - `src/codegenie/rag/__init__.py` (created by S1-05 as empty namespace marker).

## Goal

Ship `Embedder` Protocol + `FastembedEmbedder` adapter that runtime-refuses to start on `embeddings_model.lock` sha256 drift, plus a `codegenie embeddings bootstrap` CLI that idempotently downloads pinned BGE-small weights and writes the lock; `model_digest()` returns the locked sha256 verbatim so S4-02's cache keys invalidate on model upgrade.

## Acceptance criteria

- [ ] **AC-1 — `Embedder` Protocol declaration.** `src/codegenie/rag/embedder.py` exports `Embedder` as a `@runtime_checkable` `Protocol` with **exactly three** non-dunder member names:
    - `embed(self, text: str) -> EmbeddingVector` — synchronous.
    - `embed_batch(self, texts: list[str]) -> list[EmbeddingVector]` — synchronous; len(returned) == len(texts).
    - `model_digest(self) -> BlobDigest` — pure (returns the same value over the lifetime of the instance).
    No fourth member; no `close()`; no `warmup()`. Fence test (AC-9) asserts the count.
- [ ] **AC-2 — `FastembedEmbedder` lazy init + refuse-start.** `FastembedEmbedder(model_name: str = "BAAI/bge-small-en-v1.5", lock_path: Path | None = None)`:
    - Reads `.codegenie/rag/embeddings_model.lock` (default location; overridable for tests). The lock is YAML `{model_name: str, sha256: str}`.
    - Lock file missing → raises `EmbeddingsBootstrapRequired` with `runbook_url = "docs/operations/embeddings.md"` and a diagnostic string mentioning `codegenie embeddings bootstrap` literally.
    - Lock present but `model_name` field ≠ ctor `model_name` → raises `EmbeddingModelMismatch(expected=<ctor>, found=<lock>)`.
    - Lock present, model file present, sha256 of on-disk weights bytes ≠ `lock.sha256` → raises `EmbeddingModelMismatch(expected=<lock.sha256>, found=<computed>)`.
    - Lock present + sha256 matches → loads `fastembed.TextEmbedding(model_name)` and caches the loaded session on `self._session` (one-time).
- [ ] **AC-3 — `embed` produces a fixed-dim vector.** `embed(text="hello world")` returns an `EmbeddingVector` whose underlying `np.ndarray` has `shape == (384,)` and `dtype == np.float32`. The vector is L2-normalized (cosine ≈ dot product downstream); assert `abs(np.linalg.norm(vec) - 1.0) < 1e-3`.
- [ ] **AC-4 — `embed_batch` returns identical vectors as repeated `embed`.** For `texts = ["a", "b", "c"]`, `embed_batch(texts)[i]` is bit-identical to `embed(texts[i])` for each `i`. (Fastembed batches internally; this property pins that batching is a perf optimization, never a semantic change.)
- [ ] **AC-5 — `model_digest()` is stable + matches the lock.** `embedder.model_digest()` returns `BlobDigest(lock.sha256)` verbatim; two calls return the **same string** (`==`); a freshly constructed second `FastembedEmbedder` against the same lock returns the **same digest**.
- [ ] **AC-6 — `codegenie embeddings bootstrap` CLI is idempotent + writes the lock.** New subcommand wired into the existing CLI entry-point. First invocation:
    - Fetches the model weights archive from `BAAI/bge-small-en-v1.5` via `fastembed`'s own download path (do NOT roll our own HTTP — `fastembed.TextEmbedding(model_name)` will download into its cache on first construction; the CLI invokes that path explicitly and records the result).
    - Computes `sha256(open(weights_path, 'rb').read())`.
    - Writes `.codegenie/rag/embeddings_model.lock` with `{model_name, sha256}` as YAML, sorted keys, trailing newline.
    - Second invocation with the lock already on disk: computes sha256 of the on-disk weights, compares to lock; if equal → no-op + log "lock current"; if not equal → exit code 1 with diagnostic naming both digests.
    - Exit code 0 on success; exit code 1 on hash drift or download failure.
- [ ] **AC-7 — Bootstrap is the ONLY runtime weight download path.** A unit test patches `fastembed.TextEmbedding` and asserts: constructing `FastembedEmbedder(...)` from the runtime path **never** triggers the model download (only the lock-check + session load). The CLI subcommand is the only callsite that may trigger download. `tests/fence/test_no_embedder_download_outside_cli.py` AST-walks `src/codegenie/rag/embedder.py` and asserts no top-level `TextEmbedding(...)` call with download side effects — only inside the CLI module.
- [ ] **AC-8 — `EmbeddingModelMismatch` + `EmbeddingsBootstrapRequired` typed errors.** `src/codegenie/rag/errors.py` defines:
    - `EmbeddingModelMismatch(Exception)` with typed attributes `expected: str`, `found: str`; `__str__` includes both verbatim and a runbook pointer (`docs/operations/embeddings.md`). Tests assert `exc_info.value.expected == "<digest>"` directly, not just `in str(...)`.
    - `EmbeddingsBootstrapRequired(Exception)` with `runbook_url: str`. `__str__` literally contains the substring `"codegenie embeddings bootstrap"`.
- [ ] **AC-9 — `Embedder` Protocol surface fence test.** `tests/fence/test_embedder_protocol_frozen.py` asserts (mirroring `tests/fence/test_plugin_protocol_frozen.py` precedent):
    - `{n for n in dir(Embedder) if not n.startswith("_")} == {"embed", "embed_batch", "model_digest"}`.
    - `inspect.isfunction(Embedder.embed)` (likewise for `embed_batch`, `model_digest`).
- [ ] **AC-10 — Path-scoped fence still green.** Re-run `tests/fence/test_pyproject_fence_phase4.py` after this story. `fastembed` and `onnxruntime` appear only in `src/codegenie/rag/embedder.py` (and the CLI module if that module also lives under `src/codegenie/rag/cli.py`); no other module imports either package.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the new modules + tests.

## Implementation outline

1. **Errors first** — `src/codegenie/rag/errors.py`: define `EmbeddingsBootstrapRequired` and `EmbeddingModelMismatch` as documented; both inherit `Exception`; typed attributes set in `__init__`; `__str__` formatted explicitly (do not rely on default `args[0]`).
2. **`Embedder` Protocol** — `src/codegenie/rag/embedder.py`: `from __future__ import annotations`; `@runtime_checkable` Protocol with three method signatures (`...` bodies). Import `EmbeddingVector`, `BlobDigest` from `codegenie.types.identifiers`.
3. **Lock model** — `src/codegenie/rag/embedder.py`: small frozen Pydantic model `_EmbeddingsModelLock(BaseModel, frozen=True, extra="forbid")` with fields `model_name: str`, `sha256: str`. Helper `_read_lock(path: Path) -> _EmbeddingsModelLock | None` (returns `None` if file missing; otherwise YAML-parses + validates).
4. **`FastembedEmbedder.__init__`** — accept `model_name` and `lock_path`. Call `_read_lock(lock_path)`. If `None` → raise `EmbeddingsBootstrapRequired`. If `lock.model_name != model_name` → raise `EmbeddingModelMismatch`. Resolve `weights_path` from `fastembed`'s cache (its known on-disk location); compute sha256; compare; mismatch → raise. Store `self._model_digest = BlobDigest(lock.sha256)`. Construct `self._session = fastembed.TextEmbedding(model_name)` only after all checks pass. **Do NOT** call any `fastembed` API that triggers download from `__init__` — the lock-check happens before session construction; if `fastembed` would download because the on-disk cache is empty, that is a bootstrap-skipped error and the lock-check must have already failed (no weights → no sha256 to match → `EmbeddingsBootstrapRequired`).
5. **`embed`** — `vec_iter = self._session.embed([text])`; `vec = next(iter(vec_iter)).astype(np.float32)`; L2-normalize defensively (BGE-small ships normalized but guard against future model swaps); return `EmbeddingVector(vec)`.
6. **`embed_batch`** — `[*self._session.embed(texts)]` materialized, each cast + normalized; assert `len(out) == len(texts)`.
7. **`model_digest`** — returns `self._model_digest` (already a `BlobDigest`).
8. **CLI subcommand** — under `src/codegenie/rag/cli.py` (new) and wired into the existing CLI entry-point. `codegenie embeddings bootstrap [--model-name <name>] [--cache-dir <path>]`. Implementation:
   - Default `--model-name = "BAAI/bge-small-en-v1.5"`.
   - Default `--cache-dir = .codegenie/rag/` resolved relative to cwd.
   - Trigger the `fastembed.TextEmbedding(model_name)` constructor in a **module under `src/codegenie/rag/`** so the path-scoped fence remains green. The constructor's first-time-call downloads weights into fastembed's known cache path.
   - Resolve the cached weights path (fastembed exposes this) → read bytes → sha256.
   - Write `.codegenie/rag/embeddings_model.lock` YAML.
   - Idempotent re-runs: read existing lock first; if sha256 matches recomputed value → log "lock current" + exit 0; else exit 1 with diagnostic.
9. **Tests** — `tests/unit/rag/test_embedder.py` covers AC-2 through AC-7 (use a fixture that writes a synthetic lock YAML pointing at a deterministic on-disk fake weights file for the negative paths; AC-3/AC-4/AC-5 invoke the real BGE-small via the CI-bootstrapped weight cache — flag the test with `pytest.mark.fastembed` and ensure CI runs bootstrap once). `tests/fence/test_embedder_protocol_frozen.py` per AC-9. `tests/fence/test_no_embedder_download_outside_cli.py` per AC-7.
10. **Operations doc stub** — `docs/operations/embeddings.md` (skeleton only; S7-10 fills in full content): one paragraph naming bootstrap, lock format, and what `EmbeddingModelMismatch` means.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_embedder.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.errors import EmbeddingModelMismatch, EmbeddingsBootstrapRequired


def test_fastembed_embedder_refuses_to_start_when_lock_missing(tmp_path: Path) -> None:
    """ADR-0007 §Decision: runtime path refuses-start on bootstrap absence.
    Catches the "silent-fallback-to-untracked-weights" failure mode."""
    from codegenie.rag.embedder import FastembedEmbedder

    with pytest.raises(EmbeddingsBootstrapRequired) as exc_info:
        FastembedEmbedder(lock_path=tmp_path / "embeddings_model.lock")  # absent

    assert "codegenie embeddings bootstrap" in str(exc_info.value)
    assert exc_info.value.runbook_url == "docs/operations/embeddings.md"


def test_fastembed_embedder_refuses_to_start_on_sha256_drift(tmp_path: Path) -> None:
    """ADR-0007 §Decision + edge case #3: a contributor who fat-fingers a model
    upgrade halts the worker rather than silently embedding into a different
    vector space."""
    from codegenie.rag.embedder import FastembedEmbedder

    lock = tmp_path / "embeddings_model.lock"
    lock.write_text(
        "model_name: BAAI/bge-small-en-v1.5\n"
        "sha256: 0000000000000000000000000000000000000000000000000000000000000000\n"
    )
    with pytest.raises(EmbeddingModelMismatch) as exc_info:
        FastembedEmbedder(lock_path=lock)
    assert exc_info.value.expected == (
        "0000000000000000000000000000000000000000000000000000000000000000"
    )
    assert exc_info.value.found != exc_info.value.expected
```

Why it fails: `codegenie.rag.embedder`, `codegenie.rag.errors` don't exist yet — `ImportError` on the first line.

### Green — make it pass

Land `errors.py`, `embedder.py` per the implementation outline. The minimum: typed errors, lock-file parsing, sha256 comparison, raise. No `fastembed` import needed to pass the red tests — those paths fail before session construction.

### Refactor

- Hoist the sha256 comparison + `EmbeddingModelMismatch` raise into a small `_verify_lock_or_raise(lock_path, weights_path) -> BlobDigest` pure helper so the CLI's idempotent re-run path reuses it.
- Add module docstring citing ADR-0007 and naming the fence test.
- Pin `from fastembed import TextEmbedding` import to module level (only one import statement; admitted by ADR-0003 path-scoping).

### Required follow-on tests

- `test_embed_returns_normalized_384_vector` (AC-3) — requires bootstrapped weights; mark `@pytest.mark.fastembed` so it skips when bootstrap hasn't run locally; CI runs bootstrap once.
- `test_embed_batch_identical_to_repeated_embed` (AC-4).
- `test_model_digest_stable` (AC-5) — two calls return same; two embedder instances against the same lock return same.
- `test_protocol_runtime_checkable` — `isinstance(emb, Embedder) is True`.
- `test_embedder_protocol_surface_frozen` (AC-9) — fence test under `tests/fence/`.
- `test_no_download_outside_cli` (AC-7) — AST walk: no `TextEmbedding(` call appears in `embedder.py`'s module-level scope or inside `__init__` before the lock-check; the only `TextEmbedding(model_name)` call after lock-verify is allowed.
- `test_bootstrap_cli_idempotent` — calls the CLI twice; second invocation exits 0 with "lock current"; lock-file mtime unchanged on the second run (no-op).
- `test_bootstrap_cli_writes_lock` — first invocation writes `.codegenie/rag/embeddings_model.lock` with `model_name` + `sha256` YAML keys.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/__init__.py` | Confirmed empty namespace marker (S1-05 lands; this story may also land if not present). |
| `src/codegenie/rag/embedder.py` | `Embedder` Protocol + `FastembedEmbedder` + `_EmbeddingsModelLock` model + `_verify_lock_or_raise` helper. |
| `src/codegenie/rag/errors.py` | `EmbeddingsBootstrapRequired`, `EmbeddingModelMismatch` typed errors (others land in S4-03/S4-04/S4-05). |
| `src/codegenie/rag/cli.py` | `codegenie embeddings bootstrap` subcommand; the **only** module that may trigger weight download. |
| `src/codegenie/cli/__init__.py` (or equivalent existing CLI entry) | Wire the `embeddings` subcommand group (existing patterns). |
| `tests/unit/rag/__init__.py` | Test package marker. |
| `tests/unit/rag/test_embedder.py` | Red test + AC follow-ons. |
| `tests/unit/rag/test_embeddings_bootstrap_cli.py` | CLI idempotence + lock-write tests. |
| `tests/fence/test_embedder_protocol_frozen.py` | AC-9 surface freeze. |
| `tests/fence/test_no_embedder_download_outside_cli.py` | AC-7 AST walk. |
| `docs/operations/embeddings.md` | Stub runbook (S7-10 finalizes). |

## Out of scope

- **Embedding cache (`.codegenie/rag/embeddings.cache.sqlite`)** — S4-02 owns the BLAKE3-keyed cache-aside layer. This story's `embed()` is the cache-miss path; S4-02 wraps it.
- **`SolvedExampleStore` / chromadb** — S4-03.
- **`RecordProvenance.verify`** — S4-05.
- **`SolvedExampleRetriever`** — S5-01 (composes this embedder + S4-03 store).
- **Voyage / Cohere / second `Embedder` adapter** — Phase 6.5 calibration may motivate; not Phase 4's call.
- **Cross-arch determinism test** — Phase 6.5 owns; Phase-4 CI is x86_64 only per ADR-0007.
- **`embed_batch` perf optimization** — the Protocol-level method signature is what S4-07 needs; further batching tuning lives there.

## Notes for the implementer

### §1 — `EgressGuard` is defense-in-depth, not the primary control

ADR-0007 names the runtime refuse-start as the primary control; `EgressGuard` (Step 3) is belt-to-suspenders. This story does **not** need `EgressGuard` to be in place to ship — the refuse-start path closes the failure mode on its own. If `EgressGuard` happens to be wired earlier, weights-download attempts from the runtime would also raise `EgressViolation` (correct).

### §2 — Why `model_digest()` is a Protocol method, not a function

`Embedder` is acknowledged borderline-premature pluggability (ADR-0007 §Pattern fit). The justification for keeping it a Protocol is **specifically** that S4-02's cache key includes `model_digest()` as a column; without the Protocol method, every cache lookup would hardcode `"fastembed"` — the wrong coupling. If a reviewer asks "why is this a Protocol when there's only one adapter?", the one-line answer is "cache-key contract; S4-02 reads it."

### §3 — Cross-architecture float drift at the 5th decimal

ONNX float outputs may differ at the 5th decimal between x86_64 and arm64 (ADR-0007 §Context). The mitigation is **the two-threshold band in Step 5**, not point-tightening here. Do not hash embeddings as cache keys (S4-02 hashes input text + model digest); cosine at the 0.65 / 0.85 floors is robust to 5th-decimal drift. Phase 6.5's bench harness owns the cross-arch test.

### §4 — Bootstrap is operator-initiated, not auto-on-`__init__`

The temptation is to make `FastembedEmbedder.__init__` "helpful" by auto-running bootstrap when the lock is missing. **Do not.** ADR-0007 §Decision is explicit: bootstrap is offline-only, operator-initiated. The `EmbeddingsBootstrapRequired` diagnostic with the literal CLI command in the message is the UX commitment. Auto-running bootstrap from a runtime path defeats the supply-chain control and would also bypass `EgressGuard` once it's installed.

### §5 — `fastembed`'s on-disk cache layout

`fastembed.TextEmbedding` caches model weights under `~/.cache/fastembed/` (or `FASTEMBED_CACHE_DIR` if set). Resolve the on-disk weights path from `fastembed`'s known cache directory; if `fastembed` doesn't expose a clean accessor, the bootstrap CLI sets `FASTEMBED_CACHE_DIR=.codegenie/rag/fastembed-cache/` and reads from the deterministic location. Document the env-var posture in the bootstrap CLI docstring + `docs/operations/embeddings.md`.

### §6 — `_FastembedSessionProtocol` if mypy complains

`fastembed` does not ship type stubs as of writing. If `mypy --strict` complains, add a `[tool.mypy.overrides] module = "fastembed.*" ignore_missing_imports = true` entry to `pyproject.toml` — the **only** acceptable per-module relaxation per `CLAUDE.md`. Do not `# type: ignore` inside the source.

### §7 — The Protocol's `embed` is synchronous

Phase 4's RAG path is synchronous-feeling (one in-process retrieval per planning call); making `embed` `async` adds yield-points for zero capability gain. Keep `embed`/`embed_batch` sync. If a future phase needs async, an ADR amendment is the path — and the existing sync method can wrap in `asyncio.to_thread` at the callsite (e.g., the retriever in S5-01).

### §8 — Path-scoped fence is the structural enforcement

ADR-0003 §Decision: only modules under `src/codegenie/rag/` may import `fastembed`/`onnxruntime`. This story creates `src/codegenie/rag/embedder.py` and `src/codegenie/rag/cli.py` — both qualify. **Do not** add a top-level CLI command in `src/codegenie/cli/__init__.py` that imports `fastembed` directly; the CLI entry-point should defer-import the bootstrap function from `codegenie.rag.cli` so the fence catches any accidental boundary breach. Re-run `tests/fence/test_pyproject_fence_phase4.py` before opening the PR.
