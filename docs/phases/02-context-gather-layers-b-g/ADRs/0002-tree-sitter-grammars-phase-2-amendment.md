# ADR-0002: `py-tree-sitter` Phase 2 amendment — the one named-trigger C-extension exception

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** dependency-policy · supply-chain · cve-surface · parser · named-trigger · amendment
**Related:** [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md), 02-ADR-0001, [Phase 1 ADR-0008](../../01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md)

## Context

[Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) set the dep-closure policy: Phase 0's ratified parser set (`pyyaml.CSafeLoader`, stdlib `json`, `blake3`, `jsonschema`, Pydantic, plus the Phase 1 `pyarn` conditional addition) is the closed default; any new C-extension parser dep requires (1) a named-trigger threshold, (2) measurement against the existing closure first, and (3) an ADR amendment to ADR-0009 with the specific dep added and CVE-feed / wheel-matrix / stubs cost accepted.

Phase 2 ships `TreeSitterImportGraphProbe` (B3) per `localv2.md §5.2`. The probe extracts file-level import edges from the source tree using tree-sitter grammars; there is no pure-Python replacement that produces grammar-accurate ASTs at tree-sitter's per-file latency (~5 ms/file). The named trigger is therefore the spec itself: `localv2.md §5.2 B3` names `tree-sitter` as a required tool for Phase 2 (`final-design.md §"Components" #12`; `phase-arch-design.md §"Component design" #12`). The Phase 0 fallback ("tune the existing parser closure") does not apply — there is no closure entry that can produce a grammar-accurate import graph for TypeScript/JavaScript/Python in milliseconds.

The performance lens proposed three additional C-extension deps in the same breath: `msgpack` (for an on-disk SCIP projection format), `scip-python` (a parser-only library), and `tantivy` (a Rust BM25 indexer for `ExternalDocsIndexProbe`). The synthesizer (`final-design.md §"Conflict-resolution table" row 8`) refused all three; none has a named-trigger in `localv2.md` and each forces a Phase 3 adapter shape that ADR-0032's plugin-internal adapter contract is meant to leave open. The critic (`critique.md §"Cross-design observations" §"shared blind spot #2"`) framed all three Phase-2 designs' silent adoption of `tree-sitter` as a missed engagement with ADR-0009; this ADR closes that gap.

## Options considered

- **Option A — pure-Python tokenization (e.g., regex-based import extractor; `ast` for Python only).** Stays inside ADR-0009's closure. **Pattern:** Functional core. Insufficient: regex import extraction is grammar-inaccurate (loses `import type {…}` vs `import {…}` distinction, misses dynamic imports, miscounts edges in TSX); `ast` covers Python only. Critic's [B] §"hidden assumption" lens applies here too — the simple shape would degrade Phase 3's adapter quality silently.
- **Option B — fork [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) wholesale; accept all three of `py-tree-sitter`, `msgpack`, `scip-python`.** Maximum Phase-2 performance flexibility. Critic [P] finding #6 attacks this: each new dep is a new CVE feed + new mypy stubs problem + new wheel-matrix surface, and only `py-tree-sitter` has a named Phase-2 consumer. The other two force downstream commitments Phase 3 should own.
- **Option C — amend ADR-0009 with **`py-tree-sitter` only**, grammar pinning at load time, in-process load, no `_grammar_runner` subprocess.** **Pattern:** Policy-by-precedent — the named-trigger amendment is the documented escape valve ADR-0009 itself prescribed. Adds exactly one C-extension dep; the wheel matrix cost is bounded (one wheel per CI platform); grammar BLAKE3-pinning makes the supply-chain attack surface auditable. Refuses `_grammar_runner` (subprocess wrap of grammar loads) as over-engineering for a threat the pin already addresses.
- **Option D — option C plus an out-of-process `_grammar_runner` subprocess for tree-sitter grammar invocations.** Security lens's proposal (`critique.md §"Attacks on the security-first design"` related context). Critic-acknowledged hidden assumption: the grammar pin already guards the supply-chain surface; the subprocess wrap is over-engineering for the Phase-2 threat model (a malicious grammar would be a deliberate supply-chain compromise the pin catches at load).

## Decision

Adopt **Option C**. `py-tree-sitter` is added to Phase 2's `gather` extras as **the single C-extension exception** to [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md). The named trigger is `localv2.md §5.2 B3`'s explicit naming of `tree-sitter` as the required tool. Grammars (`.so` / `.dylib`) are vendored, BLAKE3-pinned in `tools/grammars.lock`, and loaded **in-process**; a load-time BLAKE3 mismatch surfaces as a typed `GrammarLoadRefused` failure (the probe slice is `confidence="low"` and no grammar code executes). `msgpack`, `scip-python`, `scip-python`'s `tree-sitter-python` companion, `gitleaks-python`, and `tantivy`-as-default remain rejected.

## Tradeoffs

| Gain | Cost |
|---|---|
| The amendment path ADR-0009 itself prescribed is honored — Phase 2's one named-trigger probe (B3) gets its tool, and the closure stays bounded otherwise | `py-tree-sitter` is one more CVE-feed entry (`pip-audit` + `osv-scanner` already watch it); a memory-corruption CVE in the underlying tree-sitter C lib is a real risk surface |
| Grammar BLAKE3 pins make the *grammar* supply-chain auditable (vendored binaries; pin diff is PR-reviewable) | Grammar regeneration (a new TypeScript grammar version) is a PR with a binary diff — heavier review than the source-only `pyarn` precedent |
| In-process load is the boring shape — no second subprocess pathway, no wheel-matrix-for-`_grammar_runner` to maintain | A crashed grammar crashes the gather process; Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`, and the loudness is a feature (see Rule 12) |
| Wheel matrix stays small — `py-tree-sitter` ships wheels for macOS, Linux x86_64, Linux ARM64 (the Phase 2 supported set) | Future CI platforms (e.g., Windows-on-ARM) may lack a maintained wheel; that's a Phase-14+ concern, not Phase 2 |
| Three rejected alternatives (`msgpack`, `scip-python`, `tantivy` as default) leave Phase 3's adapter consumption shape open — Phase 3 picks `.scip` projection / mmap / re-parse based on real first-adapter measurements | Phase 3 adapters re-parse `.scip` binaries every query if no projection is added later; the Phase 3 author may discover this is too slow and propose a projection ADR. We pay that re-discovery cost rather than pre-commit Phase 2 to a binary on-disk format |
| The "one exception" rule is loud — future C-extension proposals must clear the same bar, named-trigger + measurement + ADR amendment | Future engineers may experience friction adding a dep that "obviously helps"; the friction is the point ([Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) tradeoffs) |

## Pattern fit

Pattern: **Policy-by-precedent — the named-trigger amendment is the documented escape valve the parent ADR prescribed** (composes with `design-patterns-toolkit.md §"Open/Closed Principle"`). [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) was deliberately written as a policy that admits its own override path; this ADR exercises that path exactly once for Phase 2. The Open/Closed shape is preserved: the rule itself is closed for modification (no rewrite of ADR-0009), open for extension (this amendment) — the next C-extension dep is one more amendment, not a fork. The pattern's failure mode the toolkit warns against ("the central dispatch function has a `match` block that grows every time") is avoided by keeping the closure rule additive at the ADR layer, not at a runtime dispatch layer.

## Consequences

- `pyproject.toml`'s `gather` extras gains `py-tree-sitter` (one named-trigger dep). `msgpack`, `scip-python`, `tantivy`, `gitleaks-python` remain absent.
- `tools/grammars.lock` is added — a reviewed-as-data file mapping grammar identity (language + version) to BLAKE3 digest. Vendored `.so`/`.dylib` artifacts live under `tools/grammars/` and are pin-validated at load.
- `TreeSitterImportGraphProbe.load_grammar()` performs the BLAKE3 check before any grammar code runs. On mismatch, `GrammarLoadRefused` is raised; the probe slice is marked `confidence="low"` with `error_id="grammar_pin_mismatch"`; no grammar code executes.
- `TreeSitterImportGraphProbe` does **not** ship an internal `ThreadPoolExecutor` (final-design §12; critic [P] hidden-assumption #3). Sequential per-file extraction under the Phase 0 single semaphore is the boring shape — hidden parallelism inside a probe lies to the coordinator's budget (see 02-ADR-0003).
- `pip-audit` and `osv-scanner` (Phase 0 §2.5 dep-watch tooling) continue to watch `py-tree-sitter`'s CVE feed; a CVE alert is a "review the upstream advisory, decide whether to bump or veto" PR — not a code change.
- A Phase 3+ proposal to add another C-extension parser (e.g., `scip-python` for adapter-side `.scip` parsing) requires its own ADR amendment to ADR-0009, with a named trigger from `localv2.md` or the Phase author's spec. This ADR-0002 sets the shape but does not exhaust the budget.
- The performance-lens-proposed `msgpack` SCIP projection format is rejected here, deliberately — Phase 3's first `ScipAdapter` decides projection shape (`raw .scip` mmap / re-parse / pre-projected). No Phase 2 commitment binds Phase 3 to a binary on-disk format (final-design §"Patterns rejected" #9).

## Reversibility

**High.** Removing `py-tree-sitter` is a `pyproject.toml` edit + a `TreeSitterImportGraphProbe.run()` rewrite to emit `confidence="low"` with `error_id="b3_disabled"`. The probe is one file in `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`; consumers (Phase 3 `ImportGraphAdapter`) read `raw/import-graph.json` as forward-only adjacency — a missing/empty file degrades them to "no import-graph evidence available" without consumer-side changes. Adding more C-extension deps later is the documented amendment path, not a fork.

## Evidence / sources

- `../final-design.md §"Conflict-resolution table" row 8` — Tree-sitter dep amendment resolution
- `../final-design.md §"Shared blind spots considered" #2` — explicit recognition that all three lenses missed Phase 1 ADR-0009 engagement
- `../final-design.md §"Components" #12 TreeSitterImportGraphProbe` — internal design, grammar pin, no thread pool
- `../phase-arch-design.md §"Component design" #12` — load-time BLAKE3 mismatch is `GrammarLoadRefused`
- `../phase-arch-design.md §"Edge cases" row 10` — pin-mismatch detection and containment
- `../critique.md §"Cross-design observations" §"shared blind spot #2"` — the framing
- [Phase 1 ADR-0009](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) — the parent policy this amends
- [Phase 1 ADR-0008](../../01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md) — the precedent against per-probe fork+exec; same logic refuses `_grammar_runner`
