"""Process-wide tool-version resolver (S4-03 AC-19).

Several Phase-2 probes need the resolved version of an external CLI to roll
into ``probe.version`` (the cache-key tuple at
``src/codegenie/cache/keys.py:146``). Without a shared memo, every probe
would (a) re-spawn the subprocess at every cache-key derivation and (b)
copy-paste the same try/except/parse code, which crosses the rule-of-three
at the Phase-2 boundary (``scip-typescript``, ``tree-sitter``, plus the
Layer-G ``grype`` / ``syft`` / ``semgrep`` / ``gitleaks`` family).

This module is a *kernel*: one function, one synchronous result, one
process-wide memo keyed by ``(binary, argv-tuple)``. The memo lives at
module scope (not on a class) for the same reason ``codegenie.indices.registry``
uses a module-level singleton — there is exactly one process-wide resolved
version per ``(binary, argv-tuple)`` pair, and that singleton is the
auditable surface.

Three discipline points the design pins:

1. **Lazy.** The first call triggers the subprocess; subsequent calls are
   in-memory dict lookups. The subprocess must NOT fire at import time —
   import-time subprocess is an anti-pattern (S4-03 validation report
   F-DP-2) that turns ``pytest`` collection into a tool-availability test.
2. **Tool-missing safe.** ``ToolMissingError`` returns ``"unknown"`` rather
   than raising. The probe's ``version`` ``@property`` reads this and must
   stay safe even on a machine where the binary is uninstalled — otherwise
   the cache-key derivation itself would crash, taking down probes that
   never wanted to invoke the missing tool.
3. **Test seam.** :func:`clear_for_tests` mirrors S1-02's
   ``unregister_for_tests`` precedent — the deliberately-awkward name *is*
   the policy: production code paths never clear the memo.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-03-scip-index-probe.md``
  AC-19, AC-2, T-20.
- ``docs/phases/02-context-gather-layers-b-g/stories/_validation/S4-03-scip-index-probe.md``
  §"Design-patterns critic" DP-2 (kernel-extract over rule-of-three).
- ``src/codegenie/indices/registry.py`` — singleton + ``unregister_for_tests``
  precedent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import structlog

from codegenie.errors import ToolMissingError
from codegenie.exec import ProcessResult, run_external_cli
from codegenie.types.identifiers import ProbeId

__all__ = ["clear_for_tests", "resolve_tool_version"]


_log = structlog.get_logger(__name__)


_MEMO: dict[tuple[str, tuple[str, ...]], str] = {}
# Probe-id under which the resolver invokes ``run_external_cli``. The
# resolver is the caller, not a probe; the ``ProbeId`` is required by the
# port's signature and is recorded as the structured-log ``probe_name`` for
# subprocess events.
_RESOLVER_PROBE_ID: ProbeId = ProbeId("tool_versions")


def _default_parser(stdout: bytes) -> str:
    """Default version parser: first non-empty line, UTF-8 decoded, trimmed.

    Tolerates BOM, leading whitespace, and Windows line endings. The first
    non-empty line of ``--version`` output is the convention every external
    CLI in the Phase 2 allowlist follows (``scip-typescript 0.3.21`` /
    ``tree-sitter 0.20.6`` / ``grype 0.74.0`` …).
    """
    decoded = stdout.decode("utf-8", errors="replace").strip()
    if not decoded:
        return "unknown"
    return decoded.splitlines()[0].strip()


async def resolve_tool_version(
    binary: str,
    *,
    version_argv: list[str] | None = None,
    parser: Callable[[bytes], str] | None = None,
) -> str:
    """Return the resolved version of *binary*, memoized process-wide.

    The first call invokes :func:`codegenie.exec.run_external_cli` with
    ``[<binary>, ...version_argv]`` and a 5 s timeout; subsequent calls
    return the cached result without spawning a subprocess. On
    :class:`ToolMissingError` the result is ``"unknown"`` (the memo records
    that too — a missing tool stays missing for the life of the process).

    Args:
        binary: The CLI name (must be in :data:`ALLOWED_BINARIES`).
        version_argv: Arguments after the binary; default ``["--version"]``.
        parser: ``stdout -> str`` decoder; default first non-empty line.

    Returns:
        The version string (or ``"unknown"`` on tool-missing /
        non-zero-exit). Never raises on the tool-missing path — callers
        compose this into ``probe.version`` which must stay safe.
    """
    argv_tuple = tuple(version_argv) if version_argv is not None else ("--version",)
    key = (binary, argv_tuple)
    cached = _MEMO.get(key)
    if cached is not None:
        return cached

    try:
        result: ProcessResult = await run_external_cli(
            _RESOLVER_PROBE_ID,
            [binary, *argv_tuple],
            cwd=Path.cwd(),
            timeout_s=5,
        )
    except ToolMissingError:
        _MEMO[key] = "unknown"
        _log.debug("tool_versions.missing", binary=binary)
        return "unknown"

    if result.returncode != 0:
        _MEMO[key] = "unknown"
        _log.debug("tool_versions.nonzero_exit", binary=binary, returncode=result.returncode)
        return "unknown"

    parse = parser or _default_parser
    version = parse(result.stdout)
    _MEMO[key] = version
    _log.debug("tool_versions.resolved", binary=binary, version=version)
    return version


def resolve_tool_version_sync(
    binary: str,
    *,
    version_argv: list[str] | None = None,
    parser: Callable[[bytes], str] | None = None,
) -> str:
    """Synchronous wrapper around :func:`resolve_tool_version`.

    Used by probe ``version`` ``@property`` blocks, which cannot be ``async``.
    The first invocation per ``(binary, argv)`` pair pays the subprocess
    cost; subsequent reads are pure in-memory lookups (the memo dominates).

    Two cases the wrapper handles:

    - **No running loop** (typical case — ``probe.version`` is read from
      synchronous code paths like ``cache_key`` derivation): we spin up a
      one-shot loop via :func:`asyncio.run`.
    - **A running loop** (unit tests that drive the probe inside
      ``pytest-asyncio``): :func:`asyncio.run` would refuse with
      ``RuntimeError``. The memo short-circuit (above) catches the common
      case where the test has primed the cache via ``clear_for_tests()``
      + an explicit ``await resolve_tool_version(...)`` before reading
      ``probe.version``. If the cache is cold and a loop is running, we
      surface ``"unknown"`` rather than blocking the loop — the contract
      is "safe to read"; cache-miss in the running-loop case is degraded
      output, never a hang.
    """
    argv_tuple = tuple(version_argv) if version_argv is not None else ("--version",)
    cached = _MEMO.get((binary, argv_tuple))
    if cached is not None:
        return cached

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(resolve_tool_version(binary, version_argv=version_argv, parser=parser))
    # A loop is running — cannot block on asyncio.run; degrade to "unknown".
    # Test fixtures prime the cache with an explicit ``await
    # resolve_tool_version(...)`` before constructing the probe.
    return "unknown"


def clear_for_tests() -> None:
    """**Test-only** convenience that resets the process-wide memo.

    The deliberately-awkward name *is* the policy — production code paths
    do not clear the cache. Two unit tests in
    ``tests/unit/exec/test_tool_versions.py`` call this in a ``finally:``
    block so the cache state from one test does not pollute the next.
    Mirrors :func:`codegenie.indices.registry.FreshnessRegistry.unregister_for_tests`.
    """
    _MEMO.clear()
