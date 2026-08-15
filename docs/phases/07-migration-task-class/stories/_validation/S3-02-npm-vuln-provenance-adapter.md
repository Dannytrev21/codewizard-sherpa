# Validation report: S3-02 — `NpmVulnProvenanceAdapter` body + DI kwargs

**Story:** [`../S3-02-npm-vuln-provenance-adapter.md`](../S3-02-npm-vuln-provenance-adapter.md)
**Validator run:** 2026-08-14 (scheduled-task `story-validation-corrector`)
**Verdict:** **HARDENED — BLOCKED status preserved; Implementation outline / ACs / TDD plan rewritten against the landed contract**

## Summary

The story as written prescribed a `RepoContext`-reading, `package-lock.json`-walking adapter with a payload-carrying `AdapterConfidence` sum type and an `AdapterError(id, details=…)` constructor. **None of those contracts landed.** S1-02..S2-04 shipped a strictly narrower Protocol: positional `attribute(cve_id, package_id, image_ref, sbom)` with no `RepoContext`; flat `StrEnum` `AdapterConfidence`; marker-exception `AdapterError`; closed three-name `_DI_KWARGS` vocabulary typed `object | None`.

The validator kept the story's **Goal** (Land `NpmVulnProvenanceAdapter` returning typed variants) unchanged and rewrote everything below the Goal to match the SBOM-walk contract actually shipped. Two of the seven original attempt-log blockers (B — bench cassette absent; F — S3-01 fixture defect) remain genuinely unresolved and are surfaced as pre-execution preconditions the executor must halt on. Blockers A / C–E / G resolved by the rewrite. This is the same pattern the sister-story S3-03 validation applied on 2026-05-23.

## Findings by critic lens

Findings were produced by four parallel critic subagents (Coverage, Test-Quality, Consistency, Design-Patterns). Consolidated + de-duplicated below. Severity: **block** = story cannot execute correctly without the fix; **harden** = story-executes-but-executor-writes-fragile-code without the fix; **nit** = cleanup.

### F1 (Consistency) — `attribute()` signature contradicts landed Protocol [block]

The story's `attribute(self, *, cve_id, package_id, image_ref, sbom, repo_context: RepoContext) -> Provenance` diverges from `src/codegenie/primitives/vuln_provenance/protocols.py:74-80` which is positional `(self, cve_id, package_id, image_ref: ImageRef | None, sbom)`. `assembly.py:167` dispatches positionally: `factory(cls).attribute(cve_id, package_id, image_ref, sbom)`. An adapter with the story-prescribed keyword-only signature would `TypeError` at dispatch.

**Fix:** rewrote AC-6, AC-8, Implementation-outline step 4, and Notes-for-implementer to reference the positional signature. Added AC-Signature with an explicit `inspect.signature` smoke test. Added AC-ImageRef-None to pin the `None` arm.

### F2 (Consistency + Coverage F1 + Test-Quality F2) — Variant field names contradict landed `types.py` [block]

Story referenced non-existent fields on `AppDirect` / `AppTransitive`: `package_id`, `version`, `locked_version`, `location`. Landed shapes (`types.py:190-217`) are `(kind, manifest_path, package, confidence)` for `AppDirect` and `(kind, manifest_path, package, chain: min_length=2, confidence)` for `AppTransitive`. Also: story described `chain` as starting with "the direct dep and ending with the queried package (NOT including the root package itself)" — but the landed docstring pins `min_length=2` (length 1 collapses to `AppDirect`). The story never mentioned the mandatory `confidence: AdapterConfidence` field on each variant.

**Fix:** rewrote all variant ACs (AC-Direct, AC-Transitive, AC-Deep-Nesting, AC-Scoped) with landed field names and Pydantic `min_length=2` semantics. Added AC-Hoisting-Priority to pin the "same package appears direct + transitive" invariant (npm hoisting → direct wins). Added explicit chain-tuple equality assertions (`chain == (PackageId("express"), PackageId("lodash"))`) rather than length-only checks — kills the "always AppDirect with hardcoded chain=(pkg, pkg)" mutant.

### F3 (Consistency + Coverage F6 + Test-Quality F4) — `AdapterConfidence` is a flat StrEnum, not a payload sum [block]

Story AC-9 referenced `AdapterConfidence.High` / `.Degraded(reason=…)` / `.Unavailable(reason=…)`. Landed `AdapterConfidence` (`types.py:100-114`) is a flat `StrEnum` with three members: `HIGH`, `DEGRADED`, `UNAVAILABLE`. The story's payload-carrying constructor syntax simply doesn't compile.

**Fix:** rewrote as AC-Confidence — `confidence()` returns `AdapterConfidence.HIGH` unconditionally (the adapter-class-level confidence used by the dispatch tie-breaker per `protocols.py:92-98`). Per-call confidence rides on each returned variant's `.confidence` field (also `HIGH` for the SBOM-nesting adapter — the classifier is deterministic when it produces a chain). Explicitly rejected the story's `_last_outcome: Optional[Provenance]` caching pattern (Design-Patterns F6, Coverage F10) — it makes `confidence()` call-order dependent and violates functional-core discipline.

### F4 (Consistency + Test-Quality F1) — `AdapterError` is a plain marker class, no `details=` kwarg [block]

Story instantiated `AdapterError("vuln_provenance.adapter_error", details={"error": str(e)})`. Landed `AdapterError` (`errors.py:92-96`) is a plain marker exception subclassing `ProvenanceError` — no `__init__`, no `details` attribute, no WarningId payload. Per its docstring: "Behavior on the exception is composed by the catch site, not embedded on the class."

**Fix:** rewrote Implementation-outline step 4 to use `raise AdapterError(str(e)) from e`. Also revisited the raise trigger: under the landed SBOM-walk (not lockfile-walk) contract, no `json.JSONDecodeError`-style parse failure exists — the classifier "returns None on non-match" approach folds every malformed case into `Unknown(sbom_layer_attribution_absent)`. Kept the raise arm structurally in AC-Fail-Loud but explicitly permitted the executor to drop it if no reachable trigger exists (surface in attempt log; also drop the `"vuln_provenance.adapter_error"` `_WARNING_IDS` entry).

### F5 (Consistency + Design-Patterns F3) — `verifier: SbomVerifier | None` DI kwarg is out-of-contract [block]

Implementation-outline step 6 originally prescribed a `verifier: SbomVerifier | None = None` DI kwarg for defensive degradation against S4-01's `sbom_verifier.py` absence. But `_DI_KWARGS` at `src/codegenie/primitives/vuln_provenance/factory.py:54` is **closed** at `{"sbom_reader", "logger", "image_manifest_cache"}` (ADR-0007 §Decision, §Tradeoffs row 1). Adding a fourth name requires an ADR-0007 amendment. The story never proposed the amendment.

**Fix:** removed the cross-verification prescription entirely. Rewrote Implementation-outline step 6 as an anti-instruction: "S3-02 does NOT attempt cross-verification. Add it uniformly to all adapters when the DI vocabulary is amended in a future post-S4-01 wiring story." Rule 2 + Rule 3 rationale. Also rewrote AC-Init-Positional to allow the adapter to declare a *subset* of `_DI_KWARGS` — the landed shape is `__init__(self, *, logger: object | None = None)` declaring only `logger`.

### F6 (Consistency + Design-Patterns F1) — Adapter `__init__.py` already exists; ADR-0009 row #1 covers `npm_provenance.py` only [harden]

Story AC-1 said "create `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` (new file)". `ls plugins/vulnerability-remediation--node--npm/adapters/` shows `__init__.py` already exists (predates this story — Phase 4 S6-05 sibling `ts_typecheck_signal.py` lives here). ADR-0009 row #1 lists **only** `npm_provenance.py`; a second file would be a fence violation.

**Fix:** deleted AC-1. Rewrote "Files to touch" to remove `adapters/__init__.py`. Added explicit "Files this story does NOT touch" list including `adapters/__init__.py`, `api.py`, `tccm.yaml`, and the S3-01 fixture — to guard against "while I'm here" scope creep.

### F7 (Consistency F7) — ADR-0009 vs High-level-impl.md row-enumeration contradiction [harden — inherited from S3-03]

ADR-0009 rows (canonical): `npm_provenance.py`, `tccm.yaml`, `src/codegenie/__init__.py`, `repo_context.schema.json`, `tccm.py`, `sandbox/client.py`, `sandbox/__init__.py`, `exec/__init__.py`, `pyproject.toml`, `plugins/loader.py`. `api.py` **is not listed**. High-level-impl.md Step 5 (line 157-159): row #8 = `npm_provenance.py`, row #9 = `api.py`, row #10 = `tccm.yaml`. The two lists disagree on `api.py` vs `pyproject.toml`.

This contradiction was surfaced by the S3-03 validation (F2 there). S3-02 itself only creates row #1 (`npm_provenance.py`, present in both lists), so this story is not blocked on the contradiction — but the executor MUST NOT presume `api.py` is allowlisted when landing S3-03. Documented in the Validation notes header.

### F8 (Consistency + Coverage F3) — AC-12 vs Out-of-scope contradiction (Blocker G) [block]

Story AC-12 demanded S3-02 flip S3-01's three integration scenarios GREEN and remove the `xfail(strict=True)` markers. Out-of-scope deferred `api.py` wiring to S3-03. With no `api.py` import, the decorator side-effect never fires via the canonical `load_plugins(...)`; `_REGISTRY[(APP, NPM)]` is empty; `assemble_provenance` returns `Unknown(no_adapter_resolved)`; removing `xfail` markers converts three passing-xfail tests into three hard CI failures. S3-02 alone cannot satisfy AC-12.

**Fix:** rewrote AC-12 as AC-S3-01-Deferred — S3-02 does NOT touch the integration test file. The `xfail` removal is S3-03's job. Unit tests exercise the adapter class directly via the `provenance_registry_reset` fixture (matching the pattern in `tests/unit/primitives/vuln_provenance/test_assembly.py`).

### F9 (Consistency + Coverage F4) — `bench/vuln-remediation/` cassette does not exist (Blocker B) [block]

Story AC-14 asserted "byte-identical against `bench/vuln-remediation/` cassette replay (ε ≤ $0.01)" as "the load-bearing assertion". `ls bench/` returns "No such file or directory". Same contract-against-nonexistent-artifact as F8.

**Fix:** rewrote as AC-Full-Check — if the cassette exists at execution time, ε ≤ $0.01 asserted; otherwise the assertion is out of scope for this story and gets documented in the attempt log. Cassette creation is a Phase 3 obligation; S3-02 does NOT synthesize a cassette to satisfy the AC. Recorded in Out-of-scope. AC-Status added: story stays `BLOCKED-PARTIAL` if the cassette (or the S3-01 fixture) persists at execution time.

### F10 (Coverage F2) — Missing SBOM path-nesting edge cases [block]

The story's original ACs referenced npm dep-tree walking without covering: scoped packages (`node_modules/@types/lodash/…` — must count as one hop, not two), deep nesting depth ≥ 3, path shapes outside `node_modules/` (`dist/bundle.js`, `src/index.js`), empty `locations` on a matching artifact, and npm hoisting (same package at both direct and transitive locations).

**Fix:** added AC-Deep-Nesting (parametrized over depths 2, 3, 4), AC-Scoped (direct + transitive), AC-Non-NodeModules-Path (parametrized over three shapes), AC-Absent-No-Locations, AC-Hoisting-Priority. Each AC is a full-tuple `==` assertion, not a length-only or type-only check. The Implementation-outline classifier regex (`_NODE_MODULES_PATH_RE`) explicitly handles scoped packages via the `@[^/]+/[^/]+` alternate in each hop.

### F11 (Test-Quality F3 + Coverage F10) — No test forbids filesystem reads inside `attribute()` [block]

Every original AC gated I/O at `__init__` only. A mutant that ignores `sbom` and opens a real `package-lock.json` from `cwd` would pass the entire unit suite (the story literally prescribed this behavior via Implementation-outline step 4's `self._read_lockfile(repo_context)`).

**Fix:** added AC-NoIO-Attribute — monkeypatch `Path.read_text`, `Path.open`, and `builtins.open` to raise, invoke `attribute()`, assert no raise. This is the mutation-killer for the entire contract-divergence risk surface.

### F12 (Test-Quality F6) — Red-state proof is weak [harden]

The story's original TDD "Red" phase produced `ModuleNotFoundError`, which also passes on a typo'd test path or a checked-in stub returning `Unknown` for everything.

**Fix:** rewrote TDD "Red" to require ≈ 18 substantive `AssertionError` / `NotImplementedError` failures — start with a stub module (`raise NotImplementedError` in `attribute()` and `confidence()`), write all 18 AC tests first, red phase produces concrete failures per AC. Committed as the red baseline.

### F13 (Test-Quality F5) — DI-storage AC is a tautology [harden]

Story AC-6 said "test inspects `self._sbom_reader is sbom_reader`". Under the landed contract, `sbom_reader` is a dead kwarg (SBOM arrives at call time). And the identity-check would pass on any stub that stores + never uses the reference — no signal.

**Fix:** dropped the DI-storage AC. Replaced with AC-Idempotent — three consecutive `attribute()` calls with byte-identical inputs return `==`-equal `Provenance`. Kills any per-call hidden-state cache or first-call mutation. Also kills the `_last_outcome` field pattern the story previously proposed for `confidence()`.

### F14 (Test-Quality F7) — No registry-isolation fixture named [harden]

Repeated module imports re-register into `_REGISTRY[(APP, NPM)]`; the S3-01 integration test's plugin loader also mutates this state. The story listed no fixture, so tests would leak state across module boundaries.

**Fix:** added AC-Registry-Fixture — every unit test in the module uses the `provenance_registry_reset` autouse fixture from `tests/unit/primitives/vuln_provenance/conftest.py`. No unit test invokes `load_plugins(...)`. No unit test monkeypatches `_REGISTRY` directly.

### F15 (Test-Quality F10) — Test names encode behavior, not intent (Rule 9) [nit]

Original AC bullets like "Direct-dep happy path → AppDirect" describe *what*, not *why*.

**Fix:** rewrote TDD-plan test names to encode intent: `test_top_level_node_modules_nesting_classifies_as_direct`, `test_hoisted_package_prefers_direct_over_transitive`, `test_scoped_package_slug_counts_as_one_hop`, etc.

### F16 (Design-Patterns F2 + F4 + F8) — Anti-instructions to preserve Rule 2 simplicity [harden, notes-only]

Story's original refactor step said "extract `_lockfile_walk.py` if `npm_provenance.py` exceeds ~150 LOC" and left cross-verification / DI-registry / base-class patterns unaddressed. The design-patterns critic surfaced multiple pre-emptive-abstraction traps.

**Fix:** rewrote Refactor step + added Notes-for-implementer paragraphs explicitly forbidding:
1. Marker catalog `_NPM_PATH_CLASSIFIER_RULES` (one grammar → one regex; deferred to Yarn PnP / pnpm rule-of-three).
2. Sibling module `_classify_sbom_locations.py` extraction (single-consumer; renaming problem for S4-02/S4-03).
3. `AbstractVulnProvenanceAdapter` base class (Protocol IS the seam; S4-02/S4-03 share zero classification code).
4. `verifier: SbomVerifier | None` DI kwarg (out-of-contract per `_DI_KWARGS`).
5. `_last_outcome` state cache in `confidence()` (violates functional-core discipline).
6. `NpmPackageChain` newtype (Pydantic `Field(min_length=2)` on `AppTransitive.chain` is already the smart constructor).
7. `NodeModulesPath` newtype (internal parse target, not a domain identity that crosses seams).

Each anti-instruction lands as a Notes-for-implementer paragraph, NOT as an AC (pattern advice belongs in Notes per validator skill rules; ACs must be observable).

### F17 (Design-Patterns F6) — Functional core seam is cleaner under SBOM contract than story admitted [harden]

Original Implementation-outline step 4 mixed impure `_read_lockfile(repo_context)` with pure chain-walking. Under the landed contract, `attribute()` receives `sbom: SyftSbom` as a parameter — the entire adapter body shrinks to a list comprehension + a pure classifier call + three variant constructors. ~30 LOC.

**Fix:** rewrote Implementation-outline step 4 with concrete code showing the ≤ 30-LOC body. Called out the "adapter is ~100 LOC total" target in the Green phase of the TDD plan.

### F18 (Design-Patterns F7 + Coverage F11) — `_WARNING_IDS` enumeration expanded [harden]

Story pinned only `{"vuln_provenance.adapter_error"}` — tied to the (non-existent) lockfile-parse failure mode. Under the SBOM contract, realistic additions: `vuln_provenance.sbom_missing_locations` (matched artifact had no locations), `vuln_provenance.node_modules_path_malformed` (classifier rejected the path shape).

**Fix:** expanded `_WARNING_IDS` in AC-WarningIds to `frozenset({"vuln_provenance.adapter_error", "vuln_provenance.sbom_missing_locations", "vuln_provenance.node_modules_path_malformed"})`. Permitted the executor to drop `"vuln_provenance.adapter_error"` if no reachable trigger exists (see F4).

## Findings NOT made (and why)

- **No new abstraction introduced pre-emptively.** Per Rule 2 + the design-patterns critic (F1, F4, F8), the classifier, base class, DI verifier registry, and helper module all stay inline. The extension seams are Protocol + registry + future ADR amendments — none of them are code S3-02 writes.
- **No property-based test in this story.** S4-04 owns SBOM-tampering property tests; the classifier's inverse invariant (chain length = 1 + count("/node_modules/") in the matched substring) is recorded as a follow-up hook in the TDD plan, not added here (surgical-changes / Rule 3).
- **No re-typing of the Goal.** The Goal ("Land the first `VulnProvenanceAdapter` returning typed variants; register on module import") is sound. The validator's job is to align the how (implementation outline + ACs + TDD plan), not rewrite the intent.
- **No unilateral fix to the S3-01 fixture defect.** Blocker F requires an S3-01 owner's judgment call; S3-02 explicitly stops rather than editing across story boundaries.
- **No unilateral creation of the `bench/vuln-remediation/` cassette.** Blocker B is a Phase 3 obligation; S3-02 does not synthesize.
- **No ADR amendment proposed here.** The `_DI_KWARGS` widening for cross-verification is a future story's amendment; the ADR-0009 vs High-level-impl.md contradiction is documented but the resolution is out-of-scope for a validator run (belongs to a `phase-architect` amendment pass).

## Recommendations to the user (out-of-scope for this validation)

1. **Fix Blocker B — synthesize `bench/vuln-remediation/`.** This is a Phase 3 obligation and it also unblocks S3-03's AC-6 (cost-ledger byte-equality) and the entire Phase 7 Step 3 done-criterion #3. Assign to a Phase 3 owner.
2. **Fix Blocker F — restructure `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json`.** Move `lodash` under `node_modules/express/node_modules/`; repoint the S3-01 direct test at `express`. This unblocks the integration-suite handoff for S3-02 + S3-03 both. Assign to an S3-01 owner or a Phase 7 owner.
3. **Amend ADR-0009 (or High-level-impl.md) to reconcile the 10-row byte-edit allowlist contradiction.** Same recommendation as the S3-03 validation. Blocks the executor's `api.py` byte-edit in S3-03.
4. **Consider a future ADR-0007 amendment widening `_DI_KWARGS` for `sbom_verifier`.** After S4-01 lands, cross-verification would benefit from uniform DI-level access to the verifier — but the amendment should be a deliberate, phase-level decision, not per-adapter defensive workaround.

## What "good" looks like for this story post-edit

The story now (when its two remaining blockers clear) gives the executor:

- 22 acceptance criteria, each individually verifiable via a concrete `pytest` assertion.
- A ~100-LOC target adapter with a ~20-LOC pure classifier + a ~30-LOC `attribute()` shell.
- 18 substantive TDD-red-phase tests, each intent-named (Rule 9) and parametrized where the mutation surface is wide.
- Explicit filesystem-I/O guardrails inside `attribute()` (AC-NoIO-Attribute — the mutation-killer for the entire contract-divergence risk).
- Full-tuple variant equality assertions (kills "always AppDirect / always chain=(x,x)" mutants).
- Registry-isolation via the established `provenance_registry_reset` fixture.
- Explicit anti-instructions in Notes-for-implementer forbidding seven pre-emptive-abstraction traps.
- Explicit precondition step that STOPS the executor cold if Blocker B or Blocker F persists — no silent workaround, no synthesized cassette, no cross-story fixture edit.

## Mark of completion

The story file has been edited in place. This validation report has been written. The story header now carries a `**Validator status:** HARDENED (2026-08-14)` line linking back here. BLOCKED status is preserved for Blockers B + F; the header BLOCKED block has been rewritten to enumerate only the remaining structural blockers (A / C–E / G resolved by the rewrite).
