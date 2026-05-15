# Story S1-09 — `ProbeContext.image_digest_resolver` extension + contract-freeze regen

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** M
**Depends on:** S1-08
**ADRs honored:** 02-ADR-0004, 00-ADR-0007 (probe-contract-freeze), 01-ADR-0002 (precedent)

## Validation notes (2026-05-15)

This story was hardened by `phase-story-validator` before execution. Changes:

1. **`localv2.md §4` update added as a load-bearing AC.** The original story omitted it; 00-ADR-0007 says "change code to match doc, never the inverse," and `test_probe_contract_doc_fingerprint_matches_snapshot` (Tier 1) **fails** unless the doc is updated *first*. Without this AC the executor would commit a snapshot whose `doc_fingerprint` was regenerated from an out-of-date doc — a silent contract drift the regen script cannot itself catch.
2. **Reconciled with existing test infrastructure.** The story originally invented a parallel `_ALLOWED_PROBE_CONTEXT_FIELDS` set inside `tests/unit/test_probe_contract.py`. The actual file already carries `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` (Tier 7) with a hard-coded 7-field tuple, plus a `test_probe_context_sentinel_fires_on_synthetic_third_field` in-test synthetic-dataclass mutation-killer. Per Rule 11 (match the codebase's conventions), this story now **extends the existing sentinel** by renaming the tuple to `_ALLOWED_PROBE_CONTEXT_FIELDS` (no ADR suffix; multi-ADR moving forward) and adds a *second* ADR-0004-specific synthetic-third-field mutation killer mirroring the Phase-1 one — so the failure message routes contributors to ADR-0004 §Reversibility, not (only) ADR-0002.
3. **Corrected the regen script path.** Story said `scripts/regen_probe_contract.py`; the file in tree is `scripts/regen_probe_contract_snapshot.py`. Updated everywhere.
4. **Replaced pseudo-code subprocess test with the codebase's in-test synthetic-dataclass pattern.** The story's `tests/unit/test_probe_contract_regen_script.py` was a sketch (`Pseudocode — the implementer wires this`). Per Rule 9 (tests verify intent concretely) and Rule 11, mirror `test_probe_context_sentinel_fires_on_synthetic_third_field` instead — build a synthetic 8-field dataclass, assert the existing sentinel raises with regex match for `ADR-0004`. No subprocess required; deterministic.
5. **Added type-annotation pin (mutation-killer).** A new AC asserts `image_digest_resolver`'s annotation `repr()` contains `"Callable"`, `"Path"`, and `"str | None"` (mirrors the existing `test_probe_context_new_field_annotations_pinned`). Catches silent retypes like `Callable[[Path], str]` (dropping `| None` from the return) or `Callable[[str], str | None]` (dropping `Path`).
6. **Added a `localv2.md §4` doc-grep AC.** Mirrors `test_localv2_section_4_shows_phase1_probe_context_fields`. Names *what* drifted when the Tier 1 doc_fingerprint check fires — without it, the failure is opaque.
7. **CODEOWNERS scope narrowed.** AC-7 originally proposed `@phase2-architects` as the team alias. There is no such GitHub team and the file already carries `TODO(S5-02): CODEOWNERS entry required` (see `src/codegenie/probes/base.py` header). Resolved: this story does NOT create CODEOWNERS speculatively (Rule 2); the TODO already exists; AC-7 reworded to verify the TODO is still present (regression-resistance) and the actual CODEOWNERS file is filed under S5-02 / S8-04 follow-up.
8. **AC-2 (Probe ABC unchanged) strengthened via the existing structural snapshot.** The story tried to add bespoke `hasattr(Probe, ...)` checks; the existing Tier 4 `test_structural_signature_captures_required_probe_class_attributes` + `test_structural_signature_preserves_probe_class_attribute_order` already pin the ABC's class-attribute set and order. AC-2 now asserts those Tier 4 tests continue to pass (regression-style) rather than adding parallel `hasattr` spot-checks.
9. **Notes-for-implementer: queued kernel extraction.** `_ALLOWED_PROBE_CONTEXT_FIELDS` is the second precedent (ADR-0002 + ADR-0004). If a Phase 3+ ADR adds a third optional callable, the rule-of-three is reached and a `_ALLOWED_PROBE_CONTEXT_FIELDS_BY_ADR: Mapping[ADRId, frozenset[str]]` registry (Open/Closed at the file boundary) should be extracted — Phase 3 owns that decision; do NOT introduce it speculatively here (Rule 2).
10. **Removed the regen-script subprocess test file.** `tests/unit/test_probe_contract_regen_script.py` from the original TDD plan was redundant once the existing in-test synthetic-dataclass pattern is reused. Files-to-touch trimmed.

Verdict: **HARDENED** (no structural problems with the story's goal or scope; concrete fixes to ACs, TDD plan, and file list).

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

- [ ] **AC-1.** `src/codegenie/probes/base.py` `ProbeContext` gains exactly one field, appended after `input_snapshot`:
  ```python
  # Phase 2 ADR-0004 — the one additive amendment in Phase 2.
  image_digest_resolver: Callable[[Path], str | None] | None = None
  ```
  The field is optional with default `None`. No other field is added or modified. The `Callable` and `Path` imports are already present (Phase 1 ADR-0002 widened `ALLOWED_BASE_PY_IMPORTS` to admit `collections.abc.Callable` and `Mapping`); no import edits are needed.
- [ ] **AC-2.** The `Probe` ABC class itself is unchanged — verified by the existing Tier 4 contract-snapshot tests in `tests/unit/test_probe_contract.py`:
  - `test_structural_signature_captures_required_probe_class_attributes` continues to pass (same nine class attributes, no additions).
  - `test_structural_signature_preserves_probe_class_attribute_order` continues to pass (same order).
  - `test_probe_class_has_no_version_attribute` continues to pass.
  No bespoke `hasattr(Probe, ...)` spot-checks are added — the structural snapshot is the single chokepoint and adding parallel checks creates two sources of truth.
- [ ] **AC-3.** **`docs/localv2.md §4` is updated to include `image_digest_resolver` in the `ProbeContext` block** *before* the snapshot is regenerated. The added line is exactly:
  ```python
      # Phase 2 ADR-0004. No further extensions without ADR amendment.
      image_digest_resolver: Callable[[Path], str | None] | None = None
  ```
  appended after `input_snapshot:` inside the `class ProbeContext:` block. This is load-bearing per 00-ADR-0007 ("change code to match doc, never the inverse") — without this edit, `test_probe_contract_doc_fingerprint_matches_snapshot` (Tier 1) fails with the `templates/adr-amendment.md` pointer even after the regen script runs against the un-updated doc.
- [ ] **AC-4.** `tests/snapshots/probe_contract.v1.json` is regenerated via `python scripts/regen_probe_contract_snapshot.py` *after* AC-1 and AC-3 land. The committed snapshot:
  - has a `doc_fingerprint` value **different** from the pre-story value (asserts the doc edit actually changed the hash — guards against an executor who runs the script before editing the doc and commits an unchanged digest).
  - has a `structural_signature.ProbeContext.fields` list whose last element is `{"name": "image_digest_resolver", "type": "Callable[[Path], str | None] | None", "default": "None"}` (or the renderer-equivalent — verify by reading the regen script's `_stable_type_repr` output).
  - `snapshot_schema_version` is unchanged at `1`.
- [ ] **AC-5.** The existing Tier 7 sentinel in `tests/unit/test_probe_contract.py` is updated:
  - `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` is renamed to `_ALLOWED_PROBE_CONTEXT_FIELDS` (no ADR suffix; the tuple now spans ≥2 ADRs).
  - The tuple becomes exactly `("cache_dir", "output_dir", "workspace", "logger", "config", "parsed_manifest", "input_snapshot", "image_digest_resolver")`.
  - `test_probe_context_field_list_matches_adr_0002_amendment` is renamed to `test_probe_context_field_list_matches_allowed` (no per-ADR suffix; mention both ADRs in the failure message).
  - The failure message names BOTH ADR-0002 (parsed_manifest, input_snapshot) AND ADR-0004 (image_digest_resolver), and tells contributors to file a new Phase ADR amendment for any third addition.
- [ ] **AC-6.** A new mutation-killer test `test_probe_context_sentinel_fires_on_synthetic_phase_2_addition` is added, mirroring the existing `test_probe_context_sentinel_fires_on_synthetic_third_field`. It builds a synthetic 9-field dataclass (the 8 allowed plus one bogus addition) via `@dataclasses.dataclass`, asserts the equality check raises `AssertionError`, and asserts `pytest.raises(..., match=r"ADR-0004")` (regex specific to the new ADR). The existing `..._synthetic_third_field` test is kept and updated so its match regex now includes `r"ADR-0002|ADR-0004"` (either-routes-to-an-amendment-ADR), or kept as `ADR-0002` if the test message is updated to name both.
- [ ] **AC-7.** A new mutation-killer test `test_image_digest_resolver_annotation_pinned` is added in the Tier 7 section, asserting:
  - `"Callable" in repr(ann["image_digest_resolver"])`
  - `"Path" in repr(ann["image_digest_resolver"])`
  - `"str | None" in repr(ann["image_digest_resolver"])`
  Mirrors `test_probe_context_new_field_annotations_pinned`. Catches silent retypes like `Callable[[Path], str]` (drops `| None` return), `Callable[[str], str | None]` (drops `Path`), or `dict[Path, str]` (drops `Callable` entirely).
- [ ] **AC-8.** A new doc-grep test `test_localv2_section_4_shows_image_digest_resolver` is added, mirroring `test_localv2_section_4_shows_phase1_probe_context_fields`. Asserts that `image_digest_resolver:` appears in the extracted §4 body. This names *what* drifted when Tier 1 fires; without it the contributor sees an opaque hash mismatch.
- [ ] **AC-9.** A new unit test `test_probe_context_image_digest_resolver_is_optional_with_none_default` verifies the Phase 0/1 construction signature is preserved — constructing `ProbeContext(cache_dir=…, output_dir=…, workspace=…, logger=…, config={})` without the new kwarg succeeds and `ctx.image_digest_resolver is None`. Backward-compat smoke test for callers that predate Phase 2.
- [ ] **AC-10.** A new unit test `test_probe_context_image_digest_resolver_accepts_callable_returning_none` verifies the *type contract*'s `None` return arm:
  - Construct with a resolver that returns `None` (e.g., `lambda _p: None`); call it; assert the result is `None`.
  - Construct with a resolver that returns a digest string (e.g., `lambda _p: "sha256:cafef00d"`); call it; assert the result is the string.
  Catches a future widener who silently broadens to `Callable[[Path], str]` (drops the `None` arm).
- [ ] **AC-11.** The regen script `scripts/regen_probe_contract_snapshot.py` is **idempotent**: running it twice consecutively produces a byte-identical `tests/snapshots/probe_contract.v1.json`. Verify by a new test (preferred) or by manual confirmation logged in the implementation notes. Naming convention: `test_regen_script_is_idempotent` in a new `tests/unit/test_probe_contract_regen_script.py`, or appended to the existing `test_probe_contract.py`. The test runs the regen script in a subprocess against the live tree, captures the snapshot bytes before and after a second invocation, and asserts equality.
- [ ] **AC-12.** The `parsed_manifest` field (Phase 1 ADR-0002) is **NOT renamed or repositioned**; its annotation `Callable[[Path], Mapping[str, Any] | None] | None = None` is byte-identical. Verified by the existing `test_probe_context_new_field_annotations_pinned`.
- [ ] **AC-13.** The Phase 0 `forbidden-patterns` check (`scripts/check_forbidden_patterns.py`) continues to pass on the modified `base.py`. Verified by running the script as part of `make lint` / `pre-commit run --all-files`; no new ban patterns are added or removed by this story.
- [ ] **AC-14.** The `TODO(S5-02): CODEOWNERS entry required for src/codegenie/probes/base.py …` comment at the top of `src/codegenie/probes/base.py` is **preserved verbatim** — the existing `test_base_py_carries_codeowners_todo_for_s5_02` continues to pass. CODEOWNERS is NOT created speculatively in this story (Rule 2); the linkage is already audit-logged via the TODO and the follow-up is owned by S5-02 / S8-04.
- [ ] **AC-15.** All Tier 1 anchoring tests pass:
  - `test_probe_contract_doc_fingerprint_matches_snapshot` — the new `localv2.md §4` body normalizes-and-hashes to the new `doc_fingerprint`.
  - `test_probe_class_structural_signature_matches_snapshot` — the new `ProbeContext` shape matches the regenerated `structural_signature`.
- [ ] **AC-16.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie tests/unit/test_probe_contract*.py`, the Phase 0 `contract-freeze` CI job (i.e. `pytest tests/unit/test_probe_contract.py -v`), and `pytest tests/unit/test_probe_contract*.py -v` all pass.
- [ ] **AC-17.** The TDD plan's red tests exist on disk, were committed in a red-state commit before the implementation commit, and are now green. Confirmable via `git log -- tests/unit/test_probe_contract*.py` showing two commits in this story's range with descriptive subject lines.

## Implementation outline

**Order matters** — the doc edit must precede the code edit, and the snapshot regeneration must come last, otherwise the Tier 1 anchoring tests fail mid-flight.

1. **Red phase — write the failing tests first, against the *current* tree.**
   - Edit `tests/unit/test_probe_contract.py`:
     - Rename `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` → `_ALLOWED_PROBE_CONTEXT_FIELDS` and extend the tuple by appending `"image_digest_resolver"`.
     - Rename `test_probe_context_field_list_matches_adr_0002_amendment` → `test_probe_context_field_list_matches_allowed`; update the failure message to name both ADR-0002 and ADR-0004.
     - Add the new tests: `test_probe_context_image_digest_resolver_is_optional_with_none_default` (AC-9), `test_probe_context_image_digest_resolver_accepts_callable_returning_none` (AC-10), `test_image_digest_resolver_annotation_pinned` (AC-7), `test_localv2_section_4_shows_image_digest_resolver` (AC-8), `test_probe_context_sentinel_fires_on_synthetic_phase_2_addition` (AC-6).
   - Add (or extend) `tests/unit/test_probe_contract_regen_script.py` with `test_regen_script_is_idempotent` (AC-11). If a single file is cleaner, append to `test_probe_contract.py`.
   - Run `pytest tests/unit/test_probe_contract*.py -v`. The new tests fail (field doesn't exist; doc-grep test fails; sentinel tuple mismatch). The Tier 1 anchoring tests **also** fail (the sentinel tuple is the new 8-tuple but `ProbeContext` is still 7-field). This is the expected red state.
   - **Commit the red state** with subject `test(phase2/S1-09): RED — image_digest_resolver contract extension`.

2. **Green phase — edit doc, then code, then regenerate snapshot.**
   - **Step 2a.** Edit `docs/localv2.md §4` `ProbeContext` block: append the `image_digest_resolver` line exactly as in AC-3, preserving the leading 4-space indent and the `# Phase 2 ADR-0004. No further extensions without ADR amendment.` comment style mirroring Phase 1's. **Do not run the regen script yet.**
   - **Step 2b.** Edit `src/codegenie/probes/base.py`:
     - Append the new field after `input_snapshot` in the `ProbeContext` dataclass with the same comment as in §4.
     - Update the module docstring with one sentence: *"Phase 2 ADR-0004 adds **one** optional field, `image_digest_resolver`, mirroring Phase 1 ADR-0002's `parsed_manifest` precedent. Adding a third future field requires a new phase ADR amendment; the sentinel test in `tests/unit/test_probe_contract.py` fails CI with an explicit pointer."*
   - **Step 2c.** Run `python scripts/regen_probe_contract_snapshot.py`. Inspect the diff against `tests/snapshots/probe_contract.v1.json`:
     - `doc_fingerprint` changes (it MUST — that proves AC-3 actually landed).
     - `structural_signature.ProbeContext.fields` grows by one entry at the end.
     - No other key changes.
   - **Step 2d.** Run `pytest tests/unit/test_probe_contract*.py -v`. All tests now green. If any Tier 1, Tier 4, or Tier 7 test fails, the doc edit, code edit, or snapshot regen is out of sync — diagnose; do NOT add escape hatches.
   - **Commit** with subject `feat(phase2/S1-09): GREEN — ProbeContext.image_digest_resolver (ADR-0004)`.

3. **Refactor phase — verify idempotence, lint, type-check.**
   - Run the regen script a second time; confirm zero diff (AC-11).
   - Run `ruff check`, `ruff format --check`, `mypy --strict src/codegenie tests/unit/test_probe_contract*.py`, `make lint` (or `pre-commit run --all-files`).
   - Verify the AC-14 `TODO(S5-02): CODEOWNERS entry required` comment is still present in `base.py`.
   - **Commit** with subject `refactor(phase2/S1-09): REFACTOR — idempotence + lint clean`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Edit `tests/unit/test_probe_contract.py` (extend the existing Phase 0/1 file; do NOT create a parallel test file). The codebase's idiom is in-test synthetic-dataclass mutation-killers — mirror it.

```python
# In the Tier 7 section, rename the existing sentinel constant and tests:

_ALLOWED_PROBE_CONTEXT_FIELDS: tuple[str, ...] = (
    "cache_dir",
    "output_dir",
    "workspace",
    "logger",
    "config",
    "parsed_manifest",     # Phase 1 ADR-0002
    "input_snapshot",      # Phase 1 ADR-0002
    "image_digest_resolver",  # Phase 2 ADR-0004
)
_ADR_0004_PATH = (
    REPO_ROOT
    / "docs"
    / "phases"
    / "02-context-gather-layers-b-g"
    / "ADRs"
    / "0004-image-digest-as-declared-input-token.md"
)


def test_probe_context_field_list_matches_allowed() -> None:
    # AC-5 — the allowed-field tuple now spans ADR-0002 and ADR-0004.
    # Any third future addition requires a new phase ADR amendment.
    import dataclasses

    actual = tuple(f.name for f in dataclasses.fields(base.ProbeContext))
    assert actual == _ALLOWED_PROBE_CONTEXT_FIELDS, (
        f"ProbeContext field list {actual} does not match the allowed set. "
        f"Current additions are gated by ADR-0002 (parsed_manifest, input_snapshot) "
        f"and ADR-0004 (image_digest_resolver). Any new field requires a new "
        f"Phase ADR amendment. See "
        f"docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md "
        f"and docs/phases/02-context-gather-layers-b-g/ADRs/"
        f"0004-image-digest-as-declared-input-token.md."
    )


def test_probe_context_image_digest_resolver_is_optional_with_none_default(tmp_path: Path) -> None:
    # AC-9 — backward compatible with Phase 0/1 callers (no kwarg supplied).
    import logging

    ctx = base.ProbeContext(
        cache_dir=tmp_path / "c",
        output_dir=tmp_path / "o",
        workspace=tmp_path / "w",
        logger=logging.getLogger("test"),
        config={},
    )
    assert ctx.image_digest_resolver is None


def test_probe_context_image_digest_resolver_accepts_callable_returning_none(tmp_path: Path) -> None:
    # AC-10 — the `| None` return arm is part of the contract; the resolver
    # may legitimately report "no image built yet".
    import logging

    def _none_resolver(_p: Path) -> str | None:
        return None

    def _digest_resolver(_p: Path) -> str | None:
        return "sha256:cafef00d"

    ctx_none = base.ProbeContext(
        cache_dir=tmp_path / "c", output_dir=tmp_path / "o", workspace=tmp_path / "w",
        logger=logging.getLogger("test"), config={},
        image_digest_resolver=_none_resolver,
    )
    assert ctx_none.image_digest_resolver is _none_resolver
    assert ctx_none.image_digest_resolver(tmp_path / "img") is None

    ctx_dig = base.ProbeContext(
        cache_dir=tmp_path / "c", output_dir=tmp_path / "o", workspace=tmp_path / "w",
        logger=logging.getLogger("test"), config={},
        image_digest_resolver=_digest_resolver,
    )
    assert ctx_dig.image_digest_resolver(tmp_path / "img") == "sha256:cafef00d"


def test_image_digest_resolver_annotation_pinned() -> None:
    # AC-7 — catches silent retypes: drop `| None` return, drop `Path` arg,
    # widen to `dict[Path, str]`, etc.
    import inspect as _inspect

    ann = _inspect.get_annotations(base.ProbeContext)
    rendered = repr(ann["image_digest_resolver"])
    assert "Callable" in rendered, rendered
    assert "Path" in rendered, rendered
    assert "str | None" in rendered, rendered


def test_localv2_section_4_shows_image_digest_resolver() -> None:
    # AC-8 — code-matches-doc is the ADR-0007 discipline; this test names
    # *what* drifted when Tier 1 fingerprint fires.
    body = extract_section_4_body(LOCALV2_PATH.read_text(encoding="utf-8"))
    assert "image_digest_resolver:" in body, (
        "localv2.md §4 ProbeContext is missing image_digest_resolver (02-ADR-0004)"
    )


def test_adr_0004_names_image_digest_resolver() -> None:
    # AC-6 companion — the ADR text is the human-facing record; an ADR that
    # doesn't name its own field is rot the moment a contributor reads it.
    text = _ADR_0004_PATH.read_text(encoding="utf-8")
    assert "image_digest_resolver" in text


def test_probe_context_sentinel_fires_on_synthetic_phase_2_addition() -> None:
    # AC-6 — mirror `test_probe_context_sentinel_fires_on_synthetic_third_field`
    # but for the ADR-0004 amendment. A synthetic dataclass with one MORE
    # field than the allowed tuple stands in for the future amendment.
    import dataclasses as _dc

    @_dc.dataclass
    class _SyntheticNineField:
        cache_dir: Path
        output_dir: Path
        workspace: Path
        logger: Any
        config: dict[str, Any]
        parsed_manifest: Any = None
        input_snapshot: Any = None
        image_digest_resolver: Any = None
        future_extra_field: Any = None  # the offending addition

    actual = tuple(f.name for f in _dc.fields(_SyntheticNineField))
    with pytest.raises(AssertionError, match=r"ADR-0004"):
        assert actual == _ALLOWED_PROBE_CONTEXT_FIELDS, (
            f"ProbeContext field list {actual} does not match the allowed set. "
            f"Current additions are gated by ADR-0002 (parsed_manifest, input_snapshot) "
            f"and ADR-0004 (image_digest_resolver). Any new field requires a new "
            f"Phase ADR amendment."
        )
```

Idempotence test (AC-11). Either append to `test_probe_contract.py` or place in a new `tests/unit/test_probe_contract_regen_script.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "probe_contract.v1.json"
REGEN_SCRIPT = REPO_ROOT / "scripts" / "regen_probe_contract_snapshot.py"


def test_regen_script_is_idempotent() -> None:
    # AC-11 — golden-stability discipline (mirrors S7-03). Running the script
    # twice must produce a byte-identical snapshot. The implicit contract:
    # `_stable_type_repr` and `structural_signature` are deterministic across
    # Python sub-processes on the same interpreter.
    assert REGEN_SCRIPT.exists(), REGEN_SCRIPT
    before = SNAPSHOT_PATH.read_bytes()
    r1 = subprocess.run([sys.executable, str(REGEN_SCRIPT)], capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    after_first = SNAPSHOT_PATH.read_bytes()
    r2 = subprocess.run([sys.executable, str(REGEN_SCRIPT)], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    after_second = SNAPSHOT_PATH.read_bytes()
    assert after_first == after_second, (
        "regen script is not idempotent — running twice produced different snapshots"
    )
    # And the committed snapshot is up-to-date (no diff vs. before).
    assert before == after_second, (
        "committed snapshot is stale; run `python scripts/regen_probe_contract_snapshot.py`"
    )
```

Run `pytest tests/unit/test_probe_contract*.py -v`. The new tests fail; also several existing Tier 1 + Tier 7 tests fail because the sentinel tuple now expects 8 fields but `ProbeContext` has 7. **Commit the red state** before proceeding.

### Green — make the tests pass

**Step 1 — update `docs/localv2.md §4`.** Append `image_digest_resolver` to the `ProbeContext` block (AC-3 spec).

**Step 2 — edit `src/codegenie/probes/base.py`.**

```python
@dataclass
class ProbeContext:
    cache_dir: Path
    output_dir: Path           # where probe writes raw artifacts
    workspace: Path            # ephemeral workspace for the probe
    logger: Logger
    config: dict[str, Any]
    # Phase 1 additions (ADR-0002). No further extensions without ADR amendment.
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
    input_snapshot: frozenset["InputFingerprint"] | None = None
    # Phase 2 ADR-0004. No further extensions without ADR amendment.
    image_digest_resolver: Callable[[Path], str | None] | None = None
```

Add the one-line module-docstring note about the ADR-0004 amendment.

**Step 3 — regenerate the snapshot.** `python scripts/regen_probe_contract_snapshot.py`. Inspect the diff (one new entry in `ProbeContext.fields`; `doc_fingerprint` changed). Commit the snapshot.

Run `pytest tests/unit/test_probe_contract*.py -v` — all tests green.

### Refactor — clean up + verification

- Run the regen script a second time → no diff (AC-11 confirmed at the human level too).
- Run `ruff check`, `ruff format --check`, `mypy --strict src/codegenie tests/unit/test_probe_contract*.py`, `make lint`.
- Confirm `test_base_py_carries_codeowners_todo_for_s5_02` still passes (AC-14).
- Confirm no other CI job in the Phase 0/1 fence broke (`pytest tests/ -k "not slow"` or the project's full unit-test command).

## Files to touch

| Path | Why |
|---|---|
| `docs/localv2.md` | §4 `ProbeContext` block gains the `image_digest_resolver` line. Must precede the code edit and the snapshot regen (00-ADR-0007 — "change code to match doc"). |
| `src/codegenie/probes/base.py` | Append `image_digest_resolver: Callable[[Path], str \| None] \| None = None` after `input_snapshot`. One-line module-docstring note about the ADR-0004 amendment. |
| `tests/unit/test_probe_contract.py` | Rename `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` → `_ALLOWED_PROBE_CONTEXT_FIELDS`; extend tuple; rename and rewrite the field-list sentinel test; add the new ADR-0004 mutation-killer, annotation-pin, doc-grep, backward-compat, and `| None`-return tests (AC-5..AC-10). |
| `tests/unit/test_probe_contract_regen_script.py` *(new, optional)* | `test_regen_script_is_idempotent` (AC-11). May instead be appended to `test_probe_contract.py` if cleaner. |
| `tests/snapshots/probe_contract.v1.json` | Regenerated by `scripts/regen_probe_contract_snapshot.py` after the doc + code edits. `doc_fingerprint` changes; `ProbeContext.fields` grows by one entry. |
| `scripts/regen_probe_contract_snapshot.py` | **Read-only** — no edits required. The script is allowed-field-agnostic; it walks `dataclasses.fields(ProbeContext)` directly. The "allowed-list" gate lives in `tests/unit/test_probe_contract.py`, not in the script. |

**Out-of-scope file deltas (DO NOT TOUCH in this story):**

- `.github/CODEOWNERS` / `docs/CODEOWNERS` — not created speculatively (Rule 2); the `TODO(S5-02)` in `base.py` already records the linkage; the file lands under S5-02 or S8-04.
- `src/codegenie/cache.py` — token-recognizer dispatch for `image-digest:` belongs to a Phase 0 cache layer change, scoped to the consumer story (RuntimeTraceProbe S5-02), not this contract-extension story.
- Any probe file consuming the resolver — that's S5-02's surface.

## Out of scope

- **Phase 0 `Probe` ABC edits** — strictly forbidden by 02-ADR-0003 + 02-ADR-0004. The ABC is frozen.
- **`RuntimeTraceProbe`'s consumption of `image_digest_resolver`** — handled by S5-02; this story only ships the field.
- **The Phase 1 `parsed_manifest` semantics** — unchanged; reuse the precedent.
- **`InputFingerprint` evolution** — Phase 1 contract; not extended in Phase 2.
- **`heaviness`/`runs_last` decorator-kwargs** — handled by S1-08 (the previous story); this story does not edit `base.py` beyond the one field.
- **`@register_index_freshness_check` consumption** — that's S4-01; this story is the data-only extension.

## Notes for the implementer

- **Three-source-of-truth alignment is the load-bearing invariant.** `docs/localv2.md §4`, `src/codegenie/probes/base.py`, and `tests/snapshots/probe_contract.v1.json` must all agree on the new field at commit time. The Tier 1 anchoring tests (`test_probe_contract_doc_fingerprint_matches_snapshot` + `test_probe_class_structural_signature_matches_snapshot`) detect *any* drift across the three; the Tier 7 sentinel makes the failure message route to a concrete ADR. Edit in the order doc → code → snapshot regen. Skipping the doc edit will produce a snapshot whose `doc_fingerprint` was computed from a stale doc and the next contributor's regen will fail loudly.
- **Reconcile the field list with current Phase 0/1 reality before extending it.** Phase 0 ships `ProbeContext(cache_dir, output_dir, workspace, logger, config)`; Phase 1 ADR-0002 adds `parsed_manifest` and `input_snapshot`. The current `_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS` already encodes these seven. If your tree shows a different set, **stop and ask** — do not silently grow the allowed-field list.
- **`Callable[[Path], str | None] | None = None` — every arm of the type matters.**
  - `Path` (positional arg): the resolver receives a `Path` — per arch design it is the analyzed-repo root, used by the coordinator to look up the recently-built image.
  - `str | None` (return): `None` is the legitimate "no image built yet" path (`phase-arch-design.md §"Edge cases" row 14`). A future widener who drops `| None` from the return breaks the cache-fallback contract.
  - Outer `| None = None` (the field): the resolver itself is optional so Phase 0/1 callers and probes that don't need it ignore it.
  AC-7 pins all three arms via `repr()` substring assertions.
- **`logger: Logger` field — Phase 0 uses stdlib `logging`, not `structlog`.** The architect's design uses `structlog` elsewhere; the `ProbeContext.logger` field is the Phase 0 contract and is unchanged. Coordinator wires `structlog` separately at dispatch time.
- **Do NOT create a parallel `_ALLOWED_PROBE_CONTEXT_FIELDS` set inside the regen script.** The existing `scripts/regen_probe_contract_snapshot.py` is allowed-field-agnostic — it walks `dataclasses.fields(ProbeContext)` directly. Encoding the allowed-list inside the script as well would create two sources of truth (test + script) that would have to be updated in lockstep. The test is the gate; that's enough.
- **Future Phase 3+ third-callable addition — queued kernel-extract trigger (Rule of Three).** This story is the *second* precedent of "ProbeContext gains one optional callable per phase" (ADR-0002 + ADR-0004). When a Phase 3+ ADR adds a *third* optional callable, the rule-of-three trigger fires and the right shape becomes a `_ALLOWED_PROBE_CONTEXT_FIELDS_BY_ADR: Mapping[ADRId, frozenset[str]]` registry — Open/Closed at the file boundary (a new ADR amendment is a new entry, not an edit to the existing tuple). Phase 3 owns that decision. **Do NOT introduce the registry abstraction here** (Rule 2 — Simplicity First; three similar lines beats premature abstraction at N=2). Just leave the tuple flat, with both ADRs cited in the failure message.
- **The Phase 0 `forbidden-patterns` pre-commit is the structural backstop.** It catches `model_construct`, direct `subprocess.run`, and (per S1-11) `model_construct` under the new Phase 2 packages. It does NOT catch arbitrary edits to `base.py`; the contract-freeze snapshot is the defense there. AC-13 verifies the hook still passes after this story's edits.
- **The "fields-list tuple equality" assertion is strict (`==`), not subset.** Future contributors cannot silently drop `parsed_manifest`, `input_snapshot`, or `image_digest_resolver` either — the allowed-list is the exact tuple, and ordering matters (positional dataclass construction depends on it).
- **CODEOWNERS is operational, not blocking.** The `TODO(S5-02): CODEOWNERS entry required` comment at the top of `base.py` already records the linkage. AC-14 verifies it is preserved. The actual CODEOWNERS file is owned by S5-02 / S8-04; do not create it here (Rule 2).
- **Why no subprocess-based sentinel test.** The original draft prescribed a subprocess invocation of the regen script to validate rejection of a third field. The codebase's idiom (`test_probe_context_sentinel_fires_on_synthetic_third_field`) is an in-test synthetic dataclass mutation-killer — deterministic, no subprocess overhead, no flakiness, mirrors the failure-message contract directly. Per Rule 11 (match conventions), this story mirrors that pattern.
