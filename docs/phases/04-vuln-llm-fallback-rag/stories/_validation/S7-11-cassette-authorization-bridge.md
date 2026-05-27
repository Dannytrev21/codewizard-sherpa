# Validation report — S7-11 Cassette-recording authorization bridge

**Validator:** `phase-story-validator`
**Date:** 2026-05-27
**Verdict:** **HARDENED** — 3 block-tier defects fixed; 5 harden-tier defects fixed; 2 design notes deferred.

## Context

S7-11 was authored by `phase-story-executor` on 2026-05-27 as an explicit "If there is a block, write a new story" bridge — its purpose: gate S6-07/S7-06/S7-07 (all HARDENED-not-GREEN, blocked on the cassette-recording authorization step). Validator ran four parallel critics (coverage, consistency, test-quality, design-patterns) against the original draft.

Pre-validation scaffolding was already shipped at `tests/integration/test_s7_11_cassette_sets.py` + `tests/integration/test_s7_11_preflight.py`. The validator's edits leave that scaffolding in place but flag it as **requiring realignment** as part of executing the hardened story (the bridge cassette subdir names baked into the shipped tests are incorrect).

## Findings → resolutions

### Block-tier (3)

**B1 — Cassette path divergence between bridge and downstream stories.**

| Story | Original S7-11 path | Canonical path (downstream-pinned) |
|---|---|---|
| S6-07 | `tests/cassettes/anthropic/s6_07_determinism/*.yaml` (single subdir) | `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/cassette.yaml` (**4 branch subdirs** + recording_arch.json sidecar each) |
| S7-06 | `tests/cassettes/anthropic/s7_06_e2e_breaking_change/*.yaml` (subdir) | `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` (**single top-level file**) |
| S7-07 | `tests/cassettes/anthropic/s7_07_e2e_replay_lands_rag/*.yaml` (subdir) | `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` (**single top-level file**; baseline-cost first-leg *replays* S7-06's cassette) |

Per Global Rule 7 ("Surface conflicts, don't average them") + validator priority (Consistency > Coverage), downstream wins (older, HARDENED, with detailed ACs pinning paths). Resolution: AC-1/AC-2/AC-3 rewritten to the canonical paths; Files-to-touch updated; explicit `Note on s6_07_determinism/ etc.` added flagging the shipped scaffolding realignment as Phase 1 work.

**B2 — Empty-file blindness in original example test.**

Original `test_s6_07_cassette_set_present_or_loudly_skips` used `list(_CASSETTES_DIR.glob("*.yaml"))` non-empty as its assertion. A zero-byte commit would pass the bridge while pushing yaml-parse failures downstream. Resolution: every AC-1/AC-2/AC-3 test now calls `verify_cassette(path).passed is True` (S3-04 sanitizer round-trip — rejects empty/malformed/secret-bearing cassettes) **plus** a per-file BLAKE3 round-trip via `load_lockfile` + `compute_cassette_digest`.

**B3 — AC-6 referenced a `## Rotation cadence` section that doesn't exist.**

`docs/operations/cassettes.md` has no level-2 `## Rotation cadence` heading; the phrase appears once inline under `## CODEOWNERS approval flow`. The cited acceptance test `tests/integration/test_ops_docs_exist.py` (S7-10 AC-16) requires `Rotation cadence` for `secrets.md`, *not* for `cassettes.md` (see `REQUIRED_DOCS` in that file). Resolution: original AC-6 dropped entirely; new AC-6 covers "operator-appended audit-trail row" instead (the rotation log lives in `secrets.md` per S3-06's CODEOWNERS-rotation design; S7-11 should not double-write it).

### Harden-tier (5)

**H1 (coverage B5 + consistency #4) — Ordering bug.**

`make refresh-cassettes` runs `pytest -m "uses_anthropic_cassette" --record-mode=all`. On master, only one test currently carries that marker (`tests/unit/fallback/test_leaf_adapter_cassette_scenarios.py`); S6-07/S7-06/S7-07 are HARDENED-not-GREEN — their test files do not exist on master. Running S7-11's original recording session would record zero useful cassettes.

Resolution: Added **AC-0 — Downstream Red-phase scaffolds exist.** Updated `Depends on:` line to include "S6-07, S7-06, S7-07 test files at Red phase with `pytest.mark.uses_anthropic_cassette` markers and the canonical cassette paths pinned". Preflight gains `test_downstream_recording_targets_collected` — `pytest --collect-only -m uses_anthropic_cassette` must return a superset of the six canonical recording test IDs before the operator spends tokens.

**H2 — Token-spend estimate materially low.**

Original "≤ 4 Anthropic API calls" was wrong — S6-07 alone requires 4 (one per branch's seeded state). Resolution: corrected to "≥ 6 Anthropic API calls", per-branch breakdown listed in Notes-for-implementer.

**H3 — S6-07 `recording_arch.json` sidecars omitted.**

S6-07 AC-PLATFORM-1 requires a sidecar per branch (`{machine, system, embedder_model_digest}`). Pytest-recording doesn't produce it — the operator authors it by hand. Original S7-11 didn't mention it; operator would skip it; S6-07 would `pytest.skip` on arch-mismatch and silently pass on every machine.

Resolution: AC-1 strengthened to require sidecar per branch with schema check (three string keys, non-empty). Implementation outline §Phase 2 step 6 added with the authoring snippet.

**H4 — Cassette-lock check was text-substring, not per-file BLAKE3.**

Original AC-4 acceptance test used `assert c.name not in lock_body` (substring). A `cassettes.lock` containing `oldcassette.yaml` would pass the check for a new cassette named `newcassette.yaml` whose digest is wrong. Resolution: rewritten to `lock_map[relpath] == compute_cassette_digest(path)` per-file.

**H5 — AC-7 self-modification had no machine check; AC-6 ISO-date regex was tautological.**

Original AC-7 said "operator flips Status: Done" with no test. Original AC-6 said "asserts ISO date `\d{4}-\d{2}-\d{2}`" — `0000-00-00` passes that regex. Resolution: new AC-6/AC-7 enforced by single `test_audit_trail_has_recorded_row_when_status_done` that (a) only fires when `Status: Done` is in the file, (b) requires ≥ 1 audit-table row whose date field parses as `datetime.date.fromisoformat()` (rejects malformed).

### Design-pattern notes (2, deferred)

**D1 — No `CassetteBundleId` newtype.** Cassette subdir names are test-local fixture paths, not domain IDs crossing module boundaries. CLAUDE.md's newtype mandate targets cross-cutting domain IDs (probe IDs, warning IDs, package-manager identifiers); promoting a one-shot bridge fixture path is ceremony with no caller. Deferred — surfaced in Notes-for-implementer.

**D2 — No `_CASSETTE_BUNDLES` registry under `tests/_fixtures/`.** The six canonical paths live in one `_DOWNSTREAM_CASSETTES: Final` tuple inside `test_s7_11_cassette_sets.py` — that is the data-driven shape. Per Rule 2 (Simplicity First) the bridge is one-shot; if a second bridge story ever appears, *that* is the rule-of-three moment to extract a shared registry. Deferred — surfaced in Notes-for-implementer.

### Nits (acted on but not separately tracked)

- N1 — Effort tag S → M (operator coordination + sidecar authoring + per-branch recording + downstream Red-phase test scaffolding precondition).
- N2 — `pytest.xfail(strict=True)` vs loud `pytest.skip` deferred — skip is the established codebase pattern for cassette-not-yet-recorded (S7-10 AC-7 precedent), the preflight's AC-0 check provides the loud signal that compensates for skip-rot.
- N3 — Three-test-file collapse already done in shipped code; story's old "three separate files" prescription removed.

## Critic-report summary

- **Coverage critic:** 5 block + 4 harden + 2 nit. Block-level: 4 cassette-path divergences (B1-B4 in coverage report) + ordering bug (B5). All blocks addressed.
- **Consistency critic:** 2 block + 1 harden + 2 nit. Block-level: AC-6 doc-section non-existence + ordering bug duplicated as consistency #4. All blocks addressed.
- **Test-quality critic:** 3 block + 5 harden + 2 nit. Block-level: path mismatch (overlap with coverage B1-B3) + empty-file blindness (B2) + AC-1 "empty promise" wording (B3). All blocks addressed.
- **Design-patterns critic:** 0 block + 2 harden + 1 nit. Already-shipped collapse to one parametrized file noted; data-driven bundle table is the right shape at current scale; further extraction deferred per Rule 2.

Critic conflict resolution: none required at block level — all four critics agreed the path divergence and ordering issues were the dominant problems. Coverage vs design-patterns tension on "promote to a registry" resolved per validator priority (Consistency > Design-Patterns) + Rule 2: defer the extraction, surface the seam.

## Edits applied (summary)

1. Status header: `Ready` → `HARDENED`; Effort `S` → `M`; Depends-on expanded with the Red-phase-scaffolding precondition.
2. Validation notes block added under the header (block + harden defects fixed inline + deferred design-pattern notes).
3. Goal updated: "six cassettes at the exact paths those stories pin", "per-file verify_cassette-clean, BLAKE3-pinned, sidecars per branch".
4. Acceptance criteria rewritten: AC-0 added (downstream scaffolds collected); AC-1/AC-2/AC-3 rewritten with canonical paths + verify_cassette + lock round-trip + sidecar; AC-4 strengthened to per-file BLAKE3; AC-5 clarified PR-artifact form; AC-6 dropped/replaced with audit-trail enforcement; AC-7 tightened to be enforced by the same audit-trail check.
5. Implementation outline split Phase 1 (executor — realign scaffolding, no token spend) vs Phase 2 (operator — recording session).
6. TDD plan replaced with a single canonical parametrized file with full code listings: per-cassette verify+BLAKE3, per-branch sidecar, lock round-trip, audit-trail enforcement; preflight strengthened with `load_lockfile` round-trip + known-good `verify_cassette` round-trip + `test_downstream_recording_targets_collected`.
7. Files-to-touch rewritten: canonical downstream paths only; explicit note about the shipped scaffolding subdirs requiring deletion.
8. Notes-for-implementer rewritten: corrected token-spend estimate; design-pattern decisions documented (no newtype, no registry — yet).

## Follow-up for the executor

The shipped scaffolding (`tests/integration/test_s7_11_cassette_sets.py`) currently parametrizes over bridge-invented subdirs. The executor's first Red step on this hardened story is to **realign that file** to the canonical paths listed above. This is the explicit Phase 1 step 1 in the new Implementation outline.

## Verdict

**HARDENED.** Story is ready for the executor's realignment pass, and (subsequently) ready for the operator's authorized recording session once downstream stories' Red-phase scaffolds carrying `pytest.mark.uses_anthropic_cassette` are on master.
