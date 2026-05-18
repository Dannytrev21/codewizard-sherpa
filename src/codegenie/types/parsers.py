"""Phase 3 S1-01 — smart-constructor boundary parsers for the 14 newtypes.

Every external-boundary input (YAML plugin manifest, CVE feed, branch-name
validator, registry URL, …) crosses through one of these pure functions
exactly once on its way to a typed value. Each returns
``Result[<X>, ParseError]`` from :mod:`codegenie.result` — never raises.

Every regex match flows through the single private :func:`_regex_parser`
helper (AC-18 — adding a new regex-shaped parser is one line). Parsers that
need additional validation (NFKC normalisation, URL structure, etc.) layer
the helper on top of their own preflight checks; ``.fullmatch(`` never
appears outside :func:`_regex_parser`.

ADRs: phase-3 ADR-0010 (smart-constructor convention + every regex below),
production ADR-0033 (newtype every domain identifier).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Final

from codegenie.result import Err, Ok, Result
from codegenie.types.errors import ParseError
from codegenie.types.identifiers import (
    AttemptNumber,
    BlobDigest,
    BranchName,
    CveId,
    EventId,
    PackageId,
    PluginId,
    PrimitiveName,
    RecipeId,
    RegistryUrl,
    SignalKind,
    TransformId,
    TransformKind,
    WorkflowId,
)

__all__ = [
    "parse_attempt_number",
    "parse_blob_digest",
    "parse_branch_name",
    "parse_cve_id",
    "parse_event_id",
    "parse_package_id",
    "parse_plugin_id",
    "parse_primitive_name",
    "parse_recipe_id",
    "parse_registry_url",
    "parse_signal_kind",
    "parse_transform_id",
    "parse_transform_kind",
    "parse_workflow_id",
]


# --- Module-level compiled patterns (Final; ADR-0010 § grammar table) ------

_CVE_RX: Final[re.Pattern[str]] = re.compile(r"^CVE-\d{4}-\d{4,7}$")
_ULID_RX: Final[re.Pattern[str]] = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_HEX64_RX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_SNAKE_RX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_RECIPE_RX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_PLUGIN_RX: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9-]{0,63}--[a-z][a-z0-9-]{0,31}--[a-z][a-z0-9-]{0,31}$"
)
_BRANCH_RX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9/_.\-]{1,200}$")
_NPM_NAME_RX: Final[re.Pattern[str]] = re.compile(r"^(?:@[a-z0-9\-_.]+/)?[a-z0-9\-_.]+$")
_PINNED_SEMVER_RX: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.+-]+)?$")
_HOST_RX: Final[re.Pattern[str]] = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$"
)

_REGISTRY_URL_MAX_LEN: Final[int] = 2048


# --- Single helper — every regex match flows through here (AC-18) ----------


def _regex_parser(
    rx: re.Pattern[str], *, max_len: int, name: str
) -> Callable[[str], Result[str, ParseError]]:
    """Build a Result-returning regex parser.

    The closed-over ``rx``/``max_len``/``name`` get baked into the returned
    callable; the only ``.fullmatch(`` call in the module lives here. Adding
    a new regex-shaped parser = one row in the catalog below.
    """

    def _parse(s: str) -> Result[str, ParseError]:
        if len(s) > max_len:
            return Err(error=ParseError(message=f"{name}: exceeds max length {max_len}", value=s))
        if rx.fullmatch(s) is None:
            return Err(error=ParseError(message=f"{name}: does not match {rx.pattern}", value=s))
        return Ok(value=s)

    return _parse


# Catalog of regex-shaped sub-parsers — every regex match in the module
# routes through one of these closures, so ``.fullmatch(`` never appears
# outside ``_regex_parser`` (AC-18).
_cve_match = _regex_parser(_CVE_RX, max_len=21, name="CveId")
_ulid_match = _regex_parser(_ULID_RX, max_len=26, name="Ulid")
_hex64_match = _regex_parser(_HEX64_RX, max_len=64, name="Hex64")
_signal_match = _regex_parser(_SNAKE_RX, max_len=31, name="SignalKind")
_primitive_match = _regex_parser(_SNAKE_RX, max_len=31, name="PrimitiveName")
_transform_kind_match = _regex_parser(_SNAKE_RX, max_len=31, name="TransformKind")
_recipe_match = _regex_parser(_RECIPE_RX, max_len=64, name="RecipeId")
_plugin_match = _regex_parser(_PLUGIN_RX, max_len=130, name="PluginId")
_branch_match = _regex_parser(_BRANCH_RX, max_len=200, name="BranchName")
_npm_name_match = _regex_parser(_NPM_NAME_RX, max_len=214, name="PackageId.name")
_pinned_semver_match = _regex_parser(_PINNED_SEMVER_RX, max_len=128, name="PackageId.version")
_host_match = _regex_parser(_HOST_RX, max_len=253, name="RegistryUrl.host")


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 0x80 for c in s)


# --- Public parsers --------------------------------------------------------


def parse_cve_id(s: str) -> Result[CveId, ParseError]:
    """External boundary: CVE feed / fixture filename. ADR-0010."""
    r = _cve_match(s)
    return Ok(value=CveId(r.value)) if isinstance(r, Ok) else r


def parse_signal_kind(s: str) -> Result[SignalKind, ParseError]:
    """External boundary: trust-signal emitter registration. ADR-0010."""
    r = _signal_match(s)
    return Ok(value=SignalKind(r.value)) if isinstance(r, Ok) else r


def parse_primitive_name(s: str) -> Result[PrimitiveName, ParseError]:
    """External boundary: sandbox capabilities catalog. ADR-0010."""
    r = _primitive_match(s)
    return Ok(value=PrimitiveName(r.value)) if isinstance(r, Ok) else r


def parse_transform_kind(s: str) -> Result[TransformKind, ParseError]:
    """External boundary: recipe registry transform-kind catalog. ADR-0010."""
    r = _transform_kind_match(s)
    return Ok(value=TransformKind(r.value)) if isinstance(r, Ok) else r


def parse_recipe_id(s: str) -> Result[RecipeId, ParseError]:
    """External boundary: recipe registry key. ADR-0010."""
    r = _recipe_match(s)
    return Ok(value=RecipeId(r.value)) if isinstance(r, Ok) else r


def parse_plugin_id(s: str) -> Result[PluginId, ParseError]:
    """External boundary: ``plugin.yaml``. ADR-0010."""
    r = _plugin_match(s)
    return Ok(value=PluginId(r.value)) if isinstance(r, Ok) else r


def parse_transform_id(s: str) -> Result[TransformId, ParseError]:
    """Internal boundary: BLAKE3 diff digest. ADR-0010, arch §C4."""
    r = _hex64_match(s)
    if isinstance(r, Err):
        return Err(error=ParseError(message="TransformId: must be 64 lowercase hex chars", value=s))
    return Ok(value=TransformId(r.value))


def parse_blob_digest(s: str) -> Result[BlobDigest, ParseError]:
    """Internal boundary: cache key / artifact digest. ADR-0010."""
    r = _hex64_match(s)
    if isinstance(r, Err):
        return Err(error=ParseError(message="BlobDigest: must be 64 lowercase hex chars", value=s))
    return Ok(value=BlobDigest(r.value))


def parse_workflow_id(s: str) -> Result[WorkflowId, ParseError]:
    """Internal boundary: orchestrator workflow ULID. ADR-0010, arch §C5."""
    r = _ulid_match(s)
    if isinstance(r, Err):
        return Err(
            error=ParseError(message="WorkflowId: must be 26-char Crockford base32 ULID", value=s)
        )
    return Ok(value=WorkflowId(r.value))


def parse_event_id(s: str) -> Result[EventId, ParseError]:
    """Internal boundary: append-only event log entry ULID. ADR-0010."""
    r = _ulid_match(s)
    if isinstance(r, Err):
        return Err(
            error=ParseError(message="EventId: must be 26-char Crockford base32 ULID", value=s)
        )
    return Ok(value=EventId(r.value))


def parse_branch_name(s: str) -> Result[BranchName, ParseError]:
    """External boundary: git branch name. NFKC + ASCII-only. ADR-0010."""
    normalised = unicodedata.normalize("NFKC", s)
    if not _is_ascii(normalised):
        return Err(error=ParseError(message="BranchName: non-ASCII after NFKC", value=s))
    if "\x00" in normalised:
        return Err(error=ParseError(message="BranchName: contains NUL", value=s))
    if normalised.startswith("."):
        return Err(error=ParseError(message="BranchName: must not start with '.'", value=s))
    if normalised.endswith("/"):
        return Err(error=ParseError(message="BranchName: must not end with '/'", value=s))
    if "//" in normalised:
        return Err(error=ParseError(message="BranchName: must not contain '//'", value=s))
    # Reject inputs that NFKC-expanded into ASCII from non-ASCII originals —
    # accept only byte-for-byte unchanged inputs to keep round-trip identity.
    if normalised != s:
        return Err(
            error=ParseError(message="BranchName: NFKC-normalisation changed value", value=s)
        )
    r = _branch_match(normalised)
    if isinstance(r, Err):
        return Err(error=ParseError(message=f"BranchName: {r.error.message}", value=s))
    return Ok(value=BranchName(s))


def parse_package_id(s: str) -> Result[PackageId, ParseError]:
    """External boundary: npm ``<name>@<pinned-semver>`` coordinate. NFKC + ASCII-only. ADR-0010."""
    normalised = unicodedata.normalize("NFKC", s)
    if not _is_ascii(normalised):
        return Err(error=ParseError(message="PackageId: non-ASCII after NFKC", value=s))
    if "\x00" in normalised:
        return Err(error=ParseError(message="PackageId: contains NUL", value=s))
    # Reject NFKC-changing inputs to keep round-trip identity (caller cannot
    # smuggle a homoglyph that becomes ASCII only after normalisation).
    if normalised != s:
        return Err(error=ParseError(message="PackageId: NFKC-normalisation changed value", value=s))
    # Split on the LAST '@' so scoped names (``@scope/pkg@1.0.0``) parse correctly.
    if "@" not in normalised[1:]:
        return Err(error=ParseError(message="PackageId: missing '@<version>'", value=s))
    name, _, version = normalised.rpartition("@")
    if not name or not version:
        return Err(error=ParseError(message="PackageId: empty name or version", value=s))
    if isinstance(_npm_name_match(name), Err):
        return Err(
            error=ParseError(message=f"PackageId: name must match {_NPM_NAME_RX.pattern}", value=s)
        )
    if isinstance(_pinned_semver_match(version), Err):
        return Err(
            error=ParseError(
                message=f"PackageId: version must match {_PINNED_SEMVER_RX.pattern}", value=s
            )
        )
    return Ok(value=PackageId(s))


def parse_registry_url(s: str) -> Result[RegistryUrl, ParseError]:
    """External boundary: ``.npmrc`` / config registry URL. Strict-https. ADR-0010."""
    if len(s) > _REGISTRY_URL_MAX_LEN:
        return Err(
            error=ParseError(message=f"RegistryUrl: exceeds {_REGISTRY_URL_MAX_LEN} chars", value=s)
        )
    if not _is_ascii(s):
        return Err(error=ParseError(message="RegistryUrl: non-ASCII", value=s))
    if not s.startswith("https://"):
        return Err(error=ParseError(message="RegistryUrl: must start with 'https://'", value=s))
    rest = s[len("https://") :]
    if not rest:
        return Err(error=ParseError(message="RegistryUrl: empty host", value=s))
    if "?" in rest:
        return Err(error=ParseError(message="RegistryUrl: query string not allowed", value=s))
    if "#" in rest:
        return Err(error=ParseError(message="RegistryUrl: fragment not allowed", value=s))
    host_port, _slash, _path = rest.partition("/")
    if "@" in host_port:
        return Err(error=ParseError(message="RegistryUrl: userinfo not allowed", value=s))
    if ":" in host_port:
        host, _, port = host_port.partition(":")
        if not port.isdigit():
            return Err(error=ParseError(message="RegistryUrl: port must be numeric", value=s))
    else:
        host = host_port
    if not host:
        return Err(error=ParseError(message="RegistryUrl: empty host", value=s))
    if isinstance(_host_match(host), Err):
        return Err(
            error=ParseError(message=f"RegistryUrl: host must match {_HOST_RX.pattern}", value=s)
        )
    return Ok(value=RegistryUrl(s))


def parse_attempt_number(n: int) -> Result[AttemptNumber, ParseError]:
    """Internal boundary: retry counter. 1..1024 inclusive. ADR-0010."""
    if not isinstance(n, int) or isinstance(n, bool):
        return Err(error=ParseError(message="AttemptNumber: must be int", value=repr(n)))
    if n < 1 or n > 1024:
        return Err(error=ParseError(message="AttemptNumber: must be in 1..1024", value=repr(n)))
    return Ok(value=AttemptNumber(n))
