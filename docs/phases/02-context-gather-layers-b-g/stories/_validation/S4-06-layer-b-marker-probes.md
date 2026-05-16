# Validation report — S4-06 (`GeneratedCode` + `NodeReflection` + `SemanticIndexMeta` marker probes)

**Story:** [S4-06-layer-b-marker-probes.md](../S4-06-layer-b-marker-probes.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's goal — three independently-cached, ≤100-LOC marker probes (`GeneratedCodeProbe`, `NodeReflectionProbe`, `SemanticIndexMetaProbe`) that share the Layer-B per-file walker, use data-driven catalogs (Open/Closed at the file boundary), and emit honest typed confidence — is sound and traces cleanly to [`phase-arch-design.md §"Development view"`](../../phase-arch-design.md) (the three filenames are listed in `layer_b/`), [localv2.md §5.2 B3/B4](../../../../localv2.md), and CLAUDE.md's "Extension by addition" load-bearing commitment. The intentional split into three modules (separate `declared_inputs`, separate cache lifetimes) is consistent with Rule 7 (surface the conflict, don't average).

But the draft referenced **four phantom surfaces** that the executor's first red-test pass would have crashed against, plus eight harden-tier weaknesses in mutation-resistance, design-pattern enforcement, and Phase-2 sibling-slice realism:

1. **`_load_grammar` does not exist anywhere in the codebase.** The story prescribed `from codegenie.probes.layer_b.tree_sitter_import_graph import _load_grammar, GrammarLoadRefused` for `NodeReflectionProbe`. The real chokepoint is `codegenie.grammars.lock.load_and_verify` + `GrammarLoadRefused` (shipped by S4-03; verified at [`src/codegenie/grammars/lock.py:46`](../../../../src/codegenie/grammars/lock.py)). S4-04's hardened story already uses this kernel surface — S4-06 must mirror it. Phantom symbol; would have `ImportError` at module load.
2. **`ctx.sibling_slices` is not a `ProbeContext` field** (Phase 0 ADR-0007 freezes the ABC at [`src/codegenie/probes/base.py:51-62`](../../../../src/codegenie/probes/base.py); only `cache_dir`, `output_dir`, `workspace`, `logger`, `config`, `parsed_manifest`, `input_snapshot`, `image_digest_resolver` exist). AND `NodeBuildSystemProbe` does not write a `build_system.json` sidecar (its `raw_artifacts=[]` at [`node_build_system.py:748`](../../../../src/codegenie/probes/node_build_system.py)). So `SemanticIndexMetaProbe`'s prescribed "reads `build_system.typescript.resolved_compiler_options` slice if available" branch is mechanically inert — there is no surface to read it from. Same class of finding as S4-05's K-2.
3. **`build_system.typescript.resolved_compiler_options_path` is a phantom field.** The shipped `TypeScriptInfo` TypedDict at [`node_build_system.py:288-290`](../../../../src/codegenie/probes/node_build_system.py) carries `compiler_options_path: str | None` and `resolved_compiler_options: dict[str, Any]` — no `resolved_compiler_options_path`. The story's implementer-notes reference was a phantom field name.
4. **`Probe.run` signature was implied as one-arg via the impl outline's `async def run(...)` shorthand.** The frozen ABC at [`base.py:94`](../../../../src/codegenie/probes/base.py) is `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Mirrors S4-03/S4-04/S4-05 carried-over finding.

Plus harden tier:

- AC-X1's "LOC tool is implementer choice" was a variance source — pinned to `radon raw --no-comments --no-blank` (S4-04 precedent).
- AC-G2 "first hit wins" was loose — sharpened to "tuple-ordered iteration IS the precedence policy; document the ordering."
- AC-X3 confidence assertion was permissive — sharpened to `== "medium"`, not `in {"medium", "low"}`, so a regression that downgrades the marker-absent path fails the test.
- AC-X9 (byte-identical reruns) and AC-X8 (functional core / imperative shell) were missing as ACs — encoded as both ACs and TDD tests (T-X3 / T-X4).
- AC-R7's `confidence_impact` was typed `Literal["high", "medium", "low"]` but the inversion-versus-standard-confidence semantics were enforceable only by docstring. Introduced module-level `_Confidence` + `_ConfidenceImpact` distinct aliases so `mypy --strict` catches a mixing typo.
- T-R3 ("no `def _load_grammar`") was the wrong-shaped assertion — `_load_grammar` doesn't exist anywhere, so the assertion is trivially true and would not catch a regression. Rewrote to the load-bearing checks: no `GrammarLoadRefused` redeclaration, no direct `Path("tools/grammars.lock")` read, no `import blake3`, kernel import present.
- T-G7 ("no `if generator==`") was bypassable with `in {"foo", "bar"}` — rewrote to AST-walk all `Compare` nodes outside the constant declaration.
- The rule-of-three opportunity on `_get_language(lock, language) -> tree_sitter.Language` (S4-04 + S4-06 = two consumers) was not surfaced. Added a Notes-for-implementer guardrail naming the future extraction path (`codegenie.grammars.loader.language_for`) but explicitly forbidding pre-extraction (Rule 2 + CLAUDE.md "Extension by addition" without premature kernels).

After hardening, every AC is verifiable against the master surface (`base.py`, `registry.py`, `node_build_system.py`, `scip_index.py`, `grammars/lock.py`, `parsers/jsonc.py`, `index_health.py`), the kernel-chokepoint discipline is mechanically guaranteed (AST-walk tests), determinism is encoded as a property (AC-X9 / T-X3), and the extension-by-addition stance for future generator markers, reflection patterns, and indexable-file consumers is preserved through the registries (data tuples / dicts) rather than around them.

## Process note

This validation ran as an in-process synthesis rather than four parallel critic subagents — matching the S4-05 precedent. Rationale: by the time the four critics would have spawned, the main pass had already loaded the full architectural context (story, phase-arch-design.md, ADR-0002, ADR-0003, ADR-0007, S4-04 hardened story, S4-05 validation, S4-01 hardened story, S4-03 production code, `base.py`, `registry.py`, `grammars/lock.py`, `node_build_system.py`, `scip_index.py`, `index_health.py`, `parsers/jsonc.py`, `language_detection.py`). Each parallel critic would have re-loaded 1000+ lines without adding signal beyond what synthesis covered. The four lenses (coverage, test-quality, consistency, design-patterns) were applied serially below; findings carry the same severity / fix-or-NEEDS-RESEARCH tagging.

## Context Brief

**What the story promises:**

1. Three Layer-B marker probes, each ≤ 100 SLOC, each independently testable.
2. Data-driven detection (Open/Closed at the file boundary — adding a generator marker is a tuple insertion).
3. Honest typed confidence (`"medium"` for marker-absent, `"low"` reserved for hard errors).
4. Shared `_count_indexable_files` between SCIP probe and `SemanticIndexMetaProbe` (mechanically forbidden to diverge).
5. `NodeReflectionProbe` uses the same grammar-pin discipline as `TreeSitterImportGraphProbe`.

**What the phase's exit criteria demand:**

- Layer B emits structural evidence for Phase 3 adapters (phase-arch §"Goals" G1).
- Marker probes are language-agnostic in shape (data-driven catalogs).
- Adding a new generator marker / reflection pattern requires **zero edits** to detection logic (CLAUDE.md "Extension by addition").
- `phase-arch-design.md` lists `generated_code.py`, `node_reflection.py`, `semantic_index_meta.py` in `layer_b/` — this story is the deliverable for that listing.

**What the arch + ADRs constrain:**

- **Probe ABC** at [`src/codegenie/probes/base.py:74-96`](../../../../src/codegenie/probes/base.py): two-arg `async def run(self, repo: RepoSnapshot, ctx: ProbeContext)`; only `parsed_manifest`, `input_snapshot`, `image_digest_resolver` are admitted on `ProbeContext` (frozen by Phase 0 ADR-0007 + Phase 2 ADR-0004).
- **S4-03 kernel** at [`src/codegenie/grammars/lock.py`](../../../../src/codegenie/grammars/lock.py): `load_and_verify(repo_root) -> GrammarLockFile`, `GrammarLoadRefused`, `GrammarPin(language, version, file, blake3)`, `GrammarLockFile(schema_version=Literal[1], grammars=list[GrammarPin])` — frozen + extra=forbid.
- **S4-03 indexable walker** at [`scip_index.py:101-170`](../../../../src/codegenie/probes/layer_b/scip_index.py): `_INDEXABLE_SUFFIXES = frozenset({".ts", ".tsx"})`, `_EXCLUDE_DIRS = frozenset({"node_modules", "dist", "build", ".git"})`, `_walk_indexable_files`, `_count_indexable_files`.
- **`parsers.jsonc.load`** at [`jsonc.py:125`](../../../../src/codegenie/parsers/jsonc.py): `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`; raises `SizeCapExceeded`, `MalformedJSONError`, `DepthCapExceeded`, `SymlinkRefusedError`.
- **`ctx.parsed_manifest`** at [`parsed_manifest_memo.py:67-119`](../../../../src/codegenie/coordinator/parsed_manifest_memo.py): allowlists `package.json` by default; exposed on `ProbeContext` as `Callable[[Path], Mapping[str, Any] | None] | None`. Falls back to `safe_json.load` per [`language_detection.py:330-340`](../../../../src/codegenie/probes/language_detection.py).
- **Phase 1 ADR-0007 warning IDs** — pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; import-time `for _id in _WARNING_IDS: if not _ID_PATTERN.match(_id): raise AssertionError(...)` per [`index_health.py:118-123`](../../../../src/codegenie/probes/layer_b/index_health.py).
- **`@register_probe`** at [`registry.py:241-276`](../../../../src/codegenie/probes/registry.py): `@register_probe` (no parens, defaults `heaviness="light"`, `runs_last=False`) AND `@register_probe(heaviness=..., runs_last=...)` are both valid; `default_registry.all_probes()` is the enumeration API.
- **NodeBuildSystemProbe** at [`node_build_system.py:288-290, 747-748`](../../../../src/codegenie/probes/node_build_system.py): emits `schema_slice={"build_system": ...}` with `typescript: {compiler_options_path, resolved_compiler_options} | None`; `raw_artifacts=[]` — no sibling sidecar.
- **CLAUDE.md**: "Extension by addition", "Read before you write", "Surface conflicts don't average them", "Match codebase conventions", "Three similar lines is better than premature abstraction".

## Source-of-truth verifications (grep against master + sibling stories)

| Reference in draft | Master / sibling surface | Verdict |
|---|---|---|
| AC-R2 / Impl §3: `from codegenie.probes.layer_b.tree_sitter_import_graph import _load_grammar, GrammarLoadRefused` | Real surface: `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify` (S4-03 kernel at [`grammars/lock.py:33-38`](../../../../src/codegenie/grammars/lock.py)); S4-04 module's `_get_language` is private | **PHANTOM SYMBOL** — `_load_grammar` does not exist anywhere |
| AC-M2: "reads from `build_system.typescript` slice if available" | `ProbeContext` has no `sibling_slices` field (ADR-0007 freeze); `NodeBuildSystemProbe.raw_artifacts=[]` — no `build_system.json` sidecar | **PHANTOM PATH** — mechanism does not exist |
| Notes: `build_system.typescript.resolved_compiler_options_path` | Shipped field is `compiler_options_path`; no `resolved_compiler_options_path` exists | **PHANTOM FIELD** |
| Impl outline `async def run(...)` shorthand | Frozen ABC: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` | **SIGNATURE UNDER-SPECIFIED** — would not constrain a one-arg impl |
| AC-X1: "implementer choice" of LOC counter | S4-04 precedent uses `radon raw --no-comments --no-blank` exclusively; "implementer choice" is a CI variance source | **AMBIGUITY** — pin one |
| AC-X3 marker-absent confidence is `"medium"` | OK semantically; but assertion shape needs to be `== "medium"` not `in {"medium", "low"}` | **WEAK ASSERTION SHAPE** |
| T-R3 "no `def _load_grammar`" | `_load_grammar` does not exist; assertion is trivially true and catches nothing | **WRONG-SHAPED ASSERTION** |
| T-G7 "no `if generator == "..."`" | Defeated by `in {...}` / `match` rewrites | **WEAK MUTATION SHAPE** |
| AC-R1: `heaviness="light"` | S4-04 (same per-file tree-sitter Query workload on the same glob) declares `heaviness="medium"` | **INCONSISTENT WITH SIBLING** |
| AC-M1: `requires=["node_build_system"]` | Sibling-slice access not available; topological dependency would be cosmetic only | **DEAD DEPENDENCY** |
| Out-of-scope: "canonical exclude set" includes `"out"` | S4-03's `_EXCLUDE_DIRS = frozenset({"node_modules", "dist", "build", ".git"})` — no `"out"` | **DRIFTED CONSTANT** |

## Findings by critic lens

### Coverage critic

| # | Severity | Finding |
|---|---|---|
| C-1 | block | AC-M2's "reads `build_system.typescript.resolved_compiler_options` if available" branch is mechanically unreachable. Rewrite to single-source `jsonc.load` reads. |
| C-2 | harden | No AC pinned `_REPO_ROOT` resolution for `NodeReflectionProbe` — grammars live in codewizard-sherpa, not analyzed repo. (Same finding as S4-04 AC-Resolution.) Add AC-R0. |
| C-3 | harden | No AC enforced byte-identical reruns (determinism). A list-shaped slice field with unsorted dict iteration would pass goldens (which don't land until S7-05) but break Phase 3 adapters' diff stability. Add AC-X9. |
| C-4 | harden | No AC enforced functional-core / imperative-shell separation. Without it, a future contributor mixes `Path.read_bytes()` calls into a "pure" helper. Add AC-X8. |
| C-5 | harden | AC-R5 didn't specify the fallback path when `ctx.parsed_manifest is None` — would `AttributeError` at runtime. Add `safe_json.load` fallback. |
| C-6 | harden | AC-R4 didn't pin `affected_files` to POSIX-relative paths sorted by string — would leak OS path separator differences and undefined iteration order. |
| C-7 | nit | AC-X7 golden stubs are placeholder + `pytest.skip` — fine, but the comment should reference S7-01 *and* S7-05 (story already does). |

### Test-quality critic

| # | Severity | Finding |
|---|---|---|
| T-1 | block | T-R3 ("no `def _load_grammar` in this module") is the wrong-shaped assertion since `_load_grammar` doesn't exist anywhere. Replace with: no `class GrammarLoadRefused`, no direct lock-file IO, no `import blake3`, kernel import present. |
| T-2 | block | T-R5 monkeypatches `_load_grammar` to raise — must monkeypatch `codegenie.grammars.lock.load_and_verify` (the real seam). Also strengthen to spy on `tree_sitter.Language` and assert it was never called. |
| T-3 | harden | T-G7's "no `if generator==`" branch check is bypassable. Rewrite as a derived-from-data AST walk: read `_GENERATOR_HEADER_MARKERS` from the module, derive the forbidden literal set, assert no `Compare` against any of them outside the constant. |
| T-4 | harden | T-X3 (determinism / byte-identical reruns) is missing. Add. |
| T-5 | harden | T-X4 (no I/O in pure helpers) is missing. Add. |
| T-6 | harden | Per-AC mutation companions for AC-X3 and AC-R7 were absent — assertions used permissive `in {...}` shapes. Tighten to `==` form. |
| T-7 | harden | T-M5 only asserts equal counts, not that both probes import from the shared module. Add AST-walk companion. |
| T-8 | nit | T-X2 should include a negative mutation companion verifying that a typo'd warning ID fires `AssertionError` at module import (proves bare `assert` was not used and confirms the load-bearing import-time guard isn't strip-able under `python -O`). |

### Consistency critic

| # | Severity | Finding |
|---|---|---|
| K-1 | block | All four phantom-surface findings (`_load_grammar`, `ctx.sibling_slices`, `resolved_compiler_options_path`, one-arg `run`). |
| K-2 | block | AC-R1's `heaviness="light"` for `NodeReflectionProbe` contradicts S4-04's `heaviness="medium"` for the structurally-identical per-file tree-sitter Query workload. Reclassify to `medium`. |
| K-3 | harden | "Canonical exclude set" reference in Out-of-Scope included `"out"` — drifted from the real S4-03 constant. Either correct the prose or scope `_BUILD_OUTPUT_DIRS` as a separate concept. |
| K-4 | harden | `requires=["node_build_system"]` on `SemanticIndexMetaProbe` was load-bearing only if the sibling-slice path existed. It doesn't; switch to `requires=["language_detection"]` (matches the rest of the layer_b probes). |
| K-5 | harden | `_indexable_files.py` extraction was conditional ("if a shared helper") — but AC-M4's structural-equality assertion requires it. Make mandatory. |
| K-6 | nit | The "depends on S4-04" framing was wrong — S4-06 depends on the S4-03 kernel; S4-04 is a sibling consumer of the same kernel. Corrected. |

### Design-patterns critic

| # | Severity | Finding |
|---|---|---|
| D-1 | harden | Inverted-semantics `confidence_impact` field shared its Literal alias with the standard `confidence` field, so a typo'd assignment (`slice["confidence"] = "high"` when inversion was intended) was type-checker-invisible. Introduced module-level `_Confidence` and `_ConfidenceImpact` distinct aliases. |
| D-2 | harden | The `_get_language(lock, language) -> tree_sitter.Language` rule-of-three opportunity (S4-04 + S4-06 = two consumers, third precedent in Phase 8+ Python grammar) was unsurfaced. Added a Notes-for-implementer guardrail naming the future extraction path AND explicitly forbidding pre-extraction in this story. |
| D-3 | harden | Pure-vs-impure separation was implicit (Implementation outline §2 mentioned "Pure helpers"). Elevated to AC-X8 with AST-walk enforcement (T-X4). |
| D-4 | nit | The "marker catalogs ARE registries" framing was not surfaced. Added a Notes paragraph noting that 02-ADR-0007 forbids runtime plugin loaders, so module-level `Final` tuples / dicts ARE the Phase-2 registry shape — a future `KernelRegistry[K, V]` extraction is contingent on three precedents accumulating, not on Phase-2 pre-extraction. |
| D-5 | n/a | `_BUILD_OUTPUT_DIRS` vs `_EXCLUDE_DIRS` look near-duplicate but encode different concepts (build-output detection in `GeneratedCode` vs SCIP indexable-file exclusion in `_indexable_files`). Not a rule-of-three trigger. Documented the conceptual separation in AC-M4's scope note. |

## Prescriptions applied to the story (HARDENED set)

The story was edited in place to:

1. Replace `from codegenie.probes.layer_b.tree_sitter_import_graph import _load_grammar, GrammarLoadRefused` with `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify` (AC-R2 + impl outline §3).
2. Remove the phantom "reads `build_system.typescript.resolved_compiler_options` if available" branch from AC-M2 / impl §4 / Notes; `SemanticIndexMetaProbe` always reads `tsconfig.json` directly via `jsonc.load`; honest `has_extends: true` flag + `warnings: ["semantic_index_meta.extends_chain_not_resolved"]` when `extends` is present.
3. Switch `SemanticIndexMetaProbe.requires` from `["node_build_system"]` to `["language_detection"]`.
4. Pin the two-arg `Probe.run` signature explicitly in every per-probe AC and the impl outline.
5. Add AC-R0 (`_REPO_ROOT` resolution + test) and `_REPO_ROOT: Final[Path]` module-level constant in `NodeReflectionProbe`'s impl outline.
6. Reclassify `NodeReflectionProbe` as `@register_probe(heaviness="medium")`.
7. Pin LOC tool to `radon raw --no-comments --no-blank`; remove "implementer choice."
8. Add AC-X8 (functional core / imperative shell) and AC-X9 (byte-identical determinism); add T-X3 + T-X4 to the shared TDD section.
9. Introduce module-level `_Confidence` and `_ConfidenceImpact` Literal aliases (typed-distinct).
10. Rewrite T-R3 from "no `def _load_grammar`" to the load-bearing AST assertions (no `class GrammarLoadRefused`, no direct lock-file IO, no `import blake3`, kernel import present).
11. Rewrite T-R5 to monkeypatch the kernel seam and spy on `tree_sitter.Language`.
12. Rewrite T-G7 to derive the forbidden-literal set from `_GENERATOR_HEADER_MARKERS` at test time, AST-walking all `Compare` nodes.
13. Rewrite T-M5 with AST-walk companion (`test_both_probes_import_indexable_files_kernel`).
14. Sharpen AC-X3 assertion shape (`== "medium"`, not `in {...}`) and AC-R7 (per-branch `==` assertions for inversion semantics).
15. Make `_indexable_files.py` extraction mandatory (AC-M4 step 1); confirm exclude set verbatim from S4-03.
16. Sort `affected_files` and `generated_code.files` for determinism.
17. Add `safe_json.load` fallback to AC-G2 and AC-R5 (mirrors `language_detection.py:330` pattern).
18. Pin `_BUILD_OUTPUT_DIRS` vs SCIP `_EXCLUDE_DIRS` as conceptually-separate sets in AC-M4's scope note.
19. Add a rule-of-three Notes-for-implementer guardrail for `_get_language` (extraction path documented, pre-extraction explicitly forbidden).
20. Add a design-pattern Notes paragraph explaining that module-level `Final` tuples/dicts ARE the Phase-2 registry shape under 02-ADR-0007's no-plugin-loader constraint.

## Verdict rationale

**HARDENED, not RESCUE.** Although the edit scope is substantial, the story's **goal** is unchanged (three independently-cached, ≤100-LOC marker probes via data-driven catalogs), its **AC-to-goal trace** is intact, and the architectural framing (split-not-fused; Phase 1 parser reuse; kernel-chokepoint for grammar load; shared walker for indexable counts) is consistent across the entire edit set. The phantom-surface findings are mechanical reconciliations with shipped code (`grammars/lock.py`, `base.py`, `node_build_system.py`, `scip_index.py`, `parsers/jsonc.py`) and frozen contracts (Phase 0 ADR-0007 ABC, Phase 2 ADR-0007 no-plugin-loader, Phase 2 ADR-0002 grammar-pin discipline) — not redesigns of intent. After hardening, every AC is verifiable, every TDD test has a clear pass/fail criterion, and the executor's Validator pass can mechanically check the runtime evidence for each AC.

The **one architectural choice** the validator did not auto-pick: whether `_get_language` should be pre-extracted to a shared `codegenie.grammars.loader` module **before** the third consumer appears. The Notes-for-implementer guardrail explicitly forbids pre-extraction (Rule 2 + CLAUDE.md "Extension by addition"), but a future story (e.g., S6-something or a Phase 8+ Python grammar) is free to elevate. Either path satisfies the current S4-06 contract.

## Open items for the executor

1. **AC-X7 golden stubs** — should be created as empty `*.golden.yaml` placeholder files with a `pytest.skip("golden produced in S7-05")` decorator on the corresponding tests. S7-05 lands the production goldens.
2. **`_indexable_files.py` extraction regression guard** — after the extraction, `pytest tests/unit/probes/layer_b/test_scip_index.py` must stay green. If any S4-03 test references the helpers by their old path, surface the import-fix as part of this story's surgical edits (not a separate refactor story).
3. **`tools/grammars.lock` cross-repo cache-key token** — S4-04's hardened story already accepts this as a special token in `declared_inputs`. S4-06 (`NodeReflectionProbe`) does the same. If the coordinator's snapshot system has changed in a way that rejects this token, surface back to the validator — but the current S4-04 hardened semantics treat it as accepted.
4. **`radon` availability** — confirm `radon` is in dev extras (S4-04 precedent). If absent, add as part of this story's `pyproject.toml` edit (one-line addition).
