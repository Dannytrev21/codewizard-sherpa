# Validation report — S2-03 Fixture `node_typescript_helm/`

**Story:** [S2-03-fixture-node-typescript-helm.md](../S2-03-fixture-node-typescript-helm.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-03 is a **data-fixture story** — its only code is the shape test under `tests/unit/`. The fixture flows into S2-04 (warm-path memo integration), S2-05 (cache-hit), S5-05 (Layer A e2e), and S6-01 (golden seed). Because the fixture's bytes are part of the contract (the golden's input), every prescribed file and every byte inside has multi-test load-bearing meaning. The original story specified the fixture tree correctly but under-specified *verifiable invariants*: the ACs guaranteed file *presence* and the shape test asserted *presence*. Content correctness, parseability through the parsers each probe will use, closed-set complement, and forbidden subpaths all lived in prose (Implementation outline / Notes-for-implementer) rather than as ACs.

Critic synthesis surfaced 4 block-tier gaps and ~10 harden-tier gaps. The synthesizer applied edits in place:

- **AC count: 12 → 23.** Each new AC is individually verifiable and binds an observable that the executor's Validator pass can check.
- **Test-Quality**: replaced the loose `REQUIRED_FILES: tuple[str, ...]` + thin `test_package_json_declares_express` pattern with a typed `_FileSpec` NamedTuple + `_FILE_SPECS: tuple[_FileSpec, ...]` module-level constant. Each file carries a typed `consumers` tuple (closed-set `Literal`), a `parser` discriminator, and a tuple of pure `content_checks` predicates. The TDD plan now spans 9 test functions covering presence, parseability, content invariants, line endings, forbidden subpaths, closed-set complement, README cross-reference, the `_ProbeName` Literal contract, and the no-copy-from-production defensive check.
- **Design-pattern lifts (per CLAUDE.md "Extension by addition" load-bearing commitment)**: `_FILE_SPECS` is the single source of truth for the shape test, the README cross-reference test, and (in Phase 2) the per-fixture golden manifest. Same Open/Closed-at-file-boundary precedent S2-01 set with `_MONOREPO_PRECEDENCE` and S2-02 set with `_LOCKFILE_PRECEDENCE`. Adding a fixture file is a one-tuple-entry insertion with zero edits to the parametrized test bodies.
- **Consistency**: added **ADR-0012** to "ADRs honored" — `values-prod.yaml` is the load-bearing exemplar of the multi-env `environments: list` shape and the original story referenced the ADR's effect (AC-10) without citing the ADR.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0004 / ADR-0010 / ADR-0012 + the frozen Phase 0 `Probe` ABC) plus the S2-01 / S2-02 hardened-story precedents already in the same `stories/` directory. Stage 3 (researcher) skipped per the skill's token-economy guidance.

## Critics run (inline synthesis)

Given S2-03 is a small, tightly scoped data-fixture story (~150 lines of doc, no code-producing scope), the four critics were synthesized inline against the original story + the arch design (`phase-arch-design.md` §§"Component design" #1/#2/#5/#6, "Fixture portfolio", "Edge cases" rows 11+15) + ADRs 0004 / 0010 / 0012 + the S2-01 / S2-02 hardened-story precedents. Token-economy alternative to spawning four subagents per the skill's guidance.

### Critic A — Coverage

| Severity | Finding | Resolution |
|---|---|---|
| **block** | The original AC pinning `pnpm-lock.yaml` requires only "valid pnpm v6 lockfile header." It does NOT require the file actually parses through `parsers.safe_yaml.load`. S2-04's warm-path memo test and S5-05's e2e BOTH parse this file; a malformed minimal header would fail opaquely downstream. | Added **AC-3** (parseability invariant via `safe_yaml.load`). Same pattern applied to every parseable file: AC-2b (`safe_json` on `package.json`), AC-4c (`jsonc` on `tsconfig.json`), AC-7/8/9/10 (`safe_yaml` on the YAML triad + workflow). |
| **block** | The original story specified "No `packageManager` field in `package.json`" only in Notes-for-implementer. A future implementer (or LLM editor) could trivially add the field without any failing test. | Lifted to **AC-2c** as a positive observable; the `_pkg_omits_package_manager(pkg)` predicate inside `_FILE_SPECS["package.json"].content_checks` makes it test-enforced. |
| **block** | The original story specified "No `.gitignore` inside the fixture" + "No `node_modules/`" only in Notes-for-implementer. Either could be added by mistake and silently break test isolation or pollute the S6-01 golden. | Added **AC-13** (forbidden subpaths absent); enforced by `test_no_forbidden_subpaths` parametrized over `node_modules`, `.codegenie`, `.gitignore`, `dist`, `coverage`. |
| **block** | The original story had no closed-set complement: nothing prevented a stray file (e.g., a Codex-generated `notes.md`) from being added to the fixture. The S6-01 golden would catch it — but only after S6-01 lands and only by regen-diff, not at S2-03 land-time. | Added **AC-14** (closed-set complement); enforced by `test_fixture_tree_is_closed_set` which walks the fixture and asserts the path set equals `{spec.relpath for spec in _FILE_SPECS}` minus a controlled noise allowlist. |
| harden | The `tsconfig.json` "both comment styles" invariant — load-bearing per Notes ("Without comments, the file would parse via plain JSON and the `jsonc.py` code path stays untested in integration") — was not observable. | Added **AC-4b** + the standalone `test_tsconfig_has_both_comment_styles` (separate from `content_checks` because it operates on raw bytes, not the parsed structure). |
| harden | `.nvmrc` exact-bytes was implied (`v20.11.0\n`) but not asserted. A trailing-space mutation would silently dirty the golden. | Added **AC-5** + `_nvmrc_exact(raw_bytes)` predicate. |
| harden | `src/index.ts` content was specified as "trivial valid TS body (one `import express from "express"` + a 3-line server stub)" but only the file's existence was tested. | Added **AC-6** + `_index_ts_imports_express(raw_bytes)` predicate. |
| harden | `Chart.yaml` apiVersion = v2 + `values-prod.yaml` image override + CI workflow single-`build`-job-with-pnpm-step — all prescribed in ACs but none tested beyond file existence. | Added structured `content_checks` predicates for each (AC-7 / AC-8 / AC-9 / AC-10). |
| harden | README freshness: the original story said the README "lists every file in the tree and the probe that consumes it" — but had no mechanism to detect drift if a file was added later and the README wasn't updated. | Added **AC-17** + `test_readme_references_every_spec` which asserts every `_FILE_SPECS[i].relpath` AND every consumer name appears literally in the README text. |
| harden | LF line endings + final newline were mentioned in Refactor but not pinned as ACs. | Added **AC-19** + `test_fixture_file_line_endings` parametrized over `_FILE_SPECS`. |
| harden | `mypy --strict` cleanliness over the shape test was mentioned in Refactor but not an AC. | Added **AC-20**. |

### Critic B — Test-Quality (mutation-resistance lens)

The original TDD plan was a parametrized existence test + one `test_package_json_declares_express` content check. **Eleven worked mutations would have passed the original suite**:

| Mutation | Caught now by | Original suite passed? |
|---|---|---|
| Drop `express` from `package.json#dependencies` | `_pkg_declares_express` (AC-2a) | NO (would catch — this was the one content check that existed) |
| Add `"packageManager": "pnpm@8.6.0"` to `package.json` | `_pkg_omits_package_manager` (AC-2c) | **YES** — passes original |
| Set `pnpm-lock.yaml` `lockfileVersion: '5.0'` | `_pnpm_lock_header` (AC-3) | **YES** — passes original |
| Remove `/* */` block comment from `tsconfig.json` | `test_tsconfig_has_both_comment_styles` (AC-4b) | **YES** — passes original |
| Add a stray `notes.md` to the fixture | `test_fixture_tree_is_closed_set` (AC-14) | **YES** — passes original |
| Add `node_modules/lodash/package.json` (common autocomplete mistake) | `test_no_forbidden_subpaths[node_modules]` (AC-13) | **YES** — passes original |
| README drops the `deployment` consumer reference | `test_readme_references_every_spec` (AC-17) | **YES** — passes original |
| CRLF line endings sneak in via Windows editor | `test_fixture_file_line_endings` (AC-19) | **YES** — passes original |
| `values-prod.yaml` gets `image.tag: "0.0.1"` (no override) | `_values_prod_image_override` (AC-10) | **YES** — passes original |
| Implementer corrupts `pnpm-lock.yaml` so `safe_yaml.load` throws | `test_fixture_file_parses[pnpm-lock.yaml]` (AC-3) | **YES** — passes original |
| Future implementer adds a 7th probe name to `_ProbeName` (Phase-2 sneak-in) | `test_probe_name_literal_matches_phase_1_closed_set` (AC-18) | **YES** — passes original (no contract test existed) |

The hardened suite catches every one of these.

### Critic C — Consistency

| Severity | Finding | Resolution |
|---|---|---|
| harden | Original **ADRs honored** line cited only ADR-0010 (envelope-optionality, "irrelevant here — the fixture is Node"). The fixture's `values-prod.yaml` is the direct load-bearing exemplar of **ADR-0012**'s `environments: list[EnvironmentEntry]` shape — AC-10 references the ADR's effect but the header did not cite the ADR. | Updated header: ADRs honored now includes ADR-0004 (per-probe sub-schema strictness flows through this fixture's deployment slice) and ADR-0012 (multi-env Helm). |
| harden | Phase 1 fixture portfolio (`phase-arch-design.md §"Fixture portfolio"`) describes this fixture as "TypeScript + pnpm + GitHub Actions + Helm with multi-env values" — the original story's Context did not explicitly reference this canonical description. | Existing Context line ("The fixture's name — `node_typescript_helm` — telegraphs the four dimensions it exercises: Node, TypeScript, pnpm, Helm.") is sufficient; left as-is. |
| nit (flagged-not-fixed) | `engines.node = ">=20.0.0"` (range) vs. `.nvmrc = "v20.11.0"` (pin) vs. runtime `node --version` (whatever CI has installed) — depending on the runtime resolver, the `node.version_declared_resolved_disagree` warning could fire and dirty the S6-01 golden non-deterministically. | **Deferred to S6-01.** This story is for the fixture content; the deterministic-golden invariant is S6-01's responsibility (the regen script disables the ADR-0001-gated cross-check or pins the regen environment's Node). Recorded in Notes-for-implementer; **no AC added** because adding one would force S2-03 to anticipate S6-01's resolution. Documented as a known interaction. |
| nit | The story's `framework_hints == ["express"]` claim (Context line 13, S2-04 promise) is consistent with the `package.json` shape: `express` in dependencies → S2-01's `_FRAMEWORK_HINTS` dict-lookup → singleton `["express"]`. | No change. |

### Critic D — Design-Patterns (per user request — primary focus)

The original shape test used a loose `REQUIRED_FILES: tuple[str, ...]` and a single hand-written `test_package_json_declares_express`. This is *adequate* code (Rule 2 — three similar lines is better than premature abstraction), but **the within-file rule of three is met three times over**:

1. Three downstream tests (S2-04, S5-05, S6-01) consume the fixture's paths.
2. The README, the shape test, and the (future) golden regen script all enumerate the same file list.
3. Nine of the ten files have at least one content invariant to enforce.

| Severity | Pattern | Decision |
|---|---|---|
| **harden** | **Closed-set typed manifest as SSoT** (`_FILE_SPECS: tuple[_FileSpec, ...]` module-level NamedTuple tuple). Same Open/Closed-at-file-boundary precedent S2-01 set with `_MONOREPO_PRECEDENCE` and S2-02 set with `_LOCKFILE_PRECEDENCE`. | **Lifted to ACs** (AC-15, AC-16). Adding a fixture file = one tuple entry insertion + zero edits to the parametrized test bodies. The `_FileSpec` NamedTuple carries `(relpath, consumers, parser, content_checks)`. |
| **harden** | **Closed-set `Literal` for probe names** (`_ProbeName = Literal["language_detection", ...]`). `mypy --strict` catches typos in the `consumers` tuple; runtime contract test (`test_probe_name_literal_matches_phase_1_closed_set`) pins the Phase-1 set so a Phase-2 sneak-in is a deliberate edit. | **Lifted to ACs** (AC-15, AC-18). Closed-set domain-identifier discipline — same pattern recommended in CLAUDE.md's "Newtype pattern for every domain primitive" + "Make illegal states unrepresentable." |
| **harden** | **Closed-set `Literal` for parser kinds** (`_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]`). Matches the four parser modules + a `text` sentinel for non-parseable files. Adding a fifth parser is a deliberate edit. | **Lifted to AC-15.** |
| **harden** | **Pure predicate functions** for `content_checks`. Each predicate (`_pkg_declares_express`, `_pnpm_lock_header`, `_chart_apiversion_v2`, etc.) is a pure function from parsed structure → AssertionError. Independently unit-testable, easy to compose, no hidden state. Matches CLAUDE.md's "Functional core, imperative shell." | **Lifted to AC-16.** Each predicate's failure message names the AC it enforces. |
| **harden** | **README mechanical cross-reference** (AC-17 + `test_readme_references_every_spec`). The README is no longer prose-only — it's a derived artifact whose freshness is mechanically verified against `_FILE_SPECS`. Drift fails the test. | **Lifted to AC-17.** |
| **defer** | **Generic `tests/fixtures/_shape_test_kernel.py`** that parametrizes the shape-test over any fixture's `_FILE_SPECS`. Rule of three NOT met within Phase 1 (only one fixture has a shape test). | **Deferred** to S5-04 (third + fourth fixtures land). Documented in Notes-for-implementer. |
| **defer** | **YAML-based `MANIFEST.yaml`** as a non-Python SSoT inside the fixture tree. Slightly cleaner SoC; adds parser hop + extra fixture file (AC-14 would need to allowlist it). | **Deferred** — Python-as-SSoT keeps the SSoT next to its primary consumer (the shape test). Documented in Notes-for-implementer. |
| **defer** | **`FixtureConsumer` sum type / tagged union** over probe-name + downstream-test annotation. | **Deferred** — probe name is the load-bearing identity. Documented in Notes-for-implementer. |
| **defer** | **`RelPath = NewType("RelPath", str)`** for the `relpath` field. | **Deferred** — string never crosses a module boundary in Phase 1. Documented in Notes-for-implementer. |

## Conflicts surfaced (per Rule 7 — Surface conflicts, don't average)

- **Rule 2 ("Simplicity first") vs. Design-Patterns critic's "lift `_FILE_SPECS`":** The original story was already simple — `REQUIRED_FILES` + one content check. Lifting `_FILE_SPECS` adds structure. Resolved in favor of the lift because the within-file rule of three is met three times over (multiple downstream tests, multiple consumers per file, nine content invariants) AND because S2-01's `_MONOREPO_PRECEDENCE` + S2-02's `_LOCKFILE_PRECEDENCE` set the same Open/Closed precedent in the same sibling stories. The structure pays for itself in this story; deferring would force the next implementer to retrofit it.

- **Coverage critic's "add AC for `node --version` cross-check disable" vs. Consistency critic's "fixture cannot anticipate S6-01's regen script":** Resolved in favor of Consistency. The deterministic-golden invariant lives at S6-01. This story documents the interaction in Notes-for-implementer (so S6-01's implementer is forewarned) but **does not add an AC**. Adding one would couple S2-03 to S6-01's implementation, breaking the story's INVEST-N "Negotiable" property.

- **Design-Patterns critic's "lift a generic `_shape_test_kernel.py`" vs. Rule 2:** Resolved in favor of Rule 2 (deferred). One fixture with a shape test in Phase 1; extraction earns its keep at three+ consumers.

## Files edited

- **`docs/phases/01-context-gather-layer-a-node/stories/S2-03-fixture-node-typescript-helm.md`** — header (Status timestamp, ADRs honored list), inserted `Validation notes (2026-05-14)` block, rewrote Acceptance criteria (12 → 23), rewrote Implementation outline (added test-first step), rewrote TDD plan (helpers preamble + 9 test functions + mutation-resistance witness table), rewrote Notes-for-implementer (added Design-pattern lifts subsection + Deferred patterns subsection).
- **`docs/phases/01-context-gather-layer-a-node/stories/_validation/S2-03-fixture-node-typescript-helm.md`** — this report.

## Final verdict

**HARDENED.** The story is ready for `phase-story-executor`. The 23 ACs are individually verifiable; the 9-test TDD plan catches 11 worked mutations the original suite missed; the `_FILE_SPECS` SSoT extends the codebase's Open/Closed-at-file-boundary precedent (S2-01, S2-02) without introducing premature abstraction.
