# Phase 6 — Critique of the lens designs

## Performance design concerns

1. It risks treating checkpoint frequency as only a latency problem. Durability quality is part of the phase exit criteria; "fewer writes" is not automatically better.
2. It mentions a harness contract but does not specify what evidence must survive the abstraction boundary.
3. It assumes graph construction cost matters before measuring it.

## Security design concerns

1. It is strong on forbidden transitions but thin on operator ergonomics during legitimate HITL recovery.
2. "Replay verified" needs a concrete chain-head or checksum model; otherwise the phrase is decorative.
3. It treats raw graph internals as sensitive, correctly, but does not say how much sanitized evidence Phase 6.5 still needs.

## Best-practices design concerns

1. The proposed `VulnRemediationSut` is right in spirit but could become a second orchestration API if its semantics are not pinned tightly.
2. "Plugin-local behavior, shared ports" needs a hard file-placement rule or contributors will drift.
3. The testing advice is good but underspecified on exact replay and resume edge cases.

## Synthesis pressure

The final design must keep the graph plugin-local, name a stable SUT contract with precise inputs and outputs, state the replay boundary concretely, and make clear that Phase 6 adds orchestration without reopening the trust decisions from Phases 3–5.
