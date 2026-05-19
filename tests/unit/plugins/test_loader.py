"""Phase 3 S2-03 — :func:`codegenie.plugins.loader.load_plugins` parametrized
per-variant rejections + import-not-fired witness + default-registry path.

The seven :data:`PluginRejected` variants are one named test each — drift
in any variant's discriminator, payload, or routing path fails its named
test loudly. The verify-all-then-import-all order invariant has two
witnesses: ``test_tampered_plugin_module_never_imported`` (sys.modules
inspection) and ``test_no_partial_registration_on_any_rejection``
(default-registry mutation-resistance).
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

import pytest

from codegenie.plugins.errors import (
    IntegrityMismatch,
    LockFileMalformed,
    MissingManifest,
    MissingPluginDirectory,
    PluginImportError,
    PluginRejected,
    SchemaViolation,
    SymlinkEscape,
    UnlockedPlugin,
    exit_code_for_rejection,
)
from codegenie.plugins.loader import (
    LoadReport,
    compute_plugin_tree_digest,
    load_plugins,
)
from codegenie.plugins.lockfile import LockFile
from codegenie.plugins.registry import PluginRegistry
from codegenie.plugins.verifiers import (
    PluginVerifier,
    Sha256TreeDigestVerifier,
    VerificationError,
)
from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import BlobDigest, PluginId
from tests.fixtures.plugins.loader_fixtures import (
    DEFAULT_SLUG,
    make_fake_plugin_dir,
    write_lockfile,
)

# ---------------------------------------------------------------------------
# Red test — the canonical failing case at story-write time.
# ---------------------------------------------------------------------------


def test_integrity_mismatch_returns_err(tmp_path: Path) -> None:
    """ADR-0011: ``PLUGINS.lock`` mismatch is a typed ``IntegrityMismatch``
    variant with exit code 4. Mutate a plugin file after locking; the
    loader must refuse AND must NOT import the tampered module."""
    plugin_root = tmp_path / "plugins"
    slug_dir = make_fake_plugin_dir(plugin_root)

    # Snapshot the digest using the loader's own helper, then mutate AFTER
    # locking. Pin the un-prefixed 64-hex format (S1-01 BlobDigest regex).
    locked = compute_plugin_tree_digest(slug_dir).unwrap()
    assert re.fullmatch(r"[0-9a-f]{64}", locked)

    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: locked})
    (slug_dir / "api.py").write_text("# tampered body\n", encoding="utf-8")

    sys.modules.pop("__PROOF_OF_IMPORT__", None)
    registry = PluginRegistry()
    result = load_plugins(plugin_root, lock_path, registry=registry)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IntegrityMismatch)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert exit_code_for_rejection(err) == 4
    assert len(registry.all()) == 0
    # The tampered module must NOT have been imported — verify-then-import.
    assert "__PROOF_OF_IMPORT__" not in sys.modules


# ---------------------------------------------------------------------------
# Per-variant green tests (one named test per ``PluginRejected`` variant).
# ---------------------------------------------------------------------------


def test_missing_manifest_returns_err(tmp_path: Path) -> None:
    """Directory exists under ``plugins/`` but no ``plugin.yaml``.

    Distinct from ``MissingPluginDirectory`` (lock entry, no directory).
    The lock entry forces the loader to look for the slug; the empty dir
    raises the "manifest missing" arm.
    """
    plugin_root = tmp_path / "plugins"
    make_fake_plugin_dir(plugin_root, include_manifest=False, api_body=None)
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, MissingManifest)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert exit_code_for_rejection(err) == 4


def test_schema_violation_returns_err(tmp_path: Path) -> None:
    """Malformed ``plugin.yaml`` → ``SchemaViolation`` (carries detail)."""
    plugin_root = tmp_path / "plugins"
    # Unknown top-level field — Pydantic's ``extra="forbid"`` raises.
    bad_manifest = textwrap.dedent(
        f"""\
        name: {DEFAULT_SLUG}
        version: 0.1.0
        scope:
          task_class: vulnerability-remediation
          languages: javascript
          build_systems: npm
        contributes: {{}}
        bogus_unknown_field: true
        """
    )
    slug_dir = make_fake_plugin_dir(plugin_root, manifest_body=bad_manifest)
    # Lock something — loader needs to get past Discover to hit the manifest.
    digest = compute_plugin_tree_digest(slug_dir).unwrap()
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: digest})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert err.detail
    assert exit_code_for_rejection(err) == 4


def test_unlocked_plugin_returns_err(tmp_path: Path) -> None:
    """Plugin manifest names a slug not present in ``PLUGINS.lock``."""
    plugin_root = tmp_path / "plugins"
    make_fake_plugin_dir(plugin_root)
    # Lock file is empty — every manifest is unlocked.
    lock_path = write_lockfile(plugin_root, {})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, UnlockedPlugin)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert exit_code_for_rejection(err) == 4


def test_missing_plugin_directory_returns_err(tmp_path: Path) -> None:
    """``PLUGINS.lock`` names a plugin whose directory is absent."""
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, MissingPluginDirectory)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert exit_code_for_rejection(err) == 4


def test_import_error_returns_err(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugin's ``api.py`` raises at import time → ``PluginImportError``.

    The plugin tree (manifest + ``api.py``) is at ``tmp_path/plugins/{slug}/``.
    To exercise ``importlib.import_module("plugins.{slug}.api")`` we add
    ``tmp_path`` to ``sys.path`` so the synthetic package is reachable.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "plugins", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}.api", raising=False)

    plugin_root = tmp_path / "plugins"
    (plugin_root / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / "__init__.py").write_text("", encoding="utf-8")
    bad_api = "raise RuntimeError('plugin boom at import time')\n"
    slug_dir = make_fake_plugin_dir(plugin_root, api_body=bad_api)
    # The slug directory needs its own __init__.py too because the slug
    # contains hyphens; create one anyway for explicitness.
    (slug_dir / "__init__.py").write_text("", encoding="utf-8")

    digest = compute_plugin_tree_digest(slug_dir).unwrap()
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: digest})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, PluginImportError)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert "boom" in err.detail.lower() or "runtime" in err.detail.lower()
    assert exit_code_for_rejection(err) == 4


def test_symlink_escape_returns_err(tmp_path: Path) -> None:
    """A symlink inside ``plugins/{slug}/`` that resolves outside the slug
    directory raises ``SymlinkEscape``."""
    plugin_root = tmp_path / "plugins"
    slug_dir = make_fake_plugin_dir(plugin_root)
    outsider = tmp_path / "outsider.txt"
    outsider.write_text("not in the plugin tree", encoding="utf-8")
    escape_link = slug_dir / "escape.txt"
    escape_link.symlink_to(outsider)

    # Pre-stage a lock entry so the loader reaches the verifier; the digest
    # value doesn't matter because the symlink-escape short-circuits.
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SymlinkEscape)
    assert err.plugin == PluginId(DEFAULT_SLUG)
    assert exit_code_for_rejection(err) == 4


def test_malformed_lock_returns_err(tmp_path: Path) -> None:
    """``PLUGINS.lock`` is a list at top level — ``LockFileMalformed``."""
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    lock_path = plugin_root / "PLUGINS.lock"
    lock_path.write_text("[]", encoding="utf-8")

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, LockFileMalformed)
    assert exit_code_for_rejection(err) == 4


# ---------------------------------------------------------------------------
# Mutation-resistance: no partial registration on any rejection.
# ---------------------------------------------------------------------------


def _build_rejection_case(variant_name: str, tmp_path: Path) -> tuple[Path, Path]:
    """Return ``(plugin_root, lock_path)`` rigged to produce ``variant_name``.

    One builder per :data:`PluginRejected` variant — ``test_no_partial_registration``
    parametrizes over these and asserts the registry stays empty.
    """
    plugin_root = tmp_path / "plugins"
    if variant_name == "integrity_mismatch":
        slug_dir = make_fake_plugin_dir(plugin_root)
        digest = compute_plugin_tree_digest(slug_dir).unwrap()
        lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: digest})
        (slug_dir / "api.py").write_text("# tampered\n", encoding="utf-8")
        return plugin_root, lock_path
    if variant_name == "missing_manifest":
        make_fake_plugin_dir(plugin_root, include_manifest=False, api_body=None)
        return plugin_root, write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})
    if variant_name == "schema_violation":
        bad = "this is not yaml: : :\n"
        slug_dir = make_fake_plugin_dir(plugin_root, manifest_body=bad)
        digest = compute_plugin_tree_digest(slug_dir).unwrap()
        return plugin_root, write_lockfile(plugin_root, {DEFAULT_SLUG: digest})
    if variant_name == "unlocked_plugin":
        make_fake_plugin_dir(plugin_root)
        return plugin_root, write_lockfile(plugin_root, {})
    if variant_name == "missing_plugin_directory":
        plugin_root.mkdir()
        return plugin_root, write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})
    if variant_name == "symlink_escape":
        slug_dir = make_fake_plugin_dir(plugin_root)
        outsider = tmp_path / "_outsider.txt"
        outsider.write_text("not in the plugin tree", encoding="utf-8")
        (slug_dir / "escape.txt").symlink_to(outsider)
        return plugin_root, write_lockfile(plugin_root, {DEFAULT_SLUG: "0" * 64})
    if variant_name == "lockfile_malformed":
        plugin_root.mkdir()
        lock_path = plugin_root / "PLUGINS.lock"
        lock_path.write_text("[]", encoding="utf-8")
        return plugin_root, lock_path
    raise AssertionError(f"unknown variant {variant_name!r}")


_ALL_REJECTION_VARIANTS = (
    "integrity_mismatch",
    "missing_manifest",
    "schema_violation",
    "unlocked_plugin",
    "missing_plugin_directory",
    "symlink_escape",
    "lockfile_malformed",
)


@pytest.mark.parametrize("variant_name", _ALL_REJECTION_VARIANTS)
def test_no_partial_registration_on_any_rejection(variant_name: str, tmp_path: Path) -> None:
    """Across every ``PluginRejected`` variant the target registry stays
    empty when the loader returns ``Err(...)``."""
    plugin_root, lock_path = _build_rejection_case(variant_name, tmp_path)
    registry = PluginRegistry()
    result = load_plugins(plugin_root, lock_path, registry=registry)
    assert result.is_err()
    assert registry.all() == ()


def test_tampered_plugin_module_never_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Witness for the verify-all-then-import-all invariant.

    Build a plugin whose ``api.py`` would set
    ``sys.modules["__PROOF_OF_IMPORT__"] = object()`` at import time.
    Tamper a sibling file after locking; the loader must refuse with
    ``IntegrityMismatch`` AND the proof sentinel must NOT appear in
    ``sys.modules`` — the import gate never fires.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "__PROOF_OF_IMPORT__", raising=False)

    plugin_root = tmp_path / "plugins"
    slug_dir = make_fake_plugin_dir(
        plugin_root,
        api_body='import sys\nsys.modules["__PROOF_OF_IMPORT__"] = object()\n',
    )
    locked = compute_plugin_tree_digest(slug_dir).unwrap()
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: locked})
    # Tamper a non-api file so the integrity check fails BEFORE the import.
    (slug_dir / "plugin.yaml").write_text(
        slug_dir.joinpath("plugin.yaml").read_text(encoding="utf-8") + "# tampered\n",
        encoding="utf-8",
    )

    result = load_plugins(plugin_root, lock_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IntegrityMismatch)
    assert "__PROOF_OF_IMPORT__" not in sys.modules


# ---------------------------------------------------------------------------
# Default-registry path + LoadReport shape.
# ---------------------------------------------------------------------------


def test_load_plugins_default_singleton_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``load_plugins(plugin_root, lock_path)`` with no ``registry=`` kwarg
    routes registrations into :data:`default_registry`.

    The autouse ``restore_default_registry`` fixture from
    ``tests/unit/plugins/conftest.py`` snapshots + restores around this test.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "plugins", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}.api", raising=False)

    plugin_root = tmp_path / "plugins"
    api_body = "import sys\nsys.modules.setdefault('__DEFAULT_SINGLETON_PROOF__', True)\n"
    slug_dir = make_fake_plugin_dir(plugin_root, api_body=api_body)
    (plugin_root / "__init__.py").write_text("", encoding="utf-8")
    (slug_dir / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.delitem(sys.modules, "__DEFAULT_SINGLETON_PROOF__", raising=False)

    digest = compute_plugin_tree_digest(slug_dir).unwrap()
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: digest})

    result = load_plugins(plugin_root, lock_path)
    assert result.is_ok()
    report = result.unwrap()
    assert isinstance(report, LoadReport)
    assert report.loaded == (PluginId(DEFAULT_SLUG),)
    assert report.total_walked == 1
    # The import side-effect fired — proof sentinel is now in sys.modules.
    assert "__DEFAULT_SINGLETON_PROOF__" in sys.modules

    # ``default_registry`` may or may not contain a plugin depending on
    # whether the api.py called ``register_plugin``. The autouse fixture
    # snapshot-restores either way; what matters is the import side-effect
    # ran exactly once.

    # Cleanup the test-only sys.modules sentinel so subsequent tests start
    # clean (monkeypatch.delitem above only guards entry).
    sys.modules.pop("__DEFAULT_SINGLETON_PROOF__", None)


# ---------------------------------------------------------------------------
# Verifier-substitution seam (ADR-0011 §Consequences line 78).
# ---------------------------------------------------------------------------


class _AlwaysAcceptVerifier:
    """Fake :class:`PluginVerifier` that returns ``Ok(None)`` regardless.

    Demonstrates the Phase-11 substitution path. The Phase-3 default is
    :class:`Sha256TreeDigestVerifier`; Phase 11 will land
    ``SigstoreVerifier`` with zero edits to the loader.
    """

    def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]:
        del plugin_dir, expected
        return Ok(value=None)


def test_load_plugins_accepts_alternate_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An alternate :class:`PluginVerifier` short-circuits the SHA-256
    tree-digest check — Phase 11 Sigstore lands here with zero edits to
    :func:`load_plugins`."""
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "plugins", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}", raising=False)
    monkeypatch.delitem(sys.modules, f"plugins.{DEFAULT_SLUG}.api", raising=False)

    plugin_root = tmp_path / "plugins"
    slug_dir = make_fake_plugin_dir(plugin_root)
    (plugin_root / "__init__.py").write_text("", encoding="utf-8")
    (slug_dir / "__init__.py").write_text("", encoding="utf-8")
    # Lock the slug with a digest that would mismatch the default verifier.
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: "a" * 64})

    verifier: PluginVerifier = _AlwaysAcceptVerifier()
    result = load_plugins(plugin_root, lock_path, verifier=verifier)
    assert result.is_ok(), f"expected Ok, got {result!r}"
    assert result.unwrap().loaded == (PluginId(DEFAULT_SLUG),)


# ---------------------------------------------------------------------------
# Lockfile round-trip + LoadReport shape.
# ---------------------------------------------------------------------------


def test_lockfile_roundtrip(tmp_path: Path) -> None:
    """Write a lockfile, load it through :meth:`LockFile.from_path`, assert
    the typed payload matches what we wrote."""
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    digest_str = "0" * 64
    lock_path = write_lockfile(plugin_root, {DEFAULT_SLUG: digest_str})

    loaded = LockFile.from_path(lock_path)
    assert loaded.is_ok()
    lockfile = loaded.unwrap()
    assert lockfile.root[PluginId(DEFAULT_SLUG)] == BlobDigest(digest_str)


def test_exit_code_for_rejection_is_4_for_every_variant() -> None:
    """AC-16 smoke — every :data:`PluginRejected` variant maps to 4."""
    every_variant: tuple[PluginRejected, ...] = (
        IntegrityMismatch(
            plugin=PluginId("a--b--c"),
            expected=BlobDigest("0" * 64),
            actual=BlobDigest("1" * 64),
        ),
        MissingManifest(plugin=PluginId("a--b--c")),
        SchemaViolation(plugin=PluginId("a--b--c"), detail="x"),
        UnlockedPlugin(plugin=PluginId("a--b--c")),
        MissingPluginDirectory(plugin=PluginId("a--b--c")),
        PluginImportError(plugin=PluginId("a--b--c"), detail="x"),
        SymlinkEscape(plugin=PluginId("a--b--c"), offending_path=Path("/x")),
        LockFileMalformed(plugin=PluginId("<lockfile>"), detail="x"),
    )
    for variant in every_variant:
        assert exit_code_for_rejection(variant) == 4


# ---------------------------------------------------------------------------
# Verifier protocol shape.
# ---------------------------------------------------------------------------


def test_sha256_tree_digest_verifier_is_a_plugin_verifier() -> None:
    """The Phase-3 default conforms to the :class:`PluginVerifier` Protocol.

    A future maintainer who changes :class:`Sha256TreeDigestVerifier`'s
    method signature breaks this assertion — and the loader's ``verifier=``
    contract simultaneously."""
    verifier: PluginVerifier = Sha256TreeDigestVerifier()
    assert isinstance(verifier, PluginVerifier)


# ---------------------------------------------------------------------------
# Consumer-site exhaustiveness gate (mypy --strict will catch new variants).
# ---------------------------------------------------------------------------


def test_pluginrejected_exhaustiveness_gate() -> None:
    """A consumer-site ``match`` block over every variant; if a new variant
    lands without updating consumers, ``assert_never`` (and mypy --strict)
    fails before this test fires."""
    from typing import assert_never

    def _render(rejection: PluginRejected) -> str:
        match rejection:
            case IntegrityMismatch():
                return "integrity_mismatch"
            case MissingManifest():
                return "missing_manifest"
            case SchemaViolation():
                return "schema_violation"
            case UnlockedPlugin():
                return "unlocked_plugin"
            case MissingPluginDirectory():
                return "missing_plugin_directory"
            case PluginImportError():
                return "plugin_import_error"
            case SymlinkEscape():
                return "symlink_escape"
            case LockFileMalformed():
                return "lockfile_malformed"
            case _:
                assert_never(rejection)

    sample: PluginRejected = MissingManifest(plugin=PluginId("a--b--c"))
    assert _render(sample) == "missing_manifest"


# Quiet "unused import" for the ``Err`` / ``Ok`` symbols used in helpers.
_ = (Err, Ok)
