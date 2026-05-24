"""Phase-4 S2-05 AC-15 — deliberately failing ``mypy --strict`` fixture.

This file calls ``LeafLlm.invoke(...)`` *without* the required keyword
argument ``token: BudgetToken``. Under ``mypy --strict`` that is a
missing-keyword-argument diagnostic — the **type-system proof** that
ADR-0010's "capability is a function-signature property" claim holds.

This AC is gated on S3-01 landing ``codegenie.fallback.leaf.protocol``;
``tests/fence/test_budget_token_typecheck.py`` uses
``pytest.importorskip`` to skip cleanly when the Protocol does not yet
exist (the only ``pytest.skip`` allowed in ``tests/fence/``, per the
story's explicit gating-permission for AC-15).

When S3-01 GREENs, this fixture flips from skip → red (the missing-arg
mypy diagnostic). The fixture body never actually runs — ``mypy``
type-checks it as a subprocess.
"""

# pyright: reportMissingImports=false
# mypy is the bar — pyright is not configured for this repo (CLAUDE.md
# §"`pyright` is not used; `mypy --strict`"). The pyright comment is a
# documentation cue for any IDE the contributor uses.
from __future__ import annotations

# S3-01 has not yet landed. When it does, the import below resolves and
# the call site is mypy-checked. Until then the test using this fixture
# `importorskip`s on the same path.
from codegenie.fallback.leaf.protocol import LeafLlm  # type: ignore[import-not-found]

from codegenie.fallback.budget_token import BudgetToken  # noqa: F401


async def caller(leaf: LeafLlm) -> None:
    """Calling ``invoke`` without ``token=...`` MUST be a mypy error.

    The Protocol's signature lists ``token: BudgetToken`` as a required
    keyword argument; omitting it is the type-system proof that
    "Capability passed through ten frames" cannot reappear by accident.
    """
    await leaf.invoke(  # type: ignore[call-arg]
        system_prompt=...,  # type: ignore[arg-type]
        user_message=...,  # type: ignore[arg-type]
        schema=...,  # type: ignore[arg-type]
    )
