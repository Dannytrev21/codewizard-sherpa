# Story S4-04 — Fixtures + end-to-end smoke + cache-hit-on-second-run

**Status:** Done
**Completed:** 2026-05-13
**Attempts:** 1
**Evidence:**
- Files: `tests/fixtures/{empty_repo,js_only,polyglot}/*`, `tests/smoke/{__init__.py,conftest.py,test_cli_end_to_end.py}`, `.github/workflows/ci.yml`, `src/codegenie/coordinator/coordinator.py` (cache_key in probe.success), `src/codegenie/cli.py` (repo.root basename redaction)
- Tests: `tests/smoke/test_cli_end_to_end.py::{test_help_exits_zero_and_lists_flags__group, test_help_exits_zero_and_lists_flags__gather, test_gather_empty_repo, test_gather_js_only, test_gather_polyglot, test_envelope_required_fields_present, test_cache_hit_on_second_run, test_cache_miss_on_tracked_input_edit, test_audit_verify_smoke_run}` — 9 tests; full suite 577 passed, coverage 93.36% (clears 85% floor).
- Attempt log: [`_attempts/S4-04.md`](_attempts/S4-04.md)
- Commit: (pending human merge)

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Original status:** Ready (validated 2026-05-13)
**Effort:** M
**Depends on:** S4-01, S4-02
**ADRs honored (directly asserted):** ADR-0008, ADR-0009, ADR-0011, ADR-0013
**ADRs honored (transitively via deps):** ADR-0007 (via S2-02 snapshot test + S4-01 probe), ADR-0010 (via the coordinator's `_ProbeOutputValidator` chokepoint, exercised by every smoke run)

## Validation notes

Validated by `phase-story-validator` on 2026-05-13 — verdict **HARDENED**. Full audit at [`_validation/S4-04-fixtures-smoke-cache-hit.md`](_validation/S4-04-fixtures-smoke-cache-hit.md). Four block-level findings drove the edits below:

1. **Envelope-required-YAML-fields had no AC trace** (Goal #1 of `phase-arch-design.md`). Added explicit assertions for `schema_version`, `generated_at`, `repo.root`, `repo.git_commit`.
2. **`codegenie audit verify` was never exercised** (Goal #9 / Step 4 done-criteria). Added `test_audit_verify_smoke_run`.
3. **Monkeypatch blast radius made the load-bearing test observably flaky** — `monkeypatch.setattr(ld_mod.os, "scandir", ...)` mutates the global `os` module because `ld_mod.os IS os`. Replaced with a `types.SimpleNamespace`-based shim on the `os` *name binding* of the `language_detection` module — patches only the probe's lookup path, never any other caller of `os.scandir`.
4. **No test pinned the *negative* of the cache invariant** — a buggy "always return CacheHit" implementation would have passed every original AC. Added `test_cache_miss_on_tracked_input_edit` as the metamorphic partner of the existing hit test.

Harden-level edits also: tightened polyglot/js_only/empty_repo dict assertions to closed-world (`set(counts.keys()) == {...}`) and pinned `primary` values exactly; pinned permission and sanitizer scans to a named test with recursive walks; corrected the coverage-gate carve-out target from `pyproject.toml` (where it doesn't exist) to `.github/workflows/ci.yml:98` (where it does); stripped the `from os import scandir` hedge (S4-01 chose `import os` — final).

## Context

This is the bullet tracer's load-bearing exit. Every Phase 0 design doc converges on a single sentence: **"`codegenie gather <path>` runs end-to-end on empty / JS-only / polyglot fixtures and the cache hits on the second run."** This story ships that sentence. It writes the three fixtures, runs the CLI end-to-end against each, and pins the cache-hit-on-second-run assertion — the one test that proves the harness from S3-01 (cache), S3-02 (validator), S3-03 (sanitizer + writer), S3-05 (coordinator), S3-06 (audit) actually composes into a working pipeline, not just a set of unit-tested chokepoints.

The cache-hit test is also the gate for `phase-arch-design.md §Scenarios — Scenario 2` (the structural property that makes the cache invariant testable against a *non-empty* fixture — `README.md` edits must not invalidate the probe's cache entry because `declared_inputs` is extension-scoped, per S4-01).

This story flips the `--cov-fail-under=85` gate from wired-but-exempt (S1-02) to live: post-S4-04 the coverage gate enforces 85% line / 75% branch on the smoke surface.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals` — Goal #1 (CLI runs on three fixtures), Goal #4 (cache hits on non-empty fixture's second run).
  - `../phase-arch-design.md §Scenarios — Scenario 1: Cold gather over a JS fixture` — the happy path this story exercises end-to-end.
  - `../phase-arch-design.md §Scenarios — Scenario 2: Warm gather (cache hit, the bullet tracer's load-bearing exit)` — the cache-hit assertion; explains why `README.md` must be edited between runs.
  - `../phase-arch-design.md §Testing strategy — Fixture portfolio` — the three fixtures and their shapes (counts, file types).
  - `../phase-arch-design.md §Testing strategy — Test pyramid` — smoke tests live under `tests/smoke/` and run locally + in CI.
  - `../phase-arch-design.md §Edge cases` — row 9 (`fence` alarm — informational); row 13 (`pyyaml` fallback if `CSafeDumper` unavailable on contributor box).
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0009-cache-hit-pass-through-coordinator-output.md` — ADR-0009 — second run reports `executions["language_detection"] = CacheHit(...)`; the smoke test asserts the variant explicitly.
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — `LanguageDetectionProbe` from S4-01 honors the frozen ABC; smoke depends on its `declared_inputs` being extension-scoped.
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — post-gather, every file in `.codegenie/` is `0600`; every directory is `0700`. Smoke test asserts post-gather state.
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — produced YAML contains no absolute paths from `/Users/`, `/home/`, `/root/`, or the analyzed-repo prefix.
  - `../ADRs/0013-layered-additional-properties-schema.md` — ADR-0013 — the envelope validates strictly; `probes.language_detection.*` is loose under the per-probe sub-schema.
- **Source design:**
  - `../../../roadmap.md §"Phase 0"` — the exit criteria sentence this story makes real.
  - `../final-design.md §11 Exit criteria` — the refined criteria list including the cache-hit test.
- **Existing code:**
  - `src/codegenie/probes/language_detection.py` — the probe from S4-01. The smoke test uses its module-level `os.scandir` reference as the monkeypatch target.
  - `src/codegenie/cli.py` — the entry point from S4-02. Smoke uses `click.testing.CliRunner` to invoke it.
  - `src/codegenie/coordinator/coordinator.py` — `GatherResult.executions["language_detection"]` is what the cache-hit assertion reads.
  - `src/codegenie/logging.py` — `probe.cache_hit` is the structlog event the cache-hit test also asserts (redundant signal per `High-level-impl.md §Step 4 risks specific to this step`).
- **External docs (only if directly relevant):**
  - `click.testing.CliRunner` — the test harness for invoking `cli` in-process.

## Goal

`pytest tests/smoke/test_cli_end_to_end.py -q` exits 0; the suite covers `--help`, all three fixtures (`empty_repo`, `js_only`, `polyglot`), and the cache-hit-on-second-run test that asserts (a) `executions["language_detection"]` is `CacheHit` on the second invocation, (b) `os.scandir` is invoked zero times between the two runs (verified via monkeypatch at the `language_detection` module level), and (c) editing `README.md` in the fixture between the two runs does **not** invalidate the cache.

## Acceptance criteria

### Fixtures

- [x] `tests/fixtures/empty_repo/` contains exactly one file: `.gitkeep` (empty).
- [x] `tests/fixtures/js_only/` contains three `.js` files, one `.mjs` file, one `.cjs` file, and a `README.md`. The README is the load-bearing piece — editing it between two runs in the cache-hit test must not invalidate the cache (it is **not** in `LanguageDetectionProbe.declared_inputs`).
- [x] `tests/fixtures/polyglot/` contains exactly one file per language branch of `LanguageDetectionProbe`: `main.js`, `main.ts`, `main.py`, `main.go`, `main.rs`. Each is a one-liner appropriate to the language. No README.

### `--help` smoke (two invocations, asserted independently)

- [x] `test_help_exits_zero_and_lists_flags__gather`: `runner.invoke(cli, ["gather", "--help"]).exit_code == 0` AND output contains every documented flag (`--verbose`, `--version`, `--refresh-tools`, `--no-gitignore`, `--auto-gitignore`) AND for each documented exit code in `{0, 2, 3, 5, 6}` the regex `re.search(r"\bexit(\s+code)?\s+%d\b" % n, output)` matches.
- [x] `test_help_exits_zero_and_lists_flags__group`: `runner.invoke(cli, ["--help"]).exit_code == 0` AND output lists the subcommand names `gather`, `audit`, `cache`.

### Per-fixture smoke (closed-world dict assertions; specification by example)

- [x] `test_gather_empty_repo`: runs `cli` with `["gather", "--no-gitignore", str(empty_repo_fixture)]`; exit code 0; `<fixture>/.codegenie/context/repo-context.yaml` exists and parses as YAML; `language_stack.counts == {}` and `language_stack.primary is None` (pinned by S4-01 module docstring line 37; sub-schema `v0.1.1` declares `primary: {"type": ["string", "null"]}` — the empty-string sentinel is rejected).
- [x] `test_gather_js_only`: runs against `js_only/`; exit 0; `language_stack.counts == {"javascript": 5}` (exact dict equality; `set(counts.keys()) == {"javascript"}` is the closed-world clause that mutation-resists "ghost zero-count keys"); `language_stack.primary == "javascript"`.
- [x] `test_gather_polyglot`: runs against `polyglot/`; exit 0; `language_stack.counts == {"go": 1, "javascript": 1, "python": 1, "rust": 1, "typescript": 1}` (exact dict equality); `language_stack.primary == "go"` — the alphabetically-first language of the max-count tie set per S4-01's tie-break rule, deterministic across Python versions and `PYTHONHASHSEED`.

### Envelope-level required YAML fields (Phase 0 Goal #1)

- [x] `test_envelope_required_fields_present` (over the `js_only` fixture; once is enough since the envelope shape is fixture-independent): after parsing `<fixture>/.codegenie/context/repo-context.yaml`:
  - [x] Top-level keys are exactly `{"schema_version", "generated_at", "repo", "probes"}` (ADR-0013's strict envelope; no unknown top-level keys).
  - [x] `schema_version` is a non-empty string matching the version pinned by S3-02 (read the value from `src/codegenie/schema/repo_context.schema.json`'s `$id` or version field and compare).
  - [x] `generated_at` is a non-empty string parseable by `datetime.fromisoformat(...)` AND ends with `+00:00` or `Z` (UTC, per `phase-arch-design.md`).
  - [x] `repo.root` is a non-empty string with NO `/Users/`, `/home/`, `/root/`, or `str(fixture)` prefix (sanitizer-scrubbed per ADR-0008).
  - [x] `repo.git_commit` is either `None` (for the non-git `empty_repo` and copied-fixture cases — depending on what S4-02's CLI emits when `git rev-parse` fails) OR a string matching `^[0-9a-f]{7,40}$`. Pin the expected branch per fixture; surface as a Q in the executor's attempt log if S4-02 doesn't make this deterministic yet.

### Load-bearing cache-hit test (Scenario 2 from `phase-arch-design.md §Scenarios`)

- [x] **`test_cache_hit_on_second_run`** (load-bearing):
  - [x] Copies `js_only/` into `tmp_path/js_only/` via the `_copy_fixture` helper. The dir passed to `gather` is `fixture = tmp_path/js_only`.
  - [x] Run 1 (cold) with `["gather", "--no-gitignore", str(fixture)]`; exit code 0; `<fixture>/.codegenie/context/repo-context.yaml` exists.
  - [x] Captures the cold run's `probe.success` event for `language_detection` (it carries `cache_key=...`); records `cold_key`.
  - [x] Edits `<fixture>/README.md` (appends `"\nmore content\n"`). README is NOT in `LanguageDetectionProbe.declared_inputs`.
  - [x] **Module-local scandir patch (TQ-1 fix).** Builds a `types.SimpleNamespace` shim mirroring every public attribute of `os`, overrides only `scandir` with a counting wrapper, then `monkeypatch.setattr(ld_mod, "os", shim)`. This swaps the `os` *name binding inside `codegenie.probes.language_detection`* — global `os.scandir` is untouched, so cache-layer / writer / pytest internals never increment the counter. **Do not use** `monkeypatch.setattr(ld_mod.os, "scandir", ...)` — it mutates the global `os` module (because `ld_mod.os IS os`) and causes false-RED.
  - [x] Run 2 (warm) with the same args; exit code 0.
  - [x] The counting wrapper recorded **zero** invocations across run 2 (no other code path can trigger it now that the patch is module-local).
  - [x] Exactly one `probe.cache_hit` structlog event was emitted on run 2 with `event == "probe.cache_hit"` and `probe == "language_detection"`. The event is the CLI-observable proxy for `GatherResult.executions["language_detection"] = CacheHit(...)` — the typed `GatherResult` is not reachable from a `CliRunner` invocation in Phase 0 (no JSON output mode; reaching into the coordinator directly would break the CLI-level smoke framing).
  - [x] **No** `probe.success` event for `language_detection` fired on run 2 (negative-case clause — pins the variant: it was a CacheHit *instead of* a Ran).
  - [x] The warm run's `probe.cache_hit` event carries `cache_key=<warm_key>`; assert `warm_key == cold_key` byte-equal (proves the structural cache-key invariance — a buggy impl that recomputed a new key but happened to hit a different stored blob would fail this clause). *Gap-check before implementation:* if the coordinator's `probe.success` event doesn't yet carry `cache_key`, surface it in the executor's attempt log; either patch S3-05 or drop this byte-equality clause (the metamorphic pair with the miss-test below still pins both directions).

### Cache-miss negative test (mutation-resistance for the cache invariant)

- [x] **`test_cache_miss_on_tracked_input_edit`** (metamorphic partner of the hit test — without this, an "always return CacheHit" impl passes the whole story):
  - [x] Copy `js_only/` to `tmp_path/js_only/`; run cold; assert exit 0.
  - [x] Edit `<fixture>/a.js` — append `// changed\n` (a `.js` file IS in `LanguageDetectionProbe.declared_inputs`).
  - [x] Install the same module-local scandir-counting shim as the hit test (so the counter is observable but scoped).
  - [x] Run warm; assert exit 0.
  - [x] Counting wrapper recorded **at least one** invocation on the warm run (the probe was re-run).
  - [x] **No** `probe.cache_hit` event for `language_detection` on the warm run.
  - [x] Exactly one `probe.success` event for `language_detection` on the warm run.
  - [x] The warm run's reported `cache_key` differs from the cold run's (`warm_key != cold_key`) — proves the key was re-derived from the changed input.

### Audit verify smoke (Phase 0 Goal #9 / Step 4 done-criteria)

- [x] **`test_audit_verify_smoke_run`**:
  - [x] Run `gather` against `js_only/`; assert exit 0 and a run-record file exists at `<fixture>/.codegenie/context/runs/<utc>-<short>.json`.
  - [x] Invoke `runner.invoke(cli, ["audit", "verify"], catch_exceptions=False)` with the CWD changed to `<fixture>` (or with whatever scope flag S4-02's `audit verify` accepts — verify the exact invocation form in S4-02 before writing the test).
  - [x] Exit code 0.
  - [x] Stdout matches the documented zero-mismatch sentinel from S4-02 (e.g., `re.search(r"\b0 mismatch(es)?\b", result.output)`). If S4-02 doesn't print a deterministic sentinel, soften the assertion to `result.exit_code == 0` and surface as Q in the executor's attempt log.
  - [x] The run-record JSON parses and has the documented Phase 0 structure (`run_id`, `started_at`, `finished_at`, `yaml_sha256`, `probe_executions[*].blob_sha256`).

### Cross-cutting security / hygiene assertions (pinned to `test_gather_js_only`)

- [x] **Permission assertion (ADR-0011).** In `test_gather_js_only`: `for p in (fixture / ".codegenie").rglob("*"): mode = stat.S_IMODE(p.stat().st_mode); assert (mode == 0o600 if p.is_file() else mode == 0o700)`. The recursive `rglob("*")` is the load-bearing piece — without it a top-level-only check would let permission regressions in nested dirs slip through. Test is platform-gated: `@pytest.mark.skipif(sys.platform == "win32")` (Phase 0 CI is ubuntu-24.04 only per Goal #5; macOS dev is the other supported surface and matches Linux POSIX modes).
- [x] **Sanitizer assertion (ADR-0008).** In `test_gather_js_only`: read the produced YAML as text; assert that NONE of the substrings `/Users/`, `/home/`, `/root/`, `str(fixture)` (the analyzed-repo abs path the sanitizer scrubs), or `str(tmp_path)` (belt-and-suspenders superset) appear anywhere in the file. AC asserts an AND-condition (every prefix is absent), not OR — on macOS where `tmp_path` lives under `/var/folders/`, the `str(fixture)` clause is the load-bearing one.

### Schema and quality gates

- [x] Schema validation pass: the produced YAML parses under `codegenie.schema.validator.validate(...)` with no `SchemaValidationError` (per ADR-0013). Asserted in `test_gather_js_only` after the file is read.
- [x] **Coverage gate flip (corrected target).** The PR-only carve-out is in `.github/workflows/ci.yml:98` (`pytest -q --cov-fail-under=0`) — NOT in `pyproject.toml`. The wired floor at `pyproject.toml:162` (`--cov-fail-under=85 --cov-branch`) is already live. ACs:
  - [x] `.github/workflows/ci.yml:98` no longer contains the `--cov-fail-under=0` override; the `test` job invokes `pytest -q` only (the `addopts` in `pyproject.toml` apply automatically).
  - [x] The TODO comment block at `.github/workflows/ci.yml:81–84` (referencing S4-04) is removed.
  - [x] `pyproject.toml:162` still contains `--cov-fail-under=85` AND `--cov-branch` AND `--cov=src/codegenie` (unchanged from S1-02).
  - [x] Branch threshold of 75% per Goal #8 is encoded — verify it's present in `[tool.coverage.report]` (`fail_under` line / `--cov-branch` flag); document the current mechanism in the attempt log if S1-02 wired it differently than expected.
  - [x] No `# pragma: no cover` markers were added to `src/codegenie/**` in this PR's diff (assert at review via `git diff --unified=0 origin/master..HEAD -- 'src/codegenie/*' | grep '+.*# pragma: no cover'` returning no rows).
  - [x] `pytest -q --cov=src/codegenie --cov-branch --cov-fail-under=85` exits 0 locally — the live gate passes.
- [x] `ruff check`, `ruff format --check`, and `pytest tests/smoke/test_cli_end_to_end.py -q` all pass. (`mypy --strict` applies to `src/`; the smoke test file under `tests/` is on the relaxed config from S1-02.)

## Implementation outline

1. Create the three fixture directories under `tests/fixtures/`:
   - `empty_repo/.gitkeep` (empty file).
   - `js_only/{a,b,c}.js`, `js_only/m.mjs`, `js_only/c.cjs`, `js_only/README.md` (each `.js`/`.mjs`/`.cjs` is a one-liner like `// fixture`; `README.md` is one line like `# js_only fixture`).
   - `polyglot/main.{js,ts,py,go,rs}` — exactly one file per language; one-liner stubs.
2. Create `tests/smoke/__init__.py` (empty; makes the smoke suite a package per pytest convention) and `tests/smoke/test_cli_end_to_end.py`.
3. In `tests/conftest.py` (create or extend), add:
   - A `_copy_fixture(name, dst)` helper (used by every smoke test for tmp_path isolation).
   - An autouse fixture that pins the structlog config to the testing chain *before* the CLI re-initializes logging inside the runner — see "TDD plan / Notes for the implementer / TQ-6" below. Without this, `capture_logs()` can miss events emitted after the CLI calls `codegenie.logging.configure()`.
4. Implement each smoke test as a separate function. Use `click.testing.CliRunner` to invoke `cli`. Always invoke with `--no-gitignore` so the test is not coupled to TTY-prompt behavior (per the original Notes for the implementer, also matches S4-02 documented override).
5. For the cache-hit test, structure as:
   - Run 1 (cold) → assert exit 0 and YAML on disk; record the cold run's `cache_key` from the `probe.success` event payload.
   - Append `"\nmore content\n"` to `<fixture>/README.md` (this is the structural assertion: README is NOT in `declared_inputs`).
   - **Install the module-local scandir shim (TQ-1 fix).** Build a `types.SimpleNamespace` carrying every attribute of `os` plus a counting `scandir` wrapper. Replace the `os` *name binding* on the `language_detection` module via `monkeypatch.setattr(ld_mod, "os", shim)`. This is module-local: only `language_detection.os.scandir` is the counter; global `os.scandir` is untouched. **Do not** call `monkeypatch.setattr(ld_mod.os, "scandir", ...)` — that mutates the shared `os` module and produces false-RED whenever cache/writer/audit/pytest internals call `os.scandir` during the warm run.
   - Run 2 (warm) → assert exit 0; counter == 0; `probe.cache_hit` event fired once with `probe="language_detection"`; no `probe.success` event fired for `language_detection`; warm-run `cache_key == cold_key`.
6. For the cache-miss test (`test_cache_miss_on_tracked_input_edit`), same scaffold as the hit test but edit `a.js` instead of `README.md`. Assertions invert: counter > 0; one `probe.success` event for `language_detection`; no `probe.cache_hit` event; `warm_key != cold_key`.
7. For the audit-verify test, run `gather` first against `js_only/`, then `runner.invoke(cli, ["audit", "verify"])` scoped to the fixture's `.codegenie/`. Verify the exact invocation form in S4-02 before writing the test — if S4-02 took a `--scope <path>` flag, use it; if S4-02 reads CWD, set `CliRunner.invoke(cli, [...], standalone_mode=False)` with `cwd` switched (or skip CWD-switch and pass scope explicitly).
8. For the envelope-required-fields test, parse the YAML once, then assert on each top-level key plus `repo.root` / `repo.git_commit` shape. If `git_commit` is non-deterministic for the copied fixture (no `.git/`), surface as Q in the executor's attempt log and pin to the actual S4-02 behavior.
9. **Coverage-gate fix — corrected target.** Edit `.github/workflows/ci.yml`: at line 98, drop the `--cov-fail-under=0` override (change `pytest -q --cov-fail-under=0` to just `pytest -q`). Remove the now-stale TODO comment block at lines 81–84 referencing S4-04. **Do not edit `pyproject.toml:162`** — its `--cov-fail-under=85 --cov-branch` already takes effect via `addopts` as soon as the CI override is gone.
10. Add the post-gather permission assertion to `test_gather_js_only` (recursive `rglob("*")`; skipif Windows).
11. Add the sanitizer substring scan to `test_gather_js_only` (AND-condition across `/Users/`, `/home/`, `/root/`, `str(fixture)`, `str(tmp_path)`).
12. Run the suite locally; iterate until green. Run `pytest -q --cov=src/codegenie --cov-branch --cov-fail-under=85` and confirm the gate passes. If branch coverage on `src/codegenie/` (excluding `cli.py`) is under 75%, add focused unit tests to under-covered modules — **never** weaken the gate or add `# pragma: no cover` (per `CLAUDE.md` Rule 12).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/smoke/test_cli_end_to_end.py`

The metamorphic pair (`test_cache_hit_on_second_run` + `test_cache_miss_on_tracked_input_edit`) is the load-bearing anchor for this story. Write both before any other smoke test — together they pin the cache invariant in *both* directions; alone, either is bypassable by a trivially wrong implementation.

```python
# tests/smoke/test_cli_end_to_end.py
import os
import shutil
import types
from pathlib import Path
from click.testing import CliRunner
from structlog.testing import capture_logs


def _copy_fixture(name: str, dst: Path) -> Path:
    src = Path(__file__).parent.parent / "fixtures" / name
    target = dst / name
    shutil.copytree(src, target)
    return target


def _install_scandir_counter(monkeypatch, ld_mod) -> dict[str, int]:
    """Replace the ``os`` *name binding* on the language_detection module
    with a SimpleNamespace shim. Patches only ``ld_mod.os.scandir``;
    global ``os.scandir`` is untouched, so cache/writer/audit/pytest internals
    that call ``os.scandir`` during the warm run do NOT increment the counter.

    Why not ``monkeypatch.setattr(ld_mod.os, "scandir", ...)``?
    Because ``ld_mod.os IS os`` — that form mutates the shared os module and
    produces false-RED whenever any other code path scandirs during the test.
    """
    calls = {"count": 0}
    real_scandir = os.scandir

    def counting_scandir(*args, **kwargs):
        calls["count"] += 1
        return real_scandir(*args, **kwargs)

    shim = types.SimpleNamespace()
    for attr in dir(os):
        if not attr.startswith("_"):
            setattr(shim, attr, getattr(os, attr))
    shim.scandir = counting_scandir
    monkeypatch.setattr(ld_mod, "os", shim)
    return calls


def test_cache_hit_on_second_run(tmp_path, monkeypatch):
    fixture = _copy_fixture("js_only", tmp_path)
    from codegenie.cli import cli
    import codegenie.probes.language_detection as ld_mod
    runner = CliRunner()

    # Run 1 (cold) — populates the cache; capture cold cache_key.
    with capture_logs() as cold_logs:
        result_cold = runner.invoke(cli, ["gather", "--no-gitignore", str(fixture)])
    assert result_cold.exit_code == 0, result_cold.output
    assert (fixture / ".codegenie" / "context" / "repo-context.yaml").exists()
    cold_success = [e for e in cold_logs
                    if e.get("event") == "probe.success" and e.get("probe") == "language_detection"]
    assert len(cold_success) == 1, f"expected 1 probe.success on cold run, got {len(cold_success)}"
    cold_key = cold_success[0].get("cache_key")
    assert cold_key, "probe.success event must carry cache_key (gap-check against S3-05)"

    # Mutate README.md — must NOT invalidate the cache (README is not in declared_inputs).
    (fixture / "README.md").write_text((fixture / "README.md").read_text() + "\nmore content\n")

    # Install the module-local scandir-counting shim (TQ-1 fix).
    calls = _install_scandir_counter(monkeypatch, ld_mod)

    # Run 2 (warm) — must hit the cache.
    with capture_logs() as warm_logs:
        result_warm = runner.invoke(cli, ["gather", "--no-gitignore", str(fixture)])

    assert result_warm.exit_code == 0, result_warm.output
    assert calls["count"] == 0, f"scandir invoked {calls['count']} times on warm run"

    warm_hits = [e for e in warm_logs
                 if e.get("event") == "probe.cache_hit" and e.get("probe") == "language_detection"]
    warm_successes = [e for e in warm_logs
                      if e.get("event") == "probe.success" and e.get("probe") == "language_detection"]
    assert len(warm_hits) == 1, f"expected 1 probe.cache_hit, got {len(warm_hits)}"
    assert len(warm_successes) == 0, "probe.success must NOT fire on cache-hit warm run"
    assert warm_hits[0].get("cache_key") == cold_key, "cache_key invariance broken across runs"


def test_cache_miss_on_tracked_input_edit(tmp_path, monkeypatch):
    """Metamorphic partner of test_cache_hit_on_second_run.

    Edits a .js file (which IS in declared_inputs) between runs. The cache
    MUST miss; without this test, a buggy impl that always returns CacheHit
    passes every other AC in this story.
    """
    fixture = _copy_fixture("js_only", tmp_path)
    from codegenie.cli import cli
    import codegenie.probes.language_detection as ld_mod
    runner = CliRunner()

    with capture_logs() as cold_logs:
        result_cold = runner.invoke(cli, ["gather", "--no-gitignore", str(fixture)])
    assert result_cold.exit_code == 0, result_cold.output
    cold_success = [e for e in cold_logs
                    if e.get("event") == "probe.success" and e.get("probe") == "language_detection"]
    cold_key = cold_success[0].get("cache_key")

    # Edit a tracked input — a.js IS in declared_inputs.
    (fixture / "a.js").write_text((fixture / "a.js").read_text() + "// changed\n")

    calls = _install_scandir_counter(monkeypatch, ld_mod)

    with capture_logs() as warm_logs:
        result_warm = runner.invoke(cli, ["gather", "--no-gitignore", str(fixture)])

    assert result_warm.exit_code == 0, result_warm.output
    assert calls["count"] > 0, "probe must re-walk on tracked-input change"

    warm_hits = [e for e in warm_logs
                 if e.get("event") == "probe.cache_hit" and e.get("probe") == "language_detection"]
    warm_successes = [e for e in warm_logs
                      if e.get("event") == "probe.success" and e.get("probe") == "language_detection"]
    assert len(warm_hits) == 0, "cache must NOT hit when a tracked input changed"
    assert len(warm_successes) == 1, "probe must fire probe.success on cache miss"
    assert warm_successes[0].get("cache_key") != cold_key, "cache_key must change when inputs change"
```

Run both. First failure: either `ModuleNotFoundError` (if S4-01/S4-02 haven't landed in the agent's branch — surface that), `FileNotFoundError` on the fixture (until step 1 of the implementation outline lands), `AssertionError` on `cache_key` being unset (if S3-05's `probe.success` event doesn't carry the key — gap-check, file as Q in attempt log), or — once everything is wired — assertion failures from a wrong implementation. Commit the failing pair as the red marker.

Then add the per-fixture smoke tests, `test_envelope_required_fields_present`, `test_audit_verify_smoke_run`, and the two `--help` tests. Each fails until both the fixture content and the CLI startup path are in place.

### Green — make it pass

1. Land the three fixture directories with the file shapes from the implementation outline.
2. Run the metamorphic pair. If the hit test reports `calls["count"] > 0`, the bug is upstream: either S4-01's `declared_inputs` is `["**/*"]` (re-read S4-01 §Notes for the implementer), or S3-01's cache key incorporates a path that includes `README.md`, or the cache wasn't found on disk because S3-03's writer wrote to the wrong location. Diagnose by running with `--verbose` and inspecting the warm-run log stream.
3. If the warm run still emits `probe.success` instead of `probe.cache_hit` (or both fire), the bug is in S3-05's coordinator: it ran the probe instead of returning the cached output. The `probe.success`-absence assertion is the variant-pin — failing it identifies the bug class precisely.
4. If the miss test reports `calls["count"] == 0` or no `probe.success`, the cache is incorrectly returning a hit on a tracked-input change — same coordinator bug, opposite direction. The metamorphic pair makes both directions debuggable in isolation.
5. If `cache_key` is missing from `probe.success` events, surface as Q in the executor's attempt log; either patch S3-05 to emit it or drop the byte-equality clauses (the structural assertions still pin the invariant).
6. Run the other smoke tests (`--help` × 2, three per-fixture, envelope, audit-verify); iterate until each passes.

### Refactor — clean up

- Promote the fixture-copy helper to a `conftest.py` fixture (`@pytest.fixture def js_only_fixture(tmp_path): ...`) so each smoke test reads cleanly. Move `_install_scandir_counter` to `conftest.py` too so both metamorphic tests share it.
- The post-gather permission assertion (`rglob("*")` + `stat.S_IMODE`) and the sanitizer substring scan are part of `test_gather_js_only` from the red phase — no refactor work, just keep them tight.
- Edit `.github/workflows/ci.yml`: drop the `--cov-fail-under=0` override on line 98 (the `test` job's pytest invocation becomes `pytest -q`); remove the now-stale TODO comment at lines 81–84. `pyproject.toml:162` is unchanged (already at `--cov-fail-under=85 --cov-branch` from S1-02).
- Run the full test suite (`pytest -q`) + coverage report. If branch coverage on `src/codegenie/` (excluding `cli.py`) is under 75%, add unit tests to the modules under-covered (do **not** weaken the gate; do **not** add `# pragma: no cover` markers — per `CLAUDE.md`'s Rule 12, "fail loud" beats "lower the bar").
- Run `ruff format` over the new test files; commit the cleaned form.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/empty_repo/.gitkeep` | New file — single-file fixture (smoke baseline) |
| `tests/fixtures/js_only/a.js`, `b.js`, `c.js`, `m.mjs`, `c.cjs`, `README.md` | New files — the cache-hit-load-bearing fixture; the README is the cache-invariant pin |
| `tests/fixtures/polyglot/main.{js,ts,py,go,rs}` | New files — one per language branch of `LanguageDetectionProbe` |
| `tests/smoke/__init__.py` | New file (empty) — makes `tests/smoke/` a pytest package |
| `tests/smoke/test_cli_end_to_end.py` | New test — the metamorphic cache pair + per-fixture smokes + envelope-required-fields + audit-verify smoke + `--help` × 2 |
| `tests/conftest.py` | New or amended — fixture-copy helper, `_install_scandir_counter` shim, structlog-config autouse fixture (so `capture_logs()` captures across `cli.configure()` re-init — see Notes TQ-6) |
| `.github/workflows/ci.yml` | **Coverage carve-out fix (corrected target).** Drop `--cov-fail-under=0` from the `test` job's pytest invocation at line 98; remove the stale `TODO(S4-04)` comment block at lines 81–84. The `pyproject.toml:162` floor at `--cov-fail-under=85 --cov-branch` then takes effect for every CI run. |
| `pyproject.toml` | **Verify only — no edit required.** Line 162 (`--cov-fail-under=85 --cov-branch`) is already wired by S1-02. Confirm at PR time; if anything has drifted, re-pin to those flags. The original story instructed editing `pyproject.toml` to remove a literal `--cov-fail-under=0` carve-out, but that string does not exist there — it is in `.github/workflows/ci.yml:98`. |

## Out of scope

- **Adversarial tests** (`tests/adv/test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`, `test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`) — handled by story S4-05.
- **Performance canaries** (`tests/bench/`) — handled by story S5-01.
- **Concurrent-cache test** — handled by story S5-01.
- **Hypothesis-driven property/metamorphic tests** for the cache invariant — the specification-by-example pair (`test_cache_hit_on_second_run` + `test_cache_miss_on_tracked_input_edit`) pins both directions; a richer property family (∀ untracked-edit ⇒ HIT; ∀ tracked-edit ⇒ MISS) lifts in S5-01 alongside the bench canaries.
- **`CSafeDumper`-unavailable fallback testing** — covered by S3-03's `tests/unit/test_output_writer.py`; the smoke runs with whatever YAML dumper is present on the contributor box.
- **Integration tests against a real Node.js repo** — Phase 1 (`roadmap.md §"Phase 1"`).
- **Tree-sitter-based language disambiguation** — Phase 1; not in scope here.
- **Golden-output snapshots of `repo-context.yaml`** — Phase 2 (`tests/golden/` ships then).
- **`tests/fixtures/js_only/README.md` content quality** — it just needs to exist and be editable. A one-liner is fine.
- **A `--json` output mode on the CLI** that exposes typed `GatherResult.executions` — out of scope per S4-02; the smoke uses `structlog.testing.capture_logs()` as the CLI-observable proxy for the variant.

## Notes for the implementer

- The metamorphic pair (`test_cache_hit_on_second_run` + `test_cache_miss_on_tracked_input_edit`) is the **single most important pair of tests in Phase 0**. If either passes for the wrong reason, every Phase 1+ probe that relies on the cache invariant will appear to work locally and either silently re-walk in CI (hit-broken) or silently re-use stale outputs forever (miss-broken). The redundant-signal mitigation per `High-level-impl.md §Step 4 risks` lives across THREE dimensions on each test: scandir-count, event variant (`probe.cache_hit` vs `probe.success` presence/absence), and `cache_key` value. Don't drop any of the three when "simplifying" the tests.
- **Monkeypatch target — final, no hedge.** S4-01 chose `import os` (see `src/codegenie/probes/language_detection.py` module docstring line 24, line 52). The patch always goes through the module-local `os` *name binding* — never through `ld_mod.os.<attr>` directly. The `_install_scandir_counter` helper in the TDD plan implements this with a `types.SimpleNamespace` shim. Do NOT use `monkeypatch.setattr(ld_mod.os, "scandir", ...)` — it mutates the global `os` module (since `ld_mod.os IS os`) and produces false-RED whenever any other call site scandirs during the warm run.
- **`capture_logs()` and CLI logging init (TQ-6).** `structlog.testing.capture_logs()` works by swapping the active processor chain inside the `with` block. If the CLI calls `codegenie.logging.configure()` *inside* the `CliRunner.invoke(...)` (it does, per S2-04), the configure call replaces structlog's config with the production chain — `capture_logs()` may then see nothing on the warm run. The `tests/conftest.py` autouse fixture must pin the structlog config to the testing chain BEFORE the CLI's `configure()` runs (call `codegenie.logging.configure()` once at fixture scope, then enter the `capture_logs()` context inside the test). Verify on the cold run: at least one `probe.success` event for `language_detection` must appear in `cold_logs` — if none does, the capture is broken, not the implementation.
- **Sanitizer scope is the YAML, not the structlog stream (CON-6).** Per ADR-0008, `OutputSanitizer.scrub` is a chokepoint on `RepoContext` emission, NOT a structlog processor. The sanitizer AC scans the on-disk YAML only. Per-call-site log-payload sanitization is the probe's responsibility (S4-01 AC-4 pins it for `LanguageDetectionProbe`'s symlink events). Adversarial log-leak tests are S4-05's surface, not this story's.
- The fixture-copy helper exists because `CliRunner.invoke` will mutate `<fixture>/.codegenie/` on the *source tree* otherwise. Always copy to `tmp_path` first. `shutil.copytree` is the standard choice.
- The `js_only` fixture's exact JS count (5 files: 3 `.js` + 1 `.mjs` + 1 `.cjs`) is asserted in `test_gather_js_only` via `counts == {"javascript": 5}` (exact dict equality, closed-world). If you adjust the fixture count, update the assertion. Don't add a sixth file "for variety" — the assertion's specificity is intentional and mutation-resists "ghost zero-count keys."
- The polyglot fixture has exactly one file per language. With all counts at 1, the alpha-tie-break makes `primary == "go"` deterministically (alphabetically first of `{go, javascript, python, rust, typescript}`). Both clauses are pinned to exact values per S4-01's tie-break rule — don't relax either.
- Every CLI invocation in the smoke suite passes `--no-gitignore` so the test is not coupled to `.gitignore`-prompt behavior. `--no-gitignore` is the documented override per S4-02 §AC; explicit beats implicit.
- Per ADR-0011 §Consequences, mode-bit assertions apply to post-`gather` state, **not** post-restore state. The smoke test runs gather, so it asserts post-gather modes. Don't add a "post-restore" assertion — there is no `actions/cache` restore in a local pytest run.
- Per ADR-0013, `additionalProperties: false` is strict at the envelope but loose under `probes.*`. The envelope test asserts the top-level key SET is exactly `{schema_version, generated_at, repo, probes}` (closed-world for the envelope); the per-probe slice assertions check for specific keys, not the absence of others, so Phase 1 can extend `probes.language_detection.language_stack` without breaking these tests.
- Per `phase-arch-design.md §Goals` Goal #1, the YAML at minimum contains: `schema_version`, `generated_at`, `repo.root`, `repo.git_commit`, `probes.language_detection.language_stack.{counts, primary}`. If S3-03's writer doesn't populate these top-level fields from the CLI's envelope-merge step (S4-02), surface the gap — Phase 0's exit criterion does not pass without them. The `test_envelope_required_fields_present` AC pins this.
- **Coverage gate flip — corrected target.** The PR-only carve-out is `--cov-fail-under=0` on the `test` job's pytest invocation in `.github/workflows/ci.yml` (line 98), **not** anything in `pyproject.toml`. The wired floor at `pyproject.toml:162` (`--cov-fail-under=85 --cov-branch`) is already live and takes effect as soon as the workflow override is removed. Land the smoke tests first, run coverage, see what's uncovered. If a probe's edge case is uncovered, add a focused unit test — don't weaken the gate, don't add `# pragma: no cover`. Per `CLAUDE.md` Rule 12 ("Fail loud"), a missed edge case is the kind of thing that *should* fail the gate.
