# Validation report — S8-01 (Phase 3 fixture portfolio: ≥10 repos incl. ≥5 CVE fixtures)

**Validated:** 2026-05-20
**Validator:** `phase-story-validator` skill (automated, scheduled task `story-validation-corrector`)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S8-01-fixture-portfolio.md`
**Verdict:** **HARDENED** — substantial edits applied. The story's goal (a ten-fixture Phase-3 portfolio + smoke loader + pinning/size fences) is sound and traces 1:1 to `phase-arch-design.md §Testing strategy §Fixture portfolio`, the roadmap exit criterion, and ADR-0008/0001/0010. The defects are reconciliation-with-on-disk-reality and test-mechanism-layer — none touches the goal — so per `editor.md` Step 3 this is HARDENED, not RESCUE.

## Methodology note

This run applied the four critic lenses (Coverage, Test-Quality, Consistency, Design-Patterns) inline rather than as four separately-spawned subagents: the Stage-1 context load had already read the story, `phase-arch-design.md §Testing strategy / §Edge cases / §C12`, `High-level-impl.md §Step 8`, the three referenced ADRs' anchors, the as-built `tests/fixtures/` tree, `tests/fixtures/_shape_test_kernel.py`, `tests/fixtures/README.md`, `src/codegenie/parsers/safe_json.py` + `_depth.py`, and the sibling stories S8-02/03/04. Re-spawning four subagents to re-read the same corpus would have burned token budget (global Rule 6) with no added signal. No finding required Stage-3 research — every fix is grounded in an existing repo precedent.

## Context Brief

- **Story snapshot.** Land 10 hand-authored fixture repos (≥5 carrying real CVEs), each with a byte-pinned `package-lock.json` and a four-section README, plus a smoke loader and lockfile-pinning / size-cap fences. The portfolio is the substrate for S8-02 (golden e2e), S8-03 (determinism property), S8-04 (adversarial regressions) and Step-9 benches.
- **Sibling-family lineage.** First story of Step 8. The fixture-shape-test *kernel* family is already mature: `tests/fixtures/_shape_test_kernel.py` has **8 consumers** (`test_fixture_minimal_ts_shape.py`, `…monorepo_pnpm…`, `…native_modules…`, `…distroless_target…`, `…node_monorepo_turbo…`, `…node_typescript_helm…`, `…non_node_go…`, `…stale_scip…`) and `tests/fixtures/README.md` documents the pattern as load-bearing ("one tuple-entry insertion … Open/Closed at the file boundary"). Rule-of-three for a fixture-list kernel is conclusively past.
- **Build-order reality.** Phase-3 `_attempts/` reaches S5-01 (S1-01..S5-01 are `Done — GREEN`; S5-02..S7-05 are `HARDENED` but unexecuted). The S6-04 e2e vertical slice — which S8-02's Context says creates the `express-cve-2024-21501/` stub — has not run; **no such directory exists anywhere in the tree.**
- **On-disk collisions.** Two of the ten named fixtures already exist under other paths: `tests/fixtures/portfolio/stale-scip/` (Phase 2 / S7-02 — shape-tested, ~20 probe goldens, `tests/adv/phase02/test_stale_scip_fixture.py`) and `tests/fixtures/phase03/postinstall_canary/` (Phase 3 / S4-02 — `test_bwrap_postinstall_canary.py`).
- **Load-bearing commitments implicated.** "Extension by addition" / "Open/Closed at the file boundary" (the manifest + kernel reuse), "Newtype identifiers — never raw `str`" (CVE ids), "Match the existing convention" (Rule 11 — `README.md`, the shape-test kernel), "Surface conflicts, don't average" (Rule 7), "Surgical changes" (Rule 3 — no renaming other phases' fixtures).

## Critic findings (consolidated)

Four lenses — Coverage (`CV`), Test-Quality (`TQ`), Consistency (`CN`), Design-Patterns (`DP`). 19 findings: 3 block-class, 12 harden, 4 nit.

### Block-class (each with a clear in-place fix → HARDENED, not RESCUE)

| ID | Finding | Resolution |
|---|---|---|
| CN-1 | **The "S6 stub" premise is false.** Context, AC-1 (`express-cve-2024-21501/` "extended from S6 stub"), outline §1, and Files-to-touch ("extend") all assume Step 6 landed an `express-cve-2024-21501/` stub. No such directory exists; S6-04 (the e2e slice that creates it, per S8-02's Context) is unexecuted. `Depends on: S6-06` is also wrong — S6-06 is the phase5-contract-snapshot, unrelated. | AC-1 + Context + outline §1/§4 + Files-to-touch reframed to **create-or-extend**; `Depends on:` corrected to S5-05 (outcome vocabulary) + S6-04 (the real stub origin), soft S6-06. |
| CN-2 | **`stale-scip/` already exists** at `tests/fixtures/portfolio/stale-scip/`. The story says "create NEW", and prescribes committing a `.codegenie/scip/index.scip` — which the shared kernel's `_FORBIDDEN_SUBPATHS` (`{.codegenie, node_modules, dist, coverage, build}`) bans. | AC-1 `stale-scip` item rewritten to **reuse in place**; the `.codegenie/`-committed prescription dropped; outline §6/§7 (the mtime-mangling conftest) removed — the existing fixture already solves staleness via `_seed/` + `regenerate.sh`. |
| CN-3 | **`postinstall-canary` already exists** at `tests/fixtures/phase03/postinstall_canary/` (consumed by `test_bwrap_postinstall_canary.py`). The story says "create NEW". | AC-1 `postinstall-canary` item rewritten to **reconcile / reuse**; new AC-9 forbids two same-named fixtures; the cross-story path conflict (S8-03/S8-04 hardcode `tests/fixtures/repos/`) is surfaced in Notes + Out-of-scope rather than silently relocated. |

### Harden-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| CN-4 | `README.fixture.md` contradicts the established convention — zero such files exist; the kernel's `assert_readme_references_every_spec` and all 8 fixture shape-tests + `tests/fixtures/README.md` use `README.md`. The story's Notes claimed `README.fixture.md` was "more recent" (false) and told the implementer to "flag the older convention for cleanup" (a Rule-3 cross-phase rename). | `README.fixture.md` → `README.md` throughout (`replace_all`); the false "more recent" claim and the cleanup instruction removed; a Notes bullet pins `README.md` + Rule 3. |
| CN-5 / DP-3 | The story ignores the established fixture-shape-test kernel and reinvents ad-hoc assertions in `test_fixtures_load.py`. `tests/fixtures/README.md` documents the kernel as THE pattern. | AC-4 + outline §6 + Notes mandate consuming `_shape_test_kernel.py` helpers (`assert_file_exists/parses/line_endings`, `assert_no_forbidden_subpath`, `assert_tree_is_closed_set`); a new References sub-section lists the as-built kernel. |
| DP-1 | The 10-fixture list is re-declared across `test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py` (this story) **plus** S8-03's `_REPO_FIXTURES`/`_CVE_IDS` and S8-04. 6+ consumers — rule-of-three conclusively past. | New **AC-7**: a single typed `tests/fixtures/repos/_portfolio.py` manifest — `Final` tuple of frozen `FixtureSpec` records. All fence tests import it. New **AC-8**: observable Open/Closed AC — adding an 11th fixture is one manifest row + one dir, zero fence-logic edits. |
| DP-2 | Newtype discipline absent — fixture CVE ids would be raw `str`; the adversarial/benign split was an ad-hoc `[n for n in … if n != "malformed…"]` comprehension (illegal-state-representable). | AC-7 mandates `cve_ids: tuple[CveId, ...]` via the `parse_cve_id` smart constructor, and `is_adversarial: bool` as the single source of the parse-expectation split. |
| TQ-1 | `test_malformed_fixture_actually_malformed` counts `{` braces and asserts `> 16` — brace count ≠ nesting depth (20 sibling objects at depth 2 pass the proxy). Verifies the wrong thing (Rule 9). | TDD red test rewritten: `with pytest.raises(DepthCapExceeded): safe_json.load(pkg, max_bytes=1 MiB, max_depth=16)` — drives the real depth-capped parser (arch §C12). |
| TQ-2 | `test_readme_has_four_sections` checks substring presence only — no "exactly four", no order; a 5-section or reordered README passes. AC-3 says "exactly four". | AC-3 + the red test rewritten to extract the ordered `^## ` heading list and assert equality with the four expected titles in order. |
| TQ-3 / CV-1 | TDD plan is **incomplete vs AC-4** — AC-4 requires asserting `package-lock.json` parses (and `malicious-npmrc` ships an `.npmrc`), but the red test had no lockfile-parse test and no `.npmrc` test. The pinning + size-cap fences were prose-only — no red test. | Red section adds `test_non_adversarial_lockfile_parses_and_is_v3` and `test_malicious_npmrc_fixture_ships_the_npmrc`; a paragraph specifies the pinning + size-cap fences' red tests (planted `^`-version / `sha512-TODO` / `file:` URL / 300-KiB fixture). |
| CV-3 / TQ-4 | AC-2's pinning fence checked only `^`/`~` via raw grep; outline §3 listed a wider set; neither verified `integrity`/`resolved` shape — a `sha512-TODO` placeholder passed. | AC-2 rewritten: structural inspection of parsed JSON fields — exact-semver `version`, `^sha512-[A-Za-z0-9+/]+={0,2}$` `integrity`, `registry.npmjs.org` `resolved`. Raw-grep brittleness removed. |
| CV-2 | The "8 non-adversarial" count is ambiguous (there are 7 truly-benign fixtures; the wording silently folds `postinstall-canary` in). | AC-4 derives the split from `FixtureSpec.is_adversarial` — the count is now data, not prose arithmetic. |
| CV-4 | The story's `ADRs honored` line, References §Edge-cases line, and Refactor list claim **E11 (`cve_delta`)** and **E2 (Yarn Berry)** coverage, but no fixture provides either substrate. | References line + Refactor list corrected; Out-of-scope gains an explicit E11 bullet pointing at S8-04's `test_cve_delta_introduced.py`. |
| CN-6 | The `tests/conftest.py` canary-cleanup extension (outline §7, Files-to-touch) and the `stale-scip` mtime conftest (outline §6) are S8-04 scope — this story's smoke loader never runs `npm install` or checks mtime (Rule 3). | Both dropped from Files-to-touch + outline; an Out-of-scope bullet reassigns the conftest cleanup to S8-04. |
| CV-5 | The downstream cross-story path conflict — S8-02/03/04 hardcode `tests/fixtures/repos/` for *all* fixtures including the two reused ones — was invisible. | A Notes bullet + Out-of-scope bullet surface it; AC-1's `postinstall-canary` item makes surfacing it part of the AC. (Rule 7 — surfaced, not averaged.) |

### Nit-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| CN-7 | `tests/fixtures/repos/` is a 4th fixture-location convention (flat Phase-1, `portfolio/`, `phase03/`, now `repos/`). | Kept `repos/` — the arch §Testing strategy and all four S8 stories name it; changing it would desync S8-01 from S8-02/03/04 (Consistency + sibling-story consistency). A References bullet documents the divergence so fixtures aren't scattered. |
| CV-5b | AC-1 mixed `RecipeOutcome` and `RemediationOutcome` in the per-fixture "Expected outcome" prose. | Left as-is in prose (the data model genuinely distinguishes internal `RecipeOutcome`/`ApplyResult` from contract `RemediationOutcome`; S8-02/S8-04 assert the real types). Flagged here so downstream readers aren't misled. |
| TQ-5 | The red test's `_EXPECTED_FIXTURES` tuple was itself an instance of the DP-1 duplication. | Resolved by AC-7 — the red test imports `PORTFOLIO` from the manifest. |
| DP-4 | The Goal's path `tests/fixtures/test_fixtures_load.py` and "Land all 10 fixture repos under `tests/fixtures/repos/`" went stale after the reuse decision. | Goal lightly corrected (path → `tests/fixtures/repos/test_fixtures_load.py`; "eight new + two reused"). Not a goal/scope rewrite — a factual-consistency fix. |

## Research briefs

None — no finding was tagged `NEEDS RESEARCH`. Every prescribed pattern (depth-capped parsing via `safe_json`, the `_shape_test_kernel.py` consumer pattern, a single typed manifest, `CveId` newtype + `parse_cve_id`) is an existing, shipped repo precedent.

## Conflict resolutions

- **DP-1 (single manifest) vs Rule 2 (no premature abstraction).** Rule-of-three is conclusively crossed — 3 fence files in *this story alone*, plus S8-03 and S8-04. Per `editor.md` Step-2 rule 5, the extract is mandated; per rule 4 it lands as an *observable* AC (AC-7/AC-8: "one manifest row, zero fence-logic edits"), never a pattern-name AC. Resolved for DP-1.
- **CN-7 (`repos/` is a 4th location) vs Rule 11 (match the `portfolio/` convention).** `phase-arch-design.md §Testing strategy` and all four S8 stories (S8-02 line 30, S8-03 line 33, S8-04 lines 38/85/169) hardcode `tests/fixtures/repos/`. Per `Consistency > Design-Patterns` and sibling-story consistency, `repos/` is kept; the divergence is surfaced (Rule 7), not averaged away.
- **CN-2/CN-3 (reuse existing fixtures) vs the story's literal "create NEW".** Reuse wins — Rule 2 (don't author duplicates) and Consistency (on-disk reality). The story is hardened to "reuse / reconcile" with an explicit no-duplicates AC.

## Edits applied

1. **Header** — `Status: Ready → HARDENED`; `Depends on:` corrected from `S6-06` alone to S5-05 + S6-04 (+ soft S6-06) with rationale.
2. **`## Validation notes`** block inserted after the header — verdict, finding counts, 7 numbered key corrections.
3. **Context** — a "Reconciliation with on-disk reality" paragraph replaces the false "Step 6 already created an `express-cve-2024-21501/` stub … this story extends that one" sentence.
4. **References** — the §Edge-cases line corrected (drops the false E2/E11 claims); the "Existing code / fixtures" bullets corrected (the non-existent S6 stub replaced with the real Phase-2 portfolio precedents); a new "As-built code this story must consume / reconcile against" sub-section added (kernel, conventions doc, the two pre-existing fixtures, `safe_json`).
5. **Goal** — path + "eight new + two reused" factual correction.
6. **Acceptance criteria** — restructured into numbered AC-1..AC-11; per-fixture dispositions (create / create-or-extend / reuse) made explicit; AC-2 (structural pinning fence), AC-3 (exactly-four ordered README sections), AC-4 (exhaustive smoke loader + kernel) hardened; **AC-7 (typed manifest), AC-8 (Open/Closed extension AC), AC-9 (no duplicate fixtures)** added.
7. **Implementation outline** — rewritten 9-step: reconcile-first, manifest-first, create-7, create-or-extend express, reuse-2, then loader / pinning / size fences. The two conftest steps removed.
8. **TDD plan** — Red rewritten against real APIs: imports the manifest + `safe_json` + the kernel; the brace-count proxy replaced with a `DepthCapExceeded` parse; lockfile-parse / `.npmrc` / ordered-README / forbidden-subpath / ≥5-CVE / no-duplicate tests added. Refactor list's E-case set corrected (E11 removed).
9. **Files to touch** — added `_portfolio.py`; the two pre-existing fixtures changed to `REUSE — no edit`; `tests/conftest.py` dropped; fence-test paths moved under `tests/fixtures/repos/`.
10. **Out of scope** — added the E11 fixture, the conftest canary cleanup, and the relocation of Phase-2/3 fixtures.
11. **Notes for the implementer** — rewritten: consume the kernel, the `_portfolio.py` manifest as design centre, reuse-don't-duplicate, the cross-story path conflict, structural pinning, `README.md` not `README.fixture.md`, deep-not-wide malformed JSON.

## Verdict rationale

**HARDENED.** Three block-class findings, twelve hardens, four nits — but every block has a concrete in-place fix verified against repo source (the missing `express-cve-2024-21501/` directory, the pre-existing `portfolio/stale-scip/` and `phase03/postinstall_canary/` fixtures, the `_FORBIDDEN_SUBPATHS` ban on `.codegenie/`). None requires rewriting the story's goal — the portfolio's purpose and its 1:1 trace to the arch are intact. After the edits every AC is individually verifiable, the smoke loader fails against a wrong fixture (a depth-capped parse, exact section/order checks, structural lockfile-field inspection), and the prescribed implementation consumes the established kernel + a single typed manifest so adding an eleventh fixture is a one-row change (Open/Closed — the maintainability goal the scheduled task explicitly asked for).

## Residual risks (flagged, not blocking)

- **S6-04 is unexecuted.** AC-1 now creates `express-cve-2024-21501/` from scratch if absent — but the implementer must confirm, when S6-04 *does* land, that the two do not diverge. The story instructs create-or-extend and the manifest is the reconciliation point.
- **Cross-story path coupling.** S8-03/S8-04 hardcode `tests/fixtures/repos/` for the two reused fixtures. The hardened story surfaces this (Notes + Out-of-scope + AC-1) but does not resolve it — that reconciliation (have S8-03/S8-04 read the manifest's `path` field, or a follow-up that unifies the directory) is deliberately left to those stories' own validation/execution, since editing them is outside S8-01's surgical scope.
- **`assert_no_forbidden_subpath` on the reused `stale-scip`.** The kernel helper does a raw `.exists()` check; the reused `stale-scip` fixture has a *gitignored* `.codegenie/`/`.git/` that may be present on disk after a local `regenerate.sh` run. The executor should scope forbidden-subpath policing to the eight S8-01-owned fixtures (the two reused ones have their own shape tests) or use `enumerate_tracked`. Noted for the executor; not blocking.
