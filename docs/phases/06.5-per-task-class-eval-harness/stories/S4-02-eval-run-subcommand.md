# Story S4-02 — `codegenie eval run` subcommand end-to-end on the stub bench

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (CLI scaffold + exit codes), S3-02 (runner fan-out), S3-06 (cost-cap), S2-02 (loader), S2-04 (audit chain extension)
**ADRs honored:** ADR-0001 (subprocess rubric isolation surfaces here as exit semantics), ADR-0002 (`lower_bound_95` reported, not `mean`, as the gate signal), ADR-0010 (`isolation_class` annotated on every emitted report), Phase 5 ADR-0016 (eval-harness-as-trust-evidence)

## Context

`codegenie eval run --task-class=<name>` is the operator's primary entry point. It chains the Step 3 runner to the Step 2 loader and audit chain, emits one JSONL line per case + one aggregate line on stdout (default `--format=jsonl`), and persists a `BenchRunReport` JSON at `.codegenie/eval/runs/<utc-iso>-<short>.json`. Behind that one sentence sit five operator-visible flags (`--cases`, `--concurrency`, `--max-cost-usd`, `--no-cache`, `--with-verdict`) and seven exit-code paths from S4-01. Until this story lands, every later story that runs an end-to-end bench (S5-05, S6-03, S7-02) has no way to drive the harness.

The JSONL contract is structural: Phase 11 (PR provenance) will pipe these lines into a separate tool. Each per-case line is a self-describing `BenchScore` JSON object plus `case_id`; the aggregate line is the full `BenchRunReport`. The audit JSON at `.codegenie/eval/runs/` is byte-identical to the aggregate stdout payload (single source of truth). The cold-start budget from S4-01 (≤ 600 ms) continues to constrain — heavy imports stay deferred inside this command body.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` — usage line: `codegenie eval run --task-class=<name> [--cases=<glob>] [--concurrency=N] [--max-cost-usd=$] [--no-cache] [--out=<path>] [--with-verdict]`.
  - `../phase-arch-design.md §Happy path (cold cache, vuln-remediation, 10 cases)` — the end-to-end chain `cli → runner.plan → loader → audit.verify → runner.execute → audit.write_run_record → exit 0`.
  - `../phase-arch-design.md §Dynamic view → Sequence: nightly CI` — the orchestration the CLI implements.
  - `../phase-arch-design.md §Performance budgets` — vuln-remediation cold ≤ 12 min, warm ≤ 8 s (the run path); cold-start budget continues from S4-01.
  - `../phase-arch-design.md §Failure modes table` — rows 1, 2, 5, 6, plus cost-cap (§Happy path step 5) define the exit-code paths.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `lower_bound_95` is the gate signal; the report carries `mean_score`, `score_stddev`, AND `lower_bound_95`; the JSONL aggregate must emit all three.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — every emitted report carries `isolation_class="subprocess"` in Phase 6.5; the JSONL aggregate must surface this field so downstream tooling can partition.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — `--cases` glob must support filtering by `case_id`; held-out vs rag-corpus-derived is a `BenchCase` field, not a CLI selector.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the `--with-verdict` flag never auto-acts; it writes a recommendation file (S4-05).
- **Source design:** `../High-level-impl.md §Step 4` — names the exact flag list and the JSONL + audit JSON output shape.

## Goal

Implement `codegenie eval run` end-to-end on the stub bench fixture from S3-02: parse the five flags, load the task class + cases, run the runner, emit one JSONL line per case + one aggregate JSONL line on stdout, persist the report to `.codegenie/eval/runs/<utc-iso>-<short>.json`, and exit 0 on success / 2 on cost-cap / 3-6 on the typed startup failures from S4-01.

## Acceptance criteria

- [ ] `codegenie eval run --task-class=stub-task-class` over the S3-02 stub bench fixture exits 0; stdout has exactly `N+1` lines (one JSONL per case + one aggregate JSONL); `.codegenie/eval/runs/<utc-iso>-<short>.json` exists and round-trips to a valid `BenchRunReport`.
- [ ] The five flags are wired with the documented semantics:
  - `--cases='<glob>'`: filters by `case_id` (e.g., `--cases='001-*'` runs only case ids matching the glob); empty/missing means all cases; non-matching glob → exit 1 with a diagnostic naming the glob and the available case ids.
  - `--concurrency=N`: integer ≥ 1; overrides `Runner` default; out-of-range → exit 1 with a click-validation diagnostic.
  - `--max-cost-usd=<float>`: default 5.0; exceeding it triggers S3-06's cost-cap path → exit 2; the persisted report has `complete=False` and `run_id.startswith("partial:")`.
  - `--no-cache`: bypasses S2-03's content-addressed cache for the run (cache.get always misses); cache.put still writes the new entries.
  - `--with-verdict`: after the run, invoke `PromotionGate.evaluate(...)` (S4-04) and write a recommendation to `.codegenie/eval/recommendations/<utc-iso>.json` (S4-05). When the flag is absent, no verdict is computed and no recommendation file is written.
- [ ] **Stdout JSONL shape:** each per-case line is `{"kind": "case", "case_id": "...", "score": <BenchScore.score>, "passed": <bool>, "breakdown": {...}, "failure_modes": [...], "cost_usd": <float>, "wall_clock_s": <float>}`; the aggregate line is `{"kind": "aggregate", ...BenchRunReport fields...}` including `mean_score`, `score_stddev`, `lower_bound_95`, `passed_count`, `block_severity_failure_modes`, `isolation_class`, `complete`, `chain_head`, `run_id`.
- [ ] **`--format=human`** prints a small summary table (case-id, score, pass/fail) and a footer row with `mean / stddev / lower_bound_95`; no JSONL; same exit-code semantics.
- [ ] **Audit JSON path:** `.codegenie/eval/runs/<utc-iso>-<short>.json` where `<utc-iso>` is `report.run_started_iso` (e.g., `2026-05-12T14-32-08Z`) and `<short>` is the first 8 chars of `report.run_id`. The file is mode `0600`, written atomically (S2-04's `audit.write_run_record` is the writer; this story uses its return value, does not reimplement).
- [ ] **`--out=<path>`** optional override for the audit JSON destination; default `.codegenie/eval/runs/`.
- [ ] Exit-code paths from S4-01 are exercised: `TaskClassNotFound` → 3; `BenchCaseDigestMismatch` → 6; `ChainTamperDetected` → 5; cost-cap → 2; missing `bench/<name>/` directory → 4; success → 0.
- [ ] **Heavy imports remain deferred:** the `run` command body imports `runner`, `loader`, `audit`, `pydantic` lazily; the cold-start test from S4-01 stays green after this story lands.
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/integration/test_cli_run.py tests/unit/test_cli_run_flags.py` all pass on touched files.

## Implementation outline

1. Write red tests in `tests/unit/test_cli_run_flags.py` (flag parsing + glob filter) and `tests/integration/test_cli_run.py` (end-to-end stub bench) — see §TDD plan.
2. Fill in the `run` subcommand stub from S4-01:
   - Click options: `--task-class` (required), `--cases` (default `None`), `--concurrency` (`int`, default `None` so the runner picks its own), `--max-cost-usd` (`float`, default 5.0), `--no-cache` (flag), `--out` (`Path`, default `Path(".codegenie/eval/runs")`), `--with-verdict` (flag), `--bench-root` (`Path`, default `Path("bench")`).
   - Body (all imports inside the function):
     1. `from codegenie.eval.loader import load_task_class, load_cases`.
     2. `tc = load_task_class(task_class, bench_root)` — raises `TaskClassNotFound` (→ 3) / missing-dir (→ 4).
     3. `cases = load_cases(tc)` — raises `BenchCaseDigestMismatch` (→ 6) / `BenchCaseIDCollision` (→ 1).
     4. If `--cases` glob, filter `cases` by `fnmatch(case.case_id, glob)`; empty result → exit 1 with diagnostic.
     5. `from codegenie.eval.audit import verify; vr = verify(out_dir=out)` — `ChainTamperDetected` (→ 5).
     6. `from codegenie.eval.runner import Runner; runner = Runner(task_class=tc, cases=cases, concurrency=concurrency, max_cost_usd=max_cost_usd, no_cache=no_cache)`.
     7. `report = asyncio.run(runner.run_eval())` — internally calls `audit.write_run_record` and fills `report.chain_head`.
     8. Emit JSONL or human format to stdout per `ctx.obj["format"]`.
     9. If `--with-verdict`: `from codegenie.eval.promotion import PromotionGate; verdict = gate.evaluate(report)`; `from codegenie.eval.recommendation import write_recommendation; write_recommendation(verdict, ...)`.
     10. If `report.complete is False` (cost-cap): `sys.exit(EXIT_COST_CAP)`. Otherwise `sys.exit(EXIT_SUCCESS)`.
3. Implement the JSONL writer as a small helper `_emit_jsonl(report, stream)` in `cli.py` (or a sibling `cli_io.py` if it grows past ~20 lines). The aggregate line includes every wire field per S4-01's deferred-import discipline (no `pydantic.BaseModel.model_dump_json` at module top; call it lazily).
4. Implement `_emit_human(report, stream)` as a small text table.
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/test_cli_run_flags.py
from click.testing import CliRunner
from codegenie.eval.cli import eval as eval_group


def test_run_requires_task_class():
    runner = CliRunner()
    result = runner.invoke(eval_group, ["run"])
    assert result.exit_code != 0
    assert "--task-class" in result.output.lower()


def test_run_unknown_task_class_exits_three(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bench").mkdir()
    runner = CliRunner()
    result = runner.invoke(eval_group, ["run", "--task-class=does-not-exist"])
    assert result.exit_code == 3  # EXIT_TASK_CLASS_NOT_REGISTERED


def test_run_missing_bench_dir_exits_four(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No bench/ at all
    runner = CliRunner()
    result = runner.invoke(eval_group, ["run", "--task-class=anything"])
    assert result.exit_code == 4  # EXIT_BENCH_DIR_MISSING


def test_run_cases_glob_no_match_exits_one(stub_bench_root, monkeypatch):
    monkeypatch.chdir(stub_bench_root.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--cases=999-nothing-*"],
    )
    assert result.exit_code == 1
    assert "999-nothing" in result.output
```

```python
# tests/integration/test_cli_run.py
import json
from pathlib import Path
from click.testing import CliRunner
from codegenie.eval.cli import eval as eval_group


def test_run_stub_bench_exits_zero_emits_jsonl_and_writes_audit(stub_bench_root, monkeypatch):
    monkeypatch.chdir(stub_bench_root.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    lines = [ln for ln in result.output.splitlines() if ln.strip().startswith("{")]
    assert len(lines) == 4  # 3 cases + 1 aggregate (stub bench has 3 cases per S3-02)

    case_lines = [json.loads(ln) for ln in lines if json.loads(ln)["kind"] == "case"]
    agg_lines = [json.loads(ln) for ln in lines if json.loads(ln)["kind"] == "aggregate"]
    assert len(case_lines) == 3
    assert len(agg_lines) == 1

    agg = agg_lines[0]
    # ADR-0002: all three stats are reported, lower_bound_95 is gate signal
    for k in ("mean_score", "score_stddev", "lower_bound_95"):
        assert k in agg, f"aggregate missing {k}"
    # ADR-0010: isolation_class is annotated
    assert agg["isolation_class"] == "subprocess"
    # Gap #4: complete=True on a non-cost-capped run
    assert agg["complete"] is True
    assert agg["chain_head"]  # filled by audit.write_run_record

    runs_dir = Path(".codegenie/eval/runs")
    persisted = list(runs_dir.glob("*.json"))
    assert len(persisted) == 1
    on_disk = json.loads(persisted[0].read_text())
    assert on_disk["chain_head"] == agg["chain_head"]


def test_run_cost_cap_breach_exits_two_and_writes_partial(stub_bench_root_expensive, monkeypatch):
    # Stub bench whose SUT records cost > $0.01 per case
    monkeypatch.chdir(stub_bench_root_expensive.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        [
            "run",
            "--task-class=stub-expensive",
            "--max-cost-usd=0.005",
            "--no-cache",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2  # EXIT_COST_CAP

    runs_dir = Path(".codegenie/eval/runs")
    persisted = list(runs_dir.glob("*.json"))
    assert len(persisted) == 1
    on_disk = json.loads(persisted[0].read_text())
    assert on_disk["complete"] is False
    assert on_disk["run_id"].startswith("partial:")


def test_run_with_verdict_writes_recommendation(stub_bench_root, monkeypatch):
    monkeypatch.chdir(stub_bench_root.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--no-cache", "--with-verdict"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    rec_dir = Path(".codegenie/eval/recommendations")
    assert rec_dir.exists()
    recs = list(rec_dir.glob("*.json"))
    assert len(recs) == 1


def test_run_human_format_prints_table(stub_bench_root, monkeypatch):
    monkeypatch.chdir(stub_bench_root.parent)
    runner = CliRunner()
    result = runner.invoke(
        eval_group,
        ["--format=human", "run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # Human format: no JSONL lines on stdout
    json_lines = [ln for ln in result.output.splitlines() if ln.startswith("{")]
    assert json_lines == []
    # But the three statistics surface in human form
    for tok in ("mean", "stddev", "lower_bound_95"):
        assert tok in result.output.lower()
```

Run; confirm failures. Commit as the red marker.

### Green — make it pass

Implement the `run` command body per §Implementation outline. Use `Runner` from S3-02, `load_task_class` from S2-01, `load_cases` from S2-02, `verify` from S2-04. JSONL emission uses `report.model_dump_json()` (Pydantic v2). For human format: `click.echo` a small `tabulate` (or hand-rolled) table.

### Refactor — clean up

- Extract `_emit_jsonl` and `_emit_human` into small private helpers; do not over-abstract (Rule 2 — single-use code stays inline).
- Type hints on every helper (`mypy --strict`); `Stream` is `TextIO`.
- The `--cases` glob uses stdlib `fnmatch.fnmatch`; no regex.
- Log `structlog.info` at run-start with `task_class`, `cases_count`, `concurrency`, `max_cost_usd` so operators can grep audit logs by task class.
- The cost-cap path: the runner's `run_eval` returns a `BenchRunReport` with `complete=False` — the CLI does not re-raise an exception; it inspects `report.complete` and exits 2. (S3-06's contract is the runner returns the report; S4-01's `_map_exception_to_exit_code` is a parallel mapping for thrown errors.)
- Single source of truth for the persisted JSON: `audit.write_run_record(report, out_dir)` from S2-04. The stdout JSONL and the persisted JSON come from the *same* `report.model_dump_json()` call applied to the *same* finalized object (after `chain_head` is filled).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cli.py` | Fill in the `run` subcommand body; add JSONL/human emit helpers. |
| `tests/unit/test_cli_run_flags.py` | New file — flag parsing, validation, error paths. |
| `tests/integration/test_cli_run.py` | New file — end-to-end against the stub bench fixture from S3-02. |
| `tests/fixtures/bench/stub-task-class/` | If S3-02's fixture is not yet committed, scaffold a 3-case fixture here; coordinate with S3-02. |

## Out of scope

- **`PromotionGate` internals** — S4-04 owns `evaluate` and the all-conditions check. This story calls `gate.evaluate(report)` when `--with-verdict` is set and assumes the result is a `PromotionVerdict`.
- **Recommendation file format and writer** — S4-05 owns `.codegenie/eval/recommendations/<utc-iso>.json` shape and the `write_recommendation` callable. This story calls it.
- **`verify` and `promote-verdict` subcommands** — S4-03 and downstream stories.
- **Real benches (`bench/vuln-remediation/`, `bench/migration-chainguard-distroless/`)** — S5-* and S6-* land them. This story tests against the S3-02 stub fixture only.
- **Cache hit-rate testing** — S5-06 owns the integration tests for warm-run cache behavior.
- **`scaffold_bench_case.py`** — S5-07.

## Notes for the implementer

- **Single source of truth for `chain_head`.** `audit.write_run_record(report)` returns the new head and is the only writer; the CLI must use `report.model_copy(update={"chain_head": head})` (or accept the returned filled report from S2-04's API) before emitting to stdout. Stdout JSONL and on-disk JSON MUST share the same `chain_head` — drift here is a P0 bug.
- **`<utc-iso>` formatting:** Python's `datetime.isoformat()` produces `:` characters which break filename-safe paths on Windows and some FAT volumes. Use `strftime("%Y-%m-%dT%H-%M-%SZ")` — hyphens, not colons. Phase 0's `gather` output uses the same convention.
- **`<short>` is `report.run_id[:8]`.** Run IDs are content-addressed strings; the first 8 hex chars are the standard "short" form mirroring `git`.
- **`asyncio.run(runner.run_eval())`** — wrap the runner call exactly once per CLI invocation; do not let `asyncio.run` calls nest (runner uses its own loop and semaphore internally).
- **Cost-cap path is *non-exceptional*.** The runner does not raise on cost-cap; it returns a partial report. Only the CLI maps that to exit 2. If you find yourself adding a `CostCapExceeded` exception, push back to S3-06 — the design is for the runner to keep all its data on the report.
- **`--no-cache` flag semantics:** the runner's cache *reads* are bypassed (every case is a miss), but writes still happen. This lets a re-run with cache enabled hit. If you want a "no writes" mode, that is a separate flag (out of scope here).
- **Stdout newline discipline:** one JSON object per line; use `click.echo` (which appends `\n`); do not `print(..., flush=True)` — let Click handle buffering. Operators piping into `jq` need line-delimited input.
- **Heavy import audit:** after this story, re-run S4-01's cold-start test. If it goes over 660 ms, you imported a heavy module at the wrong scope; fix that before merging.
