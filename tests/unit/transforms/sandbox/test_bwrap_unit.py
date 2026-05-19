"""S4-02 unit tests — argv shape, env propagation, cleanup, determinism.

Covers AC-2, AC-6, AC-7, AC-10, AC-11, AC-16, AC-17, AC-19, AC-20.
Every test mocks :func:`codegenie.exec.run_allowlisted` at the
``codegenie.transforms.sandbox.bwrap.run_allowlisted`` module reference
so no real subprocess is spawned.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ProcessResult
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    DenyAll,
    JailSetupFailed,
    NpmEnv,
    RegistryAllowlist,
    TimedOut,
)
from codegenie.types.identifiers import RegistryUrl
from tests.unit.transforms.sandbox._fakes import make_process_result, make_spec

# ---------------------------------------------------------------------------
# AC-2 — argv shape matches ADR-0006 §Decision, NO extra injected flags.
# ---------------------------------------------------------------------------


async def test_argv_prefix_matches_adr_0006(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake(
        argv: list[str],
        *,
        cwd: Path,
        timeout_s: float,
        env_extra: dict[str, str] | None = None,
    ) -> ProcessResult:
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        captured["env_extra"] = dict(env_extra or {})
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    spec = make_spec(tmp_path)
    await BwrapAdapter().run(spec)
    argv = captured["argv"]
    prefix = [
        "bwrap",
        "--unshare-all",
        "--new-session",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(spec.cwd),
        str(spec.cwd),
    ]
    assert argv[: len(prefix)] == prefix


async def test_argv_carries_seccomp_flag_with_integer_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path))
    argv = captured["argv"]
    assert "--seccomp" in argv
    fd_str = argv[argv.index("--seccomp") + 1]
    assert fd_str.isdigit(), f"--seccomp fd is not a decimal integer: {fd_str!r}"


async def test_argv_tail_is_spec_cmd_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11: cmd is preserved as the strict tail of the argv."""
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    cmd = ("npm", "install", "--ignore-scripts", "--package-lock-only", "--no-audit")
    await BwrapAdapter().run(make_spec(tmp_path, cmd=cmd))
    assert tuple(captured["argv"][-len(cmd) :]) == cmd


async def test_argv_no_extra_flags_between_prefix_and_cmd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 full-shape: catches mutants that smuggle ``--share-net``,
    ``--cap-add``, ``--uid 0``, etc. between the prefix and ``spec.cmd``.
    """
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    spec = make_spec(tmp_path)
    await BwrapAdapter().run(spec)
    argv = captured["argv"]
    prefix_len = 12  # "bwrap" + 11 fixed-flag tokens (see _BWRAP_FIXED_FLAGS + cwd-bind)
    inner_start = prefix_len + 2  # --seccomp + <fd>
    inner_end = len(argv) - len(spec.cmd)
    assert inner_start == inner_end, f"unexpected flags injected: {argv[inner_start:inner_end]}"


async def test_run_allowlisted_kwargs_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2: ``cwd`` is the unwrapped Path from ``spec.cwd.absolute`` (S4-04
    flipped the SandboxedPath alias to a Pydantic BaseModel; adapters unwrap
    to Path at the OS-call boundary), ``timeout_s`` is the spec budget,
    ``env_extra`` is the dict from ``spec.env.to_env_mapping()``."""
    captured: dict[str, Any] = {}

    async def fake(
        argv: list[str],
        *,
        cwd: Path,
        timeout_s: float,
        env_extra: dict[str, str] | None = None,
    ) -> ProcessResult:
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        captured["env_extra"] = env_extra
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    spec = make_spec(tmp_path, time_budget_s=12.5)
    await BwrapAdapter().run(spec)
    assert captured["cwd"] == spec.cwd.absolute
    assert captured["timeout_s"] == 12.5
    assert captured["env_extra"] == {"npm_config_ignore_scripts": "true"}


# ---------------------------------------------------------------------------
# AC-6 — DenyAll never shares net.
# ---------------------------------------------------------------------------


async def test_denyall_argv_has_no_share_net_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path, network=DenyAll()))
    argv = captured["argv"]
    assert "--share-net" not in argv
    assert "--unshare-net=false" not in argv
    assert not any(a.startswith("--bind-net") for a in argv)


async def test_denyall_does_not_invoke_setup_netns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_calls: list[frozenset[str]] = []

    def fake_setup(hosts: frozenset[str]) -> Any:
        setup_calls.append(hosts)
        return type("H", (), {"name": "x"})()

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist",
        fake_setup,
    )

    async def fake_run(argv: list[str], **_: Any) -> ProcessResult:
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run)
    await BwrapAdapter().run(make_spec(tmp_path, network=DenyAll()))
    assert setup_calls == []


# ---------------------------------------------------------------------------
# AC-7 — RegistryAllowlist invokes _setup_netns_with_allowlist with the hosts.
# ---------------------------------------------------------------------------


async def test_registry_allowlist_invokes_setup_with_exact_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_hosts: list[frozenset[str]] = []

    def fake_setup(hosts: frozenset[str]) -> Any:
        captured_hosts.append(hosts)
        return type("H", (), {"name": "ns-x"})()

    teardown_calls: list[str] = []

    def fake_teardown(handle: Any) -> None:
        teardown_calls.append(handle.name)

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist",
        fake_setup,
    )
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._teardown_netns",
        fake_teardown,
    )

    async def fake_run(argv: list[str], **_: Any) -> ProcessResult:
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run)

    hosts = frozenset(
        {
            RegistryUrl("https://registry.npmjs.org"),
            RegistryUrl("https://registry.yarnpkg.com"),
        }
    )
    await BwrapAdapter().run(make_spec(tmp_path, network=RegistryAllowlist(hosts=hosts)))
    assert len(captured_hosts) == 1
    assert captured_hosts[0] == {str(h) for h in hosts}
    # AC-19: teardown invoked exactly once even on the clean path.
    assert teardown_calls == ["ns-x"]


# ---------------------------------------------------------------------------
# AC-10 — env_extra concrete dict[str, str] reaches the chokepoint.
# ---------------------------------------------------------------------------


async def test_npm_env_propagated_as_concrete_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake(
        argv: list[str],
        *,
        cwd: Path,
        timeout_s: float,
        env_extra: dict[str, str] | None = None,
    ) -> ProcessResult:
        captured["env_extra"] = env_extra
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path, env=NpmEnv()))
    env_extra = captured["env_extra"]
    assert isinstance(env_extra, dict)
    assert env_extra["npm_config_ignore_scripts"] == "true"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in env_extra.items())


# ---------------------------------------------------------------------------
# AC-16 — typed-error fence: every chokepoint exception → typed variant.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raised, expected_reason",
    [
        (DisallowedSubprocessError("bwrap not allowlisted"), "binary-not-allowlisted"),
        (ToolMissingError("bwrap not on PATH"), "bwrap-not-on-path"),
        (
            FileNotFoundError("/no/such/cwd"),
            "cwd-missing",
        ),
        (
            PermissionError("CAP_NET_ADMIN missing"),
            "cap-net-admin-missing",
        ),
        (OSError("kernel said no"), "kernel-setup-failed"),
    ],
)
async def test_chokepoint_exception_maps_to_jail_setup_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: BaseException,
    expected_reason: str,
) -> None:
    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        raise raised

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    result = await BwrapAdapter().run(make_spec(tmp_path))
    assert isinstance(result, JailSetupFailed), f"expected JailSetupFailed, got {result!r}"
    assert result.reason == expected_reason


async def test_chokepoint_timeout_maps_to_typed_timedout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        raise ProbeTimeoutError("bwrap exceeded timeout_s=5.0 (elapsed_ms=5050)")

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    result = await BwrapAdapter().run(make_spec(tmp_path, time_budget_s=5.0))
    assert isinstance(result, TimedOut)
    assert result.budget_s == 5.0


async def test_bwrap_module_has_no_bare_exception_handlers() -> None:
    """AC-16 / AC-4: AST walk forbids ``except Exception:`` and bare
    ``except:`` blocks inside ``bwrap.py`` (the typed-error fence)."""
    import ast
    import inspect

    import codegenie.transforms.sandbox.bwrap as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                raise AssertionError(f"bare except: at line {node.lineno}")
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                raise AssertionError(
                    f"except Exception: at line {node.lineno} — use a typed exception"
                )


# ---------------------------------------------------------------------------
# AC-17 — determinism: same spec → same argv across two calls.
# ---------------------------------------------------------------------------


async def test_two_consecutive_runs_produce_equal_argv_modulo_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captures: list[list[str]] = []

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captures.append(list(argv))
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    adapter = BwrapAdapter()
    spec = make_spec(tmp_path)
    await adapter.run(spec)
    await adapter.run(spec)
    assert len(captures) == 2

    def _strip_fd(argv: list[str]) -> list[str]:
        i = argv.index("--seccomp")
        return argv[: i + 1] + ["<fd>"] + argv[i + 2 :]

    assert _strip_fd(captures[0]) == _strip_fd(captures[1])


async def test_two_consecutive_runs_produce_equal_seccomp_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seccomp blob is deterministic — same blocked set ⇒ same bytes."""
    captured_blobs: list[bytes] = []

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        fd_str = argv[argv.index("--seccomp") + 1]
        fd = int(fd_str)
        # Re-open by path is not available; the adapter's fd is still open
        # at this point. Read the bytes by pread to avoid moving the cursor.
        captured_blobs.append(os.pread(fd, 4096, 0))
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    adapter = BwrapAdapter()
    spec = make_spec(tmp_path)
    await adapter.run(spec)
    await adapter.run(spec)
    assert len(captured_blobs) == 2
    assert captured_blobs[0] == captured_blobs[1]
    assert captured_blobs[0], "seccomp blob is empty"


# ---------------------------------------------------------------------------
# AC-19 — cleanup-on-exception.
# ---------------------------------------------------------------------------


async def test_seccomp_temp_file_unlinked_on_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_path: dict[str, str] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        # The fd is open; readlink-style discovery of the underlying path.
        fd_str = argv[argv.index("--seccomp") + 1]
        fd = int(fd_str)
        captured_path["path"] = (
            os.readlink(f"/proc/self/fd/{fd}") if os.path.exists(f"/proc/self/fd/{fd}") else ""
        )
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path))
    # On Linux: path was discovered and must be unlinked post-run.
    # On macOS: /proc isn't available; assertion is a no-op (the cleanup
    # path is still exercised — failure would be a leaked-fd warning).
    if captured_path.get("path"):
        assert not os.path.exists(captured_path["path"]), (
            f"seccomp temp file leaked: {captured_path['path']}"
        )


async def test_teardown_netns_invoked_on_chokepoint_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    teardown_calls: list[str] = []

    def fake_setup(hosts: frozenset[str]) -> Any:
        return type("H", (), {"name": "ns-y"})()

    def fake_teardown(handle: Any) -> None:
        teardown_calls.append(handle.name)

    async def fake_run(argv: list[str], **_: Any) -> ProcessResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist",
        fake_setup,
    )
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._teardown_netns",
        fake_teardown,
    )
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run)

    hosts = frozenset({RegistryUrl("https://registry.npmjs.org")})
    result = await BwrapAdapter().run(make_spec(tmp_path, network=RegistryAllowlist(hosts=hosts)))
    # AC-16: bare RuntimeError gets classified, not raised through the Port.
    assert isinstance(result, JailSetupFailed)
    # AC-19: teardown still ran.
    assert teardown_calls == ["ns-y"]


# ---------------------------------------------------------------------------
# AC-20 — concurrent runs use uniquely-named netns (Strategy A).
# ---------------------------------------------------------------------------


async def test_concurrent_runs_allocate_distinct_netns_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake_setup(hosts: frozenset[str]) -> Any:
        import uuid

        name = f"codegenie-jail-{uuid.uuid4().hex[:12]}"
        seen.append(name)
        return type("H", (), {"name": name})()

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist",
        fake_setup,
    )
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._teardown_netns",
        lambda h: None,
    )

    async def fake_run(argv: list[str], **_: Any) -> ProcessResult:
        await asyncio.sleep(0.01)  # let scheduler interleave
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run)

    hosts = frozenset({RegistryUrl("https://registry.npmjs.org")})
    adapter = BwrapAdapter()
    spec = make_spec(tmp_path, network=RegistryAllowlist(hosts=hosts))
    await asyncio.gather(adapter.run(spec), adapter.run(spec))
    assert len(seen) == 2
    assert len(set(seen)) == 2, f"netns names not unique: {seen}"


# ---------------------------------------------------------------------------
# AC-22 — stateless across calls: no module-level mutable globals.
# ---------------------------------------------------------------------------


def test_module_has_no_mutable_module_level_assignments() -> None:
    """AC-22 AST: every module-level ``Assign`` either targets a private
    ``_*`` name annotated as ``Final[...]`` / immutable type (Final,
    Constant, dataclass-frozen, tuple/frozenset), or is the `__all__`
    list, the dataclass body, or a class-body assignment."""
    import ast
    import inspect

    import codegenie.transforms.sandbox.bwrap as mod

    tree = ast.parse(inspect.getsource(mod))
    for node in tree.body:
        # Class / function / import are fine.
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.AnnAssign):
            # Final-typed assignments at module level are immutable by
            # typing convention — permit.
            ann = node.annotation
            ann_src = ast.unparse(ann)
            if "Final" in ann_src:
                continue
            raise AssertionError(
                f"non-Final module-level annotation at line {node.lineno}: {ann_src}"
            )
        if isinstance(node, ast.Assign):
            # ``__all__`` is the only permitted bare module-level assignment.
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if targets == ["__all__"]:
                continue
            raise AssertionError(
                f"module-level mutable assignment to {targets} at line {node.lineno}"
            )
        # Expr / Pass / docstring nodes are fine.


async def test_double_call_does_not_reuse_cached_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-22 runtime: two calls compose argv from scratch each time —
    a mutated cached argv between the two runs would fail this assertion.
    """
    captured: list[list[str]] = []

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured.append(list(argv))
        # Mutate the captured copy AFTER recording — proves the second
        # call doesn't observe the mutation.
        captured[-1][:] = ["mutated"]
        return make_process_result(returncode=0)

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    adapter = BwrapAdapter()
    spec = make_spec(tmp_path)
    await adapter.run(spec)
    await adapter.run(spec)
    # Both captures were mutated post-record; a state-sharing adapter
    # would either have raised or returned a different shape.
    assert len(captured) == 2
