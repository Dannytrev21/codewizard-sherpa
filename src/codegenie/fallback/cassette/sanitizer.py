"""Phase-4 S3-04 — ``CassetteSanitizer``: pure-function sanitizer + verifier.

Layer 1 of the ADR-0014 cassette-discipline stack — the load-bearing first
layer that ensures the FIRST BYTE any cassette ever writes is already clean.

The sanitizer strips secret HTTP headers and body-scans for shaped secrets
on the ``pytest-recording`` ``before_record_request`` /
``before_record_response`` hook entry-points. It is wired in
``tests/conftest.py``'s ``vcr_config`` fixture.

ADRs honored:

- **Phase-4 ADR-0014** — exact header list + body patterns; sanitizer drops
  fields silently on record. CI scanner (S3-05) is the surfacing layer.
- **Phase-4 ADR-0003** — path-scoped fence admits this module under
  ``src/codegenie/fallback/``.

Discipline (story S3-04):

- **Functional core / imperative shell**: every helper that performs the
  scan/redact arithmetic is pure (``_normalize_headers``, ``_strip_headers``,
  ``_redact_header_values``, ``_redact_body``, ``_scan_cassette_doc``);
  :func:`verify_cassette` is the ONLY function in this module that touches
  ``Path`` / ``open`` / ``yaml``. The split is what makes
  ``tests/fence/test_sanitizer_purity.py``'s AST check applicable, and it is
  what S3-05's CI scanner reuses against in-memory documents.
- **Single bytes catalog**: ``_BODY_SECRET_PATTERNS`` is one
  ``Final[tuple[re.Pattern[bytes], ...]]`` of three rows; ``str`` header
  values are encoded once at the boundary so there is no parallel str/bytes
  tuple to keep in sync (AC-3).
- **Three scan surfaces** per sanitization call: (a) header *names* against
  ``_FORBIDDEN_HEADERS``, (b) surviving header *values* against
  ``_BODY_SECRET_PATTERNS``, (c) bodies against ``_BODY_SECRET_PATTERNS``.
- **No in-place mutation**: ``copy.deepcopy`` then edit the copy. The input
  is byte-for-byte identical after the call (AC-4 / AC-5).
- **Total verifier**: :func:`verify_cassette` over a non-existent path / empty
  file / non-YAML / missing ``interactions`` returns a single
  ``Violation(kind="unreadable", ...)`` rather than raising (AC-20). S3-05's
  directory walk depends on this.

The sanitizer is intentionally **silent** — it emits no warnings on the
record path (ADR-0014 §Decision item 1). Hence ``_WARNING_IDS`` is the empty
frozenset (AC-17). The CI scanner (S3-05) is where surfacing happens.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, computed_field, model_validator

__all__ = (
    "CassetteVerification",
    "Violation",
    "sanitize_request",
    "sanitize_response",
    "verify_cassette",
)


# --- Module-level constants (Final, AC-1) ---------------------------------


_FORBIDDEN_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
        "anthropic-version",
    }
)
"""Header *names* dropped at record time (case-insensitive — RFC 7230)."""


_BODY_SECRET_PATTERNS: Final[tuple[re.Pattern[bytes], ...]] = (
    re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"claude_[A-Za-z0-9_-]{20,}"),
    re.compile(rb"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)
"""Body / header-value patterns. Bytes-typed (bodies are bytes) — the str
header value path encodes once at the boundary and scans the same catalog.
Adding a pattern is a one-line tuple edit (Open/Closed)."""


_WARNING_IDS: Final[frozenset[str]] = frozenset()
"""The sanitizer emits no warnings — it drops silently per ADR-0014.
The CI scanner (S3-05) is where surfacing happens."""


_REDACTED_BYTES: Final[bytes] = b"[REDACTED]"


# --- Diagnostic models (AC-9) ---------------------------------------------


_ViolationKind = Literal[
    "header",
    "header_value",
    "body_request",
    "body_response",
    "unreadable",
]


class Violation(BaseModel):
    """One leak record produced by :func:`verify_cassette`.

    ``kind`` is the discriminator; the ``@model_validator(mode="after")``
    enforces kind/field coupling so a nonsense ``Violation`` cannot be
    constructed (AC-9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    interaction_index: int
    kind: _ViolationKind
    header_name: str | None = None
    pattern: str | None = None
    snippet: str

    @model_validator(mode="after")
    def _check_kind_field_coupling(self) -> Violation:
        if self.kind in ("header", "header_value"):
            if self.header_name is None:
                raise ValueError(f"Violation(kind={self.kind!r}) requires header_name")
        if self.kind in ("body_request", "body_response"):
            if self.pattern is None:
                raise ValueError(f"Violation(kind={self.kind!r}) requires pattern")
        return self


class CassetteVerification(BaseModel):
    """Result of :func:`verify_cassette`.

    The model's only data field is ``violations``. ``passed`` is a
    computed property — ``passed=True`` alongside a non-empty
    ``violations`` is structurally unrepresentable (the silent-leak
    failure mode is impossible by construction; AC-9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    violations: tuple[Violation, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return not self.violations


# --- Pure helpers (functional core; AC-21 / AC-23) ------------------------


def _normalize_headers(headers: Any) -> list[tuple[str, str]]:
    """Absorb vcrpy's two header-storage shapes into a single list-of-pairs.

    vcrpy stores request headers as a ``dict[str, str]`` (or
    ``HeadersDict`` subclass) and *cassette-doc* response headers as
    ``dict[str, list[str]]``. Either shape (or a list of pairs) lands here
    and leaves as ``list[tuple[str, str]]``. Pure — no I/O.
    """
    if headers is None:
        return []
    if isinstance(headers, Mapping):
        # vcrpy's HeadersDict is a CaseInsensitiveDict subclass — a
        # ``MutableMapping`` but NOT a ``dict`` subclass; we MUST use
        # ``Mapping`` here or the isinstance check falls through to the
        # stringify fallback and the entire headers object becomes one
        # `(repr, "")` row. (Discovered via integration TDD against
        # ``vcr.request.Request``.)
        out: list[tuple[str, str]] = []
        for name, value in headers.items():
            if isinstance(value, (list, tuple)):
                for v in value:
                    out.append((str(name), str(v)))
            else:
                out.append((str(name), str(value)))
        return out
    if isinstance(headers, (list, tuple)):
        return [(str(n), str(v)) for n, v in headers]
    # Fallback: empty (defensive; should not be reached against vcrpy).
    return []


def _strip_headers(
    pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Drop header *names* matching ``_FORBIDDEN_HEADERS`` (case-insensitive)."""
    return [(n, v) for n, v in pairs if n.lower() not in _FORBIDDEN_HEADERS]


def _redact_value_bytes(value: bytes) -> bytes:
    """Apply ``_BODY_SECRET_PATTERNS`` to a bytes buffer; return redacted bytes.

    Pure. Iterates the catalog — never branches per-pattern. The implementation
    works on arbitrary ``bytes`` (binary or non-UTF-8); no decode step (AC-19).
    """
    out = value
    for pattern in _BODY_SECRET_PATTERNS:
        out = pattern.sub(_REDACTED_BYTES, out)
    return out


def _redact_header_values(
    pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Scan surviving header *values* against the same bytes catalog.

    Header values are ``str``; encode once at the boundary using
    ``surrogatepass`` (defensive against arbitrary byte sequences carried
    in a `str`-typed header), scan with the same one catalog, decode back.
    No parallel str/bytes catalog to keep in sync (AC-3 / Notes §"Bytes
    catalog scans `str` header values too").
    """
    redacted: list[tuple[str, str]] = []
    for name, value in pairs:
        encoded = value.encode("utf-8", "surrogatepass")
        scanned = _redact_value_bytes(encoded)
        if scanned == encoded:
            redacted.append((name, value))
        else:
            redacted.append((name, scanned.decode("utf-8", "surrogatepass")))
    return redacted


def _redact_body(body: Any) -> Any:
    """Redact body bytes; pass-through non-bytes / ``None``.

    vcrpy bodies are ``bytes`` for the request path and a ``dict`` like
    ``{"string": bytes}`` for the cassette-doc response shape. Cassette-doc
    response bodies are unwrapped + re-wrapped to preserve the on-disk shape.
    """
    if body is None:
        return None
    if isinstance(body, bytes):
        return _redact_value_bytes(body)
    if isinstance(body, str):
        # Defensive: some vcrpy versions yield str bodies for text content.
        return _redact_value_bytes(body.encode("utf-8", "surrogatepass")).decode(
            "utf-8", "surrogatepass"
        )
    if isinstance(body, dict) and "string" in body:
        inner = body["string"]
        new_body = dict(body)
        new_body["string"] = _redact_body(inner)
        return new_body
    return body


# --- Public hook entry points (AC-4 / AC-5) -------------------------------


def sanitize_request(request: Any) -> Any:
    """``pytest-recording`` ``before_record_request`` hook entry point.

    Returns a NEW request object; the input is byte-for-byte unchanged
    after the call (AC-4). Sanitizes across three surfaces:
    (a) header *names* in ``_FORBIDDEN_HEADERS`` are dropped,
    (b) surviving header *values* are scanned against
    ``_BODY_SECRET_PATTERNS`` and matches replaced with ``[REDACTED]``,
    (c) the body is scanned with the same catalog.
    """
    if request is None:
        return None
    out = copy.deepcopy(request)

    headers = getattr(out, "headers", None)
    if headers is None and isinstance(out, dict):
        headers = out.get("headers")
    pairs = _normalize_headers(headers)
    stripped = _strip_headers(pairs)
    redacted_pairs = _redact_header_values(stripped)
    _write_headers(out, redacted_pairs)

    if hasattr(out, "body"):
        out.body = _redact_body(out.body)
    elif isinstance(out, dict) and "body" in out:
        out["body"] = _redact_body(out["body"])

    return out


def sanitize_response(response: Any) -> Any:
    """``pytest-recording`` ``before_record_response`` hook entry point.

    Mirrors :func:`sanitize_request` over the three surfaces for response
    objects. Returns a NEW object; the input is byte-for-byte unchanged
    after the call (AC-5).

    The only legitimate difference between the two functions is the
    object shape they destructure and rebuild — scan logic lives in
    shared pure helpers and is never copy-pasted.
    """
    if response is None:
        return None
    out = copy.deepcopy(response)

    headers = getattr(out, "headers", None)
    if headers is None and isinstance(out, dict):
        headers = out.get("headers")
    pairs = _normalize_headers(headers)
    stripped = _strip_headers(pairs)
    redacted_pairs = _redact_header_values(stripped)
    _write_headers(out, redacted_pairs)

    if hasattr(out, "body"):
        out.body = _redact_body(out.body)
    elif isinstance(out, dict) and "body" in out:
        out["body"] = _redact_body(out["body"])

    return out


def _write_headers(target: Any, pairs: list[tuple[str, str]]) -> None:
    """Write the (sanitized) header pairs back into ``target``.

    Preserves the storage shape we found: ``dict[str, str]`` for vcrpy
    request objects, ``dict[str, list[str]]`` for cassette-doc response
    dicts. Pure-helper friendly modulo the targeted mutation — the
    *outer* function (sanitize_*) already worked on a deepcopy.
    """
    # Detect storage shape from the pre-existing object.
    existing = getattr(target, "headers", None)
    if existing is None and isinstance(target, dict):
        existing = target.get("headers")

    if isinstance(existing, Mapping):
        # Was the original a list-valued mapping (cassette-doc response shape)?
        list_valued = any(isinstance(v, list) for v in existing.values())
        new_headers: dict[str, Any] = {}
        if list_valued:
            for name, value in pairs:
                new_headers.setdefault(name, []).append(value)
        else:
            # Collapse multi-pair to last-wins for dict-of-scalars vcrpy shape.
            for name, value in pairs:
                new_headers[name] = value

        if hasattr(target, "headers"):
            # vcr.request.Request stores headers in a ``HeadersDict``
            # (CaseInsensitiveDict subclass). Preserve the storage type so
            # downstream vcrpy code keeps its case-insensitive semantics;
            # fall through to a plain dict if the type isn't constructible
            # from a dict literal.
            try:
                ctor = type(existing)
                target.headers = ctor(new_headers)  # type: ignore[call-arg]
            except TypeError:
                target.headers = new_headers
        else:
            target["headers"] = new_headers
        return

    if isinstance(existing, (list, tuple)):
        if hasattr(target, "headers"):
            target.headers = list(pairs)
        else:
            target["headers"] = list(pairs)
        return

    # No existing headers shape (None / unknown): write a plain dict if there's
    # anything to write at all.
    if pairs:
        new_headers = {}
        for name, value in pairs:
            new_headers[name] = value
        if hasattr(target, "headers"):
            target.headers = new_headers
        elif isinstance(target, dict):
            target["headers"] = new_headers


# --- Cassette walker (functional core + thin I/O shell) -------------------


def _scan_cassette_doc(doc: Any) -> tuple[Violation, ...]:
    """Walk a parsed cassette document; emit violations.

    PURE. No I/O. The walker S3-05's CI scanner reuses against an in-memory
    document (AC-21). Returns an empty tuple on a clean cassette and on
    a cassette whose ``interactions`` list is empty (AC-8).
    """
    if not isinstance(doc, dict):
        return (
            Violation(
                interaction_index=-1,
                kind="unreadable",
                snippet=_snippet_of(repr(doc)[:120]),
            ),
        )
    if "interactions" not in doc:
        return (
            Violation(
                interaction_index=-1,
                kind="unreadable",
                snippet="cassette missing 'interactions' key",
            ),
        )

    interactions = doc.get("interactions") or []
    if not isinstance(interactions, list):
        return (
            Violation(
                interaction_index=-1,
                kind="unreadable",
                snippet="cassette 'interactions' is not a list",
            ),
        )

    out: list[Violation] = []
    for idx, interaction in enumerate(interactions):
        if not isinstance(interaction, dict):
            continue
        request = interaction.get("request") or {}
        response = interaction.get("response") or {}
        if isinstance(request, dict):
            out.extend(_scan_message(idx, request, body_kind="body_request"))
        if isinstance(response, dict):
            out.extend(_scan_message(idx, response, body_kind="body_response"))
    return tuple(out)


def _scan_message(
    idx: int,
    message: dict[str, Any],
    *,
    body_kind: Literal["body_request", "body_response"],
) -> list[Violation]:
    """Pure scan of one request- or response-shaped dict from a cassette doc."""
    found: list[Violation] = []
    pairs = _normalize_headers(message.get("headers"))

    # (a) header NAMES
    for name, value in pairs:
        if name.lower() in _FORBIDDEN_HEADERS:
            found.append(
                Violation(
                    interaction_index=idx,
                    kind="header",
                    header_name=name,
                    snippet=_snippet_of(value),
                )
            )

    # (b) header VALUES (only surviving headers — ones whose names are not
    # in _FORBIDDEN_HEADERS; the others already flagged above).
    for name, value in pairs:
        if name.lower() in _FORBIDDEN_HEADERS:
            continue
        encoded = value.encode("utf-8", "surrogatepass")
        match = _first_pattern_match(encoded)
        if match is not None:
            pattern_pretty, matched_bytes = match
            found.append(
                Violation(
                    interaction_index=idx,
                    kind="header_value",
                    header_name=name,
                    pattern=pattern_pretty,
                    snippet=_snippet_of(value),
                )
            )

    # (c) BODY
    body = message.get("body")
    body_bytes = _body_to_bytes(body)
    if body_bytes is not None:
        match = _first_pattern_match(body_bytes)
        if match is not None:
            pattern_pretty, matched_bytes = match
            found.append(
                Violation(
                    interaction_index=idx,
                    kind=body_kind,
                    pattern=pattern_pretty,
                    snippet=_snippet_of(_safe_bytes_to_str(body_bytes)),
                )
            )
    return found


def _body_to_bytes(body: Any) -> bytes | None:
    """Coerce a cassette-doc body field to ``bytes`` for scanning. Pure."""
    if body is None:
        return None
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8", "surrogatepass")
    if isinstance(body, dict) and "string" in body:
        return _body_to_bytes(body["string"])
    return None


def _first_pattern_match(buf: bytes) -> tuple[str, bytes] | None:
    """Return ``(pattern_pretty, matched_bytes)`` for the first hit, else ``None``."""
    for pattern in _BODY_SECRET_PATTERNS:
        m = pattern.search(buf)
        if m is not None:
            return (pattern.pattern.decode("ascii", "replace"), m.group(0))
    return None


def _snippet_of(value: str) -> str:
    """Bound a snippet to 60 chars (~ ±20 around a typical match)."""
    if len(value) <= 60:
        return value
    return value[:60] + "…"


def _safe_bytes_to_str(b: bytes) -> str:
    return b.decode("utf-8", "replace")


def verify_cassette(path: Path) -> CassetteVerification:
    """Read + walk a YAML cassette. The ONLY impure function in this module.

    Total over the filesystem (AC-20): a non-existent path, an empty file,
    non-YAML content, and a cassette missing ``interactions`` each return a
    ``CassetteVerification`` carrying a single ``Violation(kind="unreadable")``.
    Never raises.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as exc:
        return CassetteVerification(
            violations=(
                Violation(
                    interaction_index=-1,
                    kind="unreadable",
                    snippet=f"could not read {path}: {type(exc).__name__}",
                ),
            )
        )

    if not text.strip():
        return CassetteVerification(
            violations=(
                Violation(
                    interaction_index=-1,
                    kind="unreadable",
                    snippet="empty cassette file",
                ),
            )
        )

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return CassetteVerification(
            violations=(
                Violation(
                    interaction_index=-1,
                    kind="unreadable",
                    snippet=f"yaml parse error: {type(exc).__name__}",
                ),
            )
        )

    return CassetteVerification(violations=_scan_cassette_doc(doc))
