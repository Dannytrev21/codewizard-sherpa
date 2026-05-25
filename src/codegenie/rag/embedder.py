"""Phase-4 S4-01 — :class:`Embedder` Protocol + :class:`FastembedEmbedder`.

The embedder substrate is the RAG kernel's cache-key contract: every
embedding read/written by :class:`codegenie.rag.SolvedExampleRetriever`
(S5-01) and the BLAKE3-keyed cache (S4-02) is tied to a
:func:`Embedder.model_digest` returned by this module.

Discipline notes (re-stated from ADR-0007 and the S4-01 story):

- **Refuse-start, never silent-fallback.** ``FastembedEmbedder.__init__``
  verifies the ``.codegenie/rag/embeddings_model.lock`` file *before*
  it constructs any ``fastembed.TextEmbedding`` session. Lock missing
  / corrupt / weights absent / digest mismatch all raise typed errors
  from :mod:`codegenie.rag.errors`. A raw ``yaml.YAMLError`` or
  ``pydantic.ValidationError`` is **never** allowed to escape past the
  adapter boundary (Rule 12 — fail loud *and* typed).

- **Bootstrap is operator-initiated.** The only module authorized to
  trigger a weights download is :mod:`codegenie.rag.cli`. This module's
  ``__init__`` reaches ``fastembed.TextEmbedding`` only *after* the
  on-disk weights directory digest matches ``lock.sha256`` — at that
  point fastembed reads from cache and never downloads.

- **Path-scoped fence.** This module imports ``fastembed`` (and,
  transitively, ``onnxruntime``); ADR-0003 admits both only under
  ``src/codegenie/rag/``. The fence test
  ``tests/fence/test_pyproject_fence_phase4.py`` enforces this.

- **No ``np.ndarray`` past the return boundary.**
  :class:`codegenie.types.identifiers.EmbeddingVector` is a
  ``NewType`` over the bare ``tuple`` (S1-01 AC-2). numpy is used
  freely *inside* this module but the value handed back through
  :meth:`embed` / :meth:`embed_batch` is a ``tuple[float, ...]``.

The companion fence ``tests/fence/test_no_embedder_download_outside_cli.py``
walks this module's AST to assert that (a) there is **no module-scope**
``TextEmbedding(...)`` call and (b) inside ``FastembedEmbedder.__init__``
the lock-verification helper is invoked *before* ``TextEmbedding(...)``.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

import fastembed
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.rag.errors import (
    EmbeddingModelMismatch,
    EmbeddingsBootstrapRequired,
)
from codegenie.types.identifiers import BlobDigest, EmbeddingVector, ModelId

if TYPE_CHECKING:  # pragma: no cover — typing-only import
    import numpy as np

_DEFAULT_MODEL_NAME: Final[ModelId] = ModelId("BAAI/bge-small-en-v1.5")
_DEFAULT_LOCK_PATH: Final[Path] = Path(".codegenie/rag/embeddings_model.lock")
_EXPECTED_DIM: Final[int] = 384
_L2_NORM_TOLERANCE: Final[float] = 1e-3


# ---------------------------------------------------------------------------
# Embedder Protocol — the cache-key contract S4-02 reads (ADR-0007)
# ---------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Synchronous text-to-vector embedder. Three members, exactly.

    The Protocol is acknowledged borderline-premature pluggability — kept
    because :meth:`model_digest` is the cache-key contract S4-02 reads;
    without it every cache lookup would hardcode the adapter's name.

    Method semantics:

    - :meth:`embed` returns a single :class:`EmbeddingVector` for a
      single string. Run-to-run deterministic on a single instance
      (AC-12); a non-deterministic ``embed`` would poison the S4-02
      cache.
    - :meth:`embed_batch` is a perf optimization, not a semantic change:
      ``embed_batch([t]) ≈ [embed(t)]`` within ``cos ≥ 1 - 1e-6`` /
      per-component ``abs ≤ 1e-5`` (ONNX kernel-dispatch nondeterminism
      at the 5th decimal — ADR-0008 absorbs).
    - :meth:`model_digest` is idempotent — the same ``BlobDigest`` over
      the lifetime of the instance and across instances pointing at the
      same lock.
    """

    def embed(self, text: str) -> EmbeddingVector: ...
    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]: ...
    def model_digest(self) -> BlobDigest: ...


# ---------------------------------------------------------------------------
# Lock — frozen pydantic model with the on-disk YAML shape
# ---------------------------------------------------------------------------


class _EmbeddingsModelLock(BaseModel):
    """Frozen, ``extra='forbid'`` Pydantic shape for
    ``.codegenie/rag/embeddings_model.lock``. Forbidding extras means an
    unknown YAML key surfaces as :class:`ValidationError`, which the
    adapter remaps to :class:`EmbeddingsBootstrapRequired` rather than
    letting raw Pydantic exceptions escape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_name: ModelId
    sha256: str


# ---------------------------------------------------------------------------
# Pure helpers — functional core
# ---------------------------------------------------------------------------


def _read_lock(lock_path: Path) -> _EmbeddingsModelLock | None:
    """Read and validate the on-disk lock.

    Returns
    -------
    ``None`` if ``lock_path`` does not exist.

    Raises
    ------
    EmbeddingsBootstrapRequired
        If the file exists but is unparseable YAML or fails Pydantic
        validation (including unknown-key rejection via
        ``extra='forbid'``). Raw ``yaml.YAMLError`` /
        ``pydantic.ValidationError`` is NOT allowed to escape past
        this adapter (Rule 12).
    """
    if not lock_path.is_file():
        return None
    try:
        raw = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EmbeddingsBootstrapRequired(
            reason=f"lock file corrupt at {lock_path} ({exc.__class__.__name__})"
        ) from exc
    if not isinstance(raw, dict):
        raise EmbeddingsBootstrapRequired(
            reason=f"lock file corrupt at {lock_path} (expected mapping)"
        )
    try:
        return _EmbeddingsModelLock.model_validate(raw)
    except ValidationError as exc:
        raise EmbeddingsBootstrapRequired(
            reason=f"lock file corrupt at {lock_path} ({exc.error_count()} validation errors)"
        ) from exc


def _compute_dir_digest(root: Path) -> str:
    """AC-6 directory-digest algorithm.

    ``sha256`` fold over every regular file in ``root``, sorted by
    relative POSIX path. Each file contributes:

    ``rel_path_bytes  +  b"\\0"  +  file_bytes  +  b"\\0"``

    The trailing null separator after the body prevents an
    adjacent-file ambiguity (without it,
    ``("a", b"x") + ("b", b"")`` and ``("a", b"") + ("xb", b"")``
    could be indistinguishable on certain pathologies — the separator
    closes that hole). The leading rel_path means a tokenizer-config
    swap (same bytes under a different filename) drifts the digest.
    """
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _weights_present(cache_dir: Path) -> bool:
    """True iff ``cache_dir`` contains at least one regular file."""
    if not cache_dir.is_dir():
        return False
    return any(p.is_file() for p in cache_dir.rglob("*"))


def _verify_lock_or_raise(
    *,
    model_name: ModelId,
    lock_path: Path,
    cache_dir: Path,
) -> BlobDigest:
    """Verification kernel reused by the runtime path AND the bootstrap
    CLI's idempotent re-run path. Pure: reads files, raises typed errors,
    returns the verified digest. No side effects beyond filesystem reads.

    Branch order (load-bearing — every branch is exercised by a unit
    test):

    1. Lock missing → :class:`EmbeddingsBootstrapRequired`.
    2. Lock corrupt → :class:`EmbeddingsBootstrapRequired` (via
       :func:`_read_lock`).
    3. ``lock.model_name != model_name`` →
       :class:`EmbeddingModelMismatch` with ``kind='model_name'``.
    4. On-disk weights absent → :class:`EmbeddingsBootstrapRequired`.
    5. Weight digest != ``lock.sha256`` →
       :class:`EmbeddingModelMismatch` with ``kind='sha256'``.
    6. All checks pass → return ``BlobDigest(lock.sha256)``.
    """
    lock = _read_lock(lock_path)
    if lock is None:
        raise EmbeddingsBootstrapRequired(reason=f"lock file missing at {lock_path}")
    if lock.model_name != model_name:
        raise EmbeddingModelMismatch(
            kind="model_name",
            expected=str(model_name),
            found=str(lock.model_name),
        )
    if not _weights_present(cache_dir):
        raise EmbeddingsBootstrapRequired(reason=f"on-disk weights absent at {cache_dir}")
    computed = _compute_dir_digest(cache_dir)
    if computed != lock.sha256:
        raise EmbeddingModelMismatch(kind="sha256", expected=lock.sha256, found=computed)
    return BlobDigest(lock.sha256)


def _finalize(arr: np.ndarray) -> EmbeddingVector:
    """Shape + dtype + L2-norm normalize + tuple-conversion.

    Factored so :meth:`FastembedEmbedder.embed` and
    :meth:`FastembedEmbedder.embed_batch` cannot diverge on the
    return-boundary contract (every element a Python ``float``, shape
    ``(384,)``, L2-norm ≈ 1.0).
    """
    import numpy as np  # noqa: PLC0415 — admitted under src/codegenie/rag/

    if arr.shape != (_EXPECTED_DIM,):
        raise RuntimeError(
            f"embedder produced wrong shape: expected ({_EXPECTED_DIM},) got {arr.shape}"
        )
    f32 = arr.astype(np.float32, copy=False)
    norm = float(np.linalg.norm(f32))
    if norm <= 0.0 or not math.isfinite(norm):
        raise RuntimeError(f"embedder produced unnormalizable vector (norm={norm})")
    # Defensive normalize — BGE-small ships normalized but a future model
    # swap might not. Keep this here rather than at __init__ time so the
    # shell stays robust to model identity.
    if abs(norm - 1.0) > _L2_NORM_TOLERANCE:
        f32 = f32 / norm
    return EmbeddingVector(tuple(float(x) for x in f32))


# ---------------------------------------------------------------------------
# FastembedEmbedder — the imperative shell
# ---------------------------------------------------------------------------


class FastembedEmbedder:
    """Concrete :class:`Embedder` adapter wrapping
    ``fastembed.TextEmbedding`` (ADR-0007). One adapter, one model
    family — Voyage/Cohere stay out of Phase 4.

    All ``__init__`` paths verify the on-disk lock and weight digest
    *before* constructing the fastembed session, so the runtime path
    is provably zero-network: if weights were missing,
    :func:`_verify_lock_or_raise` would already have raised.
    """

    __slots__ = ("_model_digest", "_model_name", "_session")

    _model_digest: BlobDigest
    _model_name: ModelId
    _session: object  # ``fastembed.TextEmbedding`` — typed in TYPE_CHECKING block

    def __init__(
        self,
        model_name: ModelId = _DEFAULT_MODEL_NAME,
        lock_path: Path | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        resolved_lock = lock_path if lock_path is not None else _DEFAULT_LOCK_PATH
        resolved_cache = self._resolve_cache_dir(cache_dir)
        self._model_digest = _verify_lock_or_raise(
            model_name=model_name,
            lock_path=resolved_lock,
            cache_dir=resolved_cache,
        )
        self._model_name = model_name
        # Verification has passed: weights are present and match. Loading
        # via fastembed therefore reads from cache and does NOT download
        # — AC-7's structural reason the refuse-start posture holds.
        # Direct import (admitted under src/codegenie/rag/ by ADR-0003)
        # so static analysis sees the fastembed dependency honestly.
        self._session = fastembed.TextEmbedding(model_name, cache_dir=str(resolved_cache))

    @staticmethod
    def _resolve_cache_dir(cache_dir: Path | None) -> Path:
        """Resolve the model-weights cache root.

        - If ``cache_dir`` is provided (tests + explicit ops), honor it.
        - Else read ``FASTEMBED_CACHE_DIR`` from the environment.
        - Else fall back to ``.codegenie/rag/fastembed-cache`` under
          the current working directory — this is the deterministic
          default the operator runbook documents.
        """
        if cache_dir is not None:
            return cache_dir
        env = os.environ.get("FASTEMBED_CACHE_DIR")
        if env:
            return Path(env)
        return Path.cwd() / ".codegenie" / "rag" / "fastembed-cache"

    def embed(self, text: str) -> EmbeddingVector:
        """Synchronous single-string embed."""
        import numpy as np  # noqa: PLC0415 — admitted under src/codegenie/rag/

        vec_iter = self._session.embed([text])  # type: ignore[attr-defined]
        first = next(iter(vec_iter))
        return _finalize(np.asarray(first))

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        """Synchronous batched embed. ``embed_batch([]) == []``.

        Semantic equivalence with :meth:`embed` is within tolerance
        (AC-4) — ONNX batch kernels can differ from singleton kernels
        at the 5th decimal.
        """
        if not texts:
            return []
        import numpy as np  # noqa: PLC0415 — admitted under src/codegenie/rag/

        vec_iter = self._session.embed(texts)  # type: ignore[attr-defined]
        out = [_finalize(np.asarray(v)) for v in vec_iter]
        if len(out) != len(texts):
            raise RuntimeError(f"embedder returned {len(out)} vectors for {len(texts)} texts")
        return out

    def model_digest(self) -> BlobDigest:
        return self._model_digest


__all__ = (
    "Embedder",
    "FastembedEmbedder",
    "_compute_dir_digest",
    "_verify_lock_or_raise",
)
