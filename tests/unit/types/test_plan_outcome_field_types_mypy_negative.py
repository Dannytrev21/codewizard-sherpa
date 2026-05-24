"""Phase 4 S1-03 — ``mypy --strict`` rejects field-type swaps on ``AppliedFromLlm``.

Newtype discipline (production ADR-0033): swapping ``response_id`` (typed
``LeafResponseId``) with ``SolvedExampleId`` must be a static type error, and
vice-versa for ``few_shot_ref``.

The check reads the field via **attribute access** (``wrong: T = m.<field>``),
NOT through the Pydantic constructor (F6): this repo does not enable the
``pydantic.mypy`` plugin (``[tool.mypy]`` carries no ``plugins=``), so
``BaseModel.__init__`` is ``(**data: Any)`` to mypy — a constructor-kwarg
type swap is silently accepted, false-passing the test. The attribute-read
idiom is plugin-independent and reads the class-body annotation directly.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")

# (field, wrong_target_type) — assigning ``m.<field>`` to a var of
# ``wrong_target_type`` must be a mypy error. ``response_id`` is
# ``LeafResponseId``; ``few_shot_ref`` is ``SolvedExampleId | None``.
_SWAPS = [
    ("response_id", "SolvedExampleId"),
    ("few_shot_ref", "LeafResponseId"),
]


def _src(field: str, wrong_target: str) -> str:
    return textwrap.dedent(
        f"""
        from codegenie.fallback.plan_outcome import AppliedFromLlm
        from codegenie.types.identifiers import LeafResponseId, SolvedExampleId

        def _read(m: AppliedFromLlm) -> None:
            wrong: {wrong_target} = m.{field}
        """
    )


@pytest.mark.parametrize("field,wrong_target", _SWAPS)
def test_mypy_strict_rejects_wrong_field_type(
    tmp_path: Path, field: str, wrong_target: str
) -> None:
    tmp = tmp_path / "swap.py"
    tmp.write_text(_src(field, wrong_target))
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted a wrong type for {field}; stdout:\n{result.stdout}"
    )
    out = result.stdout.lower()
    assert "incompatible type" in out or "assignment" in out, (
        f"mypy failed but not for the {field} type swap; stdout:\n{result.stdout}"
    )
