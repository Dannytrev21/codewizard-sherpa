# ADR-0028: Task class introduction order — vulnerability remediation before migration

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** task-class · sequencing · scope
**Related:** ADR-0010, ADR-0011, ADR-0026

## Context

The system targets multiple task classes — vulnerability remediation, Chainguard distroless migration, dependency upgrades, language migrations, etc. The order in which they are introduced into the system has real consequences: each new task class is intended to extend the system by **addition** (extension-by-addition is a load-bearing commitment in `CLAUDE.md`), so the *first* task class shapes the contract surface that all subsequent classes must extend. Get the first one wrong and the second class forces edits to Phase 0–6 code, breaking the invariant.

The original framing put Chainguard distroless migration first. After the production design and the phased roadmap were built out, that ordering was revised — vulnerability remediation first, migration second, agentic recipe authoring third. This ADR records the decision and the reasoning so it doesn't drift back.

## Options considered

- **Migration first.** Higher-visibility outcome (a concrete container image swap that demos well); CVE-driven work waits in the queue.
- **Vulnerability remediation first.** Highest-frequency, smallest-blast-radius transforms (a single package bump); cost-per-CVE-eliminated (ADR-0026) becomes measurable immediately; the contract surface is exercised against the statistically most common case first.
- **Both in parallel.** Move faster early; but the contract surface gets shaped by two simultaneous demands — high risk of accidental coupling between task classes that should remain independent.

## Decision

**Vulnerability remediation is introduced first** (roadmap Phase 3). **Chainguard distroless migration is introduced second** (roadmap Phase 7), and the introduction is itself the test that the probe / skill / recipe contracts extend without editing Phase 0–6 code. **Agentic recipe authoring is introduced third** (roadmap Phase 15), once enough solved examples exist to make the compounding-savings story real.

## Tradeoffs

| Gain | Cost |
|---|---|
| Vuln remediation has the highest frequency in any portfolio — the system delivers value continuously instead of in big-bang migration batches | Distroless migration delivers more dramatic single-incident value; deferring it means leadership demos rely on cumulative CVE numbers rather than a "we migrated 50 services" headline |
| Cost-per-CVE-eliminated (ADR-0026 headline ratio) becomes measurable at Phase 3, not Phase 7 — the ROI story lands earlier | The first migration PR isn't until Phase 7, so portfolio-shaped work is gated longer |
| The contract surface is shaped by the highest-frequency case first, which is statistically the right thing to optimize for | When migration is added at Phase 7, anything in the contract that turned out to be too vuln-specific surfaces as a refactor demand |
| Phase 7 doubles as an extension-by-addition test — if adding the second class requires edits to Phase 0–6 code, the contract was wrong and we fix it immediately, while the system is still small | One full task class worth of design lives behind a "we'll verify when we add the second class" gate |

## Consequences

- The roadmap's Phase 3 is the first phase that ships a real transform, and it ships against vuln remediation, not migration.
- Phase 7's exit criterion includes a non-trivial assertion: the diff for that phase touches *only* new files. No Phase 0–6 source code is modified. If that assertion fails, the contract is wrong and the fix is to refactor the contract — never to "just edit one Phase 0–6 line because it's easier."
- Cost-per-CVE-eliminated (ADR-0026) carries the early ROI narrative; cost-per-merged-PR is meaningful from Phase 3 onward.
- Any future task class (Python migrations, Java migrations, dependency-major upgrades) follows the same extension-by-addition pattern proven by Phase 7.
- This ordering also implies the *third* task class — agentic recipe authoring — is something the system grows into rather than ships with. Until enough solved examples accumulate (the Stage 7 Learning loop feeds this), recipe authoring would just be writing recipes by hand under a fancier name.

## Reversibility

**Medium.** Reordering after Phase 3 ships is expensive — the contract surface is shaped by whatever class lands first, and migrating that shape to a new center of gravity means refactoring the probe + skill + recipe contracts. Reversing *before* Phase 3 ships is cheap (text only). After Phase 7 (extension-by-addition proven), the order no longer matters — the contract is stable in both directions.

## Evidence / sources

- `../design.md §2` (load-bearing commitments — extension by addition)
- `../../roadmap.md` (the full phased plan)
- ADR-0010 (seven-stage pipeline shape — the stages every task class flows through)
- ADR-0011 (recipe-first → RAG → LLM-fallback — the per-task-class decision chain)
- ADR-0026 (ROI KPI model — cost-per-CVE-eliminated is one of the two headline ratios)
