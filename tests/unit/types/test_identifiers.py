"""Phase 2 S1-05 — ADR-0033 newtype identifier guards.

Verifies the four kernel-tier ``NewType`` aliases declared in
``src/codegenie/types/identifiers.py`` and the ``PackageManager`` re-export
from Phase 1 ADR-0013's owning module.
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


def test_package_manager_reexported_from_phase1_adr_0013_location() -> None:
    """AC-5 — same object identity, no re-wrapping.

    Phase 1 ADR-0013 currently lives at ``codegenie.probes.node_build_system``;
    if it moves to ``.layer_a.*`` that is a deliberate Phase 1 ADR amendment.
    """
    try:
        from codegenie.probes.node_build_system import PackageManager as P1
    except ImportError:  # pragma: no cover - future re-org guard
        from codegenie.probes.layer_a.node_build_system import (  # type: ignore[no-redef,import-untyped]
            PackageManager as P1,
        )

    assert ids.PackageManager is P1, (
        "PackageManager must be re-exported from its Phase 1 ADR-0013 location; "
        "a redefinition violates ADR-0013 and ADR-0033."
    )


def test_no_package_manager_redefinition_in_types_module() -> None:
    """AC-4 — guard against silent shadowing in ``identifiers.py``."""
    src_path = inspect.getsourcefile(ids)
    assert src_path is not None
    src = pathlib.Path(src_path).read_text()
    assert "class PackageManager" not in src, "Do not redefine PackageManager"
    # Disallow ``PackageManager = <not-an-import>`` reassignment.
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE), (
        "Only `from ... import PackageManager as PackageManager` is allowed"
    )
    matches = re.findall(r"^\s*from .* import .*PackageManager", src, flags=re.MULTILINE)
    assert len(matches) == 1, f"expected one PackageManager import; found {matches}"


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
