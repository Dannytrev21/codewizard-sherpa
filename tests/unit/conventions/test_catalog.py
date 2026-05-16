"""Unit tests for ``codegenie.conventions`` — story 02 S2-02.

Covers AC-1, AC-2, AC-3..AC-13d, AC-15, AC-16 from
``docs/phases/02-context-gather-layers-b-g/stories/S2-02-conventions-catalog-loader.md``.

AC-1a, AC-5a, AC-9 (compile-time half), AC-10 (AST half), AC-14 live in
sibling files (test_no_*.py, test_inverted_helper_is_independent.py,
test_apply_match_is_exhaustive_compile_time.py).
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

import codegenie.parsers.safe_yaml as safe_yaml_mod
from codegenie.conventions import (
    Catalog,
    ConventionRule,
    ConventionRuleDockerfilePattern,
    ConventionRuleDockerfilePatternInverted,
    ConventionRuleFilePattern,
    ConventionRuleMissingFile,
    ConventionResult,
    ConventionsCatalogLoader,
    ConventionsError,
    Fail,
    NotApplicable,
    Pass,
)
from codegenie.conventions.loader import (
    CatalogFileUnreadable,
    CatalogLoadOutcome,
    DepthCapExceeded,
    FatalLoadError,
    SchemaError,
    SizeCapExceeded,
    SymlinkRefused,
    UnknownPatternType,
    UnsafeYaml,
)
from codegenie.probes.base import RepoSnapshot
from codegenie.result import Err, Ok
from codegenie.types.identifiers import ConventionId


def _write_catalog(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _repo_snapshot_with(tmp_path: Path, files: dict[str, str]) -> RepoSnapshot:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for relpath, contents in files.items():
        f = tmp_path / relpath
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contents)
    return RepoSnapshot(
        root=tmp_path, git_commit=None, detected_languages={}, config={}
    )


# ---------------------------------------------------------------------------
# AC-1 — module surface
# ---------------------------------------------------------------------------


def test_ac1_module_all_is_exact_set() -> None:
    import codegenie.conventions as c

    assert set(c.__all__) == {
        "Catalog",
        "CatalogFileUnreadable",
        "CatalogLoadOutcome",
        "ConventionRule",
        "ConventionRuleDockerfilePattern",
        "ConventionRuleDockerfilePatternInverted",
        "ConventionRuleFilePattern",
        "ConventionRuleMissingFile",
        "ConventionResult",
        "ConventionsCatalogLoader",
        "ConventionsError",
        "DepthCapExceeded",
        "Fail",
        "FatalLoadError",
        "NotApplicable",
        "Pass",
        "SchemaError",
        "SizeCapExceeded",
        "SymlinkRefused",
        "UnknownPatternType",
        "UnsafeYaml",
    }


@pytest.mark.parametrize(
    "model_cls",
    [
        Catalog,
        ConventionRuleDockerfilePattern,
        ConventionRuleDockerfilePatternInverted,
        ConventionRuleFilePattern,
        ConventionRuleMissingFile,
        Pass,
        Fail,
        NotApplicable,
        CatalogLoadOutcome,
    ],
)
def test_ac1_models_are_frozen_and_extra_forbid(model_cls: type) -> None:
    cfg = model_cls.model_config
    assert cfg.get("frozen") is True, f"{model_cls.__name__} must be frozen"
    assert cfg.get("extra") == "forbid", f"{model_cls.__name__} must extra='forbid'"


# ---------------------------------------------------------------------------
# AC-2 — pure-data constructor (no I/O)
# ---------------------------------------------------------------------------


def test_ac2_constructor_does_no_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(*a: object, **kw: object) -> None:
        pytest.fail(f"constructor performed I/O: args={a} kwargs={kw}")

    monkeypatch.setattr(os, "listdir", _fail)
    monkeypatch.setattr(os, "scandir", _fail)
    monkeypatch.setattr(os, "open", _fail)
    monkeypatch.setattr(os, "stat", _fail)
    monkeypatch.setattr(Path, "exists", _fail, raising=False)
    monkeypatch.setattr(Path, "is_dir", _fail, raising=False)
    monkeypatch.setattr(Path, "glob", _fail, raising=False)
    monkeypatch.setattr(Path, "iterdir", _fail, raising=False)
    ConventionsCatalogLoader(
        search_paths=[tmp_path / "does-not-exist", tmp_path / "also-missing"]
    )


# ---------------------------------------------------------------------------
# AC-3 — happy path per pattern type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yaml_body,expected_cls,expected_kind,expected_id,extra_field_name,extra_field_value",
    [
        (
            textwrap.dedent(
                """\
                rules:
                  - kind: dockerfile_pattern
                    id: distroless-base
                    description: must use chainguard distroless base
                    pattern: 'FROM cgr\\.dev/chainguard/'
                """
            ),
            ConventionRuleDockerfilePattern,
            "dockerfile_pattern",
            "distroless-base",
            "pattern",
            "FROM cgr\\.dev/chainguard/",
        ),
        (
            textwrap.dedent(
                """\
                rules:
                  - kind: dockerfile_pattern_inverted
                    id: no-root-user
                    description: must not run as root
                    pattern: '^USER root'
                """
            ),
            ConventionRuleDockerfilePatternInverted,
            "dockerfile_pattern_inverted",
            "no-root-user",
            "pattern",
            "^USER root",
        ),
        (
            textwrap.dedent(
                """\
                rules:
                  - kind: file_pattern
                    id: tsconfig-strict
                    description: strict mode required
                    file_glob: "**/tsconfig.json"
                    pattern: '"strict"\\s*:\\s*true'
                """
            ),
            ConventionRuleFilePattern,
            "file_pattern",
            "tsconfig-strict",
            "file_glob",
            "**/tsconfig.json",
        ),
        (
            textwrap.dedent(
                """\
                rules:
                  - kind: missing_file
                    id: no-rogue-dockerfile
                    description: no rogue dockerfile
                    file_glob: Dockerfile
                """
            ),
            ConventionRuleMissingFile,
            "missing_file",
            "no-rogue-dockerfile",
            "file_glob",
            "Dockerfile",
        ),
    ],
)
def test_ac3_happy_path_per_kind(
    tmp_path: Path,
    yaml_body: str,
    expected_cls: type,
    expected_kind: str,
    expected_id: str,
    extra_field_name: str,
    extra_field_value: str,
) -> None:
    _write_catalog(tmp_path / "conventions" / "c.yaml", yaml_body)
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert outcome.per_file_errors == []
    assert len(outcome.catalog.rules) == 1
    rule = outcome.catalog.rules[0]
    assert isinstance(rule, expected_cls)
    assert rule.kind == expected_kind
    assert rule.id == ConventionId(expected_id)
    assert "description" in expected_cls.model_fields
    assert getattr(rule, extra_field_name) == extra_field_value


def test_ac3a_multi_rule_single_file_in_order(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: a
                description: a
                pattern: 'X'
              - kind: missing_file
                id: b
                description: b
                file_glob: Dockerfile
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert len(outcome.catalog.rules) == 2
    assert outcome.catalog.rules[0].kind == "dockerfile_pattern"
    assert outcome.catalog.rules[1].kind == "missing_file"


def test_ac3b_multi_file_merge_is_sorted_relpath(tmp_path: Path) -> None:
    convdir = tmp_path / "conventions"
    _write_catalog(
        convdir / "b.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: from-b
                description: b
                file_glob: NEVER
            """
        ),
    )
    _write_catalog(
        convdir / "a.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: from-a
                description: a
                file_glob: NEVER
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[convdir]).load_all().unwrap()
    )
    assert [r.id for r in outcome.catalog.rules] == [
        ConventionId("from-a"),
        ConventionId("from-b"),
    ]


# ---------------------------------------------------------------------------
# AC-4 — dockerfile_pattern three outcomes (rule_id assertion-strict)
# ---------------------------------------------------------------------------


def test_ac4_dockerfile_pattern_three_outcomes(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: distroless-base
                description: chainguard required
                pattern: '^FROM cgr\\.dev/chainguard/'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    catalog = outcome.catalog
    expected_id = ConventionId("distroless-base")

    repo_pass = _repo_snapshot_with(
        tmp_path / "pass-repo", {"Dockerfile": "FROM cgr.dev/chainguard/node:latest\n"}
    )
    result_pass = catalog.apply(repo_pass)[0]
    assert isinstance(result_pass, Pass)
    assert result_pass.rule_id == expected_id

    repo_fail = _repo_snapshot_with(
        tmp_path / "fail-repo", {"Dockerfile": "FROM node:20-alpine\n"}
    )
    result_fail = catalog.apply(repo_fail)[0]
    assert isinstance(result_fail, Fail)
    assert result_fail.rule_id == expected_id
    assert result_fail.evidence != ""

    repo_na = _repo_snapshot_with(tmp_path / "na-repo", {"package.json": "{}"})
    result_na = catalog.apply(repo_na)[0]
    assert isinstance(result_na, NotApplicable)
    assert result_na.rule_id == expected_id
    assert result_na.reason == "no_dockerfile_present"


def test_ac4d_dockerfile_pattern_uses_re_multiline(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: distroless-base
                description: chainguard required
                pattern: '^FROM cgr\\.dev/chainguard/'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    repo = _repo_snapshot_with(
        tmp_path / "r",
        {"Dockerfile": "# build args first\nFROM cgr.dev/chainguard/node:latest\n"},
    )
    result = outcome.catalog.apply(repo)[0]
    assert isinstance(result, Pass)


# ---------------------------------------------------------------------------
# AC-5 — dockerfile_pattern_inverted three outcomes
# ---------------------------------------------------------------------------


def test_ac5_dockerfile_pattern_inverted_three_outcomes(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern_inverted
                id: no-root-user
                description: must not run as root
                pattern: '^USER root'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    catalog = outcome.catalog
    expected_id = ConventionId("no-root-user")

    # Match found → Fail
    repo_bad = _repo_snapshot_with(
        tmp_path / "bad", {"Dockerfile": "FROM scratch\nUSER root\n"}
    )
    result = catalog.apply(repo_bad)[0]
    assert isinstance(result, Fail)
    assert result.rule_id == expected_id

    # No match → Pass
    repo_good = _repo_snapshot_with(
        tmp_path / "good", {"Dockerfile": "FROM scratch\nUSER nobody\n"}
    )
    result = catalog.apply(repo_good)[0]
    assert isinstance(result, Pass)
    assert result.rule_id == expected_id

    # Missing Dockerfile → NotApplicable
    repo_na = _repo_snapshot_with(tmp_path / "na", {"package.json": "{}"})
    result = catalog.apply(repo_na)[0]
    assert isinstance(result, NotApplicable)
    assert result.rule_id == expected_id
    assert result.reason == "no_dockerfile_present"


# ---------------------------------------------------------------------------
# AC-6 — file_pattern semantics
# ---------------------------------------------------------------------------


def test_ac6_file_pattern_zero_matches_is_not_applicable(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: file_pattern
                id: tsconfig-strict
                description: strict mode required
                file_glob: "**/tsconfig.json"
                pattern: '"strict"\\s*:\\s*true'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    repo = _repo_snapshot_with(tmp_path / "no-ts", {"package.json": "{}"})
    result = outcome.catalog.apply(repo)[0]
    assert isinstance(result, NotApplicable)
    assert result.rule_id == ConventionId("tsconfig-strict")
    assert result.reason == "file_glob_no_matches"


def test_ac6a_file_pattern_pass_when_all_match(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: file_pattern
                id: tsconfig-strict
                description: strict mode required
                file_glob: "**/tsconfig.json"
                pattern: '"strict"\\s*:\\s*true'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    repo = _repo_snapshot_with(
        tmp_path / "r",
        {
            "a/tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
            "b/tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
        },
    )
    result = outcome.catalog.apply(repo)[0]
    assert isinstance(result, Pass)
    assert result.rule_id == ConventionId("tsconfig-strict")


def test_ac6b_file_pattern_fail_names_lex_first_failing(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: file_pattern
                id: tsconfig-strict
                description: strict mode required
                file_glob: "**/tsconfig.json"
                pattern: '"strict"\\s*:\\s*true'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    repo = _repo_snapshot_with(
        tmp_path / "r",
        {
            "a/tsconfig.json": '{"strict": true}\n',
            "b/tsconfig.json": '{"strict": false}\n',
            "z/tsconfig.json": '{"strict": false}\n',
        },
    )
    result = outcome.catalog.apply(repo)[0]
    assert isinstance(result, Fail)
    assert "b/tsconfig.json" in result.evidence
    assert "z/tsconfig.json" not in result.evidence


def test_ac6c_file_glob_pathlib_recursive_and_dot_exclusion(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: file_pattern
                id: foo-strict
                description: foo
                file_glob: "**/foo.json"
                pattern: 'X'
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    repo = _repo_snapshot_with(
        tmp_path / "r",
        {
            "x/y/foo.json": "X\n",
            ".hidden/foo.json": "X\n",
        },
    )
    # Only the non-hidden file participates. Since it matches the pattern, Pass.
    result = outcome.catalog.apply(repo)[0]
    assert isinstance(result, Pass)


# ---------------------------------------------------------------------------
# AC-7 — missing_file semantics
# ---------------------------------------------------------------------------


def test_ac7_missing_file_passes_when_absent_fails_when_present(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: no-rogue-dockerfile
                description: no rogue dockerfile
                file_glob: Dockerfile
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    catalog = outcome.catalog
    expected_id = ConventionId("no-rogue-dockerfile")

    repo_clean = _repo_snapshot_with(tmp_path / "clean", {"package.json": "{}"})
    result = catalog.apply(repo_clean)[0]
    assert isinstance(result, Pass)
    assert result.rule_id == expected_id

    repo_dirty = _repo_snapshot_with(tmp_path / "dirty", {"Dockerfile": "FROM scratch\n"})
    result = catalog.apply(repo_dirty)[0]
    assert isinstance(result, Fail)
    assert result.rule_id == expected_id
    assert "Dockerfile" in result.evidence


# ---------------------------------------------------------------------------
# AC-8 — unknown pattern type + AC-8a/b/c — yaml umbrellas
# ---------------------------------------------------------------------------


def test_ac8_unknown_pattern_type_isolated_other_rules_unaffected(
    tmp_path: Path,
) -> None:
    convdir = tmp_path / "conventions"
    bad = _write_catalog(
        convdir / "bad.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern_glob
                id: x
                description: y
                pattern: ".*"
            """
        ),
    )
    _write_catalog(
        convdir / "good.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: ok-rule
                description: ok
                file_glob: NEVER
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[convdir]).load_all().unwrap()
    )
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, UnknownPatternType)
    assert err.offending_kind == "dockerfile_pattern_glob"
    assert err.path == bad
    assert len(outcome.catalog.rules) == 1
    assert outcome.catalog.rules[0].id == ConventionId("ok-rule")


def test_ac8a_unsafe_yaml_python_object_does_not_execute(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    _write_catalog(
        tmp_path / "conventions" / "evil.yaml",
        f"!!python/object/apply:os.system ['touch {sentinel}']\n",
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert not sentinel.exists(), "yaml deserialization executed code"
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, UnsafeYaml)


def test_ac8a_unsafe_yaml_syntax_error_lands_in_umbrella(tmp_path: Path) -> None:
    _write_catalog(tmp_path / "conventions" / "bad.yaml", "rules: [\n")
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, UnsafeYaml)


def test_ac8b_size_cap_exceeded(tmp_path: Path) -> None:
    big = tmp_path / "conventions" / "big.yaml"
    big.parent.mkdir(parents=True, exist_ok=True)
    # 1.1 MiB of yaml-ish padding
    big.write_text("rules: []\n" + "# pad\n" * ((1 << 20) // 6 + 100))
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SizeCapExceeded)


def test_ac8c_depth_cap_exceeded(tmp_path: Path) -> None:
    deep = "rules:\n  - kind: dockerfile_pattern\n"
    # construct a deeply nested mapping under `extra:` to trip depth walker
    body = "x:\n" + "".join("  " * i + f"k{i}:\n" for i in range(1, 70)) + "  " * 70 + "leaf: 1\n"
    _write_catalog(tmp_path / "conventions" / "deep.yaml", body)
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, DepthCapExceeded)


# ---------------------------------------------------------------------------
# AC-9 — match smoke (runtime half)
# ---------------------------------------------------------------------------


def test_ac9_apply_match_smoke_asserts_assert_never_only() -> None:
    from codegenie.conventions.catalog import _apply_one

    class _Imposter:
        kind = "not_a_real_kind"

    with pytest.raises(AssertionError):
        _apply_one(_Imposter(), repo=None)  # type: ignore[arg-type]


def test_ac9a_result_model_field_sets_are_minimal() -> None:
    p = Pass(rule_id=ConventionId("x"))
    assert p.model_dump() == {"kind": "pass", "rule_id": "x"}

    f = Fail(rule_id=ConventionId("x"), evidence="why")
    assert f.model_dump() == {"kind": "fail", "rule_id": "x", "evidence": "why"}

    na = NotApplicable(rule_id=ConventionId("x"), reason="no")
    assert na.model_dump() == {"kind": "not_applicable", "rule_id": "x", "reason": "no"}

    # Pass must reject `evidence` (illegal-states-unrepresentable)
    with pytest.raises(ValidationError):
        Pass(rule_id=ConventionId("x"), evidence="leak")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AC-10 — safe_yaml.load chokepoint (runtime half — AST half in sibling file)
# ---------------------------------------------------------------------------


def test_ac10_safe_yaml_chokepoint_is_only_yaml_call_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_load = safe_yaml_mod.load
    calls: list[Path] = []

    def spy(path: Path, *, max_bytes: int, max_depth: int = 64):  # type: ignore[no-untyped-def]
        calls.append(path)
        return real_load(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(safe_yaml_mod, "load", spy)
    # Two catalog files — assert one spy call per file
    convdir = tmp_path / "conventions"
    _write_catalog(convdir / "a.yaml", "rules: []\n")
    _write_catalog(convdir / "b.yaml", "rules: []\n")
    ConventionsCatalogLoader(search_paths=[convdir]).load_all().unwrap()
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# AC-11 — sub-schemas extra="forbid" (typed SchemaError)
# ---------------------------------------------------------------------------


def test_ac11_extra_field_yields_typed_schema_error(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: x
                description: y
                pattern: ".*"
                unexpected_key: value
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert outcome.catalog.rules == []
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SchemaError)
    assert err.details
    assert any("unexpected_key" in str(row) for row in err.details)


def test_ac11a_uncompilable_regex_pattern_lands_at_load(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: bad
                description: bad regex
                pattern: "[unterminated"
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    assert outcome.catalog.rules == []
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SchemaError)
    assert any("pattern" in str(row.get("loc", "")) for row in err.details)


# ---------------------------------------------------------------------------
# AC-12 — Catalog.apply is pure (idempotent + no repeated I/O)
# ---------------------------------------------------------------------------


def test_ac12_catalog_apply_is_idempotent_without_repeated_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_catalog(
        tmp_path / "conventions" / "c.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: dockerfile_pattern
                id: x
                description: y
                pattern: "FROM"
            """
        ),
    )
    outcome = (
        ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
        .load_all()
        .unwrap()
    )
    catalog = outcome.catalog
    repo = _repo_snapshot_with(tmp_path / "r", {"Dockerfile": "FROM node\n"})

    first = catalog.apply(repo)

    opens: list[Path] = []
    real_open = Path.open

    def _spy_open(self: Path, *a: object, **kw: object):  # type: ignore[no-untyped-def]
        if self.is_relative_to(repo.root):
            opens.append(self)
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", _spy_open, raising=False)
    second = catalog.apply(repo)
    assert first == second
    assert opens == []


# ---------------------------------------------------------------------------
# AC-13 — ConventionsError discriminated union, seven reasons
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ctor,kwargs",
    [
        (UnknownPatternType, {"path": Path("/x"), "offending_kind": "y"}),
        (SchemaError, {"path": Path("/x"), "details": [{"loc": ("a",)}]}),
        (SymlinkRefused, {"path": Path("/x")}),
        (UnsafeYaml, {"path": Path("/x")}),
        (SizeCapExceeded, {"path": Path("/x")}),
        (DepthCapExceeded, {"path": Path("/x")}),
        (CatalogFileUnreadable, {"path": Path("/x"), "errno_name": "ENOENT"}),
    ],
)
def test_ac13_conventions_error_discriminated_union_seven_reasons(
    ctor: type, kwargs: dict
) -> None:
    adapter = TypeAdapter(ConventionsError)
    instance = ctor(**kwargs)
    # Round-trip through the adapter validates discriminator dispatch
    dumped = instance.model_dump()
    rehydrated = adapter.validate_python(dumped)
    assert isinstance(rehydrated, ctor)


def test_ac13_symlink_refused_json_shape() -> None:
    assert SymlinkRefused(path=Path("/x")).model_dump() == {
        "reason": "symlink_refused",
        "path": Path("/x"),
    }


def test_ac13_unknown_reason_raises() -> None:
    adapter = TypeAdapter(ConventionsError)
    with pytest.raises(ValidationError):
        adapter.validate_python({"reason": "bogus", "path": "/x"})


def test_ac13a_toctou_disappearance_yields_catalog_file_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    convdir = tmp_path / "conventions"
    missing_path = _write_catalog(convdir / "a.yaml", "rules: []\n")
    _write_catalog(
        convdir / "b.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: b-rule
                description: b
                file_glob: NEVER
            """
        ),
    )
    real_load = safe_yaml_mod.load
    raised = {"done": False}

    def _maybe_raise(path: Path, *, max_bytes: int, max_depth: int = 64):  # type: ignore[no-untyped-def]
        if not raised["done"] and path == missing_path:
            raised["done"] = True
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_load(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(safe_yaml_mod, "load", _maybe_raise)
    outcome = (
        ConventionsCatalogLoader(search_paths=[convdir]).load_all().unwrap()
    )
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, CatalogFileUnreadable)
    assert err.errno_name == "ENOENT"
    assert any(r.id == ConventionId("b-rule") for r in outcome.catalog.rules)


def test_ac13b_partial_success_under_mixed_quality(tmp_path: Path) -> None:
    convdir = tmp_path / "conventions"
    _write_catalog(
        convdir / "ok.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: missing_file
                id: ok
                description: ok
                file_glob: NEVER
            """
        ),
    )
    _write_catalog(
        convdir / "unknown.yaml",
        textwrap.dedent(
            """\
            rules:
              - kind: unknown_kind
                id: x
                description: y
                pattern: "."
            """
        ),
    )
    _write_catalog(convdir / "broken.yaml", "rules: [\n")
    outcome = (
        ConventionsCatalogLoader(search_paths=[convdir]).load_all().unwrap()
    )
    assert len(outcome.catalog.rules) == 1
    assert outcome.catalog.rules[0].id == ConventionId("ok")
    reasons = sorted(e.reason for e in outcome.per_file_errors)
    assert reasons == ["unknown_pattern_type", "unsafe_yaml"]


def test_ac13c_empty_search_paths_returns_ok_empty() -> None:
    result = ConventionsCatalogLoader(search_paths=[]).load_all()
    assert isinstance(result, Ok)
    outcome = result.value
    assert outcome.catalog.rules == []
    assert outcome.per_file_errors == []


def test_ac13d_fatal_when_every_search_path_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    convdir = tmp_path / "conventions"
    convdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(os, "access", lambda *a, **kw: False)
    result = ConventionsCatalogLoader(search_paths=[convdir]).load_all()
    assert isinstance(result, Err)
    err = result.error
    assert isinstance(err, FatalLoadError)
    assert err.reason == "no_search_path_readable"
    assert err.paths == [convdir]


# ---------------------------------------------------------------------------
# AC-16 — TDD discipline is implied by the commit history; nothing runtime to assert.
# ---------------------------------------------------------------------------
