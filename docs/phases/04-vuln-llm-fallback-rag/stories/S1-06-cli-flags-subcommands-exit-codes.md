# Story S1-06 — Phase-4 CLI flag stubs + new subcommand groups + exit codes 9/10/11

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-P4-002, ADR-P4-008, ADR-P4-010, ADR-P4-013

## Context

Cross-cutting. The CLI is the only public surface the operator sees and the contract Phase-4 stories beyond Step 1 keep extending. This story plants every Phase-4 flag on `remediate` so Step 2–6 stories can fill in semantics without touching the parser, plants the three new subcommand *groups* (`solved-examples`, `auth`, `models`) so Step 4/6 stories can hang concrete subcommands off them, and wires the new exit codes 9 / 10 / 11 documented in `../phase-arch-design.md §"Harness engineering"`. Flag parsing only — every default-semantics decision (e.g. what `--no-rag` does to writeback) is deferred to its owner story (S6-03 for `--no-rag` semantics; S2-04 for `auth status` echo discipline; S4-07 for `models fetch` body).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Harness engineering"` — exit codes, configuration precedence, every Phase-4 flag enumerated.
  - `../phase-arch-design.md §"Control flow"` — flag-driven decision points A–E.
- **Phase ADRs:**
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — `--max-llm-cost-usd`, `--allow-cost-overrun`.
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 — `auth` subcommand group rationale.
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — `--leaf {in_process,jailed}`.
- **Existing code:**
  - `src/codegenie/cli.py` — Phase-0–3 CLI; extend.

## Goal

Extend `src/codegenie/cli.py` with the six new `remediate` flags and three new subcommand groups, and wire exit codes 9 (`llm_output_rejected | out_of_scope_action_surface | cost_ceiling_breached | egress_violation`), 10 (`llm.upstream_unavailable`), and 11 (`config_invalid`) — parsing and exit-code mapping only.

## Acceptance criteria

- [ ] `codegenie remediate --help` lists `--max-llm-cost-usd FLOAT`, `--leaf {in_process,jailed}`, `--no-llm`, `--no-rag`, `--allow-cross-repo-rag`, `--allow-cost-overrun FLOAT` with one-line help text per flag.
- [ ] `--max-llm-cost-usd` parses to `Decimal`, not `float` (consistent with `LlmRequest.cost_usd` and `LlmInvocationGuard`).
- [ ] `--leaf` defaults: `in_process` on macOS, `jailed` on Linux; CLI auto-resolves the default via `platform.system()`.
- [ ] `codegenie solved-examples --help`, `codegenie auth --help`, `codegenie models --help` each list at least one subcommand placeholder and exit 2 with a clear "not yet implemented" message when invoked without a subcommand or with a stub subcommand.
- [ ] Exit-code mapping wired in the CLI's top-level exception handler: `LlmOutputRejected | CostCeilingBreached | EgressViolation | OutOfScopeActionSurface` → 9; `LlmTransportError | LlmTimeout` → 10; `PromptTemplateInvalid | PromptVariableMissing | ConfigInvalid` → 11. Existing Phase-0–3 mappings unchanged.
- [ ] `tests/unit/cli/test_phase4_flags_parse.py` covers each new flag (positive parse + default value).
- [ ] `tests/unit/cli/test_phase4_exit_code_map.py` covers each new exception → exit-code mapping (raise → assert exit code).
- [ ] `tests/unit/cli/test_phase4_subcommand_groups.py` asserts each new group prints help and exits 2 when called without a subcommand.
- [ ] Exit-9 path prints a stderr banner pointing the operator to the Phase-4 runbook (`docs/phases/04-vuln-llm-fallback-rag/runbook.md` — created in S7-06). Placeholder is fine in Step 1.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/cli.py` clean.

## Implementation outline

1. Extend `remediate` command with six new options. Match the Phase-0–3 framework (`click`, per `CLAUDE.md`).
2. Add three new subcommand groups (`@cli.group()`) named `solved-examples`, `auth`, `models`. Each carries a single placeholder subcommand that prints "not yet implemented for v0.4.0 — see Phase 4 runbook" and exits 2.
3. Centralize exit-code mapping: a single function `_phase4_exception_to_exit_code(exc)` in `cli.py` (or in a small `cli/exit_codes.py` helper if Phase 0–3 already factored it) maps each Phase-4 exception type to an int. Hook it into the CLI's top-level `try/except` in `main`.
4. The exit-9 stderr banner is a 2–3 line block: human-readable reason + path to the (future) runbook + run-id (if available).
5. `--leaf` default resolution: `platform.system() == "Linux"` → `jailed`, else `in_process`. Surface a one-line CLI startup audit warning when `--leaf=in_process` is overridden on Linux (the actual `audit.warning(leaf_in_process_on_linux)` event is emitted in S3-02; the CLI just lets the override through).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/cli/test_phase4_flags_parse.py`

```python
from decimal import Decimal

from click.testing import CliRunner

from codegenie.cli import cli


def test_remediate_accepts_all_phase4_flags():
    r = CliRunner().invoke(
        cli,
        [
            "remediate",
            "--cve", "CVE-2024-0001",
            "--max-llm-cost-usd", "0.50",
            "--leaf", "in_process",
            "--no-llm",
            "--no-rag",
            "--allow-cross-repo-rag",
            "--allow-cost-overrun", "1.00",
            "--dry-run",
        ],
    )
    assert r.exit_code in (0, 4), r.output  # 4 = no_recipe is fine; we're testing parse
    # negative: a typo'd flag must fail
    r2 = CliRunner().invoke(cli, ["remediate", "--max-llm-cost", "0.50"])
    assert r2.exit_code != 0


def test_max_llm_cost_is_decimal_not_float():
    # arrange/act/assert via the CLI context's parsed value — concrete approach
    # depends on how Phase-0 plumbs click params to the runtime. The shape we
    # require: when the flag parses, the held value is `Decimal`, not `float`.
    ...


def test_leaf_default_matches_platform(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    r = CliRunner().invoke(cli, ["remediate", "--help"])
    assert "jailed" in r.output and "[default: jailed]" in r.output
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    r = CliRunner().invoke(cli, ["remediate", "--help"])
    assert "in_process" in r.output and "[default: in_process]" in r.output
```

Test file path: `tests/unit/cli/test_phase4_exit_code_map.py`

```python
import pytest

from codegenie.errors import (
    CostCeilingBreached, LlmOutputRejected, LlmTransportError,
    LlmTimeout, PromptTemplateInvalid, PromptVariableMissing,
)
from codegenie.cli import _phase4_exception_to_exit_code


@pytest.mark.parametrize("exc_factory,expected", [
    (lambda: LlmOutputRejected(reason="canary_echo_failed", errors=[], canary_fingerprint=""), 9),
    (lambda: CostCeilingBreached(estimated=1.0, ceiling=0.5), 9),
    (lambda: LlmTransportError(retries=3, last_status=529), 10),
    (lambda: LlmTimeout(seconds=60), 10),
    (lambda: PromptTemplateInvalid(path="x", reason="y"), 11),
    (lambda: PromptVariableMissing(template="x", variable="y"), 11),
])
def test_phase4_exit_code_mapping(exc_factory, expected):
    assert _phase4_exception_to_exit_code(exc_factory()) == expected
```

Test file path: `tests/unit/cli/test_phase4_subcommand_groups.py`

```python
from click.testing import CliRunner

from codegenie.cli import cli


@pytest.mark.parametrize("group", ["solved-examples", "auth", "models"])
def test_subcommand_group_lists_in_help_and_exits_2_without_subcmd(group):
    r = CliRunner().invoke(cli, [group])
    assert r.exit_code == 2, (group, r.output)
    assert "not yet implemented" in r.output.lower() or "Usage:" in r.output
```

### Green — make it pass

Add the flags, the groups, the exit-code mapping function. The simplest possible implementation — flag parsing only; no behaviour change.

### Refactor — clean up

- Help text on each flag should fit one line and name the owner story for the semantics (e.g. `--no-rag` help text: "Skip tier-2 retrieval; LLM-cold still runs (S6-03 Gap 4)").
- The exit-code mapping function should be exhaustive: any Phase-4 exception type registered in S1-01 must be in the map. Add a regression test that iterates over `BaseCodegenieError.__subclasses__()` and asserts every subclass added in S1-01 has an exit-code mapping or is explicitly excluded.
- Rule 11 (match conventions): the Phase-0 CLI uses `click`; keep using `click`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Add flags, subcommand groups, exit-code mapping. |
| `tests/unit/cli/test_phase4_flags_parse.py` | Flag parsing positive + default. |
| `tests/unit/cli/test_phase4_exit_code_map.py` | Exception → exit code. |
| `tests/unit/cli/test_phase4_subcommand_groups.py` | Group help + exit-2 behavior. |

## Out of scope

- **`--no-rag` / `--no-llm` runtime semantics** — S6-03 (Gap 4).
- **`auth set-anthropic-key`, `auth status`** bodies — S2-05.
- **`models fetch`** body — S4-07.
- **`solved-examples calibrate|list|show`** bodies — S6-04.
- **`solved-examples reindex|prune --orphans`** bodies — S4-07.
- **Runbook content at `docs/phases/04-vuln-llm-fallback-rag/runbook.md`** — S7-06 lands the file; this story just references the path.
- **Audit emission of `leaf_in_process_on_linux`** — S3-02.

## Notes for the implementer

- `--max-llm-cost-usd` must yield `Decimal` (not `float`) to flow into `LlmInvocationGuard` (S2-03) without loss. `click.FLOAT` is `float`; use `click.STRING` + `Decimal(...)` conversion in a callback.
- `--leaf` default split between macOS/Linux is mandated by ADR-P4-004; do not unify to one default "for simplicity" (Rule 11 + ADR honour).
- The three subcommand groups must exist as *groups*, not as no-op commands, so S2-05 / S4-07 / S6-04 can attach subcommands without touching this story's diff. Use `@cli.group()` and `@<group>.command()` patterns.
- The exit-code mapping function is the single source of truth for exit semantics; if a Phase-4 module raises a typed exception not in the map, the CLI must surface that as a defect (not silently exit 1). Add a fall-through that prints "internal error: unmapped Phase-4 exception {type}" and exits 70 (sysexits `EX_SOFTWARE`) to make missing mappings loud (Rule 12).
- Configuration precedence (`../phase-arch-design.md §"Harness engineering"` row "Configuration precedence"): CLI > env > `~/.config/codegenie/llm.yaml` > defaults. This story implements only the CLI level. Env-var pickup (`CODEGENIE_MAX_LLM_COST_USD`, etc.) is fine to register here if the Phase-0 framework supports it cheaply; if not, defer to S6-03.
- The exit-9 stderr banner is the first place an operator looks when the LLM path rejects output. Make the message specific: include the reason ("canary echo failed") and the cassette/raw-response path when known. The reason string comes from the exception's `reason` kwarg (S1-01).
- Edge cases from `../phase-arch-design.md §"Edge cases"`: row #9 (`$`-cap exceeded), row #10 (cassette miss → exit 9 doesn't apply, but exit 1 from pytest fails CI loud), row #11 (Anthropic 5xx → exit 10), row #17 (PromptTemplate malformed YAML → exit 11). The mapping function covers them.
