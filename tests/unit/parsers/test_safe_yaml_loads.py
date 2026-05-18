"""Unit tests for ``safe_yaml.loads`` (S6-03 / AC-21).

The in-memory bytes entry-point sibling to :func:`safe_yaml.load`. It
preserves the chokepoint discipline (size cap, top-level mapping, depth
walk) without admitting a parallel YAML pathway: it wraps the existing
``_parse_one`` + ``assert_max_depth`` primitives. Each test names the
mutation it catches (Rule 9 — tests verify intent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.errors import DepthCapExceeded, MalformedYAMLError, SizeCapExceeded
from codegenie.parsers import safe_yaml


def test_loads_happy_path_mapping() -> None:
    """AC-21. Mutation caught: a regression that drops the mapping
    decode pathway would surface as an empty parse here."""
    data = b"name: foo\nvalue: 42\n"
    parsed = safe_yaml.loads(data, max_bytes=4096, max_depth=8)
    assert parsed == {"name": "foo", "value": 42}


def test_loads_size_cap_exceeded() -> None:
    """AC-21. Mutation caught: dropping the pre-parse size guard would
    silently admit arbitrarily large in-memory payloads through the
    chokepoint."""
    data = b"x: " + b"y" * 100
    with pytest.raises(SizeCapExceeded):
        safe_yaml.loads(data, max_bytes=10, max_depth=8)


def test_loads_top_level_list_rejected() -> None:
    """AC-21 / AC-22. Mutation caught: admitting a top-level list would
    bypass the mapping discipline that the exception-YAML format pin
    depends on."""
    data = b"- a\n- b\n"
    with pytest.raises(MalformedYAMLError):
        safe_yaml.loads(data, max_bytes=4096, max_depth=8)


def test_loads_top_level_scalar_rejected() -> None:
    """AC-21. Mutation caught: silently returning a non-mapping scalar
    would break the ``Mapping[str, JSONValue]`` return contract."""
    with pytest.raises(MalformedYAMLError):
        safe_yaml.loads(b"42\n", max_bytes=4096, max_depth=8)


def test_loads_empty_bytes_rejected() -> None:
    """AC-21. Empty bytes resolve to ``None`` from PyYAML — the chokepoint
    rejects ``None`` the same way ``load(path)`` does on an empty file."""
    with pytest.raises(MalformedYAMLError):
        safe_yaml.loads(b"", max_bytes=4096, max_depth=8)


def test_loads_depth_cap_exceeded() -> None:
    """AC-21. Mutation caught: dropping the depth walk would re-open the
    alias-amplification surface that ``assert_max_depth`` closes."""
    deep = b"a:\n  b:\n    c:\n      d:\n        e: 1\n"
    with pytest.raises((DepthCapExceeded, MalformedYAMLError)):
        safe_yaml.loads(deep, max_bytes=4096, max_depth=2)


def test_loads_malformed_yaml_translated() -> None:
    """AC-21. Mutation caught: leaking a raw ``yaml.YAMLError`` out of the
    chokepoint would break catch-site coupling to ``MalformedYAMLError``."""
    with pytest.raises(MalformedYAMLError):
        safe_yaml.loads(b"key: : :\n", max_bytes=4096, max_depth=8)


def test_loads_byte_identical_to_load_from_path(tmp_path: Path) -> None:
    """AC-21. Cross-validation: ``loads(bytes)`` and ``load(path)`` yield
    identical parsed structures for the same payload — confirms the
    chokepoint extension routes through the shared ``_parse_one`` + depth
    walker primitives, not a parallel decode."""
    payload = b"k: 1\nlist:\n  - a\n  - b\n"
    f = tmp_path / "f.yaml"
    f.write_bytes(payload)
    from_path = safe_yaml.load(f, max_bytes=4096, max_depth=8)
    from_bytes = safe_yaml.loads(payload, max_bytes=4096, max_depth=8)
    assert dict(from_path) == dict(from_bytes)


def test_loads_exported_in_public_all() -> None:
    """AC-21. Mutation caught: forgetting to grow ``__all__`` would
    silently hide the new entry-point from ``from safe_yaml import *``
    consumers and from public-surface tests."""
    assert "loads" in safe_yaml.__all__
