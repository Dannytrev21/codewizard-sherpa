# Validation report: S3-07 — DinD integration suite against `hello-node`

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-07 is the first end-to-end exercise of the DinD backend against a real
Docker daemon — four `pytest.mark.integration` tests (happy / OOM / timeout /
egress-blocked) that close Phase-5 Goal 5 (`gate_isolation_class:
shared_kernel`) and feed Goal 10 (`hello-node` p50/p95). The draft correctly
identified the four deliverables and traced cleanly to ADR-0001 (chokepoint
discipline), ADR-0004 (DinD = shared_kernel), ADR-0012 (env allowlist), and
ADR-0013 (digest-pinned policy), but had **five block-tier contradictions**
that an executor following the draft literally would have hit on first import
— three of which were recurrences of contract bugs that sibling validations
(S3-01, S3-02, S3-03) had already caught and removed from the production
surface.

The dominant failure pattern: the draft was written before S3-01..S3-05's
validations landed, so it referenced API surfaces (`allowlist=`,
`for_gate_test_override`) that were explicitly *removed* during sibling
hardening. The fourth block (phantom `hello-node` fixture) is a new finding
— the draft assumed the fixture was Phase-3/4 carryover, but `ls
tests/fixtures/repos/` confirms it was never shipped, which would silently
skip all four tests (the worst failure mode for an integration suite,
since the lane reports "ok" while delivering zero coverage).

## Findings (severity, lens, fix)

### Block-tier (would-not-compile / would-silently-pass)

1. **(consistency — block) `DockerInDockerClient(allowlist=allowlist)`** in
   all four draft tests. S3-02 `_validation/` finding #1 dropped the
   `allowlist` parameter entirely; the hardened signature is `__init__(self,
   *, docker_url: str | None = None, docker_factory: Callable[[],
   DockerClient] = docker.from_env)`. Draft would `TypeError` at construction.
   **Fix:** AC-CLIENT-CTOR-1 pins the bare default form; AC-CLIENT-CTOR-2 +
   `tests/sandbox/test_no_allowlist_kwarg_in_integration.py` grep-guard
   against reintroduction. TDD-plan code blocks rewritten.
2. **(consistency — block) `stage6_spec_builder.for_gate_test_override(...)`
   is a phantom method.** S3-01 HARDENED AC-API-2 pins `set(__all__) ==
   {"SandboxSpecBuilder"}`; AC-FG-1 pins the only public method as
   `for_gate(gate, attempt, ctx)`. The draft's proposed overrides
   (`memory_limit_mib`, `time_budget_seconds`, `network`, `egress_allowlist`,
   `cmd_override`) bypass the catalog→SandboxSpec translation S3-01/S3-05
   own. Worse, the draft contradicted itself in Green ("add on builder…keep
   in conftest"). **Fix:** AC-NO-PHANTOM-1..-3 construct `SandboxSpec`
   directly via Pydantic (the unit under test is `DockerInDockerClient`, not
   the builder); use the pure `_canonical_blake3` helper S3-01 exposes for
   reuse to compute `sandbox_spec_hash`.
3. **(consistency — block) `tests/fixtures/repos/hello-node/` does not
   exist.** Draft claimed Phase-3/4 carryover and Out-of-scope said "do not
   regenerate." Reality: only `express-cve-2024-21501` and `malicious-npmrc`
   exist under `tests/fixtures/repos/`. Without the fixture, all four tests
   skip and the lane silently reports "ok" with zero coverage. **Fix:**
   AC-FIXTURE-1 has this story scaffold a minimal `hello-node/` (single
   `package.json` + README placeholder); AC-FIXTURE-2 verifies the shape in a
   no-docker lane. The full `npm ci`/120-test variant is properly owned by
   the install/test signal collector story (Step 4).
4. **(consistency — harden) `python3 -c '...'` in the OOM cmd** — the
   draft's hedge ("python3 typically exists; fall back to node") is the
   exact silent-failure Rule 12 forbids. **Fix:** AC-OOM-CMD-1 mandates
   `node -e "Buffer.alloc(1e9)"` unconditionally (`node` is guaranteed by
   the Chainguard Node base image); AC-OOM-CMD-2 grep guards.
5. **(coverage + test-quality — block) Egress test asserts only stdout
   contents** — passively satisfied on any runner where github.com is
   unreachable for unrelated reasons (corporate firewall, mid-test outage,
   host routing) even when the iptables chokepoint never ran. **Fix:**
   AC-EGRESS-EVIDENCE-1..-4 — (a) `--max-time 5 --connect-timeout 3` so a
   drop fails fast, (b) capture curl rc via `echo rc=$?` and assert `rc ∈
   {28, 7}` (canonical timeout / no-connect signatures), (c) assert
   `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED` appears EXACTLY ONCE per run
   in captured structlog events (proves the chokepoint actually ran — closes
   ADR-0001 escape hatch), (d) `run_ok.run_id != run_blocked.run_id` defends
   against fake-client constants.

### Harden-tier (would-silently-mis-narrow)

6. **(coverage — harden) `gate_isolation_class` Literal-narrowing
   unverified.** Draft asserts `== "shared_kernel"` but does not guard the
   two-value Literal from silent ADR-0004 widening. **Fix:**
   AC-RUN-CONTRACT-1 + AC-RUN-CONTRACT-2 ship `typing.get_args` guards in a
   no-docker test (`tests/sandbox/test_sandbox_run_isolation_class_literal.py`).
7. **(test-quality — harden) `exit_code == 137`** for timeout
   over-asserts. SIGKILL via Docker is 137 today; the canonical contract is
   the `SandboxRun.timed_out=True` boolean (arch §Edge case 3). **Fix:**
   AC-TIMEOUT-1 keeps the boolean assertion; AC-TIMEOUT-2 records the
   observed `exit_code` into the perf row for trend observation without
   gating.
8. **(test-quality — harden) `re.search(r"\d+\.\d+\.\d+", stdout)`** for
   happy path matches too broadly. **Fix:** AC-HAPPY-1 tightens to
   `re.fullmatch(r"\d+\.\d+\.\d+", stripped)` on the trimmed stdout.
9. **(coverage — harden) Cleanup + concurrency unspecified.** Tests can
   leak Docker containers on failure; pytest-xdist parallel runs would race
   on iptables rules (global kernel state). **Fix:** AC-CLEANUP-1 (per-label
   leak-sweep finalizer), AC-CONCURRENCY-1/-2 (`pytest.mark.serial` +
   `-p no:xdist` for this lane + `Makefile` target capture).
10. **(coverage — harden) Skip-path verification missing.** Draft AC says
    "skip cleanly when Docker unreachable" but no test verifies it. **Fix:**
    AC-SKIP-1 monkeypatches `docker.from_env` to raise; asserts the fixture
    calls `pytest.skip` (not raises/errors).
11. **(consistency — harden) `codegenie sandbox health` CLI** is S8-01
    territory and `src/codegenie/cli/sandbox.py` doesn't exist yet. **Fix:**
    AC-CLI-SMOKE-1 demotes to manual verification in `_attempts/S3-07.md`;
    the canonical test-level smoke is a direct `SandboxHealthProbe.run()`
    invocation from S3-06.
12. **(test-quality — harden) Perf row writer untested.** Draft mentions
    JSONL emission but no assertion on shape. **Fix:** AC-PERF-1 pins
    closed-set keys + `tests/sandbox/test_perf_row_writer.py` validates
    against a parametrized grid under a fake clock and fake `SandboxRun`.

### Patterns (Open/Closed + Hexagonal-port uniformity)

13. **(patterns — harden, Open/Closed) Parametrize over a scenario
    table.** Four tests with near-identical setup → execute → assert shape.
    Adding a fifth scenario should be a one-row diff. **Fix:**
    AC-SCENARIO-TABLE-1 + AC-PATTERN-1 — `tests/integration/sandbox/_scenarios.py`
    carries `_SCENARIOS: Final[tuple[Scenario, ...]]`; happy + timeout tests
    parametrize off it; OOM + egress stay standalone (unique-shape
    assertions); AST-walked by `test_integration_scenario_extensibility.py`.
14. **(patterns — harden, DI uniformity) `docker_available` fixture
    should consume the `docker_factory` port** S3-02 ships. **Fix:**
    AC-PATTERN-2 — fixture takes `docker_factory: Callable[[],
    DockerClient] = docker.from_env` (overridable in AC-SKIP-1 via
    monkeypatch); aligns production + test seams.

## Critic-resolution notes

- **Coverage vs Consistency conflict:** none.
- **Test-Quality vs Coverage conflict:** none — both pushed toward more
  rigorous evidence on the egress and timeout assertions.
- **Design-Patterns vs Rule 2 ("three similar lines is better than premature
  abstraction"):** the four integration tests crossed the Rule-of-Three
  threshold for the scenario-table parametrization (four sibling tests, with
  a fifth `copy_out` already foreseeable in §K of the story's Notes-for-implementer
  context). The parametrization is elevated to an AC (AC-PATTERN-1) because
  the third concrete consumer of the pattern has arrived. The OOM + egress
  standalones stay because their assertions are unique-shape — the goal is
  extension-by-addition, not uniformity-for-uniformity.

## Stage 3 — Research

Not invoked. All findings were resolvable from the repo (sibling-story
HARDENED contract surfaces in `_validation/` + arch + ADRs + the actual
filesystem state of `tests/fixtures/repos/`); no `NEEDS RESEARCH` tags
fired.

## Edits applied (story file)

- Status `Ready → HARDENED`.
- `Depends on:` widened to enumerate S3-01..S3-05's *hardened* contract
  surfaces explicitly (no `allowlist=`, no `for_gate_test_override`, etc.).
- `ADRs honored:` adds ADR-0014 (frozen Pydantic surface).
- New `Validation notes (2026-05-24)` block with 14 numbered findings.
- `Acceptance criteria` section replaced with structured A–K subsections
  carrying 30 explicit AC- identifiers (vs 12 unstructured bullets).
- `Implementation outline` rewritten to the post-S3-02/S3-03 surface.
- `TDD plan` code blocks rewritten — direct `SandboxSpec` Pydantic
  construction; `_canonical_blake3` reuse; `caplog_events` capture;
  parametrized scenario table; `node -e "Buffer.alloc(1e9)"` for OOM;
  `--max-time 5 --connect-timeout 3` on every curl; rc-extraction with
  `_ACCEPTABLE_DROP_RCS` constant; structlog event-count assertions.
- `Files to touch` table grown from 8 → 17 entries, mapping each to the
  AC it satisfies (including the seven no-docker guard tests that close
  the silent-pass holes).
- `Notes for the implementer` rewritten — 11 bullets, each citing the AC
  it backs; load-bearing warnings (no `allowlist=`, no
  `for_gate_test_override`, `node -e` OOM, structlog evidence for egress,
  `--max-time`, serial-run requirement) pinned at the top.

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`. The executor
should:

1. Land the seven no-docker guard tests FIRST (AC-FIXTURE-2,
   AC-CLIENT-CTOR-2, AC-NO-PHANTOM-1, AC-RUN-CONTRACT-1/2, AC-SKIP-1,
   AC-PERF-1 writer, AC-PATTERN-1) — they catch every contract drift before
   a single Docker container boots.
2. Then land the four integration tests + the perf-writer module.
3. Verify the integration lane runs serially in CI.
4. Record the `SandboxHealthProbe.run()` manual smoke in `_attempts/S3-07.md`.

Open follow-ups (out of scope for this story, deferred to sibling work):

- Full `hello-node` fixture (`package.json` + `npm ci` + 120 unit tests)
  — owned by Step-4 install/test signal collector story.
- `codegenie sandbox health` Click CLI — owned by S8-01.
- Firecracker integration suite parity — owned by S6-01.
