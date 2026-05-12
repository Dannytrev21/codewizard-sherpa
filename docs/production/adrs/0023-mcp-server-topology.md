# ADR-0023: MCP server topology — single global vs per-stage

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** platform · authorization
**Related:** ADR-0007, ADR-0013

## Context

Structured data (RepoContext, Skills, Knowledge Graph, Policies) is served to the orchestrator and to leaf LLM nodes via MCP servers. Two operational topologies:

- **One global MCP** serving every data domain (Context + Skills + KG + Policy under one server).
- **Per-stage MCP servers** — separate servers for Context, Skills, Knowledge Graph, and Policy. Each is scoped, addressable, and independently scaled.

The difference shows up in deployment complexity, authorization model, scaling characteristics, and blast radius of a single MCP failure.

## Options considered

- **Single global MCP.** Simpler to deploy and discover. One auth boundary covers all data. Failure mode: any MCP outage takes down all data access.
- **Per-stage MCP servers.** Authorization scopes cleanly per data domain (the Planning leaf only needs Context + Skills + KG; the Trust gate only needs Policy). Each scales independently. Failure of one MCP doesn't take down the others.
- **Hybrid — by access pattern.** Read-heavy serving (Context, Skills, KG) on one MCP; write-heavy serving (Policy evaluations, Audit log) on another. Less clean than per-stage.

## Default until decided

**Per-stage MCP servers** is the recommended direction based on authorization clarity.

Reasoning:
- The Planning agent should not have access to internal-only Policy details; the Trust gate should not have access to RAG retrieval. Per-stage authorization is the natural enforcement.
- Failure isolation is cleaner: a Knowledge-Graph outage doesn't block Stage 2 reads from the Context MCP.
- Per-MCP scaling: Context MCP is read-heavy (every agent call), Policy MCP is hit only at gate evaluations, KG MCP is hit at planning. Mismatched throughput patterns deserve independent autoscaling.

But this is **not yet committed** because the operational complexity (4 MCPs to deploy, monitor, version) is real.

## Evidence needed to resolve

- **Authorization model maturity.** Are we adopting a per-agent identity model (ADR-0009 implies yes)? If so, per-stage authorization is much easier to express with per-stage MCPs.
- **Operational complexity tolerance.** How many MCP servers can the team reasonably operate? If the answer is 1, that forces single global.
- **Failure-isolation requirements.** Does an outage in one data domain need to leave the others available? If yes, per-stage wins.
- **Discovery/routing complexity.** With multiple MCPs, leaf nodes need a discovery mechanism (config or service mesh). Adds complexity.

## Reversibility (of the eventual choice)

**Medium.** Splitting a single global MCP into per-stage is a refactor of server code plus client config. Merging per-stage back to a single MCP is similar effort.

## Evidence / sources

- `../design.md §5` (Identity and tool governance subsection)
- `../design.md §7` (Open questions — MCP server topology)
- `../design.md §8.1` (logical view shows separate MCP servers per data domain — the current draft assumes per-stage but this is the deferred decision)
- `../../context.md §"Exposure to the agent"` — MCP query operations (the function set could be served by one server or many)
