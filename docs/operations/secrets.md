# Secrets — Anthropic API key storage and rotation

> Operator runbook for the **single** secret Phase 4 introduces: the
> Anthropic API key. The key is consumed exclusively by
> [`AnthropicLeafAdapter`](../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md);
> no other code path reads it.

## Anthropic key storage

The key lives in the operator's OS keyring under
`(service="codegenie", username="anthropic_api_key")`. There is **no
environment-variable fallback** (see "Refuse-to-start behavior" below).

```bash
# macOS Keychain / Linux SecretService / Windows Credential Manager:
keyring set codegenie anthropic_api_key
# Paste the key when prompted; nothing is echoed to the terminal.
```

On macOS this lands in the user's login keychain; on Linux it lands in
the active SecretService backend (gnome-keyring or KWallet). On
Windows it lands in the Credential Manager. The same `keyring get
codegenie anthropic_api_key` retrieval shape works across all three.

## Refuse-to-start behavior

`AnthropicLeafAdapter.__init__` calls `keyring.get_password("codegenie",
"anthropic_api_key")`. If the call returns `None` (key absent) or an
empty string, the constructor raises **without** consulting environment
variables. This is a load-bearing defensive choice per Phase-4
[ADR-0005](../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md)
(no SPKI pin; egress is defense-in-depth) and Phase-4
[ADR-0006](../phases/04-vuln-llm-fallback-rag/ADRs/0006-egress-guard-no-production-loopback-carveout.md)
(no production loopback carveout).

Refuse-to-start guards two attack surfaces simultaneously:

1. **CI secret leakage.** Even if a future CI job accidentally
   surfaces the key as `ANTHROPIC_API_KEY=...`, the adapter still
   refuses to start — the env var is never read.
2. **Local-dev drift.** A developer who clones the repo and runs the
   live-LLM tests without configuring the keyring gets an immediate
   loud failure rather than silent fallback to a stale env var.

The executable test asserting this lives at
`tests/integration/test_anthropic_leaf_refuse_on_missing_key.py` (or
the successor file the S3-02 attempt log named).

## Rotation cadence

Quarterly. The cassette-steward (named in
[`cassettes.md` § CODEOWNERS approval flow](cassettes.md)) coordinates
the rotation alongside any cassette refresh that quarter.

The rotation procedure is mechanical:

1. Generate a new key in the Anthropic console; keep the old key
   active.
2. Run `keyring set codegenie anthropic_api_key` to swap the local
   keyring entry.
3. Verify by running one cassette-replay test (replay does not call
   the API; this only confirms the keyring lookup succeeds).
4. Run one `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`
   pass to confirm live API access with the new key.
5. Revoke the old key in the Anthropic console.

## codegenie auth set

When the `codegenie auth` CLI ships (planned S3-02 follow-up), the
operator-facing surface becomes:

```bash
codegenie auth set anthropic
# Interactive prompt; same keyring write path; OS keychain unlock dialog
# fires on first call.
```

Until then the canonical path remains `keyring set codegenie
anthropic_api_key` documented above.

## See also

- [`../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md`](../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md)
- [`../phases/04-vuln-llm-fallback-rag/ADRs/0006-egress-guard-no-production-loopback-carveout.md`](../phases/04-vuln-llm-fallback-rag/ADRs/0006-egress-guard-no-production-loopback-carveout.md)
- [`./cassettes.md`](./cassettes.md) — cassette-steward role and rotation pairing.
