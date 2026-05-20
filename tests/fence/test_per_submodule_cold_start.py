"""Fence — every public ``codegenie.*`` submodule imports cleanly as the
*first* import in a fresh Python subprocess.

Static circular imports between codegenie submodules are easy to introduce
and almost impossible to notice inside the pytest suite: by the time
collection reaches any given test module, dozens of earlier imports have
already loaded ``codegenie.probes``, ``codegenie.types.identifiers``, etc.,
priming sys.modules so the cycle short-circuits. The bug is real in source
but only fires when a downstream consumer imports a specific submodule
*first* — e.g. a REPL one-liner, a notebook, the SDK, another tool.

Discovered 2026-05-19 when ``from codegenie.plugins.manifest import PluginManifest``
crashed with ``cannot import name 'PackageManager' from partially initialized
module 'codegenie.types.identifiers'`` — the cycle being
``types/identifiers → probes/node_build_system → probes/__init__ → layer_b/dep_graph
→ depgraph/__init__ → depgraph/registry → types/identifiers``. The failure
intermittently reproduces under bare ``python -c``; the pytest suite never
catches it because conftest collection has already loaded probes first.

Mirrors the fresh-subprocess idiom of ``tests/unit/test_cli_cold_start.py``
(per-package level) — this is the per-submodule generalisation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_SRC_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "src" / "codegenie"

# Modules deliberately excluded from the import sweep — each with a
# one-line justification. Keep this set as small as possible; the goal of
# this fence is that *every* submodule round-trips.
_SKIP: Final[frozenset[str]] = frozenset(
    {
        # S3-02 — Alembic migration scripts are internal plumbing only
        # invocable through ``command.upgrade(cfg, "head")``; they import
        # ``alembic.op`` at module top which crashes when imported without
        # an Alembic ``context`` set up. Callers reach them via the public
        # ``VulnIndex._upgrade`` seam, which is fenced separately by
        # ``tests/unit/vuln_index/test_cold_start.py`` (AC-L2).
        "codegenie.vuln_index.migrations.env",
        "codegenie.vuln_index.migrations.versions.0001_initial_schema",
    }
)

# Empty. The ``types/identifiers → probes/node_build_system → probes/__init__
# → layer_b/dep_graph → depgraph/__init__ → depgraph/registry →
# types/identifiers`` circular that quarantined 28 modules was fixed by
# ADR-0013 Amendment 2026-05-20 — ``PackageManager``'s definition home moved
# to the kernel-tier ``codegenie.types.identifiers``, so ``types`` no longer
# depends on the ``probes`` leaf. The set stays declared (and
# ``test_known_broken_set_is_empty`` keeps it empty) as a re-quarantine
# mechanism: a future regression may add an entry ONLY alongside a tracked fix.
_KNOWN_BROKEN_PRE_FIX: Final[frozenset[str]] = frozenset()


def _discover_submodules() -> list[str]:
    """Walk ``src/codegenie/`` for every importable ``.py`` and return the
    dotted module names.

    Excludes ``__pycache__``, ``__main__``, and private ``_*`` modules
    (leading-underscore is the convention for non-public helpers; if they
    cycle, the public module that imports them surfaces it).
    """
    modules: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(_SRC_ROOT.parent)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        elif parts[-1] == "__main__":
            continue
        # Skip private modules — by convention, callers reach them via the
        # public sibling, which is what we're really fencing.
        if any(p.startswith("_") and p != "__init__" for p in parts):
            continue
        dotted = ".".join(parts)
        if dotted in _SKIP:
            continue
        modules.append(dotted)
    assert modules, "submodule discovery returned nothing — check _SRC_ROOT"
    return modules


_SUBMODULES: Final[list[str]] = _discover_submodules()


@pytest.mark.parametrize("module", _SUBMODULES, ids=lambda m: m)
def test_submodule_imports_in_fresh_subprocess(module: str) -> None:
    """``import {module}`` exits 0 in a fresh subprocess.

    Catches any static import cycle whose only victim is a consumer that
    imports the affected module *first* — invisible to the rest of the
    test suite because pytest's shared interpreter already has the cycle's
    other end loaded by the time the test runs.

    A failure here means the import graph has a latent fragility. The fix
    is usually to move the offending re-export to a neutral module or to
    use ``TYPE_CHECKING`` to defer the cyclic reference (cf. the
    canonical Phase 3 ``codegenie.plugins.protocols`` pattern).

    :data:`_KNOWN_BROKEN_PRE_FIX` is empty (the cold-start cycle was fixed —
    ADR-0013 Amendment 2026-05-20); the skip branch below is the
    re-quarantine mechanism, and :func:`test_known_broken_set_is_empty`
    guards that the set stays empty.
    """
    if module in _KNOWN_BROKEN_PRE_FIX:
        pytest.skip(
            f"Known cold-start failure pending circular-import fix "
            f"(spawned task 'Break circular import in codegenie.plugins.manifest'). "
            f"Module: {module}."
        )
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        f"Fresh-subprocess `import {module}` failed (exit={result.returncode}).\n"
        f"--- stderr ---\n{result.stderr}\n"
        f"--- stdout ---\n{result.stdout}"
    )


def test_known_broken_set_is_empty() -> None:
    """The cold-start quarantine set MUST stay empty.

    The 28-module ``types/identifiers → probes → depgraph →
    types/identifiers`` cycle was fixed by ADR-0013 Amendment 2026-05-20.
    This is now a permanent guard: re-adding an entry to
    ``_KNOWN_BROKEN_PRE_FIX`` (re-quarantining a module instead of fixing
    the regression) fails here.
    """
    assert _KNOWN_BROKEN_PRE_FIX == frozenset(), (
        f"_KNOWN_BROKEN_PRE_FIX has {len(_KNOWN_BROKEN_PRE_FIX)} entries "
        f"({sorted(_KNOWN_BROKEN_PRE_FIX)}); a cold-start circular import "
        f"regressed — fix it, do not quarantine."
    )
