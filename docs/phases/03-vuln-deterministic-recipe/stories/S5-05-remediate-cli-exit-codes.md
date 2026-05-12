# Story S5-05 — `codegenie remediate` CLI + `codegenie recipes list` + exit-code mapping

**Step:** Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface
**Status:** Ready
**Effort:** M
**Depends on:** S5-04 (`PatchBranchWriter`), S5-03 (`RemediationOrchestrator`), S5-02 (`load_context`), S1-10 (CLI subcommand-group stubs from Step 1 — `remediate`, `cve`, `recipes`); transitively S3-06 (`RecipeRegistry.list`), S4-05 (`gate.signal_escalate` escalation JSON), S2-07 (`CveFeedReader` staleness).
**ADRs honored:** ADR-0001, ADR-0005, ADR-0006, ADR-0007, ADR-0008, ADR-0014; Gap 3 (`signal_escalate` operator surface), Gap 6 (engine availability snapshot), Gap 7 (auto_gather recursion).

## Context

This story wires the operator-facing surface — every flag, every exit code, every tool-readiness check, every CLI banner — and is where the documented exit-code mapping becomes load-bearing (the mapping table is asserted by integration tests on a per-row basis). Step 1's S1-10 landed the `remediate`/`cve`/`recipes` subcommand *groups* as placeholders printing "not yet implemented" at exit 2; this story replaces those placeholders with the real implementations.

The CLI is the **top-level safety net** per S5-03's failure-preservation contract — it catches the one `Exception` allowed in Phase 3, emits `meta.unexpected_exception` to the audit chain, writes the partial `remediation-report.yaml` (with `exit_code: 99` or similar for unhandled), and re-raises to the operator with a stack trace on stderr. Every other layer in Phase 3 propagates uncaught.

The seven documented exit codes (0/4/5/6/7/8/9) each have a corresponding integration test that drives the CLI end-to-end on a real fixture. Two more exit codes (10/11) are reachable from `resolve_advisory` but are out of scope for the load-bearing integration suite — unit tests on S2-07 cover them.

Per Gap 3, `gate.signal_escalate` (exit 8) has an operator-facing surface: a JSON file on disk (`<run-dir>/escalation.json` written by S4-05), a section in `remediation-report.yaml`, and a stderr banner from this CLI. The banner is the contract the operator-runbook (S7-07) documents.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #16 CLI subcommands` — three subcommands, regex validation, tool-readiness check.
  - `../phase-arch-design.md §"Component design" #9 RemediationOrchestrator` — exit-code mapping table.
  - `../phase-arch-design.md §"Control flow" — Decision points` — exit-code edges.
  - `../phase-arch-design.md §"Gap 3 — gate.signal_escalate has no human in the local POC"` — operator surface (JSON + banner).
  - `../phase-arch-design.md §"Harness engineering" — Logging` — structured JSON to stderr; stdout reserved for the YAML location line.
- **Phase ADRs:**
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — exit 8 + `--allow-test-network`.
  - `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — exit 7 + `--allow-policy-violations`.
  - `../ADRs/0008-cve-feed-integrity-content-hash-best-effort-signature-graded-staleness.md` — `--allow-stale-feeds` (exits 11 → 0 with the flag).
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — tool-readiness for `git`, `npm`, `ncu`, optionally `java`.
- **Production ADRs:**
  - `../../../production/adrs/0005-cli-exit-code-discipline.md` — the broader exit-code discipline this story implements one slice of.
- **Source design:**
  - `../final-design.md §"Components" #11 CLI` — subcommand list + flag set.
- **Existing code:**
  - `src/codegenie/cli.py` (Phase 0 + S1-10 placeholder groups) — the entry point this story extends.
  - `src/codegenie/transforms/coordinator.py` (S5-03) — `remediate(...)` is the function this CLI invokes.
  - `src/codegenie/recipes/registry.py` (S1-03 + S3-04 + S3-06) — `RecipeRegistry.list(engine, task)` is the function `recipes list` invokes.
  - `src/codegenie/transforms/branch_writer.py` (S5-04) — produces `remediation-report.yaml` path on stdout.
  - `src/codegenie/audit/writer.py` (S1-07) — `meta.unexpected_exception` event type.

## Goal

Wire `codegenie remediate <repo> --cve <id>` and `codegenie recipes list` end-to-end with the seven documented exit codes (0/4/5/6/7/8/9), the tool-readiness check at startup, the operator-facing surfaces for `signal_escalate` (JSON + report section + stderr banner), and the top-level safety net that catches the one allowed `Exception` in Phase 3 and emits `meta.unexpected_exception` before re-raising.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` (or `src/codegenie/cli/remediate.py` if Phase 0 used a per-subcommand module pattern) implements `@cli.command("remediate")` with the full flag set: `<repo>` (positional Path), `--cve TEXT` (required, regex-validated `^CVE-\d{4}-\d{4,}$`), `--engine [ncu|openrewrite]` (default `ncu`), `--allow-policy-violations TEXT` (comma-separated list of violation type names), `--allow-test-network` (boolean flag), `--allow-stale-feeds` (boolean), `--strict` (boolean), `--auto-gather/--no-auto-gather` (default from config file), `--run-id TEXT` (default: ISO-8601 timestamp + random short-id).
- [ ] `@cli.command("recipes")` group with sub-command `list` accepting `--engine TEXT` (optional) and `--task TEXT` (default `vuln_remediation`); prints a table of registered recipes (id, engine, kind, applies-to languages, digest).
- [ ] **Tool-readiness check at CLI startup** — before invoking `remediate(...)`, the CLI verifies the required binaries are on `$PATH`: always `git`, `npm`, `ncu`; only when `--engine=openrewrite`, additionally `java`. Missing binary → exit 2 with a clear stderr message: `error: required binary 'X' not found on PATH (see docs/phases/03-vuln-deterministic-recipe/runbook.md)`.
- [ ] **Exit-code mapping at the CLI layer** — the CLI converts `RemediationReport.attempt.exit_code` to `sys.exit(...)` with the documented codes:

  | Code | Meaning | Trigger |
  |---|---|---|
  | 0 | success | green outcome, branch written |
  | 2 | tool readiness OR malformed CLI input | startup check fails OR `--cve` regex fails |
  | 4 | no_recipe | `selection.reason != "matched"` |
  | 5 | transform_fail | engine or resolver returned errors |
  | 6 | validation_fail | install/build/test failed without network signal |
  | 7 | policy_violation | `LockfilePolicyScanner` refused, no override |
  | 8 | signal_escalate | test failed with network-required signature |
  | 9 | auto_gather_failure | `StaleContextNotRefreshed` or `AutoGatherFailed` |

- [ ] **Top-level safety net** — the CLI wraps `remediate(...)` in exactly one `try/except Exception`. On any uncaught exception: (a) append `meta.unexpected_exception` audit event with `exception_type`, `exception_message`, `traceback` (truncated to first 4 KB), (b) write a partial `remediation-report.yaml` with `exit_code: 99` + `attempt.errors=[<exc-shape>]`, (c) print the stack trace to stderr, (d) `sys.exit(99)`. This is the **only** `except Exception` in Phase 3.
- [ ] **`signal_escalate` operator surface (Gap 3)** — on exit 8:
  - `.codegenie/remediation/<run-id>/escalation.json` is on disk (written by `validate` in S4-05).
  - `remediation-report.yaml` contains an `escalation` section with `signature_matched`, `suggested_flag: "--allow-test-network"`, `escalation_json_path`.
  - **stderr banner** — a multi-line block prefixed with `╔══ ESCALATION REQUIRED ══` (or equivalent; pick one stable string the runbook documents) summarizing what to do, including the suggested re-run command verbatim: `codegenie remediate <repo> --cve <cve> --allow-test-network`.
- [ ] **`--allow-stale-feeds` graded behavior** — when CVE-feed snapshot is > 90 days old and the flag is absent, exit 11; when present, the orchestrator runs and emits `cve.snapshot.stale_allowed` advisory event. (Exit 11 is reachable from `resolve_advisory`; this story tests the integration but the load-bearing test is on S2-07.)
- [ ] **`--allow-policy-violations` parsing** — comma-separated list parsed into a `frozenset[str]` of typed violation names (`RegistryRedirect`, `MissingIntegrity`, `LifecycleScriptDeclared`, `PublishConfigOverride`, `ResolutionsRedirect`). Unknown names → exit 2 with `error: unknown policy violation type 'X' (allowed: ...)`.
- [ ] **Structured logging discipline** — all CLI-emitted operator messages go to **stderr** as structured JSON via structlog (or human-readable mode for TTY). **Stdout** is reserved for ONE machine-parseable line at exit 0: the absolute path to `remediation-report.yaml`. CI consumers (Phase 11) read stdout; humans read stderr.
- [ ] **`codegenie recipes list`** — prints a rich-formatted table to stdout (or YAML if `--format yaml`). Columns: `id`, `engine`, `kind`, `languages`, `digest`. Default sort: by `id`. Empty result → empty table + exit 0 (NOT exit non-zero).
- [ ] **Integration tests** under `tests/integration/`:
  - `test_remediate_express_e2e.py` — happy path on express fixture; exit 0; branch on disk; `remediation-report.yaml` parseable; stdout = report path; stderr contains no banner.
  - `test_remediate_no_recipe_clean_skip.py` — exit 4; report's `attempt.transform_output is None`; stderr names `selection.reason="catalog_miss"`.
  - `test_remediate_install_fails.py` — bumped version fails `npm ci`; exit 6; report's `attempt.gate_outcome.validators[0].name == "install"`, `.passed == False`.
  - `test_remediate_pnpm_workspace.py` — exit 4 with `reason="unsupported_dialect"`; transform never invoked.
  - `test_remediate_yarn_classic.py` — exit 4 with `reason="unsupported_dialect"`.
  - `test_remediate_lockfile_policy_violation_blocked.py` — exit 7; banner names the violation type.
  - `test_remediate_lockfile_policy_violation_allowed.py` — same fixture + `--allow-policy-violations=RegistryRedirect` → exit 0.
  - `test_remediate_test_needs_network_escalates.py` — exit 8; `escalation.json` on disk; banner present on stderr; suggested-rerun command parseable.
- [ ] `tests/integration/test_remediate_unexpected_exception_safety_net.py` — inject a `RuntimeError` from inside `apply_transform`; CLI exits 99; `meta.unexpected_exception` event present in audit slice; partial report on disk.
- [ ] `tests/integration/test_remediate_cli_help_text.py` — `codegenie remediate --help` exit 0, contains every documented flag; `codegenie recipes list --help` exit 0.
- [ ] `tests/integration/test_remediate_tool_readiness_exit_2.py` — `npm` removed from `$PATH` → exit 2 with the documented stderr message.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing integration tests under `tests/integration/` (red).
2. Replace the S1-10 placeholder in `src/codegenie/cli.py` (or `cli/remediate.py`) with the real `@cli.command("remediate")` decorated function. Wire every flag with `click.option`.
3. Implement `_validate_cve_id(cve_id)` — regex `^CVE-\d{4}-\d{4,}$`; click-callback or pre-call validator.
4. Implement `_parse_policy_violations(value: str) -> frozenset[str]` — comma split + membership check against the closed set; raise `click.BadParameter` on unknown.
5. Implement `_check_tool_readiness(engine_choice) -> None` — `shutil.which("git")`, `shutil.which("npm")`, `shutil.which("ncu")`, conditional `shutil.which("java")` when `engine_choice == "openrewrite"`. Missing → `click.echo` to stderr + `sys.exit(2)`.
6. Implement `_build_config_from_flags(...) -> Config` — assembles the Pydantic `Config` (S5-03) from click's parsed flags + the loaded `~/.codegenie/config.yaml` defaults.
7. Implement the `_emit_escalation_banner(report) -> None` — when `attempt.exit_code == 8`, print the multi-line banner to stderr with the suggested re-run command. Banner string lives in a module constant `_ESCALATION_BANNER_TEMPLATE`.
8. Implement the top-level safety net — a single `try: report = remediate(...); except Exception as exc: ...` block; on success print `report.report_path` to stdout. The except block writes the partial report + appends `meta.unexpected_exception` + sys.exit(99).
9. Implement `recipes list` — load `RecipeRegistry`, filter by `--engine` and `--task`, format as table (or YAML), print to stdout.
10. Wire structlog: configure JSON-mode for non-TTY, human-mode for TTY. Every CLI emit uses structlog, not `print(..., file=sys.stderr)`.
11. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Integration tests under `tests/integration/`:

```python
# Test signatures only — no implementation.

def test_remediate_express_e2e_exits_0_and_writes_branch(cli_runner, fixture_express_bundle): ...
def test_remediate_no_recipe_exits_4_with_catalog_miss(cli_runner, fixture_unknown_package): ...
def test_remediate_install_fails_exits_6_with_install_validator_failure(cli_runner, fixture_breaks_npm_ci): ...
def test_remediate_pnpm_workspace_exits_4_with_unsupported_dialect(cli_runner, fixture_pnpm): ...
def test_remediate_yarn_classic_exits_4_with_unsupported_dialect(cli_runner, fixture_yarn): ...
def test_remediate_lockfile_policy_violation_blocked_exits_7(cli_runner, fixture_redirect): ...
def test_remediate_lockfile_policy_violation_allowed_with_flag_exits_0(cli_runner, fixture_redirect): ...
def test_remediate_test_needs_network_exits_8_writes_escalation_json(cli_runner, fixture_test_needs_db): ...
def test_remediate_test_needs_network_stderr_banner_present(cli_runner, fixture_test_needs_db): ...
def test_remediate_test_needs_network_banner_suggests_allow_test_network_flag(cli_runner, ...): ...
def test_remediate_auto_gather_failure_exits_9(cli_runner, stale_fixture_no_docker): ...
def test_remediate_unexpected_exception_exits_99_emits_meta_event(cli_runner, monkeypatch_inject_runtimeerror): ...
def test_remediate_tool_readiness_exit_2_missing_npm(cli_runner, monkeypatch_no_npm): ...
def test_remediate_tool_readiness_exit_2_missing_java_only_when_openrewrite(cli_runner, monkeypatch_no_java): ...
def test_remediate_invalid_cve_format_exits_2(cli_runner): ...
def test_remediate_unknown_policy_violation_type_exits_2(cli_runner): ...
def test_remediate_stdout_is_report_path_only_on_success(cli_runner, fixture_express_bundle): ...
def test_recipes_list_prints_table(cli_runner): ...
def test_recipes_list_filter_by_engine(cli_runner): ...
def test_recipes_list_empty_filter_exits_0(cli_runner): ...
def test_remediate_help_text_contains_every_documented_flag(cli_runner): ...
```

Run pytest; confirm failures (most fail at the click-app-doesn't-define-the-command layer, some fail at the assertion-on-stderr layer). Commit as red marker.

### Green — make it pass

Implement the click command per the outline. Keep `remediate` thin: parse flags → build Config → readiness check → invoke orchestrator → emit banner if escalation → print stdout report path → `sys.exit(exit_code)`. The `try/except Exception` safety net wraps the orchestrator call and ONLY the orchestrator call — every other CLI surface (readiness check, flag parsing) has its own typed `click.BadParameter` raises that click handles.

The escalation banner is a module-level template string; format with `cve_id`, `repo_root`, and the suggested flag. Test the literal banner string ("ESCALATION REQUIRED" is the canary the runbook indexes).

### Refactor — clean up

- Hoist `_EXIT_CODES` from S5-03 — re-import the same `MappingProxyType` so the CLI and orchestrator agree on the integer-to-name mapping. Tests reference both sites.
- Module docstring naming Gap 3 (escalation surface), Gap 6 (snapshot — read from `report.attempt.engine_availability`), Gap 7 (auto-gather → exit 9).
- Confirm structlog's JSON-mode vs human-mode toggle is keyed off `sys.stderr.isatty()`. CI logs are JSON; developer terminals are human-readable.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` (or `src/codegenie/cli/remediate.py`) | Replace S1-10 placeholder with the real `remediate` command |
| `src/codegenie/cli/recipes.py` | New (or extension) — `recipes list` subcommand |
| `src/codegenie/cli/_banner.py` | New — `_ESCALATION_BANNER_TEMPLATE` + `_emit_escalation_banner` |
| `src/codegenie/cli/_readiness.py` | New — `_check_tool_readiness` |
| `tests/integration/test_remediate_express_e2e.py` | New |
| `tests/integration/test_remediate_no_recipe_clean_skip.py` | New |
| `tests/integration/test_remediate_install_fails.py` | New |
| `tests/integration/test_remediate_pnpm_workspace.py` | New |
| `tests/integration/test_remediate_yarn_classic.py` | New |
| `tests/integration/test_remediate_lockfile_policy_violation_blocked.py` | New |
| `tests/integration/test_remediate_lockfile_policy_violation_allowed.py` | New |
| `tests/integration/test_remediate_test_needs_network_escalates.py` | New |
| `tests/integration/test_remediate_unexpected_exception_safety_net.py` | New |
| `tests/integration/test_remediate_tool_readiness_exit_2.py` | New |
| `tests/integration/test_remediate_cli_help_text.py` | New |
| `tests/integration/fixtures/` | Extended — minimum-viable fixtures for each integration test (full portfolio lands in S7-01) |

## Out of scope

- **Full ≥ 30 adversarial corpus** — handled by S7-02. This story ships the minimum-viable fixtures to drive the integration tests; S7-01 ships the canonical `.bundle` + `npm-resolution.json` portfolio + pinned mirror; S7-02 extends to ≥ 30.
- **`codegenie cve sync` CLI** — already shipped in S2-07 (CVE feed syncer); this story does not modify it. The placeholder in S1-10 is replaced by S2-07's work.
- **Determinism canary (5× byte-identical)** — handled by S7-03. The express e2e test runs once; the canary runs the same fixture 5× and asserts byte equality.
- **Perf canaries** — handled by S7-04 (hot-path p95 ≤ 30 s + cache-hit rate ≥ 70%).
- **Phase-2 regression hard-gate** — handled by S7-05.
- **Phase-4 handoff contract test** — handled by S7-06. This story produces the `remediation-report.yaml` Phase 4 consumes; S7-06 verifies a Phase-4-shaped consumer can read it without importing Phase-3 internals.
- **Runbook** — handled by S7-07. This story produces the operator-facing CLI surface; the runbook documents the surfaces (escalation flow, fixture rotation, gc policy stub).
- **`codegenie remediation gc`** — Phase-14 runbook stub (S7-07).
- **`--strict` calibration** — per `phase-arch-design.md §"Open questions" #10`, default `--strict` does not escalate `medium` confidence. This story implements the flag as a passthrough to `Config`; Phase 4 calibrates the behavior.

## Notes for the implementer

- **The integration tests are the load-bearing contract for the exit-code mapping.** Each row of the table corresponds to exactly one test. If the table changes (a new exit code is added, or a code is repurposed), the test file with the same name in the integration suite changes in the same PR. Adding a new exit code requires (a) updating S5-03's orchestrator, (b) updating this CLI, (c) adding the integration test, (d) updating the runbook in S7-07 — all four in one PR.
- **Stdout is the machine line; stderr is the human + structured log.** The integration test `test_remediate_stdout_is_report_path_only_on_success` is the canary. If you find yourself adding `click.echo("Remediating CVE-...")` to stdout, stop — that breaks Phase 11's CI consumer that reads stdout to find the report path.
- **The escalation banner string is in the runbook.** Per Gap 3, the operator runbook (S7-07) documents the banner text verbatim. Pick the string here, lock it in `_ESCALATION_BANNER_TEMPLATE`, and reference it from the runbook stub. Cross-link both directions in the comments. If a future contributor "improves" the banner string by paraphrasing, the runbook indexes a stale phrase — the integration test asserting the literal "ESCALATION REQUIRED" substring is the canary.
- **The top-level safety net is the ONE `except Exception` in Phase 3.** Every other layer propagates uncaught. If you find yourself adding `except Exception` to the orchestrator, the transform, or any helper — stop. The architecture commitment is "the CLI catches once; the orchestrator catches never." This makes the audit-event `meta.unexpected_exception` actually meaningful — it fires exactly once per run, exactly at the CLI boundary, with the full traceback.
- **Tool-readiness check uses `shutil.which`, not `subprocess.run`.** `shutil.which` is fast (no fork) and respects `$PATH` semantics. Avoid `subprocess.run(["which", "npm"])` — that's slower and forks the shell.
- **`--auto-gather/--no-auto-gather` default reads from config.** Per `phase-arch-design.md §"Open questions" #12`: default config file (`~/.codegenie/config.yaml` or `<repo>/.codegenie/config.yaml`) ships with `auto_gather: false`; developer shell convention overrides to `true`. The click flag's `default` should be `None` (tri-state), and `_build_config_from_flags` picks: CLI flag if set, else config-file value, else `False` (CI safe default).
- **`--run-id` default is `f"{utcnow_iso8601()}_{secrets.token_hex(4)}"`.** Deterministic enough for human eyes; collision-proof enough for the determinism canary (S7-03 uses an explicit `--run-id` per run to assert byte-equality across five runs).
- **`recipes list` is a small surface but the test for it is load-bearing for Phase 4.** Phase 4's RAG retrieval prompt will likely query the recipe registry for context. The `recipes list` output format is the canary — if the column set changes, Phase 4's parsing breaks. Keep the columns frozen: `id`, `engine`, `kind`, `languages`, `digest`. Adding a column requires an ADR amendment.
- **Per Rule 3 (Surgical Changes):** the click app structure was set by Phase 0/1/2; do not refactor the subcommand dispatch. Replace the S1-10 placeholder body with the real implementation; everything else stays. If the CLI uses `Click >= 8.1`'s decorator-only style, follow it; if it uses an older `click.Group()` + `cmd.add_command(...)` style, follow that. Conformance > taste (Rule 11).
- **Per Rule 12 (Fail loud):** when the `meta.unexpected_exception` path fires, the CLI must NOT silently exit 0 or 1. Exit 99, write the partial report, print the traceback. Operators debugging a real production-shape failure rely on this loudness.
