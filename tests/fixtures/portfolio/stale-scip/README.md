# stale-scip — Phase 2 roadmap exit-criterion fixture

**This fixture is LOAD-BEARING for the Phase 2 roadmap exit criterion.**
Do not delete, do not retarget the seeded `last_indexed_commit` to current
`HEAD`. The fixture and its adversarial test
(`tests/adv/phase02/test_stale_scip_fixture.py`) gate the Phase 2 build —
if `IndexHealthProbe` (B2) ever regresses and silently treats moved-HEAD
as `Fresh`, the build fails. That is the operational meaning of "honest
confidence" (`docs/production/design.md §2.3`).

## Regeneration

Run `./regenerate.sh` from this directory. The script:

1. Removes `.git/` and `.codegenie/`.
2. Initializes `.git/` (branch `main`) with two commits:
   - **v0** — adds `package.json`. **`last_indexed_commit` points here** (the parent).
   - **v1** — adds `main.ts`. HEAD lands here.
3. Materializes `.codegenie/context/raw/scip.json` by substituting
   `PARENT_COMMIT` in `_seed/scip-slice.template.json`.
4. Copies the empty placeholder `_seed/scip-index.scip.placeholder` to
   `.codegenie/context/raw/scip-index.scip`.
5. Refuses to set `last_indexed_commit == HEAD` (guard error → exit 1).

`HEAD` is genuinely ahead by ≥ 1 by construction.

Both `.git/` and `.codegenie/` are gitignored (fixture-local `.gitignore`
plus the repo-wide `.gitignore`). The reviewable contract surface is
`_seed/scip-slice.template.json`, `regenerate.sh`, and this README — every
assertion the adversarial test makes traces back to one of these three.

## Structural assertion

The adversarial test asserts the typed outcome of `IndexHealthProbe`:

- `slice["index_health"].keys() == {"scip"}` (outer-key invariant).
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

## Tool-version bumps

If you bump `scip-typescript`'s version (S4-03 / S7-02), regenerate; the
structural assertion survives any version bump.

## Future materialization (S7-02)

Full fixture materialization (real `scip-typescript` invocation against a
prior commit, replacing the placeholder `.scip` blob with a real binary)
lands in S7-02. This stub is enough for S4-02's adversarial assertion.
