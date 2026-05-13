# Story S4-02 — CLI `gather` + `audit verify` + tool-readiness check

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready — HARDENED 2026-05-13
**Effort:** M
**Depends on:** S3-06, S4-01
**ADRs honored:** ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0012, ADR-0013

## Validation notes (2026-05-13)

This story was hardened by `phase-story-validator` before going to the executor. Major changes:

- **Goal narrowed.** The three fixtures (`empty_repo/`, `js_only/`, `polyglot/`) are S4-04's territory (per the Out-of-scope section); the Goal now anchors on a per-test `<tmp_path>` instead. Smoke-against-fixtures verification belongs to S4-04.
- **Exit-code namespace clarified.** Phase-arch §Component design/CLI documents `0/2/3/4/5/6` for the CLI as a whole; the original AC-4 elided code `4` (owned by `audit verify` mismatch, already shipped in `src/codegenie/cli.py` from S3-06) and added code `1` to the documented success set. AC-4 now splits the namespace: `gather`'s documented codes are `0/2/3/5/6`; `1` is the click-handler fallback (tested as a guard, not a contract); `4` is owned exclusively by `audit verify` mismatch.
- **`pyproject.toml` script target corrected.** `pyproject.toml:77` declares `codegenie = "codegenie.__main__:main"`, not `codegenie.cli:cli`. The `cli` group is invoked via `__main__.main(argv)` (an existing contract). The Files-to-touch row and Implementation outline step 7 now reflect this.
- **`AuditWriter.record` call shape corrected.** `audit.py:209-217` ships as `AuditWriter(output_dir).record(gather_result, *, cli_version, sherpa_commit, tool_versions, yaml_sha256) -> Path` — the writer builds the `RunRecord` internally. AC-5 step 11 was claiming a non-existent positional API.
- **`exec.run_allowlisted` async-await surface called out.** The function is `async def` (`exec.py:174`); AC-5 now states the gather body wraps its awaitable chain in `asyncio.run(...)` and tolerates non-git paths via `ToolMissingError` / non-zero `returncode` → `git_commit=None`.
- **`run_id` ownership clarified.** The coordinator already binds `run_id = secrets.token_hex(8)` via `structlog.contextvars.bind_contextvars` (coordinator.py:429). The CLI must NOT mint its own; it inherits the value. The audit filename's 4-hex `<short>` is a separate per-write collision-avoidance suffix — kept distinct on purpose.
- **ADR-0009 wording aligned.** AC-6 was gating on "non-empty output"; ADR-0009 only requires "≥1 probe in `outputs`". `CacheHit` counts. Tightened.
- **Coverage gaps closed.** New ACs added for: language_stack-actually-in-YAML (AC-12), `cli.start`/`cli.end` event correlation (AC-13), `_gitignore_mutation_stub` shim (AC-14), exit-1 fallback (AC-15), `--version` matches `codegenie.version.__version__` (AC-16), `cache.gc.stub` event name pinned (AC-17), non-git → `git_commit=None` test (AC-18), `--verbose` → DEBUG events (AC-19), startup-order orchestration test (AC-20), sanitizer-as-defense-in-depth for exit-6 (AC-21), corrupt-tool-cache → miss → re-write (AC-22), atomic-write-leaves-no-`.tmp`-sidecar (AC-23), shallow-merge collision behavior (AC-24).
- **TDD plan tightened.** The vague monkeypatch targets now name resolved import paths; the cold-start subprocess test now asserts non-empty success output with a sentinel; the symlink arrange step is now concrete; the exit-code dispatch is parametrized.
- **Edge-case rows 9 (fence alarm) and 13 (CSafeDumper fallback) removed from this story's references.** Row 9 belongs to the fence CI job test (S1-05) and row 13 belongs to the writer story (S3-03); neither is `cli.py`'s responsibility.

Full audit at `_validation/S4-02-cli-gather-audit-verify.md`.

## Context

This is the user-visible vertical slice: `codegenie gather <path>` runs end-to-end on a real directory, dispatches `LanguageDetectionProbe` through the harness internals from Step 3, and writes the first `.codegenie/context/repo-context.yaml` an engineer can open and read. Every Phase 0 exit criterion that says "the CLI runs" or "the YAML is on disk" closes here.

The CLI sits at the lazy-import boundary — `--help` and `--version` must not pull in `pyyaml` / `jsonschema` / `pydantic` / `blake3` / `structlog` (per `import-linter` config from S1-05). All heavy imports happen *inside* command function bodies. This is the structural defense for cold-start.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CLI` — public interface, lazy-import boundary, subcommand list.
  - `../phase-arch-design.md §Process view` — the full step-by-step runtime path (steps 1–18) from `codegenie gather` through to exit.
  - `../phase-arch-design.md §Control flow — Happy path` — the one-paragraph spec the CLI startup must follow exactly.
  - `../phase-arch-design.md §Scenarios — Scenario 3` — the all-probes-failed exit-2 branch.
  - `../phase-arch-design.md §Scenarios — Scenario 4` — the secret-shaped-field exit-6 branch.
  - `../phase-arch-design.md §Edge cases` — rows 7 (symlink output → exit 5), 11 (corrupt tool cache). Rows 9 (fence alarm) and 13 (CSafeDumper fallback) are NOT this story's responsibility; row 9 → S1-05's fence test, row 13 → S3-03's writer.
  - `../phase-arch-design.md §Harness engineering — Logging strategy` — `probe.*` lifecycle event names.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — `RepoSnapshot` construction goes through `exec.run_allowlisted` (`git rev-parse HEAD`); no other subprocess.
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `~/.codegenie/.tool-cache.json` is mode `0600`; `~/.codegenie/` is `0700`; re-applied on every write.
  - `../ADRs/0009-cache-hit-pass-through-coordinator-output.md` — ADR-0009 — exit code reads `GatherResult.executions` and `GatherResult.outputs`; cache hits count as success.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `SecretLikelyFieldNameError` maps to exit 6; lazy-imported.
  - `../ADRs/0013-layered-additional-properties-schema.md` — ADR-0013 — schema validation failure maps to exit 3; CLI writes `.yaml.invalid`.
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — symlink target refusal maps to exit 5.
- **Production ADRs:**
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — the cost model the CLI's tool-readiness cache exists to serve at Phase 14 scale.
- **Existing code:**
  - `src/codegenie/coordinator/coordinator.py` — `gather(...)` signature and `GatherResult` shape.
  - `src/codegenie/audit.py` — `AuditWriter.record(...)` and `audit verify` re-verification path (from S3-06).
  - `src/codegenie/output/writer.py` — `Writer.write(...)` from S3-03.
  - `src/codegenie/schema/validator.py` — `validate(...)` from S2-05.
  - `src/codegenie/exec.py` — `run_allowlisted` from S2-04.
  - `src/codegenie/logging.py` — `configure_logging(verbose)` from S2-01.

## Goal

`codegenie gather <tmp_path>` on a synthetic directory containing one `.js` file exits 0 and writes a valid `.codegenie/context/repo-context.yaml` whose `probes.language_detection.language_stack` slice is a non-empty dict, plus a `runs/<utc-iso>-<short>.json` audit record at mode `0600`. The `audit verify` subcommand is wired into the `click` group and dispatches to `audit.verify_runs(runs_dir, cache_dir, yaml_path)` (already shipped in S3-06). End-to-end validation against the three Step 4 fixtures (`empty_repo/`, `js_only/`, `polyglot/`) and cache-hit-on-second-run live in S4-04 — out of scope here.

## Acceptance criteria

- [ ] **AC-1 (subcommand surface).** `src/codegenie/cli.py` exports a `click.Group` named `cli` with subcommands `gather`, `audit verify` (group `audit` with subcommand `verify`, already wired in S3-06 — preserve the existing `--runs-dir` / `--cache-dir` / `--yaml-path` flag surface; do NOT change S3-06's exit-code contract), and `cache gc` (stub that exits 0 and logs *exactly one* structlog event named `cache.gc.stub`). `pyproject.toml [project.scripts] codegenie = "codegenie.__main__:main"` is unchanged; `__main__.main(argv)` invokes the `cli` group (preserves the `main(argv) -> int` contract pinned by S1-01).
- [ ] **AC-2 (global flags).** Global flags accepted at the group level: `--verbose`, `--version` (via `click.version_option(__version__, prog_name="codegenie")` reading `codegenie.version.__version__`), `--refresh-tools`, `--no-gitignore`, `--auto-gitignore`. The last three are propagated to `gather` via `ctx.obj`. A test asserts: (a) `--version` stdout contains the exact `codegenie.version.__version__` string and exits 0, (b) each flag parses without error and reaches the gather body (assertable by side-effects on a mocked downstream — `--refresh-tools` calls the readiness helper with `refresh=True`, `--no-gitignore` calls the gitignore shim with `skip=True`, `--auto-gitignore` with `auto=True`).
- [ ] **AC-3 (cold-start invariant).** `codegenie --help` and `codegenie --version` complete with exit code 0 AND without importing `pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`, or `yaml.CSafeDumper`. The structural defense is `import-linter` (config from S1-05). The runtime test (`tests/unit/test_cli_cold_start_imports.py`) spawns a child via `[sys.executable, "-c", ...]` with `cwd=PROJECT_ROOT`, runs both `--help` and `--version`, prints `json.dumps({"leaked": sorted(...), "exit_code": result.exit_code, "sentinel": "OK"})`, and asserts `leaked == []` AND `exit_code == 0` AND `"OK"` is present (so a child-process crash before the leak check is NOT a false-pass).
- [ ] **AC-4 (exit-code namespace, `gather`).** `gather`'s documented exit codes (printed by `codegenie gather --help`) are: `0` success; `2` all probes errored or were `Skipped` (per ADR-0009); `3` schema validation failed (writes `<output>/repo-context.yaml.invalid`, does NOT write `repo-context.yaml`, per phase-arch §Control flow); `5` symlink output refused (`SymlinkRefusedError`, per ADR-0008); `6` secret-shaped field rejected by `_ProbeOutputValidator` in the coordinator (`SecretLikelyFieldNameError`, per ADR-0010; the `OutputSanitizer` repeat-pass is defense-in-depth and is exercised separately in AC-21). Exit `1` is the click-default unhandled-exception path — see AC-15 (tested but not part of the documented "success route" matrix). Exit `4` is owned by `audit verify` mismatch (S3-06) and `gather` MUST never emit it. A `--help`-text test asserts the documented codes are listed verbatim and that `1` and `4` are NOT in the gather table.
- [ ] **AC-5 (gather startup order, awaitable surface).** `codegenie gather <path>` body wraps its awaitable chain in `asyncio.run(...)` and executes in this order: (1) `configure_logging(verbose=...)`, (2) tool-readiness check populating `~/.codegenie/.tool-cache.json` at mode `0600` (Phase 0 checks `git` only; `--refresh-tools` forces re-detect), (3) `.gitignore` mutation shim (`_gitignore_mutation_stub` per AC-14 — S4-03 lands the real body), (4) `load_config(repo_root, cli_overrides)`, (5) `await exec.run_allowlisted(["git","rev-parse","HEAD"], cwd=path, timeout_s=10)` then construct `RepoSnapshot` — on `ToolMissingError`, non-zero `returncode`, or `CalledProcessError` set `git_commit=None` (per AC-18), (6) `default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))`, (7) `await coordinator.gather(snapshot, task, probes, config, cache, sanitizer)`, (8) shallow-merge each output's `schema_slice` into the envelope under `probes.<name>` — collision behavior per AC-24, (9) `schema.validator.validate(envelope)` — on `SchemaValidationError` write `.yaml.invalid` and exit 3 (no `.yaml`), (10) `Writer.write(envelope, raw_artifacts, output_dir)`, (11) `AuditWriter(output_dir).record(gather_result, cli_version=__version__, sherpa_commit=snapshot.git_commit, tool_versions=tool_versions, yaml_sha256=identity_hash_bytes(yaml_bytes))` — the `RunRecord` is built *inside* `record()`; the CLI does NOT construct one. The orchestration is asserted by AC-20.
- [ ] **AC-6 (exit-code policy, per ADR-0009).** Exit 0 if `len(gather_result.outputs) >= 1`; exit 2 if `outputs` is empty (every probe was `Skipped` or returned an errored `Ran`). `CacheHit` counts as success — do NOT gate on "fresh execution" or "non-empty schema_slice". Parametrized test covers: (a) one `Ran` → 0, (b) one `CacheHit` → 0, (c) one errored `Ran` (empty outputs) → 2, (d) one `Skipped` → 2, (e) mix of one `Ran` + one errored `Ran` → 0.
- [ ] **AC-7 (tool-readiness cache modes & atomic write).** The tool-readiness cache file `~/.codegenie/.tool-cache.json` is written with mode `0600`; the containing `~/.codegenie/` directory is `0700` (per ADR-0011). Modes are asserted post-write via `os.stat` AND modes on artifacts written by `Writer` / `CacheStore` / `AuditWriter` remain unbroken (asserted by re-running their existing unit tests as part of this story's green gate, not duplicated here). First-run path: when `~/.codegenie/` does NOT exist, the helper creates it with mode `0700` (asserted by a fresh `tmp_home` fixture). See also AC-22 (corruption) and AC-23 (atomic write residue).
- [ ] **AC-8 (audit verify wiring).** `codegenie audit verify --runs-dir <r> --cache-dir <c> --yaml-path <y>` resolves through the `cli` group (the subcommand is callable via `CliRunner().invoke(cli, ["audit", "verify", ...])`). Internally it dispatches to `audit.verify_runs(runs_dir, cache_dir, yaml_path)` from S3-06 unchanged; exit-code mapping is preserved: `0` ↔ `mismatches == 0`, `4` ↔ `mismatches > 0`. A unit test feeds a hand-built fixture run-record dir (NOT one produced by this story's `gather`) and asserts both mappings. The "gather → audit verify on a real smoke run" end-to-end test lives in S4-04.
- [ ] **AC-9 (exit-code test matrix).** `tests/unit/test_cli_exit_codes.py` parametrizes `(exception_cls, expected_code)` over the documented mapping `{AllProbesFailedError: 2, SchemaValidationError: 3, SymlinkRefusedError: 5, SecretLikelyFieldNameError: 6}` with a happy-path test for 0 alongside. Each parametrized case patches the *resolved* import path inside `codegenie.cli` (e.g., `monkeypatch.setattr("codegenie.cli._dispatch_for_test", ...)` — or whichever seam the implementer factors), not the upstream module — lazy imports mean upstream patches are no-ops. The dispatch table itself (`dict[type[CodegenieError], int]`) is module-scope and a unit test snapshots its contents to lock the mapping.
- [ ] **AC-10 (test-pass gate).** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/` (excluding `cli.py` per pyproject coverage exemption — its lazy-imports defeat structural typing; imported modules remain strict-clean), `lint-imports`, and `pytest tests/unit/test_cli_*` all pass.
- [ ] **AC-11 (probes-failed cleanup).** When AC-6 exits 2 (all probes failed/skipped), no `repo-context.yaml` is written (asserted) AND an audit record IS still written under `runs/` logging the probe failures (per phase-arch §Scenario 3). Test asserts: (a) `not (output_dir / "repo-context.yaml").exists()`, (b) `any((output_dir / "runs").glob("*.json"))`, (c) the run-record's `probes[*].exit_status` reflects the failures.
- [ ] **AC-12 (language_stack actually in YAML — closes Goal trace).** Happy-path test loads the written `repo-context.yaml` via `yaml.safe_load` and asserts `parsed["probes"]["language_detection"]["language_stack"]` is a non-empty dict containing at least the keys the probe's S4-01 contract guarantees. This anchors the Goal's "containing the `language_detection` probe's `language_stack` slice" promise; without it, an empty `probes: {}` envelope passes every other AC.
- [ ] **AC-13 (`cli.start` / `cli.end` events; `run_id` correlation).** The CLI emits exactly one `cli.start` and one `cli.end` event per `gather` invocation. Both share the same `run_id` (the coordinator's existing `secrets.token_hex(8)` binding via `structlog.contextvars` — `coordinator/coordinator.py:429-430`; the CLI does NOT mint a new id). The `cli.end` event carries an `outcome` field (`"ok" | "crash" | "probes_failed" | "schema_invalid" | "symlink_refused" | "secret_field" | …`). Test uses `structlog.testing.capture_logs()` to capture and assert event names, presence of `run_id`, and matching values; also asserts the audit filename's 4-hex `<short>` is NOT required to equal `run_id` (kept distinct on purpose — the `<short>` is the per-write collision-avoidance suffix from `audit.py:239`).
- [ ] **AC-14 (`_gitignore_mutation_stub` shim).** `src/codegenie/cli.py` ships `_gitignore_mutation_stub(repo_root: Path, *, auto: bool, skip: bool) -> None` that logs `gitignore.mutation.deferred_to_s4_03` and returns. Unit test asserts: (a) the function exists with that exact signature (via `inspect.signature`), (b) it makes no filesystem writes, (c) `--no-gitignore` short-circuits before the stub is invoked at all (no log emitted). S4-03 replaces the body without changing the signature.
- [ ] **AC-15 (exit 1 — unhandled exception fallback).** When a non-`CodegenieError` exception escapes the gather body, the process exits with code 1 and emits a `cli.end` event with `outcome="crash"` and a `cli.unhandled` event with the exception class name. Test injects a raw `RuntimeError("synthetic")` inside the body (via monkeypatch on a private seam) and asserts both the exit code and the events.
- [ ] **AC-16 (`--version` matches `codegenie.version.__version__`).** Test asserts `CliRunner().invoke(cli, ["--version"]).output` contains the exact string returned by `codegenie.version.__version__` (no hardcoded value). Mutation defense: a version-drift would surface here.
- [ ] **AC-17 (`cache gc` stub structural event).** Test invokes `codegenie cache gc` and asserts: (a) exit code 0, (b) exactly one structlog event captured with `event == "cache.gc.stub"` (NOT `cache.gc.noop` or any other name). The exact event name is part of the Phase-1+ migration contract.
- [ ] **AC-18 (non-git path → `git_commit=None`).** Test runs `gather` against a `tmp_path` that is NOT a git repo (no `.git/`) and asserts: (a) exit code 0, (b) the resulting envelope's `repo.git_commit` is `None` (per JSON Schema's `["string", "null"]` union), (c) NO exception escapes to the click handler. Distinguishes between `ToolMissingError` (no `git` on `$PATH`) and `git rev-parse` non-zero (path is not a git working tree) — both map to `git_commit=None`.
- [ ] **AC-19 (`--verbose` raises log level to DEBUG).** Test invokes `gather --verbose` against a happy-path fixture, captures structlog output, and asserts at least one `level == "debug"` event is emitted (e.g., the `Provenance` log from `load_config`, per phase-arch §Harness engineering — Configuration). Without `--verbose`, no `debug`-level event is emitted.
- [ ] **AC-20 (startup-order orchestration).** Test injects a `Mock` for each of the 11 collaborators referenced in AC-5 (configure_logging, _check_tools, _gitignore_mutation_stub, load_config, run_allowlisted, default_registry.for_task, coordinator.gather, the shallow-merge function, validator.validate, Writer.write, AuditWriter.record), records `call_order` via a side-effect appended to a list, runs `gather`, and asserts the list equals the expected step sequence (1..11). Mutation defense: reordering steps would break this.
- [ ] **AC-21 (sanitizer-as-defense-in-depth for exit 6).** Per Scenario 4, even if `_ProbeOutputValidator` is bypassed, `OutputSanitizer.scrub` repeats the secret-field pass. Test: monkeypatch the validator to be a no-op pass-through; emit a probe output with `schema_slice = {"github_token": "ghp_x"}`; assert `SecretLikelyFieldNameError` is still raised by the sanitizer and exits 6. (The validator-path is covered by AC-9's parametrized case.)
- [ ] **AC-22 (corrupt tool-readiness cache → miss → re-write — edge case row 11).** Test pre-writes `~/.codegenie/.tool-cache.json` as truncated/invalid JSON (`b'{not-jso'`); runs `gather`; asserts: (a) the file is overwritten with valid JSON (`{"git": "<version>"}`), (b) mode is `0600`, (c) a `tool_cache.invalid` warning event was emitted.
- [ ] **AC-23 (atomic write leaves no `.tmp` sidecar).** After any tool-readiness cache write, no `.tool-cache.json.tmp` (or similar) file exists in `~/.codegenie/`. Asserts the atomic-write pattern (`<tmp> → fsync → os.replace`) holds.
- [ ] **AC-24 (probe-name collision on shallow merge).** The shallow-merge step (AC-5 step 8) defends against two probes registering the same `name` (registry bug, hot-reload). Behavior: raise `ProbeNameCollisionError` mapped to exit 1 (it's a programming error, not a documented user-facing code). Test exercises two stub probes sharing a name and asserts the exit code and event name `cli.unhandled` carrying `error_repr` including `"ProbeNameCollisionError"`. If the registry already enforces uniqueness at registration time (S2-05), this AC degenerates to a defense-in-depth assertion — document the redundancy in the test docstring.

## Implementation outline

1. Scaffold `src/codegenie/cli.py` with a `click.Group` named `cli`, a `gather` subcommand, the existing `audit` subgroup (`audit verify` already present from S3-06 — keep it), and a `cache` subgroup with a `gc` stub.
2. Add the global options at the group level via `@click.option`. Pass them down to subcommands via `ctx.obj`. Use `click.version_option(__version__, prog_name="codegenie")` at the group level for `--version`.
3. Inside each command body, do all heavy imports *first*, at the *top* of the body (not lazily inside try/except — `import-linter` + AC-3 cold-start test snapshot `sys.modules`, and any partial heavy-import would surface there): `pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`, `yaml`, plus the `codegenie.*` modules that themselves import these.
4. Implement the tool-readiness check as a helper (`_check_tools(refresh: bool) -> dict[str, str]`) that reads `~/.codegenie/.tool-cache.json`, on miss / corrupt-JSON / `--refresh-tools` runs `await exec.run_allowlisted(["git","--version"], cwd=Path.cwd(), timeout_s=10)`, writes the cache atomically (`<tmp> → fsync → os.replace`) with mode `0600`, and returns `{"git": "<version-string>"}`. First run creates `~/.codegenie/` at mode `0700`.
5. Implement the gather startup path per `../phase-arch-design.md §Control flow — Happy path`. Because `exec.run_allowlisted` and `coordinator.gather` are `async def`, the gather body wraps its awaitable chain in `asyncio.run(...)`. Wrap the whole body in `try/except CodegenieError` and translate each exception to its documented exit code via a module-scope `_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int]` (the single source of truth — AC-9 snapshots it). Non-`CodegenieError` exceptions hit the click default handler → exit 1 (AC-15).
6. `audit verify` is already wired by S3-06 — do NOT reshape its flag surface (`--runs-dir / --cache-dir / --yaml-path`). Confirm it's reachable through the `cli` group (`CliRunner().invoke(cli, ["audit", "verify", ...])`) and that its exit-code mapping (`0` clean, `4` mismatch) is preserved.
7. Wire the entry point through `__main__.main(argv)`: `pyproject.toml [project.scripts]` declares `codegenie = "codegenie.__main__:main"` (already shipped by S1-01; do NOT change). Reshape `__main__.py` so `main(argv)` imports the `cli` group from `codegenie.cli` and dispatches through it: `return cli.main(argv or sys.argv[1:], standalone_mode=False, prog_name="codegenie") or 0` (or equivalent that preserves the existing `main(argv) -> int` contract).
8. `RunRecord` is built INSIDE `AuditWriter.record()` — the CLI does NOT construct one. The CLI call shape is `AuditWriter(output_dir).record(gather_result, cli_version=__version__, sherpa_commit=snapshot.git_commit, tool_versions=tool_versions, yaml_sha256=identity_hash_bytes(yaml_bytes))`. The `yaml_bytes` are captured between steps 10 and 11 by reading the just-written file (or by capturing the bytes object before `os.replace`).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_cli_exit_codes.py`, `tests/unit/test_cli_tool_readiness.py`, `tests/unit/test_cli_cold_start_imports.py`, `tests/unit/test_cli_orchestration.py`, `tests/unit/test_cli_flags.py`, `tests/unit/test_cli_audit_subcommand.py`.

The list below is the *intent* under test (mapped 1:1 to ACs); the implementer factors the exact monkeypatch seams.

```python
# tests/unit/test_cli_exit_codes.py — AC-4, AC-9, AC-11, AC-21
import pytest
from click.testing import CliRunner

# AC-9 — parametrize the dispatch table (mutation defense)
from codegenie.errors import (
    AllProbesFailedError, SchemaValidationError,
    SymlinkRefusedError, SecretLikelyFieldNameError,
)
@pytest.mark.parametrize("exc_cls,expected_code", [
    (AllProbesFailedError, 2),
    (SchemaValidationError, 3),
    (SymlinkRefusedError, 5),
    (SecretLikelyFieldNameError, 6),
])
def test_documented_error_maps_to_documented_exit_code(
    tmp_path, monkeypatch, exc_cls, expected_code,
):
    """Each CodegenieError subclass maps to its documented gather exit code.
    Intent (Rule 9): the dispatch table — `_EXIT_CODE_DISPATCH` — is the
    contract. A swap of two codes (e.g., 5↔6) MUST fail this test."""
    from codegenie import cli as cli_mod
    # Patch the resolved seam INSIDE cli (lazy imports → upstream patch is no-op)
    monkeypatch.setattr(cli_mod, "_run_gather_pipeline",
                        lambda *a, **kw: (_ for _ in ()).throw(exc_cls("synthetic")))
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(tmp_path)])
    assert result.exit_code == expected_code, result.output

def test_dispatch_table_snapshot():
    """Locks the {ExceptionClass: exit_code} mapping. Adding a code REQUIRES
    a story amendment + test update — prevents silent drift."""
    from codegenie.cli import _EXIT_CODE_DISPATCH
    from codegenie.errors import (AllProbesFailedError, SchemaValidationError,
                                  SymlinkRefusedError, SecretLikelyFieldNameError)
    assert _EXIT_CODE_DISPATCH == {
        AllProbesFailedError: 2, SchemaValidationError: 3,
        SymlinkRefusedError: 5, SecretLikelyFieldNameError: 6,
    }

# AC-4 — help-text lists documented codes; excludes 1 and 4
def test_gather_help_lists_documented_exit_codes_only():
    from codegenie.cli import cli
    out = CliRunner().invoke(cli, ["gather", "--help"]).output
    for code in ("0", "2", "3", "5", "6"):
        assert f"exit {code}" in out.lower() or f"`{code}`" in out
    # exit 1 is click's fallback (not contract); exit 4 belongs to `audit verify`
    assert "exit 4" not in out.lower()  # owned by audit verify

# AC-3 happy path with REAL probe via S4-01 — assert YAML contents (AC-12)
def test_gather_happy_path_writes_language_stack(tmp_path):
    (tmp_path / "a.js").write_text("// hi")
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 0, result.output
    yaml_path = tmp_path / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.exists()
    import yaml
    envelope = yaml.safe_load(yaml_path.read_text())
    stack = envelope["probes"]["language_detection"]["language_stack"]
    assert isinstance(stack, dict) and stack  # AC-12 — non-empty
    # AC-11 cousin — audit record exists
    runs = list((tmp_path / ".codegenie" / "context" / "runs").glob("*.json"))
    assert len(runs) == 1

# AC-11 — exit 2 leaves no .yaml; audit record still written
def test_gather_exits_2_leaves_no_yaml_but_writes_audit(tmp_path, monkeypatch):
    from codegenie import cli as cli_mod
    monkeypatch.setattr(cli_mod, "_run_gather_pipeline",
                        lambda *a, **kw: (_ for _ in ()).throw(AllProbesFailedError("synthetic")))
    # ... arrange so the audit writer is still invoked (or assert via a Mock)
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(tmp_path)])
    assert result.exit_code == 2
    assert not (tmp_path / ".codegenie" / "context" / "repo-context.yaml").exists()
    assert any((tmp_path / ".codegenie" / "context" / "runs").glob("*.json"))

# AC-4 — exit 3 writes .yaml.invalid AND does NOT write .yaml
def test_exit_3_writes_invalid_only(tmp_path, monkeypatch):
    from codegenie import cli as cli_mod
    monkeypatch.setattr(cli_mod, "_validate_envelope",
                        lambda env: (_ for _ in ()).throw(SchemaValidationError("synthetic")))
    (tmp_path / "a.js").write_text("//")
    result = CliRunner().invoke(cli_mod.cli, ["gather", str(tmp_path)])
    assert result.exit_code == 3
    ctx = tmp_path / ".codegenie" / "context"
    assert (ctx / "repo-context.yaml.invalid").exists()
    assert not (ctx / "repo-context.yaml").exists()
    import yaml
    # The invalid file must contain the rejected envelope (no empty-file shortcut)
    assert yaml.safe_load((ctx / "repo-context.yaml.invalid").read_text())

# AC-4, ADR-0008 — concrete symlink arrange
def test_exit_5_when_output_yaml_is_symlink(tmp_path):
    (tmp_path / "a.js").write_text("//")
    ctx = tmp_path / ".codegenie" / "context"
    ctx.mkdir(parents=True)
    decoy = tmp_path / "decoy.yaml"
    decoy.write_text("# attacker controlled\n")
    (ctx / "repo-context.yaml").symlink_to(decoy)
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 5
    # decoy untouched (writer refused to follow the symlink)
    assert decoy.read_text() == "# attacker controlled\n"

# AC-21 — sanitizer defense-in-depth (validator bypassed)
def test_exit_6_via_sanitizer_when_validator_bypassed(tmp_path, monkeypatch):
    from codegenie.coordinator import validator as v
    monkeypatch.setattr(v, "_ProbeOutputValidator",
                        lambda **kw: type("Pass", (), {"model_dump": lambda s: kw})())
    # Feed a probe that emits a secret-shaped field
    # Assert SecretLikelyFieldNameError is raised by OutputSanitizer.scrub
    ...
    assert result.exit_code == 6
```

```python
# tests/unit/test_cli_tool_readiness.py — AC-7, AC-22, AC-23
import json, os, stat
from click.testing import CliRunner

@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    return tmp_path

def test_first_run_creates_dir_and_cache_at_correct_modes(tmp_home):
    """AC-7 — ~/.codegenie/ created at 0700; .tool-cache.json at 0600."""
    repo = tmp_home / "repo"; repo.mkdir(); (repo / "a.js").write_text("//")
    from codegenie.cli import cli
    CliRunner().invoke(cli, ["gather", str(repo)])
    cache = tmp_home / ".codegenie" / ".tool-cache.json"
    assert cache.exists()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache.parent.stat().st_mode) == 0o700
    payload = json.loads(cache.read_text())
    assert "git" in payload  # AC-7 — content sanity, not just mode

def test_corrupt_tool_cache_becomes_miss_then_rewritten(tmp_home, caplog):
    """AC-22 / edge case row 11."""
    (tmp_home / ".codegenie").mkdir(mode=0o700)
    cache = tmp_home / ".codegenie" / ".tool-cache.json"
    cache.write_bytes(b"{not-jso")  # truncated
    cache.chmod(0o600)
    repo = tmp_home / "repo"; repo.mkdir(); (repo / "a.js").write_text("//")
    from codegenie.cli import cli
    CliRunner().invoke(cli, ["gather", str(repo)])
    # File is valid JSON now, still 0600
    payload = json.loads(cache.read_text())
    assert "git" in payload
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    # warning event emitted
    assert any("tool_cache.invalid" in r.message for r in caplog.records)

def test_atomic_write_leaves_no_tmp_sidecar(tmp_home):
    """AC-23 — no `.tool-cache.json.tmp` or sibling tmp survives."""
    repo = tmp_home / "repo"; repo.mkdir(); (repo / "a.js").write_text("//")
    from codegenie.cli import cli
    CliRunner().invoke(cli, ["gather", str(repo)])
    siblings = list((tmp_home / ".codegenie").iterdir())
    assert all(not s.name.endswith(".tmp") for s in siblings), siblings
```

```python
# tests/unit/test_cli_cold_start_imports.py — AC-3
import json, subprocess, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def test_help_and_version_keep_heavy_modules_out_of_sys_modules():
    """AC-3 — exit 0 AND no heavy modules imported. The sentinel guards
    against false-pass on a crashed child producing empty stdout."""
    probe = (
        "import sys, json;"
        " from codegenie.cli import cli;"
        " from click.testing import CliRunner;"
        " r1 = CliRunner().invoke(cli, ['--help']);"
        " r2 = CliRunner().invoke(cli, ['--version']);"
        " heavy = {'yaml','jsonschema','pydantic','blake3','structlog'};"
        " leaked = sorted(k for k in sys.modules if k.split('.')[0] in heavy);"
        " print(json.dumps({'leaked':leaked,"
        " 'help_exit':r1.exit_code,'version_exit':r2.exit_code,"
        " 'sentinel':'OK'}))"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", probe], text=True, cwd=str(PROJECT_ROOT),
    )
    data = json.loads(out.strip().splitlines()[-1])
    assert data["sentinel"] == "OK"         # guard: child didn't crash early
    assert data["help_exit"] == 0
    assert data["version_exit"] == 0
    assert data["leaked"] == []
```

```python
# tests/unit/test_cli_orchestration.py — AC-20, AC-13, AC-15, AC-18
def test_startup_order_matches_ac5_spec(tmp_path, monkeypatch):
    """AC-20 — record call order of the 11 collaborators in AC-5."""
    calls = []
    # ... monkeypatch each seam in codegenie.cli so its side-effect is
    # calls.append("configure_logging") / "check_tools" / "gitignore_stub"
    # / "load_config" / "run_allowlisted" / "registry_for_task"
    # / "coordinator_gather" / "shallow_merge" / "validate" / "writer_write"
    # / "audit_record"
    (tmp_path / "a.js").write_text("//")
    from codegenie.cli import cli
    CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert calls == [
        "configure_logging", "check_tools", "gitignore_stub", "load_config",
        "run_allowlisted", "registry_for_task", "coordinator_gather",
        "shallow_merge", "validate", "writer_write", "audit_record",
    ]

def test_cli_start_and_end_events_share_run_id(tmp_path):
    """AC-13 — coordinator-minted run_id (not CLI-minted) appears on both events."""
    import structlog
    (tmp_path / "a.js").write_text("//")
    with structlog.testing.capture_logs() as logs:
        from codegenie.cli import cli
        CliRunner().invoke(cli, ["gather", str(tmp_path)])
    starts = [e for e in logs if e.get("event") == "cli.start"]
    ends = [e for e in logs if e.get("event") == "cli.end"]
    assert len(starts) == 1 and len(ends) == 1
    assert starts[0]["run_id"] == ends[0]["run_id"]
    assert len(starts[0]["run_id"]) == 16  # secrets.token_hex(8)
    assert ends[0]["outcome"] == "ok"

def test_unhandled_exception_exits_1_with_crash_outcome(tmp_path, monkeypatch):
    """AC-15 — non-CodegenieError → click fallback → exit 1."""
    from codegenie import cli as cli_mod
    monkeypatch.setattr(cli_mod, "_run_gather_pipeline",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("synthetic")))
    import structlog
    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli_mod.cli, ["gather", str(tmp_path)])
    assert result.exit_code == 1
    assert any(e.get("event") == "cli.unhandled" for e in logs)
    end = [e for e in logs if e.get("event") == "cli.end"][0]
    assert end["outcome"] == "crash"

def test_non_git_path_yields_null_git_commit(tmp_path):
    """AC-18 — no .git/ → git_commit=None, no exception."""
    (tmp_path / "a.js").write_text("//")  # not a git repo
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 0
    import yaml
    env = yaml.safe_load((tmp_path / ".codegenie" / "context" / "repo-context.yaml").read_text())
    assert env["repo"]["git_commit"] is None
```

```python
# tests/unit/test_cli_flags.py — AC-2, AC-14, AC-16, AC-17, AC-19
def test_version_matches_codegenie_version(tmp_path):
    """AC-16 — version string is sourced from codegenie.version, not hardcoded."""
    from codegenie.cli import cli
    from codegenie.version import __version__
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output

def test_global_flags_propagate_to_gather(tmp_path, monkeypatch):
    """AC-2 — --refresh-tools, --no-gitignore, --auto-gitignore reach the body."""
    seen = {}
    monkeypatch.setattr("codegenie.cli._check_tools", lambda refresh: seen.setdefault("refresh", refresh) or {"git":"x"})
    monkeypatch.setattr("codegenie.cli._gitignore_mutation_stub",
                        lambda root, *, auto, skip: seen.setdefault("gitignore", (auto, skip)))
    (tmp_path / "a.js").write_text("//")
    from codegenie.cli import cli
    CliRunner().invoke(cli, ["--refresh-tools", "--no-gitignore", "gather", str(tmp_path)])
    assert seen["refresh"] is True
    assert seen["gitignore"] == (False, True)  # auto=False, skip=True

def test_cache_gc_stub_emits_exact_event_name():
    """AC-17 — exact event name `cache.gc.stub` is contract."""
    import structlog
    from codegenie.cli import cli
    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli, ["cache", "gc"])
    assert result.exit_code == 0
    stub_events = [e for e in logs if e.get("event") == "cache.gc.stub"]
    assert len(stub_events) == 1

def test_gitignore_stub_signature_and_noop():
    """AC-14 — shim signature is stable across S4-02 → S4-03."""
    import inspect
    from codegenie.cli import _gitignore_mutation_stub
    sig = inspect.signature(_gitignore_mutation_stub)
    assert list(sig.parameters) == ["repo_root", "auto", "skip"]
    assert sig.parameters["auto"].kind == inspect.Parameter.KEYWORD_ONLY
    # ... call with auto=False, skip=False on a tmp_path and assert no FS writes

def test_verbose_emits_debug_events(tmp_path):
    """AC-19 — --verbose → at least one debug event."""
    import structlog
    (tmp_path / "a.js").write_text("//")
    from codegenie.cli import cli
    with structlog.testing.capture_logs() as logs:
        CliRunner().invoke(cli, ["--verbose", "gather", str(tmp_path)])
    assert any(e.get("log_level") == "debug" for e in logs)
```

```python
# tests/unit/test_cli_audit_subcommand.py — AC-8
def test_audit_verify_wired_into_cli_group(tmp_path):
    """AC-8 — subcommand resolves AND exit-code mapping preserved (0/4)."""
    runs = tmp_path / "runs"; runs.mkdir()
    cache = tmp_path / "cache"; cache.mkdir()
    yaml = tmp_path / "repo-context.yaml"; yaml.write_text("schema_version: '0.1.0'\n")
    # ... build a minimal clean run-record fixture, assert exit 0
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, [
        "audit", "verify",
        "--runs-dir", str(runs), "--cache-dir", str(cache), "--yaml-path", str(yaml),
    ])
    assert result.exit_code == 0
    # ... tamper one run-record's blob_sha256, re-run, assert exit 4
```

Run all of the above; each fails (`ModuleNotFoundError`, `AttributeError`, or wrong exit code). Commit the failing tests.

### Green — make it pass

Implement `cli.py` per the outline above. Heavy imports inside command bodies. Exit-code dispatch table. Tool-readiness helper with atomic write + chmod. Defer `.gitignore` mutation to the helper S4-03 provides (use a stub raising `NotImplementedError` if S4-03 has not landed; S4-02's tests don't exercise that path).

### Refactor — clean up

- Pull the exit-code dispatch into a small typed dict (`_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int]`) at module scope; AC-9 snapshots it.
- Add docstrings on `gather`, `audit verify`, and the tool-readiness helper. The `gather` docstring lists the documented exit codes (so `--help` reflects them automatically).
- Ensure every probe lifecycle event name used by the coordinator (S3-05) flows through to stderr in JSON-on-non-TTY / pretty-on-TTY (handled by `configure_logging`; this story just calls it).
- Add `cli.start` (at body entry) and `cli.end` (in `finally`) events. The CLI does **not** mint its own `run_id` — the coordinator already binds `secrets.token_hex(8)` via `structlog.contextvars` (coordinator.py:429-430) and the CLI emits its events *inside* that context so both share the bound id automatically. The audit filename's 4-hex `<short>` (`audit.py:239`) is a separate per-write collision-avoidance suffix and is intentionally distinct from `run_id`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Expand the existing stub (S1-05 + S3-06 already shipped `cli` group + `audit verify`) — add `gather`, `cache gc`, global flags, dispatch table, tool-readiness helper, `_gitignore_mutation_stub` |
| `src/codegenie/__main__.py` | Reshape `main(argv)` to dispatch through `codegenie.cli.cli` while preserving the `main(argv) -> int` contract pinned by S1-01 |
| `tests/unit/test_cli_exit_codes.py` | New — anchors the `_EXIT_CODE_DISPATCH` table (parametrized) + AC-11 (no-yaml + audit-still-written on exit 2) + AC-21 (sanitizer defense-in-depth) |
| `tests/unit/test_cli_tool_readiness.py` | New — AC-7 (modes), AC-22 (corruption), AC-23 (atomic write) |
| `tests/unit/test_cli_cold_start_imports.py` | New — AC-3 (heavy-module exclusion with sentinel guard) |
| `tests/unit/test_cli_orchestration.py` | New — AC-13 (run_id), AC-15 (exit 1), AC-18 (non-git), AC-20 (startup order) |
| `tests/unit/test_cli_flags.py` | New — AC-2 (flag propagation), AC-14 (gitignore stub), AC-16 (version), AC-17 (cache gc event), AC-19 (verbose) |
| `tests/unit/test_cli_audit_subcommand.py` | New — AC-8 (subcommand wired through `cli` group; exit-code 0/4 mapping preserved) |
| `pyproject.toml` | NO CHANGE. `[project.scripts] codegenie = "codegenie.__main__:main"` was set by S1-01 and is the contract; do NOT redirect to `codegenie.cli:cli` |

## Out of scope

- **`.gitignore` mutation prompt routine + TTY/non-TTY branches** — handled by story S4-03. This story calls into the routine via a thin shim.
- **End-to-end smoke tests against real fixtures + cache-hit-on-second-run** — handled by story S4-04.
- **Adversarial test suite** (`tests/adv/test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) — handled by story S4-05.
- **`cache gc` real implementation** — Phase 1+; this story ships only the stub subcommand.
- **`audit verify` re-verification logic** — landed in S3-06; this story only wires the subcommand into `click`.
- **External-tool readiness for binaries beyond `git`** — Phase 1 lights up `tree-sitter` etc.; Phase 0 only checks `git`.

## Notes for the implementer

- `import-linter` (from S1-05) blocks `yaml`, `jsonschema`, `pydantic`, `blake3`, `structlog` from being imported at module-import time in `cli.py`. AC-3's runtime test is the structural defense; if `import-linter` fails the lint job, the issue is at module top of `cli.py` (not inside command bodies).
- Heavy imports inside command bodies must be at the *top* of the body, not lazily inside try/except — AC-3's cold-start test checks `sys.modules` after `--help`/`--version` and any partial heavy-import would surface.
- The `.gitignore` mutation routine in S4-03 must be callable without S4-03 having landed. Ship `_gitignore_mutation_stub(repo_root: Path, *, auto: bool, skip: bool) -> None` (AC-14) — S4-03 replaces the body without changing the signature.
- `RepoSnapshot.git_commit` must be `None` (not raise) when the input path is not a git repo. `exec.run_allowlisted` is `async def` so the call site is `await`-ed; tolerate `ToolMissingError` (no `git` on `$PATH`) AND non-zero `returncode` (not a git working tree, no HEAD yet) — both → `git_commit=None` (AC-18).
- The CLI body wraps its awaitable chain in `asyncio.run(...)` because `exec.run_allowlisted` and `coordinator.gather` are both async.
- The exit-code dispatch table (`_EXIT_CODE_DISPATCH`) is the single source of truth for the documented codes — AC-9 snapshots it; the `gather` docstring lists the codes so `--help` text inherits them. Adding a code requires a story amendment + test update.
- The tool-readiness helper writes to `~/.codegenie/.tool-cache.json` atomically (`<tmp>` → `fsync` → `os.replace`) per ADR-0011, then `os.chmod 0600` on the file and `0700` on the directory. `os.chmod` is idempotent. AC-23 enforces no `.tmp` sidecar survives.
- The coordinator already binds `run_id = secrets.token_hex(8)` (16 hex chars) via `structlog.contextvars` at `coordinator/coordinator.py:429-430`. The CLI inherits it — do **not** mint a new id. The audit filename's 4-hex `<short>` (`audit.py:239`) is a separate per-write collision-avoidance suffix; the two are intentionally distinct.
- Per ADR-0009 (verified against `coordinator/coordinator.py`'s `GatherResult` docstring): `outputs` already only contains entries for `Ran` (including errored `Ran`) and `CacheHit`; `Skipped` probes contribute no `outputs` entry. So `len(outputs) >= 1` is the structural success gate. Do NOT additionally gate on "non-empty schema_slice."
- `AuditWriter.record` is a method on `AuditWriter(output_dir)`; its signature is `record(gather_result, *, cli_version, sherpa_commit, tool_versions, yaml_sha256) -> Path`. The `RunRecord` is built inside the method — the CLI does not construct one. `yaml_sha256` is `hashing.identity_hash_bytes(yaml_bytes)` (S3-06 pinned `identity_hash_bytes`, NOT `identity_hash`).
- Exit code `4` is owned exclusively by `audit verify` mismatch (S3-06). `gather` must never emit it. Exit code `1` is the click default unhandled-exception fallback (AC-15) — tested but NOT in the documented `gather` exit-code matrix.
- The `audit verify` subcommand is already wired by S3-06 (`src/codegenie/cli.py:30-74`) with `--runs-dir / --cache-dir / --yaml-path` flag surface. Do NOT change the flag shape or exit-code mapping; AC-8 only requires it remains reachable through the `cli` group and that its `0`/`4` contract is preserved.
