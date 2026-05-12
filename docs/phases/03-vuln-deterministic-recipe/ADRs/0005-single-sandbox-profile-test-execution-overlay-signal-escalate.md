# ADR-0005: One sandbox profile + `test_execution=True` overlay flag; `--network=none` default with `gate.signal_escalate` for network-needing tests

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** sandbox · chokepoint-preservation · validation-gate · synthesizer-departure · phase-5-handoff
**Related:** [Phase 2 ADR-0003](../../02-context-gather-layers-b-g/ADRs/0003-subprocess-sandbox-profile-extension.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md), ADR-0006

## Context

Stage 6 of the orchestrator runs `npm ci` + `npm test` + (opt-in) `npm run build` to verify the diff passes the repo's own tests — the Phase 3 exit criterion (`docs/roadmap.md §"Phase 3"`). Each design proposed a different sandbox shape:

- **Performance-first** ran the install in a scoped-network sandbox and used a depgraph-driven fast-path subset of tests, with full-suite fallback. The critic dismantled the fast-path: dynamic `require`, plugin loaders, jest `setupFiles`, mocha hooks are out of scope for static reachability — a single missed pattern ships a regression with no fallback green-or-not signal (`critique.md §"Attacks on performance-first" #4`).
- **Security-first** introduced **two** sandbox profiles (Boundary 1 for per-tool subprocesses; `TestSandboxProfile` for `npm test`) with `--network=none` **HARD** and no escape valve. The critic attacked this in two blows (`§"Attacks on security-first" #1, #4`): two profiles double the audit surface against `production/design.md §4`'s Phase-5 microVM commitment; HARD `--network=none` breaks any test suite that uses postgres/redis/external DNS — the majority of nontrivial Node services — and routes to a human reviewer that does not exist in Phase 3.
- **Best-practices** ran `npm test` directly on the worktree with no sandbox at all — the loosest stance, accepts that test execution is attacker-code execution.

All three quietly agreed that running the repo's tests means executing attacker code; `production ADR-0012` commits the microVM as Phase 5's deliverable, not Phase 3's (`critique.md §"Cross-design observations" §"Where do all three quietly agree on something questionable?" #1`). The synthesis preserves Phase 2's `run_in_sandbox` chokepoint ([Phase 2 ADR-0003](../../02-context-gather-layers-b-g/ADRs/0003-subprocess-sandbox-profile-extension.md)) and ships the simplest extension that survives both posture and usability constraints — per critic recommendation verbatim (`final-design.md §"Departures from all three inputs"` #3).

## Options considered

- **Two sandbox profiles, HARD `--network=none` on tests [S].** Strongest posture. Breaks legitimate repos. Routes to a nonexistent human. Doubles the test matrix against Phase 5's microVM unification commitment.
- **One sandbox, scoped network, fast-path test subset [P].** Cheapest. Fast-path is unsafe at the exit criterion (dynamic loads missed). Forces every probe author to tag plugin patterns across an unbounded surface.
- **No sandbox; run `npm test` directly on worktree [B].** Loosest. Accepts attacker-code execution with no isolation; test failure has no "needs network" classification.
- **One sandbox profile + `test_execution=True` overlay flag; `--network=none` default; signal-escalate on network-required failure signatures [synth].** Single chokepoint. Single test matrix. Network-none default preserves posture. Escalation signal preserves operator control.

## Decision

**Phase 3 extends Phase 2's `run_in_sandbox` chokepoint with one new boolean parameter:**

```python
def run_in_sandbox(
    argv, *,
    allowlist, env, timeout_s, cwd,
    network: Literal["none", "scoped"] = "none",
    test_execution: bool = False,     # NEW
    ...
) -> ProcessResult
```

- **One profile.** Same `bwrap`/`sandbox-exec` posture as Phase 2 ADR-0003. No new `SandboxStrategy` interface. No second `TestSandboxProfile`.
- **`test_execution=True` overlay behavior:**
  - Writable upper layer over `/work` for the test runner's tmp output.
  - Larger PID and wall-clock budgets (4 GB RSS cap vs. 900 MB; 600 s wall vs. 180 s).
  - `--ignore-scripts` is **OFF** (the test command runs scripts by definition).
  - `--network=none` is the **default**, not a hard wall.
- **`install_validator` runs with `network="scoped"`, `allowlist=["registry.npmjs.org"]`, `--ignore-scripts` ON.**
- **`test_validator` runs with `network="none"`, `test_execution=True`, `--ignore-scripts` OFF (the test command itself).**
- **Network-required test signatures:** on non-zero test exit, the validator scans stderr for known patterns (`ENOTFOUND`, `ECONNREFUSED`, `getaddrinfo`, `getaddrinfo EAI_AGAIN`, `connect ECONNREFUSED`, common ORM connect error strings). On match:
  - Emit `ValidatorOutput(passed=False, confidence="medium", requires_network=True)`.
  - Emit audit event `gate.signal_escalate` (`final-design.md §"Trust & safety goals"` #15).
  - Exit code 8.
  - Operator re-runs with `--allow-test-network` after review.
- **`--allow-test-network` flag:** explicit operator opt-in. Re-runs `test_validator` with `network="scoped"` and a per-repo allowlist (initial: empty; documented as a per-run decision).
- **Phase 5 promotes the chokepoint to a microVM** without changing the call signature (per Phase 2 ADR-0003 precedent). The `test_execution` overlay translates to microVM resource caps; the network-none default and signal-escalate semantics survive.

## Tradeoffs

| Gain | Cost |
|---|---|
| One sandbox profile — one threat-model surface, one test matrix, one set of adversarial fixtures (target ≥ 30, down from S's 40) | Single profile must satisfy both install and test workloads; budgets are larger for the overlay than they would be in a tighter test-only profile |
| `--network=none` default preserves the security posture S wanted without the breakage; legitimate test suites that need DB/DNS get an honest "we couldn't verify" signal | First-run on any repo whose tests need network requires operator review and an explicit `--allow-test-network` flag — operational friction |
| `gate.signal_escalate` is an explicit operator choice, not a silent allowance; the audit chain (ADR-0010) records the escalation; Phase 5 routes it to LangGraph `interrupt()` | The signature-scan heuristic is incomplete; novel network-required error strings will fail closed (escalate when they shouldn't) — implementer maintains the pattern set as a list-of-known-strings |
| Phase 5's microVM lands at the same chokepoint — `test_execution` overlay translates to microVM resource caps; no probe code moves | Phase 3 ships without microVM-grade test-execution isolation; accepted, mitigated by `--network=none` default |
| `--ignore-scripts` is mandatory everywhere except inside the test command itself (ADR-0006); wrapper-level guard raises `NpmScriptsEnabled` on misuse | The "scripts run only in test execution" rule is a discipline the wrapper enforces; CI test asserts the negative |
| Phase 5's gate machinery wraps this with three-retry-on-network-escalate logic additively — Phase 3's escalation signal is the input | If Phase 5 doesn't land, the local POC's "signal_escalate has no human" gap remains (`phase-arch-design.md §"Gap 3"`); mitigated by stderr banner + `escalations/<utc>.json` + remediation-report.yaml `escalations:` section |
| Phase 2 ADR-0003's chokepoint discipline preserved — same call site, same probe-contract |  `test_execution=True` is a Phase-3 commitment to Phase 2's profile; if Phase 2's `bwrap` profile cannot host `npm test` in a writable overlay, Phase 3 needs a Phase 2 amendment before shipping (`final-design.md §"Roadmap coherence check" §"Prior phases"`) |

## Consequences

- `src/codegenie/exec.py` gains `test_execution: bool` parameter; one new branch in the bwrap/sandbox-exec profile assembly.
- `src/codegenie/transforms/validation/test.py` calls `run_in_sandbox(..., test_execution=True, network="none")` by default.
- `src/codegenie/transforms/validation/install.py` calls `run_in_sandbox(..., test_execution=False, network="scoped", allowlist=["registry.npmjs.org"])`.
- Network-required signature patterns live in `src/codegenie/transforms/validation/network_signatures.py` as a tunable list; initial set per `final-design.md §"Open questions"` #3.
- CLI flag `--allow-test-network` added.
- Exit code 8 (`signal_escalate`) documented.
- `tests/adv/` ships the carry-over from Phase 2 ADR-0003's negative tests plus new fixtures: `test_remediate_test_needs_network_escalates.py`, `test_test_execution_overlay_writable_only_under_work.py`.
- Adversarial corpus target reduced to ≥ 30 (from S's ≥ 40); the missing ten are about `TestSandboxProfile`-only behaviors that don't exist in the single-profile design (`final-design.md §"Test plan" §"Adversarial tests"`).
- Phase 5's gate machinery routes `gate.signal_escalate` to LangGraph `interrupt()`; same audit event is source-of-truth.
- Phase 11's CODEOWNERS notifier reads the same audit event for Slack/PR-comment routing.

## Reversibility

**Medium.** Splitting `test_execution=True` into a second `TestSandboxProfile` later (if Phase 5's microVM benefits from separate profiles) is mechanically additive — split the call sites — but every call site would need updating. Tightening `--network=none` to HARD (no `--allow-test-network`) is **high cost in operational terms** (every repo with networked tests becomes unremediable in Phase 3); doing it post-hoc would surface as broken integration tests across the fixture portfolio. The single-profile + overlay shape is the load-bearing piece; the signature-scan pattern set is configuration and easily evolved.

## Evidence / sources

- `../final-design.md §"Goals" §"Trust & safety goals"` #11, #15
- `../final-design.md §"Components" #7 "Validation gate (single sandbox + overlay)"`
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` rows "Validation test gate" and "Sandbox boundary count"
- `../final-design.md §"Departures from all three inputs"` #3
- `../phase-arch-design.md §"Component design" #11 "ValidationGate"`
- `../phase-arch-design.md §"Gap analysis" §"Gap 3 — `gate.signal_escalate` has no human in the local POC"`
- `../critique.md §"Attacks on security-first" #1` — two-profile critique
- `../critique.md §"Attacks on security-first" #4` — HARD `--network=none` breaks real repos
- `../critique.md §"Attacks on performance-first" #4` — fast-path test selection
- `../critique.md §"Cross-design observations" §"Where do all three quietly agree on something questionable?" #1, #2`
- [Phase 2 ADR-0003](../../02-context-gather-layers-b-g/ADRs/0003-subprocess-sandbox-profile-extension.md) — chokepoint precedent
- [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — Phase 5 microVM commitment
