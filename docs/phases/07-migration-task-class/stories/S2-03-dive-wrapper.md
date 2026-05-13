# Story S2-03 — `tools/dive.py` Pydantic wrapper with `extra="forbid"`

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** S
**Depends on:** S2-02
**ADRs honored:** ADR-P7-002 (`dive` on `ALLOWED_BINARIES`), ADR-0008 (`dive_efficiency` advisory-only — the wrapper produces facts; the signal collector decides advisory)

## Context

`dive --json` is the third tool wrapper Step 2 owns. Its job is small and load-bearing: parse `dive`'s upstream JSON into a strict Pydantic model so any future schema break (upstream `dive` minor-version drift, the well-known fragility of single-maintained tools) **fails loudly at the deserialization boundary** rather than corrupting downstream signal collectors. The strict-Pydantic `extra="forbid"` posture is the *whole point* of the wrapper — without it, an upstream rename of `efficiencyScore` → `efficiency_score` would silently zero out a strict-AND signal.

This wrapper is consumed at one place: the `dive` signal collector (S3-04, advisory only) and the `shell_presence` collector (S3-05, strict-AND projection of `final_layer_files`). One dive invocation, two signals (`phase-arch-design.md §Component 8`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 8. Signal collectors` (lines ~712–746) — describes one-dive-two-signals pattern and `DiveSignal` advisory posture.
  - `../phase-arch-design.md §Data model ›Internal` (`DiveResult`, `DiveFileEntry`) — the exact Pydantic shape this wrapper returns.
  - `../phase-arch-design.md §Adversarial tests` — "`dive --json` schema upstream-break adversarial (`extra="forbid"` defense)" — load-bearing for this story.
  - `../phase-arch-design.md §Edge cases #6` (legitimate Alpine→glibc growth — the wrapper emits the size ratio; advisory decision is downstream).
- **Phase ADRs:**
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — `dive` newly on `ALLOWED_BINARIES`.
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — informs *what the wrapper does not do* (it does not decide `passed`; that's the collector's job).
- **High-level impl:**
  - `../High-level-impl.md §Step 2` (lines 60–82) — features delivered, including `tests/unit/tools/test_dive.py`.

## Goal

`from codegenie.tools.dive import run_dive` returns a `DiveResult` Pydantic model whose `extra="forbid"` raises `pydantic.ValidationError` on any unexpected field in `dive --json`'s output — the upstream-schema-drift early warning system.

## Acceptance criteria

- [ ] `src/codegenie/tools/dive.py` exports `run_dive(image_digest: str, *, timeout_s: int = 60) -> DiveResult`, plus the Pydantic models `DiveResult` and `DiveFileEntry`.
- [ ] `DiveResult` and `DiveFileEntry` match `phase-arch-design.md §Data model ›Internal` exactly: `DiveResult` has `image_digest`, `final_size_bytes`, `efficiency_pct`, `wasted_bytes`, `layer_count`, `final_layer_files: list[DiveFileEntry]`, `size_ratio_post_pre: float | None`. Both have `model_config = ConfigDict(extra="forbid", frozen=True)`.
- [ ] An unexpected field in the JSON payload raises `pydantic.ValidationError` (not silently dropped) — this is the entire point of the wrapper. Test fixture seeds a known-good payload + adds a single extra key.
- [ ] A `dive` subprocess non-zero exit raises `DiveInvocationFailed` with stderr captured (not logged).
- [ ] The wrapper does **not** set `passed` on anything — `passed` lives on `DiveSignal` (S3-04). The wrapper is facts-only (Rule 9).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/tools/test_dive.py` all pass on the touched files.
- [ ] Fence-CI confirms no `anthropic|chromadb|sentence-transformers` imports.

## Implementation outline

1. Write the failing tests in `tests/unit/tools/test_dive.py` — happy path + schema-drift detection + subprocess failure. Commit.
2. Define `DiveFileEntry` and `DiveResult` Pydantic models. `extra="forbid", frozen=True`.
3. Implement `run_dive(image_digest, timeout_s=60)`:
   - Subprocess `dive --json <image_digest>` with `timeout_s` wall-clock and `capture_output=True`.
   - Non-zero exit → `DiveInvocationFailed(stderr=..., exit_code=...)`.
   - Parse stdout as JSON → `DiveResult.model_validate_json(stdout)`.
   - On `pydantic.ValidationError`, re-raise (do not swallow). The whole point.
4. Compute `size_ratio_post_pre` — wrapper accepts an optional `pre_size_bytes: int | None` kwarg; when `None`, `size_ratio_post_pre = None` (honest absence).
5. Add `tools/digests.yaml` entry for `sandbox.dive` (S2-07 finalizes the additive set).
6. Refactor: docstrings, type hints, structlog event, fence-CI clean.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/tools/test_dive.py`

```python
# tests/unit/tools/test_dive.py
import json
import subprocess
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from codegenie.tools.dive import (
    run_dive,
    DiveResult,
    DiveFileEntry,
    DiveInvocationFailed,
)

_GOOD_PAYLOAD = {
    "image": {"sizeBytes": 100_000_000, "efficiencyScore": 0.97, "wastedBytes": 2_000_000, "layers": 4},
    "layer": [
        {"index": 3, "files": [
            {"path": "/usr/bin/node", "sizeBytes": 90_000_000},
            {"path": "/etc/passwd", "sizeBytes": 200},
        ]}
    ],
}


def _fake_run_ok(stdout_obj):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(stdout_obj), stderr="",
    )


def test_run_dive_parses_known_good_payload():
    """Happy path: well-formed dive --json maps into DiveResult."""
    with patch("subprocess.run", return_value=_fake_run_ok(_GOOD_PAYLOAD)):
        result = run_dive(image_digest="sha256:abc")
    assert isinstance(result, DiveResult)
    assert result.image_digest == "sha256:abc"
    assert result.final_size_bytes == 100_000_000
    assert result.efficiency_pct == 0.97
    assert result.layer_count == 4
    assert any(f.path == "/usr/bin/node" for f in result.final_layer_files)


def test_run_dive_rejects_unexpected_field_loudly():
    """Schema drift defense: extra key → pydantic.ValidationError, never silent."""
    poisoned = dict(_GOOD_PAYLOAD)
    poisoned["new_upstream_field"] = "this was added in a minor version bump"
    with patch("subprocess.run", return_value=_fake_run_ok(poisoned)):
        with pytest.raises(ValidationError):
            run_dive(image_digest="sha256:abc")


def test_run_dive_propagates_subprocess_failure():
    """dive non-zero exit → DiveInvocationFailed with stderr captured."""
    fake_cp = subprocess.CompletedProcess(
        args=[], returncode=2, stdout="", stderr="dive: image not found\n",
    )
    with patch("subprocess.run", return_value=fake_cp):
        with pytest.raises(DiveInvocationFailed) as exc:
            run_dive(image_digest="sha256:missing")
    assert exc.value.exit_code == 2
    assert "image not found" in exc.value.stderr


def test_run_dive_size_ratio_none_when_pre_size_missing():
    """Honest absence: pre_size_bytes=None → size_ratio_post_pre is None."""
    with patch("subprocess.run", return_value=_fake_run_ok(_GOOD_PAYLOAD)):
        result = run_dive(image_digest="sha256:abc", pre_size_bytes=None)
    assert result.size_ratio_post_pre is None


def test_run_dive_does_not_decide_passed():
    """Wrapper is facts-only: no `passed` field appears on DiveResult (Rule 9)."""
    fields = set(DiveResult.model_fields)
    assert "passed" not in fields
```

The tests fail with `ImportError` initially. Commit.

### Green — make it pass

- Add `src/codegenie/tools/dive.py` with `DiveResult`, `DiveFileEntry`, `DiveInvocationFailed`, and `run_dive()`.
- The Pydantic-validate step is one call — `DiveResult.model_validate(payload_dict)` after `json.loads(stdout)` — and the `extra="forbid"` ConfigDict does all the schema-drift work.
- `image_digest` is **not** parsed from dive output (dive's `image.name` is unstable); it's the caller's input, passed through.
- Map upstream JSON keys to Pydantic field names via `Field(alias="efficiencyScore")` or a custom validator — whichever stays inside the strict envelope.

### Refactor — clean up

- Docstrings; PEP 604 unions; `Literal` where applicable.
- `structlog.bind(...)` event `dive.ok` on success and `dive.failed` on exception; do not log stdout/stderr at INFO (Phase 7 harness rule — raw subprocess output goes to `raw/` artifact files only, not the logger).
- Confirm fence-CI passes; mypy strict.
- Confirm `phase-arch-design.md §Adversarial tests` "`dive --json` schema upstream-break adversarial" is exercised by the schema-drift test.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tools/dive.py` | New — wrapper, models, exception. |
| `tests/unit/tools/test_dive.py` | New — red tests covering happy path + schema-drift + subprocess failure. |
| `tools/digests.yaml` | Record `sandbox.dive` pinned digest (S2-07 finalizes). |

## Out of scope

- **`DiveSignal` advisory collector** — S3-04 owns the `passed=True`-always advisory decision per ADR-0008.
- **`shell_presence` projection on `final_layer_files`** — S3-05.
- **Caching dive output** — handled by Phase 5 sandbox / collector layer; the wrapper is stateless.
- **Dive performance optimization** — its 5–15 s (Mac) / 10–25 s (Linux) cost lives in the strict-AND budget envelope per §Component 8; no work here.
- **`dive` binary digest pin** — finalized in S2-07's `tools/digests.yaml` additive set.

## Notes for the implementer

- The `extra="forbid"` discipline is the entire reason this wrapper exists. Any temptation to relax it ("`dive` 0.13 added one harmless field; let me just allow it") is a Rule 11 / Rule 12 violation — surface the drift, file an ADR, regenerate the contract-surface snapshot (S1-07 / S2-06), don't widen silently.
- Map upstream JSON to Pydantic via aliases (`Field(alias="efficiencyScore")`); keep the public Pydantic field names snake_case to match the rest of the codebase (Rule 11 — match conventions).
- This wrapper **must not** call the dive sub-tool's "interactive" mode. `--json` only. Do not invoke `dive build`; the build step is `tools/buildkit.py`'s job.
- `phase-arch-design.md §Risks #3` — toolchain pinning drift across CI runners. Pin the `dive` binary digest in `tools/digests.yaml#sandbox.dive` (S2-07 lands the entry; this story records the requirement). Do not rely on the runner's pre-baked `dive`.
- Do not parse `dive`'s human-readable output for fallback. If `--json` fails, fail loudly.
- The `pre_size_bytes` kwarg is the seam where `size_ratio_post_pre` gets populated; the caller (signal collector) supplies it from `imagetools_inspect` (S2-02). Honest `None` propagates when unknown — `dive_summary` in `MigrationReport` will show "ratio: unknown" rather than 0.0.
