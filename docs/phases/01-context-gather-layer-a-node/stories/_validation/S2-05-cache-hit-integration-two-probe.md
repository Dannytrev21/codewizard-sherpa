# Validation report — S2-05 (Cache-hit-on-real-repo integration test, two probes)

**Date:** 2026-05-14
**Validator:** `phase-story-validator` skill
**Story:** [`S2-05-cache-hit-integration-two-probe.md`](../S2-05-cache-hit-integration-two-probe.md)
**Verdict:** **HARDENED** — five BLOCK-tier issues fixed in place (nonexistent helpers × 3, global-`os`-mutation monkeypatch, missing autouse seam-disablement); seven HARDEN-tier ACs added (metamorphic miss-partner, negative-variant pin, cache-key byte-equality, slice-content invariance, POSIX-form stat-snapshot, fail-loud failure messages, static-gate split); one design-pattern observation elevated to an Open/Closed AC (rule-of-three frozenset constant); one design-pattern observation surfaced in Notes (project-root conftest lift as alternative).

## Context Brief

S2-05 lands **Phase 1 exit criterion #2** in its two-probe form: a cache-hit-on-second-run integration test against `node_typescript_helm/` for `LanguageDetectionProbe` and `NodeBuildSystemProbe`. It is the seam test that S5-05 extends to all six probes. It mirrors Phase 0's `S4-04` bullet-tracer anchor (`tests/smoke/test_cli_end_to_end.py::test_cache_hit_on_second_run`).

Phase reference docs read in full:
- `phase-arch-design.md` §"Scenarios", §"Control flow", §"Gap analysis & improvements" → "Gap 1", §"Edge cases" row 16, §"Testing strategy" → "Test pyramid".
- `ADRs/0002-parsed-manifest-memo-on-probe-context.md`, `ADRs/0004-per-probe-subschema-additional-properties-false.md`, `ADRs/0010-layer-a-slices-optional-at-envelope.md`.
- `High-level-impl.md` §"Step 2".
- `stories/README.md` Step 2 + Step 5 rows.
- **Phase 0 precedent (full read):** [`docs/phases/00-bullet-tracer-foundations/stories/S4-04-fixtures-smoke-cache-hit.md`](../../../00-bullet-tracer-foundations/stories/S4-04-fixtures-smoke-cache-hit.md) and its `_validation/` report. S4-04's TQ-1 (monkeypatch blast radius) and TQ-3 (negative-variant pin, cache_key byte-equality, metamorphic miss-partner) findings apply verbatim.
- **Sibling story (full read):** [`stories/S2-04-warm-path-memo-integration.md`](../S2-04-warm-path-memo-integration.md) hardened version + its `_validation/` report. S2-04 lands the `tests/integration/probes/conftest.py` kernel that S2-05 extends.
- Source: `src/codegenie/probes/language_detection.py`, `src/codegenie/probes/node_build_system.py`, `src/codegenie/cli.py`, `src/codegenie/coordinator/coordinator.py:313` (cache_hit event emission), `src/codegenie/logging.py` (event constants), `src/codegenie/schema/validator.py`, `tests/smoke/conftest.py` (the canonical `_install_scandir_counter` + autouse).

### Story snapshot (verbatim from story)
- **Goal:** Two-probe cache-hit on second `codegenie gather` against `node_typescript_helm/` — zero scandir invocations on the warm path AND `probe.cache_hit` for both probes.
- **Non-goals:** Six-probe extension (S5-05), wall-clock benches (S6-02), cache-invalidation-scope unit test (S3-06), TOCTOU-window edit test (S1-08), adversarial hostile cache state (Phase 2).

### Phase / arch constraints applied
- ADR-0002: cache key derives from `content_hash`, not live `os.stat`; stat-snapshot is belt-and-suspenders.
- ADR-0004: cached slice MUST validate under each per-probe sub-schema's strict root on the warm run (AC-16).
- ADR-0010: canonical fixture is a Node repo; both Layer A slices ARE present.
- CLAUDE.md "Extension by addition": S5-05's extension to six probes must be one-line additive — drives the frozenset constant AC-18.
- Phase 0 ADR-0009 (`cache-hit-pass-through-coordinator-output`): cached slice IS the validated slice — fail-loud slice-content ACs (AC-14/15) catch a cache that round-trips raw probe output.

## Findings by lens

### Coverage (lens 1 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C-1 | harden | No AC asserted `errors == []` / `warnings == []` / `confidence == "high"` for either slice on the warm run. A buggy cache that replays a degraded slice (e.g., `confidence: low` due to a memo race) would pass the original `cache_hit`-presence check. Same silent-degradation failure mode S2-04's C-1 surfaced. | Added AC-14, AC-15. |
| C-2 | harden | No AC asserted the warm-run envelope **still validates** under sub-schema strict roots (ADR-0004). The original story said "envelope still validates" but used the nonexistent `load_envelope_validator`. | Reshaped as AC-16 with correct import `from codegenie.schema.validator import validate`. |
| C-3 | harden | No AC asserted **cache_key byte-equality** across cold and warm runs. Without it, a buggy impl that re-derives a different key but happens to find a different stored blob (e.g., hash collision in test cases — unlikely but constructible) passes. S4-04 added this exact AC. | Added AC-13 (with gap-check note for `node_build_system` if S3-05 doesn't emit `cache_key` on its `probe.success`). |
| C-4 | harden | No AC asserted **negative-variant pin**: that `probe.success` (with `cache_key`) does **not** fire on the warm run for either probe. A buggy impl could emit BOTH `probe.success` and `probe.cache_hit` and pass the cache_hit-presence check. S4-04 §AC + TQ-3 added this. | Added AC-12. |
| C-5 | block | Missing **metamorphic miss-partner test**. The original story has one direction only (hit). An `always-return-CacheHit` mutant passes every other AC. S4-04 carries `test_cache_miss_on_tracked_input_edit` for exactly this mutation-resistance reason. | Added AC-17 (`test_two_probes_cache_miss_on_tracked_input_edit`) with full assertion shape. |
| C-6 | ok | Out-of-scope items match `stories/README.md` row + the High-level-impl Step 2 done-criteria. No drift. | No change. |

### Test Quality (lens 2 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| TQ-1 | **block** | `from codegenie.cli import gather_in_process` — **symbol does not exist**. Same bug as S2-04 TQ-1. Phase 0 + S2-04 precedent is `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` ([`tests/smoke/test_cli_end_to_end.py:87`](../../../../../tests/smoke/test_cli_end_to_end.py) `_invoke_gather`). | Rewrote AC-3, Implementation outline #3, TDD plan. |
| TQ-2 | **block** | `structlog_capture` pytest fixture — **does not exist**. Same as S2-04 TQ-2. Real form is `structlog.testing.capture_logs()` *context manager*. | Rewrote AC-4, Implementation outline #3, TDD plan. |
| TQ-3 | **block** | `from codegenie.schema import load_envelope_validator` — **does not exist**. Same as S2-04 TQ-5. Real API is `from codegenie.schema.validator import validate` (function that raises `SchemaValidationError`). | Rewrote AC-16, Implementation outline #4, TDD plan. |
| TQ-4 | **block** | Implementation outline #7 + TDD plan prescribed `monkeypatch.setattr(ld_mod.os, "scandir", counting_scandir)`. **This mutates the global `os` module** because `ld_mod.os IS os` — Phase 0 S4-04's TQ-1 hardened exactly this anti-pattern. The pattern produces false-RED on warm gather (the counter sees scandir calls from cache layer, output writer, audit chain, pytest internals — not just the probe). Phase 0 solved this with `_install_scandir_counter` in [`tests/smoke/conftest.py:49`](../../../../../tests/smoke/conftest.py) which replaces the `os` *name binding* on the probe module with a `types.SimpleNamespace` shim. | Rewrote AC-5 to mandate `_install_scandir_counter(monkeypatch, ld_mod)`; explicit prohibition on `monkeypatch.setattr(ld_mod.os, "scandir", ...)` in Notes; corrected TDD plan and Implementation outline. |
| TQ-5 | **block** | Missing the autouse `_disable_cli_configure_logging` requirement (S2-04's AC-2). Without it, `capture_logs()` silently returns empty inside `CliRunner.invoke` because `_seam_configure_logging` re-installs structlog's chain mid-invoke. S2-05's draft was unaware of this seam. | Surfaced as AC-2 (precondition: S2-04 conftest must exist; S2-05 extends, does not parallel-create); documented in Notes. |
| TQ-6 | harden | `_stat_snapshot` keyed by raw `Path` objects. ADR-0002 explicitly documents the macOS case-insensitive-FS Path-equality foot-gun (`Path("/a/B") != Path("/a/b")` but both stat the same inode). | Reshaped AC-6: snapshot keyed by `str(p.resolve())`; return type `dict[str, tuple[int, int]]`. |
| TQ-7 | harden | Failure messages in the original TDD plan were terse (`assert counter["n"] == 0, f"expected 0 scandir calls, got {counter['n']}"`). An empty `warm_logs` (from a broken autouse fixture) would produce zero counter calls AND zero events — the test passes for the wrong reason. S2-04 TQ-8 established the pattern of including `events` / state in failure messages. | All fail-loud failure messages now embed `warm_logs` / `cold_logs` and diff dicts (AC-6, AC-8, AC-10, AC-11, AC-12, AC-13). |
| TQ-8 | harden | No `mypy --strict` AC. S2-04 AC-15 sets the precedent. Captured-events list is `list[dict[str, Any]]`; helper return types are explicit. | Added AC-21 (mypy --strict). Split static gates from runtime gate (AC-19/20/22). |
| TQ-9 | nit | Original story did not list `__init__.py` package markers. S2-04 lands them — no duplication needed. | No change; verified S2-04's Files-to-touch includes them. |

### Consistency (lens 3 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO-1 | **block** | Three references to nonexistent symbols (`gather_in_process`, `structlog_capture`, `load_envelope_validator`) contradict the actual codebase. Same family of bugs S2-04 had — strong signal the draft was copy-edited from S2-04's pre-validation version. | Already fixed via TQ-1/2/3. |
| CO-2 | **block** | Story says monkeypatch target may be `codegenie.probes.language_detection.os.scandir` OR `codegenie.probes.language_detection.scandir` "per the module docstring set in S2-01's refactor step". Phase 0's `S4-04` chose the **module-level `os` name binding replacement** approach, not either of those forms — they are both load-bearing-foot-guns (the first mutates global `os`; the second only works if S4-01 chose `from os import scandir`, which it didn't — see `language_detection.py:69` `import os`). | Replaced with hard prescription: `_install_scandir_counter(monkeypatch, ld_mod)`. The S4-04 hardened story's TQ-1 resolution applies verbatim. |
| CO-3 | ok | Aligned with ADR-0002: cache key derives from `content_hash`; `_stat_snapshot` is correctly framed as belt-and-suspenders. The story explicitly notes "Don't add `time.sleep()` — TOCTOU-safe via S1-08's content-hash snapshot." | No change; reinforced in Notes. |
| CO-4 | ok | Aligned with ADR-0004: AC-16 asserts envelope validates under sub-schema strict roots after cache replay. | No change. |
| CO-5 | ok | Aligned with ADR-0010: canonical fixture is a Node repo; non-Node fixture is explicitly out of scope. | No change. |
| CO-6 | harden | Story didn't surface `Depends on: S2-04` even though it imports from the S2-04 conftest. The S2-04 conftest is the precondition for AC-2 + AC-4. | Added `S2-04` to Depends-on header line. |

### Design patterns (lens 4 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP-1 | harden → AC | Original story said "Structure the test so adding four more probes to the cache-hit assertion is a one-line edit (extending the `hit_probes >= {…}` set)" but did **not** express this as an observable AC and used a `>=` (membership) rather than `==` (closed-world coverage) assertion shape. The rule-of-three threshold (S2-05 + S5-05 = two near-term consumers; the integration kernel itself = third) is **already** crossed inside Phase 1. Per validator-skill rule, design-pattern findings crossing the rule-of-three threshold are elevated to observable ACs. | Promoted to AC-18 ("S5-05's extension must require exactly one edit — adding probe names to `WARM_PATH_CACHE_HIT_PROBES`; zero edits to `_install_scandir_counter`, `_stat_snapshot`, or any test function body"). Implementation outline mandates `WARM_PATH_CACHE_HIT_PROBES: frozenset[str]` in the integration conftest; test bodies parametrize over it via `set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES`. |
| DP-2 | harden | `_install_scandir_counter` currently lives only in `tests/smoke/conftest.py`. S2-05 is the second consumer (S5-05 the third). The integration-probes conftest must consume it, not duplicate it. Open/Closed Principle on the kernel surface: one source of truth. | Implementation outline mandates a **re-export** (`from tests.smoke.conftest import _install_scandir_counter` + `__all__`), not a copy. Surface the project-root `tests/conftest.py` lift as an alternative satisfying AC-2 in Notes (implementer judgment). |
| DP-3 | notes | `_stat_snapshot` return type `dict[str, tuple[int, int]]` — POSIX-form-str keys (not `Path`) — composes with ADR-0002's macOS Path-equality documentation. Phase 1 needs the helper for S5-05; Phase 2's `IndexHealthProbe` warm-path may extend the helper's input set. Helper signature is the forward-compat contract. | Surfaced in Notes; AC-21 enforces strict typing. |
| DP-4 | skip | Tempting to introduce a `CacheCounter` wrapper class or a `@pytest.fixture` for the scandir counter. CLAUDE.md Rule 2 ("three similar lines is better than a premature abstraction"): two consumers + the existing function-pattern helper is the right level. Skip. | No action. |
| DP-5 | notes | The probe-set frozenset constant doubles as a phase-1 "extension contract" — adding a Layer A probe to S5-05 means adding to the constant; that's the architectural seam. Surface as Notes so S5-05 inherits the framing. | Surfaced in Notes (the design-pattern AC is at the test level; the architectural framing belongs at the story level). |

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every finding was directly resolvable from:
- The codebase (verifying which symbols exist).
- Phase 0's hardened `S4-04` precedent and its `_validation/` report.
- S2-04's hardened version and its `_validation/` report (sibling-family lineage).
- The phase ADRs (0002, 0004, 0010).

## Synthesis + edit log

### Conflict resolution

Priority order applied: **Consistency > Coverage > Test-Quality > Design-Patterns**.

- **CO-2 vs. original story's S2-01-docstring-says-the-target framing:** The story said "read the S2-01 module docstring to find the patch target." Consistency wins — `language_detection.py` uses `import os` (verified at module level), and `tests/smoke/conftest.py` already encodes the correct pattern in `_install_scandir_counter`. The hedged "read the docstring; don't guess" prose was a relic of a pre-hardening worldview. Removed.
- **DP-1 vs. Rule 2 ("simplicity first"):** The frozenset constant + parametric assertion is conventionally a small abstraction. The rule-of-three threshold is unambiguously crossed (S2-05 + S5-05 + the kernel itself); the abstraction is *not* speculative. Design-Patterns wins on this one; AC-18 is observable (a grep test on the resulting code).
- **TQ-4 vs. "the docstring is the source of truth" framing in original Implementation outline #7:** Consistency wins. The Phase 0 hardened convention (module-local `SimpleNamespace` shim) is the source of truth; any contradicting docstring on `language_detection.py` is a follow-up cleanup, not load-bearing for this story.

### Edits applied (in-place, via `Edit`)

1. **Header / Status:** `Ready` → `Ready (Hardened 2026-05-14)`; added `S2-04` to Depends-on; added `ADR-0004` to ADRs honored.
2. **New `Validation notes` block** under header — eight-paragraph summary linking to this report.
3. **References — where to look:** rewrote to point at real symbols (`CliRunner`, `capture_logs`, `validate`, `_install_scandir_counter`); pinned Phase 0 precedent files with line numbers; added S2-04 sibling reference; replaced the speculative "read the docstring" framing.
4. **Goal:** expanded from one-sentence to one-paragraph; encodes all four redundant signals (scandir, cache_hit event, no probe.success, slice content invariance) as concrete acceptance.
5. **Acceptance criteria:** rewrote from 9 unnumbered bullets to **23 numbered, individually-verifiable ACs** in 7 sections: harness wiring (AC-1..AC-5), stat-snapshot invariant (AC-6), load-bearing two-probe cache-hit (AC-7..AC-13), slice-content invariance (AC-14..AC-16), metamorphic miss partner (AC-17), design-pattern Open/Closed AC (AC-18), static + dynamic gates (AC-19..AC-23).
6. **Implementation outline:** rewrote 12 steps into 7 with concrete signatures, real imports, the autouse precondition, the metamorphic miss flow, and the explicit "two `with capture_logs()` blocks, never one" rule.
7. **TDD plan — Red snippet:** replaced wholesale with a 150-line concrete test file using real symbols (`CliRunner` + `capture_logs` + `validate`), real helper imports (`_install_scandir_counter`, `_stat_snapshot`, `_copy_tree`, `_load_envelope`, `WARM_PATH_CACHE_HIT_PROBES`), the metamorphic pair (hit + miss), and fail-loud failure messages embedding `cold_logs` / `warm_logs`.
8. **TDD plan — Green:** rewrote diagnostic-by-AC ladder (which production layer to fix when which AC fails). Added the gap-check escape hatch for AC-13 if `node_build_system` doesn't emit `cache_key` on `probe.success`.
9. **TDD plan — Refactor:** added the grep-for-literals validation step (proves AC-18 is satisfied — probe names appear only in slice-content assertions, not in cache_hit/miss assertion loops).
10. **Files to touch:** clarified `conftest.py` is **extended** (from S2-04), not created; added re-export pattern; added the optional project-root-lift alternative.
11. **Out of scope:** unchanged (already correct per the manifest).
12. **Notes for the implementer:** rewrote from 7 to 13 bullets — added the monkeypatch-target paragraph (with the explicit prohibition), the autouse-is-load-bearing paragraph, the four-redundant-signals framing, the `node_build_system`-doesn't-scandir asymmetry note, the AC-13-gap-check escape hatch, the S5-05-extension-by-addition note, and the sub-schema-strictness-preserved-on-cache-hit paragraph.

### Edits NOT applied (out of scope)

- **Lifting `_install_scandir_counter` + `_disable_cli_configure_logging` to project-root `tests/conftest.py`.** Offered as alternative satisfying AC-2; not mandated. The implementer judges based on whether they want to delete the smoke-conftest local definitions in the same PR (Rule 3 — surgical changes).
- **Structured `.cache_key` attribute on `probe.success` for `node_build_system`.** The gap-check note in AC-13 surfaces this as a potential upstream fix; out of scope inside S2-05's PR.
- **Hypothesis property-based test family** (`∀ untracked-edit ⇒ HIT; ∀ tracked-edit ⇒ MISS`). The S4-04 §"Out of scope" note already defers this to S5-01's bench-canary tier. S2-05 follows the same convention; specification-by-example pair is sufficient.
- **Cross-schema-version cache invalidation** (sub-schema bump invalidates only that probe's entries). Belongs in S3-06's `test_cache_invalidation_scope.py` extension, not S2-05.

## Final verdict

**HARDENED.** All five BLOCK-tier issues fixed in place — the story is now executable by `phase-story-executor` with high probability of GREEN on first attempt:

1. ✅ Real symbols (`CliRunner`, `capture_logs`, `validate`, `_install_scandir_counter`) replace the three nonexistent helpers.
2. ✅ Global-`os`-mutation monkeypatch replaced with the Phase 0 hardened `SimpleNamespace`-shim pattern.
3. ✅ Autouse `_disable_cli_configure_logging` surfaced as AC-2 precondition (inherited from S2-04 conftest).
4. ✅ Metamorphic miss-partner test added (AC-17) — `always-return-CacheHit` mutant is now killed.
5. ✅ Negative-variant pin (AC-12) + cache-key byte-equality (AC-13) + fail-loud slice content (AC-14/15) close the remaining mutation-resistance gaps S4-04 had hardened on.

The hardened story also better matches CLAUDE.md's "Extension by addition" commitment: AC-18 makes S5-05's six-probe extension a single-line edit to `WARM_PATH_CACHE_HIT_PROBES`. Zero changes to the test bodies, zero changes to the conftest helpers. The kernel is closed for modification, open for extension.
