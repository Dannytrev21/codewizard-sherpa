# Phase 01 — Context gathering: Layer A (Node.js): Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12
**Companions (parallel):** `design-performance.md`, `design-security.md`
**Source of truth for scope:** [`docs/roadmap.md` "Phase 1"](../../roadmap.md), [`localv2.md` §4–§8, §12](../../localv2.md), `docs/production/design.md §2` (load-bearing commitments), `docs/phases/00-bullet-tracer-foundations/final-design.md`.

---

## Lens summary

Phase 0 planted the spine: the probe contract, async coordinator, content-addressed cache, layered JSON Schema, output sanitizer, subprocess allowlist, audit anchor. Phase 1's job is **not to extend that spine but to populate it** — five new probes (`NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`) alongside the existing `LanguageDetection`, each in its own module, each declaring its `applies_to_languages`, `applies_to_tasks`, and `declared_inputs`, each owning one schema slice under `src/codegenie/schema/probes/`, each exhaustively unit-tested against fixture Node.js repos.

The best-practices bet: **the Phase 0 contract is the budget, not a starting point.** Every Phase 1 component lives in a file that Phase 0 anticipated. No new top-level packages. No "Phase 1 wrapper" layer around the Phase 0 coordinator. No bespoke fixture harness — `pytest`'s `tmp_path` plus a `fixtures/` directory of committed minimal Node.js repos is the entire fixture story. The probe ABC stays byte-for-byte `localv2.md §4` (per [phase-0 ADR-0007](../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md)); the snapshot test continues to enforce it.

The deepest commitment in this lens [Rule 11, Rule 8]: **conformance over taste**. The Phase 0 cache returns `ProbeOutput` directly via the `Ran | CacheHit | Skipped` pass-through (final-design §2.6); Phase 1 reads that contract and uses it as-is. The Phase 0 sanitizer two-pass remains the only path to disk; Phase 1 probes hand their `ProbeOutput` to the coordinator and never touch the writer. The Phase 0 `additionalProperties` layering (final-design §2.9) is the extension hook for new probe sub-schemas — Phase 1 adds five `$ref`s and five files under `schema/probes/`, period.

---

## Conventions honored

- **No LLM in the gather pipeline** ([ADR-0005](../../production/adrs/0005-no-llm-in-gather-pipeline.md), `production/design.md §2.1`) → Every Phase 1 probe is pure Python parsing of files on disk (YAML, JSON, lockfile formats) plus, for `TestInventory`, a `tree-sitter` AST query routed through the existing subprocess allowlist. The Phase 0 `fence` CI job (final-design §3.2 job 6) continues to assert the dependency closure contains no LLM SDK; Phase 1 adds no LLM SDK, so the fence stays green by default. The `pyproject.toml` extras shape from final-design §2.2 is preserved — no probe imports `anthropic`, `langgraph`, or any other agent SDK.
- **Facts, not judgments** (`production/design.md §2.2`) → `NodeManifest` emits `native_modules: [{name, version, requires_node_gyp, binary_artifacts, system_deps_required}]` from a hand-curated catalog. It does **not** emit `safe_for_distroless: true`. `CI` emits `image_build_command: "docker build -t ..."`; it does not emit `ci_appropriate_for_migration: true`. `Deployment` emits `security_context.run_as_user: 1000`; it does not emit `production_ready: true`. The `_ProbeOutputValidator`'s recursive `JSONValue` type from Phase 0 (final-design §2.3) structurally rejects any field that would carry judgment-shaped data — there is no `Literal["safe", "unsafe"]` type in the schema; there are counts, paths, versions, presence flags.
- **Honest confidence** (`production/design.md §2.3`) → Every Phase 1 probe reports `confidence: high | medium | low` and an explicit `warnings` list. A `NodeBuildSystem` run that finds three lockfiles (a real failure mode in Node monorepos) reports `confidence: low` and `warnings: ["multiple lockfiles detected: pnpm-lock.yaml, package-lock.json, yarn.lock"]`. A `CI` run on a repo with no recognized CI provider reports `applies()` → `True` (the slice still has to exist) with `confidence: low`, `warnings: ["no recognized CI provider; checked: .github/workflows/, .gitlab-ci.yml, .circleci/, Jenkinsfile"]`. **No probe overclaims by silence.**
- **Extension by addition** (`production/design.md §2.5`, [ADR-0007 production](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)) → Each Phase 1 probe is one new file under `src/codegenie/probes/`, one new sub-schema under `src/codegenie/schema/probes/`, one new test module under `tests/unit/probes/`, one new entry in the explicit registry import list in `src/codegenie/probes/__init__.py`. **Zero edits to** `coordinator.py`, `cache/`, `output/`, `audit.py`, `schema/validator.py`, `exec.py`. The Phase 0 `test_probe_contract.py` snapshot test fails CI if the ABC drifts; Phase 1 must not trigger it.
- **Determinism over probabilism** (`production/design.md §2.4`, [ADR-0006](../../production/adrs/0006-continuous-deterministic-gather.md)) → Parsers are deterministic (`json.loads`, `yaml.safe_load`, `tomllib`, `tree_sitter`). No LLM, no heuristic fuzzy matching, no probabilistic classifiers. The native-module catalog (`src/codegenie/catalogs/native_modules.yaml`) is a flat YAML lookup table; expanding it is a data edit, not a code change.
- **Organizational uniqueness as data, not prompts** (`production/design.md §2.6`) → The native-module catalog and the CI-provider detection table are both YAML data files loaded at module import. Adding a new native module (e.g., `node-rdkafka`) is a one-line YAML PR. Adding a new CI provider (e.g., Buildkite) is a new entry in `src/codegenie/probes/ci_providers.yaml`.
- **Progressive disclosure** (`production/design.md §2.7`) → `repo-context.yaml` continues to index, not inline. Phase 1 probes write large raw artifacts under `.codegenie/context/raw/<probe>.json` (the lockfile dump from `NodeManifest`, the parsed Jenkinsfile from `CI`, the rendered Helm values from `Deployment`); the YAML manifest only references them by relative path.
- **Humans always merge** (`production/design.md §2.8`, [ADR-0009](../../production/adrs/0009-humans-always-merge.md)) → N/A in Phase 1 (no PRs opened).
- **Cost observability** (`production/design.md §2.9`, [ADR-0024](../../production/adrs/0024-cost-observability-end-to-end.md)) → Per-probe wall-clock continues to be recorded in the audit anchor (final-design §2.12). Phase 1 adds five more entries to that record; the cost ledger of Phase 13 will read this same audit record.

---

## Goals (concrete, measurable)

- **Public API surface (count):** 0 new public modules. Phase 1 adds private modules only (probes and their per-probe sub-schemas). The public API of `codegenie` remains the CLI plus `__version__`.
- **New top-level packages:** 0. Probes land in the existing `src/codegenie/probes/` package; sub-schemas land in `src/codegenie/schema/probes/`; catalogs land in a new sibling `src/codegenie/catalogs/` (this is the *only* new directory — declared explicitly so the synthesizer notices, and because catalogs are *data*, not code).
- **Net new Python files in `src/`:** 5 probe modules + 1 catalog loader + 5 sub-schema JSON files + 1 `catalogs/native_modules.yaml` + 1 `catalogs/ci_providers.yaml`. ≤ 12 files total.
- **Net new lines of `src/` Python (excluding catalogs):** target ≤ 1100 lines, hard ceiling 1500. Each probe should be ~150–250 lines of clear parsing logic plus a 30–50-line `__init__`-style declaration.
- **Net new lines of test code:** target ≥ 1.4× source-code lines (the test-pyramid bias). Phase 1 lands roughly 1500–1800 lines of test code against ~1100 lines of source — *this ratio is the convention, not a vanity metric*; see "Test plan" below.
- **Test coverage target:** ratchet from Phase 0's 85 / 75 floor to **90% line / 80% branch** on `src/codegenie/` excluding `cli.py`. (Per final-design §3.3 the floor was always intended to ratchet up at Phase 1; this delivers on that commitment.)
- **Cyclomatic complexity ceiling per function:** **10** (enforced via `ruff` rule `C901`). Probes that exceed it must split into helper functions; this is a Rule 2 (Simplicity First) tripwire. The lockfile parser will likely sit at 8–9 — close, but inside the bound.
- **Plain Python vs framework-coupled code ratio:** ≥ 95% plain Python. The only framework-coupled paths are the `click` decorator on `cli.py` (Phase 0) and `pydantic` inside `_ProbeOutputValidator` (Phase 0); Phase 1 adds **zero** new framework couplings. No probe imports `pydantic`, `click`, `structlog` directly — they use the existing facades.
- **External tool surface added to `exec.ALLOWED_BINARIES`:** **1** (`node`, used by `NodeBuildSystem` for `node --version` engine-constraint cross-check). Each binary addition requires its own ADR amendment per Phase 0 §2.5. (We deliberately do *not* add `pnpm`, `npm`, `yarn` as binaries — we read their lockfiles, we do not invoke them. Lockfile-parsing is what makes the gather deterministic and cache-friendly.)
- **Cache hit rate target on second run** (Phase 1 exit-criterion): **100% of Phase 1 probes return `CacheHit`** when no `declared_inputs` have changed. Verified by `tests/integration/test_cache_hit_on_real_repo.py` against an open-source Node.js fixture.
- **Wall-clock target for the cold integration run on the real-OSS fixture:** p50 ≤ 4s, p95 ≤ 8s. Warm (cache-hit): p50 ≤ 0.4s. These are *targets surfaced as advisory CI dashboard metrics*, not blocking gates (per Phase 0 §2.11 the cold-start canary is advisory).
- **Pre-commit / lint / type-check posture:** unchanged from Phase 0. `ruff` + `mypy --strict` on `src/` + `forbidden-patterns` continue. Phase 1 must pass the existing hooks with zero suppressions, zero `# type: ignore`, zero `# noqa`. If a rule fires legitimately, surface it (Rule 12) — don't suppress it.

---

## Architecture

```
                              codegenie gather <path>
                                       │
                                       ▼
                         ┌────────────────────────────┐
                         │  Phase 0 CLI entry (click) │   ← unchanged
                         │  - path validation         │
                         │  - tool-readiness check    │
                         │  - config load             │
                         │  - .gitignore prompt       │
                         └──────────────┬─────────────┘
                                        │
                                        ▼
                         ┌────────────────────────────┐
                         │  Phase 0 Coordinator       │   ← unchanged
                         │  - asyncio.Semaphore       │
                         │  - per-probe Task          │
                         │  - cache lookup / pass-thru│
                         │  - _ProbeOutputValidator   │
                         │  - OutputSanitizer.scrub   │
                         └──────────────┬─────────────┘
                                        │
                                        ▼
       ┌────────────────────────────────┴────────────────────────────────┐
       │       Phase 0 Probe Registry (explicit import — no entry pts)    │
       │                                                                  │
       │  language_detection (Phase 0)   ← unchanged                      │
       │                                                                  │
       │  ┌──────────────── Phase 1 additions ──────────────────────────┐ │
       │  │                                                              │ │
       │  │  node_build_system   ┐                                       │ │
       │  │  node_manifest       ├─ each: one file in probes/            │ │
       │  │  ci                  │  each: one sub-schema in schema/probes/│ │
       │  │  deployment          │  each: declares applies_to_languages, │ │
       │  │  test_inventory      ┘   applies_to_tasks, declared_inputs   │ │
       │  │                                                              │ │
       │  └──────────────────────────────────────────────────────────────┘ │
       └──────────────────────────────────────────────────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────────────┐
              │                         │                                 │
              ▼                         ▼                                 ▼
       ┌──────────────┐         ┌──────────────┐                ┌──────────────────┐
       │ Phase 0 Cache│         │ Phase 0 Audit│                │ Phase 0 Sanitizer│
       │  unchanged   │         │  unchanged   │                │   unchanged      │
       └──────┬───────┘         └──────────────┘                └──────┬───────────┘
              │                                                        │
              ▼                                                        ▼
       .codegenie/cache/                                    .codegenie/context/
       (Phase 0 layout)                                     ├── repo-context.yaml
                                                            ├── schema-version.txt
                                                            ├── raw/
                                                            │   ├── language_detection.json
                                                            │   ├── node_build_system.json
                                                            │   ├── node_manifest.json
                                                            │   ├── ci.json
                                                            │   ├── deployment.json
                                                            │   └── test_inventory.json
                                                            └── runs/<ts>-<short>.json

                              Probe Catalogs (data, not code)
                              ──────────────────────────────────
                              src/codegenie/catalogs/
                                native_modules.yaml   ← NodeManifest reads
                                ci_providers.yaml     ← CI reads
```

Three things to notice in the diagram:

1. **Every existing box says "unchanged."** This is the test of extension-by-addition. If Phase 1 needed even one box edited, the contract was wrong; per Phase 0 §12, the only legitimate Phase 1 modifications are `exec.ALLOWED_BINARIES` (with an ADR amendment) and the addition of new sub-schemas and new probes.
2. **Catalogs are a new sibling directory.** They are *data*, loaded by the probes that consume them. Adding a native module to the catalog must not require touching `node_manifest.py`. This is `production/design.md §2.6` ("Organizational uniqueness as data, not prompts") applied to internal organizational knowledge.
3. **Each probe owns exactly one slice of `repo-context.yaml`.** `NodeBuildSystem` owns `build_system`; `NodeManifest` owns `manifests`; `CI` owns `ci`; `Deployment` owns `deployment`; `TestInventory` owns `test_inventory`. No probe writes outside its slice. This is the spine of `localv2.md §4`.

---

## Components

### LanguageDetectionProbe (extension, not new)

- **Purpose:** Extend Phase 0's `LanguageDetectionProbe` to populate the Node-specific fields `localv2.md §5.1` (A1) requires: framework hints, monorepo markers. The Phase 0 implementation produced only extension counts.
- **Public interface:** unchanged. `run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` per the §4 ABC.
- **Internal design:** the directory walker from Phase 0 stays; what changes is post-walk classification.
  - Framework detection: read `package.json` once (via `NodeManifestProbe`'s parser, *which it does not directly call* — see Tradeoffs below) and inspect `dependencies` + `devDependencies` for known framework markers (`nestjs/*`, `express`, `fastify`, `next`, `koa`, `hapi`). This is a flat dictionary lookup against a constant set; ~20 lines of code.
  - Monorepo detection: filesystem checks for `pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, and `package.json#workspaces` field presence. Five `Path.exists()` calls + one JSON read = ~30 lines.
- **Dependencies:** stdlib only (`json`, `pathlib`). No new deps.
- **Where it lives:** `src/codegenie/probes/language_detection.py` (Phase 0 file, extended in place — this is **not** an exception to extension-by-addition; `localv2.md §5.1 A1` defines the full A1 schema slice up front, and Phase 0 deliberately shipped a subset with the rest deferred to Phase 1 per [phase-0 final-design §2.10](../00-bullet-tracer-foundations/final-design.md)).
- **Tradeoffs accepted:**
  - `LanguageDetection` reads `package.json` *itself* rather than depending on `NodeManifestProbe` having already run. This violates DRY by a small margin (two probes parse `package.json`), but it preserves probe isolation (`localv2.md §2`: "Adding a new probe never requires modifying existing ones"). Coupling `LanguageDetection` to `NodeManifest`'s output is the worse failure mode — it would make `LanguageDetection`'s test fixtures depend on the entire `NodeManifest` test surface.
  - Framework detection is intentionally shallow. `NestJS` detected by `@nestjs/core` in deps, not by AST-level decorator analysis. The shallow signal is correct for `LanguageDetection`'s role (a quick repo map); deeper detection lives in Phase 2's `NodeReflectionProbe`.

### NodeBuildSystemProbe

- **Purpose:** Populate the `build_system` slice from `localv2.md §5.1 A2`. Determines package manager, engine constraints, npm scripts, bundler, TypeScript compilation setup.
- **Public interface:** standard probe ABC. `name = "node_build_system"`, `layer = "A"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `declared_inputs = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb", ".nvmrc", ".node-version", "tsconfig.json", ".tool-versions"]`.
- **Internal design:**
  - Package-manager resolution by lockfile precedence (`bun.lockb` > `pnpm-lock.yaml` > `yarn.lock` > `package-lock.json`). Pure stdlib; ~15 lines.
  - `package.json#scripts` extraction via `json.loads`; values pass through as opaque strings (we record what's there, we do not interpret).
  - Node version: read `package.json#engines.node`, `.nvmrc`, `.node-version`, `.tool-versions` (asdf format) in declared precedence order. Each is a file read with simple string handling.
  - `tsconfig.json`: read via `json.loads` (it's JSON-with-comments in practice; we use `tomllib`-style permissive parsing — **no**, we use `json5` is a temptation we resist. Instead: read the file, strip line comments (`// ...` regex) and block comments (`/* ... */` regex) with a small ~10-line helper, then `json.loads`). This is the *only* place a non-trivial parser helper lives; if it grows beyond a screen, it moves to `src/codegenie/parsers/jsonc.py`.
  - Bundler detection: pure data lookup against deps (`webpack`, `rollup`, `esbuild`, `vite`, `parcel`, `turbopack`) + config-file presence (`webpack.config.js`, `rollup.config.js`, `vite.config.ts`, etc.).
  - `node --version` cross-check (optional, gated by tool-readiness): if `node` is in `ALLOWED_BINARIES` and on `$PATH`, call `node --version` via `exec.run_allowlisted` and record the local version alongside the constraint. Absence is fine; the probe reports `node_version_pinned: null, node_version_resolved_locally: null, confidence: high` (the constraint is the load-bearing fact).
- **Dependencies:** stdlib (`json`, `pathlib`, `re`). PyYAML (existing Phase 0 dep) for the lockfile YAML cases.
- **Where it lives:** `src/codegenie/probes/node_build_system.py`.
- **Tradeoffs accepted:**
  - We choose the package manager by **lockfile**, not by `packageManager` field in `package.json`. The lockfile is the empirical ground truth; the field is aspirational. Where they disagree, we emit `warnings: ["packageManager field declares 'yarn@4.0.0' but yarn.lock is absent and pnpm-lock.yaml is present"]` and prefer the lockfile.
  - We do **not** evaluate any script. `commands.build = "pnpm run build"` is what the probe records; what that script actually does is the Planner's problem, not ours.
  - Multiple lockfiles trigger `confidence: low` (per "Honest confidence" — final-design and `production/design.md §2.3`). We pick the one with highest precedence and record the conflict; we do not deduplicate.

### NodeManifestProbe

- **Purpose:** Populate `manifests` from `localv2.md §5.1 A3`. The **single most distroless-relevant** Layer A probe — native module enumeration is the largest source of distroless migration failures.
- **Public interface:** standard probe ABC. `name = "node_manifest"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection"]`, `declared_inputs = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "src/codegenie/catalogs/native_modules.yaml"]`.
- **Internal design:**
  - **Three lockfile parsers**, each in its own helper function: `_parse_pnpm_lock`, `_parse_package_lock`, `_parse_yarn_lock`. The pnpm parser uses `yaml.safe_load`; the package-lock parser uses `json.loads`; the yarn parser is the only non-trivial one (Berry's YAML-ish format) and uses **the `pyarn` library on PyPI** if it remains widely supported as of Phase 1 land, falling back to a small hand-rolled parser otherwise. This is the only library decision in Phase 1 that requires evidence at land-time — see "Open questions" below.
  - Native module catalog: `src/codegenie/catalogs/native_modules.yaml` is a flat list of `{name, requires_node_gyp, system_deps_required, binary_artifacts_glob, notes}`. The probe iterates the lockfile's resolved packages and emits one entry per match. Adding a module is a YAML PR.
  - Engine declarations: read from `package.json#engines`.
  - Optional / bundled dependencies: counted from `package.json#optionalDependencies` and `package.json#bundledDependencies`.
- **Dependencies:** stdlib + PyYAML + (optionally) `pyarn`. The `pyarn` dependency, if adopted, must pass the Phase 0 `fence` test (it's a YAML parser, not an LLM SDK — should be fine) and is pinned in `pyproject.toml` under the `gather` extra closure.
- **Where it lives:** `src/codegenie/probes/node_manifest.py`. Lockfile parsers live in `src/codegenie/probes/_lockfiles/` (private helpers).
- **Tradeoffs accepted:**
  - **The catalog is hand-curated**, not derived from npm metadata. This is deliberate: native-module knowledge is organizational + community knowledge that drifts slowly and demands human review when entries are added. Auto-deriving from registry metadata is a Phase 2+ concern, and even then, the catalog stays canonical with auto-derivation as input.
  - We parse the lockfile, not `node_modules/`. The lockfile is committable, deterministic, cache-friendly; `node_modules/` is a build artifact and may not be present. This is the only choice consistent with the cache contract.
  - We do **not** invoke `npm ls` or `pnpm list`. Those require `node_modules/` and are slow. Lockfile parsing is the deterministic equivalent.

### CIProbe

- **Purpose:** Populate `ci` from `localv2.md §5.1 A4`. Records which CI provider is in use, which workflows build container images, which test/lint commands run.
- **Public interface:** standard probe ABC. `name = "ci"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `declared_inputs = [".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", "azure-pipelines.yml", "src/codegenie/catalogs/ci_providers.yaml"]`.
- **Internal design:**
  - **Provider detection**: read the `ci_providers.yaml` catalog; each entry declares a list of marker paths and a parser function name. First catalog entry whose marker paths exist wins.
  - **GitHub Actions parser**: `yaml.safe_load` per workflow file. Extracts job names, the steps in each job, looks for `docker build`/`docker buildx`/`docker/build-push-action` to set `builds_image: true`, extracts test/lint scripts from `run:` steps via simple string matching against known patterns (`npm run test`, `pnpm test`, `yarn test`, etc.).
  - **GitLab CI parser**: same `yaml.safe_load`; the schema is well-documented and stable.
  - **Jenkinsfile**: best-effort regex-only parser. It's Groovy; we don't try to be a Groovy parser. Records that Jenkinsfile is present with `confidence: low` and `warnings: ["Jenkinsfile detected; only marker-level recognition implemented"]`. This is **Rule 12 (fail loud)** applied to a probe: the artifact says explicitly that the analysis is partial.
  - **CircleCI / Azure Pipelines**: stub recognizers (mark presence with `confidence: low`); fuller parsers land when actually needed.
- **Dependencies:** stdlib + PyYAML.
- **Where it lives:** `src/codegenie/probes/ci.py`. Per-provider parsers live in `src/codegenie/probes/_ci_parsers/` (private helpers, one file each).
- **Tradeoffs accepted:**
  - Multiple providers can coexist in a repo (e.g., GitHub Actions + a legacy Jenkinsfile). The probe records both; the `provider` field becomes a list, not a singleton (this is a small departure from `localv2.md §5.1 A4`'s example output, which shows a singleton — we report this as a doc-update candidate, not a deviation; see Open Questions). Confidence drops if more than one provider is detected.
  - We do **not** execute any CI logic or simulate any CI run. We read configuration as data.

### DeploymentProbe

- **Purpose:** Populate `deployment` from `localv2.md §5.1 A5`. Records deployment type (Helm, Kustomize, raw manifests, Terraform), image reference path, health probe paths, security context, exposed ports, required env vars.
- **Public interface:** standard probe ABC. `name = "deployment"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `declared_inputs = ["deploy/**/*.yaml", "deploy/**/*.yml", "k8s/**/*.yaml", "helm/**/*", "chart/**/*", "kustomization.yaml", "kustomization.yml", "*.tf", "main.tf"]`.
- **Internal design:**
  - **Deployment type detection** by directory and file marker: `Chart.yaml` → Helm; `kustomization.yaml` → Kustomize; raw `kind: Deployment` YAML → raw manifests; `.tf` files → Terraform.
  - **Helm**: read `Chart.yaml` + `values.yaml`; do **not** render templates (rendering requires a Helm binary and would be non-deterministic for templates using `now` or random functions). Record the image reference *path* (e.g., `image.repository`) and the value at that path in `values.yaml`. The Planner can render later if it needs the rendered form.
  - **Kustomize**: read `kustomization.yaml` resources list; recurse one level. Do not invoke `kustomize build`.
  - **Raw manifests**: walk YAML files, `yaml.safe_load_all` (multi-document), filter to `kind: Deployment | StatefulSet | DaemonSet | Pod`, extract `spec.template.spec.containers[].image`, `securityContext`, `ports`, `env`.
  - **Terraform**: optional. If `python-hcl2` is available in the gather extras, parse; otherwise emit `confidence: low, warnings: ["Terraform files detected but python-hcl2 not installed; parsing skipped"]`. Per Phase 0's stance on optional tooling, we do not add `python-hcl2` to required deps in Phase 1 — Terraform-heavy migrations are a Phase 7+ concern.
- **Dependencies:** stdlib + PyYAML. `python-hcl2` is *optional* (declared in `pyproject.toml` under a new `gather-terraform` extra; not in default install).
- **Where it lives:** `src/codegenie/probes/deployment.py`. Per-type parsers in `src/codegenie/probes/_deployment_parsers/`.
- **Tradeoffs accepted:**
  - We do **not** render Helm or Kustomize. That's a deliberate determinism choice (`production/design.md §2.4`); the rendered form is non-deterministic in general. The Planner is free to render in Phase 3 with full Helm/Kustomize tooling; the gather captures source-level evidence.
  - Multi-environment deployments (separate `values-prod.yaml`, `values-staging.yaml`) are reported as a list of environments, each with its own image reference. `production/design.md` does not require us to pick "the prod one"; that's a Planner judgment.

### TestInventoryProbe

- **Purpose:** Populate `test_inventory` from `localv2.md §5.1 A6`. Records the test framework, test count, integration/smoke/e2e command paths, coverage data presence.
- **Public interface:** standard probe ABC. `name = "test_inventory"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection", "node_build_system"]`, `declared_inputs = ["package.json", "vitest.config.*", "jest.config.*", ".mocharc.*", "playwright.config.*", "test/**/*.test.*", "tests/**/*.test.*", "src/**/*.test.*", "**/*.spec.*", "coverage/lcov.info"]`.
- **Internal design:**
  - **Framework detection**: data lookup against `dependencies + devDependencies` for `vitest`, `jest`, `mocha`, `tap`, `node:test` (presence of `node:test` is implied by `engines.node >= 18`), `playwright`, `cypress`, `@playwright/test`.
  - **Test count**: a single pass `os.walk` (per Phase 0's exclusion conventions — `node_modules`, `dist`, `build`, `coverage`, `.next`, `.turbo`) counting files matching `*.test.{js,ts,jsx,tsx,mjs,cjs}` and `*.spec.{js,ts,jsx,tsx,mjs,cjs}`.
  - **Command extraction**: read `package.json#scripts` for entries named `test`, `test:unit`, `test:integration`, `test:smoke`, `test:e2e`, `test:coverage`. Record verbatim.
  - **Smoke script presence**: filesystem check for `scripts/smoke.sh`, `scripts/smoke.js`, `scripts/smoke.ts`, `tests/smoke/*`.
  - **Coverage data**: filesystem check for `coverage/lcov.info`; if present, parse the totals (small `lcov` parser; ~30 lines or use the `lcov-parser` PyPI library if it remains maintained — decided at land-time via the same evidence-bar as `pyarn`).
- **Dependencies:** stdlib only (PyYAML already loaded).
- **Where it lives:** `src/codegenie/probes/test_inventory.py`.
- **Tradeoffs accepted:**
  - We count test **files**, not test cases. Counting cases requires running the framework or parsing per-framework `describe/it` blocks — both are expensive and noisy. File counts are sufficient for the planner's "is there test coverage?" judgment.
  - `node:test` is reported as `framework: node_test` (a value not present in the §5.1 A6 example output). This is a fact, not a judgment; the schema's `framework` field accepts string enumeration.

### Probe registry — explicit imports

- **Purpose:** Make every probe in the system visible at one place. Per Phase 0 §2.4 (`design-best-practices` and final-design): no `entry_points` scan, no plugin discovery, no auto-import.
- **Public interface:** `src/codegenie/probes/__init__.py` continues to be the single place where new probes are imported (to trigger their `@register_probe` decoration). Phase 1 adds five `from . import ...` lines.
- **Where it lives:** `src/codegenie/probes/__init__.py`.
- **Tradeoffs accepted:** explicit imports cost one line of code per probe and grep-ability for "what's in this system." This is the trade we make every time; it's worth it.

### Probe sub-schemas

- **Purpose:** Each probe owns one sub-schema declaring the JSON shape of its slice. The Phase 0 envelope (`src/codegenie/schema/repo_context.schema.json`) `$ref`s each sub-schema by path.
- **Where it lives:**
  - `src/codegenie/schema/probes/language_detection.schema.json` (Phase 0, extended in place for the new fields)
  - `src/codegenie/schema/probes/node_build_system.schema.json`
  - `src/codegenie/schema/probes/node_manifest.schema.json`
  - `src/codegenie/schema/probes/ci.schema.json`
  - `src/codegenie/schema/probes/deployment.schema.json`
  - `src/codegenie/schema/probes/test_inventory.schema.json`
- **Tradeoffs accepted:**
  - Each sub-schema is `additionalProperties: false` at its own root (per Phase 0's layered policy: strict at the boundaries where it matters). Adding a field to a probe's output requires editing both the probe code and its sub-schema in the same PR — this is friction, and the friction is the point.
  - Sub-schemas are **JSON files**, not Pydantic models. JSON Schema is the contract Phase 0 chose; we honor it (Rule 11). Pydantic stays at the trust-boundary inside the coordinator.

### Catalog loader

- **Purpose:** Read YAML data files (native modules, CI providers) once at module import, expose them as immutable mappings.
- **Public interface:** `src/codegenie/catalogs/__init__.py` exports `NATIVE_MODULES: Mapping[str, NativeModuleEntry]` and `CI_PROVIDERS: Mapping[str, CIProviderEntry]` where the entry types are `NamedTuple`s (stdlib, immutable, type-friendly, deserialization-trivial).
- **Internal design:** read YAML via `yaml.safe_load` at import; build the named-tuple-keyed dict; freeze via `types.MappingProxyType`. Schema-validate the catalog itself against `src/codegenie/catalogs/_schema.json` (loaded once, validated once at import). **Fail-loud** if the catalog YAML is malformed (Rule 12).
- **Where it lives:** `src/codegenie/catalogs/{__init__.py, native_modules.yaml, ci_providers.yaml, _schema.json}`.
- **Tradeoffs accepted:** loading at import time is a small startup cost (~5ms total) but it's the predictable, conventional way; the alternative (lazy lookup) would scatter "is the catalog loaded yet?" checks throughout the probe code.

---

## Data flow

A representative Phase 1 run on a real Node.js repo (`acme/billing-service`, ~1k files, TypeScript + NestJS + pnpm + GitHub Actions + Helm):

1. **CLI entry** (Phase 0). Path validated; tool-readiness check now includes `node` (optional) in addition to `git`. Config loaded.
2. **`RepoSnapshot` construction** (Phase 0). `git rev-parse HEAD` via `exec.run_allowlisted`. The snapshot now carries `detected_languages: {"typescript": 247, "javascript": 32, ...}` after `LanguageDetectionProbe` runs.
3. **Probe registry filter** (Phase 0). `for_task("__bullet_tracer__", {"typescript"})` now returns `[LanguageDetection, NodeBuildSystem, NodeManifest, CI, Deployment, TestInventory]`. `LanguageDetection` has no dependencies; the other four depend on it via the `requires` field. The coordinator's topological order: `LanguageDetection` first (alone, completes in ~80ms), then the remaining five in parallel.
4. **Coordinator dispatch** (Phase 0). `Semaphore(min(cpu_count(), 8))`; one `asyncio.Task` per probe; `asyncio.wait_for` with each probe's `timeout_seconds` (default 30s for these probes — they're all file-parsing, no subprocess except the optional `node --version`).
5. **Per-probe cache lookup** (Phase 0). For each probe, compute `cache_key = identity_hash(probe_name, probe_version, schema_version, content_hash(declared_inputs))` per [phase-0 final-design §2.7](../00-bullet-tracer-foundations/final-design.md). Cold first run: all misses.
6. **Probe execution** (Phase 1, new). Each probe parses its files, builds its slice, returns a `ProbeOutput`. Per-probe wall-clock on the 1k-file fixture (target, p50): `LanguageDetection` 80ms, `NodeBuildSystem` 40ms, `NodeManifest` 250ms (lockfile parse dominates), `CI` 50ms, `Deployment` 60ms (Helm chart walk), `TestInventory` 120ms (file count walk). Parallel wall-clock dominated by `NodeManifest` at ~250ms.
7. **`_ProbeOutputValidator`** (Phase 0). Each `ProbeOutput` validated against `JSONValue` recursive type + field-name regex. Phase 1 probes use field names like `package_manager`, `native_modules`, `image_reference`, `framework` — none trip the secret-name regex. (If a future probe needs a field literally named `auth_token`, this is a design issue to surface, not suppress.)
8. **`OutputSanitizer.scrub`** (Phase 0). Absolute paths in lockfile entries (e.g., `binary_artifacts: ["/Users/me/work/billing/node_modules/sharp/build/..."]`) get scrubbed to relative paths. This is **load-bearing for Phase 11** (final-design §2.8) — the `.codegenie/` artifacts will eventually be committed to repos, and developer home paths must not leak.
9. **Cache write** (Phase 0). Each `ProbeOutput` blob written via the BLAKE3-keyed, two-shard-char layout; index appended.
10. **Output merge** (Phase 0). Each probe's `schema_slice` merged into the top-level `repo-context.yaml` envelope.
11. **Schema validation** (Phase 0). `Draft202012Validator` runs against the full envelope; the layered `additionalProperties` policy means: strict at the envelope (extra root keys rejected), strict per-probe-sub-schema, loose between (an unknown probe's slice is `probes.unknown_probe: <object>` — accepted by the envelope's `additionalProperties: true` on `probes.*`).
12. **Raw artifact writing** (Phase 0). Each probe's raw output (the full parsed lockfile, the full parsed Helm chart, etc.) is written to `.codegenie/context/raw/<probe>.json`, 0600.
13. **YAML write** (Phase 0). `repo-context.yaml.tmp` → `os.replace`. `CSafeDumper`.
14. **Audit record** (Phase 0). Per-probe `(name, version, cache_hit, wall_clock, exit_status, warnings_count)` recorded; final YAML SHA-256 included.
15. **Exit 0.**

**Second run (cache hit path).** Same invocation, no source files changed:
1. Steps 1–5 identical until per-probe cache lookup.
2. Each probe's cache lookup hits (same `declared_inputs`, same content). Coordinator records `ProbeExecution.CacheHit` for each, returns the cached `ProbeOutput` directly (per [phase-0 final-design §2.6](../00-bullet-tracer-foundations/final-design.md), cache-hit pass-through preserved as a first-class coordinator output).
3. No probe `run()` is called; no parsing happens; no subprocess.
4. Steps 8 (sanitizer), 11 (schema validation), 12–14 still run because the merge must happen (cache stores the per-probe slice, the merge into a single YAML happens fresh each run — this keeps the YAML's `gathered_at` timestamp honest).
5. Wall-clock target on the 1k-file fixture for the cache-hit run: p50 ≤ 0.4s.

The data flow honors three of the load-bearing commitments explicitly:
- **Probe contract (`localv2.md §4`)** holds across all six probes; the snapshot test in `test_probe_contract.py` (Phase 0) is unmodified and continues to pass.
- **Cache-hit pass-through** is exercised in steps 2–4 of the second run; this is the exit-criterion "cache hits on second run."
- **Idempotent activities** — each probe is referentially transparent on its `declared_inputs`. Phase 9's Temporal Activities will wrap each of these probes directly; no rewrite needed.

---

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| `NodeBuildSystem` finds multiple lockfiles | Probe internal logic | `confidence: low`; `warnings: [list of lockfiles]`; pick by precedence; **gather continues** |
| `NodeManifest` lockfile parse error (malformed `pnpm-lock.yaml`) | `LockfileParseError` raised in helper | Caught by probe; `ProbeOutput(errors=["lockfile parse failed: ..."], confidence: low, schema_slice={"manifests": [...partial...]})`; **gather continues** |
| Native module catalog missing or malformed | `CatalogLoadError` at module import | **Hard fail** at CLI startup with a clear "the native_modules.yaml catalog is malformed" message and the path to the file. This is Rule 12 (fail loud) — the catalog is load-bearing data, silent fallback is wrong. |
| `CI` probe finds Jenkinsfile only | Probe internal logic | `confidence: low`; `warnings: ["Jenkinsfile detected; only marker-level recognition implemented"]`; **gather continues**, slice has provider + path but no extracted commands |
| `Deployment` finds no recognized deployment | Probe internal logic | Schema slice `{"type": null, "confidence": "low", "warnings": ["no recognized deployment manifests found"]}`; **gather continues** |
| `Deployment` finds Terraform but `python-hcl2` absent | Optional-dep ImportError caught | `confidence: low`; `warnings: ["python-hcl2 not installed; Terraform parsing skipped"]`; **gather continues** |
| `TestInventory` finds no test files at all | Probe internal logic | `test_count: 0`; `confidence: medium` (the *absence* is itself a fact, but it's worth flagging); `warnings: ["no test files matching standard patterns found"]`; **gather continues** |
| `tsconfig.json` is JSONC with unsupported syntax | `JSONDecodeError` after comment-strip | `confidence: low`; `warnings: ["tsconfig.json contains non-standard syntax; partial parse"]`; **gather continues** with whatever fields parsed |
| Probe exceeds its `timeout_seconds` | Phase 0 coordinator (`asyncio.wait_for`) | Phase 0 handling unchanged: `ProbeOutput(errors=["timeout"], confidence: low)`; gather continues |
| `node --version` fails (binary absent, exec error) | `exec.run_allowlisted` raises | Probe catches; `node_version_resolved_locally: null`; **does not affect probe confidence** — the constraint from `package.json#engines` is the load-bearing fact |
| Path traversal in `declared_inputs` (e.g., a probe author writes `"../etc/passwd"`) | Phase 0 registration test (`test_path_traversal.py`) | **Hard fail at registration time**; the test never lets the probe register |
| Schema sub-schema malformed | `jsonschema` schema-compile error at module load | **Hard fail** at CLI startup with a clear message pointing to the malformed sub-schema file |
| Sub-schema `$ref` resolves to nonexistent path | `jsonschema` reference resolution error | **Hard fail** at CLI startup; envelope tests assert all `$ref`s resolve |
| Probe slice fails its own sub-schema | `Draft202012Validator` at envelope level | YAML written with `.invalid` suffix; **CLI exits 3** (Phase 0 convention) |
| Two probes attempt to write the same top-level slice key | Coordinator merge logic | **Hard fail** with `DuplicateSchemaSliceError`; test `tests/unit/test_probe_slice_disjoint.py` asserts statically |

The pattern: **deterministic facts about messy reality, explicit confidence, never silent degradation.** Every probe that meets its inputs in an unexpected state surfaces a typed `warning` rather than guessing. Every hard-fail is a load-bearing-invariant violation (Rule 12).

---

## Resource & cost profile

- **Tokens per run:** 0. Phase 1 is deterministic gather end-to-end. The Phase 0 `fence` CI job continues to assert this structurally.
- **Wall-clock per `codegenie gather`** on the real-OSS fixture (`expressjs/express` shape — ~200 source files, no native modules, GitHub Actions, no Helm), target p50 / p95:
  - Cold (cache empty): 1.5s / 3s
  - Warm (cache full): 0.3s / 0.6s
- **Wall-clock per `codegenie gather`** on the 1k-file billing-service-shape fixture:
  - Cold: 4s / 8s (dominated by `NodeManifest` lockfile parse and the `TestInventory` walk)
  - Warm: 0.4s / 1s
- **Memory:** ~80 MB RSS at peak (Phase 0 ~70 MB; +10 MB for the catalogs and the additional probe state).
- **Storage growth per gather:** `repo-context.yaml` ~20–40 KB; `raw/` ~200–400 KB (lockfile dumps dominate); cache blobs ~50 KB total; audit ~5 KB. Per-repo per-gather: ~0.5 MB. After a year of nightly continuous gather: ~180 MB per repo (well within local-disk tolerances; Phase 14 will revisit when continuous gather lands at portfolio scale).
- **CI walltime impact:** the Phase 0 90s p95 advisory target should hold; Phase 1 adds five probe unit-test modules (each ~30 tests) plus one integration test against a real OSS fixture cloned at test time (~3s, cached by `actions/cache` on a checksum of the fixture's commit SHA). Estimated CI delta: +25s p50, +45s p95.
- **Convention cost (where best practices buy future-proofing at present-day expense):**
  - Per-probe sub-schemas + the `additionalProperties: false` discipline cost ~30 minutes of authoring time per probe versus a single loose top-level schema. Pays for itself the first time Phase 7 (distroless migration) adds a probe and the strict envelope rejects a typo at land-time rather than at downstream-consumer time.
  - The catalog separation (`native_modules.yaml`, `ci_providers.yaml`) costs ~150 lines of YAML and one schema file. Pays back the first time someone adds `node-rdkafka` to the catalog as a YAML PR rather than a Python PR.
  - The probe-isolation discipline (each probe re-reads `package.json` rather than depending on another probe's parsed output) costs ~30 lines of duplicated parser-invocation glue. Pays back permanently — every probe is independently testable, independently cacheable, and independently lift-able to the service per [ADR-0007 production](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md).

---

## Test plan

The test pyramid here is wider at the unit base than at the integration top. Each probe is unit-tested exhaustively against fixture inputs *before* the integration test cares whether they compose correctly.

### Unit tests (`tests/unit/probes/`)

One test module per probe. Each follows the same shape (predictable, not clever):

| Test module | Asserts |
|---|---|
| `test_language_detection.py` | (Phase 0 tests retained.) New: framework detection from `dependencies` (NestJS, Express, Fastify, Next, Koa, Hapi); monorepo markers (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, `package.json#workspaces`); confidence reporting (medium when only one weak signal). |
| `test_node_build_system.py` | Lockfile-precedence selection (each of pnpm, yarn, npm, bun on isolated fixtures); multi-lockfile detection drops confidence; `engines.node` precedence over `.nvmrc` over `.node-version`; `tsconfig.json` with comments parses; bundler detection per bundler; `package.json` malformed → `confidence: low`, `errors: [...]`. ~25 tests. |
| `test_node_manifest.py` | Each lockfile parser on a fixture for that format; native-module detection against the catalog (one fixture per cataloged module: bcrypt, sharp, better-sqlite3, node-canvas); `optionalDependencies` counting; `bundledDependencies` counting; lockfile integrity bit reported; cache-key stability across runs. ~30 tests. |
| `test_ci.py` | GitHub Actions parsing (one workflow that builds an image; one that doesn't; one with a matrix); GitLab CI; Jenkinsfile (presence only); multiple-provider repo; absent CI directory. ~20 tests. |
| `test_deployment.py` | Helm `Chart.yaml` + `values.yaml`; Kustomize; raw Deployment manifest; raw Pod (skipped — pods aren't deployments); multi-environment Helm (`values-prod.yaml` + `values-staging.yaml`); Terraform with `python-hcl2` present (skip if not installed in CI); securityContext extraction; required env vars from `envFrom` and direct `env`. ~25 tests. |
| `test_test_inventory.py` | Vitest, Jest, Mocha, Tap, node:test, Playwright, Cypress detection; test-file count walks honor exclusions; `package.json#scripts` extraction for the recognized script names; smoke-script presence; coverage `lcov.info` parsing (totals only); empty test directory case. ~20 tests. |
| `test_catalogs.py` | Catalog YAML parses; catalog schema validates; every catalog entry has the required fields; duplicate names rejected at load. |
| `test_probe_registration.py` (extends Phase 0) | Each Phase 1 probe registers exactly once; `requires` graph is acyclic; `LanguageDetection` has no `requires`; the other five all declare `requires=["language_detection"]` correctly; `applies_to_languages` is non-empty for Node-only probes; `applies_to_tasks=["*"]` for all Layer A probes. |
| `test_probe_slice_disjoint.py` (extends Phase 0) | Asserts statically that no two registered probes write to the same top-level `schema_slice` key. This catches accidental collisions at test time rather than at merge time. |
| `test_sub_schemas.py` | Each per-probe sub-schema is itself a valid JSON Schema (Draft 2020-12); each `$ref` from the envelope resolves; each sub-schema has `additionalProperties: false` at its root; round-trip a representative slice through the envelope validator. |
| `test_cache_keys.py` (extends Phase 0) | For each Phase 1 probe, modifying a file in `declared_inputs` changes the cache key; modifying a file *not* in `declared_inputs` does not change the cache key (this is the contract that makes incremental gathers correct). |

Coverage target: **90% line / 80% branch** per the ratchet from Phase 0.

### Integration tests (`tests/integration/`)

| Test module | Asserts |
|---|---|
| `test_layer_a_end_to_end.py` | Runs the full `codegenie gather` flow against the committed fixture at `tests/fixtures/node_typescript_helm/` (a minimal but realistic NestJS-on-Helm repo); asserts every Phase 1 probe produces a non-empty slice; asserts the full `repo-context.yaml` validates against the envelope schema; asserts every cross-probe reference holds. |
| `test_cache_hit_on_real_repo.py` | Runs `gather` twice against the same fixture; asserts the second run produces zero `ProbeExecution.Ran` for the Phase 1 probes (all `CacheHit`); asserts wall-clock ratio second / first ≤ 0.25 (advisory metric). |
| `test_cache_invalidation.py` | Runs `gather`; modifies `package.json` (adds a dependency); runs `gather` again; asserts `NodeBuildSystem`, `NodeManifest`, `LanguageDetection`, and `TestInventory` produce `Ran` (their `declared_inputs` changed) and `CI`, `Deployment` produce `CacheHit` (their `declared_inputs` did not). |
| `test_real_oss_fixture.py` | Clones `expressjs/express` (pinned commit SHA) at test setup time; runs `gather`; asserts schema validity, asserts no probe crashed, asserts the manifest probe detects no native modules (Express has none), asserts the CI probe detects GitHub Actions. **Cached by `actions/cache` on the commit SHA.** |

### Golden files (`tests/golden/`)

For the integration test against the committed fixture, the expected `repo-context.yaml` is committed at `tests/golden/node_typescript_helm/repo-context.yaml`. The test diffs the live output against it. Updating the golden file is an explicit `make update-goldens` step that requires the developer to inspect the diff. This is the pattern Phase 2 will scale up (per roadmap); Phase 1 lands the convention with one fixture.

### Property tests

**Deferred to Phase 2.** Phase 1's probes have no obvious universal invariants the way the cache and sanitizer do (the property-test backbone is `for all inputs, this invariant holds`; probes are file-shape-specific). Phase 2's `IndexHealthProbe` will introduce real invariants (e.g., "coverage_pct = files_indexed / files_in_repo") that property-test cleanly.

### What is explicitly **not** in Phase 1 tests

- No tests against running CI providers (no live `gh actions` calls; we read configuration files only).
- No tests requiring Docker or `node_modules` to be installed.
- No tests of probes Phase 1 didn't ship.
- No tests of `IndexHealthProbe` (Phase 2).
- No tests of cache TTL expiration (Phase 0 covers it; we don't re-test).
- No fuzz tests on lockfile parsers (Phase 8 risk-budget; the lockfile formats are well-understood and the parsers are small).

---

## Risks (top 3–5)

1. **The native-module catalog is the system's blast radius for distroless migration accuracy, and Phase 1 owns it.** A missed native module → a Phase 7 distroless migration that builds and passes tests but crashes at runtime because `libvips` is missing. Mitigation: the catalog ships in Phase 1 with the well-known set (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`, `node-pty`, `bufferutil`, `utf-8-validate`, `argon2`, `keytar`); ADR-amendment workflow exists for additions; Phase 7's integration tests *will* exercise the catalog and surface gaps. Phase 1's job is to land a correct *seed*, not a complete enumeration.
2. **Multi-environment Helm and Kustomize deployments expose ambiguity the schema barely captures.** The schema in `localv2.md §5.1 A5` shows a single `image_reference`; reality has prod / staging / dev overlays. We resolve by emitting a list; this technically deviates from §5.1's example output. The risk: a downstream consumer expects a singleton and breaks. Mitigation: the schema (the JSON Schema, not the doc's example) defines `image_reference` as either an object or a list of objects; the envelope's strict validation surfaces the mismatch loudly if a consumer's expectations drift. We file a doc-update PR against `localv2.md` per the ADR-0007 workflow.
3. **The Jenkinsfile parser is intentionally shallow** (regex-level marker recognition only). A repo whose entire CI lives in Jenkinsfile will produce a `confidence: low` `ci` slice that the Planner correctly downgrades to "uncertain" — but the slice still has to exist (the envelope requires the `ci` key). Risk: a downstream consumer interprets "presence of `ci` key + `confidence: low`" as "CI is configured and the gather is ambiguous" rather than "we don't actually know what the CI does." Mitigation: the `warnings` array is explicit, and the schema for `ci` requires a `provider_recognized: bool` field — when `false`, the Planner has a structural signal, not just a probabilistic one.
4. **The `pyarn` library is the only Phase 1 non-stdlib parser choice not already in Phase 0's dependency closure**, and its maintenance status is the bet. Mitigation: at land-time, the implementer confirms (a) the library is still maintained (last release < 18 months), (b) the latest version passes our test fixtures, and (c) a fallback hand-rolled yarn-lock parser is in place if it's not. The fallback is ~100 lines of code; the cost is ours to pay if we have to.
5. **Coverage ratchet from 85/75 to 90/80 may pinch on the deployment probe**, which has many narrow branches (per-deployment-type) and limited diminishing-returns past 85%. Mitigation: if 90% line proves unreachable without gameable tests (Rule 9), we lower the per-module floor for `deployment.py` to 85% and surface it explicitly in the PR (Rule 12); we do **not** ratchet the project-wide target down. Per-module floor exemptions live in `pyproject.toml` and require an ADR amendment.

---

## Acknowledged blind spots

- **I have not designed for what happens when `LanguageDetection` decides "this isn't a Node.js repo."** All five Phase 1 probes declare `applies_to_languages = ["javascript", "typescript"]`. If `LanguageDetection` reports a Go-only or Python-only repo, the coordinator's `for_task` filter skips them all and the YAML envelope has empty `build_system`, `manifests`, etc. slices — but the **schema requires these keys**. The envelope schema needs nullable variants for the Layer A Node slices, which deviates from `localv2.md §7`'s example (which assumes Node throughout). The synthesizer should pick a stance: nullable slices, conditional schema branches, or a "Layer A is Node-specific; non-Node repos use a different envelope" position. My recommendation is conditional schema branches keyed on `language_stack.primary`, but it's not free — it adds schema complexity that may not pay back until Phase 7+.
- **I have not designed for the case where `package.json` itself is a manifest fragment from a workspace root** (i.e., `package.json#workspaces` exists, but `package.json#dependencies` is empty because all dependencies are in `packages/*/package.json`). `NodeManifest` will report `direct_dependencies.production: 0` and `confidence: high`, which is structurally true but misleading. A future `BuildGraphProbe` (Phase 2's B5) resolves the monorepo case fully; Phase 1's `NodeManifest` is correctly scoped to "manifests as facts," but the consumer experience on a workspace root may be confusing. The fix is a doc fix (`CONTEXT_REPORT.md` template gains a "workspace root detected" note in Phase 1.5 or Phase 2).
- **The performance lens will argue for parallel lockfile parsing within `NodeManifest` for monorepos with many `package.json` files.** Phase 1 ships sequential parsing. For monorepos with 100+ packages, this might cost ~2–4s. My position: best-practices says ship the readable serial version, measure on a real monorepo fixture in Phase 2, optimize if the measurement demands it. The synthesizer should weigh this against the performance lens's likely "parallelize at the lockfile level" argument.
- **I have not designed CI behavior on missing optional binaries** (`node --version` for `NodeBuildSystem`). The Phase 0 tool-readiness cache treats `node` as advisory; CI runners may have it, may not. The probe handles absence gracefully (returns `confidence: high` with `node_version_resolved_locally: null`), but this means the CI matrix doesn't fully exercise the `exec.run_allowlisted("node", ...)` path unless we explicitly install Node. My recommendation: install Node 20.x in the CI matrix (`setup-node@v4` action, pinned by SHA per Phase 0 §3.2) so the path is exercised. The synthesizer may want to weigh whether this couples Phase 1's CI to a binary that Phase 2 may not need.
- **The security lens will likely push for runtime checks against tree-traversal in `declared_inputs` glob expansion.** Phase 0 tests this at registration time; Phase 1 inherits. If glob expansion at gather-time can be exploited (e.g., a maliciously-crafted symlink in the analyzed repo), the threat is real but it's a Phase 0 layer, not a Phase 1 one. I'm leaving this for the security lens to surface as a structural concern at the right layer.

---

## Open questions for the synthesizer

1. **Nullable Layer A slices for non-Node repos.** Should the envelope schema use conditional branches (`if language_stack.primary == "typescript" then ...`), nullable fields with `confidence: not_applicable`, or a separate envelope per language family? Best-practices favors `confidence: not_applicable` + explicit `applies_to_languages` filtering at the registry level — the envelope schema treats Layer A slices as **optional** rather than nullable, and the JSON Schema marks them as such. This is the minimum-change path; the synthesizer should validate against `localv2.md §7`'s envelope.
2. **`pyarn` adoption decision rule.** Adopt at land-time if maintained (< 18 months since last release) and the test fixtures pass; otherwise ship a 100-line hand-rolled parser. Best-practices favors written-down decision rules; the synthesizer should encode the rule (or pick definitively now).
3. **`packageManager` field handling.** `package.json#packageManager` (e.g., `"pnpm@8.15.0"`) is a relatively new field meant to declare the canonical package manager. Where it disagrees with the lockfile, best-practices says **prefer the lockfile** (it's the empirical truth). The synthesizer may have evidence I don't have on team practice here.
4. **GitHub Actions parser depth.** Phase 1 ships the minimum to populate the §5.1 A4 example schema (provider, builds_image, test/lint commands, matrix). The performance lens will likely argue for a deeper parser (every step, every secret reference, every reusable workflow); the security lens will likely argue for at minimum a "secrets referenced" extraction. Best-practices favors landing the minimum and growing it with evidence — the YAML will keep evolving with GitHub's spec; pinning a deep parser now will require revisiting. The synthesizer should pick the depth.
5. **`node` binary in `ALLOWED_BINARIES`.** Phase 1 adds `node` for the optional `node --version` cross-check in `NodeBuildSystem`. The decision is justified by ADR amendment in Phase 1; the synthesizer should confirm this is the right call versus reading `engines.node` only. My position: read both; surface the disagreement when present.
6. **Helm rendering vs. parsing.** Phase 1 parses source. The synthesizer may argue that without rendering, the `image_reference` recorded is sometimes a templated string (`{{ .Values.image.repository }}`) and the actual value is in `values.yaml`. The probe handles this by emitting both the path in `values.yaml` *and* the templated string from the manifest, but a real-world test against five Helm charts at synthesizer review would close the loop better than my fixture coverage.
7. **Catalog-versioning story.** The native-module catalog is data, not code; how do we version it? Best-practices says use a `catalog_version: int` field in the YAML and include it in the cache key. The synthesizer should confirm — without versioning, a catalog update silently invalidates cached `NodeManifest` outputs (which may actually be desirable; the synthesizer picks).
