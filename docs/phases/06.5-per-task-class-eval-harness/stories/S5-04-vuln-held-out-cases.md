# Story S5-04 — vuln-remediation 5 held-out hand-curated cases

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** L
**Depends on:** S5-02 (rubric must score these end-to-end; without it, the cases are inert)
**ADRs honored:** ADR-0006 (these 5 cases are `curation_class="held-out"`; their existence is the structural precondition for any `min_cases_for_promotion` tier ≥ silver; fence-CI assertion #3 enforces the count), ADR-0005 (32-hex `cassette_canary_pin` per case; the pin's deterministic role through Phase 4 `Canary.mint(seed=...)`)

## Context

ADR-0006 is unambiguous about why this story is the long pole: hand-curated held-out cases are the *only* evidence base that can distinguish memorization from judgment for `vuln-remediation`. The 5 cases must be drawn from CVEs **outside** Phase 4's RAG corpus (i.e., CVE-YEAR-NNNN where YEAR ≥ the Phase 4 corpus cutoff, or older CVEs that were intentionally excluded from corpus construction). Each case requires hand-built ground truth: a pre-fix repo snapshot under `input/`, an expected post-fix diff and validator-output under `expected/`, a 32-hex `cassette_canary_pin`, and a BLAKE3 `case_digest`.

The phase-level schedule risk is acknowledged in `High-level-impl.md §Implementation-level risks #1`: "Hand-curating CVE-fix ground truth ... is slow and easy to underestimate. Signal it's going sideways: Step 5 stretches past one week with < 5 held-out cases written." This story's effort is **L** because curation is real work, not because the contract is complex.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy → Fixture portfolio` — names this as the production-fixture half of the 5+5 split.
  - `../phase-arch-design.md §Risks (top 5)` — risk #1 names "RAG-corpus-derived cases conflate memorization with judgment" and the held-out floor as the structural remediation.
  - `../phase-arch-design.md §Edge cases #9` — fence-CI counts `c.curation_class == "held-out"` and fails if < 5 when silver is declared.
- **Phase ADRs:**
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision, §Consequences` — held-out selection criterion ("CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff"); cases are hand-curated.
  - `../ADRs/0005-cassette-canary-seed-parameterization.md` — every case carries a 32-hex pin; for held-out cases the pin is freshly minted at curation time (the case had no prior cassette).
- **Production ADRs:** `../../../production/adrs/0009-humans-always-merge.md` — the curation discipline is the human-in-the-loop boundary at the bench layer.
- **Source design:** `../High-level-impl.md §Step 5` + `§Implementation-level risks #1`.

## Goal

Curate exactly 5 `BenchCase` directories under `bench/vuln-remediation/cases/` with `curation_class="held-out"`, each from an independent CVE *not* represented in Phase 4's RAG corpus, each carrying hand-built `input/` and `expected/` snapshots, a 32-hex `cassette_canary_pin`, and a BLAKE3 `case_digest`. The 5 cases must satisfy fence-CI assertion #3 so the bench can declare `silver` in `min_cases_for_promotion`.

## Acceptance criteria

- [ ] `bench/vuln-remediation/cases/` contains exactly 5 additional directories (on top of S5-03's 5) whose names follow the pattern `00{6..10}-<cve-id>-held-out/`.
- [ ] Each case's `case.toml` validates into a `BenchCase` with `curation_class="held-out"`, `source="curated"`, `task_class="vuln-remediation"`, tz-aware UTC timestamps, 32-hex `cassette_canary_pin`, `blake3:`-prefixed 64-hex `case_digest`.
- [ ] Each case's `case_id` contains a CVE identifier (e.g., `006-cve-2025-31234-held-out`); the CVE is **not** referenced by any cassette under `tests/cassettes/phase4/` — a unit test (`test_held_out_cve_not_in_rag_corpus`) asserts this by grep-scanning the cassette tree.
- [ ] Each case directory contains `input/` with the pre-fix repo snapshot (or `input-pointer.toml` if the snapshot lives elsewhere; documented) and `expected/` with the ground-truth diff + validator output.
- [ ] `loader.load_cases(task_class)` returns 10 total cases sorted by `case_id`; 5 are `held-out`, 5 are `rag-corpus-derived`.
- [ ] Fence-CI assertion #3 passes: with `min_cases_for_promotion["silver"]=25` declared in `registration.py` (per S5-01), the held-out count is exactly 5 (the ≥ 5 floor), not fewer. Removing one held-out case (synthetic) makes fence-CI fail with the diagnostic naming `vuln-remediation` and the count.
- [ ] Each case scores end-to-end through `bench/vuln-remediation/rubric.py` — `score(case, harness_output)` produces a valid `BenchScore` for at least one constructed `harness_output` (smoke-test: the case's `expected/` must encode something the rubric can match against; the bench-author tests verify the matching logic).
- [ ] CVE selection criterion is documented in `bench/vuln-remediation/README.md`: "CVE-YEAR-NNNN where YEAR ≥ <Phase 4 corpus cutoff date>, or older CVEs explicitly excluded from corpus construction (and noted)". The README also names each held-out CVE and its public reference.
- [ ] Red test from §TDD plan exists, was committed at red, now green; `ruff check`, `ruff format --check`, and `pytest tests/integration/test_vuln_held_out_cases.py` all pass.

## Implementation outline

1. **Identify 5 CVEs** outside Phase 4's RAG corpus. Curator selection:
   - Walk `tests/cassettes/phase4/` and grep for `CVE-` references; build the exclusion set.
   - Source candidates from public CVE feeds (NVD / GHSA) where YEAR ≥ Phase 4 corpus cutoff.
   - Prefer CVEs with public, well-documented patches (Apache, CPython, popular libs).
   - Mix of language ecosystems (e.g., 2 Python, 2 Java, 1 Node) to avoid single-language bias.
2. Write the red test `tests/integration/test_vuln_held_out_cases.py` first — see §TDD plan.
3. **For each CVE**, hand-build the case directory:
   - `input/` — a snapshot of the affected repo at a pre-fix commit (`input-pointer.toml` pointing to a vendored snapshot under `bench/vuln-remediation/snapshots/<cve>/` is acceptable if the snapshot is large).
   - `expected/` — the ground-truth fix: `expected/diff.patch` (the actual upstream patch), `expected/validator_output.json` (the validator's expected JSON output: `{"build_passed": true, "tests_passed": true, "cve_dropped": true}`).
   - `case.toml` — fully populated; `commit_sha` may be the pre-fix commit (this is `source="curated"` so `commit_sha` is optional, but include it for traceability).
   - `cassette_canary_pin` — freshly minted via `Canary.mint()` at curation time; record the 32 hex chars.
   - `case_digest` — BLAKE3 over `input/` + `expected/` (same algorithm as S5-03).
4. Verify the 5 cases load and score through the rubric; iterate.
5. Update `bench/vuln-remediation/README.md` with the CVE → case mapping table.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_vuln_held_out_cases.py`

```python
# tests/integration/test_vuln_held_out_cases.py
"""5 held-out cases must exist, be distinct CVEs, be absent from the RAG corpus,
and satisfy fence-CI assertion #3. ADR-0006 §Decision is the contract."""

import re
from pathlib import Path

import pytest

from codegenie.eval.loader import load_cases, load_task_class

BENCH_ROOT = Path(__file__).parents[2] / "bench"
RAG_CORPUS_ROOT = Path(__file__).parents[2] / "tests" / "cassettes" / "phase4"


def _held_out_cases():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    return [c for c in load_cases(tc) if c.curation_class == "held-out"]


def test_exactly_five_held_out_cases_exist():
    held_out = _held_out_cases()
    assert len(held_out) == 5, f"expected 5 held-out, found {len(held_out)}"


def test_case_ids_carry_cve_identifier():
    cve_re = re.compile(r"cve-\d{4}-\d+", re.IGNORECASE)
    held_out = _held_out_cases()
    seen = set()
    for c in held_out:
        m = cve_re.search(c.case_id)
        assert m, f"{c.case_id} does not carry a CVE identifier"
        cve = m.group(0).lower()
        assert cve not in seen, f"duplicate CVE {cve}"
        seen.add(cve)


def test_held_out_cve_not_in_rag_corpus():
    """ADR-0006 §Decision: held-out CVEs must not appear in tests/cassettes/phase4/."""
    cve_re = re.compile(r"cve-\d{4}-\d+", re.IGNORECASE)
    held_out = _held_out_cases()
    if not RAG_CORPUS_ROOT.exists():
        pytest.skip("RAG corpus tree absent; skipping cross-check")
    corpus_text = "\n".join(
        p.read_text(errors="ignore") for p in RAG_CORPUS_ROOT.rglob("*") if p.is_file()
    ).lower()
    for c in held_out:
        cve = cve_re.search(c.case_id).group(0).lower()
        assert cve not in corpus_text, (
            f"{cve} ({c.case_id}) appears in RAG corpus — violates held-out contract"
        )


def test_held_out_cases_have_blake3_digest_and_pin():
    for c in _held_out_cases():
        assert c.case_digest.startswith("blake3:") and len(c.case_digest) == 71
        assert len(c.cassette_canary_pin) == 32
        assert all(ch in "0123456789abcdef" for ch in c.cassette_canary_pin)


def test_held_out_cases_have_diff_and_validator_output():
    for c in _held_out_cases():
        diff = c.expected_path / "diff.patch"
        validator = c.expected_path / "validator_output.json"
        assert diff.is_file() and diff.stat().st_size > 0, f"{c.case_id}: diff.patch missing/empty"
        assert validator.is_file() and validator.stat().st_size > 0, f"{c.case_id}: validator_output.json missing/empty"


def test_held_out_floor_met_for_silver_tier_eligibility():
    """Fence-CI assertion #3 (ADR-0006): if any tier ≥ silver in
    min_cases_for_promotion, count(held-out) >= 5."""
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    if "silver" in tc.min_cases_for_promotion or any(
        t in tc.min_cases_for_promotion for t in ("silver", "gold", "platinum")
    ):
        assert len(_held_out_cases()) >= 5
```

Run it; confirm zero or fewer cases. Commit as red marker.

### Green — smallest impl shape

1. CVE selection (the heavy lift). Pick 5 well-documented CVEs. Suggested patterns (curator chooses):
   - 2025-era CVEs in Python libraries with simple patch diffs.
   - One Java CVE (Apache lib) — exercises a different language path.
   - One Node CVE.
   - One CVE with a non-trivial multi-file patch — exercises the rubric on a harder case.
2. For each CVE:
   - Vendor the pre-fix repo snapshot to `bench/vuln-remediation/snapshots/<cve>/` (or use `input-pointer.toml` if vendoring is rejected by repo size constraints).
   - Write `expected/diff.patch` (lift from the upstream commit).
   - Write `expected/validator_output.json` describing the expected validator JSON shape.
   - Compute `case_digest`; mint `cassette_canary_pin`.
   - Write `case.toml`.
3. Iterate the red test to green. Fix per-case issues (digest mismatch, missing files) until the suite passes.

### Refactor — clean up

- `bench/vuln-remediation/README.md` table: case_id ↔ CVE ↔ language ↔ upstream commit ↔ derivation date.
- Verify each case's `harness_output`-matched-against-`expected/` scoring works in `bench/vuln-remediation/tests/test_rubric_unit.py` by adding one happy-path test per held-out case.
- `last_validated_at` is set at curation time; the loader's "stale > 90 days" warning (edge case #20) will fire eventually — flag in the README.
- The CVE → case mapping is reviewed by CODEOWNERS at PR time; reviewer must confirm the CVE is genuinely held-out (the grep test is structural; reviewers add semantic confirmation).

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/cases/006-cve-XXXX-XXXXX-held-out/{case.toml, input/*, expected/*}` | New — first held-out case |
| `bench/vuln-remediation/cases/007-cve-XXXX-XXXXX-held-out/{case.toml, input/*, expected/*}` | New — second |
| `bench/vuln-remediation/cases/008-cve-XXXX-XXXXX-held-out/{case.toml, input/*, expected/*}` | New — third |
| `bench/vuln-remediation/cases/009-cve-XXXX-XXXXX-held-out/{case.toml, input/*, expected/*}` | New — fourth |
| `bench/vuln-remediation/cases/010-cve-XXXX-XXXXX-held-out/{case.toml, input/*, expected/*}` | New — fifth |
| `bench/vuln-remediation/snapshots/<cve>/...` | New (per case) — vendored pre-fix repo snapshots (if not pointer-based) |
| `bench/vuln-remediation/README.md` | Extend — CVE → case mapping table; corpus-cutoff date |
| `tests/integration/test_vuln_held_out_cases.py` | New — 5 structural assertions |
| `bench/vuln-remediation/tests/test_rubric_unit.py` | Extend — one happy-path test per held-out case |

## Out of scope

- **Signing in `digests.yaml`.** S5-05.
- **E2E run.** S5-05.
- **Cache invalidation tests.** S5-06.
- **The recipe / Phase 4 SUT.** This story does not touch Phase 4 internals. The held-out cases will be executed against whatever SUT Phase 6.5 wires in — the rubric is the scoring layer.
- **CVE-specific recipe authoring.** The bench measures the SUT; it does not author recipes for the SUT. If a held-out CVE doesn't fix correctly through the current pipeline, that is *data* — the rubric will score the failure honestly.

## Notes for the implementer

- **Start early.** Per `High-level-impl.md §Implementation-level risks #1`, this story is the long pole. The mitigation is: scaffold the case directories (via S5-07 `scripts/scaffold_bench_case.py`) in parallel with Step 3 work; populate `input/` / `expected/` as curation matures.
- **Real CVEs only.** Synthesized "fake CVE-2099-99999" cases are not acceptable — the cases must measure judgment on real vulnerability patches the LLM has plausibly not seen.
- **Public-data discipline.** CVE snapshots and upstream patches are public. Do not vendor proprietary or undisclosed-vulnerability material. CODEOWNERS review is the human gate; if in doubt, ask.
- **Snapshot size discipline.** A 100 MiB repo vendored 5 times is 500 MiB in the repo. Prefer `input-pointer.toml` pointing to a `git-lfs`-tracked snapshot, or a `git submodule`, or a tarball under `bench/vuln-remediation/snapshots/<cve>/snapshot.tar.gz` with a checksum. Document the choice; the loader (S2-02) should resolve pointers transparently — coordinate with S2-02's implementer if pointer resolution is incomplete.
- **`cassette_canary_pin` minting.** Use `Canary.mint()` from Phase 4 at curation time; pin the result. The pin's role is per-case determinism — different cases must have different pins or two case runs leak into each other through the canary. If `Canary.mint` doesn't accept `seed=...` at curation time, the value is whatever `mint()` returns (32 hex). ADR-0005 amends `Canary.mint(seed=...)` so the runner can re-derive the same canary at run time.
- **Disposition diversity.** Aim for at least 1 `negative` case (a CVE the SUT *should not* fix because the patch is wrong / has been reverted upstream) among the 5. Negative cases are higher-signal for judgment evaluation.
- **Difficulty diversity.** At least 1 `hard` case (multi-file patch, cross-cutting concern). Easy + medium + hard mix yields a more informative `lower_bound_95`.
- **`commit_sha`.** Required iff `source != "curated"`; for these `source="curated"` cases it is optional, but include the pre-fix commit SHA in the `case.toml` comment block for review/audit.
- **Coordination with S5-05.** S5-05 signs all 10 cases. If `case_digest` recomputation reveals drift here (e.g., a curator edits `input/` after computing the digest), S5-05's signing step will fail. Stabilize `input/`/`expected/` before computing the digest; do not re-edit after.
