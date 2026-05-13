# Story S4-05 — `multi_stage_distroless_refactor` recipe + Go golden patch

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** M
**Depends on:** S4-03
**ADRs honored:** ADR-P7-004 (handrolled-only; multi-stage is *the* recipe `rewrite-docker` cannot do), ADR-P7-006 (`Recipe.engine` Literal extension)

## Context

This story lands the **harder** of the two seed recipes — the multi-stage refactor that converts a Go service from a single-stage build to a two-stage `golang:builder` → `cgr.dev/chainguard/static:nonroot` runtime layout. It is the recipe ADR-P7-004 explicitly cites as the reason for skipping OpenRewrite: `rewrite-docker`'s own docs say multi-stage refactors fall through; the handrolled engine carries the load.

The Go static-binary path is the second of the three E2E flows (S6-03 consumes this recipe), and the harder of the two engine exercises — it requires the engine to *insert* a new stage, not just swap a FROM line, which exercises a different mutation primitive in S4-01. If S4-01's primitives are missing the multi-stage emit, this story will fail loudly and force the primitive back into S4-01's scope.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›4. DockerfileRecipeEngine` — multi-stage emit must round-trip safely; otherwise recipe miss.
  - `../phase-arch-design.md §Component design ›5. DockerfileBaseImageSwapTransform` — same transform path as single-stage; engine routes by recipe shape.
  - `../phase-arch-design.md §Testing strategy ›Golden files` — `dockerfile_multistage_go.patch`.
  - `../phase-arch-design.md §Edge cases` row 10 — BuildKit heredoc + multi-stage interactions.
- **Phase ADRs:**
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — explicitly names multi-stage as the recipe `rewrite-docker` can't do.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 18` — names multi-stage as the load-bearing argument against OpenRewrite.
- **Existing code:**
  - `src/codegenie/recipes/engines/dockerfile_engine.py` (S4-01) — the engine must expose a multi-stage emit primitive; if it doesn't, surface back to S4-01.
  - `src/codegenie/recipes/catalog/docker/swap_base_image_single_stage.yaml` (S4-04) — companion recipe; mirror YAML shape and field ordering.

## Goal

`src/codegenie/recipes/catalog/docker/multi_stage_distroless_refactor.yaml` exists with `engine: "dockerfile"`, matches a single-stage Go Dockerfile (`FROM golang:1.<minor>` with `go build` in a single layer), and produces a patch that converts it to a two-stage `golang:1.<minor> AS builder` → `cgr.dev/chainguard/static:nonroot` layout — byte-identical across five consecutive runs, byte-exact against `tests/golden/dockerfile_multistage_go.patch`.

## Acceptance criteria

- [ ] `src/codegenie/recipes/catalog/docker/multi_stage_distroless_refactor.yaml` exists with `engine: "dockerfile"`, `applies_to_tasks: ["distroless_migration"]`, and match rules covering single-stage Go Dockerfiles using `golang:1.<minor>(-<variant>)` base images.
- [ ] The recipe deserializes through `Recipe.model_validate` without error.
- [ ] `tests/fixtures/repos/static-go-distroless-min/` exists with a minimal Go fixture: `Dockerfile` (single-stage `FROM golang:1.22`), `main.go` (one-liner `package main; func main() {}`), `go.mod` (one line `module example.com/m`).
- [ ] `tests/golden/dockerfile_multistage_go.patch` exists; contains exactly the patch bytes the engine + transform produce on the minimal Go fixture; the golden contains both the `FROM golang:1.22 AS builder` insertion *and* the `FROM cgr.dev/chainguard/static:nonroot` runtime stage *and* the `COPY --from=builder` line.
- [ ] `pytest tests/integration/test_multi_stage_distroless_refactor_recipe.py` is green: applies the recipe → asserts `patch_bytes == golden.read_bytes()`.
- [ ] `pytest --update-golden tests/integration/test_multi_stage_distroless_refactor_recipe.py` regenerates the golden cleanly; running it twice produces no diff.
- [ ] Five-run byte-determinism: a test loops 5 times applying the recipe and asserts the produced patch is byte-identical across all runs.
- [ ] Recipe matches the minimal Go fixture; recipe does *not* match the Node 20 single-stage fixture from S4-04 (the recipes route to disjoint match contexts).
- [ ] Engine round-trip safety holds on the *output* of this recipe: `parse(serialize(parse(patched_dockerfile))) == parse(patched_dockerfile)`. (If the engine emits a non-round-trippable multi-stage Dockerfile, this story fails and feeds back to S4-01's engine primitives.)
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the test files.

## Implementation outline

1. Read `swap_base_image_single_stage.yaml` (S4-04); copy field ordering and front-matter convention.
2. Author `multi_stage_distroless_refactor.yaml`:
   - `id: multi_stage_distroless_refactor`
   - `engine: dockerfile`
   - `match_rules`: regex for `FROM golang:1.<minor>` + presence of `go build` in a `RUN` line (single-stage signature).
   - `transforms`: a `convert_to_multi_stage` directive naming the builder stage's reused-as base + the runtime stage's target image lookup key.
3. Confirm the engine (S4-01) exposes the `convert_to_multi_stage` primitive. If it doesn't, file the gap back to S4-01 and stop — do not add the primitive in this story (out of scope per Step 4's separation).
4. Create the minimal Go fixture under `tests/fixtures/repos/static-go-distroless-min/`.
5. Author `tests/integration/test_multi_stage_distroless_refactor_recipe.py` (parallel to S4-04's structure).
6. Run `pytest --update-golden ...` to generate `tests/golden/dockerfile_multistage_go.patch`; commit.
7. Re-run without `--update-golden`; confirm all tests pass.
8. Confirm the round-trip-on-output test holds: serialize the patched Dockerfile, re-parse, assert AST equality.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_multi_stage_distroless_refactor_recipe.py`

```python
# tests/integration/test_multi_stage_distroless_refactor_recipe.py
GOLDEN = Path("tests/golden/dockerfile_multistage_go.patch")
RECIPE = Path("src/codegenie/recipes/catalog/docker/multi_stage_distroless_refactor.yaml")
FIXTURE = Path("tests/fixtures/repos/static-go-distroless-min/")

def test_recipe_yaml_deserializes_via_pydantic():
    text = RECIPE.read_text(encoding="utf-8")
    recipe = Recipe.model_validate(yaml.safe_load(text))
    assert recipe.engine == "dockerfile"
    assert recipe.id == "multi_stage_distroless_refactor"


def test_recipe_produces_multistage_golden(tmp_repo_from_fixture):
    # arrange
    repo = tmp_repo_from_fixture(FIXTURE)
    transform = DockerfileBaseImageSwapTransform()
    input_ = TransformInput(repo_path=repo, recipe_path=RECIPE,
                            target_image="cgr.dev/chainguard/static:nonroot@sha256:" + "b" * 64,
                            task_type="distroless_migration", run_id="multistage")

    # act
    output = transform.run(input_)

    # assert
    assert output.exit_code == 0
    assert output.patch_bytes == GOLDEN.read_bytes()
    # additional: patch contains the builder + runtime stages
    assert b"+FROM golang:1.22 AS builder" in output.patch_bytes
    assert b"+FROM cgr.dev/chainguard/static:nonroot" in output.patch_bytes
    assert b"+COPY --from=builder" in output.patch_bytes


def test_recipe_round_trip_on_output(tmp_repo_from_fixture):
    repo = tmp_repo_from_fixture(FIXTURE)
    transform = DockerfileBaseImageSwapTransform()
    output = transform.run(input_for(repo))
    # apply the patch, re-parse the result, assert AST round-trips
    patched_dockerfile = apply_patch_in_memory(FIXTURE / "Dockerfile", output.patch_bytes)
    ast1 = dockerfile_parse.parse(patched_dockerfile)
    ast2 = dockerfile_parse.parse(dockerfile_parse.serialize(ast1))
    assert ast1 == ast2


def test_recipe_five_run_byte_determinism(tmp_repo_from_fixture):
    repo = tmp_repo_from_fixture(FIXTURE)
    runs = [DockerfileBaseImageSwapTransform().run(input_for(repo)).patch_bytes for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_recipe_does_not_match_single_stage_node_fixture():
    matcher = RecipeMatcher.from_catalog([RECIPE])
    node_fixture = Path("tests/fixtures/repos/express-distroless-min/Dockerfile")
    assert not matcher.match(node_fixture.read_text())
```

Run. Tests fail because the YAML, fixture, and golden don't exist. Commit as marker.

### Green — make it pass

- Write `multi_stage_distroless_refactor.yaml`.
- Write `tests/fixtures/repos/static-go-distroless-min/{Dockerfile,main.go,go.mod}`.
- Run `pytest --update-golden tests/integration/test_multi_stage_distroless_refactor_recipe.py`; commit `tests/golden/dockerfile_multistage_go.patch`.
- Re-run; tests pass.

If the engine's `convert_to_multi_stage` primitive is missing or broken on the round-trip-on-output test: stop, file a gap back to S4-01, do not patch around it here.

### Refactor — clean up

- Re-read the golden patch by hand. The multi-stage refactor is the hardest engine-level test — verify the *human-readable* diff produces a Dockerfile that builds. (Don't actually `docker buildx build` here; that's S5-06's / S6-03's job. But read the diff and confirm it's syntactically Dockerfile-valid and semantically a static-binary copy.)
- Confirm the patch's COPY line preserves the binary name from the Go fixture — the engine should not invent file names.
- Confirm the runtime stage's `USER nonroot` or equivalent matches Chainguard's `static:nonroot` convention.
- Document in the YAML's top comment: ADR-P7-004 (handrolled-only — this recipe is *the* reason), S4-01 (engine), S6-03 (E2E consumer).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/catalog/docker/multi_stage_distroless_refactor.yaml` | New file — the seed multi-stage refactor recipe. |
| `tests/fixtures/repos/static-go-distroless-min/Dockerfile` | New minimal Go fixture for this story. |
| `tests/fixtures/repos/static-go-distroless-min/main.go` | New minimal Go fixture (`package main; func main() {}`). |
| `tests/fixtures/repos/static-go-distroless-min/go.mod` | New minimal Go fixture (one-line module path). |
| `tests/integration/test_multi_stage_distroless_refactor_recipe.py` | New test — anchors TDD red phase + round-trip-on-output + five-run determinism. |
| `tests/golden/dockerfile_multistage_go.patch` | New golden patch; generated via `pytest --update-golden`. |

## Out of scope

- **Engine primitive `convert_to_multi_stage`.** — must exist in the engine from S4-01; if it doesn't, file back to S4-01.
- **`buildx build` of the patched Go Dockerfile.** — handled by story S6-03 (`tests/integration/test_migrate_static_go_e2e.py`).
- **Full static-Go fixture (`tests/fixtures/repos/static-go-distroless/`).** — handled by story S6-03; this story uses a *minimal* fixture (`-min` suffix).
- **`grype` / `dive` validation.** — S6-03.
- **Adversarial multi-stage corpus (≥30 fixtures).** — story S6-01.
- **Heredoc + Alpine→glibc fixtures.** — story S6-05.

## Notes for the implementer

- The multi-stage refactor is *the* recipe ADR-P7-004 cites as the OpenRewrite deferral rationale. If you find yourself wanting to add a more general AST-rewrite primitive to the engine to make this recipe work, stop and re-read ADR-P7-004 — handrolled means the primitives are *specific*, not *general*.
- Read `CLAUDE.md` Rule 8 first. The engine's primitive list is exposed in S4-01's module; if `convert_to_multi_stage` isn't there, file a gap. Don't add it ad-hoc here.
- The Go fixture must be `git init`-ed with one initial commit so `git worktree add` works (same constraint as S4-04).
- The `target_image` for the runtime stage is `cgr.dev/chainguard/static:nonroot` — *not* a language-specific image. Chainguard's `static` is the canonical target for statically-linked Go binaries. Verify against the catalog (S2-06) that this image is in the row set; if not, the recipe will catalog-miss at runtime.
- The golden patch is *much* larger than S4-04's — multi-stage produces a multi-hunk diff. That's expected. Don't try to minimize it manually; let the engine produce it and accept whatever it emits, then verify by hand.
- The "does not match single-stage Node" test prevents recipe leakage in the other direction — if `multi_stage_distroless_refactor` accidentally matches Node fixtures, S5-06's Express E2E will route to the wrong recipe. Make the match rules tight.
- Per `CLAUDE.md` Rule 7, if S4-04's recipe YAML uses one field-ordering convention and Phase 3's existing recipes use another, pick one (the more recent — i.e., Phase 7's S4-04) and flag the conflict in the PR description. Don't average them.
- Per `CLAUDE.md` Rule 12, the round-trip-on-output test must *actually fail* if the engine emits a non-round-trippable multi-stage Dockerfile — not silently pass because `dockerfile_parse.parse` is permissive. If the test passes on a known-broken input, the round-trip assertion is too lax.
