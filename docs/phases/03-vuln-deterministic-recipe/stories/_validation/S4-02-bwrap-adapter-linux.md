# Validation report — S4-02 `BwrapAdapter` (Linux)

**Verdict:** HARDENED
**Validated:** 2026-05-18
**Story file:** `../S4-02-bwrap-adapter-linux.md`

## Summary

Story has solid intent and excellent fail-not-skip discipline, but four critics surfaced 3 BLOCK-grade structural problems (a factual API contradiction with the existing `run_external_cli`; a runtime-Protocol `isinstance` that S4-01 explicitly forbids; and an undeclared runtime dependency on `pyseccomp`/`seccomp`) plus 17 harden-grade gaps in mutation-resistance, design-pattern shape, edge-case coverage, and primitive-obsession on syscall names. All BLOCKs are fixable through AC rewriting + an Implementation-outline correction + an explicit precondition coordination note with S4-05 — no `phase-story-writer` re-run needed. Edits applied in place; the executor receives a story whose ACs collectively constrain a correct implementation and whose TDD plan would catch obvious mutants.

## Context Brief

- **What the story promises:** `BwrapAdapter(SubprocessJail)` lands at `src/codegenie/transforms/sandbox/bwrap.py`, wrapping every Phase-3 subprocess in bwrap + seccomp + netns; integration test fails (not skips) when bwrap is missing on Linux; every `JailedSubprocessResult` variant translatable from underlying signals.
- **Phase exit-criterion this serves:** Goal G1 (`codegenie remediate --cve <id>` runs `npm install` + `npm test` inside `SubprocessJail`); Goal G6 (zero edits to Phase 0/1/2 — only ADR-0012 amendment + import-linter contracts).
- **Arch + ADR constraints:** ADR-0006 §Decision pins the bwrap command line, the six blocked syscalls (`mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`), and the `NetworkPolicy` sum-type semantics (`DenyAll | RegistryAllowlist`). ADR-0012 §Decision claims the adapter routes through `run_external_cli` — see Critic-Consistency finding #1; this is documentation drift.
- **CLAUDE.md commitments:** "Extension by addition" (the second `SubprocessJail` Adapter must share substrate-agnostic logic with the first), "Functional core / imperative shell" (pure `run`-helpers separable), "Newtype identifiers" (syscall names should not be raw `str`), "Match the existing convention" (`@register_*` registries, module-level `Final` tuples, sum-type `match` discipline).

## Stage 2 — Critic reports

Four critics ran in parallel. Severity legend: `block` = must rewrite/coordinate before executor; `harden` = real gap that mutates-survive; `nit` = small polish.

### Critic A — Coverage (executor's view: do the ACs collectively constrain a correct implementation?)

| # | Severity | Title |
|---|---|---|
| B1 | block | `env_extra` doesn't exist on `run_external_cli` — Goal #3 and AC-10 are unimplementable as written. |
| B2 | block | `run_external_cli` already wraps argv in its own bwrap (double-wrap on Linux). |
| B3 | block | AC-2 doesn't pin which chokepoint is invoked or the `probe_name` argument. |
| H1 | harden | SIGKILL discriminator gap (timeout vs OOM both produce SIGKILL on Linux). |
| H2 | harden | `NetworkDenied` false-positive prevention is absent — a DNS failure could be misclassified. |
| H3 | harden | `DiskQuotaExceeded` mechanism is aspirational; Notes admit "rarely-triggered." |
| H4 | harden | Cleanup-on-exception (seccomp temp file, netns, pf rules) is untested. |
| H5 | harden | Concurrent `BwrapAdapter().run()` from different asyncio tasks — netns/iptables race. |
| H6 | harden | Authority contradiction `High-level-impl.md:128` (skip) vs L310 + ADR-0006 (fail) is unresolved in the story. |
| H7 | harden | AC-15 (CI integration) has no runtime evidence today — depends entirely on S9-01. |
| H8 | harden | `_setup_netns_with_allowlist` requires `CAP_NET_ADMIN`; behavior when absent is unspecified. |
| N1 | nit | AC-9 fallback to `node -e fetch(...)` is unverified — neither `curl` nor `node` availability is pinned. |
| N2 | nit | AC-12 postinstall canary fixture layout is opaque (no path, no fixture directory). |
| N3 | nit | Empty `spec.cmd` / `None` env edge cases unspecified. |
| N4 | nit | SIGINT-during-run / orphaned bwrap child not asserted. |
| N5 | nit | Non-existent `SandboxedPath` dir not handled at the Port boundary. |

### Critic B — Test Quality (mutation-resistance lens)

| # | Severity | Title |
|---|---|---|
| TQ-1 | block | AC-1 `isinstance(BwrapAdapter(), SubprocessJail)` will `TypeError` — S4-01 explicitly forbids `@runtime_checkable`. |
| TQ-2 | block | AC-10 asserts `env_extra` parameter that `run_external_cli` does not have. |
| TQ-3 | block | AC-5 sentinel-string indirection through `_fakes_for_tests` pins nothing concrete; mutant fakes trivially pass. |
| TQ-4 | harden | AC-4 substring grep escapable (`from subprocess import run`; `getattr(subprocess, "run")(...)`; `os.exec*`; `os.spawn*`). |
| TQ-5 | harden | AC-3 seccomp test pins the helper-call boundary, not the kernel-boundary effect. |
| TQ-6 | harden | AC-2 argv-prefix-only check allows injected dangerous flags between prefix and `spec.cmd`. |
| TQ-7 | harden | AC-11 first loop (`for token in cmd: assert token in argv`) is dead weight — out-of-order tokens pass. |
| TQ-8 | harden | AC-12 postinstall canary lacks fixture details and detection mechanism; no negative control. |
| TQ-9 | harden | No AC verifies Goal §49's promise that "no bare exceptions cross the Port boundary." |
| TQ-10 | harden | Missing Hypothesis-driven property tests (DenyAll → no `--share-net`; allowlist host coverage; verbatim `cmd` preservation; determinism). |
| TQ-11 | harden | No determinism AC (same input spec → same argv + same seccomp bytes). |
| TQ-12 | nit | AC-9 live test silently skips if neither `curl` nor `node` available — mirrors the fail-not-skip discipline AC-8 enforces. |
| TQ-13 | nit | Performance-envelope claim (~80–200 ms) has no observable AC. |

### Critic C — Consistency (arch / ADR / CLAUDE.md / existing-code)

| # | Severity | Title |
|---|---|---|
| C-1 | block | `run_external_cli` chokepoint is fundamentally misused — story prescribes API that conflicts with Phase 2 ADR-0001 + the regression test `test_allowed_binaries_closed_set_regression` (which pins `bwrap` and `bubblewrap` as MUST-NOT-be-allowlisted). |
| C-2 | block | `isinstance(BwrapAdapter(), SubprocessJail)` violates S4-01 AC-2 (NOT `@runtime_checkable`). |
| C-3 | block | Silent introduction of new Python runtime dep (`pyseccomp`/`seccomp`) in Notes-for-implementer without ADR amendment. |
| C-4 | harden | `spec.cwd.absolute` is a bound-method, not a property; `str(bound_method)` yields `"<bound method...>"`. |
| C-5 | harden | `_fakes_for_tests.py` under `src/` violates "no test code in src" hygiene. |
| C-6 | harden | `SandboxedPath` integration-test import path drifts from S4-01 AC-11 (`codegenie.transforms._forward`, NOT `codegenie.plugins.sandbox_path`). |
| C-7 | harden | `bench_workflow_e2e_warm` substrate cost (~80–200 ms) has zero observable AC. |
| C-8 | harden | AC-9 implicitly requires `curl` in `ALLOWED_BINARIES` (it's in the deny list of the closed-set regression test). |
| C-9 | nit | Doc-debt: `High-level-impl.md:128` wording "must pytest.skip" contradicts ADR-0006 + L310 + this story's correct "must pytest.fail." |
| C-10 | nit | AC-12 canary verifies the CLI flag `--ignore-scripts`, not the substrate binds (passes even if bwrap is misconfigured). |

### Critic D — Design Patterns

| # | Severity | Title |
|---|---|---|
| D-H1 | harden | Outcome classifier not extracted; `SandboxExecAdapter` (S4-03) will duplicate it. |
| D-H2 | harden | `_fakes_for_tests.py` under `src/` is a code smell (overlaps C-5). |
| D-H3 | harden | Primitive obsession on syscall names (`set[str]` — typos fail silently). |
| D-H4 | harden | `NetworkPolicy` dispatch must be `match` (sum-type), not `isinstance` ladder. |
| D-H5 | harden | Hidden state via module-level globals (warn-once pattern from `run_external_cli`'s `_BWRAP_WARNED`). |
| D-H6 | harden | `run_external_cli` signature mismatch (overlaps C-1 / B1 / TQ-2). |
| D-H7 | harden | OOM / DiskQuotaExceeded detection mechanism left as "Adapter-author choice" (overlaps Coverage H1, H3). |
| D-N1 | nit | Registry pattern for substrates: explicitly rule it out (constructor injection is the right shape). |
| D-N2 | nit | Confirm `BwrapAdapter` does NOT carry a capability token (capabilities gate recipe engines, not substrates). |
| D-N3 | nit | Production-side types should be tight throughout (`argv: list[str]`, `cmd: tuple[str, ...]`); test `dict[str, object]` is scaffolding only. |

## Stage 3 — Researcher

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. Every fix has an in-codebase precedent (`test_outcomes_mypy_negative.py` for subprocess-mypy negative; `_GENERATOR_HEADER_MARKERS` for module-level `Final` tuples; `@register_*` for registry decision; S4-01 `_StubJail` for structural Protocol conformance; Phase 2 ADR-0006 for sum-type `match` discipline) or a standard library tool (`ast` for AST grep, `hypothesis` for property tests, `cgroups v2 memory.events` for OOM signal source).

## Stage 4 — Synthesis + edits applied

**Conflict-resolution decisions:**

- **Consistency C-1 / Coverage B1-B3 / TQ-2 / D-H6 — chokepoint reconciliation:** Per `Consistency > Coverage > Test-Quality > Design-Patterns` priority and CLAUDE.md Rule 7 ("Surface conflicts, don't average them"): the story is amended to call `run_allowlisted` directly (not `run_external_cli`). Rationale: `run_allowlisted` already has `env_extra`, performs a single allowlist check on `argv[0]`, and does NOT do implicit bwrap-wrapping (the implicit-wrap is `run_external_cli`'s probe-binary concern, structurally separate from the SubprocessJail-adapter concern). ADR-0012 §Decision wording ("`run_external_cli`") is **documentation drift** — flagged as doc-debt for an ADR-0012 amendment that the implementer surfaces in the attempt log. S4-05 must (a) add `bwrap` and `sandbox-exec` to `ALLOWED_BINARIES` AND (b) remove `bwrap`/`bubblewrap` from the `test_allowed_binaries_closed_set_regression` deny-list (line 362-363 of `tests/unit/test_exec.py`).

- **Consistency C-3 — `pyseccomp` dep:** Mandate the hand-written BPF + `tools/seccomp/build_filter.py` helper path. Removes the "either is fine" defer-to-implementer choice. Six syscalls are a fixed list — the BPF program is ~30 lines of hand-rolled bytecode using `audit_arch` + `BPF_*` constants from `linux/seccomp.h` (Python `ctypes` or a one-row `struct.pack` table). No new dep needed; no ADR amendment required.

- **Design-pattern D-H4 vs Rule 2 — registry for substrates:** Critic D-N1 wins (rule it out — constructor injection is the right shape). Add to Notes.

- **All other findings:** applied as proposed.

**Story edits (summary):**

1. `Validation notes` block prepended under the story header (this report's per-finding decisions in story-local form).
2. AC-1 rewritten: structural mypy + `inspect.signature` + `_StubJail`-style call-site test; no `isinstance`.
3. AC-2 rewritten: explicit `run_allowlisted` call site; argv full-shape assertion (prefix + seccomp flags + cmd-tail = entire argv with no leftover); no `probe_name` (it's a `run_external_cli` concept).
4. AC-3 strengthened: helper-input assertion + helper-output-bytes assertion + integration-tier kernel-boundary test (`unshare -U /bin/true` inside live jail → non-zero exit with SIGSYS).
5. AC-4 rewritten: AST-based check; covers `subprocess.*`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `asyncio.create_subprocess_*`, and `getattr(subprocess, ...)` indirections.
6. AC-5 rewritten: direct mocks of `run_allowlisted` with real-shape `ProcessResult` (returncode=-9 + elapsed>budget → `TimedOut`; returncode=0 → `Completed`; etc.); explicit SIGKILL discriminator pinned (timeout-vs-OOM tie-break: if `elapsed_s >= time_budget_s` then `TimedOut`, else if `peak_rss_mib >= memory_mib` then `OomKilled`, else `Completed(exit_code=-9)`).
7. AC-6 / AC-7 strengthened: full-argv-shape DenyAll check + property test that ∀ allowlist hosts → all appear in netns-setup call.
8. AC-8 / AC-9 strengthened: AC-9 replaces `curl` with `node -e "fetch(...)"` (avoids the closed-set regression); both add explicit `pytest.fail` when required inner binary missing on Linux runner.
9. AC-10 rewritten: assertion against `run_allowlisted`'s `env_extra` parameter (now real, not phantom).
10. AC-11 simplified: drop the dead first loop; keep `tuple(argv[-len(cmd):]) == cmd` strict tail.
11. AC-12 strengthened: fixture path pinned (`tests/fixtures/phase03/postinstall_canary/`); canary path explicit; **negative control** added (same fixture without `--ignore-scripts` and without bwrap → canary IS written, proving the test detects substrate breakage).
12. New AC-16: typed-error fence (no bare exception escapes Port boundary; parametric failure-injection test).
13. New AC-17: determinism property (same spec → same argv + same seccomp bytes across two consecutive calls).
14. New AC-18: property-based tests for DenyAll-no-share-net, allowlist-host-coverage, verbatim-cmd-preservation.
15. New AC-19: cleanup-on-exception (try/finally + `tempfile.TemporaryDirectory` discipline; assert no leaked temp files/netns/iptables rules).
16. New AC-20: concurrent-run serialization (asyncio.Lock instance-level OR unique-named netns per call; pinned).
17. New AC-21: `CAP_NET_ADMIN` absent → typed `NetworkPolicySetupFailed(reason)` variant OR skip the live-test fixture with a loud message (NOT silent skip).
18. New AC-22: stateless across calls (no module-level mutable globals introduced by `bwrap.py`).
19. New AC-23: `_classify_outcome` extracted to `src/codegenie/transforms/sandbox/_classify.py`; pure; unit-tested with parametric inputs; consumed by both `BwrapAdapter` and (future) `SandboxExecAdapter`.
20. New AC-24: `Syscall` `StrEnum` for the six blocked syscalls + module-level `_BLOCKED_SYSCALLS: Final[frozenset[Syscall]]`; no string-literal hard-coding at call sites.
21. New AC-25: `match spec.network` (exhaustive on `NetworkPolicy` sum), not `isinstance` ladder; mypy proves exhaustiveness.
22. New AC-26: perf smoke (Linux-only, `@pytest.mark.bench`-marked, NOT in `make check`): `BwrapAdapter().run(spec_for_echo_hi)` wall time < 1.0 s on a warm jail.
23. Files-to-touch: drop `src/codegenie/transforms/sandbox/_fakes_for_tests.py`; replace with `tests/unit/transforms/sandbox/_fakes.py`. Add `src/codegenie/transforms/sandbox/_classify.py`. Add `tools/seccomp/build_filter.py` (hand-written BPF helper). Add `tests/fixtures/phase03/postinstall_canary/` (fixture dir).
24. Implementation outline: `spec.cwd.absolute` → `str(spec.cwd)`; chokepoint changed to `run_allowlisted`; OOM signal source pinned (cgroups v2 `memory.events:oom_kill` post-mortem, with `child_returncode == -SIGKILL AND peak_rss > spec.memory_mib` fallback); NetworkDenied detection pinned (host ∉ allowlist AND parent observed netns/pf block event; ambiguous failures → `Completed(exit_code=N)` to prevent false positives); cleanup discipline pinned (try/finally with TemporaryDirectory).
25. Out-of-scope: append doc-debt notes for ADR-0012 §Decision rewording and High-level-impl.md:128 wording (both deferred to a doc-only follow-up; this story surfaces them in the attempt log).

## Files written

- `docs/phases/03-vuln-deterministic-recipe/stories/S4-02-bwrap-adapter-linux.md` — edited in place (HARDENED).
- `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S4-02-bwrap-adapter-linux.md` — this report.

## Pre-executor coordination (must read)

Before executing this story, the implementer (or their pre-flight) MUST:

1. Confirm S4-05 has landed (or land it as a precondition) — ALLOWED_BINARIES amendment + `test_allowed_binaries_closed_set_regression` update.
2. Confirm S4-04 has landed (or use `FakeSandboxedPath` for the unit tests and gate the integration tests behind `pytest.importorskip` with a loud message).
3. Surface in `_attempts/S4-02.md` Attempt 1: "ADR-0012 §Decision wording drift — adapters route through `run_allowlisted`, not `run_external_cli`. Pre-existing `run_external_cli` is the Phase 2 probe-binary chokepoint (does its own bwrap-wrap); adapters cannot use it without breaking either the closed-set regression test or the double-wrap invariant. Follow-up: amend ADR-0012 §Decision in a doc-only story." + "`High-level-impl.md:128` says skip-not-fail; ADR-0006 + L310 + this story say fail-not-skip. The latter wins. Surface as doc-debt in the next phase-arch-design refresh."
