# Validation report: S3-03 — Output sanitizer + atomic writer

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S3-03-sanitizer-writer.md`](../S3-03-sanitizer-writer.md)

## Summary

S3-03 lands the single chokepoint between a `ProbeOutput` and a persisted byte: `OutputSanitizer.scrub` (two passes — field-name regex + path scrub) and `Writer.write` (atomic raw-then-yaml publish with `0600`/`0700` modes and symlink refusal). The story's goal, ADR fidelity (ADR-0008 + ADR-0011), and out-of-scope were directionally correct, but the AC set and TDD plan had **five classes** of weakness:

1. **A triadic Writer-signature contradiction** between AC-5 (`envelope: dict`), `phase-arch-design.md §Output writer + sanitizer` (`envelope: dict`), and ADR-0008 §Consequences line 46 ("takes a `SanitizedProbeOutput`"), with implementer-notes line 188 acknowledging both — leaving the executor free to pick either reading.
2. **Thin tests with `...` bodies** — 8 of 10 test bodies were description-only. S3-02 validation explicitly burned this lesson one story ago (Edit 8 of `_validation/S3-02-probe-output-validator.md`) and S3-03 reverted to the antipattern.
3. **Critical load-bearing requirements buried in refactor notes**, not ACs: the recursive chmod tree-walk (edge case #6, the actual fix for `actions/cache`-restore mode flattening) and the `_csafe_warned` once-per-process semantic both lived in the refactor section.
4. **A missing global no-leak invariant** — every sanitizer test checked a single field; a mutant whose regex dropped `/home/` while keeping `/Users/` passed every example test. Phase 11 commits these YAMLs into real repos; this is the load-bearing security property.
5. **`errors` and `warnings` fields not scrubbed** — AC-3 only mentioned `schema_slice`. But probes emit `errors=["FileNotFoundError: /Users/danny/foo"]` which land in `repo-context.yaml` unchanged. Most likely real-world leak vector.

Three critics returned **46 findings** (16 block, 23 harden, 7 nit) with **zero `NEEDS RESEARCH` tags** — every fix was answerable from in-repo docs (ADR-0008, ADR-0010, ADR-0011, ADR-0007, `phase-arch-design.md` Edge cases #6/#7/#13, the S3-02 validation report) and local test idioms (`test_audit_models.py`, `test_cache_store.py`, `test_exec.py`, `test_logging.py`).

The validator applied edits in place:

- **Rewrote AC set end-to-end** — 10 ACs → 26 ACs, grouped into five sections (`SanitizedProbeOutput` shape, pass-1 secret rejection, pass-2 path scrubbing, Writer atomic publish, Writer symlink+filename safety + perms + tooling). Every new AC names one observable behavior; every AC traces back to a goal clause, an ADR consequence, an edge-case row, or an arch-design commitment.
- **Rewrote the TDD plan end-to-end as concrete runnable Python** — all `...` bodies replaced. Parametrized 5×6 = 30 secret-key/depth combinations + 5 benign-key cases; 5 depth-walk cases; 5 unsafe-filename cases; 3 symlink-victim cases. Mock-with-manager ordering check for fsync-before-replace; replace-spy for raw-then-yaml order; `structlog.testing.capture_logs` for event pinning per local idiom. Added a `test_output_paths.py` file the original story omitted.
- **Resolved the Writer-signature triadic contradiction** in favor of `envelope: dict` (the arch+AC reading). ADR-0008 §Consequences line 46's typed-enforcement promise is structurally undeliverable because the writer is downstream of an N-to-1 merge that loses per-probe typing; the typed-enforcement *intent* survives at the `scrub → SanitizedProbeOutput` step. Surfaced as ADR amendment follow-up (Nygard policy: amend the ADR text to match the synthesis-time relaxation).
- **Promoted the recursive-chmod tree-walk** from refactor note to AC-22 with a dedicated test (`test_writer_fixes_preexisting_loose_modes`) that pre-creates a `0644` file and asserts post-`Writer.write()` it's `0600`. This was the load-bearing fix for edge case #6; an executor reading only the original ACs would have shipped a one-file chmod that defeats the CI cache-restore guarantee.
- **Added a global no-leak invariant** (AC-12 + `test_no_path_leaks_anywhere_after_scrub`) walking every string in `schema_slice` + `errors` + `warnings` and asserting zero strings start with any forbidden prefix. Mutation-resistant: dropping any one alternative from the regex fails this test.
- **Added `errors`/`warnings`-field scrubbing** to AC-6, with dedicated tests. Probes' error messages were the most likely real-world leak vector.
- **Added `re.escape`, longest-prefix-wins, symlinked-`repo_root`, `repo_root` precondition, embedded-mid-string, username-segment-strip, and depth-N secret-key** ACs and tests (originally implicit in implementer-notes or absent).
- **Added `_csafe_warned` once-per-process** as AC-15 with a three-write test; the original AC-6 said "once" without disambiguating once-per-call vs once-per-process.
- **Added raw-artifact filename safety** (AC-21) — `../`, `/`, leading-`/`, empty, `.` all rejected with `ValueError`. Closes the chokepoint property of ADR-0008 against attacker-controlled raw names.
- **Added structlog event pinning** (AC-25) with `structlog.testing.capture_logs` — the four named events fire when expected and only then; happy-path emits zero.
- **Expanded `Depends on`** from `S2-05` to `S2-05, S3-02` — the structural dependency on `coordinator.validator.SECRET_FIELD_PATTERN` was implicit.
- **Added Validation notes block** under the story header summarizing every change.
- **Added `ADR-0010`** to the honored-ADRs line — the single-source secret-pattern guarantee crosses both ADR-0008 (chokepoint) and ADR-0010 (where the constant lives).
- **Expanded Out-of-scope** to explicitly defer: parent-directory fsync, Windows path scrubbing, mount points beyond the four declared, raw filename collision behavior, and individual-raw-artifact symlink refusal (covered by AC-21 + parent symlink check).

Three architectural follow-ups surfaced (not auto-fixed — outside this story's surgical scope per Rule 3):

1. **ADR-0008 §Consequences line 46** — amend "Writer.write takes a SanitizedProbeOutput" to reflect the merged-envelope reality. The typed-enforcement clause as written is structurally undeliverable across the N-to-1 merge.
2. **ADR-0011 line 39** — amend "every file and directory it creates" to "every file and directory in `output_dir`" to match edge case #6's actual requirement (AC-22 captures the broader scope).
3. **High-level-impl.md Step 3 line 111** — the sanitizer test count is undercounted (5 sanitizer tests + 3 paths tests now, not 3 sanitizer behaviors); refresh.

## Findings by critic

### Coverage critic — 15 findings (4 block, 9 harden, 2 nit)

- **F1 (block)** — Anchored regex misses embedded paths. `^(/Users/|...)` doesn't match `"see /Users/danny/foo.js"` strings in `errors`. Phase 11 commit leaks. **→ AC-5 (non-anchored) + AC-12 (no-leak invariant) + test `test_pass2_scrubs_embedded_path_in_error_string`.**
- **F2 (block)** — Paths outside `repo_root` undefined. `/Users/danny/somewhere-else/x` with `repo_root=/tmp/repo`: `Path.relative_to` raises; behavior is mute. **→ AC-9 (strip user segment, keep structural info) + tests for `/Users/`, `/home/`, `/root/` outside-repo cases.**
- **F3 (harden)** — `SanitizedProbeOutput` fields unspecified. Could ship with only `schema_slice` + `confidence`, dropping `errors`/`warnings`/`duration_ms`. **→ AC-2 (field-set parity) + `test_sanitized_probe_output_field_parity`.**
- **F4 (block)** — Writer signature contradiction (`envelope: dict` vs `SanitizedProbeOutput`). **→ AC-14 + follow-up to amend ADR-0008.**
- **F5 (harden)** — Partial-raw failure semantics undefined. **→ AC-18 + `test_writer_partial_raw_failure_no_envelope`.**
- **F6 (harden)** — Symlink-refusal scope only on `repo-context.yaml`, not `output_dir` or `raw/`. **→ AC-20 + parametrized three-victim test.**
- **F7 (block)** — chmod re-apply scope only in refactor note, not AC. **→ AC-22 + `test_writer_fixes_preexisting_loose_modes`.**
- **F8 (harden)** — `_csafe_warned` log-once ambiguous (per-call vs per-process). **→ AC-15 + three-write test.**
- **F9 (harden)** — Pass-1 idempotence semantics undefined. **→ AC-13 (idempotence on pass-1-clean inputs + non-identity assertion).**
- **F10 (harden)** — `repo_root = /` or prefix-of-itself. **→ AC-11 (precondition) + AC-10 (longest-prefix-wins) + three precondition tests + `test_pass2_repo_under_users_prefers_repo_prefix`.**
- **F11 (harden)** — `os.fsync` in AC-7 but no test. **→ AC-16 + `test_writer_fsync_called_before_replace`.**
- **F12 (harden)** — Empty inputs untested. **→ AC-24 + empty-input tests for both modules.**
- **F13 (harden) — promoted to load-bearing** — `errors` and `provenance` fields not scrubbed. Most likely real-world leak vector. **→ AC-6 (walks schema_slice + errors + warnings) + `test_pass2_scrubs_errors_field` + `test_pass2_scrubs_warnings_field`.**
- **F14 (nit)** — Exact `repo_root` match without trailing slash. **→ Covered by AC-9 + AC-10's longest-prefix rule.**
- **F15 (nit)** — AC-10 mypy strictness underspecified. **→ AC-26 (zero errors, zero `# type: ignore` in new code).**

### Test-Quality critic — 19 findings (10 block, 7 harden, 1 nit, 1 process-level block)

- **F1 (block)** — T1 mutation-survivable (any-error-passes). **→ Parametrized depth+key matrix, `exc.value.args[0]` pinning, benign-key negative matrix.**
- **F2 (block)** — No depth-N secret-key test. **→ `test_pass1_rejects_secret_key_at_any_depth` parametrized depth 1..5.**
- **F3 (block)** — T2 single-example hard-coded matches hard-coded. **→ Per-rule tests + AC-12 global invariant + AC-7 metachar test.**
- **F4 (block)** — T3 vague qualitative ("relative or stripped"). **→ AC-9 pins exact post-state; tests assert no `/Users/` prefix, no username, non-absolute result.**
- **F5 (harden)** — T4 depth-3 insufficient to kill a 2-level walker. **→ `test_pass2_walks_arbitrary_depth` parametrized 1..5.**
- **F6 (block)** — T5 idempotence trivially true on no-op `def scrub(x,_): return x`. **→ AC-13 requires non-identity assertion ("first scrub DID work") + idempotence; `test_scrub_is_idempotent_and_does_work`.**
- **F7 (block)** — T6 atomic replace wrong patch surface, "tmp may exist" too permissive, no fsync-before-replace check. **→ AC-16 + AC-19 + dedicated tests using `mock.patch.object(writer_mod.os, "replace")` and the manager-mock ordering technique.**
- **F8 (block)** — No global no-leak invariant. **→ AC-12 + `test_no_path_leaks_anywhere_after_scrub`.**
- **F9 (block)** — T7 modes only on top dir + yaml. **→ AC-22 + `test_writer_modes_applied_recursively_to_new_tree` + `test_writer_fixes_preexisting_loose_modes`.**
- **F10 (harden)** — T8 symlink refusal doesn't verify "no write attempted". **→ AC-20 + `test_writer_refuses_symlink_planted` parametrized across three victims, asserts sentinel bytes unchanged + no `.tmp` produced.**
- **F11 (harden)** — T9 CSafe fallback doesn't enforce once-per-process. **→ AC-15 + `test_writer_csafe_unavailable_logs_once_per_process` (three writes, exactly one event).**
- **F12 (block)** — T10 doesn't verify ordering. **→ AC-17 + `test_writer_replaces_raws_before_yaml` using `os.replace` spy.**
- **F13 (block)** — `SECRET_FIELD_PATTERN` single-source-of-truth has no test (S3-02 explicitly deferred verification to this story). **→ AC-3 + `test_sanitizer_uses_canonical_secret_pattern_by_identity` (identity check) + `test_sanitizer_module_does_not_redefine_secret_regex` (AST scan).**
- **F14 (harden)** — No test for `re.escape` on `repo_root`. **→ AC-7 + `test_pass2_escapes_regex_metachars_in_repo_root` (uses `repo.git` decoy).**
- **F15 (harden)** — No test for symlinked `repo_root`. **→ AC-8 + `test_pass2_resolves_symlinked_repo_root`.**
- **F16 (block)** — Writer signature contradiction (duplicates Coverage F4 / Consistency F1). **→ See AC-14 resolution.**
- **F17 (harden)** — Raw-artifact filename traversal undefined. **→ AC-21 + parametrized `test_writer_refuses_unsafe_raw_names` over five bad names.**
- **F18 (nit)** — structlog event emissions not tested. **→ AC-25 + four event-emission tests (sanitizer + writer happy-path-zero check).**
- **F19 (block, process-level)** — `...` test bodies; S3-02 validation already burned this lesson. **→ Full TDD-plan rewrite with concrete runnable Python.**

### Consistency critic — 12 findings (2 block, 7 harden, 3 nit)

- **F1 (block)** — Writer signature triadic contradiction. **→ Resolved per AC-14 + follow-up ADR-0008 amendment.**
- **F2 (block)** — `SECRET_FIELD_PATTERN` import seam has prose AC but no test (S3-02 hand-off). **→ AC-3 + AST-scan test.**
- **F3 (harden)** — `SanitizedProbeOutput` field shape underspecified. **→ AC-2 (duplicates Coverage F3).**
- **F4 (harden)** — `os.fsync` semantics ambiguous (file fd vs parent fd). **→ AC-16 pins file fd; parent-dir fsync explicitly deferred in Out-of-scope.**
- **F5 (harden)** — Symlink scope too narrow (duplicates Coverage F6). **→ AC-20.**
- **F6 (harden)** — AC-9 broader than ADR-0011 line 39. **→ AC-22 codifies broader scope; surfaced as ADR amendment follow-up.**
- **F7 (harden)** — Idempotence precondition unstated (duplicates Coverage F9 / Test-Quality F6). **→ AC-13.**
- **F8 (nit)** — `forbidden-patterns` lint trace missing. **→ Implementer-notes (no new AC; lint owned by S1-04).**
- **F9 (nit)** — `High-level-impl.md` Step 3 line 111 undercounts. **→ Surfaced as follow-up #3.**
- **F10 (nit)** — Determinism implicit, not explicit. **→ AC-13 (`test_scrub_is_deterministic_across_instances`).**
- **F11 (harden)** — Depends-on header missing S3-02. **→ Header updated.**
- **F12 (harden)** — `repo_root.resolve()` precondition unspecified. **→ AC-11 + three precondition tests.**

## Research briefs

**None.** Stage 3 was skipped. Every finding had a fix answerable from in-repo docs (ADRs 0007/0008/0010/0011, `phase-arch-design.md`, `final-design.md`, `localv2.md §4`, the S3-02 validation report) and local test idioms (`test_audit_models.py` for parametrize style; `test_cache_store.py` for `os.replace` patch + `structlog.testing.capture_logs`; `test_exec.py` for structlog event pinning; `test_logging.py` for capture_logs setup).

The codebase has no `hypothesis` dependency and Phase 0 does not list adding one (Rule 2 — no speculative dependency). Heavy parametrization (5×6 secret-key/depth + 5 depth-walk + 5 unsafe-filename + 3 symlink-victim cases ≈ 43 parametrized cases per file) delivers mutation-resistance equivalent to a property-based suite for this story's invariants.

## Conflict resolutions

- **Coverage F4 ≡ Test-Quality F16 ≡ Consistency F1** (Writer signature triadic contradiction): merged into AC-14 rewrite. `envelope: dict` wins (arch + AC agree; ADR-0008 §Consequences is the document with the structurally undeliverable clause). The typed-enforcement *intent* of ADR-0008 survives at the `OutputSanitizer.scrub → SanitizedProbeOutput` step. ADR-0008 §Consequences line 46 amendment surfaced as follow-up #1 (Nygard policy: when an ADR's *consequence* clause is structurally undeliverable as written, the synthesis-time relaxation should be re-codified in the ADR rather than the story silently diverging).
- **Coverage F7 ≡ Consistency F6** (chmod scope drift): merged into AC-22. AC takes the broader scope (recursive tree-walk including pre-existing files) — this is what edge case #6 (`phase-arch-design.md` line 783) actually requires. ADR-0011 line 39's narrower "creates" wording surfaced as follow-up #2.
- **Test-Quality F13 ≡ Consistency F2** (SECRET_FIELD_PATTERN import test): merged into AC-3 with two complementary tests — identity check (`is`, not `==`) plus AST scan (no `re.compile` in `sanitizer.py`). The dual approach closes both the trivial drift (re-compile with same pattern) and the regression drift (re-compile with a different pattern).
- **Coverage F9 ≡ Test-Quality F6 ≡ Consistency F7** (idempotence precondition): merged into AC-13. Idempotence applies only to pass-1-clean inputs; the test explicitly asserts non-identity ("first scrub DID work") so a no-op mutant doesn't pass; a test helper re-wraps `SanitizedProbeOutput` as `ProbeOutput` for the second call.
- **Coverage F1 ≡ Test-Quality F4 + F8** (no-leak invariant): merged into AC-5 (non-anchored regex) + AC-12 (global no-leak walk). The two ACs together are the load-bearing security property; AC-12's test is the canonical mutation-resistance gate.

## Edits applied (sequenced)

1. **Header** — Status `Ready → Ready — HARDENED`; Depends-on `S2-05 → S2-05, S3-02`; ADRs `ADR-0008, ADR-0011 → ADR-0008, ADR-0010, ADR-0011`; Validated date added; link to this validation report.
2. **Validation notes block** — appended under header summarizing the rewrite.
3. **Goal** — expanded to name `SanitizedProbeOutput` field-set parity, depth-N secret rejection, single-source `SECRET_FIELD_PATTERN`, `errors`/`warnings` scrubbing, the four declared prefixes, the under-repo vs outside-repo rewrite distinction, raw-then-yaml ordering, three-victim symlink refusal, and recursive chmod.
4. **Acceptance criteria** — rewritten end-to-end. 10 ACs → 26 ACs grouped into five sections.
5. **Implementation outline** — rewritten with the per-call regex shape, the `_assert_safe_name` helper, the `_csafe_warned` module flag, the `_fix_modes` recursive walker, and the precondition check.
6. **TDD plan** — rewritten end-to-end. 9 `...`-stubbed tests → ~50 concrete tests across three test files. Every `arrange` builds a real fixture; every assertion pins a concrete post-state; parametrize matrices enumerated.
7. **Files-to-touch** — expanded test-file descriptions; added `tests/unit/test_output_paths.py`.
8. **Out-of-scope** — expanded with parent-dir fsync deferral, Windows scope, mount-point set, raw filename collision behavior, and individual-raw-artifact symlink scope.
9. **Notes for the implementer** — rewritten with the embedded-scrub-is-intentional / username-segment-strip / `re.escape` / module-level-`_csafe_warned` / Writer-signature / `repo_root`-precondition decisions.
10. **Follow-ups surfaced** — new section listing the three architectural amendments (ADR-0008 §Consequences, ADR-0011 line 39, High-level-impl undercount) the validator surfaced but did not auto-fix.

## Verdict rationale

**HARDENED, not STRONG**: the original story had a structural contradiction (Writer signature) and a meta-pattern regression (`...` test bodies) that no critic alone could fix in isolation; the validator resolved both in place.

**HARDENED, not RESCUE**: the goal, ADR honoring, files-to-touch, and dependency chain were directionally correct. The story didn't need to be rewritten; it needed to be enforced.

A subsequent executor run against this hardened story can be evaluated against AC-1..AC-26 deterministically; every AC has at least one test that fails a named mutant; the load-bearing security property (AC-12 no-leak invariant) is mutation-resistant against single-prefix-drop, anchored-regex, and missing-field-scrub mutants.
