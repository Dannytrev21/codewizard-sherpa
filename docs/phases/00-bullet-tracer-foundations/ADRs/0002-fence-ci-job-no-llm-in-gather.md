# ADR-0002: `fence` CI job enforcing no-LLM-in-gather

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** ci · determinism · supply-chain · invariant
**Related:** [ADR-0006](0006-pyproject-toml-extras-shape.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`production/design.md §2.1` and [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) make "No LLM in the gather pipeline" a load-bearing architectural commitment. Reversibility on that ADR is High — adding an LLM call to a probe would break the cache contract, the replay guarantee, the cost-prediction model, and the audit story simultaneously.

`../critique.md §7.2` and `../critique.md §6.1` both observe that the commitment is enforced *nowhere* in the lens designs. Performance and best-practices ship `[project.optional-dependencies.dev]` as the only extra; security mentions a `gather` extra but doesn't design it. Phase 4 will introduce `anthropic` / `langgraph` into the same `pyproject.toml` unless the structural separation is designed *now*. The roadmap explicitly defers the fence to "Phase 4 will route LLM SDKs through a `service` extra" — by which point the wheel may already pull them transitively.

A load-bearing commitment that isn't a test fails open under contributor pressure.

## Options considered

- **Documentation-only (status quo across all three lens designs).** `production/design.md §2.1` says "no LLM in gather" and the team commits to honoring it. Trust contributors and PR reviewers.
- **Lint rule blocking `from anthropic import` / `from langgraph import` in `src/codegenie/`.** Catches direct imports; misses transitive deps and `importlib`-style indirection.
- **Runtime check at CLI startup.** Inspect `sys.modules` after import; refuse to run if an LLM SDK is loaded. Brittle (depends on probe import order); detection lags introduction.
- **CI test asserting the wheel's runtime dependency closure contains no LLM SDK (synth, load-bearing).** Walks `importlib.metadata.distribution("codewizard-sherpa").requires`; intersects with `{"anthropic", "langgraph", "openai", "langchain", "transformers"}`; asserts empty. Catches direct and transitive contamination before merge.

## Decision

**A dedicated `fence` CI job runs `tests/unit/test_pyproject_fence.py` on every PR.** The test computes `set(distribution("codewizard-sherpa").requires) ∩ {"anthropic", "langgraph", "openai", "langchain", "transformers"}` over the installed wheel and asserts the intersection is empty. The test ships with a **deliberate-negative test** (`test_fence_catches_planted_anthropic_dep`) that plants `anthropic` in a synthetic `pyproject.toml` and asserts the check fails — guarding against the check itself silently breaking. The fence job is in the six-job CI matrix and PR-blocking.

## Tradeoffs

| Gain | Cost |
|---|---|
| Production ADR-0005 stops being aspirational; it becomes an executable test that fails red on regression | One more CI job (~5–10s); one more test to maintain |
| The "no LLM in gather" invariant is enforced from Phase 0, not retroactively in Phase 4 | The fence forces the `pyproject.toml` shape (see [ADR-0006](0006-pyproject-toml-extras-shape.md)) to have a real `agents` extra ready before LLM SDKs land |
| The deliberate-negative test inoculates against silent rot of the check itself — the named risk in `../final-design.md §10` risk #5 | Two tests instead of one; ~5 lines extra |
| The intersection list is a contract: future LLM SDKs (Bedrock, Vertex) are added by a one-line PR with mandatory review | The list must be maintained; an SDK not on the list slips through (mitigated: the list is reviewed at each phase boundary) |
| Transitive contamination (e.g., a `dev` plugin pulling `openai`) surfaces immediately | The test is scoped to `dependencies` (not `optional-dependencies`); the `dev` closure is allowed to contain LLM SDKs |

## Consequences

- The wheel's `dependencies` list is the canonical gather-pipeline closure. The `gather` extra in `[project.optional-dependencies]` is intentionally empty — its existence marks the slot, but the runtime closure is `dependencies` itself.
- Any future PR adding an LLM SDK must route it through `[project.optional-dependencies.agents]` and import it from a code path that is *not* loaded by `codegenie gather`. The fence test fails fast if this discipline slips.
- The fence is the structural enforcement of [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md). It sharpens that ADR from aspirational to tested.
- The `fence` job's signature (~5–10s) keeps the CI walltime budget intact.
- The test surface establishes a pattern (deliberate-negative test alongside the real check) reusable for other load-bearing invariants (e.g., the probe-contract snapshot in [ADR-0007](0007-probe-contract-frozen-snapshot.md)).

## Reversibility

**Low.** Adding or removing entries from the intersection set is a one-line PR. Disabling the job entirely is a deliberate `ci.yml` edit. The cost of reversing is small *mechanically* but **High politically** — the fence is the structural backbone of [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md); removing it should require an ADR amendment, not a configuration tweak.

## Evidence / sources

- `../final-design.md §2.2` (fence CI test specification)
- `../final-design.md §3.2` (Six CI jobs — `fence` is job #6, "the load-bearing job")
- `../final-design.md §10 risk #5` (Deliberate-negative test rationale)
- `../phase-arch-design.md §Testing strategy / CI gates` (Phase 0 jobs)
- `../critique.md §7.2` (Critic flags absence of enforcement)
- `../critique.md §6.1` (Shared blind spot: no `pyproject.toml` shape for the split)
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — the commitment this job enforces
