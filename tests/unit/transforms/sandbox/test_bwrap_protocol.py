"""Structural Protocol conformance — S4-02 AC-1.

The :class:`~codegenie.transforms.sandbox_jail.SubprocessJail` Protocol is
intentionally NOT ``@runtime_checkable`` (S4-01 AC-2 fences the negative),
so ``isinstance(BwrapAdapter(), SubprocessJail)`` would ``TypeError``.
Instead this test relies on (a) mypy-time assignment conformance and
(b) runtime introspection via :mod:`inspect`.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

from codegenie.exec import ProcessResult
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    JailedSubprocessResult,
    JailedSubprocessSpec,
    SubprocessJail,
)
from tests.unit.transforms.sandbox._fakes import make_spec


def test_module_exists_and_exports_bwrap_adapter() -> None:
    """AC-1: module + export both exist."""
    import codegenie.transforms.sandbox as sandbox_pkg
    import codegenie.transforms.sandbox.bwrap as bwrap_mod

    assert hasattr(bwrap_mod, "BwrapAdapter")
    assert sandbox_pkg.BwrapAdapter is bwrap_mod.BwrapAdapter


def test_assignment_to_protocol_type_checks() -> None:
    """AC-1 (mypy-time check): ``adapter: SubprocessJail = BwrapAdapter()``
    type-checks under ``mypy --strict``. The assertion below is what the
    type-checker observes; the runtime statement keeps this file honest.
    """
    adapter: SubprocessJail = BwrapAdapter()
    assert adapter is not None


def test_run_is_a_coroutine_function() -> None:
    """AC-1: ``inspect.iscoroutinefunction(BwrapAdapter.run)`` is True."""
    assert inspect.iscoroutinefunction(BwrapAdapter.run)


def test_run_signature_matches_port() -> None:
    """AC-1: ``BwrapAdapter.run`` has exactly ``self`` and ``spec``."""
    sig = inspect.signature(BwrapAdapter.run)
    assert set(sig.parameters.keys()) == {"self", "spec"}


def test_run_type_hints_match_port() -> None:
    """AC-1: ``spec`` resolves to :class:`JailedSubprocessSpec` and the
    return annotation resolves to :data:`JailedSubprocessResult` (the
    ``Annotated[...]`` discriminator wrapper)."""
    hints = get_type_hints(BwrapAdapter.run, include_extras=True)
    assert hints["spec"] is JailedSubprocessSpec
    assert hints["return"] is JailedSubprocessResult


async def test_call_site_exercise_through_port_surface(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: a ``SubprocessJail``-typed local reference calls the adapter
    and gets back a typed :data:`JailedSubprocessResult` variant."""

    captured: dict[str, object] = {}

    async def fake_run_allowlisted(
        argv: list[str],
        *,
        cwd: object,
        timeout_s: float,
        env_extra: dict[str, str] | None = None,
    ) -> ProcessResult:
        captured["argv"] = list(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap.run_allowlisted",
        fake_run_allowlisted,
    )
    jail: SubprocessJail = BwrapAdapter()
    spec = make_spec(tmp_path)  # type: ignore[arg-type]
    result = await jail.run(spec)
    # Result is one of the JailedSubprocessResult variants — confirm by
    # round-tripping through the Pydantic discriminator.
    from pydantic import TypeAdapter

    TypeAdapter(JailedSubprocessResult).validate_python(result.model_dump())
    assert captured["argv"], "BwrapAdapter.run did not call run_allowlisted"
