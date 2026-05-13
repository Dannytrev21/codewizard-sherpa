# Story S6-05 — Heredoc + Alpine→glibc fixtures

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S6-04
**ADRs honored:** ADR-P7-006 (`Recipe.engine "dockerfile"`), ADR-P7-007 (advisory `dive`), ADR-P7-009 (`DistrolessLedger`)

## Context

Two specific edge cases need fixture exercise before S6-06 wires the LLM fallback E2E: the **BuildKit heredoc** input that `dockerfile-parse` partially parses (`parser_skipped_lines > 0`), which deterministically forces a recipe miss; and the **legitimate Alpine→glibc migration** where the post-migration image grows because Chainguard's glibc runtime is larger than Alpine's musl runtime — the dive signal must stay advisory (`passed=True`) and the gate must not auto-fail (this is the critic sec.3 finding closed by ADR-P7-007).

The heredoc fixture is the bridge into S6-06: it's the deterministic "recipe miss" trigger the LLM-fallback E2E consumes. The Alpine→glibc fixture is the safety belt for advisory-only dive — if dive's size ratio ever creeps into the strict-AND, this fixture's test fires red.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #6` — Alpine→glibc legitimate growth; dive advisory only
  - `../phase-arch-design.md §Edge cases #10` — BuildKit heredoc → `parser_skipped_lines > 0` → recipe miss
  - `../phase-arch-design.md §Component 4 ›DockerfileRecipeEngine ›Recipe miss path` — `parser_skipped_lines > 0` forces RAG/LLM path
  - `../phase-arch-design.md §Fixture portfolio ›heredoc-buildkit-distroless` (line 1269)
  - `../phase-arch-design.md §Fixture portfolio ›alpine-to-glibc-distroless` (line 1270)
  - `../phase-arch-design.md §Component 8 ›Signal collectors ›DiveSignal` — `passed=True` always (advisory)
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — `test_dive_signal.py` asserts `passed=True` even when `size_ratio_post_pre > 1.0`; this story's E2E counterpart asserts the same at the gate level
- **Phase ADRs:**
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — this story is the integration-level enforcement of that ADR
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — recipe miss path
- **Existing code:**
  - `src/codegenie/tools/dockerfile_parse.py` (S2-01) — emits `parser_skipped_lines`
  - `src/codegenie/probes/base_image.py` (S3-01) — sets `confidence=medium` when `parser_skipped_lines > 0`
  - `src/codegenie/graph/nodes/distroless/select_recipe.py` (S5-02) — treats `parser_skipped_lines > 0` as a recipe miss
  - `src/codegenie/sandbox/signals/dive.py` (S3-04) — advisory collector
  - `tests/integration/test_migrate_node_e2e.py` (S5-06) — clone-then-adapt for both fixtures

## Goal

Two new fixture repos exist under `tests/fixtures/repos/` — one whose BuildKit heredoc forces a recipe miss (asserted at `parser_skipped_lines > 0`, `RecipeSelector` route `"miss"`), and one whose Alpine→glibc Chainguard migration grows the image size (asserted at `size_ratio_post_pre > 1.0`, `dive.passed=True`, gate overall passes).

## Acceptance criteria

- [ ] `tests/fixtures/repos/heredoc-buildkit-distroless/` exists with: a `Dockerfile` whose `RUN` block uses BuildKit heredoc syntax (`RUN <<EOF ... EOF`), a minimal app stub (Node, Python, or static `echo` server), `.dockerignore`, git-initialised state, `README.md` documenting the fixture's `parser_skipped_lines > 0` purpose.
- [ ] `tests/fixtures/repos/alpine-to-glibc-distroless/` exists with: a `Dockerfile` whose base is `node:20-alpine` (or `python:3.12-alpine`), a minimal app whose binary actually requires glibc (use `node` itself — switching to Chainguard's glibc node image is the canonical move), `.dockerignore`, git-initialised state, `README.md` documenting Risk #6 / critic sec.3 mitigation.
- [ ] `tests/integration/test_heredoc_forces_recipe_miss.py` exists. Runs the heredoc fixture through `codegenie migrate run` and asserts:
  - `DockerfileInventory.parser_skipped_lines > 0` after the gather phase.
  - `RecipeSelection.matched is False` with `reason == "parser_skipped_lines_nonzero"` (or whatever reason code S5-02 emits — match the source).
  - `last_engine != "dockerfile_recipe"` (the loop took the miss path; further routing — RAG / LLM — is out of scope, the test stops here OR mocks the downstream nodes to assert routing).
  - `BaseImageProbe.confidence == "medium"`.
- [ ] `tests/integration/test_alpine_glibc_dive_advisory.py` exists. Runs the Alpine→glibc fixture through `codegenie migrate run` and asserts:
  - The recipe applies successfully (`last_engine == "dockerfile_recipe"`).
  - `ObjectiveSignals.dive.size_ratio_post_pre > 1.0` (legitimate growth).
  - `ObjectiveSignals.dive.passed is True` (advisory; ADR-P7-007).
  - The overall gate `last_outcome.passed is True` (strict-AND does not fail on the dive growth).
  - The `migration-report.yaml` records the size delta in a `size_delta_advisory` section for human review.
- [ ] Both tests are green on the reference Linux DinD runner.
- [ ] Both fixtures include a `README.md` explaining *why* the fixture exists; this is the only protection against a later refactor deleting them as "redundant".
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on touched test files.

## Implementation outline

1. **Heredoc fixture.** Craft the smallest possible BuildKit heredoc that `dockerfile-parse` partially parses. Pattern is `RUN <<EOF\n echo a\n echo b\nEOF`. Confirm against S2-01's parser locally: `dockerfile_parse.parse_strict(fixture_bytes).parser_skipped_lines > 0`. If S2-01 *rejects* the heredoc outright rather than partial-parsing it, escalate — the contract is partial-parse → `parser_skipped_lines` is incremented; outright rejection contradicts the design.
2. **Heredoc test.** Write the red test asserting recipe miss. If the migration runs all the way to LLM fallback, that's fine for this story — just assert the **miss** branch was taken; do not assert the LLM downstream path (that's S6-06).
3. **Alpine→glibc fixture.** Use `node:20-alpine` as the base. The Express app is similar to S5-06's. Confirm locally that swapping to `cgr.dev/chainguard/node:20` produces a runnable image (Chainguard's `node` is glibc).
4. **Alpine→glibc test.** Run the migration. Assert dive shows growth, signal still passes, gate passes overall. This test depends on **`cgr.dev/chainguard/node`** being pullable — share the operator-side credential note with S5-06's fixture.
5. Run both tests; commit fixtures + tests.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/integration/test_heredoc_forces_recipe_miss.py
from pathlib import Path
from click.testing import CliRunner
from codegenie.cli.migrate import migrate
from codegenie.graph.state_distroless import DistrolessLedger

FIXTURE = Path(__file__).parent.parent / "fixtures" / "repos" / "heredoc-buildkit-distroless"

def test_heredoc_dockerfile_produces_parser_skipped_lines_and_recipe_miss(tmp_path, snapshot_runner):
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                                     "--cve", "CVE-2024-FAKE", "--stop-after", "select_recipe"])
    # The --stop-after flag is per S5-05's debug surface, if available; otherwise read the ledger at any pause point.

    ledger = _read_latest_ledger(repo)
    assert ledger.gather.dockerfile_inventory.parser_skipped_lines > 0
    assert ledger.recipe_selection.matched is False
    assert ledger.recipe_selection.reason == "parser_skipped_lines_nonzero"
    assert ledger.base_image_signal.confidence == "medium"
```

```python
# tests/integration/test_alpine_glibc_dive_advisory.py
def test_alpine_to_glibc_growth_does_not_fail_gate(tmp_path, snapshot_runner):
    repo = snapshot_runner.copy_fixture(FIXTURE, tmp_path)
    runner = CliRunner()
    result = runner.invoke(migrate, ["run", str(repo), "--target", "distroless",
                                     "--cve", "CVE-2024-FAKE"])
    assert result.exit_code == 0, result.output

    ledger = _read_latest_ledger(repo)
    assert ledger.last_engine == "dockerfile_recipe"
    sig = ledger.last_outcome.signals.dive
    assert sig.size_ratio_post_pre > 1.0, "fixture is designed to grow legitimately"
    assert sig.passed is True, "ADR-P7-007: dive is advisory; growth must not fail the gate"
    assert ledger.last_outcome.passed is True
```

Red causes: fixtures don't exist; `--stop-after` flag may not exist (use `interrupt_before` or read interim ledger checkpoints instead); `parser_skipped_lines_nonzero` reason string may differ from S5-02's literal — match the source.

### Green — make it pass

- Materialize both fixtures.
- Confirm the heredoc actually produces `parser_skipped_lines > 0` against S2-01 — if not, the heredoc shape is wrong (try `RUN --mount=type=cache <<EOF ...` instead of plain `<<EOF`).
- Run the migrate flow and capture the actual reason codes; align the test assertions.

### Refactor — clean up

- Add a defensive assertion in the heredoc test that S5-02 took the **miss** route on the `route_after_select_recipe` edge (read `ledger.audit_chain` for the `decision:route_after_select_recipe→miss` entry).
- Add an assertion in the Alpine→glibc test that `migration-report.yaml.size_delta_advisory.original_size_mb < final_size_mb` — the *direction* of growth is the test's intent.
- Reuse `snapshot_runner` and `_read_latest_ledger` helpers introduced by S5-06.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/heredoc-buildkit-distroless/Dockerfile` | New — BuildKit heredoc; partial-parse trigger |
| `tests/fixtures/repos/heredoc-buildkit-distroless/server.js` | New — minimal app |
| `tests/fixtures/repos/heredoc-buildkit-distroless/package.json` | New |
| `tests/fixtures/repos/heredoc-buildkit-distroless/.dockerignore` | New |
| `tests/fixtures/repos/heredoc-buildkit-distroless/README.md` | New — purpose: `parser_skipped_lines > 0` |
| `tests/fixtures/repos/alpine-to-glibc-distroless/Dockerfile` | New — `FROM node:20-alpine` start state |
| `tests/fixtures/repos/alpine-to-glibc-distroless/server.js` | New |
| `tests/fixtures/repos/alpine-to-glibc-distroless/package.json` | New |
| `tests/fixtures/repos/alpine-to-glibc-distroless/.dockerignore` | New |
| `tests/fixtures/repos/alpine-to-glibc-distroless/README.md` | New — Risk #6 / critic sec.3 mitigation |
| `tests/integration/test_heredoc_forces_recipe_miss.py` | New |
| `tests/integration/test_alpine_glibc_dive_advisory.py` | New |

## Out of scope

- **LLM-fallback downstream of the heredoc miss.** The heredoc fixture is consumed by S6-06; this story asserts the miss happens, S6-06 asserts the LLM path completes.
- **A `dive` schema-drift adversarial.** Handled by `tests/unit/sandbox/signals/test_dive_signal.py` (S3-04) and `phase-arch-design.md §Edge cases #13` — out of this story.
- **Variant heredoc shapes** (`<<-EOF` indented, `<<\\EOF` quoted, `--mount=type=cache <<EOF`). One canonical heredoc fixture here suffices; S6-01's adversarial corpus may include variants.
- **Multi-stage Alpine→glibc** — single-stage suffices for the dive-growth assertion. Multi-stage is covered by S6-03.

## Notes for the implementer

- The heredoc fixture is the load-bearing trigger for S6-06's LLM-fallback E2E. If the assertion in this story passes but S6-06's downstream depends on a *different* reason code, fix the contract at S5-02 / `RecipeSelection.reason` — do not branch.
- ADR-P7-007's claim "dive growth never fails the gate" is the load-bearing safety property for legitimate-growth migrations. **Test the negative.** If the gate fails this fixture, the entire phase ships an unsafe gate that auto-rejects valid distroless migrations.
- For the Alpine→glibc fixture, document the `cgr.dev` cold-pull risk in the fixture's `README.md` — `phase-arch-design.md §Edge cases #16`. On a fresh CI runner the pull is ~150–300 MB and the test will be slow; that's expected.
- The heredoc test must not require `--stop-after` if that flag doesn't exist. Read the interim ledger from the checkpoint sqlite or assert post-hoc on the run-id directory's state. S5-05's CLI surface is the contract; use what's there.
- Reuse the `snapshot_runner` fixture pattern S5-06 established — do not re-implement fixture copying.
- The Alpine→glibc test's CVE input must be one that targets the *base image*, otherwise the recipe won't fire. Use a synthetic advisory aligned with the fixture's setup.
- Update story `Status:` to `Done` when complete.
