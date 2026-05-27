# Story S7-11 — Cassette-recording authorization bridge (S6-07/S7-06/S7-07 unblocker)

**Step:** Step 7 — Ship plugin wiring + E2E exit criteria (bridge: authorization-gate)
**Status:** Ready (new story; authored 2026-05-27 by phase-story-executor as the explicit "If there is a block, write a new story" path the active goal authorized)
**Effort:** S (one operator action + observable acceptance; the executor cannot self-fulfill — see Goal)
**Depends on:** S3-04 (CassetteSanitizer shipped), S3-05 (cassettes.lock + CI scanner shipped), S3-06 (CODEOWNERS + `make refresh-cassettes` ergonomic + `docs/operations/cassettes.md` runbook shipped — verified on master via S7-10 Attempt #1 of `docs/operations/cassettes.md`)
**Unblocks:** S6-07 (determinism-cassette-replay property), S7-06 (E2E breaking-change), S7-07 (E2E replay-lands-RAG)

## Context

Phase 4's E2E exit-criterion stories (S6-07, S7-06, S7-07) cannot run in CI today because the Anthropic cassettes they replay do not exist on master. The cassette-recording path is operational (S3-04 sanitizer + S3-05 lock + S3-06 runbook + `make refresh-cassettes` + CODEOWNERS approval flow — all GREEN on master), but **executing it spends real Anthropic API tokens**. The executor cannot self-authorize that spend; CLAUDE.md §"Cassette workflow" makes the human-authorization gate explicit: *"Never run `pytest --record-mode=all` directly; always go through the make target so the explicit-acknowledgement gate fires."*

S6-07/S7-06/S7-07 have all been HARDENED for weeks; they're not blocked on engineering work, only on the human-authorization step that's deliberately not automated.

This story is the **bridge artifact**: one observable operator action + an acceptance check that the resulting cassettes flow through the pre-existing S3-04/S3-05/S3-06 discipline, after which S6-07/S7-06/S7-07 can run their full TDD plans without further bridge work.

## References — where to look

- **`docs/operations/cassettes.md`** — the runbook (shipped in S7-10 Attempt #1). Names the refresh-trigger matrix, the `make refresh-cassettes` invocation, the CODEOWNERS approval flow, the BLAKE3 lock-refresh discipline, and the `CassetteSanitizer` guarantees.
- **`Makefile` — `refresh-cassettes` target** (shipped in S3-06). Mandates `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`; CODEGENIE_LIVE_LLM=1 environment plumbing.
- **`tests/cassettes/anthropic/cassettes.lock`** — BLAKE3 manifest (shipped in S3-05); the CI scanner `tests/security/test_cassettes_clean.py` checks every cassette against this.
- **S6-07 story** — determinism property over 50 cassette-replay runs.
- **S7-06 story** — E2E breaking-change test (express CVE major bump).
- **S7-07 story** — E2E replay-lands-RAG (second-run hits RAG, lower cost).

## Goal

The cassette-stewart (per CODEOWNERS) runs **one** authorized recording session producing the cassettes S6-07/S7-06/S7-07 need; the recording flows through `CassetteSanitizer` (S3-04) + lands a refreshed `cassettes.lock` (S3-05) + passes `tests/security/test_cassettes_clean.py` (S3-05) + this story's three new acceptance tests verifying each downstream story's cassette set is present + structurally non-empty + sanitized.

**The executor cannot self-fulfill this story.** This story exists so a future operator can:
1. Read this file.
2. Run the documented commands.
3. Verify the acceptance tests pass.
4. Mark this story Done.
5. Resume S6-07/S7-06/S7-07 with their TDD plans now reachable.

## Acceptance criteria

- [ ] **AC-1 — Cassette set for S6-07 exists.** `tests/cassettes/anthropic/s6_07_determinism/*.yaml` contains ≥ 1 cassette captured under `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1 CODEGENIE_LIVE_LLM=1`. Per the existing `CassetteSanitizer` (S3-04), every recorded cassette is stripped of `Authorization`/`X-API-Key`/`Cookie`/`anthropic-version` headers and body-scanned for `sk-ant-*`/`claude_*`/40+-char base64 patterns. **Acceptance test:** `tests/integration/test_s7_11_cassette_set_s6_07.py` asserts the directory contains at least one cassette file + the file passes `tests/security/test_cassettes_clean.py`'s scanner shape.
- [ ] **AC-2 — Cassette set for S7-06 exists.** `tests/cassettes/anthropic/s7_06_e2e_breaking_change/*.yaml` per the same shape — captures the leaf-LLM invocation for the express-cve-2026-1234 fixture's major-bump CVE path. **Acceptance test:** `tests/integration/test_s7_11_cassette_set_s7_06.py`.
- [ ] **AC-3 — Cassette set for S7-07 exists.** `tests/cassettes/anthropic/s7_07_e2e_replay_lands_rag/*.yaml` — captures the second-run-hits-RAG E2E's two leaf-LLM invocations (first run produces the seeded record; second run reads from RAG). **Acceptance test:** `tests/integration/test_s7_11_cassette_set_s7_07.py`.
- [ ] **AC-4 — `cassettes.lock` refreshed in the same commit.** The BLAKE3 manifest (S3-05) is regenerated and committed alongside the new cassettes; `pre-commit run --files tests/cassettes/anthropic/cassettes.lock` is clean. **Acceptance test:** the existing `tests/security/test_cassettes_clean.py` (S3-05) runs on the new cassettes without skipping any.
- [ ] **AC-5 — CODEOWNERS approval recorded.** The recording PR is approved by the named cassette-steward per `CODEOWNERS` (S3-06); the approval timestamp + steward identity appear in the PR commit trailer (`Co-Authored-By` line or `Approved-By` trailer). Acceptance: a human-verifiable PR artifact; no automated test for this AC.
- [ ] **AC-6 — `docs/operations/cassettes.md` rotation-cadence entry updated.** The `## Rotation cadence` section names the recording-session date + the next-scheduled-refresh date (per the S7-10 Attempt #1-shipped quarterly cadence). **Acceptance test:** `tests/integration/test_ops_docs_exist.py` (S7-10 AC-16) parses the section and asserts a non-empty body that contains an ISO-shaped date (`\d{4}-\d{2}-\d{2}`).
- [ ] **AC-7 — Story status flip.** After AC-1..AC-6 are green, this story file's `Status:` flips to `Done`. The operator records the spend (token count, USD cost) in a single-line section appended to this story file as audit trail.

## Implementation outline

The operator executes the following sequence; the executor records each acceptance test alongside.

1. **Pre-flight checks** (executor authors these as `tests/integration/test_s7_11_preflight.py` — runs without recording):
   - `CassetteSanitizer` import succeeds.
   - `tests/cassettes/anthropic/cassettes.lock` exists and parses as BLAKE3 manifest shape.
   - The fixture `tests/fixtures/repos/express-cve-2026-1234/` exists and contains a `package.json` (precondition; S7-05 ships this).
2. **Operator action** (NOT executor-runnable):
   ```bash
   export ANTHROPIC_API_KEY=$(keyring get codegenie anthropic_api_key)
   make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1 CODEGENIE_LIVE_LLM=1
   ```
   This invocation:
   - Spins up the S6-07/S7-06/S7-07 test fixtures.
   - Routes the leaf-LLM calls through `pytest-recording` + `CassetteSanitizer`.
   - Writes the cassette YAMLs under the three story-specific subdirectories.
   - Recomputes BLAKE3 + appends to `cassettes.lock` (S3-05).
   - Reports the dollar cost + token count to stdout.
3. **Operator action — review the diff:**
   - Verify every new cassette under `tests/cassettes/anthropic/` is sanitized (the S3-04 hooks ran).
   - Verify `cassettes.lock` covers every new cassette.
4. **Operator action — record the audit trail:**
   - Append a one-line entry to this story file under `## Audit trail` with the recording date, the steward's GitHub handle, the token count, the USD cost.
5. **Operator action — flip status:**
   - Change `Status: Ready` → `Status: Done` at the top of this file.
   - Run `pytest tests/integration/test_s7_11_*.py` and verify all six acceptance tests pass.
6. **Operator action — open downstream stories:**
   - With cassettes now on master, S6-07 / S7-06 / S7-07 are unblocked.

## TDD plan — preflight + acceptance scaffolding

The executor pre-builds the acceptance tests as **skip-when-cassettes-absent** so they document the expected shape without failing on a clean master. When the operator runs the recording session, the same tests unskip and pass.

```python
# tests/integration/test_s7_11_cassette_set_s6_07.py
"""S7-11 AC-1 — S6-07 determinism-property cassette set exists + is sanitized."""
from __future__ import annotations
from pathlib import Path
import pytest

_CASSETTES_DIR = Path("tests/cassettes/anthropic/s6_07_determinism")


def test_s6_07_cassette_set_present_or_loudly_skips() -> None:
    if not _CASSETTES_DIR.exists():
        pytest.skip(
            "S6-07 cassettes not recorded yet — S7-11 AC-1 not satisfied. "
            "Operator path: run `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`."
        )
    cassettes = list(_CASSETTES_DIR.glob("*.yaml"))
    assert cassettes, (
        f"S7-11 AC-1: {_CASSETTES_DIR} exists but contains no .yaml cassettes. "
        f"Re-run make refresh-cassettes or remove the empty directory."
    )
```

(Identical scaffolding for `test_s7_11_cassette_set_s7_06.py` + `test_s7_11_cassette_set_s7_07.py`, parametrized over the three subdirs.)

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_s7_11_preflight.py` | New — pre-flight checks (executor can land today). |
| `tests/integration/test_s7_11_cassette_set_s6_07.py` | New — AC-1 acceptance with loud-skip-when-absent (executor can land today). |
| `tests/integration/test_s7_11_cassette_set_s7_06.py` | New — AC-2 acceptance with loud-skip-when-absent. |
| `tests/integration/test_s7_11_cassette_set_s7_07.py` | New — AC-3 acceptance with loud-skip-when-absent. |
| `tests/cassettes/anthropic/s6_07_determinism/*.yaml` | Operator-recorded under AC-1. |
| `tests/cassettes/anthropic/s7_06_e2e_breaking_change/*.yaml` | Operator-recorded under AC-2. |
| `tests/cassettes/anthropic/s7_07_e2e_replay_lands_rag/*.yaml` | Operator-recorded under AC-3. |
| `tests/cassettes/anthropic/cassettes.lock` | Operator-refreshed under AC-4 (S3-05). |
| `docs/operations/cassettes.md` | Operator-updates `## Rotation cadence` section per AC-6. |
| `docs/phases/04-vuln-llm-fallback-rag/stories/S7-11-cassette-authorization-bridge.md` | This file — status flip under AC-7. |

## Out of scope

- Re-implementing the cassette pipeline. S3-04/S3-05/S3-06 already shipped everything; S7-11 is a bridge story, not a re-implementation.
- Automating the token-spend authorization. CLAUDE.md §"Cassette workflow" explicitly mandates the human-acknowledgement gate; bypassing it is an ADR-level decision.
- The downstream story executions themselves (S6-07/S7-06/S7-07). Those have their own TDD plans; S7-11 unblocks them, doesn't replace them.

## Notes for the implementer (the operator, not the executor)

- **Token spend estimate.** S6-07's 50-run determinism property re-uses the same cassette N times — the actual recording is a single Anthropic call. S7-06's E2E records one full plan-and-trust cycle. S7-07's E2E records two (first-run + second-run-hits-RAG). Total: ≤ 4 Anthropic API calls, all bounded by `LlmInvocationGuard.running_total` to the per-call cap shipped in `phase4-config.yaml` (`per_call_max_tokens: 32_000`). Expected total cost: well under $1.
- **Steward rotation.** Per `docs/operations/cassettes.md §CODEOWNERS approval flow`, the cassette-steward role rotates quarterly. The recording session counts as one steward turn; record it in the rotation log.
- **Sanitizer self-test.** Before pushing the recording PR, the operator runs `pytest tests/unit/fallback/test_cassette_sanitizer.py` to verify the sanitizer's idempotence property (sanitize ∘ sanitize ≡ sanitize) holds on the new cassettes. This catches a regression where a future Anthropic SDK upgrade emits a header shape the sanitizer doesn't strip.
- **Reverse-bridge:** if the recording session reveals that S6-07/S7-06/S7-07's TDD plans need adjustment (e.g., a fixture's hand-authored `package.json` doesn't trigger the expected CVE detection path), the operator opens a sibling story rather than amending S7-11. S7-11's success criterion is exactly the four operator actions producing the four sets of artifacts; downstream TDD adjustments are downstream stories' concerns.

## Audit trail

*(Operator appends here after the recording session completes.)*

| Date | Steward | Token count | USD cost | Cassette commit hash |
|---|---|---|---|---|
| — | — | — | — | — |
