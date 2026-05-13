# Phase 6.5 — Per-task-class eval harness + first benches: ADRs

Architecture Decision Records for Phase 6.5, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Devil's-advocate critique:** [critique.md](../critique.md) — surfaces the load-bearing forks these ADRs resolve.
**Anchor ADR:** [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — Phase 6.5 implements this commitment.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-rubric-execution-isolation-via-subprocess.md) | Rubric runs as a scrubbed-env subprocess — not in-process, not microVM | isolation · security · trust-boundary · rubric |
| [0002](0002-promotion-gate-keys-on-lower-bound-95.md) | Promotion gate keys on `lower_bound_95` (BCa bootstrap), not `mean_score` | statistics · promotion · honest-confidence · phase-7-precondition |
| [0003](0003-tier-identifiers-as-str-validated-at-startup.md) | Tier identifiers are `str`, validated at startup against `docs/trust-tiers.yaml` | extension-by-addition · type-system · contract-data |
| [0004](0004-per-task-class-failure-modes-taxonomy.md) | Per-task-class `failure_modes.yaml` taxonomy with typed `FailureMode` | taxonomy · trust · promotion · extension-by-addition · fail-loud |
| [0005](0005-cassette-canary-seed-parameterization.md) | Per-case `cassette_canary_pin` + Phase 4 `Canary.mint(seed=...)` additive amendment | cassettes · determinism · phase-4-amendment · cross-phase-boundary |
| [0006](0006-curation-class-split-with-fence-ci-held-out-floor.md) | Bench cases split by `curation_class` — `rag-corpus-derived` vs `held-out` with fence-CI floor | memorization · judgment · curation · fence-ci · phase-7-precondition |
| [0007](0007-bench-invocation-tagging-on-sandbox-cost-entry.md) | Bench-invocation tagging on `SandboxCostEntry` via env-var contract — amends Phase 5 ADR-0010 | cost-ledger · phase-5-amendment · phase-13-handoff · cross-phase-boundary |
| [0008](0008-breakdown-keys-strenum-with-substring-ban.md) | Per-task-class `BreakdownKey` StrEnum + fence-CI substring ban at value level | llm-judgment-smuggling · type-safety · static-introspection · fence-ci |
| [0009](0009-automatic-demotion-as-recommendation-shift.md) | "Automatic demotion" semantics — recommendation-shift, not side-effect (amends Phase 5 ADR-0016) | promotion · demotion · humans-always-merge · adr-amendment |
| [0010](0010-isolation-class-annotation-on-bench-run-report.md) | `isolation_class` annotation on `BenchRunReport` for Phase 16 microVM upgrade safety | audit-chain · phase-16-handoff · isolation-upgrade · population-mixing |

## Conventions

- **Filenames** `NNNN-kebab-case-title.md` zero-padded, numbered locally per phase from 0001.
- **Numbers are immutable** — superseded ADR keeps its number; new ADR gets next number + cross-links.
- **Cross-references** to production ADRs: `../../../production/adrs/NNNN-*.md`. To sibling Phase 5 ADRs: `../../05-sandbox-trust-gates/ADRs/NNNN-*.md`. Within Phase 6.5: `NNNN-*.md`.
- Phase ADR numbering is **local to this phase**; it does not continue from production ADR numbers. Phase 6.5 ADR-0001 is unrelated to production ADR-0001.

## ADRs that amend prior decisions

This phase produces three amendments to already-accepted decisions. Each is captured as a Phase 6.5 ADR; the amended document gains an "Amended by" cross-link as part of phase-6.5 work:

- Amends **Phase 4 final design** (cassette canary discipline — additive `seed: bytes | None` kwarg on `Canary.mint`) — captured in [ADR-0005](0005-cassette-canary-seed-parameterization.md). The Phase 4 ADR (`ADR-P4-006-canary-seed-kwarg.md`) is drafted as part of Phase 6.5 work.
- Amends **[Phase 5 ADR-0010](../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md)** (cost-ledger schema — additive `bench_invocation: bool` field on `SandboxCostEntry`) — captured in [ADR-0007](0007-bench-invocation-tagging-on-sandbox-cost-entry.md).
- Amends **[Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) §Decision §4** ("automatic demotion" semantics — recommendation-shift, not side-effect) — captured in [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md).

## ADR clusters

The ten ADRs group into four load-bearing themes. Reading the cluster together is faster than reading the index linearly.

- **Trust posture & evidence semantics** — [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md) (rubric isolation), [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md) (statistical gate signal), [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md) (no autonomous tier mutation), [ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md) (audit-chain invariance under Phase 16 upgrade).
- **Anti-smuggling structural defenses** — [ADR-0004](0004-per-task-class-failure-modes-taxonomy.md) (failure-mode taxonomy is data), [ADR-0008](0008-breakdown-keys-strenum-with-substring-ban.md) (dict-key LLM-judgment ban).
- **Curation discipline** — [ADR-0005](0005-cassette-canary-seed-parameterization.md) (deterministic cassette replay), [ADR-0006](0006-curation-class-split-with-fence-ci-held-out-floor.md) (memorization-vs-judgment split).
- **Extension by addition + cross-phase contracts** — [ADR-0003](0003-tier-identifiers-as-str-validated-at-startup.md) (tier slugs as data), [ADR-0007](0007-bench-invocation-tagging-on-sandbox-cost-entry.md) (Phase 5 cost-ledger amendment).

## Decisions noted but not yet documented in arch / final-design

The phase-architect's gap analysis surfaced four candidate decisions; two were promoted to ADRs ([ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md) closes Gap 1; [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md) closes the §"automatic" ambiguity). The other two remain as paragraphs in `phase-arch-design.md` rather than ADRs:

- **`_codegenie_bench` vs `bench` import-path resolution** (`phase-arch-design.md §Gap analysis Gap 2`, §Open questions #3) — The architecture recommends Option A (prepend `bench/`'s parent to `sys.path`; import `bench.{name}.registration` directly) with Option B (`MetaPathFinder`) as the contingency. The decision is *implementation-time-recoverable*: if Option A surfaces a packaging conflict in CI, Option B is the documented fallback. Promote to an ADR only if Option B is chosen at implementation time, or if the resolution affects external consumers.
- **Case-ID collision as a fence-CI assertion** (`phase-arch-design.md §Gap analysis Gap 3`) — The architecture promotes this to a seventh fence-CI assertion + a `loader.py` `BenchCaseIDCollision` raise (defense-in-depth). The change is mechanical and inside the existing fence-CI envelope; no architectural fork. Promote to an ADR only if a contributor objects to the assertion or proposes a different containment.
- **`complete: bool` field on `BenchRunReport` + partial-run handling** (`phase-arch-design.md §Gap analysis Gap 4`) — The architecture commits to the field and to `PromotionGate.evaluate(...)` rejecting `complete=False` reports. The change is one bool, one early return, one `VerifyResult` tuple field — small enough that the architecture spec is its own canonical record. Promote to an ADR if a future phase changes the rejection semantics (e.g., allows partial reports under a `--allow-partial` flag).
- **Per-host vs canonical-host fingerprinting for the audit chain** (`phase-arch-design.md §Gap analysis Gap 5`, §Open questions #2) — Implementation must pick the fingerprint construction (hostname-derived vs UUID-on-first-run). Both work; the architecture surface area is small. Promote to an ADR when the CI substrate's matrix structure becomes load-bearing (Phase 13 or Phase 16 territory).

If any of these decisions hardens into a load-bearing fork during implementation, the ADR set should grow; the local-numbering convention guarantees the new ADR gets the next sequential number with no renumbering of the existing ten.
