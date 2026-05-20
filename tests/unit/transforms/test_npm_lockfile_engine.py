"""S5-02 — :class:`NpmLockfileRecipeEngine` unit suite (fake jail).

Exercises the corrected ADR-0014 contract: ``apply`` returns a bare
:data:`RecipeOutcome`; the produced :class:`NpmLockfileTransform` is surfaced
via the constructor-injected :class:`TransformRegistry` and retrieved with
``registry.get(outcome.transform_id)``.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import blake3
import orjson
import pytest

# Direct SandboxedPath / NpmInstallCapability construction is convention-
# reserved for the owning modules + ``tests/`` — this is a test.
from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.engines import npm_lockfile as eng_mod
from codegenie.transforms.engines.npm_lockfile import (
    NpmLockfileRecipeEngine,
    NpmLockfileTransform,
)
from codegenie.transforms.outcomes import ApplicationPlan, Applied, RecipeFailed
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.transforms.sandbox_jail import (
    Completed,
    DiskQuotaExceeded,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    OomKilled,
    TimedOut,
)
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import (
    ErrorId,
    PackageId,
    PluginId,
    RecipeId,
    RegistryUrl,
    TransformId,
    TransformKind,
)

# --- Fake jails ------------------------------------------------------------


class FakeJail:
    """Single-result fake :class:`SubprocessJail`; records every call."""

    def __init__(self, result: JailedSubprocessResult) -> None:
        self.result = result
        self.calls: list[JailedSubprocessSpec] = []

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        return self.result


class WritingJail(FakeJail):
    """Fake jail that simulates ``npm install`` by writing a regenerated
    ``package-lock.json`` (serialised from ``after_lockfile``) into ``cwd``."""

    def __init__(self, after_lockfile: dict[str, Any]) -> None:
        super().__init__(
            Completed(
                kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.01
            )
        )
        self._after = after_lockfile

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        cwd = Path(str(spec.cwd))
        (cwd / "package-lock.json").write_bytes(
            orjson.dumps(self._after, option=orjson.OPT_INDENT_2) + b"\n"
        )
        return self.result


class RawWritingJail(FakeJail):
    """Fake jail that writes arbitrary raw bytes as the regenerated lockfile —
    used to exercise the lockfile size cap (AC-5a)."""

    def __init__(self, raw: bytes) -> None:
        super().__init__(
            Completed(
                kind="completed", exit_code=0, stdout_bytes=0, stderr_bytes=0, wall_time_s=0.01
            )
        )
        self._raw = raw

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        (Path(str(spec.cwd)) / "package-lock.json").write_bytes(self._raw)
        return self.result


_CLEAN_LOCKFILE: dict[str, Any] = {
    "name": "fixture",
    "lockfileVersion": 3,
    "packages": {"node_modules/express": {"version": "4.19.2"}},
}


# --- Fixtures --------------------------------------------------------------


def _write_repo(root: Path, package_json: dict[str, Any]) -> None:
    (root / "package.json").write_bytes(
        orjson.dumps(package_json, option=orjson.OPT_INDENT_2) + b"\n"
    )
    (root / "package-lock.json").write_bytes(
        orjson.dumps(
            {"name": "fixture", "lockfileVersion": 3, "packages": {}},
            option=orjson.OPT_INDENT_2,
        )
        + b"\n"
    )


@pytest.fixture
def express_repo(tmp_path: Path) -> Path:
    _write_repo(
        tmp_path,
        {
            "name": "fixture",
            "version": "1.0.0",
            "dependencies": {"express": "^4.17.1", "lodash": "^4.17.21"},
        },
    )
    return tmp_path


@pytest.fixture
def plan() -> ApplicationPlan:
    return ApplicationPlan.for_npm_semver_bump(
        package=PackageId("express"),
        from_version="^4.17.1",
        to_version="^4.19.2",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )


@pytest.fixture
def capability() -> NpmInstallCapability:
    """A real S4-05 ``NpmInstallCapability``. It carries no event id — the
    engine derives the provenance ``capability_use_id`` from it (see
    ``_derive_capability_use_id``)."""
    return NpmInstallCapability(
        registry=RegistryUrl("https://registry.npmjs.org"),
        minted_by=PluginId("vuln-node-npm"),
    )


@pytest.fixture
def registry() -> TransformRegistry:
    return TransformRegistry()


def _sp(path: Path) -> SandboxedPath:
    return SandboxedPath(absolute=path)


# --- Surface + module shape ------------------------------------------------


def test_module_all_is_exactly_the_two_public_names() -> None:
    """AC-Surface-1 — ``__all__`` re-exports only the engine + the transform."""
    assert set(eng_mod.__all__) == {"NpmLockfileRecipeEngine", "NpmLockfileTransform"}


async def test_runtime_checkable_protocol_conformance(registry: TransformRegistry) -> None:
    """AC-Surface-2(a) — runtime ``isinstance`` against the ``RecipeEngine``
    Protocol (``@runtime_checkable`` per S5-01)."""
    engine = NpmLockfileRecipeEngine(jail=FakeJail(_completed(0)), transform_registry=registry)
    assert isinstance(engine, RecipeEngine)


def test_transform_is_transform_abc_subclass_with_tuple_files_changed() -> None:
    """AC-Surface-3 — ``NpmLockfileTransform`` is a ``Transform`` subclass with
    a ``tuple`` (not ``list``) ``files_changed``; the ABC stays un-instantiable."""
    assert issubclass(NpmLockfileTransform, Transform)
    with pytest.raises(TypeError):
        Transform()  # type: ignore[abstract]
    provenance = _provenance()
    transform = NpmLockfileTransform(
        transform_id=TransformId("a" * 64),
        diff_bytes=b"",
        files_changed=(),
        provenance=provenance,
    )
    assert isinstance(transform.files_changed, tuple)
    assert isinstance(transform, Transform)


def test_engine_holds_no_module_level_mutable_state() -> None:
    """AC-Surface-4 — both collaborators are constructor-injected; no global
    registry write happens at import time."""
    fresh = TransformRegistry()
    engine = NpmLockfileRecipeEngine(jail=FakeJail(_completed(0)), transform_registry=fresh)
    assert engine._transform_registry is fresh
    assert len(fresh) == 0


# --- Error-id taxonomy -----------------------------------------------------


def test_error_id_taxonomy_is_a_closed_14_entry_set() -> None:
    """AC-Tax-1 — 14 ids (13 in the original draft + ``recipe.jail_setup_failed``
    for the as-built sixth ``JailedSubprocessResult`` variant). Every member
    round-trips through the ``ErrorId`` newtype and the closed ``Literal``."""
    import typing

    literal_args = set(typing.get_args(eng_mod._NpmLockfileErrorId))
    assert len(eng_mod._ERROR_IDS) == 14
    assert eng_mod._ERROR_IDS == frozenset(ErrorId(eid) for eid in literal_args)
    assert "recipe.jail_setup_failed" in literal_args


# --- Step 1: package.json parse + caps -------------------------------------


async def test_package_json_too_large_short_circuits_before_npm(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-1a — a 1 MiB + 1 byte package.json fails before ``npm install`` is
    ever invoked."""
    oversize = eng_mod._PACKAGE_JSON_MAX_BYTES + 1
    (tmp_path / "package.json").write_bytes(b"x" * oversize)
    (tmp_path / "package-lock.json").write_bytes(b"{}\n")
    jail = FakeJail(_completed(0))
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.package_json_too_large")
    assert outcome.error.details == {"limit_bytes": 1048576, "observed_bytes": oversize}
    assert len(jail.calls) == 0


async def test_package_json_depth_exceeded_short_circuits_before_npm(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-1b — a depth-17 package.json exceeds the depth-16 cap; jail untouched."""
    nested: Any = 0
    for _ in range(17):
        nested = {"a": nested}
    (tmp_path / "package.json").write_bytes(orjson.dumps(nested))
    (tmp_path / "package-lock.json").write_bytes(b"{}\n")
    jail = FakeJail(_completed(0))
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.package_json_depth_exceeded")
    assert outcome.error.details == {"limit": 16, "observed": 17}
    assert len(jail.calls) == 0


@pytest.mark.parametrize("bad_name", ["a\x00b", "a‮b", "..", "/"])
async def test_adversarial_repo_content_in_name_is_rejected(
    tmp_path: Path,
    plan: ApplicationPlan,
    capability: NpmInstallCapability,
    bad_name: str,
) -> None:
    """AC-1c — a NUL byte / bidi control / path-traversal ``name`` is rejected
    by the ``parse_package_name`` smart constructor; jail untouched."""
    _write_repo(
        tmp_path,
        {"name": bad_name, "version": "1.0.0", "dependencies": {"express": "^4.17.1"}},
    )
    jail = FakeJail(_completed(0))
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.adversarial_repo_content")
    assert len(jail.calls) == 0


# --- Step 2: in-memory edit, key order preserved ---------------------------


async def test_no_op_edit_is_byte_identical_round_trip(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-2a — a plan whose ``to_version`` equals the current version leaves
    package.json byte-identical (key order + indentation preserved)."""
    noop_plan = plan.model_copy(update={"to_version": "^4.17.1"})
    before = (express_repo / "package.json").read_bytes()
    await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), noop_plan, capability)
    assert (express_repo / "package.json").read_bytes() == before


@pytest.mark.parametrize("dep,new_version", [("express", "^4.19.2"), ("lodash", "^4.17.22")])
async def test_edited_round_trip_changes_only_the_targeted_version_line(
    express_repo: Path, capability: NpmInstallCapability, dep: str, new_version: str
) -> None:
    """AC-2b — editing one dependency changes exactly that dependency's
    version line; every other byte is preserved."""
    edit_plan = ApplicationPlan.for_npm_semver_bump(
        package=PackageId(dep),
        from_version="^0.0.0",
        to_version=new_version,
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )
    before = (express_repo / "package.json").read_bytes()
    await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), edit_plan, capability)
    after = (express_repo / "package.json").read_bytes()
    # n=0 → no context lines: exactly one removed + one added line.
    diff = list(
        difflib.unified_diff(
            before.decode().splitlines(),
            after.decode().splitlines(),
            lineterm="",
            n=0,
        )
    )
    removed = [ln for ln in diff if ln.startswith("-") and not ln.startswith("---")]
    added = [ln for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    assert len(removed) == 1
    assert len(added) == 1
    assert new_version in added[0]


async def test_package_not_in_dependencies(
    express_repo: Path, capability: NpmInstallCapability
) -> None:
    """AC-2c — a plan targeting a dep absent from all four sections fails
    before ``npm install``."""
    missing_plan = ApplicationPlan.for_npm_semver_bump(
        package=PackageId("not-installed"),
        from_version="^1.0.0",
        to_version="^2.0.0",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )
    jail = WritingJail(_CLEAN_LOCKFILE)
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), missing_plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.package_not_in_dependencies")
    assert outcome.error.details["package"] == "not-installed"
    assert len(jail.calls) == 0


async def test_section_precedence_edits_first_match_only(
    tmp_path: Path, capability: NpmInstallCapability
) -> None:
    """AC-2d — when a dep is in two sections the FIRST in precedence
    (``dependencies`` > ``devDependencies``) is edited; the other is left."""
    _write_repo(
        tmp_path,
        {
            "name": "fixture",
            "version": "1.0.0",
            "dependencies": {"shared": "^1.0.0"},
            "devDependencies": {"shared": "^1.0.0"},
        },
    )
    bump = ApplicationPlan.for_npm_semver_bump(
        package=PackageId("shared"),
        from_version="^1.0.0",
        to_version="^9.9.9",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )
    await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), bump, capability)
    after = orjson.loads((tmp_path / "package.json").read_bytes())
    assert after["dependencies"]["shared"] == "^9.9.9"
    assert after["devDependencies"]["shared"] == "^1.0.0"


# --- Step 4: npm install under SubprocessJail ------------------------------


async def test_npm_install_command_is_exactly_the_four_flag_tuple(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-4a — the recorded ``cmd`` tuple is bit-identical, order included."""
    jail = WritingJail(_CLEAN_LOCKFILE)
    await NpmLockfileRecipeEngine(jail=jail, transform_registry=TransformRegistry()).apply(
        _sp(express_repo), plan, capability
    )
    assert jail.calls[0].cmd == (
        "npm",
        "install",
        "--package-lock-only",
        "--ignore-scripts",
        "--no-audit",
        "--prefer-offline",
    )


async def test_network_policy_is_registry_allowlist_only(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-4c — egress is the exact single-host ``RegistryAllowlist``."""
    jail = WritingJail(_CLEAN_LOCKFILE)
    await NpmLockfileRecipeEngine(jail=jail, transform_registry=TransformRegistry()).apply(
        _sp(express_repo), plan, capability
    )
    network = jail.calls[0].network
    assert network.kind == "registry_allowlist"
    assert network.hosts == frozenset({RegistryUrl("https://registry.npmjs.org")})


def test_engine_never_constructs_a_deny_all_or_allow_all_policy() -> None:
    """AC-4c2 — the engine source never references a ``DenyAll`` / ``AllowAll``
    network policy under any code path."""
    import inspect

    source = inspect.getsource(eng_mod)
    assert "DenyAll" not in source
    assert "AllowAll" not in source


async def test_budget_envelope_is_pinned(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-4d — time / memory / pid budgets are pinned to the module constants."""
    jail = WritingJail(_CLEAN_LOCKFILE)
    await NpmLockfileRecipeEngine(jail=jail, transform_registry=TransformRegistry()).apply(
        _sp(express_repo), plan, capability
    )
    spec = jail.calls[0]
    assert spec.time_budget_s == 60.0
    assert spec.memory_mib == 1024
    assert spec.pids_max == 1024


async def test_typed_env_discriminator_double_enforces_ignore_scripts(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-4e — ``env.kind == 'npm'`` and ``NpmEnv`` emits the
    ``npm_config_ignore_scripts`` env half of the ADR-0007 split defence."""
    jail = WritingJail(_CLEAN_LOCKFILE)
    await NpmLockfileRecipeEngine(jail=jail, transform_registry=TransformRegistry()).apply(
        _sp(express_repo), plan, capability
    )
    env = jail.calls[0].env
    assert env.kind == "npm"
    assert env.to_env_mapping()["npm_config_ignore_scripts"] == "true"


async def test_npm_install_nonzero_exit_maps_to_typed_failure(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-4f — a non-zero ``Completed`` exit becomes ``recipe.npm_install_exit_nonzero``
    with the byte counts carried in ``details``."""
    jail = FakeJail(
        Completed(kind="completed", exit_code=1, stdout_bytes=0, stderr_bytes=512, wall_time_s=0.34)
    )
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.npm_install_exit_nonzero")
    assert outcome.error.details == {
        "exit_code": 1,
        "stderr_bytes": 512,
        "wall_time_s": 0.34,
    }


@pytest.mark.parametrize(
    "variant,expected_error_id,expected_details",
    [
        (
            TimedOut(kind="timed_out", budget_s=60.0, elapsed_s=61.2),
            "recipe.install_timeout",
            {"budget_s": 60.0, "elapsed_s": 61.2},
        ),
        (
            OomKilled(kind="oom_killed", peak_rss_mib=1100),
            "recipe.install_oom",
            {"peak_rss_mib": 1100},
        ),
        (
            NetworkDenied(kind="network_denied", host="attacker.example.com"),
            "recipe.network_policy_violation",
            {"host": "attacker.example.com"},
        ),
        (
            DiskQuotaExceeded(
                kind="disk_quota_exceeded", quota_bytes=10_000_000, bytes_written=10_000_001
            ),
            "recipe.disk_quota_exceeded",
            {"quota_bytes": 10_000_000, "bytes_written": 10_000_001},
        ),
        (
            JailSetupFailed(
                kind="jail_setup_failed", reason="bwrap-not-on-path", detail="bwrap missing"
            ),
            "recipe.jail_setup_failed",
            {"reason": "bwrap-not-on-path", "detail": "bwrap missing"},
        ),
    ],
)
async def test_jail_failure_variants_map_to_typed_recipe_failed(
    express_repo: Path,
    plan: ApplicationPlan,
    capability: NpmInstallCapability,
    variant: JailedSubprocessResult,
    expected_error_id: str,
    expected_details: dict[str, Any],
) -> None:
    """AC-4g — every non-``Completed`` ``JailedSubprocessResult`` variant maps
    to a distinct typed ``RecipeFailed`` (``JailSetupFailed`` included — the
    sixth as-built variant)."""
    outcome = await NpmLockfileRecipeEngine(
        jail=FakeJail(variant), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId(expected_error_id)
    assert outcome.error.details == expected_details


# --- Step 5: parse the regenerated lockfile --------------------------------


async def test_lockfile_too_large(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-5a — a 32 MiB + 1 byte regenerated lockfile is rejected."""
    oversize = eng_mod._LOCKFILE_MAX_BYTES + 1
    outcome = await NpmLockfileRecipeEngine(
        jail=RawWritingJail(b"x" * oversize), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.lockfile_too_large")
    assert outcome.error.details == {"limit_bytes": 33554432, "observed_bytes": oversize}


async def test_lockfile_depth_exceeded(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-5b — a depth-25 regenerated lockfile exceeds the depth-24 cap."""
    nested: Any = 0
    for _ in range(25):
        nested = {"a": nested}
    outcome = await NpmLockfileRecipeEngine(
        jail=WritingJail(nested), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.lockfile_depth_exceeded")
    assert outcome.error.details == {"limit": 24, "observed": 25}


async def test_lockfile_v1_unsupported(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-5c — a ``lockfileVersion: 1`` lockfile is rejected with a distinct id."""
    outcome = await NpmLockfileRecipeEngine(
        jail=WritingJail({"name": "x", "lockfileVersion": 1}),
        transform_registry=TransformRegistry(),
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.lockfile_v1_unsupported")
    assert outcome.error.details["lockfile_version"] == 1


async def test_lockfile_size_cap_wins_over_version_check(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-5c (ordering) — an oversize *and* v1 lockfile surfaces the size error;
    the size check runs before the version dispatch."""
    raw = b"x" * (eng_mod._LOCKFILE_MAX_BYTES + 1)
    outcome = await NpmLockfileRecipeEngine(
        jail=RawWritingJail(raw), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.lockfile_too_large")


# --- ApplicationPlan additive widening -------------------------------------


def test_application_plan_widens_additively() -> None:
    """AC-Plan-1 — the four new npm fields are optional; every existing
    ``ApplicationPlan`` call site keeps constructing."""
    assert ApplicationPlan().package is None
    assert ApplicationPlan(summary="legacy call site").summary == "legacy call site"
    full = ApplicationPlan.for_npm_semver_bump(
        package=PackageId("express"),
        from_version="^4.17.1",
        to_version="^4.19.2",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
    )
    assert full.package == PackageId("express")
    assert full.from_version == "^4.17.1"
    assert full.to_version == "^4.19.2"
    assert full.transform_kind == TransformKind("npm-lockfile-semver-bump")
    assert full.summary is None


# --- Step 6: Applied outcome + NpmLockfileTransform ------------------------


async def test_happy_path_registers_transform_and_returns_applied(
    express_repo: Path,
    plan: ApplicationPlan,
    capability: NpmInstallCapability,
    registry: TransformRegistry,
) -> None:
    """AC-Apply-1 — the happy path returns a bare ``Applied`` and the produced
    transform is retrievable from the injected registry by ``transform_id``."""
    outcome = await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=registry
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, Applied)
    assert outcome.kind == "applied"
    transform = registry.get(outcome.transform_id)
    assert isinstance(transform, NpmLockfileTransform)
    assert transform.transform_id == outcome.transform_id
    assert len(transform.files_changed) == 2
    repo_root = express_repo.resolve()
    assert {p.absolute.name for p in transform.files_changed} == {
        "package.json",
        "package-lock.json",
    }
    assert all(p.absolute.is_relative_to(repo_root) for p in transform.files_changed)


async def test_transform_id_is_the_blake3_digest_of_diff_bytes(
    express_repo: Path,
    plan: ApplicationPlan,
    capability: NpmInstallCapability,
    registry: TransformRegistry,
) -> None:
    """AC-Apply-2 — ``transform_id`` is the BLAKE3-hex digest of ``diff_bytes``."""
    outcome = await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=registry
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, Applied)
    transform = registry.get(outcome.transform_id)
    assert transform.transform_id == TransformId(blake3.blake3(transform.diff_bytes).hexdigest())
    assert b"--- file: package.json ---" in transform.diff_bytes
    assert b"--- file: package-lock.json ---" in transform.diff_bytes


async def test_provenance_threads_capability_and_plan(
    express_repo: Path,
    plan: ApplicationPlan,
    capability: NpmInstallCapability,
    registry: TransformRegistry,
) -> None:
    """AC-Apply-3 — provenance carries the plugin / recipe / transform-kind
    identity and a capability-derived audit anchor."""
    outcome = await NpmLockfileRecipeEngine(
        jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=registry
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, Applied)
    provenance = registry.get(outcome.transform_id).provenance
    assert isinstance(provenance, TransformProvenance)
    assert provenance.plugin_id == capability.minted_by
    assert provenance.recipe_id == RecipeId("npm-lockfile-semver-bump")
    assert provenance.transform_kind == TransformKind("npm-lockfile-semver-bump")
    assert provenance.applied_at.tzinfo is not None
    # The audit anchor is derived deterministically from the capability.
    assert provenance.capability_use_id == eng_mod._derive_capability_use_id(capability)
    assert outcome.plugin_id == capability.minted_by


async def test_plan_missing_required_field_fails_loud(
    express_repo: Path, capability: NpmInstallCapability
) -> None:
    """AC-Plan-2 — an ``ApplicationPlan`` with no ``package`` fails before any
    filesystem work."""
    outcome = await NpmLockfileRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), ApplicationPlan(summary="no npm fields"), capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.package_not_in_dependencies")
    assert outcome.error.message == "ApplicationPlan missing package field"


# --- Edge branches ---------------------------------------------------------


async def test_package_json_root_not_an_object_is_adversarial(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """A package.json whose JSON root is an array (not an object) is rejected
    as adversarial repo content."""
    (tmp_path / "package.json").write_bytes(b"[]\n")
    (tmp_path / "package-lock.json").write_bytes(b"{}\n")
    outcome = await NpmLockfileRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.adversarial_repo_content")


async def test_lockfile_root_not_an_object_is_adversarial(
    express_repo: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """A regenerated lockfile whose JSON root is an array is rejected as
    adversarial repo content."""
    outcome = await NpmLockfileRecipeEngine(
        jail=RawWritingJail(b"[]\n"), transform_registry=TransformRegistry()
    ).apply(_sp(express_repo), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.adversarial_repo_content")


async def test_missing_package_json_surfaces_filesystem_race(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """An absent package.json cannot be resolved under the repo jail — the
    engine surfaces ``recipe.filesystem_race`` before any jail call."""
    jail = FakeJail(_completed(0))
    outcome = await NpmLockfileRecipeEngine(
        jail=jail, transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.filesystem_race")
    assert len(jail.calls) == 0


async def test_no_lockfile_after_install_surfaces_filesystem_race(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """When the repo has no initial lockfile and the jail writes none, the
    post-install lockfile resolution fails — exercising the empty ``before``
    lockfile path and the post-install resolution-failure branch."""
    (tmp_path / "package.json").write_bytes(
        orjson.dumps(
            {"name": "fixture", "version": "1.0.0", "dependencies": {"express": "^4.17.1"}},
            option=orjson.OPT_INDENT_2,
        )
        + b"\n"
    )
    outcome = await NpmLockfileRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=TransformRegistry()
    ).apply(_sp(tmp_path), plan, capability)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.error_id == ErrorId("recipe.filesystem_race")


def test_write_package_json_reraises_non_eloop_oserror(tmp_path: Path) -> None:
    """A non-``ELOOP`` ``OSError`` on write-back is re-raised loud, never
    masquerading as a filesystem race (Rule 12)."""
    bad = SandboxedPath(absolute=tmp_path / "missing-dir" / "package.json")
    with pytest.raises(OSError):  # noqa: PT011 — ENOENT, not ELOOP
        eng_mod._write_package_json(bad, b"{}\n")


# --- Determinism -----------------------------------------------------------


async def test_intra_run_determinism_five_fresh_fixtures(
    tmp_path: Path, plan: ApplicationPlan, capability: NpmInstallCapability
) -> None:
    """AC-Det-1 — five ``apply`` runs against five freshly-restored fixtures
    produce byte-identical ``diff_bytes`` exercising both file sections."""
    diffs: list[bytes] = []
    for index in range(5):
        repo = tmp_path / f"run-{index}"
        repo.mkdir()
        _write_repo(
            repo,
            {
                "name": "fixture",
                "version": "1.0.0",
                "dependencies": {"express": "^4.17.1", "lodash": "^4.17.21"},
            },
        )
        registry = TransformRegistry()
        outcome = await NpmLockfileRecipeEngine(
            jail=WritingJail(_CLEAN_LOCKFILE), transform_registry=registry
        ).apply(_sp(repo), plan, capability)
        assert isinstance(outcome, Applied)
        transform = registry.get(outcome.transform_id)
        assert b"--- file: package.json ---" in transform.diff_bytes
        assert b"--- file: package-lock.json ---" in transform.diff_bytes
        diffs.append(transform.diff_bytes)
    assert len(set(diffs)) == 1


# --- helpers ---------------------------------------------------------------


def _completed(exit_code: int) -> Completed:
    return Completed(
        kind="completed",
        exit_code=exit_code,
        stdout_bytes=0,
        stderr_bytes=0,
        wall_time_s=0.01,
    )


def _provenance() -> TransformProvenance:
    from codegenie.types.identifiers import EventId

    return TransformProvenance(
        plugin_id=PluginId("vuln-node-npm"),
        plugin_version="3.0.0",
        recipe_id=RecipeId("npm-lockfile-semver-bump"),
        recipe_version="3.0.0",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        capability_use_id=EventId("e" * 64),
    )
