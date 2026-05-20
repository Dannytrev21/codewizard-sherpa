# ADR-0008: Python dep-graph extraction is pure parsing of resolved lockfiles — never resolution, never network, never subprocess

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Strategy pattern · Functional core, imperative shell · determinism · no-network · security
**Related:** [ADR-0009](0009-requirements-txt-directive-language-parsing-contract.md), [ADR-0007](0007-python-probes-hardened-parse-only-no-exec.md), [ADR-0011](0011-python-search-adapter-tree-sitter-first-scip-deferred.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)

## Context

Python dep-graph extraction must produce the `dep_graph.consumers`-class data for the three Python package managers — pip, poetry, uv. The temptation, and the conventional approach, is to *resolve* dependencies: run `pip install --dry-run`, `poetry lock`, or `uv lock`, which fetch from a package index and walk the transitive graph. Resolution at gather time is a hard "no" for this codebase: it would mean network egress during gather, a package-manager binary in `ALLOWED_BINARIES`, and a non-deterministic result (the same repo resolves differently as the index changes).

The codebase already structurally forbids network-at-gather-time (the `fence` job + `import-linter` + the closed `ALLOWED_BINARIES` frozenset). The security lens supplied the parse-only discipline for Python lockfiles. The best-practices lens treated lockfiles as "just another format" and would have under-handled them; the synthesis adopts the security framing (CONFLICT CR-4). The remaining design question was the *strategy structure*: three concrete per-format parsers, or a premature "generic Python lockfile reader" abstraction.

## Options considered

- **Option A — resolve dependencies at gather time** (`pip install --dry-run`, `poetry lock`, `uv lock`). **Pattern:** none — network egress + a new `ALLOWED_BINARIES` entry + non-determinism; categorically rejected.
- **Option B — one generic "Python lockfile reader" abstraction** spanning pip/poetry/uv. **Pattern:** premature abstraction — a rule-of-three violation; three formats is not yet a pattern to abstract.
- **Option C — three concrete `DepGraphStrategy` callables, one per package manager, each a pure parse of an *already-resolved* lockfile.** `poetry.lock` / `uv.lock` / `Pipfile.lock` are TOML/JSON parsed with byte+depth caps; no binary invoked, no network touched. **Pattern:** Strategy pattern + Functional core, imperative shell.

## Decision

Python dep-graph extraction is **pure parsing of already-resolved lockfiles** — it performs **zero network I/O and zero subprocess spawns**, and **never invokes a package-manager binary**. It is **three concrete `DepGraphStrategy` callables**, registered via `@register_dep_graph_strategy(PackageManager)` for the keys `"pip"`, `"poetry"`, `"uv"` (a `PackageManager` `Literal` `+3`, a loud compiler-policed edit), with **no generic lockfile-reader abstraction** — three concrete parsers for three formats, revisited only at a fourth Python package manager (rule-of-three). `poetry.lock` / `uv.lock` / `Pipfile.lock` are TOML/JSON parsed with the byte+depth caps from [ADR-0007](0007-python-probes-hardened-parse-only-no-exec.md). A new `tests/fence/test_depgraph_purity.py` AST fence proves `src/codegenie/depgraph/python/` imports no `urllib` / `requests` / `http` / `socket` / `subprocess` and contains no network/exec call. `ALLOWED_BINARIES` is **untouched** — `pip`/`poetry`/`uv` are not added.

## Tradeoffs

| Gain | Cost |
|---|---|
| Determinism — same lockfile bytes → same `DiGraph`; a re-gather produces a byte-identical golden | A repo whose dependencies are *only* in an unresolved `requirements.txt` (no lockfile) yields a near-empty graph — completeness is sacrificed |
| Zero network egress, zero subprocess — the `fence` + `import-linter` invariant holds, and a new AST fence proves it specifically for the Python depgraph | The AST fence is a narrower restatement of an invariant `import-linter` already enforces — modest redundancy, accepted for the explicit Python-scoped proof |
| `ALLOWED_BINARIES` is untouched — no new jail surface, no supply-chain entry, no subprocess-jail question | `pip`/`poetry`/`uv` metadata that lives *only* behind a resolver call is not recovered — Python dep-graph completeness on lockfile-less repos is explicitly lower |
| Three concrete parsers — honest, no premature abstraction; each format's quirks are handled directly | A fourth Python package manager will need a fourth concrete strategy before the abstraction is earned — the abstraction is deferred, not free |
| The `Strategy` registry is the existing `@register_dep_graph_strategy` seam — a new ecosystem is new files plus a `Literal` `+3` | The three strategies share no code; a genuine cross-format bug fix would touch three files until the rule-of-three is met |

## Pattern fit

The toolkit's **Strategy pattern** is the right structure: three interchangeable per-ecosystem parsers behind the existing `DepGraphStrategy` callable alias, selected by `PackageManager` key — and the toolkit explicitly warns "Strategy with a single implementation = unnecessary indirection; wait for the second implementation." Here there are genuinely three, so the registry is earned. But the toolkit equally warns against **premature pluggability** — a generic "lockfile reader" abstraction spanning three formats is machinery ahead of need; three concrete parsers for three concrete formats is honest, and the rule-of-three says abstract at the *fourth*. The parse-only discipline is **functional core, imperative shell**: the strategies are pure parses of already-resolved data — no I/O beyond the read, no resolution, no subprocess. This is what makes determinism a structural property: a function that does not fetch cannot return a different answer because the index changed.

## Consequences

- A re-gather of a Python fixture produces a byte-identical golden — the golden-regen idempotence test holds; `tests/golden/languages/python/` is a stable contract.
- `ALLOWED_BINARIES` stays a closed set with `pip`/`poetry`/`uv`/`scip-python` absent — a closed-set regression test asserts this; a future resolver would need a sanctioned `ALLOWED_BINARIES` amendment under the Phase 2 omnibus ADR-0001.
- A repo using only VCS deps or a lockfile-less `requirements.txt` yields a near-empty graph with `confidence="low"` and explicit unresolved-reasons — dep-graph completeness on adversarial/lockfile-less inputs is explicitly sacrificed.
- `tests/fence/test_depgraph_purity.py` is a CI-blocking AST proof that `src/codegenie/depgraph/python/` cannot fetch — a planted `import requests` in that subpackage turns it red.
- A fourth Python package manager is a fourth concrete strategy + a `PackageManager` `Literal` `+1`; the generic abstraction is revisited then, not before.

## Reversibility

**Low.** The no-network / no-subprocess discipline is a fixed trust-boundary invariant of the whole gather pipeline (production ADR-0005) — reversing it for Python alone is not a design option. The *structure* (three concrete strategies vs. an abstraction) is more reversible — Medium — and is explicitly deferred to a rule-of-three trigger. Adding a resolver would be a fundamental architecture change (network at gather time) requiring its own ADR and an `ALLOWED_BINARIES` amendment; it is out of scope for every foreseeable phase.

## Evidence / sources

- [final-design.md §Components — Python dep-graph strategies](../final-design.md#components), §Synthesis ledger CR-4, §Resource & cost profile, §Test plan (fence)
- [phase-arch-design.md §Component design — Python dep-graph strategies](../phase-arch-design.md#component-design), §Goals G5 and G8
- [critique.md §Things this design missed](../critique.md) — `requirements.txt` is a directive language; best-practices' "just another lockfile format" framing
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — deterministic gather, no network egress
- Phase 2 ADR-0006 — `@register_dep_graph_strategy` / `DepGraphRegistry`; Phase 2 omnibus ADR-0001 — the `ALLOWED_BINARIES` amendment path
