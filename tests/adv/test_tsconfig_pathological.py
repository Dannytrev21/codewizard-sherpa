"""Adversarial: pathological ``tsconfig.json`` defenses across three
mutation-distinct sub-cases plus a gather-level silent-swallow observable.

Each sub-case pins one invariant in isolation so a regression that drops
one defense surfaces deterministically:

- Sub-case A (AC-9): nested block comments + unterminated string →
  ``jsonc.load`` raises :class:`MalformedJSONError` in O(n) wall-clock.
  Stripper state-machine regression (S1-04).
- Sub-case B (AC-10): circular ``extends`` → ``_walk_extends`` emits
  ``tsconfig.extends_cycle`` and preserves the first level's
  ``compilerOptions`` per the "deepest-reached config" semantic.
  Cycle-detection regression (S2-02).
- Sub-case C (AC-11): linear depth-exceeded chain → ``_walk_extends``
  emits ``tsconfig.extends_depth_exceeded``. Depth-cap regression (S2-02).
- Sub-case A gather-level (AC-12): the whole gather completes; the
  pathological body silently-swallows in ``_walk_extends`` (per
  ``node_build_system.py:421``); no spurious tsconfig ID surfaces.

Splitting a single combined-vector fixture (nested-blocks + cycle + depth)
into three would mask any single regression; the split is the mutation
resistance gain.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from codegenie.errors import MalformedJSONError
from codegenie.parsers import jsonc
from codegenie.probes.node_build_system import _walk_extends
from tests.adv._helpers import invoke_gather

# --- helpers ----------------------------------------------------------------


def _build_extends_chain(root: Path, *, depth: int) -> Path:
    """Write ``depth + 1`` linked tsconfig files; return the head path.

    Chain: ``tsconfig.json → t1.json → ... → t<depth>.json``. The terminal
    file omits ``extends`` so the chain is non-cyclic; ``depth=5`` exceeds
    the ``_TSCONFIG_EXTENDS_MAX_DEPTH=4`` cap.
    """
    names = ["tsconfig.json"] + [f"t{i}.json" for i in range(1, depth + 1)]
    for i, name in enumerate(names[:-1]):
        nxt = names[i + 1]
        (root / name).write_text(f'{{"extends": "./{nxt}"}}', encoding="utf-8")
    (root / names[-1]).write_text("{}", encoding="utf-8")
    return root / names[0]


# --- Sub-case A — nested blocks + unterminated string -----------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_jsonc_load_nested_blocks_plus_unterminated_string_raises_under_one_second(
    tmp_path: Path,
) -> None:
    """AC-9 — ``jsonc.load`` raises :class:`MalformedJSONError` with the
    ``"unterminated string"`` marker in O(n) wall-clock.

    The ``match="unterminated string"`` is mutation-resistant against a
    regression where the stripper falls through to ``json.loads`` and the
    error carries a generic ``JSONDecodeError`` message instead.
    """
    body = (
        (b"/*" * 100) + (b"*/" * 100) + b'\n{ "extends": "./other.json", "compilerOptions": { "out'
    )
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_bytes(body)

    t0 = time.monotonic()
    with pytest.raises(MalformedJSONError, match="unterminated string"):
        jsonc.load(tsconfig, max_bytes=1_000_000)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"jsonc.load took {elapsed:.2f}s on pathological tsconfig"


# --- Sub-case B — circular extends ------------------------------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_walk_extends_detects_cycle_under_one_second(tmp_path: Path) -> None:
    """AC-10 — ``_walk_extends`` emits ``tsconfig.extends_cycle`` and
    preserves the first level's ``compilerOptions`` before the cycle fires.

    The "deepest-reached config" semantic is part of S2-02's contract:
    even when the chain ends in a cycle, the configurations resolved
    *before* the cycle remain observable.
    """
    (tmp_path / "tsconfig.json").write_text(
        '{"extends": "./tsconfig.cycle.json", "compilerOptions": {"strict": true}}',
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.cycle.json").write_text(
        '{"extends": "./tsconfig.json"}',
        encoding="utf-8",
    )

    t0 = time.monotonic()
    deepest, warnings = _walk_extends(tmp_path / "tsconfig.json", tmp_path)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.5, f"_walk_extends took {elapsed:.2f}s on cyclic chain"
    assert "tsconfig.extends_cycle" in warnings, warnings
    assert deepest == {"strict": True}, deepest


# --- Sub-case C — depth-exceeded linear chain -------------------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_walk_extends_emits_depth_exceeded_on_six_level_chain(tmp_path: Path) -> None:
    """AC-11 — ``_walk_extends`` emits ``tsconfig.extends_depth_exceeded``
    on a linear chain whose depth exceeds the cap (5 > 4).

    Closed-world: ``tsconfig.extends_cycle`` MUST NOT also fire — a
    regression that conflates cycle and depth-exceeded would surface as
    a spurious ``tsconfig.extends_cycle`` warning.
    """
    head = _build_extends_chain(tmp_path, depth=5)
    _deepest, warnings = _walk_extends(head, tmp_path)
    assert "tsconfig.extends_depth_exceeded" in warnings, warnings
    assert "tsconfig.extends_cycle" not in warnings, warnings


# --- Sub-case A gather-level — silent-swallow + closed-world ID absence -----


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds(
    tmp_path: Path,
) -> None:
    """AC-12 — end-to-end gather under Sub-case A's body silently swallows
    the ``MalformedJSONError`` in ``_walk_extends`` (per
    ``node_build_system.py:421``); ``typescript.resolved_compiler_options``
    stays empty; no spurious tsconfig ID surfaces.

    The 2 s wall-clock bound catches a regression where the pathological
    body forces ``jsonc.load`` into a non-terminating path.
    """
    body = (b"/*" * 100) + (b"*/" * 100) + b'\n{ "compilerOptions": { "out'
    (tmp_path / "tsconfig.json").write_bytes(body)
    (tmp_path / "package.json").write_text('{"name":"x","version":"0.0.0"}', encoding="utf-8")

    t0 = time.monotonic()
    result = invoke_gather(tmp_path)
    elapsed = time.monotonic() - t0

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert elapsed < 2.0, f"gather took {elapsed:.2f}s on pathological tsconfig"

    # Envelope shape: ``probes.node_build_system.build_system.*`` — the probe
    # wraps its slice under its own slice key ``"build_system"``. Story AC
    # text dropped the inner wrap; navigate the shipped envelope (Rule 11).
    bs = result.context["probes"]["node_build_system"]["build_system"]
    ts = bs["typescript"]
    # Sub-case A's body trips ``jsonc.load`` on the FIRST file (the head
    # itself is malformed). ``_walk_extends`` breaks before resolving any
    # ``compilerOptions``; the silent-swallow contract leaves the resolved
    # map empty even though ``compiler_options_path`` is still the head's
    # repo-relative path. The closed-world ID-absence below pins that no
    # tsconfig ID surfaces despite the parser failure.
    assert ts["resolved_compiler_options"] == {}, ts["resolved_compiler_options"]
    # Closed-world: silent swallow means NO tsconfig ID surfaces in
    # warnings or errors.
    bs_warnings = bs.get("warnings", [])
    bs_errors = bs.get("errors", [])
    assert "tsconfig.extends_cycle" not in bs_warnings, bs_warnings
    assert "tsconfig.extends_depth_exceeded" not in bs_warnings, bs_warnings
    assert "tsconfig.depth_cap_exceeded" not in bs_errors, bs_errors
