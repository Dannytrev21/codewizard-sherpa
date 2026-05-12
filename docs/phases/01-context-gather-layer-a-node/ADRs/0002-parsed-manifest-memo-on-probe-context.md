# ADR-0002: `ParsedManifestMemo` on `ProbeContext` — in-coordinator per-gather parse memo

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** coordinator · probe-context · performance · chokepoint-preservation
**Related:** ADR-0008, [Phase 0 ADR-0009](../../00-bullet-tracer-foundations/ADRs/0009-cache-hit-pass-through-coordinator-output.md), [Phase 0 ADR-0010](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md)

## Context

Four Phase 1 probes (`LanguageDetection` extended, `NodeBuildSystem`, `NodeManifest`, `TestInventory`) read `package.json`. The critic's cross-design observation #3 (`final-design.md "Shared blind spots considered"` #3) names the gap directly: "All three lenses accept reading `package.json` more than once per gather; none uses the cheapest, cleanest seam." On the cache-miss warm path that's three parses of the same bytes per gather — ~15 ms of pure duplicate work, plus the surface area of three independent cap-and-validate paths drifting.

The performance lens proposed `.parsed/package.json.msgpack` written to `ctx.workspace` as a side-channel. The critic rejected this (`critique.md "Attacks on the performance-first design"` #2): it bypasses `_ProbeOutputValidator` (Phase 0 ADR-0010) and `OutputSanitizer` (Phase 0 ADR-0008) — Phase 0's two structural trust boundaries on every `ProbeOutput`-shaped byte that hits disk.

The security lens's sandbox would force re-parse per fork ([final-design] "Conflict-resolution table" row 1 rejects the sandbox entirely; see ADR-0008). The best-practices lens accepted the triple parse explicitly. None of the three lenses proposed a coordinator-internal memo — it surfaced as a synthesizer departure.

## Options considered

- **`msgpack` side-channel at `ctx.workspace/.parsed/package.json.msgpack` ([P]).** First probe writes; others read. Cheapest. Violates the sanitizer + validator trust boundary by writing a parallel persistence path the chokepoint never sees.
- **Each probe re-parses independently ([B]).** Simplest. Honors isolation. Triples parse cost on warm path; three places to drift the size+depth caps; mitigates nothing the critic flagged.
- **`ParsedManifestMemo` on the coordinator's per-gather scope, exposed to probes via an optional `ctx.parsed_manifest` callable.** Lives entirely in process memory; never written to disk; never crosses sanitizer or validator (because there's nothing to sanitize — the dict is a parser product, not a `ProbeOutput`). One Phase 0 dataclass extension (`ProbeContext.parsed_manifest: Callable | None = None`).

## Decision

**Introduce `ParsedManifestMemo` in `src/codegenie/coordinator/parsed_manifest_memo.py`.** The coordinator constructs one per `gather()` invocation, then exposes it to each probe via `ProbeContext.parsed_manifest: Callable[[Path], Mapping[str, JSONValue] | None] | None` (defaulting to `None`).

- **Key:** `(absolute_path, mtime_ns, size)` for TOCTOU safety. A file changed mid-gather re-parses.
- **Allowlist:** Phase 1 allows only `{"package.json"}`. Future allowlist additions are additive.
- **Lifetime:** per-gather. The memo is discarded at gather end. Phase 14's Temporal Activities re-parse per Activity (correct — Activities are independent units of work).
- **Immutability:** parsed dicts returned wrapped in `types.MappingProxyType` at the top level; nested dicts/lists are returned by reference with `Mapping`-typed signatures (mutation is a mypy error).
- **Fallback:** each probe defensive-checks `ctx.parsed_manifest is not None` and falls back to direct `safe_json.load(...)`. Same correctness; 3× parse cost.
- **Failures don't cache:** if `safe_json.load` raises (cap exceeded, malformed), the memo does not store the result; the next probe retries and sees the same error.

## Tradeoffs

| Gain | Cost |
|---|---|
| Eliminates 3× `package.json` parse on warm cache-miss path (~10 ms saved per gather) | One field added to the Phase 0 `ProbeContext` dataclass — ADR-gated extension to a frozen contract surface |
| No side-channel: the memo never writes to disk, never crosses `OutputSanitizer` or `_ProbeOutputValidator` | Probes that don't use the memo (older test paths, future extensions) carry one defensive `is None` check |
| Per-gather scope cleanly composes with Phase 14's Activity model (no implicit cross-gather state) | The memo is invisible to the cache — repeat gathers re-parse from scratch (correct; the cache hits the `ProbeOutput`, not the intermediate dict) |
| TOCTOU-safe key catches concurrent editor saves mid-gather (Edge case 16) | The mtime/size key does not detect content rewrites that preserve mtime AND size — but `safe_json.load` always reads bytes, so this is bounded to "stale memoization in one gather," not durable cache poisoning |
| Mypy `Mapping` typing makes mutation a static error | `MappingProxyType` wraps only the top level — nested mutation is a runtime convention, not a static guarantee |
| Probes that don't share state (`CI`, `Deployment`) are unaffected — the field is optional | The seam is one of a small number of Phase 0 contract additions Phase 1 makes; each demands its own ADR (this one) |

## Consequences

- `src/codegenie/coordinator/parsed_manifest_memo.py` is a new file; `ProbeContext` gains one optional field.
- Probes that opt in route their `package.json` read through `ctx.parsed_manifest(repo_root / "package.json")` first, then fall back to `safe_json.load`. The pattern is a one-helper-function pattern; the lockfile parsers and other parse work continue to call `safe_json` / `safe_yaml` directly.
- Phase 2's `IndexHealthProbe` reuses the memo at zero implementation cost.
- The audit anchor (Phase 0 ADR-0004) gains a sibling event family `probe.memo.hit` / `probe.memo.miss` for instrumentation; cache-key derivation is unaffected.
- `tests/unit/probes/test_parsed_manifest_memo.py` covers first-call parses, subsequent-call returns memoized, `mtime` change re-parses, and the falsy-memo fallback path.
- The Gap #1 improvement in `phase-arch-design.md` (pre-dispatch input-snapshot pass) is documented as a future amendment to this ADR if Phase 14's concurrent-gather threat model demands it.

## Reversibility

**High.** Removing the memo is mechanically a one-field deletion on `ProbeContext`, deletion of the `parsed_manifest_memo.py` module, and removal of the `ctx.parsed_manifest(...)` calls in the four consumer probes (replaced by direct `safe_json.load`). Probes already fall back to direct parsing when the memo is absent — removal is functionally a permanent fallback. No on-disk artifact embeds the memo's existence.

## Evidence / sources

- `../final-design.md "Components" #2 ParsedManifestMemo` — full design rationale
- `../final-design.md "Conflict-resolution table" row 3` — the resolution
- `../final-design.md "Departures from all three inputs" #1` — synthesizer call-out
- `../final-design.md "Shared blind spots considered" #3` — the critic's framing
- `../phase-arch-design.md "Component design" #3` — interface specifics
- `../phase-arch-design.md "Data model"` — the dataclass extension
- `../phase-arch-design.md "Edge cases" rows 12, 16` — failure and TOCTOU paths
- `../critique.md "Attacks on the performance-first design"` #2 — the msgpack rejection
- [Phase 0 ADR-0010](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) — the trust boundaries the side-channel option would have bypassed
