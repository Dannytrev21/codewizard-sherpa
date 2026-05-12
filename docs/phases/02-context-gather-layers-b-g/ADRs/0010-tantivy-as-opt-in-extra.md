# ADR-0010: `tantivy` is an opt-in extra (`pip install codegenie[search]`); default BM25 path is ripgrep

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** dependency-policy · c-extension · simplicity · test-coverage · search-backend
**Related:** [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md), ADR-0004, ADR-0009

## Context

`ExternalDocsIndexProbe` (D9) builds a BM25 index over the markdown corpus configured for retrieval. The performance lens proposed `tantivy` (Rust-backed BM25) as the default engine; the best-practices lens accepted `tantivy` as default + ripgrep fallback; the security lens treated `tantivy` as another C-extension to audit.

The critic attacked this in two places (`critique.md "Attacks on the performance-first design"` #5; `"Attacks on the best-practices design"` #5):

1. Phase 1's `final-design.md` synthesizer **explicitly rejected** a new C-extension parser dependency on supply-chain and simplicity grounds (Phase 1 ADR-0009). Adding `tantivy` reverses that decision.
2. The best-practices lens itself admits that the ripgrep fallback is the *CI default path*. If ripgrep is the CI default, **`tantivy`'s code path is dead-by-default** — installed, untested in the CI loop, but in `pyproject.toml`'s default deps anyway. Rule 2 (Simplicity First) and Rule 9 (Tests verify intent) both fail.

The synthesis (`final-design.md "Conflict-resolution table" D11`): `tantivy` is opt-in via `pip install codegenie[search]`; default install path is ripgrep-only; CI exercises the default path.

## Options considered

- **Default `tantivy` with ripgrep fallback [P/B].** Maximum perf-out-of-box; reverses Phase 1 ADR-0009; adds a Rust toolchain build (or wheel) to every default install; CI's BM25 path is `tantivy` but the ripgrep fallback is the dead-code-by-default if CI somehow misses `tantivy`. Worst posture for verifying both.
- **Default ripgrep, no `tantivy` at all.** Simplest. Users who need `tantivy`-class throughput must fork or wait for a future phase to add it.
- **Default ripgrep; `tantivy` as opt-in extra [synth].** Phase 1 ADR-0009 honored; `tantivy` available for users who explicitly want it; the *code path* is exercised in a separate CI matrix run for users on `[search]`; ripgrep is the CI default.

## Decision

**Phase 2 makes `tantivy` an opt-in extra**: users install via `pip install codegenie[search]` to get the `tantivy` backend; the default `pip install codegenie` produces a ripgrep-only build.

- **`pyproject.toml`'s default dependencies** include `markdown-it-py` (pure-Python, well-supported) but **not `tantivy`**. The `[search]` extras group adds `tantivy` (wheel-pinned + `tools/digests.yaml` grammar-style SHA pin under ADR-0004).
- **`ExternalDocsIndexProbe`** detects backend at startup: `try: import tantivy; backend = "tantivy"; except ImportError: backend = "ripgrep"`. Records the chosen backend in its `index_backend` slice field; downstream consumers can read which backend produced the index.
- **The default CI path is ripgrep.** `tests/integration/test_phase2_external_docs_disabled_by_default.py` runs without `[search]`; asserts `index_backend == "ripgrep"`.
- **A separate CI matrix run exercises `[search]`.** `tests/integration/test_external_docs_index_tantivy.py` runs only when `tantivy` is importable; asserts `index_backend == "tantivy"` and query-result equivalence with the ripgrep path on a small fixture corpus.
- **Slice schema is backend-agnostic.** `index_backend ∈ {"ripgrep", "tantivy"}` is an enum field; the rest of the slice is identical regardless. Phase 4's RAG consumer reads the same shape from either backend.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 1 ADR-0009's "no new C-extension parser dependencies" stance preserved in spirit — `tantivy` is opt-in, not default | Two CI paths (default + `[search]`) — slightly more CI matrix complexity |
| Default install has no Rust toolchain dependency, no wheel-build cost — `pip install codegenie` works on every platform Phase 1 supports | Users on portfolio-scale corpora (Phase 14+) who actually need `tantivy`'s throughput must opt in explicitly; documented in the extras README |
| Dead-code-by-default failure mode (critic §P.5, §B-5) closed — both backends are exercised in CI under their respective install configurations | `tantivy`'s slice-format equivalence with ripgrep must be a test invariant (golden-file equivalence on a fixture corpus); `tests/integration/test_external_docs_index_tantivy.py` is the witness |
| `tools/digests.yaml` pins the `tantivy` wheel hash (ADR-0004 generalizes to extras) — supply-chain hygiene scales | An extras-only dependency is still a dependency; the `tantivy` wheel auditing burden falls on the same supply-chain process |
| Phase 4's RAG retrieval reads `index_backend` from the slice — knows which backend produced the index without re-querying | One additional enum field in the D9 sub-schema; documented |
| The `ExternalDocsIndexProbe` fallback logic is simple and well-tested (one `try/except`) — low-complexity defense | Backend-detection-at-startup means a user with `tantivy` installed but broken (e.g., wheel mismatch) gets ripgrep silently; mitigated by digest verification at install (ADR-0004) failing loud earlier |

## Consequences

- `pyproject.toml` declares an `[project.optional-dependencies]` group named `search` containing `tantivy>=X.Y` (pinned).
- `src/codegenie/probes/external_docs_index.py` imports `tantivy` inside a `try/except ImportError`; sets `backend = "tantivy"` or `"ripgrep"` accordingly.
- The ripgrep path is implemented as a thin wrapper around `rg --line-buffered --json` plus BM25 scoring in pure Python.
- The `tantivy` path uses `tantivy.Index` from the Python binding.
- `tests/integration/test_external_docs_index_tantivy.py` is gated on `pytest.importorskip("tantivy")`; runs in the `[search]` CI matrix.
- `tests/integration/test_external_docs_index_ripgrep.py` runs in the default CI matrix.
- A property test in `tests/property/test_external_docs_index_backend_equivalence.py` asserts that on a small fixture corpus, both backends return the same top-K document IDs (Hypothesis).
- The fence CI job (`final-design.md "Goals" #13`) is extended to forbid `tantivy` ML deps if ever added as a default — assert the extras-only placement.

## Reversibility

**High.** Promoting `tantivy` to a default dep is a `pyproject.toml` edit (move from `optional-dependencies` to `dependencies`). Demoting it further (removing entirely) is also a one-edit. The two backends produce equivalent slice shapes, so consumer code is backend-agnostic. The decision is configuration; the *capability* (BM25 indexing) is not in question.

## Evidence / sources

- `../final-design.md "Components" §5.4 ExternalDocsIndexProbe — Default engine: ripgrep`
- `../final-design.md "Conflict-resolution table" D11` — the resolution
- `../final-design.md "Departures from all three inputs" #8` — synth call-out
- `../final-design.md "Resource & cost profile"` External-dep additions — `tantivy` extras placement
- `../phase-arch-design.md "Non-goals" #9` — explicit refusal of tantivy-by-default
- `../critique.md "Attacks on the performance-first design"` #5 — Phase 1's "no C-extension" stance
- `../critique.md "Attacks on the best-practices design"` #5 — dead-code-by-default
- [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) — the precedent
