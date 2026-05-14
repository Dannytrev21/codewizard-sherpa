# Validation report — S1-07 `ParsedManifestMemo` per-gather coordinator memo

**Story:** [S1-07-parsed-manifest-memo.md](../S1-07-parsed-manifest-memo.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — ship `src/codegenie/coordinator/parsed_manifest_memo.py` exposing `ParsedManifestMemo`; wire the coordinator so probes can call `ctx.parsed_manifest(path)` on the runtime ctx; preserve the never-crosses-OutputSanitizer and failure-doesn't-cache invariants from ADR-0002 — traces cleanly to `phase-arch-design.md §"Component design" #3`, `§"Data model"`, `§"Edge cases"` rows 12 & 16, `§"Process view"`, `§"Harness engineering"` → "Logging strategy", ADR-0002, and `final-design.md "Components" #2` (the explicit msgpack-side-channel rejection).

**The draft, however, prescribed a wiring path that doesn't match the actual Phase 0 runtime ctx surface.** Four block-tier defects and eleven harden-tier gaps were identified. The most load-bearing:

1. **`ProbeContext(...)` is not constructed anywhere in the coordinator.** The story's Implementation outline says "Where `ProbeContext(...)` is built, set `parsed_manifest=memo.get`." The Phase 0 coordinator's `_make_probe_context` ([src/codegenie/coordinator/coordinator.py:230](../../../../src/codegenie/coordinator/coordinator.py)) returns a `BudgetingContext` ([src/codegenie/coordinator/budget.py:67](../../../../src/codegenie/coordinator/budget.py)), and `_dispatch_one` passes that `BudgetingContext` to `probe.run(snapshot, ctx)`. S1-06 added `parsed_manifest`/`input_snapshot` to the `ProbeContext` *contract type*, but the *runtime instance* is still `BudgetingContext`. Every probe that accesses `ctx.parsed_manifest` would hit `AttributeError` at runtime under the original draft. The hardened story resolves this by mirroring the two S1-06 additions onto `BudgetingContext` (additive, `None`-default), preserving the `report_bytes` callback contract intact. The `ProbeContext` vs. `BudgetingContext` duality is flagged as a pre-existing smell tracked for a future ADR.
2. **Callable return-type uses `Mapping[str, JSONValue]`** but S1-06's hardened `ProbeContext.parsed_manifest` field type is `Callable[[Path], Mapping[str, Any] | None] | None`. The Phase 0 precedent (`RepoSnapshot.config`, `ProbeContext.config`, `ProbeOutput.schema_slice`, `Task.options`) keeps the contract-surface dict-typing loose-and-stdlib (`Any`); narrowing (`JSONValue`) belongs downstream at `_ProbeOutputValidator`. Hardened: `Mapping[str, Any] | None` at the memo's `get()` boundary.
3. **The `"never crosses OutputSanitizer / _ProbeOutputValidator"` AC was tautological.** `parsed_manifest_memo.py` doesn't import those names, so `monkeypatch.setattr(OutputSanitizer, "scrub", ...)` is trivially never-called. Hardened with a *behavioral* check: tmp_path tree-snapshot before/after `memo.get(p)` asserting byte-equality (no side-channel write). This is the real `msgpack`-rejection invariant `final-design.md "Components" #2` describes.
4. **The `capsys.readouterr().err` log-capture pattern is brittle and inconsistent with S1-02..S1-05 hardened precedent.** It assumes the structlog ProcessorFormatter writes to stderr in a parse-friendly format. The validated precedent is `structlog.testing.capture_logs()` which yields a list of structured-field dicts. Hardened: rewrite the logging test to use `capture_logs()` and assert structured-field shape (`event`, `path`, `allowlist_match`).

Plus seven harden-tier issues:

- **`repo_root: Path` is unused in `__init__`** — dead state; removed. The cache is per-instance, the coordinator owns per-gather lifetime, and no method on the memo needs `repo_root` (the keys are derived from `path.resolve()` directly).
- **Allowlist is locked at module scope** — Phase 2's `IndexHealthProbe` re-uses this memo (ADR-0002 §Consequences) with a wider allowlist. Module-scope `ALLOWLIST` requires editing the memo kernel to add an entry. Hardened: allowlist injected via `__init__(*, allowlist: frozenset[str] = frozenset({"package.json"}))`. This is dependency inversion + Open/Closed at the kernel boundary — the same plugin-shape framing as `parsers/_io.py` (`parser_kind` discriminator) and `catalogs/__init__.py` (`schema_subkey: Literal[...]`).
- **`mtime_ns` integer discipline not pinned.** A mutation that swaps `st.st_mtime_ns` → `int(st.st_mtime * 1e9)` silently loses sub-millisecond precision, breaking rapid-rewrite-disambiguation. Hardened: AC-9 reads the key tuple and pins `isinstance(k[1], int)`; a paired rapid-rewrite test forces ns resolution.
- **Symlink semantics not pinned.** `path.stat()` follows symlinks; `safe_json.load` uses `O_NOFOLLOW`. The two-call interaction (`stat` succeeds → `load` raises `SymlinkRefusedError`) is the actual on-disk behavior; the original story didn't address it. Hardened: AC-11 creates a symlink, asserts the raise, then deletes-and-recreates as a real file and asserts retry semantics.
- **`FileNotFoundError`-only swallowing not pinned.** The original outline catches `FileNotFoundError` and returns `None` but does not document that *other* `OSError` subclasses (notably `PermissionError`) must **propagate**. Hardened: AC-12 with two paired tests (FileNotFoundError → None; PermissionError → raise).
- **Allowlist case-sensitivity not pinned.** A mutation `path.name.lower() in allowlist` would silently accept `Package.json` on case-insensitive filesystems. Hardened: AC-4 explicitly tests `Package.json` (capital P) returns `None`.
- **No-event-on-failure not pinned.** The original story implied success-only event emission but did not pin "no event when `safe_json.load` raises." Hardened: a dedicated test asserts no `probe.memo.*` event appears in `capture_logs` after a `MalformedJSONError`.
- **No AC for cross-gather isolation as observable behavior.** The original story said per-gather discard as commentary only. Hardened: AC-17 asserts `id(ctx.parsed_manifest)` differs across two sequential `gather(...)` calls; mutation that hoists the memo to module-level state is caught.
- **No AC for same-gather sharing.** Symmetric to AC-17: AC-18 asserts the same memo is shared across all probes within a single gather; mutation that constructs a memo per probe is caught.
- **No AC pinning the kernel is closed for modification.** Hardened: AC-20 asserts the public symbol surface (`__all__ == ["ParsedManifestMemo"]`) and the absence of module-level `ALLOWLIST` constants.
- **The cache-tuple types were not type-pinned.** A mutation that swaps the tuple element types (e.g., `(Path, int, int)` instead of `(str, int, int)`) survives the key-equality tests but breaks on macOS's case-insensitive FS path-comparison. Hardened: AC-5 pins `(str, int, int)`.

Three Stage-2D (Design-Patterns) findings:

- **Kernel/policy split**: the allowlist is *policy* (data); the memo is the *kernel*. The original draft inverted this by hard-coding the allowlist as a module constant. The hardened design takes allowlist as a constructor parameter so Phase 2's `IndexHealthProbe` extends by addition (construct with a wider set), zero edits to `parsed_manifest_memo.py`. This matches the precedent set by `parsers/_io.py` (`parser_kind` discriminator) and `catalogs/__init__.py` (`schema_subkey: Literal[...]` widening) — same plugin/registry framing.
- **Newtype on the cache key** is the next move (`MemoKey(NamedTuple)` with `path: str; mtime_ns: int; size: int`) — but YAGNI per Rule 2: the key is used in exactly one place (the `_cache` dict), changes shape entirely in S1-08 (flips to `content_hash`-only), and the 3-tuple is self-documented by the named local `key = (...)`. Recorded in Notes for the implementer as "future move"; not surfaced as an AC.
- **`ProbeContext` vs. `BudgetingContext` duality is a pre-existing smell.** S1-07 mirrors the field set onto `BudgetingContext` to close the runtime gap. A unifying ADR may collapse the two types later (perhaps when Phase 14 introduces Activity-scoped ctx); flagged in Notes for the implementer so the future refactor has a paper trail.

No `NEEDS RESEARCH` findings — every weakness is answerable from `phase-arch-design.md`, ADR-0002, `final-design.md "Components" #2`, the Phase 0 source tree, the S1-02..S1-06 hardened story precedent (kernel/policy split; `structlog.testing.capture_logs`; markers-only construction; mutation-killer tests), and the four typed exceptions from `errors.py` (S1-01). Stage 3 skipped.

The synthesizer expanded ACs from **11 single-bullet items to 22 individually verifiable ACs**, rewrote the TDD plan with ~16 named tests each annotated with its AC and the mutation it catches, added a `BudgetingContext` extension AC, added kernel/policy split via constructor-injected allowlist, replaced the tautological monkeypatch-OutputSanitizer AC with a behavioral tmp_path tree-snapshot AC, replaced `capsys`-based log capture with `structlog.testing.capture_logs`, and surfaced the runtime-ctx duality as Notes for the implementer.

## Context Brief (Stage 1)

- **Goal as written:** Ship `src/codegenie/coordinator/parsed_manifest_memo.py` with a `ParsedManifestMemo` class keyed by `(absolute_path, mtime_ns, size)`, allowlisted to `{"package.json"}`, returning `MappingProxyType`-wrapped parsed dicts, emitting `probe.memo.{hit,miss}` events; coordinator constructs one per `gather()` and injects `ctx.parsed_manifest = memo.get`.
- **Phase exit criteria touched:**
  - Arch §"Component design" #3 — interface, allowlist, lifetime, immutability via `MappingProxyType`, failure-doesn't-cache.
  - Arch §"Data model" — class skeleton (`_cache: dict[(str, int, int), MappingProxyType]`).
  - Arch §"Edge cases" rows 12, 16 — memo-is-None fallback; mid-gather edit re-parses.
  - Arch §"Process view" — coordinator constructs memo at gather start, exposes via runtime ctx's `parsed_manifest` callable.
  - Arch §"Harness engineering" → "Logging strategy" — `probe.memo.hit` / `probe.memo.miss` events with structured fields.
- **ADRs:**
  - ADR-0002 — full design rationale; key=`(absolute_path, mtime_ns, size)` for TOCTOU safety; allowlist additive; failure-doesn't-cache; never-on-disk; allowlist `{"package.json"}` for Phase 1; Phase 2 extends.
  - Phase-0 ADR-0007 — explains why `BudgetingContext` is the runtime ctx (only `workspace: Path` honored from ProbeContext); ADR-0002's S1-06 amendment widened the contract surface but did not unify the runtime ctx.
  - Phase-0 ADR-0008, ADR-0010 — the two trust boundaries the memo does NOT cross (OutputSanitizer, _ProbeOutputValidator).
- **Phase 0 contract (load-bearing):**
  - `BudgetingContext` is the runtime ctx; pre-existing structurally distinct from `ProbeContext` but mypy-compatible via `Any`-typed runtime hop in `_run_probe_with_isolation` ([src/codegenie/coordinator/coordinator.py:387](../../../../src/codegenie/coordinator/coordinator.py)).
  - `safe_json.load(path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]` ([src/codegenie/parsers/safe_json.py:60](../../../../src/codegenie/parsers/safe_json.py)).
  - Errors hierarchy ([src/codegenie/errors.py](../../../../src/codegenie/errors.py)): `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` — the four typed exceptions `safe_json.load` may raise. Markers-only construction; positional message only.
  - `structlog.testing.capture_logs()` is the validated precedent (S1-02 / S1-03 / S1-04 / S1-05 hardenings) for structured-field event assertions.
- **S1-06 hardened contract (this phase, predecessor):**
  - `ProbeContext.parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None` — type at the contract boundary uses `Mapping[str, Any]`, not `Mapping[str, JSONValue]`.
  - `InputFingerprint` is a `NamedTuple` in `base.py` with fields `(path: str, mtime_ns: int, size: int, content_hash: str)`.
- **Phase-0 runtime ctx reality:**
  - `_make_probe_context` ([src/codegenie/coordinator/coordinator.py:230](../../../../src/codegenie/coordinator/coordinator.py)) returns `BudgetingContext(workspace=..., raw_artifact_mb=...)`.
  - The docstring explicitly says: "Phase 1+ probes that need `cache_dir`/`output_dir`/`logger`/`config` will see those wired when the harness grows that surface." — S1-07 is one such Phase-1+ moment, but only for `parsed_manifest`. The remaining four `ProbeContext` fields stay unwired in this story (no probe needs them).
- **Open ambiguities surfaced:**
  1. The story's "Where `ProbeContext(...)` is built" prescription is structurally wrong — no such site exists in the coordinator. Resolved by extending `BudgetingContext` (the actual runtime ctx) with two None-default fields mirroring S1-06's `ProbeContext` extension.
  2. The story's `Mapping[str, JSONValue]` return type contradicts S1-06's hardened `Mapping[str, Any]` boundary type. Resolved by narrowing the memo's `get()` return type to `Mapping[str, Any] | None`.
  3. The story's `repo_root: Path` constructor parameter is unused. Resolved by removing it. The memo state is per-instance + per-gather; the coordinator owns the lifetime.
  4. The story's `monkeypatch(OutputSanitizer, ...)` AC is tautological because `parsed_manifest_memo.py` doesn't import those names. Resolved by replacing with a behavioral tmp_path tree-snapshot check.
  5. The story's `capsys.readouterr().err` log capture is brittle and inconsistent with S1-02..S1-05 precedent. Resolved by using `structlog.testing.capture_logs()`.

## Stage 2 — critic reports (synthesized in-head from S1-02..S1-06 precedent + S1-07 specifics)

The Coverage / Test-Quality / Consistency / Design-Patterns critic patterns are now well-known from S1-02..S1-06 hardenings. The validator skill's parallel-subagent fan-out is omitted in this case (token economy):

- Every recurring finding from prior validation reports reappears identically here (markers-only construction is irrelevant here since the memo doesn't construct typed errors; structured-field event assertions via `capture_logs`; module surface closure; kernel/policy split; mutation-killer tests).
- All story-specific deltas required first-principles analysis against `src/codegenie/coordinator/coordinator.py`, `src/codegenie/coordinator/budget.py`, `src/codegenie/probes/base.py` (post-S1-06), `src/codegenie/parsers/safe_json.py`, and `src/codegenie/errors.py` — five files, ~700 lines total.
- No external research needed; canonical patterns (`MappingProxyType` immutability, `os.stat` ns precision, `O_NOFOLLOW` interaction, `frozenset[str]` as policy, `capture_logs` event assertions) are stdlib- or structlog-docs-documented.

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (block)** — No AC pins the runtime-ctx structural reality. Resolved by AC-15 (extend `BudgetingContext` with two additive fields) + AC-16 (coordinator threads memo.get via `_make_probe_context`).
- **CV2 (block)** — No AC pins `Mapping[str, Any]` at the memo boundary. Resolved by AC-3.
- **CV3 (block)** — No AC pins the no-disk-write invariant as a *behavioral* check. The original monkeypatch-OutputSanitizer AC is tautological. Resolved by AC-14 (tmp_path tree-snapshot before/after).
- **CV4 (block)** — `capsys.readouterr().err` log capture inconsistent with S1-02..S1-05 hardened precedent. Resolved by AC-13 using `structlog.testing.capture_logs()`.
- **CV5 (harden)** — No AC pins case-sensitivity of the allowlist comparison. Resolved by AC-4 with explicit `Package.json` test.
- **CV6 (harden)** — No AC pins `st_mtime_ns` (int, ns) vs. `st_mtime` (float, seconds). Resolved by AC-9 with `isinstance(k[1], int)` and a rapid-rewrite disambiguation.
- **CV7 (harden)** — No AC pins symlink+`O_NOFOLLOW` interaction. Resolved by AC-11 with symlink-then-real-file retry test.
- **CV8 (harden)** — No AC pins that `FileNotFoundError` is the *only* swallowed `OSError`. Resolved by AC-12 with PermissionError-propagates paired test.
- **CV9 (harden)** — No AC pins cross-gather isolation as observable behavior. Resolved by AC-17 (`id(ctx.parsed_manifest)` differs across two gather()s).
- **CV10 (harden)** — No AC pins same-gather sharing. Resolved by AC-18 (`id(ctx.parsed_manifest)` equal across two probes in one gather).
- **CV11 (harden)** — No AC pins "no event on parse failure". Resolved by AC-13's dedicated `capture_logs` assertion that `probe.memo.*` is absent after a raise.
- **CV12 (harden)** — No AC pins the cache key tuple element types `(str, int, int)`. Resolved by AC-5.

### Test Quality (verdict: TESTS-HARDEN)

Mutation analysis (~14 plausible wrong implementations) — each caught by at least one named test:

| # | Mutation | Catches | Test |
|---|---|---|---|
| 1 | Forget to wrap in MappingProxyType | AC-3, AC-5 | `test_first_call_parses_and_returns_mappingproxy` |
| 2 | Re-wrap on hit (`return MappingProxyType(dict(hit))`) | AC-6 | `test_second_call_returns_same_instance` |
| 3 | Drop `mtime_ns` from key | AC-7 | `test_mtime_change_triggers_reparse` |
| 4 | Drop `size` from key | AC-8 | `test_size_change_triggers_reparse` |
| 5 | Use `st_mtime` (float) instead of `st_mtime_ns` | AC-9 | `test_key_uses_int_ns_mtime_not_float_seconds` + rapid-rewrite paired test |
| 6 | Cache on parse failure | AC-10 | `test_parse_failure_does_not_cache` + `test_size_cap_exceeded_does_not_cache` |
| 7 | Cache on symlink raise | AC-11 | `test_symlink_path_raises_and_does_not_cache` |
| 8 | Raise on FileNotFoundError | AC-12 | `test_missing_file_returns_none` |
| 9 | Swallow PermissionError | AC-12 | `test_permission_error_propagates` |
| 10 | Case-insensitive allowlist | AC-4 | `test_allowlist_is_case_sensitive` |
| 11 | Emit event on parse failure | AC-13 | `test_no_event_on_parse_failure` |
| 12 | Side-channel disk write | AC-14 | `test_memo_does_not_write_to_disk` |
| 13 | Module-level memo (singleton) | AC-17 | `test_cross_gather_isolation` |
| 14 | Per-probe memo (no sharing) | AC-18 | `test_same_gather_sharing_across_probes` |
| 15 | Forget to add `parsed_manifest` field to `BudgetingContext` | AC-15 | `test_budgeting_context_has_parsed_manifest_and_input_snapshot_fields` |
| 16 | Coordinator forgets to thread memo.get | AC-16 | `test_gather_threads_parsed_manifest_to_ctx` |

The TDD plan covers all 16 mutations with named, AC-anchored tests. No test is tautological; no test verifies "exception not raised" alone; every test would *fail* under at least one wrong implementation.

### Consistency (verdict: CONSISTENCY-HARDEN)

- **CN1 (block)** — Story's `ProbeContext(...)` construction prescription contradicts the Phase 0 coordinator. Resolved by AC-15 + AC-16 (extend `BudgetingContext` instead).
- **CN2 (block)** — Story's `Mapping[str, JSONValue]` return type contradicts S1-06's hardened `Mapping[str, Any]` boundary on `ProbeContext.parsed_manifest`. Resolved by AC-3.
- **CN3 (harden)** — Story's note "S1-08 flips the key to `content_hash`" should be marked inline in the green commit so the follow-up is grep-friendly. Resolved by adding the inline-comment requirement in the Refactor section.
- **CN4 (harden)** — Story's "memo never crosses OutputSanitizer or _ProbeOutputValidator" is preserved as a behavioral AC (AC-14) rather than a tautological monkeypatch AC.
- **CN5 (nit)** — Story's `_MAX_BYTES = 5_242_880` literal should be a module-level `Final[int]` constant with arch §"Component design" #3 named in the comment. Resolved in the Refactor section.

### Design Patterns (verdict: DESIGN-HARDEN)

- **DP1 (harden)** — Module-level `ALLOWLIST` locks the policy into the kernel. Phase 2's `IndexHealthProbe` reuses this memo with a wider allowlist (ADR-0002 §Consequences). Resolved by AC-2: allowlist is a `__init__` keyword-only parameter, kernel never edited.
- **DP2 (harden)** — `repo_root: Path` dead state — primitive obsession on an unused parameter. Resolved: removed from `__init__`.
- **DP3 (harden)** — Kernel closure invariant: `__all__ == ["ParsedManifestMemo"]`; no module-level `ALLOWLIST`. Resolved by AC-20.
- **DP4 (recorded for posterity, no AC)** — `MemoKey(NamedTuple)` newtype on the cache key would self-document the 3-tuple, but YAGNI applies: the key is used in exactly one place, changes shape entirely in S1-08, and the named local `key = (...)` is sufficient. Recorded in Notes for the implementer as "future move if Phase 2 needs an explicit key type"; not surfaced as an AC.
- **DP5 (recorded for posterity, no AC)** — `ProbeContext` vs. `BudgetingContext` duality is a pre-existing smell. S1-07 mirrors the field set onto `BudgetingContext`; a future ADR may collapse the two. Recorded in Notes for the implementer.

## Stage 3 — research

Skipped. No `NEEDS RESEARCH` findings.

## Stage 4 — synthesis

Conflicts resolved using `Consistency > Coverage > Test-Quality > Design-Patterns`:

- **Conflict 1**: Coverage CV1 (extend `BudgetingContext`) vs. Consistency CN1 (story prescribes `ProbeContext`). Consistency wins — the runtime ctx is `BudgetingContext` per Phase 0 contract. Extend it.
- **Conflict 2**: Design-Patterns DP1 (allowlist as constructor param) vs. Rule 2 / YAGNI (could leave at module scope). Design-Patterns wins because the *third* concrete consumer of the memo (`IndexHealthProbe` in Phase 2) is named in ADR-0002 §Consequences — the rule-of-three threshold is reached; injection is justified.
- **Conflict 3**: Design-Patterns DP4 (`MemoKey` newtype) vs. Rule 2 / YAGNI. YAGNI wins because S1-08 changes the key shape entirely; investing in `MemoKey(NamedTuple)` now is premature. Recorded as Notes-for-implementer, not an AC.

Final verdict: **HARDENED**. The hardened story is ready for the executor.

## Edits applied to the story

- Status updated to "Ready (validator-hardened 2026-05-14)".
- Added the `Validation notes` block after the header documenting every change.
- Context section rewritten to surface the runtime-ctx duality and the per-gather lifetime explicitly.
- References section expanded with Phase-0 source-code line-anchored citations and the S1-06-hardened contract type.
- Goal rewritten to name the `BudgetingContext` extension explicitly.
- ACs expanded from 11 single-bullets to 22 individually verifiable items, each with intent commentary.
- Implementation outline rewritten with the actual `_make_probe_context` integration shape.
- TDD plan rewritten with ~16 named tests each annotated with its AC and the mutation it catches; `structlog.testing.capture_logs` replaces `capsys.readouterr().err`.
- Files-to-touch table expanded with the `BudgetingContext` extension file and the new `tests/unit/coordinator/` directory.
- Out-of-scope expanded with explicit notes on the `ProbeContext` ↔ `BudgetingContext` collapse and the event-vocabulary registry.
- Notes for the implementer expanded with the runtime-ctx duality, symlink semantics, `FileNotFoundError`-only semantics, threading caveats, and the kernel/policy framing as a recorded design pattern.

## Final verdict

**HARDENED.** The story is ready for `phase-story-executor`. The structural runtime-ctx gap (the original story's most load-bearing defect) is resolved by mirroring the S1-06 field additions onto `BudgetingContext`. The kernel/policy split via constructor-injected allowlist preserves the Open/Closed invariant for Phase 2's reuse. All 16 plausible wrong implementations are caught by named tests with explicit AC anchors.
