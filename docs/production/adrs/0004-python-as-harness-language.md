# ADR-0004: Python as the harness language across POC and service

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** language · ecosystem
**Related:** ADR-0003, ADR-0007

## Context

The harness language determines which libraries can be called in-process, which agent ecosystems the code can plug into, which engineers can contribute, and how much subprocess overhead the system pays. The decision is sticky — once a service has 5K lines of orchestrator code in language X, switching to language Y has 6-figure engineering cost.

The local POC ([`../../localv2.md`](../../localv2.md)) is already in Python. The decision is whether to keep Python at service-lift time or rewrite.

## Options considered

- **Python.** Native bindings for tree-sitter, jsonschema, tantivy, Anthropic SDK, OpenAI SDK, semgrep, CodeQL CLI wrappers. Mature Temporal SDK. Largest agent/LLM library ecosystem in 2026.
- **TypeScript.** Could embed the TS compiler API directly instead of shelling to scip-typescript. Better at long-running concurrent IO. Splits the codebase the moment we need CodeQL/Joern/semgrep (all Python-ecosystem).
- **Go.** Where Chainguard's own tooling lives (`dfc`, `incert`, `chainctl`, `syft`, `grype`, `trivy`). Best concurrency story. Weakest agent/LLM library ecosystem.
- **Rust.** Best performance, smallest binary footprint. Iteration speed is wrong for a probe-heavy POC where we tune catalog YAML weekly.
- **Split-language.** Python for orchestrator, Go for hot-path CLIs. Real option, deferred — see below.

## Decision

**Python 3.11+ across both POC and service.** Reserve the right to write occasional Go or Rust binaries for hot-path tools and subprocess to them from Python (Chainguard tooling already follows this shape).

## Tradeoffs

| Gain | Cost |
|---|---|
| Native access to the agent/LLM library ecosystem (Anthropic SDK, LangGraph, etc.) | Cold-start latency higher than Go/Rust (mitigated: Temporal workers are long-running) |
| Probe authors already know Python | Type discipline at scale requires investment (pyright strict + Pydantic at boundaries) |
| Most published autonomous-migration prior art (Konveyor Kai, DeepMind CodeMender) is Python — reference architectures translate directly | GIL constrains CPU-bound parallelism (mitigated: probes subprocess to external tools) |
| Tree-sitter, semgrep, CodeQL, jsonschema, tantivy all have first-class Python bindings | Dependency management requires discipline — adopt `uv`, not pip |
| Single language across POC and service — probe contract lifts unchanged (ADR-0007) | Engineers wanting Go would have to write subprocess binaries |

## Consequences

- The toolchain becomes: Python 3.11+, `uv` for dependencies, `pyright --strict` in CI, Pydantic for data models, `ruff` for lint.
- CPU-bound work (SCIP indexing, AST parsing) always goes through subprocess to a dedicated tool — never tight loops inside Python.
- Chainguard tooling (`dfc`, `incert`) and security tools (`syft`, `grype`, `trivy`) are invoked via subprocess. Go's parallel scheduler handles their internal concurrency.
- Anthropic and OpenAI SDKs are first-class; ADR-0020 evaluates which to use at leaf nodes.

## Reversibility

**High cost.** Switching languages mid-project would require rewriting probes, orchestrator, gate runners, and Activity bindings. Realistically a permanent decision unless a forcing function appears (e.g., a deal-breaking performance ceiling).

## Evidence / sources

- `../design.md §1` (project shape)
- `../../localv2.md §6` (tool dependencies — almost all CLIs, accessed via subprocess)
- Konveyor Kai source (Python; Red Hat's reference implementation of similar architecture)
- DeepMind CodeMender — Python-shaped
- Anthropic SDK ecosystem coverage in 2026
- `uv` adoption as the modern Python dependency manager
