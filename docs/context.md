# Context-Gathering Component Design

*The Layer 1 component for an autonomous code-change pipeline. AST + SCIP hybrid, language- and build-system-agnostic, supporting arbitrary company-specific uniqueness.*

*Phase 1 target: Chainguard distroless container migration. Extensible to vulnerability remediation, language upgrades, and any other code-modification task.*

---

## What this component does

This is the first thing the system runs on every task, and it's the layer that determines whether everything downstream succeeds. A bad Change Contract built on incomplete context produces a bad PR no matter how good the agent or validators are.

The component has one job: **produce a structured `RepoContext` artifact that the Planning layer can use to author a Change Contract and Impact Map.** It does not write code, does not reason about the task, does not call the LLM for transformation. It gathers, structures, and persists.

---

## What context the agent actually needs for distroless migration

For distroless specifically, the agent has to answer six questions before it can plan a safe migration. The context gatherer's job is to make sure each question has a deterministic, evidence-backed answer in the `RepoContext` artifact:

1. **What language and runtime is this?** Drives the target Chainguard base image (`cgr.dev/chainguard/jre`, `chainguard/python`, `chainguard/go`, etc.) and which Skill to load.
2. **How is it built today?** The current Dockerfile, build tool, build commands, multi-stage structure, and entrypoint determine the transformation strategy.
3. **What does the running container actually need?** Static SBOM analysis catches packages; runtime tracing catches the things that load via `dlopen`, read from cert stores, or shell out at startup. Both are required.
4. **What changes if the container surface changes?** Entrypoint behavior, signal handling, file writes, port bindings, healthcheck commands — these are the runtime contract with the orchestrator (Kubernetes, ECS, Nomad). Breaking them silently is the worst failure mode.
5. **What conventions does this organization expect?** Custom base image policy, internal cert handling, approved registries, mandatory labels, deployment patterns. This is where company uniqueness lives.
6. **How is this repo connected to the rest of the org?** Cross-repo callers, shared libraries, downstream services that consume this image. SCIP answers most of this; service-mesh data and ownership metadata fill the rest.

The same structure extends to Phase 2 vulnerability work — the questions change ("what's the vulnerable symbol's blast radius?" replaces "what binaries does this container need?") but the gatherer's shape is identical. Build it for distroless, scale it to vulns by adding new Probes.

---

## Architectural shape: a parallel probe pipeline

The gatherer is a fan-out / fan-in pipeline. A single coordinator dispatches independent **Probes** in parallel, each Probe producing one slice of the context. Probes don't talk to each other — they read the repo, run their tool, write structured output. This isolation is what makes the system extensible to any language, package manager, or repo type: adding Node.js support means writing a `NodeProbe`, not modifying anything else.

```
                    ┌──────────────────────┐
                    │  Context Coordinator  │
                    │  (orchestrates fan-   │
                    │   out and merges)     │
                    └──────────┬────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
        │                      │                          │
        ▼                      ▼                          ▼
┌──────────────┐     ┌──────────────────┐       ┌──────────────────┐
│  Layer A:    │     │  Layer B:        │       │  Layer C:        │
│  Repo Map    │     │  Semantic Index  │       │  Runtime/        │
│  Probes      │     │  Probes          │       │  Container       │
│              │     │                  │       │  Probes          │
│ - Language   │     │ - SCIP find-refs │       │ - Dockerfile     │
│ - Build tool │     │ - Symbol graph   │       │   parse          │
│ - Manifests  │     │ - Import graph   │       │ - Syft SBOM      │
│ - CI files   │     │ - Cross-repo     │       │ - Grype CVE      │
│ - K8s/Helm   │     │   callers        │       │ - Runtime trace  │
│ - Tests      │     │                  │       │ - Cert detection │
└──────────────┘     └──────────────────┘       └──────────────────┘
        │                      │                          │
        │            ┌─────────┴─────────┐                │
        │            ▼                   ▼                │
        │   ┌─────────────────┐  ┌──────────────────┐    │
        │   │  Layer D:       │  │  Layer E:        │    │
        │   │  Organizational │  │  Cross-repo /    │    │
        │   │  Probes         │  │  Operational     │    │
        │   │                 │  │  Probes          │    │
        │   │ - AGENTS.md     │  │ - Service mesh   │    │
        │   │ - Skills index  │  │ - Ownership      │    │
        │   │ - ADRs          │  │ - Deployment     │    │
        │   │ - Policy refs   │  │   manifests      │    │
        │   │ - Org rules     │  │ - SLOs/runbooks  │    │
        │   └─────────────────┘  └──────────────────┘    │
        │            │                   │                │
        └────────────┴─────────┬─────────┴────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │  RepoContext Merger  │
                    │  + JSON-Schema       │
                    │  validator           │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Persistent Cache    │
                    │  (content-addressed) │
                    │  + Postgres index    │
                    └──────────┬───────────┘
                               │
                               ▼
                       RepoContext artifact
                       (consumed by Planning)
```

Each Probe declares its inputs (which files it reads, which tools it shells out to), its outputs (the schema slice it owns), and its skip conditions (the `NodeProbe` skips if no `package.json` exists). The coordinator runs Probes in parallel up to a concurrency budget, with per-Probe timeout and failure isolation — a single failed Probe degrades the context but doesn't kill the gather.

---

## Probe inventory across the five layers

### Layer A: Repo Map Probes (cheap, fast, run on every task)

These run on every gather regardless of task type. They use tree-sitter and lightweight parsers, never the LLM, and complete in seconds.

**LanguageDetectionProbe.** Scans for marker files (`pom.xml`, `go.mod`, `package.json`, `requirements.txt`, `Cargo.toml`, `Gemfile`, `composer.json`, `pyproject.toml`, `*.csproj`) and tree-sitter grammars matching file extensions. Outputs primary language plus secondary languages (most repos have at least three: a primary, plus shell/Dockerfile/YAML). Detects mono-repo vs single-app via workspace files (`pnpm-workspace.yaml`, Lerna, `go.work`, Maven `<modules>`, Cargo workspaces, Bazel `WORKSPACE`, Nx, Turborepo).

**BuildSystemProbe.** Identifies the build tool and extracts build commands. This is the probe that makes the system language-agnostic — instead of hardcoding "run `mvn package` for Java," the probe reads the actual repo and emits the actual build command. The matrix is large but bounded:

| Language | Common build tools the probe handles |
|---|---|
| Java/Kotlin | Maven, Gradle, sbt, Bazel |
| Python | pip + setup.py, Poetry, pdm, uv, Hatch, Pants |
| JavaScript/TypeScript | npm, pnpm, yarn, Bun, Turborepo, Nx |
| Go | go modules, Bazel |
| Rust | Cargo, Bazel |
| C/C++ | CMake, Make, Bazel, Meson, Ninja |
| C#/.NET | dotnet CLI, MSBuild |
| Ruby | Bundler, Rake |
| PHP | Composer |
| Swift | SwiftPM, Bazel |

The probe extracts: build command, test command, lint command, output artifact paths, and the package manifest contents (parsed structurally, not as text).

**ManifestProbe.** Parses package manifests structurally and extracts: declared dependencies with version constraints, dev/test/build dependencies separated, lockfile presence and integrity, declared engines/runtimes (Node version, Python version, JDK version), declared scripts.

**CIProbe.** Detects CI provider (GitHub Actions, Jenkins, GitLab CI, CircleCI, Buildkite, Drone, Tekton, Argo) and parses the pipeline definition. Extracts: build steps that produce containers, test commands, smoke-test commands, deployment hooks, secret references (without reading values), runner constraints. This is where the agent learns "this repo's CI builds the image with `docker build -t payments-service:test .` and runs smoke tests via `./scripts/smoke-test.sh`" — used by the Planning layer to compose the validation plan.

**DeploymentProbe.** Parses Kubernetes manifests, Helm charts, Kustomize overlays, ECS task definitions, Nomad jobs, docker-compose files, Pulumi/Terraform, CDK. Extracts: container image references and how they're set (literal tag, values.yaml, Helm value override, env interpolation), deployment health probes, resource constraints, securityContext, runAsUser, capabilities, mounted volumes, environment variables.

**TestInventoryProbe.** Locates test files and frameworks (JUnit, pytest, Go test, Jest, Vitest, RSpec, etc.), extracts test commands, identifies smoke-test scripts (any file matching `smoke*`, `e2e*`, `integration*` plus heuristics from the CI parser), and surfaces test coverage data if present (`coverage.xml`, `lcov.info`, `coverage.out`).

### Layer B: Semantic Index Probes (compiler-grade structure)

These produce the structural backbone — true cross-file find-references, not similarity matches. SCIP is the workhorse; LSP and CodeQL fill gaps.

**SCIPIndexProbe.** Triggers SCIP indexing if the repo's index is stale (older than the latest main-branch commit), otherwise reuses the cached index. Uses the right indexer per language: `scip-java`, `scip-typescript`, `scip-python`, `scip-go`, `scip-clang`, `scip-ruby`, `rust-analyzer scip`, `scip-dotnet`. Output: the SCIP index path. The Planning layer queries it via the SCIP MCP server.

**SymbolGraphProbe.** Queries the SCIP index to extract: exported symbols with signatures, public API surface, internal symbols not exported, inheritance/implements relationships. For library repos this is the contract surface other repos depend on. For app repos it's mostly informational, but matters for blast-radius queries.

**ImportGraphProbe.** Builds the file-level import graph from SCIP plus tree-sitter for files SCIP doesn't index. The Planning layer uses this for blast-radius queries — "if I change `Dockerfile` and the entrypoint signal handling shifts, which downstream services consuming this image's logs/metrics break?"

**CrossRepoCallerProbe.** For any symbol declared in this repo, queries the org-wide SCIP graph (assuming Sourcegraph or equivalent has indexed the rest of your codebase) to enumerate external callers. Critical for shared libraries and platform repos. Outputs counts plus a sample of caller files per external repo.

**SecurityIndexProbe (Phase 2).** Triggers CodeQL or Joern CPG generation on demand. Skipped for distroless tasks. For vulnerability work, exposes high-level queries (`track_taint`, `traverse_call_graph`, `find_sinks`) via MCP, never raw CPGQL.

Layer B is more expensive than Layer A — SCIP indexing for a million-line repo takes minutes. The system caches indexes content-addressed by the source-tree hash and reuses across tasks. Most gathers hit warm caches.

### Layer C: Runtime/Container Probes (the distroless core)

These are what make distroless migration tractable. Static analysis alone misses what containers actually load at runtime; this layer uses dynamic analysis to close the gap.

**DockerfileProbe.** Parses every Dockerfile in the repo (not just the root one — `Dockerfile.local`, `Dockerfile.test`, etc.) using a real Dockerfile parser, not regex. Extracts per file: every `FROM` and its base image, the stage graph (multi-stage relationships), every `RUN` command split into individual shell commands, every `COPY` with source/dest, `ENTRYPOINT`/`CMD`/`USER`/`WORKDIR`/`EXPOSE`/`HEALTHCHECK`, environment variables set, volumes declared, custom labels.

**SBOMProbe.** Builds the existing image, then runs Syft to enumerate every package the image contains, with versions, licenses, and source (apt, apk, pip wheel, npm, etc.). Persists the full SBOM. The Planning layer compares this to the post-migration SBOM; the Validation layer asserts no critical packages went missing.

**CVEProbe.** Runs Grype against the SBOM to enumerate known CVEs. Outputs counts by severity plus the top-N highest-severity CVEs. Phase 2 uses this as a Phase 1 check too — if migrating to distroless dropped the CVE count from 47 to 3, that's the headline evidence the PR cites.

**RuntimeTraceProbe.** *The probe that catches what static analysis can't.* Builds the existing image, runs it against the smoke-test command from `TestInventoryProbe`, and traces every syscall using `strace -f` or eBPF (`bpftrace`, `bcc`). Captures: every `openat` (which files does the container actually read?), every `execve` (which binaries does it spawn?), every `mmap` of a shared library (which `.so` files load via `dlopen`?), every connect/bind (which network endpoints does it touch?). This catches the killers — JNI native libraries, SSL CA cert reads from `/etc/ssl/certs`, `getent` calls hitting glibc NSS modules, shell-outs to `sh -c` for env interpolation. Without this probe, distroless migration breaks silently in production.

**CertificateProbe.** Specifically scans for custom CA certificate handling. Inspects the existing image for non-standard certs in `/etc/ssl/certs`, `/usr/local/share/ca-certificates`, `/etc/pki`, plus parses Dockerfile for `update-ca-certificates`, `cfssl`, custom cert COPY directives, and `JAVA_HOME/lib/security/cacerts` modifications. This is the single most common distroless-migration blocker — internal corporate CAs that need Incert.

**EntrypointProbe.** Parses the entrypoint and CMD into a structured shape: is it shell-form (`/bin/sh -c "..."`) or exec-form (`["java", "-jar", "app.jar"]`)? Does it invoke a script file? Does that script require bash features? Does it set up signal handlers, exec the real process, or fork? Distroless has no shell, so shell-form entrypoints break unless rewritten — this probe surfaces that risk to the Planner before execution begins.

### Layer D: Organizational Probes (the unique-to-your-company layer)

This is where arbitrary company specifics enter the system. The challenge is making it bounded and lazily-loaded so it doesn't blow up the agent's context. The pattern: **structured metadata at gather time, full content lazy-loaded by the agent through MCP**.

**RepoConfigProbe.** Reads `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` if present. Parses YAML frontmatter for declared repo properties (criticality tier, owning team, deployment environment, opt-in/opt-out flags). The body content is *not* loaded into the agent context here — only metadata about what's available. The agent loads the body via an MCP tool when relevant.

**SkillsIndexProbe.** Walks the central Skills directory and the repo-local `.codegenie/skills/` directory, reads each `SKILL.md`'s YAML frontmatter (`name`, `description`, `applies_to` task types and languages), and emits a manifest of available Skills with descriptions only. **Progressive disclosure:** descriptions cost dozens of tokens at startup; full Skill content only loads when the Planning layer decides to use that Skill. This is what makes the system scale to hundreds of company-specific Skills without context bloat.

A Skill's `applies_to` field is the matching key. Example:

```yaml
---
name: distroless-java-springboot-internal
description: |
  Internal Spring Boot distroless migration for services using
  the company's shared logging library (com.acme.logging) and
  the internal CA certificate bundle. Handles JMX exposure for
  the company's monitoring sidecar.
applies_to:
  task_types: [distroless_migration]
  languages: [java]
  frameworks: [spring-boot]
  conditions:
    - dependency_present: com.acme.logging
required_tools: [dfc, incert, syft, grype]
---
# Skill content (not loaded until invoked)
...
```

The probe outputs the manifest of Skills whose `applies_to` matches the current repo. The Planner chooses which to fully load. New company-specific Skills are added by dropping a directory into `skills/`, no code changes.

**ADRProbe.** Locates Architecture Decision Records — `docs/adr/`, `docs/architecture/`, `docs/decisions/`, README sections matching ADR patterns. Parses the title and status of each, emits a list of ADR titles and IDs. Full content lazy-loaded only if the Planner decides an ADR is relevant. ADRs are how organizations encode "we decided three years ago that all Java services must run on JRE 17, never JDK" — the kind of constraint that can't be inferred from the code but is mandatory for the agent to respect.

**PolicyProbe.** Reads policy-as-code repos (linked via convention or AGENTS.md `policy_repos:` field). Pulls the org's container policy, image registry allowlist, base-image approval list, mandatory PR labels, mandatory PR reviewers, branch protection rules. This is structured config, not free-form docs — it can be embedded directly in `RepoContext` because it's small and bounded.

**ConventionProbe.** Detects company-specific conventions by pattern-matching against the codebase. Examples: "all controllers in this org extend `BaseController` from `com.acme.web`", "all configuration is loaded via the `@AcmeConfig` annotation", "Dockerfiles must label `team=` and `service=`". Conventions are declared as rules in a central config file and matched at gather time — the probe doesn't infer conventions, it checks declared ones. Output: which conventions this repo follows, which it violates, which don't apply.

**ExceptionProbe.** Reads any waivers or exceptions registered for this repo — "this service is exempt from distroless migration until the JNI native lib is replaced," "this repo's CI runs on a custom self-hosted runner," "do not modify Dockerfile.legacy, it's used for the EOL'd customer." Exceptions are versioned and time-bounded. The Planner refuses to act on tasks that violate active exceptions.

The key design move in Layer D is **"declared, not inferred"**: organizational rules live in structured files (Skills with frontmatter, policy YAML, exception registry, ADR index) that the gatherer reads with deterministic parsers. The LLM never has to guess what your company's rules are. New rules are added by editing config, not by retraining or reprompting.

### Layer E: Cross-repo and Operational Probes

These are the highest-latency probes and run only when relevant. They tell the agent how this repo connects to the rest of the org's running systems.

**OwnershipProbe.** Resolves the owning team via `CODEOWNERS`, repo topics, internal service catalog (Backstage, Cortex, OpsLevel, custom catalog APIs). Outputs primary team, on-call rotation if discoverable, escalation contacts.

**ServiceTopologyProbe.** If the org runs a service mesh (Istio, Linkerd, Consul Connect) or has a service catalog, queries it for upstream and downstream services that this repo's deployed image talks to. Outputs the runtime call graph at the network level, complementing SCIP's static call graph.

**SLOProbe.** Locates SLO definitions (Sloth YAML, Pyrra, Datadog SLO configs, Grafana annotations) and runbook references. Tells the agent and reviewer "this service has a 99.95% availability SLO; a botched migration that breaks startup is a high-impact incident." Affects risk scoring.

**ProductionConfigProbe.** Reads non-secret production config (Helm values for prod environment, ConfigMaps, environment-specific overlays) to confirm what runtime parameters are set in production — JVM heap sizing, GC tuning, feature flags, JNI library paths. This is what catches the case where the dev image runs fine but the prod image fails because production sets `LD_LIBRARY_PATH` to a directory that doesn't exist in distroless.

Layer E is organization-dependent. Most companies don't have all of these systems. The probes skip cleanly when the underlying source isn't available; the gatherer doesn't fail.

---

## The RepoContext schema

Every Probe writes into a single typed schema. The schema is the contract between gatherer and Planner; changes to it are versioned. Here's the shape, abbreviated:

```yaml
schema_version: "1.3"
repo_id: org/payments-service
gathered_at: 2026-04-26T14:32:18Z
gather_duration_ms: 47291
gather_status: complete  # or partial, with probe_failures listed
probe_failures: []

# Layer A
language_stack:
  primary: java
  secondary: [shell, dockerfile, yaml]
  detected_files:
    java: 1247
    shell: 12
build_system:
  tool: maven
  version: "3.9.5"
  commands:
    build: "mvn -B clean package -DskipTests"
    test: "mvn -B test"
    lint: "mvn -B checkstyle:check"
  output_artifacts:
    - target/payments-service-0.4.2.jar
manifests:
  - path: pom.xml
    declared_runtime: { java: 17 }
    direct_dependencies: 47
    lockfile_present: false  # Maven uses dependencyManagement, no lockfile
ci:
  provider: jenkins
  pipeline_file: Jenkinsfile
  builds_image: true
  image_build_command: "docker build -t payments-service:${BUILD_NUMBER} ."
  smoke_test_command: "./scripts/smoke-test.sh"
deployment:
  type: helm
  chart_path: deploy/helm
  image_reference_path: "values.yaml#image.repository"
  health_probes:
    liveness: "/health"
    readiness: "/ready"
  run_as_user: 1000
  capabilities_dropped: [ALL]
test_inventory:
  unit_test_command: "mvn test"
  smoke_test_path: scripts/smoke-test.sh
  integration_test_path: src/test/java/integration
  coverage_data_present: true

# Layer B
semantic_index:
  scip_index_path: s3://scip-cache/org/payments-service/abc123.scip
  scip_indexer: scip-java
  symbol_count: 2847
  exported_symbols: 142
cross_repo:
  external_callers:
    - repo: org/payment-gateway
      caller_count: 8
    - repo: org/billing-service
      caller_count: 3

# Layer C
containerization:
  dockerfiles:
    - path: Dockerfile
      stages: 2
      base_images:
        - stage: build
          image: maven:3.9-eclipse-temurin-17
        - stage: runtime
          image: eclipse-temurin:17-jre
      entrypoint:
        form: exec
        command: ["java", "-jar", "/app/app.jar"]
      user: appuser
      shell_in_final_stage: false
sbom:
  artifact_uri: s3://sboms/org/payments-service/abc123/syft.json
  package_count: 247
  packages_by_source:
    apk: 78
    java-archive: 169
cve_scan:
  artifact_uri: s3://cve-scans/org/payments-service/abc123/grype.json
  total: 47
  by_severity: { critical: 0, high: 12, medium: 22, low: 13 }
runtime_trace:
  artifact_uri: s3://traces/org/payments-service/abc123/strace.log
  binaries_executed: ["java"]
  shared_libs_loaded: ["libjvm.so", "libnet.so", "libnio.so", "libsunec.so"]
  cert_paths_read: ["/etc/ssl/certs/ca-certificates.crt"]
  shell_invocations: 0
custom_certificates:
  detected: true
  paths: ["/usr/local/share/ca-certificates/acme-internal-ca.crt"]
  install_method: "COPY + update-ca-certificates"

# Layer D
organizational:
  agents_md_present: true
  agents_md_uri: repo://AGENTS.md
  available_skills:
    - name: distroless-java-springboot-internal
      description: "Internal Spring Boot distroless migration..."
      applies: true
      uri: skills://distroless-java-springboot-internal
    - name: distroless-java-generic
      description: "Generic Spring Boot distroless migration"
      applies: true
      uri: skills://distroless-java-generic
  adrs:
    - id: ADR-0014
      title: "Java services run JRE-only in production"
      status: accepted
      uri: repo://docs/adr/0014-jre-only.md
  policies:
    container:
      base_image_allowlist: ["cgr.dev/chainguard/*", "internal-registry.acme.com/*"]
      mandatory_labels: [team, service, version]
      run_as_root: forbidden
  conventions:
    followed: ["acme-logging-lib", "acme-config-annotation"]
    violated: []
  exceptions:
    active: []

# Layer E
ownership:
  team: payments-platform
  on_call: pagerduty://schedules/payments
  reviewers: ["@team-payments-platform"]
service_topology:
  upstream: ["payment-gateway", "billing-service"]
  downstream: ["postgres-payments", "kafka-events"]
slo:
  availability_target: 99.95
  runbook_uri: "https://runbooks.acme.com/payments-service"
production_config:
  jvm_opts: "-Xmx2g -XX:+UseG1GC"
  ld_library_path: null
  required_env_vars: [DB_HOST, KAFKA_BROKERS, OTEL_ENDPOINT]
```

The schema is enforced with JSON Schema validation; the Planner refuses to consume malformed `RepoContext`. New Probes add new top-level keys; existing keys are backwards-compatible.

---

## Caching, freshness, and incremental gathers

Gathering is expensive. Caching makes it tractable.

**Content-addressed caching.** Each Probe's output is keyed by a hash of its inputs — for `LanguageDetectionProbe` that's the file tree's Merkle hash; for `SBOMProbe` it's the built image digest; for `SCIPIndexProbe` it's the source tree hash. Identical inputs always produce identical outputs (Probes must be deterministic), so the cache is reusable across tasks and across repos when content matches. Cursor's published architecture shows this pattern hits >90% cache reuse in practice.

**Freshness model.** The coordinator runs in three modes. **Fresh-on-trigger** rebuilds Probes whose inputs changed since the last gather (the default for production runs). **Cached-only** reuses everything (used for replay, debugging, or when running multiple tasks against the same repo back-to-back). **Force-refresh** ignores cache (used when a Probe's logic itself has changed). The trigger source determines mode — a CVE-driven task wants fresh runtime context; a campaign task replaying previous logic wants cached.

**Incremental gathers.** Most production repos don't change the whole context between runs. If only `Dockerfile` changed since the last gather, only `DockerfileProbe`, `SBOMProbe`, `CVEProbe`, `RuntimeTraceProbe`, `EntrypointProbe`, and `CertificateProbe` need to rerun. The coordinator computes the file-change set against the cached gather and skips Probes whose declared inputs didn't change.

**Storage layout.** Hot index in Postgres (the `RepoContext` artifact and Probe metadata, queryable). Cold artifact storage in S3 or equivalent (SCIP indexes, SBOMs, CVE reports, strace logs — large blobs, content-addressed). Pre-rendered "agent views" in Redis for the slices the agent hits frequently — `available_skills`, `entrypoint`, `risk_flags` — keyed by repo so the MCP server serves them in milliseconds.

---

## Exposure to the agent: the MCP interface

The gatherer doesn't dump `RepoContext` into the agent's prompt. That would be exactly the kind of context bloat that destroys agent performance. Instead, the gatherer exposes typed query operations through an MCP server. The agent loads only what it needs, when it needs it.

```python
# Agent-facing tools, one MCP call each:

get_repo_summary(repo_id) -> RepoSummary
    # Compact (~500 tokens): language, build, current base image,
    # entrypoint, risk_flags, available skill names

get_dockerfile(repo_id, path?) -> DockerfileDetail
    # Full parsed Dockerfile structure for one file

get_runtime_requirements(repo_id) -> RuntimeRequirements
    # What the running container actually needs:
    # binaries, libs, certs, files, envs, ports

get_skill(skill_name) -> SkillContent
    # Full Skill content, lazy-loaded on first use

get_adr(adr_id) -> ADRContent
    # Full ADR content, lazy-loaded

get_blast_radius(repo_id, change_type) -> BlastRadius
    # For a proposed change type, what callers and
    # downstream services are affected

list_callers(symbol_fqn, depth=1) -> Callers
    # SCIP find-references with cross-repo expansion

get_policy(repo_id, policy_class) -> Policy
    # Container policy, base image allowlist, mandatory labels

get_validation_plan(repo_id, task_type) -> ValidationPlan
    # Composed from CI commands, smoke tests, available scanners
```

The Planner's first MCP call is always `get_repo_summary`. From there it calls additional tools as the plan develops. Most Planning runs touch 5–10 tools, totaling under 5,000 tokens of context — versus a naive "dump everything" approach that would push 100k+ tokens and degrade agent quality.

---

## Extensibility: how new languages, probes, and company rules slot in

The whole point of this design is that adding support for a new repo type is config plus a new Probe, never a refactor.

**A new language (Rust, say).** Add `RustProbe` extending `BuildSystemProbe` with Cargo parsing logic; ensure `scip-rust` (`rust-analyzer scip`) is wired into `SCIPIndexProbe`'s indexer-selection logic; write a `distroless-rust` Skill bundling the Cargo `--release --target x86_64-unknown-linux-musl` patterns and the `cgr.dev/chainguard/static` runtime image strategy. About a day of work.

**A new build system (Bazel for an existing language).** Add `BazelProbe` that detects `WORKSPACE`/`MODULE.bazel` and extracts targets; the existing language Probes degrade gracefully when their tool isn't the primary build system. Bazel-specific Skills handle the BUILD-file mutation patterns.

**A new package manager (uv replacing pip).** `ManifestProbe` adds `pyproject.toml` + `uv.lock` parsing alongside existing pip support. No other Probe changes.

**A new repo style (Bazel monorepo with multiple deployable services).** `LanguageDetectionProbe` already detects monorepos. The coordinator adds a per-target gather mode where each Bazel target produces its own `RepoContext` slice, and a top-level `MonorepoContext` aggregates them. The Planner targets a specific deployable, not the whole monorepo.

**A new company convention.** Drop a YAML rule into the central conventions repo (`acme-config-annotation: { detect: '@AcmeConfig' annotation present in any source file }`). `ConventionProbe` picks it up on next gather. No code change.

**A new Skill.** Drop a directory with `SKILL.md` into the Skills repo. `SkillsIndexProbe` discovers it. No code change.

**A new ADR pattern.** ADRs are already discovered by `ADRProbe` if they live in conventional paths. Non-conventional locations get added to the ADRProbe's path list — one config edit.

**A new external system (the company adopts a service catalog tool).** Write one new Probe in Layer E that queries it. Existing Probes are unaffected.

The Probe interface is minimal and stable:

```python
class Probe(ABC):
    name: str
    layer: Literal["A", "B", "C", "D", "E"]

    def applies(self, repo: RepoSnapshot) -> bool:
        """Skip-detection: should this Probe run for this repo?"""

    def declared_inputs(self) -> set[str]:
        """File globs / external resources this Probe reads.
        Used for incremental gather and cache keying."""

    def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        """Produce the schema slice this Probe owns."""
```

---

## What runs the gatherer

A simple, durable orchestrator. Temporal is a good fit because Probes are long-running, can fail and retry, and have natural fan-out/fan-in semantics. Each gather is one Temporal workflow; each Probe is an Activity. The workflow handles the cache-vs-rerun logic, parallel dispatch up to a per-repo concurrency budget, per-Probe timeouts, partial failure (degraded gathers are still useful), and the final merge + schema validation step.

Probes run inside the same microVM sandbox the executor uses later — same isolation, same network policy, same lack of production credentials. Some Probes (`SBOMProbe`, `RuntimeTraceProbe`) need to actually build and execute container images, so the sandbox needs Docker-in-Docker or equivalent (gVisor/Firecracker with nested virt). Layer A and B Probes don't need that and run in lighter sandboxes.

For a typical Java microservice, a cold gather (no cache) takes 3–6 minutes — dominated by SCIP indexing and the runtime trace step. A warm gather (most caches valid) takes 20–40 seconds. An incremental gather where only the Dockerfile changed takes under 10 seconds. These numbers are what make the gatherer viable as the front of every task — fast enough to run on every PR comment, every CVE drop, every nightly scan.

---

## Why this shape

Three properties make this design hold up.

**Determinism where determinism is possible.** Every Probe is deterministic: same inputs, same output. The LLM is not invoked anywhere in the gather. This means the `RepoContext` artifact is reproducible, cacheable, and auditable — three properties the rest of the system depends on. When a PR fails review and you need to know why the agent thought a particular runtime library was unnecessary, you can replay the gather and see exactly what `RuntimeTraceProbe` reported.

**Bounded scope per Probe.** Each Probe owns one schema slice and reads a declared set of inputs. Failure isolation falls out: a flaky `ServiceTopologyProbe` doesn't break the gather. Extensibility falls out: adding Rust support touches one Probe, not the whole system. Cacheability falls out: per-Probe caching keys on declared inputs means most gathers hit warm caches.

**Organizational uniqueness as data, not prompts.** The hardest part of any company-specific agent is encoding "the way we do things here" without retraining or massive prompts. The Skills + AGENTS.md + ADRs + Policy + Exceptions pattern moves all of that into structured data the gatherer reads with deterministic parsers. New rules are config edits. The agent never has to guess; it queries. This is what lets the same architecture serve a fintech with strict compliance ADRs, a healthcare company with HIPAA-driven exceptions, and a SaaS company with custom internal frameworks — without re-architecting per organization.

The gatherer is the foundation everything else stands on. Get this right and the Planner has truthful, structured context to write a Change Contract against. Get it wrong and no amount of validation downstream will save the system from making changes based on a hallucinated picture of the repo.
