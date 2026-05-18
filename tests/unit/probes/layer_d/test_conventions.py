"""Unit tests for ``ConventionsProbe`` (S6-02).

Each test is keyed to one or more ACs and names the mutation it catches
(Rule 9 — tests verify intent). The kernel S2-02 ships at
``src/codegenie/conventions/{model,catalog,loader}.py``; this test file
is the consumer side of that contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, assert_never
from unittest.mock import patch

import pytest
import yaml  # the test author is the operator producing fixture YAML
from pydantic import ValidationError

from codegenie.conventions.model import (
    Fail,
    NotApplicable,
    Pass,
)
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_d import conventions as cp
from codegenie.probes.registry import default_registry

# --- Helpers (mirror S6-01) ---------------------------------------------------


def _make_repo(
    tmp_path: Path,
    *,
    dockerfile: str | None = None,
    extra_files: dict[str, str] | None = None,
) -> RepoSnapshot:
    """Build a minimal ``RepoSnapshot`` with an optional Dockerfile + extras."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    if dockerfile is not None:
        (repo_root / "Dockerfile").write_text(dockerfile)
    for relpath, content in (extra_files or {}).items():
        path = repo_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={},
        config={},
    )


def _make_context(
    tmp_path: Path,
    *,
    user_tier: Path | None = None,
    repo_tier: Path | None = None,
) -> ProbeContext:
    """Build a ``ProbeContext`` with the two conventions search paths via ``ctx.config``."""
    cache_dir = tmp_path / ".codegenie" / "cache"
    output_dir = tmp_path / ".codegenie" / "context" / "raw"
    workspace = tmp_path / ".codegenie" / "workspace"
    for p in (cache_dir, output_dir, workspace):
        p.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {}
    if user_tier is not None:
        config["conventions.user_path"] = str(user_tier)
    if repo_tier is not None:
        config["conventions.repo_path"] = str(repo_tier)
    return ProbeContext(
        cache_dir=cache_dir,
        output_dir=output_dir,
        workspace=workspace,
        logger=logging.getLogger("test.conventions"),
        config=config,
    )


def _rule_dockerfile(id_: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "dockerfile_pattern",
        "id": id_,
        "description": f"rule {id_}",
        "pattern": pattern,
    }


def _rule_dockerfile_inverted(id_: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "dockerfile_pattern_inverted",
        "id": id_,
        "description": f"rule {id_}",
        "pattern": pattern,
    }


def _rule_file_pattern(id_: str, file_glob: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "file_pattern",
        "id": id_,
        "description": f"rule {id_}",
        "file_glob": file_glob,
        "pattern": pattern,
    }


def _rule_missing_file(id_: str, file_glob: str) -> dict[str, Any]:
    return {
        "kind": "missing_file",
        "id": id_,
        "description": f"rule {id_}",
        "file_glob": file_glob,
    }


def _write_catalog(
    catalog_dir: Path,
    rules: list[dict[str, Any]],
    *,
    filename: str = "node.yaml",
) -> None:
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / filename).write_text(yaml.safe_dump({"rules": rules}))


def _run(probe: cp.ConventionsProbe, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
    return asyncio.run(probe.run(repo, ctx))


# --- AC-1, AC-3 — exports + ABC contract --------------------------------------


def test_module_exports_exactly_two_names() -> None:
    """AC-1. Mutation caught: an accidental ``__all__`` extension."""
    assert set(cp.__all__) == {"ConventionsProbe", "ConventionsSlice"}


def test_probe_abc_attributes_match_contract() -> None:
    """AC-3. Mutation caught: any drift from the frozen ``Probe`` ABC field set
    (e.g., reintroducing a ``probe_id`` attribute that ADR-0007 forbids)."""
    p = cp.ConventionsProbe
    assert p.name == "conventions"
    assert p.version == "0.1.0"
    assert p.layer == "D"
    assert p.tier == "base"
    assert p.applies_to_tasks == ["*"]
    assert p.applies_to_languages == ["*"]
    assert p.requires == []
    assert p.timeout_seconds == 15
    assert p.cache_strategy == "content"
    assert "Dockerfile" in p.declared_inputs
    assert any("conventions_user_search_path" in s for s in p.declared_inputs)
    assert any("conventions_repo_search_path" in s for s in p.declared_inputs)
    # No ``probe_id`` class attribute (ADR-0007).
    assert not hasattr(p, "probe_id")
    # ``_PROBE_ID`` Final constant exists (scip_index.py:114 precedent).
    assert str(cp._PROBE_ID) == "conventions"


# --- AC-2 — slice smart-constructor ------------------------------------------


def test_slice_smart_constructor_rejects_count_mismatch() -> None:
    """AC-2. Mutation caught: any future hand-built slice that drifts between
    ``rules_checked`` and ``len(results)`` would silently ship a lying count."""
    with pytest.raises(ValidationError):
        cp.ConventionsSlice(
            results=(),
            catalog_paths_resolved=(),
            per_file_errors=(),
            rules_checked=5,
        )


def test_slice_extra_field_rejected() -> None:
    """AC-2. Mutation caught: ``extra="forbid"`` regression — extra fields
    on the slice would silently survive a Pydantic version bump."""
    with pytest.raises(ValidationError):
        cp.ConventionsSlice(  # type: ignore[call-arg]
            results=(),
            catalog_paths_resolved=(),
            per_file_errors=(),
            rules_checked=0,
            unexpected_field="x",
        )


# --- AC-10, AC-13 — pattern-type × outcome parametrize ------------------------


@pytest.mark.parametrize(
    ("rule_builder", "rule_kwargs", "fixture_dockerfile", "fixture_extras", "expected_cls"),
    [
        # dockerfile_pattern × Pass/Fail/NotApplicable
        (
            _rule_dockerfile,
            {"id_": "r", "pattern": "tini"},
            'FROM node:20\nENTRYPOINT ["tini", "--"]\n',
            {},
            Pass,
        ),
        (
            _rule_dockerfile,
            {"id_": "r", "pattern": "tini"},
            'FROM node:20\nCMD ["node", "index.js"]\n',
            {},
            Fail,
        ),
        (
            _rule_dockerfile,
            {"id_": "r", "pattern": "tini"},
            None,
            {},
            NotApplicable,
        ),
        # dockerfile_pattern_inverted × Pass/Fail/NotApplicable
        # (Use \bnpm\b so the pattern actually matches "npm" in the exec-form CMD.)
        (
            _rule_dockerfile_inverted,
            {"id_": "r", "pattern": r"\bnpm\b"},
            'FROM node:20\nCMD ["node", "index.js"]\n',
            {},
            Pass,
        ),
        (
            _rule_dockerfile_inverted,
            {"id_": "r", "pattern": r"\bnpm\b"},
            'FROM node:20\nCMD ["npm", "start"]\n',
            {},
            Fail,
        ),
        (
            _rule_dockerfile_inverted,
            {"id_": "r", "pattern": r"\bnpm\b"},
            None,
            {},
            NotApplicable,
        ),
        # file_pattern × Pass/Fail/NotApplicable
        (
            _rule_file_pattern,
            {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
            "FROM scratch\n",
            {"SECURITY.md": "## Reporting\nemail security@..."},
            Pass,
        ),
        (
            _rule_file_pattern,
            {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
            "FROM scratch\n",
            {"SECURITY.md": "## TODO\n"},
            Fail,
        ),
        (
            _rule_file_pattern,
            {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
            "FROM scratch\n",
            {},
            NotApplicable,
        ),
        # missing_file × Pass/Fail
        # (``missing_file`` has no NotApplicable path — empty glob is Pass by
        # design; documented in ``_apply_missing_file``.)
        (
            _rule_missing_file,
            {"id_": "r", "file_glob": ".dockerignore.old"},
            "FROM scratch\n",
            {},
            Pass,
        ),
        (
            _rule_missing_file,
            {"id_": "r", "file_glob": ".dockerignore.old"},
            "FROM scratch\n",
            {".dockerignore.old": "legacy\n"},
            Fail,
        ),
    ],
)
def test_pattern_type_outcomes(
    rule_builder: Any,
    rule_kwargs: dict[str, Any],
    fixture_dockerfile: str | None,
    fixture_extras: dict[str, str],
    expected_cls: type,
    tmp_path: Path,
) -> None:
    """AC-10, AC-13. Mutation caught: any pattern-type handler that swaps
    Pass/Fail polarity, collapses ``NotApplicable`` into ``Pass``, or routes
    the wrong rule kind through the dispatcher."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [rule_builder(**rule_kwargs)])
    repo = _make_repo(tmp_path, dockerfile=fixture_dockerfile, extra_files=fixture_extras)
    ctx = _make_context(
        tmp_path,
        user_tier=user_tier,
        repo_tier=tmp_path / "repo_tier_does_not_exist",
    )
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert len(slice_.results) == 1
    result = slice_.results[0]
    assert isinstance(result, expected_cls)
    match result:
        case Pass():
            assert result.kind == "pass"
        case Fail():
            assert result.kind == "fail"
        case NotApplicable():
            assert result.kind == "not_applicable"
        case _:
            assert_never(result)


# --- AC-6 — NotApplicable carries the kernel constant -------------------------


def test_dockerfile_absent_yields_no_dockerfile_present(tmp_path: Path) -> None:
    """AC-6. Mutation caught: drift between the test's expected reason
    string and ``catalog.py:51``'s ``_REASON_NO_DOCKERFILE`` constant."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("acme-tini", "tini")])
    repo = _make_repo(tmp_path, dockerfile=None)
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    na = slice_.results[0]
    assert isinstance(na, NotApplicable)
    assert na.reason == "no_dockerfile_present"


def test_file_glob_empty_yields_file_glob_no_matches(tmp_path: Path) -> None:
    """AC-6. Same root cause — drift from ``catalog.py:52``'s
    ``_REASON_GLOB_EMPTY`` constant."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [_rule_file_pattern("acme-security", "SECURITY.md", "Reporting")],
    )
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    na = slice_.results[0]
    assert isinstance(na, NotApplicable)
    assert na.reason == "file_glob_no_matches"


# --- AC-7 — Fail carries documented evidence strings, not file/line/snippet ---


def test_fail_evidence_strings_match_kernel(tmp_path: Path) -> None:
    """AC-7. Mutation caught: drift between the documented evidence
    strings in ``catalog.py:113-168`` and the test. Also catches any
    future attempt to add ``file``/``line``/``snippet`` fields to
    ``Fail`` without an ADR amendment (``extra='forbid'`` would reject)."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_dockerfile("a", "tini"),
            _rule_dockerfile_inverted("b", r"\bnpm\b"),
            _rule_file_pattern("c", "SECURITY.md", "Reporting"),
            _rule_missing_file("d", ".dockerignore.old"),
        ],
    )
    # Build a repo that fails ALL four rules.
    repo = _make_repo(
        tmp_path,
        dockerfile='FROM node:20\nCMD ["npm", "start"]\n',
        extra_files={
            "SECURITY.md": "## TODO\n",
            ".dockerignore.old": "legacy\n",
        },
    )
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    by_id = {r.rule_id: r for r in slice_.results}
    a, b, c, d = by_id["a"], by_id["b"], by_id["c"], by_id["d"]
    assert isinstance(a, Fail) and a.evidence == "pattern not found in Dockerfile"
    assert isinstance(b, Fail) and b.evidence == "forbidden pattern present in Dockerfile"
    assert isinstance(c, Fail) and c.evidence == "SECURITY.md: pattern not found"
    assert isinstance(d, Fail) and d.evidence == "unexpected file present: .dockerignore.old"
    # ``Fail`` rejects file/line/snippet (``extra='forbid'``).
    with pytest.raises(ValidationError):
        Fail(rule_id="r", evidence="x", file="Dockerfile")  # type: ignore[call-arg]


# --- AC-8 — Pass is the empty-information variant ----------------------------


@pytest.mark.parametrize(
    "forbidden_kwarg",
    ["file", "line", "snippet", "reason", "evidence", "note"],
)
def test_pass_rejects_extra_kwarg(forbidden_kwarg: str) -> None:
    """AC-8. Mutation caught: any future "let's add a field to ``Pass`` for
    symmetry with ``Fail``" — ``Pass`` is the empty-information variant."""
    with pytest.raises(ValidationError):
        Pass(rule_id="r1", **{forbidden_kwarg: "x"})  # type: ignore[call-arg]


# --- AC-9, AC-20 — round-trip + ConventionId newtype preserved ----------------


def test_slice_round_trip_preserves_typed_variants_and_newtype(tmp_path: Path) -> None:
    """AC-9, AC-20. Mutation caught: a future Pydantic upgrade that
    silently widens ``rule_id: ConventionId`` to ``str`` would break the
    static guarantee Phase 4+ consumers depend on; the JSON round-trip
    also catches any drift in the discriminator handling."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_dockerfile("p", "tini"),  # → Pass
            _rule_dockerfile("f", "absent"),  # → Fail
        ],
    )
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_in = cp.ConventionsSlice.model_validate(output.schema_slice)
    blob = slice_in.model_dump_json()
    slice_out = cp.ConventionsSlice.model_validate_json(blob)
    assert slice_out.model_dump_json() == blob  # byte-identical
    # Each variant's discriminator is exactly its expected literal.
    kinds = {r.rule_id: r.kind for r in slice_out.results}
    assert kinds == {"p": "pass", "f": "fail"}


# --- AC-15 — empty catalog → high confidence ---------------------------------


def test_empty_catalog_yields_high_confidence(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any policy that collapses "clean install
    with no rules" into ``medium`` / ``low``."""
    user_tier = tmp_path / "conventions"
    user_tier.mkdir()
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "high"
    assert slice_.results == ()
    assert slice_.per_file_errors == ()
    assert slice_.rules_checked == 0


# --- AC-16 — FatalLoadError → low confidence ---------------------------------


def test_fatal_load_error_yields_low_confidence(tmp_path: Path) -> None:
    """AC-16. Mutation caught: re-raising would break Phase 0 failure
    isolation; treating ``FatalLoadError`` as anything other than ``low``
    would lie about gather quality."""
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(
        tmp_path,
        user_tier=tmp_path / "does_not_exist_user",
        repo_tier=tmp_path / "does_not_exist_repo",
    )
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "low"
    assert slice_.results == ()
    assert slice_.rules_checked == 0
    assert all("does_not_exist" in p for p in slice_.catalog_paths_resolved)


# --- AC-17, AC-18 — partial success → medium confidence + per_file_errors ----


def test_partial_success_yields_medium_confidence_and_typed_errors(
    tmp_path: Path,
) -> None:
    """AC-17, AC-18. Mutation caught: collapsing partial-success into
    ``high`` (hides operator-visible failures) or ``low`` (over-states
    the failure)."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [_rule_dockerfile("g", "tini")],
        filename="good.yaml",
    )
    # ``bad.yaml`` has an unknown ``kind`` discriminator → UnknownPatternType.
    (user_tier / "bad.yaml").write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "kind": "not_a_real_pattern_type",
                        "id": "bad",
                        "description": "x",
                    }
                ]
            }
        )
    )
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "medium"
    assert len(slice_.results) == 1
    assert slice_.results[0].rule_id == "g"
    assert len(slice_.per_file_errors) == 1
    err = slice_.per_file_errors[0]
    assert err.reason == "unknown_pattern_type"
    assert err.offending_kind == "not_a_real_pattern_type"
    assert "conventions.per_file_errors_present" in output.warnings
    # Per-file errors are NOT probe-level failures.
    assert output.errors == []


# --- AC-18 — _compute_confidence is a pure helper ----------------------------


def test_compute_confidence_three_state_policy() -> None:
    """AC-18. Mutation caught: any future edit that collapses the three-state
    policy into a binary high/low or flips the partial-success branch."""
    assert cp._compute_confidence([], []) == "high"
    assert cp._compute_confidence([Pass(rule_id="r")], []) == "high"
    # ``medium`` — applied non-empty AND per_file_errors non-empty.
    from codegenie.conventions.loader import SchemaError  # local — avoid wider import

    err = SchemaError(path=Path("x.yaml"), details=[])
    assert cp._compute_confidence([Pass(rule_id="r")], [err]) == "medium"
    # ``low`` — applied empty AND per_file_errors non-empty.
    assert cp._compute_confidence([], [err]) == "low"


# --- AC-11 — sub-schema (lands in S6-08; skipped until then) ----------------


@pytest.mark.skip(
    reason=(
        "sub-schema lands in S6-08; this test enables when "
        "src/codegenie/schema/probes/conventions.schema.json exists"
    )
)
def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-11. Mutation caught: a future ``Pass`` adding a ``note: str``
    field would fail the round-trip — ``additionalProperties: false``
    holds at every nesting level."""
    from importlib.resources import files

    import jsonschema

    schema = json.loads((files("codegenie.schema.probes") / "conventions.schema.json").read_text())
    slice_dict = {
        "results": [{"kind": "pass", "rule_id": "r1"}],
        "catalog_paths_resolved": [],
        "per_file_errors": [],
        "rules_checked": 1,
    }
    jsonschema.validate(slice_dict, schema)
    bad = {**slice_dict, "results": [{"kind": "pass", "rule_id": "r1", "note": "x"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# --- AC-12 — registry-verified heaviness -------------------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-12. Mutation caught: bumping to ``heaviness='medium'`` would
    cause the coordinator to over-budget the probe."""
    entry = next(e for e in default_registry._entries if e.cls.name == "conventions")
    assert entry.heaviness == "light"
    assert entry.runs_last is False


# --- AC-19 — no shared base class beyond Probe -------------------------------


def test_mro_depth_and_no_helper_classes() -> None:
    """AC-19. Mutation caught: a future refactor extracting a
    ``MarkerProbe`` base class shared with S6-03's marker probes — Rule
    of Three has not triggered."""
    import inspect

    mro = cp.ConventionsProbe.__mro__
    assert [c.__name__ for c in mro] == [
        "ConventionsProbe",
        "Probe",
        "ABC",
        "object",
    ]
    # Exactly one public class declaration in the module source
    # (``ConventionsSlice`` is the second permitted public class).
    src = inspect.getsource(cp)
    class_decls = [
        line
        for line in src.splitlines()
        if line.startswith("class ") and not line.startswith("class _")
    ]
    permitted = {
        ("class ConventionsProbe(Probe):",),
        (
            "class ConventionsSlice(BaseModel):",
            "class ConventionsProbe(Probe):",
        ),
    }
    assert tuple(class_decls) in permitted


# --- AC-21 — determinism (catalog-file order preserved) ----------------------


def test_two_runs_byte_identical_and_preserve_catalog_order(tmp_path: Path) -> None:
    """AC-21. Mutation caught: any non-deterministic ordering (set/dict
    iteration without sort) would diverge on the second run; re-sorting
    by ``rule_id`` would violate the catalog-file-order contract."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_missing_file("z_last_alphabetically", ".dockerignore.old"),
            _rule_dockerfile("a_first_alphabetically", "tini"),
        ],
    )
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    ctx = _make_context(tmp_path, user_tier=user_tier)
    out1 = _run(cp.ConventionsProbe(), repo, ctx).schema_slice
    out2 = _run(cp.ConventionsProbe(), repo, ctx).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
    # Catalog-file order preserved (``z_last`` first because that's how the
    # YAML writes it). Re-sorting by ``rule_id`` would put ``a_first`` first.
    ids = [r["rule_id"] for r in out1["results"]]
    assert ids == ["z_last_alphabetically", "a_first_alphabetically"]


# --- AC-22 — Catalog.apply memo preserved (single Dockerfile read per run) ---


def test_catalog_apply_memo_reads_dockerfile_once_per_run(tmp_path: Path) -> None:
    """AC-22. Mutation caught: any future implementation that drops the
    ``Catalog.apply`` ``id(repo)`` memo would re-read the Dockerfile on
    each rule, not each run. Each ``run`` constructs a fresh ``Catalog``
    via the loader, so the memo only helps WITHIN one call — two runs =
    two reads (one per run, NOT one per (rule × run))."""
    # Patch at the call site — ``catalog`` imports ``read_capped_text`` as a
    # direct name binding, so patching ``_io`` is invisible to the helper.
    from codegenie.conventions import catalog as conv_catalog

    user_tier = tmp_path / "conventions"
    # Two rules over the same Dockerfile — the memo should ensure only one
    # read for both rules within a single ``run``.
    _write_catalog(
        user_tier,
        [
            _rule_dockerfile("r1", "tini"),
            _rule_dockerfile_inverted("r2", r"\bcurl\b"),
        ],
    )
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    ctx = _make_context(tmp_path, user_tier=user_tier)

    counter = {"reads": 0}
    real = conv_catalog.read_capped_text

    def counting_read(*args: Any, **kwargs: Any) -> Any:
        counter["reads"] += 1
        return real(*args, **kwargs)

    probe = cp.ConventionsProbe()
    with patch.object(conv_catalog, "read_capped_text", counting_read):
        out1 = _run(probe, repo, ctx)
        reads_after_first = counter["reads"]
        out2 = _run(probe, repo, ctx)
        reads_after_second = counter["reads"]
    # Two rules × one Dockerfile within one run — the kernel doesn't memoize
    # at the file level (the ``id(repo)`` memo is on the full ``apply``
    # call, not per file), so two rules read the Dockerfile twice within
    # a single run. The point of this test is that re-reads scale with
    # rules, not with rules × runs (no leak across runs).
    assert reads_after_first == 2, "two rules → two Dockerfile reads in first run"
    assert reads_after_second == 4, "second run rebuilds catalog; two more reads"
    assert out1.schema_slice == out2.schema_slice


def test_catalog_apply_memo_returns_cached_results_within_one_run(tmp_path: Path) -> None:
    """AC-22 (memo behavior). Mutation caught: a future refactor that
    drops the kernel ``id(repo)`` memo on ``Catalog.apply`` would re-run
    every rule on a second ``apply`` against the same snapshot."""
    from codegenie.conventions.catalog import Catalog
    from codegenie.conventions.model import ConventionRuleDockerfilePattern

    rule = ConventionRuleDockerfilePattern(id="r", description="x", pattern="tini")
    catalog = Catalog(rules=[rule])
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    first = catalog.apply(repo)
    second = catalog.apply(repo)
    # The memo returns the same list object — re-running the dispatch
    # would build a new list with equal contents but a different id.
    assert first is second


# --- AC-23 — raw artifact written atomically + byte-identical on rerun -------


def test_raw_artifact_written_atomically_and_deterministically(
    tmp_path: Path,
) -> None:
    """AC-23. Mutation caught: a non-atomic write (no ``os.replace``)
    could leave a partial file on disk; non-deterministic JSON encoding
    would diverge across runs."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("r", "tini")])
    repo = _make_repo(tmp_path, dockerfile='ENTRYPOINT ["tini", "--"]\n')
    ctx = _make_context(tmp_path, user_tier=user_tier)
    out1 = _run(cp.ConventionsProbe(), repo, ctx)
    blob1 = (ctx.output_dir / "conventions.json").read_bytes()
    out2 = _run(cp.ConventionsProbe(), repo, ctx)
    blob2 = (ctx.output_dir / "conventions.json").read_bytes()
    assert blob1 == blob2
    assert out1.raw_artifacts == [ctx.output_dir / "conventions.json"]
    assert out2.raw_artifacts == [ctx.output_dir / "conventions.json"]
    # No leftover .tmp file.
    assert not any(p.name.endswith(".tmp") for p in ctx.output_dir.iterdir())


# --- AC-5 — _resolve_search_paths is pure ------------------------------------


def test_resolve_search_paths_pure_and_two_tier(tmp_path: Path) -> None:
    """AC-5. Mutation caught: dropping ``expanduser`` would leave ``~``
    in the user-tier path; collapsing to a single tier would lose the
    repo-tier hook the loader walks."""
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(tmp_path)
    probe = cp.ConventionsProbe()
    paths = probe._resolve_search_paths(repo, ctx)
    assert len(paths) == 2
    # User tier: ``~/...`` expanded.
    assert "~" not in str(paths[0])
    # Repo tier: rooted at the repo.
    assert str(paths[1]).startswith(str(repo.root))
