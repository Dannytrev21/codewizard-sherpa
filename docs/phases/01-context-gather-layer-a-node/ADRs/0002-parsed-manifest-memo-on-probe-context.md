# ADR-0002: `ParsedManifestMemo` on `ProbeContext` — in-coordinator per-gather parse memo

**Status:** Accepted
**Date:** 2026-05-12
**Last amended:** 2026-05-14 (S1-08 — Gap 1 landed, additive `content_hash` key shape via `compute_input_snapshot`)
**Tags:** coordinator · probe-context · performance · chokepoint-preservation · toctou
**Related:** ADR-0008, [Phase 0 ADR-0009](../../00-bullet-tracer-foundations/ADRs/0009-cache-hit-pass-through-coordinator-output.md), [Phase 0 ADR-0010](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md), [Phase 0 ADR-0008](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md)

> **Amendment scope (2026-05-14, S1-06):** this ADR is the single Phase-0-contract amendment for the entire Phase 1. The amendment adds `input_snapshot: frozenset[InputFingerprint] | None = None` and the companion `InputFingerprint` `NamedTuple` to `src/codegenie/probes/base.py`, alongside the original `parsed_manifest` seam. **No further extensions to `ProbeContext` are permitted in Phase 1 without a new ADR.** The dedicated sentinel test `test_probe_context_field_list_matches_adr_0002_amendment` in `tests/unit/test_probe_contract.py` hard-codes the allowed 7-field tuple and fails CI naming this ADR the moment a third future field appears.

## Context

Four Phase 1 probes (`LanguageDetection` extended, `NodeBuildSystem`, `NodeManifest`, `TestInventory`) read `package.json`. The critic's cross-design observation #3 (`final-design.md "Shared blind spots considered"` #3) names the gap directly: "All three lenses accept reading `package.json` more than once per gather; none uses the cheapest, cleanest seam." On the cache-miss warm path that's three parses of the same bytes per gather — ~15 ms of pure duplicate work, plus the surface area of three independent cap-and-validate paths drifting.

The performance lens proposed `.parsed/package.json.msgpack` written to `ctx.workspace` as a side-channel. The critic rejected this (`critique.md "Attacks on the performance-first design"` #2): it bypasses `_ProbeOutputValidator` (Phase 0 ADR-0010) and `OutputSanitizer` (Phase 0 ADR-0008) — Phase 0's two structural trust boundaries on every `ProbeOutput`-shaped byte that hits disk.

The security lens's sandbox would force re-parse per fork ([final-design] "Conflict-resolution table" row 1 rejects the sandbox entirely; see ADR-0008). The best-practices lens accepted the triple parse explicitly. None of the three lenses proposed a coordinator-internal memo — it surfaced as a synthesizer departure.

## Options considered

- **`msgpack` side-channel at `ctx.workspace/.parsed/package.json.msgpack` ([P]).** First probe writes; others read. Cheapest. Violates the sanitizer + validator trust boundary by writing a parallel persistence path the chokepoint never sees.
- **Each probe re-parses independently ([B]).** Simplest. Honors isolation. Triples parse cost on warm path; three places to drift the size+depth caps; mitigates nothing the critic flagged.
- **`ParsedManifestMemo` on the coordinator's per-gather scope, exposed to probes via an optional `ctx.parsed_manifest` callable.** Lives entirely in process memory; never written to disk; never crosses sanitizer or validator (because there's nothing to sanitize — the dict is a parser product, not a `ProbeOutput`). One Phase 0 dataclass extension (`ProbeContext.parsed_manifest: Callable | None = None`).

## Decision

**Two additive optional fields are appended to the Phase-0 `ProbeContext` dataclass** in `src/codegenie/probes/base.py` (the contract surface), both defaulting to `None` so every existing construction site (Phase 0 probes, tests, the coordinator) keeps working unchanged:

1. `parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None` — the memo seam. The coordinator constructs a per-gather `ParsedManifestMemo` (`src/codegenie/coordinator/parsed_manifest_memo.py`, S1-07) and exposes its `get` method here.
2. `input_snapshot: frozenset[InputFingerprint] | None = None` — the pre-dispatch input-snapshot pass (`phase-arch-design.md §"Gap analysis"` Gap 1, S1-08). The coordinator walks each probe's `declared_inputs`, stats + content-hashes every match exactly once, populates the `frozenset` and pins it on the per-gather `ProbeContext`. Cache-key derivation moves to `content_hash` (not live `os.stat`), closing the TOCTOU window load-bearing for Phase 14's continuous-gather concurrent-edit threat model.

The companion contract type `InputFingerprint` is a `typing.NamedTuple` defined in `base.py` alongside `ProbeContext`:

```python
class InputFingerprint(NamedTuple):
    path: str            # absolute POSIX-form string (cross-platform hashable + comparable)
    mtime_ns: int        # os.stat result
    size: int            # bytes
    content_hash: str    # blake3 hex digest
```

`NamedTuple` is chosen so the type is auto-hashable for `frozenset[InputFingerprint]` membership without `dataclass(frozen=True, eq=True)` boilerplate. `InputFingerprint` lives in `base.py` (not in `coordinator/`) because it is a contract type — coordinator produces, probes consume via `ctx.input_snapshot` — and the stdlib-only fence on `base.py` is preserved (its only new import is `from collections.abc import Callable, Mapping`).

### `ParsedManifestMemo` semantics

- **Key (dual-shape, additive — S1-08):** when the coordinator's adapter passes a snapshot-derived `content_hash`, the cache key is the single-element tuple `(content_hash,)` and a file edited mid-gather cannot poison the parse of the snapshotted bytes (Gap-1 closure). When `content_hash` is omitted (`None`), the cache key is the legacy `(str(path.resolve()), mtime_ns, size)` tuple from S1-07 — preserved for non-coordinator callers (Phase 14 tests, ad-hoc CLI usage) so the S1-07 test surface lands unmodified. Sentinel `content_hash` values (`"<oversize>"`, `"<refused>"`, or any leading-`"<"` prefix) bypass the cache entirely (return `None`, no entry written) — the downstream parse would fail anyway and a cached sentinel only serves confusion.
- **Allowlist:** Phase 1 allows only `{"package.json"}`. Future allowlist additions are additive.
- **Lifetime:** per-gather. The memo is discarded at gather end. Phase 14's Temporal Activities re-parse per Activity (correct — Activities are independent units of work).
- **Immutability:** parsed dicts returned wrapped in `types.MappingProxyType` at the top level; nested dicts/lists are returned by reference with `Mapping`-typed signatures (mutation is a mypy error).
- **Fallback:** each probe defensive-checks `ctx.parsed_manifest is not None` and falls back to direct `safe_json.load(...)`. Same correctness; 3× parse cost.
- **Failures don't cache:** if `safe_json.load` raises (cap exceeded, malformed), the memo does not store the result; the next probe retries and sees the same error.

### `input_snapshot` semantics

- **Source of truth for cache keys.** Probe cache keys are derived from the `content_hash` of each declared-input entry, not from a live `os.stat` at cache-key time. A file changed between snapshot-pass and probe-dispatch does not silently invalidate the cache key.
- **Pre-dispatch single-pass.** The coordinator stats + hashes each file once at the start of a gather; ~5 ms of pre-dispatch I/O per repo.
- **Fallback:** probes defensive-check `ctx.input_snapshot is not None` (Edge case 12 in `phase-arch-design.md`) and fall back to live `os.stat` if absent — same correctness, TOCTOU window reopens.
- **Why `path: str` and not `Path`:** macOS's case-insensitive filesystem makes `Path` equality a foot-gun (`Path("/a/B") != Path("/a/b")` but both stat the same file). The coordinator normalizes to an absolute POSIX-form string at fingerprint time.

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

- `src/codegenie/coordinator/parsed_manifest_memo.py` is a new file; `ProbeContext` gains **two** optional fields (`parsed_manifest`, `input_snapshot`) and `base.py` gains the `InputFingerprint` `NamedTuple` (S1-06).
- Probes that opt in route their `package.json` read through `ctx.parsed_manifest(repo_root / "package.json")` first, then fall back to `safe_json.load`. The pattern is a one-helper-function pattern; the lockfile parsers and other parse work continue to call `safe_json` / `safe_yaml` directly.
- Phase 2's `IndexHealthProbe` reuses the memo at zero implementation cost.
- The audit anchor (Phase 0 ADR-0004) gains a sibling event family `probe.memo.hit` / `probe.memo.miss` for instrumentation; cache-key derivation is unaffected.
- `tests/unit/probes/test_parsed_manifest_memo.py` covers first-call parses, subsequent-call returns memoized, `mtime` change re-parses, and the falsy-memo fallback path.
- **Resolved in S1-08 (2026-05-14):** the Gap #1 improvement is landed via `compute_input_snapshot` + `make_parsed_manifest_adapter` in `src/codegenie/coordinator/input_snapshot.py`. The memo's signature gained an additive `content_hash: str | None = None` parameter (departure from arch line 990's prescribed full-flip, recorded per Rule 7) — when the coordinator's adapter passes a snapshot-derived `content_hash`, the cache key is `(content_hash,)`; when omitted, S1-07's `(absolute_path, mtime_ns, size)` key is used unchanged. Sentinels (`"<oversize>"`, `"<refused>"`) bypass the memo. Rationale for the additive shape: (a) preserves S1-07's hardened test suite — the executor doesn't rewrite ~16 tests inside the S1-08 PR; (b) supports non-coordinator callers (test paths that construct `memo` directly without first running `compute_input_snapshot`); (c) the coordinator's adapter always passes `content_hash=...` for snapshotted paths, so the on-the-warm-path behavior is the arch-prescribed shape — no observable regression.
- `tests/unit/test_probe_contract.py` gains the ADR-0002 sentinel test `test_probe_context_field_list_matches_adr_0002_amendment` (hard-coded 7-field tuple) plus an `InputFingerprint` mutation-killer tier and doc-grep tests on `localv2.md §4` and this ADR. Adding a third field to `ProbeContext` fails CI with a message naming this ADR.
- The stdlib-only fence on `base.py` is widened by exactly `"collections"` (admits `from collections.abc import Callable, Mapping`); `ALLOWED_BASE_PY_IMPORTS` is pinned by `test_allowed_base_py_imports_includes_collections` so a future revert is a loud regression.

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
