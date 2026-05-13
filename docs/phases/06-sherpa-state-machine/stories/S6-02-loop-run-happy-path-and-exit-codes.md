# Story S6-02 — Implement `loop run` happy path + structured exit codes

**Step:** Step 6 — Ship `cli/loop.py` operator surface + workflow-id derivation + exit codes
**Status:** Ready
**Effort:** M
**Depends on:** S6-01
**ADRs honored:** ADR-0009 (cli/loop parallel to cli/remediate — `cli/remediate.py` diff must remain empty), ADR-0001 (lazy-singleton `build_vuln_loop`), ADR-0006 (`AuditedSqliteSaver` per-workflow fsync), ADR-0007 (BLAKE3 chain extension)

## Context

`codegenie loop run <repo> --cve <id>` is the **happy-path operator entry** for the LangGraph vuln loop. It is the umbrella roadmap exit criterion — "the vuln-remediation loop runs as a LangGraph state machine" — wired end-to-end through actual Phase 3/4/5 engines (mocked or fixtured in tests; live in production). This story turns the S6-01 stub into a working invocation: derive `workflow_id`, build `AuditedSqliteSaver` at `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`, construct the initial `VulnLedger` (seeding `chain_head` from Phase 5's `RetryLedger.head_from_phase5(...)`), call `await build_vuln_loop(checkpointer=...).ainvoke(initial, config={"configurable": {"thread_id": workflow_id}})`, translate the final-state-or-paused-or-exception path into the five-code exit table (`0/11/12/13/1`), and toggle `--json` on stderr. The story also lands the **strongest ADR-0009 guard**: an acceptance criterion that the diff of `cli/remediate.py` post-merge is empty.

The exit-code table is the operator-observable contract: `0` (success / `emit_artifact`), `11` (`escalate` end-node), `12` (paused at `interrupt_before=["await_human"]`), `13` (one of `CheckpointTampered | CheckpointerInsecure | SchemaDrift | AuditChainCorrupted`), `1` (unexpected). Each is asserted independently by a parametrized test, and the structured-JSON stderr shape is pinned alongside.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 8. cli/loop.py — operator surface` lines 840–862 — the canonical exit-code table and `run`'s control flow.
  - `../phase-arch-design.md §Control flow — Happy path` lines 1011–1031 — step-by-step what `cli/loop.py:run()` must do (workflow_id derivation → checkpointer → initial ledger → `ainvoke` → final state).
  - `../phase-arch-design.md §Process view — Scenario 1 (happy)` lines 338–386 — the sequence the test fixture exercises.
  - `../phase-arch-design.md §Process view — Scenario 2 (HITL paused)` line 431 — `interrupt_before=["await_human"]` causes CLI to exit 12.
  - `../phase-arch-design.md §Harness engineering — Logging strategy` lines 1058–1068 — `--json` toggles structured stderr; redaction rules (no raw patch bytes, no LLM responses).
  - `../phase-arch-design.md §Harness engineering — Configuration` lines 1098–1107 — precedence; `--max-attempts 0` rejected at Pydantic parse time.
- **Phase ADRs:**
  - `../ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md` — **the single non-negotiable AC** of this story is "diff of `cli/remediate.py` post-merge is empty"; §Consequences §1 mandates the `tests/graph/test_cli_remediate_unchanged.py` CI gate landed in S6-01.
  - `../ADRs/0001-lazy-singleton-build-vuln-loop-factory.md` — `build_vuln_loop()` is module-cached; `run` must not pass `force_rebuild=True` (that's test-only).
  - `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — `make_checkpointer(workflow_id, ...)` factory is the seam; `run` uses the factory, never instantiates `AuditedSqliteSaver` directly.
  - `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — `chain_head` seeded from Phase 5's existing chain.
- **Existing code:**
  - `src/codegenie/cli/loop.py` (S6-01) — adds the `run` body on top of the stub; `derive_workflow_id` is reused.
  - `src/codegenie/graph/__init__.py` — `build_vuln_loop`, `VulnLedger` exports.
  - `src/codegenie/graph/checkpointer.py` (S2-01) — `make_checkpointer(workflow_id, base=Path(".codegenie/loop/checkpoints"))` factory.
  - `src/codegenie/gates/retry_ledger.py` (Phase 5) — `RetryLedger.head_from_phase5(run_id) -> bytes` accessor (verify exists per S2-02 Gap 2; if absent, surface and resolve as ADR amendment, not silent inline).
  - `src/codegenie/graph/hooks.py` (S1-04) — `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted` exception classes that map to exit 13.

## Goal

`codegenie loop run <repo> --cve <id> [--max-attempts N] [--checkpointer-db <path>]` runs the LangGraph vuln loop to completion against a real or fixtured repo, emits exit codes `0 | 11 | 12 | 13 | 1` per the canonical table, and a `--json` flag toggles structured-JSON stderr — **without touching `cli/remediate.py`**.

## Acceptance criteria

- [ ] `loop run` parses flags: `REPO` (positional, existing dir), `--cve` (required str), `--max-attempts` (optional int; rejected at parse time if `< 1`), `--checkpointer-db` (optional Path; defaults to `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`).
- [ ] Pydantic `Settings` model `LoopRunSettings(max_attempts: int = 3, ...)` rejects `--max-attempts 0` and `--max-attempts -1` at parse time with a clear error (G14 / Configuration §"non-config-conformant invocation rejected at CLI parse time, not at graph-build time").
- [ ] `run` invokes `derive_workflow_id(repo, advisory_canonical_id)` (S6-01 helper) where `advisory_canonical_id` comes from Phase 3's `AdvisoryLoader(...).load(cve).canonical_id`.
- [ ] `run` constructs `saver = make_checkpointer(workflow_id, base=checkpointer_db_dir)` (S2-01 factory); does **not** instantiate `AuditedSqliteSaver` directly.
- [ ] `run` constructs the initial `VulnLedger` with `chain_head` seeded from `RetryLedger.head_from_phase5(workflow_id)` (or the documented fallback if Gap 2 surfaces; surface, do not inline).
- [ ] `run` calls `asyncio.run(build_vuln_loop(checkpointer=saver, max_attempts=settings.max_attempts).ainvoke(initial, config={"configurable": {"thread_id": workflow_id}}))`.
- [ ] **Exit-code table (parametrized)** — `tests/cli/test_loop_exit_codes.py` covers each path:
  - [ ] `0` — final state's `last_node == "emit_artifact"` and `events[-1].kind == "exit"`; `report.json` exists on disk.
  - [ ] `11` — final state's `last_node == "escalate"` (terminal node reached after `HumanDecision.action="abort"` or unrecoverable path).
  - [ ] `12` — `GraphInterrupt` raised by LangGraph (`interrupt_before=["await_human"]` paused before `await_human` body); stderr prints "Paused at await_human; thread_id=<id>; run codegenie loop resume <id> --decision continue".
  - [ ] `13` — any of `CheckpointTampered | CheckpointerInsecure | SchemaDrift | AuditChainCorrupted` raised; stderr includes the exception class name.
  - [ ] `1` — any other exception type (catch-all); stack trace suppressed in non-`--json` mode and printed as `traceback` field in `--json` mode.
- [ ] **`--json` flag** — when set on the parent group (`codegenie loop --json run ...`), stderr is a single JSON object per terminal event with fields `{"event": "loop.exit", "exit_code": int, "workflow_id": str, "reason": str, "last_node": str | null}`. Without `--json`, stderr is human-readable (rich).
- [ ] **ADR-0009 hard gate** — `git diff origin/master -- src/codegenie/cli/remediate.py` is empty after this story merges. The `tests/graph/test_cli_remediate_unchanged.py` SHA-256 pin (S6-01) still matches; CI fails loudly if not. **This AC is non-negotiable.**
- [ ] **Happy-path integration** — `tests/cli/test_loop_run_happy.py` invokes `codegenie loop run ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM` against a fixture repo with Phase 3/4/5 mocked at module boundaries; asserts exit `0` and the existence of `report.json` under the fixture's `.codegenie/remediation/<run-id>/`.
- [ ] **Workflow_id flows through** — the LangGraph `config["configurable"]["thread_id"]` equals the derived workflow_id (verified by reading the checkpointer's `aget_tuple` after invocation).
- [ ] **Cold start is not regressed** — `import codegenie.cli.loop` does **not** trigger `build_vuln_loop` compile (the heavy import lives inside `run`'s body). Verified by `tests/cli/test_loop_import_does_not_compile.py` which patches `codegenie.graph.vuln_loop._build` to `MagicMock(side_effect=AssertionError)` and asserts the import is clean.
- [ ] **Redaction.** stderr never contains the bytes of any patch (only blake3 + path); never contains LLM response strings. `tests/cli/test_loop_run_redaction.py` greps stderr against fixtures.
- [ ] `mypy --strict src/codegenie/cli/loop.py` clean; no `Any`, no `cast`.
- [ ] `ruff check src/codegenie/cli/loop.py` clean.
- [ ] TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. Define exit-code constants at module top:
   ```python
   EXIT_OK = 0
   EXIT_ESCALATE = 11
   EXIT_PAUSED = 12
   EXIT_DURABILITY = 13
   EXIT_UNEXPECTED = 1
   ```
2. Define `LoopRunSettings(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=True)` and `max_attempts: int = Field(default=3, ge=1)`.
3. Body of `run`:
   1. Build `settings = LoopRunSettings(max_attempts=max_attempts or 3)` — catches `--max-attempts 0` via Pydantic.
   2. `advisory = AdvisoryLoader().load(cve)` (Phase 3); `workflow_id = derive_workflow_id(repo, advisory.canonical_id)`.
   3. `db_dir = checkpointer_db.parent if checkpointer_db else Path(".codegenie/loop/checkpoints")`.
   4. `saver = make_checkpointer(workflow_id, base=db_dir)` (factory enforces 0600 + WAL+NORMAL + chain seed).
   5. `chain_head = RetryLedger.head_from_phase5(workflow_id)`.
   6. `initial = VulnLedger(schema_version="v0.6.0", workflow_id=workflow_id, thread_id=workflow_id, repo_path=repo, advisory=advisory, chain_head=chain_head)`.
   7. `graph = build_vuln_loop(checkpointer=saver, max_attempts=settings.max_attempts)`.
   8. Inside a `try` block: `final = asyncio.run(graph.ainvoke(initial, config={"configurable": {"thread_id": workflow_id}}))`.
   9. Translate to exit code via `_exit_code_from_final_state(final)` (returns `EXIT_OK` if `last_node == "emit_artifact"`, `EXIT_ESCALATE` if `last_node == "escalate"`).
4. Exception → exit-code mapping:
   - `langgraph.errors.GraphInterrupt` → `EXIT_PAUSED`; emit "Paused at await_human; thread_id=…; resume hint" to stderr.
   - `CheckpointTampered | CheckpointerInsecure | SchemaDrift | AuditChainCorrupted` → `EXIT_DURABILITY`.
   - Anything else → `EXIT_UNEXPECTED`; full traceback only in `--json` mode (as a `traceback` field).
5. `_emit_terminal(ctx, exit_code, workflow_id, reason, last_node)`: if `ctx.obj["json"]`, dump JSON; else human-readable.
6. Invoke `sys.exit(exit_code)` at the end of `run`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/cli/test_loop_exit_codes.py`

```python
# tests/cli/test_loop_exit_codes.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from langgraph.errors import GraphInterrupt

from codegenie.cli import cli
from codegenie.graph.hooks import (
    CheckpointTampered, CheckpointerInsecure, SchemaDrift, AuditChainCorrupted,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


@pytest.fixture
def cve_fixture() -> Path:
    return Path("tests/fixtures/repos/cve-fixture")


def _run(runner: CliRunner, *args: str, json: bool = False) -> "Result":
    base = ["loop"]
    if json:
        base.append("--json")
    return runner.invoke(cli, [*base, *args], catch_exceptions=False)


def test_exit_0_on_emit_artifact(runner, cve_fixture, mock_phase345_happy):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM")
    assert res.exit_code == 0


def test_exit_11_on_escalate(runner, cve_fixture, mock_phase345_escalate):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM")
    assert res.exit_code == 11


def test_exit_12_on_paused_at_await_human(runner, cve_fixture, mock_phase345_pauses):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM")
    assert res.exit_code == 12
    assert "codegenie loop resume" in res.stderr


@pytest.mark.parametrize("exc", [
    CheckpointTampered("row mutated"),
    CheckpointerInsecure("mode=0644"),
    SchemaDrift("v0.6.0 -> v0.7.0"),
    AuditChainCorrupted("phase5 head mismatch"),
])
def test_exit_13_on_durability_exceptions(runner, cve_fixture, exc):
    with patch("codegenie.cli.loop._invoke_graph", side_effect=exc):
        res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM")
    assert res.exit_code == 13
    assert type(exc).__name__ in res.stderr


def test_exit_1_on_unexpected_error(runner, cve_fixture):
    with patch("codegenie.cli.loop._invoke_graph", side_effect=RuntimeError("boom")):
        res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM")
    assert res.exit_code == 1


def test_json_mode_emits_structured_terminal_event(runner, cve_fixture, mock_phase345_happy):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-2024-FAKE-NPM", json=True)
    payload = json.loads(res.stderr.strip().splitlines()[-1])
    assert payload["event"] == "loop.exit"
    assert payload["exit_code"] == 0
    assert payload["last_node"] == "emit_artifact"
    assert len(payload["workflow_id"]) == 16


def test_max_attempts_zero_rejected_at_parse_time(runner, cve_fixture):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-X", "--max-attempts", "0")
    assert res.exit_code != 0
    assert "max_attempts" in res.stderr or "max-attempts" in res.stderr


def test_max_attempts_negative_rejected(runner, cve_fixture):
    res = _run(runner, "run", str(cve_fixture), "--cve", "CVE-X", "--max-attempts", "-3")
    assert res.exit_code != 0
```

Test file path: `tests/cli/test_loop_import_does_not_compile.py`

```python
from unittest.mock import patch


def test_import_loop_cli_does_not_compile_graph():
    with patch("codegenie.graph.vuln_loop._build") as m:
        m.side_effect = AssertionError("import should not compile the graph")
        import codegenie.cli.loop  # noqa: F401
        assert m.call_count == 0
```

Test file path: `tests/cli/test_loop_run_happy.py` — full Phase 3/4/5-mocked invocation asserting exit 0 + `report.json` written.

### Green — make it pass

Smallest implementation: ~120 LOC. `_invoke_graph(graph, initial, config)` is a thin wrapper around `asyncio.run(graph.ainvoke(...))` so tests can patch a single seam without monkey-patching LangGraph. The exit-code translator is a single match-statement.

### Refactor — clean up

- Extract `_exit_code_for_terminal_node(last_node: str) -> int` so the mapping is a dict literal `{"emit_artifact": 0, "escalate": 11}`.
- Extract `_emit_terminal_event(ctx, **fields)` with both `--json` and rich branches.
- Add module docstring citing ADR-0009 ("diff of cli/remediate.py is empty post-merge") prominently.
- Verify `import codegenie.cli.loop` resolves without importing `codegenie.graph.*` at module top — only inside `run`'s body.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/loop.py` | Flesh out the `run` body; add `LoopRunSettings`, exit constants, terminal emitter. |
| `tests/cli/test_loop_exit_codes.py` | New — the parametrized 0/11/12/13/1 + `--json` table. |
| `tests/cli/test_loop_run_happy.py` | New — full mocked-Phase-345 happy-path integration; asserts exit 0 + `report.json`. |
| `tests/cli/test_loop_run_redaction.py` | New — stderr does not leak patch bytes or LLM responses. |
| `tests/cli/test_loop_import_does_not_compile.py` | New — cold-start guard. |
| `tests/cli/conftest.py` | Shared mocked-Phase-345 fixtures (`mock_phase345_happy`, `mock_phase345_escalate`, `mock_phase345_pauses`). |

## Out of scope

- `loop resume` body (S6-03).
- `loop inspect | replay | render | migrate-checkpoint` bodies (S6-04).
- HITL parametrized `max_attempts ∈ {1,2,3}` integration test (S7-01).
- Replay-after-kill multiprocessing canary (S8-01).
- Performance canary for `ainvoke` overhead (S9-01).
- `--operator` flag on `run` (only `resume` consumes it — S6-03).

## Notes for the implementer

- **The ADR-0009 byte-identity test (`tests/graph/test_cli_remediate_unchanged.py`) is your CI tripwire**, not a soft suggestion. If you find yourself wanting to "just add one line to `remediate.py`", stop and re-read ADR-0009 §Reversibility — the answer is no, even for a one-liner. The CLI surface split is load-bearing for Phase 7.
- The five exit codes are **mutually exclusive**: a paused-at-`await_human` run must never report exit 0, and a `CheckpointTampered` must never report exit 1. Encode this as a parametrized test that asserts the exit-code set is exactly `{0, 11, 12, 13, 1}`.
- `langgraph.errors.GraphInterrupt` is the canonical paused-state signal from `interrupt_before=["await_human"]`. Catch it specifically; do not catch the generic `BaseException` parent or you will mask exit 13's durability exceptions.
- `make_checkpointer(workflow_id, base=db_dir)` (S2-01 factory) is the single seam; never instantiate `AuditedSqliteSaver(...)` directly from `cli/loop.py` — that's Phase 9's swap point (`make_checkpointer` will return an `AuditedPostgresSaver` there).
- Phase 5's `RetryLedger.head_from_phase5(workflow_id)` may not exist as a public accessor (S2-02 Gap 2). If it doesn't, **surface the gap**, don't paper over it. Options documented in `phase-arch-design.md §Implementation-level risks #1`: (a) add the one-line public read accessor to Phase 5 (preferred), or (b) parse the chain JSONL directly and ship a Phase 6 ADR. Do not silently inline.
- `asyncio.run(...)` once at the top of `run`'s body is correct; do not call it nested. Click's command is sync; the async event loop is owned by this single call.
- Resist exposing `--force-rebuild` on `run` — that's a test-only flag on `build_vuln_loop`. Tests can monkey-patch `_COMPILED` if needed (S5-01 conftest helpers).
- Stderr structured-JSON output is **newline-delimited** (one JSON object per terminal event, last line is `loop.exit`). Don't pretty-print; JSON Lines is what Phase 13's cost ledger and Phase 16's audit pipeline will consume.
