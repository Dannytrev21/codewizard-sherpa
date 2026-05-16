# Story S4-02 — `stale-scip` fixture stub + load-bearing adversarial test wired CI-gating

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready · VALIDATED (HARDENED — see `_validation/S4-02-stale-scip-adversarial.md`)
**Effort:** M
**Depends on:** S4-01 (`IndexHealthProbe` with `scip` freshness check registered; the typed `Stale(CommitsBehind(...))` value B2 emits; the on-disk `read_raw_slices(raw_dir(repo.root))` path that reads `<repo>/.codegenie/context/raw/scip.json`)
**ADRs honored:** 02-ADR-0006 (`IndexFreshness` is the typed answer to honest-confidence — `CommitsBehind.n` and `last_indexed` are both asserted), Phase 0 ADR — adversarial corpus convention (`tests/adv/phase02/` is the Phase 2 home; CI job `adv-phase02` is build-gating), [production design.md §2.3 honest-confidence](../../../production/design.md), [`CLAUDE.md`](../../../../CLAUDE.md) "single most important probe is `IndexHealthProbe`"

## Validation notes (2026-05-16)

Seven BLOCK-severity inconsistencies with master + S4-01's hardened surface closed; eight harden findings closed; four design-pattern notes added. Full audit: `_validation/S4-02-stale-scip-adversarial.md`. Highlights:

1. **`Probe.run` is two-argument** `(repo: RepoSnapshot, ctx: ProbeContext)` per Phase 0 ADR-0007 + S4-01 hardened AC-1. Original draft's `asyncio.run(probe.run(ctx))` would have `TypeError`-ed immediately.
2. **No `ctx.sibling_slices`; no `build_probe_context` helper.** Both are phantom. The test constructs `RepoSnapshot` and `ProbeContext` inline mirroring the existing idiom at `tests/unit/probes/test_language_detection_extended.py:29-42`. B2 reads sibling slice data from disk via `read_raw_slices(raw_dir(repo.root))`.
3. **Filename is `scip.json`, not `semantic_index.json`.** B2's `read_raw_slices` keys by `IndexName` stem; for `IndexName("scip")` the file is `scip.json` (per S4-01 hardened cross-story integration handoff). The fixture's seed material lives at the tracked path `_seed/scip-slice.template.json` and `regenerate.sh` substitutes `PARENT_COMMIT` and copies it to the gitignored runtime location `.codegenie/context/raw/scip.json`.
4. **`_clear_for_tests()` is phantom.** Use the `clean_freshness_registry` snapshot-and-restore fixture from S4-01's TDD preamble (snapshots `_checks` + `_origins`; restores in `finally:`). The actual S1-02 API is `unregister_for_tests(index_name)` per-name.
5. **`.git/` cannot be vendored** inside the parent repo (Git refuses nested `.git/` tracking; repo-wide `.gitignore` already ignores `.codegenie/`). Restructured: `regenerate.sh`, `README.md`, `_seed/`, `package.json`, `main.ts` are tracked; `.git/` and `.codegenie/` are runtime-materialized by `regenerate.sh` and gitignored via a fixture-local `.gitignore`.
6. **`regenerate.sh` guard refactored to be env-overrideable** (`LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"`) so `test_regenerate_sh_guard` can deterministically force the guard branch. The original inline guard was dead code (LAST_INDEXED was captured between commits and could never equal post-2nd-commit HEAD).
7. **Discriminated-union round-trip uses `TypeAdapter[IndexFreshness]`** instead of `Stale.model_validate`. Exercises the actual variant-selection path real consumers (S8-01's renderer, Phase 3 adapters) use; gives diagnostic "Expected `Stale`, got `Fresh(...)`" on the load-bearing regression.
8. **Outer-key invariant + per-source confidence asserted at the slice surface** (AC-1 step 1 hardened to `set(slice.keys()) == {"scip"}`; new step 5 pins `confidence == "medium"` per S4-01 AC-9's `CommitsBehind` demote-min mapping).

## Context

This is **the roadmap exit criterion test for Phase 2** ([phase-arch-design.md §"Goals" G2](../phase-arch-design.md), [final-design.md §"Goals"](../final-design.md), [stories/README.md §"Phase exit-criterion traceability"](README.md)). The deliberately-seeded `stale-scip` fixture in `tests/fixtures/portfolio/stale-scip/` is a repo where:
- the `.codegenie/context/raw/scip-index.scip` blob (or the seed `semantic_index` slice) reflects a **prior** commit,
- the working-tree `HEAD` has moved forward by ≥ 1 commit.

S4-01 ships `IndexHealthProbe` (B2). This story ships the **CI-gating adversarial test that proves B2 catches the staleness**. If B2 ever regresses — silently treating the moved HEAD as `Fresh`, or emitting a `Stale` with the wrong reason variant — this test fails and the Phase 2 build fails. That is the operational meaning of "honest confidence" ([production design.md §2.3](../../../production/design.md)): we encode the load-bearing failure mode as a test that gates the build.

**Implementation risk #3 from the manifest** ([`High-level-impl.md §"Risks specific to this step"` #3](../High-level-impl.md)): the assertion must check **both** `CommitsBehind.n >= 1` **AND** `last_indexed != current_HEAD`. Why both? Because B2's `CommitsBehind.n` has a fallback path (S4-01 AC-6): if `git rev-list --count <last_indexed>..<HEAD>` fails (e.g., shallow clone, force-push, fixture-seeded commit not in the analyzed repo's history), `n` falls back to `1`. A test asserting only `n >= 1` would pass even if the fallback fired in a degenerate case — e.g., if the freshness check itself were buggy and silently emitted `Stale(CommitsBehind(n=1, last_indexed="<garbage>"))`. The second assertion (`last_indexed != current_HEAD`) anchors the structural fact: the two commits are genuinely different SHAs. Together they survive any fixture regeneration with a different tool version.

This story lands the fixture as a **stub** with the **seed-vs-runtime split** (DP2 in §Design-pattern notes): tracked seed material (`_seed/scip-slice.template.json`, `regenerate.sh`, `README.md`, `package.json`, `main.ts`, `.gitignore`) plus runtime-materialized state (`.git/`, `.codegenie/`) created by `regenerate.sh`. The split is mechanically necessary — the repo-wide `.gitignore` excludes `.codegenie/` everywhere and Git refuses to track a nested `.git/` directory — and is also conceptually clean: reviewers see the seed template (with `PARENT_COMMIT` substitution token) in git history and know exactly what the adversarial asserts. The full materialization (an actual `scip-typescript` run against a prior commit, then HEAD moved, then `regenerate.sh` documented) is S7-02. The stub is enough to exercise B2's `scip` freshness check end-to-end — the structural assertion is tool-version-agnostic by design (it asserts shapes, not specific commit counts).

The test wires into the new `adv-phase02` CI job that S8-03 lands. **`adv-phase02` is build-gating** — failure fails the PR. Other adversarial tests (S5-05 image-digest-drift, S5-06 adversarial-dockerfile, S6-07 secret-in-source, S7-04 hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped) join the same CI job; this is the first inhabitant.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Goals" G2`](../phase-arch-design.md) — "Build FAILS if the probe does not catch it. This is the roadmap exit criterion."
  - [`../phase-arch-design.md §"Process view" Scenario 2`](../phase-arch-design.md) — sequence diagram for "Stale-SCIP fixture catches in CI."
  - [`../phase-arch-design.md §"Testing strategy" → "Adversarial tests"`](../phase-arch-design.md) — `test_stale_scip_fixture.py` is the load-bearing entry.
  - [`../phase-arch-design.md §"Edge cases" row 11`](../phase-arch-design.md) — stale-SCIP fixture in CI, deliberate seed.
  - [`../phase-arch-design.md §"Implementation risks" #3`](../phase-arch-design.md) — the `n >= 1` AND `last_indexed != HEAD` combined assertion rationale.
- **Phase 2 ADRs:**
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — `CommitsBehind(n, last_indexed)` is the variant; both fields are asserted.
- **Story dependencies:**
  - [`S4-01-index-health-probe.md`](S4-01-index-health-probe.md) AC-5c, AC-6 — the production path the fixture exercises.
  - [`S7-02-fixtures-batch-two.md`](S7-02-fixtures-batch-two.md) — full fixture materialization + `regenerate.sh` policy (downstream).
  - [`S8-03-ci-jobs-and-benches.md`](S8-03-ci-jobs-and-benches.md) — wires `adv-phase02` as a CI gate.
- **Source design:**
  - [`docs/localv2.md §5.2 B1, B2`](../../../localv2.md) — SCIP slice shape and `IndexHealthProbe` slice shape.
  - [`docs/production/design.md §2.3`](../../../production/design.md) — honest confidence commitment.

## Goal

A new test file `tests/adv/phase02/test_stale_scip_fixture.py` runs against `tests/fixtures/portfolio/stale-scip/` and asserts the typed structural outcome of `IndexHealthProbe` (invoked at unit-level via `probe.run(snapshot, ctx)` — two-arg per the frozen ABC; no full `codegenie gather` pipeline). The test is **wired into the `adv-phase02` CI job** via a `phase02_adv` pytest marker (the CI YAML stanza S8-03 lands consumes the marker; no edits to existing markers required). The fixture exists as a stub split between **tracked seed material** and **runtime-materialized state**:

- **Tracked** (committed in this story): `regenerate.sh`, `README.md`, `_seed/scip-slice.template.json` (the synthetic SCIP sibling slice with a `PARENT_COMMIT` substitution token), `_seed/scip-index.scip.placeholder` (optional empty bytes — documentation only), `package.json`, `main.ts`, and a fixture-local `.gitignore` excluding `.git/` and `.codegenie/`.
- **Runtime** (created by `regenerate.sh`, gitignored): `.git/` (a real git work tree with ≥ 2 commits so HEAD is genuinely ahead of the seeded parent), `.codegenie/context/raw/scip.json` (template with `PARENT_COMMIT` substituted), `.codegenie/context/raw/scip-index.scip` (placeholder binary).

The on-disk `scip.json` is the file B2's `read_raw_slices(raw_dir(repo.root))` reads — `<index_name>.json` keyed by `IndexName` stem per S4-01's hardened cross-story integration handoff. This story's seed slice is the substitute for whatever S4-03 (`ScipIndexProbe`) will eventually write at the same path — the contract surface S4-03 must honor. The structural assertions (`CommitsBehind.n >= 1` AND `last_indexed != current_HEAD`) survive any future regeneration that uses a different `scip-typescript` version, moves HEAD by a different commit count, or replaces the seed template with real probe output.

## Acceptance criteria

- [ ] **AC-1 — Adversarial test exists and asserts the typed outcome.** `tests/adv/phase02/__init__.py` and `tests/adv/phase02/test_stale_scip_fixture.py` exist. The test invokes `IndexHealthProbe.run(snapshot, ctx)` — **two-argument**, per the frozen `Probe` ABC at `src/codegenie/probes/base.py:94` and S4-01's hardened AC-1 — against the stale-scip fixture (unit-level invocation; no full gather pipeline; the gather entry point is out of scope here because it pulls in Phase 1 probes that aren't relevant to B2's structural assertion). `snapshot` and `ctx` are constructed inline mirroring the existing test idiom at `tests/unit/probes/test_language_detection_extended.py:29-42` (no `build_probe_context` helper — that's phantom). The test makes **all five** of these assertions in order, each with its own loud diagnostic message:
  1. `set(slice["index_health"].keys()) == {"scip"}` — the slice's outer keys exactly equal `{"scip"}` (the SCIP source is the *only* registered check inside the adversarial's clean-registry window). Asserting exact-equality (not just `"scip" in ...`) catches the singleton-pollution regression: if a prior test registered a `mock` freshness check without unregistering, `{"scip", "mock"}` would slip through a containment check. Per S4-01 AC-10's outer-key invariant.
  2. `freshness = TypeAdapter(IndexFreshness).validate_python(slice["index_health"]["scip"]["freshness"])` — round-trips through the **discriminated union** (`Fresh | Stale` with `kind` discriminator per 02-ADR-0006). Using `TypeAdapter[IndexFreshness]` rather than `Stale.model_validate` exercises the variant-selection logic that real consumers (S8-01's renderer, Phase 3 adapters) will use, and gives the diagnostic "Expected `Stale`, got `Fresh(indexed_at=...)`" on the load-bearing regression where B2 silently returns `Fresh`. Followed by `assert isinstance(freshness, Stale)` for the loud, named, intent-encoding failure (DP3).
  3. `assert isinstance(freshness.reason, CommitsBehind)` — the reason variant is exactly `CommitsBehind`, not `IndexerError`/`CoverageGap`/`DigestMismatch`. Catches the bug "B2 emits a `Stale` but with the wrong reason — e.g., `upstream_scip_unavailable` masking a real staleness." If this assertion fails with `reason=IndexerError`, the diagnostic explicitly suggests checking that `regenerate.sh` was run (the fixture's `scip.json` may be absent, causing B2 to emit `Stale(IndexerError("upstream_scip_unavailable"))`).
  4. `assert freshness.reason.n >= 1` **AND** `assert freshness.reason.last_indexed != current_HEAD` — the **combined** structural assertion (`High-level-impl.md §"Risks specific to this step" #3`). Both inequalities are independently asserted with their own error messages. The second inequality is the falsifier against S4-01 AC-6's `n=1` fallback path — a degenerate case where the fallback fires but `last_indexed == HEAD` (which would be a B2 bug) would pass `n >= 1` alone.
  5. `assert slice["index_health"]["scip"]["confidence"] == "medium"` — pins S4-01 AC-9's `Stale(CommitsBehind(...))` → `"medium"` demote-min mapping at the slice surface. Catches the regression "the typed value is `Stale` but the flat `confidence` field wasn't re-derived and reads `"high"`" — silent floor-demotion failure of the very mechanism §2.3 honest-confidence requires.

- [ ] **AC-2 — `current_HEAD` is derived at test time, not hardcoded.** The test computes `current_HEAD` via `subprocess.run(["git", "rev-parse", "HEAD"], cwd=fixture_path, ...)` (the same path B2 takes — but at test boundary, not inside production code). Hardcoding a specific SHA would make the test brittle against fixture regeneration. The test value must survive `regenerate.sh` producing a new commit graph.

- [ ] **AC-3 — Fixture directory + minimal contents land in this story.** `tests/fixtures/portfolio/stale-scip/` exists as a **stub**, split between tracked seed material (reviewable in the parent repo's git history) and runtime-materialized state (created by `regenerate.sh`, gitignored). The split is load-bearing — Git refuses to track a nested `.git/` directory as files, and the repo-wide `.gitignore` already excludes `.codegenie/` everywhere; pretending these can be vendored is the regression vector hardened against here.

  **Tracked (committed in this story):**
  - `regenerate.sh` — executable, reviewed-as-code (AC-5 covers the guard).
  - `README.md` — documents the regeneration policy (AC-4).
  - `.gitignore` — fixture-local; ignores `.git/` and `.codegenie/` so the regenerated state is never accidentally committed (parent repo's `.gitignore` already covers `.codegenie/` but the fixture-local `.gitignore` also excludes `.git/` and makes the intent explicit at the fixture boundary).
  - `_seed/scip-slice.template.json` — the synthetic SCIP sibling slice with a literal `PARENT_COMMIT` token that `regenerate.sh` substitutes. Shape: `{"last_indexed_commit": "PARENT_COMMIT", "last_indexed_at": "2026-04-26T08:00:00Z", "files_indexed": 1, "files_in_repo": 1, "indexer_errors": 0}`. **The seed slice is the contract surface S4-03's `ScipIndexProbe` must honor when it ships** — S4-03 will write the real value to the same path (`.codegenie/context/raw/scip.json`); this story ships the substitute.
  - `_seed/scip-index.scip.placeholder` — optional empty bytes (documentation: "this is where the real `.scip` binary lands in S7-02"). Not parsed by anyone.
  - `package.json` (`{"name": "stale-scip-fixture", "private": true}`) — preparatory for a future end-to-end use; not currently load-bearing because the test invokes B2 directly.
  - `main.ts` (one-liner: `export const x = 1;`) — content for the v1 commit.

  **Runtime (created by `regenerate.sh`, gitignored — NOT committed):**
  - `.git/` — a real git work tree with ≥ 2 commits so HEAD is genuinely ahead of the seeded `last_indexed_commit` by ≥ 1.
  - `.codegenie/context/raw/scip.json` — produced from `_seed/scip-slice.template.json` with `PARENT_COMMIT` substituted to the v0 commit SHA. **The filename is `scip.json`** (keyed by `IndexName("scip")` stem per S4-01's hardened `read_raw_slices` contract). The previously-drafted `semantic_index.json` is wrong — B2 would not find it and would emit `Stale(IndexerError("upstream_scip_unavailable"))`.
  - `.codegenie/context/raw/scip-index.scip` — placeholder binary copied from `_seed/scip-index.scip.placeholder`.

  The seeded `last_indexed_commit` is the SHA of the parent commit (v0), not HEAD (v1).

- [ ] **AC-4 — `tests/fixtures/portfolio/stale-scip/README.md` documents the regeneration policy.** The README states verbatim (or equivalent prose):
  - "**This fixture is LOAD-BEARING for the Phase 2 roadmap exit criterion.** Do not delete, do not retarget the seeded `last_indexed_commit` to current `HEAD`."
  - "Regeneration: run `./regenerate.sh` from this directory. The script creates `.git/` with ≥ 2 commits, seeds `last_indexed_commit` to the **parent** commit, and substitutes `PARENT_COMMIT` in `_seed/scip-slice.template.json` to produce `.codegenie/context/raw/scip.json`. HEAD is genuinely ahead by ≥ 1."
  - "Both `.git/` and `.codegenie/` are gitignored (fixture-local `.gitignore` + repo-wide `.gitignore`). The reviewable contract surface is `_seed/scip-slice.template.json`, `regenerate.sh`, and this README — every assertion the adversarial test makes traces back to one of these three."
  - "The structural assertion is `CommitsBehind.n >= 1` **AND** `last_indexed != current_HEAD`. Both are tool-version-agnostic. Do not assert on a specific `n` value."
  - "The sibling slice file is `.codegenie/context/raw/scip.json` (keyed by `IndexName('scip')` stem per S4-01's `read_raw_slices` contract). This is the contract surface S4-03's `ScipIndexProbe` must honor when it ships; this fixture provides the substitute until S4-03 lands."
  - "If you bump `scip-typescript`'s version (S4-03 / S7-02), regenerate; the structural assertion survives any version bump."
  - "Full fixture materialization (real `scip-typescript` invocation against a prior commit) lands in S7-02. This stub is enough for S4-02's adversarial assertion."

- [ ] **AC-5 — `regenerate.sh` errors out if retargeted to current HEAD.** `tests/fixtures/portfolio/stale-scip/regenerate.sh` is executable, reviewed-as-code, and contains an **env-overrideable** guard that defaults to the structurally-correct value (the parent commit) but can be deterministically forced to the failing branch by `test_regenerate_sh_guard`:
  ```bash
  # After both commits exist, derive (or accept env override of) LAST_INDEXED.
  LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"
  if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
    echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
    echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
    exit 1
  fi
  ```
  The original draft's guard captured `LAST_INDEXED` *between* the two commits and compared it against post-2nd-commit HEAD — dead code, unreachable under any normal invocation. The env-overrideable form lets `test_regenerate_sh_guard` invoke the script with `LAST_INDEXED=$(git -C tmp rev-parse HEAD)` (the SHA *after* both commits) to force the guard branch deterministically. A unit test (`test_regenerate_sh_guard`) does exactly that and asserts exit code 1 + stderr contains `"refuses to set last_indexed_commit == HEAD"`.

- [ ] **AC-6 — Test failure mode is loud and actionable.** When the adversarial fails (a future B2 regression), pytest's `--tb=long` shows:
  1. The exact `IndexFreshness` value B2 emitted (via `freshness.model_dump_json(indent=2)`).
  2. The expected structural shape (`Stale(reason=CommitsBehind(n>=1, last_indexed != HEAD))`).
  3. A pointer to this story file + the [`production/design.md §2.3`](../../../production/design.md) honest-confidence commitment.
  Use `pytest.fail(msg)` with a multiline string, not bare `assert` — the diagnostic at CI-failure time is the load-bearing artifact (Rule 12 — fail loud).

- [ ] **AC-7 — Test is wired into the `adv-phase02` placeholder.** `pyproject.toml`'s `[tool.pytest.ini_options].markers` list (the existing registration site for `bench` and `adv` markers — see `pyproject.toml:208-211`) is extended with `"phase02_adv: Phase 2 adversarial tests (CI-gating; see tests/adv/phase02/)"`. The marker registration is pinned to `pyproject.toml` (NOT `conftest.py` `pytest_configure` registration) to match the existing Phase 0/1 convention and to avoid double-registration drift. `tests/adv/phase02/conftest.py` exists but registers only a `fixture_path` fixture resolving to `tests/fixtures/portfolio/stale-scip/`, not the marker. The CI YAML stanza is OUT OF SCOPE here (S8-03 lands `pytest -m phase02_adv` as the `adv-phase02` job). A unit test asserts `"phase02_adv" in markers` so accidental removal is caught.

- [ ] **AC-8 — No skip-on-missing-tool path.** This test must not `pytest.skip` on any condition — it is build-gating. At test start the test calls `shutil.which("git")`; if it returns `None`, the test `pytest.fail`s with an explicit "`git` is not on $PATH; this is a developer-environment bug, not a skip condition. Install git and rerun." message — this catches the developer-environment failure mode loudly with the right diagnostic. Without this pre-flight check, missing `git` would be silently wrapped by B2 into `Stale(IndexerError("repo_not_a_git_workdir"))` and fail at AC-1 step 3 ("Expected `CommitsBehind`, got `IndexerError`") — correct outcome but the operator wastes time diagnosing the wrong layer. Phase 0's `fence` job already ensures `git` is present on the CI runner.

- [ ] **AC-9 — No false-passing path under registry-empty.** Defensive: if the test is somehow invoked with an empty freshness registry (e.g., S4-01's `scip` check is not registered), B2 emits `slice == {}` (S4-01 AC-11) and the test fails at AC-1 step 1 (`set(slice["index_health"].keys()) == {"scip"}` reduces to `set() == {"scip"}` — loud, named). The test must NOT silently pass via the empty-slice path. A unit test (`test_empty_registry_fails_adversarial`) uses the `clean_freshness_registry` snapshot-and-restore fixture (per S4-01 TDD preamble — snapshots `_checks` + `_origins`, restores in `finally:`; `_clear_for_tests` is phantom — the actual S1-02 API is per-name `unregister_for_tests(index_name)`), runs the adversarial under the clean-and-empty condition, and asserts the adversarial fails at AC-1 step 1.

- [ ] **AC-10 — The test runs in < 10 s on CI.** Adversarial tests are part of CI critical path; a slow adversarial penalizes every PR. The fixture is small enough that B2 (unit-level invocation, no real `scip-typescript`) completes in < 1 s; the test budget is 10 s including pytest setup. **Enforced in-test** via `@pytest.mark.timeout(10)` (assumes the `pytest-timeout` plugin is on the Phase 0/1 dev-dep list — verify; if not available, scope a tiny `time.perf_counter()` start/end around the body with `assert elapsed < 10.0`). If the time creeps past 10 s in CI, the test fails loudly at the per-test budget; the bench advisory (S8-03's `bench_index_health_overhead`) is the secondary defense.

- [ ] **AC-11 — Tooling green.** `ruff check tests/adv/phase02/`, `ruff format --check`, `mypy --strict tests/adv/phase02/test_stale_scip_fixture.py` all pass. The fixture's regenerated state (`.git/`, `.codegenie/`) is gitignored.

- [ ] **AC-12 — `.gitignore` policy verified.** A unit test `test_fixture_gitignore_policy` asserts: (a) `git check-ignore tests/fixtures/portfolio/stale-scip/.git/` exits 0 (ignored); (b) `git check-ignore tests/fixtures/portfolio/stale-scip/.codegenie/context/raw/scip.json` exits 0 (ignored); (c) `git check-ignore tests/fixtures/portfolio/stale-scip/_seed/scip-slice.template.json` exits 1 (tracked). The test protects the seed-vs-runtime split — if a future contributor accidentally commits the regenerated `.codegenie/` content, the assertions catch it.

## Implementation outline

The shape is **deliberately a single test method with maximum diagnostic value** (Rule 2 / Rule 9 / Rule 12). Helpers stay inline so a future contributor reading the test sees the structural assertion in one screen. The seed-material-vs-runtime split (DP2) keeps every reviewable artifact in the parent repo's git history while `.git/` and `.codegenie/` are materialized at runtime.

1. **Create `tests/adv/phase02/__init__.py`** (empty) and `tests/adv/phase02/conftest.py` (defines a `fixture_path` fixture resolving to `tests/fixtures/portfolio/stale-scip/`; does **not** register the pytest marker — that lives in `pyproject.toml` per AC-7).

2. **Create the fixture directory `tests/fixtures/portfolio/stale-scip/`** with the seed/runtime split:

    - `_seed/scip-slice.template.json`:
      ```json
      {"last_indexed_commit": "PARENT_COMMIT",
       "last_indexed_at": "2026-04-26T08:00:00Z",
       "files_indexed": 1, "files_in_repo": 1, "indexer_errors": 0}
      ```
    - `_seed/scip-index.scip.placeholder` — empty file (documentation; S7-02 replaces with real `.scip` binary).
    - `package.json` (`{"name": "stale-scip-fixture", "private": true}`).
    - `main.ts` (`export const x = 1;` — content for the v1 commit).
    - `.gitignore` (fixture-local; ignores `.git/` and `.codegenie/`).
    - `README.md` per AC-4.
    - `regenerate.sh` (executable, shellcheck-clean) — see below.

    `regenerate.sh`:
    ```bash
    #!/usr/bin/env bash
    # Regenerates the stale-scip fixture. See README.md.
    # MUST keep HEAD ahead of the parent commit by >= 1.
    set -euo pipefail
    cd "$(dirname "$0")"
    rm -rf .git .codegenie

    git init -q -b main
    git config user.email "fixture@codewizard.local"
    git config user.name  "Fixture Bot"

    # v0 — content of package.json is the seed commit; LAST_INDEXED will point here.
    git add package.json && git commit -q -m "v0 — seeded last_indexed_commit"
    PARENT_COMMIT=$(git rev-parse HEAD)

    # v1 — HEAD moves forward.
    git add main.ts && git commit -q -m "v1 — HEAD moves forward"

    # Materialize the runtime sibling-slice from the tracked template.
    mkdir -p .codegenie/context/raw
    sed "s|PARENT_COMMIT|${PARENT_COMMIT}|g" \
      _seed/scip-slice.template.json > .codegenie/context/raw/scip.json
    cp _seed/scip-index.scip.placeholder .codegenie/context/raw/scip-index.scip

    # Guard — env-overrideable so `test_regenerate_sh_guard` can force the failing branch.
    # Default: the parent of HEAD (which by construction is NOT HEAD itself).
    LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"
    if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
      echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
      echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
      exit 1
    fi
    echo "stale-scip fixture regenerated. last_indexed=$PARENT_COMMIT head=$(git rev-parse HEAD)"
    ```

3. **Write `test_stale_scip_fixture.py`** (~100 LOC). The test constructs `RepoSnapshot` and `ProbeContext` inline (no `build_probe_context` helper — that's phantom; mirror the existing idiom at `tests/unit/probes/test_language_detection_extended.py:29-42`). The on-disk `.codegenie/context/raw/scip.json` is the sibling-slice surface B2 reads via `read_raw_slices(raw_dir(repo.root))`.

    ```python
    # tests/adv/phase02/test_stale_scip_fixture.py
    from __future__ import annotations
    import asyncio, json, shutil, subprocess
    from logging import getLogger
    from pathlib import Path
    import pytest
    from pydantic import TypeAdapter
    from codegenie.indices.freshness import (
        CommitsBehind,
        Fresh,  # noqa: F401  — only re-exported for TypeAdapter discrimination
        IndexFreshness,
        Stale,
    )
    from codegenie.probes.base import ProbeContext, RepoSnapshot
    from codegenie.probes.layer_b.index_health import IndexHealthProbe

    pytestmark = pytest.mark.phase02_adv

    FIXTURE = (
        Path(__file__).parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"
    )
    _SLICE_PATH = FIXTURE / ".codegenie" / "context" / "raw" / "scip.json"
    _FRESHNESS_ADAPTER: TypeAdapter[IndexFreshness] = TypeAdapter(IndexFreshness)


    def _current_head(repo: Path) -> str:
        # Mirror B2's exact byte-decode path so encoding drift is impossible.
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, check=True
        )
        return result.stdout.decode("utf-8").strip()


    def _snapshot(root: Path) -> RepoSnapshot:
        return RepoSnapshot(
            root=root, git_commit=None, detected_languages={}, config={}
        )


    def _ctx(root: Path) -> ProbeContext:
        return ProbeContext(
            cache_dir=root / ".cache",
            output_dir=root / ".codegenie" / "context",
            workspace=root / ".ws",
            logger=getLogger("test"),
            config={},
        )


    @pytest.mark.timeout(10)  # AC-10 — adversarial budget; pytest-timeout
    def test_index_health_catches_stale_scip() -> None:
        """Roadmap exit criterion: IndexHealthProbe surfaces a real staleness case.

        Build FAILS if B2 does not catch the deliberately-seeded staleness.
        See docs/phases/02-context-gather-layers-b-g/stories/S4-02-stale-scip-adversarial.md.
        """
        # AC-8 — pre-flight: git must be on PATH. NO pytest.skip path.
        if shutil.which("git") is None:
            pytest.fail(
                "`git` is not on $PATH; this is a developer-environment bug, not a "
                "skip condition. Install git and rerun. (Phase 0 fence job ensures "
                "git on the CI runner; if you're seeing this on CI, the fence job "
                "regressed.)"
            )
        if not FIXTURE.exists() or not _SLICE_PATH.exists():
            pytest.fail(
                f"stale-scip fixture missing or not regenerated. "
                f"Run `{FIXTURE}/regenerate.sh`. Looked for {_SLICE_PATH}."
            )
        head = _current_head(FIXTURE)
        probe = IndexHealthProbe()
        out = asyncio.run(probe.run(_snapshot(FIXTURE), _ctx(FIXTURE)))
        index_health = out.schema_slice["index_health"]

        # AC-1 step 1 — outer-key invariant (catches singleton pollution).
        assert set(index_health.keys()) == {"scip"}, (
            f"Expected slice['index_health'].keys() == {{'scip'}}, got "
            f"{set(index_health.keys())!r}. Either the freshness registry has been "
            "polluted by a prior test (use `clean_freshness_registry` fixture), or "
            "B2's outer-key invariant (S4-01 AC-10) regressed."
        )

        # AC-1 step 2 — discriminated-union round-trip (DP3).
        raw = index_health["scip"]["freshness"]
        freshness = _FRESHNESS_ADAPTER.validate_python(raw)
        assert isinstance(freshness, Stale), (
            f"Expected `Stale`, got `{type(freshness).__name__}` with "
            f"value:\n{json.dumps(raw, indent=2)}\n"
            "See production/design.md §2.3 (honest confidence) — silent freshness "
            "(B2 emits Fresh against the stale-seeded fixture) is THE load-bearing "
            "failure mode this adversarial gates."
        )

        # AC-1 step 3 — reason variant pinned.
        assert isinstance(freshness.reason, CommitsBehind), (
            f"Expected `Stale(reason=CommitsBehind)`, got "
            f"`Stale(reason={type(freshness.reason).__name__})`. "
            f"Full freshness:\n{json.dumps(raw, indent=2)}\n"
            "If reason=IndexerError, the fixture's "
            "`.codegenie/context/raw/scip.json` may be absent or malformed — "
            "rerun `regenerate.sh`. If reason=CoverageGap or DigestMismatch, "
            "B2's `scip` freshness check (S4-01 AC-5) misclassified the staleness."
        )

        # AC-1 step 4 — BOTH inequalities (implementation risk #3 — see
        # High-level-impl.md §"Risks specific to this step").
        assert freshness.reason.n >= 1, (
            f"Expected CommitsBehind.n >= 1, got n={freshness.reason.n}. "
            f"Full freshness:\n{json.dumps(raw, indent=2)}"
        )
        assert freshness.reason.last_indexed != head, (
            f"Expected CommitsBehind.last_indexed != current HEAD, but both are "
            f"{head!r}. The fixture's seeded last_indexed_commit must be the "
            "parent commit, NOT HEAD. Did regenerate.sh's guard fail? See "
            "tests/fixtures/portfolio/stale-scip/README.md."
        )

        # AC-1 step 5 — per-source confidence demote-min wiring.
        assert index_health["scip"]["confidence"] == "medium", (
            f"Expected per-source confidence=='medium' for "
            f"`Stale(CommitsBehind(...))` (S4-01 AC-9 mapping), got "
            f"{index_health['scip']['confidence']!r}. The typed value may be "
            "correct but the flat `confidence` field wasn't re-derived — the "
            "honest-confidence demote-min mechanism regressed."
        )
    ```

4. **Wire the pytest marker** in `pyproject.toml`'s existing `[tool.pytest.ini_options].markers` list (`pyproject.toml:208-211`):
    ```toml
    markers = [
        "bench: advisory performance canaries — not run under the default suite",
        "adv: adversarial-fixture corpus tests (Phase 1 §S5-01/02/03)",
        "phase02_adv: Phase 2 adversarial tests (CI-gating; see tests/adv/phase02/)",
    ]
    ```

5. **Add the `test_regenerate_sh_guard` unit test** at `tests/unit/fixtures/test_stale_scip_regenerate_guard.py`: copies the fixture into a tmpdir, invokes `regenerate.sh` first (normal flow, exit 0) to build `.git/` with two commits, then invokes the script a second time with `LAST_INDEXED=$(git -C tmpdir rev-parse HEAD)` (the post-2nd-commit HEAD), and asserts exit code 1 plus stderr contains "refuses to set last_indexed_commit == HEAD". This is the only place we test shell behavior — keep it surgical (Rule 3).

6. **Add the `test_empty_registry_fails_adversarial` unit test** at `tests/unit/probes/layer_b/test_index_health_empty_registry_adversarial.py`: uses the `clean_freshness_registry` snapshot-and-restore fixture from S4-01's TDD preamble (snapshots `default_freshness_registry._checks` + `_origins`, restores in `finally:` — `_clear_for_tests` is phantom; the actual S1-02 API is per-name `unregister_for_tests`), runs B2 against the fixture under the clean-and-empty condition, asserts `out.schema_slice["index_health"] == {}`, and then asserts that the AC-1-step-1 expression `set({}) == {"scip"}` is `False` (re-asserting the adversarial would fail at step 1). This is the AC-9 anti-false-pass guard.

7. **Add the `test_fixture_gitignore_policy` unit test** at `tests/unit/fixtures/test_stale_scip_gitignore_policy.py`: invokes `git check-ignore` against the three paths under AC-12 and asserts the expected return codes. This protects the seed-vs-runtime split.

## TDD plan — red / green / refactor

### RED

- **T-01** `test_index_health_catches_stale_scip` (the main adversarial) FAILS initially because the fixture directory + `_seed/` material do not exist. Add the tracked seed files (no `.git/`, no `.codegenie/`); rerun; FAILS with "stale-scip fixture missing or not regenerated. Run `regenerate.sh`." Run `regenerate.sh`; rerun; the test invokes B2 (assuming S4-01 is GREEN) which reads `.codegenie/context/raw/scip.json`, computes `CommitsBehind`, and the test PASSES through all five AC-1 assertions.
- **T-02** `test_regenerate_sh_guard`: FAILS until the env-overrideable guard form (`LAST_INDEXED="${LAST_INDEXED:-...}"`) is in `regenerate.sh`. The test runs the script in a tmpdir, then invokes the script again with `LAST_INDEXED=$head_after_v1`, asserts exit 1.
- **T-03** `test_empty_registry_fails_adversarial` (AC-9): FAILS until the `clean_freshness_registry` snapshot fixture is wired (per S4-01 TDD preamble — phantom name `_clear_for_tests` does not exist; use the snapshot-and-restore pattern). Once correct, B2 emits `{}` under the clean window; the test asserts the AC-1 step-1 expression would fail (closed-world).
- **T-04** `test_marker_registered`: `pytest --markers` output contains `phase02_adv`. FAILS until `pyproject.toml`'s `markers` list is extended.
- **T-05** `test_fixture_gitignore_policy` (AC-12): FAILS until the fixture-local `.gitignore` exists and the repo-wide `.gitignore` does not over-match `_seed/`. Asserts `git check-ignore` outcomes for the three paths.
- **T-06** Mutation test (manual, documented in the test docstring AND in `_attempts/S4-02.md` after implementation): temporarily change S4-01's `scip_freshness` to always return `Fresh(indexed_at=datetime.now(tz=UTC))` — rerun T-01 — assert it FAILS at AC-1 step 2 with the diagnostic "Expected `Stale`, got `Fresh(...)`". Then change it to return `Stale(reason=IndexerError("nope"))` — rerun T-01 — assert it FAILS at AC-1 step 3 with the diagnostic naming `IndexerError`. Revert. (This is a documented manual check, not a CI step — Phase 6's formal mutation harness will codify it. Run BEFORE opening the PR; record the two diagnostics verbatim in the PR description per Rule 9 — tests verify intent.)

### GREEN

Implement the fixture (seed material + `.gitignore` + `regenerate.sh`), the adversarial test, the marker registration in `pyproject.toml`, and the three companion unit tests. T-01 through T-05 turn green. Run T-06 manually and record the two diagnostics in the PR description.

### REFACTOR

- Confirm the error messages on each assertion are actionable (a future CI failure must point a contributor at this story and at `production/design.md §2.3`).
- Verify the test completes in < 10 s (AC-10) — the `@pytest.mark.timeout(10)` enforces this in-test.
- Run `regenerate.sh` twice in a row and confirm idempotency — second run produces the same outputs modulo commit SHAs (which legitimately change due to commit timestamps; the `CommitsBehind.n >= 1` AND `last_indexed != HEAD` invariants survive any commit-SHA churn).
- `git status` in `tests/fixtures/portfolio/stale-scip/` shows ONLY untracked `.git/` and `.codegenie/` (both gitignored) — confirms the seed/runtime split is enforced.

## Files to touch

**Create (committed — tracked seed material + tests):**
- `tests/adv/phase02/__init__.py` (empty)
- `tests/adv/phase02/conftest.py` — defines a `fixture_path` fixture resolving to `tests/fixtures/portfolio/stale-scip/`. Does **not** register the pytest marker (that's `pyproject.toml`'s job per AC-7).
- `tests/adv/phase02/test_stale_scip_fixture.py`
- `tests/fixtures/portfolio/stale-scip/regenerate.sh` (executable)
- `tests/fixtures/portfolio/stale-scip/README.md`
- `tests/fixtures/portfolio/stale-scip/.gitignore` — fixture-local; ignores `.git/` and `.codegenie/` (defense-in-depth; repo-wide `.gitignore` already covers `.codegenie/`).
- `tests/fixtures/portfolio/stale-scip/.gitattributes` — declares `_seed/scip-index.scip.placeholder binary` so git does not corrupt it.
- `tests/fixtures/portfolio/stale-scip/_seed/scip-slice.template.json` — synthetic SCIP sibling slice with `PARENT_COMMIT` token.
- `tests/fixtures/portfolio/stale-scip/_seed/scip-index.scip.placeholder` — empty file (S7-02 replaces with real blob).
- `tests/fixtures/portfolio/stale-scip/package.json` (`{"name": "stale-scip-fixture", "private": true}`)
- `tests/fixtures/portfolio/stale-scip/main.ts` (content for v1 commit)
- `tests/unit/fixtures/test_stale_scip_regenerate_guard.py`
- `tests/unit/fixtures/test_stale_scip_gitignore_policy.py`
- `tests/unit/probes/layer_b/test_index_health_empty_registry_adversarial.py`

**Runtime — NOT committed (created by `regenerate.sh`, gitignored):**
- `tests/fixtures/portfolio/stale-scip/.git/` (real git work tree; ≥ 2 commits)
- `tests/fixtures/portfolio/stale-scip/.codegenie/context/raw/scip.json` (template substituted; keyed by `IndexName("scip")` stem per S4-01's `read_raw_slices` contract)
- `tests/fixtures/portfolio/stale-scip/.codegenie/context/raw/scip-index.scip` (placeholder binary copied from `_seed/`)

**Edit (additive):**
- `pyproject.toml` — extend `[tool.pytest.ini_options].markers` (existing list at `pyproject.toml:208-211`) with the `phase02_adv` marker entry.

## Out of scope

- **Full fixture materialization via real `scip-typescript` invocation.** S7-02 owns this — runs `scip-typescript` against the parent commit, replaces the placeholder `.scip` blob with the real binary, documents the regeneration ritual against tool-version bumps. This story ships a stub sufficient to gate B2's typed outcome.
- **The `adv-phase02` CI job YAML.** S8-03 lands the eight CI jobs including `adv-phase02`. This story registers the pytest marker; that story consumes the marker in `.github/workflows/`.
- **Adversarial tests for other failure modes.** S5-05 (image-digest-drift), S5-06 (adversarial-dockerfile), S6-07 (secret-in-source), S7-04 (hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped) all join `tests/adv/phase02/` later. Each is independent.
- **Renderer assertion that the typed value lands in `CONTEXT_REPORT.md`.** S8-01's renderer story will exercise pattern-matching on this exact `Stale(CommitsBehind(...))` value; this story stops at the typed-value boundary.
- **Property-based round-trip of `IndexFreshness`.** S1-02 already covers `tests/property/test_index_freshness_roundtrip.py` (Hypothesis) at the unit level. This story uses **concrete** values from the fixture — adversarial-test discipline (real seeded scenario, not generated input).

## Notes for the implementer

- **Why a stub fixture is enough here.** B2's `scip` freshness check (S4-01 AC-5) reads the `last_indexed_commit` field from the `scip.json` sibling slice (B2's `read_raw_slices` keys by `IndexName` stem), NOT the SCIP binary itself. Producing a real `.scip` binary is S4-03's `ScipIndexProbe` job, and the binary is exercised end-to-end in S7-02's portfolio sweep. The adversarial test path bypasses the binary entirely — it materializes `scip.json` from `_seed/scip-slice.template.json` and asserts B2's typed output. Coupling the adversarial to a real `scip-typescript` run would (a) require `scip-typescript` on every CI runner that runs `adv-phase02`, (b) make the test fail for unrelated reasons (e.g., a `scip-typescript` minor-version bump), (c) lengthen CI runtime past AC-10's 10 s budget. The structural assertion is the contract; the binary-format pathway is integration territory.
- **Why both inequalities (`n >= 1` AND `last_indexed != HEAD`).** Implementation risk #3 from [`High-level-impl.md §"Risks specific to this step"`](../High-level-impl.md) spells this out. S4-01 AC-6 has a fallback path where `n` falls back to `1` if `git rev-list --count` fails. A test asserting only `n >= 1` would pass even if the fallback fired in a degenerate state where `last_indexed == HEAD` (which would be a B2 bug — emitting `CommitsBehind` for a non-stale state). Asserting `last_indexed != HEAD` independently anchors the structural fact that the two commits are genuinely different, which is the actual definition of "stale." Both assertions together are what makes the test tool-version-agnostic AND fallback-resilient.
- **Cross-story integration handoff (S4-03).** S4-01's hardened cross-story integration handoff states: "S4-03 (SCIP probe) MUST write `<repo>/.codegenie/context/raw/scip.json` during its `run()` containing keys `{last_indexed_commit, files_indexed, files_in_repo, indexer_errors, last_indexed_at}`." This adversarial story ships the **substitute** for that file (`_seed/scip-slice.template.json` → runtime `scip.json`). The seed slice IS the contract surface S4-03 must honor when it ships. If S4-03 picks a different filename (e.g., `semantic_index.json`) or a different key set, this fixture and S4-01 both break — that mismatch is a tracked Phase-2 invariant.
- **Don't `pytest.skip`.** AC-8 forbids skip paths. The adversarial test is build-gating; skipping it silently is the same failure mode B2 is built to prevent (silent staleness → silent skip). If a missing prerequisite is detected, `pytest.fail` with a clear message, never `pytest.skip`. The `shutil.which("git")` pre-flight is the one place this discipline is implemented in test code.
- **Construct `RepoSnapshot` + `ProbeContext` inline.** There is **no** `tests/helpers/probe_context.py` / `build_probe_context` helper — that was a phantom in the original draft. Mirror the existing test idiom (`tests/unit/probes/test_language_detection_extended.py:29-42`): inline `_snapshot` and `_ctx` factories scoped to this file. Rule 11 — match the codebase convention.
- **Mutation test as design verification (T-06).** Documented as a manual check rather than a CI step because mutation-testing infrastructure is a Phase 6 concern. But every implementer of this story should run T-06 manually before opening the PR — temporarily make `scip_freshness` always return `Fresh`, confirm the adversarial fails loudly at AC-1 step 2 with the diagnostic "Expected `Stale`, got `Fresh(...)`"; then change it to `Stale(reason=IndexerError("nope"))`, confirm the adversarial fails at AC-1 step 3; revert. Record both diagnostics verbatim in the PR description. This is the "tests verify intent" check from Rule 9 — without this manual mutation pass, the PR is not ready.
- **Fixture seed material at a tracked path, runtime materialized.** The repo-wide `.gitignore` ignores `.codegenie/` everywhere; Git refuses to track a nested `.git/` directory; the original "vendored `.git/`" plan was mechanically impossible. The fix splits the fixture into reviewable seed material (`_seed/scip-slice.template.json`, `regenerate.sh`, `README.md`, `package.json`, `main.ts`, `.gitignore`) and runtime-materialized state (`.git/`, `.codegenie/`). The seed JSON, with its `PARENT_COMMIT` token, is the *contract surface*: a reviewer can read it and know exactly what the adversarial asserts. This is Functional-Core / Imperative-Shell applied at the fixture boundary.
- **Rule 12 — fail loud.** Every `assert` in the adversarial test has a multi-line error message that points to (a) what shape was expected, (b) what shape was actually emitted (`json.dumps(raw, indent=2)`), (c) the story / ADR / production doc that explains why, (d) the most likely operator action (e.g., "rerun `regenerate.sh`"). When this test fails in CI six months from now, the person fixing it must not need to read the test source to understand the failure.

### Design-pattern notes (from validation, 2026-05-16)

- **DP1 — Adversarial test helpers are a rule-of-three deferred kernel.** S4-02 is the FIRST of six adversarial tests landing in `tests/adv/phase02/` (per `phase-arch-design.md §"Adversarial tests"`): S5-05 (image-digest-drift), S5-06 (adversarial-dockerfile), S6-07 (secret-in-source), S7-04 (hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped). Every one will construct `RepoSnapshot` + `ProbeContext`, invoke a single probe, and assert a structural outcome. **Do NOT pre-extract a helper module in S4-02** (Rule 2 — simplicity first; Rule 3 — surgical changes). When the 3rd adversarial lands, the rule-of-three threshold trips and a dedicated extraction story should lift `tests/adv/phase02/_helpers.py` — mirroring the Phase-1 precedent at `tests/adv/_helpers.py`. The kernel candidates today: `_snapshot(root)`, `_ctx(root)`, the `_FRESHNESS_ADAPTER` TypeAdapter, and the `_current_head` byte-decode helper.
- **DP2 — Seed-at-tracked-path / runtime-materialized split (Functional Core / Imperative Shell at the fixture boundary).** What's reviewable in git lives in `_seed/` + `regenerate.sh` + `README.md`. What's regenerated per-run lives in `.git/` + `.codegenie/`. A reviewer reads the seed template's `PARENT_COMMIT` placeholder and knows the adversarial's structural shape without running anything. This pattern generalizes to every fixture under `tests/fixtures/portfolio/`; S7-01 / S7-02 should normalize it across the five-fixture portfolio.
- **DP3 — `TypeAdapter[IndexFreshness]` as the round-trip-at-the-boundary idiom.** The discriminated union (`Fresh | Stale` with `kind` discriminator per 02-ADR-0006) exists precisely so consumers can validate JSON → `IndexFreshness` without knowing which variant they'll get. Using `Stale.model_validate(raw)` bypasses the discrimination and gives an opaque Pydantic error on the load-bearing regression. Using `TypeAdapter` followed by `isinstance(freshness, Stale)` gives a named, diagnostic, intent-encoding failure. Future adversarials that round-trip typed values (`ScannerOutcome`, `AdapterConfidence`, `IndexFreshness`) should follow this pattern.
- **DP4 — Open/Closed at the file boundary for adversarial tests.** Adding the next adversarial under `tests/adv/phase02/` requires zero edits to existing adversarial tests (each file is self-contained); zero edits to the `phase02_adv` marker registration in `pyproject.toml` (one marker per phase covers all); zero edits to the `adv-phase02` CI YAML stanza S8-03 lands (which uses `pytest -m phase02_adv`); and zero edits to `tests/adv/phase02/conftest.py` (per-test fixtures go in their own test file unless they're the 3rd repetition triggering DP1's extraction). This Open/Closed property is the discipline S5-05 / S5-06 / S6-07 / S7-04 inherit.
