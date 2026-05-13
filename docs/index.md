# codewizard-sherpa

Autonomous agentic system that opens PRs to modify code across repos at
portfolio scale. Task classes are introduced one at a time
(vulnerability remediation → distroless migrations → recipe authoring),
each extending the system by addition.

The first implementation milestone is **Phase 0 — bullet-tracer
foundations**: project skeleton, deterministic tooling, the `fence` CI job
that pins the gather pipeline as LLM-free.

## Where to start

- [Roadmap](roadmap.md) — the 17-phase plan from local POC to production
- [Production target](production/README.md) — canonical reference for the
  full Temporal-orchestrated service
- [Phase 0 overview](phases/00-bullet-tracer-foundations/README.md) — the
  current implementation milestone
- [Contributing](contributing.md) — placeholder until S5-02 lands

## Repo entry point

The repository-level `README.md` (not rendered into this site) covers
cloning, prerequisites, and the `make bootstrap` flow.
