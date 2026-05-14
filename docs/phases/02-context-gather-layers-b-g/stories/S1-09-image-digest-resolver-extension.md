# Story S1-09 — `ProbeContext.image_digest_resolver` extension + contract-freeze regen

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** S1-08
**ADRs honored:** 02-ADR-0004

## Context

`RuntimeTraceProbe` (S5-02) needs the image digest as part of its `declared_inputs` so a rebuilt-image-with-same-Dockerfile invalidates the cache (image-digest drift adversarial — `tests/adv/phase02/test_image_digest_drift.py` in S5-05). The image isn't visible at `RepoSnapshot` construction time (the image is built mid-gather). The architect's solution — mirroring Phase 1 ADR-0002's `parsed_manifest` precedent — is to add **one** optional field to `ProbeContext`: a `Callable[[Path], str | None]` the coordinator binds. This is the **only** Phase-0-contract amendment in all of Phase 2, and the contract-freeze snapshot regeneration must encode the allowed-field list so a third field fails CI with the ADR-0004 pointer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #6 — RuntimeTraceProbe (cache key)` — describes the `image-digest:<resolved>` declared-input token and how the resolver is consumed.
  - `../phase-arch-design.md §"Data model"` (lines `# ---------- [contract — additive] codegenie/probes/base.py (Phase 0 + 1 frozen) ----------`) — the exact additive field signature.
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row "Image digest as a declared-input *token*" — Phase 0 `declared_inputs` discipline survives.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-image-digest-as-declared-input-token.md` — 02-ADR-0004 — the decision; mirrors Phase 1 ADR-0002's `parsed_manifest` precedent; `image_digest_resolver` is **the** one Phase-2 ProbeContext field.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0007-probe-contract-freeze.md` — Phase 0 ADR-0007 — contract-freeze snapshot test; this story regenerates it with one documented addition.
- **Source design:**
  - `../final-design.md §6 — Image digest as a declared-input token` — the synthesis ledger row.
- **Existing code:**
  - `src/codegenie/probes/base.py` — current `ProbeContext` fields (Phase 0 + Phase 1's `parsed_manifest` + `input_snapshot`). Phase 2 adds exactly one field.
  - `tests/unit/test_probe_contract.py` (Phase 0) — the snapshot test that hashes the `Probe` ABC + `ProbeContext` shape; this story regenerates the snapshot.
  - `tests/snapshots/probe_contract.v1.json` (likely path; verify at impl time) — the committed snapshot file.
- **External docs (only if directly relevant):**
  - None.

## Goal

Extend `src/codegenie/probes/base.py` `ProbeContext` with **one** additive optional field — `image_digest_resolver: Callable[[Path], str | None] | None = None` — and regenerate `tests/unit/test_probe_contract.py`'s snapshot so that *only* this documented amendment is admitted and any future widening fails CI with an `ADR-0004` pointer in the error message.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/probes/base.py` `ProbeContext` gains exactly one field after `input_snapshot`:
  ```python
  image_digest_resolver: Callable[[Path], str | None] | None = None  # Phase 2 ADR-0004
  ```
  The field is optional with default `None`. No other field is added or modified.
- [ ] **AC-2.** The `Probe` ABC itself is unchanged — no new methods, no new attributes. The `forbidden-patterns` pre-commit (extended by S1-11) bans `model_construct` under the new packages but does **not** restrict edits to `base.py` beyond the snapshot test (which is the structural defense for the ABC).
- [ ] **AC-3.** `tests/unit/test_probe_contract.py` (or the equivalent contract-freeze snapshot test) is regenerated. The regeneration script is a standalone, runnable Python file under `scripts/regen_probe_contract.py` (or wherever Phase 0/1 lives — adapt). The script **encodes the allowed-field list** as a Python literal at the top of the file; the snapshot check is "fields in `ProbeContext` MUST be a subset of `_ALLOWED_PROBE_CONTEXT_FIELDS`". A new field added by a future contributor without editing the allowed-list fails CI with: `"third field added to ProbeContext violates 02-ADR-0004 §Reversibility — file a Phase 2 ADR amendment or revert"`.
- [ ] **AC-4.** `_ALLOWED_PROBE_CONTEXT_FIELDS` is exactly:
  ```python
  {
      "cache_dir", "output_dir", "workspace", "logger", "config",
      "parsed_manifest", "input_snapshot",        # Phase 1 ADR-0002
      "image_digest_resolver",                     # Phase 2 ADR-0004
  }
  ```
  (Reconcile with the actual Phase 0/1 field set at implementation time — the architecture cites `parsed_manifest` precedent for Phase 1; check `src/codegenie/probes/base.py` to confirm current fields.)
- [ ] **AC-5.** A *unit* test (not the snapshot) verifies the addition is *additive* — Phase 0/1 callers constructing `ProbeContext(cache_dir=..., output_dir=..., ...)` without the new kwarg continue to work; the default is `None`.
- [ ] **AC-6.** A test asserts the Phase 0 `forbidden-patterns` hook (banning direct `subprocess.run` / `asyncio.create_subprocess_exec` outside `exec.py`) continues to pass after this story.
- [ ] **AC-7.** `src/codegenie/probes/base.py` is routed to `CODEOWNERS` (`docs/CODEOWNERS` or `.github/CODEOWNERS`) — any edit requires explicit review. If a `CODEOWNERS` file exists, add a rule:
  ```
  /src/codegenie/probes/base.py @phase2-architects
  /tests/snapshots/probe_contract.* @phase2-architects
  ```
  If none exists, file a follow-up issue in S8-04 (Phase 3 handoff) — do not create CODEOWNERS speculatively here.
- [ ] **AC-8.** The `parsed_manifest` field (Phase 1 ADR-0002) is **NOT renamed or repositioned**; its type annotation is preserved; the `Callable` import is unchanged.
- [ ] **AC-9.** The regeneration script is idempotent: running it twice produces no diff (golden-stability discipline mirrored from S7-03).
- [ ] **AC-10.** A test attempts to add a fake third field via a `dataclasses.fields()`-monkeypatched assertion (or via a regression test that explicitly tries to add `_FAKE_THIRD_FIELD` to the allowed-list and asserts the script rejects it). The error message contains `"02-ADR-0004"` and `"file a Phase 2 ADR amendment"`.
- [ ] **AC-11.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and the Phase 0 `contract-freeze` CI job (recomputed with this story's snapshot regeneration) all pass.

## Implementation outline

1. Open `src/codegenie/probes/base.py`. Add the one field after `input_snapshot`. Confirm `Callable` is already imported (from `collections.abc` per Phase 1 ADR-0002 widening); if not, add the import via the same explicit `# ADR-0002 (Phase 1)` pattern.
2. Open `tests/unit/test_probe_contract.py`. Examine the existing snapshot strategy. Either it stores the snapshot in a JSON file or computes a hash inline. Either way:
   - Add `_ALLOWED_PROBE_CONTEXT_FIELDS` constant at the top.
   - Update the snapshot-validation to assert `{f.name for f in dataclasses.fields(ProbeContext)} == _ALLOWED_PROBE_CONTEXT_FIELDS`.
3. Regenerate the snapshot (run the regen script; commit the diff).
4. Write red tests (see TDD plan); confirm one currently fails (the new field doesn't exist yet).
5. Make the additive edit; confirm green.
6. Refactor: update the snapshot regeneration script's documentation; confirm the script prints the ADR-0004 pointer on third-field rejection.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_probe_contract.py` (extend the existing Phase 0 file)

```python
from __future__ import annotations

import dataclasses

import pytest

from codegenie.probes.base import ProbeContext


# AC-4 — the allowed-field set is encoded HERE in the test as well, so the
# regen script and the test agree.
_ALLOWED_PROBE_CONTEXT_FIELDS = {
    "cache_dir", "output_dir", "workspace", "logger", "config",
    "parsed_manifest", "input_snapshot",
    "image_digest_resolver",  # Phase 2 ADR-0004
}


def test_probe_context_field_set_matches_allowed() -> None:
    actual = {f.name for f in dataclasses.fields(ProbeContext)}
    assert actual == _ALLOWED_PROBE_CONTEXT_FIELDS, (
        f"ProbeContext fields drifted: actual={actual}, "
        f"allowed={_ALLOWED_PROBE_CONTEXT_FIELDS}. "
        f"Any addition requires a Phase 2 ADR amendment (02-ADR-0004 §Reversibility)."
    )


def test_image_digest_resolver_is_optional_with_none_default() -> None:
    # AC-5 — backward compatible with Phase 0/1 callers
    from logging import getLogger
    from pathlib import Path
    ctx = ProbeContext(
        cache_dir=Path("/tmp/c"),
        output_dir=Path("/tmp/o"),
        workspace=Path("/tmp/w"),
        logger=getLogger("test"),
        config={},
    )
    assert ctx.image_digest_resolver is None


def test_image_digest_resolver_accepts_callable() -> None:
    from logging import getLogger
    from pathlib import Path
    def _resolver(_p: Path) -> str | None:
        return "sha256:cafef00d"
    ctx = ProbeContext(
        cache_dir=Path("/tmp/c"),
        output_dir=Path("/tmp/o"),
        workspace=Path("/tmp/w"),
        logger=getLogger("test"),
        config={},
        image_digest_resolver=_resolver,
    )
    assert ctx.image_digest_resolver is _resolver
    assert ctx.image_digest_resolver(Path("/tmp/img")) == "sha256:cafef00d"


def test_parsed_manifest_unchanged() -> None:
    """AC-8 — the Phase 1 field is not renamed or modified."""
    field_names = {f.name for f in dataclasses.fields(ProbeContext)}
    assert "parsed_manifest" in field_names


def test_probe_abc_unchanged() -> None:
    """AC-2 — Probe ABC has no new methods/attributes from this story."""
    from codegenie.probes.base import Probe
    # The ABC's abstract method set is run() (and Phase 0/1 attributes); no
    # `heaviness`, no `runs_last`, no `image_digest_resolver` on the ABC.
    assert not hasattr(Probe, "image_digest_resolver")
    assert not hasattr(Probe, "heaviness")
    assert not hasattr(Probe, "runs_last")
```

A second test file `tests/unit/test_probe_contract_regen_script.py`:

```python
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def test_regen_script_rejects_unknown_third_field(tmp_path: Path) -> None:
    """AC-10 — the regen script enforces the allowed-field list. Adding an
    undocumented field must fail with an ADR-0004 pointer."""
    # Spawn the regen script in a subprocess with a monkeypatched ProbeContext
    # that adds a forbidden field. The script must exit non-zero and print the
    # ADR pointer.
    # Pseudocode — the implementer wires this to the actual regen script path.
    script = Path("scripts/regen_probe_contract.py")
    result = subprocess.run(
        [sys.executable, str(script), "--check-allowed-fields-only"],
        capture_output=True, text=True,
    )
    # In a healthy tree this is a successful pre-check; the failure mode is
    # exercised by a sibling test that injects a synthetic third field via
    # importlib magic. Pick whichever shape Phase 0's existing snapshot test
    # uses for "I tampered the snapshot" — the discipline is the same.
    assert result.returncode == 0
```

Run — confirm `test_image_digest_resolver_is_optional_with_none_default` fails because the field doesn't exist. Commit.

### Green — make it pass

In `src/codegenie/probes/base.py`:

```python
@dataclass
class ProbeContext:
    cache_dir: Path
    output_dir: Path
    workspace: Path
    logger: Logger
    config: dict[str, Any]
    # Phase 1 ADR-0002
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
    input_snapshot: frozenset["InputFingerprint"] | None = None
    # Phase 2 ADR-0004 — the one additive amendment in Phase 2.
    image_digest_resolver: Callable[[Path], str | None] | None = None
```

Update the snapshot regen script (`scripts/regen_probe_contract.py` or equivalent) with the new allowed-field list. Run the regen; commit the updated snapshot.

### Refactor — clean up

- Add a one-line note to the `base.py` module docstring: *"Phase 2 ADR-0004 amends this contract by adding **one** optional field, `image_digest_resolver`. The snapshot regeneration script enforces the allowed-field list — adding a third field fails CI with an ADR-0004 pointer."*
- Confirm `CODEOWNERS` routing — if the file exists, add the two lines. If not, file the follow-up in S8-04.
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/probes/base.py tests/unit/test_probe_contract*.py`, `pytest tests/unit/test_probe_contract*.py -v`. Run the contract-freeze CI job locally if possible (`pytest tests/unit/test_probe_contract.py`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base.py` | Add `image_digest_resolver: Callable[[Path], str | None] | None = None`. |
| `tests/unit/test_probe_contract.py` | Extend `_ALLOWED_PROBE_CONTEXT_FIELDS`; field-set assertion; backward-compat constructor; ABC-unchanged spot-checks. |
| `tests/unit/test_probe_contract_regen_script.py` | Regen-script idempotence + third-field rejection. |
| `scripts/regen_probe_contract.py` | Update allowed-field list; emit ADR-0004 pointer on rejection. |
| `tests/snapshots/probe_contract.v1.json` (or equivalent) | Regenerated snapshot reflecting the one new field. |
| `.github/CODEOWNERS` (or `docs/CODEOWNERS`) | Route `probes/base.py` + snapshots — IF the file already exists. Otherwise file a follow-up in S8-04. |

## Out of scope

- **Phase 0 `Probe` ABC edits** — strictly forbidden by 02-ADR-0003 + 02-ADR-0004. The ABC is frozen.
- **`RuntimeTraceProbe`'s consumption of `image_digest_resolver`** — handled by S5-02; this story only ships the field.
- **The Phase 1 `parsed_manifest` semantics** — unchanged; reuse the precedent.
- **`InputFingerprint` evolution** — Phase 1 contract; not extended in Phase 2.
- **`heaviness`/`runs_last` decorator-kwargs** — handled by S1-08 (the previous story); this story does not edit `base.py` beyond the one field.
- **`@register_index_freshness_check` consumption** — that's S4-01; this story is the data-only extension.

## Notes for the implementer

- **The "one and only one Phase-0-contract amendment in Phase 2" rule is structurally encoded.** The allowed-field list is the gate; the regen script enforces it; a third field fails CI with an explicit pointer to 02-ADR-0004 §Reversibility. Do not soften the pointer — fail-loud is the discipline.
- **Reconcile the field list with current Phase 0/1 reality.** Phase 0 ships `ProbeContext(cache_dir, output_dir, workspace, logger, config)`; Phase 1 adds `parsed_manifest` and `input_snapshot`. If your tree shows a different set, **stop and ask** — do not silently grow the allowed-field list. The Phase 0/1 actual state is the input.
- **`Callable[[Path], str | None] | None = None` — the type matters.** `Path` because the resolver may receive the path to the image-tar / Dockerfile; `str | None` because the image may not have been built yet (warm path with no image returns `None`); the outer `| None = None` makes the *resolver itself* optional, so coordinator integration can be deferred to S5-02.
- **`logger: Logger` field — Phase 0 uses stdlib `logging`, not `structlog`.** The architect's design uses `structlog` elsewhere; the `ProbeContext.logger` field is the Phase 0 contract and is unchanged. Coordinator wires `structlog` separately at dispatch time.
- **Snapshot file vs. inline-hash strategy.** Phase 0 may use either pattern. Verify by reading the current `tests/unit/test_probe_contract.py`; preserve the chosen pattern. If the snapshot is a JSON file, regenerate it and commit the diff (one new key for the new field). If the snapshot is an inline hash, recompute it with the new field included.
- **The Phase 0 `forbidden-patterns` pre-commit is the structural backstop.** It catches `model_construct`, direct `subprocess.run`, and now (per S1-11) `model_construct` under the new Phase 2 packages. It does NOT catch arbitrary edits to `base.py`; the snapshot test is the defense there.
- **CODEOWNERS is operational, not blocking.** If `.github/CODEOWNERS` does not exist, this story does not create it speculatively (Rule 2 — Simplicity First); the follow-up belongs in S8-04 (Phase 3 handoff) alongside other operational concerns.
- **The "fields-set equality" assertion is strict (`==`), not subset.** A future contributor cannot silently drop `input_snapshot` either — the allowed-list is the exact set.
