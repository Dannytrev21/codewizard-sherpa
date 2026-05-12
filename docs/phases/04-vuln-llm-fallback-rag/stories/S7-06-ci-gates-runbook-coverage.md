# Story S7-06 — CI gates wired + runbook + coverage ratchet

**Step:** Step 7 — Harden — adversarial corpus, recall@3, perf canaries, E2E exit criterion, Phase-3 regression, Phase-5 handoff, CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S7-02, S7-03, S7-04, S7-05
**ADRs honored:** ADR-P4-001, ADR-P4-002, ADR-P4-003, ADR-P4-004, ADR-P4-005, ADR-P4-006, ADR-P4-007, ADR-P4-008, ADR-P4-009, ADR-P4-010, ADR-P4-011, ADR-P4-012, ADR-P4-013, ADR-P4-014, ADR-P4-015

## Context

The final fence. Every prior Step 7 story authored a test, fixture, or property; this story wires them into merge-gating CI lights and writes the operator runbook that documents every Phase-4 workflow the operator can run from the CLI. Without this story, all of Step 7's work is locally-green-but-CI-unenforced. The coverage ratchet locks the contract surface at 95/90 line/branch and new-package code at 90/80, so regressions on the highest-risk surface (`llm/contract.py`, `rag/contract.py`, `rag/models.py`, `llm/output_validator.py`, `rag/writeback.py`) are caught the moment a PR slips coverage.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"CI gates"` — names every gate this story wires and the strictness mode each runs in.
  - `../phase-arch-design.md §"Performance regression tests"` — nightly cost canary cadence + 10% drift threshold.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — coverage targets.
  - `../phase-arch-design.md §"Edge cases"` row #4 (misleading-match `τ_hit` auto-raise) and row #24 — runbook documents the operator-facing behavior.
  - `../phase-arch-design.md §"Integration with Phase 5"` — runbook documents the contract surface so Phase-5 readers know what's stable.
- **Phase ADRs:** every ADR is referenced; the runbook is the operator-facing surface that documents the ADR-resolved workflows (especially ADR-P4-002 pending/promoted, ADR-P4-006 embedding-model swap, ADR-P4-008 prompt injection observability, ADR-P4-012 cassette discipline, ADR-P4-013 API-key store policy).
- **Source design:**
  - `../final-design.md §"VCR cassette discipline"` — `cassettes-reviewed` label workflow + sanitization pre-commit.
  - `../final-design.md §"Failure modes & recovery"` — operator recovery workflows (orphan-body recovery, stale-lock breaker, embedding-model reindex).
  - `../final-design.md §"Open questions deferred to implementation"` — runbook lands the resolutions (Gap 4 `--no-rag` semantics, Open question #4 `τ_hit` auto-raise default).
- **Source files lining up for coverage ratchet:**
  - `src/codegenie/llm/contract.py` (S1-02) — 95/90 contract surface.
  - `src/codegenie/rag/contract.py` (S1-03) — 95/90.
  - `src/codegenie/rag/models.py` (S1-03) — 95/90.
  - `src/codegenie/llm/output_validator.py` (S2-01) — 95/90.
  - `src/codegenie/rag/writeback.py` (S6-01) — 95/90.
  - `src/codegenie/{llm,rag,planner,recipes/engines}/**` (Steps 2–6 packages) — 90/80.
- **Pre-existing CI configuration:** `.github/workflows/ci.yml` (Phase 0) — extend, do not rewrite.

## Goal

Land all merge-gating CI gates, write the operator runbook, and wire the coverage ratchet so Phase 4 is enforced at PR-time.

## Acceptance criteria

- [ ] **CI workflow file** `.github/workflows/ci.yml` extended (NOT rewritten) with the following merge-blocking jobs, each with a stable job name:
  - `fence` — extended from Step 1's lint-only check to **gating**; failing imports block merge.
  - `lint` (ruff), `format` (ruff format --check), `type` (mypy strict on `src/codegenie/{rag,llm,planner}`).
  - `test_unit`, `test_integration` — `pytest --record-mode=none` with `VCR_BAN_NEW_CASSETTES=1` env var.
  - `test_adversarial` — runs `tests/adversarial/` (S7-02).
  - `test_e2e_exit_criterion` — runs `tests/e2e/test_e2e_major_version_breaking_change.py` (S7-04) as its own job for fast failure surfacing.
  - `test_phase3_regression` — runs `tests/integration/test_phase3_unchanged.py` (S7-05).
  - `test_phase5_handoff` — runs `tests/integration/test_phase5_handoff_contract.py` (S7-05).
  - `canary_recall_at_k` — runs `tests/canaries/test_rag_retrieval_recall_at_k.py` (S7-03); failure on recall@3 < 0.85 hard-blocks merge.
  - `canary_perf` — runs `tests/canaries/test_selector_chain_p95_under_250ms.py`, `test_query_key_replay_under_5ms.py`, `test_e2e_llm_path_under_180s.py`, `test_prompt_cache_breakpoint_layout.py`.
  - `nightly_cost_canary` — scheduled nightly + on-demand; >10% drift fails the run; gating only on the nightly cadence, surfaced as a status check on PRs.
  - `determinism_canary` — re-runs the Phase-3 determinism canary (already in CI); stays green.
  - `security_logs` — runs `tests/security/test_no_api_key_in_logs.py` against every committed log/audit fixture.
  - `linux_only` — separate Linux-runner job for `test_e2e_jailed_leaf_linux.py`, `test_api_key_store_linux_strict.py`, `test_egress_proxy_allowlist.py`, `test_egress_proxy_strips_agent_x_api_key.py`, `test_egress_proxy_byte_cap_128kb.py`.
- [ ] `.github/workflows/cassettes-reviewed.yml` (new file) enforces the **`cassettes-reviewed` PR label** workflow: any PR diff that touches `tests/fixtures/cassettes/**/*.yaml` requires the label to be set by a human reviewer before the `test_*` jobs run.
- [ ] `.github/scripts/setup-linux-jail.sh` (new file) provisions the Linux runner — creates `agent` UID, installs `bwrap`, prepares `/agent-jail/` mount; the `linux_only` job invokes it.
- [ ] `tests/security/test_no_api_key_in_logs.py` (new file) scans every `.codegenie/remediation/**/audit.jsonl`, `.codegenie/remediation/**/cost-ledger.jsonl`, and `tests/fixtures/audit/*.jsonl` for the API-key fingerprint pattern (`sk-ant-[A-Za-z0-9_-]{30,}`); zero matches required.
- [ ] **`pip install --require-hashes` against `requirements.lock`** wired in CI; rejects any unhashed transitive dep.
- [ ] **Coverage ratchet** configured in `pyproject.toml` (or `.coveragerc`):
  - 95% line / 90% branch on `src/codegenie/llm/contract.py`, `src/codegenie/rag/contract.py`, `src/codegenie/rag/models.py`, `src/codegenie/llm/output_validator.py`, `src/codegenie/rag/writeback.py`.
  - 90% line / 80% branch on every other module under `src/codegenie/{llm,rag,planner,recipes/engines}/`.
  - CI red on any drop below the ratchet on any file.
- [ ] **Runbook** `docs/phases/04-vuln-llm-fallback-rag/runbook.md` exists with sections (each with a stable anchor):
  - `## api_key.env_present — Mac warn flow` — when fired, why, how to remediate.
  - `## Jailed-leaf provisioning on Linux` — runner setup script + `agent` UID + `/agent-jail/`.
  - `## --no-rag / --no-llm semantics (Gap 4)` — explicit cell-by-cell semantics for the `(--no-rag, --no-llm)` matrix and which writeback fires.
  - `## τ_hit auto-raise behaviour (Edge case #4 + #24)` — when the planner auto-raises `τ_hit` on misleading-match clusters, how to disable, audit-event trail.
  - `## Embedding-model swap workflow` — `codegenie models fetch` → `codegenie solved-examples reindex --model-digest <new>`; Gap 2 recovery path.
  - `## Orphan-body recovery` — `codegenie solved-examples prune --orphans`.
  - `## Calibration workflow` — `codegenie solved-examples calibrate` suggests but does not write; operator commits the suggested thresholds.
  - `## RAG retrieval fixture rotation (quarterly, ADR-amended)` — per `../final-design.md` §"30 labeled-triples corpus rotation policy".
  - `## Cassette regeneration` — `pytest --record-mode=once` locally → `cassettes-reviewed` label flow → sanitization pre-commit.
  - `## Model-pin deprecation (ADR-P4-007)` — 60-day warning, coordinated re-record steps.
- [ ] Runbook cross-linked from `README.md` (top-level) and from CLI exit-9 stderr banner (the orchestrator's exit-9 emit path adds a one-line `see runbook: docs/phases/04-vuln-llm-fallback-rag/runbook.md#<anchor>` line keyed to the specific exit reason).
- [ ] All Phase-4 acceptance-criterion items from `../High-level-impl.md §"Step 7" → "Done criteria"` are checked; the matrix is reproduced in `runbook.md §"Phase-4 exit checklist"` with a per-row CI-status reference.
- [ ] TDD red test exists, committed, green (the gate-wiring itself is testable via a `test_ci_workflow_well_formed.py` that yaml-parses `.github/workflows/ci.yml` and asserts the required job names are present).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean across all touched files.
- [ ] On a fresh clone, `pytest` (default invocation) is green; CI lights as documented; the `cassettes-reviewed` label workflow rejects a PR that touches a cassette without the label.

## Implementation outline

1. **Extend the CI workflow.** Open `.github/workflows/ci.yml`; append jobs without renaming existing ones (Rule 3 — surgical). Use a YAML reusable-workflow pattern only if the file is already structured that way; otherwise inline the jobs.
2. **Coverage ratchet.** Wire `pytest-cov` (or `coverage.py` directly) with the per-file targets. Use `coveragerc`'s `[report]` section's `fail_under` per-file via `[paths]` + `[run] source` plus a small `tools/check_coverage_ratchet.py` script (more flexible than the built-in single-threshold).
3. **`cassettes-reviewed` workflow.** New file `.github/workflows/cassettes-reviewed.yml` triggered on `pull_request` events; uses `gh pr view --json labels` to check for the label; required-status-check via branch protection rule (documented in runbook — branch protection itself is configured outside the repo).
4. **Linux-only job.** Set `runs-on: ubuntu-latest`; invoke `.github/scripts/setup-linux-jail.sh` as the first step; install `bubblewrap`; run the Linux-only test files.
5. **Security log scan.** `tests/security/test_no_api_key_in_logs.py` walks every fixture file matching the audit/log glob; greps for `sk-ant-`; fails with the filename + line on any match. (Production-key prefixes documented in the test docstring; redaction unit-tested via a separate fixture that DOES contain a fake key prefix in a known-safe position.)
6. **`pip install --require-hashes`.** Requires `requirements.lock` exists (Phase 0 should already have shipped this; if not, generate via `pip-compile --generate-hashes`).
7. **Runbook.** Single Markdown file. Each section has stable anchor; cross-link from `README.md`. Update the orchestrator's exit-9 emit (in `src/codegenie/orchestrator/remediate.py` from S6-03) to print the runbook link to stderr — this is a small, surgical edit per Rule 3.
8. **CI workflow well-formedness test.** `tests/ci/test_ci_workflow_well_formed.py` parses YAML, asserts every required job name is present, each has `runs-on` set, the cassette-label workflow exists.

## TDD plan — red / green / refactor

### Red

`tests/ci/test_ci_workflow_well_formed.py`

```python
def test_ci_workflow_has_every_phase4_merge_gate():
    """Every Phase-4 merge-gating job named in High-level-impl §"Step 7"
    must be present in .github/workflows/ci.yml. Drift here means a gate
    landed in a story but never made it into the workflow file."""
    import yaml
    from pathlib import Path

    ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    jobs = set(ci["jobs"].keys())
    required = {
        "fence", "lint", "format", "type",
        "test_unit", "test_integration", "test_adversarial",
        "test_e2e_exit_criterion", "test_phase3_regression",
        "test_phase5_handoff",
        "canary_recall_at_k", "canary_perf", "determinism_canary",
        "security_logs", "linux_only",
    }
    missing = required - jobs
    assert not missing, f"missing CI jobs: {missing}"


def test_cassettes_reviewed_workflow_exists():
    from pathlib import Path
    assert Path(".github/workflows/cassettes-reviewed.yml").exists()


def test_vcr_ban_new_cassettes_set_in_test_env():
    import yaml
    from pathlib import Path
    ci = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    test_job = ci["jobs"]["test_integration"]
    env = test_job.get("env", {})
    assert env.get("VCR_BAN_NEW_CASSETTES") == "1", \
        "test_integration job missing VCR_BAN_NEW_CASSETTES=1"
```

`tests/security/test_no_api_key_in_logs.py`

```python
import re
from pathlib import Path

API_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]{30,}")


def test_no_api_key_in_any_committed_log_or_audit_fixture():
    """G12: the API key must never appear in any committed log or audit fixture.
    This scan runs on every commit; a real key never reaches CI because Phase-3
    EgressProxy holds it (S3-04) and the agent process never sees it.
    A test fixture accidentally containing the prefix is the realistic failure."""
    roots = [
        Path("tests/fixtures/audit"),
        Path("tests/fixtures/logs"),
        Path("tests/fixtures/cassettes"),  # post-sanitization, should also be clean
    ]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            text = p.read_text(errors="replace")
            if API_KEY_PATTERN.search(text):
                hits.append(str(p))
    assert not hits, f"API key prefix found in committed fixtures: {hits}"


def test_redaction_unit_smoke():
    """Confirm the scanner FINDS a key when a known-bad string is present.
    Without this, the negative test would silently pass on a broken regex."""
    sample = "x sk-ant-aB0_-A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9 y"
    assert API_KEY_PATTERN.search(sample) is not None
```

(Analogous red tests for the coverage ratchet via `tools/check_coverage_ratchet.py` invocation; for the runbook anchors via a presence check.)

### Green

For each red test: extend `.github/workflows/ci.yml`, add the missing jobs and env, commit the runbook, wire the scanner. The work is mostly config + Markdown, not new Python.

The "redaction smoke" pattern is important — without it, a regex bug that *never matches* would let the scanner false-pass forever (Rule 12 — fail loud).

### Refactor

- Group CI jobs by phase in `ci.yml` with header comments (`# === Phase 4 — vuln LLM fallback ===`); do not re-order existing jobs (Rule 3).
- Extract the coverage ratchet logic into `tools/check_coverage_ratchet.py` so the per-file targets are data, not workflow YAML.
- The runbook should be **flat** — each section single-purpose, cross-linked, no nested deep hierarchies. The orchestrator's stderr-banner link must point to a specific anchor, not just the top of the file.
- Add a `runbook.md` "How to update this runbook" footer noting that runbook updates land **without** ADR amendments (it's operator-facing, not contract), but additions of *new* operator workflows do trigger ADR amendments.

## Files to touch

| Path | Why |
|---|---|
| `.github/workflows/ci.yml` | Extend with Phase-4 merge gates. |
| `.github/workflows/cassettes-reviewed.yml` | Label-gate for cassette diffs. |
| `.github/scripts/setup-linux-jail.sh` | Linux runner provisioning. |
| `tests/security/test_no_api_key_in_logs.py` | API-key scan + redaction smoke. |
| `tests/ci/test_ci_workflow_well_formed.py` | CI well-formedness gate. |
| `tools/check_coverage_ratchet.py` | Per-file coverage ratchet. |
| `pyproject.toml` (or `.coveragerc`) | Coverage configuration. |
| `requirements.lock` | Pinned + hashed deps (regenerate if needed). |
| `docs/phases/04-vuln-llm-fallback-rag/runbook.md` | The operator runbook. |
| `README.md` | Cross-link to runbook. |
| `src/codegenie/orchestrator/remediate.py` (surgical) | Append runbook link to exit-9 stderr banner. |

## Out of scope

- **Branch-protection rules** — set in repo settings, not in this story's files (documented in the runbook).
- **Mutation testing infrastructure** — Phase 13 maturity.
- **A central audit-events YAML registry** — `../High-level-impl.md` Open question #7, deferred.
- **Pre-commit hooks (local)** — orthogonal to CI; if Phase 0 shipped them, keep them; this story doesn't add new ones.
- **Automated cassette regeneration on model-pin deprecation** — documented in runbook; tooling is Phase 5+.
- **Slack/email notifications on canary drift** — out of phase scope; gate on CI status only.
- **`solved-examples reindex` implementation** — runbook documents the workflow; the CLI subcommand lands in S6-04.

## Notes for the implementer

- Per Rule 3 (surgical changes): the existing `.github/workflows/ci.yml` was authored by Phase 0. Extend, do not rewrite. Preserve job names other phases reference.
- Per Rule 12 (fail loud): every gate must produce a **specific** failure message. "Tests failed" is the wrong shape; "canary_recall_at_k: recall@3=0.83 < 0.85 (3 misses; see tests/canaries/_last_run.json)" is the right shape. S7-03's diagnostic JSON is the input to this.
- The `cassettes-reviewed` label workflow is **the most important social gate** in Phase 4 — it's the human-review checkpoint that keeps the cassette corpus from drifting silently against the live SDK. Make the workflow's failure message direct: "PR touches `tests/fixtures/cassettes/`; add the `cassettes-reviewed` label after a human reviews the cassette diff." No clever phrasing.
- The runbook is the **operator-facing surface**. Write it as if the reader is debugging a CI failure they've never seen before. Each anchor must answer the question "what do I do now?" without forcing the reader back through `phase-arch-design.md`.
- The orchestrator's stderr banner edit is **the single Phase-4 edit outside `src/codegenie/{llm,rag,planner,recipes/engines}/`**. Keep it to literally one line per exit reason. Don't refactor the orchestrator's error-path while you're there (Rule 3).
- Coverage ratchets are a **trailing indicator**, not a leading one. The contract files are at 95/90 because that's where Phase 5 inherits — coverage gaps here are pre-shipped contract bugs. New-package code is at 90/80 because that's the standard floor.
- The Linux-only job needs `bubblewrap` (Debian/Ubuntu pkg) and the runner needs the `agent` UID. The setup script is committed at `.github/scripts/setup-linux-jail.sh` and runs as the first step of the `linux_only` job. Document the script's preconditions in the runbook.
- The `VCR_BAN_NEW_CASSETTES=1` env var is the **load-bearing CI invariant** for hermetic-replay. Without it, a missing cassette would record-once silently and merge — defeating the whole `pytest-recording` discipline (S3-06). Set it on every `test_*` job, not just `test_integration`.
- Per `../High-level-impl.md §"Implementation-level risks"` row 7 (prompt-template versioning + cassette golden interaction): a legitimate prompt edit invalidates every recorded cassette. Document the workflow inline in the runbook's `## Cassette regeneration` section. Engineers will hit this once a quarter; the workflow must be clear or they'll work around it.
- The redaction smoke test pattern (the test that confirms the regex DOES match a known-bad string) is the canonical defense against a broken-scanner false-pass. Apply it elsewhere — the cassette-sanitizer pre-commit needs the same shape.
- The model-pin deprecation runbook section (ADR-P4-007) names the 60-day warning. CI surfaces the warning as a status check from `tools/check_model_pin_deprecation.py` (Phase-0 may already have a similar gate — confirm before adding a duplicate).
- Cross-linking the runbook from CLI exit banners is the **second** instance of the "exit-9 + runbook anchor" pattern (Phase 3 may have shipped the first). If so, follow Phase 3's convention; if not, this story sets the convention for future phases (Phase 5+).
- The coverage ratchet check script lives under `tools/` (Phase 0 convention), not `scripts/`. Match conventions (Rule 11).
- Per `../High-level-impl.md §"What's next — handoff to Phase 5"`: every Phase-4 artifact on disk is consumed by Phase 5. The runbook is the single document a Phase-5 author opens first. Write for that reader.
