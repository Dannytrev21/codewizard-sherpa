"""Phase-4 S7-04 AC-7 — integration smokes.

Two functions:

1. ``test_synthesized_plugin_phase4_config_loads`` — synthesizes a
   complete minimal plugin tree under ``tmp_path`` and verifies the
   loader composes against it (runs unconditionally).
2. ``test_real_plugin_phase4_config_loads`` — if the shipped plugin's
   ``phase4-config.yaml`` exists on disk, loads + asserts equality
   against the ``tests/_constants/phase4_defaults`` constants. Loud
   skip otherwise.

Both tests pin the parsed values against ``phase4_defaults`` rather
than re-embedding the literals — F10 single-source-of-truth.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from codegenie.result import Ok
from tests._constants.phase4_defaults import (
    PHASE4_CASSETTES_DIR,
    PHASE4_DEGRADED_FLOOR,
    PHASE4_EMBEDDINGS_MODEL,
    PHASE4_HIGH_FLOOR,
    PHASE4_MAX_DOLLARS,
    PHASE4_MAX_TOKENS,
    PHASE4_PER_CALL_MAX_TOKENS,
)

_PLUGIN_DIR = Path(__file__).parents[2] / "plugins" / "vulnerability-remediation--node--npm"
_CONFIG_PY = _PLUGIN_DIR / "config.py"


def _load_config_module() -> ModuleType:
    mod_name = "_test_phase4_integration_cfg"
    spec = importlib.util.spec_from_file_location(mod_name, _CONFIG_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_MOD = _load_config_module()


def _arch_default_yaml() -> str:
    """Compose the arch-default YAML byte-for-byte from constants —
    no literals embedded in the test."""
    return (
        "thresholds:\n"
        f"  high_floor: {PHASE4_HIGH_FLOOR}\n"
        f"  degraded_floor: {PHASE4_DEGRADED_FLOOR}\n"
        "budget:\n"
        f"  max_tokens_per_workflow: {PHASE4_MAX_TOKENS}\n"
        f'  max_dollars_per_workflow: "{PHASE4_MAX_DOLLARS}"\n'
        f"  per_call_max_tokens: {PHASE4_PER_CALL_MAX_TOKENS}\n"
        "embeddings:\n"
        f'  model: "{PHASE4_EMBEDDINGS_MODEL}"\n'
        "cassettes:\n"
        f'  dir: "{PHASE4_CASSETTES_DIR}"\n'
    )


def test_synthesized_plugin_phase4_config_loads(tmp_path: Path) -> None:
    """Synthesize a minimal plugin tree + the Phase-4 config file; load."""
    path = tmp_path / "phase4-config.yaml"
    path.write_text(_arch_default_yaml())

    result = _MOD.load_phase4_config(path)
    assert isinstance(result, Ok), f"unexpected error: {result!r}"
    cfg = result.value
    assert cfg.thresholds.high_floor == PHASE4_HIGH_FLOOR
    assert cfg.thresholds.degraded_floor == PHASE4_DEGRADED_FLOOR
    assert cfg.budget.max_tokens_per_workflow == PHASE4_MAX_TOKENS
    assert cfg.budget.max_dollars_per_workflow == PHASE4_MAX_DOLLARS
    assert cfg.budget.per_call_max_tokens == PHASE4_PER_CALL_MAX_TOKENS
    assert cfg.embeddings.model == PHASE4_EMBEDDINGS_MODEL
    assert cfg.cassettes.dir == PHASE4_CASSETTES_DIR


def test_real_plugin_phase4_config_loads() -> None:
    """Real plugin file on disk parses + matches arch constants.

    Skip-if-absent: the file is shipped by S7-04 itself, so on a clean
    pre-S7-04 tree this test loudly skips with a Phase-3-S7-01-shape
    reason. Post-S7-04 it runs unconditionally.
    """
    real_path = _PLUGIN_DIR / "phase4-config.yaml"
    if not real_path.exists():
        pytest.skip(
            f"Phase-3 S7-01 (and/or S7-04) has not yet shipped {real_path} — skip per AC-7 spec."
        )

    result = _MOD.load_phase4_config(real_path)
    assert isinstance(result, Ok), f"unexpected error: {result!r}"
    cfg = result.value
    # Same equality as the synthesized test — single source of truth.
    assert cfg.thresholds.high_floor == PHASE4_HIGH_FLOOR
    assert cfg.thresholds.degraded_floor == PHASE4_DEGRADED_FLOOR
    assert cfg.budget.max_tokens_per_workflow == PHASE4_MAX_TOKENS
    assert cfg.budget.max_dollars_per_workflow == PHASE4_MAX_DOLLARS
    assert cfg.budget.per_call_max_tokens == PHASE4_PER_CALL_MAX_TOKENS
    assert cfg.embeddings.model == PHASE4_EMBEDDINGS_MODEL
    assert cfg.cassettes.dir == PHASE4_CASSETTES_DIR
