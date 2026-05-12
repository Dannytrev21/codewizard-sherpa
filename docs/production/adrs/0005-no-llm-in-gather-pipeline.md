# ADR-0005: No LLM in the gather pipeline — determinism end-to-end

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** gather · determinism
**Related:** ADR-0006, ADR-0007, ADR-0008

## Context

The gather layer produces the `RepoContext` artifact that every downstream stage depends on. If gather is wrong, every plan is wrong; if gather is non-deterministic, every replay diverges; if gather varies in cost, portfolio-scale operations become unforecastable.

Many similar projects (LLM-powered code-understanding tools) invoke an LLM to summarize repos, classify files, or interpret config. This produces "richer" artifacts at the cost of reproducibility, audit, and cost predictability.

## Options considered

- **LLM-augmented gather.** Use an LLM at specific probe points (e.g., to summarize unstructured docs, classify ambiguous files, infer org conventions from prose). Produces a richer artifact.
- **Pure deterministic gather.** Every probe is `inputs → outputs` with no LLM in the path. Unstructured content (docs, notes) is indexed by structure (BM25, headings) and stored as opaque blobs; the *Planner* reads them at decision time, not the *gatherer*.

## Decision

**No LLM is invoked anywhere in the gather pipeline.** All probes are deterministic; same inputs always produce same outputs. Unstructured content is captured with deterministic indexing (BM25 over headings and metadata via Tantivy); the Planner reads originals at decision time using its own LLM, in the context of a specific question.

## Tradeoffs

| Gain | Cost |
|---|---|
| `RepoContext` is reproducible — replay a gather, get byte-identical output | The artifact contains structure and indexes, not pre-summarized prose |
| Content-addressed cache works (ADR-0006) — same inputs hit the same key | Probes cannot infer "intent" from free-form text; only structure |
| Auditable: if a plan was bad, replay the gather to byte-identical evidence | More work for the Planner at decision time (reads originals via MCP) |
| Cost predictable — gather has bounded compute cost, no per-token spend | Some "obvious" features (auto-summarized README, auto-tagged docs) are off the table |
| Continuous gather (ADR-0006) becomes tractable — cheap to run every hour | The architecture is opinionated against "AI-everywhere" trends |

## Consequences

- Unstructured-knowledge probes (`RepoNotesProbe`, `ExternalDocsProbe`, `ExternalDocsIndexProbe` per `../../localv2.md §5.4`) follow a strict pattern: capture as opaque blobs with provenance, index by headings/tags/URLs (BM25, not embeddings), surface manifests to the agent. The agent reads originals on demand.
- "Should we LLM-summarize this?" is a recurring temptation. The answer is always *no, surface the headings; the Planner reads what it needs.*
- Continuous gather is operationally cheap because no LLM API spend per run (ADR-0006).
- The Planning stage (ADR-0011) is where the LLM enters the system, not before.

## Reversibility

**High cost.** Adding an LLM call to a probe would break the cache contract (ADR-0006), the replay guarantee, the cost-prediction model, and the audit story. Every layer downstream of gather depends on the deterministic property. Reversing this decision is approximately a re-architecture.

## Evidence / sources

- `../design.md §2.1` (load-bearing commitment)
- `../design.md §3.2` ("Why this matters architecturally" — the determinism-enables-continuity argument)
- `../../localv2.md §"Design principles"` ("Deterministic over probabilistic")
- `../../context.md §"Why this shape"` — determinism, bounded probe scope, organizational uniqueness as data
