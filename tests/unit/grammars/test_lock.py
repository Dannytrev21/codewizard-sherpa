"""Tests for ``codegenie.grammars.lock`` (S4-03 AC-20).

T-21 — happy path AND mismatch path, plus the negative cases the loader is
load-bearing for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.grammars.lock import (
    GrammarLoadRefused,
    GrammarLockFile,
    GrammarPin,
    load_and_verify,
)


def _write_pair(tmp_path: Path, content: bytes) -> tuple[Path, str]:
    """Write a placeholder binary; return (file_path, blake3_hex)."""
    from blake3 import blake3

    grammars_dir = tmp_path / "tools" / "grammars"
    grammars_dir.mkdir(parents=True, exist_ok=True)
    fp = grammars_dir / "typescript.so"
    fp.write_bytes(content)
    return fp, blake3(content).hexdigest()


def _write_lock(
    repo_root: Path, *, blake3_hex: str, file_rel: str = "tools/grammars/typescript.so"
) -> Path:
    lock_path = repo_root / "tools" / "grammars.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        "schema_version: 1\n"
        "grammars:\n"
        "  - language: typescript\n"
        '    version: "0.20.6"\n'
        f"    file: {file_rel}\n"
        f'    blake3: "{blake3_hex}"\n',
        encoding="utf-8",
    )
    return lock_path


def test_load_and_verify_happy_path(tmp_path: Path) -> None:
    """T-21 happy: BLAKE3 matches → returns parsed GrammarLockFile."""
    _, digest = _write_pair(tmp_path, b"hello grammar")
    _write_lock(tmp_path, blake3_hex=digest)

    lock = load_and_verify(tmp_path)
    assert isinstance(lock, GrammarLockFile)
    assert lock.schema_version == 1
    assert [p.language for p in lock.grammars] == ["typescript"]
    assert lock.grammars[0].blake3 == digest


def test_load_and_verify_tampered_binary_refused(tmp_path: Path) -> None:
    """T-21 mismatch: tamper one byte → GrammarLoadRefused names language."""
    fp, digest = _write_pair(tmp_path, b"hello grammar")
    _write_lock(tmp_path, blake3_hex=digest)

    # Tamper the binary AFTER writing the lock — the lock's pin no longer matches.
    fp.write_bytes(b"hello grammar tampered")

    with pytest.raises(
        GrammarLoadRefused,
        match=r"language='typescript'.*BLAKE3 mismatch|BLAKE3 mismatch.*typescript",
    ):
        load_and_verify(tmp_path)


def test_load_and_verify_missing_lock_file(tmp_path: Path) -> None:
    with pytest.raises(GrammarLoadRefused, match=r"grammars\.lock missing"):
        load_and_verify(tmp_path)


def test_load_and_verify_missing_referenced_binary(tmp_path: Path) -> None:
    """Lock references a binary that does not exist."""
    _write_lock(tmp_path, blake3_hex="0" * 64, file_rel="tools/grammars/typescript.so")

    with pytest.raises(GrammarLoadRefused, match=r"missing binary"):
        load_and_verify(tmp_path)


def test_load_and_verify_malformed_yaml(tmp_path: Path) -> None:
    lock = tmp_path / "tools" / "grammars.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("schema_version: 1\n  bad: indentation: here", encoding="utf-8")

    with pytest.raises(GrammarLoadRefused, match=r"YAML parse"):
        load_and_verify(tmp_path)


def test_load_and_verify_schema_violation_extra_field(tmp_path: Path) -> None:
    """``extra='forbid'`` rejects unknown fields → schema invalid refusal."""
    _, digest = _write_pair(tmp_path, b"x")
    lock_path = tmp_path / "tools" / "grammars.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        "schema_version: 1\n"
        "grammars:\n"
        "  - language: typescript\n"
        '    version: "0.20.6"\n'
        "    file: tools/grammars/typescript.so\n"
        f"    blake3: {digest}\n"
        "    rogue_field: bad\n",
        encoding="utf-8",
    )

    with pytest.raises(GrammarLoadRefused, match=r"schema invalid"):
        load_and_verify(tmp_path)


def test_grammar_pin_rejects_bad_blake3_shape() -> None:
    with pytest.raises(ValidationError):
        GrammarPin(language="typescript", version="0.20.6", file="x.so", blake3="not-hex")


def test_grammar_pin_rejects_bad_language() -> None:
    with pytest.raises(ValidationError):
        GrammarPin(language="TYPESCRIPT", version="0.20.6", file="x.so", blake3="0" * 64)


def test_grammar_lock_file_rejects_schema_v2() -> None:
    with pytest.raises(ValidationError):
        GrammarLockFile(schema_version=2, grammars=[])  # type: ignore[arg-type]
