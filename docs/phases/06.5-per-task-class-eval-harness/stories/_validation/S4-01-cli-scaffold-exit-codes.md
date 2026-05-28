# Validation report — S4-01 CLI scaffold + partitioned exit codes

**Validated:** 2026-05-28 · **Skill:** phase-story-validator · **Verdict:** **HARDENED**

## Context brief

- **Goal:** land `src/codegenie/eval/cli.py` — the `codegenie eval` Click group, deferred heavy imports, the seven-code exit-code partition (0–6), `--format=human|jsonl` (default `jsonl`), cold-start ≤ 600 ms. `run`/`verify`/`promote-verdict` are stubs; S4-02/03/04 fill them.
- **Constraints read:** `phase-arch-design.md` (cli.py component = `codegenie eval run|verify|promote-verdict`; exit codes 1–6 partition; cold-start budget; `__init__` surface omits `pydantic`/`click`/`pyyaml`); ADR-0001 + ADR-0004 (per-case failures are *data on the report*, not CLI exit categories — the run still exits 0/2); production ADR-0009 (autonomy ends at the CLI; exit codes are operator-facing); S1-01 (the eval errors module — the **nine** frozen typed exceptions the mapper keys on); CLAUDE.md (Open/Closed via data-driven registries; newtypes/`Final` discipline; extension by addition).
- **Codebase reality checked:** `src/codegenie/eval/` does **not** exist yet (phase 6.5 unimplemented at code level — validating pre-execution). Top-level group is the `cli` object (`name="codegenie"`) in `src/codegenie/cli.py`, with sibling sub-groups `audit` / `vuln-index` registered there; `__main__.py` only calls `cli.main(...)`. `tests/unit/eval/` is the established eval-unit-test directory. S1-01's nine error classes do **not** include `CostCapExceeded` (S3-06 owns it).

## Critic findings

### Consistency (highest priority)
- **F-CON-1 — BLOCK.** `tests/unit/test_cli_exit_codes.py` **already exists** and is the *gather* CLI's exit-code test (`codegenie.cli` + `codegenie.errors`, created in commit `bcbaf6e`). The story's "Files to touch" created a new file at that exact path → silent clobber of unrelated, shipped tests. Also `tests/unit/test_cli_scaffold.py` was at the wrong directory. **Fix:** all eval CLI tests moved to `tests/unit/eval/` (matches `tests/unit/eval/test_runner_plan.py` etc.).
- **F-CON-2 — harden.** Registration was specified as `src/codegenie/__main__.py` or `pyproject.toml`. Neither registers a Click sub-group; the registration point is `src/codegenie/cli.py` (`cli.add_command(eval_group)`). Corrected in outline + Files-to-touch.
- **F-CON-3 — harden.** Exported symbol `eval` shadows the `eval()` builtin (the original red test even carried `# noqa: A001`). Renamed to `eval_group` with `name="eval"`, matching the `cli`/`name="codegenie"` precedent.

### Coverage
- **F-COV-1 — harden.** AC-2 lists six error→code mappings; the red test exercised only 3/5/6. Added **bench-dir-missing → 4** and **cost-cap → 2** cases.
- **F-COV-2 — harden.** The `BenchCaseLoadError`-reason → 4 mapping is the single fragile (stringly-typed) discrimination. Added a *negative* test (`reason != sentinel → 1`) that guards a "map every `BenchCaseLoadError` → 4" mutation, and pinned the sentinel as a module-level `Final` constant (`_BENCH_DIR_MISSING_REASON`) — one coupling point to the loader, not a scattered magic string. New AC-5.
- **F-COV-3 — harden.** `CostCapExceeded` is not among S1-01's frozen nine; it depends on S3-06. Made the cost-cap row + test **shim-safe** (`getattr`/`skipif`) so the suite neither silently passes a missing mapping nor redefines S3-06's symbol. New AC-6.

### Test quality
- **F-TQ-1 — harden.** `test_format_option_default_is_jsonl` only asserted the strings `--format` and `jsonl` appear in `--help`. A `default="human"` mutation survives (the Choice list `[human|jsonl]` still contains `"jsonl"`). Replaced with a behavioral probe subcommand echoing `ctx.obj["format"]`: omitting `--format` must print `jsonl`, `--format human` must print `human`. Tests the default **and** propagation (AC-4) by behavior.
- **F-TQ-2 — harden.** Subcommand listing used substring presence (`"run" in output` matches `"running"`). Replaced with `set(eval_group.commands) == {"run","verify","promote-verdict"}`.

### Design patterns
- **F-DP-1 — harden.** `_map_exception_to_exit_code` as an `if/elif` ladder grows by *edit* per new mapping — against the codebase's data-driven Open/Closed idiom. Replaced with a module-level `Final` ordered `_EXIT_CODE_TABLE` of `(matcher, code)` rows iterated by the mapper (default `EXIT_GENERIC_ERROR`). With six mappings this is past rule-of-three, so it became observable **AC-9** (codes 2–6 reachable from the table; adding a mapping = one-row append). Ordering documented (reason-row before any broad catch-all).
- **F-DP-2 — nit.** `EXIT_*` annotated `Final[int]`.
- **F-DP-3** — folded into F-CON-3 (builtin shadow).

## Conflict resolution
No critic conflicts. Consistency findings (file collision, registration point) dominated and were applied directly; design-pattern table-drivenness was past rule-of-three so elevated to an observable AC rather than left as a note.

## Edits applied
- Header `Status: Ready → HARDENED`; added `Validation notes` block; added S1-01 to `Depends on`.
- ACs renumbered/strengthened (AC-1..AC-11): exact command set, behavioral `--format` default+propagation, reason-discrimination (AC-5), shim-safe cost-cap (AC-6), table-driven mapper (AC-9), `Final[int]` constants.
- Implementation outline: test paths → `tests/unit/eval/`; registration → `src/codegenie/cli.py`; sentinel + table specified.
- TDD plan rewritten: exact-command-set test, behavioral format test, table-coverage test, reason-discrimination test, shim-safe cost-cap test; file paths corrected.
- Files-to-touch table corrected (test dir + registration module).
- Notes for implementer: table ordering, cross-package `ChainTamperDetected` collision, builtin-shadow avoidance, `main()`-as-sole-chokepoint.

## Verdict
**HARDENED** — the goal, cold-start budget, and exit-code partition were sound; the story had one blocking defect (test-file collision) and several real-but-fixable weaknesses (wrong registration point, thin format/listing tests, untested partitions, branch-driven mapper, builtin shadow). All addressed in place. Ready for `phase-story-executor`.
