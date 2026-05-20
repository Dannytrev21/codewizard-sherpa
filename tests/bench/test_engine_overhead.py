"""Advisory micro-bench — ``NpmLockfileRecipeEngine`` pure-Python overhead.

The ``apply`` budget is dominated by the jailed ``npm install``; the engine's
own work (parse + edit + serialise + diff + BLAKE3) should add well under
50 ms per call on the express fixture. ``bench`` is excluded from the default
``pytest`` selection — this canary never gates merge.
"""

from __future__ import annotations

import time

import orjson
import pytest

from codegenie.transforms.engines.npm_lockfile import (
    _build_unified_diff,
    _compute_transform_id,
    _edit_dep_version,
    _max_depth,
    _serialize_json,
)

_OVERHEAD_BUDGET_S = 0.050  # 50 ms — arch §Performance envelope C12


@pytest.mark.bench
def test_pure_python_overhead_under_50ms() -> None:
    """The parse + edit + serialise + diff + digest path stays under 50 ms."""
    before = (
        orjson.dumps(
            {
                "name": "express-cve-2024-21501",
                "version": "1.0.0",
                "dependencies": {"express": "^4.17.1", "lodash": "^4.17.21"},
            },
            option=orjson.OPT_INDENT_2,
        )
        + b"\n"
    )
    lockfile = orjson.dumps({"name": "x", "lockfileVersion": 3, "packages": {}}) + b"\n"

    start = time.perf_counter()
    doc = orjson.loads(before)
    _max_depth(doc)
    edited = _edit_dep_version(doc, "express", "^4.19.2")
    assert isinstance(edited, dict)
    after = _serialize_json(edited)
    diff = _build_unified_diff(before, after, lockfile, lockfile)
    _compute_transform_id(diff)
    elapsed = time.perf_counter() - start

    assert elapsed < _OVERHEAD_BUDGET_S, f"pure-Python overhead {elapsed * 1000:.1f} ms > 50 ms"
