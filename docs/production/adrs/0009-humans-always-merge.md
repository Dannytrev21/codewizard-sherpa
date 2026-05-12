# ADR-0009: Humans always merge — no autonomous merge to production

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** safety · governance
**Related:** ADR-0008, ADR-0014

## Context

The system can be designed to either propose pull requests (humans review and merge) or to merge autonomously (when all gates pass, the bot pushes to main). Autonomous merge is what the most ambitious agentic systems aspire to; it's also what the empirical research uniformly warns against.

The Copilot Agent Mode research (cited in `../../auto-agent-design.md §2.6`) found that fully autonomous migration is insufficient for production: dependency and environment issues are the main failure class, and human-in-the-loop plus runtime feedback close the gap. The Safer Builders / Risky Maintainers data shows agents fail at 6.72–9.35% during maintenance tasks. Trust gates catch the failures we know how to detect; agents fail in ways gates don't see (intent mismatch, semantic-but-not-functional correctness, hidden state changes like the SQLAlchemy autocommit example in `../../gemini-auto-agent-design.md`).

## Options considered

- **Fully autonomous merge.** When all objective gates pass, push to main. Maximum throughput; maximum risk of cascading silent failures across portfolio.
- **Human merge required for everything.** Every PR requires a CODEOWNERS approval before merging. Standard human-in-the-loop.
- **Tiered: autonomous for low-risk task classes, human for high-risk.** Plausible but how do you define "low-risk" before you've shipped? The system that decides "this class is low-risk" is the same system we don't fully trust.

## Decision

**Humans always merge.** Autonomy ends at PR creation. The system can plan, execute, validate, and propose — it cannot merge. Branch protection rules in the target repos enforce this at the GitHub/GitLab level so even a misconfigured bot cannot bypass.

## Tradeoffs

| Gain | Cost |
|---|---|
| Catastrophic miss-cases require human accomplice to land in production | Throughput is capped at reviewer attention bandwidth |
| Engineers stay in the loop for the decisions that matter — they read evidence bundles | Reviewer fatigue is real; the system must produce *good* evidence bundles to be reviewable |
| Compliance and audit are clean — every prod change has a named human approver | Slow merge feedback loop for the agent — Stage 7 Learning may wait days |
| Reverses on a single ADR-update; no infrastructure debt to undo | Some classes of "obvious" change (e.g., automated dep-bot bumps) still need human eyes |

## Consequences

- Stage 6 Handoff (`../design.md §3` Stage 6) is the final stage of every workflow; Temporal pauses on a `pull_request.closed` webhook signal that arrives only after a human merges.
- The PR evidence bundle (CVE delta, validator outputs, runtime trace diff, link to sandbox build artifacts) is treated as a first-class output. The bundle is what makes the human-in-the-loop step tractable rather than a bottleneck.
- The bot account that opens PRs has narrow GitHub scopes: read repo, open branch, open PR, comment on PR. It cannot merge, force-push, or modify branch protection.
- Branch protection rules in target repos enforce: required reviewers, no force-push, no admin override without a second approver.
- Throughput planning: assume reviewer capacity is the bottleneck. Plan for 1 reviewer per ~20 PRs/day per familiar repo, lower for unfamiliar.

## Reversibility

**Low cost to relax** in narrow ways once production evidence justifies it (e.g., autonomous merge for "version bumps to packages with no transitive deps changed"). **High cost / dangerous** to relax broadly — would require reverting branch protection, expanding bot scopes, and accepting catastrophic-miss risk. Treat the default as permanent; treat narrow exceptions as ADR-amendable.

## Evidence / sources

- `../design.md §2.8` (load-bearing commitment)
- `../design.md §3` (Stage 6 description)
- `../design.md §4.5` (both worked scenarios end at PR creation)
- `../../auto-agent-design.md §2.6` — Copilot Agent Mode research on autonomous-migration failure modes
- `../../gemini-auto-agent-design.md` — Confidence Trap, Safer Builders / Risky Maintainers, SQLAlchemy autocommit case
- Konveyor Kai precedent — human-in-the-loop at execution
