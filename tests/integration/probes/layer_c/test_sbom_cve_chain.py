"""S5-04 — integration tests for the SbomProbe → CveProbe chain.

Validates the end-to-end story: a fixture ``runtime_trace`` slice on
disk, SbomProbe runs and writes both raw files to ``<raw_dir>/``,
CveProbe runs against the SBOM file SbomProbe just wrote, and the
cache-key infrastructure invalidates atomically across both probes when
the ``image-digest:<resolved>`` resolved value changes (02-ADR-0004
§Consequences).

Mocks ``run_external_cli`` (no real syft/grype binaries needed) but
exercises the actual probe codepath end-to-end. Lives in
``tests/integration/`` so the fast unit suite is unaffected.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from codegenie.cache.keys import key_for
from codegenie.exec import ProcessResult
from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot, Task
from codegenie.probes.layer_c import cve as cve_mod
from codegenie.probes.layer_c import sbom as sbom_mod
from codegenie.probes.layer_c.cve import CveProbe
from codegenie.probes.layer_c.sbom import SbomProbe

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def _repo(p: Path) -> RepoSnapshot:
    return RepoSnapshot(root=p, git_commit=None, detected_languages={}, config={})


def _ctx(p: Path, image_digest: str | None = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=p / "_c",
        output_dir=p / "_o",
        workspace=p / "_w",
        logger=logging.getLogger("t"),
        config={},
        image_digest_resolver=(lambda _root: image_digest) if image_digest else None,
    )


def _write_runtime_trace(repo_root: Path, digest: str) -> None:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "runtime_trace.json").write_text(
        json.dumps(
            {
                "built_image_digest": digest,
                "trace_coverage_confidence": "high",
                "scenarios_run": ["startup"],
                "scenarios_failed": [],
            }
        )
    )


def test_sbom_then_cve_chain_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: SbomProbe writes syft-sbom.json, CveProbe reads it,
    both slice files materialize at <raw_dir>/sbom.json and cve.json."""
    syft_bytes = (FIXTURES / "syft" / "hello_world.json").read_bytes()
    grype_bytes = (FIXTURES / "grype" / "hello_world.json").read_bytes()

    async def _stub_sbom(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=syft_bytes, stderr=b"")

    async def _stub_grype(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=grype_bytes, stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _stub_sbom)
    monkeypatch.setattr(cve_mod, "run_external_cli", _stub_grype)
    _write_runtime_trace(tmp_path, "sha256:deadbeefcafef00ddeadbeefcafef00d")

    # Step 1 — SbomProbe.run() — produces sbom.json + syft-sbom.json on disk.
    sbom_out = asyncio.run(SbomProbe().run(_repo(tmp_path), _ctx(tmp_path)))
    rd = raw_dir(tmp_path)
    assert (rd / "sbom.json").is_file()
    assert (rd / "syft-sbom.json").is_file()
    assert sbom_out.schema_slice["sbom"]["outcome"]["kind"] == "ran"

    # Step 2 — CveProbe.run() — finds sbom.json + the raw syft file, runs grype.
    cve_out = asyncio.run(CveProbe().run(_repo(tmp_path), _ctx(tmp_path)))
    assert (rd / "cve.json").is_file()
    assert (rd / "grype-cves.json").is_file()
    cve = cve_out.schema_slice["cve"]
    assert cve["outcome"]["kind"] == "ran"
    assert cve["total"] == 4
    assert cve["scanner"] == "grype"


def test_image_digest_invalidation_two_distinct_cache_entries(tmp_path: Path) -> None:
    """02-ADR-0004 — same Dockerfile, two distinct ``image-digest:`` resolver
    returns must produce two distinct cache keys."""
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    repo = _repo(tmp_path)
    task = Task(type="distroless_migration", options={})
    digest_a = "sha256:aaaa1111aaaa1111aaaa1111aaaa1111"
    digest_b = "sha256:bbbb2222bbbb2222bbbb2222bbbb2222"
    ctx_a = _ctx(tmp_path, image_digest=digest_a)
    ctx_b = _ctx(tmp_path, image_digest=digest_b)
    key_a = key_for(SbomProbe(), repo, task, ctx=ctx_a)
    key_b = key_for(SbomProbe(), repo, task, ctx=ctx_b)
    assert key_a != key_b, "image-digest change must invalidate the SbomProbe cache key"
    # Repeated call with same digest is stable (cache-HIT correctness).
    key_a_again = key_for(SbomProbe(), repo, task, ctx=ctx_a)
    assert key_a == key_a_again
