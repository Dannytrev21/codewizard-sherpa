# Story S8-04 — Adversarial regression tests E1–E20

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S8-04-adversarial-regressions.md`](_validation/S8-04-adversarial-regressions.md))
**Effort:** L
**Depends on:** S8-01 (fixture portfolio — supplies E3/E4/E5/E6/E7/E8/E18/E20 fixtures **and** the new `yarn-berry/` fixture, see Files-to-touch), S8-03. **Real execution prerequisites (broader than the sequential predecessor):** the orchestrator (S6-04), the `SubprocessJail` + adapters (S4-01..S4-04), the recipe engines (S5-01..S5-05), and all three plugins (S7-01..S7-05) must be **GREEN** — every adversarial test invokes `codegenie remediate` end-to-end. As of 2026-05-20 those are HARDENED-not-executed and S5-02 is BLOCKED; **this story is itself BLOCKED until that upstream lands**. The executor must check upstream `Status:` lines first and abort with a BLOCKED attempt-log entry if any prerequisite is not GREEN — do not write tests against absent code.
**ADRs honored:** ADR-0010 (every adversarial test asserts on a tagged-union *variant class* + `.kind` discriminator + payload — e.g. `isinstance(o, RecipeNotApplicable) and o.reason == "PEER_DEP_CONFLICT"`, `isinstance(r, NetworkDenied) and r.host == ...`, `isinstance(o, RequiresHumanReview) and o.reason == "no_concrete_match"` — never a `bool` or a `dict[str, Any]`, and never pseudo-attribute access like `RecipeOutcome.Failed` which is not a real symbol — see the Typed-assertion vocabulary box in Acceptance criteria), ADR-0008 (the `cve_delta` adversarial test asserts that a lockfile re-resolve introducing a NEW CVE produces `Validated(passed=False, failing=[SignalKind("cve_delta")])` — verifying the cache-key invariant and the strict-AND scoring composition); ADR-0001 (the breaking-test-suite test asserts `Validated(passed=False)` is **terminal** in Phase 3 with **no retry** — Phase 5's `GateRunner` retry envelope hasn't shipped yet; the test fails-loud if any Phase-3 retry slips in)

## Validation notes

Validated: 2026-05-20
Verdict: HARDENED
Findings addressed: 16 distinct — 4 blocks, 10 hardens, 2 nits (de-duplicated across four critics).

Changes applied:
- **Directory convention corrected** — `tests/adversarial/` → `tests/adv/phase03/` everywhere. The shipped adversarial convention is `tests/adv/` (Phase 0/1, marker `adv`) and `tests/adv/phase02/` (Phase 2, marker `phase02_adv`). `tests/adversarial/` never existed. `phase-arch-design.md` §Testing strategy (lines 986, 989, 1062) still says `tests/adversarial/` — **flagged as arch-doc cleanup**, not fixed here (validator edits only the story). — Consistency F1, all critics.
- **Marker mechanism fixed** — Implementation outline step 2 and Notes claimed `pytestmark` in `conftest.py` propagates to sibling test files. It does not: `pytestmark` is module-scoped and `conftest.py` has no tests. The actual Phase 2 convention (`tests/adv/phase02/*.py`) is **per-file `pytestmark = pytest.mark.phase02_adv`**. Rewrote the outline/notes to per-file `pytestmark`; added a collection meta-test AC. — Test-Quality #1, Consistency F2, Design-Patterns.
- **Outcome-variant symbol names corrected** — the story used `RecipeOutcome.Failed(...)`, `RecipeOutcome.NotApplicable(...)`, `RecipeOutcome.Applied(transform=...)`, `RemediationOutcome.Failed(...)`. These tagged unions are `Annotated[A|B|C, Field(discriminator="kind")]` aliases with **no attribute access**. Shipped variant classes (`src/codegenie/transforms/outcomes.py`): `Applied | Skipped | RecipeNotApplicable | RecipeFailed` and `Validated | RequiresHumanReview | RemediationNotApplicable | RemediationFailed`. `RecipeFailed` carries `error: RecipeError` (no `reason` field); `Applied` carries `transform_id/plugin_id/recipe_id` (no `transform` field). Every AC rewritten to the real classes + `.kind` discriminator + payload. — Consistency F4/F5.
- **E11 `cve_delta` top-level discriminator resolved** — the story's Context hedged "`RemediationFailed` or `Validated(passed=False)`". Resolved: a `cve_delta` failure is a **verdict**, not an unrecoverable error, so the outcome is `Validated(passed=False, failing=[SignalKind("cve_delta")])` (the `Validated` model enforces `passed iff failing==[]`). — Coverage F3.
- **Run-command AC fixed** — `pytest tests/adv/phase03/ -m phase03_adv` would silently miss E2 and the `extends`-chain test (both under `tests/integration/`). Replaced with a marker-scoped command. — Coverage F2.
- **E8/E14/E15/E5/E13/E18 hardened** — "canary file absent" / "event present" assertions strengthened to also prove the containment *mechanism* fired and the relevant stage actually ran (so a skipped stage cannot pass spuriously). — Coverage F4/F6, Test-Quality #4/#5/#6.
- **No-retry red test de-tautologised** — `report.get("attempts") in (None, [], 0)` accepted `None`; an omitted field would pass regardless of retry. Event-count is now the load-bearing assertion. — Test-Quality #3.
- **Mutation-verification discipline added** — this is a *regression* suite over already-shipped code; "every test fails before its impl lands" is a category error. Replaced with a mutation-verification requirement (revert the containment, confirm red, log the diff). — Test-Quality #2.
- **E19 rollback contradiction** — arch E19 row says "rollback branch"; disk-full happens mid-write of `Transform.diff_bytes` before any branch exists. The story (no rollback, atomic-rename) is correct; arch row flagged as cleanup. — Consistency F3.
- **`yarn-berry/` fixture ownership** — moved into S8-01's scope (fixture portfolio owner); S8-04 now depends on S8-01. — Design-Patterns.
- **Shared helpers** relocated from `conftest.py` to `tests/adv/phase03/_helpers.py`, matching `tests/adv/_helpers.py` (Phase 0/2). — Design-Patterns.
- **`malformed-recipe-YAML-at-load`** adversarial item (arch §Testing strategy, High-level-impl Step 8) added to Out-of-scope with rationale. — Coverage F5.
- References line, marker-description string, Goal trace — nits fixed.

Full audit log: [`_validation/S8-04-adversarial-regressions.md`](_validation/S8-04-adversarial-regressions.md)

## Context

`phase-arch-design.md §Edge cases` enumerates 20 adversarial scenarios (E1–E20) — each row names the detection mechanism, the containment, and the recovery disposition. The Step 8 goal in the manifest is unambiguous: "every adversarial case from §Edge cases E1–E20 has a regression test." Many of the fixtures S8-01 ships exist precisely to make these regressions reproducible; this story wires the test assertions on top.

Two architectural constraints are load-bearing:

1. **No Phase-5 retry envelope.** Phase 3 alone runs zero retries. When `breaking-test-suite/` produces `Validated(passed=False)`, the orchestrator returns immediately — the test asserts this is a terminal disposition, NOT a retry-in-flight that just hasn't completed. If the implementer accidentally wires a retry loop, the test must catch it.

2. **`cve_delta` failure produces no branch and no rollback.** When a lockfile re-resolve introduces a NEW CVE not present before, the `TrustScorer`'s strict-AND across the 5 signals yields a failing verdict — the orchestrator refuses to write the branch. There is no rollback (no partial branch to undo); the workflow exits non-zero with `cve_delta_introduced`. **Discriminator resolved (validator):** a `cve_delta` is a trust *verdict*, not an unrecoverable error, so the top-level outcome is `Validated(passed=False, failing=[SignalKind("cve_delta")])` — **not** `RemediationFailed`. (`Validated` denormalizes S6-02's `TrustOutcome`; its model invariant enforces `passed iff failing==[]`.) The test asserts the `Validated` variant + no branch created.

This story groups its tests under `tests/adv/phase03/` and marks every test `@pytest.mark.phase03_adv` so CI can run them as a discrete gating job. Phase 2 already established the `phase02_adv` marker precedent (`pyproject.toml § [tool.pytest.ini_options].markers`); this story adds `phase03_adv`.

Edge cases that map to **specific fixtures from S8-01**: E2 → `tests/integration/test_yarn_berry_routed_to_universal.py` + a small `yarn-berry/` fixture this story creates (or uses the universal-fallback fixture from S7-03 with a Yarn-Berry-shaped lockfile); E3 → `monorepo-workspaces/`; E4 → `peer-dep-conflict/`; E5 → `transitive-only-cve/`; E6 → `major-bump-required/`; E7 → `malicious-npmrc/`; E8 → `postinstall-canary/`; E11 → constructed in-test (lockfile re-resolve introducing a CVE); E12 → in-test symlink-swap fixture; E18 → `stale-scip/`; E20 → `malformed-package-json/`. Others (E1 v1/v2/v3 lockfile, E9 `extends` cycle, E10 import-error precedence, E13 concurrent invocation, E14 git hooks, E15 stale vuln-index, E16 CVE record size cap, E17 PLUGINS.lock mismatch, E19 disk full) are constructed in-test or use synthetic single-file fixtures.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases` — the 20-row table; every row is a test target. Coverage must hit each E#.
  - `../phase-arch-design.md §Component design C6` — `TrustOutcome.passed` strict-AND across signals; the `cve_delta` adversarial test asserts on this composition.
  - `../phase-arch-design.md §Component design C8` — `JailedSubprocessResult` discriminated union; `NetworkDenied(host)` is the variant the `.npmrc` test asserts on.
  - `../phase-arch-design.md §Component design C10` — `SandboxedPath` TOCTOU honesty: `OSError(errno=ELOOP)` at `open()`; `FilesystemRaceDetected` event emitted.
  - `../phase-arch-design.md §Testing strategy §Adversarial tests` — the bullet-list naming size/depth-caps, `--ignore-scripts` canary, egress denial, symlink TOCTOU, capability fence.
  - `../phase-arch-design.md §Integration with Phase 04` — confirms `Validated(passed=False)` is terminal in Phase 3; Phase 4 reads `NotApplicable(reason)` as the LLM-fallback trigger; Phase 5 wraps the retry envelope. The breaking-test-suite test asserts the no-retry contract.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — every adversarial assertion is on a discriminated-union variant, not a boolean.
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — the `cve_delta` test indirectly verifies the cache-key honors `vuln_index.digest` (a re-resolve that pulls a new CVE must invalidate prior cache state).
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — the no-retry contract in Phase 3; Phase 5 wraps.
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` — `SubprocessJail` is what enforces `NetworkDenied`, `--ignore-scripts`, postinstall containment.
- **Existing code:**
  - `tests/fixtures/repos/` (S8-01) — fixtures `malicious-npmrc/`, `postinstall-canary/`, `breaking-test-suite/`, `peer-dep-conflict/`, `major-bump-required/`, `transitive-only-cve/`, `monorepo-workspaces/`, `malformed-package-json/`, `stale-scip/`.
  - `tests/adv/phase02/` (Phase 2 precedent) — `tests/adv/phase02/conftest.py` (registers a `fixture_path` helper; the marker is registered in `pyproject.toml`, **not** in conftest) and the per-file `pytestmark = pytest.mark.phase02_adv` shape in each test module (`test_secret_in_source.py`, `test_stale_scip_fixture.py`). `tests/adv/_helpers.py` (Phase 0/2) is the precedent for importable shared test helpers.
  - `src/codegenie/transforms/outcomes.py` — the shipped `RecipeOutcome` / `RemediationOutcome` tagged-union variant classes the adversarial assertions target (`Applied`, `Skipped`, `RecipeNotApplicable`, `RecipeFailed`, `Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed`). There is **no** `RecipeOutcome.Failed` attribute — these are `Annotated[... , Field(discriminator="kind")]` aliases; assert on the variant class + `.kind`.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — the orchestrator the tests exercise; especially the no-retry behavior on `Validated(passed=False)`.
  - `src/codegenie/transforms/sandbox_jail.py` (S4-01..S4-04) — the `SubprocessJail` whose `NetworkDenied`/`Completed`/`TimedOut` variants the adversarial tests assert on.
- **High-level impl:**
  - `../High-level-impl.md §Step 8` — Done criteria explicitly name `test_breaking_test_suite.py` (no retry) and `test_cve_delta_introduced.py` (refuse to branch).

## Goal

Land a regression test under `tests/adv/phase03/` for every edge case E1–E20 in `phase-arch-design.md §Edge cases`, each marked `@pytest.mark.phase03_adv`, each asserting on the typed discriminator (not a boolean), with specific coverage of: postinstall canary (E8), egress denial (E7), symlink TOCTOU (E12), `extends`-chain composition (E9-adjacent), Yarn Berry → universal (E2), breaking-test-suite no-retry (Phase-3 terminal contract), and `cve_delta`-introduced refuse-to-branch with no rollback (E11).

## Acceptance criteria

> **Typed-assertion vocabulary (read first — applies to every E# below).** `RecipeOutcome` and `RemediationOutcome` are `Annotated[A | B | ..., Field(discriminator="kind")]` aliases in `src/codegenie/transforms/outcomes.py` — they have **no attribute access**. There is no `RecipeOutcome.Failed`. Assert on the shipped *variant classes* and the `.kind` discriminator + payload (ADR-0010). The shipped variants are: `RecipeOutcome` → `Applied` (`kind="applied"`, fields `transform_id/plugin_id/recipe_id`) | `Skipped` | `RecipeNotApplicable` (`kind="not_applicable"`, `reason: NotApplicableReason`) | `RecipeFailed` (`kind="failed"`, `error: RecipeError` — **no `reason` field**; `RecipeError` carries `error_id: ErrorId` dotted-snake-case + `message`). `RemediationOutcome` → `Validated` (`kind="validated"`, `branch/report_path/passed/failing: list[SignalKind]`, invariant `passed iff failing==[]`) | `RequiresHumanReview` (`reason: HumanReviewReason` ∈ `{"no_concrete_match","trust_outcome_failed","policy_violation_unrecoverable"}`) | `RemediationNotApplicable` | `RemediationFailed` (`error: RemediationError`, `partial_report_path`). Exact `error_id` strings and the `cve_delta` `SignalKind` value must be read from the shipped code at execution time — placeholders below are marked *(verify)*.

- [ ] `tests/adv/phase03/` directory exists. **Each test file** carries a per-file module-level `pytestmark = pytest.mark.phase03_adv` — the Phase 2 convention (`tests/adv/phase02/*.py`). NOTE: a `pytestmark` set in `conftest.py` does **not** propagate to sibling test files (pytest semantics — `pytestmark` is module-scoped; conftest has no tests); do not attempt that.
- [ ] **Marker meta-test** `tests/adv/phase03/test_marker_applied.py` — asserts `pytest --collect-only -q -m phase03_adv tests/adv/phase03/ tests/integration/test_yarn_berry_routed_to_universal.py tests/integration/test_extends_chain.py` collects **N > 0** items (N = the full count) and `pytest --collect-only -q -m "not phase03_adv" tests/adv/phase03/` collects **0** items. Without this meta-test a missing `pytestmark` is invisible (an unmarked file silently drops out of the gating job). (validator: added — closes the silent-unmarked-file failure mode.)
- [ ] `pyproject.toml § [tool.pytest.ini_options].markers` declares `phase03_adv: Phase 3 adversarial tests (CI-gating; see tests/adv/phase03/)` — string shape matches the existing `phase02_adv` entry.
- [ ] **E1** `tests/adv/phase03/test_lockfile_version_unsupported.py` — pass a `lockfileVersion: 1` lockfile to the engine; assert the outcome is a `RecipeFailed` instance with `outcome.kind == "failed"` and `outcome.error.error_id == "lockfile.v1_unsupported"` *(verify the exact `ErrorId` against the shipped lockfile parser)* + CLI exits 3.
- [ ] **E2** `tests/integration/test_yarn_berry_routed_to_universal.py` — Yarn-Berry-shaped fixture (`.pnp.cjs` + `yarn.lock` with `__metadata: version: 6`); resolver does not match `(vuln, node, npm)`; outcome is a `RequiresHumanReview` instance with `reason == "no_concrete_match"`; `handoff_path` is non-`None` and the `.codegenie/handoff/<workflow_id>.md` file it names exists. CLI exits 7.
- [ ] **E3** `tests/adv/phase03/test_monorepo_workspace_isolated_edit.py` — using `monorepo-workspaces/` fixture, assert the workflow reached the edit stage (an `Applied` outcome — not skipped early); assert the engine edits ONLY the workspace owning the vuln; the other workspace's `package.json` is unchanged byte-for-byte; root `package-lock.json` re-resolves.
- [ ] **E4** `tests/adv/phase03/test_peer_dep_conflict.py` — using `peer-dep-conflict/` fixture, assert the outcome is a `RecipeNotApplicable` instance with `reason == "PEER_DEP_CONFLICT"`; CLI exits 3.
- [ ] **E5** `tests/adv/phase03/test_transitive_only_overrides.py` — using `transitive-only-cve/` fixture, assert the outcome is an `Applied` instance (`kind == "applied"`); look up the produced `Transform` by `Applied.transform_id` and assert its provenance/diff edits an `overrides` block; assert an `OverridesUsed` event is present on the workflow-internal stream **and its payload names the transitive package** (not just that the event exists).
- [ ] **E6** `tests/adv/phase03/test_major_bump_refuse.py` — using `major-bump-required/` fixture, assert the outcome is a `RecipeNotApplicable` instance with `reason == "MAJOR_BUMP_REFUSE"`; CLI exits 3.
- [ ] **E7** `tests/adv/phase03/test_malicious_npmrc_network_denied.py` — using `malicious-npmrc/` fixture inside `SubprocessJail` with `network=RegistryAllowlist(["registry.npmjs.org"])`, assert the inner `JailedSubprocessResult` is a `NetworkDenied` instance with `host == "attacker.example.com"`; assert a `NetworkPolicyViolation` event is emitted; assert the resulting `RecipeOutcome` is a `RecipeFailed` instance; CLI exits 4.
- [ ] **E8** `tests/adv/phase03/test_postinstall_canary.py` — using `postinstall-canary/` fixture, run the full workflow. **Load-bearing assertion (intent):** spy `SubprocessJail.run` and assert **every** `JailedSubprocessSpec` passed to it has `ignore_scripts is True` AND `"--ignore-scripts"` in its `argv` AND the npm-script env disabled. Then assert the install stage actually executed (an `InstallStageOutcome` event is present — proving the canary was unwritten *because of containment*, not because the stage was skipped). Finally assert the canary file (`/tmp/codegenie-canary-postinstall.txt`) does **not** exist.
- [ ] **E9** `tests/adv/phase03/test_plugin_extends_cycle.py` — write a synthetic plugin pair under a temp `plugins/` dir where A `extends` B and B `extends` A; loader exits 4 with `PluginExtendsCycle(chain=["A", "B", "A"])` BEFORE any resolution.
- [ ] **E10** `tests/adv/phase03/test_universal_not_silent_on_import_error.py` — synthetic concrete plugin whose `api.py` raises `ImportError` at `importlib.import_module(...)`; loader exits 4 with `PluginRejected(import_error)` BEFORE resolver runs; assert positively that the universal fallback was NOT substituted (no `UniversalFallbackResolution` event; no handoff artifact written).
- [ ] **E11** `tests/adv/phase03/test_cve_delta_introduced.py` — construct a `VulnIndex` and lockfile state where post-`npm install` the new lockfile contains a transitive that itself has a known CVE. Assert the top-level outcome is a `Validated` instance with `passed is False` and `failing == [SignalKind("cve_delta")]` *(verify the `cve_delta` `SignalKind` string against the shipped `TrustScorer`/`SignalKind` registry)* — a `cve_delta` is a **verdict**, so the outcome is `Validated`, not `RemediationFailed`. Assert NO git branch was created under `refs/heads/codegenie/*` (`git for-each-ref` returns empty). Assert NO rollback occurred — `git status --porcelain` against the target repo is empty (no orphaned worktree state). CLI exits 4 with `cve_delta_introduced`.
- [ ] **E12** `tests/adv/phase03/test_symlink_toctou.py` — construct a `SandboxedPath` inside a jail directory; **after** `create()` but **before** `open()`, replace the target with a symlink to `/etc/passwd`; assert `open()` raises `OSError` with `errno == errno.ELOOP`; assert the caller emits a `FilesystemRaceDetected` event; CLI exits 4 with `filesystem_race`. The swap must be made deterministic — see Implementation outline step 7 + Notes (do not rely on a wall-clock race).
- [ ] **E13** `tests/adv/phase03/test_concurrent_workflow_lock.py` — acquire `.codegenie/.lock` (`fcntl.flock` exclusive) from the test directly; invoke `codegenie remediate` against the same repo; assert exit code 8; assert a `WorkflowConcurrent` event on the spanning stream **and its payload names the contended lock path** (not just that the event exists).
- [ ] **E14** `tests/adv/phase03/test_git_hooks_disabled.py` — fixture with a `.git/hooks/pre-commit` that writes a canary file; run the workflow. Assert the commit stage actually ran (a commit/branch event is present). Assert the git invocation spec carries the hook-disabling mechanism (`core.hooksPath` set to `/dev/null`, or the equivalent `-c core.hooksPath=/dev/null` arg). Assert a `GitHooksDisabledForRun` event is present. Then assert the canary file does NOT exist.
- [ ] **E15** `tests/adv/phase03/test_stale_vuln_index_warns.py` — using a fixture constructed so the **only** remediable fault is index staleness (a clean, otherwise-passing repo), backdate `vuln-index.sqlite` mtime > 7 days; run the workflow; assert a `StaleVulnIndex` spanning event is emitted; assert the workflow proceeded past the trust-scoring stage (a `Validated` outcome event downstream of index init — proving staleness did not short-circuit); CLI exits 0. Control: a non-backdated run of the same fixture must also exit 0 (so exit 0 genuinely isolates the stale-but-non-blocking property).
- [ ] **E16** `tests/adv/phase03/test_cve_record_size_cap.py` — feed the smart-constructor parsers a CVE record JSON larger than the 1-MiB cap (e.g. 2 MiB); assert the parser returns `Result.Err(SizeCapExceeded)`; assert the ingest path skips the row with an `IngestRejected` log; assert the existing index row count + digest are unchanged.
- [ ] **E17** `tests/adv/phase03/test_plugins_lock_integrity_mismatch.py` — mutate a plugin file post-`PLUGINS.lock`; loader exits 4 with `PluginRejected(integrity_mismatch)` and the rejection payload carries the offending path + computed-vs-recorded SHA diff.
- [ ] **E18** `tests/adv/phase03/test_stale_scip_degraded_confidence.py` — using `stale-scip/` fixture, run the workflow; assert an `AdapterDegraded` event on the workflow-internal stream; assert the final `remediation-report.yaml` `trust_outcome` block reports degraded confidence — *(verify the field name + value against the shipped S6-02 `TrustOutcome` and S5-05 report writer; `Validated` itself does not carry `confidence`, so the report must denormalize it from `TrustOutcome`)*.
- [ ] **E19** `tests/adv/phase03/test_disk_full_on_transform_write.py` — mock `os.statvfs` to report 0 free blocks; assert the top-level outcome is a `RemediationFailed` instance whose `error.error_id` names disk-exhaustion *(verify the exact `ErrorId`)*; assert a `WorkflowFailed` spanning event is emitted; assert no partial file at the `.tmp` path (atomic-rename means no partial state); CLI exits 4.
- [ ] **E20** `tests/adv/phase03/test_adversarial_package_json_content.py` — `package.json` with NUL bytes, zero-width chars, and bidi controls in the `name` field; assert `parse_package_id` returns an `Err`; assert the engine returns a `RecipeFailed` instance whose `error.error_id` names invalid-repo-content *(verify the exact `ErrorId`)*; assert the operator-facing handoff markdown is sanitized identically (NFKC-normalized, bidi/zero-width stripped — no bidi leakage to humans).
- [ ] **Breaking-test-suite (Phase-3-terminal contract)** `tests/adv/phase03/test_breaking_test_suite_no_retry.py` — using `breaking-test-suite/` fixture, assert the outcome is a `Validated` instance with `passed is False` and `"tests"` in `failing`. **No-retry proof (load-bearing — event-count, not the report field):** count event kinds in the workflow-internal stream and assert **exactly one** `InstallStageOutcome` and **exactly one** `TestStageOutcome` (a retry produces 2× each). Additionally assert the report's `attempts` field **exists and equals `[]`** (a present-and-empty list — do NOT accept a missing/`None` field as proof, since an omitted field passes regardless of whether a retry happened). Assert no `AttemptSummary` with `attempt > 1` anywhere in the workflow events. CLI exits 5.
- [ ] **`extends`-chain composition** `tests/integration/test_extends_chain.py` — synthetic plugin chain A `extends` B `extends` C `extends` D (depth 4 — boundary of cycle check); resolver walks the chain; assert the final resolution carries the union of A,B,C,D's TCCM and recipes; assert depth 5 is rejected with `PluginExtendsDepthExceeded`.
- [ ] Every adversarial test's assertion message names the edge-case number (`"E7 — malicious .npmrc must produce NetworkDenied; got: {result}"`) so a failure points the reader back at the architecture row.
- [ ] `pytest -m phase03_adv tests/adv/phase03/ tests/integration/test_yarn_berry_routed_to_universal.py tests/integration/test_extends_chain.py` runs all 23 tests (20 E# + breaking-test-suite + extends-chain + marker meta-test); every test passes. NOTE: a bare `pytest tests/adv/phase03/ -m phase03_adv` would silently miss E2 and the `extends`-chain test (they live under `tests/integration/`) — the marker-scoped command above is the canonical one. CI wiring of this command as a required job is S9-01's job; this story only ensures the marker + command are correct.
- [ ] `make check` clean; the new tests use the same typed-assertion discipline as the rest of Phase 3 (assert on variant classes + `.kind`; no `dict[str, Any]`, no boolean-collapsing of discriminated unions).
- [ ] **Mutation-verification** (replaces "red test fails first" — this is a *regression* suite over already-shipped code, so tests are green-first by construction). For the breaking-test-suite no-retry test and **at least two** representative containment tests (E7 egress denial, E8 postinstall canary), the implementer temporarily reverts the relevant containment in production code (delete the no-retry early-return; drop `--ignore-scripts`; widen the registry allowlist), confirms the test goes **red** with a message naming the regression, restores the code, and records each mutation diff + the observed red output in `_attempts/S8-04.md`. A regression test that cannot be made to fail by reverting its target is not testing what it claims.

## Implementation outline

0. **Precondition check.** Before writing any test, read the `Status:` line of S6-04 (orchestrator), S4-01..S4-04 (jail + adapters), S5-01..S5-05 (recipe engines), S7-01..S7-05 (plugins). If any is not `GREEN`/`Done`, this story is BLOCKED — write a BLOCKED entry in `_attempts/S8-04.md` and stop (see the `Depends on:` line). The suite invokes `codegenie remediate` end-to-end; it cannot be written against absent code.
1. Add `phase03_adv` marker to `pyproject.toml § [tool.pytest.ini_options].markers`; one line, description string `phase03_adv: Phase 3 adversarial tests (CI-gating; see tests/adv/phase03/)` (mirrors the existing `phase02_adv` entry).
2. Create `tests/adv/phase03/__init__.py`, `tests/adv/phase03/conftest.py`, and `tests/adv/phase03/_helpers.py`. Each **test file** declares its own module-level `pytestmark = pytest.mark.phase03_adv` (the Phase 2 convention — `tests/adv/phase02/test_*.py` each do this). Do **not** put `pytestmark` in `conftest.py`: pytest's `pytestmark` is module-scoped and a `conftest.py` (which contains no tests) does not propagate it to sibling test modules — that would silently leave every file unmarked and the gating job empty. `conftest.py` holds only fixtures (e.g. a `fixture_path` helper + the session-scoped canary cleanup, mirroring `tests/adv/phase02/conftest.py`). The marker meta-test (`test_marker_applied.py`) guards against a forgotten per-file `pytestmark`.
3. Group tests by where they get their fixture from:
   - **From `tests/fixtures/repos/` (S8-01)** — tests E3, E4, E5, E6, E7, E8, E18, E20, and E2's `yarn-berry/` fixture (S8-01 ships it — see Files-to-touch).
   - **From in-test synthetic construction** — tests E1, E9, E10, E11, E12, E13, E14, E15, E16, E17, E19, breaking-test-suite, `extends`-chain.
4. E2's `yarn-berry/` fixture (`package.json` with `"packageManager": "yarn@3.0.0"` + `yarn.lock` with the `__metadata: version: 6` marker + a `.pnp.cjs` stub) is owned by **S8-01** (the fixture-portfolio story) — this story consumes it, it does not create it. If S8-01 has not yet shipped it, the E2 AC may fall back to the universal-fallback fixture from S7-03 given a Yarn-Berry-shaped `yarn.lock` (the story's References note this option). Either way, `tests/fixtures/repos/` is not edited by S8-04.
5. For E11 (`cve_delta`), construct a custom VulnIndex sqlite seeded with the post-resolve transitive's CVE; the test acquires the pre-state digest, runs the workflow, asserts NO branch creation via `git for-each-ref refs/heads/codegenie/*` returning empty AND `git status --porcelain` empty (no rollback / no orphaned state).
6. For the breaking-test-suite no-retry test, the **load-bearing** proof is the event count: extract event kinds from the workflow-internal stream and assert exactly one `InstallStageOutcome` and exactly one `TestStageOutcome`. Additionally assert `report["attempts"] == []` — the field must be **present and an empty list**; an absent/`None` field is not acceptable proof (it passes whether or not a retry happened). `ApplyContext.prior_attempts` is always `[]` in Phase 3.
7. For E12 (symlink TOCTOU), the swap must be made **deterministic**, not raced against a wall clock. Default approach: a tight loop that performs the swap then retries `open()`, asserting `open()` *eventually* raises `OSError(errno=ELOOP)` — `O_NOFOLLOW` guarantees correctness once the symlink is in place, so the only nondeterminism is "did the swap land", which the loop removes. Use a synchronous test seam **only if `SandboxedPath` already exposes one** — do not add a debug-only seam to production code purely for this test (see Notes).

## TDD plan — red / green / refactor

### Red — write the test first (regression suite: green-first by construction, mutation-verified)

Test file path: `tests/adv/phase03/test_breaking_test_suite_no_retry.py` (the most representative — captures the Phase-3-terminal contract).

```python
from __future__ import annotations
import errno
import shutil
from collections import Counter
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli

pytestmark = pytest.mark.phase03_adv

# tests/adv/phase03/<this file> -> parents[2] is tests/
FIXTURE = Path(__file__).parents[2] / "fixtures" / "repos" / "breaking-test-suite"


def test_breaking_test_suite_returns_validated_false_with_no_retry(tmp_path: Path) -> None:
    """Phase 3 contract: Validated(passed=False) is terminal; no GateRunner wrap until Phase 5.

    Contract: §Integration with Phase 04 + ADR-0001 (not a single §Edge cases row).
    """
    repo = tmp_path / "breaking-test-suite"
    shutil.copytree(FIXTURE, repo)

    result = CliRunner().invoke(cli, ["remediate", str(repo), "--cve", "CVE-PLACEHOLDER"])
    assert result.exit_code == 5, f"breaking-test-suite: expected exit 5 (validated_failed); got {result.exit_code}: {result.output}"

    import yaml
    report = yaml.safe_load((repo / ".codegenie" / "remediation-report.yaml").read_text())

    # Phase-3-terminal: discriminator says validated, but passed is False.
    assert report["outcome"]["kind"] == "validated", report["outcome"]
    assert report["trust_outcome"]["passed"] is False, report["trust_outcome"]
    assert "tests" in report["trust_outcome"]["failing"], report["trust_outcome"]

    # No-retry proof #1 (load-bearing): exactly one install + one test stage.
    kinds = Counter(_event_kinds(repo))  # _helpers.py — decompress workflow-internal stream
    assert kinds["InstallStageOutcome"] == 1, f"no-retry violated — InstallStageOutcome×{kinds['InstallStageOutcome']}; a retry produces 2+"
    assert kinds["TestStageOutcome"] == 1, f"no-retry violated — TestStageOutcome×{kinds['TestStageOutcome']}; a retry produces 2+"

    # No-retry proof #2: attempts field is present AND empty (a missing/None field is NOT proof).
    assert report["attempts"] == [], f"Phase 3 must not retry; attempts={report.get('attempts')!r}"
    assert not any(e.get("attempt", 1) > 1 for e in kinds.elements() if isinstance(e, dict)), "no AttemptSummary with attempt>1"
```

**Why this is not "red-first" in the classic sense.** S8-04 is a *regression* suite layered on already-shipped code (S6-04 honors the no-retry contract; S4-0x enforce containment). A regression test is **green the first time it runs** — that is correct, not a smell. The honest discipline is **mutation verification** (see the Mutation-verification AC): temporarily delete the orchestrator's no-retry early-return, confirm `InstallStageOutcome×2` makes this test go red with the message above, restore, and log the mutation diff in `_attempts/S8-04.md`. A regression test that cannot be driven red by reverting its target tests nothing. The earlier story text "every adversarial test should fail before its implementation lands" was a category error and has been removed.

### Green — minimal pass

- For each E# row, write the smallest test that captures the *variant-class + payload* assertion (not a boolean).
- Tests E3–E8, E18, E20 (fixture-backed) — wire to the S8-01 fixtures, invoke the CLI or orchestrator directly, assert on the shipped `RecipeOutcome` / `RemediationOutcome` / `JailedSubprocessResult` variant classes.
- Tests E1, E9, E10, E11, E12, E13, E14, E15, E16, E17, E19, breaking-test-suite, extends-chain — write the in-test synthetic setup; assert.
- Add `test_marker_applied.py` (the marker meta-test).
- Run the canonical command until green: `pytest -m phase03_adv tests/adv/phase03/ tests/integration/test_yarn_berry_routed_to_universal.py tests/integration/test_extends_chain.py`.

### Refactor

- Shared helpers live in **`tests/adv/phase03/_helpers.py`** (with `__all__`), mirroring `tests/adv/_helpers.py` (Phase 0/2). `conftest.py` holds only fixtures/hooks — not importable logic.
- Factor a `_run_workflow_expecting(exit_code, fixture, cve)` helper to deduplicate CLI invocation across the fixture-backed tests (rule-of-three: 8 fixture-backed tests — clearly met).
- Extract a `_event_kinds(repo)` helper that decompresses the workflow-internal stream + yields `event.kind` for the count-based assertions (used by breaking-test-suite + any event-count test).
- A `_assert_no_branch_created(repo)` helper is used by E11 (and any other no-branch case). Note E12 (TOCTOU abort) and E19 (disk-full mid-transform) do not create branches for the *same* reason as E11 and their "no orphaned state" checks differ (E19 also asserts no partial `.tmp`) — keep those checks inline rather than forcing them through one helper if the assertion is not byte-identical (avoid a shared helper that masks distinct intent — Rule 2 / Rule 9).
- Edge cases from §Edge cases that this code touches: literally all 20 (E1–E20) — this is the comprehensive regression suite. The breaking-test-suite and Yarn-Berry tests additionally encode contracts (no-retry and no-silent-substitution) that aren't single-row edge cases but cross-cutting invariants the architecture spec calls out.
- Cross-reference each test's docstring with the §Edge cases row it satisfies, citing `E#`.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` (extend) | Add `phase03_adv` marker definition. |
| `tests/adv/phase03/__init__.py` | NEW — package marker. |
| `tests/adv/phase03/conftest.py` | NEW — fixtures + session-scoped canary cleanup only. **No `pytestmark`** (it does not propagate from conftest — see Implementation outline step 2). |
| `tests/adv/phase03/_helpers.py` | NEW — importable shared helpers (`_run_workflow_expecting`, `_event_kinds`, `_assert_no_branch_created`), mirroring `tests/adv/_helpers.py`. |
| `tests/adv/phase03/test_marker_applied.py` | NEW — marker meta-test (collection assertion). |
| `tests/adv/phase03/test_lockfile_version_unsupported.py` | NEW — E1. |
| `tests/integration/test_yarn_berry_routed_to_universal.py` | NEW — E2 (lives under `integration/` because it exercises the resolver end-to-end). |
| `tests/fixtures/repos/yarn-berry/` | **NOT created here** — owned by S8-01 (fixture portfolio). S8-04 consumes it; if S8-01 has not shipped it, fall back to the S7-03 universal-fallback fixture with a Yarn-Berry-shaped `yarn.lock` (see Implementation outline step 4). |
| `tests/adv/phase03/test_monorepo_workspace_isolated_edit.py` | NEW — E3. |
| `tests/adv/phase03/test_peer_dep_conflict.py` | NEW — E4. |
| `tests/adv/phase03/test_transitive_only_overrides.py` | NEW — E5. |
| `tests/adv/phase03/test_major_bump_refuse.py` | NEW — E6. |
| `tests/adv/phase03/test_malicious_npmrc_network_denied.py` | NEW — E7. |
| `tests/adv/phase03/test_postinstall_canary.py` | NEW — E8. |
| `tests/adv/phase03/test_plugin_extends_cycle.py` | NEW — E9. |
| `tests/adv/phase03/test_universal_not_silent_on_import_error.py` | NEW — E10. |
| `tests/adv/phase03/test_cve_delta_introduced.py` | NEW — E11. |
| `tests/adv/phase03/test_symlink_toctou.py` | NEW — E12. |
| `tests/adv/phase03/test_concurrent_workflow_lock.py` | NEW — E13. |
| `tests/adv/phase03/test_git_hooks_disabled.py` | NEW — E14. |
| `tests/adv/phase03/test_stale_vuln_index_warns.py` | NEW — E15. |
| `tests/adv/phase03/test_cve_record_size_cap.py` | NEW — E16. |
| `tests/adv/phase03/test_plugins_lock_integrity_mismatch.py` | NEW — E17. |
| `tests/adv/phase03/test_stale_scip_degraded_confidence.py` | NEW — E18. |
| `tests/adv/phase03/test_disk_full_on_transform_write.py` | NEW — E19. |
| `tests/adv/phase03/test_adversarial_package_json_content.py` | NEW — E20. |
| `tests/adv/phase03/test_breaking_test_suite_no_retry.py` | NEW — Phase-3 terminal contract. |
| `tests/integration/test_extends_chain.py` | NEW — depth-4 composition; depth-5 rejection. |

## Out of scope

- **Retry behavior** — Phase 5 ships `GateRunner`. This story's breaking-test-suite test asserts the **absence** of retry in Phase 3 (a forward-compat contract). When Phase 5 lands, that test will move/amend; not now.
- **Rollback of partial state** — Phase 3 has no rollback semantics by design. The `cve_delta`-introduced test asserts no branch was created (so there's nothing to roll back), not that a rollback happened.
- **microVM-class sandbox** — `SubprocessJail` is bwrap/sandbox-exec until Phase 5 substitutes Firecracker. The network-denial and postinstall-canary tests assume the bwrap-class substrate.
- **Adversarial input fuzzing** — S8-03 is the property test; this story is the *regression* suite. No Hypothesis here.
- **Malformed-recipe-YAML-rejected-at-load** — `phase-arch-design.md §Testing strategy §Adversarial tests` and `High-level-impl.md §Step 8` name a "recipe-authoring abuse precursor: malformed recipe YAML rejected at load" item. It is **not** one of the E1–E20 §Edge cases rows and is deliberately out of scope here: the recipe catalog is Python-registered in Phase 3 (`@register_recipe`, S5-01); a YAML-driven recipe loader does not exist until Phase 15. The malformed-recipe-YAML adversarial belongs with whatever story introduces that loader. If a reviewer believes Phase 3 must cover it, raise it against S5-01/S5-04 — do not silently fold it into this story.
- **Capability-construction fence** — `tests/static/test_capability_fence.py` is owned by Step 4 (S4-05); not re-created here.
- **CI wiring** of the `phase03_adv` marker as a required job — S9-01 owns CI config.
- **Operator runbook for adversarial exit codes** — S9-04 ships `docs/operations/phase03-runbook.md`.

## Notes for the implementer

- **Assert on the *variant class*, not a boolean, and not pseudo-attribute access.** ADR-0010 is the discipline. `RecipeOutcome` / `RemediationOutcome` are discriminated-union *aliases* — there is no `RecipeOutcome.Failed` or `RemediationOutcome.RequiresHumanReview`. Import the variant classes from `codegenie.transforms.outcomes` and assert `isinstance(outcome, RecipeNotApplicable) and outcome.reason == "PEER_DEP_CONFLICT"`, `isinstance(result, NetworkDenied) and result.host == ...`, `isinstance(outcome, RequiresHumanReview) and outcome.reason == "no_concrete_match"`. A test asserting `result.failed is True` is wrong — it collapses the discriminator. See the "Typed-assertion vocabulary" box at the top of Acceptance criteria for the full shipped variant list and field shapes.
- **The breaking-test-suite no-retry test is the load-bearing one.** If Phase 3 accidentally ships a retry loop, every Phase 5 contract assumption breaks. The *primary* no-retry proof is the event count (`InstallStageOutcome == 1`, `TestStageOutcome == 1`) — a retry produces 2× each. The `report["attempts"]` check is secondary and must require the field **present and `== []`**; never `report.get("attempts") in (None, [], 0)` — accepting `None` makes an omitted field pass whether or not a retry happened (a tautology).
- **`cve_delta` is the hardest test to construct, and its top-level outcome is `Validated`, not `RemediationFailed`.** A `cve_delta` is a trust *verdict*, so the orchestrator returns `Validated(passed=False, failing=[SignalKind("cve_delta")])` (the `Validated` model enforces `passed iff failing==[]`). You need a `VulnIndex` state where the *post*-resolution lockfile pulls a transitive that itself is in the index. Easiest path: seed a custom in-memory `VulnIndex` whose lookup for `<some-transitive-of-the-bumped-version>` returns a real CVE. Verify by manual inspection of the lockfile diff that the new CVE is actually pulled in.
- **`postinstall-canary` test must clean up.** A leftover `/tmp/codegenie-canary-postinstall.txt` from a flaky CI run will make the next clean run pass spuriously. Session-scoped `conftest.py` fixture (already in S8-01) removes it before each session. The canary-absent check alone is weak — the load-bearing assertion is the `JailedSubprocessSpec` inspection (`--ignore-scripts` present) plus proof the install stage ran (see E8 AC).
- **Yarn-Berry fixture is intentionally minimal and is owned by S8-01.** A `package.json` with `"packageManager": "yarn@3.0.0"` + a `.pnp.cjs` stub + a `yarn.lock` with `__metadata: version: 6` is enough for the resolver to refuse routing to `(vuln, node, npm)`. S8-04 does not write under `tests/fixtures/repos/` — consume S8-01's fixture (or the S7-03 fallback).
- **`extends`-cycle and PLUGINS.lock-mismatch tests** belong under `tests/adv/phase03/`, NOT under `tests/unit/plugins/` — they exercise the loader's exit-code surface, not unit behavior.
- **Marker discipline — per file, never conftest.** Each test file declares its own module-level `pytestmark = pytest.mark.phase03_adv`, exactly as `tests/adv/phase02/test_*.py` do. `pytestmark` in `conftest.py` is a no-op for sibling files (it is module-scoped; conftest has no tests). The `test_marker_applied.py` meta-test exists precisely to catch a forgotten per-file `pytestmark`. This keeps the suite extensible by addition: adding the 21st adversarial case = drop one new file (with its `pytestmark` line) — zero edits to `conftest.py` or any existing file.
- **E12's symlink-swap must be made deterministic — and do NOT add a production seam for it.** Default to the loop approach: swap the symlink, retry `open()`, assert it *eventually* raises `OSError(errno=ELOOP)` — `O_NOFOLLOW` makes correctness deterministic once the symlink lands, so the loop only removes timing nondeterminism. A synchronous test seam in `SandboxedPath` is acceptable *only if one already exists* — adding a debug-only hook to production code purely to make a test convenient is the anti-pattern this story must not introduce. The arch §Risks row 5 already prescribes a `with_sandbox_open(...)` helper; route through that if it exists.
- **Directory + marker convention is `tests/adv/phase03/` + `phase03_adv`** — the shipped Phase 0/1 (`tests/adv/`, `adv`) and Phase 2 (`tests/adv/phase02/`, `phase02_adv`) precedent. The arch doc's `tests/adversarial/` wording is stale and flagged for cleanup; do not resurrect it.
- **The `extends`-chain depth-4-OK / depth-5-rejected test pair is the Open/Closed-confidence test.** Depth 4 is the max; depth 5 must be rejected with `PluginExtendsDepthExceeded`. If the resolver accepts depth 5 silently, that's a regression that opens an unbounded-recursion attack surface.
- **Yarn Berry test cites E2; breaking-test-suite test cites the §Integration with Phase 04 contract; `cve_delta` test cites E11.** Cross-link in docstrings so future readers can navigate.
- **This is a regression suite — tests are green-first; verify them by mutation, not by red-first.** Do not expect any test to fail against current (correct) shipped code. The honest discipline is the Mutation-verification AC: revert the containment, confirm red, restore, log the diff in `_attempts/S8-04.md`.
