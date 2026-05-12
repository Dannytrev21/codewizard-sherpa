# Story S4-02 — CLI `gather` + `audit verify` + tool-readiness check

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready
**Effort:** M
**Depends on:** S3-06, S4-01
**ADRs honored:** ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0012, ADR-0013

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
  - `../phase-arch-design.md §Edge cases` — rows 7 (symlink output → exit 5), 9 (fence alarm), 11 (corrupt tool cache), 13 (CSafeDumper fallback).
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

`codegenie gather <path>` on the three Step 4 fixtures (`tests/fixtures/empty_repo/`, `js_only/`, `polyglot/`) exits 0 and writes a valid `.codegenie/context/repo-context.yaml` containing the `language_detection` probe's `language_stack` slice, plus a `runs/<utc-iso>-<short>.json` audit record that `codegenie audit verify` re-reads and reports zero mismatches on.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` exports a `click.Group` named `cli` with subcommands `gather`, `audit verify` (group `audit` with subcommand `verify`), and `cache gc` (stub that exits 0 and logs `cache.gc.stub`).
- [ ] Global flags accepted at the group level: `--verbose`, `--version`, `--refresh-tools`, `--no-gitignore`, `--auto-gitignore`. The last three are read by the `gather` subcommand; `--version` exits 0 immediately after printing the version from `codegenie.version`.
- [ ] `codegenie --help` and `codegenie --version` complete without importing `pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`, or `yaml.CSafeDumper` (verified by a test that snapshots `sys.modules` keys before and after `--help`).
- [ ] Exit codes documented in `--help` and tested: `0` success, `1` unhandled exception, `2` all probes failed, `3` schema validation failed (writes `.yaml.invalid` next to where `.yaml` would have gone), `5` symlink output refused (`SymlinkRefusedError`), `6` secret-shaped field rejected at the validator/sanitizer (`SecretLikelyFieldNameError`).
- [ ] `codegenie gather <path>` startup path runs in this order: (1) `configure_logging(verbose=...)`, (2) tool-readiness check populating `~/.codegenie/.tool-cache.json` mode `0600` (Phase 0 checks `git` only; `--refresh-tools` forces re-detect), (3) maybe-prompt-or-skip `.gitignore` mutation (story S4-03 implements; this story just calls into the routine), (4) `load_config(repo_root, cli_overrides)`, (5) construct `RepoSnapshot` via `exec.run_allowlisted(["git","rev-parse","HEAD"], cwd=path, timeout_s=10)` (tolerate non-git repos: `git_commit=None`), (6) `default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))`, (7) `await coordinator.gather(snapshot, task, probes, config, cache, sanitizer)`, (8) shallow-merge each output's `schema_slice` into the envelope under `probes.<name>`, (9) `schema.validator.validate(envelope)` — on failure write `.yaml.invalid` and exit 3, (10) `Writer.write(envelope, raw_artifacts, output_dir)`, (11) `AuditWriter.record(run_record, output_dir)`.
- [ ] Exit code policy reads `GatherResult.executions`: exit 0 if `outputs` contains at least one probe entry from a `Ran` or `CacheHit` execution that produced a non-empty output; exit 2 if every probe was `Skipped` or returned only `errors`.
- [ ] The tool-readiness cache file `~/.codegenie/.tool-cache.json` is written with mode `0600`; the containing `~/.codegenie/` directory is `0700`. A test asserts both modes post-write via `os.stat`. A corrupted cache file (truncated JSON) is treated as a miss, re-detected, and re-written atomically (edge case #11).
- [ ] `codegenie audit verify` walks `.codegenie/context/runs/`, re-reads every claimed `blob_sha256` and recomputes; reports zero mismatches on a clean smoke-run state; reports a mismatch (non-zero exit) when a blob file is tampered with. Already implemented in S3-06; this story wires the subcommand into the `click` group.
- [ ] A red test (`tests/unit/test_cli_exit_codes.py`) covers each of the documented exit codes (0/2/3/5/6) with mocks; the test is green after implementation.
- [ ] `ruff check`, `ruff format --check`, and `pytest tests/unit/test_cli_exit_codes.py tests/unit/test_cli_tool_readiness.py` all pass. (`mypy --strict` is relaxed on `cli.py` per pyproject coverage exemption — the lazy-imports defeat structural typing — but the imported modules used inside the command body are themselves `mypy --strict` clean.)

## Implementation outline

1. Scaffold `src/codegenie/cli.py` with a `click.Group` named `cli`, a `gather` subcommand, an `audit` subgroup with a `verify` subcommand, and a `cache` subgroup with a `gc` stub.
2. Add the global options at the group level via `@click.option`. Pass them down to subcommands via `ctx.obj`.
3. Inside each command body, do all heavy imports *first* (`pyyaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`, `yaml`, the `codegenie.*` modules that themselves import these).
4. Implement the tool-readiness check as a helper (`_check_tools(refresh: bool) -> dict[str, str]`) that reads `~/.codegenie/.tool-cache.json`, on miss runs `await exec.run_allowlisted(["git","--version"], ...)`, writes the cache with `0600` mode, and returns `{"git": "<version-string>"}`.
5. Implement the gather startup path per `../phase-arch-design.md §Control flow — Happy path`. Wrap the whole body in a `try/except CodegenieError` and translate each exception to its documented exit code via a small dispatch dict.
6. Implement `audit verify` by calling the `AuditWriter.verify(output_dir)` method from S3-06 and exiting 0 / non-zero based on the report's mismatch count.
7. Wire the entry point: `pyproject.toml` `[project.scripts]` already declares `codegenie = "codegenie.cli:cli"` (set in S1-01); confirm it resolves.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_cli_exit_codes.py`, `tests/unit/test_cli_tool_readiness.py`, `tests/unit/test_cli_cold_start_imports.py`

This story has three distinct anchor behaviors. Write one red test for each.

```python
# tests/unit/test_cli_exit_codes.py
from click.testing import CliRunner

def test_gather_exits_0_on_happy_path(tmp_path):
    # arrange: a fixture with one .js file, mock the coordinator to return a successful GatherResult
    (tmp_path / "a.js").write_text("//")
    # act
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    # assert
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".codegenie" / "context" / "repo-context.yaml").exists()


def test_gather_exits_2_when_all_probes_fail(tmp_path, monkeypatch):
    # arrange: monkeypatch the registry to return a probe whose run() raises
    # act + assert
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 2


def test_gather_exits_3_on_schema_validation_failure(tmp_path, monkeypatch):
    # arrange: monkeypatch the validator to raise SchemaValidationError
    # act + assert
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 3
    assert (tmp_path / ".codegenie" / "context" / "repo-context.yaml.invalid").exists()


def test_gather_exits_5_on_symlink_output(tmp_path, monkeypatch):
    # arrange: pre-create .codegenie/context/repo-context.yaml as a symlink target
    # act + assert
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 5


def test_gather_exits_6_on_secret_field(tmp_path, monkeypatch):
    # arrange: monkeypatch a probe to emit schema_slice with a secret-shaped key
    # act + assert
    result = CliRunner().invoke(cli, ["gather", str(tmp_path)])
    assert result.exit_code == 6
```

```python
# tests/unit/test_cli_tool_readiness.py
def test_tool_readiness_creates_cache_file(tmp_home_dir):
    # arrange: clean ~/.codegenie/
    # act: run gather (which calls the readiness check)
    CliRunner().invoke(cli, ["gather", str(tmp_path)])
    # assert
    cache = tmp_home_dir / ".codegenie" / ".tool-cache.json"
    assert cache.exists()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache.parent.stat().st_mode) == 0o700
```

```python
# tests/unit/test_cli_cold_start_imports.py
import subprocess, sys
def test_help_does_not_import_heavy_modules():
    # arrange: child process so we observe a fresh import graph
    out = subprocess.check_output(
        [sys.executable, "-c",
         "import sys; from codegenie.cli import cli;"
         " from click.testing import CliRunner; CliRunner().invoke(cli, ['--help']);"
         " print('\\n'.join(sorted(k for k in sys.modules if k.split('.')[0] in "
         "{'yaml','jsonschema','pydantic','blake3','structlog'})))"],
        text=True,
    )
    # assert: none of the heavy modules are present
    assert out.strip() == ""
```

Run all three; each fails (`ModuleNotFoundError`, `AttributeError`, or wrong exit code). Commit the failing tests.

### Green — make it pass

Implement `cli.py` per the outline above. Heavy imports inside command bodies. Exit-code dispatch table. Tool-readiness helper with atomic write + chmod. Defer `.gitignore` mutation to the helper S4-03 provides (use a stub raising `NotImplementedError` if S4-03 has not landed; S4-02's tests don't exercise that path).

### Refactor — clean up

- Pull the exit-code dispatch into a small typed dict (`dict[type[CodegenieError], int]`) at module scope.
- Add docstrings on `gather`, `audit verify`, and the tool-readiness helper.
- Ensure every probe lifecycle event name used by the coordinator (S3-05) flows through to stderr in JSON-on-non-TTY / pretty-on-TTY (handled by `configure_logging`; this story just calls it).
- Add a structured `cli.start` and `cli.end` event with `run_id=secrets.token_hex(8)` so audit records and structlog events share the same ID (per `../phase-arch-design.md §Harness engineering — Tracing strategy`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | New file — the entry point and lazy-import boundary |
| `tests/unit/test_cli_exit_codes.py` | New test — anchors the 0/2/3/5/6 exit code branches |
| `tests/unit/test_cli_tool_readiness.py` | New test — anchors the `~/.codegenie/.tool-cache.json` mode `0600` invariant per ADR-0011 |
| `tests/unit/test_cli_cold_start_imports.py` | New test — anchors the lazy-import boundary structurally |
| `pyproject.toml` | Confirm `[project.scripts] codegenie = "codegenie.cli:cli"` resolves (set in S1-01; no change expected) |

## Out of scope

- **`.gitignore` mutation prompt routine + TTY/non-TTY branches** — handled by story S4-03. This story calls into the routine via a thin shim.
- **End-to-end smoke tests against real fixtures + cache-hit-on-second-run** — handled by story S4-04.
- **Adversarial test suite** (`tests/adv/test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) — handled by story S4-05.
- **`cache gc` real implementation** — Phase 1+; this story ships only the stub subcommand.
- **`audit verify` re-verification logic** — landed in S3-06; this story only wires the subcommand into `click`.
- **External-tool readiness for binaries beyond `git`** — Phase 1 lights up `tree-sitter` etc.; Phase 0 only checks `git`.

## Notes for the implementer

- `import-linter` (from S1-05) blocks `yaml`, `jsonschema`, `pydantic`, `blake3`, `structlog` from being imported at module-import time in `cli.py`. The test `test_cli_cold_start_imports.py` is the structural defense; if `import-linter` fails the lint job, the issue is at module top of `cli.py` (not inside command bodies).
- Heavy imports inside command bodies must be at the *top* of the body, not lazily inside try/except — the test for `--help` cold-start checks `sys.modules` and any partial heavy-import would surface there.
- The `.gitignore` mutation routine in S4-03 must be callable without S4-03 having landed; ship a `_gitignore_mutation_stub(...)` that does nothing on first land, and S4-03 replaces it. Or land the stub interface here and the body in S4-03.
- `RepoSnapshot.git_commit` must be `None` (not raise) when the input path is not a git repo. `exec.run_allowlisted` will return non-zero from `git rev-parse HEAD`; catch and set to `None`.
- The exit-code dispatch table is the single source of truth for the documented codes — link it from the `--help` text via the docstring of `gather` so the documented codes can't drift from the implementation.
- The tool-readiness helper writes to `~/.codegenie/.tool-cache.json` *atomically* (`<tmp>` → `os.replace`) per ADR-0011, then `os.chmod 0600` on the file and `0700` on the directory. The `os.chmod` is idempotent.
- The `run_id = secrets.token_hex(8)` is the same value that ends up in the audit filename's `<short>` (the audit writer in S3-06 uses 4 hex; align on 4 here for filename brevity, or document the discrepancy in the structlog event docstring).
- Per ADR-0009, "exit 0 if ≥ 1 probe in `outputs`" is the contract — a `CacheHit` counts as a successful probe execution. Don't gate on "executed fresh."
