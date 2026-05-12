# ADR-0014: Add `npm`, `ncu`, and `java` (opt-in) to `ALLOWED_BINARIES`; extend `tools/digests.yaml` for each

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** allowlist · tool-use · supply-chain · phase-3-tools · synthesizer-mechanical
**Related:** [Phase 2 ADR-0005](../../02-context-gather-layers-b-g/ADRs/0005-allowed-binaries-additions.md), [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-tools-digests-yaml-pin-manifest.md), ADR-0003, ADR-0011

## Context

Phase 2 ADR-0005 added six binaries to `ALLOWED_BINARIES` (`scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`), each as a separate ADR-justified line under the Phase-1 per-binary-named precedent. Phase 3 introduces three new external CLIs:

1. **`npm`** — used by `LockfileResolver` (`npm install --package-lock-only`), the install validator (`npm ci`), and the test validator (`npm test`). Required for every Phase 3 run.
2. **`ncu`** (`npm-check-updates`) — used by `NcuRecipeEngine.apply()` (ADR-0003). Required for every `--engine=ncu` run (the default).
3. **`java`** — used by `OpenRewriteEngineStub.apply()` (ADR-0003). Required only when `--engine=openrewrite`; **opt-in**.

Each must be added to `ALLOWED_BINARIES` (the wrapper-level guard `run_in_sandbox` checks) and to `tools/digests.yaml` (Phase 2 ADR-0004 pin manifest). The synthesizer flagged this as ADR-P3-009 (`final-design.md §"Roadmap coherence check" §"New ADRs implied"`).

## Options considered

- **Add all three as a single bundled allowlist entry.** Loses per-binary justification; Phase 2 ADR-0005's per-binary precedent.
- **Add `npm` and `ncu` only; defer `java` to a future ADR.** Forces Phase 3 to ship without OpenRewrite stub coverage — violates ADR-0003.
- **Add all three as a single ADR with sub-sections per binary, mirroring Phase 2 ADR-0005 [synth].** Same per-binary discipline; `java` flagged as opt-in to acknowledge its conditional use.

## Decision

**`ALLOWED_BINARIES` (Phase 2 ADR-0005) extends with three new entries; `tools/digests.yaml` extends with three new pinned digests.**

### `npm`

- **Purpose:** Lockfile resolution, install validation, test execution.
- **Pin granularity:** **Minor** digest in `tools/digests.yaml` (ADR-0011's open-question resolution — patch is too churny; major loses too much determinism).
- **Sandbox profile (`run_in_sandbox`):** Mandatory `--ignore-scripts` on every install/`ci`; OFF only inside the test-execution overlay (ADR-0005). `--no-audit --no-fund` for non-deterministic-output suppression (ADR-0011).
- **Tool-readiness check:** at CLI startup (per `roadmap.md §"Phase 3"` tooling), the tool readiness probe asserts `npm` on PATH and digest matches `tools/digests.yaml`.
- **Test:** `tests/integration/test_npm_pin_enforcement.py` asserts the readiness check fails on digest mismatch.

### `ncu` (`npm-check-updates`)

- **Purpose:** `NcuRecipeEngine.apply()` invocation per ADR-0003.
- **Pin granularity:** **Patch** digest in `tools/digests.yaml` (`ncu`'s JSON output format has had breaking changes between minor versions — `critique.md §"Attacks on best-practices" §"Hidden assumptions" #3` — patch pinning is the safe choice).
- **Sandbox profile:** `run_in_sandbox(network="none", test_execution=False)` — `ncu` operates on `package.json` only; needs no network.
- **Tool-readiness check:** at CLI startup, asserts `ncu` on PATH and digest matches.
- **Test:** `tests/integration/test_ncu_pin_enforcement.py` and `tests/unit/test_ncu_json_output_schema.py` (asserts the engine handles the pinned `ncu` version's output schema).

### `java` (opt-in)

- **Purpose:** `OpenRewriteEngineStub.apply()` invocation per ADR-0003.
- **Pin granularity:** Major digest in `tools/digests.yaml` (Java 17 LTS or Java 21 LTS — selected per implementer judgment).
- **Opt-in:** Only required when `--engine=openrewrite` is passed. If absent on PATH:
  - Selector emits `RecipeSelection(reason="no_engine")` per ADR-0004.
  - `OpenRewriteEngineStub.available()` returns `False`.
  - The orchestrator does **not** fail; exits cleanly via the `reason="no_engine"` path (ADR-0004, ADR-0006).
- **Sandbox profile:** `run_in_sandbox(network="none", test_execution=False)`; JVM heap pinned at `-Xmx2g` and wall-clock at 300 s per `final-design.md §"Open questions"` #5.
- **Tool-readiness check:** at CLI startup, asserts `java` only if `--engine=openrewrite`; otherwise the check is skipped.
- **OpenRewrite jar pin:** the pinned `tools/openrewrite/<digest>.jar` is a separate `tools/digests.yaml` entry per Phase 2 ADR-0004 precedent.
- **Test:** `tests/integration/test_openrewrite_stub_skipped_without_java.py` asserts the selector emits `no_engine` when `java` is absent and the run exits 4.

### Shared discipline (per Phase 2 ADR-0005)

- Each binary has a per-tool wrapper under `src/codegenie/tools/{npm.py, ncu.py, java.py}` that calls `run_in_sandbox` with the right profile.
- The wrapper's CI test asserts the binary is invoked through the sandbox chokepoint (no direct subprocess calls).
- `localv2.md §6` "Required external tools at runtime" is the operator-facing list; this ADR is the architectural justification.

## Tradeoffs

| Gain | Cost |
|---|---|
| Same per-binary discipline as Phase 2 ADR-0005 — every external CLI has a digest, a wrapper, a readiness check, and a CI test | Three new wrappers; three new readiness checks; three new digest entries to maintain |
| `java` as opt-in honors ADR-0003's "OpenRewrite stub is a contract anchor, not a feature" — developer laptops without JVM aren't blocked | The opt-in path is a code branch that must be tested explicitly; CI matrix includes a `no-java` profile |
| Minor-pin for `npm` matches ADR-0011's cache-key discipline — patch bumps don't stampede portfolio | npm minor bumps invalidate the lockfile-resolver cache portfolio-wide; pre-warmed on the bump PR |
| Patch-pin for `ncu` is the right granularity given `ncu`'s history of breaking JSON-output changes between minor versions (critic hidden assumption #3) | Every `ncu` patch release triggers a digest manifest update; routine sprint work |
| `tests/integration/test_*_pin_enforcement.py` per binary is the single failure-loud mechanism; digest drift breaks CI before it breaks production | Three new tests; immaterial maintenance cost |
| Phase 0's fence CI is unchanged — the new tools don't introduce LLM SDKs | The fence covers code packages, not binary invocations; the sandbox chokepoint is the binary-side defense |

## Consequences

- `src/codegenie/exec/allowed_binaries.py` (or equivalent) extends with `npm`, `ncu`, `java`.
- `tools/digests.yaml` extends with `npm` (minor), `ncu` (patch), `java` (major), and `openrewrite/<jar-name>.jar`.
- `src/codegenie/tools/npm.py`, `ncu.py`, `java.py` ship as per-tool wrappers calling `run_in_sandbox`.
- CLI tool-readiness check (`codegenie remediate` startup) asserts `git`, `npm`, `ncu` present; `java` asserted only when `--engine=openrewrite`.
- Failure mode on missing tool: `ToolReadinessError` with a clear install message per `localv2.md §6` precedent.
- Integration tests assert per-binary pin enforcement and the opt-in skip-cleanly behavior for `java`.
- Phase 7 (Chainguard distroless) may add `chainctl`, `cosign`, or related tools — each its own future ADR.
- The OpenRewrite jar digest pin is a separate `tools/digests.yaml` entry; updates flow through the same review discipline as Phase 2 ADR-0004.

## Reversibility

**High.** Removing one of the three binaries from `ALLOWED_BINARIES` is mechanically additive in the reverse direction — but if `npm` is removed, Phase 3 cannot run (`npm` is the lockfile resolver primitive); if `ncu` is removed, the default engine breaks; if `java` is removed, the OpenRewrite stub becomes unreachable. Pin granularity changes (e.g., promoting `ncu` from patch to minor) are low cost in code but operationally meaningful — wider pin invites more drift. The Phase 2 ADR-0005 precedent governs the per-binary-justification discipline; reversing it (bundling future binaries into one entry) would surface as a contradiction.

## Evidence / sources

- `../final-design.md §"Resource & cost profile"` — `ALLOWED_BINARIES` additions
- `../final-design.md §"Roadmap coherence check" §"New ADRs implied"` ADR-P3-009
- `../phase-arch-design.md §"Component design" #4 "NpmPackageUpgradeTransform"`
- `../phase-arch-design.md §"Component design" #2 "RecipeEngine ABC + two implementations"`
- `../phase-arch-design.md §"Architectural context"` — tool readiness check
- `../critique.md §"Attacks on best-practices" §"Hidden assumptions" #3` — `ncu` version variability
- [Phase 2 ADR-0005](../../02-context-gather-layers-b-g/ADRs/0005-allowed-binaries-additions.md) — per-binary precedent
- [Phase 2 ADR-0004](../../02-context-gather-layers-b-g/ADRs/0004-tools-digests-yaml-pin-manifest.md) — pin manifest
- `docs/localv2.md §6` — required external tools at runtime
