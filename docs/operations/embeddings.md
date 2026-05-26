# Embeddings substrate runbook

This is the **stub** runbook for the Phase-4 RAG-substrate embeddings
layer (S4-01); S7-10 finalizes the full operator guide. The two
load-bearing facts an on-call engineer needs *right now*:

1. The runtime path (`FastembedEmbedder`) **refuses to start** if
   `.codegenie/rag/embeddings_model.lock` is missing, corrupt, or out
   of sync with the on-disk weight cache. There is no silent fallback.
2. The **only** way to (re)populate the lock + weights is the
   operator-initiated CLI:

   ```bash
   python -m codegenie embeddings bootstrap
   ```

## Lock file

Path: `.codegenie/rag/embeddings_model.lock`. YAML shape, sorted keys,
trailing newline:

```yaml
model_name: BAAI/bge-small-en-v1.5
sha256: <64-hex-char directory digest>
```

The `sha256` is **not** a single-file digest — it is folded over every
regular file in the on-disk fastembed cache (sorted by relative path).
A tokenizer-config edit therefore drifts the digest just as much as a
weights edit does (ADR-0007 §Consequences + arch edge case #3).

## CLI surface

```text
codegenie embeddings bootstrap
    [--model-name <fastembed model id>]
    [--cache-dir <path>]
    [--lock-path <path>]
```

Defaults:

- `--model-name` → `BAAI/bge-small-en-v1.5` (ADR-0007).
- `--cache-dir` → `$FASTEMBED_CACHE_DIR` if set, else
  `<cwd>/.codegenie/rag/fastembed-cache`.
- `--lock-path` → `.codegenie/rag/embeddings_model.lock`.

Exit codes:

- **0** — lock written (first run), lock_current (idempotent re-run),
  or explicit model upgrade.
- **1** — same-model digest drift (corruption / tampering). The lock
  is **NOT** rewritten; investigate cache contents before re-running.

## Failure-mode quick reference

| Symptom (raised by runtime path) | Remediation |
| --- | --- |
| `EmbeddingsBootstrapRequired` (lock missing) | Run `codegenie embeddings bootstrap`. |
| `EmbeddingsBootstrapRequired` (lock corrupt) | Inspect the lock; the safest fix is `rm <lock> && codegenie embeddings bootstrap`. |
| `EmbeddingsBootstrapRequired` (weights absent) | Run `codegenie embeddings bootstrap`; the cache directory was cleared without the lock. |
| `EmbeddingModelMismatch(kind="model_name")` | The constructor argument disagrees with the lock. Decide which is correct, then re-run bootstrap with the intended `--model-name` (this overwrites the lock and triggers the `embeddings.bootstrap.model_upgraded` warning). |
| `EmbeddingModelMismatch(kind="sha256")` | Genuine cache tampering / corruption. Inspect `<cache-dir>` contents; do **not** run bootstrap blindly — that would mask the drift only if you also accept the new digest. |

## Why this exists

ADR-0007 §Decision: fastembed ONNX over `sentence_transformers` / `torch`.
The refuse-start posture is the primary supply-chain control;
`EgressGuard` (S3-03) is defense-in-depth. Bootstrap is **operator-
initiated** — auto-running it from a runtime path defeats the control
and bypasses egress filtering.

## codegenie embeddings bootstrap

The operator-initiated CLI that downloads the pinned
[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)
fastembed model weights into `.codegenie/rag/` and writes the SHA-256
digest into `.codegenie/rag/embeddings_model.lock`.

```bash
python -m codegenie embeddings bootstrap
```

The command is content-addressed: it computes the digest of the downloaded
weight directory and refuses to write the lock file if the digest does not
match the value
pinned in [ADR-04-0007](../phases/04-vuln-llm-fallback-rag/ADRs/0007-fastembed-onnx-over-sentence-transformers.md).
Download integrity failures fail loud; partial writes are removed.

The lock file is the contract every later runtime path reads — see
"Refuse-to-start on lock state" below.

## codegenie rag rebuild

Deterministically reconstructs the Chroma persistent store from the canonical
YAML records under `.codegenie/rag/records/`. Use it in three scenarios
(arch §Edge cases #13):

1. **Embedding-model drift** — when `embeddings_model.lock` shows a digest
   different from the one shipped today.
2. **Corpus restore** — after a destructive operation or restoring from
   backup, the YAML records are the source of truth; the Chroma index is
   re-derived.
3. **SQLite corruption** — when the underlying sqlite store fails its
   integrity check, `rebuild` writes a fresh store from canonical YAML.

```bash
python -m codegenie rag rebuild           # rebuild Chroma, reuse cached embeddings
python -m codegenie rag rebuild --reembed  # also re-compute embeddings (model drift)
```

The `--reembed` flag re-runs the FastembedEmbedder over every record body;
use it whenever the lock-file digest changes.

## Refuse-to-start on lock state

`FastembedEmbedder.__init__` reads `.codegenie/rag/embeddings_model.lock`
at construction time and raises if **either** of the following holds:

1. **Lock-file drift** — the on-disk digest does not match the runtime-pinned
   digest (model was bootstrapped against a different model version).
2. **Lock-file absent** — the file does not exist; the operator has not yet
   run `bootstrap` (or the cache was deleted).

There is no silent fallback. The operator runs `bootstrap` to recover from
either failure mode. The executable test asserting both failure shapes lives
at `tests/unit/rag/test_fastembed_embedder_refuse_on_lock_state.py` (or the
successor file the S4-01 attempt log named).

## Cross-architecture float drift

Fastembed runs through ONNX runtime, which has documented numerical drift at
the 5th decimal place across architectures (macOS arm64 vs Linux x86_64).
This is acknowledged and absorbed by the **two-threshold band classifier**:
any similarity score that crosses the band-edge floor on one architecture
but not the other still falls inside the same `(RagHit | RagDegraded | RagMiss)`
classification. See
[ADR-04-0008](../phases/04-vuln-llm-fallback-rag/ADRs/0008-two-threshold-calibration-band.md)
for the design rationale and the calibration smoke test at S5-04 that
pins the drift envelope.

Do **not** hash raw embedding floats as cache keys — Phase 4 hashes BLAKE3
of the canonical text input instead, sidestepping the drift entirely.

## See also

- [ADR-04-0007 — fastembed/ONNX over sentence-transformers](../phases/04-vuln-llm-fallback-rag/ADRs/0007-fastembed-onnx-over-sentence-transformers.md)
- [ADR-04-0008 — two-threshold calibration band](../phases/04-vuln-llm-fallback-rag/ADRs/0008-two-threshold-calibration-band.md)
- [`./cassettes.md`](./cassettes.md) — cassette discipline (separate substrate; no overlap).
- [`./secrets.md`](./secrets.md) — Anthropic key storage.
