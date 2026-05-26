"""Phase-4 S7-04 — :class:`Phase4Config` schema rejection rules (AC-5, AC-6).

Covers the 12-row Specification-pattern rejection table. Each rule has
one parametrized test; every failing fixture asserts:

* :func:`load_phase4_config` returns :class:`Err`, never raises.
* The wrapped error is a :class:`Phase4ConfigError` (tagged-union shape).
* For schema-level + business-rule violations, the variant is
  :class:`SchemaViolation` and the dotted-path field name (or
  human-readable rationale substring) appears in ``field_errors``.

Tests use **non-arch values** (``0.70``, ``0.30``, ``100_000``, ``0.75``,
``10_000``, ``"test-embedder/v1"``, ``"tests/cassettes/test"``) so a
hardcoded ``0.85`` implementation would fail the round-trip — F4 mitigation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from codegenie.result import Err, Ok

_CONFIG_PATH = (
    Path(__file__).parents[3] / "plugins" / "vulnerability-remediation--node--npm" / "config.py"
)


def _load_config_module() -> ModuleType:
    """Load ``config.py`` via importlib (hyphenated slug isn't import-valid)."""
    mod_name = "_test_phase4_plugin_config"
    spec = importlib.util.spec_from_file_location(mod_name, _CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_CONFIG_MOD = _load_config_module()
load_phase4_config = _CONFIG_MOD.load_phase4_config
Phase4Config = _CONFIG_MOD.Phase4Config
SchemaViolation = _CONFIG_MOD.SchemaViolation
MalformedYaml = _CONFIG_MOD.MalformedYaml
IoError_ = _CONFIG_MOD.IoError


def _valid_config_dict() -> dict[str, Any]:
    """Non-arch values so a hardcoded ``0.85`` impl would FAIL roundtrip."""
    return {
        "thresholds": {"high_floor": 0.70, "degraded_floor": 0.30},
        "budget": {
            "max_tokens_per_workflow": 100_000,
            "max_dollars_per_workflow": "0.75",
            "per_call_max_tokens": 10_000,
        },
        "embeddings": {"model": "test-embedder/v1"},
        "cassettes": {"dir": "tests/cassettes/test"},
    }


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "phase4-config.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


# --- AC-6 — happy-path load ------------------------------------------------


def test_valid_config_loads_as_ok(tmp_path: Path) -> None:
    """The non-arch valid fixture round-trips and equals input.

    Catches hardcoded-default implementations: if any field silently
    defaults to the arch literal (0.85, 250_000, ...), the equality
    assertion below would catch it because we use non-arch values.
    """
    path = _write(tmp_path, _valid_config_dict())
    result = load_phase4_config(path)
    assert isinstance(result, Ok), f"expected Ok, got {result!r}"
    cfg = result.value
    assert cfg.thresholds.high_floor == 0.70
    assert cfg.thresholds.degraded_floor == 0.30
    assert cfg.budget.max_tokens_per_workflow == 100_000
    assert str(cfg.budget.max_dollars_per_workflow) == "0.75"
    assert cfg.budget.per_call_max_tokens == 10_000
    assert cfg.embeddings.model == "test-embedder/v1"
    assert cfg.cassettes.dir == "tests/cassettes/test"


# --- AC-5 R1 — unknown top-level key (typo) --------------------------------


def test_r1_unknown_top_level_key(tmp_path: Path) -> None:
    data = _valid_config_dict()
    # Typo: thresolds (missing h)
    data["thresolds"] = data.pop("thresholds")
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any("thresolds" in e for e in result.error.field_errors)


# --- AC-5 R2 — missing required field --------------------------------------


def test_r2_missing_thresholds_high_floor(tmp_path: Path) -> None:
    data = _valid_config_dict()
    del data["thresholds"]["high_floor"]
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any("thresholds.high_floor" in e for e in result.error.field_errors)


# --- AC-5 R3 + R4 — threshold ordering -------------------------------------


@pytest.mark.parametrize(
    ("high", "degraded"),
    [
        (0.65, 0.65),  # R3 — equality violates strict >
        (0.50, 0.70),  # R4 — high < degraded
    ],
)
def test_r3_r4_threshold_ordering(tmp_path: Path, high: float, degraded: float) -> None:
    data = _valid_config_dict()
    data["thresholds"]["high_floor"] = high
    data["thresholds"]["degraded_floor"] = degraded
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any(
        "high_floor must be > thresholds.degraded_floor" in e for e in result.error.field_errors
    )


# --- AC-5 R5 + R6 — finite + in-range thresholds ---------------------------


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), 1.5, -0.1])
def test_r5_r6_threshold_out_of_range_or_nan(tmp_path: Path, bad_value: float) -> None:
    data = _valid_config_dict()
    data["thresholds"]["high_floor"] = bad_value
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any("must be a finite float in [0.0, 1.0]" in e for e in result.error.field_errors)


# --- AC-5 R7 — max_dollars > 0 ---------------------------------------------


def test_r7_max_dollars_must_be_positive(tmp_path: Path) -> None:
    data = _valid_config_dict()
    data["budget"]["max_dollars_per_workflow"] = "0.00"
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any("max_dollars_per_workflow must be > 0" in e for e in result.error.field_errors)


# --- AC-5 R8 — per_call <= workflow ----------------------------------------


def test_r8_per_call_max_within_workflow_cap(tmp_path: Path) -> None:
    data = _valid_config_dict()
    data["budget"]["per_call_max_tokens"] = 300_000  # > 100_000 workflow cap
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any(
        "per_call_max_tokens must be <= budget.max_tokens_per_workflow" in e
        for e in result.error.field_errors
    )


# --- AC-5 R9 — negative ints rejected --------------------------------------


@pytest.mark.parametrize(
    "field",
    ["max_tokens_per_workflow", "per_call_max_tokens"],
)
def test_r9_negative_budget_int_rejected(tmp_path: Path, field: str) -> None:
    data = _valid_config_dict()
    data["budget"][field] = -1
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    # Either the business rule catches it OR Pydantic does (both acceptable).
    assert result.error.field_errors


# --- AC-5 R10 — empty / whitespace-only embeddings model -------------------


@pytest.mark.parametrize("bad_model", ["", "   "])
def test_r10_empty_embeddings_model(tmp_path: Path, bad_model: str) -> None:
    data = _valid_config_dict()
    data["embeddings"]["model"] = bad_model
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any(
        "embeddings.model must be non-empty after .strip()" in e for e in result.error.field_errors
    )


# --- AC-5 R11 — cassettes.dir absolute / traversal -------------------------


@pytest.mark.parametrize("bad_dir", ["/etc/passwd", "../../outside", "a/../b"])
def test_r11_cassettes_dir_absolute_or_traversal(tmp_path: Path, bad_dir: str) -> None:
    data = _valid_config_dict()
    data["cassettes"]["dir"] = bad_dir
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any(
        "cassettes.dir must be a relative path with no '..' segments" in e
        for e in result.error.field_errors
    )


# --- AC-5 R12 — cassettes.dir empty ----------------------------------------


def test_r12_cassettes_dir_empty(tmp_path: Path) -> None:
    data = _valid_config_dict()
    data["cassettes"]["dir"] = ""
    path = _write(tmp_path, data)
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert any(
        "cassettes.dir must be a non-empty relative path" in e for e in result.error.field_errors
    )


# --- AC-6 — loader never raises (Result-shape contract) --------------------


def test_loader_returns_err_for_missing_file(tmp_path: Path) -> None:
    """File-not-found is :class:`IoError`, not an :class:`OSError` propagating."""
    result = load_phase4_config(tmp_path / "does-not-exist.yaml")
    assert isinstance(result, Err)
    assert isinstance(result.error, IoError_)


def test_loader_returns_err_for_malformed_yaml(tmp_path: Path) -> None:
    """Broken YAML is :class:`MalformedYaml`, not a propagating YAMLError."""
    path = tmp_path / "broken.yaml"
    path.write_text("thresholds:\n  high_floor: [unclosed list\n")
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, MalformedYaml)


def test_loader_does_not_raise_on_unknown_top_level_key(tmp_path: Path) -> None:
    """Pydantic ``extra="forbid"`` ValidationError is caught and translated.

    AC-6 contract: ``load_phase4_config`` never raises for any documented
    failure mode. ``pytest.raises`` is the wrong shape here — the test
    must verify the Result return value.
    """
    data = _valid_config_dict()
    data["extra_unknown_block"] = {"x": 1}
    path = _write(tmp_path, data)
    # No `pytest.raises(...)` — the contract is "never raises".
    result = load_phase4_config(path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
