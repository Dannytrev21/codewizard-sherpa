"""Pydantic _ProbeOutputValidator trust boundary — see ADR-0010, ADR-0008.

Test taxonomy (verifies AC-1 .. AC-19):
- structural shape (AC-1, AC-2, AC-13, AC-14)
- forbidden-type rejection at any depth (AC-2, AC-12, AC-16)
- confidence Literal enforcement (AC-3)
- secret-field-name rejection at any depth (AC-4, AC-11, AC-15)
- forbidden extras (AC-1 with extra="forbid")
- frozenness (AC-1, AC-18)
- ADR-0007 seam — validator decoupled from dataclass (AC-10)
- coordinator-shaped call (AC-9)
- packaging — privacy + lazy import (AC-5, AC-17)
- recursion safety (AC-19)
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from codegenie.coordinator.validator import (
    SECRET_FIELD_PATTERN,
    _ProbeOutputValidator,
)
from codegenie.errors import SecretLikelyFieldNameError


# -----------------------------------------------------------------------------
# AC-2 / AC-12 / AC-16 — forbidden values rejected at depth, regardless of type
# -----------------------------------------------------------------------------
class _CustomObj:  # arbitrary non-JSON-representable class
    pass


FORBIDDEN_LEAVES = [
    pytest.param(b"x", id="bytes"),
    pytest.param(bytearray(b"x"), id="bytearray"),
    pytest.param(lambda: 1, id="callable-lambda"),
    pytest.param((1, 2), id="tuple"),
    pytest.param({1, 2}, id="set"),
    pytest.param(frozenset({1}), id="frozenset"),
    pytest.param(datetime(2026, 5, 13), id="datetime"),
    pytest.param(Path("/tmp"), id="path"),
    pytest.param(Decimal("1.0"), id="decimal"),
    pytest.param(_CustomObj(), id="custom-object"),
]


@pytest.mark.parametrize("bad_leaf", FORBIDDEN_LEAVES)
def test_forbidden_leaf_at_top_level_rejected(bad_leaf: Any) -> None:
    """AC-2: every non-JSONValue type is structurally unrepresentable."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={"k": bad_leaf}, confidence="high")
    assert ei.value.errors(), "ValidationError must carry at least one error"
    locs = {tuple(e["loc"][:1]) for e in ei.value.errors()}
    assert ("schema_slice",) in locs, f"expected schema_slice in {locs}"


@pytest.mark.parametrize("bad_leaf", FORBIDDEN_LEAVES[:3])
def test_forbidden_leaf_at_depth_2_rejected(bad_leaf: Any) -> None:
    """AC-12: deeply-nested bytes/callable rejection — ADR-0010 §Consequences."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": [{"b": bad_leaf}]},
            confidence="high",
        )
    locs = {tuple(e["loc"][:1]) for e in ei.value.errors()}
    assert ("schema_slice",) in locs


PERMITTED_INPUTS = [
    pytest.param({}, id="empty"),
    pytest.param({"k": None}, id="null"),
    pytest.param({"k": True}, id="bool-true"),
    pytest.param({"k": False}, id="bool-false"),
    pytest.param({"k": 1}, id="int"),
    pytest.param({"k": 1.5}, id="float"),
    pytest.param({"k": "s"}, id="string"),
    pytest.param({"k": []}, id="empty-list"),
    pytest.param({"k": {}}, id="empty-dict"),
    pytest.param({"a": {"b": [{"c": [1, None, "x", True]}]}}, id="deeply-nested-json"),
]


@pytest.mark.parametrize("slice_", PERMITTED_INPUTS)
def test_permitted_inputs_round_trip(slice_: dict[str, Any]) -> None:
    """AC-2, AC-13, AC-14 — JSONValue closure accepts JSON-representable shapes."""
    m = _ProbeOutputValidator(schema_slice=slice_, confidence="medium")
    assert m.schema_slice == slice_


def test_bool_round_trips_as_bool_not_int() -> None:
    """AC-13: Pydantic v2 Union member-ordering — bool MUST precede int."""
    m = _ProbeOutputValidator(schema_slice={"k": True}, confidence="high")
    assert m.schema_slice["k"] is True
    assert isinstance(m.schema_slice["k"], bool)
    assert type(m.schema_slice["k"]) is bool  # noqa: E721


# -----------------------------------------------------------------------------
# AC-3 — confidence Literal enforcement
# -----------------------------------------------------------------------------
INVALID_CONFIDENCES = [
    pytest.param("", id="empty-string"),
    pytest.param("HIGH", id="uppercase"),
    pytest.param("High", id="titlecase"),
    pytest.param("high ", id="trailing-space"),
    pytest.param("high_with_caveats", id="extended"),
    pytest.param("unknown", id="extra-value"),
    pytest.param("n/a", id="other"),
    pytest.param(None, id="none"),
    pytest.param(1, id="int"),
    pytest.param(["high"], id="list-wrap"),
]


@pytest.mark.parametrize("bad", INVALID_CONFIDENCES)
def test_confidence_rejects_non_literal(bad: Any) -> None:
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={}, confidence=bad)
    errs = ei.value.errors()
    assert any(tuple(e["loc"]) == ("confidence",) for e in errs), errs
    assert any(
        e["type"] in ("literal_error", "string_type", "string_pattern_mismatch") for e in errs
    ), errs


@pytest.mark.parametrize("good", ["high", "medium", "low"])
def test_confidence_accepts_each_literal(good: str) -> None:
    _ProbeOutputValidator(schema_slice={}, confidence=good)  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# AC-4 / AC-11 / AC-15 — secret-field-name rejection at any depth
# -----------------------------------------------------------------------------
SECRET_KEYS = [
    pytest.param("secret", id="secret"),
    pytest.param("client_secret", id="contains-secret"),
    pytest.param("token", id="token"),
    pytest.param("github_token", id="contains-token"),
    pytest.param("password", id="password"),
    pytest.param("DB_PASSWORD", id="password-upper"),
    pytest.param("credential", id="credential"),
    pytest.param("aws_credentials", id="credentials-plural"),
    pytest.param("api_key", id="api_key-underscore"),
    pytest.param("api-key", id="api-key-hyphen"),
    pytest.param("apikey", id="apikey-no-separator"),
    pytest.param("API_KEY", id="api_key-upper"),
    pytest.param("auth_token", id="auth_token"),
    pytest.param("auth-token", id="auth-token-hyphen"),
    pytest.param("bearer", id="bearer"),
    pytest.param("Authorization_bearer", id="bearer-mixed"),
    pytest.param("access_key", id="access_key"),
    pytest.param("access-key", id="access-key-hyphen"),
    pytest.param("private_key", id="private_key"),
    pytest.param("ssh_private_key", id="private_key-prefixed"),
]


def _unwrap_typed_error(exc: ValidationError) -> BaseException | None:
    """Pydantic v2 wraps validator exceptions; surface the original.

    Tries the documented surfaces in order: errors()[i]["ctx"]["error"], then
    __cause__. Either is acceptable per AC-4. Returns None if neither carries
    a typed error (which is itself an assertion failure for our purposes).
    """
    for e in exc.errors():
        ctx = e.get("ctx") or {}
        err = ctx.get("error")
        if isinstance(err, BaseException):
            return err
    return exc.__cause__


@pytest.mark.parametrize("secret_key", SECRET_KEYS)
def test_secret_key_at_top_level_rejected(secret_key: str) -> None:
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(schema_slice={secret_key: "v"}, confidence="high")
    typed = _unwrap_typed_error(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError), (
        f"expected SecretLikelyFieldNameError; got {type(typed).__name__}: {typed}"
    )


@pytest.mark.parametrize("secret_key", SECRET_KEYS[:5])
def test_secret_key_at_depth_3_via_list_rejected(secret_key: str) -> None:
    """AC-11: walker recurses through dicts AND through list-of-dicts."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": {"b": [{secret_key: "v"}]}},
            confidence="high",
        )
    typed = _unwrap_typed_error(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError)


@pytest.mark.parametrize(
    "benign_key",
    ["tokenize_result", "tokens_used", "password_strength_meter", "secretary_name"],
)
def test_benign_keys_containing_substring_are_still_rejected(benign_key: str) -> None:
    """ADR-0010 §Tradeoffs: regex has false positives; fail loud is the contract.

    These keys are *semantically* benign but lexically contain a forbidden
    substring (``token``, ``password``, ``secret``). The regex matches them
    and the validator rejects them — the ADR's stated tradeoff.
    """
    with pytest.raises(ValidationError):
        _ProbeOutputValidator(schema_slice={benign_key: 1}, confidence="high")


@pytest.mark.parametrize("safe_key", ["language", "stack", "build_system", "ci_provider", "files"])
def test_non_secret_keys_accepted(safe_key: str) -> None:
    _ProbeOutputValidator(schema_slice={safe_key: "v"}, confidence="high")


# ADR-0014 — narrow allowlist for the secret-shaped field-name rejection.


def test_references_secrets_field_name_allowlisted() -> None:
    """ADR-0014: ``references_secrets`` is the literal-identifier-names field
    on ``CISlice`` (S4-01); the values are construction-time guaranteed to be
    identifier strings, not secret payloads. The allowlist lets it through
    while every other secret-shaped key still raises."""
    _ProbeOutputValidator(
        schema_slice={"references_secrets": ["NPM_TOKEN", "AWS_ACCESS_KEY_ID"]},
        confidence="high",
    )


def test_allowlist_does_not_widen_to_substring_matches() -> None:
    """ADR-0014: allowlist is exact-equality, NOT substring. A nearby name
    like ``references_secrets_v2`` is still rejected by the regex."""
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"references_secrets_v2": ["A"]},
            confidence="high",
        )
    typed = _unwrap_typed_error(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError)


def test_allowlist_constant_shape() -> None:
    """ADR-0014: the allowlist is exposed for re-use and is frozen."""
    from codegenie.coordinator.validator import SECRET_FIELD_ALLOWLIST

    assert isinstance(SECRET_FIELD_ALLOWLIST, frozenset)
    assert "references_secrets" in SECRET_FIELD_ALLOWLIST


def test_secret_field_pattern_is_compiled_at_module_scope() -> None:
    """AC-15: S3-03 will import this symbol — pin its presence and shape."""
    import re

    assert isinstance(SECRET_FIELD_PATTERN, re.Pattern)
    for canonical in (
        "secret",
        "token",
        "password",
        "credential",
        "api_key",
        "auth_token",
        "bearer",
        "access_key",
        "private_key",
    ):
        assert SECRET_FIELD_PATTERN.search(canonical), canonical


# -----------------------------------------------------------------------------
# AC-1 — extra="forbid" + frozen
# -----------------------------------------------------------------------------
def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator.model_validate({"schema_slice": {}, "confidence": "low", "rogue": 1})
    errs = ei.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errs), errs
    assert any(tuple(e["loc"]) == ("rogue",) for e in errs), errs


def test_frozen_model_mutation_raises() -> None:
    """AC-18: frozenness actively verified — mirrors test_audit_models idiom."""
    m = _ProbeOutputValidator(schema_slice={}, confidence="high")
    with pytest.raises(ValidationError):
        m.confidence = "low"  # type: ignore[misc]


# -----------------------------------------------------------------------------
# AC-16 — non-string keys
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("bad_key", [1, 1.5, (1, 2), b"x", None, True])
def test_non_string_keys_rejected(bad_key: Any) -> None:
    with pytest.raises(ValidationError):
        _ProbeOutputValidator(schema_slice={bad_key: "v"}, confidence="high")


# -----------------------------------------------------------------------------
# AC-9 — coordinator-shaped call: model_validate(asdict(probe_output))
# -----------------------------------------------------------------------------
def test_model_validate_from_asdict_round_trip() -> None:
    """AC-9: the goal's exact call shape works for a real ProbeOutput dataclass.

    S3-05 will project the asdict() down to {schema_slice, confidence} before
    calling model_validate (since extra='forbid'); the story's responsibility
    is to make that two-key projection round-trip cleanly.
    """
    from codegenie.probes.base import ProbeOutput

    po = ProbeOutput(
        schema_slice={"language": "typescript", "files": 12},
        raw_artifacts=[],
        confidence="high",
        duration_ms=42,
        warnings=[],
        errors=[],
    )
    projected = {
        k: v for k, v in dataclasses.asdict(po).items() if k in ("schema_slice", "confidence")
    }
    m = _ProbeOutputValidator.model_validate(projected)
    assert m.schema_slice == {"language": "typescript", "files": 12}
    assert m.confidence == "high"


# -----------------------------------------------------------------------------
# AC-10 — validator.py does not import ProbeOutput from probes.base
# -----------------------------------------------------------------------------
def test_validator_module_does_not_import_from_probes_base() -> None:
    """AC-10: preserves the ADR-0007 dataclass-contract seam."""
    src = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "codegenie"
        / "coordinator"
        / "validator.py"
    )
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("codegenie.probes"), (
                f"validator.py must not import from codegenie.probes "
                f"(ADR-0007 seam); got: from {mod} import ..."
            )


# -----------------------------------------------------------------------------
# AC-5 + AC-17 — privacy and lazy-import
# -----------------------------------------------------------------------------
def test_validator_not_exported_from_coordinator_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5: importing codegenie.coordinator does not expose _ProbeOutputValidator."""
    for mod in list(sys.modules):
        if mod.startswith("codegenie.coordinator"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import codegenie.coordinator as pkg

    assert not hasattr(pkg, "_ProbeOutputValidator")
    assert "_ProbeOutputValidator" not in getattr(pkg, "__all__", ())


def test_importing_coordinator_does_not_pull_pydantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-17: cold-start fence — pydantic stays out of sys.modules until S3-05 dispatches."""
    for mod in list(sys.modules):
        if mod.startswith(("codegenie.coordinator", "pydantic")):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import codegenie.coordinator  # noqa: F401

    assert "pydantic" not in sys.modules


# -----------------------------------------------------------------------------
# AC-19 — recursion safety
# -----------------------------------------------------------------------------
def test_deeply_nested_dict_does_not_recursion_error() -> None:
    """AC-19: depth 200 must validate cleanly — no RecursionError leaks."""
    deepest: Any = "leaf"
    for _ in range(200):
        deepest = {"x": deepest}
    try:
        _ProbeOutputValidator(schema_slice={"root": deepest}, confidence="high")
    except ValidationError:
        pass  # acceptable: structural rejection
    except RecursionError:  # pragma: no cover — failure mode
        pytest.fail("recursive walker overflowed Python's stack at depth 200")
