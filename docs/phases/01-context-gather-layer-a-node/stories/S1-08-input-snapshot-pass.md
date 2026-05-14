# Story S1-08 — Pre-dispatch input-snapshot pass (Gap 1)

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Done — 2026-05-14
**Effort:** M
**Depends on:** S1-06, S1-07
**ADRs honored / amended:** ADR-0002 (amended in this story, see AC-22)

## Done — evidence block (2026-05-14)

All 23 ACs verified. Implementation landed in a single attempt; the harness's RED → GREEN → REFACTOR cycle ran clean. Full attempt log: [`_attempts/S1-08.md`](_attempts/S1-08.md). Lessons appended: L-15, L-16.

### Code shipped

- [src/codegenie/coordinator/input_snapshot.py](../../../../src/codegenie/coordinator/input_snapshot.py) — new module; `__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]`; sentinel constants `_CONTENT_HASH_OVERSIZE = "<oversize>"`, `_CONTENT_HASH_REFUSED = "<refused>"`; pure `_fingerprint_from_fd` + impure `compute_input_snapshot` (functional core / imperative shell split); `_canonical_abs_path(matched) = str(matched.parent.resolve() / matched.name)` helper preserves the symlink's own name in the refused branch.
- [src/codegenie/coordinator/parsed_manifest_memo.py](../../../../src/codegenie/coordinator/parsed_manifest_memo.py) — `get(self, path, *, content_hash: str | None = None)` additive signature; sentinel-bypass branch (`content_hash.startswith("<")` → `None`); dual key shapes coexist (`(content_hash,)` vs S1-07's `(absolute_path, mtime_ns, size)`).
- [src/codegenie/coordinator/coordinator.py](../../../../src/codegenie/coordinator/coordinator.py) — `_dispatch_one` computes the per-probe snapshot before constructing `ctx`, builds the adapter via `make_parsed_manifest_adapter`, and threads both onto the runtime `BudgetingContext` via the extended `_make_probe_context` keyword-only signature.
- [docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md](../ADRs/0002-parsed-manifest-memo-on-probe-context.md) — amended per AC-22 (key-bullet rewritten to the dual-shape form; Consequences §"Resolved in S1-08"; `**Last amended:**` line updated).

### Tests

- [tests/unit/coordinator/test_input_snapshot.py](../../../../tests/unit/coordinator/test_input_snapshot.py) — 20 tests covering AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11 (5-way parametrize), AC-12, AC-13 (present + missing + roundtrip), AC-20, AC-21.
- [tests/unit/coordinator/test_coordinator_threads_input_snapshot.py](../../../../tests/unit/coordinator/test_coordinator_threads_input_snapshot.py) — 4 tests covering AC-16, AC-17, AC-18, AC-19.
- [tests/unit/coordinator/test_parsed_manifest_memo.py](../../../../tests/unit/coordinator/test_parsed_manifest_memo.py) — appended `test_memo_dual_keys_coexist` (AC-14) + `test_memo_sentinel_content_hash_returns_none` (AC-15); S1-07's 20 prior tests remain green.
- [tests/unit/coordinator/test_coordinator_injects_memo.py](../../../../tests/unit/coordinator/test_coordinator_injects_memo.py) — minimal update: `ctx.parsed_manifest.__self__` → `ctx.parsed_manifest.__memo__` (the closure adapter exposes the memo on `__memo__` so S1-07's same-gather-sharing / cross-gather-isolation invariants stay testable).
- [tests/unit/test_adr_0002_records_s1_08_amendment.py](../../../../tests/unit/test_adr_0002_records_s1_08_amendment.py) — doc-grep AC-22.

### Gates

- `pytest tests/unit/coordinator/ tests/unit/test_adr_0002_records_s1_08_amendment.py` → 53 passed
- Full suite: 843 passed, 3 failed (pre-existing — `lint-imports` not on PATH; `pre-commit` hook catches an unrelated `yaml.load(` without `Loader=` in [src/codegenie/catalogs/\_\_init\_\_.py](../../../../src/codegenie/catalogs/__init__.py) — both reproduce on master before S1-08).
- `ruff check src tests` → clean
- `ruff format --check src tests` → clean
- `mypy --strict src` → 42 source files, no issues
- No new direct `blake3` import anywhere under `src/codegenie/`.

## Validation notes (added 2026-05-14 by phase-story-validator)

Four critics ran (Coverage, Test-Quality, Consistency, Design-Patterns). The story landed with a sound Goal (close the Gap 1 TOCTOU window by pinning per-probe input snapshots at coordinator dispatch time), but the original draft carried 7 block-tier defects and ~25 harden-tier gaps. The most load-bearing:

- **Reference path for `InputFingerprint` was wrong.** S1-06 moved the newtype into `src/codegenie/probes/base.py`; the original story imported from a non-existent `coordinator/input_snapshot.py`. The red commit would have failed with `ModuleNotFoundError` for the wrong reason. Hardened: all imports go through `codegenie.probes.base`.
- **Wiring target was wrong.** AC-3 said "assigned to that probe's `ProbeContext`" — but the runtime ctx is `BudgetingContext` (S1-07 lesson; the `ProbeContext` ↔ `BudgetingContext` duality is the phase's standing smell). S1-07 already mirrored `input_snapshot` onto `BudgetingContext`; S1-08's wiring goes through `_make_probe_context → BudgetingContext(..., input_snapshot=snapshot)`. Hardened: AC-3 + AC-4 pin the wiring at the runtime-ctx site.
- **ADR-0001 chokepoint risk.** The original outline said "use `hashing.py`" but `content_hash(path)` opens the path directly (follows symlinks); the helper must call `content_hash_bytes(data)` on bytes already read through an `O_NOFOLLOW` fd. Hardened: AC-7 + AC-8 pin the chokepoint and forbid direct `blake3` imports.
- **The TOCTOU-closure red test couldn't actually prove the closure.** The original test bumped `mtime` on a file with identical content — `content_hash` was naturally equal, so a memo that completely ignores `content_hash` and still keys on `(path, mtime, size)` would arguably pass. The real Gap 1 scenario is: **bytes change** mid-gather, yet the pre-frozen snapshot continues to serve the parse of the old bytes. Hardened: T-7 rewrites the test to overwrite bytes between two `memo.get(p, content_hash=old)` calls and asserts identity (the pinned parse is preserved).
- **Self-contradictions in oversize / symlink / Rule-12 OSError handling.** Three different prescriptions across AC-2, Green block, and Notes for implementer. Hardened: AC-9 (oversize → `<oversize>` sentinel + warning event), AC-10 (symlink → `<refused>` sentinel + retry semantics), AC-11 (narrow catch — only `ELOOP` and `FileNotFoundError` are swallowed; every other `OSError` propagates per Rule 12 + Phase 0 `parsers/_io.py` precedent).
- **AC-5 (additive memo signature) and AC-7 (snapshot-missing path) contradicted each other.** Hardened: the memo signature is additive (`content_hash: str | None = None` falls back to S1-07's `(abspath, mtime_ns, size)` key); the adapter passes `content_hash=None` for paths not in the snapshot, and the memo's S1-07 path-stat fallback still parses and caches. CN9/TQ10 reconciled.
- **Departure from arch §"Gap analysis" Gap 1 line 990 ("full flip")** surfaced and recorded. Per Rule 7 (surface conflicts, don't average them): S1-08 ships the additive variant intentionally — preserves S1-07's hardened test suite intact, and allows non-coordinator callers (Phase 14 tests, ad-hoc CLI usage) to continue using `memo.get(p)` without re-implementing snapshot construction. AC-22 records the departure and patches ADR-0002.
- **Path-canonicalization protocol unpinned.** `fp.path` shape vs. the adapter's lookup key were silently misaligned (`as_posix()` in tests vs `str(resolve())` in Notes). On Windows they diverge and the adapter silently misses every lookup, re-opening the TOCTOU window the story is supposed to close. Hardened: AC-12 pins `fp.path == str(matched_path.resolve())` and rewires the test to assert the roundtrip.
- **Adapter `_make_parsed_manifest_adapter(snapshot, memo)` lifted out of Notes into an explicit named helper** so it's independently testable (AC-13). Same Open/Closed shape S1-07 set for the memo kernel.
- **Functional core / imperative shell split.** `_compute_input_snapshot` is decomposed into a pure `_fingerprint_from_fd(fd, abs_path, *, max_bytes)` helper and the impure orchestration shell. The pure half admits a determinism property-test (T-12); the impure half stays small.
- **Module-level naming collision.** Notes suggested extracting to `coordinator/snapshot.py` — but that file already exists (S3-05, builds `RepoSnapshot`). Hardened: if extracted, the new module is `coordinator/input_snapshot.py` (mirroring the type's logical home), with a closed `__all__` per S1-07 precedent.

**Verdict:** HARDENED. Story expanded from 11 single-bullet ACs to 23 individually verifiable ACs; TDD plan rewritten with 14 named tests each tagged with its AC and the mutation it catches; Notes-for-implementer surfaces design opportunities surfaced beyond the rule-of-three threshold (functional-core split as Notes; smart constructor on `InputFingerprint` recorded as future move because the contract surface is frozen by ADR-0007); ADR-0002 amendment AC added; `localv2.md §4` confirmed unaffected (the memo's signature change is internal coordinator detail, not part of §4's probe-contract surface).

Full validation report: [`_validation/S1-08-input-snapshot-pass.md`](_validation/S1-08-input-snapshot-pass.md).

## Context

The Phase 0 / S1-07 memo keys parsed dicts by `(str(path.resolve()), mtime_ns, size)` — a stat-tuple key. That key is TOCTOU-sensitive across `NodeManifestProbe`'s combined read of `package.json` (via the memo) and the lockfile (via `safe_yaml.load` / `safe_json.load`): `package.json` can be edited mid-gather between the moment the probe's `declared_inputs` content-hash is computed (cache-key derivation) and the moment the memo is consulted. The cache entry's key then reflects the old bytes but its data was parsed from the new bytes — logical inconsistency *within* a single gather.

The fix per `phase-arch-design.md §"Gap analysis"` Gap 1 (lines 982–990): pin each probe's input snapshot at **coordinator dispatch time**, expose it as `ctx.input_snapshot: frozenset[InputFingerprint]`, and key the memo by `content_hash` sourced from the snapshot rather than by live `os.stat`. After this story:

- Mid-gather edits to `package.json` cannot poison `NodeManifest`'s cache key.
- The memo serves the parse of the **snapshotted bytes** for the entire gather; the audit anchor is coherent with the bytes that were parsed.
- Phase 14's webhook-driven continuous gather (where mid-gather concurrent edits are the norm, not the exception) inherits the seam at zero additional cost.

Cost: ~5 ms of pre-dispatch I/O for the 1k-file fixture. Benefit: closes Gap 1; ADR-0002 §Consequences's "future amendment" line collapses into landed reality.

**Departure from arch (recorded per Rule 7).** Arch line 990 says "The memo's key changes **from** `(abspath, mtime_ns, size)` **to** `(content_hash,)`" — a full flip. S1-08 implements the **additive** variant: the memo gains a `content_hash: str | None = None` parameter; when provided, the cache key is `(content_hash,)`; when omitted, the legacy `(str(path.resolve()), mtime_ns, size)` key shape is used unchanged. Rationale: (a) preserves S1-07's hardened test suite — the executor doesn't have to rewrite ~16 tests inside this story's PR; (b) supports non-coordinator callers (test paths that construct `memo` directly without first running `_compute_input_snapshot`); (c) the coordinator's adapter always passes `content_hash=...` for snapshotted paths, so the on-the-warm-path behavior is the arch-prescribed shape — no observable regression. AC-22 records the departure and amends ADR-0002 accordingly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis"` Gap 1 (lines 982–990) — full rationale; the seam: coordinator computes `(path, mtime_ns, size, content_hash)` once before dispatch.
  - `../phase-arch-design.md §"Component design" #3` (lines 492–507) — `ParsedManifestMemo`'s key gains the `content_hash` shape sourced from the snapshot.
  - `../phase-arch-design.md §"Data model"` — `InputFingerprint` shape (S1-06 lands the type).
  - `../phase-arch-design.md §"Edge cases"` row 16 — mid-gather edit; the snapshot pins the parse for the current gather.
  - `../phase-arch-design.md §"Process view"` — the sequence: Coordinator constructs memo, then per probe computes `input_snapshot`, then dispatches.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — S1-08 amends §"`ParsedManifestMemo` semantics" (Key bullet) and §Consequences (resolved-in-this-ADR note). See AC-22.
- **Phase 0 ADRs (load-bearing for this story):**
  - `../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md` — the single-chokepoint discipline for `blake3` / `hashlib`. The snapshot pass MUST go through `codegenie.hashing.content_hash_bytes`.
  - `../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-by-doc-snapshot.md` — `probes/base.py` is stdlib-only; `InputFingerprint` may not grow a classmethod that imports `os`/`codegenie.hashing`.
  - `../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md` & `0010-pydantic-probe-output-validator.md` — the trust boundaries the snapshot pass MUST NOT cross (it never writes to disk).
- **Predecessor stories:**
  - `S1-06-probe-context-extension.md` (validator-hardened) — `InputFingerprint` lives in `src/codegenie/probes/base.py`; `ProbeContext` carries `input_snapshot: frozenset["InputFingerprint"] | None = None`.
  - `S1-07-parsed-manifest-memo.md` (validator-hardened) — `BudgetingContext` mirrors the two `ProbeContext` fields; memo signature is `get(path)`, key is `(str(path.resolve()), mtime_ns, size)`; module surface closed via `__all__ = ["ParsedManifestMemo"]`; allowlist policy is injected via `__init__(*, allowlist=...)`.
- **Existing code:**
  - `src/codegenie/coordinator/coordinator.py` — `gather()`, `_dispatch_one`, `_make_probe_context` (lines ~230, ~255, ~297) — this story extends these.
  - `src/codegenie/coordinator/budget.py` — `BudgetingContext` (S1-07 added `parsed_manifest`/`input_snapshot` here; S1-08 wires them).
  - `src/codegenie/coordinator/parsed_manifest_memo.py` — S1-07 deliverable; S1-08 extends `get()` additively.
  - `src/codegenie/probes/base.py` — `InputFingerprint` lives here (S1-06).
  - `src/codegenie/hashing.py` — `content_hash_bytes(b: bytes) -> "blake3:<hex>"` is the snapshot hash chokepoint. **Note:** `content_hash(path)` opens the path directly (no `O_NOFOLLOW`) — DO NOT call it from the snapshot pass.
  - `src/codegenie/parsers/_io.py` — precedent for the narrow-OSError catch (only `ELOOP` → `SymlinkRefusedError`; everything else propagates).
- **Smell tracked (pre-existing):** `ProbeContext` vs. `BudgetingContext` duality — see S1-07 Notes for implementer. S1-08 does NOT collapse the two types.

## Goal

Coordinator computes `frozenset[InputFingerprint]` for each probe's `declared_inputs` **once before dispatch**, freezes it on the runtime `BudgetingContext.input_snapshot`, and `ParsedManifestMemo` accepts an additive `content_hash` parameter so the coordinator's adapter can key parsed dicts by `content_hash` rather than by live `os.stat`. The Gap 1 TOCTOU window between cache-key derivation and probe parse is closed within a single gather.

## Acceptance criteria

### Snapshot helper

- [ ] **AC-1.** `_compute_input_snapshot(probe: Probe, repo_root: Path, *, max_bytes_per_file: int = _DEFAULT_MAX_BYTES_PER_FILE) -> frozenset[InputFingerprint]` exists. The helper lives at exactly **`src/codegenie/coordinator/input_snapshot.py`** (extracted from `coordinator.py` for testability; the new module declares `__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]`; per-call helpers are underscore-prefixed). Import is `from codegenie.coordinator.input_snapshot import compute_input_snapshot, make_parsed_manifest_adapter`. (NB: `coordinator/snapshot.py` is already taken by S3-05's `RepoSnapshot` builder — do not collide.) A grep test asserts `from codegenie.coordinator.input_snapshot import compute_input_snapshot` resolves and that no `coordinator/snapshot.py` line names `compute_input_snapshot`.

- [ ] **AC-2.** `InputFingerprint` is imported exclusively from `codegenie.probes.base` (S1-06's home). A grep test asserts that no file under `src/codegenie/` or `tests/` contains the string `coordinator.input_snapshot import InputFingerprint` (i.e., the type lives with the contract, the module lives with the implementation).

- [ ] **AC-3.** The helper enumerates each `declared_inputs` pattern via `Path(repo_root).glob(pattern)` uniformly — no special-casing for literal (non-glob) entries. Glob is **case-sensitive** even on macOS/Windows: a test creates `Package.json` (capital P), runs the helper with `declared_inputs=["package.json"]`, and asserts the resulting frozenset is empty. (Matches S1-07 allowlist case-sensitivity discipline.)

- [ ] **AC-4.** For each matched file the helper:
  1. opens the file via `os.open(matched_path, os.O_RDONLY | os.O_NOFOLLOW)` (refuses symlinks at the final path component);
  2. calls `os.fstat(fd)` to obtain `st_mtime_ns` and `st_size` — both sourced from the **same** fd, never from a separate `path.stat()`;
  3. reads at most `max_bytes_per_file` bytes via `os.read(fd, st_size)`;
  4. computes the content hash via `codegenie.hashing.content_hash_bytes(data)` (ADR-0001 chokepoint — `"blake3:<64-hex>"` prefixed return);
  5. closes the fd via `os.close(fd)`;
  6. records `InputFingerprint(path=str(matched_path.resolve()), mtime_ns=st.st_mtime_ns, size=st.st_size, content_hash=<hash-or-sentinel>)`.

  Construction discipline is centralized in a private `_fingerprint_from_fd(fd: int, abs_path: str, *, max_bytes: int) -> InputFingerprint` helper colocated with the snapshot module (NOT a classmethod on `InputFingerprint` — `probes/base.py` is stdlib-only per ADR-0007).

- [ ] **AC-5.** The helper returns a `frozenset[InputFingerprint]`. Test asserts `isinstance(snap, frozenset)` and that every element is a `codegenie.probes.base.InputFingerprint`. Mutation: returning `list` or `tuple` is caught.

- [ ] **AC-6.** Empty / no-match semantics: if `probe.declared_inputs == []` OR every glob matches zero files, the helper returns `frozenset()` (empty frozen set — NOT `None`, NOT raise). Test parametrizes `declared_inputs=[]` and `declared_inputs=["nonexistent-*.json"]` and asserts both produce `frozenset()`.

- [ ] **AC-7.** `InputFingerprint.content_hash` carries the **algorithm-prefix tag** — `"blake3:<64-hex>"` form returned verbatim by `codegenie.hashing.content_hash_bytes`. Test asserts `fp.content_hash.startswith("blake3:")` and `len(fp.content_hash) == len("blake3:") + 64` on every non-sentinel hash. Mutation: stripping the prefix or swapping to `hashlib.sha256` is caught.

- [ ] **AC-8.** **ADR-0001 chokepoint discipline.** The new `input_snapshot.py` module does NOT import `blake3` directly: `grep -E "^(from blake3|import blake3)" src/codegenie/coordinator/input_snapshot.py` returns zero matches. A unit test asserts this via `inspect.getsource` + simple string scan.

- [ ] **AC-9.** **Oversize handling.** If `os.fstat(fd).st_size > max_bytes_per_file`, the helper records `InputFingerprint(path=..., mtime_ns=st.st_mtime_ns, size=st.st_size, content_hash=_CONTENT_HASH_OVERSIZE)` (where `_CONTENT_HASH_OVERSIZE: Final[str] = "<oversize>"`), does NOT read the bytes, emits a structured `probe.input_snapshot.oversize` event with `path: str`, `size_bytes: int`, `cap_bytes: int`, and continues. The downstream probe's own `safe_parse` will refuse the file via its cap. Test uses `monkeypatch` to shrink `_DEFAULT_MAX_BYTES_PER_FILE` (or passes `max_bytes_per_file=1024`) and writes a 2 KB file; asserts `fp.content_hash == "<oversize>"` exactly and that the event fires.

- [ ] **AC-10.** **Symlink handling.** A symlinked declared input (the `os.open(..., O_NOFOLLOW)` call raises `OSError(errno=ELOOP)`) is recorded as `InputFingerprint(path=str(matched_path.resolve()), mtime_ns=lstat_mtime_ns, size=lstat_size, content_hash=_CONTENT_HASH_REFUSED)` (where `_CONTENT_HASH_REFUSED: Final[str] = "<refused>"`). `mtime_ns` and `size` are sourced from `os.lstat(matched_path)` (no symlink follow). The helper continues. Test creates `tmp/real.json` and symlinks `tmp/package.json → tmp/real.json`, runs the helper, asserts `fp.content_hash == "<refused>"`, no exception, no event other than (optionally) `probe.input_snapshot.symlink_refused`. Retry semantics: deleting the symlink and creating a real `package.json` at the same path → the next snapshot pass returns a real `"blake3:..."` hash.

- [ ] **AC-11.** **Rule 12 — Fail loud on unexpected OSError.** The helper swallows **only** `OSError` with `errno == ELOOP` (symlink case → `<refused>`) and `FileNotFoundError` (glob race — file vanished between `glob` and `os.open`; treated as "no entry"). Every other `OSError` propagates — including `PermissionError`, `IsADirectoryError`, and unclassified `OSError`. Test parametrizes `[OSError(errno.ELOOP, "..."), FileNotFoundError("..."), PermissionError("..."), IsADirectoryError("..."), OSError(errno.EIO, "...")]` via `monkeypatch.setattr(os, "open", ...)`; asserts the first two produce snapshot entries (sentinel or absent) and the last three propagate out of `compute_input_snapshot`. Matches `parsers/_io.py` Phase 0 precedent.

- [ ] **AC-12.** **Path canonicalization protocol.** `InputFingerprint.path` is always `str(matched_path.resolve())` — the absolute, symlink-resolved string form. The adapter (AC-13) uses the **same** form for its lookup key. A unit test (`test_snapshot_path_canonicalization_protocol`) creates a file under `tmp_path`, runs the helper, and asserts: (a) `Path(fp.path).is_absolute()`; (b) `fp.path == str((tmp_path / "package.json").resolve())`; (c) the adapter built from the same snapshot, called with a relative `Path("./package.json")` resolved against `tmp_path`, finds the fingerprint's content_hash. Mutation: using `.as_posix()` (Windows divergence) or `str(matched_path)` (relative + non-canonical) is caught.

### Adapter & memo wiring

- [ ] **AC-13.** **`make_parsed_manifest_adapter(snapshot: frozenset[InputFingerprint], memo: ParsedManifestMemo) -> Callable[[Path], Mapping[str, Any] | None]`** is a public helper exported from `coordinator/input_snapshot.py`. It precomputes a `dict[str, str]` from `fp.path → fp.content_hash` **once** (O(1) lookup per `get` call rather than O(n) scan). The returned callable, when called with a path `p`, returns `memo.get(p, content_hash=by_path.get(str(p.resolve())))`. Test (`test_parsed_manifest_adapter`) verifies: (a) calling with a path present in the snapshot returns the memo's parsed dict (memo is a real instance, file is `package.json`); (b) calling with a path NOT in the snapshot returns the memo's legacy-key result (`content_hash=None` falls back to S1-07's `(abspath, mtime_ns, size)` key — parses and caches normally); (c) the path-resolution roundtrip is closed: ingesting a path as `Path("./package.json")` resolved against `tmp_path` still finds the snapshot entry recorded under `str(...resolve())`.

- [ ] **AC-14.** **`ParsedManifestMemo.get` signature is additive.** New signature: `get(self, path: Path, *, content_hash: str | None = None) -> Mapping[str, Any] | None`. When `content_hash` is provided (non-None, non-sentinel), the cache key is `(content_hash,)` (single-element tuple); when `None`, the cache key is the S1-07 form `(str(path.resolve()), mtime_ns, size)`. Tests:
  - `test_memo_get_with_content_hash_keys_by_hash`: calling `memo.get(p, content_hash="blake3:abc...")` stores under `("blake3:abc...",)`; calling again with the same content_hash returns the **same** `MappingProxyType` instance (identity).
  - `test_memo_get_without_content_hash_falls_back_to_stat_key`: `memo.get(p)` continues to work, stores under `(str(p.resolve()), mtime_ns, size)`, and S1-07's full test suite (`tests/unit/coordinator/test_parsed_manifest_memo.py`) remains green unmodified.
  - `test_memo_dual_keys_coexist`: calling `memo.get(p, content_hash="blake3:abc")` then `memo.get(p)` produces **two** distinct cache entries (`len(memo._cache) == 2`). Mutation that removes the `content_hash=None` fallback or that conflates the two key shapes is caught.

- [ ] **AC-15.** **Sentinel-keyed memo bypass.** When `content_hash` starts with `"<"` (i.e., is a sentinel — `"<oversize>"` or `"<refused>"`), the memo **does not parse or cache** — it returns `None`. A test calls `memo.get(p, content_hash="<refused>")` and asserts the return is `None` and `memo._cache` remains empty. Rationale: sentinel inputs are precisely the case where the parse will fail downstream; caching a `None` sentinel under a sentinel key would only serve confusion.

### Coordinator wiring (runtime ctx is `BudgetingContext`)

- [ ] **AC-16.** **Per-probe snapshot computation.** In `coordinator/coordinator.py:_dispatch_one`, before constructing `ctx` (line ~297), the coordinator calls `compute_input_snapshot(probe, per_probe_snap.root)` and binds the result to a local `snapshot: frozenset[InputFingerprint]`. The snapshot is computed **per-probe**, NOT once-per-gather. Test installs two stub probes with disjoint `declared_inputs` (one `["package.json"]`, one `["pnpm-lock.yaml"]`); after `gather()`, each probe's captured `ctx.input_snapshot` contains only its own declared inputs. Mutation that takes the union across all probes is caught.

- [ ] **AC-17.** **`_make_probe_context` signature extension.** `_make_probe_context(workspace, raw_artifact_mb, *, parsed_manifest=None, input_snapshot=None) -> BudgetingContext` gains two keyword-only parameters (defaulted to `None` to preserve all existing call sites). It constructs `BudgetingContext(workspace=workspace, raw_artifact_mb=raw_artifact_mb, parsed_manifest=parsed_manifest, input_snapshot=input_snapshot)`. A type-pin test asserts the signature via `inspect.signature(_make_probe_context).parameters`.

- [ ] **AC-18.** **`_dispatch_one` threads snapshot + adapter.** `_dispatch_one` builds the per-probe adapter via `adapter = make_parsed_manifest_adapter(snapshot, memo)` and passes both into `_make_probe_context(..., parsed_manifest=adapter, input_snapshot=snapshot)`. The single memo instance is the one already constructed at the top of `gather()` (S1-07 deliverable). Test installs a stub probe whose `run()` captures `ctx.input_snapshot` and `ctx.parsed_manifest`; after `gather()`:
  - `ctx.input_snapshot` is a `frozenset[InputFingerprint]` with the expected entries (non-empty when `declared_inputs` match files; `frozenset()` otherwise);
  - `ctx.parsed_manifest` is callable and `ctx.parsed_manifest(repo_root / "package.json")` returns the parsed `MappingProxyType`.

  Mutation that drops the wiring (snapshot computed but never assigned, OR adapter constructed but never threaded) is caught here, not only in isolated helper tests.

- [ ] **AC-19.** **TOCTOU closure across a concurrent edit.** Integration test simulates the Gap 1 scenario:
  1. Write `package.json` with content **A**; compute snapshot — captures `content_hash_A`.
  2. Call the adapter on the path → memo parses A, returns `pa`.
  3. **Overwrite the file with content B** (different bytes, different size) — no snapshot recomputation.
  4. Call the adapter on the path again → memo returns `pb`. Assert `pa is pb` (same `MappingProxyType` instance) because the adapter's `content_hash_A` lookup still hits the cached parse.
  5. Separately, calling `memo.get(p, content_hash=content_hash_B)` returns a **fresh** parse of B (`pb_fresh is not pa`).

  This is the actual Gap-1-closure assertion — the mtime-bump test in the original draft did not prove it. Mutation that ignores `content_hash` and falls through to the legacy stat-tuple key is caught (the mtime/size changes when bytes change, so the legacy key would miss and re-parse).

### Observability & determinism

- [ ] **AC-20.** **`probe.input_snapshot.computed` structured event.** The coordinator emits one event per probe dispatch with structured fields:
  - `probe: str` — the probe name
  - `entries: int` — `len(snapshot)`
  - `total_bytes: int` — sum of `fp.size` across entries whose `content_hash` is NOT a sentinel
  - `wall_clock_ms: int` — wall time for **this probe's** entire snapshot computation (not per-file)

  Test uses `structlog.testing.capture_logs()` (S1-02..S1-07 hardened precedent), dispatches a stub probe with two real files and one oversize file, and asserts the event dict shape exactly. The bench-canary (S6-02) reads `wall_clock_ms` to track snapshot cost separately from probe cost.

- [ ] **AC-21.** **Determinism property.** `compute_input_snapshot` is deterministic given identical on-disk bytes. Test calls the helper twice in succession against the same fixture and asserts `{(fp.path, fp.content_hash) for fp in snap_a} == {(fp.path, fp.content_hash) for fp in snap_b}` (mtime_ns may differ if a touch occurred; content_hash MUST not). Mutation that mixes `time.time_ns()` or `os.getpid()` into any field is caught. (This is the property test that the functional-core split — see Notes — would let us elevate to Hypothesis-driven property generation in a future story.)

### Doc & ADR amendments

- [ ] **AC-22.** **ADR-0002 amendment.** `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` is amended:
  - §"`ParsedManifestMemo` semantics" — the `Key:` bullet is rewritten to name the dual-shape key: legacy `(str(path.resolve()), mtime_ns, size)` for `content_hash=None`; `(content_hash,)` when the adapter passes a snapshot-derived hash.
  - §Consequences — the line "The Gap #1 improvement in `phase-arch-design.md` is documented as a future amendment to this ADR if Phase 14's concurrent-gather threat model demands it" is replaced with: "**Resolved in S1-08 (2026-05-14):** the Gap #1 improvement is landed via `compute_input_snapshot` + `make_parsed_manifest_adapter` in `coordinator/input_snapshot.py`. The memo's signature gained an additive `content_hash: str | None = None` parameter (departure from arch's prescribed full-flip, recorded per Rule 7)."
  - A `**Last amended:** 2026-05-14 (S1-08 — Gap 1 landed, additive key shape)` line is added under the title block.
  - A doc-grep test (`tests/unit/test_adr_0002_records_s1_08_amendment`) asserts the literal substrings `"content_hash"`, `"S1-08"`, and `"compute_input_snapshot"` appear in ADR-0002's body.

- [ ] **AC-23.** **`localv2.md §4` is unaffected.** The memo's signature change is internal coordinator detail — it is not part of §4's probe-contract surface (which declares `ProbeContext`, `RepoSnapshot`, `Task`, `ProbeOutput`, `Probe`). S1-06's §4 amendment already declared `parsed_manifest` and `input_snapshot` on `ProbeContext`. A grep test asserts §4's body is unchanged from its post-S1-06 state. (Surfaced as an explicit Out-of-scope confirmation.)

### Hygiene

- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.
- [ ] No `from blake3 import` or `import blake3` anywhere except `src/codegenie/hashing.py` (ADR-0001 chokepoint preserved); CI's `fence` job or an explicit grep test enforces.

## Implementation outline

1. Create `src/codegenie/coordinator/input_snapshot.py`:
   - Module docstring: cite Gap 1, ADR-0002 (amended), and the load-bearing role for Phase 14.
   - Module surface: `__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]`.
   - Module-level constants: `_DEFAULT_MAX_BYTES_PER_FILE: Final[int] = 52_428_800` (50 MiB); `_CONTENT_HASH_OVERSIZE: Final[str] = "<oversize>"`; `_CONTENT_HASH_REFUSED: Final[str] = "<refused>"`.
   - Private helper `_fingerprint_from_fd(fd, abs_path, *, max_bytes) -> InputFingerprint`:
     - `os.fstat(fd)` → `(st_mtime_ns, st_size)`
     - if `st_size > max_bytes` → return oversize-sentinel `InputFingerprint` (no read)
     - else `os.read(fd, st_size)` → `data`
     - `content_hash_bytes(data)` → `"blake3:<hex>"`
     - return `InputFingerprint(path=abs_path, mtime_ns=st_mtime_ns, size=st_size, content_hash=hash)`
   - `compute_input_snapshot(probe, repo_root, *, max_bytes_per_file=_DEFAULT_MAX_BYTES_PER_FILE) -> frozenset[InputFingerprint]`:
     - `t0 = time.perf_counter()`
     - For each `pattern in probe.declared_inputs`:
       - `for matched in Path(repo_root).glob(pattern):` (case-sensitive post-filter on macOS/Windows — see Notes)
         - `abs_path = str(matched.resolve())`
         - try `fd = os.open(matched, os.O_RDONLY | os.O_NOFOLLOW)`
         - except `OSError as exc`: if `exc.errno == errno.ELOOP`: → record `_CONTENT_HASH_REFUSED` sentinel using `os.lstat(matched)` for mtime/size; emit `probe.input_snapshot.symlink_refused` event (optional); continue
         - except `FileNotFoundError`: continue (glob race)
         - **let every other `OSError` propagate** (Rule 12)
         - else: `fp = _fingerprint_from_fd(fd, abs_path, max_bytes=max_bytes_per_file)`; if oversize sentinel, emit `probe.input_snapshot.oversize` event; `os.close(fd)`; add `fp` to a local `set`
     - `wall_clock_ms = int((time.perf_counter() - t0) * 1000)`
     - emit `probe.input_snapshot.computed` event with `(probe, entries, total_bytes, wall_clock_ms)`
     - return `frozenset(...)`
   - `make_parsed_manifest_adapter(snapshot, memo)`:
     - `by_path: dict[str, str] = {fp.path: fp.content_hash for fp in snapshot}`
     - return a closure `_get(path: Path) -> Mapping[str, Any] | None` that returns `memo.get(path, content_hash=by_path.get(str(path.resolve())))`

2. Extend `src/codegenie/coordinator/parsed_manifest_memo.py`:
   - `get(self, path: Path, *, content_hash: str | None = None) -> Mapping[str, Any] | None`:
     - if `content_hash is not None` and `content_hash.startswith("<")`: return `None` (sentinel bypass — AC-15).
     - if `content_hash is not None`: key = `(content_hash,)`; do lookup/parse/cache under this key.
     - else: key = `(str(path.resolve()), mtime_ns, size)` (S1-07 path); unchanged behavior.
   - The kernel surface `__all__ == ["ParsedManifestMemo"]` does not change.

3. Extend `src/codegenie/coordinator/coordinator.py`:
   - `_make_probe_context` gains keyword-only `parsed_manifest=None, input_snapshot=None` and threads them into `BudgetingContext(...)`.
   - `_dispatch_one`: after the cache lookup short-circuit (line ~292) and before constructing `ctx` (line ~297), compute `snapshot = compute_input_snapshot(probe, per_probe_snap.root)`; build `adapter = make_parsed_manifest_adapter(snapshot, memo)` (where `memo` is the existing per-gather instance threaded through from `gather()` — S1-07's deliverable); call `_make_probe_context(..., parsed_manifest=adapter, input_snapshot=snapshot)`.

4. Amend `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` per AC-22.

## TDD plan — red / green / refactor

### Red — failing tests first

Test file: `tests/unit/coordinator/test_input_snapshot.py` (new). Plus targeted additions to `tests/unit/coordinator/test_parsed_manifest_memo.py` (memo additive signature) and one integration test under `tests/unit/coordinator/test_coordinator_threads_input_snapshot.py`.

Each test below names its AC + the mutation it catches:

```python
# tests/unit/coordinator/test_input_snapshot.py
import errno
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from structlog.testing import capture_logs

from codegenie.coordinator.input_snapshot import (
    compute_input_snapshot,
    make_parsed_manifest_adapter,
)
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
from codegenie.probes.base import InputFingerprint


class _FakeProbe:
    name = "stub.snapshot"
    declared_inputs = ["package.json", "pnpm-lock.yaml"]


# T-1 — AC-2 (import path): InputFingerprint is from codegenie.probes.base
def test_input_fingerprint_imported_from_probes_base() -> None:
    assert InputFingerprint.__module__ == "codegenie.probes.base"
    # Catches a mutation that re-introduces coordinator/input_snapshot.py as the home for the newtype.


# T-2 — AC-3 + AC-5 + AC-6: snapshot type, contents, empty case
def test_snapshot_returns_frozenset_with_expected_paths(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    assert isinstance(snap, frozenset)
    for fp in snap:
        assert isinstance(fp, InputFingerprint)
    paths = {fp.path for fp in snap}
    assert str((tmp_path / "package.json").resolve()) in paths
    assert str((tmp_path / "pnpm-lock.yaml").resolve()) in paths
    # Mutation: returning list/tuple — caught by isinstance frozenset.


def test_empty_declared_inputs_yields_empty_frozenset(tmp_path: Path) -> None:
    class _Empty:
        name = "empty"; declared_inputs: list[str] = []
    assert compute_input_snapshot(_Empty(), tmp_path) == frozenset()
    class _Nomatch:
        name = "nomatch"; declared_inputs = ["nonexistent-*.json"]
    assert compute_input_snapshot(_Nomatch(), tmp_path) == frozenset()
    # Mutation: raise on empty / return None — caught.


# T-3 — AC-3: glob is case-sensitive even on case-insensitive FS
def test_glob_is_case_sensitive(tmp_path: Path) -> None:
    (tmp_path / "Package.json").write_text("{}")  # capital P
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    # _FakeProbe declares "package.json" (lowercase); Package.json must not match.
    assert not any(fp.path.endswith("Package.json") for fp in snap)
    # Mutation: case-insensitive match — caught.


# T-4 — AC-4 + AC-7 + AC-8: content_hash is "blake3:<hex>" via the chokepoint
def test_content_hash_is_blake3_prefixed(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash.startswith("blake3:")
    assert len(fp.content_hash) == len("blake3:") + 64  # blake3 hex digest
    # Mutation: hashlib.sha256, bare hexdigest, prefix-stripped — all caught.


def test_input_snapshot_module_does_not_import_blake3_directly() -> None:
    import codegenie.coordinator.input_snapshot as m
    src = Path(m.__file__).read_text()
    assert "import blake3" not in src
    assert "from blake3" not in src
    # ADR-0001 chokepoint — hashing.py is the single import site.


# T-5 — AC-9: oversize files record "<oversize>" sentinel and emit warning event
def test_oversize_file_records_sentinel(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_bytes(b"x" * 2048)
    with capture_logs() as logs:
        snap = compute_input_snapshot(_FakeProbe(), tmp_path, max_bytes_per_file=1024)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash == "<oversize>"
    oversize_events = [r for r in logs if r["event"] == "probe.input_snapshot.oversize"]
    assert len(oversize_events) == 1
    assert oversize_events[0]["size_bytes"] == 2048
    assert oversize_events[0]["cap_bytes"] == 1024
    # Mutation: silent truncation + partial hash — caught.


# T-6 — AC-10: symlinked declared input → "<refused>"; retry semantics
def test_symlink_input_records_refused_then_retries(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text(json.dumps({"name": "x"}))
    link = tmp_path / "package.json"
    link.symlink_to(target)
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert fp.content_hash == "<refused>"
    # Retry: delete symlink, create real file at same path
    link.unlink()
    link.write_text(json.dumps({"name": "x"}))
    snap2 = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp2 = next(fp for fp in snap2 if fp.path.endswith("package.json"))
    assert fp2.content_hash.startswith("blake3:")
    # Mutation: path.read_bytes() (follows symlinks) — caught.


# T-7 — AC-11: Rule 12 — unexpected OSError propagates; only ELOOP + FileNotFoundError swallowed
@pytest.mark.parametrize(
    "exc,must_propagate",
    [
        (OSError(errno.ELOOP, "loop"), False),
        (FileNotFoundError(2, "missing"), False),
        (PermissionError(13, "denied"), True),
        (IsADirectoryError(21, "is dir"), True),
        (OSError(errno.EIO, "io"), True),
    ],
    ids=["ELOOP", "FileNotFoundError", "PermissionError", "IsADirectoryError", "EIO"],
)
def test_oserror_handling_per_rule_12(tmp_path: Path, monkeypatch, exc, must_propagate) -> None:
    (tmp_path / "package.json").write_text("{}")
    real_open = os.open
    def _maybe_raise(path, flags, *args, **kwargs):
        if str(path).endswith("package.json"):
            raise exc
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", _maybe_raise)
    if must_propagate:
        with pytest.raises(type(exc)):
            compute_input_snapshot(_FakeProbe(), tmp_path)
    else:
        compute_input_snapshot(_FakeProbe(), tmp_path)  # must not raise
    # Mutation: blanket `except OSError: continue` — caught by PermissionError/IsADirectoryError/EIO cases.


# T-8 — AC-12: path canonicalization is str(matched_path.resolve())
def test_input_fingerprint_path_is_resolved_string(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{}")
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    fp = next(fp for fp in snap if fp.path.endswith("package.json"))
    assert Path(fp.path).is_absolute()
    assert fp.path == str(p.resolve())
    # Mutation: .as_posix() (Windows divergence) or str(matched_path) (non-canonical) — caught.


# T-9 — AC-20: probe.input_snapshot.computed event shape
def test_emits_computed_event_with_structured_fields(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    with capture_logs() as logs:
        snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    evt = next(r for r in logs if r["event"] == "probe.input_snapshot.computed")
    assert evt["probe"] == "stub.snapshot"
    assert evt["entries"] == 2
    assert evt["total_bytes"] > 0
    assert isinstance(evt["wall_clock_ms"], int) and evt["wall_clock_ms"] >= 0


# T-10 — AC-21: determinism property
def test_snapshot_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    snap_a = compute_input_snapshot(_FakeProbe(), tmp_path)
    snap_b = compute_input_snapshot(_FakeProbe(), tmp_path)
    by_path_a = {fp.path: fp.content_hash for fp in snap_a}
    by_path_b = {fp.path: fp.content_hash for fp in snap_b}
    assert by_path_a == by_path_b
    # Mutation: time.time_ns() or os.getpid() mixed into the hash — caught.


# T-11 — AC-13: make_parsed_manifest_adapter — present + missing path
def test_adapter_resolves_present_and_missing_paths(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x"}))
    snap = compute_input_snapshot(_FakeProbe(), tmp_path)
    memo = ParsedManifestMemo()
    adapter = make_parsed_manifest_adapter(snap, memo)
    # Present in snapshot → content_hash-keyed lookup
    parsed = adapter(p)
    assert parsed is not None and parsed["name"] == "x"
    # Missing from snapshot → content_hash=None fallback to S1-07 stat-tuple key (still parses)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"name": "y"}))
    parsed_other = adapter(other)
    assert parsed_other is None or parsed_other["name"] == "y"
    # The exact behavior for "missing from snapshot but allowlisted by memo" depends on the memo's allowlist;
    # both `None` (path not in memo allowlist) and the parsed dict (allowlisted, stat-key path) are valid per AC-14.


# T-12 — AC-14: memo dual-key shapes coexist; identity preserved per key
def test_memo_dual_keys_coexist(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x"}))
    memo = ParsedManifestMemo()
    a = memo.get(p, content_hash="blake3:abc")
    b = memo.get(p)  # content_hash=None — legacy stat-tuple key
    # Both parse the file (allowlisted); they're stored under different keys.
    assert a is not None
    assert b is not None
    assert len(memo._cache) == 2
    # Identity under same key
    a2 = memo.get(p, content_hash="blake3:abc")
    b2 = memo.get(p)
    assert a is a2
    assert b is b2


# T-13 — AC-15: sentinel content_hash bypasses the memo (returns None, no cache entry)
def test_memo_sentinel_content_hash_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{}")
    memo = ParsedManifestMemo()
    assert memo.get(p, content_hash="<refused>") is None
    assert memo.get(p, content_hash="<oversize>") is None
    assert len(memo._cache) == 0
```

```python
# tests/unit/coordinator/test_coordinator_threads_input_snapshot.py
import json
from pathlib import Path
from typing import Any

import pytest


# T-14 — AC-16 + AC-17 + AC-18: gather() threads snapshot + adapter onto runtime ctx
@pytest.mark.asyncio
async def test_gather_threads_input_snapshot_and_adapter_to_ctx(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    captured: dict[str, Any] = {}

    # Build a stub probe (see existing test patterns in tests/unit/coordinator/ for the helper)
    # whose run() captures ctx.input_snapshot and ctx.parsed_manifest.

    # ... gather() invocation ...

    snap = captured["input_snapshot"]
    adapter = captured["parsed_manifest"]
    assert isinstance(snap, frozenset)
    assert any(fp.path.endswith("package.json") for fp in snap)
    assert callable(adapter)
    parsed = adapter(tmp_path / "package.json")
    assert parsed is not None and parsed["name"] == "x"
    # Mutation: snapshot computed but never wired — caught (snap would be None).


# T-15 — AC-16: per-probe snapshot independence
@pytest.mark.asyncio
async def test_two_probes_in_one_gather_see_independent_snapshots(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    # Two stub probes with disjoint declared_inputs; capture each ctx.input_snapshot.
    # Assert probe_a.snap contains package.json but NOT pnpm-lock.yaml; probe_b.snap is the inverse.


# T-16 — AC-19: Gap-1 closure — mid-gather byte change does NOT invalidate the snapshotted parse
def test_snapshot_pins_parse_against_concurrent_byte_change(tmp_path: Path) -> None:
    from codegenie.coordinator.input_snapshot import (
        compute_input_snapshot, make_parsed_manifest_adapter,
    )
    from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo

    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "A"}))
    memo = ParsedManifestMemo()
    class _StubProbe:
        name = "stub"; declared_inputs = ["package.json"]
    snap_A = compute_input_snapshot(_StubProbe(), tmp_path)
    adapter_A = make_parsed_manifest_adapter(snap_A, memo)
    parsed_A = adapter_A(p)
    assert parsed_A is not None and parsed_A["name"] == "A"

    # Overwrite bytes; do NOT recompute snapshot
    p.write_text(json.dumps({"name": "BBBBBBBB"}))  # different bytes, different size

    parsed_A_again = adapter_A(p)
    assert parsed_A_again is parsed_A  # IDENTITY — the snapshot pinned the parse

    # Separately: a fresh snapshot + adapter sees the new bytes
    snap_B = compute_input_snapshot(_StubProbe(), tmp_path)
    adapter_B = make_parsed_manifest_adapter(snap_B, memo)
    parsed_B = adapter_B(p)
    assert parsed_B is not None and parsed_B["name"] == "BBBBBBBB"
    assert parsed_B is not parsed_A  # different content_hash → different cache key
```

Plus one doc-grep test:

```python
# tests/unit/test_adr_0002_records_s1_08_amendment.py
from pathlib import Path

def test_adr_0002_records_s1_08_landing() -> None:
    body = Path("docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md").read_text()
    assert "content_hash" in body
    assert "S1-08" in body
    assert "compute_input_snapshot" in body
```

Run; confirm failures (module + helpers + memo kwarg + adapter + coordinator wiring all absent). Commit as red.

### Green — minimal impl

Implement per the Implementation outline. The pure `_fingerprint_from_fd` helper + the impure `compute_input_snapshot` shell + the adapter live in `coordinator/input_snapshot.py`. The memo's `get` gains the additive `content_hash` kwarg with sentinel-bypass. The coordinator's `_make_probe_context` + `_dispatch_one` gain the wiring. ADR-0002 is amended.

### Refactor — clean up

- Module docstring on `coordinator/input_snapshot.py`: name Gap 1, ADR-0002 (amended), and the load-bearing role for Phase 14.
- Inline a one-line comment on `_DEFAULT_MAX_BYTES_PER_FILE` pointing at `phase-arch-design.md §"Component design" #3` so future tuning is grep-discoverable.
- `compute_input_snapshot` keeps the snapshot logic in one function — easier to swap to a parallelized version in Phase 14 by writing a sibling `compute_input_snapshot_parallel` rather than editing this one.
- `wall_clock_ms` field on the event is the entire snapshot computation for the probe — not per-file. The bench-canary (S6-02) reads this.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/input_snapshot.py` | **New** — `compute_input_snapshot`, `make_parsed_manifest_adapter`, private helpers, sentinel constants. `__all__ = ["compute_input_snapshot", "make_parsed_manifest_adapter"]`. |
| `src/codegenie/coordinator/parsed_manifest_memo.py` | Add `content_hash: str \| None = None` kwarg to `get`; sentinel bypass; legacy fallback path unchanged. |
| `src/codegenie/coordinator/coordinator.py` | Extend `_make_probe_context` with `parsed_manifest`/`input_snapshot` kwargs; wire `_dispatch_one` to compute snapshot per probe, build adapter, thread both through. |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` | Amend §"`ParsedManifestMemo` semantics" + §Consequences + add `**Last amended:** 2026-05-14 (S1-08)` line. |
| `tests/unit/coordinator/test_input_snapshot.py` | **New** — 13 tests (T-1..T-13). |
| `tests/unit/coordinator/test_parsed_manifest_memo.py` | Add T-12 + T-13 to existing file (don't remove the S1-07 tests; they continue to pin the legacy key path). |
| `tests/unit/coordinator/test_coordinator_threads_input_snapshot.py` | **New** — 3 integration tests (T-14, T-15, T-16) — the most load-bearing. |
| `tests/unit/test_adr_0002_records_s1_08_amendment.py` | **New** — doc-grep test for the ADR amendment. |

## Out of scope

- **Per-probe raw-artifact budget** — S1-09 (sibling story).
- **Cache-key derivation in `CacheStore.put` using `input_snapshot`** — Phase 0's `CacheStore` already derives keys from `declared_inputs` content hashes (S3-01). This story does not edit `CacheStore`; the `input_snapshot` is what flows into the same hashing function the coordinator already uses pre-dispatch. If those hashes aren't already content-based, mark a follow-up in the PR.
- **Parallelizing snapshot computation** — Phase 14 may parallelize per-probe snapshot computation across worker threads. Phase 1's sequential pre-dispatch pass is correct and cheap (≤ 50 ms p50 on the 1k-file fixture).
- **Concurrent re-snapshotting on long-running gathers** — Phase 14 owns it.
- **`localv2.md §4` amendment** — not required. The memo's signature change is internal coordinator detail; §4's probe-contract surface (declaring `ProbeContext`, `RepoSnapshot`, `Task`, `ProbeOutput`, `Probe`) is unaffected. S1-06 already declared `parsed_manifest`/`input_snapshot` on `ProbeContext` in §4.
- **Collapsing the `ProbeContext` vs. `BudgetingContext` duality.** Pre-existing smell tracked for a future ADR (likely lands when Phase 14 introduces Activity-scoped ctx). S1-08 mirrors fields onto `BudgetingContext` (the path S1-07 set) and does NOT attempt the unification.
- **Smart constructor on `InputFingerprint` itself** (e.g., `@classmethod from_fd(...)`). `probes/base.py` is stdlib-only per ADR-0007; importing `os`/`codegenie.hashing` into it would break the frozen contract surface. Smart-construction discipline lives in the snapshot module's private `_fingerprint_from_fd` helper instead.

## Notes for the implementer

- **Runtime ctx is `BudgetingContext`.** S1-06 added `input_snapshot` to the `ProbeContext` contract type (frozen, stdlib-only); S1-07 mirrored it onto `BudgetingContext` (the actual runtime ctx threaded through `_make_probe_context → _dispatch_one → probe.run`). When you wire S1-08, you're assigning onto the runtime instance — the `BudgetingContext`. The `ProbeContext` extension exists for type-checker satisfaction; the runtime hop is `Any`-typed at `_run_probe_with_isolation`. This duality is a pre-existing smell tracked for a future ADR.

- **ADR-0001 chokepoint.** Use `codegenie.hashing.content_hash_bytes(data)` for the hash. The returned form is `"blake3:<hex>"` — the prefix is part of the contract. Do NOT call `codegenie.hashing.content_hash(path)`: it opens the path directly (no `O_NOFOLLOW`), silently following symlinks. Do NOT `from blake3 import blake3` — there's exactly one allowed import site (`hashing.py`).

- **`os.fstat` vs `path.stat()`.** Source `mtime_ns` and `size` from `os.fstat(fd)` (same fd you read from) — guarantees consistency. The only legitimate use of `os.lstat(path)` in this module is the symlink-refused branch, where the fd was never opened.

- **`Path.glob` case-sensitivity.** Python 3.12+ supports `pathlib.PurePath.match(..., case_sensitive=True)` and `Path.glob(..., case_sensitive=True)`. On Python 3.11, post-filter with `if matched.name in declared_inputs_lowered: continue if matched.name != matched.name.lower() else proceed` — or use `glob.glob(..., case_sensitive=True)` if the project's Python version supports it. Match S1-07's allowlist case-sensitivity discipline.

- **Functional core / imperative shell.** The pure `_fingerprint_from_bytes(abs_path, mtime_ns, size, data)` shape (returns `InputFingerprint` deterministically from inputs only) is colocated as a helper inside `_fingerprint_from_fd`. The impure shell does I/O. The split is what lets T-10 (determinism) be a simple equality test rather than a property-based test with FS mocking. **Future move:** when Phase 14's parallel snapshot lands, the pure half is reusable; surface this opportunity in the Phase 14 PR description.

- **Sentinel strings as constants.** `_CONTENT_HASH_OVERSIZE = "<oversize>"` and `_CONTENT_HASH_REFUSED = "<refused>"` live at module scope as `Final[str]`. Downstream consumers (the memo's sentinel-bypass branch, future cache-key derivation in Phase 14) branch on the `"<"` prefix rather than importing the names — preserves the string-protocol contract.

- **Adapter helper is the seam for Phase 14.** `make_parsed_manifest_adapter(snapshot, memo)` is the named seam that Phase 14's parallel snapshot will replace with a thread-safe variant. Keep it small and well-tested (T-11). The current implementation precomputes `by_path: dict[str, str]` once — O(1) per `get` call rather than O(n) scan.

- **Path canonicalization protocol.** This is the single most subtle correctness defect: `fp.path` and the adapter's lookup key MUST agree on shape. Both use `str(matched_path.resolve())`. The `.resolve()` call canonicalizes symlinks AND normalizes path separators; using `.as_posix()` (forward slashes on Windows) or `str(matched_path)` (relative + non-canonical) silently misses lookups → re-opens the TOCTOU window the story is supposed to close. T-8 and T-11 pin both halves of the roundtrip.

- **Rule 7 — surface conflicts, don't average them.** The arch-doc Gap 1 (line 990) prescribes a full key flip; S1-08 ships the additive variant. The departure is recorded in AC-22's ADR-0002 amendment and in this story's Validation notes. If a future reviewer reads only the arch doc, the ADR amendment is where they'll find the rationale.

- **Future move (rule-of-three threshold not yet met).** Three patterns are recorded for future surfacing:
  1. **`type InputSnapshot = frozenset[InputFingerprint]` alias** in `probes/base.py` — three use sites now (`ProbeContext.input_snapshot`, `BudgetingContext.input_snapshot`, `compute_input_snapshot` return type). Deferred because introducing the alias re-edits the frozen probe-contract surface (ADR-0007) and would regen the contract snapshot. Phase 2's `IndexHealthProbe` (the fourth consumer) is the right ADR moment.
  2. **`FileEnumerator` Strategy interface** — `Path.glob` is one of three plausible enumeration strategies (`git ls-files`, `os.walk`, `Path.glob`). Phase 14 may swap; defer extraction until then.
  3. **`make_parsed_manifest_adapter` as a Hexagonal Port** — today the snapshot module owns both the port and the adapter; Phase 14's parallel snapshot will likely want a port/adapter split (the coordinator depends on the port; the adapter is the file-system implementation; Phase 14 ships a `git`-aware adapter). Defer.
