"""S4-04 — ``SandboxedPath`` smart-constructor, ``O_NOFOLLOW`` ``open()``,
and the load-bearing TOCTOU regression.

AC mapping (per ``docs/phases/03-vuln-deterministic-recipe/stories/
S4-04-sandboxed-path-onofollow.md``):

* AC-1, AC-2/AC-2b/AC-relative-shape — module surface + happy paths
* AC-3/AC-4/AC-4b/AC-5/AC-12 — disjoint error variants + audit-payload pins
* AC-6a/AC-6b/AC-sum-type-coverage — frozen / extra-forbid / sum-type closure
* AC-7/AC-7a/AC-7b/AC-7c — ``_MANDATORY_FLAGS`` plumbing + flag composition
* AC-fd-leak — ``os.fdopen`` failure closes the underlying fd
* AC-fail-loud — AST-scan asserts ``open()`` catches nothing
* AC-8/AC-9/AC-benign-replacement — TOCTOU symlink swap → ``ELOOP``
* AC-10a/AC-10b/AC-10c — known limitations documented as living tests
* AC-15a/AC-15b/AC-15c — module docstring dual-discipline framing
* AC-Sub-1 — ``transforms.SandboxedPath is plugins.sandbox_path.SandboxedPath``
"""

from __future__ import annotations

import ast
import errno
import fcntl
import os
import typing
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from codegenie.plugins.sandbox_path import (
    _MANDATORY_FLAGS,
    PathEscape,
    SandboxedPath,
    _flags_for_mode,
)
from codegenie.result import Err, Ok

# ---------------------------------------------------------------------------
# AC-1 — surface lock
# ---------------------------------------------------------------------------


def test_module_all_is_alphabetized_pair() -> None:
    import codegenie.plugins.sandbox_path as mod

    assert mod.__all__ == ["PathEscape", "SandboxedPath"]
    publics = {n for n in vars(mod) if not n.startswith("_")}
    leaked = publics - set(mod.__all__) - {"annotations"}  # __future__ side effect
    # Filter out re-exported types from typing/pydantic/etc that are not symbols
    # we declared. The strict check: every non-underscore name in vars() that is
    # *defined* in this module must be in __all__.
    import inspect

    declared = {
        n
        for n in publics
        if getattr(vars(mod)[n], "__module__", None) == "codegenie.plugins.sandbox_path"
        or inspect.isclass(vars(mod)[n])
        and vars(mod)[n].__module__ == "codegenie.plugins.sandbox_path"
    }
    leaked = declared - set(mod.__all__)
    assert not leaked, f"unintended public surface: {leaked!r}"


def test_result_imported_from_canonical_module() -> None:
    """Proves the implementer used codegenie.result (NOT codegenie.types.result)."""
    import codegenie.plugins.sandbox_path as mod

    src = Path(mod.__file__).read_text()
    assert "from codegenie.result import" in src
    assert "codegenie.types.result" not in src


# ---------------------------------------------------------------------------
# AC-2 / AC-2b — happy paths
# ---------------------------------------------------------------------------


def test_create_happy_path(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hi")
    sp = SandboxedPath.create(tmp_path, "file.txt").unwrap()
    assert sp.absolute == (tmp_path / "file.txt").resolve()
    assert isinstance(sp, BaseModel)
    # AC-2 / AC-11 anti-confusion check — SandboxedPath is a BaseModel,
    # not a Path subclass; pin the negative so a future "make it a Path
    # subclass for ergonomics" regression is loud.
    assert not isinstance(sp, Path)  # type: ignore[unreachable]


def test_create_with_symlinked_jail_resolves_both(tmp_path: Path) -> None:
    real_jail = tmp_path / "real"
    real_jail.mkdir()
    alias_jail = tmp_path / "alias"
    os.symlink(real_jail, alias_jail)
    (real_jail / "f.txt").write_text("ok")
    sp = SandboxedPath.create(alias_jail, "f.txt").unwrap()
    assert sp.absolute == (real_jail / "f.txt").resolve()


# ---------------------------------------------------------------------------
# AC-relative-shape — edge cases on the ``relative`` arg
# ---------------------------------------------------------------------------


def test_relative_empty_string_returns_jail(tmp_path: Path) -> None:
    sp = SandboxedPath.create(tmp_path, "").unwrap()
    assert sp.absolute == tmp_path.resolve(strict=True)


def test_relative_dot_returns_jail(tmp_path: Path) -> None:
    sp = SandboxedPath.create(tmp_path, ".").unwrap()
    assert sp.absolute == tmp_path.resolve(strict=True)


def test_relative_absolute_path_rejected_eagerly(tmp_path: Path) -> None:
    """Absolute ``relative`` strings must be rejected before any FS call —
    ``(jail_abs / "/etc/passwd")`` evaluates to ``/etc/passwd`` (pathlib
    drops the LHS), so eager rejection is the only safe shape."""
    result = SandboxedPath.create(tmp_path, "/etc/passwd")
    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert err.reason == "absolute"
    assert err.attempted_path == "/etc/passwd"


# ---------------------------------------------------------------------------
# AC-3 / AC-4 / AC-4b / AC-5 / AC-12 — disjoint error variants
# ---------------------------------------------------------------------------


def test_create_path_escape_via_dotdot(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    result = SandboxedPath.create(jail, "../outside.txt")
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, PathEscape)
    assert err.reason == "not_under_jail"
    assert Path(err.attempted_path).resolve() == outside.resolve()
    assert Path(err.jail).resolve() == jail.resolve()


def test_create_missing_leaf(tmp_path: Path) -> None:
    err = SandboxedPath.create(tmp_path, "does-not-exist.txt").unwrap_err()
    assert err.reason == "missing"  # exact, no disjunction


def test_create_when_jail_does_not_exist(tmp_path: Path) -> None:
    err = SandboxedPath.create(tmp_path / "no-such-jail", "x.txt").unwrap_err()
    assert err.reason == "invalid_jail"


def test_create_broken_symlink_is_not_resolvable(tmp_path: Path) -> None:
    (tmp_path / "broken-link").symlink_to("/does/not/exist/anywhere/i-promise")
    err = SandboxedPath.create(tmp_path, "broken-link").unwrap_err()
    assert err.reason == "not_resolvable"  # NOT "missing"


def test_create_symlink_target_outside_jail_rejected(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("target")
    (jail / "file.txt").symlink_to(outside)
    err = SandboxedPath.create(jail, "file.txt").unwrap_err()
    assert err.reason == "not_under_jail"
    assert Path(err.attempted_path).resolve() == outside.resolve()


# ---------------------------------------------------------------------------
# AC-6a / AC-6b — frozen + extra="forbid"
# ---------------------------------------------------------------------------


def test_sandboxed_path_is_frozen_basemodel(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "x.txt").unwrap()
    assert issubclass(SandboxedPath, BaseModel)
    assert SandboxedPath.model_config.get("frozen") is True
    assert SandboxedPath.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        sp.absolute = Path("/etc")


def test_sandboxed_path_extra_forbid() -> None:
    """Construction with an unexpected kwarg raises (extra=forbid)."""
    with pytest.raises(ValidationError):
        SandboxedPath(absolute=Path("/tmp"), extra="bad")  # type: ignore[call-arg]


def test_path_escape_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        PathEscape(
            attempted_path="/x",
            jail="/y",
            reason="not_under_jail",
            extra="bad",  # type: ignore[call-arg]
        )


def test_path_escape_frozen() -> None:
    err = PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail")
    with pytest.raises(ValidationError):
        err.reason = "missing"


# ---------------------------------------------------------------------------
# AC-sum-type-coverage — every PathEscape.reason literal has a producer
# ---------------------------------------------------------------------------


def test_every_path_escape_reason_has_a_producing_test(tmp_path: Path) -> None:
    reasons = set(typing.get_args(PathEscape.model_fields["reason"].annotation))
    produced: set[str] = set()
    # not_under_jail — via dotdot
    jail = tmp_path / "j"
    jail.mkdir()
    (tmp_path / "x").write_text("")
    produced.add(SandboxedPath.create(jail, "../x").unwrap_err().reason)
    # missing
    produced.add(SandboxedPath.create(tmp_path, "nope").unwrap_err().reason)
    # invalid_jail
    produced.add(SandboxedPath.create(tmp_path / "no-jail", "x").unwrap_err().reason)
    # absolute
    produced.add(SandboxedPath.create(tmp_path, "/etc/passwd").unwrap_err().reason)
    # not_resolvable
    (tmp_path / "broken").symlink_to("/no/such/path/here")
    produced.add(SandboxedPath.create(tmp_path, "broken").unwrap_err().reason)
    assert produced == reasons, f"unreached reasons: {reasons - produced}"


# ---------------------------------------------------------------------------
# AC-7 / AC-7a / AC-7b / AC-7c — mandatory flags + mode dispatch
# ---------------------------------------------------------------------------


def test_mandatory_flags_constant() -> None:
    assert _MANDATORY_FLAGS & os.O_NOFOLLOW != 0
    assert _MANDATORY_FLAGS & os.O_CLOEXEC != 0


_MODE_BASE_CHECKS: list[tuple[str, Callable[[int], bool]]] = [
    ("r", lambda f: (f & 0b11) == os.O_RDONLY),
    ("rb", lambda f: (f & 0b11) == os.O_RDONLY),
    ("w", lambda f: bool(f & os.O_WRONLY and f & os.O_CREAT and f & os.O_TRUNC)),
    ("wb", lambda f: bool(f & os.O_WRONLY and f & os.O_CREAT and f & os.O_TRUNC)),
    (
        "a",
        lambda f: bool(
            f & os.O_WRONLY and f & os.O_CREAT and f & os.O_APPEND and not f & os.O_TRUNC
        ),
    ),
    (
        "ab",
        lambda f: bool(
            f & os.O_WRONLY and f & os.O_CREAT and f & os.O_APPEND and not f & os.O_TRUNC
        ),
    ),
    ("r+", lambda f: bool(f & os.O_RDWR)),
    ("x", lambda f: bool(f & os.O_WRONLY and f & os.O_CREAT and f & os.O_EXCL)),
    ("xb", lambda f: bool(f & os.O_WRONLY and f & os.O_CREAT and f & os.O_EXCL)),
]


@pytest.mark.parametrize("mode,base_assertion", _MODE_BASE_CHECKS)
def test_open_flag_composition_per_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    base_assertion: Callable[[int], bool],
) -> None:
    # x / xb require the file to NOT exist; other modes need it.
    leaf_name = "leaf-new.txt" if mode.startswith("x") else "leaf-existing.txt"
    if not mode.startswith("x"):
        (tmp_path / leaf_name).write_text("")
    # We need a SandboxedPath whose .absolute points at the leaf. For
    # x/xb the leaf does not exist yet, so .create() would fail with
    # "missing". Construct directly via the BaseModel constructor for
    # those modes.
    if mode.startswith("x"):
        sp = SandboxedPath(absolute=(tmp_path / leaf_name).resolve())
    else:
        sp = SandboxedPath.create(tmp_path, leaf_name).unwrap()

    captured: list[int] = []
    real_open = os.open

    def spy_open(p: object, flags: int, *a: object, **kw: object) -> int:
        captured.append(flags)
        return real_open(p, flags, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", spy_open)
    try:
        f = sp.open(mode)
        f.close()
    except OSError:
        pass  # only captured flags matter for this AC

    assert captured, "os.open was never called"
    for flags in captured:
        assert flags & os.O_NOFOLLOW, f"O_NOFOLLOW missing for mode={mode!r}; flags={flags}"
        assert flags & os.O_CLOEXEC, f"O_CLOEXEC missing for mode={mode!r}; flags={flags}"
        assert base_assertion(flags), (
            f"base flag composition wrong for mode={mode!r}; flags={flags}"
        )


def test_returned_fd_has_fd_cloexec(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("ok")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    f = sp.open("rb")
    try:
        fd = f.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        assert flags & fcntl.FD_CLOEXEC
    finally:
        f.close()


@given(mode=st.sampled_from(["r", "rb", "w", "wb", "a", "ab", "r+", "x", "xb"]))
def test_flags_for_mode_does_not_set_mandatory_flags(mode: str) -> None:
    flags = _flags_for_mode(mode)
    # Helper returns BASE flags only — open() ORs in _MANDATORY_FLAGS.
    assert (flags & os.O_NOFOLLOW) == 0
    assert (flags & os.O_CLOEXEC) == 0


@pytest.mark.parametrize("bad", ["q", "", "rwx", "rbz"])
def test_flags_for_mode_unknown_mode_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        _flags_for_mode(bad)


def test_open_unknown_mode_raises_loudly(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    with pytest.raises(ValueError):
        sp.open("q")


# ---------------------------------------------------------------------------
# AC-fd-leak — os.fdopen failure must close the underlying fd
# ---------------------------------------------------------------------------


def test_open_closes_fd_when_fdopen_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    captured_fd: list[int] = []
    real_open = os.open

    def spy_open(p: object, flags: int, *a: object, **kw: object) -> int:
        fd = real_open(p, flags, *a, **kw)  # type: ignore[arg-type]
        captured_fd.append(fd)
        return fd

    def fail_fdopen(*args: object, **kwargs: object) -> object:
        raise OSError("synthetic fdopen failure")

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "fdopen", fail_fdopen)

    with pytest.raises(OSError):
        sp.open("rb")
    assert captured_fd, "os.open was never called"
    with pytest.raises(OSError) as ei:
        os.fstat(captured_fd[0])
    assert ei.value.errno == errno.EBADF


# ---------------------------------------------------------------------------
# AC-fail-loud — AST-scan asserts open() catches nothing
# ---------------------------------------------------------------------------


def test_open_method_has_no_exception_handlers() -> None:
    import codegenie.plugins.sandbox_path as mod

    src = Path(mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "open":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Try):
                    assert not sub.handlers, (
                        "SandboxedPath.open() must not catch exceptions; "
                        "consumers handle OSError(errno=ELOOP). try/finally "
                        "is OK; try/except is not."
                    )
            return
    raise AssertionError("SandboxedPath.open method not found")


# ---------------------------------------------------------------------------
# AC-8 — THE LOAD-BEARING TOCTOU TEST
# ---------------------------------------------------------------------------


def test_symlink_swap_between_create_and_open_raises_eloop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "realfile.txt"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "realfile.txt").unwrap()

    target.unlink()
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("attacker target")
    os.symlink(elsewhere, target)

    opened_fds: list[int] = []
    real_open = os.open

    def spy_open(p: object, flags: int, *a: object, **kw: object) -> int:
        fd = real_open(p, flags, *a, **kw)  # type: ignore[arg-type]
        opened_fds.append(fd)
        return fd

    monkeypatch.setattr(os, "open", spy_open)

    with pytest.raises(OSError) as excinfo:
        sp.open("rb")
    assert excinfo.value.errno == errno.ELOOP
    # Confidentiality: no fd was opened on the attacker target.
    assert opened_fds == [], (
        f"os.open should have raised ELOOP before returning an fd; opened fds: {opened_fds}"
    )


# ---------------------------------------------------------------------------
# AC-9 — directory-symlink swap → ELOOP
# ---------------------------------------------------------------------------


def test_directory_symlink_swap_raises_eloop(tmp_path: Path) -> None:
    target = tmp_path / "dir_or_file"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "dir_or_file").unwrap()
    target.unlink()
    other_dir = tmp_path / "other_dir"
    other_dir.mkdir()
    os.symlink(other_dir, target)
    with pytest.raises(OSError) as ei:
        sp.open("rb")
    assert ei.value.errno == errno.ELOOP


# ---------------------------------------------------------------------------
# AC-benign-replacement — atomic real-file swap is NOT a TOCTOU target
# ---------------------------------------------------------------------------


def test_benign_real_file_replacement_is_permitted(tmp_path: Path) -> None:
    f1 = tmp_path / "f.txt"
    f1.write_text("v1")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    f2 = tmp_path / "f2.txt"
    f2.write_text("v2")
    os.replace(f2, f1)  # atomic real-file swap; no symlink involved
    with sp.open("rb") as f:
        assert f.read() == b"v2"


# ---------------------------------------------------------------------------
# AC-10a / AC-10b / AC-10c — known limitations (living documentation)
# ---------------------------------------------------------------------------


def test_intermediate_component_symlink_is_not_caught(tmp_path: Path) -> None:
    realdir = tmp_path / "realdir"
    realdir.mkdir()
    (realdir / "b.txt").write_text("ok")
    os.symlink(realdir, tmp_path / "aliased")
    sp = SandboxedPath.create(tmp_path, "aliased/b.txt").unwrap()
    with sp.open("rb") as f:
        assert f.read() == b"ok"


def test_hardlink_swap_is_not_caught(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("trusted")
    sp = SandboxedPath.create(tmp_path, "real.txt").unwrap()
    other = tmp_path / "other.txt"
    other.write_text("attacker")
    real.unlink()
    os.link(other, real)
    with sp.open("rb") as f:
        content = f.read()
    assert content == b"attacker", "documents the hardlink-swap limitation"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo not available")
def test_fifo_replacement_is_not_caught_by_o_nofollow(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("ok")
    # Construct so create() resolves while still a regular file.
    SandboxedPath.create(tmp_path, "real.txt").unwrap()
    real.unlink()
    os.mkfifo(real)
    # Use non-blocking probe to avoid deadlock — O_NOFOLLOW does NOT block FIFOs.
    fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        # Reached: O_NOFOLLOW did NOT raise. Limitation confirmed.
        pass
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# AC-15a / AC-15b / AC-15c — module docstring dual discipline
# ---------------------------------------------------------------------------


def test_module_docstring_uses_honest_framing() -> None:
    import codegenie.plugins.sandbox_path as mod

    doc = mod.__doc__ or ""
    low = doc.lower()
    # Positive: required substrings
    assert "in-jail at construction" in doc
    assert "audit + lint" in low or "audit and lint" in low
    assert "adr-0011" in low
    # Negative: banned framings (case-insensitive)
    for banned in (
        "in-jail forever",
        "unforgeable",
        "makes illegal states unrepresentable",
        "illegal states unrepresentable",
        "signature",
    ):
        assert banned not in low, f"docstring contains banned phrase: {banned!r}"
    # Limitations enumerated
    for phrase in ("intermediate", "hardlink", "fifo"):
        assert phrase in low, f"docstring missing limitation phrase: {phrase!r}"


# ---------------------------------------------------------------------------
# AC-Sub-1 — transforms.SandboxedPath IS plugins.sandbox_path.SandboxedPath
# ---------------------------------------------------------------------------


def test_transforms_sandboxed_path_is_plugins_sandboxed_path() -> None:
    from codegenie.plugins.sandbox_path import SandboxedPath as B
    from codegenie.transforms import SandboxedPath as A

    assert A is B


# ---------------------------------------------------------------------------
# AC-11 — JailedSubprocessSpec.cwd accepts a real SandboxedPath instance
# ---------------------------------------------------------------------------


def test_sandboxed_path_satisfies_subprocess_jail_cwd(tmp_path: Path) -> None:
    from codegenie.plugins.sandbox_path import SandboxedPath as PluginsSP
    from codegenie.transforms import SandboxedPath as TransformsSP

    assert TransformsSP is PluginsSP

    from codegenie.transforms.sandbox_jail import (
        DenyAll,
        JailedSubprocessSpec,
        NpmEnv,
    )

    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=sp,
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=1.0,
        memory_mib=1,
        pids_max=1,
    )
    assert spec.cwd is sp
    assert isinstance(spec.cwd, BaseModel)
    assert not isinstance(spec.cwd, Path)  # type: ignore[unreachable]


# ---------------------------------------------------------------------------
# Smart-constructor returns Ok/Err — discriminated-union sanity
# ---------------------------------------------------------------------------


def test_create_returns_ok_variant(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    result = SandboxedPath.create(tmp_path, "f.txt")
    assert isinstance(result, Ok)
    assert result.is_ok()
    assert not result.is_err()


def test_create_returns_err_variant(tmp_path: Path) -> None:
    result = SandboxedPath.create(tmp_path, "nope")
    assert isinstance(result, Err)
    assert result.is_err()
    assert not result.is_ok()
