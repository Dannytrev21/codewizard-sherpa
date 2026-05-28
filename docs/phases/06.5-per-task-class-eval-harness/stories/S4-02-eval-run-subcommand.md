# Story S4-02 — `codegenie eval run` subcommand end-to-end on the stub bench

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** HARDENED (phase-story-validator, 2026-05-28)
**Effort:** M
**Depends on:** S4-01 (CLI scaffold + `eval_group` symbol + exit-code table), S3-01 (`Runner.plan` — owns chain-verify + tamper/digest raises), S3-02 (`Runner.execute` fan-out), S3-06 (`Runner.run_eval` — the audit-writing composition root + cost-cap partial report), S2-01 (`load_task_class` — invoked *inside* `plan`), S2-02 (`load_cases` — invoked *inside* `plan`), S2-03 (`cache_dir` content-addressed cache — `--no-cache` routes to an ephemeral dir), S2-04 (`write_run_record` filename + `verify` return contract), S4-04 (`PromotionGate` — `--with-verdict`), S4-05 (`write_recommendation` — `--with-verdict`)
**ADRs honored:** ADR-0001 (subprocess rubric isolation surfaces here as exit semantics), ADR-0002 (`lower_bound_95` reported, not `mean`, as the gate signal), ADR-0010 (`isolation_class` annotated on every emitted report), Phase 5 ADR-0016 (eval-harness-as-trust-evidence)

## Validation notes (phase-story-validator, 2026-05-28)

Hardened in place — the goal traces cleanly to `phase-arch-design.md §Exit criteria #6`, but the story was written before its dependencies were hardened and drifted from their locked APIs. Verdict **HARDENED**; full audit log at `_validation/S4-02-eval-run-subcommand.md`. Key corrections:

- **F-CON-1 (BLOCK): `eval_group`, not `eval`.** S4-01 renamed the Click group to `eval_group` (no `eval` alias) to avoid shadowing the builtin. Every import/test reference updated.
- **F-CON-2 (BLOCK): the runner API.** There is no `Runner(task_class=…, cases=…, no_cache=…)` constructor and no zero-arg `run_eval()`. `Runner()` is stateless; the flow is `plan = Runner().plan(name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version)` → `report = await Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency, max_cost_usd, out_dir)`.
- **F-CON-3 (BLOCK): `plan()` already verifies the chain; `verify()` returns, it does not raise.** `Runner.plan` (S3-01 AC-4) calls `audit.verify` internally and raises `ChainTamperDetected` (→5) / `BenchCaseDigestMismatch` (→6) before any SUT call. The CLI does **not** call `verify` separately on the run path; the exit-5/6 paths flow from `plan()` raising → S4-01's `main()` mapper. (`audit.verify` itself returns a `VerifyResult`; it never raises — that lives in S4-03's `verify` subcommand.)
- **F-CON-4 (BLOCK): `chain_head` is filled by `run_eval`, not the CLI.** S3-06 AC-2 makes `run_eval` return a report with `chain_head` already stamped; the CLI emits it verbatim. The old `report.model_copy(update={"chain_head": head})` note was wrong — `head` is never in CLI scope.
- **F-CON-5 (BLOCK): the audit filename is `write_run_record`'s, not the CLI's.** S2-04 pins `f"{utc_iso}-{secrets.token_hex(4)}.json"` — `<short>` is a random token, not `run_id[:8]`; the CLI never constructs or sees the path (`run_eval` writes internally). The CLI learns the file exists by globbing `out`. All filename-derivation ACs replaced with glob-count + round-trip + `chain_head`-equality assertions.
- **F-CON-6 (BLOCK): `PromotionGate`.** `PromotionGate(tier_config, registry=None)` built from `load_tier_config(Path("docs/trust-tiers.yaml"))`; `evaluate(report, target_tier, *, evidence_window=())`. `--with-verdict` gains an optional `--target-tier` (defaults to the task class's current tier) and is **skipped on `complete is False`** (evaluate raises `IncompleteReportForPromotion` on partials; the run exits 2 anyway).
- **F-CON-7 (BLOCK): `write_recommendation(verdict, out_dir)`** takes the directory, not a full path.
- **F-CON-8 (BLOCK): `--no-cache` has no runner seam.** S3-02 F-DP-8 deferred the cache-disable injection. `--no-cache` therefore routes the run's `cache_dir` to a fresh ephemeral directory (reads always miss; writes discarded; canonical cache untouched). The old "writes still persist to the canonical cache" claim is removed.
- **F-COV-1 / F-DP-1 (BLOCK): SUT/rubric/`sut_digest_fn` sourcing was undesigned.** The CLI holds only a task-class *name*; `TaskClass` carries `rubric_class` but no SUT. Added a `codegenie.eval.sut_registry` resolver (`@register_sut(name)` / `resolve_sut(name)`) mirroring the repo's three existing decorator-registries — the rubric_runner is built from `task_class.rubric_class`, the SUT + `sut_digest_fn` come from the resolver. New AC-3 + AC-12 make the seam and its observable extension constraint testable. **The executor should record this `name → SystemUnderTest` decision in a one-paragraph ADR (`phase-architect`)** since S5-05/S6-03/Phase-9 all consume it.
- **F-CON-9 (HARDEN): test paths** moved to `tests/unit/eval/` + `tests/integration/eval/` (S4-01 convention).
- **F-COV-3 (HARDEN): `--cases` glob** filters `plan.cases` *after* `plan()` via `dataclasses.replace(plan, cases=…, cache_keys=…)` (preserves the S3-01 AC-1a invariant).
- Test-quality hardening (F-TQ-2..6): typed JSONL assertions, `chain_head` equality + `verify().ok`, cost-cap partial contract (`len(per_case)==len(cases)`, no `CancelledError`), human-format **no-JSON** assertion, cold-start re-assertion.

## Context

`codegenie eval run --task-class=<name>` is the operator's primary entry point. It resolves the task class's SUT + rubric, drives the Step 3 runner (`plan` → `run_eval`, which loads, chain-verifies, fans out, and appends to the audit chain), emits one JSONL line per case + one aggregate line on stdout (default `--format=jsonl`), and persists one chained `BenchRunReport` JSON under `out` (default `.codegenie/eval/runs/`; the exact `<utc_iso>-<token>.json` filename is owned by `write_run_record`, S2-04 — the CLI globs `out`, it does not build the name). Behind that one sentence sit the operator flags (`--cases`, `--concurrency`, `--max-cost-usd`, `--no-cache`, `--out`, `--with-verdict`, `--target-tier`, `--bench-root`) and the seven-code exit partition from S4-01. Until this story lands, every later story that runs an end-to-end bench (S5-05, S6-03, S7-02) has no way to drive the harness.

The JSONL contract is structural: Phase 11 (PR provenance) will pipe these lines into a separate tool. Each per-case line is a self-describing `BenchScore` JSON object plus `case_id`; the aggregate line is the full `BenchRunReport`. **Single source of truth:** `Runner.run_eval` (S3-06) calls `audit.write_run_record` internally and returns a `BenchRunReport` whose `chain_head` is already stamped (`model_copy`); the CLI emits *that* finalized object to stdout. The on-disk record and the stdout aggregate share the same `chain_head` because S2-04 AC-3a pins the persisted `chain_head` to equal the returned head — the CLI does not re-stamp anything and never sees the written path (it globs `out` to confirm the append). The cold-start budget from S4-01 (≤ 600 ms) continues to constrain — heavy imports (`runner`, `audit`, `promotion`, `pydantic`, `sut_registry`) stay deferred inside this command body.

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

Implement `codegenie eval run` end-to-end on the stub bench fixture from S3-02 against the corrected runner contract: parse the flags, resolve the task class's SUT via the `sut_registry` seam and its rubric_runner from `task_class.rubric_class`, call `Runner().plan(...)` (which loads + chain-verifies internally and raises `ChainTamperDetected`/`BenchCaseDigestMismatch` on bad state), optionally narrow `plan.cases` by the `--cases` glob, call `Runner().run_eval(plan, ...)` (which fans out, aggregates, and appends one chained `BenchRunReport` under `out`), emit one JSONL line per case + one aggregate JSONL line on stdout, and exit 0 on a complete run / 2 on cost-cap (`report.complete is False`) / 1 on a non-matching glob / 3-6 on the typed `plan()` failures mapped by S4-01's `main()`.

## Acceptance criteria

- [ ] **AC-1 (end-to-end happy path):** `codegenie eval run --task-class=stub-task-class --no-cache` over the S3-02 stub bench fixture exits 0; stdout has exactly `N+1` JSONL lines (one per case + one aggregate, `N` = stub-bench case count); exactly one new `*.json` appears under `out` (default `.codegenie/eval/runs/`) and round-trips to a valid `BenchRunReport`; `audit.verify(out).ok is True` after the run.
- [ ] **AC-2 (corrected runner flow — observable):** the `run` body uses the hardened two-call contract — `plan = Runner().plan(task_class, sut_digest_fn=…, bench_root=…, out_dir=out, run_started_iso=…, cassette_root=…, harness_version=…)` then `report = asyncio.run(Runner().run_eval(plan, system_under_test=sut, rubric_runner=rr, cache_dir=cache_dir, timeout_per_case_seconds=…, concurrency=concurrency, max_cost_usd=max_cost_usd, out_dir=out))`. It does **not** construct `Runner(task_class=…)`, does **not** call a zero-arg `run_eval()`, does **not** call `load_task_class`/`load_cases`/`verify` directly, and does **not** `model_copy` the returned report. (Pinned structurally by AC-13's AST/import test + the integration test passing.)
- [ ] **AC-3 (SUT-resolver seam — `sut_registry`):** the CLI obtains the SUT via a new `codegenie.eval.sut_registry` module exposing `@register_sut(task_class_name)` / `resolve_sut(name) -> SystemUnderTest` / `default_sut_registry: Final[SutRegistry]` / a `registry=` DI kwarg, following the kernel discipline of the repo's three sibling registries (`default_registry` S1-03, `plugins/registry`, `transforms/signal_kinds`): duplicate registration raises a collision error naming both origins, the default singleton is `Final`, and `resolve_sut` raises a typed error mapped to exit 3 (treat an unregistered SUT like an unregistered task class) when no SUT is registered for `name`. The `rubric_runner` is built from `task_class.rubric_class` (S3-03), **not** the resolver. `sut_digest_fn` is supplied by the resolved SUT entry. A unit test registers a stub SUT into a fresh `SutRegistry()` and asserts `resolve_sut("x", registry=reg)` returns it.
- [ ] **AC-4 (`--cases` glob filters `plan.cases`, preserving the invariant):** with `--cases='<glob>'` the CLI computes `filtered = tuple(c for c in plan.cases if fnmatch.fnmatch(c.case_id, glob))`; empty `filtered` → exit 1 with a diagnostic naming the glob **and** the available case ids; otherwise `plan = dataclasses.replace(plan, cases=filtered, cache_keys={c.case_id: plan.cache_keys[c.case_id] for c in filtered})` (re-runs S3-01 AC-1a's `__post_init__`; the cache-keys/cases invariant holds). Empty/missing `--cases` runs all cases. A test asserts `--cases='001-*'` over a ≥2-case stub runs exactly the matching subset (stdout case-line count == matched count).
- [ ] **AC-5 (`--concurrency`):** `click.IntRange(min=1)`-typed; default `None` (the runner picks its own bound — S3-02); `--concurrency=0`/negative → click usage error (exit ≠ 0) without entering the run body.
- [ ] **AC-6 (`--max-cost-usd` cost-cap → exit 2, partial report):** default 5.0; when `run_eval` returns `report.complete is False` (S3-06 cost-cap), the CLI exits 2; the persisted record has `complete=False`, `run_id.startswith("partial:")`, and `len(per_case) == len(plan.cases)` (S3-06 `_Aborted` placeholders). No `CancelledError` escapes (the run does not crash). The CLI inspects `report.complete` — it does **not** expect a `CostCapExceeded` exception.
- [ ] **AC-7 (`--no-cache` → ephemeral cache_dir):** `--no-cache` routes the run's `cache_dir` to a fresh ephemeral directory (e.g. `tempfile.mkdtemp(prefix="codegenie-eval-nocache-")`), so every `cache.get` misses and all writes are discarded; the canonical `.codegenie/eval/cache/` tree is never read or written for the run. A test asserts the canonical cache dir gains zero entries after a `--no-cache` run. (S3-02 F-DP-8 deferred a per-run cache-disable seam; this is the zero-runner-change realization.)
- [ ] **AC-8 (`--with-verdict`, gated on completeness, target-tier aware):** add an optional `--target-tier` to `run` (default = the task class's current tier from `TierConfig.current_tiers`, else the lowest declared tier). When `--with-verdict` is set **and** `report.complete is True`: build `gate = PromotionGate(load_tier_config(Path("docs/trust-tiers.yaml")))`, call `verdict = gate.evaluate(report, target_tier)`, then `write_recommendation(verdict, Path(".codegenie/eval/recommendations"))` (S4-05 — directory arg, filename derived inside). When `--with-verdict` is absent, no verdict and no recommendation file. When set but `report.complete is False`, the verdict is skipped (no `evaluate` call — it would raise `IncompleteReportForPromotion`) and the run still exits 2.
- [ ] **AC-9 (`plan()`-raised exits, end-to-end through the CLI):** invoked via `CliRunner`, these surface as the S4-01 exit codes mapped by `main()`: unknown task class / unregistered SUT → 3; missing `bench/<name>/` directory → 4; tampered audit chain at `out` → 5 (`plan()` raises `ChainTamperDetected`); poisoned case (digest mismatch) → 6 (`plan()` raises `BenchCaseDigestMismatch`); complete run → 0. Each is a concrete fixture (reuse S2-02's digest-mismatch builder and S2-04's chain-tamper builder); no path asserts on a `verify` *return value* (the run path never calls `verify`).
- [ ] **AC-10 (stdout JSONL shape, typed):** each per-case line is `{"kind":"case","case_id":str,"score":float∈[0,1],"passed":bool,"breakdown":{...},"failure_modes":[...],"cost_usd":float,"wall_clock_s":float}`; the aggregate line is `{"kind":"aggregate", …BenchRunReport fields…}` and the test asserts `isinstance(agg["lower_bound_95"], float)`, `isinstance(agg["score_stddev"], float)`, `isinstance(agg["mean_score"], float)`, `agg["isolation_class"] == "subprocess"`, `agg["complete"] is True` (happy path), `agg["chain_head"]` truthy, and the on-disk record's `chain_head` **equals** `agg["chain_head"]`. (ADR-0002: all three statistics emitted; ADR-0010: `isolation_class` annotated.)
- [ ] **AC-11 (`--format=human` emits no JSON):** prints one table row per case (`case-id`, `score`, `pass/fail`) and a footer with `mean / stddev / lower_bound_95` formatted to fixed precision; same exit-code semantics. A test asserts **every** stdout line fails `json.loads` (no JSONL leaks) AND row count == case count AND the three statistic values appear. `--format` is read from `ctx.obj["format"]` (S4-01 AC-4 propagation).
- [ ] **AC-12 (extension by addition — observable):** registering a new task class's SUT (`@register_sut("some-new-class")` in that bench's module) makes `codegenie eval run --task-class=some-new-class` resolvable with **zero edits to `src/codegenie/eval/cli.py`**. A test registers a second stub SUT into a fresh `SutRegistry` and drives a run through the CLI seam without touching `cli.py`. (Open/Closed at the file boundary — the rule-of-three is well past with three existing sibling registries.)
- [ ] **AC-13 (deferred imports stay deferred):** after `import codegenie.eval.cli`, none of `pydantic`, `yaml`, `runner`, `audit`, `promotion`, `sut_registry`, or any `bench.` module is in `sys.modules`; the `run` body imports them lazily. S4-01's cold-start test (`tests/unit/eval/test_cli_scaffold.py`) stays green (< 660 ms).
- [ ] **AC-14 (`--out=<path>`):** optional override (`click.Path`), default `Path(".codegenie/eval/runs")`; passed to **both** `plan(out_dir=out)` (chain verify) and `run_eval(out_dir=out)` (chain append). A test points `--out` at a tmp dir and asserts the record lands there, not in the default.
- [ ] **AC-15:** the red tests from §TDD plan exist under `tests/unit/eval/` + `tests/integration/eval/`, were committed at the red marker, and are now green.
- [ ] **AC-16:** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/integration/eval/test_cli_run.py tests/unit/eval/test_cli_run_flags.py` all pass on touched files.

## Implementation outline

1. Write red tests in `tests/unit/eval/test_cli_run_flags.py` (flag parsing + glob filter + SUT seam) and `tests/integration/eval/test_cli_run.py` (end-to-end stub bench) — see §TDD plan.
2. Land the SUT-resolver seam `src/codegenie/eval/sut_registry.py` (AC-3): `SystemUnderTest` type alias / Protocol (`Callable[[BenchCase], Awaitable[Mapping[str, Any]]]` per arch §runner.py line 581), a `SutEntry` carrying `(sut, sut_digest_fn)`, `SutRegistry` with origin-tracking collision (mirror `transforms/signal_kinds.py` / `plugins/registry.py`), `default_sut_registry: Final[SutRegistry]`, `@register_sut(name, *, registry=None)`, `resolve_sut(name, *, registry=None) -> SutEntry` raising a typed not-found error mapped to exit 3.
3. Fill in the `run` subcommand stub from S4-01 (`@eval_group.command(name="run")`):
   - Click options: `--task-class` (required), `--cases` (default `None`), `--concurrency` (`click.IntRange(min=1)`, default `None`), `--max-cost-usd` (`float`, default 5.0), `--no-cache` (flag), `--out` (`click.Path`, default `Path(".codegenie/eval/runs")`), `--with-verdict` (flag), `--target-tier` (default `None`), `--bench-root` (`Path`, default `Path("bench")`).
   - Body (all heavy imports inside the function — AC-13):
     1. `from codegenie.eval.sut_registry import resolve_sut` → `entry = resolve_sut(task_class)` (typed not-found → exit 3 via `main()`).
     2. `from codegenie.eval.runner import Runner`; `from codegenie.eval.rubric import build_rubric_runner` (S3-03) → `rr = build_rubric_runner(task_class, bench_root)`.
     3. Choose `cache_dir`: `Path(tempfile.mkdtemp(prefix="codegenie-eval-nocache-"))` if `--no-cache` else `Path(".codegenie/eval/cache")` (AC-7).
     4. `plan = Runner().plan(task_class, sut_digest_fn=entry.sut_digest_fn, bench_root=bench_root, out_dir=out, run_started_iso=_utc_now_iso(), cassette_root=…, harness_version=…)` — `plan()` loads + chain-verifies; raises `ChainTamperDetected`(→5)/`BenchCaseDigestMismatch`(→6)/`TaskClassNotFound`(→3)/bench-dir-missing(→4), all mapped by `main()`.
     5. If `--cases`: `filtered = tuple(c for c in plan.cases if fnmatch.fnmatch(c.case_id, cases))`; if not `filtered` → `click.echo(...avail ids...); sys.exit(EXIT_GENERIC_ERROR)`; else `plan = dataclasses.replace(plan, cases=filtered, cache_keys={c.case_id: plan.cache_keys[c.case_id] for c in filtered})`.
     6. `report = asyncio.run(Runner().run_eval(plan, system_under_test=entry.sut, rubric_runner=rr, cache_dir=cache_dir, timeout_per_case_seconds=…, concurrency=concurrency, max_cost_usd=max_cost_usd, out_dir=out))` — returns a report with `chain_head` already stamped; appends one record under `out`.
     7. Emit per `ctx.obj["format"]` via the `_EMITTERS` dispatch map (AC-10/AC-11).
     8. If `--with-verdict` and `report.complete is True`: build `PromotionGate(load_tier_config(Path("docs/trust-tiers.yaml")))`, resolve `target_tier` (flag, else `current_tiers[task_class]`), `verdict = gate.evaluate(report, target_tier)`, `write_recommendation(verdict, Path(".codegenie/eval/recommendations"))`.
     9. `sys.exit(EXIT_COST_CAP if report.complete is False else EXIT_SUCCESS)`.
4. JSONL/human emitters: two small private helpers `_emit_jsonl(report, stream)` / `_emit_human(report, stream)` dispatched by a module-level `_EMITTERS: Final[Mapping[str, Callable[[BenchRunReport, TextIO], None]]]` (Strategy-via-dict; adding `--format=csv` later is a one-row edit — F-DP-2). `model_dump_json()` is called lazily inside the helpers, never at module top.
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Reuse S3-01's `tests/helpers/bench.py:stub_task_class_fixture` + S3-02's stub SUT, S2-02's digest-mismatch builder, and S2-04's chain-tamper builder. The integration fixtures register the stub SUT through the `sut_registry` seam (AC-3) so the CLI's `resolve_sut(...)` returns it — this is what makes an end-to-end run possible from a bare task-class *name*.

```python
# tests/unit/eval/test_cli_run_flags.py
from click.testing import CliRunner
from codegenie.eval.cli import eval_group


def test_run_requires_task_class():
    result = CliRunner().invoke(eval_group, ["run"])
    assert result.exit_code != 0
    assert "--task-class" in result.output.lower()


def test_run_concurrency_zero_is_usage_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=x", "--concurrency=0"]
    )
    assert result.exit_code != 0  # click.IntRange(min=1) usage error, body not entered


def test_run_unknown_task_class_exits_three(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bench").mkdir()
    result = CliRunner().invoke(eval_group, ["run", "--task-class=does-not-exist"])
    assert result.exit_code == 3  # resolve_sut / plan() not-found, mapped by main()


def test_run_missing_bench_dir_exits_four(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no bench/ at all
    result = CliRunner().invoke(eval_group, ["run", "--task-class=anything"])
    assert result.exit_code == 4  # EXIT_BENCH_DIR_MISSING


def test_resolve_sut_seam_is_registry_isolated():
    """AC-3 — the SUT resolver is a DI-isolated registry, not a global edit."""
    from codegenie.eval.sut_registry import SutRegistry, register_sut, resolve_sut

    reg = SutRegistry()

    @register_sut("seam-stub", registry=reg)
    class _StubSut:  # entry carries (sut, sut_digest_fn)
        ...

    entry = resolve_sut("seam-stub", registry=reg)
    assert entry is not None
    assert callable(entry.sut_digest_fn)


def test_run_cases_glob_no_match_exits_one(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--cases=999-nothing-*", "--no-cache"],
    )
    assert result.exit_code == 1
    assert "999-nothing" in result.output  # names the glob
```

```python
# tests/integration/eval/test_cli_run.py
import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from codegenie.eval import audit
from codegenie.eval.cli import eval_group

# `stub_bench_with_sut` (conftest): scaffolds the S3-02 stub bench (N cases) AND
# registers its stub SUT + sut_digest_fn into the sut_registry under
# "stub-task-class". Returns the bench root. `N_STUB_CASES` is its case count.


def test_run_stub_bench_exits_zero_emits_jsonl_and_appends_chain(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    lines = [json.loads(ln) for ln in result.output.splitlines() if ln.strip().startswith("{")]
    cases = [o for o in lines if o["kind"] == "case"]
    aggs = [o for o in lines if o["kind"] == "aggregate"]
    assert len(cases) == N_STUB_CASES
    assert len(aggs) == 1
    assert len(lines) == N_STUB_CASES + 1

    agg = aggs[0]
    # ADR-0002 — all three stats emitted, typed as floats.
    assert isinstance(agg["mean_score"], float)
    assert isinstance(agg["score_stddev"], float)
    assert isinstance(agg["lower_bound_95"], float)
    # ADR-0010 — isolation_class annotated; Gap #4 — complete on a clean run.
    assert agg["isolation_class"] == "subprocess"
    assert agg["complete"] is True
    assert agg["chain_head"]
    for c in cases:
        assert isinstance(c["score"], float) and 0.0 <= c["score"] <= 1.0

    out = Path(".codegenie/eval/runs")
    persisted = list(out.glob("*.json"))
    assert len(persisted) == 1  # filename owned by write_run_record (S2-04); we glob
    on_disk = json.loads(persisted[0].read_text())
    assert on_disk["chain_head"] == agg["chain_head"]   # single source of truth
    assert audit.verify(out).ok is True                  # appended record is chain-valid


def test_run_no_cache_leaves_canonical_cache_untouched(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    canonical = Path(".codegenie/eval/cache")
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # AC-7 — ephemeral cache_dir: canonical cache gained nothing.
    assert not canonical.exists() or list(canonical.glob("*.json")) == []


def test_run_cases_glob_runs_only_matching_subset(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--cases=001-*", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    cases = [json.loads(ln) for ln in result.output.splitlines()
             if ln.strip().startswith("{") and json.loads(ln)["kind"] == "case"]
    assert {c["case_id"] for c in cases} == {c for c in _ALL_STUB_IDS if c.startswith("001-")}


def test_run_cost_cap_breach_exits_two_and_writes_partial(stub_expensive_bench_with_sut, monkeypatch):
    # Stub SUT records cost > $0.01 per case; cap below that fires S3-06's partial path.
    monkeypatch.chdir(stub_expensive_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group,
        ["run", "--task-class=stub-expensive", "--max-cost-usd=0.005", "--no-cache"],
        catch_exceptions=False,   # a CancelledError leaking would crash here, not exit 2
    )
    assert result.exit_code == 2  # EXIT_COST_CAP via report.complete is False

    persisted = list(Path(".codegenie/eval/runs").glob("*.json"))
    assert len(persisted) == 1
    on_disk = json.loads(persisted[0].read_text())
    assert on_disk["complete"] is False
    assert on_disk["run_id"].startswith("partial:")
    # S3-06 AC-7 — _Aborted placeholders fill the tuple.
    assert len(on_disk["per_case"]) == len(_EXPENSIVE_STUB_IDS)


def test_run_with_verdict_writes_recommendation(stub_bench_with_sut, monkeypatch, trust_tiers_yaml):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--no-cache", "--with-verdict"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    recs = list(Path(".codegenie/eval/recommendations").glob("*.json"))
    assert len(recs) == 1


def test_run_without_verdict_writes_no_recommendation(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert not Path(".codegenie/eval/recommendations").exists()


def test_run_chain_tamper_exits_five(stub_bench_with_sut, monkeypatch, tampered_chain):
    # tampered_chain seeds a corrupted record under .codegenie/eval/runs before the run.
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=stub-task-class", "--no-cache"],
    )
    assert result.exit_code == 5  # plan() raises ChainTamperDetected -> main() maps to 5


def test_run_poisoned_case_exits_six(stub_bench_poisoned, monkeypatch):
    # stub_bench_poisoned byte-flips a case so its digest mismatches digests.yaml.
    monkeypatch.chdir(stub_bench_poisoned.parent)
    result = CliRunner().invoke(
        eval_group, ["run", "--task-class=stub-task-class", "--no-cache"],
    )
    assert result.exit_code == 6  # plan() raises BenchCaseDigestMismatch


def test_run_human_format_emits_no_json(stub_bench_with_sut, monkeypatch):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    result = CliRunner().invoke(
        eval_group,
        ["--format=human", "run", "--task-class=stub-task-class", "--no-cache"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    rows = [ln for ln in result.output.splitlines() if ln.strip()]
    for ln in rows:
        with pytest.raises(json.JSONDecodeError):
            json.loads(ln)  # AC-11 — no JSONL leaks in human mode
    for tok in ("mean", "stddev", "lower_bound_95"):
        assert tok in result.output.lower()


def test_run_out_flag_redirects_audit(stub_bench_with_sut, monkeypatch, tmp_path):
    monkeypatch.chdir(stub_bench_with_sut.parent)
    custom = tmp_path / "custom-runs"
    result = CliRunner().invoke(
        eval_group,
        ["run", "--task-class=stub-task-class", "--no-cache", f"--out={custom}"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(list(custom.glob("*.json"))) == 1
    assert not Path(".codegenie/eval/runs").exists()
```

Run; confirm failures (`ImportError` on `sut_registry`, `AttributeError` on the `run` stub). Commit as the red marker.

### Green — make it pass

Implement `src/codegenie/eval/sut_registry.py` then the `run` body per §Implementation outline. The flow is `resolve_sut` → `build_rubric_runner` → `Runner().plan(...)` → optional glob `dataclasses.replace` → `asyncio.run(Runner().run_eval(...))` → emit → optional verdict → `sys.exit`. JSONL emission uses `report.model_dump_json()` (Pydantic v2, called lazily inside `_emit_jsonl`). Human format: a hand-rolled table in `_emit_human`.

### Refactor — clean up

- `_emit_jsonl` / `_emit_human` are private; dispatched by a module-level `_EMITTERS: Final[Mapping[str, Callable[[BenchRunReport, TextIO], None]]]` keyed on `ctx.obj["format"]` (Strategy-via-dict — adding `--format=csv` is a one-row edit). Both take the stream as a param (`TextIO`) for testability; do not monkeypatch `click.echo`.
- The `--cases` glob uses stdlib `fnmatch.fnmatch`; no regex.
- `structlog.info` at run-start with `task_class`, `cases_count`, `concurrency`, `max_cost_usd` (lazy logger inside the body).
- Cost-cap is **non-exceptional**: `run_eval` returns `complete=False`; the CLI inspects `report.complete` and exits 2. Do not add a `CostCapExceeded` catch — if you reach for one, re-read S3-06.
- `chain_head` is **not** the CLI's to set: `run_eval` returns the report with it stamped (S3-06 AC-2). The CLI emits the returned object verbatim; the on-disk record matches because S2-04 AC-3a pins it. There is no `model_copy` in the CLI.
- The audit filename (`<utc_iso>-<token>.json`) is owned by `write_run_record` (S2-04); the CLI never builds it — it globs `out` to confirm the single append.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/sut_registry.py` | **New file** — `SutRegistry`, `SutEntry(sut, sut_digest_fn)`, `@register_sut`, `resolve_sut`, `default_sut_registry: Final`. The `name → SystemUnderTest` seam (AC-3). Mirrors `transforms/signal_kinds.py` / `plugins/registry.py` kernel discipline. |
| `src/codegenie/eval/cli.py` | Fill in the `run` subcommand body (corrected `plan`→`run_eval` flow); add `_emit_jsonl`/`_emit_human` + the `_EMITTERS` dispatch map. |
| `tests/unit/eval/test_cli_run_flags.py` | New file — flag parsing/validation, `--cases` glob, SUT-seam isolation, exit-3/4 paths. |
| `tests/integration/eval/test_cli_run.py` | New file — end-to-end against the stub bench (registers the stub SUT through the seam); JSONL shape, `--no-cache`, cost-cap partial, `--with-verdict`, tamper→5, poison→6, human-no-JSON, `--out`. |
| `tests/unit/eval/conftest.py` | Extend with `stub_bench_with_sut` / `stub_expensive_bench_with_sut` / `stub_bench_poisoned` / `tampered_chain` / `trust_tiers_yaml` fixtures that build on S3-01's `stub_task_class_fixture` and register the stub SUT into a fresh `SutRegistry`. Do not redefine S2-01's autouse isolation fixture. |

## Out of scope

- **`PromotionGate` internals** — S4-04 owns `evaluate(report, target_tier, *, evidence_window=())` and the all-conditions check. This story calls it (when `--with-verdict` AND `report.complete is True`) and assumes a `PromotionVerdict`.
- **Recommendation file format and writer** — S4-05 owns `.codegenie/eval/recommendations/<utc-iso>.json` shape and `write_recommendation(verdict, out_dir)`. This story calls it.
- **`verify` and `promote-verdict` subcommands** — S4-03 (`verify` — the only place `audit.verify`'s `VerifyResult` is surfaced to operators) and downstream stories.
- **Real SUTs** — `VulnRemediationSut` (Phase 6, registered for `vuln-remediation` by S5) and the distroless SUT (S6) are registered into `sut_registry` *by addition*. This story registers only a stub SUT for the stub bench. The arch's `name → VulnRemediationSut` binding (§Scenario 1) is realized by the resolver seam; the concrete real SUTs are not built here.
- **Real benches (`bench/vuln-remediation/`, `bench/migration-chainguard-distroless/`)** — S5-* and S6-* land them. This story tests against the S3-02 stub fixture only.
- **Reviving the deferred `CachePort` / per-run cache-disable injection** — S3-02 F-DP-8 deferred it; `--no-cache` here uses an ephemeral `cache_dir` instead. A true read-bypass-but-still-persist mode is a separate story if a consumer ever needs it.
- **Cache hit-rate testing** — S5-06 owns the integration tests for warm-run cache behavior.
- **Cross-host / cross-process run lock** — S3-06 F-CON-5 deferred `fcntl.flock` on a run lock; single-process is the Phase 6.5 cadence.
- **`scaffold_bench_case.py`** — S5-07.

## Notes for the implementer

- **The runner contract changed after this story was first written — follow the hardened APIs, not the original prose.** `Runner()` is stateless. `Runner().plan(name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version)` loads the task class + cases and verifies the chain *internally*, raising `ChainTamperDetected` / `BenchCaseDigestMismatch` / `TaskClassNotFound` before any SUT call. `Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, max_cost_usd=5.0, out_dir)` is the audit-writing composition root. Do **not** call `load_task_class`/`load_cases`/`audit.verify` directly on this path — `plan()` owns them.
- **Single source of truth for `chain_head` — the CLI does NOT set it.** `run_eval` returns the report with `chain_head` already stamped (S3-06 AC-2 `model_copy`). Emit the returned object verbatim. The on-disk record and the stdout aggregate match because S2-04 AC-3a pins the persisted `chain_head` to equal the returned head. There is no `model_copy` and no `head` variable in the CLI body.
- **You never build the audit filename.** `write_run_record` (called inside `run_eval`) owns `f"{utc_iso}-{secrets.token_hex(4)}.json"` (S2-04). The CLI does not see the path — it globs `out` to confirm exactly one record was appended, and reads it back to assert `chain_head` equality.
- **The SUT comes from `sut_registry`, the rubric from the task class.** The CLI holds only a name; `resolve_sut(name)` returns the `(sut, sut_digest_fn)` entry, and `build_rubric_runner(task_class, bench_root)` (S3-03) builds the subprocess rubric from `task_class.rubric_class`. Register new SUTs by addition (`@register_sut`) — never branch on task-class name in `cli.py` (AC-12). **Record the resolver decision in a one-paragraph ADR** (`phase-architect`); S5-05/S6-03/Phase-9 consume it.
- **`--cases` glob filters `plan.cases`, preserving the S3-01 AC-1a invariant.** Use `dataclasses.replace(plan, cases=filtered, cache_keys={c.case_id: plan.cache_keys[c.case_id] for c in filtered})` so `__post_init__` re-validates `set(cache_keys) == {c.case_id}`. A non-matching glob is exit 1 (operator error); a zero-case bench is a legitimate exit-0 (S2-02 AC-11 / S3-01 AC-12) — don't collapse them.
- **`--no-cache` → ephemeral `cache_dir`.** Point `cache_dir` at `tempfile.mkdtemp(...)` for the run; the canonical cache is never touched (S3-02 deferred a true read-bypass seam — F-DP-8). Do not claim writes persist to the canonical cache.
- **`--with-verdict` is completeness-gated and target-tier aware.** `PromotionGate.evaluate(report, target_tier)` raises `IncompleteReportForPromotion` on `report.complete is False` — so only call it when `complete is True`. Resolve `target_tier` from the `--target-tier` flag, else `TierConfig.current_tiers[task_class]`.
- **Cost-cap is *non-exceptional*.** `run_eval` returns `complete=False` (+ `partial:` run_id + `_Aborted` placeholders filling `per_case`). The CLI inspects `report.complete` and exits 2. No `CostCapExceeded` catch (S3-06).
- **`asyncio.run(Runner().run_eval(...))`** exactly once per invocation; the runner owns its own loop + semaphore internally — do not nest.
- **Stdout newline discipline:** one JSON object per line via `click.echo` (appends `\n`); no `print(..., flush=True)`. Operators pipe into `jq`.
- **Heavy-import audit:** all of `runner`/`audit`/`promotion`/`pydantic`/`sut_registry`/`bench.*` import *inside* the `run` body. Re-run S4-01's cold-start test (< 660 ms) after this story.
