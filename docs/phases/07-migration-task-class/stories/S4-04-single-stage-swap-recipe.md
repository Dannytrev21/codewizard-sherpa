# Story S4-04 — `swap_base_image_single_stage` recipe + Node 20 golden patch

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** S
**Depends on:** S4-03
**ADRs honored:** ADR-P7-004 (handrolled-only), ADR-P7-006 (`Recipe.engine` Literal extension)

## Context

This story lands the **first** seed recipe — a Dockerfile-shaped recipe that matches a single-stage Node 20 Dockerfile and produces the Chainguard distroless swap. It is the artifact the Express E2E test (S5-06) consumes for its golden-patch comparison and is the smaller, cleaner of Phase 7's two seed recipes (the multi-stage Go refactor lands in S4-05).

The recipe is a YAML file consumed by Phase 3's `RecipeMatcher` and dispatched to `DockerfileRecipeEngine` via the `engine: "dockerfile"` value extended into `Recipe.engine` in S1-05. The golden patch is the byte-exact output the engine + transform pair must produce; if the engine drifts, the golden mismatch fires loudly. The five-run determinism criterion is the operational evidence that the engine has no `random`/`time`/env-dependent ordering.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›4. DockerfileRecipeEngine` — engine consumes the recipe.
  - `../phase-arch-design.md §Component design ›5. DockerfileBaseImageSwapTransform` — transform invokes the engine on this recipe.
  - `../phase-arch-design.md §Testing strategy ›Golden files` — `dockerfile_swap_node20.patch`; updatable via `pytest --update-golden`.
  - `../phase-arch-design.md §Scenarios ›Scenario 1` — happy path uses this recipe.
- **Phase ADRs:**
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — `engine: "dockerfile"`, not `engine: "openrewrite_docker"`.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — the `engine` value must match the Literal extended in S1-05.
- **Existing code:**
  - `src/codegenie/recipes/catalog/` — Phase 3's recipe YAML examples; copy the front-matter shape.
  - `src/codegenie/recipes/contract.py` — `Recipe` Pydantic model; the YAML must deserialize through it.
  - `src/codegenie/recipes/engines/dockerfile_engine.py` — the engine landed in S4-01; the recipe's `match_rules` and `transforms` are what the engine consumes.
  - `src/codegenie/transforms/dockerfile_base_image_swap.py` — landed in S4-03; the recipe routes through this transform.

## Goal

`src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml` exists with `engine: "dockerfile"`, deserializes through Phase 3's `Recipe` Pydantic model, matches a minimal Node 20 single-stage Dockerfile, and produces a `git format-patch` whose bytes match `tests/golden/dockerfile_swap_node20.patch` exactly — five times in a row, byte-identical.

## Acceptance criteria

- [ ] `src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml` exists; declares `engine: "dockerfile"`, `applies_to_tasks: ["distroless_migration"]`, and match rules covering Node 20 single-stage (`FROM node:<version>(-<variant>)` for `<version>` in `{18, 20}` and `<variant>` in `{bullseye-slim, bookworm-slim, alpine, ""}`).
- [ ] The recipe deserializes through `Recipe.model_validate` without error.
- [ ] `tests/golden/dockerfile_swap_node20.patch` exists; contains exactly the patch bytes the engine + transform produce on the `tests/fixtures/repos/express-distroless-min/` fixture (a *minimal* Express fixture for this story — the full Express fixture lands in S5-06).
- [ ] `pytest tests/integration/test_swap_base_image_single_stage_recipe.py` is green: applies the recipe → asserts `patch_bytes == golden.read_bytes()`.
- [ ] `pytest --update-golden tests/integration/test_swap_base_image_single_stage_recipe.py` regenerates the golden cleanly; running it twice produces no diff.
- [ ] Five-run byte-determinism: a test loops 5 times applying the recipe and asserts the produced patch is byte-identical across all runs. (Same code path the engine's S4-01 determinism test exercises, but at the recipe boundary, not the engine boundary.)
- [ ] Recipe matches the minimal Node 20 fixture; recipe does *not* match a multi-stage Go fixture (the S4-05 recipe will).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the touched Python files (the YAML files pass via the `Recipe.model_validate` test).

## Implementation outline

1. Read Phase 3's existing recipe YAMLs under `src/codegenie/recipes/catalog/` (e.g., `npm_*.yaml`). Mirror their structure, front-matter shape, and field ordering.
2. Author `swap_base_image_single_stage.yaml`:
   - `id: swap_base_image_single_stage`
   - `engine: dockerfile`
   - `applies_to_tasks: [distroless_migration]`
   - `applies_to_languages: ["*"]`
   - `match_rules`: regex or structured match on `FROM node:...` images (be specific about Node 20).
   - `transforms`: a single `replace_from` directive naming the canonical target image lookup key.
3. Add a minimal Express fixture: `tests/fixtures/repos/express-distroless-min/Dockerfile` (one `FROM node:20.10.0-bullseye-slim` + one `CMD`) — *minimal*; the full S5-06 fixture is out of scope.
4. Generate the golden patch the first time via the engine + transform; commit it.
5. Add `tests/integration/test_swap_base_image_single_stage_recipe.py`: golden-file test + recipe-loads-via-Pydantic test + five-run determinism loop.
6. Wire `--update-golden` flag handling (Phase 3 already has the helper; reuse via `pytest_plugins`).
7. Confirm `mypy --strict` passes on the test file; the YAML doesn't need typing, only the Pydantic validation step does.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_swap_base_image_single_stage_recipe.py`

```python
# tests/integration/test_swap_base_image_single_stage_recipe.py
GOLDEN = Path("tests/golden/dockerfile_swap_node20.patch")
RECIPE = Path("src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml")
FIXTURE = Path("tests/fixtures/repos/express-distroless-min/")

def test_recipe_yaml_deserializes_via_pydantic():
    text = RECIPE.read_text(encoding="utf-8")
    recipe = Recipe.model_validate(yaml.safe_load(text))
    assert recipe.engine == "dockerfile"
    assert "distroless_migration" in recipe.applies_to_tasks


def test_recipe_produces_golden_patch(tmp_repo_from_fixture):
    # arrange: fresh git repo seeded from the fixture
    repo = tmp_repo_from_fixture(FIXTURE)
    transform = DockerfileBaseImageSwapTransform()
    input_ = TransformInput(repo_path=repo, recipe_path=RECIPE,
                            target_image="cgr.dev/chainguard/node:20-distroless@sha256:"+"a"*64,
                            task_type="distroless_migration", run_id="single-stage")

    # act
    output = transform.run(input_)

    # assert: byte-exact match
    assert output.exit_code == 0
    assert output.patch_bytes == GOLDEN.read_bytes()


def test_recipe_five_run_byte_determinism(tmp_repo_from_fixture):
    repo = tmp_repo_from_fixture(FIXTURE)
    transform = DockerfileBaseImageSwapTransform()
    input_ = TransformInput(repo_path=repo, recipe_path=RECIPE, target_image="cgr.dev/...", task_type="distroless_migration", run_id="d")
    runs = [transform.run(input_).patch_bytes for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_recipe_does_not_match_multistage_fixture():
    matcher = RecipeMatcher.from_catalog([RECIPE])
    multistage = Path("tests/fixtures/dockerfiles/property/multi_stage.Dockerfile")
    assert not matcher.match(multistage.read_text())
```

Run. The first two fail because the YAML doesn't exist. Commit as marker.

### Green — make it pass

- Write the YAML.
- Write the minimal Express fixture.
- Run `pytest --update-golden tests/integration/test_swap_base_image_single_stage_recipe.py`; commit the produced `tests/golden/dockerfile_swap_node20.patch`.
- Re-run without `--update-golden`; all four tests pass.

### Refactor — clean up

- Verify the YAML field ordering matches Phase 3's convention (alphabetical, or whatever the catalog uses — see Rule 11).
- Add a short comment header to the YAML naming ADR-P7-006 and pointing at S4-01 for the engine.
- Document the `tmp_repo_from_fixture` fixture in `tests/conftest.py` if you added it; reuse if Phase 3 already exposes an equivalent.
- Confirm the golden patch contains *only* the relevant FROM-line change — if there's extra noise (e.g., a `whitespace: trailing` re-flow), the engine's canonicalization is doing more than byte-only; revisit S4-01.
- Confirm `tests/golden/dockerfile_swap_node20.patch` has LF line endings (no CRLF) and no trailing whitespace — the engine's canonicalization should guarantee this; assert it via a one-line test.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml` | New file — the seed single-stage recipe. |
| `src/codegenie/recipes/catalog/docker/__init__.py` or marker | If the catalog scans by directory, ensure the new subdir is picked up. |
| `tests/fixtures/repos/express-distroless-min/Dockerfile` | New minimal Express fixture for this story. |
| `tests/fixtures/repos/express-distroless-min/package.json` | New minimal Express fixture (one line — empty `{}` or a `name` field). |
| `tests/integration/test_swap_base_image_single_stage_recipe.py` | New test — anchors TDD red phase + five-run determinism. |
| `tests/golden/dockerfile_swap_node20.patch` | New golden patch; generated via `pytest --update-golden`. |

## Out of scope

- **Multi-stage Go recipe.** — handled by story S4-05.
- **Full Express fixture + Node E2E test.** — handled by story S5-06 (this story uses a *minimal* Express fixture; the full one belongs to the E2E story).
- **`buildkit build` validation against the patched Dockerfile.** — handled by Phase 5's `validate_in_sandbox` in story S5-06.
- **`grype` CVE delta verification.** — S5-06.
- **`dive` no-/bin/sh assertion on the produced image.** — S5-06.
- **Recipe-miss → RAG → LLM fallback test.** — story S6-06.
- **Distroless RAG seed corpus.** — story S6-07.

## Notes for the implementer

- The `--update-golden` flag is repository convention; if Phase 3 hasn't shipped it yet, surface that as an open question — don't roll your own. The conftest hook lives at the repo root.
- A golden patch is byte-exact. CRLF line endings, BOM, trailing whitespace, `git format-patch`'s "From " header date — every byte matters. The engine's deterministic-`format-patch` helper (S4-01) handles all four; if a fresh checkout's golden differs from CI's, the helper has a bug, not the recipe.
- The minimal fixture must be `git init`-ed and have one initial commit so `git worktree add` works. The `tmp_repo_from_fixture` helper should do this — verify before claiming green.
- The "does not match multi-stage" test prevents recipe leakage — if `swap_base_image_single_stage` accidentally matches multi-stage Dockerfiles, S4-05's multi-stage recipe will never be selected. Phase 3's `RecipeMatcher` picks the *first* match; ordering matters.
- Five-run determinism is *not* "five runs of the engine" — it's five runs of the *transform* (which spawns the engine, the worktree, and `git format-patch`). The whole pipeline must be deterministic, not just the engine internals.
- The `target_image` digest in the test (`sha256:aaaa...`) is fictional; that's fine — the recipe + engine don't `docker pull` it. Real digests come from `base_catalog.json` at runtime (S5-02's `resolve_target_image` node), and the golden patch reflects whatever `target_image` the test passes in. Pick a stable test value and document it in the test docstring.
- Per `CLAUDE.md` Rule 9, the five-run determinism test's WHY is: "if it fails, two warm CI runs of the same E2E test produce different patches, the golden compare fails on the second run, and operators see flaky CI for no reason." State that in the test docstring.
