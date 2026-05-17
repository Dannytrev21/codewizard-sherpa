# ADR-0011: Tree-sitter grammars via PyPI wheels (supersedes vendored `.so` model)

**Status:** Accepted
**Date:** 2026-05-17
**Supersedes:** [02-ADR-0002](0002-tree-sitter-grammars-phase-2-amendment.md)
**Tags:** dependency-policy · supply-chain · parser · cross-platform · amendment
**Related:** [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md), 02-ADR-0001

## Context

02-ADR-0002 adopted **vendored grammar binaries** under `tools/grammars/{language}.so` with BLAKE3 content pins in `tools/grammars.lock`. The model was "reviewed-as-code" — each grammar bump is a binary diff in the PR, reviewers compare the BLAKE3 to upstream, the loader recomputes BLAKE3 at runtime and refuses on mismatch.

Empirical findings on the road to S4-04 and S4-06 forced a re-evaluation:

1. **Cross-platform tax was never paid.** The repo shipped only Linux x86_64 `.so` stubs and no macOS `.dylib` / no Linux aarch64 / no Windows. Contributors on macOS could not run S4-04 or NodeReflectionProbe; CI on multiple platforms is a future requirement, not solvable by the current shape.
2. **The vendored binaries on master are 68-byte placeholder stubs.** Real grammars are 250–500 KiB. S4-04 hit `BLOCKED` (2026-05-16) and S4-06's NodeReflectionProbe hit the same blocker the next day. Neither story can ship without real binaries. Producing real binaries requires a build chain (Node.js + tree-sitter CLI + C compiler) that is contributor-specific and per-platform.
3. **"Reviewed-as-code" is theoretical for binary diffs.** A human reviewer cannot meaningfully diff a `.so` file. The actual review is "does the BLAKE3 match what upstream signed?" — which is *exactly* the trust-the-maintainer model PyPI provides, routed through manual hash bumps.
4. **The Python `tree_sitter` API has moved.** The `Language(path, name)` shape 02-ADR-0002 designed around is deprecated upstream. Modern usage is `Language(<PyCapsule>)` where the capsule comes from a sibling PyPI package (`tree_sitter_typescript.language_typescript()`).
5. **Maintenance cost grows linearly.** Phase 8+ adds Python and Java grammars; each new language × each supported platform compounds the binary-vendoring matrix. PyPI scales by `pip install <new-grammar>` — the wheel matrix is the maintainer's problem, not ours.
6. **`tools/grammars.lock` is a re-implementation of `pip --require-hashes`.** Both pin specific bytes by hash; only one is a one-off reinvention. Aligning with the ecosystem standard is a long-term simplification.

The named-trigger amendment 02-ADR-0002 made to Phase 1 ADR-0009 (the C-extension dep policy) is *not* in dispute — `tree-sitter` is still the single named-trigger exception. This ADR amends only **how grammars are delivered**, not whether `tree-sitter` itself is allowed.

## Options considered

- **Option A — stay with vendored `.so` files, refill the stubs with real binaries.** Honors 02-ADR-0002 literally. Defers but does not solve: cross-platform matrix, ABI churn, per-grammar-bump build-chain dependency, deprecated Python API. Each new language compounds the work.
- **Option B — adopt PyPI grammar wheels (`tree-sitter-typescript`, `tree-sitter-javascript`, future `tree-sitter-python`, `tree-sitter-java`).** Wheels ship per-platform, maintained by the upstream tree-sitter org. `pip --require-hashes` in CI preserves the supply-chain-pin property at the wheel level. ABI compatibility is the wheel maintainer's responsibility. New language = new dep line in `pyproject.toml`.
- **Option C — hybrid: PyPI in dev, vendored in prod / service.** Doubles the cache-key strategies, doubles the test matrix, doubles the failure modes. No clear benefit either path lacks.
- **Option D — descope NodeReflectionProbe + B3 import-graph to a pure-Python regex tokenizer.** Avoids `tree-sitter` entirely. Rejected: 02-ADR-0002's Option A analysis already documented why regex tokenization is grammar-inaccurate; that finding still holds.

## Decision

Adopt **Option B**. Tree-sitter grammars are sourced from PyPI as `tree-sitter-typescript`, `tree-sitter-javascript`, and (Phase 8+) `tree-sitter-python`, `tree-sitter-java`. The `tree-sitter` runtime is upgraded to `>=0.23,<0.26` to match the modern `Language(<PyCapsule>)` API.

`tools/grammars/`, `tools/grammars.lock`, and `tools/regenerate_grammars_lock.sh` are **deleted**. The `codegenie.grammars` kernel's surface narrows to a single function `language_for(name) -> tree_sitter.Language` that imports the matching PyPI package and returns the `Language` object. `GrammarLoadRefused` is retained as the exception type — consumers catch it on `ImportError` (the package is missing from the closure) or on an unknown language name.

Supply-chain pinning moves from BLAKE3-of-`.so` to `pip --require-hashes` against the wheel SHA256 (Phase 0 ADR-0006's pinned-dep discipline applies uniformly). The pin is expressed in the `pyproject.toml` lower bound + the lockfile pip ultimately consumes (Phase 0 + Phase 1 already encode pip-lockfile discipline; this ADR does not extend it).

`pip-audit` and `osv-scanner` already watch the entire installed runtime closure, so the new wheels gain CVE-feed coverage automatically — no new tooling.

## Tradeoffs

| Gain | Cost |
|---|---|
| Cross-platform out of the box — macOS Intel/Apple Silicon, Linux x86_64/aarch64, Windows wheels all ship from upstream | Trust shifts from "we built it" to "tree-sitter org built it and signed the wheel" — generally net-better for the threat model, but a deliberate shift |
| Two stories (S4-04 + S4-06 NodeReflection) unblock with a single ADR amendment + one kernel refactor | One-time migration cost: ADR amendment, kernel refactor, story status updates, deletion of vendoring infrastructure |
| Modern `Language(<PyCapsule>)` API — the deprecated `Language(path, name)` shape becomes irrelevant; future tree-sitter upgrades don't break us | The new API needs `tree-sitter>=0.23`; older grammar wheels that bundle their own C extension may pin lower. Verified upstream `tree-sitter-typescript@0.23.2` + `tree-sitter-javascript@0.25.0` co-install with `tree-sitter@0.23.x` cleanly |
| Maintenance burden scales by `pip install <new-grammar>` — Phase 8+ Python grammar adds one dep line | Wheels are larger than .so files (~1–3 MB each) due to bundled C ext; runtime closure size grows ~5 MB for ts+js |
| `tools/grammars.lock` BLAKE3 model collapses into pip's existing hash-pinning — same supply-chain property, one mechanism instead of two | Pre-existing tests that exercised the BLAKE3 verifier (~9 tests across `tests/unit/grammars/` and `tests/unit/tools/`) are deleted; replaced by smaller "does the kernel return a `Language`" surface |
| Reviewed-as-code property preserved at a higher level — `pip --require-hashes` is the ecosystem-standard expression of the same pin | A malicious upstream maintainer of `tree-sitter-typescript` could publish a compromised wheel; same threat model as every other pinned dep, mitigated by the same pip hash machinery |

## Pattern fit

Pattern: **Ports & Adapters / Dependency Inversion** (composes with `design-patterns-toolkit.md §"Hexagonal architecture"`). The kernel (`codegenie.grammars.language_for`) is the **port**; the PyPI grammar packages are the **adapter**. The probe code never imports `tree_sitter_typescript` directly — it asks the kernel for a `Language("typescript")` and the kernel does the dispatch. Adding Python in Phase 8+ is one new branch in the kernel's dispatch table, zero edits to NodeReflectionProbe.

This is also a strict simplification of 02-ADR-0002's pattern. The old shape encoded supply-chain trust at TWO layers (a hand-rolled BLAKE3 verifier + the PyPI installer for `py-tree-sitter` itself). The new shape encodes it at ONE layer (pip hash-pinning). Functional core / imperative shell holds: `language_for` is pure-ish (it imports a module and constructs an object); consumers compose it.

## Consequences

- `pyproject.toml`'s `[project].dependencies` gains `tree-sitter>=0.23,<0.26`, `tree-sitter-typescript>=0.23,<1`, `tree-sitter-javascript>=0.23,<1`. The fence (Phase 0 ADR-0002) continues to enforce the LLM-SDK closure; tree-sitter wheels are not LLM SDKs.
- `tools/grammars/`, `tools/grammars.lock`, `tools/regenerate_grammars_lock.sh` are deleted. The `.gitattributes` entries for `tools/grammars/*.so` and `tools/grammars/*.dylib` are removed.
- `src/codegenie/grammars/lock.py` is replaced by a smaller module exposing `language_for(name) -> tree_sitter.Language` and `GrammarLoadRefused`. The `GrammarLockFile` / `GrammarPin` dataclasses are removed (no callers outside the deleted tests).
- S4-04 (`TreeSitterImportGraphProbe`) and S4-06 NodeReflectionProbe both unblock. S4-04's story file is updated to reference `language_for` instead of `load_and_verify`. S4-06's story file removes the AC-R2 / T-R3 assertions about "no `class GrammarLoadRefused` redeclaration" (the import surface changes; the no-redeclaration property is preserved).
- Phase 8+ language additions (Python, Java, Go) are one-line `pyproject.toml` additions plus one entry in the kernel's dispatch table — no ADR amendment unless the runtime closure changes shape (e.g., a non-PyPI grammar source).
- A grammar wheel CVE alert via `pip-audit` is a "review the upstream advisory, bump or veto" PR — same workflow as every other dep CVE.

## Reversibility

**High.** Reverting to vendored grammars is: re-add the `tools/grammars/` directory + lockfile + regen script (the deleted ADR-0002 shape), rewrite `language_for` to call `load_and_verify`, drop the PyPI deps. Consumers (`NodeReflectionProbe`, `TreeSitterImportGraphProbe`) call `language_for(...)` either way — the kernel boundary makes the swap mechanical.

## Evidence / sources

- [02-ADR-0002](0002-tree-sitter-grammars-phase-2-amendment.md) — the parent ADR this supersedes
- [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) — the C-extension policy 02-ADR-0002 amended is still honored; this ADR only changes grammar delivery
- `docs/phases/02-context-gather-layers-b-g/stories/_attempts/S4-04.md` — empirical blocker analysis: stub binaries cannot be loaded; build chain is per-contributor
- `docs/phases/02-context-gather-layers-b-g/stories/_attempts/S4-06.md` — same blocker hit by NodeReflectionProbe one day later
- `tree-sitter-typescript` on PyPI: https://pypi.org/project/tree-sitter-typescript/ — wheels for linux x86_64/aarch64, macOS Intel/Apple Silicon, Windows
- `tree-sitter-javascript` on PyPI: https://pypi.org/project/tree-sitter-javascript/ — same wheel matrix
- Modern `tree_sitter.Language(<PyCapsule>)` API: https://github.com/tree-sitter/py-tree-sitter
