"""Tests for ``TestInventoryProbe`` (S4-03).

Pins AC-1..AC-57 from
``docs/phases/01-context-gather-layer-a-node/stories/S4-03-test-inventory-probe.md``.

Helpers are inlined here (matches the S2-02 / S4-01 / S4-02 sibling idiom).
The probe's ``run()`` is async; tests use ``asyncio.run`` directly to keep
``pytest-asyncio`` out of the dependency surface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------- helpers ----------------------------------------------------------


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


def _ctx(root: Path, *, parsed_manifest: Any = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )


def _run(root: Path, *, parsed_manifest: Any = None) -> ProbeOutput:
    from codegenie.probes.test_inventory import TestInventoryProbe

    return asyncio.run(
        TestInventoryProbe().run(_snapshot(root), _ctx(root, parsed_manifest=parsed_manifest))
    )


def _minimal_envelope_with_test_inventory() -> dict[str, Any]:
    slice_payload: dict[str, Any] = {
        "framework": None,
        "e2e_framework": None,
        "unit_test_file_count": 0,
        "unit_test_count_is_file_count": True,
        "commands": {},
        "smoke_test_path": None,
        "coverage_data": {"present": False, "parse_error": False, "totals": None},
        "warnings": [],
    }
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-15T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {"test_inventory": {"test_inventory": slice_payload}},
    }


# ---------- AC-1 / AC-2 / AC-3: contract -----------------------------------


def test_module_exists_and_exports_probe() -> None:
    """AC-1."""
    from codegenie.probes import test_inventory as mod

    assert hasattr(mod, "TestInventoryProbe")


def test_contract_attributes_pinned() -> None:
    """AC-2."""
    from codegenie.probes.test_inventory import TestInventoryProbe

    assert TestInventoryProbe.name == "test_inventory"
    assert TestInventoryProbe.layer == "A"
    assert TestInventoryProbe.tier == "base"
    assert TestInventoryProbe.applies_to_languages == ["javascript", "typescript"]
    assert TestInventoryProbe.applies_to_tasks == ["*"]
    assert TestInventoryProbe.requires == ["language_detection", "node_build_system"]
    assert TestInventoryProbe.timeout_seconds == 10
    assert re.fullmatch(r"0\.\d+\.\d+", TestInventoryProbe.version)
    assert TestInventoryProbe.version == "0.1.0"


def test_declared_inputs_is_list_not_tuple() -> None:
    """AC-3 — S2-02 frozen-ABC ``tuple``-vs-``list`` regression discipline."""
    from codegenie.probes.test_inventory import TestInventoryProbe

    assert isinstance(TestInventoryProbe.declared_inputs, list)
    assert TestInventoryProbe.declared_inputs == [
        "package.json",
        "vitest.config.*",
        "jest.config.*",
        "playwright.config.*",
        ".mocharc.*",
        "test/**/*.test.*",
        "tests/**/*.test.*",
        "src/**/*.test.*",
        "**/*.spec.*",
        "coverage/lcov.info",
        "scripts/smoke.*",
        "tests/smoke/**/*",
    ]


# ---------- AC-4: registration additive ------------------------------------


def test_registry_contains_test_inventory() -> None:
    """AC-4 — additive import in ``probes/__init__.py``."""
    from codegenie.probes import default_registry
    from codegenie.probes.test_inventory import TestInventoryProbe

    names = {p.name for p in default_registry.all_probes()}
    assert "test_inventory" in names
    assert any(p is TestInventoryProbe for p in default_registry.all_probes())


# ---------- AC-5: registry membership across languages ---------------------


@pytest.mark.parametrize(
    "langs, expected",
    [
        (frozenset({"javascript"}), True),
        (frozenset({"typescript"}), True),
        (frozenset({"javascript", "typescript"}), True),
        (frozenset({"go"}), False),
        (frozenset(), False),
    ],
)
def test_registry_membership_across_languages(langs: frozenset[str], expected: bool) -> None:
    """AC-5."""
    from codegenie.probes.registry import default_registry
    from codegenie.probes.test_inventory import TestInventoryProbe

    matched = [p for p in default_registry.for_task("*", langs) if p is TestInventoryProbe]
    assert (len(matched) == 1) is expected


# ---------- AC-6 / AC-7: detector tuples are module-level ------------------


def test_framework_detectors_precedence_anchor() -> None:
    """AC-6."""
    from codegenie.probes.test_inventory import _FRAMEWORK_DETECTORS

    assert _FRAMEWORK_DETECTORS[0] == "vitest"
    assert _FRAMEWORK_DETECTORS == ("vitest", "jest", "mocha", "tap")


def test_e2e_framework_detectors_anchor() -> None:
    """AC-7."""
    from codegenie.probes.test_inventory import _E2E_FRAMEWORK_DETECTORS

    assert _E2E_FRAMEWORK_DETECTORS == ("playwright", "cypress")


# ---------- AC-8: framework × E2E framework matrix -------------------------


@pytest.mark.parametrize(
    "dev_deps, fw, e2e, warns",
    [
        ({"vitest": "^1"}, "vitest", None, []),
        ({"jest": "^29"}, "jest", None, []),
        ({"mocha": "^10"}, "mocha", None, []),
        ({"tap": "^16"}, "tap", None, []),
        ({"@playwright/test": "^1"}, None, "playwright", []),
        ({"cypress": "^13"}, None, "cypress", []),
        ({"jest": "^29", "@playwright/test": "^1"}, "jest", "playwright", []),
        ({"vitest": "^1", "jest": "^29"}, "vitest", None, ["test_framework.ambiguous"]),
    ],
)
def test_framework_e2e_matrix(
    tmp_path: Path,
    dev_deps: dict[str, str],
    fw: str | None,
    e2e: str | None,
    warns: list[str],
) -> None:
    """AC-8."""
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": dev_deps}))
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["framework"] == fw
    assert s["e2e_framework"] == e2e
    for w in warns:
        assert w in s["warnings"]


# ---------- AC-9: multi-E2E precedence -------------------------------------


def test_e2e_ambiguous_alpha_precedence(tmp_path: Path) -> None:
    """AC-9."""
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@playwright/test": "^1", "cypress": "^13"}})
    )
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["e2e_framework"] == "playwright"
    assert "e2e_framework.ambiguous" in s["warnings"]


# ---------- AC-10: node:test precedence rule -------------------------------


@pytest.mark.parametrize(
    "engines, deps, fw",
    [
        ({"node": ">=18"}, {}, "node_test"),
        ({"node": "^20"}, {}, "node_test"),
        ({"node": "~18.10.0"}, {}, "node_test"),
        ({"node": ">=16"}, {}, None),
        ({"node": ">=20"}, {"vitest": "^1"}, "vitest"),
        ({}, {}, None),
    ],
)
def test_node_test_precedence(
    tmp_path: Path,
    engines: dict[str, str],
    deps: dict[str, str],
    fw: str | None,
) -> None:
    """AC-10."""
    (tmp_path / "package.json").write_text(
        json.dumps({"engines": engines, "devDependencies": deps})
    )
    assert _run(tmp_path).schema_slice["test_inventory"]["framework"] == fw


# ---------- AC-11: _engines_at_least table ---------------------------------


@pytest.mark.parametrize(
    "constraint, expected",
    [
        (">=18", True),
        (">=18.0.0", True),
        ("^20", True),
        ("~18.10.0", True),
        (">=16", False),
        ("^17.4.2", False),
        ("", False),
        ("garbage", False),
        (None, False),
    ],
)
def test_engines_at_least_table(constraint: str | None, expected: bool) -> None:
    """AC-11."""
    from codegenie.probes.test_inventory import _engines_at_least

    assert _engines_at_least(constraint, 18) is expected


# ---------- AC-12 / AC-13: test-file pattern matrix ------------------------


@pytest.mark.parametrize(
    "ext",
    [
        ".test.js",
        ".test.jsx",
        ".test.ts",
        ".test.tsx",
        ".test.mjs",
        ".test.cjs",
        ".spec.js",
        ".spec.jsx",
        ".spec.ts",
        ".spec.tsx",
        ".spec.mjs",
        ".spec.cjs",
    ],
)
def test_each_test_file_pattern_counted(tmp_path: Path, ext: str) -> None:
    """AC-12 / AC-13."""
    (tmp_path / "package.json").write_text("{}")
    src = tmp_path / "src"
    src.mkdir()
    (src / f"a{ext}").write_text("")
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["unit_test_file_count"] == 1


# ---------- AC-14: noise-dir exclusion -------------------------------------


def test_test_file_count_excludes_all_noise_dirs(tmp_path: Path) -> None:
    """AC-14."""
    (tmp_path / "package.json").write_text("{}")
    src = tmp_path / "src"
    src.mkdir()
    for i in range(15):
        (src / f"a{i}.test.ts").write_text("")
    for d in ("node_modules/foo", ".git", "dist", "__pycache__", ".next", "build"):
        p = tmp_path / d
        p.mkdir(parents=True)
        (p / "decoy.test.ts").write_text("")
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["unit_test_file_count"] == 15


# ---------- AC-15: _NOISE_DIRS is the imported _SKIP_DIRS ------------------


def test_noise_dirs_is_imported_not_duplicated() -> None:
    """AC-15 — object-identity, not equality."""
    from codegenie.probes.language_detection import _SKIP_DIRS
    from codegenie.probes.test_inventory import _NOISE_DIRS

    assert _NOISE_DIRS is _SKIP_DIRS


# ---------- AC-16: unit_test_count_is_file_count is always True ------------


@pytest.mark.parametrize(
    "fixture",
    [
        {"package.json": "{}"},
        {"package.json": '{"devDependencies": {"jest": "^29"}}'},
        {"package.json": '{"engines": {"node": ">=18"}}'},
    ],
)
def test_unit_test_count_is_file_count_always_true(tmp_path: Path, fixture: dict[str, str]) -> None:
    """AC-16."""
    for name, body in fixture.items():
        (tmp_path / name).write_text(body)
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["unit_test_count_is_file_count"] is True


# ---------- AC-17 / AC-18 / AC-19: canonical scripts ----------------------


def test_canonical_script_names_anchor() -> None:
    """AC-17."""
    from codegenie.probes.test_inventory import _CANONICAL_SCRIPT_NAMES

    assert _CANONICAL_SCRIPT_NAMES == (
        "test",
        "test:unit",
        "test:integration",
        "test:smoke",
        "test:e2e",
        "test:coverage",
    )


def test_canonical_scripts_extracted_verbatim_only(tmp_path: Path) -> None:
    """AC-18 / AC-19 — verbatim, no eval, alpha-sorted keys."""
    pkg = {
        "scripts": {
            "test": "vitest",
            "test:unit": "vitest --run",
            "test:integration": "vitest --integration",
            "test:smoke": "./scripts/smoke.sh",
            "test:e2e": "playwright test",
            "test:coverage": "vitest --coverage",
            "lint": "eslint .",
            "build": "tsc",
        }
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["commands"] == {
        "test": "vitest",
        "test:coverage": "vitest --coverage",
        "test:e2e": "playwright test",
        "test:integration": "vitest --integration",
        "test:smoke": "./scripts/smoke.sh",
        "test:unit": "vitest --run",
    }
    # Alpha-sort verified by the dict literal above (3.7+ insertion order).
    assert list(s["commands"].keys()) == sorted(s["commands"].keys())
    assert "lint" not in s["commands"]
    assert "build" not in s["commands"]


# ---------- AC-20 / AC-21: smoke path precedence ---------------------------


def test_smoke_path_precedence_anchor() -> None:
    """AC-20 — module-level tuple."""
    from codegenie.probes.test_inventory import _SMOKE_PATH_PRECEDENCE

    assert _SMOKE_PATH_PRECEDENCE == (
        "scripts/smoke.sh",
        "scripts/smoke.js",
        "scripts/smoke.ts",
        "tests/smoke",
    )


@pytest.mark.parametrize(
    "files, dirs, expected",
    [
        (["scripts/smoke.sh"], [], "scripts/smoke.sh"),
        ([], ["tests/smoke"], "tests/smoke"),
        (["scripts/smoke.sh", "scripts/smoke.js"], [], "scripts/smoke.sh"),
        (["scripts/smoke.ts"], ["tests/smoke"], "scripts/smoke.ts"),
        ([], [], None),
    ],
)
def test_smoke_path_resolution(
    tmp_path: Path, files: list[str], dirs: list[str], expected: str | None
) -> None:
    """AC-20 / AC-21."""
    (tmp_path / "package.json").write_text("{}")
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["smoke_test_path"] == expected


# ---------- AC-22 / AC-23 / AC-24: lcov scanner module shape ---------------


def test_lcov_prefix_map_anchor() -> None:
    """AC-22."""
    from codegenie.probes._lcov_scanner import _LCOV_PREFIX_MAP

    assert dict(_LCOV_PREFIX_MAP) == {
        "LF:": "lines_found",
        "LH:": "lines_hit",
        "FNF:": "functions_found",
        "FNH:": "functions_hit",
        "BRF:": "branches_found",
        "BRH:": "branches_hit",
    }


def test_lcov_totals_namedtuple_shape() -> None:
    """AC-23."""
    from codegenie.probes._lcov_scanner import LcovTotals

    t = LcovTotals(1, 2, 3, 4, 5, 6)
    assert t._fields == (
        "lines_found",
        "lines_hit",
        "functions_found",
        "functions_hit",
        "branches_found",
        "branches_hit",
    )


def test_lcov_max_bytes_constant() -> None:
    """AC-24."""
    from codegenie.probes._lcov_scanner import _LCOV_MAX_BYTES

    assert _LCOV_MAX_BYTES == 50 * 1024 * 1024


# ---------- AC-25 / AC-26: AST walks (kernel reuse + regex-free) -----------


def test_scanner_reuses_open_capped_kernel() -> None:
    """AC-25."""
    import ast
    import inspect

    from codegenie.probes import _lcov_scanner

    src = Path(inspect.getsourcefile(_lcov_scanner) or "").read_text()
    tree = ast.parse(src)
    has_open_capped_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.parsers._io":
            for alias in node.names:
                if alias.name == "open_capped":
                    has_open_capped_import = True
    assert has_open_capped_import, "lcov scanner MUST import open_capped"
    # No local re-implementation
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    forbidden = {"O_NOFOLLOW", "fstat"}
    assert not (forbidden & names), f"lcov scanner re-implements: {forbidden & names}"


def test_scanner_has_no_regex() -> None:
    """AC-26 — structural ReDoS defense (regex-free over bytes)."""
    import ast
    import inspect

    from codegenie.probes import _lcov_scanner

    src = Path(inspect.getsourcefile(_lcov_scanner) or "").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "re", "scanner imports `re` — ReDoS surface forbidden"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "re", "scanner imports from `re` — ReDoS surface forbidden"


# ---------- AC-27: symlink refusal sentinel --------------------------------


def test_symlink_to_lcov_refused_with_sentinel(tmp_path: Path) -> None:
    """AC-27 — sentinel value (31337) MUST NOT survive into the slice."""
    from codegenie.errors import SymlinkRefusedError
    from codegenie.probes._lcov_scanner import scan

    leak = tmp_path.parent / "SENTINEL_LCOV.info"
    leak.write_text("LF:31337\nLH:31337\nend_of_record\n")
    try:
        link = tmp_path / "lcov.info"
        link.symlink_to(leak)
        with pytest.raises(SymlinkRefusedError):
            scan(link)

        # Probe-level integration
        (tmp_path / "package.json").write_text("{}")
        cov = tmp_path / "coverage"
        cov.mkdir()
        (cov / "lcov.info").symlink_to(leak)
        s = _run(tmp_path).schema_slice["test_inventory"]
        assert "coverage.lcov_parse_error" in s["warnings"]
        assert s["coverage_data"]["totals"] is None
        assert s["coverage_data"]["present"] is True
        assert s["coverage_data"]["parse_error"] is True
        assert "31337" not in repr(s)
    finally:
        if leak.exists():
            leak.unlink()


# ---------- AC-28: byte-budget fuzz (replaces wall-clock-only) ------------


def test_pathological_input_scanned_at_at_least_5MB_per_second(tmp_path: Path) -> None:
    """AC-28 — primary: ≥ 5 MB/s; secondary: < 5 s soft canary."""
    import time

    from codegenie.probes._lcov_scanner import LcovTotals, scan

    p = tmp_path / "lcov.info"
    pathological = ("SF:" * 200_000 + "\n").encode() + b"GARBAGE\n" * 50_000
    p.write_bytes(pathological)
    size = p.stat().st_size
    t0 = time.monotonic()
    t = scan(p)
    elapsed = time.monotonic() - t0
    # Avoid div-by-zero on instantaneous scans
    elapsed = max(elapsed, 1e-6)
    assert size / elapsed >= 5_000_000, f"too slow: {size / elapsed:.0f} B/s"
    assert elapsed < 5.0
    assert t == LcovTotals(0, 0, 0, 0, 0, 0)


# ---------- AC-29: lcov dialect tolerance ----------------------------------


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            "SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n",
            (10, 8, 3, 2, 4, 3),
        ),
        (
            "LF:10\nLH:8\nend_of_record\nLF:5\nLH:3\nend_of_record\n",
            (15, 11, 0, 0, 0, 0),
        ),
        ("LF:10\nLH:8\nend_of_record\n", (10, 8, 0, 0, 0, 0)),
        ("DA:1,2\nLF:10\nLH:8\nend_of_record\n", (10, 8, 0, 0, 0, 0)),
    ],
)
def test_lcov_dialect_tolerance(
    tmp_path: Path, body: str, expected: tuple[int, int, int, int, int, int]
) -> None:
    """AC-29."""
    from codegenie.probes._lcov_scanner import LcovTotals, scan

    p = tmp_path / "lcov.info"
    p.write_text(body)
    assert scan(p) == LcovTotals(*expected)


# ---------- AC-30 / AC-31: coverage_data four-state matrix ----------------


def test_coverage_data_file_absent(tmp_path: Path) -> None:
    """AC-31 (state 1 of 4)."""
    (tmp_path / "package.json").write_text("{}")
    cd = _run(tmp_path).schema_slice["test_inventory"]["coverage_data"]
    assert cd == {"present": False, "parse_error": False, "totals": None}


def test_coverage_data_file_present_parsed_ok(tmp_path: Path) -> None:
    """AC-31 (state 2 of 4)."""
    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"
    cov.mkdir()
    (cov / "lcov.info").write_text(
        "SF:/a.js\nLF:10\nLH:8\nFNF:3\nFNH:2\nBRF:4\nBRH:3\nend_of_record\n"
    )
    cd = _run(tmp_path).schema_slice["test_inventory"]["coverage_data"]
    assert cd["present"] is True
    assert cd["parse_error"] is False
    assert cd["totals"] == {
        "lines_found": 10,
        "lines_hit": 8,
        "functions_found": 3,
        "functions_hit": 2,
        "branches_found": 4,
        "branches_hit": 3,
    }


def test_coverage_data_size_cap_exceeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-31 (state 3 of 4)."""
    from codegenie.probes import _lcov_scanner

    monkeypatch.setattr(_lcov_scanner, "_LCOV_MAX_BYTES", 16)
    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"
    cov.mkdir()
    (cov / "lcov.info").write_bytes(b"x" * 32)
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["coverage_data"] == {"present": True, "parse_error": True, "totals": None}
    assert "coverage.size_cap_exceeded" in s["warnings"]


def test_coverage_data_other_parse_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-31 (state 4 of 4) — generic parse error routes to lcov_parse_error."""
    from codegenie.probes import test_inventory as ti

    (tmp_path / "package.json").write_text("{}")
    cov = tmp_path / "coverage"
    cov.mkdir()
    (cov / "lcov.info").write_text("LF:1\n")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("simulated read failure")

    monkeypatch.setattr(ti, "_lcov_scan", _boom)
    s = _run(tmp_path).schema_slice["test_inventory"]
    assert s["coverage_data"] == {"present": True, "parse_error": True, "totals": None}
    assert "coverage.lcov_parse_error" in s["warnings"]


def test_coverage_block_typeddict_strict() -> None:
    """AC-30 — schema mirror with additionalProperties: false at coverage_data."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    env = _minimal_envelope_with_test_inventory()
    env["probes"]["test_inventory"]["test_inventory"]["coverage_data"]["unknown"] = 1
    with pytest.raises(SchemaValidationError) as ei:
        validate(env)
    assert "unknown" in str(ei.value)


def test_coverage_data_never_python_none_in_phase_1(tmp_path: Path) -> None:
    """AC-32 — meta-test: probe never emits coverage_data is None."""
    fixtures: list[dict[str, str]] = [
        {"package.json": "{}"},
        {
            "package.json": "{}",
            "coverage/lcov.info": "LF:10\nLH:8\nend_of_record\n",
        },
    ]
    for fixture in fixtures:
        # Recreate dir for each fixture
        for name, body in fixture.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        s = _run(tmp_path).schema_slice["test_inventory"]
        assert s["coverage_data"] is not None


# ---------- AC-33 / AC-34 / AC-35 / AC-36: memo behavior --------------------


def test_memo_used_when_provided(tmp_path: Path) -> None:
    """AC-33 / AC-34."""
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    memo = MagicMock(return_value={"devDependencies": {"jest": "^29"}})
    out = _run(tmp_path, parsed_manifest=memo)
    assert memo.call_count == 1
    assert memo.call_args.args[0].name == "package.json"
    assert out.schema_slice["test_inventory"]["framework"] == "jest"


def test_memo_off_falls_back_to_safe_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-35."""
    from codegenie.parsers import safe_json

    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    calls: list[Path] = []
    real_load = safe_json.load

    def _spy_load(path: Path, **kw: Any) -> Any:
        calls.append(path)
        return real_load(path, **kw)

    monkeypatch.setattr(safe_json, "load", _spy_load)
    out = _run(tmp_path, parsed_manifest=None)
    assert any(p.name == "package.json" for p in calls)
    assert out.schema_slice["test_inventory"]["framework"] == "jest"


def test_memo_only_called_for_package_json(tmp_path: Path) -> None:
    """AC-36 — ADR-0002 Phase-1 allowlist."""
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29"}}')
    memo = MagicMock(return_value={"devDependencies": {"jest": "^29"}})
    _run(tmp_path, parsed_manifest=memo)
    for call in memo.mock_calls:
        if call.args:
            assert call.args[0].name == "package.json"


# ---------- AC-37: package.json typed-exception routing -------------------


@pytest.mark.parametrize(
    "exc_name, expected_id",
    [
        ("SizeCapExceeded", "package_json.size_cap_exceeded"),
        ("MalformedJSONError", "package_json.malformed"),
        ("SymlinkRefusedError", "package_json.symlink_refused"),
    ],
)
def test_package_json_failure_routes_to_probeoutput_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc_name: str, expected_id: str
) -> None:
    """AC-37."""
    from codegenie import errors as e
    from codegenie.parsers import safe_json

    (tmp_path / "package.json").write_text("{}")

    def _raise(*a: Any, **kw: Any) -> Any:
        raise getattr(e, exc_name)("boom")

    monkeypatch.setattr(safe_json, "load", _raise)
    out = _run(tmp_path)
    assert expected_id in out.errors
    assert expected_id not in out.schema_slice["test_inventory"]["warnings"]
    s = out.schema_slice["test_inventory"]
    assert s["unit_test_file_count"] == 0
    assert s["unit_test_count_is_file_count"] is True
    assert s["framework"] is None
    assert s["e2e_framework"] is None
    assert s["commands"] == {}
    assert s["smoke_test_path"] is None
    assert s["coverage_data"] == {"present": False, "parse_error": False, "totals": None}


# ---------- AC-38 / AC-39 / AC-40: schema sanity --------------------------


def test_schema_file_exists_and_strict_at_root() -> None:
    """AC-38."""
    schema = json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["test_inventory"]["additionalProperties"] is False


def test_test_inventory_optional_at_envelope() -> None:
    """AC-39 — ADR-0010."""
    envelope = json.loads(Path("src/codegenie/schema/repo_context.schema.json").read_text())
    assert "test_inventory" not in envelope["properties"]["probes"].get("required", [])


def test_unit_test_count_is_file_count_documented() -> None:
    """AC-40."""
    schema = json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())
    desc = schema["properties"]["test_inventory"]["properties"]["unit_test_count_is_file_count"][
        "description"
    ]
    assert "Phase 1" in desc
    assert "file" in desc.lower()
    assert "case" in desc.lower()


# ---------- AC-41: framework / e2e_framework enums closed -----------------


def test_framework_enum_closed() -> None:
    """AC-41 — playwright/cypress NOT in framework enum."""
    schema = json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())
    fw_enum = set(schema["properties"]["test_inventory"]["properties"]["framework"]["enum"])
    assert fw_enum == {"vitest", "jest", "mocha", "tap", "node_test", None}
    e2e_enum = set(schema["properties"]["test_inventory"]["properties"]["e2e_framework"]["enum"])
    assert e2e_enum == {"playwright", "cypress", None}


def test_schema_rejects_playwright_in_framework() -> None:
    """AC-41 — playwright in framework field fails sub-schema validation."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    env = _minimal_envelope_with_test_inventory()
    env["probes"]["test_inventory"]["test_inventory"]["framework"] = "playwright"
    with pytest.raises(SchemaValidationError):
        validate(env)


# ---------- AC-42 / AC-43 / AC-44: warning + error IDs -------------------


def test_warning_ids_anchor() -> None:
    """AC-42."""
    from codegenie.probes.test_inventory import _WARNING_IDS

    assert isinstance(_WARNING_IDS, frozenset)
    assert _WARNING_IDS == frozenset(
        {
            "coverage.lcov_parse_error",
            "coverage.size_cap_exceeded",
            "test_framework.ambiguous",
            "e2e_framework.ambiguous",
        }
    )


def test_error_ids_anchor() -> None:
    """AC-43."""
    from codegenie.probes.test_inventory import _ERROR_IDS

    assert isinstance(_ERROR_IDS, frozenset)
    assert _ERROR_IDS == frozenset(
        {
            "package_json.size_cap_exceeded",
            "package_json.malformed",
            "package_json.symlink_refused",
            "package_json.depth_cap_exceeded",
        }
    )


def test_id_pattern_conformance_loop() -> None:
    """AC-44 — every ID matches the ADR-0007 pattern."""
    from codegenie.probes.test_inventory import _ERROR_IDS, _ID_PATTERN, _WARNING_IDS

    for wid in (*_WARNING_IDS, *_ERROR_IDS):
        assert _ID_PATTERN.match(wid), f"ADR-0007 violation: {wid!r}"
        assert ADR_0007.match(wid), f"global pattern check: {wid!r}"


# ---------- AC-45: walk-every-nested-block additionalProperties:false ----


def test_schema_additionalproperties_false_walks_every_object() -> None:
    """AC-45."""
    schema = json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())
    bad: list[str] = []

    def _walk(node: Any, ptr: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                if node.get("additionalProperties") is not False:
                    bad.append(ptr)
            for k, v in node.items():
                _walk(v, ptr + "/" + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, ptr + f"/{i}")

    _walk(schema, "")
    assert bad == []


# ---------- AC-46: schema rejection at exact JSON Pointer ----------------


@pytest.mark.parametrize(
    "path, bad_value",
    [
        (["unknown"], 1),
        (["coverage_data", "unknown"], 1),
        (["framework"], "playwright"),
    ],
)
def test_schema_rejection_at_exact_json_pointer(path: list[str], bad_value: Any) -> None:
    """AC-46."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    env = _minimal_envelope_with_test_inventory()
    node: dict[str, Any] = env["probes"]["test_inventory"]["test_inventory"]
    for k in path[:-1]:
        node = node[k]  # type: ignore[assignment]
    node[path[-1]] = bad_value
    with pytest.raises(SchemaValidationError) as ei:
        validate(env)
    # The error message contains the JSON Pointer; just assert key
    # markers landed in the failure rather than a brittle exact string.
    msg = str(ei.value)
    assert "test_inventory" in msg


# ---------- AC-47: confidence field rejected ------------------------------


def test_confidence_field_rejected_by_schema() -> None:
    """AC-47 — TestInventorySlice has no confidence semantics."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    env = _minimal_envelope_with_test_inventory()
    env["probes"]["test_inventory"]["test_inventory"]["confidence"] = "high"
    with pytest.raises(SchemaValidationError) as ei:
        validate(env)
    assert "confidence" in str(ei.value)


# ---------- AC-48: two-run byte-equal determinism ------------------------


def test_two_runs_byte_equal_determinism(tmp_path: Path) -> None:
    """AC-48."""
    import os
    import random

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "devDependencies": {"jest": "^29", "@playwright/test": "^1"},
                "scripts": {
                    "test": "jest",
                    "test:unit": "jest --unit",
                    "test:smoke": "./scripts/smoke.sh",
                    "test:e2e": "playwright test",
                },
            }
        )
    )
    src = tmp_path / "src"
    src.mkdir()
    for i in range(5):
        (src / f"a{i}.test.ts").write_text("")
    for i in range(2):
        (src / f"b{i}.spec.js").write_text("")
    cov = tmp_path / "coverage"
    cov.mkdir()
    (cov / "lcov.info").write_text("LF:10\nLH:5\nend_of_record\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "smoke.sh").write_text("")

    s1 = _run(tmp_path).schema_slice["test_inventory"]
    for p in tmp_path.rglob("*"):
        if p.is_file():
            t = random.randint(1_700_000_000, 1_800_000_000)
            os.utime(p, ns=(t * 1_000_000_000, t * 1_000_000_000))
    s2 = _run(tmp_path).schema_slice["test_inventory"]
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)


# ---------- AC-49: structlog events --------------------------------------


def test_structlog_events_emitted(tmp_path: Path) -> None:
    """AC-49 — probe.start + probe.success on enter / exit."""
    from structlog.testing import capture_logs

    (tmp_path / "package.json").write_text("{}")
    with capture_logs() as records:
        _run(tmp_path)
    events = [r["event"] for r in records]
    assert "probe.start" in events
    assert "probe.success" in events
    # probe.success carries the discriminating keys
    success = next(r for r in records if r["event"] == "probe.success")
    assert "framework" in success
    assert "e2e_framework" in success
    assert "unit_test_file_count" in success
    assert "coverage_present" in success


# ---------- AC-50: pure helpers individually unit-tested ------------------


def test_select_framework_helper() -> None:
    """AC-50 #2."""
    from codegenie.probes.test_inventory import _select_framework

    assert _select_framework({"vitest"}) == ("vitest", False)
    assert _select_framework({"jest"}) == ("jest", False)
    assert _select_framework({"vitest", "jest"}) == ("vitest", True)
    assert _select_framework(set()) == (None, False)


def test_select_e2e_framework_helper() -> None:
    """AC-50 #3."""
    from codegenie.probes.test_inventory import _select_e2e_framework

    assert _select_e2e_framework({"@playwright/test"}) == ("playwright", False)
    assert _select_e2e_framework({"cypress"}) == ("cypress", False)
    assert _select_e2e_framework({"@playwright/test", "cypress"}) == ("playwright", True)
    assert _select_e2e_framework(set()) == (None, False)


def test_count_test_files_helper(tmp_path: Path) -> None:
    """AC-50 #4."""
    from codegenie.probes.test_inventory import _count_test_files

    (tmp_path / "a.test.ts").write_text("")
    (tmp_path / "b.spec.js").write_text("")
    (tmp_path / "ignored.txt").write_text("")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "x.test.ts").write_text("")
    assert _count_test_files(tmp_path) == 2


def test_select_smoke_path_helper(tmp_path: Path) -> None:
    """AC-50 #5."""
    from codegenie.probes.test_inventory import _select_smoke_path

    assert _select_smoke_path(tmp_path) is None
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "smoke.sh").write_text("")
    assert _select_smoke_path(tmp_path) == "scripts/smoke.sh"


def test_extract_canonical_scripts_helper() -> None:
    """AC-50 #6."""
    from codegenie.probes.test_inventory import _extract_canonical_scripts

    pkg = {
        "scripts": {
            "test": "x",
            "test:unit": "y",
            "lint": "eslint",
            "non_string": 123,
        }
    }
    out = _extract_canonical_scripts(pkg)
    assert out == {"test": "x", "test:unit": "y"}
    assert _extract_canonical_scripts({"scripts": "not a dict"}) == {}
    assert _extract_canonical_scripts({}) == {}


def test_classify_node_test_helper() -> None:
    """AC-50 #7."""
    from codegenie.probes.test_inventory import _classify_node_test

    assert _classify_node_test({"engines": {"node": ">=18"}}, None) == ("node_test", [])
    assert _classify_node_test({"engines": {"node": ">=20"}}, "vitest") == ("vitest", [])
    assert _classify_node_test({"engines": {"node": ">=16"}}, None) == (None, [])
    assert _classify_node_test({}, None) == (None, [])
    assert _classify_node_test({"engines": "not_a_dict"}, None) == (None, [])


# ---------- AC-51 / AC-52: forbidden patterns ----------------------------


def test_no_lcov_parse_pypi_dep_added() -> None:
    """AC-51 — ADR-0009."""
    pyproject = Path("pyproject.toml").read_text()
    forbidden = ["lcov-parse", "coverage-parse", "python-lcov", "pyjson5", "orjson"]
    for token in forbidden:
        assert token not in pyproject, f"forbidden dep {token!r} appeared in pyproject.toml"


def test_no_subprocess_in_probe_or_scanner() -> None:
    """AC-52."""
    import ast
    import inspect

    from codegenie.probes import _lcov_scanner, test_inventory

    for mod in (test_inventory, _lcov_scanner):
        src = Path(inspect.getsourcefile(mod) or "").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", (
                        f"{mod.__name__}: subprocess import forbidden"
                    )
                    assert "_exec" not in alias.name, (
                        f"{mod.__name__}: must not invoke run_allowlisted"
                    )
            if isinstance(node, ast.ImportFrom):
                assert node.module != "subprocess", (
                    f"{mod.__name__}: from subprocess import forbidden"
                )


# ---------- AC-53: no additionalProperties: true anywhere ----------------


def test_no_additionalproperties_true_anywhere() -> None:
    """AC-53."""
    schema = json.loads(Path("src/codegenie/schema/probes/test_inventory.schema.json").read_text())

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            ap = node.get("additionalProperties")
            assert ap is not True, f"unexpected additionalProperties: true at {node!r}"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(schema)
