# Story S7-04 — `plugin.yaml` + skill templates

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (`FallbackTierPlanRecipeEngine` registered as `transforms()['plan']`)
**ADRs honored:** ADR-0008 (two-threshold band thresholds in `plugin.yaml`), ADR-0010 (budget caps as capability — values live in config), production-ADR-0031 (plugin scoping)

## Context

Phase 4's tuning knobs — RAG thresholds, budget caps, embeddings-model name, cassette directory — live in the plugin's `plugin.yaml`, not in code. This is the canonical pattern: "calibration is config, not code" (ADR-0008). Two skill templates also externalize the LLM-facing instruction surface: `vuln-major-bump.md` (the skill) and `leaf-llm-instruction.md` (the instruction template). Phase 4 ships them schema-validated at plugin-load time so a typo in YAML or a missing template fails *at startup*, not in the middle of a workflow.

Three reasons this story is `S` rather than `M`: (1) the schema for `plugin.yaml` is established by Phase 3's plugin loader — this story extends the schema, doesn't invent it; (2) the skill `.md` files are content with a thin frontmatter envelope, not behavior; (3) the validation is a plugin-load-time check, not a runtime gate.

The acceptance criteria pin the *exact* values from arch §"Configuration" so that future stories (the calibration smoke test S5-04, the E2E tests S7-06/S7-07, the budget-cap unit tests) read the same constants from a single source.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Configuration` — "Plugin-scoped: `plugin.yaml` carries thresholds (`high_floor: 0.85`, `degraded_floor: 0.65`), budget caps (`max_tokens_per_workflow: 250000`, `max_dollars_per_workflow: 1.50`, `per_call_max_tokens: 32000`), embeddings model name, cassette directory."
  - `../phase-arch-design.md §Prompt template structure` — "Externalized in `plugins/vulnerability-remediation--node--npm/skills/`: `vuln-major-bump.md` (skill), `leaf-llm-instruction.md` (instruction template). Schema-validated at plugin-load time. Three cached system blocks per call."
  - `../phase-arch-design.md §Development view` — `p_skills["skills/vuln-major-bump.md (NEW), leaf-llm-instruction.md (NEW)"]` and `p_yaml["plugin.yaml: requires rag_capabilities + llm_capabilities; thresholds: high_floor degraded_floor; budget caps"]`.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — thresholds live in `plugin.yaml`; calibration is config not code.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` — budget caps are capability-bound; the **values** come from `plugin.yaml`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — `plugin.yaml` is the manifest format; loader integrity (Phase-3 ADRs) requires schema validation.
- **Source design:**
  - `../final-design.md §Configuration`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Ship `plugin.yaml` (thresholds, budget caps, embeddings model, cassette dir) + schema-validated `skills/{vuln-major-bump,leaf-llm-instruction}.md`; plugin-load schema check fails on missing keys."
- **Existing code:**
  - `plugins/vulnerability-remediation--node--npm/plugin.yaml` (Phase 3) — current shape; this story extends it surgically.
  - Phase-3 plugin loader (`src/codegenie/plugins/loader.py` or similar — read first) — the schema-validation entry point.
  - `src/codegenie/fallback/budget.py` (S2-05) — the consumer of `max_tokens_per_workflow`/`max_dollars_per_workflow`.
  - `src/codegenie/rag/confidence.py` (S5-02) — the consumer of `high_floor`/`degraded_floor`.

## Goal

Ship `plugins/vulnerability-remediation--node--npm/plugin.yaml` extended with Phase-4 keys (thresholds, budget caps, embeddings model, cassette directory) plus the two schema-validated skill templates `skills/vuln-major-bump.md` and `skills/leaf-llm-instruction.md` — and a plugin-load-time schema check that **fails loud** on missing or malformed Phase-4 keys.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/plugin.yaml` contains the Phase-4 block under a stable top-level key (e.g., `phase4:` or `fallback:` — read the Phase-3 plugin.yaml first to pick the consistent nesting). The block specifies, with exact arch values:
  ```yaml
  fallback:
    thresholds:
      high_floor: 0.85
      degraded_floor: 0.65
    budget:
      max_tokens_per_workflow: 250000
      max_dollars_per_workflow: 1.50
      per_call_max_tokens: 32000
    embeddings:
      model: "BAAI/bge-small-en-v1.5"
    cassettes:
      dir: "tests/cassettes/anthropic"
  ```
- [ ] `plugin.yaml` also declares the new capability requirements: `requires: [rag_capabilities, llm_capabilities]` (mirroring the existing `requires` list per Phase-3 manifest schema).
- [ ] `skills/vuln-major-bump.md` exists with YAML frontmatter naming `kind: skill`, `task_class: vulnerability-remediation`, `language: node`, `build_system: npm`, plus a body (the prompt-cached `system[0]` block; size budget ~2 KB per arch §Prompt template structure).
- [ ] `skills/leaf-llm-instruction.md` exists with YAML frontmatter naming `kind: instruction_template`, plus a body (the prompt-cached `system[1]` block; size budget ~3 KB per arch).
- [ ] Plugin-load-time schema validation rejects (a) missing `thresholds.high_floor`, (b) `high_floor <= degraded_floor` (the bands must be strictly ordered), (c) `max_dollars_per_workflow <= 0`, (d) `embeddings.model` not a string, (e) missing skill files, (f) skill file missing required frontmatter keys.
- [ ] Each schema-rejection is unit-tested (`tests/unit/plugin/test_plugin_yaml_phase4_schema.py`) with a deliberately-malformed fixture and asserts a typed `PluginManifestError` (or whatever the Phase-3 loader raises) carrying a diagnostic message that names the offending key.
- [ ] An integration smoke (`tests/integration/test_plugin_loads_phase4_config.py`) loads the actual `plugin.yaml` and asserts the parsed values match the constants above exactly (so a typo in the YAML is caught by the test, not by a downstream consumer at workflow time).
- [ ] The S5-02 confidence-band classifier and the S2-05 budget guard both **read these values via the plugin config layer** rather than hardcoded constants (verify by AST-walking those modules: no literal `0.85`/`0.65`/`250000`/`1.50`/`32000`).
- [ ] `make check` clean.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first**: open the current `plugin.yaml` and the Phase-3 plugin-loader schema. Identify the existing top-level structure and the schema-validation pattern (Pydantic? JSON Schema? Phase-3 dictates the shape).
2. Extend the schema (likely `src/codegenie/plugins/manifest.py` or `loader.py` — but **only the additive parts**; the kernel-frozen guard from S1-07 may forbid edits to `src/codegenie/plugins/protocols.py`, so the schema extension must land in a Phase-3-allowed module or be a plugin-side Pydantic model that the loader imports). Surface a conflict per Global Rule 7 if the schema lives in a kernel-frozen file.
3. Add the `fallback:` block to `plugin.yaml` with exact arch values; mirror the indentation/style of existing blocks (Global Rule 11).
4. Create `skills/vuln-major-bump.md` and `skills/leaf-llm-instruction.md` with YAML frontmatter + bodies. The bodies are placeholder-acceptable for this story (they will be filled in by the implementer of the LLM-from-scratch cassette recording in S3-02/S7-06); the **structure** must be validated, not the prose.
5. Add schema-validation unit tests covering each rejection branch.
6. Add the integration smoke that round-trips `plugin.yaml` through the loader.
7. Wire S5-02 (`confidence.py`) and S2-05 (`budget.py`) to read from the plugin config — if those modules currently use hardcoded defaults, refactor surgically (Global Rule 3) to accept the config values via constructor injection (the values flow through the plugin TCCM).

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

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/plugin.yaml` | Add the `fallback:` block with thresholds, budget caps, embeddings model, cassette dir. |
| `plugins/vulnerability-remediation--node--npm/skills/vuln-major-bump.md` | New skill template (system[0] block; ~2 KB). |
| `plugins/vulnerability-remediation--node--npm/skills/leaf-llm-instruction.md` | New instruction template (system[1] block; ~3 KB). |
| `src/codegenie/plugins/manifest.py` (or equivalent Phase-3 loader location) | Extend manifest Pydantic models with `Phase4Config`. |
| `tests/unit/plugin/test_plugin_yaml_phase4_schema.py` | TDD red tests + per-rejection coverage. |
| `tests/integration/test_plugin_loads_phase4_config.py` | Smoke that round-trips real `plugin.yaml`. |
| `src/codegenie/rag/confidence.py` | Wire to read thresholds from manifest (surgical refactor of S5-02's defaults). |
| `src/codegenie/fallback/budget.py` | Wire to read budget caps from manifest (surgical refactor of S2-05's defaults). |

## Out of scope

- The prose contents of the skill templates (these are placeholder-acceptable here; the LLM-from-scratch cassette recording in S7-06 will iterate on the prose).
- The `cassettes.lock` manifest format (S3-05); this story only references the directory path.
- Phase-3 plugin manifest schema redesign — this story extends, does not redesign.

## Notes for the implementer

- The "calibration is config not code" framing from ADR-0008 is the durable invariant. Hardcoded `0.85` anywhere in the source after this story is a regression — the AST-walk acceptance bullet catches it.
- If S5-02 or S2-05 was already written with hardcoded defaults at story-write time (S5-04 may have shipped first), the refactor is *surgical*: change the constructor signature to accept the value, pass it from the plugin TCCM at construction time. Do not "improve" anything else in those modules (Global Rule 3).
- The "high_floor > degraded_floor" rejection is the most important schema rule — without it, the two-threshold band collapses silently and `RagDegraded` becomes unreachable. Surface loudly per Global Rule 12 if any code path can short-circuit the check.
- The skill `.md` files can contain placeholder prose (e.g., "# Skill: vulnerability remediation, major-bump\n\nTODO: refined during S7-06 cassette recording.") — the test asserts the *frontmatter* shape, not the body content. Document this clearly in the file headers so future maintainers don't take the placeholder as final.
- Plugin-load failure must be **loud** (Global Rule 12): `PluginManifestError` with diagnostic naming the offending key and the file path. A silent `KeyError` from a downstream `manifest.fallback.thresholds.high_floor` access is the wrong failure mode.
