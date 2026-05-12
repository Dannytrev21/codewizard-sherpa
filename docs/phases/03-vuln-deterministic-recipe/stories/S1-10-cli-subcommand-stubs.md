# Story S1-10 — `codegenie remediate` / `cve` / `recipes` CLI subcommand-group stubs

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-02 (`Transform` ABC + `TransformError` exception — the stub error messages reference the ABC by name in their not-yet-implemented helptext), S1-04 (Pydantic boundary models — the CVE-id regex validator and the eventual flag types live in `cli.py` close to the boundary types)
**ADRs honored:** ADR-0001 (the `Transform` ABC is the contract these CLI surfaces ultimately drive — the stubs are entry points only; the bodies are wired in S5-05), ADR-0014 (`ALLOWED_BINARIES +3` — the tool-readiness check shape is sketched here; full implementation in S5-05), production ADR-0005 (CLI exit-code discipline — exit 2 is reserved for "not yet implemented" + malformed-CLI-input per the production-level mapping)

## Context

S5-05 is the load-bearing CLI story that wires every flag, exit code, and operator surface for the `codegenie remediate`/`cve`/`recipes` subcommands end-to-end. But S5-05 depends on every prior step's machinery (orchestrator, branch writer, CVE syncer, recipe registry). Per the High-level-impl plan, Step 1 lands the three subcommand *groups* as **entry-point-only stubs** so:

1. The CLI shape is reviewable in a small PR alongside the contracts (the click group/command tree is the surface Phase 4 might consume; nailing it early is cheap).
2. Step 1's `tool-readiness` discipline (ADR-0014) has somewhere to live without waiting until Step 5.
3. The `--cve` regex validator lives in `cli.py` close to the Pydantic boundary models from S1-04, decoupling the validation from the body implementation.
4. Phase 0/1/2's existing `cli.py` is exercised by Step 1's tests (the `remediate`/`cve`/`recipes` groups must coexist with the existing `gather` group from Phase 1+2 without regression).

This story does **not** implement the subcommand bodies. Each stub command prints a "not yet implemented" message to stderr and exits 2. The exit code is deliberate per production ADR-0005's CLI exit-code discipline: code 2 is "tool-readiness OR malformed CLI input" — a stub is structurally "not ready to do the work," which is the same operator-visible condition. S5-05 replaces every stub body with real logic; the stubs serve as placeholders that make Step 1 a self-contained, reviewable surface.

The closed-enum flag types (e.g., `--engine ncu|openrewrite`, `--allow-policy-violations <type>,...`) and the `--cve` regex are declared at the click-decorator level so the validator-side discipline (closed-enum click choices) is in place from day one. A consumer running `codegenie remediate --engine bogus` after this story merges sees `error: Invalid value for '--engine': 'bogus' is not one of 'ncu', 'openrewrite'` — not a NameError two steps deep into the orchestrator. The validation surface is the load-bearing piece of this story; the bodies are not.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #16 CLI subcommands` — the full flag set, the regex on `--cve`, the tool-readiness check shape.
  - `../phase-arch-design.md §"Control flow" — Decision points`  — the exit-code edges this story stubs out.
- **Phase ADRs:**
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — the tool-readiness binary list (`git`, `npm`, `ncu`; `java` only on `--engine=openrewrite`).
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — the stubs point at the contract these subcommands will eventually drive.
- **Production ADRs:**
  - `../../../production/adrs/0005-cli-exit-code-discipline.md` — exit 2 reserved for malformed-CLI / not-ready conditions.
- **Source design:**
  - `../final-design.md §"Components" #11 CLI` — subcommand list + flag set + tool-readiness sketch.
  - `../High-level-impl.md §"Step 1"` — entry-point-only stubs explicitly called out for Step 1; bodies in Step 5.
- **Existing code:**
  - `src/codegenie/cli.py` (Phase 0 / Phase 1 / Phase 2) — the entry point this story extends. Read it before extending to confirm whether it uses a single-file pattern or a per-subcommand module pattern (`src/codegenie/cli/__init__.py` + `src/codegenie/cli/<group>.py`). Match the existing convention.
  - `src/codegenie/errors.py` (extended in S1-01) — `TransformError`, `EngineUnavailable` types referenced in the stub helptext (so the helptext stays self-documenting as the body lands in S5-05).
- **Style reference:**
  - `S5-05-remediate-cli-exit-codes.md` — the *target* surface this story stubs. The stubs in this story are the entry-point-only seam; S5-05 fills in the bodies.

## Goal

Land three new click subcommand groups — `codegenie remediate`, `codegenie cve`, `codegenie recipes` — as entry-point-only stubs that validate flags (closed-enum `--engine`, `--cve` regex) at parse time, print "not yet implemented" to stderr, and exit 2; the existing Phase 0/1/2 `gather` group continues to work unchanged; the click group tree is reviewable as a self-contained surface ahead of S5-05 wiring the bodies.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` (or `src/codegenie/cli/<module>.py` per the existing convention — match whatever Phase 0 used) declares three new click groups: `remediate`, `cve`, `recipes`. Each group is registered via `@cli.group()` (or whatever the parent `cli` group's name is) on the top-level entry point.
- [ ] **`codegenie remediate`** is a single click *command* (not a group) with the full Step-5 flag set declared at the decorator level:
  - `<repo>` (positional `click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True)`).
  - `--cve TEXT` (required, with a `callback=` validator that re-raises `click.BadParameter` if the value does not match `^CVE-\d{4}-\d{4,}$`).
  - `--engine [ncu|openrewrite]` (default `ncu`, closed-enum via `click.Choice(["ncu", "openrewrite"])`).
  - `--allow-policy-violations TEXT` (default empty string; parsed in S5-05 — this story accepts the flag but does not yet parse it).
  - `--allow-test-network` / `--no-allow-test-network` (boolean flag, default off).
  - `--allow-stale-feeds` / `--no-allow-stale-feeds` (boolean, default off).
  - `--strict` / `--no-strict` (boolean, default off).
  - `--auto-gather` / `--no-auto-gather` (boolean, default on — `True`).
  - `--run-id TEXT` (default to a callable producing ISO-8601 + short random id; the callable lives in `src/codegenie/cli.py` as a helper so S5-05 can reuse it).
- [ ] **`codegenie cve`** is a click *group* with a single sub-command `sync` declared (entry-point only):
  - `--source [nvd|ghsa|osv|all]` (closed-enum `click.Choice(...)`, default `all`).
  - `--since TEXT` (optional, intended to accept ISO-8601 date; this story does not validate beyond presence — S2-07 will).
- [ ] **`codegenie recipes`** is a click *group* with a single sub-command `list` declared (entry-point only):
  - `--engine TEXT` (optional).
  - `--task TEXT` (default `vuln_remediation`).
- [ ] Every stub command body is the literal shape:
  ```text
  Print to stderr: "error: <subcommand> is not yet implemented (Phase 3 Step 5 lands the body — see docs/phases/03-vuln-deterministic-recipe/stories/S5-05-remediate-cli-exit-codes.md)"
  sys.exit(2)
  ```
- [ ] `--help` on each new command prints the full flag set and a one-line summary describing the eventual behavior (e.g., `Remediate a CVE on a local Node.js repository by selecting and applying a deterministic recipe, then validating in a sandbox.`). The help text is the human-facing contract; this story makes it correct from day one.
- [ ] **The existing `codegenie gather` group is unchanged** — the click registration tree extends additively. A regression test asserts `codegenie gather --help` still exits 0 and prints the Phase 2 help text.
- [ ] **CVE-id regex validator** is exported as a callable from `cli.py` (or a sibling module) so S5-05 and S2-07 can import it instead of redeclaring the pattern. A unit test pins (a) `CVE-2024-21538` accepts; (b) `CVE-2024-1` rejects (digits-after-year < 4); (c) `cve-2024-21538` rejects (case-sensitive); (d) `CVE-2024-21538-extra` rejects (no trailing garbage).
- [ ] `tests/unit/cli/test_phase3_subcommand_stubs.py` exists, exercises the three subcommand groups via `click.testing.CliRunner`, and asserts:
  - `codegenie remediate <tmp-dir> --cve CVE-2024-21538` → exit 2; stderr contains "not yet implemented".
  - `codegenie remediate --cve CVE-2024-21538` (no positional) → exit 2 (click validation); stderr names the missing positional argument.
  - `codegenie remediate <tmp-dir> --cve bogus` → exit 2; stderr contains "Invalid value for '--cve'".
  - `codegenie remediate <tmp-dir> --cve CVE-2024-21538 --engine bogus` → exit 2; stderr contains "Invalid value for '--engine'".
  - `codegenie cve sync --source nvd` → exit 2; stderr contains "not yet implemented".
  - `codegenie cve sync --source bogus` → exit 2; stderr contains "Invalid value for '--source'".
  - `codegenie recipes list` → exit 2; stderr contains "not yet implemented".
  - `codegenie gather --help` → exit 0 (regression — Phase 2 unchanged).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli.py tests/unit/cli/` pass.
- [ ] No changes to `src/codegenie/transforms/` or `src/codegenie/recipes/` source code from this story — the seams those packages plant (S1-02 / S1-03) are imported only inside the stubs' `--help` text formatting at most; if even that creates a circular dependency at click-registration time, defer the import.

## Implementation outline

1. **Read `src/codegenie/cli.py` (or equivalent) end-to-end** — Rule 8. Confirm whether the existing CLI uses a single-file pattern or a per-subcommand module. Match the convention.
2. **Add a helper** `_validate_cve_id(ctx, param, value: str) -> str` callable in `cli.py` that re-raises `click.BadParameter` if the value does not match the regex `^CVE-\d{4}-\d{4,}$`. Export it (or place it in a sibling `cli/_validators.py` if Phase 0 used that pattern) for S2-07 / S5-05 reuse.
3. **Add a helper** `_default_run_id() -> str` that returns `f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"` — ISO-8601 compact + 6-char random. The helper is the contract S5-05 reuses.
4. **Declare the three groups** (`remediate`, `cve`, `recipes`) on the existing top-level click group. Each registered via `@cli.group(...)` or as a top-level `@cli.command(...)` for `remediate` (which is a command, not a group).
5. **Declare every flag at the decorator level**, with `click.Choice` for enums and `callback=_validate_cve_id` for `--cve`. The flag set is the contract S5-05 reads; do not change it later.
6. **Body of each stub** is literally:
   ```python
   click.echo(f"error: {COMMAND_NAME} is not yet implemented (Phase 3 Step 5 — see ...)", err=True)
   raise click.exceptions.Exit(code=2)
   ```
   (Use `click.exceptions.Exit(code=2)`, not `sys.exit(2)`, so the runner machinery surfaces the code cleanly in tests.)
7. **Tests** under `tests/unit/cli/test_phase3_subcommand_stubs.py` exercise every assertion via `CliRunner().invoke(cli, [...])`. Use `mix_stderr=False` so stderr is asserted independently of stdout.
8. **Regression test** for the existing `gather` group: `CliRunner().invoke(cli, ["gather", "--help"])` exits 0 + stdout contains a Phase 2 expected string (e.g., `"Discover repository context"`). If Phase 2's help text wording differs, match the actual text.
9. **CVE-id regex tests** — four cases (accept happy; reject short year-suffix; reject lowercase; reject trailing garbage). Tests use the validator callable directly (not the click runner) so they pin the validator in isolation.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Path: `tests/unit/cli/test_phase3_subcommand_stubs.py`

```python
"""ADR-0001 + ADR-0014 | Invariant: Phase 3 lands three CLI subcommand stubs in Step 1; bodies in Step 5.

Step-1 contract:
- All flags validated at click-parse time (closed enums + CVE-id regex).
- Stubs exit 2 ("not yet implemented") per production ADR-0005.
- Phase 2 `gather` group continues to work — no regression.
"""
import pytest
from click.testing import CliRunner
from codegenie.cli import cli

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)

def test_remediate_stub_exits_2_with_message(runner, tmp_path) -> None:
    result = runner.invoke(cli, ["remediate", str(tmp_path), "--cve", "CVE-2024-21538"])
    assert result.exit_code == 2
    assert "not yet implemented" in result.stderr

def test_remediate_rejects_bad_cve_id(runner, tmp_path) -> None:
    result = runner.invoke(cli, ["remediate", str(tmp_path), "--cve", "bogus"])
    assert result.exit_code == 2
    assert "Invalid value for '--cve'" in result.stderr

def test_remediate_rejects_bad_engine(runner, tmp_path) -> None:
    result = runner.invoke(cli, ["remediate", str(tmp_path), "--cve", "CVE-2024-21538", "--engine", "bogus"])
    assert result.exit_code == 2
    assert "Invalid value for '--engine'" in result.stderr

def test_cve_sync_stub_exits_2(runner) -> None:
    result = runner.invoke(cli, ["cve", "sync", "--source", "nvd"])
    assert result.exit_code == 2
    assert "not yet implemented" in result.stderr

def test_cve_sync_rejects_bad_source(runner) -> None:
    result = runner.invoke(cli, ["cve", "sync", "--source", "bogus"])
    assert result.exit_code == 2
    assert "Invalid value for '--source'" in result.stderr

def test_recipes_list_stub_exits_2(runner) -> None:
    result = runner.invoke(cli, ["recipes", "list"])
    assert result.exit_code == 2
    assert "not yet implemented" in result.stderr

def test_gather_group_still_works(runner) -> None:
    result = runner.invoke(cli, ["gather", "--help"])
    assert result.exit_code == 0

def test_cve_id_regex_accepts_valid_cve() -> None:
    from codegenie.cli import _validate_cve_id  # or whatever the export path is
    assert _validate_cve_id(None, None, "CVE-2024-21538") == "CVE-2024-21538"

def test_cve_id_regex_rejects_short_year_suffix() -> None:
    import click
    from codegenie.cli import _validate_cve_id
    with pytest.raises(click.BadParameter):
        _validate_cve_id(None, None, "CVE-2024-1")

def test_cve_id_regex_rejects_lowercase() -> None:
    import click
    from codegenie.cli import _validate_cve_id
    with pytest.raises(click.BadParameter):
        _validate_cve_id(None, None, "cve-2024-21538")

def test_cve_id_regex_rejects_trailing_garbage() -> None:
    import click
    from codegenie.cli import _validate_cve_id
    with pytest.raises(click.BadParameter):
        _validate_cve_id(None, None, "CVE-2024-21538-extra")
```

Run; commit red.

### Green — make it pass

- Implement `_validate_cve_id` in `cli.py` (or sibling `_validators.py`). Use `re.fullmatch(r"^CVE-\d{4}-\d{4,}$", value)`.
- Implement `_default_run_id` helper using `datetime.now(timezone.utc).strftime(...)` + `secrets.token_hex(3)`.
- Declare `remediate` as `@cli.command()` with `@click.argument("repo", type=click.Path(...))` + every `@click.option(...)` per the acceptance criteria. The body prints "not yet implemented" and raises `click.exceptions.Exit(code=2)`.
- Declare `cve` as `@cli.group()`; under it, `@cve.command("sync")` with `--source` and `--since`.
- Declare `recipes` as `@cli.group()`; under it, `@recipes.command("list")` with `--engine` and `--task`.
- Ensure the existing `gather` group registration is unchanged.

### Refactor — clean up

- **One stub message constant** — pull the "not yet implemented" message format into a module-level constant `NOT_YET_IMPLEMENTED_FMT = "error: {cmd} is not yet implemented (Phase 3 Step 5 — see docs/phases/03-vuln-deterministic-recipe/stories/S5-05-remediate-cli-exit-codes.md)"`. Each stub formats with its command name. Keeps the format consistent and grep-able.
- **Confirm the click registrations are in the right order** — the top-level `cli` group is unchanged; `remediate` / `cve` / `recipes` extend it additively. The order in code is alphabetical for human readability; click does not enforce order.
- **Type annotations.** `click` types are notoriously fiddly with `mypy --strict`; use `Callable[..., Any]` on the validator if needed and document inline.
- **Confirm `codegenie --help` shows all four groups** (`gather`, `remediate`, `cve`, `recipes`). Capture the output in the PR body as evidence the surface is reviewable.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Add three subcommand groups (or commands) as entry-point-only stubs; declare every flag at decorator level. |
| `src/codegenie/cli/_validators.py` (optional, only if Phase 0 used this layout) | Hold `_validate_cve_id` + `_default_run_id` if Phase 0 already established a per-validator module. |
| `tests/unit/cli/test_phase3_subcommand_stubs.py` | New — invoke each stub via `CliRunner`; pin exit 2 + error message; pin Phase 2 `gather` regression. |
| `tests/unit/cli/test_cve_id_regex.py` (optional, may fold into above) | New — four-case regex validator tests. |

## Out of scope

- **Subcommand body implementation** — S5-05 wires `remediate`; S2-07 wires `cve sync`; S3-06 + S5-05 wire `recipes list`. This story is entry-point-only.
- **Tool-readiness check** — S5-05 plants the actual `git`/`npm`/`ncu`/`java` `which` check on the `remediate` body. This story's stub does not invoke it.
- **The `_default_run_id` callable's interaction with `--run-id`** — S5-05 wires the click resolution (CLI flag overrides default). This story just declares the callable.
- **Parsing `--allow-policy-violations`** — comma-separated parsing is S5-05's job; this story accepts the flag as a free-form TEXT.
- **Click completions / shell autocomplete** — out of scope; click ships its own scaffolding which a later phase can opt into.
- **Localization of error messages** — English-only; the messages are operator-facing and grep-able.

## Notes for the implementer

- **The stubs are the contract surface, not the body.** A reviewer of this PR is reviewing whether `codegenie remediate <repo> --cve CVE-2024-21538 --engine ncu --allow-test-network` is the right shape — every flag, every closed-enum, every default. The body wiring in S5-05 cannot retroactively change the surface without a follow-up ADR (the click decorator is the public CLI contract).
- **`click.exceptions.Exit(code=2)` vs `sys.exit(2)`.** Use the click exception. Click's runner machinery catches `Exit` and surfaces the code via `result.exit_code`; `sys.exit` works too but produces a `SystemExit` that test infra has to handle separately. Match what Phase 0's `cli.py` does.
- **Closed-enum at the decorator is load-bearing.** A consumer running `--engine openrwriete` (typo) gets a click error at parse time, not a `KeyError` two steps into the orchestrator. The same discipline applies to `--source` and (eventually in S5-05) `--allow-policy-violations` once that's parsed.
- **The CVE-id regex is `^CVE-\d{4}-\d{4,}$`** — four-or-more digits after the year. Real CVE IDs have been issued with five-digit suffixes (CVE-2024-21538 has five); the regex accommodates that. Do not narrow to exactly four digits.
- **`mix_stderr=False` on `CliRunner`** is what makes the stderr-assertion tests work. Without it, click's runner conflates stdout and stderr.
- **Phase 0's CLI uses click as the framework** — this story should not switch to argparse or typer. Rule 11 (match the codebase's conventions).
- **The "not yet implemented" message references S5-05 explicitly.** A consumer who runs `codegenie remediate ...` at the end of Step 1 should be able to find the story that will fix it. Resist the urge to make the message vague; it is the operator-debugging hint.
- **`mypy --strict` on `cli.py` is the trickiest test in Step 1.** Click's API uses overloaded decorators with `Any`-heavy signatures; if `mypy --strict` complains about the click decorators, add `# type: ignore[misc]` selectively on the decorators (not the bodies). Phase 0 may already have established the convention; mirror it.
- **Tool-readiness assertion in this story is *just the binary list*** — it does not run the check. The check shape lives in `src/codegenie/cli.py` as a private helper `_assert_tool_readiness(required: list[str]) -> None` that S5-05 wires onto the `remediate` body. This story can declare the helper as a `def _assert_tool_readiness(required: list[str]) -> None: raise NotImplementedError("wired in S5-05")` if a placeholder is useful; otherwise defer the helper to S5-05.
- **Regression risk: very low.** The biggest risk is breaking the existing `gather` group registration by replacing `@cli.command()` with `@cli.group()` on the parent. The Phase 2 regression test catches this. If `gather --help` red-fails after your change, you broke the parent group's invocation pattern — revert and try again.
