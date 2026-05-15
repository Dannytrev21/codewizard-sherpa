# Validation Report — S5-05 Layer A end-to-end integration

**Date:** 2026-05-15
**Validator:** phase-story-validator skill (Sonnet)
**Story:** `../S5-05-integration-end-to-end.md`
**Verdict:** **HARDENED** — story had real but fixable weaknesses; edits applied; ready for executor.

## Summary

Six **blocking** corrections and ~10 **harden**-class strengthenings landed. The story's goal and structural intent were sound — five integration tests proving Phase 1 exit criteria — but the first-draft ACs were inconsistent with the actual envelope shape, the actual filterability rules for Phase-1 probes, the actual CLI subcommand surface, and the existing `WARM_PATH_CACHE_HIT_PROBES` Open/Closed seam designed specifically for S5-05. Tests would have either failed on correct code or passed by asserting the wrong shape.

After hardening, every AC is individually verifiable, the AC set collectively guarantees the goal, every test in the TDD plan would catch a plausible wrong implementation (mutation-resistance), and the prescribed implementation consumes the existing conftest seams rather than shadowing them.

## Stage 1 — Context Brief

### Story snapshot
- **Goal:** Five integration tests under `tests/integration/probes/` green in CI, asserting Phase 1's load-bearing structural commitments end-to-end through the CLI.
- **Step:** Phase 1, Step 5 (Adversarial corpus + integration end-to-end + fixture portfolio).
- **Depends on:** S5-01, S5-02, S5-03, S5-04 — all hardened, S5-04 with critical "three not five Node-only probes" correction.
- **Out-of-scope:** Golden-file diff (S6-01), bench canaries (S6-02), 90/80 coverage ratchet (S6-02), real-OSS-repo test, workspace-member traversal (Phase 2).

### Phase / arch constraints
- **ADR-0010** — Layer A slices optional at envelope; absence-is-the-contract for filtered probes; "*"-applicability probes (`ci`, `deployment`) may produce empty inner slices on non-Node repos.
- **ADR-0004** — per-probe sub-schema `additionalProperties: false` at slice root; envelope's `probes.*` remains `additionalProperties: true`.
- **ADR-0002** — `ParsedManifestMemo` + `input_snapshot` on `ProbeContext`; cache keys derive from `content_hash` (not live `os.stat`).
- **ADR-0007** — `warnings.id` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Does NOT govern `logger.bind` context keys (relevant to prelude-test AC-PR-4).
- **Phase 0 audit verify command** — `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …`; exit 0 = no mismatches; exit 4 = anchor drift.

### Sibling-family lineage
- **3rd+ concrete consumer** of `WARM_PATH_CACHE_HIT_PROBES`-style closed-set seams (S2-04 memo, S2-05 cache-hit, S5-05 ×5 tests). Rule-of-three threshold REACHED — `PHASE_1_PROBE_NAMES` and `PHASE_1_PROBE_TO_SLICE` kernel extraction is mandatory, lifted to conftest.
- **Prior validation framings carried forward:** S5-04 established the "three not five Node-only probes" rule + the typed `_FILE_SPECS` closed-set pattern; S2-05 established the four-redundant-signals warm-path metamorphic pair + the asymmetric scandir-counter.

### Phase exit criteria the story must contribute to
- Exit #1 — Useful `repo-context.yaml` on a real Node.js repo → `test_layer_a_end_to_end.py`
- Exit #2 — Cache hits on second run (all six probes) → `test_cache_hit_on_real_repo.py` extension
- Exit #3 — Schema validation passes → all five tests via `codegenie.schema.validator.validate`
- Exit (Scenario 4) — Non-Node repo gathers cleanly with only `language_stack` → `test_non_node_repo.py`
- Phase 0 Gap-#4 prelude pass → `test_coordinator_prelude.py`

### Open ambiguities (resolved during validation)
- ✅ Envelope shape (`probes[probe_name][slice_key]`) — resolved against `test_cache_hit_on_real_repo.py:207` ground truth.
- ✅ Slice key names per probe — resolved against `src/codegenie/schema/probes/*.schema.json`.
- ✅ `codegenie audit verify` vs `codegenie verify-anchor` — resolved against `src/codegenie/cli.py:692-727`.
- ✅ `applies_to_languages` for ci/deployment — resolved against probe source code + S5-04 validation.
- ✅ `monorepo.markers` field name — resolved against `language_detection.schema.json:38-43`.

## Stage 2 — Critic findings (synthesized)

Four critics ran in parallel: Coverage, Test Quality, Consistency, Design Patterns. Their findings are merged below by issue. Severity priority resolution: **Consistency > Coverage > Test-Quality > Design-Patterns** (per skill reference).

### Blocking — applied

**B1. Probe-name vs slice-name conflation throughout AC-1, AC-3, AC-4, AC-5 + the TDD red snippet.**
- *Where (before):* `PHASE_1_SLICES = ("language_stack", "build_system", "manifests", "ci", "deployment", "test_inventory")` then `for slice_name in PHASE_1_SLICES: assert slice_name in probes`.
- *Source of truth:* `envelope["probes"]` is keyed by probe NAME; the slice key is nested. `tests/integration/probes/test_cache_hit_on_real_repo.py:207`: `envelope["probes"]["language_detection"]["language_stack"]`. Schema files confirm slice keys: `language_detection→language_stack`, `node_build_system→build_system`, `node_manifest→manifests`, `ci→ci`, `deployment→deployment`, `test_inventory→test_inventory`.
- *Fix applied:* Introduced `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` in conftest (AC-INFRA-1). All ACs rewritten to use explicit `probes[probe_name][slice_key]` paths. TDD red snippet rewritten. Pure helper `assert_phase_1_slices_present` enforces the correct shape (AC-INFRA-4).

**B2. "Five Node-only probes" → "three Node-only probes" (consistency drift across Context, AC-3, AC-3(v), outline #3, Notes).**
- *Where (before):* "Phase 1's Node-only probes are filtered out by `Registry.for_task`" / "the five Phase-1 Node probes filtered out".
- *Source of truth:* `src/codegenie/probes/ci.py` and `deployment.py` declare `applies_to_languages = ["*"]` — run on every repo. Only three probes are language-filtered: `node_build_system`, `node_manifest`, `test_inventory`. S5-04 validation made this explicit.
- *Fix applied:* Every "five" → "three"; ACs distinguish absent (Node-only) from ran-but-empty (ci/deployment). `assert_only_language_stack` helper enforces both shapes per ADR-0010.

**B3. `codegenie verify-anchor` is not a real subcommand.**
- *Where (before):* AC-1(iv) + Implementation outline #1.
- *Source of truth:* `src/codegenie/cli.py:692-727` — actual subcommand is `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …`; exit 0 = success, exit 4 = mismatch.
- *Fix applied:* AC-E2E-4 rewritten with full `CliRunner` invocation; TDD snippet includes the call.

**B4. Cache-hit extension prescribes editing the wrong file (bypasses Open/Closed seam).**
- *Where (before):* Implementation outline #2 — "Replace the literal `{"language_detection", "node_build_system"}` set with [six-element set]" in `test_cache_hit_on_real_repo.py`.
- *Source of truth:* `tests/integration/probes/conftest.py:90` declares `WARM_PATH_CACHE_HIT_PROBES: Final[frozenset[str]]` with the explicit docstring "S5-05 extends to all six Layer-A probes by adding entries here — **zero** edits to any test function body." (Open/Closed at the file boundary; CLAUDE.md "Extension by addition".)
- *Fix applied:* Outline #2 rewritten to extend the conftest frozenset. AC-INFRA-2 prohibits function-body edits in `test_cache_hit_on_real_repo.py` (only docstring update, slice-content invariance extension, test renames are permitted).

**B5. Misleading "verify whether test_inventory needs its own monkeypatch" speculation.**
- *Where (before):* Implementation outline #2 — speculated that `test_inventory.py`'s `os.walk` may need its own scandir monkeypatch.
- *Source of truth:* On the cache-hit path, **the coordinator never invokes `probe.run()`** — it returns the cached `ProbeOutput` directly. No probe walks the filesystem on warm. The scandir counter at `codegenie.probes.language_detection.os.scandir` namespace is correctly asymmetric to LD only; load-bearing signals for the other 5 probes are `probe.cache_hit` event + cache_key byte-equality (S2-05's four-signal redundancy).
- *Fix applied:* AC-CH-4 made this asymmetry explicit; outline #2 deleted the speculative paragraph.

**B6. `_stub_node_version_check` helper never referenced — environment-dependent flake guaranteed.**
- *Where (before):* No mention in any AC or outline step.
- *Source of truth:* `tests/integration/probes/conftest.py:194-224` documents and exports the helper; `test_cache_hit_on_real_repo.py:134` uses it. Without it, `NodeBuildSystemProbe`'s `node --version` cross-check emits `node.version_declared_resolved_disagree` whenever installed Node ≠ fixture's `.nvmrc`.
- *Fix applied:* Every test that gathers a Node fixture (`test_layer_a_end_to_end`, `test_monorepo_turbo`, `test_coordinator_prelude`, failure-isolation) now calls `_stub_node_version_check(monkeypatch)`. TDD snippets show the call.

### Harden — applied

**H1. `run_gather` fixture is fictional; canonical pattern is `_invoke_gather`.**
- *Fix applied:* `_invoke_gather` promoted from module-local in `test_cache_hit_on_real_repo.py` to a top-level conftest helper (AC-INFRA-3). Rule of three met (cache-hit cold + warm + S5-05 ×5 = 7+ call sites). `--no-gitignore` flag remains load-bearing.

**H2. Truthy-only slice check (`assert probes[slice_name]`) is mutation-weak.**
- *Fix applied:* AC-E2E-2 + AC-CH-5 add per-slice value pins (`framework_hints == ["express"]`, `package_manager == "pnpm"`, etc.). Reuses S2-05's existing value pins on the same fixture.

**H3. No metamorphic partner / negative path for end-to-end test.**
- *Fix applied:* AC-NEG-1 (schema additionalProperties:false enforcement) added inside `test_layer_a_end_to_end.py`. AC-ERR-1 (probe failure isolation) added as a sibling test/function. Combined with the per-slice value pins, the end-to-end test now resists trivially-wrong implementations.

**H4. Prelude test relies on causally-fragile timestamp ordering.**
- *Fix applied:* AC-PR-2 promotes the structural snapshot observation (a Wave-2 event carries `detected_languages` from the enriched snapshot) to the PRIMARY signal. AC-PR-3 keeps timestamp ordering as redundant secondary. AC-PR-4 surfaces an explicit "S1-07 follow-up if coordinator bind missing" pathway.

**H5. Test name `test_two_probes_cache_hit_on_second_run` will lie after extension.**
- *Fix applied:* AC-CH-7 renames to `test_warm_path_probes_cache_hit_on_second_run` and the metamorphic partner identically. Module docstring updated.

**H6. Closed-set sharing — local `PHASE_1_SLICES` tuple in test file is design debt.**
- *Fix applied:* AC-INFRA-1 lifts `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` to conftest with a module-load `assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES` invariant. Phase 2's 7th probe must update both atomically — refusing to load otherwise (fail-loud per CLAUDE.md Rule 12).

**H7. Pure shape-assertion helpers not extracted (rule of three crosses with S6-01).**
- *Fix applied:* AC-INFRA-4 adds `assert_phase_1_slices_present`, `assert_only_language_stack`, `assert_monorepo_markers` as pure helpers in conftest. Functional core / imperative shell. Reused by S6-01.

**H8. Audit-record string compare vs typed enum (primitive obsession).**
- *Fix applied:* AC-NN-5 requires `ProbeExecution(record["execution"]) == ProbeExecution.Skipped` (typed round-trip). Catches audit-serializer drift + primitive-obsession mutants.

**H9. Registry-filter coupling not asserted.**
- *Fix applied:* AC-NN-6 asserts `set(envelope["probes"].keys()) == {p.name for p in Registry.for_task(task, languages={"go"})}`. Catches a renamed-fixture mutant.

**H10. PR-body grep contract not test-enforced.**
- *Fix applied:* AC-E2E-5 + an in-module `test_phase_1_exit_criterion_docstring_present` test asserts the literal line is in `__doc__`. A refactor that drops the docstring now fails the test.

**H11. AC-7 walltime ("developer's machine") non-deterministic.**
- *Fix applied:* Reframed as AC-DOD-2 (Definition of Done) anchored to `ubuntu-latest` CI runner; `test_layer_a_end_to_end` carries `@pytest.mark.timeout(15)` as CI-enforced ceiling.

**H12. `markers` field name hedged ("or whatever the S2-01 sub-schema names the field").**
- *Fix applied:* Schema confirmed (`language_detection.schema.json:32-43`); AC-MR-2 pins `markers` directly and uses `assert_monorepo_markers(expected_markers=["package.json", "turbo.json"])` (sorted union per schema description).

### Nits — applied

- "Confirm at land-time" hedges removed where the source of truth is on disk now.
- Relative `Path("tests/fixtures/...")` paths replaced with `FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"` (mirrors S2-05 line 77).
- Python 3.11/3.12 matrix AC moved to Definition of Done.

## Stage 3 — Research

**Skipped.** No critic findings tagged `NEEDS RESEARCH`. Every issue resolved against codebase ground truth (sibling validated stories, conftest helpers, schema files, CLI surface).

## Stage 4 — Edits applied

The story file `S5-05-integration-end-to-end.md` was edited in place:

1. **Status:** `Ready` → `Ready (HARDENED 2026-05-15)`.
2. **ADRs honored** expanded with ADR-0007 + Phase 0 ADR-0006 (audit verify exit codes).
3. **Validation notes block** added under the header documenting every change.
4. **Context** rewritten: corrected slice-key vs probe-key paths; "five Node-only" → "three Node-only"; `WARM_PATH_CACHE_HIT_PROBES` referenced as the extension seam; structural prelude signal called out as primary.
5. **Acceptance criteria** rewritten end-to-end into 8 grouped sections (`INFRA-`, `E2E-`, `CH-`, `NN-`, `MR-`, `PR-`, cross-cutting `NEG-`/`ERR-`, `DOD-`) with 30 individual ACs replacing the first-draft's 8 unstructured ACs.
6. **Implementation outline** rewritten with explicit landing order (conftest first), correct CLI invocations, correct helper references, and a documented coordinator-bind fallback for AC-PR-2.
7. **TDD plan red snippets** rewritten with correct envelope-shape access, value pins, audit verify CliRunner invocation, negative-path schema mutation, structural prelude observation, fixture-root pattern.
8. **Files to touch** table expanded — added conftest extensions, `test_failure_isolation.py`, possible coordinator extension, possible pyproject.toml dep addition.
9. **Notes for the implementer** rewritten — load-bearing commitments section, design-pattern guidance section, process / PR hygiene section.

## Final verdict — HARDENED

The story is ready for `phase-story-executor`. After hardening:

- Every AC is individually verifiable.
- The AC set collectively guarantees the goal (five integration tests proving Phase-1 exit criteria).
- Every test in the TDD plan has a mutation-resistance signal — truthy-only checks replaced with value pins; positive paths paired with negative paths (schema additionalProperties, probe failure isolation); timestamp ordering supplemented with structural snapshot observation.
- No contradictions with `phase-arch-design.md`, ADR-0010, ADR-0004, ADR-0002, ADR-0007, or any landed CLAUDE.md commitment.
- Critical edge cases listed: empty repo (S2-05 covers indirectly), non-Node, monorepo, schema negative path, probe error isolation.
- The prescribed implementation consumes existing kernels (`WARM_PATH_CACHE_HIT_PROBES`, `_stub_node_version_check`, `_invoke_gather`, `_copy_tree`, `_load_envelope`) and extracts new ones at the rule-of-three threshold (`PHASE_1_PROBE_NAMES`, `PHASE_1_PROBE_TO_SLICE`, three pure shape helpers). No "edit the kernel" cliffs left for Phase 2's seventh probe — adding it is a two-line frozenset/mapping update + automatic test pickup.
- Domain identifiers (probe names, slice keys, `ProbeExecution` variants) are typed at boundaries — frozensets/MappingProxyType for closed sets, enum round-trip for execution variants.
- Pure logic separable from I/O (`assert_*` helpers are pure; `_invoke_gather` + `_copy_tree` are the imperative shell).
- Data shapes don't permit illegal combinations — the conftest module-load `assert` invariant refuses to load if the two frozensets drift.

The S1-07 coordinator-bind dependency for AC-PR-2 is the one optional in-scope coordinator extension; flagged as a PR-body follow-up if needed, not a contract amendment.
