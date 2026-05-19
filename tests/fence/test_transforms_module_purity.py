"""Module-purity fences for the Phase-3 Transform contract surface — S1-04
AC-6a / AC-6b / AC-5b.

AST-walks ``transform.py``, ``apply_context.py``, ``_forward.py`` and asserts
the import set is a strict subset of the kernel-tier allowlist. Also pins
absence of ``model_construct`` (validation bypass) on the three modules and
fences the ``__all__`` export set on ``codegenie.transforms``.

Mirrors the S1-01 ``tests/unit/types/test_module_purity.py`` precedent and
the S1-03 ``tests/unit/transforms/test_outcomes_purity.py`` precedent.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import codegenie.transforms as transforms_pkg
import codegenie.transforms._forward as forward_mod
import codegenie.transforms.apply_context as apply_context_mod
import codegenie.transforms.transform as transform_mod

# ---------------------------------------------------------------------------
# Allowed import roots — exact strict subsets per module.
# Adding to any allowlist requires an ADR amendment (see ADR-0001).
# ---------------------------------------------------------------------------

# 03-ADR-0011 §Decision §Capability tokens + S4-05 substitution: ``_forward``
# additionally admits ``codegenie.plugins.capabilities`` so the empty
# ``CapabilityBundle`` shim becomes a re-export of the real model. The
# one-way ``transforms → transforms._forward`` direction is unchanged
# (see _forward.py:14-20 docstring for the substitution prescription).
_FORWARD_ALLOWED: frozenset[str] = frozenset(
    {
        "__future__",
        "pathlib",
        "typing",
        "pydantic",
        "codegenie.plugins.sandbox_path",
        "codegenie.plugins.capabilities",
    }
)

_TRANSFORM_ALLOWED: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "datetime",
        "re",
        "typing",
        "pathlib",
        "pydantic",
        "codegenie.types.identifiers",
        "codegenie.types.errors",
        "codegenie.transforms._forward",
    }
)

_APPLY_CONTEXT_ALLOWED: frozenset[str] = frozenset(
    {
        "__future__",
        "typing",
        "pathlib",
        "pydantic",
        "codegenie.types.identifiers",
        "codegenie.types.errors",
        "codegenie.transforms._forward",
    }
)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "<relative-import>")
    return names


def test_forward_module_imports_only_allowed() -> None:
    """AC-5b / S4-04 AC-Sub-2 — ``_forward.py`` import set is the closed
    allowlist. S4-04 flipped the ``SandboxedPath`` ``TypeAlias`` to a
    re-export of :mod:`codegenie.plugins.sandbox_path`; the one-way
    ``transforms → transforms._forward`` direction (cycle-avoidance
    contract of ADR-0001) still holds — the inverse direction
    (``plugins.sandbox_path → transforms``) is fenced separately by
    :mod:`tests.fence.test_plugins_sandbox_path_purity`."""
    src = inspect.getsource(forward_mod)
    imported = _imported_module_names(src)
    extra = imported - _FORWARD_ALLOWED
    assert not extra, (
        f"codegenie.transforms._forward imports outside the allowlist: {sorted(extra)}"
    )


def test_transform_module_imports_only_allowed() -> None:
    """AC-6a — ``transform.py`` import set is a strict subset of the
    kernel-tier allowlist; specifically forbids ``codegenie.plugins.*`` and
    sibling ``transforms.outcomes`` reach-through that would loop the
    contract surface."""
    src = inspect.getsource(transform_mod)
    imported = _imported_module_names(src)
    extra = imported - _TRANSFORM_ALLOWED
    assert not extra, (
        f"codegenie.transforms.transform imports outside the allowlist: {sorted(extra)}"
    )


def test_apply_context_module_imports_only_allowed() -> None:
    """AC-6a — ``apply_context.py`` import set is a strict subset of the
    kernel-tier allowlist."""
    src = inspect.getsource(apply_context_mod)
    imported = _imported_module_names(src)
    extra = imported - _APPLY_CONTEXT_ALLOWED
    assert not extra, (
        f"codegenie.transforms.apply_context imports outside the allowlist: {sorted(extra)}"
    )


def test_no_model_construct_in_contract_modules() -> None:
    """AC-6b — ``model_construct`` bypasses Pydantic validation; ban it at
    source-text level on every contract-surface module ADR-0010 requires
    smart-construct discipline for."""
    for mod in (forward_mod, transform_mod, apply_context_mod):
        src = Path(mod.__file__ or "").read_text()  # type: ignore[arg-type]
        assert "model_construct" not in src, (
            f"{mod.__name__} contains the forbidden ``model_construct`` token; "
            "use ``Model(**kwargs)`` to keep validation in the boundary path."
        )


def test_transforms_all_is_exact_set() -> None:
    """AC-6 — ``__all__`` on ``codegenie.transforms`` includes the S1-04
    additions exactly. The set must be a superset of the Step-1 contract
    surface; S1-03's outcome-union exports remain admitted (this fence does
    not byte-pin the legacy entries because S6-06 will own that snapshot)."""
    required: frozenset[str] = frozenset(
        {
            "Transform",
            "TransformProvenance",
            "ApplyContext",
            "AttemptSummary",
            "CapabilityBundle",
            "SandboxedPath",
        }
    )
    actual: frozenset[str] = frozenset(transforms_pkg.__all__)
    missing = required - actual
    assert not missing, (
        f"codegenie.transforms.__all__ is missing the S1-04 surface: {sorted(missing)}"
    )
