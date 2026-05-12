# Story S6-01 — Golden file `node_typescript_helm` + `scripts/regen_golden.py`

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S5-05
**ADRs honored:** ADR-0002 (memo determinism), ADR-0004 (sub-schema strictness), ADR-0007 (warning-ID pattern stable in golden output)

## Context

Phase 1 has produced six populated Layer A slices on `tests/fixtures/node_typescript_helm/` and the end-to-end integration test (S5-05) asserts the slices are present, the envelope validates, and the audit anchor re-computes. What it does **not** yet assert is *byte-identical output* across runs — the deterministic-gather invariant that every downstream phase (continuous gather in Phase 14, recipe inputs in Phase 3, distroless inputs in Phase 7) relies on. The golden file is the seam that turns "deterministic" from an aspiration into a CI gate.

This story lands `tests/golden/node_typescript_helm.repo-context.yaml` (canonical key-sorted YAML, every wall-clock and audit-timestamp field excluded) plus `scripts/regen_golden.py` (the only sanctioned way to update it). The integration test from S5-05 is extended to diff live output against the golden as a hard CI gate.

Golden files are notoriously brittle to non-determinism. The Phase 0 commitment that `gather` is deterministic on identical content carries the load here, but **`audit.wall_clock_ms`** and **`audit.completed_at`** must be excluded from the golden by the regen script — otherwise every CI run fails the diff. The implementer-level risk from `High-level-impl.md` #6 ("run the regen script twice locally and verify byte-identical output **before** opening the Step 6 PR") is non-negotiable.

This is the canonical example Phase 2 expands. Phase 2's broader golden portfolio (more fixtures, IndexHealthProbe slices, possibly Go/Java fixtures) follows the same shape — sorted keys, excluded wall-clock, single regen script as the only mutation path.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" / "Golden files"` — `tests/golden/node_typescript_helm.repo-context.yaml` is the seed; updating it is a deliberate PR step with a `regen` script under `scripts/regen_golden.py`. Phase 2's broader golden portfolio extends the convention.
  - `../phase-arch-design.md §"Testing strategy" / "CI gates"` — the `test` job runs `pytest` including the golden diff; `--cov-fail-under=90` ratchet (S6-02 enforces).
  - `../phase-arch-design.md §"Integration with Phase 2"` — Phase 2 reads `.codegenie/context/repo-context.yaml` and extends the golden portfolio; Phase 1's golden is the shape contract.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — ADR-0002 — the memo is per-gather; cache-hit second run must produce byte-identical slices. The golden is the proof.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — ADR-0004 — every slice in the golden conforms to its sub-schema; the integration test re-validates after diff.
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — every warning ID present in the golden matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- **High-level impl plan:**
  - `../High-level-impl.md §"Step 6"` — features delivered: `tests/golden/node_typescript_helm.repo-context.yaml` (seed golden); `scripts/regen_golden.py` (canonical YAML ordering).
  - `../High-level-impl.md §"Implementation-level risks" #6` — golden non-determinism: regen script excludes wall-clock + audit timestamps; run twice locally and verify byte-identical output before opening the Step 6 PR.
  - `../High-level-impl.md §"Step 6 — Done criteria"` bullet 1 and 2 — golden exists, canonically ordered; `regen_golden.py` produces byte-identical output across two consecutive runs.
- **Manifest:**
  - `../stories/README.md` — S6-01 row; Definition-of-done section.
- **Existing code (consumed by this story):**
  - `src/codegenie/cli.py` — `codegenie gather` entry point invoked by the regen script.
  - `src/codegenie/coordinator/coordinator.py` — `GatherResult` shape; the slices the golden captures.
  - `src/codegenie/writer.py` (or equivalent from Phase 0) — the YAML writer; the golden uses the same serializer for shape consistency.
  - `tests/fixtures/node_typescript_helm/` — the fixture (S2-03); the golden's input.
  - `tests/integration/probes/test_layer_a_end_to_end.py` (S5-05) — extended in this story to diff against the golden.

## Goal

Land `tests/golden/node_typescript_helm.repo-context.yaml` (canonical key-sorted YAML, wall-clock and audit-timestamp fields excluded) and `scripts/regen_golden.py` (the only sanctioned way to update it); the S5-05 integration test diffs live output against the golden as a hard CI gate; two consecutive regen runs produce byte-identical output.

## Acceptance criteria

- [ ] `tests/golden/node_typescript_helm.repo-context.yaml` exists, is sorted by key at every level (`yaml.safe_dump(..., sort_keys=True, default_flow_style=False)`), and contains the six Layer A slices populated for the `node_typescript_helm` fixture.
- [ ] `scripts/regen_golden.py` runs `codegenie gather` against `tests/fixtures/node_typescript_helm/` to a temporary output directory, strips `audit.wall_clock_ms` and `audit.completed_at` (and any other timestamp field surfaced by Phase 0/1 audit shape), writes the result to `tests/golden/node_typescript_helm.repo-context.yaml` in canonical YAML ordering.
- [ ] `scripts/regen_golden.py` produces **byte-identical output** across two consecutive invocations on the same machine (verified locally before merge; surfaced in the PR body as a `sha256` line for each run).
- [ ] `tests/integration/probes/test_layer_a_end_to_end.py` is extended with one new assertion: `live_yaml_bytes == golden_yaml_bytes` (after the same wall-clock-stripping helper the regen script uses, applied to live output); failure surfaces a `unified_diff` of the first 50 differing lines in the test failure message.
- [ ] The golden diff failure message instructs the reader: `"To update the golden, run: python scripts/regen_golden.py"` — no other mutation path is documented.
- [ ] The regen script exits non-zero if `codegenie gather` exits non-zero, if the output envelope fails schema validation, or if any of the six expected Layer A slices is missing from the result.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on `scripts/regen_golden.py` and the touched integration test.

## Implementation outline

1. Write the TDD red test first: extend `tests/integration/probes/test_layer_a_end_to_end.py` with a `test_golden_byte_identical` assertion that reads `tests/golden/node_typescript_helm.repo-context.yaml` and compares it to the gathered output (post wall-clock strip). The test fails because the golden file does not yet exist.
2. Write `scripts/regen_golden.py`:
   - Use `pathlib.Path` for all paths; `subprocess.run` with `check=True` to invoke `codegenie gather --output <tmp>`.
   - Read the produced `<tmp>/.codegenie/context/repo-context.yaml` via `yaml.safe_load` (`safe_yaml.load` if available from S1-03).
   - Apply `_strip_wall_clock(data)` — a 10-line helper that pops `audit.wall_clock_ms`, `audit.completed_at`, and any field whose key ends in `_ms` or `_at` *inside* the `audit` block. Document the helper inline.
   - Write back via `yaml.safe_dump(data, sort_keys=True, default_flow_style=False, width=120)` to `tests/golden/node_typescript_helm.repo-context.yaml`.
   - Print `sha256(golden_bytes)` to stdout so two consecutive runs can be visually compared.
3. Run the regen script twice locally; verify the two `sha256` outputs match. If they don't, the wall-clock-strip helper is missing a field — surface in the PR body which field was discovered.
4. Implement the matching `_strip_wall_clock(data)` helper in the integration test file (or factor to `tests/integration/probes/_golden_helpers.py` if a second golden fixture is added in this story — not required for Phase 1).
5. The integration test loads the golden bytes, the live gather bytes (stripped), compares byte-for-byte. On failure, emit a unified diff via `difflib.unified_diff(...)` truncated to 50 lines and the regen instruction.
6. Confirm `pytest tests/integration/probes/test_layer_a_end_to_end.py` passes locally.
7. Document the regen workflow in the script's module docstring: "Run after a deliberate change to a Phase 1 probe's slice shape; commit the golden diff alongside the probe change in the same PR."

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_layer_a_end_to_end.py`

```python
# tests/integration/probes/test_layer_a_end_to_end.py (added test)
import difflib
from pathlib import Path

import yaml

from codegenie.cli import gather_cli  # or whatever the Step-1 entry exposes


GOLDEN_PATH = Path(__file__).parent.parent.parent / "golden" / "node_typescript_helm.repo-context.yaml"
FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "node_typescript_helm"


def _strip_wall_clock(data: dict) -> dict:
    """Drop fields that must not appear in golden (wall-clock + completion timestamps)."""
    audit = data.get("audit", {})
    for key in list(audit.keys()):
        if key in {"wall_clock_ms", "completed_at"} or key.endswith("_ms") or key.endswith("_at"):
            audit.pop(key)
    return data


def test_golden_byte_identical(tmp_path: Path) -> None:
    """
    Phase 1 exit invariant: `codegenie gather` against the canonical fixture
    produces byte-identical output (modulo wall-clock fields) to the committed
    golden. Failure means either (a) a probe changed its slice shape without
    regen, or (b) gather is non-deterministic — both are land-blockers.
    """
    # arrange: run gather to tmp_path; load result.
    gather_cli(str(FIXTURE), output=str(tmp_path))
    live_path = tmp_path / ".codegenie" / "context" / "repo-context.yaml"
    live = _strip_wall_clock(yaml.safe_load(live_path.read_bytes()))
    live_bytes = yaml.safe_dump(live, sort_keys=True, default_flow_style=False, width=120).encode()

    # assert byte-identical to the golden.
    assert GOLDEN_PATH.exists(), "Run: python scripts/regen_golden.py"
    golden_bytes = GOLDEN_PATH.read_bytes()
    if live_bytes != golden_bytes:
        diff = "\n".join(
            difflib.unified_diff(
                golden_bytes.decode().splitlines()[:200],
                live_bytes.decode().splitlines()[:200],
                fromfile="golden",
                tofile="live",
                lineterm="",
            )
        )
        raise AssertionError(
            f"Golden diff (first 50 lines shown). To update: python scripts/regen_golden.py\n{diff[:2000]}"
        )
```

This test fails initially because `tests/golden/node_typescript_helm.repo-context.yaml` does not exist. Commit the failing test, then run the regen script.

### Green — make it pass

1. Write `scripts/regen_golden.py` (~60 LOC):
   ```python
   """Regenerate tests/golden/node_typescript_helm.repo-context.yaml.

   The only sanctioned way to update the golden. Run after a deliberate change
   to a Phase 1 probe's slice shape; commit the diff alongside the probe change.
   """
   import hashlib
   import subprocess
   import sys
   import tempfile
   from pathlib import Path

   import yaml

   REPO_ROOT = Path(__file__).parent.parent
   FIXTURE = REPO_ROOT / "tests" / "fixtures" / "node_typescript_helm"
   GOLDEN = REPO_ROOT / "tests" / "golden" / "node_typescript_helm.repo-context.yaml"


   def _strip_wall_clock(data: dict) -> dict:
       audit = data.get("audit", {})
       for key in list(audit.keys()):
           if key in {"wall_clock_ms", "completed_at"} or key.endswith("_ms") or key.endswith("_at"):
               audit.pop(key)
       return data


   def main() -> int:
       with tempfile.TemporaryDirectory() as td:
           result = subprocess.run(
               ["codegenie", "gather", str(FIXTURE), "--output", td],
               check=False,
               capture_output=True,
           )
           if result.returncode != 0:
               print(result.stderr.decode(), file=sys.stderr)
               return result.returncode
           live = yaml.safe_load((Path(td) / ".codegenie" / "context" / "repo-context.yaml").read_bytes())
           live = _strip_wall_clock(live)
           # Sanity: all six Layer A slices present.
           required = {"language_stack", "build_system", "manifests", "ci", "deployment", "test_inventory"}
           missing = required - set(live.get("probes", {}).keys())
           if missing:
               print(f"missing slices: {missing}", file=sys.stderr)
               return 2
           out = yaml.safe_dump(live, sort_keys=True, default_flow_style=False, width=120).encode()
           GOLDEN.write_bytes(out)
           print(f"wrote {GOLDEN} sha256={hashlib.sha256(out).hexdigest()}")
       return 0


   if __name__ == "__main__":
       sys.exit(main())
   ```
2. Run `python scripts/regen_golden.py` locally. Record the `sha256`.
3. Run it again. Verify the `sha256` is identical. If not, the strip helper is missing a field; add it and re-run.
4. Run the failing test from the red step; it now passes.

### Refactor — clean up

- Move `_strip_wall_clock` to a shared helper if Phase 2 needs it (Phase 1 keeps it inline; one production-side strip is one duplicated 6-line function — acceptable).
- Add a module-level docstring to the integration test explaining the golden's role and the regen workflow.
- Add a `make regen-golden` target to the `Makefile` so contributors don't have to remember the path.
- Confirm `mypy --strict` and `ruff` pass on both the script and the test.

## Files to touch

| Path | Why |
|---|---|
| `tests/golden/node_typescript_helm.repo-context.yaml` | New file — the seed golden (canonical key-sorted YAML, wall-clock fields excluded). |
| `scripts/regen_golden.py` | New file — the only sanctioned mutation path; canonical YAML ordering; sha256 emitted for verification. |
| `tests/integration/probes/test_layer_a_end_to_end.py` | Modify — add `test_golden_byte_identical` assertion + `_strip_wall_clock` helper + golden-diff failure message instructing the regen path. |
| `Makefile` | Modify (optional) — add `regen-golden` target invoking the script. |

## Out of scope

- **Multiple golden fixtures.** Phase 1 seeds one; Phase 2 extends the portfolio per `phase-arch-design.md §"Golden files"`. Do not preemptively factor a generic regen library — that's premature abstraction (Rule 2).
- **Audit-anchor regen.** S5-05 already asserts the audit anchor recomputes; the golden does not duplicate that assertion. The strip helper drops audit timestamps but keeps the anchor hash, which is itself deterministic on the slice content.
- **Schema bump detection in the regen script.** The script asserts all six slices are present; it does not detect a sub-schema-shape change (that's covered by `additionalProperties: false` rejection at validate time). A schema bump that changes the slice shape requires regen + golden review in the same PR — that's the convention, not the tooling.
- **Comparing across Python 3.11 / 3.12.** The integration test runs on both per CI matrix. If the YAML serializer behaves differently across versions (it does not in practice for `safe_dump` with `sort_keys=True`), the test will catch it.

## Notes for the implementer

- The `_strip_wall_clock` helper is duplicated between `scripts/regen_golden.py` and the integration test by design. Factoring it to a shared module under `tests/_helpers/` is acceptable but not required — six lines of duplication is cheaper than a shared-helper import path that travels across `scripts/` ↔ `tests/`.
- `yaml.safe_dump(..., default_flow_style=False, width=120)` is the canonical primitive. Do not pass `default_style="|"` or `allow_unicode=False` — the goal is byte-identity across runs, and `safe_dump`'s defaults plus `sort_keys=True` are sufficient.
- Run the regen script **twice** locally and capture both `sha256` lines in the PR body. If they differ, the strip helper missed a field; surface which field in the PR body so reviewers see the root cause.
- The integration test's `unified_diff` output is truncated at 2000 characters to keep CI logs scannable. If a future probe's slice grows very large and the diff is unreadable, raise the truncation in a follow-up — do not preemptively expand here.
- The golden is checked in. Phase 7's distroless work will eventually want a separate golden for `node_pnpm_native`; that PR adds a second golden + extends the regen script — both are Phase 7 concerns. Phase 1 ships one.
- Do not run the regen script in CI. The golden is *checked in*; CI only compares. If CI were allowed to regenerate, the gate would be tautological.
- If `codegenie gather` is asynchronous or takes more than ~30 s on the fixture, the regen script should still complete quickly enough not to need a progress indicator. If it ever does, that's a Phase 1 perf regression worth surfacing.
