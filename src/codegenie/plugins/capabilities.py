"""``Capability`` tokens + ``mint()`` chokepoint — S4-05 / 03-ADR-0011.

**Honest framing (03-ADR-0011 §Decision §Capability tokens).** These models
are **audit + lint enforcement**, NOT runtime unforgeability. Pydantic models
can be constructed anywhere in the codebase that imports them; the type
system doesn't know its caller. The defence is two-tiered:

1. **File-level chokepoint** — :func:`mint` is the only function in this
   module that constructs ``*Capability`` instances. Enforced by an AST walk
   in :mod:`tests.unit.plugins.test_capabilities` over
   ``inspect.getsource(capabilities)``.
2. **Repo-wide audit + lint** — :mod:`codegenie._capability_fence` AST-walks
   ``src/codegenie/`` and reports any ``*Capability(...)`` construction
   outside this module and ``tests/``. Consumed from
   :mod:`tests.fence.test_capability_fence`.

Every :func:`mint` call emits a :class:`CapabilityMinted` event through the
module-level chokepoint ``_emit_capability_minted``. S6-01 lands the real
two-stream event log; until then the chokepoint is a no-op shim — but it's
a *real function definition*, not a try/except ImportError swallow, so the
monkeypatch test in S4-05 can substitute a spy without import-time binding
games.

**:class:`GitLocalOpsCapability` has no ``push`` field.** Minting one is
type-impossible. This IS a real type-level invariant — for one specific
operation that matters most (per production ADR-0009 — humans always merge).

**:class:`CapabilityBundle` carries exactly one non-None field** (one
:func:`mint` call ⇒ one capability; the aggregator does not represent a
"set of capabilities" in Phase 3). The model_validator catches accidental
over-construction.

Sources:

- 03-ADR-0011 §Decision §Capability tokens.
- ``docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md``
  §Component design C10 — Capability tokens.
- ``docs/phases/03-vuln-deterministic-recipe/stories/
  S4-05-allowed-binaries-capabilities.md`` — story.
"""

from __future__ import annotations

import hashlib
from typing import Final, TypeAlias, assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator

from codegenie.plugins.sandbox_path import SandboxedPath
from codegenie.types.identifiers import PluginId, RegistryUrl

__all__: Final[tuple[str, ...]] = (
    "CapabilityBundle",
    "CapabilityMinted",
    "CapabilityScope",
    "FsReadWriteCapability",
    "FsScope",
    "GitLocalOpsCapability",
    "GitLocalOpsScope",
    "NpmInstallCapability",
    "NpmScope",
    "mint",
)


# ───────────────────────────────────────────────────────────────────────────
# CapabilityScope sum type (ADR-0010 §Decision §1 — make illegal states
# unrepresentable). Each variant carries exactly the inputs ``mint()`` needs
# to construct its corresponding capability.
# ───────────────────────────────────────────────────────────────────────────


class NpmScope(BaseModel):
    """Scope for minting an :class:`NpmInstallCapability`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    registry: RegistryUrl


class FsScope(BaseModel):
    """Scope for minting an :class:`FsReadWriteCapability`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: SandboxedPath


class GitLocalOpsScope(BaseModel):
    """Scope for minting a :class:`GitLocalOpsCapability`.

    No ``push`` field — the GitLocalOps scope models *local* operations only.
    The scope mirrors the capability shape: a workflow that wants ``push``
    cannot even express it through the scope type.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: SandboxedPath
    branch_namespace: str


CapabilityScope: TypeAlias = NpmScope | FsScope | GitLocalOpsScope
"""Closed sum type — every :func:`mint` call dispatches on the concrete
variant via ``isinstance``. ``assert_never`` in the final else pins
exhaustiveness at type-check time."""


# ───────────────────────────────────────────────────────────────────────────
# Capability tokens — frozen Pydantic models. ``mint()`` is the only legal
# constructor (enforced by audit + lint; see module docstring).
# ───────────────────────────────────────────────────────────────────────────


class NpmInstallCapability(BaseModel):
    """Permission to invoke ``npm install`` against ``registry``.

    Honest framing per 03-ADR-0011: audit + lint enforcement, NOT runtime
    unforgeability. ``mint()`` is the only legal constructor; the
    :mod:`codegenie._capability_fence` walker reports any construction
    outside :mod:`codegenie.plugins.capabilities` and ``tests/``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    registry: RegistryUrl
    minted_by: PluginId = Field(..., alias="_minted_by")


class FsReadWriteCapability(BaseModel):
    """Permission to read + write under ``scope`` (an in-jail
    :class:`SandboxedPath`).

    Honest framing per 03-ADR-0011: audit + lint enforcement. The
    :class:`SandboxedPath` is itself in-jail-at-construction only — TOCTOU
    is acknowledged and the second-line defence lives at
    :meth:`SandboxedPath.open` time via ``O_NOFOLLOW``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    scope: SandboxedPath
    minted_by: PluginId = Field(..., alias="_minted_by")


class GitLocalOpsCapability(BaseModel):
    """Permission to perform local git operations under ``repo`` and within
    ``branch_namespace``.

    This capability has no push field — minting a push capability is
    type-impossible. The framing pins production ADR-0009 (humans always
    merge) at the type level: 03-ADR-0011 names this the one real
    type-level invariant in the capability surface.

    See:

    * 03-ADR-0011 §Decision §Capability tokens — type-level invariant.
    * production ADR-0009 (humans always merge) — the autonomy boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    repo: SandboxedPath
    branch_namespace: str
    minted_by: PluginId = Field(..., alias="_minted_by")


# ───────────────────────────────────────────────────────────────────────────
# CapabilityBundle — aggregator with the exactly-one validator (Sub-4).
# ───────────────────────────────────────────────────────────────────────────


class CapabilityBundle(BaseModel):
    """Aggregator returned by :func:`mint`. Exactly one of ``npm``, ``fs``,
    ``git`` is non-None per bundle — one mint call serves one scope, so the
    aggregator represents *the* minted capability, not a set.

    Constructing :class:`CapabilityBundle` with zero or two non-None fields
    raises ``ValidationError`` (the ``_validate_exactly_one`` validator).
    When the design needs to mint multiple capabilities at once, the bundle
    becomes a ``tuple[Capability, ...]`` and this validator is replaced —
    until then the constrained shape catches accidental over-construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    npm: NpmInstallCapability | None = None
    fs: FsReadWriteCapability | None = None
    git: GitLocalOpsCapability | None = None

    @model_validator(mode="after")
    def _validate_exactly_one(self) -> CapabilityBundle:
        non_none = [name for name in ("npm", "fs", "git") if getattr(self, name) is not None]
        if len(non_none) != 1:
            raise ValueError(
                f"CapabilityBundle must carry exactly one non-None capability; "
                f"got {len(non_none)} ({non_none!r})"
            )
        return self


# ───────────────────────────────────────────────────────────────────────────
# CapabilityMinted event + forward-shim sink.
# ───────────────────────────────────────────────────────────────────────────


class CapabilityMinted(BaseModel):
    """Spanning event emitted from :func:`mint`.

    S6-01 lands the real two-stream event log that consumes these events;
    until then the sink is the module-level :func:`_emit_capability_minted`
    no-op. ``bundle_digest`` is a SHA-256 hex digest over the bundle's
    canonical JSON serialisation; the digest is deterministic so a second
    :func:`mint` call with identical inputs produces a byte-identical
    digest — the audit chain is replayable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: PluginId
    bundle_digest: str


def _emit_capability_minted(event: CapabilityMinted) -> None:
    """Forward-shim sink for :class:`CapabilityMinted` events.

    Defined here as a module-level function (NOT a re-imported alias from
    :mod:`codegenie.plugins.events`) so monkeypatch substitution at
    ``codegenie.plugins.capabilities._emit_capability_minted`` is observable
    from inside :func:`mint`. A top-of-module ``from codegenie.plugins.events
    import emit_capability_minted`` would bind the symbol at import time
    and defeat the monkeypatch.

    Today's body is a true no-op — when S6-01 lands the two-stream event
    log, that story rewires the sink (either by attribute assignment at
    orchestrator init or by replacing the body).
    """
    del event  # no-op until S6-01


def _digest_bundle(bundle: CapabilityBundle) -> str:
    """Return a deterministic SHA-256 hex digest over the bundle's canonical
    JSON serialisation. ``model_dump_json`` is deterministic in Pydantic v2
    (stable field-ordering); the digest is therefore replayable across runs.
    Algorithm pinned to SHA-256 — BLAKE3 would require an additional
    runtime dep that 02-ADR-0001 keeps off the gather closure."""
    canonical = bundle.model_dump_json()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ───────────────────────────────────────────────────────────────────────────
# mint() — the only chokepoint for constructing ``*Capability`` instances.
# Enforced by AST tests (this module) and a repo-wide fence walker (S4-05).
# ───────────────────────────────────────────────────────────────────────────


def mint(plugin: PluginId, scope: CapabilityScope) -> CapabilityBundle:
    """Mint a :class:`CapabilityBundle` for *plugin* targeting *scope*.

    The only legal constructor for ``*Capability`` instances. Dispatches on
    the concrete :class:`CapabilityScope` variant; ``assert_never`` in the
    final else pins exhaustiveness at type-check time (mypy --strict) and
    catches a fifth-variant addition that forgot the dispatch arm.

    Emits a :class:`CapabilityMinted` event via the module-level
    :func:`_emit_capability_minted` sink (forward-shim; rewired by S6-01).
    """
    if isinstance(scope, NpmScope):
        bundle = CapabilityBundle(
            npm=NpmInstallCapability(registry=scope.registry, _minted_by=plugin),
        )
    elif isinstance(scope, FsScope):
        bundle = CapabilityBundle(
            fs=FsReadWriteCapability(scope=scope.scope, _minted_by=plugin),
        )
    elif isinstance(scope, GitLocalOpsScope):
        bundle = CapabilityBundle(
            git=GitLocalOpsCapability(
                repo=scope.repo,
                branch_namespace=scope.branch_namespace,
                _minted_by=plugin,
            ),
        )
    else:
        assert_never(scope)

    _emit_capability_minted(
        CapabilityMinted(plugin_id=plugin, bundle_digest=_digest_bundle(bundle))
    )
    return bundle
