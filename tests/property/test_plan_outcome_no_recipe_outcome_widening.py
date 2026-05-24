"""Phase 4 S1-03 — ADR-0004 + Phase-7 exit-criterion fence.

Phase-3 ``RecipeOutcome``'s variant set must stay byte-identical to the
snapshot at ``tests/property/_recipe_outcome_phase3_snapshot.txt``. If this
fence fails, the introducing PR has silently broken the
"extension by addition" invariant — Phase 7's plugin diff would need new
``case`` arms in Phase-3/4/5/6 code, violating that phase's "diff touches
only the new plugin directory" exit criterion.

Inherited by every future phase. The failure message names ADR-0004
explicitly so the next reader knows where to look.
"""

from __future__ import annotations

import ast
import pathlib

# Canonical Phase-3 home of RecipeOutcome (verified against the source).
# The MODULE is imported (not the ``RecipeOutcome`` value) because
# ``RecipeOutcome`` is an ``Annotated[...]`` alias — a typing special form —
# and ``inspect.getfile(RecipeOutcome)`` raises ``TypeError`` on it (F3). The
# module object exposes its source file via ``.__file__``.
import codegenie.transforms.outcomes as _recipe_outcome_mod

SNAPSHOT = pathlib.Path(__file__).parent / "_recipe_outcome_phase3_snapshot.txt"


def _extract_variant_names_from_module(mod_path: pathlib.Path) -> set[str]:
    """Return the set of variant class names that compose ``RecipeOutcome``.

    Handles both ``RecipeOutcome = A | B | C`` (``ast.Assign``) and an
    annotated ``RecipeOutcome: TypeAlias = A | B | C`` (``ast.AnnAssign``,
    F11), with the RHS being either a bare union or
    ``Annotated[A | B | C, Field(...)/Discriminator(...)]``.
    """
    tree = ast.parse(mod_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "RecipeOutcome" for t in node.targets
        ):
            return _names_from_union_or_annotated(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RecipeOutcome"
            and node.value is not None
        ):
            return _names_from_union_or_annotated(node.value)
    raise AssertionError("RecipeOutcome declaration not found in expected module")


def _names_from_union_or_annotated(value: ast.AST) -> set[str]:
    """Unwrap ``Annotated[X | Y | Z, Discriminator(...)]`` and recurse over ``|``.

    Returns the leaf ``ast.Name`` ids; raises ``AssertionError`` if the RHS
    shape is unexpected (a defense against silent restructuring).
    """
    if (
        isinstance(value, ast.Subscript)
        and isinstance(value.value, ast.Name)
        and value.value.id == "Annotated"
    ):
        inner = value.slice.elts[0] if isinstance(value.slice, ast.Tuple) else value.slice
        return _names_from_union_or_annotated(inner)
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
        return _names_from_union_or_annotated(value.left) | _names_from_union_or_annotated(
            value.right
        )
    if isinstance(value, ast.Name):
        return {value.id}
    raise AssertionError(f"Unrecognized RecipeOutcome RHS shape: {ast.dump(value)}")


def test_recipe_outcome_variants_match_phase3_snapshot() -> None:
    snapshot = {line.strip() for line in SNAPSHOT.read_text().splitlines() if line.strip()}
    mod_file = _recipe_outcome_mod.__file__
    assert mod_file is not None, "codegenie.transforms.outcomes has no __file__"
    found = _extract_variant_names_from_module(pathlib.Path(mod_file))
    assert found == snapshot, (
        "RecipeOutcome variants drifted from Phase-3 snapshot — "
        "Phase 7's exit criterion is at risk; see ADR-0004. "
        f"Snapshot={sorted(snapshot)}, Found={sorted(found)}."
    )
