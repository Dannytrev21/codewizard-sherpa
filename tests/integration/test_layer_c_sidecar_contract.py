"""End-to-end regression guard for the Layer C sibling-slice contract.

WHY THIS FILE EXISTS — the gap it closes
----------------------------------------
Layer C marker probes (``entrypoint``, ``shell_usage``, ``certificate``)
consume an upstream probe's slice from ``.codegenie/context/raw/<name>.json``
via :func:`~codegenie.probes.layer_b.index_health.read_raw_slices`. That
pattern only works if the upstream probe actually *persists* that sidecar.
Two upstream probes — ``dockerfile`` and ``runtime_trace`` — historically did
not (they returned ``raw_artifacts=[]`` and wrote nothing to ``raw/``), so
every consumer was silently dead on every gather, on every platform: each
emitted ``confidence: "unavailable"`` forever.

No existing test caught it, for three structural reasons:

1. **Consumer unit tests fabricate their own upstream.** Each consumer's
   unit test writes ``raw/<name>.json`` by hand before running the probe
   (e.g. ``tests/unit/probes/layer_c/test_entrypoint.py::_write_dockerfile_slice``).
   The producer<->consumer seam was therefore never exercised as a pair —
   the consumer was always handed a fabricated sidecar.
2. **The portfolio golden test snapshotted the broken output.** It runs a
   full gather, but its committed goldens recorded the broken
   ``confidence: "unavailable"`` slice as the expected baseline. A golden
   detects *drift*, not *wrongness* — a broken baseline passes forever.
3. **The smoke fixtures have no Dockerfile.** ``empty_repo`` / ``js_only`` /
   ``polyglot`` never let a Layer C container probe produce real output, and
   the one structural smoke check (``test_no_probe_errors_in_smoke_run_record``)
   treats ``skipped`` / empty slices as first-class — it only catches
   *exceptions*, not *silent emptiness*.

These tests run a real ``codegenie gather`` against a repo that HAS a
Dockerfile and assert the contract directly: (1) every raw sidecar a probe
declares as an input is actually produced, and (2) the dependent probes emit
real data rather than the degraded ``unavailable`` slice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner

_DOCKERFILE = (
    "FROM node:20-slim\n"
    "WORKDIR /app\n"
    "COPY package.json ./\n"
    "COPY index.js ./\n"
    "RUN npm ci --omit=dev || true\n"
    'ENTRYPOINT ["node", "index.js"]\n'
)

_RAW_SIDECAR_TOKEN = re.compile(r"^\.codegenie/context/raw/([a-z0-9_]+)\.json$")


def _make_dockerfile_repo(tmp_path: Path) -> Path:
    """Build a hermetic Node repo that HAS a Dockerfile.

    A Dockerfile is the precondition that makes both sidecar producers run:
    ``dockerfile`` parses it, and ``runtime_trace`` only ``applies()`` when a
    Dockerfile is present.
    """
    repo = tmp_path / "dockerfile_repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text(_DOCKERFILE)
    (repo / "package.json").write_text(
        '{"name": "sidecar-contract-fixture", "version": "1.0.0"}\n'
    )
    (repo / "index.js").write_text("console.log('hello');\n")
    return repo


def _gather(repo: Path) -> dict[str, Any]:
    """Run ``codegenie --no-gitignore gather <repo>`` and return the envelope."""
    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert result.exit_code == 0, f"gather failed (exit {result.exit_code}): {result.output}"
    yaml_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.is_file(), f"envelope missing at {yaml_path}"
    envelope = yaml.safe_load(yaml_path.read_text())
    return envelope


def _declared_raw_sidecars() -> set[str]:
    """Every ``raw/<name>.json`` sidecar that any registered probe declares
    as an input via ``declared_inputs``.

    Probes are instantiated (``e.cls()``) before reading ``declared_inputs``
    because some probes — e.g. ``DepGraphProbe`` — set it on the instance
    rather than the class, exactly as the CLI's registry seam does.
    """
    import codegenie.probes  # noqa: F401  (import populates the probe registry)
    from codegenie.probes.registry import default_registry

    required: set[str] = set()
    for entry in default_registry.sorted_for_dispatch():
        for token in entry.cls().declared_inputs:
            match = _RAW_SIDECAR_TOKEN.match(token)
            if match is None:
                continue
            required.add(match.group(1))
    return required


def test_declared_raw_sidecar_inputs_are_produced_by_a_gather(tmp_path: Path) -> None:
    """Structural contract: every ``raw/<name>.json`` a probe declares as an
    input must actually be written by a gather.

    This is the catch-all for the bug class "probe wired to a sidecar nobody
    writes". A declaring probe whose sidecar is never produced reads nothing
    via ``read_raw_slices`` and emits ``confidence=unavailable`` on every run,
    forever — exactly how entrypoint/shell_usage/certificate shipped dead.
    The check auto-extends: any future probe that declares a raw sidecar
    input gets the same guarantee for free.
    """
    required = _declared_raw_sidecars()

    assert {"dockerfile", "runtime_trace"} <= required, (
        f"expected the Layer C marker sidecars in declared inputs; got {sorted(required)}"
    )

    repo = _make_dockerfile_repo(tmp_path)
    _gather(repo)
    raw_dir = repo / ".codegenie" / "context" / "raw"

    missing = sorted(name for name in required if not (raw_dir / f"{name}.json").is_file())
    assert not missing, (
        f"probes declare raw/<name>.json as a gather input, but no probe produced it: "
        f"{missing}. The declaring probe(s) will read nothing via read_raw_slices() and "
        f"emit confidence=unavailable on every gather. The producing probe must persist "
        f"its slice to raw/<name>.json (see dockerfile.py / runtime_trace.py _write_files)."
    )


def test_dockerfile_consumers_populate_on_real_gather(tmp_path: Path) -> None:
    """Behavioural contract: a repo WITH a Dockerfile yields non-empty
    ``entrypoint`` and ``shell_usage`` slices after a real gather.

    This is the semantic oracle the portfolio golden test lacked — it asserts
    the *expectation* ("a parsed Dockerfile reaches its consumers"), not a
    snapshot, so a broken baseline cannot hide the bug.
    """
    repo = _make_dockerfile_repo(tmp_path)
    probes = _gather(repo)["probes"]

    entrypoint = probes["entrypoint"]["entrypoint"]
    assert entrypoint["confidence"] != "unavailable", (
        "entrypoint is 'unavailable' despite a Dockerfile being present — "
        "it could not read the dockerfile sidecar"
    )
    assert entrypoint["entrypoints"], (
        "entrypoint probe saw a Dockerfile but reported no entrypoint"
    )
    assert entrypoint["entrypoints"][0]["form"] == "exec", entrypoint["entrypoints"]

    static = probes["shell_usage"]["shell_usage"]["static"]
    assert static["final_stage_entrypoint_form"] == "exec", (
        "shell_usage.static did not pick up the Dockerfile's ENTRYPOINT — "
        f"it could not read the dockerfile sidecar. static={static}"
    )
    assert static["final_stage_run_commands"], (
        "shell_usage.static dropped the Dockerfile RUN line"
    )


def test_runtime_trace_consumer_populates_on_real_gather(tmp_path: Path) -> None:
    """Behavioural contract for the second producer: ``certificate`` consumes
    the ``runtime_trace`` sidecar.

    On macOS the underlying trace is platform-degraded, but ``certificate``
    must still reach a non-``unavailable`` confidence — proving it read a real
    ``runtime_trace`` slice rather than a phantom missing file.
    """
    repo = _make_dockerfile_repo(tmp_path)
    probes = _gather(repo)["probes"]

    certificate = probes["certificate"]["certificate"]
    assert certificate["confidence"] != "unavailable", (
        "certificate is 'unavailable' — it could not read the runtime_trace "
        "sidecar (raw/runtime_trace.json was never written)"
    )
