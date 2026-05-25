"""Phase-4 S3-04 AC-11 + AC-22 — real ``vcr.request.Request`` integration.

The unit suite uses a dict shim for the request shape; this file exercises
the sanitizer against the **actual** vcrpy ``Request`` type to pin the
contract (AC-22) and uses the real ``vcr_config`` fixture wiring to prove a
cassette miss under ``record_mode="none"`` is a hard failure (AC-11).
"""

from __future__ import annotations

import pytest
from vcr.request import Request as VcrRequest

from codegenie.fallback.cassette.sanitizer import (
    sanitize_request,
    sanitize_response,
)


def test_sanitize_accepts_real_vcr_request_strips_header_and_redacts_body() -> None:
    """AC-22: real ``vcr.request.Request`` round-trips with header dropped + body redacted."""
    req = VcrRequest(
        method="POST",
        uri="https://api.anthropic.com/v1/messages",
        body=b'{"api_key": "sk-ant-' + b"A" * 30 + b'"}',
        headers={
            "Authorization": "Bearer sk-ant-real-key-xyz",
            "User-Agent": "codegenie/0.4",
        },
    )
    out = sanitize_request(req)

    # Header name dropped (case-insensitive)
    header_names_lower = {k.lower() for k in out.headers}
    assert "authorization" not in header_names_lower
    assert "user-agent" in header_names_lower

    # Body redacted
    assert b"sk-ant-A" not in out.body
    assert b"[REDACTED]" in out.body

    # Input unchanged
    assert "Authorization" in req.headers
    assert b"sk-ant-A" in req.body


def test_sanitize_real_vcr_request_is_a_new_object() -> None:
    """AC-4 mutation discipline: returned object is not the same instance."""
    req = VcrRequest(
        method="POST",
        uri="https://api.anthropic.com/v1/messages",
        body=b"hello",
        headers={"User-Agent": "ok"},
    )
    out = sanitize_request(req)
    assert out is not req


def test_sanitize_response_dict_strips_set_cookie() -> None:
    """AC-5: cassette-doc response dict shape — Set-Cookie dropped."""
    resp = {
        "status": {"code": 200, "message": "OK"},
        "headers": {
            "Content-Type": ["application/json"],
            "Set-Cookie": ["session=secret"],
        },
        "body": {"string": b'{"id": "msg_123"}'},
    }
    out = sanitize_response(resp)
    keys_lower = {k.lower() for k in out["headers"]}
    assert "set-cookie" not in keys_lower
    assert "content-type" in keys_lower
    # Original unchanged
    assert "Set-Cookie" in resp["headers"]


def test_vcr_config_fixture_default_record_mode_is_none(vcr_config: dict) -> None:
    """AC-10 / AC-12: default ``record_mode`` is ``"none"`` without CODEGENIE_LIVE_LLM."""
    assert vcr_config["record_mode"] == "none"
    assert vcr_config["before_record_request"] is sanitize_request
    assert vcr_config["before_record_response"] is sanitize_response


def test_vcr_config_fixture_live_llm_flips_record_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-12: ``CODEGENIE_LIVE_LLM=1`` flips ``record_mode`` to ``"all"``.

    Constructs the fixture directly (not via pytest) so we can monkeypatch
    the env var without affecting the rest of the session.
    """
    monkeypatch.setenv("CODEGENIE_LIVE_LLM", "1")
    # Re-import the conftest function to re-run its env lookup.
    import importlib

    import tests.conftest as conftest_mod

    importlib.reload(conftest_mod)
    cfg = conftest_mod.vcr_config.__wrapped__()  # call the underlying function
    assert cfg["record_mode"] == "all"


def test_cassette_miss_under_record_mode_none_is_a_hard_failure(tmp_path, monkeypatch) -> None:
    """AC-11: ``record_mode="none"`` + no matching cassette → hard fail.

    Behaviour-level: we don't pin a third-party error string (vcrpy's
    ``CannotOverwriteExistingCassetteException`` wording is outside this
    story's ownership). We pin that a network call without a cassette
    raises *some* vcrpy-shaped exception when the cassette layer is engaged.
    """
    import vcr  # type: ignore[import-untyped]

    my_vcr = vcr.VCR(
        record_mode="none",
        cassette_library_dir=str(tmp_path),
        before_record_request=sanitize_request,
        before_record_response=sanitize_response,
    )

    # We assert on the in-scope behaviour: under record_mode="none", *any*
    # un-cassetted HTTP attempt raises before reaching the network. Use
    # urllib (stdlib) so we don't need a third-party HTTP client.
    import urllib.request

    from vcr.errors import CannotOverwriteExistingCassetteException

    with my_vcr.use_cassette("missing.yaml"):
        with pytest.raises(CannotOverwriteExistingCassetteException):
            urllib.request.urlopen("http://192.0.2.1/")  # noqa: S310 — guarded by vcr
