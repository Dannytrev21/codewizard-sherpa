"""S1-11 — repo-wide mypy ``warn_unreachable`` invariants (AC-4).

Phase 0 S1-02 set ``warn_unreachable = true`` repo-wide (``pyproject.toml``
line 134, commit ``3944f02``). This story does not narrow the scope; it
verifies the broader-than-arch invariant survives.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-11-forbidden-patterns-mypy-adrs.md``
  §AC-4.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md
  §"CI gates"`` job 7 — the *narrower* per-module prescription Phase 0
  superseded.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# The five named modules from arch §"CI gates" job 7 — the load-bearing
# exhaustiveness consumers in Phase 2.
NAMED_MODULES = (
    "codegenie.indices.*",
    "codegenie.probes.layer_b.index_health",
    "codegenie.report.*",
    "codegenie.adapters.*",
    "codegenie.tccm.*",
)


def test_repo_wide_warn_unreachable_is_true() -> None:
    """AC-4 — Phase 0 S1-02 set this repo-wide. If a future PR removes the
    line, the broader-than-arch invariant breaks silently — this test prevents
    that.
    """
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert cfg["tool"]["mypy"]["warn_unreachable"] is True, (
        "[tool.mypy] warn_unreachable = true must remain set; see story S1-11 §"
        "Validation notes and arch §'CI gates' job 7."
    )


def test_no_override_disables_warn_unreachable_for_named_modules() -> None:
    """AC-4 — defense-in-depth. The repo-wide setting covers the five named
    modules; this test prevents a future ``[[tool.mypy.overrides]]`` block
    from silently weakening it on any of them.
    """
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    overrides = cfg.get("tool", {}).get("mypy", {}).get("overrides", [])
    for o in overrides:
        if o.get("warn_unreachable") is False:
            mod = o.get("module")
            mods = [mod] if isinstance(mod, str) else list(mod or [])
            for m in mods:
                assert m not in NAMED_MODULES, (
                    f"override silently disables warn_unreachable for {m}; forbidden by S1-11 AC-4"
                )
