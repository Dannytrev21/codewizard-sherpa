# Story S1-07 — `ParsedManifestMemo` per-gather coordinator memo

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (validator-hardened 2026-05-14)
**Effort:** M
**Depends on:** S1-02, S1-06
**ADRs honored:** ADR-0002

## Validation notes

Hardened 2026-05-14 by `phase-story-validator`. Full report: [`_validation/S1-07-parsed-manifest-memo.md`](_validation/S1-07-parsed-manifest-memo.md). Four block-tier defects and eleven harden-tier gaps corrected; ACs expanded from 11 single-bullets to 22 individually verifiable items; the TDD plan was rewritten with ~16 named tests each annotated with its AC and the mutation it catches.

Key reshapes vs. the original draft:

- **Runtime-ctx structural mismatch surfaced and resolved.** The original draft prescribed "where `ProbeContext(...)` is built, set `parsed_manifest=memo.get`." No such construction site exists. The Phase 0 coordinator's `_make_probe_context` ([src/codegenie/coordinator/coordinator.py:230](../../../../src/codegenie/coordinator/coordinator.py)) returns a `BudgetingContext` ([src/codegenie/coordinator/budget.py:67](../../../../src/codegenie/coordinator/budget.py)) which it passes as `ctx` to `probe.run(snapshot, ctx)`. S1-06 added `parsed_manifest`/`input_snapshot` to the `ProbeContext` *contract type*, but the *runtime instance* is still `BudgetingContext`. S1-07 must close that gap or every probe accessing `ctx.parsed_manifest` will hit `AttributeError`. The hardened resolution: extend `BudgetingContext` with two additive `None`-defaulting fields that mirror S1-06's `ProbeContext` extension — the surgical-by-Rule-3 path that preserves the Phase 0 `report_bytes` callback contract intact. The `ProbeContext` vs. `BudgetingContext` duality is a pre-existing smell flagged for a future ADR (see Notes for the implementer).
- **Callable type narrowed to match S1-06's hardened contract.** Original used `Mapping[str, JSONValue]`. `JSONValue` lives in `coordinator/validator.py` and is not importable from `parsers/` without an explicit re-export — but importantly, S1-06's validation hardened the `ProbeContext.parsed_manifest` field annotation to `Callable[[Path], Mapping[str, Any] | None] | None` because of the Phase 0 `dict[str, Any]` precedent on every other contract-surface dict. The memo's `get()` return-type annotation now mirrors `Mapping[str, Any] | None`. The implementation may internally type its `dict[str, JSONValue]` from `safe_json.load`'s return; `MappingProxyType` covariance makes the narrowing compatible.
- **`structlog.testing.capture_logs` replaces `capsys.readouterr().err`.** The S1-02 / S1-03 / S1-04 / S1-05 validated precedent: stderr-string assertions are brittle (format mode, color, line buffering); the structured-field shape is the contract. Tests now read `[entry["event"]" for entry in logs]` and assert `entry["path"]` is the stringified resolved path.
- **`unused repo_root` removed from `__init__`.** The original implementation outline took `repo_root: Path` but never read it. Dead state. The class now takes no `__init__` args; the cache is per-instance and the coordinator owns the per-gather lifetime.
- **Allowlist as constructor parameter (Open/Closed).** The original locked `ALLOWLIST = frozenset({"package.json"})` at module scope. Phase 2's `IndexHealthProbe` re-uses this memo per ADR-0002 §Consequences. The hardened design takes the allowlist as a `__init__` parameter `allowlist: frozenset[str] = frozenset({"package.json"})`. The kernel never changes; Phase 2 constructs with a wider set, and Phase 1's coordinator passes the default. This is dependency inversion at the seam — the memo is the kernel; the policy (what to memoize) is data, injected by the caller.
- **Symlink-on-`stat` semantics pinned.** `path.stat()` follows symlinks; `safe_json.load` uses `O_NOFOLLOW`. So a symlink at the final path component will *succeed* `stat()` (returning target's metadata) and then *fail* `safe_json.load` with `SymlinkRefusedError`. Failure does not cache → next call retries → same failure. AC-10 covers this; Notes for the implementer documents the interaction explicitly.
- **`FileNotFoundError` on `stat()` returns `None` (not raise).** The original outline had this implicit; AC-11 now pins it. Pre-existing precedent: any other `OSError` (permission denied, etc.) **propagates** — only `FileNotFoundError` is converted to `None`. This matches the "memo is best-effort" contract.
- **Disk-write paranoia AC replaced with behavioral check.** The original AC said "verify in test via monkeypatch of `OutputSanitizer` / `_ProbeOutputValidator` — assert they're not entered." But `parsed_manifest_memo.py` doesn't import those names, so the monkeypatch is trivially never-called — a tautology. The hardened AC is behavioral: snapshot `tmp_path` contents before/after `memo.get(p)` and assert byte-equality (no side-channel write).
- **Cross-gather isolation pinned.** The original story said "per-gather memo discarded at gather end" as commentary only. AC-16 pins it as observable: two sequential `gather()` calls must construct two distinct memo instances; module-level state would fail this test.
- **Event structured-field shape pinned.** Beyond just the event-name assertion, AC-12 pins that each emitted event carries `path=<resolved-absolute-string>` and `allowlist_match="package.json"` so future log consumers (S2-04 warm-path test) have a stable field shape.
- **Allowlist case-sensitivity made platform-explicit.** Test pins `Package.json` (capital P) → `path.name not in allowlist` → `None`. The mutation that swaps `path.name not in allowlist` to `path.name.lower() not in allowlist` is caught by this test independently of the structural-signature test for the allowlist constant.
- **`mtime_ns` integer discipline pinned.** A mutation that uses `path.stat().st_mtime` (float seconds, not nanoseconds) silently loses sub-millisecond resolution — making rapid sequential rewrites collide. AC pins `int` type and ns precision via `st_mtime_ns`.

## Context

`ParsedManifestMemo` is the in-coordinator per-gather memo that eliminates 3× `package.json` parsing across `LanguageDetectionProbe` (extended), `NodeBuildSystemProbe`, `NodeManifestProbe`, and `TestInventoryProbe`. It lives in process memory only — never written to disk, never crossing `OutputSanitizer` or `_ProbeOutputValidator` (Phase 0 chokepoints unchanged). Its key derives from a `(absolute_path, mtime_ns, size)` triple in this story; S1-08 flips the key to `InputFingerprint.content_hash` sourced from the pre-dispatch input-snapshot pass.

Per-gather scope means: one `Coordinator.gather()` call constructs one memo instance and discards it on return. Two sequential `gather()` calls — even back-to-back — share no memo state. Phase 14's Temporal Activities re-parse per Activity (correct: Activities are independent units of work).

Phase 1 allowlist: `{"package.json"}`. The allowlist is taken as a `__init__` parameter so Phase 2's `IndexHealthProbe` (which extends the memo to SCIP index manifests per ADR-0002 §Consequences) constructs with a wider set without touching the memo's kernel.

**Runtime-ctx structural reality** (load-bearing for the wiring AC): The Phase 0 coordinator passes a `BudgetingContext` ([src/codegenie/coordinator/budget.py:67](../../../../src/codegenie/coordinator/budget.py)) as the runtime `ctx`. S1-06 added `parsed_manifest`/`input_snapshot` to the `ProbeContext` **contract type** but the **runtime instance** seen by `probe.run(snap, ctx)` is `BudgetingContext`. S1-07 closes the gap by mirroring the two `ProbeContext` fields onto `BudgetingContext` (additive, `None`-default) so probes accessing `ctx.parsed_manifest` succeed at runtime. The duality between the contract type and the runtime ctx is a pre-existing smell tracked for a future ADR; S1-07 does NOT attempt to collapse the two types.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #3`](../phase-arch-design.md) — full interface, allowlist, lifetime, immutability via `MappingProxyType`, failure-doesn't-cache semantics.
  - [`../phase-arch-design.md §"Data model"`](../phase-arch-design.md) — class skeleton; `_cache: dict[(str, int, int), MappingProxyType]`.
  - [`../phase-arch-design.md §"Edge cases"`](../phase-arch-design.md) rows 12, 16 — memo-is-None fallback; mid-gather edit re-parses.
  - [`../phase-arch-design.md §"Harness engineering" → "Logging strategy"`](../phase-arch-design.md) — `probe.memo.hit` / `probe.memo.miss` events with structured fields.
  - [`../phase-arch-design.md §"Process view"`](../phase-arch-design.md) — coordinator constructs memo at gather start, exposes via the runtime ctx's `parsed_manifest` callable.
- **Phase ADRs:**
  - [`../ADRs/0002-parsed-manifest-memo-on-probe-context.md`](../ADRs/0002-parsed-manifest-memo-on-probe-context.md) — full design rationale; key=`(absolute_path, mtime_ns, size)` for TOCTOU safety; allowlist additive in future phases; failure-doesn't-cache; never-on-disk.
- **Phase-0 ADRs:**
  - [`../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-by-doc-snapshot.md`](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-by-doc-snapshot.md) — explains why `BudgetingContext` is the runtime ctx (`workspace: Path` is the only frozen ProbeContext field S3-05 honored at the runtime layer).
  - [`../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md`](../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md), [`../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md`](../../00-bullet-tracer-foundations/ADRs/0010-pydantic-probe-output-validator.md) — the two trust boundaries the memo does NOT cross.
- **Source design:**
  - [`../final-design.md §"Components" #2`](../final-design.md) — design statement; explicit rejection of the msgpack side-channel.
- **Existing code (load-bearing reads):**
  - [`src/codegenie/parsers/safe_json.py`](../../../../src/codegenie/parsers/safe_json.py) (S1-02) — memo parses through this; `load(path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`.
  - [`src/codegenie/parsers/__init__.py:26`](../../../../src/codegenie/parsers/__init__.py) — `JSONValue` is exported from `codegenie.parsers` so the implementation may type internally as `dict[str, JSONValue]` if desired (the boundary return type is `Mapping[str, Any] | None` per S1-06 hardening).
  - [`src/codegenie/probes/base.py`](../../../../src/codegenie/probes/base.py) (S1-06) — `ProbeContext.parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None` — the **contract type** the runtime ctx must satisfy structurally.
  - [`src/codegenie/coordinator/budget.py`](../../../../src/codegenie/coordinator/budget.py) (S3-05) — `BudgetingContext` is the runtime ctx; S1-07 extends it with two additive None-default fields mirroring `ProbeContext`'s S1-06 extension.
  - [`src/codegenie/coordinator/coordinator.py`](../../../../src/codegenie/coordinator/coordinator.py) (S3-05) — `_make_probe_context(...)` builds the runtime ctx; `gather(...)` is the integration point; constructs the memo once at top, threads through to `_dispatch_one → _make_probe_context`.
  - [`src/codegenie/errors.py`](../../../../src/codegenie/errors.py) (S1-01) — `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` are the four typed exceptions `safe_json.load` raises; the memo does NOT cache on any of them.
  - [`tests/unit/_coordinator_fixtures.py`](../../../../tests/unit/_coordinator_fixtures.py) — `make_probe_context` exists for the test surface (constructs `ProbeContext` directly); use as the wiring smoke test's harness.

## Goal

Ship `src/codegenie/coordinator/parsed_manifest_memo.py` exposing `ParsedManifestMemo`. Extend `BudgetingContext` with two additive None-default fields (`parsed_manifest`, `input_snapshot`) mirroring the S1-06 `ProbeContext` extension. The coordinator constructs one memo per `gather()` invocation, threads it through `_dispatch_one → _make_probe_context`, and the resulting `BudgetingContext` carries `parsed_manifest=memo.get` so probes accessing `ctx.parsed_manifest(...)` succeed at runtime. Emit `probe.memo.{hit,miss}` events with structured fields. Never write to disk. Never cache parse failures.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/coordinator/parsed_manifest_memo.py` is a new module exporting exactly one public symbol, `ParsedManifestMemo`. Module docstring names `phase-arch-design.md §"Component design" #3`, ADR-0002, and the explicit msgpack rejection from `final-design.md "Components" #2`.
- [ ] **AC-2.** `ParsedManifestMemo.__init__(self, *, allowlist: frozenset[str] = frozenset({"package.json"})) -> None`:
  - Accepts the allowlist as a keyword-only constructor parameter with the Phase 1 default `frozenset({"package.json"})`.
  - Stores `self._allowlist` (frozen, never mutated) and initializes `self._cache: dict[tuple[str, int, int], MappingProxyType[str, Any]] = {}`.
  - Does NOT take a `repo_root` parameter (dead state in the original draft — removed).
  - A test parametrizes `[frozenset({"package.json"}), frozenset({"package.json", "scip-index.json"})]` to pin the allowlist-injection extension path.
- [ ] **AC-3.** `ParsedManifestMemo.get(self, path: Path) -> Mapping[str, Any] | None` is the only public method. Type signature is exactly `Mapping[str, Any] | None` (not `Mapping[str, JSONValue] | None`) at the boundary — mirroring S1-06's hardened `ProbeContext.parsed_manifest` field type.
- [ ] **AC-4.** `get(path)` returns `None` when `path.name not in self._allowlist`. Comparison is **case-sensitive**: `Path("/tmp/Package.json")` (capital P) → `None`. A dedicated test pins case-sensitivity by constructing `Package.json` and asserting `None`; a mutation swapping to `.lower()` is caught.
- [ ] **AC-5.** First call for an allowlisted path:
  - Calls `path.stat()`; if it raises `FileNotFoundError`, `get()` returns `None` (no raise, no cache).
  - Otherwise, builds the cache key `(str(path.resolve()), st.st_mtime_ns, st.st_size)`. Key types pinned exactly: `(str, int, int)`. A test reads `next(iter(memo._cache.keys()))` and asserts `isinstance(k[0], str) and isinstance(k[1], int) and isinstance(k[2], int)`.
  - Calls `safe_json.load(path, max_bytes=5_242_880)` (5 MiB cap — matches `phase-arch-design.md §"Component design" #3`).
  - Wraps result in `MappingProxyType` and stores in `_cache[key]`.
  - Returns the wrapped result.
- [ ] **AC-6.** Identity contract: the **same `MappingProxyType` instance** is returned on a cache hit. A test asserts `a is b` (the `is` operator, not `==`) across two `memo.get(p)` calls on an unchanged file. Mutation `return MappingProxyType(dict(hit))` (rewrap on hit) would break this test. This is the contract S2-04's warm-path test will assert on (memo-hit count == 1 across the four Phase 1 probes that consume `package.json`).
- [ ] **AC-7.** `mtime_ns` change triggers re-parse: rewriting the file with identical bytes but a different mtime (via `os.utime`) → `memo.get(p)` returns a different instance (`a is not b`). Pins that mtime is part of the key; a mutation dropping `st_mtime_ns` from the tuple is caught.
- [ ] **AC-8.** `size` change triggers re-parse: rewriting the file with different bytes (different size, same mtime if possible) → `memo.get(p)` returns a different instance. Mutation dropping size is caught.
- [ ] **AC-9.** `st_mtime_ns` integer discipline pinned: the key's mtime element is `int` (nanoseconds), **not** `float` (seconds). A test reads the key tuple and asserts `isinstance(k[1], int) and k[1] >= path.stat().st_mtime_ns`. A mutation swapping `st.st_mtime_ns` → `int(st.st_mtime * 1e9)` (lossy float conversion) survives this assertion only if the value coincidentally equals; reliably caught by parameterizing two rapid writes within < 1 ms (forcing ns-level resolution to disambiguate).
- [ ] **AC-10.** Parse-failure paths — `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`:
  - The exception **propagates** from `memo.get(p)` unchanged.
  - The cache is NOT populated (`memo._cache` remains empty after the raise).
  - Subsequent calls retry the parse and observe the same error (or the new value if the file was fixed in between).
  - A test parametrizes all four error classes (where simulatable) and pins both the propagation and the no-cache invariants.
- [ ] **AC-11.** Symlink interaction with `path.stat()` vs `safe_json.load`'s `O_NOFOLLOW`: a symlinked `package.json` → `path.stat()` succeeds (follows the symlink), but `safe_json.load` raises `SymlinkRefusedError`. The memo propagates the raise and does not cache. A test creates a symlink, calls `memo.get(symlink_path)`, asserts `SymlinkRefusedError`, then deletes the symlink and creates a real file at the same path — the next call returns the parsed value (retry semantics).
- [ ] **AC-12.** `FileNotFoundError` on `path.stat()` returns `None` (no raise). A test asserts `memo.get(Path("/nonexistent/package.json")) is None`. **Other `OSError` subclasses** (e.g., `PermissionError`) **propagate unchanged** — `FileNotFoundError` is the only swallowed error class. A test using `monkeypatch` on `Path.stat` to raise `PermissionError` asserts the raise propagates.
- [ ] **AC-13.** Structured logging events: `probe.memo.hit` on a cache hit; `probe.memo.miss` on a successful new parse. Each event carries structured fields `path: str` (the resolved absolute path string) and `allowlist_match: str` (the matched allowlist entry, e.g., `"package.json"`). On a parse failure, **no event is emitted** (the typed exception is the failure signal; downstream structlog from `safe_json.load`'s own `probe.parser.cap_exceeded` covers cap errors). Tests use `structlog.testing.capture_logs()` (matching S1-02..S1-05 hardened precedent), assert the events list shape, and assert each `event` dict's `path` is the `str(path.resolve())` form (not the raw input path).
- [ ] **AC-14.** No-disk-write invariant: `memo.get(p)` performs zero filesystem writes. Test: snapshot the tmp_path tree (recursive listing + per-file `(size, mtime_ns, sha256_of_bytes)`) before and after `memo.get(p)`; assert the snapshot is identical. Catches any future regression that adds a side-channel write (mirroring the `msgpack` rejection in `final-design.md "Components" #2`).
- [ ] **AC-15.** `BudgetingContext` extension (in [src/codegenie/coordinator/budget.py](../../../../src/codegenie/coordinator/budget.py)):
  - Two new additive fields appended after `bytes_written`, both with `None` defaults:
    - `parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None`
    - `input_snapshot: frozenset["InputFingerprint"] | None = None` (imported as `from codegenie.probes.base import InputFingerprint` — the S1-06 newtype lives there).
  - Existing fields preserved in order/types/defaults: `workspace: Path`, `raw_artifact_mb: int`, `bytes_written: int = field(default=0)`.
  - The pre-existing `report_bytes(n: int) -> None` method is untouched.
  - A test (`test_budgeting_context_has_parsed_manifest_and_input_snapshot_fields`) pins the 5-tuple of field names: `("workspace", "raw_artifact_mb", "bytes_written", "parsed_manifest", "input_snapshot")` and asserts both new fields default to `None`.
- [ ] **AC-16.** Coordinator wiring (in [src/codegenie/coordinator/coordinator.py](../../../../src/codegenie/coordinator/coordinator.py)):
  - `gather(...)` constructs **exactly one** `ParsedManifestMemo(allowlist=frozenset({"package.json"}))` at the top of the function body (after `run_id` binding, before the prelude dispatch).
  - The memo is threaded through `_dispatch_one(...)` as a new keyword argument `memo: ParsedManifestMemo` (or by partial application of `_make_probe_context`).
  - `_make_probe_context(...)` accepts a `parsed_manifest: Callable | None` keyword argument and threads it into the constructed `BudgetingContext(..., parsed_manifest=parsed_manifest)`.
  - A test (`test_gather_threads_parsed_manifest_to_ctx`) installs a stub probe whose `run()` body asserts `ctx.parsed_manifest is not None and callable(ctx.parsed_manifest)`, runs `gather(...)`, and verifies the stub's assertion fired (probe completed without `AssertionError`).
- [ ] **AC-17.** Cross-gather isolation: two sequential `gather(...)` calls on the same repo construct **two distinct memo instances**. A test runs `gather(...)` twice with a stub probe that captures `id(ctx.parsed_manifest)`; asserts the captured IDs differ across the two gathers. Mutation: module-level memo (singleton) is caught.
- [ ] **AC-18.** Same-gather sharing: within one `gather(...)` invocation, every probe sees **the same memo callable**. A test runs `gather(...)` with two stub probes (one base, one rest) that each capture `id(ctx.parsed_manifest)`; asserts the IDs are equal. Mutation: rebuilding the memo per-probe is caught.
- [ ] **AC-19.** `Probe.run(snap, ctx)` signature is unchanged. The ABC contract (`tests/unit/test_probe_contract.py`) remains green. No edits to `src/codegenie/probes/base.py`, `docs/localv2.md §4`, `tests/snapshots/probe_contract.v1.json`, or `scripts/regen_probe_contract_snapshot.py`.
- [ ] **AC-20.** The `ParsedManifestMemo` kernel is **closed for modification**: a test (`test_memo_kernel_is_closed_for_modification`) reads the module-level surface and asserts the only public symbol is `ParsedManifestMemo`; no module-level `ALLOWLIST` constant, no module-level state. The allowlist policy is **injected** via constructor (AC-2). This is the Open/Closed shape that lets Phase 2's `IndexHealthProbe` reuse the kernel with a wider allowlist without touching `parsed_manifest_memo.py`.
- [ ] **AC-21.** A red TDD test exists, is committed at a red commit, and turns green after the implementation lands.
- [ ] **AC-22.** `ruff check src tests`, `ruff format --check src tests`, `mypy --strict src tests`, and the full test suite all pass on the touched files (`src/codegenie/coordinator/parsed_manifest_memo.py`, `src/codegenie/coordinator/budget.py`, `src/codegenie/coordinator/coordinator.py`, `tests/unit/coordinator/`).

## Implementation outline

1. **Create `src/codegenie/coordinator/parsed_manifest_memo.py`:**

   ```python
   """In-coordinator per-gather parse memo for allowlisted manifests.

   References:
     - phase-arch-design.md §"Component design" #3
     - ADR-0002 (parsed_manifest_memo)
     - final-design.md "Components" #2 — explicit msgpack-side-channel rejection.

   The memo lives entirely in process memory; it never writes to disk and
   never crosses ``OutputSanitizer`` or ``_ProbeOutputValidator`` (Phase 0
   ADR-0008 / ADR-0010). Per-gather lifetime: the coordinator constructs
   one instance at the top of ``gather()`` and discards it on return.
   """

   from __future__ import annotations

   from collections.abc import Mapping
   from pathlib import Path
   from types import MappingProxyType
   from typing import Any, Final

   import structlog

   from codegenie.parsers import safe_json

   __all__ = ["ParsedManifestMemo"]

   _DEFAULT_ALLOWLIST: Final[frozenset[str]] = frozenset({"package.json"})
   _MAX_BYTES: Final[int] = 5_242_880  # 5 MiB — phase-arch-design.md §Component design #3

   _logger = structlog.get_logger(__name__)


   class ParsedManifestMemo:
       """Per-gather memo. Not thread-safe (Phase 1 coordinator dispatches serially per event-loop)."""

       def __init__(self, *, allowlist: frozenset[str] = _DEFAULT_ALLOWLIST) -> None:
           self._allowlist: frozenset[str] = allowlist
           self._cache: dict[tuple[str, int, int], MappingProxyType[str, Any]] = {}

       def get(self, path: Path) -> Mapping[str, Any] | None:
           if path.name not in self._allowlist:
               return None
           try:
               st = path.stat()
           except FileNotFoundError:
               return None
           # NB: other OSError subclasses (PermissionError, etc.) propagate.

           # S1-08 will replace this key with (input_fingerprint.content_hash,) sourced
           # from ctx.input_snapshot, closing the TOCTOU window between stat() and load().
           key = (str(path.resolve()), st.st_mtime_ns, st.st_size)

           hit = self._cache.get(key)
           if hit is not None:
               _logger.info("probe.memo.hit", path=key[0], allowlist_match=path.name)
               return hit

           parsed = safe_json.load(path, max_bytes=_MAX_BYTES)  # may raise; do NOT cache on failure
           wrapped: MappingProxyType[str, Any] = MappingProxyType(parsed)
           self._cache[key] = wrapped
           _logger.info("probe.memo.miss", path=key[0], allowlist_match=path.name)
           return wrapped
   ```

2. **Edit `src/codegenie/coordinator/budget.py`** (additive only, no behavior change):
   - Add the import `from codegenie.probes.base import InputFingerprint` under `TYPE_CHECKING` (avoid circular at module load) or as a string-typed forward reference: `frozenset["InputFingerprint"]`.
   - Add to `BudgetingContext`:
     ```python
     parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
     input_snapshot: frozenset["InputFingerprint"] | None = None
     ```
   - Update the module docstring to name the S1-07 extension and ADR-0002.

3. **Edit `src/codegenie/coordinator/coordinator.py`** (surgical — two changes):
   - Import: `from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo`.
   - Inside `gather(...)` near top (after `run_id` binding, before `cpu` / `bound` calculation), add:
     ```python
     memo = ParsedManifestMemo()  # default allowlist = frozenset({"package.json"})
     ```
   - Thread the memo into both prelude and rest dispatches by extending `_dispatch_one`'s signature with `memo: ParsedManifestMemo` and `_make_probe_context`'s signature with `parsed_manifest: Callable[..., Mapping[str, Any] | None] | None`. In `_make_probe_context`, return `BudgetingContext(workspace=workspace, raw_artifact_mb=raw_artifact_mb, parsed_manifest=parsed_manifest)`.

4. **Tests under `tests/unit/coordinator/test_parsed_manifest_memo.py`** + `tests/unit/coordinator/test_coordinator_injects_memo.py` (new directory).

## TDD plan — red / green / refactor

### Red — failing tests first

`tests/unit/coordinator/__init__.py` (empty marker).

`tests/unit/coordinator/test_parsed_manifest_memo.py`:

```python
"""Unit tests for ``ParsedManifestMemo`` — S1-07.

Each test is annotated with its AC and the mutation it catches.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import MappingProxyType

import pytest
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    return p


# AC-2 — allowlist injection
def test_init_accepts_custom_allowlist():
    m = ParsedManifestMemo(allowlist=frozenset({"package.json", "scip-index.json"}))
    assert "scip-index.json" in m._allowlist  # noqa: SLF001 — internal-state assertion is intentional


# AC-3, AC-5 — first call parses, wraps in MappingProxyType
def test_first_call_parses_and_returns_mappingproxy(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    out = ParsedManifestMemo().get(p)
    assert isinstance(out, MappingProxyType)
    assert out["name"] == "x"


# AC-6 — identity contract on cache hit
def test_second_call_returns_same_instance(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    b = m.get(p)
    # Mutation `return MappingProxyType(dict(hit))` (rewrap on hit) breaks this test.
    assert a is b


# AC-7 — mtime change triggers re-parse
def test_mtime_change_triggers_reparse(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    time.sleep(0.01)
    os.utime(p, ns=(time.time_ns(), time.time_ns()))
    b = m.get(p)
    assert a is not b


# AC-8 — size change triggers re-parse
def test_size_change_triggers_reparse(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    p.write_text(json.dumps({"name": "xxxxxxxxxxxxxxxxx"}))
    b = m.get(p)
    assert a is not b


# AC-9 — mtime integer discipline (ns precision)
def test_key_uses_int_ns_mtime_not_float_seconds(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    m.get(p)
    (key,) = m._cache.keys()  # noqa: SLF001
    assert isinstance(key[0], str)
    assert isinstance(key[1], int)  # ns mtime; float would fail
    assert isinstance(key[2], int)  # size


# AC-4 — non-allowlisted path returns None
def test_non_allowlisted_path_returns_none(tmp_path):
    p = _write(tmp_path, "yarn.lock", {"k": 1})
    assert ParsedManifestMemo().get(p) is None


# AC-4 — case-sensitive allowlist
def test_allowlist_is_case_sensitive(tmp_path):
    p = _write(tmp_path, "Package.json", {"name": "x"})  # capital P
    assert ParsedManifestMemo().get(p) is None
    # Mutation: `path.name.lower() in allowlist` would pass this test as not-None.


# AC-10 — parse failure does not cache
def test_parse_failure_does_not_cache(tmp_path):
    p = tmp_path / "package.json"
    p.write_text("{not json}")
    m = ParsedManifestMemo()
    with pytest.raises(e.MalformedJSONError):
        m.get(p)
    assert m._cache == {}  # noqa: SLF001
    p.write_text(json.dumps({"name": "ok"}))
    out = m.get(p)
    assert out is not None and out["name"] == "ok"


# AC-10 — size-cap raise does not cache
def test_size_cap_exceeded_does_not_cache(tmp_path, monkeypatch):
    p = _write(tmp_path, "package.json", {"k": "x" * 100})
    m = ParsedManifestMemo()

    def _raise(*_a, **_kw):
        raise e.SizeCapExceeded("simulated cap breach")

    monkeypatch.setattr("codegenie.coordinator.parsed_manifest_memo.safe_json.load", _raise)
    with pytest.raises(e.SizeCapExceeded):
        m.get(p)
    assert m._cache == {}  # noqa: SLF001


# AC-11 — symlink path: stat() succeeds, safe_json refuses
def test_symlink_path_raises_and_does_not_cache(tmp_path):
    target = _write(tmp_path, "real_package.json", {"name": "x"})
    link = tmp_path / "package.json"
    link.symlink_to(target)
    m = ParsedManifestMemo()
    with pytest.raises(e.SymlinkRefusedError):
        m.get(link)
    assert m._cache == {}  # noqa: SLF001
    # Replace symlink with a real file; retry should succeed.
    link.unlink()
    link.write_text(json.dumps({"name": "ok"}))
    assert m.get(link)["name"] == "ok"


# AC-12 — missing file returns None
def test_missing_file_returns_none(tmp_path):
    assert ParsedManifestMemo().get(tmp_path / "no-such" / "package.json") is None


# AC-12 — other OSError propagates
def test_permission_error_propagates(tmp_path, monkeypatch):
    p = _write(tmp_path, "package.json", {"name": "x"})

    def _raise(self):
        raise PermissionError("simulated")

    monkeypatch.setattr(Path, "stat", _raise)
    with pytest.raises(PermissionError):
        ParsedManifestMemo().get(p)


# AC-13 — structured events with capture_logs
def test_emits_memo_hit_and_miss_events_with_structured_fields(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    with capture_logs() as logs:
        m.get(p)  # miss
        m.get(p)  # hit

    events = [(r["event"], r.get("path"), r.get("allowlist_match")) for r in logs]
    miss = next(e for e in events if e[0] == "probe.memo.miss")
    hit = next(e for e in events if e[0] == "probe.memo.hit")
    assert miss[1] == str(p.resolve())
    assert miss[2] == "package.json"
    assert hit[1] == str(p.resolve())
    assert hit[2] == "package.json"


# AC-13 — no event on parse failure
def test_no_event_on_parse_failure(tmp_path):
    p = tmp_path / "package.json"
    p.write_text("{not json}")
    m = ParsedManifestMemo()
    with capture_logs() as logs, pytest.raises(e.MalformedJSONError):
        m.get(p)
    assert not any(r["event"].startswith("probe.memo.") for r in logs)


# AC-14 — no disk write
def test_memo_does_not_write_to_disk(tmp_path):
    p = _write(tmp_path, "package.json", {"name": "x"})

    def _snapshot() -> set[tuple[str, int, int]]:
        return {(str(q.relative_to(tmp_path)), q.stat().st_size, q.stat().st_mtime_ns)
                for q in tmp_path.rglob("*") if q.is_file()}

    before = _snapshot()
    ParsedManifestMemo().get(p)
    after = _snapshot()
    assert before == after


# AC-20 — module surface is closed for modification
def test_module_only_public_symbol_is_parsedmanifestmemo():
    import codegenie.coordinator.parsed_manifest_memo as m
    assert m.__all__ == ["ParsedManifestMemo"]
```

`tests/unit/coordinator/test_coordinator_injects_memo.py`:

```python
"""Coordinator-wiring smoke tests for ``ParsedManifestMemo`` injection — S1-07."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from codegenie.coordinator.coordinator import gather
# import the Phase 0 fixtures factory + Probe subclass helpers
from tests.unit._coordinator_fixtures import (  # type: ignore[import-untyped]
    make_repo_snapshot,
    make_task,
    make_cache,
    make_sanitizer,
    make_config,
    StubProbe,  # an ABC-conforming probe used in S3-05's tests
)


# AC-16 — coordinator threads parsed_manifest onto every ctx
@pytest.mark.asyncio
async def test_gather_threads_parsed_manifest_to_ctx(tmp_path):
    captured: dict[str, Any] = {}

    async def _assert_ctx(repo, ctx):
        captured["parsed_manifest"] = ctx.parsed_manifest
        captured["is_callable"] = callable(ctx.parsed_manifest)
        return ...  # build minimal ProbeOutput

    probe = StubProbe(name="stub.a", layer="A", tier="base", run=_assert_ctx)
    await gather(
        make_repo_snapshot(tmp_path), make_task(), [probe],
        make_config(), make_cache(tmp_path), make_sanitizer(),
    )
    assert captured["is_callable"] is True


# AC-17 — cross-gather isolation
@pytest.mark.asyncio
async def test_cross_gather_isolation(tmp_path):
    seen: list[int] = []

    async def _capture(repo, ctx):
        seen.append(id(ctx.parsed_manifest))
        return ...

    probe = StubProbe(name="stub.a", layer="A", tier="base", run=_capture)
    snap = make_repo_snapshot(tmp_path)
    task = make_task()
    cfg = make_config()
    cache = make_cache(tmp_path)
    san = make_sanitizer()
    await gather(snap, task, [probe], cfg, cache, san)
    await gather(snap, task, [probe], cfg, cache, san)
    assert len(seen) == 2
    assert seen[0] != seen[1]


# AC-18 — same-gather sharing across probes
@pytest.mark.asyncio
async def test_same_gather_sharing_across_probes(tmp_path):
    seen: list[int] = []

    async def _capture(repo, ctx):
        seen.append(id(ctx.parsed_manifest))
        return ...

    p1 = StubProbe(name="stub.a", layer="A", tier="base", run=_capture)
    p2 = StubProbe(name="stub.b", layer="A", tier="task_specific", run=_capture)
    await gather(
        make_repo_snapshot(tmp_path), make_task(), [p1, p2],
        make_config(), make_cache(tmp_path), make_sanitizer(),
    )
    assert len(seen) == 2
    assert seen[0] == seen[1]
```

`tests/unit/test_coordinator_budget.py` (extend existing):

```python
# AC-15 — BudgetingContext gains parsed_manifest + input_snapshot fields
def test_budgeting_context_has_parsed_manifest_and_input_snapshot_fields():
    import dataclasses

    from codegenie.coordinator.budget import BudgetingContext

    names = tuple(f.name for f in dataclasses.fields(BudgetingContext))
    assert names == ("workspace", "raw_artifact_mb", "bytes_written",
                     "parsed_manifest", "input_snapshot"), \
        "BudgetingContext field shape is the runtime ctx contract — see ADR-0002 + S1-07"
    bc = BudgetingContext(workspace=Path("/tmp"), raw_artifact_mb=10)
    assert bc.parsed_manifest is None
    assert bc.input_snapshot is None
```

Run; confirm all the above fail at the import or assert layer. Commit as red.

### Green — minimal implementation

Implement per outline. Resist any urge to expand `ProbeContext` to incorporate `report_bytes` or to collapse `BudgetingContext` into `ProbeContext`. Per Rule 3, this story preserves both types — the duality is a known smell tracked for a future ADR (see Notes for the implementer).

### Refactor — clean up

- Module docstring on `parsed_manifest_memo.py` names `phase-arch-design.md §"Component design" #3`, ADR-0002, and the explicit msgpack rejection from `final-design.md "Components" #2`.
- The `5_242_880` literal is `_MAX_BYTES: Final[int] = 5_242_880`. The `5 MiB` arch reference goes in the comment.
- The line `key = (str(path.resolve()), st.st_mtime_ns, st.st_size)` carries an inline `# S1-08:` comment naming the planned flip to `(content_hash,)` from `ctx.input_snapshot`.
- The structlog literals `"probe.memo.hit"` / `"probe.memo.miss"` stay as bare strings in S1-07 (no `Final[str]` constants — Rule 2 / YAGNI; constants land alongside the analogous `probe.parser.cap_exceeded` family in S1-10 if the event-vocabulary registry ADR fires).
- Thread-safety docstring on `ParsedManifestMemo`: "Not thread-safe; per-gather coordinator scope assumes serial access on the event loop. Phase 14 (concurrent gathers under Temporal Activities) constructs a fresh memo per Activity — wrapping with `asyncio.Lock` is unnecessary in that model."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/parsed_manifest_memo.py` | New — `ParsedManifestMemo` kernel |
| `src/codegenie/coordinator/budget.py` | Add 2 None-default fields to `BudgetingContext` (mirroring S1-06's `ProbeContext` extension) |
| `src/codegenie/coordinator/coordinator.py` | Surgical: construct memo per `gather()`, thread through `_dispatch_one` → `_make_probe_context` → `BudgetingContext(..., parsed_manifest=memo.get)` |
| `tests/unit/coordinator/__init__.py` | New — package marker |
| `tests/unit/coordinator/test_parsed_manifest_memo.py` | New — ~16 unit tests, each annotated with AC + mutation caught |
| `tests/unit/coordinator/test_coordinator_injects_memo.py` | New — coordinator wiring smoke tests (AC-16/17/18) |
| `tests/unit/test_coordinator_budget.py` | Extend — pin the new field shape on `BudgetingContext` (AC-15) |

## Out of scope

- **Pre-dispatch input-snapshot pass (Gap 1)** — S1-08 lands the `(content_hash,)`-keyed flip and the `ctx.input_snapshot` computation. S1-07's key remains `(path, mtime_ns, size)`.
- **Wave-1 prelude ADR** — `phase-arch-design.md §"Open implementation questions" #11` leaves ADR creation as judgment in S1-07. **Recommendation:** skip ADR creation here; the Wave-1 prelude is documented coordinator behavior already, not a new commitment. File an ADR in Phase 2 if `IndexHealthProbe` extends the prelude to multi-probe.
- **Allowlist beyond `{"package.json"}`** — Phase 2 extends. AC-2 pins the *injection* path so Phase 2's extension is a constructor-arg change in the coordinator, not an edit to the memo kernel.
- **Cross-gather caching** — by design, never. Per-gather memo discarded at gather end.
- **`ProbeContext` ↔ `BudgetingContext` collapse** — pre-existing duality (S1-06 added fields to the contract type; runtime instance is `BudgetingContext`). S1-07 mirrors the field set onto `BudgetingContext` to close the runtime gap. A future ADR may collapse the two; not in this story.
- **`report_bytes` integration with the memo** — orthogonal. The memo never writes to disk, so no budget accounting applies.
- **Event-vocabulary registry / `Final[str]` constants** — `probe.memo.hit` / `probe.memo.miss` remain bare string literals. S1-10 (or its successor) lifts the family alongside `probe.parser.cap_exceeded`.

## Notes for the implementer

- **`MappingProxyType` only wraps the top level.** Nested dicts/lists are returned by reference. Probes treat the result as `Mapping[str, Any]`-typed; mypy flags mutation, but a determined caller can still `dict(out["scripts"])["new"] = "x"` — runtime convention, not a static guarantee. Do not deep-freeze; the perf cost isn't justified.
- **Identity check (`a is b`)** is the load-bearing contract for S2-04's warm-path test (`probe.memo.hit` count == 1 across the four `package.json`-consuming probes). Do not replace `MappingProxyType` with a new instance on each hit.
- **Failure must not cache.** Per ADR-0002 §Decision: "if `safe_json.load` raises, the memo does *not* cache the result; the next probe retries and sees the same error." Inserts into `_cache` happen **after** successful parse only.
- **Memo never crosses `OutputSanitizer` or `_ProbeOutputValidator`.** The dict is a parser product, not a `ProbeOutput`-shaped artifact. There is no `ProbeOutput` byte path leaving the memo — `ctx.parsed_manifest=memo.get` hands probes a *callable*, not a `ProbeOutput`. AC-14's behavioral check pins this with a tmp_path snapshot.
- **Key shape today is `(absolute_path, mtime_ns, size)`.** S1-08 flips this to `content_hash` sourced from the pre-dispatch `InputFingerprint` snapshot (`ctx.input_snapshot`). Mark the key-construction line with `# S1-08:` in the green commit so the follow-up is grep-friendly.
- **Symlink semantics:** `path.stat()` follows symlinks; `safe_json.load` opens with `O_NOFOLLOW` and raises `SymlinkRefusedError` on a symlinked final component. A symlinked `package.json` therefore: `stat()` returns target's metadata → key computed → `safe_json.load(link)` raises `SymlinkRefusedError` → memo does NOT cache → next call retries with same outcome. AC-11 pins this end-to-end.
- **`FileNotFoundError` is the ONLY OSError class converted to `None`.** Permission errors, IO errors, and so on propagate. The memo is best-effort with respect to *file presence*, not best-effort with respect to *OS-level access*.
- **Threading:** Phase 0 coordinator uses asyncio + a bounded worker pool, with probe `run()` calls happening on the event loop (`asyncio.to_thread` used for blocking I/O internally). `ParsedManifestMemo` is **not thread-safe**; calls happen serially in Phase 0/1's model. Document this in the class docstring: "Not thread-safe; per-gather coordinator scope assumes serial access on the event loop." Phase 14 (concurrent Activities) constructs a fresh memo per Activity, so no lock is needed.
- **Coordinator change is one of three allowed Phase-0 source edits in Step 1** (the others are `probes/base.py` in S1-06 and `exec.py` in S1-10; `budget.py` is also touched here as an additive extension of S3-05's surface). No other Phase-0 source files change in this story.
- **`BudgetingContext` vs `ProbeContext` duality** — Phase 0 ships `BudgetingContext` as the runtime ctx (it carries the `report_bytes` callback the budget enforcement contract requires). S1-06 added `parsed_manifest`/`input_snapshot` to the `ProbeContext` *contract* type, but the runtime *instance* probes receive is still `BudgetingContext`. S1-07 closes the runtime gap by mirroring the two `ProbeContext` field additions onto `BudgetingContext`. The static contract is `ProbeContext`; the runtime shape is `BudgetingContext`. Probes typed `ctx: ProbeContext` see `BudgetingContext` at runtime — structural compatibility holds because `BudgetingContext` now has the same five field-shapes (`workspace`, plus the two S1-06 additions, plus the two pre-existing budget fields). A future ADR may collapse the two; flagging this as a known smell now so the eventual refactor has a paper trail.
- **Design-pattern framing (recorded for posterity):** the kernel/policy split is the Open/Closed move — `ParsedManifestMemo` is the kernel (knows nothing about *which* paths are memoized); the allowlist is the *policy* (data, injected via constructor). Phase 2's reuse of this kernel for SCIP index manifests is "construct with `frozenset({"package.json", "scip-index.json"})`" — zero edits to `parsed_manifest_memo.py`. The same shape the validated S1-02..S1-05 stories surfaced for `parsers/_io.py` and `catalogs/__init__.py`.
