# Story S1-11 — `forbidden-patterns` extension + `mypy --warn-unreachable` verification + nine ADRs

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Done (GREEN 2026-05-15, all 15 ACs satisfied — see `_attempts/S1-11.md`)
**Effort:** M
**Depends on:** S1-01, S1-02, S1-03, S1-04, S1-09, S1-10
**ADRs honored:** 02-ADR-0001 through 02-ADR-0009 (the **nine** Step-1 ADRs; 02-ADR-0010 file already exists in the tree but its enforcement code lands in S3-02 — see AC-11 lock)

## Validation notes (2026-05-15)

This story was hardened by the `phase-story-validator` skill. Two ground-truth shifts were absorbed against the original draft:

1. **`warn_unreachable = true` is already set REPO-WIDE in `pyproject.toml` [tool.mypy].** Committed in Phase 0 S1-02 (commit `3944f02`, 2026-05-13) — months before this story was written. The original draft prescribed adding *per-module* overrides; that work is already done at broader-than-arch scope. The story's mypy work collapses to **verification + an automated exhaustiveness fixture test**. The arch's per-module prescription (`phase-arch-design.md §"CI gates"` job 7) is the *narrower* target; Phase 0 deliberately went broader (the original `[tool.mypy]` comment names the rationale). The deviation is logged here, not silently reversed — narrowing scope is an S8-04 backlog decision, not a Step-1 surgical edit.
2. **02-ADR-0010 file already exists** under `ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`. AC-11's two-option punt is resolved: **the Step-1 nine are 0001–0009**; the 0010 file's pre-existing presence is tolerated (`docs/phases/02-context-gather-layers-b-g/README.md` lists it under a "Step-3 land" sub-bullet); its *enforcement code* (`RedactedSlice`) still ships in S3-02 per the dependency DAG.

Other harden-tier edits applied:

- Test script path corrected (`scripts/check_forbidden_patterns.py`, not `forbidden_patterns.py`).
- The error-message contract tightened from `or` to `and`: both `ADR-0010` AND `ADR-0033` substrings must appear (AC-1, AC-2 tests).
- Mutation-resistance tests added for the `model_construct` regex (instance-call, class-call, kwarg-style — each form is parametrized).
- Phase-0 regression test added: the existing 11 forbidden-patterns rules must still fire after the loop refactor (no silent truncation).
- Nygard-section check expanded from 5 sections to 8 (every ADR in this phase already conforms — verified across `0001`, `0006`, `0009`, `0010`).
- AC-7 reframed from VERIFY to WRITE: the Phase 2 README does not currently list any ADRs (verified at validation time); this story adds the section.
- Open/Closed structural commitment elevated to AC: the `_RULES` table refactor (rule-of-three threshold; literal-pattern + regex-pattern + path-scoped-regex-pattern are now three rule kinds) must support new path-scoped rules with **zero edits** to `_scan_file()` / `main()`. Pinned via a structural test.

Verdict from validator: **HARDENED**. See `_validation/S1-11-forbidden-patterns-mypy-adrs.md` for the full audit.

## Context

The nine new ADRs (0001–0009) document irreversible (or hard-to-reverse) Phase 2 commitments; they MUST land *with* the code that enforces them. This story finalizes Step 1 by (a) extending Phase 0's `forbidden-patterns` pre-commit hook to ban `model_construct` under the seven new Phase 2 packages (closing the smart-constructor escape hatch the architect's anti-patterns row 12 names) — refactored to make any future path-scoped rule a one-line addition; (b) **verifying** the already-repo-wide `mypy warn_unreachable = true` is honored end-to-end by adding an automated fixture-based exhaustiveness test (the arch prescribed per-module rollout, but Phase 0 S1-02 went broader; this story does *not* narrow — see Validation notes); and (c) confirming all nine Step-1 ADR files exist, are Nygard-format, and are linked from `docs/phases/02-context-gather-layers-b-g/README.md` (currently no ADR-listing section exists — this story adds it).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Anti-patterns avoided"` row 12 — `model_construct()` bypass; Phase 0's `forbidden-patterns` pre-commit (extended here) bans it under the new packages.
  - `../phase-arch-design.md §"Open questions deferred to implementation"` #5 — `mypy --warn-unreachable` rollout policy: per-module only in Phase 2; full-repo rollout is a tracked backlog item (S8-04 files the issue).
  - `../phase-arch-design.md §"Path to production end state"` — nine-ADR table with one-line records (the source of truth for the nine ADRs that must exist).
  - `../phase-arch-design.md §"CI gates"` job 7 (`mypy`) — `mypy --strict` repo-wide + `--warn-unreachable` per-module overrides.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — 02-ADR-0001
  - `../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md` — 02-ADR-0002
  - `../ADRs/0003-coordinator-heaviness-sort-annotation.md` — 02-ADR-0003
  - `../ADRs/0004-image-digest-as-declared-input-token.md` — 02-ADR-0004
  - `../ADRs/0005-secret-findings-no-plaintext-persistence.md` — 02-ADR-0005
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — 02-ADR-0007
  - `../ADRs/0008-no-event-stream-in-phase-2.md` — 02-ADR-0008
  - `../ADRs/0009-pytest-xdist-veto-preserved.md` — 02-ADR-0009
  - `../ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md` — 02-ADR-0010 (the smart-constructor *code* lands in S3-02; the ADR is among the Step-1 nine — note: the manifest says "nine ADRs land in Step 1"; the README counts ten ADR files. Reconcile: Step 1 lands the **nine** Step-1 ADRs (0001–0009); 0010 ships in Step 3 alongside S3-02 unless the README dates show it already drafted — verify and adjust the list).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0033-typed-identifiers.md` — production ADR-0033 — the binding discipline for the newtypes S1-05 ships.
- **Source design:**
  - `../final-design.md §"Open Q 5"` — per-module rollout policy.
- **Existing code (verified at validation time, 2026-05-15):**
  - `scripts/check_forbidden_patterns.py` — the actual Phase 0 script (NOT `scripts/forbidden_patterns.py`). 11 rules in a flat `_RULES: list[tuple[str, Pattern[str], str]]`; no path-scoping mechanism today; scoping is done at the pre-commit `files:`/`exclude:` level. This story refactors `_RULES` into a small `Rule` dataclass with `applies_when: Callable[[Path], bool]` to add path-scoping without procedural branches in the loop (rule-of-three threshold reached — see AC-15).
  - `pyproject.toml` `[tool.mypy] warn_unreachable = true` (line 134) — **already enabled repo-wide by Phase 0 S1-02** (commit `3944f02`, 2026-05-13). This story does NOT add `[[tool.mypy.overrides]]` blocks (would be redundant); it adds the automated fixture-based exhaustiveness test the arch hand-waved.
  - `.pre-commit-config.yaml` lines 67-87 — the `forbidden-patterns` hook entry; `entry: scripts/check_forbidden_patterns.py`; `files: '\.py$'`; `exclude: '^(tests/|scripts/|tools/)'`. Path-scoping for the new rule MUST live in the script (so the test exercises the right surface), not in this YAML.
  - `tests/unit/indices/test_freshness.py` lines 113-149 — already exercises `assert_never` over `IndexFreshness`. The fixture-based mypy exhaustiveness test in this story complements (not duplicates) that runtime test.
- **External docs (only if directly relevant):**
  - https://mypy.readthedocs.io/en/stable/config_file.html#per-module-and-global-options — `warn_unreachable` per-module override.

## Goal

(1) Extend Phase 0's `forbidden-patterns` pre-commit hook to ban `model_construct` under `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph,output}/**` — **refactoring the rule loop to make path-scoping a first-class predicate** (Open/Closed; adding a future path-scoped rule must require zero edits to `_scan_file()`/`main()`); (2) **verify** the already-repo-wide `mypy warn_unreachable = true` works end-to-end via an automated fixture-based exhaustiveness test (Phase 0 S1-02 enabled `warn_unreachable` repo-wide — broader-than-arch — see Validation notes; this story does not narrow); (3) verify the nine Step-1 ADR files (0001–0009) exist, are 8-section-Nygard-format, and are listed in `docs/phases/02-context-gather-layers-b-g/README.md` (currently no ADR-listing section — this story adds it).

## Acceptance criteria

- [x] **AC-1.** `scripts/check_forbidden_patterns.py` is extended with a new rule that fires when a `.py` file *under* `src/codegenie/{indices,tccm,skills,conventions,adapters,depgraph,output}/**` matches the regex `\.model_construct\s*\(|\bmodel_construct\s*=` (the exact `re.compile` source must appear verbatim in `_RULES`). The rule's `advice` field MUST contain BOTH the substring `02-ADR-0010 §Decision` AND the substring `production ADR-0033 §3` (the contract is `and`, not `or` — both names appear in every emitted error line). Path scoping lives **inside the script** via the rule's `applies_when` predicate, NOT in `.pre-commit-config.yaml`'s `files:`/`exclude:` regex, so the test surface and the runtime surface are the same.
- [x] **AC-2.** *Positive coverage of the ban surface*, parametrized over `(package, source_form)`:
  - `package ∈ {indices, tccm, skills, conventions, adapters, depgraph, output}` (7 packages)
  - `source_form ∈ {"class_call": "Foo.model_construct(x=1)", "instance_call": "foo.model_construct(x=1)", "kwarg": "Bar(model_construct=lambda **kw: None)", "renamed_class": "MyModel.model_construct()"}` (4 mutation-resistance forms)
  - For each of the 28 combinations, a synthetic `.py` file written under `tmp_path/src/codegenie/{package}/synth.py`, fed to `scripts/check_forbidden_patterns.py` via `subprocess.run([sys.executable, "scripts/check_forbidden_patterns.py", str(target)], ...)`, MUST exit non-zero. Emitted stdout/stderr MUST contain BOTH `02-ADR-0010 §Decision` AND `production ADR-0033 §3` (assert both substrings — not `or`).
- [x] **AC-3.** *Negative coverage* (path-scoping is surgical): a synthetic `.py` file containing `Foo.model_construct(x=1)` written under `tmp_path/src/codegenie/probes/layer_a/synth.py` (Phase 1 — NOT in the banned package list) MUST exit zero from the script — proving the `applies_when` predicate is honored. Also covered: a synthetic `.py` file under `tmp_path/src/codegenie/indices/synth.py` containing the comment-only string `# .model_construct( is banned — see ADR-0010` is acceptable false-positive territory (regex is structural, not AST-precise) — this story documents the choice; the negative test pins `applies_when` discipline, not regex-precision.
- [x] **AC-4.** *Verification, not configuration* — `pyproject.toml [tool.mypy]` already has `warn_unreachable = true` repo-wide (set in Phase 0 S1-02, commit `3944f02`, line 134). This story:
  - ASSERTS `cfg["tool"]["mypy"]["warn_unreachable"] is True` (the repo-wide setting is preserved).
  - ASSERTS that NO `[[tool.mypy.overrides]]` block sets `warn_unreachable = false` for any of the five named modules (`codegenie.indices.*`, `codegenie.probes.layer_b.index_health`, `codegenie.report.*`, `codegenie.adapters.*`, `codegenie.tccm.*`) — i.e., the repo-wide setting is not silently weakened for them.
  - Adds NO new `[[tool.mypy.overrides]]` block (would be redundant — top-level already covers them).
  - The arch's per-module prescription (`phase-arch-design.md §"CI gates"` job 7) is the *narrower* target; Phase 0 went broader. Narrowing is an S8-04 backlog item, NOT a Step-1 surgical edit.
- [x] **AC-5.** *Automated exhaustiveness fixture test* (replaces the original draft's manual procedure). A fixture file `tests/fixtures/mypy_warn_unreachable/incomplete_match.py` is added containing a deliberately-incomplete `match` over `IndexFreshness` (omits one variant; the function ends with `assert_never(value)`). A new test `tests/unit/test_mypy_warn_unreachable_fixture.py::test_incomplete_match_fails_mypy_strict` invokes `subprocess.run([sys.executable, "-m", "mypy", "--strict", "<fixture>"], capture_output=True, text=True)` and asserts: (i) exit code != 0; (ii) stderr or stdout contains the substring `unreachable` OR `Argument 1 to "assert_never" has incompatible type`; (iii) the fixture's docstring names ADR-0006 §Consequences (the load-bearing arch invariant). The test is marked `@pytest.mark.slow` if mypy invocation walltime ≥ 2 s on CI; otherwise unmarked.
- [x] **AC-6.** All nine Step-1 ADR files exist under `docs/phases/02-context-gather-layers-b-g/ADRs/` (`0001` through `0009`). Each contains **all eight** Nygard sections: `## Context`, `## Options considered`, `## Decision`, `## Tradeoffs`, `## Pattern fit`, `## Consequences`, `## Reversibility`, `## Evidence / sources`. (Verified at validation time across `0001`, `0006`, `0009`, `0010` — all conform; the test pins all eight, not five.) Each ADR's header MUST contain the literal line `**Status:** Accepted` (otherwise a `Draft` ADR would pass).
- [x] **AC-7.** *Add ADR-listing section to README* (this is a WRITE, not VERIFY — `docs/phases/02-context-gather-layers-b-g/README.md` currently has NO ADR-listing section; verified at validation time, 2026-05-15). The new section MUST: (a) list each of the nine Step-1 ADRs (0001–0009) by filename + ADR ID + one-line title + `Accepted` status; (b) include 02-ADR-0010 under a clearly-marked "Pre-drafted; enforcement code lands in S3-02 (Step 3)" sub-bullet (since the file already exists); (c) be located after the existing "Reading order" section. A test asserts every ADR filename in `ADRs/` appears in the README at least once.
- [x] **AC-8.** A Step-1-completion smoke test: invoking `pytest tests/unit/{indices,adapters,tccm,types,depgraph,exec,probes}/` exits 0; every Step-1 story's test file is included.
- [x] **AC-9.** Phase 0 `fence` job (no `anthropic`/`openai`/`langgraph`/`httpx`/`requests`/`socket` import under `src/codegenie/`) stays green — verify by running the existing fence CI script against the post-Step-1 tree.
- [x] **AC-10.** Phase 0 `contract-freeze` job stays green — the only documented amendment is S1-09's `image_digest_resolver` field.
- [x] **AC-11.** **LOCKED** (validator removed ambiguity): the Step-1 ADR set is `{0001, 0002, 0003, 0004, 0005, 0006, 0007, 0008, 0009}`. 02-ADR-0010 file already exists in the ADRs/ directory (verified) — its presence is tolerated and documented in the README's "Pre-drafted" sub-bullet (per AC-7), but it is NOT in `REQUIRED_ADRS` for the existence test; its *enforcement code* (`RedactedSlice` smart constructor) ships in S3-02 per the dependency DAG. The test's `REQUIRED_ADRS` list stops at 0009. Adding 0010 to the existence test in any future story is an explicit decision — not silent extension.
- [x] **AC-12.** The TDD plan's red tests exist, were committed (as red — failing), and turned green after the green-stage edits.
- [x] **AC-13.** `ruff check`, `ruff format --check`, `mypy --strict` (repo-wide, which already includes `warn_unreachable = true`), `pre-commit run --all-files`, and `pytest` full suite all pass on the post-S1-11 tree.
- [x] **AC-14.** *Phase-0 regression invariant* — the existing 11 `_RULES` rows (the Phase-0 ADR-0008/0012 rules: `print(`, `yaml.load( without Loader=`, `shell=True`, `subprocess.run(..., shell=...)`, `yaml.Dumper`, `os.system(`, `os.popen(`, `pickle.loads(`, `eval(`, `exec(`, `__import__(`) still fire after the refactor. A dedicated test feeds a fixture file containing each banned construct to the script and asserts non-zero exit + the expected rule label appears in stdout. (Mutation guard: a refactor that silently truncated `_RULES` or replaced it with a different list would pass AC-1/AC-2 but fail AC-14.)
- [x] **AC-15.** *Open/Closed structural invariant* (rule-of-three threshold reached — `_RULES` now carries three rule kinds: literal-string regex, anchored regex, and path-scoped regex). The refactored `_RULES` row shape is a `Rule` dataclass (or `NamedTuple`) with at minimum the fields `label: str`, `pattern: Pattern[str]`, `advice: str`, `applies_when: Callable[[Path], bool] = lambda _p: True`. A dedicated test imports `_RULES` from `scripts.check_forbidden_patterns` and asserts: (i) every row has an `applies_when` callable (`assert callable(rule.applies_when)`); (ii) the Phase-2 `model_construct` rule's `applies_when` returns `True` for `Path("src/codegenie/indices/x.py")` and `False` for `Path("src/codegenie/probes/layer_a/x.py")`; (iii) the existing 11 Phase-0 rules' `applies_when` is the default-always predicate (verified by calling it with an arbitrary path and asserting `True`). This pins that adding a future path-scoped rule (e.g., a Phase-3 ban of `httpx` under `src/codegenie/plugins/`) requires only one new `Rule(...)` entry — zero edits to `_scan_file()` or `main()`.

## Implementation outline

1. **Read `scripts/check_forbidden_patterns.py`** (verified path; the original draft's `scripts/forbidden_patterns.py` is wrong). Inventory the current 11 `_RULES` rows; sketch the dataclass refactor target shape.
2. **Refactor `_RULES` row shape into a small `Rule` dataclass** (`@dataclass(frozen=True, slots=True)`) with `label: str`, `pattern: Pattern[str]`, `advice: str`, `applies_when: Callable[[Path], bool]` (default `lambda _p: True`). Update `_scan_file()` to call `rule.applies_when(path)` before iterating `pattern.finditer`. The 11 existing rows convert one-for-one with the default predicate; no behavioral change. (AC-14 + AC-15.)
3. **Add the Phase-2 path-scoped rule.** Append one new `Rule(...)` entry:
   ```python
   _PHASE2_BANNED_PACKAGES: frozenset[str] = frozenset({
       "indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output",
   })

   def _is_under_phase2_banned_package(path: Path) -> bool:
       parts = path.parts
       try:
           idx = parts.index("codegenie")
       except ValueError:
           return False
       return idx + 1 < len(parts) and parts[idx + 1] in _PHASE2_BANNED_PACKAGES

   # ... appended to _RULES:
   Rule(
       label="model_construct (Phase 2 packages)",
       pattern=re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*="),
       advice=(
           "02-ADR-0010 §Decision + production ADR-0033 §3 — smart constructors "
           "must be the only public path; use `from_validated_input(...)` or the "
           "public model factory."
       ),
       applies_when=_is_under_phase2_banned_package,
   ),
   ```
   `pathlib.Path.parts` is the OS-neutral check (do NOT regex against the full path string — Windows + symlinked checkouts trip you).
4. **`pyproject.toml` — NO EDITS** (verified at validation time: `[tool.mypy] warn_unreachable = true` is already present from Phase 0 S1-02, commit `3944f02`). Adding `[[tool.mypy.overrides]]` blocks with `warn_unreachable = true` for the five named modules would be redundant and would expand the YAML surface unnecessarily. The arch's per-module prescription is recorded as honored-broader-than-arch in `_validation/S1-11-…md`.
5. **Add the automated mypy fixture test (AC-5).** Create `tests/fixtures/mypy_warn_unreachable/incomplete_match.py` — a tiny module with a `match: IndexFreshness` that omits one variant and ends with `assert_never(value)`. Write `tests/unit/test_mypy_warn_unreachable_fixture.py` that subprocess-invokes mypy on it and asserts non-zero exit + the `unreachable`/`assert_never` diagnostic.
6. **Verify nine ADR files exist + 8-section Nygard format + Status: Accepted (AC-6).** Write `tests/unit/test_adr_inventory_phase2.py` with `REQUIRED_ADRS` = 0001–0009. The 0010 file's presence is tolerated by the test (not asserted; not forbidden).
7. **Add the README ADR-listing section (AC-7).** Insert after the existing "Reading order" section. List 0001–0009 under "Phase 2 ADRs (Step-1)"; list 0010 under a clearly-marked "Pre-drafted; enforcement code lands in S3-02 (Step 3)" sub-bullet.
8. **Write the structural test for AC-15** (Open/Closed): import `_RULES` from the script module (use `importlib.util.spec_from_file_location` since `scripts/` is not a package), iterate, assert every row has a callable `applies_when`. Pin the model_construct row's `applies_when` behavior on two probe paths.
9. **Refactor + green confirm.** Run `pre-commit run --all-files`, `mypy --strict src/codegenie/`, `pytest tests/`. The Phase-0 regression test (AC-14) is the cheapest correctness witness — run it first.

## TDD plan — red / green / refactor

### Red — write the failing tests first

**Test file 1**: `tests/unit/pre_commit/test_forbidden_patterns_phase2_extension.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


BANNED_PACKAGES = ("indices", "tccm", "skills", "conventions", "adapters", "depgraph", "output")
ALLOWED_PHASE0_PATHS = ("probes/layer_a",)  # Phase 1 — model_construct NOT banned here

# Mutation-resistance forms — a regex that only catches one of these would
# silently pass weaker tests. Each form is a real syntactic variant a future
# contributor could plausibly write.
SOURCE_FORMS = {
    "class_call":   "class Foo:\n    pass\nFoo.model_construct(x=1)\n",
    "instance_call": "class Foo:\n    pass\nfoo = Foo()\nfoo.model_construct(x=1)\n",
    "renamed_class": "class MyVerySpecificName:\n    pass\nMyVerySpecificName.model_construct()\n",
    "kwarg":         "def bar(model_construct=None): pass\n",
}

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_forbidden_patterns.py"


def _write_synth(tmp_path: Path, rel: str, body: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


@pytest.mark.parametrize("pkg", BANNED_PACKAGES)
@pytest.mark.parametrize("form_name,body", list(SOURCE_FORMS.items()))
def test_model_construct_banned_under_phase2_packages(
    tmp_path: Path, pkg: str, form_name: str, body: str
) -> None:
    """AC-1, AC-2 — every banned package × every source form must trip the hook.

    The 28-cell matrix (7 packages × 4 forms) is the mutation guard: weakening
    the regex (e.g. dropping `\bmodel_construct\s*=`) collapses one column
    instead of one cell."""
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth_{form_name}.py", body)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True, text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"hook must reject model_construct under {pkg} ({form_name}); got exit 0; output:\n{combined}"
    )
    # AC-1 contract is `and`, not `or` — both ADR identifiers in every emitted line.
    assert "02-ADR-0010 §Decision" in combined, f"missing 02-ADR-0010 §Decision in: {combined}"
    assert "production ADR-0033 §3" in combined, f"missing production ADR-0033 §3 in: {combined}"


@pytest.mark.parametrize("pkg", ALLOWED_PHASE0_PATHS)
def test_model_construct_NOT_banned_under_phase0_phase1_packages(tmp_path: Path, pkg: str) -> None:
    """AC-3 — surgical rollout discipline; the `applies_when` predicate is honored."""
    body = SOURCE_FORMS["class_call"]
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth.py", body)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True, text=True,
    )
    # Phase 0/1 retrofit is out of scope; the model_construct rule's
    # `applies_when` returns False here. (Other rules still apply — the
    # synth body contains no other banned constructs.)
    assert result.returncode == 0, (
        f"hook must NOT reject model_construct under {pkg} (Phase 0/1); got exit "
        f"{result.returncode}; output:\n{result.stdout}{result.stderr}"
    )


def test_existing_phase0_rules_still_fire(tmp_path: Path) -> None:
    """AC-14 — regression guard: refactoring `_RULES` row shape must not silently
    drop any of the 11 Phase-0 rules. Feed each banned construct in turn and
    assert the rule label appears in the output."""
    cases = {
        "print(":                "print('hello')\n",
        "yaml.load( without Loader=": "import yaml\nyaml.load('x:y')\n",
        "shell=True":            "import subprocess\nsubprocess.run('ls', shell=True)\n",
        "yaml.Dumper":           "import yaml\nyaml.dump({}, Dumper=yaml.Dumper)\n",
        "os.system(":            "import os\nos.system('ls')\n",
        "os.popen(":             "import os\nos.popen('ls')\n",
        "pickle.loads(":         "import pickle\npickle.loads(b'')\n",
        "eval(":                 "eval('1+1')\n",
        "exec(":                 "exec('pass')\n",
        "__import__(":           "__import__('os')\n",
    }
    for label, body in cases.items():
        target = _write_synth(tmp_path, f"src/codegenie/output/synth_{label[:6]}.py", body)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target)], capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, f"Phase-0 rule `{label}` no longer fires; output:\n{combined}"
        assert label in combined, f"Phase-0 rule `{label}` fired but its label is missing from output:\n{combined}"
```

**Test file 2**: `tests/unit/pre_commit/test_forbidden_patterns_rule_shape.py`

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_forbidden_patterns.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("_check_forbidden_patterns", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_rule_row_has_applies_when_callable() -> None:
    """AC-15 — Open/Closed. Every `_RULES` row must expose an `applies_when`
    callable. Adding a new path-scoped rule must require zero edits to
    `_scan_file()` or `main()` — only a new `Rule(...)` entry."""
    mod = _load_script_module()
    rules = mod._RULES
    assert len(rules) >= 12, f"expected at least 12 rules (11 Phase-0 + 1 Phase-2); got {len(rules)}"
    for rule in rules:
        assert callable(rule.applies_when), f"rule {rule.label!r} lacks callable applies_when"


def test_model_construct_rule_path_scoping() -> None:
    """AC-15 — the model_construct rule's `applies_when` is the SINGLE source of
    truth for path scoping. Pinned on representative paths."""
    mod = _load_script_module()
    rule = next(r for r in mod._RULES if "model_construct" in r.label)
    assert rule.applies_when(Path("src/codegenie/indices/freshness.py")) is True
    assert rule.applies_when(Path("src/codegenie/tccm/loader.py")) is True
    assert rule.applies_when(Path("src/codegenie/output/sanitizer.py")) is True
    assert rule.applies_when(Path("src/codegenie/probes/layer_a/foo.py")) is False
    assert rule.applies_when(Path("src/codegenie/cli.py")) is False
    assert rule.applies_when(Path("tests/unit/test_foo.py")) is False


def test_phase0_rules_use_default_always_predicate() -> None:
    """AC-15 — the 11 Phase-0 rules must remain repo-wide (default predicate
    returns True for any path), not silently scoped by the refactor."""
    mod = _load_script_module()
    arbitrary = Path("src/codegenie/anywhere/foo.py")
    phase0_labels = {
        "print(", "yaml.load( without Loader=", "shell=True",
        "subprocess.run(..., shell=...)", "yaml.Dumper", "os.system(",
        "os.popen(", "pickle.loads(", "eval(", "exec(", "__import__(",
    }
    for rule in mod._RULES:
        if rule.label in phase0_labels:
            assert rule.applies_when(arbitrary) is True, (
                f"Phase-0 rule {rule.label!r} silently scoped — must remain repo-wide"
            )
```

**Test file 3**: `tests/unit/test_adr_inventory_phase2.py`

```python
from __future__ import annotations
from pathlib import Path

import pytest


ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "phases" / "02-context-gather-layers-b-g" / "ADRs"
README = ADR_DIR.parent / "README.md"

# Step-1 nine — 0010 is intentionally excluded (file may exist; not required;
# enforcement code lands in S3-02 per AC-11 lock).
REQUIRED_ADRS = [
    "0001-add-docker-and-security-cli-tools-to-allowed-binaries.md",
    "0002-tree-sitter-grammars-phase-2-amendment.md",
    "0003-coordinator-heaviness-sort-annotation.md",
    "0004-image-digest-as-declared-input-token.md",
    "0005-secret-findings-no-plaintext-persistence.md",
    "0006-index-freshness-sum-type-location.md",
    "0007-no-plugin-loader-in-phase-2.md",
    "0008-no-event-stream-in-phase-2.md",
    "0009-pytest-xdist-veto-preserved.md",
]

NYGARD_SECTIONS = (
    "## Context",
    "## Options considered",
    "## Decision",
    "## Tradeoffs",
    "## Pattern fit",
    "## Consequences",
    "## Reversibility",
    "## Evidence / sources",
)


@pytest.mark.parametrize("name", REQUIRED_ADRS)
def test_adr_file_exists_and_nygard_shape(name: str) -> None:
    """AC-6 — every Step-1 ADR has all 8 Nygard sections + `Status: Accepted`."""
    path = ADR_DIR / name
    assert path.exists(), f"missing ADR: {name}"
    text = path.read_text(encoding="utf-8")
    for section in NYGARD_SECTIONS:
        assert section in text, f"{name} missing Nygard section: {section}"
    assert "**Status:** Accepted" in text, f"{name} is not marked Accepted (Draft ADRs are rejected at Step-1 gate)"


def test_phase2_readme_lists_every_step1_adr() -> None:
    """AC-7 — README has an ADR-listing section; every Step-1 ADR appears."""
    readme_text = README.read_text(encoding="utf-8")
    for name in REQUIRED_ADRS:
        adr_id = name.split("-", 1)[0]  # "0001"
        assert adr_id in readme_text or name in readme_text, (
            f"docs/phases/02-context-gather-layers-b-g/README.md does not link ADR {name}"
        )


def test_phase2_readme_marks_0010_as_pre_drafted() -> None:
    """AC-7, AC-11 — 02-ADR-0010 file already exists in the tree but its
    enforcement code ships in S3-02. The README's ADR list MUST disambiguate
    this so a reader doesn't assume 0010 is Step-1-active."""
    readme_text = README.read_text(encoding="utf-8")
    assert "0010" in readme_text, "README must reference 0010 to explain its pre-drafted status"
    # The disambiguating string SHOULD name S3-02 (the story that lands the
    # enforcement code). Flexible on exact wording; strict on the link.
    assert "S3-02" in readme_text or "Step 3" in readme_text or "Step-3" in readme_text, (
        "README's 0010 entry must mark it as a Step-3 deliverable (enforcement code)"
    )
```

**Test file 4**: `tests/unit/test_mypy_warn_unreachable_invariants.py`

```python
from __future__ import annotations
import tomllib
from pathlib import Path


PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# The five named modules from arch §"CI gates" job 7 — the load-bearing
# exhaustiveness consumers in Phase 2.
NAMED_MODULES = (
    "codegenie.indices.*",
    "codegenie.probes.layer_b.index_health",
    "codegenie.report.*",
    "codegenie.adapters.*",
    "codegenie.tccm.*",
)


def test_repo_wide_warn_unreachable_is_true() -> None:
    """AC-4 — Phase 0 S1-02 set this repo-wide (commit 3944f02). The story is a
    verification gate, not a configuration change. If a future PR removes this
    line, the broader-than-arch invariant breaks silently — this test prevents
    that."""
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert cfg["tool"]["mypy"]["warn_unreachable"] is True, (
        "[tool.mypy] warn_unreachable = true must remain set; see story S1-11 §"
        "Validation notes and arch §'CI gates' job 7."
    )


def test_no_override_disables_warn_unreachable_for_named_modules() -> None:
    """AC-4 — defense-in-depth. The repo-wide setting covers the five named
    modules; this test prevents a future `[[tool.mypy.overrides]]` block from
    silently weakening it on any of them."""
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    overrides = cfg.get("tool", {}).get("mypy", {}).get("overrides", [])
    for o in overrides:
        if o.get("warn_unreachable") is False:
            mod = o.get("module")
            mods = [mod] if isinstance(mod, str) else list(mod or [])
            for m in mods:
                assert m not in NAMED_MODULES, (
                    f"override silently disables warn_unreachable for {m}; forbidden by S1-11 AC-4"
                )
```

**Test file 5**: `tests/unit/test_mypy_warn_unreachable_fixture.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mypy_warn_unreachable" / "incomplete_match.py"


@pytest.mark.slow
def test_incomplete_match_fails_mypy_strict() -> None:
    """AC-5 — automates the original draft's manual `delete-an-arm` procedure.

    The fixture is a deliberately-incomplete `match: IndexFreshness` ending in
    `assert_never(value)`. With `warn_unreachable = true` enabled repo-wide
    (per Phase 0 S1-02), mypy must reject this fixture under `--strict`. If
    this test ever passes mypy clean, the repo-wide setting has silently
    broken — which is the failure mode 02-ADR-0006 §Consequences names."""
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(FIXTURE)],
        capture_output=True, text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"mypy --strict must reject the incomplete match (warn_unreachable invariant); "
        f"got exit 0; output:\n{combined}"
    )
    # mypy emits one of these phrases for the warn-unreachable + assert_never
    # failure mode (exact wording varies across versions; pin to the family).
    needles = ("unreachable", 'Argument 1 to "assert_never"', "Statement is unreachable")
    assert any(n in combined for n in needles), (
        f"mypy failure must name unreachable/assert_never; got:\n{combined}"
    )
```

**Fixture**: `tests/fixtures/mypy_warn_unreachable/incomplete_match.py`

```python
"""Deliberately-incomplete match over IndexFreshness — the failure target for
S1-11 AC-5. This file is NEVER imported by runtime code; it is invoked only as
input to `python -m mypy --strict` inside the test.

Pin to 02-ADR-0006 §Consequences: every consumer of IndexFreshness MUST close
its match with `assert_never(value)`; the `warn_unreachable = true` repo-wide
setting (Phase 0 pyproject.toml line 134) turns this from a runtime catch into
a mypy build-failure.
"""

from __future__ import annotations
from typing import assert_never

from codegenie.indices.freshness import IndexFreshness, Fresh, Stale, Unknown


def describe(value: IndexFreshness) -> str:
    match value:
        case Fresh():
            return "fresh"
        case Stale():
            return "stale"
        # case Unknown(): intentionally omitted — this is the warn_unreachable trigger.
    assert_never(value)
```

Run — confirm ALL of the tests above fail (red). Forbidden-patterns extension fails because `_RULES` doesn't have a `model_construct` row yet; the rule-shape tests fail because rows are tuples (no `applies_when` attribute); the ADR-Nygard tests fail because the README has no ADR listing; the mypy-fixture test fails because the fixture file doesn't exist. The `test_repo_wide_warn_unreachable_is_true` is the ONE that should already pass (Phase 0 set it months ago) — keep it as a forward-pinning regression guard, not a red test. Commit.

### Green — make it pass

1. **Refactor `_RULES` row shape** (`scripts/check_forbidden_patterns.py`):
   ```python
   from collections.abc import Callable
   from dataclasses import dataclass, field
   from pathlib import Path
   from re import Pattern

   @dataclass(frozen=True, slots=True)
   class Rule:
       label: str
       pattern: Pattern[str]
       advice: str
       applies_when: Callable[[Path], bool] = field(default=lambda _p: True)
   ```
   Convert the 11 existing tuples into `Rule(...)` constructor calls (default predicate).
2. **Add the Phase-2 rule** (one new `Rule(...)` entry + the `_is_under_phase2_banned_package` helper; both shown in the Implementation outline §3). The `advice` field contains BOTH `02-ADR-0010 §Decision` AND `production ADR-0033 §3` substrings verbatim.
3. **Update `_scan_file()`** to check `rule.applies_when(path)` before `pattern.finditer`. The loop body is unchanged otherwise.
4. **Create `tests/fixtures/mypy_warn_unreachable/incomplete_match.py`** as shown above. NO `pyproject.toml` edits.
5. **Edit `docs/phases/02-context-gather-layers-b-g/README.md`** — add the "Phase 2 ADRs" section listing 0001–0009 + the "Pre-drafted (S3-02): 0010" sub-bullet. Insert after the existing "Reading order" section.
6. **Run** `pre-commit run --all-files`, `mypy --strict src/codegenie/`, `pytest tests/unit/`. Confirm green on all five test files.

### Refactor — clean up

- The `_RULES` rows are now a contiguous block of `Rule(...)` constructors; group the 11 Phase-0 rules under a `# Phase 0 — ADR-0008 + ADR-0012` comment header and the new row under `# Phase 2 — model_construct ban (02-ADR-0010 + production ADR-0033)`.
- `_is_under_phase2_banned_package` is a single module-private helper; the `_PHASE2_BANNED_PACKAGES` constant sits next to it. Do NOT export either — `_RULES` is the only consumer.
- The README ADR section uses one-line bullets: `[0001 — Add docker + security CLIs to ALLOWED_BINARIES](ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — Accepted`.
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/`, `pre-commit run --all-files`, `pytest`.

## Files to touch

| Path | Action | Why |
|---|---|---|
| `scripts/check_forbidden_patterns.py` | modify | Refactor `_RULES` rows into a `Rule` dataclass with `applies_when` predicate (AC-15); append the Phase-2 path-scoped `model_construct` rule (AC-1); update `_scan_file()` to honor `applies_when`. |
| `docs/phases/02-context-gather-layers-b-g/README.md` | modify | Add an ADR-listing section (does not currently exist) — 0001–0009 + a "Pre-drafted (S3-02): 0010" sub-bullet (AC-7). |
| `tests/unit/pre_commit/test_forbidden_patterns_phase2_extension.py` | create | 28-cell positive matrix + path-scoping negative + Phase-0 regression (AC-2, AC-3, AC-14). |
| `tests/unit/pre_commit/test_forbidden_patterns_rule_shape.py` | create | Structural test for `Rule` dataclass + `applies_when` predicate (AC-15). |
| `tests/unit/test_adr_inventory_phase2.py` | create | Nine Step-1 ADR files exist + 8-section Nygard + `Status: Accepted` + README links each one + 0010 marked Pre-drafted (AC-6, AC-7, AC-11). |
| `tests/unit/test_mypy_warn_unreachable_invariants.py` | create | Repo-wide `warn_unreachable = true` stays set; no override silently disables it for the five named modules (AC-4). |
| `tests/unit/test_mypy_warn_unreachable_fixture.py` | create | Subprocess-mypy fixture-based exhaustiveness test (AC-5). |
| `tests/fixtures/mypy_warn_unreachable/incomplete_match.py` | create | The deliberately-incomplete `match` consumed by AC-5's subprocess test. |

`pyproject.toml` is NOT touched (verified at validation time — `warn_unreachable = true` already set repo-wide by Phase 0 S1-02).

## Out of scope

- **The `SecretRedactor` / `RedactedSlice` smart-constructor *code*** — handled by S3-01 / S3-02. This story only lands the `forbidden-patterns` discipline that those stories rely on.
- **`mypy --warn-unreachable` repo-wide rollout** — explicitly deferred to a backlog item filed in S8-04 per final-design Open Q 5.
- **The `tests/adv/phase02/test_no_inmemory_secret_leak.py` `inspect`-based boundary test** — handled by S7-04 (Gap 5 closure).
- **Phase-2-completion exit checklist** — handled by S8-04.
- **CI job authoring** (`fence`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`) — handled by S8-03.
- **ADR-0010 code (`RedactedSlice`)** — handled by S3-02. This story's ADR-inventory test does NOT require 0010 (the Step-1 nine are 0001–0009).
- **`@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe(heaviness=, runs_last=)` decorator implementations** — handled by S1-02, S1-10, S1-08 respectively.

## Notes for the implementer

- **Step 1 PR-size risk (manifest Implementation risk #1).** If the Step-1 PR exceeds 1,800 LOC during implementation, split into Step 1a (types: S1-01..S1-05, S1-11's type-side discipline) and Step 1b (kernel edits: S1-06..S1-10, S1-11's kernel-side discipline). The dependency edges in the DAG remain identical; the split is purely a delivery shape. Make the call before opening the PR — splitting later is review-pain.
- **The forbidden-patterns hook is the structural defense.** The architect's anti-patterns row 12 says `model_construct` bypasses Pydantic validation; the rationale is that smart-constructor invariants (S3-02's `RedactedSlice`, S1-04's `TCCM`) become fictional once `model_construct` is allowed. The hook ban is the only practical enforcement — mypy doesn't catch it (`model_construct` is a public Pydantic API).
- **The `Rule` dataclass refactor is the load-bearing design change (AC-15).** Before this story, `_RULES` carries two rule kinds: literal-pattern regex (e.g., `print(`, `os.system(`) and anchored regex (`yaml.Dumper` with negative lookbehinds). Adding a third kind — path-scoped regex (`model_construct` only under seven packages) — crosses the rule-of-three threshold (CLAUDE.md "Three similar lines is better than premature abstraction" is satisfied AT the third site, not before). The clean Open/Closed shape is one `applies_when` predicate per row. A future Phase-3 rule (e.g., ban `httpx` under `src/codegenie/plugins/`) is one new `Rule(...)` entry — no further edits to the loop body. Without the refactor, the procedural alternative (an `if _is_in_phase2_banned(path) and pattern_X.search(...)` branch in the loop) accretes — every new path-scoped rule adds another branch.
- **Path-component check.** Use `pathlib.Path.parts` and look for `codegenie` followed by one of the seven names. Do NOT regex against the full path string — Windows path separators and symlinked checkout paths will trip you.
- **`warn_unreachable = true` is already repo-wide (verified at validation time, pyproject.toml line 134, set by Phase 0 S1-02 in commit `3944f02`).** The arch's per-module prescription (`phase-arch-design.md §"CI gates"` job 7) is the *narrower* target; Phase 0 deliberately went broader for the reason called out in the inline comment ("warn_unreachable is a strict-extra; --strict does NOT enable it. Without this, dead-code-after-narrowing slips through silently"). This story does NOT narrow the scope back — that would be a Phase-0 surgical edit and is out of scope here. The arch's per-module prescription is now satisfied broader-than-arch; the narrowing decision is an S8-04 backlog item if/when accumulated false-positives demand it.
- **AC-11 lock.** The story's REQUIRED_ADRS list is 0001–0009. 02-ADR-0010 already exists on disk (verified) — its file is *tolerated* by the existence test (not asserted, not forbidden). The README's "Pre-drafted" sub-bullet does the disambiguation work; AC-7 pins that the README mentions both 0010 and S3-02 (or "Step 3") so a casual reader doesn't assume 0010 is Step-1-active.
- **The mypy fixture (AC-5) must be excluded from normal pytest test-collection.** Place it under `tests/fixtures/mypy_warn_unreachable/` (not `tests/unit/`) and add `collect_ignore = ["fixtures/mypy_warn_unreachable"]` to `tests/conftest.py` if pytest tries to collect it. The fixture is INPUT to a subprocess, not a runnable test — pytest collecting it would surface the `match` failure as a runtime error.
- **`tomllib` is stdlib in Python 3.11+.** Project baseline is 3.11+ (per Phase 0 `pyproject.toml`); no third-party `toml` dep needed.
- **CODEOWNERS for `pyproject.toml`.** If `.github/CODEOWNERS` exists, route `pyproject.toml` to the same Phase 2 architects. If not, this is a follow-up in S8-04 — do not file speculatively.
- **`Phase 0 fence` job stays green.** The fence asserts no LLM SDK imports under `src/codegenie/`. None of Step 1's stories add such an import; this is the structural backstop.
- **`Phase 0 contract-freeze` job stays green.** Only `image_digest_resolver` (S1-09) widens `ProbeContext`; the snapshot regen script encoded the allowed-field list so any further widening fails CI with an ADR-0004 pointer.
- **False-positive risk for `\bmodel_construct\s*=` (regex precision).** The pattern matches kwarg defaults (`def bar(model_construct=None)`) and assignments (`model_construct = something`). Both are extremely unlikely in legitimate Phase 2 code (`model_construct` is reserved Pydantic surface), so the regex is honest about being a *structural* defense rather than an AST-precise one. If a future Phase-2 file legitimately needs a variable named `model_construct` (it shouldn't — review-block it), the rule fires and a PR comment routes the reviewer to consider whether the file legitimately needs the variable. Document this trade-off in the rule's `advice` field.
