# ADR-0007: `BuildGraphProbe` runs `pnpm list -r --ignore-scripts` with two-stage `resolution_status` output

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** build-graph · supply-chain · facts-not-judgments · postinstall-rce · localv2-conformance · synthesizer-departure
**Related:** [Phase 1 ADR-0011](../../01-context-gather-layer-a-node/ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md), [production ADR-0006](../../../production/adrs/0006-deterministic-gather-no-llm.md), ADR-0003, ADR-0005

## Context

`localv2.md §5.2 B5` requires `BuildGraphProbe` to capture the *resolved* monorepo dependency graph — hoisted deps, workspace overrides, peer-dep resolution — by invoking the package manager. The value over static manifest parsing is precisely the resolved set: a `pnpm` workspace with `--shamefully-hoist` or a `yarn workspaces` config with overrides produces edges that no manifest parser can compute.

The three lenses split on B5 strategy in mutually-exclusive ways (`final-design.md "Conflict-resolution table" D7`):

- **[P] `networkx` from parsed manifests, no subprocess.** Misses resolved hoisting; defensible-but-wrong on non-trivial monorepos. Critic noted: emits a wrong graph as `confidence: medium`.
- **[S] forbid package-manager invocation entirely.** Critic's `§S.1` strongest attack: emits a fabricated graph dressed as evidence (violates `CLAUDE.md` "facts, not judgments"). Direct contradiction of `localv2.md §5.2 B5`.
- **[B] `pnpm list -r` without `--ignore-scripts`.** Captures resolution but runs `postinstall` scripts. Hostile `package.json` with `scripts.postinstall: "curl ... | sh"` is exploited. Critic's `§B-2`.

The synthesis (`final-design.md §3.5 BuildGraphProbe`): run `pnpm list -r --ignore-scripts` (yarn/npm equivalents enforced identically), *and* emit a two-stage output with `resolution_status` so consumers can distinguish declared vs resolved evidence.

## Options considered

- **Static parse only (`networkx`/in-process).** Misses resolved hoisting; produces partial graph dressed as `medium` confidence. The "fabricated graph" pathology.
- **`pnpm list -r` without `--ignore-scripts`.** Captures full resolution; opens postinstall-RCE path on hostile inputs. The CI exit criterion ("real OSS repos in CI") becomes a regular adversarial-input exposure.
- **`pnpm list -r --ignore-scripts` + two-stage output [synth].** Captures resolution where the resolver doesn't depend on postinstall-generated bindings; falls back honestly to static-only where it does. Closes the postinstall-RCE path at the wrapper level. Distinguishes declared vs resolved in the schema.

## Decision

**`BuildGraphProbe` runs two stages in sequence**:

1. **Stage 1 — static parse, always.** `ParsedManifestMemo`-aware reads of `pnpm-workspace.yaml`, `package.json`, `packages/*/package.json`, `apps/*/package.json`, `libs/*/package.json`, `lerna.json`, `nx.json`, `turbo.json`. Produces a *declared* edge set. Cheap; runs even when package managers are absent.

2. **Stage 2 — resolved invocation, conditional.** If a package manager is available *and* the repo is a monorepo (per Phase 1's `LanguageDetectionProbe.monorepo` flag), the wrapper invokes:
   - `pnpm` repos: `pnpm list -r --depth -1 --json --ignore-scripts`
   - `yarn` workspaces repos: `yarn workspaces list --json --no-default-rc` (no `--ignore-scripts` flag needed — `yarn workspaces list` does not run scripts; documented)
   - `npm` workspaces repos: `npm ls --json --workspaces --omit=dev` (npm does not run scripts on `npm ls`; documented)
   - All inside `run_in_sandbox` with `network="none"` (per ADR-0003).

**`--ignore-scripts` is mandatory for `pnpm list`.** Wrapper at `src/codegenie/tools/...` (invoked via the BuildGraph internal helper, not a dedicated tool wrapper since pnpm is shell-invoked via the existing `node` path through `run_in_sandbox`). The wrapper checks the argv contains `--ignore-scripts` before invocation; missing flag raises `BuildGraphProbeMisconfigured` (typed exception). CI fixture `tests/adv/test_buildgraph_postinstall_blocked.py` plants `scripts.postinstall: "touch /tmp/POWNED"` and asserts the file does not exist after the run.

**Output schema's `resolution_status` field is the evidence-vs-judgment seam**:

- `static_only` — Stage 2 didn't run (no package manager available, or not a monorepo, or invocation failed). The output contains *only* the declared edge set; the resolved graph is absent. Consumers reading this know the resolved graph is *unknown*, not *empty*.
- `resolved` — Stage 2 ran cleanly. Declared and resolved edge sets are both emitted. Resolved is the authoritative graph for consumers.
- `resolved_with_discrepancy` — Stage 1 and Stage 2 produced disjoint edges; resolved is authoritative but the discrepancy is recorded as a structured warning for the Planner.

This is the **facts-not-judgments** seam: a consumer reading `resolution_status: static_only` knows the probe couldn't resolve; it does not see a graph dressed as `medium`-confidence resolved evidence. (Closes the critic's `§S.1` "fabricated graph" attack.)

## Tradeoffs

| Gain | Cost |
|---|---|
| Resolved monorepo accuracy where the resolver doesn't depend on postinstall — `localv2.md §5.2 B5` honored | Cost: ~2-5 s of `pnpm list` per gather on a 100-package monorepo; cached on `(pnpm-lock.yaml hash + workspace manifest hash)` |
| Postinstall-RCE path is closed at the wrapper boundary — `--ignore-scripts` mandatory; CI fixture asserts | `--ignore-scripts` means peer-dep resolution that *requires* postinstall-generated bindings is incomplete; reported as `confidence: medium` |
| Two-stage output distinguishes declared from resolved — consumers can reason about evidence quality | Output schema is more complex than a flat graph; sub-schema enumerates three `resolution_status` enum values |
| `resolution_status: static_only` is honest absence, not fabricated presence (closes critic §S.1) | Consumers must check `resolution_status` before treating the graph as authoritative; documentation lives in the sub-schema |
| Yarn and npm equivalents are documented; the discipline scales to whatever package-manager Phase 7's distroless work introduces | The three package managers' command syntaxes differ; the wrapper has three code paths (mitigated by per-pm helpers) |
| Resolved-with-discrepancy as an explicit `resolution_status` value surfaces inconsistencies for Planner inspection | A discrepancy may be expected (e.g., yarn's nohoist); the warning is structured so the Planner can route accordingly |

## Consequences

- `src/codegenie/probes/build_graph.py` ships with the two-stage logic; the `--ignore-scripts` enforcement lives in a tight wrapper helper invoked via `run_in_sandbox`.
- `src/codegenie/schema/probes/build_graph.schema.json` declares `resolution_status` as a closed enum: `["static_only", "resolved", "resolved_with_discrepancy"]`.
- `tests/adv/test_buildgraph_postinstall_blocked.py` plants `scripts.postinstall: "touch /tmp/POWNED"` and asserts the file does not exist after gather; CI-gating.
- `tests/integration/test_buildgraph_static_vs_resolved.py` covers the three `resolution_status` cases: monorepo with pnpm available (resolved), monorepo without pnpm (static_only), monorepo with yarn nohoist (resolved_with_discrepancy).
- The wrapper raises `BuildGraphProbeMisconfigured` if argv-mutation drops `--ignore-scripts`; CI fixture asserts a typed exception.
- Phase 3 (vuln remediation) consumes the resolved graph when `resolution_status == "resolved"`; falls back to manifest-only logic otherwise.
- Phase 7 (distroless) may extend this pattern for build-tool dependency analysis with its own catalog of package-manager invocations — same wrapper discipline.

## Reversibility

**Medium.** Dropping the two-stage output to a flat graph is a schema break (consumers reading `resolution_status` would silently lose the field; needs a major sub-schema bump). Dropping `--ignore-scripts` from the wrapper is a security regression that this ADR explicitly forbids — would require a new ADR to undo. The conservative direction is *additive*: future ADRs may extend `resolution_status` enum (e.g., `resolved_via_lockfile` for a more aggressive resolver), but the existing values are immutable.

## Evidence / sources

- `../final-design.md "Components" §3.5 BuildGraphProbe`
- `../final-design.md "Conflict-resolution table" D7` — the resolution
- `../final-design.md "Departures from all three inputs" #4` — synth call-out
- `../final-design.md "Risks" #1` — `--ignore-scripts` discipline as ongoing convention
- `../phase-arch-design.md "Non-goals" #4, #5` — explicit refusal of [S]'s ban and [B]'s no-`--ignore-scripts`
- `../critique.md "Attacks on the security-first design"` #1 — fabricated-graph attack
- `../critique.md "Attacks on the best-practices design"` "Things this design missed" — `--ignore-scripts` omission
- `localv2.md §5.2 B5` — the contract this honors
- [Phase 1 ADR-0011](../../01-context-gather-layer-a-node/ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md) — the precedent for sanctioned/unsanctioned package-manager invocation
