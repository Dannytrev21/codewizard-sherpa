# ADR-0013: `SCIPIndexProbe` conditionally mounts `node_modules` read-only; never invokes `npm install`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** scip · node-modules · postinstall-rce · evidence-quality · sandbox-policy · synthesizer-departure
**Related:** ADR-0003, ADR-0007, [Phase 1 ADR-0011](../../01-context-gather-layer-a-node/ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md)

## Context

`SCIPIndexProbe` (B1) is the load-bearing Layer B probe — the semantic index it produces is what `TestCoverageMappingProbe`, `NodeReflectionProbe`, and Stage 3 Planning's symbol-resolution all depend on. Coverage quality determines downstream evidence quality.

The three lenses split on `node_modules` policy (`final-design.md "Conflict-resolution table" D3`):

1. **[P]** Wrapper invokes scip-typescript; silent on node_modules (assumed present or not).
2. **[S]** **Never** use `node_modules`; refuse `npm install`; mount nothing. Critic's §S.3 (the strongest single attack on [S]): for the vast majority of cloned-fresh repos and CI fixtures `node_modules` is absent; the probe emits `confidence: medium` (or `low`) on *virtually every real repo*, destroying SCIP coverage and rendering `IndexHealthProbe`'s staleness signal useless because every CI run reports `low` for the wrong reason.
3. **[B]** Mount if present; runs scip-typescript directly via wrapper; silent on the create-vs-honor distinction.

The synthesis (`final-design.md §3.1 SCIPIndexProbe`): mount `node_modules` read-only into the sandbox if present at gather time; never invoke `npm install`; report `confidence: medium` (not `low`) when `node_modules` is absent but lockfiles are resolvable.

The distinction matters: `npm install` is the postinstall-RCE path (the same surface ADR-0007 closes for `BuildGraphProbe`). Honoring a *committed-or-CI-pre-warmed* `node_modules` is evidence; *creating* `node_modules` is supply-chain attack surface.

## Options considered

- **Never use `node_modules`; refuse `npm install` [S].** Strongest supply-chain isolation. Coverage drops on most real OSS repos; `confidence: medium` becomes the dominant outcome; the load-bearing Layer B probe is permanently under-resolved.
- **Wrapper invokes `npm install` inside the sandbox before scip-typescript.** Highest coverage. Opens postinstall-RCE: a hostile `package.json` with a `postinstall: 'curl ... | sh'` runs inside the gather sandbox; `--ignore-scripts` discipline is required everywhere, not just `BuildGraphProbe`; the surface expands. Critic shared concern.
- **Conditional mount: use `node_modules` if present, never invoke `npm install` [synth].** Honors externally-provided coverage; never adds the attack surface; documents `confidence: medium` as the honest evidence when `node_modules` is absent.

## Decision

**`SCIPIndexProbe` uses `node_modules` conditionally and never invokes `npm install`**:

- **Mount policy.** If `node_modules/` exists in the repo at gather time, the probe mounts it **read-only** into the sandbox (`--ro-bind <repo>/node_modules /repo/node_modules`). `scip-typescript` resolves imports against it; coverage is high.
- **No `npm install`.** The probe never invokes the package manager. Honoring an existing tree is evidence; creating one is judgment-as-evidence-plus-attack-surface.
- **Lockfile resolution path.** If `node_modules` is absent, the probe still walks `pnpm-lock.yaml` / `yarn.lock` / `package-lock.json` (via `ParsedManifestMemo`-aware reads from Phase 1) and records `node_modules_present: false, lockfiles_resolved: true, coverage_pct: <reduced>`. Confidence is `medium` (not `low`) because the lockfiles bound the dep graph even without resolution.
- **Confidence ladder.**
  - `high` — `node_modules` present, scip-typescript resolves > 95% of imports.
  - `medium` — `node_modules` absent but lockfiles resolvable; or `node_modules` present but resolution coverage 70–95%.
  - `low` — neither `node_modules` nor parseable lockfiles; or scip-typescript exit-non-zero; or `.scip` re-validation fails.
- **CI pre-warm.** The roadmap exit criterion test (`tests/integration/test_phase2_real_oss.py`) runs `npm ci --ignore-scripts` *outside the gather* (in CI setup) on the `nestjs/nest` checkout *before* invoking `codegenie gather`. The probe sees `node_modules` present, mounts it read-only, scip-typescript resolves at high coverage, B2 reports `scip.confidence: high`. The probe itself stays clean of `npm install`; the CI test setup does the pre-warm under its own sandbox.
- **Phase 14 pre-gather step.** The continuous-gather worker (Phase 14) runs `npm ci --ignore-scripts` as a *pre-gather* step inside its production sandbox. The probe contract stays clean; the orchestration handles the pre-warm.
- **Cache key.** Includes `scip-typescript` digest from `tools/digests.yaml` (ADR-0004), plus the content hashes of `tsconfig*.json`, lockfiles, and the `node_modules` directory's recursive content hash if present. Different `node_modules` contents → different cache key.
- **Output artifact.** `.codegenie/index/scip-index.scip` is a **per-repo binary artifact**, rewritten in place on every cache-miss. Not under `cache/` because its lifecycle is per-repo, not per-gather. `cache gc` extended to manage (LRU on `cache/`; manual `cache prune-index` on `index/`).
- **Re-validation.** Parent process re-validates `.scip` output against the SCIP grammar (protobuf parser is well-fuzzed) before merging; corruption → typed exception → `confidence: low`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Real OSS fixtures with CI-pre-warmed `node_modules` get `confidence: high` SCIP coverage — the seeded-staleness test (ADR-0011) can distinguish *real* staleness from coverage-loss artifacts | Repos without committed or pre-warmed `node_modules` get `confidence: medium`; honest evidence, but downstream consumers must factor it in |
| `npm install` is never invoked from gather — postinstall-RCE surface is closed at the SCIP entry point too, not just BuildGraph (ADR-0007) | A user expecting "just point at this fresh checkout and get high-coverage SCIP" must pre-warm `node_modules` outside the gather; documented in the CLI help and integration test |
| Cache key includes `node_modules` content hash — a `pnpm install` between gathers invalidates the cache correctly | Hashing `node_modules` recursively is non-trivial cost; mitigated by skipping subtrees the lockfile parsers already pin |
| The `confidence: medium` (not `low`) outcome for "no node_modules but lockfiles resolvable" gives the Planner a workable signal — not the worst-case `low` that [S] would emit | Phase 3's vuln-remediation consuming `medium` SCIP may itself need to factor that into its decision graph; documented in Phase 3's design |
| Phase 14's continuous-gather worker can pre-warm in its orchestrator layer — the probe stays clean across Phase 2 → Phase 14 evolution | The orchestration-layer pre-warm is a Phase 14 deliverable; until then, CI tests pre-warm in test setup |
| Read-only mount of `node_modules` keeps the sandbox isolation invariant (no probe-side writes to the tree) | If `node_modules` contains malicious bytes (e.g., a hostile native module's `.so`), scip-typescript loading them is still an attack surface; mitigated by `--network=none` + sandbox env-strip (ADR-0003) |
| `.codegenie/index/scip-index.scip` as a per-repo artifact (not per-gather cache blob) is the right namespace — `cache gc` doesn't accidentally delete a 25 s rebuild | A new on-disk namespace (`.codegenie/index/`) Phase 0's gc didn't know about; the gc is extended to manage it (`cache prune-index` is opt-in manual) |

## Consequences

- `src/codegenie/probes/scip_index.py` ships with conditional mount + lockfile fallback logic.
- `src/codegenie/schema/probes/scip_index.schema.json` declares: `node_modules_present: bool`, `lockfiles_resolved: bool`, `coverage_pct: number`, `confidence: enum(high, medium, low)`.
- `tests/integration/test_phase2_real_oss.py` runs `npm ci --ignore-scripts` in CI setup; asserts probe sees `node_modules`, emits `confidence: high`.
- `tests/integration/test_scip_no_node_modules.py` runs without pre-warm; asserts `confidence: medium`, `node_modules_present: false`, `lockfiles_resolved: true`.
- `tests/adv/test_hostile_tsconfig_extends.py` plants a hostile `tsconfig.json` `extends:` chain trying to read host files; asserts sandbox contains; no host file modified.
- `.codegenie/index/scip-index.scip` lives outside `.codegenie/cache/`; `cache prune-index` (manual) is documented in CLI help.
- Phase 14's pre-gather step in the continuous-gather worker is a named deliverable for Phase 14's design.
- Phase 5's Trust-Aware gates (production ADR series) consume SCIP `confidence` directly; the Planner knows to gate on `medium`.

## Reversibility

**Medium.** Adding `npm install` invocation (the [B-implicit] option) is mechanically additive — wrapper change + `--ignore-scripts` enforcement. Removing the mount entirely (the [S] option) is mechanically subtractive but evidence-destructive: every CI run drops to `medium` or `low` for the wrong reason. The conditional-mount-but-never-create stance is the sweet spot; reversal direction matters a lot — making it more permissive (mount + install) opens RCE; making it more restrictive (never mount) destroys evidence. Future phases should *add* pre-warm mechanisms in orchestration (Phase 14), not move the probe's policy.

## Evidence / sources

- `../final-design.md "Components" §3.1 SCIPIndexProbe`
- `../final-design.md "Conflict-resolution table" D3` — the resolution
- `../final-design.md "Risks" #3` — SCIP coverage on cold OSS fixtures
- `../phase-arch-design.md "Non-goals" #6` — explicit "no `npm install` invocation"
- `../critique.md "Attacks on the security-first design"` #3 — strongest attack on [S] this resolves
- ADR-0003 — the sandbox profile this probe runs under
- ADR-0007 — the parallel `--ignore-scripts` discipline for BuildGraphProbe
- ADR-0011 — the staleness-signal test this enables
- [Phase 1 ADR-0011](../../01-context-gather-layer-a-node/ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md) — the precedent for "no `npm ls` invocation" — this ADR extends the policy to `npm install`
