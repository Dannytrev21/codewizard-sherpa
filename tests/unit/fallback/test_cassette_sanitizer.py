"""Phase-4 S3-04 — ``CassetteSanitizer`` unit tests.

Red-phase coverage of the public sanitizer + verifier contract:

- AC-2 / AC-3 — module-level Final catalogs (shape + types).
- AC-4 / AC-5 — three scan surfaces, new object (no mutation).
- AC-6 — Hypothesis idempotence biased to the redaction path.
- AC-8 / AC-9 — ``verify_cassette`` flags header / body / clean / empty.
- AC-19 — non-UTF-8 / binary body never raises.
- AC-20 — ``verify_cassette`` is total over the filesystem.
- AC-21 — ``_scan_cassette_doc`` exercised on an in-memory dict.

Integration with the real ``vcr.request.Request`` lives in
:mod:`tests/integration/fallback/test_cassette_sanitizer_real_vcr` (AC-22).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from codegenie.fallback.cassette.sanitizer import (
    _BODY_SECRET_PATTERNS,
    _FORBIDDEN_HEADERS,
    CassetteVerification,
    Violation,
    _scan_cassette_doc,
    sanitize_request,
    sanitize_response,
    verify_cassette,
)

# --- Fixtures + shims -----------------------------------------------------


def _make_request(headers: dict[str, str], body: bytes = b"") -> dict[str, Any]:
    """A dict shim for vcr.request.Request — the integration test uses the real type."""
    return {"headers": dict(headers), "body": body}


def _make_response(
    headers: dict[str, Any] | None = None,
    body_string: bytes = b"",
) -> dict[str, Any]:
    """Cassette-doc shape for a recorded response."""
    return {
        "status": {"code": 200, "message": "OK"},
        "headers": dict(headers or {}),
        "body": {"string": body_string},
    }


# --- AC-1 / AC-2 / AC-3 — module-level catalogs ---------------------------


def test_forbidden_headers_exact_set() -> None:
    """AC-2: the forbidden-header set is exactly the five names from ADR-0014."""
    assert _FORBIDDEN_HEADERS == frozenset(
        {"authorization", "x-api-key", "cookie", "set-cookie", "anthropic-version"}
    )


def test_body_secret_patterns_are_bytes_typed() -> None:
    """AC-3: ``_BODY_SECRET_PATTERNS`` is a single tuple of bytes patterns."""
    assert isinstance(_BODY_SECRET_PATTERNS, tuple)
    assert len(_BODY_SECRET_PATTERNS) == 3
    for pat in _BODY_SECRET_PATTERNS:
        assert isinstance(pat, re.Pattern)
        # Bytes-typed: pattern.pattern is bytes, not str.
        assert isinstance(pat.pattern, bytes), f"Pattern {pat.pattern!r} must be bytes-typed"


def test_body_secret_patterns_cover_three_shapes() -> None:
    """AC-3: three rows — sk-ant prefix, claude_ prefix, 40+-char base64."""
    payloads = [
        b"sk-ant-" + b"A" * 30,
        b"claude_" + b"B" * 30,
        b"QUFBQ" + b"C" * 50 + b"==",
    ]
    for p in payloads:
        assert any(pat.search(p) for pat in _BODY_SECRET_PATTERNS), f"No pattern matched {p!r}"


# --- AC-4 — sanitize_request: three surfaces, no mutation -----------------


@pytest.mark.parametrize("h", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_header_stripped_case_insensitively(h: str) -> None:
    req = _make_request({h: "Bearer sk-ant-xyz", "User-Agent": "ok"})
    out = sanitize_request(req)
    assert h not in out["headers"]
    assert "User-Agent" in out["headers"]


@pytest.mark.parametrize(
    "header",
    ["X-API-Key", "Cookie", "Set-Cookie", "anthropic-version", "x-api-key"],
)
def test_each_forbidden_header_name_dropped(header: str) -> None:
    req = _make_request({header: "secret"})
    out = sanitize_request(req)
    assert all(k.lower() != header.lower() for k in out["headers"])


def test_body_redacts_sk_ant_pattern() -> None:
    body = b'{"api_key": "sk-ant-real-looking-key-1234567890abcdef"}'
    req = _make_request({}, body=body)
    out = sanitize_request(req)
    assert b"sk-ant-real-looking-key" not in out["body"]
    assert b"[REDACTED]" in out["body"]


def test_body_redacts_all_occurrences() -> None:
    """Kills a ``replace``-first-match impl; only ``re.sub`` (global) passes."""
    body = b"first: sk-ant-" + b"A" * 30 + b" second: sk-ant-" + b"B" * 30 + b" third: " + b"Q" * 60
    out = sanitize_request(_make_request({}, body=body))
    assert b"sk-ant-A" not in out["body"]
    assert b"sk-ant-B" not in out["body"]
    assert out["body"].count(b"[REDACTED]") == 3


def test_secret_in_non_forbidden_header_value_is_redacted() -> None:
    """AC-4(b): scan surviving header *values*, not just header names."""
    req = _make_request({"X-Auth-Custom": "Bearer sk-ant-" + "A" * 30})
    out = sanitize_request(req)
    assert "X-Auth-Custom" in out["headers"]
    assert "sk-ant-" not in out["headers"]["X-Auth-Custom"]
    assert "[REDACTED]" in out["headers"]["X-Auth-Custom"]


def test_sanitize_request_does_not_mutate_input() -> None:
    """AC-4: input byte-for-byte unchanged after the call."""
    req = _make_request(
        {"Authorization": "Bearer sk-ant-xyz", "User-Agent": "codegenie"},
        body=b"sk-ant-" + b"X" * 30,
    )
    before = copy.deepcopy(req)
    sanitize_request(req)
    assert req == before


def test_innocuous_input_unchanged() -> None:
    """AC-15 sibling: no over-redaction on innocuous input."""
    req = _make_request({"User-Agent": "codegenie/0.4"}, body=b"hello world")
    out = sanitize_request(req)
    assert out["headers"] == {"User-Agent": "codegenie/0.4"}
    assert out["body"] == b"hello world"


def test_redacted_marker_is_stable() -> None:
    """Notes: re-sanitizing a body containing literal ``[REDACTED]`` is a no-op."""
    body = b"prefix [REDACTED] suffix"
    out = sanitize_request(_make_request({}, body=body))
    assert out["body"] == body
    # And re-sanitizing one that DID get redacted doesn't double-encode.
    body2 = b"secret: sk-ant-" + b"A" * 30
    once = sanitize_request(_make_request({}, body=body2))
    twice = sanitize_request(once)
    assert once["body"] == twice["body"]


def test_redacts_non_utf8_body() -> None:
    """AC-19: arbitrary bytes (including invalid UTF-8) never crash."""
    body = b"\xff\xfe\x00sk-ant-" + b"A" * 30 + b"\x80\x81"
    out = sanitize_request(_make_request({}, body=body))
    assert b"sk-ant-" not in out["body"]
    assert b"[REDACTED]" in out["body"]


def test_sanitize_request_none_passes_through() -> None:
    """vcrpy: returning ``None`` drops the interaction. Don't crash on it."""
    assert sanitize_request(None) is None


# --- AC-5 — sanitize_response: mirror with response shape ----------------


def test_response_set_cookie_dropped() -> None:
    resp = _make_response(
        headers={"Content-Type": ["application/json"], "Set-Cookie": ["session=abc"]},
        body_string=b'{"ok": true}',
    )
    out = sanitize_response(resp)
    keys_lower = {str(k).lower() for k in out["headers"]}
    assert "set-cookie" not in keys_lower
    assert "content-type" in keys_lower


def test_response_body_redacts_pattern() -> None:
    resp = _make_response(body_string=b'{"key":"claude_' + b"Z" * 30 + b'"}')
    out = sanitize_response(resp)
    assert b"claude_Z" not in out["body"]["string"]
    assert b"[REDACTED]" in out["body"]["string"]


def test_sanitize_response_does_not_mutate_input() -> None:
    resp = _make_response(
        headers={"Set-Cookie": ["session=secret"]},
        body_string=b"sk-ant-" + b"A" * 30,
    )
    before = copy.deepcopy(resp)
    sanitize_response(resp)
    assert resp == before


# --- AC-6 — Hypothesis idempotence biased to the redaction path -----------


_secret_bytes = st.sampled_from(
    [
        b"sk-ant-" + b"A" * 30,
        b"claude_" + b"B" * 30,
        b"QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB",  # 44-char base64
    ]
)
_body_bias = st.one_of(
    st.binary(max_size=200),
    st.builds(lambda j, s: j + s, st.binary(max_size=100), _secret_bytes),
    st.builds(lambda s, j: s + j, _secret_bytes, st.binary(max_size=100)),
)
_header_value_bias = st.one_of(
    st.text(min_size=0, max_size=80),
    st.builds(
        lambda prefix, secret: f"{prefix} {secret.decode('ascii', 'replace')}",
        st.text(min_size=0, max_size=40),
        _secret_bytes,
    ),
)
_headers_bias = st.dictionaries(
    keys=st.sampled_from(
        ["Authorization", "User-Agent", "X-Custom", "Content-Type", "X-Auth-Custom"]
    ),
    values=_header_value_bias,
    max_size=6,
)


@given(headers=_headers_bias, body=_body_bias)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@example(
    headers={"Authorization": "Bearer sk-ant-" + "A" * 30},
    body=b"sk-ant-" + b"A" * 30,
)
@example(
    headers={"X-Auth-Custom": "claude_" + "B" * 30},
    body=b"claude_" + b"B" * 30,
)
@example(
    headers={"X-Custom": "ok"},
    body=b"QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB",
)
def test_sanitize_request_is_idempotent(headers: dict[str, str], body: bytes) -> None:
    req = _make_request(headers, body)
    once = sanitize_request(req)
    twice = sanitize_request(once)
    assert once == twice


@given(headers=_headers_bias, body=_body_bias)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@example(
    headers={"Set-Cookie": "session=secret"},
    body=b"sk-ant-" + b"A" * 30,
)
def test_sanitize_response_is_idempotent(headers: dict[str, str], body: bytes) -> None:
    # Construct cassette-doc shape with list-valued headers (vcrpy norm).
    resp = _make_response({k: [v] for k, v in headers.items()}, body_string=body)
    once = sanitize_response(resp)
    twice = sanitize_response(once)
    assert once == twice


# --- AC-8 / AC-9 — verify_cassette --------------------------------------


def test_verify_cassette_flags_unredacted_authorization(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "interactions:\n"
        "  - request:\n"
        "      headers:\n"
        "        Authorization: Bearer sk-ant-leak\n"
        "      body: null\n"
        "    response:\n"
        "      status:\n"
        "        code: 200\n"
        "        message: OK\n"
        "      headers: {}\n"
        "      body:\n"
        "        string: ok\n"
    )
    v = verify_cassette(bad)
    assert v.passed is False
    assert any(viol.kind == "header" for viol in v.violations)


def test_verify_cassette_flags_body_violation_request(tmp_path: Path) -> None:
    body = "sk-ant-" + "A" * 30
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "interactions:\n"
        f"  - request:\n"
        "      headers: {}\n"
        f"      body: '{body}'\n"
        "    response:\n"
        "      status:\n"
        "        code: 200\n"
        "        message: OK\n"
        "      headers: {}\n"
        "      body:\n"
        "        string: ok\n"
    )
    v = verify_cassette(bad)
    assert v.passed is False
    assert any(viol.kind == "body_request" for viol in v.violations)


def test_verify_cassette_flags_body_violation_response(tmp_path: Path) -> None:
    body = "claude_" + "B" * 30
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "interactions:\n"
        "  - request:\n"
        "      headers: {}\n"
        "      body: null\n"
        "    response:\n"
        "      status:\n"
        "        code: 200\n"
        "        message: OK\n"
        "      headers: {}\n"
        "      body:\n"
        f"        string: '{body}'\n"
    )
    v = verify_cassette(bad)
    assert v.passed is False
    assert any(viol.kind == "body_response" for viol in v.violations)


def test_verify_cassette_clean_passes(tmp_path: Path) -> None:
    clean = tmp_path / "clean.yaml"
    clean.write_text(
        "interactions:\n"
        "  - request:\n"
        "      headers:\n"
        "        User-Agent: codegenie/0.4\n"
        "      body: hello\n"
        "    response:\n"
        "      status:\n"
        "        code: 200\n"
        "        message: OK\n"
        "      headers:\n"
        "        Content-Type:\n"
        "          - application/json\n"
        "      body:\n"
        "        string: world\n"
    )
    v = verify_cassette(clean)
    assert v.passed is True
    assert v.violations == ()


def test_verify_cassette_empty_interactions_passes(tmp_path: Path) -> None:
    empty_int = tmp_path / "empty.yaml"
    empty_int.write_text("interactions: []\n")
    v = verify_cassette(empty_int)
    assert v.passed is True
    assert v.violations == ()


def test_passed_is_a_derived_property_not_a_field() -> None:
    """AC-9: ``passed=True`` alongside non-empty ``violations`` is unrepresentable."""
    cv = CassetteVerification(
        violations=(
            Violation(
                interaction_index=0,
                kind="header",
                header_name="Authorization",
                snippet="…",
            ),
        )
    )
    assert cv.passed is False
    # Cannot pass ``passed`` directly — extra="forbid".
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CassetteVerification(violations=(), passed=True)  # type: ignore[call-arg]


def test_violation_kind_field_coupling() -> None:
    """AC-9: a nonsense Violation cannot be constructed."""
    # header kind requires header_name
    with pytest.raises(ValueError):
        Violation(interaction_index=0, kind="header", snippet="x")
    # body_* kind requires pattern
    with pytest.raises(ValueError):
        Violation(interaction_index=0, kind="body_request", snippet="x")


# --- AC-20 — verify_cassette is total over the filesystem ----------------


def test_verify_cassette_total_nonexistent(tmp_path: Path) -> None:
    v = verify_cassette(tmp_path / "missing.yaml")
    assert v.passed is False
    assert len(v.violations) == 1
    assert v.violations[0].kind == "unreadable"


def test_verify_cassette_total_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    v = verify_cassette(p)
    assert v.passed is False
    assert v.violations[0].kind == "unreadable"


def test_verify_cassette_total_not_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("{this is not yaml: [unclosed\n")
    v = verify_cassette(p)
    assert v.passed is False
    assert v.violations[0].kind == "unreadable"


def test_verify_cassette_total_missing_interactions_key(tmp_path: Path) -> None:
    p = tmp_path / "wrong.yaml"
    p.write_text("version: 1\n")
    v = verify_cassette(p)
    assert v.passed is False
    assert v.violations[0].kind == "unreadable"


# --- AC-21 — _scan_cassette_doc pure walker -----------------------------


def test_scan_cassette_doc_is_pure_in_memory() -> None:
    """AC-21: ``_scan_cassette_doc`` accepts an in-memory dict — no temp file."""
    doc = {
        "interactions": [
            {
                "request": {
                    "headers": {"Authorization": "Bearer x"},
                    "body": None,
                },
                "response": {
                    "headers": {},
                    "body": {"string": "ok"},
                },
            }
        ]
    }
    violations = _scan_cassette_doc(doc)
    assert any(v.kind == "header" and v.header_name == "Authorization" for v in violations)


def test_scan_cassette_doc_empty_dict() -> None:
    """A non-cassette dict surfaces 'unreadable', not a crash."""
    violations = _scan_cassette_doc({"version": 1})
    assert len(violations) == 1
    assert violations[0].kind == "unreadable"


def test_scan_cassette_doc_clean_returns_empty_tuple() -> None:
    doc = {
        "interactions": [
            {
                "request": {"headers": {"User-Agent": "ok"}, "body": "hello"},
                "response": {
                    "headers": {"Content-Type": ["application/json"]},
                    "body": {"string": "world"},
                },
            }
        ]
    }
    assert _scan_cassette_doc(doc) == ()
