"""Adversarial: a planted ``node`` shim on ``$PATH`` cannot leak secrets.

The story being pinned is *not* that ``node`` cannot be hijacked — under
ADR-0001 + ADR-0008, the env-strip carries the load-bearing weight, not
a binary-signature check. The chokepoint at
:func:`codegenie.exec.run_allowlisted` builds the child env by inclusion
of ``{PATH, HOME, LANG, LC_ALL}`` plus a sanitized ``env_extra``; the
parent process's ``os.environ`` is **never copied**.

Two distinct env-leak surfaces are exercised:

1. **Parent-env inclusion** (AC-6) — sensitive vars set on the parent
   via ``monkeypatch.setenv`` (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``,
   ``GITHUB_TOKEN``, ``AWS_*``, ``SSH_AUTH_SOCK``) are structurally absent
   from the child because ``_filter_env`` never copies them. Catches a
   refactor that drops ``env=env`` from ``create_subprocess_exec``.
2. **env_extra denylist** (AC-7, AC-8) — sensitive sentinels passed
   *through* ``env_extra`` are filtered by ``_is_sensitive``
   (``exec.py:112-121``) and the structlog event
   ``subproc.env_extra.sensitive_key_dropped`` fires once per sensitive
   key. Catches a regression that removes the
   ``if _is_sensitive(key): continue`` branch at ``exec.py:142-148``.

Both surfaces share one positive control: ``MY_LEGIT_VAR=passes-through``
proves the chokepoint did not over-filter, and a trailing
``node-shim-invoked`` marker line in the sentinel file proves the shim
actually ran (test is not vacuously green).

``SENTINEL_FILE`` is the test's own out-of-band channel and is passed
through ``env_extra`` — **not** ``monkeypatch.setenv``. The 4-key
baseline does not include ``SENTINEL_FILE`` so the parent-env-strip
would otherwise make the shim's redirect write to nowhere usable.

Traces to:
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Adversarial tests" item #7.
- ``docs/phases/01-context-gather-layer-a-node/final-design.md``
  §"Adversarial tests" — "env-strip carries the load-bearing weight".
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md``
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
- ``exec.py:112-150`` — ``_is_sensitive`` + ``_filter_env``.
- Mirrors the spy-at-the-chokepoint pattern in
  ``tests/adv/test_env_var_strip.py`` (S4-05), but spawns the real shim
  here so the child env's runtime view is the surface under test.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from structlog.testing import capture_logs

SHIM_BODY = """#!/bin/sh
{
  printf 'OPENAI_API_KEY=%s\\n' "${OPENAI_API_KEY:-}"
  printf 'ANTHROPIC_API_KEY=%s\\n' "${ANTHROPIC_API_KEY:-}"
  printf 'GITHUB_TOKEN=%s\\n' "${GITHUB_TOKEN:-}"
  printf 'AWS_ACCESS_KEY_ID=%s\\n' "${AWS_ACCESS_KEY_ID:-}"
  printf 'AWS_SECRET_ACCESS_KEY=%s\\n' "${AWS_SECRET_ACCESS_KEY:-}"
  printf 'SSH_AUTH_SOCK=%s\\n' "${SSH_AUTH_SOCK:-}"
  printf 'MY_LEGIT_VAR=%s\\n' "${MY_LEGIT_VAR:-}"
  printf 'node-shim-invoked\\n'
} > "$SENTINEL_FILE"
echo v20.0.0
"""

_PARENT_LEAK_CANARY = "PARENT_LEAK_CANARY"
_EXTRA_CANARY_PREFIX = "EXTRA_LEAK_CANARY_"


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")
async def test_planted_node_shim_runs_in_stripped_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins AC-4 through AC-8.

    Catches:
      - a refactor swapping the spawn primitive to one that ignores the
        explicit ``env=`` kwarg (parent ``os.environ`` would leak); the
        parent-canary assertion fails.
      - a regression deleting the ``if _is_sensitive(key): continue``
        branch; ``EXTRA_LEAK_CANARY_*`` would appear in the shim sentinel
        for the four sensitive keys.
      - a regression deleting the structlog
        ``subproc.env_extra.sensitive_key_dropped`` event; the four-events
        assertion fails.
      - a regression over-filtering ``env_extra`` (e.g. dropping unknown
        keys); ``MY_LEGIT_VAR=passes-through`` would be empty in the
        sentinel.
    """
    from codegenie import exec as cg_exec

    shim_dir = tmp_path / "fake-bin"
    shim_dir.mkdir()
    shim = shim_dir / "node"
    shim.write_text(SHIM_BODY)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    sentinel = tmp_path / "sentinel.txt"

    # AC-6 — parent-env canaries. NEVER copied to the child by design
    # (env-by-inclusion at exec.py:124-150).
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
    ):
        monkeypatch.setenv(key, _PARENT_LEAK_CANARY)

    env_extra = {
        # PATH override + sentinel channel — non-sensitive, pass through.
        "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
        "SENTINEL_FILE": str(sentinel),
        "MY_LEGIT_VAR": "passes-through",
        # AC-7 — sensitive sentinels; must be dropped by ``_is_sensitive``.
        "OPENAI_API_KEY": f"{_EXTRA_CANARY_PREFIX}OPENAI",
        "ANTHROPIC_API_KEY": f"{_EXTRA_CANARY_PREFIX}ANTHROPIC",
        "AWS_SECRET_ACCESS_KEY": f"{_EXTRA_CANARY_PREFIX}AWS",  # AWS_ prefix path
        "GITHUB_TOKEN": f"{_EXTRA_CANARY_PREFIX}GH",
    }

    with capture_logs() as logs:
        result = await cg_exec.run_allowlisted(
            ["node", "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra=env_extra,
        )

    # AC-5 — the shim actually ran (positive control; test is not vacuously green).
    body = sentinel.read_text()
    lines = body.splitlines()
    assert lines and lines[-1] == "node-shim-invoked", (
        f"shim did not write the trailing marker — sentinel body was {body!r}"
    )
    parsed: dict[str, str] = dict(line.split("=", 1) for line in lines if "=" in line)

    # AC-6 — parent ``os.environ`` was never copied; each sensitive var is empty.
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
    ):
        assert parsed.get(key, "<missing>") != _PARENT_LEAK_CANARY, (
            f"parent-env leak: {key} reached child as {parsed.get(key, '<missing>')!r}"
        )
    assert _PARENT_LEAK_CANARY not in body, (
        f"PARENT_LEAK_CANARY appears somewhere in shim output: {body!r}"
    )

    # AC-7 — ``_is_sensitive`` filtered the env_extra sensitives.
    assert _EXTRA_CANARY_PREFIX not in body, f"sensitive env_extra reached the child: {body!r}"
    # Positive control — legitimate env_extra var DID pass through.
    assert parsed.get("MY_LEGIT_VAR") == "passes-through", (
        f"MY_LEGIT_VAR was dropped; chokepoint over-filtered: {parsed!r}"
    )

    # AC-8 — structlog event observability for the denylist path.
    drops = [e for e in logs if e.get("event") == "subproc.env_extra.sensitive_key_dropped"]
    assert len(drops) == 4, (
        f"expected exactly 4 sensitive_key_dropped events; got {len(drops)}: {drops!r}"
    )
    assert {e["key"] for e in drops} == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    }, drops

    # Sanity — the shim returned 0 and stdout looked like a version.
    assert result.returncode == 0, result
    assert result.stdout.strip() == b"v20.0.0"
