# Story S5-04 — Add the uv dep-graph strategy

**Step:** Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)
**Status:** Ready
**Effort:** M
**Depends on:** S2-03
**ADRs honored:** ADR-0008

## Context
`uv.lock` is an already-resolved TOML lockfile — like `poetry.lock`, pure parsing it yields a deterministic dependency graph with no resolver call. This is the third of ADR-0008's three concrete per-format strategies; it parses `uv.lock` under the same byte/depth cap discipline. Completing the `pip`/`poetry`/`uv` triple is a prerequisite for `S7-01` (constructing `PYTHON_PACK`).

## References — where to look
- **Architecture:** `../phase-arch-design.md §Python dep-graph strategies (pip / poetry / uv)` — `uv.lock` TOML parsed with byte+depth caps, three concrete parsers — no generic abstraction, "no package-manager binary invoked; no network touched".
- **Architecture:** `../phase-arch-design.md §Edge cases` row 4 — oversized / billion-laughs lockfile rejected *before* parse, `confidence="low"`, no OOM/hang.
- **Phase ADRs:** `../ADRs/0008-python-depgraph-pure-parsing-no-resolution.md` — ADR-0008 — pure parse, byte+depth caps, three concrete strategies, no premature abstraction, `ALLOWED_BINARIES` untouched.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — the byte/depth cap discipline this strategy reuses.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphStrategy` alias, `@register_dep_graph_strategy`.
- **Existing code:** `src/codegenie/parsers/_io.py`, `src/codegenie/parsers/_depth.py` — the Phase-1 cap machinery.
- **Existing code:** `src/codegenie/depgraph/python/poetry.py` (S5-03) — the TOML-lockfile strategy precedent; mirror its shape but keep it an independent file (no shared base — rule-of-three).

## Goal
Land `depgraph/python/uv.py` — a pure-parse `DepGraphStrategy` that parses `uv.lock` TOML under byte/depth caps into a `networkx.DiGraph`, registered via `@register_dep_graph_strategy("uv")`.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and fails before implementation — then green.
- [ ] The strategy satisfies the `DepGraphStrategy` callable signature and is registered via `@register_dep_graph_strategy("uv")`; `default_dep_graph_registry` dispatches `"uv"` to it.
- [ ] A minimal valid `uv.lock` resolves to a `networkx.DiGraph` with a node per `[[package]]` entry and edges for declared dependencies.
- [ ] An oversized (`> 5 MiB`) / billion-laughs `uv.lock` is rejected *before* parse with a `python.lockfile_truncated`/`python.manifest_oversized` warning and `confidence="low"` — no OOM, no hang.
- [ ] The strategy parses with `tomllib` only — no package-manager binary, no network, no subprocess; `ALLOWED_BINARIES` is verified untouched (no `uv` entry — covered by the S5-05 closed-set test but assert nothing here adds it).
- [ ] A malformed (non-TOML) `uv.lock` yields a `confidence="low"` structured-error result — the strategy never crashes.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest` green on touched test files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/depgraph/python/uv.py`.
2. Implement `build_uv_dep_graph(ctx, manifests) -> networkx.DiGraph` matching the `DepGraphStrategy` shape.
3. Before parse: apply the byte + depth caps (reuse `parsers/_io.py` / `parsers/_depth.py`) — reject oversized / deeply-nested lockfiles with the right `_WARNING_IDS` entry.
4. Parse `uv.lock` text with `tomllib.loads`; iterate `[[package]]` tables (uv's lock schema: `name`, `version`, `dependencies`); add a node per package and edges per declared dependency.
5. On a `tomllib.TOMLDecodeError` → return a near-empty graph with `confidence="low"` and a structured warning — never raise out of `run`.
6. Declare a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import.
7. Decorate with `@register_dep_graph_strategy("uv")`; add the `+1` import line in `depgraph/python/__init__.py`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/depgraph/python/test_uv_strategy.py`.
Test name: `test_uv_lock_resolves_to_digraph`.
```python
def test_uv_lock_resolves_to_digraph(tmp_path: Path) -> None:
    # arrange: a minimal valid uv.lock with one [[package]] table.
    (tmp_path / "uv.lock").write_text(_MINIMAL_UV_LOCK)
    # act
    graph = default_dep_graph_registry.dispatch("uv", _ctx_for(tmp_path), _manifests(tmp_path))
    # assert: a real DiGraph parsed purely from uv.lock TOML — no resolver call.
    assert isinstance(graph, networkx.DiGraph)
    assert graph.number_of_nodes() >= 1
```
Also red before impl: `test_oversized_uv_lock_rejected_before_parse` (a `> 5 MiB` file → `confidence="low"` + warning, file not fully parsed), `test_malformed_uv_lock_does_not_crash`. Each fails (no `"uv"` registered) before impl.

### Green — make it pass
Implement `uv.py`: cap-check → `tomllib.loads` → build `DiGraph`; register via the decorator. Smallest shape — node per `[[package]]`, edge per declared dependency.

### Refactor — clean up
Extract a pure `uv_lock_to_graph(toml_text) -> ...` core; docstrings citing ADR-0008; cap-check before the full read; confirm imports are stdlib + `networkx` + cap machinery only.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/depgraph/python/uv.py` | The uv `DepGraphStrategy`, registered for `"uv"`. |
| `src/codegenie/depgraph/python/__init__.py` | `+1` import line so the `@register_dep_graph_strategy("uv")` decorator fires. |
| `tests/unit/depgraph/python/test_uv_strategy.py` | The uv-strategy unit tests. |

## Out of scope
- The pip / poetry strategies — S5-02 / S5-03.
- A generic lockfile-reader abstraction shared with `poetry.py` — ADR-0008 forbids it until a fourth Python package manager; keep `uv.py` independent.
- The adversarial corpus + system egress monitors — S5-05.
- The depgraph-purity AST fence — S5-06.
- Constructing `PYTHON_PACK`'s `dep_graph_strategies` mapping from the three strategies — S7-01.

## Notes for the implementer
- Keep `uv.py` independent of `poetry.py` — they look similar but ADR-0008 explicitly defers the shared abstraction to a fourth package manager (rule-of-three). Copy-with-divergence is the *intended* design here.
- uv's lock schema differs from poetry's in details (`uv.lock` uses `[[package]]` with `name`/`version`/`dependencies` arrays) — parse the actual `uv.lock` format, do not assume poetry's layout.
- Byte cap before the full TOML parse — same discipline as S5-03 (Edge case 4 — no OOM on a 200 MB file).
- A malformed lockfile is a `confidence="low"` fact, never an exception out of the coordinator.
- `_WARNING_IDS` must be a module-level `Final[frozenset[str]]` validated at import via `raise AssertionError(...)` — bare `assert` is forbidden by the `forbidden-patterns` hook.
- This story is on the critical spine to `S7-01` (`PYTHON_PACK`) — it must register cleanly so `validate_pack`'s grammar/strategy checks pass.
