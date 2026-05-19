"""Plugin-manifest YAML fixtures for ``tests/unit/plugins/test_manifest.py``.

Helpers write each valid + invalid manifest shape into a caller-supplied
``tmp_path``; every helper returns the written :class:`pathlib.Path` so the
test can hand it straight to ``PluginManifest.from_yaml``. The fixtures
**do not import** ``codegenie.plugins.manifest`` — keeping the fixture
module type-cyclically clean lets the tests assert on production-module
state (``ast.parse`` of the source) without dragging the production module
through the fixture import chain.

Story precedent: Phase 2 ``S2-02-conventions-catalog-loader.md`` (catalog
YAML fixtures) and Phase 2 ``S1-04-tccm-model-loader.md`` (TCCM YAML
fixtures). The 1 MiB oversized helper mirrors the cap pinned at
``src/codegenie/plugins/manifest.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = [
    "MINIMAL_VALID_YAML",
    "OVERSIZED_BYTES",
    "write_full",
    "write_invalid_plugin_id",
    "write_malformed",
    "write_minimal",
    "write_oversized",
    "write_with_typo",
]

MINIMAL_VALID_YAML: Final[str] = """\
name: vulnerability-remediation--node--npm
version: 0.1.0
scope:
  task_class: vulnerability-remediation
  languages: javascript
  build_systems: npm
contributes: {}
"""

FULL_VALID_YAML: Final[str] = """\
name: vulnerability-remediation--node--npm
version: 0.1.0
scope:
  task_class: vulnerability-remediation
  languages: [javascript, typescript]
  build_systems: [npm]
extends:
  - vulnerability-remediation--node--star
precedence: 100
contributes:
  adapters:
    dep_graph: adapters.npm_dep_graph:NpmDepGraphAdapter
    scip: adapters.node_scip:NodeScipAdapter
  tccm: ./tccm.yaml
  subgraph: ./subgraph/
  skills: ./skills/
  recipes: ./recipes/
  probes:
    - npm_lockfile_probe
    - package_json_probe
requirements:
  external_tools:
    - npm
  optional:
    - corepack
"""

OVERSIZED_BYTES: Final[int] = 2 << 20  # 2 MiB — strictly above the 1 MiB cap.


def write_minimal(tmp_path: Path, *, name: str = "plugin.yaml") -> Path:
    """Write a minimum-required-fields manifest; returns the path."""
    path = tmp_path / name
    path.write_text(MINIMAL_VALID_YAML, encoding="utf-8")
    return path


def write_full(tmp_path: Path, *, name: str = "plugin.yaml") -> Path:
    """Write a fully-populated manifest exercising every documented field."""
    path = tmp_path / name
    path.write_text(FULL_VALID_YAML, encoding="utf-8")
    return path


def write_with_typo(
    tmp_path: Path, *, submodel: str, name: str = "plugin.yaml"
) -> tuple[Path, str]:
    """Write a manifest with a typo in the named submodel.

    Returns ``(path, expected_substring)`` — the substring that must appear
    in the rendered ``SchemaViolation.field_errors`` so the test can pin
    *which* field tripped ``extra="forbid"``.
    """
    if submodel == "top_level":
        body = MINIMAL_VALID_YAML + "precedance: 50\n"
        expected = "precedance"
    elif submodel == "contributes":
        body = MINIMAL_VALID_YAML.replace(
            "contributes: {}\n",
            "contributes:\n  tccmm: ./tccm.yaml\n",
        )
        expected = "tccmm"
    elif submodel == "requirements":
        body = MINIMAL_VALID_YAML + "requirements:\n  external_toolz:\n    - npm\n"
        expected = "external_toolz"
    elif submodel == "scope":
        body = """\
name: vulnerability-remediation--node--npm
version: 0.1.0
scope:
  task_classs: vulnerability-remediation
  languages: javascript
  build_systems: npm
contributes: {}
"""
        expected = "task_classs"
    else:  # pragma: no cover - test-only branch
        raise ValueError(f"unknown submodel {submodel!r}")
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path, expected


def write_malformed(tmp_path: Path, *, kind: str, name: str = "plugin.yaml") -> Path:
    """Write a manifest that fails the safe-YAML chokepoint structural check."""
    bodies: dict[str, bytes] = {
        "empty_file": b"",
        "invalid_syntax": b"name: foo\n  : invalid-indent\n",
        "top_level_list": b"- a\n- b\n",
        "top_level_scalar": b'"hello"\n',
        "null_document": b"null\n",
    }
    if kind not in bodies:  # pragma: no cover - test-only branch
        raise ValueError(f"unknown malformed kind {kind!r}")
    path = tmp_path / name
    path.write_bytes(bodies[kind])
    return path


def write_oversized(tmp_path: Path, *, name: str = "big.yaml") -> Path:
    """Write a file larger than the 1 MiB manifest cap (drives the size-cap arm)."""
    path = tmp_path / name
    path.write_bytes(b"x" * OVERSIZED_BYTES)
    return path


def write_invalid_plugin_id(tmp_path: Path, *, name: str = "plugin.yaml") -> Path:
    """Write a manifest whose ``name`` does not match the plugin-id grammar."""
    body = MINIMAL_VALID_YAML.replace(
        "name: vulnerability-remediation--node--npm\n",
        "name: NotAPluginId\n",
    )
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path
