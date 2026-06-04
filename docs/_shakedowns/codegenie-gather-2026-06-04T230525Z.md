# Shakedown — `codegenie gather` — 2026-06-04T23:05:25Z

**Capability:** `codegenie gather` (the primary shipped CLI surface)
**Sample app:** `Dannytrev21/sample-apps :: sample-apps/javascript/npm/esbuild` (fresh clone at `/tmp/sample-apps-shakedown/`)
**Operator context:** scheduled capability-shakedown run. Entry
precondition was a **red master** — the `ci` workflow's `security` job
was failing — so this run first fixed CI, then exercised the gather
pipeline (untouched since the 2026-05-25 baseline; Phase 6.5 work is
validated but unexecuted, so no new gather probes have landed).
**Mode:** default (fix-in-place). Codebase fixes committed + pushed
(scheduled task explicitly authorizes commit/push to master, the repo's
established single-branch workflow).
**Wall-clock:** ~18 min (CI fix + CI wait + 3× gather runs + inspection).
**Outcome:** ✅ CI security failure fixed and verified green; gather
pipeline reproduces the clean by-design baseline — zero new findings.

---

## Entry precondition — red master (fixed first)

The most recent `ci` run before this shakedown (commit `803c11d`,
run 26980650466) **failed** in the `security` job. `pip-audit` flagged
aiohttp 3.13.5 with two advisories fixed only in 3.14.0:

| ID | GHSA | Nature |
|---|---|---|
| CVE-2026-34993 | GHSA-jg22-mg44-37j8 | `CookieJar.load()` on untrusted input → code execution |
| CVE-2026-47265 | GHSA-hg6j-4rv6-33pg | per-request `cookies=` re-sent across attacker-controlled cross-origin redirect |

**Root cause — genuine dependency conflict.** Commit `e0aba57` had
pinned `aiohttp<3.14` because vcrpy 8.1.1 (the latest release; no newer
one exists) imports `aiohttp.streams.AsyncStreamReaderMixin`, which
aiohttp 3.14.0 removed — lifting the cap breaks the cassette integration
tests at import time. So the fix version (3.14.0) is unreachable while
vcrpy lacks 3.14 support.

**Why the advisories are not reachable in our usage:**
- aiohttp is a **transitive dep only** — `grep -rn 'import aiohttp' src/`
  is empty. It enters via chromadb/fastembed (path-scoped to
  `src/codegenie/rag/` per ADR-04-0003) and the kubernetes client.
- CVE-2026-34993 requires `CookieJar.load()` on attacker-controlled
  input; codegenie never calls it. OSV itself notes the advisory is
  "unlikely to affect many applications."
- CVE-2026-47265 requires per-request `cookies=` plus an
  attacker-controlled cross-origin redirect; codegenie issues no such
  requests.

**Fix (matches the existing `PYSEC-2026-89` / `MAL-2026-4750`
suppression pattern):** documented suppression in both enforcement
points —
- `.github/workflows/ci.yml` — `pip-audit … --ignore-vuln
  CVE-2026-34993 --ignore-vuln CVE-2026-47265` with a full rationale
  comment.
- `osv-scanner.toml` — two `[[IgnoredVulns]]` entries keyed by GHSA id,
  each carrying a `reason` + `ignoreUntil = 2026-09-04` so the
  suppression re-surfaces for review.

**Verified:**
- Local reproduction of the CI step: `pip-audit … --ignore-vuln …` →
  `No known vulnerabilities found, 2 ignored` (exit 0).
- TOML + YAML both parse.
- Committed `da57171`, pushed; CI run **26982841903 succeeded** —
  `security` job green.

**Removal trigger:** drop all four `--ignore-vuln` flags + both
`osv-scanner.toml` entries once vcrpy ships aiohttp-3.14 compatibility
and the `aiohttp<3.14` cap in `pyproject.toml` is lifted.

---

## Stage 0 — Environment doctor

`git`, `make` on PATH; `ruff`/`mypy`/`pytest` at `.venv/bin/*` (repo
idiom); `codegenie` v0.0.1 responds; `docker` present (unused — no
finding needed it). Working tree clean apart from untracked
`.claude/worktrees/` + `.coverage`. **Pass.**

## Stage 1 — Capability spec + prior report

Read `docs/_shakedowns/codegenie-gather-2026-05-25T185701Z.md` — the
last gather shakedown was clean with four settled by-design findings
(F1–F4 below). `codegenie gather PATH` walks the repo, runs every
registered probe under the coordinator's bounded semaphore, writes
`.codegenie/context/repo-context.yaml` + `raw/*` + an audit anchor.
Documented exit codes: 0 ok / 2 all-skipped / 3 schema-invalid /
5 symlink-refused / 6 secret-shaped-field.

## Stage 2 — Sample app

`Dannytrev21/sample-apps :: javascript/npm/esbuild` — canonical Node
fixture (`Dockerfile`, `package.json`, `package-lock.json`, `src/*.js`,
`docker-entrypoint.sh`, `k8s/`, `.semgrep.yml`). Cloned fresh; the
committed `.codegenie/` was removed before each baseline run.

## Stage 3 — Runs

| Run | Result | Notes |
|---|---|---|
| #1 (cold) | `cli.end outcome=ok exit_code=0` | `secrets_redacted_count=2`, `fingerprints=[2bb4ede3, 6f9c56c7]` — identical to baseline |
| #2 (warm) | `cli.end outcome=ok exit_code=0` | cache hits across probes incl. `cve`/`sbom`/`scip_index`; no `missing_on_cache_hit` warnings — idempotent |
| #3 (cold, error sweep) | `exit 0` | only event matching error/warn/skip/fail: `subproc.bwrap.skipped reason=not_linux platform=darwin` (bubblewrap is Linux-only — by-design) |

Envelope: `schema_version 0.1.0`, **36 probes** (unchanged from
baseline — no new gather probes since), schema-valid (else exit 3).
27 raw artifacts: 25 JSON, `ripgrep_curated-raw.json` is JSONL (ripgrep
`--json` is natively line-delimited — honest raw tool stdout),
`scip-index.scip` is binary protobuf (by-design `.scip`).

## Stage 4–5 — Findings + diagnosis

Zero **new** findings. The four prior by-design honest-degradation
outputs reproduce byte-for-identically:

| # | Finding | Root cause | Evidence |
|---|---------|------------|----------|
| F1 | `runtime_trace`: all 5 scenarios failed, `last_traced_image_digest=null` | **by-design** — macOS lacks `dtrace`/`strace`; bwrap skip (`not_linux`). Probe reports honest unavailability. | `subproc.bwrap.skipped`; `CLAUDE.md` "honest confidence". |
| F2 | `dep_graph.confidence: low / no_strategy_for_ecosystem` (ecosystem `npm`, 0 nodes/edges) | **by-design** — `grep -rn '@register_dep_graph_strategy' src/` finds only the decorator definition; registry ships empty per CLAUDE.md §Open/Closed seams. | registry empty confirmed. |
| F3 | `cve.confidence: unavailable / outcome.reason=upstream_unavailable` | **by-design** — vuln-index sqlite not refreshed (`codegenie vuln-index refresh`). | reproduces baseline F3. |
| F4 | `sbom.confidence: unavailable` | **by-design** — `osv-scanner`/`syft` not on local PATH. | reproduces baseline F4. |

## Stage 6 — Fixes

**Gather pipeline: nothing to fix** — all findings are by-design,
already documented in `CLAUDE.md` + `docs/get-started.md`. The only
codebase change this run was the CI security suppression (above), which
does not touch the gather runtime closure (`ci.yml` + `osv-scanner.toml`
only).

## Stage 7 — Doc sweep

No gather code changed → no gather docs stale. The CI fix is
self-documenting (inline `ci.yml` rationale + `osv-scanner.toml` `reason`
fields, mirroring the two existing suppressions). No ADR/design/roadmap
doc was made stale by a config-only suppression.

## Adjacent state observed (not findings — context for next run)

- **Phase 6.5** (per-task-class eval harness) is fully **validated**
  (stories `HARDENED`/`Ready`) but **unexecuted** — no `src/codegenie/eval`
  or `bench` module exists, no `_attempts/` dir. There is no eval-harness
  capability to shake down yet.
- **`S2-05-canary-seed-shim` is `BLOCKED`** (design-stage): the story was
  written against a phantom Phase-4 `Canary.mint(seed=...)` API. The
  validator left a documented rescue path (expose a pure
  `pinned_nonce_source(case)` factory feeding the existing
  `FenceWrapper(nonce_source=…)` DI seam; zero Phase-4 edits). **Owner:
  phase architect** — amend ADR-0005 to the shipped Phase-4 surface and
  re-run `phase-story-writer`. Not a regression; correctly parked.

## Next-run primer

1. **F1–F4 remain by-design on macOS dev hosts** — do not chase without
   `sudo dtrace` / a Linux `strace` substrate / an `osv-scanner` install
   / a populated vuln-index.
2. **When `@register_dep_graph_strategy(PackageManager.NPM)` lands**,
   `dep_graph` for this sample should flip `low → high` with real npm
   edges — the next meaningful gather delta on this fixture.
3. **The aiohttp CVE suppression is temporary** — re-check at the
   `2026-09-04` `ignoreUntil`; remove once vcrpy supports aiohttp 3.14.
4. **No new gather probes will appear until Phase 6.5 is executed** (or a
   later phase adds Layer-G strategies). A gather re-run before then will
   reproduce this exact 36-probe baseline.

## Token + wall-clock

- Wall-clock: ~18 min (CI fix + ~15 min CI wait + 3× gather + inspection).
- Token consumption: within session budget; flagged here per Rule 6.
