# Story S5-03 — Add the poetry dep-graph strategy

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** M
**Depends on:** S2-03
**ADRs honored:** ADR-0008

## Context
`poetry.lock` is an *already-resolved* lockfile — pure parsing it (TOML) yields a complete, deterministic dependency graph without any resolver call. ADR-0008 prescribes three concrete per-format strategies (no premature generic abstraction); this is the poetry one. It must apply the Phase-1 byte/depth cap machinery *before* parse so an oversized or billion-laughs lockfile is rejected without OOM or hang.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Python dep-graph strategies (pip / poetry / uv)` — "`poetry.lock` / `uv.lock` / `Pipfile.lock` are TOML/JSON parsed with byte+depth caps", "no package-manager binary invoked; no network touched", three concrete parsers — no generic abstraction (rule-of-three).
- **Architecture:** `../phase-arch-design.md §Edge cases` row 4 — 200 MB / billion-laughs `poetry.lock` rejected *before* parse with `python.lockfile_truncated`/`python.manifest_oversized`, `confidence="low"`, no OOM/hang.
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — pure parse of already-resolved lockfiles, byte+depth caps from ADR-0007, three concrete strategies.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — the byte/depth cap discipline this strategy reuses.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphStrategy` alias, `@register_dep_graph_strategy`.
- **Existing code:** `src/codegenie/parsers/_io.py`, `src/codegenie/parsers/_depth.py` — the Phase-1 `SizeCapExceeded`/`DepthCapExceeded` cap machinery to reuse before parse.
- **Existing code:** `src/codegenie/depgraph/python/pip.py` (S5-02) — the strategy/registration precedent to mirror.

## Goal
Land `depgraph/python/poetry.py` — a pure-parse `DepGraphStrategy` that parses `poetry.lock` TOML under byte/depth caps into a `networkx.DiGraph`, registered via `@register_dep_graph_strategy("poetry")`.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before implementation — then green.
- [ ] The strategy satisfies the `DepGraphStrategy` callable signature and is registered via `@register_dep_graph_strategy("poetry")`; `default_dep_graph_registry` dispatches `"poetry"` to it.
- [ ] A minimal valid `poetry.lock` resolves to a `networkx.DiGraph` with a node per `[[package]]` entry and edges for declared sub-dependencies.
- [ ] An oversized (`> 5 MiB`) lockfile is rejected *before* parse with a `python.lockfile_truncated`/`python.manifest_oversized` warning and a `confidence="low"` partial fact — no OOM, no hang (reuses Phase-1 `SizeCapExceeded`/`DepthCapExceeded`).
- [ ] The strategy parses with `tomllib` only — no package-manager binary, no network, no subprocess.
- [ ] A malformed (non-TOML) `poetry.lock` yields a structured-error / `confidence="low"` result — the strategy never crashes.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green on touched test files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/depgraph/python/poetry.py`.
2. Implement `build_poetry_dep_graph(ctx, manifests) -> networkx.DiGraph` matching the `DepGraphStrategy` shape.
3. Before parse: apply the byte cap (reuse `parsers/_io.py` `SizeCapExceeded` machinery) and the depth cap (`parsers/_depth.py` `DepthCapExceeded`) — reject oversized / deeply-nested lockfiles with the appropriate `_WARNING_IDS` entry.
4. Parse the `poetry.lock` text with `tomllib.loads`; iterate `[[package]]` tables; add a node per package and edges per declared `dependencies`.
5. On a `tomllib.TOMLDecodeError` (malformed lockfile) → return a near-empty graph with `confidence="low"` and a structured warning — never raise out of `run`.
6. Declare a module-level `_WARNING_IDS: Final[frozenset[str]]` (`python.lockfile_truncated`, `python.manifest_oversized`, etc.) validated at import per the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` convention.
7. Decorate with `@register_dep_graph_strategy("poetry")`; add the `+1` import line in `depgraph/python/__init__.py`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/depgraph/python/test_poetry_strategy.py`.
Test name: `test_poetry_lock_resolves_to_digraph`.
```python
def test_poetry_lock_resolves_to_digraph(tmp_path: Path) -> None:
    # arrange: a minimal valid poetry.lock with one [[package]] entry.
    (tmp_path / "poetry.lock").write_text(_MINIMAL_POETRY_LOCK)
    # act
    graph = default_dep_graph_registry.dispatch("poetry", _ctx_for(tmp_path), _manifests(tmp_path))
    # assert: a real DiGraph parsed purely from the lockfile TOML — no resolver.
    assert isinstance(graph, networkx.DiGraph)
    assert graph.number_of_nodes() >= 1
```
Also red before impl: `test_oversized_poetry_lock_rejected_before_parse` (a `> 5 MiB` file → `confidence="low"` + `python.lockfile_truncated`/`python.manifest_oversized` warning, asserting the file is NOT fully read into a TOML parse), `test_malformed_poetry_lock_does_not_crash`. Each fails (no `"poetry"` registered) before impl.

### Green — make it pass
Implement `poetry.py`: cap-check → `tomllib.loads` → build `DiGraph`; register via the decorator. Smallest shape — node per `[[package]]`, edge per declared dependency.

### Refactor — clean up
Extract a pure `poetry_lock_to_graph(toml_text) -> ...` core; docstrings citing ADR-0008; ensure the cap check runs *before* the full read where possible (size-check the file handle, not the loaded string); confirm imports are stdlib (`tomllib`, `pathlib`) + `networkx` + the cap machinery — nothing else.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/depgraph/python/poetry.py` | The poetry `DepGraphStrategy`, registered for `"poetry"`. |
| `src/codegenie/depgraph/python/__init__.py` | `+1` import line so the `@register_dep_graph_strategy("poetry")` decorator fires. |
| `tests/unit/depgraph/python/test_poetry_strategy.py` | The poetry-strategy unit tests. |

## Out of scope
- The pip / uv strategies — S5-02 / S5-04.
- A generic "Python lockfile reader" abstraction shared with uv — ADR-0008 forbids it until a fourth Python package manager (rule-of-three); keep `poetry.py` and `uv.py` independent.
- The adversarial corpus + system egress monitors — S5-05 (pip-scoped; the cap-rejection behavior here is unit-tested locally).
- The depgraph-purity AST fence — S5-06.

## Notes for the implementer
- ADR-0008 explicitly forbids the generic abstraction — resist the urge to share a base parser with `uv.py`. Three concrete parsers is the *correct* design until a fourth package manager appears.
- The byte cap must apply *before* the full TOML parse — read the file size (or stream-cap the read) first; loading a 200 MB file into a string just to reject it defeats the cap (Edge case 4 — no OOM).
- A malformed lockfile is a `confidence="low"` fact, not an exception — the strategy must never raise out into the coordinator.
- Reuse the Phase-1 `SizeCapExceeded`/`DepthCapExceeded` machinery — do not re-implement caps. Step 4's probes establish the reuse pattern for Python; follow it.
- `_WARNING_IDS` must be a module-level `Final[frozenset[str]]` validated at import via `raise AssertionError(...)` (bare `assert` is forbidden by the `forbidden-patterns` hook).
- `tomllib` is stdlib (Python 3.11+) — no third-party TOML dependency, nothing for `make fence` to flag.
