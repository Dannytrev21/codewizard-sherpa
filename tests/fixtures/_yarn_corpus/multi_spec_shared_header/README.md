# Fixture: `multi_spec_shared_header`

**Shape:** Two yarn-classic v1 entries. The first uses a **comma-joined
specifier-range header** (`"debug@^2.6.9", "debug@^2.6.0":`) — both ranges
resolve to the same package, so yarn writes them on one header line. The
second is a plain header.

**Entry count:** 2
**Native modules present:** no
**Shared specifier headers:** yes (`debug` entry)

**Invariants pinned non-trivially:**

- Invariant 1 (anchored-name presence) — the parsed entry-key is the full
  comma-joined string; the invariant splits on `, ` and asserts each name
  (here, `debug` twice, then `ms`) appears at a start-of-locator position.
  This catches a parser that mishandles the quoted-comma-joined header
  syntax — e.g., emits one of the two `debug` specifiers as a phantom
  unquoted package.
- Invariant 2 (version locality) — `2.6.9` and `2.0.0` must each appear
  within ±5 lines of their headers.
- Invariant 3 (count parity) — entry-header line count = 2 (the
  comma-joined header counts as **one** header line).
