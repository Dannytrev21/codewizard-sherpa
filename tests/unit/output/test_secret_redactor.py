"""Tests for ``redact_secrets`` (S3-01).

Covers all 28 ACs (AC-1..AC-25, AC-26..AC-34 after phase-story-validator
hardening). The mutation-test discipline is load-bearing: each named
pattern class is verified by ``monkeypatch.setattr`` against the
module-level ``_PATTERNS`` table, then re-running the redactor against the
canonical example and asserting it slips through.
"""

from __future__ import annotations

import copy
import inspect
import re
from typing import Any

import pytest

import codegenie.output.sanitizer as sanitizer_module
from codegenie.hashing import content_hash_bytes
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.sanitizer import SecretFinding, redact_secrets
from codegenie.types.identifiers import ProbeId

_PROBE = ProbeId("test_probe")
_FP_REGEX = re.compile(r"^[0-9a-f]{8}$")
_TOKEN_REGEX = re.compile(r"<REDACTED:fingerprint=[0-9a-f]{8}>")


# Canonical examples per pattern class.
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"  # 20 chars (AKIA + 16)
_GH_TOKEN = "ghp_" + "a" * 36
_NPM_TOKEN = "npm_" + "b" * 36
_ANT_KEY = "sk-ant-" + "c" * 50
_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
_RSA_BLOCK = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF32WC2sZxHbPNqcQzgrjLKB\n"
    "QwTKb+EeT3wfeKEbKlbcByEhxLHmTo3GodFmu+9b97Pc92dRefU3+7mWX2\n"
    "-----END RSA PRIVATE KEY-----"
)

_HIGH_ENTROPY_32 = "P9aJ+xUq3rNvLkQ4yF2BzX8sH7CmDeWtVbAoEjGiRfKlpMcN"  # 48 chars


# ----------------------------------------------------------------------------
# AC-1 / AC-2 — surface and docstring
# ----------------------------------------------------------------------------


def test_ac1_redact_secrets_is_exported() -> None:
    assert callable(redact_secrets)
    sig = inspect.signature(redact_secrets)
    assert list(sig.parameters) == ["slice_", "probe_name"]


def test_ac2_module_docstring_contains_required_anchors() -> None:
    doc = inspect.getdoc(sanitizer_module) or ""
    for needle in [
        "02-ADR-0005",
        "02-ADR-0010",
        "4.5",
        "32",
    ]:
        assert needle in doc, f"docstring missing required reference: {needle}"


def test_ac3_secret_finding_model_shape() -> None:
    assert SecretFinding.model_config.get("frozen") is True
    assert SecretFinding.model_config.get("extra") == "forbid"
    assert set(SecretFinding.model_fields.keys()) == {
        "probe_name",
        "fingerprint",
        "pattern_class",
        "cleartext_len",
    }


# ----------------------------------------------------------------------------
# AC-4 .. AC-9 — pattern-class regex coverage
# ----------------------------------------------------------------------------


def _redact_and_extract(input_slice: dict[str, Any]) -> tuple[RedactedSlice, list[SecretFinding]]:
    rs, findings = redact_secrets(input_slice, _PROBE)
    assert isinstance(rs, RedactedSlice)
    return rs, findings


def test_ac4_aws_access_key_redacted() -> None:
    rs, findings = _redact_and_extract({"env": _AWS_KEY})
    assert _TOKEN_REGEX.fullmatch(rs.slice["env"])  # type: ignore[arg-type]
    assert findings[0].pattern_class == "aws_access_key"


def test_ac5_github_token_redacted() -> None:
    rs, findings = _redact_and_extract({"env": _GH_TOKEN})
    assert _TOKEN_REGEX.fullmatch(rs.slice["env"])  # type: ignore[arg-type]
    assert findings[0].pattern_class == "github_token"


def test_ac6_jwt_redacted_and_strict_three_segment() -> None:
    rs, findings = _redact_and_extract({"auth": f"Bearer {_JWT}"})
    # Inline replacement preserves the "Bearer " prefix.
    text = rs.slice["auth"]
    assert isinstance(text, str)
    assert text.startswith("Bearer ")
    assert _TOKEN_REGEX.search(text)
    assert findings[0].pattern_class == "jwt"

    # Bare "eyJabc" (no dots, no segments) is NOT redacted by the JWT rule.
    rs2, findings2 = _redact_and_extract({"auth": "eyJabc"})
    assert rs2.slice["auth"] == "eyJabc"
    assert all(f.pattern_class != "jwt" for f in findings2)


def test_ac7_rsa_private_key_block_collapses_to_single_token() -> None:
    rs, findings = _redact_and_extract({"key": _RSA_BLOCK})
    text = rs.slice["key"]
    assert isinstance(text, str)
    matches = _TOKEN_REGEX.findall(text)
    assert len(matches) == 1
    assert findings[0].pattern_class == "rsa_private_key"


def test_ac8_npm_token_redacted() -> None:
    rs, findings = _redact_and_extract({"env": _NPM_TOKEN})
    assert _TOKEN_REGEX.fullmatch(rs.slice["env"])  # type: ignore[arg-type]
    assert findings[0].pattern_class == "npm_token"


def test_ac9_anthropic_key_redacted_min_length() -> None:
    rs, findings = _redact_and_extract({"key": _ANT_KEY})
    assert _TOKEN_REGEX.fullmatch(rs.slice["key"])  # type: ignore[arg-type]
    assert findings[0].pattern_class == "anthropic_key"

    # Below the minimum length must not match the anthropic rule.
    short = "sk-ant-" + "c" * 10
    rs2, findings2 = _redact_and_extract({"key": short})
    assert rs2.slice["key"] == short
    assert all(f.pattern_class != "anthropic_key" for f in findings2)


# ----------------------------------------------------------------------------
# AC-10 / AC-11 / AC-12 — entropy fallback
# ----------------------------------------------------------------------------


def test_ac10_high_entropy_32plus_redacted_as_entropy_class() -> None:
    rs, findings = _redact_and_extract({"opaque": _HIGH_ENTROPY_32})
    redacted = rs.slice["opaque"]
    assert isinstance(redacted, str)
    assert _TOKEN_REGEX.search(redacted)
    classes = {f.pattern_class for f in findings}
    assert "entropy" in classes


def test_ac11_low_entropy_long_string_not_redacted() -> None:
    payload = "a" * 64
    rs, findings = _redact_and_extract({"opaque": payload})
    assert rs.slice["opaque"] == payload
    assert findings == []


def test_ac11b_prose_text_not_redacted() -> None:
    payload = "the quick brown fox " * 4
    rs, findings = _redact_and_extract({"opaque": payload})
    assert rs.slice["opaque"] == payload
    assert findings == []


def test_ac12_short_high_entropy_not_redacted() -> None:
    short_high_entropy = "P9aJ+xUq3rNvLkQ4"  # 16 chars
    rs, findings = _redact_and_extract({"opaque": short_high_entropy})
    assert rs.slice["opaque"] == short_high_entropy
    assert findings == []


# ----------------------------------------------------------------------------
# AC-13 / AC-14 / AC-32 — fingerprint scheme
# ----------------------------------------------------------------------------


def test_ac13_fingerprint_is_first_8_hex_after_prefix_strip() -> None:
    rs, findings = _redact_and_extract({"env": _AWS_KEY})
    finding = findings[0]
    assert len(finding.fingerprint) == 8
    assert _FP_REGEX.fullmatch(finding.fingerprint)

    expected_full = content_hash_bytes(_AWS_KEY.encode("utf-8"))
    assert expected_full.startswith("blake3:")
    expected_short = expected_full[len("blake3:") :][:8]
    assert finding.fingerprint == expected_short


def test_ac13_identical_cleartext_yields_identical_fingerprint() -> None:
    rs1, findings1 = _redact_and_extract({"env": _AWS_KEY})
    rs2, findings2 = _redact_and_extract({"a": _AWS_KEY, "b": _AWS_KEY})
    fp1 = findings1[0].fingerprint
    fps2 = {f.fingerprint for f in findings2}
    assert fps2 == {fp1}


def test_ac13_distinct_cleartext_yields_distinct_fingerprint() -> None:
    rs, findings = _redact_and_extract({"a": _AWS_KEY, "b": _GH_TOKEN, "c": _NPM_TOKEN})
    fps = {f.fingerprint for f in findings}
    assert len(fps) == 3


def test_ac14_replacement_token_format_and_dedup_order() -> None:
    rs, findings = _redact_and_extract({"a": _AWS_KEY, "b": _AWS_KEY, "c": _GH_TOKEN})
    # All distinct fingerprints in insertion order, deduplicated.
    aws_fp = next(f.fingerprint for f in findings if f.pattern_class == "aws_access_key")
    gh_fp = next(f.fingerprint for f in findings if f.pattern_class == "github_token")
    assert rs.fingerprints == [aws_fp, gh_fp]

    # Token format is exactly the prescribed shape.
    assert _TOKEN_REGEX.fullmatch(rs.slice["a"])  # type: ignore[arg-type]
    assert _TOKEN_REGEX.fullmatch(rs.slice["b"])  # type: ignore[arg-type]
    assert _TOKEN_REGEX.fullmatch(rs.slice["c"])  # type: ignore[arg-type]


def test_ac32_fingerprint_helper_prefix_strip_regression_guard() -> None:
    fp = sanitizer_module._fingerprint("sentinel")
    assert _FP_REGEX.fullmatch(fp)
    full = content_hash_bytes(b"sentinel")
    assert fp == full[7:15]


# ----------------------------------------------------------------------------
# AC-15 / AC-16 / AC-17 — recursive walk over JSONValue
# ----------------------------------------------------------------------------


def test_ac15_recursive_walk_nested_dict_list() -> None:
    fixture: dict[str, Any] = {"a": [{"b": [_AWS_KEY]}]}
    rs, findings = _redact_and_extract(fixture)
    inner = rs.slice["a"][0]["b"][0]  # type: ignore[index]
    assert isinstance(inner, str)
    assert _TOKEN_REGEX.fullmatch(inner)
    assert len(findings) == 1


def test_ac16_dict_keys_are_not_walked_as_values() -> None:
    # The KEY string itself happens to match an AWS regex shape; this MUST
    # NOT cause a redaction (Phase 0 field-name regex is a separate defense).
    rs, findings = _redact_and_extract({_AWS_KEY: "harmless"})
    assert _AWS_KEY in rs.slice
    assert findings == []


def test_ac17_non_string_scalars_passed_through() -> None:
    fixture: dict[str, Any] = {
        "i": 42,
        "f": 1.5,
        "b": True,
        "n": None,
        "list_of_ints": [1, 2, 3],
    }
    rs, findings = _redact_and_extract(fixture)
    assert rs.slice == fixture
    assert findings == []


# ----------------------------------------------------------------------------
# AC-18 — mutation tests (load-bearing)
# ----------------------------------------------------------------------------


_MUTATION_CASES = [
    # Each mutation makes the regex fundamentally unable to match the
    # canonical example: a length quantifier that exceeds the example's
    # length, a literal that no longer appears, or a single-line constraint
    # against a multi-line block. The mutation harness must NOT redact the
    # canonical when the pattern row is replaced with the mutated form.
    pytest.param(
        "aws_access_key",
        re.compile(r"AKIA[0-9A-Z]{17}"),  # canonical is AKIA + 16; requires 17
        _AWS_KEY,
        id="aws_quantifier_too_long",
    ),
    pytest.param(
        "github_token",
        re.compile(r"ghp_[A-Za-z0-9]{37}"),
        _GH_TOKEN,
        id="github_quantifier_too_long",
    ),
    pytest.param(
        "jwt",
        # Require literal `XXX` prefix that no JWT carries.
        re.compile(r"XXX[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        _JWT,
        id="jwt_prefix_changed",
    ),
    pytest.param(
        "rsa_private_key",
        # Require [^\n] between BEGIN and END — never matches a multi-line block.
        re.compile(
            r"-----BEGIN[ A-Z]*PRIVATE KEY-----[^\n]+?"
            r"-----END[ A-Z]*PRIVATE KEY-----"
        ),
        _RSA_BLOCK,
        id="rsa_single_line_only",
    ),
    pytest.param(
        "npm_token",
        re.compile(r"npm_[A-Za-z0-9]{37}"),
        _NPM_TOKEN,
        id="npm_quantifier_too_long",
    ),
    pytest.param(
        "anthropic_key",
        # Canonical is sk-ant- + 50 chars; requires 60 minimum.
        re.compile(r"sk-ant-[A-Za-z0-9_-]{60,}"),
        _ANT_KEY,
        id="anthropic_quantifier_too_long",
    ),
]


@pytest.mark.parametrize(("pattern_class", "weakened", "canonical"), _MUTATION_CASES)
def test_ac18_mutation_weakened_pattern_misses_canonical(
    pattern_class: str,
    weakened: re.Pattern[str],
    canonical: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Replace the matching row with a weakened pattern; drop other rows so the
    # canonical secret is only matchable via the weakened row.
    new_patterns = [(pattern_class, weakened)]
    monkeypatch.setattr(sanitizer_module, "_PATTERNS", new_patterns)
    # Also raise the entropy floor so the entropy fallback does not mask the
    # missed pattern match.
    monkeypatch.setattr(sanitizer_module, "_ENTROPY_THRESHOLD_BITS_PER_CHAR", 99.0)

    rs, findings = redact_secrets({"v": canonical}, _PROBE)
    assert canonical in rs.slice["v"], (  # type: ignore[operator]
        f"weakened {pattern_class} regex unexpectedly redacted the canonical "
        f"example; mutation harness is not load-bearing"
    )
    assert findings == []


def test_ac19_entropy_threshold_mutation_above_floor_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Choose a mutated floor above the canonical fixture's measured entropy
    # (~5.58 bits/char for the 48-char near-uniform sample) so the rule
    # genuinely refuses to fire. A regression that ignores the threshold
    # constant entirely would still redact and fail this assertion.
    monkeypatch.setattr(sanitizer_module, "_PATTERNS", [])
    monkeypatch.setattr(sanitizer_module, "_ENTROPY_THRESHOLD_BITS_PER_CHAR", 6.0)
    rs, findings = redact_secrets({"opaque": _HIGH_ENTROPY_32}, _PROBE)
    assert rs.slice["opaque"] == _HIGH_ENTROPY_32
    assert findings == []


# ----------------------------------------------------------------------------
# AC-20 / AC-21 / AC-22 — in-band findings list contract
# ----------------------------------------------------------------------------


def test_ac20_findings_count_matches_total_matches() -> None:
    fixture: dict[str, Any] = {
        "a": _AWS_KEY,
        "b": "AKIAJANOTHEREXAMPLE0",
        "c": _HIGH_ENTROPY_32,
    }
    rs, findings = _redact_and_extract(fixture)
    assert len(findings) == 3
    assert rs.findings_count == 3


def test_ac21_secret_finding_has_no_cleartext_field() -> None:
    rs, findings = _redact_and_extract({"env": _AWS_KEY})
    assert "cleartext" not in findings[0].model_dump()
    assert findings[0].cleartext_len == len(_AWS_KEY.encode("utf-8"))


def test_ac22_stateless_across_calls() -> None:
    fixture: dict[str, Any] = {"a": _AWS_KEY, "b": _GH_TOKEN}
    rs1, findings1 = redact_secrets(copy.deepcopy(fixture), _PROBE)
    rs2, findings2 = redact_secrets(copy.deepcopy(fixture), _PROBE)
    assert rs1 == rs2
    assert findings1 == findings2


# ----------------------------------------------------------------------------
# AC-23 / AC-24 — Phase 0 contract preserved + no model_construct
# ----------------------------------------------------------------------------


def test_ac24_no_model_construct_in_sanitizer_module() -> None:
    src = inspect.getsource(sanitizer_module)
    pattern = re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*=")
    assert pattern.search(src) is None


# ----------------------------------------------------------------------------
# AC-26 / AC-27 / AC-28 / AC-29 — validator-added edge cases
# ----------------------------------------------------------------------------


def test_ac26_same_secret_twice_dedupes_fingerprint_not_finding() -> None:
    rs, findings = _redact_and_extract({"a": _AWS_KEY, "b": _AWS_KEY})
    assert len(findings) == 2
    assert len(rs.fingerprints) == 1


def test_ac27_two_distinct_named_patterns_in_one_string() -> None:
    payload = f"aws={_AWS_KEY} github={_GH_TOKEN}"
    rs, findings = _redact_and_extract({"creds": payload})
    classes = {f.pattern_class for f in findings}
    fps = {f.fingerprint for f in findings}
    assert classes == {"aws_access_key", "github_token"}
    assert len(fps) == 2


def test_ac28_cleartext_len_is_byte_length_not_char_length() -> None:
    # A 4-byte non-ASCII codepoint (U+1F600) precedes the high-entropy string.
    multi_byte_high_entropy = "\U0001f600" + _HIGH_ENTROPY_32
    rs, findings = _redact_and_extract({"opaque": multi_byte_high_entropy})
    # The cleartext that was redacted is the FULL string (entropy fallback
    # operates on the full leaf when no inline-pattern fires).
    assert findings
    finding = findings[0]
    assert finding.cleartext_len == len(multi_byte_high_entropy.encode("utf-8"))
    assert finding.cleartext_len != len(multi_byte_high_entropy)


def test_ac29_input_slice_is_not_mutated() -> None:
    fixture: dict[str, Any] = {
        "a": _AWS_KEY,
        "nested": {"b": [_GH_TOKEN, "plain"]},
    }
    snapshot = copy.deepcopy(fixture)
    redact_secrets(fixture, _PROBE)
    assert fixture == snapshot


# ----------------------------------------------------------------------------
# AC-30 — module-level positive controls
# ----------------------------------------------------------------------------


def test_ac30a_patterns_table_is_module_level() -> None:
    assert isinstance(sanitizer_module._PATTERNS, list)


def test_ac30b_entropy_threshold_is_module_level_float() -> None:
    assert isinstance(sanitizer_module._ENTROPY_THRESHOLD_BITS_PER_CHAR, float)


def test_ac30c_monkeypatch_patterns_disables_aws_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sanitizer_module, "_PATTERNS", [])
    monkeypatch.setattr(sanitizer_module, "_ENTROPY_THRESHOLD_BITS_PER_CHAR", 99.0)
    rs, findings = redact_secrets({"v": _AWS_KEY}, _PROBE)
    assert rs.slice["v"] == _AWS_KEY
    assert findings == []


# ----------------------------------------------------------------------------
# AC-31 — entropy edge cases
# ----------------------------------------------------------------------------


def test_ac31_shannon_entropy_total_over_str() -> None:
    fn = sanitizer_module._shannon_entropy
    assert fn("") == 0.0
    assert fn("a") == 0.0
    assert fn("a" * 100) == 0.0
    val = fn("ä" * 64)
    assert isinstance(val, float)
    # Mixed unicode string just shouldn't crash.
    fn("\U0001f600" + "abcdefghij" * 6)


# ----------------------------------------------------------------------------
# AC-33 — S3-02 round-trip integration
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        {},
        {"a": _AWS_KEY},
        {"a": _AWS_KEY, "b": _AWS_KEY},
        {"a": _AWS_KEY, "b": _GH_TOKEN, "c": _HIGH_ENTROPY_32},
        {"nested": {"deeper": [{"k": _NPM_TOKEN}, _ANT_KEY]}},
    ],
)
def test_ac33_redacted_slice_round_trips_invariants(fixture: dict[str, Any]) -> None:
    rs, _findings = redact_secrets(fixture, _PROBE)
    reloaded = RedactedSlice.model_validate(rs.model_dump())
    assert reloaded == rs
    for fp in reloaded.fingerprints:
        assert _FP_REGEX.fullmatch(fp), fp
    assert reloaded.findings_count >= len(reloaded.fingerprints)
    assert reloaded.findings_count >= 0


# ----------------------------------------------------------------------------
# AC-34 — inline substring replacement across all named patterns
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "pattern_class"),
    [
        (f"prefix-{_AWS_KEY}-suffix", "aws_access_key"),
        (f"Authorization: token {_GH_TOKEN}", "github_token"),
        (f"NPM_TOKEN={_NPM_TOKEN}", "npm_token"),
        (f"X-Anthropic-Key: {_ANT_KEY}", "anthropic_key"),
    ],
)
def test_ac34_inline_substring_replacement(payload: str, pattern_class: str) -> None:
    rs, findings = redact_secrets({"v": payload}, _PROBE)
    text = rs.slice["v"]
    assert isinstance(text, str)
    assert _TOKEN_REGEX.search(text)
    # The non-secret prefix/suffix survives.
    if pattern_class == "aws_access_key":
        assert text.startswith("prefix-") and text.endswith("-suffix")
    elif pattern_class == "github_token":
        assert text.startswith("Authorization: token ")
    elif pattern_class == "npm_token":
        assert text.startswith("NPM_TOKEN=")
    elif pattern_class == "anthropic_key":
        assert text.startswith("X-Anthropic-Key: ")
    classes = {f.pattern_class for f in findings}
    assert pattern_class in classes


def test_ac34_entropy_inline_substring_replacement() -> None:
    payload = f"random-prefix-{_HIGH_ENTROPY_32}-suffix"
    rs, findings = redact_secrets({"v": payload}, _PROBE)
    text = rs.slice["v"]
    assert isinstance(text, str)
    assert _TOKEN_REGEX.search(text)
    classes = {f.pattern_class for f in findings}
    assert "entropy" in classes
