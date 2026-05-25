"""Phase-4 S2-05 AC-15 — deliberately failing ``mypy --strict`` fixture.

This file calls ``LeafLlm.invoke(...)`` *without* the required keyword
argument ``token: BudgetToken``. Under ``mypy --strict`` that is a
missing-keyword-argument diagnostic — the **type-system proof** that
ADR-0010's "capability is a function-signature property" claim holds.

This AC is gated on S3-01 landing ``codegenie.fallback.leaf.port``;
``tests/fence/test_budget_token_typecheck.py`` uses
``pytest.importorskip`` to skip cleanly when the Protocol does not yet
exist (the only ``pytest.skip`` allowed in ``tests/fence/``, per the
story's explicit gating-permission for AC-15). S2-05 named the module
``.protocol`` in this fixture; S3-01 (the contract owner — AC-1 names
``port.py``) reconciled the path to ``.port``.

When S3-01 GREENs, this fixture flips from skip → red (the missing-arg
mypy diagnostic). The fixture body never actually runs — ``mypy``
type-checks it as a subprocess.
"""

# pyright: reportMissingImports=false
# mypy is the bar — pyright is not configured for this repo (CLAUDE.md
# §"`pyright` is not used; `mypy --strict`"). The pyright comment is a
# documentation cue for any IDE the contributor uses.
from __future__ import annotations

from codegenie.fallback.budget_token import BudgetToken  # noqa: F401

# S3-01 has landed `codegenie.fallback.leaf.port`; the call site below
# is now mypy-checked by ``tests/fence/test_budget_token_typecheck.py``.
from codegenie.fallback.leaf.port import LeafLlm


async def caller(leaf: LeafLlm) -> None:
    """Calling ``invoke`` without ``token=...`` MUST be a mypy error.

    The Protocol's signature lists ``token: BudgetToken`` as a required
    keyword argument; omitting it is the type-system proof that
    "Capability passed through ten frames" cannot reappear by accident.
    """
    # The `# type: ignore[arg-type]` on each ``...`` placeholder suppresses
    # the *expected* arg-type noise so the only unsuppressed diagnostic is
    # the missing ``token=`` keyword arg ([call-arg]) — exactly what
    # ``tests/fence/test_budget_token_typecheck.py`` asserts on.
    await leaf.invoke(
        system_prompt=...,  # type: ignore[arg-type]
        user_message=...,  # type: ignore[arg-type]
        schema=...,  # type: ignore[arg-type]
    )
