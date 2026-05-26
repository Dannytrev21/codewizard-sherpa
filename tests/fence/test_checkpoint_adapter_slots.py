"""Phase 6 S2-01 AC-14 — adapter classes declare ``__slots__``.

Without ``__slots__``, an executor accidentally writes
``self._connetcion = ...`` (typo) and creates a silent shadow
attribute; the real ``self._connection`` stays ``None`` and surfaces as
a much later ``NoneError``. ``__slots__`` makes the typo a
class-construction failure.

AST-walks both adapter modules and asserts every adapter class
declares a non-empty ``__slots__``.
"""

from __future__ import annotations

import ast
import inspect

from codegenie.workflows import in_memory_checkpoints, sqlite_checkpoints

_ADAPTER_MODULES = (
    ("InMemoryCheckpointStore", in_memory_checkpoints),
    ("SqliteCheckpointStore", sqlite_checkpoints),
)


def _slots_for(class_name: str, module: object) -> tuple[str, ...] | None:
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for sub in node.body:
                if (
                    isinstance(sub, ast.Assign)
                    and len(sub.targets) == 1
                    and isinstance(sub.targets[0], ast.Name)
                    and sub.targets[0].id == "__slots__"
                ):
                    if isinstance(sub.value, (ast.Tuple, ast.List)):
                        return tuple(
                            elt.value
                            for elt in sub.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        )
            return None
    return None


def test_ac14_in_memory_adapter_declares_slots() -> None:
    slots = _slots_for("InMemoryCheckpointStore", in_memory_checkpoints)
    assert slots is not None, (
        "InMemoryCheckpointStore must declare __slots__ — see AC-14 directive."
    )
    assert len(slots) > 0


def test_ac14_sqlite_adapter_declares_slots() -> None:
    slots = _slots_for("SqliteCheckpointStore", sqlite_checkpoints)
    assert slots is not None, "SqliteCheckpointStore must declare __slots__ — see AC-14 directive."
    assert len(slots) > 0


def test_s202_replay_verifier_declares_slots() -> None:
    """Phase-6 S2-02 AC-4 — ``ReplayVerifier`` declares ``__slots__ = ('_store',)``."""
    from codegenie.workflows import replay as replay_module

    slots = _slots_for("ReplayVerifier", replay_module)
    assert slots is not None, (
        "ReplayVerifier must declare __slots__ — S2-02 AC-4 typo-defense + "
        "memory discipline. Without __slots__, an executor accidentally "
        "adds self._cache: dict = {} for ad-hoc memoization, but caching "
        "verification results across verify() calls is dangerous (the "
        "underlying chain can be re-tampered between calls)."
    )
    assert slots == ("_store",), (
        f"ReplayVerifier __slots__ drift — got {slots!r}, want ('_store',). "
        "Any added slot must surface in PR review."
    )


def test_ac14_runtime_slots_enforce_attribute_set() -> None:
    """Runtime check — assigning an undeclared attribute raises AttributeError."""
    from pathlib import Path

    from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
    from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore

    store_mem = InMemoryCheckpointStore()
    try:
        try:
            store_mem._undeclared_typo = 42  # type: ignore[attr-defined]
            raise AssertionError(
                "InMemoryCheckpointStore accepted an undeclared attribute — "
                "__slots__ is not enforcing typo defense."
            )
        except AttributeError:
            pass
    finally:
        store_mem.close()

    store_sql = SqliteCheckpointStore(Path("/tmp"))
    try:
        try:
            store_sql._undeclared_typo = 42  # type: ignore[attr-defined]
            raise AssertionError(
                "SqliteCheckpointStore accepted an undeclared attribute — "
                "__slots__ is not enforcing typo defense."
            )
        except AttributeError:
            pass
    finally:
        # close() is safe even though no connection has been opened.
        store_sql.close()
