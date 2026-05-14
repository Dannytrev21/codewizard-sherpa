---
name: New probe
about: Propose, scope, or track a new RepoContext probe (Layer A–G).
labels: ["probe", "phase-1"]
---

## Probe identity

- **Probe class name:**
- **Layer:** (A: language/build, B: deep static analysis, C: runtime trace, D: CI/deployment, E: dependency, F: security, G: cross-repo)
- **Applies to languages:** (e.g. `["javascript", "typescript"]` or `["*"]`)
- **Applies to task classes:** (e.g. `["vulnerability_remediation"]` or `["*"]`)

## Why this probe earns its slot

Probes capture **facts, not judgments**. Describe the evidence this probe will record on the `RepoContext` artifact and which Planner decision consumes that evidence. If you cannot name a downstream consumer, the probe is premature.

## Contract changes (if any)

This probe should NOT widen the probe contract in `src/codegenie/probes/base.py` or the snapshot `tests/snapshots/probe_contract.v1.json`. If it must, file an ADR amendment (see `.github/ISSUE_TEMPLATE/adr-amendment.md`) FIRST. Per ADR-0007, drift is resolved by changing code, never by editing the spec.

## Declared inputs

- **File globs:**
- **External tools:** (must be in the §6 `localv2.md` allowlist; new tools need an ADR)
- **Estimated runtime:** (cold / warm)

## Acceptance criteria

- [ ] Probe class registers via `@register_probe`
- [ ] `declared_inputs`, `applies_to_languages`, `applies_to_tasks` populated
- [ ] Output schema lives under `src/codegenie/schema/probes/`
- [ ] Unit test covers happy-path + at least one failure mode + confidence reporting
- [ ] Probe respects the cache key contract (no probe-internal mutable state)
- [ ] Probe contributes to `repo-context.yaml` via the existing writer (no new top-level keys without ADR)

## References

- `docs/localv2.md §4` — probe contract (do not edit; if drift is needed, see ADR amendment template)
- `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md` — Phase 0 probe lifecycle
- `docs/contributing.md` — "Adding a probe" cheat sheet (numbered recipe)
