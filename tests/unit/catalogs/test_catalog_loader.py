"""Unit tests for ``codegenie.catalogs`` (S1-05).

Pins the contract from
``docs/phases/01-context-gather-layer-a-node/stories/S1-05-catalogs.md``
and arch §"Component design" #10 + ADR-0006 / ADR-0008 / ADR-0004.

The Phase-0 markers-only invariant
(``tests/unit/test_errors.py::test_subclasses_are_markers_only``) means
every raised typed exception is constructed with **exactly one positional
formatted message string** and carries no instance state — recoverable
detail lives in ``args[0]``.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, get_args, get_type_hints

import pytest
import structlog.testing

import codegenie.errors as e

# --- AC-1: Module surface --------------------------------------------------


def test_module_exports_documented_names() -> None:
    """AC-1 — ``__all__`` enumerates exactly the six documented names."""
    import codegenie.catalogs as cat

    assert set(cat.__all__) == {
        "NATIVE_MODULES",
        "CI_PROVIDERS",
        "NATIVE_MODULES_CATALOG_VERSION",
        "CI_PROVIDERS_CATALOG_VERSION",
        "NativeModuleEntry",
        "CIProviderEntry",
    }


# --- AC-2 / AC-3: NamedTuple shapes ----------------------------------------


def test_native_module_entry_shape() -> None:
    """AC-2 — six fields in declared order; sequence fields ``tuple[str, ...]``."""
    from codegenie.catalogs import NativeModuleEntry

    hints = get_type_hints(NativeModuleEntry)
    assert list(NativeModuleEntry._fields) == [
        "name",
        "requires_node_gyp",
        "system_deps_required",
        "binary_artifacts_glob",
        "notes",
        "catalog_entry_version",
    ]
    assert hints["name"] is str
    assert hints["requires_node_gyp"] is bool
    assert hints["system_deps_required"] == tuple[str, ...]
    assert hints["binary_artifacts_glob"] == tuple[str, ...]
    assert hints["notes"] is str
    assert hints["catalog_entry_version"] is int


def test_ci_provider_entry_shape() -> None:
    """AC-3 + AC-8 — three fields; ``parser`` is the five-arm ``Literal``."""
    from codegenie.catalogs import CIProviderEntry

    hints = get_type_hints(CIProviderEntry)
    assert list(CIProviderEntry._fields) == ["name", "marker_paths", "parser"]
    assert hints["name"] is str
    assert hints["marker_paths"] == tuple[str, ...]
    assert get_args(hints["parser"]) == (
        "github_actions",
        "gitlab_ci",
        "jenkins",
        "circleci",
        "azure_pipelines",
    )


# --- AC-4 / AC-5: Catalog content ------------------------------------------


def test_native_modules_seed_complete() -> None:
    """AC-4 — exactly the 10 seed entries."""
    import codegenie.catalogs as cat

    expected = {
        "bcrypt",
        "sharp",
        "better-sqlite3",
        "node-canvas",
        "node-rdkafka",
        "node-pty",
        "bufferutil",
        "utf-8-validate",
        "argon2",
        "keytar",
    }
    assert set(cat.NATIVE_MODULES) == expected
    bcrypt = cat.NATIVE_MODULES["bcrypt"]
    assert bcrypt.requires_node_gyp is True
    assert isinstance(bcrypt.catalog_entry_version, int)


def test_ci_providers_seed_complete() -> None:
    """AC-5 — exactly the 5 providers; GHA marker_paths includes both extensions."""
    import codegenie.catalogs as cat

    expected = {"github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"}
    assert set(cat.CI_PROVIDERS) == expected
    gha = cat.CI_PROVIDERS["github_actions"]
    assert ".github/workflows/*.yml" in gha.marker_paths
    assert ".github/workflows/*.yaml" in gha.marker_paths
    assert gha.parser == "github_actions"


# --- AC-6: MappingProxyType + Mapping --------------------------------------


def test_mappings_are_mappingproxy_and_mapping() -> None:
    """AC-6 — exposed as ``MappingProxyType`` and ``collections.abc.Mapping``."""
    import codegenie.catalogs as cat

    assert isinstance(cat.NATIVE_MODULES, MappingProxyType)
    assert isinstance(cat.NATIVE_MODULES, Mapping)
    assert isinstance(cat.CI_PROVIDERS, MappingProxyType)
    assert isinstance(cat.CI_PROVIDERS, Mapping)


# --- AC-7: Sequence fields are tuples at runtime ---------------------------


@pytest.mark.parametrize(
    ("catalog_attr", "sequence_attr"),
    [
        ("NATIVE_MODULES", "system_deps_required"),
        ("NATIVE_MODULES", "binary_artifacts_glob"),
        ("CI_PROVIDERS", "marker_paths"),
    ],
)
def test_named_tuple_sequence_fields_are_tuples(catalog_attr: str, sequence_attr: str) -> None:
    """AC-7 — catches the mutation that forgets the ``list -> tuple`` coercion."""
    import codegenie.catalogs as cat

    catalog = getattr(cat, catalog_attr)
    for entry in catalog.values():
        value = getattr(entry, sequence_attr)
        assert isinstance(value, tuple), f"{sequence_attr} is {type(value).__name__}, not tuple"
        assert not isinstance(value, list)


# --- AC-9: Catalog-version constants are positive ints ---------------------


def test_catalog_version_constants_are_positive_ints() -> None:
    """AC-9 — version constants are positive ``int``."""
    import codegenie.catalogs as cat

    assert isinstance(cat.NATIVE_MODULES_CATALOG_VERSION, int)
    assert cat.NATIVE_MODULES_CATALOG_VERSION >= 1
    assert isinstance(cat.CI_PROVIDERS_CATALOG_VERSION, int)
    assert cat.CI_PROVIDERS_CATALOG_VERSION >= 1


# --- AC-10: Routes through ``safe_yaml.load`` chokepoint ------------------


def test_catalog_routes_through_safe_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-10 — catches the mutation that bypasses the chokepoint."""
    import codegenie.parsers.safe_yaml as syaml

    calls: list[tuple[Path, int]] = []
    real = syaml.load

    def spy(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, object]:
        calls.append((path, max_bytes))
        return real(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(syaml, "load", spy)
    sys.modules.pop("codegenie.catalogs", None)
    importlib.import_module("codegenie.catalogs")
    assert len(calls) == 2
    names = {p.name for p, _ in calls}
    assert names == {"native_modules.yaml", "ci_providers.yaml"}
    assert all(mb <= 1_000_000 for _, mb in calls)


# --- AC-11: Module-level constants populated on import --------------------


def test_module_level_constants_populated_on_first_import() -> None:
    """AC-11 — constants exist after a clean import."""
    sys.modules.pop("codegenie.catalogs", None)
    cat = importlib.import_module("codegenie.catalogs")
    assert cat.NATIVE_MODULES, "NATIVE_MODULES empty after import"
    assert cat.CI_PROVIDERS, "CI_PROVIDERS empty after import"
    assert cat.NATIVE_MODULES_CATALOG_VERSION
    assert cat.CI_PROVIDERS_CATALOG_VERSION


# --- AC-12: MappingProxyType blocks every mutation ------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        lambda m: m.__setitem__("x", None),
        lambda m: m.__delitem__("bcrypt"),
        lambda m: m.update({"x": None}),
        lambda m: m.pop("bcrypt"),
        lambda m: m.clear(),
        lambda m: m.setdefault("x", None),
    ],
)
def test_mappingproxy_blocks_all_mutation(
    mutation: Callable[[Mapping[str, object]], object],
) -> None:
    """AC-12 — every mutation API is blocked.

    ``MappingProxyType`` raises ``TypeError`` for ``__setitem__`` /
    ``__delitem__`` and ``AttributeError`` for the dict-only mutators
    (``update`` / ``pop`` / ``clear`` / ``setdefault``) — both shapes
    satisfy the AC intent "mutation API rejected" (story prescribed
    ``TypeError`` uniformly; reality is mixed; lesson L-7).
    """
    import codegenie.catalogs as cat

    with pytest.raises((TypeError, AttributeError)):
        mutation(cat.NATIVE_MODULES)


# --- AC-13: Marker-only failure shape -------------------------------------


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_malformed_yaml_translates_to_catalog_load_error(tmp_path: Path) -> None:
    """AC-13 — malformed YAML raises ``CatalogLoadError`` as a marker."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    bad = _write(tmp_path, "native_modules.yaml", ":\n:\n:invalid")
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    assert len(ei.value.args) == 1
    assert isinstance(ei.value.args[0], str)
    assert str(bad) in ei.value.args[0]
    assert not hasattr(ei.value, "path")
    assert not hasattr(ei.value, "detail")


def test_catalog_load_error_is_marker() -> None:
    """AC-13 — class-shape invariant (re-asserts S1-01 contract locally)."""
    assert e.CatalogLoadError.__init__ is e.CodegenieError.__init__
    exc = e.CatalogLoadError("some message")
    assert exc.args == ("some message",)


# --- AC-14: Hard fail at import time --------------------------------------


def test_loader_does_not_catch_its_own_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-14 — ``CatalogLoadError`` propagates out of the import statement."""
    sys.modules.pop("codegenie.catalogs", None)

    import codegenie.parsers.safe_yaml as syaml

    def boom(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, object]:
        raise e.MalformedYAMLError(f"{path}: forced failure")

    monkeypatch.setattr(syaml, "load", boom)
    with pytest.raises(e.CatalogLoadError):
        importlib.import_module("codegenie.catalogs")


# --- AC-15: Schema rejects unknown fields ---------------------------------


@pytest.mark.parametrize(
    ("extra_top_field", "expected_path_fragment"),
    [
        ("cataolg_version: 1", "cataolg_version"),
        ("rogue: yes", "rogue"),
    ],
)
def test_schema_rejects_unknown_top_level_field(
    tmp_path: Path, extra_top_field: str, expected_path_fragment: str
) -> None:
    """AC-15 — unknown top-level field is rejected (``additionalProperties: false``)."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    body = (
        "catalog_version: 1\n"
        f"{extra_top_field}\n"
        "entries:\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: true\n"
        "    system_deps_required: []\n"
        "    binary_artifacts_glob: []\n"
        "    notes: ''\n"
        "    catalog_entry_version: 1\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    msg = ei.value.args[0]
    assert expected_path_fragment in msg or "additional properties" in msg.lower()


def test_schema_rejects_unknown_entry_field(tmp_path: Path) -> None:
    """AC-15 — unknown entry field is rejected."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    body = (
        "catalog_version: 1\n"
        "entries:\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: true\n"
        "    system_deps_required: []\n"
        "    binary_artifacts_glob: []\n"
        "    notes: ''\n"
        "    catalog_entry_version: 1\n"
        "    nots: bogus\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


# --- AC-16: Empty entries list rejected -----------------------------------


def test_empty_entries_rejected(tmp_path: Path) -> None:
    """AC-16 — ``entries: []`` is a schema violation (``minItems: 1``)."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    bad = _write(tmp_path, "native_modules.yaml", "catalog_version: 1\nentries: []\n")
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


# --- AC-17: Non-positive catalog_version rejected -------------------------


@pytest.mark.parametrize("bad_version", [0, -1])
def test_non_positive_catalog_version_rejected(tmp_path: Path, bad_version: int) -> None:
    """AC-17 — ``catalog_version`` must be ``minimum: 1``."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    body = (
        f"catalog_version: {bad_version}\n"
        "entries:\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: true\n"
        "    system_deps_required: []\n"
        "    binary_artifacts_glob: []\n"
        "    notes: ''\n"
        "    catalog_entry_version: 1\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


@pytest.mark.parametrize("bad_version", [0, -1])
def test_non_positive_catalog_entry_version_rejected(tmp_path: Path, bad_version: int) -> None:
    """AC-17 — ``catalog_entry_version`` must be ``minimum: 1``."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    body = (
        "catalog_version: 1\n"
        "entries:\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: true\n"
        "    system_deps_required: []\n"
        "    binary_artifacts_glob: []\n"
        "    notes: ''\n"
        f"    catalog_entry_version: {bad_version}\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError):
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")


# --- AC-18: Duplicate names detected post-load ----------------------------


def test_duplicate_name_detected_when_entries_differ_in_other_fields(
    tmp_path: Path,
) -> None:
    """AC-18 — duplicate ``name`` rejected even when other fields differ."""
    from codegenie.catalogs import NativeModuleEntry, _load_catalog

    body = (
        "catalog_version: 1\n"
        "entries:\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: true\n"
        "    system_deps_required: []\n"
        "    binary_artifacts_glob: []\n"
        "    notes: 'first'\n"
        "    catalog_entry_version: 1\n"
        "  - name: bcrypt\n"
        "    requires_node_gyp: false\n"
        "    system_deps_required: [foo]\n"
        "    binary_artifacts_glob: [bar]\n"
        "    notes: 'second'\n"
        "    catalog_entry_version: 2\n"
    )
    bad = _write(tmp_path, "native_modules.yaml", body)
    with pytest.raises(e.CatalogLoadError) as ei:
        _load_catalog(bad, NativeModuleEntry, schema_subkey="native_modules")
    assert "bcrypt" in ei.value.args[0]


# --- AC-19: structlog event with structured fields ------------------------


def test_catalog_load_event_emitted_with_structured_fields() -> None:
    """AC-19 — exactly two ``probe.catalog.load`` events with structured fields."""
    sys.modules.pop("codegenie.catalogs", None)
    with structlog.testing.capture_logs() as logs:
        importlib.import_module("codegenie.catalogs")
    events = [ev for ev in logs if ev.get("event") == "probe.catalog.load"]
    assert len(events) == 2
    by_name = {ev["catalog_name"]: ev for ev in events}
    assert set(by_name) == {"native_modules", "ci_providers"}
    for _, ev in by_name.items():
        assert isinstance(ev["entries"], int) and ev["entries"] >= 1
        assert isinstance(ev["catalog_version"], int) and ev["catalog_version"] >= 1


# --- AC-20: Kernel is closed for modification -----------------------------


def test_kernel_is_closed_for_modification(tmp_path: Path) -> None:
    """AC-20 — a 3rd-style catalog loads through the kernel without editing it."""
    from codegenie.catalogs import _LOAD_SCHEMA, _load_catalog

    class FixtureEntry(NamedTuple):
        name: str
        tag: str

    fixture_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["catalog_version", "entries"],
        "properties": {
            "catalog_version": {"type": "integer", "minimum": 1},
            "entries": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "tag"],
                    "properties": {
                        "name": {"type": "string"},
                        "tag": {"type": "string"},
                    },
                },
            },
        },
    }
    _LOAD_SCHEMA["$defs"]["fixture"] = fixture_schema
    try:
        good = _write(
            tmp_path,
            "fixture.yaml",
            "catalog_version: 1\nentries:\n  - {name: a, tag: x}\n  - {name: b, tag: y}\n",
        )
        mapping, version = _load_catalog(
            good,
            FixtureEntry,
            schema_subkey="fixture",  # type: ignore[arg-type]
        )
        assert version == 1
        assert set(mapping) == {"a", "b"}
        assert mapping["a"].tag == "x"
    finally:
        del _LOAD_SCHEMA["$defs"]["fixture"]


# --- AC-21: schema_subkey is Literal-typed --------------------------------


def test_schema_subkey_is_literal_typed() -> None:
    """AC-21 — ``schema_subkey`` annotated as the two-arm ``Literal``."""
    from codegenie.catalogs import _load_catalog

    hints = get_type_hints(_load_catalog)
    assert set(get_args(hints["schema_subkey"])) == {"native_modules", "ci_providers"}


# --- AC-22: Module docstring references arch + ADRs -----------------------


def test_module_docstring_references_arch_and_adrs() -> None:
    """AC-22 — module docstring cites arch §10 + ADR-0006 + ADR-0008."""
    import codegenie.catalogs as cat

    doc = cat.__doc__ or ""
    assert "Component design" in doc
    assert "ADR-0006" in doc
    assert "ADR-0008" in doc


# --- AC-23: Shipped catalogs validate against the self-schema -------------


def test_shipped_catalogs_validate_against_self_schema() -> None:
    """AC-23 — land-time gate: hand-edited shipped YAML cannot regress."""
    from codegenie.catalogs import (
        CIProviderEntry,
        NativeModuleEntry,
        _load_catalog,
    )

    pkg = importlib.import_module("codegenie.catalogs")
    pkg_file = pkg.__file__
    assert pkg_file is not None
    pkg_dir = Path(pkg_file).parent
    nm, nm_v = _load_catalog(
        pkg_dir / "native_modules.yaml",
        NativeModuleEntry,
        schema_subkey="native_modules",
    )
    ci, ci_v = _load_catalog(
        pkg_dir / "ci_providers.yaml",
        CIProviderEntry,
        schema_subkey="ci_providers",
    )
    assert len(nm) == 10 and nm_v >= 1
    assert len(ci) == 5 and ci_v >= 1
