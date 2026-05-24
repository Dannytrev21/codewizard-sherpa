# Validation report: S7-04 — `plugin.yaml` + skill templates

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-04 ships Phase-4 calibration knobs (RAG thresholds, budget caps, embeddings model, cassette dir) as plugin-scoped configuration plus two skill templates, with fail-loud schema validation at plugin-load time. The original draft was structurally sound in **goal** but consistently wrong in **prescription**: it (a) prescribed extending the kernel `PluginManifest` even though `src/codegenie/plugins/manifest.py:42-46` explicitly forbids that without an ADR; (b) invented a `PluginManifestError` / `load_plugin_manifest` API that contradicts the existing `Result[PluginManifest, ManifestError]`-returning kernel loader; (c) invented a `requires: [rag_capabilities, llm_capabilities]` field that has no home in `ManifestRequirements`; (d) prescribed skill `.md` frontmatter (`kind:`, `task_class:`, `language:`, `build_system:`) that the existing `Skill` Pydantic model (`extra="forbid"`) rejects field-by-field; (e) used `language: node` where Phase-3 S7-01 hardening pinned `languages: javascript`; (f) had no `Depends on:` for Phase-3 S7-01 (which ships the actual plugin directory — not yet on disk today). All six blockers were resolved by pivoting to **plugin-local config**: each plugin owns its own Pydantic models loaded by its own `api.py`. The kernel stays frozen. This honors ADR-0043 ("extension by addition — no silent edits"), is the strictly less-risky path, and is the right choice at the rule-of-three threshold (Phase 4 is the **1st** plugin-local-config consumer; Phase 7 distroless will be the 2nd; the kernel `@register_plugin_config_block` registry is a Phase-7+ rule-of-three concern, not this story's). Test plan was also rewritten — substring-match exception assertions replaced with `Result`-tagged-union `field_errors` assertions; AC-9's vacuous AST-walk for hardcoded literals (S5-02 and S2-05 are already DI'd, so the walk passes trivially in their own modules) replaced with an end-to-end runtime witness asserting that mutating `phase4.yaml`'s `high_floor` value changes `BandClassifier` behavior.

## Findings by critic

### Coverage critic

- **F1 — Boundary `==` ambiguity** (harden, AC-5b). Need `==` rejection, `> 1.0`, `< 0.0`, `NaN` rows.
- **F2 — Budget cap consistency rules missing** (harden, AC-5c). Need `per_call > workflow_cap`, negative-int, non-int rejection rows.
- **F3 — Skill-file body/frontmatter edge cases unspecified** (harden, AC-3/AC-4/AC-5f). Empty file; frontmatter-only; unknown frontmatter keys; wrong `kind` value; BOM/CRLF; non-UTF-8.
- **F4 — `cassettes.dir` validation absent** (harden, AC-1/AC-5). Pin "relative path, no traversal"; existence checked lazily by Recorder, not loader.
- **F5 — Embeddings model name not validated as well-formed** (nit, AC-5d). Reject empty/whitespace-only/strippable strings.
- **F6 — "Diagnostic message that names the offending key" is vague** (harden, AC-6). Pin dotted-path convention.
- **F7 — AST-walk AC is weak as written** (harden, AC-8). S5-02 + S2-05 already DI'd; the walk catches nothing in those modules. Real risk is the construction-site wiring.
- **F8 — `requires:` vs Phase-3 `requirements: ManifestRequirements` contradiction** (block, AC-2). No `requires` field exists; the "capability" concept has no manifest-schema home.
- **F9 — `additionalProperties` / extra-keys policy unspecified** (harden, AC-1/AC-5). Pin `extra="forbid"` at every Phase4Config sub-model.
- **F10 — Test-fixture brittleness** (nit, AC-7). Single-source-of-truth constants.

### Test-Quality critic

- **F1 — Wrong error type / wrong loader API** (block, all tests). `PluginManifestError` does not exist; real API is `PluginManifest.from_yaml -> Result[..., ManifestError]`; `from_yaml` never raises.
- **F2 — Substring matching against bare key name is mutation-blind** (harden, parametrize block). Need exact dotted-path membership + distinguishing token.
- **F3 — Threshold-ordering rule undertested at the boundary** (harden, AC-5b). Need `==` cases, `+1e-12` cases, Hypothesis property.
- **F4 — `test_loads_phase4_config_with_exact_values` tests parser identity, not intent** (harden, lines 112-120). Use non-arch values in unit test; pin arch values in integration smoke only.
- **F5 — Integration smoke is precondition-blocked TODAY** (block, AC-7). `plugins/vulnerability-remediation--node--npm/` doesn't exist; story has no `Depends on:` Phase-3 S7-01.
- **F6 — Skill-file test is a literal `...` stub** (block, lines 147-151). AC-3/4/5e/5f have zero corresponding red test.
- **F7 — AST-walk acceptance criterion is hand-wavy and trivially circumventable** (harden, AC-8). `Decimal("0.85")`, `float("0.85")`, `17/20`, IEEE bit pattern. Need concrete module list + node-type list + parameter-introspection backstop.
- **F8 — No round-trip / metamorphic test** (nit). Defense against asymmetric serializers.
- **F9 — No test that consumers actually receive injected values** (block, AC-9). The AST-walk passes while the value never flows. Need behavioral test that mutates YAML and observes downstream behavior change.
- **F10 — Float equality on `1.50` is fragile** (nit, integration smoke line 164). Inconsistent `pytest.approx` use; consider `Decimal` for money.

### Consistency critic

- **CN-1 — `requires:` field does not exist on `PluginManifest`** (block, AC-2). Real field is `requirements: ManifestRequirements{external_tools, optional}`. With `extra="forbid"`, `requires:` is a hard `SchemaViolation`. No "capability" concept exists.
- **CN-2 — Adding top-level `fallback:` block requires explicit ADR per `manifest.py` docstring** (block, AC-1/AC-5). The kernel forbids escape hatches; no Phase-4 ADR authorizes the edit.
- **CN-3 — `PluginManifestError` is fictional; real API is `Result[..., ManifestError]`** (block, AC-5/TDD plan). Tests rewritten.
- **CN-4 — Skill `.md` frontmatter contradicts existing `Skill` model** (block, AC-3/AC-4). Existing `Skill` has `id, applies_to_tasks, applies_to_languages`; story uses `kind, task_class, language, build_system`. None of those fields exist; all would be rejected by `extra="forbid"`. There is no `instruction_template` kind in Phase 2.
- **CN-5 — `language: node` contradicts Phase-3 S7-01 hardening pin `javascript`** (block, AC-3). Two stories disagree on the same language token.
- **CN-6 — No `Depends on: Phase-3 S7-01` despite touching `plugins/vulnerability-remediation--node--npm/plugin.yaml`** (harden, header). Plugin dir doesn't exist.
- **CN-7 — AC-9 (AST-walk for hardcoded literals) is vacuous and hides the real wiring gap** (harden, AC-9). S5-02/S2-05 already DI'd; AST walk in those modules passes trivially. Real wiring belongs to FallbackTierPlanRecipeEngine (Phase-4 S7-01).
- **CN-8 — `Phase4Config` Pydantic model + skill-frontmatter validator have no architectural home named** (harden, Implementation outline step 2). Story leaves implementer to guess between kernel-edit and plugin-local.
- **CN-9 — TDD fixture is missing required `scope:` and `contributes:` fields** (nit, lines 94-96). Fixture is incomplete vs the real `PluginManifest` shape.
- **CN-10 — Cassette path `tests/cassettes/anthropic` is consistent** (no action).
- **CN-11 — AC-7 path consistent with convention** (no action).

### Design-Patterns critic

- **DP-01 — Kernel Frankenstein anti-pattern** (block, AC-1/AC-5). Phase 4 edits `PluginManifest` → Phase 7 edits it for distroless → Phase 8 for hot-views → 12-field god-model. **Plugin-local config path** is the structural fix.
- **DP-02 — Skill `kind` field collides with frozen Skill model** (block, AC-3/AC-4). Drop `kind`; both files are plain `Skill`s differentiated by `id`. `@register_skill_kind` registry is a rule-of-three deferral.
- **DP-03 — Specification pattern at threshold from day one** (harden, AC-5/refactor). Six rejection rules already past the story's own ">5 = factor" threshold. Start with a `_VALIDATORS: tuple[Validator, ...]` table.
- **DP-04 — Domain primitives missed** (harden, AC-1). `EmbeddingModelId` newtype (ADR-0007 calls out model digests). `Decimal` (not `float`) for dollars.
- **DP-05 — Runtime witness should be primary, AST walk secondary** (harden, AC-8). Mutate `phase4.yaml` → reload → BandClassifier behavior changes → end-to-end value flow.
- **DP-06 — Functional core / imperative shell unnamed** (nit, Implementation outline). Pure `_validate` + impure `_load` shell.
- **DP-07 — Loader error type contract drift** (harden, TDD plan). Kernel loader returns `Result`; story regresses to `pytest.raises`. Rewrite as `Result`/`Err` assertions.
- **DP-08 — Rule-of-three deferral note** (nit, Notes). Phase 4 is 1st plugin-local-config consumer; document deferral so Phase 7's author finds the precedent.

## Conflict resolutions

- **DP-01 vs Coverage F8 vs Consistency CN-1, CN-2** — all three critics flagged the kernel-extension path. Consistency wins (source of truth: `manifest.py:42-46` + ADR-0043). Resolution: pivot story to plugin-local `Phase4Config` Pydantic model loaded by `plugins/.../api.py`. Kernel stays frozen. Resolves CN-1, CN-2, DP-01 in one move and dissolves F8 (no "capabilities" field needed on kernel manifest because capability requirements are an ADR-architecture concept, not a manifest field).
- **DP-02 vs Coverage F3 vs Consistency CN-4** — three critics on skill-file shape. Consistency wins. Resolution: drop `kind:` entirely; both files are plain `Skill`s with existing `id`/`applies_to_tasks`/`applies_to_languages` frontmatter. The `leaf-llm-instruction` body is structurally a skill — Phase 4 doesn't need a new kind. If Phase 5 needs a third kind, do `@register_skill_kind` then (rule of three).
- **F7 vs DP-05 vs CN-7** — three critics on AST-walk. Test-Quality wins on phrasing ("specify modules + node types + parameter introspection"), Design-Patterns wins on primacy ("runtime witness is primary, AST walk is defense-in-depth"). Resolved: AC-8 split into AC-8a (runtime witness, primary) and AC-8b (AST walk, defense-in-depth) with the walk scope made concrete and a parameter-introspection backstop added.

## Edits applied

### Edit 1 — Validation notes block added (header)

Inserted under the Status line. Documents pivot to plugin-local config, dropped `requires:`, dropped `kind:`, fixed `language: javascript`, added Phase-3 S7-01 dependency.

### Edit 2 — `Depends on:` line extended (header)

Added `Phase-3 S7-01 (ships the plugin directory + base manifest at `plugins/vulnerability-remediation--node--npm/`)`. Without this, the story is BLOCKED today.

### Edit 3 — Goal rewritten

Pivoted from "`plugin.yaml` carries Phase-4 keys + load-time schema check on the kernel manifest" to "plugin-local `Phase4Config` Pydantic model (loaded by the plugin's own `api.py` from a sibling `phase4-config.yaml`) carries the calibration knobs; kernel `PluginManifest` is **not** edited."

### Edit 4 — AC-1 rewritten

Was: "extend kernel `plugin.yaml` with a `fallback:` block." Now: "ship `plugins/.../phase4-config.yaml` parsed by a plugin-local `Phase4Config(BaseModel, frozen=True, extra="forbid")`." Kernel `PluginManifest` untouched.

### Edit 5 — AC-2 rewritten (was the `requires:` blocker)

Was: "`requires: [rag_capabilities, llm_capabilities]`." That field doesn't exist on `ManifestRequirements`. New AC-2: the plugin's `api.py` declares the capabilities it consumes via plugin-side documented constants (`_CONSUMES_RAG_CAPABILITIES = True`) AND the plugin's existing `requirements.optional` tuple lists the external binaries (no schema invention).

### Edit 6 — AC-3 + AC-4 rewritten (skill frontmatter)

Was: `kind: skill`, `kind: instruction_template`, `task_class:`, `language: node`, `build_system: npm` — none of which match the existing `Skill` model. Now: both files are plain `Skill`s with `id: vuln-major-bump-vulnerability-remediation-javascript-npm` / `id: leaf-llm-instruction-vulnerability-remediation-javascript-npm`, `applies_to_tasks: [vulnerability-remediation]`, `applies_to_languages: [javascript]`. Skill model unchanged. Language token `javascript` per Phase-3 S7-01.

### Edit 7 — AC-5 rewritten with full Specification table

Was: 5 rules. Now: 12 rules (`extra="forbid"` rejects unknown keys; `high_floor == degraded_floor` rejected; NaN rejected; out-of-`[0,1]` rejected; `per_call_max_tokens > max_tokens_per_workflow` rejected; negative ints rejected; empty/whitespace embeddings model rejected; cassette dir must be relative + no `..` traversal; empty skill file rejected; frontmatter-only skill rejected; unknown skill frontmatter key rejected; wrong-shape `applies_to_tasks` rejected). Each rule is a named `_validate_<rule>(config) -> Result[None, Phase4ConfigError]` function — Specification pattern from the start.

### Edit 8 — AC-6 rewritten

Was: "diagnostic message that names the offending key." Now: error type is `Phase4ConfigError(BaseModel, frozen=True, extra="forbid")` — a tagged union mirroring `ManifestError`'s shape; the diagnostic includes the **dotted path from `Phase4Config` root** (`thresholds.high_floor`, `budget.per_call_max_tokens`, `skills.vuln_major_bump.frontmatter.applies_to_tasks`) and the absolute file path.

### Edit 9 — AC-7 rewritten (integration smoke)

Was: reads `plugins/.../plugin.yaml`, fails before Phase-3 S7-01 lands. Now: synthesizes a complete plugin directory under `tmp_path` with the real `Phase4Config` shape; round-trips through `load_phase4_config(path)`; ALSO `pytest.skip`s with a loud reason if `plugins/vulnerability-remediation--node--npm/` doesn't exist (executor uses the skip as a tracking signal).

### Edit 10 — AC-8 split: 8a (runtime witness, primary) + 8b (AST walk, defense-in-depth)

Was: vague AST walk that S5-02/S2-05 trivially pass. Now: AC-8a (primary): mutate `phase4-config.yaml`'s `high_floor` to `0.99`, reload through the plugin's `api.py` (Phase-4 S7-01 wiring), drive a known-`0.86` candidate through `BandClassifier`, assert classification flips from `RagHit` to `RagDegraded`. AC-8b (defense): walk `ast.parse(...)` of the plugin's wiring module + `FallbackTierPlanRecipeEngine.__init__`, assert no `ast.Constant` node with value in `{0.85, 0.65, 250_000, 1.50, 32_000}`. AC-8c (parameter-introspection backstop): `inspect.signature(BandClassifier).parameters['high_floor'].default is inspect.Parameter.empty` (proves the constructor requires the value; no Pydantic-default escape).

### Edit 11 — AC-9 dropped (folded into AC-8)

Was: "S5-02 and S2-05 read these values via the plugin config layer rather than hardcoded constants." Vacuous because S5-02 + S2-05 are already DI'd. The real assertion is AC-8a (runtime witness). Removed as a separate AC; kept as a Note-for-implementer about the wiring location (Phase-4 S7-01's `FallbackTierPlanRecipeEngine.__init__`).

### Edit 12 — TDD plan rewritten

Removed `from codegenie.plugins.manifest import load_plugin_manifest, PluginManifestError`. Replaced with `from plugins.vulnerability_remediation__node__npm.config import load_phase4_config, Phase4ConfigError`. Replaced `pytest.raises(PluginManifestError, match=...)` with `result = load_phase4_config(path); assert isinstance(result, Err); assert isinstance(result.error, Phase4ConfigError); assert "thresholds.high_floor" in result.error.field_errors`. Added Hypothesis property `test_threshold_ordering_property` covering the full `(0, 1)` × `(0, 1)` band. Added round-trip/metamorphic test `test_phase4_config_yaml_roundtrip`. Added the runtime-witness test scaffold for AC-8a. Filled the stub `test_skill_files_validated_at_load` with four concrete tests.

### Edit 13 — Files to touch updated

Removed `src/codegenie/plugins/manifest.py` (kernel stays frozen). Added `plugins/vulnerability-remediation--node--npm/config.py` (new — `Phase4Config` + `load_phase4_config`), `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` (new — the calibration values). Removed `src/codegenie/rag/confidence.py` and `src/codegenie/fallback/budget.py` from the files-to-touch (S5-02 + S2-05 already shipped them with DI; the wiring is Phase-4 S7-01's responsibility, not this story's).

### Edit 14 — Notes for the implementer extended

Added: rule-of-three deferral note (Phase 4 is the 1st plugin-local-config; defer `@register_plugin_config_block` registry until Phase 7+); functional core / imperative shell named split; `Decimal` for money; `EmbeddingModelId` newtype consideration; explicit cross-reference to Phase-3 S7-01 validation CN-8 for the `javascript` language token.

## Verdict rationale

The story's **goal** ("ship Phase-4 calibration as config-not-code with fail-loud load-time validation") is sound and traces to ADR-0008's load-bearing commitment. The story's **prescription** was wrong in six independent ways, but all six dissolved at the design root cause: **the prescription tried to extend the kernel `PluginManifest` instead of using plugin-local config**. Pivoting to plugin-local config eliminates CN-1, CN-2, CN-3, DP-01 in one design move; CN-4 + DP-02 dissolve by aligning skill frontmatter to the existing `Skill` model; CN-5 dissolves by using `javascript`; CN-6 dissolves by adding the Phase-3 S7-01 dependency. The remaining `harden`/`nit` findings became surgical AC rewrites and a Specification table. Verdict: **HARDENED** with substantial rewrites that the implementer can now execute against a coherent kernel without inventing new APIs.

## Recommended next step

`phase-story-executor` to implement. **Precondition**: Phase-3 S7-01 (plugin directory scaffold) must have landed; AC-7 will pytest.skip until then. If S7-01 hasn't landed when the executor picks up this story, the executor should pause and surface — do not implement against a non-existent plugin directory.
