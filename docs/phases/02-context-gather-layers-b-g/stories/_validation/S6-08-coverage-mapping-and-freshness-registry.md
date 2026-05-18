# Validation report: S6-08 — `TestCoverageMapping` + Layer D/E/G sub-schemas + freshness registrations

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S6-08 closes Phase 2 Step 6 by shipping the fifth Layer G probe (`TestCoverageMappingProbe`), 16 sub-schemas for Layer D/E/G, and three `@register_index_freshness_check` registrations that prove the Open/Closed promise of S1-02. The story's **intent** is sound and traces cleanly to the phase exit criteria. Four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns) found 22 substantive issues, of which 7 were `block`-tier: the prescribed implementation violated the frozen `Probe` ABC contract (sync `_run(ctx)` instead of `async run(repo, ctx)`), used a closed-sum-violating `ScannerSkipped` literal, declared `probe_id` as a class attribute that an existing Layer-D architectural test explicitly rejects, re-implemented `_lcov_scanner`'s state machine when the kernel already exists, and verified the load-bearing Open/Closed proof at the registry level only — never through `IndexHealthProbe` itself. None of these required a goal rewrite; all are mechanically fixable by editing AC text + the Green skeleton + the TDD plan. Verdict: HARDENED. Story edited in place.

## Findings by critic

### Coverage critic

**Verdict from critic:** HARDENED.

- [block] F1 — AC-9 enumeration mismatch: "7 schemas — one per S6-01..S6-04 + S6-05 Layer D probe" then lists 8 names. AC-17's "15 sub-schemas" is inconsistent. **Fix applied:** AC-9 → "8 schemas"; AC-17 → "16".
- [block] F2 — AC-14 doesn't exercise `IndexHealthProbe`. The Goal §3 says "the next gather's `IndexHealthProbe` constructs `Stale(...)`" but the test only calls the registry. **Fix applied:** AC-14 split into AC-14a (registry-level smoke) + AC-14b (end-to-end through `IndexHealthProbe`).
- [harden] F3 — AC-11 `expected_rule_pack_version` data-flow unspecified. **Fix applied:** AC-20 added — first-gather → `Fresh()`; prior baseline read from `ctx.config["prior_run"]` → `.codegenie/context/raw/{name}.json`; freshness function signature unchanged.
- [harden] F4 — Empty-coverage edge case unspecified. **Fix applied:** AC-18 added — well-formed but zero-record artifact → `ScannerRan(findings=())`, `files_seen=0`, `confidence="low"`.
- [harden] F5 — Both lcov + Istanbul present: ordering test missing. **Fix applied:** AC-19 added — lcov wins; `slice.format == "lcov"`.
- [harden] F6 — AC-13's git-diff form is fragile. **Fix applied:** AC-13 rewritten to pin BLAKE3 of `index_health.py`.
- [harden] F7 — Phase-2 "raw evidence only" non-goal not actively enforced. **Fix applied:** AC-21 added — `CoverageRecord` field set is frozen; architectural test rejects per-line-attribution leakage.
- [nit] F8 — `ScannerFailed(exit_code=0, ...)` semantic oddity. **Fix applied:** AC-7 rewritten with explicit `reason=None`; Notes-for-implementer documents the closed-sum constraint.
- [nit] F9 — LOC ceiling acceptable. Kept.

### Test-Quality critic

**Verdict from critic:** RESCUE (escalated by ABC-contract failures).

- [block] F1 — Every test calls `tcm.TestCoverageMappingProbe()._run(ctx)`; `_run` does not exist on the `Probe` ABC. **Fix applied:** every test rewritten to `asyncio.run(probe.run(repo, ctx))` with explicit `RepoSnapshot` + `ProbeContext` construction.
- [block] F2 — `ProbeContext.for_test(repo_root=...)` is not a real classmethod. **Fix applied:** explicit `ProbeContext(cache_dir=..., output_dir=..., workspace=..., logger=..., config={})` construction mirroring Layer-D test helpers; `repo.root` (not `ctx.repo_root`) is the repo root.
- [block] F3 — AC-3 prescribes `probe_id = ProbeId(...)` class attribute, but `tests/unit/probes/layer_d/test_conventions.py:159` asserts `not hasattr(p, "probe_id")` per ADR-0007. **Fix applied:** AC-3 rewritten to use `name` + module-level `_PROBE_ID: Final`.
- [harden] F4 — `test_lcov_parses_into_coverage_records` and Istanbul counterpart assert `files_seen == 1` only; a parser returning `CoverageRecord(source_file="", lines_covered=())` would pass. **Fix applied:** tests rewritten to pin actual `CoverageRecord` values (source_file, lines_covered).
- [harden] F5 — AC-14 registry-only test misses the B2-dispatch proof. **Fix applied:** AC-14b end-to-end variant; `test_index_health_probe_marks_index_stale_on_drift` parametrized.
- [harden] F6 — `test_oversized_coverage_yields_scanner_failed` writes 65 MB to disk. **Fix applied:** monkeypatch `_MAX_BYTES = 8`; write tiny file.
- [harden] F7 — `test_truncated_lcov_yields_scanner_failed` asserts isinstance only. **Fix applied:** pin `exit_code == 0`, `reason is None`, substring of stderr_tail diagnostic.
- [harden] F8 — Property test missing for lcov whitespace / unknown prefixes / blank lines. **Fix applied:** added `test_unknown_lcov_prefixes_silently_dropped` with `hypothesis` strategy.
- [harden] F9 — Determinism test missing. **Fix applied:** added `test_two_consecutive_gathers_are_byte_identical`.
- [harden] F10 — Both-files-present precedence test missing. **Fix applied:** AC-19 + `test_lcov_wins_when_both_artifacts_present`.
- [harden] F11 — Sub-schema round-trip only covered `ScannerSkipped`. **Fix applied:** parametrized round-trip across all three `ScannerOutcome` variants.
- [harden] F12 — `_PROBE_REGISTRY` reaches into a private dict that doesn't exist. **Fix applied:** test uses `default_registry._entries` per Layer-D precedent (`test_skills_index.py:353`).
- [nit] F12-tautology — `test_timeout_seconds_is_30` is a contract pin; renamed implicitly in the rewrite; acceptable.

### Consistency critic

**Verdict from critic:** RESCUE (escalated by frozen-contract violations).

- [block] Closed sum-type violation (AC-6 → `ScannerSkipped.reason="no_coverage_artifact"` not in `Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]`; module docstring + 02-ADR-0006 §Consequences make extension ADR-amendment-gated). **Fix applied:** AC-6 rewritten with `reason="upstream_unavailable"`.
- [block] Probe ABC signature mismatch (sync `_run(ctx)` vs async `run(self, repo, ctx)`). **Fix applied:** every reference rewritten.
- [block] `ProbeId` import path: `codegenie.ids` → `codegenie.types.identifiers`. **Fix applied** in Green skeleton.
- [block] Missing ABC class attributes (`name`, `layer`, `tier`, `requires`, `declared_inputs`). **Fix applied:** AC-3 declares full set.
- [block] `ctx.repo_root` doesn't exist; repo root is on `RepoSnapshot.root`. **Fix applied:** every reference rewritten.
- [block] `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=[])` — `ProbeOutput` has no `probe_id` and requires `raw_artifacts`, `duration_ms`, `warnings`, `errors`. **Fix applied:** Green skeleton's `_output` helper carries the full field set.
- [harden] Re-implements `_lcov_scanner`; bypasses `open_capped`. **Fix applied:** AC-5 rewritten — extend `_lcov_scanner` with `scan_records(...)`; consume `open_capped` + `safe_json.load`. New `test_no_inline_size_cap_or_lcov_parser` AST-walker test enforces the kernel-reuse contract.
- [harden] 64 MB vs Phase 1's 50 MB cap. **Fix applied:** `_MAX_BYTES = 50 * 1024 * 1024` (aligned with `_lcov_scanner._LCOV_MAX_BYTES`).
- [harden] AC-13 git-diff fragile. **Fix applied:** BLAKE3 pin.
- [harden] AC-7 narrative-only "concise reason". **Fix applied:** explicit `reason=None`.
- [nit] AC-9 count vs enumeration mismatch. **Fix applied:** 8/8.
- [nit] `applies_to_tasks=("*",)` tuple vs ABC `list[str]`. **Fix applied:** `list[str] = ["*"]`.

### Design-Patterns critic

**Verdict from critic:** RESCUE.

- [block] DP-1 — Liskov violation on Probe ABC (`def _run(self, ctx)` vs frozen `async def run(self, repo, ctx)`). **Fix applied:** Notes-for-implementer §0 codifies the contract; AC-22 added as the architectural enforcement; Green skeleton rewritten.
- [block] DP-2 — Closed sum-type violation on `ScannerSkipped.reason`. **Fix applied:** principled reuse of `upstream_unavailable`; no ADR amendment needed; Notes §7 documents the closed-sum constraint for future contributors.
- [harden] DP-3 — `_lcov_scanner` + `open_capped` not reused. **Fix applied:** Implementation outline §1a — extend `_lcov_scanner` with `scan_records(...)` additive API; probe consumes both kernels.
- [harden] DP-4 — Missing `requires`, `declared_inputs` would silently break content-addressed caching. **Fix applied:** AC-3 declares full ABC attribute set; `test_declared_inputs_pinned` enforces the pin.
- [harden] DP-5 — Hidden state on `expected_rule_pack_version`. **Fix applied:** AC-20 + Implementation outline §3 — prior-run baseline read via `ctx.config["prior_run"]` + shared `_load_prior_value(name, key)` helper. The shared helper crosses the rule-of-three threshold for I/O specifically (3 call sites). Per-scanner comparator body stays inline.
- [harden] DP-6 — `_parse_lcov` shape disagreement between AC-5 (`Result[...]`) and Green skeleton (`tuple[..., str | None]`). **Fix applied:** Green skeleton uses `tuple[records, reason | None]` convention; Istanbul parser remains the only inline smart constructor; AC-5 narrative aligned.
- [nit] DP-7 — `CoverageFormat` newtype opportunity. **Surfaced** in Notes §10 (defer; Rule 2 says three-similar-lines is OK).
- [nit] DP-8 — `_wrap` 5-arg helper. **Surfaced** in Refactor section — module-level `_output` helper kept; inline-everything alternative is acceptable.

## Research briefs

None. No critic flagged `NEEDS RESEARCH`. All fixes have concrete sibling-code precedents in the repo (Layer-D probes, `_lcov_scanner`, `open_capped`, `_shared/scanner_outcome.py`, `tests/unit/test_probe_contract.py`).

## Conflict resolutions

1. **Coverage F4 (empty input → `ScannerSkipped`) vs Test-Quality**: synthesized to `ScannerRan(findings=())` because (a) the artifact IS present (not skipped), (b) it parses (not failed), and (c) zero-record artifacts are a real production case (a test suite that wrote no coverage). Resolution recorded in AC-18.

2. **Design-Patterns DP-2 (closed sum violation) options** (amend ADR vs reuse literal vs new variant): picked **reuse `upstream_unavailable`** because (a) "no upstream coverage artifact" is structurally the same shape as Layer-C's "SBOM upstream missing" already covered by `upstream_unavailable`, (b) amending 02-ADR-0006 introduces phase-out-of-scope work, (c) the closed sum's whole point is to keep the variant set small. Notes §7 documents the constraint so a future contributor doesn't reflexively widen.

3. **Design-Patterns DP-3 (lcov kernel reuse) vs Rule 2 (three-similar-lines)**: kernel reuse wins because `_lcov_scanner` already exists and is documented as the lcov primitive — this is the fifth consumer, not a new abstraction. The `scan_records(...)` API is **additive** (not an edit), respecting extension-by-addition.

4. **Design-Patterns DP-5 (`_load_prior_value` shared helper) vs Rule 2**: the **I/O** part is extracted (three call sites do identical filesystem reads → DRY at the I/O boundary). The **comparator body** stays inline in each scanner (Rule 2 — three similar 5-LOC bodies is fine, and each scanner's per-version-key concern is its own).

## Edits applied

### Edit 1 — Validation notes block prepended (Status: Ready → HARDENED)

### Edit 2 — AC-3 rewritten (full ABC attribute set + `name`/`_PROBE_ID: Final` precedent)

### Edit 3 — AC-5 rewritten (consume `_lcov_scanner.scan_records` + `open_capped`; no inline lcov parser; no inline size cap)

### Edit 4 — AC-6 rewritten (`reason="upstream_unavailable"`; closed-sum-honoring literal)

### Edit 5 — AC-7 rewritten (explicit `reason=None`; closed-sum honored)

### Edit 6 — AC-9 count corrected (7 → 8 Layer D schemas)

### Edit 7 — AC-13 rewritten (BLAKE3 pin replaces `git diff --name-only`)

### Edit 8 — AC-14 split into AC-14a (registry-level) + AC-14b (end-to-end through `IndexHealthProbe`)

### Edit 9 — AC-17 count corrected (15 → 16 Step-6 sub-schemas)

### Edit 10 — AC-18 added (empty-coverage edge case)

### Edit 11 — AC-19 added (lcov-wins precedence pin)

### Edit 12 — AC-20 added (freshness baseline data-flow; first-gather → `Fresh()`)

### Edit 13 — AC-21 added (`CoverageRecord` field set frozen; non-goal actively enforced)

### Edit 14 — AC-22 added (Probe ABC contract architectural test)

### Edit 15 — TDD plan rewritten end-to-end
- Test fixture helpers (`_snapshot`, `_ctx`, `_run`) documented in TDD-plan preamble
- Every test uses `asyncio.run(probe.run(repo, ctx))` with explicit `RepoSnapshot` + `ProbeContext`
- Parser tests pin actual `CoverageRecord` values (not `files_seen` counts)
- Oversized-file test monkeypatches `_MAX_BYTES` (no 50 MB disk write)
- Empty-coverage tests added (lcov + Istanbul)
- Both-files-present precedence test added
- `CoverageRecord` field-set architectural test added
- Probe-ABC-contract AST-walker test added
- Kernel-reuse AST-walker test added (`test_no_inline_size_cap_or_lcov_parser`)
- Determinism test added (two-gathers byte-identical)
- Property-based test added (`hypothesis` over unknown lcov prefixes)
- Sub-schema round-trip parametrized across all three `ScannerOutcome` variants
- `_PROBE_REGISTRY` reach replaced with `default_registry._entries` per Layer-D precedent

### Edit 16 — Freshness-registrations test rewritten with BLAKE3 hash pin

### Edit 17 — Rule-pack-drift integration test rewritten
- AC-14a (registry-level smoke) + AC-14b (end-to-end through `IndexHealthProbe`)
- AC-20 first-gather → `Fresh()` parametrized test
- `_make_drift_fixture` helper referenced (sibling Layer-B precedent)

### Edit 18 — Green skeleton rewritten
- `async def run(self, repo, ctx)`; `repo.root` (not `ctx.repo_root`)
- `from codegenie.types.identifiers import ProbeId` (correct path)
- Full ABC attribute set declared (`name`, `layer`, `tier`, `requires`, `declared_inputs`, etc.)
- Module-level `_PROBE_ID: Final[ProbeId]` (not a class attribute)
- `ProbeOutput` constructed with the full field set (`raw_artifacts=[]`, `duration_ms=...`, `warnings=[]`)
- Consumes `open_capped`, `_lcov_scanner.scan_records`, `safe_json.load`; no inline lcov parser; no inline 64-MB cap

### Edit 19 — Implementation outline rewritten
- §1: kernel-reuse contract documented
- §1a: additive `_lcov_scanner.scan_records(...)` API
- §2: 16 sub-schemas (not 15)
- §3: prior-run baseline lookup via `ctx.config["prior_run"]` + shared `_load_prior_value` helper

### Edit 20 — Refactor section rewritten (the Open/Closed seam is the design; rule-of-three signal for future scanners)

### Edit 21 — Files-to-touch extended
- `_lcov_scanner.py` (additive)
- `indices/registry.py` (or `_prior_lookup.py`) — `_load_prior_value` helper

### Edit 22 — Notes for the implementer extended
- §0 (new) — frozen Probe ABC contract
- §7 (new) — closed sum types are NOT extensible by addition (02-ADR-0006)
- §8 (new) — rule-of-three watch on freshness comparator
- §9 (new) — async-dispatch test infrastructure
- §10 (new) — `CoverageFormat` newtype opportunity (deferred)

## Verdict rationale

**HARDENED.** Three of four critics returned RESCUE on the strength of the Probe-ABC and closed-sum-type violations, but those failures are all in the prescribed *implementation details* (ACs, Green skeleton, TDD plan tests) — not in the story's *goal* or its *scope*. The Goal text reads cleanly against `phase-arch-design.md` §"Component design" #5 and §"Gap analysis" Gap 3; every AC traces to one of the three Goal clauses; the load-bearing design discipline (one file per Layer G scanner, `@register_index_freshness_check` Open/Closed seam, `IndexHealthProbe` byte-stable) is preserved. The skill's RESCUE bar is "fixes would require rewriting the goal" — that bar is not met here. All 22 findings have in-place edits applied to the story. The story is ready for the executor.

## Recommended next step

`phase-story-executor` to implement against the hardened story.
