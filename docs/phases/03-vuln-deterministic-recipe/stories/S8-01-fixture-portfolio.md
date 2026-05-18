# Story S8-01 — Fixture portfolio (≥10 repos incl. ≥5 CVE fixtures)

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** Ready
**Effort:** L
**Depends on:** S6-06
**ADRs honored:** ADR-0008 (deterministic Bundle requires every fixture's `package-lock.json` to be pinned bytes-for-bytes — registry drift would flip the property test green/red across days), ADR-0001 (`remediation-report.yaml` schema-snapshot tests in Step 6 are only meaningful if Step 8's fixtures exercise every variant of `RemediationOutcome` — `Validated(passed=True)`, `Validated(passed=False)`, `NotApplicable`, `RequiresHumanReview`), ADR-0010 (each fixture's `package.json` `name` field must round-trip through `parse_package_id` — adversarial fixtures `malformed-package-json/` and `malicious-npmrc/` deliberately violate this to verify smart-constructor rejection)

## Context

Phase 3's headline exit criterion ("Given a Node.js repo with a known npm CVE, the system writes a working patch diff…") and Goal G4 (determinism) both depend on a fixture portfolio that does three things at once: (1) exercises every `RecipeOutcome` variant the four npm recipes can emit; (2) covers every adversarial edge case from `phase-arch-design.md §Edge cases E1–E20`; (3) pins each fixture's `package-lock.json` to exact bytes so the determinism property test (S8-03) and the golden-file diff (S8-02) don't flake when the live npm registry mutates. Step 6 already created an `express-cve-2024-21501/` stub as part of the end-to-end happy-path scaffold — this story *extends* that one and lands the other nine.

Implementation-risk #2 in `High-level-impl.md` calls this out explicitly: "real `npm install` resolutions change when the registry changes. Mitigation: pin every fixture's `package-lock.json` to exact versions; assert no implicit-version `^`/`~` resolution in golden comparisons." A fixture whose lockfile resolves a `^4.17.0` semver range against the live registry is a time bomb — within a year, `4.17.21` becomes `4.17.22` and every downstream test starts producing different `transform.diff_bytes`. The fixture must be self-contained: every entry in `package-lock.json` has an exact `version`, an exact `integrity` sha512, and an exact `resolved` URL.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Fixture portfolio` — names all 10 fixtures with their failure modes; matches this story 1:1.
  - `../phase-arch-design.md §Edge cases E1–E20` — every fixture in this story exists to make one or more of these edge cases reproducible; E2 (Yarn-Berry → universal), E3 (workspaces), E5 (transitive-only), E4 (peer-dep conflict), E6 (major-bump-refuse), E7 (malicious .npmrc → NetworkDenied), E8 (postinstall canary), E11 (cve_delta), E18 (degraded adapter / stale SCIP), E20 (adversarial package.json content).
  - `../phase-arch-design.md §Component design C12` — the `NpmLockfileRecipeEngine` reads `package.json` (1 MiB / depth-16 caps) and `package-lock.json` (32 MiB / depth-24 caps); `malformed-package-json/` is the fixture that hits the depth cap.
  - `../phase-arch-design.md §Goals G4` — the cardinal determinism goal that S8-03 verifies *over these fixtures*; if fixtures aren't byte-pinned, G4 is unverifiable.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — explains why a `^`-ranged lockfile is incompatible with the determinism property; the fixture portfolio is the only way to honor this at scale.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — the contract-snapshot tests passed in S6-06 only verify *schema shape*; this story's fixtures are what give the next story (S8-02) the inputs to verify schema *contents*.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `malformed-package-json/` and `malicious-npmrc/` are designed to fail `parse_package_id` / `parse_registry_url` smart constructors, asserting the discipline holds.
- **Existing code / fixtures:**
  - `tests/fixtures/repos/express-cve-2024-21501/` (S6 stub) — the precedent for `package.json`, `package-lock.json`, `README.fixture.md` layout to mirror across the new nine.
  - `tests/fixtures/repos/` parent directory layout — pre-existing Phase 1/2 fixtures (Node monorepo, etc.) demonstrate the README-per-fixture convention; do not co-locate fixtures from different phases.
  - `tests/integration/test_end_to_end_express_cve.py` (S8-02 — sibling story; reads several of these fixtures).
- **High-level impl:**
  - `../High-level-impl.md §Step 8` — enumerates the 10 fixtures and the "≥5 CVE fixtures" roadmap exit-criterion target.

## Goal

Land all 10 fixture repos under `tests/fixtures/repos/`, each with an exact-pinned `package-lock.json`, a `README.fixture.md` explaining what edge case it triggers, and a smoke loader `tests/fixtures/test_fixtures_load.py` that asserts every fixture is well-formed (parseable `package.json`, parseable `package-lock.json` for the non-adversarial ones, expected file presence/absence). The portfolio is the substrate every Step 8 story (S8-02/03/04) and several Step 9 bench stories depend on.

## Acceptance criteria

- [ ] `tests/fixtures/repos/` contains **all ten** of the following directories, each with the files enumerated below:
  - [ ] `express-cve-2024-21501/` — extended from S6 stub; contains `package.json`, exact-pinned `package-lock.json` (lockfileVersion 3), `README.fixture.md`, `.gitignore`, a minimal `test/index.test.js` so `npm test` can run. CVE: `CVE-2024-21501` (express). Expected outcome: `RemediationOutcome.Validated(passed=True)`.
  - [ ] `monorepo-workspaces/` — `package.json` with `"workspaces": ["packages/*"]`; two workspaces (`packages/a/`, `packages/b/`); vulnerability in ONLY `packages/a`'s direct deps; root `package-lock.json` resolves both. Expected outcome: `Applied` only against the workspace owning the vuln; root lockfile re-resolves.
  - [ ] `transitive-only-cve/` — direct dep `safe-pkg@1.0.0` whose transitive `vuln-pkg@<2.0.0` carries the CVE. Expected: `NpmTransitiveOverridesRecipe` adds an `overrides` block; `OverridesUsed` event.
  - [ ] `peer-dep-conflict/` — direct dep `pkg-a@1.0.0` that declares `peerDependency: pkg-b@^1.0.0` while bump would require `pkg-b@^2.0.0`. Expected outcome: `RecipeOutcome.NotApplicable(reason=PEER_DEP_CONFLICT)`.
  - [ ] `major-bump-required/` — CVE on `vulnerable-pkg@^1.0.0` whose only patched version is `2.0.0`. Expected outcome: `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)`.
  - [ ] `breaking-test-suite/` — pinned lockfile installs cleanly; a `test/index.test.js` deliberately calls `assert(false, "intentionally failing")`. Expected outcome: `RemediationOutcome.Validated(passed=False, failing=["tests"])`.
  - [ ] `stale-scip/` — Phase 2 SCIP index file (`.codegenie/scip/index.scip`) with `mtime` artificially set > 14 days ago; otherwise valid. Expected: `AdapterDegraded` event → `TrustOutcome.confidence == "degraded"`.
  - [ ] `malformed-package-json/` — `package.json` with depth-22 nested object (deliberately above the 16-depth parse cap). Expected: `RecipeOutcome.Failed(reason=invalid_repo_content)` at parse.
  - [ ] `malicious-npmrc/` — `.npmrc` with `registry=https://attacker.example.com/`. Expected: `JailedSubprocessResult.NetworkDenied(host="attacker.example.com")`.
  - [ ] `postinstall-canary/` — `package.json` includes a dep whose `postinstall` script writes `/tmp/codegenie-canary-{fixture}.txt`. Expected: canary file does NOT exist after the workflow (proves `--ignore-scripts` enforcement).
- [ ] **Every** non-adversarial fixture's `package-lock.json` has `lockfileVersion: 3` and every entry under `packages` carries (a) an exact `version` (no `^`, `~`, `*`, or range), (b) an `integrity` sha512, and (c) a `resolved` URL pointing at `https://registry.npmjs.org/`. A grep-based fence in `tests/fixtures/test_fixtures_pinning.py` asserts this — any `^` or `~` in any lockfile-version field fails CI.
- [ ] Each fixture has a `README.fixture.md` containing exactly four sections: `## What this fixture is`, `## Edge case(s) covered (E#)`, `## Expected outcome`, `## Maintenance — when to regenerate the lockfile`.
- [ ] `tests/fixtures/test_fixtures_load.py` smoke-loads each of the 10 fixtures: asserts directory exists, asserts `package.json` exists (for all 10), asserts `package-lock.json` parses (for 8 non-adversarial; `malformed-package-json/` is asserted to **fail** parsing; `malicious-npmrc/` is asserted parseable but `.npmrc` present), asserts `README.fixture.md` has all four sections.
- [ ] ≥5 of the 10 fixtures carry a real CVE identifier in their `README.fixture.md` (roadmap exit-criterion: "Library of fixture repos with known vulnerable lockfiles"). The five CVE-carrying fixtures are: `express-cve-2024-21501`, `monorepo-workspaces` (CVE in one workspace), `transitive-only-cve`, `major-bump-required`, `breaking-test-suite`.
- [ ] No fixture exceeds 256 KiB on disk (`tests/fixtures/test_fixtures_size_cap.py`); large transitive deps are NOT vendored — the lockfile pins identity, `npm install --prefer-offline` resolves via the pre-warmed cache S8-03 ships.
- [ ] `make check` clean on touched files (`ruff check`, `ruff format --check`).
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Extend `tests/fixtures/repos/express-cve-2024-21501/` from the S6 stub: ensure `package-lock.json` is fully pinned (every entry has `version`, `integrity`, `resolved`), add `test/index.test.js`, add the four-section `README.fixture.md`.
2. Create the other nine directories in order of dependency-on-each-other:
   - First the non-adversarial ones (`monorepo-workspaces`, `transitive-only-cve`, `peer-dep-conflict`, `major-bump-required`, `breaking-test-suite`, `stale-scip`) — these exercise `RecipeOutcome` variants and feed S8-02's golden tests.
   - Then the adversarial three (`malformed-package-json`, `malicious-npmrc`, `postinstall-canary`) — these feed S8-04's regression tests; each ships **with** an inline note in the README that it is intentionally malformed/malicious so security scanners and reviewers don't flag it.
3. Write the lockfile-pinning fence `tests/fixtures/test_fixtures_pinning.py` — fails CI if any `package-lock.json` field uses `^`, `~`, `*`, `>`, `<`, or a git/tarball/file URL.
4. Write the size-cap fence `tests/fixtures/test_fixtures_size_cap.py` — fails if any fixture directory exceeds 256 KiB.
5. Write the smoke loader `tests/fixtures/test_fixtures_load.py` parametrized over the 10 directories.
6. For `stale-scip/`: commit a tiny placeholder `index.scip` and a `conftest.py`-level fixture that adjusts its `mtime` to `now - 14 days` at test-collection time (don't try to commit a stale mtime — git doesn't preserve it).
7. For `postinstall-canary/`: name the canary file `/tmp/codegenie-canary-postinstall.txt` and add a session-scoped pytest fixture in `tests/conftest.py` that removes any pre-existing canary file before the session starts.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fixtures/test_fixtures_load.py`

```python
from pathlib import Path
import json
import pytest

FIXTURES_DIR = Path(__file__).parent / "repos"

_EXPECTED_FIXTURES = (
    "express-cve-2024-21501",
    "monorepo-workspaces",
    "transitive-only-cve",
    "peer-dep-conflict",
    "major-bump-required",
    "breaking-test-suite",
    "stale-scip",
    "malformed-package-json",
    "malicious-npmrc",
    "postinstall-canary",
)


@pytest.mark.parametrize("name", _EXPECTED_FIXTURES)
def test_fixture_directory_exists(name: str) -> None:
    """Each Phase 3 fixture documented in phase-arch-design §Fixture portfolio must exist."""
    fx = FIXTURES_DIR / name
    assert fx.is_dir(), f"missing fixture: {name}"
    assert (fx / "package.json").is_file()
    assert (fx / "README.fixture.md").is_file()


@pytest.mark.parametrize(
    "name",
    [n for n in _EXPECTED_FIXTURES if n != "malformed-package-json"],
)
def test_package_json_parses(name: str) -> None:
    """All fixtures except the deliberately-malformed one have a parseable package.json."""
    raw = (FIXTURES_DIR / name / "package.json").read_text()
    json.loads(raw)


def test_malformed_fixture_actually_malformed() -> None:
    """The malformed fixture must blow the 16-depth cap — otherwise it doesn't test what it claims."""
    raw = (FIXTURES_DIR / "malformed-package-json" / "package.json").read_text()
    # Use the project's parse cap (depth=16); reproduce the failure expectation here.
    open_braces = raw.count("{")
    assert open_braces > 16, "malformed-package-json must nest > 16 deep to hit the cap"


def test_readme_has_four_sections() -> None:
    for name in _EXPECTED_FIXTURES:
        readme = (FIXTURES_DIR / name / "README.fixture.md").read_text()
        for section in (
            "## What this fixture is",
            "## Edge case(s) covered",
            "## Expected outcome",
            "## Maintenance",
        ):
            assert section in readme, f"{name} README missing section: {section!r}"
```

State why it fails: nine of the ten directories don't exist; only the S6 stub is on disk. Each parametrized case fails at `FIXTURES_DIR / name` not being a directory.

### Green — minimal pass

- Create each of the nine new directories with a real `package.json`, `package-lock.json` (pinned), `README.fixture.md` (four sections), and the per-fixture extras (workspaces, peer-dep, `.npmrc`, postinstall script, etc.).
- Extend `express-cve-2024-21501/` if the S6 stub is missing the four README sections or the pinned lockfile.
- Run the test until all parametrized cases pass.

### Refactor

- Add the pinning fence `tests/fixtures/test_fixtures_pinning.py` (grep every lockfile for forbidden range chars; fail on any hit) — this catches lockfile regressions when devs regenerate offline.
- Add the size-cap fence (fails on any fixture > 256 KiB).
- Cross-link each `README.fixture.md` to the `phase-arch-design.md §Edge cases` row it satisfies (E#).
- Edge cases from §Edge cases that this code touches: E2, E3, E4, E5, E6, E7, E8, E11, E18, E20 — every fixture is the substrate for at least one. Cite the E# in every fixture's README.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/express-cve-2024-21501/` (extend) | Pin lockfile; add `test/index.test.js`; add four-section README. |
| `tests/fixtures/repos/monorepo-workspaces/` | NEW — workspaces fixture (E3). |
| `tests/fixtures/repos/transitive-only-cve/` | NEW — `overrides`-recipe fixture (E5). |
| `tests/fixtures/repos/peer-dep-conflict/` | NEW — `NotApplicable(PEER_DEP_CONFLICT)` fixture (E4). |
| `tests/fixtures/repos/major-bump-required/` | NEW — `NotApplicable(MAJOR_BUMP_REFUSE)` fixture (E6). |
| `tests/fixtures/repos/breaking-test-suite/` | NEW — `Validated(passed=False)` fixture. |
| `tests/fixtures/repos/stale-scip/` | NEW — stale-index fixture (E18). |
| `tests/fixtures/repos/malformed-package-json/` | NEW — depth-cap rejection fixture (E20). |
| `tests/fixtures/repos/malicious-npmrc/` | NEW — `NetworkDenied` fixture (E7). |
| `tests/fixtures/repos/postinstall-canary/` | NEW — `--ignore-scripts` canary fixture (E8). |
| `tests/fixtures/test_fixtures_load.py` | NEW — smoke loader; parametrized over all 10. |
| `tests/fixtures/test_fixtures_pinning.py` | NEW — lockfile range-char fence. |
| `tests/fixtures/test_fixtures_size_cap.py` | NEW — 256 KiB per-fixture cap. |
| `tests/conftest.py` (extend) | Session-scoped fixture cleaning the postinstall canary path. |

## Out of scope

- **Pre-warmed npm cache** (the `.npm-cache/` tarball that lets `--prefer-offline` install deterministically) — that's S8-03's responsibility because only the determinism property test depends on its content being byte-pinned.
- **Golden lockfile diffs** (`tests/golden/lockfiles/express-cve-2024-21501.{before,after}.json`) — S8-02 ships these from this fixture's lockfile.
- **The actual adversarial tests** asserting `NetworkDenied`, postinstall canary unwritten, depth-cap rejection — S8-04 wires these up to read these fixtures.
- **Yarn Berry routed-to-universal fixture** — `tests/integration/test_yarn_berry_routed_to_universal.py` is a Step 8 test (separate from the 10 fixtures above); the Yarn Berry fixture itself can live alongside but is not in this story's "≥10 fixture repos" target. If the implementer wants to add an 11th fixture (`yarn-berry/`), it's welcome but not required here; S8-04 will create it if absent.
- **VulnIndex seeding** with the CVE records the fixtures reference — that's S3-02/S3-03's job; this story consumes the existing sqlite store.

## Notes for the implementer

- **Lockfile pinning is the load-bearing discipline.** A `^4.17.21` resolved-version in any non-adversarial fixture WILL eventually flake S8-03's determinism property test. The pinning fence (`tests/fixtures/test_fixtures_pinning.py`) is what catches accidental regressions when devs regenerate offline.
- **Don't run `npm install` against the live registry when authoring a fixture.** Generate lockfiles in an isolated bwrap-jail-equivalent or copy the structure from an existing pinned-lockfile-aware Phase 1/2 fixture. The point of the portfolio is that it does NOT depend on network state.
- **Realistic — but minimal — `package.json`.** Each fixture's `package.json` should name a real package as the direct vulnerable dep (e.g., `express@4.17.0`), not invent one. The CVE-IDs in the READMEs must be real (`CVE-YYYY-NNNNN` format; `parse_cve_id` accepts).
- **`stale-scip/` is the only fixture whose state is *time-relative*.** Don't commit a stale mtime to git (git doesn't preserve mtime past clone). Instead, ship a normal `index.scip` and adjust the mtime in a `conftest.py` fixture at collection time (`os.utime(path, (now-14d, now-14d))`).
- **`malicious-npmrc/` and `postinstall-canary/` are adversarial; mark them.** Inline note in each `README.fixture.md`: "This fixture is intentionally hostile and exists solely to verify Phase 3 sandbox containment. Do NOT run `npm install` against it outside the bwrap/sandbox-exec jail."
- **`monorepo-workspaces/` lockfile is the trickiest.** npm v7+ resolves workspaces into the root lockfile under `packages/<workspace>` entries. Use `lockfileVersion: 3`; the workspace package shows up as `"packages/a": { "version": "1.0.0", ... }` in the root lockfile.
- **Match the existing fixture-directory convention** in `tests/fixtures/repos/`. If the Phase 1/2 fixtures use a top-level `README.md` instead of `README.fixture.md`, surface it as a conflict, pick the `README.fixture.md` form (more recent, more disambiguating), and flag the older convention for cleanup. Do not blend the two.
- **The fixture portfolio is a contract for downstream stories.** Once S8-02 and S8-03 land golden files derived from these fixtures, changing a `package-lock.json` byte means regenerating the goldens. Future PRs touching `tests/fixtures/repos/` should expect to touch `tests/golden/lockfiles/` and `tests/golden/event-streams/` in the same PR.
