# Validation report — S2-04 (Warm-path memo integration)

**Date:** 2026-05-14
**Validator:** `phase-story-validator` skill
**Story:** [`S2-04-warm-path-memo-integration.md`](../S2-04-warm-path-memo-integration.md)
**Verdict:** **HARDENED** — multiple BLOCK-tier issues fixed in place; multiple HARDEN-tier ACs added; design-pattern observations surfaced in Notes; rule-of-three extension elevated to an AC (AC-2) because the third consumer (S5-05) lives in the same phase.

## Context Brief

S2-04 is the **first integration test in Phase 1** and the first end-to-end exercise of `ParsedManifestMemo` across two probes. It pins two distinct invariants:

1. **Memo warm-path:** `package.json` is parsed exactly once across `LanguageDetectionProbe` + `NodeBuildSystemProbe` (1 `probe.memo.miss` + 1 `probe.memo.hit`).
2. **ADR-0004 cross-cutting rejection:** an unknown field under `probes.node_build_system` fails sub-schema validation.

Phase reference docs read in full:
- `phase-arch-design.md` §"Control flow", §"Component design" #3 (`ParsedManifestMemo`), §"Harness engineering", §"Edge cases" rows 12/16.
- `ADRs/0002-parsed-manifest-memo-on-probe-context.md`, `ADRs/0004-per-probe-subschema-additional-properties-false.md`.
- `High-level-impl.md` §"Step 2".
- `stories/README.md` Step 2 row.
- Source: `src/codegenie/coordinator/parsed_manifest_memo.py`, `src/codegenie/schema/validator.py`, `src/codegenie/errors.py`, `src/codegenie/cli.py`.
- Phase 0 precedent: `tests/smoke/test_cli_end_to_end.py`, `tests/smoke/conftest.py`.

## Findings by lens

### Coverage (lens 1 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C-1 | harden | No AC asserted `language_detection.errors == []` / `warnings == []`. A buggy probe could surface `framework_hints == ["express"]` *and* warn about a duplicate-detected/extras condition, and the test would pass anyway — exactly the silent-degradation failure mode integration tests exist to catch (Rule 12, fail-loud). | Added AC-8, AC-9. |
| C-2 | harden | No AC asserted `node_build_system.confidence == "high"`. A single-lockfile, non-cycling-tsconfig fixture has no legitimate trigger for `low`/`medium`. | Added to AC-9. |
| C-3 | nit | Equality assertion on `framework_hints == ["express"]` already covers duplicate (`["express", "express"]` ≠ `["express"]`) and extra-entry (`["express", "next"]` ≠ `["express"]`) bugs. No change. | Acknowledged in AC-5 with rationale. |
| C-4 | ok | Cache-hit-on-second-run is **not** in S2-04's scope — it belongs to S2-05 (see High-level-impl.md Done-criteria #4 + README.md Step 2 row). S2-04 stays focused on memo + ADR-0004. | No change. |

### Test Quality (lens 2 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| TQ-1 | **block** | The draft prescribed `from codegenie.cli import gather_in_process` — this symbol **does not exist** in `src/codegenie/cli.py`. The actual Phase 0 precedent invokes the CLI via `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])` ([`tests/smoke/test_cli_end_to_end.py:87`](../../../../../tests/smoke/test_cli_end_to_end.py)). | Rewrote Implementation outline #3, TDD snippet, and AC-3. |
| TQ-2 | **block** | The draft prescribed a `structlog_capture` or `caplog_structlog` pytest fixture — **no such fixture exists**. Phase 0 uses `structlog.testing.capture_logs()` as a context manager, called inline around `CliRunner.invoke`. | Rewrote Implementation outline #4, TDD snippet, and AC-4. |
| TQ-3 | **block** | Capture chain silently empty under `CliRunner.invoke` — `_seam_configure_logging` replaces structlog's processor chain mid-invoke, blowing away the `capture_logs()` `LogCapture` processor. [`tests/smoke/conftest.py`](../../../../../tests/smoke/conftest.py) carries an autouse `_disable_cli_configure_logging` monkeypatch to no-op this; the new `tests/integration/probes/conftest.py` must do the same. Without it, every memo-event count silently returns 0 — a misleading RED that would consume executor retries. | Promoted to AC-2 (explicit conftest requirement); documented in Notes for implementer; offered the lift-to-root-conftest alternative. |
| TQ-4 | **block** | The draft asserted `exc_info.value.json_pointer == "/probes/node_build_system/unknown_field"`. **`SchemaValidationError` has no `.json_pointer` attribute** ([`src/codegenie/errors.py:84`](../../../../../src/codegenie/errors.py) — bare `CodegenieError` subclass). Furthermore, the validator emits jsonschema's JSONPath form (`$.probes.node_build_system.unknown_field`) embedded in `str(exception)` — **not** RFC-6901 JSON Pointer. | Reshaped AC-12: assert each pointer component (`"probes"`, `"node_build_system"`, `"unknown_field"`) appears in `str(exc_info.value)`. Robust against either future shape. Flagged a structured-`.json_path`-attribute follow-up in Notes (out of scope here). |
| TQ-5 | **block** | The draft's `from codegenie.schema import load_envelope_validator` does not exist. Actual public API is `from codegenie.schema.validator import validate` (function that raises `SchemaValidationError`). | Fixed import in TDD snippet + Implementation outline #5. |
| TQ-6 | harden | Memo event-count filter used `"package.json" in e.get("path", "")` — substring on path. The memo emits a structured `allowlist_match=path.name` key — exact match on `allowlist_match == "package.json"` is stronger and immune to incidental substring collisions. | Replaced filter shape in TDD snippet + AC-11; added the `allowlist_match` kwarg to `_count_memo_events`. |
| TQ-7 | harden | `_minimal_valid_envelope()` was undefined in the draft — the executor would invent a shape, possibly missing required envelope keys (`schema_version`, `generated_at`, `repo.root`, `repo.git_commit`, `probes`). | Inlined a concrete reference shape in Implementation outline #1 + Notes; matched against `src/codegenie/schema/repo_context.schema.json:8`. |
| TQ-8 | harden | TDD snippet's failure messages were terse. A `(0,0)` memo-count failure (probe bypassed memo) would surface as `assert 0 == 1` with no diagnostics. | Included `events` in the failure message so the executor can diagnose without re-running. |
| TQ-9 | harden | No explicit `mypy --strict` on the conftest. AC-15 now binds both files. The `events` list shape is `list[dict[str, Any]]`. | Added to AC-13/14/15. |

### Consistency (lens 3 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CO-1 | harden | Story says "per Phase 0 convention, integration tests run in-process". Phase 0 uses `tests/smoke/`, not `tests/integration/`. Phase 1 *newly* introduces `tests/integration/`. The wording conflated the layer location with the invocation style. | Clarified in the Implementation outline + References. |
| CO-2 | **block** | `gather_in_process` referenced. Doesn't exist. | Already fixed via TQ-1. |
| CO-3 | **block** | `load_envelope_validator` referenced. Doesn't exist. | Already fixed via TQ-5. |
| CO-4 | **block** | `.json_pointer` attribute referenced. Doesn't exist. | Already fixed via TQ-4. |
| CO-5 | ok | Aligns with ADR-0002 (allowlist `{"package.json"}`, per-gather lifetime, `allowlist_match` event field), ADR-0004 (per-probe sub-schema rejection at own root), ADR-0007 (warning ID pattern — not exercised here but warnings are asserted empty), ADR-0010 (Layer A optional at envelope — single-package fixture means `monorepo is None` is the valid shape). | No change. |

### Design patterns (lens 4 of 4)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP-1 | harden → AC | The draft listed `conftest.py` as **optional** ("If `_copy_tree` / `_minimal_valid_envelope` is also needed by S2-05, factor it here"). Per [`stories/README.md` Step 2 + Step 5](../README.md), the same scaffolding is needed by S2-05 (cache-hit-on-real-repo) and S5-05 (all-six-probes warm-path). Three concrete consumers all inside Phase 1 → rule-of-three threshold crossed → CLAUDE.md "Extension by addition" prefers the kernel landed in this story. **This is the design-pattern finding elevated to an AC** (per the validator-skill rule: when a Design-Patterns finding crosses the rule-of-three threshold, express the extension-by-addition constraint as an observable AC rather than as a "consider doing this" note). | Promoted to AC-2; expanded Implementation outline #1 to detail every helper that lands in conftest. |
| DP-2 | notes | The autouse `_disable_cli_configure_logging` lives only in `tests/smoke/conftest.py` today. Better extension-by-addition path: lift it to a project-root `tests/conftest.py` so both `tests/smoke/` and the new `tests/integration/probes/` inherit it from one place. | Surfaced as an alternative satisfying AC-2 in Notes. Did not mandate the project-root lift — that is an implementer judgment call. |
| DP-3 | notes | `_count_memo_events` helper takes `allowlist_match` as a kwarg, not a hard-coded `"package.json"` — so Phase 2's `IndexHealthProbe` (allowlist will extend to `{"package.json", "scip-index.json"}`) reuses the helper unchanged. | Added Notes paragraph noting the helper signature is the contract for forward-compat. |
| DP-4 | skip | Tempting to introduce a `StructlogCapture` wrapper class. Per CLAUDE.md Rule 2 ("Simplicity First") + the validator's editor rule ("three similar lines is better than premature abstraction"): three call sites with a 2-line filter is fine. Skip. | No action. |

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. All findings are codebase-confirmable.

## Synthesis + edit log

Conflicts resolved (priority `Consistency > Coverage > Test-Quality > Design-Patterns`):

- TQ-4 vs. arch-design.md docstring on validator: The validator module docstring claims "JSON Pointer" but the code emits JSONPath via `err.json_path`. This is a pre-existing documentation/code mismatch upstream — the validator is the source of truth in code; the docstring is wrong. The AC was reshaped to assert what the code emits (Consistency wins → tests verify behavior, not docstring claims). Flagged the docstring fix as an upstream follow-up in Notes.
- DP-1 vs. Rule 2: The "land conftest with all four helpers" is conventionally aggressive for a story called "small". But the rule-of-three is satisfied *inside the same phase* (S2-04, S2-05, S5-05); deferring would force a copy-paste cliff in S2-05's PR. Design-Patterns wins on this one because the YAGNI threshold is exceeded (not premature).

### Edits applied (in-place, via `Edit`)

1. **Header / status:** Status `Ready` → `Ready (Hardened 2026-05-14)`.
2. **New `Validation notes` block** under the header summarizing eight categories of change + linking to this report.
3. **References — where to look:** added `tests/smoke/test_cli_end_to_end.py` + `tests/smoke/conftest.py` as Phase 0 precedent; pointed at the memo's actual `allowlist_match` emission; pointed at validator's actual message-string shape.
4. **Acceptance criteria:** rewritten as 16 numbered, individually-verifiable ACs in 4 sections (test-file existence/harness; slice content invariants; memo event-count; ADR-0004 rejection; static+dynamic gates). AC-2 (conftest with autouse + 4 helpers), AC-3/AC-4 (CliRunner + capture_logs concretely), AC-8/AC-9 (fail-loud errors/warnings/confidence assertions), AC-11 (`allowlist_match` filter), AC-12 (reshaped pointer assertion), AC-13–AC-16 (concrete static gates).
5. **Implementation outline:** rewrote to land conftest first with concrete helper signatures + reference shape for `_minimal_valid_envelope()`; replaced `gather_in_process` with `CliRunner` + `capture_logs`; replaced `load_envelope_validator` with `validate`.
6. **TDD plan — Red snippet:** rewritten end-to-end with correct imports, the `capture_logs()` context manager pattern, fail-loud failure messages including `events` and `lang/nbs` dicts, and the reshaped ADR-0004 assertion.
7. **Files to touch:** added `conftest.py` (now required, not optional), `__init__.py` markers.
8. **Notes for the implementer:** expanded from 6 bullets to 9; added the autouse-fixture-is-load-bearing paragraph, the `allowlist_match`-not-`path` paragraph, the `SchemaValidationError`-message-shape paragraph, the rule-of-three justification, and the forward-compat-helper-signature paragraph.

### Edits NOT applied (out of scope)

- **Structured `.json_path` attribute on `SchemaValidationError`.** Would require an `errors.py` change + every raise site + a docstring fix in `validator.py`. Flagged in Notes as a separate follow-up. Adding it inside S2-04 would violate Rule 3 (Surgical Changes) and broaden the story's blast radius.
- **Lift `_disable_cli_configure_logging` to project-root `tests/conftest.py`.** Offered as an alternative satisfying AC-2, not mandated. The implementer judges based on whether they want to delete the smoke conftest's local fixture in the same PR.
- **Adding a metamorphic "memo disabled" partner test** (forces `ctx.parsed_manifest = None`, asserts `2 misses + 0 hits`). The `exactly 1+1` shape is already mutation-resistant — a memo-disabled mutant produces `(2,0)` which fails AC-11. The extra test would be redundant; skipped per Rule 2.

## Final verdict

**HARDENED.** All four BLOCK-tier issues (nonexistent helpers, nonexistent attribute, nonexistent import, capture-chain disablement) fixed in place. The story is now executable by `phase-story-executor` with a high probability of GREEN on first attempt — every AC is individually verifiable, the TDD snippet imports symbols that actually exist, and the autouse fixture requirement is surfaced before the executor wastes a retry on a misleading-empty event stream.

The hardened story also better matches CLAUDE.md's "Extension by addition" commitment by landing the shared kernel (conftest helpers) in this story rather than letting S2-05 deal with a copy-paste cliff. No structural rewrites were necessary; the goal and scope are preserved verbatim.
