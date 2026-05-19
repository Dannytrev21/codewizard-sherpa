# Story S12-01 — Phase 7 fixture portfolio (six trees under `tests/fixtures/portfolio/`)

**Step:** Step 12 — End-to-end test suite + property tests + adversarial tests + regression-gate enforcement
**Status:** Ready
**Effort:** M
**Depends on:** S10-02 (`DockerfileMultiStageRefactorTransform`), S10-04 (`DistrolessBuildGate`), S10-05 (`ShellInvocationDeltaGate`), S11-04 (exit-code-8 wiring)
**ADRs honored:** ADR-0004 (`vuln.provenance` primitive home — fixtures exercise the seven-variant union end-to-end), ADR-0007 (registry stores classes — fixtures load the same registry the e2e tests dispatch against), ADR-0008 (no `vuln.provenance` cache — fixtures must produce the same `Provenance` on repeated reads), ADR-0009 (byte-edit allowlist — fixture trees are net-new files under `tests/fixtures/portfolio/`; no Phase 0–6.5 file is edited), ADR-0010 (Chainguard CVE-image lookup frozen YAML — fixtures carry pinned `image-digest:` snapshot tokens), ADR-0013 (`dockerfile-parse` recipe engine — multi-stage fixture exercises ARG-driven FROM + `COPY --from=` corner cases).

## Context

Step 12 is the convergence step. Every prior story (S1-01 through S11-04) lands here for validation. The two headline e2e tests (`test_distroless_migration_e2e.py`, `test_both_provenance_emits_coordination_event_e2e.py`), three property tests (`test_both_invariant.py`, `test_both_always_emits_coordination.py`, plus the dispatch-order + idempotence tests already shipped in S2-05 / S4-04), the adversarial suite (S12-04), and the perf benchmarks (S12-05) ALL read fixtures from `tests/fixtures/portfolio/`. If the fixtures don't exist — or worse, drift between e2e runs because of stale `image-digest:` resolution — every downstream test in Step 12 is unreliable.

This story ships **six fixture trees** under `tests/fixtures/portfolio/`, each pinned to a specific scenario from `phase-arch-design.md §Fixture portfolio`:

1. `node-vulnerable-alpine/` — Node.js app, Alpine base, vulnerable transitive in app + vulnerable apk pkg in base (the `Both` fixture).
2. `node-vulnerable-app-only/` — Node.js, distroless base already, vulnerable transitive in app (app-only).
3. `node-vulnerable-base-only/` — Node.js, Alpine, vulnerable openssl in base, clean app (base-only).
4. `node-already-distroless/` — Node.js, `cgr.dev/chainguard/node`, no CVEs (no-op).
5. `multi-stage-dockerfile/` — Node.js with shell-using `RUN` lines that must move to a builder stage; ARG-driven FROM; `COPY --from=base` referencing intermediate stage.
6. `node-poisoned-sbom/` — Alpine fixture with fabricated `locations[].layerID` values that don't match the image manifest (cross-references S4-04's Hypothesis property test fixture).

Each fixture is **deterministic**: the `image-digest:<sha256:...>` snapshot token is pinned at fixture-creation time, so probe + adapter outputs are reproducible byte-for-byte across CI runs. No network resolution at test time.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Fixture portfolio` (lines 1295–1303) — the six fixtures verbatim.
  - `../phase-arch-design.md §Scenarios A/B/C/D` (lines 369–516) — the workflow each fixture is meant to drive.
  - `../phase-arch-design.md §Edge cases #1, #5, #7, #13` — multi-stage `COPY --from=base` and ARG-driven FROM corner cases the `multi-stage-dockerfile/` fixture exercises.
- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — fixture catalog entry shape; the e2e fixture's CVE must match a row in `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml`.
  - `../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md` — `dockerfile-parse` must accept every fixture Dockerfile; ARG-driven FROM and heredoc edge cases must produce typed `not_applicable(reason="dockerfile_parse_failed")` rather than crash.
- **Existing code:**
  - `tests/fixtures/portfolio/minimal-ts/` + `monorepo-pnpm/` + `distroless-target/` + `native-modules/` + `stale-scip/` — Phase 1/2 precedent for portfolio fixture shape (directory layout, manifest layout, `.codegenie/` placement).
  - `tests/fixtures/adversarial/dockerfile-*` — Phase 2 precedent for Dockerfile fixtures with `.codegenie/` pre-populated for deterministic probe outputs.
  - `tests/fixtures/syft/` — Phase 4 (S4-01..S4-04) Syft SBOM fixture layout; `node-poisoned-sbom/` mirrors this style with fabricated layerIDs.

## Goal

Land six fixture trees under `tests/fixtures/portfolio/` with pinned `image-digest:` snapshot tokens so every Step 12 e2e / property / adversarial / perf test reads the same deterministic inputs across CI runs. Each fixture carries enough machinery (`Dockerfile`, `package.json`, `package-lock.json`, `.codegenie/context/raw/*.json` pre-populated for probe slices, `sbom.json` if applicable) that downstream tests can run cold without any network resolution.

## Acceptance criteria

**Directory existence + shape (AC-1 through AC-6)**
- [ ] **AC-1** `tests/fixtures/portfolio/node-vulnerable-alpine/` exists with: `Dockerfile` (Alpine base, e.g. `FROM node:18-alpine`), `package.json` (declares a vulnerable transitive), `package-lock.json` (resolved tree showing the vulnerable transitive), `sbom.json` (Syft-shaped, layerIDs match a pinned image manifest), `.codegenie/snapshots/image-digest.txt` containing the pinned `sha256:<...>` digest. README inside the fixture names the CVE and the two-layer attribution (app transitive + apk pkg).
- [ ] **AC-2** `tests/fixtures/portfolio/node-vulnerable-app-only/` exists with: `Dockerfile` (`FROM cgr.dev/chainguard/node`), `package.json` + `package-lock.json` declaring a vulnerable transitive, `sbom.json` showing the transitive in the app layer only. `assemble_provenance` against this fixture returns `AppDirect` or `AppTransitive` — verified by AC-9.
- [ ] **AC-3** `tests/fixtures/portfolio/node-vulnerable-base-only/` exists with: `Dockerfile` (Alpine base), clean `package.json` (no vulnerable deps), `sbom.json` showing a vulnerable `openssl` in the apk layer. `assemble_provenance` returns `BaseImage(...)`.
- [ ] **AC-4** `tests/fixtures/portfolio/node-already-distroless/` exists with: `Dockerfile` (`FROM cgr.dev/chainguard/node`), clean `package.json`, `sbom.json` with no CVEs. The migration plugin's `applicability()` returns `Unknown(reason="base_image_already_distroless")` (Edge case #3).
- [ ] **AC-5** `tests/fixtures/portfolio/multi-stage-dockerfile/` exists with: a Dockerfile containing at least one `RUN sh -c "..."` line that must move to a builder stage, an `ARG NODE_VERSION` driving `FROM node:${NODE_VERSION}-alpine AS base`, a `COPY --from=base /app /app` instruction in the runtime stage, and exec-form `ENTRYPOINT`. `package.json` + `package-lock.json` present. Pinned to a CVE whose remediation requires `DockerfileMultiStageRefactorTransform` (S10-02).
- [ ] **AC-6** `tests/fixtures/portfolio/node-poisoned-sbom/` exists with: `Dockerfile` (Alpine base), `sbom.json` whose `locations[].layerID` values are fabricated (do not match any layer in the pinned image manifest). Cross-references S4-04's Hypothesis property test (this is the deterministic seed case; S4-04 generates 100+ around it).

**Pinned `image-digest:` snapshot tokens (AC-7, AC-8)**
- [ ] **AC-7** Every fixture that carries a `Dockerfile` carries a `.codegenie/snapshots/image-digest.txt` file containing the resolved `sha256:<64 hex>` digest of the base image. The digest format is asserted by a meta-test `tests/fixtures/portfolio/test_phase7_fixture_digests_pinned.py` (parametrized over the six fixtures; each must have a valid `sha256:<64 hex>` line OR an explicit `# already-distroless: <digest>` comment for the `node-already-distroless/` case). Format regex: `^sha256:[0-9a-f]{64}$`.
- [ ] **AC-8** No fixture's `image-digest:` value resolves via network at test time. The meta-test in AC-7 also asserts that `ProbeContext.image_digest_resolver` is constructed with `network_disabled=True` for fixture-driven test sessions (this is the `phase07_e2e_image_resolver` conftest fixture introduced here). Verified by a planted-violation test: temporarily set `network_disabled=False`, run the resolver against a non-existent image, assert the test would have hit a network error → confirms the live tests are isolated.

**Provenance round-trip (AC-9, AC-10)**
- [ ] **AC-9** `tests/integration/test_phase7_fixture_provenance.py` (new) loads each of the six fixtures via the standard plugin-load + `assemble_provenance(...)` path and asserts the expected `Provenance` variant:
  - `node-vulnerable-alpine/` → `Both(AppDirect|AppTransitive, BaseImage)`.
  - `node-vulnerable-app-only/` → `AppDirect` or `AppTransitive` (chain-length-dependent).
  - `node-vulnerable-base-only/` → `BaseImage(...)`.
  - `node-already-distroless/` → `Unknown(reason="base_image_already_distroless")`.
  - `multi-stage-dockerfile/` → `Both(...)` or `BaseImage(...)` depending on the seeded CVE; pinned in the fixture's README.
  - `node-poisoned-sbom/` → `Unknown(reason="sbom_layer_attribution_absent")`.
  Every assertion is on the typed variant, not on stringified output (Rule 9 — tests verify intent).
- [ ] **AC-10** Re-running the fixture-provenance integration test twice produces byte-identical `Provenance` instances (idempotence; locks Edge case #10 — cache miss does NOT change result). Verified via `Provenance.model_dump_json()` equality.

**Determinism + isolation (AC-11, AC-12)**
- [ ] **AC-11** Each fixture is **self-contained**: no fixture depends on another fixture's state. Verified by a meta-test `tests/fixtures/portfolio/test_phase7_fixtures_independent.py` that copies each fixture to a fresh `tmp_path` and asserts `assemble_provenance` produces the same variant as when run in-place.
- [ ] **AC-12** Fixture `Dockerfile` byte-hashes are pinned in `tests/fixtures/portfolio/_phase7_fixture_hashes.txt` (one line per fixture: `<fixture-name>\t<sha256-of-Dockerfile>`); the byte-edit allowlist fence S5-01 reads this file as the per-fixture invariant for adversarial-test isolation. A test asserts every listed file's hash matches the recorded hash; out-of-CODEOWNERS edits fail CI.

**Gates inherited from Definition of Done**
- [ ] **AC-13** `make check` green end-to-end on this branch (fixture creation alone must not regress Phase 3–6.5 — adding fixture files is the only change).
- [ ] **AC-14** Byte-edit allowlist fence S5-01 green: this story adds files ONLY under `tests/fixtures/portfolio/` and `tests/integration/test_phase7_fixture_provenance.py` + meta-tests. No file under `src/codegenie/{plugins,transforms,probes,coordinator}/` is edited.
- [ ] **AC-15** `mypy --strict tests/integration/test_phase7_fixture_provenance.py` clean.

## Implementation outline

1. Author the six fixture trees in dependency order: scaffold each as a small repo with `Dockerfile`, `package.json`, `package-lock.json`, optional `sbom.json`, README, `.codegenie/snapshots/image-digest.txt`.
2. Resolve each base image's `sha256:` digest **once at fixture-authoring time** (via local `docker buildx imagetools inspect <image>` — recorded by hand, NOT at test time), pin in `image-digest.txt`. Document the authoring step in the fixture README.
3. For SBOM-bearing fixtures, run `syft` once at authoring time against the pinned image, commit the output as `sbom.json`. For `node-poisoned-sbom/`, take a real `sbom.json` and mutate `locations[].layerID` to fabricated values.
4. Write `_phase7_fixture_hashes.txt` (sha256 of each `Dockerfile`); meta-test reads + verifies.
5. Write the integration test (`test_phase7_fixture_provenance.py`) parametrized over the six fixtures; the expected `Provenance` variant for each is hardcoded in the test (intent-encoded per Rule 9).
6. Write the two meta-tests (`test_phase7_fixture_digests_pinned.py`, `test_phase7_fixtures_independent.py`).
7. Wire the `phase07_e2e_image_resolver` conftest fixture that constructs `ProbeContext.image_digest_resolver` with `network_disabled=True`.
8. Confirm `make check` green; confirm S5-01 byte-edit fence green.

## TDD plan (red-green-refactor)

### Red (write the failing test first)
1. Author `tests/fixtures/portfolio/test_phase7_fixture_digests_pinned.py` parametrized over the six fixture names. Initially every parametrized case fails because the fixture directory doesn't exist. The test must fail because `pathlib.Path(fixture_dir).exists() is False`, not because of an import error — assert on filesystem state, not on import.
2. Author `tests/integration/test_phase7_fixture_provenance.py` with parametrized `(fixture_name, expected_provenance_variant_type)` pairs. Initially every case errors because `assemble_provenance` cannot run (no fixture inputs).

### Green
1. Create each fixture tree (Dockerfile + manifests + SBOM + image-digest.txt + README).
2. Populate `_phase7_fixture_hashes.txt`.
3. Run the digest-pinning meta-test → green.
4. Run the integration test → green.

### Refactor
1. Extract the fixture-path resolution into a single conftest helper `phase07_fixture(name) -> Path` used across Step 12 stories — DRY before S12-02 and S12-03 land their own fixture-loader code.
2. Verify the integration test would still fail if any fixture's expected `Provenance` variant changed (mutation guard — flip one expected variant to a wrong type, assert the test fails, revert).

## Files to touch

**New files:**
- `tests/fixtures/portfolio/node-vulnerable-alpine/` (`Dockerfile`, `package.json`, `package-lock.json`, `sbom.json`, `README.md`, `.codegenie/snapshots/image-digest.txt`).
- `tests/fixtures/portfolio/node-vulnerable-app-only/` (same shape).
- `tests/fixtures/portfolio/node-vulnerable-base-only/` (same shape).
- `tests/fixtures/portfolio/node-already-distroless/` (same shape, no `sbom.json` needed).
- `tests/fixtures/portfolio/multi-stage-dockerfile/` (same shape, more complex Dockerfile).
- `tests/fixtures/portfolio/node-poisoned-sbom/` (same shape, mutated SBOM).
- `tests/fixtures/portfolio/_phase7_fixture_hashes.txt`.
- `tests/fixtures/portfolio/test_phase7_fixture_digests_pinned.py`.
- `tests/fixtures/portfolio/test_phase7_fixtures_independent.py`.
- `tests/integration/test_phase7_fixture_provenance.py`.

**Modified files (allowlist conformance — none expected):**
- `tests/conftest.py` — IF a global `phase07_fixture(name)` helper makes more sense than a Step-12-local conftest. If added globally, ensure S5-01's allowlist row covers `tests/conftest.py` for this story (likely yes — conftest is test-tree code, not under `src/codegenie/`).

## Out of scope

- Building / publishing fixture Docker images (the pinned `sha256:` digests reference public images; no Docker build at test time).
- E2E or property tests against these fixtures — that's S12-02 / S12-03.
- Adversarial mutation of these fixtures — S12-04.
- Perf benchmarks against these fixtures — S12-05.
- Expanding the fixture portfolio beyond six trees — speculative; not needed for Phase 7 exit criteria.

## Notes for the implementer

- **Pin `sha256:` digests at authoring time, not test time.** The whole point of `image-digest:<resolved>` snapshot tokens (ADR-0004 from Phase 2) is that the gather pipeline runs against an immutable input. If you resolve digests at test time you've defeated the snapshot.
- **The `node-poisoned-sbom/` fixture is the deterministic seed for S4-04's Hypothesis test.** Keep its layerID mutations small and obviously fabricated (e.g., `sha256:` followed by 64 `f` characters) — the test must be able to spot it AND humans must be able to read the fixture diff and see what was tampered with.
- **Fixture READMEs are load-bearing documentation.** Future maintainers will read them to understand what each fixture tests. Name the CVE explicitly; name the expected `Provenance` variant; name the cross-referenced stories (S12-02, S12-03, etc.).
- **`multi-stage-dockerfile/` is the corner-case workhorse.** Include at least: ARG-driven FROM (Edge case #13), `COPY --from=` referencing an intermediate stage (Edge case #7), shell-form RUN that must move (S10-02 work), and exec-form ENTRYPOINT (S10-03 invariant). Document each in the README so future readers can trace which edge case each line targets.
- **Rule 11 — match codebase conventions.** Look at `tests/fixtures/portfolio/minimal-ts/` and `tests/fixtures/adversarial/dockerfile-*` for shape; mirror their layout (top-level `Dockerfile`, top-level manifest files, `.codegenie/` under the fixture root). Don't invent a new layout.
- **Surface conflicts (Rule 7).** If `tests/fixtures/portfolio/*` Phase 1/2 fixtures use a slightly different `.codegenie/` layout than `tests/fixtures/adversarial/`, pick one (the more recent — `adversarial/` is Phase 2) and document the chosen convention in this story's notes. Don't blend.
