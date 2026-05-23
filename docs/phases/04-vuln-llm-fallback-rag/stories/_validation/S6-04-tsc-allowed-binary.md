# Validation report — S6-04 — `./node_modules/.bin/tsc` admitted to `ALLOWED_BINARIES`

**Story:** [`S6-04-tsc-allowed-binary.md`](../S6-04-tsc-allowed-binary.md)
**Validated:** 2026-05-22
**Verdict:** **HARDENED**

The story is mechanically small — one allowlist row + tests — but carries a
load-bearing structural defense (the bare-name closed-set discipline). The
critics surfaced two **block-severity** clusters: (1) the TDD plan is
uncompilable against the real API (wrong signature, wrong error name, wrong
return field, missing `await`); (2) the story's "admit `./node_modules/.bin/tsc`
as a path" decision **contradicts** the bare-name closed-set convention
asserted across the codebase and pinned by closure-regression tests. Both are
fixable in the story, but (2) requires a small ADR amendment downstream
(analogous to S1-05's flagging of ADR-0003 staleness).

The hardened story (a) corrects the API/test errors, (b) reframes the
admission as a bare-name `"tsc"` row (matching the bubblewrap precedent's
"short name IN, paths/aliases OUT" discipline), (c) routes the narrow-
admission discipline to the caller (`TypecheckTypescriptSignal`, S6-05) via
the existing `env_extra={"PATH": ...}` seam — Open/Closed at the file
boundary; the allowlist stays uniform, (d) mirrors the Phase-3
`test_allowlist_phase3.py` 8-AC family pattern in a single new
`tests/unit/exec/test_allowlist_phase4.py`, and (e) flags ADR-04-0015 +
`High-level-impl.md` §175 for amendment.

The verdict is HARDENED not RESCUE because the story's underlying intent
(make `tsc` callable so S6-05 can ship) is sound; only the path/convention
decision and the API in the TDD plan needed correction.

---

## Stage 1 — Context Brief

| Aspect | Finding |
|---|---|
| What the story promises | Admit `./node_modules/.bin/tsc` to `ALLOWED_BINARIES`; assert other tsc paths rejected. |
| What the phase exit criteria demand | S6-05 must be unblocked — the `TypecheckTypescriptSignal` collector must be able to invoke the TS type-checker through `run_allowlisted`. |
| What the arch + ADRs constrain | ADR-04-0015 §Pattern-fit (line 44) explicitly says "**only one ADR amendment to `ALLOWED_BINARIES`** … following the Phase 3 ADR-0012 pattern." Phase 3 ADR-0012 admits **bare names**. ADR-04-0015's §Decision text saying "add `./node_modules/.bin/tsc`" *internally contradicts* its own §Pattern-fit. |
| Source-of-truth files | `src/codegenie/exec/__init__.py` (lines 105–130 `ALLOWED_BINARIES`; lines 245–247 docstring "must be a bare binary name"); `tests/unit/exec/test_allowlist_phase3.py` (lines 53–253 — the 8-AC family pattern); `tests/unit/test_exec.py` (lines 311–406 — closed-set regression + bubblewrap-long-name-disallowed precedent); CLAUDE.md §"Subprocess discipline". |

---

## Stage 2 — Critic findings (consolidated)

### Severity legend
- **block** — story cannot ship as-is.
- **harden** — real-but-fixable weakness.
- **nit** — minor wording.

### Cluster A — API + test-collection failures (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| T-1, C-Coverage-2 | block | TDD imports `AllowlistViolation`; real symbol is `DisallowedSubprocessError` in `codegenie.errors` | Test-Quality + Coverage |
| T-2, C-Coverage-1 | block | `run_allowlisted` is `async`, takes `argv: list[str]`, requires `timeout_s` kwarg, returns `ProcessResult.returncode` (not `exit_code`) — story's tests are sync, split argv0/args positionally, miss `timeout_s`, and read `exit_code` | Test-Quality + Coverage |
| T-3 | block | Positive test uses a real shim script — passes even under "admits everything" mutation. Mirror Phase-3 AC-5's spawn-spy pattern. | Test-Quality |
| T-4 | block | Negative test missing `spy.assert_not_awaited()` — mutation that defers the allowlist check until after spawn slips through | Test-Quality |

**Synthesis:** the entire TDD plan needs rewriting to async-with-real-API and to mirror the Phase-3 family pattern. Editor rewrites both test stubs + adds spawn-spies.

### Cluster B — Convention conflict on the allowlist element shape (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-1, D-1, D-2 | block | Story admits a *path* into a `frozenset[str]` of **bare names**. `__init__.py:245-247` docstring says "must be a bare binary name." Every existing entry is a bare name. The bubblewrap precedent (`test_exec.py:397-406`) explicitly codifies "short bare name IN; canonical long name OUT" — admitting the path inverts this. | Consistency + Design-Patterns |
| C-Consistency-1 (cont.) | block | Phase-3 path-traversal regression (`test_allowlist_phase3.py:156-176`) parametrizes `[f"./{b}" for b in NEW_BINARIES]` as **must-raise**. Admitting `./node_modules/.bin/tsc` either contradicts the regression or forces a one-off exemption that weakens the structural defense. | Consistency |
| D-1 (cont.) | block | Sum-type discipline (CLAUDE.md §load-bearing-commitments — Phase 2 ADR-0006) is silently violated: `frozenset[str]` becomes "bare-name OR repo-local path" with no type-level distinction. | Design-Patterns |
| D-2 | block | The OCP-compliant factoring is **caller-side narrowing**: admit bare `"tsc"`; the signal owns `env_extra={"PATH": str(repo / "node_modules" / ".bin")}`. `run_allowlisted` stays uniform; the closure-equality structural defense survives. | Design-Patterns |

**Synthesis (Consistency > Design > Coverage priority):**

ADR-04-0015 internally contradicts itself: §Decision says "add `./node_modules/.bin/tsc`"; §Pattern-fit (line 44) says "only one ADR amendment to `ALLOWED_BINARIES`" + "following the Phase 3 ADR-0012 pattern" (bare names); §Tradeoffs row 1 calls the entry "content-hashed" which has zero plumbing.

Per Global Rule 7 ("Surface conflicts, don't average them"), the validator picks the more-tested convention (bare names + bubblewrap precedent + path-traversal regression + docstring + sum-type discipline — five independent assertions) over the ADR-04-0015 §Decision text's "path" wording (one assertion that contradicts the rest of the ADR's own pattern claims). The story is reframed to admit **bare `"tsc"`**; narrow-admission discipline moves to the caller via the existing `env_extra` seam.

ADR-04-0015 §Decision and §Tradeoffs are flagged for amendment in the same way S1-05 flagged ADR-0003 §Decision and final-design §2.1 as stale. The executor logs this and updates both — the path-string "content-hashed" framing is replaced with bare-name + caller-side PATH-scoping.

### Cluster C — Missing closure-test updates (block)

| ID | Severity | Title | Source |
|---|---|---|---|
| T-5, C-Consistency-3, D-6 | block | Story names `tests/unit/exec/test_allowlist_closure.py` — **file does not exist**. Real closure-equality assertions live at **three** sites: `tests/unit/test_exec.py:352`, `tests/unit/exec/test_allowed_binaries.py`, `tests/unit/exec/test_allowlist_phase3.py:72-76`. All three must be updated to 17 entries. Story leaves this hole open. | Test-Quality + Consistency + Design-Patterns |

**Synthesis:** Editor enumerates all three closure sites in `Files to touch` and `Implementation outline`, with the OCP-friendly chain form `EXPECTED_TOTAL_PHASE_3 | {"tsc"}` so the next phase's amendment is a one-row delta on top of this one.

### Cluster D — Missing parametric coverage (Phase-3 family-pattern parity) (block/harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| T-6 | block | No ADR cross-document gate test (Phase-3 AC-4 equivalent at `test_allowlist_phase3.py:116-129`) | Test-Quality |
| T-7 | block | No `codegenie.exec` module-docstring assertion (Phase-3 AC-2 equivalent at `test_allowlist_phase3.py:97-108`) | Test-Quality |
| T-8 | harden | No `_RUNNING_PROCS` weakref-cleanup test (Phase-3 AC-8 equivalent at `test_allowlist_phase3.py:236-252`) | Test-Quality |
| T-9 | harden | Path-traversal parametric is hand-picked, not derived. Add `tsc.bat`, symlink escape, `.bin/../usr/bin/tsc` cases. | Test-Quality |
| D-5 | harden | Phase 3 uses **one** file (`test_allowlist_phase3.py`) with 8 section-banner ACs. Story forks the convention with two files (`test_allowlist_admits_tsc.py`, `test_allowlist_rejects_system_tsc.py`). Match Phase-3 with `test_allowlist_phase4.py` — Open/Closed at the file boundary. | Design-Patterns |
| T-11 | nit | Property-style "delta = exactly one entry vs Phase-3 closed set" test — single mutation barrier | Test-Quality |

**Synthesis:** Editor consolidates the test plan into a single `tests/unit/exec/test_allowlist_phase4.py` mirroring the Phase-3 file's 8-AC structure, plus the delta-from-Phase-3 property test as a ninth assertion.

### Cluster E — Stale ADR claims (block/harden)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-2, C-Coverage-5, D-4 | block | ADR-04-0015 §Decision (line 27), §Tradeoffs row 1 (line 35), and §Consequences (line 51) all claim "content-hashed per major Node version per Phase 3 ADR-0012's amendment pattern." Phase-3 ADR-0012 admits **bare names with no hashing** — no such pattern exists. | Consistency + Coverage + Design-Patterns |
| C-Consistency-4 | harden | `High-level-impl.md` §175 says "ADR-04-0001 amends `ALLOWED_BINARIES`" — the amending ADR is ADR-04-0015 (typo). | Consistency |

**Synthesis:** Editor adds an explicit AC for both amendments. ADR-04-0015 amendment: replace "content-hashed per major Node version" framing with "bare name `tsc`; caller-side PATH-scoping for narrow-admission discipline." `High-level-impl.md` amendment: ADR-04-0001 → ADR-04-0015.

### Cluster F — AC wording bugs (harden/nit)

| ID | Severity | Title | Source |
|---|---|---|---|
| C-Consistency-5, C-Coverage-7 | harden | AC-1 "alphabetically ordered consistent with surrounding entries" is empirically false — `ALLOWED_BINARIES` is phase-grouped, not alpha. | Consistency + Coverage |
| C-Coverage-6 | harden | AC-6 "no edits to `run_allowlisted` logic" reads as "no code changes" — but the closure-test updates ARE code changes. Reword to "no changes to spawn / env / timeout / allowlist-check invariants of `run_allowlisted`." | Coverage |
| C-Consistency-7 | nit | AC-6's "AST-walking diff check (or simple `git diff --stat`)" invents a verification mechanism that has no implementation. Reword to "diff touches only `src/codegenie/exec/__init__.py` `ALLOWED_BINARIES` block + the new/updated test files." | Consistency |

### Cluster G — YAGNI flag forward (nit)

| ID | Severity | Title | Source |
|---|---|---|---|
| D-7 | nit | Don't build a `NarrowAdmissionPolicy` registry now (single instance — Rule 2). But note the YAGNI line so the **third** repo-local binary (Phase 5+) triggers the registry refactor, not a third hack. | Design-Patterns |

---

## Stage 3 — Research

**Not invoked.** No findings tagged `NEEDS RESEARCH` — every issue resolved by referencing already-known codebase patterns (the Phase-3 family pattern in `test_allowlist_phase3.py`, the bubblewrap precedent in `test_exec.py`, and S1-05's ADR-staleness-amendment precedent).

---

## Stage 4 — Edits applied (before / after)

### Edit 1 — `Validation notes` block inserted under header (new)

A six-line block summarizing the convention-shift resolution, the ADR-04-0015
amendment flag, and the Phase-3 file-naming alignment.

### Edit 2 — `**Status:** Ready` → `**Status:** HARDENED`

Matches the validator convention (see S1-05).

### Edit 3 — Goal rewritten

**Before (line 28):** "Add `./node_modules/.bin/tsc` to the `ALLOWED_BINARIES`
frozenset (content-hashed per major Node version where applicable per Phase-3
ADR-0012 pattern) so `run_allowlisted` accepts it; assert via a deliberate-
violation fixture that other `tsc` paths (`/usr/local/bin/tsc`, plain `tsc`
resolved by PATH) remain rejected."

**After:** "Admit bare-name **`tsc`** (matching the existing bare-name +
bubblewrap-precedent convention) to the `ALLOWED_BINARIES` frozenset so
`run_allowlisted(['tsc', ...], cwd=repo_root, env_extra={'PATH': ...},
timeout_s=...)` accepts it; assert via the Phase-3 path-traversal regression
family that path-shaped invocations (`./node_modules/.bin/tsc`,
`/usr/local/bin/tsc`, `./tsc`) raise `DisallowedSubprocessError`; flag
ADR-04-0015 + `High-level-impl.md` §175 for amendment (the 'admit the path'
+ 'content-hashed per major Node version' framing is internally contradictory
and has no plumbing). Narrow-admission discipline (only the repo-local
`./node_modules/.bin/tsc` ever runs) lives caller-side in S6-05 via
`env_extra={'PATH': str(repo / 'node_modules' / '.bin')}`."

### Edit 4 — All 7 ACs rewritten + 4 new ACs added (11 total)

Mirror Phase-3 `test_allowlist_phase3.py` 8-AC family pattern + ADR-amendment
ACs. Each AC tagged with `(validator: hardened — <citation>)` per S1-05
convention. See edited story for the full list.

### Edit 5 — TDD plan rewritten

Replace both uncompilable test stubs with async-with-real-API tests inside a
single new file `tests/unit/exec/test_allowlist_phase4.py`. Mirror Phase-3's
8-section banner structure + add the delta-from-Phase-3 property assertion.

### Edit 6 — `Files to touch` enumerated

Adds the three closure-update sites (`tests/unit/test_exec.py`,
`tests/unit/exec/test_allowed_binaries.py`,
`tests/unit/exec/test_allowlist_phase3.py`), the two doc amendments
(`docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-*.md`,
`docs/phases/04-vuln-llm-fallback-rag/High-level-impl.md`), and renames the
test file to `test_allowlist_phase4.py`.

### Edit 7 — `Notes for the implementer` expanded

Adds:
- The ADR-04-0015 amendment guidance (mirror S1-05's ADR-0003 flagging
  approach: log in attempt log, flag for amendment per Rule 7).
- The caller-side narrow-admission design pattern note pointing at the
  Phase-3 `env_extra` seam already in `run_allowlisted`'s signature.
- The YAGNI flag (D-7): don't build a `NarrowAdmissionPolicy` registry
  now; the third repo-local binary triggers it.

---

## Final verdict

**HARDENED** — story edited in place; ready for `phase-story-executor`. The
executor should:

1. Log the ADR-04-0015 + `High-level-impl.md` §175 amendments in the
   attempt log per Rule 7 (analogous to S1-05's handling of ADR-0003
   staleness).
2. Land the two doc amendments **in the same PR** as the code change so
   the closure-equality assertions land alongside the corrected
   surrounding text.
3. Verify the closure-count delta sticks at exactly +1 across all three
   closure sites.
