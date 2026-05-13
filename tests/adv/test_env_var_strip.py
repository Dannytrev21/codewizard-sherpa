"""Adversarial: sensitive env vars never reach a subprocess via ``run_allowlisted``.

The chokepoint in ``codegenie.exec`` has TWO attack surfaces:

1. The **parent-env path** — invariant *by construction*. The wrapper builds
   the child env by inclusion of ``{PATH, HOME, LANG, LC_ALL}`` only and
   never copies ``os.environ`` (see ``exec.py:14-18``, ``_filter_env``).
2. The **env_extra path** — the only mutation-relevant surface. A future
   regression that loosens ``_is_sensitive`` (or removes the
   ``if _is_sensitive(key): continue`` branch at ``exec.py:142``) would let
   secrets through. This is the surface the test is designed to catch.

Both surfaces are pinned. ``asyncio.create_subprocess_exec`` is patched via
``monkeypatch.setattr`` so the test observes what the chokepoint *would
have* passed to the kernel without actually spawning a child — mirrors the
spy idiom in ``tests/unit/test_exec.py``.

Traces to:
- ADR-0012 §Decision — six chokepoint invariants in one place.
- ``phase-arch-design.md §Agentic best practices — Tool-use safety``.
- ``exec.py:111-148`` — ``_is_sensitive`` + ``_filter_env``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from structlog.testing import capture_logs


def _make_fake_create() -> tuple[dict[str, Any], Any]:
    """Build a spy that captures the ``env=`` kwarg and short-circuits the spawn.

    Returns ``(captured, fake_create)``. ``captured["env"]`` holds the dict
    the wrapper would have passed to ``create_subprocess_exec``.
    """
    captured: dict[str, Any] = {}

    async def fake_create(*args: Any, **kwargs: Any) -> mock.AsyncMock:
        captured["env"] = kwargs.get("env", {})
        captured["argv"] = args
        proc = mock.AsyncMock()
        proc.communicate = mock.AsyncMock(return_value=(b"", b""))
        proc.returncode = 0
        proc.pid = 99999
        return proc

    return captured, fake_create


async def test_parent_env_built_by_omission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Pins: the child env is built by INCLUSION of ``{PATH, HOME, LANG, LC_ALL}``
          — NOT by deletion from ``os.environ``. Sensitive vars in the parent
          environment are structurally absent.
    Traces to: ADR-0012 §Decision (six invariants); ``exec.py:14-18`` ("built
          by omission, not by deletion").
    Catches: a regression that switched to ``env = {**os.environ}; env.pop(k)
             for k in SENSITIVE`` — that would leak any env var not in the
             ``SENSITIVE`` allowlist (e.g. an internal ``ROGUE_TOKEN`` someone
             forgot to enumerate). The closed-world ``set(env.keys()) == ...``
             assertion fails under that mutation.
    """
    from codegenie import exec as cg_exec

    for v in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
        "GITHUB_TOKEN",
        "ROGUE_TOKEN",
    ):
        monkeypatch.setenv(v, "secret-must-not-leak")

    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await cg_exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=tmp_path, timeout_s=10)

    env = captured["env"]
    # Closed-world: child env has ONLY the four-key baseline (no env_extra here).
    assert set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}, (
        f"env should be exactly the build-by-omission baseline; got {set(env.keys())!r}"
    )
    # Redundant-but-clear: each sensitive var name is absent.
    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
        "GITHUB_TOKEN",
        "ROGUE_TOKEN",
    ):
        assert var not in env, f"{var} leaked into subprocess env"


async def test_env_extra_sensitive_keys_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Pins: caller-supplied ``env_extra`` is sanitized — sensitive keys are
          silently dropped (and logged) while legitimate keys pass through.
    Traces to: ADR-0012 §Decision; ``exec.py:111-148`` (``_is_sensitive`` +
          ``_filter_env``).
    Catches: a regression that removed ``_is_sensitive`` or its caller — the
             only plausible regression surface for env-stripping, because
             the parent-env path is structural. The
             ``subproc.env_extra.sensitive_key_dropped`` event-emitted-N-times
             assertion adds a positive signal that the chokepoint ran.
    """
    from codegenie import exec as cg_exec

    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    with capture_logs() as logs:
        await cg_exec.run_allowlisted(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            timeout_s=10,
            env_extra={
                "OPENAI_API_KEY": "leak",
                "ANTHROPIC_API_KEY": "leak",
                "AWS_SECRET_ACCESS_KEY": "leak",
                "SSH_AUTH_SOCK": "leak",
                "GITHUB_TOKEN": "leak",
                "MY_LEGIT_VAR": "kept",
            },
        )

    env = captured["env"]

    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
        "GITHUB_TOKEN",
    ):
        assert var not in env, f"{var} smuggled into the subprocess env via env_extra"

    assert env.get("MY_LEGIT_VAR") == "kept", (
        "legitimate env_extra key did not pass through — _is_sensitive over-matched"
    )

    drops = [e for e in logs if e.get("event") == "subproc.env_extra.sensitive_key_dropped"]
    assert len(drops) == 5, (
        f"expected exactly 5 drop events (one per sensitive key); got {len(drops)}: {drops!r}"
    )


async def test_env_extra_case_insensitivity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Pins: ``_is_sensitive`` normalizes the key via ``.upper()`` —
          lowercase/mixed-case variants of sensitive keys are also dropped.
          AWS_ prefix-matching is also case-insensitive.
    Traces to: ADR-0012; ``exec.py:117`` (``upper = key.upper()``).
    Catches: a regression that removed the ``.upper()`` normalization —
             lowercase variants would slip through ``_SENSITIVE_EXACT`` and
             the assertion below would fail.
    """
    from codegenie import exec as cg_exec

    captured, fake_create = _make_fake_create()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await cg_exec.run_allowlisted(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        timeout_s=10,
        env_extra={
            "openai_api_key": "leak",
            "aws_secret_access_key": "leak",
        },
    )

    env = captured["env"]
    assert "openai_api_key" not in env
    assert "OPENAI_API_KEY" not in env
    assert "aws_secret_access_key" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
