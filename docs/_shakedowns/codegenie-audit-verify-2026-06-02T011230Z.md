# Shakedown — `codegenie audit verify` — 2026-06-02T01:12:30Z

**Capability:** `codegenie audit verify` (the Phase-2 Gap-2 / ADR-0004 pure-read
audit-anchor verifier — recomputes every per-probe `blob_sha256` + the
whole-output `yaml_sha256` and reports drift/tamper).
**Sample app:** `Dannytrev21/sample-apps :: sample-apps/javascript/npm/esbuild`
(fresh clone at `/tmp/sample-apps/`). The capability operates on a
`.codegenie/context/` substrate, so a fresh `codegenie gather` run against the
esbuild fixture produced the audit substrate under test (36 probes + 1
run-record + 1 YAML whole-output anchor + content-addressed cache blobs).
**Operator context:** scheduled `capability-shakedown` run. `audit verify` was
flagged **never-shaken-down** in the prior `rag rebuild` report's Next-run
primer (`docs/_shakedowns/codegenie-rag-rebuild-2026-05-25T170000Z.md`). It is
the cleanest hermetic / deterministic never-tested capability — no network
(unlike `vuln-index refresh`), exercises the audit-integrity chain nothing
else covers.
**Mode:** default (would fix on a real codebase bug; nothing required a code fix).
**Repo HEAD:** `db40f7d` (master, CI green — last push S4-02 succeeded).
**Wall-clock:** ~6 minutes (gather substrate + 7 verify invocations + source
read + doc note + report).
**Outcome:** ✅ **clean — zero codebase bugs.** The capability works correctly
across the happy path, three independent tamper paths, and three edge cases.
One low-severity by-design observation (O1) documented as an operator note in
`docs/get-started.md`. Per Rule 12 this is reported as "found zero codebase
issues — verify by spot-reading the run log below," not a silent ✓.

## Stage 0 — Environment doctor

`.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/pytest`, `make`, `git`, and
`codegenie` (`.venv/bin/python -m codegenie --version` → `0.0.1`) all resolve.
`docker` present at `/usr/local/bin/docker` (not needed — no Docker-dependent
finding). The repo idiom is `.venv/bin/<tool>` (no global PATH install);
acceptable, not a finding. The Phase-6 untracked-scratch noise flagged in the
2026-05-25 reports is **gone** — current `git status` shows only `.coverage` +
`.claude/worktrees/` untracked. Clean entry precondition.

## Stage 1 — Capability spec

`codegenie audit verify --runs-dir <dir> --cache-dir <dir> --yaml-path <file>`
is a pure-read verifier (`src/codegenie/audit.py::verify_runs`). For every
`RunRecord` under `runs/`:

- For each probe execution with a non-empty `blob_sha256`: resolve the cache
  index record by `cache_key`, read the blob's **raw** bytes, recompute the
  hash via `codegenie.hashing.identity_hash_bytes`, compare to the recorded
  `blob_sha256`.
- Recompute the whole-output `yaml_sha256` over `repo-context.yaml` and compare.

**Documented exit-code contract:** `0` = no mismatches (verified); `4` = one or
more mismatches (tamper or drift). (click adds its own `2` for an invalid
`--runs-dir` path.)

**Named-event contract (load-bearing — Phase 11/13 subscribe by name; module
docstring §"Audit-event-name contract"):** `audit.verify.ok` (always emitted
once as the summary with the final `mismatch_count` + walk counters — note this
fires *regardless* of mismatch count; it means "verify completed", not "no
mismatches"), `audit.verify.mismatch`, `audit.verify.yaml_mismatch`,
`audit.verify.missing_blob`.

## Stage 2 — Sample app + substrate

Fresh clone of `Dannytrev21/sample-apps`; the committed (stale) `.codegenie/`
under the esbuild fixture was removed and a fresh `codegenie --auto-gitignore
gather` run produced a self-consistent substrate: `cli.end outcome=ok
exit_code=0`, `secrets_redacted_count=2`, `fingerprints=[2bb4ede3, 6f9c56c7]`
(identical to prior gather shakedowns), 1 run-record
(`20260602T010845Z-dc0da04e.json`, 36 probe anchors + `yaml_sha256`), cache
`index.jsonl` + sharded blobs, `repo-context.yaml`.

## Stage 3 + 4 — Runs and findings

Seven invocations against the substrate. A **finding** is one thing
missing/empty/wrong/no-op; this run produced **zero codebase findings** and one
by-design observation.

| # | Path | Command mutation | Result | Verdict |
|---|---|---|---|---|
| A | Happy path | none | `audit.verify.ok mismatch_count=0 probes_walked=36 run_records_walked=1 yaml_anchors_walked=1`, **exit 0** | ✓ correct |
| B | Whole-output tamper | append `# tampered` to `repo-context.yaml` | `audit.verify.yaml_mismatch` (actual≠expected), **exit 4** | ✓ correct |
| C | Per-probe tamper | append a byte to a cache blob | `audit.verify.mismatch probe_name=adrs`, **exit 4** | ✓ correct |
| D | Cache eviction | delete a referenced cache blob | `audit.verify.missing_blob reason=missing_blob_file`, **exit 4** | ✓ correct |
| E | Nonexistent runs-dir | `--runs-dir /tmp/does-not-exist` | click usage error, **exit 2** | ✓ correct (fail-loud) |
| F | Missing YAML | `--yaml-path /tmp/nope.yaml` | `audit.verify.yaml_mismatch reason=yaml_missing actual=`, **exit 4** | ✓ correct |
| G | Empty runs-dir | `--runs-dir <empty existing dir>` | `audit.verify.ok mismatch_count=0 ... run_records_walked=0`, **exit 0** | ⚠ vacuous pass (O1) |

Control re-runs after each tamper returned **exit 0** — the verifier is a pure
read; tampering and restoring is fully reversible and the clean state verifies
identically each time.

The missing-blob path (`_verify_one_blob`, `src/codegenie/audit.py:375`) is
robust across all four sub-cases (no index record / empty alt-hash field /
missing blob file / unreadable blob) — each returns `1` (counted as a mismatch
→ exit 4) with an `audit.verify.missing_blob` event carrying a distinct
`reason`.

## Stage 5 — Diagnosis

**Zero codebase-bug findings.** `audit verify` does exactly what the spec says:
it detects whole-output tamper, per-probe blob tamper, cache eviction, and a
missing YAML anchor, each with the documented exit `4` and a distinct named
event; it fail-loud-rejects a nonexistent `--runs-dir` (click, exit `2`); and
the happy path verifies all 36 probe anchors + the YAML anchor with exit `0`.

**O1 (low severity, by-design) — empty `--runs-dir` is a vacuous pass.**
Pointing `--runs-dir` at an empty-but-existing directory returns exit `0`
"verified" with nothing actually checked (`run_records_walked=0`). This is
standard verify-the-empty-set semantics (an empty set has no mismatches), and
the signal *is* present: the `audit.verify.ok` summary event carries
`run_records_walked` / `probes_walked` / `yaml_anchors_walked`, all `0` in the
vacuous case. The documented exit contract is only `{0=verified, 4=mismatch}` —
there is no "nothing to verify" code, and inventing one (or flipping the empty
case to non-zero) would be an undocumented contract change that the named-event
subscribers (Phase 11/13) and the get-started exit-code table both depend on.
**Route: by-design → document, not code-fix** (safety rail: do not edit a
documented contract autonomously).

A second, even-smaller naming nit (`audit.verify.ok` fires even when
`mismatch_count>0`) is explicitly **by-design** per the module docstring
(line 336: "Always emits exactly one `audit.verify.ok` summary event with the
final `mismatch_count`") — it is a named-event contract, not a bug. Not chased.

## Stage 6 — Fixes

No codebase fix (zero bugs). No sample-app fix (the esbuild fixture is
complete for this capability). No environment fix.

## Stage 7 — Doc sweep

- [`docs/get-started.md`](../get-started.md) — added an operator note under the
  exit-code table documenting O1: `audit verify` on an empty `--runs-dir` exits
  `0` (vacuous pass), and operators should confirm a real verification by
  reading the `run_records_walked` / `probes_walked` / `yaml_anchors_walked`
  counters in the `audit.verify.ok` event.

No ADR amendment needed — the capability matches its design; no architectural
fact changed. No phase-doc / roadmap / story is made stale by this run.

## Stage 8 — Definition of done

- [x] Stage 0 passed; capability + sample app named in the first line
- [x] Capability ran to completion (gather substrate + 7 `audit verify`
      invocations); exit codes + named log events + filesystem state captured
- [x] Every finding has exactly one root-cause class with evidence (O1:
      by-design, evidenced by the documented exit-code contract + emitted
      walk counters)
- [x] Zero codebase-bug findings → no failing-first test required (none would
      go red: every behavior tested is already correct)
- [x] No sample-app or environment findings; the one by-design observation is
      documented in `get-started.md`
- [x] Doc sweep ran (`get-started.md` updated; no ADR/phase/roadmap impact)
- [x] Report written with the Next-run primer
- [x] Wall-clock + token consumption recorded

## Next-run primer

`audit verify` is **verified-correct** — happy path + 3 tamper variants + 3
edges all behave to spec. Remaining never-shaken-down capabilities (from the
prior primer):

- `codegenie vuln-index refresh --source nvd|ghsa|osv` — never shaken-down;
  hits the network (NVD/GHSA/OSV). Best run with a cassette / offline source
  fixture to stay hermetic, or accept the network dependency and flag it.
- `codegenie embeddings bootstrap` — exercised implicitly in the rag-rebuild
  run; never as primary. The model-drift exit-1 path against a tampered cache
  is the obvious target.
- `codegenie self-check egress` — Phase-4 S3-03 operator self-check; reports
  egress-allowlist posture without escalating privilege. Hermetic, never tested.
- `codegenie cassette` subcommands — Phase-4 cassette-discipline surface.

For a future `audit verify` re-run, the untested wrinkle is a **multi-run-record
runs-dir** (>1 `*.json` under `runs/`, exercising the `sorted(glob)` loop and
the per-record YAML-anchor walk with divergent `yaml_sha256` values) and a
**foreign/malformed `.json` artifact** under `runs/` (the `except (OSError,
ValueError): continue` skip-silently branch at `audit.py:349` — confirm it does
not inflate `run_records_walked`).

## Token + wall-clock

- Wall-clock: ~6 minutes (gather + 7 verify runs + source read + doc + report).
- Token consumption: within the per-session budget; surfaced here per Rule 6.
