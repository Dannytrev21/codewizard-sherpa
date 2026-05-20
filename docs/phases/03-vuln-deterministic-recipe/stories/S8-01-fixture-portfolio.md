# Story S8-01 — Fixture portfolio (≥10 repos incl. ≥5 CVE fixtures)

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S8-01-fixture-portfolio.md`](_validation/S8-01-fixture-portfolio.md))
**Effort:** L
**Depends on:** S5-05 (the `RemediationOutcome` / `RecipeOutcome` variant vocabulary each fixture's `README.md` "Expected outcome" section cites), S6-04 (the e2e vertical slice that — per S8-02's Context — creates the `express-cve-2024-21501/` stub this story claims to extend; **may not exist on disk yet** — AC-1 now creates-or-extends). Soft: S6-06 (contract schemas frozen). (validator: was `S6-06` alone — corrected; S6-06 is the phase5-contract-snapshot story, unrelated to the fixture portfolio.)
**ADRs honored:** ADR-0008 (deterministic Bundle requires every fixture's `package-lock.json` to be pinned bytes-for-bytes — registry drift would flip the property test green/red across days), ADR-0001 (`remediation-report.yaml` schema-snapshot tests in Step 6 are only meaningful if Step 8's fixtures exercise every variant of `RemediationOutcome` — `Validated(passed=True)`, `Validated(passed=False)`, `NotApplicable`, `RequiresHumanReview`), ADR-0010 (each fixture's `package.json` `name` field must round-trip through `parse_package_id` — adversarial fixtures `malformed-package-json/` and `malicious-npmrc/` deliberately violate this to verify smart-constructor rejection)

## Validation notes

**Validated:** 2026-05-20 · **Verdict:** HARDENED · **Validator:** `phase-story-validator` (automated, scheduled task `story-validation-corrector`)

19 findings addressed — 3 block-class (each with a clear in-place fix), 12 harden, 4 nit. The goal (a 10-fixture Phase-3 portfolio + smoke loader + pinning/size fences) is sound and traces cleanly to `phase-arch-design.md §Testing strategy §Fixture portfolio` and the roadmap exit criterion. The defects are reconciliation-with-reality and mechanism-layer, not goal-layer — hence HARDENED, not RESCUE.

Key corrections:
1. **The "S6 stub" premise was false.** No `express-cve-2024-21501/` directory exists anywhere in the tree, and S6-04 (the e2e vertical slice that creates it, per S8-02) is not yet executed (`_attempts/` reaches only S5-01). AC-1 + outline §1 now *create-or-extend*; `Depends on:` corrected.
2. **`stale-scip/` already exists** at `tests/fixtures/portfolio/stale-scip/` (Phase 2 / S7-02 — fully shape-tested, ~20 probe goldens, an adversarial test). The story said "create NEW". It now **reuses the existing fixture in place**; the prescription to commit a `.codegenie/scip/index.scip` was dropped (the shared shape-test kernel's `_FORBIDDEN_SUBPATHS` bans `.codegenie/`).
3. **`postinstall-canary` already exists** at `tests/fixtures/phase03/postinstall_canary/` (Phase 3 / S4-02, consumed by `test_bwrap_postinstall_canary.py`). The story must reconcile, not duplicate — a new AC forbids two same-named fixtures.
4. **`README.fixture.md` → `README.md`.** Zero `README.fixture.md` files exist; the shared kernel `assert_readme_references_every_spec` and all 8 existing fixture shape-tests + `tests/fixtures/README.md` use `README.md`. The story's claim it was "more recent" was false (Rule 11). The "flag the older convention for cleanup" instruction was removed (Rule 3 — S8-01 must not rename other phases' fixtures).
5. **The story ignored the established fixture-shape-test kernel** `tests/fixtures/_shape_test_kernel.py` (8 consumers; `tests/fixtures/README.md` documents it as THE pattern — "one tuple-entry insertion … Open/Closed at the file boundary"). The smoke loader now consumes it.
6. **Single-source fixture manifest** (`tests/fixtures/repos/_portfolio.py`) added — the 10-fixture list was re-declared across 3 fence files in this story alone (plus S8-03 / S8-04). Rule-of-three conclusively past; elevated to an observable AC.
7. TDD plan hardened — the brace-count "is it malformed?" proxy replaced with a real depth-capped parse; missing `package-lock.json`-parse / `.npmrc`-presence tests added; pinning fence given positive field-shape assertions (`integrity` sha512 shape, exact-semver `version`, `registry.npmjs.org` `resolved`).

Full audit log: [`_validation/S8-01-fixture-portfolio.md`](_validation/S8-01-fixture-portfolio.md).

## Context

Phase 3's headline exit criterion ("Given a Node.js repo with a known npm CVE, the system writes a working patch diff…") and Goal G4 (determinism) both depend on a fixture portfolio that does three things at once: (1) exercises every `RecipeOutcome` variant the four npm recipes can emit; (2) covers every adversarial edge case from `phase-arch-design.md §Edge cases E1–E20`; (3) pins each fixture's `package-lock.json` to exact bytes so the determinism property test (S8-03) and the golden-file diff (S8-02) don't flake when the live npm registry mutates.

**Reconciliation with on-disk reality (validator).** The original story assumed Step 6 had already landed an `express-cve-2024-21501/` stub "as part of the end-to-end happy-path scaffold". As of validation that stub does **not** exist anywhere in the tree — the e2e vertical slice that creates it (S6-04, per S8-02's Context) is not yet executed. Two of the other nine fixtures, by contrast, *do* already exist under different paths: `stale-scip` lives at `tests/fixtures/portfolio/stale-scip/` (Phase 2 / S7-02) and `postinstall-canary` lives at `tests/fixtures/phase03/postinstall_canary/` (Phase 3 / S4-02). This story therefore does three different things across the ten: **create** seven genuinely-new fixtures, **create-or-extend** `express-cve-2024-21501/`, and **reuse** the two pre-existing fixtures rather than authoring duplicates. See AC-1 and the Notes for the per-fixture disposition.

Implementation-risk #2 in `High-level-impl.md` calls this out explicitly: "real `npm install` resolutions change when the registry changes. Mitigation: pin every fixture's `package-lock.json` to exact versions; assert no implicit-version `^`/`~` resolution in golden comparisons." A fixture whose lockfile resolves a `^4.17.0` semver range against the live registry is a time bomb — within a year, `4.17.21` becomes `4.17.22` and every downstream test starts producing different `transform.diff_bytes`. The fixture must be self-contained: every entry in `package-lock.json` has an exact `version`, an exact `integrity` sha512, and an exact `resolved` URL.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Fixture portfolio` — names all 10 fixtures with their failure modes; matches this story 1:1.
  - `../phase-arch-design.md §Edge cases E1–E20` — each fixture in this story is the substrate for one or more of these edge cases: E3 (workspaces), E4 (peer-dep conflict), E5 (transitive-only), E6 (major-bump-refuse), E7 (malicious .npmrc → NetworkDenied), E8 (postinstall canary), E18 (degraded adapter / stale SCIP), E20 (adversarial package.json content). **Not covered by this story's ten fixtures:** E2 (Yarn-Berry → universal — its `yarn-berry/` fixture is an S8-04 deliverable, see Out of scope) and E11 (`cve_delta` — `tests/adversarial/test_cve_delta_introduced.py`, also S8-04). (validator: corrected — the original line claimed E2 and E11.)
  - `../phase-arch-design.md §Component design C12` — the `NpmLockfileRecipeEngine` reads `package.json` (1 MiB / depth-16 caps) and `package-lock.json` (32 MiB / depth-24 caps); `malformed-package-json/` is the fixture that hits the depth cap.
  - `../phase-arch-design.md §Goals G4` — the cardinal determinism goal that S8-03 verifies *over these fixtures*; if fixtures aren't byte-pinned, G4 is unverifiable.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — explains why a `^`-ranged lockfile is incompatible with the determinism property; the fixture portfolio is the only way to honor this at scale.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — the contract-snapshot tests passed in S6-06 only verify *schema shape*; this story's fixtures are what give the next story (S8-02) the inputs to verify schema *contents*.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `malformed-package-json/` and `malicious-npmrc/` are designed to fail `parse_package_id` / `parse_registry_url` smart constructors, asserting the discipline holds.
- **Existing code / fixtures:**
  - `tests/fixtures/portfolio/minimal-ts/` and `tests/fixtures/portfolio/monorepo-pnpm/` — the Phase-2 portfolio fixtures; the precedent for `package.json` / lockfile / `README.md` / `.gitignore` / `regenerate.sh` layout to mirror across the new fixtures. (validator: corrected — the original referenced a `tests/fixtures/repos/express-cve-2024-21501/` "S6 stub" that does not exist.)
  - `tests/fixtures/README.md` — the inventory + conventions doc (LF endings, no build artifacts, the one-tuple-entry Open/Closed rule). New fixtures must satisfy it.
  - Note the as-built fixture trees live under `tests/fixtures/` (flat, Phase 1), `tests/fixtures/portfolio/` (Phase 2), and `tests/fixtures/phase03/` (Phase 3). `phase-arch-design.md §Testing strategy` and all four S8 stories name `tests/fixtures/repos/` for the Phase-3 portfolio — keep that path; do not scatter the new fixtures across the older directories.
  - `tests/integration/test_end_to_end_express_cve.py` (S8-02 — sibling story; reads several of these fixtures).
- **High-level impl:**
  - `../High-level-impl.md §Step 8` — enumerates the 10 fixtures and the "≥5 CVE fixtures" roadmap exit-criterion target.
- **As-built code this story must consume / reconcile against (validator-added):**
  - `tests/fixtures/_shape_test_kernel.py` — the **established fixture-shape-test kernel** (8 consumers today). Exports `_FileSpec`, the closed `_ParserKind` Literal, `_FORBIDDEN_SUBPATHS` (note: includes `.codegenie`, `node_modules`, `dist`, `coverage`, `build`), and flat helpers `assert_file_exists` / `assert_file_parses` / `assert_file_line_endings` / `assert_no_forbidden_subpath` / `assert_tree_is_closed_set`. The smoke loader consumes these — it does **not** reinvent ad-hoc assertions.
  - `tests/fixtures/README.md` — the fixture-inventory conventions doc: LF line endings + final newline (shape-test enforced), no build artifacts, hand-authored deterministic content, and the load-bearing rule "Adding a fixture file is one tuple-entry insertion … never edit the parametrized test bodies. This is Open/Closed at the file boundary."
  - `tests/unit/test_fixture_minimal_ts_shape.py` — the canonical kernel-consumer example to mirror for the new fixtures' `_FILE_SPECS`.
  - `tests/fixtures/portfolio/stale-scip/` + `tests/unit/test_fixture_stale_scip_shape.py` + `tests/adv/phase02/test_stale_scip_fixture.py` — the **pre-existing** `stale-scip` fixture this story reuses (do not duplicate).
  - `tests/fixtures/phase03/postinstall_canary/` + `tests/integration/transforms/test_bwrap_postinstall_canary.py` — the **pre-existing** `postinstall-canary` fixture this story reconciles against.
  - `src/codegenie/parsers/safe_json.py` — `load(path, *, max_bytes, max_depth=64)`; raises `DepthCapExceeded` (from `codegenie.errors`) past `max_depth`. This is the real depth-cap parser the `malformed-package-json/` test must drive (arch §C12 caps `package.json` at depth 16).

## Goal

Land the 10-fixture Phase-3 portfolio — eight new directories under `tests/fixtures/repos/` plus the two pre-existing fixtures (`stale-scip`, `postinstall-canary`) reused in place — each with an exact-pinned `package-lock.json`, a `README.md` explaining what edge case it triggers, a single typed `_portfolio.py` manifest, and a smoke loader `tests/fixtures/repos/test_fixtures_load.py` that asserts every fixture is well-formed (parseable `package.json`, parseable `package-lock.json` for the non-adversarial ones, expected file presence/absence). The portfolio is the substrate every Step 8 story (S8-02/03/04) and several Step 9 bench stories depend on. (validator: was "Land all 10 fixture repos under `tests/fixtures/repos/`" — corrected; two fixtures are reused at their existing paths, and the manifest is the new design centre.)

## Acceptance criteria

- [ ] **AC-1 — the portfolio is exactly ten fixtures.** The Phase-3 fixture portfolio is the set of ten directories below. Seven are **created new** under `tests/fixtures/repos/`; `express-cve-2024-21501/` is **created-or-extended** there; `stale-scip` and `postinstall-canary` already exist elsewhere and are **reused** (see the per-fixture disposition — do NOT author a duplicate). Each fixture's disposition and `expected_outcome` is recorded in the `_portfolio.py` manifest (AC-7), which is the machine-checked source of truth; the prose below is descriptive.
  - [ ] `express-cve-2024-21501/` — **create-or-extend** at `tests/fixtures/repos/express-cve-2024-21501/`. The S6 stub this story originally claimed to extend does not exist on disk (S6-04 unexecuted) — outline §1 confirms its presence and creates it from scratch if absent. Contents: `package.json`, exact-pinned `package-lock.json` (`lockfileVersion: 3`), `README.md`, `.gitignore`, a minimal `test/index.test.js` so `npm test` can run. CVE: `CVE-2024-21501` (express). Expected outcome: `RemediationOutcome.Validated(passed=True)`.
  - [ ] `monorepo-workspaces/` — NEW. `package.json` with `"workspaces": ["packages/*"]`; two workspaces (`packages/a/`, `packages/b/`); vulnerability in ONLY `packages/a`'s direct deps; root `package-lock.json` resolves both. Expected outcome: `Applied` only against the workspace owning the vuln; root lockfile re-resolves. (E3)
  - [ ] `transitive-only-cve/` — NEW. Direct dep `safe-pkg@1.0.0` whose transitive `vuln-pkg@<2.0.0` carries the CVE. Expected: `NpmTransitiveOverridesRecipe` adds an `overrides` block; `OverridesUsed` event. (E5)
  - [ ] `peer-dep-conflict/` — NEW. Direct dep `pkg-a@1.0.0` that declares `peerDependency: pkg-b@^1.0.0` while bump would require `pkg-b@^2.0.0`. Expected outcome: `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)`. (E4)
  - [ ] `major-bump-required/` — NEW. CVE on `vulnerable-pkg@^1.0.0` whose only patched version is `2.0.0`. Expected outcome: `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)`. (E6)
  - [ ] `breaking-test-suite/` — NEW. Pinned lockfile installs cleanly; a `test/index.test.js` deliberately calls `assert(false, "intentionally failing")`. Expected outcome: `RemediationOutcome.Validated(passed=False, failing=["tests"])`.
  - [ ] `stale-scip` — **REUSE the pre-existing `tests/fixtures/portfolio/stale-scip/`** (Phase 2 / S7-02 — already shape-tested, with ~20 probe goldens and an adversarial test). The `_portfolio.py` manifest records this entry at its real path. Do **not** create a second `stale-scip/` and do **not** commit a `.codegenie/scip/index.scip` (the shared kernel's `_FORBIDDEN_SUBPATHS` bans `.codegenie/`; the existing fixture already solves staleness via a `_seed/` blob + `regenerate.sh`). If — and only if — a Phase-3-specific adapter-degraded scenario genuinely cannot be expressed by the existing fixture, author it under a **distinct name** and justify it in the README; never a second `stale-scip`. (E18)
  - [ ] `malformed-package-json/` — NEW. `package.json` with a nested object **> 16 containers deep** (depth, not brace count). Verified by AC-4 driving the project's depth-capped parser. Expected: parse rejection (`DepthCapExceeded`) → `RecipeOutcome.Failed(reason=invalid_repo_content)`. (E20)
  - [ ] `malicious-npmrc/` — NEW. Parseable `package.json` + `package-lock.json`, plus an `.npmrc` with `registry=https://attacker.example.com/`. Expected: `JailedSubprocessResult.NetworkDenied(host="attacker.example.com")`. (E7)
  - [ ] `postinstall-canary` — **RECONCILE with the pre-existing `tests/fixtures/phase03/postinstall_canary/`** (Phase 3 / S4-02, consumed by `test_bwrap_postinstall_canary.py`). The portfolio entry reuses it; if the portfolio genuinely needs it under `tests/fixtures/repos/` (S8-03/S8-04 currently assume that path — see Notes), surfacing that cross-story path conflict is part of this AC. Do not leave two `postinstall-canary` fixtures. (E8)
- [ ] **AC-2 — lockfile pinning is byte-exact and machine-enforced.** Every non-adversarial fixture's `package-lock.json` has `lockfileVersion: 3`, and the pinning fence `tests/fixtures/repos/test_fixtures_pinning.py` asserts, for every entry under `packages`: **(a)** `version` matches an exact semver `^\d+\.\d+\.\d+([-+].+)?$` — **no** `^`, `~`, `*`, `>`, `<`, `||`, or `x`-range; **(b)** `integrity` matches `^sha512-[A-Za-z0-9+/]+={0,2}$` (a placeholder like `sha512-TODO` MUST fail); **(c)** `resolved` starts with `https://registry.npmjs.org/` — no git/tarball/`file:` URL. The fence inspects the *parsed JSON version-bearing fields* (not a raw-text grep), so it cannot false-pass or false-fail on incidental characters. (validator: hardened — original AC checked only `^`/`~` via grep and never verified `integrity`/`resolved` shape, so a `sha512-TODO` placeholder slipped through.)
- [ ] **AC-3 — every fixture `README.md` has exactly four sections, in order.** The four `##`-level headings, and no others, are exactly: `## What this fixture is`, `## Edge case(s) covered`, `## Expected outcome`, `## Maintenance`. The smoke loader extracts the ordered list of `^## ` headings and asserts it equals the four expected titles **in that order** — a fifth rogue section, a missing section, or a reordering fails. (validator: hardened — original AC/test checked only substring presence, so a 5-section or reordered README passed.)
- [ ] **AC-4 — the smoke loader is exhaustive and consumes the shared kernel.** `tests/fixtures/repos/test_fixtures_load.py`, parametrized over the `_portfolio.py` manifest (AC-7), asserts for every fixture: directory exists; `package.json` exists; `README.md` exists with the four ordered sections (AC-3); and — driven by each fixture's `is_adversarial` flag — `package-lock.json` **parses** via `safe_json.load` for every fixture **except** `malformed-package-json/`, for which `safe_json.load(..., max_depth=16)` is asserted to raise `DepthCapExceeded`. For `malicious-npmrc/` the loader additionally asserts an `.npmrc` file is present. The structural checks (file presence, parseability, LF line endings, no forbidden subpaths, closed-set tree) delegate to `tests/fixtures/_shape_test_kernel.py` helpers — the loader does not reinvent them. (validator: hardened — original TDD plan had no `package-lock.json`-parse test and no `.npmrc`-presence test despite the AC requiring both; the "8 non-adversarial" count was ambiguous and is now derived from the manifest's `is_adversarial` flag.)
- [ ] **AC-5 — ≥5 fixtures carry a real CVE.** ≥5 of the ten fixtures declare a real `CVE-YYYY-NNNNN` identifier (roadmap exit-criterion "Library of fixture repos with known vulnerable lockfiles"). Each such id is stored in the manifest as a `CveId` newtype constructed via the `parse_cve_id` smart constructor (AC-7) — a malformed id fails at manifest import. The five CVE-carrying fixtures: `express-cve-2024-21501`, `monorepo-workspaces`, `transitive-only-cve`, `major-bump-required`, `breaking-test-suite`. Each fixture's `README.md` "Expected outcome" section also names the id in prose.
- [ ] **AC-6 — per-fixture size cap.** No fixture directory exceeds 256 KiB on disk; `tests/fixtures/repos/test_fixtures_size_cap.py`, parametrized over the manifest, enforces it. Large transitive deps are NOT vendored — the lockfile pins identity; `npm install --prefer-offline` resolves via the pre-warmed cache S8-03 ships.
- [ ] **AC-7 — single-source typed manifest (Open/Closed at the file boundary).** The ten-fixture portfolio is declared exactly once, in `tests/fixtures/repos/_portfolio.py`, as a module-level `Final` tuple of frozen typed records — `FixtureSpec(name: str, path: Path, is_adversarial: bool, cve_ids: tuple[CveId, ...], edge_cases: tuple[str, ...], expected_outcome: str)`. `cve_ids` uses the `CveId` newtype (CLAUDE.md "Newtype identifiers … never raw `str` for domain IDs"); `is_adversarial` is the single source for the parse-expectation split (no `[n for n in … if n != "malformed…"]` comprehensions anywhere — illegal states unrepresentable). `test_fixtures_load.py`, `test_fixtures_pinning.py`, and `test_fixtures_size_cap.py` all import this tuple — **no test file re-declares the fixture names or CVE ids**. (validator: added — the list was re-declared across 3 fence files in this story alone, plus S8-03's `_REPO_FIXTURES`/`_CVE_IDS` and S8-04; rule-of-three conclusively past.)
- [ ] **AC-8 — adding a fixture is one manifest row + one directory, zero fence-logic edits.** Adding an eleventh fixture requires exactly: one new `FixtureSpec` row in `_portfolio.py` and one new fixture directory. It requires **zero** edits to the bodies of `test_fixtures_load.py`, `test_fixtures_pinning.py`, or `test_fixtures_size_cap.py`. A test in `test_fixtures_load.py` (or a comment-anchored assertion) demonstrates this Open/Closed property is real. (validator: added — observable extension-by-addition AC; pattern: registry / Open/Closed, mirroring `tests/fixtures/README.md`'s documented `_FILE_SPECS` convention.)
- [ ] **AC-9 — no duplicate-named fixtures.** No two fixture directories anywhere under `tests/fixtures/` share a directory name. A check (in `test_fixtures_load.py`) asserts the manifest's reused entries (`stale-scip`, `postinstall-canary`) resolve to exactly one on-disk path each. (validator: added — guards against the `stale-scip` / `postinstall-canary` duplication this validation surfaced.)
- [ ] **AC-10 — `make check` clean** on every touched file (`ruff check`, `ruff format --check`, and `mypy --strict` on the new `_portfolio.py` and fence-test modules — the manifest and tests are typed, no `Any`, no untyped functions).
- [ ] **AC-11 — TDD plan's red tests exist, were committed failing, and are green** after the fixtures land.

## Implementation outline

1. **Reconcile with on-disk reality first.** Confirm whether `tests/fixtures/repos/express-cve-2024-21501/` exists (it does not as of validation); confirm `tests/fixtures/portfolio/stale-scip/` and `tests/fixtures/phase03/postinstall_canary/` exist (they do). Read `tests/fixtures/_shape_test_kernel.py` and `tests/fixtures/README.md` so the new fixtures match the established conventions (LF endings + final newline, no build artifacts, hand-authored deterministic content).
2. **Write the manifest `tests/fixtures/repos/_portfolio.py` first** — the `Final` tuple of `FixtureSpec` records (AC-7). Every later step and every fence test derives from it. Construct `cve_ids` via `parse_cve_id`. Record `stale-scip` and `postinstall-canary` at their real (reused) paths; the other eight under `tests/fixtures/repos/`.
3. **Create the seven genuinely-new fixtures** under `tests/fixtures/repos/`: `monorepo-workspaces`, `transitive-only-cve`, `peer-dep-conflict`, `major-bump-required`, `breaking-test-suite` (non-adversarial — exercise `RecipeOutcome` variants, feed S8-02's goldens), then `malformed-package-json`, `malicious-npmrc` (adversarial — feed S8-04's regressions). Each adversarial fixture's `README.md` carries an inline note that it is intentionally malformed/malicious, so security scanners and reviewers don't flag it.
4. **Create-or-extend `express-cve-2024-21501/`** at `tests/fixtures/repos/`: fully-pinned `package-lock.json` (every entry has exact `version`, well-formed `integrity` sha512, `registry.npmjs.org` `resolved`), `test/index.test.js`, `.gitignore`, four-section `README.md`. If S6-04 has by then landed a stub, extend it; otherwise author it from scratch.
5. **Reuse `stale-scip` and `postinstall-canary`** — do not author duplicates (AC-1, AC-9). The manifest references them where they live. If S8-03/S8-04's hardcoded `tests/fixtures/repos/` path for these two cannot be satisfied by reuse, surface the cross-story conflict in the attempt log rather than silently relocating Phase-2 fixtures (relocation is out of scope — see Out of scope).
6. **Write the smoke loader `tests/fixtures/repos/test_fixtures_load.py`** parametrized over the manifest, delegating structural checks to `_shape_test_kernel.py` helpers (`assert_file_exists`, `assert_file_parses`, `assert_file_line_endings`, `assert_no_forbidden_subpath`, `assert_tree_is_closed_set`). Adversarial-vs-benign parse expectations are driven by `FixtureSpec.is_adversarial`.
7. **Write the lockfile-pinning fence `tests/fixtures/repos/test_fixtures_pinning.py`** — parses each `package-lock.json` and inspects the version-bearing fields per AC-2 (exact-semver `version`, `sha512-` `integrity` shape, `registry.npmjs.org` `resolved`).
8. **Write the size-cap fence `tests/fixtures/repos/test_fixtures_size_cap.py`** — parametrized over the manifest; fails if any fixture directory exceeds 256 KiB.
9. Cross-link each `README.md` "Edge case(s) covered" section to the `phase-arch-design.md §Edge cases` row(s) it satisfies (E#).

## TDD plan — red / green / refactor

Each test below names the AC it verifies and is written to **fail against a wrong implementation**, not merely to pass against a right one (Rule 9).

### Red — write the failing tests first

Test file path: `tests/fixtures/repos/test_fixtures_load.py` (co-located with the fixtures + the `_portfolio.py` manifest).

```python
from __future__ import annotations

import re

import pytest

from codegenie.errors import DepthCapExceeded
from codegenie.parsers import safe_json
from tests.fixtures._shape_test_kernel import (
    _FORBIDDEN_SUBPATHS,
    assert_no_forbidden_subpath,
)
from tests.fixtures.repos._portfolio import PORTFOLIO, FixtureSpec  # the AC-7 manifest

_PKG_JSON_DEPTH_CAP = 16  # arch §C12 — package.json parse cap
_README_SECTIONS = (
    "## What this fixture is",
    "## Edge case(s) covered",
    "## Expected outcome",
    "## Maintenance",
)


@pytest.mark.parametrize("spec", PORTFOLIO, ids=lambda s: s.name)
def test_fixture_directory_and_core_files_exist(spec: FixtureSpec) -> None:
    """AC-1/AC-4 — every portfolio fixture is on disk with package.json + README.md."""
    assert spec.path.is_dir(), f"missing fixture dir: {spec.path}"
    assert (spec.path / "package.json").is_file(), f"{spec.name}: no package.json"
    assert (spec.path / "README.md").is_file(), f"{spec.name}: no README.md"


@pytest.mark.parametrize(
    "spec", [s for s in PORTFOLIO if not s.is_adversarial], ids=lambda s: s.name
)
def test_non_adversarial_lockfile_parses_and_is_v3(spec: FixtureSpec) -> None:
    """AC-4 — every non-adversarial fixture has a parseable lockfileVersion-3 lockfile.

    Drives the real depth-capped parser, not json.loads — a fixture that smuggles
    a 33-MiB or depth-25 lockfile must fail here, exactly as production would.
    """
    lock = safe_json.load(spec.path / "package-lock.json", max_bytes=32 * 1024 * 1024)
    assert lock["lockfileVersion"] == 3, f"{spec.name}: lockfile must be v3"


def test_malformed_fixture_blows_the_depth_cap() -> None:
    """AC-4 — malformed-package-json must hit the depth-16 cap, not merely have many braces.

    Mutation guard: a brace-count proxy passes for 20 *sibling* objects at depth 2;
    only an actual depth-capped parse distinguishes deep nesting from wide nesting.
    """
    spec = next(s for s in PORTFOLIO if s.name == "malformed-package-json")
    with pytest.raises(DepthCapExceeded):
        safe_json.load(
            spec.path / "package.json",
            max_bytes=1 * 1024 * 1024,
            max_depth=_PKG_JSON_DEPTH_CAP,
        )


def test_malicious_npmrc_fixture_ships_the_npmrc() -> None:
    """AC-1/AC-4 — the E7 fixture is only adversarial if the hostile .npmrc is present."""
    spec = next(s for s in PORTFOLIO if s.name == "malicious-npmrc")
    npmrc = (spec.path / ".npmrc").read_text()
    assert "attacker.example.com" in npmrc, "malicious-npmrc must redirect the registry"


@pytest.mark.parametrize("spec", PORTFOLIO, ids=lambda s: s.name)
def test_readme_has_exactly_four_sections_in_order(spec: FixtureSpec) -> None:
    """AC-3 — exactly the four sections, in order; a 5th/missing/reordered section fails."""
    headings = re.findall(
        r"^## .*$", (spec.path / "README.md").read_text(), flags=re.MULTILINE
    )
    normalized = tuple(h.split("(")[0].rstrip() for h in headings)
    assert normalized == _README_SECTIONS, f"{spec.name}: section set/order wrong: {headings}"


@pytest.mark.parametrize("spec", PORTFOLIO, ids=lambda s: s.name)
def test_no_forbidden_subpaths(spec: FixtureSpec) -> None:
    """AC-4 — no node_modules/.codegenie/dist/coverage/build leaked into a fixture tree."""
    for forbidden in _FORBIDDEN_SUBPATHS:
        assert_no_forbidden_subpath(spec.path, forbidden)


def test_at_least_five_fixtures_carry_a_cve() -> None:
    """AC-5 — roadmap exit-criterion: ≥5 fixtures with a real CVE id."""
    with_cve = [s for s in PORTFOLIO if s.cve_ids]
    assert len(with_cve) >= 5, f"only {len(with_cve)} CVE fixtures: {[s.name for s in with_cve]}"


def test_no_duplicate_fixture_names() -> None:
    """AC-9 — guards against a second stale-scip / postinstall-canary."""
    names = [s.name for s in PORTFOLIO]
    assert len(names) == len(set(names)) == 10, f"duplicate or wrong-count names: {names}"
```

State why it fails (red): `tests/fixtures/repos/_portfolio.py` does not exist (import error), and eight of the ten fixture directories are not on disk. Every parametrized case errors at import / `spec.path` resolution.

A sibling `test_fixtures_pinning.py` red test asserts (against a temporarily-planted `^4.17.0` `version`, a `sha512-TODO` `integrity`, and a `file:` `resolved`) that each is rejected — the fence must catch all three, proving AC-2's positive field-shape checks bite. A `test_fixtures_size_cap.py` red test asserts a planted 300-KiB fixture fails AC-6.

### Green — minimal pass

- Write `tests/fixtures/repos/_portfolio.py` (the typed `FixtureSpec` manifest — AC-7).
- Create the seven new fixture directories + create-or-extend `express-cve-2024-21501/`, each with a real pinned `package.json`/`package-lock.json`, a four-section `README.md`, and the per-fixture extras (workspaces, peer-dep, `.npmrc`, postinstall script, deep-nested malformed JSON, etc.).
- Reuse `stale-scip` and `postinstall-canary` in place; record them in the manifest at their real paths.
- Run the loader until every parametrized case passes.

### Refactor

- Land the pinning fence `tests/fixtures/repos/test_fixtures_pinning.py` (structural field-shape inspection per AC-2) and the size-cap fence `tests/fixtures/repos/test_fixtures_size_cap.py` — both parametrized over the manifest.
- Confirm `make check` clean — `ruff` + `mypy --strict` on `_portfolio.py` and the three fence-test modules.
- Cross-link each `README.md` "Edge case(s) covered" section to its `phase-arch-design.md §Edge cases` row.
- Edge cases from §Edge cases this portfolio is the substrate for: E3, E4, E5, E6, E7, E8, E18, E20. **E11 (`cve_delta` — lockfile re-resolve introduces a NEW CVE) is NOT covered by this story** — no fixture here provides that substrate; per `High-level-impl.md §Step 8` it is `tests/adversarial/test_cve_delta_introduced.py`, an S8-04 deliverable that ships its own fixture. (validator: corrected — the original Refactor list and the `ADRs honored` line claimed E11; this story has no E11 fixture.)

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/_portfolio.py` | NEW — the typed `FixtureSpec` manifest; single source of truth for all 10 (AC-7). |
| `tests/fixtures/repos/express-cve-2024-21501/` (create-or-extend) | Pin lockfile; add `test/index.test.js`; four-section `README.md`. May not exist yet — see AC-1. |
| `tests/fixtures/repos/monorepo-workspaces/` | NEW — workspaces fixture (E3). |
| `tests/fixtures/repos/transitive-only-cve/` | NEW — `overrides`-recipe fixture (E5). |
| `tests/fixtures/repos/peer-dep-conflict/` | NEW — `NotApplicable(PEER_DEP_CONFLICT)` fixture (E4). |
| `tests/fixtures/repos/major-bump-required/` | NEW — `NotApplicable(MAJOR_BUMP_REFUSE)` fixture (E6). |
| `tests/fixtures/repos/breaking-test-suite/` | NEW — `Validated(passed=False)` fixture. |
| `tests/fixtures/repos/malformed-package-json/` | NEW — depth-cap rejection fixture (E20). |
| `tests/fixtures/repos/malicious-npmrc/` | NEW — `NetworkDenied` fixture (E7). |
| `tests/fixtures/portfolio/stale-scip/` (REUSE — no edit) | Pre-existing Phase-2 fixture; referenced by the manifest, not duplicated (E18). |
| `tests/fixtures/phase03/postinstall_canary/` (REUSE — no edit) | Pre-existing Phase-3 fixture; referenced by the manifest, not duplicated (E8). |
| `tests/fixtures/repos/test_fixtures_load.py` | NEW — smoke loader; parametrized over the manifest; consumes `_shape_test_kernel.py`. |
| `tests/fixtures/repos/test_fixtures_pinning.py` | NEW — structural lockfile field-shape fence (AC-2). |
| `tests/fixtures/repos/test_fixtures_size_cap.py` | NEW — 256 KiB per-fixture cap (AC-6). |

(validator: dropped the `tests/conftest.py` row — the session-scoped postinstall-canary cleanup belongs to S8-04, which actually runs the adversarial postinstall test; this story's smoke loader never invokes `npm install`. Dropped the `repos/stale-scip/` and `repos/postinstall-canary/` NEW rows — those fixtures already exist; see the REUSE rows.)

## Out of scope

- **Pre-warmed npm cache** (the `.npm-cache/` tarball that lets `--prefer-offline` install deterministically) — that's S8-03's responsibility because only the determinism property test depends on its content being byte-pinned.
- **Golden lockfile diffs** (`tests/golden/lockfiles/express-cve-2024-21501.{before,after}.json`) — S8-02 ships these from this fixture's lockfile.
- **The actual adversarial tests** asserting `NetworkDenied`, postinstall canary unwritten, depth-cap rejection — S8-04 wires these up to read these fixtures.
- **Yarn Berry routed-to-universal fixture** — `tests/integration/test_yarn_berry_routed_to_universal.py` is a Step 8 test (separate from the 10 fixtures above); the Yarn Berry fixture itself can live alongside but is not in this story's "≥10 fixture repos" target. If the implementer wants to add an 11th fixture (`yarn-berry/`), it's welcome but not required here; S8-04 will create it if absent.
- **VulnIndex seeding** with the CVE records the fixtures reference — that's S3-02/S3-03's job; this story consumes the existing sqlite store.
- **The E11 `cve_delta` fixture** (a lockfile whose re-resolve introduces a NEW transitive CVE) — none of the ten fixtures here provides that substrate. Per `High-level-impl.md §Step 8`, E11 is verified by `tests/adversarial/test_cve_delta_introduced.py`, an S8-04 deliverable that ships its own fixture. (validator: added — the original story claimed E11 coverage without a fixture.)
- **The session-scoped postinstall-canary cleanup fixture in `tests/conftest.py`** — belongs to S8-04 (the story that runs the adversarial postinstall test). This story's smoke loader only checks files exist; it never runs `npm install`, so it needs no canary cleanup. (validator: added — was incorrectly assigned here.)
- **Relocating the pre-existing `tests/fixtures/portfolio/stale-scip/` or `tests/fixtures/phase03/postinstall_canary/`** into `tests/fixtures/repos/` — out of scope. Each is wired into shape tests, ~20 probe goldens, and adversarial tests; moving them is a cross-cutting change far beyond a fixture-portfolio story. If S8-03/S8-04's hardcoded `tests/fixtures/repos/` path for these two proves load-bearing, that path reconciliation is a separate follow-up; this story surfaces the conflict (AC-1, attempt log) rather than silently performing the move. (validator: added.)

## Notes for the implementer

- **Consume the shared shape-test kernel — do not reinvent it.** `tests/fixtures/_shape_test_kernel.py` already exists with 8 consumers, and `tests/fixtures/README.md` documents it as THE pattern: "Adding a fixture file is one tuple-entry insertion … never edit the parametrized test bodies. This is Open/Closed at the file boundary." The smoke loader's structural checks (file presence, parseability, LF endings, forbidden subpaths, closed-set tree) delegate to its flat helpers. `tests/unit/test_fixture_minimal_ts_shape.py` is the canonical consumer to mirror. Authoring a parallel ad-hoc assertion mechanism is a Rule-11 violation.
- **The `_portfolio.py` manifest is the design centre of this story.** One `Final` tuple of `FixtureSpec` records. Every fence test and every downstream consumer (S8-03's `_REPO_FIXTURES`/`_CVE_IDS`, S8-04) should import it instead of re-declaring the list. `cve_ids` is `tuple[CveId, ...]` built via `parse_cve_id` — newtype discipline, not raw `str` (CLAUDE.md). `is_adversarial: bool` is the *only* place the adversarial/benign split lives — no `[n for n in … if n != "malformed…"]` comprehensions; the split is data, not control flow (make illegal states unrepresentable). This is what makes "add an 11th fixture" a one-row change (AC-8).
- **Two of the ten fixtures already exist — reuse, do not duplicate.** `stale-scip` is `tests/fixtures/portfolio/stale-scip/` (Phase 2 / S7-02, already shape-tested with ~20 probe goldens + `tests/adv/phase02/test_stale_scip_fixture.py`). `postinstall-canary` is `tests/fixtures/phase03/postinstall_canary/` (Phase 3 / S4-02, consumed by `test_bwrap_postinstall_canary.py`). The manifest references both at their real paths. Authoring a second `stale-scip/` or `postinstall-canary/` under `repos/` is a defect (AC-9). Note the existing `stale-scip` solves time-relative staleness via a `_seed/` blob + `regenerate.sh` — you do **not** commit a stale mtime, and you do **not** commit a `.codegenie/` directory (the kernel's `_FORBIDDEN_SUBPATHS` bans it).
- **Cross-story path conflict to surface.** S8-03 and S8-04 currently hardcode `tests/fixtures/repos/` for *all* fixtures, including `postinstall-canary`. Reusing the fixture at `tests/fixtures/phase03/postinstall_canary/` means those stories' paths won't resolve. Do not silently relocate the Phase-2/3 fixtures (out of scope — breaks their shape tests + goldens). Surface this in the attempt log so S8-03/S8-04 can be reconciled — either they read the manifest's `path` field, or a separate follow-up unifies the directory.
- **Lockfile pinning is the load-bearing discipline.** A `^4.17.21` resolved-version in any non-adversarial fixture WILL eventually flake S8-03's determinism property test. The pinning fence inspects parsed JSON fields (AC-2), not raw text — so it cannot false-pass on a `^` buried in a base64 `integrity` string nor false-fail on incidental characters. A `sha512-TODO` placeholder must fail the fence.
- **Don't run `npm install` against the live registry when authoring a fixture.** Generate lockfiles in an isolated bwrap-jail-equivalent or copy the structure from an existing pinned-lockfile-aware Phase 1/2 fixture. The point of the portfolio is that it does NOT depend on network state.
- **Realistic — but minimal — `package.json`.** Each fixture's `package.json` should name a real package as the direct vulnerable dep (e.g., `express@4.17.0`), not invent one. The CVE-IDs in the READMEs must be real (`CVE-YYYY-NNNNN` format; `parse_cve_id` accepts).
- **`README.md`, not `README.fixture.md`.** Every existing fixture and the shared kernel's `assert_readme_references_every_spec` use `README.md`; zero `README.fixture.md` files exist. The four-section format (`## What this fixture is`, `## Edge case(s) covered`, `## Expected outcome`, `## Maintenance`) lives inside `README.md`. Do not rename any Phase 1/2 fixture READMEs — that is not this story's scope (Rule 3).
- **`malformed-package-json` must nest *deep*, not *wide*.** The fixture's `package.json` needs > 16 levels of *container nesting* — `{"a":{"b":{"c": … }}}` — so `safe_json.load(..., max_depth=16)` raises `DepthCapExceeded`. A file with 20 sibling objects at depth 2 has 20+ braces but depth 2 and would NOT trip the cap. AC-4's test drives the real parser precisely so this confusion is caught.
- **`malicious-npmrc` is adversarial; mark it.** Inline note in its `README.md`: "This fixture is intentionally hostile and exists solely to verify Phase 3 sandbox containment. Do NOT run `npm install` against it outside the bwrap/sandbox-exec jail."
- **`monorepo-workspaces` lockfile is the trickiest.** npm v7+ resolves workspaces into the root lockfile under `packages/<workspace>` entries. Use `lockfileVersion: 3`; the workspace package shows up as `"packages/a": { "version": "1.0.0", ... }` in the root lockfile.
- **The fixture portfolio is a contract for downstream stories.** Once S8-02 and S8-03 land golden files derived from these fixtures, changing a `package-lock.json` byte means regenerating the goldens. Future PRs touching `tests/fixtures/repos/` should expect to touch `tests/golden/lockfiles/` and `tests/golden/event-streams/` in the same PR.
