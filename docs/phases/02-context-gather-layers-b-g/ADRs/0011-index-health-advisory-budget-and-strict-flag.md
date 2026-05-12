# ADR-0011: `IndexHealthProbe` advisory budget (200 ms, no hard kill); `--strict` flag is the CI failure mechanism

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** honesty-oracle · failure-isolation · budget-policy · cli-flag · synthesizer-departure
**Related:** ADR-0001, ADR-0002, [production ADR-0006](../../../production/adrs/0006-deterministic-gather-no-llm.md), [Phase 0 ADR-0005](../../00-bullet-tracer-foundations/ADRs/0005-coordinator-async-from-day-one.md)

## Context

`IndexHealthProbe` (B2) is the single most important probe in the gather pipeline (`localv2.md §5.2 B2`, `production/design.md §2`): silent index staleness is the worst failure mode for downstream Planner correctness. Phase 2's roadmap exit criterion *names* B2: "IndexHealthProbe surfaces at least one real staleness case in CI (deliberately seeded fixture)."

The three lenses chose mutually-incompatible budget and failure-mode policies (`final-design.md "Conflict-resolution table" D4, D5`):

1. **[P] 50 ms hard budget via `asyncio.wait_for`; `cache_strategy = "none"`.** Critic's §P.3: unachievable — B2's `git rev-list --count` is 20–80 ms by itself; the timeout fires; B2 emits `confidence: low` *deterministically* on every gather, the most important probe in the system permanently lies, the roadmap exit criterion becomes meaningless because every CI run reports `low` for the wrong reason.
2. **[S] Fails the gather on any non-explicit upstream-probe failure.** Critic's §S.5: converts a hygiene probe into a global circuit breaker without a kill switch; one flaky `scip-typescript` run hard-fails the gather; portfolio-scale Phase 14 rescans ripple Stage 1 Assessment failures everywhere.
3. **[B] Advisory budget; dedicated dashboard; deliberately-seeded fixture; `--strict` CLI flag.** No critic attack on this directly, but the `--strict` flag is the only explicit failure-mode handle of the three.

The synthesis (`final-design.md §3.2 IndexHealthProbe`): combine [B]'s structural shape + [P]'s `cache_strategy = "none"` correctness + [S]'s rigorous per-domain formulas; reject [P]'s hard kill; reject [S]'s gather-fail circuit breaker; add a 200 ms advisory budget and a `--strict` CLI flag as the supported failure-loud path.

## Options considered

- **50 ms hard budget [P].** B2 auto-degrades to `low` whenever the budget fires; the probe lies on every gather where `git rev-list` slips; the seeded-staleness test cannot distinguish real low-confidence from budget-induced low-confidence.
- **Fail-the-gather on upstream failure [S].** B2 becomes a circuit breaker; gather is no longer resilient to single-probe failures (Phase 0/1 ADR'd "failure isolation: one probe's exception does not poison the rest"); CI gets noisy.
- **No budget, no failure policy [B initial].** B2 wall-clock grows silently; the most important probe becomes a tax on every gather; nothing fails when degradation happens.
- **Advisory budget + `--strict` CLI flag [synth].** Budget tracked as observability; failure surfaces via opt-in CLI gate; CI uses `--strict` against seeded fixtures; default `gather` exit-0 with a `confidence_summary` slice.

## Decision

**`IndexHealthProbe` budget is advisory (200 ms target, no hard kill); failure-mode is `--strict`-driven.**

- **Budget:** 200 ms p95 target. **No `asyncio.wait_for`.** If B2 exceeds 200 ms, the gather still completes; the slice emits `index_health.budget_exceeded: true` for observability. The dashboard tracks B2's wall-clock distribution.
- **Cache:** `cache_strategy = "none"`. B2 reads the post-sanitizer frozen peer-output snapshot (ADR-0001) on every gather. Recomputed always; cheap because it's pure-Python over peer outputs plus a single in-process `git rev-list --count` call.
- **Per-domain confidence.** B2 emits `index_health.<domain>.confidence ∈ {high, medium, low}` for each of: `scip`, `sbom`, `cve`, `semgrep`, `gitleaks`, `runtime_trace`. Each domain reads `last_indexed_commit`, `commits_behind`, `coverage_pct`, `tool_digest_in_use` from the peer-output snapshot.
- **`runtime_trace` reports `status: not_applicable`** (not `not_run`, not `low`) because C4 is deferred-by-design (ADR-0002); structurally distinguishable from "expected absence" vs "unexpected absence" (closes critic shared blind spot #2).
- **Never fails the gather.** B2's own failures (snapshot missing, `git rev-list` error) emit `index_health.<domain>.status: failed_upstream` per domain; gather continues; consumers see structured evidence of B2's own degradation.
- **`--strict` CLI flag.** `codegenie gather --strict` exits with code 3 if any `index_health.<domain>.confidence == "low"`. Default (`codegenie gather`) exits 0 with the `confidence_summary` slice surfacing the degradation.
- **CI uses `--strict` against the three seeded-staleness fixtures** (`stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`); `--strict` is the roadmap exit criterion's structural witness.
- **Bench regression gate.** A 25% mean-wall-clock regression on B2 across the bench fixtures fails the PR (advisory bench gate; not a runtime failure).
- **Single `git rev-list` invocation.** B2 issues exactly one subprocess in its entire `run()` — `git rev-list --count` — via Phase 0's allowlisted subprocess path. Default `gitpython` (in-process), fallback to subprocess if `gitpython` proves unreliable at portfolio scale (open question; see `final-design.md "Open questions"` #7).

## Tradeoffs

| Gain | Cost |
|---|---|
| B2 is honest — its own wall-clock degradation does not cause it to report `low` confidence falsely; the seeded-staleness signal is the only thing that produces `low` | Future probe authors who add a slow subprocess to B2 will see the dashboard alert but won't be hard-stopped; the 25% regression bench gate is the operational guardrail |
| Failure isolation (`localv2.md §3`) is preserved — one flaky peer probe doesn't hard-fail the gather; B2 records the upstream failure per domain | Operators reading the CLI exit code see "0" by default even when B2 reports `low`; they must check the `confidence_summary` slice or use `--strict` |
| `--strict` is the supported way for CI to fail-loud on `low` confidence — opt-in, explicit, scoped to the deployment | Adding `--strict` to the CLI introduces an exit-code mapping (3 = strict B2 low) the operator must know; documented in CLI help and integration test |
| Three seeded-staleness fixtures (SCIP, SBOM, semgrep rule-pack) exceed the roadmap "at least one" exit criterion — discipline scales | Maintaining three fixtures is more work than one; they collectively prove the architecture; each is in the adversarial corpus |
| `runtime_trace.status = not_applicable` (per ADR-0002) keeps the seeded-staleness signal high SNR — not_run noise doesn't drown the real signal | The `not_applicable` status is one more enum value; documented in the B2 sub-schema |
| B2 runs *last* in the dispatch order (`consumes_peer_outputs = True`; ADR-0001); peer outputs are frozen post-sanitizer | Adding any new B-or-later probe means deciding whether it's a peer of B2; documented in B2's `requires` declaration |
| Single `git rev-list` call keeps B2 cheap; `gitpython` in-process is the default — no per-gather subprocess overhead | `gitpython` reliability at portfolio scale is an open question (Phase 14 may switch to subprocess); the fallback is mechanical |

## Consequences

- `src/codegenie/probes/index_health.py` ships with the per-domain table, the frozen-snapshot consumption (via ADR-0001), and the single `git rev-list` call.
- `src/codegenie/schema/probes/index_health.schema.json` declares per-domain confidence enums + `budget_exceeded` + `status` enum.
- `src/codegenie/cli.py` ships the `--strict` flag; exit code 3 is documented in `--help`.
- `tests/integration/test_index_health_staleness_seeded.py` is the load-bearing test; three fixtures; each surfaces `confidence: low` on its specific domain.
- `tests/integration/test_strict_flag_fails_on_low_confidence.py` invokes `--strict` against seeded fixtures; asserts exit code 3.
- `tests/bench/test_index_health_budget.py` asserts B2 wall-clock ≤ 200 ms p99 across 1000 iterations on a populated peer-output snapshot; 25% regression fails the PR.
- B2 emits `confidence_summary` and `risk_flags` slices pre-shaped for Phase 8's hot-view projection — the projection is a dict-copy when Phase 8 lands.
- A future Phase 14 may revisit `gitpython` vs subprocess for portfolio-scale reliability; the fallback path is in-place.
- Phase 5's `RuntimeTraceProbe` landing flips B2's `runtime_trace` domain from `not_applicable` to an active status; B2's own code stays unchanged.

## Reversibility

**Medium.** Switching to a hard budget (the [P] option) requires implementation changes plus a re-design of the seeded-staleness test (the test would fail at false positives under hard kill). Switching to gather-failure on upstream-probe failure (the [S] option) requires implementation changes plus revisiting the failure-isolation invariant in Phase 0/1 ADRs. Adding more `--strict` exit codes (e.g., `--strict-sbom`) is mechanically additive. The 200 ms advisory threshold itself is configuration. The *failure-mode philosophy* — advisory by default, `--strict` for CI — is the load-bearing decision; reversing it would be re-litigating the whole D4/D5 conflict.

## Evidence / sources

- `../final-design.md "Components" §3.2 IndexHealthProbe (B2) — the honesty oracle`
- `../final-design.md "Conflict-resolution table" D4, D5` — the resolutions
- `../final-design.md "Departures from all three inputs" #3` — synth call-out
- `../final-design.md "Goals (concrete, measurable)"` `--strict` and IndexHealth-budget bullets
- `../final-design.md "Failure modes & recovery"` IndexHealthProbe budget row; `--strict` row
- `../phase-arch-design.md "Goals" #9, #11` — `--strict` and 200 ms target
- `../critique.md "Attacks on the performance-first design"` #3 — 50 ms hard budget unachievable
- `../critique.md "Attacks on the security-first design"` #5 — fail-the-gather rejected
- ADR-0001 — peer-output binding mechanism B2 uses
- ADR-0002 — runtime_trace `not_applicable` linkage
