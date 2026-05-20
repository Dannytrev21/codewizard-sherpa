# Validation report: S7-05 — npm plugin app-layer precheck (refuse-mode for non-app-layer CVEs)

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-05 inserts a `verify_cve_in_app_layer` node at the head of the npm vuln-remediation plugin's
subgraph: if a CVE's affected npm package is absent from the resolved `package-lock.json` dep
graph, the node short-circuits with a new `NotApplicableReason` value `CVE_NOT_IN_APP_LAYER` plus
an evidence model; otherwise it advances. It is the Phase-3 precursor to Phase 7's `vuln.provenance`
adapter.

The **goal is sound** — it traces cleanly to ADR-0038 §Decision §Phase-3-scope and to ADR-0003's
evidence-bearing-outcome rule, and every critic endorsed it. The weakness was entirely in the ACs,
implementation outline, and TDD plan: the story was drafted against an **imagined API surface** that
diverges from what the sibling stories actually shipped. Four parallel critics surfaced 45 findings
(14 of them block-tier). Every block finding had a concrete, determined in-place fix — none required
rewriting the goal — so the verdict is HARDENED, not RESCUE.

The hardening pinned the story to the shipped contracts (`NotApplicableReason` is a `typing.Literal`
not an enum; `RemediationNotApplicable` is the real class and has no `evidence` field;
`SubgraphState` carries `cve: CveId` + `bundle` and no `cve_record`/`npm_dep_graph`), corrected
every fabricated file path, made the additive model + event-taxonomy + contract-snapshot widenings
explicit, added ACs for the degenerate-input / multi-package / determinism / pure-helper gaps, and
made the test fixtures story-local to remove a forward dependency on S8-01.

## Findings by critic

### Coverage critic

- **F1 (block)** — AC-2 reads `state.cve_record` + `state.npm_dep_graph`; neither exists on
  `SubgraphState` (S6-03 AC-9: `workflow_id, cve: CveId, resolution, bundle, recipe_outcome,
  transform, trust_outcome, branch`). `state.cve` is a bare `CveId`, not a record with
  `affected.packages`. The node has no parsed CVE to read.
- **F2 (block)** — Implementation outline step 3 references `read_raw_slices(raw_dir(snapshot.root))`
  with no `snapshot` in scope, and simultaneously prescribes `state.bundle.slices[...]` — two
  contradictory data-access paths.
- **F3 (block)** — AC-4 requires `AppLayerAbsenceEvidence` in `outcome.evidence`, but
  `RemediationNotApplicable` (`outcomes.py:284-292`, `frozen, extra="forbid"`) has only `kind` +
  `reason`. The additive model change is never stated.
- **F4 (block)** — `NotApplicableReason` is a `Literal`, not an enum; AC-1/test/outline assume enum
  semantics (`NotApplicableReason.CVE_NOT_IN_APP_LAYER`); the prescribed lowercase value
  `"cve_not_in_app_layer"` contradicts the UPPER_SNAKE convention.
- **F5 (harden)** — Zero-affected-packages CVE case unpinned (vacuous OR → misleading short-circuit).
- **F6 (harden)** — Multi-package logical-OR matching is in Notes only; no AC/test pins it.
- **F7 (harden)** — `node_manifest` slice missing / `bundle is None` not covered; absence-of-data
  would masquerade as absence-of-package.
- **F8 (harden)** — Positive-path event emission (`present_in_app_layer=True`) unverified.
- **F9 (harden)** — `npm_dep_graph_digest` determinism unpinned despite veto-strength G4; `AC-4` and
  `AC-5` use different names (`npm_dep_graph_digest` vs `dep_graph_digest`).
- **F10 (harden)** — Scoped names (`@scope/name`), case-sensitivity, empty-graph not pinned.
- **F11 (nit)** — `_WARNING_IDS` refactor note adds a warning ID but no AC emits a warning — orphan.
- **F12 (nit)** — AC-6 "pass on touched files" would skip the S5-01/S6-04/S5-05 consumer tests.
- **F13 (nit)** — Out-of-scope section confirmed meaningful — no action.
- **F14 (block)** — Lazy-impl thought experiment: a node that always `Advance`s passes every literal
  AC; AC-2 phrases behaviour as an implementation description, not an observable contract. Split into
  two observable ACs (short-circuit arm, advance arm).

### Test-Quality critic

- **F1 (block)** — TDD pseudocode does not type-check / import: enum attribute access on a `Literal`,
  the nonexistent dotted `RemediationOutcome.NotApplicable`, `build_subgraph()` with no `registry`
  arg, `PluginScope.parse(...)` (a `Result`) passed straight to `resolve()`.
- **F2 (block)** — Positive test asserts only `not _is_precheck_refuse(outcome)`; a no-op
  `return Advance(state)` mutant passes it.
- **F3 (block)** — Six undefined helpers; `_run_subgraph` invoked with two contradictory signatures.
- **F4 (block)** — Tests depend on the `express-cve-2024-21501` fixture owned by S8-01, which runs
  *after* S7-05; `Depends on` omits it — a dependency cliff.
- **F5 (harden)** — No determinism test for `npm_dep_graph_digest`; `hypothesis` is already a dev dep.
- **F6 (harden)** — No multi-package OR test; an `all(...)` AND-mutant passes all three planned tests.
- **F7 (harden)** — Negative test does not assert the precheck short-circuited *at the head* — a
  node placed last still produces `CVE_NOT_IN_APP_LAYER`.
- **F8 (harden)** — The pure lookup helper has no fast unit test; matching logic is only covered
  through heavyweight integration tests.
- **F9 (nit)** — Event test does not constrain payload fields beyond `present_in_app_layer`.
- **F10 (nit)** — `_WARNING_IDS` discipline added in Refactor but no test asserts it.

### Consistency critic

- **F1 (block)** — AC-1 prescribes the wrong serialization value (`"cve_not_in_app_layer"` vs the
  UPPER_SNAKE convention) and the wrong type vocabulary ("enum variant" vs `Literal` member).
- **F2 (block)** — AC-4 + outline step 6 require an `evidence` field absent from
  `RemediationNotApplicable`; the additive change and the triggered S6-06 contract-snapshot
  regeneration are never stated.
- **F3 (block)** — AC-2 references nonexistent `SubgraphState` fields; two contradictory access
  paths; `read_raw_slices` does not exist in S5-04.
- **F4 (harden)** — Nonexistent dotted forms `RemediationOutcome.NotApplicable` /
  `RecipeOutcome.NotApplicable` throughout the Goal/ACs/outline/TDD.
- **F5 (block)** — Files-to-touch vs implementation-outline contradict on where
  `AppLayerAbsenceEvidence` lives; the plugin-dir placement would invert the dependency direction
  (core `transforms/` importing from `plugins/`).
- **F6 (block)** — Files-to-touch names `src/codegenie/transforms/types/outcomes.py` and
  `src/codegenie/events/workflow_internal.py`; neither path exists (the real paths are
  `transforms/outcomes.py` and `plugins/events.py`).
- **F7 (block)** — AC-5 treats `AppLayerPrecheckCompleted` as a union class variant to "just add";
  the event taxonomy is a closed contract surface gated by the S6-06 snapshot — additive extension
  is allowed (S3-05 `cache_gc_completed` precedent) but must be explicit.
- **F8 (harden)** — References cites a phantom "CVE for unrelated package" row in arch §Edge cases
  (E1–E20 has no such row).
- **F9 (harden)** — Implicit forward dependency on the S8-01 fixture; `Depends on` omits it.
- **F10 (harden)** — Story first-implements `build_subgraph` (S7-01 shipped a `NotImplementedError`
  stub) but never says so; the TDD calls `build_subgraph()` with no `registry`.
- **F11 (nit)** — `_WARNING_IDS` is a *probe* discipline; a `SubgraphNode` has no warning channel.
- **F12 (harden)** — `RecipeOutcome` vs `RemediationOutcome` conflated; the node constructs
  `RemediationNotApplicable`, and the new member joins the *shared* `NotApplicableReason` Literal.
- **F13 (harden)** — Outline step 6 widens `outcome.evidence` into a "discriminated union over
  `AppLayerAbsenceEvidence | …existing variants…`" — there are zero existing variants; a
  one-member union is premature abstraction.

### Design-Patterns critic

- **F1 (block)** — `AppLayerAbsenceEvidence` placed in the plugin directory inverts the dependency
  direction; a core sum-type member naming it forces `transforms/ → plugins/` import.
- **F2 (harden)** — `PackageName` is an invented identifier; the codebase's domain ID is `PackageId`
  (with a `.parse` smart constructor, the type `VulnIndex` keys on).
- **F3 (harden)** — `outcome.evidence` discriminated union is premature (zero existing variants);
  ship `evidence: AppLayerAbsenceEvidence | None = None`.
- **F4 (harden)** — No observable AC pins the package-in-dep-graph lookup as a pure, separately
  testable function; the Refactor section only *mentions* it. Phase 7 must wrap it without a
  refactor — the rule-of-three threshold is met by the named second consumer, so an AC is warranted.
- **F5 (block)** — `SubgraphState` lacks `cve_record`/`npm_dep_graph`; AC-2 reads fields that do not
  exist; `state.npm_dep_graph` is wrong (the tree is reached via `state.bundle`).
- **F6 (nit)** — Event emission location undefined; risk of pure-impure tangle inside the helper.
- **F7 (nit)** — Positive finding: the node is a conforming *leaf*; no premature registry/ABC/adapter
  is introduced; the Phase-7 deferral in Out-of-scope is the correct Rule-2 call.
- **F8 (harden)** — Multi-package OR semantics has no observable AC — it defines the helper's core
  contract and the most likely implementation bug (AND vs OR).

## Research briefs

None. No finding was tagged `NEEDS RESEARCH` — every weakness was resolvable by reading the shipped
sibling code and stories.

## Conflict resolutions

No genuine critic-vs-critic conflicts arose; the synthesis priority chain
(`Consistency > Coverage > Test-Quality > Design-Patterns`) was not needed to break a tie. Three
notable cross-critic *agreements* (recorded so the merge is auditable):

1. **`_WARNING_IDS` orphan** — flagged independently by Coverage F11, Test-Quality F10, Consistency
   F11. All three agree it is dead scaffolding (a `SubgraphNode` is not a probe and has no warning
   channel). Resolution: the `_WARNING_IDS` refactor bullet was removed.
2. **Evidence model location** — Consistency F5 and Design-Patterns F1 independently concluded
   `AppLayerAbsenceEvidence` must live in core `transforms/`, never the plugin directory (dependency
   inversion). Resolution: AC-6 + Files-to-touch + outline all pin the core location.
3. **Premature discriminated union** — Consistency F13 and Design-Patterns F3 both flagged the
   one-member union. This is the one place Rule 2 (Simplicity First) is senior to a Design-Patterns
   proposal — but here Design-Patterns *agreed* the union is premature, so Rule 2 and the critic
   point the same way. Resolution: `evidence: AppLayerAbsenceEvidence | None = None`, plain optional
   field; the future-union opportunity surfaced in Notes-for-implementer, not as an AC.

## Edits applied

### Edit 1 — Status + Validation-notes block
- Source: validator housekeeping.
- `Status: Ready` → `Status: HARDENED (validated 2026-05-20 — …)`. `Effort` raised `S` → `S–M`.
  Added a `## Validation notes (2026-05-20)` block summarising the block-tier closures.

### Edit 2 — `Depends on` line
- Source: Consistency F9, F12.
- Added S6-01 (event module) and S6-06 (contract snapshot) as explicit dependencies; corrected the
  S5-01 description (`RecipeOutcome.NotApplicable.reason` → the shared `NotApplicableReason` Literal);
  noted S7-01 ships `build_subgraph` as a stub this story first implements.

### Edit 3 — `ADRs honored` line
- Source: Consistency F1, F12.
- `new RecipeOutcome.NotApplicable.reason = CVE_NOT_IN_APP_LAYER variant` → `new NotApplicableReason
  Literal member "CVE_NOT_IN_APP_LAYER"`.

### Edit 4 — Goal
- Source: Consistency F4; Coverage F14.
- `ShortCircuit(RemediationOutcome.NotApplicable(reason=CVE_NOT_IN_APP_LAYER))` → real class
  `RemediationNotApplicable(reason="CVE_NOT_IN_APP_LAYER", evidence=…)`; added the `Escalate(…)` arm
  for the degenerate-input case.

### Edit 5 — References §Architecture
- Source: Consistency F8.
- Removed the phantom "CVE for unrelated package" §Edge cases row; re-anchored to the real adjacent
  rows (E2, E5) and to ADR-0038 §Context as the actual specification source.

### Edit 6 — Acceptance criteria (full rewrite)
- Source: every critic.
- The 7 unlabelled bullets were replaced with 14 labelled, individually-verifiable ACs:
  - **AC-1** — `NotApplicableReason` is a `Literal`; new member is UPPER_SNAKE `"CVE_NOT_IN_APP_LAYER"`
    at the single declaration site; `assert_never` exhaustiveness at all three `match` sites.
    (Coverage F4, Consistency F1.)
  - **AC-2 / AC-3** — AC-2 split into two observable behaviour ACs: the short-circuit arm and the
    advance arm. (Coverage F14, Test-Quality F2.)
  - **AC-4** — the node reads only real `SubgraphState` fields (`state.cve`, `state.bundle`); the
    `cve_record`/`npm_dep_graph`/`snapshot.root`/`read_raw_slices` references removed; an explicit
    executor precondition added (bind to the real `Bundle`/TCCM API; BLOCKED-PARTIAL rather than
    invent a `SubgraphState` field). (Coverage F1+F2, Consistency F3, Design-Patterns F5.)
  - **AC-5** — six-node subgraph; `build_subgraph(self, registry)` first-implemented (S7-01 stub),
    npm-plugin-local customization. (Consistency F10.)
  - **AC-6** — `AppLayerAbsenceEvidence` in core `transforms/`; `PackageId`, not `PackageName`.
    (Consistency F5+F6, Design-Patterns F1+F2.)
  - **AC-7** — `RemediationNotApplicable` gains `evidence: … | None = None` additively (precedent:
    `RecipeNotApplicable.considered`); plain optional field, not a union. (Consistency F2+F13,
    Design-Patterns F3, Coverage F3.)
  - **AC-8** — `npm_dep_graph_digest` deterministic over a canonical serialization; name reconciled.
    (Coverage F9, Test-Quality F5.)
  - **AC-9** — normalized matching (lowercase, scoped names) + logical-OR multi-package.
    (Coverage F6+F10, Test-Quality F6, Design-Patterns F8.)
  - **AC-10** — `AppLayerPrecheckCompleted` additive event, one per invocation on both paths.
    (Coverage F8, Consistency F7, Test-Quality F8-adjacent.)
  - **AC-11** — degenerate inputs `Escalate`, never a misleading `CVE_NOT_IN_APP_LAYER`.
    (Coverage F5+F7.)
  - **AC-12** — the lookup is a separately-testable pure function (the Phase-7 seam).
    (Design-Patterns F4, Test-Quality F8.)
  - **AC-13 / AC-14** — red tests green; full `make check` + `make lint-imports` green; S6-06
    snapshot regenerated. (Test-Quality F1, Coverage F12, Consistency F14-adjacent.)

### Edit 7 — Implementation outline (full rewrite)
- Source: Coverage F1-F4, Consistency F2/F5/F6/F13, Design-Patterns F1/F3.
- Eight steps pinned to real paths and the shipped types: `Literal` member, core evidence model +
  additive field, pure helper as a distinct step, real `SubgraphState` reads, `build_subgraph`
  first-implementation, additive event variant, report-writer serialization, S6-06 snapshot regen.

### Edit 8 — TDD plan (full rewrite)
- Source: Test-Quality F1-F10, Coverage F5-F10, Design-Patterns F4/F8.
- Pseudocode rewritten against verified APIs (`match RemediationNotApplicable(reason="…")`,
  `PluginScope.parse(…).unwrap()`, `build_subgraph(default_registry)`). Story-local fixtures + a
  single-signature `conftest.py` replace the undefined helpers and the S8-01 dependency. Added:
  positive-path event assertion, head-of-subgraph ordering test, multi-package OR/AND tests,
  missing-slice + zero-affected escalation tests, a fast pure-helper unit-test file, and a
  `hypothesis` digest-determinism property test. The `_WARNING_IDS` refactor bullet was removed.

### Edit 9 — Files to touch (full rewrite)
- Source: Consistency F5+F6, Test-Quality F3+F4.
- Every fabricated path corrected (`transforms/outcomes.py`, `transforms/evidence.py`,
  `plugins/events.py`); rows added for the pure-helper file, the `conftest.py` + fixtures, the
  unit-test file, the `match`-site edits, and the S6-06 snapshot regeneration.

### Edit 10 — Notes for the implementer (rewrite)
- Source: Coverage F1 (self-contradiction), Design-Patterns F2/F4/F6, Consistency F11.
- Removed the self-contradictory "node sits BEFORE `ingest_cve` … reads the parsed CVE" bullet.
  Added: bind-to-real-APIs-first guidance with the explicit BLOCKED-PARTIAL escape hatch;
  absence-of-data ≠ absence-of-package; `PackageId` not `PackageName`; evidence stays a plain
  optional field until Phase 7's rule-of-three; the pure helper is the Phase-7 seam.

## Verdict rationale

**HARDENED.** The goal is sound and well-motivated; it traces directly to ADR-0038 §Decision and
ADR-0003. All 14 block-tier findings were defects in the *ACs / outline / TDD plan* — the story was
written against an imagined API surface — and every one had a determined, in-place fix grounded in
the shipped sibling code (`outcomes.py`, S6-03, S7-01, S6-01). No finding required rewriting the
goal or scope, so this is not a RESCUE. The one genuinely hard area — how the node reaches the CVE's
affected-package set, given `SubgraphState` exposes only `cve: CveId` — was hardened honestly: the
ACs now name only real fields, route both reads through `state.bundle`, and carry an explicit
executor precondition (Rule 12 — fail loud) that a `SubgraphState` widening, if truly required, is a
contract change to surface as BLOCKED-PARTIAL rather than invent silently.

## Recommended next step

`phase-story-executor` to implement S7-05. The executor's **first** action must be the AC-4
precondition: bind the node's two `state.bundle` reads to the real S3-04 `Bundle` / S7-01 TCCM API
and confirm the affected-package set is reachable; if it is not, surface a BLOCKED-PARTIAL before
writing further code.
