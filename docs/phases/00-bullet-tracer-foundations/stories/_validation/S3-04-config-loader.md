# Validation report: S3-04 — Config loader + defaults

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S3-04-config-loader.md`](../S3-04-config-loader.md)

## Summary

S3-04 lands the four-source config merge (`defaults < ~/.codegenie/config.yaml < <repo>/.codegenie/config.yaml < cli_overrides`) with fail-loud-on-unknown-keys and a `difflib`-driven "did you mean?" suggestion — a tiny surface (3 files, ~80 LOC) but a load-bearing one because every Phase 0 component reads `Config`. The goal, file layout, and out-of-scope were directionally correct, but the AC set and TDD plan had **six classes** of weakness:

1. **Three test bodies were `...`** — the S3-02 and S3-03 validations explicitly burned this antipattern one and two stories ago; S3-04 reverted to it (`test_cli_overrides_repo_yaml`, `test_env_var_expansion_off`, `test_provenance_logged_at_debug`).
2. **Wrong testing harness** — the original `test_provenance_logged_at_debug` used `caplog`, but this codebase's `configure_logging` (S2-01) wires structlog with a `WriteLoggerFactory` to stderr; `caplog` does NOT capture structlog events. The test would have silently no-op'd, a Rule 12 "fail loud" violation. The adjacent idiom in `tests/unit/test_exec.py:285` uses `structlog.testing.capture_logs`.
3. **`ConfigError` failure surface was under-ACed** — `phase-arch-design.md §Config / Failure behavior` (line 434) and `final-design.md §2.13` commit the loader to `ConfigError` on **three** failure modes (unknown key, YAML parse error, type mismatch); the original story only ACed unknown-key. YAML parse error and type-mismatch wrapping were buried in implementer-notes.
4. **A 4-source precedence chain (6 pairwise relationships) tested on 1 pair** — only `repo > user` was exercised; `user > defaults`, `repo > defaults`, `cli > defaults`, `cli > user`, and `cli > repo` were untested. A mutant `merged = defaults | cli | repo | user` (cli losing to user) passed every test.
5. **Two security invariants buried in implementer-notes, not enforced by tests** — env-var-off (line 154) and `yaml.safe_load`-only (refactor note line 128). S3-03 had already set the precedent: single-source-of-truth security invariants belong in AST-scan tests, not prose.
6. **Vocabulary drift between story and design** — provenance label set `("defaults", "user_yaml", "repo_yaml", "cli")` vs `final-design.md §2.13` and `§4 step 4`'s `("defaults", "global", "repo", "cli")`; provenance scope "non-default fields only" vs design's "every field"; error-message format ambiguity between Goal and AC-5; the env-var-off attribution conflated `auto_envvar_prefix=None` (S4-02 territory) with `os.path.expandvars` avoidance (loader territory).

Three critics returned **42 findings** (13 block, 21 harden, 9 nit) with **zero `NEEDS RESEARCH` tags** that survived synthesis — Coverage F13's question on how to verify env-var-off was answered in-line by Test-Quality F6's AST-scan + spy idiom. Every other fix was answerable from in-repo docs (`final-design.md §2.13`, `phase-arch-design.md §Component design / Config` line 422, `§Harness / Configuration` line 760, ADR-0012, `High-level-impl.md` Step 3) and local test idioms (`test_exec.py:285,308`, `test_logging.py`, `test_audit_models.py`).

The validator applied edits in place:

- **Rewrote the AC set end-to-end** — 8 ACs → 21 ACs, grouped into seven sections (A: dataclass shape, B: source precedence, C: YAML parsing safety, D: unknown-key check, E: env-var-off, F: provenance, G: code hygiene + metamorphic relations). Every new AC names one observable behavior and traces back to a Goal clause, a `final-design.md §2.13` line, a `phase-arch-design.md` paragraph, or an implementer-note that was previously buried.
- **Rewrote the TDD plan end-to-end as concrete runnable Python** — all `...` bodies replaced. Added shared fixtures (`write_user_yaml` with `monkeypatch.setattr(Path, "home", ...)`, `write_repo_yaml`) so no test ever touches the developer's real `~/.codegenie/`.
- **Added a parametrized precedence matrix** (8 rows covering every adjacent pair + a 3-way + the defaults-only baseline) — every adjacent-swap mutant in the 4-source chain fails at least one row.
- **Added a separate user-yaml-only test** — closes the "reads only repo YAML" mutant that the override-chain tests left alive.
- **Added a disjoint-keys union test** — closes the "repo YAML replaces user YAML wholesale" mutant.
- **Added an AST scan for `yaml.safe_load`-only** (AC-5 + `test_loader_uses_only_yaml_safe_load`) banning `yaml.load`, `yaml.unsafe_load`, `yaml.full_load`. CVE-2017-18342-class regression vector closed structurally.
- **Added an AST scan for env-var-off** (AC-13 + `test_loader_module_does_not_reference_env_expansion_apis`) banning `os.path.expandvars`, `string.Template`, `os.path.expanduser`, `os.environ`, `os.getenv` on YAML values. Mirrors S3-03's `SECRET_FIELD_PATTERN` single-source-of-truth idiom.
- **Added a spy-on-merged-dict test** (AC-14 + `test_loader_preserves_dollar_literal_in_merged_dict`) — installs `$ENV_VAR=999` in the environment, writes `cache_ttl_hours: "$ENV_VAR"` to repo yaml, spies on `_typed_construct` to capture the merged dict, and asserts the literal `"$ENV_VAR"` survived. The spy is necessary because Phase 0's three fields are all primitive-typed; without a string field shape, only the merged-dict-pre-construction step can observe the unexpanded literal.
- **Promoted three implementer-notes to ACs**: parse-error wrap (AC-8), type-mismatch wrap (AC-9), and empty/null YAML normalization (AC-6) each got dedicated tests with `__cause__` chaining assertions (Rule 12 — fail loud + preserve traceback).
- **Added a top-level non-mapping YAML check** (AC-7) — `yaml.safe_load("- a\n- b\n")` returns a list; the original loader would have crashed with a confusing `TypeError` inside `dict.update`. AC-7 makes this an explicit `ConfigError` naming the file path + the actual top-level type.
- **Pinned the error-message format** as `^unknown key '<k>'; did you mean '<closest>'\?$` via a module-level regex `UNKNOWN_KEY_FORMAT` (AC-11) — the swap mutant `f"unknown key: {suggestion}; did you mean {key}?"` fails the regex's group ordering.
- **Pinned the no-close-match clause omission** (AC-12 + `test_unknown_key_no_close_match_omits_did_you_mean`) — the mutant that always appends `"; did you mean: ?"` (empty) used to pass every "happy path" suggestion test.
- **Pinned the suggestion specificity** (`test_unknown_key_suggestion_is_single_closest_match`) — asserts other declared field names do NOT appear in the message, killing the mutant that dumps the entire `_known_fields()` list.
- **Pinned the frozen-dataclass invariant** (AC-1 + `test_config_is_frozen_dataclass_with_pinned_defaults`) — `Config.__dataclass_params__.frozen is True` + `FrozenInstanceError` assertion. The `frozen=True → frozen=False` one-keyword regression now fails loudly. Matches the precedent in `tests/unit/test_exec.py:245`.
- **Pinned the default values** (AC-20 + same test) — silent default-value drift is a load-bearing-commitment-violation alarm (ADR-0004 makes `enable_audit: True` semantically load-bearing, even though the loader is just plumbing).
- **Fixed the provenance harness** (AC-16) — `structlog.testing.capture_logs` replaces `caplog`. Added a second provenance test (`test_provenance_event_when_nothing_overrides_labels_all_as_defaults`) — covers the defaults-only case the original story's "non-default only" narrowing would have failed.
- **Aligned provenance vocabulary** with `final-design.md §2.13` — labels are now `("defaults", "global", "repo", "cli")`, not `("defaults", "user_yaml", "repo_yaml", "cli")`. Rule 11: match the design.
- **Broadened provenance scope** to "every declared field" per `phase-arch-design.md §Harness / Configuration` line 760 + `final-design.md §2.13` line 318 — original AC said "each non-default field's source", a story-local narrowing.
- **Pinned `Path.home()` as the user-yaml resolver** (AC-4) — not `os.environ["HOME"]` (Windows-fragile). Tests monkeypatch `Path.home` so they're hermetic.
- **Added cold-start budget protection** (AC-18 + `test_loader_package_does_not_import_pydantic_or_jsonschema_or_blake3_at_top_level`) — the loader is on the CLI startup path; an accidental `import pydantic` at the top of `loader.py` would shred `codegenie --help` p95. Mirrors the `import-linter` discipline from `High-level-impl.md` Step 1.
- **Added a metamorphic relation** (AC-21 + `test_cli_default_value_override_is_metamorphic_equal_to_no_override`) — `load_config(r, {})` and `load_config(r, {"max_concurrent_probes": 8})` produce equal `Config` instances; provenance allowed to differ. Distinguishes value-equality (AC-21) from source-equality (AC-15) — a confusion that frequently bites config code.
- **Added a re-export sanity test** (AC-19 + `test_config_package_reexports`) — catches the "forgot to add it to `__init__.py`" mutant.
- **Added `ADRs honored: ADR-0012`** — the bare `yaml.load(...)` ban in the `forbidden-patterns` hook lives in ADR-0012 (subprocess + forbidden-patterns). AC-5 is the test-side enforcement at the package level.
- **Added a "See also: S4-02" header** — cross-story coupling for env-var-off: the loader's half (AC-13/14) covers the YAML-value path; S4-02's `auto_envvar_prefix=None` covers the click-flag path. Without explicit cross-reference, the executor could ship S3-04 green while S4-02 leaves click expansion on (an undetected leak).
- **Expanded Out-of-scope** to explicitly defer: property-based testing of the suggestion algorithm (declined for 3 fields), YAML 1.1 boolean truthiness ergonomics, parent-directory fsync, symlinked `~/.codegenie/`.
- **Added Validation notes block** under the story header summarizing every change.

Three architectural follow-ups surfaced (not auto-fixed — outside this story's surgical scope per Rule 3):

1. **`final-design.md §2.13` line 316** says "Levenshtein" but every Python implementation will reach for `difflib.get_close_matches` (Ratcliff-Obershelp ratio, not edit distance). Either edit the design line to "edit-distance-style suggestion via `difflib.get_close_matches`" or vendor a `Levenshtein` / `rapidfuzz` dependency — pick one and lock it in the design once, not per-story.
2. **Provenance label vocabulary** (`defaults`/`global`/`repo`/`cli`) is referenced across `final-design.md §2.13`, `§4 step 4` (line 418), and `phase-arch-design.md §Harness / Configuration` (line 760) — lock the spelling in one canonical place and have downstream stories cite it. The story-author drift (`user_yaml`/`repo_yaml`) hints this isn't load-bearing-locked yet.
3. **No ADR codifies env-vars-off in Phase 0 → re-enabled in Phase 9.** Currently a prose commitment in `phase-arch-design.md §Harness / Configuration` (line 760) and a click-level flag note in `final-design.md`. An ADR-of-record would lock the path-traversal close in before Phase 9 has to revisit, and clarify which components in Phase 9 are allowed to opt in.

## Findings by critic

### Coverage critic — 14 findings (4 block, 9 harden, 1 nit; 0 needs-research after synthesis)

- **F1 (block)** — No AC asserts CLI-override precedence vs repo-yaml/user-yaml is *observable*. **→ AC-3 + parametrized 8-row matrix.**
- **F2 (harden)** — Missing "user-yaml-only field survives" AC. **→ `test_user_yaml_only_field_survives_when_no_repo_yaml`.**
- **F3 (block)** — Type-mismatch / coercion behavior unspecified. Dataclasses don't enforce types at construction; `max_concurrent_probes="eight"` would succeed silently. **→ AC-9 + `_typed_construct` per-field `isinstance` check + `test_type_mismatch_wraps_typeerror_with_cause`.**
- **F4 (block)** — Malformed YAML (`yaml.YAMLError`) behavior unspecified. **→ AC-8 + `test_malformed_yaml_wraps_yaml_error_with_cause`.**
- **F5 (block)** — YAML top-level not a mapping (list/scalar) unspecified. **→ AC-7 + parametrized `test_yaml_top_level_must_be_mapping`.**
- **F6 (harden)** — Empty/null YAML normalization buried in implementer notes. **→ AC-6 + parametrized `test_empty_or_null_yaml_treated_as_empty_mapping` (4 payloads).**
- **F7 (harden)** — Unknown-key suggestion not asserted for CLI source. **→ `test_unknown_cli_key_format_offender_before_suggestion` parallel to YAML source.**
- **F8 (harden)** — "No close match" suggestion fallback in notes only. **→ AC-12 + `test_unknown_key_no_close_match_omits_did_you_mean`.**
- **F9 (harden)** — Suggestion correctness (single closest, not enumeration) not asserted. **→ `test_unknown_key_suggestion_is_single_closest_match`.**
- **F10 (harden)** — `repo_root` non-existent / not-a-dir behavior unspecified. **→ AC-10 + `test_missing_files_and_missing_repo_root_fall_through`.**
- **F11 (harden)** — Frozen-dataclass invariant untested. **→ AC-1 + frozen + FrozenInstanceError assertion in `test_config_is_frozen_dataclass_with_pinned_defaults`.**
- **F12 (harden)** — `Path.home()` vs `$HOME` not pinned. **→ AC-4 + `monkeypatch.setattr(Path, "home", ...)` fixture pattern.**
- **F13 (block, originally NEEDS RESEARCH)** — Env-var-off AC has no observable contract; test body is a placeholder. **Resolved in-line by Test-Quality F6's AST-scan + `_typed_construct` spy idiom. → AC-13 + AC-14 + two tests.**
- **F14 (harden)** — Disjoint-key merge (union) not tested. **→ `test_disjoint_keys_across_sources_yield_union`.**
- **F15 (nit, declined as covered)** — Provenance default-source labeling. Resolved by aligning with `final-design.md §2.13` — all fields included, defaults labeled `"defaults"`. **→ AC-15 + `test_provenance_event_when_nothing_overrides_labels_all_as_defaults`.**
- **F16 (harden)** — Provenance log content asserted only by event name. **→ AC-15 exact-dict-equality assertion.**
- **F17 (nit)** — Default-source labeling in provenance ambiguous. **→ Pinned to "every field, `defaults` for un-overridden".**
- **F18 (nit)** — Error message format drift between Goal and AC-5. **→ Goal + AC-11 + UNKNOWN_KEY_FORMAT regex aligned.**

### Test-Quality critic — 17 findings (8 block, 7 harden, 2 nit)

- **F1 (block)** — Three test bodies are `...`. **→ Full TDD-plan rewrite with concrete Python.**
- **F2 (block)** — `caplog` is the WRONG harness for structlog `config.loaded` assertion. **→ AC-16 + `structlog.testing.capture_logs()` per `test_exec.py:285` idiom.**
- **F3 (block)** — `test_cli_overrides_repo_yaml` exercised 1 of 6 pairwise orderings. **→ 8-row parametrized matrix in `test_precedence_pairwise_matrix`.**
- **F4 (harden)** — `test_defaults_only_when_no_yaml_and_no_overrides` doesn't check `isinstance(cfg, Config)` or frozen-ness. **→ AC-1 + AC-20 + `test_config_is_frozen_dataclass_with_pinned_defaults`.**
- **F5 (harden)** — `test_missing_yaml_files_are_not_errors` is tautological (`is not None`). **→ `test_missing_files_and_missing_repo_root_fall_through` with `cfg == Config()`.**
- **F6 (block)** — `test_env_var_expansion_off` body is `...` AND the design comment is wrong about how to verify it. Phase 0 has no string field, so the right verification is on the merged-dict pre-construction. **→ AC-13 (AST scan) + AC-14 (spy) + `test_loader_module_does_not_reference_env_expansion_apis` + `test_loader_preserves_dollar_literal_in_merged_dict`.**
- **F7 (harden)** — Unknown-key tests don't pin error message format. **→ UNKNOWN_KEY_FORMAT regex + format-assertion in 4 tests.**
- **F8 (harden)** — Missing tests for `yaml.safe_load(None)`/`""`/comment-only → `{}`. **→ AC-6 + parametrized test (4 payloads).**
- **F9 (block)** — `test_provenance_logged_at_debug` is missing, vague, AND uses wrong harness. **→ AC-15 + AC-16 + two `capture_logs` tests pinning per-field source dict.**
- **F10 (harden)** — `yaml.safe_load` enforcement isn't tested. **→ AC-5 + `test_loader_uses_only_yaml_safe_load` AST scan.**
- **F11 (harden)** — `TypeError → ConfigError` wrap (notes line 155) is untested. **→ AC-9 + `test_type_mismatch_wraps_typeerror_with_cause` + `__cause__` chain assertion.**
- **F12 (nit)** — `__init__.py` re-exports untested. **→ AC-19 + `test_config_package_reexports`.**
- **F13 (nit, declined)** — Property-based test for "did you mean" overkill for 3 fields. **→ Declined in Out-of-scope.**
- **F14 (harden)** — `Path.home()` injection idiom unspecified. **→ TDD plan Test fixtures section + `write_user_yaml` fixture.**
- **F15 (harden)** — No metamorphic relation on "cli={} vs cli={default}" idempotence. **→ AC-21 + `test_cli_default_value_override_is_metamorphic_equal_to_no_override`.**
- **F16 (nit)** — `enable_audit` YAML boolean parsing footguns. **→ Implementer-notes mention; AC-9 covers the type-mismatch path for quoted-string `"yes"`. YAML 1.1 truthiness ergonomics deferred to Out-of-scope.**
- **F17 (block, process-level)** — `...` test bodies; S3-02/S3-03 validations already burned this lesson. **→ Full TDD-plan rewrite (F1).**

### Consistency critic — 9 findings (1 block, 5 harden, 3 nit)

- **F1 (harden)** — Provenance label vocabulary drifts from `final-design.md §2.13`. **→ AC-15 labels aligned to `(defaults, global, repo, cli)`.**
- **F2 (harden)** — AC-7 says "each non-default field" but arch says "each field". **→ AC-15 broadened to all declared fields.**
- **F3 (block)** — `ConfigError` surface narrower than `phase-arch-design.md §Config / Failure behavior` (line 434). Three failure modes documented, one ACed. **→ AC-8 (parse error) + AC-9 (type mismatch) + AC-7 (non-mapping) added.**
- **F4 (harden)** — "Levenshtein" vs `difflib` algorithm drift. **→ Implementer-notes paragraph + Validation follow-up #1.**
- **F5 (nit)** — "ADRs honored: —" is correct but misses ADR-0012's relevance. **→ Header updated to `ADRs honored: ADR-0012`.**
- **F6 (harden)** — `auto_envvar_prefix=None` claim conflates click-level (S4-02) with loader-level (this story). **→ Context paragraph rewritten + AC-6 rewritten + AC-13 + "See also: S4-02" cross-reference added.**
- **F7 (nit)** — Loader must not import pydantic transitively (cold-start budget). **→ AC-18 + `test_loader_package_does_not_import_pydantic_or_jsonschema_or_blake3_at_top_level`.**
- **F8 (harden)** — Inter-story dependency on S4-02's click flag missing. **→ Header "See also: S4-02".**
- **F9 (nit, positive)** — `enable_audit: True` default traces cleanly to ADR-0004. Noted, no edit needed.

## Conflict resolution

Two cross-critic conflicts arose; both resolved in favor of the **source-of-truth design doc** per the skill's conflict-resolution rule:

- **Provenance label spelling**: Test-Quality F9 assumed `user_yaml`/`repo_yaml` (matching the story). Consistency F1 cited `final-design.md §2.13` and `§4 step 4` as `global`/`repo`. **Resolved: `("defaults", "global", "repo", "cli")` per final-design.** All test bodies that exposed the labels were edited to match.
- **Provenance scope**: Test-Quality F9 was silent on "all fields vs non-default fields"; Coverage F16 hinted at "exact dict equality"; the original story narrowed to "non-default fields". Consistency F2 cited `final-design.md §2.13` line 318 and `phase-arch-design.md §Harness / Configuration` line 760 as "**every** field". **Resolved: every field, with `"defaults"` for un-overridden.** Added a second test (`test_provenance_event_when_nothing_overrides_labels_all_as_defaults`) to anchor the defaults-only case.

## Research briefs

None required after synthesis. Coverage F13's `NEEDS RESEARCH` tag on env-var-off verification was resolved in-line by Test-Quality F6's AST-scan + spy idiom (which mirrors S3-03's `SECRET_FIELD_PATTERN` single-source pattern, already-precedented in this codebase).

## Edits applied — before/after

### Edit 1 — Header

**Before:**
```
**Status:** Ready
**Depends on:** S2-05
**ADRs honored:** —
```

**After:**
```
**Status:** Validated
**Depends on:** S2-05
**See also (cross-story coupling):** S4-02 — CLI must set `auto_envvar_prefix=None` at the click level; companion close to AC-15 (env-var-off) verified there, not here.
**ADRs honored:** ADR-0012 (subprocess allowlist + forbidden-patterns hook bans bare `yaml.load(...)` — AC-7 is the test-side enforcement)
```

### Edit 2 — Validation notes block

Added under the header — summarizes every change + the three architectural follow-ups.

### Edit 3 — Context paragraph

**Before:** Two paragraphs; AC-level claim that env-var expansion is off "(`auto_envvar_prefix=None` at the click level)".

**After:** Three paragraphs; separates loader-level env-var-off (this story's AC-13/14) from CLI-level `auto_envvar_prefix=None` (S4-02's job). Names the four-source merge explicitly.

### Edit 4 — Acceptance criteria

**Before:** 8 unstructured ACs.

**After:** 21 ACs in seven sections (A: dataclass shape, B: source precedence, C: YAML parsing safety, D: unknown-key check, E: env-var-off, F: provenance, G: code hygiene). Every AC has at least one paired test.

### Edit 5 — Implementation outline

Restructured to call out the three private helpers (`_read_yaml_if_exists`, `_check_unknown_keys`, `_typed_construct`) explicitly and to require `_typed_construct` to perform per-field `isinstance` checks (closing the silent-coercion mutant from Coverage F3).

### Edit 6 — TDD plan

**Before:** 8 sketched tests, 3 with `...` bodies, `caplog` used for structlog assertions, single-row precedence check.

**After:** 23 tests organized by AC section. Shared `write_user_yaml` and `write_repo_yaml` fixtures with `monkeypatch.setattr(Path, "home", ...)` for hermeticity. All bodies are real Python. Parametrized matrices for precedence (8 rows), empty/null YAML (4 payloads), non-mapping YAML (3 payloads). AST scans for `yaml.safe_load`-only, env-var-off, and cold-start-budget protection.

### Edit 7 — Files to touch

Unchanged (same 4 files); descriptions tightened to call out the new test categories.

### Edit 8 — Out of scope

Expanded from 5 deferrals to 8: added property-based testing of the suggestion algorithm (declined for 3 fields), YAML 1.1 boolean truthiness ergonomics, parent-directory fsync, symlinked `~/.codegenie/`.

### Edit 9 — Notes for the implementer

Expanded from 7 notes to 10. New notes: the four-payload `yaml.safe_load → None` cases (line 152 expansion), the `Mapping`-vs-`dict` check rationale for AC-7, the `_typed_construct` per-field `isinstance` rationale for AC-9, the `Path.home()`-internally-consults-`pwd` clarification for AC-13.

## Verdict

**HARDENED** — story had real but fixable weaknesses across all three critic lenses (coverage, test quality, consistency). The story file has been edited in place and is ready for `phase-story-executor`. The three architectural follow-ups (Levenshtein wording, provenance vocabulary, env-var-off ADR) are out-of-scope for this story per Rule 3 and have been surfaced in the Validation notes block for separate action.
