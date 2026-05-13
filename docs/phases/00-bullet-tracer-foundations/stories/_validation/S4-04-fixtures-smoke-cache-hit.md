# Validation report — S4-04 (fixtures + smoke + cache-hit-on-second-run)

**Story:** [`../S4-04-fixtures-smoke-cache-hit.md`](../S4-04-fixtures-smoke-cache-hit.md)
**Date:** 2026-05-13
**Validator skill:** `phase-story-validator`
**Verdict:** **HARDENED**

The story's goal is sound and the architecture trace is intact, but four blockers and several harden-level smells were caught before the executor sees it. All four blockers are concrete additions or fixes; none of them required re-running `phase-story-writer`. The two most consequential — TQ-1 (monkeypatch blast radius) and TQ-2 (no cache-miss test) — would each have let an obviously-wrong implementation pass.

## Context summary

- **Goal (verbatim):** `pytest tests/smoke/test_cli_end_to_end.py -q` exits 0 with the suite covering `--help`, three fixtures (`empty_repo`, `js_only`, `polyglot`), and the cache-hit-on-second-run test (scandir count = 0, `executions["language_detection"]` is `CacheHit`, README.md edit between runs does not invalidate the cache).
- **ADRs honored (header):** ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0013.
- **Depends on:** S4-01 (LanguageDetectionProbe — Done; pinned to `import os` per its docstring), S4-02 (CLI gather + audit verify — Done).
- **Phase exit criteria contributed to:** Goals #1, #4, #8, #9 of `phase-arch-design.md §Goals`.

## Critic verdicts

| Critic | Verdict | Block | Harden | Nit |
|---|---|---|---|---|
| Coverage | HARDENED | 2 | 6 | 2 |
| Test-Quality | HARDENED | 2 | 5 | 1 |
| Consistency | HARDENED | 0 | 3 | 3 |

No `NEEDS RESEARCH` flags; Stage 3 skipped.

## Blocker findings (must-fix before executor sees the story)

### COV-4 — Envelope-level required YAML fields are not asserted

`phase-arch-design.md §Goals` Goal #1 enumerates the YAML's required fields: `schema_version`, `generated_at`, `repo.root`, `repo.git_commit`, plus `probes.language_detection.language_stack.{counts, primary}`. The original ACs assert only `language_stack.{counts, primary}`. The four envelope fields had no AC trace at all. Notes line 206 flagged the risk but didn't promote it to an AC. Phase 0 exit criterion #1 cannot be satisfied without these fields.

**Fix:** new AC `test_envelope_required_fields_present` plus a tightened post-parse assertion in `test_gather_js_only`. Pins `schema_version` as non-empty string, `generated_at` as ISO-8601-parseable UTC, `repo.root` as a sanitizer-scrubbed string (no `/Users/` / `/home/` / `/root/`), `repo.git_commit` as `^[0-9a-f]{7,40}$` (or `null` for the non-git empty_repo fixture).

### COV-5 — `codegenie audit verify` is never exercised end-to-end

Goal #9 of phase-arch-design and the Step 4 done-criteria list in `High-level-impl.md` both require `codegenie audit verify` to report zero mismatches on the smoke run. The story doesn't touch `audit verify` anywhere.

**Fix:** new AC `test_audit_verify_smoke_run` — gather js_only, then invoke `cli ["audit", "verify"]` against the same `.codegenie/` tree; exit 0; stdout reports the zero-mismatch sentinel; the run-record JSON exists and parses.

### TQ-1 — Monkeypatch blast radius (load-bearing test is observably flaky)

The story's red-test does `monkeypatch.setattr(ld_mod.os, "scandir", counting_scandir)`. Because `ld_mod.os IS os` (the same module object), this mutates `os.scandir` *globally* for the duration of the test, not just within the probe module. Any other code path that happens to call `os.scandir` during the warm run (cache layer enumerating blobs, writer enumerating `.codegenie/`, pytest fixtures) increments the counter, producing false-RED on a correct cache-hit implementation. S4-01's module docstring asserts the patch target works, but it conflates "mutate the `os` module attribute" with "patch within `language_detection` only" — they are not the same.

**Fix:** replace the `os` *name binding* on the language_detection module with a `types.SimpleNamespace` shim that carries every attribute of `os` plus a patched `scandir`. Only `codegenie.probes.language_detection.os.scandir` is the counting wrapper; every other `os.scandir` caller is untouched. AC and TDD snippet updated to this approach. S4-01's docstring guidance ("import os") still holds — the test just routes the patch through the module-local name rather than the global one.

### TQ-2 — No test pins the *negative* of the cache invariant

Every AC in the original story asserts "cache hits when an *untracked* file is edited." A trivially wrong implementation that always returns `CacheHit` (e.g., the coordinator loads the last `GatherResult` from disk unconditionally) passes every single AC. The cache invalidation direction is unverified.

**Fix:** new AC + TDD red-test `test_cache_miss_on_tracked_input_edit`. Same flow as the hit test, but edits a `.js` file (or adds `d.js`) between runs. Asserts `executions == "Ran"` via the `probe.success` structlog event (not `probe.cache_hit`), scandir counter > 0, and `probe.cache_hit` event absent. Metamorphic pair with the existing test: untracked edit ⇒ HIT; tracked edit ⇒ MISS.

## Harden-level findings applied

| ID | Issue | Fix applied |
|---|---|---|
| COV-1 / TQ-8 | `--help` AC bundles two invocations under one exit-code assertion; "0/2/3/5/6 in output" is too loose | Split into explicit `gather --help` and group-level `--help` assertions; match `re.search(r"\\bexit\\s+(code\\s+)?%d\\b" % n, output)` for each documented exit code. |
| COV-2 / CON-2 | `executions["language_detection"] is CacheHit` is unreachable from a CLI smoke (no JSON mode in S4-02; coordinator's structlog event carries `probe`/`cache_key` only) | Collapsed to the achievable signal: assert `probe.cache_hit` event fired with `probe="language_detection"` and `probe.success` did NOT fire for this probe on the warm run. The original AC about `GatherResult.executions` is reworded as a context note. |
| COV-3 | No assertion that the cache *key* didn't change across runs | Added AC: cold and warm runs both emit a `probe.cache_hit`-or-`probe.success` event carrying `cache_key=...`; the two key values are byte-equal. Requires the coordinator's `probe.success` event to also carry `cache_key`; flagged in the Notes as a gap-check before implementation. |
| COV-6 / TQ-3 | Polyglot AC says "contains keys for every language present" but doesn't pin counts or primary value | Tightened to exact dict: `counts == {"go": 1, "javascript": 1, "python": 1, "rust": 1, "typescript": 1}` and `primary == "go"` (alpha-first of the max-count tie set, per S4-01). |
| COV-7 | empty_repo allows `primary in (None, "")` — two sentinels for one state | Pinned to `primary is None` per S4-01 docstring line 37. Added envelope-fields assertion. |
| COV-8 / TQ-5 | "Asserted via os.stat in at least one smoke test" is vague | Pinned permissions assertion to `test_gather_js_only` specifically; recursively walks `<fixture>/.codegenie/` via `rglob("*")`; uses `stat.S_IMODE`. Same for sanitizer scan. |
| COV-10 | Coverage gate AC doesn't pin the 75% branch threshold numerically | Pinned `--cov-fail-under=85` (line) AND verified branch threshold of 75% per Goal #8. Added negative check: no `# pragma: no cover` added in this PR's diff. |
| TQ-4 | js_only AC doesn't enforce closed-world counts | Added `set(counts.keys()) == {"javascript"}`; matches S4-01's `test_counts_js_fixture` convention. |
| TQ-6 | `capture_logs()` may miss events if CLI re-initializes structlog inside the runner | Added test-side fix: a `tests/conftest.py` autouse fixture pins structlog config to the testing chain before the CLI re-initializes; documented in the TDD plan. |
| CON-1 | Story hedged on `import os` vs `from os import scandir`; S4-01 is Done and chose `import os` | Stripped every "or the bare-name scandir if S4-01 imported from os import scandir" hedge across the AC list, implementation outline, TDD snippet, and Notes. |
| CON-3 | Sanitizer absolute-path scan referenced `str(tmp_path)` but the sanitizer scrubs the analyzed-repo abs path | Reworded scans to use `str(fixture)` (the dir passed to `gather`), with `str(tmp_path)` retained as a superset belt-and-suspenders. |
| CON-4 | Story tells implementer to remove `--cov-fail-under=0` from `pyproject.toml`, but the carve-out is actually in `.github/workflows/ci.yml:98` | Corrected target: edit `.github/workflows/ci.yml` to drop the `--cov-fail-under=0` override on the test job; `pyproject.toml:162` is already at `--cov-fail-under=85`. Also removed the TODO comment at ci.yml:83–84. |

## Nit-level findings (acknowledged inline, not blocking)

- **COV-9** — Added a one-line clarification to Out-of-scope: pyyaml C-extension fallback path is covered by S3-03's `tests/unit/test_output_writer.py`, not by smoke.
- **CON-5** — Added a one-line clarification to the Context section: ADR-0007 and ADR-0010 are honored transitively (via S4-01's probe and S2-02's snapshot test) and not asserted directly here.
- **CON-6** — Added a Notes paragraph: the sanitizer AC scans the on-disk YAML only; structlog payload sanitization is per-call-site (S4-01 AC-4 covers it for LanguageDetectionProbe; S4-05 owns adversarial log-leak tests).
- **TQ-7** — Acknowledged in the Notes that a richer hypothesis-driven metamorphic family belongs to S5-01; the current pair (TQ-2 + the existing hit test) pins both directions of the invariant in two specification-by-example tests.

## Edits applied to the story

The story file was edited in place — see the diff for `S4-04-fixtures-smoke-cache-hit.md` in the same commit. Summary of structural changes:

1. New `Validation notes` block under the header, listing date, verdict, and the four block-level findings.
2. AC list rewritten: original ten ACs expanded to fifteen; the two ambiguous wordings around `executions` and monkeypatch scoping were tightened or split.
3. Implementation outline gained three new steps (envelope assertion, audit-verify smoke, cache-miss test) and the coverage-gate step now points at `.github/workflows/ci.yml`.
4. TDD plan's red-test snippet rewritten with the `SimpleNamespace`-shim monkeypatch and the warm-run `probe.success`-absent assertion; a new red-test snippet for `test_cache_miss_on_tracked_input_edit` added.
5. Files to touch: added `.github/workflows/ci.yml`; corrected `pyproject.toml` row to "verify only (no edit needed)".
6. Notes: stripped `from os import scandir` hedge, added paragraphs on TQ-6 (logging config order) and CON-6 (sanitizer scope).

## Verdict rationale

The goal is well-scoped, the architecture trace is sound, and every AC traces to either the Goal or an honored ADR after the edits. The two blockers around the monkeypatch and the missing cache-miss test were the kind of issue the executor's Validator pass *might* have surfaced after a wasted implementation attempt; catching them here costs less. HARDENED — ready for the executor.

## Open questions surfaced (not blocking; flagged for executor)

- **Q1:** Does the coordinator's `probe.success` structlog event carry `cache_key=...`? COV-3's assertion ("cold and warm cache keys are byte-equal") depends on it. If not, the executor needs to either (a) ask S3-05 to add the field, or (b) drop the byte-equality assertion (the metamorphic TQ-2 pair plus the event-presence assertion still pin the invariant well).
- **Q2:** Does `codegenie audit verify` print a deterministic "0 mismatches" sentinel, or just exit 0? If just exit 0, the AC's `"0 mismatches" in stdout` check needs softening to "exit 0 + run-record parses". Recommend checking S3-06 / S4-02 first.
