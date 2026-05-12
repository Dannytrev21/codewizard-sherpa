# ADR-0007: Anthropic model pin via versioned alias `claude-sonnet-4-7@vuln_remediation` resolved at startup

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** model-pin · cassette-discipline · supply-chain · synthesizer-departure
**Related:** [ADR-0012](0012-vcr-cassette-discipline.md), [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md) (digest-pin precedent)

## Context

The model name in every Anthropic request is a load-bearing byte sequence. Every VCR cassette records it. Bumping models bumps the cassette key. Best-practices hard-pinned `claude-opus-4-7-20260415` (dated, opaque); the critic (`critique.md §best-practices.5`) attacked the cassette-corpus-regen bottleneck this creates — every model upgrade becomes a multi-week PR bottlenecked through one engineer who can review every cassette diff. Performance left the model name loose (`"claude-sonnet-4-7"`); the critic (`critique.md §performance.4`) attacked the silent-quality-drift exposure.

The synthesizer's compromise: a versioned alias `claude-sonnet-4-7@vuln_remediation` resolved at startup from `~/.config/codegenie/llm.yaml` to the dated model name in `llm/rates.yaml`. The alias is what appears in code and prompts; the dated name appears only in the resolved request body. Bumps are ADR amendments; cassette-freshness CI script reports drift.

## Options considered

- **Hard pin to a dated model (`claude-opus-4-7-20260415`).** Best-practices. Honest about what's being called but every bump regenerates every cassette through a single human reviewer.
- **Loose pin to a model family (`claude-sonnet-4-7`).** Performance. Hidden upstream rollback risk; cassettes pin a SDK-and-API contract that Anthropic may flip behind a flag.
- **Versioned alias resolved at startup.** Synth. `claude-sonnet-4-7@vuln_remediation` in the code; resolves to the dated name in `llm.yaml` at process start. ADR amendments + cassette-freshness CI catch drift.
- **Multi-model fallback (Opus → Sonnet → Haiku).** Performance had a softer version of this. Rejected — silent quality drift, plus the cost story falls apart if Opus is the resolved tier.

## Decision

Pin via versioned alias. `LlmRequest.model: Literal["claude-sonnet-4-7"]` carries the alias in code; `~/.config/codegenie/llm.yaml` resolves `models.vuln_remediation: claude-sonnet-4-7@vuln_remediation` to the dated model name in `llm/rates.yaml`. Model bumps are ADR amendments; cassette-freshness CI script reports drift on bump. The cassette key (per [ADR-0012](0012-vcr-cassette-discipline.md)) includes a hash of `(model_id, sdk_minor, prompt_template_id, prompt_template_version)` so the bump invalidation is structured. Sonnet 4.7 is the chosen tier (5× cheaper than Opus; fits the $0.08/PR target; better cache discipline).

**No fallback model on upstream failure.** Anthropic upstream 5xx / 529 after 3 transport retries exits 10 `llm.upstream_unavailable`; operator re-runs later. Avoids silent quality drift.

## Tradeoffs

| Gain | Cost |
|---|---|
| Model bump is one config edit + one ADR amendment, not a multi-week cassette-corpus regen | Resolved-name drift between `llm.yaml` and `rates.yaml` is a real footgun; CI gate ("rates table has an entry for every alias resolved") catches it |
| Cassette key includes resolved model + SDK minor; legitimate bumps surface as a structured cassette-key change, not a body-bytes scramble | Two files to edit on bump (`llm.yaml`, `rates.yaml`) + ADR + cassette re-record — friction is intentional but real |
| Sonnet 4.7's cost profile (5× cheaper than Opus, better cache discipline) hits $0.08/PR with 80% cache hit | Sonnet on hard breaking-change CVEs may underperform Opus; Phase 6 reopens the model tier choice once multi-turn replan is available |
| Operator pinning of `~/.config/codegenie/llm.yaml` means dev environments and CI can pin different tiers (cheap Sonnet in dev, the production tier in CI) | The alias-to-dated-name mapping is operator-side config; a misconfigured operator silently hits a different model |
| No fallback model means failures are loud (`exit 10 llm.upstream_unavailable`); operator re-runs | Anthropic outage = phase 4 outage; surfaced as known concession |
| Cassette-freshness nightly canary against the Anthropic free tier catches upstream shape drift before it breaks CI | Free-tier canary needs a recorded fixture and an Anthropic account; mild operational burden |

## Consequences

- `llm/rates.yaml` carries the per-model rate table *and* the alias → dated-name resolution. Schema-validated at startup; exit 11 on malformed.
- `LlmRequest.model` is `Literal["claude-sonnet-4-7"]` (the alias). The resolved dated name appears in the SDK request body, the cassette, and the `cost.llm.invoked` event payload.
- Cassette key hash inputs: `(resolved_model_id, sdk_minor, prompt_template_id, prompt_template_version)`. Bumping any forces a re-record; the structured key makes the invalidation surface obvious.
- Nightly free-tier canary: one call against a tiny fixture. Drift in response shape → CI yellow with a Slack/email notification; humans triage. Yellow not red per `phase-arch-design.md §"Open questions"` #6.
- Phase 6 re-opens streaming + multi-turn; Sonnet 4.7 may flip back to Opus for the reasoning-heavy retry-with-context path. The alias mechanism survives that.
- Phase 4 ships *non-streaming* — closes critic §performance.4 cassette-fragility-on-streaming attack. Phase 6 reopens.

## Reversibility

**High.** The alias is just a config indirection. Reverting to a hard pin means deleting the resolution layer; one PR's worth of work. The decision is durable on the side of "what bumps cost"; the *mechanism* is easy to flip.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Model pin format"
- `../final-design.md §"Components"` #3 — `LeafLlmAgent` + `AnthropicClient` model pin
- `../phase-arch-design.md §"Component design"` #2 — `LlmRequest.model` Literal
- `../phase-arch-design.md §"Tradeoffs"` — Sonnet 4.7 model pin row
- `../critique.md §best-practices.5` — cassette-regen bottleneck on hard pin
- `../critique.md §performance.4` — streaming + structured output fragility
