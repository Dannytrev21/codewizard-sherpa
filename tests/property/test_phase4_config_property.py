"""Phase-4 S7-04 — Hypothesis properties (AC-9 round-trip, AC-10 ordering).

**AC-9 (round-trip / metamorphic).** Generate a valid Phase4Config dict,
dump it to YAML, reload via :func:`load_phase4_config`, assert byte-equal
model. Defends against asymmetric serializers (e.g. a future YAML
formatter that wraps quotes inconsistently between dump + parse).

**AC-10 (threshold-ordering on the unit square).** ``Phase4Config`` is
``Ok`` iff ``0 <= degraded_floor < high_floor <= 1``, else ``Err``.
Includes the boundary cases (``high_floor == 1.0``, ``degraded_floor == 0.0``)
and the strict-equality rejection at the band-touching point.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from codegenie.result import Err, Ok

_CONFIG_PATH = (
    Path(__file__).parents[2] / "plugins" / "vulnerability-remediation--node--npm" / "config.py"
)


def _load() -> ModuleType:
    mod_name = "_test_phase4_property_cfg"
    spec = importlib.util.spec_from_file_location(mod_name, _CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_MOD = _load()


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "phase4-config.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


# --- AC-9 — round-trip property --------------------------------------------


@given(
    high=st.floats(min_value=0.51, max_value=1.0, allow_nan=False, allow_infinity=False),
    degraded=st.floats(min_value=0.0, max_value=0.49, allow_nan=False, allow_infinity=False),
    max_tokens=st.integers(min_value=1, max_value=10_000_000),
    max_dollars_str=st.from_regex(r"^[1-9]\d{0,3}\.\d{2}$", fullmatch=True),
    embeddings_model=st.text(
        alphabet=st.characters(
            min_codepoint=0x20,
            max_codepoint=0x7E,
            blacklist_characters="'\"\\",
        ),
        min_size=1,
        max_size=40,
    ),
    cassettes_dir_segments=st.lists(
        st.text(
            alphabet=st.characters(
                min_codepoint=0x61, max_codepoint=0x7A
            ),  # a-z only — keeps YAML round-trip stable
            min_size=1,
            max_size=8,
        ),
        min_size=1,
        max_size=4,
    ),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_phase4_config_yaml_roundtrip(
    high: float,
    degraded: float,
    max_tokens: int,
    max_dollars_str: str,
    embeddings_model: str,
    cassettes_dir_segments: list[str],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Generated valid config dumps to YAML and reloads byte-equal.

    Catches asymmetric serializers: a future YAML formatter that quotes
    Decimals inconsistently between dump + parse would round-trip-fail
    here.
    """
    # Constrain so per_call <= workflow.
    per_call = max(1, max_tokens // 2)
    assume(embeddings_model.strip())  # R10 — non-empty after strip
    cassettes_dir = "/".join(cassettes_dir_segments)
    data = {
        "thresholds": {"high_floor": high, "degraded_floor": degraded},
        "budget": {
            "max_tokens_per_workflow": max_tokens,
            "max_dollars_per_workflow": max_dollars_str,
            "per_call_max_tokens": per_call,
        },
        "embeddings": {"model": embeddings_model},
        "cassettes": {"dir": cassettes_dir},
    }
    tmp = tmp_path_factory.mktemp("roundtrip")
    path = _write(tmp, data)

    result_a = _MOD.load_phase4_config(path)
    assert isinstance(result_a, Ok), f"unexpected error: {result_a!r}"
    cfg_a = result_a.value

    # Round-trip: dump the parsed model back to YAML, reload.
    redump = {
        "thresholds": {
            "high_floor": cfg_a.thresholds.high_floor,
            "degraded_floor": cfg_a.thresholds.degraded_floor,
        },
        "budget": {
            "max_tokens_per_workflow": cfg_a.budget.max_tokens_per_workflow,
            "max_dollars_per_workflow": str(cfg_a.budget.max_dollars_per_workflow),
            "per_call_max_tokens": cfg_a.budget.per_call_max_tokens,
        },
        "embeddings": {"model": cfg_a.embeddings.model},
        "cassettes": {"dir": cfg_a.cassettes.dir},
    }
    second_dir = tmp / "second"
    second_dir.mkdir(parents=True, exist_ok=True)
    path_b = _write(second_dir, redump)
    result_b = _MOD.load_phase4_config(path_b)
    assert isinstance(result_b, Ok), f"reload failed: {result_b!r}"

    # Model equality (Pydantic frozen model __eq__).
    assert cfg_a == result_b.value


# --- AC-10 — threshold ordering property -----------------------------------


@given(
    h=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    d=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_phase4_thresholds_ok_iff_strict_ordering(
    h: float, d: float, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """``Phase4Config`` is ``Ok`` iff ``0 <= d < h <= 1``, else ``Err``.

    Boundary cases included (h == d, h == 0, d == 1, h == 1).
    """
    tmp = tmp_path_factory.mktemp("ordering")
    data = {
        "thresholds": {"high_floor": h, "degraded_floor": d},
        "budget": {
            "max_tokens_per_workflow": 100_000,
            "max_dollars_per_workflow": "0.75",
            "per_call_max_tokens": 10_000,
        },
        "embeddings": {"model": "test/v1"},
        "cassettes": {"dir": "tests/cassettes/test"},
    }
    path = _write(tmp, data)
    result = _MOD.load_phase4_config(path)

    valid = 0.0 <= d < h <= 1.0
    if valid:
        assert isinstance(result, Ok), f"expected Ok for h={h}, d={d}; got {result!r}"
    else:
        assert isinstance(result, Err), f"expected Err for h={h}, d={d}; got {result!r}"
