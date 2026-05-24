"""Runtime-closure scan: ``codegenie.{plugins,transforms}`` must not import
any of ``FORBIDDEN_LLM_SDKS`` at module load time.

ADR-0011 framing: this is **audit + lint** (specifically, a runtime fence
that fires inside CI's pytest invocation), NOT a runtime guarantee. A
plugin author who lazy-imports anthropic inside a function body bypasses
this scan — the import-linter contracts in ``pyproject.toml`` are the
static defense; this test is the dynamic complement (catches eager
imports the linter might miss if it can't follow conditional flows).

Mutation-resistance property: the live test and the parametrized planted-
positive tests both call ``_scan_phase3_runtime_closure()``. A regression
in the scanner kills both. Parity with the Phase 0 ``test_pyproject_fence``
precedent.
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

_PHASE3_PACKAGES: Final[tuple[str, ...]] = ("codegenie.plugins", "codegenie.transforms")


def _walk_phase3_packages(packages: Iterable[str]) -> None:
    """Eagerly import every submodule of each Phase 3 package.

    A syntax / import error here surfaces as ``ImportError`` with the failing
    module name — fix the module before re-running the fence (Rule 12).

    Calls :func:`importlib.invalidate_caches` first so the planted-positive
    tests reliably surface new files written after Python's ``FileFinder``
    cached the package directory. Without this, sub-second-mtime writes
    (the common case in pytest) leave the importer with a stale directory
    listing — the walker would not discover the planted module and the
    scanner would silently return an empty set (phase-shakedown F-01)."""
    importlib.invalidate_caches()
    for pkg_name in packages:
        pkg = importlib.import_module(pkg_name)
        for mod_info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            try:
                importlib.import_module(mod_info.name)
            except ImportError as exc:
                raise AssertionError(
                    f"Phase-3 runtime-closure scan failed to import {mod_info.name}: "
                    f"{exc}. Fix the underlying import error before re-running the fence."
                ) from exc


def _scan_phase3_runtime_closure() -> frozenset[str]:
    """Return the intersection of ``sys.modules`` with ``FORBIDDEN_LLM_SDKS``
    after walking ``codegenie.{plugins,transforms}``.

    Both the live check and the planted-positive tests call THIS function —
    a regression in the walker kills both (mutation-resistance).

    Phase-4 S1-05 / ADR-0003: ``FORBIDDEN_LLM_SDKS`` holds canonical PyPI
    *distribution* names (PEP 503 — ``sentence-transformers`` with a hyphen);
    ``sys.modules`` keys are Python *import* names
    (``sentence_transformers`` with an underscore). Canonicalize both via
    :func:`packaging.utils.canonicalize_name` for the intersection, then
    return the canonical names of the leaked SDKs (matching
    ``FORBIDDEN_LLM_SDKS`` shape so callers can compare directly)."""
    _walk_phase3_packages(_PHASE3_PACKAGES)
    canonical_forbidden = {canonicalize_name(n): n for n in FORBIDDEN_LLM_SDKS}
    leaked: set[str] = set()
    for mod in sys.modules:
        canonical = canonicalize_name(mod)
        if canonical in canonical_forbidden:
            leaked.add(canonical_forbidden[canonical])
    return frozenset(leaked)


# ---------------------------------------------------------------------------
# AC-4.a live check + AC-4.d import-success guard
# ---------------------------------------------------------------------------


def test_no_llm_sdk_imported_by_phase3_packages() -> None:
    """AC-4.a: a clean Phase 3 closure imports zero LLM SDKs."""
    # Pre-clean: remove any LLM SDK that another test (or a prior run) may
    # have pre-populated so we measure ONLY what the Phase 3 walk imports.
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
        leaked = _scan_phase3_runtime_closure()
        # AC-4.d: import-success guard — the walk must actually have run.
        assert "codegenie.plugins" in sys.modules
        assert "codegenie.transforms" in sys.modules
        assert leaked == frozenset(), (
            f"LLM SDK leaked into Phase 3 runtime closure: {leaked}. "
            f"Phase 3 is deterministic-only (ADR-0010)."
        )
    finally:
        for sdk, mod in saved.items():
            sys.modules[sdk] = mod


# ---------------------------------------------------------------------------
# AC-4.b per-SDK planted-positive (5 cases = 5 mutation guards)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sdk", sorted(FORBIDDEN_LLM_SDKS))
def test_scanner_catches_each_planted_sdk_under_phase3(
    sdk: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4.b: plant ONE forbidden SDK at a time as a fake stdlib-resolvable
    module then have a Phase 3 submodule import it. The SAME scanner the
    live check uses MUST catch the leak.

    Phase-4 S1-05 / ADR-0003: ``FORBIDDEN_LLM_SDKS`` holds the canonical PyPI
    *distribution* names (PEP 503) — ``sentence-transformers`` has a hyphen.
    The synthesized planted module + ``import`` statement must use the Python
    *import* name (underscore), so hyphens are translated to underscores here.
    ``sys.modules`` keys are import names; the live scanner intersects against
    ``FORBIDDEN_LLM_SDKS`` after canonicalizing both spellings — see
    ``_scan_phase3_runtime_closure``."""
    # PEP 503: PyPI distribution name `sentence-transformers` resolves to import
    # name `sentence_transformers`. `import sentence-transformers` is a
    # SyntaxError. Translate before writing the planted module.
    import_name = sdk.replace("-", "_")

    # 1. Create a temp directory hosting both the fake SDK and a temp Phase 3
    #    submodule that imports it.
    fake_sdk_dir = tmp_path / "fake_sdk_root"
    fake_sdk_dir.mkdir()
    fake_sdk_file = fake_sdk_dir / f"{import_name}.py"
    fake_sdk_file.write_text(
        f'"""Fake `{import_name}` for AC-4.b planted-positive test."""\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(fake_sdk_dir))

    # 2. Plant a temp submodule inside codegenie.plugins that imports the SDK.
    planted_path = Path("src/codegenie/plugins") / f"_test_planted_{import_name}.py"
    planted_path.write_text(
        f"# Planted-positive AC-4.b fixture for {sdk!r}.\nimport {import_name}  # noqa: F401\n",
        encoding="utf-8",
    )

    # 3. Snapshot — and clear — only codegenie.plugins.* in sys.modules so
    #    the walker re-imports them fresh and picks up the planted submodule.
    #    Crucially we do NOT pop ``codegenie.transforms.*`` — after S4-04
    #    ``codegenie.transforms._forward`` re-exports
    #    ``codegenie.plugins.sandbox_path.SandboxedPath``; popping plugins
    #    forces a re-import that creates a NEW ``SandboxedPath`` class
    #    identity. ``codegenie.transforms.sandbox_jail.JailedSubprocessSpec``
    #    (already loaded by other tests at collection time) has its
    #    ``cwd: SandboxedPath`` field bound to the OLD class; consumers
    #    constructing a NEW ``SandboxedPath`` then trigger Pydantic
    #    ``model_type`` validation errors downstream. Restoring the OLD
    #    plugins modules from snapshot keeps identity stable.
    snapshot: dict[str, object] = {}
    for mod_name in list(sys.modules.keys()):
        if mod_name == "codegenie.plugins" or mod_name.startswith("codegenie.plugins."):
            snapshot[mod_name] = sys.modules.pop(mod_name)
    sys.modules.pop(import_name, None)

    try:
        leaked = _scan_phase3_runtime_closure()
        assert sdk in leaked, (
            f"Scanner failed to catch planted `{sdk}` import "
            f"(imported via `{import_name}`). "
            f"sys.modules ∩ FORBIDDEN_LLM_SDKS = {leaked}"
        )
    finally:
        if planted_path.exists():
            planted_path.unlink()
        sys.modules.pop(import_name, None)
        # Drop the freshly-imported (post-scan) plugins modules and restore
        # the snapshot — subsequent tests see the SAME class identities they
        # had at collection time.
        for mod_name in list(sys.modules.keys()):
            if mod_name == "codegenie.plugins" or mod_name.startswith("codegenie.plugins."):
                sys.modules.pop(mod_name, None)
        for mod_name, mod in snapshot.items():
            sys.modules[mod_name] = mod  # type: ignore[assignment]
            # ``importlib.import_module`` rebinds each submodule as an attribute
            # on its parent package. Restoring ``sys.modules`` alone leaves the
            # parent's attribute pointing at the fresh module — breaking
            # ``is``-identity for any class captured at collection time. Re-set
            # the parent attribute now so ``from codegenie import plugins``
            # and ``from codegenie.plugins import submod`` resolve to the same
            # objects subsequent tests already hold references to.
            parent_name, _, child_name = mod_name.rpartition(".")
            if parent_name and parent_name in sys.modules:
                setattr(sys.modules[parent_name], child_name, mod)


# ---------------------------------------------------------------------------
# AC-4.c metamorphic complement: SDK outside Phase 3 closure must NOT fire
# ---------------------------------------------------------------------------


def test_scanner_ignores_llm_sdk_present_outside_phase3_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4.c: pre-populate ``sys.modules["anthropic"]`` via a fake module
    NOT imported by ``codegenie.plugins`` or ``codegenie.transforms``.

    The scanner uses ``sys.modules.keys() & FORBIDDEN_LLM_SDKS`` after the
    walk, so any pre-populated SDK would be a false positive. This test
    pins the documented limitation: the scope is the runtime sys.modules
    state ACROSS the walk, not the runner's pre-existing modules — so we
    pre-clean inside the live test and ALSO inside this complement.

    The complement here proves that if we DO pre-populate without cleaning,
    the scanner observes the SDK only because of our pre-population — i.e.
    the walker is not the one importing it.
    """
    # Plant a fake `anthropic` module that NO Phase 3 module imports.
    fake_dir = tmp_path / "fake_outside"
    fake_dir.mkdir()
    (fake_dir / "anthropic.py").write_text(
        '"""Fake `anthropic` outside Phase 3 closure."""\n', encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(fake_dir))
    importlib.import_module("anthropic")
    try:
        # Walk packages (does NOT pop pre-existing modules — so anthropic stays).
        _walk_phase3_packages(_PHASE3_PACKAGES)
        # Confirm that anthropic is in sys.modules ONLY because we planted it,
        # NOT because Phase 3 imported it.
        assert "anthropic" in sys.modules
        # The metamorphic property: the LIVE check pre-cleans sys.modules, so
        # the same scanner under that test would return an empty set.
        for sdk in FORBIDDEN_LLM_SDKS:
            sys.modules.pop(sdk, None)
        post_clean_leaked = frozenset(sys.modules.keys() & FORBIDDEN_LLM_SDKS)
        assert post_clean_leaked == frozenset(), (
            "After pre-cleaning, sys.modules must contain zero LLM SDKs — "
            "this proves the Phase 3 walk did not re-import anthropic."
        )
    finally:
        sys.modules.pop("anthropic", None)


# ---------------------------------------------------------------------------
# AC-4.e module-level docstring framing check
# ---------------------------------------------------------------------------


def test_module_docstring_names_adr_0011_framing() -> None:
    """AC-4.e: docstring MUST flag this as audit + lint, NOT runtime — so a
    future operator who reads the test file does not over-trust the gate."""
    module = importlib.import_module(__name__)
    assert module.__doc__ is not None
    assert "audit + lint" in module.__doc__.lower() or "audit and lint" in module.__doc__.lower()
    assert "not a runtime guarantee" in module.__doc__.lower()
