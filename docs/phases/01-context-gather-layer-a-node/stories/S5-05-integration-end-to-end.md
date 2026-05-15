# Story S5-05 — Layer A end-to-end integration + cache-hit-all-six + non-Node + prelude pass

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** M
**Depends on:** S5-01, S5-02, S5-03, S5-04
**ADRs honored:** ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0010 (Layer A slices optional at envelope), ADR-0002 (`ParsedManifestMemo` + `input_snapshot` on `ProbeContext`), ADR-0007 (warning ID pattern — assertions on `warnings[]` content honor the pattern), [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-cli-exit-code-policy.md) (audit verify exit-code policy)

## Validation notes (2026-05-15 — phase-story-validator)

This story is the **convergence point** of Phase 1's integration testing (5 end-to-end CLI tests proving the roadmap exit criteria). Validation surfaced six blocking corrections versus the first-draft + multiple harden-class strengthenings. All in place; no scope changes.

Key corrections versus the first-draft story:

- **Envelope shape: probe-name keys, slice-key nesting.** First-draft AC-1 + the TDD red snippet conflated probe names with slice keys (`PHASE_1_SLICES = ("language_stack", "build_system", "manifests", ...)` then `assert slice_name in probes` — wrong; `probes` is keyed by probe NAME (`language_detection`, `node_build_system`, ...), and the slice is the nested key inside). Verified via `tests/integration/probes/test_cache_hit_on_real_repo.py:207` (`envelope["probes"]["language_detection"]["language_stack"]`) and every Phase-1 schema file (e.g., `node_build_system.schema.json` declares `"required": ["build_system"]` under the slice root). New ACs and the TDD red snippet now use both a probe-name set AND a probe→slice mapping; the per-slice expected values are pinned (e.g., `framework_hints == ["express"]`, `package_manager == "pnpm"`) to kill the truthy-only-check mutant class (Rule 9).
- **"Five Node-only probes" → "three Node-only probes."** Source-of-truth code (`src/codegenie/probes/ci.py`, `deployment.py`) shows `CIProbe` and `DeploymentProbe` declare `applies_to_languages = ["*"]` — they run on **every** repo, including non-Node. Only **three** Phase 1 probes are language-filtered: `node_build_system`, `node_manifest`, `test_inventory`. The first-draft `test_non_node_repo.py` AC asserting `ci`/`deployment` absent would have failed on correct code. ACs and Notes rewritten to: three Node-only probes recorded `ProbeExecution.Skipped`; `ci`/`deployment` probes ran-but-produced-empty slices (ADR-0010 permits both shapes).
- **CLI subcommand name corrected.** First-draft said `codegenie verify-anchor`. Source-of-truth (`src/codegenie/cli.py:692-727`) shows the actual subcommand is `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` (exit 0 = no mismatches; exit 4 = anchor drift). AC-1(iv) and the TDD red snippet now invoke the correct command via `CliRunner`.
- **Cache-hit extension uses the existing Open/Closed seam.** The conftest at `tests/integration/probes/conftest.py:90` declares `WARM_PATH_CACHE_HIT_PROBES: Final[frozenset[str]]` with a docstring explicitly designed for S5-05 to extend "with zero edits to any test function body" (Open/Closed at the file boundary; CLAUDE.md "Extension by addition"). First-draft Implementation outline #2 said "Replace the literal `{"language_detection", "node_build_system"}` set with [six-element set]" — but that literal does not exist in `test_cache_hit_on_real_repo.py`; it's the named frozenset in `conftest.py`. Outline #2 rewritten: edit one line in `conftest.py`; do not edit any test function body. The misleading "verify whether `test_inventory` needs its own monkeypatch" speculation removed (on the cache-hit path, `probe.run()` is never invoked — coordinator short-circuits — so the scandir counter is correctly asymmetric to LD only; load-bearing signals for the other 5 probes are `probe.cache_hit` event count + cache_key byte-equality).
- **`_stub_node_version_check` referenced.** First-draft never named the existing conftest helper for neutralizing the env-dependent `node.version_declared_resolved_disagree` warning. Every test that gathers `node_typescript_helm` or `node_monorepo_turbo` (i.e., four of the five tests) now calls `_stub_node_version_check(monkeypatch)` (mirrors `test_cache_hit_on_real_repo.py:134`). Without this, the tests flake whenever CI Node version drifts from the fixture's `.nvmrc` pin.
- **Canonical CLI invocation pattern pinned.** First-draft mentioned a `run_gather` pytest fixture that does not exist. The actual canonical pattern lives in `test_cache_hit_on_real_repo.py:80-86`: a module-local `_invoke_gather(repo)` using `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` (the `--no-gitignore` flag is load-bearing — avoids TTY-prompt coupling). Story now promotes `_invoke_gather` + `_load_envelope` from conftest helpers to the explicit pattern.

Key strengthenings:

- **Prelude test: structural metamorphic invariant.** First-draft AC-5 relied on timestamp-index ordering of structlog `probe.start` / `probe.success` events — causally fragile under asyncio (a coordinator that dispatches Wave-2 with an empty/None snapshot but completes LD-success-log before any Wave-2-start-log passes by luck). Replaced primary signal with a **non-temporal** invariant: a Wave-2 probe (use `NodeBuildSystemProbe`) emits `coordinator.wave_2.dispatch` (or `probe.start`) carrying `detected_languages` derived from the enriched snapshot; the test asserts the field is present and non-empty. Timestamp ordering downgraded to a redundant secondary check.
- **Schema negative-path AC added.** ADR-0004's `additionalProperties: false` is load-bearing; first-draft tested only positive validation. AC-NEG-1 added: synthesize an envelope with an unknown key under one slice; re-validate; assert `SchemaValidationError`.
- **Probe error-path AC added.** Phase 1's failure-isolation commitment (one probe fails → gather exits 0; other slices populate; audit records the error) was untested. AC-ERR-1 added: monkeypatch one probe's `run()` to raise; assert exit 0, five other slices populate, audit record shows `ProbeExecution` error state.
- **Shared frozensets promoted to conftest.** `PHASE_1_PROBE_NAMES` and `PHASE_1_PROBE_TO_SLICE` added to `tests/integration/probes/conftest.py`. After S5-05 lands, `WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES`; conftest asserts this invariant at module load. Test files iterate the conftest constants — never re-declare slice/probe lists locally.
- **Pure shape-assertion helpers extracted.** `assert_phase_1_slices_present(envelope)`, `assert_only_language_stack(envelope)`, `assert_monorepo_markers(envelope, expected)` added to conftest (functional core / imperative shell). Each helper raises `AssertionError` with a structured diff. Reused by S6-01 (golden-file regen) — rule-of-three met across S5-05 ×3 + S6-01.
- **Test rename.** `test_two_probes_cache_hit_on_second_run` → `test_warm_path_probes_cache_hit_on_second_run` (probe-count agnostic — survives Phase 2 additions). Metamorphic partner renamed identically. Module docstring updated.
- **Audit-record comparisons go through the typed enum.** AC-3(v) now requires `ProbeExecution(record["execution"]) == ProbeExecution.Skipped` (round-trip), never raw string compare — kills the primitive-obsession class of mutants.
- **`monorepo.markers` field name pinned.** First-draft hedged ("or whatever the S2-01 sub-schema names the field"). Schema file confirmed: `monorepo.markers` (sorted union of hit marker filenames).
- **Walltime budget reframed.** AC-7 (30s) was non-deterministic ("developer's machine"). Moved to Definition-of-Done with CI-baseline anchor (`ubuntu-latest`); `test_layer_a_end_to_end` carries `@pytest.mark.timeout(15)` as a CI-enforced ceiling.

Validation report: [`_validation/S5-05-integration-end-to-end.md`](_validation/S5-05-integration-end-to-end.md).

## Context

This story lands the five integration tests that make the **roadmap Phase 1 exit criteria** demonstrably green in CI. Each test runs `codegenie gather` end-to-end through the CLI against a fixture and asserts a load-bearing structural property.

- `test_layer_a_end_to_end.py` — **roadmap exit criterion #1**: "useful `repo-context.yaml` produced on a real Node.js repo" — proxied by `node_typescript_helm`. All six Phase-1 probe entries present under `probes`, each with its declared slice populated and value-pinned; envelope + six sub-schemas pass `codegenie.schema.validator.validate`; `codegenie audit verify` re-computes the audit anchor successfully (exit 0).
- `test_cache_hit_on_real_repo.py` — **roadmap exit criterion #2** extension: gather twice; **all six** Phase-1 probes report `ProbeExecution.CacheHit` on the second run. S2-05 covered two probes; this story extends to six by adding the four remaining names to `WARM_PATH_CACHE_HIT_PROBES` in `conftest.py` — zero edits to any test function body (Open/Closed at the file boundary; see Validation notes). The four S2-05 redundant signals (cache-hit event, no-success-with-cache_key, cache_key byte-equality, asymmetric scandir==0) all hold; per-slice content invariance extends to the four new slices.
- `test_non_node_repo.py` — ADR-0010 contract test: a Go-only repo produces an envelope with `language_stack` populated and the **three** Node-only probes (`node_build_system`, `node_manifest`, `test_inventory`) filtered out by `Registry.for_task`; `ci` and `deployment` probes (`applies_to_languages = ["*"]`) **run** but produce empty / no-evidence slices — both ADR-0010-compliant shapes. Audit run-record shows `ProbeExecution.Skipped` for the three Node-only probes (typed enum compare).
- `test_monorepo_turbo.py` — `probes.language_detection.language_stack.monorepo` populated when the fixture has both `turbo.json` and `package.json#workspaces` (`monorepo.tool == "turbo"`, `monorepo.markers == ["package.json", "turbo.json"]` — sorted union per schema); the root-level `probes.node_build_system.build_system` slice produced (workspace-member traversal is Phase 2's concern, not asserted here).
- `test_coordinator_prelude.py` — Phase 0 Gap-#4 + Phase 1 reinforcement: Wave-1 `LanguageDetectionProbe` completes before Wave-2 dispatch (secondary timestamp signal), and — **primary, non-temporal signal** — a Wave-2 probe (`NodeBuildSystemProbe`) emits a `probe.start` (or coordinator `coordinator.wave_2.dispatch`) event whose bound payload carries `detected_languages` derived from the enriched snapshot (non-empty; contains `javascript` or `typescript`). The structural invariant survives async event-interleaving race conditions; the timestamp check is kept as redundant belt-and-suspenders.

This is the convergence point of Step 5: S5-01/-02/-03 prove the defenses; S5-04 ships the fixture portfolio; this story exercises the whole stack end-to-end.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` — Phase 1 exit criteria.
  - `../phase-arch-design.md §"Scenarios"` Scenario 1 (cold gather), Scenario 2 (warm cache hit), Scenario 4 (non-Node) — the runtime paths this story asserts.
  - `../phase-arch-design.md §"Testing strategy" → "Integration tests"` — the five-test inventory.
  - `../phase-arch-design.md §"Component design" — Coordinator prelude pass`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — the envelope + six sub-schemas all pass validation.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — the non-Node case validates with only `language_stack`.
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo seam is what makes the warm-path test green.
- **Source design:**
  - `../final-design.md §"Test plan"` → "Integration tests" — the canonical five-test list.
  - `../final-design.md §"Failure modes & recovery"` — informs negative-case integration coverage.
  - `../High-level-impl.md §"Step 5"` — integration-test list with assertions.
- **Existing code (lands earlier — must be on disk before this story starts):**
  - All six Layer A probes (S2-01 + S2-02 + S3-05 + S4-01 + S4-02 + S4-03).
  - All five fixtures (S2-03, S3-06 ×2, S5-04 ×2).
  - Coordinator prelude pass (S1-07 + S1-08 wiring).
  - `tests/integration/probes/test_cache_hit_on_real_repo.py` (S2-05) — this story **extends** the existing file, not creates anew.
- **Style reference:** `../../00-bullet-tracer-foundations/stories/S4-02-cli-gather-audit-verify.md` (Phase 0 integration-test pattern + style).

## Goal

Five integration tests under `tests/integration/probes/` are green in CI, asserting Phase 1's load-bearing structural commitments end-to-end through the CLI against the fixture portfolio.

## Acceptance criteria

Each AC is **individually verifiable** (a third party can run a check and get binary pass/fail). ACs prefixed `E2E-` apply to `test_layer_a_end_to_end.py`; `CH-` to `test_cache_hit_on_real_repo.py`; `NN-` to `test_non_node_repo.py`; `MR-` to `test_monorepo_turbo.py`; `PR-` to `test_coordinator_prelude.py`; `NEG-` / `ERR-` are cross-cutting negative-path ACs; `INFRA-` covers conftest extensions; `DOD-` is Definition-of-Done.

### Shared conftest extensions (Open/Closed seam)

- [ ] **AC-INFRA-1 — Promoted closed sets in `tests/integration/probes/conftest.py`.** Two new `Final[frozenset[str]]` constants added next to the existing `WARM_PATH_CACHE_HIT_PROBES`:
  - `PHASE_1_PROBE_NAMES = frozenset({"language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"})`
  - `PHASE_1_PROBE_TO_SLICE: Final[Mapping[str, str]] = MappingProxyType({"language_detection": "language_stack", "node_build_system": "build_system", "node_manifest": "manifests", "ci": "ci", "deployment": "deployment", "test_inventory": "test_inventory"})`

  Plus a module-load-time invariant: `assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES, "S5-05 must extend the warm-path frozenset to all Phase-1 probes"`. Adding a 7th Phase-2 probe = one frozenset insertion + one mapping entry; zero edits to any of the five S5-05 test bodies.
- [ ] **AC-INFRA-2 — `WARM_PATH_CACHE_HIT_PROBES` extended in `conftest.py`** to `frozenset({"language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"})`. **Zero** edits to test function bodies in `test_cache_hit_on_real_repo.py` (the file iterates the frozenset; the seam was designed for this — see conftest docstring lines 47-48). Only permitted edits to the cache-hit test file: (a) module docstring update to reflect six-probe scope; (b) extension of the per-probe slice-content invariance block (lines 206-215) to cover the four added slices; (c) test rename (AC-CH-7).
- [ ] **AC-INFRA-3 — `_invoke_gather` promoted to a shared module-level helper in `conftest.py`.** Currently lives as a module-local in `test_cache_hit_on_real_repo.py`. Rule of three met (cache-hit cold + warm + five S5-05 tests = 7+ call sites). Signature: `def _invoke_gather(repo: Path) -> click.testing.Result`. The `--no-gitignore` flag remains load-bearing (avoids TTY-prompt coupling). All five S5-05 tests import + use it.
- [ ] **AC-INFRA-4 — Pure shape-assertion helpers extracted to `conftest.py`** (functional core / imperative shell):
  - `assert_phase_1_slices_present(envelope: Mapping[str, Any]) -> None` — every probe in `PHASE_1_PROBE_NAMES` is present under `envelope["probes"]` with its declared slice key non-empty. Raises `AssertionError` with a structured diff (which probe / slice failed).
  - `assert_only_language_stack(envelope: Mapping[str, Any]) -> None` — `language_detection` is present with `language_stack`; the three Node-only probe keys are absent; `ci` / `deployment` may be present with empty slices.
  - `assert_monorepo_markers(envelope: Mapping[str, Any], *, expected_tool: str, expected_markers: Sequence[str]) -> None` — `probes.language_detection.language_stack.monorepo` is non-null and matches the expected `tool` + sorted-union `markers`.

  Each helper is pure (input → assertion; no I/O). Reused by S6-01's golden-file regen test.

### `test_layer_a_end_to_end.py` — exit criterion #1

- [ ] **AC-E2E-1 — File exists; cold gather on `node_typescript_helm`.** Test creates a hermetic copy of `tests/fixtures/node_typescript_helm/` under `tmp_path` via `_copy_tree`; calls `_stub_node_version_check(monkeypatch)` (mirrors S2-05; without it the `node.version_declared_resolved_disagree` warning fires on CI); invokes `_invoke_gather(repo)`; asserts `result.exit_code == 0`.
- [ ] **AC-E2E-2 — All six probe entries present, each slice non-empty, value-pinned.** After loading via `_load_envelope(repo)`, call `assert_phase_1_slices_present(envelope)`. Beyond the presence check, pin per-slice load-bearing fields (mutation-killing assertions — Rule 9):
  - `probes.language_detection.language_stack.primary == "typescript"` (or the value the S2-03 fixture canonically declares; cross-reference S2-03's hardened ACs at land-time and pin).
  - `probes.language_detection.language_stack.framework_hints == ["express"]` (reuses S2-05's value pin).
  - `probes.node_build_system.build_system.package_manager == "pnpm"` (reuses S2-05's value pin).
  - `probes.node_manifest.manifests` is non-empty with at least one entry referencing `package.json`.
  - `probes.ci.ci.providers` contains at least one entry (the S2-03 fixture ships a GitHub Actions workflow per `phase-arch-design.md §"Fixture portfolio"`).
  - `probes.deployment.deployment.manifests` contains at least one entry (Helm Chart.yaml + values).
  - `probes.test_inventory.test_inventory.framework_hints` contains the framework the S2-03 fixture declares.
- [ ] **AC-E2E-3 — Envelope + per-probe sub-schemas validate via the production seam.** Call `codegenie.schema.validator.validate(envelope)` (the production seam used by S2-05 line 244). Do **not** hand-roll a `Draft202012Validator` against a relative `Path("src/codegenie/schema/...")` — fragile to test cwd and bypasses the production composer. The validator already composes the envelope + six per-probe sub-schemas via `$ref`.
- [ ] **AC-E2E-4 — Audit anchor re-computes via the real CLI subcommand.** Inside the test, after the cold gather, invoke `CliRunner().invoke(cli, ["audit", "verify", "--runs-dir", str(repo / ".codegenie" / "context" / "runs"), "--cache-dir", str(repo / ".codegenie" / "cache"), "--yaml-path", str(repo / ".codegenie" / "context" / "repo-context.yaml")])`; assert `result.exit_code == 0` (no anchor mismatches). The subcommand is `codegenie audit verify` (NOT `codegenie verify-anchor`); exit-code policy per `src/codegenie/cli.py:716-727`.
- [ ] **AC-E2E-5 — Docstring-as-contract enforced by an in-module test.** The module's `__doc__` contains the literal line `"Phase 1 exit criterion #1: GREEN — all six probe entries populated, envelope + 6 sub-schemas validated."` (grep-able for the Step 6 PR-body close-out). A trivial `test_phase_1_exit_criterion_docstring_present` in the same module imports its own `__doc__` and asserts via `assert "Phase 1 exit criterion #1: GREEN" in __doc__`. A well-meaning future refactor that drops the docstring now fails the test, not silently breaks Step 6.

### `test_cache_hit_on_real_repo.py` — exit criterion #2 (extension)

- [ ] **AC-CH-1 — All six probes emit exactly one `probe.cache_hit` event on the warm run.** The existing test body (S2-05 hardened) iterates `WARM_PATH_CACHE_HIT_PROBES`; after AC-INFRA-2's frozenset extension the assertion automatically covers six probes. Assertion is `set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES` (= `PHASE_1_PROBE_NAMES`).
- [ ] **AC-CH-2 — Cache-key byte-equality cold↔warm for all six probes.** Existing `_coordinator_success_keys`-based loop already iterates the frozenset; verifies for each probe `warm_hits[probe]["cache_key"] == cold_keys[probe]`. ADR-0002 derives cache keys from `content_hash`; this assertion proves cache-key invariance directly for the new four probes.
- [ ] **AC-CH-3 — Zero coordinator-side `probe.success(cache_key)` events on warm for any of the six.** Variant pin: existing rogue-success filter (S2-05 AC-12) already iterates the frozenset; coverage automatically extends.
- [ ] **AC-CH-4 — `os.scandir` zero-invocations on warm path (asymmetric, LD-specific).** Existing assertion on the module-local scandir counter at `codegenie.probes.language_detection.os.scandir` namespace remains the load-bearing signal for `LanguageDetectionProbe`. The four added probes do **not** call `os.scandir` directly at their own module namespace (`node_build_system` uses `Path.exists`; `node_manifest` uses memo + lockfile parsers; `ci` uses `Path.glob`; `deployment` uses `Path.rglob`; `test_inventory` uses `os.walk` — internal to `os`, not at `codegenie.probes.test_inventory.os.scandir`). On the cache-hit path **no probe's `run()` is invoked** (coordinator short-circuits via cache lookup); no additional monkeypatches are needed or appropriate. The load-bearing signals for the added four are AC-CH-1 + AC-CH-2 + AC-CH-3.
- [ ] **AC-CH-5 — Slice-content invariance extended to the new four slices.** The existing block (S2-05 AC-14/AC-15, lines 206-224) value-pins LD and NBS slice contents. Extend to pin one load-bearing field per added slice (mutation-killing per Rule 9): `nm = envelope["probes"]["node_manifest"]; assert nm["manifests"]["primary"] == "package.json"`; `ci_slice = envelope["probes"]["ci"]; assert ci_slice["ci"]["providers"]` non-empty; `dp = envelope["probes"]["deployment"]; assert dp["deployment"]["manifests"]` non-empty; `ti = envelope["probes"]["test_inventory"]; assert ti["test_inventory"]["unit_test_count_is_file_count"] is True`. Cross-check the actual S4-03/S4-02/S4-01 schema-required fields at land-time and use one canonical pinned value per probe.
- [ ] **AC-CH-6 — Metamorphic partner extended.** `test_two_probes_cache_miss_on_tracked_input_edit` (existing) iterates `WARM_PATH_CACHE_HIT_PROBES` and asserts a cache-key change for each. After AC-INFRA-2's extension, the metamorphic invariant automatically covers six probes. No code edits to the test body required; only the rename (AC-CH-7).
- [ ] **AC-CH-7 — Test rename for honesty.** `test_two_probes_cache_hit_on_second_run` → `test_warm_path_probes_cache_hit_on_second_run`; `test_two_probes_cache_miss_on_tracked_input_edit` → `test_warm_path_probes_cache_miss_on_tracked_input_edit`. Module docstring header `S2-05 — two-probe warm-path cache-hit metamorphic pair` → `S2-05 + S5-05 — warm-path cache-hit metamorphic pair (all Phase-1 probes via WARM_PATH_CACHE_HIT_PROBES)`. The name lying about cardinality is design debt; rename now while the file is being touched.

### `test_non_node_repo.py` — ADR-0010 contract test

- [ ] **AC-NN-1 — File exists; gather on `non_node_go` exits 0.** Test copies the fixture under `tmp_path`, invokes `_invoke_gather(repo)`, asserts `result.exit_code == 0`. No `_stub_node_version_check` needed (no `.nvmrc`, no Node).
- [ ] **AC-NN-2 — `language_detection` slice populated with `primary == "go"`.** `envelope["probes"]["language_detection"]["language_stack"]["primary"] == "go"`; `counts["go"] >= 2` (the S5-04 fixture has two `.go` files); `monorepo is None`.
- [ ] **AC-NN-3 — The three Node-only probes are ABSENT from `probes` (per ADR-0010 absence-is-the-contract).** `assert_only_language_stack(envelope)` enforces: `"node_build_system" not in probes`; `"node_manifest" not in probes`; `"test_inventory" not in probes`. Absence (not null-valued presence) — ADR-0010's contract.
- [ ] **AC-NN-4 — `ci` and `deployment` MAY be present with empty / no-evidence inner slices.** `applies_to_languages = ["*"]` means both probes run on every repo. The S5-04 `non_node_go` fixture has no CI workflows and no Helm/Kustomize/Compose/Terraform manifests, so each probe ran-and-produced-empty. ADR-0010 permits both shapes — present-with-empty OR absent — for "*"-applicability probes. Test asserts: if `"ci" in probes`, the inner `ci.providers` is `[]` or absent; if `"deployment" in probes`, the inner `deployment.manifests` is `[]` or absent. Do NOT assert absence — would fail on a correct implementation.
- [ ] **AC-NN-5 — Audit run-record proves `ProbeExecution.Skipped` for the three Node-only probes (typed enum compare).** Read the most recent run-record from `repo / ".codegenie" / "context" / "runs"`; locate the `executions` mapping (or whatever the audit serializer names it — cross-reference Phase-0 audit shape at land-time); for each of the three Node-only probes, deserialize the execution variant via `ProbeExecution(record["execution"])` (typed round-trip, not raw string compare) and assert it equals `ProbeExecution.Skipped`. Kills the primitive-obsession class of mutants; couples the test to the typed contract.
- [ ] **AC-NN-6 — `Registry.for_task` filter coupling (cross-check, not just key-absence).** Compute the expected runnable-probe set: `expected = {p.name for p in Registry.for_task(task, languages={"go"})}`; assert `set(envelope["probes"].keys()) == expected`. Catches a renamed-fixture mutant (e.g., someone changed `non_node_go/main.go` to `main.js` — primary flips to JavaScript and the filtered set changes).
- [ ] **AC-NN-7 — Envelope validates via the production seam.** `codegenie.schema.validator.validate(envelope)` succeeds on the present-keys-only envelope (proves ADR-0010's "slices optional at envelope's `probes.*` level" works in practice — a Go-only envelope is schema-valid).

### `test_monorepo_turbo.py` — S2-01 monorepo block

- [ ] **AC-MR-1 — File exists; gather on `node_monorepo_turbo` exits 0.** Test copies the fixture under `tmp_path`, invokes `_stub_node_version_check(monkeypatch)` (the fixture has Node files — defensive), invokes `_invoke_gather(repo)`, asserts `result.exit_code == 0`.
- [ ] **AC-MR-2 — `monorepo` block populated, two markers detected, sorted union.** `assert_monorepo_markers(envelope, expected_tool="turbo", expected_markers=["package.json", "turbo.json"])`. The `markers` field is named `markers` per `src/codegenie/schema/probes/language_detection.schema.json` (`monorepo.tool` is the highest-precedence hit; `monorepo.markers` is the sorted union of all hit marker filenames — basenames only). The fixture has both `turbo.json` and `package.json#workspaces`, so this test pins the precedence-chain code path that the fixture exists to exercise (cross-reference S5-04 AC-MR-3 — `_detect_monorepo` returns `tool == "turbo"` AND `markers == ["package.json", "turbo.json"]`).
- [ ] **AC-MR-3 — Root `build_system` slice populated.** `probes.node_build_system.build_system` is non-null; `package_manager` reflects the fixture's chosen lockfile (`pnpm` per S5-04 AC-MR-6); `lockfile_present == True`. Workspace-member traversal is **explicit Phase-2** scope (this AC does not assert anything about `packages/app-web/package.json` or `packages/app-api/package.json` being individually probed).
- [ ] **AC-MR-4 — Envelope validates via the production seam.** `codegenie.schema.validator.validate(envelope)` succeeds.

### `test_coordinator_prelude.py` — Phase-0 Gap-#4 + Phase-1 reinforcement

- [ ] **AC-PR-1 — File exists; gather on `node_typescript_helm` exits 0 with `_stub_node_version_check`.**
- [ ] **AC-PR-2 — PRIMARY signal: structural snapshot observation in a Wave-2 probe.** The coordinator binds `detected_languages` (derived from the enriched snapshot) into the structlog context **before** dispatching Wave-2 probes. Test captures the structlog event stream via `capture_logs()`; filters to events with `event == "coordinator.wave_2.dispatch"` (or — if S1-07's coordinator does not already emit this event with the bound key — the test asserts via the audit run-record's per-probe `input_snapshot.detected_languages` field that a Wave-2 probe's serialized `ProbeContext` carries non-empty `detected_languages`). The bound value contains at least one of `"javascript"` or `"typescript"`. This is **causally bound** — if LD didn't run-and-enrich-before-dispatch, the field is absent or empty; no scheduler luck can satisfy this. Strengthening over first-draft timestamp-only ordering.
- [ ] **AC-PR-3 — SECONDARY signal: timestamp ordering (redundant belt-and-suspenders).** `language_detection`'s `probe.success` event precedes every Wave-2 `probe.start` event by event-index (not wall-clock). The async event interleaving risk acknowledged in Notes — this signal is kept as redundant evidence, but AC-PR-2 carries the load. If AC-PR-3 alone passes but AC-PR-2 fails, the coordinator's prelude pass is broken (the test surfaces both signals on failure).
- [ ] **AC-PR-4 — If S1-07's coordinator does not already emit the `detected_languages`-bound event, surface as an explicit follow-up.** The Implementation outline #5 proposes either a `logger.bind(detected_languages=...)` site at the Wave-2-dispatch path, OR (fallback) reading the audit run-record's serialized `ProbeContext`. The bind is preferred — it makes the prelude pass observable in production logs, which is the point of structured logging (the AC encodes the runtime invariant, not just the test wiring). If the bind isn't on disk, S5-05 PR adds it (one-line additive coordinator extension; ADR-0007 governs `warnings.id` patterns, not `logger.bind` context keys, so no ADR amendment needed — surface as PR-body note "S1-07 follow-up: bind detected_languages on Wave-2 dispatch event").

### Cross-cutting negative paths

- [ ] **AC-NEG-1 — Schema `additionalProperties: false` is enforced (ADR-0004 contract test).** Inside `test_layer_a_end_to_end.py` (or a sibling test in the same file), deep-copy the loaded envelope, inject an unknown key (`envelope["probes"]["language_detection"]["language_stack"]["bogus_field"] = "x"`), call `codegenie.schema.validator.validate(mutated)`, and assert it raises (the project's `SchemaValidationError` or `jsonschema.ValidationError` — pin to the actual exception type the production validator raises). Without this AC, ADR-0004's strictness could silently regress (a schema flipped to `additionalProperties: true`) and every positive test still passes.
- [ ] **AC-ERR-1 — Probe failure isolation (Phase 1 fail-loud + recovery commitment).** A separate test (e.g., `test_layer_a_end_to_end_failure_isolation.py` or in the same module) monkeypatches one probe's `run()` to raise an exception (suggest `DeploymentProbe.run` — non-load-bearing for the other slices' assertions); invokes `_invoke_gather(repo)`; asserts `result.exit_code == 0` (failure isolation — `phase-arch-design.md §"Failure modes & recovery"`); asserts five other probe slices populated normally via `assert_phase_1_slices_present`-minus-deployment; asserts the audit run-record records `ProbeExecution` in an error variant for `deployment` with the captured exception type/message; asserts `probes.deployment` is absent OR carries an error-coded slice (whichever ADR-0010 / `phase-arch-design.md §"Failure modes"` row 14 prescribes — cross-reference at land-time and pin).

### Definition of Done

- [ ] **AC-DOD-1 — Python 3.11 + 3.12 CI matrix green.** All five tests pass on both interpreters in CI; tests use only Python 3.11-compatible syntax.
- [ ] **AC-DOD-2 — Walltime budget enforced.** `test_layer_a_end_to_end.py` carries `@pytest.mark.timeout(15)` (CI-enforced ceiling, assuming `pytest-timeout` is on dev-deps; otherwise add it — single-dep addition, no SDK closure risk). The five tests collectively complete in under 30 s wall-clock on the `ubuntu-latest` CI runner (measured via `pytest --durations=0`; reported in PR body, not CI-blocking).
- [ ] **AC-DOD-3 — Strict mypy passes** on every new test module and the conftest extensions.

## Implementation outline

**Suggested landing order (smallest to highest blast radius):**

0. **Conftest extensions FIRST** (AC-INFRA-1..4). All other tests depend on these. Land the two new frozensets/mapping next to `WARM_PATH_CACHE_HIT_PROBES`; add the module-load `assert` invariant; promote `_invoke_gather` to a top-level helper (move from `test_cache_hit_on_real_repo.py:80`); add the three pure shape-assertion helpers. Update `conftest.py` `__all__` to export the new names. Verify the existing two-probe test still passes (the move of `_invoke_gather` is a pure refactor at this point).

1. **`tests/integration/probes/test_cache_hit_on_real_repo.py` extension (AC-INFRA-2 + AC-CH-1..7):** One-line edit in `conftest.py` extends `WARM_PATH_CACHE_HIT_PROBES` to all six probes. The test function bodies do not change — the parametrization picks up the four new probes automatically. Apply: (a) module-docstring update (S2-05 → S2-05 + S5-05; two-probe → all-Phase-1-probes via frozenset); (b) extend the slice-content invariance block (lines 206-215 of S2-05's hardened test) to pin one load-bearing field per added slice (AC-CH-5); (c) function renames (AC-CH-7). Run the full file; the metamorphic partner (AC-CH-6) extends automatically. Surface in the PR body which assertions were strengthened.

2. **`tests/integration/probes/test_layer_a_end_to_end.py` (AC-E2E-1..5 + AC-NEG-1):**
   - Import: `from tests.integration.probes.conftest import _copy_tree, _invoke_gather, _load_envelope, _stub_node_version_check, assert_phase_1_slices_present, PHASE_1_PROBE_TO_SLICE` and `from codegenie.schema.validator import validate`.
   - Fixture path: `FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"`; `node_typescript_helm = FIXTURE_ROOT / "node_typescript_helm"` (mirrors S2-05 line 77 — the resilient pattern; not the cwd-fragile `Path("tests/fixtures/...")` of the first-draft).
   - Cold gather: `_stub_node_version_check(monkeypatch)`; `repo = _copy_tree(node_typescript_helm, tmp_path / "repo")`; `result = _invoke_gather(repo)`; `assert result.exit_code == 0, result.output`.
   - Shape: `envelope = _load_envelope(repo)`; `assert_phase_1_slices_present(envelope)`; per-slice value pins (AC-E2E-2).
   - Schema: `validate(envelope)` — no hand-rolled `Draft202012Validator`, no relative-path schema reads.
   - Negative path (AC-NEG-1): deep-copy envelope, mutate one slice with an unknown key, assert `validate(mutated)` raises the production-validator's exception type.
   - Audit anchor (AC-E2E-4): `CliRunner().invoke(cli, ["audit", "verify", "--runs-dir", str(repo / ".codegenie/context/runs"), "--cache-dir", str(repo / ".codegenie/cache"), "--yaml-path", str(repo / ".codegenie/context/repo-context.yaml")])`; assert `exit_code == 0`.
   - Docstring contract (AC-E2E-5): module docstring includes the literal line; a trivial `test_phase_1_exit_criterion_docstring_present` asserts `"Phase 1 exit criterion #1: GREEN" in __doc__`.

3. **`tests/integration/probes/test_non_node_repo.py` (AC-NN-1..7):**
   - `repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")` (no `_stub_node_version_check` — no Node).
   - Smoke + slice presence: `_invoke_gather(repo)`; `envelope = _load_envelope(repo)`; `assert_only_language_stack(envelope)` (the helper enforces AC-NN-3 + AC-NN-4 — Node-only absent; ci/deployment may be present-but-empty).
   - Primary slice content: `envelope["probes"]["language_detection"]["language_stack"]["primary"] == "go"`; `counts["go"] >= 2`.
   - Audit record (AC-NN-5): locate the most recent run-record under `repo / ".codegenie" / "context" / "runs"`; read its `executions` (cross-reference Phase-0 audit shape at land-time); for each Node-only probe, `ProbeExecution(record["execution"]) == ProbeExecution.Skipped` (typed enum round-trip).
   - Registry coupling (AC-NN-6): `from codegenie.probes.registry import Registry`; `expected = {p.name for p in Registry.for_task(<task>, languages={"go"})}`; `assert set(envelope["probes"].keys()) == expected`. Cross-reference the actual `Registry.for_task` signature at land-time (it may take task + snapshot, not task + languages).
   - Schema: `validate(envelope)` passes (proves ADR-0010 — a Go-only envelope is schema-valid).

4. **`tests/integration/probes/test_monorepo_turbo.py` (AC-MR-1..4):**
   - `_stub_node_version_check(monkeypatch)`; `repo = _copy_tree(FIXTURE_ROOT / "node_monorepo_turbo", tmp_path / "repo")`; `result = _invoke_gather(repo)`.
   - `assert_monorepo_markers(envelope, expected_tool="turbo", expected_markers=["package.json", "turbo.json"])`. Sorted-union; basenames; field name pinned via the schema (not hedged).
   - Root `build_system`: `bs = envelope["probes"]["node_build_system"]["build_system"]`; `bs["package_manager"] == "pnpm"`; `bs["lockfile_present"] is True` (or the actual schema field name — cross-reference at land-time).
   - No assertions about workspace-member traversal (Phase-2 scope).

5. **`tests/integration/probes/test_coordinator_prelude.py` (AC-PR-1..4):**
   - `_stub_node_version_check`; `_invoke_gather`; capture structlog via `with capture_logs() as events: ...`.
   - **Primary signal (AC-PR-2 — structural):** filter events to those with key `detected_languages` (the coordinator's Wave-2-dispatch bind, OR a Wave-2 probe's `probe.start` event with the bound context). Assert at least one event has `detected_languages` non-empty containing `"javascript"` or `"typescript"`. If no such event exists in the captured stream, fall back to reading the most recent run-record's per-probe serialized `ProbeContext.input_snapshot.detected_languages` (the audit serializer captures this — verify field path at land-time). Either path is acceptable; the bind is preferred for production observability.
   - **Secondary signal (AC-PR-3 — temporal redundant):** find `ld_success_idx = next(i for i, e in enumerate(events) if e.get("event") == "probe.success" and e.get("probe") == "language_detection")`; `wave_2_starts = [i for i, e in enumerate(events) if e.get("event") == "probe.start" and e.get("probe") != "language_detection"]`; `assert wave_2_starts`; `assert all(i > ld_success_idx for i in wave_2_starts)`. If only the secondary signal passes and primary fails, the prelude is broken and the test surfaces both.
   - **If the coordinator does NOT already bind `detected_languages`** on its Wave-2-dispatch event (verify by reading `src/codegenie/coordinator/coordinator.py` first), add a one-line additive seam: `logger.bind(detected_languages=tuple(sorted(enriched_snapshot.detected_languages.keys())))` at the Wave-2 dispatch site, then emit a `coordinator.wave_2.dispatch` event. ADR-0007 governs `warnings.id` patterns, not `logger.bind` context keys — no ADR amendment required. Surface in the PR body as "S1-07 follow-up: bind detected_languages on Wave-2 dispatch event" so the change is reviewable.

6. **Probe failure isolation (AC-ERR-1):** Either a sixth test file or a sibling test function inside `test_layer_a_end_to_end.py`. Monkeypatch `codegenie.probes.deployment.DeploymentProbe.run` to raise `RuntimeError("forced failure")`; gather; assert exit 0; five other slices populate; audit record contains an error-variant `ProbeExecution` for deployment with the captured message. Cross-reference Phase-1 final-design §"Failure modes & recovery" row for deployment-probe failure shape at land-time (the inner slice may be present with an error code, or absent — pin to whichever ADR-0010 / failure-modes table prescribes).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Land in the order described in Implementation outline (conftest first, cache-hit extension, end-to-end, non-Node, monorepo, prelude, failure isolation). Each red asserts a structural property the current code may or may not deliver; on a clean Phase-1 implementation, every red turns green without source edits (modulo the optional S1-07 coordinator bind for AC-PR-2). Sketches below show the corrected shape — implementers should cross-reference field names against the actual landed S2-01..S4-03 schemas.

```python
# tests/integration/probes/conftest.py (additions next to WARM_PATH_CACHE_HIT_PROBES)
from types import MappingProxyType
from typing import Final, Mapping

PHASE_1_PROBE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }
)
"""All Phase-1 Layer-A probe names. Adding a 7th probe in Phase 2 = one
frozenset insertion + one PHASE_1_PROBE_TO_SLICE entry; zero edits to
any S5-05 test body. (Open/Closed at the file boundary; CLAUDE.md
'Extension by addition'.)"""

PHASE_1_PROBE_TO_SLICE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "language_detection": "language_stack",
        "node_build_system": "build_system",
        "node_manifest": "manifests",
        "ci": "ci",
        "deployment": "deployment",
        "test_inventory": "test_inventory",
    }
)
"""Probe-name → declared slice-key. The envelope path is
`probes[<probe>][<slice>]`; this mapping is the source of truth (the
slice name does NOT always match the probe name — note
language_detection→language_stack, node_build_system→build_system,
node_manifest→manifests). First-draft S5-05 conflated the two."""

# Module-load invariant: after S5-05 lands, the two sets are identical.
# Adding a new Phase-2 probe must update BOTH frozensets in the same PR.
assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES, (
    "S5-05 must extend WARM_PATH_CACHE_HIT_PROBES to all Phase-1 probes; "
    "Phase 2's new probes must update BOTH frozensets."
)


def _invoke_gather(repo: Path) -> "click.testing.Result":  # moved from test_cache_hit_on_real_repo.py
    """``--no-gitignore`` is load-bearing (avoids TTY-prompt coupling).
    Global flags BEFORE the subcommand (click left-to-right binding)."""
    from click.testing import CliRunner
    from codegenie.cli import cli
    return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])


def assert_phase_1_slices_present(envelope: Mapping[str, Any]) -> None:
    """All six Phase-1 probes are present under envelope['probes'], and
    each has its declared slice non-empty. Pure helper; raises
    AssertionError with a structured message naming which probe/slice
    failed."""
    probes = envelope.get("probes", {})
    for probe_name, slice_key in PHASE_1_PROBE_TO_SLICE.items():
        assert probe_name in probes, f"missing probe entry: {probe_name!r}; got {sorted(probes)!r}"
        slice_obj = probes[probe_name].get(slice_key)
        assert slice_obj, f"empty slice: {probe_name}.{slice_key} = {slice_obj!r}"


def assert_only_language_stack(envelope: Mapping[str, Any]) -> None:
    """Three Node-only probe keys ABSENT (per ADR-0010 absence-is-the-contract);
    language_detection present with language_stack; ci/deployment may be
    present with empty inner slices (applies_to_languages = ['*'] means
    they ran)."""
    probes = envelope.get("probes", {})
    assert "language_detection" in probes, sorted(probes)
    assert "language_stack" in probes["language_detection"]
    for forbidden in ("node_build_system", "node_manifest", "test_inventory"):
        assert forbidden not in probes, (
            f"{forbidden} must be absent on a non-Node repo "
            f"(ADR-0010 absence-is-the-contract); got {sorted(probes)!r}"
        )
    # ci/deployment: if present, inner slice must be empty / no evidence
    for sometimes_present in ("ci", "deployment"):
        if sometimes_present in probes:
            slice_obj = probes[sometimes_present].get(sometimes_present, {}) or {}
            # The exact emptiness check is probe-specific; cross-reference
            # ci.providers / deployment.manifests at land-time and pin.


def assert_monorepo_markers(
    envelope: Mapping[str, Any],
    *,
    expected_tool: str,
    expected_markers: Sequence[str],
) -> None:
    """probes.language_detection.language_stack.monorepo non-null and matches.
    `markers` is the sorted union of all hit marker filenames (basenames only)
    per the language_detection schema."""
    monorepo = envelope["probes"]["language_detection"]["language_stack"]["monorepo"]
    assert monorepo is not None, "monorepo block must not be None on a monorepo fixture"
    assert monorepo["tool"] == expected_tool, monorepo
    assert monorepo["markers"] == sorted(expected_markers), monorepo
```

```python
# tests/integration/probes/test_layer_a_end_to_end.py
"""S5-05 — Roadmap Phase 1 exit criterion #1 end-to-end integration test.

Phase 1 exit criterion #1: GREEN — all six probe entries populated,
envelope + 6 sub-schemas validated.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.schema.validator import validate as validate_envelope
from tests.integration.probes.conftest import (
    PHASE_1_PROBE_TO_SLICE,
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    _stub_node_version_check,
    assert_phase_1_slices_present,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.timeout(15)  # AC-DOD-2 — CI-enforced ceiling for the long-pole test
def test_layer_a_end_to_end_node_typescript_helm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_node_version_check(monkeypatch)
    repo = _copy_tree(FIXTURE_ROOT / "node_typescript_helm", tmp_path / "repo")

    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)

    # AC-E2E-2 — all six probes present, slices non-empty
    assert_phase_1_slices_present(envelope)

    # AC-E2E-2 — value pins (mutation-killing; reuses S2-05 pins on this fixture)
    ld = envelope["probes"]["language_detection"]["language_stack"]
    assert ld["framework_hints"] == ["express"], ld
    nbs = envelope["probes"]["node_build_system"]["build_system"]
    assert nbs["package_manager"] == "pnpm", nbs
    # … per-slice pins for node_manifest / ci / deployment / test_inventory
    # cross-referenced from the landed S3-05 / S4-01 / S4-02 / S4-03 schemas
    # and S2-03's fixture content.

    # AC-E2E-3 — envelope + per-probe sub-schemas validate via the production seam
    validate_envelope(envelope)

    # AC-NEG-1 — additionalProperties:false is enforced (ADR-0004 contract)
    mutated = deepcopy(envelope)
    mutated["probes"]["language_detection"]["language_stack"]["bogus_field"] = "x"
    with pytest.raises(Exception):  # narrow to SchemaValidationError at land-time
        validate_envelope(mutated)

    # AC-E2E-4 — audit anchor re-computes via the real CLI subcommand
    audit_result = CliRunner().invoke(
        cli,
        [
            "audit",
            "verify",
            "--runs-dir", str(repo / ".codegenie" / "context" / "runs"),
            "--cache-dir", str(repo / ".codegenie" / "cache"),
            "--yaml-path", str(repo / ".codegenie" / "context" / "repo-context.yaml"),
        ],
    )
    assert audit_result.exit_code == 0, audit_result.output


def test_phase_1_exit_criterion_docstring_present() -> None:
    """AC-E2E-5 — the PR-body grep contract is test-enforced, not just docstring-as-comment."""
    import tests.integration.probes.test_layer_a_end_to_end as mod
    assert "Phase 1 exit criterion #1: GREEN" in (mod.__doc__ or ""), (
        "module docstring must contain the grep contract for the Step 6 close-out"
    )
```

```python
# tests/integration/probes/test_non_node_repo.py  (ADR-0010 contract test)
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeExecution
from codegenie.schema.validator import validate as validate_envelope
from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    assert_only_language_stack,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
_NODE_ONLY_PROBES = ("node_build_system", "node_manifest", "test_inventory")


def test_non_node_go_envelope_shape(tmp_path: Path) -> None:
    repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")
    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)
    assert_only_language_stack(envelope)

    # AC-NN-2 — primary slice content
    ls = envelope["probes"]["language_detection"]["language_stack"]
    assert ls["primary"] == "go"
    assert ls["counts"].get("go", 0) >= 2
    assert ls["monorepo"] is None

    # AC-NN-7 — envelope validates (ADR-0010 — a Go-only envelope is schema-valid)
    validate_envelope(envelope)


def test_non_node_go_audit_records_skipped_for_node_only(tmp_path: Path) -> None:
    """AC-NN-5 — typed enum compare, not raw string."""
    repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")
    _invoke_gather(repo)
    # Read the most recent run-record (cross-reference Phase-0 audit shape)
    runs_dir = repo / ".codegenie" / "context" / "runs"
    # … load the canonical run-record; for each probe in _NODE_ONLY_PROBES,
    # ProbeExecution(record["execution"]) == ProbeExecution.Skipped
```

```python
# tests/integration/probes/test_coordinator_prelude.py
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _stub_node_version_check,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def test_prelude_pass_enriches_snapshot_before_wave_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_node_version_check(monkeypatch)
    repo = _copy_tree(FIXTURE_ROOT / "node_typescript_helm", tmp_path / "repo")

    with capture_logs() as events:
        result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    # AC-PR-2 — PRIMARY: structural snapshot observation in Wave-2 dispatch
    enriched_events = [
        e for e in events if "detected_languages" in e and e.get("detected_languages")
    ]
    if not enriched_events:
        # Fallback to audit-record inspection
        # … read run-record's per-probe input_snapshot.detected_languages
        pytest.fail(
            "no Wave-2 event carried `detected_languages`; "
            "coordinator's prelude bind may be missing (S1-07 follow-up). "
            "Add `logger.bind(detected_languages=...)` at the Wave-2 dispatch site "
            "OR verify the audit run-record carries input_snapshot.detected_languages."
        )
    langs = enriched_events[0]["detected_languages"]
    assert langs, f"enriched_snapshot.detected_languages is empty: {langs!r}"
    assert any(lang in ("javascript", "typescript") for lang in langs), langs

    # AC-PR-3 — SECONDARY: timestamp/event-index ordering (redundant)
    ld_success_idx = next(
        i for i, e in enumerate(events)
        if e.get("event") == "probe.success" and e.get("probe") == "language_detection"
    )
    wave_2_starts = [
        i for i, e in enumerate(events)
        if e.get("event") == "probe.start" and e.get("probe") != "language_detection"
    ]
    assert wave_2_starts, "no Wave-2 probe started — fixture isn't exercising the path"
    assert all(i > ld_success_idx for i in wave_2_starts), (
        f"Wave-2 probes started before LD completed — prelude pass broken; events={events}"
    )
```

Probable failure modes when each red is run:

- `test_layer_a_end_to_end`: a slice is empty (probe failed silently) — surface in PR body; investigate which probe and fix.
- `AC-NEG-1`: the per-probe sub-schema was flipped to `additionalProperties: true` — fix the schema, ADR-0004 regression.
- `test_non_node_go_envelope_shape`: a Node-only probe ran (its `applies_to_languages` filter is wrong) — fix in S2-02 / S3-05 / S4-03.
- `test_non_node_go_audit_records_skipped_for_node_only`: a probe ran when it should have been Skipped, OR the audit serializer doesn't write the `Skipped` variant — fix coordinator audit emission.
- `test_prelude_pass_enriches_snapshot_before_wave_2` AC-PR-2 fail: the coordinator dispatched Wave-2 without binding `detected_languages` — surface as S1-07 follow-up (one-line `logger.bind` addition at the dispatch site).
- AC-ERR-1 fail: a probe failure kills the gather — fix coordinator's failure-isolation path (`phase-arch-design.md §"Failure modes & recovery"`).

### Green — make it pass

If a red fails because a probe is broken in a way that's not "the test is wrong," fix the probe (or coordinator, or schema) and surface the fix in the PR body as a "S2-XX follow-up" / "S3-XX follow-up" / "S1-07 follow-up" reference. The five integration tests are the final QA gate for Phase 1; expect to surface 1–3 small fixes during this story.

The cache-hit extension's "green" is automatic once `WARM_PATH_CACHE_HIT_PROBES` is extended in conftest — the existing test bodies iterate the frozenset. The only test-file edits are the docstring update, the slice-content invariance extension for the four added probes, and the test renames.

### Refactor — clean up

After green:

- Confirm the conftest extensions are clean (no implementation leak into test files — every test imports from conftest; `PHASE_1_PROBE_NAMES`, `PHASE_1_PROBE_TO_SLICE`, the three helpers, `_invoke_gather`, `_stub_node_version_check` all live in one place).
- Verify each test's wall-clock locally with `pytest tests/integration/probes/ --durations=10`; if `test_layer_a_end_to_end` exceeds the `@pytest.mark.timeout(15)` ceiling, profile and identify the slow probe (likely deployment + Helm chart parsing); coordinate with S4-02 owner if a regression is implicated.
- Ensure every test uses `tmp_path` + `_copy_tree` (never the repo's `.codegenie/`).
- For `test_prelude_pass_enriches_snapshot_before_wave_2`: stress-run with `pytest --count=10` locally to verify the primary signal (AC-PR-2) is stable. The structural invariant should never flake; if it does, the coordinator's bind site is wrong (firing AFTER Wave-2 dispatch rather than before).
- Confirm each test passes both on macOS and Linux (CI matrix); `O_NOFOLLOW` and event-loop scheduling can differ.
- Update `tests/integration/probes/conftest.py` `__all__` to export the new public names.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/conftest.py` | **Extend** — add `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` constants; extend `WARM_PATH_CACHE_HIT_PROBES` to all six probes (AC-INFRA-2 — one-line edit); promote `_invoke_gather` from `test_cache_hit_on_real_repo.py` to a top-level helper (AC-INFRA-3); add three pure shape-assertion helpers `assert_phase_1_slices_present`, `assert_only_language_stack`, `assert_monorepo_markers` (AC-INFRA-4); update `__all__`. Module-load `assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES` invariant added. |
| `tests/integration/probes/test_cache_hit_on_real_repo.py` | **Extend** — module-docstring update; per-probe slice-content invariance block extended to four new slices (AC-CH-5); test function renames (AC-CH-7). No function-body edits — extension flows from the conftest frozenset (Open/Closed). |
| `tests/integration/probes/test_layer_a_end_to_end.py` | **New** — roadmap exit criterion #1; includes the docstring-grep self-test (AC-E2E-5) and the schema negative-path mutation (AC-NEG-1). |
| `tests/integration/probes/test_non_node_repo.py` | **New** — ADR-0010 contract test; two test functions (envelope shape + audit-record typed-enum compare). |
| `tests/integration/probes/test_monorepo_turbo.py` | **New** — S2-01 monorepo block + root-level `build_system` slice. |
| `tests/integration/probes/test_coordinator_prelude.py` | **New** — Phase 0 Gap-#4 + Phase 1 reinforcement; primary structural signal (AC-PR-2) + secondary timestamp signal (AC-PR-3). |
| `tests/integration/probes/test_failure_isolation.py` *or* function inside `test_layer_a_end_to_end.py` | **New** — AC-ERR-1 probe-failure-isolation. Implementer picks whichever co-locates better with the existing patterns; flag the decision in the PR body. |
| `src/codegenie/coordinator/coordinator.py` | **Possibly extend** — if the coordinator does not already bind `detected_languages` on its Wave-2-dispatch event, add a one-line `logger.bind(detected_languages=...)` + emit a `coordinator.wave_2.dispatch` event. Surface as "S1-07 follow-up" in PR body. ADR-0007 governs `warnings.id` patterns, not `logger.bind` context keys — no ADR amendment required. |
| `pyproject.toml` (possibly) | **Possibly extend** — add `pytest-timeout` to dev-deps if not already present (AC-DOD-2). Verify against the existing dep set before adding; minor addition, no LLM-SDK closure risk. |

## Out of scope

- **Golden-file diffing against `node_typescript_helm`** — owned by S6-01.
- **Bench canaries (warm-path latency, per-probe RSS)** — owned by S6-02.
- **Coverage ratchet to 90/80** — owned by S6-02.
- **Real-OSS-repo integration test** (e.g. cloning `expressjs/express` at a pinned SHA) — explicitly deferred per `final-design.md §"Tests explicitly not in Phase 1"`; the `node_typescript_helm` fixture is the proxy.
- **Multi-language monorepo integration test** — Phase 2 concern.
- **Workspace-member-level probe assertion** in `test_monorepo_turbo.py` — explicit Phase 2 carve-out.

## Notes for the implementer

### Load-bearing structural commitments

- **The "all six probe entries populated" assertion in `test_layer_a_end_to_end.py` is the single most important assertion in Phase 1.** If any one slice is empty on `node_typescript_helm`, the roadmap exit criterion #1 is not met. Treat a failure here as P0; the fix may be in any of S2-01 / S2-02 / S3-05 / S4-01 / S4-02 / S4-03. The S5-05 PR may legitimately need to land a small follow-up to a probe to make the slice non-empty. **Important**: the envelope's `probes` dict is keyed by **probe name** (`language_detection`, `node_build_system`, …), and the slice (`language_stack`, `build_system`, `manifests`, …) is the **nested** key inside. The first-draft of this story conflated the two; use `PHASE_1_PROBE_TO_SLICE` from conftest as the source of truth.
- **The cache-hit-all-six test is the load-bearing test for `phase-arch-design.md §"Goals"` — "Cache hits on second run (all six Layer A probes)."** S2-05 covered 2; this story covers 6. On the cache-hit path **the coordinator skips `probe.run()` entirely** — no walks happen for any probe, so no additional `os.scandir`/`os.walk` monkeypatches are required beyond LD's. The load-bearing signals for the four added probes are `probe.cache_hit` event count + cache_key byte-equality (the S2-05 four-signal pattern). The scandir counter is correctly asymmetric to `LanguageDetectionProbe` only.
- **`test_non_node_repo.py`'s "absent, not null" assertion (ADR-0010).** A probe that's been filtered out by `Registry.for_task` should not appear as a key in `probes`. The test asserts `"node_build_system" not in probes`, not `probes["node_build_system"] is None`. **BUT**: `CIProbe` and `DeploymentProbe` declare `applies_to_languages = ["*"]` — they **run on every repo** including Go-only. They may produce empty / no-evidence inner slices on `non_node_go`; ADR-0010 permits both shapes (present-with-empty OR absent) for "*"-applicability probes. Do NOT assert their absence — only the **three** Node-only probes (`node_build_system`, `node_manifest`, `test_inventory`) are filter-absent.
- **`test_monorepo_turbo.py` does NOT assert workspace-member traversal.** `phase-arch-design.md §"Open questions"` lists workspace traversal as Phase 2's concern. Resist adding assertions about `packages/app-web/package.json` being individually probed; that's not Phase 1's contract. The fixture's S5-04 AC-MR-5 already pins workspace-member shape — this story exercises Phase 1's root-level probe behavior.
- **`test_coordinator_prelude.py` PRIMARY signal is structural, not temporal.** Async event interleaving makes timestamp-only ordering causally fragile (a coordinator that dispatches Wave-2 with an empty snapshot but completes LD-success-log first under the scheduler passes by luck). The structural invariant — a Wave-2 probe receives an enriched snapshot — is causally bound and cannot be satisfied by scheduling luck. Implementer should verify the coordinator binds `detected_languages` on its dispatch event; if not, add the bind as part of this PR (one-line additive seam; ADR-0007 governs `warnings.id` patterns, not bound context keys, so no ADR amendment).

### Design-pattern guidance

- **Use the conftest seam — do not shadow it.** `tests/integration/probes/conftest.py:90` declares `WARM_PATH_CACHE_HIT_PROBES` explicitly for S5-05 to extend with zero test-body edits. The first-draft Implementation outline proposed editing a "literal set inside the test function" — that literal does not exist; the set IS the named frozenset in conftest. Edit one line in conftest; the test bodies pick up the four new probes automatically. This is the Open/Closed-at-the-file-boundary precedent the Phase-1 conftest established for S5-05 specifically.
- **Closed-set / SSoT for Phase-1 probes.** Three+ consumer sites (S2-04 memo, S2-05 cache-hit, S5-05 ×5 tests) justify lifting `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` to conftest (rule of three met). The module-load `assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES` invariant means Phase 2's seventh probe **must** update both frozensets atomically — refusing to load otherwise. This is the kind of compile-time-style discipline CLAUDE.md "Fail loud" rewards.
- **Functional core / imperative shell** — the three pure shape-assertion helpers (`assert_phase_1_slices_present`, `assert_only_language_stack`, `assert_monorepo_markers`) take a loaded envelope dict and raise `AssertionError`. They contain no I/O, no CLI invocation, no fixture management. The imperative shell (CLI invoke + fixture copy) lives in each test function. Reused by S6-01's golden-file regen test — the rule-of-three threshold is reached.
- **Typed enum for ProbeExecution.** AC-NN-5 round-trips via `ProbeExecution(record["execution"])`; never raw string compare. The audit serializer may emit the variant name as a string in JSON, but the test reconstructs the enum at the assertion boundary. Catches "audit serializer drift" (e.g., a future change that emits `"skipped"` lowercase) and primitive-obsession-on-string mutants.
- **Anti-pattern guard — do NOT re-declare slice/probe lists inside test files.** First-draft had `PHASE_1_SLICES = (...)` inside `test_layer_a_end_to_end.py`. That tuple drifted out of sync with `WARM_PATH_CACHE_HIT_PROBES` (which uses probe names) and the actual envelope shape. The conftest is the source of truth; every test imports from conftest.

### Process / PR hygiene

- **The PR-body grep contract** ("Phase 1 exit criterion #1: GREEN — ...") is what makes the Step 6 (`S6-03`) close-out story's job mechanical. Don't omit the line; the `test_phase_1_exit_criterion_docstring_present` test (AC-E2E-5) refuses to let a refactor silently drop it.
- **If S1-07 coordinator follow-up is required for AC-PR-2,** name it explicitly in the PR body: "S1-07 follow-up: bind `detected_languages` on Wave-2 dispatch event (one-line additive seam at `coordinator.py:<line>`)." Reviewers should be able to see this change without hunting.
- **Surface 1–3 probe follow-ups** during this story. The five integration tests are the final QA gate for Phase 1; expect to find a probe slice that's silently empty or a sub-schema field that drifted from its consumer. Land the fixes in this PR with `S2-XX follow-up` / `S3-XX follow-up` PR-body references, or split into a sibling PR if the fix is non-trivial — coordinate with the original story's owner.
- **Walltime budget:** 30 s total CI wall-clock on `ubuntu-latest`. `test_layer_a_end_to_end` is the long pole (~10 s for a full cold gather; `@pytest.mark.timeout(15)` enforces a CI ceiling); the other four are sub-3 s each. Verify locally with `pytest tests/integration/probes/ --durations=10` before opening the PR; if a regression bumps total walltime above 30 s, profile and surface in the PR body — coordinate fixture slimming with the S2-03 / S3-06 / S5-04 owners (do not edit fixtures without their sign-off).
- **Stability under repeat runs.** Run `pytest tests/integration/probes/ --count=10 -p pytest_repeat` locally before opening the PR (or `for i in $(seq 1 10); do ...; done` if `pytest-repeat` isn't installed). `test_coordinator_prelude.py`'s primary signal (AC-PR-2) is causally bound and should never flake; if it does, the coordinator's bind site is wrong.
