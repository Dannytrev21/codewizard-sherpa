# Story S4-04 — `TreeSitterImportGraphProbe` — `py-tree-sitter` no-internal-threads + grammar pin

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** M
**Depends on:** S4-03 (`tools/grammars.lock` + vendored TypeScript + JavaScript grammar binaries on disk; load-time BLAKE3 verification target)
**ADRs honored:** [`02-ADR-0002`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) (`py-tree-sitter` is the **one** Phase-2 C-extension exception amending Phase 1 ADR-0009; grammar pin is the supply-chain defense; in-process load, NOT a `_grammar_runner` subprocess), [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (`heaviness="medium"` is a registry annotation; no internal `ThreadPoolExecutor` — hidden parallelism lies to the coordinator's single semaphore), Phase 1 ADR-0008 (in-process parse caps, not per-probe sandbox; grammar code runs in the gather process), Phase 1 ADR-0007 (warning ID pattern)

## Context

`TreeSitterImportGraphProbe` extracts file-level import edges from the source tree using `tree-sitter` grammars and emits forward-only adjacency to `raw/import-graph.json`. Phase 3's adapters (`ImportGraphAdapter` `Protocol` shipped in S1-08) decide reverse projection; Phase 2 emits only.

Two disciplines from [ADR-0002](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) and [phase-arch-design.md §"Component design" #12](../phase-arch-design.md) are load-bearing:

1. **In-process load with BLAKE3 grammar pin verification at load time.** Vendored grammar binaries live under `tools/grammars/` and are pinned in `tools/grammars.lock` (landed in S4-03). The probe verifies BLAKE3 before any grammar code executes. On mismatch → `GrammarLoadRefused` (typed exception); probe slice `confidence="low"`, `error_id="grammar_pin_mismatch"`, **no grammar code runs**. The pin is the supply-chain defense — a malicious grammar binary would have to clear the pin first.
2. **No internal `ThreadPoolExecutor`** — the probe is one slot under the Phase 0 single `Semaphore(min(cpu_count(), 8))`. Hidden parallelism inside a probe lies to the coordinator's budget ([ADR-0003 §Decision](../ADRs/0003-coordinator-heaviness-sort-annotation.md) reinforces this). Per-file extraction is sequential under the probe; the coordinator owns concurrency across probes. **Verified by `tracemalloc`/thread-count assertion at test time** (not just by absence-of-`threading`-import grep — that's the test the manifest's risk callout warned against).

[ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) explicitly rejects `_grammar_runner` (out-of-process subprocess for tree-sitter invocations) — the grammar pin already addresses the threat; the subprocess wrap is over-engineering. In-process is the boring shape; a crashed grammar crashes the gather process, and Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`. Loudness is a feature (Rule 12).

The slice ([localv2.md §5.2 B3](../../../localv2.md) — `NodeReflectionProbe` SLICE has reflection data, NOT import edges; this probe lands forward-only adjacency under a `import_graph` slice that the architecture treats separately from `reflection`). The arch [§"Component design" #12](../phase-arch-design.md) names `raw/import-graph.json` as the artifact; the slice itself summarizes (`files_with_imports`, `total_edges`, `cyclic_components_count`, `confidence`). Production consumers (Phase 3's `ImportGraphAdapter`) read the raw JSON, not the slice.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #12`](../phase-arch-design.md) — full internal structure; load-bearing properties: in-process, no thread pool, grammar pin verified.
  - [`../phase-arch-design.md §"Edge cases" row 10`](../phase-arch-design.md) — tree-sitter grammar BLAKE3 mismatch.
  - [`../phase-arch-design.md §"Design patterns applied"`](../phase-arch-design.md) row "Anti-patterns avoided" — "hidden parallelism inside a probe lies to the coordinator's budget."
- **Phase 2 ADRs:**
  - [`../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — full rationale; in-process; pin-at-load; `_grammar_runner` rejected; one named-trigger exception to Phase 1 ADR-0009.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness="medium"`; no internal pools.
- **Phase 1 ADRs:**
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md`](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) — the policy this ADR amends.
- **Source design:**
  - [`docs/localv2.md §5.2 B3`](../../../localv2.md) — `NodeReflectionProbe` uses tree-sitter as a sibling pattern; this probe is the import-graph one.
- **Existing code:**
  - `tools/grammars.lock` + `tools/grammars/{typescript,javascript}.so` (from S4-03).
  - `src/codegenie/probes/base.py` (frozen).
  - `src/codegenie/probes/registry.py` (extended in S1-08).

## Goal

Running `codegenie gather` against a TypeScript/JavaScript repo populates `.codegenie/context/raw/import-graph.json` (a JSON file containing forward-only adjacency, NetworkX-serializable shape) AND emits an `import_graph` slice summarizing edge counts. Grammar binaries are loaded in-process with BLAKE3 verified against `tools/grammars.lock` BEFORE any grammar code executes; mismatch produces typed `GrammarLoadRefused`. The probe contains zero `ThreadPoolExecutor`, zero `multiprocessing.Pool`, zero `asyncio.gather` over per-file work — per-file extraction is sequential under the probe's single coordinator slot, verified by thread-count assertion (not just import absence).

## Acceptance criteria

- [ ] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` defines `class TreeSitterImportGraphProbe(Probe)` with `list[str]` class attributes: `name="tree_sitter_import_graph"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=120`, `cache_strategy: Literal["content"] = "content"`. `declared_inputs` includes `["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "tools/grammars.lock"]` (the lock-file is part of the cache key — a grammar version bump invalidates). The decorator is `@register_probe(heaviness="medium")`.

- [ ] **AC-2 — Grammar BLAKE3 pin verified at load time, before any code runs.** A pure helper `_load_grammar(language: Literal["typescript","javascript"]) -> tree_sitter.Language`:
  1. Reads `tools/grammars.lock` (via `safe_yaml.load` — Phase 1 chokepoint).
  2. Finds the entry for `language`.
  3. Computes `blake3.blake3(Path(entry.file).read_bytes()).hexdigest()` and compares **byte-for-byte** to `entry.blake3`.
  4. **On mismatch:** raises `GrammarLoadRefused(language=language, expected_blake3=entry.blake3, actual_blake3=computed)`. No `tree_sitter.Language(...)` constructor is called — no grammar code executes.
  5. **On match:** calls `tree_sitter.Language(entry.file, language)` and returns the `Language` object.
  6. **Result is process-cached** — the same `Language` is reused across files within one process; never re-verified per file (re-verification per file is the kind of "defensive over-engineering" Rule 2 forbids; the trust boundary is process startup).

- [ ] **AC-3 — `GrammarLoadRefused` is typed and contained.** Defined in `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` (or a nested `_errors.py`):
  ```python
  class GrammarLoadRefused(Exception):
      def __init__(self, language: str, expected_blake3: str, actual_blake3: str) -> None:
          super().__init__(f"BLAKE3 mismatch for {language} grammar: expected {expected_blake3}, got {actual_blake3}")
          self.language = language
          self.expected_blake3 = expected_blake3
          self.actual_blake3 = actual_blake3
  ```
  The probe's `run` catches `GrammarLoadRefused`, emits slice with `confidence="low"`, `error_id="grammar_pin_mismatch"`, `warnings=["tree_sitter.grammar_pin_mismatch"]`, AND `import_edges_count=0`, AND writes NO `import-graph.json` (the file is absent or empty, never partially populated).

- [ ] **AC-4 — No internal `ThreadPoolExecutor` (verified by thread-count, NOT just by import absence).** The probe's module has no `import threading`, no `from concurrent.futures import ThreadPoolExecutor`, no `multiprocessing.Pool` (verified by AST walk in T-05). **Additionally** (the load-bearing assertion per the manifest risk callout), a runtime test (T-06) wraps `run()` in `threading.enumerate()` before/after captures and asserts `len(threads_after) - len(threads_before) == 0`. **A future refactor that uses `asyncio.gather(*[parse_file(f) for f in files])` would NOT trigger thread creation but would still violate the discipline** — so T-07 separately AST-walks the module and asserts no `await asyncio.gather`, no `await asyncio.wait_for` over a list of coroutines (the `wait_for` arming the `timeout_s` budget is admissible; the parallelism shape is what's forbidden). The probe processes files in a `for file in indexable_files: ...` loop, one at a time, awaiting nothing inside the loop body except the path I/O.

- [ ] **AC-5 — Per-file extraction emits forward-only adjacency.** For each TypeScript/JavaScript file, the probe parses the file via `tree_sitter.Parser(language=ts_or_js)`, walks the AST with a tree-sitter Query, and extracts every `import X from "..."` (ES module) and `require(...)` (CommonJS). Output shape:
  ```json
  {
    "schema_version": 1,
    "edges": [
      {"from": "src/index.ts", "to": "lodash"},
      {"from": "src/index.ts", "to": "./utils"},
      ...
    ]
  }
  ```
  Forward-only — no reverse adjacency in Phase 2 (Phase 3's `ImportGraphAdapter` builds it). `to` values are emitted verbatim from the source (string literal as it appears in the import statement — `"./utils"`, `"lodash"`, `"@scope/pkg"`, etc.). No resolution to filesystem paths — that's Phase 3 adapter territory.

- [ ] **AC-6 — `import-graph.json` schema_version + valid JSON.** The artifact has top-level `{"schema_version": 1, "edges": [...]}`. A unit test (`test_import_graph_json_well_formed`) validates the artifact against a small Pydantic model. `schema_version: 1` is the current value; future shape changes bump and add a Phase-N ADR.

- [ ] **AC-7 — Slice summary fields.** The `import_graph` slice contains:
  - `files_with_imports: int` (count of source files where ≥ 1 edge was emitted).
  - `total_edges: int`.
  - `confidence: Literal["high","medium","low"]` — `"high"` on a clean run, `"medium"` if any file failed to parse but ≥ 50% succeeded, `"low"` if `<50%` succeeded OR `GrammarLoadRefused` fired.
  - `parsed_files: int`, `failed_files: int` (the denominator + numerator of the confidence ratio).
  - `import_graph_uri: str` (`".codegenie/context/raw/import-graph.json"` — relative path).
  - `grammar_versions: dict[str, str]` — `{"typescript": "0.20.6", "javascript": "0.20.4"}` from `tools/grammars.lock`; provenance.

- [ ] **AC-8 — Per-file parse failure is contained.** If `tree_sitter.Parser.parse(bytes)` raises or produces a tree with `has_error=True`, the file is skipped (`failed_files += 1`); no edges emitted from it; `warnings.append("tree_sitter.file_parse_failed")` with a count cap (≤ 5 warnings — past 5, increment an internal counter and emit one summary `tree_sitter.parse_failed_count=N` warning). The probe does NOT raise. **A future refactor that adds `pytest.raises(SyntaxError)` here would defeat the discipline** — failure containment is the contract.

- [ ] **AC-9 — Confidence semantics per AC-7 are NOT silently `"high"`-on-empty-repo.** If `parsed_files == 0` AND `failed_files == 0` (an empty repo or one with zero `.ts`/`.js` files), `confidence="low"`, `warnings.append("tree_sitter.no_files_to_parse")`. Without this guard, an empty repo would pass through with `confidence="high"` — the silent-confidence failure mode B2 exists to prevent. T-09 exercises this.

- [ ] **AC-10 — `confidence="low"` slice on `GrammarLoadRefused`.** Per AC-3. No `import-graph.json` is written. The slice contains `files_with_imports=0`, `total_edges=0`, `parsed_files=0`, `failed_files=0`, `confidence="low"`, `errors=["tree_sitter.grammar_pin_mismatch"]`. T-10 monkeypatches `_load_grammar` to raise `GrammarLoadRefused` and asserts the slice shape end-to-end.

- [ ] **AC-11 — Warning + error ID frozenset + import-time assertion.** All IDs (`tree_sitter.grammar_pin_mismatch`, `tree_sitter.file_parse_failed`, `tree_sitter.parse_failed_count`, `tree_sitter.no_files_to_parse`) are declared in a module-level `_WARNING_IDS` / `_ERROR_IDS` frozenset. Import-time `assert` verifies each matches the Phase 1 ADR-0007 regex.

- [ ] **AC-12 — Timeout containment via `asyncio.wait_for`.** The probe's `run()` is `await asyncio.wait_for(self._parse_all(...), timeout=self.timeout_seconds)`. **The `wait_for` is the ONLY admissible asyncio-coordination primitive** — `asyncio.gather` over a list of coroutines is forbidden (AC-4). On `asyncio.TimeoutError`, the slice contains whatever partial state was accumulated up to the timeout point AND `confidence="low"`, `warnings=["tree_sitter.timeout"]`. The artifact `import-graph.json` is written with the partial edges (or omitted if no edges were collected); a partial graph is better than no graph for Phase 3 fallback — UNLIKE `ScipIndexProbe` (S4-03 AC-6 where partial blobs are deleted) — because the JSON is parseable as a partial list (Phase 3 reads it with confidence-informed degradation).

- [ ] **AC-13 — Registry membership + `for_task` filter.** `src/codegenie/probes/__init__.py` imports `TreeSitterImportGraphProbe` via an explicit additive line. `default_registry.all_probes()` includes it with `heaviness="medium"`. `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it; non-Node languages skip.

- [ ] **AC-14 — `pyproject.toml` `gather` extras gains `py-tree-sitter`** ([ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md)). The `gather` extras section lists `py-tree-sitter` exactly once with a `~=` minor-pin (e.g., `py-tree-sitter ~= 0.21`). `pip-audit` and `osv-scanner` (Phase 0 dep-watch tooling) continue to scan it. A unit test (`test_pyproject_lists_py_tree_sitter_in_gather_extras`) reads `pyproject.toml` and asserts the entry.

- [ ] **AC-15 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/layer_b/tree_sitter_import_graph.py`, `pytest tests/unit/probes/layer_b/test_tree_sitter_import_graph.py`. All green.

## Implementation outline

1. **Create `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`** with class per AC-1.

2. **`GrammarLoadRefused` exception class** (AC-3).

3. **`_load_grammar(language) -> tree_sitter.Language` (AC-2).** Process-level memo (`functools.lru_cache(maxsize=4)`); reads `tools/grammars.lock` exactly once; verifies BLAKE3 before constructing `tree_sitter.Language`. Tested in T-02/T-03.

4. **`_extract_imports_from_file(path: Path, language: tree_sitter.Language) -> list[Edge]` (pure-ish — does I/O on `path`, then pure parse).** Reads bytes; parses; walks AST with a tree-sitter Query targeting `import_statement` and `call_expression` nodes (with `require` callee); emits `Edge(from_=relative_path, to=specifier)` for each hit. Returns `[]` and increments external `failed_files` counter on `parse error`/`has_error` (signaled by raising `_PerFileParseFailed` caught by the loop).

5. **`async def _parse_all(self, ctx) -> tuple[list[Edge], int, int]`** — the sequential loop:
   ```python
   edges: list[Edge] = []
   parsed = 0; failed = 0
   for file in _enumerate_indexable_files(ctx.snapshot.root):
       try:
           file_edges = _extract_imports_from_file(file, language)
           edges.extend(file_edges); parsed += 1
       except _PerFileParseFailed:
           failed += 1
   return edges, parsed, failed
   ```

6. **`async def run(self, ctx) -> ProbeOutput`** — wraps `_parse_all` in `asyncio.wait_for(..., self.timeout_seconds)`; handles `GrammarLoadRefused` and `asyncio.TimeoutError` per AC-10/AC-12; writes `import-graph.json`; emits slice.

7. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

8. **Add `py-tree-sitter` to `pyproject.toml`'s `[project.optional-dependencies] gather` list** (AC-14).

## TDD plan — red / green / refactor

### Test helpers preamble

```python
# tests/unit/probes/layer_b/test_tree_sitter_import_graph.py
from __future__ import annotations
import ast, asyncio, json, threading
from pathlib import Path
import pytest
from codegenie.probes.layer_b.tree_sitter_import_graph import (
    TreeSitterImportGraphProbe, GrammarLoadRefused, _load_grammar,
)
```

### RED

- **T-01** `test_probe_contract_attributes`: AC-1.
- **T-02** `test_grammar_pin_match_loads_language`: AC-2 happy path — vendored binary's BLAKE3 matches; `_load_grammar("typescript")` returns a `tree_sitter.Language`.
- **T-03** `test_grammar_pin_mismatch_refuses_load` (AC-3): monkeypatch `tools/grammars.lock` entry to a wrong BLAKE3; `_load_grammar("typescript")` raises `GrammarLoadRefused`. Critical sub-assertion: `tree_sitter.Language(...)` is NOT called (spy via monkeypatch on `tree_sitter.Language`).
- **T-04** `test_grammar_pin_mismatch_grammar_code_does_not_execute` (AC-3): stronger version of T-03 — assert no entry in `sys.modules` for `tree_sitter._binding` (or whatever C-extension loader hooks fire); ensures the mismatch path short-circuits before any grammar code runs.
- **T-05** `test_no_thread_pool_executor_import` (AC-4): AST-walk the module; assert no `threading`, no `concurrent.futures`, no `multiprocessing` import names appear.
- **T-06** `test_no_threads_created_during_run` (AC-4 — the load-bearing thread-count assertion): capture `threading.enumerate()` before `asyncio.run(probe.run(ctx))`; capture after; assert `len(threads_after) == len(threads_before)`. (Tree-sitter's C library may use threads internally — if it does, the test must distinguish "library-internal threads we don't own" from "probe-spawned threads"; the safest assertion is "no threads created by Python code in this probe.")
- **T-07** `test_no_asyncio_gather_over_files` (AC-4): AST-walk; assert no `await asyncio.gather` invocation whose argument is a list comprehension over a file iterator.
- **T-08** `test_per_file_parse_failure_contained` (AC-8): create a fixture with one valid `.ts` file and one syntactically-invalid `.ts` file; assert `parsed_files==1`, `failed_files==1`, slice contains `"tree_sitter.file_parse_failed"` warning, probe returns success.
- **T-09** `test_no_files_to_parse_is_low_confidence` (AC-9): empty repo (no `.ts`/`.js`); assert `confidence="low"`, `warnings == ["tree_sitter.no_files_to_parse"]`.
- **T-10** `test_grammar_load_refused_full_slice` (AC-10): monkeypatch `_load_grammar` to raise `GrammarLoadRefused`; assert slice fields per AC-10; assert `import-graph.json` does NOT exist on disk.
- **T-11** `test_forward_only_adjacency_shape` (AC-5/AC-6): create a fixture with `src/index.ts` importing `lodash` and `./utils`; run probe; load `import-graph.json`; assert exact shape `{"schema_version": 1, "edges": [{"from": "src/index.ts", "to": "lodash"}, {"from": "src/index.ts", "to": "./utils"}]}`.
- **T-12** `test_slice_summary_fields` (AC-7): assert every field present per spec.
- **T-13** `test_timeout_contained_partial_graph_written` (AC-12): monkeypatch `_parse_all` to await an unsignalled future; `timeout_seconds=1`; assert `asyncio.TimeoutError` does NOT propagate; `confidence="low"`, `warnings=["tree_sitter.timeout"]`.
- **T-14** `test_warning_error_ids_match_adr_0007` (AC-11).
- **T-15** `test_registry_membership_heaviness_medium` (AC-13).
- **T-16** `test_pyproject_lists_py_tree_sitter_in_gather_extras` (AC-14).

### GREEN

Implement the module per outline. Source the tree-sitter Query strings from the tree-sitter-typescript and tree-sitter-javascript README query examples (the import-extraction queries are stable across recent grammar versions; bundle them in `_TS_IMPORT_QUERY` and `_JS_IMPORT_QUERY` module constants).

### REFACTOR

- Extract `_enumerate_indexable_files` to share with S4-03 (or import from there — Rule 11 — match codebase convention).
- Confirm `mypy --strict` passes; tree-sitter's stubs may need a `# type: ignore[import-untyped]` on the `import tree_sitter` line with a TODO referencing the upstream stubs issue (loud, not silent).
- Verify the structured-log event includes `parsed_files`, `failed_files`, `total_edges`, `grammar_versions` for ops observability.

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`
- `tests/unit/probes/layer_b/test_tree_sitter_import_graph.py`

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — additive import.
- `pyproject.toml` — `[project.optional-dependencies] gather` adds `py-tree-sitter ~= 0.21`.

**Pre-existing (from S4-03):**
- `tools/grammars.lock`, `tools/grammars/typescript.so`, `tools/grammars/javascript.so` — consumed by `_load_grammar`.

## Out of scope

- **Reverse adjacency / `ImportGraphAdapter`.** Phase 3 plugin owns reverse lookups. This story emits forward-only.
- **Symbol-level resolution.** SCIP (S4-03) is the symbol-level layer; tree-sitter is statement-level.
- **Dynamic `import("./" + name)` resolution.** Forward-only emission records the literal specifier as-emitted in source; if the source has `import(specifier)` where `specifier` is a variable, the probe emits `to: "<dynamic>"` placeholder OR omits (implementer choice — recommend omit, and let `NodeReflectionProbe` (out of scope for this probe; it's S5-/B3 territory if a Phase-3 reflection probe is needed) handle dynamic patterns).
- **Other languages.** TypeScript + JavaScript are Phase-2-required. Python / Go / Java grammars are Phase-8+ ADR-amendments to ADR-0002.
- **Out-of-process `_grammar_runner`** — explicitly rejected by [ADR-0002 §Decision](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md). Do NOT propose subprocess isolation; the grammar pin is the supply-chain defense.
- **Re-verification per file.** AC-2 explicitly says the BLAKE3 is verified at process startup, not per file. A future contributor proposing "re-verify per file for safety" is to be redirected here — the trust boundary is the process.

## Notes for the implementer

- **The thread-count test (T-06) is the load-bearing one.** The manifest's risk callout for this story: "verify by enumerating thread count, not just by absence of `threading` import." A future contributor could (a) import `asyncio` (admissible), (b) use `loop.run_in_executor(None, ...)` to spawn threads from the default executor, (c) violate the discipline without importing `threading` directly. T-06 catches (b) — `threading.enumerate()` sees the executor's threads. If the test starts to flake because tree-sitter's C library spawns threads we don't own, scope the assertion to "no threads spawned by `codegenie.probes.layer_b.tree_sitter_import_graph`" via `inspect`-stack filtering, BUT only after confirming with logs that the new threads are upstream-tree-sitter and not ours.
- **`_load_grammar` is process-cached via `lru_cache`.** Once per process, never per file. Rule 2 — simplicity first. Per-file BLAKE3 re-verification would be the kind of "defensive over-engineering" that adds cost without changing the threat model.
- **Vendored grammar paths are relative.** `tools/grammars/typescript.so` is the literal path in `tools/grammars.lock`. The path is resolved relative to the repo root at probe load time (NOT the snapshot root of the analyzed repo — the grammars belong to `codewizard-sherpa` itself, not the analyzed repo). A test fixture asserts this: a fixture-mode analyzed repo at `tests/fixtures/portfolio/minimal-ts/` resolves `tools/grammars.lock` to `<codewizard-sherpa-repo-root>/tools/grammars.lock`, NOT `<fixture>/tools/grammars.lock`.
- **The `py-tree-sitter` API.** Modern `py-tree-sitter` (≥ 0.21) uses `tree_sitter.Language(path, name)` for loading; older versions used `Language.build_library(...)`. Pin to a modern minor version (`~= 0.21`) so the import idiom is stable.
- **Tree-sitter Query language.** The probe uses tree-sitter Queries (S-expression syntax) to match import patterns. For TypeScript: `(import_statement source: (string) @specifier)` and similar; for require: `(call_expression function: (identifier) @func arguments: (arguments (string) @specifier) (#eq? @func "require"))`. Bundle the queries as module constants and document them inline — Rule 11 — match codebase convention, which means readable inline patterns over a vendored `.scm` query file (Phase 2 only needs ~6 query patterns).
- **The "loudness is a feature" framing.** [ADR-0002 §Tradeoffs](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — "A crashed grammar crashes the gather process; Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`, and the loudness is a feature." A grammar binary CVE or corruption is a real risk; the response is a CI failure (loud), not a silent skip. The `asyncio.wait_for` containment is what makes this safe — the worst case is the gather drops this one probe's output and continues.
- **Rule 9 — tests verify intent.** T-04 (grammar code does not execute on pin mismatch) encodes the WHY of the pin (supply-chain defense). T-06 (no threads created) encodes the WHY of the no-internal-pool rule (honesty to coordinator). T-13 (timeout writes partial graph) encodes the WHY of "partial-graph-is-better-than-no-graph" — distinct from S4-03 where partial blobs are deleted, because JSON degrades gracefully and `.scip` doesn't. Every test name and assertion message must point at WHICH discipline is being defended.
