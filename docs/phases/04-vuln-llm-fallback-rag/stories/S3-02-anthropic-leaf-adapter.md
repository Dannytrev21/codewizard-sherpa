# Story S3-02 — `AnthropicLeafAdapter` with keyring-only key + retries + path-scoped fence assertion

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Done — GREEN 2026-05-24 (phase-story-executor; see [`_attempts/S3-02.md`](_attempts/S3-02.md) for the per-AC evidence table + gate log — `AnthropicLeafAdapter` lands at `src/codegenie/fallback/leaf/anthropic_adapter.py` (~430 lines: local `EgressGuardPort` Protocol, `AnthropicKeyMissing` / `LeafProtocolViolation` exceptions, 8 pure helpers, `__slots__`-bound `AnthropicLeafAdapter` with 4 emit-event helpers, 1 `_load_key`, 1 `_build_request`, 1 `_parse_response`, 1 transport-retry SDK call, public `invoke`). Four new workflow-internal events land in `codegenie.plugins.events` (`LeafKeyLoaded`, `LeafInvoked`, `LeafReturned`, `LeafProtocolViolationEvent` — internal-variant count grew 26 → 30). 25 story-scoped tests pass on first GREEN: 5 event-tests, 18 adapter-tests, 2 malformed-retry tests, 2 structured-output tests, 1 prompt-newtype-boundary fence, 2 (skipped) cassette markers. Gates green: 424 fence tests, 6593 unit+integration, `mypy --strict src/` (222 files), `ruff check`/`ruff format --check`, `lint-imports` (11 contracts kept / 0 broken — incl. the new singleton `anthropic_adapter -> anthropic` `ignore_imports` and the matching `anthropic_adapter -> codegenie.fallback.budget_token` ADR-0010 edge). The pre-commit mypy hook now mirrors `anthropic` + `keyring` in its `additional_dependencies`. Three pre-existing local-env failures (L-2 macOS `tsconfig_pathological` timing flake; L-4 `lint_imports_canary` PATH issue × 2) verified out of story scope — CI Linux runners are clean.)
**Pre-validation Status:** HARDENED
**Effort:** L
**Depends on:** S3-01 (`LeafLlm` Protocol + `LeafResponse`; `schema: TypeAdapter[PlanProposal]`), S2-05 (`BudgetToken`), S2-04 (`PromptBuilder` -> `TrustedPrompt` + `FencedPromptBody`), S1-02 (`PlanProposal` closed union; schema exported via `TypeAdapter(PlanProposal).json_schema()`), S1-05/S1-06 (path-scoped fence + import-linter admitting `anthropic` only under `src/codegenie/fallback/leaf/`)
**ADRs honored:** ADR-0001 (Phase 4 — schema-at-SDK-boundary), ADR-0003 (Phase 4 — path-scoped fence admits `anthropic` here and only here), ADR-0005 (Phase 4 — no SPKI pin; system trust), ADR-0010 (Phase 4 — `BudgetToken` keyword-only required), ADR-0014 (Phase 4 — cassettes are sanitized before record), ADR-0020 (production — Protocol earns its keep here)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 15 — 5 blocks, 8 hardens, 2 nits

Changes applied:
- **C1/API1 (block)** — replaced stale `PlanProposal.model_json_schema()` / `response_format` wording with the S3-01-hardened `TypeAdapter[PlanProposal]` seam and Anthropic's current structured-output request shape: `output_config={"format": {"type": "json_schema", "schema": schema.json_schema()}}`.
- **C2 (block)** — reconciled prompt-cache block assembly with S2-04: the adapter receives a flattened `TrustedPrompt` plus fenced `FencedPromptBody`, so it must not split `skill`/`instruction_template` or promote RAG few-shots out of the fenced body.
- **C3 (block)** — removed the future-story dependency on concrete `EgressGuard`; this story depends on an injected `EgressGuardPort` Protocol so S3-03 can later provide the implementation without a story-order cycle.
- **C4 (block)** — cassettes are no longer recorded in S3-02 before S3-04/S3-05/S3-06 land the sanitizer, scanner, lock, and operator path. This story ships cassette-ready scenario tests only; live cassette bytes are deferred to the cassette discipline stories.
- **C5/TQ1 (block)** — replaced stale `src/codegenie/logging.py` / `event_log_spy.entries` assumptions with `codegenie.plugins.events.EventLog.emit_internal(...)`, `WorkflowInternalEvent` registration, and replay-based tests.
- **TQ2 (harden)** — replaced the `cast`-based Protocol proof with a subprocess-mypy positive assignment (`_leaf: LeafLlm = AnthropicLeafAdapter(...)`) so the test cannot hide non-conformance.
- **TQ3 (harden)** — pinned the first request's user bytes to exactly `FencedPromptBody`; the malformed-output retry may append only the trusted suffix at SDK-request construction time and must not mint a new `FencedPromptBody`.
- **TQ4 (harden)** — request/response digest formulas now match the actual one-system-block shape and use response text parsed through `schema.validate_json(...)`.
- **TQ5 (harden)** — transport retry tests must prove the exact call-count semantics and that `EgressGuardPort.pinned_to(...)` wraps every physical SDK attempt.
- **D1 (harden)** — added dependency-inversion notes: the adapter owns SDK translation; the egress guard and event log are injected ports; no SDK details escape the `LeafLlm` seam.
- **D2 (harden)** — `pyproject.toml` import-linter ignore edge is now an explicit AC: S3-02 adds exactly the one permitted `codegenie.fallback.leaf.anthropic_adapter -> anthropic` edge.
- **D3 (harden)** — event models are workflow-internal and named separately from exceptions (`LeafProtocolViolationEvent` vs `LeafProtocolViolation`).
- **Cov1 (harden)** — cache-usage token mapping now names the Anthropic usage fields and defaults optional cache counters to zero when absent.
- **N1 (nit)** — lower/upper SDK version pin must be justified in the attempt log and covered by a frozen-cassette compatibility smoke test.
- **N2 (nit)** — no `Any` / untyped SDK dict shuffling: request payload aliases use typed `TypedDict` or frozen Pydantic models local to the adapter.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S3-02-anthropic-leaf-adapter.md

## Context

`AnthropicLeafAdapter` is the **single concrete `LeafLlm`** Phase 4 ships and the **sole** module in the codebase allowed to `import anthropic` — enforced both structurally (path-scoped fence test from S1-05) and by `import-linter` (S1-06). Every Anthropic-SDK detail (structured-output request shape, prompt-cache control, retry policy, key acquisition, SDK response parsing) lives here so the rest of Phase 4 sees only the `LeafLlm` Protocol seam.

Per the hardened predecessor stories, three draft assumptions are stale and corrected here:

- S3-01 hardened the Protocol to `schema: TypeAdapter[PlanProposal]`; `PlanProposal` is an `Annotated` discriminated-union alias, not a class, so `PlanProposal.model_json_schema()` / `schema.model_json_schema()` is not implementable.
- Anthropic's current structured-output API uses `output_config={"format": {"type": "json_schema", ...}}` on `messages.create(...)` (or the SDK `messages.parse(...)` helper for Pydantic models). Because this codebase's schema is a `TypeAdapter` over an annotated union, this story uses raw `messages.create(...)` + `schema.json_schema()` + `schema.validate_json(...)`.
- S2-04 hardened `PromptBuilder.build(...)` to return a flattened `TrustedPrompt` (`skill + "\n\n" + instruction_template`) and a fenced `FencedPromptBody` containing all untrusted bytes including RAG few-shots. Therefore this adapter must not split the trusted prompt into separate `skill` / `instruction_template` system blocks and must not lift RAG few-shots out of the fenced body. It sends one cached trusted-system block plus one exact fenced user body.

Operational constraints:

- Key loaded from `keyring.get_password("codegenie", "anthropic_api_key")` -> `SecretStr`. **No env-var fallback**, including no `CODEGENIE_ANTHROPIC_KEY_CI` (explicitly rejected by ADR-0005/0010). Missing key -> refuse-to-start with diagnostic pointing to `codegenie auth set`.
- The adapter performs **one** in-call retry when the SDK response cannot be parsed by `schema.validate_json(...)`, appending the trusted suffix `"\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."` only while constructing the retry SDK request. It must not mint a new `FencedPromptBody`.
- Transport retries apply only to `anthropic.APIStatusError` with backoff `1s, 4s, 16s` (three retries = four physical SDK attempts). No other exception retries.
- The adapter depends on an injected `EgressGuardPort` Protocol whose `pinned_to("api.anthropic.com:443")` async context manager wraps every physical SDK attempt. S3-03 ships the concrete guard later; this story remains executable with a mock port.
- **No live cassettes are recorded in S3-02.** The first real Anthropic cassette bytes must be recorded only after S3-04 installs sanitizer hooks, S3-05 installs the scanner/lock, and S3-06 provides the operator refresh path. S3-02 owns cassette-ready scenario tests and expected variants only.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 4 — LeafLlm Protocol + AnthropicLeafAdapter` — internal structure, key loading, retry policy. Treat `type[PlanProposal]` / `response_format` lines there as stale; S3-01 and this validation supersede the spelling while preserving the schema-at-boundary invariant.
  - `../phase-arch-design.md §Sequence: LLM-from-scratch` and §Sequence: retry-bypass-RAG — the leaf call's event-emission order.
  - `../phase-arch-design.md §Edge cases #7, #12, #16, #20` — invalid JSON retry, egress non-Anthropic host, transport retry schedule, missing keyring key.
  - `../phase-arch-design.md §Design patterns applied` — "Adapter at a hard trust boundary" and "Capability pattern (financial)".
- **Phase ADRs:**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` §Decision — schema-at-SDK-boundary. Treat the `PlanProposal.model_json_schema()` wording as stale; the invariant is preserved through `TypeAdapter(PlanProposal).json_schema()`.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — admits `anthropic` *only* under `src/codegenie/fallback/leaf/`.
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` §Decision + §Consequences — system trust store; no env-var key fallback; nightly drift job is the canary.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` §Consequences — `BudgetToken` is consumed but not reconciled by the adapter; `LlmInvocationGuard.reconcile(...)` happens in `FallbackTier` (S6-01).
  - `../ADRs/0014-cassette-discipline-security-control.md` — no cassette bytes land before sanitizer + scanner + manifest + operator workflow.
- **Production ADRs:**
  - `../../../production/adrs/0020-leaf-agents-sdk.md` — multi-vendor seam.
- **Source design:** `../final-design.md §Component 4 — LeafLlm`.
- **Predecessor validations:**
  - `_validation/S3-01-leaf-llm-port.md` — `schema: TypeAdapter[PlanProposal]`, `LeafResponse` field constraints, no `cast` proof.
  - `_validation/S2-04-prompt-builder-sole-mint.md` — flattened `TrustedPrompt`; all RAG few-shot bytes stay in `FencedPromptBody`; sole-mint AST fence.
  - `_validation/S2-05-llm-invocation-guard-budget-token.md` — real `EventLog` API and internal event registration.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py` — `EventLog.emit_internal(...)`, `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, replay conventions.
  - `src/codegenie/hashing.py` — BLAKE3 helper; do not fork hashing.
  - S1-05/S1-06 fence/import-linter tests — append only the single permitted Anthropic import edge.
- **External API docs:**
  - Anthropic structured outputs: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs` — `output_config.format` request shape and current Python SDK helper behavior.

## Goal

Land `AnthropicLeafAdapter` as the sole `anthropic` SDK importer in the codebase, wrap every physical SDK attempt in an injected `EgressGuardPort.pinned_to("api.anthropic.com:443")`, enforce schema-at-SDK-boundary with Anthropic structured outputs (`output_config.format` from `schema.json_schema()` plus defensive `schema.validate_json(...)`), honor the documented retry policy (1 in-call schema retry, 3 transport retries with exponential backoff), and refuse-to-start when `keyring` returns no key. The story makes the adapter cassette-ready, but it does **not** record live cassette bytes before the cassette-discipline stories land.

## Acceptance criteria

### Adapter shape + key loading

- [x] AC-1 — `src/codegenie/fallback/leaf/anthropic_adapter.py` exists; class `AnthropicLeafAdapter` structurally conforms to the S3-01 `LeafLlm` Protocol. Proof is a subprocess-mypy positive control assigning `_leaf: LeafLlm = AnthropicLeafAdapter(event_log=..., egress_guard=...)`; no `cast(...)`, no `isinstance(adapter, LeafLlm)` (the Protocol is not runtime-checkable).
- [x] AC-2 — `AnthropicLeafAdapter.__init__(self, *, event_log: EventLog, egress_guard: EgressGuardPort, model: ModelId = ModelId("claude-sonnet-4-5-20250929")) -> None`. `EgressGuardPort` is a local `Protocol` requiring `pinned_to(host: str) -> AsyncContextManager[None]`; it is deliberately a port, not an import of S3-03's future concrete `EgressGuard`. `event_log` and `egress_guard` are injected. `keyring.get_password("codegenie", "anthropic_api_key")` is called at `__init__`; `None` raises `AnthropicKeyMissing` with the literal diagnostic `"codegenie auth set"`.
- [x] AC-3 — Key handling never stores cleartext on `self`: the returned key is wrapped in `SecretStr`, passed to `anthropic.AsyncAnthropic(api_key=secret.get_secret_value())`, then not retained except inside the SDK client. Test introspects `adapter.__dict__` and serialized events for absence of `sk-ant` and the exact fake key bytes.
- [x] AC-4 — Refuse-to-start emits a workflow-internal `LeafKeyLoaded(present=False)` event via `event_log.emit_internal(...)` then raises; happy path emits `LeafKeyLoaded(present=True)` exactly once. The event model is registered in `codegenie.plugins.events.WorkflowInternalEvent` and `_INTERNAL_CLASSES`; tests read events via `EventLog.replay()`.
- [x] AC-5 — **No env-var fallback path exists.** AST source-scan asserts the adapter does not reference `os.environ`, `os.getenv`, `getpass.getpass`, or any `CODEGENIE_*` string. Adversarial test sets `CODEGENIE_ANTHROPIC_KEY_CI=sk-ant-test` in env, `keyring` returns `None` -> `AnthropicKeyMissing` still raises.

### Invoke semantics

- [x] AC-6 — `AnthropicLeafAdapter.invoke` signature exactly matches S3-01:
  ```python
  async def invoke(
      self,
      system_prompt: TrustedPrompt,
      user_message: FencedPromptBody,
      *,
      schema: TypeAdapter[PlanProposal],
      token: BudgetToken,
  ) -> LeafResponse: ...
  ```
  `schema` and `token` are keyword-only and required. The adapter does not construct or import `LlmInvocationGuard`.
- [x] AC-7 — The first SDK request is constructed with:
  - `output_config={"format": {"type": "json_schema", "schema": schema.json_schema()}}` — current Anthropic structured-output request shape.
  - `system=[{"type": "text", "text": str(system_prompt), "cache_control": {"type": "ephemeral"}}]` — one trusted cached block. The adapter must not split `TrustedPrompt` on `"\n\n"`, must not inspect for `skill` / `instruction_template`, and must not use any `rag_few_shot` / `rag_retrieved` literal.
  - `messages=[{"role": "user", "content": str(user_message)}]` — first-attempt user content is **exactly** the `FencedPromptBody` bytes. Test fails on f-string interpolation, `.format`, prefix/suffix, or any raw prompt wrapping on the first attempt.
- [x] AC-8 — On successful 200 response, the adapter extracts exactly one text response body, parses it with `schema.validate_json(response_text)`, constructs `LeafResponse`, and emits `LeafInvoked(prompt_digest_blake3)` before the physical SDK call and `LeafReturned(response_digest_blake3, tokens_in, tokens_out, cache_read, cache_creation)` after parse succeeds. Event order is asserted via `EventLog.replay()`.
- [x] AC-9 — Token fields map from the Anthropic SDK response usage object: `tokens_in = usage.input_tokens`, `tokens_out = usage.output_tokens`, `cache_read_tokens = usage.cache_read_input_tokens` or `0` when absent, `cache_creation_tokens = usage.cache_creation_input_tokens` or `0` when absent. Values are wrapped in `TokenCount` and then validated by `LeafResponse`'s `Annotated[TokenCount, Field(ge=0)]` fields (S3-01 AC-3).
- [x] AC-10 — `prompt_digest_blake3` is `blake3(str(system_prompt) + str(user_message))`; `response_digest_blake3` is `blake3(response_text)`. No raw prompt or response bytes appear in event payloads. Test serializes every emitted event and asserts neither the system prompt, user message, nor response body substring appears.
- [x] AC-11 — **`BudgetToken` is consumed but not reconciled here.** The adapter accepts the token as a typed signature requirement but does not call `LlmInvocationGuard.reconcile`, mutate budget state, or import `LlmInvocationGuard`. Reconciliation happens in `FallbackTier` (S6-01). Test mocks/monkeypatches `LlmInvocationGuard.reconcile` and asserts it is not reached.

### In-call malformed-output retry

- [x] AC-12 — If the first SDK response cannot be parsed by `schema.validate_json(...)` (including malformed JSON, missing text content, or a schema-invalid structured response), the adapter builds exactly one retry request. The retry request's user content is `str(user_message) + "\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."`. This suffix is trusted adapter-owned text; the adapter must **not** call `FencedPromptBody(...)` or any prompt-newtype constructor (S2-04 sole-mint invariant). An AST test asserts no `TrustedPrompt(` / `FencedPromptBody(` calls exist in `anthropic_adapter.py`.
- [x] AC-13 — Unit test (`tests/unit/fallback/test_leaf_adapter_malformed_retry.py`): first response is hand-crafted invalid JSON; second response is a valid `PlanProposalRefuse`. Assert exactly two schema-parse attempts, exactly two physical SDK calls (modulo no transport errors), returned `LeafResponse.plan.kind == "refuse"`, and no `LeafProtocolViolationEvent` emitted.
- [x] AC-14 — Second-failure test: both responses invalid -> `LeafProtocolViolation(first_error, second_error)` raised; workflow-internal `LeafProtocolViolationEvent` emitted once; no `LeafReturned` event. Exception and event are distinct types/names.

### Transport retries (1s / 4s / 16s)

- [x] AC-15 — On `anthropic.APIStatusError` (5xx or rate-limit 429), the adapter retries with sleeps `[1.0, 4.0, 16.0]` seconds (three retries total = four physical SDK calls). After the fourth failure, the original `APIStatusError` propagates *unwrapped* to the caller. Test monkeypatches `asyncio.sleep` and the SDK method; asserts sleep schedule, call count, and propagated exception identity.
- [x] AC-16 — Non-`APIStatusError` exceptions (`EgressViolation`, `LeafProtocolViolation`, `pydantic.ValidationError` after the one in-call retry, unexpected SDK exceptions) do **not** trigger transport retry; they propagate immediately under their own policy.
- [x] AC-17 — Transport retry and malformed-output retry are independent: an `APIStatusError` happens before any response parse and is retried by AC-15; a schema parse failure happens after a 200 response and uses AC-12's one in-call retry. A test covers `APIStatusError` on the first physical attempt followed by a malformed 200 then a valid 200, proving both counters are separate and bounded.

### EgressGuardPort composition

- [x] AC-18 — Every physical SDK call (first attempt, transport retries, malformed-output retry) is wrapped in `async with self._egress_guard.pinned_to("api.anthropic.com:443"):`. Test installs a recording async context manager and asserts one enter/exit pair per physical SDK call, all with `host == "api.anthropic.com:443"`.

### Fence + import-linter

- [x] AC-19 — `tests/fence/test_only_leaf_imports_anthropic.py` exists, consumes the shared S1-05 Phase-4 fence scanner, and asserts the **only** source file containing `import anthropic` or `from anthropic` is `src/codegenie/fallback/leaf/anthropic_adapter.py`. A deliberately-violating fixture under `tests/fence/fixtures/` is verified to fail the same scanner so the test cannot pass vacuously.
- [x] AC-20 — `pyproject.toml`'s Phase-4 import-linter contract from S1-06 gains exactly one `ignore_imports` edge for Anthropic: `"codegenie.fallback.leaf.anthropic_adapter -> anthropic"`. No other `anthropic` ignore edge is added. Shape test asserts exact singleton.
- [x] AC-21 — `make lint` and `make lint-imports` pass after this story; `tests/fence/test_pyproject_fence_phase4.py`, `tests/fence/test_only_leaf_imports_anthropic.py`, and the S1-05 runtime-closure assertion remain green.

### Cassettes (adapter is cassette-ready; live recording deferred)

- [x] AC-22 — No live cassette YAML files are created or committed by S3-02. Tests under `tests/unit/fallback/` use SDK fakes/mocks only; any live-API cassette scenario tests are marked `pytest.mark.uses_anthropic_cassette` and skipped unless S3-04/S3-06 enable the refresh workflow.
- [x] AC-23 — The two cassette scenarios are specified as fixtures/markers for S3-06 to record later: `leaf_adapter_llm_from_scratch` expects `PlanProposalCallsiteRewrite` on `fixtures/vuln-major-bump/express-cve-2026-1234`; `leaf_adapter_rag_hit_few_shot` expects the cassette-recorded `PlanProposal` on `fixtures/vuln-rag-hit/express-rerun`. The adapter code must be compatible with `pytest-recording`, but this story must not bypass the S3-04 sanitizer hooks.
- [x] AC-24 — `tests/security/test_cassettes_clean.py` and `tests/cassettes/anthropic/cassettes.lock` are not required to exist yet in S3-02. Their absence does not block this story; S3-05 owns the scanner/manifest and will consume the scenario markers from AC-23.

### Cross-cutting

- [x] AC-25 — `mypy --strict src/codegenie/fallback/leaf/` clean. `ruff check`, `ruff format --check` clean on touched files.
- [x] AC-26 — Adapter-local request/response payload shapes use typed aliases (`TypedDict`) or frozen Pydantic models. No `Any`, no untyped functions, no raw dict-shuffling across helper boundaries.
- [x] AC-27 — TDD red test exists, was demonstrably failing before implementation, now green.

## Implementation outline

1. Add strictly bounded `anthropic` and `keyring>=24,<26` to `pyproject.toml` `[project.dependencies]` if S1-05 has not already done so; record the exact Anthropic lower/upper bound rationale in the attempt log because cassette compatibility depends on it.
2. Create `src/codegenie/fallback/leaf/anthropic_adapter.py`:
   - Top-level `import anthropic` (the **one** allowed site).
   - Local `EgressGuardPort(Protocol)` and typed SDK request aliases.
   - `class AnthropicKeyMissing(Exception)` with the `codegenie auth set` diagnostic string.
   - `class LeafProtocolViolation(Exception)` carrying both parse error contexts.
   - `class AnthropicLeafAdapter` with `__init__`, `_load_key()`, `_build_request(...)`, `_parse_response(...)`, async `invoke(...)`, and `_call_sdk_with_transport_retry(...)`.
3. Register workflow-internal events in `src/codegenie/plugins/events.py`: `LeafKeyLoaded`, `LeafInvoked`, `LeafReturned`, `LeafProtocolViolationEvent`. Extend `tests/unit/plugins/test_events.py` with round-trip/replay tests.
4. Build the first request from one cached trusted-system block and exact fenced user bytes. Do not split `TrustedPrompt` or inspect RAG markers.
5. Use `output_config={"format": {"type": "json_schema", "schema": schema.json_schema()}}`, then parse response text with `schema.validate_json(...)` before constructing `LeafResponse`.
6. Implement malformed-output retry by appending the trusted suffix to SDK request content only; do not construct a new prompt newtype.
7. Implement transport retry as a small loop over `_TRANSPORT_RETRY_BACKOFF_SECONDS: Final[tuple[float, ...]] = (1.0, 4.0, 16.0)` and catch only `anthropic.APIStatusError`.
8. Wrap every SDK call in `async with self._egress_guard.pinned_to("api.anthropic.com:443"):`.
9. Add the `anthropic` import-linter ignore edge and the targeted fence test with positive-control fixture.
10. Add cassette scenario markers/fixtures, but do not record cassettes or create `cassettes.lock`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/fallback/test_leaf_adapter.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import TypeAdapter

from codegenie.fallback.leaf.anthropic_adapter import (
    AnthropicLeafAdapter,
    AnthropicKeyMissing,
)
from codegenie.fallback.plan_proposal import PlanProposal


@pytest.mark.asyncio
async def test_init_refuses_when_keyring_returns_none(event_log):
    egress = MagicMock()
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing) as exc:
            AnthropicLeafAdapter(event_log=event_log, egress_guard=egress)
    assert "codegenie auth set" in str(exc.value)
    events = list(event_log.replay())
    assert events[-1].event_type == "leaf_key_loaded"
    assert events[-1].present is False


@pytest.mark.asyncio
async def test_init_does_not_fall_back_to_env(monkeypatch, event_log):
    monkeypatch.setenv("CODEGENIE_ANTHROPIC_KEY_CI", "sk-ant-NOPE")
    with patch("keyring.get_password", return_value=None):
        with pytest.raises(AnthropicKeyMissing):
            AnthropicLeafAdapter(event_log=event_log, egress_guard=MagicMock())


@pytest.mark.asyncio
async def test_request_uses_type_adapter_schema_and_exact_fenced_body(
    adapter_with_sdk_mock,
    trusted_prompt,
    fenced_body,
    budget_token,
):
    schema = TypeAdapter(PlanProposal)
    await adapter_with_sdk_mock.invoke(
        trusted_prompt,
        fenced_body,
        schema=schema,
        token=budget_token,
    )
    request = adapter_with_sdk_mock.sdk.calls[0].kwargs
    assert request["output_config"]["format"]["schema"] == schema.json_schema()
    assert request["messages"] == [{"role": "user", "content": str(fenced_body)}]
    assert request["system"] == [
        {
            "type": "text",
            "text": str(trusted_prompt),
            "cache_control": {"type": "ephemeral"},
        }
    ]


@pytest.mark.asyncio
async def test_transport_retry_schedule_is_1_4_16(monkeypatch, adapter_with_sdk_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    adapter_with_sdk_mock.sdk.raise_api_status_error_times(3)
    await adapter_with_sdk_mock.invoke_valid_request()
    assert sleeps == [1.0, 4.0, 16.0]
    assert adapter_with_sdk_mock.sdk.call_count == 4
```

```python
# tests/unit/fallback/test_leaf_adapter_malformed_retry.py
@pytest.mark.asyncio
async def test_in_call_schema_failure_retries_exactly_once(adapter_with_sdk_mock):
    adapter_with_sdk_mock.sdk.queue_text("not json")
    adapter_with_sdk_mock.sdk.queue_plan_refuse(reason="out_of_scope")

    response = await adapter_with_sdk_mock.invoke_valid_request()

    assert adapter_with_sdk_mock.sdk.call_count == 2
    retry_content = adapter_with_sdk_mock.sdk.calls[1].kwargs["messages"][0]["content"]
    assert retry_content.endswith(
        "\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."
    )
    assert response.plan.kind == "refuse"
```

```python
# tests/fence/test_anthropic_adapter_prompt_newtype_boundary.py
import ast
from pathlib import Path


def test_adapter_does_not_mint_prompt_newtypes():
    tree = ast.parse(Path("src/codegenie/fallback/leaf/anthropic_adapter.py").read_text())
    forbidden = {"TrustedPrompt", "FencedPromptBody"}
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden
    ]
    assert calls == []
```

### Green — make it pass

Author the adapter file as outlined above; add event models and focused tests. Use SDK fakes for every unit test. Do not create live cassettes in this story.

### Refactor — clean up

- Extract `_build_system_blocks(...)`, `_build_output_config(...)`, and `_parse_leaf_response(...)` as pure helpers; `invoke(...)` stays the imperative shell that emits events, opens the egress context, and calls the SDK.
- Move retry suffix and sleep schedule to module-level `Final` constants.
- Keep `EgressGuardPort` small and local. Do not introduce a global registry, factory, or concrete guard import.
- Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"leaf.key_loaded", "leaf.invoked", "leaf.returned", "leaf.protocol_violation"})` validated at import time per Phase-1 ADR-0007.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Pin `anthropic` + `keyring`; add exactly one Anthropic import-linter ignore edge if S1-05/S1-06 already landed the contracts. |
| `src/codegenie/fallback/leaf/anthropic_adapter.py` | The adapter (this story's primary deliverable). |
| `src/codegenie/plugins/events.py` | Register `LeafKeyLoaded`, `LeafInvoked`, `LeafReturned`, `LeafProtocolViolationEvent`. |
| `tests/unit/plugins/test_events.py` | Event registration / replay tests. |
| `tests/unit/fallback/test_leaf_adapter.py` | Init/refuse/retry/schema unit tests. |
| `tests/unit/fallback/test_leaf_adapter_malformed_retry.py` | In-call schema-retry semantics. |
| `tests/unit/fallback/test_anthropic_structured_output.py` | Asserts `output_config.format.schema == schema.json_schema()` and `schema.validate_json(...)` parse path. |
| `tests/fence/test_only_leaf_imports_anthropic.py` | AST source-scan: only one importer of `anthropic`. |
| `tests/fence/test_anthropic_adapter_prompt_newtype_boundary.py` | AST source-scan: adapter does not mint prompt newtypes. |
| `tests/fence/fixtures/violating_anthropic_import.py.txt` | Deliberately-violating fixture (proves the fence walk catches violations). |
| `tests/unit/fallback/test_leaf_adapter_cassette_scenarios.py` | Cassette-ready scenario markers / expected variants; skipped until S3-04/S3-06 enable live recording. |

## Out of scope

- Concrete `EgressGuard` implementation (S3-03; this story consumes an injected port and tests with a mock).
- `CassetteSanitizer` hooks (S3-04).
- `cassettes.lock` walker / scanner (S3-05).
- `make refresh-cassettes` ergonomic and live recording (S3-06).
- `FallbackTier` composition (S6-01).
- Anthropic prompt-cache *measurement* (Phase 6.5).

## Notes for the implementer

- `anthropic.AsyncAnthropic` is the SDK entry point; pass `api_key=secret.get_secret_value()` only at the SDK boundary. Do not assign the cleartext to an attribute; keep it inside the SDK client.
- The current Anthropic structured-output request shape is `output_config={"format": {"type": "json_schema", "schema": ...}}`. Do not use the stale `response_format` spelling unless the pinned SDK version explicitly documents a backward-compatible alias; if an alias is used, record the SDK-doc citation in the attempt log and add a compatibility smoke test.
- `TrustedPrompt` is already flattened by S2-04; do not split it. `FencedPromptBody` contains RAG few-shots as fenced untrusted bytes; do not extract or promote them into the system block for cache control.
- `LlmInvocationGuard.reconcile(token, ...)` is called *not* here but in `FallbackTier.run(...)` (S6-01) after `await leaf.invoke(...)` returns — keep the adapter free of budget-state mutations so the capability flows through exactly two frames (ADR-0010 §Pattern fit).
- The transport-retry backoff `(1.0, 4.0, 16.0)` is *not* a jittered schedule; Phase 5's retry envelope adds jitter at the outer layer. Do not pre-emptively jitter here.
- Do not record cassettes before S3-04/S3-05/S3-06. A live cassette PR before sanitizer hooks is a security bug, not a shortcut.
- C-extension residual: `anthropic`'s `httpx` transport is expected to use Python socket paths that S3-03's `EgressGuard` catches. The native-extension restriction from S1-06 remains the compensating control for lower-level bypasses.
