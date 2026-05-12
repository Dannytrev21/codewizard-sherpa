# ADR-0004: `tools/digests.yaml` binary pin manifest with install-gate verification and cache-key inclusion

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** supply-chain · cache-invalidation · security · catalog · install-gate
**Related:** [Phase 1 ADR-0006](../../01-context-gather-layer-a-node/ADRs/0006-native-module-catalog-versioning.md), [production ADR-0006](../../../production/adrs/0006-deterministic-gather-no-llm.md), ADR-0005, ADR-0011

## Context

Phase 2 introduces six external CLIs (`scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker`) plus tree-sitter grammar wheels. Each is a code-loading interpreter running attacker-controlled bytes (`final-design.md "Lens summary"`). A drift in tool version — whether silent (a CI runner upgrade) or hostile (a binary swap mid-install) — changes probe output without invalidating any cache. The cache-key composition that Phase 1 settled (`(probe_name, probe_version, sub_schema_version, content_hashes, lockfile_hash)`) was complete for in-process Python parsers; for subprocess tools whose outputs *are* the evidence, it is not.

The performance and security lenses converged on tool-digest pinning (`design-security.md §"tools/digests.yaml"`, `design-performance.md` cache-key composition for SCIPIndex/Semgrep/Syft/Grype); the best-practices lens was silent. The critic did not attack this directly but its scope (six binaries, ~10 wheel hashes, a CI install gate, a per-probe cache-key extension) deserves an ADR because it changes the per-probe cache-key derivation and adds a CI gating mechanism that future tool additions must conform to.

A silently-stale binary on a CI runner is the worst failure mode the gather pipeline can suffer — `production design.md §2` "Honest confidence" says staleness must be detectable. `IndexHealthProbe` (B2) reports `tool_digest_in_use` per domain; that only catches drift *after* the gather runs. Pre-gather, the install gate must reject a runner whose tools don't match the pinned digests.

## Options considered

- **Tool version strings only (`semgrep 1.78.0`).** Cheapest; what most projects do. A version-string match against a different binary (release-channel swap, build-flag drift) is undetectable; the cache happily reuses stale evidence.
- **Per-probe pinned tool version, no digest, no install gate.** Better than nothing; still vulnerable to binary drift within a version label; no CI signal until B2 runs.
- **`tools/digests.yaml` SHA-256 pin manifest + install-gate verification + cache-key inclusion [S+P].** Strongest. Adds CI mechanism; adds catalog file to maintain; cache invalidates probe-side on any drift.

## Decision

**Phase 2 ships `src/codegenie/catalogs/tools/digests.yaml`** enumerating SHA-256 digests for `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, plus tree-sitter grammar wheel hashes (cross-checked against `uv.lock`). The manifest:

- **Is the source of truth for tool integrity.** Every Phase 2 cache key for a probe that calls a tool includes the relevant `tool_digest` field from this catalog (`SCIPIndexProbe` keys include `scip-typescript` digest; `SemgrepProbe` keys include `semgrep` digest; etc.).
- **Has a `catalog_version: int` field.** Following Phase 1 ADR-0006's pattern, the `catalog_version` participates in cache keys for *every probe that references this catalog*. A digest change is a minor bump; an entry addition is a minor bump; an entry removal is a major bump (probe + sub-schema bump together).
- **Is enforced at install time.** A CI install-gate script (`scripts/verify_tool_digests.py`) runs `<tool> --version`-and-`sha256sum <tool>` style checks on every install and compares to the manifest. Mismatch → fail loud, release gate trips.
- **Lives under `catalogs/tools/`.** Same package shape as Phase 1's `catalogs/native_modules.yaml`. Same authoring discipline.

Tree-sitter grammar wheels are pinned by hash in `uv.lock` *and* cross-checked against `tools/digests.yaml#grammars`. The double pin is intentional: `uv.lock` is the operational truth; `digests.yaml` is the audit truth.

`grype`'s vulnerability database is **separately pinned** via `tools/grype-db-listing.signed.json` (in-tree pin file): `grype db check` against the listing on every gather start; mismatch on cache miss forces `grype db update`, which is the one network-egress path Phase 2 sanctions (`final-design.md §"Goals" no-outbound-network` bullet; ADR-0003).

## Tradeoffs

| Gain | Cost |
|---|---|
| Silent tool drift on a CI runner fails the install gate, not a probe — surfaces before the gather even starts | Updating a tool now requires two diffs: `pyproject.toml` (or system-install procedure) and `tools/digests.yaml`; the catalog grows |
| Cache invalidation is automatic on any digest change — no probe has to remember to bump its `probe_version` when its tool upgrades | Cross-platform digests can differ (Linux vs macOS binaries); the catalog must enumerate per-platform digests or commit to a single supported platform for verification |
| `tools/digests.yaml#catalog_version` propagates via Phase 1 ADR-0006's catalog-versioning pattern; no new cache-invalidation mechanism | The catalog becomes a hot edit point; conflicts on simultaneous tool bumps must be resolved manually |
| Tree-sitter wheels are double-pinned (uv.lock + digests.yaml) — supply-chain audit has both operational and review surfaces | Tree-sitter grammar bumps need both files updated; CI cross-check (`tests/integration/test_tree_sitter_digests_consistent.py`) is required |
| `grype`'s vuln-DB separately pinned via signed listing — DB drift is detectable and triggers `grype db update`, the one sanctioned egress | DB pinning introduces a second pin file and a separate update cadence; documented in `tools/digests.yaml`'s sibling README |
| Future Phase 7 (distroless) tools (`crane`, `cosign`, `chainctl`) land in this catalog by extension — discipline scales | Phase 7's tool additions must each pass the install-gate and a Phase-7 ADR amendment to this one or a new ADR |

## Consequences

- `src/codegenie/catalogs/tools/digests.yaml` ships in Phase 2 with the six binaries + grammar wheel hashes + `catalog_version: 1`.
- `scripts/verify_tool_digests.py` is a CI artifact; the `phase2-install` CI job invokes it before any test runs.
- Each Phase 2 probe wrapping a tool reads its tool digest at coordinator init (via a small `tools/digests.get(name)` helper) and includes it in the probe's cache-key tuple.
- Phase 7's distroless work extends this catalog by addition (`chainctl`, `cosign`, `crane` if needed); a new ADR captures Phase 7's pinning additions.
- A tool CVE flow: vendor publishes patched binary → operator updates `tools/digests.yaml` with new SHA-256 → CI install gate passes → every Phase 2 probe that uses that tool invalidates its cache on first run → fresh evidence. The "supply chain integrity > automatic patching" stance from `design-security.md` is honored.
- `tests/integration/test_cache_key_includes_tool_digests.py` (Hypothesis property test) asserts any digest mutation ⇒ cache-key change for every probe-tool pair.
- The `grype-db-listing.signed.json` pin file lives alongside `digests.yaml`; signature verification logic lives in `src/codegenie/tools/grype.py`.

## Reversibility

**Medium.** Removing the digest pinning is mechanically additive-reversed — delete the file, remove the cache-key contribution, remove the install gate. But every Phase 2 probe's cache key has been *salted* with the digest; ripping it out invalidates every cached `ProbeOutput` once. The cost is a single recache, not data loss. The install gate's removal is more consequential: silent tool drift returns as a failure mode. Most likely future evolution is *extension* (Phase 7+ tools added to the manifest), not removal.

## Evidence / sources

- `../final-design.md "Goals (concrete, measurable)"` Tool-digest-pinning bullet
- `../final-design.md "Components" #8 Cache layer extension` — digest in cache-key
- `../final-design.md "Conflict-resolution table" D14, D16` — adjacent decisions
- `../phase-arch-design.md "Goals" #7` — the pinning statement
- `../phase-arch-design.md "Components" §10 AuditWriter` — digest auditing
- [Phase 1 ADR-0006](../../01-context-gather-layer-a-node/ADRs/0006-native-module-catalog-versioning.md) — the catalog-versioning pattern this ADR generalizes
- [production ADR-0006](../../../production/adrs/0006-deterministic-gather-no-llm.md) — the deterministic-gather invariant this defends
