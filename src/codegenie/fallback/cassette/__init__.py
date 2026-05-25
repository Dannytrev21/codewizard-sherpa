"""Phase-4 S3-04 — ``CassetteSanitizer`` package.

Layer 1 of ADR-0014's cassette-discipline stack: a pure-function sanitizer
that strips secret HTTP headers and body-scans for shaped secrets, plus
``verify_cassette`` — the walker S3-05's CI scanner reuses.

The package exposes the three hook-shaped public functions (sanitize_request,
sanitize_response, verify_cassette) plus the :class:`CassetteVerification` /
:class:`Violation` diagnostic models. The two ``_FORBIDDEN_HEADERS`` /
``_BODY_SECRET_PATTERNS`` constants are private; their identities are pinned
by the AC-2 / AC-3 tests, not by re-export.

ADR-0014 §Decision: the sanitizer is the load-bearing FIRST layer (sanitize at
record); the CI scanner (S3-05) is the backstop. A secret that escapes the
sanitizer reaches the scanner; a secret that escapes both reaches the lock
file. Depth-of-defense ordering matters.
"""

from __future__ import annotations

from codegenie.fallback.cassette.manifest import (
    LockfileMalformed,
    LockfileMalformedDetail,
    compute_cassette_digest,
    load_lockfile,
    rebuild_lockfile,
)
from codegenie.fallback.cassette.sanitizer import (
    CassetteVerification,
    Violation,
    sanitize_request,
    sanitize_response,
    verify_cassette,
)

__all__ = (
    "CassetteVerification",
    "LockfileMalformed",
    "LockfileMalformedDetail",
    "Violation",
    "compute_cassette_digest",
    "load_lockfile",
    "rebuild_lockfile",
    "sanitize_request",
    "sanitize_response",
    "verify_cassette",
)
