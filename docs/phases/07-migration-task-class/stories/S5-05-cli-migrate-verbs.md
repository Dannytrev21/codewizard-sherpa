# Story S5-05 — `cli/migrate.py` Click verbs + workflow_id scheme

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S5-04, S1-04
**ADRs honored:** ADR-P7-005 (parallel CLI verbs; no shared dispatcher; `cli/loop.py` not modified), ADR-P7-001 (parallel factory; CLI consumes it), Phase 6 ADR-0009 (CLI parallel pattern reused verbatim)

## Context

This story ships the operator entry point for the distroless task class. Per ADR-P7-005, `cli/migrate.py` is a **new file** parallel to Phase 6's `cli/loop.py`; `cli/loop.py` is **not edited** (Phase 6 exit criterion #14, preserved verbatim); `cli/sherpa.py` is **not coined** (Phase 8's supervisor will own it). Shared options (workflow_id derivation, advisory loading, audit-chain seeding) are *inlined* in `cli/migrate.py` rather than extracted to a `common.py` — the duplication is accepted, the refactor candidate is Phase 8.

The load-bearing decision in this story is the `workflow_id` derivation per arch §Gap 1: `workflow_id = blake3(f"{repo_root_blake3}|wf:distroless:{advisory_canonical_id or target_image}".encode())[:16]`. The `wf:distroless:` prefix prevents cross-task chain-head collisions with `wf:vuln:` workflows (S5-07 verifies). Phase 8's supervisor will use the prefix as the dispatch key.

Exit codes match Phase 6 exactly: `0` ok / `11` escalate / `12` paused at human / `13` checkpoint integrity violation / `1` unexpected.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 12 — cli/migrate.py` (lines 827–842) — exact Click command surface, `workflow_id` derivation, exit codes.
  - `../phase-arch-design.md §Gap 1 — Cross-task chain-head` (lines 1403–1407) — `wf:distroless:<sha>` prefix discipline.
  - `../phase-arch-design.md §Control flow §Dispatch (vuln vs distroless)` (lines 1143–1150) — no shared dispatcher in Phase 7; CLI seam is the dispatch.
  - `../phase-arch-design.md §Harness engineering` (lines 1154–1168) — logging strategy, `--json` flag, idempotence.
- **Phase ADRs:**
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-005 — verbatim: parallel verb, no shared dispatcher, inline shared options.
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 (transitively, since the loop's `replan_with_phase4` consumes it).
- **Production ADRs:**
  - `../../../production/adrs/0028-task-class-introduction-order.md` — extension-by-addition amendment; this story honors by adding a new file.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 16` — CLI dispatch home; `[B]` over `[P]`.
  - `../final-design.md §Architecture B-shape Open Q #5` — inline shared options.
- **Existing code:**
  - `src/codegenie/cli/loop.py` (Phase 6 S6-01..04) — mirror the Click `run/resume/inspect/replay/render` surface byte-for-byte where shape coincides. **Do not import from it** and **do not modify it**.
  - `src/codegenie/graph/distroless_loop.py` (S5-04) — the factory this CLI invokes.
  - `src/codegenie/graph/state_distroless.py` (S5-01) — the ledger this CLI constructs the initial instance of.
  - `src/codegenie/gates/retry_ledger.py` (Phase 5) — `head_from_phase5(...)` for the chain seed.
  - `src/codegenie/planner/fallback_tier.py` (S1-04) — the `task_type` kwarg is consumed *inside* the loop, not the CLI; the CLI need not pass `task_type` directly.

## Goal

Land `src/codegenie/cli/migrate.py` with the five Click verbs (`run`, `resume`, `inspect`, `replay`, `render`), the `workflow_id = blake3(...|wf:distroless:...)[:16]` derivation, and exit codes `0/11/12/13/1` matching Phase 6 — while leaving `src/codegenie/cli/loop.py` byte-identical pre- and post-merge.

## Acceptance criteria

- [ ] `src/codegenie/cli/migrate.py` exists and registers a `migrate` Click group with five subcommands: `run`, `resume`, `inspect`, `replay`, `render`.
- [ ] `codegenie migrate run <repo> --target distroless [--cve <id>] [--max-attempts N] [--dry-run] [--json]` invokes `build_distroless_loop(checkpointer=AuditedSqliteSaver(...)).ainvoke(initial_state, config)`.
- [ ] `workflow_id = blake3(f"{repo_root_blake3}|wf:distroless:{advisory_canonical_id or target_image}".encode())[:16]` — exact derivation per arch §Gap 1; the literal `"|wf:distroless:"` appears in source.
- [ ] Checkpoint path is `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` (different directory from vuln per arch §Physical view).
- [ ] Exit codes: `0` ok / `11` escalate / `12` paused at human / `13` checkpoint integrity violation / `1` unexpected. Each is asserted by a Click `CliRunner` test.
- [ ] `src/codegenie/cli/loop.py` is **byte-identical pre- and post-PR** — a CI test (`tests/integration/test_cli_loop_unchanged.py`) compares the file's BLAKE3 hash to a hard-coded value or to `master`.
- [ ] `codegenie migrate resume <thread_id> --decision continue|override|abort [--note "..."] [--operator <name>]` injects a `HumanDecision` into the checkpoint via the Phase 6 HITL contract (verbatim).
- [ ] `codegenie migrate inspect <thread_id>` pretty-prints `compiled.get_state_history(config)`.
- [ ] `codegenie migrate replay <thread_id> [--from <checkpoint_id>]` re-runs from a chosen checkpoint frame.
- [ ] `codegenie migrate render --out <path>` writes the topology graph (the same content as the S5-04 golden, but operator-facing).
- [ ] The Click entry point is registered under `codegenie` (e.g., `cli/__init__.py` adds `cli.add_command(migrate)`) — *via additive registration, not by editing `cli/loop.py`*.
- [ ] `tests/unit/cli/test_migrate_cli.py` exercises every Click verb, exit code, and the `--json` flag.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli/migrate.py`, and `pytest tests/unit/cli/test_migrate_cli.py` all pass.

## Implementation outline

1. Mirror `src/codegenie/cli/loop.py` structure — Click `Group`, five subcommand decorators. Do *not* `from codegenie.cli.loop import ...`; copy the option/handler shapes by reading.
2. `run` subcommand: parse `<repo>`, `--cve`, `--target distroless`, `--max-attempts`, `--dry-run`, `--json`; compute `repo_root_blake3 = blake3_of_repo(repo)`; compute `workflow_id`; construct `AuditedSqliteSaver(Path(f".codegenie/migration/checkpoints/{workflow_id}.sqlite3"))`; construct initial `DistrolessLedger` with `chain_head=RetryLedger.head_from_phase5(...)` seed; call `build_distroless_loop(checkpointer=...).ainvoke(initial, config)`; map outcome to exit code.
3. `resume` subcommand: load checkpoint at `<thread_id>`; build `HumanDecision(action=..., note=..., operator=...)`; inject via the Phase 6 HITL contract (`AuditedSqliteSaver.aupdate_state(...)` per Phase 6); re-invoke the compiled graph.
4. `inspect` subcommand: open the checkpointer; iterate `get_state_history(config)`; pretty-print each frame's `next` nodes + ledger snapshot (redact `chain_head` to first 8 hex chars for human readability).
5. `replay` subcommand: read `--from <checkpoint_id>`; build a config with `checkpoint_id` set; invoke the loop from that frame.
6. `render` subcommand: call `build_distroless_loop(InMemorySaver(), force_rebuild=True).get_graph().draw_mermaid()` and write to `--out` path.
7. Add a `tests/integration/test_cli_loop_unchanged.py` that BLAKE3-hashes `cli/loop.py` and compares against a fixed digest (or against the file's content at `master`).
8. Tests written failing first.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file: `tests/unit/cli/test_migrate_cli.py` (Click `CliRunner` driven).

```python
from click.testing import CliRunner
from codegenie.cli.migrate import migrate


def test_migrate_run_exit_0_on_happy_path(tmp_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_repo)
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(tmp_repo), "--target", "distroless", "--cve", "CVE-2025-XXXX"])
    assert result.exit_code == 0


def test_migrate_run_exit_12_on_paused_at_human(tmp_repo: Path, monkeypatch) -> None:
    """Per arch §Component 12 — exit code 12 = paused_at_human."""
    with _stub_loop_to_pause_at_human():
        runner = CliRunner()
        result = runner.invoke(migrate, ["run", str(tmp_repo), "--target", "distroless"])
        assert result.exit_code == 12


def test_migrate_run_exit_11_on_escalate(tmp_repo: Path, monkeypatch) -> None:
    with _stub_loop_to_escalate():
        runner = CliRunner()
        result = runner.invoke(migrate, ["run", str(tmp_repo), "--target", "distroless"])
        assert result.exit_code == 11


def test_migrate_run_exit_13_on_checkpoint_tampered(tmp_repo: Path) -> None:
    with _stub_checkpoint_tampered():
        runner = CliRunner()
        result = runner.invoke(migrate, ["run", str(tmp_repo), "--target", "distroless"])
        assert result.exit_code == 13


def test_migrate_run_exit_1_on_unexpected_error(tmp_repo: Path) -> None:
    with _stub_unexpected_exception():
        runner = CliRunner()
        result = runner.invoke(migrate, ["run", str(tmp_repo), "--target", "distroless"])
        assert result.exit_code == 1


def test_workflow_id_uses_wf_distroless_prefix() -> None:
    """ADR-P7-005 / arch §Gap 1 — workflow_id must include `|wf:distroless:` literal."""
    src = (REPO_ROOT / "src/codegenie/cli/migrate.py").read_text()
    assert '"|wf:distroless:"' in src or "'|wf:distroless:'" in src or "|wf:distroless:" in src


def test_workflow_id_blake3_truncated_to_16() -> None:
    """The derivation is blake3(...)[:16]; verify by computing in test."""
    from codegenie.cli.migrate import _derive_workflow_id  # exposed for testing
    wid = _derive_workflow_id(
        repo_root_blake3="a" * 64,
        advisory_canonical_id="CVE-2025-XXXX",
        target_image=None,
    )
    assert len(wid) == 16
    # And differs from the vuln derivation
    from codegenie.cli.loop import _derive_workflow_id as vuln_derive
    vuln_wid = vuln_derive(repo_root_blake3="a" * 64, advisory_canonical_id="CVE-2025-XXXX")
    assert wid != vuln_wid


def test_cli_loop_byte_identical_to_master() -> None:
    """ADR-P7-005 — Phase 6 cli/loop.py is byte-identical pre- and post-PR."""
    expected_blake3 = "<pin the master hash here>"
    actual = hashlib.blake3((REPO_ROOT / "src/codegenie/cli/loop.py").read_bytes()).hexdigest()
    assert actual == expected_blake3, (
        "cli/loop.py was modified — Phase 6 exit criterion #14 + ADR-P7-005 violation"
    )
```

Run; confirm all fail. Commit.

### Green — make it pass

Author `cli/migrate.py` with the five subcommands; expose `_derive_workflow_id` as an internal helper for testability. Mirror `cli/loop.py`'s control-flow shape; inline the workflow_id derivation, advisory loading, and audit-chain seeding (per ADR-P7-005 / final-design.md §Architecture B-shape Open Q #5).

Register under the top-level CLI group via `cli/__init__.py` *additively* — add `cli.add_command(migrate)` after the existing `cli.add_command(loop)`. Do not reorder.

### Refactor — clean up

- Add module docstring citing arch §Component 12 + ADR-P7-005; explicitly note "Phase 6 `cli/loop.py` not edited; shared options inlined per ADR-P7-005".
- Add `--json` flag support: structured JSON to stdout when set; plain text otherwise (per arch §Harness engineering).
- Operator-facing stderr is human-readable; auth errors map to `RegistryAuthFailed` from `tools/buildkit.py` with a link to Chainguard auth docs (Edge case #7).
- Per cross-cutting determinism: no `random` (use the `workflow_id` BLAKE3 derivation); no `time` (use Pydantic's `datetime` types in `MigrationReport`).
- Per `CLAUDE.md` Rule 12 ("Fail loud"): unknown advisory schema, missing `repo_path`, non-git repo — all raise loud, not silent exit 1.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/migrate.py` | NEW — Click verbs, `workflow_id` derivation, exit codes. |
| `src/codegenie/cli/__init__.py` | UPDATE — `cli.add_command(migrate)` additive registration. |
| `tests/unit/cli/test_migrate_cli.py` | Click CliRunner tests for every verb + exit code + `--json`. |
| `tests/integration/test_cli_loop_unchanged.py` | Byte-identity assertion on `cli/loop.py`. |

## Out of scope

- **Factory (`build_distroless_loop`)** — owned by S5-04.
- **Node bodies** — owned by S5-02, S5-03.
- **E2E test** — owned by S5-06.
- **Cross-task chain-no-collision integration test** — owned by S5-07.
- **Replay-after-SIGKILL test** — owned by S5-08.
- **`cli/loop.py` edits** — explicitly forbidden by ADR-P7-005 / Phase 6 exit criterion #14.
- **`cli/sherpa.py`** — Phase 8 owns it.
- **Operator notes / README updates** — deferred to S8-04 (operator-notes optional).
- **GitHub PR opening** — Phase 11.
- **Cost ledger output (`migration-report.yaml` `cost` fields)** — `emit_artifact` (S5-03) writes them; this story consumes them via outputs.

## Notes for the implementer

- **`cli/loop.py` must be byte-identical** post-merge. The `test_cli_loop_unchanged.py` assertion is the mechanical check. If you find yourself thinking "a tiny refactor here would DRY two CLI files" — *stop*. The duplication is *accepted* per ADR-P7-005 / final-design.md §Architecture B-shape Open Q #5; Phase 8 unifies. CLAUDE.md Rule 2 ("Simplicity First") + Rule 3 ("Surgical Changes") apply.
- **The `wf:distroless:` prefix is load-bearing** for Phase 8's supervisor dispatch (arch §Gap 1). Phase 8 splits on the prefix to choose `build_vuln_loop` vs `build_distroless_loop`. Pin the literal in source so an Phase 8 audit can `grep` it.
- **The `<workflow_id>` BLAKE3 derivation is content-addressed** — same repo + same advisory + same target image → same workflow_id → same checkpoint file → resumable. Per arch §Harness engineering "Idempotence". Use `blake3` library, *not* `hashlib.blake2b`.
- **Exit codes match Phase 6 exactly** (`0/11/12/13/1`). Operators using both CLIs see consistent exit semantics. This is the Phase 8 supervisor's prep — it will translate exit codes uniformly.
- **`AuditedSqliteSaver` is the Phase 6 checkpointer ABC** — same class instantiated against a different file path. The BLAKE3 chain extension semantics are unchanged; the per-workflow SQLite at `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` is the only difference from Phase 6.
- **`chain_head=RetryLedger.head_from_phase5(...)`** — Phase 5's accessor for the audit-chain seed. Per `phase-arch-design.md §Gap 1`, the chain file is per-`<run-id>` under `.codegenie/migration/<run-id>/audit/`; the cross-task collision test (S5-07) verifies the disjoint directory structure.
- **`HumanDecision` injection for `resume`** uses the Phase 6 HITL contract verbatim. Do not re-define `HumanDecision`; import from `codegenie.graph.hitl` (Phase 6).
- **`--dry-run`** skips the `ainvoke` and instead prints the initial ledger + the matched recipe + the target image, exiting 0. Per arch §Component 12.
- **Per `CLAUDE.md` Rule 8 ("Read before you write")**: read `cli/loop.py` end-to-end first. Note the option ordering, the JSON-output formatting, the exception-to-exit-code mapping. Mirror — do not reinvent.
- **Per `CLAUDE.md` Rule 11**: match the codebase's conventions (Click's `@click.group()` + `@click.command()`, not argparse).
