"""Byte-equal contract snapshot — S4-01 AC-15.

S6-06 consumes the golden at ``tests/golden/contracts/sandbox_jail.schema.json``.
Per Step 9 risk #4, an additive field (new optional with ``default_factory``)
is permitted; a rename, removal, or required-field addition requires an ADR
amendment + a fresh golden regeneration.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from codegenie.transforms.sandbox_jail import (
    JailedSubprocessResult,
    JailedSubprocessSpec,
)

_GOLDEN = Path(__file__).resolve().parents[3] / "tests/golden/contracts/sandbox_jail.schema.json"


def test_contract_snapshot_byte_equal() -> None:
    expected = json.loads(_GOLDEN.read_text())
    actual = {
        "spec": JailedSubprocessSpec.model_json_schema(by_alias=True),
        "result": TypeAdapter(JailedSubprocessResult).json_schema(by_alias=True),
    }
    assert actual == expected, (
        "Contract snapshot drift. Either revert the change or "
        "regenerate the golden + amend ADR-0006 per Step 9 risk #4."
    )
