# Story S4-01 — `DockerfileRecipeEngine` ABC implementation + determinism

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** M
**Depends on:** S2-01, S1-05
**ADRs honored:** ADR-P7-004 (OpenRewrite deferred), ADR-P7-006 (Recipe.engine Literal extended), ADR-P7-001 (six named seams), ADR-P7-009 (contract-surface snapshot)

## Context

This story lands the heart of the Phase 7 recipe path: the handrolled `DockerfileRecipeEngine` that mutates Dockerfile ASTs deterministically and emits clean `git format-patch` output. Per ADR-P7-004, Phase 7 ships **one** Dockerfile-shaped engine — no OpenRewrite stub, no `rewrite-docker` — so this engine carries the entire weight of both the single-stage swap and the multi-stage refactor recipes that land in S4-04/S4-05.

The engine is foundational for Step 4: S4-02 builds the round-trip + idempotence property tests on top of it, S4-03 wraps it in the `DockerfileBaseImageSwapTransform`, and S4-04/S4-05 supply the recipes it consumes. Once green here, every later step's distroless path depends on the determinism and round-trip safety this engine establishes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›4. DockerfileRecipeEngine` — interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — the `test_dockerfile_engine.py` ≥12-test target.
  - `../phase-arch-design.md §Edge cases` rows 1, 2, 10 — hostile Dockerfile, round-trip failure, BuildKit heredoc.
  - `../phase-arch-design.md §Harness engineering` — deterministic subprocess wrappers, fixed bot identity for `git format-patch`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — *no* OpenRewrite path; `DockerfileRecipeEngine` is the only Dockerfile engine in Phase 7.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — engine `name = "dockerfile"` joins the `Recipe.engine` Literal value added in S1-05.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — new files only.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — recipe-first ordering; the engine sits behind `RecipeMatcher`.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 18` — OpenRewrite shipped → deferred.
  - `../final-design.md §"Departures #3 ADR-P7-004"` — pure deferral rationale.
- **Existing code (to look at, not to edit):**
  - `src/codegenie/recipes/contract.py` — the `RecipeEngine` ABC + `ApplyContext` + `RecipeApplication` from Phase 3. Implement verbatim.
  - `src/codegenie/recipes/engines/` — Phase 3's `NcuEngine` is the reference for `@register_recipe_engine` shape and `git format-patch` helper usage.
  - `src/codegenie/tools/dockerfile_parse.py` — the S2-01 wrapper this engine calls (strict-mode, BOM/CR/ONBUILD rejection, 1 MB cap, 10 s wall-clock).

## Goal

`DockerfileRecipeEngine` exists, registers via `@register_recipe_engine` with `name="dockerfile"`, implements the Phase 3 `RecipeEngine` ABC verbatim, asserts `parse(serialize(parse(x))) == parse(x)` before emitting any patch, and produces byte-identical `git format-patch -1 --stdout` output across five consecutive runs on the same input.

## Acceptance criteria

- [ ] `src/codegenie/recipes/engines/dockerfile_engine.py` exists with `class DockerfileRecipeEngine(RecipeEngine)` decorated by `@register_recipe_engine`, `name = "dockerfile"`.
- [ ] `available()` returns `True` iff `dockerfile-parse` is importable **and** `docker buildx` is on `$PATH`; returns `False` (no raise) when either is missing.
- [ ] `apply(ctx: ApplyContext)` returns `RecipeApplication`; on round-trip failure returns `exit_code=2, errors=["roundtrip_failed:<reason>"]`; on parser rejection returns `exit_code=3, errors=["dockerfile_rejected:<reason>"]`.
- [ ] Round-trip post-assertion: before any patch bytes are returned, the engine re-parses the serialized output and compares against the originally-parsed AST; failure raises `RoundTripFailure` internally and is translated to `exit_code=2`.
- [ ] Byte-only canonicalization: serializer strips trailing whitespace and normalizes line endings to LF only — no semantic rewrites, no token reordering, no instruction-case normalization (asserted by `tests/unit/recipes/engines/test_dockerfile_engine.py::test_canonicalization_byte_only`).
- [ ] `git format-patch -1 --stdout` runs with `core.hooksPath=/dev/null` and a fixed bot identity (`name="codegenie"`, `email="codegenie@local"`); five consecutive runs against the same fixture produce byte-identical patches.
- [ ] No `import random`, no `import time`, no `from datetime import` of `datetime.now`/`time.time` anywhere under `src/codegenie/recipes/engines/dockerfile_engine.py` (fence-CI deny-imports — assertion lives in S4-06 / S7-06 but the file must already comply).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/recipes/engines/dockerfile_engine.py` and `tests/unit/recipes/engines/test_dockerfile_engine.py`.

## Implementation outline

1. Read Phase 3's `RecipeEngine` ABC and `NcuEngine` for the `@register_recipe_engine` pattern, `ApplyContext`/`RecipeApplication` shapes, and the existing `git format-patch` helper.
2. Sketch `DockerfileRecipeEngine` skeleton: `name`, `available()`, `apply()`. Delegate parsing to `tools.dockerfile_parse.parse()` (S2-01).
3. Build the mutation primitives the seed recipes need: `replace_from_image(stage_idx, new_image)`, `convert_to_multi_stage(builder_image, runtime_image, copy_paths)` — but keep them minimal; only what the recipes in S4-04 and S4-05 need.
4. Implement the round-trip post-assertion: `parse(serialize(mutated_ast)) == mutated_ast`. Surface failures as `RoundTripFailure` → `RecipeApplication(exit_code=2, ...)`.
5. Implement byte-only canonicalization: LF normalization + trailing-WS strip. **Not** an AST pass — operates on the serialized bytes.
6. Wire the deterministic `git format-patch` helper from Phase 3; pass `env={"GIT_COMMITTER_NAME": "codegenie", "GIT_COMMITTER_EMAIL": "codegenie@local", "GIT_AUTHOR_NAME": "codegenie", "GIT_AUTHOR_EMAIL": "codegenie@local"}` and `--no-hooks` / `core.hooksPath=/dev/null`.
7. Add typed errors `RoundTripFailure`, `DockerfileRejected` (re-export from `tools.dockerfile_parse` if already there).
8. Add docstrings on public surface; structlog hook at engine start / engine end with `engine="dockerfile", recipe_id=<id>, ast_round_trip_ok=<bool>` per `phase-arch-design.md §Harness engineering`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/recipes/engines/test_dockerfile_engine.py`

```python
# tests/unit/recipes/engines/test_dockerfile_engine.py
def test_register_and_apply_single_stage_swap(tmp_path):
    # arrange: a minimal Dockerfile + a recipe-shaped ApplyContext
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM node:20.10.0-bullseye\nCMD [\"node\", \"server.js\"]\n")
    ctx = build_apply_context(
        repo_root=tmp_path,
        recipe=Recipe(engine="dockerfile", id="swap_base_image_single_stage", ...),
        target_image="cgr.dev/chainguard/node:20-distroless@sha256:" + "a" * 64,
    )

    # act: lookup the engine via the registry, apply
    engine = get_recipe_engine("dockerfile")
    result = engine.apply(ctx)

    # assert: success, patch is non-empty, FROM line updated
    assert result.exit_code == 0
    assert b"-FROM node:20.10.0-bullseye" in result.patch_bytes
    assert b"+FROM cgr.dev/chainguard/node:20-distroless" in result.patch_bytes
```

Additional red tests anchoring distinct behaviors:

```python
def test_round_trip_failure_returns_exit_code_2(monkeypatch):
    # arrange: monkeypatch the parser so parse(serialize(parse(x))) != parse(x)
    # act: apply
    # assert: result.exit_code == 2 and "roundtrip_failed" in result.errors[0]
    ...

def test_available_false_when_docker_buildx_missing(monkeypatch):
    monkeypatch.setenv("PATH", "")
    engine = DockerfileRecipeEngine()
    assert engine.available() is False  # no raise
```

The first test fails with `ImportError` (module doesn't exist) or `KeyError` (registry doesn't know `"dockerfile"`). Confirm red, commit the failing test as a marker.

### Green — make it pass

Add `src/codegenie/recipes/engines/dockerfile_engine.py` with the minimum surface to pass the three tests:
- `@register_recipe_engine` decorator + `name = "dockerfile"`.
- `available()` returns `bool` based on `importlib.util.find_spec("dockerfile_parse")` and `shutil.which("docker")`.
- `apply()` calls the S2-01 wrapper, performs one mutation (FROM-line replace for the single-stage case), runs the round-trip assertion, calls the Phase 3 `git format-patch` helper.

Resist implementing the multi-stage path here — it lands in S4-05 via a separate recipe + the second mutation primitive. One engine, two recipes; the engine carries only the primitives the recipes need.

### Refactor — clean up

- Pull mutation primitives into private helpers (`_replace_from`, `_emit_multi_stage`) inside the engine module — not a new module.
- Type hints on every public method; return types pinned.
- Docstrings on `DockerfileRecipeEngine`, `available`, `apply` referencing ADR-P7-004 and ADR-P7-006.
- Structlog hook at `apply` entry/exit with the fields named in `phase-arch-design.md §Harness engineering`.
- Edge cases from `phase-arch-design.md §Edge cases` rows 1, 2, 10 — each should translate to a distinct `exit_code` + `errors[0]` shape; assert each in `tests/unit/recipes/engines/test_dockerfile_engine.py`.
- Confirm no `time` / `random` / `datetime.now` imports remain — these break determinism and will fail S4-06's fence-CI synthetic-PR check.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/engines/dockerfile_engine.py` | New file — implements `RecipeEngine` ABC per ADR-P7-004 / ADR-P7-006. |
| `tests/unit/recipes/engines/test_dockerfile_engine.py` | New test — anchors TDD red phase; ≥12 tests per `phase-arch-design.md §Testing strategy ›Unit tests`. |
| `tests/unit/recipes/engines/__init__.py` | New empty file — package marker if not already present. |
| `tests/fixtures/dockerfiles/single_stage_node20.Dockerfile` | New fixture — minimal Node 20 Dockerfile for the red test. |

## Out of scope

- **`DockerfileBaseImageSwapTransform`** — handled by story S4-03 (this engine is consumed by the transform, not the other way around).
- **`swap_base_image_single_stage.yaml` recipe + Node 20 golden patch** — handled by story S4-04.
- **`multi_stage_distroless_refactor.yaml` recipe + Go golden patch** — handled by story S4-05.
- **Round-trip Hypothesis property test over the full adversarial corpus** — handled by story S4-02 (initial small fixture set) and story S6-02 (full corpus per G14).
- **Fence-CI synthetic-PR rejection test** — handled by story S4-06.
- **Snapshot regeneration for the new `RecipeEngine` registration** — flows through story S4-06's snapshot canary path; the `Recipe.engine` Literal extension itself already landed in S1-05.

## Notes for the implementer

- The round-trip assertion is the load-bearing property of this engine (G14). It compares parsed ASTs, not bytes — that's what makes byte-only canonicalization legitimate. If the assertion compares bytes you've made canonicalization load-bearing for correctness and broken the contract.
- `dockerfile-parse` is single-maintained and brittle on edge cases (BuildKit heredocs especially — `phase-arch-design.md §Edge cases` row 10). Reject inputs the wrapper flags with `parser_skipped_lines > 0` via a clean `exit_code=3` rather than working around upstream bugs (per `High-level-impl.md §Step 4 risks`).
- `git format-patch` will silently emit different bytes if `core.autocrlf` is on, if `core.hooksPath` is unset, if `user.name`/`user.email` come from the developer's `~/.gitconfig`, or if `GIT_COMMITTER_DATE` varies. Use the Phase 3 helper — it already handles all four. Don't roll your own.
- Phase 3's `RecipeApplication` exit-code translation table maps to Phase 4's `FallbackTierResult.source` without change — don't introduce new exit codes; reuse the existing `0` / `2` / `3` codes already accepted by the planner.
- The engine returns a `RecipeApplication`, not a `TransformOutput`. The `TransformOutput`-shaped result is the responsibility of S4-03's `DockerfileBaseImageSwapTransform`.
- Per `CLAUDE.md` Rule 8, read `src/codegenie/recipes/engines/ncu_engine.py` (or equivalent Phase 3 engine) before writing — the `git format-patch` helper, `@register_recipe_engine` shape, and `ApplyContext` consumption patterns are all there. Don't re-derive.
- The performance envelope (< 500 ms full apply) is checked formally in S7-04 (`tests/perf/test_dockerfile_engine_p95.py`); don't add perf assertions here.
