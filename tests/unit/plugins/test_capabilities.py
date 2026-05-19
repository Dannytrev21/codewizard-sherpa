"""Tests for ``codegenie.plugins.capabilities`` — S4-05 / 03-ADR-0011.

Covers:

* AC-10 — module exports the exact public surface.
* AC-11 — every capability is frozen + ``extra="forbid"``.
* AC-12 — ``GitLocalOpsCapability`` has no ``push`` field (type-level invariant).
* AC-13 — :func:`mint` is the only constructor of capabilities (AST scan).
* AC-14 — :func:`mint` emits :class:`CapabilityMinted` via the module-level
  chokepoint with a deterministic ``bundle_digest``.
* AC-Sub-4 — :class:`CapabilityBundle` rejects zero-non-None and two-non-None.
* AC-Sub-5 — :data:`CapabilityScope` is a closed sum type; :func:`mint`
  dispatches on each variant.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

import codegenie.plugins.capabilities as capabilities_mod
from codegenie.plugins.capabilities import (
    CapabilityBundle,
    CapabilityMinted,
    CapabilityScope,
    FsReadWriteCapability,
    FsScope,
    GitLocalOpsCapability,
    GitLocalOpsScope,
    NpmInstallCapability,
    NpmScope,
    mint,
)
from codegenie.plugins.sandbox_path import SandboxedPath
from codegenie.types.identifiers import PluginId, RegistryUrl

_PLUGIN: PluginId = PluginId("vulnerability-remediation--node--npm")
_REGISTRY: RegistryUrl = RegistryUrl("https://registry.npmjs.org")


def _sp(tmp_path: Path) -> SandboxedPath:
    """Construct a real SandboxedPath under *tmp_path*."""
    return SandboxedPath.create(jail=tmp_path, relative=Path(".")).unwrap()


# ───────────────────────────────────────────────────────────────────────────
# AC-10 — module exports exactly the documented public surface.
# ───────────────────────────────────────────────────────────────────────────


def test_module_all_exports_exact_set() -> None:
    """AC-10 — ``__all__`` is the closed contract surface of the module."""
    assert set(capabilities_mod.__all__) == {
        "CapabilityBundle",
        "CapabilityMinted",
        "CapabilityScope",
        "FsReadWriteCapability",
        "FsScope",
        "GitLocalOpsCapability",
        "GitLocalOpsScope",
        "NpmInstallCapability",
        "NpmScope",
        "mint",
    }


# ───────────────────────────────────────────────────────────────────────────
# AC-11 — frozen + ``extra="forbid"`` on every capability.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cls",
    [NpmInstallCapability, FsReadWriteCapability, GitLocalOpsCapability],
)
def test_capability_rejects_unknown_field(cls: type[BaseModel]) -> None:
    """AC-11 — ``extra="forbid"`` rejects unknown fields. A mutant
    dropping ``frozen=True`` survives THIS assertion alone (see
    next test)."""
    with pytest.raises(ValidationError):
        cls(surprise="x")


def test_npm_capability_rejects_attribute_reassignment(tmp_path: Path) -> None:
    """AC-11 — ``frozen=True`` rejects attribute reassignment on a fully-
    constructed valid instance. Independent assertion from the
    extra="forbid" check so a mutant dropping one config key cannot
    pass both kills.
    """
    inst = NpmInstallCapability(registry=_REGISTRY, _minted_by=_PLUGIN)
    with pytest.raises(ValidationError):
        inst.registry = RegistryUrl("https://other")


def test_fs_capability_rejects_attribute_reassignment(tmp_path: Path) -> None:
    inst = FsReadWriteCapability(scope=_sp(tmp_path), _minted_by=_PLUGIN)
    with pytest.raises(ValidationError):
        inst.scope = _sp(tmp_path)


def test_git_capability_rejects_attribute_reassignment(tmp_path: Path) -> None:
    inst = GitLocalOpsCapability(
        repo=_sp(tmp_path), branch_namespace="codegenie/", _minted_by=_PLUGIN
    )
    with pytest.raises(ValidationError):
        inst.branch_namespace = "other/"


@pytest.mark.parametrize(
    "cls",
    [NpmInstallCapability, FsReadWriteCapability, GitLocalOpsCapability],
)
def test_capability_model_config_keys_are_pinned(cls: type[BaseModel]) -> None:
    """AC-11 — explicit structural assertion on the ``model_config`` keys.
    Catches a regression that replaces ``ConfigDict(frozen=True,
    extra="forbid")`` with ``ConfigDict()`` (empty) and re-introduces
    mutation + unknown-field acceptance."""
    assert cls.model_config.get("frozen") is True, (
        f"{cls.__name__}.model_config must carry frozen=True"
    )
    assert cls.model_config.get("extra") == "forbid", (
        f"{cls.__name__}.model_config must carry extra='forbid'"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-12 — ``GitLocalOpsCapability`` has no ``push`` field.
# ───────────────────────────────────────────────────────────────────────────


def test_git_local_ops_has_no_push_field() -> None:
    """AC-12 — minting a push capability is type-impossible."""
    assert "push" not in GitLocalOpsCapability.model_fields


def test_git_local_ops_rejects_push_kwarg(tmp_path: Path) -> None:
    """AC-12 — passing ``push=True`` raises ``ValidationError`` with
    ``"push"`` in the message. **All other fields must be valid** so
    the rejection localises on ``push``, not on a missing-required
    error (otherwise a mutant that adds ``push`` but breaks ``repo``
    validation still passes)."""
    with pytest.raises(ValidationError, match="push"):
        GitLocalOpsCapability(  # type: ignore[call-arg]
            repo=_sp(tmp_path),
            branch_namespace="codegenie/",
            _minted_by=_PLUGIN,
            push=True,
        )


def test_git_local_ops_docstring_pins_no_push_invariant() -> None:
    """AC-12 — the class docstring carries the canonical no-push phrase
    AND references 03-ADR-0011 AND production ADR-0009. Three
    independent substring asserts — a mutant docstring that loses any
    one of the three fails."""
    doc = GitLocalOpsCapability.__doc__ or ""
    doc_lower = doc.lower()
    assert "no push field" in doc_lower, (
        "GitLocalOpsCapability docstring must contain literal 'no push field'"
    )
    assert "03-ADR-0011" in doc, "must reference 03-ADR-0011 (honest framing ADR)"
    assert "ADR-0009" in doc, "must reference production ADR-0009 (humans always merge)"


# ───────────────────────────────────────────────────────────────────────────
# AC-13 — :func:`mint` is the only legal constructor (AST scan).
# ───────────────────────────────────────────────────────────────────────────


_CAPABILITY_CLASS_NAMES: frozenset[str] = frozenset(
    {"NpmInstallCapability", "FsReadWriteCapability", "GitLocalOpsCapability"}
)


def test_only_mint_constructs_capabilities() -> None:
    """AC-13 — every ``*Capability(...)`` Call node in this module is
    lexically inside the body of :func:`mint`. AST-based (NOT substring
    `replace()`) so the kill is mutation-resistant: a constructor call
    inside a helper *defined outside* :func:`mint` (even if mint() calls
    the helper) fails this check."""
    src = inspect.getsource(capabilities_mod)
    tree = ast.parse(src)

    # Locate mint's lineno / end_lineno.
    mint_def: ast.FunctionDef | None = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "mint":
            mint_def = node
            break
    assert mint_def is not None, "could not locate FunctionDef('mint') in module"
    assert mint_def.end_lineno is not None
    mint_start, mint_end = mint_def.lineno, mint_def.end_lineno

    # Walk every Call node in the module; any capability-class constructor
    # must be inside [mint_start, mint_end].
    violations: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _CAPABILITY_CLASS_NAMES
        ):
            if not (mint_start <= node.lineno <= mint_end):
                violations.append((node.func.id, node.lineno))

    assert violations == [], (
        "capability constructors must be lexically inside mint(); "
        f"found constructors outside mint() at: {violations!r}"
    )


def test_no_sibling_function_constructs_capabilities() -> None:
    """AC-13 — every top-level ``FunctionDef`` other than :func:`mint`
    has zero ``*Capability(...)`` constructor Call nodes. Kills the
    escape hatch: "leak a constructor to a private helper that
    :func:`mint` calls"."""
    src = inspect.getsource(capabilities_mod)
    tree = ast.parse(src)

    siblings_with_violations: list[tuple[str, str, int]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "mint":
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id in _CAPABILITY_CLASS_NAMES
                ):
                    siblings_with_violations.append((node.name, sub.func.id, sub.lineno))

    assert siblings_with_violations == [], (
        "no helper function other than mint() may construct capabilities; "
        f"found: {siblings_with_violations!r}"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-14 — :func:`mint` emits :class:`CapabilityMinted` via the chokepoint.
# ───────────────────────────────────────────────────────────────────────────


def test_emit_capability_minted_is_module_level_chokepoint() -> None:
    """AC-14 — ``_emit_capability_minted`` exists as a module attribute
    so :func:`monkeypatch.setattr` can intercept it. A top-of-file
    ``from codegenie.plugins.events import emit_capability_minted as
    _emit_capability_minted`` would bind the function at import time
    and defeat the monkeypatch."""
    assert hasattr(capabilities_mod, "_emit_capability_minted")


def test_mint_calls_emit_via_module_attribute() -> None:
    """AC-14 — :func:`mint`'s call site uses the bare ``Name``
    ``_emit_capability_minted`` resolved against module scope (NOT a
    local-rebind via ``from ... import`` inside :func:`mint`). The
    monkeypatch needs the call to be a module-level attribute
    reference."""
    src = inspect.getsource(capabilities_mod.mint)
    tree = ast.parse(src)

    found_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found_names.add(node.func.id)

    assert "_emit_capability_minted" in found_names, (
        "mint() must call _emit_capability_minted by bare Name (module attr)"
    )


def test_mint_emits_capability_minted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC-14 — substituting the module-level chokepoint with a spy
    captures exactly one call carrying ``plugin_id`` + ``bundle_digest``.

    Direct module-object setattr (NOT the string form) so the patch is
    bound to the exact module instance ``mint`` resolves against. The
    string form walks via ``getattr`` on the parent package, which the
    fence test in ``test_no_llm_in_transforms`` can stale via its
    pop/restore dance over ``sys.modules['codegenie.plugins.*']``."""
    captured: list[CapabilityMinted] = []

    def spy(event: CapabilityMinted) -> None:
        captured.append(event)

    monkeypatch.setattr(capabilities_mod, "_emit_capability_minted", spy)

    bundle = mint(plugin=_PLUGIN, scope=NpmScope(registry=_REGISTRY))

    assert isinstance(bundle, CapabilityBundle)
    assert len(captured) == 1
    event = captured[0]
    assert event.plugin_id == _PLUGIN
    assert isinstance(event.bundle_digest, str) and len(event.bundle_digest) == 64


def test_bundle_digest_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14 — minting twice with identical inputs produces a
    byte-identical ``bundle_digest``. Closes the "random nonce in
    digest" mutation; S6-01's two-stream event log consumes the
    digest as a stable audit anchor."""
    captured: list[CapabilityMinted] = []
    monkeypatch.setattr(
        capabilities_mod,
        "_emit_capability_minted",
        lambda e: captured.append(e),
    )

    mint(plugin=_PLUGIN, scope=NpmScope(registry=_REGISTRY))
    mint(plugin=_PLUGIN, scope=NpmScope(registry=_REGISTRY))

    assert len(captured) == 2
    assert captured[0].bundle_digest == captured[1].bundle_digest


def test_default_emit_is_module_level_function(tmp_path: Path) -> None:
    """AC-14 — when no real sink is registered, ``_emit_capability_minted``
    is a function (not a try/except ImportError swallower) and ``mint()``
    succeeds without raising."""
    assert callable(capabilities_mod._emit_capability_minted)
    bundle = mint(plugin=_PLUGIN, scope=NpmScope(registry=_REGISTRY))
    assert isinstance(bundle, CapabilityBundle)


# ───────────────────────────────────────────────────────────────────────────
# AC-Sub-4 — ``CapabilityBundle`` exactly-one validator.
# ───────────────────────────────────────────────────────────────────────────


def test_bundle_accepts_exactly_one_capability(tmp_path: Path) -> None:
    """AC-Sub-4 — a single non-None capability is admitted."""
    bundle = CapabilityBundle(npm=NpmInstallCapability(registry=_REGISTRY, _minted_by=_PLUGIN))
    assert bundle.npm is not None
    assert bundle.fs is None
    assert bundle.git is None


def test_bundle_rejects_zero_capabilities() -> None:
    """AC-Sub-4 — zero non-None fields fails the validator. Kills the
    "zero is fine" mutation."""
    with pytest.raises(ValidationError, match="exactly one"):
        CapabilityBundle()


def test_bundle_rejects_two_capabilities(tmp_path: Path) -> None:
    """AC-Sub-4 — two non-None fields fail the validator. Kills the
    "any-subset" mutation."""
    with pytest.raises(ValidationError, match="exactly one"):
        CapabilityBundle(
            npm=NpmInstallCapability(registry=_REGISTRY, _minted_by=_PLUGIN),
            fs=FsReadWriteCapability(scope=_sp(tmp_path), _minted_by=_PLUGIN),
        )


def test_bundle_rejects_three_capabilities(tmp_path: Path) -> None:
    """AC-Sub-4 — all three non-None fails the validator."""
    with pytest.raises(ValidationError, match="exactly one"):
        CapabilityBundle(
            npm=NpmInstallCapability(registry=_REGISTRY, _minted_by=_PLUGIN),
            fs=FsReadWriteCapability(scope=_sp(tmp_path), _minted_by=_PLUGIN),
            git=GitLocalOpsCapability(
                repo=_sp(tmp_path),
                branch_namespace="codegenie/",
                _minted_by=_PLUGIN,
            ),
        )


# ───────────────────────────────────────────────────────────────────────────
# AC-Sub-5 — closed sum type; mint() dispatches per variant.
# ───────────────────────────────────────────────────────────────────────────


def test_capability_scope_is_closed_union() -> None:
    """AC-Sub-5 — ``CapabilityScope`` is a closed union over exactly the
    three scope types. A new variant added without updating mint() is
    caught by ``assert_never`` at mypy --strict; this test pins the
    closed-set discipline at the type-alias level too."""
    variants = set(get_args(CapabilityScope))
    assert variants == {NpmScope, FsScope, GitLocalOpsScope}


def test_mint_npm_scope_populates_npm_slot() -> None:
    """AC-Sub-5 — NpmScope ⇒ npm slot."""
    bundle = mint(plugin=_PLUGIN, scope=NpmScope(registry=_REGISTRY))
    assert bundle.npm is not None and bundle.fs is None and bundle.git is None
    assert bundle.npm.registry == _REGISTRY
    assert bundle.npm.minted_by == _PLUGIN


def test_mint_fs_scope_populates_fs_slot(tmp_path: Path) -> None:
    """AC-Sub-5 — FsScope ⇒ fs slot."""
    sp = _sp(tmp_path)
    bundle = mint(plugin=_PLUGIN, scope=FsScope(scope=sp))
    assert bundle.fs is not None and bundle.npm is None and bundle.git is None
    assert bundle.fs.scope == sp
    assert bundle.fs.minted_by == _PLUGIN


def test_mint_git_scope_populates_git_slot(tmp_path: Path) -> None:
    """AC-Sub-5 — GitLocalOpsScope ⇒ git slot."""
    sp = _sp(tmp_path)
    bundle = mint(
        plugin=_PLUGIN,
        scope=GitLocalOpsScope(repo=sp, branch_namespace="codegenie/"),
    )
    assert bundle.git is not None and bundle.npm is None and bundle.fs is None
    assert bundle.git.repo == sp
    assert bundle.git.branch_namespace == "codegenie/"
    assert bundle.git.minted_by == _PLUGIN
