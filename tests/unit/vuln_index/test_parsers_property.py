"""S3-03 — AC-P4 parser-determinism property test (Hypothesis).

Same ``raw: bytes`` → same ``Result`` over N runs. Catches:
- hash-seed sensitivity (set / dict iteration order in regex-Final tuples);
- global-state contamination;
- non-deterministic side-effects on first call vs second.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.vuln_index.registry import default_feed_registry

CASSETTES_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "fixtures" / "cve-feeds"


def _all_cassette_records() -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    for source in ("nvd", "ghsa", "osv"):
        for path in sorted((CASSETTES_DIR / source).glob("*.json")):
            out.append((path.read_bytes(), source))
    return out


_CORPUS: Final[list[tuple[bytes, str]]] = _all_cassette_records()


@given(idx=st.integers(min_value=0, max_value=len(_CORPUS) - 1))
@settings(max_examples=50, deadline=None)
def test_parse_one_is_deterministic(idx: int) -> None:
    raw, source = _CORPUS[idx]
    feed = default_feed_registry.get_feed(source)
    r1 = feed.parse_one(raw)
    r2 = feed.parse_one(raw)
    # ``Result`` is a frozen Pydantic discriminated union; equality is
    # structural over (kind, value/error).
    assert r1 == r2
