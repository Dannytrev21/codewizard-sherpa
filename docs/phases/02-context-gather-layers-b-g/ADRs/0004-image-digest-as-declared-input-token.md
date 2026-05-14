# ADR-0004: Image digest as a `declared_inputs` special token, not a `cache_key()` override

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** cache · declared-inputs · chokepoint-preservation · contract-fidelity · probe-context · additive-extension
**Related:** 02-ADR-0003, [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md), [Phase 0 ADR — declared_inputs cache key](../../00-bullet-tracer-foundations/ADRs/), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)

## Context

`RuntimeTraceProbe` (Phase 2 Layer C4) captures syscalls, loaded libraries, and shell invocations of the analyzed-repo's container under five scenarios. The probe's cache-correctness story is load-bearing: a `package.json`-only change (no Dockerfile change, image rebuilt with same digest) must cache-HIT; a `FROM`-line bump or a base-image rebuild (new digest) must cache-MISS. The signal that distinguishes the two cases is not in the Dockerfile bytes — it is in the **resolved image digest** that `docker build` produces. `localv2.md §4`'s `declared_inputs` is the single, universal cache-key derivation primitive; Phase 0's `Cache` reads files-by-glob from `declared_inputs` and derives the cache key from their content hashes plus `localv2.md §4`'s "special token" mechanism for non-filesystem inputs.

The performance lens proposed letting `RuntimeTraceProbe` **override `cache_key()` directly**, deviating from `declared_inputs` and introducing a parallel cache-key derivation pathway. The critic ([P] finding #6) flagged this as a structural deviation that future probes would copy: once one probe bypasses `declared_inputs`, the discipline becomes opt-out by convention rather than opt-in by chokepoint. Worse, `cache_key()` overrides hide the actual inputs from `tests/unit/test_cache_key_stability.py`'s structural checks.

The synthesis (`final-design.md §"Conflict-resolution table" row 9, 16`) picked the alternative: extend `declared_inputs` with a **special token** `image-digest:<resolved>` — exactly the special-token mechanism `localv2.md §4` already permits. The resolved digest is supplied via a new optional callable on `ProbeContext` (`image_digest_resolver: Callable[[Path], str | None] | None = None`), mirroring [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md)'s `parsed_manifest` precedent: one optional callable, default `None`, defensive-check at the call site, ADR-gated. This is the **one** `ProbeContext` field Phase 2 adds; the `Probe` ABC itself stays untouched.

## Options considered

- **Option A — Override `cache_key()` on `RuntimeTraceProbe`; bypass `declared_inputs` for the image-digest signal.** **Pattern:** none (chokepoint bypass). Performance lens's pick. Two cache-key derivation pathways exist; future probes copy the override; `localv2.md §4` discipline survives only by convention.
- **Option B — Compute the image digest **inside the probe**, then add it as an in-memory amendment to a probe-private cache key.** **Pattern:** Strategy at the cache layer. Same structural problem as Option A: the chokepoint sees one signal; the probe maintains a second.
- **Option C — Make `RuntimeTraceProbe.declared_inputs` include `Dockerfile` and `.codegenie/scenarios.yaml` only; accept that a base-image rebuild silently cache-HITs until the Dockerfile is edited.** Best-practices lens's pick (silent). Wrong: the probe-quality regression is invisible to the operator; B2 might not catch it.
- **Option D — Extend `declared_inputs` with a special token `image-digest:<resolved>`; resolve via an optional `ProbeContext.image_digest_resolver` callable mirroring [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md).** **Pattern:** Additive extension at the right layer + Open/Closed for `declared_inputs`. Synthesis pick. Same cache pathway for all probes; one auditable chokepoint; the special-token mechanism `localv2.md §4` already permits.

## Decision

Adopt **Option D**. `RuntimeTraceProbe.declared_inputs` lists `["Dockerfile", ".codegenie/scenarios.yaml", "image-digest:<resolved>"]`. The `image-digest:` token is a `localv2.md §4` special-token form; the Phase 0 `Cache` layer recognizes the token prefix and resolves it via `ProbeContext.image_digest_resolver(repo_root) -> str | None`, a new optional callable on `ProbeContext` defaulting to `None`. Probes that don't need it ignore it (the field is `Optional`); the cache layer falls back to declared-input file globs when the resolver is `None` or returns `None`. **`cache_key()` is NOT overridden on any probe.** The contract surface `localv2.md §4` froze is preserved by addition, not by bypass. **Pattern: Additive extension at the right layer — special-token mechanism already permitted; one optional callable mirroring [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md).**

## Tradeoffs

| Gain | Cost |
|---|---|
| `declared_inputs` remains the **single** cache-key derivation primitive across all probes — Phase 0 I1 contract preserved verbatim ([production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)'s deterministic-gather commitment) | One new optional callable on `ProbeContext` — `ProbeContext` grows by one field (now `parsed_manifest` + `image_digest_resolver`); the precedent for "Phase N adds one optional callable per phase" is now twice-set, and a Phase 3+ addition follows the same shape |
| Mirrors [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md) precedent exactly — `parsed_manifest` callable was the additive-optional shape; this ADR uses the same shape for `image_digest_resolver`. The "what's allowed on ProbeContext" pattern is now load-bearing precedent | A reader scanning `ProbeContext` sees two `Callable | None = None` fields; the discipline is "every such field is ADR-gated, additive, and defaults to None" — that discipline must be enforced in code review since the type system can't refuse a third arbitrary callable |
| `image-digest:` is a `localv2.md §4`-permitted special token; the Phase 0 `Cache` layer's special-token resolution path is the natural extension point | The Phase 0 `Cache` layer gains a token-recognizer dispatch; today there is one token type (`image-digest:`), so the dispatch is a one-arm `match` — but the shape ratchets if more special-tokens are added later (Phase 7's distroless target manifest? Phase 14's cross-repo SCIP?) |
| A `package.json`-only change with the image rebuilt-and-pushed-with-same-digest cache-HITs correctly; a `FROM`-line change with the same Dockerfile bytes but different resolved digest cache-MISSES correctly — the user's mental model ("changing the image invalidates trace cache") is faithfully encoded | The resolver's failure mode is silent if the implementer returns `None` carelessly — `tests/adv/phase02/test_image_digest_drift.py` (load-bearing adversarial) is the structural check that mutating the built image between gathers invalidates tier-C caches |
| C-tier probes (`syft`, `grype`, `runtime_trace`) all benefit — `SyftProbe` and `GrypeProbe` declare the same token; they share cache invalidation with `RuntimeTraceProbe` when the image digest changes | Three probes now depend on the same optional callable being supplied; if the coordinator forgets to bind `image_digest_resolver`, all three silently fall back to declared-input files only. Mitigation: the resolver is bound once at coordinator setup; tests cover the absence path explicitly |
| Phase 3+ probes that need cache invalidation against an opaque external signal (e.g., a Phase 7 distroless-target manifest fingerprint, a Phase 14 cross-repo SCIP head) can extend `declared_inputs` with their own special token + a new optional `ProbeContext` callable — the precedent is now twice-set and the shape is bounded | Future special tokens require their own ADR amendment to this one (or [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md)) — the friction is the point; ad-hoc `ProbeContext` growth is refused |

## Pattern fit

Pattern: **Additive extension at the right layer + Open/Closed for `declared_inputs`** (`design-patterns-toolkit.md §"Open/Closed Principle"`). The toolkit's prescription — "open for extension, closed for modification … adding a new feature should not require editing existing code" — is honored exactly: `declared_inputs` is unchanged in shape (still a `list[str]`); the special-token semantics are unchanged in mechanism (`localv2.md §4` already names the form); `ProbeContext`'s additive-optional shape was set by [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md). The pattern's failure mode the toolkit warns against ("the central `dispatch_task_class(name)` function has a `match name` block that grows every time") is bounded: the Phase 0 `Cache`'s token-recognizer is a one-arm match today; new tokens add arms via ADR amendment, not silent edits. Composes with **Tagged union for state** discipline — `image_digest_resolver: Callable[[Path], str | None] | None` is honest about both "I might not be supplied" and "I might not resolve."

## Consequences

- `src/codegenie/probes/base.py` (`ProbeContext` dataclass) gains one field: `image_digest_resolver: Callable[[Path], str | None] | None = None`. The `Probe` ABC itself is **not edited** (Phase 0 contract-freeze snapshot still passes).
- `src/codegenie/cache.py` (Phase 0) gains a token-recognizer dispatch in `_resolve_declared_inputs`. Tokens are recognized by the `<name>:<value>` syntax; today's one token (`image-digest:`) is resolved by calling `ctx.image_digest_resolver(repo_root)`. Unknown tokens raise `CacheKeyError(reason="unknown_special_token", token=…)` — fail-loud per Rule 12.
- `RuntimeTraceProbe.declared_inputs` lists the token; if the resolver is `None` or returns `None` (e.g., no image built yet), the probe emits `confidence="unavailable"` and the cache key falls back to file globs only.
- `SyftProbe` and `GrypeProbe` declare the same `image-digest:` token in `declared_inputs`; cache invalidation is shared with `RuntimeTraceProbe` correctly.
- `tests/adv/phase02/test_image_digest_drift.py` (load-bearing adversarial) asserts: mutating the built image between gathers invalidates tier-C caches; the same Dockerfile bytes with a new digest produce a different cache key.
- `tests/unit/test_cache_key_stability.py` (Phase 0) is extended — not edited — with the special-token round-trip cases.
- The performance-lens-proposed `cache_key()` override hook stays rejected. Phase 0's chokepoint is preserved; a Phase 3+ probe that wants cache invalidation against an opaque signal extends `declared_inputs` with its own special token (and adds an optional `ProbeContext` callable via a new ADR amendment to this one).
- The pattern is now **twice-precedented** (Phase 1's `parsed_manifest` + Phase 2's `image_digest_resolver`); a Phase 3 addition of a third optional callable carries the burden of ADR-gating + naming the named-trigger probe. Ad-hoc growth is refused; the precedent is auditable.

## Reversibility

**Medium-high.** Removing the `image-digest:` token is a `RuntimeTraceProbe.declared_inputs` edit + a `Cache` dispatch arm deletion + a `ProbeContext.image_digest_resolver` field removal (or default-`None`-and-never-set). The probe degrades to file-only cache keys — base-image-rebuild silent cache-HITs would return, but the structural rollback is small. The harder reversal is changing the special-token *syntax* (e.g., to `${image-digest}` or some YAML-ish escape); that would require coordinated edits across `declared_inputs` literals in probe modules — but no such reshape is contemplated, and `localv2.md §4` already pinned the `<name>:<value>` form.

## Evidence / sources

- `../final-design.md §"Conflict-resolution table" row 9, row 16` — `cache_key` strategy + `RuntimeTraceProbe` cache-key shape
- `../final-design.md §"Components" #6 RuntimeTraceProbe` — cache-key special-token rationale
- `../final-design.md §"Departures from all three inputs" #2` — image digest as declared-input special token (not as cache-key override)
- `../phase-arch-design.md §"Component design" #6` — `ProbeContext.image_digest_resolver` as the one Phase-2 `ProbeContext` addition
- `../phase-arch-design.md §"Data model"` — explicit single-field `ProbeContext` extension
- `../phase-arch-design.md §"Edge cases" row 14` — image-digest resolver returns `None` path
- `../critique.md §"Attacks on the performance-first design" #6` — `cache_key()` bypass framing
- [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md) — additive-optional `ProbeContext` precedent
- [`localv2.md` §4](../../../localv2.md) — special-token mechanism in `declared_inputs`
- [Production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — deterministic-gather commitment that `declared_inputs` operationalizes
