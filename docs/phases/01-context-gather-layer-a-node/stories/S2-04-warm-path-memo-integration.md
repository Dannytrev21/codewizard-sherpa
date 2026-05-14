# Story S2-04 — Warm-path memo integration test (`LanguageDetectionProbe` + `NodeBuildSystemProbe`)

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready (Hardened 2026-05-14)
**Effort:** S
**Depends on:** S2-03 (canonical fixture `node_typescript_helm/`)
**ADRs honored:** ADR-0002 (memo behavior across two probes), ADR-0004 (sub-schema strictness via the rejection test), ADR-0007 (warning IDs), ADR-0010 (Layer A slices optional at envelope)

## Validation notes (2026-05-14)

Hardened by `phase-story-validator`. Full audit at [`_validation/S2-04-warm-path-memo-integration.md`](_validation/S2-04-warm-path-memo-integration.md). Summary of changes:

- **Replaced nonexistent helpers with the actual Phase 0 precedent.** The original draft prescribed `from codegenie.cli import gather_in_process` and a `structlog_capture` / `caplog_structlog` pytest fixture — neither exists. The real precedent lives at [`tests/smoke/test_cli_end_to_end.py`](../../../../tests/smoke/test_cli_end_to_end.py): `click.testing.CliRunner` invoked with `["--no-gitignore", "gather", str(fixture)]`, paired with the `structlog.testing.capture_logs()` *context manager* (not a fixture).
- **Surfaced the load-bearing `_disable_cli_configure_logging` autouse seam disablement.** [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) no-ops `codegenie.cli._seam_configure_logging` because `CliRunner.invoke` would otherwise re-run `configure_logging`, replace structlog's processor chain, and silently drop every event the `capture_logs()` chain was swapped in to collect. Phase 1's new `tests/integration/probes/` tree needs the same autouse fixture (sibling conftest, or lift the autouse to a shared root `tests/conftest.py`); without it, every memo-event count silently returns 0 and the assertion produces a misleading RED. This is now an explicit AC.
- **Fixed the ADR-0004 rejection assertion to match what the validator actually emits.** [`src/codegenie/schema/validator.py`](../../../../src/codegenie/schema/validator.py) raises `SchemaValidationError(f"validation failed at {pointer}: {err.message}")`. `SchemaValidationError` has **no `.json_pointer` attribute** (it is a bare `CodegenieError` subclass in [`src/codegenie/errors.py:84`](../../../../src/codegenie/errors.py)), and `err.json_path` emits jsonschema's JSONPath form (`$.probes.node_build_system.unknown_field`), not RFC-6901 JSON Pointer (`/probes/node_build_system/unknown_field`). The AC now asserts the path is embedded in `str(exc_info.value)` in JSONPath form. A structured `.json_path` attribute on `SchemaValidationError` is a follow-up worth scoping in a separate ADR amendment — flagged in Notes, out of scope here.
- **Wired the actual validator import path.** `from codegenie.schema import load_envelope_validator` does not exist; the public API is `from codegenie.schema.validator import validate` (a function that raises `SchemaValidationError`).
- **Tightened memo event filter from `path` substring to `allowlist_match == "package.json"`.** [`src/codegenie/coordinator/parsed_manifest_memo.py`](../../../../src/codegenie/coordinator/parsed_manifest_memo.py) emits both `path=log_path` and `allowlist_match=path.name`; the structured allowlist key matches exactly and is robust against incidental `package.json` substrings elsewhere in the captured path.
- **Added fail-loud ACs (Rule 12).** The slice ACs now assert `language_detection.errors == []`, `language_detection.warnings == []`, `node_build_system.errors == []`, `node_build_system.warnings == []`, and `node_build_system.confidence == "high"`. Without these, a probe could degrade silently while still producing the headline fields and the test would still pass — exactly the failure mode the integration test exists to catch.
- **Defined `_minimal_valid_envelope()` concretely.** The original draft left it as a TODO. The envelope's required keys are `schema_version`, `generated_at`, `repo.{root,git_commit}`, `probes`; the helper now has a fixed shape so the executor doesn't invent one.
- **Surfaced rule-of-three extraction (Notes only).** `_copy_tree`, `_count_memo_events(events, *, allowlist_match)`, `_minimal_valid_envelope()`, and `_load_envelope()` will be reused by S2-05 (cache-hit-on-real-repo) and S5-05 (all-six-probes). Recommend landing them in `tests/integration/probes/conftest.py` in this story rather than inlining — the third consumer is in the same step (S2-05) so the extension-by-addition kernel is justified now (CLAUDE.md "Extension by addition", Rule of three).

## Context

S2-04 is the **first integration test in Phase 1** and the first end-to-end exercise of the `ParsedManifestMemo` (S1-07) across more than one probe. It is the proof point for two distinct invariants:

1. **The memo eliminates redundant `package.json` parses.** Across `LanguageDetectionProbe` (S2-01) + `NodeBuildSystemProbe` (S2-02), `package.json` is read exactly once via `safe_json.load`; the second read is a memo hit. The event count asserted by this test is `probe.memo.miss == 1` + `probe.memo.hit == 1`.
2. **The framework-hint extension propagates through the pipeline** — through the validator, sanitizer, schema validation, and YAML writer — and lands in the on-disk `repo-context.yaml` as `framework_hints == ["express"]`.

The sub-schema rejection assertion (ADR-0004 cross-cutting concern, manifest §"Cross-cutting concerns") lives here so Step 2 has at least one ADR-0004 rejection test on disk before Step 3 lands. The S5-05 end-to-end test extends the assertions to all six probes; this test is the focused two-probe version.

The test name (`test_language_detection_warm_path.py`) reflects the load-bearing assertion: it's the memo's warm path, exercised across two probes in one gather.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Control flow"` — happy-path one-paragraph description, including memo behavior across probes.
  - `../phase-arch-design.md §"Control flow" → "Decision points" → "Memo hit vs. memo miss"`.
  - `../phase-arch-design.md §"Component design" #3` (`ParsedManifestMemo` — per-gather lifetime, allowlist, hit/miss events).
  - `../phase-arch-design.md §"Harness engineering"` — `probe.memo.{hit,miss}` event-name constants.
  - `../phase-arch-design.md §"Edge cases"` row 12 (`ctx.parsed_manifest is None` fallback) and row 16 (mid-gather mtime change).
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the contract this test exercises.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — the rejection assertion at the bottom of this test file.
- **Source design:**
  - `../../../localv2.md §5.1 A1–A2` — the two slices populated here.
- **Existing code:**
  - `tests/fixtures/node_typescript_helm/` (from S2-03).
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (from S1-07/S1-08) — the structlog events this test counts come from here. Emits `path=<absolute or repo-relative path>` and `allowlist_match=<path.name>`; filter on `allowlist_match`, not `path`.
  - `src/codegenie/probes/language_detection.py` (extended in S2-01).
  - `src/codegenie/probes/node_build_system.py` (from S2-02).
  - `src/codegenie/cli.py` — `codegenie gather` entry point. Tests invoke via `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])`.
  - `src/codegenie/logging.py` — `EVENT_PROBE_MEMO_HIT = "probe.memo.hit"` / `EVENT_PROBE_MEMO_MISS = "probe.memo.miss"` event constants.
  - `src/codegenie/schema/validator.py` — `validate(repo_context)` raises `SchemaValidationError(f"validation failed at {err.json_path}: {err.message}")`. The pointer is **inside the message string** in jsonschema's JSONPath format (`$.probes.…`), not RFC-6901.
  - `src/codegenie/errors.py:84` — `SchemaValidationError(CodegenieError)`. No `.json_pointer` attribute today.
- **Precedent (Phase 0):**
  - `tests/smoke/test_cli_end_to_end.py` — canonical `CliRunner` + `structlog.testing.capture_logs()` pattern; see `_invoke_gather`, `_read_envelope`, and `test_cache_hit_on_second_run` for the load-bearing event-counting shape.
  - `tests/smoke/conftest.py` — `_disable_cli_configure_logging` autouse fixture (load-bearing) and `_copy_fixture` helper. Phase 1's `tests/integration/probes/conftest.py` must replicate (or inherit via a shared root conftest) the autouse seam disablement, otherwise `capture_logs()` is silently empty inside `CliRunner.invoke`.

## Goal

Running `codegenie gather tests/fixtures/node_typescript_helm/` in a clean cache state produces a `.codegenie/context/repo-context.yaml` whose `probes.language_detection.language_stack.framework_hints == ["express"]`, while the structlog event stream contains exactly one `probe.memo.miss` (the first read by either probe) and exactly one `probe.memo.hit` (the second read by the other probe).

## Acceptance criteria

### Test-file existence + harness wiring

- [ ] **AC-1.** `tests/integration/probes/test_language_detection_warm_path.py` exists.
- [ ] **AC-2.** `tests/integration/probes/conftest.py` exists **and** declares an autouse `_disable_cli_configure_logging` monkeypatch that no-ops `codegenie.cli._seam_configure_logging` for the duration of every test in this directory. (Without this, `CliRunner.invoke` re-runs `configure_logging`, replaces structlog's processor chain, clobbers the `capture_logs()` chain, and every event count silently collapses to 0 — see [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) for the established precedent.) If the implementer instead lifts this fixture to a project-root `tests/conftest.py` so both `tests/smoke/` and `tests/integration/probes/` inherit it, the AC is also satisfied — but the existing `tests/smoke/` autouse must continue to bind.
- [ ] **AC-3.** The test invokes the CLI via `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])`. **Not** `subprocess.run` (capture chain lives in this process). **Not** an invented `gather_in_process` helper — it does not exist.
- [ ] **AC-4.** The test uses `from structlog.testing import capture_logs` as a context manager wrapping the `CliRunner.invoke` call. (Not a pytest fixture — no `structlog_capture` / `caplog_structlog` fixture exists in this repo.)

### Slice content invariants (fail-loud, Rule 12)

- [ ] **AC-5.** After the gather completes, the test loads `.codegenie/context/repo-context.yaml` via `yaml.safe_load(...)` and asserts `probes.language_detection.language_stack.framework_hints == ["express"]` (exact equality, not membership — so an accidentally duplicated `["express", "express"]` or extra `["express", "next"]` is a fail).
- [ ] **AC-6.** `probes.language_detection.language_stack.monorepo is None` (the canonical fixture is single-package; the monorepo path is exercised by `node_monorepo_turbo` in S5-04).
- [ ] **AC-7.** `probes.node_build_system.package_manager == "pnpm"` (lockfile-precedence pick on the fixture).
- [ ] **AC-8.** `probes.language_detection.errors == []` **and** `probes.language_detection.warnings == []`. Without this, a probe could ship `framework_hints == ["express"]` alongside a `confidence: low` + `framework_hints.duplicate_detected` warning and still pass — exactly the silent-degradation failure mode this integration test exists to surface.
- [ ] **AC-9.** `probes.node_build_system.errors == []` **and** `probes.node_build_system.warnings == []` **and** `probes.node_build_system.confidence == "high"` (a single-lockfile, non-cycling-tsconfig fixture has no legitimate trigger for `low`/`medium`).
- [ ] **AC-10.** The CLI exits 0 (`result.exit_code == 0`, asserted with `result.output` in the failure message for diagnostics).

### Memo warm-path event-count assertion (load-bearing)

- [ ] **AC-11.** Collecting all structlog events captured during the gather, count `event == "probe.memo.miss" AND allowlist_match == "package.json"`: **exactly 1**. Count `event == "probe.memo.hit" AND allowlist_match == "package.json"`: **exactly 1**. (Use the structured `allowlist_match` key — the memo emits it explicitly — not a substring match on `path`.) Both `0 + 0` (memo never consulted; probes called `safe_json.load` directly) and `2 + 0` (memo consulted but never returns a hit) fail this assertion — the mutation-resistance is the point.

### ADR-0004 cross-cutting rejection assertion (per manifest "Cross-cutting concerns")

- [ ] **AC-12.** A separate test case `test_extra_field_under_node_build_system_rejected` in the same file builds a minimal valid envelope dict (via the helper `_minimal_valid_envelope()` defined in this story's `Implementation outline`), inserts `envelope["probes"]["node_build_system"] = {"unknown_field": 1}`, and calls `from codegenie.schema.validator import validate; validate(envelope)`. The test asserts `SchemaValidationError` is raised, and asserts the failing path is surfaced in the message string. Use the validator's actual emission format — `err.json_path` is jsonschema's JSONPath form (`$.probes.node_build_system.unknown_field`), embedded in `str(exc_info.value)`. Concretely:

  ```python
  with pytest.raises(SchemaValidationError) as exc_info:
      validate(envelope)
  message = str(exc_info.value)
  assert "probes" in message and "node_build_system" in message and "unknown_field" in message, message
  ```

  **Why not assert `.json_pointer`:** `SchemaValidationError` is a bare `CodegenieError` subclass today with no structured pointer attribute; introducing one is a separate ADR-amendable change (flagged as a follow-up in `Notes for the implementer`). **Why not assert the literal RFC-6901 Pointer `/probes/node_build_system/unknown_field`:** the validator emits JSONPath via `err.json_path`, not RFC-6901 — see [`src/codegenie/schema/validator.py:74`](../../../../src/codegenie/schema/validator.py). The looser `in`-on-each-component assertion above is robust against either future shape (JSONPath or RFC-6901 Pointer) while still failing when the pointer points at the wrong slice.

### Static + dynamic gates

- [ ] **AC-13.** `ruff check tests/integration/probes/test_language_detection_warm_path.py tests/integration/probes/conftest.py` passes.
- [ ] **AC-14.** `ruff format --check tests/integration/probes/test_language_detection_warm_path.py tests/integration/probes/conftest.py` passes.
- [ ] **AC-15.** `mypy --strict tests/integration/probes/test_language_detection_warm_path.py tests/integration/probes/conftest.py` passes (strict mode is the Phase 0 default; no `Any` slip-throughs on the captured-event list shape — use `list[dict[str, Any]]` explicitly).
- [ ] **AC-16.** `pytest tests/integration/probes/test_language_detection_warm_path.py` exits 0 (both test functions pass).

## Implementation outline

1. **Land `tests/integration/probes/conftest.py`** with:
   - The autouse `_disable_cli_configure_logging` monkeypatch (lifted from [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) — copy that fixture verbatim; the docstring there explains why it is load-bearing).
   - The `_copy_tree(src: Path, dst: Path) -> Path` helper (clones a fixture tree into `tmp_path`).
   - The `_load_envelope(repo: Path) -> dict[str, object]` helper (reads `.codegenie/context/repo-context.yaml` via `yaml.safe_load`; asserts the file exists with a clear message).
   - The `_count_memo_events(events, *, allowlist_match: str) -> tuple[int, int]` helper returning `(miss_count, hit_count)`. Filter on the structured `allowlist_match` key the memo emits, not a substring on `path`.
   - The `_minimal_valid_envelope() -> dict[str, object]` helper returning the smallest envelope the schema accepts:
     ```python
     def _minimal_valid_envelope() -> dict[str, object]:
         return {
             "schema_version": "0.1.0",
             "generated_at": "2026-05-14T00:00:00Z",
             "repo": {"root": "/tmp/test-repo", "git_commit": None},
             "probes": {},
         }
     ```
     The envelope schema requires only `schema_version`, `generated_at`, `repo.{root, git_commit}`, and `probes` ([`src/codegenie/schema/repo_context.schema.json:8`](../../../../src/codegenie/schema/repo_context.schema.json)). All four helpers are reused by S2-05 (cache-hit-on-real-repo) and S5-05 (all-six-probes-warm-path), so they belong in `conftest.py` from the start (rule of three; CLAUDE.md "Extension by addition").
2. **Add `tests/integration/probes/test_language_detection_warm_path.py`** with two top-level test functions:
   - `test_warm_path_memo_hits_once_across_two_probes(tmp_path)`
   - `test_extra_field_under_node_build_system_rejected()`
3. **Invocation pattern** (mirror [`tests/smoke/test_cli_end_to_end.py:87`](../../../../tests/smoke/test_cli_end_to_end.py)):
   ```python
   from click.testing import CliRunner
   from structlog.testing import capture_logs
   from codegenie.cli import cli

   with capture_logs() as events:
       result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
   ```
   `events` is a `list[dict[str, Any]]` captured for the lifetime of the `with` block. The autouse fixture from AC-2 keeps the chain alive across `CliRunner.invoke`.
4. After the gather:
   - Assert `result.exit_code == 0, result.output`.
   - Load the envelope via `_load_envelope(repo)`; assert AC-5 through AC-9 against the slices.
   - Run `miss, hit = _count_memo_events(events, allowlist_match="package.json")`; assert `miss == 1, events` and `hit == 1, events` (include `events` in the failure message so the executor can diagnose a `2/0` or `0/0` failure without re-running).
5. The ADR-0004 rejection test case builds an envelope in-test via `_minimal_valid_envelope()`, adds the rogue field, invokes `validate(envelope)` from `codegenie.schema.validator`, asserts `SchemaValidationError` raised, asserts each pointer component (`"probes"`, `"node_build_system"`, `"unknown_field"`) appears in `str(exc_info.value)`. Do **not** assert on `.json_pointer` — there is no such attribute today.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_language_detection_warm_path.py`

Sibling: `tests/integration/probes/conftest.py` carries the five helpers + the autouse `_disable_cli_configure_logging` monkeypatch (lifted verbatim from [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py)).

```python
# tests/integration/probes/test_language_detection_warm_path.py

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import cli
from codegenie.errors import SchemaValidationError
from codegenie.schema.validator import validate

# Imports from conftest.py (sibling) — these helpers are reused by S2-05 + S5-05.
from .conftest import (
    _copy_tree,
    _count_memo_events,
    _load_envelope,
    _minimal_valid_envelope,
)

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "node_typescript_helm"


def test_warm_path_memo_hits_once_across_two_probes(tmp_path: Path) -> None:
    # arrange: clone fixture into tmp_path so the .codegenie write is hermetic
    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    # act: invoke the real CLI in-process; capture the structlog event stream
    with capture_logs() as events:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])

    # assert: exit clean
    assert result.exit_code == 0, result.output

    # assert: slice content invariants (AC-5..AC-9)
    envelope = _load_envelope(repo)
    lang = envelope["probes"]["language_detection"]
    nbs = envelope["probes"]["node_build_system"]

    assert lang["language_stack"]["framework_hints"] == ["express"]
    assert lang["language_stack"]["monorepo"] is None
    assert lang["errors"] == [], lang
    assert lang["warnings"] == [], lang

    assert nbs["package_manager"] == "pnpm"
    assert nbs["errors"] == [], nbs
    assert nbs["warnings"] == [], nbs
    assert nbs["confidence"] == "high", nbs

    # assert: memo event-count invariant (AC-11) — filter on structured
    # `allowlist_match` key, not a substring on `path`
    miss, hit = _count_memo_events(events, allowlist_match="package.json")
    assert miss == 1, f"expected exactly 1 miss; got {miss}. events={events}"
    assert hit == 1, f"expected exactly 1 hit; got {hit}. events={events}"


def test_extra_field_under_node_build_system_rejected() -> None:
    # AC-12 — ADR-0004 cross-cutting rejection test
    envelope: dict[str, Any] = _minimal_valid_envelope()
    envelope["probes"]["node_build_system"] = {"unknown_field": 1}

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(envelope)

    message = str(exc_info.value)
    # The validator emits the failing path inside the message string via
    # `err.json_path` (jsonschema's JSONPath form). Assert each component
    # appears — robust against either JSONPath or RFC-6901 future shape.
    assert "probes" in message, message
    assert "node_build_system" in message, message
    assert "unknown_field" in message, message
```

Confirm both tests red — the first because the fixture isn't yet wired through CLI or the memo emits the wrong event count (depending on implementation order); the second because either the rogue field isn't rejected (sub-schema is loose) or the rejection message doesn't carry the path components. Commit, then Green.

### Green — make it pass

This test doesn't write production code — its purpose is to exercise the production paths already on disk (S1-07 memo, S2-01 framework hints, S2-02 build system). If a green assertion fails, the failure surfaces in the production code, not here. Specifically:

- If `framework_hints != ["express"]`: S2-01 is wrong; fix there.
- If `package_manager != "pnpm"`: S2-02 is wrong.
- If memo counts are off: either S1-07 is wrong, S2-01 isn't going through the memo, or S2-02 isn't going through the memo. Diagnose by which probe emitted which event.
- If the schema rejection lands at the wrong pointer: S2-02's sub-schema or the envelope's `$ref` composition is wrong.

The integration test is the **diagnostic**, not the implementation.

### Refactor — clean up

- Helpers (`_copy_tree`, `_count_memo_events`, `_load_envelope`, `_minimal_valid_envelope`) **already land in `tests/integration/probes/conftest.py` per AC-2** — S2-05 and S5-05 import them by name. The conftest is the kernel; tests are the policy.
- Confirm `mypy --strict` clean on both the test file and the conftest. The `events` list is typed `list[dict[str, Any]]`; helpers use precise return types (`tuple[int, int]` for `_count_memo_events`, `dict[str, object]` for `_load_envelope` / `_minimal_valid_envelope`).
- `ruff check` + `ruff format --check` clean.
- Document at the top of the file *why* the assertion is "exactly 1 miss + 1 hit, not 0 + 2" — the load-bearing observation is that the memo serves the second read, so the first read must be a miss; a `0/0` result means the probes called `safe_json.load` directly and bypassed the memo entirely (the failure mode the test exists to catch).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/test_language_detection_warm_path.py` | New file — the two test cases described above (warm-path memo + ADR-0004 rejection). |
| `tests/integration/probes/conftest.py` | New file — the autouse `_disable_cli_configure_logging` monkeypatch (load-bearing for `capture_logs` to receive events under `CliRunner.invoke`) plus the four shared helpers (`_copy_tree`, `_count_memo_events`, `_load_envelope`, `_minimal_valid_envelope`). The autouse and helpers are reused by S2-05 + S5-05; landing them here from the start prevents a future copy-paste cliff. |
| `tests/integration/probes/__init__.py` | Empty package marker — needed for the relative `from .conftest import ...` to resolve. |
| `tests/integration/__init__.py` | Empty package marker. |

## Out of scope

- **All-six-probes cache-hit assertion** — S5-05 extends S2-05 to cover all six. This test asserts memo + framework hints on two probes only.
- **`os.scandir` invocation count assertion** — that's S2-05's load-bearing assertion (cache-hit-on-second-run).
- **Adversarial fixtures (`tests/adv/`)** — S5-01 / S5-02 / S5-03.
- **Golden-file diff** — S6-01.
- **Real-`node-on-$PATH` hostile-shim** — S5-02.

## Notes for the implementer

- **The `_disable_cli_configure_logging` autouse fixture is load-bearing — not optional.** `CliRunner.invoke` exits and re-enters Click's runtime, which calls `_seam_configure_logging` and replaces structlog's active processor chain. `capture_logs()` works by swapping its own `LogCapture` processor into that chain; a re-configure inside `invoke` blows it away and every captured-event list comes back empty. This was discovered in Phase 0 ([`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) module docstring documents the post-mortem). Lift the fixture verbatim or, preferably, move it to a project-root `tests/conftest.py` so both `tests/smoke/` and `tests/integration/probes/` inherit it from one place — at that point the smoke conftest's local fixture can be deleted. Either path satisfies AC-2.
- **The "exactly 1 miss + 1 hit" assertion is non-trivial.** It depends on (a) both probes reading `package.json` via `ctx.parsed_manifest(...)` (not `safe_json.load` direct); (b) the coordinator constructing a single `ParsedManifestMemo` per gather and exposing it via `ctx.parsed_manifest` on every `ProbeContext`; (c) the structlog event emitter inside `ParsedManifestMemo.get(...)`. If any link breaks, the count is wrong. The most common silent-failure mode is `(0, 0)`: a probe bypasses the memo and goes direct to `safe_json.load`. The included `events` in the failure message lets you diagnose without re-running.
- **Use `CliRunner` + `capture_logs()`, never `subprocess.run`.** A subprocess gather emits to a different process's stderr and the `capture_logs()` chain (process-local) is empty. The Phase 0 precedent is [`tests/smoke/test_cli_end_to_end.py:87`](../../../../tests/smoke/test_cli_end_to_end.py) — `_invoke_gather`. Do **not** invent a `gather_in_process` helper; it doesn't exist.
- **Don't depend on event order between the two probes.** Wave 2 dispatches `LanguageDetectionProbe` and `NodeBuildSystemProbe` per the topological-sort rules — but `NodeBuildSystemProbe` `requires=["language_detection"]`, so LD always runs first. Even so, write the assertion as "exactly one miss, exactly one hit," not "LD missed then NBS hit" — that ordering may change subtly if `requires` semantics shift in Phase 2.
- **The memo emits `path` and `allowlist_match`; filter on the latter.** Look at [`src/codegenie/coordinator/parsed_manifest_memo.py:137,143`](../../../../src/codegenie/coordinator/parsed_manifest_memo.py) — `_logger.info(EVENT, path=log_path, allowlist_match=path.name)`. `allowlist_match == "package.json"` is exact; `"package.json" in path` is loose and would over-match a hypothetical future `package.json.bak` or `nested/path/with/package.json/in/it`.
- **`SchemaValidationError` carries the path inside the message string, not as a structured attribute (today).** [`src/codegenie/schema/validator.py:74`](../../../../src/codegenie/schema/validator.py) emits `f"validation failed at {err.json_path}: {err.message}"` where `err.json_path` is jsonschema's JSONPath (`$.probes.node_build_system.unknown_field`). A structured `.json_path` attribute on `SchemaValidationError` (with optional `.json_pointer` companion that converts JSONPath → RFC-6901) is a reasonable follow-up — file it as a Phase 1 nit and link this story, but do **not** add it inside S2-04. Out of scope.
- **Cross-cutting "ADR-0004 minimum" framing.** This story carries the `node_build_system` rejection only. Step 3's `test_node_manifest_*` and Step 4's three probes each contribute their own rejection tests; in aggregate the cross-cutting concern §"`additionalProperties: false`" is satisfied. The helper `_minimal_valid_envelope()` (in conftest) is the shared kernel — every future rejection test reuses it.
- **Rule-of-three extraction is justified now, not later.** S2-04 (this story) + S2-05 (cache-hit-on-real-repo) + S5-05 (all-six-probes warm-path) all need the same four helpers and the same autouse seam disablement. Three concrete consumers > rule-of-three threshold; CLAUDE.md "Extension by addition" wants the kernel landed when the third consumer is in the same step (S2-05). Land the conftest in this story.
- **No mutation testing or coverage threshold check** lives here. Per the manifest, coverage is reported in PR bodies (cross-cutting concern #6) and ratcheted to 90/80 in S6-02. This story just needs to pass.
- **Adding a new memoizable manifest in a future phase** (Phase 2's `IndexHealthProbe` extends the allowlist to `{"package.json", "scip-index.json"}`) must require zero edits to `tests/integration/probes/conftest.py`'s helpers — they already accept `allowlist_match` as a keyword. Confirm this implicitly by writing the helper signature `_count_memo_events(events, *, allowlist_match: str) -> tuple[int, int]` rather than hard-coding `"package.json"`.
