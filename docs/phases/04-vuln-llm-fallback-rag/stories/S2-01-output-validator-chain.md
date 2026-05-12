# Story S2-01 — `OutputValidator` chain — parse_json → pydantic → canary → fence-residual → action-surface

**Step:** Step 2 — Ship the deterministic LLM-side primitives — `OutputValidator`, `PromptLoader` + YAML prompts, `LlmInvocationGuard`, `ApiKeyStore`
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-08
**ADRs honored:** ADR-P4-003, ADR-P4-008, ADR-P4-011

## Context

The `OutputValidator` is the structural defense at the output boundary — every byte the LLM emits is treated as adversarial until it survives the full chain. It is the load-bearing primitive that lets Phase 4 ship an Anthropic call without process isolation: Phase 3's hard-gates close the diff side; this validator closes the plan side. It is purely deterministic, dependency-free of `anthropic` or `chromadb`, and reused by both `InProcessLeafLlmAgent` (Step 3) and `JailedLeafLlmAgent` — so it lands first.

The action-surface check delegates to the `PathAllowlistProvider` registry from S1-08; the validator never edits its own allowlist when Phase 7 ships Chainguard.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 "OutputValidator"` — the public interface, the chain order, the `Plan` envelope, the strip rule for `confidence` / `self_confidence`.
  - `../phase-arch-design.md §"Edge cases"` rows 5–8 — the four reject branches the chain must cover.
  - `../phase-arch-design.md §"Process view"` (sequence) — `OutputValidator.validate` runs inside `LeafLlmAgent.invoke`, after streaming completes, before the `Plan` reaches `RagLlmEngine`.
- **Phase ADRs:**
  - `../ADRs/0003-plan-envelope-kind-and-target-files-allowlist.md` — ADR-P4-003 — `Plan.kind ∈ {recipe_invocation, manual_patch}`, `target_files` hard-coded npm allowlist at validation time, path-traversal rejection.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — four-defense stack: canary, fence-id, structural plan, Pydantic `extra="forbid"`. Strips `confidence` / `self_confidence` (`§"Decision"` final paragraph).
  - `../ADRs/0011-llm-prompt-context-exfiltration-boundary.md` — ADR-P4-011 — `PathAllowlistProvider` registry is the extension seam; never edit the validator to add a path.
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — facts-not-judgments; LLM self-reported confidence is not trust-bearing and must be stripped before any downstream consumer (e.g., `TrustScorer`) sees the response.
- **Source design:** `../final-design.md §"Components" #5 "OutputValidator + Canary"` — pure-function chain with first-failure short-circuit.
- **Existing code:**
  - `src/codegenie/llm/contract.py` (from S1-02) — `Plan`, `ManualPatch`, `RecipeInvocation`, `LlmResponse` Pydantic models; `extra="forbid", frozen=True` already set.
  - `src/codegenie/llm/path_allowlists/__init__.py` (from S1-08) — `PathAllowlistProvider` Protocol; `NpmPathAllowlistProvider` is the default registered for `task_class="vuln"`.
  - `src/codegenie/errors.py` (from S1-01) — `LlmOutputRejected` exception (raised by the caller, not by the validator itself; the validator returns `ValidatorOutput(passed=False, errors=...)`).

## Goal

Land `src/codegenie/llm/output_validator.py` exposing `OutputValidator.validate(response_text, expected_canary, plan_schema)` that runs a pure, first-failure-short-circuit chain — `parse_json → pydantic_validate(extra="forbid") → canary_check → canary_substring_scan → fence_residual_scan → action_surface_check` — strips `confidence` / `self_confidence` to a logged-only diagnostic, and rejects all eight edge cases enumerated in `phase-arch-design.md §"Edge cases"` rows 5–8 (`pydantic_extra_forbidden`, `canary_echo_failed`, `canary_substring_leak`, `fence_residual_detected`, `out_of_scope_action_surface`, path traversal).

## Acceptance criteria

- [ ] `src/codegenie/llm/output_validator.py` exports `ValidatorOutput` (Pydantic, `extra="forbid", frozen=True`, fields `passed: bool`, `errors: list[str]`, `plan: Plan | None`, `stripped_diagnostics: dict[str, object]`) and `OutputValidator` (no constructor args; reads `PathAllowlistProvider` from the registry at `validate()` time given a `task_class` kwarg defaulting to `"vuln"`).
- [ ] `validate(response_text, expected_canary, plan_schema, *, task_class="vuln")` runs the chain in exactly this order: `parse_json → pydantic_validate(extra="forbid") → canary_check → canary_substring_scan → fence_residual_scan → action_surface_check`. First failure returns `ValidatorOutput(passed=False, errors=[<one_reason>], plan=None)`; later checks are not executed.
- [ ] Each failure produces a stable, ADR-named reason string (consumed by Phase 5's retry-with-context per `ADR-P4-003 §"Consequences"`): `"parse_json_failed"`, `"pydantic_extra_forbidden"`, `"canary_echo_failed"`, `"canary_substring_leak"`, `"fence_residual_detected"`, `"out_of_scope_action_surface"`. Path traversal is reported as `"out_of_scope_action_surface"` (same reason; ADR-P4-003 §Decision paragraph 3 explicitly catches traversal under the subset check + a normalized-path regex).
- [ ] `confidence`, `confidence_pct`, `self_confidence`, `self_assessment` fields, **if present in the parsed JSON before Pydantic validation runs**, are popped into `stripped_diagnostics` and never reach `plan_schema`. The chain still passes (Pydantic `extra="forbid"` would otherwise reject them); the stripped values are logged via `logging.LLM_SELF_REPORTED_CONFIDENCE` (event constant from S1-01) at INFO and never enter the returned `Plan`.
- [ ] `canary_substring_scan` rejects on canary appearing anywhere outside `plan.canary_echo` (e.g., `plan.rationale`, `plan.intent`, `plan.manual_patch.diff`); the test must include a ROT13-of-canary string that does *not* trigger (we only forbid the literal canary string), proving the scan is not over-broad.
- [ ] `fence_residual_scan` rejects any `Plan` field whose string body contains `<UNTRUSTED_FROM=` or `</UNTRUSTED_FROM` markers — the LLM must never quote fences back into the structured response.
- [ ] `action_surface_check` resolves `target_files` against `PathAllowlistProvider` for the given `task_class`; the subset check normalizes each path with `os.path.normpath` first; any path containing `..` after normalization, any absolute path, or any path not in the allowlist after normalization fails with `"out_of_scope_action_surface"`.
- [ ] `OutputValidator` is pure: no I/O, no subprocess, no `anthropic` / `chromadb` / `pyyaml` imports, no logging side effects other than the stripped-confidence diagnostic.
- [ ] `tests/unit/llm/test_output_validator_extra_forbid.py`, `test_output_validator_canary.py`, `test_output_validator_fence_residual.py`, `test_output_validator_action_surface.py`, `test_path_traversal_in_target_files.py`, `test_output_validator_strips_self_confidence.py`, `test_output_validator_short_circuits.py` cover each branch and the short-circuit guarantee.
- [ ] TDD red test exists, committed on a tagged commit, and the green commit brings it green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write tests first (red) — one test file per chain step plus `test_output_validator_short_circuits.py` proving the chain stops at the first failure (mock subsequent checks to assert they are not called).
2. Implement `ValidatorOutput` Pydantic model alongside `OutputValidator` in `src/codegenie/llm/output_validator.py`.
3. Implement `validate` as a sequence of `_parse_json`, `_strip_self_confidence`, `_pydantic_validate`, `_canary_check`, `_canary_substring_scan`, `_fence_residual_scan`, `_action_surface_check` private helpers — each returns `None` on pass or a reason string on fail; `validate` short-circuits on the first non-`None`.
4. `_strip_self_confidence` operates on the raw parsed dict before `_pydantic_validate` so `extra="forbid"` does not reject them; it pops the four field names and writes them to `stripped_diagnostics`. Emit `logging.LLM_SELF_REPORTED_CONFIDENCE` event at INFO with `stripped_diagnostics` as a structured field.
5. `_action_surface_check`: only runs when `plan.kind == "manual_patch"` (recipe_invocation has no `target_files`); resolves `PathAllowlistProvider` via `get_path_allowlist(task_class)`; computes `normalized = [os.path.normpath(p) for p in plan.manual_patch.target_files]`; rejects on `any("../" in n or n.startswith("/") for n in normalized)` or `not set(normalized) <= allowlist`.
6. `_canary_substring_scan`: iterate `(plan.intent, plan.rationale, plan.manual_patch.diff if plan.manual_patch else "", every str field of plan.recipe_invocation if present)`; any occurrence of `expected_canary` in those strings is a leak.
7. `_fence_residual_scan`: same iteration; reject on any occurrence of `<UNTRUSTED_FROM=` or `</UNTRUSTED_FROM`.
8. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red

Test file path (representative): `tests/unit/llm/test_output_validator_action_surface.py`

```python
# tests/unit/llm/test_output_validator_action_surface.py
import json
import pytest
from codegenie.llm.output_validator import OutputValidator, ValidatorOutput
from codegenie.llm.contract import Plan


CANARY = "a" * 64  # 32 bytes hex = 64 chars


def _plan_json(*, target_files: list[str], canary: str = CANARY) -> str:
    return json.dumps({
        "kind": "manual_patch",
        "intent": "bump lodash to fix CVE-2024-12345",
        "canary_echo": canary,
        "rationale": "advisory says >=4.17.21 patches the proto pollution sink",
        "manual_patch": {
            "diff": "--- a/package.json\n+++ b/package.json\n@@ ...",
            "target_files": target_files,
        },
    })


def test_target_files_inside_npm_allowlist_pass():
    v = OutputValidator()
    out = v.validate(_plan_json(target_files=["package.json", "package-lock.json"]),
                     expected_canary=CANARY, plan_schema=Plan)
    assert out.passed is True
    assert out.errors == []
    assert out.plan is not None


def test_source_rewrite_rejected_with_out_of_scope_action_surface():
    v = OutputValidator()
    out = v.validate(_plan_json(target_files=["src/index.js"]),
                     expected_canary=CANARY, plan_schema=Plan)
    assert out.passed is False
    assert out.errors == ["out_of_scope_action_surface"]
    assert out.plan is None  # rejection drops the plan


def test_path_traversal_rejected_with_out_of_scope_action_surface():
    v = OutputValidator()
    out = v.validate(_plan_json(target_files=["package.json", "../../etc/passwd"]),
                     expected_canary=CANARY, plan_schema=Plan)
    assert out.passed is False
    assert out.errors == ["out_of_scope_action_surface"]


def test_absolute_path_rejected_even_if_name_matches():
    v = OutputValidator()
    out = v.validate(_plan_json(target_files=["/etc/package.json"]),
                     expected_canary=CANARY, plan_schema=Plan)
    assert out.passed is False
    assert out.errors == ["out_of_scope_action_surface"]
```

A second representative test asserts the short-circuit:

```python
# tests/unit/llm/test_output_validator_short_circuits.py
from unittest.mock import patch
from codegenie.llm.output_validator import OutputValidator
from codegenie.llm.contract import Plan


def test_chain_stops_on_first_failure():
    v = OutputValidator()
    # Malformed JSON triggers parse_json_failed; later checks must not run.
    with patch.object(v, "_canary_check") as canary_check, \
         patch.object(v, "_action_surface_check") as action_check:
        out = v.validate("not-json{", expected_canary="x" * 64, plan_schema=Plan)
    assert out.passed is False
    assert out.errors == ["parse_json_failed"]
    canary_check.assert_not_called()
    action_check.assert_not_called()
```

Run; both tests fail because `OutputValidator` does not exist. Commit as red.

### Green

Implement `OutputValidator` per the outline above. Minimum shape: a module with `ValidatorOutput` + `OutputValidator.validate` running the seven private helpers in order, returning on first non-`None` reason.

### Refactor

- Add docstrings to every private helper naming the ADR clause it enforces.
- Add `mypy --strict` type hints; `validate` returns `ValidatorOutput`, helpers return `str | None`.
- Add structured-log call to `logging.LLM_SELF_REPORTED_CONFIDENCE` for stripped fields with `canary_fingerprint=blake3(canary)[:8]` rather than the canary bytes.
- Re-run the full chain test matrix; confirm no helper does I/O.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/llm/output_validator.py` | New — the validator chain |
| `tests/unit/llm/test_output_validator_extra_forbid.py` | Pydantic `extra="forbid"` rejection |
| `tests/unit/llm/test_output_validator_canary.py` | Missing / wrong / leaked canary |
| `tests/unit/llm/test_output_validator_fence_residual.py` | Fence markers leaked into Plan body |
| `tests/unit/llm/test_output_validator_action_surface.py` | npm allowlist subset check |
| `tests/unit/llm/test_path_traversal_in_target_files.py` | `..` and absolute-path rejection |
| `tests/unit/llm/test_output_validator_strips_self_confidence.py` | Stripping `confidence` / `self_confidence` before Pydantic |
| `tests/unit/llm/test_output_validator_short_circuits.py` | First-failure short-circuit guarantee |

## Out of scope

- **Canary minting and fence-id randomization** — owned by `PromptLoader` / `PromptBuilder` in **S2-02**. The validator receives the expected canary as an argument; it does not generate it.
- **Raising `LlmOutputRejected`** — the caller (`LeafLlmAgent.invoke` in **S3-02 / S3-05**) raises on `passed=False`; the validator returns `ValidatorOutput` and does not raise.
- **Emitting `llm.output_rejected` / `canary.echo_failed` / `fence.residual_detected` audit events** — those land at the call site in **S3-02**. The validator only emits the `LLM_SELF_REPORTED_CONFIDENCE` diagnostic.
- **Registry mechanics for `PathAllowlistProvider`** — already shipped by **S1-08**. This story consumes the registry; it does not extend it.
- **`Plan` schema definition** — shipped by **S1-02**. This story imports `Plan` and does not edit it.
- **Adversarial corpus** — ROT13 / fence-collision regression suites live in **S7-01 / S7-02**. This story ships unit-level coverage only.

## Notes for the implementer

- The order in the chain is load-bearing: `parse_json` must run before `_strip_self_confidence` (you need a dict to pop from) and `_strip_self_confidence` must run before `_pydantic_validate` (Pydantic `extra="forbid"` would otherwise reject these fields and crash the chain before strip). Document this ordering in the module docstring.
- `_canary_substring_scan` must walk the *post-Pydantic* `Plan` — `canary_echo` is the only field where the canary is legal; everywhere else is a leak. Don't substring-scan the raw `response_text` (that would always find the canary because `canary_echo` is in there).
- `_fence_residual_scan` does *not* run on `response_text` either; it runs on `Plan` field bodies. The LLM is allowed to receive fences in the prompt; it is never allowed to quote them back in the structured response.
- Resist adding a `try / except` wrapper around the whole `validate` — exceptions inside helpers indicate a bug (e.g., a missing field that Pydantic should have caught); let them propagate so the test surface stays honest.
- `os.path.normpath` collapses `package.json/./../package.json` to `package.json`, which is fine; what we are catching is `..` *outside* the allowlist set. The absolute-path check (`startswith("/")`) catches `/etc/package.json` where the basename matches but the path is escape-shaped.
- Do not log the canary bytes — log `blake3(canary)[:8]` per ADR-P4-013 / ADR-P4-008 §"Consequences".
- The `stripped_diagnostics` field on `ValidatorOutput` is **logged-only**; do not feed it to `TrustScorer` or any gate. Production ADR-0008 forbids confidence-as-trust at the framework level; this story enforces it at the validator level.
