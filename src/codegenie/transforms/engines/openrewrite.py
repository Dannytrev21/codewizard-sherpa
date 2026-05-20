"""Phase-3 S5-03 — :class:`OpenRewriteRecipeEngine` scaffold +
:class:`DockerfileBaseImageTransform`.

The **second** day-1 :class:`~codegenie.transforms.recipe_engine.RecipeEngine`
(ADR-0009 Option C). Where :class:`~codegenie.transforms.engines.npm_lockfile
.NpmLockfileRecipeEngine` is the *production* engine every Phase-3 npm
remediation routes through, this engine is *scaffolded*: Protocol-conformant,
JVM-subprocess-wrapped in the :class:`SubprocessJail` Port, ships one
Phase-7-tagged Dockerfile-base-image-swap fixture — and is **never invoked by
any Phase-3 npm workflow** (pinned by ``tests/fence/test_openrewrite_not_invoked_phase3.py``).

The scaffold pays the "two genuine implementations from day one" rent ADR-0009
commits to: a :class:`RecipeEngine` Protocol with a single implementation
would be the toolkit's textbook "Strategy with one strategy = unnecessary
indirection" anti-pattern. With this scaffold, Phase 7's distroless plugin
adds Dockerfile-rewrite recipes as a *recipe addition* — not an engine +
recipe + dispatch invention under the "zero edits to existing code" exit
criterion.

The scaffold is structurally complete but functionally inert. ``apply``
builds the JVM :class:`JailedSubprocessSpec`, awaits the jail, and maps the
typed result; it does **not** parse OpenRewrite's stdout into structured
recipe-application results — that is Phase 7's job. The integration test that
actually spawns ``java`` is gated behind ``@pytest.mark.phase_7_preview``
(collected only with ``-m phase_7_preview``; ``java`` is deliberately absent
from ``ALLOWED_BINARIES`` until Phase 7 enables it — ADR-0012).

Per ADR-0014 ``apply`` returns a bare :data:`RecipeOutcome` — the produced
:class:`DockerfileBaseImageTransform` is surfaced via the constructor-injected
:class:`~codegenie.transforms.transform_registry.TransformRegistry`, never as
a tuple. The pure helper :func:`_map_jail_result` keeps the internal
``(outcome, transform)`` tuple (functional core); the impure :meth:`apply`
``register``-s the transform and returns the bare outcome.

Phase 7 will extend by:

* parsing the OpenRewrite CLI's structured stdout into per-recipe results;
* shipping the real Dockerfile-rewrite recipe content (the fixture's
  ``recipe.yml`` is a placeholder);
* widening the ``RecipeEngine.apply`` ``capability`` parameter past the
  Phase-3-narrow :class:`NpmInstallCapability` (a Phase-7 ADR amendment);
* flipping ``@pytest.mark.phase_7_preview`` to a per-PR-required mark and
  adding ``java`` to ``ALLOWED_BINARIES``.

ADRs honored: ADR-0009 (this engine is the second day-1 implementation),
ADR-0006 (``SubprocessJail`` Port; the boundary that wraps the JVM
subprocess — and its 2026-05-20 ``JvmEnv`` amendment), ADR-0012 (``java``
NOT in ``ALLOWED_BINARIES`` for Phase 3), ADR-0010 (sum-type + newtype
discipline), ADR-0014 (``TransformRegistry`` surfacing), Phase-1 ADR-0007
(dotted-snake ``ErrorId`` taxonomy).
"""

from __future__ import annotations

import difflib
import typing
from datetime import UTC, datetime
from typing import IO, Final, Literal, TypeAlias, assert_never, cast

import blake3

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.result import Ok
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.outcomes import (
    ApplicationPlan,
    Applied,
    RecipeError,
    RecipeFailed,
    RecipeOutcome,
)
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    DiskQuotaExceeded,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    JvmEnv,
    NetworkDenied,
    OomKilled,
    SubprocessJail,
    TimedOut,
)
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import (
    ErrorId,
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    TransformKind,
)

__all__ = ["DockerfileBaseImageTransform", "OpenRewriteRecipeEngine"]


# ---------------------------------------------------------------------------
# Module-top ``Final`` constants — the JVM jail budget envelope, the
# OpenRewrite CLI command shape, and the scaffold's provenance sentinels.
# Open/Closed boundary: Phase 7 re-tunes the budgets in this module; a new
# JVM-ecosystem engine (Phase 8+ Maven / Gradle) adds a sibling module —
# never edits these. The mutation tests (AC-Spec-2) pin each as load-bearing.
# ---------------------------------------------------------------------------

_OPENREWRITE_TIME_BUDGET_S: Final[float] = 300.0
_OPENREWRITE_MEMORY_MIB: Final[int] = 2048
_OPENREWRITE_PIDS_MAX: Final[int] = 64
_OPENREWRITE_CLI_JAR: Final[str] = "/opt/openrewrite/rewrite-cli.jar"  # Phase 7 provisions
_JVM_HEAP_MIB: Final[int] = 1024
_JAVA_HOME: Final[str] = "/opt/java"

# Scaffold provenance sentinels (AC-Smart-2). The engine is never invoked by a
# Phase-3 workflow, so these are fixed placeholders; Phase 7 populates real
# plugin / recipe / capability ids when the distroless plugin actually drives
# the engine.
_SCAFFOLD_PLUGIN_ID: Final[PluginId] = PluginId("scaffold--phase7-preview")
_SCAFFOLD_RECIPE_ID: Final[RecipeId] = RecipeId("dockerfile-base-image-swap")
_SCAFFOLD_TRANSFORM_KIND: Final[TransformKind] = TransformKind("dockerfile_base_image_swap")
_SCAFFOLD_CAPABILITY_USE_ID: Final[EventId] = EventId("scaffold-noop")
_SCAFFOLD_VERSION: Final[str] = "0.0.0"  # semver-shape placeholder

# Fixture file names — the scaffold diffs the pre-image ``Dockerfile`` against
# the side-by-side ``expected.Dockerfile`` (under the ``FakeJail`` scaffold the
# JVM never runs; Phase 7's real JVM path rewrites the file in place).
_DOCKERFILE_NAME: Final[str] = "Dockerfile"
_EXPECTED_DOCKERFILE_NAME: Final[str] = "expected.Dockerfile"
_RECIPE_YML_NAME: Final[str] = "recipe.yml"


# ---------------------------------------------------------------------------
# Error-id taxonomy — a closed ``Literal`` sum (Design-Patterns D2). Adding a
# failure mode is a Literal expansion + a new AC + a new test; deleting one
# re-baselines the Phase-3 contract snapshot (S6-06).
#
# ``recipe.jail_setup_failed`` is the sixth id: the as-built
# ``JailedSubprocessResult`` carries six variants (``JailSetupFailed`` is the
# sixth — S4-01 GREEN), and the ``assert_never`` exhaustive ``match`` in
# ``_map_jail_result`` cannot compile under mypy-strict without an arm for it.
# This mirrors S5-02's identical 13→14 taxonomy correction.
# ---------------------------------------------------------------------------

_OpenRewriteErrorId: TypeAlias = Literal[
    "recipe.openrewrite_nonzero_exit",
    "recipe.network_policy_violation",
    "recipe.jvm_timeout",
    "recipe.jvm_oom",
    "recipe.disk_quota_exceeded",
    "recipe.jail_setup_failed",
]

_ERROR_IDS: Final[frozenset[ErrorId]] = frozenset(
    ErrorId(member) for member in typing.get_args(_OpenRewriteErrorId)
)

_DetailValue: TypeAlias = str | int | bool | float


# ---------------------------------------------------------------------------
# Wall-clock seam — tests monkeypatch this to a frozen instant so
# ``TransformProvenance.applied_at`` is deterministic (AC-Det-1). The
# content-addressed ``transform_id`` digests only ``diff_bytes`` and so is
# clock-independent regardless; the seam keeps the provenance reproducible.
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    """Return the current timezone-aware UTC instant."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Failure-construction helper — lifts a closed-taxonomy error id to the public
# ``RecipeFailed`` outcome. ``error_id`` is type-narrowed so a typo cannot
# escape mypy-strict.
# ---------------------------------------------------------------------------


def _failed(
    error_id: _OpenRewriteErrorId, message: str, details: dict[str, _DetailValue]
) -> RecipeFailed:
    """Build a :class:`RecipeFailed` from the closed error-id taxonomy."""
    return RecipeFailed(
        error=RecipeError(error_id=ErrorId(error_id), message=message, details=details)
    )


# ---------------------------------------------------------------------------
# ``DockerfileBaseImageTransform`` — concrete ``Transform`` ABC subclass
# (S1-04). The smart constructor :meth:`create` is the only sanctioned
# creation path (Design-Patterns D6).
# ---------------------------------------------------------------------------


class DockerfileBaseImageTransform(Transform):
    """The :class:`Transform` produced by :class:`OpenRewriteRecipeEngine`.

    Carries the unified diff of the rewritten ``Dockerfile``, the single
    :class:`SandboxedPath` that changed, and the audit-anchor
    :class:`TransformProvenance`. Declares the four ``Transform`` contract
    attributes as per-instance state (the S5-02 :class:`NpmLockfileTransform`
    shape). The smart constructor :meth:`create` is the only sanctioned
    creation path — an AST-walk fence forbids direct construction outside it."""

    def __init__(
        self,
        *,
        transform_id: TransformId,
        diff_bytes: bytes,
        files_changed: tuple[SandboxedPath, ...],
        provenance: TransformProvenance,
    ) -> None:
        self.transform_id = transform_id
        self.diff_bytes = diff_bytes
        self.files_changed = files_changed
        self.provenance = provenance

    @classmethod
    def create(
        cls,
        *,
        diff_bytes: bytes,
        files_changed: tuple[SandboxedPath, ...],
        provenance: TransformProvenance,
    ) -> DockerfileBaseImageTransform:
        """Smart constructor — the only sanctioned creation path.

        Computes ``transform_id`` as the BLAKE3-hex digest of ``diff_bytes``
        (the content-addressed identity, ADR-0010). Rejects an empty
        ``diff_bytes`` or an empty ``files_changed`` with :class:`ValueError`
        — an empty diff is not a transform, and a transform that changed no
        file is meaningless."""
        if not diff_bytes:
            raise ValueError("diff_bytes must be non-empty")
        if not files_changed:
            raise ValueError("files_changed must be non-empty")
        return cls(
            transform_id=TransformId(blake3.blake3(diff_bytes).hexdigest()),
            diff_bytes=diff_bytes,
            files_changed=files_changed,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# Pure helpers (functional core — AC-Pure-1). No ``await``, no
# ``os`` / ``subprocess`` / ``time`` / ``logging``; the only I/O is reading
# the side-by-side fixture files through a passed-in ``SandboxedPath``.
# ---------------------------------------------------------------------------


def _build_openrewrite_spec(
    repo: SandboxedPath, plan: ApplicationPlan, cli_jar_path: str
) -> JailedSubprocessSpec:
    """Build the JVM :class:`JailedSubprocessSpec` for the OpenRewrite CLI.

    The ``cmd`` invokes ``java -jar <cli> run --recipe <recipe.yml>
    --in-place``; the network policy is :class:`DenyAll` (Dockerfile recipes
    need no egress — the CLI jar is provisioned on-disk by Phase 7); the env
    is the typed :class:`JvmEnv`. ``plan`` is threaded for signature-shape
    parity with :class:`~codegenie.transforms.engines.npm_lockfile
    .NpmLockfileRecipeEngine`; the scaffold reads no field off it."""
    return JailedSubprocessSpec(
        cmd=(
            "java",
            "-jar",
            cli_jar_path,
            "run",
            "--recipe",
            str(repo / _RECIPE_YML_NAME),
            "--in-place",
        ),
        cwd=repo,
        env=JvmEnv(java_home=_JAVA_HOME, max_heap_mib=_JVM_HEAP_MIB),
        network=DenyAll(),
        time_budget_s=_OPENREWRITE_TIME_BUDGET_S,
        memory_mib=_OPENREWRITE_MEMORY_MIB,
        pids_max=_OPENREWRITE_PIDS_MAX,
    )


def _build_unified_diff(before: bytes, after: bytes) -> bytes:
    """Build the ``Dockerfile`` unified diff. Deterministic by construction —
    pure byte input, no ``fromfiledate`` / ``tofiledate`` timestamp arguments
    (AC-Det-2), no inode / random data enters the payload."""
    diff_lines = difflib.unified_diff(
        before.decode("utf-8").splitlines(),
        after.decode("utf-8").splitlines(),
        fromfile=_DOCKERFILE_NAME,
        tofile=_DOCKERFILE_NAME,
        lineterm="",
    )
    body = "\n".join(diff_lines)
    return (body + "\n").encode("utf-8") if body else b""


def _resolve(repo: SandboxedPath, name: str) -> SandboxedPath:
    """Resolve ``name`` under ``repo`` via the :meth:`SandboxedPath.create`
    smart constructor. A scaffold fixture file that will not resolve safely
    under the repo jail is a hard error — surfaced loud (Rule 12)."""
    result = SandboxedPath.create(repo.absolute, name)
    if isinstance(result, Ok):
        return result.value
    raise FileNotFoundError(
        f"openrewrite scaffold: {name!r} not resolvable under the repo jail ({result.error.reason})"
    )


def _read_bytes(path: SandboxedPath) -> bytes:
    """Read the full byte content of ``path`` through :meth:`SandboxedPath.open`
    (``O_NOFOLLOW`` — ADR-0011)."""
    with cast("IO[bytes]", path.open("rb")) as handle:
        return handle.read()


def _build_transform(repo: SandboxedPath, plan: ApplicationPlan) -> DockerfileBaseImageTransform:
    """Build the :class:`DockerfileBaseImageTransform` for a successful apply.

    Under the Phase-3 scaffold the JVM never runs, so the diff is computed
    from the side-by-side fixture (``Dockerfile`` pre-image vs.
    ``expected.Dockerfile`` post-image). Phase 7's real JVM path rewrites
    ``Dockerfile`` in place; the scaffold's two-file shape is the Phase-3
    stand-in. ``plan`` is threaded for signature parity; the scaffold's
    provenance uses fixed sentinels (AC-Smart-2)."""
    dockerfile = _resolve(repo, _DOCKERFILE_NAME)
    before = _read_bytes(dockerfile)
    after = _read_bytes(_resolve(repo, _EXPECTED_DOCKERFILE_NAME))
    diff_bytes = _build_unified_diff(before, after)
    provenance = TransformProvenance(
        plugin_id=_SCAFFOLD_PLUGIN_ID,
        plugin_version=_SCAFFOLD_VERSION,
        recipe_id=_SCAFFOLD_RECIPE_ID,
        recipe_version=_SCAFFOLD_VERSION,
        transform_kind=_SCAFFOLD_TRANSFORM_KIND,
        applied_at=_now_utc(),
        capability_use_id=_SCAFFOLD_CAPABILITY_USE_ID,
    )
    return DockerfileBaseImageTransform.create(
        diff_bytes=diff_bytes,
        files_changed=(dockerfile,),
        provenance=provenance,
    )


def _map_jail_result(
    result: JailedSubprocessResult, plan: ApplicationPlan, repo: SandboxedPath
) -> tuple[RecipeOutcome, Transform | None]:
    """Map the :data:`JailedSubprocessResult` tagged union to an
    ``(outcome, transform)`` pair (functional core).

    The ``match`` is exhaustive over all six variants with ``assert_never``
    in the wildcard arm — adding a seventh variant breaks this mapping under
    mypy-strict until the engine handles it (AC-Map-7). Only the
    ``Completed(exit_code=0)`` arm produces a :class:`Transform`; every
    other arm returns ``(<RecipeFailed>, None)`` so the impure
    :meth:`OpenRewriteRecipeEngine.apply` ``register``-s nothing."""
    match result:
        case Completed(exit_code=0):
            transform = _build_transform(repo, plan)
            outcome: RecipeOutcome = Applied(
                transform_id=transform.transform_id,
                plugin_id=_SCAFFOLD_PLUGIN_ID,
                recipe_id=_SCAFFOLD_RECIPE_ID,
            )
            return outcome, transform
        case Completed(exit_code=exit_code, stderr_bytes=stderr_bytes, wall_time_s=wall_time_s):
            return (
                _failed(
                    "recipe.openrewrite_nonzero_exit",
                    f"openrewrite exited {exit_code}",
                    {
                        "exit_code": exit_code,
                        "stderr_bytes": stderr_bytes,
                        "wall_time_s": wall_time_s,
                    },
                ),
                None,
            )
        case TimedOut(budget_s=budget_s, elapsed_s=elapsed_s):
            return (
                _failed(
                    "recipe.jvm_timeout",
                    "openrewrite exceeded its time budget",
                    {"budget_s": budget_s, "elapsed_s": elapsed_s},
                ),
                None,
            )
        case OomKilled(peak_rss_mib=peak_rss_mib):
            return (
                _failed(
                    "recipe.jvm_oom",
                    "openrewrite was killed for exceeding the memory budget",
                    {"peak_rss_mib": peak_rss_mib},
                ),
                None,
            )
        case NetworkDenied(host=host):
            return (
                _failed(
                    "recipe.network_policy_violation",
                    f"openrewrite attempted egress to a non-allowlisted host: {host}",
                    {"host": host},
                ),
                None,
            )
        case DiskQuotaExceeded(quota_bytes=quota_bytes, bytes_written=bytes_written):
            return (
                _failed(
                    "recipe.disk_quota_exceeded",
                    "openrewrite exceeded the jail disk quota",
                    {"quota_bytes": quota_bytes, "bytes_written": bytes_written},
                ),
                None,
            )
        case JailSetupFailed(reason=reason, detail=detail):
            return (
                _failed(
                    "recipe.jail_setup_failed",
                    "the subprocess jail could not be set up for openrewrite",
                    {"reason": reason, "detail": detail},
                ),
                None,
            )
        case _:  # pragma: no cover — exhaustiveness guard
            assert_never(result)


# ---------------------------------------------------------------------------
# ``OpenRewriteRecipeEngine`` — the scaffolded second day-1 ``RecipeEngine``.
# ---------------------------------------------------------------------------


class OpenRewriteRecipeEngine:
    """Scaffolded OpenRewrite :class:`~codegenie.transforms.recipe_engine
    .RecipeEngine` (ADR-0009 — the second day-1 implementation).

    Both collaborators are constructor-injected (ADR-0014): the
    :class:`SubprocessJail` that would run ``java -jar <openrewrite-cli>``
    and the :class:`TransformRegistry` the produced
    :class:`DockerfileBaseImageTransform` is surfaced through. No
    module-level mutable state, no global registry write at import time.

    The engine is structurally complete — it builds the JVM
    :class:`JailedSubprocessSpec`, conforms to the ``RecipeEngine`` Protocol,
    and maps every :data:`JailedSubprocessResult` variant — but is **never
    invoked by any Phase-3 npm workflow**. See the module docstring for the
    Phase-7 extension surface."""

    def __init__(
        self,
        jail: SubprocessJail,
        transform_registry: TransformRegistry,
        *,
        cli_jar_path: str | None = None,
    ) -> None:
        self._jail = jail
        self._transform_registry = transform_registry
        self._cli_jar_path = cli_jar_path if cli_jar_path is not None else _OPENREWRITE_CLI_JAR

    async def apply(
        self,
        repo: SandboxedPath,
        plan: ApplicationPlan,
        # TODO(Phase-7): widen capability union — OpenRewrite is not npm; the
        # Phase-3-narrow NpmInstallCapability is accepted only to satisfy the
        # S5-01 RecipeEngine Protocol signature. See module docstring +
        # story S5-03 Notes §"Capability mismatch".
        capability: NpmInstallCapability,
    ) -> RecipeOutcome:
        """Run the OpenRewrite CLI under the injected :class:`SubprocessJail`
        and return a bare :data:`RecipeOutcome` (ADR-0014).

        On a clean ``Completed(exit_code=0)`` the produced
        :class:`DockerfileBaseImageTransform` is ``register``-ed into the
        injected :class:`TransformRegistry` and an :class:`Applied` outcome
        carrying its ``transform_id`` is returned; every failure mode is a
        typed :class:`RecipeFailed` from the closed error-id taxonomy."""
        spec = _build_openrewrite_spec(repo, plan, self._cli_jar_path)
        result = await self._jail.run(spec)
        outcome, transform = _map_jail_result(result, plan, repo)
        if transform is not None:
            self._transform_registry.register(transform)
        return outcome
