# stale-scip — Phase 2 roadmap exit-criterion fixture

**This fixture is LOAD-BEARING for the Phase 2 roadmap exit criterion.**
Do not delete, do not retarget the seeded `last_indexed_commit` to current
`HEAD`. The fixture and its adversarial test
(`tests/adv/phase02/test_stale_scip_fixture.py`) gate the Phase 2 build —
if `IndexHealthProbe` (B2) ever regresses and silently treats moved-HEAD
as `Fresh`, the build fails. That is the operational meaning of "honest
confidence" (`docs/production/design.md §2.3`).

The fixture is fully materialized (S7-02): the v0 tree contains the full
TypeScript source (`package.json`, `tsconfig.json`, `main.ts`, and
`src/a.ts` through `src/e.ts` — 6 `.ts` files); `_seed/scip-index.scip`
is a **real binary SCIP index** built OUT-OF-BAND by
`scip-typescript` against that v0 tree; `CHANGELOG.md` is committed
at v1 so HEAD diverges from `last_indexed_commit` without mutating
the indexed source tree.

## Regeneration

Run `./regenerate.sh` from this directory. The script:

1. Removes `.git/` and `.codegenie/`.
2. Initializes `.git/` (branch `main`) with two commits:
   - **v0** — adds the full TypeScript source tree (`package.json` +
     `tsconfig.json` + `main.ts` + `src/a.ts` through `src/e.ts`).
     **`last_indexed_commit` points here** (the parent). The
     `_seed/scip-index.scip` blob was indexed against this tree.
   - **v1** — adds `CHANGELOG.md`. HEAD lands here. The indexed source
     tree is unchanged at v1, so the seed template's
     `files_indexed == files_in_repo` invariant holds.
3. Materializes `.codegenie/context/raw/scip.json` by substituting
   `PARENT_COMMIT` in `_seed/scip-slice.template.json`.
4. Copies `_seed/scip-index.scip` to `.codegenie/context/raw/scip-index.scip`.
5. Refuses to set `last_indexed_commit == HEAD` (guard error → exit 1).

`HEAD` is genuinely ahead by ≥ 1 by construction.

Both `.git/` and `.codegenie/` are gitignored (fixture-local `.gitignore`
plus the repo-wide `.gitignore`). The reviewable contract surface is
`_seed/scip-slice.template.json`, `_seed/scip-index.scip`,
`regenerate.sh`, the committed source tree, and this README — every
assertion the adversarial test makes traces back to one of these.

## Seed-build ritual (one-time per `scip-typescript` version bump)

The committed `_seed/scip-index.scip` binary is produced
**OUT-OF-BAND** on the contributor's local box. `scip-typescript` is
in `ALLOWED_BINARIES`, but the regen script does NOT invoke it (per
ADR-0001 — only `mkdir`, `cp`, `sed`, `git`, `rm`, `echo` are invoked
at regen time). When the production `scip-typescript` version changes
(S4-03 records the production pin), or when the v0 source tree
changes, rebuild the seed binary as follows:

1. Create a scratch directory exactly mirroring the v0 tree:
   ```
   mkdir -p /tmp/scip-seed-scratch/src
   cp tests/fixtures/portfolio/stale-scip/package.json /tmp/scip-seed-scratch/
   cp tests/fixtures/portfolio/stale-scip/tsconfig.json /tmp/scip-seed-scratch/
   cp tests/fixtures/portfolio/stale-scip/main.ts /tmp/scip-seed-scratch/
   cp tests/fixtures/portfolio/stale-scip/src/*.ts /tmp/scip-seed-scratch/src/
   ```
2. Install the pinned TypeScript locally so `scip-typescript` resolves
   its compiler:
   ```
   cd /tmp/scip-seed-scratch && npm install typescript@5.3.0 --no-package-lock
   ```
3. Run `scip-typescript`:
   ```
   scip-typescript index
   ```
4. Copy the resulting `index.scip` over:
   ```
   cp /tmp/scip-seed-scratch/index.scip tests/fixtures/portfolio/stale-scip/_seed/scip-index.scip
   ```
5. Commit the new seed binary; bump the version-pin entry below.

## Pinned `scip-typescript` version

`_seed/scip-index.scip` was last built with scip-typescript v0.4.0.
The structural assertion (`CommitsBehind.n >= 1` AND
`last_indexed != current_HEAD`) is tool-version-agnostic and survives
any `scip-typescript` version bump; the binary's exact bytes do not.

## Tracked files + probe consumers

| Path | Probe consumers |
|---|---|
| `package.json` | `node_build_system`, `node_manifest` |
| `tsconfig.json` | `node_build_system` |
| `main.ts` | `language_detection` |
| `src/a.ts`, `src/b.ts`, `src/c.ts`, `src/d.ts`, `src/e.ts` | `language_detection` |
| `_seed/scip-slice.template.json` | `scip_index`, `index_health` (substituted into the runtime `.codegenie/context/raw/scip.json`) |
| `_seed/scip-index.scip` | `scip_index` (forward-looking; copied to `.codegenie/context/raw/scip-index.scip` at regen time) |
| `regenerate.sh` | — (review-as-code; not consumed by a probe) |
| `CHANGELOG.md` | — (the v1 sentinel; not consumed by a probe) |
| `.gitignore`, `.gitattributes` | — (fixture-local meta) |

## How to add a new commit (and the SCIP-vs-HEAD invariant that survives)

If the fixture needs additional commits beyond v0/v1 (e.g., a v2 for
some future adversarial), append them at HEAD inside `regenerate.sh`
AFTER the v1 commit; never insert between v0 and v1. The invariant
that must always hold: `last_indexed_commit` == the v0 SHA captured
by `PARENT_COMMIT=$(git rev-parse HEAD)` immediately after `v0 — ...`
is committed. Adding commits AFTER v1 only widens
`CommitsBehind.n`; it never flips it to zero.

## Structural assertion

The adversarial test asserts the typed outcome of `IndexHealthProbe`:

- `slice["index_health"].keys()` is the live freshness-registry key
  set (currently `{"scip", "runtime_trace", "semgrep", "gitleaks", "conventions"}`;
  widens as more probes register via `register_index_freshness_check`).
- `freshness` is `Stale`, reason `CommitsBehind`.
- `CommitsBehind.n >= 1` **AND** `CommitsBehind.last_indexed != current_HEAD`.
- `slice["index_health"]["scip"]["confidence"] == "medium"` (S4-01 AC-9
  `Stale(CommitsBehind(...))` demote-min mapping).

Both inequalities matter: S4-01 AC-6 has a fallback path where `n` falls
back to `1` if `git rev-list --count <last>..<head>` fails. A test
asserting only `n >= 1` would pass even if the fallback fired in a
degenerate `last_indexed == HEAD` state (a B2 bug). Asserting
`last_indexed != current_HEAD` independently anchors the structural fact
that the two commits are genuinely different — the definition of "stale."

Both assertions are tool-version-agnostic. Do not assert on a specific
`n` value.

## Sibling slice path

`scip.json` lives at `.codegenie/context/raw/scip.json` (keyed by
`IndexName('scip')` stem per S4-01's hardened `read_raw_slices` contract).
This is the contract surface S4-03's `ScipIndexProbe` must honor when it
ships; this fixture provides the substitute until S4-03 lands.

## Phase-3+ handoff (forward-looking)

The real binary `_seed/scip-index.scip` is **forward-looking**: the
current S4-02 adversarial reads `.codegenie/context/raw/scip.json`
(materialized from `_seed/scip-slice.template.json` with the
`PARENT_COMMIT` substitution), not the binary blob. The binary is the
contract surface S4-03's `ScipIndexProbe` consumer (and any
Phase-3+ adapter) will read when it ships. Future maintainers: do not
conclude "the placeholder is fine because the adversarial passes
against it" — the binary is load-bearing for the next-phase consumer
even though it is not load-bearing for today's adversarial.
