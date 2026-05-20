"""Phase 2 S1-05 — ADR-0033 newtype identifier guards.

Verifies the four kernel-tier ``NewType`` aliases declared in
``src/codegenie/types/identifiers.py`` and the ``PackageManager`` Literal,
whose definition home moved to this module in ADR-0013 Amendment 2026-05-20.
"""

from __future__ import annotations

import inspect
import pathlib
import re

import codegenie.types.identifiers as ids


def test_newtypes_exist_and_are_distinct() -> None:
    """AC-1 — four NewType aliases over str, each exposing ``__supertype__``."""
    for name in ("IndexId", "SkillId", "TaskClassId", "IndexName"):
        assert hasattr(ids, name), f"missing {name}"
        nt = getattr(ids, name)
        assert nt.__supertype__ is str, f"{name} must be NewType over str"


def test_newtype_objects_are_distinct_identities() -> None:
    """AC-1 — the four aliases must not be the same NewType object (mypy
    treats them nominally; runtime identity should mirror that)."""
    nts = [ids.IndexId, ids.SkillId, ids.TaskClassId, ids.IndexName]
    assert len({id(nt) for nt in nts}) == 4


def test_newtypes_runtime_identity_to_str() -> None:
    """AC-7 — at runtime, NewType is identity. Documents the intentional shape
    so a future contributor doesn't add runtime ``isinstance(x, IndexId)``
    checks (which would silently succeed for any ``str``)."""
    val = ids.IndexId("scip")
    assert val == "scip"
    assert isinstance(val, str)


def test_package_manager_carries_the_five_adr_0013_values() -> None:
    """ADR-0013 Amendment 2026-05-20 — ``PackageManager``'s definition home
    is the kernel-tier ``codegenie.types.identifiers``. It is the closed
    ``Literal`` of the five ADR-0013 package-manager tags (yarn split into
    classic/berry for plugin dispatch)."""
    from typing import get_args

    assert set(get_args(ids.PackageManager)) == {
        "bun",
        "pnpm",
        "yarn-classic",
        "yarn-berry",
        "npm",
    }


def test_package_manager_is_defined_here_not_reexported() -> None:
    """ADR-0013 Amendment — ``identifiers.py`` now DEFINES ``PackageManager``
    as ``Literal[...]`` directly. The old lazy ``__getattr__`` re-export (a
    band-aid for the ``types ↔ probes`` import cycle) and the
    ``TYPE_CHECKING`` re-import from ``probes.node_build_system`` must both
    be gone — their presence would mean the inverted dependency returned."""
    src_path = inspect.getsourcefile(ids)
    assert src_path is not None
    src = pathlib.Path(src_path).read_text()
    assert "class PackageManager" not in src, "ADR-0013 PackageManager is a Literal, not a class"
    assert re.search(r"^PackageManager\s*=\s*Literal\[", src, flags=re.MULTILINE), (
        "identifiers.py must define `PackageManager = Literal[...]` (ADR-0013 Amendment)"
    )
    assert "def __getattr__" not in src, (
        "the lazy __getattr__ PackageManager re-export band-aid must be gone"
    )
    assert "import PackageManager" not in src, (
        "identifiers.py must not import PackageManager — it is the definition home"
    )


def test_all_exports_include_five_names() -> None:
    """AC-3 — package ``__all__`` re-exports all five kernel identifiers."""
    from codegenie import types as t

    assert set(t.__all__) >= {
        "IndexId",
        "SkillId",
        "TaskClassId",
        "IndexName",
        "PackageManager",
    }


def test_identifiers_module_all_lists_five_names() -> None:
    """AC-1/AC-3 — the identifiers module itself exposes the five public names."""
    assert set(ids.__all__) >= {
        "IndexId",
        "SkillId",
        "TaskClassId",
        "IndexName",
        "PackageManager",
    }
