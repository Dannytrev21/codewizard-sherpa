"""Phase 3 S1-01 AC-17 — Hypothesis totality + determinism + round-trip.

For each of the 13 str-backed parsers and ``parse_attempt_number``:

- **Totality:** the parser must return either ``Ok`` or ``Err`` for any drawn
  input — it must never raise an exception.
- **Determinism:** ``parser(s) == parser(s)`` for any drawn input — catches
  regex/Pydantic state leaks.
- **Round-trip identity (str parsers):** for inputs drawn from each parser's
  own regex, the parser returns ``Ok(value=NewType(s))``.

The negative regex strategies stay narrow on purpose — Hypothesis with
``st.text()`` already covers wide-cast fuzzing in the totality test.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.result import Err, Ok
from codegenie.types import parsers as P

# str-backed parsers only — AttemptNumber gets its own integer property test.
ALL_STR_PARSERS = [
    P.parse_plugin_id,
    P.parse_recipe_id,
    P.parse_transform_id,
    P.parse_workflow_id,
    P.parse_event_id,
    P.parse_cve_id,
    P.parse_package_id,
    P.parse_branch_name,
    P.parse_blob_digest,
    P.parse_registry_url,
    P.parse_signal_kind,
    P.parse_primitive_name,
    P.parse_transform_kind,
]


@pytest.mark.parametrize("parser", ALL_STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_total_function(parser, s):  # type: ignore[no-untyped-def]
    try:
        r = parser(s)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{parser.__name__}({s!r}) raised {type(e).__name__}: {e!r}")
    assert isinstance(r, (Ok, Err))


@pytest.mark.parametrize("parser", ALL_STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_deterministic(parser, s):  # type: ignore[no-untyped-def]
    assert parser(s) == parser(s)


@given(n=st.integers(min_value=-(2**31), max_value=2**31 - 1))
@settings(max_examples=50)
def test_attempt_number_total(n: int) -> None:
    r = P.parse_attempt_number(n)
    assert isinstance(r, (Ok, Err))


@given(n=st.integers(min_value=-(2**31), max_value=2**31 - 1))
@settings(max_examples=50)
def test_attempt_number_deterministic(n: int) -> None:
    assert P.parse_attempt_number(n) == P.parse_attempt_number(n)


# ---------------------------------------------------------------------------
# Round-trip identity for happy inputs (regex-drawn).
# ---------------------------------------------------------------------------


@given(s=st.from_regex(r"^CVE-\d{4}-\d{4,7}\Z", fullmatch=True))
@settings(max_examples=30)
def test_cve_id_round_trip(s: str) -> None:
    r = P.parse_cve_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[0-9a-f]{64}\Z", fullmatch=True))
@settings(max_examples=30)
def test_blob_digest_round_trip(s: str) -> None:
    r = P.parse_blob_digest(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[0-9a-f]{64}\Z", fullmatch=True))
@settings(max_examples=30)
def test_transform_id_round_trip(s: str) -> None:
    r = P.parse_transform_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}\Z", fullmatch=True))
@settings(max_examples=30)
def test_workflow_id_round_trip(s: str) -> None:
    r = P.parse_workflow_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}\Z", fullmatch=True))
@settings(max_examples=30)
def test_event_id_round_trip(s: str) -> None:
    r = P.parse_event_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[a-z][a-z0-9_]{0,30}\Z", fullmatch=True))
@settings(max_examples=30)
def test_signal_kind_round_trip(s: str) -> None:
    r = P.parse_signal_kind(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[a-z][a-z0-9_]{0,30}\Z", fullmatch=True))
@settings(max_examples=30)
def test_primitive_name_round_trip(s: str) -> None:
    r = P.parse_primitive_name(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[a-z][a-z0-9_]{0,30}\Z", fullmatch=True))
@settings(max_examples=30)
def test_transform_kind_round_trip(s: str) -> None:
    r = P.parse_transform_kind(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(s=st.from_regex(r"^[a-z][a-z0-9_-]{0,63}\Z", fullmatch=True))
@settings(max_examples=30)
def test_recipe_id_round_trip(s: str) -> None:
    r = P.parse_recipe_id(s)
    assert isinstance(r, Ok)
    assert r.value == s


@given(n=st.integers(min_value=1, max_value=1024))
@settings(max_examples=30)
def test_attempt_number_round_trip(n: int) -> None:
    r = P.parse_attempt_number(n)
    assert isinstance(r, Ok)
    assert r.value == n
