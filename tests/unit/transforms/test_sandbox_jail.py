"""Unit tests for the Phase-3 ``SubprocessJail`` Port — S4-01.

Covers AC-1..AC-8, AC-10..AC-12, AC-15 structural assertions. The
exhaustiveness AC-9 lives in ``test_sandbox_jail_exhaustiveness.py``, the
mypy-narrowing AC-9a lives in ``test_sandbox_jail_mypy_negative.py``, and
the byte-equal contract snapshot AC-15 lives in
``test_sandbox_jail_contract_snapshot.py``.

ADR-0006 §Decision and §Tradeoffs row 4 pin the discriminated-union /
typed-variant-per-failure-mode discipline this file fences at runtime.
"""

from __future__ import annotations

import ast
import inspect
import math
import pathlib
import re

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    DiskQuotaExceeded,
    GitEnv,
    JailedEnv,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NetworkPolicy,
    NpmEnv,
    OomKilled,
    RegistryAllowlist,
    SubprocessJail,
    TimedOut,
)
from codegenie.types.identifiers import RegistryUrl

_OK_HOST = RegistryUrl("https://registry.npmjs.org")


def _spec(**overrides: object) -> JailedSubprocessSpec:
    """Minimal valid spec, override fields per-test."""
    base: dict[str, object] = dict(
        cmd=("npm", "install", "--ignore-scripts"),
        cwd=SandboxedPath(absolute=pathlib.Path("/tmp/jail")),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=60.0,
        memory_mib=512,
        pids_max=128,
    )
    base.update(overrides)
    return JailedSubprocessSpec(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-1 — exact public surface via ``__all__``.
# ---------------------------------------------------------------------------
def test_module_exports_exact() -> None:
    import codegenie.transforms.sandbox_jail as mod

    expected = {
        "SubprocessJail",
        "JailedSubprocessSpec",
        "JailedSubprocessResult",
        "JailedEnv",
        "Completed",
        "TimedOut",
        "OomKilled",
        "NetworkDenied",
        "DiskQuotaExceeded",
        "JailSetupFailed",
        "NpmEnv",
        "GitEnv",
        "NetworkPolicy",
        "DenyAll",
        "RegistryAllowlist",
    }
    assert set(mod.__all__) == expected


def test_no_export_annotated_as_typing_any() -> None:
    """AC-1 — no public symbol resolves to ``typing.Any`` (defence in depth
    against the Phase-3 ``Any`` fence)."""
    import codegenie.transforms.sandbox_jail as mod

    for name in mod.__all__:
        symbol = getattr(mod, name)
        annotations = inspect.get_annotations(symbol) if inspect.isclass(symbol) else {}
        for field, annot in annotations.items():
            assert annot is not object, (
                f"{name}.{field} annotated as `object`/`Any` — AC-1 forbids."
            )


# ---------------------------------------------------------------------------
# AC-2 — Protocol shape, not ``@runtime_checkable``.
# ---------------------------------------------------------------------------
def test_subprocess_jail_is_protocol_not_runtime_checkable() -> None:
    assert inspect.isclass(SubprocessJail)
    assert getattr(SubprocessJail, "_is_protocol", False) is True
    # Protocol member discovery — cross-version (3.11 lacks
    # ``__protocol_attrs__``, which arrived in 3.12). Walk ``vars()`` and
    # collect the public callables declared directly on the class. Plain
    # Protocols leave ``__abstractmethods__`` empty unless members are
    # explicitly decorated with ``@abstractmethod``.
    declared = {
        name
        for name, value in vars(SubprocessJail).items()
        if callable(value) and not name.startswith("_")
    }
    assert declared == {"run"}
    # Not ``@runtime_checkable`` — ``isinstance(jail, SubprocessJail)`` is a
    # Protocol foot-gun (ignores method signatures). Enforce structural typing.
    assert getattr(SubprocessJail, "_is_runtime_protocol", False) is False


# ---------------------------------------------------------------------------
# AC-2a — ``JailedEnv`` discriminator routes by ``kind``.
# ---------------------------------------------------------------------------
def test_jailed_env_discriminator_routes() -> None:
    adapter = TypeAdapter(JailedEnv)
    npm = adapter.validate_python({"kind": "npm"})
    git = adapter.validate_python({"kind": "git"})
    assert isinstance(npm, NpmEnv)
    assert isinstance(git, GitEnv)


def test_jailed_env_missing_discriminator_rejected() -> None:
    adapter = TypeAdapter(JailedEnv)
    with pytest.raises(ValidationError):
        adapter.validate_python({})


# ---------------------------------------------------------------------------
# AC-3 — frozen + ``extra="forbid"`` + every field annotated.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field",
    ["cmd", "cwd", "env", "network", "time_budget_s", "memory_mib", "pids_max"],
)
def test_jailed_subprocess_spec_is_frozen(field: str) -> None:
    spec = _spec()
    with pytest.raises(ValidationError):
        setattr(spec, field, getattr(spec, field))


def test_jailed_subprocess_spec_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        _spec(surprise="x")  # type: ignore[call-arg]


def test_jailed_subprocess_spec_every_field_typed() -> None:
    """AC-3 — every field's annotation is non-Any / non-object."""
    annotations = inspect.get_annotations(JailedSubprocessSpec, eval_str=False)
    assert annotations, "JailedSubprocessSpec must declare at least one field"
    for field, annot in annotations.items():
        assert annot is not object, f"{field} typed as object"


# ---------------------------------------------------------------------------
# AC-3a — smart-constructor bounds on ``JailedSubprocessSpec``.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"cmd": ()},  # min_length=1
        {"time_budget_s": 0.0},  # gt=0
        {"time_budget_s": -1.0},  # gt=0
        {"time_budget_s": math.nan},  # finite
        {"time_budget_s": math.inf},  # finite
        {"memory_mib": 0},  # ge=1
        {"memory_mib": -1},  # ge=1
        {"pids_max": 0},  # ge=1
        {"pids_max": -1},  # ge=1
    ],
)
def test_spec_smart_constructor_rejects(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _spec(**overrides)


# ---------------------------------------------------------------------------
# AC-4 — discriminator routing round-trips.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "variant",
    [
        Completed(
            kind="completed",
            exit_code=0,
            stdout_bytes=0,
            stderr_bytes=0,
            wall_time_s=0.1,
        ),
        Completed(
            kind="completed",
            exit_code=-9,
            stdout_bytes=0,
            stderr_bytes=0,
            wall_time_s=0.0,
        ),
        TimedOut(kind="timed_out", budget_s=60.0, elapsed_s=60.0),
        OomKilled(kind="oom_killed", peak_rss_mib=512),
        NetworkDenied(kind="network_denied", host="evil.example.com"),
        DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1024, bytes_written=2048),
        JailSetupFailed(
            kind="jail_setup_failed",
            reason="bwrap-not-on-path",
            detail="bwrap missing on this runner",
        ),
    ],
)
def test_result_variant_roundtrip(variant: object) -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    payload = adapter.dump_python(variant)
    parsed = adapter.validate_python(payload)
    assert type(parsed) is type(variant)
    assert parsed == variant


def test_result_wrong_kind_rejected() -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    with pytest.raises(ValidationError):
        # ``Completed`` has no ``host`` field, and ``extra="forbid"`` rejects.
        adapter.validate_python({"kind": "completed", "host": "x"})


# ---------------------------------------------------------------------------
# AC-4a — non-negative observable counters + finiteness.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ctor, kwargs",
    [
        (
            Completed,
            dict(
                kind="completed",
                exit_code=0,
                stdout_bytes=-1,
                stderr_bytes=0,
                wall_time_s=0.0,
            ),
        ),
        (
            Completed,
            dict(
                kind="completed",
                exit_code=0,
                stdout_bytes=0,
                stderr_bytes=-1,
                wall_time_s=0.0,
            ),
        ),
        (
            Completed,
            dict(
                kind="completed",
                exit_code=0,
                stdout_bytes=0,
                stderr_bytes=0,
                wall_time_s=-0.1,
            ),
        ),
        (
            Completed,
            dict(
                kind="completed",
                exit_code=0,
                stdout_bytes=0,
                stderr_bytes=0,
                wall_time_s=math.nan,
            ),
        ),
        (
            Completed,
            dict(
                kind="completed",
                exit_code=0,
                stdout_bytes=0,
                stderr_bytes=0,
                wall_time_s=math.inf,
            ),
        ),
        (TimedOut, dict(kind="timed_out", budget_s=0.0, elapsed_s=1.0)),  # gt=0
        (TimedOut, dict(kind="timed_out", budget_s=1.0, elapsed_s=math.inf)),
        (OomKilled, dict(kind="oom_killed", peak_rss_mib=-1)),
        (
            DiskQuotaExceeded,
            dict(kind="disk_quota_exceeded", quota_bytes=-1, bytes_written=0),
        ),
        (
            DiskQuotaExceeded,
            dict(kind="disk_quota_exceeded", quota_bytes=0, bytes_written=-1),
        ),
    ],
)
def test_result_variant_bounds(ctor: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ctor(**kwargs)


# ---------------------------------------------------------------------------
# AC-5 — ``NetworkDenied`` host required + serialized.
# ---------------------------------------------------------------------------
def test_network_denied_host_required_and_serialized() -> None:
    nd = NetworkDenied(kind="network_denied", host="evil.example.com")
    dumped = nd.model_dump()
    assert dumped["host"] == "evil.example.com"
    assert dumped["kind"] == "network_denied"
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied", host="")
    with pytest.raises(ValidationError):
        NetworkDenied(kind="network_denied")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AC-6 — ``NetworkPolicy`` discriminator + empty allowlist rejected.
# ---------------------------------------------------------------------------
def test_network_policy_discriminator_and_empty_allowlist_rejected() -> None:
    adapter = TypeAdapter(NetworkPolicy)
    deny = adapter.validate_python({"kind": "deny_all"})
    assert isinstance(deny, DenyAll)

    allow = adapter.validate_python(
        {"kind": "registry_allowlist", "hosts": ["https://registry.npmjs.org"]}
    )
    assert isinstance(allow, RegistryAllowlist)
    assert _OK_HOST in allow.hosts

    with pytest.raises(ValidationError):
        RegistryAllowlist(hosts=frozenset())


# ---------------------------------------------------------------------------
# AC-6a — strict ``https://`` smart-constructor on ``RegistryAllowlist.hosts``.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_host",
    [
        "http://registry.npmjs.org",
        "ftp://registry.npmjs.org",
        "file:///etc/passwd",
        "registry.npmjs.org",  # schemeless
        "",  # empty
        "https:/registry.npmjs.org",  # malformed
    ],
)
def test_registry_allowlist_rejects_non_https(bad_host: str) -> None:
    with pytest.raises(ValidationError):
        RegistryAllowlist(hosts=frozenset({RegistryUrl(bad_host)}))


# ---------------------------------------------------------------------------
# AC-7 — ``npm_config_ignore_scripts`` is structurally inviolable.
# ---------------------------------------------------------------------------
def test_npm_env_ignore_scripts_constructive() -> None:
    """AC-7 (a) constructive — only path through the public constructor."""
    assert NpmEnv().to_env_mapping()["npm_config_ignore_scripts"] == "true"


def test_npm_env_ignore_scripts_source_level_inviolable() -> None:
    """AC-7 (b) AST — the literal ``"true"`` is the only RHS assigned to that
    key inside ``NpmEnv.to_env_mapping``, and no other assignment in the body
    writes a different value to the same key."""
    import codegenie.transforms.sandbox_jail as mod

    tree = ast.parse(inspect.getsource(mod))
    npm_cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "NpmEnv")
    fn = next(
        n for n in npm_cls.body if isinstance(n, ast.FunctionDef) and n.name == "to_env_mapping"
    )
    writes_to_key = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and node.value == "npm_config_ignore_scripts"
    ]
    assert writes_to_key, "to_env_mapping must reference npm_config_ignore_scripts"
    body_src = ast.unparse(fn)
    assert '"true"' in body_src or "'true'" in body_src
    assert '"false"' not in body_src and "'false'" not in body_src


def test_npm_env_no_extension_trapdoor() -> None:
    """AC-7 (c) — no public field on ``NpmEnv`` carries the env-key substring."""
    fields = NpmEnv.model_fields.keys()
    assert not any("npm_config_ignore_scripts" in f for f in fields)


# ---------------------------------------------------------------------------
# AC-8 — ``GitEnv`` safety keys + same three-tier discipline.
# ---------------------------------------------------------------------------
def test_git_env_safety_keys_constructive() -> None:
    mapping = GitEnv().to_env_mapping()
    assert mapping["GIT_TERMINAL_PROMPT"] == "0"
    assert mapping["GIT_ASKPASS"] == "/bin/false"


def test_git_env_source_level_inviolable() -> None:
    """AC-8 AST — the safety keys are pinned to their values inside
    ``GitEnv.to_env_mapping``."""
    import codegenie.transforms.sandbox_jail as mod

    tree = ast.parse(inspect.getsource(mod))
    git_cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "GitEnv")
    fn = next(
        n for n in git_cls.body if isinstance(n, ast.FunctionDef) and n.name == "to_env_mapping"
    )
    body_src = ast.unparse(fn)
    assert '"GIT_TERMINAL_PROMPT"' in body_src or "'GIT_TERMINAL_PROMPT'" in body_src
    assert '"GIT_ASKPASS"' in body_src or "'GIT_ASKPASS'" in body_src
    assert '"0"' in body_src or "'0'" in body_src
    assert '"/bin/false"' in body_src or "'/bin/false'" in body_src


def test_git_env_no_extension_trapdoor() -> None:
    fields = GitEnv.model_fields.keys()
    assert not any("GIT_TERMINAL_PROMPT" in f or "GIT_ASKPASS" in f for f in fields)


# ---------------------------------------------------------------------------
# AC-10 — ``_StubJail`` proves the Port admits every variant in <10 lines.
# ---------------------------------------------------------------------------
class _StubJail:
    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        head = spec.cmd[0]
        if head == "_timeout":
            return TimedOut(kind="timed_out", budget_s=1.0, elapsed_s=1.0)
        if head == "_oom":
            return OomKilled(kind="oom_killed", peak_rss_mib=1)
        if head == "_neterr":
            return NetworkDenied(kind="network_denied", host="x")
        if head == "_diskerr":
            return DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1, bytes_written=2)
        return Completed(
            kind="completed",
            exit_code=0,
            stdout_bytes=0,
            stderr_bytes=0,
            wall_time_s=0.0,
        )


@pytest.mark.parametrize(
    "cmd0,expected_cls",
    [
        ("_ok", Completed),
        ("_timeout", TimedOut),
        ("_oom", OomKilled),
        ("_neterr", NetworkDenied),
        ("_diskerr", DiskQuotaExceeded),
    ],
)
async def test_protocol_admits_every_variant(cmd0: str, expected_cls: type) -> None:
    stub: SubprocessJail = _StubJail()
    spec = _spec(cmd=(cmd0,), network=RegistryAllowlist(hosts=frozenset({_OK_HOST})))
    result = await stub.run(spec)
    assert type(result) is expected_cls


# ---------------------------------------------------------------------------
# AC-11 — ``SandboxedPath`` import path is exact + identity check.
# ---------------------------------------------------------------------------
def test_cwd_imports_from_forward_shim() -> None:
    """AST-level: the file imports ``SandboxedPath`` from
    ``codegenie.transforms._forward`` exactly once and from no other module."""
    import codegenie.transforms.sandbox_jail as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    sandboxed_imports = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and any(a.name == "SandboxedPath" for a in n.names)
    ]
    assert len(sandboxed_imports) == 1
    assert sandboxed_imports[0].module == "codegenie.transforms._forward"


def test_cwd_annotation_identity() -> None:
    """Identity-level — ``model_fields["cwd"].annotation is SandboxedPath``."""
    assert JailedSubprocessSpec.model_fields["cwd"].annotation is SandboxedPath


# ---------------------------------------------------------------------------
# AC-12 — typed discipline grep, with subclass-of-Exception false-positive guard.
# ---------------------------------------------------------------------------
def test_module_source_has_no_dict_any_or_bare_exception() -> None:
    import codegenie.transforms.sandbox_jail as mod

    src = inspect.getsource(mod)
    assert re.search(r"\bdict\s*\[\s*str\s*,\s*Any\s*\]", src) is None
    assert re.search(r"\bDict\s*\[\s*str\s*,\s*Any\s*\]", src) is None
    assert re.search(r"^[ \t]*except[ \t]+Exception\b", src, re.MULTILINE) is None
    assert re.search(r"\braise\s+Exception\b", src) is None
    # No ``Any`` used as a Name in annotation position. AST walk avoids
    # false-positives on the word inside docstrings / string literals.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            pytest.fail(f"`Any` used in annotation position at line {node.lineno}")


# ---------------------------------------------------------------------------
# AC-15 — schema snapshot specificity.
# ---------------------------------------------------------------------------
def test_result_schema_has_oneof_with_six_variants_and_kind_discriminator() -> None:
    adapter = TypeAdapter(JailedSubprocessResult)
    schema = adapter.json_schema(by_alias=True)
    assert schema["discriminator"]["propertyName"] == "kind"
    # S4-02 AC-21 added ``JailSetupFailed`` as the sixth variant (additive
    # extension per S4-01 contract snapshot policy / Step 9 risk #4).
    assert len(schema["oneOf"]) == 6


def test_spec_schema_has_env_and_network_discriminators() -> None:
    schema = JailedSubprocessSpec.model_json_schema(by_alias=True)
    assert schema["properties"]["env"]["discriminator"]["propertyName"] == "kind"
    assert schema["properties"]["network"]["discriminator"]["propertyName"] == "kind"
    assert schema["properties"]["cmd"]["type"] == "array"
    assert schema["properties"]["cmd"].get("minItems", 0) == 1
