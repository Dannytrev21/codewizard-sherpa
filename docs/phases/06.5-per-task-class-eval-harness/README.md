# Phase 6.5 — Per-task-class eval harness + first benches *(preamble to Phase 7)*

**Design pipeline:** `roadmap-phase-designer` → `phase-architect` → `phase-story-writer` — **all three complete**
**Status:** Design pipeline complete. 36 stories ready for autonomous implementation. See [`stories/README.md`](stories/README.md) for the manifest + dependency DAG.
**Roadmap entry:** [`../../roadmap.md` §Phase 6.5](../../roadmap.md)
**Anchor ADR:** [Phase 5 ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — per-task-class eval harness as evidence source for trust-tier promotion, threshold calibration, and LLM-Judge un-deferral.

## What this phase delivers

A per-task-class eval harness — `src/codegenie/eval/` package with `@register_task_class` registry, `BenchScore` Pydantic model, runner, audit chain, and read-only trust-tier promotion gate — plus the `bench/{task-class}/` directory contract enforced by fence-CI, the backfilled `bench/vuln-remediation/` set (≥10 curated cases), and the seed `bench/migration-chainguard-distroless/` skeleton (≥3 cases) that Phase 7 expands. Offline cadence — runs nightly, never per-PR; per-PR strict-AND from [production ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md) is unchanged.

The phase exists because [Phase 5 ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) committed to the contract but deferred the implementation, and Phase 7's introduction of a second task class (Chainguard distroless migrations) cannot land without a per-task-class evidence source that justifies tier promotion off the conservative starting tier. The non-integer phase number (6.5) keeps the change surgical — renumbering Phases 7–16 to slot a preamble in would ripple through cross-doc references for no architectural gain.

## Reading order

Start with the design of record. Consult the per-lens designs and critique as audit trail / source material.

1. **[final-design.md](final-design.md)** — **the design of record.** Synthesized from the three competing designs + critique using Graph-of-Thought decomposition (Besta et al., 2308.09687). Annotated with provenance per component (`[P]`, `[S]`, `[B]`, `[synth]`). Includes the full synthesis ledger: vertex/edge counts, conflict-resolution table, shared-blind-spot disposition, departures from all three inputs, exit-criteria checklist, load-bearing-commitments check, roadmap coherence check. *Reading time: 30–45 min.*

2. **[critique.md](critique.md)** — devil's-advocate attacks on each of the three competing designs, with concrete-by-name findings (components, decisions, numbers). Surfaced the load-bearing fork (rubric execution model) and three shared blind spots (canary-token cassette breakage, uncurated bench cases, undefined block-severity). *Reading time: 15–20 min.*

3. **[design-performance.md](design-performance.md)** — competing design under the performance-first lens. Optimizes for nightly eval wall-clock, $/run, cache hit rate on unchanged-cassette + unchanged-rubric reruns, fence-CI overhead. Key bets: content-addressed `BenchScore` cache keyed on `blake3(case || sut || rubric || cassette)`; `asyncio.Semaphore` bounded pool sized to sandbox concurrency; streaming JSONL sinks. *Reading time: 15–20 min.*

4. **[design-security.md](design-security.md)** — competing design under the security-first lens. Optimizes for rubric-execution isolation, bench-case provenance integrity, audit-chain tamper detection, promotion-authorization defense in depth. Key bets: rubric in microVM; two-signature Sigstore/GPG bench-case provenance; BLAKE3-chained `.codegenie/bench/history/` with daily Sigstore-signed published anchors; six-layer defense-in-depth. *Reading time: 15–20 min.*

5. **[design-best-practices.md](design-best-practices.md)** — competing design under the best-practices-first lens. Optimizes for idiomatic Python, mirrored project patterns, mypy-strict cleanliness, minimal abstraction count. Key bets: `@register_task_class` byte-for-byte mirror of `@register_probe` and `@register_signal_kind`; `BenchScore` mirrors `ObjectiveSignals` (`frozen=True, extra="forbid"`); serial runner (simplicity over throughput); `PromotionGate` is read-only. *Reading time: 15–20 min.*

## Key synthesized decisions

Highlights from `final-design.md` worth knowing before opening the file:

- **Rubric execution model: subprocess + scrubbed env** (Departure from all three inputs). In-process (`[P]`/`[B]`) is RCE on operator host; full Firecracker microVM (`[S]`) forks Phase 5's sandbox stack on macOS and breaks the curator dev-loop. Subprocess via stdlib defeats credential read + arbitrary FS write + harness-state import at ~150 ms/case. Residual risk (host-level network reachable from rubric child) is documented and deferred to Phase 16.
- **All three critic-flagged shared blind spots resolved in-design**, not deferred:
  - Phase 4 canary-token cassette breakage → per-case `cassette_canary_pin: str` in `case.toml`; additive `seed` kwarg threaded into Phase 4's `Canary.mint(...)`. Phase 4 ADR amendment drafted as part of this phase's deliverables.
  - Bench-case curation source → `curation_class: rag-corpus-derived | held-out` with fence-CI-enforced ≥5 held-out split per task class. Memorization tests (RAG-corpus-derived) and judgment tests (held-out) are distinguished.
  - `block`-severity definition → per-task-class `failure_modes.yaml` taxonomy; typed `FailureMode` model with `severity: Literal["block","warn","info"]`; unknown codes resolve to `rubric.unknown_failure_mode` (block-severity).
- **Promotion gate keys on `lower_bound_95` (BCa bootstrap), not `mean`** — addresses critic's N=10 statistical-noise concern. Phase 7's hard precondition shifts to `bench_score.lower_bound_95 ≥ tier_threshold[bronze]`.
- **Tier identifiers as `str` validated at startup against `docs/trust-tiers.yaml`**, not `Literal[...]` — extension by addition wins over compile-time exhaustiveness.
- **Bench-driven SUT invocations tagged via `CODEGENIE_BENCH_INVOCATION_TAG` env + additive `bench_invocation: bool` field on `SandboxCostEntry`** (Phase 5 ADR-0010 amendment) — closes the Phase 13 cost-ledger pollution gap the critic flagged.
- **Per-task-class `BreakdownKey` StrEnum + fence-CI ban on `confidence|llm|self_reported|model_says` substrings at *dict-key value* level**, not just field names — closes the LLM-judgment-smuggling hole the critic found in `breakdown: dict[str, float]`.

## ADRs implied (drafted by `phase-architect` in the next pass)

Six new Phase 6.5 ADRs are implied by the final design:
1. Subprocess-isolated rubric execution (the load-bearing fork)
2. Per-case `cassette_canary_pin` + Phase 4 `seed` kwarg amendment
3. `curation_class` split + held-out-set fence enforcement
4. `failure_modes.yaml` taxonomy + `block`-severity contract
5. Promotion gate keys on bootstrap `lower_bound_95`
6. Bench-invocation tagging on `SandboxCostEntry` (Phase 5 ADR-0010 amendment)
7. ADR-0016 amendment clarifying "automatic demotion" = recommendation-shift, not side-effect

`phase-architect` will produce `phase-arch-design.md`, the per-phase `ADRs/` directory in Nygard format, and `High-level-impl.md` as the implementation-step roadmap.

## Provenance

| Round | Agent | Output | Token usage |
|---|---|---|---|
| 1 (parallel) | Performance-first designer | `design-performance.md` | ~85k |
| 1 (parallel) | Security-first designer | `design-security.md` | ~92k |
| 1 (parallel) | Best-practices designer | `design-best-practices.md` | ~123k |
| 2 | Devil's-advocate critic | `critique.md` | ~141k |
| 3 | Graph-of-Thought synthesizer | `final-design.md` | ~187k |

Synthesizer's full vertex/edge/conflict counts are inside `final-design.md` §Synthesis ledger.
