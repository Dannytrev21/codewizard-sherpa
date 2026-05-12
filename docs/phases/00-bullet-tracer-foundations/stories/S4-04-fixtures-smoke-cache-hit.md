# Story S4-04 — Fixtures + end-to-end smoke + cache-hit-on-second-run

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready
**Effort:** M
**Depends on:** S4-01, S4-02
**ADRs honored:** ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0013

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

- [ ] `tests/fixtures/empty_repo/` contains exactly one file: `.gitkeep` (empty).
- [ ] `tests/fixtures/js_only/` contains three `.js` files, one `.mjs` file, one `.cjs` file, and a `README.md`. The README is the load-bearing piece — editing it between two runs in the cache-hit test must not invalidate the cache (it is **not** in `LanguageDetectionProbe.declared_inputs`).
- [ ] `tests/fixtures/polyglot/` contains at least one file per language branch of `LanguageDetectionProbe`: JS (`.js`), TS (`.ts`), Python (`.py`), Go (`.go`), Rust (`.rs`). Files may be one-liners.
- [ ] `tests/smoke/test_cli_end_to_end.py::test_help_exits_zero_and_lists_flags` runs `cli` with `["gather", "--help"]` and `["--help"]` (group-level help); exit code 0; the output contains every documented exit-code label (`0`, `2`, `3`, `5`, `6`) and every documented flag (`--verbose`, `--version`, `--refresh-tools`, `--no-gitignore`, `--auto-gitignore`).
- [ ] `tests/smoke/test_cli_end_to_end.py::test_gather_empty_repo` runs `cli` with `["gather", str(empty_repo_fixture)]`; exit code 0; `<fixture>/.codegenie/context/repo-context.yaml` exists and parses; `language_stack.counts == {}` and `language_stack.primary in (None, "")`.
- [ ] `tests/smoke/test_cli_end_to_end.py::test_gather_js_only` runs against `js_only/`; exit 0; `language_stack.primary == "javascript"`; `language_stack.counts["javascript"] == 5`.
- [ ] `tests/smoke/test_cli_end_to_end.py::test_gather_polyglot` runs against `polyglot/`; exit 0; `language_stack.counts` contains keys for every language present in the fixture; the chosen `primary` is deterministic (alpha-tie-broken among the max-count set per S4-01).
- [ ] **The load-bearing test** `tests/smoke/test_cli_end_to_end.py::test_cache_hit_on_second_run`:
  - [ ] Runs `gather` against `js_only/` once (cold).
  - [ ] Edits `<fixture>/README.md` (e.g., appends `"\nmore content\n"`).
  - [ ] Monkeypatches `os.scandir` **at the `codegenie.probes.language_detection` module level** (per `S4-01 §Notes for the implementer` and `High-level-impl.md §Step 4 risks specific to this step`) to a counting wrapper.
  - [ ] Runs `gather` against `js_only/` again (warm).
  - [ ] Asserts the counting wrapper recorded **zero** invocations on the second run.
  - [ ] Asserts the second run's `GatherResult.executions["language_detection"]` is a `CacheHit` (not `Ran`). This requires the test to obtain `GatherResult` either through a CLI-exposed JSON output mode, a structured-log capture, or a direct call to the coordinator (whichever the existing CLI surface supports — prefer the structured-log capture so the smoke remains CLI-level, not API-level).
  - [ ] Asserts a `probe.cache_hit` structlog event was emitted exactly once during the second run (redundant signal per the risk mitigation).
- [ ] Post-gather permission assertions on `js_only/`: every file under `.codegenie/` is mode `0600`; every directory is `0700` (per ADR-0011). Asserted via `os.stat` in at least one smoke test.
- [ ] Sanitizer output assertions: the produced YAML at `<fixture>/.codegenie/context/repo-context.yaml` contains **no** string starting with `/Users/`, `/home/`, `/root/`, or the absolute path of the test's `tmp_path` (per ADR-0008). Asserted via a substring scan in at least one smoke test.
- [ ] Schema validation pass: the produced YAML parses under `codegenie.schema.validator.validate(...)` with no `SchemaValidationError` (per ADR-0013).
- [ ] `pyproject.toml` `[tool.coverage]` `--cov-fail-under=85` (and the branch threshold) is **enabled live** (the S1-02-wired but PR-exempted carve-out is removed). The smoke + unit surface from Steps 1–4 must clear the gate.
- [ ] `ruff check`, `ruff format --check`, and `pytest tests/smoke/test_cli_end_to_end.py -q` all pass. (`mypy --strict` applies to `src/`; the smoke test file under `tests/` is on the relaxed config from S1-02.)

## Implementation outline

1. Create the three fixture directories under `tests/fixtures/`:
   - `empty_repo/.gitkeep` (empty file).
   - `js_only/{a,b,c}.js`, `js_only/m.mjs`, `js_only/c.cjs`, `js_only/README.md` (each `.js`/`.mjs`/`.cjs` is a one-liner like `// fixture`; `README.md` is one line like `# js_only fixture`).
   - `polyglot/main.js`, `polyglot/main.ts`, `polyglot/main.py`, `polyglot/main.go`, `polyglot/main.rs` (each a stub one-liner appropriate to the language).
2. Create `tests/smoke/__init__.py` (empty; makes the smoke suite a package per pytest convention) and `tests/smoke/test_cli_end_to_end.py`.
3. Implement each smoke test as a separate function. Use `click.testing.CliRunner` to invoke `cli`. For fixture isolation, **copy** each fixture to `tmp_path` before invoking (so `.codegenie/` writes don't pollute the source tree); a small fixture-copy helper at the top of the file is fine.
4. For the cache-hit test, structure as:
   - Run 1 (cold) → assert exit 0 and YAML on disk.
   - Append to `README.md`.
   - Monkeypatch `codegenie.probes.language_detection.os.scandir` (or the bare-name `scandir` if S4-01 imported `from os import scandir`) to a wrapper that increments a counter.
   - Run 2 (warm) → assert exit 0; counter is 0; `executions["language_detection"]` is `CacheHit`; `probe.cache_hit` event was emitted.
   - For asserting `executions`: the cleanest path is `caplog`-style capture of structlog events — the coordinator emits `probe.cache_hit` with the variant tag in its kwargs. Capture via `structlog.testing.capture_logs()` or the project's existing log-capture fixture (define one in `tests/conftest.py` if it doesn't exist).
5. Edit `pyproject.toml` to remove the Step 1 PR-only coverage carve-out (the `--cov-fail-under=0` override). The pre-existing `--cov-fail-under=85` from S1-02's `pyproject.toml` is the live setting.
6. Run the suite locally; iterate until green. Run `pytest --cov` and confirm the gate passes.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/smoke/test_cli_end_to_end.py`

The cache-hit test is the *single* anchor for this story (the other smoke tests follow once it's in shape). Write it first.

```python
# tests/smoke/test_cli_end_to_end.py
import shutil
from pathlib import Path
from click.testing import CliRunner
import structlog
from structlog.testing import capture_logs


def _copy_fixture(name: str, dst: Path) -> Path:
    src = Path(__file__).parent.parent / "fixtures" / name
    target = dst / name
    shutil.copytree(src, target)
    return target


def test_cache_hit_on_second_run(tmp_path, monkeypatch):
    # arrange: copy the js_only fixture into an isolated tmp_path
    fixture = _copy_fixture("js_only", tmp_path)
    from codegenie.cli import cli
    runner = CliRunner()

    # Run 1 (cold) — populates the cache
    result_cold = runner.invoke(cli, ["gather", str(fixture)])
    assert result_cold.exit_code == 0, result_cold.output
    assert (fixture / ".codegenie" / "context" / "repo-context.yaml").exists()

    # Mutate README.md — must NOT invalidate the cache because README.md
    # is not in LanguageDetectionProbe.declared_inputs
    (fixture / "README.md").write_text((fixture / "README.md").read_text() + "\nmore\n")

    # Monkeypatch os.scandir at the language_detection module level to count invocations.
    import codegenie.probes.language_detection as ld_mod
    calls = {"count": 0}
    real_scandir = ld_mod.os.scandir  # or ld_mod.scandir if S4-01 used `from os import scandir`

    def counting_scandir(*args, **kwargs):
        calls["count"] += 1
        return real_scandir(*args, **kwargs)

    monkeypatch.setattr(ld_mod.os, "scandir", counting_scandir)

    # Run 2 (warm) — must hit the cache
    with capture_logs() as logs:
        result_warm = runner.invoke(cli, ["gather", str(fixture)])

    # assert: warm run succeeded
    assert result_warm.exit_code == 0, result_warm.output
    # assert: os.scandir was never invoked from the language_detection module
    assert calls["count"] == 0, f"scandir invoked {calls['count']} times on warm run"
    # assert: probe.cache_hit event was emitted exactly once
    cache_hit_events = [e for e in logs if e.get("event") == "probe.cache_hit"]
    assert len(cache_hit_events) == 1, f"expected 1 probe.cache_hit event, got {len(cache_hit_events)}"
    # assert: the event identifies the language_detection probe
    assert cache_hit_events[0].get("probe") == "language_detection"
```

Run it. First failure: either `ModuleNotFoundError` (if S4-01/S4-02 haven't landed in the agent's branch yet — surface that), `FileNotFoundError` on the fixture directory (until step 1 of the implementation outline lands), or — once the fixture and code are present but the test itself is wrong — an assertion failure. Commit the failing test as the red marker.

Then add the simpler smoke tests (`test_help_exits_zero_and_lists_flags`, `test_gather_empty_repo`, `test_gather_js_only`, `test_gather_polyglot`) as separate red tests with `pytest.raises(...)` or expected-shape assertions. Each fails until both the fixture content and the CLI startup path are in place.

### Green — make it pass

1. Land the three fixture directories with the file shapes from the implementation outline.
2. Run the cache-hit test. If `calls["count"] > 0`, the bug is upstream: either S4-01's `declared_inputs` is `["**/*"]` (re-read S4-01 §Notes for the implementer), or S3-01's cache key incorporates a path that includes `README.md`, or the cache wasn't found on disk because S3-03's writer wrote to the wrong location. Diagnose by running with `--verbose` and inspecting the warm-run log stream.
3. If `executions["language_detection"]` isn't a `CacheHit`, the bug is in S3-05's coordinator: it ran the probe instead of returning the cached output. Inspect via the structlog stream: `probe.cache_hit` should fire instead of `probe.success` on the warm run.
4. Run the other smoke tests; iterate until each passes.

### Refactor — clean up

- Pull the fixture-copy helper into a `conftest.py` fixture (`@pytest.fixture def js_only_fixture(tmp_path): ...`) so each smoke test reads cleanly.
- Add the post-gather permission assertion to (at least) `test_gather_js_only`: iterate `<fixture>/.codegenie/`'s files and directories, assert modes `0600` / `0700` via `stat.S_IMODE(os.stat(p).st_mode)`.
- Add the sanitizer assertion to (at least) `test_gather_js_only`: read the YAML as text, assert no `/Users/`, `/home/`, `/root/`, or `str(tmp_path)` substring is present.
- Remove the Step 1 coverage carve-out from `pyproject.toml`. The pre-existing `--cov-fail-under=85` line stays untouched (already in S1-02).
- Run the full test suite (`pytest -q`) + coverage report. If branch coverage on `src/codegenie/` (excluding `cli.py`) is under 75%, add unit tests to the modules under-covered (do **not** weaken the gate; per `CLAUDE.md`'s Rule 12, "fail loud" beats "lower the bar").
- Run `ruff format` over the new test files; commit the cleaned form.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/empty_repo/.gitkeep` | New file — single-file fixture (smoke baseline) |
| `tests/fixtures/js_only/a.js`, `b.js`, `c.js`, `m.mjs`, `c.cjs`, `README.md` | New files — the cache-hit-load-bearing fixture; the README is the cache-invariant pin |
| `tests/fixtures/polyglot/main.{js,ts,py,go,rs}` | New files — one per language branch of `LanguageDetectionProbe` |
| `tests/smoke/__init__.py` | New file (empty) — makes `tests/smoke/` a pytest package |
| `tests/smoke/test_cli_end_to_end.py` | New test — the five smoke tests including the load-bearing cache-hit-on-second-run |
| `tests/conftest.py` | New or amended — fixture-copy helper, structlog `capture_logs` aliasing |
| `pyproject.toml` | Remove the Step 1 PR-only `--cov-fail-under=0` carve-out; the live gate at `--cov-fail-under=85` takes over from this PR forward |

## Out of scope

- **Adversarial tests** (`tests/adv/test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`, `test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py`) — handled by story S4-05.
- **Performance canaries** (`tests/bench/`) — handled by story S5-01.
- **Concurrent-cache test** — handled by story S5-01.
- **Integration tests against a real Node.js repo** — Phase 1 (`roadmap.md §"Phase 1"`).
- **Tree-sitter-based language disambiguation** — Phase 1; not in scope here.
- **Golden-output snapshots of `repo-context.yaml`** — Phase 2 (`tests/golden/` ships then).
- **`tests/fixtures/js_only/README.md` content quality** — it just needs to exist and be editable. A one-liner is fine.

## Notes for the implementer

- The cache-hit test is the **single most important test in Phase 0**. If it passes for the wrong reason (false-positive green), every Phase 1+ probe that relies on the cache invariant will appear to work locally and silently re-walk in CI. Per `High-level-impl.md §Step 4 risks specific to this step`: the redundant signal — asserting both the `os.scandir` invocation count **and** the `probe.cache_hit` structlog event — exists for this reason. Don't drop either assertion when "simplifying" the test.
- The monkeypatch target for `os.scandir` depends on how S4-01 imported it. Read `src/codegenie/probes/language_detection.py` first. If it has `import os` at the top and calls `os.scandir(...)`, monkeypatch via `codegenie.probes.language_detection.os.scandir`. If it has `from os import scandir`, monkeypatch via `codegenie.probes.language_detection.scandir`. The S4-01 module docstring should declare which form was chosen — if it doesn't, surface that as a gap and route the documentation back through S4-01 before proceeding.
- The fixture-copy helper exists because `CliRunner.invoke` will mutate `<fixture>/.codegenie/` on the *source tree* otherwise. Always copy to `tmp_path` first. `shutil.copytree` is the standard choice.
- The `js_only` fixture's exact JS count (5 files: 3 `.js` + 1 `.mjs` + 1 `.cjs`) is asserted in `test_gather_js_only` via `language_stack.counts["javascript"] == 5`. If you adjust the fixture count, update the assertion. Don't add a sixth file "for variety" — the assertion's specificity is intentional.
- The cache-hit test must not rely on the absence of `.gitignore` mutation prompts. Either:
  (a) The js_only fixture ships with a `.gitignore` already containing `.codegenie/` (idempotent path — `S4-03`'s helper returns without writing); **or**
  (b) The CLI invocation passes `--no-gitignore` so the routine takes the never branch.
  Pick (b) — explicit beats implicit, and `--no-gitignore` is the documented override per `S4-02 §Acceptance criteria`.
- Per ADR-0011 §Consequences, mode-bit assertions apply to post-`gather` state, **not** post-restore state. The smoke test runs gather, so it asserts post-gather modes. Don't add a "post-restore" assertion — there is no `actions/cache` restore in a local pytest run.
- Per ADR-0013, `additionalProperties: false` is strict at the envelope but loose under `probes.*`. The smoke YAML can grow `probes.language_detection.language_stack.<new_field>` in Phase 1 without breaking these tests; the assertions in this story check for specific keys, not the absence of others.
- Per `phase-arch-design.md §Goals` Goal #1, the YAML at minimum contains: `schema_version`, `generated_at`, `repo.root`, `repo.git_commit`, `probes.language_detection.language_stack.{counts, primary}`. If S3-03's writer doesn't populate these top-level fields from the CLI's envelope-merge step (S4-02), surface the gap — Phase 0's exit criterion does not pass without them.
- The coverage gate flip is the *last* thing in the implementation outline because it is the most likely to fail. Land the smoke tests first, run coverage, see what's uncovered. If a probe's edge case is uncovered, add a focused unit test — don't weaken the gate. Per `CLAUDE.md`'s global Rule 12 ("Fail loud"), a missed edge case is the kind of thing that *should* fail the gate.
