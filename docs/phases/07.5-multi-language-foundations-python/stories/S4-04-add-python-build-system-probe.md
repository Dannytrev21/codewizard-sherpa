# Story S4-04 — Add `PythonBuildSystemProbe`

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0004, ADR-0007

## Context
Python's build-backend story is fragmented — setuptools, poetry-core, hatchling, flit, pdm — and a downstream Planner needs the active backend as a *fact*. `PythonBuildSystemProbe` is the `task_specific` Layer A analog of `NodeBuildSystemProbe`: it reads `pyproject.toml`'s `[build-system]` table (and falls back to `setup.py`/`setup.cfg` presence) under hard caps, recording the detected backend without executing anything. ADR-0007 governs it — parse-only, byte/depth/timeout caps before parse, `setup.py` read as text and never executed.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — `PythonBuildSystemProbe` is `tier="task_specific"`, `applies_to_languages=["python"]`; hard caps before parse; functional core / imperative shell.
- **Architecture:** `../phase-arch-design.md §Control flow` decision point 5 — cap exceeded before parse → partial fact, `confidence="low"`, `_WARNING_IDS` entry.
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 4 and 5 — oversized/billion-laughs lockfile rejected pre-parse; hostile `setup.py` read as text never executed.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — parse-only, hard caps before parse, `setup.py` never executed, capped probe returns `confidence="low"`.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — `task_specific` probes are admitted by `language_filter._admits_languages`.
- **Existing code:** `src/codegenie/probes/node_build_system.py` — the precedent build-system probe; `_LOCKFILE_PRECEDENCE`, the `language_filter` admission pattern.
- **Existing code:** `src/codegenie/probes/language_filter.py` — `_admits_languages` predicate the rest-wave dispatch uses.
- **Existing code:** `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`, `MalformedJSONError` — the Phase 1 cap machinery reused verbatim.
- **Existing code:** `src/codegenie/probes/node_manifest.py` lines ~85–110 — `_PARSE_MAX_BYTES` / `_PARSE_MAX_DEPTH` `Final` cap constants and the parse-after-cap-check pattern.
- **Existing code:** `tomllib` (stdlib) — `pyproject.toml` parsing; cap the bytes *before* calling `tomllib.loads`.

## Goal
Land `PythonBuildSystemProbe` — a `task_specific` Layer A probe that detects the active Python build backend from `pyproject.toml` under hard caps, never executing repo code.

## Acceptance criteria
- [ ] A red test asserts the probe identifies the build backend (e.g. `setuptools`, `poetry-core`, `hatchling`) from a `pyproject.toml` `[build-system].build-backend` fixture; it fails before the probe exists.
- [ ] `PythonBuildSystemProbe` declares `layer="A"`, `tier="task_specific"`, `applies_to_languages=["python"]`, the frozen two-arg `run(self, repo, ctx)`, and tight `declared_inputs` (`pyproject.toml`, `setup.py`, `setup.cfg`).
- [ ] The probe enforces a byte cap and a depth cap **before** parsing — an oversized `pyproject.toml` is rejected pre-parse with a structured warning and a `confidence="low"` partial fact; no OOM, no hang.
- [ ] A malformed `pyproject.toml` yields a structured-error slice — the probe never crashes.
- [ ] `_WARNING_IDS` (`Final[frozenset[str]]`) is validated at import against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` and includes `python.manifest_oversized`.
- [ ] The probe is registered via `@register_probe` + one additive import line in `codegenie/probes/__init__.py`; `tests/unit/test_probe_contract.py` and the `tests/fence/` suite stay green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/probes/python/build_system.py`.
2. Define `Final` cap constants (`_PARSE_MAX_BYTES = 5 * 1024 * 1024`, `_PARSE_MAX_DEPTH`) mirroring `node_manifest.py`.
3. Implement `PythonBuildSystemProbe(Probe)` — pure helpers for backend classification; `run()` reads `pyproject.toml`, checks the byte cap *before* `tomllib.loads`, then reads `[build-system].build-backend`.
4. Map the backend string to a typed fact; if no `[build-system]` table, fall back to `setup.py`/`setup.cfg` *presence* (not execution) → `setuptools` legacy backend.
5. On a cap hit or malformed TOML, return a partial fact with `confidence="low"` and the appropriate `_WARNING_IDS` / error ID — never crash.
6. Declare `_WARNING_IDS`, decorate with `@register_probe`, add the import line.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/probes/python/test_python_build_system_probe.py`.
Test name: `test_python_build_system_probe_detects_backend`.
```python
async def test_python_build_system_probe_detects_backend(tmp_path) -> None:
    # arrange: a RepoSnapshot whose pyproject.toml has [build-system] build-backend = "poetry.core.masonry.api".
    # act: await PythonBuildSystemProbe().run(repo, ctx).
    # assert: the slice records the active backend (e.g. "poetry-core"); confidence == "high";
    #         the probe did not raise.
```
Also `test_python_build_system_probe_caps_oversized_pyproject` — an oversized `pyproject.toml` → `confidence="low"` + `python.manifest_oversized` warning, no exception. Both fail today.

### Green — make it pass
Smallest probe: a `task_specific` `Probe` whose `run` byte-caps then `tomllib.loads` the `pyproject.toml`, reads `[build-system].build-backend`, classifies it, and emits a slice. The `setup.py`/`setup.cfg` fallback is presence-only.

### Refactor — clean up
Extract backend classification into a pure helper with a module-level `Final` mapping (Open/Closed — a future backend is one row). Add type hints, a docstring tracing ADR-0007, and confirm the cap check precedes every parse call.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/probes/python/build_system.py` | `PythonBuildSystemProbe` implementation. |
| `src/codegenie/probes/__init__.py` | One additive import line registering the probe. |
| `tests/unit/probes/python/test_python_build_system_probe.py` | The red test + cap / malformed cases. |

## Out of scope
- Parsing `setup.py` *structurally* (tree-sitter) for backend metadata — S4-06. This probe uses `setup.py`/`setup.cfg` **presence only** as a fallback signal.
- The manifest probe (`PythonManifestProbe`) — S4-05.
- The Python build-system sub-schema — S4-08.
- Fanning the probe out via `register_language` — S7-01.

## Notes for the implementer
- The byte cap must be checked **before** `tomllib.loads` — a probe that parses first and caps second defeats the protection (ADR-0007's named failure: "a probe that parses first and caps second").
- `setup.py` is **never executed** here — for this probe, `setup.py`/`setup.cfg` presence alone is the legacy-`setuptools` fallback signal. Structural `setup.py` parsing is S4-06's job, and even there it is read as text only.
- Reuse the Phase 1 `SizeCapExceeded`/`DepthCapExceeded` machinery — do not invent a new cap framework (ADR-0007: the Python probes inherit the tested boundary).
- This is a `task_specific` probe — it must be admitted by `language_filter._admits_languages`, so `applies_to_languages=["python"]` is mandatory; without it the probe would run on every repo.
- A capped or malformed input yields an honest `confidence="low"` partial fact, never a crash — honest-confidence over completeness.
