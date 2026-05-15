# Validation report — S1-06 `ALLOWED_BINARIES` ten-binary Phase 2 extension

**Story:** [`../S1-06-allowed-binaries-extension.md`](../S1-06-allowed-binaries-extension.md)
**Validated:** 2026-05-15 (Pass 1 + Pass 2 same day)
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED**

## Summary

S1-06 extends `src/codegenie/exec.py` `ALLOWED_BINARIES` from `{"git", "node"}` to a twelve-entry final set, adding the ten Layer B/C/G tools named by Phase 2 `02-ADR-0001`. Pass 1 (light-touch, earlier 2026-05-15) added AC-9 (cross-file regression) and AC-10 (mandatory ADR amendment). Pass 2 (this report, same-day) ran the full four-critic audit and closed seven additional gaps.

**Pass 2 findings: 2 block-tier, 5 harden-tier, 3 nit-tier observations.** All closed in place:

- **AC-2 rewrite** — unverifiable prose deferral → pytest meta-test parsing `02-ADR-0001.md` (Coverage F2, **block**).
- **AC-11 added** — `assert "02-ADR-0001" in codegenie.exec.__doc__` pins the docstring update from Implementation outline step 2 (Coverage F3, **block**).
- **AC-12 added** — env-strip parametric over `(binary, sensitive_key)` ∈ `{docker, semgrep} × keys` (Test-Quality M2, harden).
- **AC-13 added** — `_RUNNING_PROCS` weakref-cleanup assertion per new binary (Test-Quality M5, harden).
- **AC-14 added** — path-traversal regression `[/usr/bin/{b}, ./{b}]` over 10 new binaries (Test-Quality M11 + Coverage F6, harden).
- **AC-15 added** — closed-set negative list extended with `["bwrap", "bubblewrap", "eval", "exec", "kill", "chmod", "chown", "dd", "nc"]`. **Supersedes Pass-1 AC-9's "parametrize list unchanged" instruction.** (Design-Patterns F1 + Test-Quality M9, harden).
- **AC-10 extended** — also amends 02-ADR-0001 §Tradeoffs row 2 (CVE feeds count) and adds §Consequences bullet pinning the `bwrap`-not-allowlisted wrapper-pattern exception (Consistency C2 + C4, harden).
- **AC-16 added** — `AWS_*` prefix-match coverage carried forward for a new binary (Coverage F5, harden).

Stage 3 (research) **skipped** — no `NEEDS RESEARCH` findings. Every closure answerable from existing arch + production ADRs + Phase 0/1 test precedent + verified repo state.

## Context Brief (Stage 1)

- **Goal as written (unchanged across both passes):** Extend `ALLOWED_BINARIES` from `{git, node}` to a 12-entry set; add a test asserting all new entries are present AND that the sensitive-env-var strip continues to drop the named keys.
- **Phase 2 exit criteria touched:** Step 1 plant of kernel-side data primitives. Every Phase 2 B/C/G probe (S4-x, S5-x, S6-x) consumes this allowlist via `run_external_cli` (S1-07) or `run_allowlisted` direct (Layer C).
- **Load-bearing commitments touched:**
  - **CLAUDE.md "Extension by addition":** honored — `run_allowlisted` signature untouched; only data grows.
  - **Phase 0 ADR-0012 §Decision:** `ALLOWED_BINARIES` remains a `frozenset[str]`; additions are ADR-gated via 02-ADR-0001.
  - **02-ADR-0001 §"Pattern fit":** Registry pattern — kernel-side allowlist as data-driven extension primitive. Story preserves the pattern.
  - **02-ADR-0007:** no plugin loader in Phase 2 — story does NOT introduce `register_binary(...)` or decorator-based registration.
  - **Production ADR-0033 §"newtype-per-domain-primitive":** binary names cross zero module boundaries currently; newtype is premature (Notes-for-implementer Design-Pattern observation F2, no action).
- **Sibling-family lineage:** Third consumer of the `ALLOWED_BINARIES` registry (Phase 0 `{git}` → Phase 1 `+{node}` → Phase 2 `+10`). Rule-of-three threshold crossed for the *process* (phase-omnibus ADR + frozenset extension); kernel data shape stays correct.
- **Prior validation history:** Pass 1 (light-touch, 2026-05-15) added AC-9 + AC-10 and narrowed the test exception swallow; no formal `_validation/` report existed. Pass 2 (this report) is the canonical record.
- **Open ambiguities resolved before Stage 2:**
  - **Eight-vs-ten new entries.** `02-ADR-0001 §Decision` says eight; `phase-arch-design.md` line 493, `final-design.md` line 224, and `High-level-impl.md` line 30 all agree on ten + `git` + `node`. ADR text is the drift. Pass 1's AC-10 + Pass 2's extension fix it.
  - **`bwrap` policy.** Notes-for-implementer documented the wrapper-pattern exception. Pass 1 left it as a Notes paragraph (vanishes after merge). Pass 2 promoted to a recorded ADR consequence (AC-10) and a structural test pin (AC-15).
  - **Count discipline ("eleven additions" in title vs "ten" in prose).** Title is relative to Phase 0's `{git}` baseline; prose is relative to Phase 1's `{git, node}` baseline. `EXPECTED_TOTAL` in the test is the disambiguator. Documentation noise, not test weakness — left as-is per Consistency F4 (nit).

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN — 10 findings, 2 block)

| ID | Sev | Finding | Closure |
|----|----|---|---|
| F1 | nit | Closed-set negative-list parametric is in different file than new exact-set assertion | Family-symmetric closure via AC-15 |
| **F2** | **block** | AC-2 is unverifiable prose — "OR justified in Notes" + "file an amendment if a reviewer flags the gap" is a deferral, not a pass/fail check | **AC-2 rewritten** as pytest meta-test parsing 02-ADR-0001 |
| **F3** | **block** | Module-docstring update from Impl Outline step 2 has no AC pinning it — mutant: forget docstring → all tests pass | **AC-11 added** — substring assertions on `codegenie.exec.__doc__` |
| F4 | harden | AC-4 env-strip parametrizes over `git`-argv only; per-new-binary env hygiene unverified | AC-12 added |
| F5 | harden | `AWS_*`-prefix path not asserted for new-binary AC set | AC-16 added |
| F6 | harden | Path-traversal regression `[/usr/bin/{b}, ./{b}]` not pinned for new entries | AC-14 added |
| F7 | harden | `bwrap`/`bubblewrap` rationale lives in story Notes only (vanishes after merge) | AC-10 extended + AC-15 |
| F8 | nit | Edge-case binary names | No action — value-equality is the structural answer |
| F9 | nit | AC-10 (ADR amendment) lacks a test that the file was actually amended | Subsumed by AC-2's meta-test |
| F10 | nit | `test_node_in_allowed_binaries` name is stale post-AC-9 update | Out-of-scope rename — leave to executor's judgment |

### Test-Quality critic (verdict: TESTS-HARDEN — 12 mutations evaluated, 6 real gaps)

Pre-flight verification:
- **M1 (broad-except swallow):** Pass-1 hardening already narrowed `except (ToolMissingError, Exception)` → narrow set. Stale. Nit only.
- **M6 (patch target):** `patch.object(_aio, ...)` is functionally correct, but stylistically diverges from 8 family precedents. Nit — addressed in Notes-for-implementer (use `monkeypatch.setattr(asyncio, ...)`).
- **M8 (hypothesis):** Available; not added — AC-12/13/14 parametrics achieve equivalent mutation resistance without new dependency.

Mutation table (selected):

| # | Wrong impl | Caught by original? | Closure |
|---|---|---|---|
| M2 | `if binary in NEW_PHASE_2_BINARIES: env = os.environ.copy()` in `_filter_env` | **No** — AC-4 only tests `git`-argv | **AC-12** |
| M5 | `if binary in NEW: skip the finally: pop` | **No** — Test 3 has no `_RUNNING_PROCS` assertion | **AC-13** |
| M7 | Forget the docstring update | **No** — no AC asserts | **AC-11** |
| M9 | Silent `bwrap` addition to `ALLOWED_BINARIES` | Partial — caught by AC-1 exact-equality only if `EXPECTED_TOTAL` is also not mutated. Adversarial guard missing. | **AC-15** |
| M11 | `shutil.which()` pre-resolve of argv[0] (well-meaning) | **No** — no path-traversal test for new entries | **AC-14** |
| M16 | `AWS_FOO` prefix-path special-cased for new binary | **No** — AC-4 lists three concrete `AWS_*` keys but not the prefix | **AC-16** |

### Consistency critic (verdict: CONSISTENCY-HARDEN — 2 real findings, all others trace-confirm)

| ID | Sev | Finding | Source-of-truth | Closure |
|----|----|---|---|---|
| C1 | resolved | Eight-vs-ten in 02-ADR-0001 §Decision | `High-level-impl.md` line 30 (twelve total = ten new) | Pass 1 AC-10 |
| **C2** | **harden** | `bwrap` wrapper-pattern exception contradicts 02-ADR-0001 §Tradeoffs row 4 — needs recorded consequence | 02-ADR-0001 §Tradeoffs row 4; Notes-for-implementer §3 | **AC-10 extended** (Consequences bullet) + **AC-15** (test pin) |
| **C4** | **harden** | 02-ADR-0001 §Tradeoffs row 2 "Eight new CVE feeds" stays as drift after AC-10's Decision-section amendment | 02-ADR-0001 §Tradeoffs row 2 | **AC-10 extended** (Tradeoffs row 2 update) |
| C5–C13 | trace-confirm | ADR-0012 frozenset shape, Extension-by-addition, Production ADR-0012 microVM door, Phase 0 no-shell-true invariant, ADR-0009 xdist veto, 02-ADR-0007 no-plugin-loader, final-design.md trace, all ACs trace to goal | various | No action |

**Out-of-scope spawn candidate** (Consistency F12): reconcile `final-design.md §"Resource & cost profile"` line 396 ("eight additions") with `final-design.md §"Components" §3` line 224 (names `ast-grep`/`ripgrep`) and `High-level-impl.md` line 30 (twelve total). Doc-drift cleanup; not a Phase 2 implementation block. **Spawn task NOT created** — low confidence that the drift survives AC-10's ADR amendment pull-through; revisit if it does.

### Design-Patterns critic (verdict: PATTERNS-HARDEN — 1 real finding, 2 Notes observations)

| ID | Sev | Finding | Pattern at stake | Closure |
|----|----|---|---|---|
| **F1** | **harden** | Closed-set negative-list (Phase 1 precedent at `tests/unit/test_exec.py:327`) doesn't get extended in Phase 2 despite Notes documenting `bwrap` as the intentional exception | Open/Closed at the file boundary; Registry pattern hygiene (negative space) | **AC-15** |
| F2 | nit | `BinaryName` newtype is premature — names cross zero module boundaries today | Newtype pattern / primitive obsession | **Notes-for-implementer paragraph** only |
| F3 | nit | Rule-of-three for phase-batch-ADR tooling crossed — precommit hook would be the kernel | Open/Closed; governance-as-tooling | **Notes-for-implementer paragraph** only (deferred to future story) |
| D3 | confirm | Registry pattern hygiene passes (simplest possible shape, no eager validation) | Registry pattern | No action |
| D4 | confirm | Open/Closed at file boundary satisfied | Open/Closed | No action |
| D5–D11 | confirm | Sum-types, DIP, functional core / imperative shell, hidden state, tagged-union hardening, test-side extensibility | various | No action |

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings from any critic. Every closure was answerable from existing arch + ADRs + Phase 0/1 test precedent + verified repo state.

## Stage 4 — Synthesizer + Editor

### Priority order applied

Per skill's conflict-resolution rule (`Consistency > Coverage > Test-Quality > Design-Patterns`):

1. **Consistency block-tier (C2, C4)** drove the AC-10 extension (Tradeoffs row 2 + bwrap Consequence). No conflict with other critics — Coverage F7 and Patterns F1 both wanted the same outcome.
2. **Coverage block-tier (F2, F3)** drove AC-2 rewrite and AC-11 addition. F2 conflict potential with "Rule 2 / Notes-as-documentation-is-fine" → resolved in favor of Coverage because the original AC-2 was claiming to *verify* something it could not.
3. **Test-Quality harden (M2, M5, M11, M16)** drove AC-12, AC-13, AC-14, AC-16. No conflicts — all family-symmetric with Phase 0/1 precedent.
4. **Design-Patterns harden (F1)** drove AC-15. Conflicted with Pass-1 AC-9's "keep parametrize list unchanged" — resolved by *superseding* AC-9's parametrize-list clause (negative list extended additively; old six entries kept).
5. **Design-Patterns nits (F2, F3)** surfaced as Notes-for-implementer paragraphs only — Rule 2 (Simplicity First) and Rule 3 (Surgical Changes) win for an in-scope-of-S1-06 implementation; observations recorded for future stories.

### Edits applied to the story file

| AC# / Section | Type | Critic source |
|---|---|---|
| Validation notes block | Replaced with Pass 1 + Pass 2 combined narrative | All four critics |
| AC-2 | Rewritten (prose deferral → pytest meta-test) | Coverage F2 (block) |
| AC-10 | Extended (Tradeoffs row 2 + Consequences bullet) | Consistency C2 + C4 (harden) |
| AC-11 (new) | Added | Coverage F3 (block) |
| AC-12 (new) | Added | Test-Quality M2 + Coverage F4 (harden) |
| AC-13 (new) | Added | Test-Quality M5 (harden) |
| AC-14 (new) | Added | Test-Quality M11 + Coverage F6 (harden) |
| AC-15 (new, supersedes AC-9 parametric-unchanged clause) | Added | Design-Patterns F1 + Test-Quality M9 (harden) |
| AC-16 (new) | Added | Coverage F5 (harden) |
| TDD plan | Extended with test bodies for AC-2/11/12/13/14/16 + AC-15 companion edit | All four critics |
| Files-to-touch | Updated with AC-11–AC-16 mapping | All four critics |
| Out-of-scope `bwrap` bullet | Updated — wrapper-pattern exception now structurally pinned via AC-10 + AC-15 | Consistency C2 |
| Notes-for-implementer | Extended with Design-Pattern observations (F2 BinaryName, F3 rule-of-three, D3 Registry confirmation) + style guidance (M6 monkeypatch.setattr) | Design-Patterns F2/F3/D3 + Test-Quality M6 |

### Conflicts resolved

- **AC-15 supersedes Pass-1 AC-9's "parametrize list stays unchanged"** instruction. Pass-1 AC-9 was authored before the deep audit recognized `bwrap`/`bubblewrap` as the structurally-critical negative-list entry. AC-15 extends the list additively; AC-9's "stays unchanged" instruction is now obsolete but kept for the file rename + equality update it pins. The story's Validation Notes section calls out the supersession explicitly.

- **Design-Patterns F2 (BinaryName newtype) vs production ADR-0033 "newtype-per-domain-primitive".** Apparent tension: ADR-0033 says newtype every domain primitive; F2 says binary names don't cross boundaries → no current safety gain. Resolved via the validator skill's "design quality vocabulary" prescription — newtype discipline applies *when the type crosses ≥ 2 module boundaries*. Binary names today are read once by `run_allowlisted` and never propagated. Recorded in Notes-for-implementer for the future-promotion case.

## Final verdict

**HARDENED.** Both passes (Pass 1 light-touch + Pass 2 deep audit) applied. Two block-tier gaps closed (AC-2 unverifiability, AC-11 docstring). Five harden-tier gaps closed (AC-12 env-strip, AC-13 weakref, AC-14 path-traversal, AC-15 negative-list, AC-16 AWS_FOO). Two ADR amendments folded into AC-10 (CVE-feed count + bwrap consequence). Three nit-level observations recorded as Notes-for-implementer paragraphs.

The story is now ready for `phase-story-executor` with a TDD plan that has mutation-resistance against six identified regression classes:

1. Per-binary env-handling special-casing (AC-12)
2. Weakref-table cleanup skipped for new binaries (AC-13)
3. Silent `bwrap` allowlist addition (AC-15)
4. Path-bearing argv accepted for new binaries (AC-14)
5. Module docstring forgotten (AC-11)
6. ADR text drift after code-side addition (AC-2)

The `_attempts/S1-06-allowed-binaries-extension.md` log will be created by the executor; this `_validation/` report is the validator's complete record.
