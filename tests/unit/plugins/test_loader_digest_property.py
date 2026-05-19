"""S2-03 AC-10 — Hypothesis: tree-digest is walk-order invariant.

The pure :func:`codegenie.hashing.tree_digest_of_files` MUST produce the
same digest for any permutation of input ``(relpath, bytes)`` pairs, so
long as the loader sorts before hashing. The loader's
:func:`_collect_plugin_files` does that sort; this property test pins the
contract end-to-end via the higher-level
:func:`compute_plugin_tree_digest`.
"""

from __future__ import annotations

import random
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.hashing import tree_digest_of_files
from codegenie.plugins.loader import compute_plugin_tree_digest

_RELPATH = st.text(
    alphabet=st.characters(
        min_codepoint=ord("a"), max_codepoint=ord("z"), include_characters="0123456789_"
    ),
    min_size=1,
    max_size=12,
)
_BYTES = st.binary(min_size=0, max_size=64)
_PAIRS = st.lists(st.tuples(_RELPATH, _BYTES), min_size=1, max_size=5, unique_by=lambda p: p[0])


@given(_PAIRS)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_tree_digest_of_files_walk_order_invariance(pairs: list[tuple[str, bytes]]) -> None:
    """``tree_digest_of_files(sorted(pairs)) == tree_digest_of_files(sorted(perm))``.

    The function is order-DEPENDENT by design (records concatenate before
    hashing); the loader sorts pairs by relpath before invoking. This
    property exercises the post-sort invariance: for any permutation,
    sorting before hashing yields the same digest.
    """
    canonical = sorted(pairs, key=lambda p: p[0])
    rng = random.Random(0)
    shuffled = list(pairs)
    rng.shuffle(shuffled)
    re_sorted = sorted(shuffled, key=lambda p: p[0])
    assert tree_digest_of_files(canonical) == tree_digest_of_files(re_sorted)


@given(_PAIRS)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_compute_plugin_tree_digest_is_walk_order_invariant(
    pairs: list[tuple[str, bytes]],
) -> None:
    """End-to-end: building the same plugin tree twice (regardless of the
    order in which files are created) yields identical digests.

    Filesystem walk order is OS-dependent;
    :func:`compute_plugin_tree_digest` sorts before hashing so the digest
    is a pure function of (relpath, bytes) → 64-hex.
    """
    import tempfile  # noqa: PLC0415 — narrowly-scoped to this property test

    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        a = Path(t1) / "plugin"
        b = Path(t2) / "plugin"
        a.mkdir()
        b.mkdir()
        for relpath, body in pairs:
            (a / relpath).write_bytes(body)
        for relpath, body in reversed(pairs):
            (b / relpath).write_bytes(body)
        assert compute_plugin_tree_digest(a).unwrap() == compute_plugin_tree_digest(b).unwrap()
