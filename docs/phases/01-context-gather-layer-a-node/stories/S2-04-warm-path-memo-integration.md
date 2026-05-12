# Story S2-04 — Warm-path memo integration test (`LanguageDetectionProbe` + `NodeBuildSystemProbe`)

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S2-03 (canonical fixture `node_typescript_helm/`)
**ADRs honored:** ADR-0002 (memo behavior across two probes), ADR-0004 (sub-schema strictness via the rejection test), ADR-0007 (warning IDs), ADR-0010 (Layer A slices optional at envelope)

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
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (from S1-07) — the structlog events this test counts come from here.
  - `src/codegenie/probes/language_detection.py` (extended in S2-01).
  - `src/codegenie/probes/node_build_system.py` (from S2-02).
  - `src/codegenie/cli.py` — `codegenie gather` entry point.
  - `src/codegenie/logging.py` — `probe.memo.hit` / `probe.memo.miss` event constants.

## Goal

Running `codegenie gather tests/fixtures/node_typescript_helm/` in a clean cache state produces a `.codegenie/context/repo-context.yaml` whose `probes.language_detection.language_stack.framework_hints == ["express"]`, while the structlog event stream contains exactly one `probe.memo.miss` (the first read by either probe) and exactly one `probe.memo.hit` (the second read by the other probe).

## Acceptance criteria

- [ ] `tests/integration/probes/test_language_detection_warm_path.py` exists.
- [ ] The test invokes `codegenie gather <fixture path>` programmatically (via `CliRunner` or the equivalent in-process entry point — **not** `subprocess.run`; per Phase 0 convention, integration tests run in-process to avoid subprocess overhead and to give the structlog capture fixture access to events).
- [ ] After the gather completes, the test loads `.codegenie/context/repo-context.yaml` via `safe_yaml.load` and asserts `probes.language_detection.language_stack.framework_hints == ["express"]`.
- [ ] The test asserts `probes.language_detection.language_stack.monorepo is None` (the canonical fixture is single-package, not a monorepo — the monorepo path is exercised by `node_monorepo_turbo` in S5-04).
- [ ] The test asserts `probes.node_build_system.package_manager == "pnpm"` (lockfile-precedence pick on the fixture).
- [ ] Memo event-count assertion: collecting all structlog events emitted during the gather, the count of events with `event == "probe.memo.miss"` and a `path` containing `package.json` is exactly **1**; the count of `event == "probe.memo.hit"` for the same `path` is exactly **1**. (Total: one miss, one hit, across two probes reading the same `package.json`.)
- [ ] ADR-0004 rejection assertion: a separate test case in the same file (`test_extra_field_under_node_build_system_rejected`) builds a synthetic envelope dict with `probes.node_build_system.unknown_field: 1`, passes it to the envelope validator, asserts `SchemaValidationError` at JSON Pointer `/probes/node_build_system/unknown_field`. (This assertion lives here per the manifest "Cross-cutting concerns" — every Phase-1 sub-schema gets at least one rejection test; ADR-0004.)
- [ ] The gather exits 0 (no `SchemaValidationError`, no probe crashes).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/integration/probes/test_language_detection_warm_path.py`, `pytest tests/integration/probes/test_language_detection_warm_path.py` all pass.

## Implementation outline

1. Add `tests/integration/probes/test_language_detection_warm_path.py`.
2. Use the Phase 0 in-process CLI helper (`from codegenie.cli import gather_in_process` or whatever the Phase 0 test helper is named — look at `tests/integration/test_gather_cli.py` from Phase 0 for the precedent). Pass the fixture path; let it write to a `tmp_path`-scoped output dir.
3. Capture the structlog event stream via the Phase 0 `caplog_structlog` or `structlog_capture` fixture (whichever Phase 0 standardized).
4. After the gather:
   - Open `<tmp_path>/.codegenie/context/repo-context.yaml`; load via `safe_yaml.load`.
   - Assert the four content invariants (`framework_hints`, `monorepo`, `package_manager`, exit 0).
   - Filter the captured event stream for `probe.memo.miss` / `probe.memo.hit` events with the fixture's `package.json` path; assert counts.
5. Add the ADR-0004 rejection test case as a separate `def test_extra_field_under_node_build_system_rejected()` in the same file. Build a minimal envelope dict in-test (do not write to disk). Use `from codegenie.schema import load_envelope_validator` and `pytest.raises(SchemaValidationError)`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_language_detection_warm_path.py`

```python
# tests/integration/probes/test_language_detection_warm_path.py

from pathlib import Path
import pytest

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "node_typescript_helm"


def test_warm_path_memo_hits_once_across_two_probes(tmp_path, structlog_capture):
    # arrange: copy fixture into tmp_path so .codegenie writes don't pollute the repo
    repo = tmp_path / "repo"
    _copy_tree(FIXTURE, repo)
    # act
    from codegenie.cli import gather_in_process
    exit_code = gather_in_process([str(repo)], cwd=repo)
    # assert exit
    assert exit_code == 0
    # assert content
    import yaml
    ctx = yaml.safe_load((repo / ".codegenie" / "context" / "repo-context.yaml").read_text())
    lang = ctx["probes"]["language_detection"]["language_stack"]
    assert lang["framework_hints"] == ["express"]
    assert lang["monorepo"] is None
    assert ctx["probes"]["node_build_system"]["package_manager"] == "pnpm"
    # assert memo event counts
    events = list(structlog_capture)
    pkg_path_substring = "package.json"
    miss = [e for e in events if e["event"] == "probe.memo.miss" and pkg_path_substring in e.get("path", "")]
    hit  = [e for e in events if e["event"] == "probe.memo.hit"  and pkg_path_substring in e.get("path", "")]
    assert len(miss) == 1, miss
    assert len(hit)  == 1, hit


def test_extra_field_under_node_build_system_rejected():
    # ADR-0004 cross-cutting rejection test
    from codegenie.schema import load_envelope_validator
    from codegenie.errors import SchemaValidationError
    envelope = _minimal_valid_envelope()
    envelope["probes"]["node_build_system"]["unknown_field"] = 1
    with pytest.raises(SchemaValidationError) as exc_info:
        load_envelope_validator().validate(envelope)
    assert exc_info.value.json_pointer == "/probes/node_build_system/unknown_field"
```

Confirm both tests red — the first because the fixture isn't yet wired through CLI or the memo emits the wrong event count (depending on implementation order); the second because the schema rejects on a different pointer. Commit, then Green.

### Green — make it pass

This test doesn't write production code — its purpose is to exercise the production paths already on disk (S1-07 memo, S2-01 framework hints, S2-02 build system). If a green assertion fails, the failure surfaces in the production code, not here. Specifically:

- If `framework_hints != ["express"]`: S2-01 is wrong; fix there.
- If `package_manager != "pnpm"`: S2-02 is wrong.
- If memo counts are off: either S1-07 is wrong, S2-01 isn't going through the memo, or S2-02 isn't going through the memo. Diagnose by which probe emitted which event.
- If the schema rejection lands at the wrong pointer: S2-02's sub-schema or the envelope's `$ref` composition is wrong.

The integration test is the **diagnostic**, not the implementation.

### Refactor — clean up

- Extract `_copy_tree` and `_minimal_valid_envelope` into a `tests/integration/probes/conftest.py` if reused by S2-05.
- Confirm `mypy --strict` clean on the test file; `ruff check`; the `structlog_capture` fixture is typed per Phase 0's conftest.
- Document at the top of the file *why* the assertion is "exactly 1 miss + 1 hit, not 0 + 2" — the load-bearing observation is that the memo serves the second read, so the first read must be a miss.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/test_language_detection_warm_path.py` | New file — the two test cases described above. |
| `tests/integration/probes/conftest.py` (optional) | If `_copy_tree` / `_minimal_valid_envelope` is also needed by S2-05, factor it here. |

## Out of scope

- **All-six-probes cache-hit assertion** — S5-05 extends S2-05 to cover all six. This test asserts memo + framework hints on two probes only.
- **`os.scandir` invocation count assertion** — that's S2-05's load-bearing assertion (cache-hit-on-second-run).
- **Adversarial fixtures (`tests/adv/`)** — S5-01 / S5-02 / S5-03.
- **Golden-file diff** — S6-01.
- **Real-`node-on-$PATH` hostile-shim** — S5-02.

## Notes for the implementer

- **The "exactly 1 miss + 1 hit" assertion is non-trivial.** It depends on (a) both probes reading `package.json` via `ctx.parsed_manifest(...)` (not `safe_json.load` direct); (b) the coordinator constructing a single `ParsedManifestMemo` per gather and exposing it via `ctx.parsed_manifest` on every `ProbeContext`; (c) the structlog event emitter inside `ParsedManifestMemo.get(...)`. If any link breaks, the count is wrong. Diagnose by `printing` the captured events sorted by `wall_clock_ms`.
- **Use the in-process CLI helper, not `subprocess.run`.** The structlog `structlog_capture` fixture relies on a process-local handler; a subprocess gather emits to a different process's stderr and the capture is empty. The Phase 0 test suite established this pattern; follow it.
- **Don't depend on event order between the two probes.** Wave 2 dispatches `LanguageDetectionProbe` and `NodeBuildSystemProbe` per the topological-sort rules — but `NodeBuildSystemProbe` `requires=["language_detection"]`, so LD always runs first. Even so, write the assertion as "exactly one miss, exactly one hit," not "LD missed then NBS hit" — that ordering may change subtly if `requires` semantics shift in Phase 2.
- **`structlog_capture` fixture origin.** Look at Phase 0's `tests/conftest.py` for the canonical fixture name; if Phase 0 named it `caplog_structlog` instead, use that. Do not invent a new capture mechanism.
- **The ADR-0004 rejection test in this file is the "Step 2 minimum."** Step 3's `test_node_manifest_*` and Step 4's three probes each contribute their own rejection tests; in aggregate the cross-cutting concern §"`additionalProperties: false`" is satisfied. This story carries only the `node_build_system` rejection.
- **No mutation testing or coverage threshold check** lives here. Per the manifest, coverage is reported in PR bodies (cross-cutting concern #6) and ratcheted to 90/80 in S6-02. This story just needs to pass.
