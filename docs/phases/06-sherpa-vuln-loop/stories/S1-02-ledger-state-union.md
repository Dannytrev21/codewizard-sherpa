# S1-02 — Ledger state union

**Status:** Ready  
**Goal:** Model the vuln workflow ledger as a closed discriminated union.

## Acceptance criteria

- All seven ledger variants exist.
- Illegal transitions are unrepresentable in constructors.
- Exhaustive match tests cover every state.

## TDD plan

Red: transition-table tests fail on missing variants.  
Green: add models and constructors.  
Refactor: move repeated evidence fields into shared bases.
