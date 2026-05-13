# Story S4-01 — CLI scaffold + partitioned exit codes

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** Ready
**Effort:** S
**Depends on:** S3-04 (six per-case failure paths), S3-05 (BCa bootstrap), S3-06 (cost-cap path)
**ADRs honored:** ADR-0001 (subprocess-isolation failure typing → CLI exit codes), ADR-0004 (failure-mode taxonomy surfaces via exit codes), Phase 5 ADR-0016 (eval-harness-as-trust-evidence), Phase 0 import-linter contract (deferred heavy imports for cold-start)

## Context

`cli.py` is the user-visible boundary of the eval harness. Before any subcommand exists, the surrounding plumbing must land: the Click subcommand group `codegenie eval`, deferred heavy imports so `codegenie eval --help` is fast, the `--format=human|jsonl` option (default `jsonl` per `phase-arch-design.md §Component design → cli.py`), and the partitioned exit-code table mapping `CodegenieEvalError` subclasses to codes 1–6. This story produces the scaffold and exit-code contract; S4-02/S4-03 fill in the `run` and `verify` subcommands against it.

The cold-start budget (≤ 600 ms) mirrors Phase 0's `codegenie gather` and is non-negotiable: Click resolution + `--help` rendering cannot pay for `pydantic.BaseModel` recursion, `bench.{name}.rubric` chain imports, or `pyyaml`. Heavy imports are deferred inside command bodies. The exit-code table is the load-bearing contract Phase 11 consumers (PR provenance) will branch on — partitioning is structural, not advisory.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` — usage, exit codes 0/1/2/3/4/5/6, `--format=human|jsonl` default `jsonl`, deferred-import discipline.
  - `../phase-arch-design.md §Container view` — `cli.py` is the surface; `runner.py`, `promotion.py`, `audit.py` are deferred imports.
  - `../phase-arch-design.md §Performance budgets` — cold-start ≤ 600 ms (mirrors `codegenie gather`).
  - `../phase-arch-design.md §Failure modes table` — rows 1, 2, 5, 6 map to exit codes 6, 6, 5, 6 respectively; cost-cap (row from §Happy path step 5) maps to 2; task-class-not-registered (`TaskClassNotFound`) to 3; bench-dir-missing to 4.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — rubric per-case failures are `FailureMode` not exceptions; the CLI does not exit 1 on a per-case rubric failure. The run still exits 0 (or 2 on cost-cap); the `BenchRunReport` carries the block-severity codes.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — same: per-case failures are data on the report, not CLI exit categories.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — autonomy ends at the CLI boundary; exit-code semantics are operator-facing.
- **Source design:** `../High-level-impl.md §Step 4` — names the seven exit codes verbatim and the deferred-import discipline.
- **Phase 0 precedent:** `../../00-bullet-tracer-foundations/` CLI scaffold for `codegenie gather` — same Click group pattern, same cold-start budget; mirror it.

## Goal

Land `src/codegenie/eval/cli.py` with the `codegenie eval` Click subcommand group, deferred heavy imports, the seven-code exit-code partition (0/1/2/3/4/5/6), and a `--format=human|jsonl` global option (default `jsonl`) — all measured to start in ≤ 600 ms cold.

## Acceptance criteria

- [ ] `src/codegenie/eval/cli.py` defines a Click group `eval` registered against the existing top-level `codegenie` group (Phase 0 entry-point); `codegenie eval --help` lists the three subcommands (`run`, `verify`, `promote-verdict`) as stubs that exist but may raise `NotImplementedError` outside of this story's scope.
- [ ] The seven exit codes are exported as named constants: `EXIT_SUCCESS=0`, `EXIT_GENERIC_ERROR=1`, `EXIT_COST_CAP=2`, `EXIT_TASK_CLASS_NOT_REGISTERED=3`, `EXIT_BENCH_DIR_MISSING=4`, `EXIT_CHAIN_TAMPER=5`, `EXIT_DIGEST_MISMATCH=6` (constants live in `cli.py` and are referenced by the top-level exception handler).
- [ ] A top-level `@eval.result_callback` or wrapped `main()` handler catches: `TaskClassNotFound` → 3; `BenchCaseLoadError` with reason `"bench dir missing"` → 4; `BenchCaseDigestMismatch` → 6; `ChainTamperDetected` → 5; cost-cap signal (a sentinel exception `CostCapExceeded` from S3-06 or a `BenchRunReport.complete=False` with `run_id.startswith("partial:")`) → 2; uncaught `CodegenieEvalError` and uncaught `Exception` → 1.
- [ ] `--format=human|jsonl` is a group-level option with default `jsonl`; the option value is propagated to subcommands via Click context.
- [ ] **Cold-start performance:** `python -c "import time; t=time.perf_counter(); import codegenie.eval.cli; print((time.perf_counter()-t)*1000)"` reports ≤ 600 ms on the CI runner (test asserts < 600 ms with a 10% slack budget). `pydantic`, `pyyaml`, `bench.*` modules MUST NOT appear in `sys.modules` after pure `cli` import; they are deferred inside subcommand bodies.
- [ ] **Negative cold-start guard test:** assert that after importing `codegenie.eval.cli`, the strings `pydantic`, `yaml`, and any key beginning with `bench.` are absent from `sys.modules`.
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_cli_scaffold.py tests/unit/test_cli_exit_codes.py` all pass on touched files.

## Implementation outline

1. Write the red tests first in `tests/unit/test_cli_scaffold.py` and `tests/unit/test_cli_exit_codes.py` — see §TDD plan. Confirm they fail with `ModuleNotFoundError` / attribute errors.
2. Create `src/codegenie/eval/cli.py`:
   - Import only stdlib + `click` at module top.
   - Declare the seven `EXIT_*` integer constants.
   - Define `@click.group(name="eval")` with `--format=human|jsonl` (default `jsonl`) as a group-level option attached to `click.Context.obj`.
   - Define three subcommand stubs (`run`, `verify`, `promote-verdict`) registered on the group; each body raises `NotImplementedError` (S4-02/S4-03/S4-04 will fill these in). They exist so `codegenie eval --help` lists them and the structural tests pass.
   - Define a `main()` (or a wrapping `run_cli()`) that invokes the group inside a `try/except` mapping each `CodegenieEvalError` subclass and the cost-cap signal to the corresponding `EXIT_*` constant, then `sys.exit(code)`.
   - Defer imports of `codegenie.eval.runner`, `codegenie.eval.promotion`, `codegenie.eval.audit`, `pydantic`, `pyyaml` inside subcommand bodies.
3. Wire the Click group into the top-level `codegenie` entry-point (Phase 0 adds it via `pyproject.toml`/`__main__.py`); this story may need a one-line registration edit in the existing top-level CLI module — keep it surgical (Rule 3).
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/cli.py`, `pytest tests/unit/test_cli_scaffold.py tests/unit/test_cli_exit_codes.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_cli_scaffold.py` and `tests/unit/test_cli_exit_codes.py`.

```python
# tests/unit/test_cli_scaffold.py
import sys
import time
import importlib
from click.testing import CliRunner


def test_cli_group_exists_and_lists_three_subcommands():
    from codegenie.eval.cli import eval as eval_group  # noqa: A001

    runner = CliRunner()
    result = runner.invoke(eval_group, ["--help"])
    assert result.exit_code == 0
    for sub in ("run", "verify", "promote-verdict"):
        assert sub in result.output, f"subcommand {sub!r} missing from --help"


def test_format_option_default_is_jsonl():
    from codegenie.eval.cli import eval as eval_group

    runner = CliRunner()
    # Probe default through --help (option default surfaced)
    result = runner.invoke(eval_group, ["--help"])
    assert "--format" in result.output
    assert "jsonl" in result.output


def test_cold_start_no_heavy_imports():
    # Reset sys.modules of any prior eval imports so the budget is honest.
    for k in list(sys.modules):
        if k.startswith("codegenie.eval") or k.startswith("bench."):
            sys.modules.pop(k, None)
    sys.modules.pop("pydantic", None)
    sys.modules.pop("yaml", None)

    t0 = time.perf_counter()
    importlib.import_module("codegenie.eval.cli")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 600 ms budget, 10% slack — fail loud past 660 ms.
    assert elapsed_ms < 660.0, f"cli import took {elapsed_ms:.1f}ms (> 660ms budget)"

    # Negative guard: heavy modules must NOT be loaded by importing the CLI.
    forbidden_prefixes = ("pydantic", "yaml", "bench.")
    leaked = sorted(
        m for m in sys.modules
        if any(m == p.rstrip(".") or m.startswith(p) for p in forbidden_prefixes)
    )
    assert leaked == [], f"cli import leaked heavy modules: {leaked}"
```

```python
# tests/unit/test_cli_exit_codes.py
import pytest
from codegenie.eval import cli as cli_module
from codegenie.eval import errors as e


EXPECTED = {
    "EXIT_SUCCESS": 0,
    "EXIT_GENERIC_ERROR": 1,
    "EXIT_COST_CAP": 2,
    "EXIT_TASK_CLASS_NOT_REGISTERED": 3,
    "EXIT_BENCH_DIR_MISSING": 4,
    "EXIT_CHAIN_TAMPER": 5,
    "EXIT_DIGEST_MISMATCH": 6,
}


@pytest.mark.parametrize("name,value", list(EXPECTED.items()))
def test_exit_code_constant_present_and_partitioned(name: str, value: int) -> None:
    assert getattr(cli_module, name) == value


def test_exit_codes_are_disjoint_and_total_seven():
    values = {getattr(cli_module, n) for n in EXPECTED}
    assert values == {0, 1, 2, 3, 4, 5, 6}


@pytest.mark.parametrize(
    "exc,expected_code",
    [
        (e.TaskClassNotFound("foo", ("bar",)), 3),
        (e.BenchCaseDigestMismatch("003-x", "abc", "def"), 6),
        (e.ChainTamperDetected("/tmp/x", "0" * 64, "1" * 64), 5),
    ],
)
def test_exception_maps_to_exit_code(exc: Exception, expected_code: int) -> None:
    code = cli_module._map_exception_to_exit_code(exc)  # internal helper, tested at boundary
    assert code == expected_code


def test_uncaught_exception_maps_to_generic_one() -> None:
    code = cli_module._map_exception_to_exit_code(RuntimeError("anything"))
    assert code == 1
```

Run; confirm `ModuleNotFoundError: No module named 'codegenie.eval.cli'` (and missing attributes once the module exists). Commit as the red marker.

### Green — make it pass

Create `src/codegenie/eval/cli.py` with:
- Seven `EXIT_*` integer constants.
- `@click.group(name="eval")` with `@click.option("--format", "fmt", type=click.Choice(["human", "jsonl"]), default="jsonl", show_default=True)`.
- Three `@eval.command()` stubs (`run`, `verify`, `promote-verdict`), each body `raise NotImplementedError("S4-02/S4-03/S4-04")`.
- A `_map_exception_to_exit_code(exc: BaseException) -> int` helper mapping the documented exception classes; default 1.
- A `main()` (or `run_cli()`) calling the group inside `try/except BaseException as exc: sys.exit(_map_exception_to_exit_code(exc))`.

No imports of `pydantic`, `pyyaml`, `bench.*`, `runner`, `promotion`, or `audit` at module top.

### Refactor — clean up

- Annotate every function with full type hints; `mypy --strict` clean.
- Module docstring cites `../phase-arch-design.md §Component design → cli.py` as the source-of-truth for exit-code semantics.
- Use `structlog.get_logger(__name__)` lazily inside `main()`; do not configure logging at import time.
- The exit-code constants get a module-level docstring tying each code to its triggering exception class and a `phase-arch-design.md §Failure modes` row reference; this is the table operators read when they see a non-zero exit.
- Consider extracting `EXIT_*` to a `_exit_codes.py` sibling for downstream consumers; defer unless S4-02 needs it (Rule 2 — simplicity first).
- Add a `# pragma: no cover` only on the `if __name__ == "__main__": main()` line; everything else is covered by the unit tests + S4-02/S4-03 integration tests.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/cli.py` | New file — Click group, three stub subcommands, exit-code constants, exception→code mapper, `main()` entry. |
| `tests/unit/test_cli_scaffold.py` | New file — group exists, subcommands listed, `--format=jsonl` default, cold-start < 660 ms, no heavy imports leaked. |
| `tests/unit/test_cli_exit_codes.py` | New file — seven constants present, disjoint, exception→code mapping is the documented partition. |
| `src/codegenie/__main__.py` or `pyproject.toml` entry-point | If Phase 0's top-level CLI module exists, register the `eval` group surgically (one-line edit). Otherwise note it as a follow-up; this story does not block on Phase 0 entry-point shape. |

## Out of scope

- **Implementing `run`, `verify`, `promote-verdict` bodies** — handled by S4-02 (`run`), S4-03 (`verify`), and S4-04+S4-05 (`promote-verdict` reads PromotionGate output). Stubs raise `NotImplementedError` here.
- **`--cases`, `--concurrency`, `--max-cost-usd`, `--no-cache`, `--out`, `--with-verdict`, `--bench-root` flags** — wired in S4-02 on the `run` subcommand.
- **`--since`, `--strict` flags** — wired in S4-03 on the `verify` subcommand.
- **`PromotionGate` construction and `TierConfig` loading** — wired in S4-04 (gate logic) and S4-05 (recommendation writer).
- **JSONL line writer** — the `--format` option exists structurally here; per-case JSONL emission and human-readable table rendering happen in S4-02.
- **Cost-cap exception class** — S3-06 owns the `CostCapExceeded` (or equivalent) sentinel; this story just maps it to exit 2 when the symbol exists. If S3-06 has not yet landed, gate the mapping on a `try: from codegenie.eval.errors import CostCapExceeded; except ImportError: CostCapExceeded = ...` shim and flag it.

## Notes for the implementer

- **Defer EVERY heavy import.** Even `from codegenie.eval.models import BenchRunReport` triggers `pydantic` and breaks the cold-start budget. Inside subcommand bodies, `import` at function scope; the lint contract from Phase 0 (`import-linter`) will codify this in S1-05 and S7-* — but write it correctly the first time so the test in this story stays green.
- **Click 8+** is the assumption; if the project pins an earlier version, `result_callback` and context patterns differ. Check `pyproject.toml`.
- **`--format` propagation:** store the chosen format in `click.Context.obj` (initialize via `ctx.ensure_object(dict)` at the group level). Subcommands read `ctx.obj["format"]`. This avoids parameter duplication on every subcommand declaration.
- **Cold-start budget is honestly load-bearing.** Phase 0's `codegenie gather` set this number; operators see `codegenie eval --help` ≥ 50× more often than they see a full run. A 1.5 s `--help` is broken UX even though it does no work.
- **`_map_exception_to_exit_code` is intentionally a private helper.** Testing the boundary directly (rather than only via `CliRunner`) means the partition is independently verifiable; CLI integration tests in S4-02/S4-03 cover the full Click invocation path. The name is `_`-prefixed; do not export it.
- **The cost-cap signal shape is unsettled at the time of writing.** S3-06's `BenchRunReport.complete=False` + `run_id.startswith("partial:")` is the data; whether the CLI sees a `CostCapExceeded` exception or a returned `BenchRunReport` is a S4-02 decision. Either way, this story's `_map_exception_to_exit_code` handles the exception form; the report-based path is checked by S4-02 after the runner returns.
- **No `BaseException` catch-alls in the group body** — only `main()` wraps everything. Inside subcommands, let exceptions propagate; `main()` is the single mapping point. This makes the partition tractable to test.
