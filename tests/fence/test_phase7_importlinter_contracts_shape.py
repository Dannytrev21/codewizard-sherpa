"""Shape-pin for the Phase 7 ``primitives.vuln_provenance`` import-linter contract.

Audit + lint enforcement, NOT runtime (Phase 7 ADR-0011 / Phase 3 ADR-0011).
The Phase 7 LLM-SDK contract added by S1-06 extends the production
ADR-0005 closure to the kernel-surface primitive at
``src/codegenie/primitives/vuln_provenance/``. Any silent cleanup that
flips ``as_packages = false``, drops ``include_external_packages = true``,
narrows ``forbidden_modules``, or retargets ``source_modules`` is caught
here.

Drift between this list and ``codegenie._fence.FORBIDDEN_LLM_SDKS`` is the
worst-case quiet failure — pinning the set verbatim against the canonical
constant couples the contract and the runtime scanner to one source of
truth.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

from codegenie._fence import FORBIDDEN_LLM_SDKS

_PYPROJECT_PATH: Final[Path] = Path("pyproject.toml")
_CONTRACT_NAME: Final[str] = "phase-7 primitive does not import LLM SDKs"
_EXPECTED_SOURCE_MODULES: Final[list[str]] = ["codegenie.primitives.vuln_provenance"]


def _load_phase7_contract() -> dict[str, object]:
    text = _PYPROJECT_PATH.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    for c in contracts:
        if c.get("name") == _CONTRACT_NAME:
            assert isinstance(c, dict)
            return dict(c)
    raise AssertionError(
        f"Phase 7 import-linter contract `{_CONTRACT_NAME}` missing from "
        f"`pyproject.toml [[tool.importlinter.contracts]]`."
    )


def test_phase7_contract_present() -> None:
    """AC-1: the Phase 7 LLM-SDK contract exists under
    ``[tool.importlinter.contracts]``."""
    _load_phase7_contract()


def test_phase7_contract_is_forbidden_type() -> None:
    """AC-1.a: ``type = "forbidden"`` — the only contract type that names
    ``forbidden_modules``."""
    contract = _load_phase7_contract()
    assert contract.get("type") == "forbidden"


def test_phase7_contract_source_modules_pin_to_primitive() -> None:
    """AC-1.a: ``source_modules`` MUST point to the new primitive surface.
    Retargeting (e.g., to ``codegenie.primitives``) would over-fence and
    likely get silently widened to allowlist later — pin exactly."""
    contract = _load_phase7_contract()
    assert contract.get("source_modules") == _EXPECTED_SOURCE_MODULES


def test_phase7_contract_forbids_exactly_the_llm_sdk_closure() -> None:
    """AC-1.b: ``forbidden_modules`` MUST equal
    ``codegenie._fence.FORBIDDEN_LLM_SDKS`` as a set. Drift here = the
    fence is silently incomplete."""
    contract = _load_phase7_contract()
    forbidden_raw = contract.get("forbidden_modules")
    assert isinstance(forbidden_raw, list)
    assert set(forbidden_raw) == FORBIDDEN_LLM_SDKS, (
        f"`{_CONTRACT_NAME}` forbidden_modules drift from FORBIDDEN_LLM_SDKS: "
        f"pyproject has {set(forbidden_raw)}, source-of-truth is "
        f"{FORBIDDEN_LLM_SDKS}."
    )


def test_phase7_contract_as_packages_true() -> None:
    """AC-1.c: ``as_packages = true`` is load-bearing — without it only the
    top-level package's ``__init__.py`` is scanned, and submodules
    (``types``, ``protocols``, ``errors``, ``syft_reader``, …) leak."""
    contract = _load_phase7_contract()
    assert contract.get("as_packages") is True, (
        f"`{_CONTRACT_NAME}` must declare `as_packages = true`. "
        f"Without it submodules under primitives.vuln_provenance silently leak."
    )


def test_phase7_contract_include_external_packages_true() -> None:
    """AC-1.d: ``include_external_packages = true`` is required for
    import-linter to traverse third-party packages (the LLM SDKs) in
    transitive-import reasoning."""
    contract = _load_phase7_contract()
    assert contract.get("include_external_packages") is True, (
        f"`{_CONTRACT_NAME}` must declare `include_external_packages = true` "
        f"so transitive imports through third-party packages are reasoned about."
    )
