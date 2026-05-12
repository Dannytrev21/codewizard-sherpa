# Story S3-04 — `EgressProxy` daemon (Linux only) — two-endpoint allowlist + x-api-key strip + 128 KB byte cap

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** L
**Depends on:** S2-04 (`ApiKeyStore` OS-tiered), S2-03 (`LlmInvocationGuard` L3 surface)
**ADRs honored:** ADR-P4-004, ADR-P4-010, ADR-P4-013, ADR-P4-011 (LLM prompt/context exfiltration boundary)

## Context
On Linux, the `JailedLeafLlmAgent` (S3-05) runs under `bwrap --unshare-all --uid <agent-uid>` with **no direct network**. The only way it reaches Anthropic is through `EgressProxy`, a separate long-running daemon that listens on `unix:/jail/egress.sock`. The proxy is the trust boundary: it holds the API key (read once from `ApiKeyStore` at startup; never re-read), enforces a two-endpoint allowlist (`POST /v1/messages` and `POST /v1/messages/count_tokens`), **strips any client-supplied `x-api-key` header** before forwarding (closes critic §S "egress smuggle"), and enforces the L3 128 KB egress byte cap — any response larger than that is treated as adversarial and rejected with no retry. This is the highest security-review surface in the phase.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 2. LeafLlmAgent` — process boundary + EgressProxy responsibilities; `§Process view` — startup-order sequence (proxy UDS ready before agent spawn); `§Edge cases #12, #13` — non-allowlisted request behavior + agent cannot reach Anthropic directly; `§Adversarial tests` — `test_egress_proxy_blocks_x_api_key_in_request.py`.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — why the OS-tiered design needs a proxy on Linux.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — L3 byte-cap surface lives in the proxy.
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 — proxy is one of the only modules permitted to call `ApiKeyStore.read()`.
- **Source design:** `../final-design.md §Synthesis ledger row "Agent process boundary"` and row "API-key handling" — proxy holds the key.
- **High-level impl:** `../High-level-impl.md §Step 3` — `egress_proxy.py` bullet (full responsibilities listed).
- **Existing code:** `src/codegenie/llm/secrets/key_store.py` (S2-04); `src/codegenie/audit.py` (Step-0/1) for `egress.request.deny` event.

## Goal
Ship a Linux-only egress proxy daemon that holds the API key, accepts only two POST endpoints over a Unix socket, strips agent-supplied `x-api-key` headers, and rejects any upstream response over 128 KB with no retry.

## Acceptance criteria
- [ ] `src/codegenie/llm/leaf_anthropic/egress_proxy.py` defines `EgressProxy(socket_path: Path, key_store: ApiKeyStore, byte_cap: int = 128 * 1024)` with `start()` / `stop()` / `ready()`.
- [ ] On `start()`: reads `key_store.read()` exactly **once** and stores it in a process-local handle (no re-reads, no env var); binds to `socket_path` with mode `0o600`; logs `egress.proxy.started` (no key, no key fingerprint).
- [ ] Allowlist: only `POST /v1/messages` and `POST /v1/messages/count_tokens` proceed. Anything else — `GET /v1/messages`, `POST /v1/admin`, `POST /` — returns 403 and emits `egress.request.deny(path=<>, method=<>)` audit event.
- [ ] **`x-api-key` strip:** for every accepted request, the proxy removes any client-supplied `x-api-key` / `X-Api-Key` / `Authorization` header before forwarding; the proxy attaches the real `x-api-key` from its in-memory handle. Covered by `tests/security/test_egress_proxy_strips_agent_x_api_key.py`.
- [ ] **128 KB egress byte cap:** if the upstream response body exceeds 128 KB, the proxy **does not retry**, closes the upstream connection, returns 413 (or an internal `egress.response.truncated` status) to the agent, and emits `egress.response.byte_cap_exceeded` audit event. Covered by `tests/security/test_egress_proxy_byte_cap_128kb.py` with a synthetic 200 KB upstream.
- [ ] `tests/security/test_egress_proxy_allowlist.py` covers: `POST /v1/messages` → 200; `GET /` → 403 + audit event; `POST /v1/messages/count_tokens` → 200; `POST /v1/admin` → 403.
- [ ] `tests/security/test_egress_proxy_strips_agent_x_api_key.py` covers a request where the agent sets `x-api-key: agent-spoof`; the proxy strips it and uses the in-memory real key; an outbound HTTP recorder captures the forwarded request and asserts only one `x-api-key` header is present with value != `agent-spoof`.
- [ ] `tests/security/test_egress_proxy_byte_cap_128kb.py` covers a synthetic 200 KB upstream response → truncated and rejected; no retry; one audit event.
- [ ] `tests/unit/llm/test_egress_proxy_key_read_once.py` covers the assertion that `ApiKeyStore.read()` is called exactly once across the proxy's lifetime (mock + call-count assertion).
- [ ] Linux-only CI job runs these tests; macOS CI skips them with a `@pytest.mark.linux_only` marker.
- [ ] ruff, ruff format, mypy strict on `src/codegenie/llm/leaf_anthropic/egress_proxy.py`, pytest green on Linux job.

## Implementation outline
1. Decide transport stack: prefer Python `aiohttp` server bound to a UDS path with an `aiohttp` client toward `api.anthropic.com`. Alternative is `asyncio` + `httpx` — pick one and stick with it; document in module docstring.
2. `EgressProxy.__init__(socket_path, key_store, byte_cap)` — store config, do not read the key yet.
3. `EgressProxy.start()`:
   - read key via `key_store.read()` (S2-04 call-stack-frame allowlist must include this module);
   - bind UDS at `socket_path` with `os.umask` flipped so socket inode is `0o600`;
   - set up `ready()` → `True` only once the listener is accepting.
4. Per-request handler:
   - reject non-allowlisted `(method, path)` pairs with 403 + audit;
   - copy headers from the agent request, **delete** any `x-api-key`, `X-Api-Key`, `Authorization` header (case-insensitive);
   - add the proxy's in-memory `x-api-key`;
   - forward to `https://api.anthropic.com{path}` with a streaming response;
   - read response in chunks; if cumulative bytes > 128 KB, abort, audit `egress.response.byte_cap_exceeded`, return 413; else stream back to the agent.
5. Startup-order: `ready()` is what S3-05 polls before spawning the bwrap jail.
6. Logging: structured JSON; never include header values; key fingerprint is never logged either.
7. Shutdown: `stop()` closes the UDS, deletes the socket file inode.

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/security/test_egress_proxy_allowlist.py`
- `tests/security/test_egress_proxy_strips_agent_x_api_key.py`
- `tests/security/test_egress_proxy_byte_cap_128kb.py`
- `tests/unit/llm/test_egress_proxy_key_read_once.py`

```python
# test_egress_proxy_allowlist.py
import pytest, httpx

@pytest.mark.linux_only
@pytest.mark.parametrize("method, path, status", [
    ("POST", "/v1/messages", 200),
    ("POST", "/v1/messages/count_tokens", 200),
    ("GET", "/", 403),
    ("GET", "/v1/messages", 403),
    ("POST", "/v1/admin", 403),
])
async def test_endpoint_allowlist(running_proxy, audit_log, method, path, status):
    transport = httpx.AsyncHTTPTransport(uds=str(running_proxy.socket_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        r = await c.request(method, path, json={})
    assert r.status_code == status
    if status == 403:
        assert any(e.kind == "egress.request.deny" and e.fields["path"] == path for e in audit_log.events)
```

```python
# test_egress_proxy_strips_agent_x_api_key.py
@pytest.mark.linux_only
async def test_proxy_strips_client_x_api_key(running_proxy, anthropic_recorder):
    transport = httpx.AsyncHTTPTransport(uds=str(running_proxy.socket_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        await c.post("/v1/messages",
                     headers={"x-api-key": "agent-spoof", "X-Api-Key": "agent-spoof-2"},
                     json={"model": "...", "messages": []})
    forwarded = anthropic_recorder.last_request
    keys = [v for (k, v) in forwarded.headers.items() if k.lower() == "x-api-key"]
    assert len(keys) == 1
    assert keys[0] != "agent-spoof"
    assert keys[0] != "agent-spoof-2"
```

```python
# test_egress_proxy_byte_cap_128kb.py
@pytest.mark.linux_only
async def test_proxy_rejects_oversized_upstream_response(running_proxy_with_synthetic_upstream, audit_log):
    running_proxy_with_synthetic_upstream.configure(response_size_bytes=200_000)
    transport = httpx.AsyncHTTPTransport(uds=str(running_proxy_with_synthetic_upstream.socket_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        r = await c.post("/v1/messages", json={})
    assert r.status_code in (413, 502)
    assert running_proxy_with_synthetic_upstream.upstream_call_count == 1  # no retry
    assert any(e.kind == "egress.response.byte_cap_exceeded" for e in audit_log.events)
```

```python
# test_egress_proxy_key_read_once.py
@pytest.mark.linux_only
def test_api_key_read_exactly_once(mock_key_store, running_proxy):
    # mock_key_store records every read() call
    assert mock_key_store.read_call_count == 1
    # Send many requests
    for _ in range(20):
        send_synthetic_request(running_proxy)
    assert mock_key_store.read_call_count == 1
```

### Green
Minimal `aiohttp` UDS server + UDS-to-HTTPS forwarder; in-line allowlist; header strip via dict comprehension; chunked response with cumulative byte counter.

### Refactor
- Extract `_strip_secrets(headers)` and `_forward(req, upstream)` for unit-testability without a server.
- Add docstring with the proxy's threat model and the two ADRs it implements.
- Add a `--max-response-bytes` config knob (default 128 KB) but keep the default locked.
- Add `daemon mode` start script — `python -m codegenie.llm.leaf_anthropic.egress_proxy --socket /jail/egress.sock` (consumed by S3-05's startup).
- Logging hygiene scan: a follow-up test in `tests/security/test_no_api_key_in_logs.py` (S2-04 already added) must pass against this module's logs.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/llm/leaf_anthropic/egress_proxy.py` | The daemon. |
| `src/codegenie/llm/leaf_anthropic/__init__.py` | Export `EgressProxy`. |
| `src/codegenie/llm/leaf_anthropic/__main__.py` (or `egress_proxy_main.py`) | CLI entry for daemon startup. |
| `tests/security/test_egress_proxy_allowlist.py` | Red — endpoint allowlist. |
| `tests/security/test_egress_proxy_strips_agent_x_api_key.py` | Red — header strip. |
| `tests/security/test_egress_proxy_byte_cap_128kb.py` | Red — 128 KB cap. |
| `tests/unit/llm/test_egress_proxy_key_read_once.py` | Red — single key read. |
| `.github/workflows/linux.yml` | Add `linux_only` job invocation (extend existing if present). |

## Out of scope
- **`JailedLeafLlmAgent` + bwrap launcher** — handled by S3-05; this story ships only the proxy and Linux CI hooks.
- **SPKI pinning of `api.anthropic.com`** — explicitly out per `final-design.md §Synthesis ledger row "SPKI pinning"` (deferred to Phase 16).
- **TLS for the UDS itself** — UDS is filesystem-permission-gated (mode `0o600` + bwrap UID).
- **L1 / L2 cost layers** — handled by S2-03; this story implements only L3.

## Notes for the implementer
1. **Read the key exactly once.** Re-reading per request widens the attack surface (any TOCTOU or env-var swap). Lock the handle behind a property that asserts `_key is not None` and never reassigns.
2. **Header strip must be case-insensitive.** HTTP headers are case-insensitive; iterating `dict.items()` and matching exact case misses `X-Api-Key`. Use `httpx.Headers` or normalize to lower before deletion.
3. **`Authorization` strip too.** If the agent stuffs the key into `Authorization: Bearer sk-...` you'd otherwise forward it — that is the same smuggle attack. Strip both classes of header.
4. **Byte cap must abort upstream, not just trim.** A "trim then forward" still tells the agent something it shouldn't know. Abort + 413/502 + audit.
5. **No retry on byte-cap reject.** Edge case is "treated as adversarial"; retrying could amplify a malicious large-payload probe.
6. **Linux-only CI marker.** Use a pytest marker (e.g. `pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only")`) and add the job to the Linux runner config. macOS CI must NOT skip silently — surface a "skipped 4 tests (linux_only)" line.
7. **No `subprocess` shell-out.** The proxy is plain Python — no `curl`, no `nc` glue. Audit surface stays small.
8. **Audit-event names are canonical.** `egress.request.deny`, `egress.response.byte_cap_exceeded` — these are referenced by name in Phase 5 audit assertions; don't paraphrase.
