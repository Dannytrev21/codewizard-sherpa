"""S3-03 — FeedRegistry kernel + @register_vuln_feed decorator.

Covers AC-R1..R6.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from datetime import datetime

import pytest

from codegenie.result import Result
from codegenie.vuln_index import default_feed_registry
from codegenie.vuln_index.models import VulnerabilityRecord
from codegenie.vuln_index.parsers import VulnParseError
from codegenie.vuln_index.protocol import Feed
from codegenie.vuln_index.registry import (
    FeedRegistry,
    FeedRegistryError,
    register_vuln_feed,
)


@pytest.fixture
def isolated_registry() -> Iterator[FeedRegistry]:
    """Fresh :class:`FeedRegistry` instance per test (does not pollute default)."""
    yield FeedRegistry()


# AC-R1 — registry exists; default + decorator exported.
def test_registry_has_default_singleton_and_decorator() -> None:
    from codegenie.vuln_index import registry

    assert isinstance(registry.default_feed_registry, FeedRegistry)
    assert callable(registry.register_vuln_feed)


# AC-R3 — three concrete feeds registered.
def test_feed_sources_returns_three_registered_feeds() -> None:
    assert default_feed_registry.feed_sources() == ("ghsa", "nvd", "osv")


# AC-R5 — sorted iteration order.
def test_feed_sources_is_sorted_regardless_of_registration_order(
    isolated_registry: FeedRegistry,
) -> None:
    @isolated_registry.register("zzz")
    class FeedZ:
        source = "zzz"

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            raise NotImplementedError

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            yield from ()

    @isolated_registry.register("aaa")
    class FeedA:
        source = "aaa"

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            raise NotImplementedError

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            yield from ()

    @isolated_registry.register("mmm")
    class FeedM:
        source = "mmm"

        def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
            raise NotImplementedError

        def fetch(
            self,
            *,
            since: datetime | None = None,
            timeout_s: float = 30.0,
        ) -> Iterator[bytes]:
            yield from ()

    assert isolated_registry.feed_sources() == ("aaa", "mmm", "zzz")


# AC-R1 — duplicate registration raises with both origins.
def test_duplicate_registration_raises_with_both_origins(
    isolated_registry: FeedRegistry,
) -> None:
    @isolated_registry.register("dup")
    class FirstFeed:
        source = "dup"

        def parse_one(self, raw): ...  # type: ignore[no-untyped-def]

        def fetch(self, *, since=None, timeout_s=30.0):  # type: ignore[no-untyped-def]
            yield from ()

    with pytest.raises(FeedRegistryError) as exc_info:

        @isolated_registry.register("dup")
        class SecondFeed:
            source = "dup"

            def parse_one(self, raw): ...  # type: ignore[no-untyped-def]

            def fetch(self, *, since=None, timeout_s=30.0):  # type: ignore[no-untyped-def]
                yield from ()

    message = str(exc_info.value)
    assert "dup" in message
    assert "FirstFeed" in message
    assert "SecondFeed" in message


# AC-R3 — get_feed instantiates lazily.
def test_get_feed_returns_same_instance_on_repeated_calls() -> None:
    a = default_feed_registry.get_feed("nvd")
    b = default_feed_registry.get_feed("nvd")
    assert a is b


# AC-R4 — explicit imports drive registration (subprocess fence).
def test_omitting_one_feed_import_drops_one_source() -> None:
    """Inject a sitecustomize that intercepts ``codegenie.vuln_index.feeds.ghsa``
    so the package can be imported with only 2 registered feeds — proving
    that registration is import-driven, not metadata-discovery-driven."""
    code = textwrap.dedent(
        """
        import sys
        # Pre-populate the import cache so the explicit-import row for ghsa
        # short-circuits to a no-op module (no @register_vuln_feed call).
        import types
        stub = types.ModuleType("codegenie.vuln_index.feeds.ghsa")
        sys.modules["codegenie.vuln_index.feeds.ghsa"] = stub
        from codegenie.vuln_index import default_feed_registry
        print(",".join(default_feed_registry.feed_sources()))
        """
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    sources = proc.stdout.strip().split("\n")[-1]
    assert sources == "nvd,osv"


# AC-R6 — Open/Closed observable via test helper.
def test_register_vuln_feed_decorator_adds_to_default_registry() -> None:
    """The ``register_vuln_feed`` convenience targets the default registry."""

    @register_vuln_feed("_test_open_closed")
    class TempFeed:
        source = "_test_open_closed"

        def parse_one(self, raw): ...  # type: ignore[no-untyped-def]

        def fetch(self, *, since=None, timeout_s=30.0):  # type: ignore[no-untyped-def]
            yield from ()

    try:
        assert "_test_open_closed" in default_feed_registry.feed_sources()
    finally:
        default_feed_registry._test_unregister("_test_open_closed")
    assert "_test_open_closed" not in default_feed_registry.feed_sources()


# AC-R2 — Feed Protocol structural conformance.
def test_concrete_feeds_satisfy_protocol() -> None:
    for src in default_feed_registry.feed_sources():
        feed = default_feed_registry.get_feed(src)
        assert isinstance(feed, Feed)
        assert hasattr(feed, "source")
        assert callable(feed.parse_one)
        assert callable(feed.fetch)
