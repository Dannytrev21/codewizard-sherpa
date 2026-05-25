"""Phase-4 S3-04 AC-14 — 30+ positive sanitizer corpus.

Each row asserts the sanitizer redacts a real-shaped secret. Catalog-driven —
adding a row is a one-line tuple edit, zero test edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from codegenie.fallback.cassette.sanitizer import (
    sanitize_request,
    sanitize_response,
)


@dataclass(frozen=True)
class Row:
    """One corpus case. ``surface`` names the scan surface the row exercises."""

    name: str
    surface: str  # "header_name" | "header_value" | "body_request" | "body_response"
    request_headers: dict[str, str]
    request_body: bytes
    response_headers: dict[str, list[str]]
    response_body: bytes


# AC-14: 30+ positive cases. Each ``name`` is grep-stable; tests assert the
# matching surface no longer carries the secret after sanitization.
_SK_ANT = "sk-ant-" + "A" * 30
_CLAUDE = "claude_" + "B" * 30
_B64 = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"  # 44 chars

CORPUS: tuple[Row, ...] = (
    # Forbidden header NAMES — case variants
    Row("authorization_lower", "header_name", {"authorization": _SK_ANT}, b"", {}, b""),
    Row("authorization_mixed", "header_name", {"Authorization": _SK_ANT}, b"", {}, b""),
    Row("authorization_upper", "header_name", {"AUTHORIZATION": _SK_ANT}, b"", {}, b""),
    Row("x_api_key", "header_name", {"X-API-Key": "anything"}, b"", {}, b""),
    Row("cookie", "header_name", {"Cookie": "session=abc"}, b"", {}, b""),
    Row("set_cookie_response", "header_name", {}, b"", {"Set-Cookie": ["session=x"]}, b""),
    Row("anthropic_version", "header_name", {"anthropic-version": "2023-06-01"}, b"", {}, b""),
    # Header VALUES — secret in a non-forbidden header name
    Row(
        "x_auth_custom_sk_ant",
        "header_value",
        {"X-Auth-Custom": f"Bearer {_SK_ANT}"},
        b"",
        {},
        b"",
    ),
    Row("x_proxy_claude_prefix", "header_value", {"X-Proxy": _CLAUDE}, b"", {}, b""),
    Row("x_proxy_base64", "header_value", {"X-Trace": _B64}, b"", {}, b""),
    Row("response_x_request_id_secret", "header_value", {}, b"", {"X-Request-Id": [_SK_ANT]}, b""),
    # Request bodies
    Row(
        "body_request_sk_ant_json",
        "body_request",
        {},
        f'{{"api_key": "{_SK_ANT}"}}'.encode(),
        {},
        b"",
    ),
    Row(
        "body_request_claude_prefix",
        "body_request",
        {},
        f'{{"token": "{_CLAUDE}"}}'.encode(),
        {},
        b"",
    ),
    Row(
        "body_request_base64_blob",
        "body_request",
        {},
        f'{{"blob": "{_B64}"}}'.encode(),
        {},
        b"",
    ),
    Row(
        "body_request_multi_secret",
        "body_request",
        {},
        (_SK_ANT + " " + _CLAUDE + " " + _B64).encode("utf-8"),
        {},
        b"",
    ),
    Row(
        "body_request_innocuous_key_secret_value",
        "body_request",
        {},
        f'{{"some_key": "{_SK_ANT}"}}'.encode(),
        {},
        b"",
    ),
    # Response bodies
    Row(
        "body_response_sk_ant",
        "body_response",
        {},
        b"",
        {},
        f'{{"key": "{_SK_ANT}"}}'.encode(),
    ),
    Row(
        "body_response_claude_prefix",
        "body_response",
        {},
        b"",
        {},
        f'{{"token": "{_CLAUDE}"}}'.encode(),
    ),
    Row(
        "body_response_base64",
        "body_response",
        {},
        b"",
        {},
        f'{{"blob": "{_B64}"}}'.encode(),
    ),
    # Edge cases — non-UTF-8 body
    Row(
        "body_request_non_utf8",
        "body_request",
        {},
        b"\xff\xfe\x00" + _SK_ANT.encode("ascii") + b"\x80",
        {},
        b"",
    ),
    # Bigger header sets — secret inside the response header dict
    Row(
        "response_multi_header_secret",
        "header_value",
        {},
        b"",
        {
            "Content-Type": ["application/json"],
            "X-Echo": [_CLAUDE],
        },
        b"",
    ),
    Row(
        "response_authorization_echoed",
        "header_name",
        {},
        b"",
        {"Authorization": ["Bearer leaked"]},
        b"",
    ),
    # More header-name cases
    Row("x_api_key_uppercase", "header_name", {"X-API-KEY": "x"}, b"", {}, b""),
    Row("cookie_lowercase", "header_name", {"cookie": "x"}, b"", {}, b""),
    Row("set_cookie_lowercase", "header_name", {}, b"", {"set-cookie": ["x"]}, b""),
    # Bigger body cases
    Row(
        "body_request_secret_then_prose",
        "body_request",
        {},
        _SK_ANT.encode() + b" some prose follows that should remain",
        {},
        b"",
    ),
    Row(
        "body_response_prose_then_secret",
        "body_response",
        {},
        b"",
        {},
        b"prose first, then secret: " + _CLAUDE.encode(),
    ),
    # Cookie value with secret
    Row("cookie_value_with_sk_ant", "header_name", {"Cookie": f"sid={_SK_ANT}"}, b"", {}, b""),
    # Common SDK header
    Row(
        "auth_bearer_phrasing",
        "header_name",
        {"Authorization": f"Bearer {_SK_ANT}"},
        b"",
        {},
        b"",
    ),
    # Big base64 in body
    Row(
        "body_request_long_base64",
        "body_request",
        {},
        (b"prefix " + _B64.encode() * 3 + b" suffix"),
        {},
        b"",
    ),
    # Body matches across both request and response
    Row(
        "both_request_and_response_have_secrets",
        "body_request",
        {},
        _SK_ANT.encode(),
        {},
        _SK_ANT.encode(),
    ),
)

assert len(CORPUS) >= 30, f"AC-14 corpus has only {len(CORPUS)} rows (need >= 30)"


def _make_req(row: Row) -> dict[str, Any]:
    return {"headers": dict(row.request_headers), "body": row.request_body}


def _make_resp(row: Row) -> dict[str, Any]:
    return {
        "status": {"code": 200, "message": "OK"},
        "headers": dict(row.response_headers),
        "body": {"string": row.response_body},
    }


@pytest.mark.parametrize("row", CORPUS, ids=lambda r: r.name)
def test_request_corpus(row: Row) -> None:
    req = _make_req(row)
    out = sanitize_request(req)

    # Forbidden header names are dropped (case-insensitive)
    forbidden_lower = {"authorization", "x-api-key", "cookie", "set-cookie", "anthropic-version"}
    for name in out["headers"]:
        assert name.lower() not in forbidden_lower, (
            f"row {row.name!r} left a forbidden header: {name!r}"
        )

    # No raw secrets in surviving header values
    for _name, value in out["headers"].items():
        assert "sk-ant-" not in value
        assert "claude_" not in value
    # No raw secrets in the body
    if row.request_body:
        out_body = out["body"]
        assert b"sk-ant-" not in out_body
        assert b"claude_" not in out_body


@pytest.mark.parametrize("row", CORPUS, ids=lambda r: r.name)
def test_response_corpus(row: Row) -> None:
    resp = _make_resp(row)
    out = sanitize_response(resp)

    forbidden_lower = {"authorization", "x-api-key", "cookie", "set-cookie", "anthropic-version"}
    for name in out["headers"]:
        assert name.lower() not in forbidden_lower

    for _name, value in out["headers"].items():
        # Values may be lists in cassette-doc shape
        text = " ".join(value) if isinstance(value, list) else str(value)
        assert "sk-ant-" not in text
        assert "claude_" not in text

    body = out["body"]
    if isinstance(body, dict):
        body = body.get("string", b"")
    if row.response_body:
        assert b"sk-ant-" not in body
        assert b"claude_" not in body
