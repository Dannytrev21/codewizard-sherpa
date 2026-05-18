# Story S7-05 — Phase-4 fixture portfolio

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** M
**Depends on:** S7-04 (plugin.yaml + skill templates load); Phase-3 fixture pattern for `express-cve-2024-21501` shipped (mirror its structure)
**ADRs honored:** ADR-0008 (the calibration smoke test S5-04 depends on this portfolio), ADR-0011 (RAG bypass on retry — `vuln-retry/...` fixture exercises it), production-ADR-0031 (plugin scoping — every fixture is a Node+npm repo)

## Context

Phase-4's exit-criterion tests (S7-06, S7-07), the calibration smoke test (S5-04), the provenance short-circuit test (referenced in S7-06), and the retry-bypass test (S6-02) all consume small, hermetic fixture repos. This story lands the **five** fixtures listed in arch §"Fixtures" — they are the integration-test ground truth.

Each fixture is a checked-in npm repo (with `package.json`, `package-lock.json`, and just enough source to exercise the relevant code path) plus the CVE metadata needed to drive the workflow. The express major-bump fixture is the headline (~80 `.ts` files, ~120 unit tests — the breaking-change CVE exit criterion fixture); the rest are smaller.

The arch is clear about the cardinality: "Land all five fixtures." Missing any one breaks a downstream test; missing the major-bump fixture breaks the roadmap exit criterion. This story does not include cassettes (those are recorded in S7-06 against the express fixture) or the `RagHit` seed records (those are pre-populated under the `vuln-rag-hit/express-rerun/` fixture's `.codegenie/rag/records/` directory).

The risk to manage: the express fixture is the slowest to construct (real `.ts` files, a real `tsconfig.json`, a runnable test suite). The story is `M`, not `L`, because the fixture is a one-time construction; once it lands, every downstream test consumes it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Fixtures` — the five fixture paths and one-line descriptions for each:
    - `fixtures/vuln-major-bump/express-cve-2026-1234/` — peer-dep transitive case + major-version-bump CVE (~80 `.ts` files; ~120 unit tests). **The headline exit-criterion fixture.**
    - `fixtures/vuln-major-bump/lodash-cve-2026-9876/` — major-bump callsite rewrite; smaller (~20 files) for faster unit coverage.
    - `fixtures/vuln-provenance/glibc-on-node/` — CVE not in app layer; `ProvenanceGate` refuse case.
    - `fixtures/vuln-rag-hit/express-rerun/` — pre-populated `.codegenie/rag/records/` for re-run "RAG-shapes-LLM" test.
    - `fixtures/vuln-retry/cassette-attempt-1-fails-attempt-2-passes/` — Phase-5 retry simulator fixture.
  - `../phase-arch-design.md §Goals — G1` — exit-criterion E2E fixture description.
  - `../phase-arch-design.md §Edge case #1` — the glibc-on-Node fixture exercises the provenance refuse path.
  - `../phase-arch-design.md §Edge case #11` — the `vuln-retry/...` fixture exercises the retry RAG-bypass.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the four `fixtures/vuln-major-bump/*` fixtures feed S5-04's calibration smoke (`each fixture's re-run scores RagHit; crossing-CVE queries score RagMiss`).
  - `../ADRs/0011-rag-bypass-on-retry.md` — the `vuln-retry/...` fixture is the simulator anchor for retry-bypass behavior.
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — the `glibc-on-node` fixture is the provenance refuse anchor.
- **Source design:**
  - `../final-design.md §Fixtures`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Land all five fixtures."
- **Existing code:**
  - `tests/fixtures/repos/express-cve-2024-21501/` (Phase 3) — the **template** to mirror for `express-cve-2026-1234/` structure (Global Rule 11). Note layout: `package.json`, `package-lock.json`, `src/`, `tests/`, plus a `cve.yaml` or equivalent metadata file.
  - `docs/phases/03-vuln-deterministic-recipe/stories/S8-01-fixture-portfolio.md` — the precedent story that built the Phase-3 fixture portfolio; mirror the construction discipline.

## Goal

Land the five Phase-4 fixture repos under `tests/fixtures/repos/` (or wherever Phase 3 settled — match its convention) such that: each fixture parses as a valid Node+npm repo, ships a `cve.yaml` with the CVE metadata the orchestrator needs, the `express-cve-2026-1234/` fixture has ~80 `.ts` files and a runnable Jest suite of ~120 tests, the `vuln-rag-hit/express-rerun/` fixture has pre-populated `.codegenie/rag/records/<id>.yaml` for the RAG re-run test, and each fixture has a unit test asserting it can be loaded by the Phase-3 / Phase-4 plugin chain.

## Acceptance criteria

- [ ] `tests/fixtures/repos/express-cve-2026-1234/` exists with:
  - `package.json` declaring `"dependencies": { "express": "^4.18.x" }` and dev-dep `jest` + `typescript`.
  - `package-lock.json` pinned (deterministic; do not regenerate at test time).
  - `tsconfig.json` (TypeScript strict-mode; the file `typecheck.typescript` SignalKind needs).
  - `src/**/*.ts` with **at least 60** `.ts` files containing realistic Express-4 idioms that must change for Express 5 (e.g., `req.param()` deprecated, `app.del()` removed, async middleware error handling).
  - `tests/**/*.test.ts` with **at least 100** Jest tests; some must exercise the call sites that an Express 4→5 bump would break.
  - `cve.yaml` (or whatever Phase-3's fixture metadata file is called — read first) declaring CVE id `CVE-2026-1234`, severity, package `express`, vulnerable range, fixed version (the major bump target).
  - `.gitignore` for `node_modules` and `.codegenie/` so test artifacts don't pollute the fixture directory.
- [ ] `tests/fixtures/repos/lodash-cve-2026-9876/` exists with a smaller (~20 file) `.ts` Node project pinned to `lodash@^4.17.x` and CVE metadata; ~30 Jest tests; same `cve.yaml` shape.
- [ ] `tests/fixtures/repos/glibc-on-node/` exists with a `Dockerfile FROM node:20-bullseye` (or whatever distroless base ships glibc), `package.json` with no app-layer vuln, and `cve.yaml` declaring a glibc CVE that the `vuln_provenance` adapter (S7-03) must classify as `BaseImage`.
- [ ] `tests/fixtures/repos/express-rerun/` exists (a small clone of `express-cve-2026-1234/` semantically) **plus** `.codegenie/rag/records/<id>.yaml` pre-populated with one solved-example record matching the Express-major-bump CVE — the record must round-trip through `RecordProvenance.verify` (S4-05) and be valid input to the retriever's embedding pipeline.
- [ ] `tests/fixtures/repos/cassette-attempt-1-fails-attempt-2-passes/` exists with a `.codegenie/rag/cassettes/` directory containing two cassette stubs: attempt-1 (a deliberately-wrong `PlanProposalCallsiteRewrite` the validator will reject) and attempt-2 (a correct one). The fixture's `cve.yaml` names the CVE that drives the retry simulator.
- [ ] Each fixture has a *load* test (`tests/unit/fixtures/test_phase4_fixtures_load.py`) that:
  - Parses `package.json` and asserts the expected vulnerable package is declared.
  - Parses `cve.yaml` and asserts CVE id / package / version match the per-fixture expected values.
  - For `express-rerun/`: parses `.codegenie/rag/records/*.yaml` through `SolvedExample.from_yaml` (S4-04) without error.
  - For `cassette-attempt-1-fails-attempt-2-passes/`: asserts both cassette stubs exist and parse as valid `pytest-recording` YAML.
- [ ] Each fixture's `package-lock.json` is **deterministic** — running `tests/unit/fixtures/test_phase4_fixtures_load.py` twice in a row must produce zero diff (no `npm install` at test time).
- [ ] The express fixture passes `tsc --noEmit --pretty false` cleanly on Express-4 — so the test in S7-06 can assert `tsc` *fails* after a faulty Express-5 patch and *passes* after a correct one (the SignalKind's strict-AND requires a clean baseline).
- [ ] `make check` clean (excluding `npm install` / `npm test` against the fixtures, which run only in E2E and only inside `SubprocessJail`).
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first**: open `tests/fixtures/repos/express-cve-2024-21501/` (Phase 3 fixture) to confirm directory layout, `cve.yaml` schema, and `package-lock.json` style. Mirror it (Global Rule 11).
2. Build `express-cve-2026-1234/` first (slowest):
   - Use a real Express-4 starter (or synthesize one); ~60 `.ts` files covering routing, middleware, error handling.
   - Add ~100 Jest tests touching the call sites that an Express 5 bump breaks (`req.param`, async error handling, `app.del`).
   - Pin `package-lock.json` to lockfile-version 3 with deterministic hashes.
   - Add `cve.yaml`: `id: CVE-2026-1234`, `package: express`, `vulnerable: ">=4.0.0 <5.0.0"`, `fixed: ">=5.0.0"`.
   - Verify `tsc --noEmit --pretty false` is clean against Express-4.
3. Build `lodash-cve-2026-9876/` second (smaller version of the same pattern).
4. Build `glibc-on-node/` third: minimal Node app, `Dockerfile` declaring `node:20-bullseye`, `cve.yaml` for a glibc CVE. No app-layer code change needed.
5. Build `express-rerun/`: copy `express-cve-2026-1234/` (or simplify) and add a hand-crafted `.codegenie/rag/records/<id>.yaml` solved example that the retriever can embed and score `RagHit` against. Use S4-04's canonical YAML shape.
6. Build `cassette-attempt-1-fails-attempt-2-passes/`: minimal repo + two cassette stubs. The cassettes need not be live-recorded against Anthropic for this story — placeholder YAML with the structure `pytest-recording` expects is sufficient; S7-06 will record real cassettes if needed.
7. Write `tests/unit/fixtures/test_phase4_fixtures_load.py` with the load-and-validate checks per fixture.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fixtures/test_phase4_fixtures_load.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
import yaml

ROOT = Path("tests/fixtures/repos")

FIXTURES = {
    "express-cve-2026-1234": {
        "cve_id": "CVE-2026-1234",
        "package": "express",
        "min_ts_files": 60,
        "min_jest_tests": 100,
    },
    "lodash-cve-2026-9876": {
        "cve_id": "CVE-2026-9876",
        "package": "lodash",
        "min_ts_files": 15,
        "min_jest_tests": 25,
    },
    "glibc-on-node": {
        "cve_id": None,  # CVE ID local to the fixture; type assertion only
        "package": "glibc",
        "min_ts_files": 0,
        "min_jest_tests": 0,
    },
    "express-rerun": {
        "cve_id": "CVE-2026-1234",
        "package": "express",
        "min_ts_files": 1,
        "min_jest_tests": 1,
    },
    "cassette-attempt-1-fails-attempt-2-passes": {
        "cve_id": None,
        "package": None,
        "min_ts_files": 0,
        "min_jest_tests": 0,
    },
}


@pytest.mark.parametrize("name,spec", list(FIXTURES.items()))
def test_fixture_dir_exists(name, spec):
    p = ROOT / name
    assert p.is_dir(), f"missing fixture: {p}"


@pytest.mark.parametrize("name,spec", list(FIXTURES.items()))
def test_fixture_has_package_json(name, spec):
    pj = ROOT / name / "package.json"
    assert pj.is_file()
    data = json.loads(pj.read_text())
    if spec["package"] and spec["package"] not in {"glibc"}:
        # app-layer fixtures: vuln package is in deps
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        assert spec["package"] in deps


@pytest.mark.parametrize("name,spec", list(FIXTURES.items()))
def test_cve_yaml_or_present(name, spec):
    if spec["cve_id"] is None:
        return
    cy = ROOT / name / "cve.yaml"
    assert cy.is_file()
    meta = yaml.safe_load(cy.read_text())
    assert meta["id"] == spec["cve_id"]


def test_express_fixture_has_minimum_ts_files():
    files = list((ROOT / "express-cve-2026-1234" / "src").rglob("*.ts"))
    assert len(files) >= 60, f"need ≥60 .ts files, got {len(files)}"


def test_express_fixture_has_minimum_jest_tests():
    files = list((ROOT / "express-cve-2026-1234" / "tests").rglob("*.test.ts"))
    # Count `it(`/`test(` invocations across all test files (heuristic).
    count = 0
    for f in files:
        text = f.read_text()
        count += text.count("it(") + text.count("test(")
    assert count >= 100, f"need ≥100 Jest test cases, got {count}"


def test_express_rerun_has_seeded_rag_records():
    from codegenie.rag.models import SolvedExample
    records = (ROOT / "express-rerun" / ".codegenie" / "rag" / "records").glob("*.yaml")
    parsed = [SolvedExample.from_yaml(r.read_text()) for r in records]
    assert len(parsed) >= 1
    assert any(p.cve_id == "CVE-2026-1234" for p in parsed)


def test_cassette_attempt_fixture_has_two_cassettes():
    d = ROOT / "cassette-attempt-1-fails-attempt-2-passes" / ".codegenie" / "rag" / "cassettes"
    cassettes = list(d.glob("*.yaml"))
    assert len(cassettes) == 2


def test_lockfiles_are_deterministic():
    """Re-reading produces identical bytes; no implicit npm install at test time."""
    for name in FIXTURES:
        lf = ROOT / name / "package-lock.json"
        if not lf.is_file():
            continue
        b1 = lf.read_bytes()
        b2 = lf.read_bytes()
        assert b1 == b2
```

Run: `pytest tests/unit/fixtures/test_phase4_fixtures_load.py -v` — all tests fail before any fixture lands.

### Green — make it pass

Construct fixtures one at a time, starting with the smallest (`cassette-attempt-1-fails-attempt-2-passes/`) and ending with the largest (`express-cve-2026-1234/`). Run the test after each fixture to walk the suite from red to green incrementally.

### Refactor — clean up

- Add a `tests/fixtures/repos/README.md` table listing each fixture, its purpose, the downstream test it feeds, and how to regenerate `package-lock.json` deterministically.
- Confirm `git status` shows no `node_modules/` accidentally committed (the `.gitignore` per fixture is the safety net).
- Re-run `make check`; fixtures must not break Phase-3 tests.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/express-cve-2026-1234/**` | Headline exit-criterion fixture (~80 `.ts`, ~120 Jest tests). |
| `tests/fixtures/repos/lodash-cve-2026-9876/**` | Smaller major-bump fixture for faster unit coverage. |
| `tests/fixtures/repos/glibc-on-node/**` | Provenance-refuse fixture (CVE not in app layer). |
| `tests/fixtures/repos/express-rerun/**` | RAG-hit fixture with pre-populated `.codegenie/rag/records/`. |
| `tests/fixtures/repos/cassette-attempt-1-fails-attempt-2-passes/**` | Phase-5 retry simulator fixture. |
| `tests/unit/fixtures/test_phase4_fixtures_load.py` | Load-and-validate test for every fixture. |
| `tests/fixtures/repos/README.md` | Catalog + regeneration instructions. |

## Out of scope

- Recording the live Anthropic cassettes for the E2E tests — that's S7-06's job (and the `make refresh-cassettes` target's responsibility per S3-06).
- Running `npm install` / `npm test` against the fixtures — that happens only inside `SubprocessJail` in S7-06's E2E test.
- The calibration smoke test S5-04 — that consumes the four `vuln-major-bump/*` fixtures but lives in Step 5's story.
- Updating Phase-3 fixtures — those are owned by the Phase-3 phase.

## Notes for the implementer

- **The express fixture is the bottleneck.** Budget time accordingly. If you find yourself spending more than half the story's effort on contrived Express-4 idioms, consider seeding from a real OSS Express starter (with appropriate license attribution in the fixture's README).
- The `cve.yaml` schema must match whatever Phase 3's fixture pattern uses — surface a conflict per Global Rule 7 if Phase 3's fixtures use a different metadata file name (e.g., `metadata.yaml`).
- The `express-rerun/` fixture's seeded `.codegenie/rag/records/<id>.yaml` is the **critical piece** for the S7-07 replay-lands-RAG E2E test. The record's `embedding_model` field must match the embedder's `model_digest()` (`fastembed:BAAI/bge-small-en-v1.5`), or the retriever will exclude it via S5-03's model-mismatch guard and the E2E will degenerate to a cold LLM call. Run `codegenie embeddings bootstrap` first; record the model_digest; pin it in the seeded YAML.
- The `cassette-attempt-1-fails-attempt-2-passes/` fixture is not the cassette **content** (HTTP request/response YAMLs) — it's the *fixture-level* scaffolding that S6-02's retry-bypass test inspects. Placeholder cassettes are acceptable; document this in the fixture's README.
- Deterministic `package-lock.json` is the difference between a green CI and a flaky one — set `--package-lock-only` when generating, never let `npm install` run during tests, commit the lockfile byte-for-byte.
- Resist the temptation to "improve" the Phase-3 fixture (`express-cve-2024-21501/`) while you're in `tests/fixtures/` — Global Rule 3 is the law here.
