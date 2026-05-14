# Validation report — S4-01 `CIProbe` + sub-schema

**Story:** [S4-01-ci-probe.md](../S4-01-ci-probe.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S4-01 ships the third new Phase 1 probe — structurally simple (read YAML in well-known locations, dispatch on a 5-arm catalog discriminator) but with two design tensions concentrated in one file: a 5-way parser dispatch and a single regex on attacker-controllable bytes. The story was directionally sound and well-anchored in the arch, but the four parallel critics surfaced **one critical contradiction with ADR-0007**, **two block-tier internal contradictions** (regex bound vs unbound; refactor's "ban parametrize" vs the codebase's parametrize-heavy convention), and ~20 harden-tier gaps:

- **CN-1 [CRITICAL]** — Arch §"Component design" #5 line 540 prescribes `warnings: ["ci.workflow_parse_error:<path>"]` (colon-suffixed). This violates ADR-0007's pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` admits no colons). The story's TDD assertion (`startswith` rather than `==`) sat in the middle of the contradiction, admitting both forms. **Resolution per Rule 7**: emit the bare ID; the offending workflow path lives in `raw/ci.json`. Arch-doc drift flagged in PR body for follow-up.
- **CV-8 / Outline §2 vs Notes §1** — Outline shipped the unbounded secrets regex `[A-Za-z0-9_]*`; Notes §1 prescribed the bounded `{0,128}` form. The bounded form is security-load-bearing (sole regex on attacker-controllable bytes per the Notes' own framing); reconciled to bounded with a new ReDoS test (T-12).
- **TQ-15** — The original Refactor section banned `pytest.mark.parametrize` ("one assertion target per test"). This contradicts `test_node_build_system.py` (10+ parametrized tests) and the S2-02 hardening report's own block-tier `test_lockfile_precedence_total_ordering` parametrized fix. Per Rule 9 (tests verify intent), parametrization is exactly how invariants are encoded; the prescription was wrong. Rewrote to "one **invariant** per test, parametrized over all inputs that exercise it."
- **DP-1 / DP-2 / DP-3 / DP-4 / DP-9 [BLOCK-tier design]** — Five-way ad-hoc parser branches contradict the codebase's established Open/Closed pattern (`_LOCKFILE_PRECEDENCE` / `_BUNDLERS_SORTED` / `_BERRY_MARKERS` in `node_build_system.py`). Elevated to ACs because extension-by-addition is observably testable.

The synthesizer rewrote ACs from **7 bundled bullets + 6 TDD tests** to **27 individually-verifiable ACs + 22 TDD tests** (most parametrized). New module-level Open/Closed seams: `_PROVIDER_PRECEDENCE`, `_CI_PARSERS`, `_IMAGE_BUILD_MARKERS`, `_TEST_COMMAND_MARKERS`, `_SECRETS_RE`, `_JENKINS_SH_RE`, `_WARNING_IDS` — each with import-time anchor assertions matching `node_build_system.py:212-262`.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0001/0002/0004/0006/0007/0009/0010 + production ADR-0005) plus the S2-02 hardened-story precedent. Stage 3 (researcher) skipped per skill's token-economy guidance.

## Most load-bearing fixes (block-tier)

1. **CN-1 (CRITICAL) — ADR-0007 colon contradiction.** The arch says `ci.workflow_parse_error:<path>`; the ADR's pattern admits no colons. The TDD's `startswith(...)` admitted both forms — masking the conflict. Resolution: bare ID in `slice["warnings"]`; path in `raw/ci.json`. New AC-21 + tightened T-13 assertion (`==` of expected list, plus an ADR-0007 conformance loop over every emitted warning). Arch-doc drift flagged for separate follow-up.

2. **CV-8 / Internal regex contradiction.** Outline's unbounded vs Notes' bounded. The regex is the **only** Phase-1 regex on attacker-controllable bytes (per Notes' own framing). Reconciled to bounded `{0,128}` via new AC-17 + module-level `_SECRETS_RE: Final[re.Pattern[str]]` + ReDoS test (T-12) executing under a 1-second wall-clock guard against 5000 reps of `${{ secrets.A` (no terminator).

3. **DP-1 — `_CI_PARSERS` dispatch registry.** Five parsers under one discriminator IS the strategy/dispatch pattern. The catalog already pins `parser: Literal[...]`. Original outline shaped this as five inline branches in `run()`. New AC-24 mandates a module-level `_CI_PARSERS: Mapping[ParserKind, Callable[...]]` keyed on `_PARSER_LITERAL` arms; import-time `assert set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL))` catches a new catalog arm without a parser. T-16 enforces the contract. Adding a sixth parser (Buildkite) becomes one new function + one dict entry — zero edits to the iterate-catalog control flow. Mirrors `_BERRY_MARKERS` in `node_build_system.py:303`.

4. **DP-2 — `_PROVIDER_PRECEDENCE` anchor at file boundary.** The story repeatedly invoked "deterministic order from `ci_providers.yaml`" but the dict-iteration-order semantics was nowhere pinned. Future "alphabetize the catalog" PR silently changes precedence. New AC-15 mandates a module-level tuple with import-time anchor `assert _PROVIDER_PRECEDENCE == tuple(CI_PROVIDERS.keys())`. T-3 enforces the value verbatim. Mirrors `assert _LOCKFILE_PRECEDENCE[0][1] == "bun"` in `node_build_system.py:256`.

5. **DP-3 — `_IMAGE_BUILD_MARKERS` table fixes the run-vs-uses confusion.** Outline §2 said "substring match against the union of all `run:` strings for [...] `docker/build-push-action` (the last as a `uses:` match)" — internally contradictory. New AC-25 mandates `_IMAGE_BUILD_MARKERS: Final[tuple[tuple[str, Literal["run", "uses"]], ...]]` with each marker tagged. T-17 locks the table; T-4 parametrizes over all three markers + a negative case (`docker run hello-world` → no build).

6. **DP-4 — Pure-helper extraction (functional core / imperative shell).** Original `run()` bundled parse + extract + detect + assemble. New AC-26 mandates five pure helpers (`_select_provider`, `_extract_run_strings`, `_extract_uses_strings`, `_extract_secret_names`, `_detect_image_build`); T-20 unit-tests them in isolation. Mirrors `_select_package_manager` / `_walk_extends` / `_deps_union` in `node_build_system.py`. The pure-secrets-extractor unit test is the load-bearing seam for the regex bound.

7. **DP-9 + TQ-11 — `_WARNING_IDS` frozenset + import-time ADR-0007 assertion.** Original story enumerated 5 warning IDs inline with no module-level frozenset and no import-time check. A typo (`"ci.MultiProvider"`) would silently ship and fail downstream at slice validation. New AC-20 mandates an explicit frozenset of all 8 IDs (3 added: `ci.empty_workflows_dir`, `ci.circleci_presence_only`, `ci.azure_pipelines_presence_only`) + import-time pattern loop. T-15 enforces. Mirrors `node_build_system.py:212-254`.

8. **TQ-1 + TQ-2 — Test helper preamble undefined; contract-attributes test missing.** Original referenced `_snapshot(...)` and `_ctx(...)` six times without defining either; this was the **block-tier** finding S2-02 explicitly flagged. New TDD plan opens with a complete preamble (`_snapshot`, `_ctx`, `_run`, `_write_workflow`) and drops `pytest-asyncio` in favor of explicit `asyncio.run` (matches sibling). Contract test T-2 anchors the verbatim 7-entry `declared_inputs` list and asserts `list[str]` (not tuple — the S2-02 frozen-ABC bug).

## Coverage gaps closed (harden-tier)

- **AC-2 + T-1 — Registry membership across languages.** New AC explicitly verifies `CIProbe in default_registry.for_task("*", langs)` for `langs ∈ {frozenset({"go"}), frozenset({"javascript"}), frozenset({"python"}), frozenset()}`. Catches "I forgot the additive import line" + "I narrowed `applies_to_languages` by accident."
- **AC-7 — GHA without image build (negative).** A workflow with `docker run hello-world` (Docker invoked, but not as a build) → `builds_image: false`. Catches the "any string containing `docker` triggers builds_image" mutation.
- **AC-13 + T-10 — No CI files anywhere.** Slice IS produced (probe runs because `applies_to_languages = ["*"]`), `provider: null`, all empty, `confidence: "high"`. Distinguishes "ran and found nothing" from "didn't run."
- **AC-12 + T-9 — Empty `.github/workflows/` directory.** Catalog marker matched but no workflows; new typed warning `ci.empty_workflows_dir`, `confidence: "low"`. Catches the "marker matched ⇒ confidence high" mutation.
- **AC-10 / AC-11 + T-8 — Presence-only stubs for CircleCI / Azure.** Two new typed warnings. Original story was silent on confidence for these.
- **AC-14 + T-6 — Multi-provider precedence parametrized over 5 marker combinations.** Catches "hard-coded github_actions default" + "alphabetical sort instead of catalog order" mutations.
- **AC-16 + T-6 (single-provider case) — `additional_providers == []` for single provider.** Catches "always emit `ci.multi_provider`" mutation.
- **AC-18 + T-11 — `references_secrets` sorted + deduped.** Original story silent; the test only proved `["NPM_TOKEN"]` (single-element case where order/dedup don't apply). New: `${{ secrets.B }}` then `${{ secrets.A }}` then `${{ secrets.A }}` again → `["A", "B"]`. Cross-workflow case also tested.
- **AC-19 + T-11 (negative cases) — Regex case + scope sensitivity.** `${{ env.FOO }}`, `${{ inputs.BAR }}`, `${{ Secrets.X }}` all do NOT land in `references_secrets`. Catches "loose regex matches anything in `${{ ... }}`" mutation.
- **T-11 (sentinel) — `os.environ.get` spy.** Asserts the probe never resolves a secret value. Facts-not-judgments enforced at unit level (production ADR-0005). Catches "I added a 'just check if the env var is set' helper" PR.
- **AC-21 + T-13 — Per-file workflow YAML parse failure routing.** `bad.yml` omitted from `workflow_files`; `good.yml` retained; bare `ci.workflow_parse_error` ID; ADR-0007 conformance loop over all warnings. Original test was brittle (`assert "bad.yml" in str(warnings)` — coincidental string match).
- **AC-22 + T-14 — `local-action` reference warning.** Arch §"Edge cases" row 13 names this; original story mentioned in Out-of-scope but had no test. Phase 1 confidence resolution: stay at surrounding workflow's level (rejecting arch's `medium`).
- **AC-23 + T-18 + T-19 — Two-run determinism + `workflow_files` sorted.** New AC + tests catch insertion-order-dependent behavior in dict iteration, glob ordering, secrets capture.
- **AC-3 + T-21 + T-22 — Schema rejection deepened.** Original test asserted `"unknown_field" in str(ei.value)` (brittle). New: T-21 asserts `SchemaValidationError` exception type AND `"/probes/ci"` JSON Pointer AND `"rogue_field"` in message. T-22 walks the schema asserting `additionalProperties: false` at EVERY `type: object` node (catches a nested-object regression).
- **T-22 — Envelope-optional anchor.** Asserts `"ci"` is NOT in `properties.probes.required` of the envelope schema. ADR-0010 enforced structurally.

## Test-Quality gaps closed (harden-tier)

- **T-4 image-build parametrized over all 3 markers + 1 negative.** Original tested only `docker buildx`. The implementer who writes `if "docker buildx" in run_str` passed the original test but missed `docker build` and `uses: docker/build-push-action`. Now caught.
- **T-7 Jenkinsfile parametrized over `'` and `"` quoting + no-`sh` case.** Original tested one `sh 'npm test'`. Mixed-quoting case left as a documented Phase-2 limitation (the `[^'\"\n]` regex truncates at the inner quote — pinned by an alternate parametrize entry if the implementer chooses to handle it; otherwise documented as a known-limitation in `Notes`).
- **T-12 ReDoS guard.** 5000-rep hostile input runs in < 1 second. Catches an unbounded regex regression.
- **T-15 frozenset invariant.** Asserts `_WARNING_IDS == expected_set` AND every member matches ADR-0007. Catches typo'd ID like `"ci.multiProvider"` at unit boundary, before schema validator sees it.
- **T-18 byte-equal determinism.** Same fixture, two runs → byte-equal `json.dumps(slice, sort_keys=True)`.
- **T-20 pure-helper unit tests.** Five pure helpers exercised in isolation; trivially-testable secrets-extractor table-driven over the 5 documented cases.

## Design-Pattern opportunities lifted into ACs (Open/Closed at file boundary)

Five precedence/dispatch chains live inside this one probe (provider precedence, parser dispatch, image-build markers, test-command markers, jenkins-sh regex). The within-file rule of three is met multiple times. Each was originally prescribed as branching code; each is now mandated as a module-level constant or registry — matching `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_BERRY_MARKERS` in `node_build_system.py`.

- **AC-15 — `_PROVIDER_PRECEDENCE: Final[tuple[str, ...]]`** with import-time anchor against `CI_PROVIDERS.keys()`.
- **AC-24 — `_CI_PARSERS: Mapping[ParserKind, Callable[...]]`** dispatch registry with `_PARSER_LITERAL` reused from catalog.
- **AC-25 — `_IMAGE_BUILD_MARKERS: Final[tuple[tuple[str, Literal["run","uses"]], ...]]`** with explicit run/uses tag (fixes outline's run-vs-uses contradiction).
- **AC-20 — `_WARNING_IDS: Final[frozenset[str]]`** with import-time ADR-0007 pattern loop.
- **AC-26 — Five pure helpers extracted** (`_select_provider`, `_extract_run_strings`, `_extract_uses_strings`, `_extract_secret_names`, `_detect_image_build`) — functional core / imperative shell.

The pure-helper refactor closes Design-Pattern Finding 4's pure-impure tangle and unlocks T-20's table-driven testing of `_extract_secret_names` (which is the security-load-bearing seam).

## Patterns DELIBERATELY deferred (premature-abstraction guard — Rule 2)

Documented in story Notes-for-implementer:

- **`CIProviderParser` ABC + plugin-discovery registry.** Five parsers in one file is fine; ABC adds friction without payoff. Lift in Phase 4+ when external CI plugins land.
- **`_ParseOutcome` sum type** (`Parsed[T] | ParseError | FileNotPresent | CapExceeded`). Lift only if three-of-five parsers share the exact try/except/warn shape after the green pass.
- **`CISlice(TypedDict)`** at module scope. Building as `dict[str, Any]` passes schema validation; lift if slice grows past 12 fields.
- **Shared `probes/_confidence.py` kernel** (`_demote`, `_CONFIDENCE_RANK`). Rule of three is met; copy verbatim from `node_build_system.py` here, extract at S4-03 once the fourth copy lands.
- **Shared `probes/_warning_ids.py`** for the import-time pattern check. Three-line idiom; copy verbatim, extract at ≥ 4 probes.
- **YAML catalog for `_TEST_COMMAND_MARKERS` / `_IMAGE_BUILD_MARKERS`.** Module-level tuples now; lift to YAML at Phase 2 if a third probe needs the same lists.
- **`SecretName` / `WorkflowPath` `NewType`s.** Premature; bare `str` is fine in Phase 1.

## Conflict resolutions surfaced (per Rule 7)

- **Arch line 540 `ci.workflow_parse_error:<path>` vs ADR-0007 (CN-1).** Validator priority: `Consistency > Coverage > Test-Quality > Design-Patterns`. ADR-0007 is the authority on warning ID shape; arch is the authority on architecture. Arch's specific WarningId-with-path-suffix prescription violates ADR-0007 — the ADR wins. Story emits bare ID; arch doc-drift flagged for follow-up. Path provenance moves to `raw/ci.json`.
- **Outline §2 unbounded regex vs Notes §1 bounded regex (CV-8).** Both internal to the story; the bounded form is security-load-bearing (Rule 9 — tests verify intent; the intent is "no ReDoS"). Outline updated to bounded; Notes already had it.
- **Refactor's "ban parametrize" vs sibling pattern (TQ-15).** Sibling `test_node_build_system.py` uses parametrize for 10+ tests. Per Rule 11 (match codebase conventions) and Rule 9 (tests verify intent — invariants are encoded by parametrization), the original prescription was wrong. Rewrote: "one **invariant** per test, parametrized over all inputs that exercise it."
- **Arch §"Edge cases" row 13 `confidence: medium` for `local-action` vs Phase 1 simplicity.** Phase 1 ships with no `medium` confidence anywhere (per Notes' explicit confidence rules). Resolution: emit `ci.local_action_unparsed` warning; confidence stays at surrounding workflow's level (`"high"` for an otherwise-clean repo). Re-evaluate in Phase 2.

## Departures from arch surfaced (per Rule 7)

- **WarningId format**: arch line 540's colon-suffixed `ci.workflow_parse_error:<path>` is a documentation drift; Phase 1 emits the bare ID. Story flags this in PR body.
- **`local-action` confidence**: arch row 13 says `medium`; story emits no `medium` in Phase 1 and surfaces the limitation via the warning. Documented in Notes.

## Context Brief (Stage 1)

**Story intent.** Lands `CIProbe` — the third new Phase 1 probe (after `LanguageDetection` extension and `NodeBuildSystem`). Populates `ci` slice from five CI provider markers (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`, `azure-pipelines.yml`). Records workflow paths, image-build presence + command, test/lint commands (substring match against canonical script names), and `${{ secrets.X }}` literal references — facts-not-judgments. Multi-provider downgrades to `confidence: "low"` with a typed warning. Cold p50 ~80 ms; no warm-via-memo path (no `package.json` consumption).

**Phase-1 exit criteria the story must satisfy.** ADR-0004 (sub-schema `additionalProperties: false`), ADR-0006 (`ci_providers.yaml` in `declared_inputs` for cache invalidation), ADR-0007 (warning-ID pattern), ADR-0009 (no new C-extension parser deps), ADR-0010 (slice optional at envelope), production ADR-0005 (no LLM in gather). Phase-0 chokepoints (`base.py`, `registry.py`, sanitizer, coordinator) untouched — extension by addition.

**Load-bearing constraints from arch.** Component-design #5 (lines 527–540 of `phase-arch-design.md`) specifies internal structure precisely. Edge cases 13 (`local-action`), 14 (200-workflow stress) named explicitly. Failure behavior (line 540) names `warnings: ["ci.workflow_parse_error:<path>"]` — this is the CN-1 ADR-0007 violation that the story corrects.

**Sibling pattern to mirror.** `src/codegenie/probes/node_build_system.py` — module-level `_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_NODE_VERSION_PINNED_SOURCES`, `_BERRY_MARKERS` precedence-tuples; module-level `_WARNING_IDS` + `_ERROR_IDS` frozensets with import-time ADR-0007 pattern loop; pure-helper extraction (`_select_package_manager`, `_walk_extends`, `_deps_union`); test harness conventions (`asyncio.run` over `pytest-asyncio`).

**The S2-02 hardening precedent (just landed).** Same shape: bundled bullet AC → split single-observable ACs; missing test-helper preamble → explicit inline preamble; ad-hoc branching → module-level Open/Closed tuples; missing import-time pattern check → frozenset + assert; missing contract-attributes test → verbatim test against frozen ABC. S4-01 inherits the discipline.

## Critic reports (Stage 2 — condensed)

### Coverage critic — Verdict: HARDEN

14 findings (8 block, 6 harden). Highlights:
- CV-1 [BLOCK]: Bundled "tests" AC → split into 7 distinct positive-path ACs.
- CV-2 / CV-3 / CV-4 [BLOCK]: No-CI / empty-workflows-dir / CircleCI+Azure presence-only ACs missing — 3 new typed warning IDs.
- CV-5 [BLOCK]: Registry membership AC missing.
- CV-6 [BLOCK]: Determinism AC missing.
- CV-7 [BLOCK]: `references_secrets` dedup + ordering policy unspecified.
- CV-8 [BLOCK]: Internal regex contradiction (bound in Notes; unbound in Outline).
- CV-9 / CV-10 / CV-11 / CV-12 / CV-13 / CV-14 [HARDEN]: Frozenset+pattern loop; typed-exception routing; schema rejection deepened; confidence rules per scenario; multi-provider order pinned; positive-path ACs for `workflow_files` / `smoke_test_command`.

### Test-Quality critic — Verdict: HARDEN

15 findings (4 block, 11 harden). Highlights:
- TQ-1 [BLOCK]: Test-helper preamble undefined.
- TQ-2 [BLOCK]: Contract-attributes test missing.
- TQ-3 [BLOCK]: Multi-provider test mutation-passable; replace with parametrized total-ordering.
- TQ-4 [BLOCK]: `${{ secrets.X }}` regex bound untested for documented threat model (ReDoS).
- TQ-5/6/7/8/9/10/11/12/13/14 [HARDEN]: Image-build parametrize, secrets parametrize, jenkinsfile parametrize, malformed-workflow assertion, schema-rejection JSON Pointer, registry filter, frozenset invariant, determinism, GitLab-only confidence, secrets semantics.
- TQ-15 [BLOCK]: Refactor section bans parametrize — contradicts sibling pattern.

### Consistency critic — Verdict: HARDEN

10 findings (1 critical, 2 high, 3 medium, 3 low, 1 info). Highlights:
- CN-1 [CRITICAL]: ADR-0007 colon contradiction — resolved (bare ID; arch-doc drift flagged).
- CN-2 [HIGH]: Probe `name` vs catalog `provider` namespace clarity.
- CN-3 [HIGH]: Slice optionality vs `applies_to_languages = ["*"]` interaction (no-CI repo case).
- CN-4 [MEDIUM]: `additional_providers` ordering (catalog vs alpha) not pinned.
- CN-5 [MEDIUM]: `declared_inputs` not pinned verbatim — drift risk.
- CN-6 [MEDIUM]: Confidence outcomes per scenario partially un-pinned.
- CN-7/8/9 [LOW]: Extension-by-addition AC; `version: str` convention; `errors[]` field unaddressed.
- CN-10 [INFO]: Aligned items — production ADR-0005, ADR-0009, design.md §2.4, list-vs-tuple discipline (no S2-02 bug repeat).

### Design-Patterns critic — Verdict: HARDEN

13 findings (4 block, 6 harden, 3 nit). Highlights:
- DP-1 [BLOCK]: `_CI_PARSERS` dispatch registry.
- DP-2 [BLOCK]: `_PROVIDER_PRECEDENCE` anchor at file boundary.
- DP-3 [BLOCK]: `_IMAGE_BUILD_MARKERS` table; fix run-vs-uses contradiction.
- DP-4 [BLOCK]: Functional core / imperative shell — extract 5 pure helpers.
- DP-5/6/7/8 [HARDEN]: Tagged union / TypedDict / ParserKind alias / shared confidence helper — surfaced in Notes as deferred (rule-of-three not yet met cross-file).
- DP-9 [HARDEN]: Import-time ADR-0007 pattern assertion + frozenset.
- DP-10/11/12/13 [NIT]: Deferred-patterns subsection; `references_secrets` policy; no-CI positive test; `_GHAResult` TypedDict.

## Final stats

- ACs: 7 → **27** (one observable per AC; all individually-verifiable)
- TDD tests: 6 → **22** (most parametrized; explicit helper preamble; sentinel + ReDoS + determinism + frozenset + schema-walk tests)
- New typed warning IDs added: 3 (`ci.empty_workflows_dir`, `ci.circleci_presence_only`, `ci.azure_pipelines_presence_only`); total now 8.
- New module-level Open/Closed seams: 6 (`_PROVIDER_PRECEDENCE`, `_CI_PARSERS`, `_IMAGE_BUILD_MARKERS`, `_TEST_COMMAND_MARKERS`, `_SECRETS_RE`, `_JENKINS_SH_RE`, `_WARNING_IDS`) — each with import-time anchor assertions.
- New pure helpers required: 5 (functional core / imperative shell).
- Critical contradictions resolved: 3 (CN-1 / CV-8 / TQ-15).
- Arch-doc drifts flagged for follow-up: 1 (line 540 colon-suffixed WarningId violates ADR-0007).
