# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state (2026-05)

**Phases 0–2 of the roadmap are largely shipped.** This is no longer a design-only repo: there is a working Python package (`src/codegenie/`), a CLI (`codegenie gather`), ~2,300 unit + integration + adversarial tests, mkdocs site, pre-commit firewall, CI matrix, and a published [docs site](https://dannytrev21.github.io/codewizard-sherpa/).

- **Phase 0** (bullet-tracer foundations) — Done.
- **Phase 1** (Layer A Node probes — `LanguageDetection`, `NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`) — Done.
- **Phase 2** (Layer B–G probes) — Most stories shipped (S4-01..S4-07, S5-01..S5-02 GREEN; S5-03..S6-08 in flight via the autonomous executor pipeline).
- **Phases 3, 5, 6.5** — Designed (final-design + arch + ADRs + stories) but not implemented.

The story-driven autonomous-execution pipeline (`/phase-story-writer`, `/phase-story-validator`, `/phase-story-executor`) is the canonical way new work lands. Story files under `docs/phases/{phase}/stories/` carry their own status (`Ready` / `HARDENED` / `GREEN` / `Done` / `BLOCKED`).

## What this project is

**codewizard-sherpa** is an autonomous agentic system that opens PRs to modify code across repos at portfolio scale. Task classes are introduced one at a time: **vulnerability remediation** first (Phase 3), then **Chainguard distroless container migrations** (Phase 7), then **agentic recipe authoring** itself (Phase 15) — each extending the system by *addition*, never by editing existing components.

The full service is a 7-stage Temporal-orchestrated pipeline (Discovery → Assessment → Deep Scan → Planning → Execution → Validation → Handoff → Learning). The current implementation is the **context-gathering layer only** — the `codegenie gather` CLI that produces a deterministic `RepoContext` artifact every later stage will consume.

## Common commands

The `Makefile` is the imperative surface; `pyproject.toml` + `uv.lock` are the source of truth for deps.

```bash
make bootstrap        # uv pip install -e ".[dev]"  (falls back to plain pip)
make check            # lint → typecheck → test → fence  (the full local gate)
make lint             # ruff check + ruff format --check
make lint-imports     # import-linter (structural cold-start defense; ADR-0002)
make typecheck        # mypy --strict src/
make test             # pytest -q  (excludes -m bench by default)
make docs             # mkdocs build --strict
make fence            # pytest -q tests/unit/test_pyproject_fence.py  (ADR-0002)
make clean

# CLI surface
python -m codegenie --help
python -m codegenie gather ./path/to/repo
python -m codegenie audit verify --runs-dir .codegenie/context/runs --cache-dir .codegenie/cache --yaml-path .codegenie/context/repo-context.yaml

# Running a single test / test file / test module
.venv/bin/pytest tests/unit/probes/layer_b/test_node_reflection.py -v
.venv/bin/pytest tests/unit/probes/layer_b/test_node_reflection.py::test_eval_usage_detected -v
.venv/bin/pytest -k "decorator" -v

# Pre-commit (mirrors most of `make check` at commit time; SHA-pinned hooks)
pre-commit install
pre-commit run --all-files
```

**Important pytest config (`pyproject.toml § [tool.pytest.ini_options]`):**
- `asyncio_mode = "auto"` — coroutine tests run without `@pytest.mark.asyncio`.
- `addopts` includes `--cov-fail-under=85`; running a narrow subset can falsely fail the coverage gate. Use `--no-cov` for ad-hoc subset runs.
- Markers: `bench` (advisory perf, excluded by default), `adv` (Phase 1 adversarial), `phase02_adv` (Phase 2 adversarial; CI-gating).

CI runs across Python 3.11 / 3.12 × `ubuntu-24.04` and reproduces `make check`. The `fence` job is load-bearing (ADR-0002 / production-ADR-0005 — no LLM SDK in the gather-pipeline runtime closure).

## Architecture — the big picture

The whole thing is a **deterministic pipeline**: there is no LLM anywhere in `codegenie/`. The runtime closure is locked by `tests/unit/test_pyproject_fence.py` (`FORBIDDEN_LLM_SDKS` = `{anthropic, langgraph, openai, langchain, transformers}`) and structurally enforced by `import-linter` in `make lint-imports`. Editing this without an ADR amendment is a build break.

### Probe contract — the load-bearing abstraction

Every probe implements the frozen ABC at `src/codegenie/probes/base.py`. Bytes-for-bytes pinned to `docs/localv2.md §4` by `tests/unit/test_probe_contract.py`:

```python
class Probe(ABC):
    name: str
    layer: Literal["A", "B", "C", "D", "E", "F", "G"]
    tier: Literal["base", "task_specific"]
    applies_to_tasks: list[str]                # ["*"] = all
    applies_to_languages: list[str]            # ["*"] = all
    requires: list[str]                        # other probe names
    declared_inputs: list[str]                 # globs / special tokens — drives cache key
    timeout_seconds: int = 300
    cache_strategy: Literal["content", "none"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput: ...
```

**This contract is forward-compatible with the production service** (production ADR-0007). Phase 0 ADR-0007 *freezes* it — extension is by addition of new probes, never edits to the ABC. Two-arg `run(self, repo, ctx)` is the only signature; a one-arg `run` is a `TypeError` at dispatch.

`ProbeContext` carries `cache_dir`, `output_dir`, `workspace`, `logger`, and a small set of optional capabilities admitted by ADR amendment only: `parsed_manifest` (Phase 1 ADR-0002 — `package.json` memo), `input_snapshot` (Phase 1 fingerprint cache), `image_digest_resolver` (Phase 2 ADR-0004).

### Registry-dispatched coordinator

- `src/codegenie/probes/registry.py` is the kernel: `@register_probe` (defaults) or `@register_probe(heaviness="medium", runs_last=True)` (Phase 2 ADR-0003).
- `src/codegenie/probes/__init__.py` is the **explicit-import** collection point — no `importlib.metadata` entry-point scan (supply-chain + cold-start hygiene). Adding a probe = new module + one additive import line.
- `src/codegenie/coordinator/coordinator.py` reads the registry, partitions into prelude (tier=`base`) and rest waves, dispatches under a single bounded `asyncio.Semaphore`, applies failure isolation per probe, and emits the canonical `coordinator.dispatch.order` audit event. No `pytest-xdist`; no internal `ThreadPoolExecutor` inside probes (hidden parallelism lies to the coordinator's budget — Phase 2 ADR-0003).
- `src/codegenie/cache/` is content-addressed off `declared_inputs`; keys are derived in `cache/keys.py`. `cache_strategy="none"` opts a probe out (`IndexHealthProbe` does this — it observes a moving fact).

### Open/Closed seams

The codebase prefers data-driven registries over branching code. Established seams to mirror when extending:

- `@register_probe` (probe collection).
- `@register_index_freshness_check(IndexName)` (`codegenie.indices.freshness` — B2's per-index freshness logic; Phase 2 ADR-0006 sum-type discipline).
- `@register_dep_graph_strategy(PackageManager)` (`codegenie.depgraph` — per-ecosystem strategies; Phase 3 fills it).
- Module-level `Final` tuples / dicts for marker catalogs (`_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, `_LOCKFILE_PRECEDENCE` — iterated, never branched on).
- The grammar kernel (`codegenie.grammars.lock.language_for(name) -> tree_sitter.Language`) — adding Phase 8+ Python / Java grammars is one row in `_DISPATCH` + one PyPI wheel in `pyproject.toml` (02-ADR-0011).

### Subprocess discipline

All external tool invocations go through `codegenie.exec.run_allowlisted` (Phase 0) or `codegenie.exec.run_external_cli` (Phase 2 wrapper). The allowlist (`ALLOWED_BINARIES`) is a closed frozenset; adding a binary requires an ADR amendment (Phase 2 ADR-0001 is the omnibus). The `forbidden-patterns` pre-commit hook bans `subprocess.run(..., shell=True)`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, and `pickle.loads` repo-wide.

### Sanitizer + writer

`ProbeOutput.schema_slice` flows through a two-pass sanitizer (`codegenie.output.sanitizer`) before reaching disk:
1. Schema validation via Pydantic (ADR-0010).
2. Absolute-path scrubbing + secret-shaped-field rejection (ADR-0008 + Phase 2 ADR-0005 + Phase 2 ADR-0010 — `RedactedSlice` smart constructor).

Output writer produces `.codegenie/context/repo-context.yaml` (human-facing YAML) + `.codegenie/context/raw/*.json` (machine-readable raw probe outputs that downstream probes like B2 read). Audit anchors land in `.codegenie/context/runs/*.json`.

### `RepoContext` envelope + per-probe sub-schemas

JSON Schema at `src/codegenie/schema/repo_context.schema.json`; per-probe sub-schemas under `src/codegenie/schema/probes/{name}.schema.json` (each `additionalProperties: false` at every node — Phase 1 ADR-0004). The envelope `probes.*` is `additionalProperties: true` (Phase 0 ADR-0013); strict-ness lives at the sub-schema. Adding a probe requires landing its sub-schema **and** wiring a `$ref` into the envelope's `properties.probes` (S4-07 is the precedent).

## Reading order for the design docs

Read in this order; skip the redundant ones:

1. **[`docs/production/`](docs/production/)** — canonical production-target reference folder. Start at `README.md`. Inside: `design.md` (Layered Hybrid Architecture, 7-stage pipeline, 4+1 views) + `adrs/` (one ADR per major decision, Nygard format).
2. **[`docs/localv2.md`](docs/localv2.md)** — canonical local POC spec. CLI surface, probe contract, probe inventory Layers A–G, `RepoContext` schema, caching, 6-week plan. The probe contract here is the contract.
3. **[`docs/roadmap.md`](docs/roadmap.md)** — phase scope, exit criteria, dependencies.
4. **[`docs/phases/{phase}/`](docs/phases/)** per-phase architecture — every implemented phase has `final-design.md` (synthesized design), `phase-arch-design.md` (4+1 views, edge cases, ADR table), `ADRs/` (Nygard-format decisions), `High-level-impl.md` (step-by-step plan), and `stories/` (executable units).
5. Background only: `docs/context.md`, `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`. Skip `docs/local.md` (superseded by `localv2.md`).

## Load-bearing architectural commitments

These appear across every doc and constrain implementation. Do not violate without surfacing the tradeoff via an ADR amendment:

- **No LLM anywhere in the gather pipeline.** Enforced by the `fence` CI job + `import-linter`, not by convention.
- **Facts, not judgments.** Probes capture evidence ("trace observed 0 shell invocations"). Conclusions ("safe to migrate") are the Planner's job.
- **Honest confidence.** Every probe reports `confidence: Literal["high", "medium", "low"]`. `IndexHealthProbe` (B2) is called out across docs as the single most important probe — silent index staleness is the worst failure mode.
- **Determinism over probabilism for structural changes.** Recipes (OpenRewrite) + AST/LST manipulation for structural transforms; LLM reserved for judgment calls.
- **Extension by addition.** New language / new task type = new probes + new Skills, never edits to existing probes or the coordinator. The probe contract in `base.py` is locked.
- **Organizational uniqueness as data, not prompts.** Skills with YAML frontmatter, conventions catalogs, policy YAML, replacement catalogs, exception registries.
- **Progressive disclosure for context.** `RepoContext` indexes evidence by path/manifest; consumers read originals at decision time.
- **Humans always merge.** Autonomy ends at PR creation.

## Conventions

- **YAML for the human-facing artifact** (`repo-context.yaml`); **JSON for raw probe outputs** under `.codegenie/context/raw/`; **JSON Schema** for validation.
- **Probes register via `@register_probe` decorator** at module import time. The decorator's two shapes are equivalent: `@register_probe` (defaults) and `@register_probe(heaviness=..., runs_last=...)`.
- **Each probe declares `declared_inputs`** (globs + special tokens). Cache keys derive from this; incremental gathers depend on it.
- **`declared_inputs` special tokens** ride alongside file globs (e.g., `tools/grammars.lock` historically, `image-digest:` per Phase 2 ADR-0004). The coordinator's snapshot system accepts them as content-addressable inputs.
- **`.codegenie/`** is the on-disk output namespace inside any analyzed repo. The CLI offers to add it to that repo's `.gitignore` on first run (TTY-only; non-TTY skips with a structured warning).
- **Warning + error IDs** match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007). Each probe declares a module-level `_WARNING_IDS: Final[frozenset[str]]` validated at import time via `raise AssertionError(...)` (bare `assert` is forbidden by the `forbidden-patterns` hook).
- **Functional core / imperative shell.** Pure helpers carry the logic; `run()` is the only impure code. AST-walking tests enforce this in several probes.
- **Newtype identifiers** (`ProbeId`, `IndexName`, `PackageManager`) under `codegenie.types.identifiers` — never raw `str` for domain IDs.
- **`pyright` is not used; `mypy --strict`** is the bar. `[tool.mypy.overrides]` carries per-module relaxations only when an upstream lacks stubs.
- **Match the existing convention** when in doubt. If two patterns disagree, pick the more recent and surface the older as cleanup.

## Stories + autonomous execution

The `/phase-story-writer`, `/phase-story-validator`, and `/phase-story-executor` skills are the canonical way to design / harden / ship new work. Each story under `docs/phases/{phase}/stories/` carries Context → References → Goal → Acceptance Criteria → Implementation Outline → TDD plan → Files to Touch. Per-story attempt logs live under `_attempts/` (append-only); validation reports under `_validation/`. When picking up work mid-stream, **read the latest attempt log entry first** — it tells you what already shipped and what's deferred.

A story's `**Status:**` line is the source of truth:
- `Ready` / `HARDENED` — validated, awaiting executor.
- `GREEN` / `Done` — shipped with runtime evidence.
- `BLOCKED` / `BLOCKED-PARTIAL` — explicit precondition not met; check the attempt log for the resolution path. As of 2026-05 there are zero `BLOCKED` stories.

## Global rules (also in `~/.claude/CLAUDE.md`)

The user maintains a 12-rule global instruction set: "Think Before Coding", "Simplicity First", "Surgical Changes", "Goal-Driven Execution", "Use the model only for judgment calls", "Token budgets are not advisory", "Surface conflicts, don't average them", "Read before you write", "Tests verify intent, not just behavior", "Checkpoint after every significant step", "Match the codebase's conventions", "Fail loud". Those rules apply here; this file does not restate them.
