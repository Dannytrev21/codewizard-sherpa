# Phase 07 — Add migration task class (Chainguard distroless): Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 7 is the *contract-stability test* for everything that landed in Phases 0–6. The exit criterion is unusually literal: **the diff for this phase touches only new files**. From a best-practices standpoint, that requirement is not a slogan — it is the most rigorous form of regression test the project has, and the right design is the one that lets the existing contracts (`Probe` ABC from `localv2.md §4` / ADR-0007; `Transform` + `RecipeEngine` ABCs from Phase 3; LangGraph `build_*_loop()` factory pattern from Phase 6; Skills loader index from Phase 2 §5.1; gate runner from Phase 5) absorb a second task class without modification.

The right shape is therefore *boring*: drop new probe files into `src/codegenie/probes/` next to the existing ones, drop a new transform file into `src/codegenie/transforms/`, register them with the existing decorators, ship a sibling `build_distroless_loop()` factory in `src/codegenie/graph/` next to `build_vuln_loop()`, and add a `distroless-migration` Skill YAML to the skills catalog. **No new top-level packages. No new ABCs. No new orchestrator.** Composition over inheritance: distroless reuses the existing `RecipeEngine` and `Transform` ABCs by *instantiation*, not subclassing.

The single load-bearing best-practices judgement: the `DockerfileRecipeEngine` (the new engine) and the `DockerfileBaseImageSwapTransform` (the new transform) are *additions* to the existing registries, not new contract surfaces. The recipe-data file format (`catalog/docker/*.yaml`) is an *additional ecosystem* under the same `Recipe` model from Phase 3 — only the `Recipe.engine` enum gets a new value, and that enum is data, not code. Phase 3's `RecipeSelection.reason` enum gets one new value (`unsupported_image_dialect`) — also data, additive.

If anything in this design forces a *code edit* to Phase 0–6, that's the contract speaking, not a design choice — and ADR-0028 mandates we fix the contract, not skip the phase. The candidates for "places where the contract may not extend cleanly" are flagged in §"Open questions for the synthesizer" so the synthesizer can decide whether the existing seams are sufficient or whether one (additive, ADR-recorded) extension point lands.

---

## Conventions honored

- **No LLM in the gather pipeline → ADR-0005 / `production/design.md §2.1`.** `BaseImageProbe` and `ShellInvocationTraceProbe` are deterministic Python — Dockerfile parsing + (for trace) `strace`/`dtruss`/eBPF subprocess output parsing. Same `applies()` / `cache_key()` / `run()` shape as every other probe. Zero `anthropic` / `chromadb` / `sentence-transformers` imports in `probes/` (extends Phase 0's `tools/fence_ci.yaml`).
- **Facts, not judgments → `production/design.md §2.2`.** `BaseImageProbe` reports observed evidence (`registry`, `image_name`, `tag`, `digest`, `parsed_users`, `parsed_entrypoints`, `final_stage_uses_shell`, `final_stage_package_managers`, `multistage: bool`, `stage_count: int`). It does not return `is_distroless_candidate: true` — that judgment lives in the planner subgraph (`select_distroless_recipe`). `ShellInvocationTraceProbe` reports `shell_invocations_count`, `traced_binaries: set[str]`, `network_endpoints_touched: list[Endpoint]`. The conclusion "this service does not need a shell at runtime" is something the gate computes, never the probe.
- **Extension by addition → `CLAUDE.md` / `production/design.md §2.5` / ADR-0007 / ADR-0028.** This is the load-bearing commitment for Phase 7. **No edits to `src/codegenie/probes/base.py`. No edits to the coordinator. No edits to the Skills loader. No edits to the `Transform` or `RecipeEngine` ABCs. No edits to `build_vuln_loop()`. No edits to `cli/remediate.py` or `cli/loop.py`.** The phase ships a new top-level CLI verb (`codegenie migrate`) and a new graph factory (`build_distroless_loop()`) in parallel with the existing ones.
- **Determinism over probabilism for structural changes → `production/design.md §2.4`.** The Dockerfile base-image swap is a recipe-first transform. OpenRewrite's `rewrite-docker` is the named recipe engine; we ship a `DockerfileRecipeEngine` that wraps `rewrite-docker` for the common case and falls through to a hand-rolled `dockerfile-parse`-based engine for shapes `rewrite-docker` doesn't yet cover. LLM enters at the same place it enters in Phase 4 — only when recipe + RAG both miss — through the *same* `FallbackTier` from Phase 4, called from a *new* node in the distroless subgraph. No new fallback path is invented.
- **Organizational uniqueness as data, not prompts → `production/design.md §2.6`.** The CVE-to-image-recommendation lookup table (a roadmap requirement) is a YAML file at `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml`, schema-validated. Replacement catalogs (`apt-get install X` → `chainguard-images/X`, `RUN curl` → `chainguard:wget-package`) are YAML at `src/codegenie/catalogs/distroless/shell_replacements.yaml`. Phase 2 already ships a shell-replacements catalog mechanism (§5.1 conventions catalog); we drop a Docker-scoped one next to it. Phase 4's RAG retriever reads structured catalog entries through the same `applies_to.image_patterns` / `applies_to.cve_patterns` filter shape Phase 2 introduced for skills.
- **Progressive disclosure → `production/design.md §2.7`.** `BaseImageProbe` emits the parsed Dockerfile structure as a slice; the full Dockerfile content stays at `.codegenie/context/raw/dockerfiles/<sha>/Dockerfile`. `ShellInvocationTraceProbe` emits a compact summary; the raw strace output (megabytes) stays at `.codegenie/context/raw/traces/<scenario>/strace.log`. The `RepoContext` artifact indexes; it does not inline.
- **Humans always merge → ADR-0009.** `build_distroless_loop()` has the same `await_human` interrupt node Phase 6's `build_vuln_loop()` has, gated on the same retry-exhaustion + non-retryable-signal conditions. The HITL contract (`HumanRequest` / `HumanDecision` from `docs/contracts/hitl-v0.6.0.json`) is **reused verbatim, not extended**. This is a deliberate test of Phase 6's G18 ("HumanDecision is the Phase 6 / Phase 11 contract").

---

## Goals (concrete, measurable)

- **Public API surface (count): 0 new ABCs. 0 new top-level packages. 0 new decorators.** Two new probe classes (`BaseImageProbe`, `ShellInvocationTraceProbe`) registered via the existing `@register_probe`; one new transform (`DockerfileBaseImageSwapTransform`) registered via the existing `@register_transform`; one new `RecipeEngine` implementation (`DockerfileRecipeEngine`) registered via the existing engine registry; one new graph factory (`build_distroless_loop()`) in `src/codegenie/graph/distroless_loop.py`; one new CLI verb (`codegenie migrate`) at `src/codegenie/cli/migrate.py`.
- **Net-new top-level packages: 0.** All new code lives under existing namespaces: `src/codegenie/probes/`, `src/codegenie/transforms/`, `src/codegenie/recipes/engines/`, `src/codegenie/graph/`, `src/codegenie/cli/`, `src/codegenie/catalogs/distroless/`, `src/codegenie/skills/builtins/distroless/`. The `catalogs/distroless/` and `skills/builtins/distroless/` sub-directories are *data*, not Python packages.
- **Test coverage target: 90% line, 80% branch on new files** (matches Phase 2 §B's `[B]` standard from `02-context-gather-layers-b-g/final-design.md`). Adversarial coverage 100% for Dockerfile parsing (malformed inputs, `FROM scratch`, multi-stage with shared layer names, `ARG` indirection in `FROM`).
- **Cyclomatic complexity ceiling per module: McCabe ≤ 10** (matches Phase 2 standard). Enforced by `ruff` rule `C901` in CI.
- **Lines of plain Python vs framework-coupled code (rough ratio): ≥ 70% plain.** Framework-coupled = anything importing `langgraph`, `aiosqlite`, `temporalio`. Plain Python = probes, transforms, recipe engines, catalogs, validators. The graph factory (`distroless_loop.py`) is the only framework-coupled new file; everything else is stdlib + Pydantic + the project's existing helpers.
- **Token budget contributed by Phase 7 in the gather pipeline: 0.** Same fence-CI rule extension: `probes/` and `transforms/` may not import LLM SDKs. The fallback LLM call inside the distroless graph routes through Phase 4's existing `FallbackTier.run(...)` — no Phase 7 source imports `anthropic`.
- **Phase 6 regression suite: 100% pass** before merge. The full vuln-remediation integration suite from Phases 3/4/5/6 runs unchanged as a hard CI gate (the roadmap's hard-gate requirement). Specifically: `test_remediate_express_e2e.py`, `test_replay_after_kill.py`, `test_hitl_interrupt_and_resume.py`, `test_retry_semantics_parity.py` — all green, untouched.
- **`git diff --name-status` against Phase 6's `main` head, restricted to `src/` and `tests/integration/` and `tests/e2e/`, shows only `A` (added) entries.** No `M` (modified). This is a CI gate (`tools/phase7_additive_gate.sh`) that runs in the Phase 7 merge PR and is automatically retired after merge. It's how we *prove* extension-by-addition rather than asserting it.

---

## Architecture

```
                    codegenie migrate <repo> [--cve <id> | --target distroless]
                                          │
                                          ▼
                  ┌────────────────────────────────────────────┐
                  │  src/codegenie/cli/migrate.py  (NEW)        │
                  │   - re-uses cli/loop.py's option parsing    │
                  │   - calls build_distroless_loop()            │
                  └────────────────────┬────────────────────────┘
                                       │
                                       ▼
                  ┌────────────────────────────────────────────┐
                  │  build_distroless_loop()  (NEW)             │
                  │  src/codegenie/graph/distroless_loop.py     │
                  │   - SAME factory shape as Phase 6's          │
                  │     build_vuln_loop():                       │
                  │       * lazy module-level singleton          │
                  │       * (checkpointer, max_attempts,         │
                  │          force_rebuild)                      │
                  │   - SAME AuditedSqliteSaver (Phase 6's       │
                  │     checkpointer.py, untouched)              │
                  │   - SAME HumanRequest / HumanDecision        │
                  │     (Phase 6's hitl.py, untouched)           │
                  │   - SAME @pure_edge decorator                │
                  │     (Phase 6's edges.py, untouched)          │
                  │   - NEW state model: DistrolessLedger        │
                  │     (extra=forbid, frozen=False)             │
                  │   - NEW nodes/* — analogous shape:           │
                  │       ingest_target → select_recipe →        │
                  │       (rag_lookup | replan_with_phase4) →    │
                  │       apply_recipe → validate_in_sandbox →   │
                  │       record_attempt → emit_artifact         │
                  │     (await_human, escalate — unchanged       │
                  │      structure)                               │
                  └────────────────────┬────────────────────────┘
                                       │
                  ┌────────────────────┼────────────────────────┐
                  │                    │                         │
                  ▼                    ▼                         ▼
        ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────┐
        │ Phase 2 Skills   │  │  Phase 3/4 unmod │  │  Phase 5 unmod      │
        │  loader           │  │   Transform /     │  │  GateRunner +       │
        │  (UNTOUCHED)      │  │   RecipeEngine    │  │  three-retry        │
        │   reads new       │  │   registries —    │  │  (UNTOUCHED) —      │
        │   skills/builtins │  │   register new    │  │  consumes new       │
        │   /distroless/    │  │   impls via       │  │  validators by      │
        │   *.md            │  │   decorator       │  │  registration       │
        └──────────────────┘  └──────────────────┘  └─────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────────┐
              │   NEW probes (registered via @register_probe):       │
              │     src/codegenie/probes/base_image.py     (B-layer)│
              │     src/codegenie/probes/shell_invocation_trace.py  │
              │       (C-layer; consumes Phase 2 C4 contract surface,│
              │        which Phase 2 §"Layer C scope" landed as      │
              │        class+schema only with applies()=False —      │
              │        Phase 7 flips applies() for the migration     │
              │        task and ships the strace/dtruss/eBPF impl)   │
              └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────────┐
              │   NEW transform + engine (registered via decorators):│
              │     src/codegenie/transforms/                         │
              │       dockerfile_base_image_swap.py                   │
              │     src/codegenie/recipes/engines/                    │
              │       dockerfile_engine.py    (wraps rewrite-docker;  │
              │                                hand-rolled fallback)  │
              │     src/codegenie/recipes/catalog/docker/             │
              │       *.yaml                  (recipe DATA — no code) │
              └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────────┐
              │   NEW catalogs + skills (data only):                  │
              │     src/codegenie/catalogs/distroless/                │
              │       cve_image_recommendations.yaml                  │
              │       shell_replacements.yaml                         │
              │       image_dialect_rules.yaml                        │
              │     src/codegenie/skills/builtins/distroless/         │
              │       distroless-node.md                              │
              │       distroless-static.md                            │
              │       distroless-base.md                              │
              └──────────────────────────────────────────────────────┘
```

The shape is intentionally a *mirror* of Phase 6 + Phase 3 + Phase 2 — same layers, same registries, same factory, same HITL contract — with the new files dropped next to the old ones. Reading either subgraph teaches you the other.

---

## Components

### Component 1 — `BaseImageProbe` (B-layer)

- **Purpose:** Parse every `Dockerfile` and `Dockerfile.*` in the repo into structured evidence about base image lineage, multi-stage shape, and final-stage characteristics. Fact-emitting only.
- **Public interface:** Standard `Probe` ABC. Class attributes:
  - `name = "base_image"`
  - `layer = "B"`
  - `tier = "task_specific"`
  - `applies_to_tasks = ["distroless_migration", "vuln_remediation"]` *(vuln remediation reads it too — a base-image CVE is a vuln)*
  - `applies_to_languages = ["*"]`
  - `requires = []`
  - `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/*.dockerfile"]`
  - `timeout_seconds = 30`
  - `cache_strategy = "content"`
  - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`
- **Internal design:** Pure Python using `dockerfile-parse` (the roadmap-named library). Returns the parsed AST for every Dockerfile, normalized into a Pydantic `DockerfileInventory` model. For multi-stage Dockerfiles, identifies the *final* stage (last `FROM ... AS <name>` referenced by `--from` or, absent that, the textually-last `FROM`). Flags `ARG`-indirect FROMs (`FROM $BASE_IMAGE`) with `confidence=medium` and an explicit warning. No conclusions emitted: just structural facts plus parser warnings.
- **Dependencies:** `dockerfile-parse` (new pinned dep; CVE-scanned at install, digest pinned in `tools/digests.yaml`). No subprocess calls. Phase 2's `tools/` wrapper pattern doesn't apply because `dockerfile-parse` is a Python library, not a CLI.
- **Where it lives:** `src/codegenie/probes/base_image.py` (probe + Pydantic models in same file; LOC ceiling 250 with strict `mypy --strict`).
- **Tradeoffs accepted:** `dockerfile-parse` is mature but not perfectly compatible with every BuildKit-specific syntax (heredocs in 1.5+). The probe records `parser_skipped_lines: int` per Dockerfile so silent staleness — the worst failure mode per ADR-0005's reasoning — is visible. If `parser_skipped_lines > 0`, confidence drops to `medium`.

### Component 2 — `ShellInvocationTraceProbe` (C-layer, applies-only-when-task-is-migration)

- **Purpose:** Run the candidate image under representative scenarios and capture which shell commands, binaries, and network endpoints the runtime *actually* touches. The single signal that determines whether distroless is safe ("trace observed 0 shell invocations during smoke test" — the canonical example from `CLAUDE.md`).
- **Public interface:** Standard `Probe` ABC. Class attributes:
  - `name = "shell_invocation_trace"`
  - `layer = "C"`
  - `tier = "task_specific"`
  - `applies_to_tasks = ["distroless_migration"]`
  - `applies_to_languages = ["*"]`
  - `requires = ["base_image", "language_detection", "ci"]`
  - `declared_inputs = ["__image_digest__:<base_image_probe_output>", "**/test/scenarios/*.yaml"]` *(special token: cache invalidates when the parsed image digest from `BaseImageProbe` output changes; second pattern is operator-provided scenario YAMLs at well-known paths)*
  - `timeout_seconds = 600`
  - `cache_strategy = "content"`
- **Internal design:** Phase 2 landed C4's class + schema with `applies() = False` and the impl deferred to "Phase 5" in the Phase 2 design notes — re-read against the roadmap, the impl actually belongs to **Phase 5 for vuln + Phase 7 for migration**: Phase 5 ships the microVM sandbox, and Phase 7's `ShellInvocationTraceProbe` is the *first consumer* that runs a real trace. The probe boots the candidate image inside Phase 5's `run_in_sandbox` chokepoint, runs the operator-provided scenario YAMLs (or a default "smoke" scenario), traces via `strace -f -e trace=execve,connect,openat` (Linux) or `dtruss` (macOS dev) or eBPF (`bcc` `execsnoop`, opt-in via `--trace=ebpf`), parses the trace output into a `RuntimeTraceSummary` model with counts and unique-binary sets. **All trace bytes go to `.codegenie/context/raw/traces/<scenario>/`** under Phase 2's `0600` mode and the OutputSanitizer Pass 5 prompt-injection-marker tagger — trace logs can contain secrets in argv. **Phase 2 §"Layer C scope" decision D8 explicitly anticipated this**: C4 ships class + schema in Phase 2; the implementation lands when a consumer exists. Phase 7 is that consumer.
- **Dependencies:** `strace` (Linux), `dtruss` (macOS, via DTrace), optional `bcc` for eBPF. CLIs added to Phase 0's `ALLOWED_BINARIES` via additive ADR. Phase 5's sandbox is the runtime; Phase 5's `run_in_sandbox` chokepoint with `network="scoped"` (default deny; allowlist per scenario YAML).
- **Where it lives:** `src/codegenie/probes/shell_invocation_trace.py`.
- **Tradeoffs accepted:** Tracing is slow (the roadmap's 84s estimate for "trace 5 scenarios" in `localv2.md §1`). Cache hit rate on this probe is high (image-digest-keyed), but cold-path workflows pay the trace cost up front. The alternative — static analysis of binary calls — was rejected because it produces false positives that block legitimate migrations.

**Cross-reference to Phase 2's contract**: Phase 2's design notes (`02-context-gather-layers-b-g/final-design.md` rows D8/D10) ship `RuntimeTraceProbe` with `applies() = False` and class+schema only. Phase 7 ships a *concrete* `ShellInvocationTraceProbe` that fulfils that contract — but it lives as a **new probe under a new name**, not as an edit to a stubbed Phase 2 file. If Phase 2 shipped C4 as a stub class named `RuntimeTraceProbe` whose `applies()` returns False, Phase 7's new probe sits next to it. The stub stays in place for the schema slice it owns; the implemented probe is a new file. *See Open Question #1.*

### Component 3 — `DockerfileRecipeEngine` (new `RecipeEngine` impl)

- **Purpose:** Apply Dockerfile-shaped recipes (base-image swap, RUN-step rewriting, multi-stage refactor, USER injection). Registered via the existing engine registry; selected when a recipe's `engine: dockerfile` matches.
- **Public interface:** Implements Phase 3's `RecipeEngine` ABC verbatim:
  ```python
  def apply(self, recipe: Recipe, repo: Path, ctx: ApplyContext) -> RecipeApplication:
      ...
  ```
  No subclassing of `NcuRecipeEngine` or `OpenRewriteEngineStub`; **composition over inheritance**. Internal layering:
  - **Primary path: `rewrite-docker`** (OpenRewrite's Docker recipes — roadmap-named in `production/design.md §3` Stage 3 / ADR-0011). Invoked exactly like Phase 3's `OpenRewriteEngineStub`: a pinned jar at `tools/openrewrite/<digest>.jar` with one Dockerfile-specific YAML config per recipe. Requires `java` on PATH; if missing, the engine is registered-but-unavailable (same pattern as Phase 3 — `RecipeSelection(reason="no_engine")`).
  - **Fallback path: hand-rolled `dockerfile-parse` mutator.** For recipe shapes `rewrite-docker` doesn't cover (notably the multi-stage refactor pattern that injects a builder stage and copies from it). The fallback is a small library of AST mutations on `dockerfile-parse`'s output that re-serializes deterministically. Selected when the recipe's `prefers_engine: handrolled` flag is set, or when `rewrite-docker` returns non-zero.
- **Internal design:** Two private methods (`_apply_openrewrite`, `_apply_handrolled`); the `apply()` method is a 15-line dispatcher. Deterministic output: lockfile-canonicalization-equivalent is `dockerfile-canonicalize` (a 30-line helper that strips trailing whitespace, normalizes line endings to LF, sorts only what's safely sort-able which is *nothing in Dockerfiles* — so canonicalization is whitespace-only). Diffs are produced via Phase 3's `git format-patch -1 --stdout` path.
- **Dependencies:** `rewrite-docker` (pinned in `tools/digests.yaml`); `dockerfile-parse`; reuses Phase 3's `git format-patch` invocation pattern.
- **Where it lives:** `src/codegenie/recipes/engines/dockerfile_engine.py`. *Note:* Phase 3 puts engines in `src/codegenie/recipes/engine.py` (one file). For Phase 7, we split engines into `src/codegenie/recipes/engines/__init__.py` (re-exports) + `ncu.py` + `openrewrite_stub.py` + `dockerfile_engine.py`. **This is an additive move only if Phase 3's `engine.py` can stay** — see *Open Question #2*.
- **Tradeoffs accepted:** Multi-engine internal layering (OpenRewrite primary + handrolled fallback) is more complex than a single engine, but the rationale matches Phase 3's `Ncu + OpenRewriteEngineStub` ship-both pattern: the *contract* extends; the *coverage* expands phase-by-phase.

### Component 4 — `DockerfileBaseImageSwapTransform`

- **Purpose:** The Phase 7 transform. Selects a Chainguard image, applies the swap recipe via `DockerfileRecipeEngine`, produces a deterministic diff.
- **Public interface:** Implements Phase 3's `Transform` ABC verbatim. Class attributes:
  - `applies_to_tasks = ["distroless_migration"]`
  - `applies_to_languages = ["*"]` *(the language gating happens at recipe selection, not transform applies — a Node service and a Go service both run through this transform, with different recipes)*
- **Internal design:** Mirrors Phase 3's `NpmPackageUpgradeTransform` step-for-step:
  1. `git worktree add` into `.codegenie/migration/<run-id>/worktree`.
  2. `DockerfileRecipeEngine.apply(recipe, worktree, ctx)` — swaps `FROM` lines, removes `apt-get`/`yum` install steps (those moved into the builder stage), injects `USER nonroot:nonroot` if the recipe declares it.
  3. **No lockfile-equivalent step** for Dockerfile recipes (Dockerfiles don't have lockfiles). The `docker buildx build --output type=oci,dest=/dev/null --no-cache` validator runs in Stage 6 instead. Image digest is captured at build time.
  4. `dockerfile-canonicalize` pass (deterministic serialization).
  5. Commit + `git format-patch -1 --stdout` — identical invocation flags to Phase 3.
- **Dependencies:** Re-uses Phase 3's `git` invocation pattern (`core.hooksPath=/dev/null`, `commit.gpgsign=false`, bot identity). Re-uses Phase 1/2's `run_in_sandbox` for the build validator.
- **Where it lives:** `src/codegenie/transforms/dockerfile_base_image_swap.py`.
- **Tradeoffs accepted:** Multi-stage Dockerfile refactors (one of the roadmap's two named recipes) are harder than a base-image swap; the transform's `recipe.kind` enum gets `multistage_refactor` as a new value, but Phase 7's catalog ships only *two* multistage recipes for narrow shapes (Node `npm-build → distroless-runtime`; Go `go-build → static-distroless`). The catalog grows in later phases.

### Component 5 — `build_distroless_loop()` (LangGraph subgraph)

- **Purpose:** SHERPA-disciplined state machine for the distroless migration loop. Mirrors `build_vuln_loop()` exactly in shape.
- **Public interface:**
  ```python
  def build_distroless_loop(
      *,
      checkpointer: BaseCheckpointSaver,
      max_attempts: int = 3,
      force_rebuild: bool = False,
  ) -> CompiledGraph:
      ...
  ```
  Same signature as Phase 6's `build_vuln_loop()`. Module-level lazy singleton.
- **Internal design:** Ten nodes mirroring Phase 6's, with task-specific names:
  - `ingest_target` (analog of `ingest_cve`) — reads the target Chainguard image recommendation from `catalogs/distroless/cve_image_recommendations.yaml` and the operator's CLI flags.
  - `select_recipe` — same node *name*, same `@pure_edge` shape; selects a Dockerfile recipe from `catalog/docker/*.yaml`.
  - `rag_lookup` — same shape, queries the same vector store from Phase 4 with `task_type="distroless_migration"` instead of `"vuln_remediation"`.
  - `replan_with_phase4` — calls `FallbackTier.run(..., task_type="distroless_migration", ...)` — *requires Phase 4 to accept `task_type` as a routing key.* See *Open Question #3*.
  - `apply_recipe`, `validate_in_sandbox`, `record_attempt`, `await_human`, `emit_artifact`, `escalate` — same shapes; new state model is `DistrolessLedger` (Pydantic, `extra="forbid"`, `frozen=False`).
- **HITL contract:** Reused **verbatim** from Phase 6's `hitl.py`. `HumanRequest` and `HumanDecision` are imported from `codegenie.graph.hitl`. The exported JSON contract (`docs/contracts/hitl-v0.6.0.json`) does not change. This is Phase 6 G18 made operational.
- **Checkpointer:** Reused verbatim from Phase 6's `checkpointer.py`. The `AuditedSqliteSaver` is parametric in `<workflow_id>` only; nothing in it is vuln-specific. Per-workflow SQLite file pattern unchanged.
- **Edges:** Reused `@pure_edge` decorator from Phase 6's `edges.py`. The four predicates (`route_after_select_recipe`, `route_after_rag`, `route_after_attempt`, `route_after_human`) have the same string-literal return shapes; Phase 7 adds *no new* predicate decorator — only new predicate *functions* in `graph/distroless_edges.py`.
- **Where it lives:** `src/codegenie/graph/distroless_loop.py` (factory); `src/codegenie/graph/distroless_state.py` (`DistrolessLedger`); `src/codegenie/graph/distroless_edges.py` (predicates); `src/codegenie/graph/nodes_distroless/` (one file per node, parallel to `nodes/`).
- **Tradeoffs accepted:** Two sibling subgraph trees (`nodes/` for vuln, `nodes_distroless/` for distroless) is the right move per ADR-0022 ("pure duplication for the first two subgraphs; extract shared structure when a third subgraph reveals the pattern; Three Strikes And You Refactor"). Phase 6 was strike one; Phase 7 is strike two; abstraction is deferred until Phase 15's recipe-authoring subgraph lands.

### Component 6 — Catalogs (data only; no code)

- **Purpose:** The roadmap-mandated *CVE-to-image-recommendation lookup table* and a Docker-scoped *shell-replacements catalog*, both as YAML.
- **Files:**
  - `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml` — schema-validated mapping: `affected_image_glob` → `recommended_chainguard_image` with `confidence_band`, `replaces_packages`, `notes`. Closed enum on `confidence_band`. Schema at `_schema.json` (same pattern as Phase 2 §5.3 conventions catalog).
  - `src/codegenie/catalogs/distroless/shell_replacements.yaml` — `original_command_pattern` → `chainguard_package`. Same closed-enum CI gate as Phase 2's `_apply_detector`.
  - `src/codegenie/catalogs/distroless/image_dialect_rules.yaml` — heuristics for grouping image strings into *dialects* (e.g., `debian:bookworm-slim`, `alpine:3.19`, `node:20-bullseye-slim`) so the selector can route to the right recipe.
- **Where it lives:** `src/codegenie/catalogs/distroless/`. **Same package layout pattern as Phase 2's `catalogs/conventions/` and Phase 3's `recipes/catalog/npm/`.**
- **Tradeoffs accepted:** Three new YAML files plus their schemas is more data than minimal — but each file maps to a roadmap-named concept (`CVE-to-image-recommendation lookup table`; shell replacement; image dialect routing). Folding them into one file would hurt readability.

### Component 7 — Skills (data only; markdown with YAML frontmatter)

- **Purpose:** The `distroless-migration playbook` named in the roadmap, as Phase 2-shaped Skills.
- **Files:**
  - `src/codegenie/skills/builtins/distroless/distroless-node.md` — frontmatter: `applies_to: {task_types: [distroless_migration], languages: [javascript, typescript], image_patterns: ["node:*"]}`.
  - `src/codegenie/skills/builtins/distroless/distroless-static.md` — for Go/Rust/static binaries.
  - `src/codegenie/skills/builtins/distroless/distroless-base.md` — generic playbook the others build on.
- **Skills loader:** Phase 2's `discover_skills()` reads `src/codegenie/skills/builtins/**/*.md` already. **Adding three new skill files requires zero loader code changes.** This is the single most direct test that Phase 2 §5.1's "Skills loader" contract extends by addition.
- **Tradeoffs accepted:** The `applies_to.image_patterns` field is *additive* on the `applies_to` block — Phase 2's schema allows `additionalProperties: true` at the `applies_to` level, which makes this clean. If it didn't, *that* would be the contract-extension point. See *Open Question #4*.

### Component 8 — Vector store entry (Phase 4's RAG, additive)

- **Purpose:** Seed the solved-example store with hand-curated distroless migrations so RAG works from day one.
- **Files:** `src/codegenie/skills/builtins/distroless/solved_examples/` — N markdown files in the same shape Phase 4 indexes. Phase 4's vector-DB ingestion script runs over them at build time; no Phase 4 code change.
- **Tradeoffs accepted:** Hand-curated seeds bias the RAG toward familiar shapes — but ADR-0011 explicitly anticipates this ("Cold start: no solved examples until the system has shipped real migrations"), and Stage 7 Learning will write back real examples as soon as the first PR merges.

### Component 9 — Phase 6 regression suite hard gate

- **Purpose:** Prove the contract-extension didn't break the vuln loop.
- **Where it lives:** `.github/workflows/phase7_regression.yml` (additive workflow; doesn't modify the Phase 6 workflow).
- **Internal design:** Runs `pytest tests/integration/ tests/e2e/ -m "phase6"` against Phase 6's existing tests on every Phase 7 PR. The marker `phase6` was added in Phase 6's tests at landing time (`final-design.md §G3` integration test). Failure of *any* Phase 6 test is a hard gate.

### Component 10 — Additive-diff CI gate

- **Purpose:** Mechanically enforce the exit criterion ("the diff for this phase touches only new files").
- **Where it lives:** `tools/phase7_additive_gate.sh` + workflow step in `.github/workflows/phase7_additive.yml`.
- **Internal design:** ~25 lines of bash. `git diff --name-status main...HEAD -- src/ tests/integration/ tests/e2e/ tests/golden/`. If any line starts with `M` or `D`, exit 1 with the offending file path. Whitelist: `tests/conftest.py` for test discovery (PyPI-standard) — but if even that's modified, the PR shouldn't claim the additive label. **The gate runs only on PRs labeled `phase-7-extension-test`**; once Phase 7 merges, the gate is retired (the contract-extension test is one-shot). The gate's source file stays in the repo as documentation of how to re-run it if Phase 8/15 ever wants to repeat the test.

---

## Data flow

End-to-end run for `codegenie migrate ./services/auth --target distroless`:

1. **CLI entry.** `cli/migrate.py` parses options. Tool readiness: `git`, `docker`, `dive`, `dockerfile-parse` (Python lib), `java` (only if `--engine=openrewrite`). **Same readiness pattern as Phase 3's `cli/remediate.py`** — read it; don't copy it. ✱
2. **Load context.** `repo-context.yaml` from `.codegenie/context/` is mmap'd; schema-validated; `IndexHealthProbe.confidence ≥ medium` checked. *Crucially*: `BaseImageProbe` and `ShellInvocationTraceProbe` slices are already in `repo-context.yaml` because Phase 7's probes registered into the same coordinator. The probe contract held (ADR-0007).
3. **Resolve target image.** `catalogs/distroless/cve_image_recommendations.yaml` is read; the `affected_image_glob` matching the repo's parsed base image determines the recommended Chainguard target. If `--cve` is given, the lookup table cross-references; otherwise the operator's `--target` flag wins.
4. **Build `DistrolessLedger`.** Initial state. Same schema-versioned, frozen-version-literal pattern as Phase 6's `VulnLedger` (`schema_version: Literal["v0.7.0"]`).
5. **`ainvoke()` `build_distroless_loop()`.** The LangGraph runtime takes over. **Same checkpointer (`AuditedSqliteSaver`) writing to a new per-workflow SQLite file under `.codegenie/migrate/checkpoints/<workflow_id>.sqlite3`** (different directory, same writer code).
6. **Subgraph traverses** the recipe → RAG → LLM fallback decision chain (ADR-0011), with `validate_in_sandbox` running `docker buildx build` + `dive` (image inspection) inside Phase 5's `run_in_sandbox` chokepoint. Test execution within the new image uses the same `test_execution=True` overlay flag Phase 3 §"Validation gate" introduced.
7. **HITL fires** on retry exhaustion via the *same* `await_human` mechanism Phase 6 shipped. The `HumanRequest`/`HumanDecision` pair is the identical contract; Phase 7 ships *zero* changes to `docs/contracts/hitl-v0.6.0.json`.
8. **Emit artifact.** `.codegenie/migration/<run-id>/migration-report.yaml`, `.codegenie/migration/<run-id>/diff/<recipe-id>.patch`, `.codegenie/migration/<run-id>/raw/{build.log, dive.json, scenarios/*.trace.log}`, `.codegenie/migration/<run-id>/audit/<run-id>.jsonl` chained to Phase 2's audit chain. **Branch:** `codegenie/distroless-migrate/<short-sha>` (different namespace than `codegenie/vuln-fix/`, same `PatchBranchWriter` from Phase 3).
9. **Exit 0** on success; documented exit codes are the same enum Phase 3 published (no new exit codes).

✱ The CLI option-parsing reuse: a small `src/codegenie/cli/common.py` exists (or is added — **see Open Question #5**) for `--engine`, `--allow-policy-violations`, `--allow-stale-feeds`, `--strict`, `--auto-gather` options shared between `remediate` and `migrate`. If Phase 3 didn't extract this, Phase 7 lifts the shared options into `common.py` **without modifying Phase 3's `cli/remediate.py`** — `remediate.py` imports from `common.py` via the existing `from . import` patterns. *Actually:* if Phase 3 inlined options, `migrate.py` re-inlines them too rather than touching `remediate.py`. Duplication > contract violation.

---

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Dockerfile parser hits BuildKit heredoc syntax not supported by `dockerfile-parse` | `BaseImageProbe`'s `parser_skipped_lines > 0` | Probe emits `confidence=medium` + warning; orchestrator continues; the planner subgraph routes to RAG/LLM (recipe miss) since structural facts are incomplete |
| Image dialect doesn't match any rule in `image_dialect_rules.yaml` | Selector returns `reason="unsupported_image_dialect"` *(new enum value; additive)* | Exit 4 cleanly; Phase 4 LLM fallback wraps |
| `rewrite-docker` jar missing or `java` not installed | engine availability check at startup + selector | `reason="no_engine"`; recipe with `engine: dockerfile` falls through to handrolled fallback if `prefers_engine` allows; else exit 4 (same shape as Phase 3 `OpenRewriteEngineStub` unavailable) |
| `docker buildx build` fails inside sandbox | Phase 5 `GateRunner` (unchanged) | three-retry with feedback to `replan_with_phase4` per Phase 6 retry semantics; HITL on exhaustion |
| `ShellInvocationTraceProbe` detects shell invocations in final stage during smoke scenario | `traced_binaries` set contains shell/util binaries the target distroless image doesn't ship | Gate emits `confidence=low`, `failing_signals=["shell_required_at_runtime"]`; subgraph routes to HITL (cannot auto-fix without operator confirmation that adding `wolfi-base` or `chainguard-shell` package is acceptable) |
| Multi-stage Dockerfile with `ARG` indirection in `FROM` | `BaseImageProbe` records `arg_indirect_from: true` | Probe emits `confidence=medium`; planner refuses recipe match (recipe library requires resolved FROM); LLM fallback path |
| `dive` (image inspection tool) reports image layer count regressions | `validate_in_sandbox` Phase 5 gate, new signal `image_layers_delta > 0` | Soft failure: `confidence=medium`, warning, retry once with `prefers_engine: handrolled` for the multistage_refactor recipe |
| CVE in *original* image still present in target image (recommendation table stale) | `validate_in_sandbox` runs `grype` on built image (Phase 2 wrapper, unchanged) | Gate failure with `failing_signals=["cve_delta_positive"]`; HITL after retry exhaustion; operator updates `cve_image_recommendations.yaml` |
| Trace probe times out (slow image boot) | `timeout_seconds=600` | Probe returns `confidence=low`, `errors=["trace_timeout"]`; gather completes; planner uses static-only evidence with degraded confidence |
| Phase 6 regression test fails on a Phase 7 PR | additive workflow `phase7_regression.yml` | Hard merge gate; PR cannot land; investigate which Phase 7 file shadowed/poisoned a Phase 6 import path (extension-by-addition contract violation) |
| Additive-diff gate detects a modified Phase 0–6 file | `phase7_additive_gate.sh` | Hard merge gate; PR cannot land; either the modification is genuinely additive (and the gate is wrong — fix the gate) or the contract failed (per ADR-0028, fix the contract via an additive ADR, not by silencing the gate) |

Typed errors (Phase 0 / Phase 2 pattern carried forward):

- `DockerfileParseError(file, line, raw_message)` — `dockerfile-parse` failure surfaced as a probe warning.
- `ImageRecommendationMiss(observed_image, dialect)` — no entry in `cve_image_recommendations.yaml`.
- `NoChainguardEquivalent(package_name)` — `shell_replacements.yaml` doesn't cover this `apt-get install` argument.
- `TraceUnsupportedOnPlatform(platform)` — `strace`/`dtruss`/`bcc` all unavailable on the host.
- `DockerfileEngineFallback(reason)` — `rewrite-docker` punted; logged before handrolled-fallback fires.

---

## Resource & cost profile

- **Tokens per run: 0 in the gather and execute pipelines.** LLM cost lands only when `replan_with_phase4` fires, exactly as in vuln remediation. Fence-CI extended to deny LLM-SDK imports in `probes/`, `transforms/`, `recipes/`, `catalogs/`.
- **Wall-clock targets** (Node fixture, distroless target, M-series Mac / 4-vCPU Linux runner):
  - Hot path (RepoContext cached, recipe hit, image cached, traces cached): **p50 ≤ 60 s, p95 ≤ 180 s** — dominated by `docker buildx build` cold layers.
  - Cold path (full trace + full build + small test suite): **p50 ≤ 5 min, p95 ≤ 10 min.**
  - `BaseImageProbe` alone: **p50 ≤ 1 s** (pure Python parse).
  - `ShellInvocationTraceProbe` alone: **p50 ≤ 90 s for 5 scenarios** (matches `localv2.md §1` budget).
- **Per-worker memory:** Python ≤ 350 MB. Docker daemon memory is the operator's burden (typical: 2 GB allocation).
- **Disk:** `.codegenie/migration/<run-id>/` ≤ 200 MB typical (includes built image references, not the image itself). `.codegenie/context/raw/traces/` ≤ 50 MB per gather.
- **Network:** Chainguard registry pull during sandbox build (`docker pull cgr.dev/chainguard/<image>`). No other Phase 7 outbound network. Registry credentials are operator-side via `docker login`.
- **New `ALLOWED_BINARIES` entries (one additive ADR each):** `docker`, `dive`, `strace` (Linux), `dtruss` (macOS), `java` (already added in Phase 3 for OpenRewriteStub). **New Python deps:** `dockerfile-parse` pinned in `pyproject.toml`.
- **OpenRewrite Maven mirror:** **Still not introduced.** The `rewrite-docker` jar is pinned at `tools/openrewrite/<digest>.jar` per Phase 3's stub-jar pattern. Phase 7 grows the pinned-jar set by one (Docker-specific recipes); full Maven resolution stays deferred.

---

## Test plan

Test pyramid: lots of unit, fewer integration, very few e2e. Goldens where output is deterministic; property tests where behavior is invariant; the Phase 6 regression suite as the *non-negotiable hard gate*.

### Unit tests (`tests/unit/`)

- `tests/unit/probes/test_base_image.py` — ≥ 14 tests:
  - Single-stage Dockerfile parsing.
  - Multi-stage with named stages and `--from=builder` references.
  - `ARG`-indirect `FROM` flagged as `confidence=medium`.
  - `FROM scratch` handled correctly.
  - BuildKit heredoc syntax → `parser_skipped_lines > 0` + `confidence=medium`.
  - Malformed Dockerfile (truncated) → typed `DockerfileParseError` + probe warning, no crash.
  - `applies_to_tasks` correctly returns true for `distroless_migration` and `vuln_remediation`.
  - `declared_inputs` glob picks up `Dockerfile`, `Dockerfile.prod`, `app.dockerfile`.
  - `cache_key()` invalidates on Dockerfile content change.
  - **Intent test** (CLAUDE.md Rule 9): `test_base_image_emits_facts_not_judgments` — asserts the slice's keys are observable evidence terms, not conclusion terms (no `is_distroless_candidate`, no `safe_to_migrate`).
- `tests/unit/probes/test_shell_invocation_trace.py` — ≥ 10 tests including fixture-replayed strace logs (no real subprocess); typed error `TraceUnsupportedOnPlatform` raised when no tracer is available; `confidence` correctly degrades on partial scenario coverage; sanitizer Pass 5 strips potential prompt-injection markers from raw trace bytes before they reach `repo-context.yaml`.
- `tests/unit/recipes/engines/test_dockerfile_engine.py` — ≥ 12 tests:
  - Dispatch between `rewrite-docker` primary and handrolled fallback.
  - `prefers_engine: handrolled` short-circuits OpenRewrite.
  - `java` missing → `RecipeApplication(exit_code=non_zero, stderr=...)` rather than crash.
  - Diff is byte-deterministic across 5 runs (canary test).
  - Multi-stage refactor recipe produces semantically correct multi-stage output (golden file).
- `tests/unit/transforms/test_dockerfile_base_image_swap.py` — ≥ 8 tests: standard `Transform` ABC compliance, worktree handling, dirty-tree refusal, branch naming, format-patch determinism.
- `tests/unit/catalogs/test_distroless_catalogs.py` — schema validation on `cve_image_recommendations.yaml`, `shell_replacements.yaml`, `image_dialect_rules.yaml`; closed-enum CI gate (rejects unknown `confidence_band`).
- `tests/unit/graph/test_distroless_state.py` — `DistrolessLedger` `extra="forbid"` rejection; runtime id()-diff hook fires on in-place mutation; `schema_version: Literal["v0.7.0"]` pin.
- `tests/unit/graph/test_distroless_edges.py` — every `@pure_edge` predicate × every reachable branch.

### Integration tests (`tests/integration/`)

- `tests/integration/test_migrate_node_e2e.py` — express fixture with a `node:20-bullseye-slim` base image; expected output: PR-shape diff swapping to `cgr.dev/chainguard/node:20`. Golden patch.
- `tests/integration/test_migrate_static_go_e2e.py` — minimal Go fixture; multi-stage refactor recipe; golden patch.
- `tests/integration/test_migrate_handrolled_fallback.py` — fixture for which `rewrite-docker` punts; assert handrolled fallback path executes and produces valid output.
- `tests/integration/test_migrate_shell_required_hitl.py` — fixture whose smoke scenario invokes `sh -c` at runtime; `ShellInvocationTraceProbe` flags it; gate fails; `await_human` interrupt fires; mocked `HumanDecision(action="abort")` aborts cleanly.
- `tests/integration/test_migrate_recipe_miss_llm_fallback.py` — fixture with no recipe match; `replan_with_phase4` fires; recorded LLM response via `pytest-recording` per Phase 4's pattern.
- `tests/integration/test_migrate_replay_after_kill.py` — SIGKILL during `validate_in_sandbox`; resume produces byte-identical final state (Phase 6 G2 analog).
- **The hard gate**: `tests/integration/test_phase6_unchanged.py` — re-runs every Phase 6 test verbatim. Failure = merge block.

### E2E tests (`tests/e2e/`)

- `tests/e2e/test_e2e_node_vuln_base_image_migration.py` — the roadmap-required scenario: "migrates a Node.js service with a vulnerable base image to a Chainguard distroless image." Single test, single fixture, end-to-end. The diff is reviewed; the built image's CVE count is asserted lower.

### Golden files (`tests/golden/`)

- `tests/golden/distroless_loop_topology.json` — canonical JSON form of `build_distroless_loop().get_graph().to_json()`. CI gate. (SVG committed at `docs/phases/07-migration-task-class/distroless_loop.svg` but **not** a CI gate — same posture as Phase 6 G17.)
- `tests/golden/dockerfile_swap_node20.patch` — golden patch for the Node express fixture.
- `tests/golden/dockerfile_multistage_go.patch` — golden patch for the Go multistage refactor.

### Property tests (`tests/property/`)

- Property test on `DockerfileRecipeEngine.apply()`: for any well-formed Dockerfile, applying a base-image-swap recipe is idempotent (apply twice → same diff).
- Property test on `BaseImageProbe`: the parsed `final_stage_*` fields are functions of the textually-final `FROM` directive, regardless of comment density or whitespace.

### Adversarial tests (`tests/adversarial/`)

- Dockerfile with embedded null bytes.
- 100 MB Dockerfile (probe must refuse with hard size cap).
- Dockerfile whose `FROM` is `localhost:5000/<long-redirect-chain>` (image-name parser must not crawl).
- Recipe YAML with reflective fields (`!!python/object`) — `safe_yaml.load` from Phase 1/2 already handles this; assert it does.

### CI structure

- `.github/workflows/phase7.yml` — runs unit + integration + property + adversarial on every PR.
- `.github/workflows/phase7_regression.yml` — Phase 6 hard regression gate (`pytest -m phase6`).
- `.github/workflows/phase7_additive.yml` — `phase7_additive_gate.sh` (additive-diff gate; runs only on PRs labeled `phase-7-extension-test`).

---

## Risks (top 3–5)

1. **The contract doesn't extend cleanly somewhere we didn't predict.** The whole phase rests on extension-by-addition holding. The most likely surprise: a field on `RecipeSelection.reason` or `Recipe.engine` is *typed as a closed `Literal`* in Phase 3, which means *adding* a new value forces an edit to the `Literal` definition. That's a code change to a Phase 0–6 file. **Mitigation:** audit the closed-enum sites in Phases 3–6 *before* Phase 7 starts; if any block extension, surface as a Phase 7 prep ADR (additive: introduce a discriminated-union pattern or a string-backed enum with an "extending values is additive" policy). *See Open Question #6.*
2. **`ShellInvocationTraceProbe` is flaky on CI runners.** Tracing requires elevated privileges (`CAP_SYS_PTRACE` for `strace`); GitHub Actions runners may not grant this. **Mitigation:** the probe's `applies()` returns False when the platform lacks tracer capability; an explicit `--require-trace` flag forces the run and errors loudly when tracing is impossible. CI matrix includes one self-hosted Linux runner with capabilities granted (per Phase 5's sandbox-stack provisioning).
3. **OpenRewrite's `rewrite-docker` coverage is narrower than the roadmap implies.** The roadmap names it; reality is that `rewrite-docker` covers base-image swaps well and multistage refactors poorly. **Mitigation:** the engine layering ships the handrolled fallback *from day one*, and both recipes ship in the catalog. Phase 7 doesn't fail if `rewrite-docker` covers only one of the two recipes — but if it covers *neither*, the engine is operationally `OpenRewriteEngineStub`-level coverage rather than the broader engine the roadmap implies.
4. **`docker buildx build` inside Phase 5's sandbox is heavy.** Docker-in-Docker on macOS is slow; Firecracker on Linux is faster but has its own buildx integration headaches (per ADR-0019's deferred status). **Mitigation:** the slow-path budgets above are honest about this. If buildx-in-sandbox proves unworkable, the fallback is to run buildx on the host with a content-addressed cache and rely on the diff (not the built image) as the validation artifact for Phase 7; Phase 12 deepens validation. This is a *capability degradation*, not a contract change.
5. **The `cve_image_recommendations.yaml` table goes stale.** Chainguard publishes new images; the mapping becomes wrong. **Mitigation:** `cve_image_recommendations.yaml` carries a `last_verified` timestamp per row; the migration loop emits a `confidence=medium` warning when a row's `last_verified > 90 days`. A future Phase-14 cron can refresh it. The file is a *human-curated catalog* in Phase 7 — that's the right Phase-7 shape; automation comes later, additively.

---

## Acknowledged blind spots

- **No multi-Dockerfile workflow.** If a repo has `Dockerfile` and `Dockerfile.prod` and `Dockerfile.test`, Phase 7 treats them independently — one migration run produces one diff per Dockerfile. That's the simple, predictable shape; whether the operator wants them migrated together is a Phase-12-style cross-repo planning concern.
- **No Helm chart / k8s manifest awareness.** The Chainguard image swap may need a corresponding chart update (`image.repository`, `image.tag`). Phase 7 doesn't ship Helm-aware probes/transforms. Surfaced as a `requires_human_review: chart_update_needed` warning when `BaseImageProbe` finds a `Chart.yaml` in the repo with a matching image reference; otherwise silent. Phase 8+ (or a future migration sub-phase) lands chart-aware extension probes.
- **No Wolfi/Alpine image-package mapping verification.** The shell-replacements catalog says "`apt-get install curl` becomes `cgr.dev/chainguard/curl`" — but we don't verify that `chainguard/curl` actually exists in the registry at recipe-selection time. A `RegistryProbe` (additive, future) would catch this; in Phase 7 we accept the risk and let `validate_in_sandbox`'s `docker pull` failure handle the case.
- **Dockerfile multistage refactor is more art than recipe.** The hand-curated recipes cover Node and Go; languages without one in v0.7.0 fall to LLM fallback. That's by design — Phase 15 grows the catalog from solved LLM examples. But it means Phase 7's "deterministic-first" property is *less* prominent on first-mover languages than it was for npm vuln remediation in Phase 3.
- **No load testing of the parallel `build_*_loop()` factories.** Both factories share a module-level singleton pattern; if one worker process compiles both graphs (Phase 8's supervisor will), the cold-start cost is paid twice. Negligible at one process; could matter when Phase 9's Temporal workers multiply. Surface for Phase 9's load testing.
- **The additive-diff CI gate is a one-shot test.** After Phase 7 merges, the gate is retired. Future task classes (Phase 15's recipe-authoring) get no automated "did we accidentally edit Phase 0–6?" check. **Mitigation:** the gate script stays in `tools/` as documentation; teams introducing future task classes are expected to re-instate it on their own PR labels. The discipline is human; the gate is a one-time enforcement.

---

## Open questions for the synthesizer

1. **`RuntimeTraceProbe` vs `ShellInvocationTraceProbe` naming.** Phase 2's design landed a stubbed `RuntimeTraceProbe` (C4 class + schema, `applies()=False`, impl deferred). Phase 7 needs the *implementation* but I've named it `ShellInvocationTraceProbe` because the migration-specific signal is shell invocation. The choices are:
   - **(a)** Implement the deferred `RuntimeTraceProbe` in place — fastest, but touches Phase 2's file (modifies `applies()` from False to a real check). That's a Phase 0–6 edit and **violates Phase 7's exit criterion** even though Phase 2 anticipated the change.
   - **(b)** Ship a new `ShellInvocationTraceProbe` as designed — additive; leaves the Phase 2 stub in place forever as a no-op.
   - **(c)** Phase 2's stub is a *contract surface*, and Phase 7 ships the implementation as a new class registered under the same `name = "runtime_trace"` — Python's MRO and the registry's last-registration-wins semantics make this work, but it relies on import order. Fragile.
   I picked **(b)** in this design — additive, predictable, but leaves a dead stub. The synthesizer should decide whether the dead stub is acceptable or whether Phase 7 retires the stub via an explicit additive ADR ("stubbed probes are retired by adding a sibling probe and removing the stub in a follow-up PR — the follow-up PR is permitted to be the *only* Phase 0–6 edit Phase 7 makes, recorded as ADR-P7-XXX").

2. **`src/codegenie/recipes/engine.py` (single file) vs `src/codegenie/recipes/engines/` (package).** Phase 3 inlines `NcuRecipeEngine` and `OpenRewriteEngineStub` in a single `engine.py`. Adding `DockerfileRecipeEngine` to that same file is *modifying* Phase 3's file. The alternative is creating `src/codegenie/recipes/engines/` as a package and putting *only* the new engine there, leaving Phase 3's `engine.py` untouched. Imports from outside the package read `from codegenie.recipes.engine import RecipeEngine` (unchanged) and `from codegenie.recipes.engines.dockerfile_engine import DockerfileRecipeEngine` (new). This is awkward but additive. **Synthesizer call:** accept the awkward layout, or treat splitting a one-file module across two paths as cosmetic and grant a one-line edit?

3. **Phase 4's `FallbackTier.run()` signature.** Phase 4 was designed for vuln remediation; does its `run()` take a `task_type` keyword arg or is it implicit? If implicit, Phase 7 needs to *modify Phase 4* to route by task type, which violates the exit criterion. If explicit (the task type is a parameter that Phase 4 already accepts), Phase 7 just passes a new value. **Synthesizer call:** confirm by reading Phase 4's final-design.md; if `task_type` isn't already a parameter, that's the additive-extension point and needs a Phase-7-as-Phase-4-extension ADR.

4. **Phase 2's skill schema and `applies_to.image_patterns`.** The skill-loader schema needs to allow an `image_patterns` field on `applies_to`. If Phase 2's schema has `additionalProperties: true` at that level, this is a free addition (the field is just data). If Phase 2's schema has `additionalProperties: false`, Phase 7 must *modify* the schema. **Synthesizer call:** confirm Phase 2's stance; if it's closed, this is an additive-extension ADR.

5. **`src/codegenie/cli/common.py`** for shared options between `remediate` and `migrate`. If Phase 3 didn't extract this, Phase 7 either (a) inlines options in `migrate.py` (duplication, but additive), or (b) extracts to `common.py` and updates `remediate.py` (clean, but modifies Phase 3's file). I picked (a) in this design. The synthesizer may prefer (b) as a one-off acceptable edit; that's a discipline call.

6. **Closed-`Literal` extension points across Phases 3–6.** The most likely place the contract *doesn't* cleanly extend is wherever a `Literal[...]` enum lives in a Phase 0–6 type. Examples that need an audit:
   - `Recipe.engine: Literal["ncu", "openrewrite"]` — Phase 7 needs `"dockerfile"`.
   - `RecipeSelection.reason: Literal[...]` — Phase 7 may need `"unsupported_image_dialect"`.
   - `VulnLedger.last_engine: Literal["recipe","rag","phase4_llm"]` — does `DistrolessLedger` re-use this or define its own?
   - `GraphEvent.kind: Literal["enter","exit","decision","interrupt","resume"]` — does Phase 7 need any new event kinds?
   If any of these are closed `Literal`s, *adding* a value is a Phase 0–6 source edit. The fix per ADR-0028 is to make these *open* (string-backed enums with an additive policy, or discriminated unions) — but the *first time* Phase 7 hits one, that's the contract-extension point and an additive ADR. **The synthesizer should treat this as the most important review item before story decomposition.**

7. **Where does the Chainguard registry credential live?** Phase 7 needs `docker login` against `cgr.dev`. Phase 0/2 introduced `~/.codegenie/config.yaml` for operator-side config. Does Chainguard auth live there, or is it OS-keychain (`docker login` writes to `~/.docker/config.json` already)? The cleanest answer is "operator's `~/.docker/config.json` — Phase 7 doesn't manage it, doesn't read it, doesn't store it." Confirm.

8. **Phase 5's `run_in_sandbox` with `docker buildx`.** ADR-0019 leaves the sandbox stack deferred. `docker buildx` inside Docker-in-Docker is the standard macOS posture; inside Firecracker it's more involved. Phase 7's e2e test needs *some* sandbox stack to commit to. If ADR-0019 is still deferred at Phase 7 start, do we (a) accept the dev-only macOS DinD posture as Phase 7's only e2e platform, or (b) Phase 7 forces ADR-0019 resolution? I lean (a) — ADR-0019 stays deferred until production-data-driven Phase 16 — and Phase 7's CI runs the Linux variant with DinD as well.
