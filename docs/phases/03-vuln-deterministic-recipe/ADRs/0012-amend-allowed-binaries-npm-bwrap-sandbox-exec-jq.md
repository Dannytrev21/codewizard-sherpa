# ADR-0012: Amend `ALLOWED_BINARIES` with `npm`, `bwrap`, `sandbox-exec`, `jq` (amends Phase 2 ADR-0001)

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** subprocess-discipline · allowed-binaries · amendment · supply-chain
**Related:** [0006](0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md), [0007](0007-run-npm-install-and-npm-test-in-phase3-jail.md), [Phase 2 ADR-0001](../../02-context-gather-layers-b-g/ADRs/), production ADRs

## Context

Phase 2 ADR-0001 (the omnibus subprocess-discipline ADR for Phase 2) established `ALLOWED_BINARIES` as a closed `frozenset` in `src/codegenie/exec/__init__.py`: every external CLI invocation must route through `run_allowlisted` / `run_external_cli`, and the allowlist is amendment-only. The `forbidden-patterns` pre-commit hook bans `subprocess.run(..., shell=True)`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, and `pickle.loads` repo-wide.

Phase 3 needs four binaries Phase 2 did not enable:

1. **`npm`** — for the recipe engine's `npm install --package-lock-only`, the Stage-6 validate's `npm install` + `npm test`. Without it, the roadmap exit criterion is unmeetable.
2. **`bwrap`** — the Linux `SubprocessJail` adapter (per ADR-0006). The jail spawns child processes under `bwrap --unshare-all --new-session --die-with-parent ...`.
3. **`sandbox-exec`** — the macOS `SubprocessJail` adapter (per ADR-0006). Even though it's deprecation-flagged by Apple, it's the only built-in macOS sandbox primitive Phase 3 can use without Phase 5's Lima/DinD infrastructure.
4. **`jq`** — operator-tooling adjunct used by debugging helpers (`codegenie audit verify | jq ...` patterns documented in the runbook); occasionally invoked by integration tests to inspect JSON event streams.

Phase 0/2 ADRs require an explicit ADR amendment to extend the allowlist. The architecture spec calls this out explicitly (`phase-arch-design.md §Goal G6`, §Agentic best practices, §Path to production §Phase 3 ADRs #P3-008).

## Options considered

- **Option A — Don't amend; route `npm` through a wrapper that calls Python's `requests` directly to the npm registry.** Re-implements npm. Unbounded scope, breaks at every npm semantic change. **Pattern:** wheel reinvention.
- **Option B — Amend `ALLOWED_BINARIES` with all four binaries, with a one-line justification per addition and the smallest possible privilege envelope per use.** **Pattern:** Allowlist extension with documented rationale.
- **Option C — Bypass the allowlist with a Phase-3-specific `run_jailed` function that does NOT go through `run_allowlisted`.** Splits the discipline; creates a parallel path subprocess invocations can hide in. **Pattern:** Subprocess discipline violation.

## Decision

Adopt **Option B.** Amend `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` to add: `npm`, `bwrap`, `sandbox-exec`, `jq`. Each addition is justified inline + cross-referenced to this ADR. The `forbidden-patterns` pre-commit hook continues to ban `subprocess.run(..., shell=True)`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, `pickle.loads` repo-wide — this amendment changes the *allowlist*, not the *forbiddenlist*.

The `SubprocessJail` adapters (`BwrapAdapter`, `SandboxExecAdapter`) wrap `bwrap` / `sandbox-exec` via `run_external_cli` — they do NOT bypass the chokepoint.

`java` is **NOT** added in Phase 3 (the `OpenRewriteRecipeEngine` is scaffolded but not invoked by Phase-3 workflows per ADR-0009). Phase 7 amends to add `java` when it enables OpenRewrite for distroless workflows.

## Tradeoffs

| Gain | Cost |
|---|---|
| Single chokepoint preserved — every subprocess goes through `run_external_cli`, even the jail adapters | Four new binaries the Phase-0 `tool_readiness` startup check must verify on every operator/CI machine |
| One ADR captures every Phase-3 amendment — easy diff at Phase-3-arrival time; easy audit at Phase-7-arrival time | ADR maintenance: any future binary addition must amend the allowlist + cross-reference this ADR + a new ADR |
| `npm` is a published binary with reasonable provenance (npm registry, GitHub Releases); jail isolation handles untrusted-script risk per ADR-0006 | `npm` itself has had supply-chain incidents historically; `--ignore-scripts` at both CLI and env (per ADR-0006) mitigates |
| `bwrap` is a well-audited containment primitive; `sandbox-exec` is deprecation-flagged but still functional | macOS migration to Lima/DinD is on Phase 5; Phase 3 carries the deprecation risk explicitly |
| `jq` is an operator-tooling convenience; integration tests use it to inspect JSON streams | One more binary in the allowlist; very small attack surface (`jq` is read-only over stdin) |
| The amendment-only allowlist discipline survives — Phase 3 doesn't open a hole for ad-hoc subprocess use | New plugins must amend the allowlist explicitly + ADR; no silent additions |

## Pattern fit

Implements **Adapter pattern** at the subprocess boundary (toolkit §Behavioral patterns) — `run_external_cli` is the single Adapter wrapping every binary; the allowlist is the closed kernel feature. Composes with **Hexagonal Port** (ADR-0006) — the `SubprocessJail` Adapters use `run_external_cli` internally, never `subprocess.run` directly. Honors **Open/Closed at the kernel boundary** — adding a new binary is an additive ADR, not a kernel rewrite.

## Consequences

- `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` adds 4 entries with one-line per-entry comments referencing this ADR.
- `tests/unit/exec/test_allowlist.py` asserts the exact contents (any drift fails CI).
- Phase 0's `tool_readiness` check extends to verify `npm`, `bwrap` (Linux only), `sandbox-exec` (macOS only), `jq` are on `$PATH`; missing → structured warning at orchestrator init.
- `BwrapAdapter` and `SandboxExecAdapter` (ADR-0006) wrap their respective binaries via `run_external_cli` — no `subprocess.run` direct calls.
- The architecture spec's Goal G6 ("Zero edits to Phase 0/1/2") is explicitly satisfied: the only Phase-0/1/2 edits permitted are extending `ALLOWED_BINARIES` (via this ADR) and adding `import-linter` contracts.
- Phase 7 amends `ALLOWED_BINARIES` with `java` (for `OpenRewriteRecipeEngine` invocation); the precedent established here is the model.
- `forbidden-patterns` hook is unchanged — the forbidden list grows independently of the allowlist.
- New invariant: any new binary requires an ADR + the one-line allowlist amendment + comment cross-reference.

## Reversibility

**High.** Removing a binary from the allowlist is a one-line code change + a fence test update. The forward-direction (adding) and reverse-direction (removing) are equally cheap. The constraint that matters is the social one: don't add a binary without an ADR.

## Evidence / sources

- `../phase-arch-design.md §Goal G6` ("Zero edits to Phase 0/1/2 — the only permitted edits: extending ALLOWED_BINARIES"), §Agentic best practices, §Path to production §Phase 3 ADRs #P3-008
- `../final-design.md §Roadmap coherence check — Phase 0 row (allowlist extension)`, §Synthesis ledger
- [Phase 2 ADR-0001 — subprocess-discipline omnibus (the document this amends)](../../02-context-gather-layers-b-g/ADRs/)
- `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` (the closed frozenset this amendment edits)
