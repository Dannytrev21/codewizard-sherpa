"""``PLUGINS.lock`` typed loader — Phase 3 S2-03.

``plugins/PLUGINS.lock`` ships as ``{}`` in Phase 3 (the first concrete
plugin lands in Step 7 / S7-01). The lock is the canonical attestation of
which plugin slugs the repo trusts plus their SHA-256 tree-digests
(ADR-0011 honest-framing — "integrity check", not "signature").

The :class:`LockFile` Pydantic ``RootModel`` exists to make the
``dict[PluginId, BlobDigest]`` shape *typed at the boundary* — raw
``dict[str, str]`` is lifted exactly once through ``parse_plugin_id`` +
``parse_blob_digest`` at load time. Any failure (top-level non-object,
key that is not a valid ``PluginId``, value that is not a valid 64-hex
``BlobDigest``) is returned as :class:`LockFileMalformed` via
:meth:`LockFile.from_path` — never raised.

I/O routes through :func:`codegenie.parsers.safe_json.load` (Phase 1
ADR-0009 chokepoint: ``O_NOFOLLOW`` + ``os.fstat`` size cap + post-parse
depth cap). The Phase-3 loader's AST source-scan fence forbids direct
``json`` imports under ``src/codegenie/plugins/loader.py``; this module
holds the only ``safe_json.load`` call on the loader path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import RootModel, ValidationError, model_validator

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.parsers import safe_json
from codegenie.plugins.errors import LockFileMalformed
from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import BlobDigest, PluginId
from codegenie.types.parsers import parse_blob_digest, parse_plugin_id

__all__ = ["LockFile"]


# ``plugins/PLUGINS.lock`` is small by design: 64KiB ceiling and depth=2 cap
# (top-level object plus value strings). A bloated lock indicates corruption
# rather than legitimate growth.
_LOCKFILE_MAX_BYTES: Final[int] = 1 << 16
_LOCKFILE_MAX_DEPTH: Final[int] = 2
_LOCKFILE_SENTINEL: Final[PluginId] = PluginId("<lockfile>")


class LockFile(RootModel[dict[PluginId, BlobDigest]]):
    """Typed wrapper for ``plugins/PLUGINS.lock`` contents.

    ``LockFile.root`` is ``dict[PluginId, BlobDigest]``. The Pydantic
    ``model_validator`` below lifts the raw ``dict[str, str]`` returned by
    ``safe_json`` through the S1-01 smart-constructor parsers exactly once.
    Lifting failures raise ``ValueError``; :meth:`from_path` catches the
    wrapped ``ValidationError`` and converts to :class:`LockFileMalformed`.
    """

    @model_validator(mode="before")
    @classmethod
    def _lift_keys_and_values(cls, data: object) -> dict[PluginId, BlobDigest]:
        if not isinstance(data, dict):
            raise ValueError("PLUGINS.lock root must be a JSON object")
        lifted: dict[PluginId, BlobDigest] = {}
        for raw_name, raw_digest in data.items():
            if not isinstance(raw_name, str):
                raise ValueError(f"PLUGINS.lock key must be string, got {type(raw_name).__name__}")
            if not isinstance(raw_digest, str):
                raise ValueError(
                    f"PLUGINS.lock value for {raw_name!r} must be string, "
                    f"got {type(raw_digest).__name__}"
                )
            parsed_name = parse_plugin_id(raw_name)
            if isinstance(parsed_name, Err):
                raise ValueError(f"PLUGINS.lock key {raw_name!r}: {parsed_name.error.message}")
            parsed_digest = parse_blob_digest(raw_digest)
            if isinstance(parsed_digest, Err):
                raise ValueError(
                    f"PLUGINS.lock value for {raw_name!r}: {parsed_digest.error.message}"
                )
            lifted[parsed_name.value] = parsed_digest.value
        return lifted

    @classmethod
    def from_path(cls, path: Path) -> Result[LockFile, LockFileMalformed]:
        """Load + validate ``plugins/PLUGINS.lock``; never raises.

        Routes the byte-read through :func:`codegenie.parsers.safe_json.load`
        — the Phase 1 ADR-0009 JSON chokepoint with ``O_NOFOLLOW`` + 64KiB
        cap + depth=2 cap.

        Returns:
            ``Ok(LockFile)`` on success; ``Err(LockFileMalformed)`` for
            every failure mode (missing file, symlink, size-cap, depth-cap,
            decode error, top-level non-object, invalid ``PluginId`` key,
            invalid ``BlobDigest`` value).
        """
        try:
            raw = safe_json.load(
                path,
                max_bytes=_LOCKFILE_MAX_BYTES,
                max_depth=_LOCKFILE_MAX_DEPTH,
            )
        except SymlinkRefusedError as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))
        except SizeCapExceeded as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))
        except DepthCapExceeded as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))
        except MalformedJSONError as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))
        except OSError as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))

        try:
            return Ok(value=cls.model_validate(raw))
        except ValidationError as exc:
            return Err(error=LockFileMalformed(plugin=_LOCKFILE_SENTINEL, detail=str(exc)))
