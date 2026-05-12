# ADR-0007: Probe contract preserved unchanged from POC to service

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** contract · stability
**Related:** ADR-0004, ADR-0005, ADR-0006

## Context

The local POC ([`../../localv2.md`](../../localv2.md)) defines a `Probe` ABC contract in §4 and a `RepoContext` schema in §7. These are the gather layer's public surface — the contract every probe implementation satisfies and every consumer reads against.

The question is whether to treat the POC contract as throwaway (rewrite at service-lift time) or as the same contract the service will use.

If the contract changes at service-lift, every existing probe must be rewritten — and the POC contributors' work is wasted. If the contract is preserved, the lift is structural (swap the coordinator backend, swap the cache backend) without touching probe code.

## Options considered

- **POC contract is provisional.** Treat the POC as exploration; redesign the contract for the service based on lessons learned.
- **POC contract is the service contract.** Design the POC contract carefully enough that it lifts unchanged. POC bugs become service bugs; POC reviews carry production weight.

## Decision

**The probe contract in `../../localv2.md §4` is the same contract the service uses.** The `Probe` ABC, the `declared_inputs` mechanism, the `applies_to_tasks` / `applies_to_languages` filters, the cache-key derivation, and the `RepoContext` schema all lift unchanged. Only the coordinator's dispatch backend (asyncio → Temporal Activities) and the cache backend (filesystem → object store + Postgres index) change.

## Tradeoffs

| Gain | Cost |
|---|---|
| Every probe written in the POC is service-ready | Bugs in the POC contract are production bugs once the service ships |
| Service lift is structural, not a rewrite | POC contract review at v0.1.0 is the most consequential review in the project |
| Contributors' work is preserved across phases | Cannot iterate on the contract once the service is live — additions only |
| Same engineers can land probes in either environment without context switching | "Move fast" temptation during POC must be resisted at the contract boundary |

## Consequences

- The `Probe` ABC is treated as a versioned interface. Breaking changes require a version bump and migration plan; additive changes (new fields with defaults) are safe.
- The `RepoContext` schema is JSON-Schema-validated at every gather; downstream consumers refuse malformed inputs.
- `declared_inputs` is load-bearing for cache correctness (ADR-0006). Probes that under-declare inputs cause silent staleness; probes that over-declare reduce cache hit rate.
- POC v0.1.0's exit criteria explicitly include a probe-contract review with the production lens applied.
- The `RepoContext` artifact format is also the over-the-wire format for MCP servers (ADR-0023). Schema breaks affect both gather and orchestrator.

## Reversibility

**High cost.** Changing the probe contract retroactively requires rewriting every probe (~25 probes in POC v0.1.0, growing as languages are added) and every consumer (Planning Activities, MCP servers). Plan to live with the v1 contract for the lifetime of the project; reserve breaking changes for major version bumps.

## Evidence / sources

- `../design.md §6` (POC-to-service mapping table — every row, this is the load-bearing one)
- `../../localv2.md §4` (the Probe ABC)
- `../../localv2.md §7` (the `RepoContext` schema)
- `../../localv2.md §11` (extension model — "Probe contract is identical to what the eventual service would use")
- `../../context.md §"Extensibility"` (the probe interface as stable minimum surface)
