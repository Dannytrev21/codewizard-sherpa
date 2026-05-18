# ADR-0003: Path-scoped fence amendment — admit `anthropic`, `chromadb`, `fastembed`, `onnxruntime` only outside the gather pipeline

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** module-boundary · ci-enforcement · fence · import-linter · adr-0005
**Related:** [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) · [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) · phase-0 ADR-0002 (production fence — pyproject + import-linter)

## Context

Phase 0 established a closure-scoped fence: `FORBIDDEN_LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})` enforced by `tests/unit/test_pyproject_fence.py`. That fence honors commitment §2.1 ("no LLM anywhere in the gather pipeline") by simply forbidding the imports anywhere in the runtime closure. Phase 4 needs to introduce an LLM adapter (`anthropic`), a vector store (`chromadb`), an embeddings runtime (`fastembed`), and an ONNX session (`onnxruntime`) — but commitment §2.1 still must hold for `src/codegenie/probes/`, `coordinator/`, `cache/`, `output/`, `schema/`.

The critic correctly identified this as "the single most load-bearing change in Phase 4 and none of the three designs writes out the exact set membership change" (`critique.md §"Roadmap-level critiques" item 3`). The naive approach — remove `anthropic` from `FORBIDDEN_LLM_SDKS` — quietly breaks the gather-pipeline guarantee. The other naive approach — leave `FORBIDDEN_LLM_SDKS` unchanged and just import `anthropic` in the new module — fails CI immediately.

Phase 4 also must keep `langgraph` (Phase 6's job), `openai` (no second vendor in Phase 4), `langchain`, `transformers`, `sentence_transformers`, and `torch` forbidden *everywhere*. The fence amendment must be additive and surgical.

## Options considered

- **Edit `FORBIDDEN_LLM_SDKS` to remove `anthropic`** (and add nothing else). Simple but loses the gather-pipeline guarantee — any future probe could `import anthropic` with no signal. **Pattern:** Closure-scoped allowlist.
- **Per-module `# type: ignore` / `# noqa: fence` carve-outs** at the call sites that need the new deps. Trades fence robustness for inline annotations engineers can paste anywhere. **Pattern:** Local opt-out comments.
- **New `import-linter` contracts** added to `.importlinter` declaring forbidden-import edges (e.g., `src.codegenie.probes` may not import `anthropic`). Already in use for kernel layering. Strong; adds one config file's worth of contracts. **Pattern:** Layered architecture enforcement.
- **Path-scoped fence as a new pytest file** (`tests/fence/test_pyproject_fence_phase4.py`) that complements the unchanged Phase-0 fence: declares `GATHER_PIPELINE_PATHS` and `PHASE4_ADMITTED_PACKAGES`, asserts no source under the gather paths imports admitted packages, asserts only `src/codegenie/fallback/leaf/anthropic_adapter.py` imports `anthropic`, asserts only `src/codegenie/rag/` imports `chromadb`/`fastembed`/`onnxruntime`. **Pattern:** Module Boundary pattern with CI enforcement.

## Decision

Ship a **new path-scoped fence file** `tests/fence/test_pyproject_fence_phase4.py` that **complements** (does not edit) the Phase-0 `tests/unit/test_pyproject_fence.py`. The new fence declares:

```python
GATHER_PIPELINE_PATHS = frozenset({
    "src/codegenie/probes/", "src/codegenie/coordinator/",
    "src/codegenie/cache/", "src/codegenie/output/", "src/codegenie/schema/",
})
PHASE4_ADMITTED_PACKAGES = frozenset({"anthropic", "chromadb", "fastembed", "onnxruntime"})
PHASE4_STILL_FORBIDDEN = frozenset({"langgraph", "openai", "langchain",
                                     "transformers", "sentence_transformers", "torch"})
```

Assertions: (1) no source under `GATHER_PIPELINE_PATHS` imports any package in `PHASE4_ADMITTED_PACKAGES ∪ PHASE4_STILL_FORBIDDEN`; (2) no source anywhere imports any package in `PHASE4_STILL_FORBIDDEN`; (3) `anthropic` is imported only by `src/codegenie/fallback/leaf/anthropic_adapter.py`; (4) `chromadb`/`fastembed`/`onnxruntime` are imported only by modules under `src/codegenie/rag/`. **The Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited.** Complementary `import-linter` contracts (`.importlinter`) enforce the same edges at lint time. **Pattern:** Module Boundary pattern with CI enforcement (named honestly — not a runtime-unforgeable capability).

## Tradeoffs

| Gain | Cost |
|---|---|
| Commitment §2.1 holds — the gather pipeline still has zero LLM/vector-store deps in its closure | Two fence files to maintain (Phase-0 closure-scoped + Phase-4 path-scoped); engineers must understand both |
| Adding `anthropic` to one specific file is *the* permission; any other module that tries fails CI loudly | Reorganizing module locations (e.g., moving `anthropic_adapter.py`) requires updating the fence's allowlist constants in lockstep — a load-bearing test breakage if missed |
| Phase 6/7/11 grow the same way: each phase adds a path-scoped fence row for its new deps; the closure-scoped fence stays minimal | The path allowlist is config in a test file, not in a more central manifest; future audit must touch the test |
| Both `import-linter` (lint-time) and pytest (test-time) enforce the same boundary — belt-and-suspenders | `import-linter` is a *lint*; a contributor running with import-linter disabled can locally violate it. The pytest fence is the runtime backstop |
| `langgraph`, `openai`, `langchain`, `transformers`, `sentence_transformers`, `torch` remain forbidden everywhere — strictly narrower than the original Phase-0 fence | Any future ADR that admits one of these must amend both fence files (clear paper trail) |

## Pattern fit

The toolkit names this Module Boundary pattern (not GoF Capability). The critic was specific: "True unforgeability would require an object-capability runtime; Python doesn't have one" (`critique.md §"[S] §4"`). What's enforceable in Python is *layer membership* — which module may import which package — and the enforcement happens at lint and test time, not at runtime. Naming it honestly (Module Boundary + CI enforcement) keeps the audit trail truthful and avoids overclaim.

## Consequences

- Phase 4 ships with `anthropic`, `chromadb`, `fastembed`, `onnxruntime` in the runtime closure — *but only inside `src/codegenie/fallback/leaf/` and `src/codegenie/rag/`*.
- A regression in the fence (a contributor PR that adds `import anthropic` to a probe) fails CI immediately with a precise diagnostic ("file X under GATHER_PIPELINE_PATHS imports forbidden package Y").
- Phase 5's `GateRunner` (`src/codegenie/gates/`) does not import `anthropic` — it consumes `FallbackTier`'s typed outputs. The fence catches a future ambitious GateRunner that tries to call the LLM directly.
- Phase 6 will need an *additional* fence-amendment ADR to admit `langgraph` and scope it (Phase 6 introduces LangGraph as the runtime; Phase 6 ADRs amend).
- Phase 11's pgvector adapter swap is a fence-amendment ADR ("admit `psycopg`/`pgvector` under `src/codegenie/rag/`") — additive, not a refactor.
- The `tests/fence/` directory becomes the architectural-invariant test home; every phase that touches the runtime closure deposits there.
- `tests/fence/test_only_leaf_imports_anthropic.py` and `tests/fence/test_rag_no_anthropic.py` are the per-fence-rule unit tests; the omnibus `test_pyproject_fence_phase4.py` is the cross-cutting assertion.

## Reversibility

**Medium.** Adding a phase-scoped admission (Phase 6 langgraph, Phase 11 pgvector) is one PR amending one test file and one `.importlinter` block. Reverting the entire Phase 4 admission (returning to the Phase-0 closure-scoped fence) would require removing `src/codegenie/fallback/` and `src/codegenie/rag/` — i.e., deleting Phase 4. Reversing the *path-scoping* choice (moving back to closure-scoped only) is a localized test edit but loses the gather-pipeline guarantee, which is a load-bearing commitment.

## Evidence / sources

- `../final-design.md §"Load-bearing commitments check" §2.1` (the exact diff)
- `../phase-arch-design.md §Goals — G5`
- `../critique.md §"Roadmap-level critiques" item 3` (none of the three designs wrote out the fence amendment)
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) (commitment §2.1)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (probe contract stability)
- Phase 0 ADR-0002 (production fence: `pyproject.toml` + `import-linter`)
