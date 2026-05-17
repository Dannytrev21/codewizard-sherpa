# Story S4-03 — `ScipIndexProbe` via `scip-typescript` + grammars-lock infrastructure

**Status:** Done (originally) — **grammars-lock infrastructure superseded 2026-05-17 by [02-ADR-0011](../ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md)**. The `ScipIndexProbe` half ships unchanged; the grammar-infrastructure half (`tools/grammars.lock`, `tools/regenerate_grammars_lock.sh`, vendored `.so` files, `.gitattributes` entries, `tests/unit/tools/test_grammars_lock.py`) was deleted. `src/codegenie/grammars/lock.py` was rewritten in-place — its public surface is now `language_for(name) -> tree_sitter.Language` + `GrammarLoadRefused` instead of `load_and_verify(repo_root) -> GrammarLockFile`. AC-10/AC-11/AC-12/AC-18 (the grammars-lock ACs) no longer apply; equivalent acceptance lives in `tests/unit/grammars/test_lock.py` (the new kernel) and `pip --require-hashes` at the wheel boundary.
**Completed:** 2026-05-16
**Attempts:** 1
**Evidence:**
- Files created:
  `src/codegenie/exec/__init__.py` (promoted from module),
  `src/codegenie/exec/tool_versions.py`,
  `src/codegenie/grammars/{__init__,lock}.py`,
  `src/codegenie/probes/layer_b/{scip_index,scip_slice}.py`,
  `tests/unit/{exec/test_tool_versions,grammars/test_lock,tools/test_grammars_lock,probes/layer_b/test_scip_index}.py`,
  `tools/grammars.lock`, `tools/regenerate_grammars_lock.sh`,
  `tools/grammars/{typescript,javascript}.so` (placeholders — see `tools/grammars/README.md`),
  `tools/grammars/README.md`, `.gitattributes`.
- Files edited (additive):
  `src/codegenie/probes/__init__.py` (import `scip_index`),
  `tests/unit/exec/test_run_external_cli.py` (S4-03 promoted exec.py to a package — test loosened to "anywhere inside the exec package is exempt").
- Tests (40 added, all green):
  `tests/unit/probes/layer_b/test_scip_index.py` (20),
  `tests/unit/exec/test_tool_versions.py` (6),
  `tests/unit/grammars/test_lock.py` (9),
  `tests/unit/tools/test_grammars_lock.py` (5).
- Full suite: 2097 passed, 5 skipped, 1 xfail, 2 pre-existing env-only failures
  (`test_lint_imports_canary` — `lint-imports` console script not in local `.venv`;
  passes in CI per S1-05 wiring).
- Tooling: `ruff check`, `ruff format --check`, `mypy --strict src/`, `pre-commit run`,
  `shellcheck tools/regenerate_grammars_lock.sh` all green.

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Story status (pre-execution):** Ready · VALIDATED (HARDENED — see `_validation/S4-03-scip-index-probe.md`)
**Effort:** M
**Depends on:** S1-07 (`run_external_cli` on disk, `ALLOWED_BINARIES` extended with `scip-typescript` + `tree-sitter` + nine others), S1-08 (`@register_probe(heaviness="heavy")` registry annotation; coordinator dispatches heavy probes first), S4-01 (B2's `read_raw_slices` reads `<output_dir>/raw/scip.json` — this story produces that file)

## Validation notes (2026-05-16)

Seven BLOCK-severity inconsistencies with master closed; ten HARDEN findings closed; four design-pattern opportunities elevated to load-bearing ACs. Full audit: `_validation/S4-03-scip-index-probe.md`. Highlights:

1. **`Probe.run` is two-argument** `(self, repo: RepoSnapshot, ctx: ProbeContext)` per `src/codegenie/probes/base.py:94`. Impl outline corrected throughout.
2. **`ProcessResult` shape** is `(returncode: int, stdout: bytes, stderr: bytes)` — frozen dataclass at `src/codegenie/exec.py:140-150`. No `exit_code`. No `stderr_tail`. Caller decodes + tails: `result.stderr[-4096:].decode("utf-8", errors="replace")`.
3. **`run_external_cli` exception taxonomy:** `ProbeTimeoutError` (timeout), `ToolMissingError` (binary missing), `DisallowedSubprocessError`, `FileNotFoundError` / `NotADirectoryError` (cwd missing). Does NOT raise `asyncio.TimeoutError` or `CalledProcessError`. Non-zero exits return `ProcessResult` with `returncode != 0` — caller inspects.
4. **`<output_dir>/raw/scip.json` is the LOAD-BEARING hand-off to B2** (S4-01 hardened, cross-story commitment line 13). Without it, B2 fires `Stale(IndexerError("upstream_scip_unavailable"))` on every gather. New AC-16 mandates writing it; new AC-17 mandates inclusion in `ProbeOutput.raw_artifacts` so warm-cache replay re-publishes.
5. **Tool-version cache-key sensitivity via `probe.version` `@property`, NOT a `scip-typescript-version:<resolved>` declared-input token.** Master's `cache/keys.py::declared_inputs_for` does `rglob` only — no token dispatch. ADR-0004 prescribed it for `image-digest:` but S1-09 (Done) only added the `ProbeContext.image_digest_resolver` field. `probe.version` IS in the cache key (`cache/keys.py:146`); rolling the resolved tool version into `version` (e.g., `f"0.1.0+scip-typescript-{resolved}"`) closes the gap with zero new mechanism.
6. **`files_in_repo` restricted to `.ts/.tsx`** — `scip-typescript`'s program scope. `.js/.jsx` are S4-04's `TreeSitterImportGraphProbe` concern. The original `.ts/.tsx/.js/.jsx` walk would fire B2's `Stale(CoverageGap)` on every healthy mixed JS+TS repo.
7. **Tool-version resolution extracted** to `codegenie.exec.tool_versions` (process-wide memo, lazy, `clear_for_tests()` seam). Rule-of-three crossed: `scip-typescript`, `tree-sitter`, `grype`/`syft`/`semgrep`/`gitleaks` all need it. Subprocess at probe-import time is the anti-pattern this closes.
8. **`SemanticIndexSlice` Pydantic smart constructor** is the single source of truth for the slice shape; both the envelope and `scip.json` derive from `model_dump(mode="json", exclude_none=True)`. Mirrors S3-02's `RedactedSlice` precedent.
9. **`codegenie.grammars.lock` typed loader** (`load_and_verify(repo_root) -> GrammarLockFile`; `GrammarLoadRefused` exception) is the shared chokepoint for this story's tests AND S4-04's pre-load BLAKE3 check.
10. **Import-time `assert` removed** — Phase 0 forbidden-patterns hook bans bare `assert` in `src/codegenie/`. Warning-ID conformance verified by unit test (S4-01 precedent).

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

- [ ] **AC-1 — Probe contract attributes + two-arg `run()`.** `src/codegenie/probes/layer_b/scip_index.py` defines `class ScipIndexProbe(Probe)` with `list[str]` class attributes: `name="scip_index"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection","node_build_system"]`, `timeout_seconds=300`, `cache_strategy: Literal["content"] = "content"`. `version` is a **`@property` returning `str`** (NOT a class attribute) — see AC-2 for the format. The async-run signature is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (two-arg per `src/codegenie/probes/base.py:94`). The decorator is `@register_probe(heaviness="heavy")`.

- [ ] **AC-2 — Tool-version sensitivity via `probe.version` property (NOT a declared-input token).** `ScipIndexProbe.version` is a `@property` returning `f"0.1.0+scip-typescript-{resolved}"` where `<resolved>` is `codegenie.exec.tool_versions.resolve_tool_version("scip-typescript")` (lazy, process-wide memoized — see AC-19). Format pinned by regex `r"^0\.1\.\d+\+scip-typescript-.+$"` in T-06 so the resolved suffix can vary across CI environments. **Rationale:** `probe.version` is in `key_for`'s tuple (`src/codegenie/cache/keys.py:146`); a `scip-typescript` upgrade automatically invalidates the cache with zero new mechanism. The performance-lens-proposed `scip-typescript-version:<resolved>` declared-input token is REJECTED — master's `cache/keys.py::declared_inputs_for` does `rglob` only (no token dispatch); ADR-0004's token mechanism is unimplemented in the cache layer; and `_OUTPUT_NAMESPACE = ".codegenie"` would filter any version-stamp file written under that namespace. `declared_inputs` is therefore the filesystem-only list `["**/*.ts", "**/*.tsx", "tsconfig.json", "tsconfig.*.json", "package.json"]` (the `.ts`-Merkle channel of cache-key sensitivity — `content_hash_of_inputs` aggregates these per `cache/keys.py:146`). Cache-key sensitivity test (T-06) verifies BOTH (a) altering any `.ts` file changes the key (Merkle path) and (b) altering the resolved tool version changes `probe.version` and therefore the key (version path).

- [ ] **AC-3 — Invocation via `run_external_cli` only.** The probe invokes `scip-typescript` **only** via `_exec.run_external_cli("scip_index", ["scip-typescript", "index", "--cwd", str(repo.root), "--output", str(blob_path), "--infer-tsconfig"], cwd=repo.root, timeout_s=300, max_stdout_bytes=64*1024*1024)`. No direct `subprocess.run`/`Popen`/`os.system` appears anywhere in the module. Argv composition is a pure helper (`_build_scip_argv(repo_root: Path, blob_path: Path) -> list[str]`) testable in isolation. The probe imports as `from codegenie import exec as _exec` so unit tests can monkeypatch `codegenie.exec.run_external_cli`. The stub contract for T-04 is spelled out (it writes the blob then returns a real `ProcessResult`):

  ```python
  async def _stub_writes_blob(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64*1024*1024, env_extra=None):
      out_path = Path(argv[argv.index("--output") + 1])
      out_path.write_bytes(b"FAKE-SCIP-BLOB")
      return ProcessResult(returncode=0, stdout=b'{"files_indexed":1}', stderr=b"")
  ```

- [ ] **AC-4 — Blob path via `ctx.output_dir`; slice URI is repo-relative.** The blob lands at `ctx.output_dir / "raw" / "scip-index.scip"` (Phase 1 convention — `ProbeContext.output_dir` is the "where probe writes raw artifacts" surface per `src/codegenie/probes/base.py:53`; `ctx.output_dir` is normally `<repo>/.codegenie/context`). The `semantic_index` slice's `scip_index_uri` is the path **relative to `repo.root`** (e.g. `".codegenie/context/raw/scip-index.scip"`) computed via `(ctx.output_dir / "raw" / "scip-index.scip").relative_to(repo.root)`. The directory is created via `(ctx.output_dir / "raw").mkdir(parents=True, exist_ok=True)` before invocation. If the directory cannot be created (read-only filesystem, OSError), the probe emits `confidence="low"`, `errors=["scip_index.raw_artifact_dir_unwritable"]`, and skips invocation.

- [ ] **AC-5 — Slice fields per `localv2.md §5.2 B1` + B2-compatible key set; built via `SemanticIndexSlice` Pydantic model (see AC-18).** The slice emits these fields (all required unless marked optional):
  - `scip_index_uri: str` (path relative to `repo.root`).
  - `indexer: Literal["scip-typescript"]`.
  - `indexer_version: str` (the resolved version from AC-2 — just the suffix after `+scip-typescript-`, OR `"unknown"` on tool-missing).
  - `files_indexed: int ≥ 0` (parsed from `scip-typescript --summary-json` stdout; if `--summary-json` is unavailable on the installed version, derived by counting `.ts/.tsx` files via `_count_indexable_files` — see AC-9).
  - `files_in_repo: int ≥ 0` (count of `.ts/.tsx` files under repo root excluding `node_modules`, `dist`, `build`, `.git`, and any path in `.codegenie/exclude.txt` if present). **`.js/.jsx` are EXCLUDED** — `scip-typescript`'s program scope is TypeScript-only (per `localv2.md §5.2 B1 lines 565-567`); `.js/.jsx` coverage is S4-04's `TreeSitterImportGraphProbe` concern. Including them would make B2's `Stale(CoverageGap)` fire on every healthy mixed JS+TS repo (`scip_freshness` AC-5(d) compares `files_indexed < files_in_repo`).
  - `coverage_pct: float ∈ [0.0, 100.0]` (= `files_indexed / files_in_repo * 100` rounded to one decimal; if `files_in_repo == 0`, emit `0.0`). On `files_in_repo == 0`, the **probe envelope** `confidence="low"` (the index is not informative); B2's `scip_freshness` reads `0 == 0` and emits `Fresh` (the index matches HEAD). The two layers disagree intentionally; the agreement is documented in Notes for implementer.
  - `last_indexed_commit: str` (the SHA at the time `scip-typescript` was invoked; obtained via `await _exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=repo.root, timeout_s=5)`. On `result.returncode != 0` (NOT `CalledProcessError` — `run_allowlisted` returns; it does not raise per `src/codegenie/exec.py:216-355`), `last_indexed_commit="unknown"` and `warnings.append("scip_index.head_unresolvable")`.
  - `last_indexed_at: str` (ISO-8601 UTC timestamp at invocation start; e.g., `"2026-05-16T12:34:56.789+00:00"` from `datetime.now(timezone.utc).isoformat()`).
  - `indexer_errors: int ≥ 0` (= 1 on timeout/non-zero-exit/tool-missing, else 0).
  - `indexer_warnings: int ≥ 0` (parsed from `--summary-json` if available; else 0).
  - Optional fields per `localv2.md §5.2 B1` lines 581–586 (`any_type_density`, `unresolved_dynamic_imports`, `unresolved_computed_access`, `symbol_count`, `exported_symbols`): emit if `--summary-json` provides them, else omit from the slice via `model_dump(exclude_none=True)` (the sub-schema in S4-07 marks them optional).

- [ ] **AC-6 — Timeout path emits typed `IndexerError`-flavored slice.** If `run_external_cli` raises `codegenie.errors.ProbeTimeoutError` (NOT `asyncio.TimeoutError` — `run_external_cli` wraps the asyncio timeout per `src/codegenie/exec.py:330-338`), the probe:
  1. Removes the partial blob if `blob_path.exists()` — partial SCIP would mislead Phase 3's `ScipAdapter`.
  2. Emits the slice with `indexer_errors=1`, `files_indexed=0`, `coverage_pct=0.0`, `confidence="low"`, `warnings=["scip_index.timeout"]`.
  3. Does NOT raise. The next probe in the queue continues.
  4. Writes `scip.json` per AC-16 with the same slice contents so B2 reads `indexer_errors > 0` and (per S4-01 AC-5(e)) emits `Stale(IndexerError(message=f"indexer_reported_{n}_errors"))` where `n=1`. T-07 asserts this end-to-end by both (a) inspecting the slice fields directly AND (b) calling S4-01's published `scip_freshness(slice, head)` check on the JSON and asserting the typed `Stale(IndexerError(...))` outcome. The message-format string `"indexer_reported_{n}_errors"` is consumer-coupled to S4-01; T-07 references S4-01's check function rather than re-encoding the f-string (so a S4-01 message-format refactor surfaces as a test break on both sides, not a silent drift).

- [ ] **AC-7 — Non-zero exit path.** If `run_external_cli` returns a `ProcessResult` (frozen; fields `returncode: int, stdout: bytes, stderr: bytes` — no `exit_code`, no `stderr_tail`) with `result.returncode != 0`, the probe:
  - Emits the slice with `indexer_errors=1`, `files_indexed=0`, `coverage_pct=0.0`, `confidence="low"`, `warnings=["scip_index.exit_nonzero"]`.
  - Computes `stderr_tail: str = result.stderr[-4096:].decode("utf-8", errors="replace")` and includes it in the probe's structured-log event (`_log.warning("scip_index.exit_nonzero", returncode=..., stderr_tail=stderr_tail, ...)`) but **NOT** in the slice (stderr can contain repo paths; the slice is the auditable contract).
  - Removes the partial `.scip` blob if it exists (same reasoning as AC-6).
  - Writes `scip.json` per AC-16 so B2 reads `indexer_errors > 0` and emits `Stale(IndexerError(...))`.

- [ ] **AC-8 — Tool-missing path.** If `run_external_cli` raises `codegenie.errors.ToolMissingError` (NOT `FileNotFoundError` — the latter is raised only when `cwd` does not exist, per `src/codegenie/exec.py:320`), the probe emits the slice with `indexer="scip-typescript"`, `indexer_version="unknown"`, `files_indexed=0`, `files_in_repo=<actual>`, `coverage_pct=0.0`, `indexer_errors=1`, `confidence="low"`, `warnings=["scip_index.tool_missing"]`. No blob is written. `scip.json` is still written (AC-16) so B2 emits `Stale(IndexerError("indexer_reported_1_errors"))`. The tool-version resolver (AC-19) must also return `"unknown"` on `ToolMissingError` rather than raising — the probe's `version` property must be safe to read even when the binary is missing.

- [ ] **AC-9 — `files_in_repo` and Merkle share one walker (consistency invariant).** A pure helper `_count_indexable_files(root: Path) -> int` walks `root`, counts files matching `*.ts|*.tsx` (NOT `*.js|*.jsx` — see AC-5), excluding paths under `node_modules`, `dist`, `build`, `.git`, and (if present) any path declared in `.codegenie/exclude.txt`. A second pure helper `_compute_indexable_merkle(root: Path) -> str` walks the SAME exclusion set and returns a BLAKE3 over the sorted (path, content-hash) pairs. The two helpers share a private `_walk_indexable_files(root: Path) -> Iterator[Path]` so divergence is mechanically impossible. T-09 verifies symmetric exclusion: planting `node_modules/extra.ts` leaves BOTH the count AND the Merkle unchanged versus an empty `node_modules/`.

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

- [ ] **AC-13 — Warning + error ID frozenset (unit-test verified, NOT import-time `assert`).** All warning IDs (`scip_index.timeout`, `scip_index.exit_nonzero`, `scip_index.tool_missing`, `scip_index.head_unresolvable`, `scip_index.raw_artifact_dir_unwritable`, `scip_index.summary_json_unavailable`) are declared in a module-level `_WARNING_IDS: frozenset[str]`. Phase 0 forbidden-patterns hook bans bare `assert` in `src/codegenie/`; a **unit test** (`test_warning_ids_match_adr_0007`) iterates `_WARNING_IDS` and asserts every member matches the Phase 1 ADR-0007 regex (precedent: S4-01 uses the same pattern). A second test (`test_run_only_emits_declared_warning_ids`) AST-walks `run()` and asserts every `warnings.append(...)` literal is a member of `_WARNING_IDS` — closes the silent-drift gap where a new warning string is added without being declared.

- [ ] **AC-14 — Registry membership + `for_task` filter.** `src/codegenie/probes/__init__.py` imports `ScipIndexProbe` via an explicit additive line. `default_registry.all_probes()` includes it with `heaviness="heavy"`. `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it; `for_task("*", frozenset({"go"}))` does NOT.

- [ ] **AC-15 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/layer_b/scip_index.py src/codegenie/exec/tool_versions.py src/codegenie/grammars/lock.py`, `pytest tests/unit/probes/layer_b/test_scip_index.py tests/unit/exec/test_tool_versions.py tests/unit/grammars/test_lock.py tests/unit/tools/test_grammars_lock.py`, `shellcheck tools/regenerate_grammars_lock.sh`. All green.

- [ ] **AC-16 — `scip.json` sibling raw artifact for B2 (LOAD-BEARING cross-story hand-off).** The probe writes `ctx.output_dir / "raw" / "scip.json"` containing `SemanticIndexSlice.model_dump_json(exclude_none=True, indent=2)`. The filename `scip.json` is keyed by `IndexName("scip")` — S4-01's `read_raw_slices(raw_dir)` discovers it by stem and passes the parsed dict to `scip_freshness(slice, head)`. Without this file, B2 fires `Stale(IndexerError("upstream_scip_unavailable"))` on every gather (per S4-01 AC-12 — sibling-missing path). The JSON contents MUST contain the keys B2's `scip_freshness` reads (`last_indexed_commit`, `files_indexed`, `files_in_repo`, `indexer_errors`, `last_indexed_at` — all top-level). A unit test (T-19) loads the written JSON, feeds it through S4-01's published `scip_freshness` check function, and asserts the typed `IndexFreshness` outcome (`Fresh` on green path; `Stale(...)` on each error path). This test is the structural guarantee of the cross-story contract.

- [ ] **AC-17 — `scip.json` is in `ProbeOutput.raw_artifacts` (warm-cache hand-off).** `ProbeOutput.raw_artifacts: list[Path]` includes BOTH `<ctx.output_dir>/raw/scip-index.scip` AND `<ctx.output_dir>/raw/scip.json`. The coordinator/writer replays the `raw_artifacts` list on cache HIT (Phase 0 cache replay semantics); without `scip.json` in the list, a warm gather would leave the file stale or absent and B2 would mis-fire. Verified by T-Sj-2: instantiate two probe runs back-to-back against the same inputs; the second is a cache HIT (declared inputs unchanged, `probe.version` unchanged); assert `scip.json` is still present after the second run AND its bytes are byte-identical to the first run.

- [ ] **AC-18 — `SemanticIndexSlice` Pydantic smart constructor (single source of truth for slice shape).** Define `class SemanticIndexSlice(BaseModel)` at `src/codegenie/probes/layer_b/scip_slice.py` (sibling module, kept separate from probe so S4-07's sub-schema can `model_json_schema()` it cleanly):

  ```python
  class SemanticIndexSlice(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)

      scip_index_uri: str
      indexer: Literal["scip-typescript"]
      indexer_version: str
      files_indexed: int = Field(ge=0)
      files_in_repo: int = Field(ge=0)
      coverage_pct: float = Field(ge=0.0, le=100.0)
      last_indexed_commit: str
      last_indexed_at: str
      indexer_errors: int = Field(ge=0)
      indexer_warnings: int = Field(ge=0)
      any_type_density: float | None = None
      unresolved_dynamic_imports: int | None = None
      unresolved_computed_access: int | None = None
      symbol_count: int | None = None
      exported_symbols: int | None = None
  ```

  Both the envelope-side `schema_slice["semantic_index"]` AND `scip.json` derive from `slice.model_dump(mode="json", exclude_none=True)`. This closes the F-TQ-6 mutation-killer gap by construction: a renamed field would fail Pydantic validation, not produce a silent mis-key. Mirrors S3-02's `RedactedSlice` smart-constructor precedent.

- [ ] **AC-19 — `codegenie.exec.tool_versions` extracted (kernel for repeated tool-version resolution).** Create `src/codegenie/exec/tool_versions.py` exporting:
  - `async def resolve_tool_version(binary: str, *, version_argv: list[str] | None = None, parser: Callable[[bytes], str] | None = None) -> str` — invokes `run_external_cli(<binary>, version_argv or ["--version"], cwd=Path.cwd(), timeout_s=5)`, parses the version with `parser` or a default first-line-strip, returns the version string. On `ToolMissingError` returns `"unknown"` (does NOT raise — callers route through `probe.version`).
  - Process-wide memoization keyed by `(binary, tuple(version_argv or ["--version"]))`. Two calls in one process trigger the subprocess exactly once.
  - `def clear_for_tests() -> None` — mirrors S1-02's `unregister_for_tests` precedent; resets the memo for unit-test isolation.

  `ScipIndexProbe.version` calls `resolve_tool_version("scip-typescript")` lazily via the `@property`. **Extension-by-addition guarantee:** adding a new external-CLI probe must require zero edits to `scip_index.py` for tool-version resolution. Verified by structural test: any future `tree_sitter_import_graph.py` (S4-04) imports `resolve_tool_version` from this module, not from `scip_index`. T-20 asserts two consecutive `await resolve_tool_version("scip-typescript")` calls trigger exactly one underlying `run_external_cli` invocation (subprocess count via spy).

- [ ] **AC-20 — `codegenie.grammars.lock` typed loader (kernel for `tools/grammars.lock`).** Create `src/codegenie/grammars/lock.py` exporting:
  ```python
  class GrammarPin(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      language: str
      version: str
      file: str          # repo-relative path
      blake3: str        # 64 hex chars

  class GrammarLockFile(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      schema_version: Literal[1]
      grammars: list[GrammarPin]

  def load_and_verify(repo_root: Path) -> GrammarLockFile: ...
  class GrammarLoadRefused(RuntimeError): ...
  ```
  `load_and_verify` reads `<repo_root>/tools/grammars.lock`, validates via Pydantic, recomputes BLAKE3 over every `file` entry, raises `GrammarLoadRefused` on mismatch with a structured message naming the failing language + expected/actual BLAKE3. S4-04's `TreeSitterImportGraphProbe` imports `load_and_verify` and consumes the typed result (pre-load supply-chain defense per phase-arch row 10). T-21 exercises happy path (all BLAKE3 match) AND mismatch path (tamper a vendored binary; assert `GrammarLoadRefused` with regex on the failing language).

## Implementation outline

1. **Create `src/codegenie/exec/tool_versions.py`** (AC-19). Process-wide memo, `clear_for_tests()`, `resolve_tool_version("scip-typescript")` returns the version string (or `"unknown"` on `ToolMissingError`). Lazy: no subprocess fires until first call.

2. **Create `src/codegenie/grammars/lock.py`** (AC-20). Pydantic `GrammarPin` + `GrammarLockFile`; `load_and_verify(repo_root) -> GrammarLockFile`; `GrammarLoadRefused` exception. The reader is reusable by S4-04.

3. **Create `src/codegenie/probes/layer_b/scip_slice.py`** (AC-18). `SemanticIndexSlice` Pydantic smart constructor.

4. **Create `src/codegenie/probes/layer_b/scip_index.py`** with the probe class per AC-1 plus pure helpers `_build_scip_argv`, `_count_indexable_files`, `_compute_indexable_merkle`, `_walk_indexable_files` (private shared walker — AC-9), `_parse_summary_json`. The probe's `version` is a `@property` returning `f"0.1.0+scip-typescript-{await resolve_tool_version('scip-typescript')}"` — but since `@property` cannot be `async`, the property body runs `asyncio.run(...)` on a tiny coroutine when first read, OR (cleaner) the memo is sync via a small `asyncio.run`-wrapper inside `tool_versions`. Implementer choice; both shapes are covered by T-20's process-wide single-subprocess assertion.

5. **`async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`** (two-arg per ABC). Order:
   1. `last_indexed_at: str = datetime.now(timezone.utc).isoformat()`.
   2. Resolve HEAD: `result = await _exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=repo.root, timeout_s=5)`. On `result.returncode != 0` (NOT `CalledProcessError`), `last_indexed_commit = "unknown"` + `warnings.append("scip_index.head_unresolvable")`. Else `last_indexed_commit = result.stdout.decode("utf-8").strip()`.
   3. `files_in_repo = _count_indexable_files(repo.root)` (`.ts/.tsx` only per AC-9).
   4. `raw_dir = ctx.output_dir / "raw"`; `raw_dir.mkdir(parents=True, exist_ok=True)`. On `OSError` → AC-4 short-circuit (emit slice with `confidence="low"`, `errors=["scip_index.raw_artifact_dir_unwritable"]`, skip invocation, still write `scip.json` per AC-16 so B2 doesn't see a missing sibling).
   5. `blob_path = raw_dir / "scip-index.scip"`; `argv = _build_scip_argv(repo.root, blob_path)`.
   6. `try: result = await _exec.run_external_cli(...)` with `except` arms for `ProbeTimeoutError` (AC-6), `ToolMissingError` (AC-8). All other exceptions propagate (the coordinator isolates).
   7. On `result.returncode != 0` (AC-7): compute `stderr_tail = result.stderr[-4096:].decode("utf-8", errors="replace")`; log structured; remove blob; emit error slice.
   8. On success: parse `--summary-json` stdout via `_parse_summary_json` (Pydantic; tolerant); populate optional slice fields.
   9. Construct `SemanticIndexSlice(...)` (Pydantic validates); compute `scip_index_uri` as `blob_path.relative_to(repo.root).as_posix()`.
   10. Write `<raw_dir>/scip.json` with `slice.model_dump_json(exclude_none=True, indent=2)` (AC-16).
   11. Compose `ProbeOutput` with `schema_slice={"semantic_index": slice.model_dump(mode="json", exclude_none=True)}`, `raw_artifacts=[blob_path, raw_dir / "scip.json"]` (AC-17), `confidence`, `duration_ms`, `warnings`, `errors`. Return.

6. **`_build_scip_argv(repo_root: Path, blob_path: Path) -> list[str]`** (pure). Returns `["scip-typescript", "index", "--cwd", str(repo_root), "--output", str(blob_path), "--infer-tsconfig"]`. Tested independently in T-02.

7. **`_walk_indexable_files(root: Path) -> Iterator[Path]`** (private pure). Yields `.ts/.tsx` files excluding the canonical exclude set. Shared by both `_count_indexable_files` and `_compute_indexable_merkle` so divergence is mechanically impossible (AC-9).

8. **`_count_indexable_files(root: Path) -> int`** (pure). `sum(1 for _ in _walk_indexable_files(root))`. T-09.

9. **`_compute_indexable_merkle(root: Path) -> str`** (pure). BLAKE3 over the sorted `(rel_path, content-hash)` pairs from `_walk_indexable_files`. Not directly in cache key (the Merkle channel of cache sensitivity is already provided by `content_hash_of_inputs` over `declared_inputs_for`); used as a documented invariant probe + future-proofing.

10. **`_parse_summary_json(stdout: bytes) -> _ScipSummary`** (pure). Pydantic model `_ScipSummary(BaseModel, frozen=True, extra="ignore")` with optional fields; tolerates absent fields. On parse failure (e.g., `--summary-json` unavailable on the installed version), returns an empty `_ScipSummary()` and the probe appends `warnings.append("scip_index.summary_json_unavailable")` and proceeds with derived `files_indexed = files_in_repo`.

11. **`tools/grammars.lock` + `tools/regenerate_grammars_lock.sh` + `tools/grammars/{typescript,javascript}.so`.** Land all in this story; consumer is S4-04. The lock-file SCHEMA is owned by `codegenie.grammars.lock.GrammarLockFile` (AC-20).

12. **Register the probe** via `src/codegenie/probes/__init__.py` additive import.

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

- **T-01** `test_probe_contract_attributes`: AC-1; instantiate probe; assert each class attribute matches expected value; assert `run.__qualname__` ends in `.run` and signature accepts `(self, repo, ctx)` (two-arg per ABC).
- **T-02** `test_build_scip_argv_shape`: AC-3; expected argv list verbatim against a fixture `repo.root` + `blob_path`.
- **T-03** `test_invocation_via_run_external_cli_only`: AC-3; AST-walk module; assert no `subprocess.run`/`Popen`/`os.system` calls anywhere.
- **T-04** `test_blob_lands_at_expected_path`: AC-4; **stub spelled out**:
  ```python
  async def _stub_writes_blob(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64*1024*1024, env_extra=None):
      out_path = Path(argv[argv.index("--output") + 1])
      out_path.write_bytes(b"FAKE-SCIP-BLOB")
      return ProcessResult(returncode=0, stdout=b'{"files_indexed":1}', stderr=b"")
  ```
  monkeypatch `codegenie.exec.run_external_cli` to `_stub_writes_blob`; run probe; assert `ctx.output_dir / "raw" / "scip-index.scip"` exists and is `b"FAKE-SCIP-BLOB"`; assert `slice["scip_index_uri"]` is the repo-relative POSIX form (e.g. `".codegenie/context/raw/scip-index.scip"` when `ctx.output_dir == repo.root / ".codegenie/context"`).
- **T-05** `test_slice_fields_localv2_compliance`: AC-5; stub `--summary-json` stdout with all optional fields; build `SemanticIndexSlice(...)` via `model_validate` of the slice; assert every required key is present and every optional key is present when supplied; assert `files_in_repo` counts ONLY `.ts/.tsx` (plant `.js` file; assert it is NOT counted).
- **T-06** `test_cache_key_sensitivity_via_probe_version_property`: AC-2; build a probe stub whose `version` returns `"0.1.0+scip-typescript-1.0.0"`, compute `key_for(probe_a, snapshot, task)`; rebuild with `version` returning `"0.1.0+scip-typescript-2.0.0"`; assert keys differ. Then plant two snapshots with different `.ts` content and the SAME `version`; assert keys differ (Merkle path via `content_hash_of_inputs`). Both arms of cache-key sensitivity verified against `cache/keys.py:142-148` directly (no mock of the cache layer).
- **T-07** `test_timeout_path_emits_typed_error` (AC-6): monkeypatch `run_external_cli` to raise `codegenie.errors.ProbeTimeoutError("simulated 300s timeout", probe_id="scip_index", timeout_s=300)`; run probe; assert slice contains `indexer_errors=1`, `warnings == ["scip_index.timeout"]`, `confidence="low"`; assert `.scip` blob does NOT exist (deleted); assert `scip.json` IS written; assert no exception escapes `run()`. Then load `scip.json` and feed through `codegenie.indices.registry.default_freshness_registry.dispatch_one(IndexName("scip"), {IndexName("scip"): json.loads(scip_json.read_bytes())}, head=last_indexed_commit)`; assert the returned `IndexFreshness` is `Stale` with `isinstance(stale.reason, IndexerError)` and `stale.reason.message == "indexer_reported_1_errors"` — proves the cross-story hand-off works end-to-end.
- **T-08** `test_non_zero_exit_path` (AC-7): monkeypatch to return `ProcessResult(returncode=2, stdout=b"", stderr=b"bad tsconfig\n")`; assert `indexer_errors=1`, `warnings == ["scip_index.exit_nonzero"]`, slice does NOT contain `stderr` text; assert structured log captured `stderr_tail="bad tsconfig\n"`; assert `scip.json` IS written.
- **T-09** `test_walker_exclusion_invariant` (AC-9): tempdir with `node_modules/extra.ts`, `dist/bar.ts`, `build/c.ts`, `.git/d.ts`, `src/baz.ts`, `src/quux.js` (NOT counted — `.js`), `src/zap.tsx`; assert `_count_indexable_files(root) == 2` (`baz.ts` + `zap.tsx`); assert `_compute_indexable_merkle(root)` is unchanged when `node_modules/extra.ts` is added vs. when not (symmetric exclusion proof). Both helpers route through `_walk_indexable_files`.
- **T-10** `test_tool_missing_path` (AC-8): monkeypatch `run_external_cli` to raise `codegenie.errors.ToolMissingError("scip-typescript")`; ALSO ensure `resolve_tool_version("scip-typescript")` returns `"unknown"` on the same exception (T-20 covers the resolver-side invariant); assert `indexer_version="unknown"`, `warnings == ["scip_index.tool_missing"]`; assert `scip.json` IS written; feed through S4-01's `scip_freshness` and assert `Stale(IndexerError("indexer_reported_1_errors"))`.
- **T-11** `test_raw_artifact_dir_unwritable` (AC-4): tempdir with `<output_dir>/raw` as a file (not dir); `mkdir(parents=True, exist_ok=True)` raises `FileExistsError`; probe emits AC-4's short-circuit slice; no `run_external_cli` invocation occurs (assert via spy that the stub was not called).
- **T-12** `test_warning_ids_match_adr_0007` (AC-13): iterate `_WARNING_IDS`; assert every member matches the Phase 1 ADR-0007 regex.
- **T-12b** `test_run_only_emits_declared_warning_ids` (AC-13): AST-walk `run()`; assert every string literal passed to `warnings.append(...)` is a member of `_WARNING_IDS`.
- **T-13** `test_registry_membership_heaviness_heavy` (AC-14).
- **T-19** `test_scip_json_keys_match_b2_consumer` (AC-16): run probe against a real-ish stubbed input set; load `<output_dir>/raw/scip.json`; assert the parsed dict has at minimum keys `{"last_indexed_commit", "files_indexed", "files_in_repo", "indexer_errors", "last_indexed_at"}` (B2's required set); feed through `scip_freshness(slice, head=last_indexed_commit)` and assert `isinstance(result, Fresh)` on a healthy run; vary one key at a time (drop `last_indexed_commit`, set `indexer_errors=1`, set `files_indexed=0`, set `last_indexed_commit="<other-sha>"`) and assert the expected `Stale(reason=...)` shape each time. This is the structural guarantee of the cross-story B2 hand-off.
- **T-Sj-2** `test_warm_cache_replays_scip_json` (AC-17): two consecutive `await probe.run(repo, ctx)` invocations with the same inputs; assert `scip.json` is present after the second AND its bytes equal the first run's bytes; assert `scip.json` is in `ProbeOutput.raw_artifacts` (both runs).
- **T-19b** `test_slice_envelope_and_scip_json_share_one_model` (AC-18): after a run, assert `schema_slice["semantic_index"]` and `json.loads(scip_json.read_bytes())` produce structurally identical dicts modulo nothing (single source of truth).
- **T-20** `test_resolve_tool_version_single_subprocess_per_process` (AC-19): spy on `run_external_cli`; call `await resolve_tool_version("scip-typescript")` twice; assert the spy was called exactly once. Then `clear_for_tests()`; call again; assert the spy was called exactly twice total. Also: stub `run_external_cli` to raise `ToolMissingError`; call `await resolve_tool_version("missing-binary")`; assert it returns `"unknown"` (does NOT raise — the probe's `version` property must be safe to read on tool-missing).
- **T-21** `test_grammars_lock_load_and_verify_happy_and_mismatch` (AC-20): tempdir with a valid `tools/grammars.lock` + matching vendored binary; `load_and_verify(root)` returns a `GrammarLockFile`. Tamper one byte of the vendored binary; `load_and_verify` raises `GrammarLoadRefused` with regex on the language name.

For `tools/grammars.lock`:
- **T-14** `test_grammars_lock_schema_and_blake3` (AC-10): parse `tools/grammars.lock` via `GrammarLockFile.model_validate_json(...)` (uses AC-20's typed loader); recompute BLAKE3 over each `file`; assert match.
- **T-15** `test_grammars_lock_lists_typescript_and_javascript` (AC-10): assert both languages are in the parsed `grammars` list.
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
- `src/codegenie/probes/layer_b/__init__.py`
- `src/codegenie/probes/layer_b/scip_index.py`
- `src/codegenie/probes/layer_b/scip_slice.py` — `SemanticIndexSlice` Pydantic smart constructor (AC-18).
- `src/codegenie/exec/tool_versions.py` — process-wide tool-version cache (AC-19). Note: `src/codegenie/exec.py` is currently a module; promoting it to a package (`src/codegenie/exec/__init__.py` re-exporting current public API) is the cleanest path. Implementer chooses module-vs-package; the cache must live in `codegenie.exec.tool_versions`.
- `src/codegenie/grammars/__init__.py`
- `src/codegenie/grammars/lock.py` — typed grammars-lock loader + `GrammarLoadRefused` (AC-20).
- `tests/unit/probes/layer_b/__init__.py`
- `tests/unit/probes/layer_b/test_scip_index.py`
- `tests/unit/exec/test_tool_versions.py`
- `tests/unit/grammars/__init__.py`
- `tests/unit/grammars/test_lock.py`
- `tools/grammars.lock` (data)
- `tools/grammars/typescript.so` (vendored binary — see AC-12)
- `tools/grammars/javascript.so` (vendored binary — see AC-12)
- `tools/regenerate_grammars_lock.sh` (executable)
- `tests/unit/tools/__init__.py`
- `tests/unit/tools/test_grammars_lock.py`

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — additive import line for `ScipIndexProbe`.
- `.gitattributes` — `tools/grammars/*.so binary`, `tools/grammars/*.dylib binary`.
- `pyproject.toml` — confirm `blake3` is in Phase 0 deps (it is per Phase 0 ADR — no edit needed); confirm `mypy.overrides` for the new modules if needed.

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
- **Why `probe.version` carries the tool version instead of a `scip-typescript-version:<resolved>` declared-input token (AC-2 + AC-19).** The performance lens originally proposed the special-token shape (matching ADR-0004's `image-digest:` mechanism). The problem: master's `cache/keys.py::declared_inputs_for` does `snapshot.root.rglob(pattern)` and silently drops anything that doesn't resolve to a file path; ADR-0004's token-recognizer dispatch on the cache layer is unimplemented (S1-09 — Done — added only the `ProbeContext.image_digest_resolver` field, not the `Cache._resolve_declared_inputs` dispatch arm). The `_OUTPUT_NAMESPACE = ".codegenie"` filter further strips any version-stamp file written under that namespace. So the token would be silently invariant on master. **The chokepoint that already exists** is `probe.version` — it's in the cache-key tuple at `cache/keys.py:146`. Routing the resolved tool version through `probe.version` (e.g., `f"0.1.0+scip-typescript-{resolved}"`) closes the gap with zero new mechanism, zero ADR amendment, and zero cache-layer edit. The pattern is **smart attribute + process-wide memo**; it composes with the `tool_versions` kernel (AC-19) so the subprocess fires lazily once per process. Future probes follow the same shape: declare `version` as a `@property`, route through `resolve_tool_version`.
- **Why `tool_versions` is a separate module instead of in-probe (AC-19).** Three+ Phase-2 probes need the same tool-version resolution (`scip-typescript`, `tree-sitter`, then in Phase 2 Layer G `grype`/`syft`/`semgrep`/`gitleaks`). Rule-of-three is crossed already. Keeping the memo in `scip_index.py` would (a) hide global state (a module-level `_resolved_version: str | None`) — fragile under pytest reordering and impossible to reset between tests, (b) make the next probe copy-paste the pattern, and (c) make the "one subprocess per binary per process" guarantee untestable from outside. Lifting to `codegenie.exec.tool_versions` with `clear_for_tests()` mirrors S1-02's `unregister_for_tests` precedent and makes the extension-by-addition guarantee mechanically verifiable.
- **Why `SemanticIndexSlice` is its own sibling module (AC-18).** Two consumers of the slice shape exist in this story alone: the `repo-context.yaml` envelope and `<raw>/scip.json`. A third consumer (S4-07's sub-schema generator) will call `SemanticIndexSlice.model_json_schema()` to emit the JSON Schema. A fourth consumer (Phase 3's `ScipAdapter`) will deserialize `scip.json` and want the same type. Lifting the model into `scip_slice.py` lets every consumer import the type without a circular dependency on the probe module. Mirrors S3-02's `RedactedSlice` smart-constructor precedent; the pattern is **smart constructor at the writer boundary** (validated at construction; immutable after).
- **Why `codegenie.grammars.lock` is its own module (AC-20).** This story writes `tools/grammars.lock` and tests it; S4-04 reads `tools/grammars.lock` at grammar-load time and refuses on BLAKE3 mismatch (`GrammarLoadRefused`, phase-arch row 10). Two consumers across two adjacent stories crossing the rule-of-three when counting `tools/regenerate_grammars_lock.sh` — extract now so the shape can't diverge. The pattern is **typed boundary for vendored data** (Pydantic `frozen=True` + `extra="forbid"` so a manual edit to the lock file fails parse, not deserialization at use).
- **`scip.json` is the load-bearing cross-story hand-off, not the `.scip` binary.** B2's `read_raw_slices` reads `<output_dir>/raw/<index_name>.json` files — never the binary. The `.scip` blob is Phase 3's `ScipAdapter` concern (Phase 2 is opaque). If you're tempted to skip writing `scip.json` because "the probe already wrote a blob," remember: B2 cannot parse SCIP; it reads the JSON sidecar. Per AC-16, the JSON sidecar MUST be written on every code path including timeout (AC-6), non-zero exit (AC-7), and tool-missing (AC-8) — otherwise B2 sees the sibling-missing path and fires `Stale(IndexerError("upstream_scip_unavailable"))`, which is the wrong typed signal for "the indexer ran but failed."
- **Empty-repo layer agreement (F-Cov-4 + F-Cov-6).** On a TypeScript repo with zero `.ts/.tsx` files: probe-side `confidence="low"` (the index is not informative); B2-side `Fresh(...)` (the index matches HEAD — `0 == 0`). The two layers disagree intentionally; both are correct in their own dimension. Do NOT add a "no .ts files → don't write scip.json" shortcut — that would make B2 fire `upstream_scip_unavailable`, which is wrong (the indexer did run; it just had no work).
- **`SecretRedactor` interaction (S3-03 → S4-03).** The `scip.json` content is generated from `SemanticIndexSlice.model_dump_json(...)` BEFORE the writer chokepoint applies `SecretRedactor`. Per S3-03, every slice that flows through the writer is redacted. `scip.json` contains only path counts, commit SHAs, and a version string — none of these are secrets — but the redactor MUST still see it (defense-in-depth). The probe writes `scip.json` to `ctx.output_dir / "raw"`; the writer's chokepoint (S3-03) is the one that processes it before publication. Do NOT bypass the chokepoint.
