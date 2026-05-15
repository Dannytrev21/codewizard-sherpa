# Story S5-01 — Parser-cap adversarial corpus: billion-laughs, JSON bombs, oversized lockfile

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Done — 2026-05-15 (see [_attempts/S5-01.md](_attempts/S5-01.md))
**Validated:** 2026-05-14 (HARDENED — see [_validation/S5-01-adversarial-parser-caps.md](_validation/S5-01-adversarial-parser-caps.md))
**Effort:** M
**Depends on:** S2-05, S3-06 (the second pulls in `NodeManifestProbe` for the gather-level assertions)
**ADRs honored:** ADR-0007 (typed-exception IDs land in `errors[]`, not `warnings[]`), ADR-0008 (in-process parse caps, no per-probe sandbox), ADR-0009 (no new C-extension parser dependencies)

## Validation notes (2026-05-14, HARDENED)

Six block-tier and four harden-tier weaknesses fixed. The two most load-bearing:

1. **`warnings` → `errors`.** ADR-0007 + node_manifest.py:413 + language_detection.py:454-458 all place typed-exception-derived IDs on `errors: list[str]`; `warnings: list[str]` is the soft-degrade vocabulary. Original AC-1 / AC-2 / AC-4 mistakenly asserted `warnings`. Test-against-correct-impl would have failed; an executor "fixing" the test by appending the ID to `warnings` would land an ADR-0007 violation.
2. **`DepthCapExceeded` probe-handler retrofit (new AC-12).** Neither `LanguageDetectionProbe._PKG_JSON_FAILURE` nor `NodeManifestProbe._read_package_json` catches `DepthCapExceeded` — only `SizeCapExceeded`, `SymlinkRefusedError`, `MalformedJSONError`. Without a two-line edit per probe, AC-2's `package_json.depth_cap_exceeded` ID never lands on the slice's `errors`. The retrofit is surgical (one entry in the failure-mapping registry per probe; the existing compile-time ADR-0007 pattern check validates the new ID).

Other surfaces: fictional `run_gather` fixture replaced with `tests/adv/_helpers.py::invoke_gather`; structlog payload assertion broadened to pin all four emitted fields (`parser_kind`, `cap_kind ∈ {"size","depth"}`, `cap`, `path`); pre-parse canary added for AC-4 (oversized YAML lockfile) symmetric to AC-3 (huge_string JSON); closed-world `errors == [<exact-ID>]` assertions on gather-level tests; disk-space guard for the 600 MB fixture; helper extractions promoted from "optional" to "required" (rule-of-three met across the adversarial-test family).

Design-pattern lifts elevated to ACs: registry-driven ID construction (AC-9), structlog-event-assertion helper (AC-8), pure-function fixture builders (AC-16). Lifts kept as Notes-only: `Literal["size","depth"]` / StrEnum for `cap_kind` (Phase 2 polish), composition-over-inheritance for adversarial-test base (Rule 2 governs at four siblings), `WarningId` Annotated-type adoption (the runtime pattern check is sufficient defense today).

AC count: 8 → 18 (Mechanism / Probe-retrofit / Test-marker + ergonomics / CI walltime / Hygiene).

## Context

This is one of the three load-bearing adversarial-test stories that prove the Step 1 parsers (`safe_json`, `safe_yaml`, `jsonc`) actually do what `phase-arch-design.md §"Goals"` claim: "zero successful parse-driven RCE or OOM against an adversarial fixture corpus (≥ 20 hostile inputs)." Step 5 splits the ten adversarial tests into three thematically grouped stories. S5-01 owns the **size + depth + structural-cap** family — the four tests where the defense is a hard byte / depth budget inside `parsers/`.

These tests are CI-gating (`phase-arch-design.md §"Testing strategy" → "Adversarial tests (CI-gating)"`). A regression here is a P0 defect: a parser-cap failure means a hostile repo can OOM or hang the gather, and the entire Phase 1 threat closure (ADR-0008's "~95% threat closure at ~0 ms overhead") collapses to "best effort."

The risk specific to this story (`High-level-impl.md §"Step 5 — Risks"`): adversarial tests can mask false-positive-green if the cap-exceeded path is reached via a different mechanism than intended (e.g. the test exercises `O_NOFOLLOW` when it should exercise `DepthCapExceeded`). Assert the **specific** typed exception, not just exit code 0 + `confidence: low`. The 600 MB JSON bomb is large for CI disk and walltime; generate it at test setup time, never check it in.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Adversarial tests"` rows 1, 2, 3, 10 — the four tests this story lands.
  - `../phase-arch-design.md §"Edge cases"` rows 1, 2 — the in-system behavior these tests assert.
  - `../phase-arch-design.md §"CI gates"` — `<` 30 s p95 combined for all ten adversarial tests; this story owns four of them, target a fair share.
  - `../phase-arch-design.md §"Goals"` #5 — "adversarial robustness" wording.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — every assertion in this story is a downstream test of ADR-0008. The "specific typed exception" requirement is the way the ADR makes itself falsifiable.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — the test fixtures must not require adding new parser deps to generate (stdlib `json` / `yaml.CSafeLoader` only at fixture-generation time).
- **Source design:**
  - `../final-design.md §"Failure modes & recovery"` rows for "YAML billion-laughs", "JSON bomb in package.json", "Lockfile exceeds 50 MB cap".
  - `../High-level-impl.md §"Step 5"` adversarial-test list items 1, 2, 3, 10.
- **Existing code (lands in Step 1 — must be on disk before this story starts):**
  - `src/codegenie/parsers/safe_json.py` (S1-02).
  - `src/codegenie/parsers/safe_yaml.py` (S1-03).
  - `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded` (S1-01).
- **Style reference:** `../../00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md` (story shape and TDD plan structure).

## Goal

Four adversarial tests under `tests/adv/` exist and pass, each asserting the **specific** typed parser-cap exception against a hostile fixture, and `pytest tests/adv/` completes in under 15 s wall-clock locally.

## Acceptance criteria

ACs are organised into five named groups. Every AC is individually verifiable by reading one file or running one command.

### Mechanism (parser-level invariants — direct calls, no CLI)

- [ ] **AC-1 (test #1, parser-level half).** `tests/adv/test_yaml_billion_laughs.py` builds (at test-fixture-setup time inside `tmp_path`, never checked in) a `pnpm-lock.yaml` whose top-level value is a depth-200 nested-list shape and asserts `safe_yaml.load(path, max_bytes=1_000_000)` raises `codegenie.errors.DepthCapExceeded`; asserts `str(exc)` contains the absolute path of the offending file (markers-only contract per S1-01: no instance attributes — message string carries the detail).
- [ ] **AC-2 (test #2, parser-level half).** `tests/adv/test_json_bomb_deep_nesting.py` builds a `package.json` whose top-level value is a 10,000-keys-deep `{"a": {"a": {"a": ...}}}` mapping (constructed via a Python loop in memory + `json.dumps` + `Path.write_bytes`; under 5 MB on disk; no lockfile in fixture) and asserts `safe_json.load(path, max_bytes=5_000_000)` raises `codegenie.errors.DepthCapExceeded`; asserts the file size is under the 5 MB `safe_json` size cap (proves depth — not size — is what fired).
- [ ] **AC-3 (test #3, parser-level only).** `tests/adv/test_json_bomb_huge_string.py` writes a single-string-value `package.json` of 600 MB to `tmp_path` by streaming (`open("wb")` then `write(b"a" * (1024*1024))` × 600, wrapped in a `{"name": "..."}` skeleton). The test patches `safe_json.json.loads` to raise a sentinel `RuntimeError("json.loads must not be reached")`, asserts `pytest.raises(SizeCapExceeded)` from `safe_json.load(path, max_bytes=5_000_000)`. The sentinel is the canary — if a regression breaks the pre-parse size check, the test fails with `RuntimeError` instead of `SizeCapExceeded`. Additionally instruments `os.read` to assert it is **not** called when the size cap fires (mirrors `tests/unit/parsers/test_safe_json.py::test_size_cap_raises_before_read`).
- [ ] **AC-4 (test #4, parser-level half).** `tests/adv/test_oversized_lockfile.py` writes a 60 MB `pnpm-lock.yaml` to `tmp_path` (60 × `b"# pad\n" * (1024*1024 // 6)` chunks, or equivalent streaming write). Patches `yaml.load` (the function `safe_yaml._parse_one` calls) to `side_effect=RuntimeError("yaml.load must not be reached")`. Asserts `pytest.raises(SizeCapExceeded)` from `safe_yaml.load(path, max_bytes=50_000_000)`. The sentinel is the canary, symmetric to AC-3.

### Probe-retrofit (Phase-1 follow-ups surfaced by this story)

- [ ] **AC-12 (`DepthCapExceeded` probe-handler retrofit).** Both `LanguageDetectionProbe._PKG_JSON_FAILURE` (lang_det.py:188-194) and `NodeManifestProbe._PKG_JSON_FAILURE` (node_manifest.py:275-279) gain an entry `DepthCapExceeded → ("package_json.depth_cap_exceeded", "low")`. Both probes' `_read_package_json` (lang_det.py:454; node_manifest.py:348) catch-tuples gain `DepthCapExceeded`. Each probe's `_ERRORS` frozenset (or equivalent) gains `"package_json.depth_cap_exceeded"`. The existing compile-time ADR-0007 pattern check (`_ID_PATTERN.match`) automatically validates the new ID. No other behavior changes; surgical additions only (Rule 3). Two new unit tests (one per probe) cover the new branch in `tests/unit/probes/`.

### Gather-level assertions (CLI-driven, end-to-end)

- [ ] **AC-1b (test #1, gather-level half).** Tests #1 also synthesizes a minimal Node repo around the hostile lockfile (`package.json` + `pnpm-lock.yaml` in `tmp_path`); calls `invoke_gather(tmp_path)` (the AC-7 helper); asserts `result.exit_code == 0`; asserts `result.context["probes"]["node_manifest"]["confidence"] == "low"`; asserts `result.context["probes"]["node_manifest"]["errors"] == [expected_lockfile_error_id("pnpm", DepthCapExceeded)]` (closed-world equality — sole degradation cause; the AC-9 helper construction guards against ID drift; the human-readable expected value is `"pnpm_lock.depth_cap_exceeded"` per ADR-0007 + `phase-arch-design.md §Edge cases` row 1). Asserts `"warnings"` field on the slice does NOT contain any cap-exceeded ID (typed-exception IDs go to `errors[]` per ADR-0007).
- [ ] **AC-2b (test #2, gather-level half — depends on AC-12).** Tests #2 also calls `invoke_gather(tmp_path)`; asserts exit 0; asserts both slices carry the post-retrofit ID:
  - `result.context["probes"]["language_detection"]["confidence"] == "low"` AND `["errors"] == ["package_json.depth_cap_exceeded"]`.
  - `result.context["probes"]["node_manifest"]["confidence"] == "low"` AND `["errors"] == ["package_json.depth_cap_exceeded"]`.
  Closed-world assertions — no spurious other IDs. Test fails before the AC-12 retrofit lands (canary).
- [ ] **AC-4b (test #4, gather-level half).** Test #4 also invokes the gather around a fixture containing the oversized lockfile + a minimal `package.json`; asserts exit 0; asserts `node_manifest.confidence == "low"` AND `errors == [expected_lockfile_error_id("pnpm", SizeCapExceeded)]` (`"pnpm_lock.size_cap_exceeded"`).

### Test-marker + ergonomics (helpers, registration)

- [ ] **AC-5 (`adv` marker registration).** `pyproject.toml` `[tool.pytest.ini_options].markers` gains the entry `"adv: adversarial-fixture corpus tests (Phase 1 §S5-01/02/03)"`. The story's PR registers the marker (Phase 0 ships only `bench` — pyproject.toml:183-185 — the original "if Phase 0 already registered it, skip" hedge does not apply). All four tests carry `@pytest.mark.adv` at function scope. `pytest -m adv` selects exactly the four (run-and-count assertion in `tests/unit/test_pytest_markers.py` extended with this expectation, or one-line snapshot in story's TDD plan).
- [ ] **AC-6 (`tmp_path` discipline).** All four test functions take `tmp_path: Path` and synthesize every byte under it; no fixture writes outside `tmp_path`; no synthesized file is left after pytest tears down `tmp_path`. (Static-grep assertion: `grep -rn "tests/fixtures/\|tests/adv/data/" tests/adv/test_yaml_billion_laughs.py tests/adv/test_json_bomb_*.py tests/adv/test_oversized_lockfile.py` returns nothing.)
- [ ] **AC-7 (`invoke_gather` helper).** `tests/adv/_helpers.py::invoke_gather(repo: Path) -> click.testing.Result` exists. Single seam for CLI invocation across the adversarial corpus. Implementation lifts the `_invoke_gather` pattern from `tests/smoke/test_cli_end_to_end.py:87` and additionally parses `repo / ".codegenie/context/repo-context.yaml"` into `result.context: dict` for assertion ergonomics (returns a thin `@dataclass GatherResult(exit_code, output, context)` if Click's `Result` doesn't accommodate). Used by tests #1, #2, #4 of this story and by every adversarial test in S5-02 / S5-03 going forward.
- [ ] **AC-8 (`assert_parser_cap_event` helper).** `tests/adv/_helpers.py::assert_parser_cap_event(logs: list[dict], *, parser_kind: str, cap_kind: Literal["size", "depth"], cap: int, path: Path) -> None` exists. Filters `logs` for `event == "probe.parser.cap_exceeded"`, asserts exactly one match, asserts the four structured fields equal the keyword args. Used by AC-13 / AC-14 (and downstream stories).
- [ ] **AC-9 (`expected_lockfile_error_id` helper).** `tests/adv/_helpers.py::expected_lockfile_error_id(parser_kind: ParserKind, exc_type: type[BaseException]) -> str` exists; constructs `f"{_ERROR_PREFIX_BY_KIND[parser_kind]}.{_ERROR_SUFFIX_BY_EXC[exc_type]}"` by importing the registries directly from `codegenie.probes.node_manifest` (single source of truth — drift guard). Tests retain one explicit `# expected: pnpm_lock.depth_cap_exceeded` comment per usage as the human-readable anchor.

### Cap-event payload pinning (mutation resistance)

- [ ] **AC-13 (size-cap event payload).** A dedicated parser-level test (e.g., consolidated under `tests/adv/test_oversized_lockfile.py::test_size_cap_event_payload_complete`) asserts that on `safe_yaml.load`-caught `SizeCapExceeded`, `structlog.testing.capture_logs()` records exactly one event with `event == "probe.parser.cap_exceeded"` AND `parser_kind == "safe_yaml"` AND `cap_kind == "size"` AND `cap == max_bytes` (the int passed) AND `path == str(absolute_path)`. Same assertion at `safe_json.load` boundary (`parser_kind == "safe_json"`). Uses the AC-8 helper.
- [ ] **AC-14 (depth-cap event payload).** Symmetric to AC-13 for `DepthCapExceeded` — `cap_kind == "depth"` AND `cap == max_depth`. The literal `"size"` / `"depth"` vocabulary is locked in by `parsers/_io.py:47` (`_CAP_KIND_SIZE: Final[str] = "size"`) and `parsers/_depth.py:38` (`_CAP_KIND_DEPTH: Final[str] = "depth"`); per S1-03 validation precedent (`_validation/S1-03-safe-yaml-parser.md` §AC-14 footnote) — the story's earlier ambiguity around `"bytes"` is resolved against the implementation.

### CI walltime + Hygiene

- [ ] **AC-10 (CI walltime budget).** `pytest -m adv tests/adv/test_yaml_billion_laughs.py tests/adv/test_json_bomb_deep_nesting.py tests/adv/test_json_bomb_huge_string.py tests/adv/test_oversized_lockfile.py` completes in under 15 s wall-clock on a developer machine; the slowest single test (test #3, the 600 MB write) caps under 10 s. Measure locally with `time pytest -m adv ...`; record peak in PR body.
- [ ] **AC-11 (per-file module docstring).** Each of the four new test files has a one-line module docstring referencing `phase-arch-design.md §"Adversarial tests"` row N (1, 2, 3, 10 respectively) and the specific structural defense it pins. (Helps future contributors find the why.)
- [ ] **AC-15 (disk-space guard for 600 MB fixture).** Test #3 calls `shutil.disk_usage(tmp_path)` before the streaming write; `pytest.skip(...)` with a clear message if free bytes < 1 GiB. Avoids `OSError(ENOSPC)` failing for the wrong cause on constrained CI runners.
- [ ] **AC-16 (functional-core fixture builders).** The three small-fixture builders are pure functions (bytes-in / bytes-out, no I/O):
  - `_billion_laughs_yaml(depth: int) -> bytes` — already pure in the original TDD-plan example; preserved.
  - `_deeply_nested_package_json(depth: int) -> bytes` — new pure builder for test #2.
  - The 600 MB writer is necessarily an imperative shell (cannot fit in memory). It is a single `def _write_huge_string_package_json(path: Path, *, megabytes: int) -> None` taking explicit keyword args; the `int` argument is the only "data" surface. Same imperative-shell carve-out applies to `_write_padded_lockfile(path: Path, *, megabytes: int) -> None` for test #4. Each pure builder has a one-line unit test in `tests/adv/test__helpers.py` asserting determinism (same input → same bytes).
- [ ] **AC-17 (`mypy --strict` clean).** `tests/adv/_helpers.py` and the four new test modules type-check under the project's `mypy --strict` config (no `Any`, no untyped functions, explicit `Path` / `Literal` types at every boundary). The `assert_parser_cap_event` helper takes `Literal["size", "depth"]` for `cap_kind` — type-level guard against `cap_kind="bytes"` regression.
- [ ] **AC-18 (skip-on-windows for `O_NOFOLLOW`-dependent tests).** Each of the four test functions carries `@pytest.mark.skipif(sys.platform == "win32", reason="adversarial parser caps require POSIX O_NOFOLLOW semantics")`. Mirrors `tests/adv/test_symlink_escape.py:34`. Notes-only consequence: Windows CI never runs these tests; the structural defense is platform-conditional in Phase 1 (consistent with ADR-0008 platform scope).

## Implementation outline

Order: helpers + marker first (everything depends on them), then probe-retrofit (AC-12 unblocks AC-2b), then the four tests in fixture-size order (smallest → largest).

1. **Register the `adv` pytest marker** in `pyproject.toml` `[tool.pytest.ini_options].markers` — single line: `"adv: adversarial-fixture corpus tests (Phase 1 §S5-01/02/03)"`. (`bench` is the only existing entry per pyproject.toml:183-185; no idempotency check needed.)
2. **Create `tests/adv/_helpers.py`** with three pure-function helpers and one I/O wrapper, exhaustively typed under `mypy --strict`:
   - `invoke_gather(repo: Path) -> GatherResult` — lifts `_invoke_gather` from `tests/smoke/test_cli_end_to_end.py:87`, additionally parses `repo/.codegenie/context/repo-context.yaml` so callers can write `result.context["probes"][probe_name][...]` directly. Returns a thin `@dataclass GatherResult(exit_code: int, output: str, context: dict)`.
   - `assert_parser_cap_event(logs: list[dict], *, parser_kind: str, cap_kind: Literal["size", "depth"], cap: int, path: Path) -> None` — exactly-one-event filter on `event == "probe.parser.cap_exceeded"`; explicit-keyword payload pin.
   - `expected_lockfile_error_id(parser_kind: ParserKind, exc_type: type[BaseException]) -> str` — imports `_ERROR_PREFIX_BY_KIND` and `_ERROR_SUFFIX_BY_EXC` from `codegenie.probes.node_manifest`; constructs the ID via the registry (drift guard against future vocabulary changes).
   - One pytest fixture (or top-level conftest entry, no autouse) is **NOT** added — the existing `tests/adv/conftest.py::_disable_cli_configure_logging` autouse already binds for everything under `tests/adv/`.
3. **AC-12 probe retrofit** (two-line edits per probe):
   - `src/codegenie/probes/language_detection.py`: add `DepthCapExceeded` to the import list; add `DepthCapExceeded: ("package_json.depth_cap_exceeded", "low")` to `_PKG_JSON_FAILURE` (lang_det.py:188-194); add `"package_json.depth_cap_exceeded"` to `_ERRORS` (lang_det.py:176-181); add `DepthCapExceeded` to the catch-tuple at lang_det.py:454.
   - `src/codegenie/probes/node_manifest.py`: add `DepthCapExceeded: "package_json.depth_cap_exceeded"` to `_PKG_JSON_FAILURE` (node_manifest.py:275-279); add `DepthCapExceeded` to the catch-tuple at node_manifest.py:348.
   - `tests/unit/probes/test_language_detection_probe.py` and `tests/unit/probes/test_node_manifest_probe.py`: one new test each, asserting a deeply-nested `package.json` produces `errors == ["package_json.depth_cap_exceeded"]` and demoted confidence. The compile-time `_ID_PATTERN.match` assertion in each probe automatically validates the new ID.
4. **`tests/adv/test_yaml_billion_laughs.py`** (test #1):
   - Pure builder `_billion_laughs_yaml(depth: int) -> bytes` returns a depth-N nested-list shape (e.g., `[[[...]]]`) — the depth-walker target. (NOT `*alias` references — that's S1-03's `test_safe_yaml.py::test_depth_walker_dedupes_alias_targets_no_amplification` territory; this story exercises the depth ceiling, not alias amplification.)
   - Two test functions:
     - `test_billion_laughs_pnpm_lock_raises_depth_cap` — parser-level (AC-1).
     - `test_billion_laughs_under_gather_exits_zero_with_low_confidence` — CLI-level via `invoke_gather` (AC-1b).
5. **`tests/adv/test_json_bomb_deep_nesting.py`** (test #2):
   - Pure builder `_deeply_nested_package_json(depth: int) -> bytes` → 10,000-deep `"a": {"a": ...}` mapping. Asserts file size < 5 MB (proves depth fired, not size).
   - Two test functions: parser-level (AC-2) + CLI-level (AC-2b, depends on AC-12).
6. **`tests/adv/test_json_bomb_huge_string.py`** (test #3 — parser-only, no CLI half):
   - I/O writer `_write_huge_string_package_json(path: Path, *, megabytes: int) -> None` streams in 1 MB chunks.
   - `shutil.disk_usage(tmp_path).free < 1 << 30` → `pytest.skip(...)` (AC-15).
   - Patches `safe_json.json.loads` to raise sentinel `RuntimeError`; instruments `os.read` to assert non-call; `pytest.raises(SizeCapExceeded)` (AC-3).
7. **`tests/adv/test_oversized_lockfile.py`** (test #4):
   - I/O writer `_write_padded_lockfile(path: Path, *, megabytes: int) -> None` streams `b"# pad\n"`-style padding to 60 MB.
   - Patches `yaml.load` (the symbol `safe_yaml._parse_one` calls — `unittest.mock.patch.object(safe_yaml, "yaml")` or `patch("yaml.load")` depending on import shape; verify which works against the actual import and pin in the test).
   - Two test functions: parser-level (AC-4, with sentinel canary) + CLI-level (AC-4b, closed-world `errors == ["pnpm_lock.size_cap_exceeded"]`).
8. **Cap-event payload pinning tests (AC-13 / AC-14).** Co-locate in `tests/adv/test_oversized_lockfile.py` (size case) and `tests/adv/test_json_bomb_deep_nesting.py` (depth case), or under a dedicated `tests/adv/test_parser_cap_events.py` for cohesion. Use the AC-8 helper.
9. **Module docstrings (AC-11)** and `mypy --strict` discipline (AC-17): every new file gets a one-line `phase-arch-design.md §Adversarial tests` row pointer; every function carries an explicit type signature.

## TDD plan — red / green / refactor

### Red — write the failing test first

Order: helpers + marker first, then probe-retrofit (AC-12) — the AC-2b test will fail without it; that failure is the load-bearing red, signaling the retrofit need to the executor. Then the four hostile-fixture tests in fixture-size order (smallest → largest). One file per test; commit each red separately.

```python
# tests/adv/_helpers.py  (NEW — required, not optional)
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml as _yaml
from click.testing import CliRunner, Result

from codegenie.cli import cli
from codegenie.probes.node_manifest import (
    _ERROR_PREFIX_BY_KIND,
    _ERROR_SUFFIX_BY_EXC,
    ParserKind,
)


@dataclass(frozen=True)
class GatherResult:
    """Thin envelope around CliRunner.Result with parsed repo-context."""
    exit_code: int
    output: str
    context: dict


def invoke_gather(repo: Path) -> GatherResult:
    res: Result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    ctx_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    parsed = _yaml.safe_load(ctx_path.read_text()) if ctx_path.exists() else {}
    return GatherResult(exit_code=res.exit_code, output=res.output, context=parsed)


def assert_parser_cap_event(
    logs: list[dict], *,
    parser_kind: str,
    cap_kind: Literal["size", "depth"],
    cap: int,
    path: Path,
) -> None:
    matches = [e for e in logs if e.get("event") == "probe.parser.cap_exceeded"]
    assert len(matches) == 1, f"expected exactly 1 cap-exceeded event, got {len(matches)}: {matches!r}"
    ev = matches[0]
    assert ev["parser_kind"] == parser_kind, ev
    assert ev["cap_kind"] == cap_kind, ev
    assert ev["cap"] == cap, ev
    assert ev["path"] == str(path), ev


def expected_lockfile_error_id(parser_kind: ParserKind, exc_type: type[BaseException]) -> str:
    return f"{_ERROR_PREFIX_BY_KIND[parser_kind]}.{_ERROR_SUFFIX_BY_EXC[exc_type]}"
```

```python
# tests/adv/test_yaml_billion_laughs.py
"""Adversarial: billion-laughs-shaped pnpm-lock.yaml triggers DepthCapExceeded.

Pins phase-arch-design.md §"Adversarial tests" row 1 + ADR-0008 in-process
depth cap. The depth-walker is the load-bearing defense (CSafeLoader has no
native depth limit). NOTE: alias-amplification (`*alias` references) is NOT
exercised here — it's S1-03's `test_safe_yaml.py::test_depth_walker_dedupes_alias_targets_no_amplification`.
This test exercises depth ceiling only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from codegenie.errors import DepthCapExceeded
from codegenie.parsers import safe_yaml
from tests.adv._helpers import expected_lockfile_error_id, invoke_gather


def _billion_laughs_yaml(depth: int) -> bytes:
    """Pure builder: depth-N nested-list shape encoded as YAML."""
    return f"lockfileVersion: '6.0'\nanchors: {'[' * depth}1{']' * depth}\n".encode()


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="O_NOFOLLOW required (POSIX)")
def test_billion_laughs_pnpm_lock_raises_depth_cap(tmp_path: Path) -> None:
    f = tmp_path / "pnpm-lock.yaml"
    f.write_bytes(_billion_laughs_yaml(depth=200))
    with pytest.raises(DepthCapExceeded) as exc:
        safe_yaml.load(f, max_bytes=1_000_000, max_depth=64)
    assert str(f) in str(exc.value)


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="O_NOFOLLOW required (POSIX)")
def test_billion_laughs_under_gather_exits_zero_with_low_confidence(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "x", "version": "0.0.0"}\n')
    (tmp_path / "pnpm-lock.yaml").write_bytes(_billion_laughs_yaml(depth=200))
    result = invoke_gather(tmp_path)
    assert result.exit_code == 0, result.output
    nm = result.context["probes"]["node_manifest"]
    assert nm["confidence"] == "low", nm
    expected = expected_lockfile_error_id("pnpm", DepthCapExceeded)
    # expected == "pnpm_lock.depth_cap_exceeded" (ADR-0007; node_manifest registry)
    assert nm["errors"] == [expected], nm
    # ADR-0007: typed-exception IDs go to errors[], not warnings[]
    assert all("cap_exceeded" not in w for w in nm.get("warnings", [])), nm
```

```python
# tests/adv/test_json_bomb_huge_string.py
"""Adversarial: 600 MB single-string package.json triggers SizeCapExceeded
PRE-parse. Pins phase-arch-design.md §"Adversarial tests" row 3 + ADR-0008
pre-parse fstat defense.

The patched-json.loads sentinel is the canary: if a regression reads the
file and tries to parse it, the test fails with RuntimeError instead of
SizeCapExceeded — and we know the pre-parse defense regressed.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from codegenie.errors import SizeCapExceeded
from codegenie.parsers import safe_json


def _write_huge_string_package_json(path: Path, *, megabytes: int) -> None:
    chunk = b"a" * (1024 * 1024)
    with path.open("wb") as out:
        out.write(b'{"name": "')
        for _ in range(megabytes):
            out.write(chunk)
        out.write(b'"}')


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="O_NOFOLLOW required (POSIX)")
def test_huge_string_package_json_size_cap_pre_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.disk_usage(tmp_path).free < (1 << 30):  # < 1 GiB free
        pytest.skip("insufficient disk space for 600 MB fixture")
    f = tmp_path / "package.json"
    _write_huge_string_package_json(f, megabytes=600)

    # os.read instrumentation: if safe_json reads bytes BEFORE checking size,
    # the call list is non-empty and the assertion below catches it.
    real_read = os.read
    read_calls: list[int] = []

    def tracing_read(fd: int, n: int) -> bytes:
        read_calls.append(fd)
        return real_read(fd, n)

    monkeypatch.setattr(os, "read", tracing_read)

    with patch("codegenie.parsers.safe_json.json.loads",
               side_effect=RuntimeError("json.loads must not be reached")):
        with pytest.raises(SizeCapExceeded):
            safe_json.load(f, max_bytes=5_000_000)

    assert read_calls == [], "size cap must precede any os.read"
```

For the other two tests follow the same shape — see the Implementation outline §4-§7. The load-bearing reds are:
- **AC-1b / AC-2b / AC-4b gather-level tests** that assert `errors == [<expected_id>]` (closed-world). Without the AC-12 retrofit, AC-2b fails with `errors == []` (the unhandled `DepthCapExceeded` bubbles to the coordinator's generic catch); that failure IS the signal to write the retrofit.
- **AC-3 huge-string canary**: the sentinel `RuntimeError` must NOT fire. If a regression breaks the size check, you'll see `RuntimeError: json.loads must not be reached` in the test output instead of `SizeCapExceeded` — that's the canary.
- **AC-4 pre-parse `yaml.load` canary**: symmetric to AC-3.

### Green — make it pass

The Step 1 parsers already implement the caps; tests #1 / #3 / #4 should pass at the parser level immediately. Test #2 parser-level passes; test #2 gather-level requires the **AC-12 probe retrofit** — two-line edits per probe (one mapping entry + one catch-tuple addition + one `_ERRORS` entry; existing compile-time `_ID_PATTERN.match` guard validates the new ID). Surface the retrofit in the PR body with an explicit "S2-01 / S3-05 follow-up — DepthCapExceeded handler added" note.

If any parser-level test fails because the underlying cap is not enforced, that is a Step-1 regression and must be fixed in `src/codegenie/parsers/safe_json.py` / `safe_yaml.py`. The structlog-event assertion (AC-13/AC-14) is the canary for the `parsers/_io.py` and `parsers/_depth.py` event emission staying complete; if a field is dropped, the AC-8 helper's keyword-arg pin will fail.

### Refactor — clean up

After green:
- Confirm the helpers in `tests/adv/_helpers.py` are imported (not re-implemented) by every adversarial test that touches them.
- Verify `pytest -m adv` selects exactly the four new tests (plus any AC-13/AC-14 cap-event tests) and they complete in under 15 s wall-clock.
- Confirm `mypy --strict tests/adv/` is clean (Literal types preserve `cap_kind` discipline).
- Verify the AC-12 probe edits did not regress any existing `tests/unit/probes/test_language_detection_probe.py` or `tests/unit/probes/test_node_manifest_probe.py` test (the changes are mechanically additive but the catch-tuple union touches an existing line).
- Confirm peak disk footprint locally with `du -h $TMPDIR/pytest-of-*` — the 600 MB write should reclaim cleanly via `tmp_path` teardown.
- Run the full unit+adv suite once with `--cov=src/codegenie` to confirm the AC-12 retrofit is exercised in coverage (the new probe-retrofit unit tests cover the new branch; the integration is the AC-2b CLI test).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Register `adv` pytest marker (Phase 0 ships only `bench`; this PR adds `adv` unconditionally) |
| `tests/adv/_helpers.py` | **NEW (required, not optional)** — `invoke_gather`, `assert_parser_cap_event`, `expected_lockfile_error_id`, `GatherResult` dataclass |
| `tests/adv/test_yaml_billion_laughs.py` | New test file — billion-laughs YAML → `DepthCapExceeded` (AC-1 + AC-1b) |
| `tests/adv/test_json_bomb_deep_nesting.py` | New test file — 10k-nested JSON → `DepthCapExceeded` (AC-2 + AC-2b) + AC-14 depth-cap event payload |
| `tests/adv/test_json_bomb_huge_string.py` | New test file — 600 MB string → `SizeCapExceeded` pre-parse (AC-3) |
| `tests/adv/test_oversized_lockfile.py` | New test file — 60 MB YAML → `SizeCapExceeded` (AC-4 + AC-4b) + AC-13 size-cap event payload |
| `tests/adv/test__helpers.py` | New small unit test for the pure fixture builders (AC-16 determinism check) |
| `src/codegenie/probes/language_detection.py` | **AC-12 retrofit** — `DepthCapExceeded` → `_PKG_JSON_FAILURE`, `_ERRORS`, catch-tuple |
| `src/codegenie/probes/node_manifest.py` | **AC-12 retrofit** — `DepthCapExceeded` → `_PKG_JSON_FAILURE`, catch-tuple |
| `tests/unit/probes/test_language_detection_probe.py` | One new test covering the new `DepthCapExceeded` branch |
| `tests/unit/probes/test_node_manifest_probe.py` | One new test covering the new `DepthCapExceeded` branch |

## Out of scope

- **Symlink-escape / zip-slip / pathological `tsconfig` adversarial tests** — owned by S5-03.
- **Yarn regex-DoS / planted `node` shim / `!!python/object` adversarial tests** — owned by S5-02.
- **Adding new parser-cap mechanisms** — Step 1 owns the production caps; this story exercises them.
- **Property-based fuzzing** — explicitly out of Phase 1 (`final-design.md §"Tests explicitly not in Phase 1"` item 6).
- **Real-world hostile-input corpus mining** — Phase 5's trust-gate work.

## Notes for the implementer

### Load-bearing rules (non-negotiable)

- **The "specific exception" requirement is load-bearing.** Asserting `result.exit_code == 0` alone is a false-positive risk: gather might exit 0 because the file was skipped by a different defense (e.g. `O_NOFOLLOW` if the test accidentally wrote a symlink). Always `pytest.raises(SpecificError)` on the direct parser call, and additionally assert the **closed-world** error ID list at the slice level (`errors == [<expected_id>]`, not `<expected_id> in errors`). See `phase-arch-design.md §"Step 5 — Risks"`.
- **`errors[]` not `warnings[]` for typed-exception IDs.** Per ADR-0007 §Decision: typed-exception-raised IDs land in `errors: list[str]`; `warnings: list[str]` is the soft-degrade vocabulary (`lockfile.multi_present`, `kustomization.resource_outside_repo`, …). Existing implementations confirm: `node_manifest.py:413` and `language_detection.py:456` both append to `errors`. The original story version mistakenly said `warnings` — fixed in this validation. Asserting on `warnings` against a correct implementation will fail; an executor "fixing" by appending to `warnings` would land an ADR-0007 violation.
- **`cap_kind` literal vocabulary.** `"size"` for byte-budget violations, `"depth"` for depth-budget violations — locked in by `parsers/_io.py:47` (`_CAP_KIND_SIZE`) and `parsers/_depth.py:38` (`_CAP_KIND_DEPTH`). NOT `"bytes"`. Per `_validation/S1-03-safe-yaml-parser.md` §AC-14 footnote.
- **600 MB fixture generation must be at test setup, not as a checked-in file.** CI's git checkout would balloon to 600 MB+. Generate inside `tmp_path` via streaming write (`f.write(b"a" * (1024 * 1024))` × 600). Always check `shutil.disk_usage(tmp_path).free` first and `pytest.skip(...)` if low — `OSError(ENOSPC)` is a false-failure cause.
- **Why `safe_yaml.load` raises `DepthCapExceeded` post-parse, not during parse:** `CSafeLoader` has no native depth cap. The Step 1 design is parse-then-walk. This means the YAML *is* fully constructed in memory before the walker raises — for the billion-laughs test, this means the depth must be tuned so the materialized tree is small enough to fit in ~70 MB RSS but deeper than 64 to trigger the post-parse check. The example in the red test uses depth 200 with a one-character leaf — total memory is ~200 dicts. If your test OOMs, you've made the YAML too wide; reduce the breadth.
- **CI walltime budget:** the entire adversarial corpus must run in under 30 s p95 (`phase-arch-design.md §"CI gates"`). This story owns 4 of 10 tests; budget yourself ~12 s wall-clock. Test #3 (600 MB write) is the long pole — measure locally with `time pytest -m adv tests/adv/test_json_bomb_huge_string.py` and tune the chunk-write loop if it exceeds 8 s.

### Probe-retrofit (AC-12) — the most likely place to make a wrong move

- The retrofit is **two lines per probe**, mechanically additive, ADR-0007-pattern-compatible. Do NOT introduce a new error category, a new ID prefix, a new `_demote` rule, or a defensive try/except chain. The existing dispatch tables are the right shape — extend them.
- For `language_detection.py`: the demote rank is `"low"` (DepthCapExceeded indicates a hostile fixture; degrade to lowest-confidence per the existing `SymlinkRefusedError` precedent). For `node_manifest.py`: the failure short-circuits via `_read_package_json` returning `None`; confidence is set to `"low"` at the early-return path (existing line 392).
- The compile-time `_ID_PATTERN.match` assertion in each probe (lang_det.py:220-223; node_manifest.py:284-290) automatically validates the new ID `"package_json.depth_cap_exceeded"` — no new test infrastructure needed for that check.

### Why alias-amplification is NOT this story's target

The original red sample used `[&a [&b [...]]]`-style YAML anchors. Anchor *literals* (`&a`) without alias *references* (`*a`) don't actually cause amplification — they're depth without sharing, which exercises the depth ceiling. True alias amplification (a `*alias` pointing to a previously-defined `&anchor`, repeated to create a logical-DAG visit explosion) is S1-03's territory: see `tests/unit/parsers/test_safe_yaml.py::test_depth_walker_dedupes_alias_targets_no_amplification` for the killer-mutation test that pins the `id()`-memoized walker. The clarified red sample in this story uses pure depth (`[[[1]]]`-style nesting); keep it that way.

### Design-pattern lifts (Notes-only — surfaced for future stories)

- **DP-3 — `Literal["size", "depth"]` / StrEnum for `cap_kind`.** The existing `_CAP_KIND_SIZE` / `_CAP_KIND_DEPTH` constants are typed `Final[str]`. Promoting to `Literal["size", "depth"]` (or a `StrEnum CapKind`) at the parser-event boundary would make `cap_kind="bytes"` a type-check failure rather than a runtime drift. **Not done in this story** because two consumers + per-test literal assertions (AC-13/AC-14) is sufficient defense at Phase 1 (Rule 2 — Simplicity First). Surface for Phase 2 when the parser family grows (`safe_toml`, `safe_xml`, …).
- **DP-4 — Composition over inheritance for adversarial-test base.** Tempting to extract a `class AdversarialParserCapTest` with hooks, but Rule 2 + the strong CI-debugging value of explicit per-test files (each with distinct `pytest --tb=short` failure context) wins. The helpers in AC-7/AC-8/AC-9 give us composition without inheritance.
- **DP-5 — `WarningId` Annotated-type adoption in tests.** `phase-arch-design.md "Data model"` declares `WarningId = Annotated[str, Pattern(...)]`. Tests could import this for type-level assertions on the IDs they construct. **Not done** because the runtime `_ID_PATTERN.match` compile-time assertion in each probe (node_manifest.py:284) is the structural defense; tests asserting `errors == [<id>]` get the runtime check transitively. Surface as Phase-2 polish if the WarningId vocabulary grows enough to warrant a typed enum.

### Integration with `tests/adv/conftest.py`

The Phase-0 `_disable_cli_configure_logging` autouse fixture (`tests/adv/conftest.py:23`) is already binding for everything under `tests/adv/`. It no-ops `cli._seam_configure_logging` so `structlog.testing.capture_logs` keeps its `LogCapture` processor live — without it, the cap-event assertions (AC-13/AC-14) would silently observe an empty `logs` list (false-positive green). Do not override or duplicate this fixture in the new test files.
