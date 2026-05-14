# ADR-0008: No event stream in Phase 2 — Phase 0 audit anchor unchanged; ADR-0034 defers canonical event log to Phase 9

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** observability · audit · scope · phase-boundary · defer · event-sourcing
**Related:** [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md), [Phase 0 ADR — audit anchor](../../00-bullet-tracer-foundations/ADRs/), 02-ADR-0007

## Context

[Production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) declares event sourcing the canonical primitive for agent runs and explicitly anchors the canonical event log delivery in **Phase 9 (or 13)** — §Consequences §1: "Phase 9 (Temporal) formalizes the canonical event log." Phase 0 already ships an audit anchor — `runs/<utc-iso>-<short>.json` — recording per-probe `Ran/CacheHit/Skipped` outcomes. That anchor is Phase 2's full observability surface for gather invocations.

Two of Phase 2's three input lenses proposed shipping a partial event stream now:
- **Performance lens** proposed 3 event variants (`IndexHealthDegraded`, `ProbeCacheInvalidated`, `ExternalToolMissing`) written to `.codegenie/events/` JSONL.
- **Security lens** proposed 10+ variants with a BLAKE3 hash chain — `ProbeStarted`, `ProbeFinishedOk`, `ProbeFailed`, `SkillRefused`, `GrammarLoadRefused`, `EgressBlocked`, `SecretRedacted`, and so on — with `IndexHealthProbe` reading the chain to detect tampering.

The critic ([critique.md §"Attacks on the security-first design" §"Things this design missed"](../critique.md)) framed this directly: ADR-0034 §"Event types" never described the Phase 2 use case; pre-shaping events in Phase 2 risks schema drift; treating a partial event stream as load-bearing now (e.g., "B2 reads the audit log's `FinishedOk` events") inverts the dependency direction — a probe becomes a consumer of the event stream it emits to, which is event sourcing as a runtime data plane, not as an audit primitive. The cryptographic-anchor variant ([S]'s hash-chain) defends against an attacker who can write to `.codegenie/audit/` — which per Phase 0 ADR-0011 requires having already compromised the host (the chain protects against bit-rot, not adversaries; critic-acknowledged blind spot in [S]).

The synthesis (`final-design.md §"Conflict-resolution table" row 10`, §"Departures from all three inputs" §"No event stream in Phase 2"`) refused both: ship zero events in Phase 2; the Phase 0 audit anchor is unchanged. **What Phase 2 does ship is structured slice metadata**: each probe writes its own `gathered_at`, `last_indexed_commit`, `built_image_digest`, `rule_pack_version`, etc. into its `ProbeOutput.schema_slice`. Phase 9 will project that slice metadata into the typed Postgres event log via the same `Ran/CacheHit/Skipped` outcomes Phase 0 already records — without schema drift, because Phase 9 owns the schema.

## Options considered

- **Option A — Ship 3 event variants (`IndexHealthDegraded`, `ProbeCacheInvalidated`, `ExternalToolMissing`) to `.codegenie/events/`.** Performance lens's pick. Pre-shapes Phase 9's schema; an in-Phase 9 schema choice that conflicts with these variants is now a migration. Critic finding [P] §8.
- **Option B — Ship 10+ hash-chained event variants with `IndexHealthProbe` reading the chain.** **Pattern:** Event sourcing prematurely + Capability/integrity-anchor for a non-threat. Security lens's pick. Multiple problems: schema lock-in before Phase 9 design; B2-as-consumer-of-its-own-emit; hash chain protects against bit-rot only (critic [S] §"hidden assumption" #3).
- **Option C — Ship zero events; preserve Phase 0 audit anchor; emit structured slice metadata in each probe so Phase 9 can project later.** **Pattern:** Defer until Phase 9 owns the schema. Synthesis pick. Honors ADR-0034 §Consequences §1; no pre-shape; the Phase 0 audit anchor records exactly what Phase 2 needs (per-probe outcome).

## Decision

Adopt **Option C — no event stream in Phase 2.** The Phase 0 audit anchor `runs/<utc-iso>-<short>.json` is **unchanged** and is the full observability surface for Phase 2 gather invocations. No `.codegenie/events/`. No JSONL event log. No hash chain. No event-variant Pydantic union. `IndexHealthProbe` (B2) reads sibling probes' **slice outputs** (via the coordinator-provided slice map), not an event stream. Each probe writes its own slice metadata (`gathered_at`, `last_indexed_commit`, `built_image_digest`, `rule_pack_version`) so Phase 9 can project later. **Pattern: Schema before consumer is an anti-pattern; Phase 9 owns the schema.**

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0034 §Consequences §1 honored verbatim — "Phase 9 (Temporal) formalizes the canonical event log" stays an unbroken commitment | No event-stream observability in Phase 2 — operators get the Phase 0 audit anchor (per-probe Ran/CacheHit/Skipped) and the CLI summary line, nothing finer-grained until Phase 9 |
| No schema drift risk — the Phase 9 event schema lands without "but Phase 2 already named events `ProbeFinishedOk`; we have to compat them" pre-shape | A future tooling story that wants finer-grained observability (per-probe wall-clock, cache-miss reasons) must wait for Phase 9 — Phase 2 doesn't pre-serve that need |
| Audit-log "hash chain" theatre refused — the chain protects against bit-rot only, not adversaries (critic [S] §"hidden assumption" #3); cryptographic ceremony spend on a non-threat is avoided | Some forms of accidental corruption (a `.codegenie/audit/*.json` file truncated by `kill -9` mid-write) are not auto-detected; the Phase 0 audit anchor's atomic write (`.tmp` → `os.replace`) provides the integrity guarantee Phase 2 ships with |
| B2 reads **sibling slice outputs**, not event streams — the data-flow direction matches the conceptual model (B2 inspects what other probes wrote, not what they emitted) | B2 has a structural coupling to every sibling probe's slice shape; Gap 3 improvement (`@register_index_freshness_check`) closes the Open/Closed gap before it widens |
| Phase 2 emits **slice metadata** (`gathered_at`, `last_indexed_commit`, etc.) that Phase 9 will project into the canonical event log via `Ran/CacheHit/Skipped` outcomes — the Phase 9 schema gets typed input without Phase 2 pre-shaping it | The slice-metadata convention (every probe writes `gathered_at` and friends into its slice) is honored by convention, not enforced by ABC. Mitigation: per-probe golden tests assert the metadata fields exist; the convention is grep-able |
| Cost-attribution (Phase 13 ROI dashboard) reads the same Phase 0 audit anchor — the per-probe `Ran/CacheHit/Skipped` outcomes are sufficient to bucket cost by probe family without Phase 2 inventing a separate cost-event variant | Phase 13 may need finer-grained data (e.g., per-external-CLI wall-clock); that lands in Phase 9 alongside the event log, not in Phase 2 |
| Phase 2 build is smaller — no `EventStreamEmitter` module, no event-variant Pydantic union (10+ types), no chain-walker — fewer surfaces for the critic to attack | A future contributor may be tempted to "just add one event for X"; the discipline is "no Phase-2 events"; the test enforcing this is `tests/unit/test_no_event_stream_in_phase_2.py` (textual / structural — fence-style assertion that no `.codegenie/events/` write paths exist under `src/codegenie/`) |

## Pattern fit

Pattern: **Defer until consumer is real** (`design-patterns-toolkit.md §"Event sourcing for agent runs" failure mode`: "event sourcing for state that doesn't need replayability. CRUD is fine if CRUD is what you need"). The toolkit's framing applies: Phase 2 doesn't need event-stream replayability — it needs an audit anchor that records what ran (Phase 0 already provides this), and slice metadata that Phase 9 can project into a typed event log later. The pattern's failure mode the toolkit warns against ("event sourcing for state that doesn't need replayability") is exactly the trap two lenses fell into. Composes with **Schema before consumer is an anti-pattern** (`design-patterns-toolkit.md`'s anti-pattern list, generalized) — ADR-0034 owns the event schema; pre-shaping in Phase 2 risks a Phase-9 migration. The synthesis is "ship the simplest thing that works (Phase 0 anchor + slice metadata); the canonical event log gets designed once, in Phase 9, by the team that owns the schema."

## Consequences

- `src/codegenie/` contains **no** `events/` or `event_log/` modules; **no** `EventStream` class; **no** `ProbeStarted`/`ProbeFinishedOk`/`FinishedFailed`/`CacheInvalidated`/`EgressBlocked`/`SecretRedacted` Pydantic variants.
- `tests/unit/test_no_event_stream_in_phase_2.py` is a structural assertion (textual `grep`-style over `src/codegenie/`) that no event-emission code paths exist. A future contributor adding one fails the build with a loud message naming this ADR.
- The Phase 0 audit anchor (`runs/<utc-iso>-<short>.json`) is unchanged. Per-probe outcome (`Ran` / `CacheHit` / `Skipped`) is recorded; no plaintext secrets reach the anchor (02-ADR-0005); secret-redaction count is the one new field 02-ADR-0005 lists.
- Each Phase 2 probe writes its own slice metadata into its `ProbeOutput.schema_slice`. Conventional fields: `gathered_at: datetime`, `last_indexed_commit: str | None`, `built_image_digest: str | None`, `rule_pack_version: str | None`. Per-probe golden tests assert the convention.
- `IndexHealthProbe` (B2) reads sibling slices via the coordinator-provided slice map (the `runs_last=True` annotation per 02-ADR-0003 reserves B2 for last). It does NOT read an event log; the data-flow direction is "probe inspects sibling outputs," not "probe consumes event stream."
- Phase 9 will design the canonical event log with the Phase 2 slice-metadata convention as typed input. Phase 13 cost-attribution similarly reads from Phase 0's audit anchor + Phase 2's slice metadata; no Phase 2 cost-event variant exists.
- The performance-lens-proposed 3-variant event stream stays rejected. The security-lens-proposed 10+-variant hash-chained stream stays rejected. The structural-defense for plaintext-in-audit-anchor is the SecretRedactor chokepoint (02-ADR-0005), not an event-log integrity story.

## Reversibility

**High.** Adding an event stream later (Phase 9, as ADR-0034 prescribes) is greenfield: design the schema, ship the emitter, project Phase 0's audit anchor + Phase 2's slice metadata into the typed event log via a migration script. No Phase 2 code needs to change; the audit anchor and slice metadata are forward-compatible inputs to whatever Phase 9 decides. The reverse direction (un-doing an event stream after it's shipped) is the harder path; Phase 2's "no events" position keeps that door open without commitment.

## Evidence / sources

- `../final-design.md §"Conflict-resolution table" row 10` — audit-log event stream resolution
- `../final-design.md §"Departures from all three inputs" §"No event stream in Phase 2"` — explicit refusal of both lenses
- `../final-design.md §"Patterns considered and deliberately rejected" #8` — event stream + hash-chained JSONL refused
- `../phase-arch-design.md §"Non-goals"` (Canonical event log, `.codegenie/events/` JSONL, hash-chained audit)
- `../phase-arch-design.md §"Harness engineering" §"Tracing"` — slice-metadata emission for Phase 9 projection
- `../critique.md §"Attacks on the security-first design" §"Hidden assumptions" #3` — hash-chain bit-rot framing
- `../critique.md §"Attacks on the security-first design" §"Things this design missed"` — B2-as-consumer-of-its-own-emit
- `../critique.md §"Cross-design observations" §"Where do all three quietly agree on something questionable" #1` — schema before consumer
- [Production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) §Consequences §1 — "Phase 9 (Temporal) formalizes the canonical event log"
- [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) — audit anchor `runs/<utc-iso>-<short>.json` definition
