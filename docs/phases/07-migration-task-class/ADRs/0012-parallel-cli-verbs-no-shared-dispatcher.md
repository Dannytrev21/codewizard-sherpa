# ADR-0012: `codegenie migrate` ships as a parallel CLI verb — no shared dispatcher; Phase 8 unifies

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cli · dispatcher · phase8-integration · extension-by-addition
**Related:** [ADR-0011](0011-distroless-ledger-parallel-to-vuln-ledger.md), Phase 6 [ADR-0009](../../06-sherpa-state-machine/ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md)

## Context

Phase 6 shipped `cli/loop.py` (`codegenie loop run/resume/inspect/replay/render`) and explicitly *did not* edit `cli/remediate.py` (Phase 6 exit criterion #14). Phase 7 needs an operator entry point for distroless migration. The three lens designs took three positions on dispatch (`critique.md §performance.5`, `final-design.md §Conflict-resolution row 16`):

- `[P]` proposed `cli/sherpa.py` with a parallel `run/resume/inspect/replay` subcommand surface — claiming this was the Phase 6 named home. The critic landed: operators would have two CLI commands doing identical things on different ledger types; `codegenie sherpa resume` can't operate on a vuln workflow, and vice versa; Phase 8 inherits *two* CLI surfaces to merge.
- `[S]` proposed `codegenie` with a `--task distroless` flag — unspecified about the dispatch internals.
- `[B]` proposed a new `codegenie migrate` verb in `cli/migrate.py` — parallel to `codegenie loop`, no shared dispatcher in Phase 7, Phase 8's supervisor takes the dispatch surface when it lands.

Phase 6's exit criterion #14 forbids editing `cli/loop.py`. Phase 7 cannot extend `loop` to dispatch distroless workflows; it must ship a sibling. The synthesizer picked `[B]` (`final-design.md §Conflict-resolution row 16`).

## Options considered

- **Edit `cli/loop.py` to add a `--task` flag (`[S]`).** Phase 6 exit criterion #14 violation. Rejected.
- **Coin `cli/sherpa.py` now with `run/resume/inspect/replay` parallel to `loop` (`[P]`).** Phase 8's supervisor is *supposed to be* `codegenie sherpa`; coining the verb before Phase 8 means Phase 8 inherits the fork instead of designing it.
- **New `codegenie migrate` verb in `cli/migrate.py` (synthesizer's pick).** Parallel to `codegenie loop`; same factory pattern (`build_distroless_loop()` vs `build_vuln_loop()`); no shared dispatcher; Phase 8 unifies behind a supervisor verb (likely `codegenie sherpa`).

## Decision

`src/codegenie/cli/migrate.py` ships as a new file exposing `codegenie migrate <repo> --target distroless [--cve <id>] [--max-attempts N] [--dry-run]` plus `resume / inspect / replay / render` subcommands mirroring `cli/loop.py`'s surface. **`cli/loop.py` is not modified** (Phase 6 exit criterion #14 preserved). **`cli/sherpa.py` is not coined** — Phase 8's supervisor will own it. Shared options (workflow_id derivation, advisory loading) are *inlined* in `cli/migrate.py` rather than extracted to a `common.py` (per `final-design.md §Architecture B-shape Open Q #5`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 6 exit criterion #14 preserved verbatim — `cli/loop.py` is byte-identical pre- and post-Phase 7 | Operators see two CLI verbs (`loop` for vuln, `migrate` for distroless) and must learn which to use; README must document the split |
| Phase 8's supervisor designs its own dispatch surface without inheriting a `cli/sherpa.py` shape from Phase 7 — supervisor is the *future* unifier, free to choose its own subcommand vocabulary | `cli/migrate.py` and `cli/loop.py` share workflow_id derivation + advisory loading + audit-chain seeding — duplicated code (~50 LOC each, repeated); accepted in Phase 7, refactor candidate in Phase 8 |
| The parallel-verb pattern is consistent — each `build_*_loop()` factory gets one CLI verb; Phase 8 will see three verbs (`remediate`, `loop`, `migrate`) and design the supervisor's verb based on the actual usage data | A future user-facing simplification ("just `codegenie fix`") requires a meta-CLI surface — Phase 11+ work, not Phase 7's problem |
| Inlining shared options is the simpler choice per `CLAUDE.md` Rule 2 — no new abstraction for two callsites; refactor when there's a third | The duplication is a real refactor candidate in Phase 8; if Phase 8 ships under time pressure, the duplication persists |

## Consequences

- `src/codegenie/cli/migrate.py` is a new file with the canonical surface; exit codes match Phase 6 (0 ok / 11 escalate / 12 paused at human / 13 checkpoint integrity violation / 1 unexpected).
- `tests/unit/cli/test_migrate_cli.py` exercises the Click invocation surface, exit codes, and `--json` flag.
- The compiled-graph factory `build_distroless_loop()` is the integration seam Phase 8's supervisor will consume; the CLI is the local-host operator surface only.
- Workflow ID derivation uses a `wf:distroless:<sha>` prefix differing from `wf:vuln:<sha>` (`phase-arch-design.md §Gap 1`) — Phase 8's supervisor uses the prefix as the dispatch key.
- Phase 8's supervisor reads `task_type` from the ledger schema and dispatches; the CLI surface is *behind* the supervisor — operators using the supervisor era won't invoke `codegenie migrate` directly.
- Phase 11's PR-promotion logic operates on `migration-report.yaml` (Phase 7) or `remediation-report.yaml` (Phase 6) by sniffing the file header — no shared CLI required.

## Reversibility

**High.** Folding `cli/migrate.py` into `cli/loop.py` is mechanical (add a Click subcommand group, forward to the existing handlers). Phase 8's supervisor is the natural unifier and may choose a different verb structure (`codegenie sherpa run --task distroless` vs `codegenie sherpa migrate`). The shape — two parallel verbs during the POC era — is a documented intermediate state, not a permanent commitment.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 16` (CLI dispatch home; `[B]` over `[P]`)
- `../final-design.md §Conflict-resolution row 17` (Phase 6 `cli/loop.py` not edited)
- `../final-design.md §Architecture B-shape Open Q #5` (inline shared options)
- `../final-design.md §"Acknowledged debt Phase 8 inherits"` (two CLI verbs)
- `../phase-arch-design.md §Component 12` (cli/migrate.py interface)
- `../phase-arch-design.md §"Control flow §Dispatch (vuln vs distroless)"`
- `../critique.md §performance.5` (the `cli/sherpa.py` fork attack)
- [Phase 6 ADR-0009](../../06-sherpa-state-machine/ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md) — `cli/loop.py` ships parallel pattern
