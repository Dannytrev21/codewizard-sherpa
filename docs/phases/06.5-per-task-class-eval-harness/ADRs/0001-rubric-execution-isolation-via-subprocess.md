# ADR-0001: Rubric runs as a scrubbed-env subprocess — not in-process, not microVM

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** isolation · security · trust-boundary · rubric
**Related:** [ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md), [Phase 5 ADR-0012](../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

The rubric is control-plane code: it produces `BenchScore`, which feeds the promotion gate, which determines whether a task class graduates to a higher trust tier. A rubric is also untrusted in the same sense bench-case data is — it lives under `bench/{task-class}/rubric.py`, a CODEOWNERS-gated path that any contributor may PR. The performance-first design imports `bench.{tc}.rubric` directly and runs it in-process; the security-first design wraps it in a per-case Firecracker microVM with no network or FS. The critic identified rubric isolation as **the** load-bearing fork for Phase 6.5 (critic §"Which disagreement matters most for *this* phase?"): scores are not invariant under the isolation upgrade — different process model, different timing, different environment yield different `BenchScore`s, and that mismatch silently mixes scoring populations in the audit chain.

Two empirical constraints narrow the option space: (a) macOS curators are the daily-loop audience, and Phase 5's Firecracker stack does not run on macOS without Lima/QEMU — forking the sandbox onto another substrate for rubric-only isolation breaks the dev/curator loop ([design-security.md §Risks #1](../design-security.md)); (b) the rubric runs once per case in nightly CI — ~150 ms/case subprocess spawn overhead is absorbed by the nightly budget (`final-design.md §Resource & cost profile`), while a multi-second microVM cold-start per case pushes ≥10-case runs into ~5-minute territory before the SUT has even invoked.

Half-isolation is the worst path the critic warned about ("if the harness ships with in-process rubric execution, every operator who has run the bench has executed every rubric ever merged on their host with their environment, and the threat model is closed retroactively only by re-running every eval inside a microVM — which produces a different score"). The decision is not "is microVM eventually better?" — it is "what is the right starting posture given the curator UX, the audit-chain invariance requirement, and the threat model?"

## Options considered

- **In-process import.** `bench.{tc}.rubric.score(...)` called directly. Zero overhead, full Python data sharing. Risk: any rubric edit is RCE on the operator's laptop with full env (incl. `ANTHROPIC_API_KEY`, `AWS_*`, full FS access). Fails the threat model "compromised contributor PR."
- **Full microVM (Firecracker / gVisor).** Per-case microVM with no network, scrubbed env, mounted JSON I/O. Strongest isolation. Cost: per-case cold-start in seconds (not 100 ms — the rubric needs Python + deps), macOS-incompatible without a new sandbox substrate (forks Phase 5's stack), and locks Phase 6.5 from shipping until the substrate exists.
- **Subprocess + scrubbed env, stdin/stdout JSON, tempdir `cwd`.** `asyncio.create_subprocess_exec("python", str(rubric_path), env=SCRUBBED, cwd=tempdir)`. Defeats credential read (no `ANTHROPIC_API_KEY` reachable), defeats arbitrary FS write outside the wiped tempdir, defeats arbitrary in-harness import. Does **not** defeat host-level network egress. Cost: ~150 ms/case spawn overhead. macOS-friendly (stdlib only).

## Decision

The eval runner invokes the rubric as a subprocess: `asyncio.create_subprocess_exec("python", str(rubric_path), stdin=PIPE, stdout=PIPE, stderr=PIPE, env=SCRUBBED_ENV, cwd=tempfile.TemporaryDirectory())`. `SCRUBBED_ENV` carries only `PYTHONPATH`, `PYTHONHASHSEED=0`, and a minimal `PATH` — no `ANTHROPIC_API_KEY`, `AWS_*`, `HOME`, or `USER`. The rubric reads JSON on stdin, writes a `BenchScore` JSON on stdout, and is killed at `case.rubric_wall_clock_seconds` (default 60 s, max 300 s). The bench-author unit tests (`bench/{tc}/tests/test_rubric_unit.py`) bypass subprocess isolation and import the rubric directly — `tests/` is a trusted boundary; `runner.py` is not.

## Tradeoffs

| Gain | Cost |
|---|---|
| Defeats the dominant threats for "compromised contributor PR": credential read, harness-internal-state read, arbitrary FS write outside tempdir | Does not defeat host-level network egress — a rubric `urllib.request.urlopen(...)` reaches the internet (explicit residual risk; CODEOWNERS on `bench/**/rubric.py` is the compensating control) |
| Stdlib-only — `asyncio.create_subprocess_exec` + `tempfile.TemporaryDirectory` work on macOS and Linux identically; no Lima/QEMU stack to maintain | ~150 ms/case spawn overhead (~1.5 s on a 10-case run) — absorbed by the nightly budget but real |
| Audit chain population is single-isolation-class for the entirety of Phase 6.5 — scores are comparable across the whole window | Phase 16 microVM upgrade will produce a new isolation class; the audit chain must annotate (see [ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md)) to prevent silent population mixing |
| `SCRUBBED_ENV` reuses the [Phase 5 ADR-0012](../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md) `env_allowlist.filter({})` pattern — same discipline, same review surface | Two scrub paths to keep in sync (Phase 5's sandbox; this phase's rubric subprocess) — divergence is a CODEOWNERS-visible audit risk |
| Tempdir `cwd` (atomic wipe on `__exit__`) means the rubric cannot poison the working tree even on a malicious-PR scenario | A rubric that forks a child process may strand it past tempdir teardown (`final-design.md §Open Q #3`); Phase 16 may add process-group-kill on teardown |
| Adversarial test surface is meaningful: `tests/adv/test_rubric_subprocess_env_scrubbed.py` asserts `os.environ.get("ANTHROPIC_API_KEY") is None` from inside the rubric | Adversarial tests must mirror Phase 5's discipline (same expectations, different harness); test maintenance cost grows linearly with new env scrub layers |

## Consequences

- `src/codegenie/eval/runner.py` invokes the rubric across a process boundary; the `Rubric` Protocol exists primarily so bench-author unit tests can type-check (the runner does not type-check the subprocess — there is no static type relationship across the process boundary).
- The rubric's `if __name__ == "__main__":` entrypoint is the bench-author's load-bearing surface — bench-author tests verify both the `score(...)` function (in-process) and the subprocess CLI (`python rubric.py < stdin > stdout`).
- The runner produces typed `FailureMode`s for rubric subprocess failure paths: `rubric.malformed_output` (non-zero exit / `pydantic.ValidationError`), `rubric.timeout` (`subprocess.TimeoutExpired`), `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`. All are `severity="block"` per the task-class taxonomy (see [ADR-0004](0004-per-task-class-failure-modes-taxonomy.md)).
- Phase 7's migration rubric inherits the subprocess shape — Phase 7 cannot opt back into in-process execution without an ADR amendment.
- The audit chain emits `isolation_class="subprocess"` on every `BenchRunReport` (see [ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md)); Phase 16 upgrade flips the field, and the promotion gate refuses to mix populations.
- Network egress is the explicit residual; CODEOWNERS on `bench/**/rubric.py` (`@codewizard-sherpa/security`) plus the eval-curators team's two-reviewer rule on `bench/` are the compensating controls until Phase 16.
- `[Phase 5 ADR-0012](../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md)`'s precedent extends: any new env var the harness exposes to the rubric requires an explicit allowlist entry.

## Reversibility

**Medium.** Reverting to in-process is mechanically easy (delete the subprocess plumbing in `runner.py`, call `task_class.rubric_class().score(...)` directly) but invalidates every `BenchRunReport` produced under subprocess isolation — different timing, different env, different rubric exception surface mean the prior population is non-comparable. Phase 16 upgrade to full microVM is the *forward* path; [ADR-0010](0010-isolation-class-annotation-on-bench-run-report.md) annotates the chain so the upgrade is detectable. Backing out to in-process loses the trust posture and is unlikely; backing forward to microVM is the planned escape hatch.

## Evidence / sources

- [final-design.md §Departures from all three inputs #1](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Synthesis ledger row "Rubric execution model"](../final-design.md#conflict-resolution-table)
- [final-design.md §Risks #2](../final-design.md#risks-top-5)
- [phase-arch-design.md §Agentic best practices — Tool-use safety](../phase-arch-design.md#agentic-best-practices)
- [phase-arch-design.md §Non-goals #1](../phase-arch-design.md#non-goals)
- [critique.md §"Which disagreement matters most for *this* phase?"](../critique.md#which-disagreement-matters-most-for-this-phase)
- [Phase 5 ADR-0012](../../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md) — env-allowlist pattern reused
- [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the anchor commitment this implements
