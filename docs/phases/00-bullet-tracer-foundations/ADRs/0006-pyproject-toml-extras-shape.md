# ADR-0006: `pyproject.toml` extras shape — `gather` / `dev` / `service` / `agents`

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** packaging · dependencies · phase-evolution · supply-chain
**Related:** [ADR-0002](0002-fence-ci-job-no-llm-in-gather.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`production/design.md §2.1` and [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) make "no LLM in gather" load-bearing. Phase 4 introduces `anthropic` and `langgraph`; Phase 9 introduces `temporalio` and Postgres clients. Phase 0's `pyproject.toml` shape determines where those dependencies *can* land.

`../critique.md §6.1` flags as a shared blind spot: none of the three lens designs lays down the `[project.optional-dependencies]` shape Phase 4 needs to slot into. The roadmap text lists `pydantic` and `aiofiles` as Phase 0 deps without addressing the split. `../critique.md §7.3` notes that the roadmap's Phase 0 dep list and the best-practices lens's "defer pydantic to Phase 6" are in direct conflict.

If Phase 4 has to refactor `pyproject.toml` to introduce the LLM SDKs, that's a violation of `production/design.md §2.5` (extension by addition). The slot has to exist in Phase 0.

## Options considered

- **One `dev` extra, everything else in `[project]` (the lens-design default).** Phase 4 adds `anthropic` to `[project.dependencies]` and the fence ([ADR-0002](0002-fence-ci-job-no-llm-in-gather.md)) immediately fires. The split is invisible until it breaks.
- **`gather` extra + `dev` extra.** `dependencies` is gather-runtime; `[gather]` is empty marker; `[dev]` carries the harness. Phase 4 has no slot — has to add `[agents]` retroactively.
- **`gather` + `dev` + `service` + `agents` with empty future-reserved extras (synth, [ADR-0006](0006-pyproject-toml-extras-shape.md)).** Phase 0 declares all four slots. `dependencies` *is* the gather-pipeline closure (no `[gather]` content required). `[agents]` is empty in Phase 0; Phase 4 fills it. `[service]` is empty in Phase 0; Phase 9 fills it. The fence (ADR-0002) enforces the boundary.
- **One extra per dep group exactly when needed.** Add `[agents]` in Phase 4, `[service]` in Phase 9. Minimal Phase 0 surface; each addition is a `pyproject.toml` change that touches the file every contributor reads — high-visibility but high-friction.

## Decision

**`pyproject.toml` ships four slots in Phase 0:**

```toml
[project]
dependencies = [
  # gather-pipeline runtime closure — this is what the fence guards
  "click", "pyyaml", "jsonschema", "pydantic", "structlog", "blake3",
]

[project.optional-dependencies]
gather = []   # intentionally empty; the gather closure is [project.dependencies]
dev     = [...]  # harness: pytest, mypy, ruff, mkdocs, bandit, ...
service = []  # Phase 9+ (Temporal, Postgres clients)
agents  = []  # Phase 4+ (anthropic, langgraph) — LLM SDKs land here, NOT in dependencies
```

The fence CI job ([ADR-0002](0002-fence-ci-job-no-llm-in-gather.md)) asserts `set(distribution("codewizard-sherpa").requires) ∩ {anthropic, langgraph, openai, langchain, transformers}` is empty. The `gather` extra is intentionally empty — its existence marks the slot semantically; the runtime closure is `[project.dependencies]` itself.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 4 lands LLM SDKs in `[agents]` by *adding* lines, not refactoring `pyproject.toml` — extension by addition (`production/design.md §2.5`) holds at the dependency level | Two empty extras in Phase 0 (`service`, `agents`) — they look unused; readers must understand the *slot* is the contract, not the contents |
| The fence is scoped to `dependencies` and stays clean — `dev` extra's transitive deps are allowed to contain LLM SDKs (e.g., a hypothetical mkdocs plugin) | The fence test must be carefully scoped to `dependencies` (not `optional-dependencies`); widening it accidentally breaks `dev` install |
| Phase 9's Temporal addition is symmetric — `[service]` slot exists, fill it then | The "empty extras are reserved slots" convention has to be documented (Phase 0 `contributing.md`) |
| `pydantic` lands in Phase 0 as a gather-pipeline runtime dep — supports the `_ProbeOutputValidator` trust boundary ([ADR-0010](0010-pydantic-probe-output-validator.md)) | Resolves the roadmap-vs-best-practices conflict (`critique.md §7.3`) by adopting the roadmap's `pydantic` (against `[B]`'s defer-to-Phase-6 stance) |
| `aiofiles` removed from Phase 0 deps (unused code path) — honors "ship only what you use" | Documentation bug in `roadmap.md` filed as a Phase 0-close issue |

## Consequences

- The gather-pipeline runtime closure is `[project.dependencies]`. Any future PR adding an LLM SDK to that list is rejected by the `fence` CI job — automatic enforcement of [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md).
- `pip install codewizard-sherpa` installs the gather pipeline only. `pip install codewizard-sherpa[agents]` adds LLM SDKs (Phase 4+). `pip install codewizard-sherpa[service]` adds Temporal + Postgres (Phase 9+). `pip install codewizard-sherpa[dev]` adds the harness.
- The `gather` extra (empty) is the semantic marker that `dependencies` *is* the gather closure. Removing it would obscure the contract; keeping it documents the architectural intent.
- The Phase 0 `Makefile` `bootstrap` target installs `[dev]`; CI matrix's `lint`, `typecheck`, `test`, `docs` jobs install `[dev]`; the `fence` job installs the base `[project]` (no extras) and asserts the closure.
- `pydantic` is in `dependencies` because the `_ProbeOutputValidator` chokepoint ([ADR-0010](0010-pydantic-probe-output-validator.md)) is on the gather hot path. Lazy-imported from the CLI entry to keep `--help` cold-start clean.
- The "future-reserved empty extras" convention also covers Phase 11's PR-opening (potentially `[handoff]` if `PyGithub` lands), Phase 13's cost ledger (potentially `[telemetry]` for OTel), etc. Phase 0 doesn't declare those — the convention is "declare the slot when you know the dep group is coming," not "declare every conceivable future slot."

## Reversibility

**Low.** The four-slot shape lifts unchanged into Phase 4+; reverting would require Phase 4 to move LLM SDKs into `[project.dependencies]`, which the fence ([ADR-0002](0002-fence-ci-job-no-llm-in-gather.md)) would reject. Reverting both ADRs simultaneously is an architecture change that breaks [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md). The shape stays.

## Evidence / sources

- `../final-design.md §2.2` (Tooling and dependencies — extras table)
- `../final-design.md §L3 row 8` (pydantic in Phase 0 vs Phase 6 — wins 12 vs 4)
- `../final-design.md §L4 row 1` (Shared blind spot resolution: `pyproject.toml` shape)
- `../critique.md §6.1` (Shared blind spot)
- `../critique.md §7.3` (Roadmap-vs-design conflict on `pydantic`)
- `../critique.md §7.4` (`aiofiles` listed but unused — fix here)
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — the commitment the slot shape enables enforcing
- [ADR-0002](0002-fence-ci-job-no-llm-in-gather.md) — the fence that uses this shape
