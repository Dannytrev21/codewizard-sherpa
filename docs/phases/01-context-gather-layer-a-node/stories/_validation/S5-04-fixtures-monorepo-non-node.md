# Validation report — S5-04 Fixtures `node_monorepo_turbo` + `non_node_go`

**Story:** [S5-04-fixtures-monorepo-non-node.md](../S5-04-fixtures-monorepo-non-node.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S5-04 is a **data-fixture story** that ships two new fixtures (`node_monorepo_turbo/`, `non_node_go/`) plus an updated inventory file. The first-draft framing treated it as "data-only, no TDD" with a manual smoke check as the only verifier. This regressed against the **S2-03 hardened-story precedent** (the canonical fixture `node_typescript_helm/`), which already established that fixture content has testable structural invariants — closed-set complement, parseability, forbidden subpaths, README cross-reference, multi-marker invariants — and that those invariants belong in a typed `_FILE_SPECS: tuple[_FileSpec, ...]` parametrized shape test under `tests/unit/`.

The validation:
- **AC count: 9 prose-style ACs → 22 numbered ACs** (`MR-1..8`, `NN-1..8`, `SHARED-1..7`). Each new AC is individually verifiable and binds an observable.
- **TDD plan: "data-only, smoke check" → real red/green/refactor.** Two new shape-test modules (`tests/unit/test_fixture_node_monorepo_turbo_shape.py` + `tests/unit/test_fixture_non_node_go_shape.py`) are now in the Files-to-touch table. Both follow the S2-03 typed-`_FileSpec`-manifest precedent.
- **Mutation log: 13 mutations** that would have passed the first-draft smoke check are now caught by the hardened suite.
- **Slice-filter accuracy correction.** First draft said "Phase 1's five Node-only probes are filtered out." Source-of-truth code (`src/codegenie/probes/{ci,deployment}.py`) shows only three are filtered (`node_build_system`, `node_manifest`, `test_inventory`); `ci` and `deployment` declare `applies_to_languages = ["*"]` and run on every repo. ACs and the prescribed README content now reflect the actual observable. (This was a **block**-tier consistency finding — the README, if shipped as first-drafted, would actively misinform future contributors.)
- **Design-pattern lifts (per primary user focus).** Typed `_FILE_SPECS` SSoT (Open/Closed at the file boundary), `Literal` closed sets for `_ProbeName` / `_ParserKind` (make illegal states unrepresentable), pure content-check predicates (functional core / imperative shell). Notes-for-implementer surfaces the rule-of-three deferral: the typed-fixture-manifest kernel earns extraction to a shared `tests/unit/_fixture_shape_kernel.py` at Phase 2's golden-portfolio work — fourth concrete consumer — not in this story (Rule 2 + Rule 3).

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0004 / ADR-0010, source-of-truth code in `src/codegenie/probes/`) plus the S2-03 hardened-story precedent already in this directory. Stage 3 (researcher) skipped per the skill's token-economy guidance.

## Stage 1 — Context loaded

Read:
- The story (`S5-04-fixtures-monorepo-non-node.md`).
- `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` §§ "Fixture portfolio", "Edge cases" row 11, "Scenarios" Scenario 4, "Component design" #1 (LanguageDetectionProbe extension).
- ADRs: `0004-per-probe-subschema-additional-properties-false.md`, `0010-layer-a-slices-optional-at-envelope.md`.
- Existing fixtures: `tests/fixtures/node_typescript_helm/README.md`, `tests/fixtures/node_pnpm_native/README.md`.
- Existing shape test: `tests/unit/test_fixture_node_typescript_helm_shape.py` (S2-03 hardened precedent).
- Source-of-truth code: `src/codegenie/probes/language_detection.py` (`_MONOREPO_PRECEDENCE`, `_detect_monorepo`); `src/codegenie/probes/{ci,deployment,node_build_system,node_manifest}.py` (`applies_to_languages` declarations).
- Prior validation report: `_validation/S2-03-fixture-node-typescript-helm.md` (the template this report mirrors).

## Stage 2 — Critics (inline synthesis)

The four critics were synthesized inline rather than spawned as four parallel subagents. Justification: this is a small data-fixture story (~150 lines of doc, no code-producing scope beyond the two new shape-test modules) with a sibling-story precedent already in the same directory (S2-03 validation). Token-economy alternative per the skill's stage-2 guidance.

### Critic A — Coverage

| Severity | Finding | Resolution |
|---|---|---|
| **block** | First-draft AC said "**does not** contain `build_system`, `manifests`, `test_inventory` slices for Node." Slice key names are imprecise (actual keys are `node_build_system`, `node_manifest`, `test_inventory`). | AC-NN-6 names slice keys exactly. |
| **block** | First-draft AC enumerated only 6 forbidden Node markers (`package.json`, `tsconfig.json`, `pnpm-lock.yaml`, "node-related files of any kind") and only as a Refactor-section `find` command — operator-run, not test-enforced. | AC-NN-2 lifts to a parametrized test over an expanded forbidden-subpath set including `package-lock.json`, `yarn.lock`, `.nvmrc`, `tsconfig.base.json`, `node_modules`, `.codegenie`, `dist`, `coverage`, `.DS_Store`, `.idea`, `.vscode`. |
| **block** | First-draft had no closed-set complement. A stray `notes.md` or accidental file in either fixture would silently break the S5-05 e2e gather without any failing test. | AC-MR-1 + AC-NN-1 lift the closed-set complement to typed `_FILE_SPECS`. `test_fixture_tree_is_closed_set` walks the tree. |
| **block** | The "uses two markers" invariant — Notes-for-implementer language — is THE structural reason `node_monorepo_turbo` exists (per arch design Component-design #1: "the linear scan in `run` never grows" and the precedence-chain test). First-draft had no AC for it. | AC-MR-3 pins both markers AND the precedence-resolved `tool == "turbo"`. |
| harden | First-draft had no parseability invariant. A malformed `pnpm-lock.yaml` or `turbo.json` would pass existence ACs and fail opaquely in S2-04 / S5-05. | AC-MR-2 / AC-MR-4 / AC-MR-5 / AC-MR-6 invoke `parsers.safe_json.load` / `parsers.safe_yaml.load` for every JSON/YAML file. |
| harden | `lockfileVersion: '6.0'` not pinned; first-draft permitted any pnpm lockfile version. Inconsistency with S2-03's pinned `'6.0'` would diverge S2-02 lockfile-precedence test paths. | AC-MR-6 pins `lockfileVersion == "6.0"`. |
| harden | `go.mod` exact bytes not pinned; trailing-space mutation would silently dirty a future golden. | AC-NN-3 pins exact bytes including LF terminators. |
| harden | Workspace-member `package.json` shape was prose ("each with `"name": "@scope/app-web"`..."); no test enforcement. | AC-MR-5 + `_workspace_member_shape` predicate. |
| harden | First-draft AC said `language_stack.primary: "go"` but no count threshold ensures the walker actually picked up Go files. | AC-NN-5 adds `counts["go"] >= 2`. |
| harden | First-draft was silent on whether `ci` / `deployment` slices should be present on `non_node_go`. Source-of-truth code says they will (applies_to_languages=["*"]). Without explicit AC, downstream S5-05 assertions could mis-assume. | AC-NN-7 permits (does not require) `ci`/`deployment` present-with-empty; AC-NN-8 mandates README clarifies the behavior. |
| harden | Top-level `tests/fixtures/README.md` (AC-SHARED-1) had no column requirements; "table format" was prose. | AC-SHARED-1 names required columns `{fixture, exercises, consumed-by, ADR-anchor}`. |
| nit | First-draft mentioned "no `.DS_Store` or editor artifacts" only in Refactor. | Covered by AC-NN-2's expanded forbidden-subpath set; AC-MR-1's closed-set complement covers it for the monorepo fixture. |

### Critic B — Test Quality (mutation-resistance lens)

The first-draft TDD plan had **no automated tests** — only a manual `yq`-based smoke check. Thirteen mutations would have passed the first-draft smoke check; the hardened suite catches each (see story's Mutation log section).

Particularly load-bearing mutations:

| Mutation | First-draft caught? | Hardened by |
|---|---|---|
| Drop `workspaces` from `package.json`; keep `turbo.json` (the multi-marker invariant breaks but smoke check still finds `tool: turbo` because turbo.json is hit first) | NO | `test_monorepo_two_markers_detected` (AC-MR-3) |
| `non_node_go/package.json` accidentally added | NO (Refactor `find` is operator-run) | `test_no_forbidden_subpaths` (AC-NN-2) |
| README still says "five probes filtered out" | NO | `test_non_node_go_readme_mentions_three_not_five` (AC-NN-8) |
| `pnpm-lock.yaml` is empty / malformed | NO (smoke check doesn't open it) | `test_fixture_file_parses[pnpm-lock.yaml]` (AC-MR-6) |
| Stray `notes.md` in either fixture | NO | `test_fixture_tree_is_closed_set` (AC-MR-1, AC-NN-1) |
| `turbo.json` is `{}` | NO | `_turbo_json_minimum_shape` (AC-MR-4) |
| CRLF line endings sneak in | NO | `test_fixture_file_line_endings` (AC-SHARED-4) |

### Critic C — Consistency

| Severity | Finding | Resolution |
|---|---|---|
| **block** | First-draft README content for `non_node_go/` said "Phase 1's five Node-only probes are filtered out by `Registry.for_task` against `applies_to_languages`." Source-of-truth `src/codegenie/probes/ci.py:515` + `src/codegenie/probes/deployment.py:702` both declare `applies_to_languages = ["*"]` — they run on Go-only repos. Only THREE are filtered (`node_build_system`, `node_manifest`, `test_inventory`). | **AC-NN-8** mandates README says "three" not "five" AND clarifies CI/Deployment behavior. AC-NN-7 codifies that `ci`/`deployment` may be present with empty contents. Validation-notes section flags this as a first-draft inconsistency to fix. |
| harden | `phase-arch-design.md "Edge cases" row 11` itself reads "Five Phase 1 probes filtered out" — this is an arch-doc-vs-code drift (the arch may have been written assuming CI/Deployment would be Node-only; the code chose `["*"]`). | Out of this story's scope to fix the arch doc — flagged as a known drift; the story matches the observable code behavior. The arch row should be amended in a separate doc-fix PR (out of this story's scope per Rule 3). |
| harden | First-draft cited `ADR-0004` and `ADR-0010` in the header. ADR-0007 (warning ID pattern) is tangentially relevant — fixture content must not produce warnings that violate the pattern. | Added ADR-0007 to header with a defensive note in AC-SHARED-6. |
| nit | `non_node_go` README's "Phase 1 design ref" should reference both `phase-arch-design.md §"Fixture portfolio"` AND `ADRs/0010-layer-a-slices-optional-at-envelope.md`. First-draft had only the arch-design reference. | AC-NN-8 mandates both references. |

### Critic D — Design Patterns (per primary user focus)

The first-draft "data-only, no TDD" framing missed every design-pattern opportunity the S2-03 hardening already established. Same pattern catalog applies:

| Severity | Pattern | Decision |
|---|---|---|
| **harden** | **Closed-set typed manifest as SSoT** (`_FILE_SPECS: tuple[_FileSpec, ...]`). | **Lifted to AC-SHARED-2.** Both new shape-test modules use the S2-03 `_FileSpec` NamedTuple shape. Adding a fixture file = one tuple entry, zero edits to parametrized tests. Open/Closed at the file boundary. |
| **harden** | **`Literal` closed sets for `_ProbeName` / `_ParserKind`** — make illegal states unrepresentable. | **Lifted to AC-SHARED-3.** `_ProbeName = Literal[...]` is the same closed set S2-03 declared. Typo'd consumer fails at `mypy --strict` AND at the runtime contract test. |
| **harden** | **Pure content-check predicates** (functional core / imperative shell). | Reflected in TDD plan's Red step: predicates are pure functions; the parametrized test body is the imperative shell that reads file + dispatches to parser. |
| **harden** | **Open/Closed-at-file-boundary precedent** — same shape S2-01's `_MONOREPO_PRECEDENCE` and S2-02's `_LOCKFILE_PRECEDENCE` set in production. | Notes-for-implementer surfaces the alignment. |
| nit (deferred) | **Rule-of-three kernel extraction.** With this story, four concrete consumers of `_FileSpec` will exist in `tests/unit/`. The kernel extraction (`tests/unit/_fixture_shape_kernel.py`) is the right move at the fourth concrete consumer — **but not in this story**. Per Rule 2 + Rule 3, keep each module self-contained; defer the lift to Phase 2's golden-portfolio work. | Documented in Notes-for-implementer as a deferred opportunity. **No AC added** because adding one would force premature abstraction (Rule 2: "three similar lines is better than premature abstraction"; we're at three, the lift earns at four). |
| nit | **AC-as-observable, not pattern-name-mandate.** Per the skill's editor rule: design-pattern opportunities go in Notes-for-implementer; ACs encode observables. | Followed: AC-SHARED-2 and AC-SHARED-3 are phrased as "fixture has a typed manifest" / "Literal closed set typo'd consumer fails mypy" — observables, not "use the Strategy pattern." |

## Stage 3 — Research

**Skipped.** No findings tagged `NEEDS RESEARCH`. All weaknesses resolved from in-repo authority docs and the S2-03 precedent.

## Stage 4 — Synthesizer outcome

### Conflict-resolution table

| Conflict | Resolution | Rule |
|---|---|---|
| Coverage wants `ci`/`deployment` slice ABSENT on `non_node_go`; Consistency says source-of-truth code declares them `applies_to_languages = ["*"]` — they DO run. | Consistency wins. AC-NN-7 permits them present-with-empty. | Source-of-truth (arch + code) dominates pattern intent. |
| Design-Patterns wants a kernel-extraction `tests/unit/_fixture_shape_kernel.py` for `_FileSpec`; Rule 2 ("three similar lines is better than premature abstraction") says wait. | Rule 2 wins. Defer lift to Phase 2. Surface in Notes-for-implementer. | Validator does not push abstraction past the YAGNI threshold. |
| Coverage wants every probe slice's contents pinned to specific values; story's stated scope is "structural assertions land in S5-05." | Story scope wins. AC-MR-8 / AC-NN-5–7 pin only the smoke-check observables; deep slice content is S5-05's job. | Skill anti-goal: validator does not rewrite the story's goal. |

### Edits applied to the story file (in-place)

- **Header.** Added `Validation notes` block. Added ADR-0007 to "ADRs honored."
- **Acceptance criteria.** Replaced 9 prose-style ACs with 22 numbered ACs (`MR-1..8`, `NN-1..8`, `SHARED-1..7`). Each AC is individually verifiable; each names the test that enforces it.
- **TDD plan.** Replaced "data-only, no TDD" framing with a real red/green/refactor flow. Added Mutation-log table showing 13 mutations the hardened suite catches.
- **Files to touch.** Added two new rows for the shape-test modules with explicit precedent reference.
- **Notes for the implementer.** Restructured into "Design patterns / extension-by-addition" + "Fixture-content discipline" + "Cross-references" sections. The design-pattern section surfaces SSoT, `Literal` closed-set discipline, pure predicates, rule-of-three deferral.

### Verdict

**HARDENED.** The story now has:
- AC battery that constrains a correct implementation and would surface 13 named mutations.
- TDD plan with red/green/refactor that can be executed mechanically.
- Source-of-truth-accurate README prescription (three filtered probes, not five).
- Closed-set complement for both fixtures (no silent stray files).
- Forward-compatibility for turbo schema versions (`pipeline` ≤ 1.x OR `tasks` ≥ 2.x).
- Open/Closed-at-file-boundary discipline for the shape-test modules.
- Documented kernel-extraction opportunity at the rule-of-three threshold, deferred to the appropriate future story.

Ready for `phase-story-executor`.
