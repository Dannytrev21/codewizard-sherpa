"""Shared pytest fixtures for unit tests.

The three fixtures here (:func:`fresh_cache`, :func:`fresh_sanitizer`,
:func:`fresh_config`) are the S3-05 coordinator-test triple — hermetic, no
test bleed across them. Each is function-scoped so tests can mutate state
without affecting siblings.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.output.sanitizer import OutputSanitizer


@pytest.fixture()
def fresh_cache(tmp_path: Path) -> CacheStore:
    return CacheStore(cache_dir=tmp_path / ".codegenie_cache", ttl_hours=24)


@pytest.fixture()
def fresh_sanitizer() -> OutputSanitizer:
    return OutputSanitizer()


class _MutableConfig:
    """Function-scoped wrapper that mirrors :class:`Config` fields but allows
    mutation. ``S3-04``'s frozen :class:`Config` blocks tests that need to
    set ``max_concurrent_probes=2`` for a single concurrency assertion; this
    wrapper is read in the coordinator the same way (`config.max_concurrent_probes`).
    """

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture()
def fresh_config() -> _MutableConfig:
    base = Config()
    return _MutableConfig(
        max_concurrent_probes=base.max_concurrent_probes,
        cache_ttl_hours=base.cache_ttl_hours,
        enable_audit=base.enable_audit,
    )


__all__ = ["fresh_cache", "fresh_config", "fresh_sanitizer", "replace"]
