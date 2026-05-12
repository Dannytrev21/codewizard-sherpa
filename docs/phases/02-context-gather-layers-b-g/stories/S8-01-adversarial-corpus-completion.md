# Story S8-01 — Adversarial corpus completion to ≥ 40 net-new Phase 2 fixtures

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** L
**Depends on:** S3-05, S4-02, S4-03, S5-02, S5-03, S5-04, S6-03, S6-04, S7-02, S7-03, S7-06, S7-07, S7-08, S7-09, S7-10
**ADRs honored:** ADR-0001 (`consumes_peer_outputs` contract is not weakened), ADR-0003 (sandbox extension absorbs every hostile-fixture attempt), ADR-0004 (digest pin manifest covers every tool the corpus invokes), ADR-0005 (`ALLOWED_BINARIES` is the only exec surface), ADR-0006 (Pass 4 + Pass 5 are pinned end-to-end), ADR-0007 (`--ignore-scripts` wrapper-enforced), ADR-0008 (closed-enum conventions catalog is not bypassed), ADR-0011 (B2 advisory budget never fails the gather), ADR-0012 (audit-chain break observability), ADR-0013 (`node_modules` never written by gather)

## Context

Steps 3–7 each landed the adversarial fixture(s) closest to the probe they exercise. This story closes the remaining surface so the corpus reaches **≥ 40 net-new Phase 2 fixtures** (≥ 60 total when Phase 0/1's inherited corpus is counted) and trips on **every** Phase 2 invariant that is not already covered by a unit test. The architecture enumerates 17 specific adversarial cases in `phase-arch-design.md §"Testing strategy" → "Adversarial tests"`; this story lands the residual ≥ 23 (the difference between what Steps 3–7 covered and 40) plus the unambiguously-named tests the manifest pins (`test_skill_yaml_injection.py`, `test_audit_chain_break_observability.py`, `test_legacy_npm_no_ignore_scripts_fallback.py`, `test_no_credentials_in_subprocess_env.py`, `test_truncated_scip_index.py`, `test_scip_compiler_plugin_attempt.py`, `test_treesitter_grammar_version_mismatch.py`, `test_semgrep_redos.py`, `test_malformed_semgrep_output.py`).

The corpus is **CI-gating**: any new fixture that fails on `main` blocks the merge. The combined p95 wall-clock cap is **< 90 s**; tests that need long-running subprocess work go behind `[slow-adv]` markers and run on nightly only. This is the last story in Phase 2 that adds raw test surface — S8-02 onward only consume the corpus. Treat anything not pinned here as silently exposed.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Adversarial tests"` — the 17 enumerated cases.
  - `../phase-arch-design.md §"Goals"` — Adversarial robustness ≥ 60 hostile fixtures, CI-gating; hard caps fail-loud.
  - `../phase-arch-design.md §"Failure modes & recovery"` — informs the negative-case shape (probe falls back to `confidence: low` rather than crashing the gather).
- **Phase ADRs (each one trips at least one fixture in this corpus):**
  - `../ADRs/0001-peer-outputs-binding.md` — frozen `MappingProxyType` snapshot; mutation attempts fail loud.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — scoped-egress allowlist; out-of-band hosts blocked.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — digest mismatch surfaces at gather time.
  - `../ADRs/0005-allowed-binaries-additions.md` — non-allowlisted binary refuses to exec.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — Pass 4 redacts secrets; Pass 5 tags prompt-injection markers without inlining bodies.
  - `../ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md` — `--ignore-scripts` wrapper-enforced even for legacy npm.
  - `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — `_apply_detector` `match/case` ↔ `detect.type.enum` parity.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — budget overrun is observability, never failure.
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — chain break logs `audit.chain_break.detected`, never aborts the gather.
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` — gather never invokes `npm install`.
- **Source design:**
  - `../final-design.md §"Adversarial tests"` (rows referencing the seventeen named hostile fixtures).
  - `../final-design.md §"Synthesis ledger row 2"` — three-domain seeded-staleness signal (this story extends the hostile surface, S8-03 lands the seeded fixtures).
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — list of named-and-required tests; combined p95 wall-clock < 90 s constraint.
  - `../High-level-impl.md §"Implementation-level risks"` items #3 (ABC slip), #4 (`--ignore-scripts` slip), #5 (gitleaks three-layer), #9 (`docker build` macOS fallback) — all surface in this corpus.
- **Existing code:**
  - Every Phase 2 probe under `src/codegenie/probes/`.
  - Every wrapper under `src/codegenie/tools/`.
  - `src/codegenie/exec.py` (`run_in_sandbox` is the chokepoint each fixture exercises).
  - `src/codegenie/output_sanitizer.py` Pass 4 + Pass 5.
  - `src/codegenie/audit_writer.py` (rolling chain head).
  - `tests/adv/` Phase 0/1 fixtures (for inherited surface count).
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S5-01-adversarial-parser-caps.md` (Phase 1 adversarial-fixture story pattern).

## Goal

Land ≥ 23 additional adversarial fixtures + their tests under `tests/fixtures/` and `tests/adv/` (Phase 2 net-new total ≥ 40) so every Phase 2 invariant trips a CI-gated red-fail when violated, and the combined p95 wall-clock stays under 90 s.

## Acceptance criteria

- [ ] Phase 2 ships at least **40 net-new adversarial fixtures** counted by enumerating `tests/adv/test_*.py` files added in Steps 3–8 (script `scripts/count_phase2_adversarial.py` introduced here; CI job `adversarial_count` asserts the floor of 40).
- [ ] The combined Phase 2 adversarial suite (`pytest tests/adv -m "not slow_adv"`) completes in **< 90 s p95** on the CI runner; the bench is recorded in the PR body.
- [ ] Each of the following named tests exists under `tests/adv/` and is green on `main`:
  - [ ] `test_tsconfig_extends_cycle_deep.py` — a `tsconfig.json` `extends:` chain depth > 16 → parser refuses with `ToolOutputMalformed` (or the Phase 1 cycle-detect error); no infinite loop.
  - [ ] `test_hostile_convention_catalog_yaml.py` — a malicious `node.yaml` with a YAML anchor bomb → `CatalogLoadError`; gather refuses to start, exits 2.
  - [ ] `test_malformed_cve_json.py` — a hand-crafted `grype` output with a missing `matches[].vulnerability.id` → `GrypeCVEProbe` falls back to `confidence: low` with structured warning; envelope still validates.
  - [ ] `test_oversized_sbom.py` — a `syft` output > 100 MB → size cap rejects; probe `confidence: low`; no OOM.
  - [ ] `test_blake3_cache_key_collision_attempt.py` — two artifacts with hand-crafted near-collision content → per-file cache module (S7-01) detects mismatch on read, deletes blob, probe re-runs (no silent stale answer).
  - [ ] `test_skill_yaml_injection.py` — a SKILL.md frontmatter with a YAML alias-explosion (`&a [*a, *a, ...]`) → `SkillLoadError`; CLI exits 2.
  - [ ] `test_audit_chain_break_observability.py` — manually rewrite a prior run's `chain_head` in `.codegenie/runs/`; next gather emits `audit.chain_break.detected`, **gather still completes** (exit 0); event count = 1.
  - [ ] `test_legacy_npm_no_ignore_scripts_fallback.py` — npm version on `$PATH` predates `--ignore-scripts` support; wrapper falls back to **static-only** parse with structured warning `npm.no_ignore_scripts_support`; `resolution_status: "static_only"`.
  - [ ] `test_no_credentials_in_subprocess_env.py` — set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, `MY_SUPER_SECRET_TOKEN` in the parent env; run gather; assert subprocess invocations (via `pytest-subprocess` or audit-log inspection) include none of these env vars.
  - [ ] `test_truncated_scip_index.py` — a `.scip` file truncated mid-protobuf → `ToolOutputMalformed`; `SCIPIndexProbe` falls back to `confidence: low`; gather completes.
  - [ ] `test_scip_compiler_plugin_attempt.py` — a hostile `tsconfig.json` declaring a custom TypeScript compiler plugin from `node_modules` → `SCIPIndexProbe` either (a) ignores the plugin if `node_modules` is absent (ADR-0013 path) or (b) records the plugin without executing it; assert no subprocess executes the plugin's code; assert `tools.scip_typescript.run` invoked with `--no-plugins` or equivalent.
  - [ ] `test_treesitter_grammar_version_mismatch.py` — pin `tools/digests.yaml` to grammar version `vX`; install a wheel reporting version `vY`; install-time `check_tool_digests.py` fails CI loud; complementary in-process test: load the mismatched grammar in `tools.treesitter` → `ToolInvariantViolation`.
  - [ ] `test_semgrep_redos.py` — feed `SemgrepProbe` a file with a payload constructed to ReDoS a known catastrophic pattern; wrapper-level timeout fires; probe `confidence: low`; no other probe stalls.
  - [ ] `test_malformed_semgrep_output.py` — replace `semgrep` on `$PATH` with a stub returning invalid JSON; `tools.semgrep.run` raises `ToolOutputMalformed`; `SemgrepProbe` records `confidence: low`; envelope still validates.
- [ ] `scripts/count_phase2_adversarial.py` is a < 60-LOC pure-stdlib Python script that walks `tests/adv/` and prints the count; CI job `adversarial_count` runs it and fails if count < 40.
- [ ] Every new fixture under `tests/fixtures/` is < 1 MB on disk (oversize-SBOM fixture excepted; it is constructed at test time via a fixture factory, not committed as a 100 MB blob).
- [ ] Each adversarial test docstring opens with `"""ADR-NNNN | Invariant: <one-sentence>"""` so the gating ADR is grep-able from `pytest --collect-only -q`.
- [ ] No new top-level dep introduced by this story (`pyproject.toml` unchanged); use stdlib + Phase 1/2 deps only.

## Implementation outline

1. **Inventory pass.** Run `find tests/adv -name 'test_*.py' -newer <main-merge-base>` to enumerate what Steps 3–7 already landed. Build a worksheet of (architecture-named test, exists yes/no). The 17 enumerated cases in `phase-arch-design.md` are the floor; the residual ≥ 23 above is the ceiling.
2. **For each net-new test:**
   - Add a minimal fixture under `tests/fixtures/<scenario>/` (single-file where possible; multi-file only when the scenario demands it — e.g. `tsconfig_extends_cycle_deep/` needs 17 chained tsconfig files).
   - Add the test under `tests/adv/test_<scenario>.py` with the ADR-cite docstring.
   - Assert the **fall-back** behavior, not just the raise (a gather that aborts on a hostile fixture is a Phase 2 failure mode — the contract is *probe falls back to `confidence: low` + structured warning*).
3. **`test_audit_chain_break_observability.py`** is the highest-leverage new test for ADR-0012. Stage:
   - Run gather once to produce a baseline `runs/<utc>-<short>.json`.
   - Programmatically rewrite the file's `chain_head` to a deliberately-wrong BLAKE3.
   - Run gather a second time; capture structlog; assert `audit.chain_break.detected` fires exactly once; assert exit code is 0; assert the second run's `previous_hash` does not pretend the chain was intact (the broken hash is recorded for forensics).
4. **`test_no_credentials_in_subprocess_env.py`** uses `pytest-monkeypatch` to set the credentials in `os.environ`, runs a probe that invokes a subprocess (any of the seven tool wrappers — pick `semgrep` for speed), and inspects the subprocess env via either (a) the audit record (every `probe.tool.invoked` event records the sanitized env keys) or (b) a `subprocess.run` patch that captures the `env=` kwarg. The assertion is the negative: each credential key is **not in** the subprocess env.
5. **`test_blake3_cache_key_collision_attempt.py`** does not need to actually achieve a BLAKE3 collision (computationally infeasible); it stages two writes to the per-file cache with the same `(file_blake3, rule_pack_version, grammar_version)` key but different blob bytes, simulating a partial-write corruption; the second read detects the integrity-check mismatch and triggers re-run. This is the **defense** test, not the attack test.
6. **`scripts/count_phase2_adversarial.py`**: 1 function, walks `tests/adv/`, filters by `test_*.py`, prints the count + a header line `Phase 2 adversarial fixtures: N`. The CI job `adversarial_count` greps for `^Phase 2 adversarial fixtures: ` and asserts the int ≥ 40.
7. **Wall-clock budget.** After all tests are green, run `pytest tests/adv --durations=20`. Any test > 5 s gets either (a) the `slow_adv` marker (excluded from default CI; included nightly) or (b) a perf fix. Common slow culprits: real subprocess invocations of `semgrep`/`syft` on large fixtures — substitute a stub wrapper at the `tools.<x>.run` seam, not at the subprocess seam.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with `test_audit_chain_break_observability.py` because it is the cleanest ADR-trip in the corpus and exercises the most cross-cutting machinery (audit writer + structlog + gather lifecycle).

Path: `tests/adv/test_audit_chain_break_observability.py`

```python
"""ADR-0012 | Invariant: a tampered chain_head logs once and never aborts the gather."""
from pathlib import Path

import pytest


def test_audit_chain_break_logs_but_continues(tmp_path, run_gather, structlog_capture):
    fixture = Path("tests/fixtures/node_typescript_helm").resolve()

    # First gather: establishes a baseline run record with a valid chain_head.
    first = run_gather(fixture, cache_dir=tmp_path / "cache", runs_dir=tmp_path / "runs")
    assert first.exit_code == 0
    runs = sorted((tmp_path / "runs").glob("*.json"))
    assert runs, "first gather did not write a run record"

    # Tamper with the chain_head; the next gather must observe and continue.
    import json
    record = json.loads(runs[-1].read_text())
    record["chain_head"] = "0" * 64
    runs[-1].write_text(json.dumps(record))

    structlog_capture.clear()
    second = run_gather(fixture, cache_dir=tmp_path / "cache", runs_dir=tmp_path / "runs")
    assert second.exit_code == 0, "ADR-0012: chain break must not fail the gather"
    breaks = [e for e in structlog_capture.events if e.get("event") == "audit.chain_break.detected"]
    assert len(breaks) == 1, f"expected exactly one chain-break event, got {len(breaks)}"
```

Two more representative red tests:

Path: `tests/adv/test_no_credentials_in_subprocess_env.py`

```python
"""ADR-0003 | Invariant: credentials in parent env never leak into subprocess env."""
from pathlib import Path

CREDS = {
    "OPENAI_API_KEY": "sk-fake-openai",
    "ANTHROPIC_API_KEY": "sk-ant-fake",
    "CHAINGUARD_TOKEN": "cg_fake",
    "MY_INTERNAL_SECRET_TOKEN": "leak-me-not",
}


def test_credentials_stripped_from_subprocess_env(monkeypatch, run_gather, tmp_path, audit_records):
    for k, v in CREDS.items():
        monkeypatch.setenv(k, v)
    result = run_gather(Path("tests/fixtures/node_typescript_helm").resolve(),
                        cache_dir=tmp_path / "cache")
    assert result.exit_code == 0

    # audit_records is a fixture that loads every probe.tool.invoked event with its sanitized env keys.
    for invocation in audit_records.tool_invocations:
        for forbidden in CREDS:
            assert forbidden not in invocation.env_keys, (
                f"{forbidden} leaked into {invocation.tool_name} subprocess env"
            )
```

Path: `tests/adv/test_legacy_npm_no_ignore_scripts_fallback.py`

```python
"""ADR-0007 | Invariant: legacy npm without --ignore-scripts falls back to static-only with a warning."""
from pathlib import Path


def test_legacy_npm_falls_back_to_static_only(tmp_path, run_gather_with_npm_stub):
    fixture = Path("tests/fixtures/node_typescript_helm").resolve()
    result = run_gather_with_npm_stub(
        fixture,
        cache_dir=tmp_path / "cache",
        npm_version="2.15.12",  # predates --ignore-scripts
    )
    assert result.exit_code == 0
    bg = result.context["probes"]["build_graph"]
    assert bg["resolution_status"] == "static_only"
    assert any(w["id"] == "npm.no_ignore_scripts_support" for w in bg.get("warnings", []))
```

### Green — make each one pass

For most tests, the probe already implements the correct fall-back; the test simply asserts it. For the chain-break test, S1-10's `verify_previous_chain_head()` should already emit the event — confirm at land time. If a test red-fails because the probe **doesn't** fall back gracefully (it raises and aborts the gather), the fix is in the probe, not in the test; surface as a Step 3/4/5/6/7 follow-up in the PR body and patch.

Common shape for green: a probe that today raises `ToolNonZeroExit` on a corrupt input should catch, log a structured warning, and emit `confidence: "low"` with the slice populated to the extent possible. The fall-back path is the contract, not an optimization.

### Refactor — clean up

After green:

- **Wall-clock pass.** `pytest tests/adv --durations=20 -m "not slow_adv"` — any test > 5 s gets the `slow_adv` marker or a perf fix.
- **De-duplicate fixtures.** If two tests need the same `node_typescript_helm` baseline, they share it; do not commit two near-identical copies.
- **Confirm ADR-cite docstrings** for every new test file.
- **Run `scripts/count_phase2_adversarial.py`** locally; assert the count is ≥ 40 before opening the PR.
- **Verify no test invokes the real internet.** Run with `unshare -rn pytest tests/adv` on Linux (or document the test list in the PR body) to confirm the corpus does not depend on real network access.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_tsconfig_extends_cycle_deep.py` | Cycle-detect at depth > 16; parser-cap pin. |
| `tests/adv/test_hostile_convention_catalog_yaml.py` | YAML anchor-bomb in `node.yaml` → `CatalogLoadError`. |
| `tests/adv/test_malformed_cve_json.py` | `grype` output missing required fields → `GrypeCVEProbe` falls back. |
| `tests/adv/test_oversized_sbom.py` | 100 MB SBOM → size cap; `SyftSBOMProbe` `confidence: low`. |
| `tests/adv/test_blake3_cache_key_collision_attempt.py` | Per-file cache integrity-check re-runs probe on mismatch. |
| `tests/adv/test_skill_yaml_injection.py` | YAML alias explosion in SKILL.md frontmatter → `SkillLoadError`. |
| `tests/adv/test_audit_chain_break_observability.py` | ADR-0012: chain break logs once, never aborts. |
| `tests/adv/test_legacy_npm_no_ignore_scripts_fallback.py` | Legacy npm → static-only with warning. |
| `tests/adv/test_no_credentials_in_subprocess_env.py` | ADR-0003 credential strip end-to-end. |
| `tests/adv/test_truncated_scip_index.py` | Truncated `.scip` → `ToolOutputMalformed`; `SCIPIndexProbe` falls back. |
| `tests/adv/test_scip_compiler_plugin_attempt.py` | Hostile tsconfig plugin chain refused at wrapper. |
| `tests/adv/test_treesitter_grammar_version_mismatch.py` | Grammar version mismatch detected install-time + in-process. |
| `tests/adv/test_semgrep_redos.py` | Wrapper-level timeout on ReDoS pattern. |
| `tests/adv/test_malformed_semgrep_output.py` | `tools.semgrep.run` raises `ToolOutputMalformed`; probe falls back. |
| `tests/fixtures/tsconfig_extends_cycle_deep/` | 17 chained `tsconfig.json` files. |
| `tests/fixtures/hostile_convention_yaml/node.yaml` | Anchor-bomb YAML. |
| `tests/fixtures/scip_compiler_plugin/tsconfig.json` | Hostile compiler-plugin chain. |
| `tests/fixtures/legacy_npm_fixture/` | Fixture with lockfile + a stub npm pinned to a pre-`--ignore-scripts` version. |
| `scripts/count_phase2_adversarial.py` | CI helper to enforce the ≥ 40 floor. |
| `tests/adv/conftest.py` (extend) | New fixtures: `audit_records`, `run_gather_with_npm_stub`, `structlog_capture` if not already present. |

## Out of scope

- **Seeded-staleness fixtures (`stale_scip_repo/`, `stale_sbom_repo/`, `stale_semgrep_rulepack_repo/`)** — handled by **S8-03**. Those are integration fixtures, not adversarial ones, and they pin a separate roadmap exit criterion.
- **Real-OSS fixture (`nestjs_nest_pinned/`)** — handled by **S8-02**.
- **Per-probe goldens** — handled by **S8-04**.
- **Bench canaries (warm-path, B2 budget, SCIP re-index, cold e2e)** — handled by **S8-05**.
- **CI workflow wiring of the `adversarial_count` job** — the script lands here; the job lands in **S8-06**.
- **New probe code.** If a probe needs a fall-back path that does not exist yet, surface as a follow-up; this story does not extend probe behavior beyond what Steps 3–7 already shipped.

## Notes for the implementer

- **The corpus is the single highest-leverage Phase 2 CI gate.** Every other test (golden, bench, integration) trusts that the adversarial corpus already trips on hostile input. If you ship a test that silently passes for the wrong reason (e.g., the gather aborts and pytest catches the exception as success), the gate is fictional. Verify each test's red by mutating the implementation locally and watching it fail.
- **"Fall back, do not abort" is the universal Phase 2 fall-back contract.** A probe that raises on hostile input is a regression. The hostile-fixture corpus is the contract enforcement; if a test red-fails because the probe aborted, the fix is in the probe.
- **`slow_adv` is a knife, not a refuge.** Mark a test slow only if it cannot be made fast without losing coverage (real `semgrep` invocation on a large fixture is the main legitimate case). The nightly job runs them; do not let `slow_adv` become a dumping ground.
- **The `audit.chain_break.detected` event must fire exactly once per tampered gather.** If `verify_previous_chain_head()` is called multiple times in the lifecycle, the test will count multiple events and fail confusingly. Pin the call site to "exactly once on gather startup, before the first probe dispatches."
- **`test_no_credentials_in_subprocess_env.py` is the only test in this corpus that asserts a negative across the *entire* probe set.** If a future probe adds a new tool wrapper and forgets to route through `run_in_sandbox`'s credential-stripping path, this test catches it. Make the assertion broad: any `probe.tool.invoked` event whose `env_keys` includes one of the forbidden keys fails. Do not narrow to one probe.
- **Do not commit a 100 MB SBOM blob.** The `test_oversized_sbom.py` fixture is constructed at test time via a fixture factory (e.g., write 100 MB of `'{"package": "x"}\n'` repetitions into `tmp_path` and feed that to `tools.syft.run` via a stub). Git LFS is explicitly not in scope for Phase 2.
- **The ADR-cite docstring is grep-able.** `pytest --collect-only -q | grep ADR-` should yield one line per adversarial test. The S8-06 contributor docs reference this pattern. Do not omit.
