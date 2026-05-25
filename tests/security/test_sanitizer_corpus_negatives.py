"""Phase-4 S3-04 AC-15 — innocuous corpus: sanitizer must NOT over-redact.

Pinned negative control. If a row here ever starts redacting, the catalog has
drifted into a false-positive — investigate before relaxing.
"""

from __future__ import annotations

from typing import Any

import pytest

from codegenie.fallback.cassette.sanitizer import (
    sanitize_request,
    sanitize_response,
)

# Each row is (name, headers, body). All MUST round-trip unchanged.
INNOCUOUS_REQUESTS: tuple[tuple[str, dict[str, str], bytes], ...] = (
    ("plain_user_agent", {"User-Agent": "codegenie/0.4"}, b""),
    ("plain_content_type", {"Content-Type": "application/json"}, b""),
    ("plain_accept", {"Accept": "application/json"}, b""),
    ("plain_user_agent_with_body", {"User-Agent": "ok"}, b"hello world"),
    ("short_alphanumeric_body", {}, b"abc123def"),
    ("json_no_secret", {}, b'{"hello": "world", "count": 42}'),
    ("prose_body", {}, b"the quick brown fox jumps over the lazy dog"),
    ("empty_body", {}, b""),
    ("none_body", {}, b""),
    ("short_base64_below_threshold", {}, b"QUFBQUFB"),  # 8 chars; < 40 threshold
    ("hyphenated_no_secret", {}, b"this-is-an-innocuous-hyphenated-string"),
    ("xml_payload", {}, b"<root><name>value</name></root>"),
    ("path_like_short", {"X-Trace": "abc/def/ghi"}, b""),
    ("query_string_body", {}, b"a=1&b=2&c=hello"),
    ("emoji_body", {}, "hello 🦊 world".encode()),
)


@pytest.mark.parametrize(
    "name,headers,body",
    INNOCUOUS_REQUESTS,
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_innocuous_request_is_unchanged(name: str, headers: dict[str, str], body: bytes) -> None:
    req: dict[str, Any] = {"headers": dict(headers), "body": body}
    out = sanitize_request(req)
    assert out["headers"] == headers
    assert out["body"] == body


@pytest.mark.parametrize(
    "name,headers,body",
    INNOCUOUS_REQUESTS,
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_innocuous_response_is_unchanged(name: str, headers: dict[str, str], body: bytes) -> None:
    resp: dict[str, Any] = {
        "status": {"code": 200, "message": "OK"},
        "headers": {k: [v] for k, v in headers.items()},
        "body": {"string": body},
    }
    out = sanitize_response(resp)
    # List-valued cassette-doc response headers must round-trip
    for k, v in headers.items():
        assert out["headers"][k] == [v]
    assert out["body"]["string"] == body
