# ADR-0013: Lazy `PackageManager` re-export breaks the `types` ↔ `probes` cold-start cycle

**Status:** Accepted (documents the pattern shipped in commit `0ffbd07`)
**Date:** 2026-05-18
**Tags:** typed-identifiers · circular-import · module-layering · lazy-resolution
**Related:** [Phase 1 ADR-0013](../../01-context-gather-layer-a-node/ADRs/0013-yarn-variants-as-distinct-package-managers.md), [Phase 3 ADR-0010 — domain-modeling discipline](0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [production ADR-0033 — typed identifiers](../../../production/adrs/0033-typed-identifiers.md)

## Context

Phase 2 S1-05 introduced `codegenie.types.identifiers` as the kernel-tier alias surface for every domain identifier. To honour "Phase 1 ADR-0013 owns the `package_manager` enum" without redefining the `Literal`, S1-05 implemented the alias by importing the canonical definition from the probe that emits the field:

```python
# src/codegenie/types/identifiers.py (pre-fix)
from codegenie.probes.node_build_system import PackageManager as PackageManager
```

When any module outside `codegenie.probes.*` made `codegenie.types.identifiers` the **first** `codegenie.*` import in a process, the chain detonated:

1. `types.identifiers` evaluates the top-level import → asks Python to load `codegenie.probes.node_build_system`.
2. Loading any submodule of `codegenie.probes` first runs `codegenie.probes.__init__`, which eagerly imports every probe in Layers A–G (explicit-import discipline; Phase 0 ADR-0007).
3. Layer-B's `dep_graph` probe imports from `codegenie.depgraph`, which in turn does `from codegenie.types.identifiers import PackageManager`.
4. `codegenie.types.identifiers` is mid-initialisation; `PackageManager` is not yet bound → `ImportError: cannot import name 'PackageManager' from partially initialized module 'codegenie.types.identifiers'`.

The test suite, the CLI, and most editor entry points happen to load a `codegenie.probes.*` module **before** `codegenie.types.identifiers`, so `probes/__init__` finishes before `types.identifiers` is first asked for `PackageManager`. Phase 3's `PluginManifest` (S2-02) and the `transforms.outcomes` / `adapters.confidence` dedup (S1-03) were the first consumers whose import paths lead with `types.identifiers`. Both reproduced as `ImportError` in a fresh subprocess.

The cycle is structural, not coincidental — every future kernel-tier module that lands `types.*` ahead of `probes.*` will trip it.

## Options considered

- **Option A — Make `codegenie.depgraph.registry` import `PackageManager` directly from `codegenie.probes.node_build_system`.** Most surgical but only fixes one branch of the cycle; every other Layer-B/C/D/E/G probe that imports a name from `types.identifiers` (`ProbeId`, `IndexName`, `Language`, ...) sits on the same trap because those names are defined **after** the `PackageManager` import in `identifiers.py`. **Pattern:** treat-the-symptom.

- **Option B — Inline `PackageManager` in `types.identifiers` and have `node_build_system` re-export from there.** Inverts the dependency direction so the kernel does not reach into a probe. Architecturally tidy but breaks `tests/unit/types/test_identifiers.py::test_no_package_manager_redefinition_in_types_module`, which AST-fences `identifiers.py` against any `PackageManager = ...` assignment. **Pattern:** invert ownership at the cost of an established contract.

- **Option C — Move `PackageManager` to a new neutral leaf module `codegenie.types.package_manager`; have both `node_build_system` and `types.identifiers` re-export from there.** The leaf has zero `codegenie.*` imports, so neither re-export side can trigger a cycle. **Pattern:** physical decoupling via a leaf seam.

- **Option D — Resolve `PackageManager` lazily via a module-level `__getattr__` in `types.identifiers`; guard the static import with `TYPE_CHECKING` so `mypy --strict` still sees the re-export.** The runtime import is deferred until first attribute access; by the time anything outside the package calls `types.identifiers.PackageManager`, `probes/__init__` has finished. The dual fix on `depgraph/registry.py` and `probes/layer_b/dep_graph.py` (also `TYPE_CHECKING`-guarded / direct import from `node_build_system`) closes the back-edges. **Pattern:** PEP 562 lazy module attribute + stringified annotations.

## Decision

**Adopt Option D.** Three files change (commit `0ffbd07`):

1. `src/codegenie/types/identifiers.py` — the top-level `from codegenie.probes.node_build_system import PackageManager` is moved under `if TYPE_CHECKING:` (so `mypy --strict` still resolves the re-export); a module-level `__getattr__(name)` resolves `PackageManager` at first runtime access via a function-local import. `__all__` is unchanged.
2. `src/codegenie/depgraph/registry.py` — the `from codegenie.types.identifiers import PackageManager` is moved under `if TYPE_CHECKING:`. The module already had `from __future__ import annotations`, so all `PackageManager` annotations in this file are stringified — no runtime reference exists.
3. `src/codegenie/probes/layer_b/dep_graph.py` — imports `PackageManager` directly from `codegenie.probes.node_build_system` (its canonical origin), which `probes/__init__.py` fully loads before reaching `layer_b/dep_graph`.

Phase 1 ADR-0013's single-owner contract is preserved: the `Literal` still lives in `codegenie.probes.node_build_system` and nowhere else. The kernel-tier re-export at `types.identifiers.PackageManager` still resolves to the same object — only the **timing** of the resolution moves from module-load to first attribute access.

The pre-existing AST pin at `tests/unit/probes/layer_b/test_dep_graph.py::test_package_manager_imported_from_types_identifiers` was renamed to `test_package_manager_imported_from_canonical_source` and now accepts either the origin-module path (`codegenie.probes.node_build_system`) or the kernel-tier re-export (`codegenie.types.identifiers`).

### Why not Option C (leaf module)?

A neutral `codegenie.types.package_manager` module would also break the cycle and arguably reads more cleanly (plain `from … import …` everywhere, no PEP 562 magic). It was prototyped on this branch but **not adopted** because:

- Master shipped Option D first; Option C would now require reverting + replacing the lazy-resolution pattern. The cycle is already gone — re-fighting the same files burns review budget without changing the user-observable behaviour.
- Option D is local to two re-export sites; Option C adds a new public module + a third re-export hop.
- The PEP 562 `__getattr__` pattern is rare enough in this codebase that the docstrings on `types.identifiers.__getattr__` carry the rationale to future readers — and Option C's leaf-module pattern is recorded here as a clean alternative if a future story needs a stronger structural fix.

This ADR is therefore a **documentation-and-test ADR** for the lazy-resolution pattern that shipped, not a fresh code change.

## Consequences

- **`mypy --strict` is unaffected.** The `TYPE_CHECKING`-guarded import is what the type checker sees; the lazy `__getattr__` is invisible at static-analysis time. `Literal` is a typing primitive — no runtime divergence.
- **Cold-start hygiene.** The regression test at `tests/unit/types/test_cold_import_paths.py` (new in this branch) runs `from codegenie.plugins.manifest import PluginManifest`, `from codegenie.types.identifiers import PackageManager`, `from codegenie.types import PackageManager`, `from codegenie.transforms.outcomes import Trusted, Degraded, Unavailable`, and `from codegenie.adapters.confidence import AdapterConfidence` in **fresh subprocesses** so the module cache starts empty. Each must exit zero. Adding a new kernel-tier consumer that imports `types.identifiers` ahead of `probes.*` should extend this list, not silently re-introduce the bug.
- **`import-linter` contracts unchanged.** The four production contracts (`codegenie.cli` cold-start, `codegenie` `__init__` cold-start, `codegenie.plugins` LLM-SDK, `codegenie.transforms` LLM-SDK) all remain green.
- **Phase 1 ADR-0013 amendment workflow unchanged.** Adding a new package manager (e.g., `deno`) still touches:
  1. `src/codegenie/probes/node_build_system.py::PackageManager` — Literal values
  2. `src/codegenie/schema/probes/node_build_system.schema.json` — schema enum
  3. `src/codegenie/probes/node_build_system.py::_LOCKFILE_PRECEDENCE` — lockfile detection
  4. fixtures + tests
  The `types.identifiers` re-export tracks automatically via `__getattr__` — no kernel-tier edit required for value-set changes.
- **A separate, pre-existing cold-start cycle in `codegenie.depgraph` is not addressed here.** `from codegenie.depgraph.registry import default_dep_graph_registry` in a fresh process still fails because `depgraph.registry` imports `codegenie.probes.base`, which triggers `probes/__init__`, which loads `layer_b.dep_graph`, which imports back from `codegenie.depgraph` mid-init. That cycle predates Phase 3 (it landed with Phase 2 S1-10) and is flagged here as a follow-up — not in scope for this ADR.
- **The PEP 562 pattern is now precedent.** If another kernel-tier name ever needs to re-export from a heavy `codegenie.*` package, the recipe is: `TYPE_CHECKING` import for static visibility + module-level `__getattr__` for lazy runtime resolution. Future readers grepping `__getattr__` in `codegenie/types/` will find this ADR via the docstring cross-reference.

## Reversibility

**Medium cost.** Reverting to the eager top-level import re-opens the cycle the moment anything outside `codegenie.probes.*` triggers `types.identifiers` first. The regression test would fail loudly, but the failure mode would be subtle — any future kernel-tier consumer could re-introduce it. A clean replacement would be Option C (the prototyped neutral-leaf module) — three files: new leaf, one-line edit to `node_build_system`, one-line edit to `types.identifiers`. The pattern is documented here so a future story can switch styles deliberately rather than discover the tradeoff cold.

## Evidence / sources

- Commit `0ffbd07` — `fix(phase3/S1-03): dedup AdapterConfidence + break latent types↔probes import cycle`. Implements Options A + D together (Option A for `dep_graph.py`'s back-edge; Option D for `types.identifiers` and `depgraph/registry.py`).
- `src/codegenie/types/identifiers.py::__getattr__` — the lazy-resolution implementation.
- `src/codegenie/types/identifiers.py` lines 30–42 — the `TYPE_CHECKING` import + the cycle-explanation comment block.
- `src/codegenie/depgraph/registry.py` lines 51–69 — the `TYPE_CHECKING` import + the stringified-annotation rationale.
- `src/codegenie/probes/layer_b/dep_graph.py` — the canonical-origin import path.
- `tests/unit/types/test_cold_import_paths.py` — the new fresh-subprocess regression test.
- `tests/unit/probes/layer_b/test_dep_graph.py::test_package_manager_imported_from_canonical_source` — the renamed AST pin.
- Phase 1 ADR-0013 — the enum-values owner; this ADR amends only the runtime-resolution timing, not the value-set ownership.
