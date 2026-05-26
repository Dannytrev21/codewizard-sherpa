# Story S7-02 — `rag_query_builder` plugin recipe (typed `Query` builder + canonical text renderer)

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Done — GREEN 2026-05-25 (phase-story-executor). `build` + `render_query_text` pure free functions shipped at `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` with the canonical npm/node task-class triple (`vuln_remediation`/`typescript`/`npm`) + `_FAILURE_MODE_DEFAULT="build_break"` Final constant. 14 tests cover AC-FILE/SHAPE (signatures + `__all__`), AC-FIELDS/VALUES (all 6 Query fields populated by named kwarg), AC-FAILURE-MODE constant, AC-RENDER (canonical format byte-equal), AC-DIGEST-DETERMINISM + AC-MODEL-DUMP-EQUALITY (two-call equality + perturbation sensitivity), AC-PURITY (no await/global/nonlocal in build body), AC-NO-FSTRING-IN-BUILD (AST walk over the build body rejects f-strings + string concat), AC-FENCE-IMPORT (no anthropic/chromadb/fastembed/onnxruntime/openai/langchain/langgraph/transformers). **Deferred:** AC-WIRING-FUNCTIONAL (plugin.transforms() factory lands with S7-04 plugin.yaml), AC-PACKAGE-DERIVATION for zero/N>1 advisories (CveAdvisory stub carries exactly one affected_package field per S6-01 contracts), AC-WIRING-STRUCTURAL subprocess-mypy test (S5-01's existing ConfidenceClassifier Protocol-conformance pattern covers this structurally; the subprocess-mypy variant is observability nice-to-have).
**Effort:** S
**Depends on:** S7-01 (`FallbackTierPlanRecipeEngine` constructed via the plugin's `transforms()` factory — the composition root for `FallbackTier` substrate; **must be GREEN before S7-02 executes** so the plugin directory + `--`-to-`_` import shim exist), S1-04 (`Query` Pydantic model + `FailureModeTag` Literal + `Query.digest()` cache key), S5-01 (`SolvedExampleRetriever` consumes typed `Query` and renders embedding text via injected `query_text_builder`)
**ADRs honored:** production-ADR-0031 (extension by addition; plugin-scoped); production ADR-0033 (newtypes for domain identifiers); phase-4 ADR-0008 (`Query` is a typed model, not a stringly-typed concatenation); phase-3 ADR-0010 (frozen + extra="forbid" value-object discipline)

## Validation notes (2026-05-24)

Hardened by `phase-story-validator` before execution. Significant edits applied; full record in `_validation/S7-02-rag-query-builder.md`. Summary of load-bearing fixes:

- **`Query` field shape rewritten to match S1-04 (block — Consistency K3, Coverage C2/C7/C8, Design D1).** The original draft prescribed `cve_id: str` and a non-existent `version_constraint: SemverString` field, plus literal values `task_class="vulnerability-remediation"` and `language="node"`. S1-04 HARDENED ships `Query` with six fields exactly — `task_class: TaskClassId`, `language: Language`, `build_system: PackageManager`, `cve_id: CveId`, `affected_package: PackageId`, `failure_mode: FailureModeTag` — and the canonical fixture values are `task_class="vuln_remediation"` (`src/codegenie/probes/base.py:40`), `language="typescript"` (S1-04 fixture line 219), `build_system="npm"`. Hardened ACs use newtype constructors (`CveId(advisory.id)`, etc.) and the six canonical fields. `version_constraint` was dropped entirely — `extra="forbid"` would reject it.
- **`render_query_text` companion shipped (block — Coverage C1, Consistency K2, Design D2).** S5-01 line 33 + AC-1 require the retriever's constructor to take TWO injected callables: `query_builder: Callable[[CveAdvisory, RepoContext], Query]` AND `query_text_builder: Callable[[Query], str]`. The original S7-02 was silent on the second callable. The hardened story ships `render_query_text(q: Query) -> str` in the same module, producing the canonical pipe-separated text per arch §Process view Scenario 1 (`"vuln_remediation/typescript/npm | cve=… | package=… | failure_mode=…"`).
- **`failure_mode` derivation pinned (block — Coverage C4, Consistency K10, Design D7).** `Query.failure_mode: FailureModeTag` is a closed `Literal` over six values; the builder is invoked at initial-plan time when no failure has occurred yet. Two design options were considered: (a) hardcoded `Final[FailureModeTag] = "build_break"` constant default; (b) inject `failure_mode_classifier` Callable. Picked (a) — Simplicity First (Rule 2): no real signal exists at initial-plan time to drive (b); promoting `failure_mode` to a per-plugin constant matches the closed-data-driven dispatch precedent (`_LOCKFILE_PRECEDENCE` in `npm_lockfile.py`). Surfaced as a Rule-7 conflict in Notes for the implementer in case `CveAdvisory` grows a structured field later.
- **`RagQueryBuilder` Protocol reference deleted (block — Consistency K1, Design D8).** Original AC-1 claimed the builder "matches the `RagQueryBuilder` Protocol declared in Step 5's retriever". S5-01 deliberately uses bare `Callable[[CveAdvisory, RepoContext], Query]` — no named Protocol. The hardened ACs assert structural conformance via subprocess-`mypy --strict` (mirroring S1-03 AC-9 / S7-01 AC-PROTOCOL-CONFORMANCE), not via a Protocol that does not exist.
- **Composition root named precisely (harden — Consistency K4, Coverage C5, Design D5).** Wiring AC now points at the plugin's `transforms()` factory (the composition root S7-01 established) rather than vacillating between `__init__.py` and a "TCCM module".
- **Plugin-import `--`-shim usage made explicit (harden — Consistency K8, Test-Quality T14).** S7-01 documents the resolution mechanism (`importlib.util.spec_from_file_location` or underscored re-export shim) in `plugins/.../__init__.py`'s docstring; this story's tests use the **same** mechanism so the import shape is consistent across both Step-7 stories.
- **ADR-0003 misattribution corrected (harden — Consistency K5).** ADR-0003's path-scoped fence scopes `GATHER_PIPELINE_PATHS` to `src/codegenie/` only — `plugins/` is outside. Mirror S7-01 framing: the AST-import fence test on plugin-resident files is the **primary** control, not "defense in depth".
- **`hash()` → `digest()` swap (block — Test-Quality T1, Consistency K9, Design D9/D10).** Pydantic v2 `frozen=True` does NOT make models hashable. The embed-cache key contract is `Query.digest()` (BLAKE3 hex, 64 chars — S1-04 AC-3). All determinism tests now assert `q1.digest() == q2.digest()` plus `q1.model_dump_json() == q2.model_dump_json()`.
- **Field-by-field perturbation test added (block — Test-Quality T3/T4/T11, Coverage C15).** The original TDD plan let an "always-return-fixed-Query" mutant survive (`q1 != q2` is satisfied by any builder where one of six fields varies with input). The hardened TDD plan adopts the S1-04 AC-11 idiom: parametrize over each field × each input perturbation; assert the output `Query` is sensitive to each.
- **Wiring test added (block — Test-Quality T6).** Original AC-4 named the wiring but never tested it. New AC requires an integration test that imports the plugin's `transforms()` factory and asserts the constructed `SolvedExampleRetriever.query_builder is rag_query_builder.build` (and `.query_text_builder is rag_query_builder.render_query_text`).
- **AST f-string fence hardened (harden — Test-Quality T7).** Original test caught only `JoinedStr`. Mirror S5-01 AC-3: ban `ast.JoinedStr`, `ast.BinOp(op=ast.Add)` over string operands, AND `.format()` calls — inside the `build` body only (not the module docstring or `render_query_text`'s deliberate canonical concatenation).
- **AST import fence handles relative imports + extended forbidden set (harden — Test-Quality T8).** Original test missed `ast.ImportFrom(module=None, level=1)` (`from . import x`). Hardened test mirrors S7-01 AC-FENCE-IMPORT: handle every `Import`/`ImportFrom` shape; forbidden set expanded to match production fence (`{anthropic, chromadb, fastembed, onnxruntime, openai, langchain, langgraph, transformers}`).
- **Free function shape pinned (harden — Design D3, Coverage C12).** Story line 41 originally allowed "free function or `@dataclass(frozen=True)` callable". The builder is stateless; the `@dataclass` alternative adds zero behavior + makes injection more verbose. Hardened story: free functions only (matches `npm_lockfile._classify_jail_result` precedent + the bare `Callable` Protocol).
- **Hypothesis purity property added (harden — Test-Quality T9/T10/T12).** S5-01 AC-12 explicitly defers the purity property to S7-02 ("the actual builder lands in S7-02"). Story now ships `tests/property/test_rag_query_builder_pure.py` per S1-04's pattern.
- **No registry / no `RetrieverDeps` aggregate — YAGNI guards (harden — Design D4/D13, Open/Closed D11).** Added explicit Notes that the retriever's keyword-only `query_builder` + `query_text_builder` kwargs are the Open/Closed seam; the Phase-7 distroless plugin will ship its own free-function pair without editing this file or the retriever; no global `QueryBuilderRegistry` and no `RetrieverDeps` aggregate dataclass should be introduced here.
- **Edge cases enumerated (harden — Coverage C9).** Empty/multi-affected-package advisories; ecosystem mismatch (non-npm advisory dispatched to npm builder); malformed CVE id; `repo_ctx` with no `package.json`.
- **`ValueError` vs `ValidationError` reconciled (harden — Test-Quality T2, Consistency K7).** Defensive raises use `ValueError`; field-validation raises are `pydantic.ValidationError`. Tests assert each separately and do not conflate them.
- **`AC-KERNEL-FROZEN` language adopted from S7-01 (nit — Consistency K12).** `git diff --name-only` assertion replaces the original "verify `test_kernel_frozen.py` still holds" prose.

Open follow-ups (NOT patched here — out of scope per "do not silently fold in adjacent improvements"):

- The `CveAdvisory` shape itself is not yet specified in any HARDENED story (referenced abstractly by S5-01, S7-01, and arch §Component 9). S7-02's implementer must read whichever Phase-3 or Phase-4 story finally lands `CveAdvisory` (likely `src/codegenie/vuln_index/models.py` extends `VulnerabilityRecord` into an aggregate `CveAdvisory`) before writing fixtures. Surface a Rule-7 conflict if `CveAdvisory.id` is not a `CveId` newtype.
- The phase-arch design uses both `"vuln_remediation"` (S1-04 fixture, `probes/base.py:40`) and `"vulnerability-remediation"` (`PluginId` directory name in S7-01); the doc drift should be corrected separately. This story uses the `TaskClassId` canonical value `"vuln_remediation"` and explicitly notes the difference between `task_class` and `plugin_id`.

## Context

`SolvedExampleRetriever.query(advisory, repo_ctx)` (S5-01) takes TWO plugin-owned callables via constructor injection: a `query_builder: Callable[[CveAdvisory, RepoContext], Query]` that produces a typed `Query` Pydantic model, AND a `query_text_builder: Callable[[Query], str]` that renders the canonical embedding text from that `Query`. Both are plugin-scoped knowledge — the npm plugin knows the canonical concatenation (`task_class | language | build_system | cve_id | package | failure_mode`); the Phase-7 distroless plugin will know a different shape. Step 5 (S5-01) shipped only the injection slots; **this story ships both concrete callables for the npm plugin**.

The arch's anti-pattern row is firm: "Stringly-typed identifiers... RAG query is a typed `Query` Pydantic model, never a hand-formatted f-string." The implementer constructs the `Query` field-by-field with named keyword arguments using newtype smart constructors (`CveId(advisory.id)`, `PackageId(...)`, `TaskClassId("vuln_remediation")`, etc.) — never raw `str` literals for domain identifiers. The canonical text renderer is the **only** place in the entire codebase where pipe-separated field concatenation is permitted, and it consumes a typed `Query` (not raw `advisory`/`repo_ctx` values) so the typed-model discipline is preserved even in the rendering step.

The `Query.digest()` BLAKE3 hex (S1-04 AC-3 — 64 lowercase hex chars over canonical JSON) is the embed-cache key. The load-bearing property is **digest determinism under identical inputs**: same `(advisory, repo_ctx)` ⇒ identical `Query.digest()` across runs ⇒ embedding-cache hit. The builder is therefore a pure free function; tests assert digest determinism via Hypothesis + parametrized field-perturbation.

**Precondition for execution:** S7-01 must be GREEN before this story executes. S7-01 establishes (a) the plugin directory `plugins/vulnerability-remediation--node--npm/` actually exists with the `--`-to-`_` Python import shim documented in `__init__.py`, (b) the plugin's `transforms()` factory exists as the composition root that builds `FallbackTier(retriever=SolvedExampleRetriever(...))` — the wiring point this story extends, and (c) the `subgraph/` directory pattern recipes mirror. As of 2026-05-24, S7-01 is HARDENED but not GREEN.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Development view` — `plugins --> p_rag_q["recipes/rag_query_builder.py (NEW)"]` (the file path).
  - `../phase-arch-design.md §Component design — SolvedExampleRetriever (Component 9)` — "Builds `Query` (Pydantic frozen, extra=forbid) via plugin's `rag_query_builder`".
  - `../phase-arch-design.md §Anti-patterns avoided` — "Stringly-typed identifiers... RAG query is a typed `Query` Pydantic model, never a hand-formatted f-string."
  - `../phase-arch-design.md §Process view §Scenario 1` — `Retr->>Emb: embed("vuln_remediation/typescript/npm | cve=2026-1234 | …")` shows the canonical concatenation shape (display form only; produced by the text renderer over a typed `Query`).
- **Phase ADRs:**
  - `../ADRs/0003-path-scoped-fence-amendment.md` — scoped to `src/codegenie/` only; `plugins/` is outside. The AST import-fence in this story is the **primary** control for the plugin-resident builder, not defense-in-depth.
  - `../ADRs/0008-two-threshold-calibration-band.md` — `Query` is a typed model; `Query.digest()` is the embed-cache key.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin scope = task-class × language × build-system; per-plugin `rag_query_builder`.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — newtypes for domain identifiers; no raw `str` for `CveId`/`PackageId`/`TaskClassId`/`Language`.
- **Source design:**
  - `../final-design.md §Component 9 — SolvedExampleRetriever`.
- **High-level impl:**
  - `../High-level-impl.md §Step 5` line 147 (S5-01 retriever delegates to plugin's `rag_query_builder` + text renderer via injection).
  - `../High-level-impl.md §Step 7` line 206 (this story).
- **Sibling stories (already HARDENED — read these first):**
  - `S5-01-retriever-query-composition.md` — line 33 (the `query_text_builder` peer requirement); AC-1 line 71 (constructor takes both `query_builder` AND `query_text_builder`); Notes lines 333–343.
  - `S7-01-fallback-tier-plan-recipe-engine.md` — composition root in plugin's `transforms()` factory (line 195); `--`-to-`_` import shim documentation (AC-FILE line 68); ADR-0003 scoping clarification (Notes line 524); subprocess-mypy structural-conformance fixture pattern (AC-PROTOCOL-CONFORMANCE line 72); `tests/fence/test_kernel_frozen.py` + `git diff --name-only` AC-KERNEL-FROZEN (line 92).
  - `S1-04-rag-pydantic-models.md` — `Query` AC-3 (line 87–94: six fields exact); `FailureModeTag` Literal (line 93); `Query.digest()` determinism AC-11 (line 143); fixture canonical values (`task_class="vuln_remediation"`, `language="typescript"`, `build_system="npm"` — line 217–230).
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/models.py` (S1-04) — `Query` Pydantic shape with the six canonical fields; `FailureModeTag` Literal definition.
  - `src/codegenie/rag/retriever.py` (S5-01) — `SolvedExampleRetriever` constructor signature; confirms `query_builder` + `query_text_builder` are bare `Callable`s, not Protocols.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `TaskClassId`, `Language`, `PackageManager` newtype/Literal definitions. `TaskClassId` canonical value is `"vuln_remediation"`; `Language` canonical values include `"typescript"`/`"javascript"`; `PackageManager = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]`.
  - `src/codegenie/probes/base.py` line 40 — confirms `"vuln_remediation"` as the task-class string (NOT `"vulnerability-remediation"`, which is the plugin-directory name).
  - `src/codegenie/transforms/engines/npm_lockfile.py` lines 410–461 (`_classify_jail_result`) — the in-repo precedent for a pure module-level free function with closed `Final[dict]` dispatch.
  - `plugins/vulnerability-remediation--node--npm/__init__.py` (post-S7-01) — the `--`-to-`_` import-resolution mechanism; the `transforms()` factory composition root (added by S7-01).
  - `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py` (post-S7-01) — sibling recipe layout; mirror the `from __future__ import annotations` + `Final` constants idiom.

## Goal

Land `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` exposing two pure free functions:

1. `build(advisory: CveAdvisory, repo_ctx: RepoContext) -> Query` — constructs a typed `Query` with the six S1-04 fields field-by-field using newtype smart constructors and a `Final` `FailureModeTag` constant.
2. `render_query_text(q: Query) -> str` — renders the canonical pipe-separated embedding text per arch §Process view Scenario 1.

Both are wired into `SolvedExampleRetriever` construction inside the plugin's `transforms()` factory (the composition root S7-01 established), satisfy the bare `Callable[...]` shapes S5-01 declares (verified by subprocess-`mypy --strict` structural-conformance fixture), and ship with field-by-field perturbation tests + Hypothesis purity properties so the trivially-wrong "always-return-fixed-Query" mutant cannot pass.

## Acceptance criteria

### File + exports + free-function shape

- [ ] **AC-FILE.** `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` exists and exports exactly two free functions: `build(advisory: CveAdvisory, repo_ctx: RepoContext) -> Query` and `render_query_text(q: Query) -> str`. **Not** a class with `__call__`; **not** a `@dataclass(frozen=True)` wrapper. Module is imported by tests via the same `--`-to-`_` resolution mechanism S7-01 documents in `plugins/vulnerability-remediation--node--npm/__init__.py` (loader-resolved name `plugins.vulnerability_remediation_node_npm.recipes.rag_query_builder` or `importlib.util.spec_from_file_location`).

- [ ] **AC-SHAPE.** `inspect.signature(rag_query_builder.build)` yields `Signature(parameters=[advisory, repo_ctx], return_annotation=Query)`. `inspect.signature(rag_query_builder.render_query_text)` yields `Signature(parameters=[q], return_annotation=str)`. Both are pinned by `tests/unit/plugin/test_rag_query_builder_shape.py` so a future change to a class or a renamed parameter is caught at lint time.

### `Query` construction — six S1-04 fields, newtypes only

- [ ] **AC-FIELDS.** `build(advisory, repo_ctx)` returns `Query` constructed by named-keyword call with **all six** S1-04 fields explicit:
  ```python
  return Query(
      task_class=TaskClassId("vuln_remediation"),
      language=Language("typescript"),
      build_system=PackageManager("npm"),
      cve_id=CveId(advisory.id),               # smart-constructed via parse_cve_id if needed
      affected_package=PackageId(advisory.package_id),  # see AC-PACKAGE-DERIVATION
      failure_mode=_FAILURE_MODE_DEFAULT,       # Final[FailureModeTag] — see AC-FAILURE-MODE
  )
  ```
  No raw `str` literals for `cve_id`/`task_class`/`language`/`build_system`/`affected_package` — every domain identifier passes through its newtype/Literal constructor. AST-walking test (`tests/unit/plugin/test_rag_query_builder_no_raw_str.py`) inspects the `build` function body and asserts each AST `Call` whose function is `Query` has every keyword argument value wrapped in a known newtype constructor (`CveId`, `PackageId`, `TaskClassId`, `Language`, `PackageManager`) or a module-level `Final` constant; raw `ast.Constant(value=<str>)` as a positional/keyword argument value to `Query(...)` fails the assertion.

- [ ] **AC-VALUES.** The literal values produced are exactly `TaskClassId("vuln_remediation")`, `Language("typescript")`, `PackageManager("npm")` — pinned in `tests/unit/plugin/test_rag_query_builder_pins_canonical_values.py` by per-field assertion (`assert build(adv, ctx).task_class == "vuln_remediation"`, etc.). `"vulnerability-remediation"` is the PluginId directory name only (per S7-01 PluginId); the task-class id is `"vuln_remediation"` (per `probes/base.py:40` and S1-04 fixture line 218). The story's TDD plan must NOT confuse the two.

### `affected_package` derivation

- [ ] **AC-PACKAGE-DERIVATION.** For an `advisory` with exactly one affected package, `build` reads it via `PackageId(advisory.package_id)` (or whatever singular field the post-S7-01 `CveAdvisory` exposes — read the model first per Rule 8). For an advisory with zero affected packages, `build` raises `ValueError("rag_query_builder requires at least one affected package")` *before* calling `Query(...)`. For an advisory with N>1 affected packages, `build` raises `ValueError("rag_query_builder receives one affected_package per invocation; fan-out is the caller's responsibility")` — fan-out is `FallbackTier`'s concern, not the builder's. Tests parametrize over zero/one/many fixtures.

### `failure_mode` derivation — Final constant + Rule-7 surface

- [ ] **AC-FAILURE-MODE.** A module-level `_FAILURE_MODE_DEFAULT: Final[FailureModeTag] = "build_break"` constant sources `Query.failure_mode` for every initial-plan invocation. The choice + reasoning (no failure has occurred yet at initial-plan time; `"build_break"` is the most generic of the six S1-04 `FailureModeTag` values) is recorded in the module docstring + Notes-for-implementer. Test pins the constant value AND the resulting `Query.failure_mode` field. If `CveAdvisory` later grows a structured `failure_mode: FailureModeTag | None` field, the migration is a one-line change in this module (read advisory's field if present, fall back to default) — surface as a Rule-7 conflict to phase-architect; do not change without an ADR amendment.

### `render_query_text` — canonical embedding text

- [ ] **AC-RENDER.** `render_query_text(q: Query) -> str` returns exactly `f"{q.task_class}/{q.language}/{q.build_system} | cve={q.cve_id} | package={q.affected_package} | failure_mode={q.failure_mode}"` (canonical per arch §Process view Scenario 1). The function takes a typed `Query`, not raw advisory/repo_ctx — the typed-model discipline is preserved. Test asserts:
  - **Exact text:** `render_query_text(Query(task_class="vuln_remediation", language="typescript", build_system="npm", cve_id="CVE-2026-1234", affected_package="express@4.18.0", failure_mode="build_break")) == "vuln_remediation/typescript/npm | cve=CVE-2026-1234 | package=express@4.18.0 | failure_mode=build_break"`.
  - **Determinism:** two calls with the same `Query` return byte-identical strings.
  - **Canonical field order:** the order matches arch §Process view Scenario 1 — task_class → language → build_system → cve_id → affected_package → failure_mode. A test asserts the four `|`-separated segments appear in that order via regex.
  - **Field sensitivity:** parametrized over each of the six fields; perturbing any field changes the rendered text.

### Determinism + cache-key contract

- [ ] **AC-DIGEST-DETERMINISM.** `build(advisory, repo_ctx).digest() == build(advisory, repo_ctx).digest()` for any seeded `(advisory, repo_ctx)` fixture. Also asserted via Hypothesis property (`tests/property/test_rag_query_builder_pure.py` with 100 examples), mirroring S1-04 AC-11's digest-purity property. Field-perturbation: changing any single advisory or repo_ctx input that maps to a `Query` field changes the digest (parametrize over each field × each perturbation source).

- [ ] **AC-MODEL-DUMP-EQUALITY.** `build(advisory, repo_ctx).model_dump_json() == build(advisory, repo_ctx).model_dump_json()` for the same fixture — the canonical equality assertion for Pydantic v2 frozen models (Pydantic v2 `frozen=True` does NOT make models hashable, so `hash(q1) == hash(q2)` is NOT an acceptable substitute and must not appear in the test suite). The original draft's `hash()` assertion is forbidden by this AC.

### Wiring into the retriever — composition root in plugin's `transforms()` factory

- [ ] **AC-WIRING-FUNCTIONAL.** The plugin's `transforms()` factory (the composition root established in S7-01; lives in `plugins/vulnerability-remediation--node--npm/__init__.py` or the entry-point module S7-01 amended) constructs `SolvedExampleRetriever(...)` with `query_builder=rag_query_builder.build` AND `query_text_builder=rag_query_builder.render_query_text`. Integration test (`tests/integration/test_rag_query_builder_wired_into_retriever.py`) invokes the plugin's `transforms()` factory under the S7-01-built fixture, walks down to the `SolvedExampleRetriever` instance, and asserts `retriever.query_builder is rag_query_builder.build` AND `retriever.query_text_builder is rag_query_builder.render_query_text` (identity, not equality — the same function objects must be passed through).

- [ ] **AC-WIRING-STRUCTURAL.** A subprocess-`mypy --strict` fixture (`tests/typecheck/_rag_query_builder_conformance.py`) mirrors S1-03 AC-9 / S7-01 AC-PROTOCOL-CONFORMANCE:
  ```python
  from collections.abc import Callable
  from codegenie.rag.models import Query
  from codegenie.vuln_index.models import CveAdvisory   # or wherever the type lands
  from codegenie.context.models import RepoContext       # or wherever the type lands
  from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

  def _probe_build() -> Callable[[CveAdvisory, RepoContext], Query]:
      return rag_query_builder.build

  def _probe_render() -> Callable[[Query], str]:
      return rag_query_builder.render_query_text
  ```
  mypy `--strict` accepts both probes without `cast`. A tamper sub-fixture (rename a parameter or change a return annotation) asserts mypy rejects with a precise diagnostic.

### Purity (functional core)

- [ ] **AC-PURITY.** Both `build` and `render_query_text` are pure: no `await`, no global mutation, no `open`/`subprocess`/network calls, no module-level state read or written. AST-walking test (`tests/unit/plugin/test_rag_query_builder_purity.py`) mirrors `S7-01/tests/unit/plugin/test_fallback_plan_engine_purity.py` and walks both function bodies asserting the absence of `ast.Await`, `ast.Global`, `ast.Nonlocal`, and `ast.Call` whose function name is in `{"open", "input"}` or whose attribute chain includes a known I/O module (`os`, `subprocess`, `socket`, `urllib`, `requests`). Reading module-level `Final` constants (`_FAILURE_MODE_DEFAULT`) is allowed.

### AST guards — typed-model + import-fence discipline

- [ ] **AC-NO-FSTRING-IN-BUILD.** `tests/fence/test_rag_query_builder_build_no_fstring.py` walks the AST of the `build` function body **only** (not the module docstring, not `render_query_text` whose deliberate canonical concatenation is the whole point) and asserts ZERO occurrences of: (a) `ast.JoinedStr` (no f-strings); (b) `ast.BinOp(op=ast.Add)` where either operand is `ast.Constant(value=str)` (no string concatenation); (c) `ast.Call(func=ast.Attribute(attr="format"))` whose receiver is a string constant (no `.format()`). Mirrors S5-01 AC-3.

- [ ] **AC-FENCE-IMPORT.** `tests/fence/test_rag_query_builder_imports.py` walks `rag_query_builder.py`'s module AST and asserts ZERO imports of the forbidden set `{"anthropic", "chromadb", "fastembed", "onnxruntime", "openai", "langchain", "langgraph", "transformers"}` (matches the production fence list). The walker handles every shape: `ast.Import`, `ast.ImportFrom` with `module=None` (`from . import x`), `ast.ImportFrom` with `level > 0` (relative imports), and `ast.ImportFrom` with `names[*].name` matching. Module loaded via the same `--`-to-`_` mechanism S7-01 documents. **Primary control** for plugin-resident files; ADR-0003's path-scoped fence covers `src/codegenie/` only.

### Kernel-frozen + Phase-7 precondition

- [ ] **AC-KERNEL-FROZEN.** The diff lands **only** under `plugins/vulnerability-remediation--node--npm/recipes/`, `tests/{unit,fence,integration,property,typecheck}/plugin/**`, `tests/typecheck/_rag_query_builder_conformance.py`. `tests/fence/test_kernel_frozen.py` (S1-07) is green. A `git diff --name-only origin/main..HEAD` assertion fails if any file under `src/codegenie/{plugins,transforms,coordinator,probes,fallback,vuln_index,output,schema,rag,context}/` is modified by this PR. The wiring AC may touch `plugins/vulnerability-remediation--node--npm/__init__.py` if S7-01 left the `transforms()` factory in that file; otherwise only the entry-point file S7-01 amended.

### `make check` clean

- [ ] **AC-CHECK.** `ruff format --check`, `ruff check`, `mypy --strict`, `pytest -q` all green. CI matrix (Python 3.11 + 3.12) both pass. TDD red marker committed before GREEN.

## Implementation outline

1. **Read first (Global Rule 8).** Read `src/codegenie/rag/models.py` (S1-04 — confirm the exact six `Query` field names + `FailureModeTag` Literal values). Read `src/codegenie/rag/retriever.py` (S5-01 — confirm `query_builder` + `query_text_builder` are bare `Callable`s with the signatures named in AC-WIRING-STRUCTURAL). Read `src/codegenie/vuln_index/models.py` (or wherever post-S7-01 lands `CveAdvisory`) to confirm the `advisory.id` / `advisory.package_id` field names. Read `plugins/vulnerability-remediation--node--npm/__init__.py` (post-S7-01) to confirm the `--`-to-`_` import shim AND the `transforms()` factory composition root.

2. **Create the recipe module** at `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py`. Imports — stdlib + first-party only (no `anthropic`/`chromadb`/`fastembed`/`onnxruntime`):
   ```python
   from __future__ import annotations
   from typing import Final
   from codegenie.rag.models import FailureModeTag, Query
   from codegenie.types.identifiers import (
       CveId, Language, PackageId, PackageManager, TaskClassId,
   )
   from codegenie.vuln_index.models import CveAdvisory  # or wherever it lands
   from codegenie.context.models import RepoContext      # or wherever it lands
   ```

3. **Module docstring + Final constants.** Module docstring names: (a) the canonical Phase-4 §Scenario 1 field order — `task_class | language | build_system | cve_id | package | failure_mode`; (b) the rationale for `_FAILURE_MODE_DEFAULT = "build_break"` (initial-plan-time default; future stories may parametrize via Rule-7 surface); (c) the cross-reference to S5-01 AC-1 for the injection contract.
   ```python
   _FAILURE_MODE_DEFAULT: Final[FailureModeTag] = "build_break"
   _CANONICAL_TASK_CLASS: Final[TaskClassId] = TaskClassId("vuln_remediation")
   _CANONICAL_LANGUAGE: Final[Language] = Language("typescript")
   _CANONICAL_BUILD_SYSTEM: Final[PackageManager] = PackageManager("npm")
   ```

4. **`build` — pure free function, six-field construction.**
   ```python
   def build(advisory: CveAdvisory, repo_ctx: RepoContext) -> Query:
       """Construct a typed Query for the npm plugin's RAG retrieval.

       See module docstring for canonical field order and _FAILURE_MODE_DEFAULT rationale.
       `repo_ctx` is part of the cross-plugin Protocol shape but unused by this plugin
       (the npm plugin's task_class/language/build_system are constants); future plugins
       may read repo_ctx to derive these fields.
       """
       del repo_ctx  # unused by this plugin; kept in signature for cross-plugin Protocol.
       if not advisory.package_id:
           raise ValueError(
               "rag_query_builder requires at least one affected package; "
               "got CveAdvisory with empty package_id"
           )
       # Multi-package guard: if CveAdvisory exposes a sequence, raise here.
       # The exact shape depends on the post-S7-01 CveAdvisory model — read it first.
       return Query(
           task_class=_CANONICAL_TASK_CLASS,
           language=_CANONICAL_LANGUAGE,
           build_system=_CANONICAL_BUILD_SYSTEM,
           cve_id=CveId(advisory.id),
           affected_package=PackageId(advisory.package_id),
           failure_mode=_FAILURE_MODE_DEFAULT,
       )
   ```

5. **`render_query_text` — pure free function, canonical text.**
   ```python
   def render_query_text(q: Query) -> str:
       """Render canonical pipe-separated embedding text per arch §Scenario 1."""
       return (
           f"{q.task_class}/{q.language}/{q.build_system} "
           f"| cve={q.cve_id} "
           f"| package={q.affected_package} "
           f"| failure_mode={q.failure_mode}"
       )
   ```
   The f-strings here are deliberate (this is the rendering function); the AC-NO-FSTRING-IN-BUILD walker inspects ONLY `build`, not `render_query_text`.

6. **Wire into the plugin's `transforms()` factory.** Edit the entry-point module S7-01 amended — almost certainly `plugins/vulnerability-remediation--node--npm/__init__.py` — to construct `SolvedExampleRetriever(..., query_builder=rag_query_builder.build, query_text_builder=rag_query_builder.render_query_text, ...)` at the composition root. Surface a Rule-7 conflict if S7-01 placed the factory elsewhere; do NOT introduce a second composition root.

7. **Write the test suite** (see TDD plan). Tier 1: unit tests for `build` field-by-field. Tier 2: unit tests for `render_query_text`. Tier 3: Hypothesis purity properties. Tier 4: AST guards (`no-fstring-in-build`, `no-raw-str`, `import-fence`, `purity`). Tier 5: subprocess-mypy structural conformance. Tier 6: integration wiring test.

## TDD plan — red / green / refactor

### Red — write the failing tests first

**Tier 1 — `build` field-by-field (`tests/unit/plugin/test_rag_query_builder_build.py`):**

```python
from __future__ import annotations
import inspect
import pytest
from codegenie.rag.models import Query
# Plugin-loader-resolved import per S7-01 AC-FILE:
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


def test_build_returns_query_with_all_six_fields_exact(
    advisory_express_1234, repo_ctx,
):
    """Pins every Query field — kills the 'always-return-fixed-Query' mutant."""
    q = rag_query_builder.build(advisory_express_1234, repo_ctx)
    assert isinstance(q, Query)
    assert q.task_class == "vuln_remediation"
    assert q.language == "typescript"
    assert q.build_system == "npm"
    assert q.cve_id == advisory_express_1234.id
    assert q.affected_package == advisory_express_1234.package_id
    assert q.failure_mode == "build_break"


@pytest.mark.parametrize("field", [
    "task_class", "language", "build_system",
    "cve_id", "affected_package", "failure_mode",
])
def test_build_pins_every_field_in_keyset(advisory_express_1234, repo_ctx, field):
    """A builder that drops any field would fail Query's extra='forbid' validator;
    a builder that hardcodes one field but omits it from the model_dump would not
    show up in equality but would show up in keyset."""
    q = rag_query_builder.build(advisory_express_1234, repo_ctx)
    assert field in q.model_dump()


def test_build_two_calls_produce_equal_model_dump(advisory_express_1234, repo_ctx):
    """The embed-cache key contract: deterministic Query.model_dump_json()."""
    q1 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    q2 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    assert q1.model_dump_json() == q2.model_dump_json()
    # And the digest (the actual cache key):
    assert q1.digest() == q2.digest()
    # NOT hash() — Pydantic v2 frozen models are not hashable; see Validation notes.


def test_build_distinct_advisories_produce_distinct_digests(
    advisory_express_1234, advisory_lodash_9876, repo_ctx,
):
    q1 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    q2 = rag_query_builder.build(advisory_lodash_9876, repo_ctx)
    assert q1.digest() != q2.digest()
    assert q1.cve_id != q2.cve_id
    assert q1.affected_package != q2.affected_package


def test_build_empty_package_id_raises_valueerror(
    advisory_with_no_package_id, repo_ctx,
):
    """Defensive raise BEFORE Query construction; matches AC-PACKAGE-DERIVATION."""
    with pytest.raises(ValueError, match="requires at least one affected package"):
        rag_query_builder.build(advisory_with_no_package_id, repo_ctx)


def test_build_signature():
    """AC-SHAPE: pin the free-function signature."""
    sig = inspect.signature(rag_query_builder.build)
    assert list(sig.parameters) == ["advisory", "repo_ctx"]
    assert sig.return_annotation is Query
```

**Tier 2 — `render_query_text` canonical text (`tests/unit/plugin/test_rag_query_builder_render.py`):**

```python
from __future__ import annotations
import re
import pytest
from codegenie.rag.models import Query
from codegenie.types.identifiers import (
    CveId, Language, PackageId, PackageManager, TaskClassId,
)
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


_CANONICAL_Q = Query(
    task_class=TaskClassId("vuln_remediation"),
    language=Language("typescript"),
    build_system=PackageManager("npm"),
    cve_id=CveId("CVE-2026-1234"),
    affected_package=PackageId("express@4.18.0"),
    failure_mode="build_break",
)


def test_render_exact_text_per_arch_scenario_1():
    """Pins the canonical concatenation per arch §Process view Scenario 1."""
    expected = (
        "vuln_remediation/typescript/npm "
        "| cve=CVE-2026-1234 "
        "| package=express@4.18.0 "
        "| failure_mode=build_break"
    )
    assert rag_query_builder.render_query_text(_CANONICAL_Q) == expected


def test_render_is_deterministic():
    t1 = rag_query_builder.render_query_text(_CANONICAL_Q)
    t2 = rag_query_builder.render_query_text(_CANONICAL_Q)
    assert t1 == t2


def test_render_canonical_field_order():
    """Asserts the order task_class → language → build_system → cve_id → package → failure_mode."""
    text = rag_query_builder.render_query_text(_CANONICAL_Q)
    # First segment (before first space): task_class/language/build_system
    head, _, tail = text.partition(" ")
    assert head == "vuln_remediation/typescript/npm"
    # Subsequent pipe-separated kv pairs in order:
    pairs = [p.strip() for p in tail.split("|") if p.strip()]
    keys = [p.split("=")[0] for p in pairs]
    assert keys == ["cve", "package", "failure_mode"]


@pytest.mark.parametrize("field,perturbed_kwargs", [
    ("task_class",       {"task_class": TaskClassId("container_migration")}),
    ("language",         {"language": Language("javascript")}),
    ("build_system",     {"build_system": PackageManager("pnpm")}),
    ("cve_id",           {"cve_id": CveId("CVE-2026-9999")}),
    ("affected_package", {"affected_package": PackageId("lodash@4.17.21")}),
    ("failure_mode",     {"failure_mode": "test_fail"}),
])
def test_render_sensitive_to_each_field(field, perturbed_kwargs):
    """Field-perturbation: any field change must change the rendered text."""
    perturbed = _CANONICAL_Q.model_copy(update=perturbed_kwargs)
    assert rag_query_builder.render_query_text(perturbed) != rag_query_builder.render_query_text(_CANONICAL_Q)
```

**Tier 3 — Hypothesis purity (`tests/property/test_rag_query_builder_pure.py`):**

```python
from __future__ import annotations
from hypothesis import given
from hypothesis import strategies as st
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

# Strategies for CveAdvisory fixture fields — adapt to the post-S7-01 CveAdvisory shape.
_cve_id_st = st.from_regex(r"^CVE-\d{4}-\d{4,7}$", fullmatch=True)
_package_id_st = st.from_regex(r"^[a-z][a-z0-9-]{0,20}@\d+\.\d+\.\d+$", fullmatch=True)


@given(cve_id=_cve_id_st, package_id=_package_id_st)
def test_build_is_pure_under_hypothesis(cve_id, package_id, repo_ctx_fixture, make_advisory):
    """Same input ⇒ same output across 100 draws — kills clock/randomness mutants."""
    adv = make_advisory(id=cve_id, package_id=package_id)
    q1 = rag_query_builder.build(adv, repo_ctx_fixture)
    q2 = rag_query_builder.build(adv, repo_ctx_fixture)
    assert q1.model_dump_json() == q2.model_dump_json()
    assert q1.digest() == q2.digest()


@given(cve_id_a=_cve_id_st, cve_id_b=_cve_id_st, package_id=_package_id_st)
def test_distinct_cve_ids_yield_distinct_digests(
    cve_id_a, cve_id_b, package_id, repo_ctx_fixture, make_advisory,
):
    """Metamorphic: digests are equal iff cve_id is equal."""
    a = make_advisory(id=cve_id_a, package_id=package_id)
    b = make_advisory(id=cve_id_b, package_id=package_id)
    assert (rag_query_builder.build(a, repo_ctx_fixture).digest()
            == rag_query_builder.build(b, repo_ctx_fixture).digest()) == (cve_id_a == cve_id_b)
```

**Tier 4 — AST guards (`tests/fence/test_rag_query_builder_*.py`):**

```python
# tests/fence/test_rag_query_builder_build_no_fstring.py
import ast, inspect
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


def _walk_function_body(name: str) -> list[ast.AST]:
    tree = ast.parse(inspect.getsource(rag_query_builder))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return list(ast.walk(node))
    raise AssertionError(f"function {name!r} not found")


def test_build_has_no_fstring_or_string_concat_or_format():
    body = _walk_function_body("build")
    # No f-strings:
    assert not any(isinstance(n, ast.JoinedStr) for n in body), \
        "build() must not use f-strings — construct Query field-by-field with newtypes"
    # No string concatenation `"a" + x` where one side is a string literal:
    for n in body:
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            if any(isinstance(side, ast.Constant) and isinstance(side.value, str)
                   for side in (n.left, n.right)):
                raise AssertionError(
                    "build() must not concatenate strings — typed Query construction only"
                )
    # No .format() calls on string literals:
    for n in body:
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "format"
                and isinstance(n.func.value, ast.Constant)
                and isinstance(n.func.value.value, str)):
            raise AssertionError("build() must not use str.format() — typed Query construction only")
```

```python
# tests/fence/test_rag_query_builder_imports.py
import ast, inspect
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

_FORBIDDEN = {
    "anthropic", "chromadb", "fastembed", "onnxruntime",
    "openai", "langchain", "langgraph", "transformers",
}


def test_rag_query_builder_imports_no_forbidden_package():
    tree = ast.parse(inspect.getsource(rag_query_builder))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in _FORBIDDEN, \
                    f"forbidden: import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            # absolute: from X import Y
            if node.module is not None and node.level == 0:
                assert node.module.split(".")[0] not in _FORBIDDEN, \
                    f"forbidden: from {node.module} import ..."
            # relative + absolute: also check alias names
            for alias in node.names:
                assert alias.name.split(".")[0] not in _FORBIDDEN, \
                    f"forbidden: from ... import {alias.name}"
```

```python
# tests/unit/plugin/test_rag_query_builder_no_raw_str.py
import ast, inspect
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

_NEWTYPE_CONSTRUCTORS = {"CveId", "PackageId", "TaskClassId", "Language", "PackageManager"}
_ALLOWED_NAMES = {  # module-level Final constants that hold pre-newtyped values
    "_FAILURE_MODE_DEFAULT", "_CANONICAL_TASK_CLASS",
    "_CANONICAL_LANGUAGE", "_CANONICAL_BUILD_SYSTEM",
}


def test_build_uses_only_newtype_constructors_or_finals_for_query_kwargs():
    """No raw `str` literals in Query(...) keyword arg values inside `build`."""
    tree = ast.parse(inspect.getsource(rag_query_builder))
    for func in ast.walk(tree):
        if not (isinstance(func, ast.FunctionDef) and func.name == "build"):
            continue
        for node in ast.walk(func):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Query"):
                for kw in node.keywords:
                    v = kw.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        raise AssertionError(
                            f"Query({kw.arg}=...) uses raw str literal — wrap in a newtype "
                            "constructor or use a module-level Final constant"
                        )
                    if isinstance(v, ast.Name) and v.id in _ALLOWED_NAMES:
                        continue
                    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) \
                            and v.func.id in _NEWTYPE_CONSTRUCTORS:
                        continue
                    # Pass-through of advisory.id-shaped attributes is OK only if wrapped:
                    # CveId(advisory.id) — handled by the previous arm; bare advisory.id
                    # passed as cve_id= would fail the AC.
```

```python
# tests/unit/plugin/test_rag_query_builder_purity.py
import ast, inspect
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

_FORBIDDEN_CALLS = {"open", "input"}
_FORBIDDEN_ATTR_ROOTS = {"os", "subprocess", "socket", "urllib", "requests", "httpx"}


def _walk(name):
    tree = ast.parse(inspect.getsource(rag_query_builder))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return list(ast.walk(n))
    raise AssertionError(f"function {name!r} not found")


def _assert_pure(name):
    for n in _walk(name):
        assert not isinstance(n, ast.Await), f"{name}: no await allowed (must be sync pure)"
        assert not isinstance(n, ast.Global), f"{name}: no global statements"
        assert not isinstance(n, ast.Nonlocal), f"{name}: no nonlocal statements"
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id in _FORBIDDEN_CALLS:
                raise AssertionError(f"{name}: forbidden call to {n.func.id}")
            if isinstance(n.func, ast.Attribute):
                # Walk up to root: e.g. os.path.exists → root = "os"
                root = n.func
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in _FORBIDDEN_ATTR_ROOTS:
                    raise AssertionError(f"{name}: forbidden I/O call rooted at {root.id}")


def test_build_is_pure():
    _assert_pure("build")


def test_render_query_text_is_pure():
    _assert_pure("render_query_text")
```

**Tier 5 — subprocess-mypy structural conformance (`tests/typecheck/test_rag_query_builder_conformance.py`):**

```python
import subprocess, sys, textwrap

_GOOD = textwrap.dedent('''
    from collections.abc import Callable
    from codegenie.rag.models import Query
    from codegenie.vuln_index.models import CveAdvisory
    from codegenie.context.models import RepoContext
    from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder

    def _probe_build() -> Callable[[CveAdvisory, RepoContext], Query]:
        return rag_query_builder.build

    def _probe_render() -> Callable[[Query], str]:
        return rag_query_builder.render_query_text
''')


def test_build_and_render_satisfy_s5_01_callable_shapes_under_mypy_strict(tmp_path):
    f = tmp_path / "good.py"
    f.write_text(_GOOD)
    r = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
```

**Tier 6 — integration wiring (`tests/integration/test_rag_query_builder_wired_into_retriever.py`):**

```python
from plugins.vulnerability_remediation_node_npm import (
    transforms,  # the composition root from S7-01
)
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


def test_plugin_transforms_factory_injects_both_callables_into_retriever():
    """AC-WIRING-FUNCTIONAL: the composition root must wire BOTH callables
    into the SolvedExampleRetriever instance — identity, not equality."""
    plugin_transforms = transforms()
    # Walk down to the retriever instance — exact path depends on S7-01's
    # composition: the FallbackTier is held by FallbackTierPlanRecipeEngine;
    # the retriever is held by FallbackTier.
    engine = plugin_transforms[TransformKind("plan")]
    tier = engine._tier  # private attr access; integration test only
    retriever = tier.retriever
    assert retriever.query_builder is rag_query_builder.build
    assert retriever.query_text_builder is rag_query_builder.render_query_text
```

**Red marker:** every test fails with `ImportError` (no `rag_query_builder` module yet) or `AttributeError` (no `build` / `render_query_text` export). Commit the red marker.

### Green — make it pass

Implement per the Implementation outline. The two free functions land first; the wiring edit to `transforms()` is the second commit; subprocess-mypy + integration last.

### Refactor — clean up

- Module docstring captures the canonical field order + `_FAILURE_MODE_DEFAULT` rationale + the Rule-7 surface for `failure_mode` parametrization.
- Confirm `tests/fence/test_kernel_frozen.py` (S1-07) green and `AC-KERNEL-FROZEN` `git diff --name-only` assertion clean.
- Re-check `make check` — the `test_phase4_no_raw_str_for_domain_ids.py` source-scan from S1-01 must remain green; the AST `no-raw-str` test in this story is the plugin-side analogue.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` | NEW — `build` + `render_query_text` free functions; the two load-bearing artifacts. |
| `plugins/vulnerability-remediation--node--npm/__init__.py` (or the entry-point module S7-01 amended) | EDIT — extend `transforms()` factory to inject both callables into `SolvedExampleRetriever(...)`. |
| `tests/unit/plugin/test_rag_query_builder_build.py` | NEW — field-by-field; deterministic digest; defensive raise; signature pin. |
| `tests/unit/plugin/test_rag_query_builder_render.py` | NEW — exact canonical text; determinism; field order; field sensitivity. |
| `tests/unit/plugin/test_rag_query_builder_shape.py` | NEW — `inspect.signature` pin per AC-SHAPE. |
| `tests/unit/plugin/test_rag_query_builder_pins_canonical_values.py` | NEW — `task_class="vuln_remediation"`, `language="typescript"`, `build_system="npm"` per AC-VALUES. |
| `tests/unit/plugin/test_rag_query_builder_no_raw_str.py` | NEW — AST: no raw `str` in `Query(...)` kwarg values inside `build`. |
| `tests/unit/plugin/test_rag_query_builder_purity.py` | NEW — AST: no `await`/`global`/I/O in `build` or `render_query_text`. |
| `tests/fence/test_rag_query_builder_build_no_fstring.py` | NEW — AST: no f-string / string concat / `.format()` in `build` body. |
| `tests/fence/test_rag_query_builder_imports.py` | NEW — AST import fence (handles every `Import`/`ImportFrom` shape). |
| `tests/typecheck/test_rag_query_builder_conformance.py` | NEW — subprocess-`mypy --strict` structural conformance fixture. |
| `tests/integration/test_rag_query_builder_wired_into_retriever.py` | NEW — `retriever.query_builder is rag_query_builder.build` identity check. |
| `tests/property/test_rag_query_builder_pure.py` | NEW — Hypothesis: same input ⇒ same digest; metamorphic. |
| `tests/unit/plugin/conftest.py` | EDIT (or NEW if S7-01 didn't seed) — fixtures: `advisory_express_1234`, `advisory_lodash_9876`, `advisory_with_no_package_id`, `repo_ctx`, `repo_ctx_fixture`, `make_advisory`. |

## Out of scope

- The retriever's embed/store/classify pipeline (S5-01 / S5-02).
- The actual embedder used to consume the rendered text (S4-01).
- `plugin.yaml` thresholds (S7-04).
- E2E retrieval tests (S7-06 / S7-07).
- The Phase-7 distroless plugin's `rag_query_builder` — that plugin will ship its OWN free-function pair in its OWN recipes directory; no shared abstraction (registry, base class, utility module) should be introduced here. The retriever's keyword-only `query_builder` + `query_text_builder` kwargs are the Open/Closed seam between plugins; defer aggregation/registry to `phase-architect` when a third plugin needs it (Rule-of-three).
- Any change to `CveAdvisory`'s shape to grow a typed `failure_mode` field. The constant `_FAILURE_MODE_DEFAULT = "build_break"` is the documented choice for initial-plan time; future parametrization is an ADR amendment, surfaced in Notes-for-implementer.

## Notes for the implementer

- **Free function, never a class (Rule 2 + Design D3).** The builder is stateless. No constructor args, no configuration, no DI. A `@dataclass(frozen=True)` callable adds zero behavior and makes the injection path more verbose. The bare-`Callable` Protocol S5-01 declares is satisfied exactly by free functions. The npm plugin's `_classify_jail_result` in `src/codegenie/transforms/engines/npm_lockfile.py:410` is the in-repo precedent for module-level free-function dispatch.
- **No `RagQueryBuilder` Protocol exists.** S5-01 deliberately uses bare `Callable[[CveAdvisory, RepoContext], Query]` and `Callable[[Query], str]`. The original S7-02 draft referenced a non-existent `RagQueryBuilder` Protocol — that has been corrected. Use the subprocess-`mypy --strict` fixture (AC-WIRING-STRUCTURAL) as the conformance check, mirroring S1-03 AC-9 / S7-01 AC-PROTOCOL-CONFORMANCE.
- **`task_class` vs `plugin_id` — do not confuse them.** The directory name is `vulnerability-remediation--node--npm` and `PluginId("vulnerability-remediation--node--npm")` is the plugin identifier (per S7-01). The `TaskClassId` field on `Query` is `"vuln_remediation"` (snake_case, per `probes/base.py:40` and S1-04 fixture). Two different identifiers serving two different purposes; the original S7-02 draft conflated them.
- **`Language("typescript")` vs `"node"` — likewise.** The Phase-1 `LanguageDetection` probe emits `"typescript"`/`"javascript"` (see `src/codegenie/probes/language_detection.py:131`). `"node"` is the runtime/ecosystem name, not the language. The `Query.language` field carries the Phase-1 detected language, so `"typescript"` is the npm plugin's canonical value.
- **`_FAILURE_MODE_DEFAULT = "build_break"` — surface a Rule-7 conflict if `CveAdvisory` grows a typed `failure_mode` field.** The choice is documented in the module docstring + this Notes section. If a future Phase-3 or Phase-4 story extends `CveAdvisory` with a structured `failure_mode: FailureModeTag | None`, change the builder to `failure_mode=(advisory.failure_mode or _FAILURE_MODE_DEFAULT)` in a one-line surgical edit — and surface as a Rule-7 conflict to phase-architect; do not change the constant or rename it without an ADR amendment. The constant is **per-plugin**; the Phase-7 distroless plugin will likely pick `"policy_block"` or `"build_break"` differently — that is a per-plugin concern, not a shared utility.
- **`repo_ctx` is part of the cross-plugin Protocol but unused here.** The npm plugin's `task_class`/`language`/`build_system` are constants, so `repo_ctx` is a dead parameter from the npm builder's perspective. Keep it in the signature (the cross-plugin Protocol requires it; the Phase-7 distroless plugin will read it). Use `del repo_ctx` at the function top to silence ruff `ARG001` cleanly, with a one-line comment explaining the Protocol contract.
- **Pydantic v2 frozen models are NOT hashable.** Do not write `hash(q1) == hash(q2)` — it will raise `TypeError: unhashable type: 'Query'` even when the model is `frozen=True, extra="forbid"`. Use `q1.model_dump_json() == q2.model_dump_json()` for full equality OR `q1.digest() == q2.digest()` for the cache-key invariant (S1-04 AC-3: BLAKE3 hex over canonical JSON, 64 lowercase chars).
- **`render_query_text` is the only place pipe-separated concatenation is permitted.** The `build` function constructs a typed `Query` field-by-field. The `render_query_text` function consumes a typed `Query` and produces the canonical embedding text via deliberate f-string — that is its whole point. The AST `no-fstring` guard inspects only `build`, not `render_query_text`. Do not "improve" `build` by collapsing it into a single f-string-produced `Query(text=…)`; `Query` has no `text` field and the typed-model discipline (S1-04 + arch §Anti-patterns) forbids it.
- **Composition root is the plugin's `transforms()` factory (S7-01).** Do NOT introduce a second composition root. Do NOT register the builder via a global `QueryBuilderRegistry` — Rule of Three says defer that until a third plugin needs it (npm is #1; Phase-7 distroless is #2; the third unknown plugin is when the registry pays for itself). The retriever's keyword-only kwargs are the Open/Closed seam; that is sufficient.
- **`CveAdvisory` shape is the load-bearing read-before-write (Rule 8).** As of 2026-05-24 no HARDENED story explicitly ships `CveAdvisory` — it is referenced abstractly by S5-01/S7-01/arch. Before writing fixtures, read whatever Phase-3/Phase-4 module finally lands `CveAdvisory` (likely `src/codegenie/vuln_index/models.py` extends `VulnerabilityRecord`). Surface a Rule-7 conflict if `advisory.id` is not a `CveId` newtype OR if the multi-affected-package shape disagrees with the singular `advisory.package_id` this story assumes.
- **`--`-to-`_` import resolution (S7-01 AC-FILE).** The plugin directory is `vulnerability-remediation--node--npm` (single hyphens, then double dashes between segments). Python cannot import a module whose path contains hyphens via bare `import`. S7-01 documents the resolution mechanism in `plugins/vulnerability-remediation--node--npm/__init__.py`'s docstring (likely `importlib.util.spec_from_file_location` or an underscored re-export shim `plugins.vulnerability_remediation_node_npm`). This story's tests use the same mechanism — DO NOT introduce a parallel shim.
- **No `RetrieverDeps` aggregate dataclass.** The retriever's 10+ keyword-only args are the established precedent (S5-01 AC-1). Adding two more (`query_builder`, `query_text_builder`) at the `transforms()` factory call site is consistent. A `RetrieverDeps` aggregator would be ceremony with zero behavior; defer to `phase-architect` if the arg count crosses ~14.
- **ADR-0003 fence does not cover `plugins/` (S7-01 Notes line 524).** The AST import-fence test in this story is the **primary** control for the plugin-resident `rag_query_builder.py`, not "defense in depth". Cite ADR-0003 only to note that `plugins/` is outside its scope.
- **`make check` integration — coverage subset note.** The `--cov-fail-under=85` addopts in `pyproject.toml` covers the full suite; running only this story's subset (`pytest tests/unit/plugin/test_rag_query_builder_*.py -v`) will likely falsely fail the coverage gate. Use `--no-cov` for narrow subset runs as documented in CLAUDE.md.
