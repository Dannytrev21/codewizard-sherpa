# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repo is **design-only**. No code, no build, no tests yet. All substantive content lives in `docs/`. The phased plan from local POC to production lives in [docs/roadmap.md](docs/roadmap.md); the first implementation milestone is Phase 0 of that roadmap, which corresponds to the Week 1 skeleton in [docs/localv2.md](docs/localv2.md) §12.

## What this project is

**codewizard-sherpa** is an autonomous agentic system that opens PRs to modify code across repos at portfolio scale. Task classes are introduced one at a time (see [docs/roadmap.md](docs/roadmap.md)): **vulnerability remediation** first (roadmap Phase 3), then **Chainguard distroless container migrations** (Phase 7), then **agentic recipe authoring** itself (Phase 15) — each new task class extending the system by *addition*, never by editing existing components. The full service is a 7-stage Temporal-orchestrated pipeline (Discovery → Assessment → Deep Scan → Planning → Execution → Validation → Handoff → Learning); the immediate work is a local Python CLI POC implementing only the context-gathering layer.

## Reading order for the design docs

Not all docs are equal. Read in this order and skip the redundant ones:

1. **[docs/production/](docs/production/)** — **canonical production-target reference folder**. Start at [docs/production/README.md](docs/production/README.md) for the entry point. Inside: [`design.md`](docs/production/design.md) defines the Layered Hybrid Architecture (Temporal envelope → Hierarchical Planner → SHERPA-style state machine → Trust-Aware gates → leaf LLM calls), the 7-stage pipeline, agent personas, the continuous-gather model, and the 4+1 architectural views; [`adrs/`](docs/production/adrs/) holds one Architecture Decision Record per major design choice (numbered, Nygard-style) capturing the *why* behind every decision. Synthesizes the three service-shaped docs (context.md, auto-agent-design.md, gemini-auto-agent-design.md) — read this folder first; consult the others as background.
2. **[docs/localv2.md](docs/localv2.md)** — **canonical local POC spec**. Supersedes `local.md`. Defines the Python CLI (`codegenie gather`), probe contract, probe inventory (Layers A–G), `RepoContext` schema, caching, output format, 6-week implementation plan (§12), tool dependencies (§6), and config (§13). The probe contract is forward-compatible with the service; bugs here propagate.
3. **[docs/context.md](docs/context.md)** — service-shaped design for the gather layer specifically. Read for the MCP query interface and cross-repo SCIP detail.
4. **[docs/auto-agent-design.md](docs/auto-agent-design.md)** — the original 7-stage service pipeline writeup. Read for stage-by-stage detail (Konveyor Kai prior art, recipe-first/LLM-fallback planning, Temporal rationale).
5. **[docs/gemini-auto-agent-design.md](docs/gemini-auto-agent-design.md)** — alternate (Gemini-authored) take. Heavier on AgentOps, deterministic policy engines (Agent RuleZ), LST/AST manipulation, the "Confidence Trap" and "Safer Builders, Risky Maintainers" empirical findings. Useful background; not the source of truth.
6. **[docs/local.md](docs/local.md)** — superseded by `localv2.md`. Skip unless diffing v1 vs v2.

## Load-bearing architectural commitments

These appear across every doc and constrain implementation. Do not violate without surfacing the tradeoff:

- **No LLM anywhere in the gather pipeline.** Not for probe logic, not for merging slices, not for summarizing external docs. The gatherer is deterministic end-to-end. This is what makes `RepoContext` reproducible, cacheable, and auditable.
- **Facts, not judgments.** Probes capture evidence ("trace observed 0 shell invocations"). They do not write conclusions ("safe to migrate"). Conclusions are the Planner's job. Evidence is reusable across tasks; judgments aren't.
- **Honest confidence.** Every probe reports its confidence and provenance. `IndexHealthProbe` (B2) is called out as the single most important probe because silent index staleness is the worst failure mode.
- **Determinism over probabilism for structural changes.** The empirical finding driving the whole architecture: AI agents are "safer builders, risky maintainers" — they break things during refactors at much higher rates than during net-new code. Use recipes (OpenRewrite) and AST/LST manipulation for structural transforms; reserve the LLM for judgment calls only. See `gemini-auto-agent-design.md` §"Architecting Determinism within Probabilistic Systems".
- **Extension by addition.** Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator. The probe contract in `localv2.md` §4 is the contract.
- **Organizational uniqueness as data, not prompts.** Skills with YAML frontmatter, conventions catalogs, policy YAML, replacement catalogs, exception registries. The Planner queries structured data; it never has to infer your company's rules from prose.
- **Progressive disclosure for context.** The `RepoContext` artifact indexes evidence; it doesn't inline it. Skills, ADRs, repo notes, and external docs are referenced by path/manifest only. The Planner reads originals at decision time. This is what keeps the agent's token budget tractable.
- **Humans always merge.** Autonomy ends at PR creation. This is the consistent finding from every published autonomous-migration study cited in the docs.

## Implementation entry point

Per `localv2.md` §12, Week 1 lands:

- CLI scaffolding (Python 3.11+, `click`, entry point `codegenie gather`)
- Probe contract + registry (see `localv2.md` §4 — copy the ABC verbatim; it's the same contract the service will use)
- Coordinator (asyncio, bounded worker pool, per-probe timeout, failure isolation)
- Cache layer (filesystem-backed, content-addressed under `.codegenie/cache/`)
- JSON Schema for `RepoContext` + validation via `jsonschema`
- Layer A probes only: `LanguageDetection`, `NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`
- Output writer that produces `.codegenie/context/repo-context.yaml` + raw artifacts dir

Required external tools at runtime are listed in `localv2.md` §6. The CLI is expected to check `$PATH` at startup and print clear install errors.

## Conventions to follow when writing the POC

- **Single Python project**, no services, no databases. Filesystem-backed everything.
- **YAML for the human-facing artifact** (`repo-context.yaml`), **JSON for raw probe outputs** under `.codegenie/context/raw/`.
- **Probes register via decorator** (`@register_probe`) so adding one never requires editing a central list.
- **Each probe declares `declared_inputs`** — globs of files or external resource fingerprints. Cache keys derive from this; incremental gathers depend on it.
- **Each probe declares `applies_to_tasks` and `applies_to_languages`** with `["*"]` meaning "all".
- **`.codegenie/`** is the on-disk output namespace inside any analyzed repo. The tool should offer to add it to that repo's `.gitignore` on first run.

## Global rules (also in `~/.claude/CLAUDE.md`)

This user maintains a 12-rule global instruction set covering things like "Think Before Coding", "Simplicity First", "Surgical Changes", "Goal-Driven Execution", "Match the codebase's conventions", and "Fail loud". Those rules apply here; this file does not restate them.
