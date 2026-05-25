# RAG substrate — operator runbook

Stub runbook for the Phase-4 RAG substrate (S4-07). The final, fleshed-out
operator playbook lands with S7-10. This page is the per-command reference
for the rebuild path.

## When to run `codegenie rag rebuild`

Three operator scenarios trip the rebuild:

1. **chromadb sqlite corruption.** Opening the store raises
   `StoreCorrupted`. The diagnostic names this command. Run with the
   default flags — the canonical YAML records are intact and the chromadb
   derived index is wiped and reconstructed.

2. **Schema upgrade** (e.g. `_Manifest.schema_version` v1 → v2). Reconstruct
   chromadb against the new code's schema.

3. **Embedding-model upgrade.** Run `codegenie embeddings bootstrap` first
   to drop the new weights + lock; then `codegenie rag rebuild --reembed`
   to re-embed every record's projected text against the new model.

   **Non-default `--root`:** if the RAG substrate lives outside the
   default `.codegenie/rag/`, pass the matching `--lock-path` and
   `--cache-dir` to `embeddings bootstrap` so the lock + weights cache
   land under `<root>/embeddings_model.lock` and `<root>/fastembed-cache`
   respectively. `codegenie rag rebuild --root <root> --reembed` resolves
   both relative to `--root` — it does **not** fall back to
   `.codegenie/rag/`.

## Usage

```bash
codegenie rag rebuild [--root .codegenie/rag/] [--reembed]
```

- `--root` — RAG root containing `manifest.yaml` and `records/`. Defaults
  to `.codegenie/rag/`.
- `--reembed` — re-embed each record's projected query text via the
  current `FastembedEmbedder`. Use this only after `embeddings bootstrap`
  applied a model upgrade. Default mode reuses the stored
  `embedding_vector` field — fast and the right choice for corruption
  recovery.

## Exit codes

| Code | Meaning                                                |
|------|--------------------------------------------------------|
| 0    | rebuild completed; `store.digest()` reproduces the chain head |
| 1    | YAML parse error / chromadb write failure / rmtree refused (path escape / symlink) |
| 2    | `manifest.yaml` missing under `--root` — nothing to rebuild from |

## Recovery semantics

- **Default mode is transactional at the directory level.** The dry-run
  pass parses every record YAML before deleting `<root>/chroma/`; a
  parse failure aborts before any destructive operation.
- **`--reembed` runs an embedder-preflight before any destructive op.**
  The embedder is constructed (lock + cache verified) *before* the
  rebuild touches `<root>/chroma/` or `<root>/manifest.yaml`. A
  missing/corrupt lock exits 1 with the store fully intact — the
  canonical records, derived chroma, and manifest are all preserved, so
  the operator can `codegenie embeddings bootstrap` then re-invoke.
- **`--reembed` is idempotent but NOT atomic.** Once the preflight passes
  and the rebuild starts re-writing canonical YAMLs, each record's
  canonical YAML is rewritten mid-loop with its new vector + model
  digest. A mid-loop failure leaves earlier records re-embedded on disk;
  re-running `codegenie rag rebuild --reembed` finishes the job (same
  text + same embedder → same vectors).
- **`rmtree` refuses to escape `--root`.** A symlinked or out-of-tree
  `chroma/` exits 1 with `"refusing to remove"` and never touches the
  filesystem (Rule 12 — fail loud).

See [`docs/phases/04-vuln-llm-fallback-rag/ADRs/0016-chromadb-embedded-yaml-canonical-store.md`](../phases/04-vuln-llm-fallback-rag/ADRs/0016-chromadb-embedded-yaml-canonical-store.md)
for the full decision (canonical YAML, derived chromadb, rebuild contract).
