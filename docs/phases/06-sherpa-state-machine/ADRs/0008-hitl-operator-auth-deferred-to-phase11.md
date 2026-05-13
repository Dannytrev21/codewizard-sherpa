# ADR-0008: HITL operator authentication is deferred to Phase 11 — Phase 6 ships typed `HumanDecision` only

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** hitl · scope · deferred-security · cross-phase-contract
**Related:** [ADR-0007](0007-blake3-chain-extension-and-tamper-evidence.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

The roadmap exit criterion for Phase 6 is *"HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run."* (`roadmap.md §Phase 6 Exit criteria`). The three lens designs took wildly different views of what "human approval" means:

- **Security** shipped ~600 LOC of operator-authentication machinery: `~/.config/codegenie/operator.key` (Ed25519 keypair), `codegenie operator init` CLI, `expected_approvers.json`, two-step CLI signing, gate-control HMAC envelope signing continued from Phase 5. `critique.md security.1` landed: this is *massively out of scope* for Phase 6 as the roadmap defines it. Roadmap Phase 6 tooling list is `langgraph`, `pydantic`, `aiosqlite`, `langgraph-cli`. Roadmap Phase 11 (not Phase 6) owns PR-comment dispatch and approval ingestion. Roadmap Phase 16 owns SSO/RBAC. Security imported four phases of the roadmap into Phase 6 and called it "minimum security posture."
- **Performance** shipped an *untyped* `Command(resume=ApprovalDecision(...))` payload with no signature on the `ApprovalDecision`. Critic: a `codegenie loop resume <thread_id> --decision approve_and_retry` from any local user advances any paused workflow. No authentication at all.
- **Best-practices** shipped an untyped `aupdate_state(..., {"human_decision": dict})` — same problem.

The Phase 6 commitment from CLAUDE.md Rule 3 (Surgical Changes) and load-bearing commitment §2.5 (Extension by addition) is that Phase 6 ships the *contract* HITL needs, not the *signal source* or the *authentication layer.* Phase 11 owns real PR comments tied to real GitHub identities; Phase 16 owns multi-tenant key isolation. The single-host trust posture in Phase 6 is appropriate for a local POC where the operator is the developer.

## Options considered

- **Full operator-key stack now (security's pick).** Ed25519, HMAC, key rotation, `expected_approvers.json`, multi-step CLI. ~600 LOC; trains operators on a workflow that Phase 11 will replace with real GitHub identity; blows the Phase 6 LOC budget (1200 target per best-practices) three times over.
- **No HITL typing (performance's and best-practices' picks).** `dict` blob in, `dict` blob out. Malformed payloads fail at the first node that reads them, not at the resume boundary — debugging is opaque.
- **Typed `HumanDecision` only, no auth.** Pydantic validates the shape at the resume boundary; the single-host trust posture is recorded explicitly; the operator-auth layer is deferred to Phase 11 with the contract already on disk for Phase 11 to consume.

## Decision

Phase 6 ships `HumanRequest` and `HumanDecision` as `frozen=True, extra="forbid"` Pydantic models in `src/codegenie/graph/hitl.py`. On `codegenie loop resume`, the CLI constructs a `HumanDecision`, calls `graph.aupdate_state(config, {"human_decision": decision.model_dump(mode="json")}, as_node="await_human")`, and then `graph.ainvoke(None, config)`. **No Ed25519, no HMAC, no operator-key file, no two-step CLI signing.** The `0600` checkpoint file mode plus the BLAKE3 chain integrity check (ADR-0007) constitute the single-host trust posture. The HITL contract is exported to `docs/contracts/hitl-v0.6.0.json` and Phase 11's design review is **required** to either consume this shape or amend it via a new ADR.

## Tradeoffs

| Gain | Cost |
|---|---|
| ~600 LOC of crypto plumbing saved — Phase 6's complexity budget stays inside the roadmap's stated tooling | A local user with shell access to the home directory can resume any paused workflow with any `HumanDecision` — **explicitly accepted single-host trust posture** |
| The HITL contract shape is committed to disk now — Phase 11's signal source (GitHub webhook? Slack? MCP?) gates on consumption-or-amendment | The contract may be wrong for Phase 11's actual signal source — Risk #2 records this; the minimal three-Literal-action shape is intentional to maximize the chance Phase 11 can consume it |
| `HumanDecision.model_validate` rejects malformed payloads loudly at the resume boundary, not deep inside `await_human` | The contract evolution path is "Phase 11 ADR amends `HumanDecision`" — a coordinated cross-phase change, not a unilateral Phase 11 invention |
| `HumanDecision.note` is plain text, never flowed into any LLM prompt — closes the "fence-wrapped notes" creep that critic flagged (`final-design.md §Component 7`) | A future feature that wants the operator's reasoning to inform Phase 4's next attempt cannot do so without amending the rule; the test `test_hitl_note_not_in_prompt.py` enforces |

## Consequences

- **`tests/integration/test_hitl_malformed_decision_raises.py`** is the canary — `aupdate_state` with a malformed dict raises `ValidationError` at `HumanDecision.model_validate` and the workflow halts with state preserved.
- The `cli/loop.py resume` command is the **only** HITL signal source Phase 6 ships. Phase 11 is free to add additional surfaces (a webhook listener, a Slack handler) that produce the same `HumanDecision.model_dump(mode="json")` payload and call `aupdate_state` — the Phase 6 shape is the integration seam.
- `await_human` is the **only** file that imports `langgraph.types.interrupt`. The `test_only_await_human_imports_interrupt.py` static check is the canary.
- `HumanDecision.action="continue"` resets `retry_count=0` and routes to `replan_with_phase4`; `action="override"` jumps to `emit_artifact`; `action="abort"` routes to `escalate` (`final-design.md §Component 7`).
- Phase 11's operator-key story, when it lands, will likely add a `signature: bytes` field to `HumanDecision` and a verification step in `await_human` — a strict extension of the v0.6.0 shape, not a contract break.
- Risk #4 records the explicit scope cut; it is *not* a "we'll get to it later" hand-wave but a deliberate "Phase 11/16 owns it."

## Reversibility

**High.** Adding operator authentication later is mechanical — `HumanDecision` gains a `signature` field (additive), `await_human` gains a verification step, and the CLI grows a `--key` flag. Phase 6's contract shape is the minimum stable surface; extending it is exactly what the deferral assumes. *Removing* the typed contract (going back to untyped `dict`) is reversible but unsafe and is the explicit rejection.

## Evidence / sources

- [`../final-design.md` §Component 7 "HITL contract"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 6 "HITL resume authentication"](../final-design.md)
- [`../final-design.md` §Risk 2](../final-design.md)
- [`../phase-arch-design.md` §Component 6 "HumanRequest / HumanDecision / await_human"](../phase-arch-design.md)
- [`../critique.md` §security.1](../critique.md) — the scope-creep argument
- [Production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) — establishes the "humans always merge" commitment that this contract serves
- Roadmap `Phase 11` (real PR + HITL signal source) and `Phase 16` (SSO/RBAC) — where the deferred work lands
