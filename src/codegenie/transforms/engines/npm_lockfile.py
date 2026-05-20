"""Phase-3 S5-02 — :class:`NpmLockfileRecipeEngine` + :class:`NpmLockfileTransform`.

The production day-1 :class:`~codegenie.transforms.recipe_engine.RecipeEngine`
(ADR-0009 Option C). Every Phase-3 npm vulnerability-remediation workflow
routes a typed :class:`~codegenie.transforms.outcomes.ApplicationPlan` through
:meth:`NpmLockfileRecipeEngine.apply`, which performs the deterministic
six-step lockfile-edit pipeline (``phase-arch-design.md §C12``):

1. Parse ``package.json`` via :mod:`orjson` with a 1 MiB size cap + a depth-16
   structural cap; reject NUL-byte / bidi-control adversarial ``name`` values
   via the :func:`~codegenie.types.parsers.parse_package_name` smart
   constructor.
2. Edit the affected dependency version **in-memory while preserving key
   order** (``orjson.OPT_INDENT_2``, never ``OPT_SORT_KEYS``).
3. Write ``package.json`` back through :meth:`SandboxedPath.open` — every
   write is ``O_NOFOLLOW`` (ADR-0011); a symlink swap between read and write
   raises ``OSError(ELOOP)``, caught and surfaced as ``recipe.filesystem_race``.
4. Run ``npm install --package-lock-only --ignore-scripts --no-audit
   --prefer-offline`` inside the :class:`SubprocessJail` — all four flags are
   required (ADR-0007 postinstall canary + determinism).
5. Parse the regenerated ``package-lock.json`` with 32 MiB / depth-24 caps;
   fail-fast on ``lockfileVersion: 1`` (npm v1 lockfiles are unsupported).
6. Build :class:`NpmLockfileTransform` carrying the unified diff of both
   files, ``register`` it into the constructor-injected
   :class:`~codegenie.transforms.transform_registry.TransformRegistry`, and
   return :class:`~codegenie.transforms.outcomes.Applied`.

Per ADR-0014 ``apply`` returns a bare ``RecipeOutcome`` — the produced
``Transform`` is surfaced via the injected ``TransformRegistry``, never as a
tuple. The engine is pure-Python at every step except the jailed
``npm install``: the parse / edit / re-serialise round-trip is byte-identical
regardless of whether ``npm`` is installed (the determinism contract, G4).

ADRs honored: ADR-0009 (this engine is one of the two day-1 implementations),
ADR-0007 (jailed ``npm install``; ``--ignore-scripts`` CLI half), ADR-0006
(``SubprocessJail`` Port), ADR-0010 (sum-type + newtype discipline),
ADR-0011 (``SandboxedPath`` ``O_NOFOLLOW``), ADR-0014 (``TransformRegistry``
surfacing), Phase-1 ADR-0007 (dotted-snake ``ErrorId`` taxonomy).
"""

from __future__ import annotations

import copy
import difflib
import errno
import typing
from typing import IO, Final, Literal, TypeAlias, assert_never, cast

import blake3
import orjson
from pydantic import BaseModel, ConfigDict

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
    DiskQuotaExceeded,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NpmEnv,
    OomKilled,
    RegistryAllowlist,
    SubprocessJail,
    TimedOut,
)
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import (
    ErrorId,
    EventId,
    RecipeId,
    RegistryUrl,
    TransformId,
)
from codegenie.types.parsers import parse_package_name

__all__ = ["NpmLockfileRecipeEngine", "NpmLockfileTransform"]


# ---------------------------------------------------------------------------
# Module-top ``Final`` constants — the size/depth caps, the jail budgets, and
# the four-flag ``npm install`` command line. Open/Closed boundary: a future
# ecosystem (Phase 7 distroless, yarn-berry) adds a *new constant in a sibling
# engine module* — never edits these. The mutation tests (AC-4b / AC-4d) pin
# each one as load-bearing.
# ---------------------------------------------------------------------------

_PACKAGE_JSON_MAX_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MiB
_PACKAGE_JSON_MAX_DEPTH: Final[int] = 16
_LOCKFILE_MAX_BYTES: Final[int] = 32 * 1024 * 1024  # 32 MiB
_LOCKFILE_MAX_DEPTH: Final[int] = 24
_SUPPORTED_LOCKFILE_VERSION: Final[int] = 3  # npm v7+ lockfileVersion

_NPM_INSTALL_TIME_BUDGET_S: Final[float] = 60.0  # 60 s — arch §Defaults
_NPM_INSTALL_MEMORY_MIB: Final[int] = 1024
_NPM_INSTALL_PIDS_MAX: Final[int] = 1024

# The four flags are required, not optional (ADR-0007 + determinism). Open/
# Closed seam: Phase 7 / yarn-berry add a sibling constant in their own engine
# module — never edit this tuple. The AC-4b mutation test drops each flag in
# turn and proves the resulting lockfile differs.
_NPM_INSTALL_CMD: Final[tuple[str, ...]] = (
    "npm",
    "install",
    "--package-lock-only",  # index 2 — fast, no node_modules populated
    "--ignore-scripts",  # index 3 — ADR-0007 postinstall canary (CLI half)
    "--no-audit",  # index 4 — deterministic, offline-respecting
    "--prefer-offline",  # index 5 — warm-cache determinism
)

# Phase 3 single-host allowlist. Phase 7's distroless plugin may widen
# additively via a plugin-local override constant — never edit this one.
_REGISTRY_ALLOWLIST_HOSTS: Final[frozenset[RegistryUrl]] = frozenset(
    {RegistryUrl("https://registry.npmjs.org")}
)

# Dependency-section search order — ``_edit_dep_version`` edits the FIRST match
# in this precedence; iterated, never branched on.
_DEP_SECTIONS_PRECEDENCE: Final[tuple[str, ...]] = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "overrides",
)

# Two-file diff boundary markers — ``Final`` so the determinism tests can
# assert their presence by symbol, not by a copy-pasted literal.
_PJSON_MARKER: Final[bytes] = b"--- file: package.json ---\n"
_LOCKFILE_MARKER: Final[bytes] = b"--- file: package-lock.json ---\n"

# Phase-3 provenance versions. The orchestrator (S6-04) will inject real
# plugin/recipe versions additively once the plugin layer (S7) lands; until
# then these semver-shape constants satisfy ``TransformProvenance``.
_PLUGIN_VERSION: Final[str] = "3.0.0"
_RECIPE_VERSION: Final[str] = "3.0.0"


# ---------------------------------------------------------------------------
# Error-id taxonomy — a closed ``Literal`` sum (Design-Patterns F2). Adding a
# failure mode is a Literal expansion + a new AC + a new test; deleting one
# re-baselines the Phase-3 contract snapshot (S6-06). ``recipe.jail_setup_failed``
# is the 14th id: the as-built ``JailedSubprocessResult`` carries a sixth
# ``JailSetupFailed`` variant, and the ``assert_never`` exhaustive ``match``
# below cannot compile under mypy-strict without an arm for it.
# ---------------------------------------------------------------------------

_NpmLockfileErrorId: TypeAlias = Literal[
    "recipe.package_json_too_large",
    "recipe.package_json_depth_exceeded",
    "recipe.filesystem_race",
    "recipe.npm_install_exit_nonzero",
    "recipe.install_timeout",
    "recipe.install_oom",
    "recipe.network_policy_violation",
    "recipe.disk_quota_exceeded",
    "recipe.lockfile_too_large",
    "recipe.lockfile_depth_exceeded",
    "recipe.lockfile_v1_unsupported",
    "recipe.package_not_in_dependencies",
    "recipe.adversarial_repo_content",
    "recipe.jail_setup_failed",
]

_ERROR_IDS: Final[frozenset[ErrorId]] = frozenset(
    ErrorId(eid) for eid in typing.get_args(_NpmLockfileErrorId)
)

_DetailValue: TypeAlias = str | int | bool | float

# A decoded JSON object. ``object`` (not ``Any``) for the heterogeneous values
# — the Phase-3 surface forbids ``Any`` annotations; consumers narrow with
# ``isinstance`` before use.
_JsonObject: TypeAlias = dict[str, object]


# ---------------------------------------------------------------------------
# Internal value-or-error sum. A single private frozen Pydantic model — not a
# generic ``Result[T, E]`` (Design-Patterns F1: no Result kernel exists and
# inventing one violates Rule 2). Every pure helper returns ``T | _InternalError``;
# ``apply`` narrows by ``isinstance`` and lifts to the public ``RecipeFailed``
# via :func:`_to_failed`.
# ---------------------------------------------------------------------------


class _InternalError(BaseModel):
    """Private failure payload threaded out of the engine's pure helpers."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    error_id: ErrorId
    message: str
    details: dict[str, _DetailValue]


def _err(
    error_id: _NpmLockfileErrorId, message: str, details: dict[str, _DetailValue]
) -> _InternalError:
    """Build an :class:`_InternalError` — ``error_id`` is type-narrowed to the
    closed taxonomy so a typo cannot escape mypy-strict."""
    return _InternalError(error_id=ErrorId(error_id), message=message, details=details)


def _to_failed(err: _InternalError) -> RecipeFailed:
    """Lift the internal error sum to the public ``RecipeFailed`` outcome."""
    return RecipeFailed(
        error=RecipeError(error_id=err.error_id, message=err.message, details=err.details)
    )


# ---------------------------------------------------------------------------
# Pure helpers (functional core — AC-Pure-1). The only I/O is reading through
# a passed-in ``SandboxedPath``; no ``await``, no ``os`` / ``subprocess`` /
# ``shutil``, no module-level mutable state.
# ---------------------------------------------------------------------------


def _max_depth(obj: object) -> int:
    """Return the maximum nesting depth of a JSON-decoded value.

    A scalar is depth 0; ``{"a": 1}`` is depth 1; ``{"a": {"a": 1}}`` is
    depth 2. Recursive over ``dict`` / ``list`` — safe for the depth-16 /
    depth-24 caps this module enforces well below CPython's stack limit."""
    if isinstance(obj, dict):
        return 1 + max((_max_depth(v) for v in obj.values()), default=0)
    if isinstance(obj, list):
        return 1 + max((_max_depth(v) for v in obj), default=0)
    return 0


def _serialize_json(doc: _JsonObject) -> bytes:
    """Serialise ``doc`` the way npm itself writes manifests — two-space
    indent, insertion order preserved (never sorted), trailing newline."""
    return orjson.dumps(doc, option=orjson.OPT_INDENT_2) + b"\n"


def _read_package_json(path: SandboxedPath) -> tuple[_JsonObject, bytes] | _InternalError:
    """Read + size-cap + depth-cap + adversarial-name-check ``package.json``.

    Returns ``(parsed_doc, raw_bytes)`` on success; the raw bytes are the
    diff's ``before`` side. The NUL-byte / bidi-control gate is the
    :func:`parse_package_name` smart constructor — the engine does not invent
    a parallel validator."""
    with cast("IO[bytes]", path.open("rb")) as handle:
        raw = handle.read()
    if len(raw) > _PACKAGE_JSON_MAX_BYTES:
        return _err(
            "recipe.package_json_too_large",
            "package.json exceeds 1 MiB cap",
            {"limit_bytes": _PACKAGE_JSON_MAX_BYTES, "observed_bytes": len(raw)},
        )
    parsed: object = orjson.loads(raw)
    if not isinstance(parsed, dict):
        return _err(
            "recipe.adversarial_repo_content",
            "package.json root is not a JSON object",
            {"root_type": type(parsed).__name__},
        )
    doc: _JsonObject = parsed
    depth = _max_depth(doc)
    if depth > _PACKAGE_JSON_MAX_DEPTH:
        return _err(
            "recipe.package_json_depth_exceeded",
            "package.json nesting depth exceeds cap",
            {"limit": _PACKAGE_JSON_MAX_DEPTH, "observed": depth},
        )
    name = doc.get("name")
    if isinstance(name, str) and not isinstance(parse_package_name(name), Ok):
        return _err(
            "recipe.adversarial_repo_content",
            "package.json 'name' failed smart-constructor validation",
            {"field": "name"},
        )
    return doc, raw


def _edit_dep_version(
    doc: _JsonObject, package: str, new_version: str
) -> _JsonObject | _InternalError:
    """Return a deep copy of ``doc`` with ``package``'s version set to
    ``new_version`` in the first matching dependency section.

    Walks :data:`_DEP_SECTIONS_PRECEDENCE` in declaration order and edits the
    first section that contains ``package``; key order is intrinsic to ``dict``
    and preserved by ``orjson.dumps``. ``recipe.package_not_in_dependencies``
    if no section contains ``package``."""
    edited: _JsonObject = copy.deepcopy(doc)
    for section in _DEP_SECTIONS_PRECEDENCE:
        deps = edited.get(section)
        if isinstance(deps, dict) and package in deps:
            deps[package] = new_version
            return edited
    return _err(
        "recipe.package_not_in_dependencies",
        f"package {package!r} not found in any dependency section",
        {"package": package, "sections_searched": ",".join(_DEP_SECTIONS_PRECEDENCE)},
    )


def _parse_lockfile(path: SandboxedPath) -> tuple[_JsonObject, bytes] | _InternalError:
    """Read + size-cap + depth-cap + version-check ``package-lock.json``.

    Order is load-bearing (AC-5c): size cap, then depth cap, then the
    ``lockfileVersion`` dispatch — a v1 *and* oversize lockfile surfaces
    ``recipe.lockfile_too_large`` because the size check runs first. Returns
    ``(parsed_doc, raw_bytes)`` — the raw bytes are the diff's ``after`` side."""
    with cast("IO[bytes]", path.open("rb")) as handle:
        raw = handle.read()
    if len(raw) > _LOCKFILE_MAX_BYTES:
        return _err(
            "recipe.lockfile_too_large",
            "package-lock.json exceeds 32 MiB cap",
            {"limit_bytes": _LOCKFILE_MAX_BYTES, "observed_bytes": len(raw)},
        )
    parsed: object = orjson.loads(raw)
    if not isinstance(parsed, dict):
        return _err(
            "recipe.adversarial_repo_content",
            "package-lock.json root is not a JSON object",
            {"root_type": type(parsed).__name__},
        )
    doc: _JsonObject = parsed
    depth = _max_depth(doc)
    if depth > _LOCKFILE_MAX_DEPTH:
        return _err(
            "recipe.lockfile_depth_exceeded",
            "package-lock.json nesting depth exceeds cap",
            {"limit": _LOCKFILE_MAX_DEPTH, "observed": depth},
        )
    version = doc.get("lockfileVersion")
    if version != _SUPPORTED_LOCKFILE_VERSION:
        return _err(
            "recipe.lockfile_v1_unsupported",
            "only npm lockfileVersion 3 is supported",
            {
                "lockfile_version": version if isinstance(version, int) else -1,
                "supported": _SUPPORTED_LOCKFILE_VERSION,
            },
        )
    return doc, raw


def _build_unified_diff(
    before_pjson: bytes, after_pjson: bytes, before_lock: bytes, after_lock: bytes
) -> bytes:
    """Build the two-file unified diff. Deterministic by construction — pure
    byte input, no timestamps, no inode / random data enters the payload."""
    pjson_diff = difflib.unified_diff(
        before_pjson.decode("utf-8").splitlines(keepends=True),
        after_pjson.decode("utf-8").splitlines(keepends=True),
        fromfile="package.json",
        tofile="package.json",
        lineterm="",
    )
    lock_diff = difflib.unified_diff(
        before_lock.decode("utf-8").splitlines(keepends=True),
        after_lock.decode("utf-8").splitlines(keepends=True),
        fromfile="package-lock.json",
        tofile="package-lock.json",
        lineterm="",
    )
    return (
        _PJSON_MARKER
        + "".join(pjson_diff).encode("utf-8")
        + _LOCKFILE_MARKER
        + "".join(lock_diff).encode("utf-8")
    )


def _compute_transform_id(diff_bytes: bytes) -> TransformId:
    """Return the BLAKE3-hex digest of ``diff_bytes`` — the transform's
    content-addressed identity (ADR-0010)."""
    return TransformId(blake3.blake3(diff_bytes).hexdigest())


# ---------------------------------------------------------------------------
# Side-effecting helpers (imperative shell) — writes, the jailed subprocess,
# and the jail-result classifier.
# ---------------------------------------------------------------------------


def _write_package_json(path: SandboxedPath, payload: bytes) -> _InternalError | None:
    """Write ``payload`` through :meth:`SandboxedPath.open` (``O_NOFOLLOW``).

    The single ``OSError`` catch is precisely scoped to ``errno.ELOOP`` — a
    symlink swapped under ``package.json`` between read and write (TOCTOU,
    §Edge case E12); every other ``OSError`` re-raises (Rule 12, fail loud)."""
    try:
        with cast("IO[bytes]", path.open("wb")) as handle:
            handle.write(payload)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return _err(
                "recipe.filesystem_race",
                "symlink swap detected on package.json write-back",
                {"path": "package.json"},
            )
        raise
    return None


def _classify_jail_result(result: JailedSubprocessResult) -> _InternalError | None:
    """Map the :data:`JailedSubprocessResult` tagged union to ``None`` (clean
    install) or a typed :class:`_InternalError`.

    The ``match`` is exhaustive over all six variants with ``assert_never`` in
    the wildcard arm — adding a seventh variant breaks this mapping under
    mypy-strict until the engine handles it (AC-4g / AC-4g2)."""
    match result:
        case Completed(exit_code=0):
            return None
        case Completed(exit_code=exit_code, stderr_bytes=stderr_bytes, wall_time_s=wall_time_s):
            return _err(
                "recipe.npm_install_exit_nonzero",
                f"npm install exited {exit_code}",
                {
                    "exit_code": exit_code,
                    "stderr_bytes": stderr_bytes,
                    "wall_time_s": wall_time_s,
                },
            )
        case TimedOut(budget_s=budget_s, elapsed_s=elapsed_s):
            return _err(
                "recipe.install_timeout",
                "npm install exceeded its time budget",
                {"budget_s": budget_s, "elapsed_s": elapsed_s},
            )
        case OomKilled(peak_rss_mib=peak_rss_mib):
            return _err(
                "recipe.install_oom",
                "npm install was killed for exceeding the memory budget",
                {"peak_rss_mib": peak_rss_mib},
            )
        case NetworkDenied(host=host):
            return _err(
                "recipe.network_policy_violation",
                "npm install attempted egress to a non-allowlisted host",
                {"host": host},
            )
        case DiskQuotaExceeded(quota_bytes=quota_bytes, bytes_written=bytes_written):
            return _err(
                "recipe.disk_quota_exceeded",
                "npm install exceeded the jail disk quota",
                {"quota_bytes": quota_bytes, "bytes_written": bytes_written},
            )
        case JailSetupFailed(reason=reason, detail=detail):
            return _err(
                "recipe.jail_setup_failed",
                "the subprocess jail could not be set up",
                {"reason": reason, "detail": detail},
            )
        case _:  # pragma: no cover — exhaustiveness guard
            assert_never(result)


async def _run_npm_install(jail: SubprocessJail, repo: SandboxedPath) -> _InternalError | None:
    """Run the four-flag ``npm install`` inside ``jail`` and classify the
    result. Egress is the single-host ``RegistryAllowlist``; the env is
    :class:`NpmEnv` (the ``npm_config_ignore_scripts`` env half of ADR-0007)."""
    spec = JailedSubprocessSpec(
        cmd=_NPM_INSTALL_CMD,
        cwd=repo,
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=_REGISTRY_ALLOWLIST_HOSTS),
        time_budget_s=_NPM_INSTALL_TIME_BUDGET_S,
        memory_mib=_NPM_INSTALL_MEMORY_MIB,
        pids_max=_NPM_INSTALL_PIDS_MAX,
    )
    return _classify_jail_result(await jail.run(spec))


def _resolve(repo: SandboxedPath, relative: str) -> SandboxedPath | _InternalError:
    """Resolve ``relative`` under ``repo`` via the :meth:`SandboxedPath.create`
    smart constructor. A path that will not resolve safely under the repo jail
    is a filesystem-integrity failure — surfaced as ``recipe.filesystem_race``."""
    result = SandboxedPath.create(repo.absolute, relative)
    if isinstance(result, Ok):
        return result.value
    return _err(
        "recipe.filesystem_race",
        f"{relative} could not be resolved safely under the repo jail",
        {"path": relative, "reason": result.error.reason},
    )


def _read_before_lockfile(repo: SandboxedPath) -> bytes:
    """Read the pre-install ``package-lock.json`` bytes for the diff's
    ``before`` side. A repo with no lockfile yet is valid — npm install
    creates one — so a missing file yields empty ``before`` bytes."""
    resolved = _resolve(repo, "package-lock.json")
    if isinstance(resolved, _InternalError):
        return b""
    with cast("IO[bytes]", resolved.open("rb")) as handle:
        return handle.read()


def _derive_capability_use_id(capability: NpmInstallCapability) -> EventId:
    """Derive the provenance audit anchor from the capability.

    S4-05's :class:`NpmInstallCapability` carries no event id and the S6-01
    two-stream event log is not yet built, so the engine derives a stable,
    capability-scoped :data:`EventId` by digesting the capability's canonical
    serialisation — the same capability always yields the same anchor. S6-04
    may wire a real minted event id additively once the orchestrator lands."""
    digest = blake3.blake3(capability.model_dump_json().encode("utf-8")).hexdigest()
    return EventId(digest)


# ---------------------------------------------------------------------------
# ``NpmLockfileTransform`` — concrete ``Transform`` ABC subclass (S1-04).
# ---------------------------------------------------------------------------


class NpmLockfileTransform(Transform):
    """The :class:`Transform` produced by :class:`NpmLockfileRecipeEngine`.

    Carries the unified diff of ``package.json`` + ``package-lock.json``, the
    two :class:`SandboxedPath` handles that changed, and the audit-anchor
    :class:`TransformProvenance`. Declares the four ``Transform`` contract
    attributes as per-instance state; overrides nothing else."""

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


# ---------------------------------------------------------------------------
# ``NpmLockfileRecipeEngine`` — the Phase-3 day-1 ``RecipeEngine`` worker.
# ---------------------------------------------------------------------------


class NpmLockfileRecipeEngine:
    """Deterministic npm lockfile-edit :class:`~codegenie.transforms
    .recipe_engine.RecipeEngine` (ADR-0009).

    Both collaborators are constructor-injected (ADR-0014): the
    :class:`SubprocessJail` that runs ``npm install`` and the
    :class:`TransformRegistry` the produced :class:`NpmLockfileTransform` is
    surfaced through. No module-level mutable state, no global registry write
    at import time."""

    def __init__(self, jail: SubprocessJail, transform_registry: TransformRegistry) -> None:
        self._jail = jail
        self._transform_registry = transform_registry

    async def apply(
        self,
        repo: SandboxedPath,
        plan: ApplicationPlan,
        capability: NpmInstallCapability,
    ) -> RecipeOutcome:
        """Run the six-step deterministic lockfile-edit pipeline.

        On success the produced :class:`NpmLockfileTransform` is ``register``-ed
        into the injected :class:`TransformRegistry` and an :class:`Applied`
        outcome carrying its ``transform_id`` is returned; every failure mode
        is a typed :class:`RecipeFailed` from the closed error-id taxonomy."""
        package = plan.package
        to_version = plan.to_version
        transform_kind = plan.transform_kind
        if package is None or to_version is None or transform_kind is None:
            return RecipeFailed(
                error=RecipeError(
                    error_id=ErrorId("recipe.package_not_in_dependencies"),
                    message="ApplicationPlan missing package field",
                    details={"package": "" if package is None else str(package)},
                )
            )

        pkg_path = _resolve(repo, "package.json")
        if isinstance(pkg_path, _InternalError):
            return _to_failed(pkg_path)

        # Step 1 — parse package.json with caps + adversarial-content gate.
        pjson_read = _read_package_json(pkg_path)
        if isinstance(pjson_read, _InternalError):
            return _to_failed(pjson_read)
        before_doc, before_pjson_bytes = pjson_read

        # Step 2 — edit the affected dep version, key order preserved.
        edited = _edit_dep_version(before_doc, str(package), to_version)
        if isinstance(edited, _InternalError):
            return _to_failed(edited)
        after_pjson_bytes = _serialize_json(edited)

        # Step 3 — write package.json back through O_NOFOLLOW.
        write_err = _write_package_json(pkg_path, after_pjson_bytes)
        if write_err is not None:
            return _to_failed(write_err)

        before_lock_bytes = _read_before_lockfile(repo)

        # Step 4 — npm install inside the SubprocessJail.
        install_err = await _run_npm_install(self._jail, repo)
        if install_err is not None:
            return _to_failed(install_err)

        # Step 5 — parse the regenerated lockfile with caps + version dispatch.
        lock_path = _resolve(repo, "package-lock.json")
        if isinstance(lock_path, _InternalError):
            return _to_failed(lock_path)
        lock_read = _parse_lockfile(lock_path)
        if isinstance(lock_read, _InternalError):
            return _to_failed(lock_read)
        _new_lock_doc, after_lock_bytes = lock_read

        # Step 6 — build the Transform, register it, return Applied.
        diff_bytes = _build_unified_diff(
            before_pjson_bytes, after_pjson_bytes, before_lock_bytes, after_lock_bytes
        )
        transform_id = _compute_transform_id(diff_bytes)
        recipe_id = RecipeId(str(transform_kind))
        provenance = TransformProvenance(
            plugin_id=capability.minted_by,
            plugin_version=_PLUGIN_VERSION,
            recipe_id=recipe_id,
            recipe_version=_RECIPE_VERSION,
            transform_kind=transform_kind,
            capability_use_id=_derive_capability_use_id(capability),
        )
        transform = NpmLockfileTransform(
            transform_id=transform_id,
            diff_bytes=diff_bytes,
            files_changed=(pkg_path, lock_path),
            provenance=provenance,
        )
        self._transform_registry.register(transform)
        return Applied(
            transform_id=transform_id,
            plugin_id=capability.minted_by,
            recipe_id=recipe_id,
        )
