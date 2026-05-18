# ADR-0015: `typecheck.typescript` `SignalKind` lands; `./node_modules/.bin/tsc` added to `ALLOWED_BINARIES`

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** registry-pattern · open-closed · trust-signal · subprocess-allowlist · adr-0037
**Related:** [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) · Phase 3 ADR-0012 (production) · [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

[Production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) defines the layered-analysis funnel: SCIP for gather, type-checkers for verification, LSP reserved for interactive loops (Phase 15+). Phase 4 is the first phase that ships a verification-tier type-checker — `tsc --noEmit` for TypeScript. The signal kind name is `typecheck.typescript`; it registers against Phase 3's open `@register_signal_kind` registry.

The Phase 3 `SubprocessJail` ships an `ALLOWED_BINARIES` allowlist (a closed frozenset; admission requires an ADR amendment per Phase 3 ADR-0012's pattern). `tsc` is not yet on the allowlist. Phase 4 needs to amend.

Phase 4 must also make the signal's strict-AND folding behavior explicit: the signal must fail *before* `npm test` runs when the LLM produces source that doesn't type-check (otherwise tests pass against stale dist or whatever and the LLM gets credit for a broken patch).

Phase 7's distroless plugin may *not* run `tsc` (no Node toolchain in distroless context). The signal must be plugin-local so Phase 7 can opt out by simply not registering it.

## Options considered

- **Hardcoded type-check call in Phase 5 strict-AND** (alternative). Adds a `tsc` invocation directly into `TrustScorer.score`. **Pattern:** Central dispatch. Modification of Phase 5 code; Phase 7 distroless plugin would have to suppress it; violates extension-by-addition.
- **Plugin-local signal registered via `@register_signal_kind("typecheck.typescript")`** (synthesis). The signal lives in `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`; Phase 3's open registry collects it at import time; strict-AND fold inherits. **Pattern:** Registry pattern + Open/Closed extension.
- **External LSP server** (`tsserver`). Richer signals; persistent process; coordination cost. **Pattern:** LSP-as-runtime. Rejected per [ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) — LSP is Phase 15+ interactive-loop territory.
- **No type-check signal in Phase 4** (alternative). Trust `npm test` to catch type errors via test failures. **Pattern:** Implicit-via-tests. Type errors that don't manifest as test failures (signature drift, unused-but-broken imports) slip through.

## Decision

`@register_signal_kind("typecheck.typescript")` ships in `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`. The signal runs `tsc --noEmit --pretty false` inside Phase 3's `SubprocessJail` (30 s cap); strict-AND with baseline (cached at `.codegenie/typecheck/baseline-<repo-sha>.json`) passes iff `new_errors_after <= new_errors_before`. **Phase-4 ADR amendment** to Phase 3's `ALLOWED_BINARIES`: add `./node_modules/.bin/tsc` (content-hashed per major Node version) following the [Phase 3 ADR-0012](#) pattern. The signal is **plugin-local**; Phase 7's distroless plugin won't register it. Phase 7's Node-touching plugin can re-register via a shared `vulnerability-remediation--node--*` base plugin per [ADR-0031](../../../production/adrs/0031-plugin-architecture.md)'s wildcard convention (deferred — not Phase 4's call).

**Pattern:** Registry pattern + Open/Closed (Phase 3 shipped the seam; Phase 4 adds one row).

## Tradeoffs

| Gain | Cost |
|---|---|
| First `typecheck.<lang>` signal lands per [ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md); the layered-analysis funnel's verification tier is real | `tsc` is admitted to `ALLOWED_BINARIES` — supply-chain surface grows; content-hashed path mitigates substitution attacks |
| LLM-produced source that doesn't type-check fails strict-AND *before* `npm test` runs — caught at the right tier | `tsc --noEmit` adds 3–8 s p50 to validation (capped at 30 s); contributes to time-to-PR p50 envelope but is bounded |
| Signal is plugin-local — Phase 7's distroless plugin opts out by not registering; no Phase-4 code changes for Phase 7 | A shared `vulnerability-remediation--node--*` base plugin (per [ADR-0031](../../../production/adrs/0031-plugin-architecture.md) wildcard) is a Phase-6.5 or Phase-7 decision; until then the registration is per-plugin |
| Strict-AND fold with baseline ("new_errors_after ≤ new_errors_before") avoids being broken by pre-existing repo-level type errors — the LLM only needs to not introduce new ones | Baseline cached at `.codegenie/typecheck/baseline-<repo-sha>.json`; stale baselines on aggressive rebases are a known operational corner case (recovery: delete + re-run) |
| `tsc --noEmit` is the de-facto TypeScript verification command; widely understood by contributors | Missing `tsc` (no tsconfig, no node_modules install) returns `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"}, confidence="medium")` — degraded-signal path; doesn't halt validation |
| Phase 6.5 inherits the signal for bench-replay correctness checks | `tsc` upgrade in a repo's `node_modules` may change error shapes; baseline-keyed-on-repo-sha mitigates but doesn't eliminate |

## Pattern fit

The toolkit's **Registry pattern** is the textbook fit. Phase 3 shipped the seam (`@register_signal_kind` decorator + signal-kind dict). Phase 4 adds one row by writing one module that imports + registers. **Open/Closed:** zero edits to Phase 3 code, zero edits to `TrustScorer`, zero edits to `SubprocessJail` ABC — only one ADR amendment to `ALLOWED_BINARIES`.

The signal's location in the *plugin* (not in `src/codegenie/`) is per [ADR-0031](../../../production/adrs/0031-plugin-architecture.md): organizational uniqueness as data, not core code. Phase 7's distroless plugin is a different plugin; it does its own signal registration (or not).

## Consequences

- `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` ships with the signal.
- `ALLOWED_BINARIES` (in `src/codegenie/exec/`) is amended to include `./node_modules/.bin/tsc` (content-hashed per major Node version per Phase 3 ADR-0012's amendment pattern).
- `.codegenie/typecheck/baseline-<repo-sha>.json` is the per-repo type-error baseline; bumped on legitimate type-error introductions reviewed by humans.
- Strict-AND fold: `TrustOutcome.passed` requires all signals to pass; `typecheck.typescript` participates from Phase 4 onward.
- Phase 5's `GateRunner` reads the signal kind from the registry; no Phase 5 code change.
- The integration test `tests/integration/test_typecheck_signal_catches_signature_drift.py` deliberately uses a bad LLM cassette response with a hallucinated method call; `tsc` catches it; gate fails before `npm test` runs (event ordering in stream).
- Phase 7's distroless container migration plugin doesn't register `typecheck.typescript` — its strict-AND fold simply lacks that signal kind.
- Phase 15 (LSP / agentic recipe authoring) is the home for richer interactive type signals — out of scope for Phase 4.
- The `tests/fence/test_typecheck_signal_registered.py` fence test asserts `SignalKind("typecheck.typescript")` is in the registry at import time.

## Reversibility

**Low.** Removing the signal is plugin-level (delete the module + import row); operationally easy but loses LLM-output verification at the right tier. Reverting the `ALLOWED_BINARIES` amendment would block `tsc` invocations system-wide and disable the signal automatically. Promoting the signal to a shared `vulnerability-remediation--node--*` base plugin is a Phase-6.5/Phase-7 ADR — additive, deferred.

## Evidence / sources

- `../final-design.md §Component 12 — TypecheckTypescriptSignal`
- `../final-design.md §Goal "typecheck.typescript SignalKind lands"`
- `../phase-arch-design.md §Component 11 — TypecheckTypescriptSignal`
- `../phase-arch-design.md §Goals — G10`
- [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) (layered analysis funnel; first `typecheck.<lang>` lands here)
- [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) (plugin wildcard convention for shared signals)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (objective signals only)
- Phase 3 ADR-0012 pattern (ALLOWED_BINARIES amendment via ADR)
