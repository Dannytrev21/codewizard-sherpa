"""S5-05 — Load-bearing adversarial for image-digest drift (AC-12).

Three scenarios:

- Scenario A: cache-key invalidation via the ``image-digest:<resolved>``
  declared-input token. Two distinct resolver returns must produce two
  distinct cache keys; same return must produce the same key. (02-ADR-0004
  §Consequences names this file by path.)
- Scenario B: drift detected through B2 — ``IndexHealthProbe`` emits a
  ``Stale(DigestMismatch(...))`` in ``schema_slice["index_health"]
  ["runtime_trace"]["freshness"]`` when ``built_image_digest`` differs from
  ``last_traced_image_digest``.
- Scenario C: clean run emits ``Fresh`` in the same field.

Every assertion message names the ADR that the assertion defends so an
operator grepping a build break can locate the contract immediately.

No real subprocess is invoked — the ``forbid_real_subprocess`` fixture
raises ``AssertionError`` on any escape.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from codegenie.cache.keys import key_for
from codegenie.exec import ProcessResult
from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot, Task
from codegenie.probes.layer_b.index_health import IndexHealthProbe
from codegenie.probes.layer_c.runtime_trace import RuntimeTraceProbe
from tests.adv.phase02._helpers import (  # noqa: F401 — fixtures imported for use
    build_drift_slice,
    clean_freshness_registry,
    forbid_real_subprocess,
)

HEAD_SHA = "deadbeef00000000000000000000000000000000"

pytestmark = pytest.mark.phase02_adv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _repo(p: Path) -> RepoSnapshot:
    return RepoSnapshot(root=p, git_commit=None, detected_languages={}, config={})


def _ctx(p: Path, *, image_digest: str | None = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=p / "_cache",
        output_dir=p / "_out",
        workspace=p / "_ws",
        logger=logging.getLogger("adv"),
        config={},
        image_digest_resolver=(lambda _root: image_digest) if image_digest else None,
    )


def _patch_head_resolver(monkeypatch: pytest.MonkeyPatch, head: str = HEAD_SHA) -> None:
    from codegenie import exec as ce

    async def _run_allow(*args: Any, **kwargs: Any) -> ProcessResult:
        return ProcessResult(0, (head + "\n").encode(), b"")

    monkeypatch.setattr(ce, "run_allowlisted", AsyncMock(side_effect=_run_allow))


def _write_drift_slice(repo_root: Path, *, built: str | None, last_traced: str | None) -> None:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    payload = build_drift_slice(built, last_traced)
    (rd / "runtime_trace.json").write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# Scenario A — cache-key invalidation
# ---------------------------------------------------------------------------


def test_image_digest_change_changes_cache_key(tmp_path: Path) -> None:
    """02-ADR-0004 §Consequences — two distinct resolver returns must
    produce two distinct cache keys via the ``image-digest:<resolved>``
    declared-input token."""
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    repo = _repo(tmp_path)
    task = Task(type="distroless_migration", options={})

    digest_a = "sha256:aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
    digest_b = "sha256:bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"

    ctx_a = _ctx(tmp_path, image_digest=digest_a)
    ctx_b = _ctx(tmp_path, image_digest=digest_b)

    key_a = key_for(RuntimeTraceProbe(), repo, task, ctx=ctx_a)
    key_b = key_for(RuntimeTraceProbe(), repo, task, ctx=ctx_b)
    assert key_a != key_b, (
        "02-ADR-0004 §Consequences contract violated: image-digest:<resolved> "
        "token must produce distinct cache keys under distinct resolver returns; "
        "the dispatch arm in cache/keys.py::_resolve_special_token is not folding "
        "the resolved string into the content-hash tuple."
    )

    # Same resolver return → same key. Cache-HIT correctness.
    key_a_again = key_for(RuntimeTraceProbe(), repo, task, ctx=ctx_a)
    assert key_a == key_a_again, (
        "02-ADR-0004 — same image-digest must produce stable cache key on "
        "repeated invocation (cache-HIT correctness)."
    )


# ---------------------------------------------------------------------------
# Scenario B — drift detected through B2
# ---------------------------------------------------------------------------


def test_drift_detected_through_b2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """02-ADR-0006 — B2 surfaces ``DigestMismatch`` through
    ``schema_slice["index_health"]["runtime_trace"]["freshness"]`` when
    the synthetic runtime_trace slice records ``built != last_traced``.
    """
    _write_drift_slice(tmp_path, built="sha256:deadbeef", last_traced="sha256:cafebabe")
    _patch_head_resolver(monkeypatch)
    out = asyncio.run(IndexHealthProbe().run(_repo(tmp_path), _ctx(tmp_path)))
    freshness = out.schema_slice["index_health"]["runtime_trace"]["freshness"]

    # Four-part inequality — the load-bearing mutation-resistance pin.
    assert freshness["kind"] == "stale", (
        f"02-ADR-0006 — DigestMismatch must surface as Stale freshness; current={freshness!r}"
    )
    assert freshness["reason"]["kind"] == "digest_mismatch", (
        "02-ADR-0006 — Stale.reason discriminator must be 'digest_mismatch' "
        f"on image-digest drift; current={freshness['reason']!r}"
    )
    assert freshness["reason"]["expected"] == "sha256:deadbeef", (
        "02-ADR-0006 — DigestMismatch.expected must carry the currently-built "
        "digest (load-bearing argument order)."
    )
    assert freshness["reason"]["actual"] == "sha256:cafebabe", (
        "02-ADR-0006 — DigestMismatch.actual must carry what-was-traced "
        "(load-bearing argument order)."
    )


# ---------------------------------------------------------------------------
# Scenario C — clean run emits Fresh
# ---------------------------------------------------------------------------


def test_clean_run_emits_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """02-ADR-0006 — when ``built == last_traced``, freshness is Fresh."""
    _write_drift_slice(tmp_path, built="sha256:cafebabe", last_traced="sha256:cafebabe")
    _patch_head_resolver(monkeypatch)
    out = asyncio.run(IndexHealthProbe().run(_repo(tmp_path), _ctx(tmp_path)))
    freshness = out.schema_slice["index_health"]["runtime_trace"]["freshness"]
    assert freshness["kind"] == "fresh", (
        f"02-ADR-0006 — matching digests must emit Fresh; current={freshness!r}"
    )
    assert out.schema_slice["index_health"]["runtime_trace"]["confidence"] == "high", (
        "02-ADR-0006 — Fresh maps to high confidence per index_health._derive_confidence."
    )


# ---------------------------------------------------------------------------
# AC-13 — no real subprocess escapes the adversarial layer
# ---------------------------------------------------------------------------


def test_no_real_subprocess_in_adv_layer(forbid_real_subprocess: None) -> None:  # noqa: F811 — pytest fixture by name
    """The ``forbid_real_subprocess`` fixture itself is the test — if any
    seam slips by, the next test in this file fails loudly. Here we
    additionally smoke-test the fixture: explicitly invoking
    ``subprocess.run`` raises."""
    import subprocess

    with pytest.raises(AssertionError, match="real subprocess forbidden"):
        subprocess.run(["echo", "hi"], check=False)


# ---------------------------------------------------------------------------
# AC-14 — informative failure messages embed ADR refs
# ---------------------------------------------------------------------------


def test_assertion_messages_carry_adr_refs() -> None:
    """AST-introspect this file's assertion messages so a contributor who
    drops the ADR cross-reference is caught at CI time."""
    import ast

    source = Path(__file__).read_text()
    module = ast.parse(source)
    messages: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Assert) and node.msg is not None:
            messages.append(ast.dump(node.msg))

    blob = "\n".join(messages)
    assert "02-ADR-0004" in blob, (
        "scenario-A assertions must name 02-ADR-0004 in their failure messages "
        "so a contributor grepping a CI break can find the contract"
    )
    assert "image-digest" in blob, (
        "scenario-A assertions must mention 'image-digest' so the failure "
        "narrative is operator-debuggable"
    )
    assert "02-ADR-0006" in blob, (
        "scenarios B and C must name 02-ADR-0006 (IndexFreshness sum-type) "
        "in their failure messages"
    )
    assert "DigestMismatch" in blob, (
        "scenario B must name DigestMismatch so the mutation-resistance pin is operator-debuggable"
    )
