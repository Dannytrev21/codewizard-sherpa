---
name: ADR amendment
about: Track an amendment to a numbered ADR (Nygard format). Use this when probe-contract drift or a production-design decision needs to evolve.
labels: ["adr", "design"]
---

## Which ADR is being amended

- **ADR number + title:** (e.g. `ADR-0007 — Probe contract frozen snapshot`)
- **ADR file path:** (e.g. `docs/production/adrs/0007-...` OR `docs/phases/<phase>/ADRs/0007-...`)
- **Current status:** Accepted / Superseded / Deprecated

## What changed (and why now)

Describe the new evidence, requirement, or constraint that motivates the amendment. Cite:

- The PR or runtime change that surfaced the need
- The probe contract snapshot diff (if any) — see `tests/snapshots/probe_contract.v1.json`
- The `docs/localv2.md §4` paragraph(s) affected (if any)

Per ADR-0007, **drift in the probe contract is resolved by changing code, never by editing the spec**. If the runtime drifted from the snapshot, the runtime is what regenerates the snapshot — but only after the amendment is approved.

## Proposed amendment

- **New decision text:** (replacement paragraph or diff)
- **New consequences:** (what new constraints land; what older constraints relax)
- **Status transition:** (Accepted → Superseded? → Deprecated?)
- **Successor ADR (if any):** (file path)

## Workflow

1. Open this issue first; do NOT open the PR until the amendment text is reviewed.
2. Once the text is agreed, open a follow-up PR using the repo's PR template at `templates/adr-amendment.md`. That PR:
   - Edits the ADR file in place (preserving the Nygard order: Context → Decision → Status → Consequences)
   - Regenerates `tests/snapshots/probe_contract.v1.json` via the documented regen script (if the contract changes)
   - Cross-links this issue
3. Reviewers from `.github/CODEOWNERS` are auto-requested.

## References

- `docs/production/adrs/` — production ADR folder (Nygard-format)
- `docs/localv2.md §4` — probe contract (the spec that must NOT be edited absent this workflow)
- `tests/snapshots/probe_contract.v1.json` — frozen snapshot regen target
- `templates/adr-amendment.md` — repo PR template used by the follow-up PR
- ADR-0007 — the policy this workflow honors
