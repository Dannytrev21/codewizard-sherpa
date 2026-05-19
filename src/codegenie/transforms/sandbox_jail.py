"""Phase-3 ``SubprocessJail`` Port — Hexagonal substrate-agnostic surface (S4-01).

This module is the Phase-3 commitment to **ports-before-adapters**
(``phase-arch-design.md §Component design C8``, §Design patterns applied row 3):
a single ``Protocol`` plus frozen Pydantic value types for the inputs and a
discriminated-union ``JailedSubprocessResult`` for the outputs. The Adapters
that implement this Protocol are S4-02 (Linux / ``bwrap``) and S4-03
(macOS / ``sandbox-exec``); Phase 5's ``FirecrackerAdapter`` and
``DinDAdapter`` substitute via the same Port with zero domain edits
(production ADR-0012).

The contract surface this module ships:

* :class:`SubprocessJail` — Protocol; one async method ``run(spec) -> result``.
  Intentionally NOT ``@runtime_checkable`` — Python's runtime Protocol check
  ignores method signatures (a class with any ``run`` attribute would pass),
  so ``isinstance(jail, SubprocessJail)`` is a foot-gun. Structural typing
  at type-check time is the only discipline; AC-2 fences the negative.
* :class:`JailedSubprocessSpec` — frozen + ``extra="forbid"`` value type;
  ``cmd: tuple[str, ...]`` (non-empty), ``cwd: SandboxedPath``, ``env``
  discriminated union, ``network`` discriminated union, ``time_budget_s``,
  ``memory_mib``, ``pids_max``. Field-level smart-constructor validators
  reject zero / negative / non-finite inputs.
* :data:`JailedSubprocessResult` — ``Annotated[Completed | TimedOut |
  OomKilled | NetworkDenied | DiskQuotaExceeded, Field(discriminator="kind")]``.
  Every variant frozen + ``extra="forbid"``; every observable numeric counter
  is non-negative (validators on each variant). The umbrella deliberately
  forbids untyped escape hatches (no untyped dict; no bare exceptions
  returned) — every failure mode is a discriminated variant.
* :data:`JailedEnv` — ``Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]``
  typed env wrapper. ``NpmEnv.to_env_mapping()`` *unconditionally* sets
  ``npm_config_ignore_scripts="true"`` — the env half of ADR-0006's split
  defence (the CLI half lives at the consumer's ``cmd``). ``GitEnv``
  unconditionally sets ``GIT_TERMINAL_PROMPT="0"`` and
  ``GIT_ASKPASS="/bin/false"``. Neither model carries a public field whose
  name contains the env-key — no extension trapdoor.
* :data:`NetworkPolicy` — ``Annotated[DenyAll | RegistryAllowlist,
  Field(discriminator="kind")]``. ``RegistryAllowlist.hosts`` is a
  ``frozenset[RegistryUrl]``; field validator rejects empty allowlists and
  any host not starting with ``https://`` (the smart constructor for the
  ``RegistryUrl`` strict-``https://`` semantic that ``NewType`` documents
  but cannot enforce at runtime — see
  ``src/codegenie/types/identifiers.py:71``).

ADRs honoured: phase-3 ADR-0006 (this Port + bwrap/sandbox-exec adapters),
phase-3 ADR-0007 (run ``npm install`` / ``npm test`` in the jail —
consumer), phase-3 ADR-0010 (sum-type + smart-constructor discipline),
phase-3 ADR-0011 (honest framing — ``SandboxedPath`` is in-jail-at-construction
NOT runtime-unforgeable; ``--ignore-scripts`` is *audit + structural* not
runtime-prevented inside npm), production ADR-0012 (microVM substitution
at Phase 5 substitutes via this same Port), production ADR-0033 (sum types
over booleans).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import RegistryUrl

__all__ = [
    "Completed",
    "DenyAll",
    "DiskQuotaExceeded",
    "GitEnv",
    "JailedEnv",
    "JailedSubprocessResult",
    "JailedSubprocessSpec",
    "NetworkDenied",
    "NetworkPolicy",
    "NpmEnv",
    "OomKilled",
    "RegistryAllowlist",
    "SubprocessJail",
    "TimedOut",
]


# ---------------------------------------------------------------------------
# Typed env wrappers — Pydantic models, not raw ``dict[str, str]``.
# Discriminated by ``kind``; ``to_env_mapping`` hard-codes the safety keys
# (no public field carries the env-key substring — no extension trapdoor).
# ---------------------------------------------------------------------------


class NpmEnv(BaseModel):
    """Typed env for npm invocations inside the jail (ADR-0006 §Decision).

    ``to_env_mapping`` ALWAYS emits ``npm_config_ignore_scripts="true"`` —
    the env half of the ``--ignore-scripts`` split defence. The CLI half
    (``--ignore-scripts`` in ``cmd``) lives at the consumer; S4-05's
    capability-fence test ties them together.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["npm"] = "npm"

    def to_env_mapping(self) -> dict[str, str]:
        return {"npm_config_ignore_scripts": "true"}


class GitEnv(BaseModel):
    """Typed env for git invocations inside the jail (ADR-0006 cross-ref to
    S6-04 ``LocalGitOps``). Disables terminal prompts + askpass leakage."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["git"] = "git"

    def to_env_mapping(self) -> dict[str, str]:
        return {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/false",
        }


JailedEnv = Annotated[NpmEnv | GitEnv, Field(discriminator="kind")]
"""Discriminated union over jail-aware env wrappers — OCP-correct extension
path: adding a third env type is one new model + one ``Literal`` row, no
changes to existing dispatch."""


# ---------------------------------------------------------------------------
# Network policy — discriminated union; ``RegistryAllowlist.hosts`` smart
# constructor enforces the strict-``https://`` semantic at the boundary.
# ---------------------------------------------------------------------------


class DenyAll(BaseModel):
    """No egress permitted. Default-deny baseline for ``npm test`` /
    deterministic recipes that should not need any network."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["deny_all"] = "deny_all"


class RegistryAllowlist(BaseModel):
    """Egress permitted only to the listed hosts. Each host must be a strict
    ``https://`` URL; empty allowlists are rejected (use :class:`DenyAll`
    instead — the empty allowlist is meaningless and a likely bug)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["registry_allowlist"] = "registry_allowlist"
    hosts: frozenset[RegistryUrl]

    @field_validator("hosts", mode="after")
    @classmethod
    def _hosts_non_empty_and_https(cls, value: frozenset[RegistryUrl]) -> frozenset[RegistryUrl]:
        if not value:
            raise ValueError(
                "sandbox_jail.registry_allowlist_empty: use DenyAll instead of "
                "an empty RegistryAllowlist."
            )
        for host in value:
            host_str = str(host)
            if not host_str.startswith("https://"):
                raise ValueError(
                    "sandbox_jail.registry_url_not_https: "
                    f"RegistryUrl must start with 'https://'; got {host_str!r}."
                )
            # Reject malformed ``https:/`` (single slash) — startswith above
            # only catches the prefix; ``https:/foo`` would pass startswith.
            if not host_str.startswith("https://") or "://" not in host_str:
                raise ValueError(
                    "sandbox_jail.registry_url_malformed: "
                    f"RegistryUrl missing scheme separator; got {host_str!r}."
                )
        return value


NetworkPolicy = Annotated[DenyAll | RegistryAllowlist, Field(discriminator="kind")]
"""Discriminated union; substrate adapters dispatch on ``kind``."""


# ---------------------------------------------------------------------------
# Result variants — every failure mode is a typed variant. The Port
# deliberately forbids untyped escape hatches (no untyped mapping returns;
# no bare exceptions) so adapters cannot lose information at the boundary.
# ---------------------------------------------------------------------------


class Completed(BaseModel):
    """Process exited cleanly (or with a non-zero exit code that is still a
    well-formed exit). Carries byte *sizes*, not byte contents — the
    adapter redirects full content to a ``SandboxedPath``-rooted log file
    outside this envelope to avoid leaking secrets through ``RepoContext``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["completed"] = "completed"
    # OS exit codes can be negative on signal-termination; do NOT pin ``ge=0``.
    exit_code: int
    stdout_bytes: int = Field(ge=0)
    stderr_bytes: int = Field(ge=0)
    wall_time_s: float = Field(ge=0)

    @field_validator("wall_time_s", mode="after")
    @classmethod
    def _wall_time_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("sandbox_jail.wall_time_not_finite: wall_time_s must be finite.")
        return value


class TimedOut(BaseModel):
    """Adapter killed the process after ``budget_s`` elapsed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["timed_out"] = "timed_out"
    budget_s: float = Field(gt=0)
    elapsed_s: float = Field(gt=0)

    @field_validator("budget_s", "elapsed_s", mode="after")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("sandbox_jail.timed_out_not_finite: budget/elapsed must be finite.")
        return value


class OomKilled(BaseModel):
    """Kernel / cgroup killed the process for exceeding ``memory_mib``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["oom_killed"] = "oom_killed"
    peak_rss_mib: int = Field(ge=0)


class NetworkDenied(BaseModel):
    """Adapter blocked egress to a non-allowlisted host. ``host`` is
    observable per ADR-0006 §Decision so the operator can debug a
    ``.npmrc`` redirect (Edge case E7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["network_denied"] = "network_denied"
    host: str = Field(min_length=1)


class DiskQuotaExceeded(BaseModel):
    """Adapter aborted the process for writing more bytes than the jail's
    tmpfs / quota permits."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["disk_quota_exceeded"] = "disk_quota_exceeded"
    quota_bytes: int = Field(ge=0)
    bytes_written: int = Field(ge=0)


JailedSubprocessResult = Annotated[
    Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded,
    Field(discriminator="kind"),
]
"""Tagged-union return of :meth:`SubprocessJail.run`. Every consumer
``match``-es with ``assert_never`` in the wildcard arm; the S1-05
exhaustiveness AST fence + S4-01 AC-9a mypy-narrowing fence both pin
this discipline."""


# ---------------------------------------------------------------------------
# Spec — frozen value type passed to ``SubprocessJail.run``.
# ---------------------------------------------------------------------------


class JailedSubprocessSpec(BaseModel):
    """Frozen value type describing a single jailed subprocess invocation.

    Every field carries a smart-constructor bound at the type level. The
    spec is *immutable* — adapters cannot mutate the spec they were handed,
    eliminating a class of "log says X, sandbox ran Y" forensic failures.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cmd: tuple[str, ...] = Field(min_length=1)
    cwd: SandboxedPath
    env: JailedEnv
    network: NetworkPolicy
    time_budget_s: float = Field(gt=0)
    memory_mib: int = Field(ge=1)
    pids_max: int = Field(ge=1)

    @field_validator("time_budget_s", mode="after")
    @classmethod
    def _time_budget_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("sandbox_jail.time_budget_not_finite: time_budget_s must be finite.")
        return value


# ---------------------------------------------------------------------------
# Port — Hexagonal Protocol; intentionally NOT ``@runtime_checkable``.
# ---------------------------------------------------------------------------


class SubprocessJail(Protocol):
    """Hexagonal Port over the subprocess-jail substrate (ADR-0006).

    The single method ``run`` accepts a frozen :class:`JailedSubprocessSpec`
    and returns a tagged-union :data:`JailedSubprocessResult`. Adapters
    (S4-02 ``BwrapAdapter`` on Linux, S4-03 ``SandboxExecAdapter`` on
    macOS, Phase 5 ``FirecrackerAdapter`` / ``DinDAdapter``) implement
    this Protocol by structural conformance only — the class is *not*
    decorated with ``@runtime_checkable`` because Python's runtime
    Protocol check ignores method signatures, making
    ``isinstance(jail, SubprocessJail)`` a foot-gun.

    Async-vs-sync — ADR-0006 §Consequences defers the choice between a
    thread-pooled blocking spawn and an asyncio-native one to each adapter
    (S4-02 / S4-03); the Port only commits to the ``async`` shape.
    """

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        """Run ``spec.cmd`` inside the substrate-specific jail; return a
        typed-variant result. Must never return ``None`` or raise a bare
        ``Exception`` — every failure mode is a typed variant
        (ADR-0006 §Tradeoffs row 4)."""
        ...


# ---------------------------------------------------------------------------
# Module-level TypeAdapter caches — exposed for the S6-06 contract-snapshot
# integration test and any adapter that needs to validate untrusted JSON
# input (Phase 5's ``FirecrackerAdapter`` reads a JSON-RPC envelope).
# ---------------------------------------------------------------------------

_RESULT_ADAPTER: TypeAdapter[JailedSubprocessResult] = TypeAdapter(JailedSubprocessResult)
"""Cached adapter — Pydantic v2 ``TypeAdapter`` construction is non-trivial
and the result is hot path for adapters validating subprocess output."""
