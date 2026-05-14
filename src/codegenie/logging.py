"""structlog configuration + lifecycle event-name constants.

Sources:

- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Harness
  engineering — JSON on non-TTY, pretty on TTY, the six ``probe.*`` event
  names are contract for Phase 6's state ledger and Phase 13's cost ledger.
- ``docs/phases/00-bullet-tracer-foundations/final-design.md`` §2.14 — same
  six lifecycle event names.

The event-name constants are plain :class:`str` values (not ``StrEnum``)
because Phase 13's cost ledger destructures via ``type(x) is str``. The ban
is load-bearing — see AC-5 in the story.

``configure_logging`` is idempotent and re-entrant: calling it twice with the
same ``verbose`` value produces an equal :func:`structlog.get_config` mapping;
calling it with a different ``verbose`` cleanly re-applies the filtering
bound logger. We achieve this by caching the configuration objects per
``(stderr-identity, is_tty, verbose)`` triple so :func:`structlog.configure`
receives the same instances on repeat calls.
"""

from __future__ import annotations

import logging as _stdlib_logging
import sys
from typing import Any, Final

import structlog

EVENT_PROBE_START: Final[str] = "probe.start"
EVENT_PROBE_CACHE_HIT: Final[str] = "probe.cache_hit"
EVENT_PROBE_SKIP: Final[str] = "probe.skip"
EVENT_PROBE_SUCCESS: Final[str] = "probe.success"
EVENT_PROBE_FAILURE: Final[str] = "probe.failure"
EVENT_PROBE_TIMEOUT: Final[str] = "probe.timeout"

# S4-03: `.gitignore` mutation routine event names. Phase-arch §Edge case #8
# ("append failure → warn + continue") + final-design §2.15 (TTY policy)
# are the source of truth; the helper imports these constants so the names
# stay rename-resistant.
GITIGNORE_APPEND_ACCEPTED: Final[str] = "gitignore.append.accepted"
GITIGNORE_APPEND_DECLINED: Final[str] = "gitignore.append.declined"
GITIGNORE_APPEND_SKIPPED: Final[str] = "gitignore.append.skipped"
GITIGNORE_APPEND_IDEMPOTENT: Final[str] = "gitignore.append.idempotent"
GITIGNORE_APPEND_FAILED: Final[str] = "gitignore.append.failed"

# S1-10: Phase-1 lifecycle event names. Previously scattered as module-local
# ``_EVENT_*: Final[str]`` definitions across three parser modules and two raw
# literals in ``parsed_manifest_memo``. Centralizing here makes the event-name
# vocabulary a single-source-of-truth registry (Open/Closed at the file
# boundary). The structural guard against literal drift is
# ``tests/unit/test_no_event_literal_drift.py``.
EVENT_PROBE_PARSER_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"
EVENT_PROBE_MEMO_HIT: Final[str] = "probe.memo.hit"
EVENT_PROBE_MEMO_MISS: Final[str] = "probe.memo.miss"
EVENT_PROBE_CATALOG_LOAD: Final[str] = "probe.catalog.load"
EVENT_PROBE_RAW_ARTIFACT_TRUNCATED: Final[str] = "probe.raw_artifact.truncated"

__all__ = [
    "EVENT_PROBE_CACHE_HIT",
    "EVENT_PROBE_CATALOG_LOAD",
    "EVENT_PROBE_FAILURE",
    "EVENT_PROBE_MEMO_HIT",
    "EVENT_PROBE_MEMO_MISS",
    "EVENT_PROBE_PARSER_CAP_EXCEEDED",
    "EVENT_PROBE_RAW_ARTIFACT_TRUNCATED",
    "EVENT_PROBE_SKIP",
    "EVENT_PROBE_START",
    "EVENT_PROBE_SUCCESS",
    "EVENT_PROBE_TIMEOUT",
    "GITIGNORE_APPEND_ACCEPTED",
    "GITIGNORE_APPEND_DECLINED",
    "GITIGNORE_APPEND_FAILED",
    "GITIGNORE_APPEND_IDEMPOTENT",
    "GITIGNORE_APPEND_SKIPPED",
    "configure_logging",
]

# Cache the configure(**kwargs) payload per (id(stderr), is_tty, verbose).
# Repeat calls with the same triple replay the same object instances into
# ``structlog.configure`` so ``structlog.get_config()`` returns equal
# mappings on every call (AC-7).
_config_cache: dict[tuple[int, bool, bool], dict[str, Any]] = {}


def _build_config(verbose: bool) -> dict[str, Any]:
    is_tty = sys.stderr.isatty()
    key = (id(sys.stderr), is_tty, verbose)
    cached = _config_cache.get(key)
    if cached is not None:
        return cached
    renderer: Any
    if is_tty:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()
    processors: list[Any] = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        renderer,
    ]
    wrapper_class = structlog.make_filtering_bound_logger(
        _stdlib_logging.DEBUG if verbose else _stdlib_logging.INFO
    )
    logger_factory = structlog.PrintLoggerFactory(file=sys.stderr)
    cfg: dict[str, Any] = {
        "processors": processors,
        "wrapper_class": wrapper_class,
        "logger_factory": logger_factory,
        "cache_logger_on_first_use": False,
    }
    _config_cache[key] = cfg
    return cfg


def configure_logging(verbose: bool = False) -> None:
    """Configure ``structlog`` for the current process.

    - JSON renderer when ``sys.stderr.isatty()`` is ``False`` (CI / piped).
    - ``structlog.dev.ConsoleRenderer`` when ``True`` (interactive terminal).
    - Bound-logger level is ``DEBUG`` when ``verbose`` else ``INFO``.
    - Output goes to ``sys.stderr`` via ``PrintLoggerFactory`` so ``capsys``
      and ``2> run.log`` capture every event.

    Safe to call multiple times: subsequent calls with the same ``verbose``
    re-apply identical configuration; calls with a different ``verbose``
    cleanly swap the bound-logger level (AC-7).
    """
    structlog.configure(**_build_config(verbose))
