# ADR-0026: `MigrationConfidence` is a single sum-type rollup the orchestrator refuses against

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · sum-type · functional-core · honest-confidence · single-refusal-point
**Related:** [0023](0023-runtime-compat-probe.md), [0024](0024-multi-arch-and-external-registry-checks.md), [0025](0025-migration-refusal-taxonomy.md), [0021](0021-runtime-shell-invocation-probe.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

By Amendment A, the gather pipeline produces a dozen confidence signals. Every probe reports `confidence: Literal["high","medium","low"]` (the frozen Probe contract). Every provenance adapter reports `AdapterConfidence ∈ {High, Degraded, Unavailable}`. `BaseImageProbe`'s mirror-registry detection ([0024](0024-multi-arch-and-external-registry-checks.md)) degrades an adapter; `RuntimeShellInvocationProbe` and `RuntimeCompatProbe` ([0023](0023-runtime-compat-probe.md)) each carry their own `confidence`.

The problem (M1 in `../final-design.md §Amendment A §A.2`): there is **no single value the orchestrator can refuse against**. Today it would have to scatter `if slice.confidence == "low"` and `if adapter.confidence == Degraded` checks across the dispatch path — gate-and-pray, with no one place that says "this migration is too uncertain to auto-apply." A new probe added later would silently *not* be considered unless someone remembered to add another check. `../phase-arch-design.md §Component design — Amendment A §21` resolves M1 with a single typed rollup and a pure aggregation function.

## Options considered

- **Option A — Scatter per-probe / per-adapter confidence checks across the orchestrator.** Each consumer site re-decides whether a `low` slice or a `Degraded` adapter matters. **Pattern:** Inline conditionals at every call site. **Rejected** — gate-and-pray: there is no single refusal point, the checks drift apart, and a probe added in a later story is silently excluded from the gate until someone updates every site. This is exactly the "primitive obsession / hidden-state" failure the project's domain-modeling discipline forbids.
- **Option B — One typed rollup the orchestrator matches on.** A frozen tagged union `MigrationConfidence = High | Degraded(reasons) | Refused(reason)` plus a pure free function `aggregate_migration_confidence(slices, adapters) -> MigrationConfidence`. **Pattern:** Sum type for state + functional-core aggregation; one value to refuse against, exhaustive `match`.
- **Option C — A numeric 0.0–1.0 confidence score with a refusal threshold.** **Pattern:** Threshold gate. **Rejected** — an opaque threshold (why 0.7?) hides *which* probe degraded; "0.62" is not actionable, and a numeric score invites tuning the threshold to make a borderline migration pass — exactly the override-by-numbers the strict-AND gate discipline ([0012](0012-dockerfile-policy-gate-strict-and-no-override.md)) rejects.

## Decision

Adopt **Option B.** Ship `MigrationConfidence` — a frozen tagged union — and `aggregate_migration_confidence`, a pure free function (functional-core), both at `plugins/distroless-migration--node--npm/migration_confidence.py`:

```python
class High(_Frozen): ...
class Degraded(_Frozen):
    reasons: tuple[str, ...]          # human-readable, names the degrading probe/adapter
class Refused(_Frozen):
    reason: str

MigrationConfidence = Union[High, Degraded, Refused]

def aggregate_migration_confidence(
    slices: Mapping[str, ProbeSlice],
    adapters: Sequence[AdapterResult],
) -> MigrationConfidence: ...
```

Rollup rule:

- Any load-bearing probe slice reporting `confidence == "low"`, **or** any adapter reporting `AdapterConfidence.Degraded` → the rollup is `Degraded(reasons=...)`, each reason naming the source.
- A typed refusal already present (a `RemediationOutcome.PendingHumanReview` variant, [0025](0025-migration-refusal-taxonomy.md)) → the rollup is `Refused(reason)`.
- Otherwise → `High`.

The orchestrator does a single exhaustive `match` on `MigrationConfidence`: `High` → apply the recipe; `Degraded` → **escalate to HITL** instead of applying; `Refused` → halt with the typed refusal. There is exactly one refusal point, and adding a new probe means adding it to the load-bearing set in one place — it is then automatically considered.

## Tradeoffs

| Gain | Cost |
|---|---|
| One value the orchestrator refuses against — a single exhaustive `match`, no scatter, no gate-and-pray | The "load-bearing probe" set is itself a list that must be maintained; a probe omitted from it is silently not considered. Mitigated: the set is one module-level `Final` tuple, AST-fence-checked against the registered Phase-7 probes |
| `Degraded(reasons)` and `Refused(reason)` carry *why* — HITL sees "`base_image` adapter Degraded: non-public mirror registry", not an opaque "0.62" | The rollup collapses heterogeneous signals (probe `low` vs adapter `Degraded`) into one verdict; the `reasons` tuple is the only place the granularity survives. Accepted: `reasons` is structured enough for HITL and for the PR description |
| Pure free function — `aggregate_migration_confidence` is functional-core: deterministic, trivially unit- and property-testable, no I/O, no hidden state | A pure function needs all inputs passed explicitly (`slices`, `adapters`); the orchestrator must assemble them. Accepted — explicit inputs are the point; no hidden global confidence state |
| Property-tested for **monotonicity** — adding a `Degraded` input never improves the rollup (`High → Degraded → Refused` is a lattice; a degrading signal can only move down or hold) | Monotonicity must be stated as a property and tested, not assumed; a future edit that breaks it (e.g. a `low` probe that "cancels out") would be a silent regression. Mitigated: the property test is the guard |
| Rejecting the numeric score keeps the project's no-opaque-threshold discipline — consistent with the strict-AND gate ([0012](0012-dockerfile-policy-gate-strict-and-no-override.md)) | Three coarse states cannot express "slightly degraded vs badly degraded." Accepted: the migration decision is binary-ish (auto-apply vs HITL); coarse is honest, fine-grained invites tuning |

## Pattern fit

Instantiates **Sum type for state — make illegal states unrepresentable** (production ADR-0033) — `MigrationConfidence` has exactly three arms; there is no "confident but also refused" state, and every consumer `match`/`assert_never`s exhaustively. Implements **Functional core / imperative shell** (CLAUDE.md §Conventions) — `aggregate_migration_confidence` is pure; the orchestrator (the shell) does the I/O and the escalation. Honours **Honest confidence** (production design §2.3) and **single refusal point** — one typed value the gate refuses against, rejecting both the scattered-conditionals (Option A) and the opaque-threshold (Option C) anti-patterns.

## Consequences

- `plugins/distroless-migration--node--npm/migration_confidence.py` is a net-new file (the `MigrationConfidence` union + `aggregate_migration_confidence`), allowlisted by [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- The orchestrator gains one `match` on `MigrationConfidence`: `High` → apply recipe; `Degraded` → escalate to HITL (no recipe applied); `Refused` → halt with the typed refusal.
- The load-bearing-probe set is a module-level `Final[tuple[str, ...]]` of slice names; a fence test asserts it against the registered Phase-7 probe set so a new probe cannot be silently omitted.
- `aggregate_migration_confidence` is pure — unit-tested per arm and **property-tested for monotonicity**: for any input set, adding a `Degraded`/`low` signal yields a rollup `≤` the original on the `High > Degraded > Refused` lattice (never an improvement).
- `Degraded.reasons` and `Refused.reason` are rendered in the PR description (M3) and the HITL escalation payload — the human sees which probe/adapter degraded.
- Consumes `AdapterConfidence` ([0024](0024-multi-arch-and-external-registry-checks.md)) and every probe `confidence` (incl. `RuntimeCompatProbe` [0023](0023-runtime-compat-probe.md), `RuntimeShellInvocationProbe` [0021](0021-runtime-shell-invocation-probe.md)); produces the single value the refusal taxonomy ([0025](0025-migration-refusal-taxonomy.md)) and the orchestrator share.
- Adding a new arm to `MigrationConfidence` (unlikely — three is intentionally complete) is a Phase-7-ADR amendment.

## Reversibility

**High.** `aggregate_migration_confidence` is a pure function with a typed signature — its implementation can be rewritten freely (different rollup rule, more `reasons` granularity) without touching any caller, and the orchestrator's single `match` is the only consumer. The `MigrationConfidence` union shape is the contract; the function behind it is fully swappable. The only sticky part is the three-arm union itself — once Phase 8+ consumers `match` on it, adding or removing an arm is a coordinated change — but the aggregation logic is the easiest thing in Amendment A to revise.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (M1 row — `MigrationConfidence` aggregator), `§A.1` (governing principle — refuse with typed evidence)
- `../phase-arch-design.md §Component design — Amendment A §21` (`MigrationConfidence` aggregator — `aggregate_migration_confidence` signature, pure / functional-core)
- [ADR-0023 — `RuntimeCompatProbe` (probe `confidence` feeds the rollup)](0023-runtime-compat-probe.md)
- [ADR-0024 — Multi-arch & external-registry checks (`AdapterConfidence.Degraded` feeds the rollup)](0024-multi-arch-and-external-registry-checks.md)
- [ADR-0025 — Migration refusal taxonomy (`Refused` arm)](0025-migration-refusal-taxonomy.md)
- [ADR-0012 — `DockerfilePolicyGate` strict-AND, no override (no-opaque-threshold precedent)](0012-dockerfile-policy-gate-strict-and-no-override.md)
- [production ADR-0033 — Domain modeling discipline (sum types, make illegal states unrepresentable)](../../../production/adrs/0033-domain-modeling-discipline.md)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
