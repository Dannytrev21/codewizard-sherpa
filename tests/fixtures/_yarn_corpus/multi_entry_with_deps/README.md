# Fixture: `multi_entry_with_deps`

**Shape:** Three yarn-classic v1 entries; the first (`express@^4.18.2`) has a
`dependencies:` sub-block referencing the other two.

**Entry count:** 3
**Native modules present:** no
**Shared specifier headers:** no

**Invariants pinned non-trivially:**

- Invariant 1 (anchored-name presence) — `express`, `accepts`, and
  `array-flatten` must each appear at a start-of-locator position in the
  lockfile bytes.
- Invariant 2 (version locality) — each entry's version (`4.18.2`, `1.3.8`,
  `1.1.1`) must appear within ±5 lines of its header.
- Invariant 3 (count parity) — entry-header line count = 3; this fixture
  catches both under-emit (e.g. a parser that drops the third entry) and
  over-emit (a parser that misreads a nested `dependencies:` key as a header).
