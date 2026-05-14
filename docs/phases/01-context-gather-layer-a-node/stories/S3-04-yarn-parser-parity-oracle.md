# Story S3-04 — Yarn parser parity + property-based oracle tests (Gap 3)

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Done (2026-05-14)
**Effort:** M
**Validated:** 2026-05-14 — see `_validation/S3-04-yarn-parser-parity-oracle.md`
**Depends on:** S3-03 (`_yarn.py` exists with `_HAS_PYARN` dispatch + hand-rolled scanner)
**ADRs honored:** ADR-0003 (the parity test that protects either land-time selection)

## Validation notes (2026-05-14)

Six findings applied by `phase-story-validator` — every one is `harden`, none `block`. Rationale logged in `_validation/S3-04-yarn-parser-parity-oracle.md`:

1. **AC-3 / AC-5 / AC-7 — parity & oracle tests go through `_yarn.parse(path)`, not the raw parser internals.** Calling `_yarn._parse_handrolled(bytes)` or `pyarn.parse(text)` directly bypasses the `open_capped` size-cap defense (S3-03 AC-3) and any future `_pyarn_parse` adapter. Both branches must exercise the public `parse(path)` entrypoint with `_HAS_PYARN` swapped via `monkeypatch.setattr`. This also closes a hidden divergence: the parity test was comparing apples (raw `pyarn` lib output) to oranges (adapted `_parse_handrolled` output); after the edit, both sides are post-adapter `YarnLock` dicts.
2. **AC-13 (new) — automated mutation self-check.** The "verify locally then write a PR-body paragraph" instruction was documentation, not a regression test. Promoted to a `test_oracle_self_check.py` module that synthesizes a *known-bad* `YarnLock` from a real fixture (e.g., renames an entry, drops a version, invents a phantom entry) and asserts every invariant flags it. This makes mutation-resistance a CI gate per global Rule 9.
3. **AC-11 (Invariant 1 strengthened) — anchored substring check, not raw `name in body`.** A wrong parser that invents `"lodash"` passes against a body containing `"lodash-es"` (false-negative). The hardened check requires the name appears bracketed in a yarn-classic locator context: either `f'"{name}@'`, `f", {name}@"`, or `f"\n{name}@"` (start-of-entry-header positions). Word-boundary anchoring lifts the invariant from "the parser didn't invent the universe" to "the parser saw an entry-header for this name."
4. **AC-13 (was AC-9) — mutation experiment AC reworded to point at the automated self-check, not a PR-body paragraph.** The original AC was unverifiable from CI logs; the rewritten AC asserts the self-check module exists and runs green.
5. **Path consistency with ADR-0003.** ADR-0003 §"Consequences" names `tests/unit/probes/test_yarn_parser_oracle.py`; this story uses `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` (sibling to the parsers). Documented in Notes §6 — the story-path is preferred (it co-locates parser tests with the parser package); the ADR can be amended in a follow-on if a reviewer flags drift.
6. **Empty-fixture documentation.** Invariant 2 is vacuously satisfied on the empty fixture (zero entries iterate zero times). Each fixture's README must state *which invariants it pins non-trivially*, so a reader can tell that the empty fixture pins invariant 3 but not 1 or 2. Pure documentation hardening; no AC change beyond a README-content clause.

Design-pattern review: the invariant set is extensible by addition (each new invariant is a new `def test_oracle_invariant_N_*` function with no edits to existing tests); the corpus pattern is extensible by addition (each new fixture is a new directory); the `force_handrolled` parametrize is the minimum viable strategy-coverage device for the current two-strategy world (rule of three not yet reached — per CLAUDE.md "Extension by addition" and Rule 2, no kernel/registry refactor proposed). Recorded in Notes §10.

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

- [x] **AC-1.** `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` runs *the public* `_yarn.parse(path)` entrypoint against every fixture under `tests/fixtures/_yarn_corpus/` **twice** — once with `_HAS_PYARN` left at its detected value, once with `monkeypatch.setattr(_yarn, "_HAS_PYARN", False)` — and asserts the two `YarnLock` dicts are equal. The test does **not** call `pyarn` directly and does **not** call `_yarn._parse_handrolled` directly — both invocations go through `_yarn.parse(path)` so the `open_capped` size-cap (S3-03 AC-3) and the `_pyarn_parse` adapter (S3-03 AC-13) are exercised on both sides.
- [x] **AC-2.** When `_HAS_PYARN` is `False` at module import (i.e., `pyarn` is not installed), `test_yarn_parser_parity.py` `pytest.skip`s the entire module with a clear reason (`pyarn not installed; parity test requires both parsers`); CI matrix has **at least one job with `pyarn` installed** so the parity test exercises in CI.
- [x] **AC-3.** `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` defines ≥ 3 invariants and asserts each on every fixture in `tests/fixtures/_yarn_corpus/`, exercising **both** parser paths via `force_handrolled ∈ {True, False}` parametrize that drives `monkeypatch.setattr(_yarn, "_HAS_PYARN", ...)`. The oracle test always calls `_yarn.parse(path)` — never the parser internals — so the `force_handrolled=False` arm also exercises any future `_pyarn_parse` adapter.
- [x] **AC-4 (Invariant 1, anchored).** For every entry name in parser output, the name appears in the lockfile bytes in at least one of three **start-of-locator** positions: `f'"{name}@'`, `f", {name}@"`, or `f"\n{name}@"`. A bare substring match is **insufficient** — that lets a parser that invents `"lodash"` pass against a body containing only `"lodash-es"`. Scoped packages (`@types/foo`) follow the same rule (the name string includes the leading `@`).
- [x] **AC-5 (Invariant 2, version locality).** For every `version` field in parser output, that version string appears in the lockfile bytes within ±5 lines of the matching entry header (located by the AC-4 anchor positions). The locality window is acknowledged-fuzzy and lives in `Notes §3`; it is good enough for Phase 1.
- [x] **AC-6 (Invariant 3, count parity).** Number of entries in parser output equals the count of lines in the lockfile bytes that match the entry-header shape: no leading whitespace, ending with `:`, not a comment, not the yarn `# yarn lockfile vN` banner or the `__metadata:` block-header. Helper `_entry_header_lines(body: str) -> list[str]` is typed, named, ≤ 12 LOC.
- [x] **AC-7.** `tests/fixtures/_yarn_corpus/` contains ≥ 4 curated `yarn.lock` files: (a) `single_entry/` — minimal one-entry; (b) `multi_entry_with_deps/` — multi-entry with `dependencies:` sub-blocks; (c) `multi_spec_shared_header/` — comma-joined specifier-range header (`"foo@^1, foo@^2":`); (d) `empty/` — comments-only, zero entries.
- [x] **AC-8.** Each fixture has a `README.md` next to it stating (i) what shape it exercises, (ii) which invariants it pins **non-trivially** (e.g., the empty fixture pins invariant 3 at the zero-boundary; invariants 1 and 2 are vacuously satisfied — README must say so), and (iii) entry count / native-modules-present / shared-header-presence so the oracle's fixture-to-invariant linkage is grep-able.
- [x] **AC-9.** `tests/unit/probes/_lockfiles/test_yarn_parser_oracle_self_check.py` exists and contains ≥ 3 *automated* mutation cases: each case takes a real fixture's parsed `YarnLock` output, applies a known-bad transform (e.g., (i) rename one entry's name to a string absent from the lockfile bytes; (ii) replace one entry's `version` with a string absent from the lockfile bytes; (iii) drop one entry from the dict so the count diverges from header-line count), and asserts that the corresponding invariant raises `AssertionError` when checked against the original body. This is the **CI-enforced mutation experiment** — replaces the prior "verify locally + PR-body paragraph" pattern. Per global Rule 9.
- [x] **AC-10.** Invariant checks are exposed as small typed helper functions in `test_yarn_parser_oracle.py` — `def _check_invariant_1(result: YarnLock, body: str) -> None`, `_check_invariant_2`, `_check_invariant_3`. Each helper raises `AssertionError` on violation (using `assert` so pytest's introspection fires). The self-check module imports these helpers so a single source of truth defines each invariant.
- [x] **AC-11.** `ruff format --check`, `ruff check`, `mypy --strict`, and `pytest` all pass.
- [x] **AC-12.** The PR body documents (a) which `pyarn` API surface the test exercises (cross-link to S3-03's land-time selection note in ADR-0003), and (b) the path-of-record deviation from ADR-0003 §"Consequences" (story uses `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py`; ADR named `tests/unit/probes/test_yarn_parser_oracle.py` — story-path is preferred for co-location, and the ADR can be amended in a follow-on if a reviewer flags drift).

## Implementation outline

1. **Land the fixture corpus first**: create `tests/fixtures/_yarn_corpus/` with the four curated `yarn.lock` files. Each lockfile is real-shaped — derive from `tests/fixtures/node_yarn_legacy/` (S3-06) or synthesize from a known package set. Add a `README.md` per fixture (per AC-8: shape, invariants pinned non-trivially, counts).
2. **Implement the invariant helpers** as small typed module-level functions in `test_yarn_parser_oracle.py`: `_check_invariant_1(result, body)`, `_check_invariant_2(result, body)`, `_check_invariant_3(result, body)`. Each ≤ 12 LOC, each raises `AssertionError` on violation. Plus the `_entry_header_lines(body)` helper used by invariant 3. **No extraction to `src/`** — test-only logic.
3. **Parity test**: parametrize over the corpus. For each fixture, call `_yarn.parse(lockfile)` once with the detected `_HAS_PYARN` and once after `monkeypatch.setattr(_yarn, "_HAS_PYARN", False)`. Compare the two `YarnLock` dicts via direct equality. `pytest.mark.skipif(not _yarn._HAS_PYARN, ...)` skips the whole module when `pyarn` is absent (per AC-2). **Do not import `pyarn` directly in the test**; let `_yarn.parse` dispatch.
4. **Oracle test**: parametrize over the corpus AND over `force_handrolled ∈ {True, False}`. When `force_handrolled=True`, `monkeypatch.setattr(_yarn, "_HAS_PYARN", False)`. Always call `_yarn.parse(lockfile)`. Then call all three `_check_invariant_*` helpers.
5. **Self-check module** (`test_yarn_parser_oracle_self_check.py`): import the `_check_invariant_*` helpers from the oracle module. Parametrize over the corpus. For each fixture, parse to get a real `YarnLock`, then apply three known-bad transforms (rename, version-swap, drop-entry — each a small typed mutator) and assert each helper raises `AssertionError` on the bad input *but not* on the original input. This is AC-9; the mutation experiment becomes CI green.
6. **Per-fixture README content**: per AC-8 — state shape, entry count, native-modules-presence, shared-header-presence, and **which invariants this fixture pins non-trivially**. Empty fixture: "pins invariant 3 at zero; invariants 1 and 2 are vacuously satisfied."

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` (start with the oracle — it's the more general defense).

```python
# tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn
from codegenie.probes._lockfiles._yarn import YarnLock

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))


def _entry_header_lines(body: str) -> list[str]:
    """Header lines: column-0 start, end with ':', skip comments and the
    `__metadata:` block-header (yarn berry sentinel)."""
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") or line.startswith(" "):
            continue
        if line == "__metadata:":
            continue
        if line.endswith(":"):
            out.append(line[:-1])
    return out


def _name_appears_anchored(name: str, body: str) -> bool:
    """Invariant 1: name must appear at a start-of-locator position so a
    parser that invents `lodash` against a body of `lodash-es` is caught.
    """
    return (
        f'"{name}@' in body
        or f", {name}@" in body
        or f"\n{name}@" in body
        or body.startswith(f"{name}@")  # rare: first line of corpus is bare-locator
    )


def _check_invariant_1(result: YarnLock, body: str) -> None:
    for entry_key in result.get("entries", {}):
        for spec in entry_key.split(", "):
            name = spec.rsplit("@", 1)[0].strip('"')
            assert _name_appears_anchored(name, body), (
                f"parser invented entry {name!r} — not anchored in lockfile bytes"
            )


def _check_invariant_2(result: YarnLock, body: str) -> None:
    lines = body.splitlines()
    for entry_key, entry in result.get("entries", {}).items():
        version = entry.get("version")
        if not version:
            continue
        first_spec = entry_key.split(", ", 1)[0].strip('"')
        name = first_spec.rsplit("@", 1)[0]
        header_idx = next(
            (i for i, line in enumerate(lines) if name in line and line.rstrip().endswith(":")),
            None,
        )
        assert header_idx is not None, f"header for {name!r} not found"
        window = "\n".join(lines[max(0, header_idx - 5) : header_idx + 6])
        assert version in window, (
            f"version {version!r} for {name!r} not within ±5 lines of header"
        )


def _check_invariant_3(result: YarnLock, body: str) -> None:
    assert len(result.get("entries", {})) == len(_entry_header_lines(body)), (
        "entry count diverges from entry-header line count"
    )


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("force_handrolled", [True, False])
def test_oracle_invariants_hold_on_corpus(
    lockfile: Path, force_handrolled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if force_handrolled:
        monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    body = lockfile.read_text()
    result = _yarn.parse(lockfile)
    _check_invariant_1(result, body)
    _check_invariant_2(result, body)
    _check_invariant_3(result, body)
```

Then the parity test:

```python
# tests/unit/probes/_lockfiles/test_yarn_parser_parity.py
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))

pytestmark = pytest.mark.skipif(
    not _yarn._HAS_PYARN,
    reason="pyarn not installed; parity test requires both parsers",
)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_pyarn_and_handrolled_paths_produce_identical_yarnlock(
    lockfile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both invocations go through the public _yarn.parse() so open_capped
    # and any _pyarn_parse adapter (S3-03) are exercised on both sides.
    pyarn_path_out = _yarn.parse(lockfile)
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    handrolled_out = _yarn.parse(lockfile)
    assert pyarn_path_out == handrolled_out
```

And the self-check (AC-9):

```python
# tests/unit/probes/_lockfiles/test_yarn_parser_oracle_self_check.py
"""Mutation-resistance gate. The oracle invariants are decoration unless
they catch obviously-wrong parser output; this module proves they do."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn
from codegenie.probes._lockfiles._yarn import YarnLock
from tests.unit.probes._lockfiles.test_yarn_parser_oracle import (
    _check_invariant_1,
    _check_invariant_2,
    _check_invariant_3,
)

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
# Self-check runs on fixtures that have ≥ 1 entry — the empty fixture has
# nothing to mutate; that case is covered by the oracle test's zero-arm.
LOCKFILES = [p for p in sorted(CORPUS_DIR.glob("*/yarn.lock")) if p.parent.name != "empty"]


def _mutate_invent_name(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    first_key = next(iter(entries))
    entries["zzz_phantom_pkg_definitely_not_in_lockfile@^9.9.9"] = entries.pop(first_key)
    return out


def _mutate_bad_version(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    first = entries[next(iter(entries))]
    first["version"] = "999.999.999-not-in-lockfile"
    return out


def _mutate_drop_entry(result: YarnLock) -> YarnLock:
    out = copy.deepcopy(result)
    entries = out.get("entries", {})
    entries.pop(next(iter(entries)))
    return out


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_1_catches_invented_name(lockfile: Path) -> None:
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_1(real, body)  # baseline: clean parse passes
    with pytest.raises(AssertionError):
        _check_invariant_1(_mutate_invent_name(real), body)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_2_catches_bad_version(lockfile: Path) -> None:
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_2(real, body)
    with pytest.raises(AssertionError):
        _check_invariant_2(_mutate_bad_version(real), body)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_invariant_3_catches_dropped_entry(lockfile: Path) -> None:
    body = lockfile.read_text()
    real = _yarn.parse(lockfile)
    _check_invariant_3(real, body)
    with pytest.raises(AssertionError):
        _check_invariant_3(_mutate_drop_entry(real), body)
```

Confirm all three test modules fail (corpus doesn't exist yet → no fixtures to parametrize, or `_check_invariant_*` helpers not yet imported). Commit red.

### Green — make it pass

1. Land the four fixture lockfiles + per-fixture READMEs under `tests/fixtures/_yarn_corpus/` per AC-7 / AC-8.
2. The oracle, parity, and self-check modules should now collect ≥ 4 (oracle/parity) / ≥ 3 (self-check, excluding the empty fixture) fixtures.
3. If the oracle invariants catch a real bug in `_parse_handrolled` from S3-03, **fix S3-03** — do not relax the invariant. Surface the fix in this PR's body as a callout ("uncovered bug in S3-03: …") so reviewers know S3-03's PR didn't catch it.
4. If `_yarn.parse()` from S3-03 already includes the `_pyarn_parse` adapter that normalizes pyarn's output to `YarnLock`, no test change needed. If the adapter is missing and `pyarn`'s native output diverges, **the fix lives in `_yarn.py`** (not the test) — S3-03 AC-13 already mandates the adapter; surface as a callback to S3-03.

### Refactor

- The `_check_invariant_*` and `_entry_header_lines` helpers stay inline in `test_yarn_parser_oracle.py`. The self-check module imports them — that's **one** cross-module use, which is the rule-of-two threshold; the helpers stay where they are (extraction at three consumers per Rule 2). If a future test module also imports them, extract to `tests/unit/probes/_lockfiles/_oracle_helpers.py` at that point.
- The `force_handrolled` parametrize doubles the oracle test count; that's deliberate — it's the only way to exercise both code paths on the same fixture under both `_HAS_PYARN` states. The doubling is bounded by `2 × len(LOCKFILES)` and acceptable.
- `hypothesis`-based property fuzzing (random byte mutations constrained to still parse) is **deferred to Phase 2**. The curated corpus + three invariants + the CI-enforced self-check (AC-9) is the Phase 1 bar; bytes-level fuzzing belongs alongside adversarial parser caps in S5-01 / S5-02. Recorded in Notes §7.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/_yarn_corpus/single_entry/yarn.lock` + `README.md` | New — minimal one-entry lockfile fixture. |
| `tests/fixtures/_yarn_corpus/multi_entry_with_deps/yarn.lock` + `README.md` | New — multi-entry with `dependencies` sub-block. |
| `tests/fixtures/_yarn_corpus/multi_spec_shared_header/yarn.lock` + `README.md` | New — comma-joined specifier-range fixture. |
| `tests/fixtures/_yarn_corpus/empty/yarn.lock` + `README.md` | New — comments-only fixture (zero entries; oracle invariant 3 tested at zero). |
| `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` | New — parity test; both branches go through `_yarn.parse(path)` with `_HAS_PYARN` monkeypatched. |
| `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py` | New — property-based oracle, three invariants, both parser paths via `force_handrolled` parametrize. Hosts the `_check_invariant_*` helpers. |
| `tests/unit/probes/_lockfiles/test_yarn_parser_oracle_self_check.py` | New (AC-9) — CI-enforced mutation experiment; imports the `_check_invariant_*` helpers and asserts each one rejects three known-bad transforms. |

## Out of scope

- **Property-based fuzzing via `hypothesis`** — defer to Phase 2 if the curated corpus + S3-03's local fuzz are sufficient evidence.
- **Adversarial regex-DoS test** — S5-02 (lives under `tests/adv/`).
- **CI matrix configuration to ensure `pyarn` is installed on at least one job** — handled in the Phase 0 `pyproject.toml` extras shape; check that `gather` extras are installed on the relevant CI matrix job, surface as a PR comment if missing.
- **`pyarn` adapter** if its output shape differs — landed in S3-03 if discovered there; this story does not modify `_yarn.parse()` beyond the bug-fix path described above.

## Notes for the implementer

1. **The mutation experiment is automated** (AC-9). The prior pattern ("verify locally + paragraph in PR body") was unverifiable from CI logs — per global Rule 9 (tests verify intent, not just behavior), the self-check module makes mutation-resistance a green-or-red CI signal. Three transforms cover the three invariants; adding a fourth invariant later means adding a fourth mutator + a fourth `test_invariant_N_catches_*` function — extension by addition.
2. **`force_handrolled` is the load-bearing parametrize trick.** Without it, the oracle only exercises whichever parser `_HAS_PYARN` selects on this machine, and the CI matrix on a different machine could give different coverage. The monkeypatch swap is the minimum viable strategy-coverage device for the two-strategy world; if a third parser strategy enters in some future phase (rule of three), this is the natural point to refactor to a strategy registry — but **not before**, per Rule 2.
3. **Invariant 2 (version locality) is the fuzziest of the three.** The ±5-line window is acknowledged-fuzzy; it's good enough for Phase 1. Tightening to "exact match on the indented `version:` line" risks false positives on legitimately weird lockfile layouts (yarn berry's `version: ` may use different indentation). Tightening is a Phase 2 candidate if a real bug slips through.
4. **Invariant 1 anchoring matters.** The original draft used a bare `name in body` substring check; that lets a parser invent `lodash` against a body containing `lodash-es` (silent false negative). AC-4 mandates start-of-locator-position anchoring (`"name@`, `, name@`, `\nname@`). The cost is brittleness to yarn format variants that use different quoting; if a yarn-berry fixture surfaces a new locator shape, **add a new anchor position, do not drop anchoring**.
5. **Per-fixture README content**: state shape, entry count, native-modules-presence, shared-header-presence, and **which invariants this fixture pins non-trivially**. Example for `empty/`: "Pins invariant 3 at zero; invariants 1 and 2 are vacuously satisfied (the iteration is empty)."
6. **Path-of-record deviation.** ADR-0003 §"Consequences" names `tests/unit/probes/test_yarn_parser_oracle.py`; this story uses `tests/unit/probes/_lockfiles/test_yarn_parser_oracle.py`. The story path is preferred — it co-locates parser tests with the `_lockfiles/` package mirror, matching the layout S3-01..S3-03 established for `test_pnpm_parser.py`, `test_npm_parser.py`, `test_yarn_parser.py`. If a reviewer flags ADR-vs-story drift, amend ADR-0003 §"Consequences" to point at the `_lockfiles/` path; that's a one-line ADR edit, not a story-rewrite.
7. **No `hypothesis` in this story.** AC-9's self-check is the targeted mutation gate; bytes-level random fuzzing belongs in S5-01 / S5-02 (adversarial parser caps). Keep the corpus to well-formed lockfiles; pathological inputs go in `tests/adv/`.
8. **The empty-fixture (zero entries) is not redundant** — it pins invariant 3 at the zero-boundary. Without it, a parser that always emits one phantom entry would pass invariants 1 and 2 trivially on every non-empty fixture. The empty fixture is excluded from the `test_oracle_self_check` module because there's nothing to mutate; that's intentional and documented in `_yarn_corpus/empty/README.md`.
9. **Do not assert `len(result["entries"]) > 0` as an invariant.** The empty fixture would fail it. Invariants are over the data; non-emptiness is a fixture property.
10. **Design-pattern review (recorded for future stories).** This story's shape is already aligned with three of the codebase's load-bearing patterns: (a) **extension by addition** — adding a new invariant is `def _check_invariant_N + test_invariant_N_catches_*`, zero edits to existing tests; (b) **functional core / imperative shell** — `_check_invariant_*` helpers are pure functions over `(YarnLock, str)`; the only imperative shell is the `_yarn.parse()` call site; (c) **strategy coverage** — the `force_handrolled` parametrize is the minimum viable two-strategy probe. No refactor to a registry/plugin shape is proposed at this scale (rule of three not yet reached, per CLAUDE.md "Extension by addition" and Rule 2). If a third lockfile-parser strategy (e.g., yarn-berry) lands in a future phase, that's the right moment to extract a `_check_invariants` capability registry — not now.
