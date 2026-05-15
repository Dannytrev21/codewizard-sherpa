# Validation report: S6-02 — Coverage ratchet to 90/80 + warm-path + per-probe RSS bench canaries

**Validated:** 2026-05-15
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S6-02 is the moment Phase 1's coverage ratchet (90/80 with the two `deployment.py` + `ci.py` 85/75 carve-outs from S4-04 / ADR-0005) becomes active and Phase 0's three bench canaries grow to five with two new advisory observation harnesses (`test_warm_path_latency.py`, `test_per_probe_rss.py`). The original draft had a sound goal that traced cleanly to `phase-arch-design.md §Goals #7`, ADR-0005, `High-level-impl.md §Step 6`, and the cross-cutting per-probe-coverage discipline established across S2-01..S4-03. The TDD plan, however, contained four blocking issues and several harden-tier issues that would have produced a story-passing-but-CI-breaking implementation.

The four blocks: (1) AC-1 named `[tool.coverage.report]` per-module floors, but coverage.py only supports a global `fail_under` — the actually-shipped (S4-04) mechanism is a `[tool.coverage_carve_outs.entries]` TOML table read by `scripts/check_coverage_carve_outs.py`. ADR-0005's pre-implementation wording was stale; the story inherited it. (2) The TDD plan reinvented the `bench-results.json` atomic-write inline despite Phase 0 S5-01 having shipped `tests/bench/_helpers.py` with `bench_results_path()` + `merge_bench_result()` — the rule-of-three was passed by Phase 0's three canaries (cold_start / coordinator_overhead / cache_hit_dispatch all consume the kernel) and reinventing it (a) silently drops `$GITHUB_WORKSPACE` resolution so artifact upload no-ops in CI, (b) drops `fsync`, (c) races a same-name `.tmp` under future `pytest-xdist`. (3) The CI workflow's `bench-collection-guard` step asserts `collected -ne 3`; adding two new bench files trips the guard immediately on PR push — the story's narrative said "no changes required if the existing step picks up the two new files automatically" without addressing the gating count. (4) The TDD plan used `subprocess.run(["codegenie", ...])` for the warm-path bench, which loses the only signal that detects a silent cache-never-hits regression (the `GatherResult.executions[name] is CacheHit` invariant Phase 0 deliberately preserved with in-process gather).

The five hardens addressed missing harness-not-silently-no-op invariants on both new bench files (mirroring the `assert ... > 0` pattern in all three Phase 0 canaries), an ambiguous `per_probe_rss.<probe_name>` JSON-key shape (resolved to a single top-level `per_probe_rss` key whose value is a dict), an enumeration AC for the six Layer A probes (without it the laziest passing implementation dispatches one probe and writes one key), a negative-space AC ensuring no third carve-out is smuggled in (without it the laziest fix for an under-floor probe is a third carve-out at 80/70), and a non-advisory `CacheHit` assertion on the warm-path bench that catches a silent cache-never-hits regression even though the wall-clock ratio remains advisory.

The two nits were design-pattern opportunities flagged but not promoted: (a) eventual extract of `measure_probe_peak_rss(...)` to `_helpers.py` if Phase 2 adds a Layer B/C/D RSS canary (this is the FIRST occurrence — Rule 2 says do not extract preemptively), and (b) `default_registry` introspection in the per-probe RSS test rather than hard-coded probe names (incorporated into AC-3 since it's the same line of code as the negative-space oracle). Both surfaced as Notes-for-implementer paragraphs.

The result is a story that is easy to extend by addition (new bench canaries land as new files consuming `_helpers.py`), pins the Open/Closed contract for the bench harness as an observable AC, encodes the negative-space ratchet contract, and surfaces each silent-no-op failure mode as an observable assertion mirrored from Phase 0 precedent. No findings required external research; all answers came from the existing `tests/bench/_helpers.py`, `pyproject.toml`, `.github/workflows/ci.yml`, and `tests/bench/test_cache_hit_dispatch.py` precedents.

## Findings by critic

### Coverage critic

#### F1 — AC-5 missing: `bench-collection-guard` count not bumped
- **Severity:** block
- **What's wrong:** `.github/workflows/ci.yml:118` asserts `if [ "${collected}" -ne 3 ]; then ... exit 1; fi`. Adding two new bench files makes `collected == 5`; the guard fails on the first PR push. AC-5 ("the existing `bench` step ... no changes required if the existing step picks up the two new files automatically") is silent on the gating count; the gate fires before the bench step even runs.
- **Proposed fix:** Add explicit AC for bumping the count `3 → 5` and the surrounding messages.
- **Confidence:** high
- **Source:** `.github/workflows/ci.yml` lines 112–119

#### F2 — AC-1 misstates where carve-out floors live
- **Severity:** block
- **What's wrong:** "[tool.coverage.report] per-module floors of 85/75 declared" — coverage.py's `[tool.coverage.report]` only supports a global `fail_under`. Per-module enforcement actually lives in `[tool.coverage_carve_outs.entries]` (a custom TOML table S4-04 added) read by `scripts/check_coverage_carve_outs.py` against `coverage.json`. ADR-0005 §Consequences originally named `[tool.coverage.report]` but what shipped is the script-driven mechanism.
- **Proposed fix:** Rewrite AC-1 to point at `[tool.coverage_carve_outs.entries]` (preserved unchanged from S4-04) and the `Per-module coverage carve-outs (ADR-0005)` CI step.
- **Confidence:** high
- **Source:** `pyproject.toml` lines 195–239 + `.github/workflows/ci.yml` line 96 + `scripts/check_coverage_carve_outs.py` existence

#### F3 — Negative-space AC missing: ratchet must NOT be silently bypassed
- **Severity:** harden
- **What's wrong:** Story narrative says "the coverage gate cannot be bypassed" but no AC encodes "if a probe is under floor, no third carve-out is added". A lazy implementer could quietly add a third carve-out at 80/70 to make CI green — would pass every literal AC.
- **Proposed fix:** Add AC: `[tool.coverage_carve_outs.entries]` contains exactly two entries; existing build test (S4-04) is the runtime proof.
- **Confidence:** high
- **Source:** Lazy-impl thought experiment + `tests/unit/build/test_coverage_carve_outs.py::test_carve_out_table_has_exactly_two_entries`

#### F4 — Empty/no-op failure-path AC missing for bench JSON
- **Severity:** harden
- **What's wrong:** AC-2/AC-3 say the bench writes a key. A bench that catches an exception and silently writes nothing satisfies the AC literally. All three Phase 0 canaries have the explicit "harness-not-silently-no-op" assertion (re-read JSON, assert key present, assert value > 0).
- **Proposed fix:** Mirror Phase 0's harness-not-noop pattern in both bench files; encode in ACs.
- **Confidence:** high
- **Source:** `test_cache_hit_dispatch.py:81–86`, `test_cli_cold_start.py:49–54`

#### F5 — Per-probe RSS: probe enumeration not pinned
- **Severity:** harden
- **What's wrong:** AC-3 says "dispatches each of the six Layer A probes individually" but does not name them (lazy impl could dispatch only `language_detection` and write one key — passes literally).
- **Proposed fix:** Enumerate the six (`language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory`); assert all six keys appear in `per_probe_rss`. Pair with start/stop-per-probe pinning so a `tracemalloc.start()`-once impl is also rejected.
- **Confidence:** high

#### F6 — Side-effect imports for probe registration
- **Severity:** nit
- **What's wrong:** `default_registry.for_task(...)` only knows about probes whose modules have been imported (the `@register_probe` decorator fires at import). Phase 0's `test_cache_hit_dispatch.py` does `import codegenie.probes.language_detection  # noqa: F401`. The story didn't mention this.
- **Proposed fix:** Note in implementation outline + Green example explicitly imports all six probe modules with `# noqa: F401`.
- **Confidence:** medium

### Test-Quality critic

#### F1 — Warm-path bench uses subprocess where in-process matches Phase 0
- **Severity:** harden
- **Smell:** Inconsistent test style across siblings (Rule 11 — match the codebase's conventions)
- **What's wrong:** TDD plan example uses `subprocess.run(["codegenie", ...])`. Phase 0's `test_cache_hit_dispatch.py` (closest sibling — also testing warm/cold) uses in-process `asyncio.run(gather(...))` so it can assert on `GatherResult.executions["language_detection"]` being a `CacheHit`. Subprocess loses that signal — a regression that silently disables caching produces a clean ratio.
- **Proposed fix:** Mirror `test_cache_hit_dispatch.py` shape: in-process gather, assert `isinstance(execution, CacheHit)` for at least one probe on warm run.
- **Confidence:** high
- **Source:** `test_cache_hit_dispatch.py:56–71`

#### F2 — TDD example duplicates the bench-results.json kernel
- **Severity:** block
- **Smell:** Reinventing existing kernel (Rule 11 + Open/Closed + extension-by-addition)
- **What's wrong:** Inline `tmp.write_text(...); tmp.replace(results_path)` atomic-write. Phase 0 S5-01 shipped `tests/bench/_helpers.py` with `bench_results_path()` + `merge_bench_result()`. Inlining: (a) drops `$GITHUB_WORKSPACE` handling so CI artifact upload no-ops, (b) drops `fsync`, (c) races a same-name `.tmp` under `pytest-xdist`.
- **Proposed fix:** `from tests.bench._helpers import bench_results_path, merge_bench_result`; call `merge_bench_result(out, "warm_path_ratio", {...})`. Same for per-probe RSS.
- **Confidence:** high
- **Citation:** All three Phase 0 canaries consume `_helpers`; rule-of-three already passed; mandate.

#### F3 — Mutation thinking: warm-path bench would silently no-op on cache regression
- **Severity:** harden
- **What's wrong:** If caching silently breaks, ratio is ~1.0 — test still passes (advisory). Without the non-advisory `CacheHit` assertion (Phase 0's pattern), the regression is undetectable.
- **Proposed fix:** Same as F1 — non-advisory `CacheHit` gate.
- **Confidence:** high

#### F4 — async loop teardown / asyncio_mode interaction
- **Severity:** nit
- **What's wrong:** pyproject sets `asyncio_mode = "auto"`. Bench tests should be sync top-level (`def test_...`) and call `asyncio.run` themselves rather than `async def test_...` to avoid plugin-marker interaction.
- **Proposed fix:** Confirm bench tests are sync `def`; the example in the Green section is.
- **Confidence:** medium
- **Source:** `pyproject.toml:165`

#### F5 — `tracemalloc` peak vs current semantics
- **Severity:** harden
- **What's wrong:** `tracemalloc.get_traced_memory()` returns `(current, peak)`. If the test pulls `current` it's ~0 after gather completes. Story narrative says "peak" but AC-3 says "per-probe peak-RSS-bytes" without pinning the unpack.
- **Proposed fix:** Pin in TDD plan: `_current, peak = tracemalloc.get_traced_memory()`. mypy --strict catches the omission.
- **Confidence:** high

### Consistency critic

#### F1 — AC-1 contradicts pyproject.toml's S4-04-landed shape
- **Severity:** block
- **What's wrong:** Same as Coverage F2 — story names `[tool.coverage.report]` per-module but reality is `[tool.coverage_carve_outs.entries]` + script. Story outline §1 also says "via `[tool.coverage.report] exclude_also` or equivalent" which is also wrong (`exclude_also` excludes lines from coverage measurement, doesn't enforce floors).
- **Proposed fix:** Same as Coverage F2. Cross-link.
- **Source:** `pyproject.toml` lines 195–239

#### F2 — High-level-impl.md vs phase-arch-design.md "≤ 0.25" wording
- **Severity:** harden
- **What's wrong:** `High-level-impl.md:185` says "assert second-run wall-clock ratio ≤ 0.25 of first-run (advisory PR comment only)". Story rejects the assertion and aligns with `phase-arch-design.md §Edge cases row 12` and Phase 0 S5-01 precedent (no wall-clock gates). Story is correct, but the contradiction with High-level-impl.md should be acknowledged so the executor doesn't try to honor the literal reading of either source.
- **Proposed fix:** Note in implementation: "the ≤ 0.25 number from `High-level-impl.md §Step 6` is the *expectation*, not the assertion. Per `phase-arch-design.md §Edge cases row 12` and Phase 0 S5-01 precedent (no wall-clock gates), the bench is advisory; the 0.25 number lives in the PR comment only."
- **Confidence:** high

#### F3 — Step 6 "post advisory PR comments" is unfunded
- **Severity:** nit
- **What's wrong:** `High-level-impl.md §Step 6 Done criteria` says "Both bench canaries run in CI and post advisory PR comments". Story's Out-of-scope correctly defers PR-comment posting (Phase 0 didn't ship a posting Action either; bench-results.json is the artifact). Surface as a known phase-gap to call out in S6-03 (Phase 2 handoff).
- **Proposed fix:** Story is consistent with Phase 0 reality; no story edit needed; note in validation report only.
- **Confidence:** high

### Design-Patterns critic

#### F1 — Reinvented atomic-write kernel
- **Severity:** block
- **Smell:** Plugin/kernel violation; rule-of-three already passed
- **What's wrong:** Same finding as Test-Quality F2. The kernel exists, all 3 Phase 0 canaries consume it, this story should too. Violates "Extension by addition" (CLAUDE.md).
- **Proposed fix:** Same as Test-Quality F2. Add observable Open/Closed AC for bench harness extension.
- **Pattern:** Plugin / Kernel + Registry; functional core / imperative shell.

#### F2 — Per-probe RSS dispatch loop: opportunity to extract pure helper
- **Severity:** nit
- **Smell:** Functional core / imperative shell
- **What's wrong:** `tracemalloc.start() / dispatch / get_traced_memory() / stop()` per probe is a pattern that may repeat in Phase 2 if Layer B/C/D probes add a per-layer RSS canary. This is the FIRST occurrence — per critic-design-patterns.md §18 / Rule 2: do NOT extract preemptively.
- **Proposed fix:** Note in Notes-for-implementer; defer extraction to the second user.
- **Confidence:** high (about the deferral)

#### F3 — Hard-coded probe names — primitive obsession / closed over Layer A
- **Severity:** harden (folded into AC-3)
- **Smell:** Primitive obsession / Open/Closed at test boundary
- **What's wrong:** Iterating six `str` literals would silently include or exclude probes when Phase 2's Layer B/C/D registrations land in the same registry. The probe classes already have a `.layer` attribute and `.name`; use them.
- **Proposed fix:** Iterate `default_registry.for_task(...)` filtered on `probe.layer == "A"`; use `_EXPECTED_LAYER_A_PROBES` constant as a negative-space oracle that catches silent registry skew either direction.
- **Confidence:** high

#### F4 — `per_probe_rss.<probe_name>` JSON-key shape ambiguous
- **Severity:** harden
- **Smell:** Make illegal states unrepresentable
- **What's wrong:** Original AC-3 wording (`per_probe_rss.<probe_name>`) is ambiguous: one nested dict, or six dotted top-level keys? Inconsistent with Phase 0's namespacing (`cold_start`, `coordinator_overhead`, `cache_hit_dispatch` are top-level). Six top-level keys would pollute the namespace and force any reader to know the six names.
- **Proposed fix:** One top-level `per_probe_rss` key whose value is `dict[probe_name, peak_bytes]`. One `merge_bench_result(out, "per_probe_rss", per_probe_peak)` call (not six).
- **Confidence:** high

#### F5 — Mirror ADR-0009-style non-advisory cache-hit assertion
- **Severity:** harden
- **What's wrong:** Same as Test-Quality F1 / F3 — without the non-advisory `CacheHit` gate, a silent cache-never-hits regression slips through.
- **Proposed fix:** Same as Test-Quality F1.
- **Source:** `test_cache_hit_dispatch.py:69` (ADR-0009 gate).

## Research briefs

None — no `NEEDS RESEARCH` findings. Every finding was answered by existing precedent in `tests/bench/_helpers.py`, `tests/bench/test_cache_hit_dispatch.py`, `pyproject.toml`'s S4-04-landed `[tool.coverage_carve_outs.entries]` table, `scripts/check_coverage_carve_outs.py`, and `.github/workflows/ci.yml`'s `bench-collection-guard` step.

## Conflict resolutions

- **Coverage F2 + Consistency F1 + Test-Quality F2 + Design-Patterns F1** all converged on the same deeper finding: the story does not consume already-shipped infrastructure (the carve-outs table + script for AC-1; the `_helpers.py` kernel for the bench files). Synthesizer picked the Consistency framing for AC-1 wording (source-of-truth is what shipped, not what ADR-0005 originally proposed) and the Design-Patterns framing for AC-10 (observable Open/Closed contract for the bench harness extension path).
- **Design-Patterns F2** (extract `measure_probe_peak_rss`) flagged a kernel opportunity. Rule 2 + critic-design-patterns.md §18 / synthesis priority chain item 5: this is the first occurrence; do NOT mandate the extract; surface in Notes-for-implementer only. No new AC.
- **High-level-impl.md vs phase-arch-design.md** disagreement on the "≤ 0.25" wording (Consistency F2): synthesizer picked phase-arch-design.md (matches Phase 0 precedent and the explicit `§Edge cases row 12` rationale). High-level-impl.md's literal reading is stale; Notes-for-implementer documents the reconciliation so the executor doesn't get confused.

## Edits applied

### Edit 1 — AC-1 rewritten to pin the actually-shipped enforcement mechanism
- Source: Consistency F1 + Coverage F2
- Before: "[tool.coverage.report] per-module floors of 85/75 declared for src/codegenie/probes/deployment.py and src/codegenie/probes/ci.py; src/codegenie/cli.py excluded (ADR-0005)."
- After: Pinned to `[tool.coverage_carve_outs.entries]` (preserved unchanged from S4-04) + `scripts/check_coverage_carve_outs.py` invocation in the CI `test` job. `[tool.coverage.report].omit` continues to exclude cli.py. Added breadcrumb for ADR-0005 §Consequences wording vs. what shipped.
- Rationale: original AC was unverifiable (the named mechanism doesn't enforce per-module floors).

### Edit 2 — AC-2 strengthened with in-process shape, kernel consumption, harness-not-noop, non-advisory CacheHit gate
- Source: Test-Quality F1 + F2 + F3 + Design-Patterns F1 + F5 + Coverage F4
- Before: "runs codegenie gather <node_typescript_helm> twice, computes second_run_wall_clock / first_run_wall_clock, writes the ratio to bench-results.json keyed warm_path_ratio, and never asserts a threshold (advisory only)."
- After: 5-bullet AC pinning in-process `asyncio.run(gather(...))`, `_helpers.merge_bench_result()` consumption, advisory wall-clock posture, non-advisory `CacheHit` assertion mirroring `test_cache_hit_dispatch.py:69`, and harness-not-silently-no-op re-read assertions (`cold_s > 0`, `warm_s > 0`).
- Rationale: subprocess shape loses the only signal that detects silent cache-never-hits regressions; inline atomic-write reinvents the kernel and silently breaks CI artifact upload by dropping `$GITHUB_WORKSPACE` handling.

### Edit 3 — AC-3 strengthened with enumeration, start/stop-per-probe, single namespaced key
- Source: Coverage F5 + Design-Patterns F3 + F4 + Test-Quality F5
- Before: "dispatches each of the six Layer A probes individually through the coordinator with tracemalloc.start() and tracemalloc.get_traced_memory(), writes per-probe peak-RSS-bytes to bench-results.json keyed per_probe_rss.<probe_name>, and never asserts a threshold (advisory only)."
- After: bullet AC pinning the six probe names as a negative-space oracle, deriving the iteration set from `default_registry.for_task(...)` filtered on `probe.layer == "A"`, start/stop-per-probe (no allocation pollution), explicit `_current, peak = ...` unpack, single `merge_bench_result(out, "per_probe_rss", {...})` call (not six), and harness-not-noop assertions (`set == {six names}`, `all > 0`).
- Rationale: original AC underspecified — lazy impl dispatching one probe with `start()` once would pass literally; ambiguous JSON-key shape; hard-coded names break Open/Closed when Phase 2 lands Layer B+ probes.

### Edit 4 — AC-5 added: bench-collection-guard count bumped 3 → 5
- Source: Coverage F1
- Before: "CI workflow file routes the two new bench tests into the existing bench step from Phase 0 (S5-01); the step uses continue-on-error: true and the artifact upload mechanism is unchanged."
- After: Explicit AC for bumping `.github/workflows/ci.yml`'s `bench-collection-guard` from `-ne 3` to `-ne 5` and updating its messages; `bench (advisory)` step itself uses path discovery and needs no edit; artifact upload unchanged.
- Rationale: the gating count fails the moment the two new bench files land if not bumped — silent CI break for the next contributor.

### Edit 5 — AC-6 unchanged in intent; reworded for verifiability
- Source: Coverage critic AC grain check
- Before: free-form "shows actual per-module coverage percentages"
- After: pinned to a markdown table with named columns (module / line % / branch % / floor / pass) and named the runtime-enforcement gate (`Per-module coverage carve-outs (ADR-0005)` CI step) as the proof.

### Edit 6 — AC-9 added: negative-space — no third carve-out
- Source: Coverage F3
- After: "`[tool.coverage_carve_outs.entries]` contains exactly two entries after this PR; `tests/unit/build/test_coverage_carve_outs.py::test_carve_out_table_has_exactly_two_entries` (S4-04) continues to pass."
- Rationale: encodes the "ratchet must not be silently bypassed" intent as an observable contract; without it the laziest passing impl is a third carve-out.

### Edit 7 — AC-10 added: extension-by-addition for bench harness
- Source: Design-Patterns F1 (rule-of-three already passed)
- After: "Adding a sixth bench canary requires zero edits to `tests/bench/_helpers.py`; the new test consumes the kernel and registers a new top-level key. The only edit elsewhere is bumping `bench-collection-guard`'s `-ne N` count by 1."
- Rationale: observable Open/Closed contract for the bench harness; pattern: Plugin / Kernel + Registry, "Extension by addition" — CLAUDE.md.

### Edit 8 — TDD plan rewritten end-to-end
- Source: Test-Quality F1 + F2 + Design-Patterns F1 + F4
- Before: subprocess-based warm-path bench with inline atomic-write; per-probe RSS sketch absent.
- After: full Green example for both bench files; in-process gather mirroring `test_cache_hit_dispatch.py`; consumes `_helpers.merge_bench_result()`; explicit start/stop-per-probe; `_EXPECTED_LAYER_A_PROBES` negative-space oracle; non-advisory `CacheHit` assertion; harness-not-noop re-read assertions on both files.
- Rationale: the original Green example was the source of truth executors copy from; replacing it removes the silent-no-op failure modes baked in.

### Edit 9 — Files-to-touch extended with the ci.yml `bench-collection-guard` bump
- Source: Coverage F1
- Added explicit modify entry for `.github/workflows/ci.yml` with the `-ne 3 → -ne 5` directive and message bump.

### Edit 10 — Notes-for-implementer rewritten
- Source: synthesis of all critics
- Added: kernel-consumption framing for `_helpers.py`; in-process vs subprocess rationale; `tracemalloc` peak/current unpack; `default_registry` introspection; first-occurrence deferral for `measure_probe_peak_rss` (Rule 2); the script-vs-coverage.py-`fail_under` mechanism explanation; the bench-collection-guard CI gate; reconciliation of the High-level-impl.md "≤ 0.25" wording vs. phase-arch-design.md.

## Verdict rationale

**HARDENED.** The story's goal is correct, traces cleanly to phase-arch-design.md §Goals #7, ADR-0005, and High-level-impl.md §Step 6, and is exactly the right scope for the Step 6 ratchet moment. The four blocks were mechanical — each had a single deterministic fix grounded in code or shipped infrastructure (no judgment calls, no research, no architectural reframing). The five hardens were missing observable invariants the executor would otherwise have written tests for *correctly* but loosely; tightening them moves the story from "executor writes plausible-looking code" to "executor's tests catch real silent-no-op failure modes". The two nits were design-pattern opportunities; one was folded into AC-3 because it's the same line of code as the negative-space oracle (`default_registry` introspection) and the other was deferred per Rule 2 (first occurrence; do not extract preemptively).

The story now has 10 ACs (up from 8), all observable, all tracing to the goal or to a phase exit criterion, with explicit Open/Closed contracts for both the carve-outs table (AC-9) and the bench harness (AC-10). The TDD plan ships byte-runnable Green examples for both new files, mirroring Phase 0 precedent for shape and consuming the `_helpers.py` kernel. The `bench-collection-guard` CI gate is now AC-5 instead of a silent CI break waiting to fire. Ready for `phase-story-executor`.

## Recommended next step

`phase-story-executor` to implement.
