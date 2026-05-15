# Story S6-01 — Golden file `node_typescript_helm` + `scripts/regen_golden.py`

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** M
**Depends on:** S5-05
**ADRs honored:** ADR-0002 (memo determinism), ADR-0004 (sub-schema strictness), ADR-0007 (warning-ID pattern stable in golden output), Phase 0 ADR-0008 (sanitizer redacts host-paths from rendered envelope)

## Validation notes (2026-05-15)

This story was hardened by `phase-story-validator`. Key corrections (full report under `_validation/S6-01-golden-file-regen.md`):

- **Critical structural bug fixed.** Original `_strip_wall_clock` targeted `data.get("audit", {})`. The actual envelope (per `src/codegenie/cli.py:423-440` + `src/codegenie/schema/repo_context.schema.json`) has top-level keys `{schema_version, generated_at, repo, probes}` — **no `audit` block exists in the envelope** (audit `RunRecord` lives in `.codegenie/context/runs/*.json`, a sidecar). The original strip would have been a silent no-op, and the golden would have contained `generated_at` (ISO-8601 wall-clock) → CI fails on the very next gather.
- **Two non-determinism sources missed.** `generated_at` (top-level UTC timestamp from `datetime.now(UTC)`) AND `repo.git_commit` (resolves via `git rev-parse HEAD` — and since fixtures live inside this repo without their own `.git/`, it resolves to the **parent codewizard-sherpa commit**, which moves with every commit). Both must be normalized in the strip pass.
- **Manual sha256 in PR body promoted to CI gate.** Two-run idempotence is now a unit-test (`test_regen_golden_idempotent.py`) — humans miss things; CI doesn't.
- **`_strip_wall_clock` duplication parity test added.** Script + test-side helpers share a single `_NORMALIZED_FIELDS` constant (single source of truth, Rule 7).
- **Open/Closed seam for Phase 2.** Hardcoded fixture/golden/slice-set replaced with a single `_GOLDEN_PAIRS` tuple at module top — Phase 2's second golden is one entry, zero edits to `main()`. Not premature abstraction (Rule 2): one concrete pair today, the second is named in this story's Out-of-scope as "Phase 7 will want a 2nd golden", and the Phase 2 broader portfolio is named in `phase-arch-design.md §"Golden files"`.
- **Schema re-validation + warning-ID pattern + path-leak negative tests added** as integration assertions (closes ADR-0004, ADR-0007, ADR-0008 traceability gaps).
- **Failure-message ergonomics tightened**: the diff-failure message includes the *exact* `python scripts/regen_golden.py` path and a reminder to inspect `git diff tests/golden/` before committing.

## Context

Phase 1 has produced six populated Layer A slices on `tests/fixtures/node_typescript_helm/` and the end-to-end integration test (S5-05) asserts the slices are present, the envelope validates, and the audit anchor re-computes. What it does **not** yet assert is *byte-identical output* across runs — the deterministic-gather invariant that every downstream phase (continuous gather in Phase 14, recipe inputs in Phase 3, distroless inputs in Phase 7) relies on. The golden file is the seam that turns "deterministic" from an aspiration into a CI gate.

This story lands `tests/golden/node_typescript_helm.repo-context.yaml` (canonical key-sorted YAML, every wall-clock and unstable-environmental field normalized) plus `scripts/regen_golden.py` (the only sanctioned way to update it). The integration test from S5-05 is extended to diff live output against the golden as a hard CI gate.

Golden files are notoriously brittle to non-determinism. The Phase 0 commitment that `gather` is deterministic on identical content carries the load here, but the **actual** non-deterministic envelope fields are:

| Field | Source | Why non-deterministic |
|---|---|---|
| `generated_at` | `datetime.now(UTC)` in `src/codegenie/cli.py:425` | Wall-clock at gather time. |
| `repo.git_commit` | `git rev-parse HEAD` from fixture path | Fixture has no `.git/`; git walks up to codewizard-sherpa's `.git/` → returns this repo's HEAD, which moves on every commit. |

There is **no `audit` block at the envelope root** — `wall_clock_ms` lives in the audit `RunRecord` written to `.codegenie/context/runs/<run-id>.json` (a sidecar produced by `_seam_audit_record`), not in `repo-context.yaml`. The integration test from S5-05 already exercises the audit anchor via `codegenie audit verify`; the golden does not duplicate that surface.

Both `generated_at` and `repo.git_commit` are normalized to fixed sentinels (`"<NORMALIZED>"`) by the strip helper before the golden is written and before the live envelope is compared. Sentinel values (rather than field deletion) preserve the envelope's required-fields shape — `repo_context.schema.json` requires `schema_version`, `generated_at`, `repo`, `probes` — so the post-normalize bytes still validate against the envelope schema, which is itself a re-asserted invariant in this story (AC-VAL-1).

This is the canonical example Phase 2 expands. Phase 2's broader golden portfolio (more fixtures, IndexHealthProbe slices, possibly Go/Java fixtures) follows the same shape — sorted keys, normalized non-deterministic fields, single regen script as the only mutation path. The Open/Closed seam for that expansion is a single `_GOLDEN_PAIRS` tuple at the top of `scripts/regen_golden.py` and the matching tuple in `tests/integration/probes/_golden_helpers.py`; Phase 2 adds one entry per golden, no `main()` edits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" / "Golden files"` — `tests/golden/node_typescript_helm.repo-context.yaml` is the seed; updating it is a deliberate PR step with a `regen` script under `scripts/regen_golden.py`. Phase 2's broader golden portfolio extends the convention.
  - `../phase-arch-design.md §"Testing strategy" / "CI gates"` — the `test` job runs `pytest` including the golden diff; `--cov-fail-under=90` ratchet (S6-02 enforces).
  - `../phase-arch-design.md §"Integration with Phase 2"` — Phase 2 reads `.codegenie/context/repo-context.yaml` and extends the golden portfolio; Phase 1's golden is the shape contract.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — ADR-0002 — the memo is per-gather; cache-hit second run must produce byte-identical slices. The golden is the proof.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — ADR-0004 — every slice in the golden conforms to its sub-schema; the integration test re-validates after diff (AC-VAL-1).
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — every warning ID present in the golden matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Re-asserted (AC-VAL-2).
- **Phase 0 ADRs (load-bearing for this story):**
  - `../../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — Phase 0 ADR-0008 — sanitizer redacts host-path prefixes (`/Users/<u>/...`, `/home/<u>/...`, tmpdirs) from the rendered envelope. The golden is a regression canary for that redaction (AC-NEG-1).
- **High-level impl plan:**
  - `../High-level-impl.md §"Step 6"` — features delivered: `tests/golden/node_typescript_helm.repo-context.yaml` (seed golden); `scripts/regen_golden.py` (canonical YAML ordering).
  - `../High-level-impl.md §"Implementation-level risks" #6` — golden non-determinism: regen script normalizes wall-clock + unstable-environmental fields; run twice locally and verify byte-identical output before opening the Step 6 PR. (Promoted to CI gate in this story — AC-IDEM-1.)
  - `../High-level-impl.md §"Step 6 — Done criteria"` bullet 1 and 2 — golden exists, canonically ordered; `regen_golden.py` produces byte-identical output across two consecutive runs.
- **Manifest:**
  - `../stories/README.md` — S6-01 row; Definition-of-done section.
- **Existing code (consumed by this story):**
  - `src/codegenie/cli.py:423-440` — envelope construction (`schema_version`, `generated_at`, `repo`, `probes`); confirm the field list against this on every revision.
  - `src/codegenie/schema/repo_context.schema.json` — envelope schema; required-fields drive the choice of "normalize, don't delete."
  - `src/codegenie/coordinator/snapshot.py:59` — `_resolve_git_commit`; explains why `repo.git_commit` is the parent-repo HEAD on fixture paths.
  - `src/codegenie/output/writer.py` — the YAML writer (`yaml.dump(..., sort_keys=False)` — note the writer does NOT sort; the regen+integration test re-serialize with `sort_keys=True` for canonical comparison).
  - `tests/integration/probes/conftest.py` — `_load_envelope`, `_stub_node_version_check`, `WARM_PATH_CACHE_HIT_PROBES`, `PHASE_1_PROBE_NAMES`, `PHASE_1_PROBE_TO_SLICE` (S5-05 lifted these); reuse, do not shadow.
  - `tests/fixtures/node_typescript_helm/` — the fixture (S2-03); the golden's input.
  - `tests/integration/probes/test_layer_a_end_to_end.py` (S5-05) — extended in this story to diff against the golden.
  - `scripts/regen_probe_contract_snapshot.py` — prior-art regen script (single-fixture, hand-rolled). This story is the **2nd** regen script in the codebase; Phase 2 adds the 3rd. Rule of three not yet met → no shared regen kernel — but the per-script `_GOLDEN_PAIRS` data shape is the discoverable seam if it is ever extracted.
- **Prior `_validation/` reports for the family:**
  - `_validation/S5-05-integration-end-to-end.md` — established the `WARM_PATH_CACHE_HIT_PROBES` Open/Closed seam, lifted `PHASE_1_PROBE_NAMES` + `PHASE_1_PROBE_TO_SLICE` to conftest, and `_stub_node_version_check` reuse. This story consumes those.

## Goal

Land `tests/golden/node_typescript_helm.repo-context.yaml` (canonical key-sorted YAML, all non-deterministic fields normalized to fixed sentinels) and `scripts/regen_golden.py` (the only sanctioned way to update it); the S5-05 integration test diffs live output against the golden as a hard CI gate; two consecutive regen runs produce byte-identical output, enforced by a unit test.

## Acceptance criteria

### Group GOLDEN — the file itself

- [ ] **AC-GOLDEN-1.** `tests/golden/node_typescript_helm.repo-context.yaml` exists and is generated by `yaml.safe_dump(envelope, sort_keys=True, default_flow_style=False, width=120, allow_unicode=True)` (UTF-8 bytes; trailing newline as `safe_dump` produces).
- [ ] **AC-GOLDEN-2.** The golden contains all six Layer A probe entries under `probes`: `language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory` (per `tests/integration/probes/conftest.py PHASE_1_PROBE_NAMES`).
- [ ] **AC-GOLDEN-3.** The golden's `generated_at` value equals the fixed sentinel string `"<NORMALIZED>"` and `repo.git_commit` equals `"<NORMALIZED>"`. (Field presence is preserved because `repo_context.schema.json` lists both as required; the values are constants so the file is byte-stable across machines and across calendar time.)
- [ ] **AC-GOLDEN-4.** The golden re-validates against the envelope schema and every per-probe sub-schema *after* the normalization pass (i.e., post-strip bytes are still a valid `RepoContext`). Asserted by AC-VAL-1's test.

### Group SCRIPT — `scripts/regen_golden.py`

- [ ] **AC-SCRIPT-1.** `scripts/regen_golden.py` exposes a `_GOLDEN_PAIRS: tuple[GoldenPair, ...]` module-level constant where each `GoldenPair` is a typed (frozen `dataclass` or `NamedTuple`) record carrying `(fixture_dir: Path, golden_path: Path, required_probes: frozenset[str])`. Phase 1 ships exactly **one** pair; Phase 2 adds new goldens by appending new entries — `main()` iterates `_GOLDEN_PAIRS` and contains no fixture-specific literals. (Open/Closed at the file boundary — extension by addition, never by edit. CLAUDE.md "Extension by addition".)
- [ ] **AC-SCRIPT-2.** `main()` invokes the in-process CLI (Click `CliRunner` against `codegenie.cli.cli`) — **not** `subprocess.run(["codegenie", ...])` — so the regen script does not depend on the package being `pip install`-ed in the developer's PATH and surfaces probe failures as Python tracebacks rather than opaque exit codes. (Mirrors `tests/integration/probes/conftest.py` invocation pattern.)
- [ ] **AC-SCRIPT-3.** The script applies `_normalize_envelope(envelope)` (a pure function — see AC-PURE-1) before serializing. The function rewrites `generated_at` and `repo.git_commit` to `"<NORMALIZED>"` and is the only normalization site.
- [ ] **AC-SCRIPT-4.** The script verifies all `pair.required_probes` are present under `envelope["probes"]` after gather; missing probes → exit `2` with the missing set on stderr (e.g., `missing probes for golden node_typescript_helm: {'test_inventory'}`).
- [ ] **AC-SCRIPT-5.** Exit codes: `0` on success; `1` if `codegenie gather` exits non-zero (relayed); `2` on missing-probes; `3` if the post-normalize envelope fails schema validation (script writes nothing in this case, surfacing the bug rather than persisting a bad golden).
- [ ] **AC-SCRIPT-6.** The script prints `wrote {path} sha256={hex}` for each golden after writing. (Used by humans for sanity-check; not a CI gate — see AC-IDEM-1.)
- [ ] **AC-SCRIPT-7.** `ruff check`, `ruff format --check`, `mypy --strict` pass on `scripts/regen_golden.py`. The script imports nothing outside `[project] dependencies` (i.e., does not need `dev` extras to run).

### Group PURE — pure normalization helper, single source of truth

- [ ] **AC-PURE-1.** `_normalize_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]` lives in **one** module — `tests/integration/probes/_golden_helpers.py` — and is imported by both `scripts/regen_golden.py` and the integration test. The list of normalized field paths is a single module-level constant `_NORMALIZED_FIELDS: Final[frozenset[tuple[str, ...]]] = frozenset({("generated_at",), ("repo", "git_commit")})`. (Rule 7 — single source of truth; Rule 11 — match codebase's typed-frozenset closed-set convention.)
- [ ] **AC-PURE-2.** `_normalize_envelope` is **pure** (no I/O, no time, no random) — given the same input dict it returns equal bytes when re-serialized. Unit-tested at `tests/unit/integration/test_golden_helpers.py::test_normalize_envelope_is_pure`.
- [ ] **AC-PURE-3.** Mutation-resistance unit test: `tests/unit/integration/test_golden_helpers.py::test_normalize_envelope_strips_each_field_path` — for each path in `_NORMALIZED_FIELDS`, construct a full minimal envelope, call `_normalize_envelope`, assert the leaf at that path equals `"<NORMALIZED>"` and the rest of the envelope is bit-equal to the input (deep-copy comparison). This test fails immediately if `_normalize_envelope` ever degrades to "return data unchanged" (the original story's no-op bug).
- [ ] **AC-PURE-4.** Negative coverage: a synthetic envelope **without** any of the normalized paths (e.g., a spec-non-conforming dict missing `generated_at`) does not raise; `_normalize_envelope` is robust to absence (defensive — non-coordinator constructed dicts may be incomplete). The function uses key-defensive traversal, never `KeyError`-raising indexing.

### Group IDEM — idempotence, enforced by CI

- [ ] **AC-IDEM-1.** `tests/unit/scripts/test_regen_golden_idempotent.py` runs `regen_golden.main()` twice into a temp directory (monkeypatching `_GOLDEN_PAIRS` to point at a temp golden path; fixture path stays at `tests/fixtures/node_typescript_helm/`) and asserts `sha256(temp_golden.read_bytes()) == sha256(temp_golden.read_bytes())` after the second run. **CI fails this story's PR if idempotence breaks** — no longer a manual PR-body verification (original story Risk #6).
- [ ] **AC-IDEM-2.** The same test asserts `_strip_wall_clock` (i.e., `_normalize_envelope`) was *actually applied* during the run by reading the produced golden bytes and asserting `b"<NORMALIZED>"` appears. (Mutation-killer: if a future refactor accidentally bypasses normalization, the produced golden will contain a real timestamp and this assertion fails.)

### Group DIFF — integration-test gate

- [ ] **AC-DIFF-1.** `tests/integration/probes/test_layer_a_end_to_end.py` is extended with `test_layer_a_end_to_end_matches_golden(tmp_path)` that:
  1. Runs `codegenie gather` against `tests/fixtures/node_typescript_helm/` via `CliRunner`.
  2. Loads the live envelope via `conftest._load_envelope`.
  3. Applies `_normalize_envelope` (the same pure function from AC-PURE-1).
  4. Re-serializes via `yaml.safe_dump(..., sort_keys=True, default_flow_style=False, width=120, allow_unicode=True)`.
  5. Asserts byte-equality against `tests/golden/node_typescript_helm.repo-context.yaml`.
- [ ] **AC-DIFF-2.** On byte mismatch, the failure message contains exactly:
  - the unified diff (via `difflib.unified_diff`, `fromfile="golden"`, `tofile="live"`, `lineterm=""`), truncated to the first 80 lines or 4000 characters, whichever shorter;
  - the literal regen invocation `python scripts/regen_golden.py`;
  - the literal reminder `Inspect the diff with: git diff tests/golden/`.
- [ ] **AC-DIFF-3.** The integration test uses `_stub_node_version_check` from conftest (S5-05's pattern) to neutralize `node --version` exec; otherwise the live envelope's `build_system.node_version_resolved_locally` will vary by contributor machine and the diff will fail on every developer.
- [ ] **AC-DIFF-4.** The integration test asserts the **golden file exists** with a clear setup error when absent (`pytest.fail(f"Golden missing at {path}. First-time setup: python scripts/regen_golden.py")`). This is distinct from a byte mismatch; surfaces "you forgot to run regen" vs. "you have a real divergence."

### Group VAL — schema + ADR-0007 + sanitizer re-validation

- [ ] **AC-VAL-1.** Same integration test re-validates the **post-normalize** envelope against the envelope schema via `codegenie.schema.validator.validate(envelope)` and asserts no `SchemaValidationError`. Catches the case where a future normalization choice (e.g., dropping a required field) silently breaks ADR-0004 / envelope schema.
- [ ] **AC-VAL-2.** Same integration test walks every `probes[*][slice_key].warnings` list (where present) and asserts each entry matches the ADR-0007 pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` via `re.fullmatch`. Catches a regression where a probe sneaks a prose-judgment warning into the golden output, defeating the structural defense.

### Group NEG — host-path leak canary

- [ ] **AC-NEG-1.** Same integration test asserts the golden bytes contain **no** absolute host-path prefix (`/Users/`, `/home/`, `/tmp/`, `/var/folders/`, the test's own `tmp_path` resolved to its parent root, and `os.path.expanduser("~")`). This is a regression canary for Phase 0 ADR-0008's `OutputSanitizer` redaction; if a probe ever bypasses the sanitizer and leaks a fixture absolute path, the golden becomes machine-specific and this AC fails. (Belt-and-suspenders — the sanitizer is the load-bearer; this is a downstream tripwire.)

### Group DOC — discoverability

- [ ] **AC-DOC-1.** `scripts/regen_golden.py` module docstring states (a) when to run it ("after a deliberate change to a Phase 1 probe's slice shape; commit the golden diff alongside the probe change in the same PR"); (b) the field list normalized (`generated_at`, `repo.git_commit`) and *why* (host-portability, no commit churn); (c) the Phase 2 extension recipe ("append a new `GoldenPair(...)` to `_GOLDEN_PAIRS`; no `main()` edits").
- [ ] **AC-DOC-2.** `Makefile` adds `regen-golden:` target invoking `python scripts/regen_golden.py`. Optional but listed as a `done` criterion under `High-level-impl.md §"Step 6"`; landed in this story for contributor ergonomics.
- [ ] **AC-DOC-3.** `tests/integration/probes/test_layer_a_end_to_end.py` module-level docstring (or the new test's docstring) explains that the golden is the deterministic-gather CI gate, that updating it is intentional, and that the regen path is `python scripts/regen_golden.py`. Surfaces the workflow to anyone reading the test for the first time.

### Group DOD — Phase 1 done-criteria mapping

- [ ] **AC-DOD-1.** `ruff check`, `ruff format --check`, `mypy --strict` pass on every file touched in this story.
- [ ] **AC-DOD-2.** The new integration test passes on Python 3.11 and 3.12 in CI; `tests/unit/integration/test_golden_helpers.py` and `tests/unit/scripts/test_regen_golden_idempotent.py` pass on both.
- [ ] **AC-DOD-3.** No new dependency added to `pyproject.toml [project] dependencies` (PyYAML, click, structlog already present); the regen script and helpers are stdlib + existing deps only.

## Implementation outline

Landing order — primitives first (helpers + types), then script, then integration extension, then docs. Each step lands its tests in the same PR.

1. **Land the shared helper module first.** Create `tests/integration/probes/_golden_helpers.py` containing:
   - `_NORMALIZED_FIELDS: Final[frozenset[tuple[str, ...]]] = frozenset({("generated_at",), ("repo", "git_commit")})`
   - `_NORMALIZED_SENTINEL: Final[str] = "<NORMALIZED>"`
   - `def _normalize_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]` — deep-copies the input, walks each path in `_NORMALIZED_FIELDS`, sets the leaf to the sentinel if the parent dict exists. No `KeyError` on absent paths (AC-PURE-4).
   - `def _golden_yaml_bytes(envelope: Mapping[str, Any]) -> bytes` — applies `_normalize_envelope` then `yaml.safe_dump(..., sort_keys=True, default_flow_style=False, width=120, allow_unicode=True).encode("utf-8")`. **The single canonical serializer.** Both the script and the integration test use this — there is no second `yaml.safe_dump` call in either site.
   Land `tests/unit/integration/test_golden_helpers.py` covering AC-PURE-2, AC-PURE-3, AC-PURE-4. RED → GREEN → REFACTOR cycle.

2. **Land the script.** Create `scripts/regen_golden.py`:
   - Import the helper from step 1 (`from tests.integration.probes._golden_helpers import _golden_yaml_bytes, _normalize_envelope`). The `tests/` package import is the single point where the regen script crosses into test territory; it's intentional (the script and the tests share one canonical normalizer; AC-PURE-1).
   - Module-level `@dataclass(frozen=True) class GoldenPair: fixture_dir: Path; golden_path: Path; required_probes: frozenset[str]` plus `_GOLDEN_PAIRS: Final[tuple[GoldenPair, ...]] = (GoldenPair(...),)` — the one-entry tuple (AC-SCRIPT-1).
   - `main()` iterates `_GOLDEN_PAIRS`, runs gather via `CliRunner` against `codegenie.cli.cli` with `["gather", str(pair.fixture_dir), "--output", str(tmpdir)]` (AC-SCRIPT-2), loads the produced envelope, asserts required probes (AC-SCRIPT-4), normalizes + serializes via `_golden_yaml_bytes` (AC-SCRIPT-3), schema-validates (AC-SCRIPT-5: exit 3 if it fails — DON'T write the golden), writes atomically via `Path.write_bytes` to `pair.golden_path`, prints the sha256 (AC-SCRIPT-6).
   - Land `tests/unit/scripts/test_regen_golden_idempotent.py` covering AC-IDEM-1 + AC-IDEM-2.

3. **Generate the golden.** Run `python scripts/regen_golden.py` once locally; verify the file landed, sha256 printed. Run again; verify the printed sha256 matches. (CI confirms via AC-IDEM-1; this is the developer's belt.)

4. **Land the integration test extension.** Add `test_layer_a_end_to_end_matches_golden` to `tests/integration/probes/test_layer_a_end_to_end.py`:
   - Use `_stub_node_version_check` (AC-DIFF-3) — non-negotiable for cross-machine stability.
   - Run gather via `CliRunner`, load envelope via `_load_envelope`, normalize+serialize via `_golden_yaml_bytes` (the same helper the script uses — AC-DIFF-1).
   - Assert byte-equality against the golden; on mismatch raise with the prescribed message (AC-DIFF-2).
   - Add the AC-VAL-1 schema re-validation, AC-VAL-2 warning-ID pattern walk, AC-NEG-1 host-path leak canary, AC-DIFF-4 missing-golden setup error.

5. **Land the Makefile target + docstrings.** `make regen-golden` (AC-DOC-2). Module docstring on the script (AC-DOC-1). Test-file or test docstring (AC-DOC-3).

6. **Confirm `pytest tests/integration/probes/test_layer_a_end_to_end.py tests/unit/integration/ tests/unit/scripts/` passes locally on Python 3.11 AND 3.12 before opening the PR.** AC-DOD-2 is a CI gate; local verification catches it earlier.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Three test files, in dependency order. Land all three RED before any GREEN.

**Test file 1 — `tests/unit/integration/test_golden_helpers.py`:**

```python
"""Pure-helper tests for _golden_helpers (story S6-01 AC-PURE-{1..4})."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.integration.probes._golden_helpers import (
    _NORMALIZED_FIELDS,
    _NORMALIZED_SENTINEL,
    _normalize_envelope,
    _golden_yaml_bytes,
)


def _full_envelope() -> dict[str, Any]:
    """A minimal envelope with every required field populated."""
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-15T10:30:00Z",
        "repo": {"root": "node_typescript_helm", "git_commit": "deadbeef" * 5},
        "probes": {"language_detection": {"language_stack": {"primary": "typescript"}}},
    }


def test_normalize_envelope_is_pure() -> None:
    """Pure: same input → same output (AC-PURE-2)."""
    src = _full_envelope()
    src_copy = copy.deepcopy(src)
    out_a = _normalize_envelope(src)
    out_b = _normalize_envelope(src)
    assert out_a == out_b
    # Input is not mutated.
    assert src == src_copy


@pytest.mark.parametrize("path", sorted(_NORMALIZED_FIELDS))
def test_normalize_envelope_strips_each_field_path(path: tuple[str, ...]) -> None:
    """Mutation-killer (AC-PURE-3): every field in _NORMALIZED_FIELDS becomes the sentinel.

    If _normalize_envelope is ever degraded to ``return data`` (the original
    story's no-op bug), this test fails for every path in the parametrize.
    """
    env = _full_envelope()
    out = _normalize_envelope(env)
    cur: Any = out
    for key in path:
        cur = cur[key]
    assert cur == _NORMALIZED_SENTINEL


def test_normalize_envelope_preserves_other_fields() -> None:
    """Non-normalized fields (e.g., probes.*) survive byte-for-byte."""
    env = _full_envelope()
    out = _normalize_envelope(env)
    assert out["schema_version"] == env["schema_version"]
    assert out["repo"]["root"] == env["repo"]["root"]
    assert out["probes"] == env["probes"]


def test_normalize_envelope_robust_to_absent_paths() -> None:
    """AC-PURE-4: an envelope missing a normalized path does not raise."""
    env = {"schema_version": "0.1.0", "probes": {}}  # no generated_at, no repo
    out = _normalize_envelope(env)
    assert out == {"schema_version": "0.1.0", "probes": {}}


def test_golden_yaml_bytes_is_canonical() -> None:
    """Sorted keys, no flow style, UTF-8 bytes ending in newline."""
    env = _full_envelope()
    body = _golden_yaml_bytes(env)
    assert isinstance(body, bytes)
    text = body.decode("utf-8")
    # Sorted top-level keys (G < P < R < S → generated_at, probes, repo, schema_version).
    keys_in_order = [line.split(":", 1)[0] for line in text.splitlines() if line and not line.startswith(" ")]
    assert keys_in_order == sorted(keys_in_order)


def test_golden_yaml_bytes_contains_normalized_sentinel() -> None:
    """AC-IDEM-2: the produced bytes carry the sentinel for normalized fields."""
    env = _full_envelope()
    body = _golden_yaml_bytes(env)
    assert b"<NORMALIZED>" in body
```

**Test file 2 — `tests/unit/scripts/test_regen_golden_idempotent.py`:**

```python
"""Idempotence + actually-applied-normalization tests (S6-01 AC-IDEM-{1,2})."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import scripts.regen_golden as regen


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "node_typescript_helm"


def _redirect_to_tmp(tmp_path: Path) -> tuple:
    """Build a one-entry _GOLDEN_PAIRS tuple pointing at a temp path."""
    original = regen._GOLDEN_PAIRS[0]
    return (replace(original, golden_path=tmp_path / "test_golden.yaml"),)


def test_regen_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-IDEM-1: two consecutive runs produce byte-identical output.

    Original story risk #6 ("golden non-determinism") was a manual PR-body
    sha256 comparison — humans skip it. This test is the CI gate.
    """
    monkeypatch.setattr(regen, "_GOLDEN_PAIRS", _redirect_to_tmp(tmp_path))
    regen.main()
    sha_a = hashlib.sha256((tmp_path / "test_golden.yaml").read_bytes()).hexdigest()
    regen.main()
    sha_b = hashlib.sha256((tmp_path / "test_golden.yaml").read_bytes()).hexdigest()
    assert sha_a == sha_b, "regen produced different bytes across two runs"


def test_regen_actually_normalizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-IDEM-2: the produced golden contains the <NORMALIZED> sentinel.

    Mutation-killer: a future refactor that accidentally bypasses
    _normalize_envelope (e.g., calls yaml.safe_dump(envelope) directly) would
    leave a real ISO timestamp in the golden — caught here.
    """
    monkeypatch.setattr(regen, "_GOLDEN_PAIRS", _redirect_to_tmp(tmp_path))
    regen.main()
    body = (tmp_path / "test_golden.yaml").read_bytes()
    assert b"<NORMALIZED>" in body
```

**Test file 3 — `tests/integration/probes/test_layer_a_end_to_end.py` (added test):**

```python
def test_layer_a_end_to_end_matches_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6-01 AC-DIFF-1, AC-DIFF-2, AC-DIFF-3, AC-DIFF-4, AC-VAL-1, AC-VAL-2, AC-NEG-1.

    Phase 1 exit invariant: the gather output for the canonical fixture is
    byte-identical (modulo the _NORMALIZED_FIELDS) to the committed golden.
    A failing diff means either (a) a probe changed its slice shape without
    a regen, (b) gather is non-deterministic, or (c) the sanitizer leaked a
    host-specific value. All three are land-blockers.
    """
    import re
    from codegenie.schema.validator import validate as schema_validate
    from tests.integration.probes._golden_helpers import _golden_yaml_bytes
    from tests.integration.probes.conftest import (
        _load_envelope,
        _stub_node_version_check,
    )

    GOLDEN_PATH = (
        Path(__file__).resolve().parents[2] / "golden" / "node_typescript_helm.repo-context.yaml"
    )
    FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "node_typescript_helm"

    if not GOLDEN_PATH.exists():
        pytest.fail(
            f"Golden missing at {GOLDEN_PATH}. First-time setup: python scripts/regen_golden.py"
        )

    # AC-DIFF-3 — neutralize node --version exec for cross-machine stability.
    _stub_node_version_check(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(cli, ["gather", str(FIXTURE), "--output", str(tmp_path)])
    assert result.exit_code == 0, f"gather failed: {result.output!r}"

    repo = tmp_path / FIXTURE.name  # adjust to the actual --output convention
    envelope = _load_envelope(repo)

    # AC-VAL-1 — re-validate the live envelope (pre-normalize) against the schema.
    schema_validate(envelope)

    # AC-VAL-2 — warning IDs match ADR-0007 pattern.
    warning_id_pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for probe_name, probe_block in envelope.get("probes", {}).items():
        for slice_key, slice_body in probe_block.items():
            for warning in (slice_body or {}).get("warnings", []) or []:
                assert warning_id_pattern.fullmatch(warning), (
                    f"probes.{probe_name}.{slice_key}.warnings contains "
                    f"non-ADR-0007 ID: {warning!r}"
                )

    live_bytes = _golden_yaml_bytes(envelope)
    golden_bytes = GOLDEN_PATH.read_bytes()

    # AC-NEG-1 — host-path leak canary.
    forbidden_prefixes = (
        b"/Users/",
        b"/home/",
        b"/tmp/",
        b"/var/folders/",
        os.path.expanduser("~").encode("utf-8") + b"/",
    )
    for prefix in forbidden_prefixes:
        assert prefix not in golden_bytes, (
            f"golden contains host-specific path prefix {prefix!r} — "
            "OutputSanitizer (Phase 0 ADR-0008) regression suspected"
        )

    # AC-DIFF-1, AC-DIFF-2 — byte-equality with prescribed failure message.
    if live_bytes != golden_bytes:
        diff = "\n".join(
            difflib.unified_diff(
                golden_bytes.decode("utf-8").splitlines()[:200],
                live_bytes.decode("utf-8").splitlines()[:200],
                fromfile="golden",
                tofile="live",
                lineterm="",
            )
        )[:4000]
        raise AssertionError(
            f"Golden diff (truncated to 80 lines / 4000 chars):\n{diff}\n\n"
            "To update: python scripts/regen_golden.py\n"
            "Inspect the diff with: git diff tests/golden/"
        )
```

### Green — make them pass

Land in the order described in **Implementation outline** §1–§5. Run each test file's RED-state pytest, then implement the minimum to turn it GREEN, then move on. Do not skip ahead.

### Refactor — clean up

- Confirm `_normalize_envelope` is the **only** site that writes the sentinel string and that `_NORMALIZED_FIELDS` is the **only** source of truth for the normalized field paths. Grep both — if the literal `"<NORMALIZED>"` appears anywhere except `_golden_helpers.py`, the parity is broken.
- Confirm the script and the integration test both import `_golden_yaml_bytes` and neither calls `yaml.safe_dump` directly. Grep for `safe_dump` — should only appear inside `_golden_helpers.py`.
- Run `mypy --strict` against `scripts/regen_golden.py` and `tests/integration/probes/_golden_helpers.py`. Any `Any` in a public signature is a refactor flag.
- Run the full integration suite (`pytest tests/integration/probes/ -q`) to confirm no other test broke (`_stub_node_version_check`'s monkeypatch is per-test; should not bleed).
- Run the script via `make regen-golden` to confirm the Makefile target works (AC-DOC-2).

## Files to touch

| Path | Why |
|---|---|
| `tests/golden/node_typescript_helm.repo-context.yaml` | New file — the seed golden (canonical key-sorted YAML, normalized non-deterministic fields). |
| `scripts/regen_golden.py` | New file — the only sanctioned mutation path; canonical YAML ordering; sha256 emitted. Open/Closed via `_GOLDEN_PAIRS` tuple. |
| `tests/integration/probes/_golden_helpers.py` | New file — `_NORMALIZED_FIELDS`, `_normalize_envelope`, `_golden_yaml_bytes`. Single source of truth shared by the script and the integration test. |
| `tests/integration/probes/test_layer_a_end_to_end.py` | Modify — add `test_layer_a_end_to_end_matches_golden` using the shared helpers. |
| `tests/unit/integration/test_golden_helpers.py` | New file — pure-helper coverage (AC-PURE-2, -3, -4 + the canonical-bytes assertions). |
| `tests/unit/scripts/test_regen_golden_idempotent.py` | New file — AC-IDEM-1 + AC-IDEM-2 (two-run idempotence as a CI gate, sentinel actually applied). |
| `Makefile` | Modify — add `regen-golden:` target invoking the script (AC-DOC-2). |

## Out of scope

- **Multiple golden fixtures.** Phase 1 seeds **one**; Phase 2 extends the portfolio per `phase-arch-design.md §"Golden files"`. The `_GOLDEN_PAIRS` tuple-of-records seam is the discoverable extension point — Phase 2 appends entries; no new abstraction is extracted in this story (Rule 2 — three concrete consumers, not yet two; the rule of three has not been met). **What this story does not do**: factor a generic `regen_kernel.py` taking a list of `GoldenPair`-shaped registry entries. That extraction is Phase 7's job (when the third golden lands).
- **Schema-bump detection in the regen script.** The script verifies all required probes are present (AC-SCRIPT-4); it does not detect a sub-schema-shape change (that's covered by `additionalProperties: false` rejection at validate time, AC-SCRIPT-5). A schema bump that changes the slice shape requires regen + golden review in the same PR — that's the convention, not the tooling.
- **Comparing across Python 3.11 / 3.12.** The integration test runs on both per the CI matrix. If `safe_dump` ever behaves differently across versions (it does not in practice for `sort_keys=True` + `default_flow_style=False`), the test will catch it on the matrix.
- **Audit-anchor regen.** S5-05 already asserts the audit anchor recomputes via `codegenie audit verify`. The golden does not duplicate that surface. The audit `RunRecord` lives in `.codegenie/context/runs/<run-id>.json` (a sidecar), **not** in `repo-context.yaml` — this story's strip pass does not need to touch it (and could not, as it's not in the envelope).
- **Deep-walking `probes.*` for nested timestamp fields.** Phase 1 probes do not embed wall-clock fields in their slices (they emit facts, not telemetry — `production/design.md §2.2`). If a Phase-2 probe ever does, the regression surfaces as a golden diff failure on the next CI run after that probe lands; the fix at that point is to add the new path to `_NORMALIZED_FIELDS` (one line) plus AC-PURE-3's parametrize automatically picks up the new entry.

## Notes for the implementer

### Load-bearing gotchas

- The envelope has **no `audit` block**. `audit.wall_clock_ms` lives in `.codegenie/context/runs/<run-id>.json`, written by `_seam_audit_record` in `cli.py`. Do not write a strip pass keyed on `data["audit"]` — it is a no-op (the original story's bug). The fields you must normalize are exactly the ones in `_NORMALIZED_FIELDS`: `("generated_at",)` and `("repo", "git_commit")`. Confirm against `cli.py:423-440` if you're ever in doubt.
- `repo.git_commit` is non-deterministic on fixture paths because the fixture has no `.git/`. `git rev-parse HEAD` walks up to codewizard-sherpa's `.git/` and returns this repo's HEAD. Every commit to this repo would otherwise change every golden. Normalize, don't delete (envelope schema requires the field).
- The writer (`src/codegenie/output/writer.py:180`) uses `sort_keys=False`. The regen script and the integration test both re-serialize via `_golden_yaml_bytes` (which uses `sort_keys=True`) so both the golden-on-disk AND the live envelope-bytes for comparison are canonical. Don't try to make the writer canonical — that's a coordinator-level change outside this story.
- `_stub_node_version_check` (conftest) is non-negotiable for the integration test. Without it, `NodeBuildSystemProbe` cross-checks `node --version` against the fixture's `.nvmrc`, and the resulting `node.version_declared_resolved_disagree` warning lands in the slice on machines where Node ≠ pinned version → integration test fails on developer machines, passes in CI's pinned env, or vice versa.

### Design pattern guidance

- The **one** abstraction this story introduces is `GoldenPair` (a 3-field frozen `dataclass`) and the `_GOLDEN_PAIRS: tuple[...]` registry. That's the Open/Closed seam: Phase 2 adds a golden by appending a `GoldenPair(...)`, never by editing `main()`. Three Phase-1 hardcoded values (fixture path, golden path, required-probes set) collapse to one record. **This is not premature abstraction** — it is the data-shaped seam that Rule 7 demands when source-of-truth would otherwise be triplicated. (Compare to S5-05's `WARM_PATH_CACHE_HIT_PROBES` and `PHASE_1_PROBE_NAMES` — same Open/Closed pattern at the file boundary.)
- The **shared `_normalize_envelope` + `_golden_yaml_bytes` helpers** are a deliberate exception to "tests/ should not be imported by scripts/." The alternative (duplicate the helper) creates a parity-drift class of bugs: change one, forget the other → silent golden divergence on a future timestamp field. Single source of truth wins; the import boundary cost is one line.
- Do **not** factor a generic `regen_kernel.py` yet. The codebase has two regen scripts (probe-contract + golden); the rule of three has not been met. Phase 7's distroless-fixture golden is the third concrete consumer; that PR earns the kernel extraction. Until then, the per-script `_GOLDEN_PAIRS` tuple plus the shared `_golden_yaml_bytes` helper carry the load. (Rule 2 — "three similar lines is better than premature abstraction.")
- Make the field list a `frozenset[tuple[str, ...]]`, not a `list[str]` of dotted paths. The tuple form encodes the path natively — no `split(".")` parsing, no ambiguity if a future field name contains a dot. The `frozenset` form makes membership checks `O(1)` and signals immutability.
- Use `pytest.MonkeyPatch.setattr(regen, "_GOLDEN_PAIRS", ...)` in the idempotence test, not `regen._GOLDEN_PAIRS = ...`. The attribute is `Final`-typed; mypy + monkeypatch is the test seam.

### Process / PR hygiene

- **Verify locally before pushing.** Run `python scripts/regen_golden.py` twice, copy both sha256 lines into the PR body. Then run `pytest tests/unit/integration/ tests/unit/scripts/ tests/integration/probes/test_layer_a_end_to_end.py -q`. If any of those fail locally, do not open the PR — the AC-IDEM and AC-DIFF tests are the CI safety net, but the local cycle is the developer's responsibility.
- The PR body should include: (a) both sha256 lines from two consecutive `python scripts/regen_golden.py` invocations; (b) the diff stat for `tests/golden/node_typescript_helm.repo-context.yaml` (one new file); (c) a one-line sentence per probe-slice in the golden saying what it asserts ("`build_system` records pnpm-lock precedence + `.nvmrc` pin", etc.). The reviewer reads the golden once; the description orients them.
- **Never `git checkout tests/golden/` to discard a diff during this story's work.** A diff there means either you found a bug in normalization or you found a bug in a probe — both deserve investigation, not erasure. (CLAUDE.md "Executing actions with care" — golden diffs are loud signals; treat them as such.)
- Do **not** run the regen script in CI. The golden is checked in; CI only compares. If CI were allowed to regenerate, the gate would be tautological.
- Truncation thresholds (`difflib.unified_diff` 80 lines / 4000 chars) are deliberately tight — CI logs are scannable. If a future probe slice grows so large that 80 lines is uninformative, the fix is in *that* PR, not pre-emptively here.

### What success looks like

- A reviewer pulls the branch, runs `make regen-golden`, sees no diff in `tests/golden/`. (Idempotence verified locally.)
- A reviewer changes one byte of `tests/fixtures/node_typescript_helm/package.json`, runs `pytest tests/integration/probes/test_layer_a_end_to_end.py -q`, sees the unified diff with the regen instruction. (Failure mode is loud and self-explanatory.)
- A reviewer drops a fake `wall_clock_ms` field into the envelope (e.g., monkeypatches `cli.py` to inject `envelope["wall_clock_ms"] = 12345`), reruns the integration test, sees the byte-diff fail (proving the strip pass does not over-reach to fields it shouldn't normalize). The fix is to either (a) add the path to `_NORMALIZED_FIELDS` and regen, or (b) revert the cli.py change. Both responses are explicit.
- Phase 2's first PR adds a second golden by appending one `GoldenPair(fixture_dir=..., golden_path=..., required_probes=...)` entry to `_GOLDEN_PAIRS`. Zero edits to `main()`, zero edits to `_normalize_envelope`. Extension by addition.
