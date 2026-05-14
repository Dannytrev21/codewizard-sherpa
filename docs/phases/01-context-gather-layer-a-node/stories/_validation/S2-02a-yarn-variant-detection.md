# Validation report — S2-02a (Yarn variant detection)

**Story:** [`stories/S2-02a-yarn-variant-detection.md`](../S2-02a-yarn-variant-detection.md)
**Validator run:** 2026-05-14
**Skill:** `phase-story-validator`
**Verdict:** **HARDENED** — story strengthened in place; ready for `phase-story-executor`.

## Stage 1 — Context

Read in full:

- Story file
- `docs/phases/01-context-gather-layer-a-node/ADRs/0013-yarn-variants-as-distinct-package-managers.md` (the decision)
- `docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md`, `0004-per-probe-subschema-additional-properties-false.md`, `0007-warnings-id-pattern.md`
- `src/codegenie/probes/node_build_system.py` (711 lines; the shipped + working-tree-modified probe)
- `src/codegenie/schema/probes/node_build_system.schema.json` (already at `$id v0.2.0`, enum split)
- `tests/unit/probes/test_node_build_system_yarn_variant.py` (already-authored red-phase tests, 507 lines)
- `docs/phases/01-context-gather-layer-a-node/stories/S3-03-yarn-lockfile-parser.md` (to verify the downstream-impact claim)
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S2-02-node-build-system-probe.md` (sibling family validation report)

**Implementation state at validation time:** the working tree contains modifications to `node_build_system.py` (adds `_BERRY_MARKERS`, `_detect_yarn_variant`, wires `run()`), `node_build_system.schema.json` (already at v0.2.0 with the split enum), `repo_context.schema.json`, and `test_node_build_system.py`. Fixture directories `node_yarn_berry_pnp/`, `node_yarn_berry_nonpnp/`, `node_yarn_legacy/` exist as untracked. The story Status was flipped to **Done** by an external process (likely `phase-story-executor`) mid-validation; validation continued on the SPEC regardless, since the validator's job is to harden the contract, not the code.

## Stage 2 — Four parallel critics

### Coverage critic — 9 findings

| # | Severity | Title | Resolution |
|---|---|---|---|
| C-1 | harden | AC-2 regex misses `yarn@1` (no minor) | **Applied** — AC-2 rewritten to cite the regex anchor explicitly; AC-8 enumerates `"yarn@1"` (no minor) as malformed. |
| C-2 | harden | AC-3 ambiguous on majors ≥ 5 | **Applied** — AC-3 rewritten as `major ≥ 2` (not the enumeration `{2,3,4}`); a hypothesis property test row added. |
| C-3 | harden | Variant + cross-manager declaration disagreement not AC'd | **Applied** — new **AC-9b** + dedicated TDD-plan row `test_cross_manager_declaration_disagreement`. |
| C-4 | harden | Warning emission location underspecified | **Applied** — new **AC-20** pins `build_system.warnings` (NOT `ProbeOutput.warnings`). |
| C-5 | harden | AC-13 idempotency weaker than purity | **Applied** — AC-13 rewritten to enumerate the read-only filesystem operations + property-test priority invariant (the *stronger* form requested by Test-Quality F3). |
| C-6 | harden | AC-4/5/6 don't pin precondition (yarn.lock must win first) | **Applied** — explicit **Precondition** clauses added to ACs 4, 5, 6 + new TDD row `test_pnpm_higher_precedence_skips_variant_detection`. |
| C-7 | harden | AC-8 malformed shapes incomplete (missing non-string types) | **Applied** — AC-8 rewritten to enumerate non-string types (missing, `null`, integer, list, dict, boolean) + dedicated parametrized TDD row `test_packagemanager_non_string_param`. Crucially: non-string types do NOT emit `package_manager_field_unparseable` (absence is normal). |
| C-8 | nit | `.yarnrc.yml` + legacy `.yarnrc` co-existence not AC'd | **Applied** — AC-4 now explicitly covers the mid-migration case. |
| C-9 | nit | Path edge cases (symlink, case, Windows) unconstrained | **Deferred** — surfaced as nit only; not added to AC. The shipped `Path.exists()` / `.is_dir()` semantics are accepted as-is. |

### Test-Quality critic — 8 findings

| # | Severity | Title | Resolution |
|---|---|---|---|
| T-1 | **block** | Priority-order flip undetectable | **Applied** — two new **AC-16** and **AC-17** + dedicated TDD-plan rows `test_priority1_classic_wins_over_yarnrc_yml`, `test_priority1_classic_wins_over_pnp_cjs`, `test_priority3_yarnrc_yml_wins_over_yarn_dir_and_pnp`. |
| T-2 | harden | Regex-too-loose mutation undetected | **Applied** — AC-8 + the parametrize row now covers `"yarn@2x"`, `"yarn@123abc"`, `"yarn@1x.0"`. |
| T-3 | harden | AC-13 idempotency is Rule 9 anti-pattern | **Applied** — AC-13 + `test_property_priority_invariant` TDD row replaces the original idempotency test with a hypothesis property test pinning the priority invariant (forces classic on priority-1-positive; forces berry on priority-2-positive; metamorphic invariant on lower-priority marker removal). |
| T-4 | nit | Berry YAML lockfile-header negative test missing | **Applied** — new **AC-22** + `test_lockfile_body_ignored_by_variant_detection` TDD row. |
| T-5 | (resolved) | `SchemaValidationError` test wiring | Already correct — flagged as resolved. |
| T-6 | nit | `_validator.cache_clear()` coupling | **Deferred** — recommendation for executor to add an autouse fixture; not promoted to AC. |
| T-7 | nit | `test_pnpm_declared_on_yarn_lockfile_still_disagrees` accepts either variant | **Applied** — `test_cross_manager_declaration_disagreement` (the AC-9b row) pins the exact safe-default outcome. |
| T-8 | harden | No test asserts absent `unparseable` warning on well-formed yarn | **Applied** — new **AC-21**: every positive-case test must assert both `yarn_variant_inferred` AND `package_manager_field_unparseable` are absent. |

### Consistency critic — 9 findings

| # | Severity | Title | Resolution |
|---|---|---|---|
| K-1 | **block** | Story narrative says probe still emits `"yarn"`, but code already ships v0.2.0 + `_detect_yarn_variant` | **Applied** — Validation notes block under the header reconciles the state ("code is partially landed in working tree; the executor verifies, not redoes"). The original Context paragraph kept for historical accuracy; Validation notes documents the drift. |
| K-2 | harden | Schema `$id` bump is MAJOR-class, not MINOR; ADR-0004 has no policy | **Surfaced** — added as a "Schema `$id` increment — deferred policy gap" paragraph under Notes for implementer. Not blocking; flagged for Phase 2 policy ratification. |
| K-3 | harden | `slice.warnings` vs `ProbeOutput.warnings` emission location unwritten | **Applied** — new **AC-20** + warning-emission paragraph in Notes for implementer pin the location. |
| K-4 | **block** | Out-of-scope §1 stale: S3-03 chose unified `_HAS_PYARN` dispatch, not variant-branching | **Applied** — Out-of-scope §1 rewritten to correct the prose; references the actual hardened S3-03 design + flags the ADR-0013 Consequences §2 amendment as a follow-up. (See "Cross-cutting follow-ups" below.) |
| K-5 | nit | AC-13 "pure" wording internally inconsistent | **Applied** — AC-13 rewritten as "deterministic and side-effect-free beyond enumerated marker reads". |
| K-6 | harden | AC-14 tuple-shape lie — `("yarn.lock", "yarn")` is overridden | **Applied** — AC-14 rewritten to require an inline `# NOTE:` comment at the override line + a `test_lockfile_tuple_shape_preserved` introspection test. |
| K-7 | nit | AC-3 wording enumerates "2/3/4" but ADR uses open-ended `\d+` | **Applied** — AC-3 + the hypothesis property test pin `major ≥ 2`, open-ended. |
| K-8 | harden | Confidence-demotion asymmetry vs `multi_lockfile` | **Applied** — Notes-for-implementer "Confidence accounting (asymmetry rationale)" paragraph explains the secondary-dimension rationale. Decision is to **keep** the asymmetry (no demotion in the safe-default path); the warning IS the load-bearing signal at the variant layer. |
| K-9 | nit | Out-of-scope §5 elides Phase 0 cache invalidation | **Applied** — Notes-for-implementer "Local-dev cache invalidation" paragraph documents the one-time cache-rebuild behavior. |

### Design-Patterns critic — 6 findings

| # | Severity | Title | Resolution |
|---|---|---|---|
| D-1 | harden | Variant-detection chain should be a module-level tuple (`_BERRY_MARKERS`) parallel to existing tuples | **Applied** — Implementation outline §2 rewritten to show the `_BERRY_MARKERS` tuple form + a small `for name, predicate in _BERRY_MARKERS` loop in `_detect_yarn_variant`. New **AC-18** makes the tuple structure an *observable* constraint ("adding a new Berry marker is one tuple-entry insertion; zero edits to control flow"). The shipped code already follows this shape — the AC promotes the property from implicit-in-source to explicit-in-spec. |
| D-2 | harden | Missing compile-time discipline assert on the new tuple | **Applied** — new **AC-19** + an explicit assert in the Implementation outline mirroring the existing `_LOCKFILE_PRECEDENCE[0][1] == "bun"` and `_BUNDLERS_SORTED` sortedness asserts. |
| D-3 | harden | Pure/impure tangle — functional core / imperative shell opportunity | **Surfaced (not promoted to AC)** — added a "Functional-core / imperative-shell opportunity" paragraph in Notes for implementer. Rule 2 tension: at one caller and ~30 LOC, current shape is fine. Don't refactor prematurely; revisit when a second consumer crystalizes. |
| D-4 | nit | Primitive obsession on the variant string | **Surfaced** — Notes paragraph: lift to `class PackageManager(StrEnum)` when a third real consumer crystalizes (rule-of-three). Not promoted to AC. |
| D-5 | nit | Discriminated-union return for variant + evidence | **Deferred** — premature; YAGNI applies at one consumer. Not surfaced. |
| D-6 | harden | Warning-ID registry should be an AC | **Applied** — folded into **AC-19**: both new warning IDs are members of `_WARNING_IDS`; the import-time regex assertion covers them. |

## Stage 3 — Researcher

**Skipped.** No findings were tagged `NEEDS RESEARCH`. The two candidate items (schema `$id` versioning policy; S3-03 design alignment) were resolved by reading existing ADRs and the shipped S3-03 story.

## Stage 4 — Synthesizer

### Conflicts resolved

- **Priority `Consistency > Coverage`:** K-4 (block — S3-03 stale claim) overrode the implicit Coverage assumption that S3-03 would branch on variant. Out-of-scope §1 rewritten to match shipped S3-03 design.
- **Priority `Coverage > Test-Quality`:** Coverage F5 + Test-Quality F3 both targeted AC-13. The Coverage findings drove the AC wording (purity language); Test-Quality drove the test shape (property test with priority invariant). Both merged into the single revised AC-13.
- **Rule-2 (YAGNI) tension:** Design-Patterns F3 (functional core / imperative shell) is a real opportunity but at one caller and ~30 LOC, lifting the chooser to a pure function would be premature. Surfaced as Notes only, not promoted to AC. Same call on D-4 (StrEnum).

### Edits applied to `S2-02a-yarn-variant-detection.md`

1. Status header — added `**Hardened:** 2026-05-14` line and a forward pointer.
2. New **Validation notes** block under the header documenting the changes inline (so a reader sees the diff without consulting this report).
3. ACs 1–15 rewritten in place for precision (regex anchors, "major ≥ 2", marker preconditions, AC-13 reword from "pure" to "deterministic + enumerated read-only I/O", AC-14 reword to acknowledge tuple-literal override).
4. New ACs **9b, 16, 17, 18, 19, 20, 21, 22** added.
5. Implementation outline §2 rewritten to show the `_BERRY_MARKERS` tuple form + the import-time priority anchor assert + the (variant, warnings) tuple return.
6. TDD plan table rewritten — 22 rows replacing the original 11; each row tagged with the AC it pins; mutation-resistance tests (priority-conflict, regex-too-loose, constant-warning, lockfile-body-ignored) made explicit.
7. Out-of-scope §1 rewritten to correct the stale S3-03 claim.
8. Notes-for-implementer expanded with: functional-core opportunity, primitive-obsession note, confidence asymmetry rationale, local-dev cache invalidation, schema `$id` deferred-policy gap.

### Cross-cutting follow-ups (not in this story's scope)

These were surfaced by the critics but do not belong inside this story. Track separately:

1. **ADR-0013 Consequences §2 amendment.** "S3-03 must branch on variant" is wrong; the hardened S3-03 dispatches on `_HAS_PYARN`. ADR text should be corrected to read: "The gather-layer variant split feeds the Planner / Supervisor (production ADR-0031); S3-03's unified parser handles both Classic and Berry lockfile formats internally."
2. **ADR-0004 schema-versioning policy.** Phase 2 should ratify whether enum-value-removal is MAJOR (forcing `v1.0.0` here, in retrospect) or whether MINOR is acceptable for additive-with-deletion enum changes when there are no external consumers yet. This decision affects every future per-probe sub-schema bump in Phase 2+.
3. **S3-03 cross-manager test coverage.** S3-03's hardened story does not include a test that parses a Berry-shaped YAML lockfile with no `packageManager` field present (i.e., the AC-7 safe-default path lands `yarn-classic` in `package_manager` but the lockfile is actually YAML). Verify S3-03's hand-rolled scanner handles both formats deterministically — outside this story's scope.

## Final verdict

**HARDENED.** Story now satisfies the validator bar:

- Every AC is individually verifiable (binary pass/fail by a third party).
- The AC set collectively guarantees the goal — priority order is pinned (AC-16, AC-17), precondition is pinned (AC-4/5/6 + AC-9 + AC-9b), edge cases enumerated (AC-8 strings + non-string types).
- Every AC has at least one TDD-plan row that would fail under a wrong implementation (mutation-resistance: constant-return, priority-flip, regex-too-loose, constant-warning all caught).
- No AC is a tautology; AC-13 specifically reworded to escape the Rule 9 anti-pattern.
- The story consumes the existing Open/Closed seams (`_LOCKFILE_PRECEDENCE` shape preserved); introduces one new seam (`_BERRY_MARKERS`) at the rule-of-three threshold (parallel to three existing tuples); leaves explicit extension-by-addition paths (one entry in `_BERRY_MARKERS` for future markers; one major-version branch for future variants).
- Domain identifiers typed as `Literal[...]` at one boundary today; StrEnum lift surfaced for the rule-of-three threshold without prescribing it now.
- The implementation is separable from the I/O cleanly enough for unit tests; functional-core opportunity flagged for the implementer without forcing the refactor.

Ready for `phase-story-executor`.
