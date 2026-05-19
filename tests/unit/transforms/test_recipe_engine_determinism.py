"""Phase-3 S5-01 — :func:`match_recipes` iteration-order determinism.

Subprocess-launches a registration + walk script under multiple values of
``PYTHONHASHSEED`` and asserts byte-identical output across seeds. Catches
accidental reliance on dict-iteration ordering for the recipe sort.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    from codegenie.plugins.recipe_registry import RecipeRegistry, register_recipe
    from codegenie.transforms.outcomes import NotApplies
    from codegenie.types.identifiers import PluginId, RecipeId, TransformKind

    PID = PluginId("vulnerability-remediation--node--npm")
    KIND = TransformKind("npm_lockfile_semver_bump")

    def factory(rid, prec):
        return type(
            f"R_{rid}",
            (),
            {
                "recipe_id": RecipeId(rid),
                "name": rid,
                "kind": KIND,
                "precedence": prec,
                "applies": lambda self, cve, bundle: NotApplies(reason="PEER_DEP_CONFLICT"),
                "__init__": lambda self: None,
            },
        )

    reg = RecipeRegistry()
    for rid, prec in [("z", 1), ("a", 5), ("m", 10), ("b", 5)]:
        register_recipe(PID, registry=reg)(factory(rid, prec))

    print(",".join(r.recipe.name for r in reg.all(PID)))
    """
)


def test_iteration_order_stable_across_pythonhashseed() -> None:
    """AC-5 — same input under different ``PYTHONHASHSEED`` → same output."""
    outputs: list[str] = []
    for seed in ("0", "1", "2", "42"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(  # noqa: S603 — sys.executable trusted
            [sys.executable, "-c", _SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        # Only the script's ``print`` line is load-bearing — strip leading
        # structlog/log lines from package imports (timestamps drift).
        last = result.stdout.strip().splitlines()[-1]
        outputs.append(last)
    assert len(set(outputs)) == 1, f"Order drifted across seeds: {outputs}"
    assert outputs[0] == "m,a,b,z"
