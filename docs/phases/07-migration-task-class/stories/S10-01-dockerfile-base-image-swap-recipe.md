# Story S10-01 — `DockerfileBaseImageSwapTransform` + `dockerfile-parse` AST manipulation

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** HARDENED
**Effort:** M
**Depends on:** S8-03 (plugin loader + `api.py` side-effect registration), S9-01 (`chainguard_image_recommendation_table.yaml` + Pydantic loader), Phase-3 S5-01 (`RecipeProtocol` / `RecipeEngine` surface — the sanctioned matcher / worker split this story mirrors), Phase-3 S5-01b (`TransformRegistry` — where the produced `Transform` is surfaced per ADR-0014), a Phase-7 ADR amendment landing the three new `NotApplicableReason` Literal members (see Validation notes §Blocker resolution B4)
**ADRs honored:** [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse`, NOT OpenRewrite), [Phase 7 ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) (`dockerfile-parse` dep is row #9), [Phase 3 ADR-0001](../../03-vuln-deterministic-recipe/ADRs/0001-phase5-contract-surface.md) (`Transform` ABC is attributes-only — the recipe splits into matcher / engine / transform per this contract, NOT a single class with methods added to the ABC), [Phase 3 ADR-0014](../../03-vuln-deterministic-recipe/ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) (`RecipeEngine.apply` returns bare `RecipeOutcome`; the produced `Transform` is registered into a constructor-injected `TransformRegistry`)

> **⚠ Amendment A sequencing note (2026-05-20).** This story predates Phase 7 Amendment A ([`../final-design.md` §Amendment A](../final-design.md)). Its acceptance criteria are **extended by [S16-02](S16-02-recipe-contract-amendment.md)** — the recipe gains typed gather inputs (`SecretPatternSlice`, `TargetImageContentSlice`, `native_modules`) and the ability to refuse via the [S16-01](S16-01-migration-refusal-taxonomy.md) taxonomy. Do **not** execute this story before the Amendment A gather stories (Steps 13–15) and S16-01/S16-02 land. See [`README.md` §"Stories — Amendment A"](README.md).

## Validation notes (phase-story-validator, 2026-08-15)

Full audit trail at [`_validation/S10-01-dockerfile-base-image-swap-recipe.md`](_validation/S10-01-dockerfile-base-image-swap-recipe.md). Verdict **HARDENED**. Executive summary of the load-bearing edits — the story-as-drafted collided with the Phase-3 shipped contract in four independent ways, each of which would have blown up at the first `pytest` run:

- **B1 — `Transform` ABC has no methods.** Original AC-2 said `DockerfileBaseImageSwapTransform(Transform)` "implements `applicability(ctx) -> Applicability` + `apply(ctx) -> TransformOutcome`." But `src/codegenie/transforms/transform.py:64-95` ships `Transform` as an attributes-only ABC (`transform_id`, `diff_bytes`, `files_changed`, `provenance`). Adding methods to the ABC is a Phase-3 ADR-0001 contract amendment. **Resolution:** split into the sanctioned three-way shape mirroring Phase-3 S5-02 (`NpmLockfileTransform` + `NpmLockfileRecipeEngine`) and S5-03 (`DockerfileBaseImageTransform` + `OpenRewriteRecipeEngine`): (1) `DockerfileBaseImageSwapRecipe` implementing `RecipeProtocol` (the matcher — `applies(cve, bundle) -> Applies | NotApplies`); (2) `DockerfileRecipeEngine` implementing `RecipeEngine` (the worker — `async apply(repo, plan, capability) -> RecipeOutcome`); (3) `DockerfileBaseImageSwapTransform(Transform)` (the data-class output with a `.create(...)` smart constructor, mirror of `DockerfileBaseImageTransform.create` in `src/codegenie/transforms/engines/openrewrite.py:219`).
- **B2 — `ApplyContext` has no `cve_id` or `repo_root`.** Original TDD plan constructed `ApplyContext(workflow_id=..., attempt=..., cve_id=CveId(...), repo_root=tmp_path, capabilities=...)` — but `ApplyContext` ships as `(workflow_id, attempt, prior_attempts, capabilities)` with `extra="forbid"`, so those unknown kwargs would raise `ValidationError` at construction. **Resolution:** CVE-ID reaches the recipe via the Phase-3 `RecipeProtocol.applies(cve: VulnerabilityRecord, bundle: Bundle)` signature (`src/codegenie/transforms/recipe_engine.py:95-117`). Repo path reaches the engine via `RecipeEngine.apply(repo: SandboxedPath, plan, capability)` (`src/codegenie/transforms/engines/npm_lockfile.py:563`). The TDD plan is rewritten to use those parameters directly rather than inventing new `ApplyContext` fields.
- **B3 — `TransformOutcome` doesn't exist; `Applied` has no `.transform` or `.rendered_text`.** Original AC-6 said `apply()` produces "`TransformOutcome.Applied(diff)` where `diff_bytes` decodes to a unified diff"; the idempotence test read `first.rendered_text`. The shipped umbrella is `RecipeOutcome = Applied | Skipped | RecipeNotApplicable | RecipeFailed`, and `Applied` carries `{kind, transform_id, plugin_id, recipe_id}` only (`src/codegenie/transforms/outcomes.py:249-259`). **Resolution:** ACs now read the `.diff_bytes` off `TransformRegistry.get(outcome.transform_id)` (the ADR-0014 surface). Idempotence is re-expressed as an `applicability()` observable: re-applying the already-swapped Dockerfile yields `NotApplies(reason="base_image_already_distroless")`.
- **B4 — `NotApplicableReason` Literal doesn't include the three Phase-7 reasons.** Original AC-4 named `"no_distroless_counterpart" | "dockerfile_parse_failed" | "base_image_already_distroless"` as `NotApplicable` reasons; the shipped Literal at `src/codegenie/transforms/outcomes.py:98-106` is `{PEER_DEP_CONFLICT, MAJOR_BUMP_REFUSE, OVERRIDES_AMBIGUOUS, RECIPE_CATALOG_MISS, ALL_RECIPES_NOT_APPLICABLE, NO_RECIPES_REGISTERED, CVE_NOT_IN_DEPENDENCY_SET}`. Widening the Literal is a Phase-3 ADR-0001 contract change (regenerates the S6-06 contract snapshot). **Resolution:** a Phase-7 ADR amendment must land the additive widening BEFORE this story executes. New AC-16.a pins the sequencing.

Hardening edits also added: **debian-slim golden alongside alpine** (AC-6 was Alpine-only, catalog supports both); **DI-catalog-difference red test** (AC-3 promised it but the TDD plan didn't ship the test); **multi-adversarial Dockerfile fixture table** (AC-11 called out heredoc + ARG-driven FROM as one bucket; `dockerfile-parse` also trips on `# syntax=` BuildKit frontmatter + parser errors on Windows-CRLF-in-heredoc); **warning-emission test via mock logger** (AC-11 promised a warning event but no test); **metamorphic Hypothesis pair** (for any `(Dockerfile, catalog)` yielding `Applies`, swapping to a CVE absent from the catalog yields `no_distroless_counterpart`); **malformed-catalog-row shrug** (missing `digest` field yields `NotApplicable`, never raises). Warning ID set widened to include `base_image_already_distroless` for 1:1 parity with the three `NotApplicable` reasons.

Executor note: this story is intentionally deferred behind Amendment A (S13–S15 gather + S16-01 refusal taxonomy + S16-02 recipe amendment). B4's ADR amendment should land in the same PR series. If S16-02's ACs re-tighten (or contradict) any AC below at execution time, the S16-02 wording wins by explicit sequencing.

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

Land `plugins/distroless-migration--node--npm/recipes/__init__.py` and `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`. Mirror the Phase-3 three-way split (matcher / engine / transform data-class):

1. **`DockerfileBaseImageSwapRecipe`** — implements `RecipeProtocol` (from `codegenie.transforms.recipe_engine`). Constructor takes the DI-injected `ChainguardCatalog` + `logger`. `applies(cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies` returns `Applies` iff (i) the CVE maps to a catalog row AND (ii) the repo's `Dockerfile` parses cleanly AND (iii) the base-image kind is migratable (Alpine or debian-slim per the catalog row) AND (iv) the Dockerfile is not already distroless.
2. **`DockerfileRecipeEngine`** — implements `RecipeEngine` (Protocol). Constructor takes the injected `ChainguardCatalog` + `TransformRegistry` + `logger`. `apply(repo: SandboxedPath, plan: ApplicationPlan, capability: NoOpCapability) -> RecipeOutcome` performs the pure-Python `dockerfile-parse` rebuild, builds the unified diff via `difflib.unified_diff`, constructs a `DockerfileBaseImageSwapTransform` via its `.create(...)` smart constructor, registers it into the injected `TransformRegistry`, and returns `Applied(transform_id=..., plugin_id=..., recipe_id=...)`. Does **NOT** invoke `docker build` or any external binary. Lands in p99 ≤ 80 ms across 1000 trials.
3. **`DockerfileBaseImageSwapTransform(Transform)`** — the data-class output. Mirrors `DockerfileBaseImageTransform` in `src/codegenie/transforms/engines/openrewrite.py` — per-instance state for the four ABC attributes; `.create(diff_bytes, files_changed, provenance)` smart constructor computes `transform_id` as `blake3.blake3(diff_bytes).hexdigest()` and rejects empty diff / empty files_changed.

Byte-for-byte determinism against pinned golden fixtures for BOTH `alpine-to-chainguard.diff` and `debian-slim-to-chainguard.diff`.

## Acceptance criteria

### Recipe surface — matcher / engine / transform split

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` defines THREE collaborators (see Goal §1–§3): `class DockerfileBaseImageSwapRecipe` (matcher, `RecipeProtocol`), `class DockerfileRecipeEngine` (worker, `RecipeEngine` Protocol), and `class DockerfileBaseImageSwapTransform(Transform)` (data-class output). Module also creates `plugins/distroless-migration--node--npm/recipes/__init__.py` (empty body is fine; the module exists for plugin-side-effect imports per S8-03).
- [ ] **AC-2 — `RecipeProtocol` + `RecipeEngine` conformance; `Transform` ABC data-class conformance.** (a) `isinstance(recipe, RecipeProtocol)` is `True` after `from codegenie.transforms.recipe_engine import RecipeProtocol`. (b) `isinstance(engine, RecipeEngine)` is `True` after the analogous import. (c) `isinstance(tx, Transform)` is `True`; `tx.transform_id / diff_bytes / files_changed / provenance` return the four ABC attributes. (d) `DockerfileBaseImageSwapTransform` defines its `__init__` with keyword-only args matching `NpmLockfileTransform.__init__` verbatim (mirrors `src/codegenie/transforms/engines/npm_lockfile.py:520-539`) and a `@classmethod def create(...)` smart constructor mirroring `DockerfileBaseImageTransform.create` (`src/codegenie/transforms/engines/openrewrite.py:219-241`) — computes `transform_id` as `TransformId(blake3.blake3(diff_bytes).hexdigest())`, rejects empty `diff_bytes` or empty `files_changed` with `ValueError`. (e) The story does NOT add methods to the `Transform` ABC or new fields to `ApplyContext` — either edit would be a Phase-3 ADR-0001 contract amendment that regenerates the S6-06 snapshot.
- [ ] **AC-3 — DI for the catalog, not a module-level singleton.** `DockerfileBaseImageSwapRecipe.__init__(self, *, catalog: ChainguardCatalog, logger: Logger) -> None`. `DockerfileRecipeEngine.__init__(self, *, catalog: ChainguardCatalog, transform_registry: TransformRegistry, logger: Logger) -> None`. The catalog is injected — no module-level `_CATALOG` singleton, no `load_chainguard_catalog()` call inside `applies()` or `apply()`; the plugin's `api.py` (S8-03) constructs both collaborators with the loaded catalog. **No global state.** **Red test (`test_di_catalog_difference`):** two `DockerfileBaseImageSwapRecipe` instances built with an `empty_catalog` vs a `seeded_catalog` must return `NotApplies(no_distroless_counterpart)` vs `Applies(...)` respectively for the same `(cve, bundle)` pair.

### `applies()` semantics — matcher

- [ ] **AC-4 — `Applies` iff catalog matches AND Dockerfile parseable AND base-image migratable AND not-already-distroless.** `DockerfileBaseImageSwapRecipe.applies(cve, bundle)` returns `Applies(plan=<a Phase-7-narrow ApplicationPlan>)` only when ALL FOUR hold: (a) `cve.cve_id` is a key in the injected catalog, AND (b) the `Dockerfile` reachable through `bundle` parses cleanly via `dockerfile-parse`, AND (c) the parsed `FROM` line's base-image kind is a known-migratable kind (Alpine or debian-slim per the catalog row), AND (d) the parsed `FROM` line does not already reference `cgr.dev/chainguard/*`. Otherwise returns `NotApplies(reason=...)` with one of: `"no_distroless_counterpart"`, `"dockerfile_parse_failed"`, `"base_image_already_distroless"`.
- [ ] **AC-4.a — `applies()` is a pure decision tree.** The four predicates `_has_catalog_row(catalog, cve_id) -> bool`, `_dockerfile_parses(bundle) -> Result[ParsedDockerfile, str]`, `_base_kind_migratable(parsed, catalog_row) -> bool`, `_already_distroless(parsed) -> bool` are module-level pure functions with their own unit tests. `applies()` is a thin dispatcher over them. Mutation-resistance: a Hypothesis property test asserts `applies(cve, bundle)` never raises across arbitrary (dockerfile_text, cve_id) pairs — only returns `Applies` or `NotApplies`.
- [ ] **AC-5 — Parameterized `NotApplies` reasons are typed sum-type members with 1:1 warning-ID parity.** The three Phase-7 `NotApplies.reason` strings are declared once at module scope: `_NOT_APPLICABLE_REASONS: Final[frozenset[str]] = frozenset({"no_distroless_counterpart", "dockerfile_parse_failed", "base_image_already_distroless"})`. The warning-ID set carries the same three-way parity: `_WARNING_IDS: Final[frozenset[str]] = frozenset({"dockerfile_base_image_swap.no_distroless_counterpart", "dockerfile_base_image_swap.dockerfile_parse_failed", "dockerfile_base_image_swap.base_image_already_distroless"})`, each matching the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex from Phase 1 ADR-0007. Both sets are validated at import via `raise AssertionError(...)` (NOT bare `assert` — banned by the `forbidden-patterns` hook). Import-time invariant test: `_NOT_APPLICABLE_REASONS` and the reason-suffix of every `_WARNING_IDS` entry are equal as sets.

### `apply()` semantics and determinism — engine

- [ ] **AC-6 — Single-FROM swap; two goldens (alpine AND debian-slim).** For each of `tests/fixtures/portfolio/node-vulnerable-base-only/Dockerfile` (alpine base) and `tests/fixtures/portfolio/node-vulnerable-debian-slim-base/Dockerfile` (debian-slim base), `DockerfileRecipeEngine.apply(repo, plan, capability)` returns `Applied(transform_id=..., plugin_id=..., recipe_id=...)`. The produced `Transform` is retrieved via `transform_registry.get(outcome.transform_id)`; its `.diff_bytes` decodes to a unified diff swapping the `FROM` line to `cgr.dev/chainguard/node:<tag>@<sha256-digest>` (digest from the catalog row) and is byte-equal against `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` and `tests/golden/dockerfile-diffs/debian-slim-to-chainguard.diff` respectively.
- [ ] **AC-7 — Multi-stage runner adjustments.** For a Dockerfile with a `runtime` stage that ALREADY uses `COPY --from=builder`, `apply()` ALSO injects (if missing): `USER nonroot` (after the last `COPY`/`RUN` in the runtime stage), conversion of shell-form `ENTRYPOINT` to exec-form (e.g., `ENTRYPOINT npm start` → `ENTRYPOINT ["npm", "start"]`). Deterministic — running `apply()` twice on the same fixture yields byte-equal `.diff_bytes` across both runs.
- [ ] **AC-8 — Idempotence as an `applies()` observable.** After `engine.apply(repo, plan, capability)` succeeds, rewriting the Dockerfile with the swapped content and re-running `recipe.applies(cve, bundle)` returns `NotApplies(reason="base_image_already_distroless")`. This is the load-bearing idempotence signature: the same CVE cannot be re-applied to an already-migrated Dockerfile. (Original AC-8 asked `apply(apply(x).rendered) == apply(x).rendered` byte-equal — dropped because `Applied` has no `.rendered` field per Phase-3 shipped contract; the `applies()`-based observable is stronger anyway.)
- [ ] **AC-9 — No `docker build` in the recipe or engine.** AST-walk fence: `tests/fence/test_dockerfile_swap_no_docker_build.py` walks BOTH `dockerfile_base_image_swap.py` AND the engine module and rejects any `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen`, `run_external_cli`, `run_allowlisted`, or attribute access shaped like `docker.buildx` / `docker buildx`. The recipe / engine body imports nothing from `codegenie.exec.*`.
- [ ] **AC-10 — `files_changed` carries the Dockerfile path; provenance IDs pinned.** For an `Applied` outcome, `transform_registry.get(outcome.transform_id).files_changed == (SandboxedPath(<repo_relative_dockerfile_path>),)` (single-element tuple). `provenance.plugin_id == PluginId("distroless-migration--node--npm")`, `provenance.recipe_id == RecipeId("dockerfile-base-image-swap")`, `provenance.transform_kind == TransformKind("dockerfile-base-image-swap")`.

### Failure paths — `applies()` returns `NotApplies`, `apply()` returns `RecipeNotApplicable`

- [ ] **AC-11 — Multi-adversarial unparseable-Dockerfile fixture table.** At least THREE distinct unparseable-Dockerfile fixtures are wired into a parametrized test — each yielding `NotApplies(reason="dockerfile_parse_failed")` and each verified to trip `dockerfile-parse` on the pinned version. The three MUST include: (a) `heredoc` (`FROM alpine:3.18\nRUN <<EOF\necho hi\nEOF\n`); (b) `arg-driven FROM` (`ARG BASE\nFROM ${BASE}\n`); (c) `# syntax=` BuildKit frontmatter above the first `FROM`. Add more fixtures liberally as `dockerfile-parse` bug reports are triaged. `apply()` is not called for any of the three (asserted via a mock engine that would raise on call).
- [ ] **AC-11.a — Warning event emission for every `NotApplies` reason.** A `warning` event is emitted to the injected `logger` with an ID drawn from `_WARNING_IDS` — one per `NotApplies.reason`. Tests use a `MagicMock` logger and assert `logger.warning.call_args.args[0] in _WARNING_IDS` for each of the three failure paths (AC-11 heredoc/ARG/BuildKit, AC-12 no-catalog-match, AC-13 already-distroless).
- [ ] **AC-12 — No-catalog-match.** Given a CVE absent from the catalog, `applies()` returns `NotApplies(reason="no_distroless_counterpart")`. Test fixture: `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py::test_no_catalog_match`.
- [ ] **AC-13 — Already-distroless input.** Given a Dockerfile whose `FROM` already references `cgr.dev/chainguard/*`, `applies()` returns `NotApplies(reason="base_image_already_distroless")` (catches operator double-application).
- [ ] **AC-13.a — Malformed catalog row shrugs.** Given an otherwise-matching CVE whose catalog row is missing a `digest` field (or has an empty `digest`), `applies()` returns `NotApplies(reason="no_distroless_counterpart")` — NEVER raises `KeyError` or `ValidationError`. The recipe treats a malformed row as absence, not a crash. Pinned by a targeted test with a hand-crafted broken `ChainguardCatalog` fixture.
- [ ] **AC-13.b — Metamorphic property (Hypothesis).** For any `(dockerfile_text, catalog, cve_id)` triple that yields `Applies`, replacing `cve_id` with a fresh UUID absent from the catalog MUST yield `NotApplies(reason="no_distroless_counterpart")`. Same triple with `dockerfile_text` prepended by BuildKit frontmatter MUST yield `NotApplies(reason="dockerfile_parse_failed")`. Hypothesis strategy: `hypothesis.strategies.sampled_from(_KNOWN_MIGRATABLE_FIXTURES)` for the base, `hypothesis.strategies.uuids().map(lambda u: CveId(f"CVE-3000-{u.int % 9999}"))` for the counterfactual CVE.

### Golden + perf

- [ ] **AC-14 — Two golden diff files pinned + regeneration procedure documented.** `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` AND `tests/golden/dockerfile-diffs/debian-slim-to-chainguard.diff` exist; both tests assert byte-equality against the produced `Transform.diff_bytes`. Regeneration procedure is documented at `tests/golden/dockerfile-diffs/README.md` — names the `dockerfile-parse` version pin (pull from `pyproject.toml`), the hand-run command, and the code-review note requirement (mirrors Phase 0 `tests/golden/probes/*.json` discipline). A stale golden after a `dockerfile-parse` bump is a code-review conversation, not a silent skip.
- [ ] **AC-15 — p99 ≤ 80 ms.** `tests/perf/test_dockerfile_recipes.py::test_swap_p99_under_80ms` runs `engine.apply(...)` over a representative 2-stage Dockerfile 1000 times AFTER a 100-iteration warmup (JIT / import cache); asserts p99 ≤ 80 ms. Marked `@pytest.mark.bench` (advisory — excluded from default `pytest -q` runs per `pyproject.toml § [tool.pytest.ini_options]`).

### Gates + contract snapshot

- [ ] **AC-16** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-16.a — Phase-3 contract snapshot regenerated.** A Phase-7 ADR amendment lands adding the three new `NotApplicableReason` Literal members (`"no_distroless_counterpart"`, `"dockerfile_parse_failed"`, `"base_image_already_distroless"`) to `src/codegenie/transforms/outcomes.py`. The S6-06 contract-snapshot test (Phase-3 ADR-0001 §Consequences) regenerates and is re-committed as part of this story's PR. The `_NOT_APPLICABLE_REASONS` module-level set in the recipe is a proper subset of the widened `NotApplicableReason` Literal — pinned by a targeted test asserting `_NOT_APPLICABLE_REASONS.issubset(set(get_args(NotApplicableReason)))`.
- [ ] **AC-17** — `ruff check plugins/distroless-migration--node--npm/recipes/ tests/unit/transforms/recipes/` and `ruff format --check` clean.
- [ ] **AC-18** — `make lint-imports` green (no LLM SDK in the recipe module's runtime closure).
- [ ] **AC-19** — Phase 3–6.5 regression suite green (`make check`) AND `bench/vuln-remediation/` cassette replay byte-equal (ε ≤ $0.01) — confirms the byte-edit allowlist (S5-01) hasn't been bypassed by this story AND that the AC-16.a additive Literal widening did not perturb any existing Phase-3 recipe behavior.

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

Every test below is authored against the SHIPPED Phase-3 contract (`RecipeProtocol.applies(cve, bundle)`, `RecipeEngine.apply(repo, plan, capability)`, `Applied.transform_id` lookup via `TransformRegistry`), not against the invented `applicability(ctx) / apply(ctx) / TransformOutcome` shape from the pre-validation draft.

```python
from pathlib import Path
from unittest.mock import MagicMock

import blake3
import pytest
from hypothesis import given, strategies as st

from codegenie.transforms.outcomes import Applied, NotApplies
from codegenie.transforms.recipe_engine import RecipeEngine, RecipeProtocol
from codegenie.transforms.transform import Transform
from codegenie.transforms.transform_registry import TransformRegistry
from codegenie.types.identifiers import (
    CveId, PluginId, RecipeId, TransformId, TransformKind,
)

# --- Fixtures the test module owns (defined in conftest.py) --------------
# alpine_dockerfile / debian_slim_dockerfile — str contents of an
#   already-vulnerable base image Dockerfile.
# alpine_bundle(tmp_path, alpine_dockerfile) — writes the Dockerfile into
#   tmp_path and returns a Bundle whose repo root is tmp_path.
# seeded_catalog — ChainguardCatalog with CVE-2026-9999 → alpine row and
#   CVE-2026-8888 → debian-slim row; both rows carry a valid digest.
# empty_catalog — ChainguardCatalog with zero rows.
# broken_catalog — a catalog whose CVE-2026-9999 row is missing `digest`.
# mock_logger — MagicMock() re-used to assert `.warning(...)` calls.
# cve_9999 — VulnerabilityRecord(cve_id=CveId("CVE-2026-9999"), ...).


# ---------- AC-2 — Protocol / ABC conformance --------------------------

def test_recipe_conforms_to_RecipeProtocol(seeded_catalog, mock_logger):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe,
    )
    recipe = DockerfileBaseImageSwapRecipe(catalog=seeded_catalog, logger=mock_logger)
    assert isinstance(recipe, RecipeProtocol)


def test_engine_conforms_to_RecipeEngine(seeded_catalog, mock_logger):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileRecipeEngine,
    )
    registry = TransformRegistry()
    engine = DockerfileRecipeEngine(
        catalog=seeded_catalog, transform_registry=registry, logger=mock_logger,
    )
    assert isinstance(engine, RecipeEngine)


def test_transform_dataclass_smart_constructor_computes_blake3_id():
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapTransform,
    )
    diff = b"--- a/Dockerfile\n+++ b/Dockerfile\n@@ -1 +1 @@\n-FROM alpine:3.18\n+FROM cgr.dev/chainguard/node:20@sha256:abc\n"
    tx = DockerfileBaseImageSwapTransform.create(
        diff_bytes=diff,
        files_changed=(_sandbox_path("Dockerfile"),),
        provenance=_provenance(),
    )
    assert isinstance(tx, Transform)
    assert tx.transform_id == TransformId(blake3.blake3(diff).hexdigest())


def test_transform_smart_constructor_rejects_empty_diff():
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapTransform,
    )
    with pytest.raises(ValueError):
        DockerfileBaseImageSwapTransform.create(
            diff_bytes=b"", files_changed=(_sandbox_path("Dockerfile"),),
            provenance=_provenance(),
        )


# ---------- AC-3 — DI-catalog-difference red test ----------------------

def test_di_catalog_difference(alpine_bundle, cve_9999, seeded_catalog, empty_catalog, mock_logger):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe,
    )
    with_catalog = DockerfileBaseImageSwapRecipe(catalog=seeded_catalog, logger=mock_logger)
    without_catalog = DockerfileBaseImageSwapRecipe(catalog=empty_catalog, logger=mock_logger)

    assert with_catalog.applies(cve_9999, alpine_bundle).kind == "applies"
    v = without_catalog.applies(cve_9999, alpine_bundle)
    assert v.kind == "not_applies" and v.reason == "no_distroless_counterpart"


# ---------- AC-11 — Parametrized unparseable-Dockerfile table ----------

_UNPARSEABLE_FIXTURES = [
    ("heredoc", "FROM alpine:3.18\nRUN <<EOF\necho hi\nEOF\n"),
    ("arg-driven-from", "ARG BASE\nFROM ${BASE}\n"),
    ("buildkit-frontmatter", "# syntax=docker/dockerfile:1.4\nFROM alpine:3.18\n"),
]


@pytest.mark.parametrize("label, dockerfile_text", _UNPARSEABLE_FIXTURES, ids=[f[0] for f in _UNPARSEABLE_FIXTURES])
def test_unparseable_dockerfile_yields_dockerfile_parse_failed(
    label, dockerfile_text, tmp_path, seeded_catalog, cve_9999, mock_logger,
):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe,
    )
    (tmp_path / "Dockerfile").write_text(dockerfile_text)
    bundle = _bundle(tmp_path)
    recipe = DockerfileBaseImageSwapRecipe(catalog=seeded_catalog, logger=mock_logger)

    v = recipe.applies(cve_9999, bundle)
    assert v.kind == "not_applies" and v.reason == "dockerfile_parse_failed"
    mock_logger.warning.assert_called()
    warning_id = mock_logger.warning.call_args.args[0]
    assert warning_id == "dockerfile_base_image_swap.dockerfile_parse_failed"


# ---------- AC-6 — Two goldens (alpine + debian-slim) ------------------

@pytest.mark.parametrize(
    "fixture_name, golden_path",
    [
        ("alpine_bundle", "tests/golden/dockerfile-diffs/alpine-to-chainguard.diff"),
        ("debian_slim_bundle", "tests/golden/dockerfile-diffs/debian-slim-to-chainguard.diff"),
    ],
)
async def test_engine_apply_matches_golden(
    fixture_name, golden_path, request, seeded_catalog, mock_logger,
):
    bundle = request.getfixturevalue(fixture_name)
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileRecipeEngine, _plan_for_swap,
    )
    registry = TransformRegistry()
    engine = DockerfileRecipeEngine(
        catalog=seeded_catalog, transform_registry=registry, logger=mock_logger,
    )
    plan = _plan_for_swap(bundle=bundle)  # module-level helper the engine ships
    outcome = await engine.apply(bundle.repo_root, plan, _noop_capability())

    assert isinstance(outcome, Applied)
    tx = registry.get(outcome.transform_id)
    golden_bytes = Path(golden_path).read_bytes()
    assert tx.diff_bytes == golden_bytes


# ---------- AC-8 — Idempotence as an applies() observable --------------

async def test_apply_then_reapply_yields_already_distroless(
    alpine_bundle, cve_9999, seeded_catalog, mock_logger,
):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe, DockerfileRecipeEngine, _plan_for_swap,
    )
    registry = TransformRegistry()
    engine = DockerfileRecipeEngine(
        catalog=seeded_catalog, transform_registry=registry, logger=mock_logger,
    )
    recipe = DockerfileBaseImageSwapRecipe(catalog=seeded_catalog, logger=mock_logger)

    outcome = await engine.apply(alpine_bundle.repo_root, _plan_for_swap(bundle=alpine_bundle), _noop_capability())
    tx = registry.get(outcome.transform_id)
    # Materialize the diff onto the Dockerfile on disk — this simulates the
    # sandbox writing the swapped Dockerfile back.
    _apply_unified_diff(alpine_bundle.repo_root / "Dockerfile", tx.diff_bytes)

    v = recipe.applies(cve_9999, alpine_bundle)
    assert v.kind == "not_applies" and v.reason == "base_image_already_distroless"


# ---------- AC-13.a — Malformed catalog row shrugs --------------------

def test_malformed_catalog_row_returns_not_applies_not_raises(
    alpine_bundle, cve_9999, broken_catalog, mock_logger,
):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe,
    )
    recipe = DockerfileBaseImageSwapRecipe(catalog=broken_catalog, logger=mock_logger)
    v = recipe.applies(cve_9999, alpine_bundle)  # must not raise
    assert v.kind == "not_applies" and v.reason == "no_distroless_counterpart"


# ---------- AC-13.b — Metamorphic property ---------------------------

@given(cve_int=st.integers(min_value=1, max_value=10_000_000))
def test_metamorphic_swap_to_unknown_cve_yields_no_counterpart(
    cve_int, alpine_bundle, seeded_catalog, mock_logger,
):
    from plugins.distroless_migration__node__npm.recipes.dockerfile_base_image_swap import (
        DockerfileBaseImageSwapRecipe,
    )
    from codegenie.vuln_index.models import VulnerabilityRecord
    unknown_cve = VulnerabilityRecord(cve_id=CveId(f"CVE-3000-{cve_int}"), ...)  # test helper
    recipe = DockerfileBaseImageSwapRecipe(catalog=seeded_catalog, logger=mock_logger)
    v = recipe.applies(unknown_cve, alpine_bundle)
    assert v.kind == "not_applies" and v.reason == "no_distroless_counterpart"


# ---------- Helpers ---------------------------------------------------
def _sandbox_path(rel: str): ...   # SandboxedPath test helper
def _provenance():             ...  # TransformProvenance builder
def _bundle(root):             ...  # Bundle test helper
def _noop_capability():        ...  # NoOpCapability / minimal ADR-0011 audit token
def _plan_for_swap(*, bundle): ...  # Delegates to recipe's public helper
def _apply_unified_diff(path, diff_bytes): ...  # writes materialised patch
```

State why it fails: `ModuleNotFoundError` — the recipe module does not exist yet. Once the module exists, the `isinstance(..., RecipeProtocol)` / `isinstance(..., RecipeEngine)` assertions gate the shape before any I/O runs.

### Green — minimal pass

- Land `plugins/distroless-migration--node--npm/recipes/__init__.py` (empty).
- Land `dockerfile_base_image_swap.py` with the three-way split (§Goal §1–§3): matcher, engine, transform data-class. `applies()` is a thin dispatcher over four module-level pure predicates (`_has_catalog_row`, `_dockerfile_parses`, `_base_kind_migratable`, `_already_distroless`). The engine's `apply()` reads the parsed AST, applies the swap via `dockerfile-parse`'s structured-content API, computes a unified diff via `difflib.unified_diff`, constructs a `DockerfileBaseImageSwapTransform` via `.create(...)`, `register`s it into the injected `TransformRegistry`, and returns `Applied(transform_id=..., plugin_id=..., recipe_id=...)`.
- Land BOTH golden diff files: `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` AND `tests/golden/dockerfile-diffs/debian-slim-to-chainguard.diff` by hand-running the engine against the respective fixture and capturing the output. Land `tests/golden/dockerfile-diffs/README.md` naming the regeneration procedure.
- Land the Phase-7 ADR amendment (AC-16.a) widening `NotApplicableReason` Literal in `src/codegenie/transforms/outcomes.py` with the three new reasons; re-run the S6-06 contract-snapshot regeneration and commit the updated snapshot in the same PR.

### Refactor

- Confirm the four decision-tree predicates are module-level pure functions with dedicated unit tests.
- Pull the digest-pinned FROM-line template (`f"cgr.dev/chainguard/{name}:{tag}@{digest}"`) into a `Final` constant.
- Confirm `_NOT_APPLICABLE_REASONS` and `_WARNING_IDS` are 1:1-parity `frozenset`s validated at import via `raise AssertionError(...)`.
- Confirm the AST-walk fence (`tests/fence/test_dockerfile_swap_no_docker_build.py`) covers BOTH the recipe module AND the engine module — no `subprocess.run`, no `os.system`, no `codegenie.exec.*` imports, no `docker.buildx` attribute chains.
- Optional (rule-of-three deferred): consider extracting a `_PredicateSet` dataclass grouping the four predicates if a second Dockerfile recipe (S10-02's multi-stage refactor) ends up mirroring the shape. Do NOT extract preemptively — Rule 2 (Simplicity First) wins until the third consumer exists.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | NEW — empty shell; later stories' side-effect imports land here. |
| `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` | NEW — the three-way split (`DockerfileBaseImageSwapRecipe` matcher, `DockerfileRecipeEngine` worker, `DockerfileBaseImageSwapTransform(Transform)` data-class) per ADR-0013 + Phase-3 shipped `RecipeProtocol` / `RecipeEngine` / `Transform` contract. Reads injected `ChainguardCatalog`; produces unified diff; registers `Transform` into injected `TransformRegistry`; **no `docker build`**. |
| `tests/unit/transforms/recipes/__init__.py` | NEW (or extend) — test package marker. |
| `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` | NEW — AC-2..AC-13.b suite: Protocol conformance, DI-catalog-difference, two-golden byte-equality, parametrized unparseable-Dockerfile table, warning-emission via `MagicMock`, malformed-catalog-row shrug, Hypothesis metamorphic property. |
| `tests/unit/transforms/recipes/conftest.py` | NEW — fixtures: `alpine_dockerfile`, `debian_slim_dockerfile`, `alpine_bundle`, `debian_slim_bundle`, `seeded_catalog`, `empty_catalog`, `broken_catalog`, `mock_logger`, `cve_9999`. |
| `tests/fence/test_dockerfile_swap_no_docker_build.py` | NEW — AST-walk fence enforcing AC-9 across BOTH the recipe module AND the engine module (no `docker build`, no `subprocess`, no `codegenie.exec` imports, no `docker.buildx` attribute chains). |
| `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` | NEW — pinned exemplar diff for alpine-base swap (AC-14). |
| `tests/golden/dockerfile-diffs/debian-slim-to-chainguard.diff` | NEW — pinned exemplar diff for debian-slim-base swap (AC-14). |
| `tests/golden/dockerfile-diffs/README.md` | NEW — regeneration procedure + `dockerfile-parse` version-pin note (AC-14). |
| `tests/perf/test_dockerfile_recipes.py` | NEW or extend — `test_swap_p99_under_80ms` (AC-15), `@pytest.mark.bench`, includes a 100-iteration warmup. |
| `tests/fixtures/portfolio/node-vulnerable-debian-slim-base/Dockerfile` | NEW — debian-slim-base counterpart to the alpine fixture (S9-01 provided the alpine one). |
| `src/codegenie/transforms/outcomes.py` | EDIT — additive widening of `NotApplicableReason` Literal with the three new Phase-7 reasons (AC-16.a). Requires the Phase-7 ADR amendment authorizing the widening. Also grows the S6-06 contract snapshot. |
| `docs/phases/07-migration-task-class/ADRs/00NN-widen-not-applicable-reason-for-dockerfile-recipes.md` | NEW — Phase-7 ADR amendment authorizing AC-16.a; cites ADR-0001 §Extension-by-addition and the S6-06 snapshot regeneration path. Number assigned at story-execution time. |
| `pyproject.toml` | Confirm `dockerfile-parse` is present as a runtime dep (locked-row #9 of byte-edit allowlist; Phase 7 ADR-0009). If S9-01 didn't already add it, add it here; otherwise no edit. |

## Out of scope

- **Multi-stage refactor (moving shell-using `RUN` to builder stage)** — S10-02. This story only handles single-FROM swap + light runner-stage adjustments. If a Dockerfile has shell-using `RUN` in the runtime stage, `applicability()` may still return `Applies` (the swap is independent); S10-02's recipe runs later as a separate transform and addresses the shell-relocation.
- **`docker build` execution** — explicitly NOT this recipe's job. `DistrolessBuildGate` (S10-04) runs `docker buildx build --target=runtime` inside the microVM.
- **`DockerfilePolicyGate` invariant checking** — S10-03. The recipe produces a diff; the policy gate evaluates it.
- **`tests/integration/test_gates_register_phase7.py`** — that story's territory (S10-05's integration sweep).

## Notes for the implementer

- **Three-way split is not an option — it is the sanctioned Phase-3 shape.** Read `src/codegenie/transforms/engines/npm_lockfile.py` and `src/codegenie/transforms/engines/openrewrite.py` before you write a line: both ship the exact matcher (`RecipeProtocol`) / worker (`RecipeEngine`) / output-data-class (`Transform`) triple this story requires. Attempting to fold all three into one class — the pre-validation draft's shape — would force adding methods to the `Transform` ABC, which is a Phase-3 ADR-0001 contract amendment that also regenerates the S6-06 snapshot. Do not go there. Rule 11 (match the codebase's conventions) applies with force here — two Phase-3 sibling engines already exist to copy from.
- **CVE reaches the recipe via `applies(cve, bundle)`, NOT via `ApplyContext.cve_id`.** The pre-validation draft assumed `ApplyContext` carried `cve_id` and `repo_root`; it does not (`src/codegenie/transforms/apply_context.py:126-141`). The Phase-3 `RecipeProtocol.applies(cve: VulnerabilityRecord, bundle: Bundle)` signature is how CVE reaches the matcher. The `RecipeEngine.apply(repo: SandboxedPath, plan: ApplicationPlan, capability)` signature is how repo path + plan reach the worker. If you find yourself editing `ApplyContext` to add fields, stop — that's an ADR-0001 amendment, out of scope for this story.
- **`RecipeOutcome`, not `TransformOutcome`.** The umbrella union shipped in `outcomes.py` is `RecipeOutcome = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, ...]`. `TransformOutcome` does not exist. `Applied` carries `{kind, transform_id, plugin_id, recipe_id}` — the produced `Transform` is looked up via `TransformRegistry.get(transform_id)`, mirroring ADR-0014's discipline (`RecipeEngine.apply` returns a bare `RecipeOutcome`; the `Transform` is surfaced via the constructor-injected `TransformRegistry`).
- **The three Phase-7 `NotApplicableReason` strings require a Phase-7 ADR amendment (AC-16.a).** `NotApplicableReason` currently ships as a seven-member Literal at `src/codegenie/transforms/outcomes.py:98-106`; the three Phase-7 strings (`no_distroless_counterpart`, `dockerfile_parse_failed`, `base_image_already_distroless`) are not in it. Land the ADR amendment authorizing the additive widening BEFORE writing the recipe — the widening also grows the S6-06 contract snapshot. Do NOT invent a Phase-7-only `MigrationApplicabilityReason` alias sitting alongside — that would fragment the taxonomy and defeat the sum-type discipline.
- **`dockerfile-parse` is the recipe engine. NOT OpenRewrite.** ADR-0013 is the canonical citation. Do not reuse Phase 3's `OpenRewriteRecipeEngine` scaffold for this story — the engine split is deliberate. Adding the JVM cold-start cost would blow the p99 ≤ 80 ms budget and contradict the ADR.
- **No `docker build` in the recipe — period.** AC-9's AST-walk fence is the mechanical enforcement. Building the migrated image is `DistrolessBuildGate`'s responsibility (S10-04) inside the microVM. If you find yourself reaching for `subprocess.run(["docker", "buildx", ...])` here, stop — that's a gate, not a recipe.
- **DI over module-level state.** The Chainguard catalog is loaded once at plugin-load time by `api.py` (S8-03) and injected into BOTH collaborators' constructors (`DockerfileBaseImageSwapRecipe`, `DockerfileRecipeEngine`). Do NOT call `load_chainguard_catalog()` from within `applies()` or `apply()` — that would re-load the YAML on every invocation and break determinism if the file mutated mid-workflow. The DI-catalog-difference test (AC-3) is the mechanical pin for this discipline: two recipe instances built with different catalogs MUST return different `applies()` outcomes for the same `(cve, bundle)` — enforceable only if there is no module-level singleton.
- **`base_image_already_distroless` is a `NotApplicable` reason, not an error.** Operators may double-apply (e.g., re-running the workflow after a partial success). The recipe shrugs and returns `NotApplicable` — no exception, no warning. The `DistrolessVulnProvenanceAdapter` (S4-03) carries the same reason string; consider sharing it via a `Final` constant in `plugins/distroless-migration--node--npm/_constants.py` if it's referenced in more than two places.
- **Unified diff via `difflib.unified_diff`.** Use the original Dockerfile text as the `a` side and the rebuilt-via-`dockerfile-parse` text as the `b` side. Diff context = 3 lines (the default). The golden file is byte-pinned; if `dockerfile-parse`'s output formatting shifts between minor versions, the golden may need a refresh — pin the `dockerfile-parse` version in `pyproject.toml` (and `uv.lock`).
- **`TransformProvenance.capability_use_id`** must be populated from `ctx.capabilities.use(...)` (Phase 3 S1-04 framing). Phase 3 ships `CapabilityBundle` as an empty shell; S4-05 adds `use()`; this story may need to skip the audit-anchor line until S4-05 ships — note `# TODO: capability_use_id once S4-05 lands` and use a sentinel `EventId("00" * 32)`. If S4-05 has already landed by the time this story runs, populate honestly.
- **`_WARNING_IDS` import-time validation.** Use `raise AssertionError("...")` — NOT bare `assert` (banned by the `forbidden-patterns` hook). Mirror Phase 0/1 probe convention.
- **Edge cases the golden does NOT cover** (deferred to S10-02): shell-using `RUN` lines (those move to a builder stage); multi-FROM with three+ stages; `COPY --from=base` referencing a now-removed stage. Document these explicitly in the recipe's module docstring as "see S10-02 for multi-stage refactor."
- **p99 ≤ 80 ms** is the budget. `dockerfile-parse` is fast (~5 ms on a simple Dockerfile); the `difflib.unified_diff` is fast; the catalog lookup is dict access (O(1)). The headroom is comfortable. If perf regresses, suspect: (a) repeated catalog loads (DI it); (b) `dockerfile-parse` instantiation in a hot loop (instantiate once per `apply()`).
- **Match the codebase's convention.** Phase 3's `npm_lockfile_pin.py` is the closest sibling — mirror its file layout, its `applicability()` ladder, its `TransformOutcome` construction shape. Disagreement is a separate conversation; conformance > taste (global Rule 11).
