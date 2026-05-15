# `non_node_go/` fixture

A purely-Go repository — the load-bearing **contract test for ADR-0010**
(Layer-A slices optional at envelope).

**Exercises:** `language_detection` on a non-Node repo. The fixture proves
a non-Node repo flows cleanly through Phase 1 and produces a valid
envelope with `language_stack.primary == "go"`.
**Consumed by:** `tests/integration/probes/test_non_node_repo.py` (S5-05).
**Phase 1 design ref:**
`docs/phases/01-context-gather-layer-a-node/phase-arch-design.md §"Fixture portfolio"`
and `ADRs/0010-layer-a-slices-optional-at-envelope.md`.

## What gets filtered out

Per `applies_to_languages` filtering in `Registry.for_task`, only **three**
Phase 1 probes are filtered out of this fixture's gather pass:

- `node_build_system` (`applies_to_languages = ["javascript", "typescript"]`)
- `node_manifest` (same)
- `test_inventory` (same)

CI and Deployment probes (`applies_to_languages = ['*']`) run on this
fixture and may produce empty slices — only `node_build_system`,
`node_manifest`, `test_inventory` are filtered out. This is the precise
contract pinned by **ADR-0010**: sub-schemas declare slices optional at
the envelope's `probes.*` level, so absence (not `null`-valued presence)
is the observable.

## File-by-file

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `go.mod` | `language_detection` | Go module declaration. Exact bytes pinned by `_go_mod_exact_bytes` — declares no dependencies, so no `go.sum`. |
| `main.go` | `language_detection` | Trivial `package main` entry point. Walker counts this as a `.go` file; never parses it. |
| `internal/handler.go` | `language_detection` | Second `.go` file (`package internal`) so the counter sees more than one. |
| `README.md` | — | This file. Mechanically enforced to mention `ADR-0010` and the word `three`. |
