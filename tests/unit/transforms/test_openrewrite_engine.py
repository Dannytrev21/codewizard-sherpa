"""S5-03 — :class:`OpenRewriteRecipeEngine` scaffold unit suite (fake jail).

Exercises the ADR-0014 contract: ``apply`` returns a bare
:data:`RecipeOutcome`; the produced :class:`DockerfileBaseImageTransform` is
surfaced via the constructor-injected :class:`TransformRegistry` and
retrieved with ``registry.get(outcome.transform_id)``. No test in this file
spawns a real ``java`` — every jail is a :class:`FakeJail` (AC-CI-1); the
real-JVM end-to-end test is the ``@pytest.mark.phase_7_preview`` integration
test, skipped in Phase-3 CI.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import blake3
import pytest

from codegenie.plugins.capabilities import NpmInstallCapability
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.engines import openrewrite as eng_mod
from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
from codegenie.transforms.engines.openrewrite import (
    _ERROR_IDS,
    DockerfileBaseImageTransform,
    OpenRewriteRecipeEngine,
    _OpenRewriteErrorId,
)
from codegenie.transforms.outcomes import (
    ApplicationPlan,
    Applied,
    RecipeError,
    RecipeFailed,
)
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.transforms.sandbox_jail import (
    Completed,
    DiskQuotaExceeded,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    JvmEnv,
    NetworkDenied,
    OomKilled,
    TimedOut,
)
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import (
    ErrorId,
    EventId,
    PluginId,
    RecipeId,
    RegistryUrl,
    TransformId,
    TransformKind,
)

_FIXTURE = Path(__file__).resolve().parents[3] / (
    "tests/fixtures/openrewrite/dockerfile-base-image-swap"
)
_ENGINE_SOURCE = Path(__file__).resolve().parents[3] / (
    "src/codegenie/transforms/engines/openrewrite.py"
)

# A real S4-05 capability — accepted only to satisfy the S5-01 ``RecipeEngine``
# Protocol signature; the scaffold threads it nowhere semantic (Phase-7 widens
# the capability union — see the engine's ``# TODO(Phase-7)`` marker).
_CAPABILITY = NpmInstallCapability(
    registry=RegistryUrl("https://registry.npmjs.org"),
    minted_by=PluginId("vuln-node-npm"),
)


# --- Fake jail -------------------------------------------------------------


class FakeJail:
    """Single-result fake :class:`SubprocessJail`; records every call."""

    def __init__(self, result: JailedSubprocessResult) -> None:
        self.result = result
        self.calls: list[JailedSubprocessSpec] = []

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        self.calls.append(spec)
        return self.result


def _completed(exit_code: int, *, stderr_bytes: int = 0, wall_time_s: float = 0.0) -> Completed:
    return Completed(
        kind="completed",
        exit_code=exit_code,
        stdout_bytes=0,
        stderr_bytes=stderr_bytes,
        wall_time_s=wall_time_s,
    )


# --- Fixtures + helpers ----------------------------------------------------


def _seed_dockerfile_fixture(tmp_path: Path) -> None:
    """Copy the side-by-side ``Dockerfile`` / ``expected.Dockerfile`` pair from
    the committed fixture into ``tmp_path`` so ``_build_transform`` can compute
    a real diff."""
    for name in ("Dockerfile", "expected.Dockerfile"):
        (tmp_path / name).write_bytes((_FIXTURE / name).read_bytes())


def _sp(path: Path) -> SandboxedPath:
    return SandboxedPath(absolute=path)


def _provenance(applied_at: datetime) -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("scaffold--phase7-preview"),
        plugin_version="0.0.0",
        recipe_id=RecipeId("dockerfile-base-image-swap"),
        recipe_version="0.0.0",
        transform_kind=TransformKind("dockerfile_base_image_swap"),
        applied_at=applied_at,
        capability_use_id=EventId("scaffold-noop"),
    )


@pytest.fixture
def dockerfile_plan() -> ApplicationPlan:
    # Phase-3 ``ApplicationPlan`` is ``summary: str | None`` only; Phase-7 widens.
    return ApplicationPlan(summary="dockerfile-base-image-swap")


@pytest.fixture
def registry() -> TransformRegistry:
    return TransformRegistry()


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    fixed = datetime(2026, 5, 20, 0, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(eng_mod, "_now_utc", lambda: fixed)
    return fixed


# --- Surface + module shape ------------------------------------------------


def test_module_all_is_exactly_the_two_public_names() -> None:
    """AC-Surface-1 — ``__all__`` re-exports only the engine + the transform."""
    assert set(eng_mod.__all__) == {"OpenRewriteRecipeEngine", "DockerfileBaseImageTransform"}


def test_module_exposes_no_private_helper_in_all() -> None:
    """AC-Surface-1 — no leading-underscore helper leaks into ``__all__``."""
    assert not any(name.startswith("_") for name in eng_mod.__all__)


async def test_engine_satisfies_recipe_engine_protocol_runtime(
    registry: TransformRegistry,
) -> None:
    """AC-Surface-2(a) — ``@runtime_checkable`` structural conformance."""
    engine = OpenRewriteRecipeEngine(jail=FakeJail(_completed(0)), transform_registry=registry)
    assert isinstance(engine, RecipeEngine)


def test_apply_signature_matches_npm_engine() -> None:
    """AC-Surface-2(c) + AC-Contract-1 — both day-1 engines share the bare
    ``-> RecipeOutcome`` return annotation and the same parameter list."""
    or_sig = inspect.signature(OpenRewriteRecipeEngine.apply)
    npm_sig = inspect.signature(NpmLockfileRecipeEngine.apply)
    assert str(or_sig.return_annotation) == str(npm_sig.return_annotation)
    assert str(or_sig.return_annotation) == "RecipeOutcome"
    assert list(or_sig.parameters.keys()) == ["self", "repo", "plan", "capability"]


def test_transform_is_transform_abc_subclass_with_tuple_files_changed(
    frozen_clock: datetime, tmp_path: Path
) -> None:
    """AC-Surface-3 — ``DockerfileBaseImageTransform`` subclasses the ``Transform``
    ABC; ``files_changed`` is a ``tuple``; the ABC stays un-instantiable."""
    assert issubclass(DockerfileBaseImageTransform, Transform)
    with pytest.raises(TypeError):
        Transform()  # type: ignore[abstract]
    transform = DockerfileBaseImageTransform.create(
        diff_bytes=b"+x\n",
        files_changed=(_sp(tmp_path / "Dockerfile"),),
        provenance=_provenance(frozen_clock),
    )
    assert isinstance(transform, Transform)
    assert isinstance(transform.files_changed, tuple)


def test_engine_holds_injected_collaborators_no_module_state() -> None:
    """AC-Surface-4 — both collaborators are constructor-injected; constructing
    an engine writes nothing to a global registry."""
    fresh = TransformRegistry()
    engine = OpenRewriteRecipeEngine(jail=FakeJail(_completed(0)), transform_registry=fresh)
    assert engine._transform_registry is fresh
    assert len(fresh) == 0


# --- Error-id taxonomy -----------------------------------------------------


def test_error_id_taxonomy_is_closed_six_entry_set() -> None:
    """AC-Tax-1 (drift-corrected) — the closed ``Literal`` has six entries
    (``recipe.jail_setup_failed`` is the sixth: ``JailedSubprocessResult``
    ships six variants, S4-01 GREEN — mirrors S5-02). Every member
    round-trips through the ``ErrorId`` newtype."""
    assert len(_ERROR_IDS) == 6
    members = get_args(_OpenRewriteErrorId)
    assert len(members) == 6
    for member in members:
        assert ErrorId(member) in _ERROR_IDS


# --- Spec construction -----------------------------------------------------


async def test_spec_cmd_is_exact_openrewrite_cli_tuple(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Spec-1 — bit-identical ``cmd`` tuple including the recipe path."""
    _seed_dockerfile_fixture(tmp_path)
    jail = FakeJail(_completed(0))
    await OpenRewriteRecipeEngine(
        jail=jail, transform_registry=registry, cli_jar_path="/test/rewrite.jar"
    ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)
    assert jail.calls[0].cmd == (
        "java",
        "-jar",
        "/test/rewrite.jar",
        "run",
        "--recipe",
        str(tmp_path / "recipe.yml"),
        "--in-place",
    )


async def test_spec_budget_envelope_is_pinned(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Spec-2 — pinned JVM budgets; mutating any constant fails the AC."""
    _seed_dockerfile_fixture(tmp_path)
    jail = FakeJail(_completed(0))
    await OpenRewriteRecipeEngine(jail=jail, transform_registry=registry).apply(
        _sp(tmp_path), dockerfile_plan, _CAPABILITY
    )
    spec = jail.calls[0]
    assert spec.time_budget_s == 300.0
    assert spec.memory_mib == 2048
    assert spec.pids_max == 64


async def test_spec_network_policy_is_deny_all(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Spec-3 — the JVM jail denies all egress (Dockerfile recipes need none)."""
    _seed_dockerfile_fixture(tmp_path)
    jail = FakeJail(_completed(0))
    await OpenRewriteRecipeEngine(jail=jail, transform_registry=registry).apply(
        _sp(tmp_path), dockerfile_plan, _CAPABILITY
    )
    assert jail.calls[0].network.kind == "deny_all"


def test_engine_source_constructs_no_registry_allowlist() -> None:
    """AC-Spec-3 — an AST walk confirms no code path under ``openrewrite.py``
    constructs a ``RegistryAllowlist`` (a Dockerfile rewrite must never open
    egress)."""
    tree = ast.parse(_ENGINE_SOURCE.read_text("utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "RegistryAllowlist" not in calls


async def test_spec_env_is_jvm_typed(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Spec-4 — the env is the typed ``JvmEnv`` discriminator with pinned
    ``java_home`` / ``max_heap_mib``."""
    _seed_dockerfile_fixture(tmp_path)
    jail = FakeJail(_completed(0))
    await OpenRewriteRecipeEngine(jail=jail, transform_registry=registry).apply(
        _sp(tmp_path), dockerfile_plan, _CAPABILITY
    )
    env = jail.calls[0].env
    assert isinstance(env, JvmEnv)
    assert env.kind == "jvm"
    assert env.java_home == "/opt/java"
    assert env.max_heap_mib == 1024


# --- Result mapping — exhaustive variant dispatch --------------------------


async def test_happy_path_returns_applied_and_registers_transform(
    tmp_path: Path,
    dockerfile_plan: ApplicationPlan,
    registry: TransformRegistry,
    frozen_clock: datetime,
) -> None:
    """AC-Map-1 + AC-Contract-1 — a clean ``Completed(exit_code=0)`` yields an
    ``Applied`` outcome; the produced transform is registered and retrievable
    by ``outcome.transform_id``."""
    _seed_dockerfile_fixture(tmp_path)
    repo = _sp(tmp_path)
    outcome = await OpenRewriteRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=registry
    ).apply(repo, dockerfile_plan, _CAPABILITY)
    assert isinstance(outcome, Applied)
    transform = registry.get(outcome.transform_id)
    assert isinstance(transform, DockerfileBaseImageTransform)
    assert transform.transform_id == outcome.transform_id
    assert transform.diff_bytes  # non-empty
    assert isinstance(transform.files_changed, tuple)
    assert len(transform.files_changed) == 1
    assert transform.files_changed[0].absolute == tmp_path / "Dockerfile"


_FAILURE_CASES: list[tuple[JailedSubprocessResult, str, set[str]]] = [
    (
        Completed(kind="completed", exit_code=2, stdout_bytes=0, stderr_bytes=42, wall_time_s=0.1),
        "recipe.openrewrite_nonzero_exit",
        {"exit_code", "stderr_bytes", "wall_time_s"},
    ),
    (
        TimedOut(kind="timed_out", budget_s=300.0, elapsed_s=301.5),
        "recipe.jvm_timeout",
        {"budget_s", "elapsed_s"},
    ),
    (
        OomKilled(kind="oom_killed", peak_rss_mib=2100),
        "recipe.jvm_oom",
        {"peak_rss_mib"},
    ),
    (
        NetworkDenied(kind="network_denied", host="maven.example.com"),
        "recipe.network_policy_violation",
        {"host"},
    ),
    (
        DiskQuotaExceeded(
            kind="disk_quota_exceeded", quota_bytes=1024**3, bytes_written=1024**3 + 1
        ),
        "recipe.disk_quota_exceeded",
        {"quota_bytes", "bytes_written"},
    ),
    (
        JailSetupFailed(
            kind="jail_setup_failed", reason="bwrap-not-on-path", detail="bwrap missing"
        ),
        "recipe.jail_setup_failed",
        {"reason", "detail"},
    ),
]


@pytest.mark.parametrize(
    ("result", "expected_id", "expected_detail_keys"),
    _FAILURE_CASES,
    ids=[case[1] for case in _FAILURE_CASES],
)
async def test_failure_variant_mapping(
    tmp_path: Path,
    dockerfile_plan: ApplicationPlan,
    registry: TransformRegistry,
    result: JailedSubprocessResult,
    expected_id: str,
    expected_detail_keys: set[str],
) -> None:
    """AC-Map-2..6 + the ``JailSetupFailed`` drift arm — every non-clean
    ``JailedSubprocessResult`` variant maps to a specific ``RecipeFailed``
    error id with the expected ``details`` keys; AC-Contract-2 — a non-Applied
    outcome registers nothing."""
    outcome = await OpenRewriteRecipeEngine(
        jail=FakeJail(result), transform_registry=registry
    ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)
    assert isinstance(outcome, RecipeFailed)
    assert isinstance(outcome.error, RecipeError)
    assert outcome.error.error_id == ErrorId(expected_id)
    assert outcome.error.details is not None
    assert set(outcome.error.details.keys()) == expected_detail_keys
    assert len(registry) == 0  # AC-Contract-2 — nothing registered on failure


async def test_happy_jail_result_but_missing_dockerfile_raises_loud(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Map-1 / Rule 12 — a clean ``Completed(exit_code=0)`` against a repo
    with no ``Dockerfile`` is a hard error: ``_resolve`` raises loud rather
    than fabricating an empty transform."""
    with pytest.raises(FileNotFoundError, match="not resolvable under the repo jail"):
        await OpenRewriteRecipeEngine(
            jail=FakeJail(_completed(0)), transform_registry=registry
        ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)


async def test_nonzero_exit_carries_observed_exit_code(
    tmp_path: Path, dockerfile_plan: ApplicationPlan, registry: TransformRegistry
) -> None:
    """AC-Map-2 — the failure ``details`` carry the observed exit code, not a
    hard-coded one (a mutant that ignores ``exit_code`` is caught)."""
    outcome = await OpenRewriteRecipeEngine(
        jail=FakeJail(_completed(7, stderr_bytes=9, wall_time_s=0.5)),
        transform_registry=registry,
    ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)
    assert isinstance(outcome, RecipeFailed)
    assert outcome.error.details == {"exit_code": 7, "stderr_bytes": 9, "wall_time_s": 0.5}


# --- Smart constructor -----------------------------------------------------


def test_smart_constructor_rejects_empty_diff_bytes(frozen_clock: datetime) -> None:
    """AC-Smart-1 — an empty diff is not a transform."""
    with pytest.raises(ValueError, match="diff_bytes must be non-empty"):
        DockerfileBaseImageTransform.create(
            diff_bytes=b"",
            files_changed=(_sp(Path("/tmp/Dockerfile")),),
            provenance=_provenance(frozen_clock),
        )


def test_smart_constructor_rejects_empty_files_changed(frozen_clock: datetime) -> None:
    """AC-Smart-1 — a transform that changed no file is meaningless."""
    with pytest.raises(ValueError, match="files_changed must be non-empty"):
        DockerfileBaseImageTransform.create(
            diff_bytes=b"+x\n",
            files_changed=(),
            provenance=_provenance(frozen_clock),
        )


def test_smart_constructor_transform_id_is_blake3_of_diff(frozen_clock: datetime) -> None:
    """AC-Smart-1 — ``transform_id`` is the BLAKE3-hex digest of ``diff_bytes``."""
    diff = b"-FROM node:20-alpine\n+FROM cgr.dev/chainguard/node:latest\n"
    transform = DockerfileBaseImageTransform.create(
        diff_bytes=diff,
        files_changed=(_sp(Path("/tmp/Dockerfile")),),
        provenance=_provenance(frozen_clock),
    )
    assert transform.transform_id == TransformId(blake3.blake3(diff).hexdigest())


async def test_provenance_carries_scaffold_sentinels(
    tmp_path: Path,
    dockerfile_plan: ApplicationPlan,
    registry: TransformRegistry,
    frozen_clock: datetime,
) -> None:
    """AC-Smart-2 — the produced transform's provenance carries the scaffold
    sentinel ids + the frozen-clock ``applied_at``."""
    _seed_dockerfile_fixture(tmp_path)
    outcome = await OpenRewriteRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=registry
    ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)
    assert isinstance(outcome, Applied)
    prov = registry.get(outcome.transform_id).provenance
    assert prov.plugin_id == PluginId("scaffold--phase7-preview")
    assert prov.plugin_version == "0.0.0"
    assert prov.recipe_id == RecipeId("dockerfile-base-image-swap")
    assert prov.recipe_version == "0.0.0"
    assert prov.transform_kind == TransformKind("dockerfile_base_image_swap")
    assert prov.capability_use_id == EventId("scaffold-noop")
    assert prov.applied_at == frozen_clock


async def test_applied_outcome_carries_scaffold_plugin_and_recipe_ids(
    tmp_path: Path,
    dockerfile_plan: ApplicationPlan,
    registry: TransformRegistry,
    frozen_clock: datetime,
) -> None:
    """AC-Map-1 — the ``Applied`` outcome's plugin / recipe ids are the
    scaffold sentinels."""
    _seed_dockerfile_fixture(tmp_path)
    outcome = await OpenRewriteRecipeEngine(
        jail=FakeJail(_completed(0)), transform_registry=registry
    ).apply(_sp(tmp_path), dockerfile_plan, _CAPABILITY)
    assert isinstance(outcome, Applied)
    assert outcome.plugin_id == PluginId("scaffold--phase7-preview")
    assert outcome.recipe_id == RecipeId("dockerfile-base-image-swap")


# --- Determinism -----------------------------------------------------------


async def test_diff_bytes_byte_identical_across_ten_runs(
    tmp_path: Path,
    dockerfile_plan: ApplicationPlan,
    frozen_clock: datetime,
) -> None:
    """AC-Det-1 — ten runs against the same fixture produce a byte-identical
    diff and transform id."""
    _seed_dockerfile_fixture(tmp_path)
    repo = _sp(tmp_path)
    seen_diffs: set[bytes] = set()
    seen_ids: set[str] = set()
    for _ in range(10):
        registry = TransformRegistry()
        outcome = await OpenRewriteRecipeEngine(
            jail=FakeJail(_completed(0)), transform_registry=registry
        ).apply(repo, dockerfile_plan, _CAPABILITY)
        assert isinstance(outcome, Applied)
        transform = registry.get(outcome.transform_id)
        seen_diffs.add(transform.diff_bytes)
        seen_ids.add(transform.transform_id)
    assert len(seen_diffs) == 1
    assert len(seen_ids) == 1


def test_diff_matches_committed_golden(frozen_clock: datetime) -> None:
    """AC-Det-1 / AC-Fix-1 — the engine's diff helper reproduces the committed
    ``expected.diff`` golden byte-for-byte."""
    before = (_FIXTURE / "Dockerfile").read_bytes()
    after = (_FIXTURE / "expected.Dockerfile").read_bytes()
    assert eng_mod._build_unified_diff(before, after) == (_FIXTURE / "expected.diff").read_bytes()


def test_unified_diff_passes_no_timestamp_arguments() -> None:
    """AC-Det-2 — an AST walk confirms no ``difflib.unified_diff`` call site
    passes ``fromfiledate=`` / ``tofiledate=`` (which would inject timestamps
    and break determinism)."""
    tree = ast.parse(_ENGINE_SOURCE.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "unified_diff":
            kwargs = {kw.arg for kw in node.keywords}
            assert "fromfiledate" not in kwargs
            assert "tofiledate" not in kwargs


# --- Smart-constructor is the only creation path (AC-Smart-1 fence) --------


def test_transform_constructed_only_via_smart_constructor() -> None:
    """AC-Smart-1 — an AST walk confirms ``DockerfileBaseImageTransform(...)``
    is never *called* directly anywhere in ``openrewrite.py``; the class is
    only ever materialised via ``DockerfileBaseImageTransform.create`` (which
    uses ``cls.__new__``)."""
    tree = ast.parse(_ENGINE_SOURCE.read_text("utf-8"))
    direct_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DockerfileBaseImageTransform"
    ]
    assert direct_calls == []


# --- AC-CI-1 — no real `java` invoked anywhere in this file ----------------


def test_this_suite_never_probes_for_java() -> None:
    """AC-CI-1 — no Phase-3 unit test reaches for a real ``java`` binary; an
    AST walk of this file finds no ``.which("java")`` probe (only the
    ``@pytest.mark.phase_7_preview`` integration test may probe for ``java``)."""
    tree = ast.parse(Path(__file__).read_text("utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "which"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "java"
        ):
            raise AssertionError("AC-CI-1: a Phase-3 unit test must not probe for a real `java`")
