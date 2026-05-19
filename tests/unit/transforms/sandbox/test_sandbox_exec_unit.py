"""Cross-platform unit tests for :mod:`codegenie.transforms.sandbox.sandbox_exec`.

S4-03 ACs covered here: AC-1, AC-2 (signature half), AC-3..AC-9, AC-12,
AC-15..AC-25, AC-26 (smoke half), AC-27..AC-29. The macOS-live integration
half (AC-10, AC-11) lives under ``tests/integration/transforms/`` behind
``@pytest.mark.nightly_macos``; AC-2 (subprocess-mypy negative fixture)
lives in ``test_sandbox_exec_mypy_negative.py``; the wheel-install survival
companion to AC-26 is a future deferred fixture.

All chokepoint calls are mocked — these tests never spawn a real
``sandbox-exec``. The fence is the static AST check in
:func:`test_module_has_no_forbidden_subprocess_calls`.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import re
import string
import sys
from importlib import resources
from pathlib import Path
from typing import Any, cast
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.exec import ProcessResult
from codegenie.transforms import SandboxedPath
from codegenie.transforms.sandbox import bwrap, sandbox_exec
from codegenie.transforms.sandbox._classify import classify_outcome
from codegenie.transforms.sandbox.sandbox_exec import (
    _HELPER_VERBS,
    ProfilePlaceholderUnresolved,
    SandboxExecAdapter,
    SubstrateUnsupportedError,
    _build_argv,
    _extract_hostname,
    _extract_port,
    _load_template,
    _parse_sandbox_denial,
    _render_allow_network_clause,
    _render_allowlist_clauses,
    _render_profile,
)
from codegenie.transforms.sandbox_jail import (
    Completed,
    DenyAll,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NetworkPolicy,
    NpmEnv,
    RegistryAllowlist,
    SubprocessJail,
    TimedOut,
)
from codegenie.types.identifiers import RegistryUrl

# ---------------------------------------------------------------------------
# Test helpers — local to keep the production fakes module untouched.
# ---------------------------------------------------------------------------


def _make_spec(
    tmp_path: Path,
    *,
    cmd: tuple[str, ...] = ("/bin/echo", "hi"),
    network: NetworkPolicy | None = None,
    time_budget_s: float = 5.0,
) -> JailedSubprocessSpec:
    return JailedSubprocessSpec(
        cmd=cmd,
        cwd=SandboxedPath(absolute=tmp_path),
        env=NpmEnv(),
        network=network if network is not None else DenyAll(),
        time_budget_s=time_budget_s,
        memory_mib=128,
        pids_max=64,
    )


def _make_result(*, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> ProcessResult:
    return ProcessResult(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# AC-1 — packaged template well-formed.
# ---------------------------------------------------------------------------


def test_macos_sb_profile_template_well_formed() -> None:
    text = (
        resources.files("codegenie.transforms.sandbox.templates")
        .joinpath("macos-npm.sb")
        .read_text(encoding="utf-8")
    )
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(";;")]
    assert lines[0].strip() == "(version 1)"
    assert lines[1].strip() == "(deny default)"
    assert "$JAIL" in text
    assert "$ALLOWLIST_HOSTS" in text


# ---------------------------------------------------------------------------
# AC-15 — template polarity + sweeping-write guard.
# ---------------------------------------------------------------------------


def test_sb_template_polarity_and_no_sweeping_writes() -> None:
    raw = (
        resources.files("codegenie.transforms.sandbox.templates")
        .joinpath("macos-npm.sb")
        .read_text(encoding="utf-8")
    )
    # Strip ``;;`` comment lines — AC-15 fences the *active* clauses, not
    # documentation lines that may legally mention forms by name.
    text = "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith(";;"))
    assert "(allow default)" not in text
    assert text.count("(deny default)") == 1
    # Every (allow ... file-write* ...) form must carry a (subpath ...) target.
    for match in re.finditer(r"\(allow [^()]*file-write\*[^()]*\)", text):
        clause = match.group(0)
        # The (subpath ...) sub-clause may live in the same s-expression on
        # the next line — search the wider form starting at the (allow ... open.
        start = match.start()
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start=start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        full_form = text[start:end]
        assert "(subpath" in full_form, f"sweeping allow file-write*: {clause!r}"
    # Every (allow ... network* ...) form must carry a (remote ...) target
    # (the `$ALLOWLIST_HOSTS` placeholder text itself does not match — the
    # bare placeholder is not a sandbox clause).
    for match in re.finditer(r"\(allow [^()]*network\*[^()]*\)", text):
        clause = match.group(0)
        start = match.start()
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start=start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        full_form = text[start:end]
        assert "(remote" in full_form, f"sweeping allow network*: {clause!r}"


# ---------------------------------------------------------------------------
# AC-2 — structural Protocol conformance (signature + call-site).
# ---------------------------------------------------------------------------


def test_sandbox_exec_adapter_signature() -> None:
    sig = inspect.signature(SandboxExecAdapter.run)
    params = list(sig.parameters)
    assert params == ["self", "spec"]
    spec_param = sig.parameters["spec"]
    assert "JailedSubprocessSpec" in str(spec_param.annotation)
    assert "JailedSubprocessResult" in str(sig.return_annotation)


async def test_sandbox_exec_adapter_call_site_typechecks(tmp_path: Path) -> None:
    # Binds to Protocol-typed var — structural conformance is verified at
    # bind time + invocation. A mutant ``run = None`` would TypeError at
    # ``await adapter.run(...)``.
    adapter: SubprocessJail = SandboxExecAdapter()
    spec = _make_spec(tmp_path)

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        return _make_result()

    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await adapter.run(spec)
    assert isinstance(result, Completed)


# ---------------------------------------------------------------------------
# AC-3 — pure renderer.
# ---------------------------------------------------------------------------


def test_generated_sb_substitution(tmp_path: Path) -> None:
    template = _load_template()
    spec = _make_spec(
        tmp_path,
        network=RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")})),
    )
    rendered = _render_profile(template, spec)
    assert re.search(r"\$[A-Z_]+", rendered) is None
    assert str(tmp_path) in rendered
    # SBPL forbids hostnames in ``(remote tcp ...)``; hostname filtering
    # lives in pf rules (ADR-0006 §Consequences). The profile renders a
    # port-wildcard clause instead — hostname is validated upstream.
    assert '"*:443"' in rendered
    lines = [
        ln.strip() for ln in rendered.splitlines() if ln.strip() and not ln.strip().startswith(";;")
    ]
    assert lines[0] == "(version 1)"
    assert lines[1] == "(deny default)"
    assert rendered.count("(") == rendered.count(")"), "unbalanced parens"


# ---------------------------------------------------------------------------
# AC-4 — DenyAll has no allow-network clause.
# ---------------------------------------------------------------------------


def test_generated_sb_deny_all_has_no_allow_network(tmp_path: Path) -> None:
    template = _load_template()
    spec = _make_spec(tmp_path, network=DenyAll())
    rendered = _render_profile(template, spec)
    # Strip `;;` comment lines — they document the placeholder behaviour
    # by name and may mention forms the active body does not contain.
    active = "\n".join(ln for ln in rendered.splitlines() if not ln.strip().startswith(";;"))
    assert re.findall(r"\(allow network[^)]*remote tcp[^)]+\)", active) == []


# ---------------------------------------------------------------------------
# AC-5 — full-shape argv.
# ---------------------------------------------------------------------------


async def test_argv_full_shape(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return _make_result()

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        await SandboxExecAdapter().run(spec)
    argv = captured["argv"]
    assert argv[0] == "sandbox-exec"
    assert argv[1] == "-f"
    assert Path(argv[2]).suffix == ".sb"
    assert tuple(argv[3:]) == spec.cmd


def test_build_argv_pure() -> None:
    """:func:`_build_argv` is pure — no I/O, no chokepoint coupling."""
    out = _build_argv("/tmp/x.sb", ("npm", "test"))
    assert out == ["sandbox-exec", "-f", "/tmp/x.sb", "npm", "test"]


# ---------------------------------------------------------------------------
# AC-6 — AST-based forbidden-subprocess check.
# ---------------------------------------------------------------------------


def test_module_has_no_forbidden_subprocess_calls() -> None:
    src = Path("src/codegenie/transforms/sandbox/sandbox_exec.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{mod}.{alias.name}" if mod else alias.name

    bad_roots = {
        "subprocess",
        "os.system",
        "os.popen",
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "multiprocessing.Process",
    }
    bad_prefixes = ("os.exec", "os.spawn", "os.posix_spawn")

    def _resolve(name: str) -> str:
        head, *rest = name.split(".")
        head_resolved = aliases.get(head, head)
        return ".".join([head_resolved, *rest])

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            try:
                name = ast.unparse(node.func)
            except (AttributeError, ValueError):
                continue
            resolved = _resolve(name)
            for prefix in bad_prefixes:
                assert not resolved.startswith(prefix), f"forbidden call: {resolved}"
            root = resolved.split(".")[0]
            assert root != "subprocess", f"forbidden subprocess call: {resolved}"
            assert resolved not in bad_roots, f"forbidden call: {resolved}"
            # ``importlib.import_module("subprocess"|"os")`` literal check
            if name.endswith("import_module") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value in {
                    "subprocess",
                    "os",
                }:
                    pytest.fail(f"dynamic import of {first.value!r} forbidden")


# ---------------------------------------------------------------------------
# AC-7 — result-variant translation parametric.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "returncode, stderr, expected_type, expected_host",
    [
        (0, b"", Completed, None),
        (
            1,
            b"Sandbox: npm(1234) deny(1) network-outbound github.com:443\n",
            NetworkDenied,
            "github.com",
        ),
        (
            1,
            b"Sandbox: npm(1234) deny(1) network-outbound pypi.org:443\n",
            NetworkDenied,
            "pypi.org",
        ),
    ],
)
async def test_result_variant_translation(
    returncode: int,
    stderr: bytes,
    expected_type: type[Any],
    expected_host: str | None,
    tmp_path: Path,
) -> None:
    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        return _make_result(returncode=returncode, stderr=stderr)

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, expected_type)
    if expected_host is not None:
        assert isinstance(result, NetworkDenied)
        assert result.host == expected_host


# ---------------------------------------------------------------------------
# AC-8 — env mapping reaches the chokepoint verbatim.
# ---------------------------------------------------------------------------


async def test_env_mapping_reaches_chokepoint(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        captured["env_extra"] = kwargs.get("env_extra", {})
        return _make_result()

    spec = _make_spec(tmp_path, cmd=("npm", "--version"))
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        await SandboxExecAdapter().run(spec)
    assert captured["env_extra"].get("npm_config_ignore_scripts") == "true"


# ---------------------------------------------------------------------------
# AC-9 — spec.cmd preserved verbatim including any --ignore-scripts token.
# ---------------------------------------------------------------------------


async def test_cmd_preserved_verbatim_including_ignore_scripts(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return _make_result()

    cmd = ("npm", "install", "--ignore-scripts", "express@4.21.1")
    spec = _make_spec(tmp_path, cmd=cmd)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        await SandboxExecAdapter().run(spec)
    argv = captured["argv"]
    assert tuple(argv[-len(cmd) :]) == cmd


# ---------------------------------------------------------------------------
# AC-12 — pytest marker registered (no shell-out).
# ---------------------------------------------------------------------------


def test_nightly_macos_marker_registered(pytestconfig: pytest.Config) -> None:
    markers = pytestconfig.getini("markers")
    names = [str(m).split(":", 1)[0].strip() for m in markers]
    assert "nightly_macos" in names


# ---------------------------------------------------------------------------
# AC-16 — typed-error fence: no exception escapes the Port boundary.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [OSError("disk"), TimeoutError("budget"), Exception("oops")],
)
async def test_typed_error_fence(exc: BaseException, tmp_path: Path) -> None:
    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        raise exc

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await SandboxExecAdapter().run(spec)
    # Must return a typed variant — never propagate.
    assert result is not None
    # Specifically TimeoutError should round-trip as TimedOut via the kernel.
    if isinstance(exc, TimeoutError):
        # The kernel only maps ProbeTimeoutError to TimedOut; a bare
        # TimeoutError is treated as a setup failure. Either way, the
        # boundary discipline holds: no bare exception across the Port.
        assert isinstance(result, JailSetupFailed | TimedOut)


# ---------------------------------------------------------------------------
# AC-17 — determinism.
# ---------------------------------------------------------------------------


def test_render_is_deterministic(tmp_path: Path) -> None:
    template = _load_template()
    spec1 = _make_spec(
        tmp_path,
        network=RegistryAllowlist(
            hosts=frozenset(
                {
                    RegistryUrl("https://registry.npmjs.org"),
                    RegistryUrl("https://pypi.org"),
                }
            )
        ),
    )
    spec2 = _make_spec(
        tmp_path,
        network=RegistryAllowlist(
            hosts=frozenset(
                {
                    RegistryUrl("https://pypi.org"),
                    RegistryUrl("https://registry.npmjs.org"),
                }
            )
        ),
    )
    a = _render_profile(template, spec1)
    b = _render_profile(template, spec2)
    assert a == b
    assert _render_profile(template, spec1) == a


# ---------------------------------------------------------------------------
# AC-18 — Hypothesis properties.
# ---------------------------------------------------------------------------


_HYPOTHESIS_HOSTS = [
    "https://registry.npmjs.org",
    "https://pypi.org",
    "https://files.pythonhosted.org",
    "https://github.com",
]


# Hypothesis cannot inject pytest fixtures, so the property tests use a
# module-level tempdir captured at collection time. The actual cwd path
# is irrelevant for the substitution properties — only its presence as a
# literal in the rendered output matters.
_HYPOTHESIS_TMP = Path(__file__).parent  # any existing path suffices


@given(
    st.sets(
        st.sampled_from(_HYPOTHESIS_HOSTS),
        min_size=0,
        max_size=4,
    )
)
@settings(max_examples=25, deadline=None)
def test_property_deny_all_has_no_allow_network(host_strings: set[str]) -> None:
    template = _load_template()
    spec = _make_spec(_HYPOTHESIS_TMP, network=DenyAll())
    rendered = _render_profile(template, spec)
    active = "\n".join(ln for ln in rendered.splitlines() if not ln.strip().startswith(";;"))
    assert re.findall(r"\(allow network[^)]*remote tcp[^)]+\)", active) == []
    _ = host_strings  # property is the empty-DenyAll invariant


@given(
    st.sets(
        st.sampled_from(_HYPOTHESIS_HOSTS),
        min_size=1,
        max_size=4,
    )
)
@settings(max_examples=25, deadline=None)
def test_property_every_allowlisted_port_appears(host_strings: set[str]) -> None:
    """Property: every distinct port in the URL set appears as a
    ``(allow network* (remote tcp "*:PORT"))`` clause in the rendered
    profile. Hostnames are NOT emitted into SBPL — only ``*`` or
    ``localhost`` are valid in ``(remote tcp ...)``; hostname filtering
    lives in pf rules per ADR-0006 §Consequences.
    """
    template = _load_template()
    hosts = frozenset({RegistryUrl(s) for s in host_strings})
    spec = _make_spec(_HYPOTHESIS_TMP, network=RegistryAllowlist(hosts=hosts))
    rendered = _render_profile(template, spec)
    from urllib.parse import urlparse

    ports = {urlparse(s).port or 443 for s in host_strings}
    for p in ports:
        assert f'"*:{p}"' in rendered
    # Negative: no rendered hostname clauses leak through.
    for s in host_strings:
        host = urlparse(s).hostname
        assert host is not None
        assert f'"{host}:' not in rendered


@given(
    st.sets(
        st.sampled_from(_HYPOTHESIS_HOSTS),
        min_size=0,
        max_size=4,
    )
)
@settings(max_examples=25, deadline=None)
def test_property_render_byte_identical(host_strings: set[str]) -> None:
    template = _load_template()
    if host_strings:
        spec: JailedSubprocessSpec = _make_spec(
            _HYPOTHESIS_TMP,
            network=RegistryAllowlist(hosts=frozenset({RegistryUrl(s) for s in host_strings})),
        )
    else:
        spec = _make_spec(_HYPOTHESIS_TMP, network=DenyAll())
    assert _render_profile(template, spec) == _render_profile(template, spec)


# ---------------------------------------------------------------------------
# AC-19 — cleanup-on-exception.
# ---------------------------------------------------------------------------


async def test_cleanup_on_exception(tmp_path: Path) -> None:
    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        raise OSError("disk full")

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await SandboxExecAdapter().run(spec)
    assert result is not None
    leftover = list(Path(tmp_path).glob("*.sb"))
    assert leftover == [], f"leaked profile files: {leftover}"


# ---------------------------------------------------------------------------
# AC-20 — concurrent-run safety.
# ---------------------------------------------------------------------------


async def test_concurrent_runs_use_distinct_profiles(tmp_path: Path) -> None:
    captured_paths: list[str] = []
    lock = asyncio.Lock()

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        async with lock:
            captured_paths.append(argv[2])
        return _make_result()

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        await asyncio.gather(*[SandboxExecAdapter().run(spec) for _ in range(8)])
    assert len(captured_paths) == 8
    assert len(set(captured_paths)) == 8


# ---------------------------------------------------------------------------
# AC-21 — substrate-setup failure is typed.
# ---------------------------------------------------------------------------


async def test_substrate_setup_failure_typed(tmp_path: Path) -> None:
    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        return _make_result(
            returncode=65,
            stderr=b"Sandbox: sandbox-exec error: parse failure at line 3\n",
        )

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, JailSetupFailed)
    assert result.reason == "kernel-setup-failed"
    assert "parse failure" in result.detail


@pytest.mark.parametrize(
    "stderr_payload, expected_excerpt",
    [
        # CLI-emitted execvp denial (return 71 / EX_OSERR).
        (
            b"sandbox-exec: execvp() of '/bin/echo' failed: Operation not permitted\n",
            "execvp()",
        ),
        # CLI-emitted profile parse error (return 65).
        (
            b"sandbox-exec: host must be * or localhost in network address\n",
            "host must be",
        ),
    ],
)
async def test_substrate_setup_failure_cli_prefix_typed(
    stderr_payload: bytes,
    expected_excerpt: str,
    tmp_path: Path,
) -> None:
    """``sandbox-exec`` writes a *different* stderr prefix than the
    kernel ``Sandbox:`` form when its CLI rejects the profile or fails
    to ``execvp`` the child. Both must surface as
    ``JailSetupFailed(kernel-setup-failed)`` — Rule 12.
    """

    async def fake(argv: list[str], **kwargs: Any) -> ProcessResult:
        return _make_result(returncode=65, stderr=stderr_payload)

    spec = _make_spec(tmp_path)
    with mock.patch(
        "codegenie.transforms.sandbox.sandbox_exec.run_allowlisted",
        side_effect=fake,
    ):
        result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, JailSetupFailed)
    assert result.reason == "kernel-setup-failed"
    assert expected_excerpt in result.detail


# ---------------------------------------------------------------------------
# AC-22 — stateless across calls.
# ---------------------------------------------------------------------------


def test_module_has_no_module_level_mutable_globals() -> None:
    """AC-22 AST: every module-level ``Assign`` either targets ``__all__``
    or a ``NewType``-call binding; every ``AnnAssign`` carries
    ``Final[...]``. Mirrors the S4-02 AC-22 fence on bwrap.py.
    """
    import codegenie.transforms.sandbox.sandbox_exec as mod

    tree = ast.parse(inspect.getsource(mod))
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.AnnAssign):
            ann_src = ast.unparse(node.annotation) if node.annotation else ""
            assert "Final" in ann_src, (
                f"non-Final module-level annotation at line {node.lineno}: {ann_src}"
            )
            continue
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if targets == ["__all__"]:
                continue
            # Permit ``Hostname = typing.NewType("Hostname", str)`` —
            # ``NewType`` returns a callable, semantically a constant type
            # binding and conventional Python (mirrors S4-02 _SYSCALL_NAMES).
            if isinstance(node.value, ast.Call):
                callee = ast.unparse(node.value.func)
                if callee.endswith("NewType"):
                    continue
            raise AssertionError(
                f"module-level mutable assignment to {targets} at line {node.lineno}"
            )


# ---------------------------------------------------------------------------
# AC-23 — classifier kernel identity.
# ---------------------------------------------------------------------------


def test_classifier_kernel_is_shared_with_bwrap() -> None:
    # Story header text says ``_classify_outcome``; the actual extracted
    # kernel name is ``classify_outcome``. The identity check is on the
    # function object, not the name string.
    assert sandbox_exec.classify_outcome is classify_outcome
    assert bwrap.classify_outcome is classify_outcome
    assert bwrap.classify_outcome is sandbox_exec.classify_outcome


# ---------------------------------------------------------------------------
# AC-24 — `match` exhaustiveness on NetworkPolicy.
# ---------------------------------------------------------------------------


def test_match_assert_never_fires_on_synthetic() -> None:
    class _Bogus:
        pass

    with pytest.raises((AssertionError, TypeError)):
        _render_allowlist_clauses(cast(NetworkPolicy, _Bogus()))


# ---------------------------------------------------------------------------
# AC-25 — Hostname smart-constructor.
# ---------------------------------------------------------------------------


def test_extract_hostname_validates() -> None:
    h = _extract_hostname(RegistryUrl("https://registry.npmjs.org"))
    assert h == "registry.npmjs.org"
    with pytest.raises(ValueError):
        _extract_hostname(RegistryUrl("not-a-url"))


def test_extract_hostname_rejects_bad_charset() -> None:
    with pytest.raises(ValueError):
        # ``urlparse`` will return an empty hostname for this malformed URL.
        _extract_hostname(RegistryUrl("https:///nopath"))


def test_render_allow_network_clause_consumes_hostname() -> None:
    h = _extract_hostname(RegistryUrl("https://registry.npmjs.org"))
    clause = _render_allow_network_clause(h, 443)
    assert clause == '(allow network* (remote tcp "registry.npmjs.org:443"))'


def test_extract_port_default_and_custom() -> None:
    assert _extract_port(RegistryUrl("https://registry.npmjs.org")) == 443
    assert _extract_port(RegistryUrl("https://example.com:8443")) == 8443


# ---------------------------------------------------------------------------
# AC-26 — packaged-template load (smoke half; wheel-install half deferred).
# ---------------------------------------------------------------------------


def test_template_loads_via_importlib_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    # Smoke: works regardless of CWD — the wheel-install survival fixture
    # is deferred to a tox env per the story's coordination note.
    monkeypatch.chdir("/tmp")
    text = (
        resources.files("codegenie.transforms.sandbox.templates")
        .joinpath("macos-npm.sb")
        .read_text(encoding="utf-8")
    )
    assert "(deny default)" in text


# ---------------------------------------------------------------------------
# AC-27 — macOS 14+ gate.
# ---------------------------------------------------------------------------


def test_macos_13_raises_substrate_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.mac_ver", lambda: ("13.6.0", ("", "", ""), ""))
    with pytest.raises(SubstrateUnsupportedError):
        SandboxExecAdapter()


def test_macos_14_constructs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.mac_ver", lambda: ("14.0.0", ("", "", ""), ""))
    SandboxExecAdapter()  # must not raise


def test_non_darwin_constructs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construction is a no-op on non-darwin; ``platform.mac_ver`` returns
    an empty tuple there. The gate only fires on darwin."""
    monkeypatch.setattr(sys, "platform", "linux")
    SandboxExecAdapter()  # must not raise


# ---------------------------------------------------------------------------
# AC-28 — placeholder residual check.
# ---------------------------------------------------------------------------


def test_placeholder_residual_raises_typed(tmp_path: Path) -> None:
    bad_template = string.Template("(version 1)\n(deny default)\n$UNRESOLVED_TOKEN\n")
    spec = _make_spec(tmp_path)
    with pytest.raises(ProfilePlaceholderUnresolved) as excinfo:
        _render_profile(bad_template, spec)
    assert excinfo.value.token == "$UNRESOLVED_TOKEN"


# ---------------------------------------------------------------------------
# AC-29 — hexagonal-shape parity.
# ---------------------------------------------------------------------------


def test_helper_verb_parity() -> None:
    assert bwrap._HELPER_VERBS == _HELPER_VERBS


# ---------------------------------------------------------------------------
# AC-7 supplement — _parse_sandbox_denial unit coverage.
# ---------------------------------------------------------------------------


def test_parse_sandbox_denial_extracts_host() -> None:
    stderr = b"Sandbox: npm(1234) deny(1) network-outbound github.com:443\n"
    host = _parse_sandbox_denial(stderr)
    assert host == "github.com"


def test_parse_sandbox_denial_returns_none_on_miss() -> None:
    assert _parse_sandbox_denial(b"no match here") is None
    # Random text that loosely resembles the pattern but isn't a denial
    assert _parse_sandbox_denial(b"Sandbox: hello world") is None


def test_parse_sandbox_denial_returns_first_on_multi() -> None:
    stderr = (
        b"Sandbox: npm(1) deny(1) network-outbound github.com:443\n"
        b"Sandbox: npm(1) deny(1) network-outbound pypi.org:443\n"
    )
    assert _parse_sandbox_denial(stderr) == "github.com"
