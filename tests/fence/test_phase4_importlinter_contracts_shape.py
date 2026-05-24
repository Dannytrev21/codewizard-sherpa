"""Shape-pin for the four Phase 4 import-linter contracts in ``pyproject.toml``.

Audit + lint enforcement, NOT runtime (ADR-0003 — the lint-time belt-and-
suspenders alongside the pytest fence ``tests/fence/test_pyproject_fence_phase4.py``).
If a future cleanup silently drops ``as_packages = true``, narrows
``forbidden_modules``, retargets ``source_modules``, or removes
``include_external_packages``, this test fires.

The expected sets are DERIVED from the Phase-4 fence constants so the lint-time
contracts and the test-time fence stay coupled to one source of truth.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

import pytest

from tests.fence.test_pyproject_fence_phase4 import (
    GATHER_PIPELINE_PATHS,
    PHASE4_ADMITTED_PACKAGES,
    PHASE4_STILL_FORBIDDEN,
)

_PYPROJECT: Final[Path] = Path(__file__).resolve().parents[2] / "pyproject.toml"

_GATHER: Final = "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"
_ANTHROPIC: Final = "ADR-0003: anthropic may be imported only by the leaf adapter"
_CHROMADB: Final = "ADR-0003: chromadb may be imported only under codegenie.rag"
_EMBED: Final = "ADR-0003: fastembed and onnxruntime may be imported only under codegenie.rag"
_NAMES: Final[tuple[str, ...]] = (_GATHER, _ANTHROPIC, _CHROMADB, _EMBED)


def _path_to_module(p: str) -> str:
    """``"src/codegenie/probes/"`` -> ``"codegenie.probes"`` (D3 — path vs. module)."""
    return p.removeprefix("src/").rstrip("/").replace("/", ".")


_EXPECTED_SOURCE_MODULES: Final[dict[str, list[str]]] = {
    _GATHER: sorted(_path_to_module(p) for p in GATHER_PIPELINE_PATHS),
    _ANTHROPIC: ["codegenie"],
    _CHROMADB: ["codegenie"],
    _EMBED: ["codegenie"],
}
_EXPECTED_FORBIDDEN: Final[dict[str, set[str]]] = {
    _GATHER: set(PHASE4_ADMITTED_PACKAGES) | set(PHASE4_STILL_FORBIDDEN),
    _ANTHROPIC: {"anthropic"},
    _CHROMADB: {"chromadb"},
    _EMBED: {"fastembed", "onnxruntime"},
}


def _load() -> dict[str, dict[str, object]]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    return {c["name"]: c for c in contracts if c.get("name") in _NAMES}


def test_all_four_phase4_contracts_present() -> None:
    """AC-1 — all four Phase-4 import-linter contracts ship in pyproject.toml."""
    missing = set(_NAMES) - set(_load())
    assert not missing, f"Missing Phase-4 import-linter contracts: {missing}"


def test_root_includes_external_packages() -> None:
    """AC-3 — required so `forbidden_modules` may name third-party packages."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert data["tool"]["importlinter"].get("include_external_packages") is True


@pytest.mark.parametrize("name", _NAMES)
def test_contract_is_forbidden_type(name: str) -> None:
    assert _load()[name].get("type") == "forbidden"


@pytest.mark.parametrize("name", _NAMES)
def test_contract_uses_as_packages_true(name: str) -> None:
    """AC-1 (C1/C2) — without `as_packages = true` only each package's
    __init__.py is scanned; a violating submodule slips through."""
    assert _load()[name].get("as_packages") is True, (
        f"Contract `{name}` must declare `as_packages = true`."
    )


@pytest.mark.parametrize("name", _NAMES)
def test_contract_source_modules(name: str) -> None:
    got = _load()[name].get("source_modules")
    assert isinstance(got, list)
    assert sorted(got) == _EXPECTED_SOURCE_MODULES[name]


@pytest.mark.parametrize("name", _NAMES)
def test_contract_forbidden_modules_mirror_the_fence(name: str) -> None:
    """AC-1 (D2) — `forbidden_modules` mirrors the Phase-4 fence constants.
    Drift = the lint-time fence silently diverges from the pytest fence."""
    got = _load()[name].get("forbidden_modules")
    assert isinstance(got, list)
    assert set(got) == _EXPECTED_FORBIDDEN[name], (
        f"Contract `{name}` forbidden_modules drift: {set(got)} != {_EXPECTED_FORBIDDEN[name]}"
    )
