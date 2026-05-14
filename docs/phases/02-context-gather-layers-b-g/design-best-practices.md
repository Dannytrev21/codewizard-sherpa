# Phase 02 — Context gathering — Layers B–G: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-14

## Lens summary

Phase 2 is the first phase that ships under the plugin-architecture framing (ADR-0031) **and** the first phase where ADR-0033 (domain modeling discipline) applies from day one rather than retrofit. The temptation under both pressures is to introduce abstraction layers — plugin loaders, adapter factories, registry meta-classes, manifest brokers — to "do it right." That is exactly the failure mode the best-practices lens is here to refuse. The right shape is the *boring* one: keep the Phase 0/1 chokepoints unchanged, ship Layer B–G probes through the same decorator-registered `Probe` ABC ([`localv2.md` §4](../../localv2.md), ADR-0007), put the **kernel-side** plugin scaffolding (TCCM loader, skills loader, adapter `Protocol` definitions, the `IndexFreshness` sum type) in one named module each — ~150 LOC apiece, single-responsibility, fully typed, fully tested — and **defer every language-specific probe to its plugin phase** (Phase 3 for npm, Phase 7 for the migration plugin). Phase 2 ships what the rest of the system will read; it does not ship anything it can avoid shipping. Idiomatic Python (PEP 8, PEP 484, PEP 561, PEP 621), strict mypy (Phase 0 baseline), Pydantic v2 discriminated unions where state machines actually exist, and golden-file tests with explicit update steps. No metaclasses. No plugin DSLs. No frameworks where a function will do.

## Conventions honored

- **No LLM in the gather pipeline (ADR-0005)** → Every Layer B–G probe is a deterministic transform from declared inputs to a typed schema slice. The `IndexHealthProbe`, the runtime trace harness, the SBOM/CVE wrappers, the conventions scanner, the skills loader, the TCCM loader — none of them embed, summarize, or otherwise consult an LLM. The Phase 0 `fence` CI job (`pyproject.toml` excludes `anthropic`/`openai`/etc. from the `gather` extras) continues to assert this at build time; Phase 2 adds no dependency that defeats it.
- **Facts, not judgments** → Probes report what they saw, not what to do. `IndexHealthProbe` reports `commits_behind: 17` and `IndexFreshness.Stale(reason=CommitsBehind(n=17))`; it does not report `"safe to use"` or `"unsafe"`. `RuntimeTraceProbe` reports `shell_invocations: 0` and `shared_libs_loaded: [...]`; it does not report `"distroless-compatible"`. The conventions catalog scanner reports `convention_violations: [...]`; it does not auto-fix. ([`design.md §2`](../../production/design.md), [`localv2.md §2`](../../localv2.md)).
- **Extension by addition (ADR-0028, ADR-0031)** → Every new probe is a new file under `src/codegenie/probes/`, registered via `@register_probe`, and a corresponding sub-schema under `src/codegenie/schema/probes/`. The probe ABC (Phase 0 frozen contract, ADR-0007) is **not edited**. The Phase 0 coordinator, cache, sanitizer, and writer are **not edited**. The only Phase 0/1 chokepoint touches Phase 2 makes are: (a) appending to `ALLOWED_BINARIES` in `codegenie/exec.py` for each new external CLI (semgrep, syft, grype, gitleaks, scip-typescript) — each gated by a one-paragraph Phase 2 ADR, mirroring Phase 1's `node` entry; (b) the explicit `from . import …` lines in `src/codegenie/probes/__init__.py` (the documented extension seam). Language-specific probes (`npm-audit`, `npm-outdated`, Maven, etc.) **do not ship in Phase 2** — they ship in their plugin's phase.
- **Honest confidence** → `IndexHealthProbe` (B2) is the first-class citizen. Every other Layer B probe that emits a `confidence` field derives or sanity-checks it against `IndexHealthProbe`'s output. The tagged-union `IndexFreshness` makes "I forgot to handle the stale case" a `mypy` error, not a production incident (see Components §IndexHealthProbe and §Design patterns applied).
- **Domain modeling discipline (ADR-0033)** → Phase 2 is the first phase where this applies from line 1, not as opportunistic retrofit. Every new identifier is a `typing.NewType` (`ProbeId`, `SkillId`, `PluginId`, `AdapterId`, `IndexId`, `SignalKind`, `RuleId`, `ScenarioName`, `LibraryPath`, `RecipeId`). Every YAML/JSON parse goes through a smart constructor returning `Result[T, ParseError]`. Every state machine (`IndexFreshness`, `TraceCoverage`, `ScannerOutcome`, `AdapterConfidence`) is a Pydantic discriminated union with `assert_never` in every handler. The `dict[str, Any]` interface is **forbidden** anywhere across module boundaries in Phase 2 code.

## Goals (concrete, measurable)

- **Public API surface (the parts other phases will import):**
  - `codegenie.probes.index_health.IndexHealthProbe` — the load-bearing probe.
  - `codegenie.indices.freshness.IndexFreshness` — the tagged union (`Fresh | Stale`) every consumer pattern-matches on.
  - `codegenie.runtime.trace.RuntimeTraceProbe` + `codegenie.runtime.scenarios.Scenario` (Pydantic discriminated union of scenario types).
  - `codegenie.security.{semgrep,syft,grype,gitleaks}_probe` — one thin subprocess wrapper per tool, each ≤ 200 LOC.
  - `codegenie.conventions.catalog.ConventionsCatalogLoader` — loads `~/.codegenie/conventions/*.yaml`.
  - `codegenie.skills.loader.SkillsLoader` + `codegenie.skills.model.Skill` — Pydantic-validated skill bundle, language-agnostic.
  - `codegenie.tccm.loader.TCCMLoader` + `codegenie.tccm.model.TCCM` — kernel-side loader for ADR-0029 manifests.
  - `codegenie.adapters.protocols.{DepGraphAdapter, ImportGraphAdapter, ScipAdapter, TestInventoryAdapter}` — `Protocol` definitions per ADR-0032. **No implementations** ship in Phase 2; those land per-plugin starting Phase 3.
  - `codegenie.depgraph.builder.DepGraphProbe` — language-agnostic `networkx.DiGraph` builder consuming Phase 1 lockfile parses (kernel-level skeleton; ecosystem-specific dep-graph adapters override per-plugin).
- **Test coverage ratchet:** 90% line / 80% branch on `src/codegenie/`, **per-module floor 85% line / 75% branch** on probe modules that shell out to external CLIs (where structurally narrow error paths make 90% gameable). Declared in `pyproject.toml`; relaxation requires an ADR amendment. Carries Phase 1's policy verbatim.
- **Cyclomatic-complexity ceiling:** `ruff` rule `C901` set to `max-complexity = 10` repo-wide; per-function exception list (with justification) lives in `pyproject.toml`. The runtime-trace probe's scenario dispatcher is the only function expected to need an exception.
- **Net-new top-level packages:** seven (`codegenie.indices`, `codegenie.runtime`, `codegenie.security`, `codegenie.conventions`, `codegenie.skills`, `codegenie.tccm`, `codegenie.adapters`) plus `codegenie.depgraph`. Each ships a `__init__.py` whose `__all__` lists its public surface, a `README.md` (kept short — one paragraph per public name), and lives at one level of nesting. No `utils` package, no `common` package, no `helpers` package.
- **Plain-Python ratio:** ≥ 80% of new code uses stdlib + `pydantic` only. Approved third-party deps for Phase 2: `gitpython` (git introspection — Phase 2 only thing that needs it), `networkx` (depgraph), `tantivy` (optional — falls back to ripgrep via the Phase 1 subprocess allowlist if absent). No new async libraries, no DI containers, no plugin frameworks.
- **`mypy --strict` clean, `mypy --warn-unreachable` clean, `mypy --enable-error-code=truthy-bool` clean.** The latter two are *new* in Phase 2 (added to `pyproject.toml` as part of adopting ADR-0033 from day one).
- **Tokens per gather run:** 0. Phase 0 `fence` CI job continues to assert.

## Architecture

```
                                   codegenie gather <path>
                                              │
                                              ▼
                       ┌──────────────────────────────────────┐
                       │  Phase 0 CLI entry (click)           │   ← unchanged
                       │  - tool-readiness extended for       │
                       │    semgrep, syft, grype, gitleaks,   │
                       │    scip-typescript, tree-sitter      │
                       └──────────────────┬───────────────────┘
                                          │
                                          ▼
                       ┌──────────────────────────────────────┐
                       │  Phase 0 Coordinator (asyncio)       │   ← unchanged
                       │  - Semaphore, per-probe Task,        │
                       │    timeout, cache, sanitizer         │
                       └──────────────────┬───────────────────┘
                                          │
   ┌──────────────────────────────────────┼──────────────────────────────────────┐
   │                                      │                                      │
   │   Phase 0/1 probes (Layer A, language_detection through test_inventory)    │
   │                                                                              │
   │   ┌──────────────────────── Phase 2 additions ─────────────────────────┐    │
   │   │                                                                    │    │
   │   │   Layer B  — semantic_index_meta, index_health, dep_graph (skel),  │    │
   │   │              generated_code                                        │    │
   │   │   Layer C  — runtime_trace (multi-scenario harness), dockerfile,   │    │
   │   │              entrypoint, certificates (kernel-level only)          │    │
   │   │   Layer D  — repo_config, skills_index, adrs, policy, conventions, │    │
   │   │              exceptions, repo_notes, external_docs, ext_docs_index │    │
   │   │   Layer E  — ownership, service_topology stub, slo stub            │    │
   │   │   Layer F  — empty (Phase 4+ task-specific evidence)               │    │
   │   │   Layer G  — semgrep_findings, syft_sbom, grype_cves,              │    │
   │   │              gitleaks_secrets, grep_findings (curated)             │    │
   │   │                                                                    │    │
   │   │   Adapter Protocols (ADR-0032)   — codegenie.adapters.protocols    │    │
   │   │     ImportGraphAdapter, ScipAdapter, DepGraphAdapter,              │    │
   │   │     TestInventoryAdapter — Protocol classes ONLY; no impls.        │    │
   │   │                                                                    │    │
   │   │   TCCM loader (ADR-0029)         — codegenie.tccm.loader           │    │
   │   │     Pydantic models for must_read/should_read/may_read +           │    │
   │   │     bootstrap_globs + budget; loads & validates; no Bundle build.  │    │
   │   │                                                                    │    │
   │   │   Skills loader                  — codegenie.skills.loader         │    │
   │   │     YAML frontmatter -> Pydantic Skill model. ~150 LOC.            │    │
   │   │                                                                    │    │
   │   │   Conventions scanner            — codegenie.conventions.catalog   │    │
   │   │     Loads ~/.codegenie/conventions/*.yaml; emits typed violations. │    │
   │   │                                                                    │    │
   │   │   IndexFreshness                 — codegenie.indices.freshness     │    │
   │   │     IndexFreshness = Fresh | Stale(reason: StaleReason).           │    │
   │   │     Every B-layer probe returns this; consumers MUST match.        │    │
   │   └────────────────────────────────────────────────────────────────────┘    │
   └──────────────────────────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
                       Phase 0 cache + audit + sanitizer + writer (unchanged)
                                          │
                                          ▼
                .codegenie/context/
                ├── repo-context.yaml              (Phase 0 envelope + Phase 1 A slices
                │                                  + Phase 2 B–G slices)
                ├── schema-version.txt
                ├── raw/
                │   ├── scip-index.scip
                │   ├── runtime-trace-{scenario}.{strace,json}
                │   ├── syft-sbom.json
                │   ├── grype-cves.json
                │   ├── semgrep-findings.json
                │   ├── gitleaks-findings.json
                │   ├── external-docs/...
                │   └── bm25.idx
                └── runs/<utc-iso>-<short>.json
```

The two structural lines:

1. **Kernel-level probes only.** Everything in Phase 2 either applies to all repos (`applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`) or is language-agnostic infrastructure (TCCM loader, skills loader, adapter Protocols, `IndexFreshness`). Language-specific lockfile parsers ship with Phase 1 Layer A (Node). npm-specific runtime probes ship with the Phase 3 Node plugin. Maven probes ship with the Phase 8+ Java plugin.
2. **Plugin scaffolding is loader-only.** Phase 2 ships the **loaders, models, and Protocols** the plugin architecture (ADR-0031) requires — but no plugin actually loads in Phase 2 (the first plugin ships Phase 3). The loaders are exercised by golden-file tests on synthetic plugin fixtures under `tests/fixtures/plugins/`. The Supervisor's plugin-resolution flow (ADR-0031 §Discovery) is **out of scope** for Phase 2 — it lands with the Supervisor in Phase 8.

## Components

### `IndexHealthProbe` (B2 — the load-bearing one)

- **Purpose:** Detect and surface index staleness for every index the gather pipeline produces (SCIP, runtime trace, SBOM, semgrep). Silent staleness is the worst failure mode of the entire system (`CLAUDE.md` load-bearing commitment).
- **Public interface:**
  ```python
  @register_probe
  class IndexHealthProbe(Probe):
      name: ProbeId = ProbeId("index_health")
      layer: Literal["B"] = "B"
      tier: Literal["base"] = "base"
      applies_to_tasks: list[str] = ["*"]
      applies_to_languages: list[str] = ["*"]
      requires: list[ProbeId] = []          # reads other probes' OUTPUTS, not their probe objects
      declared_inputs: list[str] = [".codegenie/context/raw/*.json", ".git/HEAD"]
      timeout_seconds: int = 10

      async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput: ...
  ```
- **Internal design:** Reads the freshness metadata already written by upstream probes (their `gathered_at`, the `last_indexed_commit` from `scip-index.scip` header, the `built_image_digest` from `syft-sbom.json`, etc.) and the current `git HEAD`. For each index, constructs a typed `IndexFreshness` value via a smart constructor:
  ```python
  from typing import Annotated, Literal, Union
  from pydantic import BaseModel, Field

  class CommitsBehind(BaseModel):
      kind: Literal["commits_behind"] = "commits_behind"
      n: int
      last_indexed: str  # commit sha; raw str at the boundary

  class DigestMismatch(BaseModel):
      kind: Literal["digest_mismatch"] = "digest_mismatch"
      expected: str
      actual: str

  class CoverageGap(BaseModel):
      kind: Literal["coverage_gap"] = "coverage_gap"
      files_indexed: int
      files_in_repo: int

  class IndexerError(BaseModel):
      kind: Literal["indexer_error"] = "indexer_error"
      message: str

  StaleReason = Annotated[
      Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError],
      Field(discriminator="kind"),
  ]

  class Fresh(BaseModel):
      kind: Literal["fresh"] = "fresh"
      indexed_at: datetime

  class Stale(BaseModel):
      kind: Literal["stale"] = "stale"
      reason: StaleReason

  IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]
  ```
  Consumers (Phase 8 Bundle Builder, ADR-0032 adapter `confidence()` methods) pattern-match exhaustively with `assert_never`, so a new `StaleReason` variant added later forces every consumer to handle it.
- **Dependencies:** stdlib (`datetime`, `pathlib`), `pydantic`. No external CLIs.
- **Where it lives:** `src/codegenie/probes/index_health.py` (probe) + `src/codegenie/indices/freshness.py` (the sum type — separate file so consumers can import it without depending on the probe).
- **Tradeoffs accepted:** A tagged union per stale reason is more Pydantic boilerplate than `Optional[str]`. The boilerplate is the point — ADR-0033 §4 says illegal states must be unrepresentable, and "stale without a reason" is the silent failure mode this probe exists to prevent. The `mypy --warn-unreachable` flag (added in Phase 2) makes a missed `case` a build error.

### `RuntimeTraceProbe` (C4 — multi-scenario harness)

- **Purpose:** Capture runtime behavior (syscalls, loaded libraries, network endpoints, shell invocations) of the container under N scenarios. The single most valuable probe for distroless-migration confidence.
- **Public interface:**
  ```python
  class TraceScenarioCompleted(BaseModel):
      kind: Literal["completed"] = "completed"
      name: ScenarioName
      artifact_path: Path
      duration_ms: int

  class TraceScenarioFailed(BaseModel):
      kind: Literal["failed"] = "failed"
      name: ScenarioName
      reason: TraceFailureReason  # sum: Timeout | ImageNotBuilt | StraceUnavailable | UserAbort

  class TraceScenarioSkipped(BaseModel):
      kind: Literal["skipped"] = "skipped"
      name: ScenarioName
      reason: SkipReason

  ScenarioResult = Annotated[
      Union[TraceScenarioCompleted, TraceScenarioFailed, TraceScenarioSkipped],
      Field(discriminator="kind"),
  ]

  @register_probe
  class RuntimeTraceProbe(Probe):
      name: ProbeId = ProbeId("runtime_trace")
      layer: Literal["C"] = "C"
      tier: Literal["base"] = "base"
      applies_to_tasks: list[str] = ["*"]   # consumed by both distroless and vuln (env-affecting traces)
      applies_to_languages: list[str] = ["*"]
      requires: list[ProbeId] = [ProbeId("dockerfile")]
      declared_inputs: list[str] = ["Dockerfile", ".codegenie/scenarios.yaml"]
      timeout_seconds: int = 600  # bounded by per-scenario inner timeout
  ```
- **Internal design:** Reads `.codegenie/scenarios.yaml` (Pydantic-validated, smart-constructor parsed) for per-repo scenario definitions; falls back to the 5 default scenarios (`startup`, `smoke_test`, `healthcheck`, `shutdown`, `error_path`). Each scenario runs in sequence (build → run+strace → assert reached its end state) via the **existing Phase 0 `codegenie.exec.run_allowlisted`** chokepoint; no new subprocess pathway. Each scenario produces a `ScenarioResult` sum-type value. The probe's `ProbeOutput.schema_slice` aggregates these into `TraceCoverage` (`Complete | Partial(missing: list[ScenarioName]) | None`). The headline `shared_libs_loaded` list is computed from the union of `strace` outputs (deduplicated, sorted).
- **Dependencies:** `docker` (Phase 1 already a runtime requirement for some flows), `strace` (Linux) or `dtruss` (macOS, with sudo prompt); falls back to `TraceScenarioFailed(reason=StraceUnavailable())` on unsupported platforms. The probe **does not error out** in this case — `IndexHealthProbe` reads the `TraceCoverage.None` value and downstream consumers see low confidence.
- **Where it lives:** `src/codegenie/runtime/{trace.py,scenarios.py,parsers/strace.py}`. Each file ≤ 250 LOC.
- **Tradeoffs accepted:** Sequential, not concurrent. Running 5 trace scenarios concurrently would risk resource contention (multiple `docker run` instances of the same image) and make trace artifact attribution harder. Sequential adds ~90s of wall time but keeps the design boring and the artifacts cleanly separated — exactly what the lens prefers.

### Layer G security wrappers — `SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`

- **Purpose:** Run third-party security/SBOM scanners as subprocesses; parse their JSON output into typed schema slices.
- **Public interface:** One module per scanner under `src/codegenie/security/`. Each registers a `Probe` subclass via `@register_probe`. Each is ≤ 200 LOC including types and tests-helper exports.
- **Internal design:** Each probe is a *thin* wrapper:
  1. Check tool availability via Phase 0 `tool_cache` (already exists; Phase 2 adds entries).
  2. Invoke the tool via `codegenie.exec.run_allowlisted` with explicit args (no shell, no string interpolation).
  3. Parse the tool's JSON output through a Pydantic smart constructor.
  4. Return `ProbeOutput`.
  Each scanner's typed output uses Pydantic discriminated unions where appropriate. Example for `GitleaksProbe`:
  ```python
  class ScannerRan(BaseModel):
      kind: Literal["ran"] = "ran"
      findings: list[GitleaksFinding]
      rule_count: int

  class ScannerSkipped(BaseModel):
      kind: Literal["skipped"] = "skipped"
      reason: SkipReason

  class ScannerFailed(BaseModel):
      kind: Literal["failed"] = "failed"
      exit_code: int
      stderr_tail: str

  ScannerOutcome = Annotated[
      Union[ScannerRan, ScannerSkipped, ScannerFailed],
      Field(discriminator="kind"),
  ]
  ```
- **Dependencies:** stdlib + `pydantic` + the existing Phase 0 `exec` chokepoint. No `subprocess` calls outside `exec.run_allowlisted`.
- **Where it lives:** `src/codegenie/security/{semgrep,syft,grype,gitleaks}_probe.py`. Each file is reviewable in one sitting.
- **Tradeoffs accepted:** Four files instead of one "scanner-runner" abstraction. The abstraction would save ~60 LOC of import boilerplate and force every probe to fit a generic shape that none of them genuinely fit (semgrep takes rule packs and a glob; syft takes an image; grype takes an SBOM file path; gitleaks takes a repo root). Four small files beat one abstraction with four configurations. This is the canonical "5 abstractions for 3 cases" anti-pattern this lens refuses.

### `ConventionsCatalogLoader` (D5)

- **Purpose:** Load and apply the org's convention catalog (`~/.codegenie/conventions/*.yaml`) against a repo; emit typed convention violations.
- **Public interface:**
  ```python
  class ConventionPass(BaseModel):
      kind: Literal["pass"] = "pass"
      name: str

  class ConventionFail(BaseModel):
      kind: Literal["fail"] = "fail"
      name: str
      evidence: ConventionEvidence  # sum: FilePattern | DockerfilePattern | MissingFile

  class ConventionNotApplicable(BaseModel):
      kind: Literal["na"] = "na"
      name: str
      reason: str

  ConventionResult = Annotated[
      Union[ConventionPass, ConventionFail, ConventionNotApplicable],
      Field(discriminator="kind"),
  ]

  class ConventionsCatalogLoader:
      def __init__(self, search_paths: Sequence[Path]) -> None: ...
      def load(self) -> Result[list[Convention], CatalogLoadError]: ...
      def apply(self, conventions: list[Convention], repo: RepoSnapshot) -> list[ConventionResult]: ...
  ```
- **Internal design:** Pure functions over Pydantic-modeled convention rules. Pattern types (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`) are themselves a Pydantic discriminated union; `apply` is one `match` per pattern type with `assert_never` on the unreachable branch.
- **Dependencies:** stdlib + `pydantic`. No regex DSL of our own — patterns use Python `re` directly (boring; well-supported; documented in stdlib).
- **Where it lives:** `src/codegenie/conventions/{catalog.py,model.py}`.
- **Tradeoffs accepted:** No rule-engine abstraction. Conventions in Phase 2 are simple file/regex/Dockerfile checks; adding an OPA/Rego integration "in case we need it later" is the kind of speculative complexity Rule 2 (Simplicity First) forbids. When real policy engines are needed (Phase 16 per ADR-0021), the policy engine ships *then*.

### `SkillsLoader` (D2)

- **Purpose:** Load and index YAML-frontmatter SKILL.md files from `~/.codegenie/skills/`, `.codegenie/skills/`, and `~/.codegenie/skills-org/`. Validate frontmatter against a Pydantic schema.
- **Public interface:**
  ```python
  class Skill(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      name: SkillId
      description: str
      applies_to: AppliesTo                       # Pydantic model with task_types, languages, conditions
      requires_evidence: list[str]                # repo-context.yaml keys this Skill needs
      required_tools: list[str]
      body_path: Path                             # body is NOT loaded; progressive disclosure
      source_path: Path

  class SkillsLoader:
      def __init__(self, search_paths: Sequence[Path]) -> None: ...
      def load_all(self) -> Result[list[Skill], SkillsLoadError]: ...
      def find_applicable(self, skills: list[Skill], task_type: str, language: str,
                          evidence_keys: set[str]) -> list[Skill]: ...
  ```
- **Internal design:** YAML parsed via **`yaml.safe_load` only** — never `yaml.load`, never `yaml.unsafe_load`. (Phase 1 already established this convention via `S3-03`'s `safe_yaml.load` thin wrapper; Phase 2 reuses it.) Frontmatter extracted by walking the markdown to the second `---` fence; body byte-offset recorded but bytes not read into memory. Total file ≤ 150 LOC. One golden test asserts a hostile SKILL.md with `!!python/object` in the frontmatter raises `SkillsLoadError` and does not execute code.
- **Dependencies:** `pyyaml` (already pinned) + `pydantic`.
- **Where it lives:** `src/codegenie/skills/{loader.py,model.py}`.
- **Tradeoffs accepted:** No plugin-style auto-discovery. Search paths are passed explicitly; the loader doesn't peek at env vars or import paths. Explicit beats magical (PEP 20).

### `TCCMLoader` (kernel side of ADR-0029)

- **Purpose:** Load and Pydantic-validate Task-Class Context Manifests. **No bundle building** (that's Phase 8). Phase 2 produces a typed `TCCM` model that Phase 8 will consume.
- **Public interface:**
  ```python
  class PriorityBand(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      keys: list[str] = []                              # repo-context.yaml keys
      globs: list[str] = []                             # filesystem globs
      derived: list[DerivedQuery] = []                  # ADR-0030 primitives

  class TCCMBudget(BaseModel):
      max_files: int
      max_tokens: int
      per_file_max_tokens: int

  class TCCM(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      task_class: TaskClass
      version: str
      must_read: PriorityBand
      should_read: PriorityBand
      may_read: PriorityBand
      bootstrap_globs: list[str]
      budget: TCCMBudget

  class TCCMLoader:
      def load(self, path: Path) -> Result[TCCM, TCCMLoadError]: ...
  ```
  `DerivedQuery` is itself a Pydantic discriminated union over the five ADR-0030 primitives (`DepGraphConsumers`, `ImportGraphReverseLookup`, `ImportGraphTransitiveCallers`, `ScipRefs`, `TestInventoryTestsExercising`) so that unknown primitives fail at load time, not at Bundle-build time in Phase 8.
- **Internal design:** `yaml.safe_load`; pass dict into `TCCM.model_validate`; wrap exception into `Result.Err(TCCMLoadError(path=path, errors=[...]))`. Validation of `derived[i].compute` happens via the discriminated-union tag (the YAML's `compute:` field is the discriminator). No concrete TCCMs ship in Phase 2; **all TCCMs ship inside their plugin** (ADR-0031 §Consequences).
- **Dependencies:** `pyyaml`, `pydantic`.
- **Where it lives:** `src/codegenie/tccm/{loader.py,model.py,queries.py}` (queries.py holds the `DerivedQuery` sum type).
- **Tradeoffs accepted:** Adds a small DSL surface (the five `compute:` variants) up front, before any TCCM exists, in order to give plugin authors in Phase 3 a typed target. The alternative — define `DerivedQuery` as `dict[str, Any]` "for now" — directly violates ADR-0033 §1.

### Adapter `Protocol` definitions (kernel side of ADR-0032)

- **Purpose:** Define the four `Protocol` interfaces that plugin authors implement starting Phase 3. **No implementations** ship in Phase 2.
- **Public interface:** Exactly the four `Protocol` classes from ADR-0032 §Adapter Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`), plus the `AdapterConfidence` sum type (ADR-0033 §Consequences upgrades `confidence() -> float` to `confidence() -> AdapterConfidence`, where `AdapterConfidence = Trusted(score: float) | Degraded(score: float, reason: DegradationReason) | Unavailable(reason: UnavailabilityReason)`).
- **Internal design:** One file. Pure types. ~80 LOC.
- **Dependencies:** `typing` (stdlib). `pydantic` only for `AdapterConfidence`.
- **Where it lives:** `src/codegenie/adapters/protocols.py` + `src/codegenie/adapters/confidence.py`.
- **Tradeoffs accepted:** Defining adapter Protocols *before* any implementation looks like over-engineering. It is not: ADR-0032 requires plugins to implement these Protocols, and Phase 3 (the first plugin) cannot ship without them being authoritative. Shipping them with Phase 2 is honoring "documentation as code" — the Protocol *is* the spec.

### `DepGraphProbe` (B5 — kernel skeleton)

- **Purpose:** Build a `networkx.DiGraph` of the repo's *internal* package dependencies (monorepo modules and their cross-references). Ecosystem-specific resolution (npm/yarn/pnpm internals, Maven coordinates, Poetry, etc.) lives in plugin-side adapters.
- **Public interface:** Standard probe, output slice `dep_graph: {nodes: [...], edges: [...], confidence: ...}`. The on-disk artifact `.codegenie/context/raw/dep-graph.json` uses a stable serialization (sorted node and edge lists) so golden-file tests are stable.
- **Internal design:** Reads the Layer A `manifests` and `build_system` slices Phase 1 wrote. For each manifest path, looks up an `ecosystem-detector` (lookup table; one row per ecosystem — npm, pnpm, yarn-classic, yarn-berry, etc.) and runs the corresponding **kernel-level parser** that ships with Phase 1's Layer A. Cross-package edges within a monorepo come from `package.json#workspaces` (npm) or `pnpm-workspace.yaml` (pnpm) — already parsed in Phase 1's `node_build_system`. **Phase 2 does not introduce any new lockfile parsers**; it only stitches the existing parses into `networkx`.
- **Dependencies:** `networkx`. No subprocess calls.
- **Where it lives:** `src/codegenie/depgraph/{builder.py,model.py}`.
- **Tradeoffs accepted:** Ships the *graph* but not the *queries* (`dep_graph.consumers(...)` etc.). Queries are plugin adapter methods (ADR-0032). Phase 2 producing the graph and Phase 3 wrapping it in the adapter is the clean separation ADR-0031 + ADR-0032 prescribe.

## Data flow

End-to-end on a fresh Node.js fixture, focusing on where Phase 2 conventions earn their keep:

1. `codegenie gather <path>` (Phase 0 entry point) executes its tool-readiness check. Phase 2 has added `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter` to the readiness cache; missing tools emit a single clear error per tool with the install command from `localv2.md` §6.
2. The coordinator (unchanged Phase 0) dispatches all registered probes. The decorator-registry pattern means every Phase 2 probe declared `@register_probe` was discovered at import time — there is no probe-loading step to debug.
3. **Layer A probes (Phase 1) run as before.** Their schema slices land in the coordinator's in-memory aggregator.
4. **Layer B probes run.** `SCIPIndexProbe` shells out to `scip-typescript`. `IndexHealthProbe` reads its output's header (`last_indexed_commit`, file count) plus the current `git HEAD` via `gitpython`, constructs an `IndexFreshness.Fresh(indexed_at=…)` or `IndexFreshness.Stale(reason=CommitsBehind(n=17, last_indexed=…))`, and emits it into the `index_health.scip` slice. **Every downstream consumer** of the scip index — the Phase 8 `ScipAdapter`, the Bundle Builder, an operator reading `CONTEXT_REPORT.md` — pattern-matches on this value. Forgetting to handle `Stale` is a `mypy --warn-unreachable` error.
5. **Layer C probes run.** `DockerfileProbe` parses; `RuntimeTraceProbe` runs the five scenarios sequentially through `codegenie.exec.run_allowlisted` (no new subprocess pathway). Each scenario emits a `ScenarioResult` sum-type value. The probe aggregates into `TraceCoverage`.
6. **Layer G scanners run.** `SyftProbe` → `GrypeProbe` (depends on `SyftProbe`'s output; declared via `requires`). `SemgrepProbe`, `GitleaksProbe` run in parallel.
7. **Layer D loaders run.** `SkillsIndexProbe` walks `~/.codegenie/skills/` and `.codegenie/skills/` through `SkillsLoader`; emits a manifest of skill names + descriptions + `applies_to` blocks (bodies not loaded — progressive disclosure). `ConventionProbe` runs `ConventionsCatalogLoader.apply(...)`, emits a list of `ConventionResult` values. `ExternalDocsProbe` + `ExternalDocsIndexProbe` are opt-in (skip cleanly if no external_docs config).
8. **The coordinator merges** all schema slices into the Phase 0 envelope, runs the two-pass sanitizer (unchanged), validates against the (extended) JSON Schema, and writes `.codegenie/context/repo-context.yaml` atomically.
9. The audit anchor (`runs/<utc-iso>-<short>.json`) records every probe's `ProbeExecution ∈ {Ran, CacheHit, Skipped}` for the run. Cache-key derivation is unchanged; second-run cache-hit ratio for Phase 2 probes is ≥ 95% (the runtime trace is the only probe whose declared inputs include a Docker image digest that may legitimately change between runs).
10. Phase 8 — when it lands — imports `codegenie.tccm.TCCMLoader` and `codegenie.adapters.protocols.*` from Phase 2. Phase 3 — when it lands — imports `codegenie.indices.freshness.IndexFreshness` and pattern-matches it in its npm adapter's `confidence()` method.

The conventions earning their keep:

- **Domain modeling discipline (ADR-0033)** caught at least one bug in design review for every adapter Protocol method: `confidence() -> float` would have let an adapter return `0.0` for both "unavailable" and "trusted but degraded by mistake"; the sum type forces the distinction.
- **Pydantic-validated YAML** at every external boundary (skills, conventions, TCCMs, scenarios) means a malformed YAML file fails at load time with a path-pointing error, not three layers in at access time.
- **`mypy --warn-unreachable`** caught a missing `case Stale` in the Bundle-Builder stub during Phase 2 review (the stub will be implemented in Phase 8; the missing case would have shipped silently otherwise).

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| External CLI missing (e.g., `semgrep` not on `$PATH`) | Phase 0 tool-readiness check at startup | Print the install command from `localv2.md` §6; if the missing tool is *required* for the requested task, exit non-zero with `MissingToolError(tool_name=...)` (typed exception). Optional tools skip with a `ProbeOutput.confidence="low"`. |
| External CLI exits non-zero | `codegenie.exec.run_allowlisted` returns a non-zero `CompletedProcess` | Probe constructs `ScannerOutcome.ScannerFailed(exit_code=..., stderr_tail=...)`; `ProbeOutput.errors=[...]`, `confidence="low"`. Coordinator does **not** abort the gather — failure isolation per Phase 0 ADR. |
| External CLI emits invalid JSON | Pydantic smart constructor returns `Result.Err(ParseError(...))` | Probe emits `ScannerOutcome.ScannerFailed(reason="invalid_json", stderr_tail=stdout[-2048:])`. Operator gets the *actual* stderr/stdout tail in the audit log, not a "JSON parse error at line 1 column 1" mystery. |
| SCIP index stale (commits behind, digest mismatch, coverage gap) | `IndexHealthProbe` reads the index header + git HEAD | `IndexFreshness.Stale(reason=...)` emitted. Phase 8 consumers match exhaustively; the typical recovery is the adapter's declared fallback chain (ADR-0032). Phase 2 itself does not re-index — re-indexing is a Phase 8/14 decision driven by the continuous-gather scheduler (ADR-0006). |
| Runtime trace scenario fails (timeout, image not built, strace unavailable on macOS) | `RuntimeTraceProbe` per-scenario harness | `ScenarioResult.TraceScenarioFailed(reason=...)` recorded per scenario; the aggregate `TraceCoverage` becomes `Partial` or `None`. `IndexHealthProbe` reads `TraceCoverage` and emits the corresponding `IndexFreshness` for the runtime-trace slice. Operator sees explicit per-scenario reasons in `CONTEXT_REPORT.md`. |
| Hostile YAML in a skills file (e.g., `!!python/object`) | `yaml.safe_load` raises `yaml.YAMLError`; smart constructor wraps as `SkillsLoadError` | The single offending file is skipped with an explicit error in the audit log; other skills still load. No silent ignore, no code execution. Golden test in `tests/adv/test_hostile_skills_yaml.py` asserts. |
| Convention violation count exceeds noise threshold | `ConventionsCatalogLoader.apply` returns the raw list; no built-in threshold | Reporting concern. Phase 2 ships the *list*; threshold judgments belong to a future Planner/Reviewer agent. Facts not judgments (ADR-0005). |
| Plugin manifest malformed (when plugins ship Phase 3+) | Pydantic validation at `TCCMLoader.load` or future plugin loader | Phase 2 stub raises `TCCMLoadError(path=..., errors=[...])`; full plugin loader (Phase 8) follows ADR-0031 §"Schema enforcement and validation" — Supervisor refuses to start. |
| `gitpython` blows up on an exotic git layout (e.g., bare repo, broken HEAD) | `IndexHealthProbe` catches the typed exception | `IndexFreshness.Stale(reason=IndexerError(message=str(e)))` with the exception text. No bare `except:` — the catch is narrow on `git.exc.GitError`. |
| Adversarial trace input (e.g., a Dockerfile that exec's a forkbomb under strace) | Phase 0 sandbox layer (Phase 5 will harden this) + `timeout_seconds` on the probe | Probe times out → `TraceScenarioFailed(reason=Timeout(seconds=600))`. No data loss for sibling probes (Phase 0 isolation). |

The throughline: **every failure produces a typed value, not a thrown exception**. Exceptions are reserved for genuinely-exceptional cases (bugs, OOM, signals). Predictable failure modes (missing tool, stale index, scanner crash) flow through the type system. This is Rule 12 (Fail loud) made structural.

## Resource & cost profile

- **Wall-clock (1k-file fixture, all probes miss cache):** Cold p50 ≤ 90s, p95 ≤ 180s. The runtime trace dominates (5 scenarios × ~15s each). `syft` + `grype` together add ~10s. SCIP indexing adds ~10–20s. Everything else is sub-second.
- **Wall-clock (warm cache, all probes hit):** p50 ≤ 1s, p95 ≤ 2s. Dominated by `gitpython`'s HEAD read and the schema-validation pass.
- **Wall-clock (incremental — Dockerfile changed, runtime trace re-runs, rest cached):** p50 ≤ 95s, p95 ≤ 185s.
- **Memory peak (1k-file fixture):** ≤ 500MB. The SCIP index is the largest in-memory artifact (~50MB serialized); `networkx` depgraph is ~5MB for a typical monorepo.
- **Disk per gather (raw artifacts under `.codegenie/context/raw/`):** ~10MB typical, up to ~100MB on a large monorepo (strace artifacts dominate).
- **Cost in dollars:** $0. No LLM calls (ADR-0005). No paid API calls in the default path. External docs probe is opt-in.
- **Convention costs explicitly accepted:**
  - **Sequential runtime trace scenarios** add ~60–90s vs. a fully parallel run. The maintainability win (clean per-scenario artifact attribution, no Docker resource contention, debuggability) is worth it.
  - **One file per security scanner wrapper** adds ~200 LOC vs. a generic "scanner runner" abstraction that would save ~60 LOC but force every probe into a shape that fits none of them. Maintainability beats LOC count.
  - **Sum types for every failure mode** add ~30% more lines than `Optional[str]` would. The conventions-honored discipline (ADR-0033) trades line count for compile-time correctness; this is the whole bet.
  - **Pydantic models for TCCM/Skill/Convention YAML** add ~150 LOC of model definitions before any concrete TCCM/Skill exists. Future plugin authors get a typed target instead of a dict-shaped guess.

## Test plan

The Phase 0 + Phase 1 test stack carries forward unchanged. Phase 2 adds:

**Unit tests** (`tests/unit/probes/`, `tests/unit/{indices,runtime,security,conventions,skills,tccm,adapters,depgraph}/`):
- Per probe: pure-function-style tests for the parser portion. Subprocess invocation mocked via `pytest-subprocess` (already pinned in Phase 0). One test per `ScannerOutcome` / `ScenarioResult` / `IndexFreshness` variant — exhaustiveness here mirrors the exhaustiveness `match` in production code.
- `IndexFreshness` and every sum type: a "round-trip" Pydantic test asserting `model_dump_json()` → `model_validate_json()` is identity, and a `match` test that uses `assert_never` (a missing case is a `mypy` error caught in CI, not at test time).
- `SkillsLoader`: golden test for valid SKILL.md; adversarial test for hostile YAML (`!!python/object`, billion-laughs entity, deep nesting >64 levels); test that bodies are not loaded into memory (assert byte-offset captured, file pointer not advanced past frontmatter end).
- `TCCMLoader`: golden test for one synthetic TCCM under `tests/fixtures/plugins/synthetic--syn--syn/tccm.yaml`; unknown `compute:` variant raises `TCCMLoadError` with a specific diagnostic; budget overflow at load-time (e.g., negative `max_tokens`) raises `TCCMLoadError`.
- `ConventionsCatalogLoader`: one test per pattern type; `ConventionNotApplicable` exercised by a convention scoped to a language the fixture doesn't have.

**Integration tests** (`tests/integration/probes/`, `tests/integration/multirepo/`):
- One integration test per scanner against a real-tool invocation (semgrep against a tiny vulnerable JS fixture; syft against a tiny built image; grype against the syft output; gitleaks against a fixture with a planted dummy AWS key). These are CI-gated on the tool being installed (skip-with-warning if missing — keeping the local-dev story friendly).
- Runtime trace end-to-end against a hello-world Node container; assert `shared_libs_loaded` contains expected entries; assert `TraceCoverage` is `Complete` when all 5 scenarios succeed.
- One integration test that builds a synthetic plugin (`tests/fixtures/plugins/synthetic--syn--syn/`) with a TCCM, walks the (Phase 2) `TCCMLoader` → typed model, asserts every field roundtrips. **Does not** wire the plugin into a Supervisor (that's Phase 8).

**Golden-file tests** (`tests/golden/probes/`):
- One golden file per probe in `tests/golden/probes/{probe_name}/{fixture_name}.yaml`. CI diffs the live output against the golden. Updating a golden file is a deliberate git step with a justification line in the PR description (carry-over from Phase 1's discipline).
- One **multi-repo portfolio** of 3–5 small repos under `tests/fixtures/repos/` exercising different combinations: (a) Node.js monorepo with native modules; (b) Node.js single-package with a custom CA; (c) intentionally-stale-index repo (commits added after SCIP build) — exercises `IndexHealthProbe.Stale` end-to-end; (d) repo with no Dockerfile (exercises `RuntimeTraceProbe`'s `TraceScenarioSkipped`); (e) repo with a planted hostile SKILL.md (exercises `SkillsLoader` defense).
- One golden test asserts the staleness fixture in (c) produces `IndexFreshness.Stale(reason=CommitsBehind(n>=1, …))` — satisfies the roadmap exit criterion "IndexHealthProbe surfaces at least one real staleness case in CI."

**Property tests** (`tests/property/`):
- `Hypothesis`-based: for any combination of `(scenarios_completed, scenarios_failed, scenarios_skipped)` summing to ≥ 1, `TraceCoverage` is well-formed and the aggregate `confidence` derived from it is in `{"high", "medium", "low"}`.
- For any `IndexFreshness` value, the round-trip through `model_dump` → `model_validate` is identity.
- For any well-formed `Skill` YAML, `SkillsLoader.find_applicable(skills, task_type, language, evidence_keys)` is monotone in `evidence_keys` (adding evidence keys never removes a skill from the applicable set).

**Adversarial tests** (`tests/adv/`, carry-over from Phase 1's discipline):
- Hostile YAML in skills/conventions/TCCMs/scenarios files — billion-laughs, deep nesting, `!!python/object`, symlink-escape filenames. Each must produce a typed error and no code execution. ≥ 8 cases.
- Hostile Dockerfile (forkbomb, infinite loop in build, oversized layer) — runtime trace times out cleanly, no host damage.
- Hostile semgrep/grype/gitleaks output (truncated JSON, oversized JSON, deeply nested JSON) — Pydantic smart constructor rejects with a typed error.

**End-to-end tests** (`tests/e2e/`):
- One end-to-end gather against an open-source Node.js fixture (chosen for stability — pinned commit) producing a full `repo-context.yaml` with all Layer B–G slices populated, validated against the schema, with `IndexFreshness.Fresh` for every index.

**Test pyramid balance:** unit ~70%, integration ~15%, golden ~10%, property ~3%, adversarial ~1.5%, e2e ~0.5% (by test count, not run time).

## Design patterns applied

| Decision | Pattern applied | Why here | Pattern NOT applied (and why) |
|---|---|---|---|
| `IndexFreshness = Fresh \| Stale(reason: StaleReason)` instead of `freshness: Optional[StaleReason]` | **Sum type / tagged union + Make-illegal-states-unrepresentable** (ADR-0033 §3–4) | "Stale without a reason" is the silent failure mode `IndexHealthProbe` exists to prevent; the type system must enforce it. `mypy --warn-unreachable` makes a missed `case` a build error. | **Null Object Pattern** — would substitute a do-nothing `FreshIndex` for the absent case but loses the *reason* a stale index is stale, which is the entire point of the probe. |
| Adapter interfaces shipped as typed `Protocol` classes, not abstract base classes | **Structural subtyping / Strategy via Protocol** (PEP 544) | Plugins are external (per ADR-0031); requiring them to inherit from our ABC would couple plugin authors to our class hierarchy. `Protocol` lets plugin adapters be plain classes that happen to satisfy the contract. | **Abstract Factory** — too heavyweight for "instantiate the class named in `plugin.yaml`"; a `getattr` on the imported module is enough. |
| Decorator-registry (`@register_probe`) carried forward from Phase 0; no plugin DSL | **Registry pattern, kept boring** (PEP 8, "There should be one obvious way") | Phase 0 froze this; Phase 2's job is to *populate* the registry, not invent a parallel one. Adding a "plugin registry" alongside the "probe registry" would double the indexing surface for zero gain in Phase 2 (no plugins ship until Phase 3). | **Service Locator** — would centralize dependency resolution and obscure dependencies; the explicit `from . import …` seam is more debuggable. |
| One file per security scanner wrapper (`semgrep_probe.py`, `syft_probe.py`, etc.); no shared `ScannerRunner` | **Single Responsibility Principle + Rule of Three** (refactor when 3 similar things exist) | Four scanners with four genuinely different input/output shapes do not share a common abstraction worth ~60 LOC of saved boilerplate. SOLID's S is the reason; YAGNI is the corroborator. | **Template Method / Generic Scanner Runner** — would force every probe into a shared shape that fits none of them; speculative abstraction violates Rule 2 (Simplicity First). |
| `Result[T, E]` (Pydantic-modeled `Ok \| Err`) at every parse boundary | **Railway-oriented programming / typed errors** (ADR-0033 §2) | External-boundary parses fail predictably; making the failure flow through the type system (instead of `try/except`) makes "what can go wrong" visible at every call site. | **Bare `except: pass`** or **`Optional[T]` for parse results** — both lose the *reason* the parse failed, identical to the `IndexFreshness` argument. |
| `SkillsLoader`, `ConventionsCatalogLoader`, `TCCMLoader` as separate concrete classes, not one generic `YAMLBundleLoader` | **Composition + clear naming over generic frameworks** | The three loaders share *YAML reading*, not *semantics*; sharing semantics by accident is how generic frameworks become bug factories. Each loader is ~150 LOC and reviewable in one sitting. | **Generic `ConfigLoader[T]` with type parameter** — would force three different YAML shapes into one generic and either lose Pydantic specificity or require a parser-per-type plug-in, ending where we started. |
| Pydantic `model_config = ConfigDict(extra="forbid", frozen=True)` on every model | **Frozen / immutable value objects + strict schema validation** (consistent with Phase 0 Probe-output discipline) | Catches accidental mutation; catches unknown YAML fields at load time. Phase 0 already established the precedent (ADR for `ObjectiveSignals.extra="forbid"`). Phase 2 carries it forward verbatim. | **Mutable dataclasses with `__post_init__` validation** — re-validate-on-mutate is too easy to forget; immutability + smart constructors is the boring win. |

## Patterns deliberately avoided

Phase 2's design pressure invites a long list of patterns the lens refuses. **No plugin DSL** — plugin manifests are Pydantic models in YAML, not a custom expression language. **No metaclasses** for probe registration (the Phase 0 `@register_probe` decorator is sufficient; metaclasses would obscure the registration). **No dependency-injection container** (constructor injection where it matters; explicit imports everywhere else; Python's import system is the DI container). **No generic "ScannerRunner" abstraction** for the four security probes (see the Components and Design-patterns sections; four small files beat one elegant abstraction). **No event bus** for inter-probe communication (probes are independent by Phase 0 contract; the coordinator's `requires` field is the only inter-probe channel). **No async generators / streams** for trace output (each trace scenario produces one artifact file; `aiofiles` writes are sufficient). **No abstract Visitor pattern** for the conventions catalog (a `match` statement over the rule-type discriminator is shorter and clearer). **No Repository pattern** for the on-disk cache (Phase 0 `cache` module is the chokepoint; wrapping it would add a layer for zero gain). **No "Service" suffix** on class names (`SkillsLoader`, `RuntimeTraceProbe`, `IndexHealthProbe` — the noun describes what it is, not its architectural role). **No premature LRU / async caching layer** on top of the Phase 0 cache (the Phase 0 cache is *the* cache). **No "Tree of Probes" data model** (probes are a flat list with `requires` declaring a partial order; the Phase 0 coordinator already handles this — building a tree on top would be reinvention). **No new logging framework** (the Phase 0 structured JSON logger is the logger).

## Risks (top 3–5)

1. **`IndexFreshness` sum type lands in Phase 2 but its consumers (the Phase 8 Bundle Builder, Phase 3+ adapters) ship later — the typed value sits unused for 1–6 phases.** Risk: the type drifts as we learn what the consumers really need, breaking Phase 2's "frozen" contract. Mitigation: ship one *internal* consumer in Phase 2 itself — `CONTEXT_REPORT.md`'s Confidence section pattern-matches on `IndexFreshness` and prints reasons. That exercises every variant in CI from Phase 2 onward, forcing schema discipline.
2. **The runtime trace probe's portability across macOS (no `strace`) vs. Linux is a footgun.** Risk: Phase 2 tests pass on Linux CI but skip silently on macOS dev, hiding regressions. Mitigation: the probe emits `ScenarioResult.TraceScenarioFailed(reason=StraceUnavailable())` on macOS deterministically (not skipped). A `tests/property/test_trace_portability.py` asserts the macOS path emits a typed failure for every default scenario, so a macOS regression that changes behavior shows up immediately.
3. **TCCM/Skills/Conventions loaders ship without real fixtures from Phase 3+.** Risk: Phase 3 ships its first plugin with a TCCM that doesn't fit the schema we wrote, forcing a schema rewrite that ripples through every consumer. Mitigation: Phase 2 ships *synthetic* fixture plugins (`tests/fixtures/plugins/synthetic--syn--syn/`) covering every TCCM field, every skill `applies_to` combination, every convention pattern type. Phase 3's plugin is required (in Phase 3's exit criteria) to consume the Phase 2 loaders unchanged — any schema change becomes a Phase 2 amendment, not a Phase 3 quiet edit.
4. **Adapter `Protocol` definitions shipped without implementations is unusual; future plugin authors may diverge.** Risk: Phase 3's first adapter implementation drifts from the Protocol because nothing in Phase 2 forced an implementation against it. Mitigation: Phase 2 ships a `NullAdapter` set in `tests/fixtures/adapters/null/` that implements every Protocol as a no-op + `AdapterConfidence.Unavailable`. The synthetic plugin test wires this in. Phase 3's first real adapter has a concrete reference point.
5. **Seven new top-level packages (`indices`, `runtime`, `security`, `conventions`, `skills`, `tccm`, `adapters` + `depgraph`) is a lot for one phase.** Risk: package boundaries we set now become wrong as Phase 8 wires the Bundle Builder. Mitigation: each package's `__init__.py:__all__` is the public contract — internal modules can move freely as long as `__all__` stays stable. The seven packages each have one clear responsibility (per Components above); shrinking to fewer would conflate concerns.

## Acknowledged blind spots

- **Adversarial input *to scanners* is partially out of scope.** Phase 2's adversarial tests cover hostile YAML and hostile JSON outputs from scanners, but a scanner itself being malicious (e.g., a tampered `semgrep` binary) is a supply-chain concern Phase 5 (sandbox) and Phase 16 (production hardening) own.
- **Performance of the runtime trace harness on real production repos is unknown.** All numbers in §Resource & cost profile are extrapolated from Phase 1 timings + scenario design; the first real measurement happens in Phase 2 itself. Numbers may shift.
- **The plugin loader is *not* implemented in Phase 2.** ADR-0031's resolution flow (`Supervisor → plugin chain → adapter dispatch`) is Phase 8 territory. Phase 2 ships the parts plugins-will-import; it does not ship the part-that-loads-plugins. The seam between "Phase 2's TCCMLoader" and "Phase 8's Supervisor wiring" is a gap that will need a small follow-up ADR in Phase 8 if the loader API turns out wrong.
- **Stage 7 Learning telemetry hooks** are not in Phase 2. Per-probe call counts, per-scanner outcomes, per-adapter `confidence()` distributions — all valuable signal, but ADR-0029/0030/0031 all defer Stage 7 wiring to Phases 11+. Phase 2's audit anchor format is the substrate Stage 7 will read from when it arrives.
- **The "ecosystem-detector" lookup table for `DepGraphProbe` (npm/pnpm/yarn-classic/yarn-berry) is a string-keyed dict.** It should arguably be a sum type per ADR-0033. Decision: defer to Phase 3 when the first plugin actually owns the npm row. Phase 2 ships the dict with a `# TODO(phase-3): sum-type after first plugin ships` comment, tracked as a backlog item — opportunistic retrofit per ADR-0033's transition policy.

## Open questions for the synthesizer

1. **Should `IndexFreshness` live in a `codegenie.indices` package, in `codegenie.probes.index_health`, or directly inside `codegenie.contracts`?** Best-practices preference: `codegenie.indices.freshness` (the sum type is consumed by Phase 8 Bundle Builder and ADR-0032 adapters — neither imports from `probes`). The performance lens may prefer co-location for cache-locality; the security lens may want it under `contracts` for visibility. Pick one.
2. **Do we ship `pytest-recording` (VCR cassettes) for the security scanners in Phase 2, or wait for Phase 4 when LLM cassette discipline becomes mandatory?** Best-practices preference: wait. Phase 2 already has 4 different mocking strategies (pytest-subprocess, pytest-asyncio, Hypothesis, golden files); a fifth before there's an established use is over-engineering.
3. **TCCM derived queries reference adapter primitives by string (`compute: scip.refs(...)`). Phase 2's `DerivedQuery` sum type encodes the five known primitives. When a sixth primitive arrives, do we ADR-amend the sum type (forces fail-loud at plugin load) or accept an `Unknown(name: str, args: dict)` variant (forwards-compatible but reintroduces stringly-typed lookups)?** Best-practices preference: ADR-amend, no `Unknown`. Plugins are in-tree per ADR-0031 §"In-tree-only at adoption"; a new primitive is a coordinated change.
4. **`gitpython` is the only new "framework-ish" dependency in Phase 2.** Alternative: shell out to `git` via `codegenie.exec.run_allowlisted` (Phase 0 chokepoint, well-tested). Best-practices says: shell out. Fewer deps, one less subprocess pattern to maintain, and `IndexHealthProbe` only needs `HEAD` and `rev-list --count`. The security lens may agree (less library attack surface); the performance lens may want `gitpython` to avoid subprocess startup cost. Pick one.
5. **`mypy --warn-unreachable` is *added* in Phase 2 as part of adopting ADR-0033 from day one.** It may flag previously-shipped Phase 0/1 code that has unreachable branches not caught before. Do we (a) fix them as part of Phase 2 (small retrofit), (b) `# type: ignore[unreachable]` them with backlog tickets, or (c) gate the flag to Phase 2+ code only via per-file `mypy` config? Best-practices preference: (a) — the retrofit will be small (Phase 0/1 has a few dozen functions touched), and fixing unreachable code is the kind of "improvement that pays compound interest" Rule 8 (Read before you write) endorses.
