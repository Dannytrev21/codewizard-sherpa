# Shakedown — `codegenie rag rebuild` — 2026-05-25T17:00:00Z

**Capability:** `codegenie rag rebuild [--reembed]` (Phase-4 S4-07 operational-recovery CLI)
**Sample app:** a hermetic seeded RAG root under `/tmp/rag-shakedown/rag/` — three `SolvedExample` records built with `tests/fixtures/rag/fake_solved_example.make_solved_example` and laid down via the canonical `ChromaPersistentStore.add` path (the same write path the production harvest pipeline takes). The Phase-4 `rag rebuild` capability does not operate on a source-code sample app — it operates on a `.codegenie/rag/` substrate — so a seeded RAG root is the right "sample" shape.
**Operator context:** post-S4-08 follow-up. The last shakedown was `codegenie gather`; the rag rebuild CLI shipped GREEN in S4-07 but only against integration tests that monkeypatched the embedder seam. This run exercised the real `FastembedEmbedder` lookup path end-to-end with a non-default `--root` — the documented runbook workflow — and surfaced two latent regressions.
**Mode:** default (skill fixed both findings + closed the test gap that allowed them through).
**Wall-clock:** ~25 minutes (seed → run → diagnose → red-test → fix → green → live-rerun → docs sweep → report).
**Outcome:** 🟢 **two real codebase bugs found and fixed.** End-to-end operator workflow from `docs/operations/rag.md` now works against a non-default `--root`, AND a failed `--reembed` preflight preserves the entire store instead of half-deleting it.

## Stage 0 — Environment doctor

`.venv/bin/ruff` 0.15.13, `mypy` 2.1.0, `pytest` 9.0.3, `make`, `git` all resolve.
The repo idiom is `.venv/bin/<tool>` (no global PATH install) — acceptable; not a finding.

Pre-existing local-only state (NOT in CI, NOT introduced by this shakedown):
- `src/codegenie/types/parsers.py` carries an uncommitted modification with a 101-char line (Phase-6 S1-01 work-in-progress on the local tree)
- `src/codegenie/workflows/`, `tests/unit/workflows/`, `tests/integration/test_phase6_sut_contract_snapshot*.py`, `tests/fence/test_workflows_public_surface.py` are untracked scratch from earlier Phase-6 work
- `lint-imports` is only on `.venv/bin/PATH` so the canary self-tests at `tests/unit/test_lint_imports_canary.py` fail locally; CI runs `make lint-imports` which uses the venv-scoped binary and is unaffected
- `pre-commit`'s cassette-lock hook fails locally with `Executable 'python' not found` (PATH-resolution artifact); the hook is fine inside CI which sets `PATH` to include the venv

All of the above predate this run. They are surfaced loudly here per Rule 12 ("Fail loud") rather than buried — the shakedown's own changes are clean on every gate that was actually runnable.

## Stage 1 — Capability spec

`codegenie rag rebuild [--root <path>] [--reembed]` walks `<root>/manifest.yaml` + `<root>/records/*.yaml`, wipes `<root>/chroma/`, and reconstructs the chromadb derived index. Documented exit codes (per `--help` and `docs/operations/rag.md`): 0 success / 1 YAML parse error or chromadb write failure or rmtree refused / 2 manifest missing.

`--reembed` re-derives each record's `query_text` projection and re-embeds via the current `FastembedEmbedder` — used after `codegenie embeddings bootstrap` applies a model upgrade.

Most recent prior shakedown reports: `codegenie-gather-2026-05-25T185701Z.md`, `codegenie-gather-2026-05-24T213722Z.md`, `codegenie-cassette-rebuild-lockfile-2026-05-25T055801Z.md`. None covered `codegenie rag rebuild`; this is the first shakedown of that capability.

## Stage 2 — Sample-app shape

The capability's input shape is a `.codegenie/rag/` directory containing `manifest.yaml` + `records/*.yaml`. A seeded hermetic root under `/tmp/rag-shakedown/rag/` was built via the canonical `ChromaPersistentStore.add` write path with three records (CVE-2026-1111/2222/3333) — the same write path the in-pipeline harvest uses. The seed script (`/tmp/rag-shakedown/seed.py`) imports the test fixture factory directly so the records have the same shape as in any other integration test.

## Stage 3 — Runs

Five back-to-back invocations from `/tmp/rag-shakedown/`:

1. **Default mode, happy path.** `codegenie rag rebuild --root ./rag` — exit 0, `rebuild.completed digest=bf25608887b193…` matches the seeded digest byte-identically. Pre-seeded `_pre_rebuild_sentinel` under `chroma/` correctly wiped (AC-4 rmtree).
2. **Default mode, idempotent re-run.** Same command, exit 0, same digest.
3. **Manifest missing, exit 2.** `rag rebuild --root /tmp/rag-shakedown/empty` → exit 2, stderr names `docs/operations/rag.md`.
4. **Corrupt YAML, exit 1, store intact.** Wrote `\xff\xff malformed` into one record YAML, seeded chroma sentinel, ran rebuild → exit 1, stderr named the offending file verbatim, sentinel survived (AC-8 transactional dry-run pass).
5. **`--reembed` happy path with custom root (the documented workflow).** `embeddings bootstrap --lock-path ./rag/embeddings_model.lock --cache-dir ./rag/fastembed-cache` then `rag rebuild --root ./rag --reembed`. **🔴 Initial run: failed with `EmbeddingsBootstrapRequired: ... lock file missing at .codegenie/rag/embeddings_model.lock` — the lock was at `./rag/embeddings_model.lock` (where the operator put it per the runbook), but the embedder ignored `--root` and looked at the cwd-relative default.** That was Finding F1. State of the store after this failed run was *also* concerning — chroma/ was wiped and manifest.yaml deleted before the embedder ran. That was Finding F2.

## Stage 4 — Findings

| ID | Finding | Source | Severity |
|---|---|---|---|
| F1 | `--reembed` ignores `--root` for the embeddings-lock + weights-cache lookup. Embedder construction (`_seam_build_reembed_embedder(root)` at `src/codegenie/rag/cli.py:289`) called `FastembedEmbedder()` with no args, falling back to `_DEFAULT_LOCK_PATH=.codegenie/rag/embeddings_model.lock` (cwd-relative). Operator workflow from `docs/operations/rag.md` broke when the substrate lived outside the default root. | live run #5 + code read | **high** — breaks documented operator workflow |
| F2 | `--reembed` preflight failure leaves the store corrupted: `chroma/` rmtree'd + `manifest.yaml` unlinked *before* the embedder is constructed. On any embedder-build failure (F1, network outage, drift, missing lock), the operator was left with only `records/` intact — chroma + manifest both gone, requiring manual rebuild surgery. Violates the runbook's "transactional at the directory level" promise. | live run #5 file-system inspection + code read at `src/codegenie/rag/cli.py:418-441` | **high** — silent data corruption on a documented failure path |
| F3 | Test gap: `tests/integration/test_phase4_rag_rebuild_idempotent.py::test_rag_rebuild_reembed_updates_model_and_vectors` monkeypatches `_seam_build_reembed_embedder` with a fake. This is the right strategy for the AC-6 vector-content assertions, but it left the real `FastembedEmbedder()` lookup path with no integration coverage. F1 + F2 shipped GREEN through S4-07 because no test ever exercised the real lookup against a non-default `--root`. | test-suite review | **high** — root cause of F1+F2 reaching master |

## Stage 5 — Diagnosis

F1 — codebase-bug. Cause is a one-line omission in the seam constructor.
F2 — codebase-bug. Cause is the rebuild flow ordering destructive ops before all preflights.
F3 — test-gap. Closed by the new integration test below.

## Stage 6 — Fix

**Test-first (Rule 9).** New file [`tests/integration/test_phase4_rag_rebuild_reembed_root_scoped.py`](tests/integration/test_phase4_rag_rebuild_reembed_root_scoped.py) with three tests:

1. `test_reembed_failure_preserves_chroma_and_manifest` — pins F2. Seeds a real RAG root with NO `embeddings_model.lock`; invokes `rebuild(reembed=True)` against the real `FastembedEmbedder` (no seam mock). Asserts exit 1 AND that `chroma/` + `manifest.yaml` are byte-identical to pre-rebuild state.
2. `test_reembed_honors_custom_root_for_lock_lookup` — pins F1. Plants a deliberately corrupt lock at `<root>/embeddings_model.lock`, `cd`s away from the cwd, calls `_seam_build_reembed_embedder(root)` directly, asserts the resulting `EmbeddingsBootstrapRequired` names the root-scoped lock path (not the cwd-relative `.codegenie/rag/embeddings_model.lock`). The discriminator is the `lock_path=` field of the error — cwd-relative would name `.codegenie/rag/embeddings_model.lock`; root-scoped names `<root>/embeddings_model.lock`.
3. `test_reembed_with_bootstrapped_custom_root_succeeds` — the documented operator workflow with a fake embedder spy that asserts `root` flowed through to the seam.

**Red-then-green discipline.** All three tests run pre-fix:
- F2 test failed: chroma + manifest were both gone after a `--reembed` against a no-lock store.
- F1 test failed: `EmbeddingsBootstrapRequired` named the cwd-relative `.codegenie/rag/embeddings_model.lock`, not the root-scoped path.
- F3 spy-test passed pre-fix (the seam already receives root; the bug was inside the seam, not at the call site).

**The fix** ([`src/codegenie/rag/cli.py`](src/codegenie/rag/cli.py)):

1. `_seam_build_reembed_embedder(root)` now passes `lock_path=root/"embeddings_model.lock"` and `cache_dir=root/"fastembed-cache"` to `FastembedEmbedder(...)` — mirroring the `embeddings bootstrap` CLI's own root-scoped defaults.
2. `rebuild()` gains a **preflight embedder construction** phase 1b (between dry-run parse and the chroma rmtree). On `--reembed=True`, the embedder is built before any destructive operation. A failure exits 1 with `rebuild.embedder_preflight_failed` and the store left fully intact. The constructed embedder is threaded into `_rebuild_async(..., embedder=...)` so it is not re-built later.

**Post-fix verification:**
- All three new tests pass (green phase).
- All four pre-existing rag-rebuild integration tests still pass (`test_rag_rebuild_corrupt_yaml_aborts_before_chromadb_touch`, `test_rag_rebuild_reproduces_byte_identical_digest`, `test_rag_rebuild_reembed_updates_model_and_vectors`, `test_rag_rebuild_missing_manifest_exits_2`) — no regression.
- `tests/unit/rag/` 176 passed.
- `tests/fence/` (excluding the untracked `test_workflows_public_surface.py`) 477 passed.
- `mypy --strict src/codegenie/rag/`, `mypy --strict tests/integration/test_phase4_rag_rebuild_reembed_root_scoped.py`: clean.
- `ruff check` + `ruff format --check` on the changed files: clean.
- `lint-imports`: 12 contracts kept, 0 broken.
- `mkdocs build --strict`: clean.

**End-to-end live re-run after the fix:**

```
$ embeddings bootstrap --lock-path ./rag/embeddings_model.lock --cache-dir ./rag/fastembed-cache
embeddings.bootstrap.lock_written lock_path=rag/embeddings_model.lock ...
$ rag rebuild --root ./rag --reembed
rebuild.chroma_removed         path=rag/chroma
rebuild.completed              count=3 digest=0b0649db4fe421… reembed=True root=rag
EXIT=0
```

And the F2 sad-path:

```
$ rm embeddings_model.lock  # simulate "operator forgot to bootstrap"
$ rag rebuild --root ./rag --reembed
rebuild.embedder_preflight_failed error_class=EmbeddingsBootstrapRequired
rebuild --reembed cannot start: EmbeddingsBootstrapRequired: ... lock file missing at /tmp/rag-shakedown/rag/embeddings_model.lock; run `codegenie embeddings bootstrap`
EXIT=1
$ ls chroma/_pre_rebuild_sentinel manifest.yaml  # both still present, store recoverable
chroma/_pre_rebuild_sentinel manifest.yaml
```

## Stage 7 — Doc sweep

[`docs/operations/rag.md`](docs/operations/rag.md) updated:

- **§"When to run `codegenie rag rebuild`" item 3** now documents the `--root` ↔ `--lock-path` ↔ `--cache-dir` symmetry for non-default roots. The runbook's documented workflow now matches the code's behavior.
- **§"Recovery semantics"** gains an explicit "embedder-preflight before any destructive op" bullet describing the F2 fix — operators get a clear promise that a failed `--reembed` leaves the store recoverable.

No ADR amendment needed — both fixes are surgical bug-fixes inside the S4-07-shipped surface. The Phase-4 architecture (canonical YAML, derived chroma, ADR-0016) is unchanged. The S4-07 story itself was already shipped GREEN; the failing-first integration tests in the new file count as the "story-scoped HARDENED post-script" — a permanent regression pin against F1 + F2.

The S4-07 story status line is unchanged (Done — GREEN 2026-05-25). The post-shakedown shipment is logged via this report and the new integration test file.

## Stage 8 — Definition of done

- [x] Stage 0 passed (tools on PATH via `.venv/bin/`)
- [x] Capability + sample app named in the first line
- [x] Capability ran to completion (5 invocations: 4 happy/sad paths + the final live re-run post-fix); exit codes + log events + filesystem state captured
- [x] Every finding has exactly one root-cause class with evidence (F1 codebase-bug, F2 codebase-bug, F3 test-gap)
- [x] Every codebase-bug has: a test-gap analysis (F3 is the test-gap analysis), a test verified to fail-then-pass, a code fix, and the relevant test suites green
- [x] No sample-app or environment findings
- [x] Doc sweep ran ([`docs/operations/rag.md`](docs/operations/rag.md) updated)
- [x] Report written and validates

## Next-run primer

Pick a different capability next time — the natural follow-ups in `codegenie --help`:

- `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` — never shaken-down; verifies the audit-anchor chain across a run.
- `codegenie vuln-index refresh --source nvd|ghsa|osv` — never shaken-down; pulls NVD/GHSA/OSV into the local sqlite vuln index.
- `codegenie embeddings bootstrap` — shaken-down implicitly here but never as the primary capability; would be worth covering the same-model-drift exit-1 path against a deliberately tampered cache.
- `codegenie self-check` — the Phase-4 S3-03 operator self-check.

If the next run is another `rag` shakedown, the obvious missing coverage is **embeddings-model upgrade end-to-end**: bootstrap model A → seed → bootstrap model B (upgrade) → `rag rebuild --reembed` → verify per-record `embedding_model` digest updated to B's hash. The S4-07 test that asserts this uses a fake embedder; a real-fastembed end-to-end run would catch a future regression in the model-digest pipeline that the current fakes miss.

## Pre-existing local noise (NOT introduced by this run)

For the next runner: when you `cd` into this repo locally you will see:

- `src/codegenie/workflows/`, `tests/unit/workflows/`, `tests/integration/test_phase6_sut_contract_snapshot*.py`, `tests/fence/test_workflows_public_surface.py` — Phase-6 scratch, untracked, references a `codegenie.workflows` package that exists locally but isn't committed. Pytest collection blows up unless you `--ignore` these. Out of scope for this shakedown.
- `src/codegenie/types/parsers.py` — uncommitted modification with a long-line ruff failure on line 602. Out of scope.
- `lint-imports` not on global PATH → `tests/unit/test_lint_imports_canary.py` self-tests fail locally; CI uses `.venv/bin/lint-imports` and is unaffected.
- `pre-commit` cassette-lock hook fails locally with `Executable 'python' not found` (PATH artifact); not an issue inside CI.

None of the above affect the changes from this shakedown — they're pre-existing and untracked. Surfacing them per Rule 12 so the next runner doesn't waste time chasing them.
