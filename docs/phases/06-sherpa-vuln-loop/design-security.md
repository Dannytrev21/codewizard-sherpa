# Phase 6 — Security-first design

**Question:** how do we add orchestration without creating a privileged escape hatch around the trust gates that Phase 5 just made explicit?

## Design

- Nodes never call nodes. All transitions flow through conditional edges governed by explicit gate outcomes.
- The graph may request patch application or sandbox validation only through the Phase 3/5 ports that already enforce subprocess and sandbox policy.
- The ledger is typed, append-aware, and replay-verified before resume. Resume from an unverified checkpoint is forbidden.
- HITL interrupts are explicit variants, not boolean flags; resumed input is validated before it can re-enter the graph.
- The harness-facing `VulnRemediationSut` contract returns sanitized evidence, never raw prompts, secrets, or unchecked filesystem paths.

## Security controls

| Control | Purpose |
|---|---|
| Transition whitelist | Prevent unreviewed graph edges from bypassing trust gates |
| Replay verification | Reject tampered or partial checkpoint state |
| Sum-type outcomes | Make escalation and unrecoverable failure distinct from success |
| Existing sandbox ports only | Prevent orchestration code from introducing a second execution path |
| Sanitized SUT result | Keep bench artifacts free of secrets and unstable internals |

## Risks

- Resume logic is a new attack surface: stale human approvals or replayed approvals need explicit expiry semantics.
- A graph-level convenience helper could accidentally smuggle unchecked data across node boundaries; static tests should pin imports and direct calls.
- SQLite is not a security boundary; the phase relies on tamper detection, not secrecy.
