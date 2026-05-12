# Phase 00 — Bullet tracer + project foundations: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-11
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [../../roadmap.md](../../roadmap.md) §"Phase 0"

## Executive summary

The engineer is building a single Python package (`src/codegenie/`) that ships a `codegenie gather <path>` CLI, dispatches one trivial probe (`LanguageDetectionProbe`) through the *real* coordinator, cache, schema validator, sanitizer, and audit writer, and lands every project convention (ruff, strict mypy, pytest+coverage, pre-commit, six-job CI, `mkdocs build --strict` over a curated `nav`) up front. The work is sequenced **contracts-first → foundations → harness internals → vertical slice → CI hardening** because Phase 0's value is exactly the seams it plants for Phases 1–14: the probe ABC (frozen by snapshot test), the `_ProbeOutputValidator` trust boundary, the BLAKE3-over-SHA-256 cache key tuple, the audit anchor, the `fence` CI job, and the `ProbeExecution = Ran | CacheHit | Skipped` coordinator output shape. Five steps. The load-bearing CI gates land with their step, not at the end; the `fence` job (ADR-0005 enforcement) lands in Step 1.

## Order of operations

The ordering principle is **contracts-first**, then foundations, then the vertical slice, then harden + CI gates. Specifically: (1) Step 1 plants the project skeleton plus the `fence` CI job — the executable enforcement of "no LLM in gather" — so every subsequent commit is checked against the load-bearing commitment from day one. (2) Step 2 lays down the immutable contracts every later phase consumes (probe ABC byte-for-byte from `localv2.md §4`, hashing module, subprocess allowlist, error hierarchy, JSON Schema envelope). (3) Step 3 builds the harness internals (cache, coordinator, validator, sanitizer, writer, audit) against those contracts and folds in the four gap-analysis items from `phase-arch-design.md §"Gap analysis"`. (4) Step 4 cuts the vertical slice — the CLI, the one probe, the three fixtures, the end-to-end smoke test including the cache-hit-on-second-run assertion that is the bullet tracer's load-bearing exit. (5) Step 5 closes the remaining CI gates and project-management artifacts that are conventions for every later phase. Tests live with their step, not at the end; the `fence` test ships *before* the dependency closure can drift.

## Step 1 — Establish project skeleton, tooling, and the `fence` CI job

**Goal:** A reviewer can clone the repo, run `make bootstrap && make check`, get a green check, and any PR that adds an LLM SDK to runtime `dependencies` is automatically rejected.

**Features delivered:**
- `pyproject.toml` (PEP 621, `hatchling` build backend, `requires-python >= 3.11`); runtime `dependencies` set to `click`, `pyyaml`, `jsonschema>=4.21`, `pydantic>=2`, `blake3`, `structlog`; `[project.optional-dependencies]` with `gather` (empty marker), `dev` (pytest, pytest-asyncio, pytest-cov, mypy, ruff, pre-commit, mkdocs-material, import-linter, pip-audit, osv-scanner), `service` (empty stub for Phase 9+), `agents` (empty stub for Phase 4+ — the LLM SDK landing zone).
- `uv.lock` committed; `Makefile` with `bootstrap`, `check`, `lint`, `typecheck`, `test`, `docs`, `fence`, `audit-verify` targets (all targets work with and without `uv`).
- `pyproject.toml` config for ruff (lint + format), strict mypy on `src/`, relaxed mypy on `tests/`, pytest (`--cov=src/codegenie --cov-branch --cov-fail-under=85`), coverage exclude for `cli.py`.
- `.pre-commit-config.yaml` with `ruff`, `ruff-format`, `mypy`, `gitleaks`, `forbidden-patterns` (bans `print(`, `yaml.load(` without `Loader=`, `shell=True`, `yaml.Dumper` without `CSafeDumper`), `check-yaml`, `check-toml`, `end-of-file-fixer`.
- `.editorconfig`, `.gitignore` (includes `.codegenie/` for this repo's own dogfood gathers), `mkdocs.yml` with a **curated `nav`** that excludes `docs/local.md`, `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`, `docs/context.md`, `docs/localv2.md` (each with a `# excluded: see final-design.md §2.2 / §5` comment).
- `.github/workflows/ci.yml` with six jobs: `lint`, `typecheck`, `test`, `security` (pip-audit + osv-scanner against `uv.lock`), `docs` (`mkdocs build --strict` path-filtered), `fence` (the load-bearing job). Matrix `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]`. Workflow concurrency group on `${{ github.ref }}`, actions pinned by SHA, `permissions: contents: read` at workflow level.
- `tests/unit/test_pyproject_fence.py` — asserts `set(distribution("codewizard-sherpa").requires) ∩ {"anthropic", "langgraph", "openai", "langchain", "transformers"} == set()`; includes a **deliberate-negative test** that plants `anthropic` in a synthetic `pyproject.toml` fixture and asserts the check fails. Scope is `dependencies` only — never `optional-dependencies` (edge case #15 in `phase-arch-design.md`).
- `import-linter` config blocking heavy modules (`pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`) from `cli.py` and `codegenie/__init__.py` — the structural defense for cold-start (replaces critique-flagged flaky canary).
- `src/codegenie/__init__.py`, `__main__.py`, `version.py` (single source of truth, read by `pyproject.toml` via `hatchling`'s version hook).
- `src/codegenie/errors.py` with `CodegenieError` root + subclass stubs (`ConfigError`, `ToolMissingError`, `ProbeError`, `ProbeTimeoutError`, `CacheError`, `SchemaValidationError`, `SecretLikelyFieldNameError`, `DisallowedSubprocessError`, `SymlinkRefusedError`).
- `src/codegenie/logging.py` — `structlog` JSON-on-non-TTY / pretty-on-TTY configuration; lifecycle event names declared as constants (`probe.start`, `probe.cache_hit`, `probe.skip`, `probe.success`, `probe.failure`, `probe.timeout`); module exports a single `configure_logging(verbose: bool)` callable.

**Done criteria:**
- [ ] `make bootstrap` installs a working dev environment on a clean macOS or Linux box.
- [ ] `make check` runs lint + typecheck + test + fence locally and exits 0.
- [ ] `pytest tests/unit/test_pyproject_fence.py -q` passes; the deliberate-negative branch is exercised and asserts failure.
- [ ] `mkdocs build --strict` is green over the curated `nav`.
- [ ] `import-linter` config blocks `from codegenie.cli import yaml` (synthetic test).
- [ ] CI's six jobs are wired and visible in the GHA tab (they may still fail until later steps land code — but the `lint`, `docs`, and `fence` jobs are green on the Step 1 PR).
- [ ] `tests/unit/test_logging.py` asserts JSON output on non-TTY and pretty output on TTY (capsys + isatty monkeypatch).
- [ ] Coverage gate is wired (`--cov-fail-under=85`); the Step 1 PR may run with coverage exempt on the empty `src/codegenie/` tree by passing `--cov-fail-under=0` *only* on this one PR, documented in the PR body as a Step 1 carve-out.

**Depends on:** Nothing prior. External prerequisite: Python 3.11+ available locally; GitHub Actions enabled on the repo.

**Effort:** M — touches many small files but each is mechanical; the `fence` deliberate-negative test takes care and the `mkdocs` curated `nav` requires reading the existing tree.

**Risks specific to this step:** `import-linter` regex syntax across the `codegenie.*` tree can over-block — keep the blocklist scoped to `cli.py` and `__init__.py` only, not `cli/**`. The `fence` test scope (`dependencies` only, never `optional-dependencies`) must be encoded so it can never be widened silently — assert it in the test itself.

## Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)

**Goal:** Every contract every later phase consumes is on disk, snapshot-tested where applicable, and one PR away from "you can't change me without an ADR amendment."

**Features delivered:**
- `src/codegenie/probes/base.py` — **byte-for-byte** from `localv2.md §4`: `Probe` ABC, `RepoSnapshot`, `Task`, `ProbeContext`, `ProbeOutput`, all `@dataclass`-based. No deviation; if `§4` says `dict[str, Any]`, the implementation says `dict[str, Any]`.
- `scripts/regen_probe_contract_snapshot.py` — generates `tests/snapshots/probe_contract.v1.json` by SHA-256-hashing a normalized representation (whitespace-collapsed, no trailing newlines) of `localv2.md §4`'s body extracted by section anchors.
- `tests/snapshots/probe_contract.v1.json` — the contract fingerprint committed.
- `tests/unit/test_probe_contract.py` — re-runs the normalization + hash and asserts the snapshot matches; failure mode message points at `templates/adr-amendment.md`.
- `src/codegenie/probes/registry.py` — `Registry` class with `register_probe` decorator, `all_probes()`, `for_task(task: str, languages: frozenset[str])`; `for_task` cached via `functools.lru_cache(maxsize=32)`; duplicate-name registration raises at decoration time; module-level `default_registry`.
- `src/codegenie/probes/__init__.py` — explicit-import list (no `importlib.metadata` entry-point scan).
- `src/codegenie/hashing.py` — the **only** file importing `blake3` and `hashlib.sha256`. Public API: `content_hash(path) -> "blake3:<64-hex>"`, `identity_hash(*parts) -> "sha256:<64-hex>"`, `content_hash_of_inputs(paths: Iterable[Path]) -> str` (sorts `(path, size)` tuples). `blake3` imported lazily inside `content_hash`.
- `src/codegenie/exec.py` — `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})`; `ProcessResult` frozen dataclass; `async def run_allowlisted(argv, *, cwd, timeout_s, env_extra={})` via `asyncio.create_subprocess_exec(..., shell=False)`. Env filtered to `{PATH, HOME, LANG, LC_ALL}` ∪ `env_extra`; strips `SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. `cwd` resolved and must be under analyzed-repo root. SIGKILL at `1.5 × timeout_s`. Weakref process-tracking table for coordinator-cancel SIGKILL.
- `src/codegenie/schema/repo_context.schema.json` — Draft 2020-12 envelope with `additionalProperties: false` at root and `additionalProperties: true` under `probes.*`; `$id` versioned (`v0.1.0`).
- `src/codegenie/schema/probes/language_detection.schema.json` — per-probe sub-schema for `LanguageDetectionProbe` (declares `$id` for the schema-version axis Gap 1 addresses).
- `src/codegenie/schema/validator.py` — `validate(repo_context: dict) -> None`; `jsonschema.Draft202012Validator` compiled once behind `functools.lru_cache`. Composes per-probe sub-schemas via `$ref`. Raises `SchemaValidationError` with JSON Pointer of failure.
- `src/codegenie/audit.py` — `RunRecord` and `ProbeExecutionRecord` Pydantic models (per Gap 2: `ProbeExecutionRecord` includes both `cache_key` *and* `blob_sha256`). `AuditWriter.record(run_record, output_dir) -> Path` writes `runs/<utc-iso>-<short>.json` mode `0600`. `codegenie audit verify` subcommand stub re-reads run records and recomputes `yaml_sha256` + `blob_sha256` for every claimed `cache_key`.
- `templates/adr-amendment.md` — the PR template referenced by the snapshot-drift failure message.

**Done criteria:**
- [ ] `tests/unit/test_probe_contract.py` passes against the snapshot; manually editing `localv2.md §4` causes the test to fail with a message pointing at `templates/adr-amendment.md`.
- [ ] `tests/unit/test_hashing.py` asserts `content_hash` and `identity_hash` are deterministic (same input → same hex), prefix-tagged (`blake3:` / `sha256:`), and that `content_hash_of_inputs` is sort-stable across input ordering.
- [ ] `tests/unit/test_exec.py` covers: allowlist rejection (`bash` raises `DisallowedSubprocessError`), env-strip (`OPENAI_API_KEY` never reaches child), `cwd` escape rejection, timeout → `ProbeTimeoutError`, `git rev-parse HEAD` happy path against a real git fixture.
- [ ] `tests/unit/test_registry.py` covers: `@register_probe`, duplicate-name rejection, `for_task` filtering by `applies_to_tasks` and `applies_to_languages` with `["*"]` semantics, `lru_cache` hit on repeated calls.
- [ ] `tests/unit/test_schema_validation.py` validates a hand-crafted minimal envelope; a `additionalProperties: false` violation at the root fails; a `probes.unknown.field` succeeds (loose at `probes.*`).
- [ ] `tests/adv/test_no_shell_true.py` AST-scans `src/codegenie/` for `shell=True` and fails if any is found.
- [ ] `tests/adv/test_no_network_imports.py` AST-scans `src/codegenie/` and fails on `httpx`, `requests`, `urllib3`, `socket`, `urllib.request`.
- [ ] `tests/adv/test_yaml_unsafe_load.py` AST-scans for `yaml.load(` without `Loader=` and fails.
- [ ] All Step 2 code passes strict mypy.

**Depends on:** Step 1 (the pyproject + Makefile + lint config).

**Effort:** M — the snapshot-test mechanics and the sub-schema `$ref` composition are the only non-mechanical pieces; the rest is contract transcription.

**Risks specific to this step:** The byte-for-byte transcription of `localv2.md §4` is error-prone. Diff the file against §4 manually before opening the PR; the snapshot test will catch drift but a transcription mistake encoded on day one *is* the snapshot — write the regen script first and run it from a fresh extraction of §4, not from your retyped version.

## Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)

**Goal:** The runtime path from `ProbeOutput` through cache, validation, sanitization, schema check, and atomic write exists and is unit-tested in isolation, with every gap-analysis item from `phase-arch-design.md` folded in.

**Features delivered:**
- `src/codegenie/cache/keys.py` — `key_for(probe, snapshot, task)` returns `identity_hash(probe.name, probe.version, per_probe_schema_version(probe), content_hash_of_inputs(declared_inputs))`. **`per_probe_schema_version`** falls back to `envelope_schema_version` if the probe has no sub-schema; the envelope version itself is **not** in the key (Gap 1).
- `src/codegenie/cache/store.py` — `CacheStore.get(key) -> ProbeOutput | None`, `.put(key, output) -> None`, `.key_for(...)`. Storage: `.codegenie/cache/index.jsonl` (append-only, `O_APPEND`, records ≤ 4096B) + `.codegenie/cache/blobs/<2-char-shard>/<blake3-hex>.json`. Atomic write via `<dest>.tmp → fsync → os.replace`. Permissions `0700` dir / `0600` files; `os.chmod` re-applied post-write. Index read is plain buffered (no mmap). Corruption + hash-mismatch + TTL-stale all collapse to miss + log + re-run.
- `src/codegenie/coordinator/validator.py` — `_ProbeOutputValidator` Pydantic v2 model: `model_config = ConfigDict(frozen=True, extra="forbid")`; `schema_slice: dict[str, JSONValue]` with recursive `JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]`; `confidence: Literal["high", "medium", "low"]`; field-validator rejects field names matching the secret regex (`/(?i)(token|secret|password|api[_-]?key|credential|private[_-]?key|ghp_|sk-)/`) → `SecretLikelyFieldNameError`. Lazy-imported by the coordinator.
- `src/codegenie/coordinator/snapshot.py` — `RepoSnapshot` constructor using `exec.run_allowlisted("git", ["rev-parse", "HEAD"], cwd=path, timeout_s=10)`; `git_commit=None` if not a git repo.
- `src/codegenie/coordinator/coordinator.py` — `async def gather(snapshot, task, probes, config, cache, sanitizer) -> GatherResult`. `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`; per-probe `asyncio.create_task` + `asyncio.wait_for(probe.timeout_seconds)`; hard kill at `1.5 × timeout_seconds` via `cancel()` + 100ms grace. Probe exceptions caught into `ProbeOutput(errors=[...], confidence="low")`. Each output flows through `_ProbeOutputValidator` then `OutputSanitizer.scrub` *in the coordinator* before `cache.put` + merge. `GatherResult` frozen dataclass with `outputs: dict[str, ProbeOutput]` and `executions: dict[str, ProbeExecution]`; `ProbeExecution = Ran | CacheHit | Skipped` union via frozen dataclasses.
- **Coordinator prelude pass (Gap 4)** — the coordinator runs probes with `tier="base"` and `applies_to_languages=["*"]` first; constructs an `enriched_snapshot` via `dataclasses.replace(snapshot, detected_languages=prelude_output["language_stack"]["counts"])`; dispatches remaining probes against the enriched snapshot.
- **Per-probe resource budget (Gap 3)** — `Probe.declared_resource_budget` class attribute with default `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)`. Coordinator enforces `wall_clock_s` (already via `wait_for`) and `raw_artifact_mb` via a `BudgetingContext` injected as `ProbeContext.workspace`. RSS is **advisory** in Phase 0 (`probe.rss.warn` event); hard enforcement deferred to Phase 14.
- **Audit anchors (Gap 2)** — Coordinator records `cache_key` and `blob_sha256` for every probe execution; `AuditWriter` persists both in `ProbeExecutionRecord`. `codegenie audit verify` re-reads claimed blobs and recomputes `blob_sha256`.
- `src/codegenie/output/sanitizer.py` — `OutputSanitizer.scrub(output, repo_root) -> SanitizedProbeOutput`. Pass 1: field-name regex (defense in depth — `_ProbeOutputValidator` is the first line). Pass 2: absolute-path → relative-path rewriting for any string matching `^(/Users/|/home/|/root/|<analyzed-repo-abs>/)`. No `gitleaks` synchronously.
- `src/codegenie/output/writer.py` — `Writer.write(envelope, raw_artifacts, output_dir)`. `yaml.CSafeDumper` with fallback to pure-Python `yaml.SafeDumper` on `ImportError` (edge case #13). Atomic publish: write `raw/` files first, write `repo-context.yaml.tmp`, fsync, `os.replace`. Files `0600`, dirs `0700`, re-applied via `os.chmod` post-write. Refuses to overwrite a symlink target (raises `SymlinkRefusedError` → CLI exit 5).
- `src/codegenie/output/paths.py` — helpers for `<repo>/.codegenie/context/` layout.
- `src/codegenie/config/defaults.py` — `Config` frozen `@dataclass`; fields: `max_concurrent_probes: int = 8`, `cache_ttl_hours: int = 24`, `enable_audit: bool = True`. Fields are additive; not a frozen contract.
- `src/codegenie/config/loader.py` — three-source merge (defaults < `~/.codegenie/config.yaml` < `<repo>/.codegenie/config.yaml` < CLI overrides); unknown keys raise `ConfigError` with `difflib.get_close_matches` "did you mean?" suggestion; env-var expansion off (`auto_envvar_prefix=None` at the click level).

**Done criteria:**
- [ ] `tests/unit/test_cache_store.py` covers `get/put/key_for` happy path, corruption-as-miss, hash-mismatch-as-miss, post-write mode `0600`, atomic write (kill mid-write → no partial file visible).
- [ ] `tests/unit/test_cache_invalidation_scope.py` (Gap 1) asserts that bumping `NodeManifestProbe`'s sub-schema `$id` does **not** invalidate `LanguageDetectionProbe`'s cache entry, and that bumping the envelope `$id` invalidates **nothing**.
- [ ] `tests/unit/test_probe_output_validator.py` covers the JSONValue rejections (`bytes`, `Callable`), the secret field-name rejection, the `Literal["high","medium","low"]` enforcement, and an `extra="forbid"` rejection of extra fields.
- [ ] `tests/unit/test_coordinator.py` covers single-probe dispatch, the prelude-pass enrichment (Gap 4: a downstream mock-probe asserts it received the enriched `detected_languages`), failure-isolation (probe raises → others continue), timeout-then-SIGKILL, and the `raw_artifact_mb` budget cutoff.
- [ ] `tests/unit/test_output_sanitizer.py` covers field-name pass, absolute-path scrubbing (including the analyzed-repo prefix), and that the sanitizer is idempotent.
- [ ] `tests/unit/test_output_writer.py` covers atomic-replace, `0600`/`0700` modes, symlink-refusal, and the `yaml.CSafeDumper` fallback (monkeypatch the import).
- [ ] `tests/unit/test_config_loader.py` covers the three-source merge, unknown-key rejection with did-you-mean, and env-var-expansion-off.
- [ ] `tests/unit/test_audit_anchors.py` (Gap 2) asserts `cache_key` and `blob_sha256` are populated for every probe execution and that `audit verify` reports a mismatch when a blob is tampered with.
- [ ] All Step 3 code passes strict mypy.

**Depends on:** Step 2 (the contracts).

**Effort:** L — this is the densest step in the phase. The four gap-analysis items each add a few lines of code and a focused test; the prelude-pass coordinator logic is the only piece with non-trivial control flow.

**Risks specific to this step:** The prelude-pass design (Gap 4) is easy to over-engineer — keep it to "any probe with `tier='base'` runs first; its output enriches the snapshot via `dataclasses.replace`." Resist building a generalized DAG scheduler; that lands in Phase 1 if the six Layer A probes actually need it. The `raw_artifact_mb` budget enforcement needs care so it doesn't false-positive on small writes — track bytes written through `ProbeContext.workspace` only, not bytes written elsewhere.

## Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke

**Goal:** `codegenie gather <path>` runs end-to-end on empty / JS-only / polyglot fixtures, writes `.codegenie/context/repo-context.yaml`, and the cache-hit-on-second-run assertion (the bullet tracer's load-bearing exit) is green in CI.

**Features delivered:**
- `src/codegenie/probes/language_detection.py` — `LanguageDetectionProbe(Probe)`. `declared_inputs` is the language-extension glob list (`.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.py`, `.go`, `.rs`, `.java`, `.rb`, `.php`) — **not** `["**/*"]` (critical for the cache-hit-on-non-empty-fixture exit per Scenario 2). `applies_to_tasks=["*"]`, `applies_to_languages=["*"]`, `tier="base"` (engages the prelude-pass). Implementation: `os.scandir` walk, count by extension, emit `schema_slice = {"language_stack": {"counts": {...}, "primary": <max>}}`. Symlinks resolving outside the repo root are skipped (edge case #4). No tree-sitter, no Dockerfile detection.
- Register `LanguageDetectionProbe` in `src/codegenie/probes/__init__.py`.
- `src/codegenie/cli.py` — `click` group with subcommands `gather <path>`, `audit verify`, `cache gc` (stub). Global flags: `--verbose`, `--version`, `--refresh-tools`, `--no-gitignore`, `--auto-gitignore`. **All** heavy imports (`pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`, `yaml.CSafeDumper`) deferred inside command function bodies. `Path.resolve(strict=True)` validates `<path>`; symlinks crossing outside refused. Exit codes documented in `--help`: 0 success / 1 unhandled / 2 all probes failed / 3 schema validation / 4 reserved / 5 symlink refused / 6 secret-field rejected at sanitizer.
- `src/codegenie/cli.py` startup path: configure logging → tool-readiness check (Phase 0: `git` only; cached at `~/.codegenie/.tool-cache.json` mode `0600`; `--refresh-tools` re-detects) → maybe-prompt `.gitignore` mutation → load `Config` → construct `RepoSnapshot` via `exec.run_allowlisted` → resolve probes via `default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))` → `await coordinator.gather(...)` → shallow-merge `schema_slice` entries into envelope → validate against JSON Schema (write `.yaml.invalid` + exit 3 on failure) → `Writer.write(...)` → `AuditWriter.record(...)` → exit 0/2 based on `GatherResult`.
- `.gitignore` mutation routine: checks for `.codegenie/` substring in `<repo>/.gitignore`; appends atomically if absent and stdin is a TTY (after a yes/no prompt); structured warning `gitignore.append.skipped` on non-TTY. `--auto-gitignore` overrides to "always append"; `--no-gitignore` overrides to "never touch."
- `tests/fixtures/empty_repo/` — single `.gitkeep`.
- `tests/fixtures/js_only/` — 3 `.js`, 1 `.mjs`, 1 `.cjs`, a `README.md` (the README is what makes the cache-hit-on-non-empty test load-bearing — editing it between two runs must **not** invalidate the cache).
- `tests/fixtures/polyglot/` — JS + TS + Py + Go + Rust source files (one or two each); exercises every language branch of `LanguageDetectionProbe`.
- `tests/smoke/test_cli_end_to_end.py` — runs `codegenie gather --help` (exit 0, lists every flag), `codegenie gather <empty>` (exit 0, writes envelope with `language_stack.counts == {}`), `codegenie gather <js_only>` (exit 0, `language_stack.primary == "javascript"`), `codegenie gather <polyglot>` (exit 0, all five languages present).
- `tests/smoke/test_cli_end_to_end.py::test_cache_hit_on_second_run` — runs `gather <js_only>` twice; **monkeypatches `os.scandir`** to count invocations between the two runs; asserts the second run's invocation count is zero; asserts the coordinator's `executions["language_detection"]` is `CacheHit`; asserts `probe.cache_hit` structlog event was emitted; edits `README.md` in the fixture between runs and asserts the cache still hits (because `README.md` is not in `declared_inputs`).
- `tests/unit/test_cli_exit_codes.py` — covers 0/2/3/5/6 paths with mocks.
- `tests/unit/test_gitignore_mutation.py` — TTY-accept (atomic append happens), TTY-decline (no mutation), non-TTY-skip (warning logged, no mutation), `--auto-gitignore`, `--no-gitignore`, append-failure (disk-full simulation → warning, gather continues — edge case #8), already-present (idempotent no-op).
- `tests/unit/test_language_detection_probe.py` — golden-ish output assertions over each fixture; symlink-escape behavior (edge case #4); permission-error mid-walk falls into the probe-failure path with `confidence="low"` (edge case #1).
- `tests/adv/test_path_traversal.py` — `<path>` containing `..` resolves outside the working repo → refused.
- `tests/adv/test_symlink_escape.py` — symlink inside the fixture pointing at `/etc/hosts` → entry skipped with `probe.symlink.escaped` event.
- `tests/adv/test_secret_leak.py` — a synthetic probe emits `schema_slice = {"github_token": "ghp_..."}`; `_ProbeOutputValidator` raises `SecretLikelyFieldNameError`; coordinator marks the probe failed; gather continues if other probes succeeded (or exits 2 if all failed).
- `tests/adv/test_env_var_strip.py` — sets `OPENAI_API_KEY=test` in the parent env, runs `gather`, asserts the value never reaches `git rev-parse` (mock subprocess + inspect env arg).
- `codegenie audit verify` subcommand fully wired: walks `.codegenie/runs/`, re-reads claimed blobs, recomputes `blob_sha256`, recomputes `yaml_sha256` from the persisted YAML, reports zero mismatches on the smoke run.

**Done criteria:**
- [ ] `codegenie gather --help` exits 0 and lists every documented flag.
- [ ] `codegenie gather` exits 0 on all three fixtures locally and in CI.
- [ ] The cache-hit-on-second-run test passes; `os.scandir` invocation count is zero on the second run; structured event `probe.cache_hit` is emitted exactly once.
- [ ] `codegenie audit verify` on the smoke run reports zero mismatches.
- [ ] `.gitignore` mutation tests cover both TTY-accept and non-TTY-skip branches.
- [ ] Adversarial tests (`tests/adv/test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) pass.
- [ ] Coverage ≥ 85% line / ≥ 75% branch on `src/codegenie/` excluding `cli.py` (the `--cov-fail-under=85` gate is now real).
- [ ] All Step 4 code passes strict mypy.

**Depends on:** Step 3 (the harness internals).

**Effort:** M — wiring is mechanical; the `LanguageDetectionProbe` is simple; the cache-hit-on-second-run monkeypatch and the `.gitignore` mutation TTY/non-TTY split take care.

**Risks specific to this step:** The `os.scandir` monkeypatch for the cache-hit test must be applied at the right import site — `LanguageDetectionProbe`'s walker calls `os.scandir` directly, so monkeypatch `os.scandir` on the `language_detection` module, not on the `os` module globally. The `.gitignore` mutation routine has many branches; resist building a state machine — straight-line `if/elif` keeps it readable and testable.

## Step 5 — Close the remaining CI gates and project conventions

**Goal:** All six CI jobs are green on `main`; the remaining adversarial tests, performance canaries, project-management artifacts, and contributor docs are in place; Phase 0's handoff to Phase 1 is shippable.

**Features delivered:**
- `tests/adv/test_yaml_unsafe_load.py` (if not landed in Step 2 — port + extend to cover the YAML writer's `CSafeDumper` selection).
- `tests/bench/test_cli_cold_start.py` — p50 of 5 `codegenie --help` runs; posts a PR comment with the number; **advisory only**, never blocks merge.
- `tests/bench/test_coordinator_overhead.py` — dispatch + merge + write for 1 no-op probe; PR comment; advisory.
- `tests/bench/test_cache_hit_dispatch.py` — second-run vs first-run ratio; PR comment; advisory.
- `tests/unit/test_cache_concurrent.py` — two concurrent `codegenie gather` invocations against the same `.codegenie/cache/index.jsonl`; asserts the JSONL parses line-by-line and both gathers succeed (edge case #12).
- `.github/ISSUE_TEMPLATE/new-probe.md`, `.github/ISSUE_TEMPLATE/new-skill.md`, `.github/ISSUE_TEMPLATE/adr-amendment.md` — render in the GitHub UI.
- `.github/dependabot.yml` — weekly Python + GitHub Actions updates.
- `.github/CODEOWNERS` — maps `src/codegenie/probes/base.py`, `localv2.md`, `docs/production/adrs/`, and `tests/snapshots/` to a reviewer set that gates the contract-frozen files.
- `.github/PULL_REQUEST_TEMPLATE.md` — includes a checkbox for "Touches a contract-frozen file? If yes, link the ADR amendment PR."
- GitHub Project board: Phase 0 milestone closed; Phase 1 milestone created with issues aligned to `roadmap.md` §"Phase 1" (NodeBuildSystem, NodeManifest, CI, Deployment, TestInventory + tree-sitter for ambiguous LanguageDetection cases).
- `docs/contributing.md` — bootstrap, run tests, run the docs site, the "adding a probe" cheat sheet (anticipating Phase 1).
- `docs/phases/00-bullet-tracer-foundations/README.md` updated with the final exit-criteria checklist marked complete.
- A Phase 1 issue filed for the `mkdocs` `nav` cleanup (uncuratable docs get a follow-up PR to either fix or delete).
- A Phase 1 issue filed for documenting probe-version-bump conventions (open question #2 in `phase-arch-design.md §"Open questions"`).
- A Phase 1 issue filed for the `aiofiles` mention in `roadmap.md` §"Phase 0" (documentation bug per L3 row 15).
- All six CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) are green on the `main` branch's HEAD commit on both Python 3.11 and 3.12 on `ubuntu-24.04`.
- Coverage ratchet documented in `docs/contributing.md`: 85/75 in Phase 0 → 87/77 in Phase 1 → 90/80 in Phase 2 (open question #5).

**Done criteria:**
- [ ] All six CI jobs green on `main` on Python 3.11 *and* Python 3.12.
- [ ] CI walltime p95 ≤ 90s (advisory; if exceeded for two consecutive weeks, an auto-issue opens per `final-design.md §3.2`).
- [ ] All seven adversarial tests in `tests/adv/` pass: `test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`, `test_yaml_unsafe_load.py`, `test_no_shell_true.py`, `test_no_network_imports.py`.
- [ ] The three performance canaries run in CI and post advisory PR comments (no merge gate).
- [ ] All three issue templates (`new-probe`, `new-skill`, `adr-amendment`) render correctly in the GitHub UI when "New Issue" is clicked.
- [ ] `CODEOWNERS` blocks a synthetic PR touching `src/codegenie/probes/base.py` without the designated reviewer.
- [ ] Phase 1 milestone exists with issues for the five remaining Layer A probes + the three follow-up issues filed above.
- [ ] `docs/contributing.md` builds in `mkdocs build --strict` and links into the curated `nav`.

**Depends on:** Step 4 (the vertical slice — needed before the perf canaries and the smoke-coverage gates can be meaningful).

**Effort:** S — most items are configuration files and templates; the adversarial tests that didn't land in Step 2 are short.

**Risks specific to this step:** Performance canaries on GHA shared runners are variance-prone — keep them advisory, do not make any of them a merge gate (this is the explicit decision in L3 row 12). The `CODEOWNERS` file must use paths the GitHub UI honors (no trailing slashes ambiguity) — test it by opening a synthetic PR before closing the phase.

## Exit-criteria mapping

Every Phase 0 exit criterion from `docs/roadmap.md` §"Phase 0" — and every refined exit criterion from `final-design.md §11` and `phase-arch-design.md §"Goals"` — traces to a step.

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| `codegenie gather` runs on any directory | Step 4 |
| Prints external-tool readiness | Step 4 (tool-readiness check inside CLI startup) |
| Executes `LanguageDetection` | Step 4 |
| Writes `.codegenie/context/repo-context.yaml` | Step 4 |
| CI is green on `main` | Step 5 (with `lint`/`docs`/`fence` green from Step 1; `test`/`typecheck`/`security` go green progressively) |
| Docs site builds locally without warnings (`mkdocs build --strict` over curated `nav`) | Step 1 (curated `nav`) + Step 5 (final green on `main`) |
| Probe contract from `localv2.md §4` preserved byte-for-byte (snapshot-pinned) | Step 2 |
| `LanguageDetectionProbe` executes through the real coordinator + cache + validator + sanitizer + audit writer | Steps 3 + 4 |
| Cache hits on a non-empty fixture's second run | Step 4 (test) + Step 3 (CacheStore) |
| Six CI jobs green on `python: ["3.11", "3.12"]` × `os: [ubuntu-24.04]` | Step 1 (wired) + Step 5 (final green) |
| `mkdocs build --strict` over curated `nav` green | Step 1 (curated `nav`) + Step 5 (final green) |
| `fence` job blocks LLM SDKs from `dependencies` (with deliberate-negative test) | Step 1 |
| Coverage ≥ 85% line / ≥ 75% branch on `src/codegenie/` excluding `cli.py` | Step 4 (gate goes live) + Step 1 (gate wired) |
| `codegenie audit verify` over smoke run reports zero mismatches | Step 4 |
| `.gitignore` mutation path exercised for TTY-accept and non-TTY-skip | Step 4 |
| Pre-commit hooks installed by `make bootstrap`; commit with lint violation / `shell=True` / unsafe `yaml.load` blocked | Step 1 |
| Issue templates render in GitHub UI (`new-probe`, `new-skill`, `adr-amendment`) | Step 5 |
| Probe ABC snapshot test passes; drift fails CI | Step 2 |
| External-tool readiness check (Phase 0: `git`) caches at `~/.codegenie/.tool-cache.json` | Step 4 |

No exit criterion is unmapped. Every step appears in the table — none is out of scope.

## Implementation-level risks

Distinct from the design-level risks in `phase-arch-design.md`. These are about *the work*.

1. **The `localv2.md §4` byte-for-byte transcription in Step 2 is the single most consequential risk.** A transcription error encoded on Day 1 is the snapshot — every later phase inherits the bug. **Signal it's going sideways:** the snapshot test passes locally but the implementation diverges from §4 on close reading. **What to do:** the regen script (`scripts/regen_probe_contract_snapshot.py`) must extract §4 from `localv2.md` programmatically (by section anchors), not from a retyped copy. Write the regen script *before* writing `probes/base.py`, generate the snapshot, then implement `base.py` and run the test. Manually diff `base.py` against `localv2.md §4` before opening the Step 2 PR.

2. **Step 3 is the densest step; gap-analysis items can be deferred silently.** Each of the four gap items (schema-version scoping in the cache key, audit-anchor dual fields, per-probe resource budget, coordinator prelude pass) is a small code change with a focused test, but if any one is dropped, Phase 1 will hit it. **Signal:** PR review checklist for Step 3 includes "all four gap-analysis tests are present and pass." **What to do:** Land the four gap tests *first* (red), then the implementation (green) — TDD discipline on the gap items specifically, not on the rest of Step 3.

3. **The cache-hit-on-second-run test (the bullet tracer's load-bearing exit) is monkeypatch-sensitive.** Wrong monkeypatch target → false-positive green. **Signal:** the test passes but a manual second-run on a real repo still re-walks the filesystem (observable by tracing `strace -e scandir` or by adding a temporary print). **What to do:** Monkeypatch `os.scandir` at the `language_detection` module level (`monkeypatch.setattr("codegenie.probes.language_detection.os.scandir", ...)`), assert the patched callable is invoked zero times, and additionally assert the `probe.cache_hit` structlog event is emitted exactly once on the second run as a redundant signal.

4. **The `fence` test scope can drift.** If a future contributor (or Phase-1 author) widens the scope to include `optional-dependencies` (e.g., to "future-proof against agent SDKs in `dev`"), the load-bearing commitment is silently weakened. **Signal:** PR review of any change to `test_pyproject_fence.py` that touches the scope. **What to do:** Assert the scope inside the test itself (a separate test that the fence's target is `dependencies` only) and route `test_pyproject_fence.py` to `CODEOWNERS` so any change requires designated review.

5. **Strict mypy on `src/` with `pydantic` v2 has known friction (especially around `dataclasses.replace` + frozen Pydantic models).** **Signal:** Step 3 starts but `make typecheck` becomes a yak-shave. **What to do:** Pin `mypy` to a version known to play well with `pydantic` v2 (≥ `1.10`); use `pydantic.mypy` plugin; keep frozen-Pydantic and frozen-`@dataclass` types segregated by module (validator is Pydantic, contracts are dataclass — never one inside the other).

## What's next — handoff to Phase 1

After Phase 0 ships, the system materially changes in these ways. Phase 1 (`roadmap.md` §"Phase 1") picks up here.

- **New artifacts now on disk:**
  - `.codegenie/context/repo-context.yaml` (envelope, schema-version `0.1.0`) on every analyzed repo.
  - `.codegenie/context/raw/<probe>.json` (per-probe slices — currently only `language_detection.json`).
  - `.codegenie/context/runs/<utc-iso>-<short>.json` (audit records with `cache_key` + `blob_sha256` per probe).
  - `.codegenie/cache/index.jsonl` + `blobs/<shard>/<blake3>.json` (content-addressed cache).
  - `~/.codegenie/.tool-cache.json` (tool-readiness cache, mode `0600`).
  - `tests/snapshots/probe_contract.v1.json` (the `localv2.md §4` fingerprint; ADR amendment required to regenerate).
- **New contracts ready for Phase 1 consumers:**
  - `Probe` ABC at `src/codegenie/probes/base.py` — Phase 1 adds `NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory` as new files; never edits `base.py`.
  - `@register_probe` decorator + `Registry` shape — drop new probes in via explicit imports in `probes/__init__.py`.
  - `_ProbeOutputValidator` recursive `JSONValue` trust boundary — Phase 1 probes inherit field-name and shape guarantees for free.
  - `GatherResult` + `ProbeExecution = Ran | CacheHit | Skipped` — Phase 1's six probes dispatch through the same `Semaphore`-bounded `gather`; Phase 14's incremental gather extends without re-shaping.
  - `CacheStore` API (`get/put/key_for`) + the SHA-256-over-BLAKE3 key tuple; per-probe-sub-schema scoping (Gap 1) means Phase 1's per-probe sub-schemas can bump without invalidating each other's caches.
  - `OutputSanitizer.scrub` two-pass — every new probe inherits field-name + path-scrubbing defenses without per-probe code.
  - `exec.ALLOWED_BINARIES` — Phase 1 adds `tree-sitter`, `scip-typescript`, etc.; each addition is a one-line PR change with `CODEOWNERS`-forced review.
  - JSON Schema envelope (`additionalProperties: false` root / `true` under `probes.*`) + per-probe sub-schemas via `$ref` under `src/codegenie/schema/probes/`.
  - Coordinator prelude pass (Gap 4) — `tier="base"` probes run first; downstream probes filter on `enriched_snapshot.detected_languages`. Phase 1's `NodeManifestProbe` uses this directly.
  - `Probe.declared_resource_budget` (Gap 3) — Phase 1's six probes each set explicit `raw_artifact_mb` budgets in the probe class definition; coordinator enforcement is already wired.
  - Audit anchors (Gap 2) — `cache_key` + `blob_sha256` per probe execution; Phase 11's PR provenance and Phase 13's cost ledger consume these without extension.
- **New CI gates in place:**
  - `fence` (ADR-0005 enforcement) — every PR is checked against the LLM-SDK blocklist.
  - `lint`, `typecheck`, `test` (with `--cov-fail-under=85`), `security` (pip-audit + osv-scanner), `docs` (`mkdocs build --strict`).
  - `import-linter` blocks heavy imports from `cli.py` and `__init__.py` (the structural cold-start defense).
  - Probe ABC snapshot drift fails CI; `CODEOWNERS` blocks unreviewed changes to the snapshot or the `base.py` source.
- **Implicit assumptions Phase 1 can now make:**
  - The gather pipeline is deterministic end-to-end (the `fence` test guarantees no LLM dep can creep in).
  - Concurrent gathers do not corrupt the cache (`O_APPEND` JSONL + atomic blob writes — tested in `test_cache_concurrent.py`).
  - Failure isolation is real — a Phase 1 probe raising mid-walk does not poison the other five.
  - Atomic `os.replace` on the YAML — Phase 1's integration tests can read the YAML mid-gather and see only the prior or new state, never half.
  - The `LanguageDetectionProbe`'s `declared_inputs` are extension-scoped, not `["**/*"]` — Phase 1 probes narrow further (e.g., `NodeManifestProbe`'s inputs are `package.json` + `package-lock.json` + `yarn.lock` + `pnpm-lock.yaml`) without breaking the cache invariant.
  - The coverage ratchet schedule is documented (85/75 → 87/77 in Phase 1 → 90/80 in Phase 2).
- **Issues filed for Phase 1 that surface from Phase 0:**
  - `mkdocs` `nav` cleanup (fix or delete the currently-excluded docs).
  - Probe-version-bump conventions documented in a "adding a probe" guide (`docs/contributing.md` extension).
  - Remove `aiofiles` from `roadmap.md` §"Phase 0" tooling list (documentation bug per L3 row 15).
  - Coverage ratchet to 87/77.
  - Reproducibility CI check (lands when there's non-determinism in probe outputs to surface — SCIP, runtime traces).
