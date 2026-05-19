# Story S12-02 — `test_distroless_migration_e2e.py` headline e2e

**Step:** Step 12 — End-to-end test suite + property tests + adversarial tests + regression-gate enforcement
**Status:** Ready
**Effort:** L
**Depends on:** S12-01 (fixture portfolio)
**ADRs honored:** ADR-0001 (no `MultiPluginCoordinator` in Phase 7 — this e2e exercises a single-plugin migration path, no coordination needed), ADR-0002 (`ShellInvocationTraceProbe` runs in microVM — invoked transitively by `ShellInvocationDeltaGate`), ADR-0003 (`SandboxRole` additive enum — `Role.GATE` for build verification, `Role.PROBE` for trace re-run), ADR-0012 (`DockerfilePolicyGate` strict-AND, no override — e2e cannot opt out), ADR-0013 (`dockerfile-parse` recipe engine — e2e exercises real base-image swap), ADR-0015 (`docker buildx` + `dive` allowlist — e2e shells out via the allowlisted wrapper).

## Context

`tests/e2e/test_distroless_migration_e2e.py` is the headline test for the Phase 7 single-plugin happy path: **a vulnerable Node.js repo with an Alpine base and clean app deps migrates to a Chainguard distroless base**. The migration is end-to-end:

1. Operator runs `codegenie remediate <fixture> --cve <id>` against `tests/fixtures/portfolio/node-vulnerable-base-only/` (or a base-only fixture — app deps are clean so this exercises pure base-image migration without `Both` complications).
2. The gather pipeline runs `BaseImageProbe` + `ShellInvocationTraceProbe` (the latter via `SandboxClient.spawn(role=Role.PROBE)`).
3. The migration plugin's TCCM resolves `compute: vuln.provenance` to `assemble_provenance(...)`, which returns `BaseImage(...)` per the AlpineVulnProvenanceAdapter.
4. `DockerfileBaseImageSwapTransform` reads the Chainguard catalog YAML and produces a diff that replaces `FROM node:18-alpine` with `FROM cgr.dev/chainguard/node` + the multi-stage runner adjustments (`COPY --from=builder`, `USER nonroot`, exec-form `ENTRYPOINT`).
5. `DockerfilePolicyGate` (strict-AND, six invariants) passes.
6. `DistrolessBuildGate` (`docker buildx build --target=runtime` via `SandboxClient.spawn(role=Role.GATE)`) succeeds.
7. `ShellInvocationDeltaGate` (re-runs `ShellInvocationTraceProbe` against the migrated image; passes iff `shell_invocations.count == 0`) succeeds.
8. `npm test` runs inside `SubprocessJail` against the migrated image and exits 0.
9. `remediation-report.yaml` is written under `.codegenie/remediation/<workflow_id>.yaml`; the file lists the swap diff, the three gate outcomes, and confidence.
10. CLI exits with code 0 (success); **no PR is opened** (Phase 7 stops at PR boundary per S11-04 — but unlike `Both`, this is "success" not "pending coordination," so exit code 0, not 8).

This e2e is gated by `@pytest.mark.phase07_e2e` because it requires a `--privileged` Linux runner (Docker-in-Docker for `DistrolessBuildGate`). Per Phase 7 ADR-0015 + open question §6 (pinned in S12-05), the marker is opt-in per-PR via label, mandatory on `main`-merge.

This is the load-bearing proof of "both task classes run from the same orchestration" — the migration task class fires from the same `codegenie remediate` CLI entry point as Phase 3's vulnerability remediation, with plugin resolution picking the migration plugin based on `BaseImage` provenance.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios §Scenario B — Base-image-only CVE (single-plugin migration route)` (lines 404–454) — the exact sequence this e2e implements.
  - `../phase-arch-design.md §Testing strategy §End-to-end tests` (lines 1273–1278) — the marker policy + the assertions.
  - `../phase-arch-design.md §Component design §11 + §12` — `DockerfileBaseImageSwapTransform` + the three gates.
- **Phase ADRs:**
  - `../ADRs/0015-allowed-binaries-amendment-dive-buildx.md` — the `dive` + `docker buildx` allowlist amendment (the e2e shells out only via the allowlisted wrapper).
  - `../ADRs/0012-dockerfile-policy-gate-strict-and-no-override.md` — gate cannot be bypassed; e2e must not introduce an override path.
  - `../ADRs/0003-sandbox-role-additive-enum-on-spawn.md` — `Role.GATE` vs `Role.PROBE` usage in the e2e.
- **Existing code:**
  - `tests/e2e/` — check for existing Phase 3 e2e patterns (e.g., `test_remediate_e2e.py` or similar). Mirror their structure (`@pytest.mark.phase03_e2e` precedent, fixture-loading pattern, `SubprocessJail` invocation pattern).
  - `src/codegenie/cli/` — `codegenie remediate` entry point; the e2e invokes the CLI as a subprocess (via `SubprocessJail`) not as a direct Python call.

## Goal

Land `tests/e2e/test_distroless_migration_e2e.py` (`@pytest.mark.phase07_e2e`) that exercises the full vulnerable-Node.js-on-Alpine → Chainguard-distroless migration path end-to-end. The test runs on a `--privileged` Linux runner, builds the migrated image via `docker buildx`, runs `npm test` against the built image inside `SubprocessJail`, and asserts the `remediation-report.yaml` shape + the migrated Dockerfile contents. CLI exits 0; no PR is opened.

## Acceptance criteria

**CLI invocation + exit code (AC-1, AC-2)**
- [ ] **AC-1** The e2e invokes `codegenie remediate <fixture-path> --cve <pinned-cve-id>` as a subprocess (via the existing `SubprocessJail` wrapper used by Phase 3 e2es) against `tests/fixtures/portfolio/node-vulnerable-base-only/`. The CVE ID is pinned in the fixture's README (S12-01 AC-3) and re-pinned at the top of the e2e file as `_PINNED_CVE = "CVE-2026-openssl-base-only"` (or whatever the fixture uses) — verified by a guard that asserts the CVE matches the fixture's recorded value (Rule 9 — tests verify intent).
- [ ] **AC-2** The subprocess exits with code 0 (success). Verified by `assert result.returncode == 0, result.stderr` — failure message includes stderr so future debugging can see WHY the migration failed without having to re-run.

**Migrated Dockerfile assertions (AC-3, AC-4, AC-5)**
- [ ] **AC-3** After the run, the fixture's working copy (under the test's `tmp_path` — the fixture is copied, NEVER mutated in-place) has a modified `Dockerfile` whose `FROM` line matches `FROM cgr.dev/chainguard/node` (regex: `^FROM cgr\.dev/chainguard/node(:[\w.-]+)?(@sha256:[0-9a-f]{64})?$`). Verified by reading the Dockerfile + asserting on the parsed FROM line via `dockerfile-parse` (consistent with how the recipe engine reads it — Rule 11).
- [ ] **AC-4** The migrated Dockerfile contains an exec-form `ENTRYPOINT` line (regex: `^ENTRYPOINT \["[^"]+"(,\s*"[^"]+")*\]$`); a shell-form `ENTRYPOINT` would fail S10-03's `DockerfilePolicyGate` and the CLI would have exited non-zero.
- [ ] **AC-5** The migrated Dockerfile contains a `USER nonroot` (or `USER <named-nonroot>` — not `USER root` and not the absent `USER` directive); verified by `dockerfile-parse` AST inspection.

**`remediation-report.yaml` shape (AC-6, AC-7, AC-8)**
- [ ] **AC-6** `<tmp_path>/.codegenie/remediation/<workflow_id>.yaml` exists and validates against the existing Phase 3 `RemediationReport` Pydantic schema (per S6-05 work — `remediation-report.yaml` is a shared primitive). `workflow_id` is round-trippable to `WorkflowId` newtype.
- [ ] **AC-7** The `remediation-report.yaml` lists the swap diff path (`diff_path` field), the three gate outcomes (`gates: [{name: "dockerfile_policy", outcome: "passed"}, {name: "distroless_build", outcome: "passed"}, {name: "shell_invocation_delta", outcome: "passed"}]`), and `confidence: "high"` (per ADR-0004's `AdapterConfidence` enum). Assertions are on typed fields, not on stringified YAML.
- [ ] **AC-8** Golden-file check: `tests/golden/remediation-report/distroless-migration-base-only.yaml` (NEW) pins the expected `remediation-report.yaml` shape modulo time-varying fields (`workflow_id`, `emitted_at`). The e2e reads the actual report, redacts the time-varying fields, and asserts byte-equality with the golden file. Mismatches print a unified diff with a copy-paste-ready `--update-goldens` hint (mirroring Phase 3's golden-file pattern).

**`npm test` execution (AC-9, AC-10)**
- [ ] **AC-9** The e2e runs `npm test` inside `SubprocessJail` against the migrated image (using `docker run --rm <migrated-image-tag> npm test`). The subprocess exits 0. Verified by `assert npm_result.returncode == 0`.
- [ ] **AC-10** `npm_result.stdout` contains the fixture's pinned test-pass marker (a string the fixture's `package.json::scripts.test` deliberately prints, e.g., `"all tests passed: 7/7"`). Pins behavioral evidence, not just exit code (Rule 12 — fail loud).

**No-PR invariant (AC-11)**
- [ ] **AC-11** After the e2e completes, no PR is opened against any remote. Verified by asserting `gh` was NOT invoked (the `SubprocessJail` records all subprocess calls; assert `"gh" not in [call.binary for call in jail.recorded_calls]`). Phase 7 writes diffs and reports but does not push — this is the Phase-7-stops-here invariant from `High-level-impl.md §Step 12` line 448–449 and ADR-0001.

**Marker + runner gating (AC-12, AC-13)**
- [ ] **AC-12** The e2e is decorated `@pytest.mark.phase07_e2e`. The marker is registered in `pyproject.toml [tool.pytest.ini_options].markers` with description `"phase07_e2e: Phase 7 end-to-end test; requires --privileged Linux runner"`.
- [ ] **AC-13** The e2e includes a `pytest.importorskip` / `pytest.skip` guard for non-Linux platforms (macOS dev loops cannot run Docker-in-Docker `--privileged`). Skip reason: `"phase07_e2e requires Linux --privileged runner"`. The skip path is opt-in: setting `CODEGENIE_FORCE_PHASE07_E2E=1` overrides the skip (for the case where someone runs the test on a Linux dev box). Verified by parametrizing the skip-condition test: with the env var → not skipped; without → skipped on darwin.

**Gates inherited from Definition of Done**
- [ ] **AC-14** `make check` green excluding `phase07_e2e` (the e2e is opt-in per Phase 7 ADR-0015 + open question §6).
- [ ] **AC-15** `pytest -m phase07_e2e tests/e2e/test_distroless_migration_e2e.py` green on a `--privileged` Linux runner (CI matrix-split job).
- [ ] **AC-16** Byte-edit allowlist fence S5-01 green: this story adds files only under `tests/e2e/` + `tests/golden/remediation-report/`; the `pyproject.toml` marker registration consumes the existing `[tool.pytest.ini_options].markers` allowlist row (no new byte-edit allowlist row needed — markers config is a Phase 0 surface meant for incremental additions).
- [ ] **AC-17** `mypy --strict tests/e2e/test_distroless_migration_e2e.py` clean.

## Implementation outline

1. Read existing Phase 3 e2e pattern: identify the `SubprocessJail` invocation idiom, the marker registration convention, the golden-file pattern. Mirror it exactly (Rule 11).
2. Author the e2e:
   - `setup`: copy `tests/fixtures/portfolio/node-vulnerable-base-only/` into a `tmp_path`.
   - `act`: invoke `codegenie remediate <tmp_path> --cve <pinned>` via `SubprocessJail`.
   - `assert`: exit code 0 + Dockerfile assertions + `remediation-report.yaml` golden equality + `npm test` exit code 0 + `gh` not invoked.
3. Author the golden file `tests/golden/remediation-report/distroless-migration-base-only.yaml` by running the e2e once (manually), capturing the output, redacting time-varying fields, and committing.
4. Add the marker registration to `pyproject.toml`.
5. Add CI workflow file (or amend existing) to run `pytest -m phase07_e2e` on `--privileged` Linux runners when the `phase07-e2e` label is present on the PR (or always on `main`-merge). The full CI config lands in S12-05 — this story only adds the marker + the matching pytest selection guard; S12-05 owns the GitHub Actions workflow YAML.
6. Verify the e2e is **deterministic**: run it twice on the same fixture; the redacted `remediation-report.yaml` must byte-equal the golden file both times.

## TDD plan (red-green-refactor)

### Red
1. Write `tests/e2e/test_distroless_migration_e2e.py::test_base_only_alpine_migrates_to_chainguard_distroless` with the AC-1..AC-11 assertions stubbed in. Initial run: the test fails because either (a) the marker isn't registered (`PytestUnknownMarkWarning`), (b) the migration plugin doesn't resolve to the fixture's CVE (catalog row missing), or (c) the gate chain fails because S10-04 / S10-05 haven't shipped on this branch.
2. If running on macOS dev loop: confirm the test is `skipped (reason='phase07_e2e requires Linux --privileged runner')` per AC-13 — this is the "red" on dev loops; CI on Linux runners is the "red→green" path.

### Green
1. Register the marker in `pyproject.toml`.
2. Verify on a Linux `--privileged` runner: the e2e completes; the migrated Dockerfile + report + `npm test` outputs all match the assertions.
3. Capture the actual `remediation-report.yaml`, redact time-varying fields, commit as the golden file.
4. Re-run; golden equality holds.

### Refactor
1. Extract `_load_phase7_fixture(name) -> Path` into the conftest if not already done by S12-01.
2. Extract the redaction logic for `remediation-report.yaml` time-varying fields into a `_redact_for_golden(report: dict) -> dict` helper (used by S12-03 too for `coordination-summary.yaml` time fields).
3. Mutation guard: temporarily change the recipe's `FROM` target to `cgr.dev/chainguard/python` (a wrong choice). Assert the e2e fails on AC-3. Revert.
4. Mutation guard: temporarily remove the `USER nonroot` line from the recipe output. Assert AC-5 fails AND the `DockerfilePolicyGate` would have failed (so `remediation-report.yaml` would have `gates: [{name: "dockerfile_policy", outcome: "failed", ...}]` → AC-7 also fails). Revert.

## Files to touch

**New files:**
- `tests/e2e/test_distroless_migration_e2e.py`.
- `tests/golden/remediation-report/distroless-migration-base-only.yaml` (golden file; committed after first green run).
- IF Phase 3 e2es don't already have a `_redact_for_golden` helper: `tests/e2e/_golden_redaction.py`.

**Modified files:**
- `pyproject.toml [tool.pytest.ini_options].markers` — register `phase07_e2e`. This is a known Phase 0 surface meant for incremental additions; S5-01's allowlist already covers it via the broader `pyproject.toml` row reservation for Phase 7 metadata edits. Confirm this with S5-01 before landing.

## Out of scope

- The `Both`-coordination e2e — that's S12-03.
- Property tests — that's also S12-03 (the `Both` invariants) and S2-05 / S4-04 (already shipped).
- Adversarial tests — that's S12-04.
- Perf benchmarks — that's S12-05.
- CI workflow YAML for matrix-split — that's S12-05.
- Re-running this e2e against `node-vulnerable-app-only/` or other fixtures — single-plugin app-only is Phase 3's regression e2e (already exists per `bench/vuln-remediation/`); this Phase 7 e2e is single-plugin **base-only**.

## Notes for the implementer

- **`SubprocessJail` is the gate, not `subprocess.run` directly.** Per Phase 5 ADR / repo convention, all subprocess invocations in tests must go through the jail wrapper so the runtime closure stays auditable. If your IDE's autocomplete suggests `subprocess.run(...)` — STOP and use the jail.
- **The `npm test` step is the load-bearing behavioral assertion.** Without it, the e2e proves "the migrated Dockerfile builds" but not "the migrated container actually runs the app's tests." If `npm test` is flaky in CI (it shouldn't be — the fixture's `package.json::scripts.test` is a deterministic local-only smoke test), pin the failure mode in this story's `_attempts/` log; don't weaken the assertion.
- **Golden-file equality is sensitive to YAML ordering.** Use Pydantic's `model_dump_json(indent=2)` then `yaml.safe_dump(..., sort_keys=True)` — never raw `yaml.safe_dump` without sort_keys (different platforms can produce different orderings).
- **The marker is opt-in for a reason.** Per open question §6 (S12-05), `phase07_e2e` is opt-in per-PR via label, mandatory on `main`-merge. This story registers the marker + the skip guard; S12-05 owns the CI workflow that enforces the policy.
- **Fail loud on resolution failures (Rule 12).** If `codegenie remediate` exits non-zero, the assertion message must include the full `stderr` — debugging an e2e failure with only "expected 0, got 1" wastes hours. The AC-2 assertion message pattern is `assert result.returncode == 0, f"codegenie remediate failed:\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}"`.
- **Surface conflicts (Rule 7).** If Phase 3 e2es use a different marker (`phase03_e2e`) but the same `SubprocessJail` pattern, mirror the marker idiom; don't blend with a hybrid name.
- **No `pytest.mark.skipif(platform.system() != "Linux", ...)`.** Use `pytest.skip(...)` inside the test body with a check on `sys.platform` so the skip reason is visible in `pytest -v` output (per `tests/e2e/`-existing precedent if applicable). If existing Phase 3 e2es use `skipif`, match that — Rule 11.
