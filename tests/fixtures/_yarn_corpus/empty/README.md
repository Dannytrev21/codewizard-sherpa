# Fixture: `empty`

**Shape:** Comments-only yarn-classic v1 lockfile. Zero entries.

**Entry count:** 0
**Native modules present:** no
**Shared specifier headers:** no

**Invariants pinned non-trivially:**

- Invariant 3 (count parity) — entry-header line count = 0; this fixture
  pins the zero-boundary. A parser that always emits one phantom entry
  would pass invariants 1 and 2 trivially on every non-empty fixture but
  would fail this fixture's count check.

**Invariants vacuously satisfied (iteration over zero entries):**

- Invariant 1 (anchored-name presence) — there are no entries to anchor.
- Invariant 2 (version locality) — there are no versions to locate.

This fixture is **excluded** from the `test_yarn_parser_oracle_self_check`
module because there is nothing to mutate; the zero-boundary is covered by
`test_yarn_parser_oracle.py`'s parametrized arm over this fixture.

**Parse-time note:** Pre-S3-04, the hand-rolled scanner raised
`ValueError("no yarn.lock entries parsed")` on a zero-entry body, which
`_yarn.parse()` translated to `MalformedLockfileError`. S3-04 fixes that:
a comments-only body now returns `{"entries": {}}`. Malformed bytes
(non-comment, non-header lines) still raise via the "expected entry
header" branch — see `src/codegenie/probes/_lockfiles/_yarn.py`
`_parse_handrolled`. This fixture is the regression test for the fix.
