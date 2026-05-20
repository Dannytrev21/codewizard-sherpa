# Phase 7.5 — Multi-language foundations + Python: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-20

## Lens summary

Phase 7.5 adds a *second axis* to the system — the language axis — and the only performance question that matters is whether the second language is **free at the margin**: gather of a Node repo must take the same wall-clock after Python ships as before, registry dispatch must stay O(probes-that-apply) not O(all-probes-across-all-languages), grammar wheels must load lazily and exactly once per process, and the new `tests/conformance/` tier must not become a CI tentpole. The performance bet here is that `LanguagePack` is a *pure value, resolved once, then never touched on the hot path* — it shapes registration at import time and detection at gather-start, and after that the existing decomposed registries (`@register_probe`, `@register_dep_graph_strategy`, the grammar `_DISPATCH`) carry every dispatch with their existing, already-tuned cost. We pay extra design complexity (a language-scoped detection pre-pass, a per-language probe-set memo, lazy grammar handles) to buy the invariant that adding language #2 — and #3, #4 — costs zero added latency on any repo that does not use that language. Tail latency and token economy are inherited unchanged: Phase 7.5 introduces no LLM call and no new runtime service (ADR-0005 holds), so $/PR is untouched and the only cost surface is CPU/wall-clock in the deterministic gather and CI minutes in conformance.

## Goals (concrete, measurable)

These are *delta* goals — Phase 7.5 changes nothing about workflow throughput; it must *preserve* it while adding a language.

- **Zero-regression gather:** Node/TypeScript cold gather p50/p95 unchanged within ±3% measured against the Phase 7 baseline (`tests/golden` fixture set, same hardware). This is the headline goal — language #2 is free on language-#1 repos.
- **Python gather parity:** a Python fixture repo of comparable size to the Node golden gathers cold in ≤ Node-cold-p95 × 1.15 (Python Layer A/B is a smaller probe set than Node's full A–G, so this is a generous ceiling; the grammar-load amortization is the only new cost).
- **Registry dispatch:** `Registry.for_task` / `sorted_for_dispatch` p99 stays < 1 ms per gather regardless of registered-language count — dispatch cost is a function of *applicable* probes, not *total* probes. No double-counting when two `LanguagePack`s are registered.
- **Grammar cold-load:** first `language_for("python")` call ≤ 80 ms (one wheel import + one `Language` construction); every subsequent call ≤ 5 µs (memoized). A Node-only repo never imports `tree_sitter_python` — verified by a fence.
- **Conformance CI budget:** `tests/conformance/` whole-tier wall-clock ≤ 90 s on the CI runner with 2 languages registered, and grows **sub-linearly** per added language (shared fixtures, parallel parametrization, cached gather artifacts). It must not push `make check` past its current envelope.
- **Per-worker memory ceiling:** a gather worker with both languages registered stays ≤ 350 MB RSS (the dominant cost is tree-sitter C extensions; two grammars loaded is ~+15 MB over one — acceptable, and only paid by polyglot repos).
- **Token economy:** unchanged — $/PR, cache-hit rate, LLM-call count are all out of scope for a deterministic gather phase. The performance win is *not burning* tokens: the conformance suite catches a semantically-broken adapter deterministically so no LLM debugging round-trip is ever spent on it.

## Architecture

The design has one load-bearing idea: **`LanguagePack` is a build-time value, not a runtime dispatcher.** It is consumed exactly twice — once at *import time* (`register_language` fans it into the existing registries) and once at *gather-start* (the project-detector pre-pass picks which packs' probes are even eligible). After that, the hot path is the *existing* registry machinery, untouched.

```
                         ┌─────────────────────────────────────────────────────┐
  IMPORT TIME (once       │  codegenie.languages  — collection point             │
  per process, cold)      │  ┌──────────────┐   ┌──────────────┐                 │
                          │  │ TS_PACK      │   │ PYTHON_PACK  │   (frozen vals) │
                          │  │ LanguagePack │   │ LanguagePack │                 │
                          │  └──────┬───────┘   └──────┬───────┘                 │
                          │         │ register_language(pack)  (fan-out)         │
                          └─────────┼──────────────────┼──────────────────────────┘
                                    │                  │
              ┌─────────────────────┴───┐   ┌──────────┴───────────┐   ┌──────────────┐
              ▼                         ▼   ▼                      ▼   ▼              ▼
       @register_probe         @register_dep_graph      grammar _DISPATCH      search-adapter
       (probe registry)        _strategy (depgraph reg) (lazy wheel handles)   registry (ADR-0032)
              │                         │                      │                    │
              └────────── existing decomposed registries — unchanged hot path ───────┘

  GATHER-START (per run)        ┌────────────────────────────────────────────┐
                                │ LanguageDetectionPrepass                   │
   repo snapshot ──────────────▶│  cheap marker scan → {detected_languages}  │
                                │  → eligible_packs ⊆ registered_packs       │
                                └───────────────────┬────────────────────────┘
                                                    │ probe-set memo (content-keyed)
                                                    ▼
                                ┌────────────────────────────────────────────┐
   COORDINATOR (unchanged) ─────│ Registry.sorted_for_dispatch filtered to    │
                                │ probes whose language ∈ eligible_packs      │
                                │ → prelude / rest waves → bounded Semaphore  │
                                └───────────────────┬────────────────────────┘
                                                    ▼
                                          ProbeOutput → sanitizer → writer
```

Data flow, not boxes: a Node repo enters, the detection pre-pass scans for `package.json` / `tsconfig.json` / `*.py` / `pyproject.toml` markers in one `os.scandir` pass, finds only Node markers, and the coordinator dispatches **only Node probes** — Python probes are registered but filtered out before the wave is even built. `tree_sitter_python` is never imported. The Python pack costs that repo nothing.

## Components

### `LanguagePack` — frozen total-value language contract

- **Purpose:** A single immutable value carrying every capability a language must supply. Its existence is the *compile-time* proof that a language is completely registered — an incomplete `LanguagePack(...)` is a `mypy --strict` error, so a half-language can never reach the registries.
- **Interface:**
  - *Inputs (construction):* `name: SupportedLanguage`, `grammar: GrammarSpec` (module name + capsule-factory attr — the `_DISPATCH` row data), `project_detector: ProjectDetector` (a pure callable + its marker globs), `layer_a_probes: tuple[type[Probe], ...]`, `package_managers: tuple[PackageManager, ...]`, `dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]`, `search_adapter: SearchAdapterSpec` (ADR-0032 import path).
  - *Outputs:* the value itself; consumed by `register_language`.
  - *Errors:* none at runtime — incompleteness is a type error; structural breakage is a *conformance-suite* failure, not an exception.
- **Internal design:** A frozen Pydantic model (or frozen dataclass — see Open question 1). **It carries no behavior and no I/O.** The performance reasoning: a value with zero methods and zero lazy fields can be constructed at module import with no cost beyond field assignment, can be shared across threads/workers freely (frozen → no lock), and never needs re-resolution. Critically, the `grammar` field stores *the data needed to build a grammar handle* (module name, factory attr) — **not** a constructed `Language`. Constructing the `Language` at pack-definition time would import `tree_sitter_python` the instant the Python pack module is imported, defeating lazy loading. The pack stores the recipe; the grammar kernel's existing memo builds the handle on first actual use.
- **Tradeoffs accepted:** Growing `LanguagePack` with a genuinely new capability category breaks every existing pack until updated — this is *desired* (compiler-policed, ADR-0043), but it means the pack's field set is a real frozen contract and must be pinned by a snapshot test, adding one test surface. We accept that. We also accept that `LanguagePack` is a *broad* value (7 fields) where ADR-0043's freeze discipline prefers *narrow* contracts — justified in Open question 4.

### `register_language` — the fan-out function

- **Purpose:** Take one `LanguagePack` and push each capability into the *existing* decomposed registry it belongs to, so no Phase 1–7 registry code is edited.
- **Interface:** `register_language(pack: LanguagePack) -> None`. Idempotent within a process (re-registering the same pack name is a no-op, not a duplicate). Raises `LanguageRegistrationError` only on a genuine collision (two packs claiming the same `name`, or a probe name already registered by a different pack).
- **Internal design:** A straight-line sequence of calls — `_DISPATCH[pack.name] = pack.grammar.dispatch_row`; for each probe class, the *probe class is already decorated with `@register_probe`* at its own module import, so `register_language` does **not** re-register probes — it only records the `name → eligible probe set` mapping used by the detection pre-pass. For dep-graph strategies, each `(PackageManager, strategy)` pair is pushed through `register_dep_graph_strategy`. For the search adapter, the ADR-0032 import-path is recorded in the adapter registry indexed by language. Performance reasoning: **fan-out is O(capabilities-in-pack) and runs once at import.** It is not on any hot path. The function is deliberately dumb (registry pattern discipline: "keep it dumb; validate on use") — the *only* validation it does is collision detection, because a silent overwrite would be a correctness bug, not a perf one.
- **Tradeoffs accepted:** Probes still self-register via `@register_probe` at *their own* module import — so `register_language` and `@register_probe` are two registration paths that must agree. We accept this duplication-of-mechanism because making `register_language` the *sole* probe-registration path would require editing every existing probe module to drop its decorator — a silent edit to shipped code, exactly what ADR-0043 forbids. The pack's `layer_a_probes` tuple is therefore a *manifest* (used for the eligibility memo) not a *registrar*. A conformance test asserts the two agree.

### `LanguageDetectionPrepass` — gather-start eligibility filter

- **Purpose:** Decide, in one cheap filesystem pass, which languages a repo actually contains, so the coordinator dispatches only the relevant packs' probes. This is the component that makes "language #2 is free on language-#1 repos" true.
- **Interface:** *Input:* `RepoSnapshot` (the already-built file index). *Output:* `frozenset[SupportedLanguage]` of detected languages → resolves to `eligible_packs`. *Errors:* never fails — an empty result means "no known language", and the coordinator runs the universal/`["*"]` probes only.
- **Internal design:** It reuses the *existing* `language_detection` probe's marker logic — it does **not** add a second filesystem walk. The Phase 0/1 `LanguageDetection` probe already scans the tree; the pre-pass is a thin reading of `enriched_snapshot.detected_languages` (the field `cache/keys.py` and the coordinator already reference). Each `LanguagePack.project_detector` contributes its marker globs to a *single combined glob set* matched against the snapshot's already-materialized file list — no new I/O. Performance reasoning: the snapshot is built once; detection is a set-membership test over an in-memory list. Cost is O(files × markers) with markers being a handful of constants per language — sub-millisecond. The result is memoized on the snapshot's content key, so an incremental re-gather of an unchanged repo skips detection entirely.
- **Tradeoffs accepted:** A repo with a single stray `.py` file in a Node project will mark Python eligible and dispatch Python Layer A probes, which will then find no real Python project and return low-confidence/empty slices. That is a small wasted-work cost on misleading repos. We accept it rather than building a heavier "is this a *real* Python project" classifier into the pre-pass — the Python project-detector probe itself makes that call honestly, and the wasted probes are cheap (they short-circuit on no manifest). Tightening this is deferred (Open question 3).

### Grammar kernel extension — one `_DISPATCH` row, lazy by construction

- **Purpose:** Vend a `tree_sitter.Language` for Python without importing `tree_sitter_python` until a probe actually parses Python.
- **Interface:** Unchanged — `language_for("python") -> Language`, `GrammarLoadRefused` on failure. `SupportedLanguage` Literal gains `"python"`.
- **Internal design:** `register_language` writes the pack's grammar row into `_DISPATCH`. The kernel's existing `@functools.lru_cache`-memoized `_build_language` does the lazy `importlib.import_module("tree_sitter_python")` on first call only. **No code change to the kernel's hot path** — the kernel was *designed* (02-ADR-0011) for exactly this: "adding Phase 8's Python grammar is a single new dispatch row." Phase 7.5 keeps that promise; the only edits are the `Literal` member (compiler-policed, ADR-0043-sanctioned) and the `_DISPATCH` row insertion via `register_language`. Performance reasoning: the memo guarantees one wheel import + one `Language` construction per process per language; the `Language` value is shared across all parsers and all probes. Cold cost (~80 ms) is paid once and only by repos that contain Python; warm cost is a dict lookup.
- **Tradeoffs accepted:** Two grammar wheels in the runtime closure means ~+15 MB RSS for any worker that gathers a polyglot repo, and the `fence` job's `FORBIDDEN_LLM_SDKS` closure check now also implicitly vouches for one more wheel. Acceptable — tree-sitter C extensions are small and the memo bounds the cost.

### `tests/conformance/` tier — parameterized, fixture-shared, parallel

- **Purpose:** Catch the failure mode no other tier catches: a capability slot that is *filled and type-checks* but is *semantically broken* (a stub search adapter, a no-op project detector). Every registered `LanguagePack` is auto-enrolled.
- **Interface:** A pytest tier under `tests/conformance/`, parametrized over `registered_languages()`. Each language ships a mandatory fixture repo + golden under `tests/golden/languages/{language}/`.
- **Internal design (the performance-critical part):** The naive design re-runs a full cold gather per language per conformance assertion — that is the CI-bottleneck failure mode the lens explicitly warns against. Instead: **gather each language's fixture repo exactly once per session** (`@pytest.fixture(scope="session")`), cache the resulting `RepoContext` + raw probe outputs, and have every conformance *assertion* read that one cached artifact. The conformance checks themselves (does the search adapter return non-empty refs for a known symbol? does the project detector detect the fixture? does the dep-graph strategy resolve the lockfile?) are fast assertions over the pre-computed artifact. The tier is parametrized so adding language #3 adds *one fixture gather*, not a new test file. Run the per-language gathers in parallel via the session fixture warming concurrently (asyncio gather of the fixture builds). Performance reasoning: tier wall-clock = `max(per-language cold gather)` + `sum(fast assertions)`, not `sum(per-language gather × assertions)`. With 2 languages and shared session gathers this lands under the 90 s budget; it grows sub-linearly.
- **Tradeoffs accepted:** Session-scoped fixtures mean conformance tests share state — a test that mutated the cached `RepoContext` would poison siblings. We accept this and enforce read-only access via a frozen artifact (the `RepoContext` is already an immutable Pydantic value). Also: the conformance tier deliberately does *not* re-prove cache invariants or adversarial properties — those stay in their existing tiers; conformance is *only* the semantic-completeness check, kept narrow so it stays fast.

### Python Layer A/B probes + dep-graph strategies + search adapter

- **Purpose:** The actual Python capabilities — `PythonProjectDetection`, `PythonManifest` (reads `pyproject.toml` / `requirements.txt`), Python Layer B reflection/import-graph probes, pip/poetry/uv `DepGraphStrategy` implementations, and the `scip-python` search adapter (ADR-0032).
- **Interface:** Each probe implements the frozen `Probe` ABC (`localv2.md §4`) — two-arg `run(self, repo, ctx)`. Each dep-graph strategy is a `Callable[[ProbeContext, list[Mapping]], DiGraph]`. The search adapter implements the ADR-0032 `Protocol`s.
- **Internal design:** New files only — `probes/python/`, `depgraph` strategy modules, an `adapters/` module in the `vulnerability-remediation--python--pip` plugin. Performance choices: (1) the pip/poetry/uv strategies parse lockfiles, never invoke a resolver subprocess on the gather hot path — lockfile parsing is deterministic and ~100× cheaper than re-resolving; uv.lock and poetry.lock are already-resolved graphs, so `dep_graph.consumers` is a graph read, not a solve. (2) The Python probes declare tight `declared_inputs` globs (`pyproject.toml`, `*.lock`, `requirements*.txt`, `**/*.py`) so the content-addressed cache invalidates surgically — editing a Python file does not re-run Node probes and vice versa. (3) The `scip-python` adapter declares `scip-python` as an external tool and reports `confidence() == 0.0` when it is missing — degrading to the tree-sitter import-graph adapter per ADR-0032, never blocking the gather.
- **Tradeoffs accepted:** `scip-python` (pyright-based) is slow and can be stale; we deliberately make it the *fallback-capable* tier — the always-fresh tree-sitter import-graph is the default precision/cost rung and SCIP is consulted only when a query needs symbol precision. This trades some precision for predictable latency, consistent with ADR-0032's precision/cost ladder.

## Data flow

**Representative run: a cold gather on a polyglot repo (Node app with a Python tooling sidecar), both packs registered.**

1. **Import time (process start, once):** `codegenie.languages` is imported; `TS_PACK` and `PYTHON_PACK` modules load; each `LanguagePack` value is constructed (pure field assignment, no I/O — `tree_sitter_python` is *not* imported because the pack stores the grammar *recipe*, not a handle). `register_language` runs twice, fanning grammar rows into `_DISPATCH`, dep-graph strategies into the depgraph registry, and adapter import-paths into the adapter registry. Probes self-registered via `@register_probe` at their own module import. Total added cold-start cost vs. Node-only: a handful of dict insertions — sub-millisecond.

2. **Gather-start:** the coordinator builds the `RepoSnapshot` (one filesystem walk — *unchanged*, this cost exists already). The `LanguageDetectionPrepass` reads `enriched_snapshot.detected_languages`, matches each pack's marker globs against the in-memory file list, finds `{node, python}`. **Cache consulted here:** the detection result is keyed on the snapshot content hash; an incremental re-gather skips this.

3. **Wave construction:** `Registry.sorted_for_dispatch` is filtered to probes whose `applies_to_languages` intersects `{node, python}` ∪ `["*"]`. Node Layer A–G probes and Python Layer A/B probes are both in. **Parallelism extracted here:** the existing prelude/rest-wave partition runs all eligible probes under the *one* bounded `asyncio.Semaphore` — Python and Node probes share the same budget, no second pool, no nested parallelism (the coordinator's no-hidden-parallelism rule from 02-ADR-0003 holds across languages).

4. **Per-probe cache:** each probe's content-addressed cache key is checked. **Cache consulted here, per probe.** A warm Node probe whose `declared_inputs` are byte-identical is a cache hit and never runs. A Python probe touching a changed `pyproject.toml` is a miss and runs. Surgical, per-language invalidation — editing a Python file leaves every Node probe's cache valid.

5. **Grammar load:** the first Python probe that parses code calls `language_for("python")` → first call imports the `tree_sitter_python` wheel (~80 ms, once) and memoizes the `Language`. Every subsequent Python parse — across all probes, all files — is a dict lookup. The Node grammar was loaded the same way the first time a Node probe parsed. **A repo with no Python never reaches this step for Python.**

6. **Merge + sanitize + write:** probe outputs merge, flow through the sanitizer, and the writer emits `repo-context.yaml` + raw JSON. Unchanged.

**Where parallelism is extracted:** one place — the coordinator's existing bounded-semaphore wave dispatch, now spanning probes of both languages. We deliberately do *not* add a second axis of parallelism (e.g., per-language pools) — that would re-introduce the hidden-parallelism-lies-to-the-budget failure 02-ADR-0003 closed. **Where caches are consulted:** detection result (snapshot-keyed), per-probe content-addressed cache, grammar memo. Three caches, all pre-existing in shape; Phase 7.5 adds no new cache *mechanism*, only new *entries*.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Incomplete `LanguagePack(...)` — a capability field omitted | `mypy --strict` at build time | Build fails; cannot merge. No runtime path. |
| `LanguagePack` field set drifts (a new capability category added to one pack, not others) | `LanguagePack` snapshot test (the probe-ABC pattern, ADR-0043 commitment 3) + `mypy` on the other packs | Build fails loudly; the contract growth is a sanctioned compiler-policed edit that forces every pack to update. |
| Capability present but semantically broken (stub search adapter, no-op detector) | `tests/conformance/` tier | CI fails; the language is not considered registered-and-healthy. Caught deterministically — *zero LLM debugging spend*. |
| `tree_sitter_python` wheel missing from runtime closure | `language_for("python")` raises `GrammarLoadRefused`; `fence` job closure check | Gather of Python repos fails fast with a typed, language-named error; Node gather unaffected (lazy load — Node never imports the Python wheel). |
| `scip-python` external tool missing | `ScipAdapter.confidence() == 0.0` (ADR-0032) | Bundle Builder degrades to the tree-sitter import-graph adapter; logs the downgrade; gather continues. No hard failure. |
| Probe-name collision between two packs | `register_language` collision check at import | `LanguageRegistrationError` at startup — fail fast, before any gather. |
| Detection pre-pass false-positive (stray `.py` in a Node repo) | The Python project-detector probe finds no manifest | Python Layer A probes return empty/low-confidence slices; small wasted work, no incorrect output. |
| A Node probe edited as a side effect of adding Python ("silent edit") | The full Node/TS regression suite (hard gate) + the category-based extension-by-addition fence against a planted silent edit | CI fails; the regression suite is the safety net ADR-0043 relies on. |
| Conformance tier wall-clock regresses past budget | A performance-canary assertion on tier duration (see Test plan) | CI flags it; the regression is caught before it compounds across Phases 8–16. |

## Resource & cost profile

Order-of-magnitude, deterministic gather only (no LLM, no workflow — those are out of phase scope):

- **Tokens/run:** 0. Phase 7.5 introduces no LLM call. $/PR unchanged. This is the strongest performance property of the phase — the entire language axis is added on the deterministic side of ADR-0005.
- **Wall-clock — Node repo, cold:** unchanged within ±3% of Phase 7 baseline (p50 ~3–6 min for a large repo per design.md §3 Stage 2; the language axis adds only a sub-millisecond detection pre-pass and a few import-time dict writes).
- **Wall-clock — Node repo, warm:** seconds (cache hits), unchanged.
- **Wall-clock — Python fixture repo, cold:** ≤ Node-cold-p95 × 1.15. Python Layer A/B is a smaller probe set than Node A–G; the only genuinely new cost is the ~80 ms one-time `tree_sitter_python` import.
- **Grammar load:** cold ~80 ms/language/process; warm ~5 µs. Two grammars resident on a polyglot worker.
- **Memory/worker:** ≤ 350 MB RSS with both languages registered; the polyglot delta over single-language is ~+15 MB (the second tree-sitter C extension). A Node-only repo on a worker that *registered* Python but never *gathered* Python stays at single-grammar footprint — lazy load means registration is nearly free, only use costs memory.
- **Storage growth:** `tests/golden/languages/python/` fixture repo + golden (~tens of KB to low MB depending on fixture size) and the Python sub-schemas. No runtime storage change.
- **Hot vs cold ratio:** in steady-state continuous gather (design.md §3.2), the overwhelming majority of gathers are warm — incremental, cache-hit-dominated. The per-language surgical cache invalidation means a Python-file edit triggers a Python-only partial re-gather and vice versa; cross-language false invalidation is zero by construction (disjoint `declared_inputs`).
- **CI cost:** `tests/conformance/` ≤ 90 s for 2 languages, sub-linear growth. The full Node/TS regression suite runs unchanged as a hard gate — that is the largest CI cost and Phase 7.5 must not inflate it.

## Test plan

"Passes its tests" means:

- **Zero-regression proof:** the full Phase 1–7 Node/TypeScript regression suite runs green, unchanged — the hard gate proving Python did not edit Node. A *performance* assertion accompanies it: Node golden-fixture cold-gather wall-clock is within ±3% of the recorded Phase 7 baseline (the baseline is a committed number; the test reads it).
- **`mypy --strict` proof:** a deliberately incomplete `LanguagePack(...)` test fixture fails type-checking — verified by a `mypy`-as-test assertion (the build *should* reject it).
- **Conformance proof:** every registered `LanguagePack` passes `tests/conformance/` — including a deliberately planted semantically-broken capability (a stub search adapter that type-checks but returns `[]`) that the tier *must* fail on. This is the test that the tier earns its existence.
- **Grammar laziness proof:** a fence test asserts that importing `codegenie` and gathering a Node-only fixture never imports `tree_sitter_python` (assert the module is absent from `sys.modules`). This is the test that "language #2 is free" is true and not aspirational.
- **Registry-cost proof:** a test registers N synthetic `LanguagePack`s and asserts `Registry.for_task` / `sorted_for_dispatch` p99 stays flat — dispatch cost is a function of *applicable* probes, not *registered* languages.
- **Surgical-invalidation proof:** extend the Phase 3 cache-invariant Hypothesis property to a polyglot fixture — for a `(gather, edit-python-file, gather, edit-node-file, gather)` sequence, Python probe outputs change iff Python `declared_inputs` changed and Node probe outputs change iff Node `declared_inputs` changed; no cross-language false invalidation.
- **Silent-edit fence:** the category-based extension-by-addition fence (ADR-0043) is exercised against a planted silent edit to a Node probe body and must reject it.

**Performance regression canary:** a CI assertion — recorded in `tests/conformance/` or a sibling `tests/perf/` canary — pinning two numbers: (1) Node golden cold-gather wall-clock vs. baseline (±3%), and (2) `tests/conformance/` whole-tier wall-clock vs. its budget (≤ 90 s, 2 languages). Both are committed baselines, ratcheted deliberately. If either drifts, CI flags it — so the "language #2 is free" and "conformance is not a tentpole" invariants are *enforced*, not hoped for. The canary is the single most important test in this design from the performance lens: every other test proves correctness; this one proves the lens's whole thesis.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `LanguagePack` as a frozen total value with one field per capability | Make illegal states unrepresentable + Smart constructor | An incomplete language must be *impossible to construct*, not "validated later" — `mypy --strict` rejecting `LanguagePack(...)` with a missing field is the cheapest possible enforcement and runs at build time, off every hot path. Frozen → shareable across workers with no lock. | *Not* a Builder — a Builder permits a partially-built pack to exist, exactly the illegal state we are eliminating. A Builder would also add allocation cost; the total value is a single construction. |
| `register_language` fans a pack into the existing decomposed registries; the kernel never imports a pack | Plugin architecture / Registry pattern + Open/Closed | This is the load-bearing "extension by addition" decision — a new language is new files plus one collection-point line; no Phase 1–7 registry code is edited. Performance: registration is O(capabilities), runs once at import, never on the gather hot path. | *Not* a central `dispatch_language(name)` `match` block — that is modification-not-extension and would grow every language, and would centralize a cost that the decomposed registries already pay efficiently per-probe. |
| Grammar handles built lazily on first `language_for(name)` use, memoized; pack stores the *recipe* not the handle | Lazy loading + Flyweight (the memoized shared `Language`) | The performance thesis of the phase: a Node-only repo must never pay the Python wheel import. Storing a recipe (module name + factory attr) in the pack and deferring construction to the kernel's existing `lru_cache` memo guarantees one import per process *and only if used*. The `Language` value is a shared flyweight across every parser. | *Not* eager grammar construction at pack-definition time — that would import `tree_sitter_python` the instant the Python pack module loads, making registration cost memory and import time even for repos that never touch Python. |
| `LanguageDetectionPrepass` filters the probe set to detected languages before wave construction | Functional core / Specification pattern | Detection is a pure function `RepoSnapshot -> frozenset[language]` — testable, cacheable, no I/O of its own (it reuses the existing snapshot + the `LanguageDetection` probe's marker logic). It is the component that makes "language #2 is free on language-#1 repos" a structural guarantee rather than a hope. | *Not* a heavy classifier — a richer "is this a *real* project" check belongs in the per-language project-detector probe, which already makes that call honestly. Keeping the pre-pass a cheap filter avoids adding latency to every gather. |
| `tests/conformance/` uses session-scoped, parallel-warmed fixture gathers; assertions read pre-computed artifacts | Functional core + pre-rendered/cached hot view | The lens's explicit concern: the conformance suite must not become a CI tentpole. Gathering each fixture once per session and asserting over the cached `RepoContext` makes tier wall-clock `max(gather) + sum(fast assertions)` instead of `sum(gather × assertions)`, so it grows sub-linearly per language. | *Not* per-test cold gathers — the naive parametrization that re-gathers per assertion; that is precisely the bottleneck the lens names. |
| `scip-python` adapter is the fallback-capable rung; tree-sitter import-graph is the default precision/cost rung | Strategy pattern + Chain of responsibility (the ADR-0032 precision/cost ladder) | SCIP is precise but slow and can be stale; tree-sitter is always-fresh and fast. Making the cheap-and-fresh adapter the default and SCIP the consulted-on-demand fallback gives predictable tail latency — the gather never blocks on a slow indexer it did not need. | *Not* SCIP-always — that would put a slow, staleness-prone tool on the default path, inflating p95 for queries that a tree-sitter answer would have satisfied. |

## Risks (top 3–5)

1. **`LanguagePack` is a broad frozen contract where ADR-0043 prefers narrow ones.** Seven fields, frozen, breaking every pack on growth. The performance argument *for* breadth is that one resolved value off the hot path beats seven separately-registered, separately-resolved capabilities. The risk is that "genuinely new capability category" judgement calls accrete fields onto the pack faster than expected, and a broad frozen contract is brittle. *Mitigation:* the pack is frozen *provisionally* (ADR-0043 commitment 5) with a review trigger; the snapshot test makes every growth loud; and the breadth is justified because the alternative (un-grouped capabilities) loses the "resolved once" property.
2. **Detection pre-pass false-positives waste probe dispatches on misleading repos.** A stray `.py` makes Python eligible. The cost is bounded (Python probes short-circuit on no manifest) but on a large portfolio the aggregate wasted work is non-zero. *Mitigation:* deferred tightening (Open question 3); the per-probe cache means the wasted work is paid once then cached as empty.
3. **The conformance tier's session-scoped fixtures couple tests through shared state.** A test that mutates the cached artifact poisons siblings; the speed win depends on this discipline holding. *Mitigation:* the cached `RepoContext` is an immutable Pydantic value — mutation is structurally prevented — and a lint/review rule forbids non-read access.
4. **`register_language` and `@register_probe` are two registration paths that must agree.** The pack's `layer_a_probes` tuple is a manifest; the probes self-register via decorator. Drift between the two (a probe in the pack manifest but not decorated, or vice versa) would silently mis-filter the wave. *Mitigation:* a conformance assertion that every probe in a pack's manifest is in `default_registry` and carries the pack's language tag.
5. **Two grammar wheels widen the runtime closure the `fence` job vouches for.** Each added language adds a wheel; the closure-purity check (`FORBIDDEN_LLM_SDKS`) must keep pace, and ABI drift between `tree-sitter` major versions and a grammar wheel surfaces only at `language_for` call time. *Mitigation:* the grammar kernel already raises a typed `GrammarLoadRefused` naming the language on ABI mismatch; the contract test tier should add a `tree-sitter-python` real-binary contract test, version-pinned and ratcheted, run nightly.

## Acknowledged blind spots

- **I optimized for the *gather* hot path and treated the `vulnerability-remediation--python--pip` plugin's *workflow* performance as out of scope.** Token economy, $/PR, and recipe-vs-RAG-vs-LLM routing for Python vulns are real performance surfaces, but they belong to Phases 8+ (Planner) and the plugin's own design; Phase 7.5 only proves the plugin produces a real diff. A security- or best-practices-lens design may weight the plugin's correctness more heavily than I did.
- **I assumed the existing coordinator's single-semaphore wave model scales cleanly to two languages' worth of probes.** It should — the probe count roughly doubles for polyglot repos but the bound is a tuning constant — but I did not model whether the bound itself needs a per-gather adjustment when many languages are registered. If a future repo triggers 5 languages' probe sets, the semaphore bound may need to be a function of eligible-probe-count, not a constant.
- **I treated `mypy --strict` rejecting an incomplete `LanguagePack` as a *performance* win (build-time, off-hot-path enforcement).** It is, but I have not deeply considered the *developer-experience* cost of a broad frozen contract whose growth breaks every pack — a best-practices lens will weigh that more.
- **Conformance fixture sizing.** I asserted the tier stays under 90 s but the actual number depends on how large the mandatory per-language fixture repos are. If a realistic Python fixture must be large to be representative, the session-gather cost rises. I have not pinned fixture size.
- **I did not address polyglot *workflow* coordination** (a repo where a CVE touches both a Node and a Python dependency) — that is ADR-0042 multi-plugin coordination territory and a Phase 8+ concern.

## Open questions for the synthesizer

1. **`LanguagePack`: frozen Pydantic model or frozen dataclass?** Pydantic gives a smart-constructor with validation and a natural snapshot-test target but adds construction cost (paid once at import — negligible). A frozen dataclass is leaner. The performance delta is immaterial; the choice should be made on the consistency lens's preference (the codebase uses Pydantic for wire types, dataclasses for registry entries). I lean Pydantic for the snapshot-test ergonomics.
2. **Should `register_language` become the *sole* probe-registration path eventually?** Today probes self-register via `@register_probe` *and* are listed in the pack manifest — two paths. Unifying them would require editing every existing probe module (an ADR-0043-forbidden silent edit *now*) but could be a sanctioned *migration* later. Is that migration worth scheduling, or is the two-path-plus-conformance-check acceptable indefinitely?
3. **How tight should the detection pre-pass be?** A cheap marker scan over-includes (stray `.py` → Python eligible). Tightening it (require a `pyproject.toml`/`requirements.txt`, not just `*.py`) reduces wasted probe dispatch but risks under-detecting a real but unconventional Python project. The security lens may want over-inclusion; the performance lens wants tightness. Where is the line?
4. **Is freezing a 7-field `LanguagePack` defensible under ADR-0043's "freeze only narrow contracts" discipline?** My performance argument says yes — grouping the capabilities into one resolved-once value is the win. But ADR-0043 explicitly prefers narrow contracts. The synthesizer must reconcile: is `LanguagePack` "one narrow contract (the language-completeness contract)" or "seven contracts smuggled into one frozen value"?
5. **Performance-canary baseline ownership.** I propose committed baseline numbers for Node cold-gather wall-clock and conformance-tier wall-clock, ratcheted deliberately. Where do these baselines live, who re-baselines them when hardware changes, and should they gate CI hard or warn? A hard gate enforces the lens's thesis but risks flaky-hardware false failures.
