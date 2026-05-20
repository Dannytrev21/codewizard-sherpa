# Phase 7.5 — Multi-language foundations + Python: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-20

## Lens summary

Phase 7.5 is a *refactoring-discipline* phase, not a feature phase: it must add Python as the second target language **and** retrofit TypeScript as the first language pack *without editing a single shipped Phase 1–7 probe or plugin*. The best-practices answer is to invent exactly one new contract — `LanguagePack`, a frozen Pydantic value — and exactly one new privileged operation — `register_language()`, which fans the pack out into the *already-existing* decomposed registries (`@register_probe`, `@register_dep_graph_strategy`, the grammar kernel `_DISPATCH`). No new registry kernel, no plugin DI container, no capability discovery. The `LanguagePack` is a *manifest of references to things that already have homes*, not a new home. The conformance tier is a single parameterized pytest module that auto-enrolls every registered language by reading the language registry — boring, well-supported `pytest.mark.parametrize` plus indirect fixtures. The phase ships two packs (TypeScript #1, Python #2): two is the minimum that proves the abstraction without freezing it on one example, and it is also the maximum the phase scope permits — we resist a third speculative pack. The headline discipline is restraint: this design names every capability category Python *actually needs today* and refuses to add a category Python does not exercise.

## Conventions honored

- **No LLM in the gather pipeline** (production design.md §2, ADR-0005). `LanguagePack`, `register_language()`, the Python probes, and the dep-graph strategies are all deterministic Python. The `fence` job (`tests/unit/test_pyproject_fence.py`) stays green; `scip-python` is a dev/adapter-tier tool invoked through `run_external_cli`, never imported into the gather runtime closure, exactly as `scip-typescript` is today.
- **Facts, not judgments.** The Python Layer A/B probes report evidence (`detected python files: 412`, `lockfile: poetry.lock present`, `dep-graph: 88 resolved packages`) with `confidence: Literal["high","medium","low"]`. No probe concludes "safe to remediate."
- **Extension by addition — no *silent* edits** (ADR-0043, the ADR this phase lands). Adding Python touches only new files plus *compiler-policed loud edits*: a new `LanguagePack` module, one import line at the language-registry collection point, a `"python"` member appended to the `SupportedLanguage` `Literal` and the grammar `_DISPATCH` dict, `"pip"/"poetry"/"uv"` members appended to the `PackageManager` `Literal`, and additive schema `$ref`s. Every one of those is forced on consumers by `mypy --strict` or a snapshot test — the enforcement mechanism, not a violation.
- **Open/Closed at the file boundary.** `register_language()` is built *on top of* the three existing decomposed seams; it does not replace them. The grammar kernel stays the single typed boundary for `tree_sitter.Language`; `DepGraphRegistry` stays keyed by `PackageManager`; the probe registry stays the explicit-import collection point. This design adds *one* seam (the language registry) and reuses *three*.
- **Domain-modeling discipline** (ADR-0033). `LanguageId` is a `NewType`, not raw `str`. `LanguagePack` is a frozen Pydantic model — `frozen=True`, every capability a required field — so a partial pack is unrepresentable. Conformance outcomes are a sum type (`ConformancePass | ConformanceFail`), not a `bool`.
- **Probe contract preserved** (ADR-0007, localv2.md §4). Python probes implement the frozen `Probe` ABC verbatim — two-arg `run(self, repo, ctx)`, the same `name/layer/tier/applies_to_*/declared_inputs` surface. `LanguagePack` does not touch `base.py`.
- **Language search adapters** (ADR-0032). The Python `ScipAdapter` / `ImportGraphAdapter` / `DepGraphAdapter` / `TestInventoryAdapter` are structural `Protocol` implementations registered through the `vulnerability-remediation--python--pip` plugin manifest's `contributes.adapters` map — the existing mechanism, unchanged.
- **Plugin architecture** (ADR-0031). The new plugin lives at `plugins/vulnerability-remediation--python--pip/` and `extends` the universal `vulnerability-remediation--*--*` base. The `distroless-migration--python--pip` plugin is deliberately deferred (roadmap scope).
- **Mandatory golden fixtures.** Each language ships `tests/golden/languages/{language}/` with a fixture repo + a regenerable golden `RepoContext`, mirroring the existing `tests/golden/` discipline.

## Goals (concrete, measurable)

| Goal | Target |
|---|---|
| Net-new top-level packages under `src/codegenie/` | **1** — `codegenie.languages` (the pack + registry). Probes/depgraph/grammar additions go into the *existing* packages. |
| New public API surface (names exported from `codegenie.languages.__all__`) | **≤ 6** — `LanguageId`, `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`. Mirrors the 6-name `codegenie.depgraph` surface exactly. |
| `LanguagePack` capability fields | **6** — `grammar_name`, `project_detector`, `layer_a_probes`, `package_managers`, `dep_graph_strategies`, `search_adapter_module`. Exactly the six the roadmap names. No seventh speculative field. |
| Cyclomatic complexity ceiling (`ruff` C901) | **≤ 8** per function; `register_language()` itself ≤ 6 (it is a fan-out loop, not a branch tree). |
| Test coverage (the existing `--cov-fail-under` gate) | **≥ 85%**; `codegenie.languages` specifically **≥ 95%** (small, pure, no excuse). |
| Plain-Python vs framework-coupled ratio | `LanguageRegistry` + `register_language()` are **plain** Python (dataclass-shaped registry, like `DepGraphRegistry`). `LanguagePack` is the **one** Pydantic-coupled type — Pydantic is the project's chosen trust-boundary framework (ADR-0010); a pack is parsed/validated like any other contract value. |
| Edits to shipped Phase 1–7 `.py` files | **0 silent edits.** Loud edits limited to: `SupportedLanguage` Literal (+1 member), grammar `_DISPATCH` (+2 rows), `PackageManager` Literal (+3 members), one collection-point import line. Each is `mypy`/snapshot-policed. |
| New conformance test modules | **1** — `tests/conformance/test_language_conformance.py`, parameterized over the registry. |

## Architecture

```
                          codegenie.languages  (NEW — the one new package)
                          ┌───────────────────────────────────────────────┐
                          │  LanguageId         (NewType, ADR-0033)        │
                          │  LanguagePack       (frozen Pydantic model)    │
                          │  LanguageRegistry   (plain registry, like      │
                          │                      DepGraphRegistry)         │
                          │  register_language(pack) -> None               │
                          │  default_language_registry                     │
                          └───────────────────────────────────────────────┘
                                          │ register_language() fans out
              ┌───────────────────────────┼───────────────────────────────┐
              ▼                           ▼                               ▼
   codegenie.probes.registry   codegenie.depgraph.registry      codegenie.grammars.lock
   (@register_probe — EXISTING) (@register_dep_graph_strategy   (_DISPATCH — EXISTING;
              │                  — EXISTING)                     +2 rows = loud edit)
              │                           │                               │
              ▼                           ▼                               ▼
       Layer A/B probes          pip/poetry/uv strategies          tree-sitter-python

   Language packs (declared, not discovered — explicit imports):
   ┌──────────────────────────────────┐   ┌──────────────────────────────────┐
   │ codegenie.languages.packs        │   │ codegenie.languages.packs        │
   │   .typescript : LanguagePack     │   │   .python : LanguagePack         │
   │   (#1 — RETROFIT: references     │   │   (#2 — NEW: references new      │
   │    EXISTING Phase 1–7 probes)    │   │    Python probes + strategies)   │
   └──────────────────────────────────┘   └──────────────────────────────────┘

   tests/conformance/test_language_conformance.py
     @pytest.mark.parametrize over default_language_registry.all()
     → every registered language auto-enrolled; no per-language test file

   tests/golden/languages/{typescript,python}/   ← mandatory fixture repo + golden
```

The shape is deliberately the **same** as `codegenie.depgraph`: a `model.py` (the pack), a `registry.py` (the collection point), an `__init__.py` with a sorted 6-name `__all__`, and a `packs/` sub-package of explicit-import pack modules. An engineer who has read `codegenie.depgraph` reads `codegenie.languages` with zero new concepts.

## Components

### `LanguageId`

- **Purpose:** Nominal type for a programming-language identifier, so a `LanguageId` is never confused with a `TaskClassId`, `PackageManager`, or raw `str`.
- **Public interface:**
  ```python
  LanguageId = NewType("LanguageId", str)  # "typescript", "python"
  ```
- **Internal design:** Plain `typing.NewType`, identity-to-`str` at runtime, nominal under `mypy --strict` — ADR-0033 §1, exactly as `ProbeId`, `IndexName`, `PluginId` are defined. Lives **next to** the existing identifier catalog. Note: the existing `Language = NewType("Language", str)` in `codegenie.types.identifiers` already exists for `Skill.applies_to_languages`. **Convention conflict surfaced (Rule 7):** rather than introduce a near-synonym `LanguageId`, this design *reuses the existing `Language` newtype* and aliases it `LanguageId` in `codegenie.languages` only if a name-readability case is made in review. Default: reuse `Language`. Surfacing this avoids two newtypes for one concept.
- **Dependencies:** stdlib `typing` only.
- **Where it lives:** `src/codegenie/types/identifiers.py` (the existing kernel-tier identifier home — no new file).
- **Tradeoffs accepted:** Reusing `Language` means the name in `LanguagePack` reads `language: Language` not `language: LanguageId`. Slightly less self-documenting; avoids a duplicate-by-addition newtype, which ADR-0043 explicitly flags as a judgement-only anti-pattern.

### `LanguagePack`

- **Purpose:** The total, frozen value that *is* a language. One required field per capability. A partial language is unrepresentable; an incomplete `LanguagePack(...)` fails `mypy --strict` (missing required field → call-site error).
- **Public interface:**
  ```python
  from pydantic import BaseModel, ConfigDict

  class LanguagePack(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")

      language: Language                          # "python"
      grammar_name: str                           # key into grammars.lock._DISPATCH
      project_detector: ProjectDetector           # Protocol — "is this a Python repo?"
      layer_a_probes: tuple[type[Probe], ...]      # probe classes for @register_probe
      package_managers: tuple[PackageManager, ...] # ("pip", "poetry", "uv")
      dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]
      search_adapter_module: str                  # import path; ADR-0032
  ```
- **Internal design:** Pydantic v2 `frozen=True` model — the project's one sanctioned trust-boundary framework (ADR-0010). `extra="forbid"` so a typo'd capability fails loud. **Every field is required** — no `Optional`, no defaults — which is what makes a partial pack a `mypy` error (ADR-0033 §4, "make illegal states unrepresentable"). The pack holds **references** (probe *classes*, strategy *callables*, a grammar *name*, an import-path *string*) — it does not hold behavior. It is a manifest. The fields are tuples/`Mapping`, not `list`/`dict`, so the frozen value is genuinely immutable. **Growing `LanguagePack`** (a genuinely new capability category) breaks every existing pack at construction until updated — compiler-enforced, loud, and exactly the desired behavior per ADR-0043 ("the one sanctioned shared-file surface").
- **Dependencies:** `pydantic` (the trust-boundary framework, ADR-0010); `codegenie.probes.base.Probe`, `codegenie.depgraph.DepGraphStrategy`, `codegenie.types.identifiers.PackageManager` — all existing.
- **Where it lives:** `src/codegenie/languages/model.py`.
- **Tradeoffs accepted:** Pydantic over a frozen `dataclass`: a `dataclass` would also be frozen and total, but Pydantic gives `extra="forbid"`, construction-time validation, and matches the project's contract idiom (`ProbeOutput`, manifests, events are all Pydantic). The cost is Pydantic must accept `type[Probe]` and `Callable` fields (`arbitrary_types_allowed` is *not* needed for `type[...]`; for the `DepGraphStrategy` callable alias a small validator config is needed) — a known, documented Pydantic pattern. We deliberately do **not** model the pack as a sum type: there is no language-state machine here, every pack has the identical shape, so a single product type is correct (avoiding "tag-and-dispatch without a tagged union" *and* its inverse, a sum type where a product type suffices).

### `ProjectDetector`

- **Purpose:** Answer "is this repo (or this subtree) a $LANGUAGE project?" — the capability the roadmap names "project detector."
- **Public interface:**
  ```python
  class ProjectDetector(Protocol):
      def detect(self, repo: RepoSnapshot) -> DetectionResult: ...
  ```
  where `DetectionResult` is a small sum type — `Detected(confidence, marker_files) | NotDetected`.
- **Internal design:** A `typing.Protocol` — structural conformance, no inheritance, mirroring ADR-0032's adapter Protocols. The TypeScript detector is *retrofitted* by wrapping the logic already present in `LanguageDetectionProbe` — **without editing that probe**: the detector is a thin new module that reads the same markers (`package.json`, `tsconfig.json`). The Python detector reads `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile`. Detection markers live in a module-level `Final` tuple (the `_MONOREPO_PRECEDENCE` idiom), iterated never branched.
- **Dependencies:** `codegenie.probes.base.RepoSnapshot` (existing).
- **Where it lives:** detectors ship *inside each pack's source*: `codegenie/languages/packs/typescript/detector.py`, `.../python/detector.py`.
- **Tradeoffs accepted:** A detector duplicates marker knowledge that `LanguageDetectionProbe` also has. This is *intentional* under ADR-0043: editing `LanguageDetectionProbe` to expose its internals would be a silent edit to a shipped probe. The duplication is small (a tuple of filenames), loud (two named modules), and the conformance suite proves both agree on the golden fixtures. Flagged as the design's accepted-duplication point for the critic.

### `LanguageRegistry` + `register_language()`

- **Purpose:** Collect language packs and fan each one out into the three existing decomposed registries. `register_language()` is the *one new privileged operation* of the phase.
- **Public interface:**
  ```python
  class LanguageRegistry:
      def register(self, pack: LanguagePack) -> None: ...
      def get(self, language: Language) -> LanguagePack: ...        # raises LanguageRegistryError if absent
      def all(self) -> tuple[LanguagePack, ...]: ...                 # sorted by language, deterministic

  default_language_registry: LanguageRegistry          # process-wide singleton
  def register_language(pack: LanguagePack) -> None: ...  # convenience → default_language_registry
  ```
- **Internal design:** A plain class holding a `dict[Language, LanguagePack]` — the **exact** shape of `DepGraphRegistry` and `FreshnessRegistry` (`__init__` sets a dict; duplicate registration raises a loud `LanguageRegistryError` at import time naming both call sites; tests construct independent instances). `register_language()` is a **fan-out**, not a branch tree — a flat sequence with no conditionals:
  ```python
  def register_language(pack: LanguagePack) -> None:
      default_language_registry.register(pack)                       # 1. record the pack
      for probe_cls in pack.layer_a_probes:                          # 2. → probe registry
          register_probe(probe_cls)
      for pm, strategy in pack.dep_graph_strategies.items():         # 3. → depgraph registry
          register_dep_graph_strategy(pm)(strategy)
      # grammar: nothing to "register" — the kernel _DISPATCH row is a
      # compiler-policed source edit (ADR-0043 loud edit); register_language
      # asserts pack.grammar_name is in grammars.lock.supported_languages()
      # so a pack referencing an un-wired grammar fails loud at registration.
  ```
  It mirrors the `@register_*` decorator idiom by being the *one* call a pack module makes at import time — packs are collected by explicit import in `codegenie/languages/packs/__init__.py`, exactly as probes are collected in `codegenie/probes/__init__.py`. **No `importlib.metadata` scan** — supply-chain + cold-start hygiene, the established project rule.
- **Dependencies:** `codegenie.probes.registry.register_probe`, `codegenie.depgraph.register_dep_graph_strategy`, `codegenie.grammars.lock.supported_languages` — all existing seams.
- **Where it lives:** `src/codegenie/languages/registry.py`.
- **Tradeoffs accepted:** `register_language()` performs side effects (mutating three registries) at import time. This is *not* "side effects in a constructor" — it is an explicit named function, called explicitly from a pack module, the identical lifecycle as `@register_probe` firing at probe-module import. Import-time registration is the project's settled pattern; deviating would be the surprise. The cost: import order matters (a pack must import after the registries exist) — managed by the explicit collection point, the same way probes are.

### TypeScript pack (`LanguagePack` #1 — the retrofit)

- **Purpose:** Prove the abstraction is not Python-shaped by expressing the *already-shipped* Node/TypeScript stack as a `LanguagePack` — with **zero edits** to Phase 1–7 probe/plugin code.
- **Public interface:** `codegenie.languages.packs.typescript.PACK: LanguagePack`.
- **Internal design:** The pack *references* the existing Phase 1 Layer A probes (`LanguageDetectionProbe`, `NodeBuildSystemProbe`, `NodeManifestProbe`, …) by class — it imports them, it does not redefine them. The only genuinely new TypeScript code is `detector.py` (a thin marker-reader, see `ProjectDetector` tradeoffs). The grammar name is `"typescript"`, already in `_DISPATCH`. **Open problem surfaced:** the existing probe registry collects Phase 1 probes via `codegenie/probes/__init__.py`'s explicit imports *and* the TypeScript pack would also reference them. Registering them twice must be a loud `ProbeError` (the registry already raises on duplicates). **Best-practices resolution:** the retrofit moves the Phase 1 probe *registration* to flow through the TypeScript pack — but the probe registry today registers at `@register_probe` decoration time on the probe class. We do **not** edit the probe classes. Instead, the TypeScript pack's `layer_a_probes` lists the classes, and `codegenie/probes/__init__.py` keeps importing the probe modules (which is what fires `@register_probe`). The pack's `register_language()` call must therefore *not* re-register Phase 1 probes — see Open Questions Q1; this is the single sharpest retrofit seam and the critic should attack it.
- **Dependencies:** existing Phase 1 probe modules, existing Node dep-graph strategies (Phase 3), `grammars.lock`.
- **Where it lives:** `src/codegenie/languages/packs/typescript/`.
- **Tradeoffs accepted:** The retrofit is asymmetric with the Python pack — TypeScript's probes already self-register; Python's are net-new and *can* register through the pack. This asymmetry is honest and documented rather than papered over with a forced symmetry that would require editing Phase 1.

### Python pack (`LanguagePack` #2 — the new instance)

- **Purpose:** Add Python as a fully new language; the second instance that validates the contract.
- **Public interface:** `codegenie.languages.packs.python.PACK: LanguagePack`.
- **Internal design:** All-new files. Python Layer A probes (`PythonProjectProbe`, `PythonBuildSystemProbe`, `PythonManifestProbe`) and a Layer B `PythonImportGraphProbe` live under `src/codegenie/probes/python/` (a new sub-package, sibling of `probes/layer_b/` — pure addition). They implement the frozen `Probe` ABC unchanged. The three dep-graph strategies (`pip`, `poetry`, `uv`) live under `src/codegenie/depgraph/python/` and read `requirements.txt` / `poetry.lock` / `Pipfile.lock` / `uv.lock` / `pyproject.toml`. The grammar name is `"python"` — wired by the loud `_DISPATCH` +1 row + the `tree-sitter-python` PyPI wheel pinned in `pyproject.toml`. The pack lists all of the above by reference.
- **Dependencies:** `tree-sitter-python` (PyPI wheel, gather-runtime — allowed, it is a grammar not an LLM SDK); `scip-python` (dev/adapter tier, invoked via `run_external_cli`, never imported).
- **Where it lives:** `src/codegenie/languages/packs/python/`, `src/codegenie/probes/python/`, `src/codegenie/depgraph/python/`, `plugins/vulnerability-remediation--python--pip/`.
- **Tradeoffs accepted:** Three dep-graph strategies (pip/poetry/uv) is real implementation work the roadmap mandates; each reads a different lockfile format. We do **not** abstract a "generic Python lockfile reader" — three concrete strategies, three concrete parsers, no premature lockfile-format pluggability (rule of three: revisit if a fourth Python package manager appears).

### Conformance tier (`tests/conformance/`)

- **Purpose:** Catch the failure `mypy` cannot — a capability *slot filled but semantically broken* (a stub search adapter, a detector that never detects, a dep-graph strategy that returns an empty graph).
- **Public interface:** N/A — a pytest module.
- **Internal design:** **One** module, `tests/conformance/test_language_conformance.py`, parameterized over `default_language_registry.all()` via `@pytest.mark.parametrize` with the language id as `pytest.param(..., id=lang)` so failures name the language. Each parameterized test exercises one capability against that language's mandatory golden fixture under `tests/golden/languages/{language}/`:
  - `test_grammar_loads` — `grammars.lock.language_for(pack.grammar_name)` returns a usable `Language`.
  - `test_detector_detects_own_fixture` — `pack.project_detector.detect(fixture)` returns `Detected` with `confidence == "high"`.
  - `test_layer_a_probes_produce_nonempty_slices` — each Layer A probe run against the fixture yields a non-empty, schema-valid `schema_slice`.
  - `test_dep_graph_strategy_resolves` — each `(pm, strategy)` produces a graph with ≥ 1 node for the fixture.
  - `test_search_adapter_is_not_a_stub` — the adapter module imports, the adapter answers a known query against the fixture with a non-empty, non-degenerate result (this is the "passes `mypy` but semantically broken" catch).
  - `test_golden_matches` — the fixture's gathered `RepoContext` byte-matches the committed golden.
  Auto-enrollment is the key property: a new pack added to the registry is *automatically* in this suite with no test-file edit — the conformance tier grows by addition for free.
- **Dependencies:** `pytest`, the fixtures, `default_language_registry`.
- **Where it lives:** `tests/conformance/test_language_conformance.py`; fixtures under `tests/golden/languages/`.
- **Tradeoffs accepted:** Parameterizing over a *runtime registry* means the test surface depends on import side effects. This is the same coupling the coordinator already lives with; the alternative (a static list of languages in the test) would itself need editing per language, defeating "extension by addition." A registry-driven parameterization is the idiomatic pytest answer.

### Category-based extension-by-addition fence

- **Purpose:** Replace Phase 7's terminal 10-row byte-edit allowlist (ADR-0043 commitment 2: no new per-phase allowlist) with a *contract + snapshot* test for the `LanguagePack` surface.
- **Public interface:** N/A — a fence test under `tests/fence/`.
- **Internal design:** Following ADR-0043 commitment 3 ("a frozen surface is a contract with a snapshot test — the probe-ABC pattern"): a `tests/fence/test_language_pack_contract.py` snapshots the `LanguagePack` field set + types into `language_pack_contract.v1.json`, exactly as `tests/unit/test_probe_contract.py` snapshots the probe ABC against `probe_contract.v1.json`. The pack *file* stays freely editable; the snapshot test fails iff the *contract* (field names/types) changed — which is the desired loud signal when a genuinely new capability category is added. **No allowlist rows.** Per ADR-0043 the buildable, proven form is the per-contract snapshot test, not a general semantic-diff classifier — so this design does **not** build a "category classifier"; it builds one snapshot test for one contract.
- **Dependencies:** `pytest`.
- **Where it lives:** `tests/fence/test_language_pack_contract.py` + `tests/fence/snapshots/language_pack_contract.v1.json`.
- **Tradeoffs accepted:** A snapshot test catches a *contract* change, not an arbitrary silent edit anywhere in `codegenie.languages`. Non-contract code in that package is protected by the regression suite + review, exactly as ADR-0043 §"Tradeoffs" states. The planted-silent-edit test the roadmap asks for is realized as: plant an edit that adds a `LanguagePack` field → the snapshot test goes red. That is the test, and it is honest about its scope.

## Data flow

One representative end-to-end run — gathering context on a vulnerable **Python/poetry** repo, the phase's exit-criteria case:

1. **Import-time collection.** `import codegenie.languages.packs` runs `codegenie/languages/packs/__init__.py`, which explicitly imports `typescript` and `python`. Each pack module ends with `register_language(PACK)`. The TypeScript pack records itself; the Python pack records itself **and** fans `PythonProjectProbe`/`PythonBuildSystemProbe`/`PythonManifestProbe` into the probe registry and `pip`/`poetry`/`uv` strategies into `DepGraphRegistry`. *Where the convention shines:* this is the identical lifecycle as `@register_probe` — an engineer needs no new mental model.
2. **`codegenie gather ./vuln-python-repo`.** The coordinator reads the probe registry. `PythonProjectProbe` (a Layer A `tier="base"` probe) runs in the prelude pass; its `project_detector` logic finds `pyproject.toml` + `poetry.lock`, emits `schema_slice = {"python": {"detected": true, "confidence": "high", "package_manager": "poetry"}}`.
3. **Layer B.** `PythonImportGraphProbe` calls `grammars.lock.language_for("python")` — the kernel imports `tree_sitter_python`, memoized once per process — and walks imports. Honest confidence reported.
4. **Dep graph.** The `DepGraphProbe` looks up `DepGraphRegistry` for `"poetry"`, finds the strategy the Python pack registered, walks `poetry.lock`'s resolved graph, emits the dep graph slice.
5. **Sanitizer + writer.** Slices flow through the existing two-pass sanitizer; `repo-context.yaml` + `raw/*.json` written. *Nothing in steps 2–5 is new pipeline code* — the coordinator, sanitizer, and writer never learned the word "Python." They iterate registries that now have more rows.
6. **Plugin resolution (downstream).** A vuln workflow resolves `vulnerability-remediation--python--pip` from the `(task=vuln, language=python, build-tool=pip)` tuple; the plugin's `contributes.adapters` map wires the Python `ScipAdapter` etc. The plugin produces a real diff on the vulnerable fixture.
7. **Conformance.** In CI, `tests/conformance/` is parameterized over `default_language_registry.all()` — now `("python", "typescript")` — and asserts every capability of every pack against its golden fixture. The Node/TypeScript Phase 1–7 regression suite runs unchanged and green: the proof Python edited nothing.

The convention that shines through end to end: **the language axis extends exactly the way the task-class axis already does** — a new declarative bundle, collected by explicit import, fanned into existing seams. The reader who understood Phase 7's plugin addition understands Phase 7.5's language addition with no new concepts.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Incomplete `LanguagePack(...)` — a capability field omitted | `mypy --strict` at the construction call site (missing required arg) | Build fails before tests run. Engineer supplies the field. This is the contract working as designed. |
| `LanguagePack` references a grammar not in `_DISPATCH` | `register_language()` asserts `pack.grammar_name in grammars.lock.supported_languages()` — raises `LanguageRegistryError` at import | Loud failure at startup, not silent at probe dispatch. Engineer adds the `_DISPATCH` row + PyPI wheel. |
| Duplicate language registration (two packs claim `"python"`) | `LanguageRegistry.register` raises `LanguageRegistryError` naming both call sites, at import time | Mirrors `DepGraphRegistryError`/`ProbeError` — fail loud at startup. |
| Duplicate probe registration (TypeScript pack re-registers an already-imported Phase 1 probe) | `ProbeError` from the existing probe registry at decoration/registration time | See Open Question Q1 — the retrofit must ensure Phase 1 probes register *once*. Detected loud, not silent. |
| Capability slot filled but semantically broken (stub search adapter, no-op detector) | `tests/conformance/` — `mypy` passes, conformance fails | The whole reason the conformance tier exists. CI red; cannot merge. |
| `tree-sitter-python` wheel missing from the runtime closure | `grammars.lock` raises `GrammarLoadRefused` (the existing typed exception) | The kernel's single typed exception path — caller pattern-matches one `except`. Operator restores the `pyproject.toml` pin. |
| A silent edit adds a `LanguagePack` capability field without updating packs | The contract snapshot test `tests/fence/test_language_pack_contract.py` goes red | ADR-0043 commitment 3 in action — the contract changed loudly. Reviewer treats it as a `LanguagePack` growth (a sanctioned, compiler-policed shared-file edit). |
| Python golden fixture drift (probe output changed) | `tests/golden/languages/python/` golden mismatch | Engineer inspects the diff; regenerates the golden *deliberately* (a reviewed act, per the golden discipline). |
| `LanguagePack` frozen-ness violated (code tries to mutate a pack post-construction) | Pydantic `frozen=True` raises at runtime; `mypy` flags the assignment | Illegal by construction; surfaces immediately. |

Every error type above is **explicit and typed** — `LanguageRegistryError`, `GrammarLoadRefused`, `ProbeError`, `pydantic.ValidationError`. No bare `Exception`, no silent degradation. Rule 12 (fail loud) is satisfied structurally.

## Resource & cost profile

- **New runtime services:** none (roadmap confirms).
- **New gather-runtime dependency:** `tree-sitter-python` — one PyPI wheel, ~2–4 MB, loaded once per process and memoized by the grammar kernel. Comparable to `tree-sitter-typescript` already in the closure.
- **New dev-tier dependency:** `scip-python` — invoked as an external CLI through `run_external_cli`, never imported; zero gather-runtime weight; subject to the `ALLOWED_BINARIES` allowlist (one additive frozenset member, ADR-amendment-backed per the Phase 2 omnibus).
- **Cold-start cost:** `register_language()` for two packs fans out ~6 probe registrations + ~3 strategy registrations + 2 dict inserts — microseconds; negligible against the existing probe-import cost. No `importlib.metadata` scan added (the rule that keeps cold-start clean).
- **Code volume estimate:** `codegenie.languages` ≈ 250–350 LOC (model + registry + two thin pack modules + two detectors). Python probes ≈ 400–600 LOC (3 Layer A + 1 Layer B, mirroring the Node probe sizes). Python dep-graph strategies ≈ 300–450 LOC (three lockfile parsers). Conformance + fence + golden harness ≈ 200 LOC. Total net-new ≈ 1.2–1.8 kLOC — proportionate to "add a second language."
- **CI cost:** one new `tests/conformance/` module, parameterized × 2 languages × ~6 capability checks ≈ 12 fast tests; the Phase 1–7 regression suite runs unchanged (no new cost, it is the existing gate). The conformance tier is explicitly fast enough for every PR.
- **Test count delta:** ~12 conformance + ~30–50 Python probe/strategy unit tests + ~6 `codegenie.languages` unit tests + 1 contract-snapshot fence test + 2 golden suites.

## Test plan

- **Unit — `codegenie.languages` (≥ 95% coverage):**
  - `LanguagePack` rejects extra fields (`extra="forbid"`), is genuinely frozen (mutation raises), requires all 6 capabilities (omission is a `mypy` *and* runtime error).
  - `LanguageRegistry` — register/get/all round-trips; `all()` is deterministically sorted; duplicate registration raises `LanguageRegistryError` naming both origins; independent instances do not pollute.
  - `register_language()` fan-out — after a call, the probe registry contains the pack's probes, the depgraph registry contains its strategies; a pack with an un-wired grammar raises `LanguageRegistryError`.
  - **Intent over behavior (Rule 9):** the fan-out test asserts the probes are *callable and dispatchable*, not merely "a key exists" — a registry that stored the class but lost it on dispatch must fail the test.
- **Unit — Python probes & strategies:** each Layer A/B probe against small in-memory fixtures (detected vs not-detected, malformed `pyproject.toml`, missing lockfile, monorepo); each dep-graph strategy against a minimal lockfile of its format and a malformed one. Typed-error paths asserted (the probe records the error ID, never crashes).
- **Integration:** `codegenie gather` on the `tests/golden/languages/python/` fixture repo end to end — coordinator → Python probes → sanitizer → writer — asserting `repo-context.yaml` is produced and schema-valid.
- **Conformance (`tests/conformance/`):** the parameterized suite described in the component section — every registered language, every capability, against its golden fixture. Includes the deliberate "stub search adapter fails conformance" case as a *negative* test (a known-broken stub adapter, asserted to make conformance red).
- **Golden (`tests/golden/languages/{language}/`):** mandatory fixture repo + committed golden `RepoContext` per language; a golden-regen idempotence test (regenerating twice is a no-op), mirroring `tests/golden/test_regen_golden_portfolio_idempotent.py`.
- **Regression gate:** the **entire Phase 1–7 Node/TypeScript suite runs unchanged** as a hard CI gate — the load-bearing proof that adding Python edited nothing. `make check` reproduces it.
- **Fence:** `tests/fence/test_language_pack_contract.py` — the `LanguagePack` contract snapshot; planted-silent-edit test (add a field → red).
- **Property tests:** one property over `LanguageRegistry` — for any sequence of distinct packs, `all()` returns them sorted and `get(p.language) == p` for each (registry is an order-independent set keyed by language). Modest, targeted; we do not over-invest in property testing where example tests are clearer.
- **Test pyramid honored:** broad unit base (Python probes, `codegenie.languages`), a thin integration band (one `gather` run), conformance + golden as the cross-language correctness layer, the Phase 1–7 suite as the regression ceiling. No e2e service test — this phase ships no service.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `LanguagePack` as a frozen, total Pydantic value with one required field per capability | **Make illegal states unrepresentable** (ADR-0033 §4) + **value object** | A partial language is a real bug the type system can forbid for free; every required field means an incomplete pack is a `mypy` error at the construction site, before any test runs | **Builder pattern** — a `LanguagePackBuilder` with incremental `.with_grammar(...)` calls would *reintroduce* the partial-pack state the frozen total value forbids; a builder is the wrong tool when the goal is "no partial state" |
| `register_language()` fans a pack into three existing decomposed registries | **Facade** over the existing `@register_*` seams | One call, one mental model; the three registries keep their single responsibilities; the facade adds no new registry, just routing — Open/Closed at the file boundary | **A unified mega-registry** that replaces the probe/depgraph/grammar registries — would force editing Phase 1–7 registration call sites (a silent-edit storm) and centralize three orthogonal concerns; rejected as the inverse of extension-by-addition |
| `ProjectDetector` / search adapters as `typing.Protocol` | **Structural typing / duck-typed contract** (ADR-0032 precedent) | A new language implements a Protocol with no inheritance coupling to the framework; the conformance suite checks behavior, the type checker checks shape | **ABC inheritance** — would couple every language detector to a base class and invite a fragile inheritance hierarchy; Protocols give the same contract guarantee with looser coupling (composition over inheritance) |
| `DetectionResult` / `ConformanceOutcome` as discriminated unions | **Tagged union / sum type** (ADR-0033 §3) | "Detected vs not" and "conformance pass vs fail" are state machines; `match` + `assert_never` makes a missing case a compile error | **Boolean flag** (`detected: bool` + loose `confidence`/`markers` siblings) — the classic "tag-and-dispatch without a tagged union" anti-pattern; representable-but-illegal combinations (`detected=False` with `markers=[...]`) would slip through |
| Conformance suite parameterized over the live registry | **Parameterized test / open test set** | A new pack is auto-enrolled with zero test-file edits — the test surface extends by addition, mirroring the production extension story | **One hand-written test file per language** — would require editing/adding a test file per language, an enumerated list that accretes exactly like the byte-edit allowlist ADR-0043 kills |
| `LanguagePack` contract pinned by a snapshot test, not a frozen file | **Contract + snapshot test** (ADR-0043 commitment 3, the probe-ABC pattern) | The file stays editable; the *contract* is what is frozen; growing it is a loud, reviewable signal — the project's settled freeze idiom | **Per-phase byte-edit allowlist** — explicitly terminated by ADR-0043; an enumerated allowlist does not scale across Phases 8–16 |

## Patterns deliberately avoided

A **plugin/DI container** for languages — `register_language()` + explicit imports is the project's proven collection idiom; a container would be machinery ahead of need. A **capability registry / discovery mechanism** — the six capabilities are a closed, known set named by the roadmap; discovering them dynamically solves a problem this phase does not have (ADR-0043 explicitly defers a capability registry). A **`LanguagePack` inheritance hierarchy** (`BaseLanguagePack` → `JvmLanguagePack` → …) — there is no shared *behavior* between languages, only a shared *shape*; a flat product type is correct, an inheritance tree is premature taxonomy. A **generic lockfile-reader abstraction** spanning pip/poetry/uv — three concrete strategies for three formats is honest; abstracting before a fourth package manager is rule-of-three violation. A **codemod / migration harness** — ADR-0043 explicitly says build it when the first real migration appears; Phase 7.5 *defines* the migration concept but does not need the tool. A **general semantic-diff "category fence"** — ADR-0043 rejects it as a research project; the buildable form is the per-contract snapshot test, which this design ships. A **`v2` contract-versioning shim for `LanguagePack`** — there is no `v1` consumer to protect yet; ADR-0043 defers versioning machinery until a contract genuinely needs it.

## Risks (top 3–5)

1. **Premature freeze of `LanguagePack` (the mirror risk ADR-0043 names).** Two instances (TypeScript, Python) is the *minimum* evidence; it may not be *enough*. If Phase 8's language (say Java/Maven) needs a capability the six fields cannot express — e.g. a classpath resolver, or per-language sanitizer rules — `LanguagePack` grows, breaking both packs. **Mitigation:** the contract-snapshot fence makes that growth *loud and expected* (ADR-0043 calls a breaking `LanguagePack` grow "exactly the desired behaviour"); and we ship the freeze ADR as `Provisional Accepted` with `Review trigger: third language pack` per ADR-0043 commitment 5. The risk is contained, not eliminated.
2. **The TypeScript retrofit double-registration seam (Open Question Q1).** Phase 1 probes already self-register via `@register_probe` at module import. If the TypeScript pack *also* registers them, the registry raises `ProbeError`. The retrofit's correctness hinges on the pack *referencing* (not re-registering) probes whose modules are already imported by `codegenie/probes/__init__.py`. Get this wrong and either the build breaks (loud — acceptable) or, worse, the retrofit quietly diverges from the real registry. **Mitigation:** a unit test asserts the registry's probe set equals the union of all packs' `layer_a_probes` — drift becomes a red test. Critic should attack this hardest.
3. **Asymmetry between the two packs reduces the abstraction's proof value.** TypeScript's probes self-register independently; Python's flow through `register_language()`. The phase claims "Python validates the abstraction," but if the two packs are wired *differently*, Python only validates *half* of it. **Mitigation:** documented honestly (TypeScript pack component, tradeoffs); the conformance suite treats both packs identically *as inputs*, so the consumed contract is symmetric even if registration history differs.
4. **Conformance "semantically broken" detection is only as good as the fixture.** `test_search_adapter_is_not_a_stub` catches a stub only if the golden fixture exercises a query a stub would fail. A thin fixture (one file, no cross-references) lets a degenerate adapter pass. **Mitigation:** the mandatory golden fixture spec requires each language fixture to contain a genuine cross-file reference and a genuine dependency edge, asserted by a fixture-shape meta-test.
5. **`Language` newtype reuse vs. a fresh `LanguageId`.** Reusing the existing `Language` newtype (surfaced under `LanguageId`) avoids a duplicate, but `LanguagePack.language: Language` reads less pointedly than `: LanguageId`. A future reader may not connect `Skill.applies_to_languages: list[Language]` with `LanguagePack.language: Language` as the *same* concept. **Mitigation:** a one-line docstring on the newtype; surfaced for the synthesizer to rule on (Open Question Q2).

## Acknowledged blind spots

- **Performance of the Python dep-graph strategies is not characterized here** — the performance-lens design owns lockfile-parse throughput and large-monorepo cost; this design only mandates "≥ 1 node for the fixture" correctness.
- **Security posture of `scip-python` invocation** — sandboxing, the `ALLOWED_BINARIES` amendment, untrusted-lockfile parsing hardening — is the security lens's territory; this design assumes the existing `run_external_cli` discipline holds and does not re-derive it.
- **The `distroless-migration--python--pip` plugin is out of scope** by roadmap fiat; this design does not consider whether deferring it leaves the Python pack under-exercised for the migration task class.
- **Polyglot repos** (a repo that is *both* Node and Python) — ADR-0032 mentions per-dimension adapter dispatch, but this design does not specify how *two* `ProjectDetector`s both returning `Detected` interact, beyond "both probes run." The plugin-resolution layer (Phase 8) owns the multi-language workflow story; flagged so the synthesizer notes the boundary.
- **`register_language()` import-order fragility** is managed by the explicit collection point but not *enforced* — a misplaced import could register before a registry exists. The probe package has the same latent fragility today; not made worse, not fixed.

## Open questions for the synthesizer

1. **Q1 — the retrofit registration seam.** Should the TypeScript pack's probes register through `register_language()` (requiring `codegenie/probes/__init__.py` to *stop* importing those probe modules — an edit to a shipped collection point), or stay self-registered with the pack only *referencing* them (an asymmetry with Python)? This design chooses the latter (asymmetry, zero shipped-code edit) but it weakens the "Python validates the abstraction" claim. The security/performance designs may have a cleaner answer. **This is the single most important decision in the phase.**
2. **Q2 — `LanguageId` vs reusing `Language`.** Introduce a fresh `LanguageId` newtype for readability, or reuse the existing `Language` newtype to avoid a duplicate-by-addition (which ADR-0043 flags)? This design defaults to reuse; the synthesizer should rule.
3. **Q3 — does the `LanguagePack` freeze ADR ship `Provisional Accepted`?** ADR-0043 commitment 5 says freeze provisionally with a `Review trigger`. Two instances is thin evidence. Recommend `Provisional Accepted`, `Review trigger: third language pack lands`. Synthesizer to confirm against the other lenses.
4. **Q4 — where do `ProjectDetector` markers live to avoid duplication with `LanguageDetectionProbe`?** This design accepts a small, loud duplication (a tuple of marker filenames in the detector, also known to the probe) because de-duplicating would mean editing the shipped Phase 1 probe. The synthesizer should confirm this is the lesser evil versus a shared `catalogs/language_markers.yaml` both read (which *would* be addition-only and might be cleaner — flagged as a possible improvement over this design's choice).
5. **Q5 — conformance fixture minimum-richness spec.** Risk 4 depends on every golden fixture being rich enough to defeat a stub adapter. Should the fixture-shape requirement (≥ 1 cross-file ref, ≥ 1 dep edge) be a documented golden-fixture spec, a meta-test, or both? This design says both; the synthesizer should set the bar.
