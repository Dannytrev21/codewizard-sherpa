"""Phase-4 S3-01 AC-6 / AC-6a — subprocess-``mypy --strict`` meta-test.

Five negative cases (AC-6) prove the Protocol's signature is the load-bearing
contract: ADR-0010 §Consequences ("calling ``LeafLlm.invoke`` without a
``BudgetToken`` is a ``TypeError`` at call construction") holds at CI, not on
hope. One positive control (AC-6a) proves the Protocol is actually
implementable — a negative-only meta-test would still "pass" against a
``Protocol`` mangled into an un-satisfiable shape.

Every test source preamble binds correctly-typed ``sp``, ``body``, ``sch``,
``tok`` so each negative case isolates **exactly one** violation (TQ4): passing
the bare ``PlanProposal`` alias as ``schema`` would itself be a type error and
muddy the keyword-only / missing-argument cases.

``pytest.importorskip("mypy")`` so a missing mypy install surfaces as a skip,
not a confusing pass/fail.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")


_PREAMBLE = textwrap.dedent(
    """
    from pydantic import TypeAdapter

    from codegenie.fallback.budget_token import BudgetToken
    from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
    from codegenie.fallback.leaf.port import LeafLlm
    from codegenie.fallback.plan_proposal import PlanProposal

    leaf: LeafLlm
    sp: TrustedPrompt
    body: FencedPromptBody
    sch: TypeAdapter[PlanProposal] = TypeAdapter(PlanProposal)
    tok: BudgetToken

    async def _run() -> None:
    """
).strip("\n")


def _render(call_line: str) -> str:
    """Render a temp source file: preamble + one ``await`` call.

    The body of ``_run`` carries exactly the one call shape under test; the
    preamble pins every name as the correct type so any mypy error must come
    from the call line itself.
    """
    return _PREAMBLE + "\n    " + call_line + "\n"


_REJECT_CASES: list[tuple[str, str]] = [
    # Missing required ``token`` keyword arg.
    ("missing_token", "await leaf.invoke(sp, body, schema=sch)"),
    # Missing required ``schema`` keyword arg.
    ("missing_schema", "await leaf.invoke(sp, body, token=tok)"),
    # Positional ``schema`` + ``token`` — keyword-only violation.
    ("positional_kwonly", "await leaf.invoke(sp, body, sch, tok)"),
    # Raw ``str`` instead of ``TrustedPrompt``.
    ("raw_str_system_prompt", 'await leaf.invoke("raw str", body, schema=sch, token=tok)'),
    # Raw ``str`` instead of ``FencedPromptBody``.
    ("raw_str_user_message", 'await leaf.invoke(sp, "raw str", schema=sch, token=tok)'),
]


def _run_mypy(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("name", "call_line"),
    _REJECT_CASES,
    ids=[name for name, _ in _REJECT_CASES],
)
def test_mypy_rejects_invalid_leaf_invoke_call_shape(
    tmp_path: Path, name: str, call_line: str
) -> None:
    """AC-6 — each of the five negative call shapes fails ``mypy --strict``."""
    target = tmp_path / f"{name}.py"
    target.write_text(_render(call_line))
    result = _run_mypy(target)
    assert result.returncode != 0, (
        f"mypy accepted {name}; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout.lower()
    # Asserting at least one diagnostic substring (matches S1-01 / hardened
    # S1-02 AC-7) — a bare non-zero exit could come from an import-resolution
    # error and green-wash a file that fails mypy for an unrelated reason.
    assert any(
        substring in out for substring in ("incompatible type", "argument", "missing", "positional")
    ), f"mypy exit was non-zero but no expected diagnostic substring; stdout:\n{result.stdout}"


def test_mypy_accepts_conforming_stub(tmp_path: Path) -> None:
    """AC-6a positive control — a class whose ``invoke`` matches the Protocol
    type-checks clean under ``mypy --strict``.

    Proves the Protocol is actually implementable. Without this control, all
    five AC-6 cases would still "pass" against a Protocol mangled into an
    un-satisfiable shape.
    """
    source = textwrap.dedent(
        """
        from pydantic import TypeAdapter

        from codegenie.fallback.budget_token import BudgetToken
        from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
        from codegenie.fallback.leaf.port import LeafLlm, LeafResponse
        from codegenie.fallback.plan_proposal import PlanProposal


        class _ConformingStub:
            async def invoke(
                self,
                system_prompt: TrustedPrompt,
                user_message: FencedPromptBody,
                *,
                schema: TypeAdapter[PlanProposal],
                token: BudgetToken,
            ) -> LeafResponse:
                raise NotImplementedError


        _l: LeafLlm = _ConformingStub()
        """
    )
    target = tmp_path / "conforming.py"
    target.write_text(source)
    result = _run_mypy(target)
    assert result.returncode == 0, (
        f"mypy rejected the conforming stub; stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
