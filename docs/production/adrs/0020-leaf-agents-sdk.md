# ADR-0020: Leaf Agents SDK choice (Anthropic / OpenAI / both)

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** llm · vendor
**Related:** ADR-0002

## Context

Leaf LLM nodes inside SHERPA-disciplined subgraphs call an Agents SDK to do the actual reasoning. The choice is which vendor SDK to use. The SHERPA discipline (ADR-0002) isolates this choice to leaf nodes only — the orchestration logic, state model, gates, and tool use are vendor-agnostic. The vendor concern surfaces only at the LLM API boundary.

Three positions:

- **Anthropic only.** Claude Sonnet / Opus / Haiku. Prompt caching, citations, extended thinking, computer use, code execution all production-grade in 2026.
- **OpenAI only.** GPT-4.x / Codex / O-series. Tool use, structured output, Assistants API.
- **Both, behind a thin shim.** Implement a vendor-agnostic interface; route per task or per env config.

## Options considered

- **Anthropic only.** Reduces vendor surface area; Claude's prompt caching is well-suited to the few-shot RAG pattern in ADR-0011.
- **OpenAI only.** OpenAI Codex's Temporal precedent (ADR-0003) suggests OpenAI tooling is production-ready for agentic workloads. Larger ecosystem of tutorials and integrations.
- **Vendor-agnostic shim.** Lets us A/B test per task class without code changes; protects against vendor outages. Adds an internal interface to maintain.

## Default until decided

**Anthropic SDK for the initial leaf implementations.** Reasoning:

- Prompt caching directly benefits the RAG few-shot pattern (cache the matched solved example across retries).
- Claude's extended thinking is well-suited to Stage 3 Planning (deliberate, structured).
- The Anthropic SDK's tool-use shape composes cleanly with the SHERPA "tools at leaves" discipline.

The vendor-agnostic shim is the upgrade path — implement it behind the leaf interface so swapping or A/B testing later is a config change, not a refactor.

## Evidence needed to resolve

- **Per-task evaluation.** For each leaf node type (assessment, planning, autonomous execution, error triage, LLM judge), which vendor produces better outputs? Measured against post-merge incident rates and human-reviewer overrides.
- **Cost per evaluation.** Token cost at the chosen model tier per leaf invocation.
- **Latency.** P50 and P95 latency for the planned prompt+output sizes.
- **Reliability.** Outage frequency, retry-after rate during peak hours.
- **Capability gaps.** Does one vendor offer a feature (e.g., file-attachment, computer-use, citations) that materially improves a specific leaf?

## Reversibility (of the eventual choice)

**Low cost** if the vendor-agnostic shim is in place from day one. **Medium cost** if leaves are coded directly against Anthropic's SDK and need migration. Recommendation: build the shim from day one, even if it's a thin layer.

## Evidence / sources

- `../design.md §4.1` (leaf LLM calls inside SHERPA subgraphs)
- `../design.md §4.2` (SDK choice isolated to leaf nodes — composition lets us defer this)
- `../design.md §7` (Open questions — Agents SDK at the leaves)
- Anthropic SDK 2026 documentation — prompt caching, extended thinking, tool use
- OpenAI Codex precedent on Temporal (`../../auto-agent-design.md §2.3`)
