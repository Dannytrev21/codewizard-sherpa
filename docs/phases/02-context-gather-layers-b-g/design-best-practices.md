# Phase 2 — Context gathering — Layers B–G: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 0 built the spine (Probe ABC, async coordinator, content-addressed cache, JSON Schema validator, two-pass sanitizer, subprocess allowlist, audit anchor). Phase 1 populated Layer A through the *frozen* spine — five new probes, two new catalogs, three ADR-gated edits, zero structural changes to Phase 0 chokepoints. **Phase 2's job is to do exactly the same trick, three times wider, against tools that are far less polite than `json.loads`.**

The lens is "idiomatic Python for a small team over many years." Concretely:

- Every external CLI (`semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter` parsers) lives behind a **thin wrapper module** that returns a **Pydantic model**. Probes consume models, not subprocess stdout. The wrapper is the only place that knows about JSON shapes, exit codes, or `stderr` quirks. That boundary is where the rest of the codebase stops getting weirder when a tool changes its output schema.
- Layer B–G probes are added by **dropping new files under existing `src/codegenie/probes/` per-layer subpackages**, each with one `@register_probe`-decorated class. The Phase 1 registry import seam (`src/codegenie/probes/__init__.py`) is the *only* file edited to wire them in.
- **`IndexHealthProbe` (B2) is a normal probe** that reads other probes' confidence fields and emits its own structured slice. The "outsized importance" lives in **observability and CI surface area**, not in code asymmetry. Bespoke importance markers in code is exactly the smell Rule 11 warns about.
- **Golden-file tests** are a bytes-on-disk diff helper (~80 lines, pytest-native), not a plugin. The fewer moving parts the better.
- The **Skills loader** and **conventions catalog** are YAML-with-frontmatter, parsed via Phase 1's `safe_yaml`, validated against a JSON Schema, indexed by `applies_to_tasks` × `applies_to_languages`. Same shape as Phase 1's `native_modules.yaml` / `ci_providers.yaml`.

What I deprioritize, explicitly:

- **Raw throughput.** I will not co-locate parsing in subprocess pools or fork-juggle for a 200 ms gain on a probe that runs once every 90 seconds. Phase 14 reopens this.
- **Adversarial perfection.** Phase 1's in-process caps + `O_NOFOLLOW` + sanitizer are inherited and applied to every new parser; I will not add a per-probe sandbox layer that Phase 0 never sanctioned.
- **Forward compatibility with un-designed phases.** No `views.json`, no MCP shim, no streaming writer in Phase 2. Phase 8 designs Phase 8.

---

## Conventions honored

- **No LLM in the gather pipeline** ([ADR-0005](../../production/adrs/0005-no-llm-in-gather-pipeline.md)) → All Phase 2 probes parse deterministic CLI output. `tree-sitter` and `ast-grep` produce ASTs, not summaries. BM25 over external docs is `tantivy`, no embedder. The Phase 0 `fence` CI job is extended with the new dependency closure: no `anthropic`, `openai`, `sentence-transformers`, `chromadb` may appear.
- **Facts, not judgments** (CLAUDE.md §2) → Probes emit findings ("semgrep rule `nodejs.eval-detected` fired on `src/plugins/loader.ts:42`"), never conclusions ("eval usage is risky"). `IndexHealthProbe` emits `commits_behind: int`, never `index_is_stale: bool`. The Pydantic models reject judgment-shaped field names via a regex check (continuing Phase 1's `JSONValue` discipline).
- **Extension by addition** ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), CLAUDE.md §2) → The 17 new probes in Phase 2 are 17 new files. The registry decorator collects them at import. The only mandatory edit to Phase 1 code is the import seam in `probes/__init__.py`. Six ADR-gated additions to `ALLOWED_BINARIES` (one per external CLI) follow Phase 1's `node` precedent.
- **Honest confidence + IndexHealthProbe** (CLAUDE.md §2, `localv2.md §5.2 B2`) → Every Phase 2 probe emits `confidence ∈ {high, medium, low}`. `IndexHealthProbe` reads them, computes per-domain freshness, and emits its own slice. CI gains a **dedicated dashboard line** ("number of `low`/`medium` confidences emitted per gather over the rolling fixture suite") so a regression that silently degrades confidence is visible without staring at YAML diffs.
- **Progressive disclosure** (CLAUDE.md §2) → SCIP index binary stays in `.codegenie/context/raw/scip-index.scip`. Semgrep findings JSON stays in `raw/semgrep-findings.json`. The `repo-context.yaml` slice indexes counts and top-N entries by path; the Planner reads originals from `raw/` at decision time. No probe inlines a `semgrep_findings[].rule_source` block.
- **Determinism over probabilism** ([ADR-0006](../../production/adrs/0006-continuous-deterministic-gather.md), CLAUDE.md §2) → BM25 (`tantivy`), not embeddings. `ripgrep`, not fuzzy match. `tree-sitter` AST queries, not classifier models. `eval()` detection is grep-with-AST, not "looks risky."
- **Organizational uniqueness as data** (CLAUDE.md §2) → Conventions catalog is `src/codegenie/catalogs/conventions/<language>.yaml`. Skills loader reads YAML frontmatter from `~/.codegenie/skills/**/SKILL.md` and per-repo `.codegenie/skills/**/SKILL.md`. Both are validated against catalog/skill schemas at load; malformed entries fail loud at CLI startup (Phase 1 precedent).

---

## Goals (concrete, measurable)

- **Public API surface (count):** **17 new probes**, **2 new catalogs** (conventions, shell-replacements), **1 new loader** (Skills), **6 new tool wrappers** (`semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`). Each lives in a single file with a single class or pure-function module-level API. Total new top-level packages: **1** (`src/codegenie/tools/` for the wrappers). All other code lives under existing Phase 1 packages.
- **Test coverage target:** **90% line / 80% branch on `src/codegenie/`**, matching Phase 1's ratchet. Per-module floor **85% line / 75% branch** for probes that wrap a CLI thinly (the wrapper is the test surface, not the probe). Declared in `pyproject.toml` with explicit ADR amendment trigger.
- **Cyclomatic complexity ceiling:** **McCabe ≤ 10 per function**, enforced via `ruff` (`C901` rule). Probes that exceed must be refactored or carry an inline `# noqa: C901 — see ADR-NN` with a Phase-2 ADR explaining why.
- **Number of net-new top-level packages:** **1** (`src/codegenie/tools/`). Every other addition slots into Phase 0/1 directories.
- **Golden file coverage:** **Every Phase 2 probe ships at least one golden** under `tests/golden/<probe_name>/`. Per-probe directory contains the input fixture (or symlink to `tests/fixtures/`) and the expected `<probe_name>.json` raw output. `pytest --update-goldens` regenerates; CI diff fails on drift.
- **Adversarial robustness:** Every external CLI wrapper has a unit test asserting graceful handling of (a) non-zero exit, (b) malformed JSON output, (c) timeout, (d) missing binary on PATH. The wrapper's failure path raises a typed exception; the probe catches and emits `confidence: low`. Phase 1's adversarial fixture corpus extends to cover hostile SCIP indexes (truncated, wrong magic) and hostile semgrep rule packs (malformed YAML).
- **Wall-clock targets (advisory):**
  - Cold gather on 1k-file Node.js fixture (all Phase 0+1+2 probes, all miss): **p50 ≤ 60 s, p95 ≤ 120 s.** Dominated by SCIP indexing (~20 s) and runtime trace (~80 s; left out of this advisory because Layer C runtime is invoked manually for now).
  - Warm gather (all cache hits): **p50 ≤ 1 s, p95 ≤ 2 s.** Phase 1's ratio holds.
- **Tokens per run: 0.** The `fence` CI job continues to assert. Extended with the new dependency closure.

---

## Architecture

```
                                codegenie gather <path>
                                          │
                                          ▼
                       ┌──────────────────────────────────┐
                       │ Phase 0 CLI / Phase 1 readiness  │   unchanged
                       │  + extended tool checks for       │
                       │   semgrep / syft / grype /        │
                       │   gitleaks / scip-typescript /    │
                       │   tree-sitter on $PATH            │
                       └─────────────┬────────────────────┘
                                     │
                                     ▼
                       ┌──────────────────────────────────┐
                       │ Phase 0 Coordinator              │   unchanged
                       │  + ParsedManifestMemo (Phase 1)  │
                       └─────────────┬────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────────┐
        │  Phase 1 Probe Registry (explicit import — no entry points) │
        │                                                              │
        │  ┌── Phase 1 (Layer A — unchanged) ─────────────────────┐    │
        │  │  language_detection · node_build_system ·            │    │
        │  │  node_manifest · ci · deployment · test_inventory    │    │
        │  └──────────────────────────────────────────────────────┘    │
        │                                                              │
        │  ┌── Phase 2 (new files) ──────────────────────────────┐     │
        │  │  Layer B (Semantic Index)                            │     │
        │  │    scip_index · index_health · node_reflection ·     │     │
        │  │    generated_code · build_graph                      │     │
        │  │  Layer C (Container, *static-only in Phase 2*)       │     │
        │  │    dockerfile · shell_usage · entrypoint ·           │     │
        │  │    certificate                                       │     │
        │  │    [SBOM/CVE/runtime-trace deferred — see §Goals]    │     │
        │  │  Layer D (Organizational)                            │     │
        │  │    repo_config · skills_index · adr · convention ·   │     │
        │  │    exception · policy · repo_notes ·                 │     │
        │  │    external_docs · external_docs_index               │     │
        │  │  Layer E (Cross-repo, stubbed)                       │     │
        │  │    ownership · service_topology · service_contract   │     │
        │  │    [SLO / production_config left as Phase 0 stubs]   │     │
        │  │  Layer F — empty for distroless (per localv2.md)     │     │
        │  │  Layer G (Behavioral hints + SAST)                   │     │
        │  │    semgrep · ast_grep · test_coverage_map ·          │     │
        │  │    invariant_hints · grep                            │     │
        │  └──────────────────────────────────────────────────────┘     │
        └─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/tools/  ← NEW package (thin CLI wrappers)  │
        │   semgrep.py · syft.py · grype.py · gitleaks.py ·        │
        │   scip_typescript.py · treesitter.py                     │
        │   Each: typed Pydantic model + run(...) -> Model         │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/catalogs/  ← extended                       │
        │   native_modules.yaml (Phase 1)                           │
        │   ci_providers.yaml (Phase 1)                             │
        │   conventions/                                            │
        │     node.yaml · _schema.json                              │
        │   shell_replacements/                                     │
        │     node.yaml · _schema.json                              │
        │   semgrep_rule_packs.yaml  (which packs apply per task)   │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ src/codegenie/skills/  ← NEW (loader, not Skill content)  │
        │   loader.py — discovers, validates, indexes SKILL.md      │
        │   models.py — Pydantic Skill manifest                     │
        │   schema/skill.schema.json                                │
        └──────────────────────────────────────────────────────────┘
                                     │
                                     ▼
        Phase 0 cache + sanitizer + writer (unchanged)
                                     │
                                     ▼
              .codegenie/context/
              ├── repo-context.yaml      (envelope + ~17 new slices)
              ├── raw/                   (per-probe JSON + scip-index.scip + semgrep + gitleaks)
              └── runs/<utc>-<short>.json
```

Three properties to read from the diagram:

1. **Every Phase 0/1 box says "unchanged."** Same test as Phase 1.
2. **CLI wrappers are a sibling package.** Probes import from `codegenie.tools`. The wrapper is the one place that knows the tool's stdout shape. If `grype` changes JSON in v0.84, exactly one file changes.
3. **Skills loader is a sibling package, not a probe.** `SkillsIndexProbe` *uses* the loader; the loader is independently testable and reusable by later phases (Stage 3 Planner reads the same loader).

---

## Components

For each component below: purpose, interface, internal design citing the idiom, dependencies, location, tradeoffs accepted.

### 1. CLI wrappers — `src/codegenie/tools/`

- **Purpose:** Centralize all knowledge about external CLI invocation, exit codes, stdout/stderr shapes, and JSON quirks in one place per tool. Probes consume **typed Pydantic models**, never raw subprocess output.
- **Public interface:** Each wrapper exports `run(...) -> <Tool>Result`, where `<Tool>Result` is a Pydantic `BaseModel`. Example:
  ```python
  # src/codegenie/tools/semgrep.py
  class SemgrepFinding(BaseModel):
      check_id: str
      severity: Literal["info", "warning", "error"]
      path: Path
      line: int
      message: str

  class SemgrepResult(BaseModel):
      version: str
      findings: list[SemgrepFinding]
      errors: list[str]
      paths_scanned: int

  async def run(
      repo_root: Path,
      *,
      rule_packs: Sequence[str],
      timeout_s: float,
      raw_output_path: Path,
  ) -> SemgrepResult: ...
  ```
- **Internal design (idiomatic Python conventions cited):**
  - Calls Phase 0's `exec.run_allowlisted` — no direct `subprocess.run`. Phase 1 precedent.
  - JSON output written to `raw_output_path` first, then parsed (so the raw artifact survives even if the wrapper crashes mid-parse).
  - Uses `pydantic.TypeAdapter(<Result>).validate_json(...)` rather than constructing models field-by-field. **Pydantic is the idiomatic Python "parse, don't validate" tool**; the entire `unknown JSON → typed object` contract belongs there.
  - Wrapper-level exceptions are typed: `ToolNotFound`, `ToolTimeout`, `ToolNonZeroExit`, `ToolOutputMalformed`. Each carries `stderr` (truncated to 1 KB) for human diagnosis.
- **Dependencies:** `pydantic` (already in Phase 0). No new C-extensions. No `orjson`.
- **Where it lives:** `src/codegenie/tools/{semgrep,syft,grype,gitleaks,scip_typescript,treesitter}.py`.
- **Tradeoffs accepted:**
  - Six small modules instead of one big one. Acceptable — single-responsibility wins.
  - The wrapper is a thin "shell," but it isolates the change surface. If `grype` ships a new JSON field, only `tools/grype.py` and its test change.

### 2. Layer B probes

#### 2.1 `SCIPIndexProbe` (B1)

- **Purpose:** Run `scip-typescript` against TypeScript repos; emit `semantic_index` slice. (`localv2.md §5.2 B1`.)
- **Interface:** Standard probe ABC. `declared_inputs = ["tsconfig.json", "tsconfig.*.json", "package.json", "src/**/*.ts", "src/**/*.tsx"]`. `requires = ["language_detection", "node_build_system"]`. `applies_to_languages = ["typescript", "javascript"]`. `timeout_seconds = 600` (SCIP can be slow on large repos).
- **Internal design:**
  - Calls `tools.scip_typescript.run(repo_root, raw_output_path=ctx.output_dir / "scip-index.scip", timeout_s=600)`.
  - Wrapper returns `SCIPRunResult(files_indexed, files_in_repo, symbol_count, exported_symbols, indexer_errors, indexer_warnings, any_type_density, unresolved_dynamic_imports, unresolved_computed_access)` — the wrapper does the math, the probe does the slice.
  - Confidence = `high` if `files_indexed / files_in_repo >= 0.95`, `medium` if `>= 0.80`, `low` otherwise. Same rule documented in the wrapper and the probe both — but the **wrapper computes it once**.
  - Raw `.scip` binary stays in `raw/scip-index.scip`. The slice only carries metadata.
- **Where it lives:** `src/codegenie/probes/scip_index.py`.

#### 2.2 `IndexHealthProbe` (B2) — the load-bearing one

- **Purpose:** **The single most important probe for honest confidence** (`localv2.md §5.2 B2`, CLAUDE.md "Honest confidence"). Surfaces freshness and coverage of every index-producing probe as first-class data. Stale or partial indexes are silent failure modes; this probe makes them loud.
- **Interface:** Standard probe ABC. `requires = ["scip_index", "semgrep"]` (others as added). `declared_inputs = ["__git__:HEAD"]` (special token: cache invalidates whenever git HEAD moves). `applies_to_tasks = ["*"]`.
- **Internal design — the asymmetry lives in observability, not in code:**
  - **The probe itself is *structurally identical* to every other probe.** Standard ABC, standard return shape, standard sub-schema. No special handling in the coordinator. This is deliberate: special-casing in code is the smell.
  - It reads other probes' confidence + freshness fields from the coordinator's in-memory `RepoContext` builder. The Coordinator exposes a read-only view via `ProbeContext.peer_outputs() -> Mapping[str, ProbeOutput]`. **This is the one Phase 0 dataclass extension Phase 2 makes.** Phase-2 ADR-gated, same shape as Phase 1's `ParsedManifestMemo` extension.
  - Per-domain (`scip`, `runtime_trace`, `sbom`, `semgrep`, `gitleaks`): emits `last_indexed_commit`, `commits_behind`, `coverage_pct`, `indexer_errors`, `confidence`. Same shape across domains — a single Pydantic `IndexDomainHealth` model parameterized by domain name.
  - **`requires` of `IndexHealthProbe`** is the topological mechanism that guarantees it runs last in its wave. No special "run last" flag.
- **Where the outsized importance shows up:**
  - **CI dashboard line:** "IndexHealthProbe confidence distribution over the rolling fixture suite, last 30 days." A regression where the average confidence ticks down by one bucket fires a dashboard alert. Same dashboard infra Phase 0 ships.
  - **A dedicated golden file** (`tests/golden/index_health/`) per fixture — every fixture's expected `index_health` slice is committed. Drift fails CI.
  - **A deliberately-seeded staleness fixture** (`tests/fixtures/stale_scip_repo/`): a Node repo where the committed `scip-index.scip` was built against an *older* commit than HEAD. `IndexHealthProbe` must emit `commits_behind > 0` and `confidence: low`. **This is the Phase 2 roadmap exit-criterion test** ("IndexHealthProbe surfaces at least one real staleness case in CI").
  - **A `--strict` CLI flag**: `codegenie gather --strict ...` exits non-zero if any `IndexHealthProbe` domain reports `low` confidence. Default behavior is unchanged (still exits 0); `--strict` is opt-in for CI pipelines that want to fail loud.
- **Dependencies:** None new. Pure Python over `ProbeContext`.
- **Where it lives:** `src/codegenie/probes/index_health.py`.
- **Tradeoffs accepted:**
  - The `ProbeContext.peer_outputs` extension touches Phase 0/1 surface. Acknowledged; ADR-gated. The alternative (a side-channel file in `cache/`) is exactly the kind of cleverness Rule 8 warns about.
  - "Outsized importance" lives in tests + dashboards + the `--strict` flag. Not in code. If I find myself writing `if probe.name == "index_health"` anywhere in the coordinator, I have made a mistake.

#### 2.3 `NodeReflectionProbe` (B3), `GeneratedCodeProbe` (B4), `BuildGraphProbe` (B5)

- **Purpose:** Populate `reflection`, `generated_code`, `build_graph` slices per `localv2.md §5.2`.
- **Interface:** Standard ABC. `NodeReflectionProbe` uses `tools.treesitter.query(...)`. `GeneratedCodeProbe` is a filesystem walk + header-pattern matcher. `BuildGraphProbe` runs `pnpm list -r --depth -1 --json` (or equivalent) and parses the output.
- **Internal design:**
  - `NodeReflectionProbe`: tree-sitter queries live in **a sibling YAML file** (`src/codegenie/probes/_reflection_queries/node.yaml`), loaded at import. Adding a new pattern is a YAML PR. **Same shape as Phase 1's catalogs.**
  - `GeneratedCodeProbe`: header patterns (`"Generated by graphql-codegen"`, `// Code generated by`, etc.) live in `_generated_code_patterns.yaml`. Filesystem walk excludes Phase 0's noise dirs.
  - `BuildGraphProbe`: applies only when monorepo markers exist (per Phase 1's `LanguageDetectionProbe` extension). Otherwise `applies()` returns False — the slice is omitted from the envelope (Phase 1 precedent for non-Node repos).
- **Where they live:** `src/codegenie/probes/node_reflection.py`, `generated_code.py`, `build_graph.py`.

### 3. Layer C probes — static-only in Phase 2

- **Scope decision (concrete, opinionated):** Phase 2 lands `DockerfileProbe`, `ShellUsageProbe` (static analysis only), `EntrypointProbe`, `CertificateProbe`. **`SBOMProbe`, `CVEProbe`, `RuntimeTraceProbe` are deferred to Phase 5 (Sandbox + Trust gates)**, where the microVM + Docker-in-Docker infrastructure they need actually lives.
- **Why defer:** The roadmap's Phase 2 exit criteria say "every probe layer runs against real repos" — but `RuntimeTraceProbe` requires a running container, which presupposes the sandbox stack. Trying to land a 80-second strace-based runtime probe before [ADR-0019](../../production/adrs/0019-sandbox-stack.md) is resolved is the kind of premature commitment that turns into either rewriting in Phase 5 or living with a brittle local-only implementation. **Best-practices says: build the deterministic, fast, well-tested static slices now; build the dynamic ones inside the sandbox they belong in.** Surfacing this scope reduction is what Rule 12 ("Fail loud") demands when "best practices would prevent meeting exit criteria."
- **Concrete probes shipped in Phase 2 Layer C:**
  - `DockerfileProbe` (C1): wraps the `dockerfile` Python library; emits `containerization` slice. Pydantic model captures parse output.
  - `ShellUsageProbe` (C5): static-only — combines `DockerfileProbe` output with the `shell_replacements/node.yaml` catalog. The runtime-trace half of the probe is deferred (it's listed in the slice as `runtime_trace_evidence: null` with `runtime_trace_pending: true`).
  - `EntrypointProbe` (C7): reads `DockerfileProbe`'s parsed entrypoint + `package.json#engines`. Emits the static half of `entrypoint`.
  - `CertificateProbe` (C6): scans Dockerfile RUN commands for `update-ca-certificates`, source code for `NODE_EXTRA_CA_CERTS` references via tree-sitter, and Helm values for cert mounts. No image filesystem inspection (that's Phase 5).
- **Where they live:** `src/codegenie/probes/dockerfile.py`, `shell_usage.py`, `entrypoint.py`, `certificate.py`.

### 4. Layer D — Organizational

Nine probes, all idiomatic Python. The interesting one is the Skills loader, which is a **separate package** that the probe consumes.

#### 4.1 Skills loader — `src/codegenie/skills/`

- **Purpose:** Discover, validate, and index Skills from `~/.codegenie/skills/`, `.codegenie/skills/`, and `~/.codegenie/skills-org/`. Index by `applies_to.task_types` × `applies_to.languages` × `applies_to.conditions`.
- **Public interface:**
  ```python
  # src/codegenie/skills/loader.py
  def discover_skills(roots: Sequence[Path]) -> SkillIndex: ...

  # src/codegenie/skills/models.py
  class SkillManifest(BaseModel):
      name: str
      description: str
      applies_to: SkillApplicability
      requires_evidence: list[str]
      required_tools: list[str]
      source_path: Path
      body_char_count: int   # body NOT loaded; just sized

  class SkillIndex(BaseModel):
      skills: list[SkillManifest]
      def for_task_and_language(self, task: str, language: str) -> list[SkillManifest]: ...
      def matching_conditions(self, context: Mapping[str, Any]) -> list[SkillManifest]: ...
  ```
- **Internal design (idiomatic):**
  - YAML frontmatter via Phase 1's `safe_yaml.load` — caps inherited.
  - Frontmatter validated against `src/codegenie/skills/schema/skill.schema.json` (Draft 2020-12). Malformed → loud failure at CLI startup (Phase 1 catalog precedent).
  - Body is **never loaded into memory**. The loader records `body_char_count` from a stat call. Progressive disclosure ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), CLAUDE.md §2).
  - The `SkillIndex` is a small `dict[(task, language), list[SkillManifest]]` lookup built once. Filter-then-conditional-check is the idiomatic two-step.
- **Where it lives:** `src/codegenie/skills/{loader.py,models.py,schema/skill.schema.json}`.
- **Tradeoffs accepted:**
  - The Stage 3 Planner (Phase 3+) needs the same loader. Putting it under `skills/` rather than `probes/skills_index.py` is the right shape: the loader is a service the probe uses, not a probe responsibility.

#### 4.2 `SkillsIndexProbe` (D2)

- **Purpose:** Run the Skills loader; emit the `organizational.available_skills` slice listing matching skills (manifest only, no body).
- **Interface:** Standard ABC. `declared_inputs = ["~/.codegenie/skills/**/SKILL.md", ".codegenie/skills/**/SKILL.md"]`. The `~/` token is resolved against `os.environ["HOME"]` at cache-key time; resolved path is what's hashed.
- **Internal design:** ~30 LOC. Calls `discover_skills([...])`, filters by current `task` + detected `languages`, emits the manifest list.

#### 4.3 `ConventionProbe` (D5) — and the conventions catalog

- **Purpose:** Apply org-defined conventions (Dockerfile patterns, source patterns) against the repo; emit `organizational.conventions.{pass, fail, not_applicable}`.
- **Conventions catalog location:** `src/codegenie/catalogs/conventions/<language>.yaml`. Schema: `src/codegenie/catalogs/conventions/_schema.json`. **Same package as Phase 1's `native_modules.yaml` and `ci_providers.yaml`.** The new file is purely additive.
- **Schema (excerpt):**
  ```yaml
  # src/codegenie/catalogs/conventions/node.yaml
  catalog_version: 1
  conventions:
    - name: acme-tini-required
      description: "All Node services must use tini as PID 1"
      applies_to:
        task_types: ["*"]
        languages: ["javascript", "typescript"]
      detect:
        type: dockerfile_entrypoint_starts_with
        value: "tini"
      severity: error
    - name: acme-no-npm-runtime
      description: "Runtime image must not include npm/pnpm/yarn"
      applies_to: ...
      detect:
        type: dockerfile_final_stage_run_command_excludes
        pattern: '(npm|pnpm|yarn) (start|run)'
      severity: error
  ```
- **`detect.type` enum** is closed (extension by addition: new types require a new YAML schema bump and a new dispatch handler). **The dispatch is a single `match/case` in `_apply_detector(conv, dockerfile_output) -> ConventionResult`** — three lines per detector. No plugin system, no class hierarchy. `match/case` is the idiomatic Python 3.10+ way.
- **Where it lives:** `src/codegenie/probes/convention.py` (~120 LOC).

#### 4.4 `ExternalDocsProbe` (D8) + `ExternalDocsIndexProbe` (D9)

- **Purpose:** Fetch external docs (filesystem-only in Phase 2 — Confluence/Notion deferred per `localv2.md §12 Week 5`); build BM25 index via `tantivy`.
- **Internal design:**
  - `ExternalDocsProbe`: iterates over `config.external_docs` of type `filesystem` and `url_list`; copies content to `raw/external-docs/`; emits manifest with headings + tags. Heading extraction is a 20-line markdown-AST walk (use `markdown-it-py`'s tokenizer — well-supported, no surprises).
  - `ExternalDocsIndexProbe`: builds tantivy index from manifest; ripgrep fallback if `tantivy` is not installed (degrades to `confidence: medium` with a structured warning).
- **Dependencies:** `tantivy` (PyPI, Rust-backed, well-maintained, widely used). `markdown-it-py` (PyPI, stdlib-style, no surprises).
- **Where they live:** `src/codegenie/probes/external_docs.py`, `external_docs_index.py`.

#### 4.5 Remaining D probes — boring as a feature

`RepoConfigProbe` (D1), `ADRProbe` (D3), `PolicyProbe` (D4), `ExceptionProbe` (D6), `RepoNotesProbe` (D7) are each <80 LOC. Each:

- Reads a known path (or globs).
- Validates against a small Pydantic model.
- Emits a structural slice.
- Has 1 unit test + 1 golden + 1 adversarial fixture (malformed YAML).

These are the "boring tech, well-supported" the lens calls for. No surprises is the feature.

### 5. Layer E — stubs in Phase 2

`OwnershipProbe` (E1) ships in Phase 2 reading `CODEOWNERS` (well-defined format, GitHub-documented). `ServiceTopologyProbe` (E2), `ServiceContractProbe` (E3), `SLOProbe` (E4), `ProductionConfigProbe` (E5) remain stubs per `localv2.md §5.5`. The probe class exists, `applies()` returns False unless config provides a source, and the slice emits a `{stub: true}` marker. **Each stub gets one unit test asserting the stub shape.** No more.

### 6. Layer G — SAST + behavioral hints

#### 6.1 `SemgrepProbe` (G1)

- **Purpose:** Run `semgrep` with curated rule packs (per `localv2.md §5.6 G1`); emit `semgrep_findings` slice.
- **Internal design:**
  - Calls `tools.semgrep.run(repo_root, rule_packs=catalogs.SEMGREP_RULE_PACKS.for_task(task))`.
  - Rule pack catalog: `src/codegenie/catalogs/semgrep_rule_packs.yaml` — declares which packs apply per task (`{distroless_migration: [p/dockerfile, p/nodejs, p/javascript, p/secrets]}`). Catalog YAML, same shape as Phase 1.
  - Wrapper-level timeout is 300 s; probe `timeout_seconds = 360`.
  - Raw findings JSON in `raw/semgrep-findings.json` (load-bearing per progressive disclosure).
  - Slice contains: rule packs used, files scanned, count by severity, top-N findings by path (N=20, configurable in catalog). Full list lives in `raw/`.
- **Where it lives:** `src/codegenie/probes/semgrep.py`.

#### 6.2 `AstGrepProbe`, `TestCoverageMappingProbe`, `InvariantHintProbe`, `GrepProbe`

- All four follow the same shape: thin wrapper → Pydantic result → slice. Each <100 LOC. Each with a golden + a unit test + an adversarial fixture.

#### 6.3 `GitleaksProbe` (new, not in `localv2.md` Layer G but Phase 2 roadmap explicitly lists "security probes")

- **Purpose:** Run `gitleaks detect` against the repo; emit `secret_findings` slice. Roadmap: "secret/security probes."
- **Internal design:** Calls `tools.gitleaks.run(repo_root)`. Findings emit the **rule ID and path/line** only; the actual matched secret bytes are **never** copied into the slice or raw artifact. The wrapper invokes gitleaks with `--redact` to ensure even the JSON output is redacted. Phase 0's sanitizer is the belt-and-suspenders defense.
- **Where it lives:** `src/codegenie/probes/gitleaks.py`.
- **Tradeoffs accepted:** This probe is the most "security-shaped" addition; the redaction discipline is the load-bearing detail. The convention is enforced in the wrapper (single chokepoint), not at every probe.

### 7. Golden-file infrastructure

- **Mechanism:** ~80-line pytest helper in `tests/_golden.py`. Bytes-on-disk diff. **Not a plugin.**
- **Public interface:**
  ```python
  # tests/_golden.py
  def assert_golden(
      actual: Mapping[str, Any] | bytes,
      golden_path: Path,
      *,
      update: bool = False,
  ) -> None: ...
  ```
  - `update` is set when `pytest --update-goldens` is passed (a `pytest_addoption` hook in `conftest.py`).
  - For dict actuals: dumps to canonical JSON (`json.dumps(sort_keys=True, indent=2)`), compares against committed file.
  - For bytes actuals (e.g., SCIP index — though we don't golden binary outputs, we golden the *summary*): compares byte-for-byte.
- **Why not a plugin:** Plugins are heavy. The semantics are 80 lines. Idiomatic pytest is fixtures + conftest hooks; introducing a third-party plugin (`pytest-golden`, `syrupy`) adds a dependency, a magic file format, and a learning curve. The bytes-on-disk diff helper is what Rule 5 calls for ("widely-used dependency > niche dependency; but stdlib > both when stdlib suffices").
- **Where the goldens live:** `tests/golden/<probe_name>/<fixture_name>/expected.json`. Each fixture has a matching `tests/fixtures/<fixture_name>/` repo.
- **CI behavior:** Diff failure prints the diff and the `--update-goldens` instruction. **Updating a golden is a deliberate PR step** with reviewer attention — exactly the friction the roadmap calls for.

### 8. Schema additions

Per-probe sub-schemas under `src/codegenie/schema/probes/`, one per Phase 2 probe, each `additionalProperties: false` at its own root. Same Phase 1 precedent. No envelope-level changes.

The envelope's `probes.*` keeps `additionalProperties: true` (Phase 0 §2.9, Phase 1 §9). Strictness lives per-probe.

### 9. Conventions catalog schema versioning

- `catalog_version: int` at the top of each catalog YAML (Phase 1 precedent, formalized for Phase 2's larger surface).
- Catalog is in `declared_inputs` of every probe that reads it → catalog bumps invalidate cache cleanly.
- A Phase-2 ADR establishes the policy: **adding entries is a minor bump (cache invalidates for that probe); removing or restructuring entries is a major bump (probe + sub-schema both change in the same PR)**.

---

## Data flow

Representative warm-path run on a Phase 1 Node.js fixture extended with `.codegenie/skills/`, semgrep rule packs, and a stale SCIP index:

1. **CLI entry** (Phase 0, unchanged). Tool-readiness check now covers Phase 2's six new external CLIs.
2. **Coordinator dispatch** (Phase 0, unchanged + `ProbeContext.peer_outputs` extension from Phase 2 ADR).
3. **Wave 1**: `LanguageDetectionProbe` (Phase 1).
4. **Wave 2**: Phase 1 Layer A probes + Phase 2 probes with `requires=["language_detection"]` (e.g., `SCIPIndexProbe`, `SkillsIndexProbe`, `ConventionProbe`).
5. **Wave 3**: Probes with `requires` on wave 2 (`NodeReflectionProbe` → SCIP, `SemgrepProbe` → build_system, `EntrypointProbe` → dockerfile).
6. **Wave 4**: `IndexHealthProbe` (`requires = [...all index-producing probes...]`). Reads peer outputs, emits `index_health` slice. **The "outsized importance" of B2 is invisible in the coordinator dispatch logic — it just runs last because `requires` orders it last.**
7. **Per-probe ProbeOutput** through Phase 0's `_ProbeOutputValidator` + two-pass sanitizer.
8. **Cache write + index** (Phase 0).
9. **Envelope merge + per-probe sub-schema validation** (Phase 1 mechanism extended to ~17 new sub-schemas).
10. **Raw artifacts** written per probe (Phase 0).
11. **YAML write + audit record** (Phase 0).
12. **Exit 0** (or exit 3 if `--strict` and any `IndexHealthProbe` domain is `low`).

The probe contract is what makes this readable. Every probe is the same shape; the data flow is "iterate probes, dispatch, collect, validate, write." No special cases.

---

## Failure modes & recovery

| Failure | Detected by | Recovery | Provenance |
|---|---|---|---|
| `scip-typescript` not on PATH | `tools.scip_typescript.run` raises `ToolNotFound` | `SCIPIndexProbe` catches, emits `confidence: low`, slice omitted | best-practices: typed exceptions |
| `scip-typescript` exits non-zero | `tools.scip_typescript.run` raises `ToolNonZeroExit` with stderr | Probe emits `confidence: low`, `errors: [stderr]`; gather continues | best-practices |
| Semgrep rule pack download fails (network) | `tools.semgrep.run` retries 2x then raises `ToolNonZeroExit` | Probe falls back to local rule packs only; `confidence: medium`, structured warning | best-practices |
| `gitleaks` finds a secret | Wrapper redacts via `--redact` | Probe emits rule ID + path/line only; sanitizer is the second wall | security-aware default |
| Stale SCIP index (committed `.scip` older than HEAD) | `IndexHealthProbe` compares `last_indexed_commit` to current commit | `index_health.scip.confidence: low`, `commits_behind: N`; **CI fixture asserts this happens** | best-practices + roadmap exit criterion |
| Skill manifest YAML malformed | Skills loader's JSON-schema validation fails at CLI startup | Hard fail with path; CLI exits 2 | best-practices |
| Convention catalog malformed | Phase 1 catalog precedent | Hard fail at CLI startup | best-practices |
| Adversarial markdown in external doc (zip-slip, huge file) | Phase 1 `safe_yaml`/path-traversal guards inherited; markdown-it-py is well-fuzzed | Skip file, structured warning, `confidence: medium` | best-practices |
| `tantivy` not installed | `ExternalDocsIndexProbe` import-time fallback | BM25 falls back to ripgrep; `confidence: medium` | best-practices |
| Tree-sitter grammar version mismatch | `tools.treesitter.parse` raises `GrammarVersionMismatch` | Probe emits `confidence: low` | best-practices |
| `ProbeContext.peer_outputs` not provided (old wiring) | `IndexHealthProbe` checks; emits `confidence: low` with structured warning | Same correctness, less precision; surfaces in CI | best-practices |

Pattern: **typed exceptions at the boundary, caught at the probe, surfaced as structured `confidence: low` + `warnings: [<id>]`**. Same shape as Phase 1.

---

## Resource & cost profile

- **Tokens per run:** 0. `fence` CI job extended to cover Phase 2 dependencies.
- **Wall-clock (advisory, 1k-file Node fixture, M-series Mac):**
  - Cold (Phase 0+1+2 probes, all miss, Layer C runtime probes excluded — they're Phase 5): p50 ≤ 60 s, p95 ≤ 120 s. Dominated by `scip-typescript` (~20 s) and `semgrep` (~15 s).
  - Warm (all hits): p50 ≤ 1 s.
  - Incremental (`package.json` changed): p50 ≤ 5 s — re-runs `SCIPIndexProbe` (TS sources unchanged so memo helps), `SemgrepProbe` (rule packs unchanged so cache hit possible if files unchanged).
- **Memory (RSS):** ~250 MB peak (semgrep dominates; SCIP indexer is ~150 MB on a 1k-file repo). Acceptable on dev laptops; Phase 14 worker tunes.
- **Storage per gather:** `repo-context.yaml` ~80 KB; `raw/` ~5 MB (scip-index + semgrep findings dominate); cache ~1 MB. ~6 MB per gather.
- **CI walltime delta vs Phase 1:** +90 s p50, +180 s p95. Phase 1's advisory was 120 s p95; new advisory is 300 s p95. Surfaced as dashboard metric, not a gate.
- **External-dep additions (pip):** `tantivy`, `markdown-it-py`, `tree-sitter` (Python binding), `tree-sitter-typescript`, `tree-sitter-javascript`. Each well-maintained, widely used. **No new C-extensions for parsers** — `tree-sitter` is the unavoidable one (it's a parser library); the others are pure-Python or Rust-backed Python wheels.
- **External CLI additions to `ALLOWED_BINARIES` (ADR-gated, one ADR per binary):** `scip-typescript`, `semgrep`, `gitleaks`, `ast-grep`, `ripgrep`. (`syft`, `grype`, `docker` deferred to Phase 5 with their probes.) Each ADR documents the threat (`$PATH` shim), the mitigation (Phase 0 env-strip + timeout), and the invocation pattern.

---

## Test plan

The test pyramid is wide at the unit base, narrower at the integration top. Every probe has 5 layers of test before integration is even considered.

### Unit tests (`tests/unit/probes/` and `tests/unit/tools/`)

- **Per probe:** at least 6 tests — happy path, missing input, malformed input, partial input, confidence-degrade cases, schema conformance.
- **Per CLI wrapper:** at least 4 tests — happy path (recorded fixture stdout), non-zero exit, timeout, malformed JSON. **Wrappers are tested with recorded tool output JSON in `tests/fixtures/tool_outputs/`**, never by actually invoking the CLI in a unit test. CLI invocation is integration-level.
- **Skills loader:** discovery, frontmatter parsing, schema validation, indexing, condition matching. One test per code path.
- **Conventions detector dispatch:** one test per `detect.type` enum value, plus a "malformed conventions YAML fails at startup" test.

Coverage shape: ~250 unit tests across Phase 2; ratio ~3:1 with Phase 1 (which had ~80 unit tests).

### Adversarial tests (`tests/adv/`) — CI-gating

Phase 1's adversarial corpus carries forward. Phase 2 adds:

- `test_truncated_scip_index.py` — fixture `.scip` file truncated mid-record; probe emits `confidence: low`, never OOMs.
- `test_malformed_semgrep_output.py` — semgrep stdout is invalid JSON; wrapper raises `ToolOutputMalformed`, probe degrades.
- `test_gitleaks_redaction_invariant.py` — synthetic repo with a hardcoded secret; assert the secret bytes appear **nowhere** in `repo-context.yaml` or any `raw/*.json`.
- `test_stale_scip_fixture.py` — the deliberately-seeded staleness fixture. `IndexHealthProbe` must report `commits_behind > 0` and `confidence: low`. **This is the Phase 2 roadmap exit criterion test.**
- `test_skill_yaml_injection.py` — hostile YAML in a SKILL.md frontmatter; `safe_yaml` refuses; loader fails loud.
- `test_external_doc_zip_slip.py` — hostile filesystem doc path attempts escape; refused with structured warning.
- `test_huge_external_doc.py` — 200 MB markdown; size cap fires; probe degrades.
- `test_treesitter_grammar_version_mismatch.py` — wrong grammar version; wrapper raises typed exception.

### Integration tests (`tests/integration/`)

- `test_phase2_end_to_end_node.py` — full `codegenie gather` on `tests/fixtures/node_typescript_helm/` (Phase 1's primary fixture, extended with Phase 2-relevant inputs: `.codegenie/skills/`, semgrep rule pack, a SKILL.md). Every Phase 2 slice populated. Envelope + sub-schemas validate.
- `test_cache_hits_across_phases.py` — gather twice; assert all 23 probes (Phase 1's 6 + Phase 2's 17) return `CacheHit`.
- `test_real_oss_with_layer_b_g.py` — clone `nestjs/nest` at a pinned SHA, gather; assert SCIP index produced, semgrep ran clean, gitleaks ran clean, conventions catalog applied.
- `test_strict_flag_fails_on_low_confidence.py` — gather with `--strict` against the stale-scip fixture; assert exit code 3.

**No live external-API tests.** Confluence/Notion deferred per `localv2.md §12 Week 5`.

### Golden-file tests (`tests/golden/`)

**Every Phase 2 probe ships at least one golden.** Per-probe `tests/golden/<probe>/<fixture>/expected.json`. CI diff fails on drift. Update path: `pytest --update-goldens`, reviewed in the PR.

The Phase 2 roadmap exit criterion ("Golden-file tests per probe") is satisfied by this convention applied uniformly.

### Property tests (where applicable, sparingly)

- `test_conventions_dispatch_is_total.py` — `hypothesis` generates `detect.type` values within the enum, asserts dispatch never raises `KeyError`.
- `test_skill_index_query_idempotent.py` — `hypothesis` generates `(task, language)` pairs, asserts `for_task_and_language` returns the same list on repeated calls.

Property tests are limited to areas where they genuinely shine (total dispatch, idempotence). I do not property-test lockfile parsers or CLI wrappers — those are tested with curated fixtures.

### E2E

- One. `test_phase2_end_to_end_node.py` is also the e2e. The unit + integration + golden pyramid carries the weight.

---

## Risks (top 5)

1. **`scip-typescript` is the load-bearing semantic-index tool and its maintenance velocity is uneven.** A regression in a future version could silently degrade the SCIP index. **Mitigation:** the wrapper pins a known-good version in `pyproject.toml` (`scip-typescript>=0.3.20,<0.4`); `IndexHealthProbe` will catch silent degradation via `coverage_pct` thresholds; CI runs the SCIP probe against a fixed fixture and fails on field-by-field regression. The **dedicated dashboard line** for `IndexHealthProbe.scip.confidence` over the rolling fixture suite makes this visible.
2. **Skills loader's `~/.codegenie/skills/` discovery introduces a non-repo dependency that breaks reproducibility in CI.** **Mitigation:** the loader's `roots` parameter is explicit (no implicit `~/` fallback in tests); CI passes only the repo-local `.codegenie/skills/` path; the `~/` resolution is a CLI-layer behavior, not a loader behavior. Tests run with `HOME=/dev/null`-equivalent isolation.
3. **`tantivy` is a Rust-backed dep with C-extension surface.** Phase 1 explicitly avoided new C-extensions. **Mitigation:** the BM25 ripgrep fallback is the primary path in CI; `tantivy` is opt-in and gated by `pip extras` (`pip install codegenie[search]`); a Phase 2 ADR documents the C-extension surface increase and the fallback discipline.
4. **Conventions catalog grows into a DSL.** A team that wants conditional logic ("convention X applies only if Y") starts requesting catalog features that turn YAML into code. **Mitigation:** the `detect.type` enum is closed; new types require a code change (the dispatch handler) in the same PR. **"Catalog is data" is enforced by the closed enum**; if a team wants conditional logic, they write a new detector type and a new ADR.
5. **`IndexHealthProbe`'s special status creeps into the coordinator.** A future engineer adds `if probe.name == "index_health"` somewhere. **Mitigation:** the design forbids it; the `peer_outputs` mechanism is the *only* asymmetry, and it's available to *any* probe (no name check); the Phase 2 ADR establishing `peer_outputs` explicitly documents this. Code review on any future coordinator change is the load-bearing defense.

---

## Acknowledged blind spots

- **No runtime trace in Phase 2.** I deferred `SBOMProbe`, `CVEProbe`, `RuntimeTraceProbe` to Phase 5 because they need the sandbox infrastructure. The roadmap's exit-criterion phrasing ("every probe layer runs against real repos") is satisfied for Layers B, D, E, G in this design; Layer C ships its **static** half only. This may not match what the roadmap author intended. **Surfaced for the synthesizer to weigh.**
- **No Layer F.** `localv2.md §5.7` is explicit that Layer F is deferred. The roadmap is silent. I read Phase 2 as "land everything that's not LLM-dependent and not sandbox-dependent." If the synthesizer disagrees, the additions are mechanical (new probe files, new wrappers).
- **External-doc fetchers (Confluence/Notion) deferred.** Filesystem and URL list sources land. Confluence/Notion adds OAuth + rate-limit + cassette-recording complexity. Per `localv2.md §12 Week 5`, those are v0.2.
- **Performance is not the lens here.** Phase 2's design will be slower than the performance-first version. I've stated targets but I'm not optimizing for them. The performance lens will surface concrete wins; the synthesizer should fold those in where they don't violate maintainability.
- **`tree-sitter` C-extension was unavoidable; I added it but didn't soul-search.** It's the standard tool for the job, well-maintained, widely used. Phase 1's "no C extensions" was specifically about parsers we could replace with stdlib (`json5` → stdlib `json` + 30-line comment-stripper); tree-sitter has no stdlib analog.
- **Schema-version policy for sub-schemas still deferred** (Phase 1 Open Question #2). Phase 2 lands ~17 new sub-schemas v1 without addressing this. Recommend the synthesizer either pin it down now or formally defer to Phase 4 when the first cross-phase sub-schema change is anticipated.

---

## Open questions for the synthesizer

1. **Layer C scope.** Should `SBOMProbe`/`CVEProbe`/`RuntimeTraceProbe` ship in Phase 2 (as a degraded local-only implementation that's rewritten in Phase 5), or be deferred? My read is defer; the security lens may disagree. The performance lens may push for an aggressively-parallelized version. **What's the strongest argument for shipping the dynamic Layer C in Phase 2?**
2. **`peer_outputs` on `ProbeContext`.** Phase 1 ADR-gated a similar extension (`parsed_manifest` memo). Is one ADR-gated extension per phase the right cadence, or should we batch them? My read is "boring is good; ADR per change." Surfacing in case the synthesizer wants a different policy.
3. **Should `IndexHealthProbe` get a `--strict` flag, or should every probe-confidence threshold be a separate CLI flag?** I propose one `--strict` flag tied to `IndexHealthProbe`'s aggregate output. Alternative: per-probe thresholds in `~/.codegenie/config.yaml`. The simpler answer wins for Phase 2; the richer answer probably arrives in Phase 13 (cost ledger + budget enforcement is the same shape).
4. **Conventions catalog: language-scoped (`conventions/node.yaml`) or task-scoped (`conventions/distroless_migration.yaml`)?** I picked language-scoped because Phase 7 will add `conventions/distroless_migration.yaml` as additive; the `applies_to.task_types` field on each entry handles task scoping within a language file. The performance lens may prefer task-scoped for cache locality. The security lens may prefer task-scoped for blast-radius reasoning. **Surfaced for arbitration.**
5. **`tools/treesitter.py` exposes grammar parsing as a service to multiple probes (`NodeReflectionProbe`, `InvariantHintProbe`, `CertificateProbe`). Does that warrant a shared in-process AST cache (analogous to Phase 1's `ParsedManifestMemo`)?** My read: yes, but only if benchmarks show repeat parsing is hot. Default: probes parse independently; a Phase 2 follow-up ADR adds the AST memo if it matters. Surfaced because it's a natural seam the performance lens will likely call out.
6. **Skills loader path resolution.** Does the loader follow `~/.codegenie/skills/` symlinks? My read: no (Phase 1 `O_NOFOLLOW` precedent). The security lens probably agrees; the best-practices lens leans on idiomatic Path operations which *do* follow by default. **Resolving toward "no, do not follow" — recording for visibility.**
7. **Should the Phase 2 `ProbeContext.peer_outputs` extension be ADR-gated as a Phase-2 ADR, or rolled into the Phase 1 `ParsedManifestMemo` ADR as a retroactive widening?** My read: new Phase-2 ADR. The `peer_outputs` field is structurally different (it's a Mapping, not a Callable) and `IndexHealthProbe` is its only consumer in Phase 2 — that's the inflection point an ADR should mark.
