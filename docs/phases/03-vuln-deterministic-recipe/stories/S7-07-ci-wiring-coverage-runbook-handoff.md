# Story S7-07 — CI gates wired + coverage ratchets + runbook + Phase-4 follow-ups

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-02 (≥ 30 adversarial fixtures — the `adversarial_corpus` CI job needs the corpus on disk), S7-03 (5× determinism canary — the `determinism_canary` job invokes the canary test), S7-04 (perf canaries — the hot-path latency + cache-hit rate gates need the perf tests), S7-05 (Phase 2 regression hard-gate — the `phase2_regression` job invokes `test_phase2_unchanged.py`), S7-06 (Phase-4 handoff contract — the `phase4_handoff` job invokes the contract test)
**ADRs honored:** ADR-0002 (fence extension to `transforms/` + `recipes/` — finalized as merge-blocking here), ADR-0011 (recipe digest pin manifest — `recipes_digests_verify` CI gate finalizes the discipline), ADR-0014 (tool digest pin manifest — `tool_digests_verify` extended for `npm`, `ncu`, `openrewrite-jar`), ADR-0013 (no LLM — the fence gate is the mechanical CI enforcement of the no-LLM-in-this-loop invariant)

## Context

S1-09 planted the `fence` scanner extension; S3-03 + S3-04 + S6-01 planted the digest-pin manifests; S7-02/S7-03/S7-04/S7-05/S7-06 planted the tests. **This story is the final wiring** — every Phase-3 CI gate becomes merge-blocking in `.github/workflows/` (or whatever Phase 0's CI substrate is), the coverage ratchets are enforced, the operator runbook (`runbook.md`) is on disk and cross-linked, and the Phase-4 follow-up backlog is filed as GitHub issues / a backlog file. This story is the **last story in Phase 3**; the moment it merges, the phase is done.

The five new (or extended) CI gates:

1. **`fence`** (S1-09 + extension) — forbids `anthropic`, `langgraph`, `chromadb`, `qdrant`, `qdrant-client`, `sentence-transformers`, `voyageai`, `openai` under `src/codegenie/transforms/` + `src/codegenie/recipes/`. Now merge-blocking.
2. **`tool_digests_verify`** (Phase 2's + extension) — extended to verify `npm`, `ncu`, `openrewrite-jar` digests against `tools/digests.yaml`.
3. **`recipes_digests_verify`** (new) — verifies every recipe YAML's on-disk SHA-256 matches `recipes/digests.yaml`; ADR-0011 / Gap 2 enforcement.
4. **`determinism_canary`** (new) — runs the 5× byte-identical canary from S7-03.
5. **`adversarial_corpus`** (new) — runs the ≥ 30 fixtures from S7-02.

Coverage ratchets are a separate but related discipline (per the "Definition of done" in `stories/README.md`):

- **95% line / 90% branch** on `transforms/contract.py`, `recipes/contract.py`, `transforms/coordinator.py` (the three contract files).
- **90% line / 80% branch** on every other new Phase-3 package (`transforms/`, `recipes/`, sub-packages).
- Enforced via `coverage.py` config + a CI assertion step.

The operator runbook (`docs/phases/03-vuln-deterministic-recipe/runbook.md`) documents three things per Gap 3 + Gap 5 + Open Question #11:

- **`signal_escalate` flow** — what to do when `gate.signal_escalate` (exit 8) fires.
- **Fixture rotation policy** — quarterly cadence per ADR-0012; out-of-cycle triggers (npm major-version bump).
- **`codegenie remediation gc` stub** — when do `.codegenie/remediation/<run-id>/` directories rotate? Phase 14 closes; the runbook is the stub.

Phase 4 follow-up backlog: each item is a one-line issue title + 2-3-sentence description, captured in `docs/phases/03-vuln-deterministic-recipe/phase4-followups.md` (or filed directly as GitHub issues if the project uses gh-issues). The list: LLM-fallback engine registration (`LlmRecipeEngine` slot reserved in `RecipeEngine` ABC), RAG retrieval against `RecipeSelection.reason` for the four non-`matched` edges, OpenRewrite catalog expansion, `evidence_stale` filtering for RAG deposits.

The `README.md` cross-links + the CLI exit-code-8 stderr banner cross-reference are minor but load-bearing — operators must be able to navigate from a red CI gate or an exit-8 banner to the runbook in one click.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Harness engineering" §"CI gates"` — full gate list.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 3"` — `signal_escalate` operator surface; runbook entry required.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 5"` — fixture rotation policy.
  - `../phase-arch-design.md §"Roadmap coherence check" §"Phase-4 handoff"` — the follow-up backlog scope.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — recipe digest manifest CI gate.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — tool digest extensions.
  - `../ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — fixture rotation policy.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — fence gate's load-bearing rationale.
- **Source design:**
  - `../final-design.md §"Open questions"` #11 — `codegenie remediation gc` stub deferred to Phase 14.
- **Existing code:**
  - `.github/workflows/*` (Phase 0/1/2 CI) — read end-to-end to identify the existing fence + tool_digests_verify jobs and the YAML conventions to mirror.
  - `pyproject.toml` — `tool.coverage` section (Phase 0 baseline).
  - `scripts/fence_imports.py` (S1-09) — the scanner the merge-blocking gate invokes.
  - `scripts/check_tool_digests.py` (Phase 2 + extensions) — extended in S3-03 + S6-01.
  - `scripts/check_recipes_digests.py` (new in this story, or planted in S3-04) — verifies `recipes/digests.yaml` parity.
- **Story precedent:**
  - `S7-05-phase2-regression-hardgate.md` — pytest-marker → CI-job pattern this story mirrors.

## Goal

Wire every Phase-3 CI gate as merge-blocking, enforce coverage ratchets, land the operator runbook documenting `signal_escalate` + fixture rotation + GC stub, file the Phase-4 follow-up backlog, cross-link the runbook from `README.md` + CLI exit-code-8 stderr banner, and mark every Phase-3 exit criterion complete in `docs/phases/03-vuln-deterministic-recipe/README.md`.

## Acceptance criteria

- [ ] **`.github/workflows/`** (or equivalent CI substrate) has all five new/extended jobs wired and configured to block merge on red:
  - `fence` — extended to scan `src/codegenie/transforms/` + `src/codegenie/recipes/` (per S1-09); invokes `scripts/fence_imports.py`; merge-blocking.
  - `tool_digests_verify` — extended to verify `npm`, `ncu`, `openrewrite-jar` digests via `scripts/check_tool_digests.py`; merge-blocking.
  - `recipes_digests_verify` — new; invokes `scripts/check_recipes_digests.py` (or equivalent); every recipe YAML's on-disk SHA-256 matches `recipes/digests.yaml`; merge-blocking.
  - `determinism_canary` — new; invokes `pytest -m determinism_canary` (or whatever marker S7-03 used); merge-blocking; budget ≤ 10 min.
  - `adversarial_corpus` — new; invokes `pytest tests/adv/` (or `pytest -m adversarial` if marked); merge-blocking; budget ≤ 15 min.
- [ ] **Coverage ratchets enforced** at the configured thresholds:
  - 95% line / 90% branch on `src/codegenie/transforms/contract.py`, `src/codegenie/recipes/contract.py`, `src/codegenie/transforms/coordinator.py`.
  - 90% line / 80% branch on `src/codegenie/transforms/**` (excluding the three contract files; they inherit the stricter threshold) and `src/codegenie/recipes/**`.
  - Enforced via `pyproject.toml`'s `[tool.coverage.report]` `fail_under` per-file overrides (or a custom assertion script invoked from the workflow).
  - Coverage report uploaded as a CI artifact on every PR.
- [ ] **`docs/phases/03-vuln-deterministic-recipe/runbook.md`** exists with three sections:
  - **`signal_escalate` (exit 8) flow** — Gap 3. Describes: what the stderr banner says; the on-disk `escalation.json` location; how to re-run with `--allow-test-network`; what to expect from the second run (validation gate widens to scoped allowlist); when **not** to use `--allow-test-network` (production CI without operator review).
  - **Fixture rotation policy** — Gap 5. Quarterly cadence per ADR-0012; out-of-cycle triggers (npm major-version bump); the `npm-resolution.json` regeneration procedure; mirror size budget (≤ 5 MB target; ≥ 10 MB triggers git-lfs migration per Open Question #8).
  - **`codegenie remediation gc` stub** — Open Question #11. Documents the rotation policy stub (default: keep the last 30 days of `.codegenie/remediation/<run-id>/` directories; older auto-archive to `.codegenie/remediation/_archive/`); notes Phase 14 closes with a real GC.
- [ ] The runbook is **≤ 200 lines** end-to-end. Resist scope creep — operator-facing reference, not a tutorial.
- [ ] **Cross-links land** from:
  - `README.md` (top-level project README; one bullet point in the "Operating" / "Documentation" section linking to the runbook).
  - CLI exit-code-8 stderr banner (S5-05 + S4-05) — the banner already references the runbook; this story confirms the link is correct after the runbook merges.
  - The CLI's `--help` for `codegenie remediate` and `codegenie cve sync` includes a one-line note: `"See docs/phases/03-vuln-deterministic-recipe/runbook.md for operator guidance."`.
- [ ] **Phase 4 follow-ups filed.** `docs/phases/03-vuln-deterministic-recipe/phase4-followups.md` (or a set of GitHub issues — match project convention) lists at least:
  - `LlmRecipeEngine` registration via `@register_engine` (the LLM-fallback engine that lives outside `transforms/` + `recipes/` due to the fence; likely under `src/codegenie/planning/engines/`).
  - RAG retrieval against `RecipeSelection.reason` for the four non-`matched` edges (`catalog_miss` → RAG; `range_break` / `peer_dep_conflict` / `unsupported_dialect` → RAG + LLM).
  - OpenRewrite catalog expansion (more recipes under `recipes/openrewrite-stub/catalog/`).
  - `evidence_stale` filtering for RAG deposits (Phase 4 must learn to skip runs with `evidence_stale: true`).
  - Per-event payload schema ADRs (deferred per ADRs/README; required when `gate.signal_escalate` or `escalation.policy_violation` grow cross-phase consumers).
  - Branch-naming-collision ADR (deferred per ADRs/README; required if short-sha collisions surface).
  - Each entry: 2-3-sentence description naming the ADR-amendment risk + the Phase-3 file the follow-up will touch.
- [ ] **`docs/phases/03-vuln-deterministic-recipe/README.md`** exit-criteria checklist marked complete: every exit criterion in `phase-arch-design.md §"Goals"` (or wherever the checklist lives) is checked off; any unchecked item is justified inline.
- [ ] **`pytest.ini` / `pyproject.toml`** has all new markers registered: `phase2_regression` (S7-05), `phase4_handoff` (S7-06), `determinism_canary` (S7-03), `adversarial` (S7-02), `fence` (S1-09), `perf_canary` (S7-04 if used). No `PytestUnknownMarkWarning` on `main`.
- [ ] **Branch-protection rules** require the five new/extended gates pass before merge (this is GitHub-Actions-substrate-specific; if the project uses a different system, configure the equivalent). Verify by attempting a synthetic-red PR locally.
- [ ] **End-to-end roadmap verification**: `codegenie remediate <node-fixture> --cve <id>` on the express fixture (the Phase-3 roadmap exit criterion) succeeds end-to-end on a fresh CI runner; the resulting branch + report match the contract S7-06 pins. Captured as a CI integration test or as a recorded run in the PR body.
- [ ] All Phase-3 ADRs have `Status: Accepted`; no `Proposed` or `Superseded` left over.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on every Phase-3 file pass.

## Implementation outline

1. **Read existing CI workflows end-to-end** — Rule 8. Phase 0/1/2 already have `fence`, `tool_digests_verify`, and a coverage job. Identify each, identify the YAML conventions (job name, `runs-on`, `steps` pattern, `if: success()` chaining), then extend additively.
2. **Extend `fence` job** to scan the two new packages. If the existing job already enumerates packages from the scanner's constant (likely), no YAML change needed — just run the scanner. If hardcoded, extend the `args` / `paths` list.
3. **Extend `tool_digests_verify`** to include `npm`, `ncu`, `openrewrite-jar`. If `scripts/check_tool_digests.py` enumerates from `tools/digests.yaml` (likely), no script change needed.
4. **Add `recipes_digests_verify` job** invoking `scripts/check_recipes_digests.py` (which S3-04 may have planted; verify and extend if needed). The script reads `recipes/digests.yaml` + walks `recipes/catalog/**/*.yaml`; computes SHA-256 per file; asserts equality with the manifest entry.
5. **Add `determinism_canary` job** — minimal YAML wrapping `pytest tests/integration/test_byte_identical_diff_5x.py`. Budget ≤ 10 min.
6. **Add `adversarial_corpus` job** — wraps `pytest tests/adv/` (or `pytest -m adversarial`). Budget ≤ 15 min.
7. **Configure coverage ratchets.** In `pyproject.toml`, add per-file `fail_under` overrides under `[tool.coverage.report]`. If `coverage.py` does not support per-file thresholds, write a small `scripts/check_coverage.py` that reads `coverage.json` and asserts per-file thresholds.
8. **Write `runbook.md`**. Three sections; ≤ 200 lines. Cross-link to ADR-0005 (signal_escalate), ADR-0012 (fixture rotation), Phase 14 (GC).
9. **Cross-link the runbook** from `README.md`, the CLI `--help` text, and confirm the exit-8 banner reference is correct.
10. **File Phase-4 follow-ups.** Decide between `phase4-followups.md` (a markdown file) or GitHub issues; match project convention; produce the list.
11. **Update `docs/phases/03-vuln-deterministic-recipe/README.md`** exit-criteria checklist; mark complete.
12. **Synthetic-red PR test.** Locally (or in a draft PR), break one of the five gates (e.g., add `import anthropic` to a `transforms/` file); confirm CI red-fails and identifies the gate; revert.

## TDD plan — red / green / refactor

This story is the *integration* of every other Step-7 story, so the TDD-RGR shape is different — the "tests" are the existing tests S7-02/S7-03/S7-04/S7-05/S7-06 wired into CI. Still, three meta-tests pin this story's deliverables:

### Red

Path: `tests/integration/test_ci_gates_wired.py` (or a similar harness test)

```python
"""S7-07 | Invariant: every Phase-3 CI gate is wired into .github/workflows/ and merge-blocking.

This test reads the workflow YAML(s) and asserts the five new/extended jobs exist with the right names,
that each job runs the right command, and that branch-protection rules require all five to pass."""
import yaml
from pathlib import Path

def test_fence_job_extends_to_transforms_recipes() -> None:
    # Read .github/workflows/<file>.yml; find the fence job; assert it scans the two packages.
    ...

def test_recipes_digests_verify_job_exists() -> None:
    ...

def test_determinism_canary_job_exists() -> None:
    ...

def test_adversarial_corpus_job_exists() -> None:
    ...

def test_tool_digests_verify_includes_npm_ncu_openrewrite() -> None:
    ...
```

Path: `tests/integration/test_coverage_ratchets_enforced.py`

```python
"""S7-07 | Invariant: per-file coverage thresholds are configured and met."""
def test_contract_files_have_95_90_threshold() -> None:
    # Read pyproject.toml; assert per-file fail_under is configured for the three contract files.
    ...

def test_phase3_packages_have_90_80_threshold() -> None:
    ...
```

Path: `tests/integration/test_runbook_exists_and_cross_linked.py`

```python
"""S7-07 | Invariant: runbook.md exists with three sections; cross-links from README + CLI helptext."""
def test_runbook_has_three_sections() -> None:
    # Read runbook.md; assert h2 sections for "signal_escalate", "Fixture rotation", "remediation gc".
    ...

def test_readme_cross_links_runbook() -> None:
    ...

def test_remediate_helptext_references_runbook() -> None:
    from click.testing import CliRunner
    ...
```

Run all three; commit red.

### Green

- Edit the CI workflow YAMLs to add / extend each job.
- Configure coverage thresholds in `pyproject.toml`.
- Write the runbook.
- Cross-link from README + CLI helptext.
- File Phase-4 follow-ups.
- Update the exit-criteria checklist.

### Refactor

- **One CI workflow file per gate vs one combined file** — match Phase 0's convention. If Phase 0 ships a single `.github/workflows/ci.yml` with multiple jobs, extend the existing file. If Phase 0 ships separate workflow files per concern, add new files.
- **Wall-clock budgets per job** (≤ 10 min determinism, ≤ 15 min adversarial, ≤ 5 min phase2 regression, ≤ 60 s phase4 handoff) — confirm each gate completes inside its budget on a representative CI runner.
- **`pyproject.toml` markers** — confirm every new marker is registered; run `pytest --strict-markers` locally and confirm no `PytestUnknownMarkWarning`.
- **Synthetic-red PR test** — the one-time validation that the gates actually red-fail on a broken PR. Capture the resulting CI output in the PR body of *this* story as proof.

## Files to touch

| Path | Why |
|---|---|
| `.github/workflows/<existing-or-new>.yml` | Extend or add the five Phase-3 jobs. |
| `pyproject.toml` | Coverage thresholds; pytest markers. |
| `scripts/check_recipes_digests.py` (new or extend S3-04) | The `recipes_digests_verify` script. |
| `scripts/check_coverage.py` (optional, if `coverage.py` per-file thresholds insufficient) | Per-file ratchet enforcement. |
| `docs/phases/03-vuln-deterministic-recipe/runbook.md` | The operator runbook; three sections. |
| `docs/phases/03-vuln-deterministic-recipe/phase4-followups.md` | Phase-4 follow-up backlog (or filed as gh-issues per project convention). |
| `docs/phases/03-vuln-deterministic-recipe/README.md` | Mark exit-criteria checklist complete. |
| `README.md` (top-level project README) | One bullet linking to the runbook. |
| `src/codegenie/cli.py` (extend `--help` text only) | Cross-reference the runbook from `remediate` + `cve sync` helptext. |
| `tests/integration/test_ci_gates_wired.py` | Pin that the workflow YAML has the right jobs. |
| `tests/integration/test_coverage_ratchets_enforced.py` | Pin per-file thresholds. |
| `tests/integration/test_runbook_exists_and_cross_linked.py` | Pin the runbook exists + is cross-linked. |

## Out of scope

- **CI substrate migration** (e.g., GitHub Actions → CircleCI). Out of scope; this story extends the existing substrate.
- **Branch-protection-rule API automation** — branch-protection rules are configured in the GitHub web UI or `gh` CLI; this story documents the required state but does not script the configuration. If a `terraform`-managed setup exists, extend it; otherwise leave for ops.
- **Phase 4 follow-up *implementations*** — the follow-up backlog is filed; the implementations are Phase 4's job.
- **Adding new ADRs in this story** — none expected; if a Phase-4 follow-up surfaces a need for an ADR (e.g., the `LlmRecipeEngine` slot's contract), file a Phase-4 ADR seed, not a Phase-3 ADR.
- **Performance tuning of the CI gates** — perf canaries are S7-04; this story wires them but does not tune.
- **Replacing the runbook with a different format** (e.g., a Confluence page, a Notion doc) — out of scope. Markdown lives in the repo; cross-references are file paths.
- **The `codegenie remediation gc` implementation** — Phase 14. The runbook documents the stub only.
- **Re-running prior steps' acceptance criteria** — every prior story owns its own DoD; this story does not re-verify them.

## Notes for the implementer

- **This is the closing-out story for Phase 3.** Treat the PR as a final review: every prior story's "Status: Done" gets confirmed, every ADR is `Accepted`, the exit-criteria checklist is complete. If anything is unchecked, surface it explicitly in the PR body; do not silently close out an incomplete phase.
- **Synthetic-red PR is the load-bearing pin.** Before merging this story, run a one-off draft PR that introduces an `import anthropic` into `src/codegenie/transforms/foo.py` (or equivalent breakage for each gate); confirm each gate red-fails with an informative message; close the draft PR. This is the proof the gates are real, not just configured.
- **Coverage ratchets are unforgiving.** A drop from 96% to 94% on `transforms/contract.py` red-fails the ratchet. Treat this as a feature, not a bug — the contract files are load-bearing; coverage drops indicate the test suite weakened. If a legitimate refactor genuinely lowers achievable coverage (e.g., a defensive `assert False` branch unreachable in normal flow), document the exemption inline (`# pragma: no cover` with a justification comment) — never relax the ratchet.
- **The runbook is operator-facing.** Write it for someone who just got a `signal_escalate` exit-8 banner at 3 AM on a Friday — short, actionable, with the verbatim re-run command. Resist the urge to make it a comprehensive reference; that lives in `phase-arch-design.md`.
- **Phase-4 follow-ups are seeds, not specs.** A 2-3-sentence description is enough — a future Phase-4 implementer will read it as a starting point, not a spec. Resist the urge to design Phase 4 here.
- **CI YAML is fiddly across substrates.** If the project uses GitHub Actions, mirror Phase 0/1/2's job structure exactly — `runs-on`, `steps`, `if: success()` chaining. If something else, ask the project maintainer; do not invent.
- **`pytest --strict-markers`** is the way to catch unregistered markers. Add it to the default `pytest` invocation in `pyproject.toml` if not already; otherwise add a one-off CI step that fails on warnings.
- **Branch-protection rules** in GitHub require **exact-name matching** of the required status checks. If the workflow renames a job (e.g., from `Lint` to `lint`), the branch-protection rule must be updated in lockstep. This is operationally easy to miss; document the required exact names in the runbook.
- **`recipes_digests_verify` is the new gate, not an extension.** Make sure the script `scripts/check_recipes_digests.py` is committed (S3-04 may have planted it; if not, plant it here as a small ~30-line script that reads `recipes/digests.yaml` + walks `recipes/catalog/**/*.yaml` + computes SHA-256 + asserts equality).
- **Determinism canary budget.** S7-03's 5× pipeline runs are the long pole — ~30 s × 5 = ~150 s on a warm cache, ~10 min cold. The CI budget of ≤ 10 min assumes a cold cache. If the budget pressures, surface as a perf follow-up for Phase 4; do not silently lower the iteration count.
- **`README.md`'s top-level cross-link** is one bullet, ≤ 80 chars: `- Operator runbook: [docs/phases/03-vuln-deterministic-recipe/runbook.md](...)`. Keep it minimal; the README is the project entry point, not Phase 3's home.
- **Documentation-only changes** dominate this story by line count, but the YAML changes are the load-bearing piece. Review the YAML carefully; a typo in a job's `runs-on` or `steps` silently disables the gate.
- **Closing the phase requires every prior story `Status: Done`.** If any prior story is still `Ready` or `In Progress` at merge time, this story's PR should call it out as a hard blocker. The phase is not done until every story is done.
- **Regression risk: medium.** The biggest risk is silently disabling a gate (e.g., a typo in the job name makes branch-protection skip it). The synthetic-red PR test catches this; do not skip it.
