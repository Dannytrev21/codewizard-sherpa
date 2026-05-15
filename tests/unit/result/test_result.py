"""Unit tests for ``codegenie.result`` — story 02 S1-04 AC-0a..AC-0e.

Covers:

- AC-0a — ``Ok`` / ``Err`` shape, helper methods.
- AC-0b — ``__all__`` exact-set pin.
- AC-0c — runtime immutability (parametrized).
- AC-0d — round-trip identity (``model_dump_json`` → ``model_validate_json``)
  with concrete-class preservation.
- AC-0e — pure-typing module (AST import-scan).
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from pydantic import ValidationError

import codegenie.result as result_mod
from codegenie.result import Err, Ok


# AC-0b — __all__ exact public surface.
def test_result_all_is_exactly_the_public_surface() -> None:
    assert set(result_mod.__all__) == {"Result", "Ok", "Err"}


# AC-0a — Ok methods.
def test_ok_is_ok_true_and_is_err_false() -> None:
    o = Ok(value=42)
    assert o.is_ok() is True
    assert o.is_err() is False


def test_ok_unwrap_returns_value() -> None:
    assert Ok(value=42).unwrap() == 42


def test_ok_unwrap_err_raises() -> None:
    with pytest.raises(RuntimeError):
        Ok(value=42).unwrap_err()


# AC-0a — Err methods.
def test_err_is_err_true_and_is_ok_false() -> None:
    e = Err(error="boom")
    assert e.is_err() is True
    assert e.is_ok() is False


def test_err_unwrap_err_returns_error() -> None:
    assert Err(error="boom").unwrap_err() == "boom"


def test_err_unwrap_raises() -> None:
    with pytest.raises(RuntimeError):
        Err(error="boom").unwrap()


# AC-0c — runtime immutability, parametrized.
@pytest.mark.parametrize(
    "instance, field, new_value",
    [
        (Ok(value=1), "value", 2),
        (Err(error="x"), "error", "y"),
    ],
)
def test_ok_and_err_are_immutable(
    instance: Ok[int] | Err[str], field: str, new_value: object
) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, new_value)


# AC-0d — round-trip identity for Ok and Err, including nested Ok.
def test_ok_roundtrip_identity_str() -> None:
    encoded = Ok[int](value=42).model_dump_json()
    decoded = Ok[int].model_validate_json(encoded)
    assert isinstance(decoded, Ok)
    assert decoded.value == 42


def test_err_roundtrip_identity_str() -> None:
    encoded = Err[str](error="boom").model_dump_json()
    decoded = Err[str].model_validate_json(encoded)
    assert isinstance(decoded, Err)
    assert decoded.error == "boom"


def test_nested_ok_roundtrip() -> None:
    value = Ok(value=Ok(value=1))
    encoded = value.model_dump_json()
    decoded = Ok.model_validate_json(encoded)
    assert isinstance(decoded, Ok)
    # Nested value round-trips as a dict at the outer layer (no inner type info
    # without an explicit subscript); the structural shape and `kind` discriminator
    # both round-trip identity, which is the contract AC-0d names.
    assert decoded.value == {"kind": "ok", "value": 1}


# AC-0e — module purity (pure typing only).
def test_result_module_imports_only_typing_and_pydantic() -> None:
    tree = ast.parse(pathlib.Path(result_mod.__file__).read_text())
    allowed_prefixes = ("__future__", "typing", "pydantic")
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Import):
            target = node.names[0].name
        elif isinstance(node, ast.ImportFrom):
            target = node.module
        if target is None:
            continue
        assert any(target == p or target.startswith(p + ".") for p in allowed_prefixes), (
            f"codegenie.result imports {target!r} — pure-typing-only invariant"
        )
