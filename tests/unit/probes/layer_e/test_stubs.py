"""Unit tests for :class:`ServiceTopologyStubProbe` + :class:`SloStubProbe`
(S6-05).

Parametrized across the two stubs — they are deliberately near-identical
(S6-04 deferred-stub precedent). The parametrization makes the duplication
visible without hiding it behind a base class (Rule of Three forbids).
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import json
from pathlib import Path

import pydantic
import pytest

from codegenie.probes.layer_e import ownership as own
from codegenie.probes.layer_e import service_topology_stub as sts
from codegenie.probes.layer_e import slo_stub as slo
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId

_STUB_PARAMS = [
    pytest.param(
        sts,
        sts.ServiceTopologyStubProbe,
        sts.NotOptedInServiceTopologySlice,
        "service_topology",
        id="service_topology",
    ),
    pytest.param(
        slo,
        slo.SloStubProbe,
        slo.NotOptedInSloSlice,
        "slo",
        id="slo",
    ),
]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_always_high_confidence_not_opted_in(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-10, AC-11. Mutation caught: any flip to ``confidence='low'``
    (would signal "we tried and failed") or any ``repo.config[...]``
    read that bifurcates the response."""
    output = asyncio.run(probe_cls().run(_make_repo(tmp_path), _make_ctx(tmp_path)))
    assert output.confidence == "high"
    slice_ = slice_cls.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "phase_9_or_later"
    assert output.warnings == []
    assert output.errors == []


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_writes_single_raw_artifact_atomically(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-NEW-6 (part 1: stubs). Single canonical raw artifact named
    after the probe."""
    ctx = _make_ctx(tmp_path)
    output = asyncio.run(probe_cls().run(_make_repo(tmp_path), ctx))
    expected = ctx.output_dir / f"{probe_name}.json"
    assert output.raw_artifacts == [expected]
    on_disk = json.loads(expected.read_bytes())
    assert on_disk == output.schema_slice


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_two_runs_byte_identical(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-15. Mutation caught: any timestamp / nonce in the slice."""
    ctx = _make_ctx(tmp_path)
    probe = probe_cls()
    out1 = asyncio.run(probe.run(_make_repo(tmp_path), ctx))
    out2 = asyncio.run(probe.run(_make_repo(tmp_path), ctx))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True
    )
    raw_bytes = (ctx.output_dir / f"{probe_name}.json").read_bytes()
    assert json.loads(raw_bytes) == out2.schema_slice


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_registered_light_and_in_registry(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-4, AC-NEW-2."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == probe_name),
        None,
    )
    assert entry is not None, f"{probe_name} probe must be in default_registry._entries"
    assert entry.heaviness == "light"


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_probe_id_constant_exists(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-NEW-1. Dual-form identity discipline."""
    assert hasattr(module, "_PROBE_ID")
    assert module._PROBE_ID == ProbeId(probe_name)  # type: ignore[attr-defined]
    assert probe_cls.name == probe_name  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_no_forbidden_imports(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-12. Mutation caught: any HTTP/socket client import would
    break Phase-0 fence and determinism."""
    forbidden = {
        "httpx",
        "requests",
        "urllib.request",
        "aiohttp",
        "socket",
        "http.client",
        "httplib",
    }
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names), f"Forbidden imports in {probe_name}: {forbidden & names}"


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_no_subclass_extension_path(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-NEW-4. The eventual opted-in branch is ``match`` dispatch
    inside ``run``, not a subclass."""
    tree = ast.parse(inspect.getsource(module))
    target_name = probe_cls.__name__
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            assert target_name not in bases, (
                f"Subclass {node.name!r} of {target_name} violates AC-NEW-4"
            )


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_source_names_opted_in_discriminator(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-NEW-3. The grep token ``discriminator="opted_in"`` is the
    load-bearing trip-wire for the eventual Phase-9+ widening."""
    src = inspect.getsource(module)
    assert 'discriminator="opted_in"' in src, (
        f"{probe_name} module must name `opted_in` as the eventual "
        "tagged-union discriminator key (in docstring or code) per AC-NEW-3."
    )


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_docstring_documents_deferral(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-18. Deferral is grep-able via "deferred to Phase 9 or later"
    and the slice's ``reason`` literal ``"phase_9_or_later"``."""
    assert module.__doc__ is not None  # type: ignore[attr-defined]
    assert "deferred to Phase 9 or later" in module.__doc__  # type: ignore[attr-defined]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_slice_rejects_opted_in_true(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-3. Mutation caught: relaxing ``opted_in: Literal[False]``
    to ``bool``."""
    with pytest.raises(pydantic.ValidationError):
        slice_cls(opted_in=True, reason="phase_9_or_later")  # type: ignore[arg-type]


@pytest.mark.parametrize(("module", "probe_cls", "slice_cls", "probe_name"), _STUB_PARAMS)
def test_stub_slice_rejects_extra_fields(
    module: object,
    probe_cls: type,
    slice_cls: type,
    probe_name: str,
) -> None:
    """AC-2, AC-16. ``extra='forbid'`` enforced at Pydantic level."""
    with pytest.raises(pydantic.ValidationError):
        slice_cls(opted_in=False, reason="phase_9_or_later", extra="x")  # type: ignore[call-arg]


def test_no_cross_probe_imports_among_layer_e_files() -> None:
    """AC-13. The three layer_e files do not import each other; none
    imports from layer_d. Mutation caught: a future contributor
    extracting a shared base in one file and importing it in the
    others."""
    own_mod = importlib.import_module("codegenie.probes.layer_e.ownership")
    files_to_check = [own_mod, sts, slo]
    forbidden_substrings = (
        "codegenie.probes.layer_e.ownership",
        "codegenie.probes.layer_e.service_topology_stub",
        "codegenie.probes.layer_e.slo_stub",
        "codegenie.probes.layer_d",
    )
    for mod in files_to_check:
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in forbidden_substrings:
                    if forbidden == mod.__name__:
                        continue
                    assert forbidden not in node.module, (
                        f"{mod.__name__} forbidden-imports from {node.module}"
                    )


def test_ownership_module_is_distinct_from_stubs() -> None:
    """Sanity: ``own`` is imported but separate from stubs (keeps the
    cross-probe-import test's three-module fixture honest)."""
    assert own is not sts
    assert own is not slo
