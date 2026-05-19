"""S3-03 — shared CVE-feed parser kernel: size + depth caps + error model.

``VulnParseError`` is a **frozen Pydantic BaseModel** carrying a closed
``Literal[...]`` reason (NOT a markers-only :class:`CodegenieError`
subclass — S3-01 and S3-02 set the precedent verbatim). Adding a reason
variant requires a story amendment.

Module-purity invariants (AC-N2 + AC-N3):

- No ``requests`` / ``httpx`` / ``urllib3`` imports anywhere in this module.
- ``urllib.request`` is **lazy-imported inside each ``Feed.fetch`` body**;
  this module does NOT import it.
- No ``alembic`` import — cold-start fence ``test_cold_start_parsers.py``
  asserts ``import codegenie.vuln_index.parsers`` adds neither to
  ``sys.modules``.

ADRs: phase-3 ADR-0010 (closed sum-type discipline on ``reason``); production
ADR-0033 (smart-constructor parser pattern); production ADR-0005 (cold-start
budget — no heavyweight imports in the shared kernel).
"""

from __future__ import annotations

import json
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.result import Err, Ok, Result

__all__ = [
    "VulnParseError",
    "VulnParseException",
    "canonical_raw_payload",
]


# AC-S1 — caps (module-level Final; story amendment to change).
_MAX_PAYLOAD_BYTES: Final[int] = 1_048_576  # 1 MiB per fetch chunk
_MAX_JSON_DEPTH: Final[int] = 16
_MAX_RAW_PAYLOAD_BYTES: Final[int] = 262_144  # 256 KiB per persisted row
_MAX_ERROR_REPORT: Final[int] = 100  # cap on ``IngestStats.errors`` list


# ---------------------------------------------------------------------------
# Error model — frozen Pydantic, closed Literal reason (S3-01/S3-02 precedent).
# ---------------------------------------------------------------------------


class VulnParseError(BaseModel):
    """Parse failure with a typed ``reason`` payload (frozen, ``extra="forbid"``).

    Closed-set reason — mypy --strict catches typos at the construction
    site. ``details`` is unconstrained (``str | int`` values only) but its
    keys are reason-specific by convention:

    - ``payload_too_large``: ``{"size": int, "limit": int}``
    - ``json_too_deep``: ``{"depth": int}``
    - ``bad_json``: ``{"message": str}``
    - ``missing_required_field``: ``{"field": str}``
    - ``unsupported_ecosystem``: ``{"ecosystem": str}``
    - ``bad_cve_id``: ``{"value": str}``
    - ``bad_ghsa_id``: ``{"value": str}``
    - ``missing_tz``: ``{"value": str}`` (the offending raw datetime)
    - ``bad_semver``: ``{"value": str, "field": str}``
    - ``bad_ecosystem``: ``{"value": str}``
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal[
        "payload_too_large",
        "json_too_deep",
        "bad_json",
        "missing_required_field",
        "unsupported_ecosystem",
        "bad_cve_id",
        "bad_ghsa_id",
        "missing_tz",
        "bad_semver",
        "bad_ecosystem",
    ]
    details: dict[str, str | int] = {}


class VulnParseException(Exception):
    """Thin wrapper carrying a single :class:`VulnParseError` model.

    Production code paths either:

    - return ``Result.err(VulnParseError(...))`` (parser ``parse_one``); or
    - raise ``VulnParseException(VulnParseError(...))`` from a shared helper
      (e.g., :func:`_check_depth`) when surfacing via ``Result`` would force
      every recursive frame to plumb ``Err`` through.
    """

    def __init__(self, model: VulnParseError) -> None:
        super().__init__(f"VulnParseError: reason={model.reason!r} details={model.details!r}")
        self.model: VulnParseError = model


# ---------------------------------------------------------------------------
# Shared helpers (functional core — pure, no I/O).
# ---------------------------------------------------------------------------


def _safe_json_load(raw: bytes) -> Result[object, VulnParseError]:
    """Decode JSON with the 1 MiB size cap (AC-S2 / AC-S4).

    Order matters: the size check fires **before** ``json.loads`` so a
    multi-MB payload cannot exhaust memory under the parser. A valid-size
    payload that fails ``json.loads`` maps to ``bad_json`` carrying the
    decoder's message.
    """
    if len(raw) > _MAX_PAYLOAD_BYTES:
        return Err(
            error=VulnParseError(
                reason="payload_too_large",
                details={"size": len(raw), "limit": _MAX_PAYLOAD_BYTES},
            )
        )
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        return Err(error=VulnParseError(reason="bad_json", details={"message": str(exc)}))
    return Ok(value=value)


def _check_depth(value: object, *, max_depth: int = _MAX_JSON_DEPTH) -> None:
    """Walk ``value`` enforcing the depth cap (AC-S3).

    Depth counts the root container as depth 1. A dict / list at depth N
    extends depth into its children at depth N+1. Strings / numbers / null
    are leaves and do not extend depth. Raises
    :class:`VulnParseException` (wrapping ``reason="json_too_deep"``) on
    breach.
    """

    def _walk(node: object, depth: int) -> None:
        if depth > max_depth:
            raise VulnParseException(
                VulnParseError(reason="json_too_deep", details={"depth": depth})
            )
        if isinstance(node, dict):
            for child in node.values():
                if isinstance(child, (dict, list)):
                    _walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                if isinstance(child, (dict, list)):
                    _walk(child, depth + 1)

    if isinstance(value, (dict, list)):
        _walk(value, 1)


def canonical_raw_payload(record_dict: dict[str, Any]) -> bytes:
    """Canonical JSON serialization of one record (sorted keys, no whitespace).

    Used by :func:`codegenie.vuln_index.ingest._update_feed_digest` to feed
    a byte-stable representation into the BLAKE3 chokepoint regardless of
    upstream dict ordering. Caller is responsible for converting datetime /
    other non-JSON-primitive fields via ``.isoformat()`` etc.
    """
    return json.dumps(record_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
