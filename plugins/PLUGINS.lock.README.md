# `PLUGINS.lock` — plugin tree integrity attestation

`PLUGINS.lock` is a JSON object mapping each registered plugin's `PluginId`
to the SHA-256 tree-digest of its directory under `plugins/`. The
`codegenie.plugins.loader` refuses to import any plugin whose on-disk
bytes do not match the digest attested here.

## Honest framing — Phase 3 ADR-0011

This is an **integrity check**, not a cryptographic signature. The lock
catches accidental corruption and partial-merge errors. It does **not**
verify the *identity* of whoever produced the bytes — a determined adversary
with write access to both `plugins/{slug}/` and this lockfile defeats the
check trivially.

Phase 11 substitutes [Sigstore](https://www.sigstore.dev/) signing at the
same `codegenie.plugins.verifiers.PluginVerifier` interface — zero edits
required to the loader. See ADR-0011 §Consequences.

CODEOWNERS at `.github/CODEOWNERS` gates edits to this file; the
PR template at `.github/PULL_REQUEST_TEMPLATE.md` carries the regeneration
checklist.

## Phase 3 state — empty

The lock ships empty (`{}`) in Phase 3. The first concrete plugin lands
in S7-01 (`vulnerability-remediation--node--npm`) with a real digest entry.
An empty lock with no plugin directories is the documented happy path:
`codegenie.plugins.loader.load_plugins` returns
`Ok(LoadReport(loaded=(), total_walked=0))`.

## Regeneration (lands in Phase 11)

Lock-file regeneration tooling (`codegenie plugins lock-update`) is deferred
to Phase 11 alongside the Sigstore migration. Until then, regenerate entries
manually:

```python
from pathlib import Path
from codegenie.plugins.loader import compute_plugin_tree_digest
print(compute_plugin_tree_digest(Path("plugins/<slug>")).unwrap())
```
