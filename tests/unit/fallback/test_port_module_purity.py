"""Phase-4 S3-01 AC-4 — ``port.py`` is SDK / HTTP / socket / ssl-free.

Two assertions, both AST-scans of ``src/codegenie/fallback/leaf/port.py``:

(a) Named-forbidden set — yields a precise diagnostic if any of the explicit
    HTTP/SDK/socket modules are imported.
(b) Namespace rule — every import resolves to stdlib, ``pydantic``, or a
    ``codegenie.*`` module. Framing (b) as a namespace rule (rather than an
    exact frozenset) keeps the test robust when sibling Step-1/Step-2 modules
    move.

The single AST scanner under ``tests/fence/`` (``_phase4_scanner.walk_imports``)
is reused for (a). (b) needs the **full** top-level package set, not just the
"forbidden-package matches" set walk_imports returns, so a tiny local AST walk
is justified here — duplicating the scanner kernel is exactly what AC-4 of the
S1-05 phase-4 fence story forbids, but enumerating *all* package imports for a
single file does not duplicate it.
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import Final

import codegenie
from tests.fence._phase4_scanner import walk_imports

PORT_FILE: Final[pathlib.Path] = (
    pathlib.Path(codegenie.__file__).parent / "fallback" / "leaf" / "port.py"
)

# AC-4 (a) — named-forbidden HTTP/SDK/socket/ssl modules. ``port.py`` is the
# Protocol seam; concrete adapter (anthropic, httpx) lives behind it in
# ``anthropic_adapter.py``.
_FORBIDDEN_IN_PORT: Final[frozenset[str]] = frozenset(
    {"anthropic", "httpx", "requests", "urllib3", "aiohttp", "socket", "ssl"}
)

# Pydantic is the only admitted third-party import in ``port.py``.
_ADMITTED_THIRD_PARTY: Final[frozenset[str]] = frozenset({"pydantic"})


def _all_top_level_packages(file: pathlib.Path) -> set[str]:
    """Return every top-level package name imported by ``file``.

    ``walk_imports`` returns only ``(file, package)`` violations for a fixed
    forbidden set; AC-4 (b) needs the *full* import surface for a single file
    so we can negate-classify ("anything not stdlib / pydantic / codegenie is
    a violation"). One ``ast.walk`` over one file — not a parallel scanner.
    """
    tree = ast.parse(file.read_text(encoding="utf-8"))
    pkgs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                pkgs.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            pkgs.add(node.module.split(".", 1)[0])
    return pkgs


def test_port_does_not_import_named_forbidden_modules() -> None:
    """AC-4 (a) — none of anthropic / httpx / requests / urllib3 / aiohttp / socket / ssl."""
    offenders = walk_imports([PORT_FILE], forbidden=_FORBIDDEN_IN_PORT)
    assert not offenders, (
        "port.py imports a named-forbidden HTTP/SDK/socket/ssl module; "
        "the Protocol seam must stay SDK-free (ADR-0003 path-scoped fence). "
        f"Offenders: {offenders}"
    )


def test_port_third_party_imports_are_pydantic_only() -> None:
    """AC-4 (b) — every import is stdlib, pydantic, or codegenie.*.

    Framed as a namespace rule rather than an exact frozenset (validator
    DP3 / C2) so relocating sibling Step-1/Step-2 modules does not break the
    fence.
    """
    stdlib = set(sys.stdlib_module_names)
    pkgs = _all_top_level_packages(PORT_FILE)
    offenders = sorted(
        pkg
        for pkg in pkgs
        if pkg not in stdlib
        and pkg not in _ADMITTED_THIRD_PARTY
        and not pkg.startswith("codegenie")
    )
    assert not offenders, (
        "port.py imports a third-party module other than pydantic. Only stdlib, "
        f"pydantic, and codegenie.* are admitted at the Protocol seam. Offenders: {offenders}"
    )
