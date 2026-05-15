"""Red tests for S4-01 — ``CIProbe``.

Pins AC-1..AC-27 from
``docs/phases/01-context-gather-layer-a-node/stories/S4-01-ci-probe.md``.

Helpers are defined inline (matches the S2-02 / S3-05 sibling idiom). The
probe's ``run()`` is async; tests use ``asyncio.run`` directly to keep
``pytest-asyncio`` out of the dependency surface.

Pins: CIProbe records provider + workflow + image-build + secrets as facts;
multi-provider + Jenkins + presence-only-stubs downgrade confidence; secrets
regex is bounded against ReDoS; references_secrets is sorted+deduped.
Traces to: phase-arch-design.md §"Component design" #5; ADR-0004; ADR-0006;
ADR-0007; ADR-0010; production ADR-0005.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import pytest

from codegenie.catalogs import CI_PROVIDERS
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------- helpers ----------------------------------------------------------


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={},  # CIProbe is applies_to_languages = ["*"]
        config={},
    )


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=None,
    )


def _run(root: Path) -> ProbeOutput:
    from codegenie.probes.ci import CIProbe

    return asyncio.run(CIProbe().run(_snapshot(root), _ctx(root)))


def _write_workflow(root: Path, body: str, name: str = "x.yml") -> None:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(body)


def _minimal_envelope_with_ci(*, rogue_root: bool = False) -> dict[str, Any]:
    slice_payload: dict[str, Any] = {
        "provider": None,
        "additional_providers": [],
        "workflow_files": [],
        "builds_image": False,
        "image_build_command": None,
        "unit_test_command": None,
        "smoke_test_command": None,
        "references_secrets": [],
        "warnings": [],
    }
    ci_block: dict[str, Any] = {"ci": slice_payload}
    if rogue_root:
        ci_block["rogue_field"] = True
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {"ci": ci_block},
    }


# ---------- T-1: registry membership across languages (AC-2) ---------------


@pytest.mark.parametrize(
    "langs",
    [
        frozenset(),
        frozenset({"go"}),
        frozenset({"javascript"}),
        frozenset({"python"}),
    ],
)
def test_registry_membership_language_agnostic(langs: frozenset[str]) -> None:
    from codegenie.probes import default_registry
    from codegenie.probes.ci import CIProbe

    assert CIProbe in default_registry.all_probes()
    assert CIProbe in default_registry.for_task("*", langs)


# ---------- T-2: probe contract attributes (AC-1) --------------------------


def test_probe_contract_attributes_match_arch() -> None:
    from codegenie.probes.ci import CIProbe

    assert CIProbe.name == "ci"
    assert CIProbe.version == "1.0.0"
    assert CIProbe.layer == "A"
    assert CIProbe.tier == "base"
    assert CIProbe.applies_to_languages == ["*"]
    assert CIProbe.applies_to_tasks == ["*"]
    assert CIProbe.requires == []
    assert CIProbe.timeout_seconds == 10
    assert CIProbe.declared_inputs == [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "src/codegenie/catalogs/ci_providers.yaml",
    ]


# ---------- T-3: catalog precedence pinned at file boundary (AC-15) -------


def test_ci_providers_catalog_order_locked() -> None:
    from codegenie.probes.ci import _PROVIDER_PRECEDENCE

    assert tuple(CI_PROVIDERS.keys()) == _PROVIDER_PRECEDENCE
    assert _PROVIDER_PRECEDENCE == (
        "github_actions",
        "gitlab_ci",
        "circleci",
        "jenkins",
        "azure_pipelines",
    )


# ---------- T-4: image-build detection — parametrized (AC-4..AC-7) --------


@pytest.mark.parametrize(
    "step_yaml,expected_substr,builds",
    [
        ("- run: docker build -t app .", "docker build", True),
        (
            "- run: docker buildx build --platform linux/amd64 .",
            "docker buildx",
            True,
        ),
        ("- uses: docker/build-push-action@v5", "docker/build-push-action", True),
        ("- run: docker run hello-world", None, False),
    ],
)
def test_image_build_detection(
    tmp_path: Path,
    step_yaml: str,
    expected_substr: str | None,
    builds: bool,
) -> None:
    _write_workflow(
        tmp_path,
        f"jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      {step_yaml}\n",
    )
    s = _run(tmp_path).schema_slice["ci"]
    assert s["builds_image"] is builds
    if expected_substr is None:
        assert s["image_build_command"] is None
    else:
        assert s["image_build_command"] is not None
        assert expected_substr in s["image_build_command"]


# ---------- T-5: GitLab CI clean single-provider, high confidence (AC-8) --


def test_gitlab_only_high_confidence(tmp_path: Path) -> None:
    (tmp_path / ".gitlab-ci.yml").write_text("test:\n  script:\n    - npm test\n")
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] == "gitlab_ci"
    assert s.get("unit_test_command") and "npm test" in s["unit_test_command"]
    assert out.confidence == "high"
    assert s["warnings"] == []


# ---------- T-6: provider precedence — parametrized (AC-14, AC-16) --------


@pytest.mark.parametrize(
    "present,provider,additional,expect_multi_warning",
    [
        (
            {".github/workflows/x.yml", ".gitlab-ci.yml", ".circleci/config.yml"},
            "github_actions",
            ["gitlab_ci", "circleci"],
            True,
        ),
        ({".gitlab-ci.yml", "Jenkinsfile"}, "gitlab_ci", ["jenkins"], True),
        ({".gitlab-ci.yml"}, "gitlab_ci", [], False),
        ({"Jenkinsfile"}, "jenkins", [], False),
        (
            {".circleci/config.yml", ".gitlab-ci.yml"},
            "gitlab_ci",
            ["circleci"],
            True,
        ),
    ],
)
def test_provider_precedence_follows_catalog_order(
    tmp_path: Path,
    present: set[str],
    provider: str,
    additional: list[str],
    expect_multi_warning: bool,
) -> None:
    if ".github/workflows/x.yml" in present:
        _write_workflow(tmp_path, "jobs: {}\n", name="x.yml")
    if ".gitlab-ci.yml" in present:
        (tmp_path / ".gitlab-ci.yml").write_text("stages: [build]\n")
    if ".circleci/config.yml" in present:
        circ = tmp_path / ".circleci"
        circ.mkdir()
        (circ / "config.yml").write_text("version: 2.1\n")
    if "Jenkinsfile" in present:
        (tmp_path / "Jenkinsfile").write_text("pipeline {}")
    if "azure-pipelines.yml" in present:
        (tmp_path / "azure-pipelines.yml").write_text("trigger: none\n")

    s = _run(tmp_path).schema_slice["ci"]
    assert s["provider"] == provider
    assert s["additional_providers"] == additional
    if expect_multi_warning:
        assert "ci.multi_provider" in s["warnings"]
    else:
        assert "ci.multi_provider" not in s["warnings"]


# ---------- T-7: Jenkinsfile regex-only — bound + multi-quote (AC-9) ------


@pytest.mark.parametrize(
    "body,expect_in_unit",
    [
        (
            "pipeline { stages { stage('t') { steps { sh 'npm test' } } } }",
            "npm test",
        ),
        (
            'pipeline { stages { stage("t") { steps { sh "npm run build" } } } }',
            "npm run build",
        ),
    ],
)
def test_jenkinsfile_regex_extraction(tmp_path: Path, body: str, expect_in_unit: str) -> None:
    (tmp_path / "Jenkinsfile").write_text(body)
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] == "jenkins"
    assert s.get("unit_test_command") and expect_in_unit in s["unit_test_command"]
    assert s["warnings"] == ["ci.jenkinsfile_regex_only"]
    assert out.confidence == "low"


def test_jenkinsfile_no_sh_commands_still_low_confidence(tmp_path: Path) -> None:
    (tmp_path / "Jenkinsfile").write_text("pipeline { agent any }")
    out = _run(tmp_path)
    assert "ci.jenkinsfile_regex_only" in out.schema_slice["ci"]["warnings"]
    assert out.confidence == "low"


# ---------- T-8: presence-only stubs (AC-10, AC-11) -----------------------


def test_circleci_presence_only_low_confidence(tmp_path: Path) -> None:
    (tmp_path / ".circleci").mkdir()
    (tmp_path / ".circleci" / "config.yml").write_text("version: 2.1\n")
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] == "circleci"
    assert s["workflow_files"] == []
    assert "ci.circleci_presence_only" in s["warnings"]
    assert out.confidence == "low"


def test_azure_pipelines_presence_only_low_confidence(tmp_path: Path) -> None:
    (tmp_path / "azure-pipelines.yml").write_text("trigger: none\n")
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] == "azure_pipelines"
    assert "ci.azure_pipelines_presence_only" in s["warnings"]
    assert out.confidence == "low"


# ---------- T-9: empty .github/workflows/ directory (AC-12) ---------------


def test_empty_workflows_dir(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] == "github_actions"
    assert s["workflow_files"] == []
    assert s["builds_image"] is False
    assert "ci.empty_workflows_dir" in s["warnings"]
    assert out.confidence == "low"


# ---------- T-10: no CI present at all — slice IS produced (AC-13) -------


def test_no_ci_present_slice_still_emitted(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# repo\n")
    out = _run(tmp_path)
    s = out.schema_slice["ci"]
    assert s["provider"] is None
    assert s["additional_providers"] == []
    assert s["workflow_files"] == []
    assert s["builds_image"] is False
    assert s["image_build_command"] is None
    assert s["unit_test_command"] is None
    assert s["smoke_test_command"] is None
    assert s["references_secrets"] == []
    assert s["warnings"] == []
    assert out.confidence == "high"


# ---------- T-11: secrets sorted + deduped + literal-only (AC-18, AC-19) -


def test_secrets_sorted_deduped_literal_only(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - run: echo ${{ secrets.B }} ${{ secrets.A }} ${{ secrets.A }}\n",
        name="a.yml",
    )
    _write_workflow(
        tmp_path,
        "steps:\n  - run: echo ${{ secrets.C }}\n",
        name="b.yml",
    )
    s = _run(tmp_path).schema_slice["ci"]
    assert s["references_secrets"] == ["A", "B", "C"]


def test_secrets_regex_does_not_match_env_inputs_or_capitalized(
    tmp_path: Path,
) -> None:
    _write_workflow(
        tmp_path,
        "steps:\n  - run: echo "
        "${{ env.FOO }} ${{ inputs.BAR }} ${{ Secrets.X }} ${{ secrets.REAL }}\n",
    )
    assert _run(tmp_path).schema_slice["ci"]["references_secrets"] == ["REAL"]


def test_secrets_value_never_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sentinel: probe must NOT call os.environ.get for any secret name."""
    import os

    looked_up: list[str] = []
    real_get = os.environ.get

    def spy(name: str, default: Any = None) -> Any:
        looked_up.append(name)
        return real_get(name, default)

    monkeypatch.setattr(os.environ, "get", spy)
    _write_workflow(
        tmp_path,
        "steps:\n  - run: echo ${{ secrets.NPM_TOKEN }}\n",
    )
    _run(tmp_path)
    assert "NPM_TOKEN" not in looked_up


# ---------- T-12: secrets regex bound + ReDoS guard (AC-17) ---------------


def test_secrets_regex_bounded_at_129_chars(tmp_path: Path) -> None:
    long_name = "A" * 200
    _write_workflow(
        tmp_path,
        f"steps:\n  - run: echo ${{{{ secrets.{long_name} }}}}\n",
    )
    captured = _run(tmp_path).schema_slice["ci"]["references_secrets"]
    assert long_name not in captured
    for c in captured:
        assert len(c) <= 129


def test_secrets_regex_completes_under_one_second(tmp_path: Path) -> None:
    """ReDoS guard — 5000 reps of unterminated `${{ secrets.A`."""
    hostile = "${{ secrets.A" * 5000
    _write_workflow(
        tmp_path,
        f"steps:\n  - run: |\n      {hostile}\n",
    )
    t0 = time.monotonic()
    _run(tmp_path)
    assert time.monotonic() - t0 < 1.0


def test_secrets_regex_constant_shape() -> None:
    """AC-17 — exact regex constant pinned."""
    from codegenie.probes.ci import _SECRETS_RE

    assert _SECRETS_RE.pattern == r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}"


# ---------- T-13: per-file workflow YAML parse failure (AC-21, CN-1) -----


def test_malformed_workflow_skipped_gather_continues(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "jobs: {\n", name="bad.yml")
    _write_workflow(
        tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        name="good.yml",
    )
    s = _run(tmp_path).schema_slice["ci"]
    assert s["workflow_files"] == ["good.yml"]
    assert "ci.workflow_parse_error" in s["warnings"]
    for w in s["warnings"]:
        # bare ID — no colon, no path suffix
        assert ":" not in w
        assert ADR_0007.match(w), f"violates ADR-0007: {w!r}"


# ---------- T-14: local-action reference emits warning (AC-22) ----------


def test_local_action_reference_warning(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: ./.github/actions/local-action\n",
    )
    s = _run(tmp_path).schema_slice["ci"]
    assert "ci.local_action_unparsed" in s["warnings"]


# ---------- T-15: warning ID frozenset + import-time pattern (AC-20) ----


def test_warning_ids_match_adr_0007() -> None:
    from codegenie.probes import ci as ci_mod

    expected = {
        "ci.jenkinsfile_regex_only",
        "ci.multi_provider",
        "ci.workflow_parse_error",
        "ci.gitlab_ci_parse_error",
        "ci.local_action_unparsed",
        "ci.empty_workflows_dir",
        "ci.circleci_presence_only",
        "ci.azure_pipelines_presence_only",
    }
    assert ci_mod._WARNING_IDS == expected
    for w in ci_mod._WARNING_IDS:
        assert ADR_0007.match(w)


# ---------- T-16: dispatch registry covers every parser arm (AC-24) ----


def test_ci_parsers_dispatch_registry_complete() -> None:
    from typing import get_args

    from codegenie.probes.ci import _CI_PARSERS, _PARSER_LITERAL

    assert set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL))


# ---------- T-17: image-build markers tuple (AC-25) ---------------------


def test_image_build_markers_table_locked() -> None:
    from codegenie.probes.ci import _IMAGE_BUILD_MARKERS

    assert _IMAGE_BUILD_MARKERS == (
        ("docker build", "run"),
        ("docker buildx", "run"),
        ("docker/build-push-action", "uses"),
    )


# ---------- T-18: two-run determinism (AC-23) ---------------------------


def test_two_runs_byte_equal(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: docker build .\n"
        "      - run: echo ${{ secrets.B }} ${{ secrets.A }}\n",
    )
    (tmp_path / ".gitlab-ci.yml").write_text("script: ['npm test']\n")
    a = _run(tmp_path).schema_slice
    b = _run(tmp_path).schema_slice
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------- T-19: workflow_files lex-sorted (AC-23) ---------------------


def test_workflow_files_sorted_lex(tmp_path: Path) -> None:
    for n in ["zeta.yml", "alpha.yml", "mike.yml"]:
        _write_workflow(tmp_path, "jobs: {}\n", name=n)
    s = _run(tmp_path).schema_slice["ci"]
    assert s["workflow_files"] == ["alpha.yml", "mike.yml", "zeta.yml"]


# ---------- T-20: pure helper unit tests (AC-26) ------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", []),
        ("${{ secrets.A }}", ["A"]),
        ("${{ secrets.A }} ${{ secrets.B }} ${{ secrets.A }}", ["A", "B"]),
        ("${{ env.FOO }}", []),
        ("${{ Secrets.X }}", []),
    ],
)
def test_extract_secret_names_pure(text: str, expected: list[str]) -> None:
    from codegenie.probes.ci import _extract_secret_names

    assert _extract_secret_names(text) == expected


def test_select_provider_pure_first_match_wins() -> None:
    from codegenie.probes.ci import _select_provider

    p, rest = _select_provider(
        ["github_actions", "circleci"],
        ("github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"),
    )
    assert p == "github_actions"
    assert rest == ["circleci"]


def test_select_provider_pure_empty_input() -> None:
    from codegenie.probes.ci import _select_provider

    p, rest = _select_provider(
        [],
        ("github_actions", "gitlab_ci", "circleci", "jenkins", "azure_pipelines"),
    )
    assert p is None
    assert rest == []


def test_extract_run_strings_pure() -> None:
    from codegenie.probes.ci import _extract_run_strings

    workflow: dict[str, Any] = {
        "jobs": {
            "build": {
                "steps": [
                    {"run": "npm test"},
                    {"uses": "actions/checkout@v4"},
                    {"run": "echo hi"},
                ]
            }
        }
    }
    assert _extract_run_strings(workflow) == ["npm test", "echo hi"]


def test_extract_uses_strings_pure() -> None:
    from codegenie.probes.ci import _extract_uses_strings

    workflow: dict[str, Any] = {
        "jobs": {
            "b": {
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"run": "x"},
                    {"uses": "docker/build-push-action@v5"},
                ]
            }
        }
    }
    assert _extract_uses_strings(workflow) == [
        "actions/checkout@v4",
        "docker/build-push-action@v5",
    ]


def test_detect_image_build_pure_first_hit_wins() -> None:
    from codegenie.probes.ci import _detect_image_build

    builds, cmd = _detect_image_build(
        ["docker run x", "docker buildx build .", "docker build ."], []
    )
    assert builds is True
    # `docker build` is index 0 in _IMAGE_BUILD_MARKERS — first match in the
    # marker table wins (not first in the runs list).
    assert cmd is not None
    assert "docker build" in cmd


def test_detect_image_build_pure_uses_branch() -> None:
    from codegenie.probes.ci import _detect_image_build

    builds, cmd = _detect_image_build([], ["docker/build-push-action@v5"])
    assert builds is True
    assert cmd is not None and "docker/build-push-action" in cmd


def test_detect_image_build_pure_no_match() -> None:
    from codegenie.probes.ci import _detect_image_build

    builds, cmd = _detect_image_build(["docker run hello"], ["actions/checkout@v4"])
    assert builds is False
    assert cmd is None


# ---------- T-21: sub-schema rejects unknown field (AC-3) ---------------


def test_subschema_rejects_unknown_field_at_root() -> None:
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    envelope = _minimal_envelope_with_ci(rogue_root=True)
    with pytest.raises(SchemaValidationError) as ei:
        validate(envelope)
    assert "rogue_field" in str(ei.value)


def test_subschema_additional_properties_false_at_every_object() -> None:
    """AC-3 — every type:object node must declare additionalProperties:false."""
    schema = json.loads(Path("src/codegenie/schema/probes/ci.schema.json").read_text())

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict) and node.get("type") == "object":
            assert node.get("additionalProperties") is False, (
                f"missing additionalProperties: false at {path}"
            )
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}/{i}")

    walk(schema, "")


# ---------- T-22: envelope optional at probes level (AC-3 + ADR-0010) ----


def test_envelope_optional_at_probes_level() -> None:
    """Envelope's properties.probes.required does NOT list `ci`."""
    env = json.loads(Path("src/codegenie/schema/repo_context.schema.json").read_text())
    required = env.get("properties", {}).get("probes", {}).get("required", [])
    assert "ci" not in required


def test_no_ci_envelope_validates() -> None:
    """A non-Node, non-CI envelope MUST validate (slice absent)."""
    from codegenie.schema.validator import validate

    envelope = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {
            "language_detection": {
                "language_stack": {
                    "counts": {"go": 1},
                    "primary": "go",
                    "framework_hints": [],
                    "monorepo": None,
                }
            }
        },
    }
    validate(envelope)


# ---------- AC-21 raw artifact records offending path --------------------


def test_workflow_parse_error_path_recorded_in_raw_artifact(tmp_path: Path) -> None:
    """CN-1 resolution: bare warning ID; offending path goes to raw/ci.json."""
    _write_workflow(tmp_path, "jobs: {\n", name="bad.yml")
    _write_workflow(
        tmp_path,
        "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        name="good.yml",
    )
    out = _run(tmp_path)
    # at least one raw artifact written
    assert out.raw_artifacts, "expected raw/ci.json artifact for parse-error provenance"
    raw = json.loads(out.raw_artifacts[0].read_text())
    parse_errors = raw.get("parse_errors") or []
    paths = [e.get("path") for e in parse_errors]
    assert any(p and "bad.yml" in p for p in paths)
