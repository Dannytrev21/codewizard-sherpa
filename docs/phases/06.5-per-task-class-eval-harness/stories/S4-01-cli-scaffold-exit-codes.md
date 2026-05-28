# Story S4-01 — CLI scaffold + partitioned exit codes

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** HARDENED (phase-story-validator, 2026-05-28)
**Effort:** S
**Depends on:** S1-01 (eval errors module — the nine typed exceptions the mapper keys on), S3-04 (six per-case failure paths), S3-05 (BCa bootstrap), S3-06 (cost-cap path)
**ADRs honored:** ADR-0001 (subprocess-isolation failure typing → CLI exit codes), ADR-0004 (failure-mode taxonomy surfaces via exit codes), Phase 5 ADR-0016 (eval-harness-as-trust-evidence), Phase 0 import-linter contract (deferred heavy imports for cold-start)

## Validation notes (phase-story-validator, 2026-05-28)

This story was hardened in place. Changes and why:

- **F-CON-1 (BLOCK → fixed): test-file collision.** The original "Files to touch" created `tests/unit/test_cli_exit_codes.py` and `tests/unit/test_cli_scaffold.py`. **`tests/unit/test_cli_exit_codes.py` already exists on disk** — it is the gather CLI's (Phase 0/2) exit-code dispatch test (`codegenie.cli` + `codegenie.errors`). The executor would have clobbered it. Phase 6.5 eval unit tests live under **`tests/unit/eval/`** (precedent: `tests/unit/eval/test_runner_plan.py`, `test_audit_read_chain_head.py`, `test_content_hash_tree.py`). All test paths moved to `tests/unit/eval/`.
- **F-CON-2 (harden): registration point corrected.** The top-level Click group is the `cli` object (`name="codegenie"`) in `src/codegenie/cli.py`; sub-groups are added there (e.g. `@cli.group(name="audit")`, `@cli.group(name="vuln-index")`). `src/codegenie/__main__.py` only calls `cli.main(...)` and `pyproject.toml` only names the entry point — neither is where a sub-group registers. "Files to touch" + outline now name `src/codegenie/cli.py`.
- **F-CON-3 / F-DP-3 (harden): builtin shadowing.** The exported Click group was named `eval`, which shadows the `eval()` builtin (forcing `# noqa: A001` at every import). The top-level precedent names its variable `cli` with `name="codegenie"` — variable name ≠ CLI surface name, no shadow. The exported symbol is now **`eval_group`** with `@click.group(name="eval")`; the CLI surface (`codegenie eval`) is unchanged. AC-1 + tests updated.
- **F-DP-1 (harden): table-driven mapper, not an if/elif ladder.** `_map_exception_to_exit_code` is now specified as a **module-level `Final` ordered table** of `(matcher, code)` rows (mirrors the codebase's `_LOCKFILE_PRECEDENCE` / `_GENERATOR_HEADER_MARKERS` Final-tuple idiom and the registry/Open-Closed discipline in CLAUDE.md). With six non-generic mappings this is well past the rule-of-three threshold. New AC-9 makes table-drivenness observable (no per-class `if/elif`; the table is the single source).
- **F-COV-1 / F-COV-2 (harden): missing partitions + reason-discrimination.** The exit-code test only exercised codes 3/5/6. Added the **bench-dir-missing → 4** case AND a *negative* `BenchCaseLoadError(reason != "bench dir missing") → 1` case (proves the mapper discriminates on reason, not type — guards a "map all `BenchCaseLoadError` → 4" mutation), plus the **cost-cap → 2** case (skipped if `CostCapExceeded` is not yet importable, so the test never silently passes nor clobbers S3-06's symbol).
- **F-TQ-1 / F-TQ-4 (harden): `--format` default tested by behavior, not help-text substring.** The old test asserted the strings `--format` and `jsonl` appear in `--help` — a `default="human"` mutation survives (the Choice list `[human|jsonl]` still contains `"jsonl"`). Replaced with a behavioral test: a probe subcommand echoes `ctx.obj["format"]`; invoked without `--format` it must print `jsonl`, and `--format human` must print `human`. This tests the default AND context propagation (AC-4) together.
- **F-TQ-2 (harden): exact command set.** Subcommand listing now asserts `set(eval_group.commands) == {"run", "verify", "promote-verdict"}` (structural) rather than substring presence of `"run"`/`"verify"` in help text (`"run"` matches `"running"`).
- **F-DP-2 (nit): `EXIT_*` annotated `Final[int]`.**

The original cold-start budget, deferred-import discipline, and exit-code partition were already sound and are unchanged.

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

- [ ] AC-1: `src/codegenie/eval/cli.py` defines a Click group exported as the Python symbol **`eval_group`** (`@click.group(name="eval")` — the CLI surface is `codegenie eval`; the symbol does **not** shadow the `eval()` builtin, mirroring the top-level `cli`/`name="codegenie"` precedent). `codegenie eval --help` lists exactly the three subcommands (`run`, `verify`, `promote-verdict`) as stubs that exist but raise `NotImplementedError` in their bodies (out of scope here). A test asserts `set(eval_group.commands) == {"run", "verify", "promote-verdict"}` — the exact set, not substring presence.
- [ ] AC-2: The seven exit codes are exported as `Final[int]` named constants: `EXIT_SUCCESS=0`, `EXIT_GENERIC_ERROR=1`, `EXIT_COST_CAP=2`, `EXIT_TASK_CLASS_NOT_REGISTERED=3`, `EXIT_BENCH_DIR_MISSING=4`, `EXIT_CHAIN_TAMPER=5`, `EXIT_DIGEST_MISMATCH=6` (constants live in `cli.py` and are the only values the mapper may return). A test asserts the seven values are disjoint and equal `{0,1,2,3,4,5,6}`.
- [ ] AC-3: A wrapped `main()` handler maps each failure to an `EXIT_*` constant via `_map_exception_to_exit_code`: `TaskClassNotFound` → 3; `BenchCaseLoadError` **whose `reason` equals the bench-dir-missing sentinel** → 4; `BenchCaseDigestMismatch` → 6; `ChainTamperDetected` (the **`codegenie.eval.errors`** class, not the unrelated `codegenie.plugins.events.ChainTamperDetected`) → 5; the cost-cap signal (`CostCapExceeded` from S3-06, when importable) → 2; any other `CodegenieEvalError` and any other `Exception` → 1.
- [ ] AC-4: `--format=human|jsonl` is a group-level option with default `jsonl`, stored in `click.Context.obj` (`ctx.ensure_object(dict)`); subcommands read `ctx.obj["format"]`. A **behavioral** test (a probe subcommand echoing `ctx.obj["format"]`) asserts that omitting `--format` yields `jsonl` and `--format human` yields `human` — proving both the default and the propagation, not merely that the word appears in `--help`.
- [ ] AC-5: **Bench-dir-missing discrimination is reason-based, not type-based.** A `BenchCaseLoadError` carrying the bench-dir-missing sentinel reason maps to 4; a `BenchCaseLoadError` carrying any *other* reason maps to 1. The sentinel string is a module-level `Final` constant in `cli.py` (e.g. `_BENCH_DIR_MISSING_REASON`) so the coupling to the loader's reason text is a single named point, not a magic string scattered across branches. (Guards a "map all `BenchCaseLoadError` → 4" mutation.)
- [ ] AC-6: **Cost-cap mapping is shim-safe.** If `CostCapExceeded` is not yet importable from `codegenie.eval.errors` (S3-06 not landed), the cost-cap table row is omitted and the corresponding test is `pytest.mark.skipif`-guarded — the suite never silently passes a missing mapping nor redefines S3-06's symbol.
- [ ] AC-7: **Cold-start performance:** `python -c "import time; t=time.perf_counter(); import codegenie.eval.cli; print((time.perf_counter()-t)*1000)"` reports ≤ 600 ms on the CI runner (test asserts < 660 ms — 10% slack). The light import of `eval_group` into `src/codegenie/cli.py` for registration MUST NOT regress the gather CLI's cold-start (no transitive heavy imports through `eval.cli`).
- [ ] AC-8: **Negative cold-start guard test:** after `import codegenie.eval.cli`, no `sys.modules` key equals `pydantic` or `yaml`, and none begins with `bench.` — they are deferred inside subcommand bodies.
- [ ] AC-9: **The exception→code mapping is data-driven.** `_map_exception_to_exit_code` derives its result by iterating a module-level `Final` ordered table (`_EXIT_CODE_TABLE: tuple[tuple[Callable[[BaseException], bool], int], ...]` of `(matcher, code)` rows), not a per-class `if/elif` ladder; the default (no row matches) is `EXIT_GENERIC_ERROR`. A test asserts the table's codes cover `{2,3,4,5,6}` so adding a new error→code is a one-row append (Open/Closed; CLAUDE.md "extension by addition"). The helper is `_`-prefixed and never exported.
- [ ] AC-10: The red tests from §TDD plan exist under `tests/unit/eval/`, were committed at the red marker, and are now green.
- [ ] AC-11: `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/eval/test_cli_scaffold.py tests/unit/eval/test_cli_exit_codes.py` all pass on touched files.

## Implementation outline

1. Write the red tests first in `tests/unit/eval/test_cli_scaffold.py` and `tests/unit/eval/test_cli_exit_codes.py` — see §TDD plan. Confirm they fail with `ModuleNotFoundError` / attribute errors. (Do **not** touch the pre-existing `tests/unit/test_cli_exit_codes.py` — that is the gather CLI's test.)
2. Create `src/codegenie/eval/cli.py`:
   - Import only stdlib + `click` at module top.
   - Declare the seven `EXIT_*` constants as `Final[int]`.
   - Declare the bench-dir-missing sentinel `_BENCH_DIR_MISSING_REASON: Final[str]` (single coupling point to the loader's reason text).
   - Build the `_EXIT_CODE_TABLE: Final[tuple[tuple[Callable[[BaseException], bool], int], ...]]` of `(matcher, code)` rows — one row per non-generic code (3/4/5/6, plus 2 when `CostCapExceeded` is importable). Order matters: the `BenchCaseLoadError` reason-match row precedes any broader `CodegenieEvalError` row. `_map_exception_to_exit_code` iterates the table and returns the first match, defaulting to `EXIT_GENERIC_ERROR`.
   - Define `@click.group(name="eval")` assigned to the symbol `eval_group`, with `--format=human|jsonl` (default `jsonl`) as a group-level option; the group callback runs `ctx.ensure_object(dict)` then `ctx.obj["format"] = fmt`.
   - Define three subcommand stubs (`run`, `verify`, `promote-verdict`) registered on `eval_group`; each body raises `NotImplementedError`.
   - Define a `main()` (or wrapping `run_cli()`) that invokes the group inside `try/except BaseException as exc: sys.exit(_map_exception_to_exit_code(exc))`.
   - Defer imports of `codegenie.eval.runner`, `codegenie.eval.promotion`, `codegenie.eval.audit`, `pydantic`, `pyyaml` inside subcommand bodies.
3. Register the group on the top-level CLI in **`src/codegenie/cli.py`** — that module owns the `cli` object (`@click.group(name="codegenie")`) and already registers sibling sub-groups (`@cli.group(name="audit")`, `name="vuln-index")`). Add `from codegenie.eval.cli import eval_group` and `cli.add_command(eval_group)` surgically (Rule 3). `src/codegenie/__main__.py` and `pyproject.toml` are **not** the registration point. The imported `eval_group` must stay light (AC-7).
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/cli.py`, `pytest tests/unit/eval/test_cli_scaffold.py tests/unit/eval/test_cli_exit_codes.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/eval/test_cli_scaffold.py` and `tests/unit/eval/test_cli_exit_codes.py`.
(The pre-existing `tests/unit/test_cli_exit_codes.py` belongs to the gather CLI — do not touch it.)

```python
# tests/unit/eval/test_cli_scaffold.py
import sys
import time
import importlib
import click
from click.testing import CliRunner


def test_cli_group_exists_and_lists_exact_three_subcommands():
    from codegenie.eval.cli import eval_group

    # Structural, not substring: a missing/extra command fails loudly.
    assert set(eval_group.commands) == {"run", "verify", "promote-verdict"}

    result = CliRunner().invoke(eval_group, ["--help"])
    assert result.exit_code == 0


def test_format_default_and_propagation_via_context():
    """AC-4 — behavioral: the default IS jsonl and it reaches ctx.obj.

    A help-text substring check is insufficient — the Choice list
    ``[human|jsonl]`` contains 'jsonl' even if default were 'human'.
    So mount a probe subcommand that echoes the propagated value.
    """
    from codegenie.eval.cli import eval_group

    @eval_group.command(name="_probe")
    @click.pass_context
    def _probe(ctx: click.Context) -> None:
        click.echo(ctx.obj["format"])

    try:
        runner = CliRunner()
        default = runner.invoke(eval_group, ["_probe"])
        assert default.exit_code == 0
        assert default.output.strip() == "jsonl"

        explicit = runner.invoke(eval_group, ["--format", "human", "_probe"])
        assert explicit.exit_code == 0
        assert explicit.output.strip() == "human"
    finally:
        eval_group.commands.pop("_probe", None)  # keep the group pristine


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
# tests/unit/eval/test_cli_exit_codes.py
import importlib
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


def test_mapper_is_table_driven_and_covers_every_nongeneric_code():
    """AC-9 — the table is the single source; codes 2..6 are all reachable.

    Adding a new (error → code) row must not require editing branch logic;
    here we assert the table's declared codes cover the non-generic space
    (2 included only when the cost-cap row is present).
    """
    codes = {code for _matcher, code in cli_module._EXIT_CODE_TABLE}
    assert {3, 4, 5, 6} <= codes
    assert cli_module.EXIT_GENERIC_ERROR not in codes  # 1 is the default, never a row


@pytest.mark.parametrize(
    "exc,expected_code",
    [
        (e.TaskClassNotFound("foo", ("bar",)), 3),
        (e.BenchCaseDigestMismatch("003-x", "abc", "def"), 6),
        # The eval ChainTamperDetected, NOT codegenie.plugins.events's.
        (e.ChainTamperDetected("/tmp/x", "0" * 64, "1" * 64), 5),
    ],
)
def test_exception_maps_to_exit_code(exc: Exception, expected_code: int) -> None:
    # Internal helper tested at the boundary so the partition is independently
    # verifiable; CliRunner integration paths are covered by S4-02/S4-03.
    assert cli_module._map_exception_to_exit_code(exc) == expected_code


def test_bench_dir_missing_discriminates_on_reason_not_type() -> None:
    """AC-5 — only the sentinel reason maps to 4; any other reason -> 1.

    Guards a 'map every BenchCaseLoadError -> 4' mutation.
    """
    missing = e.BenchCaseLoadError(
        "bench/vuln", "case_dir", cli_module._BENCH_DIR_MISSING_REASON
    )
    other = e.BenchCaseLoadError("bench/vuln", "case.toml", "unparseable toml")
    assert cli_module._map_exception_to_exit_code(missing) == 4
    assert cli_module._map_exception_to_exit_code(other) == 1


def test_uncaught_exception_maps_to_generic_one() -> None:
    assert cli_module._map_exception_to_exit_code(RuntimeError("anything")) == 1


def test_cost_cap_maps_to_two_when_symbol_present() -> None:
    """AC-6 — shim-safe: skip cleanly if S3-06's CostCapExceeded isn't here."""
    cost_cap = getattr(e, "CostCapExceeded", None)
    if cost_cap is None:
        pytest.skip("CostCapExceeded (S3-06) not yet importable")
    assert cli_module._map_exception_to_exit_code(cost_cap("budget $5.00")) == 2
```

Run; confirm `ModuleNotFoundError: No module named 'codegenie.eval.cli'` (and missing attributes once the module exists). Commit as the red marker.

### Green — make it pass

Create `src/codegenie/eval/cli.py` with:
- Seven `EXIT_*` constants annotated `Final[int]`.
- `_BENCH_DIR_MISSING_REASON: Final[str]` — the single sentinel-reason coupling point to the loader.
- `_EXIT_CODE_TABLE: Final[tuple[tuple[Callable[[BaseException], bool], int], ...]]` — `(matcher, code)` rows, the reason-match `BenchCaseLoadError` row ordered before any broader `CodegenieEvalError` row; the cost-cap row appended only when `CostCapExceeded` imports.
- `eval_group = click.Group(...)` (or `@click.group(name="eval")` assigned to `eval_group`) with `@click.option("--format", "fmt", type=click.Choice(["human", "jsonl"]), default="jsonl", show_default=True)`; group callback does `ctx.ensure_object(dict); ctx.obj["format"] = fmt`.
- Three `@eval_group.command()` stubs (`run`, `verify`, `promote-verdict`), each body `raise NotImplementedError("S4-02/S4-03/S4-04")`.
- A `_map_exception_to_exit_code(exc: BaseException) -> int` helper that iterates `_EXIT_CODE_TABLE` and returns the first matching code, else `EXIT_GENERIC_ERROR`.
- A `main()` (or `run_cli()`) calling the group inside `try/except BaseException as exc: sys.exit(_map_exception_to_exit_code(exc))`.

No imports of `pydantic`, `pyyaml`, `bench.*`, `runner`, `promotion`, or `audit` at module top. (`from codegenie.eval import errors` is fine — that module is behavior-free markers, no `pydantic`.)

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
| `src/codegenie/eval/cli.py` | New file — Click group `eval_group`, three stub subcommands, `Final[int]` exit-code constants, `_EXIT_CODE_TABLE` data-driven mapper, `_BENCH_DIR_MISSING_REASON` sentinel, `main()` entry. |
| `tests/unit/eval/test_cli_scaffold.py` | New file — exact 3-command set, `--format` default+propagation via `ctx.obj` (behavioral), cold-start < 660 ms, no heavy imports leaked. |
| `tests/unit/eval/test_cli_exit_codes.py` | New file — seven constants disjoint, table-driven mapper covers codes 2–6, reason-discrimination for code 4, shim-safe cost-cap, generic-1 default. |
| `src/codegenie/cli.py` | Register the sub-group surgically: `from codegenie.eval.cli import eval_group` + `cli.add_command(eval_group)` alongside the existing `audit` / `vuln-index` sub-groups. **Not** `__main__.py` or `pyproject.toml`. |

## Out of scope

- **Implementing `run`, `verify`, `promote-verdict` bodies** — handled by S4-02 (`run`), S4-03 (`verify`), and S4-04+S4-05 (`promote-verdict` reads PromotionGate output). Stubs raise `NotImplementedError` here.
- **`--cases`, `--concurrency`, `--max-cost-usd`, `--no-cache`, `--out`, `--with-verdict`, `--bench-root` flags** — wired in S4-02 on the `run` subcommand.
- **`--since`, `--strict` flags** — wired in S4-03 on the `verify` subcommand.
- **`PromotionGate` construction and `TierConfig` loading** — wired in S4-04 (gate logic) and S4-05 (recommendation writer).
- **JSONL line writer** — the `--format` option exists structurally here; per-case JSONL emission and human-readable table rendering happen in S4-02.
- **Cost-cap exception class** — S3-06 owns the `CostCapExceeded` (or equivalent) sentinel; this story just maps it to exit 2 when the symbol exists. If S3-06 has not yet landed, gate the mapping on a `try: from codegenie.eval.errors import CostCapExceeded; except ImportError: CostCapExceeded = ...` shim and flag it.

## Notes for the implementer

- **Defer EVERY heavy import.** Even `from codegenie.eval.models import BenchRunReport` triggers `pydantic` and breaks the cold-start budget. Inside subcommand bodies, `import` at function scope; the lint contract from Phase 0 (`import-linter`) will codify this in S1-05 and S7-* — but write it correctly the first time so the test in this story stays green.
- **Click 8+** is the assumption (the top-level `codegenie` group already relies on it); the `main()` wrapper — not `@eval_group.result_callback` — is the single exception→exit-code chokepoint, so version-specific callback semantics are irrelevant here. Check `pyproject.toml` if in doubt.
- **`--format` propagation:** store the chosen format in `click.Context.obj` (initialize via `ctx.ensure_object(dict)` at the group level). Subcommands read `ctx.obj["format"]`. This avoids parameter duplication on every subcommand declaration.
- **Cold-start budget is honestly load-bearing.** Phase 0's `codegenie gather` set this number; operators see `codegenie eval --help` ≥ 50× more often than they see a full run. A 1.5 s `--help` is broken UX even though it does no work.
- **`_map_exception_to_exit_code` is intentionally a private helper.** Testing the boundary directly (rather than only via `CliRunner`) means the partition is independently verifiable; CLI integration tests in S4-02/S4-03 cover the full Click invocation path. The name is `_`-prefixed; do not export it.
- **Table-driven, not branch-driven (AC-9).** The mapper iterates `_EXIT_CODE_TABLE` rows and returns the first match. This is the codebase's Open/Closed idiom (`_LOCKFILE_PRECEDENCE`, `_GENERATOR_HEADER_MARKERS`, the probe/strategy registries) — adding a future error→code is a one-row append, never an `elif`. Order is load-bearing: the `BenchCaseLoadError`-reason row must precede any broad `isinstance(exc, CodegenieEvalError)` catch-all row, or the reason-discrimination (AC-5) collapses.
- **`ChainTamperDetected` is a colliding name across the codebase.** `codegenie.plugins.events.ChainTamperDetected` (an `EventLogError`) and `codegenie.eval.errors.ChainTamperDetected` (a `CodegenieEvalError`, from S1-01) are *distinct classes*. The table row must reference the **eval** one (`from codegenie.eval import errors`); a stray import of the plugins class would silently never match and the run would exit 1 instead of 5.
- **Avoid the `eval` builtin-shadow.** Export the group as `eval_group`; the `codegenie eval` CLI surface comes from `name="eval"`, not the Python identifier. This matches the top-level `cli`/`name="codegenie"` precedent and keeps `flake8-builtins` (ruff `A`) quiet without `# noqa`.
- **The cost-cap signal shape is unsettled at the time of writing.** S3-06's `BenchRunReport.complete=False` + `run_id.startswith("partial:")` is the data; whether the CLI sees a `CostCapExceeded` exception or a returned `BenchRunReport` is a S4-02 decision. Either way, this story's `_map_exception_to_exit_code` handles the exception form; the report-based path is checked by S4-02 after the runner returns.
- **No `BaseException` catch-alls in the group body** — only `main()` wraps everything. Inside subcommands, let exceptions propagate; `main()` is the single mapping point. This makes the partition tractable to test.
