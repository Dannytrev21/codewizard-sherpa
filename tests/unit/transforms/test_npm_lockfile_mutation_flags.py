"""AC-4b — per-flag mutation test for ``NpmLockfileRecipeEngine``.

Each of the four ``npm install`` flags must carry observable weight: dropping
any one must change the produced ``Transform``. The fake jail here records the
``cmd`` it was handed into the regenerated lockfile, so a dropped flag yields
a different lockfile, a different ``after`` diff section, and therefore a
different ``diff_bytes``. A flag that could be silently removed without
breaking this test would be dead weight — that is exactly what AC-4b forbids.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import pytest

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.engines import npm_lockfile as eng_mod
from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
from codegenie.transforms.outcomes import ApplicationPlan, Applied
from codegenie.transforms.sandbox_jail import (
    Completed,
    JailedSubprocessResult,
    JailedSubprocessSpec,
)
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import PackageId, PluginId, RegistryUrl, TransformKind


class FlagSensitiveJail:
    """Fake jail whose regenerated lockfile records the exact ``cmd`` it ran —
    so a different flag set produces different lockfile bytes."""

    def __init__(self) -> None:
        self.calls: list[JailedSubprocessSpec] = []

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        lockfile: dict[str, Any] = {
            "name": "fixture",
            "lockfileVersion": 3,
            "packages": {},
            "_observed_cmd": list(spec.cmd),
        }
        (Path(str(spec.cwd)) / "package-lock.json").write_bytes(
            orjson.dumps(lockfile, option=orjson.OPT_INDENT_2) + b"\n"
        )
        return Completed(
            kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.01
        )


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_bytes(
        orjson.dumps(
            {"name": "fixture", "version": "1.0.0", "dependencies": {"express": "^4.17.1"}},
            option=orjson.OPT_INDENT_2,
        )
        + b"\n"
    )
    (root / "package-lock.json").write_bytes(
        orjson.dumps({"name": "fixture", "lockfileVersion": 3, "packages": {}}) + b"\n"
    )
    return root


def _plan() -> ApplicationPlan:
    return ApplicationPlan.for_npm_semver_bump(
        package=PackageId("express"),
        from_version="^4.17.1",
        to_version="^4.19.2",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )


def _capability() -> NpmInstallCapability:
    return NpmInstallCapability(
        registry=RegistryUrl("https://registry.npmjs.org"),
        minted_by=PluginId("vuln-node-npm"),
    )


async def _diff_bytes_for_repo(repo: Path) -> bytes:
    registry = TransformRegistry()
    outcome = await NpmLockfileRecipeEngine(
        jail=FlagSensitiveJail(), transform_registry=registry
    ).apply(SandboxedPath(absolute=repo), _plan(), _capability())
    assert isinstance(outcome, Applied)
    return registry.get(outcome.transform_id).diff_bytes


@pytest.mark.parametrize("drop_index", [2, 3, 4, 5])
async def test_dropping_each_flag_changes_the_transform(
    tmp_path: Path, drop_index: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4b — dropping any one of the four flags produces a different
    ``diff_bytes`` than the full-flag baseline."""
    baseline = await _diff_bytes_for_repo(_repo(tmp_path / "baseline"))

    full = eng_mod._NPM_INSTALL_CMD
    shortened = tuple(flag for i, flag in enumerate(full) if i != drop_index)
    monkeypatch.setattr(eng_mod, "_NPM_INSTALL_CMD", shortened)

    mutant = await _diff_bytes_for_repo(_repo(tmp_path / f"drop-{drop_index}"))
    dropped_flag = full[drop_index]
    assert mutant != baseline, (
        f"dropping {dropped_flag!r} (index {drop_index}) did not change the "
        f"transform — the flag carries no observable weight"
    )
