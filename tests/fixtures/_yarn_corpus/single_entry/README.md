# Fixture: `single_entry`

**Shape:** Minimal yarn-classic v1 lockfile with exactly one entry (`lodash@^4.17.21`).

**Entry count:** 1
**Native modules present:** no
**Shared specifier headers:** no

**Invariants pinned non-trivially:**

- Invariant 1 (anchored-name presence) — `lodash` must appear at a start-of-locator
  position in the lockfile bytes; a parser that invents `lodash-es` against this
  body would be caught.
- Invariant 2 (version locality) — `4.17.21` must appear within ±5 lines of the
  `lodash@^4.17.21:` header line.
- Invariant 3 (count parity) — entry-header line count = 1; parser must emit
  exactly one entry.
