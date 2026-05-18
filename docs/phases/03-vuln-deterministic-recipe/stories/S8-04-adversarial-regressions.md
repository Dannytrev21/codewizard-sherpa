# Story S8-04 — Adversarial regression tests E1–E20

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** Ready
**Effort:** L
**Depends on:** S8-03
**ADRs honored:** ADR-0010 (every adversarial test asserts on a tagged-union discriminator — `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)`, `JailedSubprocessResult.NetworkDenied(host=...)`, `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch)` — never a `bool` or a `dict[str, Any]`), ADR-0008 (the `cve_delta` adversarial test asserts that lockfile re-resolve introducing a NEW CVE causes `TrustOutcome.passed == False` — verifying the cache-key invariant and the strict-AND scoring composition); ADR-0001 (the breaking-test-suite test asserts `Validated(passed=False)` is **terminal** in Phase 3 with **no retry** — Phase 5's `GateRunner` retry envelope hasn't shipped yet; the test fails-loud if any Phase-3 retry slips in)

## Context

`phase-arch-design.md §Edge cases` enumerates 20 adversarial scenarios (E1–E20) — each row names the detection mechanism, the containment, and the recovery disposition. The Step 8 goal in the manifest is unambiguous: "every adversarial case from §Edge cases E1–E20 has a regression test." Many of the fixtures S8-01 ships exist precisely to make these regressions reproducible; this story wires the test assertions on top.

Two architectural constraints are load-bearing:

1. **No Phase-5 retry envelope.** Phase 3 alone runs zero retries. When `breaking-test-suite/` produces `Validated(passed=False)`, the orchestrator returns immediately — the test asserts this is a terminal disposition, NOT a retry-in-flight that just hasn't completed. If the implementer accidentally wires a retry loop, the test must catch it.

2. **`cve_delta` failure produces no branch and no rollback.** When a lockfile re-resolve introduces a NEW CVE not present before, `TrustOutcome.passed == False` (strict-AND across the 5 signals) — the orchestrator refuses to write the branch. There is no rollback (no partial branch to undo); the workflow simply exits non-zero with `cve_delta_introduced` and a `RemediationOutcome.Failed` (or `Validated(passed=False)`, depending on §Component design C6's exact discriminator — verify against current code). The test asserts no branch was created.

This story groups its tests under `tests/adversarial/` and marks every test `@pytest.mark.phase03_adv` so CI can run them as a discrete gating job. Phase 2 already established the `phase02_adv` marker precedent (`pyproject.toml § [tool.pytest.ini_options].markers`); this story adds `phase03_adv`.

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
  - `tests/adversarial/` (Phase 2 precedent) — naming conventions, `@pytest.mark.phase02_adv` shape to mirror.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — the orchestrator the tests exercise; especially the no-retry behavior on `Validated(passed=False)`.
  - `src/codegenie/transforms/sandbox_jail.py` (S4-01..S4-04) — the `SubprocessJail` whose `NetworkDenied`/`Completed`/`TimedOut` variants the adversarial tests assert on.
- **High-level impl:**
  - `../High-level-impl.md §Step 8` — Done criteria explicitly name `test_breaking_test_suite.py` (no retry) and `test_cve_delta_introduced.py` (refuse to branch).

## Goal

Land a regression test under `tests/adversarial/` for every edge case E1–E20 in `phase-arch-design.md §Edge cases`, each marked `@pytest.mark.phase03_adv`, each asserting on the typed discriminator (not a boolean), with specific coverage of: postinstall canary (E8), egress denial (E7), symlink TOCTOU (E12), `extends`-chain composition (E9-adjacent), Yarn Berry → universal (E2), breaking-test-suite no-retry (Phase-3 terminal contract), and `cve_delta`-introduced refuse-to-branch with no rollback (E11).

## Acceptance criteria

- [ ] `tests/adversarial/` directory exists; every test file in it is decorated with module-level `pytestmark = pytest.mark.phase03_adv`.
- [ ] `pyproject.toml § [tool.pytest.ini_options].markers` declares `phase03_adv: Phase 3 adversarial tests (CI-gating)`.
- [ ] **E1** `tests/adversarial/test_lockfile_version_unsupported.py` — pass a `lockfileVersion: 1` lockfile to the engine; assert `RecipeOutcome.Failed(reason=lockfile_v1_unsupported)` + CLI exits 3.
- [ ] **E2** `tests/integration/test_yarn_berry_routed_to_universal.py` — Yarn-Berry-shaped fixture (`.pnp.cjs` + `yarn.lock` with `__metadata: version: 6`); resolver does not match `(vuln, node, npm)`; `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch)`; `.codegenie/handoff/<workflow_id>.md` written. CLI exits 7.
- [ ] **E3** `tests/adversarial/test_monorepo_workspace_isolated_edit.py` — using `monorepo-workspaces/` fixture, assert the engine edits ONLY the workspace owning the vuln; the other workspace's `package.json` is unchanged byte-for-byte; root `package-lock.json` re-resolves.
- [ ] **E4** `tests/adversarial/test_peer_dep_conflict.py` — using `peer-dep-conflict/` fixture, assert `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)`; CLI exits 3.
- [ ] **E5** `tests/adversarial/test_transitive_only_overrides.py` — using `transitive-only-cve/` fixture, assert `RecipeOutcome.Applied(transform=NpmLockfileTransform(...))` carrying an `overrides` annotation; `OverridesUsed` event present on the workflow-internal stream.
- [ ] **E6** `tests/adversarial/test_major_bump_refuse.py` — using `major-bump-required/` fixture, assert `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)`; CLI exits 3.
- [ ] **E7** `tests/adversarial/test_malicious_npmrc_network_denied.py` — using `malicious-npmrc/` fixture inside `SubprocessJail` with `network=RegistryAllowlist(["registry.npmjs.org"])`, assert the inner `JailedSubprocessResult` is `NetworkDenied(host="attacker.example.com")`; assert `NetworkPolicyViolation` event emitted; CLI exits 4.
- [ ] **E8** `tests/adversarial/test_postinstall_canary.py` — using `postinstall-canary/` fixture, run the full workflow; after completion assert the canary file (`/tmp/codegenie-canary-postinstall.txt`) does **not** exist; assert `--ignore-scripts` set at both CLI and env (inspect the `JailedSubprocessSpec` passed to `SubprocessJail.run`).
- [ ] **E9** `tests/adversarial/test_plugin_extends_cycle.py` — write a synthetic plugin pair under a temp `plugins/` dir where A `extends` B and B `extends` A; loader exits 4 with `PluginExtendsCycle(chain=["A", "B", "A"])` BEFORE any resolution.
- [ ] **E10** `tests/adversarial/test_universal_not_silent_on_import_error.py` — synthetic concrete plugin whose `api.py` raises `ImportError` at `importlib.import_module(...)`; loader exits 4 with `PluginRejected(import_error)` BEFORE resolver runs; universal fallback is NOT silently substituted.
- [ ] **E11** `tests/adversarial/test_cve_delta_introduced.py` — construct a `VulnIndex` and lockfile state where post-`npm install` the new lockfile contains a transitive that itself has a known CVE; assert `TrustOutcome.passed == False`, assert `failing == ["cve_delta"]`, assert NO git branch was created under `refs/heads/codegenie/*`, assert NO rollback (the test verifies `git status` shows no orphaned state). CLI exits 4 with `cve_delta_introduced`.
- [ ] **E12** `tests/adversarial/test_symlink_toctou.py` — construct a `SandboxedPath` inside a jail directory; **after** `create()` but **before** `open()`, replace the target with a symlink to `/etc/passwd`; assert `open()` raises `OSError(errno=ELOOP)`; assert caller emits `FilesystemRaceDetected`; CLI exits 4 with `filesystem_race`.
- [ ] **E13** `tests/adversarial/test_concurrent_workflow_lock.py` — acquire `.codegenie/.lock` from the test directly; invoke `codegenie remediate` against the same repo; assert exit code 8 + `WorkflowConcurrent` event on the spanning stream.
- [ ] **E14** `tests/adversarial/test_git_hooks_disabled.py` — fixture with a `.git/hooks/pre-commit` that writes a canary file; run the workflow; assert canary file does NOT exist; assert `GitHooksDisabledForRun` event present.
- [ ] **E15** `tests/adversarial/test_stale_vuln_index_warns.py` — backdate `vuln-index.sqlite` mtime > 7 days; run the workflow; assert `StaleVulnIndex` spanning event emitted; assert workflow **continues** (not blocked); CLI exits 0 if otherwise OK.
- [ ] **E16** `tests/adversarial/test_cve_record_size_cap.py` — feed the smart-constructor parsers a 2-MiB CVE record JSON; assert `Result.Err(SizeCapExceeded)`; ingest path skips with `IngestRejected` log; existing index unchanged.
- [ ] **E17** `tests/adversarial/test_plugins_lock_integrity_mismatch.py` — mutate a plugin file post-`PLUGINS.lock`; loader exits 4 with `PluginRejected(integrity_mismatch)` + the diff.
- [ ] **E18** `tests/adversarial/test_stale_scip_degraded_confidence.py` — using `stale-scip/` fixture, run the workflow; assert `AdapterDegraded` event on the workflow-internal stream; assert `TrustOutcome.confidence == "degraded"` in the final report.
- [ ] **E19** `tests/adversarial/test_disk_full_on_transform_write.py` — mock `os.statvfs` to report 0 free blocks; assert `WorkflowFailed(disk_full)`; assert no partial file at the `.tmp` path; CLI exits 4.
- [ ] **E20** `tests/adversarial/test_adversarial_package_json_content.py` — `package.json` with NUL bytes, zero-width chars, and bidi controls in the `name` field; assert `parse_package_id` returns `Err`; engine returns `RecipeOutcome.Failed(reason=invalid_repo_content)`; the operator-facing handoff markdown is sanitized identically (no bidi leakage to humans).
- [ ] **Breaking-test-suite (Phase-3-terminal contract)** `tests/adversarial/test_breaking_test_suite_no_retry.py` — using `breaking-test-suite/` fixture, assert `Validated(passed=False, failing=["tests"])`; assert workflow ran **exactly one** `_validate_stage6` invocation (use a spy or count `InstallStageOutcome`+`TestStageOutcome` events — there must be exactly one of each); assert no `AttemptSummary` with `attempt > 1` anywhere in the workflow events. CLI exits 5.
- [ ] **`extends`-chain composition** `tests/integration/test_extends_chain.py` — synthetic plugin chain A `extends` B `extends` C `extends` D (depth 4 — boundary of cycle check); resolver walks the chain; assert the final resolution carries the union of A,B,C,D's TCCM and recipes; assert depth 5 is rejected with `PluginExtendsDepthExceeded`.
- [ ] Every adversarial test's assertion message names the edge-case number (`"E7 — malicious .npmrc must produce NetworkDenied; got: {result}"`) so a failure points the reader back at the architecture row.
- [ ] `pytest tests/adversarial/ -m phase03_adv` runs all the above; every test passes; CI wires the marker as a required job (S9-01 will add the actual CI job; this story ensures the marker is correct).
- [ ] `make check` clean; the new tests use the same typed-assertion discipline as the rest of Phase 3 (no `dict[str, Any]`).
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Add `phase03_adv` marker to `pyproject.toml`; add a one-line entry to the markers list with description.
2. Create `tests/adversarial/__init__.py` and `tests/adversarial/conftest.py`; in `conftest.py`, set module-level `pytestmark = pytest.mark.phase03_adv` so individual test files don't need to repeat the decoration.
3. Group tests by where they get their fixture from:
   - **From `tests/fixtures/repos/` (S8-01)** — tests E3, E4, E5, E6, E7, E8, E18, E20.
   - **From in-test synthetic construction** — tests E1, E2, E9, E10, E11, E12, E13, E14, E15, E16, E17, E19, breaking-test-suite, `extends`-chain.
4. For E2 (Yarn Berry → universal), create a tiny `tests/fixtures/repos/yarn-berry/` with `package.json` + `yarn.lock` (with the `__metadata` v6 marker) + `.pnp.cjs` placeholder; the file is small enough not to violate S8-01's 256-KiB cap.
5. For E11 (`cve_delta`), construct a custom VulnIndex sqlite seeded with the post-resolve transitive's CVE; the test acquires the pre-state digest, runs the workflow, asserts NO branch creation via `git for-each-ref refs/heads/codegenie/*` returning empty.
6. For the breaking-test-suite no-retry test, count `InstallStageOutcome` + `TestStageOutcome` events in the per-workflow stream — exactly one of each — and assert `len(report.attempts) == 0` (or whatever `ApplyContext.prior_attempts` ends up populated as in Phase 3 — should always be `[]`).
7. For E12 (symlink TOCTOU), use `os.symlink` in a `threading.Thread` started immediately before `open()` — race-y but the property holds because `O_NOFOLLOW` makes `open()` fail deterministically once the symlink is in place (the race is just "does the swap land in time"; loop until it does or use a small file-system event API).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/adversarial/test_breaking_test_suite_no_retry.py` (the most representative — captures the Phase-3-terminal contract)

```python
from __future__ import annotations
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli

pytestmark = pytest.mark.phase03_adv

FIXTURE = Path(__file__).parent.parent / "fixtures" / "repos" / "breaking-test-suite"


def test_breaking_test_suite_returns_validated_false_with_no_retry(tmp_path: Path) -> None:
    """Phase 3 contract: Validated(passed=False) is terminal; no GateRunner wrap until Phase 5.

    Edge case: §phase-arch-design.md row none (this is the Phase-5-handshake contract from ADR-0001).
    """
    repo = tmp_path / "breaking-test-suite"
    shutil.copytree(FIXTURE, repo)

    result = CliRunner().invoke(cli, ["remediate", str(repo), "--cve", "CVE-PLACEHOLDER"])
    assert result.exit_code == 5, f"expected exit 5 (validated_failed); got {result.exit_code}: {result.output}"

    report_path = repo / ".codegenie" / "remediation-report.yaml"
    import yaml
    report = yaml.safe_load(report_path.read_text())

    # Phase-3-terminal: discriminator says validated, but passed is False.
    assert report["outcome"]["kind"] == "validated", report["outcome"]
    assert report["trust_outcome"]["passed"] is False, report["trust_outcome"]
    assert "tests" in report["trust_outcome"]["failing"], report["trust_outcome"]

    # No-retry contract: exactly one validate cycle; prior_attempts is empty.
    assert report.get("attempts") in (None, [], 0), f"Phase 3 must not retry; got {report.get('attempts')!r}"

    # Spanning + internal event count: exactly one InstallStageOutcome + one TestStageOutcome.
    events_dir = repo / ".codegenie" / "events" / "workflow-internal"
    files = list(events_dir.glob("*.jsonl.zst"))
    assert len(files) == 1, "expected exactly one workflow file"
    # ... decompress + count event kinds; assert install==1 and tests==1
```

State why it fails: the orchestrator's no-retry contract holds (S6-04 honors it), but the assertions on `report["attempts"]` and the event-count discipline are not yet exercised by any test — this is the first one to look. If S6-04 accidentally introduced a retry, the test fails meaningfully naming the regression.

### Green — minimal pass

- For each E# row, write the smallest test that captures the discriminator assertion.
- Tests E3–E8, E18, E20 (fixture-backed) — wire to the S8-01 fixtures, invoke the CLI or orchestrator directly, assert on `RecipeOutcome` / `RemediationOutcome` / `JailedSubprocessResult` variants.
- Tests E1, E9, E10, E11, E12, E13, E14, E15, E16, E17, E19, breaking-test-suite, extends-chain — write the in-test synthetic setup; assert.
- Run `pytest tests/adversarial/ -m phase03_adv` and `tests/integration/test_yarn_berry_routed_to_universal.py` and `tests/integration/test_extends_chain.py` until green.

### Refactor

- Factor a `_run_workflow_expecting(exit_code, fixture, cve)` helper to deduplicate CLI invocation across the fixture-backed tests.
- Add a `_assert_no_branch_created(repo)` helper for E11/E12/E19 (the three exits where no branch must exist).
- Extract a `_event_kinds(workflow_file)` helper that decompresses + yields `event.kind` for the count-based assertions.
- Edge cases from §Edge cases that this code touches: literally all 20 (E1–E20) — this is the comprehensive regression suite. The breaking-test-suite and Yarn-Berry tests additionally encode contracts (no-retry and no-silent-substitution) that aren't single-row edge cases but cross-cutting invariants the architecture spec calls out.
- Cross-reference each test's docstring with the §Edge cases row it satisfies, citing `E#`.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` (extend) | Add `phase03_adv` marker definition. |
| `tests/adversarial/__init__.py` | NEW — package marker. |
| `tests/adversarial/conftest.py` | NEW — module-level `pytestmark = pytest.mark.phase03_adv`. |
| `tests/adversarial/test_lockfile_version_unsupported.py` | NEW — E1. |
| `tests/integration/test_yarn_berry_routed_to_universal.py` | NEW — E2 (lives under `integration/` because it exercises the resolver end-to-end). |
| `tests/fixtures/repos/yarn-berry/` | NEW — minimal Yarn-Berry fixture for E2. |
| `tests/adversarial/test_monorepo_workspace_isolated_edit.py` | NEW — E3. |
| `tests/adversarial/test_peer_dep_conflict.py` | NEW — E4. |
| `tests/adversarial/test_transitive_only_overrides.py` | NEW — E5. |
| `tests/adversarial/test_major_bump_refuse.py` | NEW — E6. |
| `tests/adversarial/test_malicious_npmrc_network_denied.py` | NEW — E7. |
| `tests/adversarial/test_postinstall_canary.py` | NEW — E8. |
| `tests/adversarial/test_plugin_extends_cycle.py` | NEW — E9. |
| `tests/adversarial/test_universal_not_silent_on_import_error.py` | NEW — E10. |
| `tests/adversarial/test_cve_delta_introduced.py` | NEW — E11. |
| `tests/adversarial/test_symlink_toctou.py` | NEW — E12. |
| `tests/adversarial/test_concurrent_workflow_lock.py` | NEW — E13. |
| `tests/adversarial/test_git_hooks_disabled.py` | NEW — E14. |
| `tests/adversarial/test_stale_vuln_index_warns.py` | NEW — E15. |
| `tests/adversarial/test_cve_record_size_cap.py` | NEW — E16. |
| `tests/adversarial/test_plugins_lock_integrity_mismatch.py` | NEW — E17. |
| `tests/adversarial/test_stale_scip_degraded_confidence.py` | NEW — E18. |
| `tests/adversarial/test_disk_full_on_transform_write.py` | NEW — E19. |
| `tests/adversarial/test_adversarial_package_json_content.py` | NEW — E20. |
| `tests/adversarial/test_breaking_test_suite_no_retry.py` | NEW — Phase-3 terminal contract. |
| `tests/integration/test_extends_chain.py` | NEW — depth-4 composition; depth-5 rejection. |

## Out of scope

- **Retry behavior** — Phase 5 ships `GateRunner`. This story's breaking-test-suite test asserts the **absence** of retry in Phase 3 (a forward-compat contract). When Phase 5 lands, that test will move/amend; not now.
- **Rollback of partial state** — Phase 3 has no rollback semantics by design. The `cve_delta`-introduced test asserts no branch was created (so there's nothing to roll back), not that a rollback happened.
- **microVM-class sandbox** — `SubprocessJail` is bwrap/sandbox-exec until Phase 5 substitutes Firecracker. The network-denial and postinstall-canary tests assume the bwrap-class substrate.
- **Adversarial input fuzzing** — S8-03 is the property test; this story is the *regression* suite. No Hypothesis here.
- **CI wiring** of the `phase03_adv` marker as a required job — S9-01 owns CI config.
- **Operator runbook for adversarial exit codes** — S9-04 ships `docs/operations/phase03-runbook.md`.

## Notes for the implementer

- **Assert on the *variant*, not the *boolean*.** ADR-0010 is the discipline; the failure modes are: `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)`, `JailedSubprocessResult.NetworkDenied(host=...)`, `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch)`. A test asserting `result.failed is True` is wrong — it loses the discriminator.
- **The breaking-test-suite no-retry test is the load-bearing one.** If Phase 3 accidentally ships a retry loop, every Phase 5 contract assumption breaks. Make this test fail-loud with a message naming the regression: `assert report.get("attempts") in (None, [], 0), f"Phase 3 must not retry; got {report.get('attempts')!r}"`.
- **`cve_delta` is the hardest test to construct.** You need a `VulnIndex` state where the *post*-resolution lockfile pulls a transitive that itself is in the index. Easiest path: seed a custom in-memory `VulnIndex` whose lookup for `<some-transitive-of-the-bumped-version>` returns a real CVE; the rest is mechanics. Verify by manual inspection of the lockfile diff that the new CVE is actually pulled in.
- **`postinstall-canary` test must clean up.** A leftover `/tmp/codegenie-canary-postinstall.txt` from a flaky CI run will make the next clean run pass spuriously. Session-scoped `conftest.py` fixture (already in S8-01) removes it before each session.
- **Yarn-Berry fixture is intentionally minimal.** Don't ship a real Yarn Berry app — a `package.json` with `"packageManager": "yarn@3.0.0"` and a `.pnp.cjs` stub and a `yarn.lock` with `__metadata: version: 6` is enough for the resolver to refuse routing to `(vuln, node, npm)`.
- **`extends`-cycle and PLUGINS.lock-mismatch tests** belong under `tests/adversarial/`, NOT under `tests/unit/plugins/` — they exercise the loader's exit-code surface, not unit behavior. Mark with `phase03_adv`.
- **`@pytest.mark.phase03_adv` once per file, in `conftest.py`.** Don't sprinkle the decorator on every function. The pattern from Phase 2's `tests/adversarial/conftest.py` is `pytestmark = pytest.mark.phase02_adv` at module scope.
- **E12's symlink-swap race is the messiest test.** You can't guarantee the swap lands between `create()` and `open()`. Two acceptable approaches: (1) use a debug-only seam in `SandboxedPath` to inject the swap synchronously; (2) loop with backoff and use `assert eventually_raises_eloop` — pick whichever has less production-code impact (preferably option 1 if a single test hook already exists).
- **Don't blend Phase 2 and Phase 3 adversarial conventions.** If Phase 2 used `@pytest.mark.adv` and Phase 3 manifests `phase03_adv`, surface the conflict, pick `phase03_adv` (more recent, more specific), and flag the older convention as cleanup.
- **The `extends`-chain depth-4-OK / depth-5-rejected test pair is the Open/Closed-confidence test.** Per ADR-0003-adjacent resolver semantics, depth 4 is the max; depth 5 must be rejected with `PluginExtendsDepthExceeded`. If the resolver accepts depth 5 silently, that's a regression that opens an unbounded-recursion attack surface.
- **Yarn Berry test cites E2; breaking-test-suite test cites the §Integration with Phase 04 contract; `cve_delta` test cites E11.** Cross-link in docstrings so future readers can navigate.
- **Every adversarial test should fail before its implementation lands.** This is the discipline — if a test passes the first time it's run against current code, it wasn't testing what you thought.
