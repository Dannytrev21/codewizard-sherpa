# ADR-0009: Prompts as versioned YAML data; inline f-string prompt construction forbidden by fence-CI

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** prompts-as-data · prompt-cache-discipline · fence-ci · synthesizer-departure
**Related:** [ADR-0007](0007-anthropic-model-pin-via-versioned-alias.md), [ADR-0008](0008-prompt-injection-structural-defenses.md), [ADR-0012](0012-vcr-cassette-discipline.md)

## Context

Prompts are the largest mutable surface that affects cost (via prompt-cache hit rate), correctness (via instructions to the model), and security (via fence-wrapping discipline). All three lens designs built prompts differently: performance built them in Python with f-strings; security used fence-wrapping but built them in Python; best-practices YAML'd them but skipped fences (`final-design.md §"Components"` #4). Two failure modes recur in real deployments: (a) inline f-string prompt construction means a prompt edit is a Python edit — invisible to product, hard to git-review, easy to break the cache breakpoint; (b) skipping fence-wrapping on untrusted inputs is a fence-author-forgot-once-and-shipped-prod bug.

Prompts as versioned YAML data make every prompt edit a git-reviewable diff. Auto-fence-wrapping by the loader (driven by template-declared `untrusted_inputs` list) means the prompt author cannot forget. Schema validation at load time means malformed templates fail at CLI startup, not at the first user-facing error.

## Options considered

- **Inline Python f-strings.** Performance default. Fastest to write, hardest to review, easiest to break the prompt-cache byte stability. Fence-wrapping must be hand-coded everywhere; one missed call site is a vulnerability.
- **Python `string.Template`.** Mild improvement over f-strings. Still Python-source-resident; still requires per-call-site fence-wrapping.
- **Jinja2 templates.** Logic-in-templates becomes attractive. Variables become conditionals; the prompt body becomes program-shaped. Defeats the "prompts are data" framing.
- **YAML templates with `{{var}}` substitution only, schema-validated at startup, untrusted-inputs auto-fence-wrapped by the loader.** Synth pick. Variable substitution is the *only* logic; the template is data.

## Decision

Prompts ship as versioned YAML files under `src/codegenie/llm/prompts/<id>.v<n>.yaml`. Each template declares JSON-Schema-validated front matter: `cache_breakpoints` (where prompt-cache markers go), `untrusted_inputs` (which variables are adversarial-source), `required_variables`, `max_tokens`, `temperature`. Variable substitution is `{{name}}` only — no loops, no conditionals, no logic. `PromptLoader` validates every template at `__init__` against the schema; malformed → CLI exit 11. Phase 4 ships `system.v1.yaml`, `few_shot_rag.v1.yaml`, `from_scratch.v1.yaml`; bumps are `*.v2.yaml`.

**Auto-fence-wrapping.** Every variable declared in `untrusted_inputs` is wrapped by the loader: `<UNTRUSTED_FROM={var_name} fence={per_run_random_id}>...</UNTRUSTED_FROM fence={per_run_random_id}>`. The prompt author cannot forget — declaring `untrusted_inputs` once is the only requirement.

**Inline f-string prompts forbidden.** Phase 4 fence-CI extension (AST scan for `system:` / `user:` / `assistant:` strings ≥ 200 chars in `src/codegenie/llm/*` and `recipes/engines/rag_llm.py`) hard-fails the build on any inline prompt. The mechanism is `tests/fence/test_fence_phase4_no_inline_prompts.py`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Every prompt edit is a YAML diff — git-reviewable, product-readable, search-friendly | Two prompts ship in v0.4.0 (`from_scratch.v1.yaml`, `few_shot_rag.v1.yaml`); bumping is `*.v2.yaml`, not editing in place |
| Auto-fence-wrapping is structural — declaring `untrusted_inputs` once is the only requirement | New prompts that introduce a new untrusted-input variable must declare it; missing-declaration vulnerability is real but caught by `test_untrusted_inputs_fence_wrapped.py` |
| Prompt-cache breakpoints (`cache_breakpoints`) are declared in YAML, so the cache layout is reviewable | Cache breakpoints must be byte-stable across two renders of the same fixture; golden test on the system-block bytes catches drift |
| Schema validation at `PromptLoader.__init__` fails CLI startup loudly (exit 11) on malformed templates | The schema itself (`prompts/_schema.json`) is one more file to maintain |
| Inline f-string ban via fence-CI means the rule isn't a code-review convention — it's a build gate | Engineer surprise at PR time when a quick "let me just inline this short prompt for the test" hits the AST scan |
| Variable substitution is `{{var}}` only — no Jinja logic, no template DSL to maintain | Prompts that need conditionals (e.g., "include few-shots only when present") become multiple templates (`from_scratch.v1.yaml`, `few_shot_rag.v1.yaml`) rather than one parameterized template |

## Consequences

- `src/codegenie/llm/prompts/` is the canonical prompt directory. `prompts/_schema.json` validates front matter. Phase 4 ships `system.v1.yaml`, `few_shot_rag.v1.yaml`, `from_scratch.v1.yaml`.
- Prompt bumps are `*.v2.yaml`; old versions stay on disk until no cassette references them. Cassette key (per [ADR-0012](0012-vcr-cassette-discipline.md)) includes `prompt_template_id` + `prompt_template_version` so the bump invalidation is structured.
- `PromptLoader.load(template_id, context: LlmPromptContext) -> LlmRequest` is the only public entry. `PromptBuilder.build` wraps it with canary minting + per-run fence-id selection.
- Untrusted-input list (Phase 4): `advisory_description`, `package.json#description`, `lockfile._resolved` URLs, retrieved-example bodies, `readme_excerpt`.
- Golden test `test_prompt_cache_breakpoint_layout.py` asserts the rendered system block is byte-stable across two runs against the same fixture. A legitimate prompt edit lands as a YAML diff *and* a regenerated golden — both reviewed in PR.
- Phase 5/6/7 may add new templates (different task classes); the loader mechanism doesn't change.

## Reversibility

**Low.** Reverting to Python-source prompts would mean rewriting every cassette (because rendered bytes change), regenerating every golden, and removing the AST scan. The decision is durable; only the schema details are mildly reversible.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row implied by `PromptBuilder` design
- `../final-design.md §"Components"` #4 — `PromptBuilder` + `PromptLoader`
- `../phase-arch-design.md §"Component design"` #8 — `PromptLoader` + YAML prompts
- `../phase-arch-design.md §"Agentic best practices"` — prompt template structure
- `../critique.md §security "Things this design missed"` — defaulting to inline prompts is a vulnerability
- Production [design.md §2.6](../../../production/design.md) — org uniqueness as data
