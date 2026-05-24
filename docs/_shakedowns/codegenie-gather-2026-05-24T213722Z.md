---
capability: codegenie gather
sample_app: ~/development/sample-apps/sample-apps/javascript/npm/esbuild + tests/fixtures/portfolio/minimal-ts
run_utc: 2026-05-24T21:37:22Z
skill: capability-shakedown
trigger: scheduled-task (autonomous)
codebase_head: f8d3ad9
gate_result: green (pre-existing macOS-local flakes only)
findings_total: 7
findings_by_route: { codebase-bug: 1, environment: 0, sample-app: 0, by-design: 6 }
make_check_after: green-modulo-known-flakes
commit: pending (this report + fix bundle)
---

# `codegenie gather` shakedown — 2026-05-24 (run 2)

**Verdict: one real codebase-bug fixed.** The prior shakedown
(`codegenie-gather-2026-05-24T190802Z.md`, run 1) declared the warm-run
behavior "idempotent." It is **not**: when a cached probe output's
`raw_artifacts` path no longer exists on disk (an operator manually
cleared `.codegenie/context/` while leaving `.codegenie/cache/` intact),
the CLI silently skipped the artifact and produced a warm-run
`.codegenie/context/raw/` containing only 2 files instead of 27. That is
a Rule 12 violation — a silent partial output. **Fixed** in `src/codegenie/cli.py`
by adding a fail-loud `probe.raw_artifact.missing_on_cache_hit` warning,
backed by a failing-first integration test.

The other six findings from run 1 re-validated as by-design — re-running
them produced the same outputs.

## Stage 0 — environment doctor

All six tools resolved via `.venv/bin/`: `ruff` (0.15.13), `mypy` (2.1.0),
`pytest` (9.0.3), `make`, `git`, `codegenie`. PASS.

## Stage 1 — capability + sample app + prior-report read

- Prior report at `docs/_shakedowns/codegenie-gather-2026-05-24T190802Z.md`
  read first — settled findings (six by-design) not re-litigated; one
  CLAUDE.md doc-sweep follow-up carried into this run and discharged.
- CLI surface: `codegenie gather PATH` (exit codes 0 / 2 / 3 / 5 / 6 per
  ADR-0008 / ADR-0009 / ADR-0010); 36 probes register at import time.
- Sample app: `~/development/sample-apps/sample-apps/javascript/npm/esbuild`
  (same as run 1) plus `tests/fixtures/portfolio/minimal-ts` for the
  failing-first integration test.

## Stage 2/3 — runs

| # | State | Result | Notes |
|---|---|---|---|
| 1 | cold (cache + context both cleared) | exit 0 | 36 probes ran, 27 raw artifacts produced in `.codegenie/context/raw/`, 2 secrets redacted (fingerprints `2bb4ede3`, `6f9c56c7`) |
| 2 | warm (cache intact, full `.codegenie/context/` cleared) | exit 0 | **27 → 2 raw artifacts** — only `ci.json` (under `_probe_raw/`, untouched) and `package-lock.json` (source file in repo root) survived; the other 25 silently vanished |
| 3 | warm (cache intact, `.codegenie/context/raw/` + per-probe staging cleared) | exit 0 | reproduces the silent skip exactly: 2 raw files, zero warning events |

## Stage 4 — findings against the spec

Seven findings. **One is a codebase-bug** (new); six are by-design and
re-validated from run 1.

| ID | Where | What was observed | Route |
|---|---|---|---|
| F1 *(NEW)* | `cli.py:633` — `if isinstance(raw_path, Path) and raw_path.is_file():` | On a cache-hit run whose probe-staged source file is missing, the loop silently skips with **no warning event**. 25 of 27 raw artifacts vanish from `.codegenie/context/raw/` without a single log line surfacing the gap | **codebase-bug → FIXED** |
| F2 (re-validated) | `probes.ast_grep.outcome.findings = []` while `findings_detail` has data | by-design (`outcome.findings` is the generic sum-type; per-probe data lives in `findings_detail`) | by-design |
| F3 (re-validated) | `probes.sbom.outcome.kind = skipped, reason = upstream_unavailable` | by-design (cascades from F5) | by-design |
| F4 (re-validated) | `probes.cve.outcome.kind = skipped` | by-design (cascades from F5) | by-design |
| F5 (re-validated) | `runtime_trace`: all five scenarios failed; `built_image_digest = null` | by-design on macOS (`runtime_trace` needs `sudo dtrace`/Linux `strace`; honest degradation) | by-design |
| F6 (re-validated) | `dep_graph.confidence = low, reason = no_strategy_for_ecosystem` | by-design (registry intentionally empty post-Phase-3) — CLAUDE.md drift fixed in this run | by-design |
| F7 (re-validated) | `audit verify` exit 4 with `mismatch_count = 1` across re-runs | by-design (anchor is per-run; YAML regenerates with new `generated_at`) | by-design |

## Stage 5 — diagnosis

### F1 — silent raw-artifact loss on cache hit → codebase-bug

**Root cause chain.** Each probe writes its raw artifact to one of two
staging locations:

- `<workspace>/.codegenie/_probe_raw/<name>.json` (e.g. `ci.py`,
  `deployment.py` — outside the user-visible output namespace).
- `<workspace>/.codegenie/context/<name>.json` (e.g. `policy.py`,
  `conventions.py`, `adrs.py`, `external_docs.py`, `skills_index.py`,
  `repo_config.py`, `repo_notes.py`, `slo.py`, `service_topology.py`,
  `exceptions.py` — Layer D probes writing under `ctx.output_dir`).

Then `cli.py` walks every probe output, reads the bytes off `raw_path`,
redacts them, and hands the redacted bytes to `Writer.write()`, which
publishes the canonical copy under `.codegenie/context/raw/<name>`.

On a cache hit, the probe is **not re-executed**. The deserialized
`ProbeOutput` carries the same `raw_artifacts` paths the original run
emitted. If those staging files were deleted between runs (deleting
`.codegenie/context/` removes the Layer D staging files), the CLI's
`raw_path.is_file()` guard at `cli.py:633` evaluates `False` and the
loop **continues silently**. No structured event, no warning, no
operator-visible signal.

**Discriminating test.** With the fix uninstalled:

1. Cold gather populates `.codegenie/cache/` + `.codegenie/_probe_raw/` +
   `.codegenie/context/`.
2. `rm -rf .codegenie/context/raw .codegenie/context/<every-staged-name>.json`.
3. Warm gather: 36 `probe.cache_hit` events, `envelope.written` reports
   the full slice, but `ls .codegenie/context/raw/ | wc -l` returns 2,
   not 27. Logs contain **zero** events naming the 25 lost raw artifacts.

**Why run 1 missed it.** The prior shakedown ran two back-to-back
gathers with `.codegenie/context/` intact between runs, so all staging
files survived and all raw artifacts re-materialized. Run 1's claim
"`idempotent — content-addressed cache works as designed`" is true at
the YAML envelope level but **wrong at the raw-artifact level under any
operator action that clears outputs**.

**Severity.** Rule 12 (Fail loud) violation. The YAML envelope stays
correct (consumers reading the structured slice see everything), but
consumers reading `.codegenie/context/raw/*.json` see a silent partial
output with no diagnostic. Blast radius is bounded — the typical user
flow (don't manually clear codegenie outputs) does not trip the bug —
but the bug *is* a real silent data loss path.

### F2–F7 — re-validated from run 1, no changes

See `codegenie-gather-2026-05-24T190802Z.md` §Stage 5 for the
discriminating tests. The diagnoses still hold:

- F2: `outcome.findings` is the generic `ScannerOutcome.Finding` sum-type;
  probe-specific data lives in `findings_detail` (uniform across
  `ast_grep`, `ripgrep_curated`, `test_coverage_mapping`).
- F3/F4/F5: cascading degradation from `runtime_trace`'s macOS substrate
  need. CI on Linux exercises the full chain.
- F6: `default_dep_graph_registry` ships empty post-Phase-3-S5-04;
  Phase 3 cites it as a precedent registry, not an implementation site.
  The probe's `low / no_strategy_for_ecosystem` is the honest output.
- F7: `audit verify` anchor is per-run; cross-run exit 4 is the
  designed tamper-detection signal, not a bug.

## Stage 6 — fixes by route

| Route | Count | Action taken |
|---|---|---|
| codebase-bug | 1 | **F1 fixed:** new `probe.raw_artifact.missing_on_cache_hit` event in `src/codegenie/cli.py`; failing-first test at `tests/integration/cli/test_raw_artifact_missing_on_cache_hit.py`; constant registered in `src/codegenie/logging.py` (with the closure test updated in `tests/unit/test_logging.py`) |
| environment | 0 | — |
| sample-app | 0 | — |
| by-design | 6 | re-validated; no edits |

### Test-gap analysis for F1

- **Existing coverage:** `tests/unit/coordinator/test_raw_artifact_truncation_integration.py`
  pins the *truncation* event payload, but mirrors the cli.py emission
  in a parallel helper — it does not exercise the actual cli.py loop's
  `raw_path.is_file()` branch.
- **Why the bug slipped:** no test invoked the full CLI under the
  "cache warm, raw staging missing" precondition. The existing
  integration tests either preserve `.codegenie/` between runs
  (`test_summary_determinism.py`) or never run gather twice
  (`test_summary_count_matches_event.py`).
- **New coverage:** `test_raw_artifact_missing_on_cache_hit.py` runs
  the full `CliRunner.invoke(cli, ["--no-gitignore", "gather", ...])`
  pipeline twice against `minimal-ts`, deletes the staging dirs between
  invocations, and asserts the new event is emitted with the contracted
  `{event, probe, path}` payload keys.
- **Non-vacuity check:** verified test goes **red** on the pre-fix code
  (no event in `warm_logs`), then **green** after the cli.py edit. The
  failing assertion message dumps every captured event name on red, so a
  future regression of the fix produces a high-signal failure.

### Verification

- `pytest tests/integration/cli/test_raw_artifact_missing_on_cache_hit.py`:
  1 passed in 4.72s (fix-green).
- `pytest tests/integration/cli/ tests/fence/ tests/unit/test_logging.py`:
  468 passed in 93.51s.
- `mypy --strict src/codegenie/cli.py src/codegenie/logging.py`: no issues.
- `ruff check` + `ruff format --check` on all four touched source files:
  clean.
- `make docs`: builds in 36.45s.
- Full `make check`: 6479 passed / 40 skipped / 9 xfailed / **2 failed**.
  Both failures are pre-existing macOS-local flakes unrelated to the
  diff:
  - `tests/adv/test_tsconfig_pathological.py::...silently_swallows_under_two_seconds`
    — 3.24s on macOS vs. the 2.0s wall-clock bound (documented in the
    Phase-4 S1-01 attempt log; CI on Linux passes consistently).
  - `tests/integration/portfolio/test_portfolio_sweep.py::test_portfolio_sweep`
    — passed in isolation; test-ordering filesystem flake.

## Stage 7 — doc sweep

| Doc | Edit | Reason |
|---|---|---|
| `CLAUDE.md` §Open/Closed seams | rewrote the `@register_dep_graph_strategy` line — "Phase 3 fills it" → "registry ships empty; cited as a precedent; first concrete strategy lands in a later phase" | discharges the run-1 follow-up; matches the post-Phase-3-S5-04 reality |
| `docs/get-started.md` §Troubleshooting | added a "Logs include `probe.raw_artifact.missing_on_cache_hit` warnings" entry explaining the cause and the `rm -rf .codegenie/` recovery path | F1's operator-facing surface |

No ADR amendments needed:

- `02-ADR-0008` (single-event discipline) — this is one new structured
  warning, not a new event stream, so it falls under the existing
  discipline.
- The probe ABC is unchanged (no new field on `ProbeOutput`).
- The cache blob format is unchanged.

## Architectural follow-up — deferred

The minimum-viable fix surfaces the silent skip but does **not**
re-materialize the lost raw artifacts. A deeper fix would store the raw
artifact **bytes** in the cache blob (alongside `schema_slice`,
`raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`) so
cache hits could re-publish raw artifacts without re-executing probes.
That touches:

- `src/codegenie/cache/store.py` — extend the serialized blob with a
  base64-encoded `raw_artifact_bytes` field.
- `src/codegenie/coordinator/coordinator.py` — on cache miss, read bytes
  off the staging path and stash them on the in-memory output before
  caching; on cache hit, hand the cached bytes back to the CLI directly.
- `src/codegenie/audit/` — the audit anchor is computed over the cache
  blob bytes (`serialize_output`); changing the blob format changes
  the anchor.
- `tests/fence/` — several cache-format and audit-anchor fences pin the
  current blob shape.

That is a multi-file architectural change deserving an ADR amendment.
**Routing:** flagged here for a future `/phase-story-writer` cycle when
the bug's blast radius outweighs the architectural cost; today the
fail-loud warning + the troubleshooting note are the surgical fix that
satisfies Rule 3 (Surgical Changes) and Rule 12 (Fail loud) without
disturbing frozen contracts.

## Other outstanding item flagged this run

`docs/phases/04-vuln-llm-fallback-rag/stories/S1-07-test-kernel-frozen.md`
is in **RESCUE** status per its validation report at
`docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S1-07-test-kernel-frozen.md`.
The story prescribes a brand-new BLAKE3-based fence file
(`tests/fence/test_kernel_frozen.py`) when the design says to extend
the existing Phase-3 file with a one-row append to `_BASELINES`. This
is a `/phase-story-writer` re-author task, not a code change. Calling
it out here so the next operator does not pick up S1-07 as written and
clobber the shipped Phase-3 fence. Status on master: the existing
`tests/fence/test_kernel_frozen.py` is green (14 tests pass on HEAD
`f8d3ad9`).

## Next-run primer

For the next operator picking up this capability:

1. **F2/F3/F4/F5 are still by-design on macOS.** Don't chase them
   unless you have `sudo dtrace` or a Linux `strace` substrate. See
   `docs/get-started.md` §Troubleshooting.
2. **`audit verify` is per-run.** Point it at one run-record's view;
   exit 4 across re-runs is the designed tamper-detection signal.
3. **F1 (this run's bug) is now fail-loud, not silent.** If you see
   `probe.raw_artifact.missing_on_cache_hit` in the logs, the staging
   files have been deleted out from under a cached output. Clear the
   whole `.codegenie/` namespace or run `codegenie cache prune --all`
   and re-gather to force a clean re-materialization.
4. **`outcome.findings` vs `findings_detail` is structural.** Read
   `findings_detail` for the real scanner hits.
5. **`dep_graph` confidence stays `low / no_strategy_for_ecosystem`**
   until a later phase ships the first `@register_dep_graph_strategy`.
   CLAUDE.md is now accurate about this.
6. **S1-07 is in RESCUE.** Do not send it to `phase-story-executor` —
   it needs `phase-story-writer` to re-author against the existing
   Phase-3 `tests/fence/test_kernel_frozen.py` allowlist seam.

## Artifacts produced this run

- New source-of-truth event constant in `src/codegenie/logging.py`:
  `EVENT_PROBE_RAW_ARTIFACT_MISSING_ON_CACHE_HIT`.
- Code change at `src/codegenie/cli.py:633-651` — fail-loud warning
  before the existing read-and-redact branch.
- New integration test at
  `tests/integration/cli/test_raw_artifact_missing_on_cache_hit.py`.
- Updated `tests/unit/test_logging.py` (event closure registry).
- Updated `CLAUDE.md` (dep_graph drift).
- Updated `docs/get-started.md` (troubleshooting entry).
- Sample-app envelope (rebuilt twice during the shakedown):
  `~/development/sample-apps/sample-apps/javascript/npm/esbuild/.codegenie/context/repo-context.yaml`.

## Token + wall-clock

- Wall-clock for stages 0–8: ~30 minutes (one full `make check` cycle
  dominated).
- Token consumption: within the per-session 30k budget.
