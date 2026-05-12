# Story S1-09 — Per-probe raw-artifact budget (Gap 2)

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-08
**ADRs honored:** ADR-0002 (extended — see notes), ADR-0008

## Context

`phase-arch-design.md §"Gap analysis" Gap 2` names the missing budget: probes write raw artifacts to `.codegenie/context/raw/<probe>.json`, and a 50 MB lockfile that survives `safe_yaml.load`'s size cap becomes a 50 MB on-disk artifact. Phase 0 deferred per-probe RSS enforcement; this story lands the **raw-artifact** dimension: an additive `Probe.declared_raw_artifact_budget_mb: int = 5` class attribute, default 5 MB so every Phase 0 probe is unaffected. The coordinator tracks cumulative bytes written to `output_dir/raw/<probe>.json` and truncates with a marker at the boundary, emitting `probe.raw_artifact.truncated` with the original byte count.

`NodeManifestProbe` (S3-05) overrides the default to 25 MB to accommodate typical lockfiles; budgets > 50 MB require an ADR amendment. Phase 14 closes the RSS dimension separately.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" Gap 2` — full rationale, the additive class attribute, truncation-with-marker semantics, `probe.raw_artifact.truncated` event.
  - `../phase-arch-design.md §"Component design" #4` — `NodeManifestProbe.declared_raw_artifact_budget_mb = 25` (consumed in S3-05, not this story).
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `probe.raw_artifact.truncated` event with `original_bytes`, `budget_bytes`, `path`.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — Consequences §: the Gap 2 mechanism is potentially folded into ADR-0002. **Resolution** (per `phase-arch-design.md §"Open implementation questions"` #10): recommend amending ADR-0002 to document `declared_raw_artifact_budget_mb` alongside the two `ProbeContext` fields. Do the amendment in this story (one paragraph appended).
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — caps stay in-process; raw-artifact budget is the on-disk twin.
- **Source design:**
  - `../final-design.md §"Resource & cost profile"` — wall-clock and storage envelopes.
- **Existing code:**
  - `src/codegenie/probes/base.py` — `Probe` ABC; this story adds one class attribute.
  - `src/codegenie/coordinator/coordinator.py` — tracks cumulative bytes per probe; writes truncated marker.
  - `src/codegenie/errors.py` (S1-01) — no new error type needed; truncation is not an error.

## Goal

Add `Probe.declared_raw_artifact_budget_mb: int = 5` (additive class attribute, default preserved for Phase 0 probes); coordinator enforces the budget at write time, truncates with a `__truncated_at_budget__: true` marker JSON object, and emits `probe.raw_artifact.truncated` with the original byte count.

## Acceptance criteria

- [ ] `src/codegenie/probes/base.py` — `Probe` ABC gains `declared_raw_artifact_budget_mb: ClassVar[int] = 5` (additive; existing Phase 0 probes get the default for free).
- [ ] This class attribute is **NOT** added to the `ProbeContext` dataclass — it belongs on the `Probe` class, so it doesn't trigger the regen-script invariant from S1-06.
- [ ] Coordinator (`src/codegenie/coordinator/coordinator.py`) — the raw-artifact write step (Phase 0's writer or equivalent in `output/writer.py`) checks `len(bytes) > probe.declared_raw_artifact_budget_mb * 1_048_576` and, if exceeded, writes a truncated form with a marker:
  ```json
  {"__truncated_at_budget__": true, "original_bytes": <n>, "budget_bytes": <m>, "data": <first N bytes parsed as JSON, with truncation if not parseable>}
  ```
- [ ] Emits `probe.raw_artifact.truncated` structlog event with `probe`, `original_bytes`, `budget_bytes`, `path`.
- [ ] Phase 0 probes (`LanguageDetectionProbe`) are unaffected — their raw artifacts are tiny (≤ 10 KB).
- [ ] Unit test `tests/unit/coordinator/test_raw_artifact_budget.py`: default 5 MB enforcement on a stub probe; override to 25 MB on a stub subclass; truncation marker shape; `probe.raw_artifact.truncated` event emitted; no truncation when under budget.
- [ ] ADR-0002 amendment commit appends one paragraph under "Consequences" documenting `declared_raw_artifact_budget_mb`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Edit `src/codegenie/probes/base.py`:
   - Add `from typing import ClassVar` if not present.
   - On the `Probe` ABC: `declared_raw_artifact_budget_mb: ClassVar[int] = 5`.
2. Edit `src/codegenie/coordinator/coordinator.py` (or the writer at `src/codegenie/output/writer.py` — whichever holds the raw-artifact write per Phase 0's design):
   - Find the call site that writes `<output_dir>/raw/<probe.name>.json`.
   - Before writing, compute `budget_bytes = probe.declared_raw_artifact_budget_mb * 1_048_576`.
   - If `len(payload_bytes) > budget_bytes`: build the truncated wrapper object; serialize to JSON; emit event; write wrapper bytes.
   - Else: write payload as-is.
3. Write `tests/unit/coordinator/test_raw_artifact_budget.py` exercising the path with stub probes.
4. Append the ADR-0002 paragraph documenting `declared_raw_artifact_budget_mb`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/coordinator/test_raw_artifact_budget.py`.

```python
# tests/unit/coordinator/test_raw_artifact_budget.py
import json
from pathlib import Path

import pytest

from codegenie.probes.base import Probe
# import the truncation function under test — adjust to the actual coordinator/writer path
from codegenie.coordinator.coordinator import _write_raw_artifact_with_budget  # type: ignore[attr-defined]


class _StubProbe(Probe):
    name = "stub"
    declared_inputs = []
    # default 5 MB

class _BigProbe(Probe):
    name = "big"
    declared_inputs = []
    declared_raw_artifact_budget_mb = 25


def test_under_budget_writes_payload_verbatim(tmp_path):
    payload = json.dumps({"k": "v" * 100}).encode()
    out = tmp_path / "raw" / "stub.json"
    out.parent.mkdir()
    _write_raw_artifact_with_budget(_StubProbe(), payload, out)
    written = json.loads(out.read_text())
    assert written == {"k": "v" * 100}

def test_over_budget_truncates_with_marker(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    from codegenie.logging import configure_logging
    configure_logging(verbose=False)

    # build > 5 MB payload
    big = ("x" * 1024 * 1024 * 6).encode()  # 6 MB
    payload = b'{"data": "' + big + b'"}'
    out = tmp_path / "raw" / "stub.json"
    out.parent.mkdir()
    _write_raw_artifact_with_budget(_StubProbe(), payload, out)
    written = json.loads(out.read_text())
    assert written["__truncated_at_budget__"] is True
    assert written["original_bytes"] == len(payload)
    assert written["budget_bytes"] == 5 * 1_048_576
    assert "probe.raw_artifact.truncated" in capsys.readouterr().err

def test_override_to_25mb_does_not_truncate_at_5mb(tmp_path):
    payload = ("y" * 6 * 1_048_576).encode()  # 6 MB but BigProbe's budget is 25 MB
    out = tmp_path / "raw" / "big.json"
    out.parent.mkdir()
    _write_raw_artifact_with_budget(_BigProbe(), payload, out)
    # under 25 MB → payload written as-is (no marker)
    written_bytes = out.read_bytes()
    assert b"__truncated_at_budget__" not in written_bytes

def test_class_attribute_default_is_5():
    assert Probe.declared_raw_artifact_budget_mb == 5
    assert _StubProbe().declared_raw_artifact_budget_mb == 5
    assert _BigProbe().declared_raw_artifact_budget_mb == 25
```

Run; confirm `AttributeError` / `ImportError`. Commit as red.

### Green — minimal impl

- Add `declared_raw_artifact_budget_mb: ClassVar[int] = 5` to `Probe` ABC.
- Implement `_write_raw_artifact_with_budget(probe, payload_bytes, out_path)`:
  ```python
  budget = probe.declared_raw_artifact_budget_mb * 1_048_576
  if len(payload_bytes) <= budget:
      out_path.write_bytes(payload_bytes)
      return
  # Build truncated wrapper. Try to parse the under-budget prefix as JSON; if it fails, store as string.
  prefix = payload_bytes[:budget]
  try:
      truncated_data = json.loads(prefix)
  except json.JSONDecodeError:
      truncated_data = prefix.decode("utf-8", errors="replace")
  wrapper = {
      "__truncated_at_budget__": True,
      "original_bytes": len(payload_bytes),
      "budget_bytes": budget,
      "data": truncated_data,
  }
  out_path.write_text(json.dumps(wrapper))
  log.info("probe.raw_artifact.truncated", probe=probe.name,
           original_bytes=len(payload_bytes), budget_bytes=budget, path=str(out_path))
  ```
- Splice into the coordinator's existing raw-artifact write step.

### Refactor — clean up

- Function docstring naming Gap 2 + ADR-0002 Consequences amendment + ADR-0008 (on-disk twin of in-process caps).
- The wrapper's `"data"` field intentionally stores either parsed JSON (best-effort) or a UTF-8 string with replacement chars — keeps the artifact human-inspectable.
- Phase 0's writer chokepoint (if it goes through `OutputSanitizer.scrub`): confirm raw artifacts do **not** go through the sanitizer (they're the un-sanitized dump by design). Phase 0 docs should clarify this; if ambiguous, ask.
- Verify the wrapper survives the schema validator if applicable — raw artifacts have no sub-schema; only the `repo-context.yaml` envelope does.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base.py` | Add `declared_raw_artifact_budget_mb: ClassVar[int] = 5` to `Probe` ABC |
| `src/codegenie/coordinator/coordinator.py` (or `src/codegenie/output/writer.py`) | Splice `_write_raw_artifact_with_budget` into the raw-artifact write step |
| `tests/unit/coordinator/test_raw_artifact_budget.py` | New — 4 tests |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` | Append one paragraph to Consequences documenting `declared_raw_artifact_budget_mb` |

## Out of scope

- **`NodeManifestProbe` overriding to 25 MB** — S3-05 sets the class attribute; S3-06 tests the truncation at 30 MB → 25 MB.
- **RSS / wall-clock budgets** — Phase 14 owns process-level budgets. This story is on-disk only.
- **`probe.raw_artifact.truncated` event-name constant** — S1-10 registers it as `Final[str]`. This story uses the literal.
- **`output_dir/raw/` directory creation** — Phase 0 already handles `mkdir(parents=True)` for the writer; verify but do not change.

## Notes for the implementer

- **Class attribute, not instance attribute.** `ClassVar[int]` is correct because every subclass overrides at the class level (`declared_raw_artifact_budget_mb = 25`). If you typo it as a dataclass field, mypy will likely flag it; if it doesn't, the instance form would shadow the class form on construction.
- **The default 5 MB protects Phase 0 probes for free** — `LanguageDetectionProbe`'s raw artifact is ≤ 10 KB. No Phase 0 probe needs to override.
- **The truncation marker is JSON, not YAML**, because raw artifacts live as `.json` files (per Phase 0 conventions). The envelope `repo-context.yaml` is YAML; per-probe `raw/<probe>.json` is JSON.
- **Best-effort parse of the prefix** can throw on truncated UTF-8 inside a string mid-character. Use `decode(errors="replace")` for the string fallback. Don't try to be smart about JSON cleanliness — the wrapper is for debugging, not consumer-grade output.
- **Per Rule 12:** the truncation event is not optional. If the writer truncates silently without emitting the event, Phase 14's storage observability is blind. Assert the event in tests.
- **ADR-0002 amendment text** (copy verbatim into the file as the last paragraph of Consequences §):
  > **Amended (Phase 1, S1-09):** ADR-0002 also covers the additive class attribute `Probe.declared_raw_artifact_budget_mb: ClassVar[int] = 5` (Gap 2 resolution per `phase-arch-design.md`). Default 5 MB; `NodeManifestProbe` overrides to 25 MB. Coordinator enforces at raw-artifact write time, truncating with a `__truncated_at_budget__` marker and emitting `probe.raw_artifact.truncated`. Budgets > 50 MB require a further ADR amendment.
- **Path resolution:** if the raw artifact is written under `output_dir/raw/<probe>.json` but `<probe>.json` doesn't exist yet, `mkdir(parents=True, exist_ok=True)` first. Per Rule 12: do NOT swallow `FileExistsError` silently — but with `exist_ok=True` it's not raised.
- **`Probe` is the third Phase-0 file edited in Step 1.** S1-06 already amended `probes/base.py` for `ProbeContext`. This story makes a second, small, ClassVar-only change to the same file. The CODEOWNERS gating from S1-06 already covers it.
