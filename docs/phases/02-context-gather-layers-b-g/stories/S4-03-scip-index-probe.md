# Story S4-03 — `ScipIndexProbe` via `scip-typescript` + grammars-lock infrastructure

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** M
**Depends on:** S1-07 (`run_external_cli` on disk, `ALLOWED_BINARIES` extended with `scip-typescript` + `tree-sitter` + nine others), S1-08 (`@register_probe(heaviness="heavy")` registry annotation; coordinator dispatches heavy probes first)
**ADRs honored:** [`02-ADR-0001`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) (`scip-typescript` admissible only via `run_external_cli` → `run_allowlisted`), [`02-ADR-0002`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) (the `grammars.lock` infrastructure ships here, consumed in S4-04), [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (`heaviness="heavy"` is a registry annotation), [`02-ADR-0006`](../ADRs/0006-index-freshness-sum-type-location.md) (`IndexerError(message="timeout")` is the typed failure for `scip-typescript` timeout; B2 consumes), Phase 1 ADR-0004 (sub-schema lands in S4-07), Phase 1 ADR-0007 (warning ID pattern)

## Context

`ScipIndexProbe` produces the SCIP semantic index B2 reads to determine "is the index up-to-date with HEAD?" The probe invokes `scip-typescript` (the indexer; no compile required — reads `tsconfig.json` and runs the TypeScript compiler API), emits a `.scip` binary to `.codegenie/context/raw/scip-index.scip`, and reports a `semantic_index` slice with the index metadata B2's `scip` freshness check (S4-01 AC-5) reads.

**Phase 2 emits the binary only — the consumption shape is Phase 3's.** [Final-design §"Patterns rejected" #9 / Phase-3 deferral](../final-design.md): Phase 3's `ScipAdapter` (one of the four `Protocol`s shipped in S1-08) decides whether to mmap, re-parse, or pre-project the `.scip` blob. Phase 2 must not commit to a binary on-disk format (the performance lens's rejected `msgpack` proposal; [ADR-0002 §Decision](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md)). The probe's contract is "produce the blob; report metadata." Nothing more.

**Cache key sensitivity.** `declared_inputs` must capture (a) the tool version (running `scip-typescript --version`-equivalent at probe init, with the resolved version baked into the cache key), and (b) a Merkle hash over the set of `.ts`/`.tsx`/`.js`/`.jsx` files under the repo root (excluding `node_modules`, `dist`, `build`, and any path declared in `.codegenie/exclude.txt`). The Phase 0 cache layer (`src/codegenie/cache/`) computes content-addressed keys from `declared_inputs`; this probe's job is to declare the right inputs. A wrong Merkle (e.g., over ALL files rather than indexable ones) would over-invalidate; a wrong version anchor (e.g., omitting the tool version) would silently reuse a cache hit across `scip-typescript` upgrades.

**Timeout discipline.** SCIP indexing on a huge monorepo can blow past simple timeouts. The phase budget is **300 seconds** ([phase-arch-design.md §"Edge cases" row 4](../phase-arch-design.md)). On timeout, the probe surfaces a typed `IndexerError(message="timeout")` in the `semantic_index` slice's `indexer_errors` shape AND emits no blob; B2's `scip` freshness check (S4-01 AC-5e) sees `indexer_errors > 0` and emits `Stale(IndexerError(...))`. Phase 3's adapter falls back to tree-sitter per the ADR-0032 declared-fallback discipline.

**`grammars.lock` ships here, consumed in S4-04.** The Phase-2 tree-sitter integration ([ADR-0002](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md)) requires vendored grammar `.so`/`.dylib` artifacts pinned by BLAKE3 in `tools/grammars.lock`. The lock file + regeneration script are infrastructure both `ScipIndexProbe` (which uses `tree-sitter` for JavaScript files outside the TypeScript program; [localv2.md §5.2 B1](../../../localv2.md) line 563) and `TreeSitterImportGraphProbe` (S4-04) consume. Landing both lock + regenerate script in this story (rather than splitting) is a deliberate scope choice: S4-04's grammar-pin verification depends on the lock existing, so the lock must precede the consumer. The lock + regen script is "reviewed-as-code, vendored as data" (Rule 8 — read before you write; the grammar binaries are reviewed at PR time, not parsed by the implementer).

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #5`](../phase-arch-design.md) (Layer G scanner pattern — `run_external_cli`, ToolCache, Pydantic-parse-stdout — same shape applies here even though SCIP is Layer B).
  - [`../phase-arch-design.md §"Edge cases" row 4`](../phase-arch-design.md) — `scip-typescript` timeout → `IndexFreshness.Stale(reason=IndexerError(message="timeout"))`; Phase 3 adapter falls back.
  - [`../phase-arch-design.md §"Component design" #3`](../phase-arch-design.md) — `run_external_cli` signature (probe routes through this, not `run_allowlisted`).
  - [`../phase-arch-design.md §"Process view"`](../phase-arch-design.md) — heavy probes dispatched first under the single semaphore.
- **Phase 2 ADRs:**
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `scip-typescript` is in `ALLOWED_BINARIES`.
  - [`../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — `grammars.lock` shape and policy.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness="heavy"` semantics.
- **Source design:**
  - [`docs/localv2.md §5.2 B1`](../../../localv2.md) — SCIP slice shape including `coverage_pct`, `any_type_density`, `unresolved_dynamic_imports`, `symbol_count`, `exported_symbols`.
- **Existing code:**
  - `src/codegenie/probes/base.py` (frozen — subclass).
  - `src/codegenie/exec.py` (extended in S1-07) — `run_external_cli(...)` is the single subprocess port.
  - `src/codegenie/cache/` (Phase 0) — declared-inputs → cache key derivation.
- **External:**
  - `scip-typescript` README — its CLI flags (`--cwd`, `--output`, `--infer-tsconfig`); the JSON-stdout schema it emits with `--summary-json` (used here for slice metadata; the binary itself is opaque to Phase 2).

## Goal

Running `codegenie gather` against a TypeScript fixture produces `.codegenie/context/raw/scip-index.scip` (binary blob, opaque to Phase 2) AND a `semantic_index` slice in `repo-context.yaml` with `last_indexed_commit`, `last_indexed_at`, `files_indexed`, `files_in_repo`, `coverage_pct`, `indexer_errors`, `indexer_version`. Tool-version + `.ts`-Merkle are part of the cache key; a `scip-typescript` upgrade or any `.ts` file change invalidates the cache. Timeout at 300 s emits `indexer_errors=1` with structured detail visible to B2's `scip` freshness check. `tools/grammars.lock` exists with BLAKE3-pinned TypeScript + JavaScript grammar binaries, and `tools/regenerate_grammars_lock.sh` is reviewed-as-code.

## Acceptance criteria

- [ ] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/scip_index.py` defines `class ScipIndexProbe(Probe)` with `list[str]` class attributes: `name="scip_index"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection","node_build_system"]`, `timeout_seconds=300`. The decorator is `@register_probe(heaviness="heavy")`.

- [ ] **AC-2 — `declared_inputs` captures tool version + `.ts` Merkle.** `declared_inputs` is a `list[str]` containing (a) literal globs `["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "tsconfig.json", "tsconfig.*.json", "package.json"]`, (b) a special declared-input token `scip-typescript-version:<resolved>` where `<resolved>` is the stdout of `run_external_cli("scip-typescript", ["--version"], ...)` captured at probe-instance init and memoized (single subprocess call per process — Phase 0 `tool_cache` is the seam). Cache-key sensitivity test (T-06) verifies that altering EITHER any `.ts` file OR the resolved tool version yields a different cache key.

- [ ] **AC-3 — Invocation via `run_external_cli` only.** The probe invokes `scip-typescript` **only** via `_exec.run_external_cli("scip_index", ["scip-typescript", "index", "--cwd", str(snapshot.root), "--output", str(blob_path), "--infer-tsconfig"], cwd=snapshot.root, timeout_s=300, max_stdout_bytes=64*1024*1024)`. No direct `subprocess.run`/`Popen`/`os.system` appears anywhere in the module. Argv composition is a pure helper (`_build_scip_argv`) testable in isolation. The probe imports as `from codegenie import exec as _exec` so unit tests can monkeypatch `codegenie.exec.run_external_cli`.

- [ ] **AC-4 — Blob path + slice URI.** The blob lands at `<snapshot.root>/.codegenie/context/raw/scip-index.scip` (Phase 2's raw-artifact convention from S1-09). The `semantic_index` slice contains `scip_index_uri: ".codegenie/context/raw/scip-index.scip"` (relative path, NOT absolute — see Rule 8 — match codebase convention; Phase 1's raw-artifact paths are all relative). The directory is created via `mkdir(parents=True, exist_ok=True)` before invocation. If the directory cannot be created (read-only filesystem), the probe emits `confidence="low"`, `errors=["scip_index.raw_artifact_dir_unwritable"]`, and skips invocation.

- [ ] **AC-5 — Slice fields per `localv2.md §5.2 B1`.** The slice emits these fields (all required unless marked optional):
  - `scip_index_uri: str` (relative path).
  - `indexer: str = "scip-typescript"`.
  - `indexer_version: str` (the resolved version from AC-2).
  - `files_indexed: int` (parsed from `scip-typescript --summary-json` stdout; if `--summary-json` is unavailable on the installed version, derived by counting `.ts`/`.tsx` files matching the same exclude set used for Merkle).
  - `files_in_repo: int` (count of `.ts`/`.tsx`/`.js`/`.jsx` files under repo root excluding `node_modules`, `dist`, `build`, `.git`).
  - `coverage_pct: float` (= `files_indexed / files_in_repo * 100`, rounded to one decimal; if `files_in_repo == 0`, emit `0.0` AND `confidence="low"`).
  - `last_indexed_commit: str` (the SHA at the time `scip-typescript` was invoked; obtained via `run_allowlisted(["git", "rev-parse", "HEAD"], ...)` immediately before invocation — this anchors B2's `CommitsBehind.last_indexed` field).
  - `last_indexed_at: str` (ISO-8601 UTC timestamp at invocation start).
  - `indexer_errors: int` (= 1 on timeout/non-zero-exit, else 0).
  - `indexer_warnings: int` (parsed from `--summary-json` if available; else 0).
  - Optional fields per `localv2.md §5.2 B1` lines 581–586 (`any_type_density`, `unresolved_dynamic_imports`, `unresolved_computed_access`, `symbol_count`, `exported_symbols`): emit if `--summary-json` provides them, else omit from the slice (the sub-schema in S4-07 marks them optional).

- [ ] **AC-6 — Timeout path emits typed `IndexerError`-flavored slice.** If `run_external_cli` raises `asyncio.TimeoutError` (the `timeout_s=300` budget exceeds), the probe:
  1. Captures the partial blob (if any) — but does NOT preserve a corrupt `.scip` (deletes the file if it exists; partial SCIP would mislead Phase 3's `ScipAdapter`).
  2. Emits the slice with `indexer_errors=1`, `confidence="low"`, `warnings=["scip_index.timeout"]`.
  3. Does NOT raise. The next probe in the queue continues.
  4. B2's `scip` freshness check (S4-01 AC-5e) sees `indexer_errors > 0` and emits `Stale(IndexerError(message=f"indexer_reported_1_errors"))`. T-07 asserts this end-to-end via a monkeypatched `run_external_cli` that raises `TimeoutError`.

- [ ] **AC-7 — Non-zero exit path.** If `run_external_cli` returns a `ProcessResult` with non-zero `exit_code`, the probe emits the slice with `indexer_errors=1`, `confidence="low"`, `warnings=["scip_index.exit_nonzero"]`, and tail-includes the `stderr_tail` field (up to 4 KB) in the probe's structured-log event but NOT in the slice (stderr can contain repo paths; the slice is the auditable contract). The `.scip` blob is removed (same reasoning as AC-6 — partial blobs are misleading).

- [ ] **AC-8 — Tool-missing path.** If `run_external_cli` raises `FileNotFoundError` (the binary is not on `$PATH` — Phase 0's `tool_cache` check should have caught this at startup, but defensively handled), the probe emits the slice with `indexer="scip-typescript"`, `indexer_version="unknown"`, `files_indexed=0`, `coverage_pct=0.0`, `indexer_errors=1`, `confidence="low"`, `warnings=["scip_index.tool_missing"]`. No blob is written.

- [ ] **AC-9 — `files_in_repo` is computed with the same exclude set as `declared_inputs`.** A pure helper `_count_indexable_files(root: Path) -> int` walks the repo root, counts files matching `*.ts|*.tsx|*.js|*.jsx`, excluding paths under `node_modules`, `dist`, `build`, `.git`, and (if present) any path declared in `.codegenie/exclude.txt`. The same helper is used by the Merkle in AC-2 — divergence would make the cache key and the slice's `files_in_repo` inconsistent. T-09 verifies cardinality equality across helper invocations.

- [ ] **AC-10 — `tools/grammars.lock` lands with TypeScript + JavaScript pinned.** `tools/grammars.lock` is a small machine-readable file (YAML or TOML — implementer choice; YAML matches Phase 1 ADR-0004's "human-facing YAML, machine-readable JSON" convention) with at minimum:
  ```yaml
  schema_version: 1
  grammars:
    - language: typescript
      version: "0.20.6"             # tree-sitter-typescript release tag
      file: tools/grammars/typescript.so   # vendored binary path (relative to repo root)
      blake3: <64-hex-chars>        # BLAKE3 of the vendored binary
    - language: javascript
      version: "0.20.4"
      file: tools/grammars/javascript.so
      blake3: <64-hex-chars>
  ```
  Each `file` entry exists on disk (vendored), and the BLAKE3 of the vendored binary matches the `blake3` field byte-for-byte. A unit test (`tests/unit/tools/test_grammars_lock.py`) validates the schema AND verifies every BLAKE3 matches the vendored file (`blake3.blake3(open(file, "rb").read()).hexdigest()`).

- [ ] **AC-11 — `tools/regenerate_grammars_lock.sh` is reviewed-as-code.** Executable shell script under `tools/regenerate_grammars_lock.sh`. Walks `tools/grammars/`, recomputes BLAKE3 for each vendored binary, rewrites `tools/grammars.lock` with the recomputed values. Idempotent — second run produces an identical file. Refuses to run if any vendored binary is missing (loud failure, exit code 1). The script does NOT download grammars — vendoring is a manual PR-reviewable step (per [ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — "Grammar regeneration is a PR with a binary diff — heavier review"). A unit test (`test_regenerate_grammars_lock_idempotent`) runs the script twice in a tempdir copy and asserts byte-identical output.

- [ ] **AC-12 — `tools/grammars/` directory + at-least-two binaries.** `tools/grammars/typescript.so` (or `.dylib` for macOS dev; the CI runner is Linux-canonical so `.so` is the committed artifact — see [ADR-0002 §Tradeoffs](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) "Wheel matrix stays small") and `tools/grammars/javascript.so` exist as vendored binaries. `.gitattributes` declares `tools/grammars/*.so binary` and `tools/grammars/*.dylib binary` so git does not corrupt them. **The actual binary content is implementer-time work** — sourced from the tree-sitter-typescript and tree-sitter-javascript releases at the version pinned in `grammars.lock`. The PR description must include the upstream release URL and the BLAKE3 it computed locally.

- [ ] **AC-13 — Warning + error ID frozenset + import-time assertion.** All warning IDs (`scip_index.timeout`, `scip_index.exit_nonzero`, `scip_index.tool_missing`, `scip_index.raw_artifact_dir_unwritable`, `scip_index.summary_json_unavailable`) are declared in a module-level `_WARNING_IDS: frozenset[str]`. Import-time `assert` verifies every member matches the Phase 1 ADR-0007 regex.

- [ ] **AC-14 — Registry membership + `for_task` filter.** `src/codegenie/probes/__init__.py` imports `ScipIndexProbe` via an explicit additive line. `default_registry.all_probes()` includes it with `heaviness="heavy"`. `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it; `for_task("*", frozenset({"go"}))` does NOT.

- [ ] **AC-15 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/layer_b/scip_index.py`, `pytest tests/unit/probes/layer_b/test_scip_index.py`, `pytest tests/unit/tools/test_grammars_lock.py`, `shellcheck tools/regenerate_grammars_lock.sh`. All green.

## Implementation outline

1. **Create `src/codegenie/probes/layer_b/scip_index.py`** with the probe class per AC-1 plus pure helpers `_build_scip_argv`, `_count_indexable_files`, `_parse_summary_json`, `_compute_indexable_merkle`.

2. **Tool-version memoization.** At probe-class import time (NOT `__init__`-time per request — once per process), call `_exec.run_external_cli("scip_index_version_probe", ["scip-typescript", "--version"], cwd=Path.cwd(), timeout_s=5)` and store the resolved version in a module-level `_resolved_version: str | None = None`. Defensive: a second resolution on `FileNotFoundError` returns `"unknown"`. The Phase 0 `tool_cache` is the right home for this if S1-07 left it extensible; otherwise an in-module memo is fine.

3. **`async def run(self, ctx) -> ProbeOutput`.** Order:
   1. Compute `last_indexed_at = datetime.utcnow().isoformat() + "Z"`.
   2. Compute `last_indexed_commit` via `_exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=ctx.snapshot.root, timeout_s=5)` (handle `CalledProcessError` → `last_indexed_commit="unknown"` + add warning).
   3. Compute `files_in_repo = _count_indexable_files(ctx.snapshot.root)`.
   4. Ensure `raw_dir = ctx.snapshot.root / ".codegenie/context/raw"`; `mkdir(parents=True, exist_ok=True)`; on `OSError` → AC-4 short-circuit.
   5. Build argv via `_build_scip_argv`.
   6. `try: result = await _exec.run_external_cli(...)` with `except` arms for `asyncio.TimeoutError` (AC-6), `FileNotFoundError` (AC-8).
   7. On non-zero exit (AC-7), remove partial blob.
   8. On success, parse `--summary-json` stdout via Pydantic; populate optional slice fields (AC-5).
   9. Compose slice; return `ProbeOutput`.

4. **`_build_scip_argv` (pure).** Returns `list[str]` with the exact CLI shape. Tested independently in T-02.

5. **`_count_indexable_files` (pure).** Walks `root`, filters by extensions and exclude paths. Identical filter as Merkle. Tested in T-09.

6. **`_parse_summary_json` (pure).** Pydantic model `_ScipSummary` with optional fields; tolerates absent fields by leaving slice optionals unset. On parse failure, `warnings.append("scip_index.summary_json_unavailable")` and proceed with derived `files_indexed = files_in_repo`.

7. **`tools/grammars.lock` + `tools/regenerate_grammars_lock.sh` + `tools/grammars/{typescript,javascript}.so`.** Land all in this story; consumer is S4-04.

8. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

## TDD plan — red / green / refactor

### Test helpers preamble

```python
# tests/unit/probes/layer_b/test_scip_index.py
from __future__ import annotations
import asyncio, json, types
from pathlib import Path
import pytest
from codegenie.probes.layer_b.scip_index import ScipIndexProbe, _build_scip_argv, _count_indexable_files
from codegenie.exec import ProcessResult
```

### RED

- **T-01** `test_probe_contract_attributes`: AC-1.
- **T-02** `test_build_scip_argv_shape`: AC-3; expected argv list verbatim.
- **T-03** `test_invocation_via_run_external_cli_only`: AC-3; AST-walk module; assert no `subprocess.run`/`Popen` calls.
- **T-04** `test_blob_lands_at_expected_path`: AC-4; stub `run_external_cli` to write a known byte string to `--output`; assert `.codegenie/context/raw/scip-index.scip` exists and is non-empty; assert `slice["scip_index_uri"] == ".codegenie/context/raw/scip-index.scip"`.
- **T-05** `test_slice_fields_localv2_compliance`: AC-5; stub `--summary-json` stdout with all optional fields; assert every slice key matches `localv2.md §5.2 B1`.
- **T-06** `test_cache_key_sensitivity_tool_version_and_ts_merkle`: AC-2; build two `declared_inputs` with (a) same `.ts` content but different `scip-typescript-version`, (b) different `.ts` content but same version; assert the Phase 0 cache key differs in BOTH cases.
- **T-07** `test_timeout_path_emits_typed_error` (AC-6): monkeypatch `run_external_cli` to raise `asyncio.TimeoutError`; assert slice contains `indexer_errors=1`, `warnings == ["scip_index.timeout"]`, `confidence="low"`; assert `.scip` blob does NOT exist (deleted); assert no exception escapes `run()`.
- **T-08** `test_non_zero_exit_path` (AC-7): monkeypatch to return `ProcessResult(exit_code=2, stderr_tail="bad tsconfig")`; assert `indexer_errors=1`, `warnings == ["scip_index.exit_nonzero"]`, stderr NOT in slice but in structured log.
- **T-09** `test_count_indexable_files_excludes_canonical_dirs` (AC-9): tempdir with `node_modules/foo.ts`, `dist/bar.ts`, `src/baz.ts`; assert count == 1; assert `_compute_indexable_merkle` over the same root yields a Merkle that ignores `node_modules`/`dist`.
- **T-10** `test_tool_missing_path` (AC-8): monkeypatch to raise `FileNotFoundError`; assert `indexer_version="unknown"`, `warnings == ["scip_index.tool_missing"]`.
- **T-11** `test_raw_artifact_dir_unwritable` (AC-4): tempdir with `.codegenie/context/raw/` as a file (not dir); `mkdir(parents=True, exist_ok=True)` raises `FileExistsError`; probe emits AC-4's short-circuit slice; no `run_external_cli` invocation.
- **T-12** `test_warning_ids_match_adr_0007` (AC-13).
- **T-13** `test_registry_membership_heaviness_heavy` (AC-14).

For `tools/grammars.lock`:
- **T-14** `test_grammars_lock_schema_and_blake3` (AC-10): every entry has all required fields; BLAKE3 of vendored file matches the `blake3` field; `pip install blake3`-style import only — no shelling.
- **T-15** `test_grammars_lock_lists_typescript_and_javascript` (AC-10): at minimum, languages `typescript` and `javascript` are present.
- **T-16** `test_regenerate_grammars_lock_idempotent` (AC-11): run the script twice; second invocation produces byte-identical output.
- **T-17** `test_regenerate_grammars_lock_refuses_missing_binary` (AC-11): temp copy with one binary deleted; script exits 1 with stderr "missing".
- **T-18** `test_grammars_so_binary_attributes` (AC-12): `.gitattributes` contains `tools/grammars/*.so binary`.

### GREEN

Implement per outline. Vendor real grammar binaries (download from tree-sitter-typescript / tree-sitter-javascript releases at the version pinned). Compute BLAKE3 locally; commit.

### REFACTOR

- Extract `_ScipSummary` Pydantic model to a private nested class (or top-level if it grows) — keep `scip_index.py` ≤ 300 LOC.
- Confirm `mypy --strict` passes; the `Pydantic` model needs explicit `Optional[...]` for unmentioned fields.
- Confirm the structured-log event includes `tool_version`, `files_indexed`, `files_in_repo`, `duration_s` for ops observability (Rule 12 — fail loud, succeed verbose-enough-to-debug).

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/scip_index.py`
- `tests/unit/probes/layer_b/test_scip_index.py`
- `tools/grammars.lock` (data)
- `tools/grammars/typescript.so` (vendored binary)
- `tools/grammars/javascript.so` (vendored binary)
- `tools/regenerate_grammars_lock.sh` (executable)
- `tests/unit/tools/__init__.py`
- `tests/unit/tools/test_grammars_lock.py`

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — additive import line.
- `.gitattributes` — `tools/grammars/*.so binary`, `tools/grammars/*.dylib binary`.
- `pyproject.toml` — confirm `blake3` is in Phase 0 deps (it is per Phase 0 ADR — no edit needed); confirm `mypy.overrides` for the module if needed.

## Out of scope

- **Parsing the `.scip` blob.** Phase 2 emits only; Phase 3's `ScipAdapter` decides consumption shape ([ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — `msgpack`/`scip-python`/projection format all rejected).
- **`TreeSitterImportGraphProbe`.** S4-04 consumes `tools/grammars.lock` (which this story lands); the probe itself ships there.
- **Sub-schema for `semantic_index`.** S4-07 lands all seven Layer-B sub-schemas with `additionalProperties: false` and ADR-0007 ID-pattern constraints.
- **Real `scip-typescript` invocation in unit tests.** Unit tests monkeypatch `run_external_cli`; the real invocation is exercised in the portfolio sweep (S7-05) and integration job (S8-03 `integration` job).
- **Bench overhead for SCIP.** S8-03's `bench_portfolio_walltime` covers cold + warm p50; this story's perf envelope (~10 s cold per [phase-arch-design.md §"Component design" #12](../phase-arch-design.md) — though that's tree-sitter; SCIP is more like 8–30 s on minimal-ts) is informational.
- **`scip-python` / cross-language SCIP.** Phase 2 is TypeScript/JavaScript only via `scip-typescript`. Phase 8+ adds Python / Java / Go via ADR-amendments.

## Notes for the implementer

- **Why this story owns `grammars.lock` instead of S4-04.** S4-04's `TreeSitterImportGraphProbe` is the **first consumer** of the lock — it does a BLAKE3 verification at grammar load time. The lock must exist on disk before that probe can load. Splitting "lock file" and "lock-file consumer" across separate stories would create an awkward sequencing where S4-04 cannot land green without S4-03's artifacts. Bundling them here means the dependency in the manifest (`S4-04 depends on S4-03`) is real — not just narrative.
- **Vendoring grammars is a PR-reviewable step.** [ADR-0002 §Tradeoffs](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — "Grammar regeneration is a PR with a binary diff." The PR description for this story must include: (a) the upstream tree-sitter-typescript / tree-sitter-javascript release tags, (b) the local BLAKE3 the implementer computed, (c) confirmation that `tools/regenerate_grammars_lock.sh` produces the matching `tools/grammars.lock` byte-for-byte. A reviewer can re-run the regen script to verify.
- **`.dylib` vs `.so`.** The CI runner is Linux-canonical; `.so` is committed. Developers on macOS can `regenerate_grammars_lock.sh` against a `.dylib` they vendor locally — but the committed lock file pins `.so`. If a macOS dev workflow becomes load-bearing, ADR-0002's wheel-matrix discussion applies; today, Linux is the canonical PR-validation environment.
- **`run_external_cli`, not `run_allowlisted` direct.** AC-3 is load-bearing — Layer B/G external CLIs all route through `run_external_cli` ([phase-arch-design.md §"Component design" #3](../phase-arch-design.md), [phase-arch-design.md §"Goals" G6](../phase-arch-design.md)). The exception is Layer C (`docker`, `strace`) which goes through `run_allowlisted` directly. `git` is a Phase 0/1 binary and predates the chokepoint; in this probe, `git rev-parse HEAD` is admissible via `run_allowlisted` (one-line precedent from S2-02 — same allowlist entry, same env-strip path).
- **Cache key correctness is load-bearing.** A wrong cache key means stale SCIP blobs survive across `scip-typescript` upgrades — and B2 would see `last_indexed_commit` match HEAD (cache hit), report `Fresh`, but the BLOB is from the old indexer. The Merkle + tool-version anchor (AC-2) is what prevents this. Test T-06 exercises both arms.
- **Don't preserve corrupt blobs.** AC-6 / AC-7 delete the `.scip` file on timeout / non-zero exit. A partial blob would mislead Phase 3's `ScipAdapter` (it would try to parse and fail in mysterious ways). The "no blob is better than a bad blob" discipline (Rule 12 — fail loud) — but the `indexer_errors=1` signal is what makes B2's `Stale(IndexerError)` real for the renderer.
- **Rule 9 — tests verify intent.** T-06 (cache key sensitivity) encodes the WHY of `declared_inputs`. T-07 (timeout path) encodes the WHY of typed error reporting + B2 hand-off. T-09 (count consistency) encodes the WHY of helper-sharing between Merkle and count. None of them check "the code returns a value" — every one checks a load-bearing invariant.
- **The optional `--summary-json` fields.** `scip-typescript`'s `--summary-json` is a relatively new feature; if the installed version doesn't support it, fall back gracefully (AC-5 — derive `files_indexed` by counting; emit `summary_json_unavailable` warning; leave optional fields unset). Do NOT make `--summary-json` required — it would bind Phase 2 to a `scip-typescript` minimum version that's not in any ADR.
