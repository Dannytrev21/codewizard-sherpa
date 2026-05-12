# Story S7-01 — Test fixture portfolio: `.bundle` + `npm-resolution.json` + pinned npm registry mirror

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S5-05 (full `codegenie remediate` CLI vertical — fixtures must run end-to-end against the real coordinator)
**ADRs honored:** ADR-0012 (three-part fixture model = `.bundle` + recorded `npm-resolution.json` + pinned local registry mirror; quarterly rotation gated by ADR amendment), ADR-0011 (mirror is the load-bearing primitive for the determinism canary — locale + canonicalization neutralize the rest), ADR-0014 (`npm` is the only ALLOWED_BINARIES surface that touches the mirror; wrapper invariants preserved), ADR-0013 (no LLM anywhere in fixture generation tooling)

## Context

Every Phase 3 integration / adversarial / determinism / perf test that calls `codegenie remediate` end-to-end consumes a fixture. The naive bundles-only model lifted from best-practices froze the *repo* but not the *registry resolution* — `npm install --package-lock-only` against today's live `npmjs.org` produces a different lockfile than it would have on bundle-creation day, so goldens flake on every registry re-publish. ADR-0012 closes this with a **three-part fixture model**: the `.bundle` (the repo at a frozen commit), the recorded `npm-resolution.json` (what `npm` resolved on bundle-creation day), and a pinned local registry mirror (~5 MB tarball-stub directory) — `npm install` runs against `file://.../npm-mirror` and the diff is asserted against the recorded resolution. Tests are offline, deterministic against registry drift, and run against the real coordinator (no resolver mocks).

This story ships the portfolio. **No story after S7-01 can run an integration / adversarial / determinism / perf test without consuming these fixtures.** It is the load-bearing dependency for S7-02 (adversarial corpus), S7-03 (determinism canary), S7-04 (perf canaries), S7-05 (Phase-2 regression gate), and the integration tests in S5-05 retroactively use these once they land. The mirror integrity test (`test_fixture_mirror_pin_integrity.py`) is the CI gate that makes silent mirror drift impossible.

The portfolio target is **six bundles**: `express` (the canary; happy-path single-CVE upgrade), `pnpm-workspace` (selector returns `reason="unsupported_dialect"`), `yarn-classic` (same), `peer-dep-conflict` (engine refusal — `reason="peer_dep_conflict"`), `monorepo` (multi-package; targets one workspace member), `postinstall-rce-attempt` (the canonical npm-install-postinstall-blocked adversarial fixture; consumed by S7-02). The `express` bundle is the determinism canary's input (S7-03); the same `express` bundle is the perf canary's input (S7-04).

The mirror must contain the **transitive dependency closure** of every fixture's lockfile — every tarball the lockfile resolves to, content-addressed. Mirror tarballs are stubs (the smallest valid tarball that satisfies `package.json` + the integrity hash); they are not full-fidelity copies of upstream tarballs because the install path is `--ignore-scripts --no-audit --no-fund` (S3-01 wrapper invariant) and only the lockfile resolution is asserted — tarball contents past `package.json` + `index.js` placeholder are never executed in the test path. Open Question #2 picks the **recording mechanism**: `npm install --json --package-lock-only` output against the mirror, captured canonically into `npm-resolution.json`. The mirror size target is **≤ 5 MB total**; CI emits a warning at ≥ 5 MB and a hard regeneration trigger at ≥ 10 MB per ADR-0012 + Open Question #8.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #15 "Fixture portfolio"` — the three-part model definition, mirror size budget, rotation policy.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 5 — Test fixture maintenance / rotation policy"` — quarterly rotation, out-of-cycle triggers, mirror size growth response.
  - `../phase-arch-design.md §"Testing strategy" §"Golden-file tests"` — the goldens shape (`tests/golden/transforms/<recipe-id>/<fixture>/expected.patch`) that this fixture portfolio feeds.
- **Phase ADRs:**
  - `../ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — the load-bearing ADR; read it end-to-end before touching this story.
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — the canonicalization step the mirror enables.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `npm` is allow-listed (this story invokes `npm` only via the S3-01 wrapper, never directly).
- **Production ADRs:** `../../../production/adrs/` — no direct dependency; the fixture model is Phase-3-local.
- **Source design:**
  - `../final-design.md §"Determinism" #20` — three-part fixture model rationale.
  - `../final-design.md §"Departures from all three inputs" #4` — synth's departure from best-practices' bundles-only proposal.
  - `../final-design.md §"Open questions" #2` — the `npm-resolution.json` recording mechanism resolves here.
  - `../final-design.md §"Open questions" #8` — mirror size budget.
  - `../High-level-impl.md §"Step 7"` — the row that pins this story's outputs.
- **Existing code:**
  - `src/codegenie/tools/npm.py` (S3-01) — the only path that runs `npm install`; wrapper-level `--ignore-scripts --no-audit --no-fund` invariant.
  - `src/codegenie/recipes/cache_keys.py` (S3-08) — `registry_mirror_digest` is one of the four cache-key components; this story is what makes that component meaningful.
  - `src/codegenie/audit_writer.py` (Phase 2) — `cve.feed.synced` event format is the precedent for the canonical-JSON style used in `npm-resolution.json`.
  - `tests/conftest.py` (Phase 2) — extend with `bundle_fixture` + `npm_mirror` pytest fixtures.
- **Style reference:**
  - `../../02-context-gather-layers-b-g/stories/S8-01-adversarial-corpus-completion.md` — fixture-shape story; this story is its Phase-3 analog but ships the *substrate* the adversarial corpus stands on, not the corpus itself.

## Goal

Land six `.bundle` files + recorded `npm-resolution.json` files + a pinned `tests/fixtures/npm-mirror/` directory (≤ 5 MB) + `digests.yaml` mirror integrity manifest + `tests/integration/test_fixture_mirror_pin_integrity.py` so every downstream integration / adversarial / determinism / perf test can run offline against a registry-drift-immune substrate.

## Acceptance criteria

- [ ] `tests/fixtures/repos_bundles/` contains exactly six `.bundle` files at the canonical names: `express.bundle`, `pnpm-workspace.bundle`, `yarn-classic.bundle`, `peer-dep-conflict.bundle`, `monorepo.bundle`, `postinstall-rce-attempt.bundle`. Each is a valid `git bundle` per `git bundle verify <path>`; each bundle's HEAD ref is `refs/heads/main`.
- [ ] `tests/fixtures/resolutions/<fixture-name>.json` exists for each of the six fixtures. Each file is the canonical-JSON output of `npm install --json --package-lock-only --ignore-scripts --no-audit --no-fund` against the pinned mirror, post-processed with `LockfileCanonicalizer` (S3-09) for byte-stable serialization. The `peer-dep-conflict` fixture's resolution captures the **error** structure (the resolution doesn't succeed; the file records the failure shape so `RecipeSelector` can be asserted against it).
- [ ] `tests/fixtures/npm-mirror/` exists as a directory of tarball-stubs covering the transitive dependency closure of every fixture's lockfile. Total mirror size (`du -sb tests/fixtures/npm-mirror/`) is **≤ 5 MB**; CI warns at ≥ 5 MB.
- [ ] `tests/fixtures/npm-mirror/digests.yaml` pins every tarball's SHA-256 (one entry per tarball, mirroring the `tools/digests.yaml` schema from Phase 2 ADR-0004). The file ships with `schema_version: "v1"` and `additionalProperties: false` enforcement via the same Pydantic loader pattern as `tools/digests.yaml` (extend the existing helper, do not fork).
- [ ] `tests/integration/test_fixture_mirror_pin_integrity.py` exists and is green on `main`. It (a) walks every tarball under `tests/fixtures/npm-mirror/`, (b) computes SHA-256, (c) asserts the digest matches `digests.yaml`, (d) asserts every `digests.yaml` entry has a corresponding on-disk tarball (no orphan entries), (e) asserts the mirror size is ≤ 5 MB.
- [ ] `tests/conftest.py` exposes two new pytest fixtures: `bundle_fixture(name) -> Path` (unpacks the named bundle into `tmp_path` and yields the repo root) and `npm_mirror_url() -> str` (returns the `file://` URL of the pinned mirror; sets `npm config set registry <url>` and `LC_ALL=C` on every `npm` invocation downstream). Both are session-scoped where possible; the bundle unpack is per-test.
- [ ] `scripts/regenerate_fixtures.py` ships as a stdlib-only utility for the quarterly rotation procedure: walks `tests/fixtures/repos_bundles/`, re-bundles each from a checked-out source tree under `tests/fixtures/sources/` (git-ignored; not committed), re-runs `npm install --json --package-lock-only` against the regenerated mirror, writes new `npm-resolution.json` + `digests.yaml`. The script does not run in CI; it runs locally during a rotation PR.
- [ ] No fixture under `tests/fixtures/` exceeds 1 MB individually except the mirror as a whole (which is bounded by the 5 MB total cap). The `postinstall-rce-attempt` bundle is ≤ 32 KB (it contains one `package.json` + one `preinstall` script payload + nothing else).
- [ ] `docs/runbooks/regenerate-fixtures.md` exists (the runbook referenced in ADR-0012 §Consequences) and documents (a) the quarterly cadence + ADR-amendment requirement, (b) the out-of-cycle triggers (npm major-version bump, CVE-feed schema change), (c) the `scripts/regenerate_fixtures.py` invocation, (d) the mirror size escalation path at ≥ 10 MB (git-lfs vs lazy-fetch).
- [ ] `tests/fixtures/REGENERATION-LOG.md` exists as an append-only ledger; the first entry records this story's PR + the npm minor version that produced the initial portfolio.

## Implementation outline

1. **Build the sources tree.** Under `tests/fixtures/sources/` (git-ignored), check out the six target repos at curated commits. The `express` source is a single-package repo; the `pnpm-workspace` source has `pnpm-workspace.yaml` + two members; `yarn-classic` has a `yarn.lock`; `peer-dep-conflict` has a constructed `package.json` that forces npm to refuse install with a `ERESOLVE` peer-dep error; `monorepo` is a small Lerna-style or workspaces tree with two packages and a known CVE in one dep of the second package; `postinstall-rce-attempt` has a `preinstall: rm -rf /` script payload (the wrapper-level `--ignore-scripts` invariant is what tests will assert blocks it).
2. **Generate the mirror.** For each source's `package-lock.json`, enumerate the transitive tarballs. For each tarball, **construct a stub** — a minimum-content tarball whose `package.json` matches what the lockfile expects and whose contents past that are empty (or a one-line `index.js` stub). The stub's tarball SHA-256 must match what the lockfile's `integrity` field expects; this means generating the lockfile against the stub mirror, not against `npmjs.org`. The bootstrap procedure: (a) clone the source, (b) point `npm config set registry file://.../bootstrap-mirror`, (c) start with an empty mirror, (d) run `npm install --package-lock-only`, (e) for every tarball npm requests, generate a stub with the expected `package.json`, write it to the mirror, regenerate the integrity hash, update `digests.yaml`, repeat until convergence. Document the procedure in `scripts/regenerate_fixtures.py`.
3. **Record the canonical resolutions.** Once the mirror converges, run `npm install --json --package-lock-only --ignore-scripts --no-audit --no-fund` against the mirror; pipe through `LockfileCanonicalizer` (S3-09) for byte-stable serialization; write to `tests/fixtures/resolutions/<fixture-name>.json`. For `peer-dep-conflict`, capture the `npm` stderr error structure (the resolution fails; the file records the failure shape).
4. **Build the bundles.** For each source, `git bundle create tests/fixtures/repos_bundles/<name>.bundle --all` (or `main` only if the source has stale branches). `git bundle verify <path>` to confirm.
5. **Write `digests.yaml`.** Use the Pydantic loader pattern from `tools/digests.yaml` (Phase 2 ADR-0004). Schema: `{schema_version: "v1", tarballs: {<filename>: {sha256: "<hex>", size_bytes: <int>}}}`. `additionalProperties: false`.
6. **Land `tests/integration/test_fixture_mirror_pin_integrity.py`** — the mirror integrity gate. Walk + hash + assert. Fail loud on any drift or orphan.
7. **Extend `tests/conftest.py`** with the `bundle_fixture` + `npm_mirror_url` fixtures. The `npm_mirror_url` fixture also sets `LC_ALL=C` in the environment for the test process (ADR-0011 invariant) and configures `npm config set registry <url>` per session.
8. **Ship `scripts/regenerate_fixtures.py`** — the rotation utility. Stdlib + the same Pydantic loader. < 200 LOC.
9. **Write `docs/runbooks/regenerate-fixtures.md`** — runbook per ADR-0012 §Consequences.
10. **Append to `tests/fixtures/REGENERATION-LOG.md`** the initial-portfolio entry with the npm minor version + date + this story's PR URL.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/integration/test_fixture_mirror_pin_integrity.py`

```python
"""ADR-0012 | Invariant: every tarball under tests/fixtures/npm-mirror/ matches digests.yaml byte-for-byte; no orphans; ≤ 5 MB total."""

def test_every_tarball_matches_digests_yaml() -> None: ...
def test_no_orphan_entries_in_digests_yaml() -> None: ...
def test_mirror_size_under_5mb_warns_under_10mb_fails() -> None: ...
def test_digests_yaml_rejects_extra_top_level_keys() -> None: ...
```

Each test red-fails first (the mirror does not exist yet); green when steps 1–5 land. The size test is a soft-fail at 5 MB (CI warning), hard-fail at 10 MB.

Path: `tests/integration/test_bundles_verify_clean.py`

```python
"""ADR-0012 | Invariant: every .bundle under tests/fixtures/repos_bundles/ passes `git bundle verify`."""

def test_all_bundles_verify() -> None: ...
def test_each_bundle_has_main_ref() -> None: ...
```

Path: `tests/integration/test_resolutions_are_canonical.py`

```python
"""ADR-0011 + ADR-0012 | Invariant: every npm-resolution.json is byte-identical when re-serialized via LockfileCanonicalizer."""

def test_each_resolution_is_a_canonicalizer_fixed_point() -> None: ...
def test_peer_dep_conflict_resolution_captures_eresolve_shape() -> None: ...
```

Path: `tests/unit/test_bundle_fixture_pytest_fixture.py`

```python
"""Pytest fixture sanity — bundle unpacks into tmp_path, npm_mirror_url returns a file:// URL with LC_ALL=C set."""

def test_bundle_fixture_unpacks_into_tmp_path(bundle_fixture) -> None: ...
def test_npm_mirror_url_is_a_file_url(npm_mirror_url) -> None: ...
def test_npm_mirror_setup_sets_lc_all_c(monkeypatch, npm_mirror_url) -> None: ...
```

### Green — make each one pass

The green path is the implementation outline above, executed in order. The most error-prone step is **mirror convergence** (step 2): the stub-tarball SHA-256 must satisfy the lockfile's `integrity` field, which is a chicken-and-egg constraint solved by the bootstrap loop. Expect 2–3 iterations of (add stub → re-run `npm install --package-lock-only` → capture new tarball request → add stub) per fixture before convergence; the `peer-dep-conflict` fixture intentionally never converges (the install errors out, that's the test).

For the canonical-JSON resolution recording, **always pipe through `LockfileCanonicalizer`**. Raw `npm install --json` output is non-deterministic in key ordering on some npm minor versions; the canonicalizer is the load-bearing primitive that makes the resolution file byte-stable across hosts.

### Refactor — clean up

After green:

- **Mirror size audit.** Run `du -sb tests/fixtures/npm-mirror/` and `du -sh tests/fixtures/repos_bundles/`. If the mirror approaches 5 MB, look for tarballs whose `package.json` carries unnecessary fields (npm includes `_npmUser`, `_npmVersion`, etc. in some metadata paths — strip them in the stub).
- **Bundle compression.** `git bundle create --pack-options=--compression=9` is the default; verify each bundle is < 1 MB. The `postinstall-rce-attempt` bundle should be the smallest (single file, < 32 KB).
- **De-duplicate the conftest fixtures.** If `bundle_fixture` and `npm_mirror_url` end up with overlapping setup logic, factor into a private helper.
- **Confirm `LC_ALL=C` is set every time `npm` is invoked.** The `npm_mirror_url` fixture must set it on the pytest process env; the S3-01 wrapper sets it on the subprocess env. Both layers are belt-and-braces per ADR-0011.
- **Open the PR with the regeneration-log entry pre-filled.** Reviewers should see "initial portfolio @ npm v9.8.x, mirror = 4.2 MB, six bundles" without re-deriving the numbers from CI logs.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos_bundles/express.bundle` | Canary fixture — happy-path single-CVE upgrade; consumed by S7-03 + S7-04 + S5-05 integration tests. |
| `tests/fixtures/repos_bundles/pnpm-workspace.bundle` | Selector `reason="unsupported_dialect"` integration. |
| `tests/fixtures/repos_bundles/yarn-classic.bundle` | Selector `reason="unsupported_dialect"` integration. |
| `tests/fixtures/repos_bundles/peer-dep-conflict.bundle` | Selector `reason="peer_dep_conflict"` integration. |
| `tests/fixtures/repos_bundles/monorepo.bundle` | Workspaces resolver path; consumed by S7-02 adversarial. |
| `tests/fixtures/repos_bundles/postinstall-rce-attempt.bundle` | The canonical `--ignore-scripts` adversarial fixture; consumed by S7-02. |
| `tests/fixtures/resolutions/<fixture-name>.json` (×6) | Recorded canonical resolution per ADR-0012. |
| `tests/fixtures/npm-mirror/` (directory) | Pinned local registry mirror (tarball stubs); ≤ 5 MB total. |
| `tests/fixtures/npm-mirror/digests.yaml` | Per-tarball SHA-256 pin manifest; `schema_version: "v1"`. |
| `tests/integration/test_fixture_mirror_pin_integrity.py` | Mirror integrity gate; CI-blocking. |
| `tests/integration/test_bundles_verify_clean.py` | `git bundle verify` gate per bundle. |
| `tests/integration/test_resolutions_are_canonical.py` | LockfileCanonicalizer fixed-point gate. |
| `tests/conftest.py` (extend) | New `bundle_fixture` + `npm_mirror_url` pytest fixtures; session-scoped where possible. |
| `scripts/regenerate_fixtures.py` | Quarterly rotation utility; stdlib + Pydantic loader; < 200 LOC. |
| `docs/runbooks/regenerate-fixtures.md` | Rotation runbook per ADR-0012 §Consequences. |
| `tests/fixtures/REGENERATION-LOG.md` | Append-only ledger; initial portfolio entry. |

## Out of scope

- **The adversarial corpus itself.** S7-02 lands the ≥ 30 adversarial tests; this story only ships the `postinstall-rce-attempt.bundle` substrate that S7-02 consumes.
- **The determinism canary test.** S7-03 lands `test_byte_identical_diff_5x.py`; this story ships the `express` bundle it runs against.
- **The perf canary tests.** S7-04 lands the latency + cache-hit-rate + memory canaries; this story ships the substrate.
- **The Phase-2 regression hard-gate test.** S7-05 lands `test_phase2_unchanged.py`; this story ships nothing for it because the Phase-2 hard-gate runs against the `nestjs/nest` pin, which is a Phase-2 fixture not a Phase-3 fixture.
- **The Phase-4 handoff contract test.** S7-06 lands `test_phase4_handoff_contract.py`; this story ships nothing for it.
- **CI workflow wiring.** S7-07 wires the `test_fixture_mirror_pin_integrity` job into `.github/workflows/`; this story lands the test, S7-07 wires the gate.
- **Migration to git-lfs.** ADR-0012 says > 10 MB triggers a git-lfs or lazy-fetch migration. The initial portfolio is ≤ 5 MB by design; the migration is out of scope.
- **Live-registry tests.** No test in this story (or any Phase 3 story) talks to `npmjs.org`. The mirror is the registry.

## Notes for the implementer

- **Read ADR-0012 end-to-end before writing a single line of code.** The three-part fixture model is the load-bearing decision; the implementation details (which canonicalization order, which stub-tarball shape, which size cap escalation path) are pinned in the ADR. Do not invent new structure.
- **The mirror bootstrap is iterative, not declarative.** You cannot write the mirror in one pass because the lockfile's integrity hashes depend on the tarball contents you choose. The convergence loop (add stub → re-resolve → capture new tarball request → repeat) is the procedure; `scripts/regenerate_fixtures.py` automates it for rotations but the *first* generation is hand-driven. Plan 1–2 days for the convergence; document the gotchas in the runbook.
- **`peer-dep-conflict` intentionally never converges.** The fixture's contract is that `npm install --package-lock-only` errors out with `ERESOLVE`. Capture the *error shape* in `resolutions/peer-dep-conflict.json` (the stderr structure) so the selector test can assert against it without re-running `npm`.
- **The `postinstall-rce-attempt` fixture's payload must be visibly hostile.** `rm -rf /` is the canonical scare; alternatively `node -e "require('fs').writeFileSync('/tmp/pwned', '1')"` is sufficient and less alarming in code review. Either way, the test in S7-02 will assert the wrapper blocks it *before* the subprocess starts — so the payload never executes regardless. Document this loudly in the bundle's commit message.
- **Mirror tarball stubs must satisfy `npm`'s integrity check or `npm install` fails before the test starts.** This is the most fragile step; mistakes here cause cascading test failures across the entire integration suite. When in doubt, regenerate the affected tarball's SHA-256 against the actual stub bytes and update `digests.yaml` in lock-step.
- **`LC_ALL=C` is set in three places** (ADR-0011 belt-and-braces): (a) the pytest process env via `npm_mirror_url` fixture, (b) the S3-01 wrapper's subprocess env, (c) the `LockfileCanonicalizer` post-processing. All three must hold; if any drops, the determinism canary in S7-03 starts flaking on locale-divergent hosts.
- **The 5 MB cap is not aspirational.** ADR-0012 §"Tradeoffs" pins it; `test_fixture_mirror_pin_integrity.py` enforces it. If you find yourself approaching 4.5 MB on the initial portfolio, **add fewer transitive deps to the source repos**, not a bigger cap. The cap forces fixture discipline; the alternative is unbounded mirror growth which forces a git-lfs migration the team does not want yet.
- **The quarterly rotation discipline starts now, not later.** Append the initial-portfolio entry to `tests/fixtures/REGENERATION-LOG.md` in this same PR; the next rotation PR will see the template and follow it. Without the ledger, rotations become silent drift.
- **`scripts/regenerate_fixtures.py` runs locally, not in CI.** CI verifies mirror integrity (`test_fixture_mirror_pin_integrity.py`); CI does **not** regenerate fixtures. Mixing the two would make CI runs non-deterministic by definition. Document this in the runbook.
- **Surface the `tests/fixtures/sources/` git-ignore decision in the PR body.** Some reviewers will expect sources to be checked in; the rationale (sources are checked out from upstream URLs documented in the runbook; only the derived artifacts — bundles + resolutions + mirror — are version-controlled) deserves a one-paragraph note.
