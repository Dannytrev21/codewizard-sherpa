# Validation report: S1-04 — Pre-commit hooks + editorconfig + gitignore + mkdocs curated nav

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story file:** [`../S1-04-precommit-editorconfig-mkdocs.md`](../S1-04-precommit-editorconfig-mkdocs.md)

## Summary

S1-04 plants the "first defense" line: a pre-commit firewall whose `forbidden-patterns` regex hook is the *executable* enforcement of ADR-0008 (banned `yaml.load(...)` without `Loader=`, banned `yaml.Dumper`) and ADR-0012 (banned `shell=True`, `os.system`, `os.popen`, `pickle.loads`, `eval(`, `exec(`, `__import__(`, `subprocess.run` shell variants); plus the curated `mkdocs build --strict` site that excludes the five superseded design docs. As written, the story's goal, scope, references, dependency on S1-02, and ADR honoring were structurally sound (no `block`-class architectural issues). The eight ACs and five-test TDD plan, however, repeated four failure patterns already cataloged on S1-01/02/03 and added five new ones load-bearing for this story specifically:

1. **Enumerate-the-list-then-test-a-subset.** AC-1 names 9 hooks but Test 1's `required` set has 8; AC-2 enumerates 11 forbidden patterns but Test 2's needle list checks 7; AC-3 enumerates 6 editorconfig properties but Test 4 checks 4; AC-4 enumerates 13 `.gitignore` entries but Test 3 checks 7. Across all four configs, an implementer can ship 70 % of the contract and pass every original assertion. This is the same root cause four times.
2. **Behavioral ACs with zero behavioral tests.** AC-6 (`pre-commit run --all-files` exits 0) and AC-7 (`mkdocs build --strict` exits 0) are the goal *verbatim*. The original TDD plan has zero tests that invoke either command. A config that parses but fails at runtime (missing entry script, dangling nav entry) ships green. S1-02's precedent for AC-9 already established the pattern of subprocess-running the load-bearing tool from a test; S1-04 needed to follow it.
3. **`yaml.Dumper` regex would also ban the prescribed `yaml.CSafeDumper`/`SafeDumper`.** ADR-0008 §Tradeoffs row 5 prescribes `yaml.CSafeDumper` as the writer while banning `yaml.Dumper`. A naive `grep -E 'yaml\.Dumper'` regex matches both. AC-2 named the pattern but the test never asserted the regex is anchored. Real bug: the day someone adds the writer to `src/`, pre-commit blocks the commit.
4. **`yaml.safe_dump(forbidden)` then substring-check is regex-escape fragile.** A correctly-anchored pattern like `r"yaml\.load\("` serializes as `yaml\.load\(` and substring `"yaml.load"` no longer matches (the backslash breaks the match). The original Test 2 pushed the implementer toward un-escaped, over-matching greps.
5. **`_flatten` silently drops non-list `dict` values.** mkdocs accepts `{"Production": {"Design": "design.md"}}` as a valid nav shape. The original helper's recursion only fires on `isinstance(v, list)`; a dict-valued nav item is yielded as a `dict` object and the subsequent `excluded not in ref` becomes dict-key membership, not substring. A deeply nested excluded doc slips silently.
6. **Recipe-body vs entry-script discipline.** Test 1 only checked hook *ids*; an `entry: "true"` (the unix command, always exit 0) would pass. This matters most for `forbidden-patterns` (the only local hook). Same Rule-9 anti-pattern as S1-03's "lazy `lint:\n\techo lint`" — verifies declaration, not intent.
7. **`subprocess.run` shell variants — ADR-0012 vs phase-arch Q6 contradiction.** ADR-0012 §Decision line 36 names `subprocess.run` shell variants as Phase-0 banned. Phase-arch §Open questions Q6 lists the same and defers to Phase 1. The story's Out-of-scope (line 197) cites Q6 to defer. ADR Decision wins; the story now bans `subprocess.run(...shell=...)`.
8. **`print(` scope.** AC-2 carves out `tests/` and `scripts/` from the `print(` ban — load-bearing per implementer notes. No original test verified the hook's `files:`/`exclude:` block actually exempts those directories.
9. **Process-clause pattern.** AC-8 includes "was committed" — the same cataloged clause already relaxed on S1-01/02/03.
10. **Documentary clauses that aren't testable.** AC-5's "near the nav entry that would have included it, or in a top-of-file `# excluded files:` block" — `yaml.safe_load` strips comments, so Test 5 *cannot* ever verify this. The comment clause was kept but moved to "documentary" so the test contract is honest.

The Refactor step §5 placeholder file (`docs/contributing.md`) is load-bearing for AC-7 (mkdocs strict green) but had no AC. Added.

We rewrote AC-1 (full 9-hook list mirrored in Test 1); AC-2 (full 11-pattern list including `subprocess.run(...shell=...)`, anchored `yaml.Dumper` regex, behavioral fixture test); AC-3 (full 6 *.py properties + `Makefile` `indent_style = tab`); AC-4 (full 13 entries, line-parse not substring); AC-5 (comment requirement moved to documentary; nav exclusion remains load-bearing); AC-6 strengthened (behavioral subprocess test); AC-7 strengthened (behavioral subprocess test); AC-8 relaxed (drop "was committed"). Added AC-9 (`rev` SHA-pinning), AC-10 (`docs/contributing.md` placeholder exists), AC-11 (`print(` scope tested), AC-12 (`yaml.Dumper` regex does NOT match `yaml.CSafeDumper`/`SafeDumper`). TDD plan grew from 5 tests to 12. No structural rewrites; the story's goal, scope, dependency on S1-02, and ADR honor framing are unchanged. Verdict: HARDENED.

## Findings by critic

### Coverage critic findings — S1-04

#### F1 — AC-1 lists `trailing-whitespace` but Test 1's `required` set omits it
- **Severity:** harden
- **What's wrong:** AC-1 names 9 hooks; Test 1's `required` set lists 8. Implementer can ship 8/9 and pass.
- **Proposed fix:** Mirror AC-1 and Test 1 to the same `REQUIRED_HOOKS` constant.
- **Confidence:** high
- **Source:** AC-to-test trace (cataloged pattern).

#### F2 — AC-2 enumerates 10–11 patterns; Test 2 checks 7
- **Severity:** harden
- **What's wrong:** AC-2 requires bans on `print(`, `yaml.load(` (no Loader=), `shell=True`, `yaml.Dumper`, `os.system(`, `os.popen(`, `pickle.loads(`, `eval(`, `exec(`, `__import__(`. Test 2 only substring-checks 7 needles; `print(`, `exec(`, `__import__(` are missing. Subsumed by Test-Quality F1 below.
- **Proposed fix:** See Test-Quality F1.
- **Confidence:** high

#### F3 — `print(` scope ("outside `tests/` and `scripts/`") has no test
- **Severity:** harden
- **What's wrong:** AC-2 scopes the `print(` ban; implementer notes (line 203) call it out as load-bearing. No test verifies the `files:`/`exclude:` block.
- **Proposed fix:** Add Test 11: parse the `forbidden-patterns` hook block and assert it exempts `^tests/` and `^scripts/` for the `print(` rule (either via per-rule split or a hook-level `exclude` regex).
- **Confidence:** high

#### F4 — Behavioral ACs have zero behavioral tests
- **Severity:** block
- **What's wrong:** AC-6 and AC-7 (the *goal verbatim*) have zero subprocess tests. A config that parses but fails at runtime ships green. Same Rule 9 + Rule 12 violation pattern.
- **Proposed fix:** Add Test 7 (`subprocess.run(["pre-commit", "run", "--all-files"])` exits 0) and Test 8 (`subprocess.run(["mkdocs", "build", "--strict"])` exits 0).
- **Confidence:** high
- **Source:** S1-02's AC-9 precedent (subprocess-run the load-bearing tool).

#### F5 — AC-3 enumerates 6 editorconfig properties; Test 4 checks 4
- **Severity:** harden
- **What's wrong:** Missing assertions: `charset = utf-8`, `insert_final_newline = true`, `trim_trailing_whitespace = true` for `[*.py]`. Also `[Makefile]` exists but `indent_style = tab` inside it is unverified — that's the *only* reason the section is there.
- **Proposed fix:** Switch to `configparser` parse (INI-shaped); full 6-key check on `[*.py]`; assert `cfg["Makefile"]["indent_style"] == "tab"`.
- **Confidence:** high

#### F6 — AC-4 enumerates 13 `.gitignore` entries; Test 3 checks 7
- **Severity:** harden
- **What's wrong:** Missing: `*.pyc`, `htmlcov/`, `*.egg-info/`, `dist/`, `build/`, `.env`, `.DS_Store`. `.env` is security-relevant (ADR-0008 territory). Also, `".codegenie/" in body` matches a comment line `# .codegenie/ is gitignored` — false positive.
- **Proposed fix:** Line-parse `.gitignore`, strip whitespace, skip `#`-prefixed lines, assert each of all 13 entries appears as a standalone uncommented line.
- **Confidence:** high

#### F7 — `rev` SHA-pinning is in the implementation outline but not an AC
- **Severity:** harden
- **What's wrong:** Implementation outline §2 mandates SHA-pinned `rev` per phase-arch §CI gates ("Actions pinned by SHA"). No AC, no test — implementer can ship mutable `v1.2.3` tags and pass.
- **Proposed fix:** AC-9 (new): every hook's `rev` matches `^[0-9a-f]{40}$`. Test 6 enforces it. The local `forbidden-patterns` repo has no `rev` (it's `repo: local`); the test must skip those.
- **Confidence:** high

#### F8 — `docs/contributing.md` placeholder is in the refactor step but not an AC
- **Severity:** harden
- **What's wrong:** AC-7 (`mkdocs build --strict` green) hinges on the placeholder existing. Without an AC, an implementer who authors a nav referencing `contributing.md` without creating the file passes static tests but fails AC-7. Adopting F4 transitively catches it, but the static AC makes the dependency explicit.
- **Proposed fix:** AC-10 (new): `docs/contributing.md` exists with a `# TODO(S5-02)` placeholder. Test 9 asserts the file exists and contains the TODO marker.
- **Confidence:** high

#### F9 — Test 5's `_flatten` doesn't recurse into bare-dict values
- **Severity:** harden
- **What's wrong:** mkdocs accepts `{"Production": {"Design": "design.md"}}` — a dict-valued nav item. The helper yields the dict object, and `excluded not in ref` becomes dict-key membership (not substring). A deeply nested excluded doc slips. Promoted from "nit" to "harden" because mkdocs *does* accept this shape; future contributors editing the nav will not know to avoid it.
- **Proposed fix:** Recurse on any `Mapping`. Assert each yielded ref is a `str` before substring-check.
- **Confidence:** high

#### F10 — AC-5's "comment near excluded entry" is unverifiable after `yaml.safe_load`
- **Severity:** nit
- **What's wrong:** `yaml.safe_load` strips comments; Test 5 cannot ever verify this. An implementer ships `mkdocs.yml` with zero comments and passes.
- **Proposed fix:** Move the comment requirement from the load-bearing AC-5 contract to a documentary "Refactor §5" note. Or add a raw-text grep test if the comment is truly required (we choose to demote — the nav-exclusion property is what AC-7 hinges on).
- **Confidence:** medium

### Test-Quality critic findings — S1-04

#### F1 — Test 2 misses 4 of 11 ADR-mandated forbidden patterns; check is regex-escape fragile
- **Severity:** block
- **What's wrong:** Two compounded bugs. (a) The needles list is `{shell=True, yaml.load, os.system, os.popen, pickle.loads, eval(, yaml.Dumper}` — missing `print(`, `exec(`, `__import__(`, plus the `subprocess.run(...shell=...)` variant per ADR-0012. (b) The check `yaml.safe_dump(forbidden); "yaml.load" in body` breaks when patterns are stored as anchored regexes (`r"yaml\.load\("`): the serialized body contains `yaml\.load\(`, and the substring `yaml.load` no longer matches (the backslash breaks the run-length-9 match). Net effect: a correctly-anchored impl fails the test, pushing the implementer to ship un-escaped greps that over-match (e.g., `os.system` matching `cos.systemic` in a comment).
- **Proposed fix:** Replace the YAML-serialization-then-substring approach with a **behavioral fixture test**. For each of the 11 patterns, write a temp file containing the banned construct; subprocess-invoke the hook's `entry` script against that file; assert the script exits non-zero and the stderr/stdout names the pattern. This is Rule 9 (tests verify intent, not declaration) and Rule 12 (fail loud — runtime evidence the hook does its job).
- **Confidence:** high

#### F2 — `yaml.Dumper` regex would ban `yaml.CSafeDumper`/`SafeDumper` too
- **Severity:** block
- **What's wrong:** Subsumed by Consistency F1. ADR-0008 prescribes `yaml.CSafeDumper`; the hook must NOT block it. Naive `yaml\.Dumper` matches both.
- **Proposed fix:** AC-12 (new): the `yaml.Dumper` regex is anchored so it does NOT match `yaml.CSafeDumper` or `yaml.SafeDumper`. Test (part of Test 2's behavioral suite): feed `yaml.CSafeDumper(x)` to the hook entry, assert exit 0 (not blocked); feed `yaml.Dumper(x)`, assert exit non-zero (blocked).
- **Confidence:** high

#### F3 — Test 4 doesn't assert Makefile uses tabs
- **Severity:** block
- **What's wrong:** Asserts `[Makefile]` section header exists; does not assert `indent_style = tab` inside it. An impl with `[Makefile]\nindent_style = space` passes — and that breaks `make` (POSIX requires tab for recipes).
- **Proposed fix:** `configparser` parse, full key-value assertions. See Coverage F5.
- **Confidence:** high

#### F4 — Test 5's `_flatten` silently drops non-list dict values
- **Severity:** block
- **What's wrong:** See Coverage F9.
- **Proposed fix:** See Coverage F9.
- **Confidence:** high

#### F5 — Test 1 doesn't verify hook entries are non-stub
- **Severity:** harden
- **What's wrong:** An impl with `id: forbidden-patterns, entry: "true"` passes. Critical for the local `forbidden-patterns` hook.
- **Proposed fix:** Assert each `local` repo hook's `entry` is set, non-empty, and references either a real file under `scripts/` or contains `grep -E`. Behavioral test (F1) catches this transitively but the structural check is cheap insurance.
- **Confidence:** high

#### F6 — Test 1 omits `trailing-whitespace`
- **Severity:** nit
- **What's wrong:** See Coverage F1.
- **Confidence:** high

#### F7 — Test 3 substring tolerates commented-out entries
- **Severity:** harden
- **What's wrong:** `".codegenie/" in body` matches `# .codegenie/ is gitignored by convention`. Slip risk.
- **Proposed fix:** Line-parse, skip `#`-prefixed. See Coverage F6.
- **Confidence:** high

#### F8 — No behavioral test for `pre-commit run --all-files` or `mkdocs build --strict`
- **Severity:** harden
- **What's wrong:** See Coverage F4.
- **Confidence:** high

**Property-based / metamorphic applicability:** Not useful for static config files. Table-driven parametric tests over the `REQUIRED_PATTERNS` / `REQUIRED_GITIGNORE_ENTRIES` / `REQUIRED_EDITORCONFIG_PYPROPS` constants give all the mutation resistance property-based testing would. The one genuinely behavioral angle (covered by F1's fixture approach): for each banned pattern P, feeding a file containing `print(P)` to the hook entry should exit non-zero — a metamorphic-like specification-by-example over the pattern set.

### Consistency critic findings — S1-04

#### F1 — AC-2 `yaml.Dumper` regex would ban the prescribed `yaml.CSafeDumper`
- **Severity:** block
- **What's wrong:** ADR-0008 §Tradeoffs row 5 + §Consequences prescribe `yaml.CSafeDumper` as the writer while banning `yaml.Dumper`. AC-2 names the ban but doesn't constrain the regex shape. Naive `yaml\.Dumper` matches both.
- **Proposed fix:** AC-12 (new); see Test-Quality F2.
- **Confidence:** high
- **Source:** ADR-0008 §Tradeoffs row 5, §Consequences bullet 1.

#### F2 — Missing forbidden pattern: `subprocess.run(..., shell=...)`
- **Severity:** harden
- **What's wrong:** ADR-0012 §Decision line 36 explicitly names "`subprocess.run` shell variants". The story's AC-2 only enumerates `shell=True`. The story's Out-of-scope (line 197) cites phase-arch §Open questions Q6 to defer the broader list. **Direct contradiction:** ADR-0012 Decision (Accepted) says Phase 0; phase-arch Q6 (Open Question) says Phase 1.
- **Proposed fix:** ADR Decision wins as source of truth. Add `subprocess.run(..., shell=...)` to AC-2 and Test 2's behavioral fixture set. The Out-of-scope wording is narrowed: `marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"` stay deferred; `subprocess.run(...shell=...)` is pulled in.
- **Confidence:** high
- **Source:** ADR-0012 §Decision line 36; phase-arch §Open questions Q6.

#### F3 — `trailing-whitespace` hook is in AC-1 but not in source spec
- **Severity:** nit
- **What's wrong:** High-level-impl §Step 1 line 26 lists 8 hooks; AC-1 adds `trailing-whitespace`. Harmless additive but inconsistent with source.
- **Proposed fix:** Keep `trailing-whitespace` (it's same-repo as `end-of-file-fixer`, harmless, and matches editorconfig's `trim_trailing_whitespace = true`); add a sentence to the Context block explaining the additive choice.
- **Confidence:** medium

#### F4 — AC-7 silently depends on `docs/contributing.md` placeholder
- **Severity:** harden
- **What's wrong:** See Coverage F8.
- **Proposed fix:** AC-10 (new). See Coverage F8.
- **Confidence:** high

#### F5 — AC-5 "comment near nav entry" allows two forms; Test 5 verifies neither
- **Severity:** nit
- **What's wrong:** See Coverage F10.
- **Proposed fix:** Demote comment to documentary "Refactor §5" note. See Coverage F10.
- **Confidence:** medium

#### F6 — AC-8 "was committed" — process clause unverifiable from working tree
- **Severity:** nit (cataloged)
- **What's wrong:** Same as S1-01/02/03.
- **Proposed fix:** Drop the clause; restate as "exists and exits 0 under pytest".
- **Confidence:** high

#### F7 — AC-2 → goal trace is indirect
- **Severity:** nit (observational)
- **What's wrong:** AC-2 (regex content) traces to the goal only via ADRs 0008/0012; an incomplete regex set still lets `pre-commit run` exit 0 on a clean tree. Behavioral verification of the regex set is in S2-02/S4-05 (AST scans). The story now has F1's behavioral test which closes the loop within S1-04 itself — surfaced but no further edit needed.
- **Source:** Story lines 33, 38, 195.

#### F8 — Consistency checks that passed (✓)
- Five-excluded-doc set matches CLAUDE.md and phase-arch.
- `mkdocs-material` dependency wired in S1-01's `[dev]` extras.
- `gitleaks` correctly placed at pre-commit, not in synchronous write path (ADR-0008 §Consequences bullet 4).
- "Humans always merge" / "No LLM in gather" — not applicable; no contradictions.

## Research briefs

None. No findings tagged `NEEDS RESEARCH`. All patterns invoked are catalog techniques: AC ↔ test enumeration mirroring, substring-vs-line-parse, regex-escape mutation slip, behavioral-fixture-vs-config-parse (Rule 9), configparser over substring (codebase precedent), SHA-pin enumeration, mkdocs nav recursion over `Mapping`.

## Conflict resolutions

1. **Consistency F2 (ADR-0012 Decision says ban `subprocess.run` shell variants) vs. story Out-of-scope line 197 (phase-arch Q6 defers).** ADR Decision (Accepted) wins as source of truth. AC-2 expanded; Out-of-scope narrowed to retain only the patterns Q6 lists *beyond* `subprocess.run(...shell=...)` (`marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"`).
2. **Coverage F4 / TQ F8 (behavioral tests for `pre-commit run` and `mkdocs build`) vs. Out-of-scope line 195 (AST scans deferred to S2-02/S4-05).** No conflict — S2-02/S4-05's AST scans verify the regex catches violations *in the codebase*; S1-04's behavioral test verifies the hook *runs and exits 0 on the current clean tree* and the `forbidden-patterns` script *exits non-zero on a fixture file containing each banned pattern*. Different scope, different layer.
3. **Coverage F9 / TQ F4 (`_flatten` recursion into `Mapping`).** Promoted from "nit" to "harden". mkdocs *does* accept nested-dict shapes; future-proofing the test is cheap.
4. **Coverage F10 / Consistency F5 (AC-5 comment requirement).** Resolution: demote to documentary. The load-bearing property is "nav excludes the 5 docs"; the comment requirement is reviewer-friendly but not testable from `yaml.safe_load`.

## Edits applied

### Edit 1 — AC-1 strengthened (Coverage F1, TQ F6, Consistency F3)
- **Before:** "`.pre-commit-config.yaml` exists … declaring hooks: `ruff` (lint), `ruff-format`, `mypy` (strict on `src/`), `gitleaks`, a local `forbidden-patterns` regex hook, `check-yaml`, `check-toml`, `end-of-file-fixer`, and `trailing-whitespace`."
- **After:** Frozen list of 9 hooks; the same set is mirrored in Test 1 via a `REQUIRED_HOOKS` constant. A bullet documents that `trailing-whitespace` is an additive harden over High-level-impl §Step 1's 8-hook list (same `pre-commit-hooks` repo, pairs with editorconfig's `trim_trailing_whitespace`).

### Edit 2 — AC-2 strengthened (Coverage F2, F3; TQ F1, F2; Consistency F1, F2)
- **Before:** 10 patterns + qualifier on `yaml.Dumper`; no anchoring requirement; no `subprocess.run(...shell=...)`.
- **After:** 11 patterns including `subprocess.run\s*\(.*shell\s*=` (ADR-0012 §Decision line 36 wins over phase-arch Q6's deferral). The `yaml.Dumper` regex must be anchored so it does NOT match `yaml.CSafeDumper` or `yaml.SafeDumper`. The `print(` rule's scope (`exclude: ^(tests/|scripts/)`) is contractual.

### Edit 3 — AC-3 strengthened (Coverage F5, TQ F3)
- **Before:** Six properties enumerated; Makefile section named without enforcement of its `indent_style`.
- **After:** Six properties for `[*.py]` and `indent_style = tab` for `[Makefile]` — both individually contracted. Test 4 switches from substring to `configparser` parse.

### Edit 4 — AC-4 strengthened (Coverage F6, TQ F7)
- **Before:** 13 entries enumerated; Test 3 substring-checked 7.
- **After:** 13 entries, all line-parse-verified (skipping comments and blank lines). The .env entry is called out as security-relevant per ADR-0008's spirit.

### Edit 5 — AC-5 split (Coverage F10, Consistency F5)
- **Before:** Nav exclusion + comment requirement in one AC.
- **After:** AC-5 retains only the load-bearing clause (nav excludes the 5 docs). The comment-near-nav-entry guidance moves to "Notes for the implementer" as documentary (yaml.safe_load strips comments; we don't contract on what we cannot test).

### Edit 6 — AC-6 strengthened (Coverage F4, TQ F8)
- **Before:** "`pre-commit install` succeeds and `pre-commit run --all-files` exits 0 on the current tree."
- **After:** Adds: "Test 7 in the TDD plan invokes `pre-commit run --all-files` via `subprocess.run` and asserts `returncode == 0`."

### Edit 7 — AC-7 strengthened (Coverage F4, TQ F8)
- **Before:** "`mkdocs build --strict` exits 0 from the repo root."
- **After:** Adds: "Test 8 in the TDD plan invokes `mkdocs build --strict` via `subprocess.run` and asserts `returncode == 0`."

### Edit 8 — AC-8 relaxed (Consistency F6)
- **Before:** "The TDD plan's red test exists, was committed, and is green."
- **After:** "`tests/unit/test_precommit_and_docs_config.py` exists, and `pytest tests/unit/test_precommit_and_docs_config.py -q` exits 0."

### Edit 9 — AC-9 added (Coverage F7)
- **New AC:** "Every hook in `.pre-commit-config.yaml` from a non-`local` repo declares `rev` as a 40-character lowercase hex SHA (matching `^[0-9a-f]{40}$`), not a tag. The `local` `forbidden-patterns` hook has no `rev`."

### Edit 10 — AC-10 added (Coverage F8, Consistency F4)
- **New AC:** "`docs/contributing.md` exists and contains the substring `TODO(S5-02)` so the curated `nav` resolves under `mkdocs build --strict`. The real contributor docs land in S5-02."

### Edit 11 — AC-11 added (Coverage F3)
- **New AC:** "The `forbidden-patterns` hook's `print(` rule is scoped via `exclude:` (or `files:`) to skip files under `^tests/` and `^scripts/`. Test 11 in the TDD plan parses the hook block and asserts the exclusion regex matches both prefixes."

### Edit 12 — AC-12 added (Consistency F1, TQ F2)
- **New AC:** "The `yaml.Dumper` regex is anchored so `re.search(pattern, 'yaml.CSafeDumper')` and `re.search(pattern, 'yaml.SafeDumper')` are both `None`, while `re.search(pattern, 'yaml.Dumper(x)')` returns a match. This preserves ADR-0008's prescribed writer (`yaml.CSafeDumper`)."

### Edit 13 — TDD plan rewritten (all critic findings)
- **Before:** 5 tests; YAML-serialize-then-substring (regex-escape fragile); subset enumeration; no behavioral coverage of the goal sentence.
- **After:** 12 tests organized by AC:
  - Test 1: AC-1 — full 9-hook required-set check + assertion that each `local` hook's `entry` references an existing file or contains `grep -E`.
  - Test 2: AC-2 + AC-12 — behavioral fixture: write 11 temp files each containing one banned construct; invoke `scripts/check_forbidden_patterns.sh` against each; assert exit non-zero. Additionally feed `yaml.CSafeDumper(x)` and `yaml.SafeDumper(x)` to the hook; assert exit 0 (the regex is anchored).
  - Test 3: AC-4 — line-parse `.gitignore`; assert each of 13 entries appears as a standalone uncommented line.
  - Test 4: AC-3 — `configparser`-parse `.editorconfig`; assert full 6-key contract on `[*.py]` and `indent_style = tab` on `[Makefile]`.
  - Test 5: AC-5 — recursive `_flatten` over `Mapping` (not just `list`); assert each yielded ref is `str`; assert no ref contains any of the 5 excluded filenames.
  - Test 6: AC-9 — iterate `cfg["repos"]`; for each non-`local` repo, assert `rev` matches `^[0-9a-f]{40}$`.
  - Test 7: AC-6 — `subprocess.run(["pre-commit", "run", "--all-files"], cwd=PROJECT_ROOT)`; assert `returncode == 0`. Skip with reason if `pre-commit` is not on `PATH` (unit run on dev box without the dev extras).
  - Test 8: AC-7 — `subprocess.run(["mkdocs", "build", "--strict"], cwd=PROJECT_ROOT)`; assert `returncode == 0`. Skip with reason if `mkdocs` is not on `PATH`.
  - Test 9: AC-10 — assert `docs/contributing.md` exists and contains `TODO(S5-02)`.
  - Test 10: AC-1 — assert no hook id is duplicated across the config (cheap robustness).
  - Test 11: AC-11 — parse the `forbidden-patterns` hook block; assert it scopes `print(` (either per-rule or hook-level) to exclude `^tests/` and `^scripts/`.
  - Test 12: AC-8 — meta-assert via `pytest`'s own self-collection that this file collected at least 11 test functions.
- **Rationale:** Each AC now has at least one test that would fail under an obviously-wrong implementation; the goal sentence (Tests 7+8) is directly verified, not inferred.

### Edit 14 — Implementation outline strengthened
- Step 5 expanded to call out the SHA-pinning rule explicitly (was implicit in step 2).
- Step 1 (write the red test) updated to reflect the 12-test plan.

### Edit 15 — Out-of-scope narrowed (Consistency F2 conflict resolution)
- **Before:** "Extending the `forbidden-patterns` regex set with `subprocess.run(..., shell=...)`, `marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"` — these are filed as Phase 1 hardening per phase-arch Q6."
- **After:** "Extending the `forbidden-patterns` regex set with `marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"` — these are filed as Phase 1 hardening per phase-arch Q6. (`subprocess.run(..., shell=...)` is pulled into AC-2 per ADR-0012 §Decision line 36.)"

### Edit 16 — Status line + Validation notes block
- Status: "Ready" → "Ready (validated 2026-05-13 — HARDENED)".
- Inserted `## Validation notes` block under the header with changes summary and conflict resolutions.

## Verdict rationale

HARDENED. Three `block`-class findings (TQ F1+F2 fused: regex-escape-fragile substring check + missing 4 patterns; TQ F3: Makefile tabs unverified; TQ F4: `_flatten` drops nested dicts; Consistency F1: `yaml.Dumper` regex bans the prescribed writer; Coverage F4: behavioral goal ACs untested) all had concrete, mechanical fixes. Seven `harden` findings clustered around four root causes: (1) enumerate-the-list-test-a-subset (across 4 configs); (2) static-config-tests-with-no-behavioral-bridge (already-cataloged pattern from S1-02 AC-9); (3) implementation-outline contracts (SHA-pinning, placeholder file) not promoted to ACs; (4) `print(` scope unverified. Three `nit`s relaxed mechanically (trailing-whitespace mirroring, AC-5 comment demotion, AC-8 "was committed").

After the edits, the most obvious mutation paths are closed:
- `lint:\n\techo lint` — not applicable (S1-03 territory).
- Forbidden-patterns hook with `entry: "true"` — caught by Test 1's entry assertion AND Test 2's behavioral fixture.
- `yaml.Dumper` regex written as `yaml\.Dumper` (matching CSafeDumper) — caught by Test 2's CSafeDumper-not-blocked assertion.
- `.editorconfig` with `[Makefile]\nindent_style = space` — caught by Test 4's configparser check.
- `mkdocs.yml` with `{"Production": {"localv2": "localv2.md"}}` (dict-of-dict) — caught by Test 5's `Mapping`-recursive flatten.
- `.pre-commit-config.yaml` with mutable `rev: v1.2.3` — caught by Test 6's SHA regex.
- `mkdocs.yml` referencing `contributing.md` without the file — caught by Test 9 (file exists) and Test 8 (build --strict).
- 6 of 11 `forbidden-patterns` declared but `exec(` skipped — caught by Test 2's behavioral fixture iterating all 11.

The story meets the "STRONG bar" for executor handoff.

## Recommended next step

Run `phase-story-executor` against the hardened story file. The executor's Validator pass should verify:
- All 12 TDD tests are green.
- `pre-commit install` followed by `pre-commit run --all-files` is green from a clean S1-01..S1-03 tree.
- `mkdocs build --strict` is green on a clean tree.
- The four config files (`.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`, `mkdocs.yml`) plus the `scripts/check_forbidden_patterns.sh` entry script and the `docs/contributing.md` placeholder are all present.
- The hook's behavioral fixture sub-tests (Test 2) demonstrate the forbidden-patterns script correctly accepts `yaml.CSafeDumper(x)` and rejects each of the 11 banned constructs.
