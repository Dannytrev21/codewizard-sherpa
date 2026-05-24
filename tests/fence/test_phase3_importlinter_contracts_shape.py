"""Shape-pin for the two Phase 3 import-linter contracts in ``pyproject.toml``.

Audit + lint enforcement, NOT runtime (ADR-0011). If a future cleanup silently
drops ``as_packages = true``, narrows ``forbidden_modules``, or retargets
``source_modules``, this test fires.

Drift between this list and ``codegenie._fence.FORBIDDEN_LLM_SDKS`` is the
worst-case quiet failure — pinning the set verbatim here couples both
fences to the same source-of-truth.

Phase-4 S1-05 / ADR-0003: comparison is via :func:`packaging.utils.canonicalize_name`
on both sides. ``forbidden_modules`` uses **import** names (`sentence_transformers`,
underscore — import-linter scans real `import …` statements);
``FORBIDDEN_LLM_SDKS`` uses **distribution** names (`sentence-transformers`,
hyphen — the PyPI canonical form). PEP 503 canonicalises both spellings to the
same value, so set-equality across canonical forms is the source-of-truth
identity check.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

import pytest
from packaging.utils import canonicalize_name

from codegenie._fence import FORBIDDEN_LLM_SDKS

_PYPROJECT_PATH: Final[Path] = Path("pyproject.toml")

_PHASE3_CONTRACT_NAMES: Final[tuple[str, ...]] = (
    "codegenie.plugins must not import LLM SDKs",
    "codegenie.transforms must not import LLM SDKs",
)

_EXPECTED_SOURCE_MODULES: Final[dict[str, list[str]]] = {
    "codegenie.plugins must not import LLM SDKs": ["codegenie.plugins"],
    "codegenie.transforms must not import LLM SDKs": ["codegenie.transforms"],
}


def _load_phase3_contracts() -> dict[str, dict[str, object]]:
    """Return ``{name: contract_dict}`` for the two Phase 3 contracts only."""
    text = _PYPROJECT_PATH.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    return {c["name"]: c for c in contracts if c.get("name") in _PHASE3_CONTRACT_NAMES}


def test_both_phase3_contracts_present() -> None:
    """AC-1: both contracts exist in ``[tool.importlinter]``."""
    contracts = _load_phase3_contracts()
    missing = set(_PHASE3_CONTRACT_NAMES) - set(contracts.keys())
    assert not missing, (
        f"Missing Phase 3 import-linter contracts: {missing}. "
        f"Check ``pyproject.toml [[tool.importlinter.contracts]]``."
    )


@pytest.mark.parametrize("contract_name", _PHASE3_CONTRACT_NAMES)
def test_contract_is_forbidden_type(contract_name: str) -> None:
    contracts = _load_phase3_contracts()
    assert contracts[contract_name].get("type") == "forbidden"


@pytest.mark.parametrize("contract_name", _PHASE3_CONTRACT_NAMES)
def test_contract_uses_as_packages_true(contract_name: str) -> None:
    """AC-1: ``as_packages = true`` is load-bearing — without it only the
    package ``__init__.py`` is scanned, not submodules."""
    contracts = _load_phase3_contracts()
    assert contracts[contract_name].get("as_packages") is True, (
        f"Contract `{contract_name}` must declare `as_packages = true` so "
        f"submodules are scanned, not just the package __init__.py."
    )


@pytest.mark.parametrize("contract_name", _PHASE3_CONTRACT_NAMES)
def test_contract_source_modules_are_correct(contract_name: str) -> None:
    contracts = _load_phase3_contracts()
    expected = _EXPECTED_SOURCE_MODULES[contract_name]
    assert contracts[contract_name].get("source_modules") == expected


@pytest.mark.parametrize("contract_name", _PHASE3_CONTRACT_NAMES)
def test_contract_forbids_exactly_the_llm_sdk_closure(contract_name: str) -> None:
    """AC-1: each Phase 3 contract's ``forbidden_modules`` MUST equal
    ``codegenie._fence.FORBIDDEN_LLM_SDKS`` as a set. Drift here = the
    fence is silently incomplete."""
    contracts = _load_phase3_contracts()
    forbidden_raw = contracts[contract_name].get("forbidden_modules")
    assert isinstance(forbidden_raw, list)
    canonical_pyproject = {canonicalize_name(n) for n in forbidden_raw}
    canonical_fence = {canonicalize_name(n) for n in FORBIDDEN_LLM_SDKS}
    assert canonical_pyproject == canonical_fence, (
        f"Contract `{contract_name}` forbidden_modules drift from "
        f"FORBIDDEN_LLM_SDKS (canonical comparison): pyproject has "
        f"{canonical_pyproject}, source-of-truth is {canonical_fence}."
    )
