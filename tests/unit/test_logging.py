"""Pins the :mod:`codegenie.logging` public surface and runtime behavior (S2-01).

Sources:
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Harness
  engineering — JSON on non-TTY, pretty on TTY, six ``probe.*`` event names.
- ``docs/phases/00-bullet-tracer-foundations/final-design.md`` §2.14 — same six
  lifecycle event names.
"""

from __future__ import annotations

import inspect
import json
import sys

import pytest
import structlog

import codegenie.logging as cgl

EXPECTED_EVENT_NAMES = {
    "EVENT_PROBE_START": "probe.start",
    "EVENT_PROBE_CACHE_HIT": "probe.cache_hit",
    "EVENT_PROBE_SKIP": "probe.skip",
    "EVENT_PROBE_SUCCESS": "probe.success",
    "EVENT_PROBE_FAILURE": "probe.failure",
    "EVENT_PROBE_TIMEOUT": "probe.timeout",
}

# S4-03: `.gitignore` mutation routine event-name family. Kept in a
# separate dict (not `EVENT_PROBE_*`) so closure assertions stay scoped
# to the `probe.*` family unchanged.
EXPECTED_GITIGNORE_EVENT_NAMES = {
    "GITIGNORE_APPEND_ACCEPTED": "gitignore.append.accepted",
    "GITIGNORE_APPEND_DECLINED": "gitignore.append.declined",
    "GITIGNORE_APPEND_SKIPPED": "gitignore.append.skipped",
    "GITIGNORE_APPEND_IDEMPOTENT": "gitignore.append.idempotent",
    "GITIGNORE_APPEND_FAILED": "gitignore.append.failed",
}


@pytest.fixture(autouse=True)
def _reset_structlog() -> object:
    # structlog.configure mutates process-global state; without this fixture,
    # one test's renderer leaks into the next and either direction of leakage
    # can hide a wrong implementation.
    yield
    structlog.reset_defaults()


def test_event_name_constants_are_plain_strs_with_documented_values() -> None:
    # `type(...) is str` rejects StrEnum members (whose type is the enum class).
    # The implementer-note bans StrEnum; this test makes the ban load-bearing.
    for name, expected_value in EXPECTED_EVENT_NAMES.items():
        value = getattr(cgl, name)
        assert type(value) is str, (
            f"{name} must be a plain str, not a {type(value).__name__} "
            f"(StrEnum members compare equal to strings but break "
            f"`isinstance(x, str) and type(x) is str` subscribers)"
        )
        assert value == expected_value


def test_event_name_constant_closure() -> None:
    discovered = {n for n in dir(cgl) if n.startswith("EVENT_PROBE_")}
    assert discovered == set(EXPECTED_EVENT_NAMES), (
        f"event-name closure drift: expected {set(EXPECTED_EVENT_NAMES)}, "
        f"got {discovered}; add an ADR amendment before extending"
    )


def test_logging_module_all_closure() -> None:
    assert set(cgl.__all__) == {
        "configure_logging",
        *EXPECTED_EVENT_NAMES,
        *EXPECTED_GITIGNORE_EVENT_NAMES,
    }


def test_gitignore_event_name_constants_are_plain_strs_with_documented_values() -> None:
    """S4-03 AC-21: five GITIGNORE_APPEND_* constants pinned by value."""
    for name, expected_value in EXPECTED_GITIGNORE_EVENT_NAMES.items():
        value = getattr(cgl, name)
        assert type(value) is str, (
            f"{name} must be a plain str, not {type(value).__name__}; "
            "the str-identity ban applies to the gitignore family too"
        )
        assert value == expected_value


def test_gitignore_event_name_constant_closure() -> None:
    """Closure pin — adding a GITIGNORE_APPEND_* constant requires an ADR amendment."""
    discovered = {n for n in dir(cgl) if n.startswith("GITIGNORE_APPEND_")}
    assert discovered == set(EXPECTED_GITIGNORE_EVENT_NAMES), (
        f"gitignore.append.* closure drift: expected {set(EXPECTED_GITIGNORE_EVENT_NAMES)}, "
        f"got {discovered}"
    )


def test_configure_logging_signature_default_is_false() -> None:
    sig = inspect.signature(cgl.configure_logging)
    assert sig.parameters["verbose"].default is False


def test_configure_logging_json_on_non_tty_every_line_parses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().info("probe.start", probe="lang", run_id="abc")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "configure_logging must emit on non-TTY"
    for line in non_empty_lines:
        json.loads(line)  # every line must parse — no stray pretty output
    last = json.loads(non_empty_lines[-1])
    assert last["event"] == "probe.start"
    assert last["probe"] == "lang"


def test_configure_logging_pretty_on_tty_is_not_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().info("probe.start", probe="lang")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "configure_logging must emit on TTY"
    # At least one captured line must not parse as JSON (pretty/console renderer).
    non_json = []
    for line in non_empty_lines:
        try:
            json.loads(line)
        except json.JSONDecodeError:
            non_json.append(line)
    assert non_json, f"expected pretty (non-JSON) output on TTY; got {non_empty_lines!r}"
    assert any("probe.start" in line for line in non_json)


def test_verbose_true_enables_debug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=True)
    structlog.get_logger().debug("debug.event", k=1)
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "verbose=True must emit DEBUG-level events"
    payload = json.loads(non_empty_lines[-1])
    assert payload["event"] == "debug.event"
    assert payload["k"] == 1


def test_verbose_false_silences_debug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().debug("debug.event")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert not non_empty_lines, (
        f"verbose=False must filter out DEBUG-level events; got {non_empty_lines!r}"
    )


def test_configure_logging_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-7: structlog.configure mutates process-global state; double-config
    # under the same args must produce identical final config (no duplicated
    # processors, no nested wrapper-class chain).
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    snapshot_a = structlog.get_config()
    cgl.configure_logging(verbose=False)
    snapshot_b = structlog.get_config()
    assert snapshot_a == snapshot_b, (
        "configure_logging(verbose=False) called twice must converge to the same config"
    )


def test_configure_logging_reapplies_cleanly_on_verbose_change(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # AC-7: switching verbose flips the bound-logger level cleanly — no leftover
    # INFO filter that would silence DEBUG after re-config.
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    cgl.configure_logging(verbose=True)
    structlog.get_logger().debug("after.reconfig")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "re-configuring with verbose=True after verbose=False must enable DEBUG"
    assert json.loads(non_empty_lines[-1])["event"] == "after.reconfig"
