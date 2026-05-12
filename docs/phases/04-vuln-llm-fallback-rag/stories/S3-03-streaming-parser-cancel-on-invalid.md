# Story S3-03 — Streaming parser with first-invalid-step cancellation

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`InProcessLeafLlmAgent`)
**ADRs honored:** ADR-P4-004, ADR-P4-008, ADR-P4-010

## Context
Anthropic responses arrive as a server-sent-event stream. If the model starts emitting an invalid `Plan` — wrong shape, missing canary echo, fence breakout, action-surface violation — every byte that arrives after the violation is wasted spend (max-tokens worth of partial output). This story extends the in-process agent's stream consumer to validate incrementally and cancel the stream the moment the first invariant breaks, so partial-output billing is **bounded** by the first-violation byte offset and no `raw.json` artifact is ever persisted for a cancelled stream. Closes critic §P max-tokens-burns-budget; encodes Edge case #5 at the byte level.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 2. LeafLlmAgent` (failure-mode: `LlmOutputRejected`); `§Edge cases #5` — invalid `Plan` → cancel + bill partial; `§Agentic best practices` — streaming-parser-cancel-first.
- **Phase ADRs:**
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — the invariants checked incrementally are exactly the structural defenses (extra forbid, canary, fence residual, action surface).
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — partial-output billing must still flow through L2 so the running total stays honest.
- **Source design:** `../final-design.md §Risks (top 5)` — "max_tokens burns budget on bad responses" is the exact risk being closed here.
- **High-level impl:** `../High-level-impl.md §Step 3` — bullet "Streaming parser with first-invalid-step cancellation".
- **Existing code:** `src/codegenie/llm/output_validator.py` (S2-01) — the synchronous validator; this story extracts an **incremental** validator that shares its rules.
- `src/codegenie/llm/leaf_anthropic/in_process.py` (S3-02) — extension point.

## Goal
Cancel an Anthropic streamed response at the first structural invariant violation so partial-output spend is bounded and no `raw.json` artifact ever lands on disk for a cancelled stream.

## Acceptance criteria
- [ ] `src/codegenie/llm/streaming_parser.py` exposes an `IncrementalPlanValidator` that consumes streaming bytes and raises `StreamCancelled(reason, byte_offset)` on the first violation.
- [ ] `InProcessLeafLlmAgent.invoke()` consumes the stream through `IncrementalPlanValidator`; on cancellation closes the underlying SDK stream (so no further tokens are billed beyond the cancellation point).
- [ ] On `StreamCancelled`, the cost-ledger entry records `output_tokens` equal to the bytes consumed up to cancellation (mapped to tokens via SDK's per-event token count); the entry is still appended (Edge case #5: "partial-output billed only").
- [ ] On `StreamCancelled`, **no `raw.json` is written**; `request.json` is still written for forensics.
- [ ] First-violation cancellation runs **before** any tool-side persistence (assertion: no `raw.json` on disk after `StreamCancelled`).
- [ ] `tests/unit/llm/test_streaming_parser_cancels_on_invalid_step.py` covers a synthetic stream with each of the four invariant violations (extra field, missing canary, fence residual, action-surface), asserts cancellation byte-offset and that downstream `LlmOutputRejected` is raised.
- [ ] `tests/unit/llm/test_no_artifact_on_stream_cancel.py` asserts no `raw.json` on disk when the stream is cancelled mid-flight.
- [ ] `tests/unit/llm/test_streaming_parser_partial_billing_recorded.py` asserts the cost-ledger JSONL line records partial tokens.
- [ ] ruff, ruff format, mypy strict on `src/codegenie/llm/streaming_parser.py`, pytest green.

## Implementation outline
1. Extract the synchronous `OutputValidator` rules into rule objects with a `feed(partial_text)` interface that can be re-used incrementally. Each rule either returns `Pending`, `Pass`, or `Fail(reason)`.
2. Implement `IncrementalPlanValidator`:
   - on each SDK stream event (`content_block_delta` / etc.), append the delta to a buffer;
   - feed rules deterministically in order: schema-shape (tolerant; only fires once enough JSON is materialized), canary substring scan (fires as soon as the suspect window is seen), fence residual scan (fires on any unmatched fence marker), action-surface check (fires once `target_files` array is closed);
   - first `Fail` raises `StreamCancelled(reason, byte_offset, partial_tokens)`.
3. `InProcessLeafLlmAgent.invoke()`:
   - wrap the SDK stream iteration in a `try`;
   - on `StreamCancelled`: call SDK's `stream.close()` (or equivalent) to stop billing; append cost-ledger entry with `output_tokens=partial_tokens`, `stop_reason="cancelled"`, `cancellation_reason=reason`; raise `LlmOutputRejected(reason)`.
   - on clean stream end: hand the assembled body to the synchronous `OutputValidator` for a final pass (defense in depth).
4. The cancellation path must run **before** the artifact dumper from S3-02; ensure `raw.json` write is in the success branch only.

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/unit/llm/test_streaming_parser_cancels_on_invalid_step.py`
- `tests/unit/llm/test_no_artifact_on_stream_cancel.py`
- `tests/unit/llm/test_streaming_parser_partial_billing_recorded.py`

```python
# test_streaming_parser_cancels_on_invalid_step.py
import pytest
from codegenie.llm.streaming_parser import IncrementalPlanValidator, StreamCancelled

@pytest.mark.parametrize("payload, reason_kind, expected_offset_lt", [
    (b'{"kind":"recipe_invocation","extra_forbidden_field":"x", ...', "extra_forbid", 80),
    (b'{"kind":"recipe_invocation","intent":"...","canary_echo":"deadbeef","rationale":"... <CANARY:abc123> ...', "canary_substring", 200),
    (b'{"kind":"manual_patch","manual_patch":{"diff":"```PROMPT_FENCE_42``` ... ','fence_residual', 120),
    (b'{"kind":"manual_patch","manual_patch":{"target_files":["package.json","../../../etc/passwd"]}', "action_surface", 200),
])
def test_each_invariant_violation_cancels_at_first_byte(payload, reason_kind, expected_offset_lt):
    v = IncrementalPlanValidator(expected_canary="f"*64, plan_schema_id="Plan/v1")
    with pytest.raises(StreamCancelled) as exc:
        for byte in chunked(payload, 16):
            v.feed(byte)
    assert exc.value.reason == reason_kind
    assert exc.value.byte_offset < expected_offset_lt  # bounded — not draining whole stream
```

```python
# test_no_artifact_on_stream_cancel.py
def test_no_raw_json_on_cancelled_stream(tmp_path, fake_invalid_stream, make_in_process_agent):
    agent = make_in_process_agent(remediation_root=tmp_path, stream=fake_invalid_stream)
    with pytest.raises(LlmOutputRejected):
        agent.invoke(make_request(run_id="r1"))
    assert not (tmp_path / "remediation" / "r1" / "llm" / "raw.json").exists()
    assert (tmp_path / "remediation" / "r1" / "llm" / "request.json").exists()
```

```python
# test_streaming_parser_partial_billing_recorded.py
def test_partial_output_tokens_recorded_in_cost_ledger(tmp_path, fake_stream_with_known_partial_tokens, make_in_process_agent):
    agent = make_in_process_agent(remediation_root=tmp_path, stream=fake_stream_with_known_partial_tokens(partial_tokens=37))
    with pytest.raises(LlmOutputRejected):
        agent.invoke(make_request(run_id="r1"))
    entry = json.loads((tmp_path / "remediation" / "r1" / "cost-ledger.jsonl").read_text().strip())
    assert entry["output_tokens"] == 37
    assert entry["stop_reason"] == "cancelled"
```

### Green
Minimal incremental validator with feed-rules + cancellation propagation. Use the SDK's per-event token counter to compute `partial_tokens` on cancellation.

### Refactor
- Extract `_close_stream_safely(stream)` so other agents (S3-05 jailed) reuse identical cancellation semantics.
- Add Hypothesis property test: any byte-prefix of a valid plan body must NOT cancel (no false positives mid-stream).
- Add docstring on `IncrementalPlanValidator` listing the four rule kinds and citing ADR-P4-008.
- Logging: include `cancellation_reason` at WARN level; redact buffer body — never log raw deltas at INFO.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/llm/streaming_parser.py` | The incremental validator. |
| `src/codegenie/llm/leaf_anthropic/in_process.py` | Wire `IncrementalPlanValidator` into `invoke()`. |
| `src/codegenie/llm/leaf_anthropic/_artifacts.py` | Cancellation path skips `raw.json`, still writes `request.json` + partial cost-ledger entry. |
| `tests/unit/llm/test_streaming_parser_cancels_on_invalid_step.py` | Red — four invariants. |
| `tests/unit/llm/test_no_artifact_on_stream_cancel.py` | Red — no artifact on cancel. |
| `tests/unit/llm/test_streaming_parser_partial_billing_recorded.py` | Red — partial billing. |

## Out of scope
- **Synchronous `OutputValidator` chain** — S2-01.
- **Server-side `response_format` JSON Schema vs JSON-mode fallback selection** — already in S3-02.
- **Jailed agent cancellation path** — S3-05 will reuse the same incremental validator via the file-based RPC; this story scopes to in-process.

## Notes for the implementer
1. **False-positive mid-stream is the failure mode to watch.** A JSON parser that fails on incomplete input would cancel every legitimate stream. The schema-shape rule must tolerate "pending" until enough body is materialized to decide. Use a permissive streaming JSON tokenizer.
2. **Cancellation must close the SDK stream.** Otherwise the SDK keeps draining server tokens and you keep paying. Both `messages.stream` context managers and `iter()` on the response object expose `close()` — call it.
3. **Cost-ledger entry still gets written.** Edge case #5 says partial billing is recorded; this is the only place where output_tokens < the model's emitted count is acceptable. Mark the entry `stop_reason="cancelled"` for downstream forensics.
4. **No raw.json, no exceptions.** Even a partial body that LOOKS plausible cannot land on disk — a future replay would mistake it for a valid response. The dumper must check `stop_reason != "cancelled"` before writing.
5. **Order rules deterministically.** If two rules fire in the same chunk (e.g. canary substring + fence residual), pick the one whose violation byte-offset is earlier so the cancellation reason is stable across runs.
6. **No new SDK retry surface.** If the SDK auto-retries on stream errors, disable that — cancellation is final.
