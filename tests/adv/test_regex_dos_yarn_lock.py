"""Adversarial: the hand-rolled yarn-lock scanner must not regex-DoS.

Two complementary tests pin ADR-0003 §Decision ("no regex over the full
body; line-by-line state machine"):

1. **Runtime budget** (AC-1, AC-2) — a ~5 MB synthetic ``yarn.lock`` of
   multi-spec headers (the only string-allocation surface in
   ``_parse_handrolled``, via ``_dequote_entry_header``'s
   ``split('", "')`` call at ``_yarn.py:110``) parses in under 2 s. A
   regex-backtracking regression on multi-spec headers worst-cases
   quadratically against this body. The shape contract additionally
   forbids a silent-empty mutation that early-returns ``{"entries": {}}``
   on any large input.
2. **Structural** (AC-3) — an ``ast.parse``-driven walker asserts that
   ``codegenie.probes._lockfiles._yarn`` neither imports ``re`` nor
   references any ``re.<func>`` call. The deterministic complement to
   the wall-clock budget — catches a regex regression even if the
   introduced regex happens to be linear-time on the specific input.

The runtime test forces the hand-rolled path by setting
``_HAS_PYARN = False`` via ``monkeypatch.setattr(..., raising=True)``,
guarded by a ``hasattr(...)`` pre-assert so a future rename of the
flag surfaces loudly instead of silently no-op'ing the patch on a
contributor's machine where ``pyarn`` is installed.

Traces to:
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Adversarial tests" item #9.
- ``docs/phases/01-context-gather-layer-a-node/High-level-impl.md``
  §"Implementation-level risks" item 4 (regex-DoS-prone scanner).
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md``
  §Decision — "no regex over the full file".
- ``_yarn.py:115-169`` — ``_parse_handrolled``.
"""

from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path

import pytest

import codegenie.probes._lockfiles._yarn as _yarn
from codegenie.errors import MalformedLockfileError


def _pathological_yarn_lock(approx_bytes: int = 5_000_000) -> bytes:
    """Functional-core fixture builder.

    Repeats a multi-spec entry header with a single ``version`` line
    until the encoded body reaches ``approx_bytes``. The multi-spec
    header is the only string-allocation surface in the hand-rolled
    scanner; an O(n²) backtracking regression on this path would worst-
    case quadratically against the body, while the linear state machine
    handles it in O(bytes).
    """
    block_template = '"foo@^1.0.{i}", "foo@^2.0.{i}":\n  version "1.0.0"\n'
    one_size = len(block_template.format(i=0).encode("utf-8"))
    n = approx_bytes // one_size + 1
    return "".join(block_template.format(i=i) for i in range(n)).encode("utf-8")


@pytest.mark.adv
def test_yarn_pathological_input_under_runtime_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins AC-1 + AC-2 — ~5 MB body parses in < 2 s on the hand-rolled path
    and shape is non-empty (or ``MalformedLockfileError``); the silent-empty
    path is forbidden.

    Catches:
      - a hand-rolled-scanner regression that introduces a regex with
        backtracking (worst-cases quadratically against the multi-spec
        header body).
      - a regression that early-returns ``{"entries": {}}`` on any large
        input (would beat the wall-clock budget trivially without
        actually parsing).
    """
    assert hasattr(_yarn, "_HAS_PYARN"), (
        "_HAS_PYARN attribute was renamed — monkeypatch below is now a "
        "no-op; update this test to the new attribute name (or surface "
        "the rename loudly)."
    )
    monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False, raising=True)
    path = tmp_path / "yarn.lock"
    path.write_bytes(_pathological_yarn_lock(approx_bytes=5_000_000))

    t0 = time.monotonic()
    result: dict[str, object] | None
    try:
        result = _yarn.parse(path)  # type: ignore[assignment]
    except MalformedLockfileError:
        result = None
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0, (
        f"hand-rolled scanner took {elapsed:.2f}s on ~5 MB body — "
        "suggests O(n²) work or a regex with backtracking (ADR-0003 §Decision)"
    )
    if result is not None:
        assert isinstance(result, dict), result
        assert "entries" in result, result
        assert len(result["entries"]) > 0, (
            "scanner returned {'entries': {}} on a non-empty body — "
            "this is the explicit-forbidden silent-empty mutation (AC-2)"
        )


def _references_re(func_def: ast.FunctionDef) -> str | None:
    """Walk ``func_def``; return the first ``re.<attr>`` reference or ``None``.

    Treats ``re.match``/``re.search``/``re.findall``/``re.finditer``/
    ``re.compile``/``re.sub``/``re.split`` as the forbidden surface.
    """
    forbidden = {"match", "search", "findall", "finditer", "compile", "sub", "split"}
    for node in ast.walk(func_def):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "re"
            and node.attr in forbidden
        ):
            return f"re.{node.attr}"
    return None


@pytest.mark.adv
def test_yarn_handrolled_scanner_uses_no_regex() -> None:
    """Pins AC-3 — ``_yarn`` module imports no ``re``, and the hand-rolled
    scanner / helpers invoke no ``re.<func>`` call.

    The deterministic complement to the wall-clock budget in
    :func:`test_yarn_pathological_input_under_runtime_budget` — catches
    a regex-backtracking regression structurally even if the introduced
    regex happens to be linear-time on the specific test fixture
    (CLAUDE.md "Determinism over probabilism").
    """
    src = inspect.getsource(_yarn)
    tree = ast.parse(src)

    # Module-level import guard.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "re", (
                    "_yarn must remain a line-by-line state machine; "
                    "no regex over the full body (ADR-0003)"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "re", (
                "_yarn must remain a line-by-line state machine; "
                "no regex over the full body (ADR-0003)"
            )

    # Function-body guard: _parse_handrolled and any helper it might gain
    # must not reference re.<func>.
    target_funcs = {"_parse_handrolled", "_dequote_entry_header", "_pyarn_parse", "parse"}
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in target_funcs:
            seen.add(node.name)
            offender = _references_re(node)
            assert offender is None, (
                f"_yarn.{node.name} references {offender} — forbidden by "
                "ADR-0003 (state-machine only)"
            )

    # Sanity: at least _parse_handrolled and _dequote_entry_header must exist;
    # otherwise the structural assertion above ran against zero functions.
    assert {"_parse_handrolled", "_dequote_entry_header"}.issubset(seen), (
        f"expected hand-rolled scanner functions in _yarn; found {seen!r}"
    )
