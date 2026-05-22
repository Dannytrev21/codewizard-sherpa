# Story S4-01 — `Embedder` Protocol + `FastembedEmbedder` + `codegenie embeddings bootstrap`

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (`BlobDigest`, `ModelId`, `EmbeddingVector` newtypes in `codegenie.types.identifiers` — note `EmbeddingVector` is `NewType("EmbeddingVector", tuple)`, S1-01 AC-2), S1-05 (path-scoped fence admits `fastembed`/`onnxruntime` only under `src/codegenie/rag/`; lands `tests/fence/test_pyproject_fence_phase4.py`), S1-06 (import-linter contract mirrors the fence)
**ADRs honored:** ADR-0007 (fastembed ONNX over `sentence_transformers`/`torch`), ADR-0003 (path-scoped fence), ADR-0008 (cross-arch float drift mitigated by Step-5 band — referenced framing only)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 19 — 3 block (fixed in place), 12 harden, 4 nit

Changes applied:
- **AC-3 corrected (block, F1)** — `EmbeddingVector` is `NewType("EmbeddingVector", tuple)` (S1-01 AC-2 deliberately keeps numpy out of `codegenie.types`); the original AC asserted an `np.ndarray` with `dtype np.float32`, which contradicts the dependency and would fail AC-11 `mypy --strict`.
- **AC-6 rewritten (block, F3 + F12)** — added the operator-initiated model-upgrade path (arch edge case #3 makes bootstrap the upgrade mechanism; the original AC reported any change as exit-1 drift, making upgrades impossible); switched the lock hash from a single-file sha256 to a directory digest so a tokenizer-config change is also caught.
- **AC-7 reconciled (block, F4)** — the original AST-fence wording ("no `TextEmbedding(...)` call ... only inside the CLI module") is unsatisfiable: `embedder.py.__init__` legitimately constructs `TextEmbedding` after lock-verification. Reworded to assert call *ordering*, plus a behavioral spy test.
- **AC-2 expanded (harden, F5)** — added the "lock present, weights absent" and "lock present, corrupt" negative-space cases; both must raise typed errors, not a raw `OSError` / `yaml.YAMLError` / `pydantic.ValidationError`.
- **AC-4 corrected (harden, F2)** — ONNX batched inference is not guaranteed bit-identical to singleton inference; "bit-identical" relaxed to a tolerance assertion.
- **AC-8 hardened (harden, F14)** — `EmbeddingModelMismatch` gained a `kind` discriminator (it is raised at two sites with `expected`/`found` carrying different kinds of value).
- **AC-9 hardened (harden, F9)** — Protocol fence now unions `dir()` with `__annotations__`, faithfully mirroring the cited `test_plugin_protocol_frozen.py` precedent (whose docstring warns against `dir()`-only).
- **AC-12 added (harden, F10)** — pins `embed` run-to-run determinism, the load-bearing precondition for S4-02's text-keyed cache.
- **Files-to-touch fixed (harden, F6 + F7)** — CLI is the single module `src/codegenie/cli.py`, not a `cli/` package; added `pyproject.toml` (the `fastembed` marker + the `fastembed.*` mypy override).
- **TDD plan hardened** — the sha256-drift red test now sets up synthetic on-disk weights (F18); idempotence test uses byte-equality + a patched write-seam instead of mtime (F8); added model-name-mismatch, weights-absent, corrupt-lock, determinism, batch-tolerance, empty-batch, and model-upgrade tests.
- **Implementation outline** — `_EmbeddingsModelLock.model_name` typed `ModelId` not raw `str` (F13); `__init__` sequence and `embed`/`embed_batch` tuple-conversion spelled out; CLI deferred-import pattern named (F6).
- Nits: AC-1 "pure" → "idempotent" (F16); runbook filename reconciled with ADR-0007 (F15); `Depends on` corrected to S1-01 (newtypes are S1-01's, not S1-04's — F19).

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-01-fastembed-embedder-bootstrap.md

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
    - `model_digest(self) -> BlobDigest` — idempotent: returns the same value over the lifetime of the instance (it reads frozen instance state set in `__init__` — not side-effect-free in the strict sense, so "idempotent", not "pure").
    No fourth member; no `close()`; no `warmup()`. Fence test (AC-9) asserts the count.
- [ ] **AC-2 — `FastembedEmbedder` lazy init + refuse-start.** `FastembedEmbedder(model_name: ModelId = ModelId("BAAI/bge-small-en-v1.5"), lock_path: Path | None = None, cache_dir: Path | None = None)` — `cache_dir` is the model-weights cache root, defaulting to fastembed's standard location / `$FASTEMBED_CACHE_DIR`, injectable so tests can point the digest check at synthetic on-disk weights. The constructor enumerates **exactly these branches** (all checks run *before* any `fastembed` call):
    - Reads `.codegenie/rag/embeddings_model.lock` (default location; overridable via `lock_path`). The lock is YAML `{model_name: str, sha256: str}` parsed into a frozen `extra="forbid"` Pydantic model.
    - **Lock file missing** → raises `EmbeddingsBootstrapRequired` with `runbook_url = "docs/operations/embeddings.md"` and a diagnostic string mentioning `codegenie embeddings bootstrap` literally.
    - **Lock file present but unparseable** (invalid YAML, unknown key, failed field validation) → raises `EmbeddingsBootstrapRequired` with a "lock file corrupt — re-run `codegenie embeddings bootstrap`" diagnostic. A raw `yaml.YAMLError` / `pydantic.ValidationError` must NOT escape (adapter pattern; Rule 12 — fail loud *and* typed).
    - **Lock present, `model_name` field ≠ ctor `model_name`** → raises `EmbeddingModelMismatch(kind="model_name", expected=<ctor model_name>, found=<lock model_name>)`.
    - **Lock present, on-disk model weights absent** (no model directory under `cache_dir`, or it holds no model files) → raises `EmbeddingsBootstrapRequired` (the operator copied the lock without the weights, or cleared the cache — distinct from the missing-lock case, same remedy).
    - **Lock present, weights present, directory digest of on-disk weights ≠ `lock.sha256`** → raises `EmbeddingModelMismatch(kind="sha256", expected=<lock.sha256>, found=<computed digest>)`.
    - **Lock present + digest matches** → loads `fastembed.TextEmbedding(model_name)` and caches the loaded session on `self._session` (one-time). (validator: hardened — added the corrupt-lock and weights-absent branches, the `kind` discriminator, and the `cache_dir` test seam. F5 + F14 + F18)
- [ ] **AC-3 — `embed` produces a fixed-dim normalized vector.** `EmbeddingVector` is a `NewType` over the **bare `tuple`** (S1-01 AC-2 — numpy is deliberately kept out of `codegenie.types`; shape/dtype validation is *this* story's job). `embed(text="hello world")` returns an `EmbeddingVector` for which: `len(vec) == 384`; every element is a Python `float` (the ONNX `np.float32` array is converted to a `tuple` of Python floats before wrapping, so numpy never leaks past `embedder.py`'s return boundary); the vector is L2-normalized — `abs(_l2_norm(vec) - 1.0) < 1e-3`, where `_l2_norm` is computed over the tuple (`math.sqrt(sum(x * x for x in vec))`). (validator: corrected — original asserted an `np.ndarray` with `dtype np.float32`, which contradicts S1-01 AC-2's `NewType("EmbeddingVector", tuple)` and would fail AC-11 `mypy --strict`. F1)
- [ ] **AC-4 — `embed_batch` is semantically equivalent to repeated `embed`, within tolerance.** For `texts = ["a", "b", "c"]`, `len(embed_batch(texts)) == 3` and each `embed_batch(texts)[i]` matches `embed(texts[i])` **within tolerance** — `cosine(batch[i], single[i]) >= 1 - 1e-6` AND every component pair within `abs ≤ 1e-5`. ONNX batched inference (`session.embed(texts)`, `len > 1`) is **not guaranteed bit-identical** to singleton inference (`session.embed([text])`): different tensor shapes select different kernels / accumulation orders — the same 5th-decimal effect ADR-0008's two-threshold band absorbs (Notes §3). The load-bearing property is that batching is a *perf optimization, never a semantic change*; a tolerance assertion encodes exactly that intent — exact equality would be a flaky/unsatisfiable AC. `embed_batch([])` returns `[]`. (validator: corrected — original demanded "bit-identical", which ONNX batch execution does not promise. F2 + F17)
- [ ] **AC-5 — `model_digest()` is stable + matches the lock.** `embedder.model_digest()` returns `BlobDigest(lock.sha256)` verbatim; two calls return the **same string** (`==`); a freshly constructed second `FastembedEmbedder` against the same lock returns the **same digest**.
- [ ] **AC-6 — `codegenie embeddings bootstrap` CLI: idempotent, writes the lock, supports an explicit model upgrade.** New subcommand wired into the existing `click` group surface (`@cli.group(name="embeddings")` + `@embeddings.command(name="bootstrap")`, mirroring the `vuln-index` precedent in `cli.py`). Behavior:
    - **Download:** triggers `fastembed.TextEmbedding(model_name)` (do NOT roll our own HTTP — fastembed downloads into its cache on first construction); the CLI invokes that path from a module under `src/codegenie/rag/` so the path-scoped fence stays green.
    - **Digest:** computes a **directory digest** — `sha256` folded over every regular file in the resolved model cache directory, in sorted-relative-path order (each file's relative path + bytes). A single-file `sha256(model.onnx)` is **insufficient**: BGE-small's cache also contains `tokenizer.json` / `tokenizer_config.json` / `config.json` / `special_tokens_map.json`, and a tokenizer change silently shifts the vector space — exactly the drift this lock exists to catch (ADR-0007 §Consequences; edge case #3). This directory digest is the value stored as `sha256` in the lock and returned by `model_digest()`.
    - **Write:** writes `.codegenie/rag/embeddings_model.lock` with `{model_name, sha256}` as YAML, sorted keys, trailing newline.
    - **Idempotent re-run (same `--model-name` as the on-disk lock):** recomputes the directory digest; equal to `lock.sha256` → no-op, the lock file is **not** rewritten, log `embeddings.bootstrap.lock_current`, exit 0; differs → exit 1 with a diagnostic naming both digests (genuine drift / corruption — not an upgrade).
    - **Explicit model upgrade (`--model-name` differs from the on-disk lock's `model_name`):** this is the operator-initiated upgrade path of arch edge case #3. Download the new model, recompute the digest, **overwrite** the lock with the new `{model_name, sha256}`, log an `embeddings.bootstrap.model_upgraded` warning that `codegenie rag rebuild` is now required to re-embed the corpus, exit 0. A model upgrade must NOT be reported as "hash drift" (exit 1) — that would make edge case #3's upgrade workflow impossible.
    - Exit code 0 on success (first write / no-op / upgrade); exit code 1 on same-model digest drift or download failure. (validator: rewritten — original had no model-upgrade path, contradicting arch edge case #3, and hashed a single file, missing tokenizer drift. F3 + F12)
- [ ] **AC-7 — Bootstrap is the ONLY runtime weight download path.** Two complementary checks:
    - **Behavioral (primary):** a unit test patches `fastembed.TextEmbedding` with a spy and asserts that constructing `FastembedEmbedder(...)` against a lock + a fully-populated on-disk weights cache **never triggers a network download** — the session is constructed only after the lock + on-disk-digest verification passed, against an already-present cache. The structural reason this holds: `__init__` verifies the on-disk weights directory digest *before* it constructs `TextEmbedding`; if the cache were empty the digest computation would have already raised `EmbeddingsBootstrapRequired` (AC-2), so `TextEmbedding` is only ever reached when the weights are present → fastembed reads from cache, no download.
    - **Structural (`tests/fence/test_no_embedder_download_outside_cli.py`):** AST-walks `src/codegenie/rag/embedder.py` and asserts (a) there is **no module-scope** `TextEmbedding(...)` call (a module-level call would download at import time), and (b) inside `FastembedEmbedder.__init__`, the lock-verification call (`_verify_lock_or_raise`) appears at an earlier statement index than the `TextEmbedding(...)` call. `embedder.py` legitimately constructs `TextEmbedding` inside `__init__` after verification — the fence asserts the *ordering*, not the *absence*, of that call. (validator: corrected — the original wording "asserts no top-level `TextEmbedding(...)` call ... only inside the CLI module" is unsatisfiable: the implementation outline constructs `TextEmbedding` inside `embedder.py.__init__`. F4)
- [ ] **AC-8 — `EmbeddingModelMismatch` + `EmbeddingsBootstrapRequired` typed errors.** `src/codegenie/rag/errors.py` defines:
    - `EmbeddingModelMismatch(Exception)` with typed attributes `kind: Literal["model_name", "sha256"]`, `expected: str`, `found: str`. The `kind` discriminator is load-bearing: `EmbeddingModelMismatch` is raised at **two** sites (lock `model_name` ≠ ctor `model_name`; on-disk directory digest ≠ `lock.sha256`) and `expected`/`found` carry model-name strings in one case and 64-hex digests in the other — without `kind`, neither an operator nor a test can tell which. `__str__` includes `kind`, both values verbatim, and a runbook pointer (`docs/operations/embeddings.md`). Tests assert `exc_info.value.kind` and `exc_info.value.expected` directly, not just `in str(...)`.
    - `EmbeddingsBootstrapRequired(Exception)` with `runbook_url: str`. `__str__` literally contains the substring `"codegenie embeddings bootstrap"`. Raised on three conditions (AC-2): lock file missing; lock file present-but-corrupt; lock present but on-disk weights absent.
    (validator: hardened — added the `kind` discriminator; original overloaded `expected`/`found` across two semantically different raise-sites. F14 + F5)
- [ ] **AC-9 — `Embedder` Protocol surface fence test.** `tests/fence/test_embedder_protocol_frozen.py` asserts (mirroring `tests/fence/test_plugin_protocol_frozen.py` precedent **faithfully**):
    - The public surface is `({n for n in dir(Embedder) if not n.startswith("_")} | {n for n in Embedder.__annotations__ if not n.startswith("_")}) == {"embed", "embed_batch", "model_digest"}`. The precedent unions `dir()` with `__annotations__` because a `typing.Protocol` does not surface attribute-only members through `dir()` alone — copying that idiom keeps the fence correct if a future member is ever added as an attribute rather than a method.
    - `inspect.isfunction(Embedder.embed)` (likewise for `embed_batch`, `model_digest`).
    (validator: hardened — original used `dir()` alone, the exact idiom the cited precedent's docstring warns against. F9)
- [ ] **AC-10 — Path-scoped fence still green.** Re-run `tests/fence/test_pyproject_fence_phase4.py` after this story. `fastembed` and `onnxruntime` appear only in `src/codegenie/rag/embedder.py` (and the CLI module if that module also lives under `src/codegenie/rag/cli.py`); no other module imports either package.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the new modules + tests.
- [ ] **AC-12 — `embed` is deterministic run-to-run.** On a single `FastembedEmbedder` instance, `embed(t) == embed(t)` is **exactly** equal (bit-identical tuples) for the same `t` — singleton ONNX inference against a fixed session and a fixed input shape is deterministic. This is the strong invariant (AC-4's *batch*-vs-singleton comparison is the one that needs tolerance); a non-deterministic `embed` would silently poison S4-02's text-keyed cache. Requires bootstrapped weights — mark `@pytest.mark.fastembed`. (validator: added — no AC pinned `embed` determinism, the load-bearing precondition for the S4-02 cache. F10)

## Implementation outline

1. **Errors first** — `src/codegenie/rag/errors.py`: define `EmbeddingsBootstrapRequired` and `EmbeddingModelMismatch` as documented; both inherit `Exception`; typed attributes set in `__init__`; `__str__` formatted explicitly (do not rely on default `args[0]`).
2. **`Embedder` Protocol** — `src/codegenie/rag/embedder.py`: `from __future__ import annotations`; `@runtime_checkable` Protocol with three method signatures (`...` bodies). Import `EmbeddingVector`, `BlobDigest` from `codegenie.types.identifiers`.
3. **Lock model** — `src/codegenie/rag/embedder.py`: small frozen Pydantic model `_EmbeddingsModelLock(BaseModel, frozen=True, extra="forbid")` with fields `model_name: ModelId`, `sha256: str` (`ModelId` is the S1-01 newtype already carried by `SolvedExample.embedding_model` — use it here too rather than a raw `str`; Pydantic v2 validates it as its `str` base). Helper `_read_lock(path: Path) -> _EmbeddingsModelLock | None` — returns `None` if the file is **missing**; if the file is **present but unparseable** (invalid YAML, unknown key, failed field validation) it raises `EmbeddingsBootstrapRequired` with a "lock file corrupt — re-run `codegenie embeddings bootstrap`" diagnostic (do NOT let a raw `yaml.YAMLError` / `pydantic.ValidationError` escape — adapter pattern, Rule 12 fail-loud-but-typed).
4. **`FastembedEmbedder.__init__`** — accept `model_name: ModelId` (default `ModelId("BAAI/bge-small-en-v1.5")`), `lock_path: Path | None`, and `cache_dir: Path | None` (model-weights cache root; defaults to fastembed's standard location / `$FASTEMBED_CACHE_DIR`; injectable so unit tests can point the digest check at synthetic on-disk weights). Sequence, all *before* any `fastembed` call:
   1. `_read_lock(lock_path)` → `None` (file missing) → raise `EmbeddingsBootstrapRequired`.
   2. `lock.model_name != model_name` → raise `EmbeddingModelMismatch(kind="model_name", expected=model_name, found=lock.model_name)`.
   3. Resolve the model weights **directory** under `cache_dir`. If it does not exist / contains no model files → raise `EmbeddingsBootstrapRequired` (lock present but weights absent).
   4. Compute the directory digest (AC-6 algorithm); `!= lock.sha256` → raise `EmbeddingModelMismatch(kind="sha256", expected=lock.sha256, found=computed)`.
   5. Store `self._model_digest = BlobDigest(lock.sha256)`.
   6. Only now construct `self._session = fastembed.TextEmbedding(model_name)` — weights are proven present + matching, so this reads from cache and never downloads.
   Steps 1–4 are the verification kernel; hoist them into `_verify_lock_or_raise` (see Refactor) so the CLI reuses the exact same logic.
5. **`embed`** — `vec_iter = self._session.embed([text])`; `arr = next(iter(vec_iter)).astype(np.float32)`; L2-normalize defensively (BGE-small ships normalized but guard against future model swaps); **convert to a `tuple` of Python `float`s** — `EmbeddingVector(tuple(float(x) for x in arr))`. numpy is used freely *inside* `embedder.py` (admitted under `src/codegenie/rag/`) but must not leak past the return boundary — `EmbeddingVector` is a `tuple` newtype (S1-01 AC-2). Assert `len == 384` before wrapping.
6. **`embed_batch`** — materialize `self._session.embed(texts)`, cast + normalize + tuple-convert each exactly as `embed` does (factor the per-vector cast/normalize/wrap into a shared `_finalize(arr) -> EmbeddingVector` pure helper so `embed` and `embed_batch` cannot diverge); assert `len(out) == len(texts)`; `embed_batch([])` returns `[]`.
7. **`model_digest`** — returns `self._model_digest` (already a `BlobDigest`).
8. **CLI subcommand** — bootstrap *logic* lives in `src/codegenie/rag/cli.py` (new; the only module that may trigger weight download). The `click` *registration* (`@cli.group(name="embeddings")` + `@embeddings.command(name="bootstrap")`) is added to the existing `src/codegenie/cli.py`; its body does `importlib.import_module("codegenie.rag.cli")` and calls the bootstrap function — exactly the deferred-import pattern `cli.py`'s `vuln-index` subcommand already uses, which keeps both the `cli.py` cold-start import-linter contract AND the path-scoped fence green (a dynamic import is invisible to the AST-walking fence; `cli.py` never statically imports `fastembed`). Implementation:
   - `codegenie embeddings bootstrap [--model-name <name>] [--cache-dir <path>]`; default `--model-name = ModelId("BAAI/bge-small-en-v1.5")`; default `--cache-dir` = fastembed's standard cache root (document the `$FASTEMBED_CACHE_DIR` posture in the docstring + `docs/operations/embeddings.md`).
   - Trigger `fastembed.TextEmbedding(model_name)` (downloads on first construction) → resolve the cached model **directory** → compute the directory digest (AC-6).
   - Read any existing `.codegenie/rag/embeddings_model.lock`; branch per AC-6 (no-op same-digest / exit-1 same-model-drift / overwrite-on-model-upgrade / first-write).
   - The lock-write goes through a module-scope `_seam_write_lock(path, lock)` seam (mirrors `cli.py`'s `_seam_*` convention) so the idempotence test can patch it and assert it is **not** called on the no-op path.
9. **Tests** — `tests/unit/rag/test_embedder.py` covers AC-2 through AC-7 + AC-12. The negative-path fixture writes a synthetic lock YAML **and** a synthetic on-disk weights directory (≥ 2 files so the directory-digest is exercised) under a `tmp_path` `cache_dir` — the sha256-drift and weights-absent branches both need the directory controllably present / absent / mismatched. AC-3/AC-4/AC-12 invoke the real BGE-small via the CI-bootstrapped weight cache — mark `@pytest.mark.fastembed`. **Register the `fastembed` marker** in `pyproject.toml § [tool.pytest.ini_options].markers` (the suite runs under marker discipline; an unregistered marker is a warning at best, a failure under `--strict-markers`). Ensure CI runs `codegenie embeddings bootstrap` once before the marked tests. `tests/fence/test_embedder_protocol_frozen.py` per AC-9. `tests/fence/test_no_embedder_download_outside_cli.py` per AC-7.
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
    vector space. The on-disk weights are PRESENT here (so the directory digest
    can be computed) but do not match the lock — this is the sha256-drift
    branch, distinct from the weights-absent branch (which raises
    EmbeddingsBootstrapRequired). Without the synthetic weights directory this
    test would exercise the wrong branch."""
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    model_dir = cache_dir / "BAAI__bge-small-en-v1.5"  # synthetic, >= 2 files
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"not-the-real-weights")
    (model_dir / "tokenizer.json").write_bytes(b"{}")

    lock = tmp_path / "embeddings_model.lock"
    lock.write_text(
        "model_name: BAAI/bge-small-en-v1.5\n"
        "sha256: 0000000000000000000000000000000000000000000000000000000000000000\n"
    )
    with pytest.raises(EmbeddingModelMismatch) as exc_info:
        FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)
    assert exc_info.value.kind == "sha256"
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

- `test_embed_returns_normalized_384_tuple` (AC-3) — requires bootstrapped weights; `@pytest.mark.fastembed`. Assert `len(vec) == 384`, every element is a `float`, L2-norm ≈ 1.0. **Not** an `np.ndarray` / `dtype` assertion — `EmbeddingVector` is a `tuple` newtype.
- `test_embed_is_deterministic` (AC-12) — `embed(t) == embed(t)` exactly (bit-identical tuples); `@pytest.mark.fastembed`.
- `test_embed_batch_within_tolerance_of_repeated_embed` (AC-4) — for `["a","b","c"]`, `cosine(batch[i], single[i]) >= 1 - 1e-6` and per-component `abs ≤ 1e-5`; **not** bit-equality; `@pytest.mark.fastembed`.
- `test_embed_batch_empty_returns_empty` (AC-4) — `embed_batch([]) == []`.
- `test_model_digest_stable` (AC-5) — two calls return the same string; two embedder instances against the same lock return the same digest.
- `test_embedder_refuses_on_model_name_mismatch` (AC-2) — lock `model_name` ≠ ctor `model_name` → `EmbeddingModelMismatch(kind="model_name")`; assert `kind`, `expected`, `found`.
- `test_embedder_refuses_when_weights_absent` (AC-2) — lock present, no on-disk weights directory under `cache_dir` → `EmbeddingsBootstrapRequired` (NOT `EmbeddingModelMismatch`).
- `test_embedder_refuses_on_corrupt_lock` (AC-2) — lock file present but invalid YAML / unknown key → `EmbeddingsBootstrapRequired` with a "lock corrupt" diagnostic; assert no raw `yaml.YAMLError` / `pydantic.ValidationError` escapes.
- `test_protocol_runtime_checkable` — `isinstance(emb, Embedder) is True`.
- `test_embedder_protocol_surface_frozen` (AC-9) — fence test under `tests/fence/`; uses `dir() | __annotations__`.
- `test_no_download_outside_cli` (AC-7) — AST walk: no module-scope `TextEmbedding(` call in `embedder.py`; inside `__init__`, the `_verify_lock_or_raise` call precedes the `TextEmbedding(` call by statement index.
- `test_runtime_init_never_downloads` (AC-7 behavioral) — patch `fastembed.TextEmbedding` with a spy; construct `FastembedEmbedder` against a populated synthetic cache; assert the spy was reached only with the cache already present (no download).
- `test_bootstrap_cli_writes_lock` — first invocation writes `.codegenie/rag/embeddings_model.lock` with `model_name` + `sha256` YAML keys, sorted, trailing newline.
- `test_bootstrap_cli_idempotent` — calls the CLI twice with the same `--model-name`; second invocation exits 0, logs `embeddings.bootstrap.lock_current`, and **the patched `_seam_write_lock` is not called on the second run** (assert the lock file's bytes are byte-identical before/after — mtime is too coarse to be a reliable no-op signal).
- `test_bootstrap_cli_model_upgrade_rewrites_lock` (AC-6) — lock on disk for model A; run bootstrap with `--model-name` = model B; assert exit 0, the lock now carries model B's `{model_name, sha256}`, and an `embeddings.bootstrap.model_upgraded` warning was logged.
- `test_bootstrap_cli_exits_1_on_same_model_drift` (AC-6) — lock on disk for model A; on-disk weights for model A mutated; re-run bootstrap with `--model-name` = model A; assert exit 1 with a diagnostic naming both digests.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/__init__.py` | Confirmed empty namespace marker (S1-05 lands; this story may also land if not present). |
| `src/codegenie/rag/embedder.py` | `Embedder` Protocol + `FastembedEmbedder` + `_EmbeddingsModelLock` model + `_verify_lock_or_raise` helper. |
| `src/codegenie/rag/errors.py` | `EmbeddingsBootstrapRequired`, `EmbeddingModelMismatch` typed errors (others land in S4-03/S4-04/S4-05). |
| `src/codegenie/rag/cli.py` | `codegenie embeddings bootstrap` subcommand; the **only** module that may trigger weight download. |
| `src/codegenie/cli.py` | Wire the `embeddings` click group + `bootstrap` command; the command body defer-imports `codegenie.rag.cli` (mirrors the existing `vuln-index` subcommand). The CLI is a **single module** — there is no `cli/` package. |
| `pyproject.toml` | Register the `fastembed` pytest marker in `[tool.pytest.ini_options].markers`; add a `[[tool.mypy.overrides]]` block for `fastembed.*` (`ignore_missing_imports = true`) with an explanatory comment matching the existing override convention (`pyarn`, `networkx` rows). |
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

ADR-0003 §Decision: only modules under `src/codegenie/rag/` may import `fastembed`/`onnxruntime`. This story creates `src/codegenie/rag/embedder.py` and `src/codegenie/rag/cli.py` — both qualify. **Do not** add a `fastembed` import to `src/codegenie/cli.py` directly; the click command body must defer-import the bootstrap function from `codegenie.rag.cli` via `importlib.import_module` (the `vuln-index` subcommand is the precedent). This keeps two invariants green at once: the path-scoped fence (a dynamic import is invisible to its AST walk) and `cli.py`'s own cold-start import-linter contract (no heavy top-level imports). Re-run `tests/fence/test_pyproject_fence_phase4.py` before opening the PR.

### §9 — `EmbeddingVector` is a `tuple`, not an `np.ndarray`

S1-01 AC-2 fixes `EmbeddingVector = NewType("EmbeddingVector", tuple)` over the **bare, unparametrized** `tuple` — deliberately, so `codegenie.types.identifiers` stays stdlib-only (numpy never enters the kernel). `fastembed`'s `TextEmbedding.embed()` yields `numpy.ndarray`; that is fine *inside* `embedder.py` (numpy is admitted under `src/codegenie/rag/`), but the value handed back through `embed` / `embed_batch` must be a `tuple` of Python `float`s — `EmbeddingVector(tuple(float(x) for x in arr))`. Two reasons this matters beyond mypy: (a) `mypy --strict` (AC-11) rejects an `np.ndarray` where the `NewType`'s base `tuple` is expected; (b) AC-4's per-element comparison and S4-02's value round-tripping both rely on a plain tuple — `np.ndarray.__eq__` is elementwise and would break a naive `==`.

### §10 — Bootstrap rejects drift but *enables* an upgrade

The refuse-start guard and the bootstrap CLI must not be conflated. The runtime path (`FastembedEmbedder.__init__`) is pure refuse-on-drift — it never writes. The bootstrap CLI is the *only* place the lock is written, and it must distinguish two cases that look superficially alike: (a) **same `model_name`, digest changed** → genuine corruption / tampering → exit 1, do not touch the lock; (b) **`model_name` changed** → an operator deliberately upgrading the model → overwrite the lock, warn that `codegenie rag rebuild` must follow. Arch edge case #3 names `codegenie embeddings bootstrap` as the upgrade mechanism — a CLI that exit-1s on *every* change makes the documented upgrade workflow impossible. The discriminator is the `--model-name` value versus the on-disk lock's `model_name`, nothing else.

### §11 — Runbook filename

This story uses `docs/operations/embeddings.md` for the `runbook_url` in `EmbeddingsBootstrapRequired` / `EmbeddingModelMismatch` and creates the stub there. ADR-0007 §Consequences refers to `docs/operations/bootstrap.md` in passing. Keep `embeddings.md` (it scopes to this component); when S7-10 finalizes the operations docs, reconcile the ADR-0007 reference (a one-line ADR amendment) rather than splitting embeddings guidance across two files.
