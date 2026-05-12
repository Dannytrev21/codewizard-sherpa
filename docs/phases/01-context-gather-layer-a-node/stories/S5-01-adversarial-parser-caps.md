# Story S5-01 — Parser-cap adversarial corpus: billion-laughs, JSON bombs, oversized lockfile

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** M
**Depends on:** S2-05
**ADRs honored:** ADR-0008 (in-process parse caps, no per-probe sandbox), ADR-0009 (no new C-extension parser dependencies)

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

- [ ] `tests/adv/test_yaml_billion_laughs.py` builds (at test-fixture setup time, not checked in) a `pnpm-lock.yaml` with billion-laughs anchor expansion and asserts `safe_yaml.load(...)` raises `DepthCapExceeded` from `codegenie.errors`; asserts the exception's `path` attribute is the offending file and a depth field is recorded; running `codegenie gather` on a repo containing the file exits 0 (gather degrades, not crashes) with `confidence: "low"` and a `pnpm_lock.depth_cap_exceeded` warning in the `node_manifest` slice (per `phase-arch-design.md §"Edge cases"` row 1).
- [ ] `tests/adv/test_json_bomb_deep_nesting.py` builds a `package.json` whose value is 10,000 nested objects (constructed via a Python loop, not a checked-in 10 MB file) and asserts `safe_json.load(...)` raises `DepthCapExceeded`; asserts that running `codegenie gather` exits 0 and the `language_stack` / `node_manifest` slices both record `confidence: "low"` with a `package_json.depth_cap_exceeded` warning.
- [ ] `tests/adv/test_json_bomb_huge_string.py` builds a `package.json` containing a single 600 MB string value at the **test fixture-setup phase** (`tmp_path` + `f.write` in chunks; never under `tests/fixtures/` or `tests/adv/data/`) and asserts `safe_json.load(...)` raises `SizeCapExceeded` **before** `json.loads` is called (assert via mock or side-channel that `json.loads` was not invoked); asserts the typed exception is raised from `safe_json`, not from `json`.
- [ ] `tests/adv/test_oversized_lockfile.py` builds a 60 MB `pnpm-lock.yaml` and asserts `safe_yaml.load(...)` raises `SizeCapExceeded` pre-parse; running `codegenie gather` exits 0 and `node_manifest.confidence == "low"` with a `pnpm_lock.size_cap_exceeded` warning.
- [ ] All four tests are marked with a `pytest.mark.adv` marker (registered in `pyproject.toml` under `[tool.pytest.ini_options] markers`) so CI can select them with `pytest -m adv`.
- [ ] All four tests use `tmp_path` for fixture generation and clean up automatically; no synthesised file is left on disk after the test.
- [ ] `pytest tests/adv/test_yaml_billion_laughs.py tests/adv/test_json_bomb_deep_nesting.py tests/adv/test_json_bomb_huge_string.py tests/adv/test_oversized_lockfile.py` completes in under 15 s on the developer's machine; the slowest test (`test_json_bomb_huge_string`) caps under 10 s.
- [ ] `probe.parser.cap_exceeded` structlog event is emitted (from `logging.py` constants, registered in S1-10) and at least one test asserts the event was logged with `parser_kind` set correctly (`safe_json` or `safe_yaml`).

## Implementation outline

1. **Register the `adv` pytest marker** in `pyproject.toml` (idempotent — if Phase 0 already registered it, skip; otherwise add under `[tool.pytest.ini_options].markers`). This lets CI filter the corpus.
2. **`tests/adv/test_yaml_billion_laughs.py`:** synthesize the billion-laughs YAML (`&a [&b [&c [...]]]`) into `tmp_path / "pnpm-lock.yaml"`; first call `safe_yaml.load(...)` directly and `pytest.raises(DepthCapExceeded)`; then run the CLI end-to-end against the surrounding fixture (synthesize a minimal `package.json` next to it) and assert exit 0 + the `node_manifest` slice's `confidence` and warning ID.
3. **`tests/adv/test_json_bomb_deep_nesting.py`:** build a Python `dict` with 10,000 nested keys (`"a": {"a": {"a": ...}}`), `json.dumps` it, write to `tmp_path / "package.json"`; `pytest.raises(DepthCapExceeded)` on `safe_json.load(...)`; assert the **post-parse depth walker** is what raised (not size cap) by checking the file size is under 5 MB.
4. **`tests/adv/test_json_bomb_huge_string.py`:** write a 600 MB single-string `package.json` to `tmp_path` in 1 MB chunks (`f.write('a' * 1024 * 1024)` × 600 inside an opening / closing `{"name": "...."}` skeleton); patch `json.loads` to raise a sentinel `RuntimeError` and assert `pytest.raises(SizeCapExceeded)` — the test fails if `json.loads` is reached, proving the size check is pre-parse.
5. **`tests/adv/test_oversized_lockfile.py`:** write 60 MB of `# pad\n` to `tmp_path / "pnpm-lock.yaml"`; `pytest.raises(SizeCapExceeded)` on `safe_yaml.load(...)`; run CLI; assert exit 0 + the lockfile-specific warning ID.
6. **Add a shared helper** at `tests/adv/_helpers.py` (only if it doesn't already exist from Phase 0) for the "synthesize minimal Node repo around a hostile file" pattern, used by tests #1 and #4 to exercise the CLI end-to-end path.
7. **Structlog assertion:** at least one of the four tests installs a `structlog` capture (Phase 0 fixture pattern; see existing Phase 0 tests for the helper name) and asserts the `probe.parser.cap_exceeded` event was emitted with `parser_kind="safe_yaml"` (test #1) or `parser_kind="safe_json"` (test #2).

## TDD plan — red / green / refactor

### Red — write the failing test first

Write tests #1 and #2 first (smallest, fastest); tests #3 and #4 last (largest fixtures, slowest). One file per test; commit each red separately.

```python
# tests/adv/test_yaml_billion_laughs.py
from __future__ import annotations

import pytest

from codegenie.errors import DepthCapExceeded
from codegenie.parsers import safe_yaml


def _billion_laughs_yaml(depth: int) -> bytes:
    # &a [&b [&c [...]]] — depth-d nesting via YAML anchors
    body = "x"
    for i in range(depth, 0, -1):
        body = f"[&{chr(96 + (i % 26) + 1)} {body}]"
    return f"lockfileVersion: '6.0'\nanchors: {body}\n".encode()


def test_billion_laughs_pnpm_lock_raises_depth_cap(tmp_path):
    f = tmp_path / "pnpm-lock.yaml"
    f.write_bytes(_billion_laughs_yaml(depth=200))
    with pytest.raises(DepthCapExceeded) as exc:
        safe_yaml.load(f)
    assert str(f) in str(exc.value)


def test_billion_laughs_under_gather_exits_zero_with_low_confidence(tmp_path, run_gather):
    # run_gather is a Phase-0 helper fixture that invokes the CLI and returns parsed output
    (tmp_path / "package.json").write_text('{"name": "x", "version": "0.0.0"}')
    (tmp_path / "pnpm-lock.yaml").write_bytes(_billion_laughs_yaml(depth=200))
    result = run_gather(tmp_path)
    assert result.exit_code == 0
    manifests = result.context["probes"]["node_manifest"]
    assert manifests["confidence"] == "low"
    assert "pnpm_lock.depth_cap_exceeded" in manifests["warnings"]
```

The first call to `safe_yaml.load` must already raise `DepthCapExceeded` (the parser was built in S1-03). The CLI-level test is the new red.

For `test_json_bomb_huge_string`, the load-bearing red is: patching `json.loads` to raise must **not** be reached. Write the test, watch it pass only because `SizeCapExceeded` fires first; if you ever break the pre-parse size check, the test will fail with the sentinel `RuntimeError` instead — that's the canary.

```python
# tests/adv/test_json_bomb_huge_string.py
from unittest.mock import patch

import pytest

from codegenie.errors import SizeCapExceeded
from codegenie.parsers import safe_json


def test_huge_string_package_json_size_cap_pre_parse(tmp_path):
    f = tmp_path / "package.json"
    with f.open("wb") as out:
        out.write(b'{"name": "')
        for _ in range(600):
            out.write(b"a" * (1024 * 1024))
        out.write(b'"}')

    # If safe_json fails to size-check pre-parse, json.loads is reached and our
    # sentinel raises — the test fails with RuntimeError instead of SizeCapExceeded.
    with patch("json.loads", side_effect=RuntimeError("json.loads must not be reached")):
        with pytest.raises(SizeCapExceeded):
            safe_json.load(f)
```

Run each red, confirm specific exception (`pytest --tb=short` shows `DepthCapExceeded` / `SizeCapExceeded` is what fired), commit.

### Green — make it pass

Step 1 parsers already implement the caps. If the red tests pass with no new production code, that's the green — Step 5's job is to **assert the structural defense holds**, not to re-implement parsing.

If any test fails because the parser does not enforce the cap, that is a Step-1 regression and must be fixed in `src/codegenie/parsers/safe_json.py` / `safe_yaml.py`. Surface the fix in this PR with an explicit "S1-02/S1-03 follow-up" note in the PR body.

The structlog-event assertion is the one production touch this story may need: if the parser raises but doesn't log `probe.parser.cap_exceeded`, add the `logger.warning(...)` call inside the parser. That's still a Step-1 fix surfaced from a Step-5 test (an acceptable retrofit).

### Refactor — clean up

After green:

- Extract the "build minimal Node repo around a hostile file" pattern into `tests/adv/_helpers.py` if both tests #1 and #4 grow duplicated boilerplate.
- Confirm fixture cleanup: `tmp_path` is automatically cleaned by pytest, but the 600 MB file consumes disk during the test — verify `pytest --basetemp=$(mktemp -d)` does not exhaust CI runner disk by checking the test's peak disk footprint locally with `du -h $TMPDIR/pytest-of-*`.
- Add a one-line module docstring to each test file pointing to `phase-arch-design.md §"Adversarial tests"` for context (helps future contributors understand why the test exists).
- Confirm `mypy --strict` is clean (these are tests; mypy on tests is best-effort, but the helpers should be typed).

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_yaml_billion_laughs.py` | New test file — billion-laughs YAML → `DepthCapExceeded` |
| `tests/adv/test_json_bomb_deep_nesting.py` | New test file — 10k-nested JSON → `DepthCapExceeded` |
| `tests/adv/test_json_bomb_huge_string.py` | New test file — 600 MB string → `SizeCapExceeded` pre-parse |
| `tests/adv/test_oversized_lockfile.py` | New test file — 60 MB YAML → `SizeCapExceeded` |
| `tests/adv/_helpers.py` | Optional new helper for "minimal Node repo around hostile file" |
| `pyproject.toml` | Register `adv` pytest marker (idempotent, only if not already from Phase 0) |

## Out of scope

- **Symlink-escape / zip-slip / pathological `tsconfig` adversarial tests** — owned by S5-03.
- **Yarn regex-DoS / planted `node` shim / `!!python/object` adversarial tests** — owned by S5-02.
- **Adding new parser-cap mechanisms** — Step 1 owns the production caps; this story exercises them.
- **Property-based fuzzing** — explicitly out of Phase 1 (`final-design.md §"Tests explicitly not in Phase 1"` item 6).
- **Real-world hostile-input corpus mining** — Phase 5's trust-gate work.

## Notes for the implementer

- **The "specific exception" requirement is load-bearing.** Asserting `result.exit_code == 0` alone is a false-positive risk: gather might exit 0 because the file was skipped by a different defense (e.g. `O_NOFOLLOW` if the test accidentally wrote a symlink). Always `pytest.raises(SpecificError)` on the direct parser call, and additionally assert the warning ID string in the slice. See `phase-arch-design.md §"Step 5 — Risks"`.
- **600 MB fixture generation must be at test setup, not as a checked-in file.** CI's git checkout would balloon to 600 MB+. Generate inside `tmp_path` and use `f.write(b"a" * (1024 * 1024))` in a loop — single allocation of a 1 MB buffer, repeated 600 times.
- **The `pnpm_lock.depth_cap_exceeded` / `package_json.depth_cap_exceeded` / `pnpm_lock.size_cap_exceeded` warning IDs** are the canonical Phase 1 IDs from `phase-arch-design.md §"Edge cases"` rows 1 and 2. They must match ADR-0007's pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Probes register them in their slice's `warnings: list[str]`.
- **Why `safe_yaml.load` raises `DepthCapExceeded` post-parse, not during parse:** `CSafeLoader` has no native depth cap. The Step 1 design is parse-then-walk. This means the YAML *is* fully constructed in memory before the walker raises — for the billion-laughs test, this means the depth must be tuned so the materialized tree is **small enough to fit in 70 MB RSS** but **deeper than 64** to trigger the post-parse check. The example in the red test uses depth 200 with a one-character leaf — total memory is ~200 dicts. If your test OOMs, you've made the YAML too wide; reduce the breadth.
- **The structlog assertion is your canary for ADR-0007 + Step-1's `probe.parser.cap_exceeded` event** — if the event-name constant is missing from `logging.py`, the test fails with `KeyError` (the structlog capture asserts the event name); that's a signal to retrofit the constant in S1-10's deliverable.
- **CI walltime budget:** the entire adversarial corpus must run in under 30 s p95 (`phase-arch-design.md §"CI gates"`). This story owns 4 of 10 tests; budget yourself ~12 s wall-clock. Test #3 (600 MB write) is the long pole — measure locally with `time pytest tests/adv/test_json_bomb_huge_string.py` and tune the chunk-write loop if it exceeds 8 s.
