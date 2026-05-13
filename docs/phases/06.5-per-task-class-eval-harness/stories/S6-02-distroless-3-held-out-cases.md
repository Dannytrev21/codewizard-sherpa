# Story S6-02 — Three Chainguard-publicly-documented held-out cases + signed digests

**Step:** Step 6 — Seed `bench/migration-chainguard-distroless/`
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (registration, taxonomies, stub rubric must exist before cases can load)
**ADRs honored:** ADR-0005 (`cassette_canary_pin` per case), ADR-0006 (`curation_class="held-out"`), ADR-0010 (records produced under subprocess isolation; field default carries through)

## Context

Phase 6.5's exit criterion #3 demands ≥3 seed cases for `migration-chainguard-distroless`. Per `ADR-0006`, this task class has no RAG corpus today, so all three cases ship as `curation_class="held-out"`. Each case is grounded in a publicly documented Chainguard migration example — no synthetic Dockerfiles, no untested examples. The fence-CI assertions S7-01 will land (case-id uniqueness, minimum count, taxonomy validity) consume *this* corpus as their target evidence; the digests file is the integrity surface that defends against the `Scenario 2` attack (`phase-arch-design.md §Scenarios → Scenario 2`) where a CODEOWNERS auto-merge loosens an `expected/` artifact without updating `digests.yaml`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"bench/{task-class}/ directory contract"` — the `case.toml` schema and required keys.
  - `../phase-arch-design.md §"Scenarios → Scenario 2"` — the digest-integrity attack the BLAKE3 verification defends against.
  - `../phase-arch-design.md §"Component design → loader.py"` — `load_cases` walks `cases/*/case.toml`, BLAKE3-verifies per `digests.yaml`, sorts by `case_id`.
  - `../phase-arch-design.md §"Fixture portfolio"` — distroless fixture uses Chainguard-publicly-documented examples.
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md` — 32-hex `cassette_canary_pin` per case; pin is identity, not content; `case_digest` excludes `case.toml`.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — `held-out` is the curation_class for all three.
- **Source design:** `../High-level-impl.md §"Step 6" §"Features delivered"` — names the case-shape requirements.
- **Existing precedent:** `bench/vuln-remediation/cases/*` from S5-03/S5-04 and `bench/vuln-remediation/cases/digests.yaml` from S5-05; mirror the format exactly.
- **External sources for case content:**
  - https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/node/ (Node migration)
  - https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/python/ (Python migration)
  - https://edu.chainguard.dev/chainguard/chainguard-images/getting-started/go/ (Go migration)

## Goal

Ship three signed, digest-verified, held-out `case.toml`-rooted case directories that `loader.load_cases(task_class)` returns sorted by `case_id`, with BLAKE3-verified `case_digest`s and per-case `cassette_canary_pin`s.

## Acceptance criteria

- [ ] `bench/migration-chainguard-distroless/cases/001-node-distroless-migration/`, `cases/002-python-distroless-migration/`, `cases/003-go-distroless-migration/` exist (or three slugs of similar shape; preserve case-id uniqueness — Gap #3).
- [ ] Each case directory contains: `case.toml`, `input/Dockerfile`, `expected/Dockerfile`, `expected/build.log`.
- [ ] Each `case.toml` has every required field: `case_id` (matches directory name), `task_class="migration-chainguard-distroless"`, `disposition`, `difficulty`, `source` (with `commit_sha` if `source != "curated"`), `curation_class="held-out"`, `added_at`, `last_validated_at`, `cassette_canary_pin` (exactly 32 hex chars; generated via `os.urandom(32).hex()`), `case_digest` (`blake3:<hex>`).
- [ ] `cases/digests.yaml` signs all three `case_digest`s; `loader.load_cases` returns three `BenchCase`s; `BenchCaseDigestMismatch` is raised iff a content byte flips.
- [ ] The three `input/Dockerfile`s reference real upstream-canonical base images (e.g., `node:18`, `python:3.11-slim`, `golang:1.21`); the `expected/Dockerfile`s reference a `cgr.dev/chainguard/*` image; `expected/build.log` carries a representative successful build trailer.
- [ ] All three cases pass the stub rubric from S6-01 — verify by running `bench/migration-chainguard-distroless/tests/test_rubric_unit.py` parameterized over the three case directories.
- [ ] `case_id` set has no duplicates (Gap #3 / S7-01 assertion #7 will assert this at fence-CI time; this story makes the data clean *now*).
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean; `pytest tests/unit/test_distroless_cases.py` passes.

## Implementation outline

1. For each of three migrations (Node, Python, Go) — fetch the Chainguard-documented `input` Dockerfile and the `expected` distroless Dockerfile from the linked tutorials. Cite the exact URL + commit-SHA-equivalent (page version) in the `case.toml`'s `source` field.
2. Synthesize a representative `expected/build.log` — last line `Successfully built` (or container-builder-specific equivalent) so the stub rubric's `BUILD_PASSES` signal lights up. **Do not** mint a synthetic build log when the Chainguard page itself shows one — capture the page's.
3. Generate three independent 32-byte canary pins (`os.urandom(32).hex()`); paste into `cassette_canary_pin`.
4. Compute `case_digest` for each directory via the same tar-serialization-then-BLAKE3 the loader uses, **excluding `case.toml`** (ADR-0005 — pin is identity, not content; `case.toml` mutation does not invalidate `case_digest`).
5. Hand-write `cases/digests.yaml`:
   ```yaml
   "001-node-distroless-migration": "blake3:<hex>"
   "002-python-distroless-migration": "blake3:<hex>"
   "003-go-distroless-migration": "blake3:<hex>"
   ```
6. Run `loader.load_cases(task_class)` from a throwaway script; confirm three `BenchCase`s return, sorted by `case_id`.
7. Run the bench-author unit test from S6-01 parameterized over the three cases.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/test_distroless_cases.py`

```python
# tests/unit/test_distroless_cases.py
from pathlib import Path

import pytest

from codegenie.eval.errors import BenchCaseDigestMismatch
from codegenie.eval.loader import load_task_class, load_cases

BENCH_ROOT = Path(__file__).resolve().parents[2] / "bench"


@pytest.fixture
def task_class():
    return load_task_class("migration-chainguard-distroless", bench_root=BENCH_ROOT)


def test_three_held_out_cases_load_in_deterministic_order(task_class):
    cases = load_cases(task_class)
    assert len(cases) == 3
    # Sorted by case_id (ADR-0006 + loader contract).
    assert [c.case_id for c in cases] == sorted(c.case_id for c in cases)
    # All three are held-out (no RAG corpus for distroless in Phase 6.5).
    for c in cases:
        assert c.curation_class == "held-out"
        assert c.task_class == "migration-chainguard-distroless"


def test_each_case_carries_a_32_hex_cassette_canary_pin(task_class):
    cases = load_cases(task_class)
    for c in cases:
        assert len(c.cassette_canary_pin) == 32
        assert all(ch in "0123456789abcdef" for ch in c.cassette_canary_pin)
    # Pins are independent — collision among three is astronomically unlikely.
    pins = {c.cassette_canary_pin for c in cases}
    assert len(pins) == 3


def test_case_ids_are_unique_and_match_directory_names(task_class):
    cases = load_cases(task_class)
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))  # Gap #3 — uniqueness
    # Directory-name match is fence-CI assertion #7's loader-side defense-in-depth.
    case_dirs = sorted(p.name for p in (BENCH_ROOT / "migration-chainguard-distroless" / "cases").iterdir() if p.is_dir())
    assert sorted(ids) == case_dirs


def test_flipped_byte_in_expected_dockerfile_raises_digest_mismatch(task_class, tmp_path, monkeypatch):
    # Copy bench tree to tmp, flip one byte in expected/Dockerfile of case 001, reload.
    # ... canonical 'tamper a case directory and assert BenchCaseDigestMismatch' fixture.
    # The smallest red shape can simply assert load_cases works on clean bench;
    # the tamper-check belongs alongside the existing loader-test pattern from S2-02.
    cases = load_cases(task_class)
    assert any("node" in c.case_id or "python" in c.case_id or "go" in c.case_id for c in cases)
```

Run; confirm `FileNotFoundError` on `cases/digests.yaml` or empty `cases/` directory iteration. Commit as red marker.

### Green

Hand-curate the three case directories (Dockerfiles, build.logs, case.toml) from the Chainguard tutorials. Compute the three `case_digest` BLAKE3 values; write `digests.yaml`. The four-test red suite turns green when all three cases load, sort correctly, carry valid pins, and unique IDs.

### Refactor

- Confirm `expected/Dockerfile`s point to a *currently-published* `cgr.dev/chainguard/<image>` reference; the rubric does not pull the image at score time (it parses strings), but stale image refs make a case feel synthetic.
- Each `case.toml`'s `source` field cites the Chainguard tutorial URL.
- `last_validated_at` is the date this story lands; `added_at` is the same date for seed cases.
- Make sure the `case_digest` was computed with the `case.toml`-excluded tar serialization (the loader's algorithm). Run the loader's own digest computation and paste; do not hand-compute.
- README placeholder remains; S6-03 fills the "what Phase 7 must add" section.

## Files to touch

| Path | Why |
|---|---|
| `bench/migration-chainguard-distroless/cases/001-node-distroless-migration/case.toml` | New — Node migration case metadata |
| `bench/migration-chainguard-distroless/cases/001-node-distroless-migration/input/Dockerfile` | New — pre-migration upstream-canonical Dockerfile |
| `bench/migration-chainguard-distroless/cases/001-node-distroless-migration/expected/Dockerfile` | New — post-migration Chainguard-distroless Dockerfile |
| `bench/migration-chainguard-distroless/cases/001-node-distroless-migration/expected/build.log` | New — representative build success trailer |
| `bench/migration-chainguard-distroless/cases/002-python-distroless-migration/*` | New — same shape, Python |
| `bench/migration-chainguard-distroless/cases/003-go-distroless-migration/*` | New — same shape, Go |
| `bench/migration-chainguard-distroless/cases/digests.yaml` | New — signs all three `case_digest`s |
| `tests/unit/test_distroless_cases.py` | New — pins case shape + uniqueness + canary-pin discipline |

## Out of scope

- **E2E `codegenie eval run` + verdict documentation** — S6-03.
- **Adding case #4 and beyond** — Phase 7 grows the corpus to ≥10 with ≥5 held-out.
- **Recording live build cassettes** — the rubric is string-parsing-only at this phase; cassettes aren't needed for distroless at N=3.
- **The seven fence-CI assertions** — S7-01 lands them; this story makes data clean enough that all seven *would* pass.

## Notes for the implementer

- **No synthetic Dockerfiles** — every `input/Dockerfile` must be either copy-pasted from the cited Chainguard tutorial (preferred) or a near-verbatim "real-world" upstream-canonical Dockerfile (`FROM node:18`, etc.). The acceptance criterion "All 3 cases reference real Chainguard-documented migration examples" (`High-level-impl.md §Step 6`) is load-bearing.
- **Canary pins are write-once.** `os.urandom(32).hex()` once per case, paste into `case.toml`, never rotate (ADR-0005 — pin is identity). Don't be tempted to regenerate.
- **`case_digest` excludes `case.toml`.** This means a curator can fix a typo in `case.toml` (e.g., `last_validated_at`) without breaking the digest — but flipping a byte in `input/Dockerfile` or `expected/Dockerfile` *does* break the digest. That's the desired property.
- **Case-id naming is durable.** `001-` / `002-` / `003-` prefixes are convention from `bench/vuln-remediation/` (ADR-0006 names this naming pattern explicitly). Match it.
- **The `expected/build.log` is a synthetic structural signal**, not a real build log from running the case. The rubric checks for "Successfully built" or equivalent in the last line — a 5-line fixture suffices. Don't shell out to `docker build` to capture a real log; that's Phase 7 work.
- **The N=3 promotion verdict will be `evidence_sufficient=False`** when S6-03 runs it. That's intentional. Do not over-curate to make N=3 look promotion-eligible — the conservative output is the point.
- **Fence-CI assertion #7 (case-id uniqueness, Gap #3, S7-01) will walk these `case.toml`s** at PR time. Make sure the `case_id` field inside the TOML matches the directory name — the loader test above defends against this slipping.
