# Story S1-01 — Errors + structlog event constants for Phase 4

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P4-004, ADR-P4-008, ADR-P4-010, ADR-P4-013

## Context

Foundational. Every other Step 1 story imports the exception types and structlog event-name constants registered here; without them every subsequent module would invent its own ad-hoc string labels and the BLAKE3 audit chain Phase 2 ships would lose schema consistency across Phase-4 event types. This story plants the typed error surface and the structured-fields vocabulary the rest of the phase relies on (`tier`, `prompt_template_id`, `canary_fingerprint`, `cve_id`, `example_id`, `qk`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Harness engineering"` — structlog format, required fields per Phase-4 log line, exit codes 9/10/11.
  - `../phase-arch-design.md §"Edge cases"` — every edge case names the audit event it emits (rows #1–#24).
  - `../phase-arch-design.md §"Component design"` — each component's "Failure behavior" subsection names the exceptions Phase 4 raises.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004; names `LlmOutputRejected`, `LlmTransportError`, `LlmTimeout`, `CostCeilingBreached` as the four `LeafLlmAgent.invoke` exceptions.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008; names `canary.echo_failed` and `fence.residual_detected` audit events.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010; defines `CostCeilingBreached`.
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013; defines `api_key.env_present` audit event.
- **Existing code:**
  - `src/codegenie/errors.py` — current exception hierarchy (Phase 0–3); extend, do not rewrite.
  - `src/codegenie/logging.py` — current structlog configuration and constant registry (Phase 0).

## Goal

Extend `errors.py` with the nine Phase-4 exception types and `logging.py` with the structured-field constants every Phase-4 component will tag its log lines with.

## Acceptance criteria

- [ ] `src/codegenie/errors.py` exports `LlmOutputRejected`, `LlmTransportError`, `LlmTimeout`, `CostCeilingBreached`, `PromptTemplateInvalid`, `PromptVariableMissing`, `EmbeddingDigestMismatch`, `StoreCorrupt`, `StaleLockBroken` — each subclass of the existing Phase-0–3 base exception class.
- [ ] Each new exception has `__str__` / `__repr__` that includes the structured-context kwargs (no naked strings in audit chain).
- [ ] `src/codegenie/logging.py` registers the structured-field name constants: `TIER`, `PROMPT_TEMPLATE_ID`, `PROMPT_TEMPLATE_VERSION`, `MODEL`, `CANARY_FINGERPRINT`, `CVE_ID`, `EXAMPLE_ID`, `QK` (as module-level `Final[str]`).
- [ ] `src/codegenie/logging.py` registers the Phase-4 event-name constants enumerated in `../phase-arch-design.md §"Audit chain extension"` cross-cutting note (e.g. `EVENT_LLM_INVOKED`, `EVENT_LLM_OUTPUT_REJECTED`, `EVENT_CANARY_ECHO_FAILED`, `EVENT_FENCE_RESIDUAL_DETECTED`, `EVENT_COST_LLM_INVOKED`, `EVENT_API_KEY_ENV_PRESENT`, `EVENT_SOLVED_EXAMPLE_WRITTEN`, `EVENT_SOLVED_EXAMPLE_WRITEBACK_REFUSED`, `EVENT_SOLVED_EXAMPLE_RACE_OBSERVED`, `EVENT_EMBEDDING_MODEL_HASH_MISMATCH`, `EVENT_LOCK_BROKEN_STALE`, `EVENT_WRITEBACK_PARTIAL_FAILURE`, `EVENT_LEAF_IN_PROCESS_ON_LINUX`, `EVENT_EGRESS_REQUEST_DENY`, `EVENT_SOLVED_EXAMPLE_MISLEADING_MATCH_RECORDED`).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/errors.py` + `src/codegenie/logging.py` clean.
- [ ] `pytest tests/unit/test_errors_phase4.py tests/unit/test_logging_phase4_constants.py` green.

## Implementation outline

1. Open `src/codegenie/errors.py`; append nine exception classes following the existing hierarchy convention. Each carries kwargs in `__init__` matching the audit-event payload shape (e.g. `LlmOutputRejected(reason: str, errors: list[str], canary_fingerprint: str)`).
2. Open `src/codegenie/logging.py`; declare structured-field constants and event-name constants as `Final[str]` module-level values. Group them under a header comment `# === Phase 4 — vuln LLM fallback + RAG ===`.
3. Wire any registry/enum the Phase-0 logging module uses so the new event names are discoverable for the BLAKE3 chain validator that Phase 2 ships.
4. Confirm no existing constant is renamed (Rule 3 — surgical changes).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_errors_phase4.py`

```python
def test_phase4_exceptions_subclass_base_and_carry_context():
    from codegenie.errors import (
        BaseCodegenieError,
        CostCeilingBreached,
        EmbeddingDigestMismatch,
        LlmOutputRejected,
        LlmTimeout,
        LlmTransportError,
        PromptTemplateInvalid,
        PromptVariableMissing,
        StaleLockBroken,
        StoreCorrupt,
    )

    # arrange / act
    exc = LlmOutputRejected(
        reason="canary_echo_failed",
        errors=["canary mismatch"],
        canary_fingerprint="deadbeef",
    )

    # assert — subclass of base + structured context preserved in repr
    assert issubclass(LlmOutputRejected, BaseCodegenieError)
    assert "canary_echo_failed" in repr(exc)
    assert "deadbeef" in repr(exc)
    # every Phase-4 type is a BaseCodegenieError
    for t in (
        LlmTransportError, LlmTimeout, CostCeilingBreached,
        PromptTemplateInvalid, PromptVariableMissing,
        EmbeddingDigestMismatch, StoreCorrupt, StaleLockBroken,
    ):
        assert issubclass(t, BaseCodegenieError)
```

Test file path: `tests/unit/test_logging_phase4_constants.py`

```python
def test_phase4_event_constants_registered_and_unique():
    from codegenie import logging as cg_logging

    required = {
        "EVENT_LLM_INVOKED", "EVENT_LLM_OUTPUT_REJECTED",
        "EVENT_CANARY_ECHO_FAILED", "EVENT_FENCE_RESIDUAL_DETECTED",
        "EVENT_COST_LLM_INVOKED", "EVENT_API_KEY_ENV_PRESENT",
        "EVENT_SOLVED_EXAMPLE_WRITTEN",
        "EVENT_SOLVED_EXAMPLE_WRITEBACK_REFUSED",
        "EVENT_SOLVED_EXAMPLE_RACE_OBSERVED",
        "EVENT_EMBEDDING_MODEL_HASH_MISMATCH",
        "EVENT_LOCK_BROKEN_STALE", "EVENT_WRITEBACK_PARTIAL_FAILURE",
        "EVENT_LEAF_IN_PROCESS_ON_LINUX", "EVENT_EGRESS_REQUEST_DENY",
        "EVENT_SOLVED_EXAMPLE_MISLEADING_MATCH_RECORDED",
        "TIER", "PROMPT_TEMPLATE_ID", "PROMPT_TEMPLATE_VERSION",
        "MODEL", "CANARY_FINGERPRINT", "CVE_ID", "EXAMPLE_ID", "QK",
    }
    for name in required:
        assert hasattr(cg_logging, name), name
    values = [getattr(cg_logging, n) for n in required]
    assert len(set(values)) == len(values), "constants collide"
```

### Green — make it pass

Append the nine exception classes to `errors.py` with `__init__` kwargs and a `__repr__` that includes them. Append the constants block to `logging.py`.

### Refactor — clean up

- Type-annotate every `__init__` parameter.
- Add one-line docstrings keyed to the audit event payload (so future readers can follow the trail from event → exception → ADR row).
- Confirm no f-string mints the audit message body (constants only — Rule 11 — match conventions; the Phase-0 logging module is the conventions source).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | Add nine Phase-4 exception classes. |
| `src/codegenie/logging.py` | Add structured-field and event-name constants. |
| `tests/unit/test_errors_phase4.py` | Red test — exception hierarchy + context preservation. |
| `tests/unit/test_logging_phase4_constants.py` | Red test — required constants registered + unique values. |

## Out of scope

- **Actual emission** of any event from any component — handled in each downstream story (S2-04 emits `api_key.env_present`, S6-01 emits `solved_example.written`, etc.).
- **Audit-chain BLAKE3 integration** — Phase 2 already ships the chain writer; this story only names the events.
- **Central `audit-events.yaml` registry** — deferred per manifest Open Question #7.

## Notes for the implementer

- Rule 3 (surgical changes): do not refactor `errors.py` or `logging.py`. Append only.
- Rule 11 (match conventions): mimic existing Phase-0 exception classes for `__init__` shape. If Phase 0 uses dataclass-style errors, follow that.
- The `api_key.env_present` event is **warn-only on macOS, hard-refuse on Linux** (ADR-P4-013). The constant name is the same; the policy split lives in S2-04.
- The `canary_fingerprint` field is **always** `blake3(canary_token)[:8]`, never the canary itself (the canary is the secret that proves prompt-injection didn't smuggle it).
- Event names use dot-namespaced strings (`"solved_example.written"`); Python constants UPPER_SNAKE (`EVENT_SOLVED_EXAMPLE_WRITTEN`). Keep both stable.
- The `confidence=low` discipline (ADR-P4-008 / production ADR-0008) means LLM self-reported `confidence` fields are stripped before they reach the audit chain; the validator does the stripping in S2-01. Nothing to do here, but do *not* register an `EVENT_LLM_CONFIDENCE_SELF_REPORTED` event — that would normalize the smuggle.
