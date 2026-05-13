# ADR-0009: Permanent contract-surface snapshot canary replaces one-shot diff gate and BLAKE3 source freeze

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** ci · contract-surface · extension-by-addition · permanent-canary · enforcement
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0014](0014-regression-suite-wall-clock-canary.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md)

## Context

The whole point of Phase 7 per production ADR-0028 is to *prove* extension-by-addition. The three lens designs each proposed a different enforcement mechanism (`critique.md §best-practices.5`):

- `[B]` shipped a one-shot file-level additive-diff CI gate that retires after Phase 7. The critic landed: Phase 8/15/etc. then have no automated check; the discipline reverts to "the reviewer reads carefully."
- `[S]` shipped a BLAKE3-over-every-source-file freeze under `tools/phase-frozen-digests.yaml`. The critic landed: breaks on any whitespace edit, any in-file refactor, any comment fix — false-positives flood the gate and authors learn to regenerate it without thinking.
- Neither catches the actual contract drift (a new field on a Pydantic model, a new value in a closed `Literal`) the architecture cares about; both punish what the architecture doesn't.

The synthesizer's response (`final-design.md §"Departures #2"`, `§Component 10`; `phase-arch-design.md §Component 10`): a *permanent* CI test that snapshots the **public contract surfaces** of Phases 0–6 — Pydantic `model_json_schema()`, ABC public method signatures (`inspect.signature`), closed `Literal` value sets, registry decorator signatures, `ALLOWED_BINARIES` sorted list, egress allowlist sorted list, `FallbackTier.run` signature — into a single canonical-JSON file checked into the repo (`tools/contract-surface.snapshot.json`).

Any drift fails CI. Regeneration is a deliberate `pytest --update-contract-snapshot` invocation. PR template requires linking a per-phase ADR. `tools/snapshot_regen_audit.py` (phase-arch-design §Gap 5) is the *mechanical* enforcement of "ADR-or-revert" — a PR that touches the snapshot without an ADR diff in the same PR fails CI.

This is the load-bearing enforcement mechanism for ADR-0001's six-seam discipline; without it, the amendment to ADR-0028 is unenforceable convention.

## Options considered

- **One-shot additive-diff CI gate (`[B]`).** Catches Phase 7's first PR but retires after. Phase 8+ inherits no enforcement.
- **BLAKE3-over-source freeze (`[S]`).** Catches every byte; flags every legitimate refactor; authors learn to regenerate without reading.
- **Permanent contract-surface snapshot test (synthesizer's pick).** Catches contract / API / schema drift; allows in-file refactors; survives every later phase.
- **No automated enforcement; convention only.** Trust the PR review. Rejected — the whole point of Phase 7 per ADR-0028 is *to prove the discipline mechanically*.

## Decision

Ship `tests/integration/test_contract_surface_snapshot.py` as a permanent CI test, plus `tools/contract-surface.snapshot.json` as the canonical-JSON-serialized snapshot. The test composes Pydantic schemas, ABC signatures, closed `Literal` value sets, registry decorator signatures, allowlists, and key function signatures across `probes/`, `recipes/`, `transforms/`, `planner/`, `sandbox/`, `gates/`, `graph/`. The snapshot is regenerated via `pytest --update-contract-snapshot`. The Phase 7 PR is the first PR that ships the initial snapshot + intentionally regenerates it for ADRs 0002–0007. Every later phase that opens a seam follows the same pattern. `tools/snapshot_regen_audit.py` (GitHub Actions) enforces "snapshot diff requires an ADR-NNNN reference in the PR body or PR fails."

## Tradeoffs

| Gain | Cost |
|---|---|
| Catches the *kinds* of drift the architecture cares about (Pydantic schema, ABC signature, closed `Literal`, registry decorator) and ignores the kinds it doesn't (whitespace, comments, internal-only refactors) | Computing the snapshot requires walking every Pydantic model + every ABC + every closed `Literal` in scope; ~3 s on CI per run — non-trivial but well within budget |
| Permanent — survives Phase 8, 9, 15, every later phase; the discipline is mechanically enforced for the life of the codebase | Every later phase that opens a contract seam pays one snapshot regeneration; authors must understand the workflow (regenerate, link ADR, PR-review) |
| The snapshot is *one canonical JSON file* — diff in a PR is human-readable; reviewers see exactly which field/signature/value drifted | The "canonical JSON" serialization (sorted keys, fixed separators) must be byte-stable across Python versions / pydantic versions — pinned via `pyproject.toml` and the `tools/digests.yaml` mechanism |
| `tools/snapshot_regen_audit.py` makes "snapshot diff requires ADR" *mechanical* — not convention; closes Risk #4 from `final-design.md` | The audit tool is itself a small piece of new infrastructure (~80 LOC); must be tested (`tests/integration/test_snapshot_regen_audit.py`) |
| Phase 8's first PR is the first test of whether the discipline propagates — a known, named milestone | If the snapshot fires too often on legitimate refactors that *happen* to alter a schema (e.g., adding a docstring that becomes part of `model_json_schema()`), authors may push to weaken the check — the canonical-JSON serializer must strip docstrings before snapshotting |

## Consequences

- `tests/integration/test_contract_surface_snapshot.py` is on the CI gate list; failure blocks merge.
- `tools/contract-surface.snapshot.json` lives at the repo root in `tools/`; updated only via `pytest --update-contract-snapshot`.
- `tools/snapshot_regen_audit.py` runs in GitHub Actions on any PR that touches `tools/contract-surface.snapshot.json`; scrapes PR body for `ADR-(P\d+-\d+|0\d+)` and asserts at least one match corresponds to a modified ADR file in the same PR.
- The PR template includes a checkbox: "If this PR modifies `tools/contract-surface.snapshot.json`, I have added/edited a per-phase ADR and linked it above."
- Phase 7's PR ships seven artifacts in lockstep: ADRs 0001–0007 in this phase + the initial snapshot + the production ADR-0028 amendment.
- The snapshot's canonical-JSON serializer (`tools/canonical_json.py` or equivalent) is its own small contract; documented in `phase-arch-design.md §Component 10`.
- Phase 8/9/13/14/15 each pay one snapshot regeneration per seam they open — the discipline propagates by mechanical pattern, not by reviewer attention.

## Reversibility

**Low.** Removing the snapshot canary undoes the entire mechanical enforcement of extension-by-addition. The ADR-0001 amendment to production ADR-0028 becomes convention again — exactly the state the synthesizer rejected. The asymmetry is deliberate: this ADR exists to be permanent.

## Evidence / sources

- `../final-design.md §Goals#18` (Contract-surface freeze)
- `../final-design.md §Conflict-resolution row 21` (permanent canary; BLAKE3 freeze rejected)
- `../final-design.md §Component 10` (snapshot test design)
- `../final-design.md §"Departures #2"` (synthesis-original)
- `../phase-arch-design.md §Component 10` (compute_snapshot internals)
- `../phase-arch-design.md §Gap 5` (the regen-audit mechanical enforcement)
- `../critique.md §best-practices.5` (one-shot gate retired)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — Probe contract preserved
- [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md) — extension-by-addition commitment
