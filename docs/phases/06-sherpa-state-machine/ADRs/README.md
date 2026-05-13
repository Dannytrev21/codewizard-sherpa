# Phase 6 — SHERPA-style state machine for the vuln loop: ADRs

Architecture Decision Records for Phase 6, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Devil's-advocate critique:** [critique.md](../critique.md) — the attacks the synthesis had to answer.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-lazy-singleton-build-vuln-loop-factory.md) | `build_vuln_loop()` is a lazy-singleton factory, not a module constant | runtime · performance · testability |
| [0002](0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md) | `VulnLedger` is `frozen=False`, with a runtime `id()`-diff after-node hook | state · pydantic · langgraph-idiom |
| [0003](0003-per-gate-retry-counter-scope.md) | `retry_count` is scoped per gate transition, with same-signature flake short-circuit | retry · semantics · phase5-parity |
| [0004](0004-retry-re-enters-phase4-fallback-tier.md) | Retry routes back to Phase 4's `FallbackTier.run` via a single `retry_phase4` edge | retry · phase4-integration · planner |
| [0005](0005-static-schema-version-literal-pin.md) | `schema_version: Literal["v0.6.0"]` — static, not dynamic `blake3(model_json_schema())` | state · schema · durability |
| [0006](0006-audited-sqlite-saver-per-workflow-fsync.md) | Per-workflow SQLite checkpointer with fsync at every node boundary | durability · checkpointer · concurrency |
| [0007](0007-blake3-chain-extension-and-tamper-evidence.md) | Checkpointer extends Phase 5's BLAKE3 audit chain — one chain across Phases 2–6 | audit · tamper-evidence · cross-phase-contract |
| [0008](0008-hitl-operator-auth-deferred-to-phase11.md) | HITL operator authentication is deferred to Phase 11 — Phase 6 ships typed `HumanDecision` only | hitl · scope · deferred-security |
| [0009](0009-cli-loop-ships-parallel-to-cli-remediate.md) | `cli/loop.py` ships parallel to `cli/remediate.py` — Phase 0–5 source untouched | cli · extension-by-addition · phase7-integration |
| [0010](0010-phase5-runner-run-one-public-promotion.md) | Promote Phase 5's `GateRunner._run_one_attempt` to a public `run_one` — the single surgical Phase 5 touch | phase5-contract · surgical-change · parity-test |
| [0011](0011-sqlite-throughput-watch-and-postgres-escalation.md) | SQLite throughput is measured in CI — < 100 writes/s pulls Phase 9 Postgres forward | performance · durability · phase9-trigger |
| [0012](0012-pure-edge-discipline-tests-over-acl-machinery.md) | `@pure_edge` for routing + per-node unit tests — no field-ACL or docstring-AST machinery | routing · testing · determinism |
| [0013](0013-json-golden-topology-snapshot-svg-advisory.md) | JSON-form golden-graph topology is the CI gate; SVG is committed for review only | testing · golden-files · langgraph-cli |

## Conventions

- Filenames `NNNN-kebab-case-title.md`, zero-padded 4-digit, numbered locally per phase from 0001.
- Numbers are immutable — a superseded ADR keeps its number; the new ADR gets the next number with a cross-link.
- Production ADR refs use `../../../production/adrs/NNNN-*.md`.
- Sibling phase ADR refs use `[ADR-NNNN](NNNN-...md)` within this directory.
- Status starts at **Accepted** for ADRs written from synthesized designs (the decision is the synthesizer's commitment); future amendments may add **Superseded by ADR-NNNN** entries.

## Decisions noted but not yet documented in arch / final-design

These are decisions the design *implies* or *flags as needing resolution before merge* but does not yet record as a load-bearing ADR. The implementer or the next architect pass should write them or surface them.

- **ADR-P6-008 (proposed in phase-arch-design.md §Gap analysis Gap 1).** Roadmap exit-criterion wording "fail twice in a row" vs ADR-0014's `max_attempts=3` default. The Phase 6 design parametrizes `max_attempts=2` in the exit-criterion test to match the roadmap's literal wording while keeping production default at 3, but the divergence between roadmap and production is unresolved. Either amend the roadmap or change the default; surface a Phase-6 ADR before merge.
- **`HumanDecision.action="continue"` after a same-signature flake (Gap 4).** The design currently routes back to `non_retryable` because the same-signature pair is still in `prior_attempts`. Implementer must choose: (a) clear `prior_attempts`, (b) insert a `hitl_continue` marker the detector skips, or (c) document and add a CLI warning. ADR-worthy if (a) or (b) is chosen.
- **The first schema-bump migration shape (`v0.6.0 → v0.7.0`).** Phase 6 ships the registry but no migrations. The convention for `graph/migrations/v0_6_0_to_v0_7_0.py` (a single `def migrate(blob: dict) -> dict` function?) is unspecified by design; the first phase that adds a field will set the convention and should write an ADR amending ADR-0005.
- **Concurrent-throughput threshold (referenced in ADR-0011).** ADR-0011 says "at least 10× the single-workflow throughput"; the actual number is set after the first CI run records the baseline. Once a baseline lands, amend ADR-0011 with the chosen threshold.
- **`langgraph-cli` operational role in Phase 9.** Phase 6 treats `langgraph-cli` as a dev-only topology renderer; Phase 9's Postgres move may break it. Phase 9 owns the operator-inspection-tool decision (`temporal-ui` or analog); Phase 6 explicitly does not pre-design.
