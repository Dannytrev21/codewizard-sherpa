"""Tests for ``codegenie.hashing`` — the BLAKE3 + SHA-256 chokepoint (ADR-0001).

Three tiers — anchor (public-surface + prefix contract + lazy import),
mutation-killer (known-vector pins, distinguishability, separator collision,
sort stability across permutations, manifest-vs-content semantics, chunk
boundary), and edge cases (empty inputs, ``FileNotFoundError`` propagation).
"""

from __future__ import annotations

import hashlib
import itertools
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Tier 1 — anchor tests (AC-1..AC-3 public surface + prefix contract)
# ---------------------------------------------------------------------------


def test_module_all_closure_is_exactly_six_public_functions() -> None:
    """AC-1 (S2-03) + AC-13 (S3-01) + AC-25 (S2-01): ``__all__`` pins the
    public surface — three original helpers, two byte-hash extensions from
    S3-01, plus :func:`content_hash_fd` (the fd-based streaming chokepoint
    added in S2-01 for the SkillsLoader progressive-disclosure invariant)."""
    import codegenie.hashing as h

    assert set(h.__all__) == {
        "content_hash",
        "content_hash_bytes",
        "content_hash_fd",
        "content_hash_of_inputs",
        "identity_hash",
        "identity_hash_bytes",
    }


def test_content_hash_matches_prefix_regex_and_is_deterministic(
    tmp_path: Path,
) -> None:
    """AC-2 + determinism part of Goal."""
    from codegenie.hashing import content_hash

    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world\n")
    h1, h2 = content_hash(f), content_hash(f)
    assert h1 == h2
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", h1)


def test_identity_hash_matches_prefix_regex_and_is_deterministic() -> None:
    """AC-2 + determinism part of Goal."""
    from codegenie.hashing import identity_hash

    parts = ("language_detection", "1.0", "v0.1.0", "blake3:deadbeef")
    h1, h2 = identity_hash(*parts), identity_hash(*parts)
    assert h1 == h2
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", h1)


def test_content_hash_of_inputs_matches_prefix_regex(tmp_path: Path) -> None:
    """AC-2 — third public function's return shape is pinned too."""
    from codegenie.hashing import content_hash_of_inputs

    p = tmp_path / "x"
    p.write_bytes(b"y")
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", content_hash_of_inputs([p]))


def test_hex_digests_are_lowercase() -> None:
    """AC-2 — kills a ``hexdigest().upper()`` "improvement"."""
    from codegenie.hashing import content_hash_of_inputs, identity_hash

    digest = identity_hash("x").removeprefix("sha256:")
    assert digest == digest.lower()
    blake_digest = content_hash_of_inputs([]).removeprefix("blake3:")
    assert blake_digest == blake_digest.lower()


# ---------------------------------------------------------------------------
# Tier 1 — anchor tests (AC-3 + AC-4 lazy import — both halves)
# ---------------------------------------------------------------------------


def test_blake3_lazy_import_isolated_in_fresh_interpreter() -> None:
    """AC-3 + AC-4: in a fresh interpreter, importing ``codegenie.hashing``
    must NOT load ``blake3``, but calling ``content_hash`` must. Subprocess
    isolates from any ``blake3`` already loaded into this pytest session."""
    code = textwrap.dedent(
        """
        import sys, tempfile, pathlib
        assert "blake3" not in sys.modules
        import codegenie.hashing as h
        assert "blake3" not in sys.modules, "import-time leakage of blake3"
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(b"x"); tmp.flush()
            h.content_hash(pathlib.Path(tmp.name))
        assert "blake3" in sys.modules, "call-time lazy import did not fire"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_content_hash_of_inputs_also_lazy_imports_blake3(tmp_path: Path) -> None:
    """AC-3: ``content_hash_of_inputs`` is a peer public function that uses
    BLAKE3 — must lazy-import too. Fresh subprocess proves the import is
    gated on the function call, not the module import."""
    f = tmp_path / "f"
    f.write_bytes(b"")
    code = textwrap.dedent(
        f"""
        import sys, pathlib
        import codegenie.hashing as h
        assert "blake3" not in sys.modules
        h.content_hash_of_inputs([pathlib.Path({str(f)!r})])
        assert "blake3" in sys.modules
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


# ---------------------------------------------------------------------------
# Tier 2 — mutation-killers (known vectors, distinguishability, separator)
# ---------------------------------------------------------------------------


def test_content_hash_matches_blake3_library_known_vector(tmp_path: Path) -> None:
    """AC-9: kills a ``return blake3:0000...`` stub mutant. Test imports
    ``blake3`` directly — that's legal because ``tests/`` is outside the
    chokepoint scope."""
    from blake3 import blake3 as _blake3

    from codegenie.hashing import content_hash

    f = tmp_path / "f"
    payload = b"abc"
    f.write_bytes(payload)
    expected = f"blake3:{_blake3(payload).hexdigest()}"
    assert content_hash(f) == expected


def test_identity_hash_matches_sha256_with_unit_separator_known_vector() -> None:
    """AC-9 + AC-7: pins prefix, algorithm, AND the ``\\x1f`` separator at one
    shot. A mutant using ``|`` as separator fails. A mutant returning
    ``sha256:00..00`` fails. The arity-witness byte prefix is part of the
    implementation's distinctness scheme (see AC-11); this test pins the
    canonical 3-arg vector with arity byte ``\\x03``."""
    from codegenie.hashing import identity_hash

    expected_digest = hashlib.sha256(b"\x03" + b"a\x1fb\x1fc").hexdigest()
    assert identity_hash("a", "b", "c") == f"sha256:{expected_digest}"


def test_content_hash_distinguishes_different_files(tmp_path: Path) -> None:
    """AC-8: kills a ``always return same hex`` mutant."""
    from codegenie.hashing import content_hash

    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"alpha")
    b.write_bytes(b"beta!")  # same size as "alpha"
    assert content_hash(a) != content_hash(b)


def test_identity_hash_is_order_sensitive_and_distinguishes_parts() -> None:
    """AC-8."""
    from codegenie.hashing import identity_hash

    assert identity_hash("a", "b") != identity_hash("a", "c")
    assert identity_hash("a", "b") != identity_hash("b", "a")


def test_identity_hash_resists_separator_collision_attacks() -> None:
    """AC-7: boundary-shift attack — distinct part-tuples that would collide
    under a naive ``'|'.join`` must NOT collide under the chosen separator."""
    from codegenie.hashing import identity_hash

    assert identity_hash("ab", "c") != identity_hash("a", "bc")
    assert identity_hash("a", "", "b") != identity_hash("a", "b")


# ---------------------------------------------------------------------------
# Tier 2 — content_hash_of_inputs: sort-stability + manifest semantics
# ---------------------------------------------------------------------------


def test_content_hash_of_inputs_is_sort_stable_distinct_names_distinct_sizes(
    tmp_path: Path,
) -> None:
    """AC-5 (a) — two-element swap with distinct names and distinct sizes."""
    from codegenie.hashing import content_hash_of_inputs

    p1, p2 = tmp_path / "a.txt", tmp_path / "b.txt"
    p1.write_bytes(b"alpha")  # size 5
    p2.write_bytes(b"beta")  # size 4
    assert content_hash_of_inputs([p1, p2]) == content_hash_of_inputs([p2, p1])


def test_content_hash_of_inputs_sort_stable_with_equal_sizes(
    tmp_path: Path,
) -> None:
    """AC-5 (b) — kills a ``sort by size only`` mutant."""
    from codegenie.hashing import content_hash_of_inputs

    p1, p2 = tmp_path / "z.txt", tmp_path / "a.txt"
    p1.write_bytes(b"xxxxx")  # size 5
    p2.write_bytes(b"yyyyy")  # size 5 (same!)
    assert content_hash_of_inputs([p1, p2]) == content_hash_of_inputs([p2, p1])


def test_content_hash_of_inputs_sort_stable_three_element_permutation(
    tmp_path: Path,
) -> None:
    """AC-5 (c) — kills a ``swap once then stable`` mutant."""
    from codegenie.hashing import content_hash_of_inputs

    paths: list[Path] = []
    for name, payload in (("a", b"1"), ("b", b"22"), ("c", b"333")):
        f = tmp_path / name
        f.write_bytes(payload)
        paths.append(f)
    baseline = content_hash_of_inputs(paths)
    for perm in itertools.permutations(paths):
        assert content_hash_of_inputs(list(perm)) == baseline


def test_content_hash_of_inputs_hashes_manifest_not_bytes(tmp_path: Path) -> None:
    """AC-6: same ``(path, size)``, different bytes → SAME hash. The function
    hashes a manifest of inputs, not their contents."""
    from codegenie.hashing import content_hash_of_inputs

    p = tmp_path / "a.txt"
    p.write_bytes(b"first")  # 5 bytes
    h1 = content_hash_of_inputs([p])
    p.write_bytes(b"OTHER")  # 5 bytes, different content
    h2 = content_hash_of_inputs([p])
    assert h1 == h2, "content_hash_of_inputs hashes (path,size) manifest, not bytes"


def test_content_hash_of_inputs_changes_with_size(tmp_path: Path) -> None:
    """AC-6 sibling — size IS part of the manifest; changing size MUST change
    the hash."""
    from codegenie.hashing import content_hash_of_inputs

    p = tmp_path / "a.txt"
    p.write_bytes(b"short")
    h1 = content_hash_of_inputs([p])
    p.write_bytes(b"a longer payload")
    assert content_hash_of_inputs([p]) != h1


# ---------------------------------------------------------------------------
# Tier 2 — content_hash streaming across chunk boundaries
# ---------------------------------------------------------------------------


def test_content_hash_streams_files_spanning_chunk_boundary(
    tmp_path: Path,
) -> None:
    """AC-10: file > 64 KB chunk size must hash correctly."""
    from blake3 import blake3 as _blake3

    from codegenie.hashing import content_hash

    payload = (b"x" * 100_000) + (b"y" * 100_000)  # ≈ 3 chunks
    p = tmp_path / "big"
    p.write_bytes(payload)
    assert content_hash(p) == f"blake3:{_blake3(payload).hexdigest()}"


# ---------------------------------------------------------------------------
# Tier 3 — edge cases
# ---------------------------------------------------------------------------


def test_content_hash_of_inputs_empty_list_is_legal_and_deterministic() -> None:
    """AC-11: empty manifest is a valid input; returns a deterministic
    prefix-tagged hash."""
    from codegenie.hashing import content_hash_of_inputs

    h = content_hash_of_inputs([])
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", h)
    assert content_hash_of_inputs([]) == h


def test_content_hash_of_inputs_empty_list_distinct_from_empty_file(
    tmp_path: Path,
) -> None:
    """AC-11: empty manifest must NOT collide with a real-but-empty file's
    manifest. The path string is part of the manifest, so a real path
    always changes the hash."""
    from codegenie.hashing import content_hash_of_inputs

    empty_file = tmp_path / "empty"
    empty_file.write_bytes(b"")
    assert content_hash_of_inputs([]) != content_hash_of_inputs([empty_file])


def test_identity_hash_zero_parts_distinct_from_one_empty_part() -> None:
    """AC-11: ``identity_hash()`` and ``identity_hash("")`` must NOT collide
    — both are legitimate compositions of the cache-key tuple and silently
    collapsing them would change cache identity."""
    from codegenie.hashing import identity_hash

    assert identity_hash() != identity_hash("")


def test_content_hash_of_inputs_propagates_filenotfounderror(
    tmp_path: Path,
) -> None:
    """AC-12: missing path → ``FileNotFoundError``, uncaught."""
    from codegenie.hashing import content_hash_of_inputs

    with pytest.raises(FileNotFoundError):
        content_hash_of_inputs([tmp_path / "does-not-exist"])


# ---------------------------------------------------------------------------
# S3-01 AC-13 — byte-hash chokepoint extension
# ---------------------------------------------------------------------------


def test_byte_helpers_listed_in_module_all() -> None:
    """S3-01 AC-13: ``__all__`` advertises the two byte-hash helpers
    alongside the original three functions."""
    import codegenie.hashing as h

    assert "content_hash_bytes" in h.__all__
    assert "identity_hash_bytes" in h.__all__


def test_content_hash_bytes_matches_content_hash_over_same_bytes(
    tmp_path: Path,
) -> None:
    """S3-01 AC-13 parity: ``content_hash_bytes(p.read_bytes()) ==
    content_hash(p)`` for any ``p``. This is the load-bearing equivalence-
    class assertion guaranteeing the cache store can use the bytes-flavored
    helper without drifting the on-disk filename relative to a streaming
    re-hash of the same content."""
    from codegenie.hashing import content_hash, content_hash_bytes

    p = tmp_path / "blob"
    payload = b"some serialized probe output"
    p.write_bytes(payload)
    assert content_hash_bytes(payload) == content_hash(p)


def test_content_hash_bytes_prefix_and_determinism() -> None:
    """Shape: ``blake3:<64-hex>`` and deterministic for identical bytes."""
    from codegenie.hashing import content_hash_bytes

    h1 = content_hash_bytes(b"x")
    h2 = content_hash_bytes(b"x")
    assert h1 == h2
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", h1)
    assert content_hash_bytes(b"y") != h1


def test_identity_hash_bytes_matches_hashlib_known_vector() -> None:
    """S3-01 AC-13: ``identity_hash_bytes(b)`` matches stdlib
    ``hashlib.sha256(b).hexdigest()`` — pins the algorithm in the
    chokepoint extension."""
    from codegenie.hashing import identity_hash_bytes

    payload = b"audit-anchor-bytes"
    expected = hashlib.sha256(payload).hexdigest()
    assert identity_hash_bytes(payload) == f"sha256:{expected}"


def test_identity_hash_bytes_prefix_and_lowercase() -> None:
    """Shape: ``sha256:<64-hex>`` and digest is lowercase (kills a
    ``hexdigest().upper()`` mutant)."""
    from codegenie.hashing import identity_hash_bytes

    h = identity_hash_bytes(b"")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", h)
    assert h == h.lower()


# ---------------------------------------------------------------------------
# S2-01 AC-25 — content_hash_fd parity + chokepoint extension
# ---------------------------------------------------------------------------


def test_content_hash_fd_matches_content_hash_bytes_over_same_span(
    tmp_path: Path,
) -> None:
    """S2-01 AC-25 parity: streaming fd hash equals one-shot bytes hash."""
    import os

    from codegenie.hashing import content_hash_bytes, content_hash_fd

    payload = b"---\nid: foo\n---\nthe-body-bytes\n"
    body_offset = payload.index(b"the")
    body = payload[body_offset:]
    p = tmp_path / "f"
    p.write_bytes(payload)
    fd = os.open(p, os.O_RDONLY)
    try:
        streaming = content_hash_fd(fd, offset=body_offset, size=len(body))
    finally:
        os.close(fd)
    assert streaming == content_hash_bytes(body)


def test_content_hash_fd_handles_span_larger_than_chunk(tmp_path: Path) -> None:
    """The 64 KiB chunk loop must keep parity across a multi-chunk span."""
    import os

    from codegenie.hashing import content_hash_bytes, content_hash_fd

    # 200 KiB of deterministic bytes — three full 64-KiB reads plus a tail.
    body = bytes((i * 31) & 0xFF for i in range(200 * 1024))
    p = tmp_path / "f"
    p.write_bytes(b"prefix" + body)
    fd = os.open(p, os.O_RDONLY)
    try:
        assert content_hash_fd(fd, offset=len(b"prefix"), size=len(body)) == (
            content_hash_bytes(body)
        )
    finally:
        os.close(fd)


def test_content_hash_fd_short_read_raises_oserror(tmp_path: Path) -> None:
    """Asking for more bytes than available raises ``OSError`` (fail-loud)."""
    import os

    import pytest

    from codegenie.hashing import content_hash_fd

    p = tmp_path / "f"
    p.write_bytes(b"abc")
    fd = os.open(p, os.O_RDONLY)
    try:
        with pytest.raises(OSError):
            content_hash_fd(fd, offset=0, size=100)
    finally:
        os.close(fd)
