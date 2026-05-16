"""Tests for the on-disk ``tools/grammars.lock`` and vendored binaries.

S4-03 AC-10 / AC-11 / AC-12 / AC-18 — schema + BLAKE3 verification of the
real, vendored artifacts; idempotency of the regen script; refusal on
missing binary; ``.gitattributes`` marks the binaries as binary.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from blake3 import blake3

from codegenie.grammars.lock import GrammarLockFile, load_and_verify

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = REPO_ROOT / "tools" / "grammars.lock"
GRAMMARS_DIR = REPO_ROOT / "tools" / "grammars"
REGEN_SCRIPT = REPO_ROOT / "tools" / "regenerate_grammars_lock.sh"


def test_grammars_lock_schema_and_blake3() -> None:
    """T-14: parse + verify every BLAKE3 against the vendored binary."""
    lock = load_and_verify(REPO_ROOT)
    assert isinstance(lock, GrammarLockFile)
    for pin in lock.grammars:
        actual = blake3((REPO_ROOT / pin.file).read_bytes()).hexdigest()
        assert actual == pin.blake3, (
            f"BLAKE3 drift for {pin.language}: pin={pin.blake3} actual={actual}"
        )


def test_grammars_lock_lists_typescript_and_javascript() -> None:
    """T-15: AC-10 — both languages present."""
    lock = load_and_verify(REPO_ROOT)
    langs = {pin.language for pin in lock.grammars}
    assert "typescript" in langs
    assert "javascript" in langs


def test_regenerate_script_idempotent(tmp_path: Path) -> None:
    """T-16: AC-11 — running the script twice produces byte-identical output."""
    # Copy tools/ into a temp workspace to avoid mutating the real repo file.
    repo_copy = tmp_path / "repo"
    (repo_copy / "tools" / "grammars").mkdir(parents=True)
    for src in GRAMMARS_DIR.glob("*.so"):
        shutil.copyfile(src, repo_copy / "tools" / "grammars" / src.name)
    shutil.copyfile(LOCK_FILE, repo_copy / "tools" / "grammars.lock")
    # Place the regenerate script under the copy with the same relative path.
    (repo_copy / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REGEN_SCRIPT, repo_copy / "tools" / "regenerate_grammars_lock.sh")
    os.chmod(repo_copy / "tools" / "regenerate_grammars_lock.sh", 0o755)
    # Symlink ``.venv/bin/python`` so the script's interpreter lookup
    # succeeds inside the tmp tree.
    # Symlink the entire .venv so the script's interpreter resolution
    # picks up the same site-packages (blake3, pyyaml) the test process
    # has — a bare ``python`` interpreter alone would lack the deps.
    real_venv = REPO_ROOT / ".venv"
    if real_venv.is_dir():
        (repo_copy / ".venv").symlink_to(real_venv)

    subprocess.run(
        ["bash", str(repo_copy / "tools" / "regenerate_grammars_lock.sh")],
        check=True,
        capture_output=True,
    )
    first = (repo_copy / "tools" / "grammars.lock").read_bytes()
    subprocess.run(
        ["bash", str(repo_copy / "tools" / "regenerate_grammars_lock.sh")],
        check=True,
        capture_output=True,
    )
    second = (repo_copy / "tools" / "grammars.lock").read_bytes()
    assert first == second, "regenerate script must be idempotent"


def test_regenerate_script_refuses_missing_binary(tmp_path: Path) -> None:
    """T-17: AC-11 — script exits 1 when a referenced binary is missing."""
    repo_copy = tmp_path / "repo"
    (repo_copy / "tools" / "grammars").mkdir(parents=True)
    # Copy lock but NOT the binaries; the lock references them.
    shutil.copyfile(LOCK_FILE, repo_copy / "tools" / "grammars.lock")
    shutil.copyfile(REGEN_SCRIPT, repo_copy / "tools" / "regenerate_grammars_lock.sh")
    os.chmod(repo_copy / "tools" / "regenerate_grammars_lock.sh", 0o755)
    # Symlink the entire .venv so the script's interpreter resolution
    # picks up the same site-packages (blake3, pyyaml) the test process
    # has — a bare ``python`` interpreter alone would lack the deps.
    real_venv = REPO_ROOT / ".venv"
    if real_venv.is_dir():
        (repo_copy / ".venv").symlink_to(real_venv)

    result = subprocess.run(
        ["bash", str(repo_copy / "tools" / "regenerate_grammars_lock.sh")],
        capture_output=True,
    )
    assert result.returncode == 1, (
        f"expected exit 1; got {result.returncode}; stderr={result.stderr!r}"
    )
    assert b"missing" in result.stderr.lower()


def test_gitattributes_marks_so_and_dylib_binary() -> None:
    """T-18: AC-12 — .gitattributes treats grammar binaries as binary."""
    attrs = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "tools/grammars/*.so binary" in attrs
    assert "tools/grammars/*.dylib binary" in attrs
