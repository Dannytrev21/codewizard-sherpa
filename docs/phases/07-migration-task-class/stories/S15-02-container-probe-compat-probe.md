# Story S15-02 — `ContainerProbeCompatProbe` + deployment-manifest analysis + blast-radius widening

**Step:** Step 15 — Runtime-compatibility gather (G4, G6, G7–G10, G12)
**Status:** Ready
**Effort:** M
**Depends on:** S13-03 (`S13-03-amendment-a-schemas-and-fence.md` — the Amendment-A probe sub-schema directory `plugins/distroless-migration--node--npm/schema/` exists, the envelope `$ref`-wiring precedent is established, and `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` is already amended per ADR-0029 so this story's new files land inside an already-allowlisted tree)

**ADRs honored:** Phase 7 [ADR-0022](../ADRs/0022-container-probe-compat-and-blast-radius.md) (the migration blast radius includes deployment manifests; `ContainerProbeCompatProbe` analyses K8s/Compose/helm probes); Phase 7 [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (probes live under the plugin, NOT `src/codegenie/probes/`); Phase 7 [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) + [ADR-0029](../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md) (this story is **net-new-files-only** under the already-allowlisted plugin tree); Phase 7 [ADR-0027](../ADRs/0027-migration-observability-bundle.md) (non-deterministic probe rewrites WARN in the PR `transformations_applied` bundle — the WARN *surface* is S18 work; this story emits the slice the bundle reads); Phase 0 ADR-0007 / [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (frozen Probe ABC — two-arg `run(self, repo, ctx)`); Phase 1 ADR-0004 (per-probe sub-schema `additionalProperties: false`); Phase 1 ADR-0007 (warning-ID regex).

## Context

`ContainerProbeCompatProbe` is the **Layer B/C, static, plugin-internal** probe that closes Amendment A gap **G6** (`../final-design.md §Amendment A §A.2`) and is the concrete instance of Amendment A §A.3 **departure #1**: *the migration's blast radius is not just the `Dockerfile`.*

A distroless image has no shell and a reduced binary set. Any container **health or liveness/readiness probe** that depends on a shell or an absent binary silently breaks when the image is swapped:

- Dockerfile `HEALTHCHECK CMD curl -f http://localhost/health` — `curl` is not in a distroless runtime.
- Kubernetes `livenessProbe.exec.command: ["sh", "-c", "..."]` — there is no `/bin/sh`.
- Compose `healthcheck.test: ["CMD-SHELL", "..."]` — same.
- helm chart probe templates that render to either of the above.

The orchestrator sees a green build, a passing `DockerfilePolicyGate`, a merged PR — and a deployment that fails its readiness gate, or worse, **passes a now-no-op `exec` probe and routes traffic to an unhealthy pod**. The design-of-record's gather pipeline never inspects deployment manifests. The **Phase 2 `DeploymentProbe`** (`src/codegenie/probes/deployment.py`) already **locates** `docker-compose.yml`, Kubernetes manifests, and helm charts — but it only *locates* them; it performs zero probe-compatibility analysis. ADR-0022 resolves G6 to a new plugin-internal probe that *analyses* the file set `DeploymentProbe` already finds — **`DeploymentProbe` is not edited.**

The probe emits `ContainerProbeCompatSlice`: one typed record per container probe found, carrying the manifest path, the probe kind, and the specific shell/binary dependency. A module-level `Final` catalog enumerates the probe-shape patterns per manifest family — data-driven, never an `if/elif` on manifest kind.

The blast radius widens deliberately. Where a shell-dependent `exec` probe has a deterministic HTTP-probe equivalent (the app already exposes the health endpoint the `curl` probe targets), the **recipe** rewrites it and the migration PR includes the deployment-manifest change. Where the rewrite is non-deterministic, the finding is a **WARN** in the PR description ([ADR-0027](../ADRs/0027-migration-observability-bundle.md)). **This story ships the probe + the slice only** — the recipe rewrite is S16-02, the WARN-bundle rendering is S18.

The probe lives under `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` — **NOT** under `src/codegenie/probes/`. [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) is explicit; the S5-02 placement fence AST-asserts it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §19 (ContainerProbeCompatProbe)` — names the slice (`per-probe records with manifest path, probe kind, shell/binary dependency`), the Layer B/C placement, and the "consumes the file set `DeploymentProbe` locates" coupling.
  - `../phase-arch-design.md §Component design — Amendment A` preamble — every Amendment-A probe obeys the frozen Probe ABC or the established registry/strategy seams.
- **Phase ADRs:**
  - `../ADRs/0022-container-probe-compat-and-blast-radius.md` — **the governing ADR.** Option B (widen the gather scope via a new compat probe) was adopted; Option A (`Dockerfile`-only) and Option C (defer to a later phase) were rejected. The per-manifest-family `Final` pattern catalog, the `requires` dependency on `DeploymentProbe`, and the WARN-vs-deterministic-rewrite split all come from here.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` is the canonical location.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` + `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md` — ADR-0029 already enumerates `container_probe_compat_probe.py` and its sub-schema; S13-03 landed those rows. This story consumes them.
  - `../ADRs/0027-migration-observability-bundle.md` — non-deterministic probe rewrites become a WARN in `transformations_applied`. The WARN *surface* is S18; this story only emits the slice that bundle reads.
- **Existing code / precedents:**
  - `src/codegenie/probes/deployment.py` — the Phase 2 `DeploymentProbe`. **Read its slice shape.** It locates `docker-compose.yml`, Kubernetes manifests, and helm charts and records their paths. `ContainerProbeCompatProbe` declares `requires = ["deployment"]` and reads `DeploymentProbe`'s located file set from the prior probe's raw output — it does **not** re-discover manifests and does **not** edit `deployment.py`.
  - `src/codegenie/probes/layer_c/dockerfile.py` + `src/codegenie/probes/layer_c/_dockerfile_parse.py` — the Phase 2 Dockerfile-parsing layer. Use it (or `dockerfile-parse`, the Phase 7 parser added in S13-01's window) to read `HEALTHCHECK` instructions. Mirror the `_FILE_GLOBS` discovery shape.
  - `src/codegenie/probes/base.py` — the frozen Probe ABC. Two-arg `run(self, repo, ctx)`.
  - `src/codegenie/probes/registry.py` — `@register_probe` defaults (`heaviness="light"`, `runs_last=False`).
  - `src/codegenie/types/identifiers.py` — newtype-identifier discipline. This story introduces `ManifestPath` (`NewType("ManifestPath", str)` — a repo-relative posix path to a deployment manifest) and uses closed sum types for `ProbeKind` and `ManifestFamily`.
  - YAML parsing — the repo already depends on `pyyaml` (used by the catalog loaders). K8s/Compose manifests are YAML; use `yaml.safe_load` (never `yaml.load`). helm templates are *un-rendered* YAML-with-Go-templating — parse conservatively (see AC-9).
- **Story-pipeline neighbors:**
  - `S13-03-amendment-a-schemas-and-fence.md` — **must land first.** Established the `schema/` directory, the `$ref`-wiring pattern, and the ADR-0029 allowlist amendment.
  - `S7-01-base-image-probe.md` — the structural template for any Amendment-era Phase 7 plugin probe. Mirror it.
  - `S15-01-runtime-shell-invocation-probe.md` — sibling Step-15 probe; same metadata-AC + purity-fence shape. Land independently.
  - `S16-02-recipe-contract-amendment.md` — the recipe consumes `ContainerProbeCompatSlice` to rewrite deterministic `exec`/`curl` probes into HTTP-probe form. Downstream consumer.
  - `S12-01-phase7-fixture-portfolio.md` — the fixture-portfolio story; deployment-manifest fixtures may be co-located there. This story carries its own targeted fixtures.

## Goal

Land `ContainerProbeCompatProbe` under `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` as a Probe-ABC-conformant, `@register_probe`-decorated, Layer-B/C, `task_specific`, `applies_to_tasks=["distroless-migration"]` probe that — given the deployment-manifest file set the Phase 2 `DeploymentProbe` already located — statically analyses each Dockerfile `HEALTHCHECK`, Kubernetes `livenessProbe`/`readinessProbe`/`startupProbe`, Compose `healthcheck`, and helm probe template for **shell or absent-binary dependence**, classifies each against a module-level `Final` per-manifest-family pattern catalog, and emits the deterministic `ContainerProbeCompatSlice` the migration recipe consumes to widen the PR's blast radius into deployment manifests. No subprocess, no network, no manifest re-discovery.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` exists. `ContainerProbeCompatProbe(Probe)` is defined with class attributes `name = "container_probe_compat"`, `layer = "C"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `requires = ["deployment"]`, `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/docker-compose.yml", "**/docker-compose.yaml", "**/*.yaml", "**/*.yml"]`, `cache_strategy = "content"`, `timeout_seconds = 60`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_metadata.py::test_probe_metadata_shape` (reads `__dict__`, asserts each field byte-equal).
- [ ] **AC-2** `ContainerProbeCompatProbe` is registered via `@register_probe` (defaults — `heaviness="light"`, `runs_last=False`). The `requires = ["deployment"]` entry is the load-bearing coupling — the coordinator orders `DeploymentProbe` first. `test_container_probe_compat_metadata.py::test_registry_entry_present` constructs a fresh `Registry`, imports the module, and asserts `entry.probe_cls is ContainerProbeCompatProbe AND entry.heaviness == "light"`; `test_requires_deployment` asserts `"deployment" in ContainerProbeCompatProbe.requires`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the only abstract-method override; signature matches the frozen Phase 0 ABC byte-for-byte. `test_container_probe_compat_metadata.py::test_run_signature_matches_abc` AST-asserts the parameter list is exactly `["self", "repo", "ctx"]`.

**Slice shape (AC-4 through AC-6)**
- [ ] **AC-4** Slice shape (returned in `ProbeOutput.schema_slice["container_probe_compat"]`):
  ```python
  {
      "probes": [
          {
              "manifest_path": "<repo-relative-posix-path>",
              "manifest_family": "dockerfile|kubernetes|compose|helm",
              "probe_kind": "healthcheck|liveness|readiness|startup",
              "probe_form": "exec|cmd_shell|http_get|tcp_socket|grpc",
              "shell_dependency": "<None | 'sh' | 'bash'>",      # the shell binary the probe invokes, if any
              "binary_dependency": "<None | str>",               # e.g. 'curl', 'wget' — the non-distroless binary, if any
              "rewritable": <bool>,                              # True iff a deterministic HTTP-probe equivalent exists
          }, ...
      ],
      "confidence": "high|medium|low",
  }
  ```
  `probes` is sorted deterministically by `(manifest_path, probe_kind)`. Verified against `tests/golden/probes/container_probe_compat/*.json`; the **field set + key order + sort order** is pinned by this story's AC.
- [ ] **AC-5** `_PROBE_PATTERN_CATALOG: Final[tuple[ProbePattern, ...]]` is a module-level open/closed catalog. Each `ProbePattern` is a frozen dataclass with fields `(manifest_family: ManifestFamily, matcher: ..., classify: ...)` where `ManifestFamily` is a closed `Literal`/`StrEnum`. The catalog is iterated in `_analyse_manifest(path, family, content) -> list[_ProbeRecord]`, **never branched on with a chained `if/elif` on manifest family**. Verified by `test_analysis_uses_pattern_catalog.py::test_no_if_chain_on_manifest_family` — AST-walks `_analyse_manifest` and asserts no `if/elif` arm does string equality against a manifest-family literal (`"kubernetes"`, `"compose"`, …). The catalog covers at minimum: Dockerfile `HEALTHCHECK` (`curl`/`wget`/shell form), K8s `exec` probe, K8s `httpGet`/`tcpSocket`/`grpc` probe, Compose `healthcheck.test` (`CMD-SHELL` and `CMD` form), helm probe template.
- [ ] **AC-6** `probe_kind`, `probe_form`, and `manifest_family` are each a closed sum type (`Literal`/`StrEnum`), never a free string; `shell_dependency` and `binary_dependency` are `Optional` typed values. `test_typed_fields.py::test_probe_fields_are_typed` reads the slice from the K8s-exec fixture and asserts every `probe_kind` / `probe_form` / `manifest_family` value is a member of its closed set. A freeform value fails this test.

**Behavior — detection + classification (AC-7 through AC-12)**
- [ ] **AC-7** K8s `exec` liveness probe flagged — fixture `tests/fixtures/portfolio/container-probe-k8s-exec/k8s/deployment.yaml` with a `livenessProbe.exec.command: ["sh", "-c", "pgrep node"]` → slice has exactly one `probes` record: `manifest_family == "kubernetes"`, `probe_kind == "liveness"`, `probe_form == "exec"`, `shell_dependency == "sh"`, `binary_dependency == None`. `test_container_probe_compat_behavior.py::test_k8s_exec_liveness_flagged` asserts every field. This is the ADR-0022 case — `exec` against `sh` silently breaks on distroless.
- [ ] **AC-8** `HEALTHCHECK curl` flagged — fixture `tests/fixtures/portfolio/container-probe-dockerfile-curl/Dockerfile` with `HEALTHCHECK CMD curl -f http://localhost:3000/health` → slice has one record: `manifest_family == "dockerfile"`, `probe_kind == "healthcheck"`, `binary_dependency == "curl"`, `shell_dependency == None`, `rewritable == True` (a `curl` against a literal HTTP URL has a deterministic HTTP-probe equivalent). `test_container_probe_compat_behavior.py::test_healthcheck_curl_flagged` asserts the fields and that `rewritable is True`.
- [ ] **AC-9** HTTP-form probe **not** flagged — fixture `tests/fixtures/portfolio/container-probe-k8s-httpget/k8s/deployment.yaml` with a `readinessProbe.httpGet.path: /healthz` (the kubelet performs the HTTP request itself — no shell, no binary) → the slice still emits a record for the probe (`probe_form == "http_get"`) but with `shell_dependency == None`, `binary_dependency == None`, and the record is **not** a compatibility hazard. `test_container_probe_compat_behavior.py::test_httpget_probe_not_a_hazard` asserts the record's `shell_dependency` and `binary_dependency` are both `None` and that a module-level `_is_hazard(record) -> bool` returns `False` for it and `True` for the AC-7 `exec` record. **Clarification:** the slice records *every* probe found (so a consumer can see the full deployment-probe surface); `_is_hazard` is the predicate that separates the breaking ones — an `httpGet` probe is recorded but is never a hazard.
- [ ] **AC-10** Compose `CMD-SHELL` healthcheck flagged — fixture `container-probe-compose-cmdshell/docker-compose.yml` with `healthcheck: { test: ["CMD-SHELL", "curl -f localhost/health || exit 1"] }` → record: `manifest_family == "compose"`, `probe_kind == "healthcheck"`, `probe_form == "cmd_shell"`, `shell_dependency` is the implicit shell (`"sh"`), `binary_dependency == "curl"`. The `CMD-SHELL` form *always* invokes a shell — `_is_hazard` returns `True` even if the command itself looked benign.
- [ ] **AC-11** helm probe template — fixture `container-probe-helm/chart/templates/deployment.yaml` with a `livenessProbe.exec.command` inside Go-template (`{{- if .Values.probes.enabled }}`) markup → the probe parses the template **conservatively**: it detects the `exec` probe shape, emits a record with `manifest_family == "helm"`, and downgrades `confidence` to `"medium"` because templating obscures the fully-rendered probe. `test_container_probe_compat_behavior.py::test_helm_template_conservative` asserts the record is emitted and `confidence == "medium"`. ADR-0022: helm charts are analysed as templates pre-render, conservatively, with `low`/`medium` confidence where templating obscures the shape.
- [ ] **AC-12** No-deployment-manifest case — fixture `container-probe-none/` with a `Dockerfile` that has **no** `HEALTHCHECK` and no K8s/Compose/helm files → slice has `probes == []`, `confidence == "high"`. `test_container_probe_compat_behavior.py::test_empty_when_no_deployment_manifests` asserts the empty slice is well-formed (`probes` present as an empty list) and `confidence == "high"` — a repo with no deployment probes is high-confidence, not low.

**Degraded path + warning-ID discipline (AC-13 through AC-15)**
- [ ] **AC-13** Malformed-manifest path — fixture with a K8s YAML file containing a syntax error (unbalanced indentation / a tab) → the probe appends `"container_probe_compat.manifest_parse_failed"` to `warnings` (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007), skips that file, continues to the rest, and downgrades `confidence` to `"low"`. **No exception escapes `run()`** — a `yaml.YAMLError` is folded to the warning. `test_container_probe_compat_degraded.py::test_malformed_manifest_warns_and_continues` asserts (a) the warning ID is present and regex-valid, (b) a valid sibling manifest still contributes its records, and (c) `pytest.raises(BaseException)` confirms nothing escapes.
- [ ] **AC-14** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"container_probe_compat.manifest_parse_failed"})` exists; an import-time `raise AssertionError(...)` (NOT a bare `assert`) checks each ID against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Pattern mirrors S7-01's `_WARNING_IDS` block.
- [ ] **AC-15** `confidence` ladder: `"high"` when every analysed manifest parsed cleanly and contained no helm templating; `"medium"` when a helm template obscured a probe shape (AC-11); `"low"` when any manifest failed to parse (AC-13). `test_confidence_ladder.py::test_confidence_ladder` asserts `high` on the K8s-httpGet fixture, `medium` on the helm fixture, and `low` on the malformed fixture.

**Fence + lint discipline (AC-16 through AC-19)**
- [ ] **AC-16** AST-walk purity fence: `tests/fence/test_container_probe_compat_probe_purity.py` walks `container_probe_compat_probe.py` and rejects `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen`, `shell=True`, `requests.*`, `urllib.request.urlopen`, `httpx.*`, any LLM-SDK import (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`), **and any `yaml.load(` call that is not `yaml.safe_load`** (an unsafe-YAML-load fence — a deployment manifest is untrusted input). Three planted-violation parametrized cases prove the walker fires. The fence file uses `raise AssertionError("...")` — bare `assert` is forbidden.
- [ ] **AC-17** `make lint-imports` green; the new file introduces no forbidden import path. The S5-03 import-linter contract already covers `plugins/distroless-migration--*/` against LLM SDKs.
- [ ] **AC-18** `ruff check`, `ruff format --check`, `mypy --strict plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` all clean. **No `Any` in annotations** — the Phase 7 `test_no_any_in_plugin_surface` discipline applies. The probe must **not import `src/codegenie/probes/deployment.py` directly** to read its output — it consumes `DeploymentProbe`'s raw output via the coordinator's `requires`-ordered prior-probe-output channel (the same way Layer-B probes read Layer-A raw JSON). Reaching into another probe's module is a structural smell `mypy`/`lint-imports` does not catch — the implementer-notes call it out.
- [ ] **AC-19** Phase 7 ADR-0009 byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) green: this story adds files only under `plugins/distroless-migration--node--npm/` and `tests/`; the one envelope-schema `$ref` insertion is at an ADR-0029-allowlisted path (landed by S13-03). No Phase 0–6.5 file is touched — in particular **`src/codegenie/probes/deployment.py` is not edited.**

## Implementation outline

1. **Net-new files only — no edits to Phase 0–6.5.** Create:
   - `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` — the probe + private helpers.
   - `plugins/distroless-migration--node--npm/schema/container_probe_compat.schema.json` — the sub-schema (`additionalProperties: false` at every node), wired into `repo_context.schema.json` with one additive `$ref` following S13-03's precedent.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_metadata.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_behavior.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_degraded.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_analysis_uses_pattern_catalog.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_typed_fields.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py`
   - `tests/fence/test_container_probe_compat_probe_purity.py`
   - Fixture trees under `tests/fixtures/portfolio/container-probe-{k8s-exec,dockerfile-curl,k8s-httpget,compose-cmdshell,helm,none,parse-failed}/`.

2. **Module-level data (Open/Closed pattern catalog) in `container_probe_compat_probe.py`:**
   ```python
   from typing import Final, Literal
   from dataclasses import dataclass
   import re

   ManifestFamily = Literal["dockerfile", "kubernetes", "compose", "helm"]
   ProbeKind = Literal["healthcheck", "liveness", "readiness", "startup"]
   ProbeForm = Literal["exec", "cmd_shell", "http_get", "tcp_socket", "grpc"]

   @dataclass(frozen=True)
   class ProbePattern:
       manifest_family: ManifestFamily
       # matcher: extracts probe records from a parsed manifest of this family
       # classify: maps a raw probe to (probe_kind, probe_form, shell_dep, binary_dep)

   _PROBE_PATTERN_CATALOG: Final[tuple[ProbePattern, ...]] = (
       ProbePattern("dockerfile", ...),
       ProbePattern("kubernetes", ...),
       ProbePattern("compose", ...),
       ProbePattern("helm", ...),
   )

   _SHELL_BINARIES: Final[frozenset[str]] = frozenset({"sh", "bash"})
   _NON_DISTROLESS_BINARIES: Final[frozenset[str]] = frozenset({"curl", "wget", "nc", "ncat", "ping"})

   _WARNING_IDS: Final[frozenset[str]] = frozenset({"container_probe_compat.manifest_parse_failed"})
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")
   ```

3. **`_manifest_family(path: str) -> ManifestFamily | None`:**
   - Pure path/content classifier. `Dockerfile`/`Dockerfile.*` → `dockerfile`. `docker-compose.{yml,yaml}` → `compose`. A YAML file under a `templates/` directory of a directory containing `Chart.yaml` → `helm`. A YAML file with a top-level `kind:`/`apiVersion:` → `kubernetes`. Anything else → `None` (not a deployment manifest — skip).

4. **`_is_hazard(record: _ProbeRecord) -> bool`:**
   - Pure predicate: `True` iff `record.shell_dependency is not None` **or** `record.binary_dependency is not None`. An `http_get`/`tcp_socket`/`grpc` probe is never a hazard.

5. **`_analyse_manifest(path, family, content) -> list[_ProbeRecord]`:**
   - Iterate `_PROBE_PATTERN_CATALOG`, select the entries matching `family`, run each matcher against the parsed content. Catalog-driven — no `if/elif` on `family` (AC-5).
   - Dockerfile: parse `HEALTHCHECK` instructions; extract the command; the first token is the binary, `CMD-SHELL`-equivalent shell forms set `shell_dependency`.
   - K8s: `yaml.safe_load`; walk `spec.template.spec.containers[].{livenessProbe,readinessProbe,startupProbe}`; an `exec.command` whose first token is `sh`/`bash` sets `shell_dependency`; `httpGet`/`tcpSocket`/`grpcAction` set `probe_form` with no dependency.
   - Compose: `yaml.safe_load`; walk `services.*.healthcheck.test`; `["CMD-SHELL", ...]` always sets `shell_dependency="sh"`; `["CMD", "curl", ...]` sets `binary_dependency`.
   - helm: parse the template text conservatively — strip Go-template directives, then `yaml.safe_load` the remainder if possible; detect the `exec`/`httpGet` probe shape; flag `confidence` degraded.

6. **`rewritable` determination:** a record is `rewritable` iff its probe targets a literal HTTP URL (a `curl http://...`/`wget http://...` healthcheck, or a `CMD-SHELL` whose command is a single literal-URL `curl`) — the deterministic HTTP-probe equivalent. A shell command doing anything beyond a single literal-URL fetch is `rewritable == False`. This is a conservative judgment — over-cautious `False` is acceptable, over-confident `True` is not (ADR-0022).

7. **`async def run(self, repo, ctx) -> ProbeOutput`:**
   - `t0 = time.perf_counter()`.
   - Read the located deployment-manifest paths from `DeploymentProbe`'s raw output (the `requires`-ordered prior-probe channel). If `DeploymentProbe` located nothing, the probe still scans for a `Dockerfile` `HEALTHCHECK` via its own globs (a Dockerfile is always in scope; `DeploymentProbe` covers Compose/K8s/helm).
   - For each manifest: classify the family, parse, `_analyse_manifest`, accumulate records. On `yaml.YAMLError`/parse failure → append the warning, skip, continue.
   - Sort `probes` by `(manifest_path, probe_kind)`.
   - `confidence`: `low` if any parse failed; else `medium` if any helm template was analysed; else `high`.
   - Return `ProbeOutput(schema_slice={"container_probe_compat": {...}}, raw_artifacts=[], confidence=..., duration_ms=..., warnings=warnings, errors=[])`.

8. **Fixtures:** each fixture is a minimal deployment-manifest tree — see AC-7…AC-13 for exact contents. The `container-probe-none` fixture must contain a `Dockerfile` *without* a `HEALTHCHECK` so it proves the catalog does not over-match.

## TDD plan — red / green / refactor

**Red** — write `test_container_probe_compat_metadata.py::test_probe_metadata_shape` first. It does `from plugins.distroless_migration_node_npm.probes.container_probe_compat_probe import ContainerProbeCompatProbe` and asserts every metadata field — including `requires == ["deployment"]`. Run pytest — fails with `ModuleNotFoundError`.

**Green** — minimum code: create the module with the class skeleton (metadata attributes only; `async def run` raising `NotImplementedError`). Re-run pytest — metadata test green; behavior tests still fail.

**Red+** — write `test_container_probe_compat_behavior.py::test_k8s_exec_liveness_flagged` (AC-7). It builds the `container-probe-k8s-exec` fixture, runs the probe, and asserts the single record's fields. Pytest fails on `NotImplementedError`.

**Green+** — implement `run()`, `_analyse_manifest`, `_manifest_family`, `_is_hazard` for the K8s `exec` pattern. Iterate over AC-8…AC-12, adding one `ProbePattern` row + one fixture at a time. Each new family turns its red behavior test green without editing `_analyse_manifest`'s control flow (proves AC-5's catalog design).

**Red++** — write `test_analysis_uses_pattern_catalog.py::test_no_if_chain_on_manifest_family` with a planted-violation stub (`if family == "kubernetes": ...`). The AST walker is not written → pytest fails.

**Green++** — implement the AST walker; the planted-violation case goes red-by-construction, the real `_analyse_manifest` passes.

**Red+++** — write `test_container_probe_compat_probe_purity.py::test_no_unsafe_yaml_load` with a planted `yaml.load(...)`. The purity walker is not written → fails.

**Green+++** — implement the purity AST walker; three planted-violation parametrize rows (`subprocess.run`, `yaml.load(`, `requests.get`) all show red-by-construction.

**Refactor** — extract `_manifest_family`, `_is_hazard`, the pattern catalog, and per-family matchers into module-level pure functions; confirm `run()` is the only impure code. AST-assert `_analyse_manifest` and `_manifest_family` have no chained `if/elif` on a manifest-family literal.

## Files to touch

**New files (no Phase 0–6.5 byte-edits except the one ADR-0029-allowlisted `$ref`):**

| Path | Purpose |
|---|---|
| `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` | The probe + private helpers + module-level pattern catalog |
| `plugins/distroless-migration--node--npm/schema/container_probe_compat.schema.json` | Per-probe sub-schema (`additionalProperties: false` at every node) |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_metadata.py` | AC-1, AC-2, AC-3 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_behavior.py` | AC-7…AC-12 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_container_probe_compat_degraded.py` | AC-13 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_analysis_uses_pattern_catalog.py` | AC-5 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_typed_fields.py` | AC-4, AC-6 |
| `tests/unit/plugins/distroless_migration_node_npm/probes/test_confidence_ladder.py` | AC-15 |
| `tests/fence/test_container_probe_compat_probe_purity.py` | AC-16 |
| `tests/fixtures/portfolio/container-probe-*/...` | Seven deployment-manifest fixture trees (AC-7…AC-13) |

**Edited (ADR-0029-allowlisted, S13-03 established the precedent):**

| Path | Edit |
|---|---|
| `src/codegenie/schema/repo_context.schema.json` | One additive `$ref` for `container_probe_compat` under `properties.probes` |

**Files NOT touched** (would fail Phase 7 ADR-0009 fence): `src/codegenie/probes/` — **especially `src/codegenie/probes/deployment.py`** (`DeploymentProbe` is consumed via the `requires` channel, never edited) — `src/codegenie/exec/`, `pyproject.toml`, the plugin loader.

## Out of scope

- **The recipe rewrite of an `exec`/`curl` probe into HTTP-probe form** — S16-02 (`DockerfileMultiStageRefactorTransform` / the deployment-manifest transform) consumes `ContainerProbeCompatSlice` and produces the manifest diff. This story ships the slice + the `rewritable` flag + `_is_hazard`; it produces no diff.
- **Editing `DeploymentProbe`** — Phase 2's `DeploymentProbe` only *locates* manifests and stays unchanged (ADR-0022 is explicit). This probe declares `requires = ["deployment"]` and reads its output via the coordinator channel.
- **Rendering helm charts** — the probe analyses helm templates *pre-render*, conservatively. A `helm template`-style render (which would need the `helm` CLI in `ALLOWED_BINARIES`) is deliberately not done; templating ambiguity is surfaced as `confidence == "medium"`.
- **The `transformations_applied` WARN bundle / PR-description rendering** — S18 (`../ADRs/0027-migration-observability-bundle.md`) owns the WARN surface. This story emits the slice the bundle reads.
- **Plugin loader explicit-import wiring + `api.py` side-effect import** — S8-03 / the plugin's `api.py`.
- **`MigrationConfidence` aggregation** — S17-01 consumes `ContainerProbeCompatSlice.confidence`; downstream.
- **Perf bench** — a `@pytest.mark.bench` body lands in S12-05.

## Notes for the implementer

- **Rule 8 — read before you write.** Read `src/codegenie/probes/deployment.py`'s slice/raw-output shape *first* — this probe's `requires = ["deployment"]` contract binds to whatever path-list field `DeploymentProbe` emits. If `DeploymentProbe`'s output does not cleanly expose the located file paths, STOP and surface it — do not reach into `deployment.py`'s internals or re-implement manifest discovery. The `requires`-channel coupling is the whole point of ADR-0022's "reuse Phase 2 `DeploymentProbe`'s file-location output."
- **Rule 12 — fail loud.** A `yaml.YAMLError` on an untrusted deployment manifest is a *typed warning* with `confidence` downgraded to `low` — not a swallowed error and not a crash. A helm template the probe cannot fully resolve is `confidence == "medium"`, never silently `high`. Catch the **specific** `yaml.YAMLError` — a bare `except Exception` is forbidden by `mypy --strict` config.
- **Rule 9 — tests verify intent.** The behavior tests assert business semantics: "a K8s `exec: ['sh', '-c', ...]` liveness probe is flagged because distroless has no `/bin/sh` to run it" — not "the function returns a list". AC-9's paired assertion (`_is_hazard` is `False` for `httpGet`, `True` for `exec`) is the load-bearing intent test — it proves the probe distinguishes a *breaking* probe from a *recorded-but-safe* one, the exact distinction G6 needs.
- **`yaml.safe_load`, never `yaml.load`.** A deployment manifest is untrusted input. `yaml.load` without a safe loader can execute arbitrary Python on a crafted manifest. The purity fence (AC-16) enforces this; the `forbidden-patterns` pre-commit hook does *not* catch `yaml.load` specifically, so the fence is the load-bearing defense.
- **The slice records every probe, `_is_hazard` separates the breaking ones.** Do not filter `httpGet`/`tcpSocket` probes out of the slice — a consumer (and a human reviewer) benefits from seeing the *full* deployment-probe surface, with `_is_hazard` as the predicate that flags the migration-breaking subset. Conflating "recorded" with "hazard" would hide the safe probes and make the slice less legible.
- **Open/Closed pattern catalog (toolkit pattern).** `_PROBE_PATTERN_CATALOG` is the open/closed seam — adding a new manifest family (a future `nomad` job spec, a `systemd` unit) is **one new `ProbePattern` row**, not an edit to `_analyse_manifest`. The AST fence (AC-5) is the enforcer.
- **Blast radius is the headline.** ADR-0022's whole premise is that the migration PR now *legitimately* touches deployment manifests. This probe is the gather half — it makes the breakage *visible* so S16-02's recipe can rewrite it or WARN. An operator reviewing the PR will see manifest changes; the `transformations_applied` bundle (S18) names every one. This story does not surprise anyone — it produces the evidence that justifies the wider diff.
- **Effort budget.** Probe body ≤ 160 LOC; tests ≈ 300 LOC; fence ≈ 60 LOC. If the body grows past 190 LOC, extract the per-family matchers into `_probe_matchers.py`.
- **Token-budget guard (Rule 6).** Single-session-implementable at ~4k tokens. If helm-template parsing proves brittle (Go-template directives that break `yaml.safe_load` even after stripping), STOP and surface — a *regex-only* helm pass that detects the `exec:`/`httpGet:` probe shape and always reports `confidence == "medium"` is an acceptable conservative fallback and matches ADR-0022's "report `low` confidence where templating obscures the probe shape."
