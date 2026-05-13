# Validation report — S4-02 CLI `gather` + `audit verify` + tool-readiness check

**Date:** 2026-05-13
**Validator:** `phase-story-validator` (Stages 1, 2, 4; Stage 3 skipped — no `NEEDS RESEARCH` tags)
**Verdict:** **HARDENED** — many real and fixable weaknesses; edits applied; ready for executor.

## Stage 1 — Context Brief

**What the story promises (Goal — original):** `codegenie gather` on three fixtures exits 0, writes `repo-context.yaml` with `language_stack`, writes audit record, `audit verify` reports zero mismatches.

**What the phase exit criteria demand:** the user-visible vertical slice closes here — every Phase 0 exit criterion that says "the CLI runs" or "the YAML is on disk" hangs on this story.

**What the arch + ADRs constrain:**
- ADR-0008: `SymlinkRefusedError` → exit 5
- ADR-0009: exit 0 if `len(outputs) >= 1` (cache hits count); 2 if all `Skipped`/errored
- ADR-0010: `SecretLikelyFieldNameError` raised by `_ProbeOutputValidator` in coordinator → exit 6
- ADR-0011: `~/.codegenie/` mode 0700, `.tool-cache.json` mode 0600, atomic write
- ADR-0012: subprocess only via `exec.run_allowlisted`; `git rev-parse HEAD`
- ADR-0013: schema failure → exit 3, writes `.yaml.invalid`
- Phase-arch §Component design/CLI: documented codes `0/2/3/4/5/6` — code 4 is owned by `audit verify`

**Ambiguities surfaced:** five major contradictions between the story and already-merged code (B1–B4, H1). All were resolvable from the codebase, no Stage-3 research needed.

## Stage 2 — Three parallel critics

### Coverage critic — 14 findings (F1–F14)

Findings closed by AC additions:
- F1 (`cache.gc.stub` event name unpinned) → **AC-17**
- F2 (`--auto-gitignore`/`--no-gitignore`/`--refresh-tools` propagation untested) → **AC-2** (extended)
- F3 (`--version` doesn't assert version string) → **AC-16**
- F4 (Exit 1 untested) → **AC-15**
- F5 (Exit 4 namespace conflict with already-shipped `audit verify`) → **AC-4** (rewrote namespace) + **AC-8**
- F6 (shallow-merge collision behavior) → **AC-24**
- F7 (first-run `~/.codegenie/` creation) → **AC-7** (extended)
- F8 (Edge rows 9 + 13 referenced but unenforced) → **removed from References** (row 9 → S1-05, row 13 → S3-03; not this story's scope)
- F9 (non-git → `git_commit=None`) → **AC-18**
- F10 (`--verbose` doesn't assert DEBUG) → **AC-19**
- F11 (`cli.start`/`cli.end` events with shared `run_id`) → **AC-13**
- F12 (concurrent tool-cache write atomicity) → addressed by **AC-23** (atomic-write residue test); concurrent-process variant deferred — single-process atomic-write residue is the immediately-testable invariant
- F13 (AC-3 cold-start: false-pass on subprocess crash) → **AC-3** (rewrote with sentinel guard)
- F14 (AC-6 "non-empty output" ambiguity) → **AC-6** (aligned with ADR-0009: `len(outputs) >= 1`)
- AC-5 bundle issue → split into per-step assertions in AC-5 plus dedicated orchestration test (**AC-20**)

### Test-quality critic — 11 findings (F1–F11)

All test files rewritten in the TDD plan. Highlights:
- F1 (vacuous happy-path test) → AC-12 forces YAML content assertion; happy-path test now loads YAML and asserts `language_stack`
- F2 (exit-2 test doesn't assert no `.yaml`, audit-still-written) → **AC-11**
- F3 (exit-3 test doesn't assert no `.yaml` + content of `.invalid`) → tightened in TDD plan
- F4 (symlink arrange step ambiguous) → concrete arrange step in TDD plan (`(ctx / "repo-context.yaml").symlink_to(decoy)`)
- F5 (sanitizer-defense-in-depth untested) → **AC-21**
- F6 (5 identical tests → parametrize) → **AC-9** (parametrized dispatch table)
- F7 (`tmp_home_dir` undefined; corruption/atomic-write untested) → **AC-7**, **AC-22**, **AC-23**; TDD plan defines `tmp_home` fixture
- F8 (cold-start subprocess false-pass) → **AC-3** rewritten with sentinel
- F9 (missing test categories) → ACs added: AC-2/8/12/14/15/16/17/18/19/20
- F10 (vague monkeypatch sites) → AC-9 specifies "patch the resolved seam inside `codegenie.cli`"
- F11 (refactor `cli.start/end` untested) → **AC-13**

### Consistency critic — 12 findings (B1–B4, H1–H8, N1–N2)

**Block-severity (contradicted already-merged code or arch):**
- B1 (`pyproject.toml [project.scripts]` mis-stated) → Implementation outline step 7 corrected; Files-to-touch table corrected
- B2 (exit code 4 / 1 namespace conflation with S3-06's existing `audit verify`) → **AC-4** rewritten to separate gather codes vs audit verify code 4 vs click fallback code 1
- B3 (`AuditWriter.record(run_record, output_dir)` is a non-existent positional API) → **AC-5** step 11 rewritten with correct keyword-arg signature; implementer notes updated
- B4 (`exec.run_allowlisted` is `async def`; `asyncio.run` wrap not surfaced) → **AC-5** prefix rewritten; implementer notes updated

**Harden-severity:**
- H1 (`run_id` width drift; coordinator already binds 16-hex) → Refactor block + implementer notes rewritten — CLI inherits, does NOT mint
- H2 (under-stated mode obligations for `Writer`/`Cache`/`Audit`) → **AC-7** scoped to CLI-owned modes; cross-tests left to their owning stories' suites
- H3 ("non-empty output" gate that ADR-0009 doesn't require) → **AC-6** rewritten verbatim against ADR-0009
- H4 (Goal references fixtures explicitly out-of-scope) → **Goal narrowed** to per-test `<tmp_path>`; fixtures → S4-04
- H5 (Goal claims language_stack in YAML — no AC) → **AC-12**
- H6 (Goal claims audit verify zero-mismatches — but smoke run out-of-scope) → **AC-8** narrowed to unit-test of fixture run-record + exit-code mapping
- H7 (validator-vs-sanitizer raise-site conflation) → **AC-4** explicit about coordinator-side validator; **AC-21** for sanitizer DiD
- H8 (no AC for `_gitignore_mutation_stub` shim) → **AC-14**

**Nit:** N1 (`.yaml.invalid` attribution) → not edited (low value, doesn't mislead). N2 (`click.version_option` idiom) → noted in Implementation outline step 2.

## Stage 3 — Researcher
**Skipped.** No findings tagged `NEEDS RESEARCH`. All weaknesses resolvable from the codebase + ADRs.

## Stage 4 — Synthesizer + Editor

### Conflicts resolved
None of the three critics conflicted with each other. The Consistency critic's block-findings about already-merged code (B1–B4) take precedence over any speculative Coverage suggestions — and in fact aligned with them.

### Summary of edits to the story file
- **Header:** added `HARDENED 2026-05-13` status; appended a `Validation notes` block under the header.
- **Goal:** narrowed to per-test `<tmp_path>`; smoke-against-fixtures explicitly deferred to S4-04.
- **References — where to look:** removed Edge-case rows 9 and 13 (not this story's responsibility).
- **Acceptance criteria:** expanded from 10 bundled ACs to 24 atomic ACs (AC-1 through AC-24); each is now individually verifiable and traces to a specific test in the TDD plan.
- **Implementation outline:** rewrote steps 1, 4, 5, 6, 7; added step 8 (AuditWriter call shape).
- **TDD plan — Red:** replaced the three thin test stubs with six test files mapping 1:1 to ACs; parametrized exit codes; concrete symlink arrange; sentinel-guarded cold-start; defined `tmp_home` fixture; orchestration ordering test; sanitizer DiD test; verify-subcommand wiring test.
- **Refactor:** removed the incorrect "mint a new `run_id`" instruction; clarified the coordinator already binds it.
- **Files to touch:** expanded from 5 to 9 paths; corrected the `pyproject.toml` no-change note; added `__main__.py` reshape.
- **Notes for the implementer:** rewrote 11 of the 11 bullets to reflect already-merged code (the executor reads these verbatim, so drift here = wasted attempts).

### Verdict
**HARDENED.** The story now has:
- 24 individually verifiable ACs, all traced to the Goal
- A parametrized mutation-resistant exit-code dispatch test
- Concrete monkeypatch seams (no "monkeypatch the validator" hand-waves)
- A startup-order orchestration test (AC-20) that catches reordering bugs
- Defense-in-depth assertion for sanitizer (AC-21) — covers Scenario 4 fully
- All four BLOCK-level inconsistencies with already-merged code corrected
- All Goal claims now have AC backing
- Out-of-scope and ACs no longer contradict

Ready for `phase-story-executor`.
