# Story S4-01 — `LanguageDetectionProbe` + registration

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready
**Effort:** S
**Depends on:** S3-05
**ADRs honored:** ADR-0007, ADR-0010, ADR-0013, ADR-0008

## Context

This is the first concrete probe in the system and the prelude-pass anchor — its `schema_slice` is what every other probe in Phase 1 will read off `enriched_snapshot.detected_languages` (Gap 4 in the architecture). It also pins the structural property that makes the bullet tracer's load-bearing cache-hit test work: `declared_inputs` is scoped to language-extension globs, not `["**/*"]`, so editing `README.md` between two gathers must not invalidate the cache.

This story is the first time the harness internals built in Step 3 receive a real subclass of `Probe`. It's the smallest possible end of the vertical slice; the CLI (S4-02) wires it into the runtime path.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Probe + Registry` — `default_registry` and `@register_probe` shape.
  - `../phase-arch-design.md §Scenarios — Scenario 1: Cold gather over a JS fixture` — the runtime path this probe participates in.
  - `../phase-arch-design.md §Scenarios — Scenario 2: Warm gather (cache hit, the bullet tracer's load-bearing exit)` — why `declared_inputs` is extension-scoped, not `["**/*"]`.
  - `../phase-arch-design.md §Edge cases` — row 1 (PermissionError mid-walk → `confidence="low"`) and row 4 (symlink resolving outside repo root → skip + `probe.symlink.escaped`).
  - `../phase-arch-design.md §Gap analysis — Gap 4` — `tier="base"` engages the coordinator prelude pass.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — must subclass the frozen `Probe` ABC from `probes/base.py` without altering it.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `schema_slice` values must be JSON-representable; the validator runs in the coordinator after this probe returns.
  - `../ADRs/0013-layered-additional-properties-schema.md` — ADR-0013 — emit only fields the per-probe sub-schema accepts; new top-level fields under `language_stack` require a sub-schema edit.
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — paths emitted from this probe go through the sanitizer; emit short relative names where possible.
- **Source design:**
  - `../../../localv2.md §4` — `Probe` ABC, `ProbeOutput` dataclass.
  - `../../../localv2.md §5.1 A1` — `LanguageDetection` probe inventory entry (Phase 0 ships extension-counting only; no tree-sitter).
- **Existing code:**
  - `src/codegenie/probes/base.py` — the frozen ABC this probe subclasses.
  - `src/codegenie/probes/__init__.py` — register the probe here.
  - `src/codegenie/probes/registry.py` — `@register_probe` decorator.
  - `src/codegenie/schema/probes/language_detection.schema.json` — the sub-schema this probe's output must conform to (already on disk from S2-05).

## Goal

`from codegenie.probes import default_registry; default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))` returns a tuple containing `LanguageDetectionProbe`, and instantiating + running it against `tests/fixtures/js_only/` produces a `ProbeOutput` whose `schema_slice == {"language_stack": {"counts": {"javascript": 5}, "primary": "javascript"}}`.

## Acceptance criteria

- [ ] `src/codegenie/probes/language_detection.py` defines `class LanguageDetectionProbe(Probe)` with `name="language_detection"`, `version="0.1.0"`, `tier="base"`, `applies_to_tasks=["*"]`, `applies_to_languages=["*"]`, and `declared_inputs` listing the language-extension globs `[".js", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".go", ".rs", ".java", ".rb", ".php"]` (or the equivalent `**/*.<ext>` glob form the registry consumes) — **not** `["**/*"]`.
- [ ] `LanguageDetectionProbe.run(snapshot, ctx)` returns a `ProbeOutput` whose `schema_slice == {"language_stack": {"counts": {<lang>: <int>, ...}, "primary": <lang-with-max-count-or-None>}}` and whose `confidence == "high"` on the happy path.
- [ ] `src/codegenie/probes/__init__.py` imports `LanguageDetectionProbe` so it is registered at package import time; `default_registry.all_probes()` includes it.
- [ ] Symlinks whose `Path.resolve()` lands outside the analyzed-repo root are skipped; a `probe.symlink.escaped` structlog event is emitted with the offending path (sanitized).
- [ ] `PermissionError` raised mid-walk is caught and the probe returns `ProbeOutput(errors=["PermissionError: ..."], confidence="low")` (edge case #1) — the probe never re-raises a non-`CodegenieError`.
- [ ] A Pydantic validation test (per ADR-0010) asserts that the probe's `schema_slice` passes `_ProbeOutputValidator` (no `bytes`, no `Callable`, no secret-shaped keys, `confidence` is one of the three literals).
- [ ] A probe-contract-conformance test (per ADR-0007) asserts `LanguageDetectionProbe` is a `Probe` subclass and exposes every class attribute the frozen ABC declares (`name`, `version`, `declared_inputs`, `tier`, `applies_to_tasks`, `applies_to_languages`, `timeout_seconds`, etc.) without overriding the ABC's method signatures.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/language_detection.py`, and `pytest tests/unit/test_language_detection_probe.py` all pass.

## Implementation outline

1. Subclass `Probe` from `probes/base.py`; declare class attributes per acceptance criteria.
2. Implement the walker using `os.scandir` (synchronous; bounded by the coordinator's `wait_for`). For each entry: skip if `is_symlink()` and `Path.resolve()` is not under `snapshot.root`; recurse into directories; for files, take the suffix, map to a canonical language name via a small dict (`.js`/`.mjs`/`.cjs` → `"javascript"`; `.ts`/`.tsx` → `"typescript"`; `.py` → `"python"`; `.go` → `"go"`; `.rs` → `"rust"`; `.java` → `"java"`; `.rb` → `"ruby"`; `.php` → `"php"`), increment a counter.
3. Build `schema_slice = {"language_stack": {"counts": dict(counts), "primary": max-by-count-or-None}}`. Tie-break for `primary` deterministically (sorted alpha so the same fixture always picks the same primary).
4. Wrap the walk in try/except for `PermissionError` and `OSError`; collect into `errors=[...]`; set `confidence="low"` on any error.
5. Emit `probe.start` / `probe.success` / `probe.failure` structlog events (per `logging.py` constants).
6. Register the probe via the `@register_probe` decorator and the explicit import in `probes/__init__.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_language_detection_probe.py`

The story has three distinct behaviors to anchor; write one red test per behavior.

```python
# tests/unit/test_language_detection_probe.py

def test_language_detection_probe_counts_js_fixture(tmp_path):
    # arrange: a synthetic mini-fixture with 2 .js, 1 .ts, 1 .py
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "b.js").write_text("//")
    (tmp_path / "c.ts").write_text("//")
    (tmp_path / "d.py").write_text("#")
    # act
    from codegenie.probes.language_detection import LanguageDetectionProbe
    probe = LanguageDetectionProbe()
    snapshot = _snapshot_from(tmp_path)  # helper builds a minimal RepoSnapshot
    ctx = _context_for(tmp_path)         # helper builds a ProbeContext
    output = asyncio.run(probe.run(snapshot, ctx))
    # assert
    assert output.schema_slice == {
        "language_stack": {
            "counts": {"javascript": 2, "typescript": 1, "python": 1},
            "primary": "javascript",
        }
    }
    assert output.confidence == "high"
    assert output.errors == []


def test_probe_output_passes_pydantic_validator(tmp_path):
    # arrange + act: run the probe on a JS fixture
    output = _run_probe(tmp_path_with_js_files)
    # assert: the coordinator's Pydantic validator accepts the slice
    from codegenie.coordinator.validator import _ProbeOutputValidator
    _ProbeOutputValidator(
        schema_slice=output.schema_slice,
        confidence=output.confidence,
    )  # does not raise


def test_probe_contract_conformance():
    # arrange: import the probe and the frozen ABC
    from codegenie.probes.base import Probe
    from codegenie.probes.language_detection import LanguageDetectionProbe
    # assert: subclass + every contract attribute present
    assert issubclass(LanguageDetectionProbe, Probe)
    for attr in ("name", "version", "declared_inputs", "tier",
                 "applies_to_tasks", "applies_to_languages"):
        assert hasattr(LanguageDetectionProbe, attr), f"missing: {attr}"
    assert LanguageDetectionProbe.tier == "base"
    assert LanguageDetectionProbe.declared_inputs != ["**/*"]  # the bullet tracer load-bearing scope
```

The first test must fail with `ModuleNotFoundError: No module named 'codegenie.probes.language_detection'`. The second and third inherit the same failure. Run them, confirm red, commit, then implement.

### Green — make it pass

Add `src/codegenie/probes/language_detection.py` with:

- A `LanguageDetectionProbe(Probe)` subclass with the class attributes from acceptance criteria.
- An `async def run(self, snapshot, ctx) -> ProbeOutput` doing the `os.scandir` walk.
- An extension-to-language map at module scope (private).

Add the explicit import to `src/codegenie/probes/__init__.py`. No try/except polish, no logging, no symlink check yet — just enough to make the three red tests pass.

### Refactor — clean up

After green:

- Type hints throughout (`mypy --strict` clean).
- Docstring on `LanguageDetectionProbe` explaining the prelude-pass role and the extension-scoping rationale.
- Add the symlink-escape skip + `probe.symlink.escaped` event emit; add a unit test (`test_symlink_skipped`).
- Add the `PermissionError` mid-walk catch + `confidence="low"` path; add a unit test (`test_permission_error_demotes_confidence`).
- Add the deterministic `primary` tie-break (sorted alpha within max-count set).
- Confirm `mypy --strict` clean on the module.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/language_detection.py` | New file — implements `LanguageDetectionProbe` per ADR-0007 / ADR-0010 |
| `src/codegenie/probes/__init__.py` | Add explicit `from .language_detection import LanguageDetectionProbe` so registration fires |
| `tests/unit/test_language_detection_probe.py` | New test — three red tests anchoring counts, Pydantic validation, contract conformance |

## Out of scope

- **CLI wiring (`codegenie gather` invocation)** — handled by story S4-02.
- **End-to-end smoke / cache-hit-on-second-run test** — handled by story S4-04.
- **Golden-output assertions against `tests/fixtures/js_only/`, `polyglot/`, `empty_repo/`** — handled by S4-04 (which also creates the fixtures).
- **`tree-sitter` invocation for ambiguous extensions** — Phase 1's richer A1 probe per `../phase-arch-design.md §Non-goals` item 2.
- **`Dockerfile` detection** — Phase 7; explicitly out of scope per `../phase-arch-design.md §Non-goals` item 3.
- **`declared_resource_budget` field** — added in S3-05 on the base class with a default; this probe inherits the default and does not override.

## Notes for the implementer

- `declared_inputs` being extension-scoped (not `["**/*"]`) is **load-bearing for the cache-hit-on-second-run test in S4-04**. If you set it to `["**/*"]` the second-run cache will invalidate on any file change in the fixture (including the `README.md` edit S4-04 performs as a deliberate test) and the bullet tracer's load-bearing exit criterion fails. Re-read `../phase-arch-design.md §Scenarios — Scenario 2` if in doubt.
- The probe's walker must call `os.scandir` directly (not `pathlib.Path.glob`) — S4-04 monkeypatches `os.scandir` at the `codegenie.probes.language_detection` module level to assert zero invocations on the cache-hit path. If you import `from os import scandir` and use the bare name, the monkeypatch still works (it sets `codegenie.probes.language_detection.scandir`); if you use `os.scandir(...)`, monkeypatch via `codegenie.probes.language_detection.os.scandir`. Pick one and document it in the module docstring so S4-04 patches the right name.
- Symlink-escape check: `entry.is_symlink() and Path(entry.path).resolve().is_relative_to(snapshot.root.resolve())` — the latter is Python 3.9+. Skip the entry on `False`; emit the structlog event with the entry's path *relative to repo root* (the sanitizer would scrub it anyway, but emit a clean value at logging time).
- `tier="base"` engages the coordinator prelude pass (Gap 4). Do not set `requires=[...]` on this probe; it's the prelude, not a downstream consumer.
- The `_ProbeOutputValidator` (per ADR-0010) is what enforces "no `bytes` / `Callable` / `Any`" — your `schema_slice` is plain `dict[str, dict[str, ...]]` of JSON-representable values. Don't smuggle a `Path` object; convert to `str` first.
- The contract-conformance test (per ADR-0007) checks structural attributes only — it does **not** re-run the snapshot test (`tests/unit/test_probe_contract.py` already does that). Don't duplicate the fingerprint check here.
