# Story S6-03 — Implement `loop resume` + `aupdate_state(as_node="await_human")`

**Step:** Step 6 — Ship `cli/loop.py` operator surface + workflow-id derivation + exit codes
**Status:** Ready
**Effort:** M
**Depends on:** S6-02
**ADRs honored:** ADR-0009 (cli/loop parallel — `cli/remediate.py` unmodified), ADR-0008 (HITL operator auth deferred to Phase 11), ADR-0001 (lazy-singleton `build_vuln_loop`)

## Context

When `loop run` exits with code `12` (paused at `interrupt_before=["await_human"]`), the operator's only forward path is `codegenie loop resume <thread_id> --decision continue|override|abort [--note "…"] [--operator <name>]`. `resume` constructs a `HumanDecision` Pydantic model (the typed HITL contract — ADR-0008 defers operator key authentication to Phase 11; in Phase 6 `operator` is a display name, not an authenticated identity), uses LangGraph's `graph.aupdate_state(config, {"human_decision": decision.model_dump(mode="json")}, as_node="await_human")` to inject the decision into the paused frame, and then calls `graph.ainvoke(None, config)` to continue execution. The single subtlety driving most of this story's acceptance criteria: `aupdate_state(..., as_node="await_human")` is the only way to mutate state into the resumed node such that LangGraph's checkpointer commits a new frame and the next `ainvoke(None, config)` re-enters the node body with `human_decision` populated. Get the `as_node=` value wrong — pass `as_node="route_after_human"` or omit `as_node` — and either LangGraph silently skips the frame or the predicate reads `None` and routes to abort. This story pins the canonical sequence and tests it against a frozen LangGraph version (pinned in `pyproject.toml` per `phase-arch-design.md §Implementation-level risks #2`).

`resume` also enforces a load-bearing CLI contract: **`--max-attempts` is not accepted on resume**. Phase 6 freezes `max_attempts` at graph-build time (ADR-0001); silently ignoring an operator's `--max-attempts 5` mid-run would be a surprising and dangerous behavior. The story includes a guard test (`test_loop_resume_no_pause_errors.py` from `final-design.md`'s G3 scenario).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 8. cli/loop.py — operator surface` lines 853–855 — canonical `resume` sequence: `aupdate_state(..., as_node="await_human")` then `ainvoke(None, config)`.
  - `../phase-arch-design.md §Process view — Scenario 2 (HITL paused → resume)` lines 432–446 — the full happy-path resume sequence after a 3rd consecutive failure.
  - `../phase-arch-design.md §Component design — 6. HumanRequest / HumanDecision / await_human` lines 767–816 — `HumanDecision` is `extra="forbid", frozen=True`; `action: Literal["continue","override","abort"]`; `note` is never flowed into Phase 4 prompts.
  - `../phase-arch-design.md §Harness engineering — Logging strategy` line 1062 — `HumanDecision.note` is logged on `await_human` resume only; never replicated into Phase 4 prompts (`test_hitl_note_not_in_prompt.py` enforces).
  - `../phase-arch-design.md §Implementation-level risks #2` — `langgraph` API-shape compatibility for `aupdate_state(..., as_node=...)`; pin `langgraph >= 0.2.x, < 0.3.x` in `pyproject.toml`.
  - `../phase-arch-design.md §Implementation-level risks #4` — `--max-attempts` on resume is rejected with a clear error.
  - `../phase-arch-design.md §Edge cases` — `route_after_human` reads `state.human_decision.action`; `"abort" → escalate`; `"override" → emit_artifact` (skip remaining gates); `"continue" → replan_with_phase4`.
- **Phase ADRs:**
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — `operator` is unauthenticated display name; do not gate, do not look up.
  - `../ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md` — `cli/remediate.py` byte-unchanged invariant continues into this story (test pinned in S6-01).
- **Existing code:**
  - `src/codegenie/cli/loop.py` (S6-02) — the `resume` stub is replaced with the live body; exit-code constants reused.
  - `src/codegenie/graph/hitl.py` (S1-03) — `HumanDecision(action, operator, decided_at, note)`; frozen Pydantic.
  - `src/codegenie/graph/checkpointer.py` (S2-01) — `make_checkpointer(workflow_id)` factory; same instance used by `run` and `resume`.
  - `src/codegenie/graph/nodes/await_human.py` (S4-08) — the resume entry point; `route_after_human` reads `state.human_decision.action`.
  - `langgraph.graph.StateGraph.aupdate_state` — the LangGraph method; consult `langgraph` docs for `as_node` semantics on the pinned version.

## Goal

`codegenie loop resume <thread_id> --decision continue|override|abort [--note "…"] [--operator <name>]` injects a typed `HumanDecision` into a paused workflow via `aupdate_state(..., as_node="await_human")`, calls `ainvoke(None, config)` to continue execution, and exits with the same 0/11/12/13/1 table; resume against a non-paused or non-existent thread errors with a clear message; `--max-attempts` is rejected with a CLI-level error.

## Acceptance criteria

- [ ] `loop resume` parses flags: `THREAD_ID` (positional, str — the 16-char workflow_id), `--decision` (required, `click.Choice(["continue","override","abort"])`), `--operator` (required, str), `--note` (optional, str ≤ 1024 chars).
- [ ] `--max-attempts` is **rejected by Click**: passing `--max-attempts N` on `resume` produces a non-zero exit with the message "ADR-0001: max_attempts is frozen at graph-build time; rerun `codegenie loop run` to change it." (acceptance test green).
- [ ] `resume` constructs `HumanDecision(action=<decision>, operator=<operator>, decided_at=datetime.now(UTC), note=<note or "">)` and `model_validate`-s it — invalid input (e.g., decision="approve" passed through a future shell alias) raises `ValidationError` and the CLI exits `1` with a clear message.
- [ ] `resume` builds the same checkpointer as `run` (`make_checkpointer(workflow_id=thread_id)`) and the same `build_vuln_loop(checkpointer=saver, max_attempts=<from-checkpoint>)`. **`max_attempts` is read from the persisted state**, never from a flag.
- [ ] `resume` calls `await graph.aupdate_state(config, {"human_decision": decision.model_dump(mode="json")}, as_node="await_human")` — `as_node="await_human"` is asserted by a `MagicMock.call_args` test, not just by code inspection.
- [ ] `resume` then calls `await graph.ainvoke(None, config)` (the `None` input is canonical for LangGraph resume from a checkpoint).
- [ ] The final-state-to-exit-code translator from S6-02 is reused; the five exit codes still apply to `resume` (e.g., `--decision continue` may itself lead to another `await_human` pause → exit 12).
- [ ] **No-pause-or-missing-thread errors clearly.** `tests/cli/test_loop_resume_no_pause_errors.py` covers three sub-cases:
  - [ ] Thread does not exist (no checkpoint file): exit `1`, stderr "no workflow found for thread_id=<id>".
  - [ ] Thread exists but is not paused (final state was `emit_artifact` / `escalate`): exit `1`, stderr "workflow already terminal (last_node=<x>)".
  - [ ] Thread exists, is paused, but `aupdate_state` raises (LangGraph API regression): exit `1`, stderr includes the LangGraph exception class name.
- [ ] **Malformed-decision adversarial.** `HumanDecision.model_validate({"action": "merge", ...})` raises `ValidationError`; `tests/adversarial/test_hitl_malformed_decision_raises.py` confirms (test placed here even though the schema landed in S1-03 — the CLI is where the malformed payload originates).
- [ ] **`continue` semantics.** After `aupdate_state` with `action="continue"`, the `await_human` node body resets `retry_count=0` (per S4-08); the resumed run reaches `replan_with_phase4` and produces a patch with `prior_attempts` length equal to the pre-pause `prior_attempts` length (the *attempts*, not the *retry counter*, are preserved per S4-08).
- [ ] **`override` semantics.** `action="override"` routes to `emit_artifact` (skips remaining gates); resumed run exits `0` and writes `report.json` with `events[-1].fields["operator"]==<operator>`.
- [ ] **`abort` semantics.** `action="abort"` routes to `escalate`; resumed run exits `11`.
- [ ] **`note` redaction.** `--note "PII; please ignore"` is logged at `await_human` resume only and is **never** present in any Phase 4 prompt; `tests/graph/test_hitl_note_not_in_prompt.py` (originally landed S4-05) is upgraded to also exercise the resume path with a `--note` value and assert the value is absent from the captured prompt.
- [ ] **Idempotent resume.** Calling `resume` twice with the same `thread_id` and same `--decision` is safe: the second call either (a) sees a terminal state and errors with the "already terminal" message (acceptable), or (b) silently no-ops if the state has not yet advanced past `await_human`. Test parametrizes both paths.
- [ ] **LangGraph version pin.** `pyproject.toml` constrains `langgraph >= 0.2.x, < 0.3.x` (replace `x` with the published minor at story-execution time). `tests/graph/test_langgraph_version_pin.py` asserts `importlib.metadata.version("langgraph")` falls in the pinned range.
- [ ] `mypy --strict src/codegenie/cli/loop.py` clean.
- [ ] TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. Replace the `resume` stub in `cli/loop.py` with a Click command:
   ```python
   @loop.command(name="resume")
   @click.argument("thread_id", type=str)
   @click.option("--decision", type=click.Choice(["continue", "override", "abort"]), required=True)
   @click.option("--operator", type=str, required=True)
   @click.option("--note", type=str, default="")
   @click.pass_context
   def resume(ctx, thread_id, decision, operator, note):
       _reject_max_attempts_flag(ctx)  # raises ClickException if --max-attempts present
       asyncio.run(_resume_async(ctx, thread_id, decision, operator, note))
   ```
2. `_reject_max_attempts_flag`: inspect `sys.argv` for `--max-attempts`; if present anywhere after `resume`, raise `click.ClickException("ADR-0001: max_attempts is frozen at graph-build time; rerun `codegenie loop run` to change it.")`. (Click doesn't natively reject unknown flags on subcommands without `--no-context-allow-extra-args=False`; the explicit check is the simplest path and the error message is operator-facing.)
3. `_resume_async`:
   1. Validate `len(thread_id) == 16` and hex; otherwise `ClickException("invalid thread_id format")`.
   2. `decision_obj = HumanDecision(action=decision, operator=operator, decided_at=datetime.now(UTC), note=note)` — `model_validate` is implicit; malformed `action` (impossible via Click) re-checked.
   3. `saver = make_checkpointer(workflow_id=thread_id)`; build `config = {"configurable": {"thread_id": thread_id}}`.
   4. `existing = await saver.aget_tuple(config)`; if `existing is None`: emit "no workflow found" + exit 1.
   5. Read `max_attempts` from `existing.checkpoint["channel_values"]["__root__"]["max_attempts"]`; build `graph = build_vuln_loop(checkpointer=saver, max_attempts=max_attempts)`.
   6. Inspect `existing.metadata` / next node: if state's `last_node` is `emit_artifact` or `escalate`, emit "already terminal" + exit 1.
   7. `await graph.aupdate_state(config, {"human_decision": decision_obj.model_dump(mode="json")}, as_node="await_human")`.
   8. Inside try/except (same exception → exit-code mapping as S6-02): `final = await graph.ainvoke(None, config)`; translate to exit code; emit terminal event.
4. Wire log redaction: `note` may only appear in the `await_human` resume log line, never in any other emit. The unit test `test_hitl_note_not_in_prompt.py` covers the negative.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/cli/test_loop_resume_aupdate_state.py`

```python
# tests/cli/test_loop_resume_aupdate_state.py
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.graph.hitl import HumanDecision


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


@pytest.fixture
def paused_thread_id() -> str:
    return "0123456789abcdef"


def test_resume_calls_aupdate_state_with_as_node_await_human(runner, paused_thread_id, paused_graph_fixture):
    fake_graph, fake_saver = paused_graph_fixture
    res = runner.invoke(cli, [
        "loop", "resume", paused_thread_id,
        "--decision", "continue", "--operator", "alice", "--note", "ok",
    ])
    # The single assertion that pins ADR-0001's `as_node` correctness:
    fake_graph.aupdate_state.assert_awaited_once()
    args, kwargs = fake_graph.aupdate_state.call_args
    assert kwargs.get("as_node") == "await_human" or args[2] == "await_human"
    payload = args[1] if len(args) >= 2 else kwargs["values"]
    assert payload["human_decision"]["action"] == "continue"
    assert payload["human_decision"]["operator"] == "alice"
    assert payload["human_decision"]["note"] == "ok"


def test_resume_then_invokes_ainvoke_with_none(runner, paused_thread_id, paused_graph_fixture):
    fake_graph, _ = paused_graph_fixture
    runner.invoke(cli, ["loop", "resume", paused_thread_id,
                        "--decision", "continue", "--operator", "alice"])
    # Second call: ainvoke(None, config)
    fake_graph.ainvoke.assert_awaited_once()
    args, _kwargs = fake_graph.ainvoke.call_args
    assert args[0] is None


def test_resume_rejects_max_attempts_flag(runner, paused_thread_id):
    res = runner.invoke(cli, [
        "loop", "resume", paused_thread_id,
        "--decision", "continue", "--operator", "alice",
        "--max-attempts", "5",
    ])
    assert res.exit_code != 0
    assert "frozen at graph-build time" in res.stderr.lower() or "max" in res.stderr.lower()


def test_resume_unknown_thread_id_errors_clearly(runner):
    res = runner.invoke(cli, ["loop", "resume", "deadbeefdeadbeef",
                              "--decision", "continue", "--operator", "alice"])
    assert res.exit_code == 1
    assert "no workflow found" in res.stderr.lower()


def test_resume_already_terminal_errors_clearly(runner, paused_thread_id, terminal_graph_fixture):
    res = runner.invoke(cli, ["loop", "resume", paused_thread_id,
                              "--decision", "continue", "--operator", "alice"])
    assert res.exit_code == 1
    assert "terminal" in res.stderr.lower()


@pytest.mark.parametrize("action,expected_exit", [
    ("continue", 0),    # happy: resumed run reaches emit_artifact
    ("override", 0),    # short-circuit to emit_artifact
    ("abort", 11),      # escalate
])
def test_resume_three_decision_paths(runner, paused_thread_id, paused_graph_fixture_routing,
                                     action, expected_exit):
    res = runner.invoke(cli, ["loop", "resume", paused_thread_id,
                              "--decision", action, "--operator", "alice"])
    assert res.exit_code == expected_exit


def test_resume_invalid_thread_id_format_rejected(runner):
    res = runner.invoke(cli, ["loop", "resume", "not-hex",
                              "--decision", "continue", "--operator", "alice"])
    assert res.exit_code != 0
    assert "thread_id" in res.stderr.lower() or "invalid" in res.stderr.lower()
```

Test file path: `tests/cli/test_loop_resume_no_pause_errors.py` — three sub-cases (missing, terminal, aupdate-failure).

Test file path: `tests/adversarial/test_hitl_malformed_decision_raises.py`:

```python
import pytest
from pydantic import ValidationError
from codegenie.graph.hitl import HumanDecision


def test_unknown_action_rejected():
    with pytest.raises(ValidationError):
        HumanDecision.model_validate({
            "action": "merge",  # not in the Literal Union
            "operator": "alice",
            "decided_at": "2026-05-12T00:00:00Z",
            "note": "",
        })
```

### Green — make it pass

Smallest implementation: ~80 LOC for the `resume` body + helpers. The `paused_graph_fixture` in `conftest.py` builds a `MagicMock` whose `aupdate_state` and `ainvoke` are `AsyncMock`s; the assertion is on `call_args`. For end-to-end paths, a thin `mock_phase345_resume_paths` parametrized fixture covers continue/override/abort.

### Refactor — clean up

- Extract `_load_paused_state(saver, config) -> CheckpointTuple | TerminalError` so the "unknown / terminal / paused" trichotomy is a single function with three return cases.
- Replace the `sys.argv` introspection for `--max-attempts` with a Click `eager` option that raises immediately if passed (avoids ordering quirks).
- Document the `as_node="await_human"` choice in a docstring citing `phase-arch-design.md §Component design — 8`.
- Ensure `note` never appears in any `log` call site outside the `await_human` resume emit (`grep`-style test in CI).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/loop.py` | Replace `resume` stub with live body; add `_load_paused_state`, `_reject_max_attempts_flag`. |
| `tests/cli/test_loop_resume_aupdate_state.py` | New — pins `as_node="await_human"` + `ainvoke(None, config)` shape. |
| `tests/cli/test_loop_resume_no_pause_errors.py` | New — three error sub-cases. |
| `tests/adversarial/test_hitl_malformed_decision_raises.py` | New — `HumanDecision(action="merge")` rejected (lifted from arch §Edge cases). |
| `tests/graph/test_hitl_note_not_in_prompt.py` | Upgrade — also exercise `--note` round-trip through `resume`. |
| `tests/graph/test_langgraph_version_pin.py` | New — `pyproject.toml` pin verification. |
| `pyproject.toml` | Pin `langgraph >= 0.2.x, < 0.3.x` (concrete minor at execution time). |
| `tests/cli/conftest.py` | Add `paused_graph_fixture`, `terminal_graph_fixture`, `paused_graph_fixture_routing`. |

## Out of scope

- Full HITL interrupt+resume integration test parametrized at `max_attempts ∈ {1,2,3}` against real Phase 3/4/5 engines — S7-01.
- Same-signature-flake `continue`-routes-to-`non_retryable` adversarial test — S7-04.
- Exporting `docs/contracts/hitl-v0.6.0.json` — S7-05.
- Forged-decision out-of-order transition tests — S10-01.
- `loop inspect | replay | render | migrate-checkpoint` — S6-04.

## Notes for the implementer

- **`as_node="await_human"` is the single most-load-bearing string in this story.** LangGraph silently no-ops on unknown `as_node` values in some versions — that's why the version pin in `pyproject.toml` and the `test_langgraph_version_pin.py` gate exist. If the pin needs to bump, that's a deliberate PR that updates the gate, runs S7-01's HITL integration test, and notes the LangGraph API-shape change in the PR description.
- `graph.ainvoke(None, config)` — the `None` is canonical. LangGraph reads from the checkpointer at `config["configurable"]["thread_id"]` and continues from the paused frame. Do not pass the `initial` ledger again.
- `max_attempts` is read from the **persisted state**, never from a flag. This is the operator-confusion guard (Risk #4 in arch §Implementation-level risks). The `--max-attempts` rejection is non-negotiable; do not soften it to a warning.
- ADR-0008 — `operator` is unauthenticated in Phase 6. Do not look it up in a registry, do not validate against a directory. Phase 11 adds the operator-key file; this story trusts whatever string the local-host operator types.
- `HumanDecision.note` is logged at the `await_human` resume emit and **nowhere else**. The redaction test in S4-05 verifies the negative against Phase 4's prompt; this story extends it through the `resume` CLI path.
- The "already terminal" branch is important: an operator who lost their terminal can't `resume` a completed run, but the error must be clear so they know `inspect` or `replay` is the right next move (S6-04).
- The `paused_graph_fixture` in `conftest.py` should reuse the S6-02 mocked-Phase-345 fixtures where possible; do not invent a new mocking shape unless the existing one is genuinely insufficient. Convention > taste (Rule 11).
- Resist adding a `--yes`/confirmation prompt on `--decision abort`. The CLI is for operators, not end users; one decision = one CLI invocation.
- `cli/remediate.py` byte-identity must still hold after this story merges. Verify locally with `shasum -a 256 src/codegenie/cli/remediate.py` before pushing.
