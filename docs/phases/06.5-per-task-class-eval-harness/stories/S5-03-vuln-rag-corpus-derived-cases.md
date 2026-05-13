# Story S5-03 — vuln-remediation 5 RAG-corpus-derived cases

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (rubric exists; cases must be scoreable end-to-end before they're worth carrying)
**ADRs honored:** ADR-0005 (each case carries a 32-hex `cassette_canary_pin`; Phase 4 `Canary.mint(seed=...)` consumes it), ADR-0006 (these 5 cases are `curation_class="rag-corpus-derived"` — they verify the recipe/RAG pipeline doesn't regress against the corpus it was tuned on; they are **not** sufficient evidence for silver-tier promotion on their own)

## Context

ADR-0006 splits the bench corpus into two curation classes. The 5 RAG-corpus-derived cases land **first** and **mechanically** — they're constructed by extracting solved examples from Phase 4's `tests/cassettes/phase4/` cassette tree, which is the same corpus Phase 4's recipe-first/RAG-fallback path was tuned against. The point of these cases is *regression* coverage: if the pipeline degrades on cases it has already solved once, the harness will surface it. The point is explicitly **not** judgment evidence — ADR-0006 §Decision is unambiguous that promotion to silver requires 5 held-out cases (S5-04). These 5 are the schedule-permitting half of the 5+5 floor.

Mechanical construction matters because the long-pole curation work (S5-04) is hand-built CVE-fix ground truth. Shipping these 5 mechanically buys schedule margin for S5-04 without compromising the memorization-vs-judgment distinction.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — `case.toml` schema; required keys (`case_id`, `task_class`, `disposition`, `difficulty`, `source`, `curation_class`, `added_at`, `last_validated_at`, `cassette_canary_pin`, `case_digest`); optional `commit_sha`.
  - `../phase-arch-design.md §Data model → BenchCase` — required field shapes; `case_digest: str` is `"blake3:<hex>"`; `cassette_canary_pin: str` is 32 hex chars.
  - `../phase-arch-design.md §Testing strategy → Fixture portfolio` — names `bench/vuln-remediation/` as the production fixture, with the 5+5 split.
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Decision` — `Canary.mint(seed=bytes.fromhex(case.cassette_canary_pin))` is the per-case binding; the pin's 32 hex chars come from the cassette's canary at curation time.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Consequences` — naming convention `001-005-rag-corpus-derived-<slug>` (advisory; not fence-enforced); the cassette-derivation script is the curator's tool.
- **Production ADRs:** `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the upstream commitment these cases regression-test against.
- **Source design:** `../High-level-impl.md §Step 5` — "5 cases mechanically derived from `tests/cassettes/phase4/`".

## Goal

Construct exactly 5 `BenchCase` directories under `bench/vuln-remediation/cases/` with `curation_class="rag-corpus-derived"`, each derived from a `tests/cassettes/phase4/` solved-example cassette via a documented mechanical procedure, each carrying `case.toml`, `input/`, `expected/`, `cassette_canary_pin` (32 hex from the source cassette), and `case_digest` (BLAKE3 over `input/` + `expected/`).

## Acceptance criteria

- [ ] `bench/vuln-remediation/cases/` contains exactly 5 directories whose names follow the pattern `00{1..5}-<cve-or-slug>-rag-corpus-derived/`.
- [ ] Each case directory contains:
  - `case.toml` validating into a `BenchCase` with `curation_class="rag-corpus-derived"`, `source="curated"` (no `commit_sha` required; ADR-0006 §Consequences), `task_class="vuln-remediation"`, valid `disposition` (`positive|negative|ambiguous`), valid `difficulty` (`easy|medium|hard`), tz-aware UTC `added_at` and `last_validated_at`, `cassette_canary_pin` exactly 32 hex chars, `case_digest` prefixed `blake3:` with 64 hex chars.
  - `input/` directory with the bench-case's frozen input snapshot (or `input-pointer.toml` if pointing into `tests/cassettes/phase4/`; documented in `case.toml`).
  - `expected/` directory with ground-truth artifacts the rubric reads (e.g., `expected/diff.patch`, `expected/validator_output.json`).
- [ ] Each case is **mechanically traceable** to a `tests/cassettes/phase4/` cassette — a comment block at the top of each `case.toml` names the source cassette path and its commit SHA at derivation time.
- [ ] `loader.load_cases(task_class)` (S2-02) loads all 5 cases without raising; `task_class.bench_path` resolution returns them sorted by `case_id`.
- [ ] `loader` BLAKE3-verifies each case directory against the digest declared in `case.toml`; whitespace edit to any file under `input/` or `expected/` invalidates that case's digest (verified separately by S5-06's invalidation test).
- [ ] The 5 cases pair with the 5 held-out cases (S5-04) to satisfy the 10-case floor required for `min_cases_for_promotion["bronze"]=10`; **without** the held-out 5, fence-CI assertion #2 fails and the bench cannot promote at any tier.
- [ ] Running `codegenie eval run --task-class=vuln-remediation --cases='00{1..5}-*'` (subset to just these 5) exits 0 and produces a `BenchRunReport` whose `per_case` entries' `case_id`s match the 5 directory names.
- [ ] Red test from §TDD plan (`tests/integration/test_vuln_rag_corpus_derived_cases_load.py`) exists, was committed at red, now green; `ruff check`, `ruff format --check`, and `pytest tests/integration/test_vuln_rag_corpus_derived_cases_load.py` all pass.

## Implementation outline

1. Write the red test `tests/integration/test_vuln_rag_corpus_derived_cases_load.py` first — see §TDD plan.
2. **Identify 5 source cassettes** under `tests/cassettes/phase4/` representing solved examples (CVE fixes the Phase 4 pipeline successfully resolved at recipe-first or RAG-fallback). Document the selection criterion in `bench/vuln-remediation/README.md` (e.g., "5 highest-frequency CVE patterns across the cassette corpus").
3. **For each cassette**, run S5-07's `scripts/scaffold_bench_case.py` (or hand-write if S5-07 hasn't merged) to produce:
   - `case.toml` with all required keys filled.
   - `input/` populated from the cassette's pre-fix snapshot.
   - `expected/` populated from the cassette's post-fix snapshot (diff, validator output, etc.).
   - `cassette_canary_pin` extracted from the cassette's canary metadata (32 hex chars).
   - `case_digest` computed as BLAKE3 over `input/` + `expected/` (recursive byte-sorted-path BLAKE3, prefixed `blake3:`).
4. Verify each case loads:
   ```bash
   python -c "from codegenie.eval.loader import load_task_class, load_cases; tc = load_task_class('vuln-remediation', bench_root='bench'); cases = load_cases(tc); print([c.case_id for c in cases if c.curation_class == 'rag-corpus-derived'])"
   ```
5. Add a digests-yaml stub entry for each case (the full signing happens in S5-05).
6. Iterate test → green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_vuln_rag_corpus_derived_cases_load.py`

```python
# tests/integration/test_vuln_rag_corpus_derived_cases_load.py
"""5 RAG-corpus-derived cases must load cleanly. ADR-0006 §Consequences names
this curation class; we assert structural shape, not scoring correctness
(that is S5-05's E2E job)."""

import re
from pathlib import Path

import pytest

from codegenie.eval.loader import load_cases, load_task_class
from codegenie.eval.models import BenchCase


BENCH_ROOT = Path(__file__).parents[2] / "bench"


def test_exactly_five_rag_corpus_derived_cases_exist():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    cases = load_cases(tc)
    rag = [c for c in cases if c.curation_class == "rag-corpus-derived"]
    assert len(rag) == 5, f"expected 5 RAG-corpus-derived cases, found {len(rag)}"


def test_case_ids_follow_naming_convention():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    rag = [c for c in load_cases(tc) if c.curation_class == "rag-corpus-derived"]
    pattern = re.compile(r"^00[1-5]-.+-rag-corpus-derived$")
    for c in rag:
        assert pattern.match(c.case_id), f"{c.case_id!r} does not match the convention"


def test_every_case_has_32_hex_cassette_canary_pin():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    rag = [c for c in load_cases(tc) if c.curation_class == "rag-corpus-derived"]
    for c in rag:
        assert len(c.cassette_canary_pin) == 32
        assert all(ch in "0123456789abcdef" for ch in c.cassette_canary_pin)


def test_every_case_has_blake3_digest_with_64_hex():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    rag = [c for c in load_cases(tc) if c.curation_class == "rag-corpus-derived"]
    for c in rag:
        assert c.case_digest.startswith("blake3:")
        assert len(c.case_digest) == len("blake3:") + 64


def test_every_case_directory_has_input_and_expected_subdirs():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    rag = [c for c in load_cases(tc) if c.curation_class == "rag-corpus-derived"]
    for c in rag:
        assert c.input_path.is_dir(), f"{c.case_id}: input/ missing"
        assert c.expected_path.is_dir(), f"{c.case_id}: expected/ missing"
        assert any(c.input_path.iterdir()), f"{c.case_id}: input/ empty"
        assert any(c.expected_path.iterdir()), f"{c.case_id}: expected/ empty"


def test_case_toml_documents_source_cassette_path():
    """ADR-0006 §Consequences: each case traces to a tests/cassettes/phase4/ cassette."""
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    rag = [c for c in load_cases(tc) if c.curation_class == "rag-corpus-derived"]
    for c in rag:
        toml_path = BENCH_ROOT / "vuln-remediation" / "cases" / c.case_id / "case.toml"
        text = toml_path.read_text()
        assert "tests/cassettes/phase4/" in text, (
            f"{c.case_id}: case.toml does not document source cassette"
        )
```

Run it; confirm zero cases exist or wrong count. Commit as red marker.

### Green — smallest impl shape

1. Select 5 source cassettes by walking `tests/cassettes/phase4/` and choosing the 5 solved-example cassettes most representative of the recipe/RAG-fallback paths.
2. For each, scaffold via `scripts/scaffold_bench_case.py --task-class=vuln-remediation --source-cassette=...` (or hand-build):
   - `bench/vuln-remediation/cases/00N-<slug>-rag-corpus-derived/`
     - `case.toml` (with a `# Derived from: tests/cassettes/phase4/<path>` comment block)
     - `input/<files>`
     - `expected/<files>`
3. Compute `case_digest` for each:
   ```python
   import blake3, pathlib
   def case_digest(case_dir: pathlib.Path) -> str:
       h = blake3.blake3()
       for p in sorted((case_dir / "input").rglob("*"), key=lambda x: str(x)):
           if p.is_file():
               h.update(str(p.relative_to(case_dir)).encode()); h.update(p.read_bytes())
       for p in sorted((case_dir / "expected").rglob("*"), key=lambda x: str(x)):
           if p.is_file():
               h.update(str(p.relative_to(case_dir)).encode()); h.update(p.read_bytes())
       return "blake3:" + h.hexdigest()
   ```
4. Iterate until the red test goes green.

### Refactor — clean up

- `bench/vuln-remediation/README.md` documents the selection criterion and the source-cassette → case mapping (a table: case_id ↔ cassette path ↔ derivation commit SHA).
- Each `case.toml`'s comment block names the ADR (`# curation_class per ADR-0006`) and the source cassette.
- Sort the case directories alphabetically by `case_id`; the loader will do that anyway, but readable directory listing helps reviewers.
- If two RAG-corpus-derived cases happen to share a `case_id` slug (collision), the loader (S2-02) raises `BenchCaseIDCollision`; resolve at curation time by renaming with the CVE identifier.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/cases/001-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — first RAG-derived case |
| `bench/vuln-remediation/cases/002-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — second case |
| `bench/vuln-remediation/cases/003-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — third case |
| `bench/vuln-remediation/cases/004-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — fourth case |
| `bench/vuln-remediation/cases/005-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — fifth case |
| `bench/vuln-remediation/README.md` | Extend — source-cassette → case mapping table |
| `tests/integration/test_vuln_rag_corpus_derived_cases_load.py` | New — pins structural shape + naming convention |

## Out of scope

- **The held-out 5 cases.** S5-04 owns those (the long-pole).
- **`digests.yaml` signing.** S5-05 signs all 10 cases at once; this story only computes per-case `case_digest` strings into each `case.toml`.
- **The E2E run.** S5-05 exercises the cases through `codegenie eval run`. Here we only assert they *load*.
- **`scripts/scaffold_bench_case.py`.** Built in S5-07; this story may or may not depend on it depending on merge order. If it doesn't exist, hand-build the 5 cases. Both paths produce the same artifacts.
- **Promotion verdict.** With 5/10 cases, fence-CI #2 fails; running `codegenie eval run --task-class=vuln-remediation` against the *full* bench requires S5-04. Limit testing here to the `--cases='00{1..5}-*'` subset.

## Notes for the implementer

- Mechanical derivation does **not** mean "no review". Each case is CODEOWNERS-gated under `bench/vuln-remediation/cases/` and must reflect a real solved cassette. Synthesized or fabricated inputs are not acceptable.
- The `cassette_canary_pin` value is the canary from the *source cassette*, not a fresh one. Phase 4 cassettes carry a canary metadata field; extract it (32 hex chars). If the source cassette pre-dates ADR-0005 (Phase 4 amendment), pick a deterministic 32-hex derivation: `blake3.blake3(cassette_path.encode()).hexdigest()[:32]` — and note this in `case.toml`.
- `input/` may be large. Use `input-pointer.toml` (a TOML file pointing into `tests/cassettes/phase4/<path>`) if the snapshot is > ~1 MiB. The loader resolves pointers transparently; `case_digest` is computed over the *resolved* path content.
- The `disposition` field: positive (the SUT *should* fix this CVE), negative (the SUT *should* refuse to fix), ambiguous (unclear). For RAG-corpus-derived cases, expect ~5 positive (the cassette corpus is solved examples).
- The `difficulty` field is curator-assigned at derivation time. RAG-corpus-derived cases skew easy (the pipeline already solved them); annotate honestly.
- If two RAG-derived cases overlap on CVE (e.g., two cassettes both fix CVE-2024-12345), pick one — the bench is fact, not redundancy. The other becomes either a held-out case (if it represents independent judgment) or discarded.
- The `case_digest` computation must be deterministic and reproducible: sorted recursive walk by relative path; `blake3` over (relative-path-bytes || file-bytes) for each file. Document the algorithm in `bench/vuln-remediation/README.md` so curators can verify by hand if needed.
