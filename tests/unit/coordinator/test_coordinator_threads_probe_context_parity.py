"""Regression — coordinator runtime ctx must expose ``output_dir``.

The frozen probe contract (``probes/base.py`` ADR-0007) declares
``ProbeContext.output_dir``. The runtime ctx every probe receives via
``probe.run(snap, ctx)`` is :class:`BudgetingContext`. Drift between the
two was real in the wild: ``codegenie gather`` against a clean Node
repo (e.g. expressjs/express) hit ``AttributeError: 'BudgetingContext'
object has no attribute 'output_dir'`` for the Layer-B raw-sidecar
emitters (``scip_index``, ``tree_sitter_import_graph``) and the Layer-E
``slo`` stub. The coordinator's failure-isolation swallowed the crash so
the CLI still exited 0, masking the silent loss of probe output. The
audit record at ``.codegenie/context/runs/*.json`` recorded
``exit_status: "error"`` for these probes.

The fix adds ``output_dir`` to :class:`BudgetingContext` with a
``__post_init__`` default of ``workspace / .codegenie / context`` —
the same path :func:`codegenie.output.paths.context_dir` returns and
every raw-sidecar emitter writes against. This regression locks the
runtime invariant: when a probe reads ``ctx.output_dir`` through the
coordinator's real dispatch, the access must not raise.

Scope note: this is narrowly the ``output_dir`` drift. Other
``ProbeContext`` fields (``config``, ``image_digest_resolver``,
``cache_dir``, ``logger``) are also absent from
:class:`BudgetingContext`; Layer-D probes (``skills_index``, ``adrs``,
etc.) that read them keep crashing on those fields. Adding ``config`` to
the runtime ctx unmasks a separate latent ``skills_index`` sub-schema
mismatch (``shadowed_skills`` not in the schema), out of scope here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codegenie.coordinator.coordinator import gather
from codegenie.output.paths import context_dir
from codegenie.probes.base import ProbeOutput, RepoSnapshot
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


async def test_coordinator_threads_output_dir_to_ctx(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    """Probes that read ``ctx.output_dir`` MUST NOT see ``AttributeError``.

    Pre-fix: ``BudgetingContext`` did not expose ``output_dir``; every
    probe that read it crashed on the first attribute access. The
    coordinator's failure-isolation converted the crash into
    ``probe.failure`` with empty ``schema_slice`` — visible to operators
    only via ``.codegenie/context/runs/*.json``.
    """
    captured: dict[str, Any] = {}

    async def _capture(repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        # The attribute read below is exactly the access pattern the
        # failing probes use (slo, scip_index, tree_sitter_import_graph).
        # A missing field raises AttributeError, which the coordinator
        # converts into ``probe.failure`` — this test then fails because
        # ``captured["output_dir"]`` is never set.
        captured["output_dir"] = ctx.output_dir
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    probe = FakeProbe(name="probe-output-dir-readable", _run=_capture)
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )

    # ``output_dir`` resolves to <repo_root>/.codegenie/context/ — the
    # exact path the writer + every raw-sidecar emitter targets. The
    # choice is load-bearing: the CLI later reads raw artifacts from
    # ``<repo_root>/.codegenie/context/raw/`` so probes writing under
    # ``ctx.output_dir / "raw" / ...`` produce files the CLI can find.
    assert captured["output_dir"] == context_dir(tmp_path.resolve())


async def test_probe_reading_output_dir_subpath_does_not_attributeerror(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    """End-to-end shape: a probe that does ``ctx.output_dir / "raw" /
    "foo.json"`` (the scip_index / tree_sitter_import_graph pattern)
    completes via ``probe.success``, not ``probe.failure``.

    Pre-fix this raised ``AttributeError: 'BudgetingContext' object has
    no attribute 'output_dir'`` and the coordinator landed it as a
    failure with ``schema_slice={}``.
    """
    seen_path: dict[str, Path] = {}

    async def _emit(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        # Exactly the pattern in scip_index / tree_sitter_import_graph.
        artifact = ctx.output_dir / "raw" / "regression.json"
        seen_path["artifact"] = artifact
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    probe = FakeProbe(name="probe-output-dir-subpath", _run=_emit)
    result = await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )

    # A probe-failure path would land an output with non-empty errors;
    # the regression's signature was *zero* successful outputs.
    out = result.outputs.get("probe-output-dir-subpath")
    assert out is not None, "probe must produce an output, not fail"
    assert out.errors == [], f"probe failed with errors: {out.errors}"
    assert seen_path["artifact"].parts[-3:] == (
        "context",
        "raw",
        "regression.json",
    )


pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")
