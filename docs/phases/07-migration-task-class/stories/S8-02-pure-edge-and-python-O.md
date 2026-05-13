# Story S8-02 — `@pure_edge` and `python -O` extension to distroless edges

**Step:** Step 8 — Pre-flight final regression and snapshot-discipline rehearsal
**Status:** Ready
**Effort:** S
**Depends on:** S8-01
**ADRs honored:** ADR-P7-001, ADR-0009

## Context

Phase 6 shipped a `python -O` startup canary (`tests/graph/test_pep_no_O_optimizations.py`) that fails loudly when CPython is invoked with `-O`, because `-O` strips `assert` statements and `@pure_edge` decorator preconditions rely on assertions to enforce edge-function purity. Phase 7 added `route_after_resolve_target` (and any other `@pure_edge`-decorated edges in `src/codegenie/graph/edges.py` or `src/codegenie/graph/nodes/distroless/`). Those new edges inherit the same hazard but are not yet covered by the canary.

This story extends Phase 6's canary to cover every Phase 7 `@pure_edge` and adds a startup-time assertion that the interpreter is **not** running with `-O`. The work is small (an extension to one existing test plus a tiny startup-time check) but load-bearing — it closes edge case #15 in `phase-arch-design.md §Edge cases` and protects an invariant a single operator misconfiguration would otherwise silently break.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #15` — "Operator runs `python -O` (asserts stripped) → `@pure_edge` assertions silently skipped → hard error at CLI startup; documented in operator docs."
  - `../phase-arch-design.md §Testing strategy ›Property tests ›test_gate_predicates.py` — pattern for "label invariance under mutation of non-consumed fields" that `@pure_edge` predicates obey.
  - `../phase-arch-design.md §Component 13 — Phase-side seams` — confirms `route_after_resolve_target` is the *additive* edge predicate landed in `src/codegenie/graph/edges.py`; if S5-04 chose the alternative new-file path under `graph/edges_distroless.py`, scope changes accordingly.
  - `../phase-arch-design.md §Harness engineering ›Determinism vs probabilism` — every Phase 7 graph component except `replan_with_phase4` is deterministic; `@pure_edge` is the load-bearing decorator that enforces it.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — any *new* graph edge added under `graph/edges.py` must be one of the six ADR-gated seams (or strictly a new file).
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-0009 — extending the canary test does not touch the contract surface; this story should not regenerate `tools/contract-surface.snapshot.json`.
- **Existing code:**
  - `tests/graph/test_pep_no_O_optimizations.py` — Phase 6's canary; the file you extend. Read it in full first.
  - `src/codegenie/graph/edges.py` — find `@pure_edge`-decorated predicates introduced by Phase 7 (especially `route_after_resolve_target` per S5-04).
  - `src/codegenie/graph/nodes/distroless/` — scan for any `@pure_edge` on conditional routing helpers introduced by S5-02 / S5-03 / S5-04.
  - `src/codegenie/cli/migrate.py` — where the startup-time `-O` assertion belongs (parallel to Phase 6's `cli/loop.py`).
- **External docs:**
  - https://docs.python.org/3/using/cmdline.html#cmdoption-O — `-O` semantics; stdlib `sys.flags.optimize`.

## Goal

`tests/graph/test_pep_no_O_optimizations.py` parametrically covers every Phase 7 `@pure_edge` predicate, and `codegenie migrate --help` exits non-zero with a loud error when CPython was invoked with `-O` or `-OO`.

## Acceptance criteria

- [ ] `tests/graph/test_pep_no_O_optimizations.py` enumerates every `@pure_edge`-decorated callable under `src/codegenie/graph/` (Phase 6's existing list plus Phase 7's additions including `route_after_resolve_target`) via dynamic discovery — not a hand-edited list — so future `@pure_edge` additions are picked up automatically.
- [ ] For each discovered `@pure_edge`, the test asserts that the predicate's `assert` statements *fire* (verified by feeding a mutated-state input that would trip the assertion under normal Python and confirming an `AssertionError` is raised).
- [ ] A separate startup-time test invokes `python -O -m codegenie migrate --help` as a subprocess and asserts the process exits non-zero with stderr containing a documented message such as `codegenie cannot run under python -O: @pure_edge invariants require assertions`.
- [ ] `codegenie migrate` (and any other CLI entry) raises this loud error at module load time — before Click processes args — by checking `sys.flags.optimize` and `raise SystemExit(2)` with the documented message.
- [ ] Edge case #15 from `phase-arch-design.md §Edge cases` is referenced in the new test's docstring and in the CLI's startup-guard docstring.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` all pass on the touched files.

## Implementation outline

1. Write the failing red test that asserts dynamic-discovery returns ≥ 2 `@pure_edge` predicates (Phase 6 had ≥ 1; Phase 7 adds at least `route_after_resolve_target`) and that each predicate raises `AssertionError` under a mutated-state probe.
2. Extend `tests/graph/test_pep_no_O_optimizations.py` to use a dynamic-discovery walker: scan `src/codegenie/graph/` for functions whose `__wrapped__` chain or attribute marker (`_is_pure_edge = True`, whatever Phase 6 set) indicates `@pure_edge` decoration. Parametrize tests over the discovered list.
3. Write a subprocess test (`tests/graph/test_python_dash_O_startup_guard.py` or a sibling test in the same file) that invokes `python -O -m codegenie migrate --help`, asserts exit code != 0, and asserts the documented error message in stderr.
4. Add the startup-time guard to `src/codegenie/cli/migrate.py` (read Phase 6's `cli/loop.py` first — if it already has the guard, factor cleanly or duplicate per S5-05's "inlines its own shared options" precedent in ADR-0012). Use `sys.flags.optimize > 0 → SystemExit(2, "<documented message>")` at module import.
5. Refactor: ensure the dynamic discovery walker is unit-tested independently (a one-off `test_pure_edge_walker_finds_known_decorators`), so an empty discovery doesn't silently pass.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/graph/test_pep_no_O_optimizations.py` (extension) + a new subprocess test.

```python
# tests/graph/test_pep_no_O_optimizations.py — extension
"""Phase 6 canary, extended to cover Phase 7 @pure_edge predicates.

Closes phase-arch-design.md §Edge cases #15 — `python -O` strips `assert`
statements; @pure_edge invariants then silently no-op. Hard-fail at startup
and prove every @pure_edge predicate actually fires its assertions.
"""
import subprocess
import sys
from collections.abc import Callable

import pytest

from codegenie.graph import edges  # plus any edges_distroless module if S5-04 forked
# Dynamic discovery — walks every module under src/codegenie/graph/ and yields
# (qualname, callable) for every @pure_edge-decorated function. Implementation in
# tests/graph/_pure_edge_walker.py (new helper).
from tests.graph._pure_edge_walker import discover_pure_edges

PURE_EDGES: list[tuple[str, Callable[..., object]]] = list(discover_pure_edges())


def test_pure_edge_discovery_finds_phase7_additions() -> None:
    names = {qn for qn, _ in PURE_EDGES}
    # red: route_after_resolve_target was added in S5-04; the walker must find it.
    assert "codegenie.graph.edges.route_after_resolve_target" in names or \
           "codegenie.graph.edges_distroless.route_after_resolve_target" in names, \
        f"@pure_edge walker did not discover route_after_resolve_target; got: {sorted(names)}"
    # red: total count > Phase 6 baseline (>=1 phase6 + >=1 phase7).
    assert len(PURE_EDGES) >= 2, f"Expected ≥2 @pure_edge predicates; found {len(PURE_EDGES)}"


@pytest.mark.parametrize("qualname,fn", PURE_EDGES, ids=lambda v: v if isinstance(v, str) else repr(v))
def test_pure_edge_assertions_actually_fire(qualname: str, fn: Callable[..., object]) -> None:
    """Each @pure_edge predicate must raise AssertionError when fed a state that
    violates one of its `assert`s. Implementation feeds a deliberately mutated
    DistrolessLedger (or VulnLedger) with a known-bad field per the predicate's
    declared `assert` text — see _pure_edge_walker.synthesize_violating_state."""
    from tests.graph._pure_edge_walker import synthesize_violating_state
    bad_state = synthesize_violating_state(fn)
    with pytest.raises(AssertionError):
        fn(bad_state)


def test_codegenie_migrate_refuses_python_dash_O() -> None:
    """Startup-time guard: `python -O -m codegenie migrate --help` must exit non-zero
    with the documented error. Closes Edge case #15."""
    result = subprocess.run(
        [sys.executable, "-O", "-m", "codegenie", "migrate", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "codegenie migrate ran under python -O; @pure_edge invariants are silently stripped."
    assert "python -O" in result.stderr or "optimize" in result.stderr.lower(), \
        f"Startup guard error message did not mention -O / optimize: {result.stderr!r}"
```

Run it: expect `ModuleNotFoundError` on `_pure_edge_walker` or the discovery assert failing because the walker doesn't exist. Both are valid red. Commit.

### Green — make it pass

Implement the smallest version of each missing piece:
- `tests/graph/_pure_edge_walker.py` — `discover_pure_edges()` iterates modules under `src/codegenie/graph/`, yields `@pure_edge`-decorated callables; `synthesize_violating_state(fn)` reads the predicate's source (via `inspect.getsource`) or its declared marker attribute and crafts a state that trips one assertion.
- The startup-time guard in `src/codegenie/cli/migrate.py`: at module top, `if sys.flags.optimize > 0: raise SystemExit("codegenie cannot run under python -O: @pure_edge invariants require assertions to enforce edge-function purity. Re-run without -O.")`.

Resist building a parametric synthesis engine for `synthesize_violating_state` — a small registry mapping `qualname → bad_state_factory` is enough. Add registry entries for each `@pure_edge` Phase 7 added.

### Refactor — clean up

- Type-hint the walker's return type (`Iterator[tuple[str, Callable[..., object]]]`).
- Docstring on the startup guard referencing edge case #15.
- If `cli/loop.py` already implements an identical guard, follow ADR-0012's "inlines its own shared options, no shared dispatcher" precedent — duplicate, don't extract — but cross-reference both files in a comment.
- Add the docstring "Closes phase-arch-design.md §Edge cases #15" to the new test.
- Ensure no `pytest.importorskip` or `skip` markers crept in — this canary must not silently disable itself.

## Files to touch

| Path | Why |
|---|---|
| `tests/graph/test_pep_no_O_optimizations.py` | Extend with dynamic discovery + Phase 7 edges + subprocess guard test. |
| `tests/graph/_pure_edge_walker.py` | New helper — discovers `@pure_edge` callables; small per-predicate bad-state factory registry. |
| `src/codegenie/cli/migrate.py` | Add startup-time `sys.flags.optimize` guard at module top. |
| `docs/phases/07-migration-task-class/stories/S8-02-pure-edge-and-python-O.md` | Status update on completion. |

## Out of scope

- **Adding new `@pure_edge` predicates.** This story covers existing ones from S5-04 / earlier. New ones come with their own story.
- **Property tests for label invariance under non-consumed-field mutation.** S6-02 (`test_gate_predicates.py`) owns that pattern.
- **Editing `cli/loop.py`.** Phase 7 cannot edit Phase 6 sources per ADR-0001 (G19). If `cli/loop.py` lacks the same guard, file a Phase 6 follow-up story rather than fixing it here.
- **Documenting `-O` in operator docs.** Mentioned in edge case #15 as a follow-up; not in scope here.

## Notes for the implementer

- The dynamic-discovery walker is the load-bearing piece — if it silently returns an empty list, the parametric tests pass with zero parametrizations and the canary is useless. `test_pure_edge_discovery_finds_phase7_additions` explicitly guards against this by asserting `len >= 2` and naming `route_after_resolve_target`.
- Per S5-04, the implementer of that story had two paths: extending `src/codegenie/graph/edges.py` (additive, per ADR-P7-001) or forking `src/codegenie/graph/edges_distroless.py` (strict zero-edit). Read S5-04's `Done` notes (or the merged code) to find out which one shipped, and adjust the walker's module scan accordingly. If both files exist, scan both.
- `sys.flags.optimize` returns `0`, `1` (for `-O`), or `2` (for `-OO`). The guard should trigger on `> 0`, not on equality with `1`, because someone running `-OO` is even more dangerous.
- The subprocess test invokes the installed `codegenie` module — make sure the dev install (`pip install -e .`) is the test environment's import path; if running on CI under a fresh checkout, you may need a `pytest -m "needs_install"` marker. Surface this rather than skipping.
- The Phase 6 canary's existing tests must continue to pass; do not delete or rename them. This story is *purely additive* to the existing file (plus the new walker helper file).
- Per CLAUDE.md Rule 12: if a `@pure_edge` predicate's assertion language has changed since Phase 6 (e.g., asserts on a new field added in S5-01 / S5-04), the bad-state factory must trip an assertion that actually exists in the *current* source, not a stale one. Read the predicate source each time.
- The `python -O` startup guard is one line of logic but has a load-bearing failure mode: if it lives *below* a Click decorator or *inside* a function, `--help` may print before the guard fires, and the test fails silently. Put it at the very top of `cli/migrate.py`, after stdlib imports, before any `click` import.
