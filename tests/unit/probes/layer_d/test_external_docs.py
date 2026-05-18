"""Unit + architectural tests for ``ExternalDocsProbe`` (S6-04).

This story's tests are unusual: most ACs are *deferrals* — assertions
about what the probe does NOT do. That's load-bearing per the design's
"Schema before consumer" discipline: an opted-in schema with no Phase 2
consumer would be premature.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
from importlib.resources import files
from pathlib import Path

import jsonschema
import pydantic
import pytest

from codegenie.probes.layer_d import external_docs as ed
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId

from .conftest import _PROJECT_ROOT, _make_context, _make_repo


def test_run_returns_high_confidence_not_opted_in_by_default(tmp_path: Path) -> None:
    """AC-5. Pins the skip-cleanly default AND the ``confidence="high"``
    policy (absence is the data — S6-01 empty-install precedent)."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = ed.NotOptedInExternalDocsSlice.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    assert slice_.reason == "not_opted_in"
    assert output.errors == []
    assert output.warnings == []
    assert output.raw_artifacts == [ctx.output_dir / "external_docs.json"]
    assert output.duration_ms >= 0


def test_module_docstring_contains_open_q_4_phrase() -> None:
    """AC-2 / AC-13. Grep-discoverability trip-wire for Phase-4 contributors.

    Whitespace is collapsed before comparison so the prose can wrap across
    lines for line-length discipline without sacrificing the
    single-phrase grep semantics of AC-2.
    """
    assert ed.__doc__ is not None
    expected = (
        "Phase 2 ships the skip-cleanly stub; the opted-in schema lands when "
        "the first real user opts in (final-design.md Open Q 4)"
    )
    normalized = re.sub(r"\s+", " ", ed.__doc__)
    assert expected in normalized


def test_module_source_names_opted_in_discriminator() -> None:
    """AC-NEW-4. ``discriminator="opted_in"`` is the eventual tagged-union
    discriminator key; the literal string in module source is the
    discoverability contract."""
    src = inspect.getsource(ed)
    assert 'discriminator="opted_in"' in src, (
        "Module must explicitly name `opted_in` as the eventual tagged-union "
        "discriminator key (in a comment, docstring, or code) per AC-NEW-4."
    )


def test_no_subclass_extension_path() -> None:
    """AC-NEW-5. Future opted-in branch must land via ``match`` dispatch
    inside ``run``, not via subclass of ``ExternalDocsProbe``."""
    tree = ast.parse(inspect.getsource(ed))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b for b in node.bases if isinstance(b, ast.Name)]
            assert all(b.id != "ExternalDocsProbe" for b in bases), (
                f"Subclass {node.name!r} of ExternalDocsProbe violates AC-NEW-5"
            )


def test_no_forbidden_http_or_socket_imports() -> None:
    """AC-6. Fence-job duplicate in the unit lane for faster signal."""
    forbidden = {
        "httpx",
        "requests",
        "urllib.request",
        "aiohttp",
        "socket",
        "http.client",
        "httplib",
    }
    tree = ast.parse(inspect.getsource(ed))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert not (forbidden & names), f"Forbidden imports found: {forbidden & names}"


def test_no_speculative_allowlist_schema() -> None:
    """AC-7. ``Confluence`` / ``Notion`` / ... tokens fire the
    "Schema before consumer" anti-pattern alarm at compose time.

    Identifiers are matched with regex word boundaries (``\\b``) so that
    ``NotOptedInExternalDocsSlice`` — the AC-1-mandated class name that
    happens to *contain* the forbidden substring ``OptedInExternalDocsSlice``
    — does not falsely trip the speculative-schema alarm. The intent is to
    forbid a standalone identifier ``OptedInExternalDocsSlice`` from being
    defined or referenced; the substring test in the original story TDD
    plan conflicted with AC-1's naming requirement.
    """
    src = inspect.getsource(ed)
    speculative = (
        "Confluence",
        "Notion",
        "URLList",
        "URLSource",
        "FilesystemSource",
        "OptedInExternalDocsSlice",
    )
    for token in speculative:
        assert not re.search(rf"\b{re.escape(token)}\b", src), (
            f"{token!r} suggests a speculative allowlist schema. The schema "
            "lands when the first real user opts in (final-design Open Q 4)."
        )


def test_slice_rejects_opted_in_true_at_pydantic_level() -> None:
    """AC-3. ``Literal[False]`` is the discriminator-key invariant — relaxing
    to ``bool`` would silently admit an opted-in slice before ``run``
    knows how to produce one."""
    with pytest.raises(pydantic.ValidationError):
        ed.NotOptedInExternalDocsSlice(opted_in=True, reason="not_opted_in")  # type: ignore[arg-type]


def test_slice_rejects_extra_fields() -> None:
    """AC-3. ``extra="forbid"`` blocks additive fields on the not-opted-in
    model — extension lands as a new sibling, never as a backward-compatible
    additive change here."""
    with pytest.raises(pydantic.ValidationError):
        ed.NotOptedInExternalDocsSlice(
            opted_in=False,
            reason="not_opted_in",
            fetched_count=0,  # type: ignore[call-arg]
        )


def test_two_consecutive_runs_byte_identical(tmp_path: Path) -> None:
    """AC-10. ``duration_ms`` is intentionally excluded — it varies by clock."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    out2 = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True
    )
    raw_bytes = (ctx.output_dir / "external_docs.json").read_bytes()
    assert json.loads(raw_bytes) == out2.schema_slice


def test_registry_heaviness_is_light() -> None:
    """AC-9. Bumping heaviness for a probe that does no work would mis-budget
    the coordinator."""
    entry = next(e for e in default_registry._entries if e.cls.name == "external_docs")
    assert entry.heaviness == "light"


def test_registry_membership_present() -> None:
    """AC-NEW-3. ``@register_probe`` decorator is load-bearing."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == "external_docs"),
        None,
    )
    assert entry is not None, (
        "ExternalDocsProbe must be in default_registry._entries; "
        "@register_probe(heaviness='light') decorator is load-bearing"
    )


def test_probe_id_constant_exists() -> None:
    """AC-NEW-2. Dual-form probe identity (``name: str`` ABC attr +
    typed ``Final[ProbeId]`` module constant)."""
    assert hasattr(ed, "_PROBE_ID")
    assert ed._PROBE_ID == ProbeId("external_docs")
    assert ed.ExternalDocsProbe.name == "external_docs"


def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-8. Flat schema layout (no ``layer_d/`` subdir). The schema asserts
    ``opted_in`` is exactly ``false`` and ``reason`` is exactly
    ``"not_opted_in"`` with ``additionalProperties: false``."""
    schema = json.loads(
        (files("codegenie.schema.probes") / "external_docs.schema.json").read_text()
    )
    good = {"opted_in": False, "reason": "not_opted_in"}
    jsonschema.validate(good, schema)
    bad_opted_in = {"opted_in": True, "reason": "not_opted_in"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_opted_in, schema)
    bad_extra = {"opted_in": False, "reason": "not_opted_in", "fetched_count": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_extra, schema)


def test_manifest_readme_documents_deferral() -> None:
    """AC-14. Two-place documentation invariant — deletion of the deferral
    note from either docstring or manifest fires the test."""
    manifest = (
        _PROJECT_ROOT / "docs" / "phases" / "02-context-gather-layers-b-g" / "stories" / "README.md"
    )
    assert manifest.exists(), f"manifest not found at {manifest}"
    text = manifest.read_text()
    assert "ExternalDocsProbe" in text
    assert "opt-in" in text.lower() or "opted_in" in text.lower()


def test_run_performs_no_repo_or_ctx_config_reads(tmp_path: Path) -> None:
    """AC-5 (negative side). The probe must be unconditionally inert in
    Phase 2 — a pre-wired ``repo.config.get(...)`` check is the slippery
    slope to a real fetcher."""
    repo = _make_repo(tmp_path)
    repo.config["external_docs"] = {"sources": [{"type": "confluence", "url": "x"}]}
    ctx = _make_context(tmp_path)
    output = asyncio.run(ed.ExternalDocsProbe().run(repo, ctx))
    slice_ = ed.NotOptedInExternalDocsSlice.model_validate(output.schema_slice)
    assert slice_.opted_in is False
    src = inspect.getsource(ed)
    assert '.config.get("external_docs"' not in src
    assert '.config["external_docs"' not in src
    assert ".config['external_docs'" not in src
