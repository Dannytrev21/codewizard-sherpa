# Validation report — S10-01 `DockerfileBaseImageSwapTransform` + `dockerfile-parse` AST manipulation

**Story:** [`docs/phases/07-migration-task-class/stories/S10-01-dockerfile-base-image-swap-recipe.md`](../S10-01-dockerfile-base-image-swap-recipe.md)
**Validator run:** phase-story-validator, 2026-08-15
**Verdict:** **HARDENED** — four independent Phase-3-contract-surface blockers found, all patched in place; six additional coverage / test-quality / design-pattern hardenings applied.

## Context brief (Stage 1)

- **What the story promises.** A pure-Python `dockerfile-parse`-driven Dockerfile base-image swap recipe under `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py`. Reads the Chainguard catalog via DI, produces a deterministic byte-golden unified diff, does not invoke `docker build`, lands in p99 ≤ 80 ms across 1000 trials.
- **What Phase 7's exit criteria demand.** From [`High-level-impl.md` §Step 10] + [`phase-arch-design.md §Component design §11`]: two deterministic Dockerfile recipes extending Phase 3's `Transform` ABC, `dockerfile-parse` (not OpenRewrite), no `docker build` in the recipe, p99 ≤ 80 ms for the swap, honest failure behavior on unparseable Dockerfiles or catalog misses.
- **What the arch + ADRs constrain.**
  - [ADR-0013](../../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) — `dockerfile-parse` is the engine; OpenRewrite is off-limits for Phase 7's Dockerfile recipes.
  - [ADR-0009](../../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — the byte-edit allowlist authorises `pyproject.toml` gaining `dockerfile-parse` (row #9). No other Phase-0–6.5 file edits without an allowlist row.
  - [Phase-3 ADR-0001](../../../03-vuln-deterministic-recipe/ADRs/0001-ship-phase5-contract-surface-by-name.md) — the `Transform` / `ApplyContext` / `RecipeOutcome` contract surface is FROZEN. Adding methods to `Transform`, adding fields to `ApplyContext`, or renaming any `Applied` field is a contract amendment that regenerates the S6-06 snapshot.
  - [Phase-3 ADR-0014](../../../03-vuln-deterministic-recipe/ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) — `RecipeEngine.apply` returns a bare `RecipeOutcome`; the produced `Transform` is surfaced via a constructor-injected `TransformRegistry`, never as a tuple.
  - [Amendment A](../../final-design.md) — this story is deferred behind S13–S15 (gather) + S16-01 (refusal taxonomy) + S16-02 (recipe amendment adds three slice inputs). Story explicitly says do-not-execute-before-those-land.
- **What is true in the shipped Phase-3 code at validation time** (grounded, not inferred from the story):
  - `src/codegenie/transforms/transform.py:64-95` — `Transform` is an ABC with FOUR class-level attribute annotations only (`transform_id`, `diff_bytes`, `files_changed`, `provenance`). ZERO methods. The docstring is explicit: "Adding an attribute to `Transform` itself requires a Phase-3 ADR amendment + S6-06 snapshot regeneration."
  - `src/codegenie/transforms/apply_context.py:126-141` — `ApplyContext` fields: `workflow_id`, `attempt`, `prior_attempts`, `capabilities`. `model_config = ConfigDict(frozen=True, extra="forbid")`. NO `cve_id`. NO `repo_root`.
  - `src/codegenie/transforms/outcomes.py:98-106` — `NotApplicableReason = Literal["PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE", "OVERRIDES_AMBIGUOUS", "RECIPE_CATALOG_MISS", "ALL_RECIPES_NOT_APPLICABLE", "NO_RECIPES_REGISTERED", "CVE_NOT_IN_DEPENDENCY_SET"]`. The three Phase-7 reasons the story wants (`no_distroless_counterpart`, `dockerfile_parse_failed`, `base_image_already_distroless`) are absent.
  - `src/codegenie/transforms/outcomes.py:249-259` — `Applied` fields: `kind`, `transform_id`, `plugin_id`, `recipe_id`. No `.transform` object, no `.diff_bytes`, no `.rendered_text`. `TransformOutcome` as a name does not exist; the umbrella is `RecipeOutcome`.
  - `src/codegenie/transforms/recipe_engine.py:95-117` — `RecipeProtocol.applies(cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies`. That is the sanctioned CVE-reaches-recipe path.
  - `src/codegenie/transforms/engines/npm_lockfile.py:520-539, 549-618` — sibling Phase-3 implementation: `NpmLockfileTransform(Transform)` data-class with keyword-only `__init__`; separate `NpmLockfileRecipeEngine` class with constructor-injected `SubprocessJail` + `TransformRegistry`; `async def apply(repo, plan, capability) -> RecipeOutcome`.
  - `src/codegenie/transforms/engines/openrewrite.py:196-241` — the OTHER sibling: `DockerfileBaseImageTransform(Transform)` with a `.create(diff_bytes, files_changed, provenance)` smart constructor that computes `transform_id = TransformId(blake3.blake3(diff_bytes).hexdigest())` and rejects empty inputs.

## Stage 2 — Critic findings

Four lenses were applied inline. The Phase-3 shipped code was ground-truth-verified for every finding tagged `[block]`; findings tagged `[harden]` / `[nit]` are quality-of-implementation observations.

### 2A — Coverage

| # | Finding | Severity |
|---|---|---|
| C1 | AC-6 goldens only the alpine base. The catalog also supports debian-slim (AC-4 names both); leaving debian-slim ungoldened means half the migratable-base surface is unverified. | harden |
| C2 | AC-11's "heredoc or ARG-driven FROM" is a single bucket. `dockerfile-parse` also trips on `# syntax=` BuildKit frontmatter above the first `FROM` — a real-world regression risk in modern Dockerfiles. A three-fixture parametrized table (heredoc / ARG-FROM / BuildKit-frontmatter) is the mutation-resistant shape. | harden |
| C3 | Missing coverage: what happens if the catalog row itself is malformed (missing `digest`, empty `digest`, wrong shape)? Original ACs don't specify. Silent `KeyError` at run-time is the failure mode this closes. | harden |
| C4 | Missing coverage: no metamorphic pair anywhere. `(dockerfile, catalog, cve) → Applies` with the cve swapped to an unknown value → `NotApplies(no_distroless_counterpart)` is the natural invariant Hypothesis can pin. | harden |
| C5 | AC-15's p99 bench has no warmup — the first iteration pays the import + class-instantiation cost and drags the p99 upward artificially. A 100-iteration warmup before the 1000-iteration bench is the standard shape. | nit (rolled into AC-15 rewrite) |
| C6 | AC-14 says "updating the golden requires a code-review note" but does not specify how to regenerate the golden deterministically. A stale golden after a `dockerfile-parse` bump has no rescue path. | harden |

### 2B — Test Quality

| # | Finding | Severity |
|---|---|---|
| T1 | `test_swap_apply_matches_golden_diff` is a single-row byte-equality test. A dumb identity function `def apply(x): return golden_bytes` would pass. Mutation-resistance requires either (a) parametrization over multiple (input, golden) rows, or (b) a property-based test asserting invariants (e.g. "no non-FROM line changed except added USER/ENTRYPOINT rewrites"). AC-6 rewrite adds (a) via the alpine+debian-slim parametrized golden. | harden |
| T2 | `test_swap_is_idempotent` uses `first.rendered_text` — but `Applied` has no `.rendered_text` field. The test does not compile against the shipped Phase-3 code. Idempotence needs a different observable: re-materialising the swap onto disk and re-running `applies()` should yield `NotApplies(base_image_already_distroless)`. That IS the observable idempotence signature. | **block** |
| T3 | AC-3 promises a DI-different-catalog test but the TDD plan doesn't ship one. Added `test_di_catalog_difference`. | harden |
| T4 | AC-11 says a warning event is emitted to the plugin logger — no TDD-plan test verifies emission. Added `MagicMock`-based assertion pattern to the parametrized unparseable-Dockerfile test. | harden |
| T5 | No test at all for Protocol conformance (`isinstance(recipe, RecipeProtocol)`, `isinstance(engine, RecipeEngine)`, `isinstance(tx, Transform)`). These are one-liners with high mutation-resistance value. Added AC-2 rewrite + three conformance tests. | harden |
| T6 | Original TDD plan constructs `ApplyContext(workflow_id=..., cve_id=..., repo_root=..., capabilities=...)` — will `ValidationError` on `extra="forbid"` (see `apply_context.py:136`). Every downstream test in the TDD block fails at import time before any real logic runs. | **block** |

### 2C — Consistency

| # | Finding | Severity |
|---|---|---|
| K1 | AC-2 says `DockerfileBaseImageSwapTransform(Transform)` "implements `applicability(ctx) -> Applicability` + `apply(ctx) -> TransformOutcome`." But `Transform` is an attributes-only ABC per `src/codegenie/transforms/transform.py:64-95` — the docstring is explicit that adding attributes/methods is a Phase-3 ADR-0001 amendment that regenerates the S6-06 snapshot. Adding two methods is a bigger surface change than adding an attribute. The sibling Phase-3 shape (npm_lockfile.py, openrewrite.py) splits the concern into `RecipeProtocol` (matcher) + `RecipeEngine` (worker) + `Transform` (data-class output). | **block** |
| K2 | AC-4 references `ctx.cve_id`. `ApplyContext` has no `cve_id` field (`apply_context.py:126-141`); `extra="forbid"` blocks its addition at construction time. The sanctioned Phase-3 CVE-reaches-recipe path is `RecipeProtocol.applies(cve: VulnerabilityRecord, bundle: Bundle)` — see `recipe_engine.py:95-117`. | **block** |
| K3 | AC-6 / AC-10 reference `TransformOutcome.Applied(diff)` and `outcome.transform.files_changed`. `TransformOutcome` doesn't exist — the umbrella is `RecipeOutcome`. `Applied` (`outcomes.py:249-259`) has NO `.transform` object; it carries `{kind, transform_id, plugin_id, recipe_id}` and defers to `TransformRegistry.get(transform_id)` for the `Transform` instance per ADR-0014. | **block** |
| K4 | AC-4 lists three `NotApplicable` reason strings — `no_distroless_counterpart`, `dockerfile_parse_failed`, `base_image_already_distroless`. None appear in the `NotApplicableReason` Literal (`outcomes.py:98-106`). Widening is a Phase-3 ADR-0001 additive contract change that regenerates the S6-06 snapshot. Story cites ADR-0001 as "honored" but silently violates it. Note: the arch design's `UnknownReason` Literal (`phase-arch-design.md:1103-1110`) DOES include `dockerfile_parse_failed` and `base_image_already_distroless` — but that is a distinct `Provenance.reason` type; the two taxonomies must not be conflated. | **block** |
| K5 | AC-5's `_WARNING_IDS` set only lists TWO of the three `NotApplicable` reasons — `no_distroless_counterpart` and `dockerfile_parse_failed`; `base_image_already_distroless` is missing. AC-11 says a warning is emitted for the parse failure; if any of the three reasons emit warnings, all three should have IDs (1:1 parity). Otherwise the operator gets warning telemetry for two failure paths and silence for the third. | harden |
| K6 | Story's `Depends on` lists S8-03 + S9-01 only. Real dependencies also include: Phase-3 S5-01 (`RecipeProtocol` / `RecipeEngine` surface) + Phase-3 S5-01b (`TransformRegistry`) + the yet-unwritten Phase-7 ADR amendment authorising the `NotApplicableReason` widening. | harden |
| K7 | Amendment A refusal-taxonomy boundary is not called out. Under Amendment A, some "the recipe should refuse" outcomes become `PendingHumanReview(refusal=Refused*)` variants (S16-01), not `NotApplicable`. This story's three `NotApplicable` reasons are all cases where the recipe declines to run (correctly still `NotApplies`); refusals are for cases where the recipe COULD run but shouldn't ship silently (opaque secrets, unclassified native modules). The distinction is real — surface it in Notes for the implementer for downstream clarity when S16-02 runs. | harden |

### 2D — Design Patterns

| # | Finding | Severity |
|---|---|---|
| D1 | Three-way split (matcher / worker / data-class) is the sanctioned Phase-3 shape shipped in TWO sibling implementations (`npm_lockfile.py`, `openrewrite.py`). The story's original single-class-with-methods shape is a departure without ADR authorisation. Rule 11 (match the codebase's convention) applies with force — the sibling files are the canonical reference; the story just needs to mirror them. | harden (elevated to a load-bearing structural resolution via AC-1 + AC-2 rewrites) |
| D2 | Smart constructor for `DockerfileBaseImageSwapTransform` is not just a nice-to-have — the sibling `DockerfileBaseImageTransform.create` (openrewrite.py:219-241) sets the pattern: `.create(diff_bytes, files_changed, provenance)` computes `transform_id` from a BLAKE3 hash of `diff_bytes`, rejects empty inputs. This is the ONE sanctioned Transform-construction path (fenced by an AST walk in the Phase-3 codebase; a similar fence would apply here). Elevate to AC-2(d). | harden |
| D3 | `applies()` as a pure decision tree over four module-level predicates (`_has_catalog_row`, `_dockerfile_parses`, `_base_kind_migratable`, `_already_distroless`) is the functional-core / imperative-shell split CLAUDE.md commits to. Story mentioned it in Refactor as an optional hoist; elevate to AC-4.a. | harden |
| D4 | `TransformRegistry` surfacing (ADR-0014) not mentioned anywhere in the story. Phase-7 recipes must honor the same discipline — the engine's constructor takes `transform_registry: TransformRegistry`; the produced `Transform` is `register`-ed into it; `Applied` carries only the `transform_id` lookup key. Original AC-10 read the `.diff_bytes` off `outcome.transform.diff_bytes` — a shape that doesn't exist. Rewritten AC-10 goes via `transform_registry.get(outcome.transform_id).files_changed`. | **block** (folded into K3's resolution) |
| D5 | Consider a `@register_recipe_engine(TransformKind)` sibling registry mirroring `@register_dep_graph_strategy(PackageManager)`? Reject — rule of three not met. Two engines exist today (`NpmLockfileRecipeEngine`, `OpenRewriteRecipeEngine`); a third (this story's `DockerfileRecipeEngine`) is the third occurrence and is a candidate for extraction — but only if S10-02 confirms the shape. Note in the story so the executor doesn't preemptively extract a registry, and revisit at S10-02. | harden (as a Note, not an AC) |
| D6 | Extension seam for future language-plugin distroless migrations (Python, Java, Go). Nothing in this story flags the seam. Not a blocker — rule of three not yet triggered — but consider surfacing as a Note. | nit (folded into D5's note) |

**Nothing tagged `NEEDS RESEARCH`** — Stage 3 skipped. The four blockers are pure Phase-3-code / story-text reconciliation; no external pattern lookup needed. The metamorphic property and the `MagicMock`-logger-emission pattern are both already established in the Phase-3 test suite.

## Stage 4 — Synthesizer resolution

Conflict priority `Consistency > Coverage > Test-Quality > Design-Patterns` produced no cross-critic contradictions. Every blocker (T2, T6, K1, K2, K3, K4, D4) is a Phase-3-code-vs-story-text mismatch — Consistency resolves each one against the shipped code.

### Blocker resolutions

- **B1 — Transform ABC method-addition (K1, D1, D2, D4).** AC-2 rewritten to require the three-way split mirroring `npm_lockfile.py` + `openrewrite.py`. Goal rewritten to name the three collaborators explicitly. Notes for the implementer opens with "Three-way split is not an option — it is the sanctioned Phase-3 shape."
- **B2 — ApplyContext.cve_id / repo_root (K2, T6).** All ACs referencing `ctx.cve_id` / `ctx.repo_root` rewritten to use the Phase-3 signatures: `applies(cve, bundle)` for CVE reach, `apply(repo, plan, capability)` for repo reach. TDD plan rewritten wholesale to remove the `ApplyContext` construction and use fixtures (`alpine_bundle`, `cve_9999`) directly.
- **B3 — TransformOutcome / Applied.transform (K3, T2).** AC-6 / AC-10 rewritten to go via `transform_registry.get(outcome.transform_id)`. Idempotence (AC-8) rewritten as an `applies()` observable — re-materialise the swap onto disk, re-run `applies()`, assert `NotApplies(base_image_already_distroless)`.
- **B4 — NotApplicableReason widening (K4).** New AC-16.a explicitly requires a Phase-7 ADR amendment adding the three reasons to the Literal, with the S6-06 snapshot regenerated in the same PR. Files-to-touch adds the ADR row + the `outcomes.py` edit row.

### Hardenings applied

- AC-6 goldens BOTH alpine and debian-slim (C1); parametrized. New fixture `tests/fixtures/portfolio/node-vulnerable-debian-slim-base/Dockerfile` added to Files-to-touch.
- AC-11 rewritten as a three-fixture parametrized table (heredoc / ARG-FROM / BuildKit-frontmatter) (C2). AC-11.a adds warning-emission via `MagicMock` (T4).
- AC-13.a added — malformed catalog row shrugs to `NotApplies`, never raises (C3).
- AC-13.b added — Hypothesis metamorphic property (C4).
- AC-14 requires `tests/golden/dockerfile-diffs/README.md` naming the regeneration procedure + version pin (C6).
- AC-15 rewritten to require a 100-iteration warmup before the 1000-iteration bench (C5).
- AC-3 grew an explicit `test_di_catalog_difference` red test (T3).
- AC-5 widened `_WARNING_IDS` to include `base_image_already_distroless` for 1:1 parity with the three `NotApplies` reasons (K5). Added an import-time invariant test asserting reason-set / warning-ID-suffix parity.
- AC-4.a added — `applies()` is a pure decision tree over four module-level predicates (D3).
- New AC-2(d) requires `DockerfileBaseImageSwapTransform.create` smart constructor mirroring `DockerfileBaseImageTransform.create` (openrewrite.py:219) (D2).
- Depends-on expanded to include Phase-3 S5-01, S5-01b, and the yet-unwritten Phase-7 ADR amendment (K6).
- Notes-for-implementer paragraphs added on: three-way split, `applies(cve, bundle)` CVE path, `RecipeOutcome` (not `TransformOutcome`), ADR amendment sequencing, and Amendment-A refusal-taxonomy boundary (K7).
- Files-to-touch grew: `conftest.py`, second Dockerfile fixture, second golden, `README.md`, `outcomes.py` edit, new ADR row (D2, K3, K6, B4).

### What the validator did NOT do

- Did NOT rewrite the story's Goal or scope — the intent (deterministic Dockerfile base-image swap via `dockerfile-parse`, DI-injected catalog, no `docker build`, ≤ 80 ms p99) is the phase-story-writer's decision and remains authoritative.
- Did NOT commit — humans always merge. The scheduled-task wrapper commits the validation artifacts; the story change itself is a docs-only edit.
- Did NOT touch S16-02 or the Amendment A downstream stories — they extend this story's ACs additively per their own explicit design; the blockers this validator caught (Transform ABC, ApplyContext, TransformOutcome, NotApplicableReason) affect BOTH stories the same way and both will benefit when the ADR amendment lands.
- Did NOT prescribe the ADR amendment's Nygard-format text — that is `/phase-architect`'s job when the executor picks up this story.

## Verdict: HARDENED

The story now compiles against the shipped Phase-3 code. Four load-bearing contract-shape blockers are resolved by wholesale AC + TDD-plan rewrites; six coverage / test-quality / design-pattern hardenings improve mutation resistance and future extensibility. The story is ready for `phase-story-executor` — subject to Amendment A sequencing (S13–S15 + S16-01/S16-02 land first) and the Phase-7 ADR amendment that AC-16.a requires.
