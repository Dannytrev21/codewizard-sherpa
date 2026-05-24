# Validation report — S7-05 Phase-4 fixture portfolio

**Story:** [`../S7-05-phase4-fixture-portfolio.md`](../S7-05-phase4-fixture-portfolio.md)
**Validated:** 2026-05-24
**Validator:** `phase-story-validator` (automated, scheduled task `story-validation-corrector`)
**Verdict:** **HARDENED** — goal is sound and traces to arch §G1/§G6/§G7/§G11; defects were exclusively at the mechanism layer; in-place edits applied.

## Pipeline summary

| Stage | Outcome |
|---|---|
| 1 — Context loader | Read story + arch §Goals + §"Fixture portfolio" + §Edge cases + §"Cross-cutting test-architecture additions" + High-level-impl §Step 7 + ADRs 0008/0011/0012/0014/0017 + Phase-3 S8-01 (HARDENED) + S8-01 validation report + `tests/fixtures/_shape_test_kernel.py` + `tests/fixtures/README.md` + on-disk state of `tests/fixtures/repos/` (only `express-cve-2024-21501/` (minimal stub) + `malicious-npmrc/`) and `src/codegenie/` (no `rag/` yet — Phase 4 unstarted). |
| 2 — Four parallel critics | Coverage, Test-Quality, Consistency, Design-Patterns subagents spawned in one batch. All returned ≥10 findings each (44 total). |
| 3 — Conditional researcher | **Skipped.** No critic finding was tagged `NEEDS RESEARCH` — the patterns to apply are all repo-precedented (Phase-3 S8-01 manifest, `_shape_test_kernel`, `CveId` newtype, tree-sitter grammar kernel). |
| 4 — Synthesizer + editor | Conflicts resolved by priority `Consistency > Coverage > Test-Quality > Design-Patterns`. Story edited in place via targeted `Edit`s (header / Context / References / Goal / AC block / Implementation outline / TDD plan / Files-to-touch / Out-of-scope / Notes). |

## Conflict resolution log

The four critics largely **agreed** — most findings clustered around the same handful of structural defects, which kept conflicts rare.

- **Coverage [B-2] + [B-3] vs Out-of-scope shape.** Coverage flagged "Story is silent on `tests/e2e/scenarios.yaml` rows" and "silent on `tests/golden/events/`" as block-class — implying ACs should be added. Consistency [H-12] flagged the same gap but framed it as "either add ACs or explicitly out-of-scope them naming the owning story". **Resolution:** Consistency wins (more nuanced). Out-of-scope lines added naming **S7-06** (scenarios.yaml + cassettes + e2e rows) and **S7-07** (replay-lands-RAG event goldens) as owners; the validator's follow-up step is to confirm those stories actually carry the work, escalating via a new story if not. Avoids unilaterally expanding S7-05's scope.
- **Design-Patterns [B-4] sum-type elevation vs Rule 2 / Consistency.** Design-Patterns wanted `FixtureRole = AppLayerCve | ProvenanceRefuse | RagSeed | RetryCassette` mandated. Consistency / Rule 2 says: Phase-3 S8-01 settled on a single `FixtureSpec` shape with optional fields and a sum-type split would fork the convention. **Resolution:** Don't elevate to an AC. Surface as a `Notes for the implementer` paragraph marking "the elevation moment" for whichever Phase-5/6/7 story is the third to add a role-specific manifest field. Three fixtures × four roles is at the rule-of-three threshold, not over it.
- **Test-Quality [B-3] dependency declaration vs Consistency [B-5] dependency declaration.** Both flagged the same defect (`Depends on:` understates real prerequisites). **Resolution:** Merged — `Depends on:` rewritten to enumerate `S4-04`, `S4-01`, Phase-3 S8-01 GREEN, plus soft consumers (S6-02, S5-04, S7-03, S7-06, S7-07).
- **Consistency [B-1] path scheme vs Phase-3 precedent.** Arch uses category-prefixed (`fixtures/vuln-major-bump/*`); Phase-3 S8-01 HARDENED to flat (`tests/fixtures/repos/*`). **Resolution:** Pick flat (Rule 11 — match the more recent hardened convention), surface the arch path as cleanup, preserve the category dimension as a `FixtureSpec.category` field so arch §1014's glob can be expressed via list-comprehension. Don't silently make both layouts coexist.

No other resolution-class conflicts arose.

## Critic findings — full audit log

### Coverage critic (10 findings: 5 block, 5 harden, 4 nit)

- [CO-B-1] cve.yaml premise contradicts Phase-3's `_portfolio.py` precedent (empty template on disk) → addressed by AC-2 (manifest extension); per-fixture `cve.yaml` removed entirely.
- [CO-B-2] Silent on `tests/e2e/scenarios.yaml` Phase-4 rows mandated by High-level-impl §Step 7 → explicit Out-of-scope naming S7-06 owner.
- [CO-B-3] Silent on `tests/golden/events/` JSONL mandated by High-level-impl §Step 7 → explicit Out-of-scope naming S7-07 owner.
- [CO-B-4] `test_lockfiles_are_deterministic` is a same-file-read-twice tautology → removed; inherits Phase-3 S8-01 pinning fence (AC-5).
- [CO-B-5] Jest test count via `text.count("it(")` brittle proxy + no `tsc` baseline test → AC-7 (tree-sitter parse) + AC-8 (`run_external_cli` `tsc --noEmit`).
- [CO-H-1] `min_ts_files: 0` / `min_jest_tests: 0` tautologies for 3 fixtures → removed; thresholds promoted to AC-1 only for the fixtures they apply to.
- [CO-H-2] Embedding-model-mismatch (edge case #19) is Notes-only → AC-11 promoted with `EMBEDDER_MODEL_DIGEST` import.
- [CO-H-3] Provenance-refuse positive AC missing → AC-13 added (fixture-side invariant only; classification is S7-03's job).
- [CO-H-4] Retry-bypass (edge case #11) cassette structural distinctness untested → AC-12 added (typed `CassetteStub`); behavioural assertion remains S6-02's.
- [CO-H-5] tsc baseline AC was prose-only → AC-8 made executable.
- [CO-H-6] No zero-edits-to-Phase-3-fixtures AC → AC-15 added.
- [CO-H-7] No Open/Closed extension AC (S8-01 has AC-8) → AC-3 lifted verbatim.
- [CO-H-8] Goal-vs-arch path mismatch (category prefix) → explicit reconciliation in Context + `category` field on `FixtureSpec`.
- [CO-H-9] No four-section README AC (S8-01 has AC-3) → AC-6 lifted verbatim.
- [CO-H-10] `test_cve_yaml_or_present` silently no-ops on `cve_id is None` → entire `cve.yaml` AC and test removed (replaced by manifest).
- [CO-N-1] "≥60 / ≥100" vs Context "~80 / ~120" 25%/17% under-floor → tightened to ≥70 / ≥105.
- [CO-N-2] `vuln-rag-hit/` category dropped from `express-rerun` path → preserved as `category` field.
- [CO-N-3] `Depends on:` missing Phase-3 manifest precedent → Phase-3 S8-01 GREEN added as hard dep.
- [CO-N-4] AC-10 doesn't call out mypy --strict on manifest → AC-17 made explicit.

### Test-Quality critic (15 findings: 5 block, 11 harden, 4 nit)

- [TQ-B-1] `text.count("it(") + text.count("test(")` brittle substring proxy → tree-sitter parse (AC-7).
- [TQ-B-2] `test_lockfiles_are_deterministic` filesystem-physics tautology → removed; inherits S8-01 pinning fence (AC-5).
- [TQ-B-3] `from codegenie.rag.models import SolvedExample` unrunnable as RED (module doesn't exist) → `Depends on:` adds S4-04; `_validation` notes the executor must confirm at pickup time.
- [TQ-B-4] `min_ts_files: 0` / `min_jest_tests: 0` parametrized assertions vacuous → removed.
- [TQ-B-5] Cassette `len == 2` accepts two empty files → AC-12 typed `CassetteStub` + content discrimination.
- [TQ-H-1] `embedding_model` digest test missing → AC-11.
- [TQ-H-2] tsc invariance test missing → AC-8.
- [TQ-H-3] CVE id raw-`str` comparison instead of newtype → AC-10 `parse_cve_id` at manifest import.
- [TQ-H-4] Smoke loader re-invents file-presence assertions, ignores `_shape_test_kernel.py` → AC-4 mandates kernel delegation.
- [TQ-H-5] `json.loads` instead of `safe_json.load` → AC-4 mandates `safe_json.load(..., max_bytes=..., max_depth=16)`.
- [TQ-H-6] No four-section README ordered test → AC-6.
- [TQ-H-7] No single-source typed manifest → AC-2.
- [TQ-H-8] `yaml.safe_load` instead of `safe_yaml.load` → AC-4 mandates `safe_yaml.load`.
- [TQ-H-9] No semver-bump invariant → AC-9 added (parsed at manifest import; `fixed.lower > vuln.upper` in major).
- [TQ-H-10] Missing property-based test over manifest → AC-4 parametrizes universally over manifest; AC-3 documents Open/Closed property.
- [TQ-H-11] Inline `if spec["package"] not in {"glibc"}` data-as-control-flow → category-based filter via manifest (`spec.category == "vuln-provenance"`).
- [TQ-N-1] `return` instead of `pytest.skip` on no-CVE-id case → entire branch removed (manifest carries `cve_ids: tuple[CveId, ...]`, empty tuple is the absence signal).
- [TQ-N-2] Deferred import → all imports moved to module top.
- [TQ-N-3] AC-1 says "≥60/≥100" vs Context "~80/~120" asymmetry → reconciled (≥70/≥105 with target ~80/~120 documented).
- [TQ-N-4] Test path `tests/unit/fixtures/test_phase4_fixtures_load.py` vs co-located `tests/fixtures/repos/test_phase4_fixtures_load.py` → moved to co-located (Phase-3 precedent).

### Consistency critic (14 findings: 5 block, 8 harden, 3 nit)

- [CN-B-1] Path scheme drops arch's category prefix → reconciled in Context; `category` field on `FixtureSpec`.
- [CN-B-2] `cve.yaml` premise contradicts on-disk reality + Phase-3 precedent → eliminated; manifest extension.
- [CN-B-3] `_portfolio.py` manifest entirely absent → AC-2 + AC-3 + AC-4.
- [CN-B-4] Shared shape kernel not consumed → AC-4 mandates `assert_file_exists` / `_FORBIDDEN_SUBPATHS` / etc.
- [CN-B-5] `Depends on:` understates → rewritten with S4-04, S4-01, Phase-3 S8-01, plus soft S6-02 / S5-04 / S7-03 / S7-06 / S7-07.
- [CN-H-6] `glibc-on-node` AC blends fixture-shape with adapter-behaviour → AC-13 fixture-side only; classification scoped to S7-03 in Out-of-scope.
- [CN-H-7] ADR-0011 retry-bypass structural claim unasserted → AC-12 typed cassette + structural markers; behavioural assertion remains S6-02's (Out-of-scope).
- [CN-H-8] "Four `vuln-major-bump/*`" cardinality mismatch surfaced in Validation notes + Out-of-scope (does not silently add fixtures).
- [CN-H-9] Express fixture cardinality looser than arch (`≥60/≥100` vs `~80/~120`) → ≥70/≥105 floors with target documented.
- [CN-H-10] `mypy --strict` failing on `dict[str, dict[str, Any]]` → AC-17 explicit + manifest is typed.
- [CN-H-11] Notes' embedding_model digest is hidden runtime coupling → AC-11 + `Depends on: S4-01` makes it explicit.
- [CN-H-12] Phase-4 e2e/scenarios + goldens scope gap → explicit Out-of-scope naming S7-06 / S7-07 owners.
- [CN-H-13] Wrong fixture-set claim in Out-of-scope (`four vuln-major-bump/*`) → corrected and cross-linked with the cardinality note.
- [CN-N-14] Synthetic CVE id confusion → Notes-for-implementer paragraph added.
- [CN-N-15] `fixtures/` vs `tests/fixtures/` path normalisation → all references normalized to `tests/fixtures/repos/`.
- [CN-N-16] "Phase-3 fixture pattern shipped" overstated → `Depends on:` now says "Phase-3 S8-01 GREEN" (specific + verifiable).

### Design-Patterns critic (10 findings: 4 block, 6 harden, 3 nit)

- [DP-B-1] Untyped `dict[str, dict[str, Any]]` fixture manifest → AC-2 typed `FixtureSpec` extension.
- [DP-B-2] No Open/Closed extension AC → AC-3.
- [DP-B-3] No `CveId` newtype → AC-10 `parse_cve_id` at manifest import.
- [DP-B-4] Sum-type opportunity (`FixtureRole`) → recorded as `Notes for the implementer` "elevation moment" paragraph; NOT mandated this story (Rule 2; Phase-3 convention coordination cost).
- [DP-H-1] Hidden `Invariant` data buried in primitive thresholds → considered; deferred for the same reason as [DP-B-4]; recorded in Notes.
- [DP-H-2] `SolvedExample.from_yaml` coupling → `Depends on: S4-04` made explicit; Protocol-based decoupling deferred.
- [DP-H-3] Cassette stub schema undefined → AC-12 + `tests/fixtures/repos/_phase4_cassette_stub.py` (typed Pydantic model).
- [DP-H-4] Pure-impure tangle in load test → considered; the rewritten TDD plan has thin shells that delegate to kernel helpers; full functional-core extraction deferred.
- [DP-H-5] Shape-test kernel not consumed → AC-4.
- [DP-H-6] Four-section README discipline not adopted → AC-6.
- [DP-H-7] Critical invariants (embedding_model, deterministic lockfile) in advisory prose → AC-11 + AC-5.
- [DP-H-8] No `_FORBIDDEN_FIXTURE_FILES` per fixture → AC-4 delegates to kernel's `_FORBIDDEN_SUBPATHS` via `assert_no_forbidden_subpath`.
- [DP-N-1] Plugin pattern for invariant validators (registry) → deferred (Rule 2; threshold not met).
- [DP-N-2] `FixtureName` newtype → deferred (ceremony for ~5 uses).
- [DP-N-3] Heuristic Jest count via tree-sitter limitation surfaced → AC-7 + test docstring.

## Story changes — before / after summary

| Block | Before | After |
|---|---|---|
| **Header / Status** | `Ready` | `HARDENED (validated 2026-05-24)` |
| **Depends on** | "S7-04 + Phase-3 fixture pattern shipped (mirror its structure)" | Phase-3 S8-01 GREEN; S4-04; S4-01; S7-04; soft S6-02 / S5-04 / S7-03 / S7-06 / S7-07 |
| **ADRs honored** | 0008, 0011, production-0031 | + 0009, 0012, 0014, 0017 |
| **Validation notes** | absent | 17-bullet structural-changes block + audit-log cross-reference |
| **Context** | "five fixtures + cve.yaml + mirror Phase-3 stub" | + on-disk-reality reconciliation + path-scheme reconciliation + dependency-graph honesty |
| **References** | 8 entries | 18 entries (manifest, kernel, identifiers, parsers, grammar kernel, run_external_cli, tests/contract/, S8-01 + its validation report) |
| **Goal** | "Land five fixtures under `tests/fixtures/repos/` (or wherever) with `cve.yaml`" | "Land five fixtures + five `FixtureSpec` manifest rows; Open/Closed inheritance of Phase-3 fences; tree-sitter Jest count; tsc baseline; embedding-digest pin; typed cassette stubs; no cve.yaml" |
| **Acceptance criteria** | 10 ACs (mostly prose-only file-presence) | 18 ACs (single-source manifest, `CveId` newtype, semver-bump invariant, tree-sitter Jest count, executable tsc baseline, embedding-digest pin, typed cassette stubs, four-section README, kernel delegation, S8-01-fence inheritance, Open/Closed extension, zero-Phase-3-edits, size-cap inheritance, mypy --strict, RED-test discipline) |
| **Implementation outline** | 7 steps starting with "mirror the (empty) Phase-3 stub" | 7 steps starting with "reconcile with on-disk reality, extend the manifest first, build fixtures slowest-first, surface every blocker per Rule 12" |
| **TDD plan — Red** | ~85 LOC of brittle Python (inline FIXTURES, json.loads, substring counts, same-file determinism) | ~170 LOC of typed Python (manifest import, kernel helpers, safe_json/safe_yaml, tree-sitter parse, run_external_cli, parametrize over PORTFOLIO, mutation-resistance checklist) |
| **Out of scope** | 4 bullets | 8 bullets, each naming the owning story for the deferred work (S7-06 / S7-07 / S6-04 / S6-02 / S7-03 / S5-04 cardinality reconciliation) |
| **Notes for implementer** | 6 bullets | 9 bullets including the `FixtureRole` "elevation moment" deferral, synthetic-CVE-id callout, Phase-3 S8-01 GREEN precondition |

## Verdict

**HARDENED.** The story now expresses the same goal — land five Phase-4 fixtures — through the Phase-3-precedented mechanism (typed manifest extension, kernel delegation, Open/Closed extension, executable intent tests instead of brittle proxies). The executor that picks this up has:

- A `Depends on:` line that names every actual prerequisite (no surprise import errors at RED time).
- 18 ACs that are individually verifiable and collectively guarantee the goal.
- A TDD plan that fails RED on a clean tree (because the manifest rows aren't there, not because of unrelated import errors) and walks deterministically to GREEN as fixtures land.
- Explicit Out-of-scope lines naming the owning story for every deferred work item, so nothing silently falls through.
- A `FixtureRole` sum-type deferral note that records when the elevation moment arrives, so the design opportunity isn't lost.

The story is ready for `phase-story-executor`.
