# Story S4-02 — Embedding sidecar — UDS + semaphore + msgpack wire format

**Step:** Step 4 — Ship the RAG side — `EmbeddingProvider` + UDS sidecar, `SolvedExampleStore`, `QueryKeyCache`, `SolvedExampleHealthProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`SentenceTransformerProvider` is what the worker wraps)
**ADRs honored:** ADR-P4-006 (sidecar discipline, cold boot ≤ 2.5s, warm ~28ms), ADR-P4-005 (no `chromadb` import in `rag/embeddings/`)

## Context

Loading `sentence-transformers` costs ~2.5s of cold-boot time and ~50 MB of resident memory. The orchestrator amortizes this with a long-lived **UDS sidecar** (`embed_worker.py`) at `unix:.codegenie/run/embed.sock` that is activated when the session embeds ≥ 2 workflows; one-shot CLI invocations fall back to the in-proc provider from S4-01 to avoid the spawn cost. A semaphore (max 4 concurrent) bounds contention; wire format is msgpack (encapsulated so a flip to JSON is one-file change per `final-design.md §"Open questions"` #2). This story is the difference between "RAG side ships" and "RAG side ships at warm-embed budget" — every later perf canary (G7 selector p95 ≤ 250ms; G8 query-key p95 ≤ 5ms) assumes the warm sidecar is in place.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design"` #7 `EmbeddingProvider` — UDS sidecar + semaphore + msgpack rationale.
  - `../phase-arch-design.md §"Physical view"` — where the socket lives (`.codegenie/run/embed.sock`), startup-ordering note.
  - `../phase-arch-design.md §"Process view"` — sidecar lifecycle vs in-proc fallback.
  - `../phase-arch-design.md §"Harness engineering"` — structured-JSON logging discipline (`run_id`, `tier`, `prompt_template_id`) applies to the worker too.
- **Phase ADRs:**
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — sidecar perf envelope; cold boot ≤ 2.5s; warm ~28ms.
  - `../ADRs/README.md` item #2 (Open questions deferred) — msgpack vs JSON; encapsulation requirement.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — gather-side determinism; the embedding sidecar is not on the gather path but its hermetic, cassette-replayable behaviour is consistent with the broader determinism stance.
- **Source design:**
  - `../final-design.md §"Open question"` #3 — msgpack tentative; flip-ability via single-file change.
  - `../final-design.md §"Components"` #8 — sidecar lifecycle.
- **Existing code:**
  - `src/codegenie/rag/embeddings/local.py` (S4-01) — the provider the worker imports.
  - `src/codegenie/rag/contract.py` (S1-03) — Protocol the sidecar-fronted client must satisfy.

## Goal

Ship `src/codegenie/rag/embeddings/sidecar.py` (the orchestrator-side client) + `src/codegenie/rag/embeddings/embed_worker.py` (the long-lived process) so the orchestrator can call `SidecarEmbeddingProvider.embed(texts)` and have requests round-trip over `unix:.codegenie/run/embed.sock` with msgpack framing, a max-4 concurrent semaphore, and `connect()` readiness gated before any workflow embeds; warm-embed for a ~400-token query is ≤ 50 ms (headroom over the 28 ms ADR-P4-006 goal).

## Acceptance criteria

- [ ] `src/codegenie/rag/embeddings/sidecar.py` defines `SidecarEmbeddingProvider` satisfying the `EmbeddingProvider` Protocol; constructor takes `socket_path: Path = Path(".codegenie/run/embed.sock")` and `max_concurrency: int = 4`.
- [ ] `connect(timeout_s: float = 5.0) -> None` blocks until the sidecar accepts a UDS connection; raises `SidecarUnavailable` on timeout; **must be called once before `embed()` is invoked from any workflow** — `embed()` raises `SidecarNotConnected` if called without prior `connect()`.
- [ ] `embed(texts: Sequence[str]) -> list[list[float]]` round-trips over UDS using msgpack framing (length-prefixed `uint32` BE + msgpack body); returns one 384-float vector per text; same shape as `SentenceTransformerProvider.embed`.
- [ ] Internal semaphore bounds in-flight requests to `max_concurrency=4`; over-quota callers block (do not drop).
- [ ] `model_digest`, `model_id`, `dimensions` are populated from a handshake message at `connect()` time — the worker reports these from the wrapped `SentenceTransformerProvider`; mismatch between sidecar-reported digest and `tools/digests.yaml` raises `EmbeddingDigestMismatch` from the client (Gap-2 defense in depth).
- [ ] `available() -> bool` checks socket existence + last-known liveness ping; returns `False` cleanly (no exception) when the sidecar is down.
- [ ] `src/codegenie/rag/embeddings/embed_worker.py` is a runnable `python -m` entry point: binds `unix:.codegenie/run/embed.sock` (mode 0600), loads `SentenceTransformerProvider`, serves `embed`/`handshake`/`ping` requests; logs structured JSON to stderr; graceful shutdown on SIGTERM.
- [ ] Wire format is encapsulated in a single helper module (`src/codegenie/rag/embeddings/_wire.py`) exposing `pack(msg) -> bytes` / `unpack(stream) -> dict`; flipping msgpack→JSON requires editing only this one file (verified by an AST scan in the fence-CI extension or by a one-grep guard test).
- [ ] One-shot CLI fallback path: if `connect()` raises `SidecarUnavailable` AND env `CODEGENIE_ALLOW_INPROC_EMBED=1` is set (or the CLI is invoked with `--one-shot`), the calling code substitutes `SentenceTransformerProvider` instead; the substitution emits `audit.info: embedding.sidecar_fallback_inproc`.
- [ ] `tests/unit/rag/test_embedding_sidecar_warm_28ms.py` — warm embed for a ~400-token query ≤ 50 ms over UDS (allows CI-host headroom over the 28 ms goal); runs against a real spawned worker in a `tmp_path` socket.
- [ ] `tests/integration/test_embedding_sidecar_startup_ordering.py` — orchestrator must `connect()` UDS readiness *before* spawning workflows that embed; calling `embed()` before `connect()` raises `SidecarNotConnected`.
- [ ] `tests/unit/rag/test_embedding_sidecar_wire_format_encapsulated.py` — grep / AST guard asserts `import msgpack` (and `import json` for wire purposes) appear **only** in `_wire.py`, not in `sidecar.py` or `embed_worker.py`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/rag/embeddings/`, `pytest tests/unit/rag/test_embedding_sidecar_*` all pass.

## Implementation outline

1. Write the failing tests (see TDD plan). The warm-embed timing test spawns the worker via `subprocess.Popen(["python","-m","codegenie.rag.embeddings.embed_worker","--socket",str(sock)])`; the startup-ordering test asserts the pre-connect raise; the wire-encapsulation test is a static AST scan.
2. Create `src/codegenie/rag/embeddings/_wire.py`:
   - `pack(msg: dict) -> bytes`: msgpack-pack the dict, prefix with 4-byte BE length.
   - `unpack(reader: io.BufferedReader) -> dict`: read 4 bytes, decode length, read N bytes, msgpack-unpack.
3. Create `src/codegenie/rag/embeddings/embed_worker.py`:
   - Parse `--socket` arg.
   - Instantiate `SentenceTransformerProvider()`. This triggers the SHA verification from S4-01.
   - Bind UDS at the socket path, mode 0600 (`os.chmod`).
   - Loop: accept, handshake → reply `{model_id, model_digest, dimensions}`; `ping` → `{ok: True}`; `embed {texts}` → `{vectors}`.
   - SIGTERM handler removes the socket file on exit.
4. Create `src/codegenie/rag/embeddings/sidecar.py`:
   - `SidecarEmbeddingProvider` with the Protocol surface.
   - `connect()`: open UDS, send `handshake`, store `model_digest`/`model_id`/`dimensions`, verify against `tools/digests.yaml` (re-uses the helper from S4-01).
   - `embed(texts)`: acquire semaphore, send `{op: "embed", texts}`, receive vectors, return.
   - `available()`: try a brief `ping`; non-blocking.
5. Add the in-proc-fallback shim (small helper in `sidecar.py` callable from the CLI factory in S4-07; this story just exposes the substitution hook).
6. Run lint/format/type/test.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/rag/test_embedding_sidecar_warm_28ms.py`

```python
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from codegenie.rag.embeddings.sidecar import (
    SidecarEmbeddingProvider,
    SidecarNotConnected,
)


@pytest.fixture
def warm_sidecar(tmp_path: Path):
    sock = tmp_path / "embed.sock"
    proc = subprocess.Popen(
        [sys.executable, "-m", "codegenie.rag.embeddings.embed_worker",
         "--socket", str(sock)],
        env={**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1"},
    )
    # Wait up to 10s for cold boot (ADR-P4-006 says ≤ 2.5s; CI headroom is generous).
    deadline = time.time() + 10.0
    while time.time() < deadline and not sock.exists():
        time.sleep(0.05)
    yield sock
    proc.terminate()
    proc.wait(timeout=5)


def test_warm_embed_under_50ms_p50(warm_sidecar: Path) -> None:
    """ADR-P4-006 budgets ~28ms warm-embed for a ~400-token query;
    the 50ms ceiling is CI-host headroom. If this regresses, RAG
    tier-2 retrieval blows the G7 selector-chain 250ms budget."""
    provider = SidecarEmbeddingProvider(socket_path=warm_sidecar)
    provider.connect(timeout_s=5.0)
    # One warm-up embed (excluded from timing).
    provider.embed(["warmup"])
    text = "lorem ipsum " * 64  # ~400 tokens at 4 chars/token.

    times_ms: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        provider.embed([text])
        times_ms.append((time.perf_counter() - t0) * 1000)

    p50 = sorted(times_ms)[len(times_ms) // 2]
    assert p50 <= 50.0, f"warm-embed p50={p50:.1f}ms exceeds 50ms budget"


def test_embed_before_connect_raises(warm_sidecar: Path) -> None:
    """Startup-ordering invariant — orchestrator must connect() before
    spawning workflows that embed. Silent fallback would mask the bug."""
    provider = SidecarEmbeddingProvider(socket_path=warm_sidecar)
    with pytest.raises(SidecarNotConnected):
        provider.embed(["hi"])
```

Path: `tests/unit/rag/test_embedding_sidecar_wire_format_encapsulated.py`

```python
import ast
from pathlib import Path


def _imports_in(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module.split(".")[0])
    return imports


def test_msgpack_only_imported_in_wire_module() -> None:
    """Wire format must be flippable in one file (final-design Open Q #3).
    If msgpack leaks into sidecar.py or embed_worker.py, the JSON-flip
    becomes multi-file and the encapsulation guarantee is broken."""
    sidecar = _imports_in(Path("src/codegenie/rag/embeddings/sidecar.py"))
    worker = _imports_in(Path("src/codegenie/rag/embeddings/embed_worker.py"))
    wire = _imports_in(Path("src/codegenie/rag/embeddings/_wire.py"))

    assert "msgpack" not in sidecar, "msgpack leaked into sidecar.py"
    assert "msgpack" not in worker, "msgpack leaked into embed_worker.py"
    assert "msgpack" in wire, "msgpack must live in _wire.py"
```

Commit red. Both fail (`ImportError` or assertion).

### Green

- Minimal `_wire.py`: ~25 lines.
- Minimal `embed_worker.py`: ~60 lines (arg parse, bind, accept loop, dispatch).
- Minimal `sidecar.py`: ~70 lines (`connect`, `embed`, `available`, semaphore).

### Refactor

- Extract a `_Client` connection-pool helper if multiple methods need socket lifecycle.
- Add structured-JSON logging (`run_id`, `op`, `latency_ms`) to the worker stderr per harness engineering.
- Wire `available()` to short-circuit on the cached `model_digest` when fresh.
- Add a `__main__` block guard to the worker so it's runnable both as `python -m` and as a console script Phase-9 Temporal Activity will adopt.
- Verify the fence-CI test still passes; add `msgpack` to `requirements.in` if not already present.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/embeddings/sidecar.py` | New — `SidecarEmbeddingProvider` client |
| `src/codegenie/rag/embeddings/embed_worker.py` | New — long-lived UDS worker |
| `src/codegenie/rag/embeddings/_wire.py` | New — wire format encapsulation |
| `tests/unit/rag/test_embedding_sidecar_warm_28ms.py` | New — perf canary |
| `tests/integration/test_embedding_sidecar_startup_ordering.py` | New — connect-before-embed invariant |
| `tests/unit/rag/test_embedding_sidecar_wire_format_encapsulated.py` | New — AST guard on msgpack containment |
| `requirements.in` / lock | Add `msgpack` if absent |

## Out of scope

- **The orchestrator decision to use sidecar vs in-proc** — that's a CLI-startup concern S4-07 wires (`codegenie models fetch` warms the sidecar; the engine factory chooses based on session size).
- **Multi-host UDS** — Phase 4 is single-host; Phase 9 Temporal Activities subsume this question.
- **`VoyageProvider` sidecar** — the stub stays in-proc; Phase 14 reopens.
- **TLS / auth on the UDS** — UDS file mode 0600 + same-host trust is sufficient for Phase 4; remote workers are a Phase 9+ concern.
- **Adaptive batching / queueing** — `embed(texts)` already accepts a batch; smart batching across workflows is a perf optimization deferred.

## Notes for the implementer

- **`mode=0600` on the socket file is load-bearing.** The orchestrator runs as the operator UID; another user on the same host should not be able to send `embed` requests (low practical risk, but the supply-chain stance demands it). Use `os.chmod(sock_path, 0o600)` *after* `bind`.
- **Cold boot is dominated by the `SentenceTransformer` constructor.** Most of the 2.5s is the `safetensors` mmap + tokenizer load. Do not lazy-init inside the request handler — that pushes the cost onto the first `embed()` call.
- **Worker stderr is the audit channel.** Structured JSON only — no `print()` calls. The harness-engineering convention (`run_id`, `phase=4`, `tier=embed_sidecar`) applies; Phase 13's log aggregator will consume it.
- **Semaphore semantics — block, do not drop.** `embed()` callers expect a vector; dropping a request would silently return `None`-shaped output and break downstream typing. Use a bounded `asyncio.Semaphore` (or `threading.Semaphore` if the client is sync) with no timeout for in-flight bounding.
- **Handshake digest verification is defense-in-depth.** The worker may legitimately report a different digest than `tools/digests.yaml` if the operator just ran `codegenie models fetch` on a new pin — but the client should reject mismatch and force the operator to restart the orchestrator. Silent acceptance is what Gap-2 closes.
- **One-shot CLI fallback is opt-in.** Do not auto-fall-back on sidecar absence in normal operation — that would mask startup-ordering bugs (the whole reason for the integration test). The `CODEGENIE_ALLOW_INPROC_EMBED=1` opt-in is explicit; `audit.info: embedding.sidecar_fallback_inproc` makes the fall-back observable.
- **The `_wire.py` encapsulation test is a real fence-CI assertion.** Do not weaken it by importing `msgpack` indirectly elsewhere (e.g., importing a wrapper that re-exports). The AST scan checks the literal `import msgpack` statement. Future JSON flip = ~20 LOC in `_wire.py`, zero elsewhere.
