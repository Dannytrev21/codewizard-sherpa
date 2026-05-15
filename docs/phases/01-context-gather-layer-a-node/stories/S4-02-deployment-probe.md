# Story S4-02 — `DeploymentProbe` + sub-schema with zip-slip mitigation

**Status:** Done
**Completed:** 2026-05-15
**Attempts:** 1
**Evidence:**
- Files: `src/codegenie/probes/deployment.py`, `src/codegenie/schema/probes/deployment.schema.json`, `src/codegenie/probes/__init__.py`, `src/codegenie/schema/repo_context.schema.json`, `src/codegenie/schema/validator.py`, `tests/unit/probes/test_deployment.py`
- Tests: 77 in `tests/unit/probes/test_deployment.py` (covers AC-1..AC-47); full suite 1333 pass / 0 fail / 2 xfail (pre-existing)
- Per-probe coverage: 87% line / 84% branch (carve-out floor 85/75 per ADR-0005)
- Attempt log: `_attempts/S4-02.md`
- Commit: (pending human merge)

**Step:** Step 4 — Ship `CIProbe`, `DeploymentProbe`, and `TestInventoryProbe`
**Status (original):** Ready (hardened 2026-05-14)
**Effort:** L
**Depends on:** S1-03 (`safe_yaml.load` + `load_all`)
**ADRs honored:** ADR-0004 (`additionalProperties: false`), ADR-0007 (warning-ID pattern), ADR-0010 (Layer A slices optional), **ADR-0011 (no Helm render / no HCL parsing)**, **ADR-0012 (multi-env Helm as `environments: list` with nullable primary)**

## Validation notes (2026-05-14)

Validated by `phase-story-validator` skill; full audit log at `_validation/S4-02-deployment-probe.md`. Verdict: **HARDENED**. The four parallel critics (coverage / test-quality / consistency / design-patterns) surfaced one **CRITICAL** ADR-0007 contradiction (CN-1 — `helm.values_file_parse_error:<path>` was a colon-suffixed Warning ID, identical to the S4-01 CN-1 contradiction; resolution: bare ID, path moves to `raw/deployment.json`), three other BLOCK-tier internal contradictions (zip-slip `os.open` spy is a non-event guard; missing test-helper preamble; `pytest.mark.asyncio` vs codebase-standard `asyncio.run`), and ~30 harden-tier gaps. ACs expanded from 10 bundled bullets to **31 individually-verifiable observables**; TDD plan rewritten with `asyncio.run` preamble, parametrized over kind / multi-type / file-variant matrices, a sentinel-exfiltration zip-slip test that catches a broken containment defense (the original `os.open` spy did not), AST-walked import checks, and module-level Open/Closed seams (`_DEPLOYMENT_DETECTORS`, `_DEPLOYMENT_PARSERS`, `_DEPLOYMENT_TYPE`, `_WARNING_IDS`, `_demote`+`_CONFIDENCE_RANK` copied verbatim from `node_build_system.py`) mirroring the S4-01 hardened shape. Deferred-patterns list added to Notes (ABC dispatch, module split, Pydantic, `NewType`s, shared `_confidence.py` / `_warning_ids.py` modules, `flux`/`argo-cd` detectors) so the implementer can tell what's Phase-1-load-bearing from what's Phase-2-deferred per Rule 2. No `NEEDS RESEARCH` findings — every weakness resolved from authority docs (ADRs + arch + CLAUDE.md) and the just-shipped S4-01 hardening precedent.

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

> Format: one observable per AC. ACs split per S4-01 / S2-02 hardening precedent (bundled "tests" bullets are mutation-passable). Each AC traces back to the Goal sentence and to an arch-line / ADR / CLAUDE.md commitment.

### Contract surface (file + class shape)

- [x] **AC-1 — File exists.** `src/codegenie/probes/deployment.py` exists; `DeploymentProbe(Probe)` is declared.
- [x] **AC-2 — Class attributes pinned verbatim.** A contract test asserts `DeploymentProbe.name == "deployment"`, `.layer == "A"`, `.tier == "base"`, `.applies_to_languages == ["*"]`, `.applies_to_tasks == ["*"]`, `.requires == []`, `.timeout_seconds == 15`, `.version == "1.0.0"`, and `isinstance(.declared_inputs, list)` (must be `list[str]`, **NOT** `tuple[str, ...]` — the S2-02 frozen-ABC bug).
- [x] **AC-3 — `declared_inputs` verbatim from arch line 545.** A contract test asserts:
  ```python
  DeploymentProbe.declared_inputs == [
      "deploy/**/*.yaml", "deploy/**/*.yml",
      "k8s/**/*.yaml", "k8s/**/*.yml",
      "kubernetes/**/*.yaml",
      "Chart.yaml", "values.yaml", "values-*.yaml",
      "kustomization.yaml", "kustomization.yml",
      "helm/**/*", "charts/**/*",
      "*.tf",
  ]
  ```
  (Renaming, reordering, or list→tuple conversion fails at probe-PR-merge time, not at coordinator integration time.)

### Registry membership (extension-by-addition)

- [x] **AC-4 — Additive import in `probes/__init__.py`.** `src/codegenie/probes/__init__.py` adds one explicit additive import registering `DeploymentProbe`; no edits to existing imports beyond appending.
- [x] **AC-5 — Registry membership across languages.** `test_registry_membership_universal_languages` is `pytest.mark.parametrize`-d over `langs ∈ {frozenset({"go"}), frozenset({"javascript"}), frozenset({"python"}), frozenset({"javascript","typescript"}), frozenset()}`. Each asserts `DeploymentProbe in default_registry.for_task("*", langs)`. Catches a one-character regression that narrows `applies_to_languages` (S4-01 AC-2 precedent).

### Sub-schema (ADR-0004 + ADR-0010 + ADR-0012)

- [x] **AC-6 — Schema file exists.** `src/codegenie/schema/probes/deployment.schema.json` exists, Draft 2020-12, validates the `phase-arch-design.md §"Data model" DeploymentSlice` shape.
- [x] **AC-7 — `additionalProperties: false` walk.** A walk-the-schema test asserts `{"type": "object", "additionalProperties": false}` at the slice root, at `ImageRefBlock`, and at `EnvironmentEntry`. **Documented exception:** `security_context` declares `additionalProperties: true` at its own nested block (deliberate per CN-7 / option-a — verbatim Kubernetes data is the evidence; the schema's `description` field documents the exception). The test parametrises over the four nesting points and asserts `additionalProperties is False` for the first three and `is True` for `security_context`.
- [x] **AC-8 — Schema rejection at exact JSON Pointer.** `test_schema_rejects_unknown_field_at_each_nested_block` parametrised over four injection sites:
  - `/probes/deployment/rogue_root`
  - `/probes/deployment/image_reference/rogue`
  - `/probes/deployment/environments/0/rogue`
  - `/probes/deployment/environments/0/image_reference/rogue`
  Each asserts `SchemaValidationError` is raised AND the verbatim JSON Pointer AND the rogue field name appear in the error message.
- [x] **AC-9 — Envelope-level optionality (ADR-0010).** A non-deployment repo (no `Chart.yaml`, no `kustomization.yaml`, no `*.tf`, no k8s manifests) produces an envelope that validates with `probes.deployment` either absent OR present with `type: "none"`. A test asserts the envelope schema does NOT list `"deployment"` in `properties.probes.required`.
- [x] **AC-10 — ADR-0012 dual-field shape.** The slice declares **both** `image_reference: ImageRefBlock | null` (singleton, nullable) **and** `environments: list[EnvironmentEntry]` (additive, may be empty) at the root level of the slice — never collapsed to one. Schema test fixtures cover each of the three states from ADR-0012 Decision.

### ADR-0012 four-shape coverage

- [x] **AC-11 — State (a): `values.yaml`-only baseline.** Fixture with `Chart.yaml` + `values.yaml` (with `image.repository: ghcr.io/me/app`, `image.tag: v1.2.3`) → `type: "helm"`, `image_reference == {"path": "image.repository", "value": "ghcr.io/me/app:v1.2.3"}`, `environments == []`, `confidence: "high"`. (Per CN-9 the value is the verbatim `repository:tag` concatenation.)
- [x] **AC-12 — State (b): baseline + multi-env.** Fixture with `Chart.yaml` + `values.yaml` + `values-prod.yaml` + `values-staging.yaml` → `image_reference is not None` (primary from `values.yaml`), `environments` length 2 with `sorted(names) == ["prod", "staging"]`, each entry's `image_reference` populated from its values file, `confidence: "high"`.
- [x] **AC-13 — State (c): multi-env without baseline.** Fixture with `Chart.yaml` + only `values-prod.yaml` (no `values.yaml`) → `image_reference is None`, `environments` length 1 with name `"prod"`, `confidence: "high"`.
- [x] **AC-14 — Edge case 15: 12-environment chart.** Fixture with `Chart.yaml` + `values.yaml` + 12 `values-env00.yaml`..`values-env11.yaml` → `len(environments) == 12`, `confidence: "high"`, each `environments[i]` validates against `EnvironmentEntry` schema with `additionalProperties: false` (per ADR-0012 Consequences). Run once; do not double-run inside the same test (a separate determinism AC covers idempotence).
- [x] **AC-15 — Non-conforming filename emits warning + full stem.** Fixture with `Chart.yaml` + `values.prod.yaml` (dot-separator, not dash) → `environments[0]["name"] == "values.prod"` (full stem) AND `"helm.values_filename_unrecognized" in slice["warnings"]` (bare ID).
- [x] **AC-16 — `Chart.yaml`-only with no `values*.yaml` files.** Fixture with only `Chart.yaml` and no values files → `type: "helm"`, `chart_path == "Chart.yaml"`, `image_reference is None`, `environments == []`, `confidence: "low"`, `"helm.no_values_files" in warnings`. (Mirrors S4-01 `ci.empty_workflows_dir` precedent: marker matched, no consumable content.)
- [x] **AC-17 — `image.repository` + `image.tag` concatenation.** Parametrised over: (a) shorthand `image: "<repo>:<tag>"` → `path: "image"`, `value: "<repo>:<tag>"` verbatim; (b) `image.repository: <repo>` + `image.tag: <tag>` → `path: "image.repository"`, `value: "<repo>:<tag>"` concatenated; (c) `image.repository` only, no tag → `value: "<repo>"`, no colon suffix, no warning (tag-absence is benign); (d) `image.tag` only, no repository → `image_reference is None`.
- [x] **AC-18 — `.yml` filename variants.** `test_helm_yml_extension_variants` parametrised over `(values.yaml, values.yml)` and `(values-prod.yaml, values-prod.yml)`; each combination produces the equivalent slice shape.

### Type detection + multi-type + precedence

- [x] **AC-19 — `_DEPLOYMENT_TYPE` literal alias (DP-6).** Module exposes `_DEPLOYMENT_TYPE: TypeAlias = Literal["helm", "kustomize", "raw", "terraform", "none"]`. Test asserts `set(get_args(_DEPLOYMENT_TYPE)) == set(deployment.schema.json["properties"]["type"]["enum"])` — schema-enum-to-Literal equivalence (a schema-enum addition without a Literal arm fails).
- [x] **AC-20 — `_DEPLOYMENT_DETECTORS` precedence tuple (DP-1).** Module exposes `_DEPLOYMENT_DETECTORS: Final[tuple[tuple[_DEPLOYMENT_TYPE, Callable[[Path], bool]], ...]]` of length 4 (the `"none"` arm is the fall-through, not a member). Import-time `assert tuple(t for t, _ in _DEPLOYMENT_DETECTORS) == ("helm", "kustomize", "raw", "terraform")` pins precedence. Adding a fifth deployment type (`flux` / `argo`) requires one tuple-entry insertion + one new predicate + one new Literal arm + one new parser (AC-21) — zero edits to `DeploymentProbe.run` control flow.
- [x] **AC-21 — `_DEPLOYMENT_PARSERS` dispatch registry (DP-2).** Module exposes `_DEPLOYMENT_PARSERS: Final[Mapping[_DEPLOYMENT_TYPE, Callable[[Path, ProbeContext], _ParseResult]]]`. Import-time `assert _DEPLOYMENT_PARSERS.keys() == set(get_args(_DEPLOYMENT_TYPE))` catches a new Literal arm without a parser. `DeploymentProbe.run` dispatches via `_DEPLOYMENT_PARSERS[primary_type](root, ctx)`.
- [x] **AC-22 — Multi-type detection retains all evidence.** Parametrised over `(helm + terraform)`, `(helm + kustomize)`, `(helm + raw)`, `(kustomize + terraform)`, `(raw + terraform)`, `(helm + kustomize + terraform)`. Each asserts: (i) `type` is the highest-precedence winner per AC-20; (ii) `terraform_files` is populated whenever any `*.tf` is present regardless of `type` (the additive escape hatch); (iii) `confidence == "low"`; (iv) `"deployment.multi_type" in warnings` (bare ID).
- [x] **AC-23 — `type: "none"` slice IS emitted (CN-6).** Fixture is a `tmp_path` with only a `README.md`. Asserts `schema_slice is not None`, `schema_slice["type"] == "none"`, `image_reference is None`, `environments == []`, `terraform_files == []`, `exposed_ports == []`, `required_env_vars == []`, `kustomization_resource_path_outside_repo is False`, `security_context is None`, `chart_path is None`, `warnings == []`, `confidence == "high"`. (Distinguishes "ran and found nothing" from "didn't run.")

### Kustomize zip-slip (load-bearing security pin)

- [x] **AC-24 — Sentinel-exfiltration zip-slip pin (replaces `os.open` spy).** `test_kustomize_resource_outside_repo_refused` writes a sentinel file at `tmp_path.parent / "SENTINEL_LEAK.yaml"` containing a structurally-impossible-to-fake `kind: Deployment` with `containerPort: 31337`. `kustomization.yaml` lists `resources: ["../SENTINEL_LEAK.yaml", "deployment.yaml"]` (the second is a legitimate sibling). Asserts: (i) `31337 not in exposed_ports` (sentinel content did not reach slice — the smoking-gun observable); (ii) `kustomization_resource_path_outside_repo is True`; (iii) `"kustomization.resource_outside_repo" in warnings`; (iv) `8080 in exposed_ports` (legitimate sibling still processed); (v) sentinel is cleaned up in `finally`. The naive `str(root) + str(resource)` containment check provably fails this test because `Path("/tmp/x") / "../SENTINEL_LEAK.yaml"` stringifies to `/tmp/x/../SENTINEL_LEAK.yaml` which DOES start with `/tmp/x`. The correct `.resolve().is_relative_to(root.resolve())` check correctly identifies the path as outside.
- [x] **AC-25 — Symlink-via-resource refused.** `test_kustomize_symlink_resource_refused` plants `outside.yaml` (with sentinel `containerPort: 31337`) outside `tmp_path`, creates a symlink `linked.yaml → outside.yaml` inside `tmp_path`, and lists `resources: ["linked.yaml"]`. Asserts `31337 not in exposed_ports` AND a warning is emitted (either `kustomization.resource_outside_repo` from the `.resolve()` containment check OR a `safe_yaml`-level symlink-refused warning — both are acceptable defenses; defense in depth).
- [x] **AC-26 — Overlay traversal caps (depth 5, files 50).** `test_kustomize_overlay_caps` parametrised:
  - (a) 60 resource entries in one `kustomization.yaml` → 50 processed, `"kustomization.file_cap_exceeded" in warnings`;
  - (b) Chained `kustomization.yaml` overlays 6 levels deep → 5 processed, `"kustomization.depth_cap_exceeded" in warnings`.
  Both warnings are bare IDs and members of `_WARNING_IDS`.
- [x] **AC-27 — `_walk_overlays` pure helper (DP-4).** Module exposes `_walk_overlays(root_resolved: Path, kustomization_path: Path, *, max_depth: int = 5, max_files: int = 50) -> tuple[list[Path], list[str]]`. Unit-tested in isolation against four fixture shapes (flat, two-level, depth-6, 60-resources). Phase 2+ "raise to depth 8" becomes a one-line keyword-argument change.

### Raw manifests (Kubernetes kinds)

- [x] **AC-28 — Total-ordering kind filter.** `test_raw_kind_filter_total_ordering` parametrised over 8 kinds:
  - Positive (must extract): `Deployment`, `StatefulSet`, `DaemonSet`, `Pod`. Each fixture has `containerPort: 9090` (or `spec.containers[0].ports[0].containerPort` for `Pod`'s flatter shape). Asserts `9090 in exposed_ports`.
  - Negative (must NOT extract): `Service`, `ConfigMap`, `Secret`, `Ingress`, `Job`, `CronJob`, `ReplicaSet`, `Namespace`. Each has a port-shaped field (e.g., `spec.ports[].port: 9090`) that must NOT land in `exposed_ports`. Asserts `9090 not in exposed_ports`.
  Module exposes `_RAW_KIND_FILTER: Final[frozenset[str]] = frozenset({"Deployment", "StatefulSet", "DaemonSet", "Pod"})` with an import-time anchor.
- [x] **AC-29 — Raw manifests with only non-workload kinds.** Fixture: `deploy/services.yaml` containing only `Service` + `ConfigMap` (no Deployment-family). Decision pinned: `type: "raw"` (marker = `kind:` field present in a yaml under `deploy/`), `image_reference is None`, `environments: []`, `exposed_ports: []`, `required_env_vars: []`, `confidence: "low"` (raw-with-no-workloads is low-signal), `"deployment.raw_no_workloads" in warnings` (bare ID added to `_WARNING_IDS`).
- [x] **AC-30 — `exposed_ports` sorted + deduped.** Fixture: two `Deployment` documents, the first with two containers each exposing 8080 + 443 + 8080, the second with 80 + 443. Asserts `exposed_ports == [80, 443, 8080]` (sorted ascending, deduped).
- [x] **AC-31 — `required_env_vars` sorted + deduped.** Fixture: container with `env: [{name: DB_URL}, {name: API_KEY}, {name: DB_URL}]`. Asserts `required_env_vars == ["API_KEY", "DB_URL"]` (sorted alpha, deduped, names only — no values per facts-not-judgments / ADR-0011).
- [x] **AC-32 — `security_context` verbatim pass-through.** Fixture Deployment with `spec.template.spec.containers[0].securityContext: {runAsNonRoot: true, runAsUser: 1000, capabilities: {drop: ["ALL"]}}`. Asserts `slice["security_context"] == {"runAsNonRoot": True, "runAsUser": 1000, "capabilities": {"drop": ["ALL"]}}`. Validates against the schema (loose — `additionalProperties: true` at this nested block per AC-7).

### Terraform (paths-only — ADR-0011)

- [x] **AC-33 — Paths-relative-to-root, POSIX separators.** Fixture: `main.tf` + `variables.tf` at root + `modules/network/vpc.tf` nested. Asserts `sorted(terraform_files) == ["main.tf", "modules/network/vpc.tf", "variables.tf"]`. Every entry: not absolute (`not p.startswith("/")`), no `./` prefix, no backslashes (cross-platform — uses `path.relative_to(root).as_posix()`).
- [x] **AC-34 — Terraform-alone confidence.** Fixture: only `main.tf`. Asserts `type: "terraform"`, `confidence: "low"`, `"terraform.paths_only" in warnings`.

### ADR-0011 enforcement (anti-scope structural pins)

- [x] **AC-35 — No forbidden imports (AST walk).** `test_probe_imports_no_forbidden_modules` parses `src/codegenie/probes/deployment.py` with `ast` and walks every `Import` / `ImportFrom` node. Asserts no import of `hcl2`, `python_hcl2`, `kubernetes`, `pyhelm`, `subprocess`. (AST-based, not literal-string `"import hcl2" not in src`, which misses `from hcl2 import load`.)
- [x] **AC-36 — No subprocess invocations.** Static grep asserts `"run_allowlisted" not in src`, `"os.system" not in src`, `"os.execv" not in src`, `"Popen" not in src`, `"shutil.which" not in src`. (The probe does no subprocess work at all, unlike `NodeBuildSystemProbe` which legitimately calls `run_allowlisted` for `node --version`.)
- [x] **AC-37 — `ALLOWED_BINARIES` invariant.** Test asserts `exec.ALLOWED_BINARIES == {"git", "node"}` at the end of the test module's imports (Phase 1 end-state invariant; ADR-0011 compliance; not amended by this story).

### Warning-ID discipline (ADR-0007 + S4-01 CN-1 precedent)

- [x] **AC-38 — `_WARNING_IDS` frozenset + import-time ADR-0007 loop (DP-5 / CN-1 resolution).** Module exposes `_WARNING_IDS: Final[frozenset[str]]` containing every warning ID emitted. Import-time `for _id in _WARNING_IDS: assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"`. The expected set is:
  ```python
  frozenset({
      "kustomization.resource_outside_repo",
      "kustomization.depth_cap_exceeded",
      "kustomization.file_cap_exceeded",
      "helm.values_file_parse_error",        # BARE ID — no `:<path>` suffix (CN-1)
      "helm.values_filename_unrecognized",
      "helm.no_values_files",
      "deployment.multi_type",
      "deployment.raw_no_workloads",
      "terraform.paths_only",
  })
  ```
  Test asserts `_WARNING_IDS == EXPECTED_IDS` (verbatim) AND ADR-0007 conformance loop.
- [x] **AC-39 — Per-values-file parse error: bare ID + graceful degradation.** `test_values_file_partial_failure_still_emits_safe_envs` — fixture with `Chart.yaml` + valid `values.yaml` + valid `values-prod.yaml` + **malformed** `values-staging.yaml` (size cap breach or syntactic YAML error). Asserts (i) `image_reference is not None` (baseline retained), (ii) `len(environments) == 1` with name `"prod"` (staging skipped), (iii) `"helm.values_file_parse_error" in slice["warnings"]` — **bare ID**, no `:<path>` suffix (per CN-1 / S4-01 precedent), (iv) offending path is recorded in `raw/deployment.json` under `errors`, (v) `confidence == "low"` (degraded by warning).
- [x] **AC-40 — Typed-exception routing to `ProbeOutput.errors`.** Typed exceptions raised during parse (`SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `SymlinkRefusedError`) are caught into `ProbeOutput.errors` (not `slice.warnings`) as bare error IDs (`deployment.size_cap_exceeded`, `deployment.depth_cap_exceeded`, `deployment.malformed_yaml`, `deployment.symlink_refused`). A separate `_ERROR_IDS: Final[frozenset[str]]` enumerates them with the same import-time ADR-0007 pattern loop.

### Determinism + confidence discipline

- [x] **AC-41 — Two-run byte-equal determinism.** `test_two_runs_byte_equal` — fixture with mtime-shuffled inputs (5 `values-*.yaml`, 3 raw `*.yaml`, 4 `*.tf` files). Two consecutive `DeploymentProbe().run(...)` calls. Asserts `json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)`. Implementer must sort `environments` by `name`, `terraform_files` lex (POSIX), `exposed_ports` ascending, `required_env_vars` lex.
- [x] **AC-42 — Confidence outcomes per branch (parametrized).** `test_confidence_per_branch` parametrised:
  - `("helm_single_clean", "high", None)`
  - `("helm_multi_env_clean", "high", None)`
  - `("helm_no_values_files", "low", "helm.no_values_files")`
  - `("terraform_alone", "low", "terraform.paths_only")`
  - `("multi_type_helm_plus_terraform", "low", "deployment.multi_type")`
  - `("kustomize_zip_slip_detected", "low", "kustomization.resource_outside_repo")`
  - `("raw_no_workloads", "low", "deployment.raw_no_workloads")`
  - `("values_file_parse_error", "low", "helm.values_file_parse_error")`
  - `("none", "high", None)`
- [x] **AC-43 — `_demote` / `_CONFIDENCE_RANK` reused, monotone (DP-8).** Module copies `_demote(current: str, target: str) -> str` and `_CONFIDENCE_RANK: Final[Mapping[str, int]]` **verbatim** from `node_build_system.py:245+276`. Every confidence-change site in `DeploymentProbe.run` uses `_demote`; bare `confidence = "low"` assignments are forbidden (a grep test enforces). Test asserts `_demote("low", "high") == "low"` (no upgrade) and `_demote("high", "low") == "low"` (downgrade succeeds).

### Pure helpers (functional core / imperative shell — DP-3)

- [x] **AC-44 — Pure helpers extracted at module scope.** The following live at module scope and are unit-tested in isolation with table-driven cases (no I/O beyond `Path` existence checks where unavoidable):
  - `_is_under(candidate: Path, root_resolved: Path) -> bool` — load-bearing zip-slip primitive; docstring cites ADR-0011's zip-slip clause.
  - `_extract_image_ref(values: Mapping[str, Any]) -> ImageRefBlock | None` — handles the four shapes from AC-17.
  - `_select_deployment_type(root: Path) -> tuple[_DEPLOYMENT_TYPE, list[_DEPLOYMENT_TYPE]]` — returns `(primary, others_in_precedence_order)`.
  - `_env_name_from_filename(stem: str) -> tuple[str, bool]` — returns `("prod", True)` for `values-prod.yaml`, `("values.prod", False)` for `values.prod.yaml`.
  - `_filter_k8s_kinds(docs: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]` — pure kind filter using `_RAW_KIND_FILTER`.
  - `_extract_container_specs(doc: Mapping[str, Any]) -> list[Mapping[str, Any]]` — handles `Deployment`/`StatefulSet`/`DaemonSet`'s `spec.template.spec.containers` AND `Pod`'s flatter `spec.containers`.
  - `_aggregate_exposed_ports(containers: Iterable[Mapping[str, Any]]) -> list[int]` — pure deduper + ascending sorter.
  - `_aggregate_env_var_names(containers: Iterable[Mapping[str, Any]]) -> list[str]` — pure deduper + alpha sorter; names only, no values.
- [x] **AC-45 — `_ParseResult` NamedTuple dispatch outcome (DP-9).** Module exposes `_ParseResult(NamedTuple)` with `slice_fragment: dict[str, Any]`, `warnings: list[str]`, `confidence_demote_to: str | None`. Each `_parse_X` parser returns `_ParseResult`; `DeploymentProbe.run` does not access parser internals beyond these three fields.
- [x] **AC-46 — `ImageRefBlock` and `EnvironmentEntry` TypedDicts (DP-7).** Module exposes `ImageRefBlock(TypedDict)` (fields `path: str`, `value: str`) and `EnvironmentEntry(TypedDict)` (fields `name: str`, `image_reference: ImageRefBlock | None`). `_extract_image_ref` returns `ImageRefBlock | None`; the Helm parser builds `list[EnvironmentEntry]`. `mypy --strict` rejects a missing field at every construction site.

### Definition of done

- [x] **AC-47 — Toolchain green.** `ruff check`, `ruff format --check`, `mypy --strict` on `deployment.py` pass; `pytest tests/unit/probes/test_deployment.py -q` passes (all ACs above); per-probe local coverage reported in PR body (≥ 85/75 per ADR-0005 — carve-out is the floor, not the target).

## Implementation outline

> **Pattern note (per validation).** This probe is the second consumer of the S4-01 dispatch-registry pattern (5-way parser dispatch under a discriminator). Mirror `node_build_system.py:212-262` and the S4-01 hardening report verbatim — module-level Open/Closed tuples, frozenset + import-time ADR-0007 pattern loop, pure-helper extraction. Adding a future deployment shape (`flux`, `argo-cd`) must be 1 detector + 1 parser + 1 Literal arm — zero edits to `DeploymentProbe.run` control flow.

1. **Schema first.** Write `deployment.schema.json` mirroring `DeploymentSlice` from the data model. Both `image_reference` (nullable) and `environments` (list) are declared at the slice root; `EnvironmentEntry` and `ImageRefBlock` have `additionalProperties: false`. **Exception:** `security_context` declares `additionalProperties: true` at its nested block (per AC-7 / CN-7 option-a — verbatim Kubernetes data is the evidence; document the exception in the schema's `description` field). The schema's `description` field also documents the three-state distinction (per ADR-0012) and the multi-type `terraform_files` additive-evidence convention.
2. **Module-level Open/Closed seams (AC-19 → AC-21, AC-38, AC-43):**
   ```python
   _DEPLOYMENT_TYPE: TypeAlias = Literal["helm", "kustomize", "raw", "terraform", "none"]

   def _has_helm(root: Path) -> bool:
       return (root / "Chart.yaml").is_file()
   def _has_kustomize(root: Path) -> bool:
       return (root / "kustomization.yaml").is_file() or (root / "kustomization.yml").is_file()
   def _has_raw_k8s(root: Path) -> bool: ...   # yaml under deploy/ k8s/ kubernetes/ with `kind:` field
   def _has_terraform(root: Path) -> bool:
       return any(root.rglob("*.tf"))

   # Precedence-ordered. Adding `flux` is a one-line tuple insertion (zero edits to run()).
   _DEPLOYMENT_DETECTORS: Final[tuple[tuple[_DEPLOYMENT_TYPE, Callable[[Path], bool]], ...]] = (
       ("helm", _has_helm),
       ("kustomize", _has_kustomize),
       ("raw", _has_raw_k8s),
       ("terraform", _has_terraform),
   )

   # Strict total filter for raw-manifest Deployment-family kinds.
   _RAW_KIND_FILTER: Final[frozenset[str]] = frozenset({"Deployment", "StatefulSet", "DaemonSet", "Pod"})

   _WARNING_IDS: Final[frozenset[str]] = frozenset({
       "kustomization.resource_outside_repo",
       "kustomization.depth_cap_exceeded",
       "kustomization.file_cap_exceeded",
       "helm.values_file_parse_error",      # BARE — no `:<path>` suffix (CN-1)
       "helm.values_filename_unrecognized",
       "helm.no_values_files",
       "deployment.multi_type",
       "deployment.raw_no_workloads",
       "terraform.paths_only",
   })

   _ERROR_IDS: Final[frozenset[str]] = frozenset({
       "deployment.size_cap_exceeded",
       "deployment.depth_cap_exceeded",
       "deployment.malformed_yaml",
       "deployment.symlink_refused",
   })

   _ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in (*_WARNING_IDS, *_ERROR_IDS):
       assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"
   assert tuple(t for t, _ in _DEPLOYMENT_DETECTORS) == ("helm", "kustomize", "raw", "terraform"), (
       "DP-1 _DEPLOYMENT_DETECTORS precedence: 'helm' > 'kustomize' > 'raw' > 'terraform'"
   )

   _CONFIDENCE_RANK: Final[Mapping[str, int]] = {"low": 0, "medium": 1, "high": 2}

   def _demote(current: str, target: str) -> str:   # verbatim copy from node_build_system.py:276
       if _CONFIDENCE_RANK[target] < _CONFIDENCE_RANK[current]:
           return target
       return current
   ```
3. **`_select_deployment_type` pure helper (AC-44).**
   ```python
   def _select_deployment_type(root: Path) -> tuple[_DEPLOYMENT_TYPE, list[_DEPLOYMENT_TYPE]]:
       """Returns (primary, others_in_precedence_order). Multi-type → all detected types
       past the first land in `others`; caller emits `deployment.multi_type` + `_demote` to `low`."""
       detected = [t for t, predicate in _DEPLOYMENT_DETECTORS if predicate(root)]
       if not detected:
           return "none", []
       return detected[0], detected[1:]
   ```
4. **Parser dispatch registry (AC-21 / AC-45 / DP-2 / DP-9).** Each per-type parser is a free function returning a `_ParseResult` NamedTuple:
   ```python
   class _ParseResult(NamedTuple):
       slice_fragment: dict[str, Any]
       warnings: list[str]
       confidence_demote_to: str | None   # None | "low" | "medium"

   def _parse_helm(root: Path, ctx: ProbeContext) -> _ParseResult: ...
   def _parse_kustomize(root: Path, ctx: ProbeContext) -> _ParseResult: ...
   def _parse_raw(root: Path, ctx: ProbeContext) -> _ParseResult: ...
   def _parse_terraform(root: Path, ctx: ProbeContext) -> _ParseResult: ...
   def _parse_none(root: Path, ctx: ProbeContext) -> _ParseResult: ...

   _DEPLOYMENT_PARSERS: Final[Mapping[_DEPLOYMENT_TYPE, Callable[[Path, ProbeContext], _ParseResult]]] = {
       "helm": _parse_helm,
       "kustomize": _parse_kustomize,
       "raw": _parse_raw,
       "terraform": _parse_terraform,
       "none": _parse_none,
   }
   assert _DEPLOYMENT_PARSERS.keys() == set(get_args(_DEPLOYMENT_TYPE))
   ```
5. **Helm parser (per ADR-0011 + ADR-0012, AC-11 → AC-18):**
   - `safe_yaml.load(root / "Chart.yaml", max_bytes=10*1024*1024, max_depth=64)` → `chart_path`.
   - Glob `values.yaml` + `values-*.yaml` + `.yml` variants (AC-18). For each, `safe_yaml.load` and extract image via `_extract_image_ref`:
     - shorthand `image: "<repo>:<tag>"` → `{path: "image", value: verbatim}`.
     - `image.repository: <repo>` + `image.tag: <tag>` → `{path: "image.repository", value: "<repo>:<tag>"}` (concatenated, per CN-9 / AC-17).
     - `image.repository` alone → `value: "<repo>"`, no colon suffix.
     - `image.tag` alone, no repository → returns `None`.
   - Three-state assembly (per ADR-0012):
     - Only `values.yaml` → `image_reference = <extracted>`, `environments: []`.
     - `values.yaml` + `values-<env>.{yaml,yml}` → primary `image_reference = <from values.yaml>` (or `None` if not extractable); `environments` = one `EnvironmentEntry` per env file.
     - Only `values-<env>.{yaml,yml}` files (no baseline) → `image_reference: None`, `environments` non-empty.
     - **No values files at all** (AC-16) → `image_reference: None`, `environments: []`, demote to `"low"`, emit `helm.no_values_files`.
   - `name` derivation via `_env_name_from_filename(stem)` — returns `("prod", True)` for `values-prod.yaml`; `("values.prod", False)` for the dot-variant (`values.prod.yaml`); the second tuple element triggers `helm.values_filename_unrecognized`.
   - Per-file parse failure (AC-39): catch typed exceptions per file; emit **bare** `helm.values_file_parse_error` (no `:<path>` suffix — CN-1); record offending path in `raw/deployment.json`; demote to `"low"`; **other values files still processed**.
6. **Kustomize parser — load-bearing zip-slip mitigation (AC-24 → AC-27):**
   ```python
   def _walk_overlays(
       root_resolved: Path,
       kustomization_path: Path,
       *,
       max_depth: int = 5,
       max_files: int = 50,
   ) -> tuple[list[Path], list[str]]:
       """Pure: returns (safe_resource_paths, warnings).
       Zip-slip refusal here is the load-bearing defense per ADR-0011's secure-by-construction clause.
       Mirrors `_walk_extends` in node_build_system.py:373."""
       ...
   ```
   For each resource path declared in `kustomization.yaml#resources`:
   ```python
   candidate = (root / resource).resolve()   # NEVER string concat
   if not _is_under(candidate, root_resolved):
       warnings.append("kustomization.resource_outside_repo")
       slice_fragment["kustomization_resource_path_outside_repo"] = True
       continue
   # safe to read via safe_yaml.load with O_NOFOLLOW (belt + suspenders)
   ```
   - On Python 3.12+: `candidate.is_relative_to(root_resolved)`.
   - On Python 3.11: manual ancestor walk (`root_resolved in candidate.parents`).
   - **Never** trust `str(candidate).startswith(str(root))` — it accepts `/tmp/x/../outside.yaml` since the string DOES start with `/tmp/x`.
   - Overlay caps: depth 5, files 50. Exceeded → emit `kustomization.depth_cap_exceeded` / `kustomization.file_cap_exceeded` + truncate + demote to `"low"`.
7. **Raw-manifests parser (AC-28 → AC-32):**
   - Walk `deploy/`, `k8s/`, `kubernetes/` (only `declared_inputs` globs; `kubernetes/**/*.yaml` is the arch-declared spelling, no `.yml` variant — arch line 545; flagged as drift, honored verbatim per Rule 11).
   - For each `.yaml`/`.yml`, `safe_yaml.load_all(...)` (multi-document).
   - Use `_filter_k8s_kinds(docs)` → keeps only `kind ∈ _RAW_KIND_FILTER`. `Pod` uses the flatter `spec.containers[]`; the other three use `spec.template.spec.containers[]` — `_extract_container_specs` handles both shapes.
   - Aggregate via `_aggregate_exposed_ports(containers)` (sorted ascending, deduped) and `_aggregate_env_var_names(containers)` (sorted alpha, deduped, **names only** per facts-not-judgments / ADR-0011).
   - `security_context` is the verbatim `spec.template.spec.containers[0].securityContext` (or `spec.containers[0].securityContext` for `Pod`) — pass-through; schema declares this nested block `additionalProperties: true`.
   - If raw markers matched but no Deployment-family kinds found (AC-29) → emit `deployment.raw_no_workloads` + demote to `"low"`.
8. **Terraform parser (per ADR-0011, AC-33 → AC-34):**
   - Glob `*.tf` (arch spec is `*.tf` only — no `*.tf.json`).
   - Record paths via `path.relative_to(repo_root).as_posix()` → no absolute paths, no `./` prefix, no backslashes (cross-platform).
   - Sort lex; set `terraform_files: list[str]`.
   - **No parse.** No `python-hcl2`. No `terraform` invocation. AC-35 (AST-walked import check) enforces.
   - If `_select_deployment_type` returned `"terraform"` as primary AND `others == []` → emit `terraform.paths_only` + demote to `"low"`.
9. **`type: "none"` parser (AC-23).** Returns a `_ParseResult` with the empty-but-emitted shape: `image_reference: None`, `environments: []`, `terraform_files: []`, `exposed_ports: []`, `required_env_vars: []`, `kustomization_resource_path_outside_repo: False`, `security_context: None`, `chart_path: None`, `warnings: []`. Confidence stays at `"high"` (the answer "nothing here" is definitive).
10. **`DeploymentProbe.run` assembly.** Pure orchestration:
    ```python
    primary, others = _select_deployment_type(root)
    result = _DEPLOYMENT_PARSERS[primary](root, ctx)
    slice_fragment = result.slice_fragment
    warnings = list(result.warnings)
    confidence = "high" if result.confidence_demote_to is None else _demote("high", result.confidence_demote_to)
    if others:
        # Multi-type: gather terraform_files even when type != "terraform" (CN-3 / AC-22)
        if "terraform" in others:
            tf_result = _parse_terraform(root, ctx)
            slice_fragment["terraform_files"] = tf_result.slice_fragment["terraform_files"]
        warnings.append("deployment.multi_type")
        confidence = _demote(confidence, "low")
    slice_fragment["type"] = primary
    slice_fragment["warnings"] = warnings   # _WARNING_IDS membership-checked at emit sites
    ```
11. **Register** in `src/codegenie/probes/__init__.py` (additive import — AC-4).
12. **Wire** `deployment.schema.json` into the envelope under `probes.deployment` (optional `$ref`; ADR-0010 envelope-level optionality).

## TDD plan — red / green / refactor

> **Convention pins (per validation, learned from S2-02 / S4-01 hardening):** test module inlines its own `_snapshot` / `_ctx` / `_run` preamble (TQ-1); uses `asyncio.run` not `pytest.mark.asyncio` (TQ-2 / Rule 11 — matches `test_node_build_system.py:93`); zip-slip pinned with a sentinel-exfiltration fixture not an `os.open` spy (TQ-3 — the spy is a non-event guard on POSIX `Path.resolve()`); contract-attributes pinned verbatim including `isinstance(declared_inputs, list)` (TQ-4 / S2-02 frozen-ABC bug); one **invariant** per test, parametrised over all inputs that exercise it (S4-01 TQ-15 — parametrize is the codebase's idiom, not a Refactor anti-pattern).

### Red — write failing tests first

```python
# tests/unit/probes/test_deployment.py
"""Red tests for S4-02 — DeploymentProbe.

Pins: DeploymentProbe records evidence not judgment (ADR-0011 + production ADR-0005);
zip-slip refused at probe level (load-bearing); multi-env Helm as environments list
(ADR-0012); no helm/kustomize/terraform subprocess invocation (ADR-0011);
warning IDs match ADR-0007 pattern (BARE — no `:<path>` suffixes per CN-1).
Traces to: phase-arch-design.md §Component design #6 + §Data model + §Edge cases rows 4 + 15.
"""
from __future__ import annotations

import asyncio
import ast
import json
import logging
import re
from pathlib import Path
from typing import Any, get_args

import pytest

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root, git_commit=None,
        detected_languages={"javascript": 1}, config={},
    )


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache", output_dir=root / ".out",
        workspace=root, logger=logging.getLogger("test"),
        config={}, parsed_manifest=None,
    )


def _run(root: Path) -> ProbeOutput:
    from codegenie.probes.deployment import DeploymentProbe
    return asyncio.run(DeploymentProbe().run(_snapshot(root), _ctx(root)))


# --- T-CONTRACT (AC-2 + AC-3) -------------------------------------------------

def test_probe_contract_attributes_match_arch() -> None:
    """AC-2 + AC-3. Verbatim vs phase-arch-design.md §Component design #6 line 545."""
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
    # MUST be list[str], NOT tuple[str, ...] (S2-02 frozen-ABC bug):
    assert isinstance(P.declared_inputs, list)
    assert all(isinstance(g, str) for g in P.declared_inputs)
    expected = [
        "deploy/**/*.yaml", "deploy/**/*.yml",
        "k8s/**/*.yaml", "k8s/**/*.yml",
        "kubernetes/**/*.yaml",
        "Chart.yaml", "values.yaml", "values-*.yaml",
        "kustomization.yaml", "kustomization.yml",
        "helm/**/*", "charts/**/*",
        "*.tf",
    ]
    assert P.declared_inputs == expected, "drift vs phase-arch-design.md line 545"


# --- T-REG (AC-5) -------------------------------------------------------------

@pytest.mark.parametrize("langs", [
    frozenset({"go"}),
    frozenset({"javascript"}),
    frozenset({"python"}),
    frozenset({"javascript", "typescript"}),
    frozenset(),
])
def test_registry_membership_across_all_languages(langs: frozenset[str]) -> None:
    """AC-5. applies_to_languages = ["*"] ⇒ probe runs everywhere."""
    from codegenie.probes import default_registry
    from codegenie.probes.deployment import DeploymentProbe

    assert DeploymentProbe in default_registry.all_probes()
    assert DeploymentProbe in default_registry.for_task("*", langs), (
        f"missing for langs={langs}; check additive import in probes/__init__.py"
    )


# --- T-SHAPE (AC-11 → AC-18, ADR-0012 four-shape coverage) --------------------

def test_helm_single_env_image_reference(tmp_path: Path) -> None:
    """AC-11 (state a). values.yaml only → image_reference set, environments empty."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1.0\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v1.2.3\n")
    s = _run(tmp_path).schema_slice
    assert s["type"] == "helm"
    assert s["image_reference"] == {"path": "image.repository", "value": "ghcr.io/me/app:v1.2.3"}
    assert s["environments"] == []
    assert _run(tmp_path).confidence == "high"


def test_helm_multi_env_emits_environments_list(tmp_path: Path) -> None:
    """AC-12 (state b). values.yaml + values-prod + values-staging."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: base\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v1\n")
    (tmp_path / "values-staging.yaml").write_text("image:\n  repository: ghcr.io/me/app\n  tag: v0\n")
    s = _run(tmp_path).schema_slice
    names = sorted(e["name"] for e in s["environments"])
    assert names == ["prod", "staging"]
    assert s["image_reference"] is not None
    # Each EnvironmentEntry must carry a non-None image_reference here.
    for entry in s["environments"]:
        assert entry["image_reference"] is not None
        assert entry["image_reference"]["value"].endswith(":v0") or entry["image_reference"]["value"].endswith(":v1")


def test_helm_no_baseline_nullable_primary(tmp_path: Path) -> None:
    """AC-13 (state c). Only values-prod.yaml → image_reference: None, env list non-empty."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values-prod.yaml").write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice
    assert s["image_reference"] is None
    assert len(s["environments"]) == 1
    assert s["environments"][0]["name"] == "prod"


def test_helm_12_environments(tmp_path: Path) -> None:
    """AC-14 (edge case 15). 12 envs; confidence high; each entry validates strict."""
    from codegenie.schema.validator import validate

    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    for i in range(12):
        (tmp_path / f"values-env{i:02d}.yaml").write_text(f"image:\n  repository: x\n  tag: v{i}\n")
    out = _run(tmp_path)
    s = out.schema_slice
    assert len(s["environments"]) == 12
    assert out.confidence == "high"
    # Each EnvironmentEntry is additionalProperties: false (per ADR-0012 Consequences).
    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())
    for entry in s["environments"]:
        # Schema lookup: properties.environments.items
        validate.environment_entry(entry, schema)  # adapter exposed by validator


def test_helm_values_filename_unrecognized_uses_full_stem(tmp_path: Path) -> None:
    """AC-15. values.prod.yaml (dot, not dash) → name='values.prod', warning."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.prod.yaml").write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice
    assert "values.prod" in [e["name"] for e in s["environments"]]
    assert "helm.values_filename_unrecognized" in s["warnings"]


def test_helm_chart_yaml_only_no_values(tmp_path: Path) -> None:
    """AC-16. Chart.yaml alone → low confidence + helm.no_values_files warning."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    out = _run(tmp_path)
    s = out.schema_slice
    assert s["type"] == "helm"
    assert s["chart_path"] == "Chart.yaml"
    assert s["image_reference"] is None
    assert s["environments"] == []
    assert "helm.no_values_files" in s["warnings"]
    assert out.confidence == "low"


@pytest.mark.parametrize("values_body,expected_path,expected_value", [
    # (a) shorthand: image: "<repo>:<tag>" → verbatim
    ('image: "ghcr.io/me/app:v1.2.3"\n', "image", "ghcr.io/me/app:v1.2.3"),
    # (b) repository + tag → concatenated
    ("image:\n  repository: ghcr.io/me/app\n  tag: v1.2.3\n", "image.repository", "ghcr.io/me/app:v1.2.3"),
    # (c) repository alone → no colon suffix
    ("image:\n  repository: ghcr.io/me/app\n", "image.repository", "ghcr.io/me/app"),
])
def test_image_ref_extraction_shapes(tmp_path: Path, values_body: str, expected_path: str, expected_value: str) -> None:
    """AC-17. Three image-ref shapes; case (d) tested separately (returns None)."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text(values_body)
    s = _run(tmp_path).schema_slice
    assert s["image_reference"] == {"path": expected_path, "value": expected_value}


def test_image_ref_tag_only_no_repo_returns_none(tmp_path: Path) -> None:
    """AC-17 case (d). image.tag alone, no repository → None."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  tag: v1\n")
    s = _run(tmp_path).schema_slice
    assert s["image_reference"] is None


@pytest.mark.parametrize("baseline,env_file", [
    ("values.yaml", "values-prod.yaml"),
    ("values.yml", "values-prod.yml"),
    ("values.yaml", "values-prod.yml"),  # mixed
])
def test_helm_yml_extension_variants(tmp_path: Path, baseline: str, env_file: str) -> None:
    """AC-18. .yml variants behave identically to .yaml."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / baseline).write_text("image:\n  repository: x\n  tag: base\n")
    (tmp_path / env_file).write_text("image:\n  repository: x\n  tag: v1\n")
    s = _run(tmp_path).schema_slice
    assert s["type"] == "helm"
    assert any(e["name"] == "prod" for e in s["environments"])


# --- T-TYPE-PRECEDENCE (AC-19 → AC-22, AC-23) ---------------------------------

def test_deployment_type_alias_matches_schema_enum() -> None:
    """AC-19. Schema enum equivalence to _DEPLOYMENT_TYPE Literal arms."""
    from codegenie.probes import deployment as dp

    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())
    assert set(get_args(dp._DEPLOYMENT_TYPE)) == set(schema["properties"]["type"]["enum"])


def test_deployment_detectors_precedence_tuple() -> None:
    """AC-20. Open/Closed at file boundary; precedence pinned."""
    from codegenie.probes import deployment as dp

    types = tuple(t for t, _ in dp._DEPLOYMENT_DETECTORS)
    assert types == ("helm", "kustomize", "raw", "terraform")


def test_deployment_parsers_dispatch_keys() -> None:
    """AC-21. Dispatch registry covers every Literal arm."""
    from codegenie.probes import deployment as dp

    assert dp._DEPLOYMENT_PARSERS.keys() == set(get_args(dp._DEPLOYMENT_TYPE))


@pytest.mark.parametrize("markers,primary,others", [
    (("Chart.yaml", "main.tf"), "helm", ["terraform"]),
    (("Chart.yaml", "kustomization.yaml"), "helm", ["kustomize"]),
    (("kustomization.yaml", "main.tf"), "kustomize", ["terraform"]),
    (("Chart.yaml", "kustomization.yaml", "main.tf"), "helm", ["kustomize", "terraform"]),
])
def test_multi_type_detection_retains_all_evidence(tmp_path: Path, markers: tuple[str, ...], primary: str, others: list[str]) -> None:
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
    s = out.schema_slice
    assert s["type"] == primary
    if "terraform" in others or primary == "terraform":
        assert "main.tf" in s["terraform_files"]
    assert "deployment.multi_type" in s["warnings"]
    assert out.confidence == "low"


def test_repo_with_no_deployment_artifacts_emits_type_none(tmp_path: Path) -> None:
    """AC-23. Slice IS emitted with type='none'; distinguishes ran-and-found-nothing from didn't-run."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.go").write_text("package main\nfunc main() {}\n")
    out = _run(tmp_path)
    s = out.schema_slice
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


# --- T-ZIP-SLIP (AC-24 → AC-27) — LOAD-BEARING SECURITY PIN -------------------

def test_kustomize_resource_outside_repo_refused(tmp_path: Path) -> None:
    """AC-24. Sentinel-exfiltration zip-slip test. The naive
    `str(root) + str(resource)` + `.startswith` defense fails this test because
    `Path("/tmp/x") / "../SENTINEL_LEAK.yaml"` stringifies as `/tmp/x/../SENTINEL_LEAK.yaml`
    which DOES start with `/tmp/x`. Only `.resolve().is_relative_to(...)` is correct."""
    sentinel = tmp_path.parent / "SENTINEL_LEAK.yaml"
    sentinel.write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: leak}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 31337}]}]}}}\n"
    )
    try:
        (tmp_path / "kustomization.yaml").write_text(
            "resources:\n"
            f"  - ../{sentinel.name}\n"   # zip-slip attempt
            "  - deployment.yaml\n"        # valid sibling
        )
        (tmp_path / "deployment.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: x}\n"
            "spec: {template: {spec: {containers: [{name: c, image: i,"
            " ports: [{containerPort: 8080}]}]}}}\n"
        )
        s = _run(tmp_path).schema_slice
        # Smoking-gun: sentinel content MUST NOT reach the slice.
        assert 31337 not in s["exposed_ports"], "zip-slip exfiltration: sentinel reached slice"
        # Defense observables:
        assert s["kustomization_resource_path_outside_repo"] is True
        assert "kustomization.resource_outside_repo" in s["warnings"]
        # Legitimate sibling resource still processed:
        assert 8080 in s["exposed_ports"]
    finally:
        sentinel.unlink(missing_ok=True)


def test_kustomize_symlink_resource_refused(tmp_path: Path) -> None:
    """AC-25. Defense in depth — either containment refuses or O_NOFOLLOW refuses."""
    outside = tmp_path.parent / "outside.yaml"
    outside.write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: leak}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " ports: [{containerPort: 31337}]}]}}}\n"
    )
    try:
        (tmp_path / "linked.yaml").symlink_to(outside)
        (tmp_path / "kustomization.yaml").write_text("resources:\n  - linked.yaml\n")
        s = _run(tmp_path).schema_slice
        assert 31337 not in s["exposed_ports"], "symlink-via-resource leaked"
        assert (
            "kustomization.resource_outside_repo" in s["warnings"]
            or any("symlink" in w for w in s["warnings"])
        )
    finally:
        outside.unlink(missing_ok=True)


def test_kustomize_overlay_file_count_capped(tmp_path: Path) -> None:
    """AC-26 (a). 60 resource files → 50 processed, file-cap warning, slice still ships."""
    (tmp_path / "kustomization.yaml").write_text(
        "resources:\n" + "".join(f"  - r{i}.yaml\n" for i in range(60))
    )
    for i in range(60):
        (tmp_path / f"r{i}.yaml").write_text(
            f"apiVersion: apps/v1\nkind: Deployment\nmetadata: {{name: r{i}}}\n"
            f"spec: {{template: {{spec: {{containers: [{{name: c, image: i}}]}}}}}}\n"
        )
    s = _run(tmp_path).schema_slice
    assert "kustomization.file_cap_exceeded" in s["warnings"]


def test_walk_overlays_pure_helper_caps(tmp_path: Path) -> None:
    """AC-27. Pure helper unit-tested in isolation."""
    from codegenie.probes.deployment import _walk_overlays

    (tmp_path / "kustomization.yaml").write_text(
        "resources:\n" + "".join(f"  - r{i}.yaml\n" for i in range(60))
    )
    paths, warnings = _walk_overlays(tmp_path.resolve(), tmp_path / "kustomization.yaml", max_files=50)
    assert len(paths) <= 50
    assert "kustomization.file_cap_exceeded" in warnings


# --- T-RAW (AC-28 → AC-32) ----------------------------------------------------

@pytest.mark.parametrize("kind,should_extract", [
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
])
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
            f"apiVersion: v1\nkind: Pod\nmetadata: {{name: x}}\n"
            f"spec: {{containers: [{{name: c, image: i,"
            f" ports: [{{containerPort: 9090}}]}}]}}\n"
        )
    else:
        body = f"apiVersion: v1\nkind: {kind}\nmetadata: {{name: x}}\nspec: {{ports: [{{port: 9090}}]}}\n"
    (tmp_path / "deploy" / "x.yaml").write_text(body)
    s = _run(tmp_path).schema_slice
    if should_extract:
        assert 9090 in s["exposed_ports"], f"{kind} should be processed"
    else:
        assert 9090 not in s["exposed_ports"], f"{kind} should NOT be processed"


def test_raw_only_non_workload_kinds(tmp_path: Path) -> None:
    """AC-29. Marker matched but no workloads → low confidence + raw_no_workloads warning."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "x.yaml").write_text(
        "---\napiVersion: v1\nkind: Service\nmetadata: {name: a}\nspec: {ports: [{port: 80}]}\n"
        "---\napiVersion: v1\nkind: ConfigMap\nmetadata: {name: b}\ndata: {x: y}\n"
    )
    out = _run(tmp_path)
    assert out.schema_slice["type"] == "raw"
    assert out.schema_slice["exposed_ports"] == []
    assert "deployment.raw_no_workloads" in out.schema_slice["warnings"]
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
    s = _run(tmp_path).schema_slice
    assert s["exposed_ports"] == [80, 443, 8080]


def test_required_env_vars_sorted_and_deduped_names_only(tmp_path: Path) -> None:
    """AC-31. Names only (facts not judgments); sorted alpha; deduped."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "d.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: d}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " env: [{name: DB_URL, value: secret_value}, {name: API_KEY}, {name: DB_URL}]}]}}}\n"
    )
    s = _run(tmp_path).schema_slice
    assert s["required_env_vars"] == ["API_KEY", "DB_URL"]
    # Values must NEVER leak into the slice (facts-not-judgments).
    assert "secret_value" not in json.dumps(s)


def test_security_context_verbatim_passthrough(tmp_path: Path) -> None:
    """AC-32. security_context passes through verbatim (loose nested block)."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "x.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: x}\n"
        "spec: {template: {spec: {containers: [{name: c, image: i,"
        " securityContext: {runAsNonRoot: true, runAsUser: 1000,"
        " capabilities: {drop: [ALL]}}}]}}}\n"
    )
    s = _run(tmp_path).schema_slice
    assert s["security_context"] == {
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "capabilities": {"drop": ["ALL"]},
    }


# --- T-TERRAFORM (AC-33 → AC-34) ---------------------------------------------

def test_terraform_paths_relative_to_root_forward_slashes(tmp_path: Path) -> None:
    """AC-33. POSIX-style relative paths; no abs; no `./` prefix; no backslashes."""
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    (tmp_path / "variables.tf").write_text('variable "z" {}')
    (tmp_path / "modules" / "network").mkdir(parents=True)
    (tmp_path / "modules" / "network" / "vpc.tf").write_text('variable "w" {}')
    s = _run(tmp_path).schema_slice
    assert sorted(s["terraform_files"]) == ["main.tf", "modules/network/vpc.tf", "variables.tf"]
    for p in s["terraform_files"]:
        assert not p.startswith("/")
        assert not p.startswith("./")
        assert "\\" not in p


def test_terraform_alone_low_confidence(tmp_path: Path) -> None:
    """AC-34. Terraform alone → low + terraform.paths_only."""
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    out = _run(tmp_path)
    assert out.schema_slice["type"] == "terraform"
    assert out.confidence == "low"
    assert "terraform.paths_only" in out.schema_slice["warnings"]


# --- T-ADR-0011 STATIC (AC-35 → AC-37) ---------------------------------------

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


# --- T-WARNING-IDS (AC-38, AC-39, AC-40) -------------------------------------

def test_warning_ids_match_adr_0007() -> None:
    """AC-38. _WARNING_IDS verbatim + ADR-0007 conformance loop."""
    from codegenie.probes import deployment as dp

    expected = frozenset({
        "kustomization.resource_outside_repo",
        "kustomization.depth_cap_exceeded",
        "kustomization.file_cap_exceeded",
        "helm.values_file_parse_error",
        "helm.values_filename_unrecognized",
        "helm.no_values_files",
        "deployment.multi_type",
        "deployment.raw_no_workloads",
        "terraform.paths_only",
    })
    assert dp._WARNING_IDS == expected
    for w in dp._WARNING_IDS:
        assert ADR_0007.match(w), f"ADR-0007 violation: {w!r}"


def test_error_ids_match_adr_0007() -> None:
    """AC-40. _ERROR_IDS verbatim + ADR-0007."""
    from codegenie.probes import deployment as dp

    expected = frozenset({
        "deployment.size_cap_exceeded",
        "deployment.depth_cap_exceeded",
        "deployment.malformed_yaml",
        "deployment.symlink_refused",
    })
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
    s = out.schema_slice
    names = sorted(e["name"] for e in s["environments"])
    assert "prod" in names
    assert "staging" not in names
    assert "helm.values_file_parse_error" in s["warnings"]  # BARE — no colon
    for w in s["warnings"]:
        assert ADR_0007.match(w), f"non-bare warning: {w!r}"
    # Per-file path detail lives in raw/ (offending path captured there, not in warning ID).
    assert out.confidence == "low"


# --- T-DETERMINISM + CONFIDENCE (AC-41, AC-42, AC-43) ------------------------

def test_two_runs_byte_equal(tmp_path: Path) -> None:
    """AC-41. Deterministic two-run byte-equal."""
    (tmp_path / "Chart.yaml").write_text("apiVersion: v2\nname: app\nversion: 0.1\n")
    (tmp_path / "values.yaml").write_text("image:\n  repository: x\n")
    for i in range(5):
        (tmp_path / f"values-env{i}.yaml").write_text(f"image:\n  tag: v{i}\n")
    (tmp_path / "main.tf").write_text('resource "x" "y" {}')
    a = _run(tmp_path).schema_slice
    b = _run(tmp_path).schema_slice
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_demote_helper_monotone() -> None:
    """AC-43. _demote is monotone (downgrade only)."""
    from codegenie.probes.deployment import _demote
    assert _demote("low", "high") == "low"
    assert _demote("high", "low") == "low"
    assert _demote("high", "medium") == "medium"
    assert _demote("medium", "low") == "low"
    assert _demote("low", "low") == "low"


# --- T-SCHEMA REJECTION (AC-7, AC-8) -----------------------------------------

@pytest.mark.parametrize("injection_pointer,build", [
    ("/probes/deployment/rogue_root", lambda s: {**s, "rogue_root": True}),
    ("/probes/deployment/image_reference/rogue",
     lambda s: {**s, "image_reference": {**s["image_reference"], "rogue": True}}),
    ("/probes/deployment/environments/0/rogue",
     lambda s: {**s, "environments": [{**s["environments"][0], "rogue": True}]}),
    ("/probes/deployment/environments/0/image_reference/rogue",
     lambda s: {**s, "environments": [{**s["environments"][0],
        "image_reference": {**s["environments"][0]["image_reference"], "rogue": True}}]}),
])
def test_schema_rejects_extra_field_at_every_nesting_level(injection_pointer: str, build) -> None:
    """AC-8. additionalProperties: false at every nesting level except security_context."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    base_slice: dict[str, Any] = {
        "type": "helm",
        "chart_path": "Chart.yaml",
        "image_reference": {"path": "image.repository", "value": "x"},
        "environments": [
            {"name": "prod", "image_reference": {"path": "image.tag", "value": "v1"}}
        ],
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
        "probes": {"deployment": build(base_slice)},
    }
    with pytest.raises(SchemaValidationError) as ei:
        validate(envelope)
    msg = str(ei.value)
    assert "rogue" in msg


def test_every_object_node_has_additional_properties_false_except_security_context() -> None:
    """AC-7. Walk the schema; security_context is the documented exception."""
    schema = json.loads(Path("src/codegenie/schema/probes/deployment.schema.json").read_text())

    def _walk(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                if pointer.endswith("/security_context"):
                    assert node.get("additionalProperties") is True, (
                        f"security_context must be loose (AC-7 documented exception); got {node.get('additionalProperties')}"
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
    validate(envelope)  # must not raise


# --- T-CONFIDENCE-MATRIX (AC-42) ---------------------------------------------

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


@pytest.mark.parametrize("name,expected_conf,expected_warning", [
    ("helm_single_clean", "high", None),
    ("helm_multi_env_clean", "high", None),
    ("helm_no_values_files", "low", "helm.no_values_files"),
    ("terraform_alone", "low", "terraform.paths_only"),
    ("multi_type_helm_plus_terraform", "low", "deployment.multi_type"),
    ("kustomize_zip_slip_detected", "low", "kustomization.resource_outside_repo"),
    ("raw_no_workloads", "low", "deployment.raw_no_workloads"),
    ("none", "high", None),
])
def test_confidence_outcomes_per_scenario(
    tmp_path: Path, name: str, expected_conf: str, expected_warning: str | None
) -> None:
    """AC-42. Confidence × warning matrix."""
    _FIXTURES[name](tmp_path)
    out = _run(tmp_path)
    assert out.confidence == expected_conf, f"{name}: expected {expected_conf}, got {out.confidence}"
    if expected_warning:
        assert expected_warning in out.schema_slice["warnings"]


# --- T-PURE-HELPERS (AC-44, AC-45, AC-46) ------------------------------------

def test_env_name_from_filename() -> None:
    """AC-44 helper. Pure: stem → (name, conforming?)."""
    from codegenie.probes.deployment import _env_name_from_filename
    assert _env_name_from_filename("values-prod.yaml") == ("prod", True)
    assert _env_name_from_filename("values-staging.yml") == ("staging", True)
    assert _env_name_from_filename("values.prod.yaml") == ("values.prod", False)
    assert _env_name_from_filename("values.yaml") == ("values", False)  # baseline, but caller handles


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
```

Run `pytest tests/unit/probes/test_deployment.py -q`. All fail — the probe doesn't exist.

### Green — make it pass

Implement per the **Implementation outline** in order: module-level constants + `_ID_PATTERN` loop → schema → pure helpers (`_is_under` first, since zip-slip is load-bearing) → `_select_deployment_type` → per-type parsers → `_DEPLOYMENT_PARSERS` dispatch → `DeploymentProbe.run` orchestration → register → wire envelope. Iterate tests until green.

### Refactor — clean up

- Confirm the module-level constants pinned at AC-19/20/21/38/40/43 are in place with import-time anchors.
- Confirm pure helpers (AC-44) are all module-scope, table-driven-testable, and called by `_parse_X` parsers — not by `DeploymentProbe.run` directly.
- Confirm `_ParseResult` is the only return shape across all parsers (AC-45); `DeploymentProbe.run` does not access parser internals.
- Confirm `mypy --strict`: every `dict.get(...)` on parsed YAML is `cast(...)`ed or guarded. `safe_yaml.load(...)` returns `dict[str, JSONValue]`; tighten via `ImageRefBlock` / `EnvironmentEntry` TypedDicts at the slice boundary.
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

- **The zip-slip mitigation is the single most important defensive line in this probe.** A regression here is a parse-driven file-read escape — exactly the "facts not judgments + secure by construction" commitment failing. The unit test (AC-24 — sentinel-exfiltration fixture) plus the adversarial test in S5-03 form a belt-and-suspenders pair. Use `Path.resolve()`, not string concatenation. Use `.is_relative_to(root.resolve())` on 3.12+. On 3.11, walk `candidate.parents` and check `root.resolve() in candidate.resolve().parents`. **Never** trust `str(candidate).startswith(str(root))` — `Path("/tmp/x") / "../outside.yaml"` stringifies as `/tmp/x/../outside.yaml` which DOES start with `/tmp/x`; symlinks and `..` segments bypass it. AC-24's sentinel-exfiltration fixture proves the broken defense breaks.
- **Multi-env `name` derivation** is filename-driven (`values-prod.yaml` → `"prod"`). Use `_env_name_from_filename` pure helper (AC-44). For unusual cases like `values.prod.yaml` (dot, not dash), emit bare `warnings: ["helm.values_filename_unrecognized"]` and use the full stem as the name (AC-15). Per `phase-arch-design.md §"Component design" #6` and ADR-0012 consequences.
- **Three-state distinction** for the ADR-0012 shape (covered by AC-11, AC-12, AC-13 + AC-16 for the new fourth "no-values" case): (1) `image_reference: set, environments: []` (single-env baseline); (2) `image_reference: set, environments: non-empty` (multi-env with baseline); (3) `image_reference: null, environments: non-empty` (multi-env without baseline); (4) `image_reference: null, environments: []` + `helm.no_values_files` warning (Chart.yaml with no values files at all — marker matched, no consumable content; mirrors S4-01 `ci.empty_workflows_dir`). Each is a separate test case; do not let them collapse.
- **`image.repository` + `image.tag` concatenation (AC-17 / CN-9).** Helm's singleton `image_reference` shape cannot carry both as separate paths. Convention: emit `{path: "image.repository", value: "<repo>:<tag>"}` — the value is the verbatim Helm convention (`registry/repository:tag`). For shorthand `image: "<repo>:<tag>"`, emit `path: "image"` with the verbatim value. For `repository` alone, no colon suffix. For `tag` alone with no `repository`, the slice's `image_reference` is `None`.
- **`security_context` is loose pass-through (CN-7 / AC-7 / AC-32).** Kubernetes's `SecurityContext` is a ~30-field evolving structured type. The schema declares `additionalProperties: true` AT THIS NESTED BLOCK ONLY — a deliberate ADR-0004 exception documented in the schema's `description` field. Probe transcribes the dict verbatim from `spec.template.spec.containers[0].securityContext` (or `spec.containers[0].securityContext` for `Pod`'s flatter shape). Planner reads further if needed (consistent with production ADR-0005 facts-not-judgments).
- **Raw-manifest extraction is intentionally shallow.** Phase 1 captures `exposed_ports` + `required_env_vars` (names only — no values, per ADR-0011 facts-not-judgments) + `security_context` + `image` per Deployment-family kind. It does **not** chase `envFrom: configMapRef` or `envFrom: secretRef` content — only records the references. The Planner reads further if needed.
- **Cross-cutting confidence rules (AC-42 pins each):**
  - Single deployment type, clean parse → `confidence: "high"`.
  - Terraform-alone → `confidence: "low"` + `warnings: ["terraform.paths_only"]`.
  - Multi-type (e.g., Helm + Kustomize) → `confidence: "low"` + `warnings: ["deployment.multi_type"]`. `terraform_files` is captured even when `type != "terraform"` (multi-type evidence survives via the additive list field — CN-3).
  - Zip-slip detected → `confidence: "low"` + `warnings: ["kustomization.resource_outside_repo"]`.
  - Raw markers matched but no Deployment-family kinds → `confidence: "low"` + `warnings: ["deployment.raw_no_workloads"]`.
  - Chart.yaml present with no values files → `confidence: "low"` + `warnings: ["helm.no_values_files"]`.
  - Any per-values-file parse error → that file skipped; emit **bare** `warnings: ["helm.values_file_parse_error"]` (NOT colon-suffixed — per CN-1 / S4-01 CN-1 precedent / ADR-0007); offending path lives in `raw/deployment.json`; slice still populated for safe files; demote to `"low"`.
- **Use `_demote(current, target)`, never bare assignment.** Confidence demotion is monotone (downgrade-only); a bare `confidence = "high"` after a prior demote silently upgrades. Mirrors `node_build_system.py:276`. AC-43 enforces.
- **The 12-environment test** (edge case #15) is the only stress test in this story's unit suite. If `environments: list` performance becomes a concern, surface a Phase 2 follow-up; do not preemptively optimize.
- **No new dependencies.** `pyyaml.CSafeLoader` (via `safe_yaml`) is the entire toolkit. Do not import `kubernetes`, `pyhelm`, `hcl2`, or any k8s/IaC parsing library. The AST-walked import check (AC-35) enforces at unit time; the import-linter rule (Phase 0) enforces non-network; ADR-0009 enforces non-C-extension-creep.
- **`type: "none"` is a real state (AC-23).** A repo with only an app and no deployment artifacts produces `type: "none"`, empty environments, `null` image_reference, `terraform_files: []`. The slice IS still emitted (ADR-0010 admits absence at envelope, but once the probe ran, it produces output). Downstream consumers see `type: "none"` and skip.
- **Arch-doc drift flagged for follow-up (per Rule 7):**
  1. Arch line 540 (`CIProbe` failure behavior) and Notes here originally said `"helm.values_file_parse_error:<path>"` — colon-suffixed. ADR-0007 admits no colons. Resolution applied: bare ID; path moves to `raw/deployment.json`. Arch-doc fix pending.
  2. Arch line 545 `declared_inputs` lists `kubernetes/**/*.yaml` but NOT `kubernetes/**/*.yml`, while `deploy/**` and `k8s/**` are symmetric (both `.yaml` and `.yml`). Story honors arch verbatim (Rule 11); flag asymmetry for arch follow-up.
  3. Arch §"Data model" `DeploymentSlice` declares `type: Literal[...]` as a singleton; CI slice has `provider: ... | None` AND `additional_providers: list[str]`. Multi-type evidence in `DeploymentSlice` survives via `terraform_files` (the additive escape hatch); the cross-slice asymmetry is documented but not equalized.
- **Phase 7 (distroless migration) is unaffected by this probe** — it consumes `manifests.native_modules`, not `deployment`. The probe's main downstream consumers are Phase 3+ planner recipes that pick deployment images to bump. Multi-env consumer-contract resolution (final-design.md Open Q #6) is *their* problem; this story honors the data shape commitment from ADR-0012.

### Deferred patterns (per Rule 2 — premature-abstraction guard)

These are real design opportunities the four critics surfaced; each is deliberately **NOT** lifted in this story because the rule-of-three threshold is not yet met cross-file. Each becomes a Phase 2+ extraction candidate as named.

- **`DeploymentDetector` / `DeploymentParser` ABC + plugin discovery.** Five free functions with uniform signatures is fine; ABC adds friction without payoff. Lift in Phase 4+ when external plugin discovery lands.
- **`parsers/_helm.py` / `parsers/_kustomize.py` per-shape module split.** Phase-1 file count grows without payoff; defer to Phase 2+ if a third deployment shape (`flux`, `argo-cd`) lands and per-parser code crosses 200 lines.
- **`Slice(BaseModel)` Pydantic class.** Building as `dict[str, Any]` + schema-validating via the existing `SchemaValidator` is cheaper. Lift if the slice grows past 12 fields.
- **`SecretName` / `RepoRelativePath` / `YamlPath` `NewType`s.** Premature for Phase 1; bare `str` everywhere. Re-evaluate at Phase 2 if planner-time code starts confusing filesystem-paths with YAML-pointer-paths.
- **Discriminated-union `_ParseOutcome`** (`_ParseSuccess[T] | _ParseFailure`). `_ParseResult` NamedTuple is the minimum that achieves uniform dispatch. Add the discriminated union only when failure-shapes differ meaningfully across parsers (Phase 2+ if `flux` or `argo` needs structured failure-shapes).
- **Shared `probes/_confidence.py` kernel** (`_demote` + `_CONFIDENCE_RANK`). Rule of three is met at S4-03 (`TestInventoryProbe`). Copy verbatim from `node_build_system.py` here; extract at S4-03 once the fourth copy lands. (Matches S4-01's deferred-patterns guidance verbatim.)
- **Shared `probes/_warning_ids.py`** for the import-time ADR-0007 pattern check. Three-line idiom; copy verbatim; extract at ≥ 4 probes. S4-02 is the third consumer; S4-03 is the threshold.
- **YAML catalog for `_DEPLOYMENT_DETECTORS`.** Module-level tuple now; lift to YAML only if a second probe needs the same detector list (unlikely — detectors are deployment-shape-specific).
- **`_WarningCollector` helper class** with `.add(id, **context)` for dedup + ordering. Story has ~9 warning sites; rule of three is met within-file but not cross-file. Defer to S4-03 or when a probe needs cross-helper aggregation.
- **`flux` / `argo-cd` detectors.** Explicitly out-of-scope for Phase 1. With `_DEPLOYMENT_DETECTORS` + `_DEPLOYMENT_PARSERS` in place, adding either is one tuple entry + one parser + one Literal arm + import-time anchor failure if any of the four are forgotten. Documented as the canonical extension example.
