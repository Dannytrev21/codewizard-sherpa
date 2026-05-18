# Story S3-02 — `AnthropicLeafAdapter` with keyring-only key + retries + path-scoped fence assertion

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** L
**Depends on:** S3-01 (`LeafLlm` Protocol + `LeafResponse`), S2-05 (`BudgetToken`), S2-04 (`PromptBuilder` → `TrustedPrompt` + `FencedPromptBody`), S1-02 (`PlanProposal.model_json_schema()`), S1-05 (path-scoped fence admitting `anthropic` only under `src/codegenie/fallback/leaf/`)
**ADRs honored:** ADR-0001 (Phase 4 — schema-at-SDK-boundary), ADR-0003 (Phase 4 — path-scoped fence admits `anthropic` here and only here), ADR-0005 (Phase 4 — no SPKI pin; system trust), ADR-0010 (Phase 4 — `BudgetToken` keyword-only required), ADR-0020 (production — Protocol earns its keep here)

## Context

`AnthropicLeafAdapter` is the **single concrete `LeafLlm`** Phase 4 ships and the **sole** module in the codebase allowed to `import anthropic` — enforced both structurally (path-scoped fence test from S1-05; AST-walk in `tests/fence/test_only_leaf_imports_anthropic.py` landed here) and by `import-linter` (S1-06). Every Anthropic-SDK detail (caching strategy, response-format JSON schema, retry policy, key acquisition) lives here so the rest of Phase 4 sees only the `LeafLlm` Protocol seam.

Per `phase-arch-design.md §Component 4`:

- Key loaded from `keyring.get_password("codegenie", "anthropic_api_key")` → `SecretStr`. **No env-var fallback**, including no `CODEGENIE_ANTHROPIC_KEY_CI` (explicitly rejected by ADR-0005 §Consequences). Missing key → refuse-to-start with diagnostic pointing to `codegenie auth set`.
- System message assembled from three `CachedSystemBlock` records (`skill`, `instruction_template`, `rag_few_shot` when present), each `cache="ephemeral"`. The first two should hit Anthropic's prompt cache across consecutive workflows.
- The SDK call sets `response_format = schema.model_json_schema()` so Anthropic validates the `PlanProposal` shape before bytes ever reach Python.
- **One** in-call retry on JSON-parse failure, appending the instruction "your previous response was malformed; emit valid PlanProposal." Second failure → `LeafProtocolViolation`.
- **Three** in-adapter transport retries on `anthropic.APIStatusError` with backoff `1s, 4s, 16s`. **No other retries** — Phase 5's `GateRunner` owns the retry envelope at the workflow level (production ADR-0020 + ADR-0011 of Phase 3).
- The adapter wraps `EgressGuard.pinned_to("api.anthropic.com:443")` around the SDK call (S3-03 lands `EgressGuard`; this story imports `pinned_to` and pins its mock to it).

The two cassettes recorded during this story (LLM-from-scratch on `vuln-major-bump/express-cve-2026-1234`; RAG-hit on `vuln-rag-hit/express-rerun`) are the first cassettes in the repo. They must be sanitized (S3-04 hooks installed before recording) and entered into `cassettes.lock` (S3-05) — so this story is the **forcing function** that proves the discipline works end-to-end.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 4 — LeafLlm Protocol + AnthropicLeafAdapter` — internal structure, system-block assembly, retry policy.
  - `../phase-arch-design.md §Sequence: LLM-from-scratch` (lines ~229–266) and §Sequence: retry-bypass-RAG (~385+) — the leaf call's exact event-emission order.
  - `../phase-arch-design.md §Edge cases #7, #12, #16, #20` — invalid JSON retry, egress non-Anthropic host, transport retry schedule, missing keyring key.
  - `../phase-arch-design.md §Design patterns applied` — "Adapter at a hard trust boundary".
- **Phase ADRs:**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` §Decision — `response_format = PlanProposal.model_json_schema()`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — admits `anthropic` *only* under `src/codegenie/fallback/leaf/`; the fence test from S1-05 must pass after this story.
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` §Decision + §Consequences — system trust store; no env-var key fallback; nightly drift job is the canary.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` §Consequences — `BudgetToken` is **consumed but not reconciled** by the adapter; `LlmInvocationGuard.reconcile(...)` happens in `FallbackTier` (S6-01).
- **Production ADRs:**
  - `../../../production/adrs/0020-leaf-agents-sdk.md` — multi-vendor seam.
- **Source design:** `../final-design.md §Component 4 — LeafLlm`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/exec/` — Phase-0/2 subprocess discipline; no relevance to this story but the *spirit* (single typed boundary, no shell-out) applies to the SDK boundary.
  - `src/codegenie/logging.py` — `EventLog` shape for `LeafKeyLoaded`/`LeafInvoked`/`LeafReturned`/`LeafProtocolViolation` events. Mirror existing event id conventions (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`).
  - The S3-01 `LeafLlm` Protocol + `LeafResponse` model.
  - The S2-05 `BudgetToken` model.

## Goal

Land `AnthropicLeafAdapter` as the sole `anthropic` SDK importer in the codebase, wrap every call in `EgressGuard.pinned_to("api.anthropic.com:443")`, enforce schema-at-SDK-boundary via `response_format=PlanProposal.model_json_schema()`, honor the documented retry policy (1 in-call JSON retry, 3 transport retries with exponential backoff), and refuse-to-start when `keyring` returns no key — with the first two sanitized cassettes recorded against the live API.

## Acceptance criteria

### Adapter shape + key loading

- [ ] AC-1 — `src/codegenie/fallback/leaf/anthropic_adapter.py` exists; class `AnthropicLeafAdapter` implements the `LeafLlm` Protocol (mypy + runtime assertion `isinstance(adapter, LeafLlm)` not used — Protocol is not runtime-checkable; structural conformance proved by mypy + a positive type-test using `cast` or pyright assertion).
- [ ] AC-2 — `AnthropicLeafAdapter.__init__(self, *, event_log: EventLog, egress_guard: EgressGuard, model: ModelId = ModelId("claude-sonnet-4-5-20250929")) -> None` — `event_log` and `egress_guard` injected (testability); `keyring.get_password("codegenie", "anthropic_api_key")` called at `__init__`; returns `SecretStr`; raises `AnthropicKeyMissing` (typed exception, frozen Pydantic-or-attrs) if key is `None`. Diagnostic message includes the literal string `"codegenie auth set"`.
- [ ] AC-3 — Refuse-to-start emits `LeafKeyLoaded(present=False)` then raises; happy path emits `LeafKeyLoaded(present=True)` exactly once (no key bytes; no key prefix). Test asserts the audit log has zero entries whose serialized form contains `sk-ant` (defense-in-depth against accidental logging).
- [ ] AC-4 — **No env-var fallback path exists.** AST source-scan asserts the adapter does not reference `os.environ`, `os.getenv`, `getpass.getpass`, or any `CODEGENIE_*` string. Adversarial test sets `CODEGENIE_ANTHROPIC_KEY_CI=sk-ant-test` in env, `keyring` returns `None` → `AnthropicKeyMissing` still raises.

### Invoke semantics

- [ ] AC-5 — `async def invoke(self, system_prompt, user_message, *, schema, token)` constructs the SDK request with:
  - `response_format = schema.model_json_schema()` (the Pydantic-v2 export of `PlanProposal`).
  - `system` list assembled from three `CachedSystemBlock` records — `skill`, `instruction_template`, and (when `user_message` carries a RAG few-shot frame) `rag_few_shot`. Each block sets `cache_control={"type": "ephemeral"}`.
  - `messages=[{"role": "user", "content": user_message}]` — `user_message` is a `FencedPromptBody` (str-newtype); test asserts the bytes passed to the SDK are *exactly* the bytes of `user_message` (no string interpolation, no f-string, no `.format`).
- [ ] AC-6 — On successful 200 response, the adapter parses the JSON into `PlanProposal` (the SDK has already validated against the schema; this is a defensive parse), constructs a `LeafResponse`, and emits `LeafInvoked(prompt_digest_blake3)` *before* the SDK call and `LeafReturned(response_digest_blake3, tokens_in, tokens_out, cache_read, cache_creation)` *after*. Event order asserted.
- [ ] AC-7 — `prompt_digest_blake3` is `blake3(system[0].text + system[1].text + (system[2].text if present else "") + user_message)`; `response_digest_blake3` is `blake3(response.content[0].text)`. No raw prompt or response bytes appear in the event log.
- [ ] AC-8 — **`BudgetToken` is consumed but not validated against running totals here** — the adapter accepts the token as a typed function-signature requirement (S3-01 AC-2) but does not call `LlmInvocationGuard.reconcile`; reconciliation happens in `FallbackTier` (S6-01). Test: mock `LlmInvocationGuard.reconcile` and assert it is **not** called from `AnthropicLeafAdapter.invoke`.

### In-call malformed-JSON retry

- [ ] AC-9 — When the first SDK response cannot parse as `PlanProposal` (`pydantic.ValidationError`), the adapter appends to `user_message` the literal string `"\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."` and calls the SDK **exactly once more**. Second failure → `raise LeafProtocolViolation(first_error, second_error)`.
- [ ] AC-10 — Cassette-driven test (`tests/unit/fallback/test_leaf_adapter_malformed_retry.py`): first response is hand-crafted invalid JSON; second response is a valid `PlanProposalRefuse`. Assert exactly two SDK calls; assert returned `LeafResponse.plan.kind == "refuse"`; assert one `LeafProtocolViolation` is **not** emitted (only on second failure).
- [ ] AC-11 — Second-failure cassette test: both responses invalid JSON → `LeafProtocolViolation` raised; event `leaf.protocol_violation` emitted once; no `LeafReturned` event.

### Transport retries (1s / 4s / 16s)

- [ ] AC-12 — On `anthropic.APIStatusError` (5xx or rate-limit 429), the adapter retries with sleeps `[1.0, 4.0, 16.0]` seconds (three retries total = four SDK calls). After the fourth failure, the `APIStatusError` propagates *unwrapped* to the caller (Phase 5's `GateRunner` handles it). Test uses `unittest.mock.patch("asyncio.sleep")` to assert the exact sleep schedule.
- [ ] AC-13 — Non-`APIStatusError` exceptions (e.g., `EgressViolation` from `EgressGuard`, `LeafProtocolViolation` from AC-9) do **not** trigger transport retry; they propagate immediately.
- [ ] AC-14 — Transport retries only apply to the *outer* SDK call; the in-call malformed-JSON retry (AC-9) is independent (a malformed-JSON failure is **not** an `APIStatusError`).

### EgressGuard composition

- [ ] AC-15 — Every SDK call is wrapped in `async with self._egress_guard.pinned_to("api.anthropic.com:443"):`. Test installs a mock `EgressGuard` whose `pinned_to` context manager asserts `host == "api.anthropic.com:443"`; the test fails if any SDK call escapes the `async with`.

### Fence + import-linter

- [ ] AC-16 — `tests/fence/test_only_leaf_imports_anthropic.py` exists, AST-walks `src/codegenie/`, asserts the **only** file containing `import anthropic` or `from anthropic` is `src/codegenie/fallback/leaf/anthropic_adapter.py`. A deliberately-violating fixture (a test-only Python file under `tests/fence/fixtures/`) is verified to fail the fence walk so the test cannot pass vacuously.
- [ ] AC-17 — `make lint` and `make lint-imports` pass after this story; the path-scoped admission in S1-05 is what makes this possible. Re-run `tests/fence/test_pyproject_fence_phase4.py` — it must still be green.
- [ ] AC-18 — `make fence` (the existing Phase 0/2 fence job) is still green: the global `FORBIDDEN_LLM_SDKS` excludes `anthropic` per ADR-0003, but path-scoped admission means the *runtime closure* of any module **not** under `src/codegenie/fallback/leaf/` does not transitively pull `anthropic` — verified by S1-05's runtime-closure assertion.

### Cassettes (first two recorded)

- [ ] AC-19 — `tests/cassettes/anthropic/leaf_adapter_llm_from_scratch.yaml` and `tests/cassettes/anthropic/leaf_adapter_rag_hit_few_shot.yaml` are recorded against the live API (operator runs `make refresh-cassettes` from S3-06; the cassette discipline from S3-04 must already be installed in conftest). Each cassette is **scanned by `CassetteSanitizer` before write** — `Authorization`, `X-API-Key`, `Cookie`, `anthropic-version` are absent; no `sk-ant-` substring appears anywhere.
- [ ] AC-20 — Each cassette is entered into `tests/cassettes/anthropic/cassettes.lock` with its BLAKE3 (S3-05's manifest). `tests/security/test_cassettes_clean.py` passes against both cassettes.
- [ ] AC-21 — Replay-mode test (`record_mode="none"`) of both cassettes passes: `LeafResponse.plan.kind` matches the expected variant (`callsite_rewrite` for the major-bump scenario; the adapter returns the cassette-recorded `PlanProposal`).

### Cross-cutting

- [ ] AC-22 — `mypy --strict src/codegenie/fallback/leaf/` clean. `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-23 — TDD red test exists, was demonstrably failing before implementation, now green.

## Implementation outline

1. Add `anthropic>=X,<Y` and `keyring>=24,<26` to `pyproject.toml` `[project.dependencies]` (S1-05 already admitted them; pin the bounds — see open question §7 in manifest).
2. Create `src/codegenie/fallback/leaf/anthropic_adapter.py`:
   - Top-level `import anthropic` (the **one** allowed site).
   - `class AnthropicKeyMissing(Exception)` (or `Frozen` Pydantic if errors module exists) with the `codegenie auth set` diagnostic string.
   - `class LeafProtocolViolation(Exception)` carrying both error contexts.
   - `class CachedSystemBlock(BaseModel)` frozen-extra-forbid: `kind: Literal["skill", "instruction_template", "rag_few_shot"]`, `text: str`.
   - `class AnthropicLeafAdapter` with `__init__`, private `_load_key()`, private `_build_request(system_prompt, user_message, schema, has_few_shot)`, async `invoke(...)`, private `_call_sdk_with_transport_retry(request)`.
3. Implement the in-call malformed-JSON retry inside `invoke` (try parse; on `ValidationError` append the system note, call SDK once more, parse again or `raise LeafProtocolViolation`).
4. Implement transport retry as a small loop over `[1.0, 4.0, 16.0]` `await asyncio.sleep(s)` between attempts; `APIStatusError`-only.
5. Wrap the SDK call in `async with self._egress_guard.pinned_to("api.anthropic.com:443"):`.
6. Emit `LeafKeyLoaded` / `LeafInvoked` / `LeafReturned` / `LeafProtocolViolation` with BLAKE3 digests (use `codegenie.hashing.blake3` from Phase 0/1).
7. Land `tests/fence/test_only_leaf_imports_anthropic.py` + its deliberately-violating fixture.
8. Record the two cassettes via `make refresh-cassettes` (depends on S3-06 ergonomic; if S3-06 hasn't landed yet, this AC is parked until S3-06 is green).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_leaf_adapter.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from codegenie.fallback.leaf.anthropic_adapter import (
    AnthropicLeafAdapter,
    AnthropicKeyMissing,
    LeafProtocolViolation,
)


@pytest.mark.asyncio
async def test_init_refuses_when_keyring_returns_none(event_log_spy):
    egress = MagicMock()
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing) as exc:
            AnthropicLeafAdapter(event_log=event_log_spy, egress_guard=egress)
    assert "codegenie auth set" in str(exc.value)
    assert event_log_spy.entries[-1].id == "leaf.key_loaded"
    assert event_log_spy.entries[-1].fields["present"] is False


@pytest.mark.asyncio
async def test_init_does_not_fall_back_to_env(monkeypatch, event_log_spy):
    monkeypatch.setenv("CODEGENIE_ANTHROPIC_KEY_CI", "sk-ant-NOPE")
    egress = MagicMock()
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing):
            AnthropicLeafAdapter(event_log=event_log_spy, egress_guard=egress)


@pytest.mark.asyncio
async def test_transport_retry_schedule_is_1_4_16(monkeypatch, anthropic_sdk_mock):
    # ... arrange SDK to raise APIStatusError 3x, then succeed on the 4th call.
    sleeps: list[float] = []
    async def fake_sleep(s: float) -> None: sleeps.append(s)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    # ... invoke ...
    assert sleeps == [1.0, 4.0, 16.0]


@pytest.mark.asyncio
async def test_in_call_malformed_json_retries_exactly_once(anthropic_sdk_mock):
    # first response: invalid JSON; second response: valid PlanProposalRefuse.
    # assert exactly 2 SDK calls; assert returned plan.kind == "refuse"
    ...


def test_no_module_outside_leaf_imports_anthropic():
    # AST-walk src/codegenie/, asserting the only import is in anthropic_adapter.py
    ...
```

### Green — make it pass

Author the adapter file as outlined above; each test is the spec for one section.

### Refactor — clean up

- Extract `_build_system_blocks(...)` into a pure helper (functional-core/imperative-shell discipline).
- Move retry sleep schedule to a module-level `Final` tuple `_TRANSPORT_RETRY_BACKOFF_SECONDS: Final[tuple[float, ...]] = (1.0, 4.0, 16.0)`.
- Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"leaf.key_loaded", "leaf.invoked", "leaf.returned", "leaf.protocol_violation"})` validated at import time per Phase-1 ADR-0007.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Pin `anthropic` + `keyring` versions. |
| `src/codegenie/fallback/leaf/anthropic_adapter.py` | The adapter (this story's primary deliverable). |
| `tests/unit/fallback/test_leaf_adapter.py` | Init/refuse/retry/schema unit tests. |
| `tests/unit/fallback/test_leaf_adapter_malformed_retry.py` | In-call JSON-retry semantics. |
| `tests/unit/fallback/test_anthropic_response_format.py` | Asserts `response_format=PlanProposal.model_json_schema()`. |
| `tests/fence/test_only_leaf_imports_anthropic.py` | AST source-scan: only one importer of `anthropic`. |
| `tests/fence/fixtures/violating_anthropic_import.py.txt` | Deliberately-violating fixture (proves the fence walk catches violations). |
| `tests/cassettes/anthropic/leaf_adapter_llm_from_scratch.yaml` | Cassette 1 (records under S3-06 ergonomic; sanitized by S3-04 hooks). |
| `tests/cassettes/anthropic/leaf_adapter_rag_hit_few_shot.yaml` | Cassette 2 (same). |

## Out of scope

- `EgressGuard` implementation (S3-03; this story consumes the injected `egress_guard` but does not install it).
- `CassetteSanitizer` (S3-04; the hooks must already be installed for AC-19 to land — coordinate with S3-04).
- `cassettes.lock` walker (S3-05).
- `make refresh-cassettes` ergonomic (S3-06; AC-19 may be parked until S3-06 lands if executed strictly in order).
- `FallbackTier` composition (S6-01).
- Anthropic prompt-cache *measurement* (Phase 6.5).

## Notes for the implementer

- `anthropic.AsyncAnthropic` is the SDK entry point; pass `api_key=secret.get_secret_value()` only at the SDK boundary. Do not assign the cleartext to an attribute; keep it inside the SDK client.
- The `response_format` parameter is the post-2024 Anthropic API; if your pin is older verify the parameter name (you may need `response_format` vs `tool_use` shape).
- The two cassettes must be recorded with **real** Anthropic keys via `make refresh-cassettes` (S3-06). If S3-04's `before_record_request`/`before_record_response` hooks aren't yet installed in `conftest.py`, the cassettes will leak the `Authorization` header — coordinate S3-02 with S3-04 so the hooks land **before** the first recording session.
- `LlmInvocationGuard.reconcile(token, ...)` is called *not* here but in `FallbackTier.run(...)` (S6-01) after `await leaf.invoke(...)` returns — keep the adapter free of budget-state mutations so the capability flows through exactly two frames (ADR-0010 §Pattern fit).
- The transport-retry backoff `(1.0, 4.0, 16.0)` is *not* a jittered schedule; Phase 5's retry envelope adds jitter at the outer layer. Do not pre-emptively jitter here.
- C-extension residual: `anthropic`'s `httpx` transport uses Python's `socket` module (not a C `connect(2)`), so `EgressGuard` does catch it. The `import-linter` restriction on native-extension deps (ADR-0005 §Decision item 4) is the compensating control — verify the restriction list is non-empty before merging this story.
