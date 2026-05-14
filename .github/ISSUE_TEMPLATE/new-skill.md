---
name: New Skill
about: Propose a new Skill (YAML-frontmatter + body) for the Planner's catalog.
labels: ["skill", "phase-4-or-later"]
---

## Skill identity

- **Slug:** (kebab-case; matches the file name under `skills/`)
- **Task class:** (e.g. `vulnerability_remediation`, `distroless_migration`)
- **Trigger conditions:** what `RepoContext` evidence activates this Skill
- **Output shape:** what the Planner gets back (recipe path, patch, replacement-catalog entry, …)

## Why this is a Skill and not a probe / not a recipe

- **A probe** captures evidence. **A Skill** packages organizational knowledge the Planner queries at decision time.
- **A recipe** is a deterministic structural transform (e.g. OpenRewrite). **A Skill** may *select* or *parameterize* a recipe but should not embed one.
- If your contribution is fact-capture, file a `new-probe` issue instead.

## Body

- **YAML frontmatter keys:** (`name`, `task_class`, `triggers`, `outputs`, `confidence_floor`, `replaces:` if superseding an older Skill)
- **Body sections:** intent, decision rules, examples (positive + negative), known false positives, escalation rules

## Acceptance criteria

- [ ] Frontmatter validates against the Skill schema (Phase 4 lands the validator)
- [ ] Body cites at least one organizational artifact (exception registry, policy YAML, conventions catalog)
- [ ] Examples cover at least one positive trigger + one negative-space trigger (when NOT to fire)
- [ ] Tests assert the Planner queries this Skill with realistic `RepoContext` fixtures
- [ ] No PII, no proprietary code, no LLM-generated prose in the body without human review

## References

- `docs/production/design.md §"Organizational uniqueness as data, not prompts"`
- `docs/production/adrs/` — Skill catalog ADRs (when filed)
