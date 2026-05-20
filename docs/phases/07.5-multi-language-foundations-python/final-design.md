# Phase 7.5 — Multi-language foundations + Python: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-20
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

## Lens summary

The **best-practices** design dominates the structural shape — one new package (`codegenie.languages`), a frozen-Pydantic `LanguagePack` mirroring `codegenie.depgraph`, registry-driven conformance — because Phase 7.5 *is* a refactoring-discipline phase and idiomatic shape is the deliverable. The **security** design dominates the untrusted-input boundary: Python manifests/lockfiles are a directive language and `setup.py` is RCE-on-execution, so parse-only / byte-capped / no-exec discipline is load-bearing and folded in verbatim. The **performance** design contributes the *laziness* discipline (grammar wheels load on first use, a Node-only repo never imports `tree_sitter_python`) and the conformance-CI-budget concern — but its `LanguageDetectionPrepass` is **rejected outright** as a temporal-ordering bug. The synthesis **departs from all three** on four points the critic forced: (1) the language-identifier model is made explicit — `LanguagePack.language: Language` is the ecosystem axis, `grammars: tuple[SupportedLanguage, ...]` is a *modeled one-to-many relation* to grammar keys, no invented `"node"` Literal member; (2) `register_language()` is a **pure-addition Python-only fan-out** — TypeScript is retrofitted *by reference, not re-registration*, and the function is honest that it does not fan out probes for an already-self-registered pack; (3) there is **no two-phase commit** — the append-only registries cannot roll back, so `register_language()` validates-everything-first then commits, and the one residual (a mid-fan-out crash on a *new* pack) is contained by fail-fast-at-import plus a build-then-publish staging dict for the language registry itself; (4) the `LanguagePack` freeze ships **`Provisional Accepted` with `Review trigger: third language pack`**, and the contract is deliberately kept to the six roadmap-named capabilities — narrow, earned-as-far-as-two-instances-allow, provisional.

## Goals (concrete, measurable)

- **`[B]` One new top-level package.** `src/codegenie/languages/` is the only net-new package; Python probes go under the *existing* `codegenie.probes`, dep-graph strategies under the *existing* `codegenie.depgraph`, the grammar row into the *existing* `codegenie.grammars.lock`.
- **`[B]` Small public surface.** `codegenie.languages.__all__` ≤ 6 names (`LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`) — mirrors the 6-name `codegenie.depgraph` surface.
- **`[B+synth]` `LanguagePack` carries exactly the six roadmap-named capabilities** — `language`, `grammars`, `project_detector`, `layer_a_probes`, `dep_graph_strategies`, `search_adapter_module`. No seventh speculative field. (`package_managers` is *derived* from `dep_graph_strategies.keys()`, not a separate field — see Departures.)
- **`[S]` Total registration.** An incomplete `LanguagePack(...)` fails `mypy --strict` at the construction call site. A pack referencing an un-wired grammar key, a colliding probe name, or a colliding `PackageManager` key fails `register_language()` *loudly at import*, before any gather.
- **`[S]` Dep-graph parsing is pure.** Python dep-graph extraction performs zero network I/O and zero subprocess spawns — enforced by the existing `fence` + `import-linter` plus a new `tests/fence/test_depgraph_purity.py` AST fence over `src/codegenie/depgraph/python/`.
- **`[S]` `setup.py` is never executed.** `setup.py`/`setup.cfg` are read as text and parsed structurally (tree-sitter / INI). A repo whose only manifest is a hostile `setup.py` yields a `confidence="low"` "not statically analyzable" fact — never an RCE.
- **`[S]` Input hard caps.** Every Python manifest/lockfile parser enforces a byte cap, a parse-depth/entry cap, and a per-probe timeout *before* parsing — reusing the Phase 1 `SizeCapExceeded`/`DepthCapExceeded` machinery `LanguageDetectionProbe` already uses. An oversized or billion-laughs lockfile is rejected with a structured warning, not OOM/hang.
- **`[S]` `ALLOWED_BINARIES` minimal.** `pip`, `poetry`, `uv` are **not** added — Phase 7.5 never invokes them. `scip-python` is **deferred** (see Departures); the Python search adapter ships tree-sitter-first, so `ALLOWED_BINARIES` is **untouched** this phase.
- **`[P]` Language #2 is negligible-cost on language-#1 repos.** A Node-only gather never imports `tree_sitter_python`; the grammar wheel loads lazily on first Python parse (~80 ms once per process). The honest claim is *negligible*, not *zero* — the coordinator's existing `tier="base"` prelude + `language_filter` already filters Python probes out of a Node repo's wave at no new cost (see Departures, item 2).
- **`[P]` Conformance CI budget.** `tests/conformance/` whole-tier wall-clock stays within `make check`'s envelope: ~12 fast assertions × 2 languages over *committed fixture goldens*, plus one `gather` per language fixture. No re-gather-per-assertion; no `pytest-xdist`.
- **`[B]` Zero silent edits to shipped Phase 1–7 code.** Loud, compiler/snapshot-policed edits only: `SupportedLanguage` Literal `+1` (`"python"`), grammar `_DISPATCH` `+1` row, `PackageManager` Literal `+3` (`"pip"/"poetry"/"uv"`), additive schema `$ref`s, one collection-point import line. The full Phase 1–7 TS/JS regression suite runs unchanged and green as a hard gate.
- **`[B+S]` Conformance catches semantic breakage *and* fail-closed behavior.** A capability that type-checks but is semantically broken (a stub adapter, a no-op detector) fails conformance; adversarial fixtures (hostile `requirements.txt`, oversized lockfile, hostile `setup.py`) are first-class conformance cases — "fails closed on hostile input" is part of *passing*.
- **`[synth]` Tokens/run: 0.** Phase 7.5 introduces no LLM call and no new runtime service — the language axis is entirely on the deterministic side of ADR-0005.

## Architecture

```
   IMPORT TIME (once per process)
   ┌─────────────────────────────────────────────────────────────────────┐
   │  codegenie.languages.packs   — explicit-import collection point      │
   │    import .typescript   (pack #1 — RETROFIT, by reference)           │
   │    import .python       (pack #2 — NEW)                              │
   │  each pack module ends:  register_language(PACK)                     │
   └───────────────────────────────┬─────────────────────────────────────┘
                                   │
            register_language(pack: LanguagePack)         [synth]
              1. validate_pack(pack)   — totality + grammar-wired +
                 no-shadow (probe names, PackageManager keys) — ALL checks
                 run BEFORE any registry write
              2. language registry: build-then-publish (staging dict swap)
              3. Python-only fan-out:  probes + dep-graph strategies
                 (a pack flagged probes_self_registered=True is NOT
                  fanned out — the TypeScript retrofit path)
                                   │
        ┌──────────────────────────┼──────────────────────────────┐
        ▼                          ▼                              ▼
  codegenie.probes.registry  codegenie.depgraph.registry  codegenie.grammars.lock
  @register_probe (EXISTING)  @register_dep_graph_strategy  _DISPATCH +1 row
        │                     (EXISTING)                   (LOUD source edit)
        │                          │                              │
        ▼                          ▼                              ▼
  Python Layer A/B probes   pip / poetry / uv strategies   tree-sitter-python
  (new files under                (new files under         (lazy: imported on
   codegenie/probes/python/)        codegenie/depgraph/python/)  first language_for)

   GATHER (per run) — UNCHANGED coordinator
   ┌─────────────────────────────────────────────────────────────────────┐
   │ coordinator: prelude wave (tier="base") runs LanguageDetectionProbe  │
   │   → enriches RepoSnapshot.detected_languages  (EXISTING mechanism)   │
   │ rest wave (tier="task_specific"): language_filter._admits_languages  │
   │   filters Python probes out of a Node-only repo  (EXISTING predicate)│
   └───────────────────────────────┬─────────────────────────────────────┘
                                   ▼
                  ProbeOutput → two-pass sanitizer → writer
                  (each slice tagged with producing language)

   TB-2 (attacker-controlled repo): every Python probe/parser crosses it —
   parse-only · byte-capped · depth-capped · timeout-bounded · NO eval · NO net.

   tests/conformance/test_language_conformance.py
     @pytest.mark.parametrize over default_language_registry.all()
     + a collection-completeness guard (registry size == expected)
   tests/golden/languages/{typescript,python}/   — fixture repo + golden
   tests/fence/test_language_pack_contract.py    — LanguagePack contract snapshot
   tests/fence/test_depgraph_purity.py           — AST: no net/exec in python depgraph
```

## Components

### `LanguagePack`

- **Provenance:** `[B]` shape, `[S]` totality discipline, `[synth]` field set.
- **Purpose:** The total, frozen value that *is* a language — one required field per capability. A partial language is unrepresentable; an incomplete `LanguagePack(...)` is a `mypy --strict` error at the construction site. The single sanctioned shared-file surface for the language axis.
- **Interface:**
  ```python
  from pydantic import BaseModel, ConfigDict
  from codegenie.types.identifiers import Language, PackageManager
  from codegenie.grammars.lock import SupportedLanguage

  class LanguagePack(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

      language: Language                              # ecosystem axis: "typescript", "python"
      grammars: tuple[SupportedLanguage, ...]         # the one-to-many relation, modeled
      project_detector: ProjectDetector               # Protocol — "is this a $LANG repo?"
      layer_a_probes: tuple[type[Probe], ...]         # probe classes (manifest + maybe registrar)
      dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]
      search_adapter_module: str                      # "module:ClassName" import path (ADR-0032)
      probes_self_registered: bool = False            # True for the TS retrofit; see register_language
  ```
  - *Inputs:* construction in trusted pack-module code; never parsed from external data.
  - *Outputs:* the value; consumed by `register_language`.
  - *Errors:* none at runtime — incompleteness is a `mypy` error; an extra field is a `pydantic.ValidationError` (`extra="forbid"`).
- **Internal design:** Frozen Pydantic v2 model — the project's one sanctioned contract framework (ADR-0010); the `frozen=True` model is what `ProbeOutput`, manifests, and events already use. `tuple`/`Mapping` fields, not `list`/`dict`, so the frozen value is genuinely immutable. The pack holds **references** (probe classes, strategy callables, a tuple of grammar keys, an import-path string) — no behavior, no I/O. Two critic-driven changes from all three inputs: (a) `grammars: tuple[SupportedLanguage, ...]` — the critic correctly flagged that "TypeScript" is *three* grammar keys (`typescript`, `tsx`, `javascript`); modeling the one-to-many relation kills the "one language = one grammar" conflation and uses the closed `SupportedLanguage` Literal, not a raw `str` (kills the best-practices `grammar_name: str` primitive-obsession). (b) `probes_self_registered` is an explicit, typed discriminator for the retrofit asymmetry — see `register_language`.
- **Why this choice over the alternatives:** Conflict CR-1 (pack type) and CR-7 (grammar field). Pydantic over frozen dataclass: `extra="forbid"` makes a typo'd capability loud and the model is the project's contract idiom — security's "the type is the isolation" and best-practices' "the one Pydantic-coupled type" agree; performance called it immaterial. The `tuple[SupportedLanguage, ...]` field is a *departure from all three* — none modeled the one-to-many relation; the critic named it the single missed structural pattern.
- **Tradeoffs accepted:** The pack is a *broad* value (six fields) where ADR-0043 prefers *narrow* contracts. Justified: the six are the irreducible set the roadmap names, and grouping them into one resolved-once value is the abstraction. The freeze is *provisional* (`Review trigger: third language pack`) and the contract-snapshot fence makes every growth loud. `arbitrary_types_allowed=True` is needed for the `type[Probe]` / callable fields — a known, documented Pydantic pattern.

### `register_language()`

- **Provenance:** `[synth]` — departs from all three on failure semantics and the retrofit seam.
- **Purpose:** Fan one validated `LanguagePack` into the existing decomposed registries — the one new privileged operation of the phase.
- **Interface:** `register_language(pack: LanguagePack) -> None`. Idempotent within a process (re-registering the same `language` is a no-op). Raises `LanguageRegistryError` on totality/grammar/collision failure. Input is trusted typed code, not external data.
- **Internal design:** **Validate-everything-first, then commit** — *not* two-phase commit (the registries have no `unregister`; see CR-2). The sequence:
  1. `validate_pack(pack)` runs *all* checks before *any* registry write: totality (Pydantic already guarantees it), every `grammars` member is in `grammars.lock.supported_languages()`, the `search_adapter_module` import path resolves, and the **no-shadow check** — no probe name in `layer_a_probes` and no `PackageManager` key in `dep_graph_strategies` is already claimed by a *different* pack. Any failure raises `LanguageRegistryError` and *nothing* is written.
  2. The language registry write uses **build-then-publish**: the pack is added to a fresh copy of the registry dict, then the copy is swapped in (atomic at the Python-object level). This is the buildable substitute for the security design's unbacked "rollback" — the critic's named missed pattern.
  3. **Python-only fan-out:** if `pack.probes_self_registered` is `False`, fan `layer_a_probes` into the probe registry via `register_probe` and `dep_graph_strategies` into `DepGraphRegistry`. If `True` (the TypeScript retrofit), **skip the probe fan-out** — those probe modules already fired `@register_probe` at their own import; re-registering would raise `ProbeError`. The grammar `_DISPATCH` rows are *never* written by `register_language` — they are a compiler-policed source edit (ADR-0043 loud edit); `validate_pack` only *asserts* they are present.
  Residual: a mid-fan-out crash on a *genuinely new* pack (step 3, probe 3 of 5) leaves the probe registry partly written. This is contained, not eliminated: it happens *at import, before any gather*, fails the process loudly, and is covered by a unit test asserting a deliberately-broken pack's partial registration is detectable (the registry reports the inconsistency). A full rollback would require editing the shipped append-only registries — an ADR-0043-forbidden silent edit. We accept import-time fail-fast as the honest containment.
- **Why this choice over the alternatives:** Conflict CR-2 (failure semantics) — the critic identified this as *the* decision that precedes everything. Security wanted two-phase-commit-with-rollback (impossible — substrate has no `unregister`); performance and best-practices shipped straight-line fan-outs (best-practices' crashes on its own first input). The synthesis resolves it: `register_language` is a **pure addition** — TypeScript is retrofitted *by reference* (`probes_self_registered=True`), so the function never double-registers; validate-first makes collisions loud pre-write; build-then-publish gives the *language registry* real atomicity; the *one* irreducible residual (partial probe fan-out on a new pack) is contained by import-time fail-fast and surfaced honestly rather than papered over with a pattern the substrate can't support.
- **Tradeoffs accepted:** The retrofit is asymmetric — TypeScript's probes self-register, Python's fan out through the pack. This is honest and typed (`probes_self_registered`), not papered over. The conformance suite consumes both packs *identically as inputs*, so the *contract* is symmetric even though *registration history* differs — which is what "Python validates the abstraction" actually needs. The residual partial-fan-out window is real but bounded to process startup.

### `LanguageRegistry` + `default_language_registry`

- **Provenance:** `[B]`.
- **Purpose:** Collect language packs; the registry-driven enrollment surface for `tests/conformance/`.
- **Interface:**
  ```python
  class LanguageRegistry:
      def register(self, pack: LanguagePack) -> None: ...   # build-then-publish; dup raises
      def get(self, language: Language) -> LanguagePack: ... # LanguageRegistryError if absent
      def all(self) -> tuple[LanguagePack, ...]: ...         # sorted by language, deterministic

  default_language_registry: LanguageRegistry
  ```
- **Internal design:** A plain class wrapping `dict[Language, LanguagePack]` — the exact shape of `DepGraphRegistry`/`FreshnessRegistry`. Duplicate registration raises `LanguageRegistryError` naming both call sites. Tests construct independent instances. `all()` is sorted for determinism (golden files depend on it).
- **Why this choice over the alternatives:** No conflict — all three agree on a plain registry mirroring `codegenie.depgraph`. Carried forward.
- **Tradeoffs accepted:** Import-order matters (a pack must import after the registries exist) — managed by the explicit `packs/__init__.py` collection point, the identical discipline `codegenie/probes/__init__.py` already uses.

### `ProjectDetector` + the shared marker catalog

- **Provenance:** `[B]` shape, `[synth]` resolves the duplication via the catalog (best-practices' own flagged better option).
- **Purpose:** Answer "is this repo a $LANGUAGE project?" — the roadmap-named "project detector" capability.
- **Interface:**
  ```python
  class ProjectDetector(Protocol):
      def detect(self, repo: RepoSnapshot) -> DetectionResult: ...
  ```
  `DetectionResult` is a sum type — `Detected(confidence, marker_files) | NotDetected`.
- **Internal design:** A `typing.Protocol` (structural, no inheritance — ADR-0032's adapter idiom). Detection is **additive / monotone** (security's pattern): a polyglot repo is detected as *both* languages; a detector never *demotes* another language's verdict — a planted `pyproject.toml` cannot mis-route a Node repo, only add a (correct, if real) Python verdict. **The marker knowledge lives in a new addition-only `src/codegenie/languages/markers.py` `Final` catalog** — a module-level mapping `Language -> tuple[marker-glob, ...]` — that *both* the per-language `ProjectDetector` *and* (read-only, by import) `LanguageDetectionProbe`-adjacent code can consult. This **departs from best-practices' chosen path** (which duplicated marker tuples into each detector and admitted in its own Q4 that a shared catalog "would be cleaner and is addition-only"). The critic flagged the duplication as the exact anti-pattern ADR-0043 names; the catalog is the addition-only fix best-practices itself identified.
- **Why this choice over the alternatives:** Conflict CR-3 (marker duplication). The shared `markers.py` catalog is addition-only (a new file — no edit to the shipped `LanguageDetectionProbe`), kills the duplication, and is the `_MONOREPO_PRECEDENCE`/`_LOCKFILE_PRECEDENCE` idiom the codebase already uses. Best-practices found the better option and the synthesis ships it.
- **Tradeoffs accepted:** `LanguageDetectionProbe` is *not* edited to read `markers.py` — that would be a silent edit; it keeps its own Phase-0/1 marker logic. The catalog is the source of truth for the *new* detectors; a conformance assertion proves the probe and the detectors agree on the golden fixtures. Over-detection (a stray `.py` flags Python) is accepted as the lesser evil vs. under-detection (silent skip) — but tightened relative to security's stance: the Python `ProjectDetector` returns `Detected` with `confidence="high"` only on a *real* manifest (`pyproject.toml`/`setup.py`/`setup.cfg`/`requirements*.txt`/`Pipfile`), and `confidence="low"` for a bare `*.py` tree with no manifest. This narrows the attacker's "force Python parsers to run" surface (CR-5) without under-detecting an unconventional real project.

### Python Layer A/B probes

- **Provenance:** `[B]` inventory, `[S]` hardening.
- **Purpose:** Language-detection, build-system, manifest, and import-graph analogs for Python — facts, not judgments.
- **Interface:** The frozen `Probe` ABC (`src/codegenie/probes/base.py`) — *consumed unchanged* (ADR-0007/0043), two-arg `run(self, repo, ctx)`. New sub-package `src/codegenie/probes/python/`. Layer A: `PythonProjectProbe` (`tier="base"`, runs in the prelude wave — this is what enriches `detected_languages` for Python), `PythonBuildSystemProbe`, `PythonManifestProbe`. Layer B: `PythonImportGraphProbe`.
- **Internal design:** Functional core / imperative shell — pure parsing helpers; `run()` is the only impure surface and only *reads*. **Hard caps before parse** (security): byte cap, entry/depth cap, per-probe `timeout_seconds` — reusing the Phase 1 `SizeCapExceeded`/`DepthCapExceeded`/`SymlinkRefusedError` machinery `LanguageDetectionProbe` already raises, so a probe at a cap returns a partial fact with `confidence="low"` and a `_WARNING_IDS` entry (`python.manifest_oversized`, `python.lockfile_truncated`, `python.setup_py_not_static`). `setup.py` is parsed *structurally* (tree-sitter) — never executed. Tight `declared_inputs` globs (`pyproject.toml`, `requirements*.txt`, `Pipfile*`, `*.lock`, `**/*.py`) so the content-addressed cache invalidates surgically — editing a Python file leaves every Node probe's cache valid.
- **Why this choice over the alternatives:** Conflict CR-4 (probe hardening). Performance's design omitted `setup.py` entirely (the critic caught it) and assumed Python Layer A/B is "smaller than Node's A–G" with no inventory; the synthesis adopts security's parse-only/byte-capped discipline and best-practices' concrete inventory, and **drops performance's unverified 1.15×-parity goal** (CR-4 scoring: a guessed ceiling with no test that would catch a breach is not a measurable — replaced with "Python gather completes within `make check`'s envelope on the fixture", a checkable claim).
- **Tradeoffs accepted:** A probe that hits a cap returns a partial fact with low confidence — honest-confidence over completeness (commitment 3). The Python Layer B set is deliberately minimal (one import-graph probe); reflection/CI/deployment Python probes are *not* in scope — Phase 7.5 proves the *axis*, not Python feature-parity with Node's full A–G.

### Python dep-graph strategies (pip / poetry / uv)

- **Provenance:** `[S]` (the directive-language discipline is load-bearing and best-practices missed it).
- **Purpose:** `dep_graph.consumers`-class extraction for the three Python package managers.
- **Interface:** Registered via `@register_dep_graph_strategy(PackageManager)` for keys `"pip"`, `"poetry"`, `"uv"` (`PackageManager` Literal `+3`, a loud compiler-policed edit). New sub-package `src/codegenie/depgraph/python/`.
- **Internal design:** **`requirements.txt` is parsed as a directive language, not a manifest** (security; best-practices treated it as "just another lockfile format" and the critic caught it). Every non-pinned-dependency directive is recorded as a *fact*, never acted on: `-e .`/`-e <path>` → `unresolved: editable install`; `git+...`/VCS URLs → `unresolved: vcs source`; `--index-url`/`--extra-index-url` → `index_override_present{url_host}` (host only — the full URL is attacker-controlled) and **otherwise ignored — the parser never honors an index URL**; `-r <path>` is followed *only* if the path resolves inside the repo root, else `unresolved: out-of-tree include`. **Unknown directive → fail closed** (`unresolved: unknown directive` + warning) — never silently dropped (security Risk #4). `poetry.lock`/`uv.lock`/`Pipfile.lock` are TOML/JSON parsed with byte+depth caps. No package-manager binary is invoked; no network is touched. Three concrete strategies, three concrete parsers — **no premature "generic Python lockfile reader" abstraction** (best-practices; rule-of-three — revisit at a fourth Python package manager).
- **Why this choice over the alternatives:** Conflict CR-4. Security's directive-language model wins decisively — best-practices' framing would under-parse `requirements.txt` and silently drop real dependencies, a commitment-3 (honest confidence) violation.
- **Tradeoffs accepted:** Dep-graph *completeness* on adversarial inputs is explicitly sacrificed — a repo using only VCS deps yields a near-empty graph with `confidence="low"` and explicit unresolved-reasons. Chasing those would mean network resolution at gather time — a hard no.

### Python search adapter (tree-sitter-first; `scip-python` deferred)

- **Provenance:** `[S]` Open-Q3 recommendation, promoted to the decision.
- **Purpose:** Implement the ADR-0032 search-adapter Protocols for Python.
- **Interface:** The ADR-0032 `Protocol`s — `ImportGraphAdapter` (mandatory), `DepGraphAdapter`, `TestInventoryAdapter`. Registered through the `vulnerability-remediation--python--pip` plugin manifest's `contributes.adapters` map (the existing mechanism, unchanged).
- **Internal design:** Phase 7.5 ships a **tree-sitter-backed** `ImportGraphAdapter` (and `DepGraphAdapter`/`TestInventoryAdapter`) — always-fresh, no external binary, no `ALLOWED_BINARIES` change. The `scip-python` `ScipAdapter` is **deferred to a fast-follow** (ADR-0032 explicitly makes `ScipAdapter` optional; the minimum adapter surface is `ImportGraphAdapter` + `TestInventoryAdapter`). `confidence()` is the ADR-0032-as-written `-> float` — **the synthesis does not invent the "ADR-0033 amendment to ADR-0032" the security design asserted** (CR-1 of the security attacks: that amendment does not exist; changing the float-returning Protocol every shipped adapter implements would be a cross-cutting silent edit to pre-Phase-7 frozen surface). Degradation works exactly as ADR-0032 specifies: a low `confidence()` float drives the Bundle Builder's declared-fallback logic.
- **Why this choice over the alternatives:** Conflict CR-6 (`scip-python`). Security itself recommended deferring `scip-python` (its Open-Q3) yet built a full TB-4 jail for it — the critic flagged the self-contradiction. The synthesis takes security's *recommendation* and drops the *contradicting machinery*: tree-sitter-first means no new binary, no `ALLOWED_BINARIES` amendment, no jail-escape surface, no cgroup-memory-cap question — the entire `scip-python` security apparatus becomes unnecessary for this phase. Performance's "SCIP as the precision rung" is a real future want, but Phase 7.5's job is to prove the axis; SCIP precision is a Phase-8-Planner concern.
- **Tradeoffs accepted:** Python loses symbol-precise `scip.refs` until the fast-follow lands. Acceptable — ADR-0032's minimum adapter surface does not include `ScipAdapter`; tree-sitter is the always-fresh floor; and the deferral keeps `ALLOWED_BINARIES` and the subprocess-jail surface untouched.

### `tests/conformance/` tier

- **Provenance:** `[B]` shape, `[P]` budget discipline, `[S]` adversarial fixtures.
- **Purpose:** Catch the failure `mypy` cannot — a capability slot *filled and type-checking* but *semantically broken*.
- **Interface:** One module, `tests/conformance/test_language_conformance.py`, parameterized over `default_language_registry.all()` with the `Language` as `pytest.param(..., id=lang)`. Each language ships a mandatory fixture repo + golden under `tests/golden/languages/{language}/`.
- **Internal design:** Per-language capability assertions: `test_grammar_loads`, `test_detector_detects_own_fixture` (`Detected`, `confidence="high"`), `test_layer_a_probes_produce_nonempty_slices`, `test_dep_graph_strategy_resolves`, `test_search_adapter_is_not_a_stub` (a known query returns a non-empty, non-degenerate result against the fixture — the "passes mypy but broken" catch), `test_golden_matches`. **Adversarial fixtures are first-class** (security): a hostile `requirements.txt`, an oversized `poetry.lock`, a hostile `setup.py` are conformance cases — "fails closed" is part of *passing*. **CI-budget discipline** (performance): each language's fixture is gathered *once* per session (`@pytest.fixture(scope="session")`) and every assertion reads the cached `RepoContext`; **no `asyncio.gather` of fixture builds, no `pytest-xdist`** — the critic correctly showed performance's parallel-warming mechanism fights pytest and the project bans xdist. Tier wall-clock = `sum(per-language single gather)` + `sum(fast assertions)`, which for 2 languages over modest fixtures stays inside `make check`. **A collection-completeness guard** (the critic's auto-disenrollment hole, CR-8): a top-of-module assertion `len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT` — if a pack module fails to import (broken wheel, import-order bug), the suite *fails loudly* rather than silently collecting fewer parameters.
- **Why this choice over the alternatives:** Conflict CR-5 (conformance design). Best-practices' registry-parameterization is idiomatic and carried forward, *but* its auto-enrollment is also a silent auto-*disenrollment* hole — the synthesis adds the completeness guard. Security's adversarial fixtures are folded in. Performance's session-fixture caching is kept; its parallel-warming is dropped as unbuildable.
- **Tradeoffs accepted:** Session-scoped fixtures couple tests through shared state — contained because the cached `RepoContext` is an immutable Pydantic value. The fixture must be *rich enough* to defeat a stub adapter (≥1 cross-file reference, ≥1 dependency edge) — a documented golden-fixture spec plus a fixture-shape meta-test (best-practices Risk #4 + Q5).

### `LanguagePack` contract-snapshot fence

- **Provenance:** `[B]` — and it *resolves* critic finding (f), it does not dodge it.
- **Purpose:** The roadmap's "category-based extension-by-addition fence" — realized as ADR-0043 commitment 3 *explicitly* prescribes.
- **Interface:** `tests/fence/test_language_pack_contract.py` + `tests/fence/snapshots/language_pack_contract.v1.json`.
- **Internal design:** A snapshot test pinning the `LanguagePack` field set + types into `language_pack_contract.v1.json` — exactly as `tests/unit/test_probe_contract.py` pins the probe ABC against `probe_contract.v1.json`. The pack *file* stays freely editable; the snapshot test fails iff the *contract* (field names/types) changed — the desired loud signal when a genuinely new capability category is added. **No allowlist rows** (ADR-0043 commitment 2 — Phase 7's allowlist is the *last*). The planted-silent-edit requirement is realized as: plant an edit that adds a `LanguagePack` field → the snapshot test goes red.
- **Why this choice over the alternatives:** Conflict CR-9 — and the **resolution of critic finding (f)**. The critic claimed best-practices "silently downgraded" the category fence and left a roadmap exit criterion unsatisfiable. Re-reading the source documents resolves it: ADR-0043 commitment 3 *explicitly* says the buildable form of a category fence is a per-contract snapshot test ("the probe-ABC pattern"), and the roadmap's *own* test-architecture table row 7.5(c) says verbatim "new frozen surfaces use a contract + snapshot test (the probe-ABC pattern), **not allowlist rows**". The "category-based fence" in the roadmap exit criteria *is* the contract-snapshot test in the roadmap's and ADR-0043's own framing — there is no contradiction to paper over; best-practices was *correct* and merely under-explained the equivalence. The synthesis states the equivalence explicitly so no future reader re-derives the false contradiction.
- **Tradeoffs accepted:** A snapshot test catches a *`LanguagePack`-contract* change, not an arbitrary silent edit anywhere in `codegenie.languages`. **A silent edit to a Node probe body is caught by the full Phase 1–7 regression suite running as a hard gate** — which is precisely ADR-0043 commitment 1's "non-contract code is protected by the regression suite + review." The roadmap's "planted silent edit" is exercised at *two* levels: a planted `LanguagePack` field-add → snapshot fence red; a planted Node-probe-body change → Phase 1–7 regression suite red. Both are stated in the test plan.

## Data flow

End-to-end run: `codegenie gather ./hostile-python-repo` — a `pyproject.toml`, a `requirements.txt` with `-e .` + `git+https://attacker/...` + `--index-url http://attacker/`, a 200 MB `poetry.lock`, a `setup.py` calling `os.system(...)`.

1. **Import time `[synth]`.** `codegenie.languages.packs.__init__` explicitly imports `typescript` then `python`. Each module ends `register_language(PACK)`. TypeScript: `validate_pack` passes, `probes_self_registered=True` → the language registry records the pack, **no probe fan-out** (Phase 1 probes already self-registered). Python: `validate_pack` passes (grammar key `"python"` is in `_DISPATCH`, no probe-name/`PackageManager` collision), build-then-publish records the pack, then the Python-only fan-out registers `PythonProjectProbe`/`PythonBuildSystemProbe`/`PythonManifestProbe`/`PythonImportGraphProbe` + the `pip`/`poetry`/`uv` strategies. Had Python tried to claim a Node probe name, `validate_pack` would raise `LanguageRegistryError` here — before any repo is read.
2. **Prelude wave `[P]` (EXISTING coordinator).** The coordinator runs `tier="base"` probes first: `LanguageDetectionProbe` (Node) and `PythonProjectProbe` (Python) walk the tree and enrich `RepoSnapshot.detected_languages`. **This resolves the temporal-ordering bug** — detection is a *probe in the prelude wave*, not a pre-pass reading a field that does not exist yet.
3. **Rest wave `[P]` (EXISTING coordinator).** `tier="task_specific"` probes are filtered by `language_filter._admits_languages(probe.applies_to_languages, snapshot.detected_languages)` — the *existing* predicate. A Node-only repo: Python probes are filtered out, `tree_sitter_python` is never imported. This repo has Python markers, so Python probes run.
4. **Manifest probe `[S]`.** `PythonManifestProbe` reads `pyproject.toml` — byte cap checked *first*, TOML parsed with a depth cap. The 200 MB `poetry.lock` hits the byte cap *before parse* → rejected with `python.lockfile_truncated`, `confidence="low"`. No OOM.
5. **Dep-graph strategy `[S]`.** The `requirements.txt` is parsed as a directive language: `-e .` → `unresolved: editable install`; `git+https://attacker/...` → `unresolved: vcs source`; `--index-url http://attacker/` → `index_override_present{url_host: "attacker"}` and **ignored — no fetch**. Near-empty graph, `confidence="low"`, explicit unresolved-reasons. `tests/fence/test_depgraph_purity.py` is the structural proof no fetch is possible.
6. **`setup.py` `[S]`.** Read as text, parsed structurally with tree-sitter; the `os.system(...)` is *observed as a fact* ("dynamic call; not statically resolvable", `confidence="low"`). **Never executed.**
7. **Grammar load `[P]`.** The first Python probe to parse code calls `language_for("python")` → first call imports `tree_sitter_python` (~80 ms, once), memoized. Every subsequent parse is a dict lookup.
8. **Search adapter `[synth]`.** The tree-sitter `ImportGraphAdapter` walks Python imports — always-fresh, no external binary.
9. **Sanitize + write.** Every Python slice flows through the two-pass sanitizer; bidi/zero-width unicode in package names is neutralized; each slice tagged with `language: python`. `repo-context.yaml` + `raw/*.json` written. Audit anchors record `register_language` outcomes, `unresolved`/`index_override_present` events, dispatch order.

The run **completes** with honest low-confidence facts and explicit unresolved-reasons — having fetched nothing, executed nothing from the repo, corrupted no registry. Nothing in steps 2–9 is new *pipeline* code: the coordinator, sanitizer, and writer never learned the word "Python" — they iterate registries that now have more rows.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Incomplete `LanguagePack(...)` | `mypy --strict` at the construction site | Build fails; no runtime path | Author supplies the field | `[S]/[B]` |
| `LanguagePack` references an un-wired grammar key | `validate_pack` asserts `grammars ⊆ supported_languages()` → `LanguageRegistryError` at import | Loud failure at startup, before any gather | Add the `_DISPATCH` row + PyPI wheel | `[B]` |
| Pack registers a probe name / `PackageManager` key already claimed | `validate_pack` no-shadow check → `LanguageRegistryError` before any write | Registration raises pre-write; conflicting key named | PR blocked | `[S]` |
| `register_language` mid-fan-out crash on a *new* pack (probe 3 of 5) | Import fails loudly; a unit test asserts the partial state is detectable | Bounded to process startup — *before any gather* | Fix the pack; re-import | `[synth]` |
| Duplicate language registration | `LanguageRegistry.register` raises `LanguageRegistryError` naming both call sites | Build-then-publish; the partial dict is never published | Remove the duplicate | `[B]` |
| Capability filled but semantically broken (stub adapter, no-op detector) | `tests/conformance/` | CI red; cannot merge | Fix the capability | `[B]/[S]` |
| A pack module fails to import (broken wheel, import-order bug) | `tests/conformance/` collection-completeness guard (`len(all()) == EXPECTED`) | Suite fails *loudly* — no silent auto-disenrollment | Fix the import | `[synth]` (critic CR-8) |
| `tree_sitter_python` wheel missing from runtime closure | `language_for("python")` raises `GrammarLoadRefused`; `make fence` asserts the pin | Node gather unaffected (lazy load) | Restore the `pyproject.toml` pin | `[P]/[B]` |
| `requirements.txt` with VCS URL / `--index-url` / `-r /etc/passwd` | Dep-graph directive classifier; `-r` path-escape check | Recorded as `unresolved`/`index_override_present`; **no fetch** | Partial graph, `confidence="low"`, explicit reasons | `[S]` |
| Unknown `requirements.txt` directive | Directive classifier default-deny | `unresolved: unknown directive` + warning — never silently dropped | Classifier extended in a later PR | `[S]` |
| Hostile `setup.py` (arbitrary Python) | `forbidden-patterns` hook + probe AST test forbidding `exec`/`importlib` of repo files | Read as text only; never executed | `confidence="low"` "not statically analyzable" | `[S]` |
| 200 MB / billion-laughs lockfile | Byte cap + depth cap *before* parse (Phase 1 `SizeCapExceeded` machinery) | Parser rejects; `python.manifest_oversized` | Partial result, `confidence="low"`; no OOM/hang | `[S]` |
| Planted silent edit — `LanguagePack` field added | `tests/fence/test_language_pack_contract.py` snapshot goes red | Loud contract-change signal | Treated as a sanctioned `LanguagePack` growth | `[B]` |
| Planted silent edit — Node probe body changed | Full Phase 1–7 regression suite (hard gate) | CI red | The "added by addition" claim is falsified; fix before merge | `[B]/[S]` |
| Python golden fixture drift | `tests/golden/languages/python/` golden mismatch | CI red | Inspect diff; regenerate the golden *deliberately* (reviewed act) | `[B]` |

## Resource & cost profile

- **Tokens/run:** 0. No LLM call; the language axis is entirely on the deterministic side of ADR-0005. `$/PR` unchanged.
- **New runtime dependency:** `tree-sitter-python` — one PyPI wheel (~2–4 MB), loaded lazily and memoized once per process, comparable to `tree-sitter-typescript` already in the closure. **No new binary** (`scip-python` deferred → `ALLOWED_BINARIES` untouched). No new runtime service.
- **Cold-start cost:** `register_language` for two packs — `validate_pack` (a handful of set-membership checks) + a Python-only fan-out of ~4 probe registrations + 3 strategy registrations + 2 dict inserts. Microseconds. No `importlib.metadata` scan.
- **Wall-clock — Node repo:** unchanged. The coordinator's *existing* `tier="base"` prelude + `language_filter` predicate filters Python probes out of a Node-only repo's wave — this is *not new dispatch code*, it is the mechanism Phase 1 already ships. `tree_sitter_python` is never imported. (This is the honest version of performance's "language #2 is free" — *negligible*, achieved by reusing the existing filter, not by a new pre-pass.)
- **Wall-clock — Python fixture repo:** completes inside `make check`'s envelope; the only genuinely new cost is the one-time ~80 ms `tree_sitter_python` import. **No 1.15×-parity numeric gate** — that was a guessed ceiling with no test that would catch a breach (critic CR-4); replaced with a checkable "completes within `make check`" claim.
- **Memory/worker:** the second tree-sitter C extension adds ~+15 MB RSS, paid only by a worker that *gathers* a Python repo (lazy load — registration alone costs nothing).
- **CI cost:** `tests/conformance/` — one module, ~6 capability checks × 2 languages ≈ 12 fast assertions over committed goldens, plus one `gather` per language fixture (session-scoped). The cost-of-security line items (byte/depth caps, adversarial fixtures, the depgraph-purity AST fence) add a few seconds of CI — cheap. The full Phase 1–7 regression suite runs unchanged as the largest CI cost and the hard gate.
- **Where security/best-practices trade against performance:** the adversarial conformance fixtures (~5 extra fixture repos + goldens) add CI seconds performance's lens would prefer to avoid — accepted, because "fails closed on hostile input" being conformance-verified is worth more than the seconds. Authoring a *total* `LanguagePack` (six mandatory capabilities) is deliberately more work than a partial one — the human cost of "a half-registered language cannot exist."

## Test plan

**Unit — `codegenie.languages` (≥ 95% coverage):**
- `LanguagePack` rejects extra fields (`extra="forbid"`), is genuinely frozen, requires all six capabilities (omission → `mypy` *and* runtime error).
- `LanguageRegistry` register/get/all round-trips; `all()` deterministically sorted; duplicate registration raises `LanguageRegistryError` naming both origins; independent instances do not pollute; build-then-publish never publishes a partial dict.
- `register_language` — `validate_pack` runs *all* checks before any write (inject a pack failing the no-shadow check → assert all three registries byte-identical to pre-call); idempotence (register the same pack twice → no double-write); a pack with `probes_self_registered=True` does *not* fan probes out; a pack with an un-wired grammar key raises `LanguageRegistryError`.
- Intent-over-behavior (Rule 9): the fan-out test asserts probes are *callable and dispatchable*, not merely "a key exists."

**Unit — Python probes & strategies:** each Layer A/B probe against in-memory fixtures (detected / not-detected, malformed `pyproject.toml`, missing lockfile); each dep-graph strategy against a minimal lockfile and a malformed one; typed-error paths asserted (the probe records the error ID, never crashes).

**Adversarial (load-bearing — security):**
- `requirements.txt` carrying `-e .`, `git+https://...`, `--index-url http://attacker/`, `--extra-index-url`, `-r /etc/passwd`, `-r ../../../etc/passwd`, and an *unknown* directive → parser completes; **network monitor asserts zero outbound connections**; subprocess monitor asserts zero spawns; out-of-tree `-r` rejected; unknown directive → `unresolved`; results carry explicit reasons.
- Hostile `setup.py` (`os.system`, `subprocess`, `__import__`) → read as text, never executed; AST test asserts no `exec`/`eval`/`importlib`-of-repo-file in the Python probe code.
- Oversized (`>5 MiB`) and billion-laughs `poetry.lock`/`uv.lock`/`Pipfile.lock` → rejected before parse, `python.manifest_oversized` warning, no OOM/hang (timeout-bounded).
- Bidi/zero-width/ANSI-escape injection in package names → sanitizer neutralizes before `repo-context.yaml`.

**Integration:** `codegenie gather` on `tests/golden/languages/python/` end to end — coordinator → Python probes → sanitizer → writer — `repo-context.yaml` produced and schema-valid.

**Conformance (`tests/conformance/`):** the parameterized suite — every registered language, every capability, against its golden fixture; the deliberate "stub search adapter fails conformance" negative test; adversarial fixtures (hostile `requirements.txt`, oversized lockfile, hostile `setup.py`) as part of *passing* conformance; the collection-completeness guard (`len(all()) == EXPECTED`).

**Golden (`tests/golden/languages/{language}/`):** mandatory fixture repo + committed golden `RepoContext` per language; a golden-regen idempotence test; a fixture-shape meta-test (each fixture has ≥1 cross-file reference + ≥1 dependency edge, so a stub adapter cannot pass).

**Fence / structural:**
- `tests/fence/test_language_pack_contract.py` — the `LanguagePack` contract snapshot; planted-`LanguagePack`-field-add → red.
- `tests/fence/test_depgraph_purity.py` — AST-walk over `src/codegenie/depgraph/python/` asserting no `urllib`/`requests`/`http`/`socket`/`subprocess` import and no network/exec call.
- `make fence` extended: `tree-sitter-python` wheel present *and* no new `FORBIDDEN_LLM_SDK` rode in; `import-linter` contracts updated for the new Python sub-packages.
- `ALLOWED_BINARIES` closed-set regression: `pip`/`poetry`/`uv`/`scip-python` are **not** present (this phase adds none).
- Planted silent edit at the *probe-body* level — change a Node probe body → the full Phase 1–7 regression suite goes red.

**Regression gate:** the entire Phase 1–7 Node/TypeScript suite (~2,300 tests) runs unchanged and green as a hard CI gate — the load-bearing proof Python edited nothing.

**Property test:** one property over `LanguageRegistry` — for any sequence of distinct packs, `all()` returns them sorted and `get(p.language) == p`. Modest and targeted; no over-investment where example tests are clearer.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Source design | Pattern not applied (and why) |
|---|---|---|---|---|
| `LanguagePack` as a frozen total Pydantic value, one required field per capability | Make illegal states unrepresentable + value object | A partial language is a real bug `mypy` can forbid for free — an incomplete `LanguagePack(...)` is a construction-site error before any test runs | `[B]` (shape) + `[S]` (totality) | **Builder** — a `LanguagePackBuilder` reintroduces the partial-pack state the frozen total value exists to forbid |
| `LanguagePack.grammars: tuple[SupportedLanguage, ...]` — the one-language-to-many-grammars relation modeled | Modeled relation + closed sum type | "TypeScript" is three grammar keys (`typescript`/`tsx`/`javascript`); the relation must be a typed field, not a raw `str` | `[synth]` (critic's named missed pattern) | **`grammar_name: str`** — primitive obsession on a domain ID keying into a closed `Literal` (best-practices' rejected choice) |
| `register_language()` fans a pack into three existing decomposed registries | Registry pattern + Open/Closed at the file boundary | One call, one mental model — the three registries keep their single responsibilities; a new language is new files + one import line | `[B]` | **Unified mega-registry** — would force editing Phase 1–7 registration sites (a silent-edit storm) and centralize three orthogonal concerns |
| `register_language()` validate-all-then-commit; language registry via build-then-publish | Build-then-publish (staging-then-swap) | The append-only registries have no `unregister` — atomicity is *built by constructing the new state complete then swapping*, the only buildable form over the substrate | `[synth]` (critic's named missed pattern) | **Two-phase commit** — names a prepare/abort protocol the append-only registries cannot deliver; pattern-as-decoration |
| `ProjectDetector` / search adapters as `typing.Protocol` | Structural typing / duck-typed contract | A new language implements a Protocol with no inheritance coupling; ADR-0032's settled idiom | `[B]` (+ ADR-0032) | **ABC inheritance** — couples every detector to a base class; Protocols give the same guarantee with looser coupling |
| `DetectionResult` as `Detected \| NotDetected` | Tagged union / sum type | "Detected vs not" is a state with per-variant fields; `match` + `assert_never` makes a missing case a compile error | `[B]` (+ ADR-0033) | **`detected: bool` + loose siblings** — the tag-and-dispatch-without-a-tagged-union anti-pattern; `detected=False` with `markers=[...]` would slip through |
| Shared `markers.py` `Final` catalog read by every `ProjectDetector` | Registry / data-driven catalog (the `_MONOREPO_PRECEDENCE` idiom) | Marker knowledge is iterated data, not branched code; one addition-only source of truth kills the duplication ADR-0043 names | `[synth]` (best-practices' own flagged better option) | **Per-detector duplicated marker tuples** — the duplication-by-addition anti-pattern ADR-0043 singles out |
| `tests/conformance/` parameterized over the live registry + a collection-completeness guard | Parameterized test / open test set | A new pack auto-enrolls with zero test-file edits; the guard closes the auto-*disenrollment* hole | `[B]` shape + `[synth]` guard | **One hand-written test file per language** — an enumerated list that accretes exactly like the byte-edit allowlist ADR-0043 kills |
| `LanguagePack` contract pinned by a snapshot test, not a frozen file | Contract + snapshot test (the probe-ABC pattern) | ADR-0043 commitment 3 — the file stays editable; the *contract* is frozen; growing it is a loud, reviewable signal | `[B]` (+ ADR-0043) | **Per-phase byte-edit allowlist** — explicitly terminated by ADR-0043 commitment 2 |

### Patterns considered and deliberately rejected

- **A plugin / DI container for languages** — `register_language()` + explicit imports is the project's proven collection idiom; a container is machinery ahead of need (ADR-0043 defers it).
- **A capability registry / discovery mechanism** — the six capabilities are a closed, roadmap-named set; dynamic discovery solves a problem this phase does not have (ADR-0043 explicitly defers a capability registry).
- **A `LanguagePack` inheritance hierarchy** (`BaseLanguagePack → JvmLanguagePack`) — there is no shared *behavior* between languages, only a shared *shape*; a flat product type is correct, an inheritance tree is premature taxonomy.
- **A generic lockfile-reader abstraction** spanning pip/poetry/uv — three concrete strategies for three formats is honest; abstracting before a fourth Python package manager is a rule-of-three violation.
- **A codemod / migration harness** — ADR-0043 says build it when the first real migration appears; Phase 7.5 *defines* the migration concept (it lands ADR-0043) but does not need the tool.
- **A general semantic-diff "category fence"** — ADR-0043 rejects it as a research project; the buildable form is the per-contract snapshot test, which this design ships.

### Anti-patterns avoided

- **Pattern soup** — eight load-bearing pattern decisions, each tied to a real argument; performance's "Flyweight"/"Specification" and security's "Hexagonal"/"two-phase commit" pattern-name inflation are dropped (the critic flagged all four).
- **Premature pluggability** — no language DI container, no capability-discovery mechanism, no generic lockfile abstraction; `scip-python` deferred rather than built-then-jailed for a deferred component.
- **Inheritance for code reuse** — `LanguagePack` is a flat product type; detectors/adapters are Protocols.
- **Stringly-typed identifiers** — `language: Language` (the existing newtype, reused — no duplicate `LanguageId`); `grammars: tuple[SupportedLanguage, ...]` (closed Literal, not raw `str`).
- **Untyped `dict[str, Any]` interfaces** — `LanguagePack` is a typed Pydantic model; `DetectionResult` is a sum type.
- **Boolean flags on public methods** — `register_language(pack)` takes one typed argument; `probes_self_registered` is a *typed field on the pack value*, not a call-site flag.
- **Tag-and-dispatch without a tagged union** — `DetectionResult` is a sum type, not a `bool` + loose siblings.
- **Capability passed through ten frames** — the language axis flows through registries, not parameter threading.
- **Side effects in constructors / at import time** — `register_language` is an explicit named function called explicitly from a pack module (the identical lifecycle as `@register_probe`); `LanguagePack` construction is pure field assignment with no I/O (the grammar wheel is *not* imported at pack-definition time — it loads lazily on first `language_for`).

## Risks (top 3–5)

1. **`LanguagePack` is frozen on two near-isomorphic examples.** TypeScript and Python are both gradually-typed, lockfile-based, single-file-module ecosystems; passing on both proves the abstraction fits *similar* things. Phase 8's likely next language (Java/Maven — ADR-0032's running example) has a classpath, compiled artifacts, and POM inheritance the six fields cannot express. *Mitigation:* the freeze ADR ships **`Provisional Accepted` with `Review trigger: third language pack lands`** (ADR-0043 commitment 5); the contract-snapshot fence makes the inevitable growth *loud and expected* — ADR-0043 calls a breaking `LanguagePack` grow "exactly the desired behaviour." The risk is contained, not eliminated. Surfaced honestly per the roadmap-coherence check below.
2. **The TypeScript-retrofit asymmetry weakens the "Python validates the abstraction" proof.** TypeScript's probes self-register; Python's fan out through `register_language`. *Mitigation:* the asymmetry is *typed* (`probes_self_registered`), not papered over; the conformance suite consumes both packs *identically as inputs*, so the *contract* both validate is symmetric even though registration history differs. A unit test asserts the probe registry's set equals the union of all packs' `layer_a_probes` — drift becomes a red test.
3. **The `register_language` partial-fan-out residual.** A mid-fan-out crash on a *new* pack leaves the probe registry partly written — no rollback (the substrate has no `unregister`). *Mitigation:* it happens at import, before any gather, and fails the process loudly; a unit test asserts the partial state is detectable. The honest containment is import-time fail-fast; a true rollback would require an ADR-0043-forbidden silent edit to the shipped registries.
4. **Conformance "semantically broken" detection is only as good as the fixture.** A thin golden fixture lets a degenerate adapter pass `test_search_adapter_is_not_a_stub`. *Mitigation:* a documented golden-fixture spec (≥1 cross-file reference, ≥1 dependency edge) + a fixture-shape meta-test.
5. **`requirements.txt` is a moving target.** pip's directive syntax accrues (`--hash`, env markers, `--config-settings`, constraints files). *Mitigation:* the directive classifier default-denies on unknown directives (`unresolved` + warning) — an unrecognized directive fails *closed*, never silently honored or silently dropped.

## Synthesis ledger

### Vertex count
- Performance: 24 decision vertices extracted.
- Security: 27 decision vertices extracted.
- Best-practices: 26 decision vertices extracted.
- Total: 77.

### Edges
- AGREE: 19 (e.g. frozen `LanguagePack`, plain `LanguageRegistry` mirroring `codegenie.depgraph`, lazy grammar load, the conformance tier exists, no LLM, the Phase 1–7 regression gate, explicit-import pack collection, no `importlib.metadata` scan).
- CONFLICT: 9 (scored below).
- COMPLEMENT: 14 (e.g. performance's lazy-grammar discipline + security's parse-only discipline + best-practices' inventory all combine on the Python probes; security's adversarial fixtures + best-practices' parameterized conformance + performance's session-fixture caching combine on the conformance tier).
- SUBSUME: 6 (e.g. security's TB-1..TB-4 trust-boundary diagram subsumes performance's silent treatment of the gather closure; best-practices' "one new package" goal subsumes the others' looser scoping).

### Conflict-resolution table

Scores 0–3 per criterion. Commitments-fit 0 = veto. Sum of five.

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Pattern-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| CR-1 `LanguagePack` type | Pydantic-or-dataclass (punt) | dataclass-or-Pydantic | frozen Pydantic, `extra="forbid"` | **[B] frozen Pydantic** | 3 | 3 | 3 | 2 | 3 | 14 |
| CR-2 `register_language` failure semantics | straight-line, no rollback | two-phase commit + rollback | flat fan-out, no rollback (crashes on TS pack) | **[synth] validate-all-then-commit + build-then-publish + `probes_self_registered`** | 3 | 3 | 3 | 3 | 3 | 15 |
| CR-3 marker duplication | not addressed | per-detector duplication | per-detector duplication (admits catalog is better) | **[synth] shared `markers.py` catalog** | 2 | 3 | 3 | 3 | 3 | 14 |
| CR-4 Python probe hardening + parity goal | omits `setup.py`; 1.15× guessed gate | parse-only / byte-capped / no-exec | concrete inventory, happy-path | **[S] hardening + [B] inventory; drop [P]'s 1.15× gate** | 3 | 2 | 3 | 3 | 2 | 13 |
| CR-5 detection pre-pass vs existing prelude | new `LanguageDetectionPrepass` (temporal bug) | eager monotone detector | `ProjectDetector` returns `Detected`/`NotDetected` | **[synth] reuse the EXISTING `tier="base"` prelude + `language_filter`; `PythonProjectProbe` is a base probe** | 3 | 3 | 3 | 3 | 3 | 15 |
| CR-6 `scip-python` in Phase 7.5 | in, as precision rung | recommends deferring (yet jails it) | dev-tier, `run_external_cli` | **[S] recommendation — defer; tree-sitter-first; drop the jail machinery** | 3 | 2 | 3 | 3 | 3 | 14 |
| CR-7 grammar field on `LanguagePack` | not modeled | not modeled | `grammar_name: str` (raw str) | **[synth] `grammars: tuple[SupportedLanguage, ...]`** | 2 | 3 | 3 | 3 | 3 | 14 |
| CR-8 conformance auto-enrollment hole | session fixtures (no guard) | adversarial fixtures (no guard) | registry-parameterized (no guard) | **[B] registry-parameterized + [synth] collection-completeness guard + [S] adversarial fixtures + [P] session caching (no xdist)** | 3 | 3 | 2 | 3 | 3 | 14 |
| CR-9 the "category-based fence" | assumes it exists | "rejects a planted edit" | downgrades to `LanguagePack` snapshot | **[B] contract+snapshot test — IS the roadmap's category fence per ADR-0043 cmt 3 + roadmap table 7.5(c)** | 3 | 3 | 3 | 2 | 3 | 14 |

### Shared blind spots considered

The critic flagged three things all three designs quietly agreed on:

1. **"TypeScript/JavaScript is one language."** *Departed.* `LanguagePack.grammars: tuple[SupportedLanguage, ...]` models the one-to-many relation. The TypeScript pack carries `grammars=("typescript", "tsx", "javascript")`. The no-shadow check operates per grammar key. (Resolves critic finding (a) on the grammar side.)
2. **"The decomposed registries compose cleanly under a `register_language()` facade with no edits."** *Departed.* The synthesis explicitly establishes the registries are append-only with no `unregister` (so no rollback), that `@register_probe` already fires at probe-module import (so TypeScript is retrofitted by *reference*, `probes_self_registered=True`), and that `_DISPATCH` is a `Final` dict edited *textually* as a loud source edit — `register_language` never writes it. (Resolves critic findings (c) and (d).)
3. **"Two similar packs validate the abstraction; freeze the contract now."** *Carried forward with the freeze made provisional.* Two instances is the roadmap-mandated minimum and the phase cannot ship a third speculative pack. The freeze ships `Provisional Accepted` with `Review trigger: third language pack` — ADR-0043 commitment 5's exact mechanism for "freeze on thin evidence, honestly." Risk #1 surfaces it. (Resolves critic finding (e).)

### Pattern reconciliation

| Pattern | Where it appeared | Synthesis disposition | Rationale |
|---|---|---|---|
| Make illegal states unrepresentable | all three (`LanguagePack`) | Kept | A partial language is a real bug `mypy` forbids for free |
| Two-phase commit | `[S]` `register_language` | **Rejected** — replaced by build-then-publish | The append-only registries have no abort protocol; the pattern was decoration (critic confirmed) |
| Build-then-publish (staging-then-swap) | none — critic's named missed pattern | **Added** | The only buildable atomicity over append-only registries |
| Facade | `[B]` `register_language` | Reframed as Registry + Open/Closed | A "facade" that double-registers on its own first input is a leaky re-registrar (critic confirmed); the honest framing is a registry fan-out with a typed retrofit discriminator |
| Specification | `[P]` `LanguageDetectionPrepass` | **Rejected with the component** | The pre-pass had a temporal-ordering bug; the existing prelude + `language_filter` replaces it |
| Flyweight | `[P]` memoized `Language` | **Dropped** — it is plain `lru_cache` memoization the kernel already does |
| Hexagonal ports & adapters | `[S]` `scip-python` isolation | **Dropped** — restates an existing `import-linter`-enforced invariant; `scip-python` deferred anyway |
| Strategy + Chain of responsibility | `[P]` SCIP/tree-sitter ladder | **Deferred with `scip-python`** — Phase 7.5 ships tree-sitter-only |
| Tagged union / sum type | `[B]/[S]` (`DetectionResult`) | Kept | Real state with per-variant fields |
| Structural typing (Protocol) | `[B]` (detector, adapters) | Kept | ADR-0032's settled idiom |
| Registry / data-driven catalog | `[B]` (`_MONOREPO_PRECEDENCE` idiom) | **Promoted** to the `markers.py` shared catalog | Kills the marker duplication ADR-0043 names |
| Contract + snapshot test | `[B]` (`LanguagePack` fence) | Kept — and named as the roadmap's "category fence" | ADR-0043 commitment 3; roadmap table 7.5(c) verbatim |
| Newtype | `[B]` (`Language` reuse) | Kept — reuse `Language`, no duplicate `LanguageId` | ADR-0043 flags duplicate-by-addition newtypes |

### Departures from all three inputs

1. **`LanguagePack.grammars: tuple[SupportedLanguage, ...]`** — none of the three modeled the one-language-to-many-grammars relation; performance/security ignored it, best-practices used a raw `grammar_name: str`. The synthesis models it as a tuple of the closed `SupportedLanguage` Literal. (Critic's named missed structural pattern; resolves finding (a).)
2. **No new detection pre-pass — reuse the EXISTING coordinator prelude.** Performance invented `LanguageDetectionPrepass`; the critic showed it reads `RepoSnapshot.detected_languages` *before any probe runs*, a temporal-ordering bug. The synthesis uses what is *already shipped*: the coordinator's `tier="base"` prelude wave runs `LanguageDetectionProbe` (and now `PythonProjectProbe`) first, enriching `detected_languages`; the `tier="task_specific"` rest wave is filtered by the *existing* `language_filter._admits_languages` predicate. Zero new dispatch code; the temporal bug cannot occur. (Resolves finding (b).)
3. **`register_language` validate-all-then-commit + build-then-publish + `probes_self_registered`** — security wanted two-phase-commit-with-rollback (impossible over the substrate); performance and best-practices shipped straight-line fan-outs (best-practices' crashes on its own first input). The synthesis is none of the three: validate-everything-before-any-write, build-then-publish for the language registry, an explicit typed `probes_self_registered` discriminator so the TypeScript retrofit is *by reference* and never double-registers. (Resolves findings (c) and (d).)
4. **`scip-python` deferred; tree-sitter-first.** Security *recommended* this in its Open-Q3 but then built a full jail; performance wanted SCIP in as the precision rung. The synthesis takes the recommendation and drops the contradicting machinery — `ALLOWED_BINARIES` is untouched this phase.
5. **`package_managers` is derived, not a field.** All three listed `package_managers` as a separate `LanguagePack` capability field. It is redundant — `dep_graph_strategies.keys()` *is* the set of package managers. The synthesis drops it; the pack has six fields, not seven, and the redundancy (a second source of truth that could drift) is eliminated.
6. **The performance `±3%` cold-gather canary is dropped.** No committed Phase-7 baseline exists; CI runner variance exceeds ±3%; the critic showed a hard gate would be chronically flaky and a warn-only gate enforces nothing. Replaced with the checkable claim "Node gather never imports `tree_sitter_python`" (a `sys.modules` fence) and "Python fixture gather completes within `make check`."

## Exit-criteria checklist

Phase 7.5 exit criteria from `roadmap.md`:

- [ ] **Python and TypeScript both run from the same gather + plugin orchestration** → the coordinator (unchanged) iterates the probe registry now carrying both languages' probes; `vulnerability-remediation--python--pip` resolves from the `(vuln, python, pip)` tuple via the existing plugin-resolution layer.
- [ ] **The Node/TypeScript regression suite is unchanged and green** → the full Phase 1–7 suite runs as a hard CI gate; zero silent edits to shipped probe/plugin code (only loud `Literal`/`_DISPATCH`/`$ref`/import-line edits).
- [ ] **Every registered language passes `tests/conformance/`** → `test_language_conformance.py` parameterized over `default_language_registry.all()`, with the collection-completeness guard ensuring no language is silently un-enrolled.
- [ ] **An incomplete `LanguagePack` fails `mypy --strict`** → every `LanguagePack` capability is a required field; a missing field is a construction-site type error.
- [ ] **The category-based fence rejects a planted silent edit** → `tests/fence/test_language_pack_contract.py` (the contract+snapshot test ADR-0043 cmt 3 and roadmap table 7.5(c) name as *the* form of the category fence) goes red on a planted `LanguagePack` field-add; a planted Node-probe-body edit goes red against the Phase 1–7 regression gate. Both planted-edit levels are in the test plan.
- [ ] **`vulnerability-remediation--python--pip` produces a real diff on a vulnerable Python fixture repo** → the new plugin lives at `plugins/vulnerability-remediation--python--pip/`, `extends` the universal base, wires the tree-sitter Python adapters, and is exercised against a vulnerable fixture under `tests/golden/languages/python/`.
- [ ] **`tests/conformance/` tier + mandatory per-language goldens land** (test-architecture table 7.5 a/b) → one parameterized module + `tests/golden/languages/{typescript,python}/` fixture repos + goldens.
- [ ] **ADR-0043 discipline reframe** (test-architecture table 7.5 c) → ADR-0043 is already `Accepted` (committed `b4ab0ee`); Phase 7.5 ships the model case (`LanguagePack` contract + snapshot test, no allowlist rows).

## Load-bearing commitments check

Commitments from `production/design.md` §2:

- **1. No LLM in the gather pipeline** → `LanguagePack`, `register_language`, the Python probes, and the dep-graph strategies are all deterministic Python; `scip-python` is deferred so no binary even enters; the `fence` job + `import-linter` stay green; `tree-sitter-python` is a grammar wheel, not an LLM SDK.
- **2. Facts, not judgments** → Python probes report evidence (`detected python files: N`, `lockfile: poetry.lock present`, `index_override_present`, `unresolved: vcs source`) with `confidence`; no probe concludes "safe to remediate."
- **3. Honest confidence** → every Python probe reports `Literal["high","medium","low"]`; a probe at a byte/depth cap returns a *partial* fact with `confidence="low"` and a `_WARNING_IDS` entry; the directive classifier default-denies on unknown directives (no silent drop) — directly serving "silent staleness is the worst failure mode." The conformance collection-completeness guard closes the one silent-under-enrollment hole the critic found.
- **4. Determinism over probabilism** → dep-graph strategies parse already-resolved lockfiles deterministically; no resolver subprocess, no network; same inputs → same `RepoContext`.
- **5. Extension by addition — no silent edits** → adding Python is new files plus *compiler/snapshot-policed loud edits only* (`SupportedLanguage` `+1`, `_DISPATCH` `+1`, `PackageManager` `+3`, additive `$ref`s, one import line). `register_language` is a *pure addition* — TypeScript is retrofitted by reference, no shipped registry is edited. The `LanguagePack` contract is the model case: a contract + snapshot test, frozen *provisionally* and *narrowly*. **Tension surfaced:** ADR-0043 commitment 5 says "freeze only earned contracts (survived ~3 phases)"; `LanguagePack` is frozen at phase 0 of its life — the design honors the *letter* of commitment 5 by shipping `Provisional Accepted` + `Review trigger`, which 5 explicitly permits ("or state plainly why an early freeze is necessary" — here: the roadmap *mandates* the contract land this phase). Risk #1 documents it.
- **6. Organizational uniqueness as data** → the `markers.py` catalog is data (a `Final` mapping), not branching code — the project's settled "iterated, never branched" idiom.
- **7. Progressive disclosure** → unchanged; `LanguagePack` carries *references* (import paths, classes), not inlined content.
- **8. Humans always merge** → unchanged; Phase 7.5 ships no autonomy past PR creation.
- **9. Cost observable and bounded** → no LLM call, no workflow change; `$/PR` untouched.

## Roadmap coherence check

- **What prior phases established that this design depends on:** the frozen `Probe` ABC and `@register_probe` registry (Phase 0, ADR-0007); the `tier="base"` prelude wave + `RepoSnapshot.detected_languages` enrichment + `language_filter._admits_languages` predicate (Phases 0–1); the grammar kernel `language_for` / `_DISPATCH` / `SupportedLanguage` (02-ADR-0011); `@register_dep_graph_strategy` + `DepGraphRegistry` keyed by `PackageManager` (Phase 2, ADR-0006); the `Language` newtype + `PackageManager` Literal at `codegenie.types.identifiers` (Phase 3); ADR-0032 search-adapter Protocols; ADR-0031 plugin architecture; the two-pass sanitizer + writer; ADR-0043 (committed `b4ab0ee`). The Phase 1 `SizeCapExceeded`/`DepthCapExceeded`/`SymlinkRefusedError` cap machinery is reused by the Python probes.
- **What this design establishes that later phases will need:** the `LanguagePack` contract + `register_language` + `codegenie.languages` package — the seam every Phase 8+ target language registers through; `tests/conformance/` — the tier every future language auto-enrolls in; the `tests/golden/languages/{language}/` golden discipline; the `markers.py` catalog as the addition-only home for new languages' detection markers; the contract+snapshot fence as the model for every future frozen surface (ADR-0043 cmt 3).
- **New ADRs implied by this design that should be drafted (in `docs/phases/07.5-multi-language-foundations-python/ADRs/`):**
  1. **`LanguagePack` contract + freeze** — `Provisional Accepted`, `Review trigger: third language pack lands`. Justifies the six-field set, the `grammars: tuple[SupportedLanguage, ...]` relation, the drop of `package_managers` as a redundant field, and the early-freeze necessity (roadmap mandates it this phase).
  2. **`register_language` registration semantics** — documents validate-all-then-commit, build-then-publish for the language registry, the `probes_self_registered` retrofit discriminator, and the *explicit decision not to add `unregister`* to the shipped append-only registries (so the partial-fan-out residual is an accepted, contained risk, not an oversight).
  3. **Python search adapter: tree-sitter-first, `scip-python` deferred** — records that `ALLOWED_BINARIES` is untouched this phase and the `ScipAdapter` fast-follow will need its own `ALLOWED_BINARIES` amendment under the Phase 2 omnibus when it lands.
  4. **`requirements.txt` directive-language parsing contract** — pins the directive taxonomy (`unresolved` reasons, `index_override_present`, `-r` path-escape, unknown-directive default-deny) so a later directive addition is a reviewed change to a named contract.

## Open questions deferred to implementation

1. **Fixture sizing.** The conformance/golden Python fixture must be rich enough to defeat a stub adapter (≥1 cross-file ref, ≥1 dep edge) yet small enough to keep the session gather inside `make check`. The exact fixture is an implementation-time choice constrained by the documented golden-fixture spec.
2. **`tsx`/`javascript` conformance coverage.** The TypeScript pack carries three grammar keys; whether the conformance fixture exercises all three or just `typescript` is an implementation detail — the contract permits all three; the fixture-shape spec should state the minimum.
3. **`PythonImportGraphProbe` Layer-B depth.** Phase 7.5 ships one import-graph probe; whether it also covers `sys.path`/namespace-package resolution to Node's Layer-B depth, or stays minimal, is an implementation-time scoping call — the phase proves the *axis*, not Python feature-parity.
4. **`scip-python` fast-follow timing.** Deferred to a fast-follow; whether that is a Phase 7.5 closeout story or a Phase 8 preamble is a sequencing decision for the story-writer.
5. **Polyglot-repo adapter dispatch.** A repo detected as *both* Node and Python registers both packs' probes; the multi-language *workflow* coordination story (which adapter answers which query) is ADR-0032 / Phase-8-Planner territory — Phase 7.5 ensures the schema's per-probe sub-schema isolation prevents key collisions and ships a polyglot-isolation conformance assertion, but does not own the workflow story.
