"""Phase-4 S7-04 AC-2 + S7-01 completion — kernel ``plugin.yaml`` +
``api.py`` capability surface.

Pins:

* ``plugin.yaml`` parses cleanly through kernel
  :meth:`PluginManifest.from_yaml` (returns :class:`Ok`).
* ``requirements.optional`` contains ``./node_modules/.bin/tsc``
  (the S7-04 AC-2 deliverable per ADR-04-0015).
* ``api.py`` exposes ``_CONSUMES_RAG_CAPABILITIES`` and
  ``_CONSUMES_LLM_CAPABILITIES`` as ``True`` module-level constants.
* ``api.py`` exposes ``get_phase4_config_path()`` returning a path
  that, when loaded via the plugin-local ``load_phase4_config``,
  yields an :class:`Ok`.

The hyphenated plugin slug requires :func:`importlib.util.spec_from_file_location`;
this test follows the same loader pattern S7-01 / S6-05 / S7-02 / S7-04 use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from codegenie.plugins.manifest import PluginManifest
from codegenie.result import Ok

_PLUGIN_DIR = Path(__file__).parents[3] / "plugins" / "vulnerability-remediation--node--npm"
_API_PY = _PLUGIN_DIR / "api.py"
_PLUGIN_YAML = _PLUGIN_DIR / "plugin.yaml"


def _load_api_module() -> ModuleType:
    mod_name = "_test_vuln_plugin_api"
    spec = importlib.util.spec_from_file_location(mod_name, _API_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def test_plugin_yaml_exists() -> None:
    """S7-01 completion — the kernel manifest file ships with the plugin."""
    assert _PLUGIN_YAML.is_file(), f"plugin.yaml missing: {_PLUGIN_YAML}"


def test_plugin_yaml_parses_through_kernel_manifest_loader() -> None:
    """``PluginManifest.from_yaml`` returns Ok; never raises (AC-6 shape symmetry)."""
    result = PluginManifest.from_yaml(_PLUGIN_YAML)
    assert isinstance(result, Ok), f"unexpected error: {result!r}"
    manifest = result.value
    # Plugin-id is the hyphenated slug (smart-constructor lift via parse_plugin_id).
    assert str(manifest.name) == "vulnerability-remediation--node--npm"
    assert manifest.version == "0.1.0"


def test_plugin_yaml_admits_tsc_under_optional() -> None:
    """S7-04 AC-2 — ``./node_modules/.bin/tsc`` is declared as an optional
    tool the plugin requires (ADR-04-0015 / S6-04 ALLOWED_BINARIES
    amendment).
    """
    result = PluginManifest.from_yaml(_PLUGIN_YAML)
    assert isinstance(result, Ok)
    optional = result.value.requirements.optional
    assert "./node_modules/.bin/tsc" in optional, (
        f"expected tsc in requirements.optional; got {optional!r}"
    )


def test_api_module_exposes_capability_constants() -> None:
    """S7-04 AC-2 — module-level ``_CONSUMES_RAG_CAPABILITIES`` +
    ``_CONSUMES_LLM_CAPABILITIES`` are both ``True``.
    """
    api = _load_api_module()
    assert api._CONSUMES_RAG_CAPABILITIES is True
    assert api._CONSUMES_LLM_CAPABILITIES is True


def test_api_module_loads_phase4_config_at_import() -> None:
    """The ``api.py`` import-time machinery loads the sibling
    ``config.py`` module and exposes a ``get_phase4_config_path`` helper.
    """
    api = _load_api_module()
    path = api.get_phase4_config_path()
    assert path.name == "phase4-config.yaml"
    assert path.is_file()

    # Round-trip: load through the loaded config module's function.
    cfg_mod = api._PHASE4_CONFIG_MODULE
    result = cfg_mod.load_phase4_config(path)
    assert isinstance(result, Ok), f"phase4-config.yaml failed to load: {result!r}"
