# Story S7-09 — Layer E real: `OwnershipProbe` + CODEOWNERS parser

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S2-07
**ADRs honored:** `final-design.md` §"Components" §6 — Layer E real-vs-stub split (E1 real; E2–E5 stubs)

## Context

`OwnershipProbe` (E1) is the **only real Layer E probe in Phase 2**; the other four (`ServiceTopologyProbe`, `ServiceContractProbe`, `SLOProbe`, `ProductionConfigProbe`) ship as stubs in S7-10. It reads the repo's `CODEOWNERS` file in the GitHub-documented format (per-line glob pattern + space-separated owner list), with attention to: literal paths, glob patterns (`*.md`, `/src/**`), negation (`!path/to/exclude`), ordering precedence (later rules override earlier), comment lines (`#`), and blank lines. Pure-Python parser — no external dep. Phase 3+ Planner consumers use the output to route PR-creation auth and reviewer assignment.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #21 Layer E` — real-vs-stub split.
  - `../phase-arch-design.md §"Data model"` — no explicit `OwnershipSlice` shape, but `slice = {"code_owners": list[{path_pattern, owners}]}` is the canonical shape per `final-design.md`.
- **Source design:**
  - `../final-design.md §"Components" §6 Layer E — OwnershipProbe (E1) real`.
- **CODEOWNERS reference:**
  - GitHub's documented format — `<pattern> <owner1> <owner2> ...`; supports `*`, `**`, `/` rooting, `!` negation; later rules win.
- **Existing code:**
  - `src/codegenie/probes/__init__.py` — registration target.

## Goal

Ship `src/codegenie/probes/ownership.py` plus `src/codegenie/schema/probes/ownership.schema.json` — pure-Python parser reading `CODEOWNERS` (multiple search locations); emits `slice = {"code_owners": list[{path_pattern, owners, negation: bool, line_number: int}], "source_path": str, "rule_count": int}`; one unit test per CODEOWNERS rule type (literal, glob, negation, ordering, comment, blank-line, missing-file).

## Acceptance criteria

- [ ] `src/codegenie/probes/ownership.py` exports `OwnershipProbe(Probe)` with `name="ownership"`, `declared_inputs=["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]`, `requires=[]`, `applies_to_languages=["*"]`, `applies_to_tasks=["*"]`, `timeout_seconds=10`.
- [ ] Path resolution: check `CODEOWNERS`, then `.github/CODEOWNERS`, then `docs/CODEOWNERS` (GitHub's documented search order). First-found wins; `source_path` records which.
- [ ] If no CODEOWNERS file → `slice = {"code_owners": [], "source_path": null, "rule_count": 0}`; `confidence: high` (absence is a valid fact).
- [ ] Parser handles:
  - **Literal paths:** `/src/important.ts @alice` → `{path_pattern: "/src/important.ts", owners: ["@alice"], negation: false}`.
  - **Glob patterns:** `*.md @docs-team` → glob preserved; not expanded.
  - **Multiple owners:** `/api/ @alice @bob @org/team` → `owners: ["@alice", "@bob", "@org/team"]`.
  - **Negation:** `!/vendor/ @nobody` → `negation: true`. (Note: GitHub doesn't fully support negation, but the parser preserves the syntax.)
  - **Comment lines:** lines starting with `#` ignored.
  - **Blank lines:** ignored.
  - **Inline comments:** `/src/ @alice # security-sensitive` → comment stripped from owners list.
  - **Ordering preserved:** later rules appear later in the emitted list; downstream consumers compute precedence.
- [ ] `src/codegenie/schema/probes/ownership.schema.json` — `additionalProperties: false`; `schema_version: "v1"`; matches the slice.
- [ ] `tests/unit/probes/test_ownership.py` covers one test per rule type — at minimum: `test_literal_path`, `test_glob_pattern`, `test_multiple_owners`, `test_negation_preserved`, `test_comment_lines_ignored`, `test_blank_lines_ignored`, `test_inline_comment_stripped`, `test_ordering_preserved`, `test_missing_file_high_confidence`, `test_alternate_path_locations` (3 search paths).
- [ ] Performance: parse a 1000-rule CODEOWNERS in < 50 ms (asserted via `pytest-benchmark` or simple wall-clock).
- [ ] `tests/golden/ownership/happy/expected.json` — golden file with a representative CODEOWNERS fixture.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/ownership.py`:
   - `OwnershipProbe(Probe)` with class attributes per acceptance criteria.
   - `_find_codeowners(snapshot: Snapshot) -> Path | None` — three-location search.
   - `_parse_codeowners(content: str) -> list[CodeOwnersRule]` — pure-Python parser:
     - For each line (enumerated for `line_number`):
       1. Strip `\n`; strip leading whitespace.
       2. Empty / starts with `#` → skip.
       3. Split on `#` once to separate inline comment.
       4. Tokenize remainder on whitespace.
       5. First token is `path_pattern`; if starts with `!`, mark `negation: True` and strip the `!`.
       6. Remaining tokens are `owners`.
   - `async run(self, snapshot, ctx) -> ProbeOutput`:
     1. `source = self._find_codeowners(snapshot)`.
     2. If `None` → emit empty slice + `confidence: high`.
     3. Else → read content, parse, emit slice.
2. Create `src/codegenie/schema/probes/ownership.schema.json`.
3. Register probe in `probes/__init__.py`.
4. Plant fixtures: `tests/fixtures/ownership_fixture/{root_codeowners,github_codeowners,docs_codeowners,no_codeowners,malformed_codeowners}/` — one per scenario.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_ownership.py`.

```python
import pytest
from codegenie.probes.ownership import OwnershipProbe

async def test_literal_path(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("/src/main.ts @alice\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["code_owners"] == [
        {"path_pattern": "/src/main.ts", "owners": ["@alice"], "negation": False, "line_number": 1}
    ]

async def test_glob_pattern(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("*.md @docs-team\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["code_owners"][0]["path_pattern"] == "*.md"

async def test_multiple_owners(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("/api/ @alice @bob @org/team\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["code_owners"][0]["owners"] == ["@alice", "@bob", "@org/team"]

async def test_negation_preserved(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("!/vendor/ @nobody\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["code_owners"][0]["negation"] is True
    assert out.slice["code_owners"][0]["path_pattern"] == "/vendor/"

async def test_comment_lines_ignored(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("# Comment\n/src/ @alice\n# Another\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["rule_count"] == 1

async def test_inline_comment_stripped(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("/src/ @alice # security-sensitive\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["code_owners"][0]["owners"] == ["@alice"]

async def test_ordering_preserved(make_repo_with_codeowners):
    repo = make_repo_with_codeowners("/src/ @alice\n/src/foo.ts @bob\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert [r["line_number"] for r in out.slice["code_owners"]] == [1, 2]

async def test_missing_file_high_confidence(empty_repo):
    out = await OwnershipProbe().run(empty_repo.snapshot, ctx())
    assert out.confidence == "high"
    assert out.slice["code_owners"] == []
    assert out.slice["source_path"] is None

@pytest.mark.parametrize("location", ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"])
async def test_alternate_path_locations(make_repo_with_codeowners_at, location):
    repo = make_repo_with_codeowners_at(location, "/src/ @alice\n")
    out = await OwnershipProbe().run(repo.snapshot, ctx())
    assert out.slice["source_path"].endswith(location)

async def test_1000_rules_under_50ms(large_codeowners_fixture):
    import time
    t0 = time.perf_counter()
    out = await OwnershipProbe().run(large_codeowners_fixture.snapshot, ctx())
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50
    assert out.slice["rule_count"] == 1000
```

### Green

Minimal impl per outline. The parser is < 40 LOC; the probe shell is < 30 LOC.

### Refactor

- Module docstring naming `phase-arch-design.md §"Component design" #21`, `final-design.md "Components" §6`.
- `_parse_codeowners` is a pure function — testable independently of the probe shell.
- `_find_codeowners` uses a constant tuple at module scope: `_SEARCH_PATHS: Final[tuple[str, ...]] = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/ownership.py` | New — `OwnershipProbe` + parser. |
| `src/codegenie/schema/probes/ownership.schema.json` | New — sub-schema. |
| `src/codegenie/probes/__init__.py` | Register `OwnershipProbe`. |
| `tests/unit/probes/test_ownership.py` | New — 10+ unit tests. |
| `tests/fixtures/ownership_fixture/` | New — multiple subdirs for each scenario. |
| `tests/golden/ownership/happy/expected.json` | New — golden. |

## Out of scope

- **CODEOWNERS *evaluation*** — determining "for file X, who owns it?" is the Planner's job (Phase 3+). This probe records the rules; consumers compute matching.
- **GitHub Enterprise / Bitbucket / GitLab variants** — Phase 2 supports GitHub-documented format only.
- **Cross-repo ownership aggregation** — Phase 14.
- **Owner-to-team resolution** — `@org/team` is preserved as a string; LDAP / SCIM lookup deferred.
- **Stale-owner detection** — Phase 14 portfolio-scale concern.

## Notes for the implementer

- **GitHub's CODEOWNERS spec is small but has corner cases.** Read the spec once before implementing. Edge cases this story explicitly handles:
  - A line with only a pattern and no owners is **valid** in GitHub's spec — used to "reset" a path. Emit `owners: []` for this case.
  - Escaped `\#` is **not** in GitHub's spec — don't handle escapes.
  - Whitespace in patterns is **not** supported — first whitespace splits pattern from owners.
- **`!` negation is preserved syntactically, not semantically.** GitHub historically didn't honor negation; some variants do. The probe records `negation: bool`; the Planner decides what to do with it.
- **`@org/team` is a single owner**, not two. The parser must split on whitespace only — never on `/`.
- **Don't try to *match* paths against patterns.** The probe records rules; matching is the consumer's job. Pulling in a glob library here couples Phase 2 to a particular semantic.
- **The `line_number` field** is 1-indexed (matching how editors display it). Useful for downstream tooling that highlights a specific rule.
- **`source_path` is the path *relative to the repo root*** — not absolute. The slice is portable; absolute paths leak the gather environment.
- **Missing-file high-confidence is intentional.** "No CODEOWNERS file exists" is a fact; the probe successfully observed it. Don't conflate "absence" with "failure" — Phase 2's facts-not-judgments commitment.
- **The 1000-rule perf test** is a regression sentinel — if a future contributor adds a regex-compilation per-rule, the perf budget fires. The current implementation is `str.split` only; staying within 50 ms is trivial.
