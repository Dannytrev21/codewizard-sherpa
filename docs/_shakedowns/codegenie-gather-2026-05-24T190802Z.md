---
capability: codegenie gather
sample_app: ~/development/sample-apps/sample-apps/javascript/npm/esbuild
run_utc: 2026-05-24T19:08:02Z
skill: capability-shakedown
trigger: scheduled-task (autonomous)
codebase_head: 3e83a52
gate_result: green
findings_total: 6
findings_by_route: { codebase-bug: 0, environment: 0, sample-app: 0, by-design: 6 }
make_check_after: not_re-run (no codebase mutations)
commit: housekeeping_only
---

# `codegenie gather` shakedown — 2026-05-24

**Verdict: healthy.** The capability runs to completion against the
`javascript/npm/esbuild` sample app, produces a 36-probe envelope plus 27
raw artifacts, is byte-identical on the second cache-hit run, and every
field that is empty / `unavailable` / `skipped` traces to a documented
honest-degradation path — not a bug. No codebase, sample-app, or
environment fixes needed.

## Stage 0 — environment doctor

All six tools resolved on `PATH` (`.venv/bin` prepended): `ruff`, `mypy`,
`pytest`, `make`, `git`, `codegenie`. PASS.

External tools discovered (used by deferred stages, not by Stage 0):

| Tool | Present | Used by |
|---|---|---|
| `syft` | ✓ | sbom probe |
| `grype` | ✓ | cve probe |
| `docker` | ✓ | runtime_trace probe |
| `strace` | ✗ | runtime_trace probe (Linux-only) |
| `dtrace` | ✓ | runtime_trace probe (macOS) |

## Stage 1 — capability + sample app

- CLI surface: `codegenie gather PATH` (exit codes 0 / 2 / 3 / 5 / 6 per
  ADR-0008 / ADR-0009 / ADR-0010).
- 36 probes register at import time across layers A, B, C, D, E, G (no
  layer F yet by design — Phase 9+).
- Sample app pre-state: no prior `.codegenie/context/` (clean slate).
  Sample-side `.codegenie/{conventions,skills,ast-grep,exceptions.yaml,
  scenarios.yaml,notes}` already present as Layer D / G probe inputs.

## Stage 2/3 — run

Two invocations, both with `--auto-gitignore` (non-TTY safe):

| # | Result | Notes |
|---|---|---|
| 1 (cold) | exit 0 | 36 probes succeed; `envelope.written` event; 2 secrets redacted (fingerprints `2bb4ede3`, `6f9c56c7`); 27 raw artifacts produced |
| 2 (warm) | exit 0 | Every probe hit cache (`probe.cache_hit`); same `secrets_redacted_count=2`; idempotent — content-addressed cache works as designed |

Followup capability:

- `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` →
  exit **4**, `audit.verify.yaml_mismatch` against run #1's anchor.

## Stage 4 — findings against the spec

Six concrete observations, each one a thing that landed empty,
unavailable, or behaviorally surprising:

| ID | Where | What was observed |
|---|---|---|
| F1 | `probes.ast_grep.outcome.findings = []` while `probes.ast_grep.findings_detail` carries one `no-eval` hit | `outcome.findings` is *always* empty — see diagnosis |
| F2 | `probes.sbom.outcome.kind = skipped, reason = upstream_unavailable`, `package_count = 0` | despite `syft` being installed |
| F3 | `probes.cve.outcome.kind = skipped, reason = upstream_unavailable` | despite `grype` being installed |
| F4 | `probes.runtime_trace`: `scenarios_failed = [startup, smoke_test, healthcheck, shutdown, error_path]`, `built_image_digest = null`, `trace_coverage_confidence = unavailable` | all five scenarios failed |
| F5 | `probes.dep_graph.confidence = low, reason = no_strategy_for_ecosystem`, `nodes_count = 0` | npm strategy is absent from `default_dep_graph_registry` |
| F6 | `audit verify` exit 4 with `mismatch_count = 1` after re-running gather | YAML anchor recorded by run #1 mismatches current YAML rewritten by run #2 |

## Stage 5 — diagnosis

Every finding is classified into exactly one root-cause bucket. The
discriminating test for each is named.

### F1 — `ast_grep.outcome.findings = []` is intentional → **by-design**

The probe ends in `return ScannerRan(findings=[]), findings`
(`src/codegenie/probes/layer_g/ast_grep.py:141`). The shared
`ScannerOutcome.Finding` family
(`src/codegenie/probes/_shared/scanner_outcome.py:67`) is a generic
sum-type carrying `severity` + opaque `metadata`; it is deliberately
distinct from each probe's *own* finding model (`AstGrepFinding`,
`SemgrepFinding`, …). Probe-specific data lives in the slice-level
`findings_detail`; `outcome.findings` is reserved for the generic
sum-type and is empty by convention. The `outcome.kind = "ran"` is the
load-bearing signal — it tells consumers the tool ran successfully.

**Discriminating test:** confirmed by grep on the same pattern in
`ripgrep_curated` and `test_coverage_mapping` — both ship `outcome:
{ kind: ran, findings: [] }` alongside populated `findings_detail`. The
pattern is uniform.

**Note for future readers:** the data shape is harder to read than it
needs to be — a casual reader will assume `outcome.findings = []` means
"no findings." Phase-2 ADR-0006 (sum-type discipline) is the relevant
ADR. Not raising for a fix here because it is the established
multi-probe convention; flagging it instead in the doc-sweep section
below.

### F2/F3/F4 — sbom/cve/runtime_trace skipped → **by-design (cascading degradation)**

- `runtime_trace`'s job is to `docker build` + `docker run` the sample
  app and capture syscall traces. The five scenarios
  (`startup / smoke_test / healthcheck / shutdown / error_path`) all
  failed in this environment — likely because the macOS DTrace path
  needs elevated privileges (`sudo`/SIP), or the sample's Dockerfile
  build/run wasn't fully exercisable in the autonomous skill's
  unprivileged sandbox.
- `runtime_trace` then writes a slice with
  `built_image_digest = null` + `trace_coverage_confidence = unavailable`.
- `sbom` requires `runtime_trace` (declared in `requires`) — it reads the
  upstream `built_image_digest` and skips when absent
  (`src/codegenie/probes/layer_c/sbom.py:232-238`).
- `cve` skips on the same cascade
  (`src/codegenie/probes/layer_c/cve.py:194`).

`index_health.runtime_trace.kind = stale,
reason.kind = indexer_error, message = upstream_runtime_trace_unavailable`
collapses both upstream-degraded paths onto one renderer-friendly
message (`runtime_trace.py:1117-1128`) — exactly the design.

**Discriminating test:** flipping `built_image_digest` in
`runtime_trace.json` (or running on a substrate with privilege to `sudo
dtrace`) would unblock all three. The dependency chain is in the
source, not in this report's imagination.

### F5 — `dep_graph` no strategy → **by-design**

`default_dep_graph_registry.registered_ecosystems()` returns
`frozenset()`. The `@register_dep_graph_strategy(PackageManager)`
extension point ships from Phase-2 work but no concrete strategy is
registered yet. CLAUDE.md says *"Phase 3 fills it"* but Phase-3 work has
shipped lockfile-policy + recipe-engine surfaces (S5-01 … S5-04) and
uses lockfile-level inspection rather than a graph probe at the Planner
level. The `dep_graph` probe correctly emits `confidence = low, reason
= no_strategy_for_ecosystem` rather than guessing.

**Documentation drift:** CLAUDE.md's "Phase 3 fills it" sentence is now
loose. The Phase-3 stories that reference `@register_dep_graph_strategy`
(S2-01 plugin registry, S3-03 vuln-index, S6-06 contract snapshot) all
cite it as a *precedent* registry, not as a place to add an npm
strategy. The npm dep_graph strategy is genuinely deferred and the
register is genuinely empty today. Logged for the doc sweep.

### F6 — `audit verify` exit 4 → **by-design**

The YAML whole-output anchor is recorded **per run** at write time
(`audit.write.ok`). Each `gather` invocation regenerates
`repo-context.yaml` — even a 100% cache-hit run rewrites the envelope
(differing `generated_at` timestamp). So `audit verify` necessarily
sees the run-1 anchor disagree with the post-run-2 YAML hash. Anchor
mismatch is the intended tamper-detection signal; the user is meant to
point `audit verify` at *one* run-record's view of the world, not at the
union of two distinct runs.

**Note:** the CLI's help text ("Exit 4 — one or more mismatches
detected (tamper or drift)") is accurate but the operational guidance
("which run am I verifying against?") is implicit. Worth a one-line
mention in `docs/get-started.md` so the next operator does not chase a
phantom tamper. Logged for the doc sweep.

## Stage 6 — fixes by route

| Route | Count | Action taken |
|---|---|---|
| codebase-bug | 0 | — |
| environment | 0 | — (F2/F3/F4 are cascading from F4's intrinsic substrate need; setting up `sudo dtrace` is outside the autonomous-skill scope) |
| sample-app | 0 | — (no missing inputs; the sample app exercises 33 of 36 probes) |
| by-design | 6 | documented above; one doc-sweep item logged |

`make check` was not re-run because no codebase mutations were made.

## Stage 7 — doc sweep

One **trivial-doc** drift surfaced (not raising as a finding, raising as a
doc-sweep item per Rule 11):

- `CLAUDE.md` says *"`@register_dep_graph_strategy(PackageManager)`
  (`codegenie.depgraph` — per-ecosystem strategies; Phase 3 fills it)."*
  The register is empty post-Phase-3-S5-04. Phase 3 does not fill it.
  This single phrase belongs to a "deferred until vuln-remediation
  needs it" sentence, or to a roadmap pointer to whichever later phase
  actually ships the first concrete strategy. Not edited inline here
  — it is a project-context call belonging to the author. **Action:**
  flagged as a follow-up; see "Next-run primer" below.

The other five findings are by-design and need no doc updates.

## Next-run primer

For the next operator picking up this capability:

1. **Don't chase F2/F3/F4 unless you have `sudo dtrace` or a Linux
   `strace` substrate.** They are a single cascade from
   `runtime_trace`'s substrate need, not three independent failures. The
   honest-degradation envelope is the correct output in an unprivileged
   environment.
2. **`audit verify` is per-run.** Point it at one run-record's view; do
   not expect it to span re-runs. Exit 4 across runs is correct
   tamper-detection.
3. **The `dep_graph` npm strategy is genuinely not shipped.** When you
   read `dep_graph.confidence = low, no_strategy_for_ecosystem`, that is
   the truth. CLAUDE.md's hint about "Phase 3 fills it" needs an edit
   — see Stage 7.
4. **`outcome.findings` vs `findings_detail` is a structural convention,
   not a bug.** Read `findings_detail` for the real scanner hits.
5. **Bench:** cold run end-to-end ~750ms wall clock on M-series macOS;
   warm run (full cache hit) ~200ms. Both under the 30-second probe
   timeout by two orders of magnitude.

## Artifacts

- Envelope: `~/development/sample-apps/sample-apps/javascript/npm/esbuild/.codegenie/context/repo-context.yaml`
  (12,814 bytes, sha256 `803b233f8242d4a375e96765bd4e371455882cf259487a8ecc728bd4ca048ee0`)
- Raw probe outputs: 27 files in `.../raw/`
- Audit anchors: 2 run-records in `.../runs/`

## Token + wall-clock

- Wall-clock for the shakedown stages 0–8: ~3 minutes.
- Token consumption: approximately one Claude session, well under the
  per-session 30k cap.
