"""Runtime-closure scan: ``codegenie.primitives.vuln_provenance`` must not
import any of ``FORBIDDEN_LLM_SDKS`` at module load time.

This fence extends the gather-pipeline closure assertion (Phase 7 ADR-0004 +
production ADR-0005) to the new bounded-additive primitive surface introduced
in Step 1 of Phase 7 (S1-01..S1-05). Without this scan a future story could
quietly add ``import anthropic`` inside one of the primitive submodules; the
``import-linter`` static contract in ``pyproject.toml`` is the parallel static
defense.

ADR-0011 framing: this is **audit + lint** enforcement (a runtime fence that
fires inside CI's pytest invocation), NOT a runtime guarantee. A primitive
author who lazy-imports an SDK inside a function body bypasses this scan —
the import-linter contract is the static complement, and CODEOWNERS on
``tests/fence/`` is the social anchor.

Mutation-resistance property: the live test and the parametrized planted-
positive tests both call ``_scan_primitive_runtime_closure()``. A regression
in the scanner kills both. Parity with the Phase 0 ``test_pyproject_fence``
and Phase 3 ``test_no_llm_in_transforms`` precedent.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final

import pytest
from packaging.utils import canonicalize_name

from codegenie._fence import FORBIDDEN_LLM_SDKS

_PRIMITIVE_PACKAGES: Final[tuple[str, ...]] = ("codegenie.primitives.vuln_provenance",)


def _walk_primitive_packages(packages: Iterable[str]) -> None:
    """Eagerly import every submodule of each primitive package.

    Calls :func:`importlib.invalidate_caches` first so the planted-positive
    tests reliably surface new files written after Python's ``FileFinder``
    cached the package directory. A syntax / import error surfaces as
    ``AssertionError`` with the failing module name (Rule 12 — fail loud,
    do not silently green)."""
    importlib.invalidate_caches()
    for pkg_name in packages:
        pkg = importlib.import_module(pkg_name)
        for mod_info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            try:
                importlib.import_module(mod_info.name)
            except ImportError as exc:
                raise AssertionError(
                    f"Phase-7 primitive runtime-closure scan failed to import "
                    f"{mod_info.name}: {exc}. Fix the underlying import error "
                    f"before re-running the fence."
                ) from exc


def _scan_primitive_runtime_closure() -> frozenset[str]:
    """Return the intersection of ``sys.modules`` with ``FORBIDDEN_LLM_SDKS``
    after walking ``codegenie.primitives.vuln_provenance``.

    Both the live check and the planted-positive tests call THIS function —
    a regression in the walker kills both (mutation-resistance).

    Phase-4 S1-05 / ADR-0003: ``FORBIDDEN_LLM_SDKS`` holds canonical PyPI
    *distribution* names (PEP 503 — ``sentence-transformers`` with a hyphen);
    ``sys.modules`` keys are Python *import* names. Canonicalize both for the
    intersection, then return canonical (distribution-name) leaked entries
    matching ``FORBIDDEN_LLM_SDKS`` shape so callers can compare directly."""
    _walk_primitive_packages(_PRIMITIVE_PACKAGES)
    canonical_forbidden = {canonicalize_name(n): n for n in FORBIDDEN_LLM_SDKS}
    leaked: set[str] = set()
    for mod in sys.modules:
        canonical = canonicalize_name(mod)
        if canonical in canonical_forbidden:
            leaked.add(canonical_forbidden[canonical])
    return frozenset(leaked)


# ---------------------------------------------------------------------------
# AC-3.a live check + AC-3.d import-success guard
# ---------------------------------------------------------------------------


def test_no_llm_sdk_imported_by_primitive_packages() -> None:
    """AC-3.a: a clean primitive closure imports zero LLM SDKs."""
    # Pre-clean: remove any LLM SDK that another test (or a prior run) may
    # have pre-populated so we measure ONLY what the primitive walk imports.
    # Phase-4 S1-05 / ADR-0003: pop by *canonical* match — ``sys.modules`` keys
    # are import names (``sentence_transformers``) while ``FORBIDDEN_LLM_SDKS``
    # holds distribution names (``sentence-transformers``); a literal-key pop
    # would silently miss the hyphenated entries.
    canonical_forbidden = {canonicalize_name(n) for n in FORBIDDEN_LLM_SDKS}
    saved: dict[str, object] = {}
    for mod_name in list(sys.modules.keys()):
        if canonicalize_name(mod_name) in canonical_forbidden:
            saved[mod_name] = sys.modules.pop(mod_name)
    try:
        leaked = _scan_primitive_runtime_closure()
        # AC-3.d: import-success guard — the walk must actually have run.
        for pkg in _PRIMITIVE_PACKAGES:
            assert pkg in sys.modules, (
                f"Primitive walk did not import {pkg}; silently-caught "
                f"ImportError must not green the fence."
            )
        assert leaked == frozenset(), (
            f"LLM SDK leaked into primitive runtime closure: {leaked}. "
            f"`primitives.vuln_provenance` is deterministic-only "
            f"(Phase 7 ADR-0004, production ADR-0005)."
        )
    finally:
        for sdk, mod in saved.items():
            sys.modules[sdk] = mod  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# AC-3.b per-SDK planted-positive (6 cases = 6 mutation guards)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sdk", sorted(FORBIDDEN_LLM_SDKS))
def test_scanner_catches_each_planted_sdk_under_primitive(
    sdk: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3.b: plant ONE forbidden SDK at a time as a fake stdlib-resolvable
    module then have a primitive submodule import it. The SAME scanner the
    live check uses MUST catch the leak.

    Phase-4 S1-05 / ADR-0003: ``FORBIDDEN_LLM_SDKS`` holds canonical PyPI
    *distribution* names (``sentence-transformers``); ``import`` statements
    use *import* names (``sentence_transformers``). Translate hyphens to
    underscores when synthesizing the planted module / import line."""
    # PEP 503: distribution name → import name (`-` → `_`). `import
    # sentence-transformers` is a SyntaxError.
    import_name = sdk.replace("-", "_")

    # 1. Create a temp directory hosting both the fake SDK and a temp primitive
    #    submodule that imports it.
    fake_sdk_dir = tmp_path / "fake_sdk_root"
    fake_sdk_dir.mkdir()
    fake_sdk_file = fake_sdk_dir / f"{import_name}.py"
    fake_sdk_file.write_text(
        f'"""Fake `{import_name}` for AC-3.b planted-positive test."""\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(fake_sdk_dir))

    # 2. Plant a temp submodule inside the primitive that imports the SDK.
    primitive_dir = Path("src/codegenie/primitives/vuln_provenance")
    planted_path = primitive_dir / f"_test_planted_{import_name}.py"
    planted_path.write_text(
        f"# Planted-positive AC-3.b fixture for {sdk!r}.\nimport {import_name}  # noqa: F401\n",
        encoding="utf-8",
    )

    # 3. Snapshot — and clear — only codegenie.primitives.vuln_provenance.* so
    #    the walker re-imports them fresh and picks up the planted submodule.
    snapshot: dict[str, object] = {}
    for mod_name in list(sys.modules.keys()):
        if mod_name == "codegenie.primitives.vuln_provenance" or mod_name.startswith(
            "codegenie.primitives.vuln_provenance."
        ):
            snapshot[mod_name] = sys.modules.pop(mod_name)
    sys.modules.pop(import_name, None)

    try:
        leaked = _scan_primitive_runtime_closure()
        assert sdk in leaked, (
            f"Scanner failed to catch planted `{sdk}` import "
            f"(imported via `{import_name}`). "
            f"sys.modules ∩ FORBIDDEN_LLM_SDKS = {leaked}"
        )
    finally:
        if planted_path.exists():
            planted_path.unlink()
        sys.modules.pop(import_name, None)
        # Drop the freshly-imported (post-scan) primitive modules and restore
        # the snapshot — subsequent tests see the SAME class identities they
        # had at collection time.
        for mod_name in list(sys.modules.keys()):
            if mod_name == "codegenie.primitives.vuln_provenance" or mod_name.startswith(
                "codegenie.primitives.vuln_provenance."
            ):
                sys.modules.pop(mod_name, None)
        for mod_name, mod in snapshot.items():
            sys.modules[mod_name] = mod  # type: ignore[assignment]
            # ``importlib.import_module`` rebinds each submodule as an attribute
            # on its parent package (e.g. ``codegenie.primitives.vuln_provenance``
            # on ``codegenie.primitives``). Restoring ``sys.modules`` alone is
            # NOT enough — without re-setting the parent attribute, subsequent
            # ``from pkg import submod`` resolves to the fresh class, breaking
            # ``is``-identity for any name captured at collection time
            # (e.g. ``Layer``, ``Ecosystem``). Re-set the parent attribute now.
            parent_name, _, child_name = mod_name.rpartition(".")
            if parent_name and parent_name in sys.modules:
                setattr(sys.modules[parent_name], child_name, mod)


# ---------------------------------------------------------------------------
# AC-3.c metamorphic complement: SDK outside primitive closure must NOT fire
# ---------------------------------------------------------------------------


def test_scanner_ignores_llm_sdk_present_outside_primitive_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3.c: pre-populate ``sys.modules["anthropic"]`` via a fake module
    NOT imported by ``codegenie.primitives.vuln_provenance``. The live check
    pre-cleans ``sys.modules`` before walking; this complement proves that
    if pre-cleaning is in place, the scanner observes zero SDKs even though
    one was globally present at the start of the test.
    """
    fake_dir = tmp_path / "fake_outside"
    fake_dir.mkdir()
    (fake_dir / "anthropic.py").write_text(
        '"""Fake `anthropic` outside the primitive closure."""\n', encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(fake_dir))
    importlib.import_module("anthropic")
    try:
        # Walk packages (does NOT pop pre-existing modules — so anthropic stays).
        _walk_primitive_packages(_PRIMITIVE_PACKAGES)
        # Confirm that anthropic is in sys.modules ONLY because we planted it,
        # NOT because the primitive imported it.
        assert "anthropic" in sys.modules
        # The metamorphic property: the LIVE check pre-cleans sys.modules, so
        # the same scanner under that test would return an empty set.
        for sdk in FORBIDDEN_LLM_SDKS:
            sys.modules.pop(sdk, None)
        post_clean_leaked = frozenset(sys.modules.keys() & FORBIDDEN_LLM_SDKS)
        assert post_clean_leaked == frozenset(), (
            "After pre-cleaning, sys.modules must contain zero LLM SDKs — "
            "this proves the primitive walk did not re-import anthropic."
        )
    finally:
        sys.modules.pop("anthropic", None)


# ---------------------------------------------------------------------------
# AC-3.e module-level docstring framing check
# ---------------------------------------------------------------------------


def test_module_docstring_names_adr_framing() -> None:
    """AC-3.e: docstring MUST name Phase 7 ADR-0004 + production ADR-0005 and
    flag this as audit + lint (not runtime) — so a future operator reading
    the test file does not over-trust the gate."""
    module = importlib.import_module(__name__)
    assert module.__doc__ is not None
    doc = module.__doc__.lower()
    assert "adr-0004" in doc, "Module docstring must reference Phase 7 ADR-0004."
    assert "adr-0005" in doc, "Module docstring must reference production ADR-0005."
    assert "audit + lint" in doc or "audit and lint" in doc
    assert "not a runtime guarantee" in doc
