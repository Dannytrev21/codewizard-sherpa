# ADR-0009: `cli/loop.py` ships parallel to `cli/remediate.py` — Phase 0–5 source untouched

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cli · extension-by-addition · phase7-integration
**Related:** [ADR-0010](0010-phase5-runner-run-one-public-promotion.md)

## Context

The roadmap exit criterion for Phase 7 ("Add migration task class — Chainguard distroless") is *"The diff for this phase touches **only** new files — no Phase 0–6 source code is modified."* (`roadmap.md §Phase 7 Exit criteria`). The three lenses set up Phase 7 to either violate that criterion or fragment the CLI:

- **Best-practices** explicitly edited `cli/remediate.py` via its own ADR-P6-001, treating Phase 3's CLI as the dispatch point. `critique.md best-practices.5` landed: if `cli/remediate.py` is Phase 0–6 source, Phase 7 cannot edit it again to add the distroless path; the Phase 7 exit criterion forces a CLI split.
- **Performance** shipped a `codegenie loop run` command but did not address whether `codegenie remediate` was deprecated, edited, or coexistent.
- **Security** did not specify CLI naming.

Phase 6 introduces a fundamentally new orchestration shape (the LangGraph state machine) — naming and namespacing it cleanly is load-bearing for every later phase that adds a task class or a supervisor. The synthesizer's choice (`final-design.md §Goals row 14`) is to ship a *new* `cli/loop.py` that does not touch `cli/remediate.py`, so:

- Phase 7's distroless adds a sibling factory or its own CLI; Phase 6's source is untouched.
- Phase 8's supervisor adds a parallel `codegenie sherpa` namespace; Phase 6's source is untouched.
- The Phase-3 `codegenie remediate` command continues to call Phase 3's `RemediationOrchestrator` directly — no behavior change.

## Options considered

- **Edit `cli/remediate.py` to dispatch to the new graph (best-practices' pick).** One CLI command. Phase 3 source modified. Sets up Phase 7's exit-criterion violation.
- **Ship `cli/loop.py` in parallel; `cli/remediate.py` unchanged.** Two CLI commands during the POC; clean Phase 7 path; the Phase 3 linear orchestrator remains a valid (and useful) entry point for smoke tests.
- **Deprecate `cli/remediate.py` immediately.** Remove a working command before its successor is proven. Premature; violates surgical-changes discipline.

## Decision

Phase 6 ships a new file at `src/codegenie/cli/loop.py` exposing the `codegenie loop` command group:

```
codegenie loop run <repo> --cve <id> [--max-attempts N]
codegenie loop resume <thread_id> --decision continue|override|abort
                                   [--note "..."] [--operator <name>]
codegenie loop inspect <thread_id>
codegenie loop replay <thread_id> [--from <checkpoint_id>]
codegenie loop migrate-checkpoint --from <old_version> --to <new_version>
codegenie loop render --out <path>
```

`src/codegenie/cli/remediate.py` is **not modified.** It continues to invoke Phase 3's `RemediationOrchestrator` directly. The compiled-graph factory `build_vuln_loop()` is the integration seam Phase 7's `build_distroless_loop()`, Phase 8's supervisor, and Phase 9's Temporal worker will all consume.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7 ships truly additive — no Phase 0–6 source touched, exit criterion preserved | Two CLI entry points during the POC era — operators must know which to use; the README must document the split |
| Phase 3's sync orchestrator remains a working baseline for smoke tests and debugging — comparing graph behavior against linear behavior is a one-shot CLI invocation | `cli/loop.py` and `cli/remediate.py` will share some setup logic (workflow_id derivation, advisory loading); duplicating this is acceptable in Phase 6 but is one of the first refactor candidates in Phase 8 |
| Phase 8's supervisor adds `codegenie sherpa` in parallel; the namespace pattern is "one verb per orchestration layer" — durable across the roadmap | A future user-facing simplification ("just `codegenie fix`") requires a meta-CLI in Phase 11+; Phase 6 does not pre-design it |
| The compiled-graph factory is the single seam Phase 7+ consumes — clean dependency direction | The CLI duplication is the visible cost of preserving the additive-extension invariant; reviewers may want to refactor sooner; the synthesizer's answer is "not in Phase 6" |

## Consequences

- **`tests/graph/test_cli_remediate_unchanged.py`** (CI gate) — asserts `cli/remediate.py` is byte-for-byte identical to the Phase 3 baseline via a content-addressed snapshot. Reverts that touch it loudly fail.
- The Phase 7 distroless work has a documented, tested path: ship `src/codegenie/graph/distroless_loop.py` + a separate `cli/distroless.py` or extend `cli/loop.py` with a `--task` flag — Phase 7 decides which, but both options leave `vuln_loop.py` and `cli/remediate.py` alone (`phase-arch-design.md §Integration with Phase 7`).
- Workflow ID derivation is content-addressed (`blake3(repo_root_blake3 || advisory_id)`) and the same scheme is shared between the two CLIs — re-running the same advisory always lands on the same checkpoint file.
- `codegenie loop` exit codes: 0 (success), 11 (escalate), 12 (paused at await_human), 13 (`CheckpointTampered`/`CheckpointerInsecure`/`SchemaDrift`/`AuditChainCorrupted`), 1 (unexpected) — operators get a clean signal.
- Phase 9's Temporal worker imports `build_vuln_loop()` directly and never invokes `cli/loop.py`; the CLI is the local-host operator surface only.

## Reversibility

**High.** Adding the dispatch into `cli/remediate.py` later is a one-line change (literally a `click` group + a forward to the new command). Removing `cli/loop.py` and folding everything into `cli/remediate.py` requires updating tests and docs but is mechanical. The shape — two parallel namespaces during the POC — is a documented intermediate state, not a permanent commitment.

## Evidence / sources

- [`../final-design.md` §Goals row 14 "cli/remediate.py is not modified"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 9 "cli/remediate.py edit"](../final-design.md)
- [`../final-design.md` §Component 9 "CLI surface — codegenie loop"](../final-design.md)
- [`../phase-arch-design.md` §Component 8 "cli/loop.py — operator surface"](../phase-arch-design.md)
- [`../critique.md` §best-practices.5](../critique.md) — the Phase-7-exit-criterion conflict
- Roadmap §Phase 7 — "diff for this phase touches only new files"
