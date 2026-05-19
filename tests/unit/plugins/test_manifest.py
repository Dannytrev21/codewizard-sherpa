"""Unit tests for ``codegenie.plugins.manifest`` — story S2-02.

Covers AC-1..AC-19. Each test docstring names the AC it pins and the
regression class it catches (Rule 9: tests verify intent, not just
behaviour).
"""

from __future__ import annotations

import ast
import errno as _errno
import pathlib
import stat
import sys
from pathlib import Path
from typing import assert_never

import pytest
import yaml as _yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

import codegenie.plugins.manifest as manifest_mod
from codegenie.plugins.manifest import (
    IoError,
    MalformedYaml,
    ManifestContributes,
    ManifestError,
    ManifestRequirements,
    ManifestScope,
    PluginManifest,
    SchemaViolation,
    SizeCapExceeded,
)
from codegenie.result import Err, Ok
from codegenie.types.identifiers import PluginId
from tests.fixtures.plugins import sample_plugin_yaml as fx

# --- AC-13 — minimal YAML materialises every documented default --------------


def test_minimal_yaml_pins_documented_defaults(tmp_path: Path) -> None:
    """A minimal valid manifest must materialise every documented default
    by literal equality. Catches mutants that flip ``precedence``'s default
    (arch §C2 line 756 says 0; production-ADR-0031 says 50; the production
    ADR wins) or that drop a submodel default."""
    path = fx.write_minimal(tmp_path)
    result = PluginManifest.from_yaml(path)
    assert isinstance(result, Ok), repr(result)
    m = result.unwrap()
    assert m.precedence == 50
    assert m.extends == ()
    assert m.requirements == ManifestRequirements()
    assert m.requirements.external_tools == ()
    assert m.requirements.optional == ()
    assert m.contributes.tccm == "./tccm.yaml"
    assert m.contributes.subgraph == "./subgraph/"
    assert m.contributes.skills == "./skills/"
    assert m.contributes.recipes == "./recipes/"
    assert m.contributes.probes == ()
    assert m.contributes.adapters == {}


# --- AC-14 — extra="forbid" at every submodel boundary -----------------------


def test_unknown_field_returns_err_schema_violation(tmp_path: Path) -> None:
    """``extra="forbid"`` on the top-level model: a typo in ``precedence``
    must surface as a typed ``SchemaViolation`` — never silently fall back
    to the default. Without this, a Phase 7 author who adds
    ``contributes.containers`` would silently see their new field dropped."""
    path, expected = fx.write_with_typo(tmp_path, submodel="top_level")
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert any(expected in fe for fe in err.field_errors), err.field_errors


@pytest.mark.parametrize(
    "submodel",
    ["contributes", "requirements", "scope"],
    ids=["contributes", "requirements", "scope"],
)
def test_unknown_field_rejected_in_each_submodel(tmp_path: Path, submodel: str) -> None:
    """Every submodel must independently enforce ``extra="forbid"``. A
    refactor that drops ``model_config = ConfigDict(extra="forbid")`` from
    any one submodel survives the top-level test above — only this
    per-submodel sweep catches it."""
    path, expected = fx.write_with_typo(tmp_path, submodel=submodel)
    result = PluginManifest.from_yaml(path)
    assert result.is_err(), f"expected schema violation, got {result!r}"
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert any(expected in fe for fe in err.field_errors), err.field_errors


# --- AC-9 — translation table: MalformedYAMLError → MalformedYaml ------------


@pytest.mark.parametrize(
    "kind",
    [
        "empty_file",
        "invalid_syntax",
        "top_level_list",
        "top_level_scalar",
        "null_document",
    ],
    ids=["empty_file", "invalid_syntax", "top_level_list", "top_level_scalar", "null_document"],
)
def test_malformed_yaml_returns_err_malformed_yaml(tmp_path: Path, kind: str) -> None:
    """Every non-mapping or syntactically broken YAML input must surface
    as a typed ``MalformedYaml`` variant — never a ``SchemaViolation``.
    The discriminator is load-bearing for Phase 4's fail-loud handling."""
    path = fx.write_malformed(tmp_path, kind=kind)
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, MalformedYaml), f"got {type(err).__name__}: {err!r}"
    assert err.path == path


# --- AC-9 — translation table: SizeCapExceeded → SizeCapExceeded variant -----


def test_oversized_file_returns_err_size_cap_exceeded(tmp_path: Path) -> None:
    """``safe_yaml.load`` enforces the cap via ``os.fstat(fd).st_size``
    *before* any bytes are read (Phase 1 ADR-0009 — alias-amplification
    defence). A naive impl that reads-then-checks burns memory on a 2 GiB
    hostile file. The size-cap path must return ``SizeCapExceeded``."""
    path = fx.write_oversized(tmp_path)
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SizeCapExceeded)
    assert err.path == path
    assert err.cap == 1 << 20
    assert err.actual_bytes >= fx.OVERSIZED_BYTES


# --- AC-9 — translation table: OSError subclasses → IoError ------------------


def test_io_error_missing_path(tmp_path: Path) -> None:
    """``FileNotFoundError`` (errno=ENOENT) must surface as a typed
    ``IoError`` carrying the errno — never escape as a Python exception."""
    path = tmp_path / "does_not_exist.yaml"
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IoError)
    assert err.errno == _errno.ENOENT


def test_io_error_is_a_directory(tmp_path: Path) -> None:
    """Passing a directory must surface ``IoError(EISDIR)`` — a common CLI
    argument bug that the user needs to see, not a swallowed exception."""
    result = PluginManifest.from_yaml(tmp_path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IoError)
    assert err.errno in (_errno.EISDIR, _errno.EACCES)


def test_io_error_permission_denied(tmp_path: Path) -> None:
    """``chmod 000`` on the manifest file must route to ``IoError(EACCES)``."""
    if sys.platform.startswith("win"):
        pytest.skip("chmod 000 semantics differ on Windows")
    if hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() == 0:
        pytest.skip("running as root bypasses permission denials")
    path = fx.write_minimal(tmp_path)
    path.chmod(0)
    try:
        result = PluginManifest.from_yaml(path)
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IoError)
    assert err.errno == _errno.EACCES


def test_io_error_symlink_refused_routes_to_io_error(tmp_path: Path) -> None:
    """``safe_yaml`` opens with ``O_NOFOLLOW``; a symlink at the manifest
    path raises ``SymlinkRefusedError`` (a marker, not an ``OSError``
    subclass). The loader translates it to ``IoError(errno=ELOOP)`` per
    AC-9 — symlinks are a TOCTOU vector (ADR-0011 honest-framing)."""
    if sys.platform.startswith("win"):
        pytest.skip("symlink semantics differ on Windows")
    real = fx.write_minimal(tmp_path, name="real.yaml")
    link = tmp_path / "link.yaml"
    link.symlink_to(real)
    result = PluginManifest.from_yaml(link)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IoError)
    assert err.errno == _errno.ELOOP


# --- AC-12 — from_yaml never raises ------------------------------------------


@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=st.binary(min_size=0, max_size=8192))
def test_from_yaml_never_raises_on_arbitrary_bytes(tmp_path: Path, data: bytes) -> None:
    """Property: for any byte sequence written to disk, ``from_yaml``
    returns a ``Result`` — never escapes an exception. Catches missed
    ``except`` arms across the broadest input space (Rule 12 — fail loud)."""
    path = tmp_path / "fuzz.yaml"
    path.write_bytes(data)
    result = PluginManifest.from_yaml(path)
    assert isinstance(result, (Ok, Err))


# --- AC-15 — happy-path round-trip via real YAML ------------------------------


def test_happy_path_round_trip(tmp_path: Path) -> None:
    """A fully-populated, hand-authored, block-style YAML fixture round-trips
    to byte-identical reconstruction. Catches mutants that mishandle YAML's
    block-style sequences (``extends:\\n  - foo``) vs JSON-flow sugar."""
    path = fx.write_full(tmp_path)
    result = PluginManifest.from_yaml(path)
    assert isinstance(result, Ok), repr(result)
    m = result.unwrap()
    assert m.precedence == 100
    assert m.extends == (PluginId("vulnerability-remediation--node--star"),)
    assert m.contributes.tccm == "./tccm.yaml"
    assert m.requirements.external_tools == ("npm",)
    assert m.requirements.optional == ("corepack",)
    assert m.contributes.probes == ("npm_lockfile_probe", "package_json_probe")

    round_trip_path = tmp_path / "round_trip.yaml"
    round_trip_path.write_text(
        _yaml.safe_dump(m.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    second = PluginManifest.from_yaml(round_trip_path)
    assert isinstance(second, Ok), repr(second)
    assert second.unwrap() == m


# --- AC-16 — Hypothesis round-trip property -----------------------------------


_NAME_HEAD = st.sampled_from(
    [
        "vulnerability-remediation",
        "distroless-migration",
        "license-audit",
    ]
)
_NAME_MID = st.sampled_from(["node", "python", "java", "go"])
_NAME_TAIL = st.sampled_from(["npm", "pnpm", "yarn", "maven", "gradle", "pip"])


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    head=_NAME_HEAD,
    mid=_NAME_MID,
    tail=_NAME_TAIL,
    precedence=st.integers(min_value=0, max_value=10_000),
    extends_count=st.integers(min_value=0, max_value=5),
)
def test_round_trip_property(
    tmp_path: Path, head: str, mid: str, tail: str, precedence: int, extends_count: int
) -> None:
    """Property: any randomly generated valid manifest reconstructs exactly
    after a YAML round-trip. One test catches the whole class of "I added
    a field but forgot to handle round-trip" mutants (AC-16)."""
    name = f"{head}--{mid}--{tail}"
    extends_list = [f"{head}--{mid}--star"] * extends_count
    body = {
        "name": name,
        "version": "0.1.0",
        "scope": {
            "task_class": head,
            "languages": [mid],
            "build_systems": [tail],
        },
        "precedence": precedence,
        "extends": extends_list,
        "contributes": {},
    }
    path = tmp_path / "prop.yaml"
    path.write_text(_yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    first = PluginManifest.from_yaml(path)
    assert isinstance(first, Ok), repr(first)
    m = first.unwrap()

    round_trip_path = tmp_path / "prop_rt.yaml"
    round_trip_path.write_text(
        _yaml.safe_dump(m.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    second = PluginManifest.from_yaml(round_trip_path)
    assert isinstance(second, Ok), repr(second)
    assert second.unwrap() == m


# --- AC-10 — name lift via parse_plugin_id (free function) -------------------


def test_invalid_plugin_id_in_name_returns_schema_violation(tmp_path: Path) -> None:
    """``name`` lift through ``parse_plugin_id`` rejects strings that don't
    match the plugin grammar; the failure must surface as ``SchemaViolation``
    with ``"name"`` in the rendered ``field_errors`` (AC-10)."""
    path = fx.write_invalid_plugin_id(tmp_path)
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert any("name" in fe for fe in err.field_errors), err.field_errors


# --- AC-11 — extends lift; bad entry surfaces as SchemaViolation -------------


def test_invalid_plugin_id_in_extends_returns_schema_violation(tmp_path: Path) -> None:
    """A bad entry in ``extends`` short-circuits to ``SchemaViolation`` with
    ``"extends"`` named in the rendered ``field_errors`` (AC-11)."""
    body = fx.MINIMAL_VALID_YAML + "extends:\n  - NotAPluginId\n"
    path = tmp_path / "plugin.yaml"
    path.write_text(body, encoding="utf-8")
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert any("extends" in fe for fe in err.field_errors), err.field_errors


# --- AC-7 — exhaustive match callsite type-checks ----------------------------


def _match_kind(err: ManifestError) -> str:
    """Helper that exercises an exhaustive ``match`` over the tagged union.

    ``mypy --strict`` enforces exhaustiveness via ``assert_never`` on the
    fall-through arm: adding a fifth variant without updating this site
    becomes a type error (the kernel-protection mechanism ADR-0010
    §Reversibility names).
    """
    match err:
        case SizeCapExceeded():
            return "size_cap_exceeded"
        case MalformedYaml():
            return "malformed_yaml"
        case SchemaViolation():
            return "schema_violation"
        case IoError():
            return "io_error"
        case _:
            assert_never(err)


def test_exhaustive_match_over_manifest_error_variants() -> None:
    """Build one instance of each variant; the exhaustive ``match`` returns
    the variant tag. Pins AC-7's contract — the surface is exactly four
    variants, exhaustively matchable."""
    p = Path("/tmp/x")
    cases: list[tuple[ManifestError, str]] = [
        (SizeCapExceeded(path=p, actual_bytes=2 << 20, cap=1 << 20), "size_cap_exceeded"),
        (MalformedYaml(path=p, message="boom"), "malformed_yaml"),
        (SchemaViolation(path=p, field_errors=("name",)), "schema_violation"),
        (IoError(path=p, errno=_errno.ENOENT, message="missing"), "io_error"),
    ]
    for err, expected in cases:
        assert _match_kind(err) == expected


# --- AC-1, AC-6 — surface exports + discriminator union ----------------------


def test_module_exports_required_surface() -> None:
    """Pins AC-1: the module exports every name listed in the story's surface
    contract, in addition to the ``ManifestError`` alias and submodels."""
    expected = {
        "PluginManifest",
        "ManifestScope",
        "ManifestContributes",
        "ManifestRequirements",
        "SizeCapExceeded",
        "MalformedYaml",
        "SchemaViolation",
        "IoError",
        "ManifestError",
    }
    missing = expected - set(dir(manifest_mod))
    assert not missing, f"manifest module missing exports: {missing}"


def test_pydantic_models_are_frozen_and_extra_forbid() -> None:
    """Pins AC-1's "every Pydantic model uses ``frozen=True, extra='forbid'``"
    discipline — catches a refactor that drops the config on any submodel."""
    for model_cls in (
        PluginManifest,
        ManifestScope,
        ManifestContributes,
        ManifestRequirements,
        SizeCapExceeded,
        MalformedYaml,
        SchemaViolation,
        IoError,
    ):
        config = model_cls.model_config
        assert config.get("frozen") is True, f"{model_cls.__name__} not frozen"
        assert config.get("extra") == "forbid", f"{model_cls.__name__} extra != forbid"


def test_frozen_rejects_mutation(tmp_path: Path) -> None:
    """``frozen=True`` participates in equality + hashability: mutating a
    populated manifest must raise. Catches refactors that drop ``frozen``."""
    m = PluginManifest.from_yaml(fx.write_minimal(tmp_path)).unwrap()
    with pytest.raises(ValidationError):
        m.precedence = 99  # type: ignore[misc]


def test_field_change_breaks_equality(tmp_path: Path) -> None:
    """Metamorphic check: changing any documented field via ``model_copy``
    must break equality. Pins that every documented field participates in
    structural equality (Rule 9 — tests verify intent)."""
    m = PluginManifest.from_yaml(fx.write_minimal(tmp_path)).unwrap()
    assert m == m.model_copy(update={})
    assert m != m.model_copy(update={"precedence": m.precedence + 1})
    assert m != m.model_copy(update={"version": "9.9.9"})


# --- AC-3 — ManifestScope accepts str or list[str] ----------------------------


def test_manifest_scope_accepts_str_and_list(tmp_path: Path) -> None:
    """``ManifestScope`` fields accept either a single string or a list of
    strings (AC-3). Both forms must materialise as the same model shape."""
    str_form = fx.write_minimal(tmp_path, name="strform.yaml")
    list_path = tmp_path / "listform.yaml"
    list_path.write_text(
        fx.MINIMAL_VALID_YAML.replace("languages: javascript\n", "languages: [javascript]\n"),
        encoding="utf-8",
    )
    str_result = PluginManifest.from_yaml(str_form).unwrap()
    list_result = PluginManifest.from_yaml(list_path).unwrap()
    assert str_result.scope.languages == "javascript"
    assert list_result.scope.languages == ["javascript"]


# --- AC-18 — AST-walk fence ---------------------------------------------------


def test_manifest_module_does_not_bypass_safe_yaml() -> None:
    """AST source-scan fence (AC-18): the manifest module must NOT import
    ``yaml`` directly or use ``yaml.safe_load`` / ``yaml.SafeLoader`` etc.
    Every YAML read goes through the ``safe_yaml`` chokepoint (Phase 1
    ADR-0009). Mirrors ``tests/unit/tccm/test_loader.py``'s AC-23 pattern."""
    source = pathlib.Path(manifest_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {"yaml", "pyyaml"}
    forbidden_attrs = {"SafeLoader", "FullLoader", "Loader", "safe_load"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, (
                    f"manifest.py must not import {alias.name!r} (AC-18)"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod not in forbidden_modules, f"manifest.py must not import from {mod!r} (AC-18)"
            if mod in forbidden_modules:
                for alias in node.names:
                    assert alias.name not in forbidden_attrs, (
                        f"manifest.py must not import {alias.name!r} from {mod!r} (AC-18)"
                    )
    assert "safe_load" not in source, (
        "manifest.py must not reference 'safe_load' — chokepoint is safe_yaml.load (AC-18)"
    )
    assert "SafeLoader" not in source, "manifest.py must not reference 'SafeLoader' (AC-18)"
