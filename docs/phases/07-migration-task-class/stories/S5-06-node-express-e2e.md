# Story S5-06 — Node Express fixture + roadmap E2E test (G5)

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** L
**Depends on:** S4-04, S5-05
**ADRs honored:** ADR-P7-001 (parallel ledger / loop), ADR-P7-005 (parallel CLI verb), ADR-P7-006 (`Recipe.engine="dockerfile"`), ADR-P7-007 (`dive_efficiency` advisory-only — happy-path size ratio is informational), Phase 6 ADR-0001 (factory invocation)

## Context

This story closes **roadmap exit criterion G5** — the end-to-end test that migrates a Node.js Express service from `node:20-bullseye-slim` to `cgr.dev/chainguard/node:20-distroless` through the recipe path. Every Step 5 piece must work together: the CLI parses arguments → builds the `DistrolessLedger` → `build_distroless_loop().ainvoke(...)` → `ingest_target` → `resolve_target_image` (catalog hit) → `select_recipe` (matches `swap_base_image_single_stage.yaml`) → `apply_recipe` (recipe path, `last_engine="dockerfile_recipe"`) → `validate_in_sandbox` (build → grype → dive → strace) → strict-AND gate passes → `record_attempt` → `emit_artifact` → exit 0 with `migration-report.yaml` matching the golden.

The five concrete gate-time assertions per arch §Scenario 1 + High-level-impl Step 5 §Done criteria:
1. `last_engine == "dockerfile_recipe"` (recipe path, not RAG, not LLM fallback)
2. `grype` CVE delta on candidate image is `≤ 0` vs pre-image
3. `ShellInvocationTraceProbe` reports `runtime_shell_count == 0`, `confidence == "high"`
4. `dive` reports no `/bin/sh` in the final image layer (signal `shell_presence.passed=True`)
5. Patch matches `tests/golden/dockerfile_swap_node20.patch` byte-for-byte

This is the load-bearing test for the entire phase. Risks: cold pull of `cgr.dev` base on CI runners (arch §Edge cases #16), `~/.docker/config.json` credential setup (arch §Edge cases #7), strace under DinD on macOS (arch §Risks Step 5).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenario 1: Happy path — recipe match → build → all gates pass` (lines 365–407) — exact sequence diagram and final state expectations.
  - `../phase-arch-design.md §Goals — G5 / final-design "Express E2E"` — the roadmap exit criterion this story closes.
  - `../phase-arch-design.md §Testing strategy — Integration tests` (lines 1228–1239) — `test_migrate_node_e2e.py` listed as G5.
  - `../phase-arch-design.md §Testing strategy — Golden files` (lines 1254–1262) — `migration_report_node_e2e.yaml`, `dockerfile_swap_node20.patch`.
  - `../phase-arch-design.md §Fixture portfolio` (lines 1264–1273) — `express-distroless/` fixture spec.
  - `../phase-arch-design.md §Edge cases #7, #16` — Chainguard auth + cold-pull risks.
  - `../High-level-impl.md §Step 5 — Done criteria` (lines 166–174) — the five gate assertions.
- **Phase ADRs:**
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — `last_engine="dockerfile_recipe"` is the post-apply label (vs `engine="dockerfile"` on the recipe itself).
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — `dive_efficiency` is informational, never gate-failing.
- **Source design:**
  - `../final-design.md §Goals` G5 — Express E2E.
- **Existing code:**
  - `tests/fixtures/repos/express-distroless/` — **does not exist yet**; this story creates it.
  - `tests/golden/dockerfile_swap_node20.patch` (from S4-04) — the canonical expected patch.
  - `tests/golden/migration_report_node_e2e.yaml` — **does not exist yet**; this story creates it.
  - `src/codegenie/cli/migrate.py` (S5-05) — the CLI under test.
  - `src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml` (S4-04) — the recipe.
- **External:**
  - Chainguard registry auth: `https://docs.chainguard.dev/chainguard/chainguard-registry/authenticating/` — operator-side setup; this story documents the requirement, S8-04 captures in operator notes.

## Goal

Land `tests/fixtures/repos/express-distroless/` (a Node Express service with `node:20-bullseye-slim` base) and `tests/integration/test_migrate_node_e2e.py` such that running `codegenie migrate <fixture> --target distroless --cve <id>` exits 0 with a Chainguard distroless patch matching the golden file and the five gate assertions all hold.

## Acceptance criteria

- [ ] `tests/fixtures/repos/express-distroless/` exists with: a minimal Node Express app (`package.json`, `package-lock.json`, `index.js`), a single-stage `Dockerfile` with `FROM node:20-bullseye-slim` (or equivalent CVE-bearing slim), and a committed git history.
- [ ] `tests/integration/test_migrate_node_e2e.py` exists with at least one test, `test_migrate_node_express_to_chainguard_distroless_e2e`, that:
  - invokes `codegenie migrate <fixture> --target distroless --cve CVE-2025-XXXX` via Click `CliRunner` or subprocess
  - asserts `exit_code == 0`
  - reads `.codegenie/migration/<run-id>/migration-report.yaml` and validates against `MigrationReport` Pydantic model
  - asserts `last_engine == "dockerfile_recipe"`
  - asserts `grype` CVE delta `≤ 0` (parses from `raw/grype.json`)
  - asserts `shell_invocation_trace.runtime_shell_count == 0` and `confidence == "high"`
  - asserts `dive` reports no `/bin/sh` (parses from `raw/dive.json` for the final layer)
  - asserts the generated patch byte-matches `tests/golden/dockerfile_swap_node20.patch`
  - asserts `migration-report.yaml` byte-matches `tests/golden/migration_report_node_e2e.yaml`
- [ ] `tests/golden/migration_report_node_e2e.yaml` is committed (initially seeded via `pytest --update-golden`).
- [ ] The test marks itself `@pytest.mark.integration` and `@pytest.mark.requires_docker` so it can be skipped in environments without Docker / `dive` / `grype`.
- [ ] The test runs deterministically — five invocations produce byte-identical patches and byte-identical reports modulo `resolved_at` and `chain_head` (those two fields are normalized in the golden comparison).
- [ ] `mypy --strict tests/integration/test_migrate_node_e2e.py` is clean.
- [ ] The fixture's Dockerfile is committed via `git`; the test fixture-loader runs `git worktree add` against a known-clean tree per `DockerfileBaseImageSwapTransform` contract (S4-03 — `WorktreeContaminated` raises on dirty trees).

## Implementation outline

1. Build the `express-distroless/` fixture:
   - `package.json` declaring `"express": "^4.18.0"`
   - `package-lock.json` (committed for determinism)
   - `index.js` — minimal Express app on port 3000
   - `Dockerfile` — single-stage `FROM node:20-bullseye-slim` with `COPY`, `RUN npm ci`, `CMD ["node", "index.js"]`
   - `.gitignore` and an initial commit (the test fixture-loader needs a clean git tree)
2. Add the fixture rows to the distroless catalog (`src/codegenie/catalogs/distroless/cve_image_recommendations.yaml`) — already seeded by S2-06, but verify `node:20-bullseye-slim` → `cgr.dev/chainguard/node:20-distroless` is in the catalog with a pinned digest.
3. Author `tests/integration/test_migrate_node_e2e.py`:
   - Setup: tmp dir copy of the fixture; `git init` if needed.
   - Invoke `codegenie migrate <repo> --target distroless --cve CVE-2025-XXXX` via Click `CliRunner` (preferred — same process, easier debugging) or subprocess (more realistic; matches operator usage).
   - Parse outputs: report YAML, patch, raw artifacts.
   - Run the five assertions.
4. Seed the golden file by running once with `pytest --update-golden`.
5. Verify five-run determinism by running the test five times in a loop — patch and report bytes must match.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/integration/test_migrate_node_e2e.py`.

```python
import json
import yaml
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli.migrate import migrate
from codegenie.graph.state_distroless import MigrationReport


@pytest.mark.integration
@pytest.mark.requires_docker
def test_migrate_node_express_to_chainguard_distroless_e2e(express_fixture: Path) -> None:
    """G5 — Roadmap exit criterion. Express → Chainguard distroless via recipe path."""
    runner = CliRunner()
    result = runner.invoke(
        migrate,
        ["run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"

    # Locate the run artifacts
    migration_dir = next((express_fixture / ".codegenie/migration").iterdir())
    report_path = migration_dir / "migration-report.yaml"
    assert report_path.exists()

    report = MigrationReport.model_validate(yaml.safe_load(report_path.read_text()))

    # Assertion 1 — recipe path
    assert report.last_engine == "dockerfile_recipe"

    # Assertion 2 — grype CVE delta ≤ 0
    grype = json.loads((migration_dir / "raw/grype.json").read_text())
    cve_delta = _cve_delta(pre=grype["pre"], post=grype["post"])
    assert cve_delta <= 0, f"CVE delta {cve_delta} > 0 (regression)"

    # Assertion 3 — strace runtime_shell_count == 0, confidence "high"
    trace = report.signals.shell_invocation_trace
    assert trace.runtime_shell_count == 0
    assert trace.confidence == "high"

    # Assertion 4 — dive reports no /bin/sh in final image layer
    dive = json.loads((migration_dir / "raw/dive.json").read_text())
    final_layer_shells = [
        f for f in dive["final_layer"]["files"]
        if f["path"] in ("/bin/sh", "/bin/bash", "/bin/dash", "/bin/busybox")
    ]
    assert final_layer_shells == [], f"Unexpected shells in final layer: {final_layer_shells}"

    # Assertion 5 — generated patch byte-matches golden
    patch_path = migration_dir / "diff/swap_base_image_single_stage.patch"
    golden_patch = (Path("tests/golden/dockerfile_swap_node20.patch")).read_bytes()
    assert patch_path.read_bytes() == golden_patch, "Generated patch drifted from golden"

    # Assertion 6 — migration report byte-matches golden (after normalizing volatile fields)
    expected = yaml.safe_load((Path("tests/golden/migration_report_node_e2e.yaml")).read_text())
    actual = yaml.safe_load(report_path.read_text())
    _normalize(actual)  # zero out resolved_at, chain_head
    _normalize(expected)
    assert actual == expected, "Migration report drifted from golden"


@pytest.mark.integration
@pytest.mark.requires_docker
def test_migrate_node_e2e_byte_deterministic_across_five_runs(express_fixture: Path) -> None:
    """G14-adjacent — five runs produce byte-identical patches."""
    patches = []
    for _ in range(5):
        _reset_fixture(express_fixture)
        runner = CliRunner()
        runner.invoke(migrate, ["run", str(express_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"])
        migration_dir = next((express_fixture / ".codegenie/migration").iterdir())
        patches.append((migration_dir / "diff/swap_base_image_single_stage.patch").read_bytes())
        _cleanup_migration_dir(express_fixture)
    assert all(p == patches[0] for p in patches), "Non-deterministic patch across runs"
```

Run; confirm fails (likely `FileNotFoundError` on fixture or report). Commit.

### Green — make it pass

Build the fixture; seed the golden via `--update-golden`; run the test. Iterate until green.

### Refactor — clean up

- Add an `express_fixture` pytest fixture (in `tests/conftest.py` or `tests/integration/conftest.py`) that copies the canonical fixture to a tmp dir, runs `git init` + initial commit if needed, and yields the path.
- Add the `_normalize` helper that zeroes out `resolved_at`, `chain_head`, `workflow_id`, and any timestamp-derived fields before golden comparison.
- Tag the test with `@pytest.mark.slow` if the CI runtime exceeds 60 s.
- Cite arch §Scenario 1 in the test docstring.
- Per cross-cutting determinism: the test must not import `random` or `time`; use `datetime.datetime.now()` only for `resolved_at` *and* normalize it out before golden comparison.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/express-distroless/package.json` | Fixture — minimal Express app. |
| `tests/fixtures/repos/express-distroless/package-lock.json` | Fixture — pinned dependencies. |
| `tests/fixtures/repos/express-distroless/index.js` | Fixture — minimal server. |
| `tests/fixtures/repos/express-distroless/Dockerfile` | Fixture — `FROM node:20-bullseye-slim` single-stage. |
| `tests/fixtures/repos/express-distroless/.gitignore` | Standard. |
| `tests/integration/test_migrate_node_e2e.py` | The G5 E2E test. |
| `tests/golden/migration_report_node_e2e.yaml` | Golden migration report. |
| `tests/integration/conftest.py` | `express_fixture` pytest fixture + `_normalize` helper. |

## Out of scope

- **The distroless catalog seed (`cve_image_recommendations.yaml`)** — already shipped by S2-06; this story consumes it.
- **The recipe and golden patch (`swap_base_image_single_stage.yaml` + `dockerfile_swap_node20.patch`)** — already shipped by S4-04; this story consumes them.
- **CLI surface** — shipped by S5-05.
- **Replay-after-SIGKILL test** — owned by S5-08.
- **Cross-task chain-no-collision** — owned by S5-07.
- **Static-Go E2E test** — owned by S6-03.
- **Shell-required HITL E2E** — owned by S6-04.
- **LLM-fallback E2E** — owned by S6-06.
- **Performance canary (cold ≥6/hr; G6/G8)** — owned by S7-03; this story's happy-path runtime is the *baseline* (`tests/perf/baseline.json` is seeded later from here).
- **Multi-arch handling** — deferred to Phase 7.1 (arch §Edge cases #4 with `confidence=low`).

## Notes for the implementer

- **This test is the load-bearing G5 check.** If it's red, the phase ships nothing. Per CLAUDE.md Rule 12 ("Fail loud"), do not weaken assertions to make it pass; instead surface the failure and fix the underlying component. The five gate assertions are *not negotiable*.
- **`cgr.dev` cold pull on CI is a known risk** (arch §Edge cases #16 + §Risks Step 5 #7). Document the operator-side `~/.docker/config.json` requirement in the test docstring; the operator-notes capture is in S8-04. If CI fails with `429 Too Many Requests`, that's not the test — that's the runner setup. Don't add retry logic to mask it.
- **Five-run determinism is a *separate* test** (`test_migrate_node_e2e_byte_deterministic_across_five_runs`) — it asserts patch bytes match across runs, which catches `random` or `time` imports leaking into `graph/` / `recipes/` / `transforms/` (closes G14 at the integration level).
- **The `_normalize` helper zeros out `resolved_at`, `chain_head`, `workflow_id`** before golden comparison — these are volatile, content-addressed, or time-bound and must not be in the golden's byte hash. Document each excluded field in the helper's docstring with the reason.
- **Per `phase-arch-design.md §Edge cases #7`, `RegistryAuthFailed` is the loud failure mode** when `~/.docker/config.json` is missing. The test should surface this clearly — if the CLI exits 11 with `RegistryAuthFailed` in stderr, the test message should be "Chainguard registry auth not configured; see docs/operator-notes.md", not "exit_code != 0".
- **Use `CliRunner` (Click's in-process invocation) over `subprocess`** for the primary test — same process means easier debugging and faster feedback. Add a secondary subprocess-based test if operator-realism matters; the primary G5 assertion can be in-process.
- **The `<run-id>` directory under `.codegenie/migration/` is non-deterministic** (per-CLI invocation). The test must `next(iterdir())` to find it, not hard-code. Per arch §Gap 1, this is by design.
- **Per `phase-arch-design.md §Risks Step 5`**: first end-to-end run will surface latent bugs in tool wrappers / probes. Budget time for fixes in S2-* / S3-* stories that this test exposes. Do **not** weaken assertions to compensate.
- **Per cross-cutting concern in the manifest: fence-CI under `recipes/` / `transforms/` denies `anthropic | chromadb | sentence-transformers`.** This story doesn't add any code under those scopes, but the test relies on those modules being LLM-free; do not paper over a fence-CI failure here by adding a stub.
- **The fixture must be a real git repo** — `DockerfileBaseImageSwapTransform` runs `git worktree add` (S4-03); a non-git fixture raises `WorktreeContaminated`. The `express_fixture` pytest fixture handles `git init` + commit.
