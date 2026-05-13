"""Build the initial :class:`RepoSnapshot` the coordinator dispatches against.

S3-05 AC-1 pins this surface: ``build_snapshot(repo_root, config)`` calls
``git rev-parse HEAD`` via the allowlisted-subprocess wrapper
(:func:`codegenie.exec.run_allowlisted`) with a tight 10 s timeout. Any of
the four documented failure modes — ``DisallowedSubprocessError``,
``ToolMissingError``, ``ProbeTimeoutError``, or a non-zero ``git`` return
code — silently degrades to ``git_commit=None`` rather than raising. The
fall-through is what makes ``codegenie gather`` work in a freshly initialized
directory or a partially broken checkout.

``repo_root`` is resolved up-front via ``Path.resolve()`` so downstream
consumers (notably :func:`codegenie.output.sanitizer.OutputSanitizer.scrub`)
can rely on ``snapshot.root`` being absolute (S3-03 AC-12).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from codegenie.config.defaults import Config
from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import run_allowlisted
from codegenie.probes.base import RepoSnapshot

__all__ = ["build_snapshot"]

_log = structlog.get_logger(__name__)
_GIT_REV_PARSE_TIMEOUT_S: float = 10.0


def build_snapshot(repo_root: Path, config: Config) -> RepoSnapshot:
    """Construct a :class:`RepoSnapshot` for ``repo_root``.

    Resolves ``repo_root`` first so ``snapshot.root`` is absolute. The
    ``git rev-parse HEAD`` lookup is best-effort: any failure (binary
    missing, timeout, non-zero exit, etc.) yields ``git_commit=None``.

    ``detected_languages`` starts empty; the coordinator's prelude pass
    enriches it after :class:`LanguageDetectionProbe` runs (S4-01).
    """
    resolved = repo_root.resolve()
    git_commit = _resolve_git_commit(resolved)
    return RepoSnapshot(
        root=resolved,
        git_commit=git_commit,
        detected_languages={},
        config=_config_to_dict(config),
    )


def _resolve_git_commit(repo_root: Path) -> str | None:
    """Best-effort ``git rev-parse HEAD`` resolution. Any failure → ``None``."""
    try:
        return asyncio.run(_run_git_rev_parse(repo_root))
    except (
        DisallowedSubprocessError,
        ToolMissingError,
        ProbeTimeoutError,
        FileNotFoundError,
        NotADirectoryError,
    ) as exc:
        _log.info("snapshot.git_rev_parse.failed", reason=type(exc).__name__)
        return None
    except RuntimeError:
        # ``asyncio.run`` rejects calls from inside a running event loop. The
        # only Phase 0 caller is the synchronous CLI entry point, but tests
        # may call ``build_snapshot`` from a pytest-asyncio test; in that case
        # we fall back to None rather than blowing up the test runner.
        return None


async def _run_git_rev_parse(repo_root: Path) -> str | None:
    try:
        result = await run_allowlisted(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            timeout_s=_GIT_REV_PARSE_TIMEOUT_S,
        )
    except (DisallowedSubprocessError, ToolMissingError, ProbeTimeoutError) as exc:
        _log.info("snapshot.git_rev_parse.failed", reason=type(exc).__name__)
        return None
    if result.returncode != 0:
        _log.info("snapshot.git_rev_parse.non_zero", returncode=result.returncode)
        return None
    return result.stdout.decode("utf-8", errors="replace").strip() or None


def _config_to_dict(config: Config) -> dict[str, object]:
    """Render a frozen :class:`Config` as the plain ``dict`` ``RepoSnapshot``
    carries."""
    return {
        "max_concurrent_probes": config.max_concurrent_probes,
        "cache_ttl_hours": config.cache_ttl_hours,
        "enable_audit": config.enable_audit,
    }
