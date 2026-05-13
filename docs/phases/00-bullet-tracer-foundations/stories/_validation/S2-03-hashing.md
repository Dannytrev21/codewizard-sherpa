# Validation report — S2-03 Hashing module (BLAKE3 + SHA-256 chokepoint)

**Validated:** 2026-05-13
**Verdict:** **HARDENED**
**Validator skill version:** phase-story-validator

## Verdict summary

The story's Goal, scope, and choice of two algorithms tied to ADR-0001 are sound. But the original AC set was vulnerable to a "return a constant of the right shape" stub mutant — three of the four anchor tests would have passed against an implementation that returned `"blake3:" + "0"*64` or equivalent. Several load-bearing semantics named in the implementer notes (the manifest-vs-content distinction, the `\x1f`/`\x1e` separator threat model, the chunk-streaming correctness) had no AC pressure. One Out-of-scope claim — that S1-04's `forbidden-patterns` hook enforces the `blake3`/`hashlib.sha256` chokepoint discipline — was factually wrong (verified against [S1-04](../S1-04-precommit-editorconfig-mkdocs.md)).

All issues are surgical fixes. No goal or scope change required; the story is now safe to hand to the phase-story-executor.

**The hardening expanded:**
- **AC count:** 7 → 14. Original ACs preserved (renumbered) and split where they bundled multiple verifiable claims.
- **TDD plan:** 4 anchor tests → 13 tests in three tiers (anchor, mutation-killer, edge-case).
- **Implementation outline:** clarified the arity-witness requirement for `identity_hash` (AC-11), the dual-lazy-import requirement (AC-3 — `content_hash_of_inputs` is a peer public function), and the manual-grep gate (AC-13).
- **Out-of-scope** corrected re: S1-04.

## Stage 1 — Context Brief

### Story snapshot
- **Goal (verbatim, pre-edit):** "`from codegenie.hashing import content_hash, identity_hash, content_hash_of_inputs` succeeds; both `content_hash(some_path)` and `identity_hash("a","b")` return prefix-tagged hex strings (`"blake3:<64-hex>"` / `"sha256:<64-hex>"`) that are deterministic across runs, and `content_hash_of_inputs([p1, p2])` produces the same hash as `content_hash_of_inputs([p2, p1])` (sort-stable)."
- **Non-goals:** `CacheStore.key_for` integration (S3-01); `blob_sha256` (S3-06); schema versions (S3-01); AST-scan chokepoint enforcement (Phase 1 deferral); HMAC over cache contents (Phase 14).

### Source-of-truth artifacts loaded
- `docs/phases/00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md` (full).
- `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md` §Component design — Hashing (~line 504), CacheStore (~line 490), Tradeoffs row (~line 924), Stable contracts line (~line 271).
- `docs/phases/00-bullet-tracer-foundations/final-design.md` §2.7, §L3 row 1.
- `docs/phases/00-bullet-tracer-foundations/High-level-impl.md` Step 2.
- `docs/phases/00-bullet-tracer-foundations/stories/S1-04-precommit-editorconfig-mkdocs.md` (full AC-2 — to verify the chokepoint-enforcement claim).
- `docs/phases/00-bullet-tracer-foundations/stories/S3-06-audit-writer-verify.md` (to verify cross-story compatibility of `identity_hash`'s signature with the `blob_sha256` use site).
- `docs/localv2.md` §8 (SHA-256 specification for cache keys).
- `tests/unit/test_errors.py` and `tests/unit/test_logging.py` (idiomatic style reference).

### Goal-to-AC trace (pre-edit)
- AC-1 (public surface) → Goal: YES.
- AC-2 (prefix + length) → Goal: YES, but the Goal said "deterministic across runs" without naming a verifiable boundary; AC-2 covers the boundary.
- AC-3 (lazy import) → Goal: NO (orphan — not named in the Goal; load-bearing per phase-arch-design + implementer-notes cold-start argument).
- AC-4 (sort-stability) → Goal: YES.
- AC-5 (chokepoint discipline) → Goal: NO (orphan — but ADR-0001 §Decision names this as a core consequence).
- AC-6 (test file existence) → Goal: META, not a behavior.
- AC-7 (gates clean) → Goal: META.

**Conclusion:** AC-3, AC-5 were orphans in the goal-trace despite being load-bearing. Hardening widens the Goal so every AC traces.

### Open ambiguities (resolved before Stage 2)
- **Empty-input behavior** for `content_hash_of_inputs([])` and `identity_hash()` — not in Goal or ACs, not in implementer notes. Resolved in editing: both must be legal, deterministic, and distinct from a one-empty-part case (AC-11).
- **Lowercase-hex contract** — phrased in AC-2 but not pinned by tests. Resolved: regex `[0-9a-f]{64}` and `digest.islower()` assertion (AC-2 + lowercase test).
- **Cross-story consistency with S3-06** — does `identity_hash(*parts: str)` work for S3-06's `blob_sha256` use? Verified: S3-06 canonicalizes to JSON string first (`json.dumps(..., sort_keys=True, separators=(",", ":"))`) and passes the resulting `str` to `identity_hash`. Signature is compatible; no fourth public function needed.

## Stage 2 — Critic findings

Three independent subagents ran in parallel. Each consumed the story plus its lens-specific reads. Summaries below; verbatim outputs retained.

### Coverage critic (11 findings, 3 block)
- **Block:** AC-6 + the four anchor tests are tautological under mutation thinking — a `return "blake3:" + "0"*64` stub passes determinism + prefix + length on tiny inputs.
- **Block:** No AC pins the manifest-vs-content semantic for `content_hash_of_inputs`. A naive "BLAKE3 over file contents" implementation passes sort-stability.
- **Block:** No AC covers large-file streaming correctness; all test fixtures are <20 bytes; a `read()`-whole-file mutant ships green.
- **Hardens (7):** chokepoint discipline (AC-5) is a meta-AC with an explicit escape hatch; lazy-import test is order-sensitive in a shared pytest process; no separator-collision invariant test; `content_hash_of_inputs([])` undefined; `identity_hash()` zero-args undefined; `FileNotFoundError` propagation untested; path normalization unspecified.
- **Nit (1):** AC-2 says "literal prefix" but tests only `startswith` + length — tighten to `re.fullmatch`.

### Test-Quality critic (12 findings, 4 block)
- **Block:** No known-vector tests; `return "blake3:" + "0"*64` and `return "sha256:" + "0"*64` pass all four anchor tests.
- **Block:** No negative/distinguishability tests; hash-everything-to-zero mutant survives.
- **Block:** Separator-collision invariant untested; a mutant using `|` passes.
- **Block:** Manifest-vs-content semantics untested; a mutant hashing file bytes passes sort-stability.
- **Hardens (7):** chunk-boundary correctness untested; lazy-import test only proves import path, not call path; lowercase-hex unenforced; `__all__` closure untested; empty-input behavior not pinned; `FileNotFoundError` propagation untested; sort-stability test paths have distinct sizes so a sort-by-size-only mutant survives.
- **Nit (1):** chokepoint AST test deferred — given S2-04 ships an analogous `test_no_shell_true.py`, consider promoting to in-scope (declined; deferred remains consistent with story's explicit Phase 1 boundary).

### Consistency critic (9 findings, 2 block)
- **Block:** Out-of-scope falsely claims S1-04's `forbidden-patterns` hook enforces the chokepoint. Verified against S1-04 AC-2 — the 11 banned patterns are `print(`, `yaml.load(` without `Loader=`, `shell=True`, `subprocess.run(...,shell=...)`, `yaml.Dumper`, `os.system(`, `os.popen(`, `pickle.loads(`, `eval(`, `exec(`, `__import__(`. **No `blake3` or `hashlib.sha256` ban exists.** Story text must be corrected.
- **Block:** `identity_hash(*parts: str)` signature potentially collides with S3-06's planned use as a blob-bytes hasher. Verified in S3-06 line 62: S3-06 calls `_blob_sha256` which JSON-serializes to a `str` first via `json.dumps(..., sort_keys=True, separators=(",", ":"))` and then routes through `identity_hash`. Signature works as-is; **resolved as non-issue but documented in the Validation notes**.
- **Hardens (4):** AC-3 lazy-import scope ambiguous for `content_hash_of_inputs` (peer public function, not a helper); AC-2 lowercase claim not tested; AC-5 chokepoint discipline not in Goal (orphan); manifest-vs-content distinction missing from ACs.
- **Nits (3):** cold-start phrasing duplicated across References and Implementer notes; `mypy --strict` per-file vs package scope; CLAUDE.md determinism/honest-confidence not explicitly cross-referenced.

### Conflict resolution
- Coverage F2, Test-Quality F4, Consistency F6 all converge on the manifest-vs-content semantic — merged into AC-6 + two tests (mutation + size-changes).
- Coverage F1, Test-Quality F1+F2 all converge on the "constant stub passes" problem — merged into AC-8 (distinguishability) + AC-9 (known vectors).
- Coverage F5, Test-Quality F6 both flag lazy-import test fragility — merged into the `subprocess.run`-based fresh-interpreter test (AC-4) which dominates both critiques.
- No conflicts that required source-of-truth arbitration.

## Stage 3 — Researcher

Not invoked. No critic finding was tagged `NEEDS RESEARCH`. Each proposed fix was either a direct test/AC addition or a verification against an existing source-of-truth document (S1-04, S3-06, phase-arch-design.md), all of which the Consistency critic resolved inline.

## Stage 4 — Edits applied

All edits made directly to [`S2-03-hashing.md`](../S2-03-hashing.md). Below is a summary of each change; the diff is recoverable from git.

### Header
- `**Status:**` updated from `Ready` to `Ready (Validated 2026-05-13 — HARDENED)`.
- Added a `## Validation notes (2026-05-13)` block immediately after the header with the headline changes and the S1-04 / S3-06 cross-checks.

### Goal
**Before** (one sentence about deterministic prefix-tagged hex + sort-stability).
**After** widens to include:
1. Explicit regex bound (`^(blake3|sha256):[0-9a-f]{64}$`).
2. Manifest-vs-content semantic for `content_hash_of_inputs`.
3. The chokepoint discipline ("the only file in `src/codegenie/` that imports `blake3` or `hashlib.sha256`") — so AC-13 traces to the Goal.

### Acceptance criteria
| Pre-edit | Post-edit | Source(s) |
|---|---|---|
| AC-1: three public functions + `__all__` | AC-1 (unchanged in intent, signature shown verbatim with arg types) | original |
| AC-2: "literal prefix `blake3:`" + 64 hex chars | AC-2 (rewritten as regex `^(blake3\|sha256):[0-9a-f]{64}$` + `islower()` assertion) | Coverage F11, Test-Quality F7, Consistency F4 |
| AC-3: lazy `blake3` inside `content_hash` (and any helper) | AC-3 (expanded to name `content_hash_of_inputs` explicitly) | Consistency F3 |
| (none) | AC-4 (call-time activation half — pins both halves of the lazy contract) | Test-Quality F6 |
| AC-4: sort-stability on `(path, size)` | AC-5 (renumbered; expanded to require three test cases — distinct sizes, equal sizes, three-element permutation) | Test-Quality F11 |
| (none) | AC-6 (manifest-vs-content semantics — explicit) | Coverage F2, Test-Quality F4, Consistency F6 |
| (none) | AC-7 (separator-collision resistance — behavioral invariant) | Coverage F6, Test-Quality F3 |
| (none) | AC-8 (distinguishability — different inputs → different hashes) | Coverage F1, Test-Quality F2 |
| (none) | AC-9 (known-vector pins — kills constant-return mutant) | Coverage F1, Test-Quality F1 |
| (none) | AC-10 (streaming chunk-boundary correctness with >128KB fixture) | Coverage F3, Test-Quality F5 |
| (none) | AC-11 (empty-input behavior pinned, including `identity_hash()` ≠ `identity_hash("")`) | Coverage F7+F8, Test-Quality F9 |
| (none) | AC-12 (`FileNotFoundError` propagation) | Coverage F9, Test-Quality F10 |
| AC-5: chokepoint discipline | AC-13 (rewritten — code-review-only in Phase 0; AST test deferred to Phase 1; explicit manual `git grep` gate) | Coverage F4, Consistency F1 |
| AC-6: tests assert determinism, prefix, sort-stability, sys.modules | folded into AC-2, AC-4, AC-5, AC-9 (the meta-AC dissolved into concrete behaviors) | tautology fix |
| AC-7: ruff/mypy/pytest clean | AC-14 (renumbered; mypy widened to package scope per Consistency Nit) | minor |

### TDD plan
Replaced the four-test sketch with a 13-test plan organized into:
- **Tier 1 — anchor tests:** `__all__` closure, prefix regex, lazy-import (fresh interpreter via `subprocess.run`).
- **Tier 2 — mutation-killers:** known-vectors, distinguishability, separator-collision resistance, sort-stability (three cases), manifest-vs-content, chunk-boundary streaming.
- **Tier 3 — edge cases:** empty manifest, zero-parts vs one-empty-part distinctness, `FileNotFoundError` propagation.

Every test has a docstring naming the AC it pins and (for mutation-killers) the specific mutant it kills.

### Implementation outline
- Step 5 (the `content_hash_of_inputs` step) now explicitly notes the **lazy-import requirement** for this peer public BLAKE3 function (was implied; now stated).
- Step 3 (the `identity_hash` step) adds a paragraph on the **arity-witness scheme** required to satisfy AC-11 (`identity_hash()` ≠ `identity_hash("")`); leaves the encoding choice to the implementer.
- Step 6 adds the manual `git grep` chokepoint check.

### Out-of-scope
- The false S1-04 claim ("forbidden-patterns hook enforces this") rewritten to "code review only in Phase 0; an AST-scan analog is deferred to Phase 1" with the explicit verification result from S1-04 AC-2 quoted.
- Path canonicalization added as a deferred concern (Coverage F10).

### Implementer notes
- Two bullets added: the AC-3 dual-lazy-import requirement, and the AC-11 arity-witness rationale.
- Existing "Don't mix the two hashes" note tightened to cross-reference AC-6.

## Final verdict

**HARDENED.** The story is ready for the phase-story-executor. Mutation-resistance has been raised from "stub-passes-three-of-four-tests" to "stub-passes-zero-tests" by adding known-vector pins, distinguishability checks, manifest-vs-content semantics, separator-collision invariance, and chunk-boundary streaming correctness. The one factual error in the source (the S1-04 enforcement claim) has been corrected with a verified replacement. Cross-story consistency with S3-06 has been verified and documented. The Goal now covers every AC, and every AC has at least one mutation-resistant test.

Phase 0 chokepoint discipline note: until the Phase 1 AST analog ships, the manual `git grep -nE '^(from blake3|import blake3|from hashlib import sha256)' -- src/codegenie/ ':!src/codegenie/hashing.py'` check is the standing gate. Recommend adding to the PR template at the next opportunity.
