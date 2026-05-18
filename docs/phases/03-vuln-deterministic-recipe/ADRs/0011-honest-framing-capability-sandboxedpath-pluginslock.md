# ADR-0011: Honest framing — `Capability` is audit + lint (NOT runtime-unforgeable); `SandboxedPath` is in-jail-at-construction (NOT in-jail-forever); `PLUGINS.lock` is integrity check (NOT cryptographic signature)

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** threat-model · honest-framing · capability · capability-claim-discipline · phase-11-precursor
**Related:** [0006](0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

The security-first lens design (`design-security.md`) made three claims the critic correctly attacked in `critique.md §Attacks on the security-first design`:

1. **`*Capability` tokens are "unforgeable at runtime."** False. Pydantic models can be constructed anywhere in the codebase that imports them; the type system doesn't know its caller. A determined plugin author can `NpmInstallCapability(registry="...")` directly, bypassing `mint()`.
2. **`SandboxedPath` "makes illegal states unrepresentable" (in-jail forever).** False. `Path.resolve(strict=True)` resolves symlinks at constructor time, but a symlink swap between `create()` and `open()` re-introduces the TOCTOU. The path is in-jail *at construction*, not forever.
3. **`PLUGINS.lock` is a "signature".** False. It's a SHA-256 tree-hash; a committer with write access who updates both the plugin tree AND `PLUGINS.lock` passes the runtime check. "Signature" implies a private-key-signed assertion verifiable without trusting the committer; this is not that.

The critic correctly argued that overclaiming security properties is worse than honest framing because:
- Downstream phases (Phase 5 retry envelope; Phase 11 PR creation) build on top of these primitives and may assume properties that don't hold.
- An operator reading the docs and trusting "unforgeable" makes worse decisions than one trusting "audited."
- The actual mitigations (lint enforcement, `O_NOFOLLOW`, CODEOWNERS + PR review) are useful but only if framed as what they are.

The architecture spec resolves it via **honest framing** (`phase-arch-design.md §Component design C10`, §Tradeoffs, §Departures from all three inputs #9 + #12): the primitives ship, the docs and ADRs describe what they actually do, and the gaps are made explicit.

## Options considered

- **Option A — Adopt security's framing verbatim ("unforgeable", "unrepresentable", "signature").** **Pattern:** Capability pattern, overclaimed. Downstream phases inherit assumptions that don't hold. Worse than no claim because it stops the next reader from asking the right questions.
- **Option B — Drop the primitives entirely; rely on convention.** **Pattern:** No defense. Loses the genuine value of capability audit trails, `O_NOFOLLOW` second-line defense, and SHA-256 integrity-check (which catches real accidental corruption).
- **Option C — Ship the primitives with downgraded, honest framing.** `Capability` = "audit + lint enforcement, NOT runtime unforgeability"; `SandboxedPath` = "in-jail at construction, second-line defense at `open()` time via `O_NOFOLLOW`"; `PLUGINS.lock` = "integrity check (catches accidental corruption), NOT cryptographic signing — Phase 11 ships Sigstore." **Pattern:** Honest capability pattern — claims match what the implementation actually delivers.

## Decision

Adopt **Option C.** Three primitives ship with explicit framing:

### Capability tokens

`NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability`, `CapabilityBundle` are typed Pydantic models. Their value is:
- **Audit trail** — `mint()` is the single chokepoint that emits a `CapabilityMinted` spanning event; `CapabilityUsed` events tie operations to capability use.
- **Lint enforcement** — a custom `ruff` rule (`tooling/ruff_rules/no_capability_construction.py`) AST-walks `src/` + `plugins/` and fails on any `*Capability(...)` construction outside `capabilities.py` or `tests/`.

**Framed as:** audit + lint, NOT runtime unforgeability. Threat model assumes first-party plugins.

`GitLocalOpsCapability` has **no `push` field**; minting one is type-impossible. This IS a real type-level invariant for one specific operation (per ADR-0009 humans-always-merge).

### `SandboxedPath`

`SandboxedPath.create(jail, relative)` resolves with `strict=True`, checks `is_relative_to(jail)`, returns `Result[SandboxedPath, PathEscape]`. `open()` always uses `O_NOFOLLOW`.

**Framed as:** in-jail at construction, second-line defense at `open()` time via `O_NOFOLLOW`. Consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected` (workflow-internal event). TOCTOU is real and acknowledged.

### `PLUGINS.lock`

Per-plugin tree SHA-256 digests recomputed at loader startup. Mismatch → `PluginRejected(integrity_mismatch)` + exit 4.

**Framed as:** integrity check (detects accidental corruption, partial merges, file-system damage), NOT cryptographic signing. CODEOWNERS on `plugins/PLUGINS.lock` + PR review is the social anchor. Phase 11 ships Sigstore-based plugin signing (production roadmap).

## Tradeoffs

| Gain | Cost |
|---|---|
| Downstream phases (Phase 5, Phase 11) build on what the primitives actually deliver; no inherited overclaim | First-time reader may wonder why Phase 3 ships a `Capability` "system" that is "only" audit + lint — answer is in this ADR |
| The lint rule + audit trail is the real defense against accidental capability misuse; the framing matches the mechanism | A determined adversary with commit access still wins; threat model documents this explicitly |
| `O_NOFOLLOW` is a meaningful second-line defense — caught at `open()` time, raises typed `FilesystemRaceDetected` event | Every consumer of `SandboxedPath.open()` must handle `OSError(errno=ELOOP)`; lint or fence catches missed cases |
| `PLUGINS.lock` integrity check catches accidental drift (a contributor edits a plugin file but forgets to regenerate the lock) — real value | "Integrity check" sounds weaker than "signature"; messaging discipline needed in docs |
| Phase 11's Sigstore work has a clear seam to plug into — replaces the SHA-256 tree digest with a real signature verification | Two-stage migration: Phase 3 ships integrity check; Phase 11 substitutes signing. Documented forward path |
| `GitLocalOpsCapability` without `push` is a real type-level invariant for the one operation that matters most — humans always merge (ADR-0009) | One token has stronger semantics than the others; convention "no `push` here means no `push` anywhere" is doc + lint, not type |

## Pattern fit

Implements **Capability pattern** (toolkit §Composition / coupling patterns) at the *audit-trail-and-lint-enforcement* tier — the pattern recognized for what it actually delivers in a Python codebase without runtime privilege separation. Avoids the failure mode "every capability check is a runtime guarantee even when it's just a typed wrapper around a `dict`." Rejects security's overclaim ("Capability" framed as "unforgeable") which would be the toolkit's "is_admin boolean checked everywhere" failure mode wearing a wrapper — namely, a token system trusted as a runtime guarantee that doesn't enforce anything at runtime.

## Consequences

- `src/codegenie/plugins/capabilities.py` houses `mint()` and the capability types; `tooling/ruff_rules/no_capability_construction.py` enforces the lint.
- `src/codegenie/plugins/sandbox_path.py` ships `SandboxedPath.create` (returning `Result`) and `SandboxedPath.open` (always `O_NOFOLLOW`); `tests/unit/plugins/test_sandbox_path.py` exercises the TOCTOU swap via deliberate fixture.
- `src/codegenie/plugins/loader.py` performs per-plugin SHA-256 tree digest verification on startup; mismatch raises `PluginRejected(integrity_mismatch)`.
- `tests/static/test_capability_fence.py` runs the ruff custom rule across the repo as a CI-gating check.
- `CODEOWNERS` includes `plugins/PLUGINS.lock` mapped to the platform team; PR template calls out lockfile changes.
- The docs framing this ADR establishes is reused verbatim in operator runbooks — "audit + lint" not "unforgeable"; "integrity check" not "signature."
- Phase 11 substitutes `PLUGINS.lock` with Sigstore signing; the loader interface stays the same (`verify_plugin(plugin_dir) -> Result[None, VerificationError]`).
- Phase 5's gate policy can read `CapabilityUsed` events to enforce per-workflow capability budgets — the audit trail is the substrate.

## Reversibility

**High (for framing).** Re-framing is a docs-only change; no code change required to switch the prose. **Medium (for the primitives).** Removing the capability types entirely would lose the audit trail and lint scaffold; adding Phase 11's Sigstore signing substitutes one verification mechanism for another via the loader interface.

## Evidence / sources

- `../phase-arch-design.md §Component design C10`, §Tradeoffs, §Departures from all three inputs #9 + #12
- `../final-design.md §Synthesis ledger rows "Capability tokens"` (score 15/15), "`SandboxedPath` framing" (score 15/15), "Plugin loader trust model" (score 13/15)
- `../critique.md §Attacks on the security-first design — capability + sandbox-path overclaim + signature mislabel`, §Misapplied patterns
- [production ADR-0009 — humans always merge](../../../production/adrs/0009-humans-always-merge.md)
- design-patterns-toolkit.md §Capability pattern (with failure-mode callout)
