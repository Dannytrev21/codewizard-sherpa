"""Shared loader for the Phase-4 typecheck collector module.

Both ``test_ts_typecheck_signal.py`` (S6-05) and
``test_applicability_matrix.py`` (S6-06) need the collector module.
Loading it twice under different synthetic names re-registers
``typecheck.typescript`` against the open ``signal_kind_registry``,
which raises :class:`SignalKindAlreadyRegistered`. This module
performs a single load and exposes the result as a shared constant.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_COLLECTOR_PATH: Final[Path] = (
    _REPO_ROOT
    / "plugins"
    / "vulnerability-remediation--node--npm"
    / "adapters"
    / "ts_typecheck_signal.py"
)


def _load() -> ModuleType:
    mod_name = "_phase4_ts_typecheck_collector"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _COLLECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


MODULE: Final[ModuleType] = _load()
