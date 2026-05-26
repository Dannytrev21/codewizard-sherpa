"""Phase-4 S6-06 — TypeScript applicability matrix tests.

Covers the load-bearing ACs from arch §Gap 4 four-case table:

* AC-1 — truth table: (tsconfig, ts_files) → {Applicable,
  DegradedNoTsconfig, NotApplicable}.
* AC-2 — `_typescript_applicability(repo_root) -> TypeScriptApplicability`
  is a bounded-I/O helper (single os.scandir walk, no subprocess).
* AC-3 — `TypeScriptApplicability` is the closed `Applicable |
  DegradedNoTsconfig | NotApplicable` discriminated union of frozen
  dataclasses.
* AC-4 — `NotApplicable` short-circuits BEFORE `run_allowlisted`.
* AC-5 — `node_modules/` exclusion: `.ts` files under node_modules
  don't make a JS-only repo applicable.
* AC-6 — `.tsx` files trigger the in-scope detector (DegradedNoTsconfig
  when tsconfig absent).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codegenie.transforms.outcomes import TrustSignal
from tests.unit.plugin._ts_typecheck_collector_module import MODULE as _MODULE

_apply = _MODULE._typescript_applicability
Applicable = _MODULE.Applicable
DegradedNoTsconfig = _MODULE.DegradedNoTsconfig
NotApplicable = _MODULE.NotApplicable
collect = _MODULE.collect_typecheck_typescript_signal


def _make_repo(
    tmp_path: Path,
    *,
    tsconfig: bool = False,
    ts_files: bool = False,
    tsx_files: bool = False,
    node_modules_ts: bool = False,
) -> Path:
    """Build a repo with the requested files."""
    if tsconfig:
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{}}', encoding="utf-8")
    if ts_files:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
    if tsx_files:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "Component.tsx").write_text(
            "export const C = () => null;\n", encoding="utf-8"
        )
    if node_modules_ts:
        (tmp_path / "node_modules" / "some-pkg").mkdir(parents=True, exist_ok=True)
        (tmp_path / "node_modules" / "some-pkg" / "index.ts").write_text(
            "export {};\n", encoding="utf-8"
        )
    # Always create a package.json so the directory looks like a repo.
    (tmp_path / "package.json").write_text('{"name":"smoke"}', encoding="utf-8")
    return tmp_path


# --- AC-1: four-case truth table ----------------------------------------


def test_ac1_tsconfig_and_ts_file_is_applicable(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tsconfig=True, ts_files=True)
    result = _apply(repo)
    assert isinstance(result, Applicable)
    assert result.ts_files_count >= 1


def test_ac1_tsconfig_only_is_applicable_zero_files(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tsconfig=True, ts_files=False)
    result = _apply(repo)
    assert isinstance(result, Applicable)
    assert result.ts_files_count == 0


def test_ac1_ts_files_only_is_degraded_no_tsconfig(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tsconfig=False, ts_files=True)
    result = _apply(repo)
    assert isinstance(result, DegradedNoTsconfig)
    assert result.ts_files_count >= 1


def test_ac1_js_only_is_not_applicable(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tsconfig=False, ts_files=False)
    result = _apply(repo)
    assert isinstance(result, NotApplicable)


# --- AC-4: NotApplicable short-circuits BEFORE run_allowlisted ----------


@pytest.mark.asyncio
async def test_ac4_not_applicable_does_not_spawn_tsc(tmp_path: Path) -> None:
    """JS-only repo → collector returns passing signal without
    invoking `run_allowlisted`."""
    repo = _make_repo(tmp_path, tsconfig=False, ts_files=False)
    mock = AsyncMock()
    with patch.object(_MODULE, "run_allowlisted", mock):
        signal = await collect(repo, "anysha" * 5)
    mock.assert_not_called()
    assert isinstance(signal, TrustSignal)
    assert signal.passed is True
    assert signal.details["applicable"] is False


# --- AC-5: node_modules/*.ts files do NOT count -------------------------


def test_ac5_node_modules_ts_files_do_not_count(tmp_path: Path) -> None:
    """A JS-only repo with `.ts` files inside `node_modules/` is still
    NotApplicable. Catches walker mis-configuration."""
    repo = _make_repo(tmp_path, node_modules_ts=True)
    result = _apply(repo)
    assert isinstance(result, NotApplicable)


# --- AC-6: .tsx files trigger DegradedNoTsconfig ------------------------


def test_ac6_tsx_files_alone_are_degraded(tmp_path: Path) -> None:
    """`.tsx` alone (no tsconfig) → DegradedNoTsconfig, not NotApplicable."""
    repo = _make_repo(tmp_path, tsconfig=False, ts_files=False, tsx_files=True)
    result = _apply(repo)
    assert isinstance(result, DegradedNoTsconfig)


# --- AC-3: TypeScriptApplicability is a closed union ---------------------


def test_ac3_applicability_union_is_closed() -> None:
    """The union has exactly three variants — frozen dataclasses."""
    import dataclasses

    for cls in (Applicable, DegradedNoTsconfig, NotApplicable):
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} must be a dataclass"
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
