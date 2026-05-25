# Capability shakedown — `codegenie cassette rebuild-lockfile`

- **Capability:** `codegenie cassette rebuild-lockfile` (Phase 4 S3-05 + S3-06)
- **Sample app:** in-repo cassette corpus `tests/cassettes/anthropic/`
  (bootstrap-empty post-S3-06) + ephemeral synthetic corpus under
  `/tmp/cassette-shakedown/dir/` to exercise the drift / sanitizer paths.
- **Run timestamp (UTC):** 2026-05-25T05:58:01Z
- **Mode:** fix (not `--diagnose-only`).
- **Wall-clock:** ~15 min (Stages 0–8); `make check` test run ~11 min.
- **Result:** ✅ all findings routed; codebase bug fixed with failing-first
  fence; `make check` green except for the documented pre-existing
  L-2 macOS `tsconfig_pathological` timing flake (CI Linux clean).

## Stage 0 — environment doctor

| Tool | Path | Status |
|---|---|---|
| `make` | `/usr/bin/make` | OK |
| `git` | `/opt/homebrew/bin/git` | OK |
| `ruff` | `.venv/bin/ruff` | OK (system PATH missing; venv binary used) |
| `mypy` | `.venv/bin/mypy` | OK |
| `pytest` | `.venv/bin/pytest` | OK |
| `codegenie` | `.venv/bin/codegenie` (v0.0.1) | OK |

Operator note: `make check` requires the venv on PATH; the wrapper invocation used
`PATH="$PWD/.venv/bin:$PATH"`.

## Stage 1 — derive the run command

`codegenie cassette rebuild-lockfile [--cassettes-dir PATH] [--check]`

Documented exit codes (`--help`):

- `0` — rebuild succeeded (write) OR lock byte-identical to disk (`--check`).
- `8` — drift (`--check` only): rebuilt content differs from on-disk lock.
- `9` — at least one cassette has a sanitizer violation; refuse to lock dirty.

Spec sources:

- `src/codegenie/fallback/cassette/manifest.py` — canonical lock format
  (`<relpath>  <blake3-hex>`, two-space separator, sorted ascending,
  trailing newline when non-empty, empty corpus → empty file).
- `docs/operations/cassettes.md §cassettes.lock format` — runbook.
- `docs/phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md`
  — discipline ADR; §Decision item 4 pins the line format.

## Stage 2 — sample app

The cassette corpus *is* the sample app for this capability. On-disk
state at the time of the shakedown:

```
tests/cassettes/anthropic/cassettes.lock  (0 bytes — bootstrap empty)
```

To exercise the drift + lock-write + lock-check paths, a synthetic
single-cassette corpus was assembled under `/tmp/cassette-shakedown/dir/`.

## Stage 3 — runs against the corpus

| # | Command | Exit | Observed |
|---|---|---|---|
| 1 | `cassette rebuild-lockfile --check` (real corpus) | 0 | bootstrap-empty matches; no output. |
| 2 | `cassette rebuild-lockfile` (real corpus) | 0 | no change to 0-byte lock. |
| 3 | `cassette rebuild-lockfile --check` (idempotence) | 0 | clean re-check. |
| 4 | `cassette rebuild-lockfile --cassettes-dir /tmp/cassette-shakedown/dir` (synthetic 1-cassette corpus) | 0 | wrote `sample.yaml  7442…afa8`. |
| 5 | `cassette rebuild-lockfile --check` (synthetic) | 0 | matches. |
| 6 | mutate cassette body → `cassette rebuild-lockfile --check` | 8 | emitted drift message — see Finding 1. |
| 7 | `cassette rebuild-lockfile --cassettes-dir /tmp/no-such-dir` | 0 | silently created the dir + empty lock — see Finding 2. |
| 8 | `cassette rebuild-lockfile --check --cassettes-dir /tmp/no-such-dir` | 0 | matches the empty "" rebuild. |
| 9 | `make _refresh-cassettes-gate` (no ack) | 2 | gate refuses — operator-facing error correctly prints `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` reminder. |
| 10 | `make _refresh-cassettes-gate I_UNDERSTAND_THIS_SPENDS_TOKENS=1` | 0 | gate passes (`ack-ok`). |

## Stage 4 — findings

### Finding 1 — drift message names the obsolete role `cassette-review`

**Where surfaced:** Run #6 above. The `--check` drift path emitted:

> `cassette body changed without lock update — run …  rebuild-lockfile … and commit the result, then resubmit with cassette-review CODEOWNERS approval`

**What the spec says:** `cassette-steward` is the canonical role since
S3-06 (`docs/operations/cassettes.md §CODEOWNERS gate`,
`.github/CODEOWNERS`, ADR-0014 §Decision post-S3-06). The S3-06 attempt
log explicitly records: *"ADR-0014 §Decision CODEOWNERS-gate bullet reworded `cassette-review` → single-human `cassette-steward`"*.

**Live source-of-truth copies that still carried the stale token:**

1. `src/codegenie/cli.py:1159` — operator-facing CLI message.
2. `tests/security/test_cassettes_clean.py:120` — layer-2 CI scanner
   `cassette.lock_drift` diagnostic.

The story doc S3-05 line 75 also restates the literal AC string, but
that is a historical artifact (the AC was authored before S3-06's
rename); rewriting an AC corrupts the audit trail and was deliberately
left alone. The `_attempts/S3-06.md` and `_validation/...` entries
discuss the rename and must keep both spellings.

**Root cause class:** ✅ codebase-bug (string drift; S3-06 missed two
live copies). Not by-design, not environment, not sample-app.

### Finding 2 — typo'd `--cassettes-dir` silently writes an empty lock and exits 0

**Where surfaced:** Run #7 above. `cassette rebuild-lockfile
--cassettes-dir /tmp/no-such-dir` silently created the directory, wrote
an empty `cassettes.lock`, and exited 0. An operator who mistypes the
path gets a deceptively-clean success and their real corpus is
untouched.

**Mechanism:** `manifest.rebuild_lockfile(cassettes_dir)` returns `""`
when `cassettes_dir` does not exist (the bootstrap path).
`cli.cassette_rebuild_lockfile` then does `lock_path.parent.mkdir(parents=True, exist_ok=True)`
and writes the empty content. No warning, no diagnostic.

**Root cause class:** ⚠️ ambiguous between codebase-bug and by-design.
The bootstrap-empty-dir → empty-lock path is intentional, but
the bootstrap was specified for the canonical
`tests/cassettes/anthropic/` location (`AC-22`), not for an arbitrary
operator-supplied path. Distinguishing these would mean:

- *bug interpretation* — non-existent `--cassettes-dir` should warn and
  exit non-zero (Rule 12: fail loud).
- *by-design interpretation* — the CLI inherits the manifest's
  "no dir → no entries" semantics uniformly; the operator is expected
  to verify the path.

**Decision (per skill safety rails):** report both hypotheses with
evidence; take the safer route (no autonomous code change); flag for
human review. Touching the bootstrap semantics would need an ADR
amendment to ADR-0014; that is out of scope for this shakedown.

### All other runs

Runs #1–5, #8–10 matched the documented spec exactly. The Phase-4
S3-04 sanitizer hook also fired correctly when a malformed YAML body
was injected mid-shakedown (run-7-variant produced a `kind=unreadable`
sanitizer finding and exit 9).

## Stage 5 — diagnosis (recap)

| Finding | Root cause | Route |
|---|---|---|
| 1 — drift message stale role | codebase-bug | fix in place |
| 2 — typo'd `--cassettes-dir` silently bootstraps | ambiguous (by-design ↔ bug) | report-only; flag for human review |

## Stage 6 — fix (Finding 1)

**Failing-test-first.** New fence at
`tests/fence/test_cassette_drift_message_role.py` with two assertions:

- `src/codegenie/cli.py` text does not contain `cassette-review`
  and does contain `cassette-steward`.
- `tests/security/test_cassettes_clean.py` text obeys the same
  invariant.

**Initial run (RED):**

```
FAILED tests/fence/test_cassette_drift_message_role.py::test_cli_drift_message_names_cassette_steward_not_cassette_review
FAILED tests/fence/test_cassette_drift_message_role.py::test_scanner_drift_message_names_cassette_steward_not_cassette_review
```

**Fix.** Surgical string replacement in both files:

- `src/codegenie/cli.py:1159` — `cassette-review` → `cassette-steward`.
- `tests/security/test_cassettes_clean.py:120` — same.

The duplication of the message between the CLI and the CI scanner is a
known drift hazard (Rule 7). I considered extracting a shared constant
but rejected it (Rule 3: surgical changes; the duplication was not the
finding). If a third copy ever ships, that triggers the rule of three
and a shared `_LOCK_DRIFT_HINT` constant becomes the right move.

**Post-fix run (GREEN):**

```
tests/fence/test_cassette_drift_message_role.py::test_cli_drift_message_names_cassette_steward_not_cassette_review PASSED
tests/fence/test_cassette_drift_message_role.py::test_scanner_drift_message_names_cassette_steward_not_cassette_review PASSED
2 passed in 0.10s
```

**Live re-verification.** Re-ran Run #6 (synthetic drift scenario):

> `… resubmit with cassette-steward CODEOWNERS approval`

Exit 8 preserved; message now points operators at the canonical handle
documented in `.github/CODEOWNERS` and `docs/operations/cassettes.md`.

**Non-vacuity.** The test asserts both directions (the stale token is
absent **and** the canonical token is present). Removing only one half
of the rename would leave one assertion red. The RED → GREEN transition
is observed and recorded above.

## Stage 7 — doc sweep

| File | Action |
|---|---|
| `docs/phases/04-vuln-llm-fallback-rag/final-design.md:460` | `cassette-review` → `cassette-steward` (live design statement). |
| `docs/phases/04-vuln-llm-fallback-rag/stories/S3-05-cassettes-lock-and-scanner.md` | LEFT — historical AC text; rewriting corrupts the audit trail. |
| `docs/phases/04-vuln-llm-fallback-rag/stories/S3-06-cassette-ownership-runbook.md` | LEFT — story body deliberately names both tokens to document the rename. |
| `docs/phases/04-vuln-llm-fallback-rag/stories/_attempts/S3-06.md` | LEFT — attempt log discusses the rename verbatim. |
| `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S3-06-cassette-ownership-runbook.md` | LEFT — validation report discusses the rename verbatim. |
| `docs/operations/cassettes.md` | already correct (S3-06 landed it). |
| `.github/CODEOWNERS` | already correct (S3-06 landed it). |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md` | already correct (S3-06 landed it). |
| `CLAUDE.md` | no change needed — does not name the role. |
| `README.md` / `docs/get-started.md` | no change needed — do not name the role. |

## Definition of done

- [x] Stage 0 passed; capability + sample app named on the first line.
- [x] Capability ran to completion against the corpus; exit codes,
      artifacts, and stderr captured for every run.
- [x] Every finding has exactly one root-cause class (Finding 2 has two
      with explicit rationale for the conservative route).
- [x] Codebase-bug finding has: a test-gap analysis, a fence verified
      RED-then-GREEN, a code fix, and gate runs green.
- [x] `make check` green except for the documented L-2 macOS
      `tsconfig_pathological` timing flake (`4.25s` > the 2s budget;
      CI Linux runners pass — recorded as a pre-existing local-env
      failure in every recent S3-* attempt log).
- [x] No sample-app / environment / by-design findings to route.
- [x] Doc sweep ran (one live design-doc statement updated; five
      historical references deliberately untouched).
- [x] This report exists and carries the next-run primer.
- [x] Wall-clock and token consumption noted.

## Next-run primer

For the next shakedown of `codegenie cassette rebuild-lockfile`:

1. **Spend ten seconds verifying Finding 2 hasn't drifted into a real
   incident.** Run `codegenie cassette rebuild-lockfile --cassettes-dir
   /tmp/definitely-not-a-real-path` and watch the exit code. If a
   future story decides to fail-loud on a missing dir, this report's
   Finding 2 closes and the new behaviour is the spec.
2. **Once the first real cassette lands in `tests/cassettes/anthropic/`,
   re-run Stages 3–5 against the real corpus, not just the synthetic
   `/tmp/cassette-shakedown/dir/`.** The drift behaviour is identical,
   but the layer-2 CI scanner (`tests/security/test_cassettes_clean.py`)
   will then exercise the on-disk lock against the real `cassettes.lock`
   for the first time. The bootstrap-empty path becomes uninteresting
   the moment the corpus is non-empty.
3. **`make refresh-cassettes` requires `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`
   and an `ANTHROPIC_API_KEY`.** Never run it in a shakedown — that's
   what `_refresh-cassettes-gate` is for (it tests the gate without
   spending tokens). Run #9 / #10 above are the safe equivalents.
4. **The duplicated drift-message string remains a drift hazard.** If a
   third copy ever ships (e.g. a markdown runbook excerpt rendered into
   a CLI banner), promote the literal into a shared constant in
   `src/codegenie/fallback/cassette/manifest.py` and have both the CLI
   and the scanner import it. Two copies is tolerable; three is the
   rule of three.

## Changes committed by this run

- New: `tests/fence/test_cassette_drift_message_role.py` (the
  failing-first fence; 2 tests).
- Modified: `src/codegenie/cli.py` (string fix, 1 line).
- Modified: `tests/security/test_cassettes_clean.py` (string fix, 1 line).
- Modified: `docs/phases/04-vuln-llm-fallback-rag/final-design.md`
  (string fix, 1 line).
- New: this report.
