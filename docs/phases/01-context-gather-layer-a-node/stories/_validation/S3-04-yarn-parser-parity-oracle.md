# Validation report — S3-04 yarn-parser-parity-oracle

**Validated:** 2026-05-14
**Verdict:** **HARDENED**
**Story:** [`../S3-04-yarn-parser-parity-oracle.md`](../S3-04-yarn-parser-parity-oracle.md)
**Skill version:** phase-story-validator

## Verdict rationale

The story's goal (ship fixture-parity + property-based oracle tests for `_yarn.py` per ADR-0003 / Gap 3) was sound and well-traced to source-of-truth docs. Six findings, all `harden` (none `block`). No structural problems requiring RESCUE; no `NEEDS RESEARCH` items — every fix used patterns already established in the codebase (monkeypatch dispatch, parametrized fixtures, pure helpers + imperative shell).

## Context Brief

- **Story promise.** Two test modules + a fixture corpus that catches silent parser divergence (pyarn↔hand-rolled) on the curated portfolio and catches coordinated drift via lockfile-bytes-derived invariants.
- **Phase exit criteria touched.** Phase 1 final-design §Risks / phase-arch-design.md Gap 3 — "the yarn parser parity test is single-direction." This story is the answer to that gap.
- **Arch / ADR constraints.**
  - ADR-0003 — "both parser paths return identical `YarnLock` TypedDict; the parity test is the contract enforcement."
  - phase-arch-design.md §"Component design" #9 — `parse(path) -> YarnLock` is the public surface; `_HAS_PYARN` is internal dispatch.
  - S3-03 AC-3 — `parse(path)` calls `open_capped(...)` for the size-cap defense; AC-13 — `_pyarn_parse` is a body-bytes-in adapter.
  - CLAUDE.md "Extension by addition" — adding parsers / tests must not edit the kernel.
  - Global Rule 9 — tests verify intent, not behavior.
  - Global Rule 2 — three similar lines is better than premature abstraction.

## Stage 2 — Critic findings

### Coverage critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C-1 | harden | Three invariants listed (good), but the mutation-experiment AC is "verified locally + PR-body paragraph" — not CI-enforced. A reader can't audit from CI logs whether the invariants have teeth. | New AC-9: `test_yarn_parser_oracle_self_check.py` with three automated mutation cases. |
| C-2 | nit | Empty fixture trivially satisfies invariants 1 and 2 — readers won't know which invariants it pins *non-trivially*. | New AC-8 clause: README must state which invariants the fixture pins non-trivially. |
| C-3 | nit | No AC ties the invariant-helpers to a single source of truth — the oracle test could drift from the self-check. | New AC-10: helpers are module-level, exported, imported by self-check. |

### Test-Quality critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T-1 | harden | Parity test sketch calls `_yarn._parse_handrolled(bytes)` and raw `pyarn.parse(text)` directly, bypassing the `open_capped` defense (S3-03 AC-3) and any future `_pyarn_parse` adapter (S3-03 AC-13). Apples-to-oranges comparison. | AC-1 rewritten: both branches go through `_yarn.parse(path)` with `_HAS_PYARN` monkeypatched. |
| T-2 | harden | `pyarn.parse(text)` is wrong — S3-03 documents the actual API as `pyarn.lockfile.Lockfile.from_file/from_string`. Test would fail to import. | Resolved by T-1: the test never imports `pyarn` directly. |
| T-3 | harden | Invariant 1 uses bare `name in body` substring — a parser that invents `lodash` passes against a body containing only `lodash-es` (silent false negative). | AC-4 rewritten: anchored at start-of-locator (`"name@`, `, name@`, `\nname@`). |
| T-4 | nit | Invariant 3 helper doesn't skip yarn-berry's `__metadata:` block header — would over-count headers if a berry fixture were added. | `_entry_header_lines` updated to skip `__metadata:`. |
| T-5 | nit | The mutation experiment was a manual ritual — the rewritten self-check module makes it a regression test that also documents the invariant↔mutator pairing. | Covered by C-1. |

### Consistency critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| K-1 | nit | ADR-0003 §"Consequences" names `tests/unit/probes/test_yarn_parser_oracle.py`; story uses `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py`. | Documented in Notes §6 + AC-12; story-path preferred (co-location with `_lockfiles/`); ADR amend is a one-line follow-on if a reviewer flags drift. |
| K-2 | nit | ADR-0013 splits yarn into classic vs berry; the corpus is yarn-classic only. | Acknowledged as scope-correct: S3-03's `_yarn.py` targets yarn-classic; berry support would be a future story. Surfaced in Notes §4 (anchor extensibility). |

### Design-Patterns critic

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D-1 | nit | Invariant helpers could be elevated to a `INVARIANT_REGISTRY` capability registry — but only three invariants exist (below rule-of-three for a new abstraction per Rule 2). | Keep helpers inline + exported; document the elevation trigger in Notes §10. |
| D-2 | harden | The original sketch had `_check_invariant_*` logic inlined in test bodies, hard to share with self-check. | Promoted to module-level pure helpers (AC-10) — functional-core / imperative-shell split. |
| D-3 | nit | `force_handrolled` parametrize couples test to a boolean flag; a future Strategy/Registry refactor would touch tests. | Acceptable per Rule 2; documented as future trigger in Notes §2. |
| D-4 | (validated) | The corpus pattern (`{name}/yarn.lock + README.md`) is already extension-by-addition; the invariant pattern is already extension-by-addition; the self-check pattern is already extension-by-addition. | Recorded in Validation notes block at the top of the story. |

## Stage 3 — Researcher

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every fix used patterns established in the codebase (monkeypatch dispatch, pure helpers, parametrized fixtures) or in widely-known testing practice (mutation testing as a gate is canon — Just et al. 2014; Ammann & Offutt, *Introduction to Software Testing*).

## Stage 4 — Edits applied

1. **Validation notes block** appended below the story header (line 6).
2. **Acceptance criteria** restructured from 10 unnumbered checkboxes to AC-1..AC-12, with:
   - AC-1 / AC-3 redirected through the public `_yarn.parse(path)` surface (T-1, T-2).
   - AC-4 anchored Invariant 1 (T-3).
   - AC-6 expanded Invariant 3 helper specification (T-4).
   - AC-8 README content clause (C-2).
   - AC-9 new — CI-enforced self-check (C-1).
   - AC-10 new — invariant helpers as module-level single source of truth (C-3, D-2).
   - AC-12 new — PR-body documents the ADR path-of-record deviation.
3. **Implementation outline** rewritten — helper-first ordering, explicit "always go through `_yarn.parse(path)`" rule.
4. **Red TDD code** replaced — parity test uses `monkeypatch`-only dispatch; oracle test exercises helpers; new self-check module added with three mutator/invariant pairs.
5. **Green section** updated to reflect that the `_pyarn_parse` adapter mismatch is an S3-03 concern, not an S3-04 patch site.
6. **Refactor section** updated — rule-of-three trigger for helper extraction; deferral of `hypothesis` documented.
7. **Files-to-touch** added the new self-check module.
8. **Notes-for-implementer** restructured to 10 numbered points; design-pattern review at §10 records what's already right and what triggers a future refactor.

## Final state

- Every AC is individually verifiable from CI logs.
- The AC set collectively guarantees the goal (parity + oracle + mutation-resistance) — no escape hatches.
- Every invariant has a corresponding mutator that proves it has teeth (AC-9).
- No AC contradicts ADR-0003, phase-arch-design.md, S3-03, or CLAUDE.md.
- Extension paths are explicit: new invariant = new helper + new mutator + new self-check function, zero edits to existing tests.

**Verdict: HARDENED. Ready for `phase-story-executor`.**
