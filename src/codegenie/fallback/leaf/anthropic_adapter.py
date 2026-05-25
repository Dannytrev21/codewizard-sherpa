"""Phase-4 S3-02 — :class:`AnthropicLeafAdapter`, the sole concrete
:class:`~codegenie.fallback.leaf.port.LeafLlm` and the **single** module
in the codebase allowed to ``import anthropic``.

Every Anthropic-SDK detail (structured-output request shape, prompt-cache
control, retry policy, key acquisition, SDK response parsing) lives here so
the rest of Phase 4 sees only the Protocol seam.

Three sibling structural fences pin the boundary:

* ``tests/fence/test_only_leaf_imports_anthropic.py`` (S1-05 / AC-19) —
  AST-walks ``src/codegenie/`` and asserts no other file contains
  ``import anthropic`` / ``from anthropic …``.
* ``tests/fence/test_pyproject_fence_phase4.py`` (S1-05) — re-runs the
  single-callsite assertion via the shared Phase-4 scanner.
* ``tests/fence/test_anthropic_adapter_prompt_newtype_boundary.py``
  (this story, AC-12) — asserts the adapter never constructs
  :data:`TrustedPrompt` or :data:`FencedPromptBody` (the
  :class:`PromptBuilder` sole-mint invariant from S2-04).

The malformed-output retry appends a trusted suffix to the SDK request's
``user`` content **as plain ``str`` concatenation**, not by re-minting a
:data:`FencedPromptBody`. This is what keeps S2-04's AST-walk fence happy
while still allowing the adapter to nudge the model back into the schema.

References (under ``docs/phases/04-vuln-llm-fallback-rag/``):

- ``stories/S3-02-anthropic-leaf-adapter.md``
- ``ADRs/0001-plan-proposal-closed-sum-type.md``
- ``ADRs/0003-path-scoped-fence-amendment.md``
- ``ADRs/0005-no-spki-pin-egress-defense-in-depth.md``
- ``ADRs/0010-llm-invocation-guard-budget-token-capability.md``
- ``ADRs/0014-cassette-discipline-security-control.md``
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, Final, Literal, Protocol, cast

import anthropic
import keyring
from anthropic import AsyncAnthropic
from pydantic import SecretStr, TypeAdapter, ValidationError

from codegenie.fallback.budget_token import BudgetToken
from codegenie.fallback.fence.prompt_builder import FencedPromptBody, TrustedPrompt
from codegenie.fallback.leaf.port import LeafResponse
from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.hashing import content_hash_bytes
from codegenie.plugins.events import (
    EventLog,
    LeafInvoked,
    LeafKeyLoaded,
    LeafProtocolViolationEvent,
    LeafReturned,
)
from codegenie.types.identifiers import (
    BlobDigest,
    EventId,
    LeafResponseId,
    ModelId,
    TokenCount,
)

__all__ = (
    "AnthropicKeyMissing",
    "AnthropicLeafAdapter",
    "EgressGuardPort",
    "LeafProtocolViolation",
)

# --- Constants --------------------------------------------------------------

_DEFAULT_MODEL: Final[ModelId] = ModelId("claude-sonnet-4-5-20250929")
"""S3-02 default model; can be overridden at construction time."""

_ANTHROPIC_HOST: Final[str] = "api.anthropic.com:443"
"""The only host the leaf adapter is allowed to talk to. The injected
:class:`EgressGuardPort` is asked to pin every physical SDK attempt here;
S3-03's concrete :class:`EgressGuard` enforces this at the socket layer."""

_BLAKE3_PREFIX: Final[str] = "blake3:"
"""``content_hash_bytes`` returns a ``"blake3:" + 64-hex`` string; strip the
prefix to populate the un-prefixed :data:`BlobDigest`."""

_TRANSPORT_RETRY_BACKOFF_SECONDS: Final[tuple[float, ...]] = (1.0, 4.0, 16.0)
"""AC-15 — three retries on :class:`anthropic.APIStatusError`. Phase 5's outer
retry envelope is responsible for jitter; the adapter does not pre-emptively
jitter (ADR-0005 §Consequences)."""

_MAX_TOKENS_DEFAULT: Final[int] = 4096
"""Anthropic ``messages.create`` requires a ``max_tokens`` cap. The Phase-4
budget envelope tightens this further; this floor keeps the adapter
executable in isolation."""

_MALFORMED_RETRY_SUFFIX: Final[str] = (
    "\n\n[SYSTEM] your previous response was malformed; emit valid PlanProposal."
)
"""AC-12 — trusted adapter-owned text appended to the SDK request's ``user``
content on the one in-call malformed-output retry. Not a :data:`FencedPromptBody`
construction (the fence test enforces this)."""

_KEYRING_SERVICE: Final[str] = "codegenie"
_KEYRING_USER: Final[str] = "anthropic_api_key"
_MISSING_KEY_DIAGNOSTIC: Final[str] = (
    "Anthropic API key not found in OS keychain. Store it with: codegenie auth set"
)

_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "leaf.key_loaded",
        "leaf.invoked",
        "leaf.returned",
        "leaf.protocol_violation",
    }
)
"""Module-level warning-id catalog per Phase-1 ADR-0007. Adding a new
internal-event variant here requires a new entry."""

_WARNING_ID_PATTERN_OK = all(
    "." in wid and wid == wid.lower() and not wid.startswith(".") and not wid.endswith(".")
    for wid in _WARNING_IDS
)
if not _WARNING_ID_PATTERN_OK:
    raise AssertionError("S3-02 warning ids must match ^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$")


# --- Ports + exceptions -----------------------------------------------------


class EgressGuardPort(Protocol):
    """Adapter-owned :class:`Protocol` for the concrete
    :class:`~codegenie.fallback.egress.EgressGuard` that S3-03 will land.

    The async-context-manager seam is deliberately the only method on the
    port: the adapter does not care how the egress guard pins the host
    (socket-monkeypatch, ``httpx`` transport swap, eBPF) — only that an
    open egress envelope wraps every physical SDK attempt.

    Local Protocol rather than an import of a sibling module: keeps S3-02
    runnable without an S3-03 dependency, and keeps the future swap-point
    explicit (production ADR-0020 reserves the leaf seam for vendor
    plurality; the egress-guard implementation may swap likewise)."""

    def pinned_to(self, host: str) -> AbstractAsyncContextManager[None]:
        """Return an async context manager that pins the SDK's egress to
        ``host`` for the duration of the body."""
        ...


class AnthropicKeyMissing(Exception):
    """OS keychain returned no entry for ``codegenie / anthropic_api_key``.

    Diagnostic message contains the literal ``codegenie auth set`` so an
    operator sees the exact remediation command in the traceback."""


class LeafProtocolViolation(Exception):
    """Both SDK responses for one invocation failed schema validation.

    Carries both error summaries so an operator can correlate the first
    error (which triggered the in-call retry) with the second error (which
    triggered this exception). The matching workflow-internal event class
    is :class:`LeafProtocolViolationEvent` — the name suffix is deliberate
    (S3-02 §D3 — never share names across the exception/event axis)."""

    def __init__(self, first_error: str, second_error: str) -> None:
        self.first_error = first_error
        self.second_error = second_error
        super().__init__(f"leaf protocol violation: first={first_error!r} second={second_error!r}")


# --- Pure helpers (functional core) -----------------------------------------


def _build_system_blocks(system_prompt: TrustedPrompt) -> list[dict[str, Any]]:
    """One cached trusted-system block. Per S2-04 the prompt is already
    flattened (``skill + "\\n\\n" + instruction_template``); the adapter
    must not split it on ``"\\n\\n"`` or inspect for any RAG markers."""
    return [
        {
            "type": "text",
            "text": str(system_prompt),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _build_output_config(schema: TypeAdapter[PlanProposal]) -> dict[str, Any]:
    """Current Anthropic structured-output request shape (AC-7)."""
    return {"format": {"type": "json_schema", "schema": schema.json_schema()}}


def _extract_first_text(message: Any) -> str:
    """Return the first ``"text"``-typed block from an SDK ``Message``.

    Treated as a missing-text protocol violation when no such block exists —
    the in-call malformed-retry path picks it up and emits the trusted
    suffix on the next SDK request."""
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str):
                return text
    raise ValueError("SDK response has no text content block")


def _token_count_or_zero(value: int | None) -> TokenCount:
    """Project an optional SDK usage counter into a non-negative
    :data:`TokenCount` (AC-9). ``None`` defaults to zero; negative values
    are clamped to zero (the ``LeafResponse`` ``Field(ge=0)`` validator
    would otherwise reject them and mask the real protocol issue)."""
    if value is None or value < 0:
        return TokenCount(0)
    return TokenCount(value)


def _blake3_un_prefixed(payload: bytes) -> BlobDigest:
    """BLAKE3 of ``payload`` with the ``blake3:`` prefix stripped — the
    on-the-wire shape for :data:`BlobDigest` fields."""
    return BlobDigest(content_hash_bytes(payload).removeprefix(_BLAKE3_PREFIX))


def _prompt_digest(system_prompt: TrustedPrompt, user_message: FencedPromptBody) -> BlobDigest:
    """AC-10 — ``blake3(str(system_prompt) + str(user_message))`` un-prefixed."""
    return _blake3_un_prefixed((str(system_prompt) + str(user_message)).encode("utf-8"))


def _response_digest(response_text: str) -> BlobDigest:
    """AC-10 — ``blake3(response_text)`` un-prefixed."""
    return _blake3_un_prefixed(response_text.encode("utf-8"))


_LeafStopReason = Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"]
_LEAF_STOP_REASONS: Final[frozenset[str]] = frozenset(
    {"end_turn", "max_tokens", "stop_sequence", "tool_use"}
)


def _project_stop_reason(value: Any) -> _LeafStopReason:
    """Project the SDK's wider ``stop_reason`` literal (which adds
    ``pause_turn``/``refusal`` and ``None``) onto the four-member
    :data:`LeafResponse.stop_reason` literal. Unknown values fall back
    to ``"end_turn"`` — the leaf-response contract is the source of
    truth (S3-01 AC-7); widening it is an ADR amendment, not an SDK
    follow-the-leader move."""
    if isinstance(value, str) and value in _LEAF_STOP_REASONS:
        return cast(_LeafStopReason, value)
    return "end_turn"


def _now() -> datetime:
    """UTC ``datetime`` stamper. Injected via the adapter's constructor in
    tests that need a frozen clock; default uses real UTC."""
    return datetime.now(UTC)


def _new_event_id() -> EventId:
    """uuid4-hex :data:`EventId`."""
    return EventId(uuid.uuid4().hex)


# --- Adapter ----------------------------------------------------------------


class AnthropicLeafAdapter:
    """The sole concrete :class:`LeafLlm` and the single ``anthropic`` importer.

    Constructed once per workflow (matching the production ADR-0005 single-
    callsite shape). ``invoke`` is the only public method; ``_load_key`` /
    ``_build_request`` / ``_parse_response`` / ``_call_sdk_with_retry`` are
    private pure-ish helpers around the imperative shell.

    **Cleartext key hygiene (AC-3).** The adapter never stores the
    cleartext API key as a ``self`` attribute. The key is loaded from
    :mod:`keyring`, wrapped in :class:`pydantic.SecretStr`, passed once
    to :class:`anthropic.AsyncAnthropic` via
    ``api_key=secret.get_secret_value()``, and then dropped. The SDK
    client retains the key internally; the adapter retains only the
    client.
    """

    __slots__ = ("_client", "_egress_guard", "_event_log", "_model", "_workflow_id")

    def __init__(
        self,
        *,
        event_log: EventLog,
        egress_guard: EgressGuardPort,
        model: ModelId = _DEFAULT_MODEL,
    ) -> None:
        self._event_log = event_log
        self._egress_guard = egress_guard
        self._model = model
        self._workflow_id = event_log.workflow_id
        secret = self._load_key()
        # The cleartext value flows through `get_secret_value()` exactly here,
        # at the SDK boundary, and is not retained on `self` after this line.
        self._client = AsyncAnthropic(api_key=secret.get_secret_value())

    # ----- Key loading -----

    def _load_key(self) -> SecretStr:
        """Consult :mod:`keyring`; raise :class:`AnthropicKeyMissing` with
        the literal ``codegenie auth set`` diagnostic on miss.

        Emits ``leaf_key_loaded(present=...)`` exactly once before
        returning (or raising)."""
        raw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        present = raw is not None
        self._emit_key_loaded(present=present)
        if raw is None:
            raise AnthropicKeyMissing(_MISSING_KEY_DIAGNOSTIC)
        return SecretStr(raw)

    # ----- Event helpers (imperative shell) -----

    def _emit_key_loaded(self, *, present: bool) -> None:
        self._event_log.emit_internal(
            LeafKeyLoaded(
                event_id=_new_event_id(),
                workflow_id=self._workflow_id,
                timestamp=_now(),
                present=present,
            )
        )

    def _emit_invoked(self, prompt_digest: BlobDigest) -> None:
        self._event_log.emit_internal(
            LeafInvoked(
                event_id=_new_event_id(),
                workflow_id=self._workflow_id,
                timestamp=_now(),
                prompt_digest_blake3=prompt_digest,
                model=self._model,
            )
        )

    def _emit_returned(
        self,
        *,
        response_digest: BlobDigest,
        tokens_in: TokenCount,
        tokens_out: TokenCount,
        cache_read_tokens: TokenCount,
        cache_creation_tokens: TokenCount,
    ) -> None:
        self._event_log.emit_internal(
            LeafReturned(
                event_id=_new_event_id(),
                workflow_id=self._workflow_id,
                timestamp=_now(),
                response_digest_blake3=response_digest,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
            )
        )

    def _emit_protocol_violation(self, first_error: str, second_error: str) -> None:
        self._event_log.emit_internal(
            LeafProtocolViolationEvent(
                event_id=_new_event_id(),
                workflow_id=self._workflow_id,
                timestamp=_now(),
                first_error=first_error,
                second_error=second_error,
            )
        )

    # ----- Request construction -----

    def _build_request(
        self,
        *,
        system_prompt: TrustedPrompt,
        user_content: str,
        schema: TypeAdapter[PlanProposal],
    ) -> dict[str, Any]:
        """Assemble the keyword payload for :meth:`AsyncAnthropic.messages.create`.

        ``user_content`` is **plain ``str``**: the first call passes
        ``str(user_message)`` exactly; the retry call passes
        ``str(user_message) + _MALFORMED_RETRY_SUFFIX``. The adapter must
        never construct a :data:`FencedPromptBody` here — the
        prompt-newtype boundary fence
        (``tests/fence/test_anthropic_adapter_prompt_newtype_boundary.py``)
        is the structural guard."""
        return {
            "model": self._model,
            "max_tokens": _MAX_TOKENS_DEFAULT,
            "system": _build_system_blocks(system_prompt),
            "messages": [{"role": "user", "content": user_content}],
            "output_config": _build_output_config(schema),
        }

    # ----- Response parsing -----

    def _parse_response(
        self, message: Any, schema: TypeAdapter[PlanProposal]
    ) -> tuple[PlanProposal, str]:
        """Extract the first text block, validate it with
        :meth:`TypeAdapter.validate_json`, return ``(plan, response_text)``.

        Failures (no text block, malformed JSON, schema-invalid structured
        response) raise :class:`ValueError` so the in-call retry loop can
        capture the error summary uniformly."""
        response_text = _extract_first_text(message)
        try:
            plan = schema.validate_json(response_text)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return plan, response_text

    # ----- SDK invocation (imperative shell) -----

    async def _call_sdk_with_transport_retry(self, request_kwargs: dict[str, Any]) -> Any:
        """One logical SDK call with transport-retry envelope.

        Catches only :class:`anthropic.APIStatusError` (AC-15 / AC-16);
        every other exception propagates immediately. Sleeps on the
        backoff schedule between attempts. The original
        :class:`APIStatusError` propagates unwrapped after the 4th failure
        (no re-raise under a wrapper exception)."""
        last_error: BaseException | None = None
        for attempt_idx in range(len(_TRANSPORT_RETRY_BACKOFF_SECONDS) + 1):
            async with self._egress_guard.pinned_to(_ANTHROPIC_HOST):
                try:
                    return await self._client.messages.create(**request_kwargs)
                except anthropic.APIStatusError as exc:
                    last_error = exc
            if attempt_idx < len(_TRANSPORT_RETRY_BACKOFF_SECONDS):
                await asyncio.sleep(_TRANSPORT_RETRY_BACKOFF_SECONDS[attempt_idx])
        assert last_error is not None  # noqa: S101 — the loop only exits via return or error
        raise last_error

    # ----- Public invoke -----

    async def invoke(
        self,
        system_prompt: TrustedPrompt,
        user_message: FencedPromptBody,
        *,
        schema: TypeAdapter[PlanProposal],
        token: BudgetToken,  # noqa: ARG002 — accepted but not reconciled (ADR-0010)
    ) -> LeafResponse:
        """Issue one logical LLM call against the keyword-only contract.

        The ``token`` is accepted and required for type-level capability
        flow (ADR-0010 §Consequences — :class:`LlmInvocationGuard.reconcile`
        is the :class:`FallbackTier`'s concern in S6-01, not the adapter's).
        """
        prompt_digest = _prompt_digest(system_prompt, user_message)
        self._emit_invoked(prompt_digest)

        # First attempt: exact user bytes.
        first_user_content = str(user_message)
        first_message = await self._call_sdk_with_transport_retry(
            self._build_request(
                system_prompt=system_prompt,
                user_content=first_user_content,
                schema=schema,
            )
        )
        try:
            plan, response_text = self._parse_response(first_message, schema)
        except ValueError as first_error:
            first_error_summary = str(first_error)
            # AC-12 — one in-call retry. The retry user content is
            # str(user_message) + trusted suffix, built by str concat
            # only (no FencedPromptBody minting).
            retry_user_content = str(user_message) + _MALFORMED_RETRY_SUFFIX
            retry_message = await self._call_sdk_with_transport_retry(
                self._build_request(
                    system_prompt=system_prompt,
                    user_content=retry_user_content,
                    schema=schema,
                )
            )
            try:
                plan, response_text = self._parse_response(retry_message, schema)
            except ValueError as second_error:
                second_error_summary = str(second_error)
                self._emit_protocol_violation(first_error_summary, second_error_summary)
                raise LeafProtocolViolation(
                    first_error_summary, second_error_summary
                ) from second_error
            sdk_message = retry_message
        else:
            sdk_message = first_message

        usage = sdk_message.usage
        tokens_in = _token_count_or_zero(getattr(usage, "input_tokens", 0))
        tokens_out = _token_count_or_zero(getattr(usage, "output_tokens", 0))
        cache_read = _token_count_or_zero(getattr(usage, "cache_read_input_tokens", 0))
        cache_creation = _token_count_or_zero(getattr(usage, "cache_creation_input_tokens", 0))
        response_id = LeafResponseId(str(getattr(sdk_message, "id", "msg_unknown")))
        stop_reason = _project_stop_reason(getattr(sdk_message, "stop_reason", None))

        leaf_response = LeafResponse(
            plan=plan,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
            model=self._model,
            stop_reason=stop_reason,
            response_id=response_id,
        )
        self._emit_returned(
            response_digest=_response_digest(response_text),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )
        return leaf_response
