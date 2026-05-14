# Story S4-02 — `stale-scip` fixture stub + load-bearing adversarial test wired CI-gating

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`IndexHealthProbe` with `scip` freshness check registered; the typed `Stale(CommitsBehind(...))` value B2 emits)
**ADRs honored:** 02-ADR-0006 (`IndexFreshness` is the typed answer to honest-confidence — `CommitsBehind.n` and `last_indexed` are both asserted), Phase 0 ADR — adversarial corpus convention (`tests/adv/phase02/` is the Phase 2 home; CI job `adv-phase02` is build-gating), [production design.md §2.3 honest-confidence](../../../production/design.md), [`CLAUDE.md`](../../../../CLAUDE.md) "single most important probe is `IndexHealthProbe`"

## Context

This is **the roadmap exit criterion test for Phase 2** ([phase-arch-design.md §"Goals" G2](../phase-arch-design.md), [final-design.md §"Goals"](../final-design.md), [stories/README.md §"Phase exit-criterion traceability"](README.md)). The deliberately-seeded `stale-scip` fixture in `tests/fixtures/portfolio/stale-scip/` is a repo where:
- the `.codegenie/context/raw/scip-index.scip` blob (or the seed `semantic_index` slice) reflects a **prior** commit,
- the working-tree `HEAD` has moved forward by ≥ 1 commit.

S4-01 ships `IndexHealthProbe` (B2). This story ships the **CI-gating adversarial test that proves B2 catches the staleness**. If B2 ever regresses — silently treating the moved HEAD as `Fresh`, or emitting a `Stale` with the wrong reason variant — this test fails and the Phase 2 build fails. That is the operational meaning of "honest confidence" ([production design.md §2.3](../../../production/design.md)): we encode the load-bearing failure mode as a test that gates the build.

**Implementation risk #3 from the manifest:** the assertion must check **both** `CommitsBehind.n >= 1` **AND** `last_indexed != current_HEAD`. Why both? Because B2's `CommitsBehind.n` has a fallback path (S4-01 AC-6): if `git rev-list --count <last_indexed>..<HEAD>` fails (e.g., shallow clone, force-push, fixture-seeded commit not in the analyzed repo's history), `n` falls back to `1`. A test asserting only `n >= 1` would pass even if the fallback fired in a degenerate case — e.g., if the freshness check itself were buggy and silently emitted `Stale(CommitsBehind(n=1, last_indexed="<garbage>"))`. The second assertion (`last_indexed != current_HEAD`) anchors the structural fact: the two commits are genuinely different SHAs. Together they survive any fixture regeneration with a different tool version.

This story lands the fixture as a **stub** (minimal SCIP blob + `README.md` policy + `regenerate.sh` guard); the full materialization (an actual `scip-typescript` run against a prior commit, then HEAD moved, then `regenerate.sh` documented) is S7-02. The stub is enough to exercise B2's `scip` freshness check end-to-end — the structural assertion is tool-version-agnostic by design (it asserts shapes, not specific commit counts).

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

A new test file `tests/adv/phase02/test_stale_scip_fixture.py` runs against `tests/fixtures/portfolio/stale-scip/` and asserts the typed structural outcome of `IndexHealthProbe`. The test is **wired into the `adv-phase02` CI job** (placeholder stanza added; S8-03 lands the job YAML). The fixture exists as a stub: directory, `.codegenie/context/raw/scip-index.scip` placeholder, a hand-written `index_health` seed slice file (or equivalent harness input), `README.md` documenting the regeneration policy, and `regenerate.sh` that errors out if invoked against current HEAD. The structural assertions survive any future fixture regeneration that uses a different `scip-typescript` version or moves HEAD by a different commit count.

## Acceptance criteria

- [ ] **AC-1 — Adversarial test exists and asserts the typed outcome.** `tests/adv/phase02/__init__.py` and `tests/adv/phase02/test_stale_scip_fixture.py` exist. The test invokes `IndexHealthProbe.run` (or the gather entry point — implementer choice; the unit-level invocation is simpler and less flaky) against the stale-scip fixture. The test makes **all four** of these assertions in order:
  1. `assert "scip" in slice["index_health"]` — the slice has the SCIP entry (not absent).
  2. `freshness = Stale.model_validate(slice["index_health"]["scip"]["freshness"])` — round-trips through the discriminated-union (the typed value is well-formed).
  3. `assert isinstance(freshness.reason, CommitsBehind)` — the reason variant is exactly `CommitsBehind`, not `IndexerError`/`CoverageGap`/`DigestMismatch`. (Catches the bug "B2 emits a `Stale` but with the wrong reason — e.g., upstream_unavailable masking a real staleness.")
  4. `assert freshness.reason.n >= 1` **AND** `assert freshness.reason.last_indexed != current_HEAD` — the **combined** structural assertion (implementation risk #3). Both inequalities are independently asserted with their own error messages.

- [ ] **AC-2 — `current_HEAD` is derived at test time, not hardcoded.** The test computes `current_HEAD` via `subprocess.run(["git", "rev-parse", "HEAD"], cwd=fixture_path, ...)` (the same path B2 takes — but at test boundary, not inside production code). Hardcoding a specific SHA would make the test brittle against fixture regeneration. The test value must survive `regenerate.sh` producing a new commit graph.

- [ ] **AC-3 — Fixture directory + minimal contents land in this story.** `tests/fixtures/portfolio/stale-scip/` exists as a **stub**:
  - `.git/` — a real git work tree (initialized via `regenerate.sh`; ≥ 2 commits so HEAD has moved by ≥ 1 from the seeded `last_indexed_commit`).
  - `.codegenie/context/raw/scip-index.scip` — a minimal placeholder blob (could be empty bytes or a hand-crafted 16-byte stub; the test does NOT parse this binary, S4-03's `ScipIndexProbe` does — and that probe is not invoked here).
  - One harness input that B2 reads as the `semantic_index` sibling slice. Implementer choice between (a) a hand-written `.codegenie/context/raw/semantic_index.json` consumed via the coordinator slice map, or (b) a Pytest fixture that constructs the synthetic sibling slice in-memory. Option (b) is preferred for unit-level adversarial (matches S4-01 testing pattern) and avoids coupling the test to S4-03's not-yet-shipped probe output format. **Whichever option is chosen, the seeded `last_indexed_commit` must be the SHA of the parent commit (not HEAD).**
  - A minimal `package.json` (`{"name": "stale-scip-fixture", "private": true}`) so any future Phase-1-probe path that runs first does not error.

- [ ] **AC-4 — `tests/fixtures/portfolio/stale-scip/README.md` documents the regeneration policy.** The README states verbatim (or equivalent prose):
  - "**This fixture is LOAD-BEARING for the Phase 2 roadmap exit criterion.** Do not delete, do not retarget the seeded `last_indexed_commit` to current `HEAD`."
  - "Regeneration: run `./regenerate.sh` from this directory. The script creates ≥ 2 commits and seeds `last_indexed_commit` to the **parent** commit, so HEAD is genuinely ahead by ≥ 1."
  - "The structural assertion is `CommitsBehind.n >= 1` **AND** `last_indexed != current_HEAD`. Both are tool-version-agnostic. Do not assert on a specific `n` value."
  - "If you bump `scip-typescript`'s version (S4-03 / S7-02), regenerate; the structural assertion survives any version bump."
  - "Full fixture materialization (real `scip-typescript` invocation against a prior commit) lands in S7-02. This stub is enough for S4-02's adversarial assertion."

- [ ] **AC-5 — `regenerate.sh` errors out if retargeted to current HEAD.** `tests/fixtures/portfolio/stale-scip/regenerate.sh` is executable, reviewed-as-code, and contains an explicit guard:
  ```bash
  if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
    echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
    echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
    exit 1
  fi
  ```
  A unit test (`test_regenerate_sh_guard`) invokes the script with a sentinel env that forces this branch and asserts exit code 1 plus the stderr message.

- [ ] **AC-6 — Test failure mode is loud and actionable.** When the adversarial fails (a future B2 regression), pytest's `--tb=long` shows:
  1. The exact `IndexFreshness` value B2 emitted (via `freshness.model_dump_json(indent=2)`).
  2. The expected structural shape (`Stale(reason=CommitsBehind(n>=1, last_indexed != HEAD))`).
  3. A pointer to this story file + the [`production/design.md §2.3`](../../../production/design.md) honest-confidence commitment.
  Use `pytest.fail(msg)` with a multiline string, not bare `assert` — the diagnostic at CI-failure time is the load-bearing artifact (Rule 12 — fail loud).

- [ ] **AC-7 — Test is wired into the `adv-phase02` placeholder.** `pyproject.toml` (or `tests/conftest.py` registration; implementer choice) registers a pytest marker `phase02_adv` so `pytest -m phase02_adv tests/adv/phase02/` selects this test. The CI YAML stanza is OUT OF SCOPE here (S8-03 lands it); this story land the marker, the directory layout, and a `tests/adv/phase02/conftest.py` that the future job points at. A unit test asserts `"phase02_adv" in markers` so accidental removal of the marker is caught.

- [ ] **AC-8 — No skip-on-missing-tool path.** This test must not `pytest.skip` on any condition — it is build-gating. If `git` is missing, the test fails with a clear "git not on PATH; this is a developer-environment bug, not a test skip" message. (Phase 0's `fence` job already ensures `git` is present on the CI runner.)

- [ ] **AC-9 — No false-passing path under registry-empty.** Defensive: if the test is somehow invoked with an empty `@register_index_freshness_check` registry (e.g., S4-01's `scip` check is not registered), B2 emits `slice == {}` (S4-01 AC-11) and the test fails at AC-1 step 1 (`"scip" in slice["index_health"]`). The test must NOT silently pass via the empty-slice path. A unit test (`test_empty_registry_fails_adversarial`) explicitly clears the freshness registry, runs the adversarial under that condition, and asserts the adversarial fails.

- [ ] **AC-10 — The test runs in < 10 s on CI.** Adversarial tests are part of CI critical path; a slow adversarial penalizes every PR. The fixture is small enough that B2 (unit-level invocation, no real `scip-typescript`) completes in < 1 s; the test budget is 10 s including pytest setup. If the time creeps past 10 s in CI, the bench advisory (S8-03's `bench_index_health_overhead`) catches it.

- [ ] **AC-11 — Tooling green.** `ruff check tests/adv/phase02/`, `ruff format --check`, `mypy --strict tests/adv/phase02/test_stale_scip_fixture.py` all pass. The fixture's `.git/` directory is gitignored from coverage measurement.

## Implementation outline

The shape is **deliberately a single test method with maximum diagnostic value** (Rule 2 / Rule 9 / Rule 12). Helpers stay inline so a future contributor reading the test sees the structural assertion in one screen.

1. **Create `tests/adv/phase02/__init__.py`** (empty) and `tests/adv/phase02/conftest.py` (the registration point for the pytest marker and a `fixture_path` fixture that resolves to `tests/fixtures/portfolio/stale-scip/`).

2. **Create the fixture directory `tests/fixtures/portfolio/stale-scip/`:**

    - `regenerate.sh` (executable, shellcheck-clean):
      ```bash
      #!/usr/bin/env bash
      # Regenerates the stale-scip fixture. See README.md.
      # MUST keep HEAD ahead of $LAST_INDEXED by >= 1 commit.
      set -euo pipefail
      cd "$(dirname "$0")"
      rm -rf .git .codegenie
      git init -q -b main
      git config user.email "fixture@codewizard.local"
      git config user.name  "Fixture Bot"
      printf '{"name":"stale-scip-fixture","private":true}\n' > package.json
      git add package.json && git commit -q -m "v0 — seeded last_indexed_commit"
      LAST_INDEXED=$(git rev-parse HEAD)
      printf 'export const x = 1;\n' > main.ts
      git add main.ts && git commit -q -m "v1 — HEAD moves forward"
      mkdir -p .codegenie/context/raw
      printf '' > .codegenie/context/raw/scip-index.scip  # placeholder blob
      # Seed harness input — semantic_index slice naming the parent commit.
      cat > .codegenie/context/raw/semantic_index.json <<JSON
      {"last_indexed_commit": "$LAST_INDEXED",
       "last_indexed_at": "2026-04-26T08:00:00Z",
       "files_indexed": 1, "files_in_repo": 1, "indexer_errors": 0}
      JSON
      # Guard: refuse retargeting to HEAD.
      if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
        echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
        echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
        exit 1
      fi
      echo "stale-scip fixture regenerated. last_indexed=$LAST_INDEXED head=$(git rev-parse HEAD)"
      ```
    - `README.md` per AC-4.
    - Optional: a `.gitattributes` declaring `.codegenie/context/raw/scip-index.scip binary` so git does not corrupt the placeholder.

3. **Decide harness input style.** Recommended: in-test synthetic sibling slice (Option b of AC-3), so the test does not couple to S4-03's not-yet-shipped probe output. The fixture's `semantic_index.json` file is the artifact left on disk for documentation / S7-02 integration; the test reads it but passes the parsed dict as `ctx.sibling_slices["scip"]` directly to B2's `run()`.

4. **Write `test_stale_scip_fixture.py`** (~80 LOC):

    ```python
    # tests/adv/phase02/test_stale_scip_fixture.py
    from __future__ import annotations
    import asyncio, json, subprocess
    from pathlib import Path
    import pytest
    from codegenie.indices.freshness import Stale, CommitsBehind
    from codegenie.probes.layer_b.index_health import IndexHealthProbe
    from tests.helpers.probe_context import build_probe_context  # Phase 0 helper

    pytestmark = pytest.mark.phase02_adv

    FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"

    def _current_head(repo: Path) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    def test_index_health_catches_stale_scip(tmp_path: Path) -> None:
        """Roadmap exit criterion: IndexHealthProbe surfaces a real staleness case.

        Build FAILS if B2 does not catch the deliberately-seeded staleness.
        See: docs/phases/02-context-gather-layers-b-g/stories/S4-02-stale-scip-adversarial.md.
        """
        if not FIXTURE.exists():
            pytest.fail(
                f"stale-scip fixture missing at {FIXTURE}. "
                "Run tests/fixtures/portfolio/stale-scip/regenerate.sh."
            )
        head = _current_head(FIXTURE)
        sibling = json.loads((FIXTURE / ".codegenie/context/raw/semantic_index.json").read_text())
        ctx = build_probe_context(snapshot_root=FIXTURE, sibling_slices={"scip": sibling})

        probe = IndexHealthProbe()
        out = asyncio.run(probe.run(ctx))

        # AC-1 step 1.
        assert "scip" in out.schema_slice["index_health"], (
            f"B2 emitted no 'scip' entry. Slice keys: {list(out.schema_slice['index_health'].keys())}. "
            "Either the @register_index_freshness_check('scip') is missing (S4-01 regression) "
            "or B2's registry loop is broken."
        )
        # AC-1 step 2.
        raw = out.schema_slice["index_health"]["scip"]["freshness"]
        freshness = Stale.model_validate(raw)  # validate that the discriminated-union round-trips
        # AC-1 step 3.
        assert isinstance(freshness.reason, CommitsBehind), (
            f"Expected Stale(reason=CommitsBehind), got Stale(reason={type(freshness.reason).__name__}). "
            f"Full freshness:\n{json.dumps(raw, indent=2)}\n"
            "See production/design.md §2.3 (honest confidence) — silent staleness or wrong-reason-variant "
            "is the load-bearing failure mode."
        )
        # AC-1 step 4 — BOTH inequalities (implementation risk #3).
        assert freshness.reason.n >= 1, (
            f"Expected CommitsBehind.n >= 1, got n={freshness.reason.n}. "
            f"Full freshness:\n{json.dumps(raw, indent=2)}"
        )
        assert freshness.reason.last_indexed != head, (
            f"Expected CommitsBehind.last_indexed != current HEAD, but both are {head!r}. "
            "The fixture's seeded last_indexed_commit must be the parent commit, NOT HEAD. "
            "Did regenerate.sh's guard fail? See tests/fixtures/portfolio/stale-scip/README.md."
        )
    ```

5. **Wire the pytest marker** in `pyproject.toml`:
    ```toml
    [tool.pytest.ini_options]
    markers = [
        # ... existing markers ...
        "phase02_adv: Phase 2 adversarial tests (CI-gating; see tests/adv/phase02/)",
    ]
    ```

6. **Add the `test_regenerate_sh_guard` unit test** at `tests/unit/fixtures/test_stale_scip_regenerate_guard.py`: invokes the script in a temp dir with `LAST_INDEXED` set to the value of `git rev-parse HEAD` (force the guard branch) and asserts exit code 1 plus stderr contains "refuses to set". This is the only place we test shell behavior — keep it surgical (Rule 3).

7. **Add the `test_empty_registry_fails_adversarial` unit test** at `tests/unit/probes/layer_b/test_index_health_empty_registry_adversarial.py`: clears the freshness registry via `_clear_for_tests()` (S1-02 helper), invokes B2 against the stale-scip fixture, asserts B2's slice is empty AND that re-running the adversarial assertion would fail at "scip" in slice. This is the AC-9 anti-false-pass guard.

## TDD plan — red / green / refactor

### RED

- **T-01** `test_index_health_catches_stale_scip` (the main adversarial) FAILS initially because the fixture directory does not exist. Add the fixture skeleton (empty directory, empty `regenerate.sh`); rerun; FAILS with "regenerate.sh not run." Run `regenerate.sh`; rerun; the test invokes B2 which (assuming S4-01 is GREEN) emits `Stale(CommitsBehind(...))` and the test PASSES.
- **T-02** `test_regenerate_sh_guard`: FAILS until the guard branch is added to `regenerate.sh`.
- **T-03** `test_empty_registry_fails_adversarial`: FAILS until `_clear_for_tests` is called before the run; once added, it passes because B2 emits `{}` and the AC-1 step-1 assertion fails.
- **T-04** `test_marker_registered`: `pytest --markers` output contains `phase02_adv`. FAILS until `pyproject.toml` is updated.
- **T-05** Mutation test (manual, documented in the test docstring): temporarily change S4-01's `scip_freshness` to always return `Fresh(indexed_at=datetime.now())` — rerun T-01 — assert it FAILS at the AC-1 step 2 / step 3 boundary. Revert. (This is a documented manual check, not a CI step — it verifies the test catches the load-bearing regression.)

### GREEN

Implement the fixture, the regenerate script, the adversarial test, and the marker. T-01 through T-04 turn green.

### REFACTOR

- Confirm the error messages on each assertion are actionable (a future CI failure must point a contributor at this story and at `production/design.md §2.3`).
- Verify the test completes in < 10 s (AC-10).
- Run `git status` from `tests/fixtures/portfolio/stale-scip/` and confirm `.git/` is properly committed (the fixture's git repo lives inside the codewizard-sherpa git repo — submodule-or-vendored question is implementer-decided; the simplest shape is vendored with `.gitattributes binary` for the SCIP blob and a `.gitkeep` if needed; see S7-01 for how other fixtures handle this).

## Files to touch

**Create:**
- `tests/adv/phase02/__init__.py`
- `tests/adv/phase02/conftest.py` — defines the `phase02_adv` marker and a `fixture_path` fixture.
- `tests/adv/phase02/test_stale_scip_fixture.py`
- `tests/fixtures/portfolio/stale-scip/regenerate.sh` (executable)
- `tests/fixtures/portfolio/stale-scip/README.md`
- `tests/fixtures/portfolio/stale-scip/.gitattributes` (declares the SCIP blob binary)
- `tests/unit/fixtures/test_stale_scip_regenerate_guard.py`
- `tests/unit/probes/layer_b/test_index_health_empty_registry_adversarial.py`

**Run once (artifacts committed):**
- `tests/fixtures/portfolio/stale-scip/.git/` (real git work tree — initialized by `regenerate.sh`).
- `tests/fixtures/portfolio/stale-scip/package.json`
- `tests/fixtures/portfolio/stale-scip/main.ts`
- `tests/fixtures/portfolio/stale-scip/.codegenie/context/raw/scip-index.scip` (placeholder blob)
- `tests/fixtures/portfolio/stale-scip/.codegenie/context/raw/semantic_index.json` (seed sibling slice)

**Edit (additive):**
- `pyproject.toml` — add `phase02_adv` marker to `[tool.pytest.ini_options].markers`.

## Out of scope

- **Full fixture materialization via real `scip-typescript` invocation.** S7-02 owns this — runs `scip-typescript` against the parent commit, replaces the placeholder `.scip` blob with the real binary, documents the regeneration ritual against tool-version bumps. This story ships a stub sufficient to gate B2's typed outcome.
- **The `adv-phase02` CI job YAML.** S8-03 lands the eight CI jobs including `adv-phase02`. This story registers the pytest marker; that story consumes the marker in `.github/workflows/`.
- **Adversarial tests for other failure modes.** S5-05 (image-digest-drift), S5-06 (adversarial-dockerfile), S6-07 (secret-in-source), S7-04 (hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped) all join `tests/adv/phase02/` later. Each is independent.
- **Renderer assertion that the typed value lands in `CONTEXT_REPORT.md`.** S8-01's renderer story will exercise pattern-matching on this exact `Stale(CommitsBehind(...))` value; this story stops at the typed-value boundary.
- **Property-based round-trip of `IndexFreshness`.** S1-02 already covers `tests/property/test_index_freshness_roundtrip.py` (Hypothesis) at the unit level. This story uses **concrete** values from the fixture — adversarial-test discipline (real seeded scenario, not generated input).

## Notes for the implementer

- **Why a stub fixture is enough here.** B2's `scip` freshness check (S4-01 AC-5) reads the `last_indexed_commit` field from the `semantic_index` sibling slice, NOT the SCIP binary itself. Producing a real `.scip` binary is S4-03's `ScipIndexProbe` job, and the binary is exercised end-to-end in S7-02's portfolio sweep. The adversarial test path bypasses the binary entirely — it passes a synthetic sibling slice (in-test dict or seeded JSON file) and asserts B2's typed output. Coupling the adversarial to a real `scip-typescript` run would (a) require `scip-typescript` on every CI runner that runs `adv-phase02` (currently true, but coupling tightly is wasteful), (b) make the test fail for unrelated reasons (e.g., a `scip-typescript` minor-version bump), (c) lengthen CI runtime past AC-10's 10 s budget. The structural assertion is the contract; the binary-format pathway is integration territory.
- **Why both inequalities (`n >= 1` AND `last_indexed != HEAD`).** Implementation risk #3 from the manifest spells this out. S4-01 AC-6 has a fallback path where `n` falls back to `1` if `git rev-list --count` fails. A test asserting only `n >= 1` would pass even if the fallback fired in a degenerate state where `last_indexed == HEAD` (which would be a B2 bug — emitting `CommitsBehind` for a non-stale state). Asserting `last_indexed != HEAD` independently anchors the structural fact that the two commits are genuinely different, which is the actual definition of "stale." Both assertions together are what makes the test tool-version-agnostic AND fallback-resilient.
- **Don't `pytest.skip`.** AC-8 forbids skip paths. The adversarial test is build-gating; skipping it silently is the same failure mode B2 is built to prevent (silent staleness → silent skip). If a missing prerequisite is detected, `pytest.fail` with a clear message, never `pytest.skip`.
- **`build_probe_context` helper.** Phase 0 ships a test helper at `tests/helpers/probe_context.py` for constructing a synthetic `ProbeContext`. Use it; do not construct `ProbeContext` ad-hoc in the test file (Rule 11 — match the codebase convention).
- **Mutation test as design verification (T-05).** It is documented as a manual check rather than a CI step because mutation-testing infrastructure is a Phase 6 (formal mutation harness) concern. But every implementer of this story should run T-05 manually before opening the PR — temporarily make `scip_freshness` always return `Fresh`, confirm the adversarial fails loudly at the right assertion, then revert. This is the "tests verify intent" check from Rule 9.
- **The fixture's git repo inside this git repo.** The simplest shape is a vendored `.git/` directory (committed verbatim — git tracks git's own internals just fine; many test corpora do this). Alternative: an init script that creates `.git/` on demand and gitignores it — adds a "first run is slow" wart. Pick vendored for determinism; S7-01 / S7-02 will normalize this across all five fixtures.
- **Rule 12 — fail loud.** Every `assert` in the adversarial test has a multi-line error message that points to (a) what shape was expected, (b) what shape was actually emitted (`model_dump_json(indent=2)`), (c) the story / ADR / production doc that explains why. When this test fails in CI six months from now, the person fixing it must not need to read the test source to understand the failure.
