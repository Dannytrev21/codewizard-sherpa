# Story S7-04 — `AstGrepProbe` + `InvariantHintProbe` + `GrepProbe`

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S1-07
**ADRs honored:** ADR-0010 (`tantivy` opt-in via `codegenie[search]` extra)

## Context

Three Layer-G Tier-0 probes ship together because they all consume `tools.treesitter.query` (Step 1's in-process tree-sitter wrapper) and share the same cache-key shape. `AstGrepProbe` does ast-grep-style structural matching over the tree-sitter CST; `InvariantHintProbe` extracts pre/post-condition hints from comments and assertions (Tier-0 heuristics — no LLM); `GrepProbe` does BM25 over repo contents with **ripgrep as the default backend** and **`tantivy` as an opt-in via `codegenie[search]`**. ADR-0010 is the load-bearing decision: the default `pip install codegenie` produces a ripgrep-only build; `tantivy` is `codegenie[search]`. The `fence` CI job is extended in S7-04 to forbid `tantivy` in default deps.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #19` — `tools.treesitter.query` interface.
  - `../phase-arch-design.md §"Component design" #7 Layer G — SAST + behavioral hints` summary.
  - `../phase-arch-design.md §"Logical view"` — `AstGrepProbe → ToolsPackage: tools.treesitter.query`.
  - `../phase-arch-design.md §"Non-goals" #5` — no LLM in Tier-0 invariant hints; pure structural extraction.
- **Phase ADRs:**
  - `../ADRs/0010-tantivy-as-opt-in-extra.md` — ADR-0010 (default ripgrep; `tantivy` opt-in; `index_backend` slice field for downstream consumers).
- **Source design:**
  - `../final-design.md §"Components" §7 Layer G`.
  - `../final-design.md §"Conflict-resolution table" D11` — `tantivy` opt-in winner.
- **Existing code:**
  - `src/codegenie/tools/treesitter.py` (S1-07) — `async query(file_path, grammar, query_str) -> list[Match]`.
  - `src/codegenie/probes/_reflection_queries/node.yaml` (S4-02) — pinned tree-sitter query pack; reused for ast-grep style queries.
  - CI `fence` job — at `.github/workflows/`; existing import-banlist for `httpx`/`requests`/`socket`/`urllib3`/LLM SDKs.

## Goal

Ship three Layer-G probes in one PR — `src/codegenie/probes/{ast_grep,invariant_hints,grep}.py` — plus three sub-schemas under `src/codegenie/schema/probes/`. Extend the `fence` CI job to forbid `tantivy` in default deps. `GrepProbe` records `index_backend ∈ {"ripgrep", "tantivy"}` in its slice; ripgrep is detected at startup via `try: import tantivy except ImportError: backend = "ripgrep"`.

## Acceptance criteria

- [ ] `src/codegenie/probes/ast_grep.py` exports `AstGrepProbe(Probe)` with `name="ast_grep"`, `declared_inputs=["src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}"]`, `requires=["language_detection"]`, `applies_to_languages=["javascript", "typescript"]`. Consumes `tools.treesitter.query` against a set of structural queries (function-call-pattern, assignment-pattern, control-flow-pattern). Queries live under `src/codegenie/probes/_ast_grep_queries/node.yaml` (pinned query pack).
- [ ] `src/codegenie/probes/invariant_hints.py` exports `InvariantHintProbe(Probe)` with `name="invariant_hints"`, `declared_inputs=["src/**/*.{ts,tsx,...}"]`, `requires=["language_detection"]`, `applies_to_languages=["*"]`. Tier-0 heuristics: extract `assert(...)` calls, `// @invariant` comments, JSDoc `@pre`/`@post` tags. No LLM. Emits `hints: list[{file, line, kind ∈ {"assert","invariant","pre","post"}, source: str}]`.
- [ ] `src/codegenie/probes/grep.py` exports `GrepProbe(Probe)` with `name="grep"`, `declared_inputs=["**/*"]` (filtered), `requires=[]`, `applies_to_languages=["*"]`. Detects backend at startup: `try: import tantivy; backend = "tantivy"; except ImportError: backend = "ripgrep"`. Emits `slice = {"index_backend": <"ripgrep"|"tantivy">, "doc_count": int, "indexed_at_commit": str | None}`. Index built into `.codegenie/index/grep-bm25/` (separate from SCIP namespace; per-repo).
- [ ] Three sub-schemas: `src/codegenie/schema/probes/{ast_grep,invariant_hints,grep}.schema.json` — `additionalProperties: false`; `schema_version: "v1"`; for `grep`, `index_backend` is a closed enum `["ripgrep", "tantivy"]`.
- [ ] `fence` CI job (`.github/workflows/<ci>.yml` or `scripts/check_fence.py`) extended: assertion that `tantivy` is **not** in `pyproject.toml`'s default `[project] dependencies`; only in `[project.optional-dependencies] search`. Synthetic-mismatch test fails the fence as expected.
- [ ] `tests/unit/probes/test_ast_grep.py` — happy path on a fixture file; query-pack version participates in cache key; structural match on `new Function(...)` returns a hit.
- [ ] `tests/unit/probes/test_invariant_hints.py` — fixture with `assert(x > 0)`, `// @invariant: y != null`, JSDoc `@pre i >= 0` → 3 hints extracted; `kind` correctly classified.
- [ ] `tests/unit/probes/test_grep.py` — default backend is `ripgrep` (assert `index_backend == "ripgrep"` without `tantivy` installed); `doc_count` matches the fixture file count.
- [ ] `tests/unit/probes/test_grep_tantivy_opt_in.py` — when `tantivy` is importable (CI matrix run with `pip install codegenie[search]`), backend is `tantivy`. Marked with a custom pytest mark `@pytest.mark.tantivy` (skipped by default).
- [ ] `tests/unit/ci/test_fence_forbids_tantivy_default.py` — synthetic `pyproject.toml` with `tantivy` in default deps fails the fence script.
- [ ] Three goldens at `tests/golden/{ast_grep,invariant_hints,grep}/happy/expected.json`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/ast_grep.py` — `AstGrepProbe`:
   - Load `_ast_grep_queries/node.yaml` (pinned); for each query, call `tools.treesitter.query(file, grammar="typescript", query_str=...)`.
   - Aggregate matches; emit `slice = {"matches": [...], "queries_in_use_version": <hash>}`.
2. Create `src/codegenie/probes/invariant_hints.py` — `InvariantHintProbe`:
   - For each source file, parse via `tools.treesitter.query` looking for `call_expression` with `assert` identifier, comments with `@invariant`/`@pre`/`@post`.
   - Tier-0 heuristics only — no LLM, no semantic parsing.
3. Create `src/codegenie/probes/grep.py` — `GrepProbe`:
   - Module-level: `try: import tantivy; _BACKEND = "tantivy"; except ImportError: _BACKEND = "ripgrep"`.
   - `_build_index_ripgrep(snapshot, index_dir) -> dict` — invoke `rg --files --json` (via `tools.run_in_sandbox` if needed; ripgrep is in `ALLOWED_BINARIES` already from Phase 0); store a small BM25-tf-idf index in pure-Python (msgpack on disk).
   - `_build_index_tantivy(snapshot, index_dir) -> dict` — `tantivy.SchemaBuilder()` + `Index` + bulk index.
   - Emit `slice = {"index_backend": _BACKEND, "doc_count": <int>, "indexed_at_commit": <git HEAD>}`.
4. Create the three sub-schemas. `grep.schema.json`'s `index_backend` is `{"enum": ["ripgrep", "tantivy"]}`.
5. Extend `scripts/check_fence.py` (Phase 0/1) — add a check that `tantivy` is absent from `[project.dependencies]` in `pyproject.toml` (only present under `[project.optional-dependencies.search]`).
6. Register all three probes in `probes/__init__.py`.
7. Plant `tests/fixtures/ast_grep_node_fixture/`, `tests/fixtures/invariant_hints_fixture/`, ripgrep happy fixture.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_ast_grep.py`.

```python
async def test_ast_grep_finds_new_function(tmp_repo_with_new_function, ctx):
    out = await AstGrepProbe().run(tmp_repo_with_new_function.snapshot, ctx)
    assert any("new Function" in m["source"] for m in out.slice["matches"])
```

Path: `tests/unit/probes/test_invariant_hints.py`.

```python
async def test_extracts_three_hint_kinds(tmp_invariant_fixture, ctx):
    out = await InvariantHintProbe().run(tmp_invariant_fixture.snapshot, ctx)
    kinds = {h["kind"] for h in out.slice["hints"]}
    assert {"assert", "invariant", "pre"} <= kinds
```

Path: `tests/unit/probes/test_grep.py`.

```python
async def test_grep_defaults_to_ripgrep_without_tantivy(tmp_repo, ctx, monkeypatch):
    monkeypatch.setattr("codegenie.probes.grep._BACKEND", "ripgrep")
    out = await GrepProbe().run(tmp_repo.snapshot, ctx)
    assert out.slice["index_backend"] == "ripgrep"
    assert out.slice["doc_count"] > 0
```

Path: `tests/unit/ci/test_fence_forbids_tantivy_default.py`.

```python
def test_fence_rejects_tantivy_in_default_deps(tmp_pyproject_with_tantivy_in_defaults):
    from scripts.check_fence import check_pyproject
    with pytest.raises(SystemExit):
        check_pyproject(tmp_pyproject_with_tantivy_in_defaults)
```

### Green

Minimal impl per outline. Tree-sitter queries reuse the S4-02 query-pack pattern (one YAML, one grammar version). Ripgrep BM25 is implemented as a thin pure-Python wrapper (no new C-extension dep). Tantivy import is `try/except` and gated behind the optional-deps extra.

### Refactor

- Each probe gets its own module docstring naming the relevant arch-design section and ADR-0010 (for `grep.py` only).
- Helper for tree-sitter cache-key derivation lives in `tools/treesitter.py` (S1-07) — reuse, don't re-implement.
- `_BACKEND` detection is module-level (one-time at import) — testable via `monkeypatch`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/ast_grep.py` | New — `AstGrepProbe`. |
| `src/codegenie/probes/invariant_hints.py` | New — `InvariantHintProbe`. |
| `src/codegenie/probes/grep.py` | New — `GrepProbe` with backend detection. |
| `src/codegenie/probes/_ast_grep_queries/node.yaml` | New — pinned query pack. |
| `src/codegenie/schema/probes/ast_grep.schema.json` | New — sub-schema. |
| `src/codegenie/schema/probes/invariant_hints.schema.json` | New — sub-schema. |
| `src/codegenie/schema/probes/grep.schema.json` | New — sub-schema with `index_backend` enum. |
| `src/codegenie/probes/__init__.py` | Register three probes. |
| `scripts/check_fence.py` | Extend — forbid `tantivy` in default deps. |
| `pyproject.toml` | Add `[project.optional-dependencies].search = ["tantivy~=..."]`. |
| `tests/unit/probes/test_ast_grep.py` | New. |
| `tests/unit/probes/test_invariant_hints.py` | New. |
| `tests/unit/probes/test_grep.py` | New. |
| `tests/unit/probes/test_grep_tantivy_opt_in.py` | New — `@pytest.mark.tantivy`. |
| `tests/unit/ci/test_fence_forbids_tantivy_default.py` | New. |
| `tests/fixtures/{ast_grep_node_fixture,invariant_hints_fixture}/` | New. |
| `tests/golden/{ast_grep,invariant_hints,grep}/happy/expected.json` | New. |

## Out of scope

- **LLM-driven invariant extraction** — Tier-0 heuristics only; ADR-0006 production preserved.
- **Cross-file ast-grep queries** — per-file only; cross-file taint is semgrep's `--paranoid`.
- **Tantivy as default** — refused by ADR-0010.
- **Distributed grep index** — single-repo only.
- **Index incremental rebuild** — Phase 14 tunes; Phase 2 rebuilds index on cache-miss.

## Notes for the implementer

- **`_BACKEND` detection happens once at module import.** Caching it at module scope means re-running the gather without reinstalling won't see backend changes — which is the intended contract (install determines backend). Don't move the detection into the probe's `run` method.
- **Ripgrep BM25 is not "ripgrep computes BM25"** — ripgrep finds files; pure-Python computes BM25 scores. Keep the scoring logic small (one function, < 50 LOC); Phase 14 will tune.
- **`index_backend` is in the slice, not metadata.** Phase 4's RAG consumer needs to know which backend produced the index without re-querying. The field is required, not optional. Don't put it in `errors` or `warnings`.
- **`@pytest.mark.tantivy` registration** — add to `pyproject.toml`'s `[tool.pytest.ini_options].markers` so unknown-mark warnings don't fire.
- **Tree-sitter query packs are pinned via `tools/digests.yaml`.** Query-pack version goes into the cache key (S4-02 set this contract; reuse it). If you add a new query to `_ast_grep_queries/node.yaml`, bump the pack version; the cache invalidation is automatic.
- **`InvariantHintProbe` heuristics are deliberately shallow.** Don't try to handle every JSDoc dialect — just `@pre`, `@post`, `@invariant`. Phase 4 will layer LLM-augmented hint extraction on top; this story ships the deterministic baseline.
- **The `fence` extension is one regex check on `pyproject.toml`.** Don't overbuild — a small AST-walk of the TOML's `[project.dependencies]` list, asserting `tantivy` is absent, is enough. The test plants a synthetic violation; that's the witness.
- **Ripgrep is already in `ALLOWED_BINARIES`** (Phase 0 inheritance) — `tools.run_in_sandbox(["rg", ...], network="none")` is the invocation pattern. Don't add a new `tools/rg.py` wrapper unless this probe's call pattern is non-trivial.
