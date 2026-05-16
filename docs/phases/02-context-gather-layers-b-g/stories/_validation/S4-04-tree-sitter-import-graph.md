# Validation report — S4-04 (`TreeSitterImportGraphProbe`)

**Story:** [S4-04-tree-sitter-import-graph.md](../S4-04-tree-sitter-import-graph.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent is correct — emit forward-only import-graph adjacency under a single coordinator slot with in-process tree-sitter, BLAKE3-pinned grammars, and `asyncio.wait_for` as the only coordination primitive. The architectural framing (no `_grammar_runner`, no `ThreadPoolExecutor`, partial-graph-better-than-no-graph) is consistent with ADR-0002, ADR-0003, and phase-arch row 10.

But four BLOCK-severity inconsistencies with master and the predecessor story would crash the executor's first red-test pass, plus eleven HARDEN-severity weaknesses (most consequential: non-deterministic JSON output kills Phase 3 cache stability; thread-count test is brittle against pytest-xdist; pure-vs-impure tangle complicates extension; the design-pattern critic's headline finding — the story re-implements the kernel S4-03 explicitly built for it):

1. **`GrammarLoadRefused` + grammar-load logic are duplicated.** S4-03 AC-20 establishes `codegenie.grammars.lock.load_and_verify(repo_root) -> GrammarLockFile` and `GrammarLoadRefused` as the **shared chokepoint for this exact story**. The draft re-declared the exception inside the probe module and re-implemented BLAKE3 verification in a probe-private `_load_grammar` helper. This is the design-patterns critic's headline finding: extension-by-addition discipline (CLAUDE.md) means S4-04 IMPORTS the kernel; it does not re-do its work.
2. **Probe.run signature is two-arg.** `src/codegenie/probes/base.py:94` defines `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. The draft used one-arg `async def run(self, ctx)`. Same phantom-signature issue S4-03's validation caught.
3. **`py-tree-sitter` extras placement is wrong.** Phase 0 ADR-0006 §Decision: `[project.optional-dependencies] gather = []` is intentionally empty; the runtime closure IS `[project.dependencies]`; the fence ADR-0002 reads `[project.dependencies]`. The draft added the dep to the empty `gather` slot.
4. **Grammar-file path resolution was only an implementer note.** The note is load-bearing (the probe must resolve `tools/grammars.lock` to the codewizard-sherpa repo root, NOT the analyzed repo root) but lived only in `Notes for the implementer` — invisible to acceptance-criteria coverage. A naïve implementation reading `ctx.workspace / "tools/grammars.lock"` would pass every AC and silently break in fixture-mode integration.

Plus HARDEN issues: non-deterministic JSON output (no sort, no atomic write); arithmetic confidence rubric ("≥ 50% succeeded") is unjustified and arbitrary; thread-count test brittle against pytest-xdist; AC-PURE functional/imperative separation absent; large-file guard missing; `tree.has_error` API spelled imprecisely; bare `assert` doesn't match S4-01 precedent; tree-sitter is not a B2 freshness source but the draft doesn't say so; mypy override block missing; T-07 forbidden-primitive list too narrow; no property test for byte-identical reruns; `Edge` is implicit (no typed model).

After hardening, every AC is verifiable against the master surface, the hand-off to S4-03's kernel is mechanically guaranteed, and the extension-by-addition stance for future grammars (Python in Phase 8+, per ADR-0002 §Consequences) is preserved through the kernel.

## Context Brief

**What the story promises:**

1. Forward-only file-level import edges for `.ts`/`.tsx`/`.js`/`.jsx` written to `<output_dir>/raw/import-graph.json` with `{"schema_version": 1, "edges": [...]}` shape.
2. Grammar BLAKE3 verification at load time; mismatch produces `confidence="low"` slice with no grammar code executed.
3. Zero hidden parallelism — verified by thread-count assertion, not just import absence.
4. Timeout containment via `asyncio.wait_for`; partial graph (Phase 3-friendly degradation).
5. `import_graph` slice with `files_with_imports`, `total_edges`, `confidence`, `parsed_files`, `failed_files`, `import_graph_uri`, `grammar_versions`.

**What the phase's exit criteria demand:**

- Layer B emits structural evidence for Phase 3 adapters (`phase-arch-design.md §"Component design" #12`).
- `tree-sitter` import-graph IS a phase exit deliverable per `High-level-impl.md` Step 4.
- Adding a new probe requires zero edits to existing probe code (CLAUDE.md "Extension by addition").
- The grammars-lock infrastructure (lock file + kernel) lands in S4-03; this story IS the first consumer (S4-03 §Why this story owns `grammars.lock`).

**What the arch + ADRs constrain:**

- **Probe ABC** at `src/codegenie/probes/base.py:74-94`: two-arg `async def run(self, repo: RepoSnapshot, ctx: ProbeContext)`.
- **S4-03 kernel** at `src/codegenie/grammars/lock.py` (S4-03 AC-20): `load_and_verify(repo_root) -> GrammarLockFile`, `class GrammarLoadRefused(RuntimeError): ...`. This is the chokepoint.
- **ADR-0002**: in-process load, no `_grammar_runner`, BLAKE3 pin at load time.
- **ADR-0003**: `@register_probe(heaviness="medium")`; no internal pool/gather; coordinator owns concurrency.
- **Phase 0 ADR-0006**: `[project.dependencies]` IS the gather closure; `gather` extras intentionally empty.
- **S4-01 hardened**: import-time validation uses `raise AssertionError`, not bare `assert` (`index_health.py:121-123`).
- **CLAUDE.md** "Extension by addition" + Rule 2 "Simplicity First" + Rule 8 "Read before you write" + Rule 11 "Match conventions".

## Source-of-truth verifications (grep against master + sibling stories)

| Reference in draft | Master / sibling surface | Verdict |
|---|---|---|
| Impl outline §6 + AC-12: `async def run(self, ctx) -> ProbeOutput` | `Probe.run(self, repo: RepoSnapshot, ctx: ProbeContext)` at `src/codegenie/probes/base.py:94` | **PHANTOM** — one-arg signature would `TypeError` at dispatch |
| AC-2 / AC-3: probe-private `_load_grammar` + locally-declared `GrammarLoadRefused` | `src/codegenie/grammars/lock.py` (S4-03 AC-20): `load_and_verify(repo_root) -> GrammarLockFile`; `class GrammarLoadRefused(RuntimeError)` already exists as the shared chokepoint | **DUPLICATION** — re-implementation forks the supply-chain defense and the typed surface |
| AC-2 step 1: "Reads `tools/grammars.lock` via `safe_yaml.load`" | The kernel owns parsing (Pydantic + `GrammarLockFile`), NOT raw `safe_yaml.load`. Probe should not touch the file. | **CONSISTENCY** — fix to "calls `load_and_verify(_REPO_ROOT)`" |
| AC-14: `[project.optional-dependencies] gather` adds `py-tree-sitter ~= 0.21` | `pyproject.toml:47` `gather = []` per Phase 0 ADR-0006 §Decision — "intentionally empty; runtime closure is `[project.dependencies]`" | **PHANTOM** — fix to `[project.dependencies]` |
| AC-11: import-time `assert` verifies IDs | S4-01 precedent at `src/codegenie/probes/layer_b/index_health.py:121-123` — `for _id in _WARNING_IDS: if not _ID_PATTERN.match(_id): raise AssertionError(...)` | **CONVENTION-DRIFT** — use `raise AssertionError` to match S4-01 |
| AC-8: `tree_sitter.Parser.parse(bytes)` produces "a tree with `has_error=True`" | `py-tree-sitter ≥ 0.21`: `tree.root_node.has_error` (boolean on the root Node), not `tree.has_error` | **API DRIFT** — precise spelling fixes it |
| AC-7 confidence rubric: "≥ 50% succeeded" → medium | No design doc or ADR justifies the 50% threshold; the rubric is arbitrary | **WEAK** — pin discrete rule keyed on `failed_files` vs `parsed_files` |
| Implementer notes only: "Vendored grammar paths are relative to the repo root" | A naïve implementation reading `ctx.workspace / "tools/grammars.lock"` would pass every AC | **HIDDEN INVARIANT** — promote to AC-Resolution |
| AC-13 + S4-01 cross-story handoff: B2 reads `<output_dir>/raw/<index_name>.json` siblings | S4-01 hardened: `IndexName` registry covers `scip`, `runtime_trace`, `semgrep`, `gitleaks`, `conventions`. `tree_sitter` is **not** a B2 index source | **OK BUT IMPLICIT** — make explicit so executor doesn't synthesize a spurious `tree_sitter.json` by analogy to S4-03 |
| AC-12: "the artifact `import-graph.json` is written with the partial edges (or omitted if no edges were collected)" | No mention of atomic write; a partial timeout-killed write would corrupt the file for Phase 3 readers | **GAP** — atomic write via tempfile + `os.replace` required |
| Phase 0 reproducibility commitment | Tree-sitter AST traversal order is grammar-version-stable but not contract; Phase 3 cache will checksum the artifact | **DETERMINISM GAP** — sort edges + `sort_keys=True` |

## Critic reports

### Coverage critic — BLOCK + HARDEN

**F-Cov-1 (BLOCK).** AC-Resolution promoted from implementer note. A naïve implementer reading `ctx.workspace / "tools/grammars.lock"` would pass every existing AC and silently fail in integration. Promoted to AC-Resolution with explicit `_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[N]` mechanism + test (T-resolution).

**F-Cov-2 (HARDEN).** AC-DET (deterministic byte-identical artifact). Phase 3 will checksum `import-graph.json`; tree-sitter traversal order is implementation-defined. Add lexicographic edge sort + `json.dumps(..., sort_keys=True, separators=(",",":"))` + atomic write (tempfile + `os.replace`). Property test T-prop-idempotent (Hypothesis) pins the invariant.

**F-Cov-3 (HARDEN).** AC-LARGE (4-MiB file-size guard). Tree-sitter is robust but a 50-MB minified bundle can OOM the process and defeat AC-12's timeout. Skip + warn + count in `failed_files`.

**F-Cov-4 (HARDEN).** AC-INDEXABLE (shared file enumeration). The probe must use Phase 1's `_enumerate_indexable_files` helper (symlink/`node_modules`/`.codegenie` exclusion policy), not re-implement enumeration. Rule 11.

**F-Cov-5 (HARDEN).** AC-7 confidence rubric pinned to a discrete unambiguous rule (no arbitrary thresholds):
- `high` iff `failed_files == 0 AND parsed_files > 0`.
- `medium` iff `failed_files > 0 AND parsed_files >= failed_files`.
- `low` iff `parsed_files < failed_files` OR `parsed_files == 0` OR `GrammarLoadRefused` OR timeout.

**F-Cov-6 (HARDEN).** Explicit non-AC: tree-sitter is NOT a B2 freshness-index source (S4-01's `IndexName` registry covers only `scip`, `runtime_trace`, `semgrep`, `gitleaks`, `conventions`). Make explicit so the executor doesn't synthesize a spurious `<output_dir>/raw/tree_sitter.json` by analogy to S4-03.

### Consistency critic — BLOCK

**F-Con-1 (BLOCK).** `Probe.run` signature is two-arg `(self, repo: RepoSnapshot, ctx: ProbeContext)`. The draft's `async def run(self, ctx)` would `TypeError` at dispatch. Same issue S4-03's validation caught. Fix throughout — AC-1, impl outline §6→§8, T-01, T-04, T-resolution, T-10, T-13.

**F-Con-2 (BLOCK).** `GrammarLoadRefused` and `_load_grammar` duplicate the S4-03 kernel. S4-03 AC-20 explicitly states the loader is "reusable by S4-04". The probe must `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify` and call `load_and_verify(_REPO_ROOT)`. Probe-private re-implementation is deleted.

**F-Con-3 (BLOCK).** `[project.optional-dependencies] gather` is intentionally empty per Phase 0 ADR-0006 §Decision. The dep belongs in `[project.dependencies]`. The fence (Phase 0 ADR-0002) reads `[project.dependencies]`. AC-14 + T-16 rewritten.

**F-Con-4 (HARDEN).** AC-8 says `has_error=True` on the tree; modern API is `tree.root_node.has_error`. Precise.

**F-Con-5 (HARDEN).** AC-11's "import-time `assert`" — S4-01 precedent uses `raise AssertionError(f"ADR-0007 violation: {_id!r}")`. Match Rule 11.

**F-Con-6 (HARDEN).** `[[tool.mypy.overrides]]` block for `tree_sitter.*` cleaner than scattered `# type: ignore`. New AC-MYPY + test.

### Test-quality critic — HARDEN

**F-TQ-1 (HARDEN).** T-06 (thread-count) as written (`len(threads_after) == len(threads_before)`) is brittle against pytest-xdist worker threads, hypothesis runner threads, structlog-async. Rewrite as set-difference by `Thread.ident` with an explicit upstream-tree-sitter exemption filter (and a TODO comment so it's visible).

**F-TQ-2 (HARDEN).** T-05/T-07 forbidden-primitive lists too narrow. Add `asyncio.to_thread`, `asyncio.create_task`, `loop.run_in_executor`, `loop.create_task`, `asyncio.as_completed`, `asyncio.wait` (the bare form), `functools.partial(asyncio.gather, ...)`. T-07 should also positively assert exactly one `asyncio.wait_for` call site.

**F-TQ-3 (HARDEN).** T-no-direct-lockfile-IO: AST-walk asserts the probe module does NOT contain `import blake3`, `from blake3 import`, `Path("tools/grammars.lock")` literal, `"grammars.lock"` substring in a string literal passed to `open(`. The kernel owns these. Catches "let me just re-read the lock for a freshness check" regressions.

**F-TQ-4 (HARDEN).** T-pure-isolation (AC-PURE): assert `_extract_imports` is callable with in-memory bytes and that `pathlib.Path.read_bytes` is NOT invoked during the pure-helper call (monkeypatch to raise `AssertionError("filesystem touched")`).

**F-TQ-5 (HARDEN).** T-prop-idempotent (Hypothesis property test): generate synthetic TS files; two `run()` invocations yield byte-identical `import-graph.json`. Cold-cache between runs via `_get_language.cache_clear()`. Pins AC-DET as a mutation-killer.

**F-TQ-6 (HARDEN).** T-resolution (fixture-mode): a fixture analyzed-repo at `tests/fixtures/portfolio/minimal-ts/` MUST cause the probe to read the codewizard-sherpa repo's `tools/grammars.lock`, not the fixture's (which doesn't exist).

**F-TQ-7 (NIT).** Test preamble adds an `autouse=True` fixture clearing `_get_language.cache_clear()` between tests. Otherwise BLAKE3-mutation tests would be order-dependent.

**F-TQ-8 (HARDEN).** T-LARGE: 5-MiB synthetic `.ts` file; assert `failed_files==1`, `"tree_sitter.file_too_large"` warning, AND `tree_sitter.Parser.parse` is NOT called on the file (spy via monkeypatch).

### Design-patterns critic — HARDEN (kernel reuse + functional core)

**F-DP-1 (BLOCK — overlaps F-Con-2).** The story re-implements the kernel S4-03 explicitly built for it. This violates "Extension by addition" (CLAUDE.md) at the most direct level: a sibling story's chokepoint is intended to be imported, not duplicated. The validation deletes the duplication and rewrites AC-2/AC-3 to consume the kernel.

**F-DP-2 (HARDEN).** Functional core / imperative shell (AC-PURE). `_extract_imports_from_file(path: Path, language: tree_sitter.Language)` mixes I/O (read bytes) and pure logic (AST walk + Query). Split into pure `_extract_imports(language, source_bytes, relative_path)` (unit-tested against in-memory bytes — no fixtures) + thin `_read_and_extract(path, language, relative_path)` shell. Future extensions (TSX-specific cases, dynamic imports, type-only imports) live entirely in the pure helper. Tests get cheaper; mutation-resistance gets stronger.

**F-DP-3 (HARDEN).** `Edge` newtype. The story uses an implicit `Edge(from_, to)` shape. Make it a Pydantic `Edge(BaseModel, frozen=True, extra="forbid")` with `from_path: str = Field(alias="from")`. This is the production-design "smart constructor + newtype" discipline at the right boundary (the JSON serializer).

**F-DP-4 (HARDEN).** `ImportGraphArtifact` Pydantic model. The artifact's top-level shape (`schema_version: 1`, `edges: list[Edge]`) is a typed boundary; Pydantic enforces it on both write and read. Future schema_version bumps are a single model change.

**F-DP-5 (HARDEN).** Atomic write discipline at the I/O boundary. Tempfile + `os.replace`; never observed partially written.

**F-DP-6 (NIT).** `_get_language` over `(id(lock), language)` is the right memo shape — once per process, identity-keyed so re-loading the lock (e.g., between gathers in a long-running process) gets a fresh `Language` correctly. Documented in AC-2.

### Researcher — not invoked

No `NEEDS RESEARCH` tags. Standard patterns apply throughout (kernel reuse, functional core, atomic writes, Hypothesis property testing, AST-precise structural tests — all precedented in S4-01 / S4-03 / sibling Phase 2 stories).

## Edits applied (summary)

Header:
- Status: `Ready` → `Validated (HARDENED 2026-05-16) — Ready`.
- `Depends on:` clarified: S4-03 lands the kernel; S4-04 imports it (no re-implementation).
- `ADRs honored:` added Phase 0 ADR-0006 (extras shape).
- New `Validation notes` block summarizing all edits.

Context:
- Three (not two) load-bearing disciplines: kernel-import discipline added as #1.
- "Verified by thread-count set-difference + AST-precise forbidden-symbol grep" — both checks named.

Goal:
- Determinism + byte-identical reruns explicitly promised.
- Kernel-delegation framing.
- Explicit non-promise: not a B2 freshness source.

Acceptance criteria — rewritten:
- **AC-1**: two-arg `run` signature called out; phantom one-arg variant flagged inline.
- **AC-2**: kernel-import; `_get_language` lru_cache memo; explicit absence of probe-side reader / BLAKE3 / `GrammarLoadRefused` declaration.
- **AC-3**: kernel's `GrammarLoadRefused`; no probe-private re-declaration.
- **AC-Resolution** (new): `_REPO_ROOT` resolution + fixture-mode test.
- **AC-4**: thread-count set-difference + AST-precise call-site walk; explicit forbidden-symbol list.
- **AC-PURE** (new): functional core / imperative shell split.
- **AC-5**: `Edge` typed Pydantic model; sorted, deterministic shape; dynamic-import omission.
- **AC-DET** (new): edge sort + atomic write.
- **AC-6**: `ImportGraphArtifact` Pydantic boundary.
- **AC-7**: discrete confidence rubric (no arithmetic).
- **AC-8**: `tree.root_node.has_error` precise API.
- **AC-LARGE** (new): 4-MiB file-size guard.
- **AC-INDEXABLE** (new): shared `_enumerate_indexable_files`.
- **AC-9**: artifact omission + `import_graph_uri` omission.
- **AC-10**: kernel exception monkeypatch target.
- **AC-11**: `raise AssertionError` per S4-01.
- **AC-12**: atomic-write discipline tied in.
- **AC-13**: side-effect import path.
- **AC-14**: `[project.dependencies]` (NOT `gather` extras).
- **AC-MYPY** (new): `[[tool.mypy.overrides]]` block.
- **AC-15**: unchanged.

Implementation outline — rewritten end-to-end (10 steps; explicit kernel import; `_REPO_ROOT` resolution; pure/shell split; sequential loop with no `await`).

TDD plan — rewritten end-to-end. Added: `_clear_language_cache` autouse fixture, T-pure-isolation, T-resolution, T-no-direct-lockfile-IO, T-LARGE, T-prop-idempotent, T-MYPY. T-06 set-difference. T-05/T-07 explicit forbidden-symbol lists.

Files to touch:
- `pyproject.toml` change: `[project.dependencies]` (not `gather` extras), plus `[[tool.mypy.overrides]]`.
- `tests/fixtures/portfolio/minimal-ts/` (new).
- Pre-existing section: explicit "imported, not re-implemented" annotation on the kernel.

Notes for the implementer — rewritten. Added: kernel-is-source-of-truth bullet; explicit `_REPO_ROOT` `parents[N]` resolution mechanism; modern `tree-sitter` API spelling; non-negotiable `[project.dependencies]` placement; AC-PURE earns-its-keep rationale.

## Final verdict

**HARDENED.** All four BLOCKs and eleven HARDENs incorporated. The story is now consistent with the master surface (`base.py`, `pyproject.toml`, `check_forbidden_patterns.py`, `index_health.py`), with the predecessor story (S4-03's `grammars.lock` kernel), and with the load-bearing CLAUDE.md commitments (extension by addition, no LLM in gather, honest confidence, determinism for structural outputs).

The probe is now positioned to be the first consumer of S4-03's kernel — exercising the "Extension by addition" stance the architecture commits to — without re-implementing the supply-chain defense the kernel was built to centralize.
