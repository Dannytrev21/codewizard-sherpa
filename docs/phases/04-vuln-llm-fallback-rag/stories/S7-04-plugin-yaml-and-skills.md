# Story S7-04 — `phase4-config.yaml` + skill templates

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** GREEN-partial — 2026-05-26 (phase-story-executor; see [`_attempts/S7-04.md`](_attempts/S7-04.md)). Shipped `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` (arch-default values) + plugin-local `Phase4Config` Pydantic model + tagged-union `Phase4ConfigError` + `load_phase4_config(path) -> Result[Phase4Config, Phase4ConfigError]` loader + 9-named-validator Specification table covering 12 rejection rules + two skill templates parsing cleanly through kernel `_load_one_skill`. 22 schema-rejection + 3 skill-parse + 5 no-defaults + 2 Hypothesis-property + 2 integration smoke = 34 tests green; mypy --strict, ruff, lint-imports (12/12 KEPT). **AC-2 closed in Attempt #2 (2026-05-26)** — shipped kernel `plugin.yaml` + `api.py` with `_CONSUMES_RAG_CAPABILITIES`/`_CONSUMES_LLM_CAPABILITIES` constants + `tsc` admitted to `requirements.optional`; 5 tests pin parse + capability surface. **Still deferred (BLOCKED):** AC-8a (runtime witness — depends on api.py construction site), AC-8b (AST walk — same), AC-8c BandClassifier+LlmInvocationGuard half (Rule 7 conflict surfaced — shipped S5-02 + S2-05 carry arch-literal defaults; honoring AC-8c there is out-of-scope edit of those modules; Phase4Config sub-models DO honor AC-8c — every field required, no Pydantic defaults).
**Effort:** M (was S — schema-rewrite, AST + runtime-witness tests, and dependency on Phase-3 S7-01 raise the effort one notch)
**Depends on:**
- Phase-4 S7-01 — `FallbackTierPlanRecipeEngine` registered as `transforms()['plan']`; this is the wiring site that reads the `Phase4Config` and constructs the `BandClassifier` + `LlmInvocationGuard` with the loaded values (AC-8a runtime witness drives through it).
- Phase-3 S7-01 — `plugins/vulnerability-remediation--node--npm/` directory + base `plugin.yaml` + `api.py` ship here. Until S7-01 lands, this story is **BLOCKED** (AC-7 `pytest.skip`s with a loud reason). As of 2026-05-24, `plugins/` only contains `PLUGINS.lock` + `__init__.py`.
- Phase-4 S5-02 (HARDENED) — `BandClassifier` already takes `(high_floor, degraded_floor)` via constructor injection; this story does not modify it, only wires values into it.
- Phase-4 S2-05 (HARDENED) — `LlmInvocationGuard` already takes `(max_tokens, max_dollars, per_call_max_tokens, event_log)` via constructor injection; same wiring relationship.

**ADRs honored:** ADR-04-0008 (two-threshold band thresholds in plugin-scoped config; calibration is config not code), ADR-04-0010 (budget caps as capability — values live in config), production-ADR-0031 (plugin scoping), production-ADR-0043 (extension by addition — no silent edits to the kernel `PluginManifest`).

## Validation notes (2026-05-24)

Hardened by `phase-story-validator`. Six structural blockers were resolved by a single design pivot — **the calibration values live in a plugin-local `Phase4Config` Pydantic model loaded by the plugin's own `api.py`, NOT by extending kernel `PluginManifest`.** Summary:

- **Plugin-local config, not kernel manifest edit.** `src/codegenie/plugins/manifest.py:42-46` explicitly forbids escape hatches: "Adding a Phase 7 distroless `contributes.containers` field is an explicit, ADR-worthy edit to this file; never flip to `extra='allow'`." Original AC-1 + AC-5 silently assumed such an edit. The pivot honors ADR-0043 and avoids the kernel-Frankenstein anti-pattern (Phase 4 fallback / Phase 7 distroless / Phase 8 hot-views / Phase 15 agentic — each task class would otherwise grow a sibling top-level field in the kernel god-model). Phase 4 is the **1st** plugin-local-config consumer; defer a kernel `@register_plugin_config_block` registry until rule-of-three (likely Phase 7+).
- **`requires:` field dropped (CN-1, F8).** `PluginManifest` has `requirements: ManifestRequirements{external_tools, optional}` — no `requires` and no `capabilities` field. With `extra="forbid"` on the kernel model, `requires:` at YAML top-level hard-fails as `SchemaViolation`. AC-2 was rewritten to declare consumed capabilities as plugin-side documented constants in `api.py`, not as a manifest field.
- **`PluginManifestError` / `load_plugin_manifest` dropped (CN-3, F1, DP-07).** The kernel loader is `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` and **never raises**. The story's plugin-local loader follows the same shape: `load_phase4_config(path) -> Result[Phase4Config, Phase4ConfigError]` where `Phase4ConfigError` is a tagged union mirroring `ManifestError`. Tests assert `isinstance(result, Err)` + dotted-path membership in `result.error.field_errors`, never `pytest.raises`.
- **Skill `kind:`/`task_class:`/`language:`/`build_system:` frontmatter dropped (CN-4, DP-02).** Existing `Skill` Pydantic model (`src/codegenie/skills/model.py`) has `id`, `applies_to_tasks`, `applies_to_languages` with `extra="forbid"`. The story's frontmatter would have been rejected field-by-field. Pivoted: both files are plain `Skill`s differentiated by `id`; `applies_to_tasks: [vulnerability-remediation]`, `applies_to_languages: [javascript]`. If Phase 5 needs a third `kind`, add `@register_skill_kind` then (rule of three) — not now.
- **`language: node` → `language: javascript` (CN-5).** Phase-3 S7-01 hardening pinned the inner languages token to `javascript` (matches Layer A's `LanguageDetection` output). The directory slug `--node--` is operator-readable only. Skill frontmatter now uses `javascript`.
- **Phase-3 S7-01 added to `Depends on:` (CN-6, F5).** Without the plugin directory on disk, every test that round-trips through the real path fails before exercising any rule.
- **Specification pattern from day one (DP-03).** Rejection rule count is now 12 (well past the story's own ">5 = factor" threshold); the Implementation outline starts with a `_VALIDATORS: tuple[Validator, ...]` named-rule table.
- **AST walk demoted, runtime witness promoted (F7, F9, CN-7, DP-05).** S5-02 + S2-05 are already DI'd; an AST walk in those modules catches nothing. The real assertion — "mutating `phase4-config.yaml`'s `high_floor` to `0.99` causes a `0.86`-similarity candidate to flip from `RagHit` to `RagDegraded` end-to-end" — is now AC-8a (primary). AC-8b keeps the AST walk as defense-in-depth, with concrete module list + node-type list. AC-8c adds an `inspect.signature` backstop ("constructor has no default — value must be supplied").
- **Coverage gaps closed:** `==` boundary, NaN, out-of-`[0,1]` thresholds (F1); `per_call > workflow_cap`, negative ints, non-int (F2); empty / frontmatter-only / unknown-key skill files (F3); cassette dir relative + no `..` traversal (F4); empty / whitespace-only embeddings model name (F5); dotted-path diagnostic convention (F6); `extra="forbid"` on `Phase4Config` (F9); single-source-of-truth defaults constant (F10).
- **Tests assert intent, not parser identity (F4).** Unit tests use non-arch values (`0.7`, `0.3`) so a hardcoded `0.85` would fail. Arch-value pinning is in the integration smoke alone.
- **Round-trip / metamorphic test added (F8).** Defends against asymmetric serializers.

Full audit log: [`_validation/S7-04-plugin-yaml-and-skills.md`](_validation/S7-04-plugin-yaml-and-skills.md).

## Context

Phase 4's tuning knobs — RAG thresholds, budget caps, embeddings-model name, cassette directory — live in **plugin-scoped configuration**, not in code. This is the canonical pattern: "calibration is config, not code" (ADR-0008). Phase 4 ships them schema-validated at plugin-load time so a typo or a missing key fails *at startup*, not in the middle of a workflow.

**Design pivot from the original draft (see Validation notes above).** The original story put the Phase-4 keys under a top-level `fallback:` block in the kernel `plugin.yaml`, with validation extending kernel `PluginManifest`. That path is forbidden by `src/codegenie/plugins/manifest.py:42-46` ("an explicit, ADR-worthy edit … never flip to `extra='allow'`"), and across four task classes (vuln / distroless / hot-views / agentic) would grow the kernel into a god-model. The hardened story uses **plugin-local config**: the calibration values live in `plugins/vulnerability-remediation--node--npm/phase4-config.yaml`, parsed by a plugin-local `Phase4Config(BaseModel, frozen=True, extra="forbid")` Pydantic model in the same directory's `config.py`, loaded by the plugin's own `api.py`. The kernel `PluginManifest` is **not** edited. This is the textbook "extension by addition" path (ADR-0043) at the rule-of-three threshold — Phase 4 is the 1st plugin-local-config consumer; the kernel `@register_plugin_config_block` registry is a Phase 7+ concern.

Two skill templates also externalize the LLM-facing instruction surface: `vuln-major-bump.md` (the prompt-cached `system[0]` skill) and `leaf-llm-instruction.md` (the prompt-cached `system[1]` instruction template). Both are **plain `Skill`s** under the existing Phase-2 `Skill` Pydantic model (no `kind:` field, no second loader). They are differentiated by `id`; their bodies are content with a thin frontmatter envelope, not behavior.

The acceptance criteria pin the *exact* values from arch §"Configuration" so that future stories (the calibration smoke test S5-04, the E2E tests S7-06/S7-07, the budget-cap unit tests) read the same constants from a single source-of-truth Python constant (`tests/_constants/phase4_defaults.py`) — not duplicated as literals in N tests.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Configuration` — "Plugin-scoped: thresholds (`high_floor: 0.85`, `degraded_floor: 0.65`), budget caps (`max_tokens_per_workflow: 250000`, `max_dollars_per_workflow: 1.50`, `per_call_max_tokens: 32000`), embeddings model name, cassette directory." (Validator note: arch says "plugin-scoped"; the original story over-specified this to mean "in the kernel `plugin.yaml`." The hardened reading: plugin-scoped means "lives inside the plugin directory" — `phase4-config.yaml` satisfies the arch.)
  - `../phase-arch-design.md §Prompt template structure` — "Externalized in `plugins/vulnerability-remediation--node--npm/skills/`: `vuln-major-bump.md`, `leaf-llm-instruction.md`. Schema-validated at plugin-load time. Three cached system blocks per call."
  - `../phase-arch-design.md §Development view` — `p_skills["skills/vuln-major-bump.md (NEW), leaf-llm-instruction.md (NEW)"]`.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — thresholds live in plugin-scoped config; calibration is config not code; `high_floor=0.85`, `degraded_floor=0.65`.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` — budget caps are capability-bound; values come from plugin-scoped config; `max_tokens=250_000`, `max_dollars=1.50`, `per_call_max=32_000`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — `plugin.yaml` is the kernel manifest format; this story leaves it untouched and ships a sibling `phase4-config.yaml` inside the plugin directory.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — the load-bearing commitment this story's design pivot honors.
- **Source design:**
  - `../final-design.md §Configuration`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Ship `plugin.yaml` (thresholds, budget caps, embeddings model, cassette dir) + schema-validated `skills/{vuln-major-bump,leaf-llm-instruction}.md`; plugin-load schema check fails on missing keys." (Validator note: read "ship `plugin.yaml`" loosely — the **values** ship inside the plugin directory; this story locates them under `phase4-config.yaml` per the design pivot.)
- **Existing code — kernel (do NOT edit):**
  - `src/codegenie/plugins/manifest.py` — kernel `PluginManifest` Pydantic model. Read the docstring lines 42-46 before considering any change. The hardened story does not modify this file.
  - `src/codegenie/plugins/loader.py` — kernel discovery + validation. `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]`; **never raises**.
  - `src/codegenie/skills/model.py` + `src/codegenie/skills/loader.py` — kernel `Skill` model. Fields: `id`, `applies_to_tasks`, `applies_to_languages`, `body_offset`, `body_size`, `body_blake3`; `extra="forbid"`. The two new skill `.md` files conform to this shape unchanged.
  - `src/codegenie/result.py` — `Result`, `Ok`, `Err`. The plugin-local `load_phase4_config` returns `Result[Phase4Config, Phase4ConfigError]`, never raises.
- **Existing code — plugin-side wiring sites:**
  - `plugins/vulnerability-remediation--node--npm/` — does NOT exist yet (`plugins/` contains only `PLUGINS.lock` + `__init__.py` as of 2026-05-24). Phase-3 S7-01 ships the directory.
  - Phase-4 S7-01 — `FallbackTierPlanRecipeEngine.__init__` is the **construction site** that reads `Phase4Config` and instantiates `BandClassifier(high_floor=..., degraded_floor=...)` + `LlmInvocationGuard(max_tokens=..., max_dollars=..., per_call_max_tokens=..., event_log=...)`. AC-8a's runtime witness drives through this site.
  - `src/codegenie/rag/confidence.py` (S5-02, GREEN) — `BandClassifier(*, high_floor, degraded_floor)` is already constructor-injected and `@dataclass(frozen=True, kw_only=True)`. This story does NOT modify it.
  - `src/codegenie/fallback/budget.py` (S2-05, GREEN) — `LlmInvocationGuard(max_tokens, max_dollars, per_call_max_tokens, event_log)` is already constructor-injected. This story does NOT modify it.

## Goal

Ship `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` plus a plugin-local `Phase4Config` Pydantic model (in `plugins/vulnerability-remediation--node--npm/config.py`) plus a `load_phase4_config(path) -> Result[Phase4Config, Phase4ConfigError]` loader and the two skill templates `skills/vuln-major-bump.md` + `skills/leaf-llm-instruction.md` (plain `Skill`s under the existing Phase-2 model). Together these **fail loud at plugin-load time** on any missing, malformed, or out-of-band Phase-4 key. The kernel `PluginManifest` is **not** edited.

## Acceptance criteria

- [ ] **AC-1 (config file shape, plugin-local).** `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` exists with **exactly** these top-level keys (no others) and arch-pinned values:
  ```yaml
  thresholds:
    high_floor: 0.85
    degraded_floor: 0.65
  budget:
    max_tokens_per_workflow: 250000
    max_dollars_per_workflow: "1.50"   # quoted — Decimal-parseable string per DP-04
    per_call_max_tokens: 32000
  embeddings:
    model: "BAAI/bge-small-en-v1.5"
  cassettes:
    dir: "tests/cassettes/anthropic"
  ```
  No top-level `fallback:` wrapper (this *is* the fallback config file; an extra wrapper just adds noise). The kernel `plugin.yaml` is not modified by this story — it stays at the shape Phase-3 S7-01 ships. (validator: pivoted from "extend kernel `plugin.yaml`" to plugin-local — resolves CN-1/CN-2/DP-01.)
- [ ] **AC-2 (capability declaration, plugin-side; not a manifest field).** `plugins/vulnerability-remediation--node--npm/api.py` declares two module-level `Final[bool]` constants (`_CONSUMES_RAG_CAPABILITIES: Final[bool] = True`, `_CONSUMES_LLM_CAPABILITIES: Final[bool] = True`) AND adds the external binaries used by the LLM tier (`./node_modules/.bin/tsc` per ADR-04-0015) to the kernel manifest's existing `requirements.optional` tuple. There is **no** `requires: [rag_capabilities, llm_capabilities]` YAML field — that contradicts the kernel `ManifestRequirements` schema (which has only `external_tools` and `optional`). (validator: was a block; rewrote per CN-1/F8 — capability declaration is a plugin-side architectural fact, not a manifest field.)
- [ ] **AC-3 (skill file `vuln-major-bump.md` — plain `Skill` shape).** `plugins/vulnerability-remediation--node--npm/skills/vuln-major-bump.md` parses cleanly through `SkillsLoader._parse_one(path)` (the existing Phase-2 loader, unmodified) into a `Skill` whose:
  - `id == SkillId("vuln-major-bump-vulnerability-remediation-javascript-npm")` (the existing Phase-2 `SkillId` newtype),
  - `applies_to_tasks == [TaskClassId("vulnerability-remediation")]`,
  - `applies_to_languages == [Language("javascript")]` (NOT `node` — Layer A token; matches Phase-3 S7-01 validation CN-8),
  - `body_size` is between `512` and `4096` bytes (the prompt-cached `system[0]` block; arch §Prompt template structure soft-budgets ~2 KB but tolerates ±2×),
  - `body_blake3` matches `^blake3:[0-9a-f]{64}$`.
  No `kind:` / `task_class:` / `language:` / `build_system:` frontmatter — those fields do not exist on the kernel `Skill` model and would be rejected by `extra="forbid"`. (validator: was a block; rewrote per CN-4/DP-02.)
- [ ] **AC-4 (skill file `leaf-llm-instruction.md` — also a plain `Skill`).** `plugins/vulnerability-remediation--node--npm/skills/leaf-llm-instruction.md` parses cleanly into a `Skill` whose:
  - `id == SkillId("leaf-llm-instruction-vulnerability-remediation-javascript-npm")`,
  - `applies_to_tasks == [TaskClassId("vulnerability-remediation")]`,
  - `applies_to_languages == [Language("javascript")]`,
  - `body_size` is between `1024` and `6144` bytes (the prompt-cached `system[1]` block; arch soft-budgets ~3 KB).
  Phase-4 does not introduce a new `kind: instruction_template`. If Phase 5 later wants distinct kinds, that is a rule-of-three trigger for `@register_skill_kind(...)` — see Notes. (validator: was a block; rewrote per CN-4/DP-02.)
- [ ] **AC-5 (Specification-pattern rejection table — `extra="forbid"` + 12 named rules).** `plugins/vulnerability-remediation--node--npm/config.py` defines `Phase4Config(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` at **every** sub-model (`Thresholds`, `Budget`, `Embeddings`, `Cassettes`). `load_phase4_config(path)` returns `Err(Phase4ConfigError)` (never raises) when any of these 12 named rules fires:
  | # | Rule | Failing-row fixture | Expected `field_errors` member |
  |---|---|---|---|
  | R1 | unknown top-level key | `{thresolds: {...}, ...}` (typo) | `thresolds` |
  | R2 | missing `thresholds.high_floor` | pop the field | `thresholds.high_floor` |
  | R3 | `high_floor == degraded_floor` (strict `>` required) | `(0.65, 0.65)` | `thresholds.high_floor must be > thresholds.degraded_floor` |
  | R4 | `high_floor < degraded_floor` | `(0.5, 0.7)` | same as R3 |
  | R5 | threshold `NaN` (either) | `float("nan")` for either | `thresholds.high_floor must be a finite float in [0.0, 1.0]` (or `degraded_floor` variant) |
  | R6 | threshold out of `[0.0, 1.0]` | `high_floor = 1.5` or `degraded_floor = -0.1` | same as R5 |
  | R7 | `max_dollars_per_workflow <= 0` | `"0.00"` | `budget.max_dollars_per_workflow must be > 0` |
  | R8 | `per_call_max_tokens > max_tokens_per_workflow` (impossible-by-construction config) | `per_call = 300_000`, `max = 250_000` | `budget.per_call_max_tokens must be <= budget.max_tokens_per_workflow` |
  | R9 | negative `max_tokens_per_workflow` or `per_call_max_tokens` | `-1` | `budget.<field> must be a positive int` |
  | R10 | `embeddings.model` empty or whitespace-only after `.strip()` | `""`, `"   "` | `embeddings.model must be non-empty after .strip()` |
  | R11 | `cassettes.dir` is absolute path OR contains `..` traversal | `"/etc/passwd"`, `"../../outside"` | `cassettes.dir must be a relative path with no '..' segments` |
  | R12 | `cassettes.dir` empty | `""` | `cassettes.dir must be a non-empty relative path` |
  Every row is one parametrized test in `tests/unit/plugin/test_phase4_config_schema.py`. (validator: replaced the original 5 informal rules with a 12-row Specification table — resolves F1/F2/F4/F5/F9/DP-03.)
- [ ] **AC-6 (loader contract — `Result`, never raises; dotted-path diagnostics).** `load_phase4_config(path: Path) -> Result[Phase4Config, Phase4ConfigError]` mirrors the kernel `PluginManifest.from_yaml` shape: it never raises for any documented failure mode (size cap, malformed YAML, schema violation, IoError, symlink refused — same four-arm tagged union as `ManifestError`). On schema violation, `Phase4ConfigError.field_errors: tuple[str, ...]` carries the **dotted path from `Phase4Config` root** (e.g. `thresholds.high_floor`, `budget.per_call_max_tokens`, `cassettes.dir`) AND `Phase4ConfigError.path: Path` carries the absolute file path. Tests assert `isinstance(result, Err); assert isinstance(result.error, Phase4ConfigError); assert "<dotted-path>" in result.error.field_errors` — never `pytest.raises`. (validator: was a block; rewrote per CN-3/F1/DP-07.)
- [ ] **AC-7 (integration smoke — tmp-path synthesis + real-plugin skip-if-absent).** `tests/integration/test_plugin_loads_phase4_config.py` has two test functions:
  1. `test_synthesized_plugin_phase4_config_loads`: synthesizes a complete plugin directory under `tmp_path` with all required files (kernel `plugin.yaml` + `phase4-config.yaml` + two skill `.md` files), invokes `load_phase4_config(tmp_path / "phase4-config.yaml")`, and asserts the parsed values match the constants exported from `tests/_constants/phase4_defaults.py` (single source of truth — F10). Runs unconditionally.
  2. `test_real_plugin_phase4_config_loads`: if `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` exists on disk, loads it and asserts the same equality. If the file does not exist, `pytest.skip("Phase-3 S7-01 has not yet shipped the plugin directory")` with a loud reason so the skip is auditable. (validator: was a block per F5/CN-6; rewrote to unblock today while preserving the real-plugin assertion for when S7-01 lands.)
- [ ] **AC-8a (PRIMARY — runtime witness; end-to-end value flow).** `tests/integration/test_phase4_config_drives_band_classifier.py` writes a `phase4-config.yaml` with `high_floor: 0.99` (NOT the arch default), loads it via the plugin's `api.py` wiring path (which constructs `FallbackTierPlanRecipeEngine` per Phase-4 S7-01), and then drives a known-`Similarity(0.86)` candidate through the engine's `BandClassifier`. Asserts the classification is `RagDegraded` (it would have been `RagHit` under the default `0.85`). Same test with `high_floor: 0.85` confirms the same input is `RagHit`. This proves the value actually flows from YAML through the wiring to the classifier — no AST walk can prove this. (validator: was missing entirely; closes F9/CN-7/DP-05.)
- [ ] **AC-8b (DEFENSE-IN-DEPTH — AST walk; concrete scope).** A unit test walks `ast.parse(path.read_text())` for **each** of: `plugins/vulnerability-remediation--node--npm/api.py`, `plugins/vulnerability-remediation--node--npm/config.py`, and `src/codegenie/fallback/engines/fallback_tier_plan_recipe.py` (the Phase-4 S7-01 wiring site — adjust to the actual path the executor lands). For each module, visits every `ast.Constant` node and asserts `node.value not in {0.85, 0.65, 250_000, 1.50, 32_000}`. Allowlists: the `tests/_constants/phase4_defaults.py` file (it MUST hold those literals — that is its job) and any Pydantic `Field(default=...)` line inside `Phase4Config` (there should be none — see AC-8c). (validator: hardened from vague "walk the modules"; concrete scope per F7.)
- [ ] **AC-8c (DEFENSE — constructor-signature backstop).** A unit test introspects `inspect.signature(BandClassifier).parameters` and `inspect.signature(LlmInvocationGuard).parameters`; asserts that `high_floor`, `degraded_floor`, `max_tokens`, `max_dollars`, `per_call_max_tokens` all have `default is inspect.Parameter.empty` (constructor requires the value; no silent default-substitution). Also asserts every Pydantic field on `Phase4Config`'s sub-models is required (`field.is_required() is True`) — no field defaults the value to the arch literal (which would silently mask a missing-key bug). (validator: added — closes the "wire passes AST walk but classifier has Pydantic default" attack per F7.)
- [ ] **AC-9 (round-trip / metamorphic property).** Hypothesis property `test_phase4_config_yaml_roundtrip`: generate a valid `Phase4Config` (Hypothesis strategy `st.builds(Phase4Config, ...)` over the constrained field domains); dump to YAML; reload via `load_phase4_config`; assert the reloaded model equals the original. Defends against asymmetric serializers. (validator: added per F8.)
- [ ] **AC-10 (Hypothesis property — threshold ordering on the full unit square).** `tests/property/test_phase4_thresholds_property.py` uses `@given(h=st.floats(0, 1, allow_nan=False), d=st.floats(0, 1, allow_nan=False))` and asserts: a `Phase4Config` with those thresholds is `Ok` iff `0 <= d < h <= 1`, else `Err`. (validator: added per F3.)
- [ ] **AC-11 (single source of truth for defaults).** `tests/_constants/phase4_defaults.py` defines `PHASE4_HIGH_FLOOR = 0.85`, `PHASE4_DEGRADED_FLOOR = 0.65`, `PHASE4_MAX_TOKENS = 250_000`, `PHASE4_MAX_DOLLARS = Decimal("1.50")`, `PHASE4_PER_CALL_MAX_TOKENS = 32_000`, `PHASE4_EMBEDDINGS_MODEL = "BAAI/bge-small-en-v1.5"`, `PHASE4_CASSETTES_DIR = "tests/cassettes/anthropic"`. The integration smoke (AC-7) and the runtime-witness test (AC-8a default branch) import from this module — no test duplicates the literals. (validator: added per F10.)
- [ ] **AC-12 (`make check` clean).** Lint + typecheck + tests + fence all green.
- [ ] **AC-13 (TDD discipline).** Every red test for AC-3 through AC-11 lands as a `pytest`-failing commit *before* the implementation commit. The Implementation outline §Red section spells this out.

## Implementation outline

1. **Read first** (Global Rule 8): `src/codegenie/plugins/manifest.py` (especially lines 42-46 — the "no escape hatches" docstring); `src/codegenie/plugins/loader.py`; `src/codegenie/skills/model.py` + `loader.py`; `src/codegenie/result.py`. Confirm: kernel stays frozen; loader returns `Result`, never raises; `Skill` model uses `extra="forbid"`. Confirm Phase-3 S7-01 has shipped `plugins/vulnerability-remediation--node--npm/` — if not, stop and surface (story is BLOCKED).
2. **Pre-step (single source of truth)**: create `tests/_constants/phase4_defaults.py` (AC-11). Every later test imports the constants from here. This is created first so the schema model and the tests share one literal site.
3. **Create the plugin-local Pydantic model**: `plugins/vulnerability-remediation--node--npm/config.py` with:
   - `Thresholds(BaseModel, ConfigDict(frozen=True, extra="forbid"))` — `high_floor: float`, `degraded_floor: float`, no defaults (AC-8c).
   - `Budget(...)` — `max_tokens_per_workflow: int`, `max_dollars_per_workflow: Decimal`, `per_call_max_tokens: int`. `Decimal` not `float` (DP-04). No defaults.
   - `Embeddings(...)` — `model: str`. No default.
   - `Cassettes(...)` — `dir: str`. No default.
   - `Phase4Config(...)` — `thresholds: Thresholds`, `budget: Budget`, `embeddings: Embeddings`, `cassettes: Cassettes`. `extra="forbid"`.
   - `Phase4ConfigError` — tagged union mirroring `ManifestError`'s shape: `SizeCapExceeded | MalformedYaml | SchemaViolation | IoError` (the `kind` discriminator names the variant; `SchemaViolation` carries `field_errors: tuple[str, ...]`).
   - **Specification-pattern table**: `_VALIDATORS: tuple[Callable[[Phase4Config], Result[None, str]], ...]` listing 12 named pure validators (`_validate_thresholds_ordering`, `_validate_thresholds_finite_and_in_range`, `_validate_budget_positive`, `_validate_per_call_within_workflow_cap`, `_validate_embeddings_model_nonempty`, `_validate_cassettes_dir_relative_no_traversal`). Each returns `Err(message)` on failure. The `load_phase4_config` shell calls Pydantic validation first, then iterates the table.
4. **Pure / impure split** (DP-06): all 12 validators are pure functions of `Phase4Config` and return `Result[None, str]`. The only impure code is `load_phase4_config(path)`'s `safe_yaml.load(path, max_bytes=_PHASE4_CONFIG_MAX_BYTES)` call + `Path(path).resolve()` + (optionally) a structlog `phase4_config_loaded` event emit. Mirror `PluginManifest.from_yaml`'s shell exactly (translation table, never raises).
5. **Create `plugins/vulnerability-remediation--node--npm/phase4-config.yaml`** with the AC-1 arch values. Comment near the top: "Edit values directly here; downstream tests pin via `tests/_constants/phase4_defaults.py`."
6. **Create `plugins/vulnerability-remediation--node--npm/skills/vuln-major-bump.md`** with `Skill`-shaped frontmatter (`id`, `applies_to_tasks: [vulnerability-remediation]`, `applies_to_languages: [javascript]`) + a placeholder body of 1.5–2.5 KB. Document in the file header that prose is iterated by S7-06 cassette recording.
7. **Create `plugins/vulnerability-remediation--node--npm/skills/leaf-llm-instruction.md`** similarly (~2–3 KB body).
8. **Wire `api.py` (AC-2)**: add module-level `_CONSUMES_RAG_CAPABILITIES: Final[bool] = True` + `_CONSUMES_LLM_CAPABILITIES: Final[bool] = True`. Add `./node_modules/.bin/tsc` to the kernel `plugin.yaml`'s existing `requirements.optional` tuple (this is an additive edit to the YAML file that Phase-3 S7-01 ships; it is the only kernel-`plugin.yaml` change this story makes, and it stays within the existing schema). The plugin's `api.py` also loads `phase4-config.yaml` at module-import-time via `load_phase4_config(_HERE / "phase4-config.yaml")`; the resulting `Phase4Config` is held as a module-level `Final` for downstream consumption by Phase-4 S7-01's `FallbackTierPlanRecipeEngine.__init__`.
9. **Tests in TDD order** (RED → GREEN → REFACTOR; see §TDD plan).

## TDD plan — red / green / refactor

### Red — write failing tests first

All tests under `tests/unit/plugin/`, `tests/integration/`, `tests/property/`. Imports throughout use the plugin-local module path:

```python
from plugins.vulnerability_remediation__node__npm.config import (
    Phase4Config,
    Phase4ConfigError,
    SchemaViolation,
    load_phase4_config,
)
from codegenie.result import Err, Ok
```

**Unit test scaffold — `tests/unit/plugin/test_phase4_config_schema.py`** (covers AC-5, AC-6):

```python
from __future__ import annotations
import pytest
import yaml
from pathlib import Path
from decimal import Decimal
from plugins.vulnerability_remediation__node__npm.config import (
    load_phase4_config, Phase4Config, Phase4ConfigError, SchemaViolation,
)
from codegenie.result import Err, Ok


def _valid_config_dict() -> dict:
    # Use NON-arch values so a hardcoded `0.85` impl would FAIL this test (F4).
    return {
        "thresholds": {"high_floor": 0.70, "degraded_floor": 0.30},
        "budget": {
            "max_tokens_per_workflow": 100_000,
            "max_dollars_per_workflow": "0.75",
            "per_call_max_tokens": 10_000,
        },
        "embeddings": {"model": "test-embedder/v1"},
        "cassettes": {"dir": "tests/cassettes/test"},
    }


@pytest.fixture
def valid_config_path(tmp_path: Path) -> Path:
    p = tmp_path / "phase4-config.yaml"
    p.write_text(yaml.safe_dump(_valid_config_dict()))
    return p


def test_loads_valid_config_preserves_non_arch_values(valid_config_path: Path) -> None:
    result = load_phase4_config(valid_config_path)
    assert isinstance(result, Ok), result
    cfg = result.value
    assert cfg.thresholds.high_floor == 0.70
    assert cfg.thresholds.degraded_floor == 0.30
    assert cfg.budget.max_tokens_per_workflow == 100_000
    assert cfg.budget.max_dollars_per_workflow == Decimal("0.75")
    assert cfg.budget.per_call_max_tokens == 10_000
    assert cfg.embeddings.model == "test-embedder/v1"
    assert cfg.cassettes.dir == "tests/cassettes/test"


def test_rejects_missing_thresholds_block(valid_config_path: Path) -> None:
    """No silent Pydantic-default substitution — sub-models must be present."""
    data = yaml.safe_load(valid_config_path.read_text())
    data.pop("thresholds")
    valid_config_path.write_text(yaml.safe_dump(data))
    result = load_phase4_config(valid_config_path)
    assert isinstance(result, Err)
    assert isinstance(result.error, SchemaViolation)
    assert "thresholds" in result.error.field_errors


# AC-5 Specification table — one parametrize row per rule R1..R12.
@pytest.mark.parametrize(
    "mutate, expected_field_path",
    [
        # R1 — unknown top-level key
        (lambda d: d.__setitem__("thresolds", d.pop("thresholds")), "thresolds"),
        # R2 — missing required leaf
        (lambda d: d["thresholds"].pop("high_floor"), "thresholds.high_floor"),
        # R3 — equality (strict > required)
        (lambda d: d["thresholds"].update(high_floor=0.5, degraded_floor=0.5),
         "thresholds.high_floor must be > thresholds.degraded_floor"),
        # R4 — reversed
        (lambda d: d["thresholds"].update(high_floor=0.5, degraded_floor=0.7),
         "thresholds.high_floor must be > thresholds.degraded_floor"),
        # R5 — NaN
        (lambda d: d["thresholds"].update(high_floor=float("nan")),
         "thresholds.high_floor must be a finite float"),
        # R6 — out of range
        (lambda d: d["thresholds"].update(high_floor=1.5),
         "thresholds.high_floor must be a finite float"),
        # R7 — non-positive dollars
        (lambda d: d["budget"].update(max_dollars_per_workflow="0.00"),
         "budget.max_dollars_per_workflow must be > 0"),
        # R8 — per-call > workflow cap
        (lambda d: d["budget"].update(per_call_max_tokens=300_000, max_tokens_per_workflow=250_000),
         "budget.per_call_max_tokens must be <= budget.max_tokens_per_workflow"),
        # R9 — negative int
        (lambda d: d["budget"].update(max_tokens_per_workflow=-1),
         "budget.max_tokens_per_workflow"),
        # R10 — empty embeddings model
        (lambda d: d["embeddings"].update(model=""),
         "embeddings.model"),
        (lambda d: d["embeddings"].update(model="   "),
         "embeddings.model"),
        # R11 — absolute cassettes dir
        (lambda d: d["cassettes"].update(dir="/etc/passwd"),
         "cassettes.dir must be a relative path"),
        # R11 — traversal cassettes dir
        (lambda d: d["cassettes"].update(dir="../../outside"),
         "cassettes.dir must be a relative path"),
        # R12 — empty cassettes dir
        (lambda d: d["cassettes"].update(dir=""),
         "cassettes.dir"),
    ],
)
def test_rejection_specification_table(
    tmp_path: Path, mutate, expected_field_path: str
) -> None:
    data = _valid_config_dict()
    mutate(data)
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))
    result = load_phase4_config(bad)
    assert isinstance(result, Err), f"expected Err, got {result!r}"
    err = result.error
    assert isinstance(err, SchemaViolation), f"expected SchemaViolation, got {err!r}"
    # Assert dotted-path membership AND distinguishing token (F2 — avoid bare-key substring match).
    matched = any(expected_field_path in fe for fe in err.field_errors)
    assert matched, (
        f"expected {expected_field_path!r} in {err.field_errors!r}; "
        f"file={err.path}"
    )
```

**Skill-file unit tests — `tests/unit/plugin/test_phase4_skill_files.py`** (covers AC-3, AC-4; fills the previous `...` stub per F6):

```python
import pytest
from pathlib import Path
from codegenie.skills.loader import SkillsLoader
from codegenie.skills.model import Skill
from codegenie.types.identifiers import Language, SkillId, TaskClassId


PLUGIN_SKILLS = Path("plugins/vulnerability-remediation--node--npm/skills")


@pytest.mark.skipif(
    not PLUGIN_SKILLS.exists(),
    reason="Phase-3 S7-01 has not shipped the plugin skills directory",
)
@pytest.mark.parametrize(
    "filename, expected_id",
    [
        ("vuln-major-bump.md", "vuln-major-bump-vulnerability-remediation-javascript-npm"),
        ("leaf-llm-instruction.md", "leaf-llm-instruction-vulnerability-remediation-javascript-npm"),
    ],
)
def test_plugin_skill_files_parse_as_skill(filename: str, expected_id: str) -> None:
    # Use the existing Phase-2 loader, unmodified. (No new SkillsLoader; no `kind:` field.)
    loader = SkillsLoader.default()
    outcome = loader._parse_one(PLUGIN_SKILLS / filename)  # or whatever the public-test entry is
    assert outcome.ok is not None, outcome
    skill: Skill = outcome.ok.skill
    assert skill.id == SkillId(expected_id)
    assert TaskClassId("vulnerability-remediation") in skill.applies_to_tasks
    assert Language("javascript") in skill.applies_to_languages
    assert skill.body_blake3.startswith("blake3:")
    assert skill.body_size > 0


def test_skill_file_with_unknown_frontmatter_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text("---\nid: x\napplies_to_tasks: [t]\napplies_to_languages: [l]\nrogue_key: 1\n---\nbody\n")
    loader = SkillsLoader.default()
    outcome = loader._parse_one(p)
    assert outcome.ok is None
    # Existing SkillsLoader returns a typed SchemaViolation for `extra="forbid"` violations.


def test_skill_file_empty_rejected(tmp_path: Path) -> None:
    p = tmp_path / "empty.md"
    p.write_text("")
    loader = SkillsLoader.default()
    outcome = loader._parse_one(p)
    assert outcome.ok is None


def test_skill_file_frontmatter_only_rejected(tmp_path: Path) -> None:
    p = tmp_path / "fm.md"
    p.write_text("---\nid: x\napplies_to_tasks: [t]\napplies_to_languages: [l]\n---\n")
    loader = SkillsLoader.default()
    outcome = loader._parse_one(p)
    # Body must be > 0 bytes; existing loader behavior covers this — assert SchemaViolation
    # OR (if existing loader allows empty body) accept this row as a Notes-deferred concern,
    # and surface per Global Rule 7. Document the outcome in attempt log.
```

**Property tests — `tests/property/test_phase4_thresholds_property.py`** (AC-10):

```python
from hypothesis import given, strategies as st, assume
from plugins.vulnerability_remediation__node__npm.config import Phase4Config, Thresholds
from pydantic import ValidationError
import pytest


@given(h=st.floats(0.0, 1.0, allow_nan=False), d=st.floats(0.0, 1.0, allow_nan=False))
def test_thresholds_accept_iff_strictly_ordered(h: float, d: float) -> None:
    if d < h:
        Thresholds(high_floor=h, degraded_floor=d)  # MUST succeed
    else:
        with pytest.raises(ValidationError):
            Thresholds(high_floor=h, degraded_floor=d)
```

**Round-trip — `tests/property/test_phase4_config_roundtrip.py`** (AC-9):

```python
from hypothesis import given, strategies as st
import yaml
from plugins.vulnerability_remediation__node__npm.config import (
    Phase4Config, load_phase4_config,
)
from codegenie.result import Ok


@given(
    h=st.floats(0.5, 1.0, allow_nan=False).filter(lambda x: x > 0.5),
    # ... full strategy for every field, constrained to AC-5 valid domain
)
def test_phase4_config_yaml_roundtrip(tmp_path, h: float, ...):
    cfg1 = Phase4Config(thresholds={"high_floor": h, ...}, ...)
    p = tmp_path / "rt.yaml"
    p.write_text(yaml.safe_dump(cfg1.model_dump(mode="json")))
    result = load_phase4_config(p)
    assert isinstance(result, Ok)
    assert result.value == cfg1
```

**Integration smoke — `tests/integration/test_plugin_loads_phase4_config.py`** (AC-7):

```python
import pytest
import yaml
from decimal import Decimal
from pathlib import Path
from plugins.vulnerability_remediation__node__npm.config import load_phase4_config
from codegenie.result import Ok
from tests._constants.phase4_defaults import (
    PHASE4_HIGH_FLOOR, PHASE4_DEGRADED_FLOOR, PHASE4_MAX_TOKENS,
    PHASE4_MAX_DOLLARS, PHASE4_PER_CALL_MAX_TOKENS,
    PHASE4_EMBEDDINGS_MODEL, PHASE4_CASSETTES_DIR,
)


def test_synthesized_plugin_phase4_config_loads(tmp_path):
    p = tmp_path / "phase4-config.yaml"
    p.write_text(yaml.safe_dump({
        "thresholds": {"high_floor": PHASE4_HIGH_FLOOR, "degraded_floor": PHASE4_DEGRADED_FLOOR},
        "budget": {
            "max_tokens_per_workflow": PHASE4_MAX_TOKENS,
            "max_dollars_per_workflow": str(PHASE4_MAX_DOLLARS),
            "per_call_max_tokens": PHASE4_PER_CALL_MAX_TOKENS,
        },
        "embeddings": {"model": PHASE4_EMBEDDINGS_MODEL},
        "cassettes": {"dir": PHASE4_CASSETTES_DIR},
    }))
    result = load_phase4_config(p)
    assert isinstance(result, Ok), result
    cfg = result.value
    assert cfg.thresholds.high_floor == PHASE4_HIGH_FLOOR
    assert cfg.budget.max_dollars_per_workflow == PHASE4_MAX_DOLLARS


REAL_CFG = Path("plugins/vulnerability-remediation--node--npm/phase4-config.yaml")


@pytest.mark.skipif(
    not REAL_CFG.exists(),
    reason="Phase-3 S7-01 has not yet shipped the plugin directory; this test runs once S7-01 lands",
)
def test_real_plugin_phase4_config_loads():
    result = load_phase4_config(REAL_CFG)
    assert isinstance(result, Ok), result
    cfg = result.value
    assert cfg.thresholds.high_floor == PHASE4_HIGH_FLOOR
    assert cfg.thresholds.degraded_floor == PHASE4_DEGRADED_FLOOR
    assert cfg.budget.max_tokens_per_workflow == PHASE4_MAX_TOKENS
    assert cfg.budget.max_dollars_per_workflow == PHASE4_MAX_DOLLARS
    assert cfg.budget.per_call_max_tokens == PHASE4_PER_CALL_MAX_TOKENS
    assert cfg.embeddings.model == PHASE4_EMBEDDINGS_MODEL
    assert cfg.cassettes.dir == PHASE4_CASSETTES_DIR
```

**Runtime witness — `tests/integration/test_phase4_config_drives_band_classifier.py`** (AC-8a):

```python
# This is the load-bearing test for "values actually flow from YAML to consumer."
# It depends on Phase-4 S7-01 (FallbackTierPlanRecipeEngine wiring). If S7-01
# hasn't landed when this story runs, mark this as the executor's first follow-up.

import yaml
from pathlib import Path
from plugins.vulnerability_remediation__node__npm.config import load_phase4_config
# Phase-4 S7-01 ships FallbackTierPlanRecipeEngine + its wiring.
from codegenie.fallback.engines.fallback_tier_plan_recipe import build_engine_from_config
from codegenie.rag.models import RagDegraded, RagHit


def _write_cfg(tmp_path: Path, high_floor: float) -> Path:
    p = tmp_path / "phase4-config.yaml"
    p.write_text(yaml.safe_dump({
        "thresholds": {"high_floor": high_floor, "degraded_floor": 0.50},
        "budget": {"max_tokens_per_workflow": 100_000,
                   "max_dollars_per_workflow": "1.00",
                   "per_call_max_tokens": 10_000},
        "embeddings": {"model": "test-embedder/v1"},
        "cassettes": {"dir": "tests/cassettes/test"},
    }))
    return p


def _classify(engine, score: float):
    # Drive a candidate with similarity `score` through the engine's BandClassifier.
    # Exact call shape: the executor consults Phase-4 S5-01/S5-02 for the public surface.
    ...


def test_high_floor_value_flows_yaml_to_band_classifier(tmp_path):
    cfg_low = load_phase4_config(_write_cfg(tmp_path, high_floor=0.85)).value
    engine_low = build_engine_from_config(cfg_low)
    cfg_high = load_phase4_config(_write_cfg(tmp_path, high_floor=0.99)).value
    engine_high = build_engine_from_config(cfg_high)
    # A 0.86-similarity candidate: under 0.85 floor -> RagHit; under 0.99 floor -> RagDegraded.
    assert isinstance(_classify(engine_low, score=0.86), RagHit)
    assert isinstance(_classify(engine_high, score=0.86), RagDegraded)
```

**AST + signature backstop — `tests/unit/plugin/test_phase4_no_hardcoded_literals.py`** (AC-8b, AC-8c):

```python
import ast
import inspect
from pathlib import Path
from codegenie.rag.confidence import BandClassifier
from codegenie.fallback.budget import LlmInvocationGuard


_FORBIDDEN_LITERALS = {0.85, 0.65, 250_000, 1.50, 32_000}
_MODULES_TO_WALK = (
    Path("plugins/vulnerability-remediation--node--npm/api.py"),
    Path("plugins/vulnerability-remediation--node--npm/config.py"),
    # Phase-4 S7-01 wiring site — adjust to actual path the executor lands:
    Path("src/codegenie/fallback/engines/fallback_tier_plan_recipe.py"),
)
_ALLOWLIST_PATHS = (
    Path("tests/_constants/phase4_defaults.py"),  # this is the source of truth — MUST contain them
)


def test_no_hardcoded_phase4_defaults_in_wiring_modules():
    for path in _MODULES_TO_WALK:
        if not path.exists():
            continue  # AC-7 covers skip; this defense is about hygiene of what IS shipped.
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                assert node.value not in _FORBIDDEN_LITERALS, (
                    f"hardcoded phase-4 default {node.value!r} at {path}:{node.lineno}; "
                    "values must come from phase4-config.yaml — import from "
                    "tests/_constants/phase4_defaults.py in tests, or pass at construction."
                )


def test_band_classifier_requires_thresholds_at_construction():
    sig = inspect.signature(BandClassifier)
    for field in ("high_floor", "degraded_floor"):
        assert sig.parameters[field].default is inspect.Parameter.empty, (
            f"BandClassifier.{field} must have NO default; the value must come from config."
        )


def test_llm_invocation_guard_requires_caps_at_construction():
    sig = inspect.signature(LlmInvocationGuard)
    for field in ("max_tokens", "max_dollars", "per_call_max_tokens"):
        assert sig.parameters[field].default is inspect.Parameter.empty, (
            f"LlmInvocationGuard.{field} must have NO default; the value must come from config."
        )
```

### Green — make the tests pass

Build the plugin-local `Phase4Config` model + tagged-union error type + Specification-table loader (see step 3 of Implementation outline). Create the YAML file with arch values. Create the two skill `.md` files with `Skill`-shaped frontmatter. Wire `api.py` per AC-2.

### Refactor — clean up

- If the 12 validators duplicate predicates, factor shared helpers (e.g., `_assert_finite_in_unit_interval(name, value)`).
- Confirm `make check` clean: `make lint`, `make typecheck`, `make test`, `make fence`.
- If S5-04's calibration smoke test exists, run it — must still classify correctly with values now sourced from the manifest. (S5-04 may not yet exist; that is a future story's concern.)
- Verify `make lint-imports` passes — no plugin → kernel import-cycle introduced.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/plugin/test_plugin_yaml_phase4_schema.py
from __future__ import annotations
import pytest
import yaml
from codegenie.plugins.manifest import load_plugin_manifest, PluginManifestError


@pytest.fixture
def valid_phase4_yaml(tmp_path):
    p = tmp_path / "plugin.yaml"
    p.write_text(yaml.safe_dump({
        "name": "vulnerability-remediation--node--npm",
        "version": "0.4.0",
        "requires": ["rag_capabilities", "llm_capabilities"],
        "fallback": {
            "thresholds": {"high_floor": 0.85, "degraded_floor": 0.65},
            "budget": {
                "max_tokens_per_workflow": 250000,
                "max_dollars_per_workflow": 1.50,
                "per_call_max_tokens": 32000,
            },
            "embeddings": {"model": "BAAI/bge-small-en-v1.5"},
            "cassettes": {"dir": "tests/cassettes/anthropic"},
        },
    }))
    return p


def test_loads_phase4_config_with_exact_values(valid_phase4_yaml):
    m = load_plugin_manifest(valid_phase4_yaml)
    assert m.fallback.thresholds.high_floor == 0.85
    assert m.fallback.thresholds.degraded_floor == 0.65
    assert m.fallback.budget.max_tokens_per_workflow == 250000
    assert m.fallback.budget.max_dollars_per_workflow == pytest.approx(1.50)
    assert m.fallback.budget.per_call_max_tokens == 32000
    assert m.fallback.embeddings.model == "BAAI/bge-small-en-v1.5"
    assert m.fallback.cassettes.dir == "tests/cassettes/anthropic"


@pytest.mark.parametrize(
    "mutate,expected_diagnostic_substring",
    [
        (lambda d: d["fallback"]["thresholds"].pop("high_floor"), "high_floor"),
        (lambda d: d["fallback"]["thresholds"].update(high_floor=0.5, degraded_floor=0.7),
         "high_floor must be > degraded_floor"),
        (lambda d: d["fallback"]["budget"].update(max_dollars_per_workflow=0),
         "max_dollars_per_workflow"),
        (lambda d: d["fallback"]["embeddings"].update(model=123),
         "embeddings.model"),
        (lambda d: d["fallback"].pop("cassettes"), "cassettes"),
    ],
)
def test_rejects_malformed_phase4_yaml(
    tmp_path, valid_phase4_yaml, mutate, expected_diagnostic_substring,
):
    data = yaml.safe_load(valid_phase4_yaml.read_text())
    mutate(data)
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(PluginManifestError, match=expected_diagnostic_substring):
        load_plugin_manifest(bad)


def test_skill_files_validated_at_load(tmp_path):
    # Plugin manifest names skill files; loader must verify they exist and parse.
    # (Implementation detail: loader resolves skill paths relative to plugin dir.)
    ...
```

```python
# tests/integration/test_plugin_loads_phase4_config.py
from pathlib import Path
from codegenie.plugins.manifest import load_plugin_manifest

PLUGIN_DIR = Path("plugins/vulnerability-remediation--node--npm")


def test_real_plugin_yaml_parses_with_arch_values():
    m = load_plugin_manifest(PLUGIN_DIR / "plugin.yaml")
    assert m.fallback.thresholds.high_floor == 0.85
    assert m.fallback.budget.max_dollars_per_workflow == 1.50
    # Skill files exist:
    assert (PLUGIN_DIR / "skills" / "vuln-major-bump.md").is_file()
    assert (PLUGIN_DIR / "skills" / "leaf-llm-instruction.md").is_file()
```

### Green — make it pass

Extend the loader's Pydantic models (or JSON schema) with a `Phase4Config` block (`thresholds`, `budget`, `embeddings`, `cassettes`). Add the rejection rules. Write the `plugin.yaml` block. Create the two skill `.md` files with valid frontmatter. Wire S5-02 / S2-05 to read from the manifest.

### Refactor — clean up

- If the rejection rules become more than ~5, factor each into a named `_validate_<rule>(config)` function — composable Specifications, named.
- Confirm `make check` is clean.
- Re-run S5-04's calibration smoke test if it exists yet — must still classify correctly with the values now sourced from the manifest.

## Files to touch

| Path | Action | Why |
|---|---|---|
| `tests/_constants/__init__.py` | NEW (empty) | Makes `tests/_constants` an importable package. |
| `tests/_constants/phase4_defaults.py` | NEW | Single source of truth for the arch-pinned literals (AC-11). |
| `plugins/vulnerability-remediation--node--npm/config.py` | NEW | Plugin-local `Phase4Config` + `Phase4ConfigError` + `load_phase4_config`. (Requires Phase-3 S7-01 to have created the plugin dir first.) |
| `plugins/vulnerability-remediation--node--npm/phase4-config.yaml` | NEW | The calibration values themselves (AC-1). |
| `plugins/vulnerability-remediation--node--npm/skills/vuln-major-bump.md` | NEW | Plain `Skill` (system[0] block; ~2 KB body). |
| `plugins/vulnerability-remediation--node--npm/skills/leaf-llm-instruction.md` | NEW | Plain `Skill` (system[1] block; ~3 KB body). |
| `plugins/vulnerability-remediation--node--npm/api.py` | MODIFY (Phase-3 S7-01 created this) | Add `_CONSUMES_RAG_CAPABILITIES`/`_CONSUMES_LLM_CAPABILITIES` constants and module-import-time `load_phase4_config(...)` call (AC-2). |
| `plugins/vulnerability-remediation--node--npm/plugin.yaml` | MODIFY (one additive line) | Append `./node_modules/.bin/tsc` to `requirements.optional` tuple (AC-2; stays within kernel schema). |
| `tests/unit/plugin/test_phase4_config_schema.py` | NEW | AC-5/6 — schema rejection table (12 rows). |
| `tests/unit/plugin/test_phase4_skill_files.py` | NEW | AC-3/4 — `Skill`-shape conformance. |
| `tests/unit/plugin/test_phase4_no_hardcoded_literals.py` | NEW | AC-8b/8c — AST + signature backstop. |
| `tests/property/test_phase4_thresholds_property.py` | NEW | AC-10. |
| `tests/property/test_phase4_config_roundtrip.py` | NEW | AC-9. |
| `tests/integration/test_plugin_loads_phase4_config.py` | NEW | AC-7 — tmp-path synthesis + real-plugin skip-if-absent. |
| `tests/integration/test_phase4_config_drives_band_classifier.py` | NEW | AC-8a — end-to-end runtime witness. |
| `src/codegenie/plugins/manifest.py` | **DO NOT MODIFY** | Kernel stays frozen (manifest.py:42-46). |
| `src/codegenie/skills/model.py` | **DO NOT MODIFY** | Kernel stays frozen. |
| `src/codegenie/rag/confidence.py` | **DO NOT MODIFY** | S5-02 already DI'd. |
| `src/codegenie/fallback/budget.py` | **DO NOT MODIFY** | S2-05 already DI'd. |

## Out of scope

- The prose contents of the skill templates (placeholder-acceptable; S7-06 cassette recording iterates the prose).
- The `cassettes.lock` manifest format (S3-05); this story only references the directory path.
- Phase-3 plugin manifest schema redesign — this story does not redesign or extend the kernel.
- Wiring `FallbackTierPlanRecipeEngine` to consume `Phase4Config` — that's Phase-4 S7-01. AC-8a depends on S7-01's wiring being in place; if it isn't, AC-8a's `pytest.skip` documents the gap.
- A kernel `@register_plugin_config_block` registry — rule-of-three deferral; defer to Phase 7+ (see Notes).

## Notes for the implementer

- **"Calibration is config not code" (ADR-04-0008) is the durable invariant.** Hardcoded `0.85`/`0.65`/`250000`/`1.50`/`32000` anywhere in the source after this story is a regression — AC-8b catches it across the named wiring modules; AC-8c catches Pydantic-default-substitution attacks.
- **Plugin-local config, NOT kernel-manifest extension.** `src/codegenie/plugins/manifest.py:42-46` is explicit: "Adding a Phase 7 distroless `contributes.containers` field is an explicit, ADR-worthy edit to this file; never flip to `extra='allow'`." Phase 4 honors this by living entirely under `plugins/.../`. ADR-04-0008 says "thresholds live in `plugin.yaml`" — read this *as* "plugin-scoped" not *as* "the kernel `plugin.yaml`." The phase-arch-design talks about "Plugin-scoped" configuration without committing to a specific file.
- **Rule-of-three deferral on the kernel registry (DP-08).** Phase 4 is the **1st** plugin-local-config consumer. Phase 7 (distroless) will be the 2nd. If Phase 8 lands a third plugin-local-config block in the same shape, **then** introduce `@register_plugin_config_block(name)` in the kernel (mirror Phase-2's `@register_index_freshness_check` precedent). Until then, hand-write per-plugin. Resist abstracting on Phase 7 alone (only two consumers — Rule 2). Document the precedent here so Phase 7's author finds it.
- **Skill model — no new `kind:` field.** Phase 2's `Skill` model is frozen and `extra="forbid"`. Phase 4 does NOT add a `kind:` field. Both `.md` files are plain `Skill`s differentiated by `id`. If Phase 5 needs distinct kinds (e.g., a `policy_template` vs a `skill`), THAT is the rule-of-three trigger for `@register_skill_kind` — not this story.
- **Language token is `javascript`, NOT `node`.** Per Phase-3 S7-01 validation note CN-8: the `languages:` token inside the manifest/skill must match Layer A's `LanguageDetection` output (which emits `javascript`/`typescript`, never `node`). The directory slug `--node--` is operator-readable only.
- **Loader contract — `Result`, never raises.** `load_phase4_config(path) -> Result[Phase4Config, Phase4ConfigError]`. Never raises for any documented failure mode. Mirror the kernel `PluginManifest.from_yaml` shape byte-for-byte: same four-arm `ManifestError`-shaped tagged union (`SizeCapExceeded | MalformedYaml | SchemaViolation | IoError`), same `Result` import, same exception-translation pattern. Pattern: Adapter — `load_phase4_config` adapts the same shape across two files; reuse, don't reinvent.
- **`extra="forbid"` at every sub-model.** This is the schema-drift discipline that catches `thresolds:` typos at load time. ADR-0010's escape-hatch ban applies here too — never flip to `extra="allow"`.
- **`Decimal` for money (DP-04).** `max_dollars_per_workflow` is `Decimal`, not `float`. YAML side: write as a quoted string `"1.50"`; Pydantic coerces. Money-in-`float` is a Rule-12 hazard.
- **"high_floor > degraded_floor" is load-bearing (R3/R4).** Without strict ordering enforcement, the two-threshold band collapses silently and `RagDegraded` becomes unreachable. AC-10's Hypothesis property covers the full `[0, 1]²` unit square — any wrong-direction mutation fails on millions of generated cases.
- **Skill `.md` body content is placeholder-acceptable.** A file header like `<!-- placeholder body; prose iterated by S7-06 cassette recording -->` followed by ~2 KB / ~3 KB lorem-ipsum-shaped content satisfies AC-3/AC-4's body-size bounds. The S7-06 implementer will edit the bodies; the *frontmatter* and the file's *existence* + *parseability* are this story's contribution.
- **Specification table over branching `if`s (DP-03).** 12 named pure validators in a `tuple[Callable, ...]` table — never a single `if-elif` cascade. Each test row maps 1:1 to one validator. Easy to extend by addition.
- **Pure / impure split (DP-06).** All 12 validators are pure (`Phase4Config -> Result[None, str]`). `load_phase4_config(path)` is the only impure shell; it does the `safe_yaml.load`, the `Pydantic.model_validate`, then iterates the table. Mirrors `PluginManifest.from_yaml`'s shape.
- **Fail loud (Global Rule 12).** `load_phase4_config` returns `Err(SchemaViolation(...))` with a diagnostic naming the dotted path AND the file path. A silent `KeyError` from `cfg.thresholds.high_floor` access elsewhere is the wrong failure mode.
