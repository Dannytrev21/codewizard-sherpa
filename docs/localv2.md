# Local Context-Gathering POC for Node.js Distroless Migration

*A self-contained, locally-runnable POC of the context-gathering layer. Targets Node.js distroless container migration as the first task. Architected so adding new languages (Java, Scala, Python, Go) and new task types (vulnerability remediation, framework upgrades) is purely additive — new probes and skills, never rewrites.*

*This is a local-dev tool. No MCP server, no service deployment, no remote infrastructure. Run it manually against a repo on disk; it produces files in that repo. Once the design is proven as a POC, it can be lifted into a service.*

---

## 1. What this is

A command-line tool that ingests a local repository, runs a fan-out pipeline of deterministic probes against it, merges the outputs into a single structured `RepoContext` artifact, and writes that artifact to a `.codegenie/` directory inside the repo. The artifact is the input the Planning agent (or, for now, you reading the file) uses to make migration decisions.

The single binary or script runs end-to-end in one invocation. No background services, no daemons, no remote API calls except the ones probes explicitly need (image registry pulls, vendor advisory lookups). Everything else is local.

```
$ codegenie gather --task distroless-migration ~/work/myservice
[+] Detecting language stack ............................ ok (0.4s)
[+] Parsing build system ................................ ok (0.8s)
[+] Reading manifests + lockfile ........................ ok (1.2s)
[+] Indexing semantics (scip-typescript) ................ ok (8.7s)
[+] Detecting reflection patterns ....................... ok (0.3s)
[+] Parsing Dockerfile .................................. ok (0.1s)
[+] Building current image .............................. ok (47s)
[+] Generating SBOM (syft) .............................. ok (3.1s)
[+] Scanning CVEs (grype) ............................... ok (5.4s)
[+] Tracing runtime (5 scenarios) ....................... ok (84s)
[+] Detecting custom certificates ....................... ok (0.2s)
[+] Classifying shell usage ............................. ok (0.1s)
[+] Reading organizational context ...................... ok (0.4s)
[+] Indexing repo notes + external docs ................. ok (0.6s)
[+] Running SAST (semgrep) .............................. ok (12s)
[+] Mapping test coverage ............................... ok (0.6s)
[+] Validating schema ................................... ok
[+] Writing artifacts to .codegenie/ .................... done

RepoContext written to:
  .codegenie/context/repo-context.yaml         (summary + indexes into raw evidence)
  .codegenie/context/raw/                      (large probe outputs)
  .codegenie/context/CONTEXT_REPORT.md         (human-readable summary)

Confidence: HIGH
Migration class: distroless-node-native-modules (sharp detected)
Estimated risk: medium
Blast radius: 3 downstream services, no shared library callers
Gather completed in 2m 43s
```

The `CONTEXT_REPORT.md` is what a human reviews before handing off to the Planner. It summarizes findings, flags risks, points at the raw evidence files for anything that needs deeper inspection.

---

## 2. Design principles

Six rules drive every decision below.

**Local-first, no remote dependencies in the core path.** Probes run on the local machine using local tools. The only external calls are the ones probes inherently need: pulling base images for SBOM analysis, fetching vendor advisories for CVE enrichment. Everything else — parsing, indexing, tracing, classification — runs against the repo in front of you.

**Deterministic over probabilistic.** No LLM is invoked anywhere in this pipeline. Every probe consumes inputs and produces outputs deterministically. Same inputs always yield same outputs. This makes the artifact reproducible, cacheable, and auditable.

**Facts, not judgments.** The gatherer captures evidence — "RUN command in final stage uses shell," "CodeQL detected SQL sink in `getUser`," "trace observed 0 shell invocations during smoke test." It does not write conclusions like "shell is not needed" or "safe to migrate." Those are Planner judgments. This separation matters because evidence is reusable across tasks while judgments aren't.

**Probe isolation.** Each probe owns one schema slice, declares its inputs, declares which tasks/languages it applies to, and runs independently. A failing probe degrades the artifact but doesn't kill the gather. Adding a new probe never requires modifying existing ones.

**Honest confidence.** Every probe reports confidence and provenance. Stale indexes, partial coverage, ambiguous matches — all surfaced as first-class metadata. The artifact never overclaims certainty.

**Extension by addition.** Adding Java tomorrow: write Java-specific probe variants, register them, drop in Java skills. Adding vulnerability remediation: add Layer F probes, add vuln skills. The coordinator, schema validator, cache layer, and existing probes don't change.

---

## 3. Architecture overview

### 3.1 Three-view picture

#### Architecture view — what runs where

```
┌──────────────────────────────────────────────────────────────────┐
│                        Local Workstation                          │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                     codegenie CLI                            │  │
│  │  - argument parsing                                          │  │
│  │  - task + language resolution                                │  │
│  │  - artifact path resolution                                  │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                      │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                   Probe Coordinator                          │  │
│  │  - resolves probe DAG for (task, language)                   │  │
│  │  - cache lookup                                              │  │
│  │  - parallel dispatch (asyncio + worker pool)                 │  │
│  │  - timeout + failure isolation                               │  │
│  │  - merge + JSON Schema validation                            │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                      │
│         ┌──────────────────┴──────────────────────────┐           │
│         │                                              │           │
│         ▼                                              ▼           │
│  ┌─────────────────┐                          ┌──────────────────┐│
│  │  Probe Workers  │                          │   Local Store    ││
│  │  (asyncio tasks │                          │                  ││
│  │   spawning sub- │                          │  .codegenie/     ││
│  │   processes)    │                          │   context/       ││
│  │                 │                          │   cache/         ││
│  │   Each probe    │                          │   skills/        ││
│  │   shells out to │                          │                  ││
│  │   its tool      │                          │   File-system    ││
│  └────────┬────────┘                          │   based, no DB   ││
│           │                                   └──────────────────┘│
│           │                                                       │
│  ┌────────▼─────────────────────────────────────────────────────┐ │
│  │              External Tools (installed locally)               │ │
│  │                                                               │ │
│  │  scip-typescript │ tree-sitter │ syft │ grype │ semgrep      │ │
│  │  docker / podman │ buildkit    │ strace │ tini │ jq         │ │
│  │  ast-grep        │ trivy       │ skopeo │ dive │ chainctl   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

  External dependencies (read-only network calls):
    - Container registries (docker.io, cgr.dev) for base image pulls
    - npm registry for advisory metadata
    - Internal Sourcegraph instance (optional — for cross-repo callers)
    - GitHub Security Advisories API (optional — for CVE enrichment)
```

#### Component view — the layered probe model

```
                    ┌──────────────────────────────┐
                    │     Probe Coordinator         │
                    │  (resolves DAG, dispatches,   │
                    │   merges, validates)          │
                    └─────────────┬─────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────┐
        │                         │                             │
        ▼                         ▼                             ▼
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   Layer A:      │    │     Layer B:          │    │     Layer C:          │
│   Repo Map      │    │     Semantic Index    │    │     Runtime/          │
│   Probes        │    │     Probes            │    │     Container Probes  │
│                 │    │                       │    │                       │
│ - Language      │    │ - SCIP index          │    │ - Dockerfile parse    │
│ - Build system  │    │ - Index health        │    │ - SBOM (syft)         │
│ - Manifests     │    │ - Reflection patterns │    │ - CVE scan (grype)    │
│ - CI files      │    │ - Generated code      │    │ - Runtime trace       │
│ - K8s/Helm      │    │ - Build graph         │    │   (multi-scenario)    │
│ - Tests         │    │                       │    │ - Shell usage         │
│                 │    │                       │    │ - Certificates        │
└─────────────────┘    └──────────────────────┘    │ - Entrypoint          │
        │                         │                 └──────────────────────┘
        │              ┌──────────┴───────────┐                │
        │              ▼                      ▼                │
        │   ┌──────────────────┐   ┌──────────────────┐       │
        │   │   Layer D:        │   │   Layer E:        │       │
        │   │   Organizational  │   │   Cross-repo /    │       │
        │   │   Probes          │   │   Operational     │       │
        │   │                   │   │   Probes          │       │
        │   │ - AGENTS.md       │   │ - Ownership       │       │
        │   │ - Skills index    │   │ - Deployment      │       │
        │   │ - ADRs            │   │   manifests       │       │
        │   │ - Conventions     │   │ - Service contracts│      │
        │   │ - Policies        │   │ - SLO refs        │       │
        │   │ - Exceptions      │   │                   │       │
        │   │ - Repo notes      │   │                   │       │
        │   │ - External docs   │   │                   │       │
        │   │   (BM25 indexed)  │   │                   │       │
        │   └──────────────────┘   └──────────────────┘       │
        │              │                      │                │
        │              ▼                      ▼                │
        │   ┌──────────────────────────────────────────────┐  │
        │   │   Layer F: Task-Specific Evidence             │  │
        │   │   (empty for distroless; populated for vuln)  │  │
        │   │                                               │  │
        │   │   - CodeQL DB / Joern CPG (Phase 2)          │  │
        │   │   - Taint flow analysis (Phase 2)            │  │
        │   │   - Reachability queries (Phase 2)           │  │
        │   └──────────────────────────────────────────────┘  │
        │              │                                        │
        │              ▼                                        │
        │   ┌──────────────────────────────────────────────┐  │
        │   │   Layer G: Behavioral Hints + SAST            │  │
        │   │                                               │  │
        │   │   - Test-to-source coverage map               │  │
        │   │   - Invariant hints                           │  │
        │   │   - Semgrep general findings                  │  │
        │   │   - ast-grep custom patterns                  │  │
        │   └──────────────────────────────────────────────┘  │
        │              │                                        │
        └──────────────┴────────────┬───────────────────────────┘
                                    ▼
                       ┌──────────────────────┐
                       │  RepoContext Merger  │
                       │  + JSON Schema       │
                       │    validator         │
                       └──────────┬───────────┘
                                  │
                                  ▼
                       ┌──────────────────────┐
                       │  Local Filesystem    │
                       │                      │
                       │  .codegenie/         │
                       │   context/           │
                       │     repo-context.yaml│
                       │     CONTEXT_REPORT.md│
                       │     raw/             │
                       │   cache/             │
                       └──────────────────────┘
```

#### Tech view — what each box runs on

| Component | Implementation |
|---|---|
| CLI | Python 3.11+ with `click`. Single entry point: `codegenie gather`. |
| Coordinator | Python `asyncio` event loop with bounded worker pool (default 4 concurrent probes). |
| Probe interface | Python ABC; probes register via decorator at module import. |
| Probe execution | `asyncio.create_subprocess_exec` for tool invocations; structured stdout/stderr capture. |
| Cache | Filesystem-backed, content-addressed under `.codegenie/cache/`. Each cache entry is `{sha256}.json`. |
| Schema | JSON Schema (draft 2020-12). Validation via `jsonschema` library. |
| Output format | YAML for the main artifact (human-friendly diff); JSON for raw probe outputs. |
| Logging | Structured JSON logs to `.codegenie/logs/gather-{timestamp}.jsonl`; pretty-printed to stdout. |
| External tools | Required to be on `$PATH`. CLI checks at startup and prints clear error if missing. |

The whole thing is one Python project. No services, no containers (except the ones being analyzed), no databases.

### 3.2 Repository layout the tool produces

After running, the target repo has a `.codegenie/` directory:

```
myservice/
├── .codegenie/
│   ├── context/
│   │   ├── repo-context.yaml          # primary artifact, human + machine
│   │   ├── CONTEXT_REPORT.md          # human-readable summary
│   │   ├── schema-version.txt         # for compatibility checks
│   │   └── raw/
│   │       ├── scip-index.scip        # binary SCIP output
│   │       ├── syft-sbom.json
│   │       ├── grype-cves.json
│   │       ├── semgrep-findings.json
│   │       ├── runtime-trace.json     # merged from all scenarios
│   │       ├── runtime-trace-startup.strace
│   │       ├── runtime-trace-smoke.strace
│   │       ├── runtime-trace-shutdown.strace
│   │       ├── dockerfile-parsed.json
│   │       └── ... (one file per probe with non-trivial output)
│   ├── cache/
│   │   ├── {sha256}.json              # content-addressed cache entries
│   │   └── ...
│   ├── logs/
│   │   └── gather-2026-04-26T14-32-18.jsonl
│   └── skills/                         # optional; empty initially
│       └── ...
├── package.json
├── Dockerfile
└── ... (rest of repo)
```

`.codegenie/` should be gitignored by default (the tool offers to add it on first run). Artifacts are local-only by design — they may contain SBOMs, CVE details, or runtime traces that don't belong in source control.

### 3.3 Why the layer model holds for local-dev

The layered structure isn't a server-side architecture quirk; it's a separation of evidence types by where the evidence lives. Layer A reads files. Layer B runs an indexer over the source. Layer C builds and runs containers. Layer D reads org-specific config. Layer E reads cross-repo data (which, in local POC, is mostly stubbed or read from optional config). Each layer has different latency characteristics, different tool dependencies, and different cache invalidation rules. Keeping them separate makes the tool understandable and the cache effective.

For local-dev, two layers work differently than they would in a service:

**Layer E (cross-repo)** is mostly stubbed in the POC. The user can optionally configure a Sourcegraph URL or service catalog endpoint in `~/.codegenie/config.yaml`, in which case Layer E queries it. Without configuration, the layer emits "data unavailable, this is a local-dev gather" markers.

**Layer F (task-specific evidence)** for distroless is empty. For vulnerability remediation later, Layer F adds CodeQL or Joern probes — those are tools that run locally, so Layer F is not service-specific architecturally; it's just deferred.

---

## 4. The probe contract

Every probe implements one interface. The interface is the same in this POC as it would be in the eventual service — that's deliberate, so probes built here lift directly into the service later.

```python
# codegenie/probes/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Any
from pathlib import Path

@dataclass
class RepoSnapshot:
    root: Path
    git_commit: str | None
    detected_languages: dict[str, int]   # populated after LanguageDetectionProbe runs
    config: dict[str, Any]                # ~/.codegenie/config.yaml merged with repo .codegenie/config.yaml

@dataclass
class Task:
    type: str                # "distroless_migration", "vuln_remediation", etc.
    options: dict[str, Any]  # task-specific parameters

@dataclass
class ProbeContext:
    cache_dir: Path
    output_dir: Path           # where probe writes raw artifacts
    workspace: Path            # ephemeral workspace for the probe
    logger: Logger
    config: dict[str, Any]

@dataclass
class ProbeOutput:
    schema_slice: dict[str, Any]   # what gets merged into RepoContext
    raw_artifacts: list[Path]      # files written under output_dir
    confidence: Literal["high", "medium", "low"]
    duration_ms: int
    warnings: list[str]
    errors: list[str]


class Probe(ABC):
    name: str
    layer: Literal["A", "B", "C", "D", "E", "F", "G"]
    tier: Literal["base", "task_specific"]
    applies_to_tasks: list[str]                 # ["*"] = all
    applies_to_languages: list[str]             # ["*"] = all
    requires: list[str]                          # other probe names that must run first
    declared_inputs: list[str]                   # glob patterns or special tokens
    timeout_seconds: int = 300
    cache_strategy: Literal["content", "none"] = "content"

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        """Skip-detection beyond simple metadata matching."""
        return True

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        """Content-addressed cache key. Default: hash of declared_inputs contents."""
        ...

    @abstractmethod
    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        """Produce the schema slice this probe owns."""
        ...
```

A probe's `run` method shells out to its tool, parses the result, and returns a `ProbeOutput`. The coordinator handles caching, scheduling, timeout enforcement, and merging.

A registry decorator collects all probes:

```python
# codegenie/probes/registry.py

_REGISTRY: list[type[Probe]] = []

def register_probe(cls: type[Probe]) -> type[Probe]:
    _REGISTRY.append(cls)
    return cls

def all_probes() -> list[type[Probe]]:
    return list(_REGISTRY)
```

A probe declares itself with the decorator:

```python
@register_probe
class NodeManifestProbe(Probe):
    name = "node_manifest"
    layer = "A"
    tier = "base"
    applies_to_tasks = ["*"]
    applies_to_languages = ["javascript", "typescript"]
    requires = ["language_detection"]
    declared_inputs = ["package.json", "*-lock.yaml", "*-lock.json", "yarn.lock"]
    timeout_seconds = 30

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        ...
```

This is the same shape as the eventual service. When the POC is lifted into a service, probes move unchanged; only the coordinator's dispatch backend (asyncio → distributed worker queue) and cache backend (filesystem → object store) change.

---

## 5. Probe inventory for Node.js distroless

### 5.1 Layer A — Repo Map

#### A1. LanguageDetectionProbe

**Tools:** filesystem walk, file extension counting, marker-file detection, `tree-sitter` for ambiguous cases.

**Detects for Node:** primary language (JavaScript vs TypeScript by file count), secondary languages (Dockerfile, YAML, shell), framework hints from `package.json` dependencies (NestJS, Express, Fastify, Next.js, etc.), monorepo markers (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, `package.json#workspaces`).

**Output slice:**
```yaml
language_stack:
  primary: typescript
  secondary: [javascript, dockerfile, yaml, shell]
  detected_files:
    typescript: 247
    javascript: 32
    test: 89
  monorepo: false
  framework_hints: [nestjs, express]
  confidence: high
```

#### A2. NodeBuildSystemProbe

**Tools:** `package.json` parsing, lockfile detection, `node --version` check.

**Detects:** package manager precedence (pnpm > yarn > bun > npm by lockfile presence), `package.json#scripts` extraction, engine constraints from `engines` field and `.nvmrc`/`.node-version`, bundler detection (webpack/rollup/esbuild/vite/parcel/turbopack via dependencies and config files), TypeScript compilation setup from `tsconfig.json`.

**Output slice:**
```yaml
build_system:
  package_manager: pnpm
  package_manager_version: "8.15.0"
  node_version_constraint: ">=18.17.0"
  node_version_pinned: "20.10.0"     # from .nvmrc
  commands:
    install: "pnpm install --frozen-lockfile"
    build: "pnpm run build"
    test: "pnpm run test"
    lint: "pnpm run lint"
    start: "node dist/index.js"
  bundler: esbuild
  output_artifacts:
    - dist/index.js
    - dist/index.js.map
  typescript:
    enabled: true
    out_dir: dist
    target: es2022
    module: esnext
```

#### A3. NodeManifestProbe

**Tools:** `package.json` parser, lockfile parsers (`pnpm-lock.yaml` via YAML, `package-lock.json` via JSON, `yarn.lock` via custom parser), filesystem scan for `.node` artifacts, native module detection.

**Critical for distroless:** native modules (`bcrypt`, `sharp`, `better-sqlite3`, `node-canvas`, `node-rdkafka`) are the single largest source of distroless migration failures in Node. The probe enumerates them with full detail.

**Output slice:**
```yaml
manifests:
  - path: package.json
    direct_dependencies:
      production: 47
      dev: 23
    declared_engines:
      node: ">=18.17.0"
      pnpm: ">=8.0.0"
    lockfile:
      path: pnpm-lock.yaml
      integrity_valid: true
      total_packages_resolved: 412
    native_modules:
      detected: true
      packages:
        - name: bcrypt
          version: 5.1.1
          requires_node_gyp: true
          binary_artifacts: [node_modules/bcrypt/build/Release/bcrypt_lib.node]
        - name: sharp
          version: 0.33.0
          requires_node_gyp: true
          binary_artifacts:
            - node_modules/sharp/build/Release/sharp-linux-x64.node
            - node_modules/sharp/vendor/lib/libvips.so.42
          system_deps_required: [libvips42]
    optional_dependencies: 3
    bundled_dependencies: []
```

The `system_deps_required` field is hand-curated for known native modules. The probe's catalog encodes "sharp requires libvips," "node-canvas requires libcairo + libpango," etc. Catalog entries are YAML in `codegenie/catalogs/native-modules.yaml`; new entries are config edits.

#### A4. CIProbe

**Tools:** YAML parsers for GitHub Actions / CircleCI / GitLab CI; Jenkinsfile parser (best-effort, regex-based).

**Output slice:**
```yaml
ci:
  provider: github_actions
  workflow_files:
    - .github/workflows/ci.yml
    - .github/workflows/build-image.yml
  builds_image: true
  image_build_command: "docker build -t app:${{ github.sha }} ."
  unit_test_command: "pnpm run test"
  smoke_test_command: "pnpm run test:smoke"
  smoke_test_present: true
  smoke_test_path: scripts/smoke.sh
  build_matrix:
    node: ["18", "20"]
```

#### A5. DeploymentProbe

**Tools:** YAML parser, Helm chart traversal, Kustomize overlay walker, Terraform/HCL parser (optional, requires `hcl2` library).

**Output slice:**
```yaml
deployment:
  type: helm
  chart_path: deploy/helm/myservice
  image_reference:
    file: deploy/helm/myservice/values.yaml
    path: image.repository
    current_value: "registry.acme.com/myservice"
    tag_strategy: "git_sha"
  health_probes:
    liveness: { path: "/health", port: 3000 }
    readiness: { path: "/ready", port: 3000 }
  security_context:
    run_as_user: 1000
    run_as_non_root: true
    capabilities_dropped: [ALL]
  resource_limits:
    memory: "512Mi"
    cpu: "500m"
  exposed_ports: [3000]
  required_env_vars: [DATABASE_URL, REDIS_URL, OTEL_ENDPOINT]
```

#### A6. TestInventoryProbe

**Tools:** `package.json#scripts` inspection, filesystem walk for test files, framework detection (Vitest, Jest, Mocha, Tap, node:test, Playwright).

**Output slice:**
```yaml
test_inventory:
  framework: vitest
  unit_test_command: "pnpm run test"
  unit_test_count: 247
  integration_test_command: "pnpm run test:integration"
  smoke_test_path: scripts/smoke.sh
  e2e_framework: playwright
  coverage_data:
    present: true
    path: coverage/lcov.info
    line_coverage_pct: 78.4
    branch_coverage_pct: 71.2
```

### 5.2 Layer B — Semantic Index

#### B1. SCIPIndexProbe (Node variant)

**Tools:** `scip-typescript`, plus `tree-sitter` fallback for plain JavaScript files outside the TypeScript program.

**Why scip-typescript here:** runs without requiring a successful build. Reads `tsconfig.json`, runs the TypeScript compiler API, emits a `.scip` index. Mature; fast; trustworthy.

**Caveats specific to Node** (surfaced as confidence-affecting metadata):
- `any` types erase reference precision. Probe reports `any_type_density`.
- Dynamic imports (`import("./" + name)`) and computed access produce edges SCIP cannot resolve.
- CommonJS `require(varName)` patterns are partially resolved.

**Output slice:**
```yaml
semantic_index:
  scip_index_uri: .codegenie/context/raw/scip-index.scip
  indexer: scip-typescript
  indexer_version: "0.3.20"
  files_indexed: 247
  files_in_repo: 252
  coverage_pct: 98.0
  any_type_density: 0.04
  unresolved_dynamic_imports: 3
  unresolved_computed_access: 17
  symbol_count: 1843
  exported_symbols: 89
  scip_confidence: high
```

#### B2. IndexHealthProbe

**Tools:** internal — reads metadata from other probe outputs and surfaces freshness/coverage as first-class data.

**The single most important probe for honest confidence.** SCIP indexes can be stale or partial without surfacing the fact, and that silent staleness is the worst failure mode of the system. This probe makes it loud.

**Output slice:**
```yaml
index_health:
  scip:
    last_indexed_commit: abc123def456
    last_indexed_at: 2026-04-26T08:00:00Z
    current_commit: abc123def456
    commits_behind: 0
    files_indexed: 247
    files_in_repo: 247
    coverage_pct: 100.0
    indexer_errors: 0
    indexer_warnings: 2
    confidence: high
  runtime_trace:
    last_traced_image_digest: "sha256:abc..."
    image_digest_match: true
    last_traced_at: 2026-04-26T08:15:00Z
    scenarios_covered: [startup, smoke_test, healthcheck, shutdown, error_path]
    scenarios_missing: []
    confidence: high
  sbom:
    last_generated_at: 2026-04-26T08:10:00Z
    image_digest_match: true
    confidence: high
  semgrep:
    last_run_at: 2026-04-26T08:20:00Z
    files_scanned: 247
    rule_packs_used: [security, nodejs]
    confidence: high
```

The Planner (or a human reading the report) reads `confidence` per slice and degrades autonomy when any is `low` or `medium`.

#### B3. NodeReflectionProbe

**Tools:** `tree-sitter` queries against the source AST, ast-grep for richer pattern matching.

**Detects Node-specific dynamic patterns that erode SCIP confidence:**
- Dynamic property access: `obj[name]()` — common in plugin systems
- `eval()` and `new Function(...)` — rare in modern code, high-signal when present
- `require()` with computed strings or path-resolved arguments
- ES module dynamic imports: `await import(specifier)` where specifier is a variable
- Prototype manipulation
- Decorator usage: NestJS, TypeORM, class-validator
- Express middleware chains with dynamic composition
- `process.env.*` reads where env vars gate code branches

**Output slice:**
```yaml
reflection:
  language: typescript
  dynamic_property_access_count: 14
  eval_usage: 0
  function_constructor_usage: 0
  dynamic_require_count: 2
  dynamic_import_count: 5
  prototype_manipulation_count: 0
  decorator_usage:
    nestjs: true
    typeorm: false
    class_validator: true
    custom_decorators_detected: 3
  middleware_chains: 12
  env_var_reads:
    count: 47
    code_path_affecting: 8
  confidence_impact: medium
  affected_files: [src/plugins/loader.ts, src/middleware/dynamic.ts]
```

#### B4. GeneratedCodeProbe

**Tools:** filesystem walk, header pattern matching, generation tool detection from dependencies.

**Detects Node-specific generation:**
- GraphQL: codegen-generated types from schema files
- OpenAPI: generated client packages
- Prisma: generated client + schema
- Protocol Buffers: `.pb.ts` / `.pb.js` files
- TypeScript declaration files with "Generated by" headers
- Build artifacts: `dist/`, `build/`, `out/` directories

**Output slice:**
```yaml
generated_code:
  files:
    - path: src/generated/graphql.ts
      generator: graphql-codegen
      source_spec: src/schema.graphql
      regenerate_command: "pnpm run codegen"
    - path: src/generated/openapi-client.ts
      generator: openapi-typescript
      source_spec: openapi/users-v2.yaml
  build_outputs: [dist/index.js, "dist/**/*.js", "dist/**/*.js.map"]
```

The `build_outputs` list is what tells the Planner "these are produced by `pnpm run build`. The distroless image should run the build and copy `dist/`, not the source."

#### B5. BuildGraphProbe

**Tools:** for monorepos — `pnpm list -r --depth -1 --json`, `npm query`, `yarn workspaces list --json`, `nx graph --file=...`, `turbo run build --dry-run=json`.

**Detects:** module dependency graph in monorepos. Skipped for single-package repos (declares non-applicable via `applies()`).

**Output slice:**
```yaml
build_graph:
  build_system: pnpm-workspace
  modules:
    - name: payments-api
      path: packages/payments-api
      depends_on: [shared-models, payments-core]
      depended_on_by: [payments-integration-tests]
      build_outputs: [packages/payments-api/dist]
```

For monorepos this is critical — a change in `shared-models` has a blast radius determined by the build graph, not the source-level call graph alone.

### 5.3 Layer C — Runtime/Container

This is the heaviest layer. Probes here build images, run containers, and capture runtime evidence. Sequential by necessity (build → SBOM → trace).

#### C1. DockerfileProbe

**Tools:** `dockerfile` Python library (real parser, not regex). Falls back to BuildKit's parser via `buildctl debug dump-llb` for complex cases.

**Output slice:**
```yaml
containerization:
  dockerfiles:
    - path: Dockerfile
      stages: 2
      stage_graph:
        - name: build
          base: node:20-alpine
          purpose: build
        - name: runtime
          base: node:20-alpine
          purpose: runtime
          inherits_from: build
      final_stage:
        base_image: node:20-alpine
        base_image_registry: docker.io
        base_image_distroless: false
        package_manager_present: apk
      run_commands:
        - stage: build
          command: "apk add --no-cache python3 make g++"
          purpose: native_module_build_deps
        - stage: build
          command: "pnpm install --frozen-lockfile"
        - stage: build
          command: "pnpm run build"
        - stage: runtime
          command: "apk add --no-cache tini"
          purpose: signal_handling
        - stage: runtime
          command: "addgroup -g 1000 app && adduser -u 1000 -G app -S app"
          purpose: nonroot_user
      copy_directives:
        - from: build
          src: /app/dist
          dest: /app/dist
        - from: build
          src: /app/node_modules
          dest: /app/node_modules
        - from: build
          src: /app/package.json
          dest: /app/package.json
      entrypoint:
        form: exec
        command: ["tini", "--", "node", "/app/dist/index.js"]
      cmd: null
      user: app
      workdir: /app
      env: { NODE_ENV: production }
      exposed_ports: [3000]
      healthcheck: null
      labels: { team: payments, service: myservice }
```

#### C2. SBOMProbe

**Tools:** `docker build` (or `podman build` or `nerdctl`) + `syft`.

Builds the existing image (per `BuildSystemProbe` and `DockerfileProbe`-derived command), runs `syft` against it, persists JSON. Reconciles OS packages, language packages, and a classification of which OS packages are runtime-required vs build-only.

**Output slice:**
```yaml
sbom:
  artifact_uri: .codegenie/context/raw/syft-sbom.json
  built_image_digest: "sha256:def456..."
  package_count: 412
  packages_by_source:
    apk: 78
    npm: 334
  os_packages_classification:
    runtime_required: 12
    build_only: 23
    convenience: 18
    unknown: 25
  npm_packages_native_module_count: 3
  total_size_bytes: 487123456
```

#### C3. CVEProbe

**Tools:** `grype` against the SBOM. Optional secondary: `trivy` for cross-validation.

Runs both scanners and reconciles. If they disagree on a CVE's presence (false positive in one, true positive in the other), the probe surfaces both findings rather than picking a winner.

**Output slice:**
```yaml
cve_scan:
  artifact_uri: .codegenie/context/raw/grype-cves.json
  scanner: grype
  cross_validated_with: trivy
  scanned_image_digest: "sha256:def456..."
  total: 47
  by_severity:
    critical: 0
    high: 12
    medium: 22
    low: 13
    negligible: 0
  by_source:
    apk: 31
    npm: 16
  scanner_disagreements: 2
  top_findings:
    - cve: CVE-2023-45288
      severity: high
      package: "nghttp2 (apk)"
      fixed_in: "1.57.0-r0"
      reachable: unknown
```

#### C4. RuntimeTraceProbe (multi-scenario)

**The single most valuable probe for distroless confidence.** Without this, distroless migration breaks silently in production.

**Tools:** `docker run` + `strace -f -e trace=openat,execve,connect,bind,mmap` for syscall capture. eBPF-based tools (`bpftrace`, `bcc`) where available — lower overhead, supplements strace. Node-specific instrumentation for V8 events.

**Scenarios run** (configurable; defaults below):
1. Cold container start to ready state
2. The configured smoke test
3. Healthcheck endpoint hits (one minute of repeated polling)
4. SIGTERM-triggered graceful shutdown
5. An error condition (force a 500 by sending malformed input — best-effort, depends on test fixtures)

Each scenario produces its own trace artifact; the probe merges them into a unioned evidence set with per-scenario coverage breakdown.

**Output slice:**
```yaml
runtime_trace:
  artifact_uri: .codegenie/context/raw/runtime-trace.json
  per_scenario_artifacts:
    startup: .codegenie/context/raw/runtime-trace-startup.strace
    smoke_test: .codegenie/context/raw/runtime-trace-smoke.strace
    healthcheck: .codegenie/context/raw/runtime-trace-healthcheck.strace
    shutdown: .codegenie/context/raw/runtime-trace-shutdown.strace
    error_path: .codegenie/context/raw/runtime-trace-error.strace
  scenarios_run: [startup, smoke_test, healthcheck, shutdown, error_path]
  scenarios_failed: []
  binaries_executed: ["node", "tini"]
  shared_libs_loaded:
    - /lib/ld-musl-x86_64.so.1
    - /usr/lib/libstdc++.so.6
    - /usr/lib/libgcc_s.so.1
    - /app/node_modules/bcrypt/build/Release/bcrypt_lib.node
    - /app/node_modules/sharp/vendor/lib/libvips.so.42
    - /usr/lib/libvips.so.42
    - /usr/lib/libglib-2.0.so.0
  cert_paths_read:
    - /etc/ssl/certs/ca-certificates.crt
  files_read_at_runtime:
    summary:
      app_files: 247
      node_modules_files: 1843
      config_files: 12
      cert_files: 3
    full_list_uri: .codegenie/context/raw/runtime-files-read.txt
  shell_invocations: 0
  network_endpoints_touched:
    outbound:
      - "postgres:5432"
      - "redis:6379"
      - "otel-collector:4317"
    inbound:
      - "0.0.0.0:3000"
  trace_coverage_confidence: high
```

The `shared_libs_loaded` list is the headline output. Every entry is something the new distroless image *must* provide. Native module `.node` files, glibc/musl, libssl, libstdc++, libvips — all enumerated as ground-truth requirements.

The probe also reports `trace_coverage_confidence`. `high` if all five scenarios completed cleanly. `medium` if smoke-only. `low` if startup-only. The Planner factors this into risk scoring.

#### C5. ShellUsageProbe

**Tools:** Dockerfile static analysis from C1, runtime trace data from C4, plus a YAML-driven replacement catalog.

**Combines static and dynamic evidence about shell usage.** For each shell touchpoint, classifies it against a known-replacements catalog:

```yaml
# codegenie/catalogs/shell-replacements-node.yaml
- pattern: "^/bin/sh -c 'node /app/.+\\.js'$"
  classification: env_var_interpolation
  replacement_known: yes
  replacement: |
    Use exec-form ENTRYPOINT: ["node", "/app/dist/index.js"]
    Pass env vars through deployment manifest, not shell interpolation.
- pattern: "^npm start$"
  classification: package_manager_at_runtime
  replacement_known: yes
  replacement: |
    Resolve npm start to its underlying command (typically "node X")
    and invoke node directly. Distroless has no npm.
- pattern: "wait-for-it.sh"
  classification: startup_orchestration
  replacement_known: yes
  replacement: |
    Replace with init container or remove entirely; modern orchestrators
    handle dependency ordering via readiness probes.
```

Adding patterns is config — drop entries in the catalog. The probe doesn't change.

**Output slice:**
```yaml
shell_usage:
  static_analysis:
    entrypoint_form: exec
    cmd_form: null
    final_stage_run_commands:
      - command: "apk add --no-cache tini"
        runs_at: build_time
      - command: "addgroup -g 1000 app && adduser -u 1000 -G app -S app"
        runs_at: build_time
    startup_script_invoked: false
    healthcheck_uses_shell: false
  runtime_trace:
    sh_executions: 0
    bash_executions: 0
    sh_c_invocations: 0
    subprocess_shell_calls: []
  shell_dependent_features:
    env_var_interpolation_in_entrypoint: false
    glob_expansion_in_entrypoint: false
    chained_commands_in_entrypoint: false
  classification_summary:
    fully_replaceable: 2
    partial_or_uncertain: 0
    blocking: 0
```

#### C6. CertificateProbe

**Tools:** image filesystem inspection (via `dive` or unpacked image layers), Dockerfile RUN command analysis, runtime trace cert-path reads, source code scan for Node-specific cert loading patterns.

**Node-specific patterns scanned:**
- `process.env.NODE_EXTRA_CA_CERTS` references
- `https.globalAgent.options.ca` overrides
- `--use-openssl-ca` / `--use-bundled-ca` flags
- Programmatic CA loading via `fs.readFileSync` + `tls.createSecureContext`

**Output slice:**
```yaml
custom_certificates:
  detected: true
  paths:
    - /usr/local/share/ca-certificates/acme-internal-ca.crt
  install_method: "COPY + update-ca-certificates"
  node_extra_ca_certs_set: false
  node_use_openssl_ca: false
  programmatic_ca_overrides: []
  recommendation: |
    Use Incert to inject the internal CA into the Chainguard image.
    Verify NODE_EXTRA_CA_CERTS is not required.
```

#### C7. EntrypointProbe

**Tools:** Dockerfile parsing from C1, runtime trace signal data from C4.

Important Node-specific concern: PID 1 in Node is famously bad at signal handling. Many production Node containers use `tini` or `dumb-init` as PID 1. Distroless requires this to be explicit.

**Output slice:**
```yaml
entrypoint:
  form: exec
  command: ["tini", "--", "node", "/app/dist/index.js"]
  pid_1_program: tini
  signal_handler_present: true
  signal_handler_method: tini
  invokes_script_file: false
  graceful_shutdown_observed: true
  graceful_shutdown_method: "process.on('SIGTERM')"
```

### 5.4 Layer D — Organizational

#### D1. RepoConfigProbe

**Tools:** YAML parser for AGENTS.md/CLAUDE.md frontmatter.

Reads `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`. Parses frontmatter for declared repo properties. Body content is *not* loaded into the artifact body — only metadata about availability. The Planner reads the body via direct file read when relevant.

#### D2. SkillsIndexProbe

**Tools:** filesystem walk of `~/.codegenie/skills/` (user-global) + `.codegenie/skills/` (repo-local) + `~/.codegenie/skills-org/` (org shared, optional). YAML frontmatter parser.

Emits a manifest of available Skills with descriptions only — progressive disclosure. For Node distroless, the relevant Skills are:

```yaml
# ~/.codegenie/skills/distroless-node-generic/SKILL.md
---
name: distroless-node-generic
description: |
  Generic Node.js distroless migration for services without native modules.
  Targets cgr.dev/chainguard/node. Multi-stage build with build-time
  dependencies separated from runtime image. Handles tini-based signal
  handling and environment variable propagation.
applies_to:
  task_types: [distroless_migration]
  languages: [javascript, typescript]
  conditions:
    - native_modules_present: false
requires_evidence:
  - language_stack
  - build_system
  - manifests
  - containerization
  - runtime_trace
  - shell_usage
  - custom_certificates
required_tools: [dfc, syft, grype, incert]
---
# Skill body — instructions for the Planner, not the gatherer
...
```

```yaml
# ~/.codegenie/skills/distroless-node-native-modules/SKILL.md
---
name: distroless-node-native-modules
description: |
  Distroless migration for Node.js services with native modules
  (bcrypt, sharp, better-sqlite3, etc.). Requires a glibc-compatible
  base image, careful build-time / runtime split, and explicit copying
  of vendored shared libraries.
applies_to:
  task_types: [distroless_migration]
  languages: [javascript, typescript]
  conditions:
    - native_modules_present: true
requires_evidence:
  - language_stack
  - build_system
  - manifests
  - containerization
  - runtime_trace
  - shell_usage
  - custom_certificates
required_tools: [dfc, syft, grype, incert]
---
```

Adding a new variant is dropping a new SKILL.md. No probe changes.

#### D3. ADRProbe

**Tools:** filesystem walk of conventional ADR locations (`docs/adr/`, `docs/architecture/`, `docs/decisions/`), markdown parser for title/status extraction.

Emits list of ADR titles and IDs only; full bodies not loaded into artifact.

#### D4. PolicyProbe

**Tools:** YAML parser. Reads policy-as-code linked via `~/.codegenie/config.yaml` or `.codegenie/config.yaml`'s `policy_repos:` field.

For local dev, this is typically a path to a checked-out policy repo:

```yaml
# ~/.codegenie/config.yaml
policy_repos:
  - path: ~/work/acme-policies
    type: container_policy
```

#### D5. ConventionProbe

**Tools:** YAML rule loader, regex/AST-based pattern matcher.

Conventions live in a central YAML file:

```yaml
# ~/.codegenie/conventions/node.yaml
- name: acme-tini-required
  description: "All Node services must use tini as PID 1"
  detect:
    type: dockerfile_pattern
    pattern: 'ENTRYPOINT \["tini"'
- name: acme-nonroot-required
  description: "Final stage must run as nonroot user"
  detect:
    type: dockerfile_pattern
    pattern: 'USER (?!root|0)'
- name: acme-no-npm-runtime
  description: "Runtime image must not include npm/pnpm/yarn"
  detect:
    type: dockerfile_pattern_inverted
    pattern: '(npm|pnpm|yarn) (start|run)'
```

#### D6. ExceptionProbe

**Tools:** YAML parser. Reads `.codegenie/exceptions.yaml` if present, plus an optional org-wide exceptions file.

```yaml
# .codegenie/exceptions.yaml
- repo_glob: "myservice"
  task: distroless_migration
  reason: "JNI native lib not yet replaced"
  expires: 2026-09-01
  approver: "@platform-team"
```

The Planner refuses to act on tasks that violate active, unexpired exceptions.

#### D7. RepoNotesProbe

**Tools:** filesystem walk, markdown heading extractor.

The mechanism for capturing org-specific knowledge that doesn't fit any other probe — the long Slack thread from 2023 explaining why this service handles SIGTERM weirdly, the unwritten convention about not deploying on Fridays, the warning about a fragile dependency. Anything a team member wants the Planner to know about this repo.

Walks `.codegenie/notes/` and extracts headings from each markdown file. Bodies are *not* parsed or interpreted — they're referenced by path. The Planner reads them directly when relevant.

```yaml
repo_notes:
  notes_dir: ".codegenie/notes"
  files:
    - path: ".codegenie/notes/distroless-considerations.md"
      headings: ["Native modules in this service", "Cert handling", "Why we use tini"]
      char_count: 1247
      last_modified: "2026-03-14T09:22:00Z"
    - path: ".codegenie/notes/dont-touch-the-rate-limiter.md"
      headings: ["Background", "What broke last time", "Who to ping"]
      char_count: 890
      last_modified: "2025-11-08T14:55:00Z"
```

This is the mechanism by which tribal knowledge becomes structured data. The first time a team member runs the gatherer and notices the Planner is missing important context, they write a note. From that point forward, the note is part of every gather, versioned in the repo, owned by the team. The gatherer doesn't summarize it; it just makes sure the Planner knows it exists.

#### D8. ExternalDocsProbe

**Tools:** Confluence/Notion API clients (optional, opt-in via config), filesystem walk for local doc directories, HTTP fetcher for URL lists, markdown converter for HTML pages.

For docs that live outside the repo — Confluence pages, Notion databases, internal wiki, design docs in shared filesystem locations, blog posts, runbooks. Discovery is config-driven:

```yaml
# .codegenie/config.yaml
external_docs:
  - type: confluence
    space: PAYMENTS
    pages_matching_repo: true       # pages tagged with this repo's name
  - type: notion
    database_id: abc123
  - type: filesystem
    path: ~/work/internal-docs/payments-platform
  - type: url_list
    urls:
      - https://eng.acme.com/blog/2024-payments-architecture
```

The probe fetches each declared source, normalizes to markdown, stores under `.codegenie/context/raw/external-docs/`, and emits a manifest. Bodies are stored as opaque text — *not* parsed, summarized, or interpreted. The probe does deterministic things only:

- Extracts headings into a per-document table of contents
- Pulls out frontmatter, explicit tags, original URI, fetch timestamp
- Extracts URLs and code blocks (often the highest-signal content within a doc)
- Records character count and last-modified timestamp

For local-dev POC, this probe is opt-in. Most local-dev gathers will have empty `external_docs` config and the probe will skip cleanly.

```yaml
external_docs:
  fetched_count: 8
  fetch_status: complete
  fetch_failures: []
  documents:
    - source: confluence
      title: "Payments Platform Architecture Overview"
      original_uri: "https://acme.atlassian.net/wiki/spaces/PAYMENTS/pages/12345"
      local_path: ".codegenie/context/raw/external-docs/payments-platform-architecture.md"
      fetched_at: "2026-04-26T14:32:00Z"
      char_count: 8472
      headings: ["Service responsibilities", "Data flow", "Failure modes", "Operational concerns"]
      tags: [architecture, payments]
    - source: filesystem
      title: "Distroless migration retrospective"
      original_path: "~/work/internal-docs/payments-platform/distroless-retro.md"
      local_path: ".codegenie/context/raw/external-docs/distroless-migration-retrospective.md"
      char_count: 2890
      headings: ["What we learned", "What broke", "What we'd do differently", "Native modules and you"]
      tags: [retrospective, distroless]
```

#### D9. ExternalDocsIndexProbe

**Tools:** Tantivy or a small ripgrep-based fallback for BM25 indexing.

Builds a deterministic keyword search index over the documents fetched by D8 — title, headings, first paragraph, and tags. **No semantic embedding, no LLM summarization.** Pure BM25. Same query, same results, every time.

```yaml
external_docs_index:
  bm25_index_uri: ".codegenie/context/raw/external-docs/bm25.idx"
  document_count: 8
  total_chars: 47230
  searchable: true
  index_method: bm25_tantivy
```

The Planner queries this index on demand — *"is there a doc about JRE versions?"*, *"is there a retrospective on distroless?"* — and gets back document references. It then reads the original document directly, with full context of the current decision, using its own LLM. **The gather pipeline never summarizes a doc; the Planner reads originals at decision time.**

This three-probe pattern (RepoNotesProbe + ExternalDocsProbe + ExternalDocsIndexProbe) is the architecture's answer to "what about unstructured org knowledge." The principle holds: **the gatherer makes evidence findable; the Planner interprets it at decision time, never the gatherer at gather time.** Adding an LLM summarization step here would violate the determinism, cacheability, and auditability properties the rest of the system depends on. Lightweight deterministic indexing gives the Planner what it needs without compromising those properties.

### 5.5 Layer E — Cross-repo / Operational

These probes are mostly stubbed for local-dev. They emit "data unavailable" markers when their data sources aren't configured. When configured (via `~/.codegenie/config.yaml`), they pull from real sources.

#### E1. OwnershipProbe

**Tools:** `CODEOWNERS` parser, optional internal service catalog HTTP query.

#### E2. ServiceTopologyProbe

**Tools:** optional service mesh API client (Istio, Linkerd, Consul Connect), optional service catalog client (Backstage, Cortex, OpsLevel). For local dev, typically empty.

#### E3. ServiceContractProbe

**Tools:** OpenAPI/Swagger YAML parser, gRPC `.proto` parser via `protoc`, GraphQL schema parser. Source-code scan for HTTP client base URL declarations using `tree-sitter` queries.

For Node, contract sources:
- OpenAPI specs in `openapi/`, `api/`
- gRPC `.proto` files
- GraphQL schemas
- tRPC procedure definitions

Consume-side detection scans for:
- `axios.create({ baseURL: ... })` and similar
- Generated OpenAPI client packages in dependencies
- gRPC client stubs from `@grpc/grpc-js`
- GraphQL client base URL declarations

#### E4. SLOProbe / E5. ProductionConfigProbe

Stubbed for local dev. Skipped unless config points at SLO definitions or production manifests.

### 5.6 Layer G — Behavioral Hints + SAST

This is where SAST and pattern-matching tools live. They provide supplementary evidence not in the structural index.

#### G1. SemgrepProbe

**Tools:** `semgrep` with curated rule packs.

For Node distroless, runs targeted rule packs:
- `p/dockerfile` — Dockerfile best practices
- `p/nodejs` — Node-specific patterns (eval, child_process, dangerous serialization)
- `p/javascript` — general JS hygiene
- `p/secrets` — hardcoded secrets that would be carried into the image
- Custom rules in `~/.codegenie/semgrep-rules/`

For Phase 2 vuln remediation, additional rule packs:
- `p/owasp-top-ten`
- `p/cwe-top-25`

**Output slice:**
```yaml
semgrep_findings:
  artifact_uri: .codegenie/context/raw/semgrep-findings.json
  rules_run: 247
  files_scanned: 247
  findings_by_severity:
    error: 0
    warning: 3
    info: 12
  findings_summary:
    - rule: nodejs.eval-detected
      severity: error
      file: src/plugins/loader.ts
      line: 42
    - rule: dockerfile.no-root-user
      severity: warning
      file: Dockerfile
      line: 18
```

#### G2. AstGrepProbe

**Tools:** `ast-grep` for richer structural pattern matching that semgrep doesn't easily express.

Used for catching patterns specific to your org — internal framework usage, deprecated API calls, custom anti-patterns. Rules live in `~/.codegenie/ast-grep-rules/`.

#### G3. TestCoverageMappingProbe

**Tools:** `lcov.info` parser, `coverage-final.json` parser, SCIP symbol resolution.

Maps existing tests to source code via coverage data and SCIP's call graph. Output:

```yaml
test_coverage_map:
  - test_id: src/payments/paymentProcessor.test.ts::PaymentProcessor::processRefund
    test_file: src/payments/paymentProcessor.test.ts
    exercises:
      - src/payments/paymentProcessor.ts::processRefund
      - src/payments/paymentProcessor.ts::validateRefund
      - src/payments/refundCalculator.ts::calculate
  - test_id: scripts/smoke.sh
    test_file: scripts/smoke.sh
    exercises_unknown: true
    container_paths_exercised:
      - "GET /health"
      - "GET /ready"
      - "POST /api/v1/payments"
```

#### G4. InvariantHintProbe

**Tools:** `tree-sitter` query for assertion patterns, JSDoc / TypeScript type contract extraction.

Scans for declared invariants — asserts, descriptive test names, type-narrowing patterns, validation library usage (zod, yup, joi, class-validator). These aren't a behavioral spec but they're hints about what the code is supposed to guarantee.

#### G5. GrepProbe (the catch-all)

**Tools:** `ripgrep`.

Runs a small set of curated grep patterns that don't fit elsewhere — looks for common red flags that would block distroless migration:
- Hardcoded paths to `/bin/`, `/usr/bin/`, `/sbin/`
- `exec()` / `spawn()` / `execSync()` calls
- `process.platform` / `os.platform()` checks (suggests platform-specific behavior)
- `LD_PRELOAD`, `LD_LIBRARY_PATH` references

Findings are surfaced as flags for the Planner, not as judgments.

### 5.7 What Layer F looks like (Phase 2, not in this POC)

For vulnerability remediation, Layer F adds:
- `CodeQLDatabaseProbe` (creates the CodeQL DB locally via `codeql database create`)
- `TaintFlowProbe` (runs taint queries from a curated rule set)
- `ReachabilityProbe` (queries reachability for a specific symbol)
- `ExploitabilityProbe` (cross-references EPSS, KEV)
- `FixAvailabilityProbe` (queries vendor advisories)
- `HistoricalFixProbe` (searches `git log` for prior fixes of the same vuln class)

Not implemented in the POC. Mentioned here to show the extension surface stays clean.

---

## 6. Tool dependencies

The CLI checks for required tools at startup and prints clear errors with installation instructions.

| Tool | Required? | Used by | Install |
|---|---|---|---|
| Python 3.11+ | required | the CLI itself | system package manager or pyenv |
| Docker or Podman | required | C1, C2, C3, C4, C6 | docker.com or podman.io |
| BuildKit | recommended | C1 | bundled with modern Docker |
| `scip-typescript` | required | B1 | `npm install -g @sourcegraph/scip-typescript` |
| `tree-sitter` (CLI + Python bindings) | required | A1, B3, G4 | `pip install tree-sitter` + grammar packs |
| `syft` | required | C2 | anchore.com/syft |
| `grype` | required | C3 | anchore.com/grype |
| `trivy` | optional | C3 cross-validation | aquasecurity.github.io/trivy |
| `semgrep` | required | G1 | `pip install semgrep` |
| `ast-grep` | recommended | G2 | `cargo install ast-grep` or `npm install -g @ast-grep/cli` |
| `ripgrep` | required | G5 | `cargo install ripgrep` or system pkg |
| `tantivy` (Python bindings) | recommended | D9 | `pip install tantivy` (BM25 over external docs; falls back to ripgrep if absent) |
| `strace` | required (Linux) | C4 | system package manager |
| `bpftrace` / `bcc` | optional | C4 | system package manager |
| `dive` | optional | C2, C6 | github.com/wagoodman/dive |
| `tini` (binary check) | recommended | C7 | the user's Dockerfile usually pulls this |
| `chainctl` | optional | future | chainguard.dev |
| `dfc` | optional | future Planner | github.com/chainguard-dev/dfc |
| `incert` | optional | future Planner | github.com/chainguard-dev/incert |

For macOS, `strace` doesn't exist; the probe falls back to `dtruss` (with sudo) or skips runtime tracing with a clear warning. For local dev, this is acceptable — most users gather on Linux or in a Linux VM/container.

---

## 7. The RepoContext schema

Single YAML file with a versioned schema. Validated by JSON Schema. Excerpt:

```yaml
schema_version: "1.0.0-node-distroless-poc"
repo_id: org/myservice
gathered_at: "2026-04-26T14:32:18Z"
gather_duration_ms: 187293
gather_status: complete           # or "partial" with probe_failures populated
probe_failures: []
task_context:
  task_type: distroless_migration
  triggered_by: manual_cli
  cli_version: "0.1.0"

# Layer A
language_stack: { ... }
build_system: { ... }
manifests: [ ... ]
ci: { ... }
deployment: { ... }
test_inventory: { ... }

# Layer B
semantic_index: { ... }
index_health: { ... }
reflection: { ... }
generated_code: { ... }
build_graph: { ... }              # null if not monorepo

# Layer C
containerization: { ... }
sbom: { ... }
cve_scan: { ... }
runtime_trace: { ... }
custom_certificates: { ... }
shell_usage: { ... }
entrypoint: { ... }

# Layer D
organizational:
  agents_md_present: true
  agents_md_path: AGENTS.md
  available_skills: [ ... ]
  adrs: [ ... ]
  policies: { ... }
  conventions: { ... }
  exceptions: { ... }
  repo_notes: { ... }            # from RepoNotesProbe (D7)
  external_docs: { ... }         # from ExternalDocsProbe (D8); empty if not configured
  external_docs_index: { ... }   # from ExternalDocsIndexProbe (D9); empty if no docs

# Layer E (often sparse for local dev)
ownership: { ... }
service_topology: { stub: true }
inter_service: { ... }
slo: { stub: true }
production_config: { stub: true }

# Layer F (empty for distroless)
task_specific_evidence: {}

# Layer G
test_coverage_map: [ ... ]
semgrep_findings: { ... }
ast_grep_findings: { ... }
invariant_hints: { ... }
grep_findings: { ... }
```

The full file is large — typically a few hundred KB of YAML for a real Node service. Most of the bulk is in the raw artifact files; the `repo-context.yaml` is the index pointing at them.

---

## 8. Caching

Cache is filesystem-based, content-addressed, scoped to the repo's `.codegenie/cache/` directory.

**Cache key:** `sha256(probe_name | probe_version | inputs_hash)` where `inputs_hash` is computed from the `declared_inputs` field — typically the Merkle root of the relevant subtree, or an external resource fingerprint (image digest for SBOM probe, etc.).

**Cache hit check** at probe dispatch time. If the cache key resolves to a fresh entry (TTL configurable, default 24 hours), the probe is skipped and the cached output is loaded.

**Three modes** controlled by CLI flag:

```
codegenie gather --task distroless-migration .                 # default: fresh-on-trigger
codegenie gather --task distroless-migration --cache-only .    # error on miss
codegenie gather --task distroless-migration --no-cache .      # ignore cache
```

For local-dev, cache reuse is most valuable when iterating on probe code or skills — you don't want to re-run the 80-second runtime trace just because you changed how Layer A formats its output.

Cache invalidates automatically when:
- Probe code version changes (each probe declares a `version` constant; bumping invalidates that probe's entries)
- Schema version changes
- Declared inputs change

---

## 9. Output: the human-facing report

The most important output for local-dev isn't `repo-context.yaml` — it's `CONTEXT_REPORT.md`. This is what a human reads to understand whether the migration is safe to attempt.

Generated from a Jinja2 template that consumes the validated `RepoContext`:

```markdown
# Context Report: org/myservice
*Generated 2026-04-26 14:32 UTC for task `distroless_migration`*

## Summary

- **Language:** TypeScript (NestJS)
- **Build:** pnpm 8.15 + esbuild → `dist/`
- **Current image:** `node:20-alpine` (multi-stage)
- **Target image class:** `cgr.dev/chainguard/node` with native-module support
- **Selected skill:** `distroless-node-native-modules`

## Confidence

- SCIP index: HIGH (100% file coverage, 0 indexer errors)
- Runtime trace: HIGH (5/5 scenarios completed)
- SBOM: HIGH (image digest matches current Dockerfile)
- Semgrep: HIGH (247 files scanned)

**Overall gather confidence: HIGH.**

## Risk flags

- **Native modules detected:** sharp (libvips), bcrypt
  - Both are well-known and supported by the `chainguard/node:latest-dev` base
  - libvips must be present in runtime image; trace confirmed it is loaded
- **Custom CA certificate detected:** `acme-internal-ca.crt`
  - Use `incert` to inject into Chainguard image
- **Convenience packages in current image:** curl, jq, vim
  - These will be lost in distroless. Verify nothing in deploy scripts depends on them.

## Blast radius

- 0 shared library callers (this is an application, not a library)
- 3 downstream services (from service catalog)
  - api-gateway → consumes /api/v1/* endpoints
  - billing-service → consumes /api/v1/payments
  - reporting-service → consumes /api/v2/payments
- No cross-repo SCIP callers detected

## Validation plan derivation

Based on the gathered evidence, the following validation should run during migration execution:

1. Build the new distroless image
2. Generate SBOM and CVE scan; assert CVE count ≤ current
3. Run unit tests (`pnpm run test`) — 247 tests
4. Run smoke test (`scripts/smoke.sh`)
5. Trace the new image under all 5 scenarios; compare shared library load list to current
6. Run integration tests if present (Playwright detected — 12 tests)

## Available skills

- `distroless-node-generic` (does not apply: native modules detected)
- `distroless-node-native-modules` (applies — selected)
- `distroless-node-monorepo` (does not apply: not a monorepo)

## ADRs referenced

- ADR-0014: "Node services must run as nonroot user" — current Dockerfile compliant

## Conventions check

- ✓ acme-tini-required: tini detected as PID 1
- ✓ acme-nonroot-required: USER app (uid 1000)
- ✓ acme-no-npm-runtime: no npm/pnpm/yarn invocations at runtime

## Raw evidence

| File | What |
|---|---|
| `.codegenie/context/raw/scip-index.scip` | Full SCIP index (1.2 MB) |
| `.codegenie/context/raw/syft-sbom.json` | Complete SBOM (412 packages) |
| `.codegenie/context/raw/grype-cves.json` | CVE findings (47 total) |
| `.codegenie/context/raw/runtime-trace.json` | Merged runtime evidence |
| `.codegenie/context/raw/semgrep-findings.json` | SAST results |

---

*Run `codegenie report --explain <field>` to drill into any field above.*
```

This report is the artifact a human reviews before handing off to the Planner. It surfaces the high-signal data without requiring the human to read raw probe outputs.

---

## 10. Coverage of identified gaps

The earlier conversations surfaced specific gaps in pure AST + SCIP. Here's how the POC addresses each:

| Gap | How the POC closes it |
|---|---|
| Dynamic behavior is invisible | Multi-scenario `RuntimeTraceProbe` (C4) — 5 scenarios capture syscalls, library loads, file reads. `NodeReflectionProbe` (B3) flags dynamic patterns that SCIP can't resolve. |
| Reflection / dynamic dispatch | `NodeReflectionProbe` (B3) enumerates dynamic property access, eval, dynamic require/import, decorator usage, env-var-gated branches. Reported as `confidence_impact: medium/low` on affected files. |
| Cross-language calls | `ServiceContractProbe` (E3) parses OpenAPI, gRPC, GraphQL, tRPC contracts. Detects consumed contracts via source scan. |
| Generated code partially indexed | `GeneratedCodeProbe` (B4) detects all common Node generators, links generated files back to source specs. |
| Build-system semantics absent | `BuildGraphProbe` (B5) extracts module dependency graph for monorepos. |
| No taint flow / dataflow (Phase 2) | Layer F left empty in POC. Schema accommodates `CodeQLDatabaseProbe` and `TaintFlowProbe` for vuln remediation. |
| Stale/partial index detection | `IndexHealthProbe` (B2) — surfaces freshness and coverage as first-class data. The single most important gap mitigation. |
| Symbol-level granularity only | `tree-sitter` queries in B3, G4 give finer-grained AST analysis. SCIP for symbol-level; tree-sitter for statement-level. |
| Behavioral equivalence undefined | `TestCoverageMappingProbe` (G3) and `InvariantHintProbe` (G4) provide raw evidence. Behavioral equivalence judgment is a Planner / LLM-judge concern, not a gatherer concern. |
| Fuzzy matches absent | `GrepProbe` (G5) for cheap pattern matching. Embeddings deliberately excluded — keeps the system deterministic. |
| Tree-sitter has no semantics | Combined with SCIP (B1) for type info; `tree-sitter` used only for syntactic queries. |
| Unstructured org knowledge (wikis, design docs, tribal knowledge) | Three-layer pattern. `RepoNotesProbe` (D7) makes `.codegenie/notes/` a first-class place for team-authored notes. `ExternalDocsProbe` (D8) fetches Confluence/Notion/filesystem docs as opaque blobs with provenance. `ExternalDocsIndexProbe` (D9) builds a deterministic BM25 keyword index for retrieval. The Planner reads originals at decision time; the gatherer never summarizes prose. |
| Tribal knowledge not yet written down | The autonomy ladder. Low autonomy keeps a human in the loop; as teams encode discovered knowledge as conventions, exceptions, and notes, autonomy ratchets up. The system learns by accumulating structured data, not by inferring what isn't there. |

Two additional defensive measures worth noting:

**The `ShellUsageProbe` catalog pattern** — every shell touchpoint is classified against a known-replacements catalog, with each entry marked `replacement_known: yes/no/depends`. Patterns the catalog doesn't recognize are flagged as unknowns rather than silently ignored.

**Cross-validation of CVE results** — `CVEProbe` runs both `grype` and `trivy` and reports disagreements rather than picking a winner. Trusting one scanner blindly is exactly the kind of decision the gatherer should not make.

**No LLM anywhere in the gather pipeline** — including in the merge step and in handling of unstructured docs. The merger is structural composition (each probe owns a disjoint schema slice; merging is just placing each in its named section and validating). Unstructured docs are stored as opaque blobs with deterministic indexing (BM25 over headings and metadata); the Planner reads originals at decision time using its own LLM, in the context of a specific question. This keeps the artifact reproducible, cacheable, and auditable — the foundational properties every layer above this one depends on.

---

## 11. Extension model

The architectural property this POC must protect is that adding new languages and tasks is purely additive.

### 11.1 Adding Java tomorrow

1. Write language-specific probes:
   - `JavaBuildSystemProbe` (Maven/Gradle/sbt detection)
   - `JavaManifestProbe` (POM/Gradle dependency parsing)
   - `JavaReflectionProbe` (Spring/Hibernate/JNI)
   - Wire `scip-java` into `SCIPIndexProbe`'s indexer dispatch
2. Add Java to existing probes' applicability lists where they're language-agnostic (most Layer D/E/G probes already are).
3. Write Java-specific Skills (`distroless-java-springboot-jre`, `distroless-java-graalvm`).
4. Add Java conventions to `~/.codegenie/conventions/java.yaml`.

No coordinator changes. No schema changes (Java-specific fields go in `manifests[].java`). No CLI changes.

### 11.2 Adding vulnerability remediation

1. Add Layer F probes (`CodeQLDatabaseProbe`, `TaintFlowProbe`, `ReachabilityProbe`, etc.).
2. Add task-specific Skills with `requires_evidence` declarations.
3. Extend the schema with the `task_specific_evidence.vulnerability` section.
4. Add new CLI subcommand or flag: `codegenie gather --task vuln-remediation --cve CVE-2026-1234 .`

Existing distroless probes are untouched. Existing Skills untouched. Schema extends; doesn't break.

### 11.3 Lifting to a service later

The probe contract is identical to what the eventual service would use. The lift involves:
- Replace asyncio-based coordinator with a distributed worker queue (Temporal, Dagster, Airflow)
- Replace filesystem cache with an object store (S3) and a Postgres metadata index
- Replace local subprocess execution with sandboxed microVMs
- Add an MCP server in front of the artifact for agent consumption
- Add multi-repo orchestration

None of these changes touch probe code. The probe contract is the contract.

---

## 12. Implementation milestones

A two-engineer team can land the POC in about 4-6 weeks. Suggested ordering:

**Week 1: Skeleton.**
- CLI scaffolding (`click`, argument parsing)
- Probe contract + registry
- Coordinator (asyncio, parallel dispatch, timeout)
- Cache layer (filesystem-backed)
- JSON Schema definition + validation
- Layer A probes: LanguageDetection, NodeBuildSystem, NodeManifest, CI, Deployment, TestInventory
- Output writer: `repo-context.yaml` + raw artifacts directory
- First end-to-end run: produces a partial RepoContext for a Node repo

**Week 2: Semantic index + Dockerfile.**
- SCIPIndexProbe (scip-typescript integration)
- IndexHealthProbe
- DockerfileProbe (real parser, not regex)
- ShellUsageProbe (with initial catalog)
- CertificateProbe
- EntrypointProbe
- CONTEXT_REPORT.md template + generator

**Week 3: Heavy runtime probes.**
- SBOMProbe (syft integration; build the image first)
- CVEProbe (grype, optional trivy cross-validation)
- RuntimeTraceProbe single-scenario (smoke test only — multi-scenario in Week 4)

**Week 4: Multi-scenario tracing + SAST.**
- RuntimeTraceProbe multi-scenario (startup, smoke, healthcheck, shutdown, error)
- SemgrepProbe with curated rule packs
- AstGrepProbe (optional)
- GrepProbe
- TestCoverageMappingProbe

**Week 5: Layer D + organizational context.**
- RepoConfigProbe, SkillsIndexProbe, ADRProbe, ConventionProbe, ExceptionProbe
- RepoNotesProbe (`.codegenie/notes/` discovery + heading extraction)
- ExternalDocsProbe (filesystem + URL list sources first; Confluence/Notion deferred to v0.2)
- ExternalDocsIndexProbe (BM25 via Tantivy or ripgrep fallback)
- Convention catalog + first ruleset for Node
- Skills directory structure + first three Skills (`distroless-node-generic`, `distroless-node-native-modules`, `distroless-node-monorepo`)

**Week 6: Polish.**
- NodeReflectionProbe
- GeneratedCodeProbe
- BuildGraphProbe (monorepo support)
- Layer E stubs with optional configuration
- ServiceContractProbe (OpenAPI/gRPC/GraphQL)
- End-to-end testing on three real repos
- Documentation
- Tag v0.1.0

After v0.1.0 ships, the next milestones are:
- v0.2.0: Java support (Week 7-8)
- v0.3.0: Layer F for vulnerability remediation (CodeQL integration)
- v1.0.0: Service lift

---

## 13. Configuration reference

Three configuration files:

**`~/.codegenie/config.yaml`** — user-global defaults:
```yaml
default_task: distroless_migration
sourcegraph:
  enabled: false
  url: https://sourcegraph.acme.com
  token_env: SG_TOKEN
service_catalog:
  enabled: false
  type: backstage
  url: https://backstage.acme.com
policy_repos:
  - path: ~/work/acme-policies
conventions_dir: ~/.codegenie/conventions
skills_dirs:
  - ~/.codegenie/skills
  - ~/.codegenie/skills-org
runtime_trace:
  scenarios: [startup, smoke_test, healthcheck, shutdown, error_path]
  scenario_timeout_seconds: 60
sandbox:
  type: native            # POC: native subprocess; future: docker, firecracker
  cpu_quota: 4
  memory_limit_mb: 8192
```

**`.codegenie/config.yaml`** in the repo — repo-specific overrides:
```yaml
runtime_trace:
  scenarios: [startup, smoke_test, shutdown]    # skip error_path for this repo
  smoke_test_command_override: "pnpm run test:smoke:fast"
exceptions_path: .codegenie/exceptions.yaml
```

**`.codegenie/exceptions.yaml`** — repo-specific exceptions to active rules.

CLI flags override config-file settings for one-off use.

---

## 14. Why this design holds

Three properties make it durable as the POC grows toward the service.

**Determinism is preserved end-to-end.** No probe invokes an LLM. Same inputs always produce same outputs. Reproducible, cacheable, auditable. When a planning judgment turns out wrong, you can replay the gather to byte-identical evidence and find where the human (or LLM) made the bad call versus where the gatherer surfaced misleading data.

**Each probe owns one schema slice.** Failure isolation falls out — a flaky service-topology query doesn't break the gather. Extensibility falls out — adding Java is one set of new probes, not a refactor. Cacheability falls out — per-probe cache keys mean most gathers hit warm cache.

**Organizational uniqueness lives in data, not prompts.** Skills with frontmatter, conventions catalogs, policy YAML, replacement catalogs — every piece of company-specific knowledge is structured data probes read with deterministic parsers. New rules are config edits. The Planner never has to guess; it queries. This is what lets the same architecture serve a fintech with strict compliance ADRs, a healthcare company with HIPAA-driven exceptions, and a SaaS company with custom internal frameworks — without re-architecting per organization.

The gatherer is the foundation. Get it right and the Planning agent has truthful, structured context to write a Change Contract against. Get it wrong and no validation downstream saves the system from making changes based on a hallucinated picture of the repo. The design above prioritizes that correctness — at the cost of some implementation complexity in the probes — because every layer above this one depends on what comes out of it.