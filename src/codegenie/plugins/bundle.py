"""S3-04 — ``BundleBuilder`` with deterministic serial fallback (ADR-0008).

Dispatches a plugin's composed TCCM (``must_read`` / ``should_read`` /
``may_read``) through a typed ``AdapterDispatch`` seam and returns a typed
``Bundle``. Concurrency is bounded by a **per-call**
``asyncio.Semaphore(min(4, os.cpu_count() or 1))`` overridable via the
``CODEGENIE_BUNDLE_CONCURRENCY`` environment variable.

Fallback semantics is the load-bearing decision. Phase-3 ADR-0008 is
veto-strength: hedged-race composition is rejected because two runs against
the same inputs would return different ``Bundle`` bytes (scheduler noise),
violating production design §2.4's "same inputs → same Transform bytes"
commitment. The TCCM-declared ``fallback`` query fires **only** when the
primary's ``confidence`` is the ``Degraded`` or ``Unavailable`` variant of
``AdapterConfidence`` — never raced, never both. The fallback walker
``_resolve_chain`` is iterative (not recursive) and never re-acquires the
semaphore.

ADRs honored:

- Phase-3 ADR-0008 — declarative serial fallback (Option C); ``vuln_index``
  digest joins the Bundle cache key (cache layer lands in S3-05).
- Phase-3 ADR-0010 — tagged-union / ``Literal`` discipline. Dispatch on
  ``AdapterConfidence`` uses ``match`` + ``assert_never``; never
  set-membership against class identities.
- Phase-3 ADR-0011 — ``SandboxedPath`` (honest framing for Phase 3;
  audit-grade until S4-04 replaces it).
- Production ADR-0029 — TCCM ``must_read`` / ``should_read`` / ``may_read``.
  Phase 3 executes all three eagerly; deferred ``may_read`` execution is a
  Phase 6+ concern.
- Production ADR-0030 — graph-aware context-query primitives (the closed
  five-name set carried by :data:`codegenie.plugins.tccm._KNOWN_PRIMITIVES`).
- Production ADR-0032 — language-search adapters expose ``confidence()`` and
  a typed ``AdapterResult``; the ``AdapterDispatch`` callable seam bridges
  this story to S7-02's per-protocol adapter wiring.

``AdapterDegraded`` and ``FallbackChainTooDeep`` are defined here for S3-04;
S6-01 may re-export them from ``codegenie.events.bundle`` without rename.
The ``event_emitter=None`` default keeps this story testable without S6-01.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import (
    Annotated,
    Final,
    Literal,
    Protocol,
    assert_never,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field

from codegenie.adapters.confidence import (
    AdapterConfidence,
    Degraded,
    Trusted,
    Unavailable,
)
from codegenie.errors import CodegenieError
from codegenie.plugins.tccm import TCCM, ContextQuery
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import BlobDigest, PluginId, PrimitiveName

__all__ = [
    "AdapterDegraded",
    "AdapterDispatch",
    "AdapterResult",
    "Bundle",
    "BundleBuilder",
    "BundleBuilderError",
    "BundleBuilderEvent",
    "BundleBuilderRaise",
    "BundleEntry",
    "BundleResolution",
    "FallbackChainTooDeep",
]


# --- Constants --------------------------------------------------------------

_MAX_FALLBACK_DEPTH: Final[int] = 4
"""Maximum allowed fallback chain depth (mirrors S2-04 ``extends``-chain cap).

A 4-deep chain ``D → D → D → T`` succeeds (3 ``AdapterDegraded`` events).
A 5-deep all-degraded chain raises ``BundleBuilderRaise`` with
``details["depth"] == 5`` after emitting 4 ``AdapterDegraded`` plus 1
``FallbackChainTooDeep``."""

_CONCURRENCY_ENV_VAR: Final[str] = "CODEGENIE_BUNDLE_CONCURRENCY"


# --- Pure helpers -----------------------------------------------------------


def _read_concurrency_bound() -> int:
    """Read the per-call concurrency bound for ``BundleBuilder.build``.

    Empty / whitespace / unset → ``min(4, os.cpu_count() or 1)``.
    Anything that parses as a positive ``int`` (including ``"+4"``) → that int.
    Anything else → :class:`BundleBuilderRaise` with
    ``reason="invalid_concurrency_env"``.

    Pure helper (called per-construction, NOT at module import); rejection of
    ``"0"`` is veto-strength — ``Semaphore(0)`` would deadlock."""

    raw = os.environ.get(_CONCURRENCY_ENV_VAR)
    if raw is None or raw.strip() == "":
        cpu = os.cpu_count() or 1
        return min(4, cpu)
    # int() accepts leading "+"; reject anything else loudly.
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise BundleBuilderRaise(
            error=BundleBuilderError(
                reason="invalid_concurrency_env",
                details={"value": raw},
            )
        ) from exc
    if parsed <= 0:
        raise BundleBuilderRaise(
            error=BundleBuilderError(
                reason="invalid_concurrency_env",
                details={"value": raw},
            )
        )
    return parsed


def _canonicalize_args(
    args: Mapping[str, str | int | bool | list[str]],
) -> str:
    """Canonical-JSON encoding of ``ContextQuery.args`` (S3-05 cache-key input).

    Pinned: ``json.dumps(args, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False)``. Byte-stable across insertion-order — S3-05 hashes
    this with BLAKE3."""

    return json.dumps(dict(args), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- Error model ------------------------------------------------------------


class BundleBuilderError(BaseModel):
    """Typed error payload for :class:`BundleBuilderRaise`.

    Frozen Pydantic ``BaseModel`` (mirrors S3-01 ``TCCMParseError`` precedent),
    NOT an ``Exception`` subclass — the markers-only discipline forbids fields
    on ``CodegenieError`` subclasses, and we need a typed ``.reason`` /
    ``.details`` payload at the catch site.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal[
        "invalid_concurrency_env",
        "fallback_chain_too_deep",
        "missing_dispatch",
    ]
    details: dict[str, str | int] = {}


class BundleBuilderRaise(CodegenieError):
    """Thin ``CodegenieError`` wrapper that carries a typed
    :class:`BundleBuilderError` payload via ``.error``.

    The marker-only discipline lives on the :mod:`codegenie.errors` taxonomy;
    this raise-class is local to :mod:`codegenie.plugins.bundle` and is the
    boundary where typed ``BundleBuilderError`` payloads become ``raise``-able.
    """

    def __init__(self, *, error: BundleBuilderError) -> None:
        self.error: BundleBuilderError = error
        super().__init__(error.model_dump_json())


# --- AdapterResult + dispatch seam -----------------------------------------


class AdapterResult(BaseModel):
    """Result returned by an :data:`AdapterDispatch` callable.

    ``payload`` is primitive-only (matches Phase 3 ``TrustSignal.details``
    discipline); ``confidence`` is the :data:`AdapterConfidence` tagged union;
    ``adapter_name`` is the human-readable adapter identity used in
    :class:`AdapterDegraded` events and :class:`BundleEntry`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: dict[str, str | int | bool | list[str]]
    confidence: AdapterConfidence
    adapter_name: str


AdapterDispatch = Callable[[ContextQuery], Awaitable[AdapterResult]]
"""Typed callable seam — production wiring (mapping ``"scip.refs" ->
scip_adapter.refs``, etc.) lives in S7-02; this story consumes the seam."""


# --- Bundle entries ---------------------------------------------------------


class BundleEntry(BaseModel):
    """One typed entry in a :class:`Bundle`.

    ``fallback_used`` is ``True`` iff the TCCM-declared fallback fired at
    least once (the primary returned ``Degraded`` or ``Unavailable`` and a
    ``fallback`` query was declared and dispatched)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primitive: PrimitiveName
    args_canonical: str
    payload: dict[str, str | int | bool | list[str]]
    confidence: AdapterConfidence
    fallback_used: bool
    adapter_name: str


class Bundle(BaseModel):
    """Result of :meth:`BundleBuilder.build` — typed handoff to S3-05 cache /
    S6-04 orchestrator. ``entries`` is a tuple for hash-stability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[BundleEntry, ...]
    plugin_id: PluginId
    vuln_index_digest: BlobDigest


# --- Events ----------------------------------------------------------------


class AdapterDegraded(BaseModel):
    """Emitted **before** the fallback dispatch fires (operator visibility —
    "we're falling back" not "we fell back"). ``reason`` propagates verbatim
    from the primary's ``Degraded(reason=...)`` or ``Unavailable(reason=...)``
    variant — Goal G8 ``TrustScorer.confidence`` folding (S6-02) reads this."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["adapter_degraded"] = "adapter_degraded"
    primitive: PrimitiveName
    adapter_name: str
    reason: str


class FallbackChainTooDeep(BaseModel):
    """Emitted before :class:`BundleBuilderRaise` so operators see WHY the
    cap fired (the trigger is otherwise invisible in an exception traceback)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["fallback_chain_too_deep"] = "fallback_chain_too_deep"
    primitive: PrimitiveName
    depth: int


BundleBuilderEvent = Annotated[
    AdapterDegraded | FallbackChainTooDeep,
    Field(discriminator="kind"),
]


# --- Resolution boundary (structural) --------------------------------------


@runtime_checkable
class BundleResolution(Protocol):
    """Structural input boundary for :meth:`BundleBuilder.build`.

    S7-02 will produce a concrete :class:`ConcreteResolution` extension that
    satisfies this shape; tests construct ad-hoc fakes. The ``composed_tccm``
    is the Phase-3 :class:`TCCM` Pydantic model (S3-01)."""

    @property
    def composed_tccm(self) -> TCCM: ...

    @property
    def composed_dispatch(self) -> Mapping[PrimitiveName, AdapterDispatch]: ...

    @property
    def plugin_id(self) -> PluginId: ...


@runtime_checkable
class _VulnIndexLike(Protocol):
    """``vuln_index.digest()`` — :class:`codegenie.vuln_index.index.VulnIndex`
    is the production implementation (S3-02); tests pass duck-typed fakes."""

    def digest(self) -> BlobDigest: ...


# --- Pure compose-entry ----------------------------------------------------


def _compose_entry(
    query: ContextQuery,
    primary: AdapterResult,
    fallback: AdapterResult | None,
) -> BundleEntry:
    """Pure fold producing a :class:`BundleEntry` from a query plus the
    primary's result (always present) and the fallback's result (only when a
    fallback step actually executed).

    No I/O, no ``await``, no event emission, no logging — the AST static
    defense in ``tests/static/test_no_hedged_race_in_bundle.py`` pins this."""

    if fallback is None:
        return BundleEntry(
            primitive=query.primitive,
            args_canonical=_canonicalize_args(query.args),
            payload=primary.payload,
            confidence=primary.confidence,
            fallback_used=False,
            adapter_name=primary.adapter_name,
        )
    return BundleEntry(
        primitive=query.primitive,
        args_canonical=_canonicalize_args(query.args),
        payload=fallback.payload,
        confidence=fallback.confidence,
        fallback_used=True,
        adapter_name=fallback.adapter_name,
    )


# --- Iterative fallback walker ---------------------------------------------


async def _resolve_chain(
    root_query: ContextQuery,
    dispatch_table: Mapping[PrimitiveName, AdapterDispatch],
    emit: Callable[[BundleBuilderEvent], None],
) -> BundleEntry:
    """Walk a TCCM-declared fallback chain serially (ADR-0008).

    Never acquires the semaphore — the caller (``_acquire_then_dispatch``)
    holds it for the full chain. Iterative: a recursive impl would either
    burn stack frames or surface confusing "depth held the lock" semantics.
    """

    current: ContextQuery = root_query
    depth = 0  # number of fallback advances completed so far
    root_primary: AdapterResult | None = None
    last_result: AdapterResult | None = None

    while True:
        # AC-17 — cap-check happens BEFORE the would-be 5th dispatch (the
        # "5-deep chain, last variant unreachable" semantics). With
        # ``_MAX_FALLBACK_DEPTH = 4`` we permit dispatching at depths
        # 0,1,2,3 and reject the attempt that would be depth=4 (advancing
        # past 4 prior dispatches). The reported ``depth`` is the
        # one-past-current count — operator-readable as "we tried to reach
        # depth 5".
        if depth >= _MAX_FALLBACK_DEPTH:
            next_depth = depth + 1
            emit(
                FallbackChainTooDeep(
                    primitive=root_query.primitive,
                    depth=next_depth,
                )
            )
            raise BundleBuilderRaise(
                error=BundleBuilderError(
                    reason="fallback_chain_too_deep",
                    details={
                        "primitive": str(root_query.primitive),
                        "depth": next_depth,
                    },
                )
            )
        dispatch = dispatch_table.get(current.primitive)
        if dispatch is None:
            raise BundleBuilderRaise(
                error=BundleBuilderError(
                    reason="missing_dispatch",
                    details={"primitive": str(current.primitive)},
                )
            )
        result = await dispatch(current)
        last_result = result
        if root_primary is None:
            root_primary = result

        match result.confidence:
            case Trusted():
                fallback_used = last_result if depth > 0 else None
                return _compose_entry(root_query, root_primary, fallback_used)
            case Degraded() | Unavailable() as failed:
                if current.fallback is None:
                    fallback_used = last_result if depth > 0 else None
                    return _compose_entry(root_query, root_primary, fallback_used)
                # Operator-visible "we are falling back" event — fires BEFORE
                # the fallback dispatch (AC-19).
                emit(
                    AdapterDegraded(
                        primitive=current.primitive,
                        adapter_name=result.adapter_name,
                        reason=failed.reason,
                    )
                )
                depth += 1
                current = current.fallback
            case _ as never:
                assert_never(never)


# --- BundleBuilder ---------------------------------------------------------


class BundleBuilder:
    """Dispatches a plugin's composed TCCM through the
    :data:`AdapterDispatch` seam under a per-call bounded
    ``asyncio.Semaphore`` (AC-11), with declarative serial fallback (ADR-0008).
    """

    def __init__(
        self,
        cache_dir: SandboxedPath,
        *,
        event_emitter: Callable[[BundleBuilderEvent], None] | None = None,
    ) -> None:
        self._cache_dir: SandboxedPath = cache_dir
        self._event_emitter: Callable[[BundleBuilderEvent], None] | None = event_emitter
        # Read the concurrency bound at construction (fail-loud per Rule 12);
        # a bad env var must surface here, not at the first ``build()`` call.
        self._concurrency: int = _read_concurrency_bound()

    async def build(
        self,
        resolution: BundleResolution,
        repo_ctx: object,
        vuln: object,
        vuln_index: _VulnIndexLike,
    ) -> Bundle:
        """Iterate ``must_read`` then ``should_read`` then ``may_read`` and
        return a typed :class:`Bundle`. ``repo_ctx`` and ``vuln`` are
        plumbed-through for future stories (S3-05 cache key, S6-04 trust
        scorer) and intentionally unused here."""

        del repo_ctx, vuln  # consumed in later stories; AC-12 contract is band-iteration
        tccm = resolution.composed_tccm
        dispatch_table = resolution.composed_dispatch

        emit: Callable[[BundleBuilderEvent], None] = (
            self._event_emitter if self._event_emitter is not None else (lambda _e: None)
        )

        # Per-call semaphore (AC-11): two concurrent ``build()`` invocations
        # on the SAME instance get independent slots — a shared semaphore
        # silently serialises workflows.
        semaphore = asyncio.Semaphore(self._concurrency)

        queries: list[ContextQuery] = [
            *tccm.must_read,
            *tccm.should_read,
            *tccm.may_read,
        ]

        if not queries:
            return Bundle(
                entries=(),
                plugin_id=resolution.plugin_id,
                vuln_index_digest=vuln_index.digest(),
            )

        tasks = [_acquire_then_dispatch(semaphore, q, dispatch_table, emit) for q in queries]
        entries = await asyncio.gather(*tasks)

        return Bundle(
            entries=tuple(entries),
            plugin_id=resolution.plugin_id,
            vuln_index_digest=vuln_index.digest(),
        )


async def _acquire_then_dispatch(
    semaphore: asyncio.Semaphore,
    query: ContextQuery,
    dispatch_table: Mapping[PrimitiveName, AdapterDispatch],
    emit: Callable[[BundleBuilderEvent], None],
) -> BundleEntry:
    """Acquire the semaphore exactly ONCE per top-level band-level task, then
    walk the fallback chain inside the held slot. ``_resolve_chain`` itself
    never touches the semaphore (AC-16)."""

    async with semaphore:
        return await _resolve_chain(query, dispatch_table, emit)
