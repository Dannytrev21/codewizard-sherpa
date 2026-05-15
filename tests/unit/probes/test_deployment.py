"""Red tests for S4-02 — ``DeploymentProbe``.

Pins AC-1..AC-47 from
``docs/phases/01-context-gather-layer-a-node/stories/S4-02-deployment-probe.md``.

Helpers are inlined (matches the S2-02 / S3-05 / S4-01 sibling idiom). The
probe's ``run()`` is async; tests use ``asyncio.run`` directly to keep
``pytest-asyncio`` out of the dependency surface (matches
``test_node_build_system.py:93`` and ``test_ci.py:59``).

Pins: DeploymentProbe records evidence, not judgments (ADR-0011 + production
ADR-0005); zip-slip refused at probe level (load-bearing); multi-env Helm as
environments list (ADR-0012); no helm/kustomize/terraform subprocess
invocation (ADR-0011); warning IDs match ADR-0007 pattern (BARE — no
``:<path>`` suffixes per CN-1).

Traces to: phase-arch-design.md §"Component design" #6 + §"Data model" + §"Edge
cases" rows 4 + 15.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

import pytest

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------- helpers ----------------------------------------------------------


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"javascript": 1},
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
    from codegenie.probes.deployment import DeploymentProbe

    return asyncio.run(DeploymentProbe().run(_snapshot(root), _ctx(root)))


# ---------- T-CONTRACT (AC-1, AC-2, AC-3) ------------------------------------


def test_probe_module_and_class_exist() -> None:
    """AC-1. Module + class both importable."""
    from codegenie.probes import deployment as dp
    from codegenie.probes.deployment import DeploymentProbe

    assert dp is not None
    assert DeploymentProbe is not None


def test_probe_contract_attributes_match_arch() -> None:
    """AC-2 + AC-3. Class attrs + declared_inputs verbatim vs arch line 545."""
    from codegenie.probes.deployment import DeploymentProbe as P

    assert P.name == "deployment"
    assert P.layer == "A"
    assert P.tier == "base"
    assert P.applies_to_languages == ["*"]
    assert P.applies_to_tasks == ["*"]
    assert P.requires == []
    assert P.timeout_seconds == 15
    assert isinstance(P.version, str) and re.match(r"^\d+\.\d+\.\d+$", P.version)
    assert P.version == "1.0.0"
    assert isinstance(P.declared_inputs, list)
    assert all(isinstance(g, str) for g in P.declared_inputs)
    expected = [
        "deploy/**/*.yaml",
        "deploy/**/*.yml",
        "k8s/**/*.yaml",
        "k8s/**/*.yml",
        "kubernetes/**/*.yaml",
        "Chart.yaml",
        "values.yaml",
        "values-*.yaml",
        "kustomization.yaml",
        "kustomization.yml",
        "helm/**/*",
        "charts/**/*",
        "*.tf",
    ]
    assert P.declared_inputs == expected


# ---------- T-REG (AC-4, AC-5) -----------------------------------------------


def test_additive_import_in_probes_init() -> None:
    """AC-4. probes/__init__.py imports deployment."""
    src = Path("src/codegenie/probes/__init__.py").read_text()
    assert "deployment" in src


@pytest.mark.parametrize(
    "langs",
    [
        frozenset({"go"}),
        frozenset({"javascript"}),
        frozenset({"python"}),
        frozenset({"javascript", "typescript"}),
        frozenset(),
    ],
)
def test_registry_membership_across_all_languages(langs: frozenset[str]) -> None:
    """AC-5. applies_to_languages = ["*"] ⇒ probe runs everywhere."""
    from codegenie.probes import default_registry
    from codegenie.probes.deployment import DeploymentProbe

    assert DeploymentProbe in default_registry.all_probes()
    assert DeploymentProbe in default_registry.for_task("*", langs)


# ---------- T-SHAPE (AC-11 → AC-18, ADR-0012 four-shape coverage) ------------


def test_helm_single_env_image_reference(tmp_path: Path) -> None:
    """AC-11 (state a). values.yaml only → image_reference set, environments empty."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1.0\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v1.2.3\n")
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == "helm"
    assert s["image_reference"] == {"path": "image.repository", "value": "ghcr.io/me/app:v1.2.3"}
    assert s["environments"] == []
    assert out.confidence == "high"


def test_helm_multi_env_emits_environments_list(tmp_path: Path) -> None:
    """AC-12 (state b). values.yaml + values-prod + values-staging."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: base\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v1\n")
    (tmp_path / "values-staging.yaml").write_text(
        "image:\n  repository: ghcr.io/me/app\n  tag: v0\n"
    )
    s = _run(tmp_path).schema_slice["deployment"]
    names = sorted(e["name"] for e in s["environments"])
    assert names == ["prod", "staging"]
    assert s["image_reference"] is not None
    for entry in s["environments"]:
        assert entry["image_reference"] is not None


def test_helm_no_baseline_nullable_primary(tmp_path: Path) -> None:
    """AC-13 (state c). Only values-prod.yaml → image_reference: None, env list non-empty."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["image_reference"] is None
    assert len(s["environments"]) == 1
    assert s["environments"][0]["name"] == "prod"


def test_helm_12_environments(tmp_path: Path) -> None:
    """AC-14 (edge case 15). 12 envs; confidence high; each entry validates strict."""
    from codegenie.schema.validator import validate as _validate

    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    for i in range(12):
        (tmp_path / f"values-env{i:02d}.yaml").write_text(f"image:\n  repository: x\n  tag: v{i}\n")
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert len(s["environments"]) == 12
    assert out.confidence == "high"
    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())
    for entry in s["environments"]:
        _validate.environment_entry(entry, schema)  # type: ignore[attr-defined]


def test_helm_values_filename_unrecognized_uses_full_stem(tmp_path: Path) -> None:
    """AC-15. values.prod.yaml (dot, not dash) → name='values.prod', warning."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.prod.yaml").write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice["deployment"]
    assert "values.prod" in [e["name"] for e in s["environments"]]
    assert "helm.values_filename_unrecognized" in s["warnings"]


def test_helm_chart_yaml_only_no_values(tmp_path: Path) -> None:
    """AC-16. Chart.yaml alone → low confidence + helm.no_values_files warning."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == "helm"
    assert s["chart_path"] == "Chart.yaml"
    assert s["image_reference"] is None
    assert s["environments"] == []
    assert "helm.no_values_files" in s["warnings"]
    assert out.confidence == "low"


@pytest.mark.parametrize(
    "values_body,expected_path,expected_value",
    [
        ('image: "ghcr.io/me/app:v1.2.3"\n', "image", "ghcr.io/me/app:v1.2.3"),
        (
            "image:\n  repository: ghcr.io/me/app\n  tag: v1.2.3\n",
            "image.repository",
            "ghcr.io/me/app:v1.2.3",
        ),
        ("image:\n  repository: ghcr.io/me/app\n", "image.repository", "ghcr.io/me/app"),
    ],
)
def test_image_ref_extraction_shapes(
    tmp_path: Path, values_body: str, expected_path: str, expected_value: str
) -> None:
    """AC-17. Three image-ref shapes; case (d) tested separately."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text(values_body)
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["image_reference"] == {"path": expected_path, "value": expected_value}


def test_image_ref_tag_only_no_repo_returns_none(tmp_path: Path) -> None:
    """AC-17 case (d). image.tag alone, no repository → None."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  tag: v1\n")
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["image_reference"] is None


@pytest.mark.parametrize(
    "baseline,env_file",
    [
        ("values.yaml", "values-prod.yaml"),
        ("values.yml", "values-prod.yml"),
        ("values.yaml", "values-prod.yml"),
    ],
)
def test_helm_yml_extension_variants(tmp_path: Path, baseline: str, env_file: str) -> None:
    """AC-18. .yml variants behave identically to .yaml."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / baseline).write_text("image:\n  repository: x\n  tag: base\n")
    (tmp_path / env_file).write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["type"] == "helm"
    assert any(e["name"] == "prod" for e in s["environments"])


# ---------- T-TYPE-PRECEDENCE (AC-19 → AC-23) --------------------------------


def test_deployment_type_alias_matches_schema_enum() -> None:
    """AC-19. Schema enum equivalence to _DEPLOYMENT_TYPE Literal arms."""
    from codegenie.probes import deployment as dp

    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())
    enum = schema["properties"]["deployment"]["properties"]["type"]["enum"]
    assert set(get_args(dp._DEPLOYMENT_TYPE)) == set(enum)


def test_deployment_detectors_precedence_tuple() -> None:
    """AC-20. Open/Closed at file boundary; precedence pinned."""
    from codegenie.probes import deployment as dp

    types = tuple(t for t, _ in dp._DEPLOYMENT_DETECTORS)
    assert types == ("helm", "kustomize", "raw", "terraform")


def test_deployment_parsers_dispatch_keys() -> None:
    """AC-21. Dispatch registry covers every Literal arm."""
    from codegenie.probes import deployment as dp

    assert dp._DEPLOYMENT_PARSERS.keys() == set(get_args(dp._DEPLOYMENT_TYPE))


@pytest.mark.parametrize(
    "markers,primary,others",
    [
        (("Chart.yaml", "main.tf"), "helm", ["terraform"]),
        (("Chart.yaml", "kustomization.yaml"), "helm", ["kustomize"]),
        (("kustomization.yaml", "main.tf"), "kustomize", ["terraform"]),
        (("Chart.yaml", "kustomization.yaml", "main.tf"), "helm", ["kustomize", "terraform"]),
    ],
)
def test_multi_type_detection_retains_all_evidence(
    tmp_path: Path, markers: tuple[str, ...], primary: str, others: list[str]
) -> None:
    """AC-22. Highest-precedence wins; terraform_files survives even when type != terraform."""
    for m in markers:
        if m == "Chart.yaml":
            (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
            (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
        elif m == "kustomization.yaml":
            (tmp_path / "kustomization.yaml").write_text("resources: []\n")
        elif m == "main.tf":
            (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == primary
    if "terraform" in others or primary == "terraform":
        assert "main.tf" in s["terraform_files"]
    assert "deployment.multi_type" in s["warnings"]
    assert out.confidence == "low"


def test_repo_with_no_deployment_artifacts_emits_type_none(tmp_path: Path) -> None:
    """AC-23. Slice IS emitted with type='none'."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.go").write_text("package main\nfunc main() {}\n")
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == "none"
    assert s["image_reference"] is None
    assert s["environments"] == []
    assert s["terraform_files"] == []
    assert s["exposed_ports"] == []
    assert s["required_env_vars"] == []
    assert s["kustomization_resource_path_outside_repo"] is False
    assert s["security_context"] is None
    assert s["chart_path"] is None
    assert s["warnings"] == []
    assert out.confidence == "high"
    assert out.errors == []


# ---------- T-ZIP-SLIP (AC-24 → AC-27) — LOAD-BEARING -----------------------


def test_kustomize_resource_outside_repo_refused(tmp_path: Path) -> None:
    """AC-24. Sentinel-exfiltration zip-slip test."""
    sentinel = tmp_path.parent / "SENTINEL_LEAK.yaml"
    sentinel.write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: leak}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 31337}]}]}}}\n"
    )
    try:
        (tmp_path / "kustomization.yaml").write_text(
            f"resources:\n  - ../{sentinel.name}\n  - deployment.yaml\n"
        )
        (tmp_path / "deployment.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: x}\n"
            "spec: {template: {spec: {containers: [{name: c, image: i,"
            " ports: [{containerPort: 8080}]}]}}}\n"
        )
        s = _run(tmp_path).schema_slice["deployment"]
        assert 31337 not in s["exposed_ports"], "zip-slip exfiltration: sentinel reached slice"
        assert s["kustomization_resource_path_outside_repo"] is True
        assert "kustomization.resource_outside_repo" in s["warnings"]
        assert 8080 in s["exposed_ports"]
    finally:
        sentinel.unlink(missing_ok=True)


def test_kustomize_symlink_resource_refused(tmp_path: Path) -> None:
    """AC-25. Defense in depth — either containment or O_NOFOLLOW refuses."""
    outside = tmp_path.parent / "outside.yaml"
    outside.write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: leak}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 31337}]}]}}}\n"
    )
    try:
        (tmp_path / "linked.yaml").symlink_to(outside)
        (tmp_path / "kustomization.yaml").write_text("resources:\n  - linked.yaml\n")
        s = _run(tmp_path).schema_slice["deployment"]
        assert 31337 not in s["exposed_ports"], "symlink-via-resource leaked"
        assert "kustomization.resource_outside_repo" in s["warnings"] or any(
            "symlink" in w for w in s["warnings"]
        )
    finally:
        outside.unlink(missing_ok=True)


def test_kustomize_overlay_file_count_capped(tmp_path: Path) -> None:
    """AC-26 (a). 60 resource files → file-cap warning."""
    (tmp_path / "kustomization.yaml").write_text(
        "resources:\n" + "".join(f"  - r{i}.yaml\n" for i in range(60))
    )
    for i in range(60):
        (tmp_path / f"r{i}.yaml").write_text(
            f"apiVersion: apps/v1\nkind: Deployment\nmetadata: {{name: r{i}}}\n"
            f"spec: {{template: {{spec: {{containers: [{{name: c, image: i}}]}}}}}}\n"
        )
    s = _run(tmp_path).schema_slice["deployment"]
    assert "kustomization.file_cap_exceeded" in s["warnings"]


def test_walk_overlays_pure_helper_caps(tmp_path: Path) -> None:
    """AC-27. Pure helper unit-tested in isolation."""
    from codegenie.probes.deployment import _walk_overlays

    (tmp_path / "kustomization.yaml").write_text(
        "resources:\n" + "".join(f"  - r{i}.yaml\n" for i in range(60))
    )
    paths, warnings = _walk_overlays(
        tmp_path.resolve(), tmp_path / "kustomization.yaml", max_files=50
    )
    assert len(paths) <= 50
    assert "kustomization.file_cap_exceeded" in warnings


# ---------- T-RAW (AC-28 → AC-32) -------------------------------------------


@pytest.mark.parametrize(
    "kind,should_extract",
    [
        ("Deployment", True),
        ("StatefulSet", True),
        ("DaemonSet", True),
        ("Pod", True),
        ("Service", False),
        ("ConfigMap", False),
        ("Secret", False),
        ("Ingress", False),
        ("Job", False),
        ("CronJob", False),
        ("ReplicaSet", False),
        ("Namespace", False),
    ],
)
def test_raw_kind_filter_total_ordering(tmp_path: Path, kind: str, should_extract: bool) -> None:
    """AC-28. Filter to {Deployment, StatefulSet, DaemonSet, Pod}; nothing else."""
    (tmp_path / "deploy").mkdir()
    if kind in ("Deployment", "StatefulSet", "DaemonSet"):
        body = (
            f"apiVersion: apps/v1\nkind: {kind}\nmetadata: {{name: x}}\n"
            f"spec: {{template: {{spec: {{containers: [{{name: c, image: i,"
            f" ports: [{{containerPort: 9090}}]}}]}}}}}}\n"
        )
    elif kind == "Pod":
        body = (
            "apiVersion: v1\nkind: Pod\nmetadata: {name: x}\n"
            "spec: {containers: [{name: c, image: i,"
            " ports: [{containerPort: 9090}]}]}\n"
        )
    else:
        body = (
            f"apiVersion: v1\nkind: {kind}\nmetadata: {{name: x}}\n"
            "spec: {ports: [{port: 9090}]}\n"
        )
    (tmp_path / "deploy" / "x.yaml").write_text(body)
    s = _run(tmp_path).schema_slice["deployment"]
    if should_extract:
        assert 9090 in s["exposed_ports"], f"{kind} should be processed"
    else:
        assert 9090 not in s["exposed_ports"], f"{kind} should NOT be processed"


def test_raw_only_non_workload_kinds(tmp_path: Path) -> None:
    """AC-29. Marker matched but no workloads → low + raw_no_workloads."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "x.yaml").write_text(
        "---\napiVersion: v1\nkind: Service\nmetadata: {name: a}"
        "\nspec: {ports: [{port: 80}]}\n"
        "---\napiVersion: v1\nkind: ConfigMap\nmetadata: {name: b}\ndata: {x: y}\n"
    )
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == "raw"
    assert s["exposed_ports"] == []
    assert "deployment.raw_no_workloads" in s["warnings"]
    assert out.confidence == "low"


def test_exposed_ports_sorted_and_deduped(tmp_path: Path) -> None:
    """AC-30. Sorted ascending, deduped."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "a.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: a}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 8080}, {containerPort: 443}, {containerPort: 8080}]}]}}}\n"
    )
    (tmp_path / "deploy" / "b.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: b}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 80}, {containerPort: 443}]}]}}}\n"
    )
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["exposed_ports"] == [80, 443, 8080]


def test_required_env_vars_sorted_and_deduped_names_only(tmp_path: Path) -> None:
    """AC-31. Names only (facts not judgments); sorted alpha; deduped."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "d.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: d}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " env: [{name: DB_URL, value: secret_value}, {name: API_KEY},"
        " {name: DB_URL}]}]}}}\n"
    )
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["required_env_vars"] == ["API_KEY", "DB_URL"]
    assert "secret_value" not in json.dumps(s)


def test_security_context_verbatim_passthrough(tmp_path: Path) -> None:
    """AC-32. security_context passes through verbatim."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "x.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: x}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " securityContext: {runAsNonRoot: true, runAsUser: 1000,"
        " capabilities: {drop: [ALL]}}}]}}}\n"
    )
    s = _run(tmp_path).schema_slice["deployment"]
    assert s["security_context"] == {
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "capabilities": {"drop": ["ALL"]},
    }


# ---------- T-TERRAFORM (AC-33, AC-34) ---------------------------------------


def test_terraform_paths_relative_to_root_forward_slashes(tmp_path: Path) -> None:
    """AC-33. POSIX-style relative paths; no abs; no `./` prefix; no backslashes."""
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    (tmp_path / "variables.tf").write_text('variable "z" {}')
    (tmp_path / "modules" / "network").mkdir(parents=True)
    (tmp_path / "modules" / "network" / "vpc.tf").write_text('variable "w" {}')
    s = _run(tmp_path).schema_slice["deployment"]
    assert sorted(s["terraform_files"]) == ["main.tf", "modules/network/vpc.tf", "variables.tf"]
    for p in s["terraform_files"]:
        assert not p.startswith("/")
        assert not p.startswith("./")
        assert "\\" not in p


def test_terraform_alone_low_confidence(tmp_path: Path) -> None:
    """AC-34. Terraform alone → low + terraform.paths_only."""
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    assert s["type"] == "terraform"
    assert out.confidence == "low"
    assert "terraform.paths_only" in s["warnings"]


# ---------- T-ADR-0011 STATIC (AC-35, AC-36, AC-37) -------------------------


def test_probe_imports_no_forbidden_modules() -> None:
    """AC-35. AST-walked import check; not literal-string grep."""
    src = Path("src/codegenie/probes/deployment.py").read_text()
    tree = ast.parse(src)
    forbidden = {"hcl2", "python_hcl2", "kubernetes", "pyhelm", "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden, f"forbidden import-from: {node.module}"


def test_probe_no_subprocess_calls() -> None:
    """AC-36. No subprocess work at all (unlike NodeBuildSystemProbe)."""
    src = Path("src/codegenie/probes/deployment.py").read_text()
    assert "run_allowlisted" not in src
    assert "os.system" not in src
    assert "os.execv" not in src
    assert "Popen" not in src
    assert "shutil.which" not in src


def test_allowed_binaries_invariant_unchanged() -> None:
    """AC-37. Phase-1-end invariant: ALLOWED_BINARIES = {'git','node'}; ADR-0011."""
    from codegenie.exec import ALLOWED_BINARIES

    assert ALLOWED_BINARIES == {"git", "node"}


# ---------- T-WARNING-IDS (AC-38, AC-39, AC-40) -----------------------------


def test_warning_ids_match_adr_0007() -> None:
    """AC-38. _WARNING_IDS verbatim + ADR-0007 conformance loop."""
    from codegenie.probes import deployment as dp

    expected = frozenset(
        {
            "kustomization.resource_outside_repo",
            "kustomization.depth_cap_exceeded",
            "kustomization.file_cap_exceeded",
            "helm.values_file_parse_error",
            "helm.values_filename_unrecognized",
            "helm.no_values_files",
            "deployment.multi_type",
            "deployment.raw_no_workloads",
            "terraform.paths_only",
        }
    )
    assert dp._WARNING_IDS == expected
    for w in dp._WARNING_IDS:
        assert ADR_0007.match(w), f"ADR-0007 violation: {w!r}"


def test_error_ids_match_adr_0007() -> None:
    """AC-40. _ERROR_IDS verbatim + ADR-0007."""
    from codegenie.probes import deployment as dp

    expected = frozenset(
        {
            "deployment.size_cap_exceeded",
            "deployment.depth_cap_exceeded",
            "deployment.malformed_yaml",
            "deployment.symlink_refused",
        }
    )
    assert dp._ERROR_IDS == expected
    for e in dp._ERROR_IDS:
        assert ADR_0007.match(e), f"ADR-0007 violation: {e!r}"


def test_values_file_partial_failure_still_emits_safe_envs(tmp_path: Path) -> None:
    """AC-39. Per-file degradation; BARE warning ID; offending path in raw/."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  tag: v1\n")
    (tmp_path / "values-staging.yaml").write_text("image:\n  tag: [\n")  # malformed
    out = _run(tmp_path)
    s = out.schema_slice["deployment"]
    names = sorted(e["name"] for e in s["environments"])
    assert "prod" in names
    assert "staging" not in names
    assert "helm.values_file_parse_error" in s["warnings"]
    for w in s["warnings"]:
        assert ADR_0007.match(w), f"non-bare warning: {w!r}"
    assert out.confidence == "low"


# ---------- T-DETERMINISM + CONFIDENCE (AC-41, AC-42, AC-43) ----------------


def test_two_runs_byte_equal(tmp_path: Path) -> None:
    """AC-41. Deterministic two-run byte-equal."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    for i in range(5):
        (tmp_path / f"values-env{i}.yaml").write_text(f"image:\n  tag: v{i}\n")
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    a = _run(tmp_path).schema_slice["deployment"]
    b = _run(tmp_path).schema_slice["deployment"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_demote_helper_monotone() -> None:
    """AC-43. _demote is monotone (downgrade only)."""
    from codegenie.probes.deployment import _demote

    assert _demote("low", "high") == "low"
    assert _demote("high", "low") == "low"
    assert _demote("high", "medium") == "medium"
    assert _demote("medium", "low") == "low"
    assert _demote("low", "low") == "low"


# ---------- T-SCHEMA REJECTION (AC-7, AC-8, AC-9) ---------------------------


@pytest.mark.parametrize(
    "_pointer,build",
    [
        ("/probes/deployment/rogue_root", lambda s: {**s, "rogue_root": True}),
        (
            "/probes/deployment/image_reference/rogue",
            lambda s: {**s, "image_reference": {**s["image_reference"], "rogue": True}},
        ),
        (
            "/probes/deployment/environments/0/rogue",
            lambda s: {**s, "environments": [{**s["environments"][0], "rogue": True}]},
        ),
        (
            "/probes/deployment/environments/0/image_reference/rogue",
            lambda s: {
                **s,
                "environments": [
                    {
                        **s["environments"][0],
                        "image_reference": {
                            **s["environments"][0]["image_reference"],
                            "rogue": True,
                        },
                    }
                ],
            },
        ),
    ],
)
def test_schema_rejects_extra_field_at_every_nesting_level(
    _pointer: str, build: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    """AC-8. additionalProperties: false at every nesting level except security_context."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    base_slice: dict[str, Any] = {
        "type": "helm",
        "chart_path": "Chart.yaml",
        "image_reference": {"path": "image.repository", "value": "x"},
        "environments": [{"name": "prod", "image_reference": {"path": "image.tag", "value": "v1"}}],
        "security_context": None,
        "exposed_ports": [],
        "required_env_vars": [],
        "terraform_files": [],
        "kustomization_resource_path_outside_repo": False,
        "warnings": [],
    }
    envelope = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        # Slice merge wraps the payload as `{"deployment": <slice>}`; mirror at
        # validation time (matches `_minimal_envelope_with_ci` precedent).
        "probes": {"deployment": {"deployment": build(base_slice)}},
    }
    with pytest.raises(SchemaValidationError) as ei:
        validate(envelope)
    assert "rogue" in str(ei.value)


def test_every_object_node_has_additional_properties_false_except_security_context() -> None:
    """AC-7. Walk the schema; security_context is the documented exception."""
    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())

    def _walk(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                # `security_context` and any nested objects underneath it are
                # the documented ADR-0004 exception (Kubernetes SecurityContext
                # is open-shape — verbatim pass-through). Everything else is strict.
                if "/security_context" in pointer:
                    assert node.get("additionalProperties") is True, (
                        f"security_context tree must be loose at {pointer}; "
                        f"got {node.get('additionalProperties')!r}"
                    )
                else:
                    assert node.get("additionalProperties") is False, (
                        f"additionalProperties: false missing at {pointer}"
                    )
            for k, v in node.items():
                _walk(v, f"{pointer}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{pointer}/{i}")

    _walk(schema, "")


def test_deployment_slice_optional_at_envelope() -> None:
    """AC-9. ADR-0010: non-deployment repo validates with probes.deployment absent."""
    from codegenie.schema.validator import validate

    envelope = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {},
    }
    validate(envelope)


# ---------- T-CONFIDENCE-MATRIX (AC-42) -------------------------------------


def _fix_helm_single(p: Path) -> None:
    (p / "Chart.yaml").write_text("apiVersion: v2\nname: a\nversion: 0.1\n")
    (p / "values.yaml").write_text("image:\n  repository: x\n  tag: v1\n")


def _fix_helm_multi_env(p: Path) -> None:
    _fix_helm_single(p)
    (p / "values-prod.yaml").write_text("image:\n  tag: v1\n")


def _fix_helm_no_values(p: Path) -> None:
    (p / "Chart.yaml").write_text("apiVersion: v2\nname: a\nversion: 0.1\n")


def _fix_terraform_alone(p: Path) -> None:
    (p / "main.tf").write_text('resource "x" "y" {}')


def _fix_multi_type(p: Path) -> None:
    _fix_helm_single(p)
    _fix_terraform_alone(p)


def _fix_zip_slip(p: Path) -> None:
    (p / "kustomization.yaml").write_text("resources:\n  - ../outside.yaml\n")


def _fix_raw_no_workloads(p: Path) -> None:
    (p / "deploy").mkdir()
    (p / "deploy" / "x.yaml").write_text(
        "apiVersion: v1\nkind: Service\nmetadata: {name: a}\nspec: {ports: [{port: 80}]}\n"
    )


def _fix_none(p: Path) -> None:
    (p / "README.md").write_text("# nothing\n")


_FIXTURES = {
    "helm_single_clean": _fix_helm_single,
    "helm_multi_env_clean": _fix_helm_multi_env,
    "helm_no_values_files": _fix_helm_no_values,
    "terraform_alone": _fix_terraform_alone,
    "multi_type_helm_plus_terraform": _fix_multi_type,
    "kustomize_zip_slip_detected": _fix_zip_slip,
    "raw_no_workloads": _fix_raw_no_workloads,
    "none": _fix_none,
}


@pytest.mark.parametrize(
    "name,expected_conf,expected_warning",
    [
        ("helm_single_clean", "high", None),
        ("helm_multi_env_clean", "high", None),
        ("helm_no_values_files", "low", "helm.no_values_files"),
        ("terraform_alone", "low", "terraform.paths_only"),
        ("multi_type_helm_plus_terraform", "low", "deployment.multi_type"),
        ("kustomize_zip_slip_detected", "low", "kustomization.resource_outside_repo"),
        ("raw_no_workloads", "low", "deployment.raw_no_workloads"),
        ("none", "high", None),
    ],
)
def test_confidence_outcomes_per_scenario(
    tmp_path: Path, name: str, expected_conf: str, expected_warning: str | None
) -> None:
    """AC-42. Confidence × warning matrix."""
    _FIXTURES[name](tmp_path)
    out = _run(tmp_path)
    assert out.confidence == expected_conf, (
        f"{name}: expected {expected_conf}, got {out.confidence}"
    )
    if expected_warning:
        assert expected_warning in out.schema_slice["deployment"]["warnings"]


# ---------- T-PURE-HELPERS (AC-44, AC-45, AC-46) ----------------------------


def test_env_name_from_filename() -> None:
    """AC-44 helper. Pure: stem → (name, conforming?)."""
    from codegenie.probes.deployment import _env_name_from_filename

    assert _env_name_from_filename("values-prod.yaml") == ("prod", True)
    assert _env_name_from_filename("values-staging.yml") == ("staging", True)
    assert _env_name_from_filename("values.prod.yaml") == ("values.prod", False)
    assert _env_name_from_filename("values.yaml") == ("values", False)


def test_aggregate_exposed_ports() -> None:
    """AC-44 helper."""
    from codegenie.probes.deployment import _aggregate_exposed_ports

    containers = [
        {"ports": [{"containerPort": 8080}, {"containerPort": 443}]},
        {"ports": [{"containerPort": 8080}, {"containerPort": 80}]},
    ]
    assert _aggregate_exposed_ports(containers) == [80, 443, 8080]


def test_filter_k8s_kinds() -> None:
    """AC-44 helper."""
    from codegenie.probes.deployment import _filter_k8s_kinds

    docs = [{"kind": "Deployment"}, {"kind": "Service"}, {"kind": "Pod"}, {"kind": "Job"}]
    kinds = [d["kind"] for d in _filter_k8s_kinds(docs)]
    assert kinds == ["Deployment", "Pod"]


def test_parse_result_namedtuple_shape() -> None:
    """AC-45. _ParseResult NamedTuple discriminator-free dispatch contract."""
    from codegenie.probes.deployment import _ParseResult

    r = _ParseResult(slice_fragment={"type": "none"}, warnings=[], confidence_demote_to=None)
    assert r.slice_fragment == {"type": "none"}
    assert r.warnings == []
    assert r.confidence_demote_to is None
