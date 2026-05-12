# Story S3-01 — `AnthropicClient` shim — transport-only retries, model pin, no app retry

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S2-01 (`OutputValidator` chain), S2-04 (`ApiKeyStore` OS-tiered)
**ADRs honored:** ADR-P4-004, ADR-P4-007, ADR-P4-010, ADR-P4-013, ADR-P4-011 (NG4 — no application retry)

## Context
The `AnthropicClient` shim is the only transport-layer Anthropic call site in Phase 4. It is wrapped by both `InProcessLeafLlmAgent` (S3-02) and `JailedLeafLlmAgent` (S3-05). Per ADR-P4-007, the model id is a versioned alias (`claude-sonnet-4-7@vuln_remediation`) resolved at startup from `llm/rates.yaml`; per NG4, only transport-level retries are allowed (≤ 3 on 5xx/529 with exponential backoff) — application-level retries and fallback models are explicitly forbidden so quality drift can't hide behind a working pipeline. On retry exhaustion the shim raises `LlmTransportError`, which the orchestrator translates to exit code 10 (`llm.upstream_unavailable`).

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 2. LeafLlmAgent` — failure-mode table + `LlmTransportError` shape; `§Edge cases #11` — upstream 5xx → exit 10.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — the Protocol both implementations satisfy.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007 — versioned alias resolution + rates.yaml.
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 — `ApiKeyStore.read()` callable only from `codegenie.llm.leaf_anthropic.*`.
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — `cost.llm.invoked` aggregation-key shape (consumed by S3-02 cost-ledger; surface here is `LlmResponse.cost_usd` + token counts).
- **Source design:** `../final-design.md §Synthesis ledger row "Retry policy in Phase 4"` — final pick `retry=0 application; transport ≤ 3`. `§Synthesis ledger row "Model pin format"` — versioned alias.
- **High-level impl:** `../High-level-impl.md §Step 3` bullet on `client.py`.

## Goal
Ship a single transport-layer Anthropic call site that pins the model via versioned alias, retries only on transport-class errors (≤ 3 with exponential backoff), and never invokes an application-level retry or fallback model.

## Acceptance criteria
- [ ] `src/codegenie/llm/leaf_anthropic/client.py` defines `AnthropicClient` with `__init__(api_key: str, model_alias: str, rates_path: Path)` and `messages_stream(request: LlmRequest) -> Iterator[StreamEvent]` (or equivalent SDK-shaped surface used by S3-02 / S3-05).
- [ ] Versioned alias (e.g. `claude-sonnet-4-7@vuln_remediation`) is resolved **at startup** from `llm/rates.yaml` to its dated model id; resolution failure raises `ModelAliasUnresolved` before any network call.
- [ ] Transport retry policy: at most 3 retries on HTTP 5xx and 529 with exponential backoff; **no retry** on 4xx, on `Plan`-validation failure, on `LlmOutputRejected`, or on any application-class error.
- [ ] On retry exhaustion raises `LlmTransportError` with the last status code and request id; downstream maps to exit 10.
- [ ] Request body sent over the wire carries `cache_control=ephemeral` on `system_blocks` and `few_shots_block` and **no** `cache_control` on `query_block` (consumed-by-S3-02 prompt-cache assertion; tested here too).
- [ ] `tests/unit/llm/test_anthropic_client_no_application_retry.py` exercises a cassette that returns one transport failure and asserts exit-10 with no retry loop beyond transport retries.
- [ ] `tests/unit/llm/test_anthropic_client_prompt_blocks.py` asserts `cache_control` shape on rendered request.
- [ ] ruff, ruff format, mypy strict on `src/codegenie/llm/leaf_anthropic/client.py`, and `pytest` for the two test files all pass.

## Implementation outline
1. Add `src/codegenie/llm/leaf_anthropic/__init__.py` (Phase-4-only package; fence-CI from Step 1 already forbids `anthropic` imports outside this package).
2. Create `client.py`. Resolve the versioned alias from `rates.yaml` once on `__init__`; raise `ModelAliasUnresolved` (subclass of `LlmConfigError`) if missing or expired.
3. Wrap `anthropic.Anthropic(api_key=...).messages.stream(...)` (or equivalent client API used elsewhere in Phase 4). Pass `system`, `messages`, `max_tokens`, `temperature=0`, `stop_sequences` from `LlmRequest`.
4. Implement transport-retry policy using either the SDK's built-in retry config (preferred — fewer foot-guns) or a thin wrapper that increments a `retry_count` counter and re-raises after 3 attempts. Backoff: `2 ** n` seconds with jitter.
5. Define `LlmTransportError` in `src/codegenie/llm/errors.py` (or wherever Step 2's error hierarchy lives) carrying `status_code`, `request_id`, `retries_attempted`.
6. Emit one `cost.llm.invoked` audit event per successful response with token counts and `cost_usd` (computed from `rates.yaml`). Do **not** emit on transport failure beyond a `cost.llm.transport_failure` event.
7. Wire `ApiKeyStore.read()` from S2-04 — `client.py` is one of the only call sites the call-stack-frame check permits.

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/unit/llm/test_anthropic_client_no_application_retry.py`
- `tests/unit/llm/test_anthropic_client_prompt_blocks.py`

```python
# test_anthropic_client_no_application_retry.py
import pytest
from codegenie.llm.errors import LlmTransportError
from codegenie.llm.leaf_anthropic.client import AnthropicClient

@pytest.mark.vcr  # cassette returns 3x 529 then 200; but for this test only 1x 5xx then validator-rejecting body
def test_single_transport_failure_does_not_loop_application_retry(rates_yaml, fake_api_key, recorded_5xx_then_invalid_plan):
    client = AnthropicClient(api_key=fake_api_key, model_alias="claude-sonnet-4-7@vuln_remediation", rates_path=rates_yaml)
    # Cassette: first response is 503, retried once at transport layer to a 200 whose body is
    # an INVALID plan. Validator failure must NOT trigger another application retry.
    with pytest.raises(LlmTransportError) as exc:
        # transport-layer triggers retry-then-exhaust scenario set up in cassette
        list(client.messages_stream(make_request()))
    assert exc.value.retries_attempted <= 3
    # Hard property: at most 1 transport attempt + 3 transport retries = 4 network calls. No 5th.
    assert recorded_5xx_then_invalid_plan.call_count <= 4
```

```python
# test_anthropic_client_prompt_blocks.py
def test_request_payload_marks_system_and_few_shots_ephemeral_only(monkeypatch, rates_yaml, fake_api_key):
    captured = {}
    monkeypatch.setattr("anthropic.Anthropic", _capture_send(captured))
    client = AnthropicClient(api_key=fake_api_key, model_alias="claude-sonnet-4-7@vuln_remediation", rates_path=rates_yaml)
    client.messages_stream(make_request_with_system_fewshots_query())
    sys_blocks = captured["payload"]["system"]
    assert all(b.get("cache_control") == {"type": "ephemeral"} for b in sys_blocks)
    fs = next(m for m in captured["payload"]["messages"] if m["role"] == "user" and m["content"][0]["text"].startswith("FEW_SHOTS"))
    assert fs["content"][0]["cache_control"] == {"type": "ephemeral"}
    query = captured["payload"]["messages"][-1]
    assert "cache_control" not in query["content"][0]
```

### Green
- Minimal `AnthropicClient` that resolves the alias, wires `ApiKeyStore.read()`, calls the SDK with the documented cache-control shape, and surfaces transport errors as `LlmTransportError`.
- Use SDK's native retry config to bound retries; fail loudly on any 4xx.

### Refactor
- Extract `_build_payload(request)` so prompt-block layout is testable in isolation.
- Add `from __future__ import annotations`, full type hints, docstrings citing ADR-P4-007 and NG4.
- Add audit emit hook (interface only here; full ledger writer lives in S3-02).
- Logging: only `request_id`, `model_id`, token counts, status. **Never** the API key (S2-04 ensures it isn't reachable to log; assert with a follow-up scan test stub).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/llm/leaf_anthropic/__init__.py` | New leaf-anthropic package (fence-CI scoped). |
| `src/codegenie/llm/leaf_anthropic/client.py` | The shim itself. |
| `src/codegenie/llm/errors.py` | `LlmTransportError`, `ModelAliasUnresolved` (extend existing module). |
| `src/codegenie/llm/configs/rates.sample.yaml` | Add the versioned alias example if absent. |
| `tests/unit/llm/test_anthropic_client_no_application_retry.py` | Red test 1. |
| `tests/unit/llm/test_anthropic_client_prompt_blocks.py` | Red test 2. |
| `tests/fixtures/cassettes/llm/test_anthropic_client_*.yaml` | Recorded fixtures (committed once `cassettes-reviewed` label applied — only for this story since S3-06 has not yet shipped the discipline. See "Notes for the implementer".) |

## Out of scope
- **Streaming parser with first-invalid-step cancellation** — handled by S3-03.
- **In-process agent / cost ledger writer** — handled by S3-02.
- **Jailed agent + bwrap launcher** — handled by S3-04 / S3-05.
- **Cassette discipline + canary rewrite hook** — handled by S3-06 (this story may commit a few stub cassettes; S3-06 retrofits them under the canonical content-addressed key).

## Notes for the implementer
1. **No application retry, ever.** If you find yourself adding a `try/except` around `messages_stream` that retries on `LlmOutputRejected` or `Plan` validation failure, stop — that is exactly what NG4 forbids. The orchestrator handles retry semantics in Phase 5 with Trust-Aware gates.
2. **Versioned alias resolution is startup-time, not per-call.** Resolving at startup means cassette regen is a one-shot when the alias bumps; per-call resolution would silently change the model mid-run.
3. **Cassette regen warning.** This is the first story that records LLM cassettes. S3-06 hasn't landed the canary-rewrite hook yet, so any cassette here must use a deterministic canary fixture (e.g. all-zero 32-byte hex) until S3-06 retrofits the hook. Mark TODO comments referencing S3-06.
4. **Fence-CI scope.** The `anthropic` import must live only in this file and in `in_process.py` (S3-02). Step 1's fence rule should already enforce this — if it doesn't, your import will fail CI and the fix is in the fence rule, not here.
5. **API key never logged.** Use the SDK's native `request_id` logger and explicitly omit headers from any log line you emit. S2-04's `test_no_api_key_in_logs.py` will scan your fixtures.
6. **Transport vs application boundary.** Anything Anthropic-side that returns a body — even an unusable body — is application-side; only network/5xx/529 may retry. When in doubt, do not retry.
