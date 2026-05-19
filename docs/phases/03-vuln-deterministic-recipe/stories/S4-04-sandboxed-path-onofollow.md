# Story S4-04 — `SandboxedPath.create` (Result) + `open()` always `O_NOFOLLOW` + TOCTOU defense

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** HARDENED
**Effort:** S → S/M (hardening added `_forward.py` substitution + fence amendment + Pydantic-consumer compat — still small, but the seam-wiring scope grew)
**Depends on:** S4-01 (`JailedSubprocessSpec.cwd: SandboxedPath` is consumed here; the Port commits to this typename); the Phase-3-Step-1 `_forward.py` shim (S1-04 AC-5/AC-5b) — this story flips its `SandboxedPath: TypeAlias = pathlib.Path` to a re-export of `codegenie.plugins.sandbox_path.SandboxedPath`.
**ADRs honored:** 03-ADR-0011 (honest framing — `SandboxedPath` is "in-jail at construction, second-line defense at `open()` via `O_NOFOLLOW`"; NOT "in-jail forever"; NOT "makes illegal states unrepresentable"; NOT "unforgeable"; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`); 03-ADR-0010 (Pydantic frozen + `extra="forbid"` for value types + closed `Literal` sum on `PathEscape.reason`); 03-ADR-0001 (one-way `transforms → transforms._forward` direction is amended by this story to admit one re-export from `codegenie.plugins.sandbox_path`).

## Validation notes (2026-05-19, phase-story-validator)

This story was hardened from `Ready` → `HARDENED` after four critics surfaced 13 BLOCK-grade structural issues plus ~24 HARDEN-grade mutation-survival gaps. The hardening keeps the Goal and scope intact; it tightens ACs so the executor's validator pass can actually fail on a wrong implementation, and it pulls in the load-bearing seam-wiring (`_forward.py` substitution + fence allowlist) that the story originally left implicit.

**BLOCK-grade conflicts resolved:**

1. **Wrong `Result` import path.** Original outline said `from codegenie.types.result.{Result, Ok, Err}`. Codebase ships at `codegenie.result` (19 importers; zero use `codegenie/types/result`). Rule 11 wins — Implementation outline rewritten to pin `from codegenie.result import Err, Ok, Result` with API `.is_ok()`, `.is_err()`, `.unwrap()`, `.unwrap_err()`. The "verify via grep" hedging in step 1 dropped — point at `src/codegenie/result.py` directly (Rule 8).
2. **`_forward.py` substitution missing.** `src/codegenie/transforms/_forward.py` line 39 currently aliases `SandboxedPath: TypeAlias = pathlib.Path`; its docstring at lines 12–14 explicitly declares S4-04's contract: "Replace the SandboxedPath TypeAlias with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath`." Without this flip, this story ships dead code — `Transform.files_changed: tuple[SandboxedPath, ...]` and `ApplyContext.evidence_paths: tuple[SandboxedPath, ...]` still bind to `pathlib.Path`. AC-Sub-1 + Files-to-touch entry added.
3. **Fence allowlist amendment missing.** `tests/fence/test_transforms_module_purity.py:29` defines `_FORWARD_ALLOWED = frozenset({"__future__", "pathlib", "typing", "pydantic"})` and asserts `_forward.py` reaches no other modules. The substitution adds `codegenie.plugins.sandbox_path` — fence breaks unless extended. AC-Sub-2 added; ADR-0001 amendment note in attempt log.
4. **Pydantic shape unspecified.** Original outline allowed `dataclass(frozen=True)` OR `BaseModel`. The two choices ripple differently to existing consumers (`Transform`, `ApplyContext` are Pydantic `BaseModel`). Pinned to `BaseModel(frozen=True, extra="forbid", arbitrary_types_allowed=True)` — matches `Ok`/`Err`/`PathEscape` precedent. AC-2 / AC-6 / AC-Sub-3 updated.
5. **AC-3 unverified `attempted_path` payload.** Original assertion only checked `reason`; a mutant emitting wrong path strings passed. AC-3 now asserts `Path(err.attempted_path).resolve() == outside.resolve()` and `Path(err.jail).resolve() == jail.resolve()`.
6. **AC-5 disjunction `reason in {missing, not_resolvable}` was mutation-trivial.** Split into two ACs: broken-symlink → `reason == "not_resolvable"` exactly; missing-leaf → `reason == "missing"` exactly. A mutant collapsing the two branches in the smart constructor no longer survives.
7. **AC-6 `pytest.raises((AttributeError, Exception))` was a catch-all.** Tightened to `pytest.raises(ValidationError)` (Pydantic frozen). Frozen-discipline and extra-forbid split into two ACs (AC-6a / AC-6b) per TQ-06 conflation hazard.
8. **AC-7 only asserted `O_NOFOLLOW` bit.** A mutant ORing `O_RDWR` into every read-mode open silently passed. AC-7 rewritten to assert exact base-flag mask per mode (`O_RDONLY` / `O_WRONLY|O_CREAT|O_TRUNC` / `O_WRONLY|O_CREAT|O_APPEND` / `O_RDWR` / `O_WRONLY|O_CREAT|O_EXCL`) plus `O_NOFOLLOW` plus `O_CLOEXEC`. Mode set extended to include `x` / `xb`.
9. **AC-2 happy-path was macOS-tmp-symlink-fragile.** A new AC-2b adds a `jail-is-a-symlink` case to catch implementations that resolve only one of {jail, candidate}.
10. **AC-15 docstring substring check was one-sided.** Negative-substring assertions added: docstring must NOT contain `"in-jail forever"`, `"unforgeable"`, `"makes illegal states unrepresentable"`, `"unrepresentable"`, `"signature"` (case-insensitive). The discipline ADR-0011 §Consequences mandates is dual (use the right framing AND avoid the wrong one) — now enforced.
11. **AC-11 round-trip was empty pre-flip.** With AC-Sub-1, `JailedSubprocessSpec.cwd: SandboxedPath` resolves to the new class; AC-11 now asserts `isinstance(spec.cwd, BaseModel)` and `not isinstance(spec.cwd, pathlib.Path)`. Without AC-Sub-1, AC-11 silently passed because both sides were `Path`.

**HARDEN-grade additions** (extension by addition; no scope creep beyond the goal):

- `_MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC` module-level constant — single source of truth for mandatory flags; `O_CLOEXEC` prevents fd inheritance into subprocesses (S4-01 BwrapAdapter / SandboxExecAdapter), closing a Phase-3-relevant fd-leak vector at one place. AC-7a/AC-7b pin both flags.
- `_flags_for_mode(mode)` extracted as a module-private pure helper, tested independently with hypothesis (Phase 1 / Phase 2 precedent — see `tests/unit/probes/...` hypothesis usage). Unknown mode raises `ValueError` (Rule 12 fail-loud); AC-7c.
- fd-leak safety AC: if `os.fdopen` raises after `os.open` succeeds, the fd is closed before the exception propagates. AC-fd-leak.
- Typed-error fence: `SandboxedPath.open()` does not catch any exception; AST-scan asserts no `try` / `except` inside the method body. AC-fail-loud.
- Module-purity fence at `tests/fence/test_plugins_sandbox_path_purity.py` pinning `sandbox_path.py`'s import allowlist = `{__future__, errno, fcntl, os, pathlib, typing, pydantic, codegenie.result}`. AC-purity-fence.
- Edge-case ACs for `relative` shape: absolute path → `Err(absolute)`; `""` and `"."` → `Ok(jail)`. AC-relative-shape.
- Hardlink + special-file (FIFO / socket / device) limitations enumerated in module docstring AND tested (an attacker replacing the final component with a FIFO is NOT blocked by `O_NOFOLLOW`). AC-10 extended.
- AC-1 surface lock now pins `__all__ == ["PathEscape", "SandboxedPath"]` exactly (alphabetized list per `result.py` precedent + meta-test).
- AC-15 docstring framing enforced via positive + negative substring assertions (per ADR-0011 §Consequences dual discipline).
- AC-sum-type-coverage: introspects `typing.get_args(PathEscape.model_fields['reason'].annotation)` and asserts every literal value has at least one test producing a `PathEscape` carrying it (ADR-0010 sum-type-coverage pattern).

**Deferred (with tracking notes, mirroring AC-16 handling):**

- **Capability-construction lint rule** (DP-07): a custom ruff rule banning `SandboxedPath(...)` construction outside `sandbox_path.py` + `tests/`. Per ADR-0011 §Consequences, this is the "audit + lint" enforcement (no runtime impossibility). Deferred to S4-05 (Capability Fence story); story now records the tracking item explicitly.
- **`_check_under_jail` pure-helper extraction** (DP-09 / C-8 conflict-resolution): single call site today; Rule 2 (Simplicity First) wins. Notes-for-implementer captures the trigger condition for future extraction.
- **Property-based test for `is_relative_to(jail)` over synthetic Path strings** (TQ-08 NEEDS RESEARCH resolution): codebase has hypothesis precedent (Phase 1 ADR-0002 parser tests). Story adds a hypothesis test for `_flags_for_mode` (pure function) but defers fuzzing the smart-constructor itself — it's I/O-bound and the curated edge-case ACs already cover the symbolic cases.

**No re-run of `phase-story-writer` needed.** Every BLOCK was patchable inline. Verdict: HARDENED. Full critic reports + edit log in `_validation/S4-04-sandboxed-path-onofollow.md`.

## Context

`SandboxedPath` is one of three primitives ADR-0011 ships with explicit, downgraded framing. The security-lens design (`design-security.md`) overclaimed it as "in-jail forever" / "makes illegal states unrepresentable"; the critic correctly attacked this (`critique.md §Attacks on the security-first design — sandbox-path overclaim`):

> `Path.resolve(strict=True)` resolves symlinks at constructor time, but a symlink swap between `create()` and `open()` re-introduces the TOCTOU. The path is in-jail *at construction*, not forever.

The architecture's response (`phase-arch-design.md §Component design C10` + ADR-0011 §Decision §SandboxedPath) is **honest framing**: ship the primitive, document what it actually delivers, and add a meaningful second-line defense at the only place it can be added — `open()`-time `O_NOFOLLOW`. A symlink swap between `create()` and `open()` raises `OSError(errno=ELOOP)`, which consumers catch and translate into a typed `FilesystemRaceDetected` workflow-internal event (S6-01 lands the event taxonomy; this story emits the right exception that triggers it).

This story is **small** (S effort) and **focused**: ship `SandboxedPath` with the documented contract, ship the TOCTOU regression test that proves the second-line defense actually fires, and stop. The cost-to-build is dwarfed by the audit-trail value — every consumer (S5-02's `NpmLockfileRecipeEngine` writing the new `package.json`; S4-02 / S4-03 jail-cwd binds; S6-04's `LocalGitOps`) gets the same path-type and the same fail-loud behavior.

Critically, the file path per ADR-0011 §Consequences is `src/codegenie/plugins/sandbox_path.py` — under `plugins/`, NOT `transforms/`. The High-level-impl bullet says `src/codegenie/transforms/sandbox_path.py`; per Rule 7 (Surface conflicts, don't average), the ADR is the more recent / load-bearing decision and wins. See Notes for implementer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C10` — `SandboxedPath` bullet: `create(jail, relative) -> Result[SandboxedPath, PathEscape]`; `.open(mode)` always `O_NOFOLLOW`; "in-jail at construction, second-line defense at `open()`-time `O_NOFOLLOW`"; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`.
  - `../phase-arch-design.md §Edge case E12` — Symlink TOCTOU detection at `open()`-time; `RemediationOutcome.Failed(filesystem_race)`; exit 4.
  - `../phase-arch-design.md §Control flow` — "Symlink TOCTOU detected at `open()` → `OSError(ELOOP)` caught → `FilesystemRaceDetected` event → `RemediationOutcome.Failed(filesystem_race)` → exit 4."
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — row "`SandboxedPath` is 'in-jail at construction,' not 'in-jail forever'" — honest framing accepted; every consumer must handle `ELOOP`.
  - `../phase-arch-design.md §Testing strategy` — bullet `tests/unit/plugins/test_sandbox_path.py` — TOCTOU symlink swap raises `ELOOP` at `open()`; `is_relative_to(jail)` enforcement.
- **Phase ADRs:**
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — §Decision §SandboxedPath block pins the `Result`-returning constructor and the `O_NOFOLLOW`-always `open()`; §Consequences pins the file location `src/codegenie/plugins/sandbox_path.py` and the test `tests/unit/plugins/test_sandbox_path.py` exercising "the TOCTOU swap via deliberate fixture."
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — consumer of `SandboxedPath` at `JailedSubprocessSpec.cwd`; the Port commits to the typename.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "SandboxedPath framing"` (score 15/15) — honest-framing synthesis behind ADR-0011.
  - `../High-level-impl.md §Step 4 features delivered` — lists `src/codegenie/transforms/sandbox_path.py`. **This conflicts with ADR-0011's `src/codegenie/plugins/sandbox_path.py`.** ADR wins (Rule 7). See Notes.
- **Existing code:**
  - `src/codegenie/types/result.py` (or wherever the `Result[T, E]` type lives — verify via `grep -r "class Result" src/codegenie/` before starting). Phase 1 / Phase 2 already ship smart-constructor `Result`-returning functions; mirror the precedent.
  - `src/codegenie/types/identifiers.py` — newtype precedent (S1-01).
  - `src/codegenie/transforms/sandbox_jail.py` (S4-01) — the consumer. `JailedSubprocessSpec.cwd: SandboxedPath` is the load-bearing type binding.
- **External:**
  - Python stdlib `os.open(path, flags, ...)` with `os.O_NOFOLLOW` flag — raises `OSError` with `errno=errno.ELOOP` when the final component is a symlink. This is the kernel-level second-line defense.

## Goal

Ship the `SandboxedPath` primitive with ADR-0011's honest framing — **"in-jail at construction, second-line defense at `open()`-time `O_NOFOLLOW`"** (NOT "in-jail forever"; NOT "makes illegal states unrepresentable"; NOT "unforgeable"). Wire it into the existing `transforms._forward.SandboxedPath` seam so every consumer (`Transform.files_changed`, `ApplyContext.evidence_paths`, S4-01's `JailedSubprocessSpec.cwd`, S5-02's recipe engine, S6-04's local-git ops) receives the real type without changing their import paths.

Concretely land:

1. `class SandboxedPath(BaseModel)` — frozen Pydantic value type (`model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`) wrapping a resolved absolute `Path` in a private `_absolute: Path` field.
2. `SandboxedPath.create(jail: Path, relative: str | Path) -> Result[SandboxedPath, PathEscape]` — smart-constructor that:
   - rejects absolute `relative` strings with `Err(reason="absolute")`;
   - resolves `jail.resolve(strict=True)`, then `(jail_abs / relative).resolve(strict=True)`;
   - checks `resolved.is_relative_to(jail_abs)` (with both resolved), returning `Err(reason="not_under_jail")` on escape;
   - translates `FileNotFoundError` → `Err(reason="missing")` and other `OSError` (e.g., broken-symlink chains) → `Err(reason="not_resolvable")` with the two branches strictly disjoint.
3. `SandboxedPath.absolute: Path` — read-only property returning the resolved absolute `Path`.
4. `SandboxedPath.open(mode: str) -> IO[Any]` — **always** ORs `_MANDATORY_FLAGS` (= `os.O_NOFOLLOW | os.O_CLOEXEC`) into the os-flags computed from `mode`. `os.fdopen(fd, mode)` is wrapped so that an exception from `fdopen` closes `fd` before propagating. The method itself catches NO exceptions — `OSError(errno=ELOOP)` from a TOCTOU symlink swap propagates loud to the consumer.
5. `PathEscape(BaseModel)` Pydantic error variant: `model_config = ConfigDict(frozen=True, extra="forbid")`; fields `kind: Literal["path_escape"] = "path_escape"`, `attempted_path: str`, `jail: str`, `reason: Literal["not_under_jail", "not_resolvable", "missing", "absolute", "invalid_jail"]`.
6. **Substitute `_forward.py`:** replace `SandboxedPath: TypeAlias = pathlib.Path` with `from codegenie.plugins.sandbox_path import SandboxedPath` (re-export); amend `tests/fence/test_transforms_module_purity.py::_FORWARD_ALLOWED` to admit `codegenie.plugins.sandbox_path`.
7. **Two test files:** `tests/unit/plugins/test_sandbox_path.py` covers AC-1..AC-relative-shape (smart-constructor, frozen, `O_NOFOLLOW`, **TOCTOU swap**, hardlink/special-file limitations, `_flags_for_mode` pure helper); `tests/fence/test_plugins_sandbox_path_purity.py` pins the import allowlist.

`mypy --strict` clean. `ruff check` + `ruff format --check` clean. All existing fences green (transforms module-purity test passes after the allowlist amendment).

## Acceptance criteria

### Module surface

- [ ] **AC-1. Surface lock.** `codegenie.plugins.sandbox_path.__all__ == ["PathEscape", "SandboxedPath"]` (exact list, alphabetized — mirrors `src/codegenie/result.py:34` `__all__ = ["Err", "Ok", "Result"]` precedent). A meta-test iterates `vars(mod)` and asserts every non-underscore-prefixed top-level name is in `__all__` (no leaked public helpers; `_flags_for_mode`, `_MANDATORY_FLAGS`, etc. are underscore-prefixed). Test also asserts `from codegenie.result import Err, Ok, Result` is the resolution chain (proves the implementer used the canonical Result module, not a forked `codegenie.types.result`).

### Smart-constructor — happy paths

- [ ] **AC-2. Happy path (canonical-tmp).** `SandboxedPath.create(tmp_path, "file.txt")` where `(tmp_path / "file.txt").write_text("hi")`. Returns `Ok(SandboxedPath)`. `sp.absolute == (tmp_path / "file.txt").resolve()` AND `isinstance(sp, BaseModel)` AND `not isinstance(sp, pathlib.Path)`.
- [ ] **AC-2b. Happy path with a symlinked jail (metamorphic — catches half-resolved impls).** Setup: `real_jail = tmp_path / "real"` (mkdir), `alias_jail = tmp_path / "alias"` (`os.symlink(real_jail, alias_jail)`), `(real_jail / "f.txt").write_text("ok")`. `SandboxedPath.create(alias_jail, "f.txt")` returns `Ok(SandboxedPath)` whose `.absolute` equals `(real_jail / "f.txt")` (i.e., the fully-canonical path under `real_jail`, not under `alias_jail`). This proves both `jail` and `(jail/relative)` are independently `resolve(strict=True)`'d before the `is_relative_to` check. Also defends against the macOS `/var → /private/var` symlink hazard for `tmp_path`.
- [ ] **AC-relative-shape. Relative-arg edge cases.** Parametrized:
  - `create(jail, "")` → `Ok(SandboxedPath)` with `.absolute == jail.resolve(strict=True)`.
  - `create(jail, ".")` → `Ok(SandboxedPath)` with `.absolute == jail.resolve(strict=True)`.
  - `create(jail, "/etc/passwd")` (absolute path) → `Err(PathEscape(reason="absolute"))`. Implementation must detect `Path(relative).is_absolute()` and reject *before* any filesystem work (Rule 12 — fail loud, don't accidentally escape the jail through an absolute join).

### Smart-constructor — error paths (disjoint, mutation-resistant)

- [ ] **AC-3. Path-escape via `..` traversal.** `jail = tmp_path / "jail"` (mkdir), `outside = tmp_path / "outside.txt"` (write), `create(jail, "../outside.txt")` returns `Err(PathEscape)`. Assertions: `err.reason == "not_under_jail"` (exact, no disjunction); `Path(err.attempted_path).resolve() == outside.resolve()`; `Path(err.jail).resolve() == jail.resolve()`. This pins the audit-payload semantics, not just the discriminant.
- [ ] **AC-4. Missing leaf.** `create(tmp_path, "does-not-exist.txt")` → `Err(PathEscape(reason="missing"))` exactly. Test asserts `err.reason == "missing"` (NOT in a set).
- [ ] **AC-4b. Missing jail.** `create(tmp_path / "no-such-jail", "x.txt")` → `Err(PathEscape(reason="invalid_jail"))`. Implementation MUST catch `FileNotFoundError` from `jail.resolve(strict=True)` and translate; raising `FileNotFoundError` to the caller is a Rule 12 violation.
- [ ] **AC-5. Broken symlink (final component).** Create `jail/broken-link` as a symlink to `/does/not/exist/anywhere/i-promise`. `create(jail, "broken-link")` → `Err(PathEscape(reason="not_resolvable"))` exactly. The `reason in {missing, not_resolvable}` disjunction from the original draft is removed — broken-symlink-vs-missing-leaf MUST be distinguishable, because the smart-constructor distinguishes the two `OSError` subclasses (`FileNotFoundError` for leaf-missing; non-`FileNotFoundError` `OSError` for broken-chain). A collapsing-mutant no longer survives.
- [ ] **AC-12. Symlink-target-outside-jail rejected at create.** `jail/file.txt` is a symlink to `tmp_path / "elsewhere.txt"` (which exists). `create(jail, "file.txt")` resolves the symlink with `strict=True`, gets a path outside `jail`, returns `Err(PathEscape(reason="not_under_jail"))`. Proves the `is_relative_to(jail_abs)` check is operative AFTER symlink resolution. Strengthening: assert `Path(err.attempted_path).resolve() == (tmp_path / "elsewhere.txt").resolve()`.

### Immutability + Pydantic discipline

- [ ] **AC-6a. `SandboxedPath` is a frozen Pydantic `BaseModel`.** Assert `issubclass(SandboxedPath, BaseModel)`, `SandboxedPath.model_config["frozen"] is True`, `SandboxedPath.model_config["extra"] == "forbid"`. Mutating an attribute (`sp._absolute = Path("/etc")`) raises `pydantic.ValidationError` exactly — NOT `AttributeError` and NOT a bare `Exception`. (The original `pytest.raises((AttributeError, Exception))` was a catch-all that any exception passed.)
- [ ] **AC-6b. `PathEscape` is a frozen Pydantic `BaseModel`.** Same discipline as AC-6a applied to `PathEscape`. Two separate tests: (1) `PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail", extra="bad")` raises `ValidationError` (proves `extra="forbid"`); (2) mutating `err.reason = "missing"` raises `ValidationError` (proves `frozen=True`). Do NOT chain the two assertions — a mutant flipping `frozen=False` would be masked by the `extra="bad"` assertion firing first.
- [ ] **AC-sum-type-coverage. Every `PathEscape.reason` literal has a producing test.** Test introspects `typing.get_args(PathEscape.model_fields["reason"].annotation)` and for each literal value asserts there is at least one test in the file that produces an `Err(PathEscape(reason=<literal>))`. Sum-type-coverage pattern (ADR-0010 lineage) — prevents reason-creep without test coverage.

### `open()` — mandatory flags + mutation-resistant mode handling

- [ ] **AC-7. `_MANDATORY_FLAGS` is the single source of truth.** Module defines `_MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC` at module scope. Tests assert `_MANDATORY_FLAGS & os.O_NOFOLLOW != 0` AND `_MANDATORY_FLAGS & os.O_CLOEXEC != 0`. A future maintainer adding hardening flags (e.g., `O_NOATIME` if Phase 11 demands) edits one constant; the open() method picks it up automatically.
- [ ] **AC-7a. `open(mode)` ORs `_MANDATORY_FLAGS` into every call to `os.open`.** Parametrize over `mode ∈ {"r", "rb", "w", "wb", "r+", "a", "ab", "x", "xb"}`. Spy `os.open` via `monkeypatch.setattr`, capture flags, and assert for each mode:
  - `O_NOFOLLOW` set: `flags & os.O_NOFOLLOW != 0`.
  - `O_CLOEXEC` set: `flags & os.O_CLOEXEC != 0`.
  - **Exact base-flag composition** (each mode is one row — a single-bit mutant survives the original `&` test but fails this exact-mask check):
    - `r` / `rb`: `(flags & 0b11) == os.O_RDONLY`.
    - `w` / `wb`: `flags & os.O_WRONLY` AND `flags & os.O_CREAT` AND `flags & os.O_TRUNC`.
    - `a` / `ab`: `flags & os.O_WRONLY` AND `flags & os.O_CREAT` AND `flags & os.O_APPEND` AND `not (flags & os.O_TRUNC)`.
    - `r+`: `flags & os.O_RDWR`.
    - `x` / `xb`: `flags & os.O_WRONLY` AND `flags & os.O_CREAT` AND `flags & os.O_EXCL`.
  Note: the `b` suffix is a no-op at the os.open layer (affects only `os.fdopen`'s text-vs-binary kwarg).
- [ ] **AC-7b. Returned fd has `FD_CLOEXEC` set.** A non-monkeypatched test: open a file via `sp.open("rb")`, extract the underlying fd via `f.fileno()`, assert `fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC != 0`, close. Proves `O_CLOEXEC` is honored end-to-end, not just present in the flag word.
- [ ] **AC-7c. `_flags_for_mode` is a module-private pure helper.** Importable from tests as `from codegenie.plugins.sandbox_path import _flags_for_mode`. Hypothesis-property test: for any mode in the supported set, `_flags_for_mode(mode) & os.O_NOFOLLOW == 0` (the helper itself does NOT set mandatory flags — `open()` ORs them in; this avoids double-ORing and keeps the helper's contract narrow). A non-property-based test asserts unknown mode (e.g., `"q"`, `""`, `"rwx"`) raises `ValueError` (NOT a silent fall-through to `O_RDONLY` — Rule 12 fail-loud).
- [ ] **AC-fd-leak. fd-leak safety on `os.fdopen` failure.** Monkeypatch `os.fdopen` to raise `OSError("synthetic")`. Capture the fd from `os.open` via a spy. Call `sp.open("r")` and `pytest.raises(OSError)`. After the exception, assert the captured fd is closed by calling `os.fstat(fd)` and expecting `OSError(EBADF)`. Without this discipline, exceptional paths leak fds and the only symptom is `EMFILE` under load.
- [ ] **AC-fail-loud. `open()` catches no exceptions.** AST-scan test: parse `src/codegenie/plugins/sandbox_path.py`, locate the `SandboxedPath.open` `FunctionDef`, and assert it contains no `ast.Try` node with `handlers` (it may still contain a `try/finally` for fd cleanup, but no `except`). Per ADR-0011 §Decision §SandboxedPath: "Consumers handle `OSError(errno=ELOOP)`." Catching it here silently defeats the loud-fail discipline.

### TOCTOU — the load-bearing tests

- [ ] **AC-8. `test_symlink_swap_between_create_and_open_raises_eloop` (file → symlink).** Setup: `(jail / "realfile.txt").write_text("real")`, `sp = create(jail, "realfile.txt").unwrap()`. Swap: `target.unlink()`, write `(jail / "elsewhere.txt").write_text("attacker target")`, `os.symlink(elsewhere, target)`. Action: `sp.open("rb")`. Assertions: `pytest.raises(OSError)` with `excinfo.value.errno == errno.ELOOP` exactly. **Negative content check:** spy `os.open`; assert the spy either raised (`os.open` itself raised `ELOOP`) or never returned a fd that successfully read `b"attacker target"`. Documents that no bytes from the attacker-controlled file ever reached the consumer — the TOCTOU defense is preserve-confidentiality, not just raise-loud.
- [ ] **AC-9. Directory-symlink swap → ELOOP.** Same shape as AC-8 but the final component is replaced with a symlink to a directory (`os.symlink(other_dir, target)`). Same `OSError(errno=ELOOP)` expected. `O_NOFOLLOW` covers file-symlink AND directory-symlink final components.
- [ ] **AC-benign-replacement. Benign file-replacement is permitted (not a TOCTOU defense target).** Setup: `sp = create(jail, "f.txt").unwrap()`. Between create and open, `os.replace(jail / "f2.txt", jail / "f.txt")` (atomic real-file replacement; no symlink involved). `sp.open("rb").read()` succeeds and returns the new content. Documents the honest framing: only symlink-swap is a TOCTOU defense target. A defense-overzealous mutant that rejected every inode change would pass AC-8/AC-9 but fail this AC.

### Honest framing — known limitations documented as living tests

- [ ] **AC-10a. Intermediate-component symlink is NOT caught.** Create `jail/realdir/b.txt` (real). Add `jail/aliased` as `os.symlink(jail/"realdir", jail/"aliased")`. `create(jail, "aliased/b.txt")` succeeds; `sp.open("rb").read() == b"ok"`. Documents that `O_NOFOLLOW` only affects the final path component (per `man 2 open`). An attacker who can write to an intermediate directory is already a higher-level compromise than this primitive defends against.
- [ ] **AC-10b. Hardlink swap is NOT caught.** `(jail / "real.txt").write_text("trusted")`, `sp = create(jail, "real.txt").unwrap()`. Replace `real.txt` with a hardlink: `target.unlink(); os.link(other_real_file, target)` where `other_real_file` is a regular file inside `jail`. `sp.open("rb")` does NOT raise — hardlinks share an inode and are not symlinks. This is the documented limitation; the module docstring must enumerate it.
- [ ] **AC-10c. Special-file swap (FIFO / socket) is NOT caught by `O_NOFOLLOW`.** `(jail / "real.txt").write_text("ok")`, `sp = create(jail, "real.txt").unwrap()`. Replace with a FIFO: `target.unlink(); os.mkfifo(target)`. `sp.open("rb")` does NOT raise `ELOOP`. (It may block, deadlock-prone — test uses a thread that closes after a short timeout, or `os.open` with `O_NONBLOCK` in the test only to probe non-blocking.) Documents the limitation. If the test fixture cannot be made portable enough (macOS/Linux), this AC may be a skip-if-unsupported with an explanatory message; the docstring assertion MUST still cover the limitation in prose.

### Cross-story wiring — `_forward.py` substitution + fence

- [ ] **AC-Sub-1. `transforms._forward.SandboxedPath` re-exports the new class.** `src/codegenie/transforms/_forward.py` no longer declares `SandboxedPath: TypeAlias = pathlib.Path`. Instead: `from codegenie.plugins.sandbox_path import SandboxedPath`. Tests: `from codegenie.transforms import SandboxedPath as A; from codegenie.plugins.sandbox_path import SandboxedPath as B; assert A is B`. Existing consumers (`Transform`, `ApplyContext`) keep importing from `codegenie.transforms` unchanged.
- [ ] **AC-Sub-2. Fence allowlist amended.** `tests/fence/test_transforms_module_purity.py::_FORWARD_ALLOWED` extended to `frozenset({"__future__", "pathlib", "typing", "pydantic", "codegenie.plugins.sandbox_path"})`. `test_forward_module_imports_only_allowed` passes. Inverse direction (`plugins.sandbox_path` importing from `transforms`) remains forbidden — guarded by AC-purity-fence.
- [ ] **AC-Sub-3. Existing Pydantic consumers still accept `SandboxedPath` instances.** `Transform(transform_id=..., diff_bytes=b"", files_changed=(sp,), provenance=...)` constructs without `ValidationError` where `sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()`. `ApplyContext(...evidence_paths=(sp,), ...)` likewise. Two tests, one per consumer. Both already declare `arbitrary_types_allowed=True` OR `SandboxedPath` is Pydantic-native (`BaseModel`) — pinned by the choice in AC-6a, so these tests should pass without consumer-side edits. If they fail, that is a signal the shape choice broke a consumer — block on it.
- [ ] **AC-11. `JailedSubprocessSpec.cwd` (S4-01) accepts a `SandboxedPath`.** Round-trip test: import both via `codegenie.transforms` (`from codegenie.transforms import SandboxedPath` and `from codegenie.transforms.sandbox_jail import JailedSubprocessSpec, DenyAll, NpmEnv` — verify the import path against S4-01's landed code; if S4-01 lands in a subpackage like `codegenie.transforms.sandbox.jail`, follow that). Construct `JailedSubprocessSpec(cwd=sp, ...)`. Assertions: `spec.cwd is sp` AND `isinstance(spec.cwd, BaseModel)` AND `not isinstance(spec.cwd, pathlib.Path)`. The last two assertions catch the "alias not flipped" regression — without AC-Sub-1, the type is `Path` and `not isinstance(..., Path)` would fail. mypy-strict clean (no `type: ignore`, no `# noqa`).

### Static surface fences

- [ ] **AC-purity-fence. `sandbox_path.py` import allowlist pinned.** New fence at `tests/fence/test_plugins_sandbox_path_purity.py` AST-walks `codegenie.plugins.sandbox_path` and asserts its imported module names are a subset of `frozenset({"__future__", "errno", "fcntl", "os", "pathlib", "typing", "pydantic", "codegenie.result"})`. Specifically forbids `codegenie.transforms.*` imports (closes the cycle that ADR-0001 + ADR-0013 already defend against in the opposite direction).
- [ ] **AC-14. Quality gates.** `mypy --strict src/codegenie/plugins/sandbox_path.py src/codegenie/transforms/_forward.py tests/unit/plugins/test_sandbox_path.py tests/fence/test_plugins_sandbox_path_purity.py` clean. `ruff check` + `ruff format --check` clean across the changed files.

### Docstring discipline (honest framing — dual)

- [ ] **AC-15a. Required substrings.** Module docstring contains all of: `"in-jail at construction"`, `"audit + lint"` (or `"audit + lint enforcement"`), `"03-ADR-0011"` (or `"ADR-0011"`). Cite the ADR by number.
- [ ] **AC-15b. Banned substrings (the framing discipline ADR-0011 actually mandates).** Module docstring contains NONE of (case-insensitive): `"in-jail forever"`, `"unforgeable"`, `"makes illegal states unrepresentable"`, `"illegal states unrepresentable"`, `"signature"` (the lockfile-context word that ADR-0011 §Context attacks). Per ADR-0011 §Consequences: framing is a dual discipline — use the right phrases AND avoid the wrong ones. A test asserts each banned substring `not in module_docstring.lower()`.
- [ ] **AC-15c. Known-limitations enumerated.** Module docstring (or a clearly-marked block under `class SandboxedPath`'s docstring) names all four uncaught vectors from AC-10a..AC-10c plus the benign-replacement note: (1) intermediate-component symlink, (2) hardlink swap, (3) FIFO/socket/device replacement, (4) atomic real-file replacement (`os.replace`) of the final component. Test asserts each phrase is present.

### Deferred (tracked, not blocking)

- [ ] **AC-16 (deferred). Consumer-side fence: every `.open()` call on a `SandboxedPath` is wrapped in `try/except OSError` or routed through a `with_sandbox_open(...)` helper that catches `ELOOP` and emits `FilesystemRaceDetected`.** Per `High-level-impl §Step 4 Risk 5`, this fence + helper lands when the first real consumer arrives (S5-02's `NpmLockfileRecipeEngine` or S6-04's `LocalGitOps`). This story does NOT introduce a helper without a real consumer (Rule 2 — Simplicity First). The executor's attempt log must include a `Tracking: AC-16 deferred to S5-02 / S4-05` entry; do NOT mark BLOCKED-PARTIAL — explicit deferral is acceptable and documented.
- [ ] **AC-17 (deferred). Capability-construction lint rule.** A custom ruff rule (or `tests/static/` AST-walk) banning `SandboxedPath(...)` direct construction outside `sandbox_path.py` + `tests/` — mirroring ADR-0011 §Consequences "`tooling/ruff_rules/no_capability_construction.py`" precedent. Without this rule, ADR-0011's "audit + lint enforcement" framing is half-delivered. Deferred to S4-05 (Capability Fence story). Attempt log: `Tracking: AC-17 deferred to S4-05`.

## Implementation outline

1. **`Result` shape is pinned by the codebase.** `from codegenie.result import Err, Ok, Result`. API: `Ok(value=...)`, `Err(error=...)`, `.is_ok()`, `.is_err()`, `.unwrap()`, `.unwrap_err()`. See `src/codegenie/result.py:40-80`. (NOT `codegenie.types.result` — that module does not exist; 19 importers across `src/` and `tests/` use `codegenie.result`.)

2. **Create `src/codegenie/plugins/sandbox_path.py`.** Module docstring up front (AC-15a/15b/15c — honest framing dual discipline, banned substrings, known-limitations enumeration). Allowed imports (enforced by AC-purity-fence):
   ```python
   from __future__ import annotations
   import errno
   import fcntl  # only if needed for AC-7b assertion in tests; otherwise leave to test file
   import os
   from pathlib import Path
   from typing import IO, Any, Final, Literal
   from pydantic import BaseModel, ConfigDict
   from codegenie.result import Err, Ok, Result
   ```

3. **Module-level constants.**
   ```python
   _MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC
   """Single source of truth for mandatory ``open()`` flags.
   AC-7 pins both bits. Future hardening (e.g., O_NOATIME) lands here in one place."""
   ```

4. **`PathEscape(BaseModel)`** with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields:
   ```python
   kind: Literal["path_escape"] = "path_escape"
   attempted_path: str
   jail: str
   reason: Literal["not_under_jail", "not_resolvable", "missing", "absolute", "invalid_jail"]
   ```

5. **`class SandboxedPath(BaseModel)`** — Pydantic frozen value type (pinned shape, per AC-6a):
   ```python
   class SandboxedPath(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
       _absolute: Path  # use a private attr via Pydantic private-attr if needed,
                         # OR expose as a regular field with a leading-underscore name
                         # validated by Pydantic — pick the shape that survives the
                         # AC-Sub-3 round-trip test with Transform/ApplyContext.
   ```
   Note: Pydantic v2 supports private attributes via `PrivateAttr`. The Phase 3 precedent is to use regular fields; verify against `src/codegenie/plugins/scope.py` and `manifest.py` before choosing.

6. **`SandboxedPath.create(cls, jail, relative)`** — `@classmethod` returning `Result["SandboxedPath", PathEscape]`. Order matters; mutations to this body change which AC fires:
   ```python
   # Step A — reject absolute relative-arg eagerly (Rule 12, fail loud)
   rel_path = Path(relative)
   if rel_path.is_absolute():
       return Err(error=PathEscape(
           attempted_path=str(rel_path),
           jail=str(jail),
           reason="absolute",
       ))

   # Step B — resolve jail with strict=True; missing jail is "invalid_jail"
   try:
       jail_abs = jail.resolve(strict=True)
   except FileNotFoundError:
       return Err(error=PathEscape(
           attempted_path=str(jail / rel_path),
           jail=str(jail),
           reason="invalid_jail",
       ))

   # Step C — resolve (jail_abs / relative) with strict=True
   candidate = jail_abs / rel_path
   try:
       resolved = candidate.resolve(strict=True)
   except FileNotFoundError:
       return Err(error=PathEscape(
           attempted_path=str(candidate),
           jail=str(jail_abs),
           reason="missing",
       ))
   except OSError:  # broken symlink chain (ELOOP / ENOTDIR / etc. — NOT FileNotFoundError)
       return Err(error=PathEscape(
           attempted_path=str(candidate),
           jail=str(jail_abs),
           reason="not_resolvable",
       ))

   # Step D — in-jail check (post-resolution, both sides resolved with strict=True)
   if not resolved.is_relative_to(jail_abs):
       return Err(error=PathEscape(
           attempted_path=str(resolved),
           jail=str(jail_abs),
           reason="not_under_jail",
       ))

   return Ok(value=cls(_absolute=resolved))
   ```

7. **`SandboxedPath.absolute`** — `@property` returning the resolved `Path`.

8. **`SandboxedPath.open(mode)`** — always ORs `_MANDATORY_FLAGS`; closes fd on `os.fdopen` failure; catches NO exceptions (AC-fail-loud):
   ```python
   def open(self, mode: str) -> IO[Any]:
       flags = _flags_for_mode(mode) | _MANDATORY_FLAGS
       fd = os.open(self._absolute, flags)
       try:
           return os.fdopen(fd, mode)
       except BaseException:
           os.close(fd)
           raise
   ```
   The `try/finally`-shaped exception path is the ONLY exception-handling construct in `open()`. No `except OSError` or `except Exception`. The AC-fail-loud AST-scan asserts this.

9. **`_flags_for_mode(mode: str) -> int`** — module-private pure helper. Closed `dict` lookup (NOT chained `if/elif`, NOT `match` — a dict literal is the most-readable closed-table shape and supports the `_flags_for_mode("q") -> ValueError` discipline directly):
   ```python
   _MODE_TO_BASE_FLAGS: Final[dict[str, int]] = {
       "r": os.O_RDONLY,
       "rb": os.O_RDONLY,
       "w": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
       "wb": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
       "a": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
       "ab": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
       "r+": os.O_RDWR,
       "rb+": os.O_RDWR,
       "x": os.O_WRONLY | os.O_CREAT | os.O_EXCL,
       "xb": os.O_WRONLY | os.O_CREAT | os.O_EXCL,
   }

   def _flags_for_mode(mode: str) -> int:
       try:
           return _MODE_TO_BASE_FLAGS[mode]
       except KeyError as exc:
           raise ValueError(f"unsupported mode for SandboxedPath.open: {mode!r}") from exc
   ```
   The helper does NOT OR in `_MANDATORY_FLAGS` — `open()` does. Keeps the helper's contract narrow and makes AC-7c testable in isolation.

10. **`_forward.py` substitution** (AC-Sub-1). Replace `SandboxedPath: TypeAlias = pathlib.Path` with:
    ```python
    from codegenie.plugins.sandbox_path import SandboxedPath  # re-exported
    ```
    Keep `__all__ = ["CapabilityBundle", "SandboxedPath"]` unchanged. Update the module docstring's "S4-04 — Replace …" bullet to past tense.

11. **Fence allowlist amendment** (AC-Sub-2). `tests/fence/test_transforms_module_purity.py`:
    ```python
    _FORWARD_ALLOWED: frozenset[str] = frozenset(
        {"__future__", "pathlib", "typing", "pydantic", "codegenie.plugins.sandbox_path"}
    )
    ```
    Update `test_forward_module_imports_only_allowed`'s docstring to reflect that S4-04 has flipped the substitution direction.

12. **Module-purity fence for `sandbox_path.py`** (AC-purity-fence). New file `tests/fence/test_plugins_sandbox_path_purity.py` modeled on `tests/fence/test_transforms_module_purity.py` (`_imported_module_names` AST helper); allowlist = `{"__future__", "errno", "os", "pathlib", "typing", "pydantic", "codegenie.result"}` (plus `"fcntl"` only if production code imports it; if `fcntl` is test-only for AC-7b, omit from the source allowlist).

13. **Tests in `tests/unit/plugins/test_sandbox_path.py`** per the AC list. The TOCTOU tests (AC-8 / AC-9) and the limitation-documentation tests (AC-10a/10b/10c) require actual filesystem manipulation between `create()` and `open()` — use real `tmp_path` plus `os.symlink` / `os.unlink` / `os.replace` / `os.link` / `os.mkfifo`. Hypothesis test for `_flags_for_mode` follows the Phase 1 / Phase 2 hypothesis precedent (search `tests/unit/probes/` for `from hypothesis import` to mirror the established import + decorator pattern).

14. **AC-Sub-3 Pydantic-consumer round-trip tests.** Live under `tests/unit/transforms/` (NOT `tests/unit/plugins/`), so they exercise the consumer surface from the consumer's own test directory. Two new tests: `test_transform_accepts_sandboxed_path_in_files_changed` and `test_apply_context_accepts_sandboxed_path_in_evidence_paths`.

15. Run `mypy --strict src/codegenie/plugins/sandbox_path.py src/codegenie/transforms/_forward.py tests/unit/plugins/test_sandbox_path.py tests/fence/test_plugins_sandbox_path_purity.py`; `ruff check`; `ruff format --check`; `pytest tests/unit/plugins/test_sandbox_path.py tests/fence/test_plugins_sandbox_path_purity.py tests/fence/test_transforms_module_purity.py tests/unit/transforms/ -v`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Two new test files (plus extensions to `tests/fence/test_transforms_module_purity.py` for AC-Sub-2 and two new tests under `tests/unit/transforms/` for AC-Sub-3). Sketches below are illustrative — exhaustive coverage follows the AC list.

`tests/unit/plugins/test_sandbox_path.py`:

```python
from __future__ import annotations

import ast
import errno
import fcntl
import os
import typing
from pathlib import Path

import pytest
from hypothesis import given, strategies as st
from pydantic import BaseModel, ValidationError

# RED — these imports fail until S4-04 lands
from codegenie.plugins.sandbox_path import (
    _MANDATORY_FLAGS,
    _flags_for_mode,
    PathEscape,
    SandboxedPath,
)
from codegenie.result import Err, Ok, Result


# --- AC-1 surface lock ---
def test_module_all_is_alphabetized_pair() -> None:
    import codegenie.plugins.sandbox_path as mod
    assert mod.__all__ == ["PathEscape", "SandboxedPath"]
    publics = {n for n in vars(mod) if not n.startswith("_")}
    # everything public must be in __all__; helpers must be underscore-prefixed
    leaked = publics - set(mod.__all__)
    assert not leaked, f"unintended public surface: {leaked!r}"


def test_result_imported_from_canonical_module() -> None:
    # Proves the implementer used codegenie.result (NOT codegenie.types.result)
    import codegenie.plugins.sandbox_path as mod
    src = Path(mod.__file__).read_text()
    assert "from codegenie.result import" in src
    assert "codegenie.types.result" not in src


# --- AC-2 / AC-2b ---
def test_create_happy_path(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hi")
    sp = SandboxedPath.create(tmp_path, "file.txt").unwrap()
    assert sp.absolute == (tmp_path / "file.txt").resolve()
    assert isinstance(sp, BaseModel)
    assert not isinstance(sp, Path)


def test_create_with_symlinked_jail_resolves_both(tmp_path: Path) -> None:
    real_jail = tmp_path / "real"
    real_jail.mkdir()
    alias_jail = tmp_path / "alias"
    os.symlink(real_jail, alias_jail)
    (real_jail / "f.txt").write_text("ok")
    sp = SandboxedPath.create(alias_jail, "f.txt").unwrap()
    assert sp.absolute == (real_jail / "f.txt").resolve()


# --- AC-relative-shape ---
@pytest.mark.parametrize(
    "rel,expected_kind,expected_reason",
    [
        ("", "ok", None),
        (".", "ok", None),
        ("/etc/passwd", "err", "absolute"),
    ],
)
def test_relative_arg_edge_cases(
    tmp_path: Path, rel: str, expected_kind: str, expected_reason: str | None,
) -> None:
    result = SandboxedPath.create(tmp_path, rel)
    if expected_kind == "ok":
        sp = result.unwrap()
        assert sp.absolute == tmp_path.resolve(strict=True)
    else:
        err = result.unwrap_err()
        assert err.reason == expected_reason


# --- AC-3 path-escape with attempted_path payload pinned ---
def test_create_path_escape_via_dotdot(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    result = SandboxedPath.create(jail, "../outside.txt")
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, PathEscape)
    assert err.reason == "not_under_jail"
    assert Path(err.attempted_path).resolve() == outside.resolve()
    assert Path(err.jail).resolve() == jail.resolve()


# --- AC-4 / AC-4b ---
def test_create_missing_leaf(tmp_path: Path) -> None:
    err = SandboxedPath.create(tmp_path, "does-not-exist.txt").unwrap_err()
    assert err.reason == "missing"  # exact, no disjunction


def test_create_when_jail_does_not_exist(tmp_path: Path) -> None:
    err = SandboxedPath.create(tmp_path / "no-such-jail", "x.txt").unwrap_err()
    assert err.reason == "invalid_jail"


# --- AC-5 broken symlink — distinct from missing-leaf ---
def test_create_broken_symlink(tmp_path: Path) -> None:
    (tmp_path / "broken-link").symlink_to("/does/not/exist/anywhere/i-promise")
    err = SandboxedPath.create(tmp_path, "broken-link").unwrap_err()
    assert err.reason == "not_resolvable"  # NOT in {missing, not_resolvable}


# --- AC-6a / AC-6b ---
def test_sandboxed_path_frozen_and_extra_forbid(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "x.txt").unwrap()
    assert issubclass(SandboxedPath, BaseModel)
    assert SandboxedPath.model_config.get("frozen") is True
    assert SandboxedPath.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        sp._absolute = Path("/etc")  # type: ignore[misc]


def test_path_escape_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail", extra="bad")  # type: ignore[call-arg]


def test_path_escape_frozen() -> None:
    err = PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail")
    with pytest.raises(ValidationError):
        err.reason = "missing"  # type: ignore[misc]


# --- AC-sum-type-coverage ---
def test_every_path_escape_reason_has_a_producing_test(tmp_path: Path) -> None:
    reasons = set(typing.get_args(PathEscape.model_fields["reason"].annotation))
    # The producer set MUST equal the declared literal set — caught at runtime
    # so reason-creep without test coverage fails. The story's AC list pins
    # at least one producer for each: not_under_jail, not_resolvable, missing,
    # absolute, invalid_jail. This test is a self-check via a small fixture
    # table; it does NOT introspect other test functions.
    produced = set()
    # not_under_jail — via dotdot
    jail = tmp_path / "j"; jail.mkdir(); (tmp_path / "x").write_text("")
    produced.add(SandboxedPath.create(jail, "../x").unwrap_err().reason)
    # missing
    produced.add(SandboxedPath.create(tmp_path, "nope").unwrap_err().reason)
    # invalid_jail
    produced.add(SandboxedPath.create(tmp_path / "no-jail", "x").unwrap_err().reason)
    # absolute
    produced.add(SandboxedPath.create(tmp_path, "/etc/passwd").unwrap_err().reason)
    # not_resolvable
    (tmp_path / "broken").symlink_to("/no/such/path/here")
    produced.add(SandboxedPath.create(tmp_path, "broken").unwrap_err().reason)
    assert produced == reasons, f"unreached reasons: {reasons - produced}"


# --- AC-7 / AC-7a / AC-7b / AC-7c ---
def test_mandatory_flags_constant() -> None:
    assert _MANDATORY_FLAGS & os.O_NOFOLLOW != 0
    assert _MANDATORY_FLAGS & os.O_CLOEXEC != 0


@pytest.mark.parametrize(
    "mode,base_assertion",
    [
        ("r",  lambda f: (f & 0b11) == os.O_RDONLY),
        ("rb", lambda f: (f & 0b11) == os.O_RDONLY),
        ("w",  lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_TRUNC)),
        ("wb", lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_TRUNC)),
        ("a",  lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_APPEND) and not (f & os.O_TRUNC)),
        ("ab", lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_APPEND) and not (f & os.O_TRUNC)),
        ("r+", lambda f: f & os.O_RDWR),
        ("x",  lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_EXCL)),
        ("xb", lambda f: (f & os.O_WRONLY) and (f & os.O_CREAT) and (f & os.O_EXCL)),
    ],
)
def test_open_flag_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, base_assertion,
) -> None:
    # For modes that require the file to NOT exist (x/xb) start with no file;
    # for others, create the leaf.
    leaf = tmp_path / "f.txt"
    if not mode.startswith("x"):
        leaf.write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt" if leaf.exists() else "g.txt")
    sp = sp.unwrap() if sp.is_ok() else SandboxedPath.create(tmp_path, "g.txt")  # type: ignore[assignment]
    # When the leaf does not exist (x/xb), the implementation must still
    # be testable. Adjust the test setup as needed for the chosen `relative`.
    captured: list[int] = []
    real_open = os.open
    def spy_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        captured.append(flags)
        return real_open(p, flags, *a, **kw)
    monkeypatch.setattr(os, "open", spy_open)
    try:
        f = sp.open(mode)
        f.close()
    except OSError:
        pass  # only the captured flag-set matters for this AC
    assert captured, "os.open was never called"
    for f in captured:
        assert f & os.O_NOFOLLOW, f"O_NOFOLLOW missing for mode={mode!r}; flags={f}"
        assert f & os.O_CLOEXEC, f"O_CLOEXEC missing for mode={mode!r}; flags={f}"
        assert base_assertion(f), f"base flag composition wrong for mode={mode!r}; flags={f}"


def test_returned_fd_has_fd_cloexec(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("ok")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    f = sp.open("rb")
    try:
        fd = f.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        assert flags & fcntl.FD_CLOEXEC
    finally:
        f.close()


@given(mode=st.sampled_from(["r", "rb", "w", "wb", "a", "ab", "r+", "x", "xb"]))
def test_flags_for_mode_does_not_set_mandatory_flags(mode: str) -> None:
    f = _flags_for_mode(mode)
    # The helper's contract: it returns the BASE flags only. open() ORs in
    # _MANDATORY_FLAGS. This keeps the helper testable in isolation.
    assert (f & os.O_NOFOLLOW) == 0
    assert (f & os.O_CLOEXEC) == 0


@pytest.mark.parametrize("bad", ["q", "", "rwx", "rbz"])
def test_flags_for_mode_unknown_mode_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        _flags_for_mode(bad)


def test_open_unknown_mode_raises_loudly(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    with pytest.raises(ValueError):
        sp.open("q")


# --- AC-fd-leak ---
def test_open_closes_fd_when_fdopen_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    captured_fd: list[int] = []
    real_open = os.open
    def spy_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **kw)
        captured_fd.append(fd)
        return fd
    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "fdopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("synthetic")))
    with pytest.raises(OSError):
        sp.open("rb")
    assert captured_fd, "os.open was never called"
    with pytest.raises(OSError) as ei:
        os.fstat(captured_fd[0])
    assert ei.value.errno == errno.EBADF


# --- AC-fail-loud — AST-scan asserts open() catches nothing ---
def test_open_method_has_no_exception_handlers() -> None:
    import codegenie.plugins.sandbox_path as mod
    src = Path(mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "open":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Try):
                    assert not sub.handlers, (
                        "SandboxedPath.open() must not catch exceptions; "
                        "consumers handle OSError(errno=ELOOP). A try/finally is OK; "
                        "a try/except is not."
                    )
            return
    raise AssertionError("SandboxedPath.open method not found")


# --- AC-8 — THE LOAD-BEARING TOCTOU TEST ---
def test_symlink_swap_between_create_and_open_raises_eloop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "realfile.txt"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "realfile.txt").unwrap()

    target.unlink()
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("attacker target")
    os.symlink(elsewhere, target)

    # Spy os.open to confirm no successful fd was opened on the attacker file.
    opened_fds: list[int] = []
    real_open = os.open
    def spy_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **kw)
        opened_fds.append(fd)
        return fd
    monkeypatch.setattr(os, "open", spy_open)

    with pytest.raises(OSError) as excinfo:
        sp.open("rb")
    assert excinfo.value.errno == errno.ELOOP
    # Confidentiality: os.open itself raised; no fd ever opened on the attacker target.
    assert opened_fds == [], (
        "os.open should have raised ELOOP before returning an fd; "
        f"opened fds: {opened_fds}"
    )


# --- AC-9 ---
def test_directory_symlink_swap_raises_eloop(tmp_path: Path) -> None:
    target = tmp_path / "dir_or_file"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "dir_or_file").unwrap()
    target.unlink()
    other_dir = tmp_path / "other_dir"
    other_dir.mkdir()
    os.symlink(other_dir, target)
    with pytest.raises(OSError) as ei:
        sp.open("rb")
    assert ei.value.errno == errno.ELOOP


# --- AC-benign-replacement ---
def test_benign_real_file_replacement_is_permitted(tmp_path: Path) -> None:
    f1 = tmp_path / "f.txt"; f1.write_text("v1")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    f2 = tmp_path / "f2.txt"; f2.write_text("v2")
    os.replace(f2, f1)  # atomic real-file swap; no symlink involved
    with sp.open("rb") as f:
        assert f.read() == b"v2"


# --- AC-10a / AC-10b / AC-10c (known limitations) ---
def test_intermediate_component_symlink_is_not_caught(tmp_path: Path) -> None:
    realdir = tmp_path / "realdir"; realdir.mkdir()
    (realdir / "b.txt").write_text("ok")
    os.symlink(realdir, tmp_path / "aliased")
    sp = SandboxedPath.create(tmp_path, "aliased/b.txt").unwrap()
    with sp.open("rb") as f:
        assert f.read() == b"ok"


def test_hardlink_swap_is_not_caught(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"; real.write_text("trusted")
    sp = SandboxedPath.create(tmp_path, "real.txt").unwrap()
    other = tmp_path / "other.txt"; other.write_text("attacker")
    real.unlink()
    os.link(other, real)
    # Hardlinks share an inode; O_NOFOLLOW does NOT block them.
    with sp.open("rb") as f:
        content = f.read()
    assert content == b"attacker", "documents the hardlink-swap limitation"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo not available")
def test_fifo_replacement_is_not_caught_by_o_nofollow(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"; real.write_text("ok")
    sp = SandboxedPath.create(tmp_path, "real.txt").unwrap()
    real.unlink()
    os.mkfifo(real)
    # O_NOFOLLOW does not block FIFO opens. The open call may block on the
    # writer side; use O_NONBLOCK only for this probe via os.open spy isn't
    # part of the contract — instead just assert no ELOOP raised when probed
    # via low-level os.open with O_NONBLOCK.
    fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        # Reached: O_NOFOLLOW did NOT block the FIFO open. Limitation confirmed.
        pass
    finally:
        os.close(fd)


# --- AC-12 ---
def test_symlink_target_outside_jail_rejected_at_create(tmp_path: Path) -> None:
    jail = tmp_path / "jail"; jail.mkdir()
    outside = tmp_path / "elsewhere.txt"; outside.write_text("target")
    (jail / "file.txt").symlink_to(outside)
    err = SandboxedPath.create(jail, "file.txt").unwrap_err()
    assert err.reason == "not_under_jail"
    assert Path(err.attempted_path).resolve() == outside.resolve()


# --- AC-11 — round-trip with JailedSubprocessSpec (post-flip semantics) ---
def test_sandboxed_path_satisfies_subprocess_jail_cwd(tmp_path: Path) -> None:
    # Imports here (not at file top) so collection doesn't fail if S4-01 has
    # not yet landed. The story's Depends-on commits to S4-01's signature.
    from codegenie.transforms import SandboxedPath as TransformsSP
    # Lock the alias-flip: transforms.SandboxedPath IS plugins.sandbox_path.SandboxedPath
    from codegenie.plugins.sandbox_path import SandboxedPath as PluginsSP
    assert TransformsSP is PluginsSP

    from codegenie.transforms.sandbox_jail import (  # adjust to actual S4-01 path
        DenyAll, JailedSubprocessSpec, NpmEnv,
    )
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=sp,
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=1.0, memory_mib=1, pids_max=1,
    )
    assert spec.cwd is sp
    assert isinstance(spec.cwd, BaseModel)
    assert not isinstance(spec.cwd, Path)


# --- AC-15a / AC-15b / AC-15c — honest framing dual discipline ---
def test_module_docstring_uses_honest_framing() -> None:
    import codegenie.plugins.sandbox_path as mod
    doc = (mod.__doc__ or "")
    low = doc.lower()
    # Positive: required substrings
    assert "in-jail at construction" in doc
    assert "audit + lint" in doc or "audit and lint" in low
    assert "adr-0011" in low
    # Negative: banned framings (case-insensitive)
    for banned in (
        "in-jail forever",
        "unforgeable",
        "makes illegal states unrepresentable",
        "illegal states unrepresentable",
        "signature",
    ):
        assert banned not in low, f"docstring contains banned phrase: {banned!r}"
    # Limitations enumerated
    for phrase in ("intermediate", "hardlink", "fifo"):
        assert phrase in low, f"docstring missing limitation phrase: {phrase!r}"


# --- AC-Sub-1 alias-flip ---
def test_transforms_sandboxed_path_is_plugins_sandboxed_path() -> None:
    from codegenie.transforms import SandboxedPath as A
    from codegenie.plugins.sandbox_path import SandboxedPath as B
    assert A is B
```

`tests/fence/test_plugins_sandbox_path_purity.py` (new file):

```python
"""AC-purity-fence — sandbox_path.py imports a closed allowlist."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import codegenie.plugins.sandbox_path as mod

_ALLOWED: frozenset[str] = frozenset(
    {"__future__", "errno", "os", "pathlib", "typing", "pydantic", "codegenie.result"}
)


def _imported_module_names(src: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "<relative-import>")
    return names


def test_sandbox_path_module_imports_only_allowed() -> None:
    src = inspect.getsource(mod)
    extra = _imported_module_names(src) - _ALLOWED
    assert not extra, (
        f"codegenie.plugins.sandbox_path imports outside the allowlist: {sorted(extra)}"
    )
```

`tests/fence/test_transforms_module_purity.py` (extend the existing `_FORWARD_ALLOWED` set per AC-Sub-2):

```python
_FORWARD_ALLOWED: frozenset[str] = frozenset(
    {"__future__", "pathlib", "typing", "pydantic", "codegenie.plugins.sandbox_path"}
)
```

`tests/unit/transforms/test_pydantic_consumers_accept_sandboxed_path.py` (new file — AC-Sub-3):

```python
"""AC-Sub-3 — existing Pydantic consumers accept the new SandboxedPath."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.plugins.sandbox_path import SandboxedPath
from codegenie.transforms.transform import Transform  # adjust to landed surface
from codegenie.transforms.apply_context import ApplyContext  # adjust


def test_transform_files_changed_accepts_sandboxed_path(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    # Construct a minimal Transform — exact constructor signature mirrors
    # the landed Transform ABC at src/codegenie/transforms/transform.py
    # (use whatever subclass / build-helper Phase 3 already ships in tests).
    ...  # see tests/unit/transforms/test_transform_abc.py for the precedent


def test_apply_context_evidence_paths_accepts_sandboxed_path(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    ...  # mirror the existing ApplyContext construction precedent
```

Run — all RED (module + flip missing). Commit.

### Green — make it pass

Implement `src/codegenie/plugins/sandbox_path.py` per Implementation outline. Update `src/codegenie/transforms/_forward.py` (AC-Sub-1) and the fence allowlist (AC-Sub-2). Add the two AC-Sub-3 consumer tests.

The TOCTOU test (AC-8) is the most likely to surface implementation bugs:
- If `open()` uses Python's `builtins.open` directly, you don't get a chance to add `O_NOFOLLOW` — must route through `os.open(..., flags | _MANDATORY_FLAGS)` + `os.fdopen(fd, mode)`.
- Edge: on macOS, `open()` of an already-existing file with `O_RDONLY | O_NOFOLLOW` and a final-component symlink gives `ELOOP`; same on Linux. Test runs identically on both.
- `os.fdopen` failure path must close the fd before raising (AC-fd-leak). The cleanest shape is `try: return os.fdopen(fd, mode); except BaseException: os.close(fd); raise`.

### Refactor — clean up

- Pull `_flags_for_mode(mode: str) -> int` and the `_MODE_TO_BASE_FLAGS` table into the module-private section if `open()` is still long after green.
- `_check_under_jail` extraction — defer. Single call site today; Rule 2 wins. Notes-for-implementer captures the trigger condition.
- Docstring polish; ensure ADR-0011 citation is in the right place (module-level, not function-level — the AC-15a/15b/15c tests read `mod.__doc__`).
- `ruff format`, `mypy --strict`, full test suite green (including the two new fence tests, the extended `_FORWARD_ALLOWED` fence, and the two new consumer-side tests under `tests/unit/transforms/`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/sandbox_path.py` | **New.** `SandboxedPath` Pydantic frozen value type with `create() -> Result[SandboxedPath, PathEscape]`, `.absolute` property, `.open(mode)` always ORs `_MANDATORY_FLAGS` (`O_NOFOLLOW | O_CLOEXEC`); `PathEscape` Pydantic error variant; `_flags_for_mode` pure helper. (AC-1..AC-15c, AC-relative-shape, AC-fd-leak, AC-fail-loud.) |
| `src/codegenie/transforms/_forward.py` | **Edit (AC-Sub-1).** Replace `SandboxedPath: TypeAlias = pathlib.Path` with `from codegenie.plugins.sandbox_path import SandboxedPath`. Keep `__all__` unchanged. Update the docstring's "S4-04 — Replace …" bullet to past tense. |
| `tests/fence/test_transforms_module_purity.py` | **Edit (AC-Sub-2).** Extend `_FORWARD_ALLOWED` to `frozenset({"__future__", "pathlib", "typing", "pydantic", "codegenie.plugins.sandbox_path"})`. Update `test_forward_module_imports_only_allowed`'s docstring to reflect that S4-04 has flipped the substitution. |
| `tests/fence/test_plugins_sandbox_path_purity.py` | **New (AC-purity-fence).** AST-walks `codegenie.plugins.sandbox_path` and asserts imported module names ⊆ `{"__future__", "errno", "os", "pathlib", "typing", "pydantic", "codegenie.result"}`. Forbids `codegenie.transforms.*` imports. |
| `tests/unit/plugins/test_sandbox_path.py` | **New.** AC-1 through AC-15c, including the load-bearing TOCTOU test (AC-8), the negative-content confidentiality assertion, hardlink/FIFO limitation tests (AC-10b/10c), benign-replacement test (AC-benign-replacement), `_flags_for_mode` hypothesis + unknown-mode tests (AC-7c), fd-leak test (AC-fd-leak), AST-scan of `open()` exception handlers (AC-fail-loud), and the alias-flip check (AC-Sub-1). |
| `tests/unit/transforms/test_pydantic_consumers_accept_sandboxed_path.py` | **New (AC-Sub-3).** Two tests proving `Transform.files_changed: tuple[SandboxedPath, ...]` and `ApplyContext.evidence_paths: tuple[SandboxedPath, ...]` construct without `ValidationError` when fed `SandboxedPath` instances. Mirrors the construction precedent in `tests/unit/transforms/test_transform_abc.py`. |

## Out of scope

- **`FilesystemRaceDetected` event emission** — S6-01 lands the event taxonomy and the emit infrastructure. This story raises `OSError(errno=ELOOP)` from `open()`; the consumer (S5-02 / S6-04) catches it and emits the event.
- **Helper to wrap `.open()` in a try/except that emits the event** — per `High-level-impl §Step 4 Risk 5`: "a single `with_sandbox_open(...)` helper that catches `ELOOP` and emits the event; lint rule (or grep test) asserting every `.open(...)` on a `SandboxedPath` is routed through the helper." This helper lands when the first consumer arrives (S5-02) — adding it here without a real consumer is premature (Rule 2 — Simplicity First).
- **`openat2(... RESOLVE_NO_SYMLINKS ...)` Linux-only every-component defense** — explicitly out per AC-10a. ADR-0011 commits to "second-line defense at `open()`-time `O_NOFOLLOW`", not full path-walking defense. Future hardening (if Phase 11 demands it) is a separate ADR.
- **Hardlink defense** — AC-10b documents the limitation honestly. A hardlink-aware sandbox would need inode pinning (`O_PATH` + `openat`), which is Linux-only and out of scope.
- **Special-file (FIFO / socket / device) defense** — AC-10c documents the limitation. A `os.fstat(fd) & stat.S_IFREG` post-open check could narrow the contract but introduces a TOCTOU at the fstat layer too and is out of scope.
- **`SubprocessJail` Protocol + adapters** — S4-01 / S4-02 / S4-03.
- **`Capability` tokens** + capability-construction ruff rule — S4-05. AC-17 is tracked there.
- **`with_sandbox_open` consumer-side helper + lint** — AC-16 deferred to S5-02 (first real consumer) or S4-05 (static fence layer).
- **`_check_under_jail` pure-helper extraction** — deferred until the smart constructor grows a second under-jail check (rule-of-three not met yet).
- **Property-based test fuzzing the smart constructor over synthetic Path strings** — the smart constructor is I/O-bound (`resolve(strict=True)` is a syscall); the curated edge-case ACs (AC-2/2b/3/4/4b/5/12/relative-shape) cover the symbolic state-space. Hypothesis is used only for `_flags_for_mode` (AC-7c — pure function, free fuzzing).

## Notes for the implementer

- **File-location conflict, ADR wins.** `High-level-impl.md §Step 4 features delivered` says `src/codegenie/transforms/sandbox_path.py`. `phase-arch-design.md §Component design C10` and `ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md §Consequences` both say `src/codegenie/plugins/sandbox_path.py`. Per Rule 7 (Surface conflicts, don't average), the ADR is the more recent / more load-bearing decision. Use **`src/codegenie/plugins/sandbox_path.py`**. Flag the High-level-impl discrepancy in the attempt log so a follow-up doc-fix story can reconcile (do not fix it in this story — surgical).
- **`Result` lives at `codegenie.result`, not `codegenie.types.result`.** The Phase 3 codebase ships `Result[T, E] = Ok[T] | Err[E]` (Pydantic discriminated union) at `src/codegenie/result.py:34` with `__all__ = ["Err", "Ok", "Result"]`. API: `Ok(value=...)`, `Err(error=...)`, `.is_ok()`, `.is_err()`, `.unwrap()`, `.unwrap_err()`. 19 importers across `src/` + `tests/` use this path; zero use `codegenie.types.result`. The earlier story draft's "verify via grep" instruction was avoidance of Rule 8; the answer is in the codebase, point at it directly.
- **`_forward.py` substitution is half the story.** `src/codegenie/transforms/_forward.py` was authored at S1-04 explicitly anticipating this flip — its docstring (lines 12–14) declares: "S4-04 — Replace the SandboxedPath TypeAlias with a re-export of `codegenie.plugins.sandbox_path.SandboxedPath`. Every consumer keeps importing from `codegenie.transforms`; the import path stays stable." Without the flip, this story ships dead code: `Transform.files_changed: tuple[SandboxedPath, ...]` (`transforms/transform.py:94`) and `ApplyContext.evidence_paths` (`apply_context.py:86`) still bind to `pathlib.Path`. AC-Sub-1 is non-negotiable.
- **Fence allowlist amendment is structural defense.** `tests/fence/test_transforms_module_purity.py::_FORWARD_ALLOWED` currently forbids `codegenie.plugins.*` inside `_forward.py`. The amendment to admit `codegenie.plugins.sandbox_path` is a one-line edit but it IS an architectural commitment: the one-way `transforms → transforms._forward` direction (the cycle-avoidance contract of ADR-0001) now admits a single re-export from `plugins.sandbox_path`. The inverse direction (`plugins.sandbox_path → transforms.*`) remains forbidden — guarded by AC-purity-fence. Surface this in the attempt log as an ADR-0001 amendment touch-point (not a full new ADR; the existing `_forward.py` docstring already anticipated it).
- **Pin Pydantic `BaseModel`, not `dataclass`.** AC-6a requires Pydantic. Rationale: `Transform.files_changed` and `ApplyContext.evidence_paths` are Pydantic-frozen fields. A `dataclass(frozen=True)` `SandboxedPath` forces every consumer to declare `arbitrary_types_allowed=True`. A Pydantic `BaseModel` is Pydantic-native and consumers stay unchanged. Use `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)` (the `arbitrary_types_allowed=True` is for the `_absolute: Path` field, since `Path` is not Pydantic-native).
- **`_MANDATORY_FLAGS` is the single source of truth.** Inlining `flags | os.O_NOFOLLOW` literally inside `open()` invites future drift. The module-level `_MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC` constant means a future hardening flag (e.g., `O_NOATIME`) lands in one place and `open()` picks it up automatically. AC-7 pins both `O_NOFOLLOW` and `O_CLOEXEC` bits.
- **`O_CLOEXEC` matters for Phase 3.** Phase 3 spawns subprocesses via S4-01's `SubprocessJail`. An fd held by `SandboxedPath.open()` without `O_CLOEXEC` is inherited by exec'd children, leaking the jail's fds into the sandbox. This is a one-flag-OR fix; AC-7b verifies `FD_CLOEXEC` end-to-end with `fcntl`.
- **`O_NOFOLLOW` is the heart of this story.** The TOCTOU regression (AC-8) is the test that proves the architecture's claim. A naive `open(path, mode)` implementation passes every other AC and silently fails AC-8 because Python's `open` doesn't pass `O_NOFOLLOW` by default. The fix is `os.open(path, flags | _MANDATORY_FLAGS)` followed by `os.fdopen(fd, mode)`. This is not optional polish — it is the contract.
- **`_flags_for_mode` does NOT set mandatory flags.** Keep the helper's contract narrow: it returns the base flags computed from `mode`. `open()` ORs in `_MANDATORY_FLAGS` afterward. AC-7c asserts the helper returns zero mandatory bits — this lets a test for `_flags_for_mode` itself stay deterministic and prevents an accidental double-OR if `open()` is refactored.
- **Closed-set dict beats `if/elif` for mode dispatch.** `_MODE_TO_BASE_FLAGS: Final[dict[str, int]]` plus a `try/except KeyError` is the smallest shape that gets the closed-set discipline and the unknown-mode `ValueError` (Rule 12) for free. A chained `if/elif` invites a silent fall-through to `O_RDONLY`.
- **`fd` cleanup on `os.fdopen` failure.** The `os.open` call returns a raw fd; if `os.fdopen(fd, mode)` then raises (bad mode, OOM, encoding error), the fd is leaked. The cleanest shape is `try: return os.fdopen(fd, mode); except BaseException: os.close(fd); raise`. `BaseException` (not `Exception`) covers `KeyboardInterrupt` and `SystemExit` paths. AC-fd-leak verifies the discipline.
- **Don't catch the ELOOP in `open()`.** ADR-0011 §Decision §SandboxedPath: "Consumers handle `OSError(errno=ELOOP)`." The Adapter (`SandboxedPath.open`) raises; consumers (S5-02's `NpmLockfileRecipeEngine`, S6-04's `LocalGitOps`) catch and emit `FilesystemRaceDetected`. If this story catches the exception, it silently defeats the architecture's loud-fail discipline (Rule 12 — Fail loud). AC-fail-loud's AST-scan enforces this structurally: `SandboxedPath.open()` may contain `try/finally` (for the fd cleanup above) but no `try/except`.
- **Honest framing in docstring is structural — and DUAL.** ADR-0011 §Consequences: "audit + lint" not "unforgeable"; "integrity check" not "signature." AC-15a (positive) AND AC-15b (negative) enforce this. A docstring that says "unforgeable but in-jail at construction" passes the original AC-15 but violates ADR-0011's discipline — the negative substring check forbids the wrong framing alongside the positive check. AC-15c adds the limitations enumeration so a reader can never mistake the primitive for total defense.
- **AC-10 documents real limitations, not bugs.** `O_NOFOLLOW` only affects the final path component (`man 2 open`). The story tests four uncaught vectors as living documentation:
  - AC-10a intermediate-component symlink: an attacker who can write to an intermediate directory is already a higher-level compromise;
  - AC-10b hardlink swap: hardlinks share an inode; `O_NOFOLLOW` does not block them;
  - AC-10c FIFO / socket / device replacement: `O_NOFOLLOW` defends against symlinks only;
  - AC-benign-replacement atomic real-file swap (`os.replace`): not a defense target — only symlink swap is.
  The module docstring (AC-15c) enumerates all four.
- **TOCTOU window in practice.** Between `SandboxedPath.create(jail, "file.txt")` and `sp.open("rb")`, a TOCTOU window exists. The window is small (microseconds in normal flow) but real. `O_NOFOLLOW` makes the attacker's window matter only if they can land the swap before `open()` returns; if they do, `ELOOP` fires and the workflow aborts. This is "second-line defense" not "no defense" — exactly the honest framing ADR-0011 commits to.
- **`is_relative_to` is Python 3.9+** — the codebase is on 3.11+ per CI matrix. Use it directly.
- **Strict-resolve is the first line of defense.** `Path.resolve(strict=True)` raises `FileNotFoundError` for missing files and follows symlinks. After resolution, `is_relative_to(jail.resolve(strict=True))` is the in-jail check. Both jail and candidate are resolved with `strict=True` so the comparison is between fully-canonicalized paths. AC-2b proves the both-sides discipline via a symlinked-jail metamorphic test (catches macOS `/var → /private/var` half-resolved-impl regressions).
- **Reject absolute `relative` before any filesystem call.** If `Path(relative).is_absolute()`, return `Err(reason="absolute")` immediately. Otherwise `(jail_abs / "/etc/passwd")` evaluates to `"/etc/passwd"` (pathlib drops the LHS) and the resolve+is_relative_to check correctly rejects — but the `attempted_path` payload is wrong, and a future maintainer who refactors `(jail_abs / rel_path)` may break this subtle invariant. Eager rejection is loud and uncoupled.
- **Defer `_check_under_jail` extraction.** The pure `is_relative_to` check inside `create()` is one line. Extracting it into a `_check_under_jail(jail_abs, candidate_abs)` helper is tempting for testability but currently has one call site. Three-similar-lines threshold (Rule 2) not met. **Trigger condition for future extraction:** if `create()` ever grows a second under-jail check (e.g., per-component symlink rejection if Phase 11 ships `openat2(RESOLVE_NO_SYMLINKS)`), extract then. Not before.
- **Resist a `SandboxedPath` registry / strategy pattern.** This is a primitive value type with one shape; there is no plugin family to support. Adding `@register_sandboxed_path_kind(...)` is over-engineering. The plugin/strategy pattern lives upstream at the recipe-engine layer, not at the value-type layer.
- **Capability-construction lint rule is deferred (AC-17).** ADR-0011 §Consequences names `tooling/ruff_rules/no_capability_construction.py` as the lint that enforces single-mint-point for capability tokens. `SandboxedPath(...)` direct construction outside `sandbox_path.py` + `tests/` bypasses the smart constructor and the audit trail. The rule belongs in S4-05 (Capability Fence). Tracking entry in the attempt log: `AC-17 deferred to S4-05`.
- **AC-16 deferral acceptance.** S4-05 may extend the static-fence story with a consumer-side `with_sandbox_open` helper + lint rule. Or a future S5-02 story may land it inline. Either way, this story does not introduce a helper without a real consumer (Rule 2). Track as `AC-16 deferred to S5-02 or S4-05`.
- **Effort sizing reality check.** Original S sizing pre-hardening. After hardening, the load-bearing ACs are AC-7/7a/7b/7c (flag plumbing), AC-8 (TOCTOU regression with confidentiality assertion), AC-Sub-1/Sub-2/Sub-3 (forward-shim flip + fence + consumer round-trip), AC-fd-leak, AC-fail-loud (AST scan), AC-purity-fence (new fence file), and AC-15a/15b/15c (docstring dual discipline + limitations). The Pydantic-shape pin removes one branch of optionality. S/M is the honest size; if the implementer discovers a Phase-3 `Result` API surprise or a Pydantic-private-attr quirk on `_absolute`, surface in the attempt log and consider promoting to M.
