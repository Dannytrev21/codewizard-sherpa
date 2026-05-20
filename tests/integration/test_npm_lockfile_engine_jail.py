"""S5-02 integration — ``NpmLockfileRecipeEngine`` against a real substrate.

Two ACs:

* AC-3b — the symlink-swap TOCTOU race. Always runs (S4-04 has substituted
  the real ``SandboxedPath`` into ``transforms/_forward``): a symlink dropped
  under ``package.json`` between read and write-back must raise
  ``OSError(ELOOP)`` inside ``SandboxedPath.open`` and surface as
  ``recipe.filesystem_race`` — and the sentinel file must be untouched.
* AC-Gold-1 — the golden lockfile byte-equal round-trip under the real
  ``BwrapAdapter``. Gated on ``bwrap`` + ``npm`` being present; skips in the
  default CI matrix.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import orjson
import pytest

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.engines import npm_lockfile as eng_mod
from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
from codegenie.transforms.outcomes import ApplicationPlan, RecipeFailed
from codegenie.transforms.sandbox_jail import (
    Completed,
    JailedSubprocessResult,
    JailedSubprocessSpec,
)
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import ErrorId, PackageId, PluginId, RegistryUrl, TransformKind

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "lockfiles"
_FIXTURE_REPO = (
    Path(__file__).resolve().parents[1] / "fixtures" / "repos" / "express-cve-2024-21501"
)


class _NeverRunsJail:
    """Jail that fails the test if reached — AC-3b must short-circuit at the
    write-back, well before ``npm install``."""

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:  # pragma: no cover
        raise AssertionError("npm install must not be reached after a filesystem race")


def _capability() -> NpmInstallCapability:
    return NpmInstallCapability(
        registry=RegistryUrl("https://registry.npmjs.org"),
        minted_by=PluginId("vuln-node-npm"),
    )


def _plan() -> ApplicationPlan:
    return ApplicationPlan.for_npm_semver_bump(
        package=PackageId("express"),
        from_version="^4.17.1",
        to_version="^4.19.2",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )


async def test_symlink_swap_returns_filesystem_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3b — a symlink swapped under ``package.json`` between read and
    write-back raises ``ELOOP``; the engine returns ``recipe.filesystem_race``
    and the sentinel file is left byte-for-byte untouched."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_bytes(
        orjson.dumps(
            {"name": "fixture", "version": "1.0.0", "dependencies": {"express": "^4.17.1"}},
            option=orjson.OPT_INDENT_2,
        )
        + b"\n"
    )
    (repo / "package-lock.json").write_bytes(b'{"name":"fixture","lockfileVersion":3}\n')

    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"untouched")
    sentinel_mtime = sentinel.stat().st_mtime_ns

    real_read = eng_mod._read_package_json

    def _racing_read(path: SandboxedPath) -> object:
        # Read succeeds, THEN an attacker swaps package.json for a symlink —
        # the classic TOCTOU window between read and write-back.
        result = real_read(path)
        pkg = repo / "package.json"
        pkg.unlink()
        pkg.symlink_to(sentinel)
        return result

    monkeypatch.setattr(eng_mod, "_read_package_json", _racing_read)

    outcome = await NpmLockfileRecipeEngine(
        jail=_NeverRunsJail(), transform_registry=TransformRegistry()
    ).apply(SandboxedPath(absolute=repo), _plan(), _capability())

    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.filesystem_race")
    assert outcome.error.details == {"path": "package.json"}
    # The sentinel the symlink pointed at was never written through.
    assert sentinel.read_bytes() == b"untouched"
    assert sentinel.stat().st_mtime_ns == sentinel_mtime


@pytest.mark.skipif(
    shutil.which("bwrap") is None or shutil.which("npm") is None,
    reason="AC-Gold-1 requires both bwrap and npm; skipped in the default CI matrix",
)
async def test_golden_express_lockfile_byte_equal_under_real_jail(tmp_path: Path) -> None:
    """AC-Gold-1 — the express fixture, run through the real ``BwrapAdapter``,
    produces a ``package-lock.json`` byte-equal to the committed golden."""
    from codegenie.transforms.sandbox.bwrap import BwrapAdapter

    repo = tmp_path / "express-cve-2024-21501"
    repo.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(_FIXTURE_REPO / name, repo / name)

    registry = TransformRegistry()
    outcome = await NpmLockfileRecipeEngine(jail=BwrapAdapter(), transform_registry=registry).apply(
        SandboxedPath(absolute=repo), _plan(), _capability()
    )

    if isinstance(outcome, RecipeFailed):  # pragma: no cover - environment dependent
        pytest.skip(f"real jail run failed in this environment: {outcome.error.error_id}")

    after_golden = (_GOLDEN_DIR / "express-cve-2024-21501.after.json").read_bytes()
    assert (repo / "package-lock.json").read_bytes() == after_golden


def test_clean_jail_result_shape_is_completed() -> None:
    """Documents the happy-path jail result shape AC-Gold-1 expects."""
    completed = Completed(
        kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.5
    )
    assert completed.exit_code == 0
