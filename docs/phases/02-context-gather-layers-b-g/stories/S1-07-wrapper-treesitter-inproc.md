# Story S1-07 — Wrapper: `treesitter` in-process query API

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-04
**ADRs honored:** ADR-0005

## Context

Tree-sitter is the only Phase 2 "tool" that runs **in-process** rather than as a subprocess. Python's `tree-sitter` bindings consume pinned grammar wheels (`tree-sitter-typescript`, `tree-sitter-javascript`) and execute queries against parsed source code without forking. This makes `treesitter.py` the lone exception to the wrapper contract's "every wrapper routes through `run_in_sandbox`" rule (S1-04).

The contract is preserved otherwise: typed exceptions, `extra="forbid"` Pydantic result, raw-output write before parse (for the query-result blob), `probe.tool.invoked` emission. The departure from sandbox routing is intentional and **must be loudly documented** in the module docstring — otherwise the next contributor reading the wrapper contract will assume a bug.

Three downstream probes consume this wrapper: `NodeReflectionProbe` (S4-02), `GeneratedCodeProbe` (S4-03), `AstGrepProbe` (S7-04). Each calls `treesitter.query(query_pack, file_paths)` against a pinned `.scm` query pack shipped under `probes/_reflection_queries/` or equivalent.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — `treesitter.query` uses in-process Python `tree-sitter` bindings; no subprocess; no sandbox routing.
  - `../phase-arch-design.md §"4+1 architectural views" "Logical view"` — `TreesitterResult` class diagram.
  - `../phase-arch-design.md §"Edge cases"` — wrong grammar version → `ToolOutputMalformed` (adversarial test `test_treesitter_grammar_version_mismatch.py` ships in S4-02).
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — ADR-0004 — tree-sitter grammar wheel hashes pinned in both `uv.lock` and `tools/digests.yaml` (double pin).
  - `../ADRs/0005-allowed-binaries-additions.md` — tree-sitter is **not** in `ALLOWED_BINARIES` (no subprocess); the digest pin is the integrity mechanism here.
- **Source design:**
  - `../final-design.md §"Components" #1 tools/ wrappers` — design statement.
- **Existing code:**
  - `src/codegenie/tools/__init__.py` — `ToolResult` base (S1-04).
  - `src/codegenie/errors.py` — typed exceptions (S1-01).
  - `pyproject.toml` — extend with pinned `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript` deps + wheel digests.

## Goal

Implement `src/codegenie/tools/treesitter.py` as an in-process Python wrapper exporting `async def query(query_pack: Path, file_paths: Sequence[Path]) -> TreesitterResult`, with the grammar version surfacing in `tool_digest`, pinned wheel hashes added to `pyproject.toml`, and the in-process departure from the wrapper contract documented loudly in the module docstring.

## Acceptance criteria

- [ ] `src/codegenie/tools/treesitter.py` exists with a multi-line module docstring that explicitly states: (a) this wrapper is **the only `tools/` module that does not route through `run_in_sandbox`** because the workload is in-process Python bindings, (b) the integrity mechanism is the pinned wheel hash in `tools/digests.yaml` + `uv.lock`, (c) hostile grammar mismatch surfaces as `ToolOutputMalformed`.
- [ ] `src/codegenie/tools/treesitter.py` exports `TreesitterResult(ToolResult)` (with `per_file_hits: Mapping[Path, list[TreesitterHit]]`), `TreesitterHit(BaseModel)` (with `query_name`, `start_byte`, `end_byte`, `start_row`, `end_row`, `captures: Mapping[str, str]`), `TOOL_NAME = "treesitter"`, `async def query(query_pack: Path, file_paths: Sequence[Path], raw_output_path: Path) -> TreesitterResult`.
- [ ] The wrapper loads the `query_pack` (a `.scm` query file shipped under `probes/_reflection_queries/` or `probes/_ast_grep_queries/`) and executes it against each `file_path` using the language inferred from the file extension (`.ts`/`.tsx` → TypeScript grammar; `.js`/`.jsx` → JavaScript grammar).
- [ ] Grammar mismatch (e.g., grammar wheel installed at version X but query pack authored for version Y; or hostile `.scm` file that fails to compile against the installed grammar) raises `ToolOutputMalformed(tool_name="treesitter", detail=...)`.
- [ ] The wrapper writes a serialized JSON blob of `per_file_hits` to `raw_output_path` **before** validating into `TreesitterResult` (preserving the raw-output-before-parse discipline from S1-04 even though parsing is internal).
- [ ] `tool_digest` is populated from the installed `tree-sitter-typescript` and `tree-sitter-javascript` grammar versions (read at import time via `__version__` or wheel-hash lookup via S1-08's `tools/digests.get(...)` helper).
- [ ] `pyproject.toml` is extended with pinned `tree-sitter = "==X.Y.Z"`, `tree-sitter-typescript = "==X.Y.Z"`, `tree-sitter-javascript = "==X.Y.Z"` dependencies; corresponding wheel SHA-256 digests are added to `uv.lock`.
- [ ] `tests/unit/tools/test_treesitter.py` ships ≥ 5 tests — happy-path query against a tiny synthetic `.ts` file, query against `.js` file (correct grammar dispatch), grammar mismatch → `ToolOutputMalformed`, raw-output file written before parse, `probe.tool.invoked` emitted.
- [ ] `scripts/check_tools_no_subprocess.py` lint passes (the wrapper imports `tree_sitter` and `tree_sitter_typescript` / `tree_sitter_javascript`, none of which are on the forbidden list).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write `tests/unit/tools/test_treesitter.py` first (red) with fixtures under `tests/fixtures/treesitter/{tiny_ts.ts, tiny_js.js, eval_call.ts}` and a tiny `.scm` query file that matches `eval(...)` calls.
2. Implement `src/codegenie/tools/treesitter.py`:
   - Module docstring (multi-paragraph) explaining the in-process departure.
   - Import `tree_sitter`, `tree_sitter_typescript`, `tree_sitter_javascript` at module top (these are pure-Python wheels + native bindings).
   - At import time, instantiate `Parser` objects for each language and cache them: `_TS_PARSER`, `_JS_PARSER`.
   - At import time, populate `_TOOL_DIGEST: Final[str]` from `tree_sitter_typescript.__version__` + `tree_sitter_javascript.__version__` (concatenated with `:`).
   - `TreesitterHit(BaseModel)` and `TreesitterResult(ToolResult)` with `extra="forbid"`.
   - `def _language_for(path: Path)` returns the right `Language` based on file extension; raises `ValueError` on unsupported extension.
   - `async def query(query_pack, file_paths, raw_output_path)`:
     1. Read query pack content; compile via `Language.query(...)` for whichever language matches the majority of files (or per-file).
     2. For each file path, read bytes, parse via the relevant parser, execute the compiled query, collect captures into `TreesitterHit`s.
     3. Catch `tree_sitter.LanguageError`, `tree_sitter.QueryError`, and `pydantic.ValidationError` → re-raise as `ToolOutputMalformed`.
     4. Serialize `per_file_hits` to JSON and write to `raw_output_path` before constructing the `TreesitterResult`.
     5. Emit `probe.tool.invoked` with `tool_name="treesitter"`, `sandbox_network="in_process"`, `wall_clock_ms`, `exit_code=0`.
3. Extend `pyproject.toml` `[project.dependencies]` with the three pinned packages (use the latest stable versions at story time; record exact versions in the digest manifest in S1-08).
4. Run `uv lock` (or the project's lockfile tool) to populate wheel digests; commit `uv.lock`.
5. Run `pytest tests/unit/tools/test_treesitter.py`, the no-subprocess lint, `ruff check`, `mypy --strict src/codegenie/tools/treesitter.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tools/test_treesitter.py`.

```python
import json
from pathlib import Path

import pytest

import codegenie.errors as e
from codegenie.tools import treesitter


FIXTURES = Path("tests/fixtures/treesitter")


@pytest.mark.asyncio
async def test_treesitter_finds_eval_calls_in_ts(tmp_path: Path):
    query_pack = FIXTURES / "eval_query.scm"
    target = FIXTURES / "eval_call.ts"
    raw_out = tmp_path / "raw.json"
    result = await treesitter.query(
        query_pack=query_pack, file_paths=[target], raw_output_path=raw_out,
    )
    assert isinstance(result, treesitter.TreesitterResult)
    assert target in result.per_file_hits
    assert any(h.query_name == "eval_call" for h in result.per_file_hits[target])
    # raw blob written before parse — file exists and parses as JSON
    assert raw_out.exists()
    json.loads(raw_out.read_text())


@pytest.mark.asyncio
async def test_treesitter_dispatches_js_grammar_for_js_file(tmp_path: Path):
    query_pack = FIXTURES / "eval_query.scm"
    target = FIXTURES / "tiny_js.js"
    result = await treesitter.query(
        query_pack=query_pack, file_paths=[target], raw_output_path=tmp_path / "raw.json",
    )
    # smoke: produces a result without raising
    assert isinstance(result, treesitter.TreesitterResult)


@pytest.mark.asyncio
async def test_treesitter_malformed_query_raises_typed(tmp_path: Path):
    # Hostile .scm — invalid query syntax
    bad_query = tmp_path / "bad.scm"
    bad_query.write_text("(((( unclosed paren")
    target = FIXTURES / "eval_call.ts"
    with pytest.raises(e.ToolOutputMalformed) as exc:
        await treesitter.query(
            query_pack=bad_query, file_paths=[target], raw_output_path=tmp_path / "raw.json",
        )
    assert exc.value.tool_name == "treesitter"


@pytest.mark.asyncio
async def test_treesitter_unsupported_extension_raises(tmp_path: Path):
    weird = tmp_path / "x.rs"
    weird.write_text("fn main() {}")
    query_pack = FIXTURES / "eval_query.scm"
    with pytest.raises(e.ToolOutputMalformed):
        await treesitter.query(
            query_pack=query_pack, file_paths=[weird], raw_output_path=tmp_path / "raw.json",
        )


def test_tool_digest_includes_grammar_versions():
    assert ":" in treesitter._TOOL_DIGEST  # composed of ts + js versions
    assert treesitter._TOOL_DIGEST  # non-empty
```

Run; confirm `ImportError`. Commit as red marker.

### Green — make it pass

Implement per the outline. Keep the wrapper under ~150 LOC.

### Refactor — clean up

- The `_TS_PARSER` / `_JS_PARSER` module-level parsers are intentionally cached at import — tree-sitter parser construction is cheap but non-trivial, and the wrapper is called once per probe per gather. Document the lifecycle in the docstring.
- The `_TOOL_DIGEST` computation belongs at module scope (not inside `run`) — it's a constant for the process lifetime. Mark it `Final`.
- Add a brief doc comment to `eval_query.scm` fixture explaining the capture group name (`@eval_call`) — future tree-sitter query writers benefit from a reference example.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/treesitter.py` | New — in-process wrapper |
| `tests/unit/tools/test_treesitter.py` | New — ≥ 5 tests |
| `tests/fixtures/treesitter/eval_query.scm` | New — tiny `.scm` query |
| `tests/fixtures/treesitter/eval_call.ts` | New — fixture with `eval()` call |
| `tests/fixtures/treesitter/tiny_js.js` | New — JS-grammar dispatch fixture |
| `pyproject.toml` | Pin `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript` |
| `uv.lock` | Record wheel digests |

## Out of scope

- **`probes/_reflection_queries/node.yaml`** — handled by S4-02 (`NodeReflectionProbe`).
- **`probes/_ast_grep_queries/`** — handled by S7-04 (`AstGrepProbe`).
- **Per-file findings sub-cache module** — handled by S7-01; the per-file cache **shape** is established by S4-02. This wrapper has no caching responsibilities.
- **Grammar version pin in `tools/digests.yaml`** — handled by S1-08 (the manifest); this story pins in `pyproject.toml` + `uv.lock` and computes `_TOOL_DIGEST` from `__version__`.
- **Adversarial `test_treesitter_grammar_version_mismatch.py`** — handled by S4-02 (where the consumer probe surfaces the failure).

## Notes for the implementer

- **The in-process departure from the wrapper contract must be loudly documented.** Per Rule 12 (Fail loud, signal-direction edition), a future contributor reading `tools/__init__.py`'s wrapper-contract checklist and then looking at `treesitter.py` should immediately see "this wrapper does not route through `run_in_sandbox` and here's why" — three sentences at the top of the module docstring. Resist the temptation to make it a one-liner.
- The integrity mechanism for tree-sitter is the pinned wheel hash (S1-08's double pin: `pyproject.toml` + `uv.lock` cross-checked against `tools/digests.yaml`). A future contributor who bumps the grammar wheel must update both files; the install-time verifier (S1-08) catches mismatches. The wrapper's `tool_digest` is the per-call surface of that pin.
- Tree-sitter's Python bindings load native code (`.so` / `.dylib`) into the Python process. This is the precise reason the sandbox can't help: the bindings execute inside the same address space as the gatherer. Per ADR-0005 (tree-sitter is **not** in `ALLOWED_BINARIES`), this is accepted as a Phase 2 tradeoff because the alternative — subprocess + IPC for every tree-sitter query — would 10× the wall-clock cost. Phase 5's microVM is the long-term answer.
- `_language_for(path)` should be a small, exhaustive `match/case` over the closed set of supported extensions. Unsupported → `ToolOutputMalformed` per the test. Per Rule 11 (match conventions), Phase 2 favors closed enums over open dispatch (ADR-0008's pattern); follow it here.
- Async-but-not-really: `query` is declared `async` for consistency with the wrapper contract (S1-04 documents async wrappers), but the tree-sitter work is CPU-bound and synchronous internally. The `async` declaration is a future-proofing surface (e.g., per-file parallelism via `asyncio.to_thread`) without committing to it now. Document this in the function docstring.
- Per the wrapper contract, the raw output write happens **before** Pydantic validation. For tree-sitter, the "raw output" is the serialized hits dict — write it to `raw_output_path` first (JSON-serialize the `dict[str, list[dict]]` directly), then construct `TreesitterResult`. If `TreesitterResult` construction fails, the raw bytes are on disk for triage.
- Capture group names in the `.scm` files are the query author's surface — they become `TreesitterHit.query_name`. The example fixture's `(call_expression function: (identifier) @eval_call)` makes `@eval_call` the capture name. Document this convention in the eval_query.scm fixture's leading comment so S4-02/S4-03/S7-04 authors copy it correctly.
- Do **not** add a `treesitter.parse(file_path) -> Tree` public function. The wrapper exports `query` and that's it. Future probes that need parse trees pass query specs; the parse tree never escapes the wrapper. This keeps the contract small and prevents probe authors from coupling to tree-sitter internals.
