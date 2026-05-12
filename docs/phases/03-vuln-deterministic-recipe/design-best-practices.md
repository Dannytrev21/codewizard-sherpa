# Phase 3 — Vuln remediation: deterministic recipe path: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12
**Companions (parallel):** `design-performance.md`, `design-security.md`
**Source of truth for scope:** [`docs/roadmap.md` "Phase 3"](../../roadmap.md), `docs/production/design.md §2`–§3 (load-bearing commitments), [ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [ADR-0009](../../production/adrs/0009-humans-always-merge.md), [ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md), [ADR-0028](../../production/adrs/0028-task-class-introduction-order.md), prior phase finals.

---

## Lens summary

Phases 0–2 built the spine and populated it with **probes** (deterministic, cacheable, additive). Phase 3 introduces the **second** load-bearing contract — **transforms**. A transform reads `RepoContext` + Skills, chooses a recipe, applies it, and writes a diff to a local branch. The exit criterion is that the diff, when applied, installs cleanly and passes the repo's tests.

The best-practices bet, identical in spirit to Phase 1's bet on the probe ABC: **the Phase 3 `Transform` ABC is the budget, not a starting point.** Get the contract right once; Phase 4 (LLM fallback), Phase 5 (sandbox), Phase 7 (migration task class), Phase 9 (Temporal), Phase 15 (agentic recipe authoring) all extend it by addition. If Phase 4 has to *edit* `Transform`, the Phase 3 contract was wrong.

Concretely the lens means:

- A single new public ABC (`Transform`) modeled byte-for-byte on Phase 1's `Probe` ABC — same registry, same `applies()`/`run()` split, same `declared_inputs`/`applies_to_*` declarations, same typed-output contract, same wave-graph dispatch. The Probe ABC is the proven shape; Phase 3 must not invent a new one when the old one fits.
- **Three boring components** wired together: a `cve_feed` package (NVD/GHSA/OSV → one canonical `Advisory` model), the `Transform` ABC + a single `npm_package_upgrade` recipe, and a small linear orchestrator (`remediate <repo> --cve <id>`) — plain Python, no LangGraph (deferred to Phase 6 per roadmap), no agent SDK (Phase 4), no Temporal (Phase 9).
- **`npm-check-updates` (`ncu`) is the recipe engine for Phase 3.** OpenRewrite's npm support is immature and JVM-heavy; we add a JVM-runtime dependency only when the alternative is materially worse, and here it isn't. ADR-gated, surfaced. OpenRewrite stays a *future* recipe-engine option for breaking-change/codemod scenarios (Phase 4 territory anyway).
- **Skills loader from Phase 2 is reused, not re-implemented.** The Skill selection axes (`task_types × languages`) extend by addition to include `applies_to.cve_patterns` — a small additive field in the YAML frontmatter and its JSON Schema, with backwards-compatible defaults. That's an additive change to the *catalog schema*, not the loader code.
- **Validation gate** is **a sibling contract**, not a third axis on `Transform`. `Validator` is its own ABC (build / install / test). Probes describe a repo. Transforms change a repo. Validators verify a repo. Three nouns; three contracts; each idiomatic Python.
- **Test pyramid wide at the base.** Every recipe ships a **golden diff** (the recipe writes a real diff — that's testable byte-for-byte). Every `Advisory` parser ships against frozen feed snapshots committed under `tests/fixtures/cve_feeds/`. The fixture-repo portfolio is a directory of git-bundle files (`.bundle`), unpacked into `tmp_path` per test, giving deterministic byte-equivalent repos without submodules or live network.

What I deprioritize, explicitly:

- **Concurrency.** Phase 3 is single-repo. The orchestrator is a sync linear `for stage in stages: stage()` function. Phase 6/9 will reopen this; Phase 3 is where simplicity buys cognitive load reduction more than throughput buys time.
- **Polyglot recipe runtime.** No JVM. No OpenRewrite. `ncu` (Node CLI, already on developer machines) covers the Phase 3 exit criterion. OpenRewrite is documented as a future addition behind the `RecipeEngine` interface (which `NcuRecipeEngine` implements) — extension by addition.
- **CVE-feed streaming.** A nightly snapshot pull (Phase 14) is out of scope; Phase 3 reads frozen feed files (committed test fixtures) and live API calls only via an explicit `codegenie cve sync` subcommand the user runs.
- **Adversarial perfection on the CVE feed.** Phase 1's in-process caps + sanitizer + `safe_yaml` extend to the new JSON parsers. No new sandbox stratum.

---

## Conventions honored

- **No LLM in this loop** ([ADR-0005](../../production/adrs/0005-no-llm-in-gather-pipeline.md), `production/design.md §2.1`) → Phase 3 introduces the *transform* contract, and the same ban applies. The `Transform` ABC's docstring carries the prohibition verbatim. The Phase 0 `fence` CI job is extended with the Phase 3 import closure: no `anthropic`, no `langgraph`, no `chromadb`, no `sentence-transformers` may appear under `src/codegenie/transforms/`, `src/codegenie/cve/`, or `src/codegenie/recipes/`. Phase 4 unblocks LLM imports inside its own new `src/codegenie/planning/` package — never inside the deterministic packages Phase 3 lands.
- **Facts, not judgments** (`production/design.md §2.2`) → The `Advisory` model emits `package_name`, `affected_versions`, `patched_versions`, `severity_score`, `provenance: [{source, id, fetched_at}]`. It does **not** emit `should_remediate: true`. The selector emits `matched_recipe: <id>` or `no_recipe_match` — never `safe_to_apply: true`. The `TransformOutput` emits `diff_path`, `branch_name`, `files_changed`, `confidence`, `errors`; it does not write `success: true`. **Validation outcome is the validator's job** and lives in `ValidatorOutput`, not `TransformOutput`.
- **Honest confidence** (`production/design.md §2.3`) → Every transform emits `confidence: high | medium | low` and `warnings: [...]`. A `ncu` upgrade that resolves to the requested patched version with no peer-dep warnings is `high`. A bump that produced peer-dep warnings but installed clean is `medium` (validator will weigh in). A bump that required `--force` is `low` and refuses to apply without explicit operator opt-in. Same shape as probe confidence.
- **Extension by addition** ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), `production/design.md §2.5`) → Phase 3 lands **three new top-level packages** under `src/codegenie/` (`cve/`, `transforms/`, `recipes/`) plus one new package under `src/codegenie/validation/`. **Zero edits to** `coordinator.py`, `cache/`, `probes/`, `tools/`, `skills/loader.py`, `output/`, `schema/validator.py`, `exec.py`. Two ADR-gated *additive* changes: (1) the Phase 2 Skills YAML frontmatter schema gets an optional `applies_to.cve_patterns` field (defaulted to `["*"]` so every existing Skill keeps validating); (2) `ALLOWED_BINARIES` adds `npm` and `ncu` with one ADR per binary, same precedent as Phase 1's `node`. The Phase 0 `test_probe_contract.py` snapshot test stays green because no probe code changes.
- **Determinism over probabilism for structural changes** (`production/design.md §2.4`) → Recipes are deterministic. `ncu` resolves to a specific version given a specific `package.json` + lockfile + `--target patch|minor|major` flag. The selector is a flat YAML-driven decision table. The orchestrator is `for stage in stages: stage()` with no retries beyond what ADR-0014 mandates (and ADR-0014's three-retry behavior is owned by Phase 5's gate machinery, not Phase 3). Phase 3 does not retry.
- **Humans always merge** ([ADR-0009](../../production/adrs/0009-humans-always-merge.md)) → Phase 3 stops at a local branch. No `git push`. No GitHub API surface. The orchestrator's final stage is "writer wrote `codegenie/vuln-fix/<cve-id>-<short-sha>`; rebase onto your default branch and `git push` yourself." Phase 11 introduces the PR opener; Phase 3 must not anticipate it.
- **Recipe → RAG → LLM-fallback** ([ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)) → Phase 3 implements **only the recipe arm**. The selector's behavior on no-match is to emit `TransformOutput(confidence="low", errors=["no_recipe_match"], skipped=True)` and exit cleanly. **No fallback is wired in Phase 3** — this is what Phase 4 adds, and Phase 4 must do so without editing the Phase 3 selector. Concretely: the selector returns `Optional[Recipe]`; Phase 4 wraps the selector with a chain that consults RAG / LLM on `None`. The selector itself stays the same file.
- **Organizational uniqueness as data, not prompts** (`production/design.md §2.6`) → Recipes are YAML files under `src/codegenie/recipes/catalog/npm/`. The selector is a YAML-driven decision table (`src/codegenie/recipes/selector.yaml`). Skills frontmatter (Phase 2 loader, extended schema) carries the per-org overrides ("Acme always bumps to latest *minor*; never major without ADR"). Code reads catalogs; catalogs are data.
- **Progressive disclosure** (`production/design.md §2.7`) → `repo-context.yaml` is **read-only** for Phase 3 (probes wrote it; transforms read it). The transform writes its own artifacts under `.codegenie/remediation/<run-id>/`: a `remediation-report.yaml` summary, a `diff/<recipe-id>.patch` patch file (the actual git diff, on disk, the golden of golden files), a `raw/` directory with `ncu` JSON output, npm install logs, and the validator's pytest/junit XML. **The remediation report indexes; it does not inline.** Same shape as `repo-context.yaml`.
- **Cost observability** (`production/design.md §2.9`, [ADR-0024](../../production/adrs/0024-cost-observability-end-to-end.md)) → Phase 3's cost is zero LLM tokens by construction. Wall-clock per stage is recorded in the same audit-anchor format Phase 0 ships (`.codegenie/remediation/<run-id>/audit.json`). Phase 13 will read this when it lands.

---

## Goals (concrete, measurable)

- **Public API surface (count):** One new ABC (`Transform`), one new ABC (`Validator`), one new registry decorator (`@register_transform`), one new Pydantic model family (`Advisory`, `Recipe`, `TransformInput`, `TransformOutput`, `ValidatorOutput`), one new CLI subcommand tree (`codegenie remediate`, `codegenie cve sync`, `codegenie recipes list`). The Probe ABC, Skills loader, and `RepoContext` schema are unchanged.
- **New top-level packages:** **4** — `src/codegenie/cve/`, `src/codegenie/transforms/`, `src/codegenie/recipes/`, `src/codegenie/validation/`. Each siblings the existing `probes/`. (This is the largest new-package footprint since Phase 0. Surfaced because best-practices says fewer is better; the four are non-negotiable because they are four nouns: advisories, transforms, recipes, validators. Collapsing them couples lifecycles that diverge in Phase 4–Phase 7.)
- **Net new Python files in `src/`:** ~22 modules, ~2500 LOC target, 3500 hard ceiling. Breakdown: `cve/` (3 parsers + 1 model + 1 store = 5 modules); `transforms/` (ABC + registry + context + 1 npm transform = 4); `recipes/` (engine ABC + ncu engine + catalog loader + selector = 4); `validation/` (ABC + 3 validators: install / build / test = 4); plus `cli/remediate.py`, `cli/cve.py`, `cli/recipes.py` and the orchestrator `transforms/coordinator.py` (5).
- **Net new lines of test code:** target ≥ 1.5× source LOC (~3750–5250 LOC). The ratio is the convention.
- **Test coverage target:** **90% line / 80% branch** on the new packages; **95% line / 90% branch** on `transforms/` (ABC + registry + coordinator). Ratchet from Phase 2's 90/80 floor across the codebase stays in place.
- **Cyclomatic complexity ceiling:** **McCabe ≤ 10 per function**, ruff `C901` enforced. The CVE-feed normalizer is the function most likely to push this; budget split into per-source helpers if it exceeds.
- **Plain Python vs framework-coupled ratio:** ≥ 95% plain Python under the new packages. `click` only at `cli/*`, `pydantic` only at model boundaries; the orchestrator and selector are stdlib.
- **External tool surface added to `exec.ALLOWED_BINARIES`:** **2** (`npm`, `ncu`). One ADR per binary, Phase 1 precedent.
- **Golden coverage:** **Every recipe ships a golden diff**. `tests/golden/transforms/<recipe-id>/<fixture-name>/expected.patch`. CI diff fails on drift; `pytest --update-goldens` regenerates.
- **Wall-clock targets (advisory):**
  - Cold remediation on 1k-file Node fixture (read `RepoContext` cache hit + `ncu` upgrade + npm install + test suite): **p50 ≤ 90 s, p95 ≤ 180 s.** Dominated by `npm install` (~30–60 s) and the repo's test suite.
  - Selector + recipe application alone (no install, no test): **p50 ≤ 2 s.**
- **Tokens per run: 0.** `fence` CI extended.

---

## Architecture

```
                              codegenie remediate <repo> --cve <id>
                                              │
                                              ▼
                          ┌──────────────────────────────────────┐
                          │  Phase 0 CLI entry (click)            │   ← unchanged
                          │  + new subcommand group `remediate`,  │
                          │    `cve`, `recipes` (Phase 1 pattern) │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 1: Load context                │
                          │  - read .codegenie/context/           │
                          │    repo-context.yaml (Phase 1/2)      │
                          │  - validate schema (Phase 0)          │
                          │  - if stale or missing → invoke       │
                          │    Phase 0/1/2 gather as a function   │
                          │    call (NOT a separate process)      │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 2: Resolve Advisory             │
                          │  - cve.store.get(cve_id) →             │
                          │    Advisory                           │
                          │  - if miss: cve.fetch.{nvd,ghsa,osv}   │
                          │    (only on explicit user opt-in)     │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 3: Select Recipe                │
                          │  - recipes.selector.select(             │
                          │      repo_ctx, advisory, skills)      │
                          │  - returns Optional[Recipe]           │
                          │  - on None → exit cleanly (Phase 4    │
                          │    wraps with RAG/LLM fallback)       │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 4: Apply Transform              │
                          │  - transforms.npm_package_upgrade     │
                          │    .NpmPackageUpgradeTransform.run()  │
                          │  - reads RepoContext + Recipe +       │
                          │    Advisory                           │
                          │  - writes diff + checked-out branch   │
                          │    on a worktree (NEVER on user's     │
                          │    working tree)                      │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 5: Validate                     │
                          │  - validation.install.NpmInstall      │
                          │  - validation.test.NpmTest             │
                          │  - validation.build.NpmBuild           │
                          │    (only if package.json#scripts.build)│
                          │  - each emits ValidatorOutput          │
                          │  - one failure → mark report failed   │
                          │    but DO NOT delete branch            │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Stage 6: Write report + branch       │
                          │  - .codegenie/remediation/<run-id>/   │
                          │    ├── remediation-report.yaml         │
                          │    ├── diff/<recipe>.patch             │
                          │    ├── raw/{ncu.json, install.log,     │
                          │    │       test.xml, audit.json}       │
                          │    └── runs/<utc>.json                 │
                          │  - branch left checked out OR named   │
                          │    + sha-recorded for operator        │
                          └──────────────────────────────────────┘

         New top-level packages
         ──────────────────────
         src/codegenie/cve/
           models.py          ← Advisory, AffectedVersionRange, Provenance
           feeds/
             nvd.py           ← NVD JSON 2.0 → Advisory
             ghsa.py          ← GHSA JSON   → Advisory
             osv.py           ← OSV JSON    → Advisory
           store.py           ← filesystem-backed advisory cache
         src/codegenie/recipes/
           catalog/npm/       ← *.yaml (recipe definitions, data)
           engine.py          ← RecipeEngine ABC + NcuRecipeEngine
           selector.py        ← Recipe selection (consumes Skills loader)
           selector.yaml      ← (data) decision-table mapping advisory
                                  shape → recipe id
           models.py          ← Recipe, RecipeApplication
         src/codegenie/transforms/
           __init__.py        ← @register_transform decorator + registry
           contract.py        ← Transform ABC, TransformInput, TransformOutput
           coordinator.py     ← linear orchestrator (Phase 3); the LangGraph
                                  state machine arrives in Phase 6 around it
           context.py         ← TransformContext (read-only view onto
                                  RepoContext + advisory + recipe + worktree)
           npm_package_upgrade.py  ← THE Phase 3 transform (the only one)
         src/codegenie/validation/
           contract.py        ← Validator ABC, ValidatorOutput
           install.py         ← NpmInstall
           test.py            ← NpmTest
           build.py           ← NpmBuild (opt-in via package.json#scripts.build)
```

Three things to notice in the diagram:

1. **Every Phase 0/1/2 box says "unchanged."** Same test as Phase 1 and Phase 2. The probe pipeline is read-only data for Phase 3.
2. **`Transform`, `Validator`, `Recipe` are three nouns.** A transform changes a repo; a validator verifies a repo; a recipe is the *parameterization* the transform reads. The coordinator runs them in sequence. Three contracts; no three-axis matrix.
3. **The orchestrator is plain Python.** No LangGraph (Phase 6), no Temporal (Phase 9), no asyncio (we are running one repo, in one process, on one developer's laptop). The CLI subcommand calls a function that calls six other functions. **Boring on purpose.**

---

## Components

### 1. The `Transform` ABC — the most important component in Phase 3

- **Purpose:** Define the contract that every transform (this phase: `NpmPackageUpgradeTransform`; Phase 4 won't add a transform, only a planner; Phase 7: `DockerfileBaseImageSwapTransform`; Phase 15: agent-authored transforms) satisfies. **Modeled byte-for-byte on `Probe` ABC.** Same registry shape, same `applies()`/`run()` split, same declarative fields.
- **Public interface:**
  ```python
  # src/codegenie/transforms/contract.py
  from abc import ABC, abstractmethod
  from collections.abc import Sequence
  from pathlib import Path
  from typing import Literal

  from pydantic import BaseModel, Field

  from codegenie.cve.models import Advisory
  from codegenie.recipes.models import Recipe

  Confidence = Literal["high", "medium", "low"]


  class TransformInput(BaseModel):
      """Frozen, validated input to a Transform.run() call."""

      repo_root: Path
      worktree_root: Path           # *.codegenie/remediation/<run-id>/worktree*
      branch_name: str              # codegenie/vuln-fix/<cve-id>-<short-sha>
      advisory: Advisory
      recipe: Recipe
      repo_context_path: Path       # already-validated repo-context.yaml
      run_id: str                   # for tracing into raw/


  class TransformOutput(BaseModel):
      """Frozen, validated output of a Transform.run() call.

      Note: NO 'success' field. Validators decide success. Transforms describe
      what they wrote.
      """

      name: str
      diff_path: Path               # .codegenie/remediation/<run-id>/diff/...
      branch_name: str
      files_changed: list[Path]
      confidence: Confidence
      warnings: list[str] = Field(default_factory=list)
      errors: list[str] = Field(default_factory=list)
      skipped: bool = False         # True iff selector returned no recipe;
                                    # diff_path will be empty in this case


  class Transform(ABC):
      """A deterministic repo modification.

      Same contract shape as codegenie.probes.contract.Probe (ADR-0007):
        - declarative metadata (name, declared_inputs, applies_to_*)
        - applies(repo_ctx, advisory, recipe) -> bool
        - run(input) -> TransformOutput
        - NO LLM may be imported under codegenie.transforms.*
      """

      name: str
      declared_inputs: Sequence[str]               # globs in the repo
      applies_to_tasks: Sequence[str]              # ["vuln_remediation"] in P3
      applies_to_languages: Sequence[str]          # ["javascript","typescript"]
      requires_recipe_engines: Sequence[str]       # e.g. ["ncu"]

      @abstractmethod
      def applies(
          self,
          repo_context: "RepoContextView",
          advisory: Advisory,
          recipe: Recipe,
      ) -> bool: ...

      @abstractmethod
      def run(self, input: TransformInput) -> TransformOutput: ...
  ```
- **Internal design (idiomatic Python conventions cited):**
  - **Same shape as `Probe`.** Conformance over taste (Rule 11). If a future engineer wonders "why is `Transform` modeled on `Probe`," the answer is "because we are extending by addition, and they look alike on purpose."
  - **Pydantic for inputs and outputs.** "Parse, don't validate" applied at the boundary — same Phase 0–2 pattern.
  - **Registry via decorator** (`@register_transform`), same module-shape as `@register_probe`:
    ```python
    # src/codegenie/transforms/__init__.py
    _TRANSFORMS: dict[str, type[Transform]] = {}

    def register_transform(cls: type[Transform]) -> type[Transform]:
        if cls.name in _TRANSFORMS:
            raise RuntimeError(f"duplicate transform name: {cls.name}")
        _TRANSFORMS[cls.name] = cls
        return cls

    def all_transforms() -> Sequence[type[Transform]]:
        return tuple(_TRANSFORMS.values())
    ```
  - **No async.** Phase 3 is one-repo, one-process. Async is reopened in Phase 6 (state machine) and Phase 9 (Temporal); pulling it in here would be premature complexity.
  - **`RepoContextView` is a read-only Pydantic view.** It parses `repo-context.yaml` into a flat object the transform queries. It does not allow mutation. The probe pipeline owns the write path.
- **Dependencies:** `pydantic`, stdlib only.
- **Where it lives:** `src/codegenie/transforms/contract.py` and `__init__.py`.
- **Tradeoffs accepted:**
  - **`TransformInput` carries both `advisory` and `recipe`.** Could be a single `(advisory, recipe)` tuple computed by the selector — but explicit named fields make signatures readable. Pydantic models compose; tuples decay.
  - **`TransformOutput` has no `success: bool`.** This is deliberate. A transform reports what it wrote; the validator says whether the change works. Conflating these is what `production/design.md §2.2` warns against — "facts, not judgments." A future engineer's instinct will be to add `success`; the ABC's docstring explicitly forbids it.

### 2. `cve_feed` — three feeds, one canonical model

- **Purpose:** Parse NVD JSON 2.0, GHSA, and OSV feeds into one canonical `Advisory` model. The feed is the wire format; `Advisory` is the in-code object every other Phase 3 component speaks.
- **Public interface:**
  ```python
  # src/codegenie/cve/models.py
  class Provenance(BaseModel):
      source: Literal["nvd", "ghsa", "osv"]
      id: str                        # "CVE-2024-12345" | "GHSA-xxxx" | "..."
      fetched_at: datetime
      raw_path: Path                 # raw JSON file on disk

  class AffectedRange(BaseModel):
      ecosystem: Literal["npm"]      # Phase 3 = npm only
      package: str
      vulnerable: str                # semver range, e.g. "<1.2.3"
      patched: str | None            # semver range, e.g. ">=1.2.3"

  class Advisory(BaseModel):
      cve_id: str | None             # canonical CVE-YYYY-NNNN
      aliases: list[str]             # GHSA-xxx, OSV-xxx
      severity: Literal["low","medium","high","critical","unknown"]
      cvss_v3_score: float | None
      affected: list[AffectedRange]
      provenance: list[Provenance]
      summary: str                   # short, ≤500 chars

      @classmethod
      def merge(cls, sources: Sequence["Advisory"]) -> "Advisory": ...

  # src/codegenie/cve/feeds/nvd.py
  def parse(raw_path: Path) -> Advisory: ...

  # src/codegenie/cve/store.py
  class AdvisoryStore:
      """Filesystem-backed.  ~/.codegenie/cve/<cve-id>.yaml"""
      def get(self, cve_id: str) -> Advisory | None: ...
      def put(self, advisory: Advisory) -> None: ...
      def sync(self, source: Literal["nvd","ghsa","osv"], since: datetime) -> int: ...
  ```
- **Internal design:**
  - One file per feed parser. Each is a pure function `(raw_path: Path) -> Advisory`. Each emits `Provenance` with the feed name and the path. Test surface is a handful of frozen feed-snapshot JSON files under `tests/fixtures/cve_feeds/`.
  - `Advisory.merge` deduplicates by `(source, id)` and unions `affected`. Conflict resolution is **highest severity wins**, with all source provenance preserved — facts, not judgments.
  - `AdvisoryStore.sync` is the only network-touching code in Phase 3 and is **invoked exclusively by `codegenie cve sync`**, never automatically. The remediate orchestrator never fetches; it only reads from the store. This makes `remediate` runs reproducible offline.
- **Dependencies:** `pydantic`, `httpx` (synchronous mode, only used inside `store.sync` and only inside `cli/cve.py`).
- **Where it lives:** `src/codegenie/cve/`.
- **Tradeoffs accepted:**
  - **`Advisory.merge` does not normalize semver ranges across feeds.** NVD's CPE-style version expressions differ from GHSA's. We preserve both, and the selector reads `affected[*].vulnerable` as a list of ranges to test. Normalizing into one canonical range is **a recipe for silent disagreement** — best to fail loud if no recipe matches than to over-normalize.
  - **No streaming, no scheduler.** `sync` is `codegenie cve sync --source nvd --since 2026-04-01`. A user (or Phase 14's webhook job, later) drives it. Phase 3 must not anticipate Phase 14's scheduler.

### 3. `recipes` — engine ABC + ncu engine + catalog + selector

- **Purpose:** Recipes are *what* to apply; the engine is *how*; the catalog is *data*; the selector picks one.
- **Public interface:**
  ```python
  # src/codegenie/recipes/models.py
  class Recipe(BaseModel):
      id: str                        # "npm-upgrade-package@semver-patch"
      engine: Literal["ncu"]         # one engine in P3; OpenRewrite later
      applies_to_tasks: list[str]    # ["vuln_remediation"]
      applies_to_languages: list[str]
      applies_to_cve_patterns: list[str]  # globs: "CVE-*", "GHSA-*"
      parameters: dict[str, JSONValue]    # engine-specific
      source_path: Path

  class RecipeApplication(BaseModel):
      recipe_id: str
      diff: bytes                    # the *actual* unified diff
      files_changed: list[Path]
      engine_stdout: str
      engine_stderr: str
      exit_code: int

  # src/codegenie/recipes/engine.py
  class RecipeEngine(ABC):
      name: str
      @abstractmethod
      def apply(self, recipe: Recipe, repo: Path, ctx: ApplyContext) -> RecipeApplication: ...

  class NcuRecipeEngine(RecipeEngine):
      """Wraps `ncu` via codegenie.exec.run_allowlisted."""

  # src/codegenie/recipes/selector.py
  def select(
      repo_context: RepoContextView,
      advisory: Advisory,
      skills: SkillIndex,        # Phase 2 loader (unchanged)
  ) -> Recipe | None: ...
  ```
- **Internal design:**
  - **Recipes are YAML files** under `src/codegenie/recipes/catalog/npm/*.yaml`. Schema: `src/codegenie/recipes/catalog/_schema.json`. Loaded at import; malformed → loud failure at CLI startup (Phase 1/2 catalog precedent).
  - **`RecipeEngine` is an ABC** to make Phase 4's `OpenRewriteRecipeEngine` an additive change (one new file, one new ADR for the JVM dependency). Phase 3 ships exactly one engine, `NcuRecipeEngine`.
  - **`ApplyContext`** carries `repo_root`, `target_package`, `target_version`, `confidence_thresholds`, `worktree_root`. It is **constructed by `transforms.npm_package_upgrade`**, not by the engine; engines are stateless given their context.
  - **The selector consumes the Phase 2 Skills loader without modification.** The new `applies_to.cve_patterns` field on `SkillManifest` is the only schema change; the loader's matching logic gains one additional filter step (`skill_matches_cve(s, advisory)`), implemented in the *selector*, not the loader. Phase 2's loader code does not change.
  - **The selector's algorithm is small, plain, and total:**
    1. Filter Skills by `(task="vuln_remediation", language=<repo_lang>, cve_pattern matches advisory.cve_id)`.
    2. For each matching Skill, read `Skill.parameters.preferred_recipe_id` (if set).
    3. Cross-check against the recipe catalog; return the matching `Recipe`.
    4. If no Skill or no recipe matches, the selector reads `selector.yaml` (the decision table) and tries a direct match by `(advisory.affected[*].package, advisory.affected[*].vulnerable)` → recipe id.
    5. If still no match, return `None` (Phase 4 will wrap this).
  - **`selector.yaml`** is the small-default decision table. Example excerpt:
    ```yaml
    decision_table:
      - when:
          advisory.affected.ecosystem: npm
          advisory.severity_in: ["high", "critical"]
          recipe_engine_available: ncu
        then:
          recipe_id: "npm-upgrade-package@semver-patched"
    default:
      recipe_id: null
    ```
  - **`when`-clause matcher** uses a closed enum of operator types (`equals`, `in`, `available`), same shape as Phase 2's `ConventionProbe` `detect.type` enum. **Match/case dispatch, three lines per operator. No DSL.**
- **Dependencies:** `pydantic`, `pyyaml` via Phase 1's `safe_yaml`.
- **Where it lives:** `src/codegenie/recipes/`.
- **Tradeoffs accepted:**
  - **Two paths to recipe (Skill-preferred vs. selector.yaml-default).** Slight duplication; explicit override is the more conservative choice. The alternative — Skills always specify the recipe, and selector.yaml does not exist — would push all defaults into a YAML file *outside the codebase* (the Skills directory), making the default behavior less testable.
  - **`NcuRecipeEngine` is JS-tooling-coupled.** A team without `ncu` on PATH gets a hard failure at startup (Phase 0 CLI tool-readiness check). The alternative — embed our own semver resolver — is a much bigger surface than we want to maintain.

### 4. `transforms.npm_package_upgrade` — the Phase 3 transform

- **Purpose:** Apply an npm package upgrade recipe to a repo's `package.json` + lockfile, on a worktree, producing a real diff.
- **Public interface:** standard `Transform` ABC. `name = "npm_package_upgrade"`, `applies_to_tasks = ["vuln_remediation"]`, `applies_to_languages = ["javascript","typescript"]`, `declared_inputs = ["package.json","package-lock.json","pnpm-lock.yaml","yarn.lock","npm-shrinkwrap.json"]`, `requires_recipe_engines = ["ncu"]`.
- **Internal design:**
  - **Worktree, not working-tree.** The transform creates `git worktree add` into `.codegenie/remediation/<run-id>/worktree`, applies on that worktree, computes the diff with `git diff`. **The user's working tree is never touched.** This is the Phase 3 best-practice that the operator's local state is sacred.
  - **Branch naming:** `codegenie/vuln-fix/<cve-id>-<short-sha>`. The `<short-sha>` is the abbreviated SHA of the original HEAD at remediate time, so two remediation runs against different commits produce different branch names without collision.
  - **One subprocess invocation** via Phase 0's `exec.run_allowlisted` (no direct `subprocess.run`, same Phase 1/2 precedent):
    1. `ncu --packageFile package.json --upgrade --target patch --filter <package>` (parameterized by the recipe).
    2. `npm install --ignore-scripts --no-audit --no-fund` (or pnpm/yarn equivalent based on `RepoContextView.build_system.package_manager`).
    3. `git -C <worktree> add -A && git -C <worktree> commit -m "<commit-msg-from-recipe-template>"`.
    4. `git -C <worktree> format-patch -1 --stdout > diff/<recipe-id>.patch`.
  - **No `--force`.** `--force` paths are out of scope in Phase 3; if ncu refuses to resolve, the transform emits `confidence: low`, `errors: ["ncu refused; peer-dep conflict"]`, and exits cleanly. Phase 4 (LLM fallback) handles peer-dep rewrites.
  - **Idempotence.** Re-running the same `(advisory, recipe, repo_sha)` against the same `run_id` produces a byte-identical diff. This is enforced by a unit test against a frozen fixture.
- **Dependencies:** `gitpython` (Phase 2 already uses it), `pydantic`.
- **Where it lives:** `src/codegenie/transforms/npm_package_upgrade.py`.
- **Tradeoffs accepted:**
  - **`--ignore-scripts` on install.** Best-practices security default; mirrors Phase 5's eventual sandbox posture. A package that **needs** install scripts for its tests will fail validation; that's a recipe-coverage gap to surface, not a reason to weaken the default.
  - **Worktree creation costs ~100 ms.** Acceptable given the safety of operator's local state. Phase 6/9 may share worktrees across stages; Phase 3 does not.

### 5. `validation` — three small validators

- **Purpose:** A transform writes a diff; a validator checks that the diff works. Validators are sibling contracts to transforms; same registry shape; total: three validators in Phase 3 (`install`, `test`, `build`).
- **Public interface:**
  ```python
  # src/codegenie/validation/contract.py
  class ValidatorInput(BaseModel):
      worktree_root: Path
      run_id: str
      repo_context_path: Path

  class ValidatorOutput(BaseModel):
      name: str
      passed: bool
      stdout_path: Path
      stderr_path: Path
      duration_ms: int
      confidence: Confidence
      warnings: list[str] = Field(default_factory=list)
      errors: list[str] = Field(default_factory=list)

  class Validator(ABC):
      name: str
      applies_to_languages: Sequence[str]
      @abstractmethod
      def applies(self, repo_context: RepoContextView) -> bool: ...
      @abstractmethod
      def run(self, input: ValidatorInput) -> ValidatorOutput: ...
  ```
- **Internal design:**
  - `NpmInstallValidator`: `npm install` in the worktree (or pnpm/yarn); pass if exit 0.
  - `NpmTestValidator`: reads `package.json#scripts.test`; if present, runs it; pass if exit 0 *and* no test framework's output file reports failures (`junit.xml` parsed if present, jest/mocha stdout pattern-matched otherwise). The parser is `tests/fixtures/test_runner_outputs/` golden-driven.
  - `NpmBuildValidator`: opt-in — only runs if `package.json#scripts.build` exists.
  - **Re-validation is idempotent.** Running the same validator twice on the same worktree produces the same `passed` outcome (modulo timestamps in raw output, which are stripped before golden comparison).
  - **No retry inside validators.** The three-retry default ([ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md)) is **Phase 5 machinery**, not Phase 3. A failing validator emits `passed: False`; the orchestrator records it and exits without retry.
- **Dependencies:** `pydantic`, stdlib only.
- **Where it lives:** `src/codegenie/validation/`.
- **Tradeoffs accepted:**
  - **`NpmTestValidator` doesn't parse coverage.** The roadmap exit criterion is "passes the repo's own tests" — coverage is a Phase 12 concern.
  - **`passed: bool` lives on `ValidatorOutput` but not `TransformOutput`.** A validator's job is judgment about a specific objective signal; a transform's is not. The lexical separation is the point.

### 6. The orchestrator — small, linear, sync

- **Purpose:** Run the six stages in order. Pure Python.
- **Public interface:**
  ```python
  # src/codegenie/transforms/coordinator.py
  def remediate(
      repo_root: Path,
      cve_id: str,
      *,
      run_id: str,
      config: RemediateConfig,
  ) -> RemediationReport:
      """Linear, synchronous. No retries. No state machine.

      Phase 6 replaces this with a LangGraph state machine *that wraps* it.
      Phase 9 replaces that with Temporal activities. The function's signature
      and the RemediationReport schema are the contract those phases preserve.
      """
  ```
- **Internal design:** Six function calls, one after the other. Each stage emits a typed event into `audit.json` (per-stage timing, success/failure, output path). On any non-recoverable stage failure, the orchestrator writes the partial `remediation-report.yaml` with `status: aborted`, the audit anchor, and exits with a non-zero CLI code. The branch is left on disk for inspection.
- **Dependencies:** `pydantic`, stdlib only.
- **Where it lives:** `src/codegenie/transforms/coordinator.py`.
- **Tradeoffs accepted:**
  - **No state machine.** This is the single biggest deviation a future engineer will want to make. The Phase 3 ADR forbids it explicitly: state machines belong in Phase 6, which exists for a reason. Premature LangGraph here means refactoring twice.
  - **No retries.** Phase 5's three-retry gate is exactly the right place for this discipline; Phase 3 should not invent its own retry policy that Phase 5 then has to displace.

### 7. CLI surface — three subcommands

- **Purpose:** Expose Phase 3 capability via three click subcommands, matching Phase 0/1/2 patterns.
- **Public interface:**
  ```
  codegenie remediate <repo>            \
      --cve <id>                        \
      [--run-id <auto>]                 \
      [--strict]                        \
      [--skip-validate {install,test,build}]
  codegenie cve sync --source <nvd|ghsa|osv> [--since <date>]
  codegenie recipes list [--engine ncu] [--task vuln_remediation]
  ```
- **Internal design:**
  - `remediate` is the orchestrator entry. Default `run_id` is `<utc-iso8601>-<short-sha-of-cve>`.
  - `cve sync` is the *only* network-touching command. Fails clean offline.
  - `recipes list` lists the loaded catalog. Useful for operators auditing which recipes their installation has.
  - **Each subcommand is one file under `src/codegenie/cli/`**, same Phase 0/1/2 layout.
- **Dependencies:** `click`.
- **Where it lives:** `src/codegenie/cli/remediate.py`, `cve.py`, `recipes.py`.

### 8. Error model — explicit, typed, stdlib-rooted

Custom exception classes, all derived from `codegenie.errors.CodegenieError` (Phase 0):

- `cve.RawFeedMalformed` — feed JSON does not match the parser's schema.
- `cve.AdvisoryNotInStore` — `--cve <id>` not present and `--no-sync` is set.
- `recipes.RecipeUnavailable` — selector returned `None`.
- `recipes.RecipeEngineUnavailable` — declared engine not on PATH (e.g. `ncu` missing).
- `transforms.RecipeApplicationFailed` — engine returned non-zero or refused.
- `transforms.WorktreeAlreadyExists` — `<run-id>/worktree` exists; refuse to overwrite.
- `transforms.LockfileResolveFailed` — install resolved to a different version than the recipe requested.
- `validation.ValidatorFailed` — wraps the validator's `ValidatorOutput` for the orchestrator's audit anchor.

Each exception carries one of: `cve_id`, `recipe_id`, `package_name`, `path`. Each is loggable; each is structured. **Stdlib base `Exception` ancestors only.** No `pydantic.ValidationError` leakage at error boundaries (catch + re-raise as a typed `CodegenieError`).

### 9. Schema additions

Per-component sub-schemas under `src/codegenie/schema/transforms/`, `schema/validation/`, `schema/cve/`. Same `additionalProperties: false` per-root, same envelope-`true` Phase 0 layering. **`repo-context.yaml`'s schema is untouched.** Phase 3 introduces a new top-level artifact (`remediation-report.yaml`) and its own schema; the probe pipeline does not learn about it.

### 10. Test fixture portfolio — git bundles

- **Mechanism:** Each fixture repo is a `git bundle create <name>.bundle --all` artifact committed under `tests/fixtures/repos_bundles/`. The test harness unpacks each bundle into `tmp_path` via `git clone <bundle> <tmp>`. Bundles are reproducible, single-file, network-free, and unlike submodules don't drag in nested git refs.
- **Portfolio:**
  - `repo_clean_express/`: Express 4.18.2 (an old version) with one known CVE in a transitive; the recipe must update the direct dep that pulls it in.
  - `repo_peer_dep_conflict/`: a repo where the obvious upgrade triggers a peer-dep warning; the transform must emit `confidence: medium` and the install validator must report what npm says.
  - `repo_no_recipe_match/`: a repo whose vulnerable package has no matching recipe; the selector must return `None` cleanly and the orchestrator must exit with `skipped`.
  - `repo_pnpm_monorepo/`: a small pnpm workspace; the transform must respect monorepo lockfile semantics.
  - `repo_yarn_classic/`: yarn 1.x; transform must use yarn-equivalent install.
  - `repo_build_step/`: repo with `package.json#scripts.build`; build validator runs.
- **Where they live:** `tests/fixtures/repos_bundles/<name>.bundle`. Each bundle is ≤ 500 KB.
- **Tradeoffs accepted:**
  - **Bundle files are binary.** They're small, but they break `git log --stat`-style diffs. Acceptable given the alternative (submodules) is significantly worse.

---

## Data flow

Representative happy-path run on `repo_clean_express` against `CVE-2024-FAKE-NPM`:

1. **CLI entry** (`codegenie remediate ./repo_clean_express --cve CVE-2024-FAKE-NPM`). Tool-readiness check covers `npm`, `ncu`, `git`.
2. **Stage 1 — Load context.** Reads `.codegenie/context/repo-context.yaml`; validates schema. If absent or `--force-gather`, invokes Phase 0/1/2 gather as a function call (same process).
3. **Stage 2 — Resolve Advisory.** `cve.store.get("CVE-2024-FAKE-NPM")` → `Advisory(affected=[npm:express<4.20.0])`. If miss → exit with `AdvisoryNotInStore` instructing the operator to run `codegenie cve sync`.
4. **Stage 3 — Select Recipe.** `recipes.selector.select(repo_ctx, advisory, skills)` → `Recipe(id="npm-upgrade-package@semver-patched", engine="ncu", parameters={"target":"patch","filter":"express"})`.
5. **Stage 4 — Apply Transform.** `NpmPackageUpgradeTransform.run(TransformInput(...))`:
   - `git worktree add` into `.codegenie/remediation/<run-id>/worktree`.
   - `ncu --upgrade --target patch --filter express` → `package.json` bumped.
   - `npm install --ignore-scripts --no-audit --no-fund` → `package-lock.json` regenerated.
   - `git add -A && git commit -m "fix(deps): bump express to 4.20.1 (CVE-2024-FAKE-NPM)"`.
   - `git format-patch -1 --stdout` → `diff/npm-upgrade-package@semver-patched.patch`.
   - Returns `TransformOutput(confidence="high", files_changed=[package.json, package-lock.json])`.
6. **Stage 5 — Validate.**
   - `NpmInstallValidator.run(...)` → `passed=True`.
   - `NpmTestValidator.run(...)` → invokes `npm test`; parses `junit.xml` or stdout; `passed=True`.
   - `NpmBuildValidator.applies(...)` → `False` (no build script).
7. **Stage 6 — Write report.** `remediation-report.yaml` with status `succeeded`, branch name, diff path, validator outcomes. Audit anchor recorded.
8. **Exit 0.**

The orchestrator's call graph reads top-to-bottom in `coordinator.py`: six function calls in order, each typed input → typed output. **No event bus, no observer pattern, no callback maze.** Phase 6 wraps this in a state machine *without changing the function signatures*.

---

## Failure modes & recovery

| Failure | Detected by | Recovery | Provenance |
|---|---|---|---|
| `--cve <id>` not in advisory store | `cve.store.get` returns `None` | Hard fail: `AdvisoryNotInStore` with `codegenie cve sync` hint | best-practices: typed exceptions |
| Advisory schema malformed (feed corruption) | Pydantic `ValidationError` in `feeds.<src>.parse` | Re-raised as `cve.RawFeedMalformed(source, path, errors)`; sync fails loud | best-practices |
| Multiple sources disagree on `affected` ranges | `Advisory.merge` preserves all; selector tests each | Selector returns `None` if no range matches a recipe (loud, not silent) | best-practices: facts not judgments |
| Selector finds no recipe | `select()` returns `None` | `TransformOutput(skipped=True, errors=["no_recipe_match"])`; exit 4 (clean skip) | best-practices |
| `ncu` not on PATH | Phase 0 tool-readiness check at CLI startup | Hard fail at startup with install hint | best-practices: fail loud |
| `ncu` refuses (peer-dep conflict) | `NcuRecipeEngine.apply` non-zero exit | `RecipeApplicationFailed`; transform emits `confidence:low`; orchestrator exits 5 | best-practices |
| `npm install` fails | `NpmInstallValidator` `passed=False` | Validator output recorded; orchestrator marks `status: failed`; branch and worktree preserved on disk for operator inspection | best-practices |
| Test suite fails | `NpmTestValidator` `passed=False` | Same: recorded, status failed, branch preserved | best-practices |
| Worktree directory already exists | `WorktreeAlreadyExists` | Hard fail with run-id hint; the operator must remove or pass a fresh `--run-id` | best-practices |
| Lockfile resolves to wrong version | `LockfileResolveFailed` after parse | `confidence:low`, `errors`, branch preserved | best-practices |
| `repo-context.yaml` missing or stale | Schema validator at Stage 1; freshness vs HEAD via `IndexHealthProbe.confidence` | Re-run gather automatically if `--auto-gather` (default); else hard fail with hint | best-practices |
| Adversarial JSON in NVD feed (huge size, deeply nested) | Phase 1 size caps (extended to feed parsers): NVD JSON ≤ 50 MB | Refused with structured warning; sync exits non-zero on that file | best-practices |
| Hostile advisory ID (path traversal) | `cve_id` regex validation at CLI parse | Click rejects argument | best-practices |
| `git worktree add` fails (dirty index, locked) | Subprocess non-zero | `WorktreeAlreadyExists`-family typed error; surface clearly | best-practices |
| Skill manifest with invalid `cve_patterns` field | Phase 2 loader's JSON Schema (extended) | Hard fail at CLI startup | best-practices |

Pattern: **typed exceptions at the boundary, structured outputs at the contract, branches preserved on disk for operator inspection.** The orchestrator's exit codes are documented (`0=success`, `2=usage`, `3=gather_stale_strict`, `4=no_recipe`, `5=transform_failed`, `6=validation_failed`).

---

## Resource & cost profile

- **Tokens per run:** 0. `fence` CI job extended with `cve/`, `transforms/`, `recipes/`, `validation/` packages — none may import any LLM SDK.
- **Wall-clock (advisory, 1k-file Node fixture, M-series Mac):**
  - Cold remediation (gather already cached, npm install + tests run): **p50 ≤ 90 s, p95 ≤ 180 s.** Dominated by `npm install` (~30–60 s on cold cache) and the repo's tests.
  - Just `select + apply` (no validation): **p50 ≤ 2 s.**
- **Memory:** ~150 MB peak Python (Pydantic models + git diff); `npm install` is its own subprocess.
- **Storage per run:** `.codegenie/remediation/<run-id>/` ≤ 20 MB on average (worktree + raw logs); diff itself is ≤ 50 KB typically.
- **External-dep additions (pip):** `httpx` (synchronous; `cli/cve.py` only). `gitpython` already in Phase 2. No new C-extensions.
- **External CLI additions to `ALLOWED_BINARIES`** (one ADR per binary): `npm`, `ncu`. (`docker`, `syft`, `grype` already gated in Phase 2.) Each ADR documents the threat (PATH shim), the mitigation (Phase 0 env-strip + timeout), and the invocation pattern.

---

## Test plan

The pyramid is wide at the unit base, with goldens carrying the recipe-output contract.

### Unit tests (`tests/unit/{cve,transforms,recipes,validation}/`)

- **Per CVE-feed parser (3 modules):** ≥ 6 tests each — happy path, missing field, malformed JSON, size cap exceeded, severity normalization edge cases, merge dedup.
- **`Advisory.merge`:** at least 8 tests — single-source identity, two-source dedup, severity tie-break, range union, conflicting `cve_id`, all-empty, single-source-with-aliases, three-source merge.
- **Selector:** ≥ 12 tests — every `when`-clause operator (`equals`, `in`, `available`) × matched / unmatched / partial; Skills-preferred path; selector.yaml default path; no-match path.
- **`NpmPackageUpgradeTransform`:** ≥ 10 tests — happy path (mocked `ncu` via recorded stdout in `tests/fixtures/tool_outputs/`), missing `package.json`, lockfile divergence, peer-dep refusal, worktree-already-exists, branch-already-exists, idempotent re-apply, etc.
- **`Validator` suite:** ≥ 4 tests per validator — happy, missing script, non-zero exit, parser fallback for unrecognized test output.
- **`Transform` ABC + registry:** ABC instantiation refusal, duplicate-name rejection, decorator round-trip, `applies()` contract.
- **`coordinator.remediate`:** ≥ 8 tests — full success, gather-stale + auto-gather, advisory-not-in-store, no-recipe-match, transform-failed, validator-failed, audit-anchor written on each path, branch preserved on failure.

Approx. ~200–250 unit tests across Phase 3.

### Integration tests (`tests/integration/`)

- `test_remediate_express_e2e.py` — full `codegenie remediate` against `repo_clean_express` fixture; assert diff matches the golden; assert validators pass; assert exit 0.
- `test_remediate_pnpm_workspace.py` — same against the pnpm monorepo fixture.
- `test_remediate_no_recipe_clean_skip.py` — fixture has no matching recipe; assert exit 4 and a `skipped` report.
- `test_remediate_install_fails.py` — fixture where install fails post-bump; assert exit 6 and branch + worktree preserved.
- `test_cve_sync_offline_then_remediate.py` — pre-populate the advisory store from a frozen NVD snapshot; remediate works fully offline.
- `test_phase2_unchanged.py` — re-run a Phase 2 integration test verbatim; assert no Phase 2 outcomes changed (extension-by-addition invariant).

### Golden-file tests (`tests/golden/transforms/`)

**Every recipe ships at least one golden diff.** `tests/golden/transforms/<recipe-id>/<fixture-name>/expected.patch`. CI diff fails on drift. The Phase 3 exit criterion ("the system writes a working patch diff") is fundamentally a golden-tested property: the diff bytes are committed; CI asserts identity. Update path: `pytest --update-goldens`, reviewer attention required.

A second golden file per fixture: `expected_remediation_report.yaml` — the orchestrator's full report. Catches schema drift in `remediation-report.yaml`.

### Adversarial tests (`tests/adv/`) — CI-gating

- `test_nvd_oversized_feed.py` — 100 MB synthetic NVD JSON; parser refuses with size cap.
- `test_nvd_pathologically_nested.py` — deep recursion in the JSON; parser depth-limited.
- `test_cve_id_path_traversal.py` — `--cve ../../etc/passwd`; click rejects.
- `test_worktree_collision.py` — pre-existing worktree dir; `WorktreeAlreadyExists` raised cleanly.
- `test_ncu_malformed_output.py` — synthetic ncu stdout that's not valid JSON; engine raises typed error.
- `test_branch_naming_collision.py` — two runs on different SHAs produce different branch names; assert.
- `test_remediate_does_not_touch_working_tree.py` — assert `git status` on the user's working tree is byte-identical pre- and post-remediation.

### Property tests (where applicable, sparingly)

- `test_selector_is_total.py` — `hypothesis` generates random `(advisory, repo_ctx, skills)` tuples; selector always returns `Optional[Recipe]` without raising.
- `test_advisory_merge_is_commutative.py` — for any pair of advisories, `merge(a,b) == merge(b,a)` modulo provenance ordering.
- `test_advisory_merge_is_idempotent.py` — `merge(a) == a` for any single-element list.

### E2E

Three. Express, pnpm-workspace, yarn-classic. The unit + integration + golden pyramid does the heavy lifting; e2e proves the wires are right end-to-end.

### Phase 2 regression gate

The full Phase 2 integration suite runs as part of Phase 3's CI to catch any accidental Phase 0–2 edits. (This is the Phase 7 invariant test pulled forward.) Fails if any Phase 2 test fails or any Phase 0–2 source file is modified outside the explicitly ADR-gated additions (`ALLOWED_BINARIES += [npm, ncu]`, Skills schema additive field).

---

## Risks (top 5)

1. **The `Transform` ABC is the most consequential review in Phase 3.** Get this wrong and Phase 4 (LLM fallback wraps it), Phase 5 (gate machinery wraps it), Phase 7 (new task class extends it), Phase 15 (agent authors them) all pay the cost. **Mitigation:** the ABC is reviewed against four upcoming-phase use cases (Phase 4 wraps selector output, Phase 5 wraps coordinator, Phase 7 adds a Dockerfile transform, Phase 15 emits a Recipe + Transform pair) before merge. The Phase 0 `test_probe_contract.py` style snapshot test gets a sibling `test_transform_contract.py`: any signature drift fails CI. **Best-practices says: this ABC is frozen at v0.3.0 the same way `Probe` was at v0.1.0.**
2. **`ncu` is our sole recipe engine and is npm-flavor-coupled.** A pnpm-monorepo upgrade case `ncu` doesn't handle becomes a recipe-coverage gap that the LLM fallback (Phase 4) must paper over. **Mitigation:** the `RecipeEngine` ABC accepts a future `PnpmDeduplicateEngine` or `OpenRewriteRecipeEngine` as an additive extension — extension by addition. Phase 3's npm-package-upgrade recipe explicitly targets the common 80% case (transitive vuln resolvable by direct-dep bump); the long tail is Phase 4's problem by design (ADR-0011).
3. **The `applies_to.cve_patterns` schema addition to Phase 2's Skills loader could become a Trojan horse.** A future engineer adds another optional axis, then another; the Skills frontmatter grows into a DSL. **Mitigation:** the schema field is closed (string-list of CVE-shaped globs); any *new* axis requires an ADR. Phase 2's `applies_to.task_types` × `languages` pattern is the precedent — additive, conservative, ADR-gated.
4. **Validator results don't feed back into the orchestrator's decision.** Phase 3 records and exits. A future engineer's instinct will be to add "on validation failure, try the next recipe." That's Phase 4/5 territory. **Mitigation:** the orchestrator is **explicitly linear** (the ADR forbids retry inside it). Phase 5 wraps it with the three-retry gate; Phase 4 wraps the selector with the RAG/LLM chain. The orchestrator's docstring carries the prohibition.
5. **`cve sync` introduces the first outbound-network code path in `codegenie`.** Phase 0's structural ban (no `httpx`/`requests` under `src/codegenie/`) needs an explicit, narrow exception. **Mitigation:** the `fence` CI job is updated to allow `httpx` *only* in `src/codegenie/cve/store.py` and `src/codegenie/cli/cve.py` (file-list-pinned). Every other module remains barred. An ADR documents the network surface, the threat model (registry redirection / API spoofing), and the user-driven invocation discipline. **Phase 3 must not add automatic background fetches.**

---

## Acknowledged blind spots

- **OpenRewrite is deferred.** The Phase 3 roadmap line says "OpenRewrite recipes for npm" first. I'm picking `ncu` over OpenRewrite for the Phase 3 implementation because (a) OpenRewrite's npm story is currently weak (their JS/TS support lags Java), (b) JVM-on-the-laptop is a heavy dependency to take on for a feature that doesn't need it, (c) extension-by-addition means OpenRewrite lands later as a sibling `RecipeEngine` implementation without re-architecting. **I am surfacing this for the synthesizer to weigh against the roadmap's explicit naming.** If the synthesizer disagrees, the change is a new `OpenRewriteRecipeEngine` module — mechanical.
- **No `--push-pr` flag.** The roadmap is clear: Phase 3 stops at a local branch. ADR-0009 reinforces it. But a future engineer will be tempted. The Phase 3 ADR forbids it explicitly; Phase 11 is the only legitimate place this lands.
- **No LLM fallback wired.** Phase 3 *must* exit cleanly on `no_recipe_match`. Phase 4 wraps the selector. **If the synthesizer asks "but what if a real exit-criterion CVE has no recipe?" the answer is "the fixture portfolio includes only CVEs we have recipes for, and that's the deterministic budget."** Phase 4 widens the coverage; Phase 3 proves the deterministic spine.
- **Validation is install + test + (opt-in) build.** Not SAST. Not runtime trace. Not policy. Those validators exist conceptually but are out of Phase 3 scope (Phase 5's sandbox + trust gates is where the rest land).
- **Performance is not the lens.** Phase 3's design will be slower than the performance-first version. The orchestrator is synchronous; the install step is wall-clock-dominated. The synthesizer should fold in performance wins that don't violate the contracts (e.g. caching `ncu` results between adjacent runs is fine; making the orchestrator async is premature).
- **Cost-feed staleness is not addressed.** If a user's advisory store hasn't been synced in 30 days, the remediate command will still happily use a 30-day-old `Advisory`. There's no automatic check. **Mitigation candidate (for synthesizer):** the orchestrator records `advisory.provenance[*].fetched_at` and warns if any source is > N days old, where N is configurable.

---

## Open questions for the synthesizer

1. **`ncu` vs. OpenRewrite as the Phase 3 recipe engine.** The roadmap names OpenRewrite first. My read is `ncu` for the v0.3.0 cut and OpenRewrite via additive `RecipeEngine` implementation later. The security lens may have a stronger opinion about JVM surface; the performance lens may agree with `ncu` because of startup cost. **Surfaced for arbitration.**
2. **Should `Validator` and `Transform` share a registry, or two registries?** I picked two — they are two nouns with two lifecycles and two future-extension stories (Phase 5 adds *gates*; gates compose validators). The argument for one registry is uniformity; the argument for two is type clarity. **My read: two.** Surfacing for visibility.
3. **`applies_to.cve_patterns` on `SkillManifest` vs. a separate `vuln_remediation_skill.yaml` schema.** I chose additive on the existing Skill schema, which keeps the Phase 2 loader untouched. The alternative is a new schema sibling and a small new loader. **My read: additive wins** (one loader, simpler operator mental model, fewer moving parts) — but if the synthesizer worries about the Skill schema becoming a junk drawer, the alternative is clean.
4. **Does the orchestrator auto-gather on `repo-context.yaml` staleness, or fail loud?** I defaulted to auto-gather with `--no-auto-gather` to disable. Fail-loud is the more "honest confidence" choice; auto-gather is the more ergonomic. **Surfacing for the security lens.**
5. **Branch-name collision strategy across runs.** I named branches `codegenie/vuln-fix/<cve-id>-<short-sha>`. If the operator runs Phase 3 twice on the same commit (same `<cve-id>` + same `<short-sha>`), the second run collides. Options: (a) refuse and exit; (b) append `-<run-id-suffix>`; (c) overwrite. I default to (a). The performance lens may prefer (b); the security lens may prefer (a).
6. **Should `cve sync` be a Phase 3 deliverable at all, or pushed to Phase 14?** The roadmap line lists "CVE data ingestion: parsers for NVD JSON 2.0, GHSA, and OSV feeds." Parsers and the `Advisory` model are non-negotiable Phase 3 deliverables. The *fetcher* (`cve sync` subcommand calling `httpx`) is a thinner wedge — it could ship as Phase 3 (fixture-data tests still work without it) or be pushed to Phase 14 alongside the cron/webhook ingestion. **My read: ship `cve sync` in Phase 3** because demoing the exit criterion ("given a Node.js repo with a known npm CVE") is enormously more compelling if an operator can `codegenie cve sync && codegenie remediate`. Surfacing for arbitration.
7. **`NpmTestValidator` parser strategy.** I picked junit.xml + stdout-pattern. A team using vitest or jest has built-in junit reporter support, but a team using mocha-without-reporter doesn't. **My read:** if `junit.xml` is absent and stdout doesn't match a known pattern, the validator emits `confidence: medium` and trusts the exit code. The security lens may want stricter signal-disagreement handling.
8. **`Transform` ABC versioning.** Phase 0 froze the `Probe` ABC at v0.1.0 with a snapshot test. **My read: freeze `Transform` ABC at v0.3.0 with the same snapshot test pattern.** Surfacing because it formalizes a Phase 3 review gate.
