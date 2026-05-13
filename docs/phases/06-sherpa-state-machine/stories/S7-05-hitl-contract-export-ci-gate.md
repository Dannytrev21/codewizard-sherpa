# Story S7-05 — Export `docs/contracts/hitl-v0.6.0.json` + CI gate

**Step:** Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)
**Status:** Ready
**Effort:** S
**Depends on:** S7-04 (the malformed-decision canary pins the contract shape this exporter writes; landing the exporter before S7-04 would let a contract shift slip through the seven-case parametrization). Transitively: S1-03 (`HumanRequest` and `HumanDecision` Pydantic models — the JSON-schema generator's input).
**ADRs honored:** ADR-0008 (HITL operator-auth deferred to Phase 11; the contract export *is* the seam Phase 11 will consume or amend — ADR-0008 §Consequences explicitly states *"The HITL contract is exported to `docs/contracts/hitl-v0.6.0.json` and Phase 11's design review is **required** to either consume this shape or amend it via a new ADR"*). Reinforces the cross-phase preservation discipline: Phase 11's signal source (GitHub webhook, Slack, MCP) integrates by *producing* this exact shape, not by amending Phase 6.

## Context

Phase 6 ships the HITL contract; Phase 11 ships the HITL signal source. The seam between them is a committed JSON-schema file. This story makes the seam *explicit*: it lands the exporter that emits the schema from the live Pydantic models, commits the v0.6.0 schema to `docs/contracts/`, and wires a CI gate that diffs the committed file against a fresh export. Any divergence — intentional or accidental — fails CI and forces the author to either:

1. Update the committed file deliberately (intentional contract change; the PR description must name the rationale + the consuming Phase 11 ADR), or
2. Revert the Pydantic-model change (the contract was about to drift silently).

The exporter is invoked via `python -m codegenie.graph.hitl --export`. The standard idiom (Phase 0's `python -m codegenie.contracts --emit` pattern, if it exists) is the reference; if there's no in-repo precedent, this story establishes the convention. The exporter must:

- Generate the schema using `HumanRequest.model_json_schema()` + `HumanDecision.model_json_schema()`.
- Produce a single combined JSON document with both schemas under `$defs`, plus a top-level `title`, `description`, and `version` field.
- Write canonical JSON (sorted keys, `indent=2`, trailing newline) so the diff against the committed file is reproducible byte-for-byte.
- Pin `schema_version: "v0.6.0"` literal (matching `VulnLedger.schema_version`'s Literal pin per ADR-0005).
- Include the **three Literal action values** (`continue`, `override`, `abort`) as an explicit enum in the schema so a Phase 11 consumer can validate without reading Python source.
- Mark all `extra="forbid"` Pydantic constraints as JSON-schema `additionalProperties: false`.

The CI gate runs the exporter, captures stdout, diffs against `docs/contracts/hitl-v0.6.0.json`, fails on non-zero diff. The gate is a small pytest test under `tests/contracts/` plus a pre-commit hook for local feedback.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 "HumanRequest / HumanDecision / await_human"` — the typed models the exporter consumes.
  - `../phase-arch-design.md §"Public surface"` (G16) — one HITL contract pair shipped; no new ABCs.
  - `../phase-arch-design.md §Integration with Phase 7+ / Phase 11+` — Phase 7 extends `reason` Literals; Phase 11 either consumes or amends.
- **Phase ADRs:**
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — names the exported contract path explicitly; the "Phase 11's design review is required to either consume this shape or amend it" clause is the contract this story makes operational.
- **High-level-impl:** `../High-level-impl.md §Step 7`: *"HITL contract exported to `docs/contracts/hitl-v0.6.0.json` via `python -m codegenie.graph.hitl --export`. CI gate diffs `docs/contracts/hitl-v0.6.0.json` against the committed file; PR must update deliberately on shape change."* And `§Step 10` (deliverables) confirms the contract export is the final Phase 6 deliverable that must ship before Phase 7's design review.
- **Source design:** `../final-design.md §Component 7 "HITL contract"`.
- **Prior phases:** if Phase 3 / 4 / 5 ship analogous contract-export gates (e.g., a `python -m codegenie.contracts --emit` for `RecipeSelection` or `AttemptSummary`), reuse the idiom verbatim. The user-rule §11 "Match the codebase's conventions" applies.

## Goal

Land the `python -m codegenie.graph.hitl --export` CLI entry point that emits the canonical v0.6.0 HITL JSON-schema to stdout; commit the resulting `docs/contracts/hitl-v0.6.0.json` file with the canonical contents; and ship `tests/contracts/test_hitl_v0_6_0_schema_drift.py` (or analogous path) that runs the exporter and asserts byte-equality with the committed file. The PR description for any future change to either `HumanRequest` or `HumanDecision` must include the regenerated schema diff as a load-bearing review concern.

## Acceptance criteria

- [ ] `src/codegenie/graph/hitl.py` exposes a `__main__`-runnable export entry: `python -m codegenie.graph.hitl --export` writes the canonical JSON-schema to stdout and exits 0.
- [ ] **The schema document shape:**
  ```json
  {
    "title": "codegenie HITL contract",
    "description": "Typed human-in-the-loop contract for Phase 6 vuln-remediation. Phase 11 either consumes this shape or amends via a new ADR.",
    "schema_version": "v0.6.0",
    "phase_origin": "phase-6-sherpa-state-machine",
    "adrs": ["ADR-0008-hitl-operator-auth-deferred-to-phase11"],
    "$defs": {
      "HumanRequest": { ...HumanRequest.model_json_schema()... },
      "HumanDecision": {
        ...HumanDecision.model_json_schema()...,
        "properties": {
          "action": {"type": "string", "enum": ["continue", "override", "abort"]},
          "operator": {"type": "string", "minLength": 1},
          "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
          "at": {"type": "string", "format": "date-time"}
        },
        "required": ["action", "operator", "at"],
        "additionalProperties": false
      }
    }
  }
  ```
  The shape above is illustrative; the exact JSON-schema serialization Pydantic produces is what gets committed. The story does not invent a shape; it captures Pydantic's output canonically.
- [ ] **Canonical JSON output.** The exporter writes:
  - `indent=2` (human-readable).
  - `sort_keys=True` (deterministic ordering).
  - Trailing newline (POSIX file convention).
  - Unicode normalized (UTF-8, no BOM).
  - `ensure_ascii=False` (Pydantic-native; if a future field includes non-ASCII, it's not escape-encoded).
  - The CI gate's diff is reproducible byte-for-byte.
- [ ] **Committed contract file.** `docs/contracts/hitl-v0.6.0.json` exists, is the canonical output of `python -m codegenie.graph.hitl --export` at the time of commit, and is ≤ 8 KB.
- [ ] **The three Literal action values appear explicitly** in the schema as a JSON-schema `enum`. Inspecting the file with `jq '.["$defs"].HumanDecision.properties.action.enum'` returns `["continue", "override", "abort"]` (or whatever order Pydantic emits — verify against the live model).
- [ ] **`additionalProperties: false`** appears in both `HumanRequest` and `HumanDecision` schemas (the `extra="forbid"` Pydantic constraint). Verifiable via `jq '.["$defs"].HumanDecision.additionalProperties'` returning `false`.
- [ ] **CI drift gate.** `tests/contracts/test_hitl_v0_6_0_schema_drift.py` exists, runs the exporter as a subprocess (or imports the export function directly), captures stdout, reads `docs/contracts/hitl-v0.6.0.json`, asserts `live_export == committed_file` byte-for-byte. On mismatch, the test failure message prints `difflib.unified_diff` so the on-call sees the changed field.
- [ ] **Pre-commit hook.** `.pre-commit-config.yaml` (or `tools/pre-commit/`) adds an entry that runs the export-and-diff check locally before commit. The hook only fires when `src/codegenie/graph/hitl.py` is staged (no need to re-export on unrelated changes).
- [ ] **Schema validates against itself.** A sub-test in the drift-gate file loads the JSON-schema with `jsonschema.Draft202012Validator(schema)` and confirms it's a syntactically valid JSON-schema (no malformed `$ref`, no broken `$defs` references). Independent sanity check beyond byte-equality.
- [ ] **Schema validates the malformed payloads from S7-04 as invalid.** The test loads the schema, instantiates a `Draft202012Validator`, and confirms each of S7-04's seven malformed-payload cases fails validation. This is the *consumer-side* contract check: Phase 11, validating an incoming payload against the schema, must reject the same shapes the Pydantic model rejects.
- [ ] **Schema validates a well-formed `HumanDecision` as valid.** Round-trip: `HumanDecision(action="continue", operator="alice", at=now).model_dump(mode="json")` → `jsonschema.validate(payload, schema)` → no error.
- [ ] **No emojis, no trailing whitespace, no CRLF.** Standard file-hygiene checks pass on the committed file.
- [ ] **PR documentation requirement.** The schema's top-level `description` field names the cross-phase commitment: "Phase 11 either consumes this shape or amends via a new ADR; the contract is committed at v0.6.0 and a version bump (to v0.7.0) is the deliberate path."
- [ ] **Phase 11 forward-reference.** A line in `docs/contracts/README.md` (or new file) lists the v0.6.0 contract under "Active HITL contracts" and names Phase 11 as the consumer-or-amender. This is the surface a Phase 11 implementer reads first.
- [ ] **`mypy --strict src/codegenie/graph/hitl.py tests/contracts/test_hitl_v0_6_0_schema_drift.py`** passes. `ruff check` + `ruff format --check` pass.

## Implementation outline

1. **`src/codegenie/graph/hitl.py` `__main__` block.** Add the export entry. The function `export_contract() -> str` returns the canonical JSON string; the `__main__` block calls it and prints. Reusable for the test (the test imports `export_contract` directly, sidestepping subprocess overhead).
2. **Schema assembly.** Combine `HumanRequest.model_json_schema()` and `HumanDecision.model_json_schema()` under a top-level wrapper with `title`, `description`, `schema_version`, `phase_origin`, `adrs`, `$defs`. The wrapper is hand-coded; the per-model schemas are Pydantic-emitted.
3. **Canonical serialization.** `json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`. The trailing newline is the POSIX convention; without it, `git diff` shows a "no newline at end of file" marker.
4. **Commit `docs/contracts/hitl-v0.6.0.json`.** Run the exporter; redirect to the file; commit.
5. **Test scaffold.** `tests/contracts/test_hitl_v0_6_0_schema_drift.py` runs the exporter (in-process or subprocess), reads the file, asserts equality.
6. **Pre-commit hook.** Add to `.pre-commit-config.yaml` a `hitl-contract-drift` hook that runs the same check; only triggers when `hitl.py` is staged.

## TDD plan — red / green / refactor

### Red

Path: `tests/contracts/test_hitl_v0_6_0_schema_drift.py`

```python
"""ADR-0008 canary: docs/contracts/hitl-v0.6.0.json is the load-bearing seam between
Phase 6 (HITL contract) and Phase 11 (HITL signal source). Any change to HumanRequest
or HumanDecision shape must regenerate this file deliberately; the CI gate fails on
silent drift.

Regeneration procedure (intentional contract change):
1. Modify HumanRequest or HumanDecision in src/codegenie/graph/hitl.py.
2. Run: python -m codegenie.graph.hitl --export > docs/contracts/hitl-v0.6.0.json
3. Bump schema_version to v0.7.0 if the change is breaking (additive Literal extension is
   non-breaking; required-field removal or rename is breaking).
4. Update this test's expected file path (s/v0.6.0/v0.7.0/) and the Phase 11 ADR
   referenced in the schema's `adrs` field.
5. Land all changes in the same PR with a description naming the Phase 11 consumer impact.
"""

import difflib
import json
from pathlib import Path
import jsonschema
import pytest
from codegenie.graph.hitl import HumanDecision, export_contract

_COMMITTED_CONTRACT = Path("docs/contracts/hitl-v0.6.0.json")

@pytest.mark.contracts
def test_committed_contract_matches_live_export_byte_for_byte() -> None:
    live = export_contract()
    committed = _COMMITTED_CONTRACT.read_text(encoding="utf-8")
    if live != committed:
        diff = "\n".join(difflib.unified_diff(
            committed.splitlines(),
            live.splitlines(),
            fromfile=str(_COMMITTED_CONTRACT),
            tofile="<live export>",
            lineterm="",
        ))
        pytest.fail(
            "HITL contract DRIFT detected — committed file does not match live export.\n"
            "Regeneration procedure: python -m codegenie.graph.hitl --export > "
            f"{_COMMITTED_CONTRACT}\n\n{diff}"
        )

@pytest.mark.contracts
def test_committed_contract_is_valid_jsonschema() -> None:
    schema = json.loads(_COMMITTED_CONTRACT.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

@pytest.mark.contracts
def test_action_enum_contains_exactly_three_literals() -> None:
    schema = json.loads(_COMMITTED_CONTRACT.read_text(encoding="utf-8"))
    action = schema["$defs"]["HumanDecision"]["properties"]["action"]
    assert set(action["enum"]) == {"continue", "override", "abort"}

@pytest.mark.contracts
def test_additional_properties_false_on_both_models() -> None:
    schema = json.loads(_COMMITTED_CONTRACT.read_text(encoding="utf-8"))
    assert schema["$defs"]["HumanRequest"]["additionalProperties"] is False
    assert schema["$defs"]["HumanDecision"]["additionalProperties"] is False

@pytest.mark.contracts
@pytest.mark.parametrize("payload", [
    {"action": "approve", "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
    {"action": "", "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
    {"action": "continue", "at": "2026-05-12T12:00:00+00:00"},  # missing operator
    {"action": "continue", "operator": "alice", "at": "2026-05-12T12:00:00+00:00",
     "rogue_field": True},  # extra forbid
])
def test_committed_contract_rejects_malformed_payloads(payload: dict) -> None:
    schema = json.loads(_COMMITTED_CONTRACT.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema["$defs"]["HumanDecision"])
    errors = list(validator.iter_errors(payload))
    assert len(errors) > 0, f"Schema accepted malformed payload {payload}"

@pytest.mark.contracts
def test_committed_contract_accepts_well_formed_decision() -> None:
    from datetime import datetime, UTC
    decision = HumanDecision(action="continue", operator="alice", note=None,
                             at=datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC))
    payload = decision.model_dump(mode="json")
    schema = json.loads(_COMMITTED_CONTRACT.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema["$defs"]["HumanDecision"])
    errors = list(validator.iter_errors(payload))
    assert errors == [], f"Schema rejected well-formed payload: {errors}"
```

Run; commit red (the committed file doesn't exist yet, and `export_contract` isn't defined).

### Green

- Implement `export_contract()` in `src/codegenie/graph/hitl.py`.
- Run `python -m codegenie.graph.hitl --export > docs/contracts/hitl-v0.6.0.json`.
- Commit both files.
- Run the test; iterate.

### Refactor

- **Do not split the test file by concern.** All six sub-tests share the same `_COMMITTED_CONTRACT` constant; keeping them together makes the contract-canary discipline obvious.
- **`export_contract()` is a function, not a class.** This is a one-shot serializer; no state, no instance.
- **The pre-commit hook is shell-based** (`python -m codegenie.graph.hitl --export | diff - docs/contracts/hitl-v0.6.0.json`); no need for a Python entry point.
- **Do not skip the `Draft202012Validator.check_schema` call.** Without it, the schema could be malformed JSON-schema (invalid `$ref`, broken `$defs`) and Phase 11 would consume it and crash.
- **The well-formed-payload round-trip test pins the producer-consumer symmetry.** A regression where Pydantic emits a payload the schema rejects (or vice versa) is the failure mode this catches; without it, the contract could silently diverge between the model and the exported schema.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/hitl.py` | Extend — add `export_contract() -> str` and `__main__` entry point. |
| `docs/contracts/hitl-v0.6.0.json` | New — the committed canonical contract. |
| `docs/contracts/README.md` | New (or extend) — index of active contracts; HITL v0.6.0 entry; Phase 11 forward-reference. |
| `tests/contracts/test_hitl_v0_6_0_schema_drift.py` | New — the drift CI gate. |
| `.pre-commit-config.yaml` | Extend — `hitl-contract-drift` hook. |
| `pyproject.toml` | Extend — `jsonschema` dev dependency if not already pinned. |

## Out of scope

- **Phase 11's signal source design.** That's a Phase 11 story; this story only commits the seam.
- **Operator authentication signature fields on `HumanDecision`.** Deferred to Phase 11/16; if Phase 11 adds a `signature: bytes` field additively, the schema bumps to v0.7.0 (additive non-breaking).
- **A general contract-export framework.** If Phase 3/4/5 already ship analogous gates, this story matches their idiom; if not, this story does *not* generalize the pattern to all phases. Each phase ships its own contract export when ready.
- **JSON-schema in YAML form.** The contract is JSON only — JSON-schema is a JSON standard; YAML conversion is consumer-side concern.
- **Versioning policy for contract bumps.** A future ADR (not this story) can codify "additive Literal extension = patch bump (v0.6.0 → v0.6.1); breaking change = minor bump (v0.6.0 → v0.7.0)"; this story commits v0.6.0 and leaves versioning policy to whichever phase first encounters a bump.
- **Phase 4 / Phase 5 contract exports.** Each phase owns its own.

## Notes for the implementer

- **The CI gate is binary and informative.** A single drift produces a clear `pytest.fail` with `unified_diff`; the on-call sees exactly which JSON field shifted. No silent acceptance, no fuzzy comparison.
- **The well-formed-payload round-trip test is the load-bearing producer-consumer symmetry check.** Pydantic's `model_json_schema()` can occasionally produce schemas that don't exactly match the model's validation behavior (`format: date-time` is a notorious example — Pydantic accepts more datetime strings than the JSON-schema `format` validator does). If the round-trip test fails, the schema needs hand-fixup to match the model. Document the fixup in the exporter.
- **Versioning the file by filename, not by content.** `hitl-v0.6.0.json`'s filename pins the version externally; the file's `schema_version` field pins it internally. Both must agree. A future v0.7.0 commits a *new* file `hitl-v0.7.0.json` rather than overwriting v0.6.0 — Phase 11 (or any consumer) pins their dependency by filename and migrates deliberately.
- **The `$defs` pattern lets Phase 7+ extend the contract without breaking Phase 6.** Phase 7 might add new `reason` Literals (e.g., `"base_image_unavailable"`) to `HumanRequest.reason`; the additive extension lands as v0.7.0 with a new `hitl-v0.7.0.json` file; Phase 6 keeps consuming v0.6.0 unchanged. Cross-phase contract evolution is the whole point.
- **`jsonschema` is the standard library for JSON-schema validation in Python.** Use `Draft202012Validator` (the modern draft). The older `Draft7Validator` is also fine if `pyproject.toml` pins jsonschema < the version that requires 2020-12 syntax; check the existing repo's conventions first.
- **Why subprocess invocation is not used in the test.** Direct import of `export_contract` is faster (no Python startup overhead) and lets the test catch import-side issues. The CI gate is also a pre-commit hook that *does* use subprocess (for shell-pipe convenience); the test is the in-process version.
- **`docs/contracts/README.md` is the Phase 11 implementer's first read.** Keep it short: a table of active contracts with one-line descriptions and the active-version filename. The Phase 11 design lead reading "HITL v0.6.0 — operator approval/override/abort decision; Phase 11 either consumes or amends" should immediately know where to look next.
- **Pre-commit hook scope.** Only fire when `src/codegenie/graph/hitl.py` is staged. A blanket "always re-export on commit" wastes time and creates noise. The pre-commit framework's `files: ^src/codegenie/graph/hitl\.py$` selector is the right idiom.
- **The committed file is ≤ 8 KB** as a soft upper bound — if the schema balloons (e.g., a future change adds 50 Literals), reconsider whether the contract is still atomic; consider splitting into per-model files. The 8 KB number isn't load-bearing; it's a sanity check.
- **Effort sizing rationale.** S because (a) the exporter is ~30 LOC, (b) the test is ~80 LOC across six sub-tests, (c) the committed file is auto-generated, (d) the pre-commit hook is a 10-line YAML stanza. Total story size: ~150 LOC. A junior implementer should expect 2–3 hours; an experienced one ~1 hour. The discipline is in *getting the canonicalization rules right* (sort_keys + indent + trailing newline + UTF-8 without BOM); once those are set, the rest is mechanical.
- **Regression risk if this story is skipped:** very high. Without the gate, Phase 6 can ship `HumanDecision` and then a follow-up PR can silently add a fourth Literal value to `action`; Phase 11 reads the contract that was current at Phase 6's freeze, builds against it, and discovers the drift only when production fires `"approve_and_retry"` as an `action` value Phase 11's switch statement doesn't handle. The CI gate is cheap; the silent drift is expensive.
