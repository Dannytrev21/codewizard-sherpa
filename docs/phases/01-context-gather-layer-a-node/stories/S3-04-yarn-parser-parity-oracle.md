# Story S3-04 — Yarn parser parity + property-based oracle tests (Gap 3)

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** M
**Depends on:** S3-03 (`_yarn.py` exists with `_HAS_PYARN` dispatch + hand-rolled scanner)
**ADRs honored:** ADR-0003 (the parity test that protects either land-time selection)

## Context

Phase-arch-design's Gap 3 names the failure mode: shipping two parsers (`pyarn` and hand-rolled) without a parity contract means either parser can silently diverge from the other — `NodeManifestProbe` outputs depend on the parser path, the catalog cross-reference produces different hits per install state, and the cache key (already path/size-only per Phase 0 ADR-0001) doesn't disambiguate. The mitigation is **two-direction validation**:

1. **Fixture-based parity** — for every curated `yarn.lock` in the test portfolio, both parsers (when available) produce the same `YarnLock` `TypedDict`. Detects "either parser drifted from the curated truth."
2. **Property-based oracle** — for every parser output, the output satisfies invariants derived from the lockfile bytes themselves. Detects "both parsers drifted from reality together" (which fixture-parity would silently miss).

Both tests are required because they fail for orthogonal reasons. The oracle is the load-bearing piece: invariants derived from the lockfile bytes are independent of either parser's implementation, so even a coordinated bug ships a red CI.

This story is the answer to the gap analysis; without it, ADR-0003's "Reversibility: high" claim is unsupported.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" Gap 3` — the two-direction validation rationale; **this story's spec**.
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — both parser paths defined.
- **Phase ADRs:**
  - `../ADRs/0003-yarn-lock-parser-choice.md` — both parsers must return identical `YarnLock` TypedDict; the parity test is the contract enforcement.
- **Source design:**
  - `../final-design.md §"Risks" Gap 3` (parity-test rationale).
  - `../High-level-impl.md §"Step 3"` `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` + `test_yarn_parser_oracle.py` listing.
- **Existing code (from S3-03):**
  - `src/codegenie/probes/_lockfiles/_yarn.py` — exposes `_HAS_PYARN`, `parse()`, and `_parse_handrolled()`.
- **External docs:**
  - Yarn classic lockfile format spec (https://classic.yarnpkg.com/en/docs/yarn-lock) — reference for invariant derivation.

## Goal

Ship two unit tests — fixture-based parity (`test_yarn_parser_parity.py`) and property-based oracle (`test_yarn_parser_oracle.py`) — so silent divergence between `pyarn` and the hand-rolled scanner trips CI on any fixture in the portfolio.

## Acceptance criteria

- [ ] `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` runs both `pyarn` and `_parse_handrolled` against every fixture under `tests/fixtures/_yarn_corpus/` and asserts identical `YarnLock` `TypedDict` output.
- [ ] When `pyarn` is not installed, `test_yarn_parser_parity.py` `pytest.skip`s with a clear reason; CI matrix on at least one job has `pyarn` installed so the parity test exercises.
- [ ] `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` defines ≥ 3 invariants and asserts each on every fixture in `tests/fixtures/_yarn_corpus/`, exercising **both** parser paths (parametrized over `_HAS_PYARN ∈ {True, False}` via monkeypatch).
- [ ] **Invariant 1**: for every entry name in parser output, that name (substring) appears at least once in the lockfile bytes.
- [ ] **Invariant 2**: for every `version` field in parser output, that version string appears in the lockfile bytes on or near (within 5 lines of) the matching entry header.
- [ ] **Invariant 3**: number of entries in parser output equals the count of lines in the lockfile bytes that match the entry-header shape (no leading whitespace, ending with `:`, not a comment).
- [ ] `tests/fixtures/_yarn_corpus/` contains ≥ 4 curated `yarn.lock` files: (a) a minimal single-entry, (b) a multi-entry with `dependencies`, (c) a multi-spec-shared header (`"foo@^1, foo@^2":`), (d) an empty (just headers and comments, zero entries).
- [ ] Each fixture has a `README.md` next to it documenting what it exercises and what invariants it pins.
- [ ] On a deliberate one-line edit to `_parse_handrolled` (e.g., swapping `"version"` field name to `"ver"`) — verified locally — both tests fail; commit a paragraph in the PR body capturing the failure mode.
- [ ] `ruff`, `mypy --strict`, `pytest` all pass.

## Implementation outline

1. **Land the fixture corpus first**: create `tests/fixtures/_yarn_corpus/` with the four curated `yarn.lock` files. Each lockfile is real-shaped — derive from `tests/fixtures/node_yarn_legacy/` (S3-06) or synthesize from a known package set. Add a `README.md` per fixture.
2. **Parity test**: parametrize over the corpus, call `pyarn.parse(lockfile.read_text())` and `_yarn._parse_handrolled(lockfile.read_bytes())`, compare `YarnLock` dicts via direct equality. Skip the entire test module if `_yarn._HAS_PYARN is False`.
3. **Oracle test**: parametrize over the corpus AND over `_HAS_PYARN ∈ {True, False}` via monkeypatch. For each combination, parse and assert all three invariants.
4. **Implement the invariant checks** as small helper functions in the test module (typed, named, ≤ 10 LOC each). Don't extract to `src/` — these are test-only logic and shouldn't influence the parser surface.
5. **Self-check via mutation**: locally introduce a one-line bug in `_parse_handrolled` (e.g., rename `version` extraction) and confirm both tests catch it. Revert the mutation; record the experiment in the PR body.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` (start with the oracle — it's the more general defense).

```python
# tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py
from pathlib import Path
import pytest
from codegenie.probes._lockfiles import _yarn

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))


def _entry_header_lines(body: str) -> list[str]:
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") or line.startswith(" "):
            continue
        if line.endswith(":"):
            out.append(line[:-1])
    return out


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("force_handrolled", [True, False])
def test_oracle_entry_names_appear_in_lockfile(
    lockfile: Path, force_handrolled: bool, monkeypatch
):
    if force_handrolled:
        monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    body = lockfile.read_text()
    result = _yarn.parse(lockfile)
    # Invariant 1: every entry-name substring appears in the lockfile bytes.
    for entry_key in result["entries"]:
        # entry_key may be "foo@^1.0, foo@^1.1" — split and verify each.
        for spec in entry_key.split(", "):
            name = spec.rsplit("@", 1)[0]
            assert name in body, f"parser invented entry {name!r}"


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("force_handrolled", [True, False])
def test_oracle_entry_count_matches_header_count(
    lockfile: Path, force_handrolled: bool, monkeypatch
):
    if force_handrolled:
        monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    body = lockfile.read_text()
    result = _yarn.parse(lockfile)
    # Invariant 3: entry count matches the count of entry-header lines.
    assert len(result["entries"]) == len(_entry_header_lines(body))


# (additional oracle test for invariant 2 — version locality — omitted for brevity)
```

Then add the parity test:

```python
# tests/unit/probes/_lockfiles/test_yarn_parser_parity.py
from pathlib import Path
import pytest
from codegenie.probes._lockfiles import _yarn

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))

pytestmark = pytest.mark.skipif(
    not _yarn._HAS_PYARN, reason="pyarn not installed; parity test requires both parsers"
)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_pyarn_and_handrolled_produce_identical_yarnlock(lockfile: Path):
    import pyarn  # type: ignore[import-not-found]
    handrolled_out = _yarn._parse_handrolled(lockfile.read_bytes())
    pyarn_out = pyarn.parse(lockfile.read_text())
    # Normalize key ordering for fair comparison (dict equality is order-independent).
    assert handrolled_out == pyarn_out
```

Confirm both tests fail (corpus doesn't exist yet → no fixtures to parametrize). Commit red.

### Green — make it pass

1. Land the four fixture lockfiles + per-fixture READMEs under `tests/fixtures/_yarn_corpus/`.
2. Tests should now collect ≥ 4 fixtures and run on both parser paths.
3. If the oracle invariants catch a real bug in `_parse_handrolled` from S3-03, fix S3-03 — **do not relax the invariant** to make the test pass. Surface the fix in this PR's body as a callout: "uncovered bug in S3-03: …" so reviewers know S3-03's PR didn't catch it.
4. If `pyarn.parse` returns a structurally different `YarnLock` (e.g., flat `dict[str, version_info]` rather than `{entries: {...}}`), add a small adapter in `_yarn.parse()` to normalize **both** paths to the same shape. The adapter belongs in `_yarn.py`, not in the test.

### Refactor

- Extract `_entry_header_lines` into a `tests/unit/probes/_lockfiles/_oracle_helpers.py` module **only if** another test imports it. Single use → keep inline.
- The `@pytest.mark.parametrize` over `force_handrolled` doubles the test count; that's deliberate — it's the only way to exercise both code paths on the same fixture.
- Consider adding `hypothesis`-based property fuzzing (random byte mutations of a real `yarn.lock` constrained to still parse) — **defer to Phase 2** if the local fuzzing from S3-03 was thorough; the curated corpus + invariants are sufficient for Phase 1.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/_yarn_corpus/single_entry/yarn.lock` + `README.md` | New — minimal one-entry lockfile fixture. |
| `tests/fixtures/_yarn_corpus/multi_entry_with_deps/yarn.lock` + `README.md` | New — multi-entry with `dependencies` sub-block. |
| `tests/fixtures/_yarn_corpus/multi_spec_shared_header/yarn.lock` + `README.md` | New — comma-joined specifier-range fixture. |
| `tests/fixtures/_yarn_corpus/empty/yarn.lock` + `README.md` | New — comments-only fixture (zero entries; oracle invariant 3 tested at zero). |
| `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` | New — fixture-parity test (skipped without `pyarn`). |
| `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` | New — property-based oracle, three invariants, both parser paths. |

## Out of scope

- **Property-based fuzzing via `hypothesis`** — defer to Phase 2 if the curated corpus + S3-03's local fuzz are sufficient evidence.
- **Adversarial regex-DoS test** — S5-02 (lives under `tests/adv/`).
- **CI matrix configuration to ensure `pyarn` is installed on at least one job** — handled in the Phase 0 `pyproject.toml` extras shape; check that `gather` extras are installed on the relevant CI matrix job, surface as a PR comment if missing.
- **`pyarn` adapter** if its output shape differs — landed in S3-03 if discovered there; this story does not modify `_yarn.parse()` beyond the bug-fix path described above.

## Notes for the implementer

- **The mutation experiment is required.** Verifying that a known-bad parser change fails the tests is the only way to know the invariants have teeth. Skipping it means the tests are decoration, per global Rule 9 (Tests verify intent, not just behavior).
- The `force_handrolled` parametrize is the load-bearing trick — without it, the oracle only exercises whichever parser `_HAS_PYARN` happens to select on this machine, and the CI matrix on a different machine could give different coverage.
- Invariant 2 (version locality) is the fuzziest of the three; the simplest implementation is "for each entry, look for the version string within ±5 lines of the entry header." That's good enough for Phase 1; tightening to "exact match on the indented `version` line" risks false positives on legitimately weird lockfile layouts.
- Per-fixture README content: state the lockfile's intended characteristics (entry count, native modules present, shared-header presence) so the oracle's "this fixture pins invariant N" linkage is searchable.
- The empty-fixture (zero entries) is **not** redundant — it pins invariant 3 at the boundary. Without it, a parser that always emits one phantom entry would pass invariants 1 and 2 trivially.
- If you find yourself wanting to assert `len(result["entries"]) > 0` as an invariant, **don't** — the empty fixture would fail it. Invariants are over the data; non-emptiness is a fixture property.
- Per `High-level-impl.md §"Implementation-level risks"` #4, the regex-DoS adversarial test is S5-02's job, not this story's. Keep the corpus to well-formed lockfiles; pathological inputs go in `tests/adv/`.
