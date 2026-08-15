# Capability shakedown — `codegenie vuln-index refresh`

**Capability:** `codegenie vuln-index refresh` (Phase-3 S3-03)
**Sample input:** the three *live* registered feeds — `ghsa`, `nvd`, `osv`
(this capability's input is the CVE feeds themselves, not a sample repo)
**Run date:** 2026-07-26T00:02:00Z
**Mode:** full (fix enabled)
**Result:** 🔴 **3 findings — 2 fixed, 1 routed to a new story**

> **Headline:** the capability ingested **zero records from every feed** and
> reported **exit 0 (success)**. The story that shipped it is marked
> `Done — GREEN`. The silent-success half is fixed; the underlying
> can't-ingest-anything half is a real implementation gap and is routed.

---

## Stage 0 — Environment doctor

| Tool | Status |
| --- | --- |
| `ruff` / `mypy` / `pytest` | ✅ `.venv/bin` |
| `make` / `git` / `docker` | ✅ |
| `codegenie` | ✅ `.venv/bin/codegenie` |

Network reachability to the feeds was verified explicitly before diagnosis
(`api.osv.dev` → 200, `services.nvd.nist.gov` → 200) so that connectivity could
be *excluded* as a root cause. It was not the problem.

## Stage 3 — The run

```
$ codegenie vuln-index refresh --index-path <scratch>/vi.sqlite
EXIT=0
[info] vuln_index.refresh.completed digest_changed=False errors=3 exit_code=0 \
       inserted=0 skipped=0 source=['ghsa', 'nvd', 'osv']
```

Wall clock ≈ 71 s. Re-running with `--verbose` produced **the same single line** —
the three errors had no detail at any log level.

## Stage 4 — Findings

| # | Finding | Root cause |
| --- | --- | --- |
| **A** | Exit code **0** despite `errors=3, inserted=0` — a run that ingested nothing and errored on everything reported success | codebase-bug |
| **B** | Every record from every feed fails to parse — the capability cannot ingest anything from any real feed | codebase-bug (routed) |
| **C** | Parse failures are counted but never logged; `--verbose` shows no reason | codebase-bug |

## Stage 5 — Diagnosis

Driving the feed objects directly gave the per-feed truth:

| Feed | `chunks` | `ok` | `err` | Error |
| --- | --- | --- | --- | --- |
| `ghsa` | 1 | 0 | 1 | `missing_required_field {'field': 'advisory'}` |
| `nvd` | 1 | 0 | 1 | `payload_too_large {'size': 4258928, 'limit': 1048576}` |
| `osv` | 1 | 0 | 1 | `payload_too_large {'size': 1381993123, 'limit': 1048576}` |

### Finding A — silent success on total failure

`src/codegenie/cli.py`:

```python
exit_code = 4 if (total_errors > 0 and total_inserted > 0) else 0
```

The conjunction is the bug. The all-records-failed case (`errors > 0`,
`inserted == 0`) falls through the `else` to **0**. Exit 4 was only ever
reachable when *something* also succeeded.

**This is a deviation from the story's own spec, not a judgment call.**
`docs/phases/03-…/stories/S3-03-vuln-index-ingest-cli.md:60` specifies:

> `VulnRefreshPartialError=4` (**any per-record parse error**)

"Any per-record parse error" is unconditional — it has no `and at least one
success` qualifier. The shipped conjunction narrowed it. The fix restores the
specified contract rather than inventing a new one.

No caller depends on the old behavior: `grep -rn "vuln-index refresh"` across
`Makefile`, `.github/`, `src/`, and `scripts/` returns only documentation hits.

### Finding B — `fetch()` and `parse_one` disagree on what a "chunk" is

`src/codegenie/vuln_index/feeds/nvd.py`:

```python
with urlopen(url, timeout=timeout_s) as response:
    yield response.read()          # the ENTIRE response body, as one chunk
```

…while `parsers.py:39` caps a chunk at `_MAX_PAYLOAD_BYTES = 1_048_576`.

`fetch()` treats a chunk as *the whole response*; `parse_one` treats it as
*one record*. No feed paginates. Against feeds of 4 MB and 1.38 GB this is a
**guaranteed 100 % failure** — not a flake, not an outage. The capability has
never been able to ingest a record from a real feed.

The 1 MiB cap itself is **correct and deliberate** — S3-03 §Context calls it a
hard cap so "a malformed-or-malicious feed must never crash the parser or
amplify into a memory exhaustion." The cap is not the bug; the monolithic
`fetch()` is. The same story also specifies the *incremental* fetch strategies
that were never implemented:

> "`codegenie vuln-index refresh` pulls NVD JSON 2.0 **delta**, GHSA
> **`since`-cursor**, OSV via **GCS zsync**." — `phase-arch-design.md §C11`,
> quoted at S3-03:38

What shipped is `urlopen(full_url).read()` for all three: no delta, no cursor,
no zsync. So Finding B is a measurable shortfall against the story's own
written spec, not a design ambiguity.

### Finding C — errors invisible

The `errors` list was counted into the summary event and never otherwise
surfaced. Diagnosing A and B required re-driving the feeds by hand in a REPL.

## Stage 6 — Fixes applied

### Test-gap analysis (why this shipped GREEN)

`test_partial_parse_error_exits_4` — the only exit-4 test — registers a
**mixed** feed (`express-min.json` + `malformed-bad_cve.json`): one record
succeeds, one fails. That exercises `errors > 0 AND inserted > 0`, the *true*
branch of the conjunction. **The `inserted == 0` half was never covered.**
Every other feed fixture in the suite is a small, well-formed cassette well
under 1 MiB, so the payload cap never fired in tests either. The suite proved
the happy path and the mixed path, and left the all-fail path — the one real
feeds actually take — untested.

### Tests added (observed RED before the fix)

Both in `tests/integration/cli/test_vuln_index_refresh.py`:

1. `test_all_records_fail_to_parse_does_not_report_success` — asserts
   `exit_code != 0` *first*, so the test states the intent (silently claiming
   success on a total ingest failure is the bug) independently of which code we
   settle on, then pins `== 4`.
2. `test_parse_failures_are_logged_with_reason` — asserts a
   `vuln_index.parse_failed` event exists and carries `source` + `reason`.

Verified red first:

```
FAILED ...::test_all_records_fail_to_parse_does_not_report_success
FAILED ...::test_parse_failures_are_logged_with_reason
2 failed, 12 deselected
```

### Code fix (A + C)

- `exit_code = 4 if total_errors > 0 else 0` — any parse error is now non-zero.
  An empty delta still has `total_errors == 0` and still exits 0.
- A capped `log.warning("vuln_index.parse_failed", source=…, reason=…, details=…)`
  per parse error, bounded by the same `_MAX_ERROR_REPORT` budget
  `ingest_records` uses so a wholly-bad feed cannot flood the log.
- The command's exit-code docstring updated: 4 now reads "at least one record
  failed to parse … covers BOTH a partial refresh and a total parse failure —
  the latter used to exit 0."

### Verification — the same command, after

```
$ codegenie vuln-index refresh --index-path <scratch>/vi3.sqlite
EXIT=4
[warning] vuln_index.parse_failed source=ghsa reason=missing_required_field details={'field': 'advisory'}
[warning] vuln_index.parse_failed source=nvd  reason=payload_too_large details={'size': 4258928, 'limit': 1048576}
[warning] vuln_index.parse_failed source=osv  reason=payload_too_large details={'size': 1381993123, 'limit': 1048576}
[info]    vuln_index.refresh.completed errors=3 exit_code=4 inserted=0 skipped=0
```

The capability still cannot ingest (that is Finding B) — but it now **says so**,
and names why, per feed.

### Finding B — routed, not fixed here

Deliberately **not** fixed inline. It is not a one-line defect: it needs a
decided chunking contract plus three separate per-feed implementations (NVD
`resultsPerPage`/`startIndex` pagination; OSV streaming/decompressing a ~1.4 GB
zip or switching to a per-ecosystem endpoint; GHSA auth + response shape), and
likely an ADR for the `fetch()`/`parse_one` contract. That is a story, and
inventing it mid-shakedown would violate Rule 3. Routed as a task chip with the
full evidence.

**Consequence to be explicit about:** until B lands, `vuln-index refresh`
exits 4 against real feeds. That is the honest report of a capability that does
not work yet — it is not a regression introduced by this shakedown.

## Stage 7 — Doc sweep

| Doc | Action |
| --- | --- |
| `src/codegenie/cli.py` exit-code docstring | ✅ updated (contract now matches behavior) |
| `docs/phases/03-…/stories/S3-03-*.md` | ⚠️ marked `Done — GREEN`; **left as-is** — the story's own ACs were met against its cassette fixtures. The gap is that the ACs never required a real-feed run. Called out here and in the routed task rather than silently re-grading a shipped story. |
| ADRs | none affected — no ADR states the chunking contract, which is itself part of Finding B |

## Definition-of-done checklist

- [x] Stage 0 passed; capability + input named
- [x] Capability ran to completion; exit code, artifacts, logs captured
- [x] Every finding has exactly one root-cause class with evidence
- [x] Each fixed codebase bug has a test-gap analysis + a test verified
      fail-then-pass + a code fix
- [x] Finding B routed with full evidence rather than half-fixed
- [x] Doc sweep run
- [x] Gates: `ruff` ✅ · `mypy --strict` (254 files) ✅ · `pre-commit run
      --all-files` ✅ · `pytest` **7792 passed, 1 pre-existing failure**

### Gate detail — one honest exception

`tests/adv/test_tsconfig_pathological.py::test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds`
fails on this machine (2.6 s–5.5 s against a 2.0 s wall-clock budget) and is
**pre-existing and unrelated** to this shakedown. Evidence it is not caused by
anything in this change set:

- It is a wall-clock perf assertion, and CI's `test` job passes it — the last
  green run on `ae6b064` included `tests/adv/`.
- Nothing in this change set touches `gather`. The only runtime changes were
  dependency bumps, and `codegenie.cli` imports **none** of the bumped packages
  — verified directly: loading the CLI and intersecting `sys.modules` against
  `{aiohttp, cryptography, msgpack, PIL, vcr, starlette, pymdownx, keyring}`
  returns the empty set.

It is reported here rather than silently omitted (Rule 12). It is **not** being
"fixed" by widening the threshold — the budget is a deliberate advisory that CI
meets.

One self-inflicted issue was caught by the gates and fixed: removing the two
`IgnoredVulns` entries left `osv-scanner.toml` without its EOF newline;
`end-of-file-fixer` flagged it and `pre-commit run --all-files` now exits 0.

## Next-run primer

- **Do not re-litigate:** A and C are fixed; exit 4 against live feeds is now the
  *correct* observed behavior, not a new finding.
- **Start here:** re-run this capability once the routed pagination story lands.
  Success criterion: `inserted > 0` and exit 0 against at least the `nvd` feed.
- **Still unshaken-down:** `codegenie self-check`, `codegenie embeddings`,
  `codegenie cache`.
- **Watch:** `ghsa` may need a `GITHUB_TOKEN`; if so that is an *environment*
  finding next run, not a codebase one.
