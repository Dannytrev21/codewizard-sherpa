"""Red tests for S2-02a — Yarn variant detection.

Pins ACs 1-14 from
``docs/phases/01-context-gather-layer-a-node/stories/S2-02a-yarn-variant-detection.md``.

ADR-0013 (Phase 1) records the decision; this test module is the contract.

Detection priority (first hit wins):

1. ``package.json#packageManager`` matches ``^yarn@1\\.`` → ``yarn-classic``
2. ``package.json#packageManager`` matches ``^yarn@(\\d+)\\.`` with major ≥ 2 → ``yarn-berry``
3. ``.yarnrc.yml`` exists in repo root → ``yarn-berry``
4. ``.yarn/`` directory exists in repo root → ``yarn-berry``
5. ``.pnp.cjs`` or ``.pnp.loader.mjs`` exists → ``yarn-berry``
6. Default → ``yarn-classic`` + warning ``node_build_system.yarn_variant_inferred``

A malformed ``packageManager`` value (matches ``^yarn`` but not the regex above) at
priority 1/2 emits ``node_build_system.package_manager_field_unparseable`` and
falls through to priorities 3-6.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import SchemaValidationError
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


def _ctx(root: Path, parsed_manifest: Any = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )


def _run_probe(root: Path, parsed_manifest: Any = None) -> ProbeOutput:
    from codegenie.probes.node_build_system import NodeBuildSystemProbe

    return asyncio.run(NodeBuildSystemProbe().run(_snapshot(root), _ctx(root, parsed_manifest)))


@pytest.fixture(autouse=True)
def _silence_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-node-on-PATH so tests don't depend on a real `node` binary."""
    import codegenie.exec
    from codegenie.errors import ToolMissingError

    async def _raise(*a: Any, **kw: Any) -> Any:
        raise ToolMissingError("node not installed (test default)")

    monkeypatch.setattr(codegenie.exec, "run_allowlisted", _raise)


def _write_yarn_lock(root: Path) -> None:
    (root / "yarn.lock").write_text("# yarn lockfile v1\n")


# ---------- AC-1: schema enum updated ---------------------------------------


def test_schema_enum_excludes_bare_yarn_and_accepts_variants() -> None:
    """AC-1 + AC-12. Schema enum is exactly the new shape; bumped $id to v0.2.0."""
    import json as _json
    from pathlib import Path as _Path

    schema_path = (
        _Path(__file__).resolve().parents[3]
        / "src"
        / "codegenie"
        / "schema"
        / "probes"
        / "node_build_system.schema.json"
    )
    schema = _json.loads(schema_path.read_text())
    pm = schema["properties"]["build_system"]["properties"]["package_manager"]
    assert pm["enum"] == ["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", None]
    assert schema["$id"].endswith("/v0.2.0.json")


def test_envelope_rejects_legacy_yarn_value() -> None:
    """AC-12. Validation must reject ``package_manager: "yarn"`` (legacy v0.1.0 value)."""
    from codegenie.schema.validator import _validator, validate

    _validator.cache_clear()
    envelope = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {
            "node_build_system": {
                "build_system": {
                    "package_manager": "yarn",
                    "package_manager_version": None,
                    "additional_lockfiles": [],
                    "commands": {},
                    "bundler": None,
                    "typescript": None,
                    "node_version_pinned": None,
                    "node_version_constraint": None,
                    "node_version_resolved_locally": None,
                    "output_artifacts": [],
                    "warnings": [],
                }
            }
        },
    }
    with pytest.raises(SchemaValidationError):
        validate(envelope)


def test_envelope_accepts_yarn_classic_and_yarn_berry() -> None:
    """AC-1. yarn-classic + yarn-berry are accepted enum members."""
    from codegenie.schema.validator import _validator, validate

    _validator.cache_clear()
    for value in ("yarn-classic", "yarn-berry"):
        envelope: dict[str, Any] = {
            "schema_version": "0.1.0",
            "generated_at": "2026-05-14T00:00:00Z",
            "repo": {"root": "/x", "git_commit": None},
            "probes": {
                "node_build_system": {
                    "build_system": {
                        "package_manager": value,
                        "package_manager_version": None,
                        "additional_lockfiles": [],
                        "commands": {},
                        "bundler": None,
                        "typescript": None,
                        "node_version_pinned": None,
                        "node_version_constraint": None,
                        "node_version_resolved_locally": None,
                        "output_artifacts": [],
                        "warnings": [],
                    }
                }
            },
        }
        validate(envelope)


# ---------- AC-2: yarn-classic from packageManager v1 ----------------------


def test_yarn_classic_from_packagemanager_v1(tmp_path: Path) -> None:
    """AC-2 + AC-21. ``packageManager: "yarn@1.22.19"`` → ``yarn-classic``;
    neither variant-warning fires."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "yarn@1.22.19"}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]


# ---------- AC-3: yarn-berry from packageManager 2/3/4 ---------------------


@pytest.mark.parametrize(
    "pm_value",
    [
        "yarn@2.4.3",
        "yarn@3.6.4",
        "yarn@4.5.0",
        "yarn@4.0.0-rc.42",
        "yarn@5.0.0",
    ],
)
def test_yarn_berry_from_packagemanager_v2_plus(tmp_path: Path, pm_value: str) -> None:
    """AC-3 + AC-21. major ≥ 2 → ``yarn-berry``; neither variant-warning fires."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": pm_value}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]


# ---------- AC-4: yarn-berry from .yarnrc.yml marker -----------------------


def test_yarn_berry_from_yarnrc_yml(tmp_path: Path) -> None:
    """AC-4. Berry-only file ``.yarnrc.yml`` (note the extension)."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: node-modules\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


def test_yarnrc_classic_file_does_not_imply_berry(tmp_path: Path) -> None:
    """AC-4 negative — ``.yarnrc`` (no extension) is Classic's deprecated config; not Berry."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc").write_text('registry "https://registry.npmjs.org"\n')
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.yarn_variant_inferred" in s["warnings"]


# ---------- AC-5: yarn-berry from .yarn/ directory marker ------------------


def test_yarn_berry_from_yarn_dir(tmp_path: Path) -> None:
    """AC-5. ``.yarn/`` directory exists → Berry."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarn").mkdir()
    (tmp_path / ".yarn" / "releases").mkdir()
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-6: yarn-berry from PnP file marker --------------------------


@pytest.mark.parametrize("pnp_filename", [".pnp.cjs", ".pnp.loader.mjs"])
def test_yarn_berry_from_pnp_file(tmp_path: Path, pnp_filename: str) -> None:
    """AC-6. PnP marker (``.pnp.cjs`` or ``.pnp.loader.mjs``) → Berry."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    (tmp_path / pnp_filename).write_text("// pnp\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-7: yarn-classic safe-default with warning -------------------


def test_yarn_classic_safe_default_emits_inferred_warning(tmp_path: Path) -> None:
    """AC-7. Only ``yarn.lock`` (no Berry markers, no ``packageManager`` field):
    ``yarn-classic`` + warning ``node_build_system.yarn_variant_inferred``."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.yarn_variant_inferred" in s["warnings"]


# ---------- AC-8: malformed packageManager falls through -------------------


@pytest.mark.parametrize(
    "malformed_value",
    [
        "yarn",  # bare, no version
        "yarn@xyz",  # non-numeric major
        "yarn@",  # empty version
        "yarn@1",  # major-only (no minor)
    ],
)
def test_malformed_packagemanager_falls_through_to_classic(
    tmp_path: Path, malformed_value: str
) -> None:
    """AC-8. Malformed ``yarn@...`` is ignored at priorities 1-2, emits
    ``package_manager_field_unparseable``, falls through (no Berry markers →
    safe-default classic)."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": malformed_value}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.package_manager_field_unparseable" in s["warnings"]
    # And the safe-default warning surfaces because no Berry markers are present.
    assert "node_build_system.yarn_variant_inferred" in s["warnings"]


def test_malformed_packagemanager_with_berry_marker_still_berry(tmp_path: Path) -> None:
    """AC-8 fallthrough — malformed at 1-2, .yarnrc.yml at 3 → ``yarn-berry``."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "yarn@xyz"}))
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.package_manager_field_unparseable" in s["warnings"]
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


def test_non_yarn_packagemanager_does_not_emit_unparseable(tmp_path: Path) -> None:
    """AC-8 negative — ``pnpm@8.0.0`` is not yarn; no parseable warning."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "pnpm@8.6.0"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "pnpm"
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]


# ---------- AC-9: non-yarn unaffected --------------------------------------


@pytest.mark.parametrize(
    "lockfile,expected",
    [
        ("bun.lockb", "bun"),
        ("pnpm-lock.yaml", "pnpm"),
        ("package-lock.json", "npm"),
    ],
)
def test_non_yarn_unaffected_by_variant_detection(
    tmp_path: Path, lockfile: str, expected: str
) -> None:
    """AC-9. bun/pnpm/npm resolution unchanged; no yarn_variant_* warnings."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("x")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == expected
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]


def test_no_lockfile_no_yarn_variant_logic(tmp_path: Path) -> None:
    """AC-9 negative — no lockfile at all → ``package_manager`` is None; no variant logic runs."""
    (tmp_path / "package.json").write_text("{}")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] is None
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-10: existing S2-02 ACs still pass ----------------------------
# Covered by tests/unit/probes/test_node_build_system.py — running the full
# suite at Stage 3 verifies AC-10.


# ---------- AC-11: fixtures land --------------------------------------------


def test_fixture_node_yarn_legacy_resolves_to_classic() -> None:
    """AC-11 + AC-15. Fixture must be present + resolve to ``yarn-classic``."""
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "node_yarn_legacy"
    assert fixture.is_dir(), "Expected tests/fixtures/node_yarn_legacy/ to exist"
    s = _run_probe(fixture).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"


def test_fixture_node_yarn_berry_pnp_resolves_to_berry() -> None:
    """AC-11. Berry-PnP fixture: ``.yarnrc.yml`` + ``.pnp.cjs`` + ``packageManager: yarn@4.5.0``."""
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "node_yarn_berry_pnp"
    assert fixture.is_dir(), "Expected tests/fixtures/node_yarn_berry_pnp/ to exist"
    s = _run_probe(fixture).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


def test_fixture_node_yarn_berry_nonpnp_resolves_to_berry() -> None:
    """AC-11. Berry no-PnP fixture: ``.yarnrc.yml`` + ``yarn@3.6.4``, no ``.pnp.cjs``."""
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "node_yarn_berry_nonpnp"
    assert fixture.is_dir(), "Expected tests/fixtures/node_yarn_berry_nonpnp/ to exist"
    s = _run_probe(fixture).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert not (fixture / ".pnp.cjs").exists(), "Non-PnP fixture must not contain .pnp.cjs"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-13: _detect_yarn_variant() is pure ---------------------------


def test_detect_yarn_variant_is_idempotent(tmp_path: Path) -> None:
    """AC-13. Calling the function twice on the same inputs yields the same result."""
    from codegenie.probes.node_build_system import _detect_yarn_variant

    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n")
    manifest: dict[str, Any] = {"packageManager": "yarn@1.22.19"}
    # Priority 1 wins (Classic) regardless of marker presence.
    first, w1 = _detect_yarn_variant(tmp_path, manifest)
    second, w2 = _detect_yarn_variant(tmp_path, manifest)
    assert first == second == "yarn-classic"
    assert w1 == w2 == []


@pytest.mark.parametrize(
    "manifest,markers,expected,expected_warnings",
    [
        # priority 1 — Classic via packageManager v1
        ({"packageManager": "yarn@1.22.19"}, set(), "yarn-classic", []),
        # priority 2 — Berry via packageManager v2+
        ({"packageManager": "yarn@3.6.4"}, set(), "yarn-berry", []),
        # priority 3 — .yarnrc.yml
        ({}, {".yarnrc.yml"}, "yarn-berry", []),
        # priority 4 — .yarn/ directory
        ({}, {".yarn"}, "yarn-berry", []),
        # priority 5 — .pnp.cjs
        ({}, {".pnp.cjs"}, "yarn-berry", []),
        # priority 5 — .pnp.loader.mjs
        ({}, {".pnp.loader.mjs"}, "yarn-berry", []),
        # priority 6 — safe-default
        ({}, set(), "yarn-classic", ["node_build_system.yarn_variant_inferred"]),
        # malformed packageManager falls through; no Berry markers → safe-default
        (
            {"packageManager": "yarn@xyz"},
            set(),
            "yarn-classic",
            [
                "node_build_system.package_manager_field_unparseable",
                "node_build_system.yarn_variant_inferred",
            ],
        ),
    ],
)
def test_detect_yarn_variant_priority_chain(
    tmp_path: Path,
    manifest: dict[str, Any],
    markers: set[str],
    expected: str,
    expected_warnings: list[str],
) -> None:
    """AC-13 priority chain (units under test in isolation)."""
    from codegenie.probes.node_build_system import _detect_yarn_variant

    for marker in markers:
        target = tmp_path / marker
        if marker == ".yarn":
            target.mkdir()
        else:
            target.write_text("x")

    variant, warnings = _detect_yarn_variant(tmp_path, manifest or None)
    assert variant == expected
    assert warnings == expected_warnings


def test_detect_yarn_variant_handles_none_manifest(tmp_path: Path) -> None:
    """AC-13. Function accepts ``parsed_manifest=None`` (probe path when package.json is absent)."""
    from codegenie.probes.node_build_system import _detect_yarn_variant

    variant, warnings = _detect_yarn_variant(tmp_path, None)
    assert variant == "yarn-classic"
    assert warnings == ["node_build_system.yarn_variant_inferred"]


# ---------- AC-14: Open/Closed seam preserved -------------------------------


def test_lockfile_precedence_tuple_unchanged() -> None:
    """AC-14. ``_LOCKFILE_PRECEDENCE`` shape preserved — variant detection runs
    in a separate function called only when resolved manager == 'yarn'."""
    from codegenie.probes.node_build_system import _LOCKFILE_PRECEDENCE

    assert _LOCKFILE_PRECEDENCE == (
        ("bun.lockb", "bun"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    )


# ---------- Cross-cutting: declaration_lockfile_disagree must not regress --


def test_yarn_packagemanager_does_not_emit_declaration_disagree(tmp_path: Path) -> None:
    """Regression guard: ``packageManager: yarn@1.22.19`` + ``yarn.lock`` must NOT
    emit ``package_manager.declaration_lockfile_disagree`` even though the
    resolved value is now ``yarn-classic``. The disagreement check compares
    families (yarn vs pnpm), not variants."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "yarn@1.22.19"}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "package_manager.declaration_lockfile_disagree" not in s["warnings"]


def test_yarn_packagemanager_v3_on_yarn_lockfile_no_disagree(tmp_path: Path) -> None:
    """Same regression guard for Berry."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "yarn@3.6.4"}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "package_manager.declaration_lockfile_disagree" not in s["warnings"]


def test_pnpm_declared_on_yarn_lockfile_still_disagrees(tmp_path: Path) -> None:
    """Cross-family disagreement still emits the warning (AC-10 regression)."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "pnpm@8.0.0"}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] in ("yarn-classic", "yarn-berry")
    assert "package_manager.declaration_lockfile_disagree" in s["warnings"]


# ---------- AC-9b: variant detection co-exists with cross-family disagree ---


def test_pnpm_declaration_on_yarn_lockfile_runs_variant_detection_through_markers(
    tmp_path: Path,
) -> None:
    """AC-9b. ``packageManager: pnpm@8`` + ``yarn.lock`` + ``.yarnrc.yml`` →
    variant detection runs through priorities 3-6 (priority 1-2 negative
    because the field is non-yarn) and resolves to ``yarn-berry``. Both
    ``declaration_lockfile_disagree`` and the variant outcome appear.
    No ``package_manager_field_unparseable`` is emitted (the field parsed
    cleanly — it merely disagrees)."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "pnpm@8.6.0"}))
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "package_manager.declaration_lockfile_disagree" in s["warnings"]
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-16: priority-conflict — packageManager v1 beats .yarnrc.yml --


def test_priority1_classic_beats_priority3_yarnrc_yml(tmp_path: Path) -> None:
    """AC-16. ``packageManager: yarn@1.22.19`` (priority 1) wins over
    ``.yarnrc.yml`` (priority 3). A priority-order-flip mutation that
    checks `.yarnrc.yml` before `packageManager` would resolve to
    ``yarn-berry`` here — this test fails such a mutation."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": "yarn@1.22.19"}))
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-17: priority cascade among markers ---------------------------


def test_priority3_yarnrc_yml_beats_priority4_yarn_dir_and_priority5_pnp(
    tmp_path: Path,
) -> None:
    """AC-17. With all three Berry markers present and no ``packageManager``,
    ``.yarnrc.yml`` is the resolving signal (priority 3). Removing it
    cascades to ``.yarn/`` (priority 4); removing that cascades to
    ``.pnp.cjs`` (priority 5). Each step yields ``yarn-berry``."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    (tmp_path / ".yarnrc.yml").write_text("\n")
    (tmp_path / ".yarn").mkdir()
    (tmp_path / ".pnp.cjs").write_text("// pnp\n")

    # All three markers — priority 3 resolves.
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]

    # Remove .yarnrc.yml — priority 4 (.yarn/) resolves.
    (tmp_path / ".yarnrc.yml").unlink()
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]

    # Remove .yarn/ — priority 5 (.pnp.cjs) resolves.
    (tmp_path / ".yarn").rmdir()
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]


# ---------- AC-19: compile-time discipline ----------------------------------


def test_berry_markers_priority_head_pinned_at_import() -> None:
    """AC-19. ``_BERRY_MARKERS[0][0] == ".yarnrc.yml"`` is enforced by the
    module-level assertion at import. The tuple shape is locked here so a
    future refactor that flattens to an if-chain or reshuffles the head
    breaks at import time, not at runtime."""
    from codegenie.probes.node_build_system import _BERRY_MARKERS

    assert _BERRY_MARKERS[0][0] == ".yarnrc.yml"
    # And the full priority chain shape — names in order.
    names = [name for name, _ in _BERRY_MARKERS]
    assert names == [".yarnrc.yml", ".yarn", ".pnp.cjs", ".pnp.loader.mjs"]


def test_new_warning_ids_registered_in_module_set() -> None:
    """AC-19. Both new warning IDs land in ``_WARNING_IDS``; removing
    either while keeping it emitted would break the assertion below
    (and the existing import-time ADR-0007 pattern assert)."""
    from codegenie.probes.node_build_system import _WARNING_IDS

    assert "node_build_system.yarn_variant_inferred" in _WARNING_IDS
    assert "node_build_system.package_manager_field_unparseable" in _WARNING_IDS


# ---------- AC-20: warning emission location pinned -------------------------


def test_yarn_variant_warnings_land_in_slice_not_probe_output(tmp_path: Path) -> None:
    """AC-20. Variant warnings live in ``build_system.warnings``, mirroring
    ``package_manager.multi_lockfile``. ``ProbeOutput.warnings`` stays
    empty (typed-exception errors land on ``ProbeOutput.errors`` per
    ADR-0007; warnings stay slice-scoped)."""
    (tmp_path / "package.json").write_text("{}")
    _write_yarn_lock(tmp_path)
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert "node_build_system.yarn_variant_inferred" in s["warnings"]
    assert out.warnings == []


# ---------- AC-22: lockfile body is not consulted ---------------------------


def test_lockfile_body_classic_header_but_yarnrc_yml_resolves_berry(tmp_path: Path) -> None:
    """AC-22. A Classic-header ``yarn.lock`` + ``.yarnrc.yml`` resolves to
    ``yarn-berry`` via the marker — the lockfile body is NOT consulted.
    A future "improvement" that discriminated variant by reading the
    lockfile YAML signature would break this test."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "yarn.lock").write_text("# THIS IS AN AUTOGENERATED FILE.\n# yarn lockfile v1\n")
    (tmp_path / ".yarnrc.yml").write_text("nodeLinker: pnp\n")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"


# ---------- AC-8 extension: non-string packageManager is absence-equivalent -


@pytest.mark.parametrize(
    "non_string_value",
    [None, 42, ["yarn", "1"], {"name": "yarn", "version": "1"}, True],
)
def test_non_string_packagemanager_is_absent_no_unparseable_warning(
    tmp_path: Path, non_string_value: Any
) -> None:
    """AC-8 refined. Non-string ``packageManager`` (null/int/list/dict/bool)
    is absence-equivalent — falls through silently with no
    ``package_manager_field_unparseable`` warning (absence is the normal
    case). Falls to safe-default classic."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": non_string_value}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-classic"
    assert "node_build_system.package_manager_field_unparseable" not in s["warnings"]
    assert "node_build_system.yarn_variant_inferred" in s["warnings"]


# ---------- AC-3 property: random major ≥ 2 → yarn-berry --------------------


@pytest.mark.parametrize("major", [2, 5, 10, 42, 99])
def test_packagemanager_random_high_major_resolves_berry(tmp_path: Path, major: int) -> None:
    """AC-3 property — detection branches on integer major, not on a
    hardcoded ``{2, 3, 4}`` set. A mutation that hardcoded the set
    would fail for any major outside it."""
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": f"yarn@{major}.0.0"}))
    _write_yarn_lock(tmp_path)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "yarn-berry"
    assert "node_build_system.yarn_variant_inferred" not in s["warnings"]
