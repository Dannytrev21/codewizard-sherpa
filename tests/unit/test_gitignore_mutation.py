"""S4-03 — `.gitignore` mutation routine (AC-1..AC-23).

Logging assertions use :func:`structlog.testing.capture_logs` (not capsys)
because pytest's ``capsys`` rotates the ``sys.stdout``/``sys.stderr``
``CaptureIO`` between fixture setup and the test body. That swap defeats
both (a) ``monkeypatch.setattr(sys.stdout, "isatty", ...)`` — the patched
isatty lives on the pre-swap stream — and (b) ``structlog`` configured with
``PrintLoggerFactory(file=sys.stderr)`` — the factory caches the closed
pre-swap stream. ``capture_logs`` swaps the structlog processor chain
in-process and yields the raw event-dict list, so it is immune to both
issues. The level field is named ``log_level`` (not ``level``) in
capture_logs output — pinned in every assertion. WHY each test matters
(Rule 9) is in each docstring.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import structlog

CANONICAL_BLOCK = b"# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n"


class _ConfirmSpy:
    """Spy that records ``click.confirm`` calls and returns a fixed answer.

    A class (not a list) because ``list`` does not accept arbitrary attribute
    assignment — ``calls.return_value = ...`` would raise ``AttributeError``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.return_value: bool = True

    def __call__(self, *args: Any, **kwargs: Any) -> bool:
        self.calls.append((args, kwargs))
        return self.return_value

    def __len__(self) -> int:
        return len(self.calls)

    def __iter__(self) -> Any:
        return iter(self.calls)

    def __eq__(self, other: object) -> bool:
        return self.calls == other


def _load() -> Callable[..., None]:
    """Lazy import so ModuleNotFoundError is the first red marker."""
    from codegenie.output.gitignore import maybe_append_gitignore

    return maybe_append_gitignore


def _gitignore_events(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter capture_logs output down to ``gitignore.*`` events."""
    return [e for e in logs if str(e.get("event", "")).startswith("gitignore.")]


@pytest.fixture
def both_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``is_tty=True`` for both stdin and stdout.

    Intentionally DOES NOT depend on ``capsys`` — pytest's capsys rotates
    ``sys.stdout`` between fixture setup and the test body, which would
    silently lose the monkeypatched ``isatty``.
    """
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)


@pytest.fixture
def no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)


@pytest.fixture
def confirm_spy(monkeypatch: pytest.MonkeyPatch) -> _ConfirmSpy:
    spy = _ConfirmSpy()
    monkeypatch.setattr("click.confirm", spy)
    return spy


# ---------- Surface ----------


def test_signature_matches_s4_02_stub() -> None:
    """AC-1: signature is locked to S4-02 AC-14's pinned stub.

    ``from __future__ import annotations`` (Rule 11 — codebase convention)
    stores annotations as strings; ``eval_str=True`` resolves them.
    """
    fn = _load()
    sig = inspect.signature(fn, eval_str=True)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["repo_root", "auto", "skip"]
    assert params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[2].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.return_annotation in (None, type(None))


def test_tty_detection_uses_both_stdin_and_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, confirm_spy: _ConfirmSpy
) -> None:
    """AC-2: stdin-tty but stdout-pipe must take the non-TTY branch (CI prompt bug)."""
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert len(confirm_spy) == 0, "must not prompt when stdout is not a tty"
    events = _gitignore_events(logs)
    assert len(events) == 1
    assert events[0]["event"] == "gitignore.append.skipped"
    assert events[0]["reason"] == "non_tty"
    assert events[0]["log_level"] == "warning"


# ---------- Six core branches ----------


def test_tty_accept_appends_canonical_block_byte_exact(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-3 + AC-9: byte-exact append, comment line preserved, prior content untouched."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK
    assert len(confirm_spy) == 1
    events = _gitignore_events(logs)
    assert len(events) == 1
    assert events[0]["event"] == "gitignore.append.accepted"
    assert events[0]["reason"] == "tty_accept"
    assert events[0]["log_level"] == "info"


def test_tty_decline_byte_identical_and_no_mtime_change(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-4: decline path is a true no-op."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    confirm_spy.return_value = False
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    assert len(confirm_spy) == 1
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.declined"
        and e["reason"] == "tty_decline"
        and e["log_level"] == "info"
        for e in events
    )


def test_non_tty_skip_warns_and_does_not_prompt(
    tmp_path: Path, no_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-5: non-TTY never prompts; emits WARNING with reason=non_tty."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert len(confirm_spy) == 0, "non-TTY must not prompt"
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.skipped"
        and e["reason"] == "non_tty"
        and e["log_level"] == "warning"
        for e in events
    )


def test_auto_flag_appends_without_prompt_even_on_tty(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-6: auto bypasses confirm even when TTY is available (hostile case)."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK
    assert len(confirm_spy) == 0, "auto flag must bypass click.confirm"
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.accepted" and e["reason"] == "auto_flag" for e in events
    )


def test_skip_flag_never_writes_and_never_prompts(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-7: skip is the highest-precedence path; no prompt, no write, DEBUG event."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=True)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    assert len(confirm_spy) == 0
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.skipped"
        and e["reason"] == "never_flag"
        and e["log_level"] == "debug"
        for e in events
    )


def test_idempotent_pre_existing_marker_does_not_rewrite(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-8 + AC-19 stage-1: pre-existing line means no rewrite, mtime unchanged."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n.codegenie/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    confirm_spy.return_value = True
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n.codegenie/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.idempotent" and e["log_level"] == "debug" for e in events
    )


# ---------- Write contract: byte-exact, atomic, regular-file-only ----------


def test_no_trailing_newline_in_existing_file_gets_leading_newline(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    r"""AC-9: existing 'node_modules/' (no \n) yields '...\n# codewizard...\n.codegenie/\n'."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/")
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK


def test_empty_existing_gitignore_writes_canonical_block_as_sole_content(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-9: zero-byte existing file is treated like 'no leading content'; no blank prefix."""
    (tmp_path / ".gitignore").write_bytes(b"")
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_uses_atomic_replace_pattern(
    tmp_path: Path,
    both_tty: None,
    confirm_spy: _ConfirmSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-10: spy on os.fsync and os.replace; both must fire; fsync before replace.

    Mutation-kill: open(path, 'a') would never call os.replace.
    """
    order: list[str] = []
    import codegenie.output.gitignore as g

    real_fsync = g.os.fsync
    real_replace = g.os.replace

    def _spy_fsync(fd: int) -> None:
        order.append("fsync")
        real_fsync(fd)

    def _spy_replace(src: Any, dst: Any) -> None:
        order.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(g.os, "fsync", _spy_fsync)
    monkeypatch.setattr(g.os, "replace", _spy_replace)
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=True, skip=False)
    assert order == ["fsync", "replace"], "atomic write must fsync before replace"


def test_codegenie_inside_comment_is_not_idempotent(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-11: false-positive guard. A comment mentioning '.codegenie/' must not block append."""
    initial = b"# do not commit .codegenie/ in real builds\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    _load()(tmp_path, auto=True, skip=False)
    final = (tmp_path / ".gitignore").read_bytes()
    assert final == initial + CANONICAL_BLOCK
    assert final.count(b".codegenie/") == 2


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_non_regular_gitignore_refused(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy, kind: str
) -> None:
    """AC-12: symlinks and directories trigger 'unsafe_path' skip, no mutation."""
    gi = tmp_path / ".gitignore"
    if kind == "symlink":
        target = tmp_path / "other.txt"
        target.write_bytes(b"node_modules/\n")
        gi.symlink_to(target)
    else:
        gi.mkdir()
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=True, skip=False)
    if kind == "symlink":
        assert gi.is_symlink()
        assert (tmp_path / "other.txt").read_bytes() == b"node_modules/\n"
    else:
        assert gi.is_dir()
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.skipped"
        and e["reason"] == "unsafe_path"
        and e["log_level"] == "warning"
        for e in events
    )


def test_idempotent_with_crlf_line_endings(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    r"""AC-13: CRLF '.codegenie/\r\n' must register as idempotent via \s in the regex."""
    initial = b"node_modules/\r\n.codegenie/\r\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == initial
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before


# ---------- AC-14: file does not exist (four sub-cases) ----------


def test_no_gitignore_tty_accept_creates_file(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-14a"""
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_no_gitignore_auto_creates_file(
    tmp_path: Path, no_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-14b: auto flag must also create the file on non-TTY runners (CI)."""
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_no_gitignore_tty_decline_does_not_create(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-14c"""
    confirm_spy.return_value = False
    _load()(tmp_path, auto=False, skip=False)
    assert not (tmp_path / ".gitignore").exists()


def test_no_gitignore_non_tty_does_not_create(
    tmp_path: Path, no_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-14d"""
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=False, skip=False)
    assert not (tmp_path / ".gitignore").exists()
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.skipped" and e["reason"] == "non_tty" for e in events
    )


# ---------- Failure handling (AC-15..AC-18) ----------


def test_skip_beats_auto_at_helper_level(
    tmp_path: Path, both_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-15: if both auto and skip are True at the helper, skip wins."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=True, skip=True)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    events = _gitignore_events(logs)
    assert any(
        e["event"] == "gitignore.append.skipped" and e["reason"] == "never_flag" for e in events
    )


def test_conflicting_cli_flags_raise_usage_error() -> None:
    """AC-15: CLI rejects --auto-gitignore + --no-gitignore before helper invocation."""
    from click.testing import CliRunner

    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["--auto-gitignore", "--no-gitignore", "gather", "."])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


@pytest.mark.parametrize("failure_point", ["open", "write", "fsync", "replace"])
def test_append_failure_at_each_step_cleans_up_tmp(
    tmp_path: Path,
    both_tty: None,
    confirm_spy: _ConfirmSpy,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    """AC-16: every step on the write path must clean up tmp on OSError and not raise."""
    initial = b"node_modules/\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    import codegenie.output.gitignore as g

    if failure_point == "open":
        real_open = Path.open

        def _bad_open(self: Path, *a: Any, **kw: Any) -> Any:
            if self.name == ".gitignore.tmp":
                raise OSError("simulated open failure")
            return real_open(self, *a, **kw)

        monkeypatch.setattr(Path, "open", _bad_open)
    elif failure_point == "write":
        real_open = Path.open

        class _BadFile:
            def __init__(self, f: Any) -> None:
                self._f = f

            def __enter__(self) -> _BadFile:
                self._f.__enter__()
                return self

            def __exit__(self, *a: Any) -> None:
                self._f.__exit__(*a)

            def write(self, _data: bytes) -> int:
                raise OSError("simulated write failure")

            def flush(self) -> None:
                pass

            def fileno(self) -> int:
                fileno: int = self._f.fileno()
                return fileno

        def _wrap_open(self: Path, *a: Any, **kw: Any) -> Any:
            f = real_open(self, *a, **kw)
            if self.name == ".gitignore.tmp":
                return _BadFile(f)
            return f

        monkeypatch.setattr(Path, "open", _wrap_open)
    elif failure_point == "fsync":

        def _bad_fsync(_fd: int) -> None:
            raise OSError("simulated fsync failure")

        monkeypatch.setattr(g.os, "fsync", _bad_fsync)
    elif failure_point == "replace":

        def _bad_replace(*_a: Any, **_kw: Any) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(g.os, "replace", _bad_replace)

    with structlog.testing.capture_logs() as logs:
        _load()(tmp_path, auto=True, skip=False)  # must NOT raise
    assert (tmp_path / ".gitignore").read_bytes() == initial, "original file must be byte-identical"
    assert not (tmp_path / ".gitignore.tmp").exists(), f"tmp left behind on {failure_point}"
    events = _gitignore_events(logs)
    failed = [e for e in events if e["event"] == "gitignore.append.failed"]
    assert len(failed) == 1
    assert failed[0]["log_level"] == "warning"
    assert failed[0]["exc_class"] == "OSError"


def test_keyboard_interrupt_propagates(
    tmp_path: Path,
    both_tty: None,
    confirm_spy: _ConfirmSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-17: only OSError is swallowed; KeyboardInterrupt must escape."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    import codegenie.output.gitignore as g

    def _bad_replace(*_a: Any, **_kw: Any) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(g.os, "replace", _bad_replace)
    with pytest.raises(KeyboardInterrupt):
        _load()(tmp_path, auto=True, skip=False)


# ---------- Metamorphic / permissions ----------


def test_call_twice_is_metamorphic_noop(
    tmp_path: Path, no_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-19: f(f(x)) == f(x). Second call must not rewrite — mtime is the strict pin."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=True, skip=False)
    content_after_first = (tmp_path / ".gitignore").read_bytes()
    mtime_after_first = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == content_after_first
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == mtime_after_first


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only — Windows is advisory")
def test_created_gitignore_uses_platform_default_mode(
    tmp_path: Path, no_tty: None, confirm_spy: _ConfirmSpy
) -> None:
    """AC-20: per ADR-0011, the analyzed repo's .gitignore must NOT inherit 0o600."""
    _load()(tmp_path, auto=True, skip=False)
    mode = (tmp_path / ".gitignore").stat().st_mode & 0o777
    assert mode != 0o600, "ADR-0011: analyzed .gitignore must NOT inherit .codegenie/ 0600 mode"


def test_logging_constants_exist() -> None:
    """AC-21: logging.py exports the five gitignore.append.* event-name constants."""
    import codegenie.logging as cgl

    assert cgl.GITIGNORE_APPEND_ACCEPTED == "gitignore.append.accepted"
    assert cgl.GITIGNORE_APPEND_DECLINED == "gitignore.append.declined"
    assert cgl.GITIGNORE_APPEND_SKIPPED == "gitignore.append.skipped"
    assert cgl.GITIGNORE_APPEND_IDEMPOTENT == "gitignore.append.idempotent"
    assert cgl.GITIGNORE_APPEND_FAILED == "gitignore.append.failed"
