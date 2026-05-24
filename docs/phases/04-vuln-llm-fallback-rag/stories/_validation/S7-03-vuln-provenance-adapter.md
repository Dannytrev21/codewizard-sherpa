# Validation report — S7-03 `NpmVulnProvenanceAdapter` (Phase-4 plugin adapter)

**Date:** 2026-05-24
**Validator:** `phase-story-validator` (autonomous, scheduled run)
**Story file:** `docs/phases/04-vuln-llm-fallback-rag/stories/S7-03-vuln-provenance-adapter.md`
**Verdict:** **HARDENED with upstream BLOCKED status** — significant edits applied; ready for `phase-story-executor` only after upstream blockers clear (plugin scaffold, Phase 3 S7-05 pure helper).

## Summary

S7-03's intent is sound: ship the NPM `VulnProvenanceAdapter` Phase 4's `ProvenanceGate` (S2-01) classifies through. The original draft was not executor-ready because its entire mental model contradicted the shipped primitive and the **actual** Phase 3 deliverable:

1. The draft assumed a Phase-3 `NpmVulnProvenanceAdapter` **class** exists to generalize from. It does not. Phase 3 S7-05 ships a pure `is_app_layer_lookup` helper plus `VerifyCveInAppLayerNode` (a `SubgraphNode`), **not** an adapter class. The actual `NpmVulnProvenanceAdapter` class is owned by **Phase 7 S3-02** (currently BLOCKED on plugin scaffold).
2. The draft prescribed `classify(advisory: CveAdvisory, repo_ctx: RepoContext) -> Provenance` as the adapter signature. The **shipped** `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`) declares `attribute(cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance` and `confidence() -> AdapterConfidence`. `CveAdvisory` and `RepoContext` are not importable types.
3. The draft imported `Provenance` variants from `codegenie.fallback.types` — that module does not exist. The variants live at `codegenie.primitives.vuln_provenance.types`, **and the discriminator values are lower-case** (`"app_direct"`, `"app_transitive"`, …), not PascalCase. S2-01 already pinned this in its 2026-05-21 validation.
4. The draft's "Surgical per Global Rule 3" framing inverts the right discipline. CLAUDE.md's load-bearing commitment is **"Extension by addition — no silent edits."** Phase 3 owns the pure helper; Phase 4 ships a **new** adapter file that **composes** the helper. There is no Phase-3 file to "generalize"; there is only an additive new adapter under the plugin tree.
5. The draft's `is_app_layer(advisory, repo_ctx) -> bool` wrapper has the wrong shape and would shadow S2-01's already-shipped `is_app_layer(provenance) -> bool` predicate.
6. Upstream blockers: (a) the plugin tree (`plugins/vulnerability-remediation--node--npm/`) does not exist; (b) Phase 3 S7-05's pure helper has not shipped; (c) Phase 7 S3-02 (the canonical adapter story) is BLOCKED for the same reasons.

All blockers are fixable in place at the story level; the upstream code blockers are flagged but not resolved by this validation. Once upstream lands, the hardened ACs below give the executor a precise, type-correct contract.

## Context brief (Stage 1)

- **Story snapshot:** Ship the NPM `VulnProvenanceAdapter` so `ProvenanceGate` (S2-01) returns full seven-variant `Provenance` and Phase 4 emits `Refused(PROVENANCE_NOT_APP_LAYER)` for `{BaseImage, RuntimeBundled, Unknown}` deterministically.
- **Phase exit criteria implicated:** G7 (zero LLM tokens spent on non-app-layer CVEs) — proven by `test_phase4_provenance_short_circuits.py` (S7-06's companion test). This story is the gate's **classifier** dependency.
- **Authoritative sources read:**
  - `src/codegenie/primitives/vuln_provenance/types.py` — the seven-variant `Provenance` discriminated union with lower-case `kind`.
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — `VulnProvenanceAdapter` Protocol (`attribute`, `confidence` — **not** `classify`).
  - `src/codegenie/primitives/vuln_provenance/errors.py` — `ProvenanceError`, `AdapterError`.
  - `src/codegenie/primitives/vuln_provenance/registry.py` — `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` decorator that stores classes (Phase 7 ADR-0007).
  - `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S2-01-provenance-gate-tier-zero.md` — the precedent that resolved the same primitive/signature drift; this report follows the same pattern.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/S2-01-provenance-gate-tier-zero.md` — `ProvenanceClassifier` facade Protocol that S7-03's adapter must satisfy (`classify(cve_id, package_id, image_ref, sbom) -> Provenance`).
  - `docs/phases/04-vuln-llm-fallback-rag/ADRs/0012-provenance-gate-explicit-tier-zero.md` — tier-0 commitment and `_APP_LAYER_PROVENANCE_KINDS` seam.
  - `docs/phases/04-vuln-llm-fallback-rag/High-level-impl.md §Step 7` — names this file as the small additive Phase-3 generalisation.
  - `docs/phases/03-vuln-deterministic-recipe/stories/S7-05-npm-app-layer-precheck.md` — the actual Phase 3 deliverable: a `NotApplicableReason` Literal member, a pure lookup helper, and `VerifyCveInAppLayerNode`; **not** an adapter class. The story explicitly states it "seeds the adapter shape Phase 7 inherits."
  - `docs/phases/07-migration-task-class/stories/S3-02-npm-vuln-provenance-adapter.md` — Phase 7's canonical adapter story (BLOCKED). Shows the same Protocol shape (`attribute(...)`), the same `@register_provenance_adapter` decorator, the same plugin file path (`adapters/npm_provenance.py`).
  - `docs/phases/07-migration-task-class/stories/_attempts/S3-02-npm-vuln-provenance-adapter.md` — diagnoses the same primitive/signature drift this validation surfaces.

## Stage 2 — four critic synthesis

### Coverage critic (5 block, 6 harden, 1 nit)

- **CF1 (block) — AC-1 prescribes a non-existent method.** `classify(advisory, repo_ctx) -> Provenance` is not a `VulnProvenanceAdapter` method. The Protocol declares `attribute(cve_id, package_id, image_ref, sbom)` and `confidence()`. ACs must align with the shipped Protocol.
- **CF2 (block) — AC-2 wrapper signature contradicts S2-01.** The "thin `is_app_layer(advisory, repo_ctx) -> bool` wrapper" wraps the wrong inputs. S2-01 already shipped `is_app_layer(provenance: Provenance) -> bool`. Two functions with the same name and different signatures is a code smell. Removed; the adapter is registered, the gate is the consumer, no wrapper is needed.
- **CF3 (block) — AC-2 hides whether this story builds the adapter or generalises one.** No Phase-3 adapter exists; the only choice is "build it new." Rewritten as a single, explicit AC: create new file, register via decorator.
- **CF4 (block) — AC-3 over-promises classification.** `BaseImage`, `RuntimeBundled`, `Both` variants require the **base-image adapter** (Phase 7) to participate. Phase 4 alone cannot honestly classify these. Reframed: Phase 4 NPM adapter resolves app-layer evidence; absent base-image evidence collapses to `Unknown(reason="no_adapter_resolved")`, per `UnknownReason` taxonomy (`types.py:122`). Phase 7's base-image adapter and `assemble_provenance` orchestration produce `BaseImage`/`RuntimeBundled`/`Both`.
- **CF5 (block) — AC-5 demands integration fixtures the story has no place to put.** Without the plugin tree existing, `tests/fixtures/provenance/` integration cannot run. Rewritten as a precondition (upstream blocker UB-1).
- **CF6 (harden) — `confidence()` AC missing.** The Protocol requires both `attribute` and `confidence`. Added AC-CONFIDENCE.
- **CF7 (harden) — Degenerate inputs unspecified.** Missing package-lock, multi-package CVE, scoped name — none mentioned. Added AC-DEGENERATE and AC-MULTIPKG.
- **CF8 (harden) — No fence test for forbidden-patterns / Any.** Added AC-IMPORT-FENCE and AC-NO-ANY.
- **CF9 (harden) — `_WARNING_IDS` discipline absent.** Phase 7 S3-02 has this (CLAUDE.md convention). Added AC-WARNING-IDS.
- **CF10 (harden) — Composition with `ProvenanceGate` not tested.** Added AC-GATE-COMPOSE.
- **CF11 (harden) — Determinism AC was buried in a parametrize.** Promoted to a top-level AC with a digest pin.
- **CF12 (nit) — Audit event emission ownership.** Adapter does not emit; gate does. Surfaced in Notes.

### Test-Quality critic (4 block, 5 harden, 2 nit)

- **TF1 (block) — `from codegenie.fallback.types import …` ModuleNotFoundError.** Import path is wrong (variants live under `codegenie.primitives.vuln_provenance`). The TDD plan would fail at collection time before any test runs. Rewrote imports.
- **TF2 (block) — `isinstance(result, AppDirect)` is brittle.** Acceptable but the table parametrize over PascalCase classes inside a `Literal`-discriminated union will produce confusing failure messages when the shape evolves (e.g., a future `Both` arm collapses to a different class). Replaced with `assert result.kind == "app_direct"` over real Pydantic instances — robust to refactor, matches the S2-01 precedent.
- **TF3 (block) — Mocked `RepoContext` and `CveAdvisory` are vapor.** Tests build dicts pretending to be these types; mypy --strict would reject. Replaced with real `CveId`/`PackageId`/`ImageRef`/`SyftSbom` builders mirroring `tests/unit/fallback/test_provenance_gate.py` from S2-01.
- **TF4 (block) — Hypothesis property is too weak to discriminate a wrong implementation.** "Returns one of seven variants, no exception" passes a function that always returns `Unknown`. Added a **second** Hypothesis property and a **metamorphic** test (see TF5/TF6).
- **TF5 (harden) — Add monotonicity metamorphic test.** Adding `package_id` to the app-layer evidence with everything else unchanged must flip `Unknown → AppDirect | AppTransitive`, never the reverse. Encoded as a strict monotonic property over a controlled `SyftSbom` builder.
- **TF6 (harden) — Add idempotence test under cassette-style replay.** Calling `attribute(...)` twice with the same inputs returns equal `Provenance`. The pre-existing "deterministic across calls" AC is promoted to an independent test.
- **TF7 (harden) — Test for `@register_provenance_adapter` side effect missing.** Phase 7 S3-02's precedent (AC: `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter`) is required. Added.
- **TF8 (harden) — Mutation thinking: tests should fail against a "stub that always returns `Unknown`."** Added explicit "returns `AppDirect` for the express-major-bump fixture" positive assertion (not just isinstance) and the digest-pin determinism test (catches a hash-anything stub).
- **TF9 (harden) — No I/O-at-construction test.** Mirrors Phase 7 S3-02 AC. Added.
- **TF10 (nit) — `confidence()` table missing.** Added.
- **TF11 (nit) — `_WARNING_IDS` regex validation test missing.** Added per Phase 7 S3-02 precedent.

### Consistency critic (5 block, 3 harden, 1 nit)

Reproduces and reinforces CF1–CF5 from Coverage; adds:

- **CC1 (block) — `Provenance` variants do not live at `codegenie.fallback.types`.** They live at `codegenie.primitives.vuln_provenance.types`. The story's imports throughout (AC text, TDD plan, fixture file) are wrong. Fixed.
- **CC2 (block) — `_APP_LAYER_PROVENANCE_KINDS` discriminator is lower-case.** S2-01 pinned this (`frozenset({"app_direct", "app_transitive", "app_vendored", "both"})`). The story's "result in `{AppDirect, AppTransitive, AppVendored, Both}`" PascalCase-class membership check would silently pass / fail in confusing ways depending on object identity. Replaced by `result.kind in _APP_LAYER_PROVENANCE_KINDS`.
- **CC3 (block) — `NpmVulnProvenanceAdapter` ownership conflict with Phase 7 S3-02.** S2-01 explicitly defers "the real NPM provenance adapter generalization or plugin registration" to S7-03. Phase 7 S3-02's goal text claims the same surface. The story now explicitly states: **S7-03 ships the Phase-4-scoped subset** (`AppDirect` / `AppTransitive` / `AppVendored` / `Unknown` only); Phase 7 S3-02 **widens** it to all seven variants when the base-image adapter chain lands. The class is the same; the implementation grows additively. Surfaced as a cross-phase coordination note + AC-PHASE7-SEAM.
- **CC4 (harden) — Plugin file naming.** Phase 7 S3-02 places the file at `adapters/npm_provenance.py`. The Phase-4 High-level-impl says `adapters/vuln_provenance.py`. **`npm_provenance.py` wins** — it's the more-specific name, and it matches the "one provenance adapter per ecosystem" pattern. (Future `pip_provenance.py`, `gem_provenance.py`, etc. would sit alongside.) Surfaced as a Phase-4 amendment note.
- **CC5 (harden) — `applies_to_tasks` / `applies_to_languages` framing.** Phase 7 ADR-0005 says the adapter lives under the plugin directory; the plugin's `applies_to` is what selects the adapter. The story should not introduce a separate selector at the adapter level. Removed any implication.
- **CC6 (harden) — `tests/fence/test_kernel_frozen.py` allow-list.** AC-6 in the draft asserts no edits to `src/codegenie/{probes,coordinator,cache,output,schema}/`. That's the right list, but it omits `src/codegenie/plugins/protocols.py` (the load-bearing kernel file the Phase 4 path-scoped fence specifically protects per ADR-0003). Tightened.
- **CC7 (nit) — Citation of Global Rule 3.** Removed the AC-7 requirement to cite Global Rule 3 in the docstring. The rule that **actually applies** is the CLAUDE.md "Extension by addition" commitment — this is a new file, not an edit. The docstring should cite that instead.

### Design-Patterns critic (3 block, 4 harden, 2 nit)

- **DF1 (block) — "Surgical per Global Rule 3" frames the work as an edit; the work is additive.** Rule 3 governs scope-creep on existing files; this story creates new files. The right principle is "Extension by addition — no silent edits" (CLAUDE.md load-bearing commitment). Reframed throughout. Adapter is **new**; Phase 3 helper is consumed via import only, never edited.
- **DF2 (block) — Functional core / imperative shell missing from outline.** Phase 7 S3-02 and Phase 3 S7-05 both prescribe a **pure helper** (`_walk_lockfile_chain`, `is_app_layer_lookup`) that the adapter's `attribute(...)` impure method delegates to. The draft's `match`-over-variants design pushes all the logic into the impure method. Added AC-PURE-HELPER + reflective tests on it.
- **DF3 (block) — Dependency Inversion: constructor signature unspecified.** The Protocol-on-class pattern (Phase 7 ADR-0007) requires **DI via factory** with closed kwarg vocabulary `{sbom_reader, logger, image_manifest_cache}`. The draft is silent on construction; an implementer could plumb file paths or globals. Added AC-DI-KWARGS.
- **DF4 (harden) — Open/Closed: composing the Phase 3 helper, not branching.** The adapter must call the **pure helper imported from Phase 3** (`from plugins.vulnerability_remediation_node_npm.subgraph.verify_app_layer import is_app_layer_lookup` — or whatever symbol Phase 3 S7-05 exports). It must not re-implement the lockfile walk. Added AC-COMPOSE.
- **DF5 (harden) — Strategy / Adapter pattern naming.** The class is the **Adapter** in Port-and-Adapter (Phase 7 ADR-0007 says so explicitly). Surfaced in Notes for the implementer with a one-line callout that the Phase-7 base-image adapter is a **second Adapter** behind the same Port; both register via the same decorator and `assemble_provenance` (Phase 7 S2-04) dispatches.
- **DF6 (harden) — Registry pattern: decorator-based.** Made explicit (mirrors S5-01 `recipe_registry` + Phase 7 S2-01 `register_provenance_adapter`).
- **DF7 (harden) — Sum-type discipline at the boundary.** `Provenance` is a discriminated union; the adapter MUST return one of the seven concrete variants, never a `Provenance | None` or `Provenance | str`. The `attribute(...)` return annotation pins this; Pydantic + `mypy --strict` enforce.
- **DF8 (nit) — Newtype identifiers.** All inputs (`CveId`, `PackageId`, `ImageRef`) are newtypes from `codegenie.types.identifiers`. Raw `str` is forbidden at the API boundary. Story already implies this; called out in Notes.
- **DF9 (nit) — `_WARNING_IDS: Final[frozenset[str]]` is the codebase convention.** Phase 7 S3-02 has it; this story should match. Added.

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every issue resolved by reading in-repo source files, the production primitive contract, and prior validation reports (S2-01, Phase 7 S3-02, Phase 7 S3-03).

## Stage 4 — Synthesis

### Conflict resolutions

- **Phase 4 vs Phase 7 ownership of `NpmVulnProvenanceAdapter`.** S2-01 defers the adapter to S7-03; Phase 7 S3-02 also claims it. Resolved by **additive layering**: S7-03 ships the **Phase-4-scoped subset** (`AppDirect`/`AppTransitive`/`AppVendored`/`Unknown` outcomes), Phase 7 S3-02 widens the same class to all seven variants when the base-image adapter chain lands. Both stories touch the same file additively; no `Both` arm exists in the Phase-4 subset (base-image evidence collapses to `Unknown`).
- **`classify(advisory, repo_ctx)` shorthand vs shipped `attribute(...)` Protocol.** Same resolution S2-01 applied: the shipped Protocol wins. The Phase-4 `ProvenanceClassifier` facade Protocol (S2-01) preserves a `classify(...)` name for the gate's local taste but routes to the actual adapter's `attribute(...)` method. The adapter implements `attribute`; the wiring composes them.
- **File name `vuln_provenance.py` (Phase-4 High-level-impl) vs `npm_provenance.py` (Phase 7 S3-02).** Resolved in favor of `npm_provenance.py` — more specific, ecosystem-scoped, extension-friendly for future `pip_provenance.py` etc. The Phase-4 High-level-impl text is informally inaccurate (it precedes the Phase 7 S3-02 design); the canonical file path follows Phase 7's plugin layout. Surfaced as a one-line Phase-4 amendment note.

### Upstream blockers (must clear before this story is Ready)

1. **UB-1 — Plugin tree does not exist.** `plugins/vulnerability-remediation--node--npm/` is empty (only `plugins/__init__.py`, `plugins/PLUGINS.lock`, `plugins/PLUGINS.lock.README.md`). Phase 3 must implement the plugin scaffold before any plugin-side adapter can land. (Same blocker as Phase 7 S3-02, S3-03.)
2. **UB-2 — Phase 3 S7-05's pure helper not shipped.** This story's adapter is supposed to compose against the `is_app_layer_lookup` pure function that Phase 3 S7-05 ships. Phase 3 S7-05 is HARDENED but not GREEN. Without the helper, the adapter must re-derive the lockfile walk (a non-starter under Phase 7 ADR-0009 "do not edit Phase 3").
3. **UB-3 — Phase 4 S2-01 (`ProvenanceGate`) not yet GREEN.** The hardened validation report exists; the executor has not landed the code. Without `ProvenanceGate` + `ProvenanceClassifier`, the adapter has no consumer.
4. **UB-4 — Phase 7 S3-02 cross-coordination.** If Phase 7 S3-02 ships first (post-blocker resolution), S7-03 is a near-no-op (Phase 7 S3-02's adapter already satisfies Phase 4 needs). If S7-03 ships first, Phase 7 S3-02 widens it. Story execution order is a project decision; surface in `_attempts/S7-03-*.md` at execute time.

### Edits applied to the story file

1. **Header** — `Status: Ready` → `Status: HARDENED (BLOCKED on upstream)`; added Validation notes block citing this report.
2. **Context** — Rewritten to reflect Phase 3 deliverable reality (pure helper, not adapter class), the shipped Protocol (`attribute(...)`), and the additive-by-design relationship to Phase 7 S3-02.
3. **References** — Added `src/codegenie/primitives/vuln_provenance/{types,protocols,errors,registry,assembly}.py`, Phase 7 S3-02 + S3-03, S2-01 validation report. Removed broken references to `src/codegenie/fallback/types.py`.
4. **Goal** — Rewritten: ship `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` containing `NpmVulnProvenanceAdapter` (`@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`), Protocol shape (`attribute(cve_id, package_id, image_ref, sbom) -> Provenance` + `confidence() -> AdapterConfidence`), Phase-4-scoped variant production (`AppDirect`/`AppTransitive`/`AppVendored`/`Unknown`).
5. **Acceptance criteria** — Rewritten entirely against shipped contracts. 16 ACs covering: file location, decorator registration, Protocol shape, DI kwargs vocabulary, no-I/O-at-construction, `attribute(...)` variant production, `Unknown(reason)` discipline, `confidence()` return semantics, pure helper composition, multi-package logical-OR + scoped-name normalisation, determinism, `_WARNING_IDS`, forbidden-patterns, Phase-7-seam (no `Both` arm), event-emission ownership, full `make check` clean.
6. **Implementation outline** — Rewritten as additive: create new files, compose Phase 3 S7-05's pure helper, decorate, ensure DI kwargs match Phase 7 S3-02's vocabulary so the file is widening-ready.
7. **TDD plan** — Rewritten: real `Provenance` variant fixtures from `codegenie.primitives.vuln_provenance`, lower-case `kind` assertions, hand-rolled DI fakes, registry assertion, no-I/O-at-construction test, metamorphic monotonicity property, idempotence property, `_WARNING_IDS` regex check, AST import fence, `mypy --strict` smoke.
8. **Files to touch** — Updated to canonical Phase 7 layout (`adapters/__init__.py`, `adapters/npm_provenance.py`, `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py`, `tests/fixtures/provenance/`).
9. **Out of scope** — Expanded: base-image classification (Phase 7 base-image adapter), `Both` variant production (requires `assemble_provenance`), widening from Phase-4 subset to full seven variants (Phase 7 S3-02), `is_app_layer` wrapper at the adapter level (S2-01 owns the predicate over `Provenance`).
10. **Notes for the implementer** — Expanded: additive-not-edit framing, Phase-7-widening seam, lower-case discriminator contract, composition-not-reimplementation of the lockfile walk, DI factory vocabulary, fail-loud `AdapterError` discipline.

## Verdict rationale

**HARDENED with upstream BLOCKED status.** The story's goal (ship the NPM provenance adapter) is valid and traces cleanly to ADR-0012 / G7 / production ADR-0038. The original draft was stale across every dimension — wrong module paths, wrong Protocol signature, wrong discriminator casing, wrong framing of "edit vs additive," wrong ownership claim vs Phase 7 S3-02. The blockers were systematic stale-codebase assumptions, not a wrong goal. After hardening:

- Every AC is verifiable against the shipped Protocol.
- The tests would fail against the obvious wrong implementations (PascalCase-string adapter, missing decorator, I/O-in-constructor, always-returns-Unknown stub, non-deterministic walk).
- The implementation path follows Phase 7 ADR-0007 (port/adapter), Phase 7 ADR-0009 (additive file), and CLAUDE.md "Extension by addition."
- Phase-4 ↔ Phase-7 ownership is explicit and additive (no double-implementation, no surprise widening).

**Why not RESCUE.** The goal contradicts no ADR or the phase arch — it is the canonical Phase-4 plugin-side seam ADR-0012 names. The ACs traced to the goal under the wrong contract; rewritten against the shipped contract, they trace cleanly. RESCUE would be appropriate only if the goal itself were wrong (e.g., trying to put the adapter under `src/codegenie/` instead of `plugins/`, which the draft did not do).

## Recommended next step

1. Resolve upstream blockers UB-1, UB-2, UB-3 in order. UB-4 is a sequencing question, not a code blocker.
2. Then `phase-story-executor` can implement S7-03 starting from `tests/unit/fallback/test_provenance_gate.py` (S2-01's fixtures), Phase 7 S3-02's adapter skeleton (mirror its `__init__` / `attribute` shape), and Phase 3 S7-05's pure helper. The Phase-4 subset is small — most of the line count is fixtures.
