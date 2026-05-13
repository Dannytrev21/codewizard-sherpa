# ADR-0007: Checkpointer extends Phase 5's BLAKE3 audit chain — one chain across Phases 2–6

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** audit · tamper-evidence · cross-phase-contract
**Related:** [ADR-0006](0006-audited-sqlite-saver-per-workflow-fsync.md), [ADR-0008](0008-hitl-operator-auth-deferred-to-phase11.md)

## Context

Phases 2–5 already establish a BLAKE3-chained audit log at `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` (`final-design.md §Component 3` and Phase 5's `RetryLedger`). The chain is append-only, single-writer, and the head is the cryptographic linkage that proves no earlier event has been tampered with after the fact. Phase 6 introduces a new source of state — the checkpoint blob — and must decide what relationship that state has with the existing chain.

The three lenses gave conflicting answers (`critique.md §security-hidden-1`):

- **Performance** ignored the chain at the checkpointer entirely — `LoopAborted("checkpoint db corrupt")` detects *corruption* but not *forgery*. An attacker who edits the SQLite DB to flip `last_outcome.passed: False → True` is invisible.
- **Security** introduced its own `audit/<run-id>.jsonl` chain. Whether this is the same file as Phase 5's `attempts.jsonl` or a sibling file was *unspecified* — and if they're different, there are now two chains with no cross-link, which defeats the property they exist to provide.
- **Best-practices** had no concept of a chain at the checkpointer.

The synthesizer's commitment (`final-design.md §Goal 8 + §Component 3`): one chain across Phases 2–6, extended by both Phase 5's `RetryLedger.record` (for attempts) and Phase 6's `AuditedSqliteSaver.put` (for checkpoint frames). The same file. Under a shared single-process lock.

## Options considered

- **No chain extension at the checkpointer.** Detect SQLite-level corruption only. An offline DB edit flipping a verdict is undetectable. Rejected on threat-model grounds.
- **Phase 6 mints a second chain.** Sibling file (`checkpoint-chain.jsonl`). No cross-link with Phase 5's chain; two chains to verify; doubles the operator surface area; if either is dropped the property is broken.
- **Phase 6 extends Phase 5's chain in the same file.** One chain, two writers in the same process (Phase 5's `RetryLedger.record` + Phase 6's `AuditedSqliteSaver.put`), both holding the same `threading.Lock` before `O_APPEND`.

## Decision

`AuditedSqliteSaver.put` computes `digest = blake3(canonical_json(checkpoint) + prev_chain_head)` and, **inside a shared `threading.Lock` with Phase 5's `RetryLedger`**, appends a `checkpoint.write` event (with `thread_id`, `checkpoint_id`, `digest`) to `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`. On `aget_tuple`, the saver recomputes the digest from the persisted blob and matches it against the last `checkpoint.write` event for that `(thread_id, checkpoint_id)`; a mismatch raises `CheckpointTampered` and refuses to resume. The `interrupt.raised` and `resume.applied` events extend the same chain at HITL pause/resume boundaries.

## Tradeoffs

| Gain | Cost |
|---|---|
| One BLAKE3 chain across Phases 2–6 — operators verify with a single `codegenie audit verify` command and a single file | Phase 5 and Phase 6 share a writer for the chain file; the discipline that *both* writers acquire the same `threading.Lock` must be preserved (Open Q4, `test_chain_single_writer.py` is the canary) |
| Offline SQLite DB tampering is detected on resume — `CheckpointTampered` raises before any node runs | Online tampering during a paused workflow still requires the operator-auth layer that's deferred to Phase 11 (ADR-0008) |
| The `prev_chain_head` field carried in `VulnLedger` and persisted in every checkpoint blob means a corrupted DB cannot fake a fresh chain — the chain head is bound to the state | Adding chain extension to every checkpoint write costs ~one BLAKE3 hash per node boundary (~µs) plus one O_APPEND per node (negligible) |
| `checkpoint.tamper.detected`, `interrupt.raised`, `resume.applied` are first-class chain events — incident response has a clean timeline | The audit chain file is owned by Phase 5 but extended by Phase 6 — a contract that future phases must respect; if Phase 7 invents its own chain file the cross-phase property breaks |

## Consequences

- **`AuditChainCorrupted`** is raised on Phase 6 startup if the chain head Phase 6 reads from Phase 5 doesn't match the `prev` of the first `checkpoint.write` event for the workflow (closes `critique.md §security-hidden-1`). Recovery is operator triage; the workflow is refused.
- The chain file path is **`<run-id>`-keyed**, not `<workflow-id>`-keyed (Phase 6 design's Open Question #2). `RetryLedger.head_from_phase5(run_id)` is the helper Phase 6 calls at graph entry to seed `VulnLedger.chain_head`.
- `tests/adversarial/test_tampered_checkpoint.py` is the canary for the tamper detection.
- `cli/loop.py` exit code `13` covers `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted` — operator can disambiguate via the error message.
- Phase 7's `build_distroless_loop()` extends the same chain — its `task_type` discriminator differentiates the events.
- Phase 9's Postgres checkpointer (`AuditedPostgresSaver`) must preserve the chain-extension semantics — recorded in `phase-arch-design.md §Integration with Phases 8–9`.

## Reversibility

**Medium.** Removing the chain extension is one method-override; the `CheckpointTampered` test fails immediately, so reversion is detected. Splitting the chain into per-phase files would force every phase that consumes the chain to be re-audited and would defeat the cross-phase property — a multi-phase rollback. The single-shared-chain shape is the durable commitment; the implementation (BLAKE3 vs SHA256 vs Merkle tree) is reversible.

## Evidence / sources

- [`../final-design.md` §Component 3 — chain extension subsection](../final-design.md)
- [`../final-design.md` §Failure modes — "Phase 5 chain head mismatch on Phase 6 startup"](../final-design.md)
- [`../phase-arch-design.md` §Component 3 internal structure](../phase-arch-design.md)
- [`../critique.md` §security-hidden-1](../critique.md) — same-file-or-different-file ambiguity that this ADR closes
- Phase 5 `RetryLedger` design (Phase 5's `final-design.md`) — establishes the chain that Phase 6 extends
