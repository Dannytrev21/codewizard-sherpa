# Story S3-02 — `InProcessLeafLlmAgent` + telemetry dumps (raw.json, request.json, cost-ledger.jsonl)

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-01 (`AnthropicClient` shim), S2-02 (`PromptLoader` + YAML prompts), S2-03 (`LlmInvocationGuard` three layers)
**ADRs honored:** ADR-P4-004, ADR-P4-007, ADR-P4-008, ADR-P4-010, ADR-P4-013, ADR-P4-014

## Context
`InProcessLeafLlmAgent` is the macOS-default `LeafLlmAgent` implementation. It and `S3-01`'s `client.py` are the only two modules in the Phase 4 codebase that import the `anthropic` SDK — fence-CI from Step 1 enforces. It composes Step 2's primitives (`PromptLoader`, `OutputValidator`, `LlmInvocationGuard`, `ApiKeyStore`) with Step 3's `AnthropicClient`, calls `messages.stream(...)` with prompt-caching breakpoints, and emits the three on-disk telemetry artifacts Phase 5 will replay against: `raw.json` (raw Anthropic response), `request.json` (rendered request with canary redacted), and `cost-ledger.jsonl` (one JSONL line per `cost.llm.invoked` event in ADR-0024's `(workflow_id, stage, node, model)` aggregation-key shape).

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 2. LeafLlmAgent` — full Protocol shape + `LlmRequest`/`LlmResponse`; `§Process view` — call sequence; `§Agentic best practices` — telemetry dump invariants.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — Protocol contract; `InProcessLeafLlmAgent` must `isinstance(_, LeafLlmAgent)`.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — canary issuance + `OutputValidator` is consumed inside `invoke()`.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — L1 preflight and per-workflow running total.
  - `../ADRs/0014-langgraph-leaf-agent-node-minimal-wrap.md` — ADR-P4-014 — single-node LangGraph wrap (only if a LangGraph node is in scope here; otherwise document the seam Phase 6 will fill).
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — `cost.llm.invoked` aggregation-key shape (`workflow_id`, `stage`, `node`, `model`).
- **Source design:** `../final-design.md §Synthesis ledger row "Agent process boundary"` — in-process Phase 4 with `ApiKeyStore` discipline.
- **Existing code (if any):** `src/codegenie/llm/contract.py` (S1-01) — Protocol; `src/codegenie/llm/output_validator.py` (S2-01); `src/codegenie/llm/prompt_loader.py` (S2-02); `src/codegenie/llm/guard.py` (S2-03); `src/codegenie/llm/leaf_anthropic/client.py` (S3-01).

## Goal
Ship the macOS-default `LeafLlmAgent` that calls Anthropic in-process via the S3-01 shim, runs `OutputValidator` on the result, and writes the three replay artifacts to `.codegenie/remediation/<run-id>/llm/`.

## Acceptance criteria
- [ ] `src/codegenie/llm/leaf_anthropic/in_process.py` defines `InProcessLeafLlmAgent(LeafLlmAgent)` with `available()` and `invoke(request: LlmRequest) -> LlmResponse`.
- [ ] `tests/unit/llm/test_leaf_agent_protocol_satisfied.py` asserts `isinstance(InProcessLeafLlmAgent(...), LeafLlmAgent)` and that `JailedLeafLlmAgent` (importable shell from S3-05 stubs) type-checks against the Protocol via `runtime_checkable`.
- [ ] `invoke()` writes `.codegenie/remediation/<run-id>/llm/raw.json` (raw Anthropic JSON), `.codegenie/remediation/<run-id>/llm/request.json` (rendered request **with `canary_token` redacted to `<canary:redacted>`**), and appends one JSONL line per call to `.codegenie/remediation/<run-id>/cost-ledger.jsonl` with keys `workflow_id`, `stage`, `node`, `model`, `cost_usd`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `timestamp`.
- [ ] On macOS, `available()` returns `True` when `ApiKeyStore.read()` succeeds; on Linux, `available()` is `True` only when `--leaf=in_process` is the explicit selector, and emits `audit.warning(leaf_in_process_on_linux)` exactly once per process; covered by `tests/unit/llm/test_inprocess_on_linux_warn.py`.
- [ ] Two response-format branches (a) server-side `response_format` with JSON Schema for `Plan`; (b) fallback to JSON mode + client-side Pydantic validation — each branch has its own test; selection key is an init-time config flag.
- [ ] `LlmInvocationGuard.check_budget` runs preflight; `OutputValidator.validate(...)` runs on every response inside `invoke()` and any failure raises `LlmOutputRejected` without writing `raw.json` for the failed body (failed-validation case still writes `request.json` for forensic diff).
- [ ] ruff, ruff format, mypy strict on `src/codegenie/llm/leaf_anthropic/in_process.py`, and pytest for the three test files all pass.

## Implementation outline
1. Implement `InProcessLeafLlmAgent.__init__(client, prompt_loader, validator, guard, key_store, run_id, workflow_id, response_format_strategy)`.
2. `available()` — return `True` only when (`platform == "darwin"` and `key_store.read()` works) **or** (`platform == "linux"` and `selector == "in_process"`). Linux branch emits `audit.warning(leaf_in_process_on_linux)` via a one-shot lock.
3. `invoke(request)`:
   - call `guard.check_budget(request, remaining_budget_usd=...)` (L1);
   - render the payload (use `client.messages_stream(...)` from S3-01 to get the streaming iterator);
   - on success: parse JSON → call `validator.validate(text, expected_canary=request.canary_token, plan_schema=Plan)`;
   - on validator failure: raise `LlmOutputRejected`; record the (non-redacted) `request.json` for forensic diff, but **do not** persist `raw.json` for invalid bodies (Edge case #5);
   - on success: write `raw.json` and append one cost-ledger line; return `LlmResponse` populated from the raw response (token counts from response metadata, `cost_usd` computed from `rates.yaml`).
4. **Canary redaction:** `request.json` writer must replace `request.canary_token` with `<canary:redacted>` before writing. Reusable helper so other dumpers (S3-05 Jailed) can call it.
5. Add a `LangGraph` single-node wrap (`LeafAgentNode`) only if ADR-P4-014's seam is wired in this phase — otherwise stub the seam with a TODO referencing Phase 6.
6. Cost-ledger writer uses `fcntl.flock` for the append (multi-worker safe) and `os.fsync` after each line.
7. Two response-format branches share a single decode → validate pipeline; the branch difference is only the request payload shape (server-side `response_format` vs `system_prompt` carrying schema text + JSON mode).

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/unit/llm/test_leaf_agent_protocol_satisfied.py`
- `tests/unit/llm/test_inprocess_artifacts_written.py`
- `tests/unit/llm/test_inprocess_canary_redacted_in_request_json.py`
- `tests/unit/llm/test_inprocess_on_linux_warn.py`
- `tests/unit/llm/test_inprocess_validator_failure_no_raw_json.py`

```python
# test_leaf_agent_protocol_satisfied.py
from codegenie.llm.contract import LeafLlmAgent
from codegenie.llm.leaf_anthropic.in_process import InProcessLeafLlmAgent
from codegenie.llm.leaf_anthropic.jailed import JailedLeafLlmAgent  # importable shell post-S3-05

def test_inprocess_agent_satisfies_protocol(make_in_process_agent):
    agent = make_in_process_agent()
    assert isinstance(agent, LeafLlmAgent)

def test_jailed_agent_typechecks_against_protocol(make_jailed_agent):
    agent = make_jailed_agent()
    assert isinstance(agent, LeafLlmAgent)
```

```python
# test_inprocess_artifacts_written.py
def test_invoke_writes_raw_request_and_cost_ledger(tmp_path, recorded_happy_cassette, make_in_process_agent):
    agent = make_in_process_agent(remediation_root=tmp_path)
    agent.invoke(make_request(run_id="r1", workflow_id="wf1"))
    llm_dir = tmp_path / "remediation" / "r1" / "llm"
    assert (llm_dir / "raw.json").is_file()
    assert (llm_dir / "request.json").is_file()
    cl = (tmp_path / "remediation" / "r1" / "cost-ledger.jsonl").read_text().strip().splitlines()
    assert len(cl) == 1
    entry = json.loads(cl[0])
    assert entry["workflow_id"] == "wf1"
    assert entry["model"].startswith("claude-sonnet-4-7")
    for k in ("stage","node","cost_usd","input_tokens","output_tokens","cache_read_input_tokens","cache_creation_input_tokens","timestamp"):
        assert k in entry
```

```python
# test_inprocess_canary_redacted_in_request_json.py
def test_request_json_redacts_canary(tmp_path, recorded_happy_cassette, make_in_process_agent):
    agent = make_in_process_agent(remediation_root=tmp_path)
    canary = "f" * 64
    agent.invoke(make_request(run_id="r1", canary_token=canary))
    body = (tmp_path / "remediation" / "r1" / "llm" / "request.json").read_text()
    assert canary not in body
    assert "<canary:redacted>" in body
```

```python
# test_inprocess_on_linux_warn.py
def test_in_process_on_linux_emits_warning_once(monkeypatch, caplog, audit_log, make_in_process_agent):
    monkeypatch.setattr("sys.platform", "linux")
    agent = make_in_process_agent(leaf_selector="in_process")
    agent.available()
    agent.available()  # second call: no duplicate warn
    warns = [e for e in audit_log.events if e.kind == "leaf_in_process_on_linux"]
    assert len(warns) == 1
```

```python
# test_inprocess_validator_failure_no_raw_json.py
def test_validator_failure_does_not_write_raw_json(tmp_path, recorded_validator_failing_cassette, make_in_process_agent):
    agent = make_in_process_agent(remediation_root=tmp_path)
    with pytest.raises(LlmOutputRejected):
        agent.invoke(make_request(run_id="r1"))
    assert not (tmp_path / "remediation" / "r1" / "llm" / "raw.json").exists()
    assert (tmp_path / "remediation" / "r1" / "llm" / "request.json").exists()  # kept for forensics
```

### Green
Minimal implementation: thin orchestration over S3-01 + S2-01/02/03; serialize raw response straight to disk; redact in `request.json` writer; append cost-ledger line via flock'd writer.

### Refactor
- Extract `_dump_artifacts(raw, rendered_request, response, run_id, workflow_id)` to a helper module so S3-05's jailed implementation can reuse it.
- Add docstrings citing ADR-P4-004 (Protocol contract) and ADR-0024 (aggregation-key shape).
- Add property test stub for cost-ledger JSONL line shape (Hypothesis can fuzz integer token counts to ensure schema stability).
- Logging: never log full response body at INFO; DEBUG only.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/llm/leaf_anthropic/in_process.py` | Implementation. |
| `src/codegenie/llm/leaf_anthropic/_artifacts.py` | Shared artifact dumper (raw/request/cost-ledger). |
| `src/codegenie/llm/leaf_anthropic/__init__.py` | Export `InProcessLeafLlmAgent`. |
| `tests/unit/llm/test_leaf_agent_protocol_satisfied.py` | Red — Protocol membership. |
| `tests/unit/llm/test_inprocess_artifacts_written.py` | Red — telemetry dumps. |
| `tests/unit/llm/test_inprocess_canary_redacted_in_request_json.py` | Red — canary redaction. |
| `tests/unit/llm/test_inprocess_on_linux_warn.py` | Red — warn-once on Linux. |
| `tests/unit/llm/test_inprocess_validator_failure_no_raw_json.py` | Red — Edge case #5. |
| `tests/fixtures/cassettes/llm/...` | Recorded fixtures (stubs until S3-06 retrofits). |

## Out of scope
- **Streaming parser with first-invalid-step cancellation** — handled by S3-03.
- **Bwrap jail + EgressProxy** — handled by S3-04 / S3-05.
- **Cassette content-addressing + canary rewrite hook** — handled by S3-06.
- **`max_tokens` L2 enforcement** — already shipped by S2-03; this story consumes that surface.

## Notes for the implementer
1. **`raw.json` only on validated success.** Edge case #5 is explicit: invalid `Plan` → exit 9 with partial billing recorded, but no `raw.json` artifact. This is so a poisoned response can't be lying in the run dir to mislead a later replay.
2. **Two response-format branches both ship.** Server-side structured output is the preferred path; JSON mode + client-side validation is the fallback. Both branches need their own happy-path test — neither is dead code.
3. **Canary redaction is in the writer, not the caller.** Pass the un-redacted request to the dumper; the dumper redacts before write. Saves every future caller from forgetting.
4. **One audit warn per process on Linux in-process.** Use a process-local boolean, not a per-instance flag — multiple `InProcessLeafLlmAgent` instances per run are possible.
5. **Cost-ledger JSONL is append-only.** Flock-protected; one line per call. Phase 6's writeback reads this to attribute cost to the example.
6. **Do not import `anthropic` at module top.** Lazy import inside `__init__` if needed; otherwise let `client.py` own the dependency. Fence-CI watches.
