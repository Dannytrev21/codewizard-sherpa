# Story S6-03 — Static-Go E2E + multi-stage recipe coverage

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** L
**Depends on:** S4-05, S5-08
**ADRs honored:** ADR-P7-006 (`Recipe.engine "dockerfile"`), ADR-P7-007 (advisory `dive`), ADR-P7-009 (`DistrolessLedger`), ADR-P7-012 (parallel CLI verbs)

## Context

The S5-06 happy-path E2E migrates a single-stage Node.js Express service to Chainguard distroless — that closes roadmap exit criterion **G5**. It does *not* exercise the multi-stage refactor recipe (`multi_stage_distroless_refactor.yaml`, S4-05), the static-Go build pattern, or the `last_engine == "dockerfile_recipe"` ledger state for non-Node images. This story adds the second canonical E2E: a multi-stage Go service whose build stage produces a static binary (`CGO_ENABLED=0`) and whose runtime stage swaps to `cgr.dev/chainguard/static:latest`. It anchors the multi-stage refactor recipe's first end-to-end exercise, asserts the ledger transitions correctly through the deeper graph path, and pins the static-Go golden patch (`tests/golden/dockerfile_multistage_go.patch`).

The fixture pairs with the Express fixture (S5-06) so the phase ships two recipe-path E2Es covering the two canonical Dockerfile shapes the catalog supports: single-stage swap (Node) and multi-stage refactor (Go).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios ›Scenario 1` — happy-path control flow (S5-06 is single-stage; this story is the multi-stage variant — same control flow, deeper recipe path)
  - `../phase-arch-design.md §Component 4 ›DockerfileRecipeEngine` — multi-stage recipe is in the engine's surface area
  - `../phase-arch-design.md §Component 7 ›build_distroless_loop()` — ledger transitions and `last_engine` field semantics
  - `../phase-arch-design.md §Fixture portfolio ›static-go-distroless` (line 1267) — fixture composition
  - `../phase-arch-design.md §Testing strategy ›Integration tests ›test_migrate_static_go_e2e` (line 1230) — assertion shape
  - `../phase-arch-design.md §Golden files ›dockerfile_multistage_go.patch` (line 1260)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — multi-stage refactor goes through the `engine: "dockerfile"` path
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — Go static binary in distroless image will likely show a positive size delta vs original Alpine build; the dive signal stays advisory
- **Existing code:**
  - `src/codegenie/recipes/catalog/docker/multi_stage_distroless_refactor.yaml` (S4-05) — the recipe under test
  - `src/codegenie/cli/migrate.py` (S5-05) — `codegenie migrate run` is the entry point
  - `src/codegenie/graph/distroless_loop.py` (S5-04) — the graph the E2E exercises
  - `tests/integration/test_migrate_node_e2e.py` (S5-06) — *clone the structure*, adapt to Go
  - `tests/golden/dockerfile_swap_node20.patch` (S4-04) — golden-patch convention to follow
- **Phase 3 prior art (for fixture-bundle posture):**
  - `../../03-vuln-deterministic-recipe/ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — fixture conventions reused
- **External docs (only if directly relevant):**
  - `https://edu.chainguard.dev/chainguard/chainguard-images/reference/static/` — `cgr.dev/chainguard/static` documentation for the runtime stage

## Goal

`tests/integration/test_migrate_static_go_e2e.py` migrates the multi-stage Go fixture to a Chainguard distroless image through the recipe path, the final ledger state has `last_engine == "dockerfile_recipe"`, and the produced `git format-patch` matches `tests/golden/dockerfile_multistage_go.patch` byte-for-byte.

## Acceptance criteria

- [ ] `tests/fixtures/repos/static-go-distroless/` exists with: a minimal `main.go` (a stdlib HTTP `/health` server, ≤ 30 LOC), `go.mod`, multi-stage `Dockerfile` (build stage `golang:1.22-bookworm`, runtime stage `gcr.io/distroless/static-debian12` *or* `alpine:3.19` so the recipe swaps to Chainguard), `.dockerignore`, and a tagged-commit `git`-initialised state (matches Phase 3 fixture-bundle pattern).
- [ ] `tests/integration/test_migrate_static_go_e2e.py` exists and `pytest` runs it green on the reference Linux DinD runner.
- [ ] The test invokes `codegenie migrate run` on the fixture (via `CliRunner` or direct `build_distroless_loop()` invocation per the convention S5-06 set) and asserts:
  - Final `DistrolessLedger.last_engine == "dockerfile_recipe"` (NOT `"phase4_llm"`).
  - The selected recipe id is `"multi_stage_distroless_refactor"` (from S4-05).
  - The `ObjectiveSignals.dive.passed == True` even if `size_ratio_post_pre > 1.0` (advisory — ADR-P7-007).
  - The `ObjectiveSignals.shell_invocation_trace.passed == True` (static Go binary, no shell at runtime).
  - The `migration-report.yaml` is produced under `.codegenie/migration/<run-id>/`.
- [ ] `tests/golden/dockerfile_multistage_go.patch` exists, is updatable via `pytest --update-golden`, and the test asserts byte-equality of the produced patch against it.
- [ ] Five-run byte-determinism: the test runs the migration 5 times in a loop (or via `pytest-repeat`); all five runs produce byte-identical patches.
- [ ] CVE-input contract: the test asserts that running `codegenie migrate run --cve <id>` against the fixture (with an advisory that points to a Go-base-image-stage CVE) produces a patch whose diff touches the runtime stage's `FROM` line, not the build stage's.
- [ ] Workflow ID prefix: the test asserts `state.workflow_id` matches `^wf:distroless:` (per Gap 1 / S5-05).
- [ ] `mypy --strict` clean on the test file (where it imports from `src/codegenie/`).
- [ ] `ruff check`, `ruff format --check` clean on touched files.

## Implementation outline

1. Build the fixture repo at `tests/fixtures/repos/static-go-distroless/`. Init a git repo, commit `main.go`, `go.mod`, `Dockerfile`, `.dockerignore`. Tag a commit `fixture-baseline`. Document the fixture's purpose in a `README.md` inside the fixture dir.
2. Verify locally that S4-05's `multi_stage_distroless_refactor` recipe *matches* the fixture's Dockerfile shape — if it does not, surface a gap to S4-05 rather than coercing the fixture to a recipe.
3. Write the red test `tests/integration/test_migrate_static_go_e2e.py` asserting `last_engine == "dockerfile_recipe"`. Run; observe failure (no fixture, no entry point routing, no recipe match — any of these is a valid red).
4. Materialize the fixture; wire the test invocation through the CLI runner; run; if recipe matches, capture the produced patch and write it to `tests/golden/dockerfile_multistage_go.patch` via `pytest --update-golden`.
5. Add the five-run determinism loop (`for _ in range(5): ...`) and assert all produced patches are byte-identical.
6. Add the CVE-input branch — a small advisory that targets the runtime stage's base image; assert the produced diff touches only the runtime stage's `FROM`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_migrate_static_go_e2e.py`

```python
# tests/integration/test_migrate_static_go_e2e.py
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli.migrate import migrate
from codegenie.graph.state_distroless import DistrolessLedger

FIXTURE = Path(__file__).parent.parent / "fixtures" / "repos" / "static-go-distroless"
GOLDEN = Path(__file__).parent.parent / "golden" / "dockerfile_multistage_go.patch"

def test_migrate_static_go_via_recipe_path(tmp_path, snapshot_runner) -> None:
    # arrange: copy fixture to tmp_path; git-init; HEAD tagged at fixture-baseline
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)

    # act
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                                     "--cve", "CVE-2024-FAKE-GO-RUNTIME"])

    # assert: clean exit, recipe path taken, ledger transitions correct
    assert result.exit_code == 0, result.output
    ledger = DistrolessLedger.model_validate_json(
        (repo / ".codegenie" / "migration" / "checkpoints" / "latest.json").read_text()
    )
    assert ledger.last_engine == "dockerfile_recipe", \
        f"recipe should match; got last_engine={ledger.last_engine}"
    assert ledger.selected_recipe == "multi_stage_distroless_refactor"
    assert ledger.workflow_id.startswith("wf:distroless:")
    assert ledger.last_outcome.signals.dive.passed is True  # advisory — ADR-P7-007
    assert ledger.last_outcome.signals.shell_invocation_trace.passed is True

    # golden patch
    produced = (repo / ".codegenie" / "migration" / "<placeholder>" / "patch.diff").read_bytes()  # actual run-id discovered via ledger
    assert produced == GOLDEN.read_bytes()

def test_migrate_static_go_is_byte_deterministic_five_runs(...): ...  # 5x loop
def test_migrate_static_go_cve_targets_runtime_stage(...): ...        # CVE branch
```

The red is whichever surface is missing — most likely `last_engine == "dockerfile_recipe"` is `"phase4_llm"` (recipe didn't match) or the fixture doesn't exist.

### Green — make it pass

- Materialize the fixture.
- If the recipe match fails, debug the recipe (S4-05) against the fixture's Dockerfile until match holds.
- Run the test once with `--update-golden` to capture the produced patch.
- Commit the fixture + golden + green test.

### Refactor — clean up

- Add the five-run determinism loop; if the patch is non-deterministic, the root cause is in S4-01 (engine canonicalization) or S4-03 (`git format-patch` invocation) — fix at the source, do not paper over with `expected = produced` per-run.
- Add the CVE-targeted assertion using a `tests/fixtures/advisories/cve-2024-fake-go-runtime.yaml` advisory pointing to the runtime stage's base image.
- Document in the fixture's `README.md` what the migration is supposed to do and why.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/static-go-distroless/main.go` | New — minimal HTTP /health server |
| `tests/fixtures/repos/static-go-distroless/go.mod` | New — module declaration |
| `tests/fixtures/repos/static-go-distroless/Dockerfile` | New — multi-stage build with non-distroless runtime stage |
| `tests/fixtures/repos/static-go-distroless/.dockerignore` | New — minimal |
| `tests/fixtures/repos/static-go-distroless/README.md` | New — fixture purpose |
| `tests/fixtures/advisories/cve-2024-fake-go-runtime.yaml` | New — synthetic advisory targeting the runtime stage |
| `tests/integration/test_migrate_static_go_e2e.py` | New — the E2E |
| `tests/golden/dockerfile_multistage_go.patch` | New — golden patch; captured via `pytest --update-golden` |

## Out of scope

- **Building & running the Go binary in real containers**. The E2E uses the recipe path; `buildkit` wrapper runs the build during `validate_in_sandbox` (covered by S5-06's plumbing). This story does not add new sandbox infrastructure.
- **Authoring the multi-stage refactor recipe**. That's S4-05's responsibility; this story exercises it for the first time end-to-end and may surface gaps that go back to S4-05.
- **Strace tracing on the resulting image**. S3-02 / S3-05 own the strace signal; this story consumes their output via the ledger's `ObjectiveSignals`.
- **The `cgr.dev/chainguard/static` cold-pull risk**. Documented in `phase-arch-design.md §Edge cases #16`; mitigation (operator-side `codegenie cache prewarm`) is a deferred ~30 LOC PR.
- **LLM-fallback path coverage**. That's S6-06's E2E.

## Notes for the implementer

- The fixture's runtime stage should start as something **other than** `cgr.dev/chainguard/static` so the recipe has work to do — `gcr.io/distroless/static-debian12` or `alpine:3.19` are both valid starting points. The migration produces a Dockerfile whose runtime stage is `cgr.dev/chainguard/static:latest` (or a tagged variant per `cve_image_recommendations.yaml`).
- Per `phase-arch-design.md §Edge cases #6`, the Go static binary in `chainguard/static` will likely show `size_ratio_post_pre > 1.0` vs an Alpine base — **the dive signal is advisory and must pass**. Assert `dive.passed is True` *unconditionally*; the size ratio is captured in the migration report, not the gate.
- Five-run determinism is the test for ADR-P7-006's idempotence claim. If any run produces a different patch, surface a refactor PR to S4-01 (engine canonicalization). Common offenders: timestamps in patch headers (handled by `git format-patch --no-color --no-stat` + fixed `GIT_AUTHOR_DATE`); whitespace canonicalization order; YAML key ordering in recipe outputs.
- The CVE branch is the load-bearing input contract. If the CVE advisory points to the *build* stage's image, the recipe must rewrite the build stage (or refuse, depending on `cve_image_recommendations.yaml`). The test must clearly target the *runtime* stage so the assertion is unambiguous.
- The `migration-report.yaml` shape is established in S5-06's golden file (`tests/golden/migration_report_node_e2e.yaml`). Use the same shape for the Go report; do not write a new schema.
- Reference Phase 6's E2E test pattern for fixture-copying + git init — do not invent a new harness.
- Update story `Status:` to `Done` when complete.
