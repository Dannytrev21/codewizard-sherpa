# ADR-0005: Add `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker` to `exec.ALLOWED_BINARIES`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** tool-use · security · allowlist · localv2-conformance · extension-seam
**Related:** [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-subprocess-allowlist.md), [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md), ADR-0003, ADR-0004

## Context

Phase 0 introduced `src/codegenie/exec.ALLOWED_BINARIES` as the *single* sanctioned mechanism for invoking external CLIs (Phase 0 ADR-0006). Phase 1 added `node` to that list with one ADR per binary (Phase 1 ADR-0001). The discipline: every new external binary requires its own ADR documenting the threat surface, invocation pattern, and `--version` cross-check policy.

Phase 2 needs six new entries: `scip-typescript` (Layer B semantic index), `semgrep` (Layer G SAST), `syft` (Layer C SBOM), `grype` (Layer C CVE), `gitleaks` (Layer G secret scanning), `docker` (Layer C image build for SBOM). Each is named in `roadmap.md Phase 2` tooling list or in `localv2.md §6`.

The synthesis chose **one combined ADR with per-binary subsections** rather than six separate ADRs (`final-design.md "Roadmap coherence check" New ADRs implied`, item 5). Rationale: review burden for six near-identical "add binary X to allowlist" ADRs is high; the threat surface analysis differs only in detail; one ADR can document the per-binary subsections without diluting the precedent that each addition is named and justified.

## Options considered

- **Six separate ADRs, one per binary.** Strict adherence to Phase 1's precedent. Six PRs of ~50 lines each. Each is reviewable in isolation; each can be amended independently. Reviewer fatigue and search dilution are real costs.
- **One combined ADR with six subsections.** Centralized; less per-binary granularity for amendments. Easier to discover ("which binaries did Phase 2 add?"). Mirrors how Phase 0's original `ALLOWED_BINARIES` listing landed (one ADR, multiple binaries).
- **No ADR for binaries that have already been justified in `roadmap.md`.** Phase 1's discipline rejects this: every `ALLOWED_BINARIES` mutation is ADR-gated regardless of upstream justification.

## Decision

**Phase 2 lands one combined ADR (this one) extending `src/codegenie/exec.ALLOWED_BINARIES` with six binaries**, each documented in its own subsection below. The discipline holds: every binary appears here with threat surface, invocation pattern, `--version` cross-check policy, and sandbox profile.

The combined-ADR shape is a synthesis choice for review burden; Phase 7's distroless tools (`crane`, `cosign`, `chainctl`) and any future binary additions can land as either combined or per-binary, at the implementer's discretion, *as long as each binary is named in its own subsection*.

### `scip-typescript`

- **Phase 2 role:** Layer B semantic index. `SCIPIndexProbe` invokes it via `tools.scip_typescript.run(...)`.
- **Threat surface:** Code-loading interpreter (runs TypeScript compiler); attacker-controlled bytes via `tsconfig.json`, `package.json`, source files. `tsconfig extends:` traversal is a documented attack (`design-security.md`).
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/scip_typescript.py`. Sandbox: `network="none"`; `--ro-bind <repo>`; `--tmpfs /tmp`; env-strip (per ADR-0003).
- **`--version` cross-check:** Wrapper invokes `scip-typescript --version` at first call and verifies against `catalogs/tools/digests.yaml#scip-typescript` (ADR-0004). Mismatch → `ToolDigestMismatch` (typed exception).
- **Digest cache-key contribution:** Yes (ADR-0004).

### `semgrep`

- **Phase 2 role:** Layer G SAST. `SemgrepProbe` invokes it via `tools.semgrep.run(...)`.
- **Threat surface:** Code-loading interpreter (parses TS/JS into AST); rule packs are themselves YAML and can contain pathological regex (ReDoS). Hostile custom rule under `.codegenie/semgrep-rules/` is a documented attack (`tests/adv/test_semgrep_redos.py`).
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/semgrep.py`. Sandbox: `network="none"`; `SEMGREP_RULES_CACHE=<pinned-dir>`; `--disable-version-check --disable-metrics` mandatory. Rule packs pre-warmed at install time from pinned digests.
- **`--version` cross-check:** Same shape as `scip-typescript`.
- **Digest cache-key contribution:** Yes; rule-pack version is a separate cache-key field.

### `syft`

- **Phase 2 role:** Layer C SBOM. `SyftSBOMProbe` invokes it via `tools.syft.run(...)`.
- **Threat surface:** Container image scanner; parses image manifests, layer tarballs, package-manager metadata from inside images. Zip-bomb in a COPY layer is a documented attack (`tests/adv/test_syft_zipbomb.py`).
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/syft.py`. Sandbox: `network="scoped"` (only the configured base-image registry host on allowlist) during base-image pull; `network="none"` during scan.
- **`--version` cross-check:** Same shape.
- **Digest cache-key contribution:** Yes.

### `grype`

- **Phase 2 role:** Layer C CVE scan. `GrypeCVEProbe` invokes it via `tools.grype.run(...)`.
- **Threat surface:** CVE-DB consumer; parses SBOM JSON; reads vuln-DB sqlite (digest-pinned via `tools/grype-db-listing.signed.json`).
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/grype.py`. Sandbox: `network="none"` for scan; `network="scoped"` for `grype db update` on cache miss only. DB integrity verified against the in-tree signed listing.
- **`--version` cross-check:** Same shape.
- **Digest cache-key contribution:** Yes; vuln-DB digest is a separate cache-key field.

### `gitleaks`

- **Phase 2 role:** Layer G secret scanning (G6 — added in Phase 2 per roadmap; not in `localv2.md` Layer G enumeration). `GitleaksProbe` invokes it via `tools.gitleaks.run(...)`.
- **Threat surface:** Reads every file under the analyzed repo; regex-based; `--redact` discipline must be enforced or matched secrets reach disk.
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/gitleaks.py`. Sandbox: `network="none"`. Wrapper enforces `--redact` mandatory; CI test asserts (`tests/adv/test_gitleaks_redaction_invariant.py`).
- **`--version` cross-check:** Same shape.
- **Digest cache-key contribution:** Yes.

### `docker`

- **Phase 2 role:** Image build for `SyftSBOMProbe` (C2). The probe is the only consumer; `tools.docker.build(...)` is the only entry point.
- **Threat surface:** Largest of the six. `docker build` opens a Unix socket to the host daemon (or uses `buildx` driver). Hostile Dockerfile `RUN curl | sh` is a documented attack (`tests/adv/test_hostile_dockerfile_curl.py`). The host-daemon coupling is the open question (`final-design.md "Open questions deferred to implementation"` #1).
- **Invocation pattern:** Subprocess only. Wrapper at `src/codegenie/tools/docker.py`. Sandbox: `--network=none` for build phase; `--network=scoped` for the initial base-image pull only. Build context: `<repo>` (ro-bound). If `docker buildx` with `--driver=docker-container` proves required to escape the host-daemon-socket coupling, the wrapper picks that driver; otherwise default `docker build`.
- **`--version` cross-check:** Same shape.
- **Digest cache-key contribution:** Yes; the produced image digest is recorded in the SBOM cache-key composition.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 0 ADR-0006's `ALLOWED_BINARIES` chokepoint discipline holds — no subprocess outside the allowlist | Six new binaries means six new install-gate verifications (ADR-0004) and six new wrappers; the Phase 1 model scales by addition |
| One combined ADR is faster to review than six near-identical ones; per-binary subsections keep granular traceability | Future amendments to a single binary's policy require editing this file rather than a per-binary ADR; mitigated by per-subsection sections |
| Each binary's invocation is centralized in `src/codegenie/tools/<tool>.py`; threat surface analysis lives near the wrapper | Six wrappers means six small modules instead of one large one; single-responsibility wins (`final-design.md "Components" #1`) |
| The `--version` cross-check + digest pinning (ADR-0004) form a belt-and-suspenders integrity check | Adds startup cost (~50 ms per first-tool-call cross-check); amortized over the gather |
| `docker` is the most consequential addition; its sandbox posture (`--network=none` for build) is documented explicitly | The host-daemon coupling for `docker build` is unresolved; the open-question fallback is `confidence: low` with structured warning |

## Consequences

- `src/codegenie/exec.py#ALLOWED_BINARIES` extends with six entries (one diff; Phase 0 ADR-0006's frozen allowlist mutation seam).
- Six wrappers ship in `src/codegenie/tools/`: `scip_typescript.py`, `semgrep.py`, `syft.py`, `grype.py`, `gitleaks.py`, `docker.py`. Each ~80 LOC; each with ≥ 4 unit tests against recorded fixture stdouts (per `final-design.md "Test plan" Per CLI wrapper`).
- The install-gate (ADR-0004) verifies all six digests on every CI install.
- `tests/adv/` ships at least one hostile-input fixture per binary; per-binary tests above are named.
- Phase 7's distroless tools (`crane`, `cosign`, `chainctl`) will extend `ALLOWED_BINARIES` by a Phase-7 ADR (either combined or per-binary at the implementer's discretion).
- The `docker` open question (`final-design.md` open question #1) is tracked here for implementation-time resolution: if `docker build` opens the host daemon socket in a way the sandbox cannot constrain, the C2 probe falls back to `confidence: low` and gather completes; the implementer surfaces a structured warning identifying the daemon-coupling failure mode.

## Reversibility

**Low.** Removing a binary from `ALLOWED_BINARIES` requires removing the wrapper, the probe that uses the wrapper, and re-routing the probe's evidence (or accepting that the slice is unsourced). For `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `docker` — every one is the load-bearing tool for a probe whose slice the roadmap names. Reversal is phase-replanning, not ADR-amending.

## Evidence / sources

- `../final-design.md "Goals (concrete, measurable)"` Extension-by-addition bullet — the explicit `ALLOWED_BINARIES` edit
- `../final-design.md "Components" #1, #2` — tools/ wrappers and sandbox profile
- `../final-design.md "Roadmap coherence check" New ADRs implied` #5 — the combined-ADR choice
- `../phase-arch-design.md "Goals" #14` — the explicit Phase-0/1 edits
- `roadmap.md Phase 2` — tooling list naming the six binaries
- `localv2.md §6` — external tool dependency enumeration
- [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-subprocess-allowlist.md) — the allowlist chokepoint
- [Phase 1 ADR-0001](../../01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md) — the per-binary precedent
- ADR-0003 — the sandbox profile each binary runs under
- ADR-0004 — the digest pinning each binary participates in
