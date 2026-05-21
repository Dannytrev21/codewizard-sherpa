# Story S19-01 — Re-apply the Layer C raw-sidecar publishing fix + kernel-allowlist amendment

**Step:** Step 19 — Layer C raw-sidecar publishing (regression rescue, 2026-05-21; post-Amendment-A remediation, not part of the original 18-step DAG)
**Status:** Ready
**Effort:** S
**Depends on:** none — implementable against current `master`. (Forward dependency, *not* a precondition: when Phase 7 story S5-01 lands `tests/fence/test_phase7_no_byte_edits_to_locked_files.py`, that fence must also enumerate the eight files this story edits — see Notes.)

**ADRs honored:** [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) (this story is the **canonical implementer** — re-apply commit `5055292`, widen `_KERNEL_ALLOWLIST`, land the regression-guard integration test); [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (the kernel-frozen fence whose `_KERNEL_ALLOWLIST` this story amends — the audit-and-lint `git`-diff gate); [Phase 2 ADR-0006](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) (the `ScannerSkipped.reason` `config_absent` value the semgrep change reuses — §Amendment 2026-05-21); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) (the Phase 7 byte-edit allowlist fence — a forward dependency this story flags, does **not** satisfy); [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) (extension by addition; a genuinely cross-cutting kernel edit uses the sanctioned loud, ADR-gated path — never a silent edit).

## Context

The five Layer C marker probes — `entrypoint`, `shell_usage`, `certificate`, `sbom`, `cve` — read upstream evidence from `.codegenie/context/raw/<name>.json` sidecars via `codegenie.probes.layer_b.index_health.read_raw_slices`. That pattern works **only if the upstream probe persists its sidecar**. Two producers — `DockerfileProbe` and `RuntimeTraceProbe` — never did: they returned `raw_artifacts=[]` and wrote nothing under `raw/`. The result is silent and total: every consumer emits `confidence: "unavailable"` on **every** gather, on **every** platform. `entrypoint` declares `.codegenie/context/raw/dockerfile.json` and finds nothing; `certificate` declares `.codegenie/context/raw/runtime_trace.json` and finds nothing.

This is the project's worst-named failure mode — **honest confidence** ("silent index staleness is the worst failure mode") and **facts, not judgments**. A probe that always says `unavailable` is dead, not honest. The blast radius reaches the Phase 7 migration task class directly: the distroless-migration plugin's `DockerfilePolicyGate`, the Dockerfile recipe engines, `RuntimeShellInvocationProbe` blast-radius analysis, and `TargetImageContentProbe` all consume Layer C container evidence — every one of them degrades to `unavailable` while the bug stands.

**What was already done, and reverted.** Commit `5055292` ("fix(probes/layer_c): publish raw sidecars so marker probes see upstream evidence") fixed it correctly. It was reverted by `7f6a009` because it byte-edited **eight Phase 0/1/2 kernel probe files** without an `_KERNEL_ALLOWLIST` entry. `tests/fence/test_kernel_frozen.py` ([Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md)) diffs a pinned `_phase2_baseline.txt` SHA against `HEAD`; it only sees *committed* history, so `make check` passed while the change sat uncommitted, then CI went red the instant it landed. The revert message recorded the redo instruction this story executes: "redoing — but as a Phase 7 story with a proper ADR amendment widening `_KERNEL_ALLOWLIST`, not as a silent kernel edit."

The kernel-frozen fence is **designed to be extended this way**. Its own failure message says: "Either add the file to the allowlist (with an `# adr:` comment) via ADR amendment, or revert the change." [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) is that amendment; this story implements it.

**Why no existing test caught the bug** — three structural reasons, each one a reason the regression-guard test this story lands must *not* later be deleted as redundant:

1. **Consumer unit tests fabricate their own upstream.** Each Layer C consumer's unit test writes `raw/<name>.json` by hand before running the probe. The producer↔consumer seam was never exercised as a pair.
2. **The portfolio golden test snapshotted the broken output.** It runs a full gather, but its committed goldens recorded the broken `confidence: "unavailable"` slice as the expected baseline. A golden detects *drift*, not *wrongness* — a broken baseline passes forever.
3. **The smoke fixtures have no Dockerfile.** No smoke fixture lets a Layer C container probe produce real output, and the structural smoke check treats `skipped` / empty slices as first-class — it catches *exceptions*, not *silent emptiness*.

This story re-applies the fix, makes the kernel edit loud and ADR-reviewed, and lands the integration test that closes the seam permanently.

## References — where to look

- **The fix itself — the source of truth:**
  - `git show 5055292` — the verbatim diff to re-apply. Touches eight kernel files (`src/codegenie/probes/layer_c/{certificate,cve,dockerfile,entrypoint,runtime_trace,sbom,shell_usage}.py`, `src/codegenie/probes/layer_g/semgrep.py`), plus non-kernel `tests/` (unit tests + goldens) and `docs/get-started.md`. `git revert --no-commit 7f6a009` reproduces exactly that diff mechanically (it reverts the revert) — use whichever is cleaner, but `git show 5055292` is the canonical reference.
- **ADRs — primary sources of truth:**
  - `../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md` §Decision — the three parts of this story (re-apply `5055292`; widen `_KERNEL_ALLOWLIST` with the eight-file block; land the integration test). Read cover-to-cover.
  - [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) — the kernel-frozen fence's owning ADR; the "audit + lint, not a runtime guarantee" framing and the "add the file to the allowlist via ADR amendment" path.
  - [Phase 2 ADR-0006](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) §Amendment 2026-05-21 — the `config_absent` `ScannerSkipped.reason` value the semgrep change emits on a vacuous scan.
- **Existing code / precedents — read before editing:**
  - `tests/fence/test_kernel_frozen.py` — **read `_KERNEL_ALLOWLIST` (≈ lines 45–235) in full.** Note the grouped-block convention: a single `# adr:` comment can precede several `Path(...)` entries (the `ast_grep` / `scanner_outcome.py` group at lines ≈219–233 is the precedent for one comment over multiple paths). Note `_KERNEL_SCOPE_DIRS` includes `src/codegenie/probes` — all eight files are in scope.
  - `src/codegenie/probes/layer_b/index_health.py::read_raw_slices` — the consumer-side reader; confirms the `raw/<name>.json` contract.
  - `src/codegenie/probes/layer_c/entrypoint.py` (`declared_inputs = [".codegenie/context/raw/dockerfile.json"]`) and `certificate.py` (`declared_inputs = [".codegenie/context/raw/runtime_trace.json"]`) — the declaring consumers the integration test enumerates.
  - `src/codegenie/output/paths.py::raw_dir` — the `raw/` directory resolver the `5055292` `_write_files` helpers call.
- **Story-pipeline neighbors:**
  - `S5-01-phase7-byte-edit-allowlist-fence.md` — the Phase 7 byte-edit fence. **Not a dependency of this story**, but its implementer must enumerate the eight files this story edits (see Notes / Out of scope). [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) §Consequences flags this.

## Goal

Restore honest Layer C marker-probe confidence by re-applying commit `5055292` verbatim — `DockerfileProbe` and `RuntimeTraceProbe` persist their `raw/<name>.json` sidecars; the five consumers register `runs_last=True`; `SemgrepProbe` reports an honest `config_absent` skip on a vacuous scan. Make the eight-file kernel edit **loud and ADR-reviewed** by widening `_KERNEL_ALLOWLIST` in `tests/fence/test_kernel_frozen.py` with the eight files, each authorized by [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) via an inline `# adr:` comment. Land the regression-guard integration test `tests/integration/test_layer_c_sidecar_contract.py` so the producer↔consumer seam can never silently break again. End state: `make check` (lint → typecheck → test → fence) fully green.

## Acceptance criteria

**Fix re-applied — verbatim `5055292` (AC-1 through AC-6)**

- [ ] **AC-1** `DockerfileProbe.run` writes `.codegenie/context/raw/dockerfile.json` on **every** exit path — both the marker-absent path (`dockerfiles: []`, `confidence: "unavailable"`) and the parsed path (`confidence: "high"`). The sidecar `Path` is included in the returned `ProbeOutput.raw_artifacts`. Verified by `tests/unit/probes/layer_c/test_dockerfile.py::test_dockerfile_probe_publishes_raw_slice_for_sibling_readers` and `::test_dockerfile_probe_publishes_raw_slice_when_marker_absent` (both from the `5055292` diff).
- [ ] **AC-2** `RuntimeTraceProbe` routes **all five** `run()` exit paths (yaml-malformed, image-digest-unresolved, macOS-degraded, all-builds-failed, success) through a single `_finalize()` chokepoint that writes `raw/runtime_trace.json` and prepends it to `raw_artifacts`. Verified by `tests/unit/probes/layer_c/test_runtime_trace.py::test_runtime_trace_success_publishes_typed_raw_slice_for_sbom` and `::test_runtime_trace_publishes_raw_slice_on_degraded_paths` (both from `5055292`) — the latter asserts the sidecar exists and carries `trace_coverage_confidence: "unavailable"` / `built_image_digest: None` on the macOS path.
- [ ] **AC-3** `entrypoint`, `shell_usage`, `certificate`, `sbom`, `cve` are all registered `runs_last=True` (`@register_probe(..., runs_last=True)`), so they dispatch after their sidecar producers. `IndexHealthProbe` (B2) still dispatches in the `runs_last` tail after every prelude probe whose freshness it checks — verified by the relaxed `test_index_health_probe.py::test_sorted_for_dispatch_places_b2_in_runs_last_tail` (from `5055292`): `b2_idx >= non_runs_last_count` and `entries[b2_idx].runs_last is True`.
- [ ] **AC-4** `SemgrepProbe` counts rules from `time.rules` (rules *loaded*), not from distinct finding `check_id`s. A scan that loaded zero rules (`time.rules == []`) is classified `ScannerSkipped(reason="config_absent")` with `confidence == "low"` and **no** raw artifact written — a vacuous scan is reported as an honest skip, not a misleading clean result. Verified by `tests/unit/probes/layer_g/test_semgrep.py::test_classify_semgrep_outcome_zero_rules_loaded_is_skipped`, `::test_classify_semgrep_outcome_rules_loaded_present_stays_ran`, and `::test_semgrep_zero_rules_loaded_yields_low_confidence_skip` (all from `5055292`).
- [ ] **AC-5** The `5055292` golden-file updates are applied: `tests/golden/probes/entrypoint/{distroless-target,minimal-ts,monorepo-pnpm}.json` and the matching `shell_usage` goldens move off the broken `unavailable` baseline (they now record the parsed-Dockerfile slice); `certificate` goldens are updated as in the diff. `docs/get-started.md` gains the `5055292` FAQ entries (runtime_trace/sbom/cve macOS degradation cascade; semgrep `config_absent` skip).
- [ ] **AC-6** The full `5055292` diff is re-applied — no file from `git show 5055292 --stat` is omitted, no extra file is changed. Verified by inspection: `git show 5055292 --stat` lists 32 files; the re-applied change touches the same 32 (the eight kernel probe files, the `tests/` unit tests + goldens, `docs/get-started.md`).

**Kernel-allowlist amendment (AC-7 through AC-9)**

- [ ] **AC-7** `_KERNEL_ALLOWLIST` in `tests/fence/test_kernel_frozen.py` gains **exactly eight** new `Path(...)` entries — `src/codegenie/probes/layer_c/{dockerfile,runtime_trace,entrypoint,shell_usage,certificate,sbom,cve}.py` and `src/codegenie/probes/layer_g/semgrep.py` — as a single grouped block preceded by an inline `# adr:` comment that names `docs/phases/07-migration-task-class/ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md` and one-line-summarizes why (re-applies `5055292`; producers publish sidecars; consumers `runs_last=True`).
- [ ] **AC-8** `tests/fence/test_kernel_frozen.py::test_phase3_has_not_modified_phase012_kernel_outside_allowlist` is **green**, and `make fence` exits 0. Before the AC-7 amendment (but after AC-1–AC-6) this test is **red** with the eight files listed as violations — that red is captured in the attempt log as evidence the amendment is load-bearing.
- [ ] **AC-9** The only change to `tests/fence/test_kernel_frozen.py` is the eight-entry block + its `# adr:` comment — no existing allowlist entry is edited or reordered, the `_KERNEL_SCOPE_DIRS` / `_TOP_LEVEL_PHASE3_PACKAGES` / fence logic is untouched. (`test_kernel_frozen.py` is under `tests/fence/`, outside kernel scope — editing it is itself not a kernel violation.)

**Regression-guard integration test (AC-10 through AC-13)**

- [ ] **AC-10** `tests/integration/test_layer_c_sidecar_contract.py` exists, with the three recovered tests (full source in the Appendix below — reproduce it verbatim): `test_declared_raw_sidecar_inputs_are_produced_by_a_gather`, `test_dockerfile_consumers_populate_on_real_gather`, `test_runtime_trace_consumer_populates_on_real_gather`, plus the `_make_dockerfile_repo`, `_gather`, and `_declared_raw_sidecars` helpers.
- [ ] **AC-11** `test_declared_raw_sidecar_inputs_are_produced_by_a_gather` — **structural contract.** It enumerates every `.codegenie/context/raw/<name>.json` token in any registered probe's `declared_inputs` (via the `_RAW_SIDECAR_TOKEN` regex), runs a real `codegenie gather` against a repo *with* a Dockerfile, and asserts every such sidecar is actually written to `raw/`. It also asserts `{"dockerfile", "runtime_trace"} <= required` so the catch-all cannot pass vacuously if a future refactor drops the declared inputs. This case auto-extends — any future probe declaring a raw sidecar input is checked for free.
- [ ] **AC-12** `test_dockerfile_consumers_populate_on_real_gather` — **behavioural contract.** After a real gather of a Dockerfile repo, `probes.entrypoint.entrypoint.confidence != "unavailable"`, `entrypoint.entrypoints` is non-empty with `entrypoints[0].form == "exec"`, and `probes.shell_usage.shell_usage.static.final_stage_entrypoint_form == "exec"` with a non-empty `final_stage_run_commands`.
- [ ] **AC-13** `test_runtime_trace_consumer_populates_on_real_gather` — **behavioural contract.** After a real gather of a Dockerfile repo, `probes.certificate.certificate.confidence != "unavailable"` — proving `certificate` consumed a real `runtime_trace` sidecar rather than a phantom missing file. (On macOS the underlying trace is platform-degraded, but `certificate` must still reach a non-`unavailable` confidence — the `_finalize()` sidecar is written on the degraded path too.)
- [ ] **AC-14** All three integration tests **fail on pre-fix `master`** and **pass after the fix**. Demonstrate by running `tests/integration/test_layer_c_sidecar_contract.py` *before* re-applying `5055292` (expect three reds — sidecars absent, consumers `unavailable`) and *after* (expect three greens). Record both runs in `_attempts/S19-01.md`. This is the proof the test is a real oracle, not a tautology (Rule 9).

**Gates (AC-15)**

- [ ] **AC-15** `make check` (lint → typecheck → test → fence) is fully green: `ruff check` + `ruff format --check` clean, `mypy --strict src/` clean, the pytest suite green (including the new integration test), `make fence` exit 0. `make lint-imports` green — no LLM SDK enters the runtime closure (the fix is pure deterministic probe code). The integration test runs inside the standard `make check` test lane and is **not** swept into the bwrap-gated integration-test xfail set (it needs no `bwrap` — only a `codegenie gather`).

## Implementation outline

1. **Read first (Rule 8).** `git show 5055292` in full; `tests/fence/test_kernel_frozen.py` `_KERNEL_ALLOWLIST` cover-to-cover (note the grouped-`# adr:`-comment convention); [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) §Decision.

2. **Capture the pre-fix red (AC-14, first half).** Create `tests/integration/test_layer_c_sidecar_contract.py` from the Appendix. Run it against current `master` — expect three failures (`raw/dockerfile.json` / `raw/runtime_trace.json` never produced; `entrypoint`/`shell_usage`/`certificate` all `unavailable`). Paste the failure output into `_attempts/S19-01.md`.

3. **Re-apply commit `5055292` (AC-1–AC-6).** `git revert --no-commit 7f6a009` is the mechanical reproduction (it reverts the revert); or apply `git show 5055292` directly. Resolve any trivial context drift from commits landed after the revert (`60257fa`…`921c5c4` are docs-only and do not touch Layer C — expect a clean apply). Confirm all 32 files from `git show 5055292 --stat` are present in the working tree.

4. **Verify the fix turned the integration test green (AC-14, second half).** Re-run `tests/integration/test_layer_c_sidecar_contract.py` — expect three greens. Paste into `_attempts/S19-01.md`.

5. **Observe the kernel fence go red (AC-8 evidence).** Run `make fence` (or `pytest tests/fence/test_kernel_frozen.py`). `test_phase3_has_not_modified_phase012_kernel_outside_allowlist` fails, listing the eight Layer C/G files as violations. This is the *expected* red — the fence is correctly strict and has not yet been amended. Record it.

6. **Amend `_KERNEL_ALLOWLIST` (AC-7, AC-9).** Add the eight-file block to the `_KERNEL_ALLOWLIST` frozenset, preceded by one `# adr:` comment block (one comment, eight `Path(...)` lines — mirror the `ast_grep` / `scanner_outcome.py` grouped precedent). Do not touch any existing entry. See the exact block in the TDD plan / Appendix.

7. **Re-run the gates (AC-15).** `make fence` exit 0; `make check` fully green. If `mypy --strict` or `ruff` flags anything, it is drift from the `5055292`-era tree — fix it minimally and note it in `_attempts/S19-01.md`.

8. **Confirm the integration test placement (AC-15).** Verify `tests/integration/test_layer_c_sidecar_contract.py` is collected and run by `make check`'s `pytest` invocation and is not caught by any `bwrap`-conditional xfail/skip marker applied to `tests/integration/`.

## TDD plan — red / green / refactor

This story is a verbatim re-application of a reviewed, known-good commit, so the "write a failing test first" discipline is satisfied by the **recovered integration test** acting as the end-to-end oracle, plus the `5055292` unit tests it carries.

**Red 1 — the integration oracle.** Land `tests/integration/test_layer_c_sidecar_contract.py` (Appendix) on un-fixed `master`. All three tests fail: `test_declared_raw_sidecar_inputs_are_produced_by_a_gather` (the `raw/dockerfile.json` + `raw/runtime_trace.json` sidecars are never written), `test_dockerfile_consumers_populate_on_real_gather` (`entrypoint` is `unavailable`), `test_runtime_trace_consumer_populates_on_real_gather` (`certificate` is `unavailable`). This is the correct red — the producer↔consumer seam is broken.

**Green 1 — re-apply the fix.** Re-apply `5055292`. The integration test goes green; the `5055292` unit tests (`test_dockerfile.py`, `test_runtime_trace.py`, `test_semgrep.py`, `test_index_health_probe.py`) go green; the updated goldens match.

**Red 2 — the kernel fence.** With the eight kernel files now edited, `tests/fence/test_kernel_frozen.py::test_phase3_has_not_modified_phase012_kernel_outside_allowlist` fails — it diffs the `_phase2_baseline.txt` SHA against `HEAD` and finds eight in-scope, non-allowlisted files. Correct red: the fence is doing its job; the edit is loud, not silent.

**Green 2 — amend the allowlist.** Add the eight-file block to `_KERNEL_ALLOWLIST`:

```python
        # ADR-0030 — Layer C raw-sidecar publishing fix. The five Layer C
        # marker probes (entrypoint, shell_usage, certificate, sbom, cve)
        # read upstream evidence from raw/<name>.json sidecars via
        # read_raw_slices(); the dockerfile + runtime_trace producers never
        # wrote them, so every consumer emitted confidence="unavailable" on
        # every gather. Re-applies reverted commit 5055292: producers persist
        # their sidecar on every run() exit; the five consumers register
        # runs_last=True so they dispatch after the producers; semgrep counts
        # loaded rules and reports an honest config_absent skip on a vacuous
        # scan. adr: docs/phases/07-migration-task-class/ADRs/
        # 0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md
        Path("src/codegenie/probes/layer_c/dockerfile.py"),
        Path("src/codegenie/probes/layer_c/runtime_trace.py"),
        Path("src/codegenie/probes/layer_c/entrypoint.py"),
        Path("src/codegenie/probes/layer_c/shell_usage.py"),
        Path("src/codegenie/probes/layer_c/certificate.py"),
        Path("src/codegenie/probes/layer_c/sbom.py"),
        Path("src/codegenie/probes/layer_c/cve.py"),
        Path("src/codegenie/probes/layer_g/semgrep.py"),
```

`make fence` exits 0. The fence's `test_diff_status_classification` and `test_helpful_error_*` cases are unaffected — they use synthetic diffs, not the live one.

**Refactor.** Run the full `make check`. Confirm no allowlist entry other than the eight new ones changed (`git diff tests/fence/test_kernel_frozen.py` shows exactly the block). Confirm `git show 5055292 --stat` and the working-tree change cover the same 32 files. Update the story `Status` to `GREEN`.

## Files to touch

**New files:**

| Path | Purpose |
|---|---|
| `tests/integration/test_layer_c_sidecar_contract.py` | The recovered regression-guard integration test (AC-10–AC-14). Full source in the Appendix. |
| `docs/phases/07-migration-task-class/_attempts/S19-01.md` | Append-only attempt log — record the pre-fix red, the post-fix green, the fence red→green, and any `5055292`-era drift fixed. |

**Re-applied from commit `5055292` (the verbatim fix):**

| Path | Edit | Authorizing ADR |
|---|---|---|
| `src/codegenie/probes/layer_c/dockerfile.py` | `_write_files` helper; writes `raw/dockerfile.json` on every `run()` exit | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/runtime_trace.py` | `_finalize()` chokepoint; writes `raw/runtime_trace.json` on all five exits | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/entrypoint.py` | `@register_probe(..., runs_last=True)` | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/shell_usage.py` | `@register_probe(..., runs_last=True)` | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/certificate.py` | `@register_probe(heaviness="light", runs_last=True)` | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/sbom.py` | `@register_probe(heaviness="medium", runs_last=True)` | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_c/cve.py` | `@register_probe(heaviness="medium", runs_last=True)` | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) |
| `src/codegenie/probes/layer_g/semgrep.py` | `_rules_loaded` (counts `time.rules`); `config_absent` skip on a vacuous scan | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) / [Phase 2 ADR-0006](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) |
| `tests/unit/probes/layer_c/test_{dockerfile,runtime_trace,certificate,cve,entrypoint,sbom,shell_usage}.py` | the `5055292` unit-test additions | (tests — outside kernel scope) |
| `tests/unit/probes/layer_b/test_index_health_probe.py` | relaxed B2 dispatch test | (tests — outside kernel scope) |
| `tests/unit/probes/layer_g/test_semgrep.py` | the `5055292` semgrep tests | (tests — outside kernel scope) |
| `tests/unit/probes/test_coordinator_threads_probe_context_parity.py` | the `5055292` parity-test update | (tests — outside kernel scope) |
| `tests/golden/probes/{entrypoint,shell_usage,certificate}/*.json` | goldens move off the broken `unavailable` baseline | (goldens — outside kernel scope) |
| `docs/get-started.md` | FAQ: macOS degradation cascade; semgrep `config_absent` skip | (docs — outside kernel scope) |

**Edited (the amendment):**

| Path | Edit | Authorizing ADR |
|---|---|---|
| `tests/fence/test_kernel_frozen.py` | `_KERNEL_ALLOWLIST` gains the eight-file block + one `# adr:` comment | [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) (`tests/fence/` is outside kernel scope — editing it is not itself a kernel violation) |

## Out of scope

- **The Phase 7 byte-edit allowlist fence** (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`, [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md)). That fence **does not exist yet** — it is landed by Phase 7 story S5-01, which is unimplemented. This story cannot add a row to a file that does not exist (that would be the silent drift the discipline forbids). When S5-01 lands that fence, its allowlist must enumerate the eight files this story edits — [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) §Consequences flags the dependency and S5-01 must consult it. **Do not** scaffold an `_AMENDMENT_*` seam or pre-create that fence here.
- **Re-designing the sidecar contract.** This story re-applies `5055292` verbatim — it does not introduce a typed `Sidecar` abstraction, a registry of sidecar producers, or a coordinator-level dependency declaration. Those are legitimate future refactors but are not this regression rescue (Rule 2, Rule 3).
- **`High-level-impl.md` / `phase-arch-design.md` edits.** This is a post-Amendment-A remediation, not a new design step. The phase architecture docs are not rewritten; only the stories README and ADRs README indices gain a pointer.
- **The portfolio golden test's broken baseline.** `5055292` already updates the affected `entrypoint`/`shell_usage`/`certificate` goldens. If the *portfolio*-level golden snapshot also encodes `unavailable` for these probes, re-applying `5055292` updates whatever goldens its diff covers; auditing every portfolio golden for further stale `unavailable` slices is a separate `phase-shakedown` concern, not this story.
- **`sbom` / `cve` `declared_inputs`.** Those probes consume the `runtime_trace` evidence by reading the raw file directly, not via a `raw/<name>.json` `declared_input` token, so they are outside the integration test's `_declared_raw_sidecars()` enumeration. `5055292` still registers them `runs_last=True` (AC-3); no further change is in scope.

## Notes for the implementer

- **Rule 3 — surgical changes.** The `_KERNEL_ALLOWLIST` amendment is exactly eight `Path(...)` lines + one `# adr:` comment block. Do not reformat the frozenset, reorder existing entries, or "tidy" neighbouring comments. `git diff tests/fence/test_kernel_frozen.py` must show only the added block.
- **Rule 8 — read before you write.** The `5055292` diff was reviewed and is known-good; re-apply it *verbatim*. Do not "improve" the `_finalize()` chokepoint or the `_write_files` helpers while re-applying. If `mypy --strict` or `ruff` rejects the re-applied code because the surrounding tree drifted since the revert, fix the *drift* minimally — do not redesign the fix.
- **Rule 12 — fail loud.** AC-14 is the load-bearing assertion: the integration test must **fail on pre-fix `master`** and **pass after**. A regression test that was never observed red is not an oracle — it could be a tautology. Run it both ways and paste both outputs into `_attempts/S19-01.md`. Likewise AC-8: observe the kernel fence go red *before* amending the allowlist — that red is the evidence the amendment is load-bearing rather than decorative.
- **Rule 9 — tests verify intent.** The integration test's `test_declared_raw_sidecar_inputs_are_produced_by_a_gather` asserts `{"dockerfile", "runtime_trace"} <= required` *before* checking production. That guard is deliberate — without it, a future refactor that drops the `declared_inputs` tokens would make the catch-all pass vacuously (nothing required → nothing missing). Keep it.
- **The integration test needs no `bwrap` and no Docker.** It runs `codegenie gather` via `CliRunner`; `RuntimeTraceProbe` degrades gracefully on a non-Linux / no-Docker host and *still writes its sidecar* via `_finalize()` — that is the whole point of the fix, and is why `test_runtime_trace_consumer_populates_on_real_gather` asserts `certificate` reaches non-`unavailable` even on the degraded path. Ensure the test is collected by `make check` and not caught by any `bwrap`-conditional skip applied to `tests/integration/`.
- **Rule 7 — surface conflicts.** If `git revert --no-commit 7f6a009` does not apply cleanly (a commit after the revert touched a Layer C probe), stop, do not blend — re-apply `git show 5055292` hunk-by-hunk, resolve the genuine conflict, and record the resolution in `_attempts/S19-01.md`.
- **Forward dependency, not a blocker.** S5-01 (the Phase 7 byte-edit fence) does not need to exist for this story to ship — `test_kernel_frozen.py` is the only fence live today. Just make sure [ADR-0030](../ADRs/0030-amend-kernel-allowlist-for-layer-c-sidecar-publishing.md) §Consequences' forward-dependency note survives, so S5-01's implementer enumerates these eight files.

## Appendix — `tests/integration/test_layer_c_sidecar_contract.py` (verbatim)

Reproduce this file exactly. It is the regression-guard integration test recovered from the `2026-05-21` working tree.

```python
"""End-to-end regression guard for the Layer C sibling-slice contract.

WHY THIS FILE EXISTS — the gap it closes
----------------------------------------
Layer C marker probes (``entrypoint``, ``shell_usage``, ``certificate``)
consume an upstream probe's slice from ``.codegenie/context/raw/<name>.json``
via :func:`~codegenie.probes.layer_b.index_health.read_raw_slices`. That
pattern only works if the upstream probe actually *persists* that sidecar.
Two upstream probes — ``dockerfile`` and ``runtime_trace`` — historically did
not (they returned ``raw_artifacts=[]`` and wrote nothing to ``raw/``), so
every consumer was silently dead on every gather, on every platform: each
emitted ``confidence: "unavailable"`` forever.

No existing test caught it, for three structural reasons:

1. **Consumer unit tests fabricate their own upstream.** Each consumer's
   unit test writes ``raw/<name>.json`` by hand before running the probe
   (e.g. ``tests/unit/probes/layer_c/test_entrypoint.py::_write_dockerfile_slice``).
   The producer<->consumer seam was therefore never exercised as a pair —
   the consumer was always handed a fabricated sidecar.
2. **The portfolio golden test snapshotted the broken output.** It runs a
   full gather, but its committed goldens recorded the broken
   ``confidence: "unavailable"`` slice as the expected baseline. A golden
   detects *drift*, not *wrongness* — a broken baseline passes forever.
3. **The smoke fixtures have no Dockerfile.** ``empty_repo`` / ``js_only`` /
   ``polyglot`` never let a Layer C container probe produce real output, and
   the one structural smoke check (``test_no_probe_errors_in_smoke_run_record``)
   treats ``skipped`` / empty slices as first-class — it only catches
   *exceptions*, not *silent emptiness*.

These tests run a real ``codegenie gather`` against a repo that HAS a
Dockerfile and assert the contract directly: (1) every raw sidecar a probe
declares as an input is actually produced, and (2) the dependent probes emit
real data rather than the degraded ``unavailable`` slice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner

_DOCKERFILE = (
    "FROM node:20-slim\n"
    "WORKDIR /app\n"
    "COPY package.json ./\n"
    "COPY index.js ./\n"
    "RUN npm ci --omit=dev || true\n"
    'ENTRYPOINT ["node", "index.js"]\n'
)

_RAW_SIDECAR_TOKEN = re.compile(r"^\.codegenie/context/raw/([a-z0-9_]+)\.json$")


def _make_dockerfile_repo(tmp_path: Path) -> Path:
    """Build a hermetic Node repo that HAS a Dockerfile.

    A Dockerfile is the precondition that makes both sidecar producers run:
    ``dockerfile`` parses it, and ``runtime_trace`` only ``applies()`` when a
    Dockerfile is present.
    """
    repo = tmp_path / "dockerfile_repo"
    repo.mkdir()
    (repo / "Dockerfile").write_text(_DOCKERFILE)
    (repo / "package.json").write_text(
        '{"name": "sidecar-contract-fixture", "version": "1.0.0"}\n'
    )
    (repo / "index.js").write_text("console.log('hello');\n")
    return repo


def _gather(repo: Path) -> dict[str, Any]:
    """Run ``codegenie --no-gitignore gather <repo>`` and return the envelope."""
    from codegenie.cli import cli

    result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert result.exit_code == 0, f"gather failed (exit {result.exit_code}): {result.output}"
    yaml_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.is_file(), f"envelope missing at {yaml_path}"
    envelope = yaml.safe_load(yaml_path.read_text())
    return envelope


def _declared_raw_sidecars() -> set[str]:
    """Every ``raw/<name>.json`` sidecar that any registered probe declares
    as an input via ``declared_inputs``.

    Probes are instantiated (``e.cls()``) before reading ``declared_inputs``
    because some probes — e.g. ``DepGraphProbe`` — set it on the instance
    rather than the class, exactly as the CLI's registry seam does.
    """
    import codegenie.probes  # noqa: F401  (import populates the probe registry)
    from codegenie.probes.registry import default_registry

    required: set[str] = set()
    for entry in default_registry.sorted_for_dispatch():
        for token in entry.cls().declared_inputs:
            match = _RAW_SIDECAR_TOKEN.match(token)
            if match is None:
                continue
            required.add(match.group(1))
    return required


def test_declared_raw_sidecar_inputs_are_produced_by_a_gather(tmp_path: Path) -> None:
    """Structural contract: every ``raw/<name>.json`` a probe declares as an
    input must actually be written by a gather.

    This is the catch-all for the bug class "probe wired to a sidecar nobody
    writes". A declaring probe whose sidecar is never produced reads nothing
    via ``read_raw_slices`` and emits ``confidence=unavailable`` on every run,
    forever — exactly how entrypoint/shell_usage/certificate shipped dead.
    The check auto-extends: any future probe that declares a raw sidecar
    input gets the same guarantee for free.
    """
    required = _declared_raw_sidecars()

    assert {"dockerfile", "runtime_trace"} <= required, (
        f"expected the Layer C marker sidecars in declared inputs; got {sorted(required)}"
    )

    repo = _make_dockerfile_repo(tmp_path)
    _gather(repo)
    raw_dir = repo / ".codegenie" / "context" / "raw"

    missing = sorted(name for name in required if not (raw_dir / f"{name}.json").is_file())
    assert not missing, (
        f"probes declare raw/<name>.json as a gather input, but no probe produced it: "
        f"{missing}. The declaring probe(s) will read nothing via read_raw_slices() and "
        f"emit confidence=unavailable on every gather. The producing probe must persist "
        f"its slice to raw/<name>.json (see dockerfile.py / runtime_trace.py _write_files)."
    )


def test_dockerfile_consumers_populate_on_real_gather(tmp_path: Path) -> None:
    """Behavioural contract: a repo WITH a Dockerfile yields non-empty
    ``entrypoint`` and ``shell_usage`` slices after a real gather.

    This is the semantic oracle the portfolio golden test lacked — it asserts
    the *expectation* ("a parsed Dockerfile reaches its consumers"), not a
    snapshot, so a broken baseline cannot hide the bug.
    """
    repo = _make_dockerfile_repo(tmp_path)
    probes = _gather(repo)["probes"]

    entrypoint = probes["entrypoint"]["entrypoint"]
    assert entrypoint["confidence"] != "unavailable", (
        "entrypoint is 'unavailable' despite a Dockerfile being present — "
        "it could not read the dockerfile sidecar"
    )
    assert entrypoint["entrypoints"], (
        "entrypoint probe saw a Dockerfile but reported no entrypoint"
    )
    assert entrypoint["entrypoints"][0]["form"] == "exec", entrypoint["entrypoints"]

    static = probes["shell_usage"]["shell_usage"]["static"]
    assert static["final_stage_entrypoint_form"] == "exec", (
        "shell_usage.static did not pick up the Dockerfile's ENTRYPOINT — "
        f"it could not read the dockerfile sidecar. static={static}"
    )
    assert static["final_stage_run_commands"], (
        "shell_usage.static dropped the Dockerfile RUN line"
    )


def test_runtime_trace_consumer_populates_on_real_gather(tmp_path: Path) -> None:
    """Behavioural contract for the second producer: ``certificate`` consumes
    the ``runtime_trace`` sidecar.

    On macOS the underlying trace is platform-degraded, but ``certificate``
    must still reach a non-``unavailable`` confidence — proving it read a real
    ``runtime_trace`` slice rather than a phantom missing file.
    """
    repo = _make_dockerfile_repo(tmp_path)
    probes = _gather(repo)["probes"]

    certificate = probes["certificate"]["certificate"]
    assert certificate["confidence"] != "unavailable", (
        "certificate is 'unavailable' — it could not read the runtime_trace "
        "sidecar (raw/runtime_trace.json was never written)"
    )
```
