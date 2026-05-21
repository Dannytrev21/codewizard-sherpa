# Story S10-01 — `DockerfileBaseImageSwapTransform` + `dockerfile-parse` AST manipulation

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** Ready
**Effort:** M
**Depends on:** S8-03 (plugin loader + `api.py` side-effect registration), S9-01 (`chainguard_image_recommendation_table.yaml` + Pydantic loader)
**ADRs honored:** [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse`, NOT OpenRewrite), [Phase 7 ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) (`dockerfile-parse` dep is row #9), [Phase 3 ADR-0001](../../03-vuln-deterministic-recipe/ADRs/0001-phase5-contract-surface.md) (`Transform` ABC, `ApplyContext`, `TransformOutcome` contract surface)

> **⚠ Amendment A sequencing note (2026-05-20).** This story predates Phase 7 Amendment A ([`../final-design.md` §Amendment A](../final-design.md)). Its acceptance criteria are **extended by [S16-02](S16-02-recipe-contract-amendment.md)** — the recipe gains typed gather inputs (`SecretPatternSlice`, `TargetImageContentSlice`, `native_modules`) and the ability to refuse via the [S16-01](S16-01-migration-refusal-taxonomy.md) taxonomy. Do **not** execute this story before the Amendment A gather stories (Steps 13–15) and S16-01/S16-02 land. See [`README.md` §"Stories — Amendment A"](README.md).

## Context

Phase 7's distroless migration produces Dockerfile edits — not language-level code edits. Phase 3 already shipped `RecipeEngine` Protocol with two implementations: `NpmLockfileRecipeEngine` (production) and `OpenRewriteRecipeEngine` (scaffold for future Java/Kotlin/etc. transforms). Phase 7's recipes do NOT plug into `OpenRewriteRecipeEngine`. The engine split is named explicitly in [ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md): `dockerfile-parse` for Dockerfile-format recipes; OpenRewrite remains the engine for Phase 8+ language-level transforms. The reasoning is concrete — JVM cold-start tax (~2 s) is asymmetric with `dockerfile-parse`'s ≤ 80 ms; OpenRewrite's Dockerfile recipe community is immature; pure-Python AST manipulation is reviewable and deterministic.

`DockerfileBaseImageSwapTransform` is the cheap path: single `FROM` swap + multi-stage runner adjustments (`COPY --from=builder`, `USER nonroot`, exec-form `ENTRYPOINT`). It reads Step 9's frozen `chainguard_image_recommendation_table.yaml` catalog. The recipe does **NOT** call `docker build` — building is `DistrolessBuildGate`'s job (S10-04). That separation is load-bearing: the recipe produces a diff; the gate evaluates the diff inside a microVM. Conflating them would re-introduce per-recipe build cost and couple the transform to sandbox lifecycle.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §11` — `DockerfileBaseImageSwapTransform`'s public interface, internal structure (single `FROM` swap; multi-stage runner adjustments), perf envelope (≤ 80 ms p99), failure behavior (`TransformOutcome(kind="not_applicable", reason="dockerfile_parse_failed")` and `"no_distroless_counterpart"`).
  - `../phase-arch-design.md §Edge cases #13` — `dockerfile-parse` cannot parse exotic Dockerfile syntax (heredocs, ARG-driven FROM) → `not_applicable`.
  - `../phase-arch-design.md §Scenarios §Scenario B` — base-image-only CVE happy path: `DockerfileBaseImageSwapTransform.apply` runs before the gate stack.
  - `../phase-arch-design.md §Control flow §step 7` — recipe applies between `Applies` and the gate-stack.
- **Phase ADRs:**
  - [`../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md`](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) — engine split rationale; `dockerfile-parse` is the one net-new runtime Python dep; **NO `docker build` in the recipe**.
  - [`../ADRs/0009-phase-7-byte-edit-allowlist-fence.md`](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — `pyproject.toml` `dockerfile-parse` dep is enumerated row #9; do not edit other locked Phase 0–6.5 files.
- **Existing code:**
  - `src/codegenie/transforms/transform.py` — `Transform(ABC)` and `TransformProvenance` shape (Phase 3 S1-04).
  - `src/codegenie/transforms/apply_context.py` — `ApplyContext` and `AttemptSummary` shape.
  - Phase 3 `plugins/vulnerability-remediation--node--npm/recipes/npm_lockfile_pin.py` — sibling-Phase concrete-`Transform` precedent (the file layout, `TransformOutcome.Applied` construction, `applicability()` return shape).
  - `plugins/distroless-migration--node--npm/data/loader.py::load_chainguard_catalog(path)` (S9-01) — the catalog loader; takes a `Path`, returns `Result[ChainguardCatalog, ParseError]`.

## Goal

Land `plugins/distroless-migration--node--npm/recipes/__init__.py` and `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`. `DockerfileBaseImageSwapTransform(Transform)` is a pure-Python `dockerfile-parse`-driven recipe that: (a) reads the Chainguard catalog at construction time via DI; (b) returns `Applies` from `applicability()` iff the resolved CVE has a matching catalog entry AND the Dockerfile's `FROM` line is parseable; (c) returns `TransformOutcome.Applied(diff)` from `apply()` with a deterministic byte-identical diff matching `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff`; (d) does **NOT** invoke `docker build` or any external binary; (e) lands in p99 ≤ 80 ms across 1000 trials.

## Acceptance criteria

### Recipe surface

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` defines `class DockerfileBaseImageSwapTransform(Transform)`. Module also creates `plugins/distroless-migration--node--npm/recipes/__init__.py` (empty body is fine; the module exists for plugin-side-effect imports per S8-03).
- [ ] **AC-2 — `Transform` ABC compliance.** `DockerfileBaseImageSwapTransform` defines the four class-level attributes the ABC requires (`transform_id: TransformId`, `diff_bytes: bytes`, `files_changed: tuple[SandboxedPath, ...]`, `provenance: TransformProvenance`) AND implements `applicability(ctx: ApplyContext) -> Applicability` + `apply(ctx: ApplyContext) -> TransformOutcome`. `isinstance(t, Transform)` is `True`.
- [ ] **AC-3 — DI for the catalog, not a module-level singleton.** Constructor signature: `__init__(self, *, catalog: ChainguardCatalog, logger: Logger) -> None`. The catalog is injected — the recipe does NOT call `load_chainguard_catalog()` itself; the plugin's `api.py` (S8-03) constructs the recipe with the loaded catalog. **No global state.** Test: two instances with different injected catalogs return different `applicability()` results for the same `ApplyContext`.

### `applicability()` semantics

- [ ] **AC-4 — `Applies` iff catalog matches AND Dockerfile parseable.** `applicability(ctx)` returns `Applies` only when (a) `ctx.cve_id` is a key in the injected catalog AND (b) the repo's `Dockerfile` parses cleanly via `dockerfile-parse` AND (c) the parsed `FROM` line's base-image kind is a known-migratable kind (Alpine / Debian-slim per the catalog row). Otherwise returns `NotApplicable(reason=...)` with one of: `"no_distroless_counterpart"`, `"dockerfile_parse_failed"`, `"base_image_already_distroless"`.
- [ ] **AC-5 — Parameterized `NotApplicable` reasons are typed sum-type members.** The `reason` strings are pulled from a module-level `Final[frozenset[str]]` set (`_NOT_APPLICABLE_REASONS`); module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"dockerfile_base_image_swap.dockerfile_parse_failed", "dockerfile_base_image_swap.no_distroless_counterpart"})` validated at import via `raise AssertionError(...)` (NOT bare `assert` — bare `assert` is repo-banned).

### `apply()` semantics and determinism

- [ ] **AC-6 — Single-FROM swap.** For a Dockerfile with one `FROM <alpine|debian-slim>:<tag>` line, `apply()` produces a `TransformOutcome.Applied(diff)` where `diff_bytes` decodes to a unified diff swapping the `FROM` to `cgr.dev/chainguard/node:<tag>@<sha256-digest>` (digest from catalog row). Compared byte-for-byte against `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff`.
- [ ] **AC-7 — Multi-stage runner adjustments.** For a Dockerfile with a `runtime` stage that ALREADY uses `COPY --from=builder`, `apply()` ALSO injects (if missing): `USER nonroot` (after the last `COPY`/`RUN` in the runtime stage), conversion of shell-form `ENTRYPOINT` to exec-form (e.g., `ENTRYPOINT npm start` → `ENTRYPOINT ["npm", "start"]`). Idempotent — applying the same Dockerfile twice yields the same diff.
- [ ] **AC-8 — Idempotence property.** `apply(apply(x).rendered) == apply(x).rendered` (byte-equal). Test fixture: `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py::test_idempotent`.
- [ ] **AC-9 — No `docker build` in the recipe.** AST-walk fence: `tests/fence/test_dockerfile_swap_no_docker_build.py` walks `dockerfile_base_image_swap.py` and rejects any `subprocess.run`, `os.system`, `os.popen`, `run_external_cli`, `run_allowlisted`, or call to `docker buildx`. The recipe body imports nothing from `codegenie.exec.*`.
- [ ] **AC-10 — `files_changed` carries the Dockerfile path.** `TransformOutcome.Applied.transform.files_changed == (SandboxedPath(<dockerfile_path>),)`. `provenance.plugin_id == PluginId("distroless-migration--node--npm")`, `provenance.recipe_id == RecipeId("dockerfile-base-image-swap")`.

### Failure paths

- [ ] **AC-11 — Unparseable Dockerfile.** Given a heredoc-containing or ARG-driven-FROM Dockerfile that `dockerfile-parse` cannot read, `applicability()` returns `NotApplicable(reason="dockerfile_parse_failed")`; `apply()` is not called. A `warning` event with ID `dockerfile_base_image_swap.dockerfile_parse_failed` is emitted to the plugin logger.
- [ ] **AC-12 — No-catalog-match.** Given a CVE absent from the catalog, `applicability()` returns `NotApplicable(reason="no_distroless_counterpart")`. Test fixture: `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py::test_no_catalog_match`.
- [ ] **AC-13 — Already-distroless input.** Given a Dockerfile whose `FROM` already references `cgr.dev/chainguard/*`, `applicability()` returns `NotApplicable(reason="base_image_already_distroless")` (catches operator double-application).

### Golden + perf

- [ ] **AC-14 — Golden diff file pinned.** `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` exists and contains the exemplar unified diff. Test asserts byte-equality. Updating the golden requires a code-review note (mirrors Phase 0 `tests/golden/probes/*.json` discipline).
- [ ] **AC-15 — p99 ≤ 80 ms.** `tests/perf/test_dockerfile_recipes.py::test_swap_p99_under_80ms` runs `apply()` over a representative 2-stage Dockerfile 1000 times; p99 ≤ 80 ms. Marked `@pytest.mark.bench`.

### Gates

- [ ] **AC-16** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-17** — `ruff check plugins/distroless-migration--node--npm/recipes/ tests/unit/transforms/recipes/` and `ruff format --check` clean.
- [ ] **AC-18** — `make lint-imports` green (no LLM SDK in the recipe module's runtime closure).
- [ ] **AC-19** — Phase 3–6.5 regression suite green (`make check`) AND `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01) — confirms the byte-edit allowlist (S5-01) hasn't been bypassed by this story.

## Implementation outline

1. **`plugins/distroless-migration--node--npm/recipes/__init__.py`** — empty module (one-line docstring acceptable). Side-effect imports added in S10-02/S10-03/S10-04/S10-05 will live here; S10-01 ships an empty shell.
2. **`plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`** — `class DockerfileBaseImageSwapTransform(Transform)`. Class-level annotations for the four ABC attributes (mirror `src/codegenie/probes/base.py`'s `Probe(ABC)` pattern). Constructor takes injected `catalog` + `logger`. Implement `applicability(ctx)` first as a pure decision tree over `(catalog_has_cve, dockerfile_parses, base_image_kind)`. Then `apply(ctx)` rebuilds the Dockerfile via `dockerfile-parse`'s structured-content API, computes a unified diff via `difflib.unified_diff(...)`, wraps in `TransformOutcome.Applied(...)`.
3. **Module-level `_NOT_APPLICABLE_REASONS: Final[frozenset[str]]`** + **`_WARNING_IDS: Final[frozenset[str]]`** with import-time `raise AssertionError(...)` validation (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007).
4. **`tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py`** — AC-4..AC-13 covered as parametrized + targeted tests.
5. **`tests/fence/test_dockerfile_swap_no_docker_build.py`** — AST-walk fence (AC-9).
6. **`tests/golden/dockerfile-diffs/alpine-to-chainguard.diff`** — pinned exemplar; created from a hand-reviewed run of the recipe against `tests/fixtures/portfolio/node-vulnerable-base-only/Dockerfile`.
7. **`tests/perf/test_dockerfile_recipes.py::test_swap_p99_under_80ms`** — bench-marked.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py`

```python
from pathlib import Path
import pytest

from codegenie.transforms import ApplyContext
from codegenie.types.identifiers import (
    AttemptNumber, CveId, EventId, PluginId, RecipeId,
    TransformId, TransformKind, WorkflowId,
)


def _ctx(tmp_path: Path, dockerfile_text: str, cve: str = "CVE-2026-9999") -> ApplyContext:
    df = tmp_path / "Dockerfile"
    df.write_text(dockerfile_text)
    return ApplyContext(
        workflow_id=WorkflowId("01HXX00000000000000000000Z"),
        attempt=AttemptNumber(1),
        cve_id=CveId(cve),
        repo_root=tmp_path,
        capabilities=...,  # CapabilityBundle()
    )


def test_swap_applies_when_catalog_matches(tmp_path, alpine_dockerfile, seeded_catalog):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapTransform,
    )
    tx = DockerfileBaseImageSwapTransform(catalog=seeded_catalog, logger=...)
    ctx = _ctx(tmp_path, alpine_dockerfile, cve="CVE-2026-9999")
    assert tx.applicability(ctx).kind == "applies"


def test_swap_not_applicable_when_no_catalog_row(tmp_path, alpine_dockerfile, empty_catalog):
    tx = DockerfileBaseImageSwapTransform(catalog=empty_catalog, logger=...)
    ctx = _ctx(tmp_path, alpine_dockerfile)
    result = tx.applicability(ctx)
    assert result.kind == "not_applicable"
    assert result.reason == "no_distroless_counterpart"


def test_swap_not_applicable_when_dockerfile_unparseable(tmp_path, seeded_catalog):
    heredoc_df = "FROM alpine:3.18\nRUN <<EOF\necho hi\nEOF\n"  # dockerfile-parse trips on heredocs
    tx = DockerfileBaseImageSwapTransform(catalog=seeded_catalog, logger=...)
    ctx = _ctx(tmp_path, heredoc_df)
    result = tx.applicability(ctx)
    assert result.kind == "not_applicable"
    assert result.reason == "dockerfile_parse_failed"


def test_swap_apply_matches_golden_diff(tmp_path, alpine_dockerfile, seeded_catalog):
    tx = DockerfileBaseImageSwapTransform(catalog=seeded_catalog, logger=...)
    ctx = _ctx(tmp_path, alpine_dockerfile)
    outcome = tx.apply(ctx)
    assert outcome.kind == "applied"
    golden = Path("tests/golden/dockerfile-diffs/alpine-to-chainguard.diff").read_bytes()
    assert outcome.transform.diff_bytes == golden


def test_swap_is_idempotent(tmp_path, alpine_dockerfile, seeded_catalog):
    tx = DockerfileBaseImageSwapTransform(catalog=seeded_catalog, logger=...)
    ctx1 = _ctx(tmp_path, alpine_dockerfile)
    first = tx.apply(ctx1)
    # apply rendered Dockerfile → recipe is now NotApplicable (already-distroless)
    (tmp_path / "Dockerfile").write_text(first.rendered_text)
    second = tx.applicability(ctx1)
    assert second.kind == "not_applicable"
    assert second.reason == "base_image_already_distroless"
```

State why it fails: `ModuleNotFoundError` — the recipe module does not exist yet.

### Green — minimal pass

- Land `plugins/distroless-migration--node--npm/recipes/__init__.py` (empty).
- Land `dockerfile_base_image_swap.py` with the decision tree in `applicability()` + the `dockerfile-parse`-driven rebuild in `apply()`. Read FROM lines; swap to catalog row's recommended digest-pinned image; reconstruct unified diff via `difflib.unified_diff`.
- Land the golden file `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` by hand-running the recipe and capturing the output.

### Refactor

- Hoist the decision-tree predicates (`_has_catalog_row`, `_dockerfile_parses`, `_base_kind_migratable`) to module-level pure functions; test them in isolation.
- Pull the digest-pinned FROM-line template (`f"cgr.dev/chainguard/{name}:{tag}@{digest}"`) into a `Final` constant; verify deterministic ordering.
- Add the `_WARNING_IDS` import-time validation; assert ID-shape via `raise AssertionError(...)`.
- Confirm the AST-walk fence (`tests/fence/test_dockerfile_swap_no_docker_build.py`) is green — no `subprocess.run`, no `os.system`, no `codegenie.exec` imports inside the recipe.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | NEW — empty shell; later stories' side-effect imports land here. |
| `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` | NEW — `DockerfileBaseImageSwapTransform(Transform)` pure-Python `dockerfile-parse` recipe per ADR-0013; reads injected `ChainguardCatalog`; produces unified diff; **no `docker build`**. |
| `tests/unit/transforms/recipes/__init__.py` | NEW (or extend) — test package marker. |
| `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` | NEW — AC-4..AC-13 suite + golden-diff equality. |
| `tests/fence/test_dockerfile_swap_no_docker_build.py` | NEW — AST-walk fence enforcing AC-9 (no `docker build`, no `subprocess`, no `codegenie.exec` in the recipe). |
| `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` | NEW — pinned exemplar diff (AC-14). |
| `tests/perf/test_dockerfile_recipes.py` | NEW or extend — `test_swap_p99_under_80ms` (AC-15), `@pytest.mark.bench`. |
| `pyproject.toml` | Confirm `dockerfile-parse` is present as a runtime dep (locked-row #9 of byte-edit allowlist; Phase 7 ADR-0009). If S9-01 didn't already add it, add it here; otherwise no edit. |

## Out of scope

- **Multi-stage refactor (moving shell-using `RUN` to builder stage)** — S10-02. This story only handles single-FROM swap + light runner-stage adjustments. If a Dockerfile has shell-using `RUN` in the runtime stage, `applicability()` may still return `Applies` (the swap is independent); S10-02's recipe runs later as a separate transform and addresses the shell-relocation.
- **`docker build` execution** — explicitly NOT this recipe's job. `DistrolessBuildGate` (S10-04) runs `docker buildx build --target=runtime` inside the microVM.
- **`DockerfilePolicyGate` invariant checking** — S10-03. The recipe produces a diff; the policy gate evaluates it.
- **`tests/integration/test_gates_register_phase7.py`** — that story's territory (S10-05's integration sweep).

## Notes for the implementer

- **`dockerfile-parse` is the recipe engine. NOT OpenRewrite.** ADR-0013 is the canonical citation. Do not reuse Phase 3's `OpenRewriteRecipeEngine` scaffold for this story — the engine split is deliberate. Adding the JVM cold-start cost would blow the p99 ≤ 80 ms budget and contradict the ADR.
- **No `docker build` in the recipe — period.** AC-9's AST-walk fence is the mechanical enforcement. Building the migrated image is `DistrolessBuildGate`'s responsibility (S10-04) inside the microVM. If you find yourself reaching for `subprocess.run(["docker", "buildx", ...])` here, stop — that's a gate, not a recipe.
- **DI over module-level state.** The Chainguard catalog is loaded once at plugin-load time by `api.py` (S8-03) and injected into the recipe constructor. Do NOT call `load_chainguard_catalog()` from within `applicability()` or `apply()` — that would re-load the YAML on every invocation and break determinism if the file mutated mid-workflow.
- **`base_image_already_distroless` is a `NotApplicable` reason, not an error.** Operators may double-apply (e.g., re-running the workflow after a partial success). The recipe shrugs and returns `NotApplicable` — no exception, no warning. The `DistrolessVulnProvenanceAdapter` (S4-03) carries the same reason string; consider sharing it via a `Final` constant in `plugins/distroless-migration--node--npm/_constants.py` if it's referenced in more than two places.
- **Unified diff via `difflib.unified_diff`.** Use the original Dockerfile text as the `a` side and the rebuilt-via-`dockerfile-parse` text as the `b` side. Diff context = 3 lines (the default). The golden file is byte-pinned; if `dockerfile-parse`'s output formatting shifts between minor versions, the golden may need a refresh — pin the `dockerfile-parse` version in `pyproject.toml` (and `uv.lock`).
- **`TransformProvenance.capability_use_id`** must be populated from `ctx.capabilities.use(...)` (Phase 3 S1-04 framing). Phase 3 ships `CapabilityBundle` as an empty shell; S4-05 adds `use()`; this story may need to skip the audit-anchor line until S4-05 ships — note `# TODO: capability_use_id once S4-05 lands` and use a sentinel `EventId("00" * 32)`. If S4-05 has already landed by the time this story runs, populate honestly.
- **`_WARNING_IDS` import-time validation.** Use `raise AssertionError("...")` — NOT bare `assert` (banned by the `forbidden-patterns` hook). Mirror Phase 0/1 probe convention.
- **Edge cases the golden does NOT cover** (deferred to S10-02): shell-using `RUN` lines (those move to a builder stage); multi-FROM with three+ stages; `COPY --from=base` referencing a now-removed stage. Document these explicitly in the recipe's module docstring as "see S10-02 for multi-stage refactor."
- **p99 ≤ 80 ms** is the budget. `dockerfile-parse` is fast (~5 ms on a simple Dockerfile); the `difflib.unified_diff` is fast; the catalog lookup is dict access (O(1)). The headroom is comfortable. If perf regresses, suspect: (a) repeated catalog loads (DI it); (b) `dockerfile-parse` instantiation in a hot loop (instantiate once per `apply()`).
- **Match the codebase's convention.** Phase 3's `npm_lockfile_pin.py` is the closest sibling — mirror its file layout, its `applicability()` ladder, its `TransformOutcome` construction shape. Disagreement is a separate conversation; conformance > taste (global Rule 11).
