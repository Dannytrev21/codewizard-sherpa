"""Phase 7 S1-03 AC-14 — `mypy --strict` pins the static-typing layer of
the `Both` recursion guard.

The runtime tests (AC-4 in `test_provenance_union.py`) prove Pydantic
rejects illegal `Both(app_record=..., base_record=...)` shapes at
construction. But a future implementation that widens
`Both.app_record: AppKind | Both` (or `AppKind | Unknown`) would pass
every runtime test while silently regressing the static guarantee that
gives the recursion guard its "the type system itself enforces it"
status (Phase 7 ADR-0006 + arch §Design patterns applied row 1).

This file runs `mypy --strict` over hand-written snippets that pass a
forbidden variant into `Both` — they MUST be mypy errors. Companion
positive-control snippets prove `mypy` is actually running (a silent CI
mypy failure would otherwise make every "rejects" test pass for the
wrong reason).

Mirrors the S1-02 / S1-01 precedent
(`tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py`,
`tests/unit/types/test_identifiers_phase7_mypy_negative.py`).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


def _run_mypy_strict(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    src_file = tmp_path / "snippet.py"
    src_file.write_text(textwrap.dedent(body), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "--no-incremental", str(src_file)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_mypy_rejects_both_inside_both_app_record(tmp_path: Path) -> None:
    """`Both` is not a member of `AppKind` — passing a `Both` to
    `Both(app_record=...)` is a static error."""
    proc = _run_mypy_strict(
        tmp_path,
        """
        from pathlib import Path
        from codegenie.primitives.vuln_provenance import (
            AdapterConfidence, AppDirect, BaseImage, Both, DistroPackage,
        )
        from codegenie.types.identifiers import (
            DockerStageName, ImageDigest, LayerDigest, PackageId,
        )

        app = AppDirect(
            manifest_path=Path("package.json"),
            package=PackageId("a@1.0.0"),
            confidence=AdapterConfidence.HIGH,
        )
        base = BaseImage(
            image_digest=ImageDigest("sha256:" + "0" * 64),
            layer_digest=LayerDigest("sha256:" + "a" * 64),
            distro_pkg=DistroPackage(name="x", version="1", distro="alpine"),
            stage=DockerStageName("s"),
            confidence=AdapterConfidence.HIGH,
        )
        inner = Both(app_record=app, base_record=base)
        # Nested Both — type error.
        _ = Both(app_record=inner, base_record=base)
        """,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted a nested Both in Both.app_record — the static "
        f"recursion guard regressed. stdout={proc.stdout!r}"
    )


def test_mypy_rejects_unknown_in_both_app_record(tmp_path: Path) -> None:
    """`Unknown` is not a member of `AppKind` — passing an `Unknown` to
    `Both(app_record=...)` is a static error. (Pin for the arch's
    "AppKind excludes Unknown" rule, which routes `Unknown`-app cases
    through `assemble_provenance`'s `(None, base)` arm in S2-04 instead.)"""
    proc = _run_mypy_strict(
        tmp_path,
        """
        from codegenie.primitives.vuln_provenance import (
            AdapterConfidence, BaseImage, Both, DistroPackage, Unknown,
        )
        from codegenie.types.identifiers import (
            DockerStageName, ImageDigest, LayerDigest,
        )

        base = BaseImage(
            image_digest=ImageDigest("sha256:" + "0" * 64),
            layer_digest=LayerDigest("sha256:" + "a" * 64),
            distro_pkg=DistroPackage(name="x", version="1", distro="alpine"),
            stage=DockerStageName("s"),
            confidence=AdapterConfidence.HIGH,
        )
        # Unknown is not in AppKind — static error.
        _ = Both(app_record=Unknown(reason="no_adapter_resolved"), base_record=base)
        """,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted Unknown in Both.app_record — the static "
        f"AppKind-excludes-Unknown invariant regressed. stdout={proc.stdout!r}"
    )


def test_mypy_rejects_base_image_in_app_record(tmp_path: Path) -> None:
    """`BaseImage` is not a member of `AppKind` — base-layer variants in
    `Both.app_record` is a static error, mirroring the runtime AC-4
    case."""
    proc = _run_mypy_strict(
        tmp_path,
        """
        from codegenie.primitives.vuln_provenance import (
            AdapterConfidence, BaseImage, Both, DistroPackage,
        )
        from codegenie.types.identifiers import (
            DockerStageName, ImageDigest, LayerDigest,
        )

        base = BaseImage(
            image_digest=ImageDigest("sha256:" + "0" * 64),
            layer_digest=LayerDigest("sha256:" + "a" * 64),
            distro_pkg=DistroPackage(name="x", version="1", distro="alpine"),
            stage=DockerStageName("s"),
            confidence=AdapterConfidence.HIGH,
        )
        # BaseImage is not in AppKind — static error.
        _ = Both(app_record=base, base_record=base)
        """,
    )
    assert proc.returncode != 0, (
        "mypy --strict accepted BaseImage in Both.app_record — the static "
        f"AppKind/BaseKind partition regressed. stdout={proc.stdout!r}"
    )


@pytest.mark.parametrize(
    "body",
    [
        # Happy-path: AppKind member into Both.app_record.
        """
        from pathlib import Path
        from codegenie.primitives.vuln_provenance import (
            AdapterConfidence, AppDirect, BaseImage, Both, DistroPackage,
        )
        from codegenie.types.identifiers import (
            DockerStageName, ImageDigest, LayerDigest, PackageId,
        )

        app = AppDirect(
            manifest_path=Path("p.json"),
            package=PackageId("a@1.0.0"),
            confidence=AdapterConfidence.HIGH,
        )
        base = BaseImage(
            image_digest=ImageDigest("sha256:" + "0" * 64),
            layer_digest=LayerDigest("sha256:" + "a" * 64),
            distro_pkg=DistroPackage(name="x", version="1", distro="alpine"),
            stage=DockerStageName("s"),
            confidence=AdapterConfidence.HIGH,
        )
        _ = Both(app_record=app, base_record=base)
        """,
        # Happy-path: exhaustive match against Provenance compiles.
        """
        from typing import assert_never
        from codegenie.primitives.vuln_provenance import (
            AppDirect, AppTransitive, AppVendored, BaseImage,
            Both, Provenance, RuntimeBundled, Unknown,
        )

        def describe(p: Provenance) -> str:
            match p:
                case AppDirect():
                    return "ad"
                case AppTransitive():
                    return "at"
                case AppVendored():
                    return "av"
                case BaseImage():
                    return "bi"
                case RuntimeBundled():
                    return "rb"
                case Both():
                    return "b"
                case Unknown():
                    return "u"
                case _:
                    assert_never(p)
        """,
    ],
    ids=["app_into_both_ok", "exhaustive_match_ok"],
)
def test_mypy_accepts_correct_provenance_usage(tmp_path: Path, body: str) -> None:
    """Negative-control. If `mypy` silently fails to start in CI, the
    rejects-cases above would all pass for the wrong reason; this proves
    `mypy` runs and the union/aliases are statically well-typed."""
    proc = _run_mypy_strict(tmp_path, body)
    assert proc.returncode == 0, (
        f"mypy --strict rejected correct provenance usage. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
