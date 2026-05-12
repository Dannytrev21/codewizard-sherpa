# ADR-0011: `LlmPromptContext` Pydantic schema with `extra="forbid"` as the `RepoContext` exfiltration boundary

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** exfiltration-defense · pydantic-schema · secrets-handling · synthesizer-departure
**Related:** [ADR-0003](0003-plan-envelope-kind-and-target-files-allowlist.md), [ADR-0008](0008-prompt-injection-structural-defenses.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`RepoContext` carries the full file inventory, dep graph, traces (file content excerpts), policy violations, secret-scan results, and Skills text. The three lens designs all sent "a slice of `RepoContext`" to the LLM with no schema-pinned definition of what's in the slice (`critique.md §"Where do all three quietly agree on something questionable"` #3). The security lens capped the prompt at 256 KB, but a 256 KB prompt *is* the exfiltration channel: an injected LLM rewrites a fix to embed the secret in the diff (`// CONFIG_VALUE=<exfiltrated>`); the diff gets to `git apply --check`; the bytes are in the working tree.

The critic identified this as the cross-cutting blind spot. The synthesizer's answer is a Pydantic schema (`LlmPromptContext`) with `extra="forbid"`, an explicit allowlist of allowed fields, and a CI test that constructs a fixture `RepoContext` with seeded synthetic secrets and asserts none reach any built `LlmRequest`.

## Options considered

- **Nothing — send a "slice" of `RepoContext` defined per-call site.** All three lens defaults. No schema, no enforcement, secret-row leakage is ad-hoc.
- **Egress byte cap only.** Security-lens layer. Caps total bytes but doesn't constrain *what* bytes; an attacker exfiltrates 64 KB of secrets just fine.
- **Explicit Pydantic schema with allowlist + `extra="forbid"`.** Synth pick. Schema defines exactly which fields are allowed; every expansion is an ADR amendment; CI test on synthetic secret leakage runs on every schema change.
- **Schema-on-read at the LLM-prompt-builder boundary.** Validate that what's leaving doesn't match secret patterns. Slower (per-call regex sweep), softer guarantee (regexes miss novel secret shapes).

## Decision

Define `LlmPromptContext(BaseModel)` with `model_config = ConfigDict(extra="forbid")`:

```python
class LlmPromptContext(BaseModel):
    advisory: AdvisorySummary                  # CVE id, package, ranges, summary (≤ 1000 chars)
    lockfile_fingerprint: str                  # blake3, not bytes
    node_major: int
    framework_summary: str                     # ≤ 500 chars
    file_inventory: list[str]                  # paths only, no contents
    dep_graph_neighborhood_hash: str           # blake3, not graph
    recipe_failure_reason: Literal[...]        # Phase 3 reason enum
    recipe_failure_diagnostics: dict[str, str] # only string fields, sanitized
    retrieved_examples: list[RetrievedExampleStub]   # ids + advisory_summary + patch
```

**Pruned explicitly:** full source bytes (no `package.json` body), secret-scan rows (`probes/secret_scan` outputs), full dep graph (only the neighborhood hash), trace event bodies (Phase 2 Layer B — only counts), `.git/config`, environment dumps. Max prompt body 256 KB. Schema expansion requires ADR amendment.

CI test `tests/integration/test_llm_prompt_context_does_not_leak_secrets.py` constructs a fixture `RepoContext` containing seeded synthetic secrets and asserts none appear in any built `LlmRequest`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Every field in the LLM prompt is allowlisted by name — secret-row leakage is structurally impossible, not statistically rare | Tighter prompt body may mean the LLM has less context for ambiguous breaking-change cases; fix is to expand the schema deliberately (ADR amendment), not leak `RepoContext` ad-hoc |
| Schema expansion requires an ADR — drift is conspicuous; "let me just add one more field" is a PR-level conversation | Three-line schema additions become ADR amendments; friction is intentional but real |
| CI test on synthetic secret leakage runs on every schema change; novel secret shapes that match the seeded patterns are caught | Real secrets that don't match the seeded patterns may pass; mitigated by the allowlist being narrow (only the named fields ever reach the prompt) |
| `dep_graph_neighborhood_hash` (blake3 of the local neighborhood) is the smallest signal that lets the LLM reason about transitive shape without seeing the graph | Hash-only means the LLM cannot reason about specific package names beyond the advisory's named package; for some breaking-change CVEs this is insufficient |
| `retrieved_examples` is a `RetrievedExampleStub` — ids + advisory summary + patch — not the full `SolvedExample` body | Few-shot bandwidth is constrained; mitigated by the patch being the load-bearing signal for the LLM |
| Schema-pinned exfiltration boundary composes with the egress byte cap (Linux jailed mode) — defense in depth | Two layers to maintain; the schema is the structural defense, the byte cap is the runtime backstop |

## Consequences

- `LlmPromptContext` lives in `src/codegenie/llm/models.py`. Constructed by `PromptBuilder` from `RepoContext`; constructor errors on any field not in the allowlist.
- `PromptBuilder.build(template_id, advisory, repo_ctx, rag_hits)` is the only constructor of `LlmPromptContext`. Fence-CI forbids construction elsewhere.
- Schema versioning: `LlmPromptContext.schema_version: Literal["0.4.0"]`. Bumps land as ADR amendments + JSON Schema snapshot regen.
- Phase 5+ may add a *bounded file-read tool* gated by the microVM; Phase 4 ships tool-less per `final-design.md §"Synthesis ledger"` row "Tool use." When Phase 5 reopens, the file-read tool's results pass through `LlmPromptContext` field-validation too.
- The Phase 1/2 `RepoContext` is the source-of-truth on disk; `LlmPromptContext` is the over-the-wire subset. The Phase 1 schema can grow without affecting the LLM prompt; the LLM prompt can shrink without affecting the gather pipeline.
- Path-traversal attempts in `file_inventory` (`["package.json","../../etc/passwd"]`) are caught by [ADR-0003](0003-plan-envelope-kind-and-target-files-allowlist.md)'s `target_files` allowlist on the output side; the *input* side schema doesn't have that surface (paths are inventory only, not actionable).

## Reversibility

**Low.** Removing the schema means sending `RepoContext` slices defined ad-hoc per call site — the very vulnerability this ADR exists to address. The *fields* are expandable (ADR amendment); the *enforcement mechanism* is durable.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "RepoContext exfiltration boundary"
- `../final-design.md §"Departures from all three inputs"` #4 — `LlmPromptContext` as exfiltration boundary
- `../final-design.md §"Components"` #9 — `LlmPromptContext`
- `../phase-arch-design.md §"Component design"` #9 referenced (egress) + #11 (`LlmPromptContext` schema)
- `../critique.md §"Where do all three quietly agree on something questionable"` #3 — RepoContext slice as missing schema
- Production [ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — no LLM in gather (boundary precedent)
