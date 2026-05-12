# Story S4-02 — `NodeReflectionProbe` + tree-sitter query pack + per-file cache key

**Step:** Step 4 — Ship Layer B remainder (`SCIPIndexProbe`, `NodeReflectionProbe`, `GeneratedCodeProbe`)
**Status:** Ready
**Effort:** M
**Depends on:** S1-07 (`tools.treesitter.query` in-process wrapper), S2-07 (`SCHEMA-EVOLUTION-POLICY.md`)
**ADRs honored:** ADR-0004 (`tools/digests.yaml` cache-key inclusion — grammar SHA), ADR-0003 (no subprocess; in-process bindings; no new sandbox routing needed), ADR-0006 (sanitizer Pass 4/5 idempotence on slice; tree-sitter findings carry file paths only, no raw content)

## Context

`NodeReflectionProbe` (B3) is the deterministic complement to SCIP: tree-sitter parses TypeScript / JavaScript ASTs in-process and surfaces the dynamic-dispatch patterns SCIP can't statically resolve — `eval(...)`, `new Function(...)`, `Reflect.get/set/apply`, dynamic `require()` / `import()`, decorator presence, middleware-chain shapes, env-var-gated branches. These markers tell the Planner "SCIP coverage is incomplete *here* for a known reason" rather than leaving silent gaps.

This story establishes two contracts the rest of Phase 2 depends on: (1) the **pinned tree-sitter query pack** at `src/codegenie/probes/_reflection_queries/node.yaml` (declarative YAML; extensible by addition; loaded once at probe registration); (2) the **per-file findings cache key shape** `(file_content_blake3, grammar_version)` and the on-disk layout `.codegenie/cache/tree-sitter/by-file/<blake3>.<grammar_version>.msgpack`. The per-file cache **module** lands in S7-01 (semgrep + gitleaks reuse it); this story declares the on-disk shape so S7-01 is a mechanical extraction, not a redesign. The grammar version digest flows through the cache key from `tools/digests.yaml`#grammars — a wheel upgrade invalidates only the affected files (per-file BLAKE3 + grammar SHA = key).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #19 Tree-sitter wrapper` — in-process bindings, per-file cache layout, 5 s per-file hard cap, grammar pin.
  - `../phase-arch-design.md §"Component design" #17 Per-file findings cache + .codegenie/index/` — on-disk layout under `.codegenie/cache/tree-sitter/by-file/`.
  - `../phase-arch-design.md §"Logical view"` — `NodeReflectionProbe --> ToolsPackage : tools.treesitter.query`.
  - `../phase-arch-design.md §"Development view"` — `probes/_reflection_queries/node.yaml` data file location.
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — tree-sitter grammar wheel hashes pinned; grammar version participates in this probe's cache key.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — slice carries no raw file content, only paths + symbolic markers; Pass 4 idempotence preserved.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — explicitly noted in S1-07 that tree-sitter is in-process; this probe inherits.
- **Source design:**
  - `../final-design.md §"Components" §3.3 NodeReflectionProbe (B3)` — provenance `[P]`; tree-sitter at ~10k LOC/s; per-file caching saves redundant cost on incremental gathers.
  - `../final-design.md §"Synthesis ledger" row D14` — per-file findings sub-cache adopted; cap by access-time LRU; cross-file taint bypass documented.
- **Existing code (Steps 1–3 output):**
  - `src/codegenie/tools/treesitter.py` (S1-07) — `async query(file_paths: Sequence[Path], *, grammar: Literal["typescript","javascript","tsx"], query_pack: Path, timeout_s: float = 5.0) -> TreesitterResult`; surfaces `tool_digest` (grammar SHA) from `tools/digests.yaml`.
  - `src/codegenie/probes/base.py` — `Probe` ABC.
  - `src/codegenie/probes/__init__.py` — additive registration.
  - `src/codegenie/errors.py` — `ToolOutputMalformed`, `ToolTimeout`, `SizeCapExceeded`.
  - `src/codegenie/coordinator/cache_key.py` (S2-06) — `sub_schema_version` already participates; this story adds per-file-cache shape but **not yet** the cache module (S7-01).
- **External:**
  - `tree-sitter-typescript` Query DSL: `https://tree-sitter.github.io/tree-sitter/using-parsers#pattern-matching-with-queries` — for authoring `node.yaml` patterns.

## Goal

Ship a deterministic in-process `NodeReflectionProbe` that consumes the pinned `node.yaml` tree-sitter query pack via `tools.treesitter.query`, emits reflection metadata (per call site: file path, line, marker class), establishes the per-file findings cache on-disk shape `(file_blake3, grammar_version).msgpack`, and validates an `additionalProperties: false` slice.

## Acceptance criteria

- [ ] `src/codegenie/probes/node_reflection.py` exists, defines `class NodeReflectionProbe(Probe)`, sets `name = "node_reflection"`, `layer = "B"`, `applies_to_languages = ["typescript","javascript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection","node_build_system"]`, `timeout_seconds = 60`, `version: str = "1.0.0"`, `consumes_peer_outputs = False`, and `declared_inputs` including `"src/**/*.{ts,tsx,mts,cts,js,mjs,cjs}"` **plus** `"src/codegenie/probes/_reflection_queries/node.yaml"` **plus** `"src/codegenie/catalogs/tools/digests.yaml"` so a query-pack edit or grammar digest change invalidates the slice cache.
- [ ] `src/codegenie/probes/_reflection_queries/node.yaml` exists, pinned (under `CODEOWNERS` review), declares `schema_version: "v1"`, lists at minimum the five canonical reflection markers: `eval_call`, `new_function`, `reflect_call` (covers `Reflect.get/set/apply/has/ownKeys/etc.`), `dynamic_require`, `dynamic_import`. Each entry: `{name: str, grammar: enum("typescript","javascript","tsx"), query: str}`. Loaded once at probe instantiation, `MappingProxyType`-wrapped. Malformed YAML → `CatalogLoadError`, CLI exits 2.
- [ ] `src/codegenie/schema/probes/node_reflection.schema.json` ships Draft 2020-12, declares `schema_version: "v1"`, `additionalProperties: false` at root and every nested object. Slice shape: `call_sites: array<{file: string, line: int, column: int, marker: enum(...), grammar: enum(...)}>`, `files_scanned: int`, `files_cache_hit: int`, `files_cache_miss: int`, `tool_digest: string`, `query_pack_sha: string`, `confidence: enum("high","medium","low")`, `warnings: array(WarningId-pattern strings)`, `errors: array(string)`.
- [ ] `src/codegenie/probes/__init__.py` adds **one** additive import line registering `NodeReflectionProbe`.
- [ ] **Per-file cache on-disk shape is declared** by this story: `.codegenie/cache/tree-sitter/by-file/<file_blake3>.<grammar_version>.msgpack`. The probe writes to this layout directly (with atomic `tempfile.NamedTemporaryFile` + `os.replace`) — the **cache module abstraction** (S7-01) wraps this in Step 7. A module-level constant `_CACHE_LAYOUT_V1 = "by-file"` documents the shape; S7-01 reads it.
- [ ] Per-file cache **hit** path: on second run with unchanged file content + unchanged grammar version, no `tools.treesitter.query` call for that file (verified by mock-counter assertion in the test).
- [ ] Per-file cache **miss** path: file content changed → BLAKE3 changes → cache key changes → wrapper re-invoked for that file only (other files still hit).
- [ ] Hard cap honored: `tools.treesitter.query(..., timeout_s=5.0)` per file; on timeout the probe records `confidence: low` for that file's findings (preserves per-file granularity) and continues; warning `node_reflection.parse_timeout`.
- [ ] `tests/unit/probes/test_node_reflection.py` red test exists and is now green: (a) fixture with one `.ts` file containing `eval('foo')`, `new Function('x','return x')`, `Reflect.get(o, 'k')`, `require(dynamicName)`, `import(path)` → all five markers detected with correct file/line; (b) cache hit on second run (mock asserts `tools.treesitter.query.call_count == 0` for the unchanged file); (c) cache miss after content edit (wrapper re-invoked); (d) wrapper raises `ToolOutputMalformed` for one file → `confidence: low` for that file's findings; gather continues for other files; (e) wrapper raises `ToolTimeout` → warning `node_reflection.parse_timeout`, file's findings absent, slice still emitted; (f) JS file (`.mjs`) parses with `grammar: "javascript"`; (g) TSX file (`.tsx`) parses with `grammar: "tsx"`.
- [ ] `tests/unit/probes/test_node_reflection_schema.py` (or section in `test_node_reflection.py`): extra-field rejection — synthetic envelope with `probes.node_reflection.unknown_field: 1` fails `SchemaValidator` with a JSON Pointer referencing the unknown field.
- [ ] `tests/unit/probes/test_node_reflection_cache_layout.py`: asserts the on-disk file appears at exactly `.codegenie/cache/tree-sitter/by-file/<blake3>.<grammar_version>.msgpack` (regex pattern check) and is `msgpack`-deserializable; `S7-01` later extracts the read/write into a module.
- [ ] Definition-of-done items hold: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/probes/test_node_reflection*.py -q` all pass. Per-probe local coverage reported in the PR body (floor: 90 line / 80 branch).
- [ ] The slice round-trips through `OutputSanitizer` Passes 1–5 idempotently. The `call_sites` array carries no raw match strings — only structural marker classes — so Pass 4 has nothing to fingerprint and Pass 5 has no >256-char strings to scan.

## Implementation outline

1. **Author `node.yaml` first.** `src/codegenie/probes/_reflection_queries/node.yaml`. Open with `schema_version: "v1"`. Five canonical entries: `eval_call`, `new_function`, `reflect_call`, `dynamic_require`, `dynamic_import`. Each `query:` is a tree-sitter S-expression pattern. Validate by hand against `tree-sitter-typescript` and `tree-sitter-javascript` playground.
2. **Sub-schema.** Write `src/codegenie/schema/probes/node_reflection.schema.json` per Acceptance criterion 3. Cross-link to `SCHEMA-EVOLUTION-POLICY.md`. `additionalProperties: false` at every nesting level.
3. **Probe implementation.** `src/codegenie/probes/node_reflection.py`:
   - **At instantiation**, load `node.yaml` via `safe_yaml.load`; compute `query_pack_sha = blake3(yaml_bytes).hexdigest()`; cache the parsed mapping in a `MappingProxyType`.
   - **In `run(snapshot, ctx)`:**
     - Enumerate files matching `declared_inputs` globs under `snapshot.root`. Classify each by grammar via extension (`.ts → typescript`, `.tsx → tsx`, `.mts/.cts → typescript`, `.js/.mjs/.cjs → javascript`).
     - For each file: compute `file_blake3 = blake3(file_bytes).hexdigest()`; compute `grammar_version = tools.treesitter.GRAMMARS[grammar].version` (surfaced from S1-07; itself rooted in `tools/digests.yaml`#grammars); construct `cache_path = snapshot.root / ".codegenie" / "cache" / "tree-sitter" / "by-file" / f"{file_blake3}.{grammar_version}.msgpack"`.
     - **Cache check:** if `cache_path.exists()`, read it; `msgpack.unpackb(...)`; append its `call_sites` to the slice's `call_sites`; increment `files_cache_hit`.
     - **Cache miss:** call `tools.treesitter.query(file_paths=[file], grammar=grammar, query_pack=NODE_YAML_PATH, timeout_s=5.0)`. Map result to `call_sites` records. Write `cache_path` atomically (`tempfile.NamedTemporaryFile(dir=cache_path.parent, delete=False)` → `os.replace`). Increment `files_cache_miss`.
   - **Confidence ladder:**
     - `high` — all scanned files parsed without timeout / malformed errors.
     - `medium` — one or more files timed out or hit a per-file cap (`scanned > 0 and timeouts > 0`).
     - `low` — wrapper raised `ToolOutputMalformed` (grammar version mismatch — adversarial) for ≥ 1 file, or zero files scanned (no TS/JS in repo despite `applies_to_languages` matching).
4. **Failure handling.** Per-file failures isolate (caught into a typed warning, file's findings absent, gather continues for other files). Wrapper-level failures (e.g., grammar load) propagate as `confidence: low` for the whole slice. Warning IDs: `node_reflection.parse_timeout`, `node_reflection.parse_malformed`, `node_reflection.size_cap`, `node_reflection.cache_corruption`.
5. **Atomic cache write.** Use `tempfile.NamedTemporaryFile(dir=cache_path.parent, delete=False)`, `msgpack.packb` the per-file findings, `os.replace(tmp, cache_path)`. On read, verify msgpack deserializability — corruption (truncated, byte-flipped) → delete the bad blob + treat as miss + warning `node_reflection.cache_corruption` (mirrors Phase 2 #17's BLAKE3-integrity discipline; the BLAKE3 *is* the key, so re-deserialization is the integrity proxy here).
6. **Register** in `src/codegenie/probes/__init__.py` (one additive import). Add `node_reflection` to envelope `$ref` composition (optional).
7. **Cache-key participation.** The probe's `sub_schema_version` already flows through S2-06; this story additionally surfaces `query_pack_sha` and the wrapper's `tool_digest` (grammar SHA) into the per-probe blob cache key — additive to S2-06's composition.

## TDD plan — red / green / refactor

### Red — failing test first

Path: `tests/unit/probes/test_node_reflection.py`

```python
"""Pins: NodeReflectionProbe detects the five canonical reflection markers via the pinned
node.yaml query pack; per-file cache hits on unchanged files; per-file cache misses after
content edit; per-file timeout isolates to confidence: medium without failing the slice.
Traces to: phase-arch-design.md §Component design #17 + #19; ADR-0004."""

import pytest
from pathlib import Path
from unittest.mock import patch
from codegenie.probes.node_reflection import NodeReflectionProbe

@pytest.mark.asyncio
async def test_five_canonical_markers_detected(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    (src / "a.ts").write_text(
        "eval('1');\n"
        "const F = new Function('x','return x');\n"
        "Reflect.get({}, 'k');\n"
        "const n = 'd'; require(n);\n"
        "import(n);\n"
    )
    out = await NodeReflectionProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    markers = {cs["marker"] for cs in out.schema_slice["call_sites"]}
    assert {"eval_call","new_function","reflect_call","dynamic_require","dynamic_import"} <= markers
    assert out.confidence == "high"

@pytest.mark.asyncio
async def test_cache_hit_on_second_run_no_wrapper_call(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    (src / "a.ts").write_text("eval('1');\n")
    probe = NodeReflectionProbe()
    await probe.run(_snapshot(tmp_path), _ctx(tmp_path))  # warm
    with patch("codegenie.tools.treesitter.query", side_effect=AssertionError("must not be called")) as mock:
        out = await probe.run(_snapshot(tmp_path), _ctx(tmp_path))
        assert mock.call_count == 0  # full cache hit
    assert out.schema_slice["files_cache_hit"] == 1
    assert out.schema_slice["files_cache_miss"] == 0

@pytest.mark.asyncio
async def test_cache_miss_after_content_edit(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    f = src / "a.ts"; f.write_text("eval('1');\n")
    probe = NodeReflectionProbe()
    await probe.run(_snapshot(tmp_path), _ctx(tmp_path))
    f.write_text("new Function('x');\n")  # different BLAKE3
    out = await probe.run(_snapshot(tmp_path), _ctx(tmp_path))
    assert out.schema_slice["files_cache_miss"] == 1

@pytest.mark.asyncio
async def test_per_file_timeout_isolates(tmp_path, monkeypatch):
    from codegenie.errors import ToolTimeout
    src = tmp_path / "src"; src.mkdir()
    (src / "a.ts").write_text("eval('1');\n")
    (src / "b.ts").write_text("new Function('x');\n")
    async def _flaky(file_paths, **kw):
        if "a.ts" in str(file_paths[0]): raise ToolTimeout("tree-sitter")
        return _ok_result()
    monkeypatch.setattr("codegenie.tools.treesitter.query", _flaky)
    out = await NodeReflectionProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    assert "node_reflection.parse_timeout" in out.schema_slice["warnings"]
    assert out.confidence == "medium"

def test_cache_path_layout(tmp_path):
    """Pins on-disk shape: <blake3>.<grammar_version>.msgpack under cache/tree-sitter/by-file/."""
    import re
    src = tmp_path / "src"; src.mkdir()
    (src / "a.ts").write_text("eval('1');\n")
    asyncio_run(NodeReflectionProbe().run(_snapshot(tmp_path), _ctx(tmp_path)))
    by_file = tmp_path / ".codegenie" / "cache" / "tree-sitter" / "by-file"
    files = list(by_file.glob("*.msgpack"))
    assert len(files) == 1
    assert re.match(r"^[0-9a-f]{64}\.\d+\.msgpack$", files[0].name)
```

Path: `tests/unit/probes/test_node_reflection_schema.py`

```python
def test_subschema_rejects_unknown_field():
    from codegenie.coordinator.schema_validator import SchemaValidator
    envelope = {"probes": {"node_reflection": {"call_sites": [], "unknown_field": 1}}}
    with pytest.raises(Exception) as ei:
        SchemaValidator().validate(envelope)
    assert "unknown_field" in str(ei.value)
```

Run `pytest tests/unit/probes/test_node_reflection*.py -q`. All red (probe / query pack / schema don't exist yet).

### Green — smallest impl shape

1. Author `_reflection_queries/node.yaml` with the five entries.
2. Write `node_reflection.schema.json`.
3. Write `node_reflection.py` per **Implementation outline**.
4. Register; wire schema $ref.
5. Iterate to green.

### Refactor — bounded

- Extract `_load_query_pack() -> Mapping` to a module-level cached function (`functools.cache`) — one parse per process lifetime.
- Extract `_per_file_cache_path(snapshot_root, file_blake3, grammar_version) -> Path` to a module-level pure helper — S7-01 will lift this into the cache module verbatim.
- Module-level constants for warning IDs.
- Run `ruff format`, `ruff check`, `mypy --strict`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/node_reflection.py` | New — `NodeReflectionProbe` implementation |
| `src/codegenie/probes/_reflection_queries/node.yaml` | New — pinned tree-sitter query pack (CODEOWNERS review) |
| `src/codegenie/schema/probes/node_reflection.schema.json` | New — `additionalProperties: false`, `schema_version: "v1"` |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.node_reflection` (optional) |
| `tests/unit/probes/test_node_reflection.py` | New — markers, cache hit/miss, per-file timeout isolation |
| `tests/unit/probes/test_node_reflection_schema.py` | New — extra-field rejection unit test |
| `tests/unit/probes/test_node_reflection_cache_layout.py` | New — on-disk shape regex assertion |
| `tests/fixtures/node_reflection/` (or inline `tmp_path`) | Optional — minimal `.ts` / `.mjs` / `.tsx` fixtures |

## Out of scope

- **The per-file findings cache module** — handled by S7-01 (`src/codegenie/cache/per_file.py` or similar). This story declares the on-disk shape so S7-01's module is a mechanical extraction.
- **Grammar version mismatch adversarial fixture** — handled by `tests/adv/test_treesitter_grammar_version_mismatch.py` (S8-01 corpus completion, listed in `phase-arch-design.md`'s Step 4 done criteria but lands in S8-01).
- **SemgrepProbe / GitleaksProbe consumption of the per-file cache** — handled by S7-02 / S7-03, which read the same `.codegenie/cache/<tool>/by-file/` shape via S7-01's module.
- **Cross-file taint mode** — explicitly opt-in via `--paranoid` per `final-design.md §"Goals" #6`; bypasses this cache entirely. Not in scope.
- **`AstGrepProbe` reflection-marker overlap** — S7-04 handles AstGrep findings; the contract there is that NodeReflection's deterministic markers take precedence (documented in S7-04's references).
- **`GeneratedCodeProbe`'s use of tree-sitter** — handled by S4-03; that probe routes to tree-sitter only for *ambiguous* files (header-pattern miss).

## Notes for the implementer

- **The query pack is a catalog, not a code change.** Adding a sixth reflection marker (e.g., `webpack_require`, `process.binding`) is a YAML edit + a test; never a `node_reflection.py` edit. The probe walks the catalog; the catalog evolves under CODEOWNERS review.
- **Per-file cache writes must be atomic.** Two concurrent gathers on the same repo (legal even if rare) can race the same `cache_path`; `os.replace` is the atomic-rename primitive on POSIX. Never write directly to the final path.
- **Per-file BLAKE3 is the integrity proxy.** If the deserialized msgpack mismatches what was written, the BLAKE3 won't match the file content, so the *next* gather invalidates naturally. Don't add a redundant BLAKE3 over the msgpack value — keep the cache key the integrity check.
- **Grammar version comes from `tools/digests.yaml`#grammars.** Bumping the `tree-sitter-typescript` wheel without bumping the digest manifest fails the install gate (ADR-0004 + S1-08). The probe trusts the version surfaced by `tools.treesitter`; never read the wheel metadata directly here.
- **The slice carries no raw file content.** `call_sites[].marker` is a symbolic enum; line/column are integers; file is a relative path. Pass 4 (secret fingerprinter) has nothing to do; Pass 5 (prompt-injection marker) has nothing to scan. This is intentional and load-bearing for sanitizer idempotence.
- **Tree-sitter is in-process** per ADR-0003 / S1-07's documented exception. Do not route this probe's wrapper invocation through `run_in_sandbox`; the grammar wheels are the trust boundary, pinned by hash.
- **`applies_to_languages = ["typescript","javascript"]`** — the probe is a no-op on Python / Go / Java repos. Phase 2's extension-by-addition pattern means a future Python reflection probe is a *new* class (`PythonReflectionProbe`), not an edit here.
- A grep for `import requests`, `import httpx`, `import urllib3`, `import socket`, `subprocess` in `node_reflection.py` should return empty. Same import-linter rule as Phase 1.
- The five canonical markers are the minimum; the query pack is the extension point. If the reviewer asks "where's `with()`?" — answer: "extension by addition; file a `node.yaml` patch."
