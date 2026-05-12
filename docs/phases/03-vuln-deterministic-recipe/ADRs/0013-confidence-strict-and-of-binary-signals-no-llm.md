# ADR-0013: Phase-3 confidence is the strict-AND of binary objective signals; no LLM and no human-merge in this phase

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** confidence · trust-score · facts-not-judgments · human-handoff · phase-3-floor
**Related:** ADR-0001, ADR-0005, ADR-0008, [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

Production ADR-0008 commits the trust score to **objective signals only** — no LLM self-reported confidence. The three competing Phase 3 designs each named a signal set; the synthesis consolidates the union (`final-design.md §"Trust & safety goals"` #16):

> Confidence is the strict-AND of objective signals per ADR-0008. Signal set: `lockfile.parse_ok`, `lockfile.policy_violation_count == 0`, `recipe.engine.exit_status == 0`, `npm.install.exit_status == 0`, `npm.install.disallowed_egress_bytes == 0`, `tests.exit_status == 0`, `tests.duration_vs_baseline_pct ≤ 200`, `cve.delta.direction ≤ 0`, `patch.git_apply_dryrun_ok`. Any false → `confidence: low`.

Two adjacent commitments fall out of this and warrant the same ADR:

1. **No LLM anywhere in Phase 3** — `production ADR-0005`'s "no LLM in gather pipeline" extends to `transforms/` and `recipes/`. The Phase 0 fence CI matrix extends to these packages.
2. **Human handoff is at the local-branch boundary** — `production ADR-0009`'s "humans always merge" applies; Phase 3 stops at a local branch plus an evidence bundle, never pushes, never opens a PR.

This ADR consolidates the confidence model, the no-LLM extension, and the human-handoff fidelity into one decision record because they are the same architectural posture viewed from three angles.

## Options considered

- **Confidence as a continuous score [naive].** Allows soft thresholds; defeats `production/design.md §2.3` (honest confidence). Phase 4 LLM router cannot route deterministically.
- **Confidence as LLM self-report [rejected by production ADR-0008].** Excluded by production decision.
- **Confidence as strict-AND of binary objective signals; any false → `low` [synth, follows production ADR-0008].** Simple, auditable, reproducible. Phase 4 reads the per-signal evidence to route.

For LLM scope:

- **Allow LLM in Phase 3 selector for fuzzy advisory-to-recipe matching.** Defeats "deterministic recipe path" — the Phase 3 name. Rejected.
- **Fence `transforms/` and `recipes/` from importing LLM SDKs, mirroring Phase 0's fence on `probes/`.** Aligns with `production ADR-0005`.

For human handoff:

- **Push branch + open PR in Phase 3.** Violates `production ADR-0009`; Phase 11's job.
- **Stop at local branch + evidence bundle; surface escalations prominently [synth].** Matches Phase 3 scope (`roadmap.md §"Phase 3"`: "writes the diff plus a local branch ... Single-repo, local, deterministic").

## Decision

**Phase 3's confidence model is the strict-AND of nine binary objective signals:**

```python
def trust_score(signals: dict[str, bool]) -> Literal["high", "low"]:
    required = [
        "lockfile.parse_ok",
        "lockfile.policy_violation_count_zero",
        "recipe.engine.exit_status_zero",
        "npm.install.exit_status_zero",
        "npm.install.disallowed_egress_bytes_zero",
        "tests.exit_status_zero",
        "tests.duration_vs_baseline_within_200pct",
        "cve.delta.direction_non_increasing",
        "patch.git_apply_dryrun_ok",
    ]
    return "high" if all(signals.get(s, False) for s in required) else "low"
```

- The `medium` tier exists only as the **signal-escalate** signal (ADR-0005) — when the test gate cannot satisfy itself because the test environment fundamentally cannot satisfy the gate (`requires_network=true`). The orchestrator emits `confidence="medium"` + `gate.signal_escalate` and exits 8.
- `signals` are populated from `ValidatorOutput.passed` (per-validator) and per-event audit fields (per-event objective signal).
- The signal set is **closed at v0.3.0**; adding a signal requires an ADR amendment.

**LLM fence extends to Phase 3:**

- Phase 0 fence CI matrix extends to `src/codegenie/transforms/` and `src/codegenie/recipes/`.
- These packages may NOT import `anthropic`, `openai`, `langgraph`, `chromadb`, `sentence-transformers`, or any LLM-related SDK.
- CI fence test asserts.
- Tokens-per-run for Phase 3: **0**.

**Human handoff at local-branch boundary:**

- Phase 3 stops at:
  - `.codegenie/remediation/<run-id>/remediation-report.yaml` (indexing artifact per `production/design.md §2.7`)
  - `.codegenie/remediation/<run-id>/diff/<recipe-id>.patch`
  - `.codegenie/remediation/<run-id>/raw/{ncu.json, install.log, test.xml, ...}`
  - `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` (BLAKE3-chained, ADR-0010)
  - A local branch named `codegenie/vuln-fix/<cve-id>-<short-sha>`.
- **No `git push`.** **No GitHub API.** **No PR creation.** **No remote interaction except `codegenie cve sync` (ADR-0008).**
- `production ADR-0009` ("humans always merge") fidelity: the human reviewer reads the evidence bundle, decides to merge, applies the patch.
- Escalation surface (ADR-0005, `phase-arch-design.md §"Gap 3"`): on `signal_escalate` exit (8), CLI prints a stderr banner; `escalations/<utc>.json` is written; `remediation-report.yaml` includes `escalations: [...]`. The local POC has no automated human-routing layer; operators read the artifacts.

## Tradeoffs

| Gain | Cost |
|---|---|
| Strict-AND model is auditable, reproducible, deterministic — same input signals always produce the same confidence tier | Continuous-score advocates lose the ability to weight signals; the closed-enum signal set must be revised by ADR amendment when a new objective signal is identified |
| `confidence="medium"` exists only as the signal-escalate signal — the model has three legitimate tiers but two are produced by orthogonal paths; no soft thresholds | The two-tier-plus-escalate shape is unusual; the producer must understand that "medium" never comes from signal aggregation |
| Phase 0 fence CI extension to `transforms/` and `recipes/` is mechanically additive — no edits to Phase 0 code | Future contributors who want to "just add a small LLM call for selector fuzziness" hit a CI fence and must surface an ADR to change the posture |
| Tokens-per-run = 0 is a structural property, not a budgeting target — `production ADR-0024` cost-observability shows zero by construction | Phase 4 lands the LLM; the "no LLM in Phase 3" posture is hard-won and easily eroded — discipline required at code review |
| Human handoff at local-branch boundary aligns Phase 3 with `production ADR-0009`; Phase 11's PR-opening is purely additive | The local POC has no human routing; on `signal_escalate`, the operator manually reads the artifacts; mitigated by stderr banner + `escalations/` JSON files |
| Escalation surface is *prominent* (exit code 8, stderr banner, JSON event, report section) — operator cannot miss it | Operators who run `codegenie remediate` in scripts must check the exit code; documented in the runbook |
| The `cve.delta.direction_non_increasing` signal makes "after-the-fix has fewer or equal CVEs than before" a hard contract — silent regressions cannot pass | Computing the delta requires re-running the CVE probe post-transform; cost is small but measurable; documented in performance budgets |

## Consequences

- `src/codegenie/transforms/validation/trust_score.py` implements the strict-AND function and the signal-set enum.
- `src/codegenie/transforms/coordinator.py` populates the signal dict at each stage and calls `trust_score` at Stage 7.
- Phase 0's fence CI extends to `transforms/` and `recipes/` packages.
- `tests/property/test_trust_score_strict_and.py` asserts the strict-AND property under Hypothesis.
- `tests/integration/test_fence_no_llm_in_transforms.py` asserts no LLM SDKs importable from the Phase 3 packages.
- `tests/integration/test_no_git_push_in_phase_3.py` asserts the orchestrator never invokes `git push`.
- `tests/integration/test_no_github_api_in_phase_3.py` asserts no calls to `api.github.com` from `transforms/` or `recipes/`.
- `remediation-report.yaml` schema includes `confidence: Literal["high","low"]`, `escalations: list[...]`, `signals: dict[str, bool]`.
- Phase 4's LLM landing lives in a separate package (likely `src/codegenie/planning/`); Phase 4 ADRs document the LLM scope.
- Phase 11's PR opening is a separate phase deliverable; `production ADR-0009` governs.

## Reversibility

**Low.** Adding LLM to Phase 3 (e.g., for selector fuzziness) requires (a) reversing the fence, (b) adding an LLM SDK import, (c) handling determinism and reproducibility for the new code path, (d) re-architecting the confidence model to handle non-objective signals — all of which would surface as an ADR amendment that effectively rewrites Phase 3. Adding a `git push` to Phase 3 violates `production ADR-0009`; high cost to reverse because Phase 11 is structured around it. Tweaking the signal set (adding/removing one signal) is mechanically low cost but each change must be coordinated with Phase 4's router (which reads the signals for diagnostic context). The three-piece commitment (strict-AND + no-LLM + local-branch handoff) is the load-bearing architectural posture.

## Evidence / sources

- `../final-design.md §"Goals" §"Trust & safety goals"` #16 — strict-AND signal set
- `../final-design.md §"Goals" §"Cost & latency goals"` #6 — tokens-per-run = 0
- `../final-design.md §"Components" #12 "TrustScorer"` (per phase-arch-design)
- `../final-design.md §"Load-bearing commitments check (§2 of production/design.md)"` §2.1 (no LLM), §2.2 (facts), §2.3 (honest confidence), §2.8 (humans always merge)
- `../final-design.md §"Exit-criteria checklist"` "No LLM in this loop. Single-repo, local, deterministic."
- `../phase-arch-design.md §"Component design" #12 "TrustScorer"`
- `../phase-arch-design.md §"Goals" §"Cost & latency"` #6
- `../critique.md §"Roadmap-level critiques" §3 "Does it violate any load-bearing commitment"` §2.4
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — no LLM in gather (extends here)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — objective-signal trust score
- [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) — human merge boundary
