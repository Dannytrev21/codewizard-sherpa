"""S3-05 — Bundle cache: ``compose_bundle_cache_key`` + ``BundleCacheStore``.

This module is the on-disk Bundle cache. Two surfaces:

1. :func:`compose_bundle_cache_key` — pure BLAKE3 composer over an
   eight-input declared-order payload. ``vuln_index_digest`` is the
   load-bearing input (ADR-0008 §Decision): a CVE-feed refresh that
   re-classifies a CVE MUST NOT return a stale Bundle cache hit. All
   hashing routes through :func:`codegenie.hashing.content_hash_bytes`
   (ADR-0001 chokepoint — no direct ``blake3`` import here; an AST test
   in ``tests/unit/plugins/test_cache_no_blake3_import.py`` fences it).
2. :class:`BundleCacheStore` — content-addressed put/get for
   :class:`~codegenie.plugins.bundle.Bundle` values. Atomic writes via
   ``<dest>.tmp + fsync + os.replace`` (Phase-0 ``cache/store.py``
   precedent); ``0o600`` files, ``0o700`` dir; no ``flock`` on blobs
   (content-addressed — two writers of the same key write identical
   bytes). Path-traversal defence: ``put`` / ``get`` reject any key not
   matching ``^blake3:[0-9a-f]{64}$``.

This story is the **Gap 4 fix** from
``docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md
§Gap analysis #4`` — the synthesis named "GC after 7 days mtime" but
no component owned the mechanism. See sibling module
:mod:`codegenie.plugins.cache_gc` for the eviction loop.

Canonical-caller form for ``args_canonical`` is the same byte-stable
JSON the S3-04 ``_canonicalize_args`` helper produces — ``json.dumps(
args, sort_keys=True, separators=(',', ':'), ensure_ascii=False)``.
The composer is **opaque** to ``args_canonical``: two semantically-
equivalent JSON strings differing only in whitespace produce
DIFFERENT keys (the caller owns canonicalisation).

ADRs honoured:

- Phase-3 ADR-0008 §Decision — ``vuln_index.digest`` MUST participate
  in the Bundle cache key.
- Phase-0 ADR-0001 — BLAKE3 chokepoint at :mod:`codegenie.hashing`.
- Phase-0 ADR-0011 — ``0o700`` dirs, ``0o600`` files, ``os.replace``.
- Phase-3 ADR-0010 — frozen Pydantic error models, ``Literal[...]``
  closed sets, smart-constructor newtypes.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from typing import Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.errors import CodegenieError
from codegenie.hashing import _UNIT_SEP, content_hash_bytes
from codegenie.plugins.bundle import Bundle
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import (
    BlobDigest,
    BundleCacheKey,
    PluginId,
    PrimitiveName,
)

__all__ = sorted(
    [
        "BundleCacheErrorModel",
        "BundleCacheKey",
        "BundleCacheRaise",
        "BundleCacheStore",
        "compose_bundle_cache_key",
    ]
)


_BUNDLES_DIRNAME: Final[str] = "bundles"
_FILE_MODE: Final[int] = 0o600
_DIR_MODE: Final[int] = 0o700
_VALID_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^blake3:[0-9a-f]{64}$")

# Composer-input order — referenced by AC-7 (declared byte layout) and the
# parametrised mutation table at AC-8. Adding a 9th input requires an
# additive amendment to Phase-3 ADR-0008 and is out of scope here (see
# story §Notes DP-E).
_COMPOSER_INPUT_ORDER: Final[tuple[str, ...]] = (
    "plugin_id",
    "plugin_version",
    "primitive",
    "args_canonical",
    "repo_ctx_digest",
    "scip_digest",
    "dep_graph_digest",
    "vuln_index_digest",
)


_logger = structlog.get_logger(__name__)


# --- Error model ------------------------------------------------------------


class BundleCacheErrorModel(BaseModel):
    """Typed error payload for :class:`BundleCacheRaise`.

    Frozen Pydantic ``BaseModel`` (mirrors S3-01 ``TCCMParseError`` and
    S3-04 ``BundleBuilderError`` precedents). ``reason`` is a closed
    :class:`~typing.Literal` set — additions require an ADR amendment.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal[
        "invalid_ttl_env",
        "separator_in_input",
        "invalid_key",
        "corrupt_gc_stamp",
    ]
    details: dict[str, str | int] = {}


class BundleCacheRaise(CodegenieError):
    """Thin :class:`CodegenieError` wrapper that carries a typed
    :class:`BundleCacheErrorModel` payload via ``.model``.

    The marker-only ``CodegenieError`` discipline forbids state on
    subclasses; this raise-class is the boundary where the typed
    payload becomes ``raise``-able.
    """

    def __init__(self, model: BundleCacheErrorModel) -> None:
        self.model: BundleCacheErrorModel = model
        super().__init__(model.model_dump_json())


# --- Cache key composer -----------------------------------------------------


def compose_bundle_cache_key(
    *,
    plugin_id: PluginId,
    plugin_version: str,
    primitive: PrimitiveName,
    args_canonical: str,
    repo_ctx_digest: BlobDigest,
    scip_digest: BlobDigest,
    dep_graph_digest: BlobDigest,
    vuln_index_digest: BlobDigest,
) -> BundleCacheKey:
    """Return the ``blake3:<64-hex>`` Bundle cache key over the 8 declared inputs.

    Inputs are joined by :data:`codegenie.hashing._UNIT_SEP` (``\\x1f``)
    in the order declared by the keyword-only signature (matches
    :data:`_COMPOSER_INPUT_ORDER`) and the joined payload is hashed via
    :func:`codegenie.hashing.content_hash_bytes` — already prefix-tagged
    ``"blake3:"``, so we do NOT double-prefix.

    The composer is **opaque** to ``args_canonical``: two strings
    differing only in whitespace produce different keys. The canonical
    caller form is ``json.dumps(args, sort_keys=True,
    separators=(",", ":"), ensure_ascii=False)`` — see
    :func:`codegenie.plugins.bundle._canonicalize_args` for the
    in-tree producer.

    Any input containing the ``\\x1f`` separator raises
    :class:`BundleCacheRaise` with ``reason="separator_in_input"`` —
    a printable-separator analogue of the boundary-shift attack the
    arity byte defuses in :func:`codegenie.hashing.identity_hash`.
    """

    parts = (
        plugin_id,
        plugin_version,
        primitive,
        args_canonical,
        repo_ctx_digest,
        scip_digest,
        dep_graph_digest,
        vuln_index_digest,
    )
    for name, value in zip(_COMPOSER_INPUT_ORDER, parts, strict=True):
        if _UNIT_SEP in value:
            raise BundleCacheRaise(
                BundleCacheErrorModel(
                    reason="separator_in_input",
                    details={"input": name},
                )
            )
    payload = _UNIT_SEP.join(parts).encode("utf-8")
    return BundleCacheKey(content_hash_bytes(payload))


# --- Key validation ---------------------------------------------------------


def _validate_key(key: str) -> None:
    """Raise :class:`BundleCacheRaise` if ``key`` is not ``blake3:<64-hex>``.

    Defends the on-disk filename derivation against path-traversal
    (e.g. ``"blake3:../../etc/passwd"`` would otherwise become a
    relative-path filename).
    """
    if not _VALID_KEY_RE.fullmatch(key):
        raise BundleCacheRaise(
            BundleCacheErrorModel(
                reason="invalid_key",
                details={"key_prefix": key[:16]},
            )
        )


def _key_to_filename(key: BundleCacheKey) -> str:
    """Return the on-disk filename for a validated key.

    The ``"blake3:"`` algorithm prefix lives in the :class:`BundleCacheKey`
    string only — never in the filesystem name (keeps the layout
    Windows-clean even though Phase 3 is Linux/macOS).
    """
    return key[len("blake3:") :] + ".json"


# --- BundleCacheStore -------------------------------------------------------


def _atomic_write_bytes(target: SandboxedPath, data: bytes) -> None:
    """Write ``data`` to ``target`` via per-writer tmp + fsync + ``os.replace``.

    Mirrors :func:`codegenie.cache.store._atomic_write_bytes` (Phase-0
    precedent). The tmp filename embeds ``os.getpid()`` + a random
    short token so two concurrent writers of the same target do not
    race on the same ``<target>.tmp`` slot.
    """
    tmp = target.with_suffix(target.suffix + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)


class BundleCacheStore:
    """On-disk content-addressed Bundle cache.

    Layout: ``<cache_dir>/bundles/<64-hex>.json`` (one file per
    :class:`~codegenie.plugins.bundle.Bundle`, JSON-serialised). Writes
    are atomic (tmp + fsync + ``os.replace``); reads are lock-free; a
    corrupt blob does NOT delete the file — operators must be able to
    inspect what they cached. The blob mode is ``0o600`` and the
    ``bundles/`` directory mode is ``0o700`` (Phase-0 ADR-0011).
    """

    def __init__(self, cache_dir: SandboxedPath) -> None:
        self.cache_dir: SandboxedPath = cache_dir

    def _bundles_dir(self) -> SandboxedPath:
        return self.cache_dir / _BUNDLES_DIRNAME

    def put(self, key: BundleCacheKey, bundle: Bundle) -> None:
        """Write ``bundle`` to ``<cache_dir>/bundles/<64-hex>.json``.

        Idempotent: writing the same ``(key, bundle)`` twice leaves
        byte-identical content; writing the same key with a different
        :class:`Bundle` is a clean overwrite.

        Rejects any ``key`` not matching ``^blake3:[0-9a-f]{64}$`` with
        :class:`BundleCacheRaise` (``reason="invalid_key"``).
        """
        _validate_key(key)
        bundles = self._bundles_dir()
        bundles.mkdir(parents=True, exist_ok=True)
        os.chmod(bundles, _DIR_MODE)
        target = bundles / _key_to_filename(key)
        data = bundle.model_dump_json().encode("utf-8")
        _atomic_write_bytes(target, data)

    def get(self, key: BundleCacheKey) -> Bundle | None:
        """Return the :class:`Bundle` at ``key`` or ``None`` on miss.

        Returns ``None`` for missing files, missing ``cache_dir`` /
        ``bundles/`` directory, and on
        :class:`pydantic.ValidationError` /
        :class:`json.JSONDecodeError`. Corrupt blobs are **not deleted**
        — operators want to inspect the bytes (Rule 12).
        """
        _validate_key(key)
        target = self._bundles_dir() / _key_to_filename(key)
        try:
            data = target.read_bytes()
        except FileNotFoundError:
            return None
        try:
            return Bundle.model_validate_json(data)
        except (ValidationError, json.JSONDecodeError) as exc:
            _logger.warning(
                "cache.bundle.corrupt",
                path=str(target),
                key_prefix=key[:16],
                exc=repr(exc),
            )
            return None
