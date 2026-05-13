# Validation report: S1-01 — Pyproject scaffold + extras shape

**Validated:** 2026-05-12
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story file:** [`../S1-01-pyproject-scaffold.md`](../S1-01-pyproject-scaffold.md)

## Summary

S1-01 lands `pyproject.toml`, the four-slot `[project.optional-dependencies]` shape mandated by ADR-0006, and the minimal `src/codegenie/{__init__,__main__,version}.py` skeleton. As written the story's goal and AC structure traced cleanly to ADR-0006, ADR-0002, and ADR-0010 — no `block`-class structural issues. However, the original TDD plan used three patterns that would have let an obviously wrong implementation pass: (a) `set.issubset` instead of equality for the runtime closure, (b) version-specifier stripping that hid lower-bound regressions, and (c) `Provides-Extra` slot-name detection that didn't verify the three reserved-empty slots were actually empty. Three load-bearing properties (the LLM-SDK intersection, the `python -m codegenie --help` smoke, and the hatchling dynamic-version hook coherence) lacked any test. We rewrote the seven-test TDD plan to use `packaging.Requirement`-based parsing, exact-set equality, explicit version-bound probes, zero-entry assertions on the empty extras, an LLM-SDK intersection assertion, a `python -m codegenie --help` subprocess smoke, and a distribution-vs-`__version__` coherence check. AC-3's brittle exact `dev` list (which conflicted across `final-design.md §2.2` and `High-level-impl.md §Step 1`) was relaxed to a *floor* covering the AC-7 toolchain plus `pre-commit` and `mkdocs-material`. AC-8 and AC-9 were added; AC-6 was promoted from a manual `python -c` invocation to an executable test inside this story.

## Findings by critic

### Coverage critic findings — S1-01

#### F1 — AC-2 "exactly" not enforced by the AC-set
- **Severity:** harden
- **What's wrong:** AC-2 reads "**exactly** `click`, `pyyaml`, `jsonschema>=4.21`, `pydantic>=2`, `blake3`, `structlog`" but the only tests covering AC-2 (Test 2) use `expected.issubset(names)`. A lazy implementation adding `requests` to runtime `dependencies` passes every test. "Exactly" must be set-equality.
- **Proposed fix:** Tighten AC-2 to "the parsed set of `[project.dependencies]` distribution names equals **exactly** `{click, pyyaml, jsonschema, pydantic, blake3, structlog}` — neither superset nor subset". Rewrite Test 2 as `assert names == RUNTIME_DEPS`.
- **Confidence:** high
- **Source:** mutation thought experiment + Story-smell "Some/any without quantifier"

#### F2 — AC-2 version pins (`>=4.21`, `>=2`) are not testable as written
- **Severity:** harden
- **What's wrong:** ADR-0010 calls out the `pydantic>=2` major-version pin as load-bearing; High-level-impl §Step 1 names `jsonschema>=4.21`. Test 2 strips specifiers (`split(">").split("=").split("<")`) so any version slips through. Mutation: `pydantic>=1.10` is silently accepted, which would let `_ProbeOutputValidator` (ADR-0010) ship against pydantic v1, breaking ADR-0010's "frozen, extra='forbid'" model_config syntax.
- **Proposed fix:** AC-2 explicitly enumerates the version-pin commitments. Test 2 parses `Requires-Dist` with `packaging.Requirement` and asserts `"2.0.0" in pydantic_spec and "1.99.0" not in pydantic_spec` (and similarly for jsonschema).
- **Confidence:** high
- **Source:** mutation thought experiment + ADR-0010 §Decision

#### F3 — AC-3 doesn't enforce that the reserved-empty extras are empty
- **Severity:** harden
- **What's wrong:** AC-3 reads "declares all four keys `gather` (empty list), … `service` (empty list), `agents` (empty list)" but Test 3 only checks `{"gather","dev","service","agents"}.issubset(provides_extra)`. A lazy implementation moving `pyyaml` from `[project.dependencies]` into `[project.optional-dependencies.gather]` satisfies every test while violating ADR-0006's foundational invariant (the gather closure *is* `[project.dependencies]`; the extras' emptiness is what makes the slot semantic).
- **Proposed fix:** Add an explicit AC sub-clause: for each of `gather`, `service`, `agents`, the count of `Requires-Dist` entries with `; extra == "<name>"` must be **zero**. New Test 3 iterates `EMPTY_EXTRAS` and asserts `[] == _extra_requirements(extra)`.
- **Confidence:** high
- **Source:** mutation thought experiment + ADR-0006 §Decision / §Consequences

#### F4 — Goal clause 3 (`python -m codegenie --help` exit 0) is untested
- **Severity:** harden
- **What's wrong:** Story goal explicitly lists "`python -m codegenie --help` returns exit code 0" as success. No AC, no test exercises this. A `__main__.py` that does `raise NotImplementedError()` would pass every original test.
- **Proposed fix:** Add AC-8 plus a new TDD test (`test_python_dash_m_codegenie_help_returns_zero`) using `subprocess.run([sys.executable, "-m", "codegenie", "--help"])`.
- **Confidence:** high
- **Source:** goal-to-AC trace — clause 3 of the goal has no AC

#### F5 — Hatchling dynamic-version hook is not verified
- **Severity:** harden
- **What's wrong:** AC-1 declares `dynamic = ["version"]` tied to `version.py` via `[tool.hatch.version]`. Implementer notes call this out. But no test verifies coherence between `dist.metadata["Version"]` and `codegenie.__version__`. Lazy impl: declare `version = "0.0.1"` statically in `[project]` (overriding `dynamic`) and set `__version__ = "0.1.0"` in `version.py` — every original test passes; the bug only surfaces when Phase 5's release-tagging story tries to read it. The single-source-of-truth invariant is exactly what a packaging-scaffold story exists to lock down.
- **Proposed fix:** Add AC-9 plus a new TDD test (`test_distribution_version_matches_package_version`).
- **Confidence:** high
- **Source:** mutation thought experiment + High-level-impl §Step 1 ("single source of truth, read by `pyproject.toml` via `hatchling`'s version hook")

#### F6 — AC-6 is described as a manual command-line check, not a test
- **Severity:** harden
- **What's wrong:** AC-6 reads "`python -c "… print(sorted(r for r in distribution('codewizard-sherpa').requires or []))"` lists the runtime closure with **none of** `anthropic, langgraph, openai, langchain, transformers` (this is the structural property S1-05's fence test will codify)." This is the load-bearing commitment from `CLAUDE.md` §"No LLM anywhere in the gather pipeline" and production ADR-0005. Manual `python -c` verification is not regression-safe; it depends on someone remembering to run it.
- **Proposed fix:** Rephrase AC-6 to assert the set intersection; promote into Test 2 (alongside the runtime-closure equality assertion). S1-05 still owns the dedicated fence test with its deliberate-negative case — this story self-verifies the property as well.
- **Confidence:** high
- **Source:** Story-smell "Asserting on logs / manual checks" + CLAUDE.md load-bearing commitment

### Test-Quality critic findings — S1-01

#### F1 — `test_runtime_dependencies_match_adr_0006` uses `issubset`, not equality
- **Severity:** harden
- **What's wrong:** Mutation: replace runtime `dependencies` with `[click, pyyaml, jsonschema, pydantic, blake3, structlog, requests]` — test passes (extra dep is in the superset). The test name claims to "match ADR-0006" but only asserts the lower half of a match.
- **Proposed fix:** `assert names == RUNTIME_DEPS` (Equality, not subset). Test renamed to `test_runtime_dependencies_are_exactly_adr_0006_closure` so the assertion direction is in the name.
- **Confidence:** high
- **Source:** mutation thinking

#### F2 — Version specifiers stripped before assertion
- **Severity:** harden
- **What's wrong:** The `r.split(">").split("=").split("<")` chain in Test 2 throws away the specifier. Mutation: `pydantic>=1.0` → splitter yields `"pydantic"` → in expected → test passes. Yet `_ProbeOutputValidator` (ADR-0010) relies on pydantic v2's `model_config = ConfigDict(frozen=True, extra="forbid")` API, which doesn't exist on v1.
- **Proposed fix:** Use `packaging.Requirement` to parse the raw `Requires-Dist` strings and `packaging.SpecifierSet.__contains__` to assert lower bounds. New `test_runtime_dependencies_carry_required_version_specifiers` probes both inclusion (`"2.0.0" in spec`) and exclusion (`"1.99.0" not in spec`) — catches both "no specifier" and "wrong specifier" mutants.
- **Confidence:** high
- **Source:** mutation thinking + ADR-0010 §Decision

#### F3 — `test_optional_dependencies_declare_four_slots` only checks slot existence
- **Severity:** harden
- **What's wrong:** The test asserts slot *names* appear in `Provides-Extra` but never that the slots' *contents* match ADR-0006. Mutation: move `pyyaml` from `dependencies` into `gather = ["pyyaml"]` — `provides_extra` still contains `gather`, test passes, ADR-0006 §Decision violated.
- **Proposed fix:** Split into two tests. `test_optional_dependencies_declare_four_slots_and_empties_are_empty` keeps the existence check AND iterates `{gather, service, agents}` asserting zero `Requires-Dist` entries tagged with each. `test_dev_extra_contains_ac_7_toolchain_floor` separately asserts the dev floor.
- **Confidence:** high
- **Source:** mutation thinking + ADR-0006 §Decision

#### F4 — AC-6 (no LLM SDK) lacks a test in this story's TDD plan
- **Severity:** harden
- **What's wrong:** The load-bearing commitment of this whole phase ("No LLM in gather", `CLAUDE.md`) is gated by an AC the story describes as a manual command. S1-05 owns the dedicated fence test (with a deliberate-negative case) — but a regression introduced *in this story's PR* wouldn't be caught by the executor's TDD loop here. Defense in depth requires the assertion lives in both places.
- **Proposed fix:** Roll the intersection assertion into the renamed `test_runtime_dependencies_are_exactly_adr_0006_closure`. The exact-set equality already excludes LLM SDK names, but the explicit `names & LLM_SDKS == set()` assertion gives a more diagnostic failure message and survives any future relaxation of the equality check.
- **Confidence:** high
- **Source:** mutation thinking + CLAUDE.md load-bearing commitment

#### F5 — Goal clause "`python -m codegenie --help` returns exit code 0" has no test
- **Severity:** harden
- **What's wrong:** The goal states three commands should succeed; only the first (`pip install -e .`) and second (`import codegenie; print(__version__)`) are tested. The `python -m codegenie --help` line is unverified. Without it, the story can claim success while `__main__.py` is broken.
- **Proposed fix:** Add `test_python_dash_m_codegenie_help_returns_zero` using `subprocess.run([sys.executable, "-m", "codegenie", "--help"], …)`.
- **Confidence:** high
- **Source:** goal-to-test trace

#### F6 — Hatchling version-hook coherence is untested
- **Severity:** harden
- **What's wrong:** Same root cause as Coverage F5. Add a test that asserts `dist.metadata["Version"] == codegenie.__version__`. Mutation-resistant: a static `version = "0.0.1"` in `[project]` plus `__version__ = "0.1.0"` in `version.py` is caught.
- **Proposed fix:** `test_distribution_version_matches_package_version` — one-line assertion.
- **Confidence:** high
- **Source:** mutation thinking + High-level-impl §Step 1

#### F7 — `Provides-Extra` extraction via `dict.items()` is fragile across Python versions
- **Severity:** nit
- **What's wrong:** `{v for k, v in dist.metadata.items() if k == "Provides-Extra"}` — `dist.metadata` is an `email.message.Message`. Iterating `.items()` returns each (key, value) pair *individually* on CPython, but the idiomatic and stable API for multi-valued headers is `dist.metadata.get_all("Provides-Extra")`. The current form is not wrong on supported pythons, but it reads as "I'm filtering a dict" when the underlying object is a `Message`.
- **Proposed fix:** Replace with `set(dist.metadata.get_all("Provides-Extra") or [])`.
- **Confidence:** medium
- **Source:** `email.message.Message` documented API

### Consistency critic findings — S1-01

#### F1 — `dev` extras list conflicts across three source documents
- **Severity:** harden
- **What's wrong:** The story's AC-3 enumerates a specific dev set (`pytest, pytest-asyncio, pytest-cov, mypy, ruff, pre-commit, mkdocs-material, import-linter, pip-audit`). `High-level-impl.md §Step 1` "Features delivered" lists *that set plus `osv-scanner`*. `final-design.md §2.2`'s example pyproject block lists *a different set entirely*: `pytest, pytest-asyncio, pytest-cov, mypy, ruff, pre-commit, mkdocs-material, mkdocs-include-markdown-plugin, bandit, gitleaks-python, uv`. None of the three sources is canonically authoritative for the full dev list, and several entries (e.g., `pre-commit`, `mkdocs-material`, `gitleaks`, `bandit`, `osv-scanner`, `pip-audit`) belong to downstream stories (S1-04 owns pre-commit + mkdocs; S1-05 owns CI security scanners). Per the validator's conflict-resolution rule (Consistency wins on source-of-truth disputes), the right move is to relax the story's AC to **structural invariants** rather than try to pick a winner among three non-canonical lists.
- **Proposed fix:** Rewrite AC-3 to enforce (a) all four slot names appear in `Provides-Extra`, (b) `gather`/`service`/`agents` have zero `Requires-Dist` entries, (c) `dev` contains at minimum the AC-7 toolchain (`pytest, pytest-asyncio, pytest-cov, mypy, ruff`) plus `pre-commit` and `mkdocs-material` (so S1-04 inherits a working harness). Other dev entries (`import-linter`, `pip-audit`, `osv-scanner`, `bandit`, `gitleaks-python`, `uv`, `mkdocs-include-markdown-plugin`) are allowed but not enforced here; downstream stories add their own via extension by addition.
- **Confidence:** high
- **Source:** cross-document diff between `final-design.md §2.2`, `High-level-impl.md §Step 1`, and the story's original AC-3

#### F2 — Implementation outline version `0.1.0` contradicts `final-design.md §2.2` example `0.0.1`
- **Severity:** harden
- **What's wrong:** Story Implementation Outline §2 says `__version__ = "0.1.0"`; `final-design.md §2.2`'s example pyproject block shows `version = "0.0.1"`. Under AC-9 (the new dynamic-version coherence test), this becomes load-bearing: the executor will pick one and the other gets baked in. With no canonical source, the safer choice is to align with `final-design.md` (the synthesis document), reserving `0.1.0` for a future bump tied to a milestone (e.g., the first phase-0 exit tag).
- **Proposed fix:** Update Implementation Outline §2 to `__version__ = "0.0.1"`. Note that AC-9 doesn't care which value is chosen, only that `pyproject.toml`'s dynamic hook and `version.py` agree.
- **Confidence:** medium
- **Source:** cross-document diff between `final-design.md §2.2` and the story's Implementation Outline

#### F3 — Otherwise consistent with phase architecture
- **Severity:** nit
- **What's wrong:** Nothing. The story aligns with ADR-0006 §Decision (four-slot extras shape), ADR-0002 (the fence's intersection-with-LLM-SDKs target), ADR-0010 (pydantic v2 in runtime deps), the phase arch's Development view file layout, and CLAUDE.md's "No LLM anywhere in the gather pipeline" / "Extension by addition" commitments. Out-of-scope correctly excludes work owned by S1-02 / S1-03 / S1-04 / S1-05 / S2-01 / S4-02. Files-to-touch matches the arch's Development view.
- **Proposed fix:** none.
- **Confidence:** high
- **Source:** ADR-0006, ADR-0002, ADR-0010, `phase-arch-design.md §Development view`, `CLAUDE.md`

## Research briefs

None. No finding required external research — every gap had a canonical fix derivable from the project's existing ADRs, phase architecture, or `packaging` stdlib idioms.

## Conflict resolutions

**Conflict 1:** Coverage F1 ("AC-2 'exactly' isn't enforced") proposed a test that asserts exact-set equality including LLM SDK exclusion. Test-Quality F4 ("AC-6 has no test in this story") proposed a separate LLM-SDK intersection assertion. The two findings reinforce rather than conflict: exact-set equality already excludes LLM SDK names, but the explicit `names & LLM_SDKS == set()` assertion provides a more diagnostic failure message and survives any later weakening of the equality check (defense in depth). **Resolution:** both assertions live in `test_runtime_dependencies_are_exactly_adr_0006_closure`.

**Conflict 2:** Consistency F1 (dev list inconsistent across docs) and Coverage F1 (relax AC-3 to a floor rather than an exact list) point in the same direction. **Resolution:** AC-3 enforces (a) structural invariants on the four slots and (b) a minimum floor for `dev`. Per the editor.md rule "Consistency wins over Coverage on AC content": the floor is *narrower* than the original brittle list, but it's the only set every source doc agrees on.

**No two-critic disagreements arose.**

## Edits applied

### Edit 1 — AC-2 strengthened (Coverage F1, F2; Test-Quality F1, F2)
- **Before:** "`[project.dependencies]` contains **exactly** `click`, `pyyaml`, `jsonschema>=4.21`, `pydantic>=2`, `blake3`, `structlog` — no LLM SDKs, no `aiofiles`."
- **After:** "the parsed set of `[project.dependencies]` distribution names equals **exactly** `{click, pyyaml, jsonschema, pydantic, blake3, structlog}` (neither superset nor subset — no LLM SDKs, no `aiofiles`, no `requests`/`httpx`/etc.). The raw `Requires-Dist` entries for `jsonschema` and `pydantic` MUST carry the version specifiers `>=4.21` and `>=2` respectively (verified by parsing the version specifier from `Requires-Dist` — not stripping it)."
- **Rationale:** Closes the "subset, not exact" gap and the version-specifier-stripping gap simultaneously.

### Edit 2 — AC-3 restructured (Coverage F3; Test-Quality F3; Consistency F1)
- **Before:** enumerated a specific `dev` list (`pytest, pytest-asyncio, pytest-cov, mypy, ruff, pre-commit, mkdocs-material, import-linter, pip-audit`) and only said `gather`/`service`/`agents` were "empty list".
- **After:** structural invariants on the four `Provides-Extra` slots, **zero**-`Requires-Dist`-entries assertion for the three reserved-empty extras, and a *floor* for `dev` covering the AC-7 toolchain plus `pre-commit` and `mkdocs-material`. Additional dev entries explicitly allowed-but-not-enforced.
- **Rationale:** Resolves the three-way source-doc conflict; mutates the brittle exact-list AC into structural assertions that downstream stories can extend without contradicting.

### Edit 3 — AC-4 tightened (Coverage F5)
- **Before:** "`version.py` exposes a single `__version__: str` constant."
- **After:** appended "declared as a *top-level assignment* (so `hatchling`'s AST-based version hook can parse it without executing the file)."
- **Rationale:** The original allowed `__version__` to be computed (e.g., `__version__ = str(_compute_version())`), which hatchling's AST parser silently fails on.

### Edit 4 — AC-5 tightened (Test-Quality nit)
- **Before:** "The TDD red test exists at `tests/unit/test_packaging.py`, was committed at the red phase, and is green after implementation."
- **After:** appended "verifiable in git history as a commit where the test exists but `src/codegenie/` does not".
- **Rationale:** "committed at the red phase" was unverifiable as written; the git-history reformulation gives the executor a binary check.

### Edit 5 — AC-6 promoted (Coverage F6; Test-Quality F4)
- **Before:** Manual `python -c "..."` invocation listing the runtime closure; described as a "structural property S1-05's fence test will codify".
- **After:** "`set(parsed_runtime_dependency_names) ∩ {anthropic, langgraph, openai, langchain, transformers} == set()` … **Asserted by a test in this story's TDD plan** (Test 2 below), not deferred to S1-05."
- **Rationale:** The load-bearing CLAUDE.md commitment now has a regression test in this story; S1-05 still owns the dedicated fence with deliberate-negative.

### Edit 6 — AC-7 tightened (Consistency)
- **Before:** "`ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest tests/unit/test_packaging.py` all pass on the touched files."
- **After:** appended explicit invocation targets (`src/ tests/`) and the disclaimer "configuration for these tools lands in S1-02; this story relies only on CLI defaults".
- **Rationale:** The original was ambiguous about scope and could be read as "make check passes" — which would require S1-02/S1-03/S1-04 work this story explicitly excludes.

### Edit 7 — AC-8 added (Coverage F4; Test-Quality F5)
- New AC covering the goal clause "`python -m codegenie --help` returns exit code 0".

### Edit 8 — AC-9 added (Coverage F5; Test-Quality F6)
- New AC covering the hatchling dynamic-version hook coherence (`dist.metadata["Version"] == codegenie.__version__`).

### Edit 9 — Implementation Outline §2 version pin (Consistency F2)
- **Before:** `__version__ = "0.1.0"`.
- **After:** `__version__ = "0.0.1"` (matches `final-design.md §2.2`).

### Edit 10 — TDD plan rewritten end-to-end
- Replaced four tests with seven, all using `packaging.Requirement` for spec-preserving parsing.
- Renamed `test_runtime_dependencies_match_adr_0006` → `test_runtime_dependencies_are_exactly_adr_0006_closure` (assertion direction in the name).
- Added `test_runtime_dependencies_carry_required_version_specifiers` (Test-Quality F2).
- Renamed `test_optional_dependencies_declare_four_slots` → `test_optional_dependencies_declare_four_slots_and_empties_are_empty` plus split out `test_dev_extra_contains_ac_7_toolchain_floor` (Test-Quality F3, Consistency F1).
- Added `test_python_dash_m_codegenie_help_returns_zero` (Coverage F4 / Test-Quality F5).
- Added `test_distribution_version_matches_package_version` (Coverage F5 / Test-Quality F6).
- Switched `Provides-Extra` extraction to `dist.metadata.get_all("Provides-Extra")` (Test-Quality F7 nit).

### Edit 11 — Validation notes block prepended
- Inserted under the story header recording the verdict, all changes, the conflict resolution for the dev-list disagreement, and a pointer to this file.

## Verdict rationale

**HARDENED.** The story's goal, ADR alignment, scope boundaries, and overall structure were sound — no `block` findings warranting RESCUE. But six of the seven ACs had measurable mutation-test gaps: a lazy implementation could have satisfied every original AC and test while violating ADR-0006 (extra deps in the closure), ADR-0010 (pydantic v1), ADR-0002 / production ADR-0005 (LLM SDK in `dependencies`), or the hatchling single-source-of-truth invariant. All of these were fixable in place by tightening the assertions and adding two missing ACs traceable to the original goal — no goal rewrite required. The dev-list cross-document inconsistency was resolved by demoting AC-3 to structural invariants plus a toolchain floor, which is more honest about what this story actually owns (the slot shape, not the slot contents).

## Recommended next step

Proceed to `phase-story-executor` for S1-01. The story now has seven mutation-resistant TDD tests covering exact-set equality of the runtime closure, explicit version-bound probes for `pydantic>=2` and `jsonschema>=4.21`, LLM-SDK intersection emptiness, the three reserved-empty extras being literally empty, the dev toolchain floor, the `python -m codegenie --help` smoke, and the hatchling version-hook coherence.

Executor note: AC-9's coherence test means choosing one version literal and threading it through `version.py` only; do **not** add a static `version = "..."` line to `[project]` while also declaring `dynamic = ["version"]` (TOML allows both syntactically; `hatchling` will reject it at build time but the test catches the regression earlier).
