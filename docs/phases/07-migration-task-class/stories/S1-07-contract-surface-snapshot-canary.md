# Story S1-07 — Generate initial contract-surface snapshot + permanent canary

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-02, S1-03, S1-04, S1-05, S1-06

## Context

The six additive seams have all landed (S1-01..05) and the ADRs justify them (S1-06). This story lands the *permanent* enforcement mechanism: a CI test that snapshots the public contract surfaces of Phases 0–6 — Pydantic schemas, ABC signatures, closed `Literal` value sets, registry decorator signatures, `ALLOWED_BINARIES`, egress allowlist, `FallbackTier.run` signature, `base_catalog.json` shape — into a single canonical-JSON file. Any future drift fails CI; regeneration is a deliberate `pytest --update-contract-snapshot` invocation. Without this story, the ADR-0028 amendment is unenforceable convention.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 10. Contract-surface snapshot canary` (lines ~782–809) — the load-bearing component spec: `compute_snapshot()` internals, what surfaces are captured, canonical-JSON serialization, the `pytest --update-contract-snapshot` flag.
  - `../phase-arch-design.md §Scenarios ›Scenario 4` — "Cross-task regression — the contract-surface snapshot fires on an inadvertent Phase 6 edit (test path)."
  - `../phase-arch-design.md §Testing strategy ›CI gates #3` — `pytest tests/integration/test_contract_surface_snapshot.py` is a permanent merge-block.
  - `../phase-arch-design.md §Edge cases #11` — Phase 0–6 source edited outside the six named seams → snapshot fails.
- **Phase ADRs:**
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — the decision, the rejection of `[B]`'s one-shot gate and `[S]`'s BLAKE3-source freeze, the canonical-JSON serializer requirement.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — six seams; the snapshot must capture all six diffs in *this* PR (the regenerated snapshot is the first emission).
  - Every other Phase 7 ADR (0002–0007) — each names a surface the snapshot must cover.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — the `Probe` ABC signature is in the snapshot scope (must be unchanged in this PR — S1-01 verified, snapshot enforces forever).
  - `../../../production/adrs/0028-task-class-introduction-order.md` — amended in S1-06; snapshot is the enforcement mechanism cited in the amendment.
- **Existing code (read before writing):**
  - `src/codegenie/probes/`, `src/codegenie/recipes/`, `src/codegenie/transforms/`, `src/codegenie/planner/`, `src/codegenie/sandbox/`, `src/codegenie/gates/`, `src/codegenie/graph/` — every Pydantic model + every ABC + every closed `Literal` + every registry decorator under these packages is in the snapshot's scope.
  - `pyproject.toml` — Pydantic version pin (load-bearing for `model_json_schema()` byte-stability).
  - `tools/digests.yaml` — if this file exists; the snapshot does not capture it directly, but pinning Python+Pydantic versions is required for byte-stability across CI runners.

## Goal

`tools/contract-surface.snapshot.json` exists and represents the post-Phase-7-seams contract surface; `tests/integration/test_contract_surface_snapshot.py` recomputes the snapshot from source and fails on any byte-level drift; `pytest --update-contract-snapshot` is a working pytest flag that regenerates the file.

## Acceptance criteria

- [ ] `tools/contract_surface.py` (a new module — exact name negotiable, but the test imports from it) exposes `compute_snapshot() -> dict` and `canonical_json(obj) -> bytes`. `canonical_json` uses sorted keys, fixed separators (`(", ", ": ")` → `(",", ":")` per the architecture's "canonical-JSON" convention; match `json.dumps(obj, sort_keys=True, separators=(",", ":"))`), UTF-8, single trailing newline.
- [ ] `compute_snapshot()` covers, at minimum, every surface enumerated in `phase-arch-design.md §Component 10 ›Internal structure`:
  - For every Pydantic model under `src/codegenie/{probes,recipes,transforms,planner,sandbox,gates,graph}/`: `model_json_schema()`.
  - For every ABC under those packages: public method signatures via `inspect.signature` (stringified).
  - For every closed `Literal` in those models: the value set as a sorted list.
  - For every registry decorator (`@register_probe`, `@register_recipe_engine`, `@register_transform`, `@register_signal_kind`, `@register_sandbox_backend`, `@register_gate_probe`): the decorator's `inspect.signature`.
  - `src/codegenie/sandbox/host/allowed_binaries.py` `ALLOWED_BINARIES` — sorted list.
  - `src/codegenie/sandbox/host/egress_allowlist.py` egress allowlist — sorted list.
  - `src/codegenie/planner/fallback_tier.py` `FallbackTier.run` — `inspect.signature` (stringified).
- [ ] `tools/contract-surface.snapshot.json` is committed to the repo root under `tools/`, contains the canonical-JSON serialization of `compute_snapshot()`, and ends with a single newline.
- [ ] `tests/integration/test_contract_surface_snapshot.py` is committed and green: recomputes the snapshot from source and asserts byte-equality with the on-disk file. Failure message names the regen workflow: `pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py`.
- [ ] The same test file's pytest plugin (or `conftest.py` hook) registers `--update-contract-snapshot` as a CLI flag; when set, the test rewrites `tools/contract-surface.snapshot.json` from `compute_snapshot()` and exits 0 (does not assert).
- [ ] The snapshot reflects the post-Phase-7-seam state: it captures `ObjectiveSignals` with the four new `| None` fields, `FallbackTier.run` with the `task_type` kwarg, `Recipe.engine` with the `"dockerfile"` value, `ALLOWED_BINARIES` containing `"docker"`/`"dive"`, the egress allowlist containing `"cgr.dev"`/`"docker.io"`, and the `register_gate_probe` decorator signature.
- [ ] `tests/integration/test_contract_surface_snapshot_regen_flag.py` (smoke test) is committed and green: runs `pytest --update-contract-snapshot` against a copy of the snapshot in a tmpdir; asserts the file is rewritten and contains canonical-JSON with sorted keys.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `tools/contract_surface.py` and the test files.

## Implementation outline

1. Author `tools/contract_surface.py` with `canonical_json(obj) -> bytes` (sorted keys, fixed separators, UTF-8 + trailing newline) and `compute_snapshot() -> dict` (walks every package via `pkgutil.walk_packages` or explicit import list; pulls schemas, signatures, Literals, registries, allowlists).
2. Add a `conftest.py` hook (or pytest plugin) at `tests/integration/conftest.py` (or repo-level `conftest.py`) registering the `--update-contract-snapshot` flag.
3. Write the failing test `tests/integration/test_contract_surface_snapshot.py` (TDD red — the file `tools/contract-surface.snapshot.json` doesn't exist yet).
4. Run `pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py` to *generate* the initial snapshot (TDD green via deliberate regen).
5. Re-run `pytest tests/integration/test_contract_surface_snapshot.py` (without the flag) and confirm green.
6. Write the smoke test for the regen flag (`tests/integration/test_contract_surface_snapshot_regen_flag.py`).
7. Manually inspect the generated `tools/contract-surface.snapshot.json` and verify each Phase 7 seam shows up in the diff against `master` exactly once — sanity check that the snapshot is not missing a surface.
8. Refactor: docstring `compute_snapshot` enumerating every surface category; ensure the file path / line numbers in the failure message are actionable.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file: `tests/integration/test_contract_surface_snapshot.py`

```python
# tests/integration/test_contract_surface_snapshot.py
import pathlib
import pytest

from tools.contract_surface import compute_snapshot, canonical_json

SNAPSHOT_PATH = pathlib.Path("tools/contract-surface.snapshot.json")


def test_contract_surface_snapshot_phase_0_through_6(request):
    if request.config.getoption("--update-contract-snapshot", default=False):
        SNAPSHOT_PATH.write_bytes(canonical_json(compute_snapshot()))
        pytest.skip("Snapshot regenerated via --update-contract-snapshot flag.")
    expected = SNAPSHOT_PATH.read_bytes()
    actual = canonical_json(compute_snapshot())
    assert actual == expected, (
        "Phase 0–6 contract surface drifted from tools/contract-surface.snapshot.json. "
        "If this drift is intentional, regenerate with:\n"
        "    pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py\n"
        "and link the per-phase ADR documenting the additive extension in your PR body."
    )
```

`tests/integration/conftest.py`:

```python
def pytest_addoption(parser):
    parser.addoption(
        "--update-contract-snapshot",
        action="store_true",
        default=False,
        help="Regenerate tools/contract-surface.snapshot.json from source.",
    )
```

`tests/integration/test_contract_surface_snapshot_regen_flag.py`:

```python
import subprocess, json, pathlib, shutil


def test_update_flag_writes_canonical_json(tmp_path, monkeypatch):
    # Copy the repo's snapshot to a tmp work dir to avoid clobbering it under test.
    # ...
    result = subprocess.run(
        ["pytest", "tests/integration/test_contract_surface_snapshot.py", "--update-contract-snapshot"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    text = pathlib.Path("tools/contract-surface.snapshot.json").read_text(encoding="utf-8")
    parsed = json.loads(text)
    re_serialized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    assert re_serialized + "\n" == text or re_serialized == text.rstrip("\n")
```

Expected red failure mode: `FileNotFoundError: tools/contract-surface.snapshot.json` (first run) → run with `--update-contract-snapshot` once to seed → re-run without the flag → assertion green.

### Green — make it pass

1. Implement `tools/contract_surface.py`:

   ```python
   # tools/contract_surface.py — sketch; fill in per phase-arch-design §Component 10
   import inspect, json, pkgutil, typing
   from collections.abc import Sequence

   def canonical_json(obj) -> bytes:
       return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"

   def compute_snapshot() -> dict:
       return {
           "pydantic_models": _collect_pydantic_models(),
           "abcs": _collect_abc_signatures(),
           "closed_literals": _collect_closed_literals(),
           "registries": _collect_registry_decorator_signatures(),
           "allowed_binaries": _collect_allowed_binaries(),
           "egress_allowlist": _collect_egress_allowlist(),
           "fallback_tier_run_signature": _stringified_signature("codegenie.planner.fallback_tier.FallbackTier.run"),
           "base_catalog": _collect_base_catalog_shape(),  # may be the schema_version pin + key list; S2-06 fills this in
       }
   ```

   The helper functions walk `src/codegenie/` packages, find `BaseModel` subclasses, find `ABC` subclasses with abstract methods, extract `Literal[...]` annotations from model fields, and serialize via `inspect.signature(...).__str__()`. Each collector returns a sorted dict so canonical-JSON ordering is stable.

2. Run `pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py` once. The file `tools/contract-surface.snapshot.json` is generated.

3. Re-run `pytest tests/integration/test_contract_surface_snapshot.py` without the flag — must be green.

4. Diff the generated snapshot against an earlier empty/master baseline; confirm the diff includes (a) the new `ObjectiveSignals` fields, (b) `Recipe.engine` containing `"dockerfile"`, (c) `FallbackTier.run` signature containing `task_type`, (d) `register_gate_probe` decorator, (e) `docker`/`dive` in `ALLOWED_BINARIES`, (f) `cgr.dev`/`docker.io` in egress allowlist — *exactly six diffs*. Any extra diff is a scope leak; any missing one is a snapshot coverage hole.

### Refactor — clean up

- Add a `compute_snapshot()` docstring enumerating every surface category and the rationale ("we capture X but not Y because…").
- Strip docstrings from `model_json_schema()` output if Pydantic includes them — they cause noise when authors edit docstrings without changing contracts (per ADR-P7-009 tradeoffs row). Pydantic v2 has a `field_serialization_info` knob for this; verify behavior.
- Confirm the canonical-JSON output is byte-stable across `python3.11` and `python3.12` on Linux + macOS by running the test on both locally before declaring green.
- Document the snapshot regen workflow in the test's failure message and in the `tools/contract_surface.py` module docstring.

## Files to touch

| Path | Why |
|---|---|
| `tools/contract_surface.py` | New module — `compute_snapshot()` + `canonical_json()` implementations. |
| `tools/contract-surface.snapshot.json` | Initial post-Phase-7-seam snapshot — seeded via `pytest --update-contract-snapshot`. |
| `tests/integration/test_contract_surface_snapshot.py` | New test — TDD red anchor; the permanent canary. |
| `tests/integration/test_contract_surface_snapshot_regen_flag.py` | New test — smoke check that the regen flag rewrites canonical JSON. |
| `tests/integration/conftest.py` (or repo-level `conftest.py`) | Register the `--update-contract-snapshot` pytest CLI flag. |

## Out of scope

- **`tools/snapshot_regen_audit.py` (GitHub Actions ADR-link enforcement)** — S1-08.
- **Fence-CI extension to deny `anthropic|chromadb|sentence-transformers` imports under `probes/transforms/recipes/catalogs/`** — S1-08.
- **Snapshot-discipline rehearsal PRs (A: no-op edit fires canary; B: legitimate regen passes)** — S8-04.
- **`base_catalog.json` shape** — the snapshot's `base_catalog` field may be a placeholder / `null` here; S2-06 fills it in when the catalog is rendered for the first time, and that PR regenerates the snapshot citing ADR-P7-013/ADR-P7-009.
- **Wall-clock canary baseline** — S7-01 (`tests/perf/baseline.json` is a separate canary).
- **Docstring stripping if Pydantic includes them in `model_json_schema()`** — out only if the architecture's "canonical-JSON serializer must strip docstrings" rule is genuinely violated; if Pydantic v2 omits them by default, no work needed.

## Notes for the implementer

- Canonical-JSON byte-stability is *the* load-bearing invariant. Pin Python ≥ 3.11 and Pydantic ≥ 2.x in `pyproject.toml`; both are sources of `model_json_schema()` formatting drift if they bump. Document the pins in `tools/contract_surface.py`'s docstring.
- Walk packages explicitly (`pkgutil.iter_modules` or an explicit list) — `importlib` "discover everything" magic produces non-deterministic ordering, which breaks byte-stability. Sort the discovered set before serializing.
- `inspect.signature` returns a `Signature` object whose `__str__()` representation is stable but version-sensitive (`str | None` vs `Optional[str]` formatting varies). Either normalize annotations to one style before stringifying, or pin Python to a single minor version and accept the constraint. **Do not** capture the raw `Signature` object — capture its string representation.
- Pydantic `model_json_schema()` can include `"description"` fields drawn from docstrings — these are *intentional* contract surface (callers depend on the schema being authoritative), but docstring edits ("fix a typo") then read as contract drift. The ADR-P7-009 tradeoffs table calls this out: the canonical-JSON serializer "must strip docstrings before snapshotting." Implement this stripping or document why it's not needed.
- The snapshot's stability across operating systems matters too — line endings on Windows runners differ. Use `\n` everywhere; reject CRLF in `canonical_json` by writing `bytes`, never `str`.
- When the snapshot legitimately drifts (e.g., S2-06 adds the `base_catalog` shape), the author runs `pytest --update-contract-snapshot` and *links the ADR in the PR body* — S1-08's audit script enforces the linkage. This story does not enforce; it merely makes the snapshot exist and the regen flag work.
- The "six diffs exactly" sanity check in step 4 of the implementation outline is a *manual* code-review step, not an automated test. Document it in the PR description: enumerate the six seams that should show up in the snapshot diff. If a seventh diff appears, it's a contract violation (e.g., S1-02 accidentally widened more than `ObjectiveSignals`). Surface it loudly.
- The smoke test of the regen flag runs `pytest` recursively — it spawns a subprocess. Make sure CI configurations don't break on nested pytest runs (use `--disable-warnings` to keep output clean).
- Per CLAUDE.md "Fail loud": if `compute_snapshot()` encounters an import error, a malformed model, or a registry without `inspect.signature` access, raise loudly. Do not skip the failed surface silently — that creates a coverage hole the canary cannot catch.
