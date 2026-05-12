# ADR-0012: Test fixtures = `.bundle` + recorded `npm-resolution.json` + pinned local registry mirror; quarterly rotation policy

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** test-fixtures · registry-drift · determinism · synthesizer-departure · phase-evolution
**Related:** ADR-0011, [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-tools-digests-yaml-pin-manifest.md), [Phase 1 ADR placeholders]

## Context

Best-practices proposed test fixtures as `.bundle` files (git bundles) committed under `tests/fixtures/repos_bundles/`. The critic dismantled this (`critique.md §"Attacks on best-practices" §"Concrete problems" #5`):

> Git bundles freeze the *registry resolution* at bundle creation time. A bundle of `repo_clean_express` has the `package-lock.json` from whenever the bundle was made; the test asserts that `ncu` + `npm install` produces the *expected golden diff*. But `npm install` against today's registry can produce a different lockfile than `npm install` against the registry on bundle-creation day. The golden diff is not testing the resolution logic; it's testing the cached frozen resolution.

The two failure modes:

1. If CI runs against the live `npmjs.org` registry, registry mutation (re-publishes, transitive moves) silently invalidates the goldens — drift fails CI on every registry mutation, not on actual recipe-logic regressions.
2. The team either mass-regenerates goldens (defeating the discipline) or green-paints over real regressions.

The synthesis adds two structural pins on top of the bundle (`final-design.md §"Determinism" #20`, `§"Departures from all three inputs"` #4): the recorded `npm-resolution.json` (the exact resolver output on bundle-creation day) and a pinned local registry mirror under `tests/fixtures/npm-mirror/`. The combination removes both registry drift and resolver drift as test-flakiness axes.

## Options considered

- **`.bundle` only [B].** Brittle to registry drift. Goldens are "what npm resolved on bundle-creation day vs. today" — wrong axis.
- **`.bundle` + live `npmjs.org` [strictest reality].** Most realistic. CI flakes on every registry mutation; unsustainable.
- **`.bundle` + recorded `npm-resolution.json` (no live registry) [partial pin].** Asserts the recorded resolution against the bundle. Doesn't run `npm install`; loses the install-validation property.
- **`.bundle` + recorded `npm-resolution.json` + pinned local registry mirror under `tests/fixtures/npm-mirror/` (~5 MB) [synth].** Full pin — `npm install` against a frozen tarball-stub directory produces deterministic resolution; goldens assert against the recorded resolution; tests are deterministic against npm registry drift.

## Decision

**Each test fixture is a three-part tuple:**

1. **`.bundle` file** at `tests/fixtures/repos_bundles/<fixture-name>.bundle` — a git bundle containing the fixture repo at a frozen commit (`package.json`, `package-lock.json`, source tree, test suite).
2. **Recorded `npm-resolution.json`** at `tests/fixtures/resolutions/<fixture-name>.json` — the exact result of `npm install --package-lock-only` against the pinned mirror on bundle-creation day. Mechanism TBD per `phase-arch-design.md §"Open questions"` #2: candidates are `npm install --json --package-lock-only` output or a custom canonical extract.
3. **Pinned local registry mirror** at `tests/fixtures/npm-mirror/` — a tarball-stub directory (~5 MB total). Lazy-loaded by test setup. Contains every tarball any fixture's lockfile resolves to. Tarball hashes pinned in `tests/fixtures/npm-mirror/digests.yaml`.

Tests run `ncu` + `npm install --package-lock-only` against the pinned mirror (via `npm config set registry file://.../npm-mirror`) and assert the diff against the recorded `npm-resolution.json`. **No live `npmjs.org` egress in the test path.**

**Rotation policy:**

- **Quarterly rotation cycle.** Every quarter, regenerate the fixture portfolio with fresh `.bundle` + `npm-resolution.json` + mirror tarball-stubs. Gated by an ADR amendment that documents what changed.
- **Out-of-cycle triggers:** npm major-version bumps trigger an unplanned rotation; CVE-feed schema changes trigger one for the relevant fixture.
- **Pinning what doesn't rotate:** the recorded `npm-resolution.json` is the authoritative "what npm would produce on this lockfile + registry-mirror combination today" — never re-derived from live `npm install` in CI.
- **Mirror size budget:** ≤ 5 MB target; ≥ 10 MB triggers a git-lfs or lazy-fetch migration (`final-design.md §"Open questions"` #8).
- **CI guards:** the determinism canary (ADR-0011) fails loudly if the registry mirror is missing or hash-mismatched; fixture regeneration is therefore an explicit gated event, not silent drift.

## Tradeoffs

| Gain | Cost |
|---|---|
| Tests are deterministic against npm registry drift — re-publishes and transitive moves cannot flake CI | Quarterly rotation is a real maintenance cost; documented runbook + tooling required |
| Goldens assert against the recorded resolution, not against today's live resolution — drift fails CI only on actual recipe-logic regressions | Fixture portfolio grows (3 files per fixture × N fixtures); ~5 MB mirror target keeps disk footprint reasonable |
| `npm install` runs against the mirror — install-validation property is preserved (we're not just asserting the recorded resolution) | Mirror tarball-stub format requires care: must contain exact bytes for every dep, including transitive |
| Mirror is content-addressed (digests.yaml) — any silent edit produces a loud test failure | Adding a new fixture requires regenerating the mirror or extending it (operational tooling) |
| CI runs offline — no `npmjs.org` egress in tests; faster, more deterministic, no rate-limit risk | Mirror cannot model the full registry; only fixtures' dependency closures are represented |
| Quarterly rotation is gated by ADR amendment — rotation is reviewed, not silent | Quarterly review is a recurring sprint task |
| `tests/integration/test_fixture_mirror_pin_integrity.py` asserts mirror tarball hashes against `tests/fixtures/npm-mirror/digests.yaml` — same discipline as Phase 2 ADR-0004 | Mirror regeneration tooling must compute and commit the digests; CI lint asserts |
| Mirror size budget (≤ 5 MB, ≥ 10 MB trigger) prevents unbounded fixture growth | Size cap may force fixture pruning over time; CI alert on size growth |

## Consequences

- `tests/fixtures/repos_bundles/*.bundle` — git bundles per fixture.
- `tests/fixtures/resolutions/*.json` — recorded resolution per fixture.
- `tests/fixtures/npm-mirror/` — pinned tarball-stub directory with `digests.yaml`.
- `tests/conftest.py` or per-test setup sets `npm config set registry file://.../npm-mirror` before `npm install`.
- `tests/integration/test_fixture_mirror_pin_integrity.py` asserts mirror integrity.
- `tests/integration/test_remediate_express_e2e.py` and the rest of the integration suite use the three-part fixture model.
- `docs/runbooks/regenerate-fixtures.md` (Phase 3 deliverable, per `phase-arch-design.md §"Gap analysis" §"Gap 5"`) describes the quarterly rotation procedure.
- ADR amendment is the gate for any fixture rotation; the amendment records what changed (npm version, mirror digests, resolution snapshots).
- Phase 4 fixtures inherit the same model; LLM/RAG tests add `tests/fixtures/llm_cassettes/` (Phase 4 ADR).
- Mirror size growth past 10 MB triggers an architectural decision per the open question; flagged for tracking.

## Reversibility

**Medium.** Switching back to bundles-only would immediately surface registry-drift flakiness in CI; high cost to recover. Switching to live `npmjs.org` is mechanically easy but turns every CI run into a registry-mutation lottery. Adopting git-lfs (or lazy-fetch) for the mirror is **purely additive** when size grows. The three-part fixture model is the load-bearing piece; the *specific format* of each part (bundle vs. tarball, JSON vs. YAML resolution) is reversible.

## Evidence / sources

- `../final-design.md §"Determinism"` #20
- `../final-design.md §"Departures from all three inputs"` #4 — three-part fixture model
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Fixture portfolio"
- `../final-design.md §"Test plan" §"Golden-file tests"`
- `../final-design.md §"Open questions"` #2 (recording mechanism), #8 (size)
- `../phase-arch-design.md §"Component design" #15 "Fixture portfolio"`
- `../phase-arch-design.md §"Gap analysis" §"Gap 5 — Test fixture maintenance / rotation policy"`
- `../critique.md §"Attacks on best-practices" §"Concrete problems" #5` — registry drift critique
