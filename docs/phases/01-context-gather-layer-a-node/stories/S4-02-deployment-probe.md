# Story S4-02 — `DeploymentProbe` + sub-schema with zip-slip mitigation

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status:** Ready
**Effort:** L
**Depends on:** S1-03 (`safe_yaml.load` + `load_all`)
**ADRs honored:** ADR-0004 (`additionalProperties: false`), ADR-0007 (warning-ID pattern), ADR-0010 (Layer A slices optional), **ADR-0011 (no Helm render / no HCL parsing)**, **ADR-0012 (multi-env Helm as `environments: list` with nullable primary)**

## Context

`DeploymentProbe` populates the `deployment` slice (`localv2.md §5.1 A5`) by parsing Helm charts, Kustomize overlays, raw Kubernetes manifests, and Terraform paths. It is the largest probe in Step 4 because of the four-way file-marker branch and the load-bearing zip-slip mitigation. Three ADRs concentrate here:

1. **ADR-0011** — no `helm template` invocation, no `kustomize build` invocation, no `python-hcl2`, no `helm`/`kustomize`/`terraform` in `ALLOWED_BINARIES`. Phase 1 captures **evidence, not resolved state**: `image_reference` is a `{path, value}` block from values files; Kustomize follows `resources:` one level deep with containment check; Terraform is paths-only. Rendering and resolution are Phase 3+ Planner-time decisions (`production ADR-0011 recipe-first → RAG → LLM-fallback`).
2. **ADR-0012** — multi-environment Helm is emitted as `environments: list[EnvironmentEntry]` with a **nullable** primary `image_reference`. The singleton-vs-list disagreement (`localv2.md §5.1 A5` singleton example vs. reality of `values-prod.yaml` + `values-staging.yaml`) is resolved additively. Downstream Phase 3+ consumers handle the list shape from day one.
3. **ADR-0010** — `deployment` slice is **optional** at envelope level. A Go-only or Python-only repo with no Helm/Kustomize/k8s manifests produces a valid envelope with the `deployment` key absent (or present with `type: "none"` if the probe ran but found nothing).

The load-bearing piece is the **zip-slip mitigation** in Kustomize resource-following. A hostile `kustomization.yaml` with `resources: ["../../etc/passwd"]` must not cause the probe to read `/etc/passwd`. The defense is `Path.resolve()` (no string concat) followed by `Path.is_relative_to(repo_root)` on Python 3.12 or a manual ancestor-walk on 3.11. Path resolution outside `repo_root` → skip + `warnings: ["kustomization.resource_outside_repo"]` + slice field `kustomization_resource_path_outside_repo: true`. Valid resources in the same `kustomization.yaml` continue to be processed. The dedicated adversarial test (`tests/adv/test_zip_slip_kustomize.py`) lives in S5-03; this story ships the **unit-level** test against a hostile fixture so the defense is pinned at probe-PR-merge time, not three stories later.

Coverage carve-out (ADR-0005, declared in S4-04): `deployment.py` ships at 85/75. Many structurally-narrow branches (one per deployment type, one per Helm/Kustomize/raw/Terraform path) make uniform 90/80 gameable.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #6 DeploymentProbe` — full interface.
  - `../phase-arch-design.md §"Data model" DeploymentSlice` — Python-shape contract; `environments: list[EnvironmentEntry]`, `image_reference: ImageRefBlock | null`, `kustomization_resource_path_outside_repo: bool`, `terraform_files: list[str]` (paths-only).
  - `../phase-arch-design.md §"Edge cases"` row 4 (zip-slip) and row 15 (12-env Helm chart).
  - `../phase-arch-design.md §"Open questions deferred to implementation"` #5 (no Helm rendering) and #6 (multi-env consumer contract).
- **Phase ADRs:**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — root + every nested block (`EnvironmentEntry`, `ImageRefBlock`, etc.) is strict.
  - `../ADRs/0005-coverage-carve-outs-deployment-ci.md` — module floor 85/75.
  - `../ADRs/0007-warnings-id-pattern.md` — `kustomization.resource_outside_repo`, `helm.values_file_parse_error`, `terraform.paths_only`.
  - **`../ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md`** — explicit anti-scope this story honors.
  - **`../ADRs/0012-multi-environment-helm-as-list-with-nullable-primary.md`** — the data-model commitment.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — envelope-level optionality.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — facts not judgments; no resolution of rendered values.
  - `../../../production/adrs/0011-recipe-first-planning.md` (referenced by ADR-0011) — Helm rendering deferred to Planner.
- **Source design:**
  - `../final-design.md §"Components" #6` — multi-env list resolution.
  - `../final-design.md §"Failure modes & recovery"` row 13 — schema accepts both shapes; consumer-contract test in S5-05.
  - `../localv2.md §5.1 A5` — the `deployment` slice contract this honors (singleton example preserved via nullable primary).
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (S1-03) — `load` and `load_all` with `O_NOFOLLOW`, size cap, depth 64.
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC.
  - `src/codegenie/errors.py` (S1-01) — `MalformedYAMLError`, `SizeCapExceeded`, `DepthCapExceeded`.
- **External docs:**
  - Helm Chart spec (`Chart.yaml` + `values.yaml` + `values-<env>.yaml`).
  - Kustomize `kustomization.yaml` reference (`resources`, `patches`, `bases`).
  - Kubernetes manifest `kind: Deployment | StatefulSet | DaemonSet | Pod` + `spec.template.spec.containers[].image` / `.securityContext` / `.ports` / `.env` / `.envFrom`.

## Goal

Ship a deterministic `DeploymentProbe` that detects type (Helm / Kustomize / raw / Terraform / none), parses Helm `Chart.yaml` + `values*.yaml` into `image_reference` (nullable) + `environments: list`, resolves Kustomize `resources:` one level deep with zip-slip containment, extracts `image`/`securityContext`/`ports`/`env`/`envFrom` from `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}` raw manifests, lists Terraform `*.tf` files by path only, and ships a strict sub-schema honoring ADR-0012's two-field shape.

## Acceptance criteria

- [ ] `src/codegenie/probes/deployment.py` exists; `DeploymentProbe(Probe)` declares `name = "deployment"`, `layer = "A"`, `tier = "base"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `timeout_seconds = 15`, `version: str`, and `declared_inputs` per `phase-arch-design.md §"Component design" #6`.
- [ ] `src/codegenie/schema/probes/deployment.schema.json` exists, Draft 2020-12, declares `additionalProperties: false` at root and at every nested block (`EnvironmentEntry`, `ImageRefBlock`, `security_context` if not `additionalProperties: true`-style), declares optional at envelope level, validates the `phase-arch-design.md §"Data model" DeploymentSlice` shape, and ships **both** `image_reference: ImageRefBlock | null` (singleton, nullable) **and** `environments: list[EnvironmentEntry]` (additive, may be empty) per ADR-0012.
- [ ] Red unit test exists at `tests/unit/probes/test_deployment.py` covering the four ADR-0012 shape permutations: (a) `values.yaml` only → `image_reference` set, `environments: []`; (b) `values.yaml` + `values-prod.yaml` + `values-staging.yaml` → primary set, `environments` 2 entries; (c) `values-prod.yaml` only (no baseline) → `image_reference: null`, `environments` 1 entry; (d) 12 `values-*.yaml` files → `environments` 12 entries, `confidence: high`, each entry's `additionalProperties: false` continues to bind (12-env edge case).
- [ ] **Zip-slip unit test pinned at probe level** (not deferred to S5-03): `tests/unit/probes/test_deployment.py::test_kustomize_resource_outside_repo_refused` builds a fixture with `kustomization.yaml` containing `resources: ["../../etc/passwd", "deployment.yaml"]`; asserts (i) `/etc/passwd` is never opened (monkeypatch `pathlib.Path.read_text` or `os.open` and inspect calls), (ii) `kustomization_resource_path_outside_repo: true` in the slice, (iii) `warnings: ["kustomization.resource_outside_repo"]`, (iv) the valid `deployment.yaml` resource is still processed.
- [ ] Raw-manifest unit test: `tests/unit/probes/test_deployment.py::test_raw_manifest_kinds_filtered` — multi-document YAML with `Deployment` + `Service` + `ConfigMap`; assertion that only `Deployment` is processed for `image` / `securityContext` / `ports` / `env` / `envFrom` extraction (filter to `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}` per `phase-arch-design.md §"Component design" #6`).
- [ ] Terraform unit test: `tests/unit/probes/test_deployment.py::test_terraform_paths_only` — fixture with `main.tf` + `variables.tf`; assertion that `terraform_files == ["main.tf", "variables.tf"]` (or relative-path variant), `terraform_present: true`, **no parse attempted** (mock `python_hcl2` not imported — `grep "import hcl2"` over the probe file returns empty), `confidence: low` if Terraform-only (no other deployment type detected).
- [ ] No `helm`, `kustomize`, `terraform` binary invocations: grep for `run_allowlisted` in `deployment.py` returns empty; `exec.ALLOWED_BINARIES` at the end of Phase 1 remains `{"git", "node"}` (ADR-0011 compliance).
- [ ] `additionalProperties: false` rejection test (synthetic envelope with unknown field under `probes.deployment`, or unknown field under `environments[0]`) fails `SchemaValidator` at the right JSON Pointer.
- [ ] `src/codegenie/probes/__init__.py` adds one explicit additive import registering `DeploymentProbe`.
- [ ] Definition-of-done: `ruff check`, `ruff format --check`, `mypy --strict` on `deployment.py` pass; `pytest tests/unit/probes/test_deployment.py -q` passes; per-probe local coverage reported in PR body (≥ 85/75; the carve-out is the floor, not the target).

## Implementation outline

1. **Schema first.** Write `deployment.schema.json` mirroring `DeploymentSlice` from the data model. Both `image_reference` (nullable) and `environments` (list) are declared at the slice root; `EnvironmentEntry` has its own nested `additionalProperties: false`. The schema's `description` field documents the three-state distinction (per ADR-0012): single-env (`image_reference` set, `environments: []`), multi-env with baseline (`image_reference` set, `environments` non-empty), multi-env without baseline (`image_reference: null`, `environments` non-empty).
2. **Type detection (file marker):**
   ```python
   def _detect_type(root: Path) -> Literal["helm", "kustomize", "raw", "terraform", "none"]:
       if (root / "Chart.yaml").is_file(): return "helm"
       if (root / "kustomization.yaml").is_file() or (root / "kustomization.yml").is_file(): return "kustomize"
       # raw: any yaml under deploy/ k8s/ kubernetes/ with `kind: Deployment` etc.
       # terraform: any *.tf under root
       ...
   ```
   Multiple types possible (e.g., Helm + Terraform). Precedence: Helm > Kustomize > raw > Terraform > none. Multi-type → `confidence: low` + warning.
3. **Helm branch (per ADR-0011 + ADR-0012):**
   - `safe_yaml.load("Chart.yaml", max_bytes=10*1024*1024, max_depth=64)` → `chart_path`.
   - Glob `values.yaml` + `values-*.yaml`. For each, `safe_yaml.load` and extract `image.repository` + `image.tag` (or `image: ...` shorthand) as an `ImageRefBlock = {path: "image.repository", value: "<value>"}`.
   - If only `values.yaml` present → `image_reference = ImageRefBlock(...)`, `environments = []`.
   - If `values-<env>.yaml` files present → each becomes one `EnvironmentEntry(name=<stem-after-values->, image_reference=ImageRefBlock(...))`. Primary `image_reference` = the `values.yaml` extraction (or `None` if `values.yaml` is absent).
   - `name` derivation: `values-prod.yaml` → `"prod"`. Filename-stem regex `r"^values-(.+)\.(yaml|yml)$"`. Non-conforming filenames (`values.prod.yaml`) → `name: <full-stem>`, `warnings: ["helm.values_filename_unrecognized"]`.
4. **Kustomize branch (load-bearing zip-slip):**
   ```python
   kust = safe_yaml.load(root / "kustomization.yaml", max_bytes=10*1024*1024, max_depth=64)
   for resource in kust.get("resources", [])[:50]:
       candidate = (root / resource).resolve()  # NOT string concat
       # Python 3.12+: candidate.is_relative_to(root)
       # Python 3.11:  manual ancestor walk via candidate.parents
       if not _is_under(candidate, root.resolve()):
           warnings.append("kustomization.resource_outside_repo")
           slice_fields["kustomization_resource_path_outside_repo"] = True
           continue
       # safe to read candidate via safe_yaml.load
   ```
   Overlay traversal cap: depth 5, 50 total files. Both caps enforced via counters; exceeded → warning + truncation.
5. **Raw-manifests branch:**
   - Walk `deploy/`, `k8s/`, `kubernetes/` (limited to `declared_inputs` globs).
   - For each `.yaml`/`.yml`, `safe_yaml.load_all(...)` (multi-document).
   - Filter to `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}`.
   - Extract `spec.template.spec.containers[].image`, `.securityContext`, `.ports`, `.env`, `.envFrom`. Aggregate into `exposed_ports: list[int]`, `required_env_vars: list[str]` (literal names, not values — per facts-not-judgments).
6. **Terraform branch (per ADR-0011):**
   - Glob `*.tf` (and `*.tf.json` if you must, but the arch spec says `*.tf` only).
   - Record relative paths in `terraform_files: list[str]`. Set `terraform_present: true`.
   - **No parse.** No `python-hcl2`. No `terraform` invocation. If Terraform is the only marker detected → `confidence: low` + `warnings: ["terraform.paths_only"]`.
7. **`type: "none"`** when no markers detected. Slice still populated with empty lists / null fields (passes `additionalProperties: false` because optional fields use `null`/`[]`, not absence — per ADR-0004 convention).
8. **Register** in `src/codegenie/probes/__init__.py` (additive import).
9. **Wire** `deployment.schema.json` into the envelope under `probes.deployment` (optional `$ref`).

## TDD plan — red / green / refactor

### Red — write failing tests first

```python
# tests/unit/probes/test_deployment.py
"""Pins: DeploymentProbe records evidence not judgment;
zip-slip refused; multi-env Helm as environments list (ADR-0012);
no helm/kustomize/terraform invocation (ADR-0011).
Traces to: phase-arch-design.md §Component design #6 + §Data model + §Edge cases rows 4 + 15."""
import os
import pytest
from pathlib import Path
from codegenie.probes.deployment import DeploymentProbe

@pytest.mark.asyncio
async def test_helm_single_env_image_reference(tmp_path):
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1.0\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v1.2.3\n")
    out = await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))
    s = out.schema_slice
    assert s["type"] == "helm"
    assert s["image_reference"]["path"] == "image.repository"
    assert s["image_reference"]["value"] == "ghcr.io/me/app"
    assert s["environments"] == []

@pytest.mark.asyncio
async def test_helm_multi_env_emits_environments_list(tmp_path):
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  tag: v1\n")
    (tmp_path / "values-staging.yaml").write_text("image:\n  tag: v0\n")
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    names = sorted(e["name"] for e in s["environments"])
    assert names == ["prod", "staging"]
    assert s["image_reference"] is not None  # primary from values.yaml

@pytest.mark.asyncio
async def test_helm_no_baseline_nullable_primary(tmp_path):
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  repository: x\n")
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["image_reference"] is None
    assert len(s["environments"]) == 1

@pytest.mark.asyncio
async def test_helm_12_environments(tmp_path):
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    for i in range(12):
        (tmp_path / f"values-env{i:02d}.yaml").write_text(f"image:\n  tag: v{i}\n")
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert len(s["environments"]) == 12
    assert (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).confidence == "high"

@pytest.mark.asyncio
async def test_kustomize_resource_outside_repo_refused(tmp_path, monkeypatch):
    (tmp_path / "kustomization.yaml").write_text(
        "resources:\n  - ../../etc/passwd\n  - deployment.yaml\n"
    )
    (tmp_path / "deployment.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: x}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i}]}}}\n"
    )
    opened: list[str] = []
    real_open = os.open
    def spy_open(p, *a, **kw):
        opened.append(str(p))
        return real_open(p, *a, **kw)
    monkeypatch.setattr("os.open", spy_open)
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["kustomization_resource_path_outside_repo"] is True
    assert "kustomization.resource_outside_repo" in s["warnings"]
    assert not any("/etc/passwd" in p for p in opened)
    # valid resource still processed
    # (the slice's downstream `exposed_ports` / images may reflect deployment.yaml; depends on impl)

@pytest.mark.asyncio
async def test_raw_manifest_kinds_filtered(tmp_path):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "all.yaml").write_text(
        "---\napiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i, ports: [{containerPort: 8080}]}]}}}\n"
        "---\napiVersion: v1\nkind: ConfigMap\nmetadata: {name: cm}\ndata: {x: y}\n"
    )
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert 8080 in s["exposed_ports"]  # Deployment was processed
    # ConfigMap data ignored (not in {Deployment, StatefulSet, DaemonSet, Pod})

@pytest.mark.asyncio
async def test_terraform_paths_only(tmp_path):
    (tmp_path / "main.tf").write_text('resource "aws_instance" "x" {}')
    (tmp_path / "variables.tf").write_text('variable "y" {}')
    s = (await DeploymentProbe().run(_snapshot(tmp_path), _ctx(tmp_path))).schema_slice
    assert s["type"] == "terraform"
    assert sorted(s["terraform_files"]) == ["main.tf", "variables.tf"]
    # confidence: low — Terraform alone is low-signal in Phase 1

def test_no_helm_render_no_hcl_no_kustomize_build():
    # Static analysis: grep over the probe file
    src = (Path("src/codegenie/probes/deployment.py")).read_text()
    assert "import hcl2" not in src
    assert "run_allowlisted" not in src  # no subprocess
    assert "helm template" not in src
    assert "kustomize build" not in src
```

Run `pytest tests/unit/probes/test_deployment.py -q`. All fail — the probe doesn't exist.

### Green — make it pass

Implement per the **Implementation outline** in order: schema → type detection → Helm → Kustomize (zip-slip is load-bearing — write it first within Kustomize) → raw manifests → Terraform → register → wire into envelope. Iterate the tests until green.

### Refactor — clean up

- Extract `_is_under(candidate: Path, root: Path) -> bool` as a top-level helper, with a docstring explicitly citing ADR-0011's zip-slip clause. This is the load-bearing primitive; calling it out makes the defense readable.
- Extract `_extract_image_ref(values: dict) -> ImageRefBlock | None` so Helm primary + `EnvironmentEntry` reuse the same path. The path expression (`image.repository` or `image` shorthand) is documented as a constant.
- Confirm `mypy --strict`: every `dict.get(...)` on an untrusted parsed YAML returns `Any` until you `cast(...)` it; be explicit. The `safe_yaml.load(...)` return type is `dict[str, JSONValue]`; tighten via TypedDicts at the slice boundary.
- Run `ruff format` and `ruff check`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/deployment.py` | New — `DeploymentProbe` implementation; the zip-slip mitigation lives here |
| `src/codegenie/schema/probes/deployment.schema.json` | New — strict slice schema; both `image_reference` (nullable) and `environments` (list) at root per ADR-0012 |
| `src/codegenie/probes/__init__.py` | Edit — one additive import |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.deployment` (optional) |
| `tests/unit/probes/test_deployment.py` | New — unit tests including the unit-level zip-slip pin |
| `tests/fixtures/deployment_fixtures/` (or `tmp_path`-built) | New if needed — Helm chart, Kustomize fixture |

## Out of scope

- **`helm template` rendering** — ADR-0011 forbids. Phase 3+ Planner-time decision. Documented in `deployment.schema.json`'s `description` field.
- **`kustomize build` invocation** — ADR-0011 forbids.
- **`python-hcl2` Terraform parsing** — ADR-0011 forbids (CVE history). Paths-only.
- **`helm`/`kustomize`/`terraform` in `ALLOWED_BINARIES`** — ADR-0011 forbids. `ALLOWED_BINARIES` at end of Phase 1 = `{"git", "node"}`.
- **Adversarial corpus integration** — the dedicated S5-03 `tests/adv/test_zip_slip_kustomize.py` and oversized-YAML tests run end-to-end through the CLI. This story's unit test is the probe-level pin; S5-03 is the system-level pin. Both are needed.
- **Multi-env consumer contract finalization** — open question #6. The data shape lands here; the consumer-semantics question (can downstream ignore primary when `environments` non-empty?) is recorded as a Phase 3+ open question.
- **Coverage gate enforcement** — declared by S4-04, enforced by S6-02.

## Notes for the implementer

- **The zip-slip mitigation is the single most important defensive line in this probe.** A regression here is a parse-driven file-read escape — exactly the "facts not judgments + secure by construction" commitment failing. The unit test in this story plus the adversarial test in S5-03 form a belt-and-suspenders pair. Use `Path.resolve()`, not string concatenation. Use `.is_relative_to(root.resolve())` on 3.12+. On 3.11, walk `candidate.parents` and check `root.resolve() in candidate.resolve().parents`. **Never** trust `str(candidate).startswith(str(root))` — symlinks and `..` segments bypass it.
- **Multi-env `name` derivation** is filename-driven (`values-prod.yaml` → `"prod"`). For unusual cases like `values.prod.yaml` (note the `.` instead of `-`), emit `warnings: ["helm.values_filename_unrecognized"]` and use the full stem as the name. Per `phase-arch-design.md §"Component design" #6` and ADR-0012 consequences.
- **Three-state distinction** for the ADR-0012 shape: (1) `image_reference: set, environments: []` (single-env baseline); (2) `image_reference: set, environments: non-empty` (multi-env with baseline); (3) `image_reference: null, environments: non-empty` (multi-env without baseline). Each is a separate test case; do not let them collapse.
- **Raw-manifest extraction is intentionally shallow.** Phase 1 captures `exposed_ports` + `required_env_vars` + `security_context` + `image` per `Deployment`. It does **not** chase `envFrom: configMapRef` or `envFrom: secretRef` content — only records the references. The Planner reads further if needed (consistent with Production ADR-0005 facts-not-judgments).
- **Cross-cutting confidence rules:**
  - Single deployment type, clean parse → `confidence: high`.
  - Terraform-alone → `confidence: low` + `warnings: ["terraform.paths_only"]`.
  - Multi-type (e.g., Helm + Kustomize) → `confidence: low` + `warnings: ["deployment.multi_type"]`.
  - Zip-slip detected → `confidence: low` (and the warning above).
  - Any values-file parse error → that file skipped, `warnings: ["helm.values_file_parse_error:<path>"]`. Slice still populated for safe files.
- **The 12-environment test** (edge case #15) is the only stress test in this story's unit suite. If `environments: list` performance becomes a concern, surface a Phase 2 follow-up; do not preemptively optimize.
- **No new dependencies.** `pyyaml.CSafeLoader` (via `safe_yaml`) is the entire toolkit. Do not import `kubernetes`, `pyhelm`, `hcl2`, or any k8s/IaC parsing library. The import-linter rule (Phase 0) enforces non-network; ADR-0009 enforces non-C-extension-creep.
- **`type: "none"` is a real state.** A repo with only an app and no deployment artifacts produces `type: "none"`, empty environments, `null` image_reference, `terraform_files: []`. The slice is still emitted (ADR-0010 admits absence, but if the probe ran, it produces output). Downstream consumers see `type: "none"` and skip.
- **Phase 7 (distroless migration) is unaffected by this probe** — it consumes `manifests.native_modules`, not `deployment`. The probe's main downstream consumers are Phase 3+ planner recipes that pick deployment images to bump. Multi-env consumer-contract resolution is *their* problem; this story honors the data shape commitment from ADR-0012.
