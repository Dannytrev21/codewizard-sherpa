# Story S3-03 — Envelope cross-probe `if/then` dependency rule

**Step:** Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)
**Status:** Ready
**Effort:** S
**Depends on:** S3-01 (`IndexHealthProbe` populates `slice.cve.confidence` whenever the `cve_scan` peer is present)
**ADRs honored:** ADR-0011 (`IndexHealthProbe` is the honesty oracle; `cve` domain confidence is the structural witness), ADR-0004 from Phase 1 (`additionalProperties: false` envelope discipline), Phase 1 ADR's schema-evolution policy (extended in this phase via S2-07)

## Context

The envelope schema (`repo_context.schema.json`) gets the **first cross-probe `if/then` dependency rule** in Phase 2: if the `cve_scan` slice is present in the envelope, then `index_health.cve.confidence` **must** be present. This is the structural enforcement of ADR-0011's "honesty oracle" promise: a consumer (e.g., Phase 3 vuln-remediation) reading `cve_scan.matches[*].cve_id` can trust the data only if it can also read B2's `index_health.cve.confidence` and decide whether the CVE feed is fresh enough. Without the rule, a future bug that drops B2's `cve` domain (or fails it silently) lets a stale CVE feed look fresh.

This story adds the JSON Schema Draft 2020-12 `if/then` rule at the envelope root, ships the integration test that proves the rule fires, and documents the rule in `SCHEMA-EVOLUTION-POLICY.md` (from S2-07) as the canonical example of a cross-probe `if/then`. This is the seam every future cross-probe rule will copy (`phase-arch-design.md "Conflict-resolution table" D15-adjacent`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #5` IndexHealthProbe **cross-probe schema dependency** — the JSON Schema `if/then` block (literal copy-paste source for this story).
  - `../phase-arch-design.md §"Data model"` — the `if/then` rule appears verbatim at the bottom of the section.
  - `../phase-arch-design.md §"Goals" #11` — "envelope's `if-then` schema rule that ties `cve_scan` to `index_health.cve.confidence`".
- **Phase ADRs:**
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — ADR-0011 — the rule's *raison d'être* (honesty oracle integrity).
- **Source design:**
  - `../final-design.md §"Components" #11` Schema validator — `if/then` enforcement at envelope write time.
  - `../final-design.md §"Conflict-resolution table"` D15-adjacent commentary.
- **High-level impl:**
  - `../High-level-impl.md §"Step 3"` deliverable bullet for the envelope `if/then` rule.
- **Existing code (Phase 0/1 + Step 2/3 output):**
  - `src/codegenie/schema/repo_context.schema.json` — envelope schema; this story adds the `if/then` block at the root.
  - `src/codegenie/schema/probes/index_health.schema.json` — sub-schema from S3-01; this story does **not** edit it (the `if/then` rule lives at the envelope, not the sub-schema).
  - `src/codegenie/coordinator/schema_validator.py` (or equivalent Phase 0 module) — validates the envelope on every gather; already supports Draft 2020-12 `if/then`.
  - `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` — landed in S2-07; this story appends the canonical first-cross-probe-`if/then` example.

## Goal

Extend `repo_context.schema.json` with the Draft 2020-12 `if/then` rule that requires `index_health.cve.confidence` to be present whenever the `cve_scan` slice is present, ship the integration test asserting the rule fires on a synthetic envelope, and document the rule as the canonical first cross-probe `if/then` in `SCHEMA-EVOLUTION-POLICY.md`.

## Acceptance criteria

- [ ] `src/codegenie/schema/repo_context.schema.json` declares, at its root, the Draft 2020-12 `if/then` block from `phase-arch-design.md §"Component design" #5`:
  ```json
  {
    "if":   { "properties": { "probes": { "required": ["cve_scan"] } } },
    "then": { "properties": { "probes": { "properties": {
              "index_health": { "properties": { "cve": { "required": ["confidence"] } } }
            }}}}
  }
  ```
- [ ] `$schema` at the envelope root is `https://json-schema.org/draft/2020-12/schema` (already in place from Phase 0; verify, do not regress).
- [ ] Red test exists and was committed failing; green test in `tests/integration/test_schema_cross_probe_dependency.py` covers:
  - (a) Synthetic envelope with `probes.cve_scan` present **and** `probes.index_health.cve.confidence` present → `SchemaValidator().validate(envelope)` succeeds.
  - (b) Synthetic envelope with `probes.cve_scan` present **and** `probes.index_health.cve.confidence` **absent** → `SchemaValidationError` raised; error message references the missing `confidence` key (JSON Pointer `/probes/index_health/cve/confidence` or an equivalent path).
  - (c) Synthetic envelope with `probes.cve_scan` **absent** → `SchemaValidator().validate(envelope)` succeeds regardless of whether `probes.index_health.cve` is present.
- [ ] `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` (from S2-07) gains a new section "**First cross-probe `if/then` (Phase 2 S3-03)**" with the rule's text, the cross-link back to ADR-0011, and the integration-test path.
- [ ] `SchemaValidator` is **not edited** in this story — the validator already supports Draft 2020-12; if the test fails because the validator silently ignores `if/then`, file a P0 bug on the Phase 0 validator before proceeding.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` (on any new Python helper added; none expected), and the integration test all pass.
- [ ] PR body explicitly cross-links ADR-0011 and notes that this is the **first** cross-probe `if/then` — future rules copy this seam.

## Implementation outline

1. **Locate the envelope root** in `src/codegenie/schema/repo_context.schema.json`. Add a top-level `allOf` entry (or extend the existing one) containing the `if/then` block — keep additivity over the existing `properties` definitions so the rule composes cleanly with `additionalProperties: false`.
2. **Self-validate the schema** via `jsonschema.Draft202012Validator.check_schema(...)` — confirm the new construct is syntactically valid before running the integration test.
3. **Write the integration test** at `tests/integration/test_schema_cross_probe_dependency.py` per the three branches above. Build the three synthetic envelopes inline (no fixture files needed; the smallest minimal envelope that satisfies the rest of the envelope is fine).
4. **Document** the rule in `SCHEMA-EVOLUTION-POLICY.md`: append a "Cross-probe `if/then` rules" section listing this rule as item 1, with the literal `if/then` block, the ADR-0011 cross-link, and the integration-test path.
5. **PR body** explicitly notes (a) this is the first cross-probe `if/then`; (b) future `if/then` rules use the same seam; (c) the rule is a hard schema constraint (not a probe-internal soft check).

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/integration/test_schema_cross_probe_dependency.py`.

```python
# tests/integration/test_schema_cross_probe_dependency.py
"""Pins: cve_scan present ⇒ index_health.cve.confidence present.
Traces to: phase-arch-design.md §Component design #5 cross-probe dependency;
ADR-0011; final-design.md §Components #11."""
import pytest
from codegenie.coordinator.schema_validator import SchemaValidator, SchemaValidationError

def _envelope(probes: dict) -> dict:
    # Minimal envelope shape; the rest is whatever Phase 0/1 require.
    return {
        "schema_version": "v1",
        "gather_completed_utc": "2026-05-12T00:00:00Z",
        "probes": probes,
    }

def test_cve_scan_present_and_index_health_cve_confidence_present_validates():
    env = _envelope({
        "cve_scan": {"matches": []},
        "index_health": {"cve": {"confidence": "high"}},
    })
    SchemaValidator().validate(env)   # no raise

def test_cve_scan_present_without_index_health_cve_confidence_fails():
    env = _envelope({
        "cve_scan": {"matches": []},
        "index_health": {"cve": {}},   # confidence missing
    })
    with pytest.raises(SchemaValidationError) as exc:
        SchemaValidator().validate(env)
    assert "confidence" in str(exc.value)

def test_cve_scan_absent_validates_regardless():
    env = _envelope({
        "index_health": {"cve": {}},   # confidence missing — but cve_scan absent
    })
    SchemaValidator().validate(env)   # no raise
```

Run `pytest tests/integration/test_schema_cross_probe_dependency.py -q`. Expect either the validator to accept the missing-confidence envelope (the rule isn't there yet) or test fixtures to fail loading. Commit red.

### Green — smallest impl shape

1. Add the `if/then` block to `src/codegenie/schema/repo_context.schema.json`.
2. Run the test. It should turn green.
3. Append the `SCHEMA-EVOLUTION-POLICY.md` section.

### Refactor — bounded cleanup

- The `if/then` block's indentation should match the rest of `repo_context.schema.json` exactly. If the existing file uses 2-space indent, this addition does the same.
- Do **not** factor the rule into a `$ref` or `$defs` block in this story — the rule lives literally at the envelope root. Future cross-probe rules may motivate a `$defs/cross_probe_rules` section; that's a separate ADR (additive).
- Confirm the schema file still parses via `python -c "import json; json.load(open('src/codegenie/schema/repo_context.schema.json'))"`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/schema/repo_context.schema.json` | Edit — add Draft 2020-12 `if/then` block at the root |
| `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` | Edit — append "Cross-probe `if/then` rules" section |
| `tests/integration/test_schema_cross_probe_dependency.py` | New — three-branch integration test |

## Out of scope

- **Other cross-probe rules** — e.g., "if `build_graph.resolution_status == resolved` then `node_manifest.lockfile_present == true`". This story lands the **first** rule and the seam; subsequent rules are separate stories per ADR-amend.
- **`SchemaValidator` capability changes** — the validator already supports Draft 2020-12. If it doesn't, **stop and file a Phase 0 P0 bug**; do not patch the validator inside this story.
- **`IndexHealthProbe` behavior changes** — S3-01 already populates `slice.cve.confidence` whenever the `cve_scan` peer is present; this story only enforces the structural rule.
- **`--strict` CLI flag** — S3-04 owns the CLI exit-code mapping; this story is the **schema-level** enforcement, independent of strict mode.
- **Adversarial fixture** — no adversarial test for this story; the three-branch unit/integration coverage is sufficient. The seeded-staleness integration tests in Step 8 (S8-04) re-exercise the rule end-to-end on a real envelope.

## Notes for the implementer

- The rule **does not** require `index_health.cve` to exist — it only requires that *if* `index_health.cve` exists *and* `cve_scan` is present, the `confidence` field is populated. This matches the architectural spec: the `index_health` slice itself is optional at the envelope level (per Phase 1 ADR-0010 carryover), but **once present**, `cve.confidence` is required when `cve_scan` is too. Confirm by reading the `then` clause carefully: `properties.index_health.properties.cve.required: ["confidence"]` is conditional on `index_health.cve` being present.
- A future variant ("if `cve_scan` present then `index_health` slice **must** be present") would be a stricter rule. Phase 2 ships the looser form because B2's `applies()` may degrade in edge cases (corrupted git repo, no upstream peer at all). If a downstream consumer needs the stricter form, file a follow-up.
- The `SchemaValidationError` message format depends on which jsonschema library version Phase 0 pinned. The test asserts `"confidence" in str(exc.value)` — that's loose enough to survive library upgrades. Do **not** tighten it to a specific JSON Pointer match; the structural-witness is the error type, not the message text.
- The `SCHEMA-EVOLUTION-POLICY.md` entry should include a code block with the literal `if/then` JSON. Copy-paste from `phase-arch-design.md` (don't retype). This is the canonical seam — future readers paging through the policy doc need the literal text.
- Cross-link from the policy section back to ADR-0011 by relative path `../../02-context-gather-layers-b-g/ADRs/0011-index-health-advisory-budget-and-strict-flag.md` (or via the local `ADRs/` relative if the policy doc lives in the same folder — check S2-07 for the path convention before linking).
- If the existing `repo_context.schema.json` already has an `allOf` at the root, **append** to it; do **not** create a sibling `if/then` at the root level alongside an `allOf` (some validators handle this awkwardly). Keep the rule inside the `allOf` array for compositional safety.
