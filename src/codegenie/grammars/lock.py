"""Tree-sitter grammar kernel — PyPI-wheel-backed ``language_for`` (02-ADR-0011).

This module is the typed boundary every probe that needs a tree-sitter
``Language`` calls through. Consumers ask for a language by name
(``"typescript"``, ``"javascript"``, ``"tsx"``); the kernel imports the
matching PyPI grammar package and constructs the modern
``tree_sitter.Language(<PyCapsule>)`` value. Probes NEVER import
``tree_sitter_typescript`` / ``tree_sitter_javascript`` directly — the
indirection is what makes adding Phase 8's Python grammar a single
new dispatch row, with zero edits to consumers.

The grammar **lock** is `pyproject.toml`'s pinned version + `pip
--require-hashes` (Phase 0 ADR-0006). The legacy ``tools/grammars.lock``
BLAKE3-of-binary model from 02-ADR-0002 is removed; the supersession
rationale lives in 02-ADR-0011.

Construction is **memoized** per language — the underlying C extension
loads once per process, and a ``Language`` value is safe to share
across parsers. The memo collapses repeat constructions into one
without exposing global state to the kernel's API.

The kernel raises :class:`GrammarLoadRefused` on every failure path —
import failure, unknown language name, or grammar-load failure — so
callers can pattern-match a single typed exception (Rule 9: tests
verify intent; one branch type, one ``except`` clause).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md``
- Superseded
  ``docs/phases/02-context-gather-layers-b-g/ADRs/0002-tree-sitter-grammars-phase-2-amendment.md``
"""

from __future__ import annotations

import functools
import importlib
from typing import TYPE_CHECKING, Final, Literal, get_args

if TYPE_CHECKING:
    from tree_sitter import Language

__all__ = [
    "GrammarLoadRefused",
    "SupportedLanguage",
    "language_for",
    "supported_languages",
]


SupportedLanguage = Literal["typescript", "tsx", "javascript"]
"""Languages the kernel can vend. Add a Phase-8 row (e.g. ``"python"``)
by extending this Literal AND the dispatch table in :func:`language_for`."""


class GrammarLoadRefused(RuntimeError):
    """Raised when the kernel cannot return a usable ``Language``.

    Three causes are folded into one type so callers write a single
    ``except`` clause:

    1. The matching PyPI grammar package is missing from the runtime
       closure (``ImportError`` — closure regression; pyproject pin
       was dropped or the install is broken).
    2. The language name is not in :data:`SupportedLanguage`.
    3. The capsule from the grammar package failed to construct a
       ``Language`` (signals an ABI mismatch — wheel was built for
       a different ``tree-sitter`` major).

    The message names the failing language so an operator grepping
    logs can locate the affected grammar without re-running.
    """


_DISPATCH: Final[dict[str, tuple[str, str]]] = {
    # language-name → (pypi-module-name, capsule-factory-attr)
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "javascript": ("tree_sitter_javascript", "language"),
}


def supported_languages() -> tuple[str, ...]:
    """Return the tuple of language names the kernel can vend.

    Used by tests + future ``language_for`` callers that want to
    enumerate (e.g., dispatch tables that mirror the kernel's surface).
    """
    return tuple(sorted(_DISPATCH))


@functools.lru_cache(maxsize=len(_DISPATCH))
def _build_language(name: str) -> Language:
    """Construct the ``Language`` for *name* — cached per process."""
    try:
        capsule_factory_name = _DISPATCH[name]
    except KeyError as exc:
        raise GrammarLoadRefused(
            f"unsupported language={name!r}; supported={supported_languages()}"
        ) from exc

    module_name, factory_attr = capsule_factory_name

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise GrammarLoadRefused(
            f"grammar package {module_name!r} missing from runtime closure "
            f"(language={name!r}); install via `pip install {module_name}` "
            f"or check pyproject.toml"
        ) from exc

    try:
        factory = getattr(module, factory_attr)
        capsule = factory()
    except (AttributeError, RuntimeError) as exc:
        raise GrammarLoadRefused(
            f"grammar package {module_name!r} did not expose "
            f"{factory_attr!r} (language={name!r}); upstream wheel layout drift"
        ) from exc

    # Imported lazily so ``tree_sitter`` itself can be absent in
    # documentation-only environments without breaking the import graph.
    try:
        from tree_sitter import Language as _Language
    except ImportError as exc:
        raise GrammarLoadRefused(
            f"tree_sitter runtime missing (language={name!r}); "
            f"install via `pip install tree-sitter` or check pyproject.toml"
        ) from exc

    try:
        return _Language(capsule)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise GrammarLoadRefused(
            f"tree_sitter.Language(<capsule>) refused {name!r} grammar "
            f"(ABI mismatch? tree-sitter / {module_name} versions disagree)"
        ) from exc


def language_for(name: SupportedLanguage) -> Language:
    """Return the tree-sitter ``Language`` for *name*.

    Memoized — repeat calls in the same process return the same
    ``Language`` object. Probes call this per file via the shared
    parser path; one C-ext load per language per process.

    Args:
        name: One of :data:`SupportedLanguage`.

    Returns:
        A constructed :class:`tree_sitter.Language` ready to drop into
        a ``tree_sitter.Parser`` or compile a ``Query`` against.

    Raises:
        GrammarLoadRefused: On any failure surface (missing package,
            unknown language, capsule factory drift, ABI mismatch).
            The exception type is single so callers write one
            ``except`` clause — the message disambiguates the cause.
    """
    if name not in get_args(SupportedLanguage):
        raise GrammarLoadRefused(
            f"unsupported language={name!r}; supported={supported_languages()}"
        )
    return _build_language(name)
