# ADR-0001: Add `node` to `exec.ALLOWED_BINARIES` for the `--version` cross-check

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** tool-use · security · allowlist · localv2-conformance
**Related:** [Phase 0 ADR-0012](../../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

`localv2.md §5.1 A2` specifies that `NodeBuildSystemProbe` records **both** the declared Node version constraint (from `package.json#engines.node`, `.nvmrc`, etc.) **and** the locally-resolved Node version (from `node --version`). Phase 0 ADR-0012 made `codegenie/exec.py` the single subprocess chokepoint via an `ALLOWED_BINARIES` set whose only Phase 0 entry is `"git"`; any binary not in the set raises before exec. Adding a binary is the documented extension seam and requires a Phase 1 ADR.

The security lens vetoed the `node --version` invocation entirely (`design-security.md` §"NodeBuildSystemProbe" — "**Does not call `node --version`** … despite `localv2.md` mentioning it"). The threat: a hostile `node` shim on `$PATH` runs in the gather process's context and can write side-effect files, exfiltrate env vars, or starve the timeout. The best-practices lens and `localv2.md §5.1 A2` both require the cross-check. The critic (`critique.md §"Attacks on the security-first design"` #6) framed this as a Rule 11 conformance violation in lens form and demanded explicit resolution.

`final-design.md` "Conflict-resolution table" row 2 resolves the conflict in favor of the cross-check, with mitigations.

## Options considered

- **Veto the invocation entirely (security lens).** Skip `node --version`; rely on declared constraint only. Avoids the `$PATH` shim attack surface. Violates `localv2.md §5.1 A2` and Phase 0 §2.3's "`localv2.md` is the source of truth" rule.
- **Invoke unconditionally with no mitigations (naive best-practices).** Trust `$PATH`. Conforms to `localv2.md` but accepts the full shim risk.
- **Add `"node"` to `ALLOWED_BINARIES`, invoke via `exec.run_allowlisted` (env-stripped, 5 s timeout, `shell=False`), parse output as a display field only.** Conforms to `localv2.md`; the existing Phase 0 chokepoint carries the load-bearing mitigations.

## Decision

**Add `"node"` to `exec.ALLOWED_BINARIES`.** `NodeBuildSystemProbe` calls `exec.run_allowlisted(["node", "--version"], cwd=repo_root, timeout_s=5)` on the cross-check path. The optional invocation is **on by default**; absence of `node` on `$PATH` is logged at WARN and degrades to `node_version_resolved_locally: null` with `confidence` unaffected — the declared constraint is the load-bearing fact.

Output is parsed only against `^v\d+\.\d+\.\d+`; the value is recorded as a **display field** (`node_version_resolved_locally: str | null`) and never used as a control-flow input or as code.

## Tradeoffs

| Gain | Cost |
|---|---|
| `localv2.md §5.1 A2` conformance — the cross-check ships as specified | One new external-process surface in Phase 1; `ALLOWED_BINARIES` grows from 1 to 2 |
| Reuses Phase 0's `run_allowlisted` env-strip, `shutil.which` resolution, `shell=False`, 5 s timeout — all chokepoint behaviors already audited | A hostile `node` shim on `$PATH` can still run with stripped env and write side-effects within the timeout; this is documented residual risk #3 in `final-design.md` |
| Output regex `^v\d+\.\d+\.\d+` rejects garbage (Edge case #6) — `node_version_resolved_locally: null` on parse failure | Garbage-output path is one more confidence-downgrade trigger; tested in `tests/adv/test_planted_node_on_path_ignored.py` |
| Phase 14's production worker (rlimits + bwrap) closes the residual at the deployment layer | Phase 1's adversarial fixture for `$PATH` shim cannot test bwrap (no bwrap in Phase 1) — limited to env-strip assertion |
| The decision is ADR-gated; future `ALLOWED_BINARIES` entries follow the same workflow (Phase 0 §12) | Each new binary requires a phase-level ADR even if obviously benign |

## Consequences

- `src/codegenie/exec.py` gains a one-line addition: `"node"` in `ALLOWED_BINARIES`. The signature, env-strip, timeout enforcement, and `shutil.which` resolution are unchanged.
- Tool-readiness check (Phase 0 CLI startup) now probes for both `git` (required) and `node` (optional); missing `node` does not block gather, only degrades the slice.
- The `fence` CI job continues to assert no LLM SDK is in the dep closure; `node` is a runtime binary, not a Python dep.
- The `references_secrets` and audit fields never include the `node` invocation's stdout — it's a version string only.
- Future phases adding probes that need an interpreter (`python --version`, `go version`) follow this same ADR workflow.
- `tests/adv/test_planted_node_on_path_ignored.py` is the load-bearing regression: a sentinel `node` shim runs in the stripped env; the test asserts no secret env var leaks.

## Reversibility

**Medium.** Removing `"node"` from `ALLOWED_BINARIES` is a one-line code change plus deleting the cross-check branch in `NodeBuildSystemProbe`. Mechanically cheap. The political cost is moderate: it reverses `localv2.md §5.1 A2` conformance and would need to be re-litigated against the synthesis ledger. Existing `repo-context.yaml` artifacts with `node_version_resolved_locally` populated do not become invalid (the field is `nullable`), so consumers continue to function.

## Evidence / sources

- `../final-design.md "Conflict-resolution table" row 2` — the resolution itself
- `../final-design.md "Components" #3 NodeBuildSystemProbe` — invocation specifics
- `../final-design.md "Risks" #3` — residual `$PATH` shim risk documented
- `../phase-arch-design.md "Component design" #2` — invocation rules
- `../phase-arch-design.md "Edge cases" row 6` — garbage-output path
- `../critique.md` "Attacks on the security-first design" #6 — the conformance violation
- `../../../localv2.md §5.1 A2` — the contract
- [Phase 0 ADR-0012](../../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md) — the extension seam
