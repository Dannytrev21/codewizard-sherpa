# Story S8-03 — E2E `tests/e2e/test_remediate_with_sandbox.py` against `breaking-change-cve`

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready (HARDENED 2026-05-26 — see [`_validation/S8-03-e2e-remediate-with-sandbox.md`](_validation/S8-03-e2e-remediate-with-sandbox.md))
**Effort:** L
**Depends on:** S2-01, S2-02, S2-03, S3-05, S5-01, S5-02, S5-05, S6-04, S6-05, S7-03, S8-01, S8-02
**ADRs honored:** ADR-0002, ADR-0005, ADR-0007, ADR-0010, ADR-0012, ADR-0013

## Validation notes (2026-05-26)

Hardening summary (full audit in [`_validation/S8-03-e2e-remediate-with-sandbox.md`](_validation/S8-03-e2e-remediate-with-sandbox.md)):

- **Block-tier corrections to upstream contract surfaces re-applied** — JSONL discriminator is `"type"` (S2-01 AC-T-1), not `"kind"`; cassette is the single file `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` with two interactions (S5-05 HARDENED), not a two-file `tests/fixtures/vcr/cassette-attempt-{1,2}.yaml` layout that doesn't exist; `chain_head.bin` lives at `run_dir / "chain_head.bin"` (S2-03), not `run_dir.parent`.
- **Provenance assertion added** — a `CliRunner` invocation can produce all on-disk artifacts without ever invoking a real sandbox or the replan hook; the test now injects a `ReplanHookSpy` Decorator via S8-02's `make_orchestrator` DI port (AC-TEST-ORC-1) and asserts `spy.call_count == 1` + `spy.calls[0].prior_attempts[0].attempt_id == 1` + `Phase4Interaction[1].prior_attempts_serialized != ""` from the cassette.
- **Determinism + offline replay pinned** — `@pytest.mark.timeout(300)`, `@pytest.mark.vcr(...)`, `block_network` fixture; `--no-cov` in the AC invocation; sibling triple-replay-stability test for process-level cassette determinism (S5-05 AC-CASS-DET-1 precedent).
- **Run-dir resolution made deterministic** — `iterdir()` arbitrary order replaced with structured `run_id` parsed from `result.output`'s `remediate.completed` event + an exactly-one-child assertion as a tripwire.
- **Typed accessors over raw dict-shuffling** — every per-attempt field flows through `ledger.entries()` / `ledger.attempts()` returning the `LedgerEntry = PreExecuteMarker | Attempt` discriminated union and `Attempt` Pydantic models; the literal `json.loads(...)["sandbox_run_id"]` / `["patch_blake3"]` / `["outcome"]["state"]` patterns are removed.
- **Field-path guessing removed** — `SandboxCostEntry.backend: Literal["docker_in_docker", "firecracker"]` (per ADR-0010) is the canonical backend accessor; "or wherever the backend is recorded" hand-wave deleted.
- **Cross-ledger invariants added** — `{p.sandbox_run_id for p in cost_rows} == {a.sandbox_run_id for a in attempts}` bijection; pre-run `chain_head.bin` snapshot proving Phase-5 extended the chain (post != pre); `len(post_run_head) == 32`; `ledger.entries()` re-verifies BLAKE3 across `PreExecuteMarker | Attempt` rows in one pass (S2-02 AC-DR-1).
- **Positive shape checks before distinctness** — UUID7 regex on `sandbox_run_id`, 64-hex-char on `patch_blake3`, both attempts have the field — `KeyError` and `None != None` failure modes eliminated.
- **Ordered sequence asserted, not just counts** — `[entry.type for entry in ledger.entries()] == ["pre_execute", "attempt", "pre_execute", "attempt"]` catches misordered emissions that the count-only `len == 2` check missed.
- **Secret-leak grep rephrased as tripwire** — primary defense is ADR-0012's `tests/schema/test_env_allowlist_no_credentials.py` + `tests/adversarial/test_postinstall_exfil.py`; this E2E adds a regex catalog (`<NAME>_(KEY|TOKEN|SECRET|PASSWORD)\s*[:=]`, `sk-ant-api03-…`, `ghp_…`, `AKIA…`) extracted to `src/codegenie/sandbox/env_allowlist.py#CREDENTIAL_DENY_SUBSTRINGS` as the SSOT (rule-of-three: this E2E + schema test + Phase-7 distroless E2E).
- **macOS auto-detect proves the DinD path** — structlog event capture asserts exactly one `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` with `backend == "docker_in_docker"` (S8-02 AC-FALL-1 precedent).
- **Cross-OS OR-escape-hatch removed** — single-runner monkeypatch path covers branch coverage of `_kvm_available`; real Linux-KVM coverage is owned by S6-05's KVM smoke test, explicitly named.
- **`policy.json` / `trace.unavailable` content-invariants pinned** — three top-level keys (S3-05 AC-GOLDEN-2); XOR not OR; `trace.unavailable` must declare structured `{reason, platform}`.
- **CVE id resolved by reading fixture metadata** — `cve_id = yaml.safe_load((e2e_repo / "metadata.yaml").read_text())["cve_id"]`; no literal CVE id in the test body (closes the `CVE-2026-FIXTURE` vs `CVE-2026-XXXX` drift).
- **`Depends on:` widened** to every upstream story whose contract surface is exercised; **`ADRs honored:`** now includes ADR-0012 + ADR-0013 (cited inline by ACs).

No `NEEDS RESEARCH` items remained unresolved; both research candidates resolved to in-codebase kernels (S8-02 `make_orchestrator` DI port; ADR-0012 deny-substring filter constants).

## Context

This is the **headline exit-criterion test** for Phase 5. Roadmap §"Phase 5" requires: *"No transform leaves the sandbox unverified. The three-retry loop is demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2."* S5-05 already lands the integration test at the `GateRunner` level; this story lands the **full process** test: `codegenie remediate --cve <fixture-cve>` invoked via `click.testing.CliRunner` against `tests/fixtures/repos/breaking-change-cve/`, exercising every Phase 5 surface (DinD or Firecracker auto-detect, `RetryLedger` BLAKE3 chain extension, replan hook into Phase 4, cost-emitter, audit events) in one shot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Test strategy — E2E (~5%)` — exact file path `tests/e2e/test_remediate_with_sandbox.py`; budget 300 s.
  - `../phase-arch-design.md §Process view` — sequence diagram covering remediate → orchestrator → Phase 4 → GateRunner → SandboxClient → ledger; the assertions in this story trace those edges.
  - `../phase-arch-design.md §Component design — RetryLedger` — file layout `.codegenie/remediation/<run-id>/gates/<gate_id>/{attempts.jsonl,manifest.yaml}` + per-attempt `sandbox/<sandbox_run_id>/{stdout.log,stderr.log,trace.jsonl,policy.json,sbom.json}` + `.codegenie/remediation/<run-id>/chain_head.bin` at the per-run level.
  - `../phase-arch-design.md §Fixtures and data` — `tests/fixtures/repos/breaking-change-cve/` is the exit-criterion fixture; the canonical recorded cassette is **the single file** `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` (S5-05 HARDENED) with two `interactions[]` entries, in order.
- **Phase ADRs:**
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — attempt 2's prompt receives the attempt-1 `AttemptSummary` via the additive `prior_attempts` kwarg + a fenced block ≤ 4 KB; verified at this layer by introspecting the cassette's second interaction via `extract_phase4_interactions` (S5-05 helper).
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — Phase 4's `chain_head.bin` is consumed at startup AND re-written post-run; the test verifies both the post-run head matches the on-disk file AND that the head *advanced* from its pre-run value.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — every attempt writes a `pre_execute` marker (JSONL row with `"type": "pre_execute"`) BEFORE the `attempt` row (`"type": "attempt"`); markers participate in the BLAKE3 chain; the test inspects both ordered rows via `ledger.entries()`.
  - `../ADRs/0010-cost-sandbox-run-ledger-schema.md` — one `SandboxCostEntry` per attempt in `.codegenie/cost/sandbox.jsonl`; `SandboxCostEntry.backend: Literal["docker_in_docker", "firecracker"]` is the canonical backend accessor.
  - `../ADRs/0012-env-allowlist-and-credential-deny.md` — env-allowlist filtering ensures credentials never reach the sandbox; primary defense is `tests/schema/test_env_allowlist_no_credentials.py` + `tests/adversarial/test_postinstall_exfil.py`; this story adds an E2E tripwire (regex-shape catalog imported from `src/codegenie/sandbox/env_allowlist.py#CREDENTIAL_DENY_SUBSTRINGS`).
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — the per-attempt `sandbox/<sandbox_run_id>/policy.json` is the *resolved* policy used at runtime, derived from the digest-pinned `tools/policy/sandbox-policy.yaml`; minimum content invariant per S3-05 AC-GOLDEN-2: three top-level keys `lockfile`, `runtime_trace`, `test_inventory`.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three retries baseline; this test runs with the default (no override) and the fixture is expected to recover on attempt 2.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Three-retry loop with replan hook"` — the exit-criterion expectation.
- **Existing code:**
  - `tests/fixtures/repos/breaking-change-cve/` and `tests/fixtures/repos/breaking-change-cve/metadata.yaml` (S5-05 — the canonical fixture; the `cve_id` field is part of the `.expected/` Specification-pattern contract).
  - `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` (S5-05 — single cassette, two interactions; cassette discipline lives at `docs/operations/cassettes.md`).
  - `tests/integration/_helpers/vcr.py` — `extract_phase4_interactions(cassette) -> list[Phase4Interaction]` (S5-05 HARDENED helper).
  - `tests/integration/_helpers/hooks.py` — `ReplanHookSpy` Decorator (S5-05 HARDENED).
  - `src/codegenie/cli/remediate.py` after S8-02; `make_orchestrator(...)` DI port (S8-02 AC-TEST-ORC-1).
  - `src/codegenie/sandbox/env_allowlist.py` — `CREDENTIAL_DENY_SUBSTRINGS` (rule-of-three SSOT, this story extracts).
  - `src/codegenie/gates/retry_ledger.py` — `RetryLedger.entries()`, `RetryLedger.attempts()`, `RetryLedger.head()`; `LedgerEntry = PreExecuteMarker | Attempt`.
  - `tests/integration/gates/test_stage6_retry_recovers.py` (S5-05) — same fixture, integration-level scope.

## Goal

Land `tests/e2e/test_remediate_with_sandbox.py` that invokes `codegenie remediate --cve <fixture-cve> --repo <fixture-path>` via `click.testing.CliRunner` against the `breaking-change-cve` fixture end-to-end, with `make_orchestrator` injected to wrap the replan hook in a `ReplanHookSpy`. The test must assert: (a) the replan hook fired exactly once between attempts with the attempt-1 summary in the `prior_attempts` kwarg, (b) the gate passes on attempt 2 with two ordered `pre_execute` + `attempt` JSONL rows whose `sandbox_run_id` and `patch_blake3` values are well-shaped and distinct, (c) `chain_head.bin` advanced from its pre-run value and equals the post-run `ledger.head()`, (d) exactly two `SandboxCostEntry` rows in `sandbox.jsonl` whose `sandbox_run_id` set equals the attempts' set, (e) exit code 0, (f) every evidence-bundle path exists with verified content shape, (g) no credential-shaped string leaks into any artifact.

## Acceptance criteria

- [ ] `tests/e2e/test_remediate_with_sandbox.py` exists, is marked `@pytest.mark.e2e` and `@pytest.mark.timeout(300)`, and decorated with `@pytest.mark.vcr("../integration/gates/cassettes/stage6_retry_recovers.yaml")` so the single S5-05 cassette is replayed.
- [ ] The test function signature is `def test_retry2_recovers_end_to_end(e2e_repo: Path, vcr_cassettes, block_network, monkeypatch) -> None:` — `block_network` is consumed (any escape attempt during replay raises `CannotOverwriteExistingCassetteException` rather than silently re-recording).
- [ ] Before invocation: `monkeypatch.setenv("CODEGENIE_HOME", str(e2e_repo / ".codegenie"))` (isolates the run from the developer's `~/.codegenie/`).
- [ ] The CVE id is read from the fixture's metadata at test time: `cve_id = yaml.safe_load((e2e_repo / "metadata.yaml").read_text())["cve_id"]` — no literal CVE id (`CVE-2026-XXXX`, `CVE-2026-FIXTURE`) appears in the test body.
- [ ] A `ReplanHookSpy` is injected into the orchestrator via `monkeypatch.setattr("codegenie.cli.remediate.make_orchestrator", make_orchestrator_with_spy)` where `make_orchestrator_with_spy` wraps the default `replan_hook` in `ReplanHookSpy(...)` (S8-02 AC-TEST-ORC-1 DI port).
- [ ] The test invokes `CliRunner().invoke(cli, ["remediate", "--cve", cve_id, "--repo", str(e2e_repo)])` and asserts **`result.exit_code == 0`** with `result.output` in the assertion message.
- [ ] After invocation:
  - [ ] `spy.call_count == 1` (hook fired exactly once between attempts).
  - [ ] `spy.calls[0].prior_attempts[0].attempt_id == 1` (the attempt-1 summary was carried into attempt 2).
  - [ ] `len(spy.calls[0].prior_attempts) == 1` (no duplicates; ADR-0002 kwarg shape).
- [ ] The cassette's second interaction carries the fence: via `interactions = extract_phase4_interactions(cassette_path); len(interactions) == 2; assert "BEGIN_PRIOR_ATTEMPT_" in interactions[1].prompt_text; assert interactions[0] does not contain "BEGIN_PRIOR_ATTEMPT_"`; the fence body slice is `≤ 4096` bytes (ADR-0002 §Tradeoffs cap).
- [ ] Run-dir resolution is deterministic: the run-id is parsed from `result.output`'s structured `remediate.completed` event (`run_id` field) AND `len(list((e2e_repo / ".codegenie" / "remediation").iterdir())) == 1` is asserted as a tripwire — a fall-through to `next(iterdir())` is disallowed.
- [ ] `attempts.jsonl` at `.codegenie/remediation/<run-id>/gates/stage6_validate/attempts.jsonl` exists and is read **exclusively** via `ledger = RetryLedger.open_existing(run_dir, gate_id="stage6_validate"); entries = ledger.entries(); attempts = ledger.attempts()`. No `json.loads(line)["kind"]` or `json.loads(line)["type"]` literal subscripts appear in the test body — the test consumes the typed `LedgerEntry = PreExecuteMarker | Attempt` discriminated union (S2-02 AC-DR-1 + S8-01 HARDENED contract).
- [ ] The *ordered* sequence is asserted: `[entry.type for entry in entries] == ["pre_execute", "attempt", "pre_execute", "attempt"]` (defeats writers that emit the four rows in wrong order, ADR-0007 regression).
- [ ] `len(attempts) == 2`; `attempts[0].outcome.state == "failed_retryable"`; `attempts[1].outcome.state == "passed"`; `attempts[0].attempt_id == 1`; `attempts[1].attempt_id == 2`.
- [ ] Positive shape, then distinctness:
  - [ ] Both `attempts[i].sandbox_run_id` match `^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (UUID7).
  - [ ] Both `attempts[i].patch_blake3` match `^[0-9a-f]{64}$` (BLAKE3 hex digest).
  - [ ] `attempts[0].sandbox_run_id != attempts[1].sandbox_run_id`.
  - [ ] `attempts[0].patch_blake3 != attempts[1].patch_blake3`.
  - [ ] `attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]` (S5-05 precedent — paths-first-then-content; rules out overwritten / shared workdir mutations).
- [ ] BLAKE3 chain is verified via `entries()` — the call returns without raising `AuditChainCorrupted`, proving the chain holds across `PreExecuteMarker | Attempt` rows in one pass (S2-02 AC-DR-1).
- [ ] `chain_head.bin` advancement:
  - [ ] Pre-run snapshot `pre_head = (run_dir / "chain_head.bin").read_bytes()` if file exists else `b""`.
  - [ ] After the run, `post_head = (run_dir / "chain_head.bin").read_bytes()`; `len(post_head) == 32` (32-byte BLAKE3, not empty).
  - [ ] `post_head != pre_head` (chain advanced through Phase 5 per ADR-0005).
  - [ ] `post_head == ledger.head()` (the file equals what the re-read ledger derives).
- [ ] `.codegenie/cost/sandbox.jsonl` exists with **exactly two** rows, each parsed via `SandboxCostEntry.model_validate_json(line)`; the bijection across ledgers holds:
  - [ ] `{p.attempt_id for p in parsed} == {1, 2}`.
  - [ ] `{p.sandbox_run_id for p in parsed} == {a.sandbox_run_id for a in attempts}` (set equality — cost-row ↔ attempts-row cross-link).
  - [ ] `parsed_by_id[1].sandbox_run_id == attempts[0].sandbox_run_id` AND `parsed_by_id[2].sandbox_run_id == attempts[1].sandbox_run_id` (order-correct).
- [ ] Per-attempt evidence directories `.codegenie/remediation/<run-id>/gates/stage6_validate/sandbox/<sandbox_run_id>/` exist for both attempts and each contains:
  - [ ] `stdout.log` exists with non-zero size.
  - [ ] `stderr.log` exists.
  - [ ] `sbom.json` exists and `json.loads(...)` parses (non-empty object).
  - [ ] `policy.json` exists and `json.loads(...)` parses to an object containing all three top-level keys: `"lockfile"`, `"runtime_trace"`, `"test_inventory"` (per S3-05 AC-GOLDEN-2).
  - [ ] **Exactly one of** `trace.jsonl` *or* `trace.unavailable` exists (XOR — both present is a bug). If `trace.unavailable`, it parses as JSON containing `{"reason": <non-empty str>, "platform": <"darwin" | "linux">}`.
- [ ] Credential-shape tripwire: import `from codegenie.sandbox.env_allowlist import CREDENTIAL_DENY_SUBSTRINGS` (rule-of-three SSOT; the production filter and the audit must share the deny set) and grep all files under `run_dir` against each regex pattern in `CREDENTIAL_DENY_SUBSTRINGS`; assert zero matches. (This is a tripwire — the *primary* credential-leak defenses are `tests/schema/test_env_allowlist_no_credentials.py` + `tests/adversarial/test_postinstall_exfil.py` per ADR-0012.)
- [ ] No `--max-attempts-override` / `--operator-ack` flags appear in the CLI invocation — the test exercises the production-ADR-0014 default of 3 retries with the fixture expected to recover on attempt 2.
- [ ] `pytest -m e2e tests/e2e/test_remediate_with_sandbox.py --no-cov` passes (the `--no-cov` flag is required because the default `addopts` includes `--cov-fail-under=85`, which a single-test invocation cannot satisfy; see `CLAUDE.md` cassette workflow guidance).
- [ ] A second test in the same module, `test_e2e_macos_auto_detect_uses_did(e2e_repo, vcr_cassettes, block_network, monkeypatch)`:
  - [ ] `monkeypatch.setattr("codegenie.sandbox.registry._kvm_available", lambda: False)`.
  - [ ] Uses `structlog.testing.capture_logs()` to capture events during invocation.
  - [ ] Asserts `result.exit_code == 0`.
  - [ ] Asserts exactly one structlog event with `event == EVENT_SANDBOX_AUTO_DETECT_FALLBACK` fired with `backend == "docker_in_docker"` (S8-02 AC-FALL-1 precedent; the event constant is imported, not duplicated as a string).
  - [ ] Asserts both `SandboxCostEntry.backend == "docker_in_docker"` for both attempts via the typed Literal accessor on the parsed cost rows (per ADR-0010).
- [ ] A sibling test file `tests/e2e/test_remediate_with_sandbox_replay_stable.py::test_replay_stability(@pytest.mark.cassette_stability)`:
  - [ ] Runs the same scenario three times in fresh `tmp_path` dirs in the same pytest session.
  - [ ] Asserts the tuple `(result.exit_code, ledger.head(), tuple(sorted((p.attempt_id, p.sandbox_run_id) for p in parsed)))` is byte-identical across all three runs (process-level cassette-replay determinism; S5-05 AC-CASS-DET-1 precedent at the process level).
- [ ] `tests/e2e/_paths.py` exists and exports `resolve_run_dir(e2e_repo: Path, result_output: str) -> Path` and `resolve_cost_jsonl(run_dir: Path) -> Path`; the headline test and the macOS-fallback test both consume them (S8-04's coverage check will reuse — rule-of-three: this story's two tests + S8-04). No duplicated path-resolution literals remain in the test bodies.
- [ ] `src/codegenie/sandbox/env_allowlist.py` exports `CREDENTIAL_DENY_SUBSTRINGS: Final[tuple[re.Pattern[bytes], ...]]` (the regex catalog targeting credential *shape*, not bare uppercase substrings; minimum patterns: `<NAME>_(KEY|TOKEN|SECRET|PASSWORD)\s*[:=]\s*\S+`, `sk-ant-api03-[A-Za-z0-9_-]{20,}`, `ghp_[A-Za-z0-9]{36,}`, `AKIA[0-9A-Z]{16}`); `tests/schema/test_env_allowlist_no_credentials.py` (ADR-0012) is updated additively to import from the same constant.
- [ ] `pyproject.toml` registers the `e2e` marker and the `cassette_stability` marker; existing `--strict-markers` setting is unchanged (do not duplicate).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/e2e`, `pytest -m e2e tests/e2e/test_remediate_with_sandbox.py --no-cov`, and `pytest -m cassette_stability tests/e2e/test_remediate_with_sandbox_replay_stable.py --no-cov` all pass.
- [ ] TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. Create `tests/e2e/__init__.py` and `tests/e2e/conftest.py`.
2. `tests/e2e/conftest.py` exposes two fixtures:
   - `e2e_repo` — copies `tests/fixtures/repos/breaking-change-cve/` to `tmp_path` so the test never mutates the source fixture; returns the destination `Path`. Source path lives in a single module-level constant `_FIXTURE_REPO_NAME = "breaking-change-cve"` (forward-compatibility for Phase-7's distroless E2E — see Notes for the implementer).
   - `vcr_cassettes` — reuses the existing `vcr_config` plus `cassette_library_dir`; points the test at the single S5-05 cassette at `tests/integration/gates/cassettes/`. Does NOT redefine `record_mode` — the root `tests/conftest.py` already pins `RecordMode.NONE` (or `all` only when `CODEGENIE_LIVE_LLM=1` per the runbook); the `block_network` fixture is parametrized into the test to assert offline replay.
3. `tests/e2e/_paths.py`:
   - `resolve_run_dir(e2e_repo, result_output) -> Path` — parses the run-id from the structured `remediate.completed` log event in `result_output`; asserts exactly one child dir under `.codegenie/remediation/`; returns it.
   - `resolve_cost_jsonl(run_dir) -> Path` — returns `run_dir.parent.parent / "cost" / "sandbox.jsonl"` (i.e., `.codegenie/cost/sandbox.jsonl`).
4. Extract `CREDENTIAL_DENY_SUBSTRINGS` to `src/codegenie/sandbox/env_allowlist.py` if not already present (rule-of-three SSOT). Update `tests/schema/test_env_allowlist_no_credentials.py` additively to import from there (no behavior change at the schema test layer).
5. `tests/fixtures/repos/breaking-change-cve/metadata.yaml` — confirm or land a `cve_id` field (S5-05 fixture-contract extension). The test reads it; the value is whatever S5-05 declares.
6. Write `tests/e2e/test_remediate_with_sandbox.py::test_retry2_recovers_end_to_end`:
   - Set `CODEGENIE_HOME` via `monkeypatch.setenv` per Implementation outline above.
   - Read the CVE id from the fixture metadata.
   - Monkeypatch `make_orchestrator` to inject the `ReplanHookSpy`.
   - Invoke `CliRunner().invoke(...)`; assert exit code 0.
   - Resolve `run_dir` via `_paths.resolve_run_dir(e2e_repo, result.output)`.
   - Capture the pre-run head before invocation (if the file pre-exists from Phase 4 — typically `b""` in this fixture).
   - Open the ledger via `RetryLedger.open_existing(run_dir, "stage6_validate")` (use the open-existing classmethod, not the construction-with-`prev_chain_head=None` ambiguous path).
   - Walk the typed `entries()` for ordering; `attempts()` for per-attempt assertions.
   - Walk the parsed `SandboxCostEntry` rows for the cost ↔ attempts bijection.
   - Walk evidence dirs for per-attempt artifact shapes.
   - Run the credential-shape tripwire regex sweep.
7. Write `test_e2e_macos_auto_detect_uses_did` (second test in same module) per AC line above.
8. Write `tests/e2e/test_remediate_with_sandbox_replay_stable.py::test_replay_stability` per AC line above.
9. Update `pyproject.toml § [tool.pytest.ini_options].markers` to register `e2e` and `cassette_stability` markers.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/e2e/test_remediate_with_sandbox.py`

```python
from __future__ import annotations

import re
import yaml
from pathlib import Path

import pytest
import structlog
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.cost import SandboxCostEntry
from codegenie.sandbox.env_allowlist import CREDENTIAL_DENY_SUBSTRINGS
from codegenie.sandbox.registry import EVENT_SANDBOX_AUTO_DETECT_FALLBACK

from tests.e2e._paths import resolve_run_dir, resolve_cost_jsonl
from tests.integration._helpers.hooks import ReplanHookSpy
from tests.integration._helpers.vcr import extract_phase4_interactions

_CASSETTE = Path("tests/integration/gates/cassettes/stage6_retry_recovers.yaml")
_UUID7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_BLAKE3_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_FENCE_BEGIN_RE = re.compile(r"<BEGIN_PRIOR_ATTEMPT_[A-F0-9]{16}>")
_FENCE_END_RE = re.compile(r"<END_PRIOR_ATTEMPT_[A-F0-9]{16}>")


@pytest.mark.e2e
@pytest.mark.timeout(300)
@pytest.mark.vcr(str(_CASSETTE))
def test_retry2_recovers_end_to_end(
    e2e_repo: Path,
    vcr_cassettes,
    block_network,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEGENIE_HOME", str(e2e_repo / ".codegenie"))

    cve_id = yaml.safe_load((e2e_repo / "metadata.yaml").read_text())["cve_id"]

    # Inject the spy via S8-02's make_orchestrator DI port.
    spy_box: dict[str, ReplanHookSpy] = {}
    from codegenie.cli import remediate as remediate_module

    real_make_orchestrator = remediate_module.make_orchestrator

    def make_orchestrator_with_spy(**kw):
        orchestrator = real_make_orchestrator(**kw)
        spy = ReplanHookSpy(orchestrator.replan_hook)
        orchestrator.replan_hook = spy
        spy_box["spy"] = spy
        return orchestrator

    monkeypatch.setattr(
        "codegenie.cli.remediate.make_orchestrator", make_orchestrator_with_spy
    )

    # Invoke.
    pre_run_remediation_dir = e2e_repo / ".codegenie" / "remediation"
    runner = CliRunner()
    result = runner.invoke(
        cli, ["remediate", "--cve", cve_id, "--repo", str(e2e_repo)]
    )

    assert result.exit_code == 0, f"non-zero exit: {result.output}"

    # Resolve run dir deterministically.
    run_dir = resolve_run_dir(e2e_repo, result.output)
    assert len(list(pre_run_remediation_dir.iterdir())) == 1, (
        f"expected exactly one run dir, got {list(pre_run_remediation_dir.iterdir())}"
    )

    # Spy assertions — provenance: hook actually fired with the right kwarg.
    spy = spy_box["spy"]
    assert spy.call_count == 1, f"replan hook fired {spy.call_count} times"
    assert len(spy.calls[0].prior_attempts) == 1
    assert spy.calls[0].prior_attempts[0].attempt_id == 1

    # Cassette introspection — fence on second interaction only, size ≤ 4 KB.
    interactions = extract_phase4_interactions(_CASSETTE)
    assert len(interactions) == 2, "cassette must have exactly two Phase-4 interactions"
    assert not _FENCE_BEGIN_RE.search(interactions[0].prompt_text), (
        "attempt 1 must NOT carry the prior-attempts fence"
    )
    begin = _FENCE_BEGIN_RE.search(interactions[1].prompt_text)
    end = _FENCE_END_RE.search(interactions[1].prompt_text)
    assert begin and end and end.start() > begin.end(), (
        "attempt 2 must carry a well-formed fenced prior-attempts block"
    )
    fence_body = interactions[1].prompt_text[begin.end():end.start()]
    assert len(fence_body.encode("utf-8")) <= 4096, (
        f"fence body must be ≤ 4 KB (ADR-0002), got {len(fence_body.encode('utf-8'))}"
    )

    # Ledger — typed reader. NO json.loads(line)["type"] / ["kind"] anywhere.
    ledger = RetryLedger.open_existing(run_dir=run_dir, gate_id="stage6_validate")
    entries = ledger.entries()  # raises AuditChainCorrupted on chain break
    assert [entry.type for entry in entries] == [
        "pre_execute",
        "attempt",
        "pre_execute",
        "attempt",
    ], f"unexpected row order: {[e.type for e in entries]}"

    attempts = ledger.attempts()
    assert len(attempts) == 2
    assert attempts[0].attempt_id == 1
    assert attempts[1].attempt_id == 2
    assert attempts[0].outcome.state == "failed_retryable"
    assert attempts[1].outcome.state == "passed"

    # Positive shape, then distinctness.
    for i, a in enumerate(attempts):
        assert _UUID7_RE.match(a.sandbox_run_id), (
            f"attempts[{i}].sandbox_run_id not UUID7: {a.sandbox_run_id!r}"
        )
        assert _BLAKE3_HEX_RE.match(a.patch_blake3), (
            f"attempts[{i}].patch_blake3 not 64-hex: {a.patch_blake3!r}"
        )
    assert attempts[0].sandbox_run_id != attempts[1].sandbox_run_id
    assert attempts[0].patch_blake3 != attempts[1].patch_blake3
    assert attempts[0].evidence_paths["patch"] != attempts[1].evidence_paths["patch"]

    # Chain-head advancement.
    head_bin = run_dir / "chain_head.bin"
    assert head_bin.exists(), "chain_head.bin must be written at run dir"
    post_head = head_bin.read_bytes()
    assert len(post_head) == 32, f"chain head must be 32-byte BLAKE3, got {len(post_head)}"
    assert post_head == ledger.head(), "on-disk head must equal re-derived head"
    # If Phase 4 seeded a head, assert advancement; otherwise just non-empty (above).
    seed_path = e2e_repo / ".codegenie" / "phase4" / "chain_head.bin"
    if seed_path.exists():
        assert post_head != seed_path.read_bytes(), (
            "Phase-5 must extend Phase-4's chain head, not preserve it"
        )

    # Cost rows ↔ attempts bijection.
    cost_path = resolve_cost_jsonl(run_dir)
    assert cost_path.exists()
    cost_lines = cost_path.read_text().splitlines()
    assert len(cost_lines) == 2
    parsed = [SandboxCostEntry.model_validate_json(ln) for ln in cost_lines]
    assert {p.attempt_id for p in parsed} == {1, 2}
    assert {p.sandbox_run_id for p in parsed} == {a.sandbox_run_id for a in attempts}
    parsed_by_id = {p.attempt_id: p for p in parsed}
    assert parsed_by_id[1].sandbox_run_id == attempts[0].sandbox_run_id
    assert parsed_by_id[2].sandbox_run_id == attempts[1].sandbox_run_id

    # Evidence bundles per attempt.
    import json as _json
    for a in attempts:
        ev = run_dir / "gates" / "stage6_validate" / "sandbox" / a.sandbox_run_id
        assert (ev / "stdout.log").exists()
        assert (ev / "stdout.log").stat().st_size > 0, "stdout.log must be non-empty"
        assert (ev / "stderr.log").exists()

        sbom = _json.loads((ev / "sbom.json").read_text())
        assert sbom, "sbom.json must be non-empty"

        policy = _json.loads((ev / "policy.json").read_text())
        for key in ("lockfile", "runtime_trace", "test_inventory"):
            assert key in policy, f"policy.json missing top-level key {key!r}"

        trace_present = (ev / "trace.jsonl").exists()
        unavail_present = (ev / "trace.unavailable").exists()
        assert trace_present ^ unavail_present, (
            "exactly one of trace.jsonl OR trace.unavailable must exist (XOR)"
        )
        if unavail_present:
            marker = _json.loads((ev / "trace.unavailable").read_text())
            assert marker.get("reason"), "trace.unavailable must declare a reason"
            assert marker.get("platform") in {"darwin", "linux"}

    # Credential-shape tripwire.
    for p in run_dir.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            for pattern in CREDENTIAL_DENY_SUBSTRINGS:
                m = pattern.search(data)
                assert m is None, (
                    f"credential-shape match {pattern.pattern!r} in {p}: "
                    f"{data[m.start():m.end()]!r}"
                )

    # Defense in depth — chokepoint walker still clean (S5-04 export).
    from tests.schema.test_stage6_chokepoint import assert_stage6_chokepoint_clean
    assert_stage6_chokepoint_clean(Path.cwd())


@pytest.mark.e2e
@pytest.mark.timeout(300)
@pytest.mark.vcr(str(_CASSETTE))
def test_e2e_macos_auto_detect_uses_did(
    e2e_repo: Path,
    vcr_cassettes,
    block_network,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEGENIE_HOME", str(e2e_repo / ".codegenie"))
    monkeypatch.setattr("codegenie.sandbox.registry._kvm_available", lambda: False)
    cve_id = yaml.safe_load((e2e_repo / "metadata.yaml").read_text())["cve_id"]

    with structlog.testing.capture_logs() as captured:
        result = CliRunner().invoke(
            cli, ["remediate", "--cve", cve_id, "--repo", str(e2e_repo)]
        )

    assert result.exit_code == 0, result.output

    fallbacks = [e for e in captured if e.get("event") == EVENT_SANDBOX_AUTO_DETECT_FALLBACK]
    assert len(fallbacks) == 1, f"expected one fallback event, got {fallbacks}"
    assert fallbacks[0]["backend"] == "docker_in_docker"

    # Cost rows back the typed backend Literal.
    run_dir = resolve_run_dir(e2e_repo, result.output)
    cost_path = resolve_cost_jsonl(run_dir)
    parsed = [SandboxCostEntry.model_validate_json(ln) for ln in cost_path.read_text().splitlines()]
    assert all(p.backend == "docker_in_docker" for p in parsed)
```

And the sibling determinism test at `tests/e2e/test_remediate_with_sandbox_replay_stable.py`:

```python
@pytest.mark.cassette_stability
@pytest.mark.timeout(900)
@pytest.mark.vcr(str(_CASSETTE))
def test_replay_stability(
    e2e_repo_factory,  # factory variant of e2e_repo; one tmp_path per call
    vcr_cassettes,
    block_network,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process-level cassette-replay determinism: 3 back-to-back runs in fresh tmp dirs
    must produce byte-identical (exit_code, ledger.head(), attempt-id/sandbox-run-id tuples)."""
    snapshots = []
    for i in range(3):
        repo = e2e_repo_factory()
        monkeypatch.setenv("CODEGENIE_HOME", str(repo / ".codegenie"))
        cve_id = yaml.safe_load((repo / "metadata.yaml").read_text())["cve_id"]
        result = CliRunner().invoke(cli, ["remediate", "--cve", cve_id, "--repo", str(repo)])
        run_dir = resolve_run_dir(repo, result.output)
        ledger = RetryLedger.open_existing(run_dir=run_dir, gate_id="stage6_validate")
        cost_path = resolve_cost_jsonl(run_dir)
        parsed = [SandboxCostEntry.model_validate_json(ln) for ln in cost_path.read_text().splitlines()]
        snapshots.append((
            result.exit_code,
            ledger.head(),
            tuple(sorted((p.attempt_id, p.sandbox_run_id) for p in parsed)),
        ))
    assert snapshots[0] == snapshots[1] == snapshots[2], (
        f"process-level non-determinism: {snapshots}"
    )
```

### Green

If S2-01..S2-03, S3-05, S5-01, S5-02, S5-05, S6-04, S6-05, S7-03, S8-01, S8-02 landed correctly, this story's "green" is mostly wiring fixtures (`e2e_repo`, `vcr_cassettes`, `e2e_repo_factory`), extracting `CREDENTIAL_DENY_SUBSTRINGS` to `src/codegenie/sandbox/env_allowlist.py`, adding the `metadata.yaml#cve_id` field if S5-05 hadn't, and resolving the typed accessors. **If a kernel is missing (e.g., `RetryLedger.open_existing` isn't exposed yet, `extract_phase4_interactions` isn't shipped from S5-05, the `make_orchestrator` DI port isn't there from S8-02, or `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` is undefined), surface the gap in `_attempts/S8-03.md` and fix in the responsible upstream module — do NOT paper over by relaxing the assertion or stubbing the missing primitive locally.**

### Refactor

- Once all three tests share `resolve_run_dir` / `resolve_cost_jsonl`, confirm they live in `tests/e2e/_paths.py` (rule-of-three: this story's two tests + S8-04).
- If `CREDENTIAL_DENY_SUBSTRINGS` already exists in `src/codegenie/sandbox/env_allowlist.py` from S1-05/ADR-0012 work, do not re-define; import the existing constant. Update the schema test in `tests/schema/test_env_allowlist_no_credentials.py` to import from the same place (additive).
- Structured log at test-end: `structlog.get_logger().info("e2e.remediate_with_sandbox.summary", attempts_count=len(attempts), cost_rows_count=len(parsed))` for CI postmortem (observability only; not a behavioral assertion).
- Surface the `e2e_repo_factory` fixture as a defer-until-n=2 abstraction (Phase-7 will be the second consumer); today it can be a thin wrapper around `e2e_repo`. Do not parametrize the *headline* test by fixture name yet — single fixture today.

## Files to touch

| Path | Why |
|---|---|
| `tests/e2e/__init__.py` | Make `tests.e2e` a package. |
| `tests/e2e/conftest.py` | `e2e_repo`, `vcr_cassettes`, `e2e_repo_factory` fixtures. |
| `tests/e2e/_paths.py` | `resolve_run_dir(e2e_repo, result_output)`, `resolve_cost_jsonl(run_dir)` — consumed by both headline tests and S8-04. |
| `tests/e2e/test_remediate_with_sandbox.py` | Headline E2E + macOS-fallback test. |
| `tests/e2e/test_remediate_with_sandbox_replay_stable.py` | Triple-replay determinism. |
| `tests/fixtures/repos/breaking-change-cve/metadata.yaml` | Confirm or add the `cve_id` field (S5-05 fixture contract extension). |
| `src/codegenie/sandbox/env_allowlist.py` | Export `CREDENTIAL_DENY_SUBSTRINGS` as the SSOT if not already (rule-of-three). |
| `tests/schema/test_env_allowlist_no_credentials.py` | Additive: import from `codegenie.sandbox.env_allowlist` rather than redefining. |
| `pyproject.toml` | Register `e2e` and `cassette_stability` markers under `[tool.pytest.ini_options].markers`; `--strict-markers` is already set — do not duplicate. |

## Out of scope

- **`failed_unrecoverable` outcome class** (CVE that escalates past 3 retries → exit code 12). The arch's `tests/e2e/scenarios.yaml` plan anticipates a row per outcome class; this story owns exactly the *success-on-attempt-2* row. The escalation path is exercised by S7-04's integration test (repo-lock + concurrent invocations) and should be filed as a follow-on E2E story whose scope is `tests/fixtures/repos/always-fails/` if appetite remains.
- **Concurrent-invocation behavior** — S7-04's `test_subprocess_child_holds_lock_parent_raises` covers `fcntl.flock` semantics. This E2E exercises the lock acquisition path *implicitly* (any release-on-exit bug would manifest as the next test hanging). No explicit assertion on `.codegenie/remediation/.lock` lifecycle.
- **Performance / wall-clock budgets beyond 300 s**: S7-02 owns perf regression gates; this E2E is *correctness*, not perf.
- **Real Linux-KVM CI matrix run**: Owned by S6-05's KVM smoke + weekly cron. This story covers the `_kvm_available=False` branch via monkeypatch; cross-OS CI matrix is unchanged.
- **ADR audit + final coverage report**: S8-04.
- **Removing the VCR cassette dependency** by hitting a real LLM — never; violates determinism. Cassette refresh follows `docs/operations/cassettes.md`'s explicit-acknowledgement gate.
- **Cassette byte-identity pinning** (`assert blake3(cassette.read_bytes()) == "<pinned>"`) — by design, the cassette can be refreshed without breaking S8-03; the behavioral invariants (two interactions, fence on second, distinct patch) hold across refreshes.
- **Cross-OS testing beyond macOS DinD + Linux Firecracker** — Windows is out of scope for Phase 5.

## Notes for the implementer

- **Why `RetryLedger.open_existing(run_dir, gate_id)` and not `RetryLedger(..., prev_chain_head=None)`**: the latter has overloaded construction semantics (seed-vs-reopen) per S5-05's HARDENED finding #15. Use the explicit open-existing classmethod. If S2-01 / S5-02 hasn't exposed `open_existing` yet, surface as a blocker — do not work around it with a pure helper `attempts_from_jsonl(path)`; the typed reader is the contract surface.
- **Default-3-retry assumption**: The test does NOT pass `--max-attempts-override`. The fixture is expected to recover on attempt 2 within the production-ADR-0014 default of 3. If the fixture's failure pattern shifts and requires retry 3, that's a fixture problem to escalate via `_attempts/`, NOT a `--max-attempts-override 5 --operator-ack` workaround in the test. Documenting this explicitly so future readers understand why neither flag appears.
- **`trace.unavailable` marker owner**: This story asserts the marker shape but does not ship the writer. The trace collector that emits the marker on macOS is owned by S4-03 (trace + policy + CVE collectors). If S4-03's HARDENED contract does not yet define the marker schema (`{"reason": str, "platform": "darwin" | "linux"}`), file a spawned task to harden it; do not invent the schema here. The E2E asserts what the upstream story should ship.
- **`RunId` raw-string at E2E boundary**: The test reads `sandbox_run_id` as `str` off disk via Pydantic JSON parsing. `RunId = NewType("RunId", str)` is a `str` at runtime, so positional comparisons work. This is a deliberate boundary — production code (`src/codegenie/`) uses the newtype; E2E reading JSONL gets the underlying string. No conversion is needed; do not introduce one.
- **Subprocess fallback**: If `CliRunner.invoke` proves insufficient (e.g., the orchestrator forks for sandbox launch and the in-process click runner can't isolate file descriptors), fall back to `subprocess.run([sys.executable, "-m", "codegenie", "remediate", "--cve", cve_id, "--repo", str(e2e_repo)], env=..., check=False)`. This does **not** go through `codegenie.exec.run_allowlisted` — the allowlist polices SUT-internal external-tool invocations (`npm ci`, `git status`, etc.), not test-side launches of the SUT itself. If the fallback is taken, the `make_orchestrator` monkeypatch can't reach into the child process; the spy assertions then degrade to cassette-introspection-only (`extract_phase4_interactions(_CASSETTE)[1].prior_attempts_serialized != ""` proves the contract held even without the spy). Document the choice in `_attempts/S8-03.md`.
- **Forward-compatibility for Phase-7 distroless E2E**: The `e2e_repo` fixture body uses a single module-level constant `_FIXTURE_REPO_NAME = "breaking-change-cve"`. Phase-7's `tests/e2e/test_distroless_migration_with_sandbox.py` will be the second consumer; at n=2, parametrize via `pytest.fixture(params=[...])` or factory the fixture (`e2e_repo_factory(fixture_name: str)`). **Do not solve today** — Rule 2 (Simplicity First).
- **Backend parametrization deferred to n=3**: Two test functions for DinD-forced vs default (Firecracker on Linux-KVM, DinD on macOS) is acceptable per Rule 2. When Phase-7's chainguard backend lands (per S8-01 HARDENED §"Open/Closed contract for backends"), parametrize via `@pytest.mark.parametrize("backend", BackendKind, ids=...)` driven by the registry — do not abstract today.
- **`CREDENTIAL_DENY_SUBSTRINGS` — primary defense lives elsewhere**: Per ADR-0012, the *primary* credential-leak defense is `tests/schema/test_env_allowlist_no_credentials.py` (filter logic) + `tests/adversarial/test_postinstall_exfil.py` (real exfil attempts). This E2E adds a *tripwire* — if the regex catalog is too permissive (false positives) or too restrictive (false negatives), the fix is at `src/codegenie/sandbox/env_allowlist.py`, where all three callers share the constant. Do not edit only this test file.
- **Optional chokepoint check at E2E end**: The test calls `assert_stage6_chokepoint_clean(Path.cwd())` (S5-04 export) as defense-in-depth — a contributor accidentally adding a subprocess call to a fixture helper during this story's implementation would be caught. If S5-04 has not exported the callable yet, the import will fail; surface as a blocker on S5-04 rather than skipping the assertion.
- **Status semantics**: `Ready (HARDENED 2026-05-26)` — the story has been through the validator and is approved for the executor. The executor's Validator pass should still re-verify every AC against runtime evidence; this validator pass guarantees the ACs are *verifiable*, not that they have been *verified*.
