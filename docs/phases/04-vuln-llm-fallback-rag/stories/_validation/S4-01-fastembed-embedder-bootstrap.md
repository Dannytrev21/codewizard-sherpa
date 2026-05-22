# Validation report: S4-01 — `Embedder` Protocol + `FastembedEmbedder` + `codegenie embeddings bootstrap`

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-01 ships the RAG substrate's local-CPU embedder: an `Embedder` Protocol, a single `FastembedEmbedder` adapter that runtime-refuses to start on `embeddings_model.lock` drift, and a `codegenie embeddings bootstrap` CLI that downloads pinned BGE-small weights and writes the lock. The story is detailed and well-sourced, and its goal traces cleanly to arch §Component 8, ADR-0007, and edge case #3.

Four-lens critique (Coverage / Test-Quality / Consistency / Design-Patterns) surfaced **19 findings — 3 block-tier, 12 harden, 4 nit**. The blockers were all in-place fixable, so the verdict is HARDENED, not RESCUE. The most important is a hard contradiction with the dependency story S1-01: S4-01's AC-3 asserted that `EmbeddingVector` is backed by an `np.ndarray`, but S1-01 (already HARDENED) fixes `EmbeddingVector = NewType("EmbeddingVector", tuple)` and explicitly assigns shape/dtype validation to S4-01. The other two blockers were an AC (AC-6) with no model-upgrade path — making arch edge case #3's documented upgrade workflow impossible — and an AC-7 fence whose literal wording ("no `TextEmbedding(...)` call ... only inside the CLI module") is unsatisfiable given the implementation outline constructs `TextEmbedding` inside `embedder.py.__init__`.

All 19 findings were fixed in place. The story is now ready for `phase-story-executor`.

## Findings by critic

### Coverage critic

**F3 (block) — AC-6 has no model-upgrade path.** AC-6's second-invocation logic compared the recomputed digest to the lock and exit-1'd on any difference. Arch edge case #3 names `codegenie embeddings bootstrap` as the *operator-initiated model-upgrade mechanism*; an exit-1-on-every-change CLI makes that workflow impossible. Fix: AC-6 now branches on `--model-name` vs the on-disk lock's `model_name` — same model + drifted digest → exit 1 (genuine corruption); different model → overwrite the lock + warn that `rag rebuild` must follow → exit 0.

**F5 (harden) — AC-2 negative-space gaps.** AC-2 enumerated lock-missing, model_name-mismatch, sha256-mismatch, all-good — but not "lock present, on-disk weights absent" (would raise a raw `OSError`/`FileNotFoundError`) or "lock present, malformed YAML" (would raise a raw `yaml.YAMLError`/`pydantic.ValidationError`). Both now enumerated; both map to `EmbeddingsBootstrapRequired` with typed diagnostics.

**F10 (harden) — no AC pins `embed` run-to-run determinism.** AC-5 covers `model_digest` stability; nothing pinned that `embed(t) == embed(t)`. This is the load-bearing precondition for S4-02's BLAKE3(text)-keyed cache. Added AC-12.

**F11 (harden) — no test for the `model_name`-mismatch branch.** AC-2 describes the behavior; the TDD plan only tested the sha256 branch. Added `test_embedder_refuses_on_model_name_mismatch`.

**F12 (harden) — AC-6 hash target ambiguous / too narrow.** "sha256 of on-disk weights bytes" / `sha256(open(weights_path,'rb').read())` assumes a single file. BGE-small's fastembed cache is a directory (`model.onnx` + `tokenizer.json` + `tokenizer_config.json` + `config.json` + `special_tokens_map.json`); a tokenizer-config change shifts the vector space and would slip past a single-file hash. AC-6 now specifies a directory digest over every file sorted by relative path.

**F17 (nit) — `embed_batch([])` unspecified.** Folded into AC-4 (returns `[]`) + a test.

### Test-Quality critic

**F2 (harden) — AC-4 demands "bit-identical".** ONNX batched inference (`session.embed(texts)`, len > 1) is not guaranteed bit-identical to singleton inference (`session.embed([text])`) — different tensor shapes select different kernels / accumulation orders, the same 5th-decimal effect ADR-0008's band absorbs. "Bit-identical" is a flaky/unsatisfiable assertion. AC-4 relaxed to a tolerance assertion (`cosine ≥ 1 - 1e-6`, per-component `abs ≤ 1e-5`) that encodes the real intent — batching is a perf optimization, never a semantic change. The exact-equality property is preserved where it *is* guaranteed — singleton run-to-run determinism — as the new AC-12.

**F8 (harden) — idempotence test uses mtime.** `test_bootstrap_cli_idempotent` asserted "lock-file mtime unchanged"; coarse filesystem mtime granularity makes this both flaky and weak (two fast writes can share an mtime tick). Rewrote: assert lock bytes are byte-identical before/after AND the patched `_seam_write_lock` is not called on the no-op run — which forces the CLI to expose a write seam (a `cli.py`-style `_seam_*`), itself a testability improvement.

**F18 (harden) — sha256-drift red test exercises the wrong branch.** The red test `test_..._on_sha256_drift` wrote only the lock, no weights. Under the corrected (F5) branch logic, "lock present, weights absent" raises `EmbeddingsBootstrapRequired`, not `EmbeddingModelMismatch` — so the test as written would fail or test the wrong path. Rewrote it to set up a synthetic on-disk weights directory (≥ 2 files), matching implementation-outline step 9's stated intent, and added the `cache_dir` test seam to `FastembedEmbedder` so the digest check is injectable.

### Consistency critic

**F1 (block) — AC-3 contradicts S1-01 AC-2.** AC-3 asserted `embed(...)` returns an `EmbeddingVector` "whose underlying `np.ndarray` has `shape == (384,)` and `dtype == np.float32`". S1-01 (HARDENED) AC-2 fixes `EmbeddingVector = NewType("EmbeddingVector", tuple)` over the bare `tuple` — numpy is deliberately kept out of `codegenie.types` — and S1-01 AC-4 explicitly assigns shape/dtype validation to S4-01. Passing an `np.ndarray` where the `NewType`'s `tuple` base is expected also fails AC-11 `mypy --strict`. Rewrote AC-3 to assert a 384-element tuple of Python floats, L2-normalized; numpy is used inside `embedder.py` but converted to a tuple before the return boundary.

**F4 (block) — AC-7 fence wording is unsatisfiable.** AC-7 said `test_no_embedder_download_outside_cli.py` "asserts no top-level `TextEmbedding(...)` call ... only inside the CLI module." But the implementation outline constructs `TextEmbedding` inside `embedder.py.__init__` (after lock verification). The fence as worded can never pass. Reworked AC-7 into (a) a behavioral spy test (runtime path never downloads) + (b) a structural AST test that asserts *ordering* — `_verify_lock_or_raise` precedes the `TextEmbedding` call, and there is no module-scope `TextEmbedding` call.

**F6 (harden) — stale CLI path.** Files-to-touch and Notes §8 named `src/codegenie/cli/__init__.py`. The CLI is a single module, `src/codegenie/cli.py` — there is no `cli/` package. Corrected both, and named the `vuln-index` deferred-`importlib.import_module` precedent as the wiring pattern.

**F7 (harden) — `pyproject.toml` omitted from Files-to-touch.** The story marks `fastembed`-dependent tests `@pytest.mark.fastembed`, but that marker is not registered (`pyproject.toml` registers only `bench`/`adv`/`phase02_adv`/`serial`/`nightly_macos`/`phase_7_preview`). Notes §6 also calls for a `fastembed.*` mypy override. Both edit `pyproject.toml`; added the row.

**F15 (nit) — runbook filename.** Story uses `docs/operations/embeddings.md`; ADR-0007 §Consequences says `docs/operations/bootstrap.md`. Added Notes §11: keep `embeddings.md`, reconcile the ADR reference at S7-10.

**F19 (nit) — `Depends on` misattribution.** The header credited S1-04 with the `BlobDigest`/`ModelId`/`EmbeddingVector` newtypes; those are S1-01's (`codegenie.types.identifiers`). S1-04 ships the `rag/models.py` Pydantic models, which this story does not use. Corrected the `Depends on` line to S1-01 / S1-05 / S1-06.

### Design-Patterns critic

**F13 (harden) — primitive obsession on `model_name`.** `_EmbeddingsModelLock.model_name` and the ctor `model_name` were raw `str`. `ModelId` (newtype) + `parse_model_id` (smart constructor) already exist (S1-01), and `SolvedExample.embedding_model` is already typed `ModelId` (S1-04). Using `str` here is inconsistent with the second established consumer — and the story header even lists `ModelId` as a dependency. Implementation outline steps 3–4 + AC-2 now type it `ModelId`.

**F14 (harden) — `EmbeddingModelMismatch` overloaded across two raise-sites.** The error is raised both for "lock model_name ≠ ctor model_name" and "on-disk digest ≠ lock digest"; `expected`/`found` carry model-name strings in one case and 64-hex digests in the other, with no way for an operator or test to tell which. Added a `kind: Literal["model_name", "sha256"]` discriminator (make-illegal-states-distinguishable; tagged-union discipline). AC-8 + the red test now assert on `kind`.

**F9 (harden) — AC-9 Protocol fence uses `dir()` alone.** AC-9 said it mirrors `test_plugin_protocol_frozen.py`, but that precedent's docstring explicitly warns against `dir()`-only and unions `dir()` with `__annotations__` (a `typing.Protocol` does not surface attribute-only members through `dir()`). For `Embedder`'s three current methods `dir()` happens to suffice, but the fence would silently miss a future attribute-only member. AC-9 now unions `__annotations__`, faithfully mirroring the precedent.

**F16 (nit) — `model_digest()` described as "pure".** It returns frozen instance state set in `__init__` — idempotent, not side-effect-free. AC-1 reworded to "idempotent".

### Functional-core / extension-by-addition observations (no edit — already sound)

The story already prescribes the right shape: a `_verify_lock_or_raise` pure-ish kernel reused by both the runtime path and the CLI; an `Embedder` Protocol consumed by S4-02's `CachedEmbedder` decorator (so the Protocol earns its keep — the `model_digest()` cache-key contract, ADR-0007 §Pattern fit); and a single in-tree adapter with future Voyage/Cohere adapters landing behind the same port (additive). The added `_finalize(arr) -> EmbeddingVector` helper (impl step 6) closes the one duplication risk — `embed` and `embed_batch` would otherwise each re-implement cast/normalize/wrap.

## Research briefs

No `NEEDS RESEARCH` finding required an external lookup. Two questions were resolved from domain knowledge and recorded inline:

- **ONNX batch determinism (AC-4).** ONNX Runtime inference is deterministic *run-to-run for a fixed input shape*, but batched (N > 1) vs singleton (N = 1) execution runs a different-shaped computation graph — kernel selection and float accumulation order can differ. There is no fastembed/ONNX guarantee of batch-invariance. Hence AC-4 → tolerance, AC-12 → exact (singleton only).
- **fastembed cache layout (AC-6).** A fastembed-cached BGE-small model is a *directory* (ONNX file + tokenizer + config JSONs), not one file. A robust drift guard must digest every file. AC-6 → directory digest. The AC is written filename-agnostically ("every regular file ... sorted by relative path") so it holds whether the ONNX file is `model.onnx` or `model_optimized.onnx`.

## Conflict resolutions

No critic-vs-critic conflicts. One ordering note: F1 (Consistency — `EmbeddingVector` is a `tuple`) and F2 (Test-Quality — AC-4 tolerance) interact — both touch AC-4's comparison. Resolved coherently: AC-4 now compares tuples element-wise within tolerance, and the exact-equality property migrates to AC-12 (singleton determinism, where it is genuinely guaranteed). Consistency (F1) set the type; Test-Quality (F2) set the comparison.

## Edits applied

1. **Header** — `Status: Ready → HARDENED`; `Depends on` corrected to S1-01/S1-05/S1-06 (F19); inserted the `Validation notes` block.
2. **AC-1** — "pure" → "idempotent" (F16).
3. **AC-2** — added the corrupt-lock and weights-absent branches; `model_name: ModelId`; `cache_dir` test seam; `kind` discriminator on `EmbeddingModelMismatch` (F5, F13, F14, F18).
4. **AC-3** — `EmbeddingVector` is a 384-element tuple of floats, not an `np.ndarray` (F1 — block).
5. **AC-4** — "bit-identical" → tolerance assertion; `embed_batch([])` (F2, F17).
6. **AC-6** — directory digest; explicit model-upgrade path; no-op does not rewrite the lock (F3 — block, F12).
7. **AC-7** — behavioral spy test + ordering-based structural fence; removed the unsatisfiable "only inside the CLI module" claim (F4 — block).
8. **AC-8** — `EmbeddingModelMismatch.kind` discriminator; `EmbeddingsBootstrapRequired` three-condition list (F14, F5).
9. **AC-9** — `dir() | __annotations__` (F9).
10. **AC-12 added** — `embed` run-to-run determinism (F10).
11. **Implementation outline** — steps 3–9 rewritten: `ModelId`-typed lock; explicit `__init__` sequence; tuple conversion in `embed`/`embed_batch` + shared `_finalize`; CLI deferred-import wiring + `_seam_write_lock`; `fastembed` marker registration.
12. **TDD plan** — sha256-drift red test sets up synthetic weights (F18); follow-on tests reworked — added determinism, batch-tolerance, empty-batch, model-name-mismatch, weights-absent, corrupt-lock, runtime-no-download, model-upgrade, same-model-drift; idempotence test uses byte-equality + patched seam (F8).
13. **Files to touch** — `src/codegenie/cli.py` (was `cli/__init__.py`); added `pyproject.toml` (F6, F7).
14. **Notes for the implementer** — §8 path corrected; added §9 (`EmbeddingVector` is a tuple), §10 (upgrade vs drift), §11 (runbook filename).

## Verdict rationale

HARDENED. The story's goal, scope, and structure are sound and trace cleanly to arch §Component 8 + ADR-0007 + edge case #3 — no RESCUE condition. All 19 findings, including the 3 blockers, were fixable in place without touching the goal: a type correction (AC-3), an AC behavior gap (AC-6), and a self-contradictory fence (AC-7), plus twelve hardens and four nits. The blockers were genuine (AC-3 contradicted a HARDENED dependency; AC-6 contradicted a documented operator workflow; AC-7 was unsatisfiable) but localized.

## Recommended next step

`phase-story-executor` to implement S4-01. The executor should pay special attention to: (1) `EmbeddingVector` is a `tuple` newtype — numpy must not cross `embedder.py`'s return boundary; (2) the lock-verification must precede session construction so the runtime path provably never downloads; (3) the bootstrap CLI's model-upgrade branch is load-bearing for arch edge case #3.
