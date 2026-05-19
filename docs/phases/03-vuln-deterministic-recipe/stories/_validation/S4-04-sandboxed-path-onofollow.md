# Validation report — S4-04 `SandboxedPath.create` + `O_NOFOLLOW` + TOCTOU defense

**Verdict:** HARDENED
**Validated:** 2026-05-19
**Story file:** [`../S4-04-sandboxed-path-onofollow.md`](../S4-04-sandboxed-path-onofollow.md)

## Summary

Four critics surfaced **13 BLOCK-grade structural issues** plus ~24 HARDEN-grade mutation-survival gaps and a handful of nits. All BLOCKs are inline-patchable; no `phase-story-writer` re-run needed.

Most consequential resolutions:

1. **Wrong `Result` import path.** Story prescribed `codegenie.types.result`; actual home is `codegenie.result`. Rule 11 + Rule 8 win. Outline rewritten; surface assertion added to AC-1.
2. **Missing `_forward.py` substitution + fence amendment.** The Phase-3-Step-1 shim at `src/codegenie/transforms/_forward.py:39` aliases `SandboxedPath: TypeAlias = pathlib.Path` and its docstring explicitly declares S4-04's contract to flip it. Story originally omitted the flip — meaning a literal implementation would ship dead code. Added AC-Sub-1 (flip), AC-Sub-2 (fence allowlist amendment), and AC-Sub-3 (Pydantic consumer round-trip).
3. **`SandboxedPath` shape ambiguity.** Outline allowed `dataclass(frozen=True)` OR `BaseModel`. The shape ripples to existing Pydantic consumers (`Transform.files_changed`, `ApplyContext.evidence_paths`). Pinned to `BaseModel(frozen=True, extra="forbid", arbitrary_types_allowed=True)` per `Ok`/`Err`/`PathEscape` precedent.
4. **AC-7 / AC-5 / AC-3 / AC-6 mutation-trivial.** Original tests checked `flags & O_NOFOLLOW` only (a mutant ORing `O_RDWR` into read-mode survives); used `reason in {missing, not_resolvable}` disjunction (collapses two branches); only asserted `reason` discriminant without `attempted_path` payload; used `pytest.raises((AttributeError, Exception))` catch-all. All rewritten to exact-flag-mask, exact-reason, payload-pinned, and exact-exception-class assertions respectively.
5. **AC-15 docstring discipline was one-sided.** ADR-0011 §Consequences mandates dual discipline ("audit + lint" not "unforgeable"; "integrity check" not "signature"). Added AC-15b (banned substrings: `"in-jail forever"`, `"unforgeable"`, `"makes illegal states unrepresentable"`, `"signature"`) and AC-15c (limitations enumerated).
6. **Pure-function discipline + fd hygiene.** Added `_MANDATORY_FLAGS: Final[int] = os.O_NOFOLLOW | os.O_CLOEXEC` single-source-of-truth constant; `O_CLOEXEC` closes the subprocess-fd-inheritance vector Phase 3 actually has (S4-01 spawns subprocesses). Added AC-fd-leak (fd closed on `os.fdopen` failure) and AC-fail-loud (AST-scan asserts `open()` catches no exceptions — ADR-0011 §Decision "consumers handle ELOOP").

The hardened story keeps the Goal and Out-of-scope shape intact; it tightens ACs so the executor's validator pass can fail on a wrong implementation, and pulls in the seam-wiring (`_forward.py` substitution + fence allowlist + Pydantic consumer compat) that ADR-0001 + the existing shim's docstring already anticipated.

## Context Brief

- **What the story promises:** `src/codegenie/plugins/sandbox_path.py` with `SandboxedPath` (Pydantic frozen, `.create() -> Result`, `.open()` always `O_NOFOLLOW`) + `PathEscape` typed-error variant + unit tests including the load-bearing TOCTOU test.
- **Phase exit criterion this serves:** Goal G1 (subprocess + filesystem isolation primitives) on both substrates. The TOCTOU defense is the ADR-0011 "second-line defense" architecture commitment.
- **Sibling-family lineage:** This is the **1st instance of its kind** — `SandboxedPath` is a primitive value type, not a member of a parser/probe/adapter family. It IS the kernel that S5-02, S6-04, S4-02/03 jail-cwd binds will consume. Open/Closed seam at the producer side, not the consumer side.
- **Arch + ADR constraints:**
  - ADR-0011 (honest framing): "in-jail at construction" + `O_NOFOLLOW` second-line defense; consumers handle `OSError(errno=ELOOP)`; framing is dual (use the right phrases AND avoid the wrong ones).
  - ADR-0010 (domain modeling discipline): Pydantic frozen + `extra="forbid"` for value types; closed `Literal` sums.
  - ADR-0001 (one-way `transforms → transforms._forward`): amended by this story to admit one re-export from `codegenie.plugins.sandbox_path`. The amendment is anticipated by the `_forward.py` docstring (lines 12–14, authored at S1-04).
  - ADR-0006 (Hexagonal `SubprocessJail`): consumer of `SandboxedPath.cwd`. S4-01 commits the typename.
- **CLAUDE.md commitments:** Newtype identifiers (`SandboxedPath` IS one); Functional core / imperative shell (mostly applicable to `create()` — pure helper deferred per Rule 2); Extension by addition (extend `_FORWARD_ALLOWED`, don't fork; add `_MANDATORY_FLAGS` constant for future hardening); Match existing convention (Pydantic BaseModel shape, alphabetized `__all__`, `codegenie.result`).
- **Codebase precedents read:**
  - `src/codegenie/result.py` — Result API + `__all__` shape;
  - `src/codegenie/transforms/_forward.py` — the substitution target;
  - `src/codegenie/transforms/{transform,apply_context,outcomes}.py` — existing Pydantic consumers of `SandboxedPath`;
  - `tests/fence/test_transforms_module_purity.py` — the fence to amend;
  - `_validation/S4-01-…md`, `_validation/S4-02-…md`, `_validation/S4-03-…md` — sibling hardening patterns (typed-error fence, fd-leak, stateless ACs).

## Stage 2 — Critic reports

Four critics ran in parallel. Severity legend: `block` = must rewrite before executor; `harden` = real gap a mutant would survive; `nit` = small polish.

### Critic A — Coverage

| # | Severity | Title |
|---|---|---|
| COV-01 | block | Missing AC: substitute `_forward.SandboxedPath` alias and amend module-purity fence |
| COV-02 | block | Missing AC: existing Pydantic consumers must still accept `SandboxedPath` instances |
| COV-03 | block | Wrong `Result` import path; no AC pins the actual surface |
| COV-04 | harden | AC-7 mode set missing `x` / `xb`; assertion doesn't check flag composition for write modes |
| COV-05 | harden | No AC for fd-leak on `os.fdopen` failure after `os.open` succeeds |
| COV-06 | harden | AC-1 `__all__` discipline ambiguous ("exports exactly" not pinned) |
| COV-07 | harden | AC-15 docstring substring check passes mutant docstrings |
| COV-08 | harden | No AC for jail-itself-is-a-symlink case |
| COV-09 | harden | No AC for `relative` that is absolute, empty, or `"."` |
| COV-10 | harden | AC-10 "known limitations" doesn't extend to hardlinks and special-file swaps |
| COV-11 | harden | AC-11 round-trip is empty pre-alias-flip |
| COV-12 | nit | AC-8/AC-9 should assert benign file-replacement is permitted (not a defense target) |

### Critic B — Test Quality (mutation-resistance)

| # | Severity | Title |
|---|---|---|
| TQ-01 | block | AC-3 `attempted_path` payload unverified — mutant emitting wrong path passes |
| TQ-02 | block | AC-5 `reason in {missing, not_resolvable}` disjunction is mutation-trivial |
| TQ-03 | block | AC-7 checks `O_NOFOLLOW` bit only — mutant ORing `O_RDWR` into read modes survives |
| TQ-04 | block | AC-6 `pytest.raises((AttributeError, Exception))` accepts any exception |
| TQ-11 | block | AC-2 happy-path may flake on macOS due to `/var → /private/var` `tmp_path` symlink |
| TQ-05 | harden | AC-8 doesn't verify the symlink target was never opened (confidentiality assertion) |
| TQ-06 | harden | AC-13 chained frozen + extra-forbid checks mask each other on mutants |
| TQ-07 | harden | AC-15 docstring substring check is one-sided; banned-substring side missing |
| TQ-08 | harden (NEEDS RESEARCH→resolved) | No property-based test for `_flags_for_mode` |
| TQ-09 | harden | No test for unknown-mode `_flags_for_mode("q")` failure mode |
| TQ-10 | harden | No fd-leak test when `os.fdopen` raises |
| TQ-12 | harden | AC-11 import path may be wrong; binding test doesn't catch unflipped alias |
| TQ-13 | harden | No test that `.create()` rejects a non-existent jail |
| TQ-14 | harden | No metamorphic test confirming jail-resolution is idempotent |

### Critic C — Consistency

| # | Severity | Title |
|---|---|---|
| C-1 | block | Wrong Result import path — `codegenie.types.result` does not exist |
| C-2 | block | `_forward.py` substitution omitted from Files-to-touch and ACs |
| C-3 | block | Fence `_FORWARD_ALLOWED` allowlist amendment missing — CI-gating |
| C-4 | harden | SandboxedPath shape unspecified — propagates Pydantic-compat risk |
| C-5 | harden | AC-11 round-trip empty unless S4-01's `cwd: SandboxedPath` resolves to the new class |
| C-6 | harden | Cycle-defense pin missing — `sandbox_path.py` import allowlist not declared |
| C-7 | harden | AC-15 banned-substring side missing — honest-framing discipline is dual |
| C-8 | harden | Functional-core / imperative-shell split not extracted in `create()` |
| C-9 | harden | Sibling-parity ACs missing — fd-leak / cleanup-on-exception / typed-error fence |
| C-10 | harden | AC-1 module-surface assertion should match `__all__` convention |
| C-11 | harden | Honest framing missing from Goal section (only at docstring level) |
| C-12 | nit | Implementation outline step 1 should not require a grep — answer in `src/codegenie/result.py` |

### Critic D — Design Patterns

| # | Severity | Title |
|---|---|---|
| DP-06 | block | Wire the `_forward.SandboxedPath` substitution — story is dead code without it |
| DP-01 | harden | Pin Pydantic `BaseModel` for `SandboxedPath` (not `dataclass`) |
| DP-02 | harden | Extract `_MANDATORY_FLAGS` as single source of truth |
| DP-03 | harden | Add `O_CLOEXEC` to every fd (subprocess-inheritance hygiene) |
| DP-04 | harden | Test `_flags_for_mode` as a pure helper |
| DP-05 | harden | Module purity fence for `sandbox_path.py` |
| DP-07 | harden | Surface capability-construction lint as deferred AC (AC-17) |
| DP-08 | harden | Closed-set discriminator: pin `PathEscape.reason` test parity with the Literal |
| DP-09 | nit | Don't extract `_check_under_jail` yet (Rule 2; single call site) |
| DP-10 | nit | Assert `is_err()` before `.unwrap_err()` in negative-path tests |
| DP-11 | nit | `PathEscape` shape is already well-formed (no change) |
| DP-12 | nit | No DIP/port-adapter abstraction for `SandboxedPath` itself (Rule 2) |

## Stage 3 — Researcher

**Skipped** (Hypothesis precedent confirmed in-codebase). TQ-08 was tagged `NEEDS RESEARCH` for hypothesis idiomatic pattern. Codebase has hypothesis usage in Phase 1 / Phase 2 (e.g., `tests/unit/probes/...` and parser tests); the established import + decorator pattern (`from hypothesis import given, strategies as st`) is mirrored in the AC-7c property test. Researcher fan-out not required.

## Stage 4 — Synthesis + edits applied

**Conflict-resolution decisions:**

- **C-1 / COV-03 (Result import path):** Codebase wins. Outline rewritten to `from codegenie.result import Err, Ok, Result`; "verify via grep" hedging dropped; AC-1 adds a surface-source assertion proving `codegenie.types.result` is NOT imported.
- **C-2 / COV-01 / DP-06 (forward-shim substitution):** ADR-anticipated wins. The `_forward.py` docstring (S1-04, lines 12–14) explicitly declares this story's contract to flip the alias. AC-Sub-1 added; Files-to-touch entry added; Notes-for-implementer §`_forward.py is half the story`.
- **C-3 / COV-01 (fence amendment):** CI-gating; must land. AC-Sub-2 added with the exact frozenset; attempt-log note required as ADR-0001 amendment touch-point (not a new ADR — the existing `_forward.py` docstring anticipated it).
- **DP-01 / C-4 (Pydantic shape):** Pinned to `BaseModel(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. Matches `Ok`/`Err`/`PathEscape` precedent and keeps existing consumer Pydantic models unchanged. The `dataclass` alternative removed from the outline.
- **TQ-08 / DP-04 / AC-7c (hypothesis):** Resolved via in-codebase precedent; helper `_flags_for_mode` tested with `@given(mode=st.sampled_from(...))`. Helper does NOT set `_MANDATORY_FLAGS` (keeps its contract narrow; `open()` ORs them in).
- **C-8 / DP-09 (`_check_under_jail` extraction):** Rule 2 (Simplicity First) wins over Functional-core / imperative-shell stylistic. Single call site; defer. Captured in Notes-for-implementer with the trigger condition for future extraction.
- **DP-07 (capability-construction lint, AC-17):** Deferred to S4-05 mirroring AC-16 handling. ADR-0011 §Consequences names the exact rule path; S4-05 is the canonical fence-rule story.
- **C-7 / TQ-07 / AC-15 (banned substrings):** ADR-0011 §Consequences's dual-discipline wording is structural. AC-15 split into AC-15a (positive), AC-15b (banned), AC-15c (limitations enumerated).
- **TQ-11 / AC-2b (macOS `tmp_path` symlink hazard):** Added metamorphic AC-2b — `jail` as a symlink to `real_jail`; `.absolute` must resolve under `real_jail`. Catches half-resolved implementations.
- **COV-09 / AC-relative-shape:** Pinned `""` and `"."` → `Ok(jail)`; absolute relative → `Err(reason="absolute")` (eager rejection before any filesystem call — Rule 12 fail-loud, plus correct `attempted_path` payload).
- **COV-10 / AC-10b / AC-10c (hardlink + special-file limitations):** Added as living tests + docstring enumeration (AC-15c).
- **DP-08 / AC-sum-type-coverage:** `typing.get_args(PathEscape.model_fields["reason"].annotation)` introspection asserts every literal has a producer in the test file. Prevents reason-creep without coverage.
- **C-9 / AC-fd-leak / AC-fail-loud (sibling parity):** Added two ACs mirroring S4-02 / S4-03 hardening patterns. fd cleanup on `os.fdopen` failure; AST-scan asserts `open()` has no `except` clause.
- **DP-05 / AC-purity-fence:** New fence file `tests/fence/test_plugins_sandbox_path_purity.py` with allowlist = `{__future__, errno, os, pathlib, typing, pydantic, codegenie.result}`. Closes the cycle direction `plugins.sandbox_path → transforms.*` (ADR-0001 + ADR-0013 precedent).

**Story edits applied (summary):**

1. **Validation notes** block prepended under header; Status `Ready` → `HARDENED`; Effort `S` → `S/M`; Depends-on extended to `_forward.py` shim; ADRs honored extended to ADR-0010 + ADR-0001 (amended).
2. **Goal** rewritten to lead with the honest-framing sentence (per C-11); enumerates the 7-step ship list including `_forward.py` flip and two test files; pins Pydantic shape.
3. **AC block** replaced wholesale. ~25 ACs across 6 groups: Module surface, Smart-constructor happy paths, Smart-constructor error paths, Immutability + Pydantic discipline, `open()` mandatory flags + mode handling, TOCTOU load-bearing tests, Honest-framing living tests, Cross-story wiring (`_forward.py` + fence + Pydantic consumers), Static surface fences, Docstring dual discipline, Deferred (AC-16 + AC-17 tracking).
4. **Implementation outline** rewritten with the correct `Result` import path; `_MANDATORY_FLAGS` constant; closed-dict `_MODE_TO_BASE_FLAGS`; `_flags_for_mode` `try/except KeyError → ValueError` shape; `os.fdopen` `except BaseException: os.close(fd); raise` cleanup pattern; `_forward.py` substitution step; fence-amendment step; new purity-fence file step; AC-Sub-3 round-trip test file step.
5. **TDD plan** sketches rewritten with mutation-resistant assertions: exact-flag-mask per mode; payload-pinned `PathEscape.attempted_path` check; split frozen + extra-forbid tests; AST-scan of `open()` exception handlers; AC-Sub-1/Sub-2/Sub-3 sketches; hypothesis test for `_flags_for_mode`; alias-flip identity check.
6. **Files to touch** table extended from 2 rows to 6 rows: production file + `_forward.py` edit + two fence files + unit tests + consumer-side tests.
7. **Out of scope** extended with hardlink defense, special-file defense, `_check_under_jail` extraction trigger, smart-constructor property-based fuzzing (with rationale).
8. **Notes for the implementer** expanded with: `_forward.py is half the story`, fence-amendment-as-architectural-commitment, Pydantic-shape pinning, `_MANDATORY_FLAGS` + `O_CLOEXEC` rationale, helper-contract narrowness, closed-dict-over-if-elif, fd cleanup pattern, `BaseException`-not-`Exception`, dual-discipline framing, eager absolute-rejection, `_check_under_jail` trigger condition, registry-pattern resistance, AC-17 / AC-16 deferral tracking, effort sizing reality check.

## Verdict

**HARDENED.** Three pre-existing BLOCKs (Result path, `_forward.py` flip, fence amendment) would have caused the executor to either (a) create a non-existent module path, (b) ship dead code, or (c) break the CI-gating fence. The remaining ten BLOCKs collapsed mutation-trivial ACs to exact-assertion form. Twenty-four HARDEN findings raised the ceiling on mutation resistance (exact flag composition, banned-substring framing discipline, fd hygiene, hardlink/FIFO limitation documentation, sum-type coverage introspection). Two ACs (AC-16, AC-17) explicitly deferred with attempt-log tracking entries; one (`_check_under_jail` extraction) recorded as a future trigger condition.

Story is now executor-ready.
