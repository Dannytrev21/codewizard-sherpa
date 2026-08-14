# Capability shakedown — `codegenie gather`

**Capability:** `codegenie gather` (the primary shipped capability; no capability was named by the caller, so the skill default applied)
**Sample app:** `Dannytrev21/sample-apps :: sample-apps/javascript/npm/esbuild` (fresh shallow clone in the session scratchpad)
**Run date:** 2026-08-14T21:20:46Z
**Mode:** full (fix enabled)
**Result:** 🟡 **5 findings — 1 real codebase bug fixed, 1 doc fixed, 1 confirmed by-design, 2 pre-existing gate failures reported (not fixed)**

> ⚠️ **`make check` is NOT fully green** on this branch. Two tests fail, and
> **both were verified to fail with this shakedown's changes stashed** — they
> are pre-existing, not caused by this run. They are reported, not fixed:
> fixing either is out of this capability's scope and needs a decision that
> is not mine to make autonomously. See §"Entry preconditions".

> **Headline:** the `semgrep` probe (Layer G) has been reporting
> `outcome: skipped (config_absent)` on **every single scan**, on every
> platform, online or offline — and **silently discarding every finding it
> produced**. Root cause: the vacuous-scan check reads `time.rules`, a field
> semgrep only populates when `--time` is passed, which the probe never passed.
> A security probe was returning "I never ran" while holding an
> ERROR-severity match. Fixed, with the finding-loss made structurally
> unrepeatable.

---

## Stage 0 — Environment doctor

| Tool | Status |
| --- | --- |
| `ruff` / `mypy` / `pytest` | ✅ `.venv/bin` |
| `git` / `make` | ✅ |
| `codegenie` | ✅ `python -m codegenie` |
| `semgrep` | ✅ `/opt/homebrew/bin/semgrep` **1.157.0** |

**Environment note (not a capability finding):** `make check` invokes bare
`ruff` / `mypy` / `pytest` from `PATH`, which are only present in `.venv/bin`.
A plain `make check` fails instantly with `make: ruff: No such file or
directory`. The working invocation on this host is:

```bash
PATH="$PWD/.venv/bin:$PATH" make check
```

This is a host-setup ergonomic (no `.venv` auto-activation), not a defect in
the capability. Recorded here so the next run does not re-diagnose it.

## Entry preconditions — `make check` was already red

Per the skill's rule ("`make check` was already red before the skill ran → first
finding is *entry precondition fails*; do not attribute it to the capability"),
both failures below were re-run with this shakedown's edits **stashed** and
failed identically. Full local gate: **2 failed, 7797 passed, 49 skipped,
9 xfailed** (929 s).

### D — `test_phase4_diff_within_allow_list` (pre-existing, not fixed)

`tests/fence/test_phase4_diff_within_allow_list.py` fails with **23 violating
paths**, none of them this shakedown's. They are files from earlier commits
already on this branch — `CLAUDE.md`, `README.md`, `osv-scanner.toml`,
`.pre-commit-config.yaml`, the 2026-07-26 vuln-index shakedown report, and
16 phase-6.5 / phase-7 story + `_validation` docs.

This branch (`ci-health/…`) is a CI-health + story-validation branch, but the
fence gates the diff against a **Phase-4** allow-list. The fence is doing its
job; the branch's scope simply isn't Phase-4 work. Resolving it means either an
ADR-0003 allow-list amendment or re-homing those commits — **a governance
decision, not a shakedown fix.** Left untouched deliberately.

Note this fence appears to gate nothing in CI: it resolves a merge-base against
`master`, and CI's shallow checkout makes that unresolvable, so it takes its
`pytest.skip` path. It is effectively a local-only gate today. Worth a
follow-up, but out of scope here.

### E — the 2-second gather budget is only green in CI because scanners are absent

`tests/adv/test_tsconfig_pathological.py::test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds`
asserts a full `gather` finishes in **< 2.0 s**. Measured on this host:

| Build | Elapsed |
| --- | --- |
| master (no shakedown changes) | **3.89 s** ❌ |
| with this run's `--time` fix | **4.83 s** ❌ |

The budget is blown ~2× **before** any change here. The reason CI is green is
that `.github/workflows/ci.yml` **never installs `semgrep`** — its
"tool-presence preflight" only *prints* `MISSING: semgrep` (line 427) and
proceeds. With semgrep absent, the probe takes the `ToolMissingError` fast path
and never spawns a subprocess. So this timing assertion passes in CI **because
the tool under test isn't installed**, and fails on any properly-provisioned
developer host. That is a green-for-the-wrong-reason gate, and the honest
reading is that the 2 s budget has never actually been validated against a real
scanner.

**Cost of this run's fix, stated plainly:** `--time` adds ≈ **0.9 s** (3.89 →
4.83 s) to gather on this fixture — semgrep profiling overhead. It does not
change CI timing at all (semgrep is not installed there). It does not cause
this failure, but it does make an already-failing local budget worse, and that
is the honest trade for a security probe that previously could not report a
finding at all. Re-baselining the 2 s budget against a provisioned host is a
perf story, not a shakedown fix.

## Stage 1–2 — Prior art + sample app

Prior reports were read first so settled findings were not re-litigated:

- `codegenie-gather-2026-06-04T230525Z.md` — predicted that a re-run before
  Phase 6.5 lands would "reproduce this exact 36-probe baseline". **That
  prediction held exactly: 36 probes, same set.** F1–F4 (`runtime_trace` /
  `sbom` / `cve` / `dep_graph` degradation on macOS) reproduced and remain
  by-design; they were not re-investigated.
- `codegenie-vuln-index-refresh-2026-07-26T000200Z.md` — its Finding B
  (feeds cannot ingest) is still open and out of scope here.

## Stage 3 — The run

```
$ codegenie --no-gitignore gather <sample-app>
EXIT=0            wall clock 6.7 s        36 probes        0 probe errors
```

Artifacts landed as specified: `repo-context.yaml`, `raw/*.json`, and an audit
anchor under `context/runs/`. `secrets_redacted_count=2`.

## Stage 4 — Findings

| # | Finding | Root cause | Outcome |
| --- | --- | --- | --- |
| **A** | `semgrep` reports `skipped / config_absent` with `rules_run: 0` and drops all findings — on *every* scan | codebase-bug | ✅ **fixed** |
| **B** | The repo's own `.semgrep.yml` is ignored; the probe scans with the `p/nodejs` registry pack instead | **by-design** | documented, no code change |
| **C** | `docs/get-started.md` explained finding A's symptom as expected offline behavior — the doc rationalized the bug | doc staleness | ✅ **fixed** |

Everything else in the envelope was honest. `runtime_trace` / `sbom` / `cve`
report unavailable with reasons (macOS, no `strace`); `dep_graph` reports
`confidence: low, reason: no_strategy_for_ecosystem`; `service_topology` /
`slo` / `external_docs` report `opted_in: false`. These are the documented
honest-degradation paths, not defects.

## Stage 5 — Diagnosis

### Finding A — the probe cannot report a semgrep finding at all

`_classify_semgrep_outcome` treats a zero rules-loaded count as a vacuous
scan and returns a skip **with an empty findings list**:

```python
if rules_run == 0:
    return ScannerSkipped(reason="config_absent"), [], rules_run, files_scanned
return ScannerRan(findings=[]), findings, rules_run, files_scanned
```

`rules_run` comes from `_rules_loaded()`, which reads `time.rules`. The
docstring asserted that field is *"present in default `--json` output"*.
**It is not.** semgrep populates `time.rules` only under `--time`, and the
probe's argv never passed it.

Measured directly against semgrep 1.157.0 and the sample app:

| Invocation | `results` | `time.rules` |
| --- | --- | --- |
| `--config p/nodejs --json` (what the probe ran) | 0 | `[]` |
| `--config .semgrep.yml --json` | **1 (ERROR)** | `[]` |
| `--config p/nodejs --json --time` | 0 | **36** |
| `--config .semgrep.yml --json --time` | **1 (ERROR)** | **1** |

So `_rules_loaded()` returned `0` for *every* real scan, the vacuity branch
fired unconditionally, and findings were discarded. Driving the probe's own
classifier with the two real payloads confirms the consequence:

```
== .semgrep.yml (1 REAL ERROR finding)
   semgrep actually reported results: 1
   _rules_loaded() -> 0
   PROBE VERDICT -> ScannerSkipped config_absent | findings kept: 0
```

Two things worth stating plainly:

1. **The `p/nodejs` registry pack was never broken.** With `--time` it loads
   **36 rules**. The "unreachable registry pack / offline" story the code
   comment and the operator docs told was a misreading of a bug whose real
   cause was a missing flag.
2. **This is a deviation from the owning story's spec.** Phase-2 S6-06
   specified `rules_run = len({f.check_id for f in findings})` — derived from
   the findings themselves, and therefore immune to this failure. The
   `time.rules` read and the `config_absent` branch were introduced later
   (the code cites the 2026-05-21 amendment to 02-ADR-0006). The regression
   entered with that change, not with the original story.

### Finding B — repo-local `.semgrep.yml` ignored (by-design)

Confirmed by an explicit written commitment in `docs/get-started.md`:

> "a repo-local `.semgrep.yml` is **not** auto-detected — analyzed-repo
> scanner config is intentionally not trusted."

This is a deliberate supply-chain decision: codegenie analyzes untrusted
repos, so it must not execute rule config authored by the repo under
analysis. **No code change made.** The operator-supported override is
`semgrep_config` in `.codegenie/config.yaml`, which is honored today.

Consequence the operator should know: the sample app's planted
`eval()` in `src/unsafe-demo.js` is caught by its own `.semgrep.yml` but not
by `p/nodejs`, so a clean semgrep slice on this fixture is expected.

### Finding C — the docs rationalized the bug

The `get-started.md` troubleshooting entry attributed `config_absent` to
being offline. An operator who was online and hit it would have been sent
to debug their network for a bug that fires unconditionally.

## Stage 6 — Fixes applied

### Test-gap analysis (why this shipped GREEN)

Every fixture in `tests/unit/probes/layer_g/test_semgrep.py` hand-builds a
`time` block that is **internally consistent** with its findings:

- `..._zero_rules_loaded_is_skipped` → `results: []` **and** `time.rules: []`
- `..._rules_loaded_present_stays_ran` → `results: []` **and** `time.rules: [r1, r2]`

The contradictory combination that real semgrep actually emits —
**findings present while `time.rules` is empty** — was never constructed, so
the suite never questioned its own premise that `time.rules` reflects reality.
The argv test (`..._includes_metrics_off_and_quiet`) asserted flag *membership*
and so happily pinned the buggy invocation. Classic mock-shaped blind spot:
the tests agreed with the code because both were written from the same wrong
assumption about the tool's output.

### Tests added (observed RED first)

In `tests/unit/probes/layer_g/test_semgrep.py`:

1. `test_classify_semgrep_outcome_findings_present_is_never_a_vacuous_skip` —
   the real-semgrep payload shape; asserts a scan with findings is never a
   skip and its findings survive.
2. `test_semgrep_argv_requests_time_so_rules_loaded_is_populated` — pins
   `--time` in the argv, the root cause.
3. `test_semgrep_probe_keeps_findings_when_rules_block_is_empty` — probe-level
   companion pinning the user-visible symptom (`findings_detail` in the slice).

Verified red on the unfixed code:

```
FAILED ...::test_classify_semgrep_outcome_findings_present_is_never_a_vacuous_skip
FAILED ...::test_semgrep_argv_requests_time_so_rules_loaded_is_populated
FAILED ...::test_semgrep_probe_keeps_findings_when_rules_block_is_empty
3 failed, 23 deselected
```

with exactly the predicted symptom
(`SemgrepSlice(outcome=ScannerSkipped(config_absent), findings_detail=[], rules_run=0)`).

### Code fix

`src/codegenie/probes/layer_g/semgrep.py`, two changes:

1. **Root cause** — `--time` added to the argv so `time.rules` carries real data.
2. **Safety invariant** — the vacuity branch is now
   `if rules_run == 0 and not findings:`. A scan that matched something
   demonstrably loaded rules, so a zero count alongside findings means the
   *count* is untrustworthy, not that the scan was vacuous. This is the part
   that makes the finding-loss unrepeatable if semgrep's JSON shape drifts
   again — the fix does not depend on the telemetry field staying correct.

The `_rules_loaded` docstring's false premise was corrected in place.

Both pre-existing vacuity tests still pass unchanged: a genuinely empty scan
(`results: []`, `rules: []`) still reports `skipped / config_absent`, so the
honest-degradation signal 02-ADR-0006 asked for is preserved.

**LOC ceiling:** the first draft of the fix pushed `semgrep.py` to 262 lines
against the 260-line scanner ceiling in
`tests/unit/probes/layer_g/test_scanner_loc_ceiling.py`. The comments were
compressed to 257 rather than raising the ceiling — the fence is a deliberate
complexity conversation-forcer and weakening it to fit commentary would be
the wrong trade.

### Verification — same command, after

```
semgrep slice -> {
  "outcome":       {"kind": "ran", "findings": []},
  "findings_detail": [],
  "rules_run":     36,        # was 0
  "files_scanned": 6          # was 1
}
```

`skipped / config_absent / 0 rules` → `ran / 36 rules / 6 files scanned`.
The probe now reports what actually happened.

### Sibling-probe check

`ast_grep` also has a `config_absent` path, but it is a distinct pre-run
`_ConfigAbsent()` variant decided by config-file presence — sound, and not the
same bug class. `gitleaks`, `ripgrep_curated`, and `test_coverage_mapping` all
reported `ran` on this fixture. **The bug was isolated to `semgrep`.**

## Stage 7 — Doc sweep

| Doc | Action |
| --- | --- |
| `docs/get-started.md` — semgrep troubleshooting entry | ✅ **rewritten.** Keeps the by-design "repo-local config is not trusted" commitment; removes the claim that `config_absent` implies offline; adds an explicit warning that on builds before 2026-08-14 a `config_absent` is untrustworthy and why. |
| `src/codegenie/probes/layer_g/semgrep.py` docstring | ✅ corrected (the "present in default `--json` output" premise was the bug's origin) |
| `docs/phases/02-.../stories/S6-06-layer-g-curated-scanners.md` | ⚠️ **left as-is.** Its §Implementation snippet shows the pre-amendment `rules_run = len({f.check_id for f in findings})` and an argv without `--time`. The story's own ACs were met when it shipped; the regression came in with the later 02-ADR-0006 amendment. Following the precedent set by the 2026-07-26 vuln-index shakedown, a shipped story is not silently re-graded — the deviation is recorded here instead. |
| ADRs | none required. 02-ADR-0006 governs `IndexFreshness` and the `config_absent` *reason*; neither the reason's meaning nor any frozen contract changed. The probe ABC was untouched. |
| `CLAUDE.md` / roadmap | not affected — no architectural commitment changed. |

## Definition-of-done checklist

- [x] Stage 0 passed; capability + sample app named
- [x] Capability ran to completion; exit code, artifacts, logs captured
- [x] Every finding carries exactly one root-cause class with evidence
- [x] Codebase bug: test-gap analysis + tests verified RED→GREEN + minimal fix
- [x] By-design finding documented; no code change
- [x] Doc sweep completed
- [ ] ⚠️ **`make check` NOT green** — 2 failures, both proven pre-existing by
      stashing this run's changes and re-running. No fix attempted: D is a
      governance call (ADR-0003 allow-list) and E is a perf re-baseline; both
      need a human decision or a story. Reported rather than papered over.
- [x] Every test this run added was verified RED before the fix
- [x] Report written

## Next-run primer

1. **The 36-probe baseline still holds** — a `gather` re-run before Phase 6.5
   executes will reproduce it. Don't read that as staleness.
2. **F1–F4 remain by-design on macOS** (`runtime_trace` / `sbom` / `cve` /
   `dep_graph`) — do not chase without Linux + `docker` + `strace` + `syft` +
   `grype`, and a `@register_dep_graph_strategy(PackageManager.NPM)`.
3. **semgrep now reports `ran` with a real `rules_run`.** If a future run
   shows `config_absent` again, first check `semgrep --config <cfg> --json
   --time` by hand before assuming a regression — that combination is now
   meaningful rather than constant.
4. **The `p/nodejs` pack finds nothing on the esbuild fixture.** If you want a
   non-empty semgrep slice for demo purposes, set `semgrep_config` in
   `.codegenie/config.yaml` — do **not** "fix" it by auto-detecting the repo's
   `.semgrep.yml` (Finding B is a deliberate trust boundary).
5. **Still open elsewhere:** vuln-index Finding B (feeds cannot ingest); the
   `S7-10 → S6-06 → S6-04` phase-3/4 blocker chain.
6. **Use `PATH="$PWD/.venv/bin:$PATH" make check`** on this host.
7. **Findings D and E are still open and will fail your `make check`.** Don't
   re-diagnose them: D needs an ADR-0003 allow-list amendment (or the branch's
   non-Phase-4 commits re-homed), E needs the 2 s budget re-baselined against a
   host that actually has `semgrep` installed.
8. **CI does not install `semgrep` / `syft` / `grype` / `gitleaks` / `docker` /
   `strace` / `scip-typescript`** — it only prints `MISSING:` for each. Any
   test asserting on those tools' behavior is passing vacuously in CI. That is
   worth a dedicated audit: this run found one such test (E), and there may be
   more.

## Token + wall-clock

- Wall-clock: ~35 min (CI triage + fix + 2× gather + fix loop + gate + report).
- Token consumption: within session budget; flagged per Rule 6.
