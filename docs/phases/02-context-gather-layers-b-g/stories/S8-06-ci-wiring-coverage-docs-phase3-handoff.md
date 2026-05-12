# Story S8-06 — CI jobs wired + coverage carve-outs + contributing docs + Phase 3 handoff issues

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S8-03, S8-04, S8-05
**ADRs honored:** ADR-0004 (`tool_digests_verify` CI job is the install-time digest enforcer), ADR-0008 (`conventions_catalog_parity` CI job composes the parity + schema-version lints), ADR-0010 (`fence` job extended to forbid `tantivy` in default deps), ADR-0011 (B2 25%-regression bench gate is path-filtered to `index_health.py` + coordinator), every Phase 2 ADR (referenced from the contributor cheat sheet)

## Context

This is the **final Phase 2 story**. Everything Steps 1–7 built and Steps 8-01 through 8-05 verified is consolidated here into:

1. **CI workflow wiring.** The two new Phase 2 CI jobs (`tool_digests_verify`, `conventions_catalog_parity`) are added to `.github/workflows/`. Phase 1's six-job workflow (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) is **extended** in place — Phase 2 unit + adversarial + integration tests run in the `test` job; `pip-audit` + `osv-scanner` closure extends to the new pip deps; `fence` is extended to forbid `tantivy` in default deps; the path-filtered `bench_gate` job runs B2's 25%-regression bench on PRs touching `index_health.py` or coordinator; the `real_oss` job runs nightly (or on demand via a label).
2. **Coverage carve-outs.** Per-module floors of **85/75** for `probes/syft_sbom.py`, `probes/grype_cve.py`, `probes/scip_index.py` are declared in `pyproject.toml` (`[tool.coverage.report]` `fail_under` per-module sections). The global 90/80 ratchet is held.
3. **Contributor docs.** `docs/contributing.md` gets a new section "Adding a Phase 2-shape probe" — pointing at canonical examples (the 17 Phase 2 probes), the tool-wrapper contract, the sub-schema discipline, the `consumes_peer_outputs` opt-in, the per-file cache opt-in. The cheat sheet is the **index** into the architecture, not a duplicate of it.
4. **Phase 3 handoff issues.** Five GitHub issues are filed on the project board with the `phase-3` milestone (aligned to `roadmap.md §"Phase 3"`), each one citing the originating doc section so the Phase 3 author has the context one click away.
5. **Phase 2 README close.** `docs/phases/02-context-gather-layers-b-g/README.md`'s exit-criteria checklist is marked complete with a citation to the closing story for each row.

This story is the visible signal that Phase 2 is done. Reviewers see "Phase 2 closed" without re-deriving the closure from CI status.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` — Phase 2 exit criteria (every row in the README checklist).
  - `../phase-arch-design.md §"Open questions"` — items deferred from Phase 2; informs the Phase 3 issue narratives.
  - `../phase-arch-design.md §"Integration with Phase 3 (next phase)"` — new contracts Phase 3 consumes; the cheat sheet references the artifact list.
- **Phase ADRs (all 13):**
  - `../ADRs/0001-peer-outputs-binding.md` through `../ADRs/0013-scip-node-modules-conditional-mount.md` — the cheat sheet references the ADRs by number when discussing the corresponding pattern; the README close cites each ADR for the relevant exit-criteria row.
- **Source design:**
  - `../final-design.md §"Synthesis ledger"` — referenced from the cheat sheet for the rationale behind specific patterns (e.g., row 9 → SBOM cache-key composition; the cheat sheet's "cache-key recipe" subsection cites this).
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — feature list (CI jobs, coverage carve-outs, contributing docs, Phase 3 handoff).
  - `../High-level-impl.md §"What's next — handoff to Phase 3"` — the prose Phase 3's author reads on day one; informs the cheat sheet framing.
- **Existing code/CI:**
  - `.github/workflows/<phase-1-workflow>.yml` — extend, do not replace.
  - `pyproject.toml` — `[tool.coverage]`, `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.mypy]` sections.
  - `docs/contributing.md` (Phase 0/1 origin) — extend.
  - `docs/phases/02-context-gather-layers-b-g/README.md` — exit-criteria checklist.
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S6-03-contributing-docs-phase2-handoff.md` (Phase 1's analogous close-out story — the direct template).

## Goal

Wire two new CI jobs + extend the existing six jobs for Phase 2 surface, declare per-module coverage carve-outs in `pyproject.toml`, ship a "Adding a Phase 2-shape probe" cheat sheet in `docs/contributing.md`, file five Phase 3 follow-up issues on the GitHub Project board, and mark the Phase 2 README's exit-criteria checklist complete so the phase is genuinely closed.

## Acceptance criteria

- [ ] `.github/workflows/<workflow>.yml` has two new jobs:
  - `tool_digests_verify` — runs `python scripts/check_tool_digests.py` (S1-08); fails red if any binary on `$PATH` mismatches the pinned SHA-256 in `src/codegenie/catalogs/tools/digests.yaml`.
  - `conventions_catalog_parity` — runs (a) `python scripts/check_conventions_catalog_parity.py` (S2-04), (b) `python scripts/check_skill_schema_versions.py` (S2-05), (c) `python scripts/check_conventions_schema_versions.py` (S2-05); fails red on any asymmetry or missing schema version.
- [ ] The existing `test` job is extended to run Phase 2's unit + adversarial + integration test surfaces. The `real_oss` test is **excluded** from the default `test` job and runs in a separate **`real_oss`** job triggered by either `schedule: cron: '0 6 * * *'` (nightly) or the `real-oss` PR label.
- [ ] The existing `security` job's `pip-audit` + `osv-scanner` closure includes (verify by reading the workflow YAML): `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript`, `dockerfile`, `markdown-it-py`, `msgpack`, `gitpython` (if `S3-01` chose it over subprocess), optionally `tantivy` (only when `codegenie[search]` is installed).
- [ ] The existing `fence` job is extended (in the same script file, not a new file) to forbid `tantivy` in default deps — `import tantivy` under `src/codegenie/` must fail. The job continues to enforce: no LLM SDKs (`anthropic`, `openai`, …); no HTTP libs (`httpx`, `requests`, `aiohttp`); no `socket` calls; `tokens_per_run == 0`.
- [ ] A new **`bench_gate`** job runs `pytest tests/bench/test_index_health_budget.py` **only on PRs that change** `src/codegenie/probes/index_health.py` OR `src/codegenie/coordinator.py` (use `paths:` in the `pull_request:` trigger or a `dorny/paths-filter` step). The job runs the comparator script (`scripts/compare_bench_baseline.py`); failure is a hard merge block.
- [ ] A new **`adversarial_count`** job runs `python scripts/count_phase2_adversarial.py` (from S8-01); fails red if the count is < 40.
- [ ] `pyproject.toml` declares per-module coverage floors of **85% line / 75% branch** for the three heavy external-tool probes — `probes/syft_sbom.py`, `probes/grype_cve.py`, `probes/scip_index.py` — using `[tool.coverage.report]` with module-keyed `fail_under` sub-tables or an equivalent mechanism the coverage tool supports. The global 90/80 ratchet is preserved.
- [ ] `docs/contributing.md` has a new H2 section **"Adding a Phase 2-shape probe"** with at least six subsections: (a) **Choose a tool wrapper** (point at `src/codegenie/tools/` + `tools/digests.yaml`); (b) **Declare your sub-schema** (`additionalProperties: false`, `schema_version: "v1"`, cross-link to `SCHEMA-EVOLUTION-POLICY.md`); (c) **Pick a layer + cache strategy** (Layer A–G, `cache_strategy="content" | "none"`, when to opt into `consumes_peer_outputs = True`); (d) **Use the per-file findings cache** (point at `src/codegenie/coordinator/per_file_cache.py`); (e) **Honor the sanitizer + audit chain** (Pass 4 + Pass 5 are universal; never bypass); (f) **Write the golden + adversarial test** (point at S8-04 + S8-01). Each subsection ≤ 15 lines; references specific Phase 2 probes by relative link.
- [ ] The cheat sheet references **specific Phase 2 probes as canonical examples**: `src/codegenie/probes/index_health.py` (the `consumes_peer_outputs` example), `src/codegenie/probes/build_graph.py` (the wrapper-invariant example), `src/codegenie/probes/syft_sbom.py` (the cache-key-composition example), `src/codegenie/probes/semgrep.py` (the per-file cache example), `src/codegenie/probes/runtime_trace.py` (the constant-content deferred-probe example).
- [ ] **Five Phase 3 follow-up issues** are filed on the GitHub Project board, each labeled `phase-3`, milestoned to `roadmap.md §"Phase 3"`, body cites the originating doc section by relative path:
  - "Implement Phase 3's first deterministic vuln-remediation recipe" (the Phase 3 kickoff).
  - "Extend `IndexHealthProbe` with Phase 3 consumer rule (`if vuln_remediation.patch_applied present then cve_scan.matches MUST include the targeted CVE`)" (cite `phase-arch-design.md §"Open questions"` + `final-design.md §"Conflict-resolution table"`).
  - "Decide per-probe sub-schema release-versioning v1→v2 cadence" (cite Open Question #2; the cadence is revisited when the first breaking change is proposed).
  - "Phase 7 conventions catalog scope decision: language-scoped vs task-scoped" (cite Open Question #4; defers to Phase 7's distroless additions).
  - "Phase 14 sub-cache GC policy tuning" (cite Open Question #6; the 5 GB LRU cap is the Phase 2 default).
- [ ] Each Phase 3 issue body has (a) one-sentence problem statement, (b) doc-section citation, (c) load-bearing surface this issue unblocks, (d) scope hints (not a design — left to the Phase 3 author).
- [ ] `docs/phases/02-context-gather-layers-b-g/README.md`'s exit-criteria checklist is marked complete; each row cites the closing story (e.g., `- [x] Useful repo-context.yaml on a real Node.js TS repo — S8-02`).
- [ ] `mkdocs build --strict` passes; `docs/contributing.md` remains in the curated `nav`; the new ADR-cited links in the cheat sheet resolve.
- [ ] All eight CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`, `tool_digests_verify`, `conventions_catalog_parity`) — plus the `bench_gate` (path-filtered) and `adversarial_count` (always-on) — are **green on `main`** on Python 3.11 and 3.12 with the full Phase 2 test surface.

## Implementation outline

1. **Audit the existing workflow.** Read `.github/workflows/<phase-1-workflow>.yml`. Note the six-job structure (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`). The Phase 2 extension is **additive**: two new jobs (`tool_digests_verify`, `conventions_catalog_parity`), the gated `bench_gate` and `adversarial_count` jobs, and the moved-out `real_oss` job — plus in-place edits to the existing six.
2. **Add the new jobs.** Each is ≤ 20 lines of YAML; copy the structural shape from an existing job. Use the same `setup-python` + `cache: 'pip'` boilerplate. The `bench_gate` job uses `dorny/paths-filter@v3` (or the equivalent GitHub-native `paths:` trigger; both work) to gate on the two paths.
3. **Extend the existing six jobs:**
   - `test`: add `pytest tests/adv tests/integration tests/golden -m "not real_oss and not slow_adv"` to the existing command (or merge into a single `pytest` invocation with the markers).
   - `security`: extend the `pip-audit` and `osv-scanner` invocations' targets to include the new deps; if the closure is computed via `requirements*.txt`, add the Phase 2 deps to those files.
   - `fence`: extend the `forbidden_imports` list (or equivalent — the Phase 0/1 fence script lives at `scripts/fence.py` or similar) to add `tantivy`.
   - Other jobs (`lint`, `typecheck`, `docs`): verify they cover the new surface (the Phase 2 source tree is automatically included by `src/codegenie/` globs).
4. **Update `pyproject.toml`** for the per-module coverage floors. The exact syntax depends on the coverage tool (`coverage.py` supports `[tool.coverage.report]` with `fail_under` global; per-module floors typically require a custom script or `coverage report --fail-under` per-file invocation). The most portable approach: a small `scripts/check_module_coverage.py` that reads the coverage XML and asserts per-module thresholds; the `test` job runs it post-pytest. Phase 1's ADR-0005 (Phase 1) `coverage-carve-outs-deployment-ci.md` is the precedent — read it before deciding the implementation shape.
5. **Write the cheat sheet** in `docs/contributing.md`. Six subsections, each pointing at a specific Phase 2 probe and ADR. No duplicate of the architecture — point at it.
6. **File the five Phase 3 issues** via `gh issue create` (one per issue). Capture the URLs in the PR body.
7. **Mark the Phase 2 README's exit-criteria checklist complete.** Each `- [x]` row gets a citation: `S8-XX` or `S1-XX` etc. The list reads as a closed ledger.
8. **Confirm `mkdocs build --strict` passes locally** before opening the PR.

## TDD plan — red / green / refactor

### Red — write the failing test first

This story is largely declarative (CI YAML + docs + issue filing). The "red" is the CI workflow: when the new jobs are added but the underlying scripts are not invoked correctly, the jobs fail red. The first red-then-green cycle:

Path: `.github/workflows/<workflow>.yml` (extended)

```yaml
tool_digests_verify:
  runs-on: ubuntu-22.04
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
        cache: 'pip'
    - run: pip install -e .
    - run: python scripts/check_tool_digests.py
```

Open the PR; the job fires; if `scripts/check_tool_digests.py` is not invokable from a fresh CI runner (e.g., a binary expected on `$PATH` is missing), the job red-fails with a clear message — surface and fix (install the binary in the CI step or document the dependency in the script's error message).

Path: `tests/test_phase3_handoff_issues.py` (story-internal verification)

```python
"""Phase 3 handoff: five GitHub issues exist and have the right labels."""
import os
import subprocess


def test_five_phase_3_issues_filed():
    out = subprocess.check_output(
        ["gh", "issue", "list", "--label", "phase-3", "--state", "open", "--json", "title"],
        text=True,
    )
    titles = [item["title"] for item in __import__("json").loads(out)]
    expected = {
        "Implement Phase 3's first deterministic vuln-remediation recipe",
        # ... four more
    }
    missing = expected - set(titles)
    assert not missing, f"missing Phase 3 issues: {missing}"
```

This test runs once locally during the PR; it does not become a permanent CI test (the issues persist beyond CI lifespan). Note in the PR body that the test was run and passed.

### Green — make it pass

For the CI YAML edits, green is when every job runs to completion and reports the right exit code. The most common first failure is a missing dep in the CI environment (e.g., `semgrep` not on `$PATH` for the `tool_digests_verify` job to inspect) — surface as either a fixture-tools install step or a script change that handles the missing-binary case gracefully (refer to ADR-0004's contract).

For the cheat sheet, green is when `mkdocs build --strict` passes. The most common first failure is a broken relative link in the new section — verify each `[link](path)` resolves.

For the Phase 3 issues, green is when all five are filed with the right labels/milestones. Capture the URLs in the PR body for reviewer confirmation.

### Refactor — clean up

After green:

- Confirm all eight CI jobs (plus `bench_gate` + `adversarial_count` + `real_oss`) are green on `main` on a final test push.
- Confirm `mkdocs build --strict` is in the `docs` CI job (it should be, from Phase 0/1).
- Re-read the Phase 2 README's exit-criteria checklist; each row has a story citation; nothing is unmarked.
- Re-read the cheat sheet; verify each canonical-example link resolves and each ADR-cite is correct (ADR numbers can shift; verify against `../ADRs/README.md`).
- Trial-run a no-op PR (touching a comment in `index_health.py`) to verify the `bench_gate` job fires; trial-run a no-op PR touching `README.md` to verify the gate does **not** fire (path filter is correct).

## Files to touch

| Path | Why |
|---|---|
| `.github/workflows/<phase-1-workflow>.yml` | Extend in place: two new jobs + four extended jobs + two gated jobs (`bench_gate`, `adversarial_count`) + one nightly job (`real_oss`). |
| `pyproject.toml` | Per-module coverage floors (85/75 for three heavy probes); register `real_oss` + `slow_adv` markers. |
| `scripts/check_module_coverage.py` | New — per-module floor enforcement post-pytest. |
| `docs/contributing.md` | New H2 "Adding a Phase 2-shape probe" + six subsections. |
| `docs/phases/02-context-gather-layers-b-g/README.md` | Exit-criteria checklist marked complete with story citations. |
| `mkdocs.yml` | Confirm `contributing.md` is in `nav` (should already be from Phase 1; verify). |
| `tests/test_phase3_handoff_issues.py` | Story-internal — verify the five Phase 3 issues are filed; not retained in CI. |
| `requirements-dev.txt` / `requirements.txt` (or `pyproject.toml` deps) | Confirm Phase 2 deps (`tree-sitter*`, `dockerfile`, `markdown-it-py`, `msgpack`, optional `tantivy`) are listed for the `security` job's audit closure. |

## Out of scope

- **New probes or new adversarial tests.** This story consolidates; it does not extend.
- **Modifying probe behavior.** If a probe regresses against the goldens or against B2's budget, surface as a Step 3–7 follow-up; this story does not patch probes.
- **Phase 3 design work.** The five issues are placeholders pointing at the originating context; Phase 3's `roadmap-phase-designer` workflow does the design.
- **Bench baseline auto-bump.** Explicitly non-auto; manual bumps via PR.
- **Bench gate on probes other than B2.** ADR-0011 commits to one gating bench (B2); the others are advisory. Do not promote an advisory bench to gating without an ADR.
- **`real_oss` job in the default PR-trigger set.** Real-OSS is nightly + label-triggered; do not include in the default `test` matrix or PR-blocking surface (`High-level-impl.md §"Implementation-level risks"` #6).
- **Renaming Phase 1's CI workflow file.** Extend in place; renaming risks breaking GitHub's required-status-checks configuration.

## Notes for the implementer

- **Phase 1's S6-03 is the direct template for this story.** Read it once before starting; the structural pattern (extend `contributing.md`, file follow-up issues, close the README) is identical. The Phase-2 differences are scope (more probes, more ADRs, more CI jobs) — not shape.
- **The cheat sheet is the *index*, not the duplicate.** "Organizational uniqueness as data, not prompts" (`CLAUDE.md`) — the architecture lives in `phase-arch-design.md` and the ADRs; the cheat sheet points contributors at them. Resist the urge to inline the rationale; one-sentence-then-link is the discipline.
- **The `bench_gate` job's path filter is fragile.** If the filter is wrong (e.g., a typo in the path), the gate either never fires (false negative) or fires on every PR (false positive — slow CI, eroded trust). Verify with a no-op PR before merging this story.
- **`real_oss` job placement matters.** If you put it in the default workflow with a conditional `if:`, the GitHub UI may show it as "expected" and confuse contributors when it doesn't run. A separate workflow file (`real-oss.yml`) with `schedule:` + `pull_request:` triggers + a `if:` on the label is cleaner.
- **Per-module coverage floors via `scripts/check_module_coverage.py`** is the portable approach. `coverage.py`'s built-in `fail_under` is global only; the per-module enforcement is custom. Phase 1's ADR-0005 likely chose the same approach — re-use the pattern.
- **The Phase 2 README's exit-criteria checklist is the visible-signal artifact.** A reviewer skimming the phase folder should see "every row checked" with a story citation — and conclude "Phase 2 is closed." Do not leave ambiguity; even rows that were trivially satisfied (e.g., `additionalProperties: false` discipline) get a citation (`S2-07`).
- **The Phase 3 issues' bodies must cite the originating doc by relative path** (`../phase-arch-design.md §"Open questions" #2`). The Phase 3 author follows the link; if the link breaks (because the section heading changes), the issue becomes archaeology. Verify each link resolves at the time of filing; if you anticipate a heading change, file the issue against a stable section instead.
- **`mkdocs build --strict` is the docs gate.** A broken link in the cheat sheet causes the `docs` CI job to fail. Run locally before pushing.
- **Track the close-out in the PR body.** The PR description should list (a) the five Phase 3 issue URLs, (b) the count of fixtures from `adversarial_count` (showing ≥ 40), (c) the bench results (B2 p99 + ratio-to-baseline), (d) the green status of all eight + 2-gated CI jobs. This makes the merge a 30-second review for someone trusting the green check marks.
- **This is the last Phase 2 PR.** After merge, Phase 3 starts. The hand-off discipline is what makes Phase 3 cheap to start — don't shortcut the docs/issues/README close-out.
