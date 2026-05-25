# Shakedown — `codegenie gather` — 2026-05-25T18:57:01Z

**Capability:** `codegenie gather` (the primary shipped CLI surface)
**Sample app:** `Dannytrev21/sample-apps :: sample-apps/javascript/npm/esbuild` (fresh clone at `/tmp/sample-apps/`)
**Operator context:** post-S4-06 verification — confirm the Phase-4
`SolvedExampleWriter` + capability-mint boundary change did not regress
the LLM-free, fence-guarded gather pipeline runtime closure.
**Mode:** default (would fix on a real finding; nothing required fixing).
**Wall-clock:** ~3 minutes (capability runs + fence sweep).
**Outcome:** ✅ clean — zero new findings; four pre-existing by-design
honest-degradation outputs reproduce identically to the prior shakedown.

## Stage 0 — Environment doctor

`ruff` / `mypy` / `pytest` are present at `.venv/bin/*` but not on a
global `PATH`. The repo's idiom is `.venv/bin/<tool>` and the Makefile
shells set `PATH` appropriately. Acceptable, not a finding. `make`,
`git`, `python3`, and `codegenie` (`.venv/bin/python -m codegenie`)
resolve and respond to `--help`.

## Stage 1 — Capability spec

`codegenie gather PATH` walks the repo, runs every registered probe
under the coordinator's bounded `asyncio.Semaphore`, and writes
`.codegenie/context/repo-context.yaml` plus `.codegenie/context/raw/*`
+ an audit anchor under `.codegenie/context/runs/`. Documented exit
codes (per `--help`): 0 success / 2 every-probe-skipped / 3
envelope-schema-invalid / 5 symlink-refused / 6 secret-shaped-field.

Most recent prior report: `docs/_shakedowns/codegenie-gather-
2026-05-24T213722Z.md` — shipped a fail-loud
`probe.raw_artifact.missing_on_cache_hit` warning + integration test
for F1; F2–F5 were classified by-design (macOS limitations + deferred
strategies).

## Stage 2 — Sample app

`https://github.com/Dannytrev21/sample-apps :: sample-apps/javascript/
npm/esbuild` — node/npm/esbuild canonical fixture with a real
`Dockerfile`, `package.json`, `package-lock.json`, `src/index.js`,
`src/unsafe-demo.js`, `docker-entrypoint.sh`. Cloned fresh at
`/tmp/sample-apps/`. No prior `.codegenie/context/` — clean baseline.

## Stage 3 — Runs

Three back-to-back invocations from `/tmp/sample-apps/sample-apps/
javascript/npm/esbuild/`:

1. **Run #1** — `cli.end outcome=ok exit_code=0`. Every probe emitted
   `probe.success`. `secrets_redacted_count=2`,
   `fingerprints=[2bb4ede3, 6f9c56c7]` (ripgrep_curated and entrypoint
   secret-shaped redactions — expected, identical to prior shakedown).
2. **Run #2** — `cli.end outcome=ok exit_code=0`. Cache idempotence
   verified.
3. **Run #3** — `cli.end outcome=ok exit_code=0`. No
   `probe.raw_artifact.missing_on_cache_hit` warnings (F1's fail-loud
   path from the prior run does not trigger — staging files are intact).

Envelope: 36 probes present in `probes.*`; `schema_version: 0.1.0`;
`generated_at` ISO-8601 UTC; `repo.git_commit` resolves to the sample
app's HEAD.

## Stage 4 — Spec-vs-output inspection

| Layer | Probes | Result |
|-------|--------|--------|
| A (Node base) | `language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory` | all `high` |
| B | `tree_sitter_import_graph`, `scip_index`, `node_reflection`, `semantic_index_meta`, `index_health` | all `high` except `index_health` aggregate `low` (one stale source — see F1) |
| C/D/E | `ast_grep` (1 finding `no-eval`), `gitleaks` (0), `ripgrep_curated` (3 hits incl. 1 redacted), `semgrep` (clean), `dockerfile`, `entrypoint`, `shell_usage`, `certificate`, `test_coverage_mapping`, `generated_code` | all populated |
| F | `adrs`, `conventions`, `exceptions`, `external_docs`, `policy`, `repo_config`, `repo_notes`, `skills_index`, `ownership`, `service_topology`, `slo` | all populated |
| G | `runtime_trace`, `dep_graph`, `cve`, `sbom` | populated with honest degradation — see F1–F4 |

## Stage 5 — Findings + diagnosis

All four match the by-design classification from the prior shakedown.
None new. None require code changes.

| # | Finding | Root cause | Evidence |
|---|---------|------------|----------|
| F1 | `runtime_trace.trace_coverage_confidence: unavailable`; `index_health.runtime_trace = stale (indexer_error: upstream_runtime_trace_unavailable)` | **by-design** — macOS lacks `dtrace`/`strace`. Probe correctly reports honest unavailability rather than fabricating an empty trace. | Reproduces prior F2; `docs/get-started.md §Troubleshooting`; `CLAUDE.md` "honest confidence" load-bearing commitment. |
| F2 | `dep_graph.confidence: low / no_strategy_for_ecosystem` | **by-design** — `@register_dep_graph_strategy(PackageManager.NPM)` is not yet registered. First concrete strategy is deferred to a later phase (per CLAUDE.md §Open/Closed seams). | Reproduces prior F5; explicit note in `CLAUDE.md`. |
| F3 | `cve.confidence: unavailable` | **by-design** — vuln-index sqlite has not been refreshed (`codegenie vuln-index refresh`). | Reproduces prior F3. |
| F4 | `sbom.confidence: unavailable` | **by-design** — `osv-scanner` / `syft` not on local PATH. | Reproduces prior F4. |

## Stage 6 — Fixes

**Skipped — nothing to fix.** All findings are by-design honest
degradation, documented in `CLAUDE.md` and `docs/get-started.md`.

## Stage 7 — Doc sweep

**Skipped — no doc changes needed.** The prior shakedown's `get-
started.md` Troubleshooting and `CLAUDE.md` `dep_graph` note already
cover every finding observed today. The Phase-4 S4-06 work touches only
`src/codegenie/rag/*` (`ingest.py`, `_capability_mint.py`), the events
union, and a new import-linter contract — none of which affect the
gather pipeline runtime closure (verified: 477/477 fence tests pass
including the path-scoped contracts).

## Fence verification — S4-06 has not regressed the runtime closure

The fence suite is the load-bearing check that the gather pipeline
stays LLM-free:

```
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest --no-cov tests/fence/ -q
477 passed in 43.73s
```

`lint-imports --config pyproject.toml --no-cache`:

```
12 contracts KEPT, 0 broken
```

The new contract `ADR-0016: phase4 solved-example mint module is
scoped` (12th, added by S4-06) is `KEPT`. The
`codegenie.rag._capability_mint` module is reachable only from
`codegenie.rag.ingest`. Gather-pipeline modules under
`codegenie.probes/`, `codegenie.coordinator/`, `codegenie.cache/`,
`codegenie.output/`, etc. do not import `codegenie.rag.*` at all.

## Next-run primer

1. **F1–F4 remain by-design on macOS dev hosts** — do not chase them
   without `sudo dtrace`, a Linux `strace` substrate, an `osv-scanner`
   install, and a populated `vuln-index`.
2. **The fail-loud path added by the 2026-05-24 shakedown
   (`probe.raw_artifact.missing_on_cache_hit`) did not trigger this
   run** — the cache is intact and probes re-materialise from staging
   correctly.
3. **`SolvedExampleHarvested` is registered** but **not emitted** by
   gather. Emission lands with Phase-5 S6-03's caller-side gate. The
   gather CLI is silent on it; that is correct.
4. **When `@register_dep_graph_strategy(PackageManager.NPM)` lands**,
   `dep_graph.confidence` for this sample app should flip from `low` to
   `high` and surface real npm dep-graph edges. That will be the next
   meaningful delta on this sample.

## Token + wall-clock

- Wall-clock: ~3 minutes (3× gather runs + full fence pytest).
- Token consumption: within the per-session 30k budget.
