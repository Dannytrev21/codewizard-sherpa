# Validation report — S7-05 Property tests + portfolio integration sweep

**Date:** 2026-05-18
**Validator:** phase-story-validator skill (single-pass; consistency-critic findings dominated)
**Verdict:** **HARDENED**
**Reads:**
- Story: `docs/phases/02-context-gather-layers-b-g/stories/S7-05-property-and-portfolio-integration.md`
- Arch: `docs/phases/02-context-gather-layers-b-g/phase-arch-design.md` §"Testing strategy", §"Component design" #2/#5/#6/#11, §"Gap analysis" Gaps 2/4
- ADRs: 02-ADR-0006 (IndexFreshness location), 02-ADR-0007 (no plugin loader), 02-ADR-0009 (xdist veto), 02-ADR-0010 (RedactedSlice smart constructor)
- Code (the load-bearing read): `src/codegenie/indices/freshness.py`, `src/codegenie/probes/_shared/scanner_outcome.py`, `src/codegenie/probes/layer_c/runtime_trace.py`, `src/codegenie/depgraph/registry.py`, `tests/property/test_index_freshness_roundtrip.py`, `tests/property/test_sum_types_roundtrip.py`

## Verdict summary

HARDENED — the story's intent and scope are sound, but the original draft referenced multiple types and APIs that don't match the Phase-2 source tree as actually shipped. Without correction, the executor would have either spent attempts on non-existent surfaces (`TraceCoverage` class, `ScannerRan.fingerprints`/`findings_count`, `Result.Ok/Err` from the dep-graph registry) or silently duplicated existing tests (`test_scanner_outcome_roundtrip.py` vs. the shipped `test_sum_types_roundtrip.py`). Every weakness is fixable in place; none requires a re-run of `phase-story-writer`. The story is now consistent with the running code and the four ADRs it cites.

## Findings by critic

### Consistency critic (dominant — drove the largest set of edits)

| Severity | Finding | Resolution |
|---|---|---|
| `block` | Story AC-2 lists `DigestMismatch(last_traced, current_built)` and `CoverageGap(missing_files, indexed_files, total_files)`; shipped code is `DigestMismatch(expected, actual)` and `CoverageGap(files_indexed, files_in_repo)` | AC-2 rewritten with the shipped field names; TDD `_stringify` code sample uses the correct field names |
| `block` | Story AC-8/AC-9 reference `ScannerRan.findings_count` and `ScannerRan.fingerprints`; shipped `ScannerRan` has only `findings: list[Finding]`. `findings_count`/`fingerprints` live on `RedactedSlice` (ADR-0010) | AC-8 reframed to target `Finding(id, severity, metadata)` invariants the shipped strategies already exercise; AC-9 redirected to a `tests/unit/output/test_finding_redaction.py` companion test asserting `redact_secrets(...)` erases plaintext from `Finding.metadata`; `RedactedSlice` round-trip moves into a dedicated new file `test_redacted_slice_roundtrip.py` (AC-12) where every example is obtained via `redact_secrets` |
| `block` | Story AC-14/AC-15 assume `default_dep_graph_registry.lookup(...)` returns `Result.Ok|Err`; the shipped registry has no `Result` type — `dispatch()` raises `DepGraphRegistryError("no_strategy_for_ecosystem: <repr>")` and `has_strategy()` is the non-raising query | AC-14/AC-15 reframed to assert: (a) the documented prefix; (b) `has_strategy(member) == False`; (c) `registered_ecosystems() == frozenset()` as the Phase-2 invariant; (d) no other exception type ever bubbles. The "Phase 3 trip-wire" wording is preserved |
| `block` | Story AC-19..AC-24 reference a `TraceCoverage` Pydantic class with `total/completed/failed/skipped` fields and a `model_dump_json/model_validate_json` round-trip. The shipped surface is a pure function `_derive_trace_coverage_confidence(results) -> Literal[...]` plus a private `_AggregatedSlice` model. No `TraceCoverage` class exists | AC-19..AC-22 rewritten to target `_aggregate_scenarios(results, parsed) -> _AggregatedSlice` (partition + uniqueness invariants on the three name lists) and `_derive_trace_coverage_confidence` (closed-`Literal` totality + `unavailable iff len==0` canonical-empty case). File renamed `test_trace_coverage_invariants.py`. Implementer note documents the `# type: ignore[reportPrivateUsage]` choice |
| `harden` | Story planned `test_scanner_outcome_roundtrip.py` as a new file; the existing `tests/property/test_sum_types_roundtrip.py` (S5-01) already covers `ScannerOutcome` + `ScenarioResult` round-trip + per-element type identity | AC-7 reframed to extend the existing file in place (add `@settings(...)` decoration only); a new AC-37 names the coordination explicitly; "Files to touch" gets a deliberately-NOT-created entry; the duplication risk closes |
| `harden` | Story AC-7's strategy `_fresh = st.builds(Fresh)` would fail at construction — `Fresh` requires `indexed_at: datetime` | Resolved by reference to existing precedent: the shipped strategy uses `st.builds(Fresh, indexed_at=_aware_datetimes)`; AC-2 names the requirement |
| `harden` | Story AC-28 assumes `scripts/regen_golden.py --check --portfolio` exists; neither the script nor the `--portfolio` flag has shipped (S7-03 is HARDENED but not yet GREEN) | AC-28 grew a `pytest.mark.skipif` gate naming the missing flag; S8-03 lifts the skip when S7-03 lands the `--portfolio` mode |
| `nit` | "macOS `strace` warning" mentioned but not named | Stderr allowlist is now an explicit module-level tuple: `("skill_shadowed","strace_unavailable","image_digest_unresolved","external_docs_skipped")` |

### Coverage critic

| Severity | Finding | Resolution |
|---|---|---|
| `harden` | No AC asserts the gather process never crashes on a stderr keyword (`Traceback`/`Exception`) — original AC-26 only forbade `Traceback` | AC-26 now forbids both `Traceback` and `Exception` outside the explicit allowlist and prints the offending line on failure |
| `harden` | No AC pins fixture-tree purity (the canonical `tests/fixtures/portfolio/` could be silently dirtied by a misbehaving probe writing into the fixture directory rather than the tmpdir) | AC-31 now records a `_dir_sha256` snapshot of `tests/fixtures/portfolio/` at test start and asserts it unchanged at test end |
| `harden` | No AC closes the cross-test pollution gap for `default_dep_graph_registry` (a prior test that forgot `unregister_for_tests` could shift the Phase-2-zero-strategies invariant) | AC-14 specifies an autouse fixture asserting `registered_ecosystems() == frozenset()` before each example, with a failure message naming the polluter |
| `nit` | No AC closes the secret-redaction × `Finding.metadata` seam (only structural firewalls existed; no positive assertion that a plaintext secret threaded through `Finding.metadata` is erased by the writer) | New AC-9 — `tests/unit/output/test_finding_redaction.py` asserts zero plaintext substring matches after `redact_secrets` |

### Test-quality critic

| Severity | Finding | Resolution |
|---|---|---|
| `block` | AC-12's original wording was a paragraph-long dual-resolution (option A vs option B) that an executor would mis-implement | AC-12 is now a single clear path: dedicated `test_redacted_slice_roundtrip.py`, every example through `redact_secrets`, `TypeAdapter[RedactedSlice]` round-trip identity. The S7-04 structural firewall is named but not duplicated |
| `harden` | AC-32 wrote `tests/integration/portfolio/walltimes.json` into the repo unconditionally, dirtying the working tree on `make test` and tripping the pre-commit hook | Env-gated: writes only when `CODEGENIE_PORTFOLIO_WALLTIME_OUT` is set (CI sets it under `runner.temp`); otherwise prints to stdout. No repo-tree write |
| `harden` | AC-29 mixed `≤ 6 min` (CI) and `≤ 5 min target` (local) — two unverifiable thresholds | Single hard ceiling: `total_seconds <= 360` measured by the test itself; per-machine tolerance dropped |
| `harden` | AC-31 used `subprocess.run(["cp", "-R", ...])` — requires `cp` to be on the `ALLOWED_BINARIES` allowlist and bypasses the cross-platform stdlib | Replaced with `shutil.copytree` |
| `harden` | The `assert_never` test in TDD red used `Fresh()` (no arg) which doesn't construct under the shipped model | Code sample uses `Fresh(indexed_at=datetime(2026,1,1,tzinfo=UTC))` |
| `nit` | AC-35 said "implementer's call" between `database=None` vs. committing the database; the deliberately-deferred list explicitly forbids the commit option | AC-35 rewritten — `database=None` is mandatory; the commit option stays on the deferred list |

### Design-patterns critic

| Severity | Finding | Resolution |
|---|---|---|
| `harden` | AC-16 mock-strategy registration mentioned "decorator + unregister in teardown" but didn't name the existing test-only seam `unregister_for_tests` (which `default_dep_graph_registry` already exposes) | AC-16 explicitly uses `default_dep_graph_registry.unregister_for_tests(...)` in `finally:`; the autouse fixture pattern mirrors the S1-10 precedent. Implementer note added on "consume existing Open/Closed seams, do not invent new ones" |
| `harden` | Original AC-32 walltime artifact was a hidden Open/Closed cliff: S8-03's bench script silently inherits the file format. A future implementer could change the schema without breaking the producer test | Cross-story handoff documented in the implementer note + PR-description requirement; both producer and consumer share the env-var contract `CODEGENIE_PORTFOLIO_WALLTIME_OUT` |
| `nit` | Refactor section's "DO NOT extract a kernel" is correctly aligned with Rule 2 but didn't name the rule of three explicitly | Refactor section and "Patterns DELIBERATELY deferred" both call out "Rule of Three — wait for a fifth consumer before extracting" |
| `nit` | Story didn't surface that the property tests *consume* — never reinvent — three Open/Closed seams (`register_dep_graph_strategy`/`unregister_for_tests`, `redact_secrets`, `--warn-unreachable` overrides) | New "Design-pattern hooks already paid for by existing code" paragraph in Notes for implementer makes the seam-consumption discipline load-bearing |

## Research (Stage 3)

Skipped — no finding required external research. Every weakness reduced to "the story disagrees with the code in this repo." Mutation thinking, property-based pattern selection, and metamorphic invariants are all available in `tests/property/test_sum_types_roundtrip.py` (S5-01) and `tests/property/test_runtime_trace_freshness_purity.py` (S5-05); the editor reused those precedents directly.

## Edits applied

All edits were made to `docs/phases/02-context-gather-layers-b-g/stories/S7-05-property-and-portfolio-integration.md` in place. Summary of changed sections:

- **Header**: `Status` flipped to `HARDENED (validated 2026-05-18)`; new `Validation notes (2026-05-18)` block records the ten material corrections.
- **Goal**: rewrote the file-list to distinguish "extend in place" (existing files) from "new" — explicitly names the existing `test_sum_types_roundtrip.py` and `test_index_freshness_roundtrip.py`; adds the `test_redacted_slice_roundtrip.py` new file (was deferred in original "Patterns DELIBERATELY deferred"); replaces the `test_trace_coverage_well_formed.py` name with `test_trace_coverage_invariants.py`.
- **References — where to look**: corrected the field-name and class-name references to match shipped code; named the `--portfolio` flag's S7-03 dependency and the skipif gate that closes the timing gap.
- **Acceptance criteria**: AC-1..AC-37 — every block rewritten for code-reality consistency, with explicit values for budgets / allowlists / env vars previously left vague. AC-37 added for coordination.
- **Implementation outline**: 12 steps replacing the original 9, with each step naming the exact file path being created or extended.
- **TDD plan — Red**: TDD samples rewritten with correct field names (`expected/actual`, `files_indexed/files_in_repo`), correct `Fresh(indexed_at=...)` construction, real dep-graph dispatch contract (raises with prefix), and a portfolio sweep skeleton that uses `shutil.copytree`, env-gated walltime artifact, fixture-tree hash invariance, and explicit stderr allowlist.
- **Mutation-resistance witness table**: replaced 3 stale rows referencing `TraceCoverage`/`fingerprints` with 7 new rows covering the real attack surface (field-rename drift, ADR-0010 plaintext leak, `_aggregate_scenarios` partition violation, repo-tree dirtying, etc.).
- **Files to touch**: re-keyed to "extend" vs "new"; added a "Deliberately NOT created" row for `test_scanner_outcome_roundtrip.py`.
- **Out of scope** and **Patterns DELIBERATELY deferred**: `test_redacted_slice_roundtrip.py` removed from the deferred list (now in scope); `Result[T,E]` wrapper around dispatch added to deferred; conftest.py settings profile clarified as Rule-of-Three-deferred.
- **Notes for the implementer**: dropped the dead `TraceCoverage` reference; added the `# type: ignore[reportPrivateUsage]` justification, the env-var contract for walltimes, and the "consume existing Open/Closed seams" discipline.

## Why HARDENED (not RESCUE)

The story's goal — "every Phase-2 typed surface that participates in serialization has a Hypothesis round-trip property test; the portfolio sweep proves no fixture × probe combination crashes the gatherer" — is sound and traces directly to the arch's testing-strategy section and to ADRs 0006/0009/0010. The original draft's defects were uniformly "wrong specifics referencing aspirational/older API shapes," not structural disagreement with the goal. Edit-in-place was sufficient; the executor can now ship with the corrections.

## Why not STRONG

The original draft would have wasted ≥ 3 executor attempts on non-existent surfaces and would likely have shipped duplicate or broken tests. The verdict is HARDENED, not STRONG.

## Followups (not blocking this story)

- S8-03 must lift the `pytest.mark.skipif` on AC-28 when `scripts/regen_golden.py --check --portfolio` lands; the consumer contract is named in this story's PR description.
- A future Phase-3 PR that registers the first dep-graph strategy must update AC-14/AC-15 in place (the trip-wire is by design).
- If `tests/property/` grows past four files in Phase 3, extract a `tests/property/conftest.py` settings profile (Rule of Three trigger).
