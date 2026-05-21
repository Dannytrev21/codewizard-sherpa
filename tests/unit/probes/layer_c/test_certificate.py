"""S5-03 — CertificateProbe tests."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c.certificate import (
    CertificateProbe,
    classify_certificate_source,
)
from codegenie.probes.registry import default_registry


def _make_repo(p: Path) -> RepoSnapshot:
    return RepoSnapshot(root=p, git_commit=None, detected_languages={}, config={})


def _make_ctx(p: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=p / "_c",
        output_dir=p / "_o",
        workspace=p / "_w",
        logger=logging.getLogger("t"),
        config={},
    )


def _write_runtime_trace(tmp_path: Path, payload: dict[str, Any]) -> None:
    rd = raw_dir(tmp_path)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "runtime_trace.json").write_text(json.dumps(payload))


async def _run(tmp_path: Path) -> dict[str, Any]:
    return (await CertificateProbe().run(_make_repo(tmp_path), _make_ctx(tmp_path))).schema_slice


def test_certificate_probe_register_light_with_class_attr_requires() -> None:
    entries = default_registry.sorted_for_dispatch()
    match = [e for e in entries if e.cls.__name__ == "CertificateProbe"]
    assert len(match) == 1
    assert match[0].heaviness == "light"
    assert CertificateProbe.requires == ["runtime_trace"]


@pytest.mark.parametrize(
    "paths, expected",
    [
        (["/etc/ssl/certs/ca-certificates.crt"], "ca-certificates"),
        (["/etc/ssl/certs/foo.pem"], "ca-certificates"),
        (["/app/vendor/certs/my.pem"], "vendored"),
        (["/vendor/certs/my.pem"], "vendored"),
        ([], "absent"),
        (["/opt/random/cert.pem"], "unknown"),
    ],
)
def test_certificate_classification(paths: list[str], expected: str) -> None:
    assert classify_certificate_source(paths) == expected


def test_certificate_probe_classifies_ca_certificates(tmp_path: Path) -> None:
    _write_runtime_trace(tmp_path, {"cert_paths_read": ["/etc/ssl/certs/ca-certificates.crt"]})
    out = asyncio.run(_run(tmp_path))
    assert out["certificate"]["certificate_source"] == "ca-certificates"
    assert out["certificate"]["cert_paths_read"] == ["/etc/ssl/certs/ca-certificates.crt"]


def test_certificate_probe_unavailable_when_runtime_trace_absent(tmp_path: Path) -> None:
    """AC-V2 — runtime_trace slice missing → confidence=unavailable, no exception."""
    out = asyncio.run(_run(tmp_path))
    assert out["certificate"]["confidence"] == "unavailable"
    assert out["certificate"]["cert_paths_read"] == []
    assert out["certificate"]["certificate_source"] == "absent"


def test_certificate_probe_empty_paths_absent(tmp_path: Path) -> None:
    _write_runtime_trace(tmp_path, {"cert_paths_read": []})
    out = asyncio.run(_run(tmp_path))
    assert out["certificate"]["certificate_source"] == "absent"
