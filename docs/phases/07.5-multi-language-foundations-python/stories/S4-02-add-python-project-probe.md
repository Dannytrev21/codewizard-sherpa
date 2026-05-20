# Story S4-02 — Add `PythonProjectProbe` (`tier="base"` prelude)

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0004, ADR-0007

## Context
Python detection must reach the coordinator's dispatch waves without a new pre-pass: ADR-0004 killed the `LanguageDetectionPrepass` (it had a temporal-ordering bug — it read a probe output before any probe ran) and decided detection is a `tier="base"` probe running in the *existing* prelude wave. `PythonProjectProbe` is that probe — it walks the tree and enriches `RepoSnapshot.detected_languages` for Python, so the existing `language_filter._admits_languages` predicate can later admit or filter the `tier="task_specific"` Python probes with zero new dispatch code.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — `PythonProjectProbe` is `tier="base"`, runs in the prelude wave, enriches `detected_languages`.
- **Architecture:** `../phase-arch-design.md §Control flow` — happy path: the prelude wave runs `LanguageDetectionProbe` + `PythonProjectProbe`; the rest wave is filtered by `language_filter._admits_languages`.
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 1–3 — polyglot repo, bare `*.py` tree, planted `pyproject.toml`.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — detection IS a probe in the prelude wave; no coordinator edit, no pre-pass.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — parse-only, hard caps before parse, functional core / imperative shell.
- **Production ADRs:** `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — the frozen two-arg `run(self, repo, ctx)` `Probe` ABC, consumed unchanged.
- **Existing code:** `src/codegenie/probes/base.py` — the frozen `Probe` ABC (`name`, `layer`, `tier`, `applies_to_languages`, `declared_inputs`, `run`).
- **Existing code:** `src/codegenie/probes/language_detection.py` — the precedent `tier="base"` prelude probe: `os.scandir` walk, `_SKIP_DIRS` deny-list, `counts` cast to plain `dict`, module-scope `_log`, `_WARNING_IDS`/`_ERRORS` import-time validation.
- **Existing code:** `src/codegenie/probes/__init__.py` — the explicit-import collection point; a new probe = new module + one additive import line.
- **Existing code:** `src/codegenie/languages/markers.py` (lands S1-05) — `LANGUAGE_MARKERS[Language("python")]` is the marker source the probe should consult (read-only by import).

## Goal
Land `PythonProjectProbe` as a `tier="base"` prelude probe that walks the snapshot and enriches `detected_languages` with a Python count.

## Acceptance criteria
- [ ] A red test asserts that running `PythonProjectProbe` against an in-memory fixture with `*.py` files / a `pyproject.toml` produces a slice that contributes a non-zero Python signal to `detected_languages`; it fails before the probe exists.
- [ ] `PythonProjectProbe` declares `layer="A"`, `tier="base"`, the frozen two-arg `run(self, repo, ctx)` signature, and tight `declared_inputs` globs (`pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile*`, `**/*.py`).
- [ ] The probe is registered via `@register_probe` and added to `codegenie/probes/__init__.py` with one additive import line; `tests/unit/test_probe_contract.py` stays green (frozen ABC unedited).
- [ ] A Node-only fixture yields no Python signal — the probe does not over-detect; a polyglot fixture yields *both* a Node and a Python signal (monotone / additive detection).
- [ ] `_WARNING_IDS` is a module-level `Final[frozenset[str]]` validated at import against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; the probe never crashes on a malformed input — it records a structured-error slice.
- [ ] The structural fences stay green (`tests/fence/` probe-context conformance + cold-start + no-probe-errors); `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/probes/python/__init__.py` (empty package marker) and `src/codegenie/probes/python/project.py`.
2. Implement `PythonProjectProbe(Probe)` — pure helper functions for the marker/extension scan; `run()` is the only impure surface and only *reads*.
3. Reuse the `os.scandir` walk + `_SKIP_DIRS` idiom from `language_detection.py`; count `.py` files and detect Python markers via `LANGUAGE_MARKERS[Language("python")]`.
4. Emit a `schema_slice` enriching the prelude-wave `detected_languages` with a `python` entry (mirror the `language_detection` slice shape conventions).
5. Declare `_WARNING_IDS` (`Final[frozenset[str]]`) and validate it at import time with `raise AssertionError(...)`.
6. Decorate with `@register_probe` and add the import line to `codegenie/probes/__init__.py`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/probes/python/test_python_project_probe.py`.
Test name: `test_python_project_probe_enriches_detected_languages`.
```python
async def test_python_project_probe_enriches_detected_languages(tmp_path) -> None:
    # arrange: build an in-memory/tmp RepoSnapshot with a pyproject.toml and two *.py files.
    # act: await PythonProjectProbe().run(repo, ctx).
    # assert: the ProbeOutput.schema_slice contributes a non-zero "python" count toward
    #         detected_languages; tier == "base"; the probe did not raise.
```
Also `test_python_project_probe_does_not_over_detect_node` — a Node-only fixture yields zero Python signal. Both fail today: the probe does not exist.

### Green — make it pass
Smallest probe: a `tier="base"` `Probe` subclass whose `run` walks the snapshot path index (no parsing — a marker/extension scan only), counts `.py` files, and emits the enrichment slice. No build-system or manifest parsing here — that is S4-04 / S4-05.

### Refactor — clean up
Extract the scan into pure helpers; add type hints and a module docstring tracing to ADR-0004; wire `_WARNING_IDS`; confirm `declared_inputs` globs are tight enough that editing a Python file invalidates only Python probes' cache. Confirm the structural fences stay green after the new submodule lands.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/probes/python/__init__.py` | New probe sub-package marker. |
| `src/codegenie/probes/python/project.py` | `PythonProjectProbe` implementation. |
| `src/codegenie/probes/__init__.py` | One additive import line registering the probe. |
| `tests/unit/probes/python/test_python_project_probe.py` | The red test + over-detection / polyglot cases. |

## Out of scope
- Build-system, manifest, and import-graph probes — S4-04, S4-05, S4-07.
- The `ProjectDetector` object (the `Protocol` implementation) — S4-03. This story is the *probe*; S4-03 is the *detector*. They are distinct per ADR-0004 / ADR-0005.
- Fanning the probe out via `register_language` — that happens when `PYTHON_PACK` is constructed in S7-01.
- The Python probe sub-schema — S4-08.

## Notes for the implementer
- `PythonProjectProbe` must be `tier="base"` — the `language_filter` predicate explicitly yields `False` for any language-filtered probe when `detected_languages` is empty (the pre-prelude case), so detection cannot be `tier="task_specific"` or it would filter itself out.
- This is the *probe*, not the `ProjectDetector` Protocol object — do not conflate them. The probe enriches `detected_languages`; the S4-03 detector returns a `DetectionResult` sum type. They share `LANGUAGE_MARKERS` as data but are separate code.
- Detection is monotone — never demote another language's verdict; a polyglot repo must surface *both* signals (edge case #1).
- Reuse the `os.scandir`-not-`Path.glob` discipline from `language_detection.py` so vendor-dir skipping happens before recursion and the walk stays test-monkeypatchable.
- This probe does no tree-sitter parsing — it is a marker/extension scan. Keep `tree_sitter_python` out of its import path so a Node-only gather never imports it (the G11 `sys.modules` fence depends on this).
