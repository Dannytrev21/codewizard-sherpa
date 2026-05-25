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
