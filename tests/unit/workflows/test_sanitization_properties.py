"""Phase 6 S1-01 AC-5 — sanitization-by-construction Hypothesis properties.

The :class:`EvidenceRef` smart constructor enforces three rejection classes
*at construction time*:

1. Absolute paths (POSIX or Windows drive-letter), ``..`` components, null
   bytes, control chars.
2. Secret-shaped substrings — the same canonical regex set used by
   :data:`codegenie.coordinator.validator.SECRET_FIELD_PATTERN` and the JWT /
   AWS / GitHub-PAT cleartext patterns in :mod:`codegenie.output.sanitizer`.
3. ``failure_modes`` entries matching ``^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$``
   (Phase 1 ADR-0007); anything else is rejected.

Mutation thinking: a ``regex.search`` swapped for ``regex.fullmatch`` would
let ``"foo /etc/passwd"`` slip through — the property-test substring draws
target exactly that.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from codegenie.types.identifiers import (
    AttemptNumber,
    ErrorId,
    TokenCount,
)
from codegenie.types.parsers import parse_blob_digest, parse_sut_digest, parse_vuln_case_id
from codegenie.workflows import VulnRemediationResult
from codegenie.workflows.vuln_sut import CostSummary, EvidenceRef, GateSummary

# --- Helpers ---------------------------------------------------------------


def _result_with_evidence(refs: tuple[EvidenceRef, ...]) -> VulnRemediationResult:
    return VulnRemediationResult(
        case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
        terminal_state="completed",
        patch_digest=parse_blob_digest("a" * 64).unwrap(),
        gate_summary=GateSummary(attempts=AttemptNumber(1), last_outcome="pass"),
        failure_modes=(),
        cost_summary=CostSummary(
            tokens_in=TokenCount(0),
            tokens_out=TokenCount(0),
            cassette_replays=0,
        ),
        evidence_references=refs,
        sut_digest=parse_sut_digest("blake3:" + "f" * 64).unwrap(),
    )


def _result_with_failure_modes(modes: tuple[str, ...]) -> VulnRemediationResult:
    """Construct a non-completed Result with arbitrary failure_modes strings."""
    typed = tuple(ErrorId(m) for m in modes)
    return VulnRemediationResult(
        case_id=parse_vuln_case_id("01HXX00000000000000000000Z").unwrap(),
        terminal_state="failed_unrecoverable",
        patch_digest=None,
        gate_summary=GateSummary(attempts=AttemptNumber(1), last_outcome="fail_terminal"),
        failure_modes=typed,
        cost_summary=CostSummary(
            tokens_in=TokenCount(0),
            tokens_out=TokenCount(0),
            cassette_replays=0,
        ),
        evidence_references=(),
        sut_digest=parse_sut_digest("blake3:" + "f" * 64).unwrap(),
    )


# --- AC-5 property 1 — absolute-path rejection ----------------------------


@given(st.text(min_size=1, max_size=64).filter(lambda s: s.startswith("/")))
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=50)
def test_ac5_evidence_ref_rejects_absolute_unix_paths(s: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _result_with_evidence((EvidenceRef(ref=s),))
    detail = str(exc_info.value)
    assert "EvidenceRef" in detail, "AC-5: rejection must name EvidenceRef in directive"


@pytest.mark.parametrize(
    "bad",
    [
        "/etc/passwd",
        "C:\\Windows\\System32",
        "../parent/escape",
        "subdir/../escape",
        "good/path\x00null",
        "control\x01char",
    ],
)
def test_ac5_evidence_ref_rejects_known_dangerous_paths(bad: str) -> None:
    with pytest.raises(ValidationError):
        _result_with_evidence((EvidenceRef(ref=bad),))


def test_ac5_evidence_ref_rejection_quotes_offending_value() -> None:
    """Directive must name the rejected substring so the message is actionable."""
    with pytest.raises(ValidationError) as exc_info:
        _result_with_evidence((EvidenceRef(ref="/etc/passwd"),))
    detail = str(exc_info.value)
    assert "/etc/passwd" in detail, (
        "AC-5: rejection must include the rejected path in the directive."
    )


# --- AC-5 property 2 — secret-shape rejection -----------------------------


_SECRET_SHAPED_NAMES = ("GITHUB_TOKEN", "API_KEY", "DB_PASSWORD", "SESSION_SECRET", "JWT_TOKEN")


@given(
    st.sampled_from(_SECRET_SHAPED_NAMES),
    st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=0,
        max_size=20,
    ),
)
@settings(max_examples=50)
def test_ac5_evidence_ref_rejects_secret_shaped_substrings(name: str, suffix: str) -> None:
    candidate = f"{name}={suffix}"
    with pytest.raises(ValidationError):
        _result_with_evidence((EvidenceRef(ref=candidate),))


@pytest.mark.parametrize(
    "cleartext",
    [
        "ghp_" + "A" * 36,
        "AKIA" + "A" * 16,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmb28ifQ.signature_part_xx",
        "npm_" + "A" * 36,
    ],
)
def test_ac5_evidence_ref_rejects_cleartext_secret_patterns(cleartext: str) -> None:
    with pytest.raises(ValidationError):
        _result_with_evidence((EvidenceRef(ref=cleartext),))


def test_ac5_evidence_ref_directive_names_github_token() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _result_with_evidence((EvidenceRef(ref="GITHUB_TOKEN=ghp_" + "A" * 36),))
    detail = str(exc_info.value)
    assert "GITHUB_TOKEN" in detail or "secret" in detail.lower()


# --- AC-5 property 3 — failure_modes ErrorId format -----------------------


@given(
    st.text(min_size=1, max_size=64).filter(
        lambda s: not __import__("re").fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", s)
    )
)
@settings(suppress_health_check=[HealthCheck.filter_too_much], max_examples=50)
def test_ac5_failure_modes_rejects_non_phase1_error_id(s: str) -> None:
    assume(s != "")
    with pytest.raises(ValidationError):
        _result_with_failure_modes((s,))


@pytest.mark.parametrize(
    "bad",
    [
        "no_dot",
        "UPPER.case",
        "trailing.",
        ".leading",
        "two..dots",
        "with space.x",
        "1starts.numeric",
    ],
)
def test_ac5_failure_modes_rejects_specific_bad_error_ids(bad: str) -> None:
    with pytest.raises(ValidationError):
        _result_with_failure_modes((bad,))


def test_ac5_failure_modes_accepts_valid_error_id() -> None:
    r = _result_with_failure_modes(("recipe.no_match", "sandbox.timeout"))
    assert len(r.failure_modes) == 2


# --- Sanity — clean evidence refs accepted ---------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "transcript.json",
        "subdir/file.log",
        "deep/nested/relative.txt",
        "name-with-dashes.yaml",
    ],
)
def test_ac5_evidence_ref_accepts_clean_relative_paths(good: str) -> None:
    r = _result_with_evidence((EvidenceRef(ref=good),))
    assert r.evidence_references[0].ref == good
