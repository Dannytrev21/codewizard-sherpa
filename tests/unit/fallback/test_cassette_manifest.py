"""Phase-4 S3-05 — unit tests for ``cassettes.lock`` manifest module.

Covers AC-1/AC-2/AC-3/AC-17/AC-20/AC-21/AC-22 of the story. Layered
control: BLAKE3 chokepoint discipline (AC-20), `LockfileMalformedDetail`
parametrized rejection paths (AC-3), empty-bootstrap and sorted-output
invariants (AC-1/AC-22), and the bad-relpath defense against any future
walker that resolves a lock entry outside `tests/cassettes/anthropic/`
(AC-21).
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from codegenie.fallback.cassette.manifest import (
    _WARNING_IDS,
    LockfileMalformed,
    LockfileMalformedDetail,
    compute_cassette_digest,
    load_lockfile,
    rebuild_lockfile,
)

# --- AC-2 + AC-20: BLAKE3 routed through codegenie.hashing ----------------


def test_compute_digest_returns_unprefixed_64_lower_hex(tmp_path: Path) -> None:
    """The lock-file format stores unprefixed 64-hex (ADR-0014 line shape)."""
    p = tmp_path / "c.yaml"
    p.write_bytes(b"interactions: []\n")
    digest = compute_cassette_digest(p)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(ch in "0123456789abcdef" for ch in digest)
    assert not digest.startswith("blake3:")


def test_compute_digest_is_deterministic(tmp_path: Path) -> None:
    """Same bytes → same digest, repeated invocations."""
    p = tmp_path / "c.yaml"
    p.write_bytes(b"interactions: []\n")
    assert compute_cassette_digest(p) == compute_cassette_digest(p)


def test_compute_digest_changes_on_byte_diff(tmp_path: Path) -> None:
    """One byte differs → digest differs."""
    p1 = tmp_path / "c1.yaml"
    p1.write_bytes(b"interactions: []\n")
    p2 = tmp_path / "c2.yaml"
    p2.write_bytes(b"interactions: [{}]\n")
    assert compute_cassette_digest(p1) != compute_cassette_digest(p2)


# --- AC-2: load_lockfile shape --------------------------------------------


def test_load_lockfile_parses_two_space_separator(tmp_path: Path) -> None:
    """Per ADR-0014 line format: `<relpath>  <blake3-hex>` (two spaces)."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text("a.yaml  " + "0" * 64 + "\nb.yaml  " + "1" * 64 + "\n")
    parsed = load_lockfile(lf)
    assert parsed == {"a.yaml": "0" * 64, "b.yaml": "1" * 64}


def test_load_lockfile_returns_immutable_mapping(tmp_path: Path) -> None:
    """The returned mapping must be a MappingProxyType (defensive immutability)."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text("a.yaml  " + "0" * 64 + "\n")
    parsed = load_lockfile(lf)
    assert isinstance(parsed, MappingProxyType)
    with pytest.raises(TypeError):
        parsed["c.yaml"] = "2" * 64  # type: ignore[index]


def test_load_lockfile_missing_file_raises_malformed(tmp_path: Path) -> None:
    """AC-2 + AC-8 — missing file is a `missing_lockfile` reason."""
    lf = tmp_path / "does_not_exist.lock"
    with pytest.raises(LockfileMalformed) as exc:
        load_lockfile(lf)
    assert exc.value.reason == "missing_lockfile"
    assert exc.value.detail.reason == "missing_lockfile"


# --- AC-22: empty bootstrap ----------------------------------------------


def test_empty_lockfile_is_valid_bootstrap(tmp_path: Path) -> None:
    """Zero-cassette path: empty file parses to empty mapping; rebuild = ''."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text("")
    assert load_lockfile(lf) == {}
    assert rebuild_lockfile(tmp_path) == ""


def test_rebuild_empty_dir_returns_empty_string_even_when_yaml_files_absent(
    tmp_path: Path,
) -> None:
    """Empty dir → empty rebuild even if the parent is fresh-created."""
    fresh = tmp_path / "anthropic"
    fresh.mkdir()
    assert rebuild_lockfile(fresh) == ""


# --- AC-3 + AC-21: parametrized malformed cases ---------------------------


@pytest.mark.parametrize(
    "content,reason",
    [
        ("a.yaml " + "0" * 64 + "\n", "missing_separator"),  # one space
        ("a.yaml  " + "0" * 63 + "\n", "bad_hex_length"),
        ("a.yaml  " + "g" * 64 + "\n", "bad_hex_chars"),
        ("a.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "duplicate_relpath"),
        ("b.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "unsorted_lines"),
        ("a.yaml  " + "0" * 64 + "\n\n", "trailing_garbage"),
    ],
)
def test_load_lockfile_rejects_malformed(tmp_path: Path, content: str, reason: str) -> None:
    """Each malformed shape raises with the named `reason`. AC-3."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text(content)
    with pytest.raises(LockfileMalformed) as exc:
        load_lockfile(lf)
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "bad",
    [
        "/abs.yaml",
        "../escape.yaml",
        "nested/../escape.yaml",
        "nested\\windows.yaml",
        "",
    ],
)
def test_load_lockfile_rejects_unsafe_relpath(tmp_path: Path, bad: str) -> None:
    """AC-21 — defense against future walker resolving outside anthropic/."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text(f"{bad}  " + "0" * 64 + "\n")
    with pytest.raises(LockfileMalformed) as exc:
        load_lockfile(lf)
    assert exc.value.reason == "bad_relpath"


def test_lockfile_malformed_detail_is_frozen() -> None:
    """The detail model is frozen-extra-forbid (Pydantic v2 convention)."""
    detail = LockfileMalformedDetail(
        reason="bad_hex_chars",
        line_number=1,
        line_content="a.yaml  zzzz",
    )
    with pytest.raises(ValidationError):
        detail.line_number = 99  # type: ignore[misc]


def test_lockfile_malformed_carries_detail_and_props(tmp_path: Path) -> None:
    """AC-3 — raised wrapper exposes .reason / .line_number / .line_content."""
    lf = tmp_path / "cassettes.lock"
    lf.write_text("a.yaml  " + "g" * 64 + "\n")
    with pytest.raises(LockfileMalformed) as exc:
        load_lockfile(lf)
    assert exc.value.reason == "bad_hex_chars"
    assert exc.value.line_number == 1
    assert "g" * 64 in exc.value.line_content


def test_basemodel_is_not_directly_raiseable() -> None:
    """`LockfileMalformedDetail` is a BaseModel, not an Exception."""
    detail = LockfileMalformedDetail(
        reason="missing_separator", line_number=1, line_content="a.yaml"
    )
    assert not isinstance(detail, Exception)


# --- AC-1: rebuild output shape -------------------------------------------


def test_rebuild_lockfile_is_sorted_and_terminated(tmp_path: Path) -> None:
    """Lines sorted; non-empty output ends with a trailing newline."""
    (tmp_path / "b.yaml").write_bytes(b"x")
    (tmp_path / "a.yaml").write_bytes(b"y")
    out = rebuild_lockfile(tmp_path)
    lines = out.splitlines(keepends=True)
    assert len(lines) == 2
    assert lines[0].startswith("a.yaml  ")
    assert lines[1].startswith("b.yaml  ")
    assert out.endswith("\n")


def test_rebuild_lockfile_uses_two_space_separator(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_bytes(b"x")
    out = rebuild_lockfile(tmp_path)
    # The relpath ends with `.yaml`, then exactly two spaces, then 64 hex.
    relpath, sep, rest = out.partition("  ")
    assert relpath == "a.yaml"
    assert sep == "  "
    assert len(rest.rstrip("\n")) == 64


def test_rebuild_lockfile_walks_subdirectories(tmp_path: Path) -> None:
    """`rglob` semantics: cassettes nested under subdirs are included."""
    (tmp_path / "top.yaml").write_bytes(b"a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.yaml").write_bytes(b"b")
    out = rebuild_lockfile(tmp_path)
    assert "top.yaml" in out
    assert "sub/nested.yaml" in out


def test_rebuild_lockfile_emits_posix_relpaths(tmp_path: Path) -> None:
    """Relpaths use POSIX separators on every OS (the lock is committed)."""
    sub = tmp_path / "a"
    sub.mkdir()
    (sub / "b.yaml").write_bytes(b"x")
    out = rebuild_lockfile(tmp_path)
    assert "a/b.yaml" in out
    assert "a\\b.yaml" not in out


# --- AC-20: hash chokepoint ----------------------------------------------


def test_manifest_uses_hashing_chokepoint_not_direct_blake3() -> None:
    """Source-scan: no `import blake3`; calls `content_hash(`. AC-20."""
    src = Path("src/codegenie/fallback/cassette/manifest.py").read_text(encoding="utf-8")
    assert "from blake3" not in src
    assert "import blake3" not in src
    assert "content_hash(" in src


# --- AC-17: warning IDs ---------------------------------------------------


def test_warning_ids_exact_set() -> None:
    """AC-17 — four distinct error IDs the scanner emits."""
    assert _WARNING_IDS == frozenset(
        {
            "cassette.lock_malformed",
            "cassette.lock_drift",
            "cassette.lock_orphan",
            "cassette.lock_stale",
        }
    )
