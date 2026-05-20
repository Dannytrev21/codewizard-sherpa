# Story S4-05 — Add `PythonManifestProbe` with hard caps

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0004, ADR-0007

## Context
The Python manifest surface (`pyproject.toml`'s `[project]` table — name, version, declared dependencies) crosses the untrusted-repo trust boundary, and a 200 MB or billion-laughs file can OOM or hang the gather. `PythonManifestProbe` is the `task_specific` Layer A analog of `NodeManifestProbe`: it parses `pyproject.toml` under byte/depth/timeout caps applied *before* parse, reusing the Phase 1 `SizeCapExceeded`/`DepthCapExceeded` machinery, and returns an honest `confidence="low"` partial fact when a cap fires. ADR-0007 is the governing contract.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — `PythonManifestProbe` is `tier="task_specific"`, `applies_to_languages=["python"]`; hard caps before parse; `_WARNING_IDS` (`python.manifest_oversized`, `python.lockfile_truncated`).
- **Architecture:** `../phase-arch-design.md §Edge cases` row 4 — 200 MB / billion-laughs lockfile rejected before parse with a structured warning.
- **Architecture:** `../phase-arch-design.md §Control flow` decision point 5 — cap exceeded → partial fact, `confidence="low"`, `_WARNING_IDS` entry.
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — parse-only, byte/depth/timeout caps before parse, capped probe returns `confidence="low"`, reuses Phase 1 cap machinery.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — `task_specific` probes admitted by `language_filter`.
- **Existing code:** `src/codegenie/probes/node_manifest.py` — the precedent manifest probe; `_PARSE_MAX_BYTES`/`_PARSE_MAX_DEPTH` `Final` caps, the parse-after-cap-check pattern, `_WARNING_IDS`/`_ERRORS` discipline, ADR-0007 ID pattern at the catch site.
- **Existing code:** `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`, `MalformedJSONError` — reused verbatim.
- **Existing code:** `src/codegenie/probes/base.py` — frozen `Probe` ABC, `ProbeOutput` (`schema_slice`, `errors`, `confidence`).
- **Existing code:** `tomllib` (stdlib) — `pyproject.toml` parsing; cap bytes and depth before `tomllib.loads`.

## Goal
Land `PythonManifestProbe` — a `task_specific` Layer A probe that parses `pyproject.toml` `[project]` metadata under byte/depth/timeout caps applied before parse.

## Acceptance criteria
- [ ] A red test asserts the probe extracts `[project].name`/`version`/`dependencies` from a valid `pyproject.toml` fixture into a structured slice; it fails before the probe exists.
- [ ] `PythonManifestProbe` declares `layer="A"`, `tier="task_specific"`, `applies_to_languages=["python"]`, the frozen two-arg `run(self, repo, ctx)`, and tight `declared_inputs` (`pyproject.toml`, `requirements*.txt`, `Pipfile*`, `*.lock`).
- [ ] An oversized (>5 MiB) `pyproject.toml` and a billion-laughs deeply-nested TOML are rejected **before** parse — `SizeCapExceeded` / `DepthCapExceeded` caught, a `python.manifest_oversized` / `python.lockfile_truncated` warning emitted, a `confidence="low"` partial fact returned; no OOM, no hang.
- [ ] A malformed `pyproject.toml` and a missing manifest each yield a structured-error / honest-low slice — the probe never crashes.
- [ ] `_WARNING_IDS` (`Final[frozenset[str]]`) is validated at import against `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; the probe is `@register_probe`-decorated and added to `codegenie/probes/__init__.py` with one import line; `tests/unit/test_probe_contract.py` + `tests/fence/` stay green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/probes/python/manifest.py`.
2. Define `Final` cap constants (`_PARSE_MAX_BYTES`, `_PARSE_MAX_DEPTH`) mirroring `node_manifest.py`.
3. Implement `PythonManifestProbe(Probe)` — pure helpers for `[project]`-table extraction; `run()` reads `pyproject.toml`, applies the byte cap and a depth cap *before* `tomllib.loads`, then extracts name/version/dependencies.
4. On `SizeCapExceeded`/`DepthCapExceeded`/`MalformedJSONError`/`SymlinkRefusedError`, catch the typed exception, emit the ADR-0007-pattern warning/error ID, and return a `confidence="low"` partial slice.
5. Declare `_WARNING_IDS`, validate at import, `@register_probe`, add the import line.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/probes/python/test_python_manifest_probe.py`.
Test name: `test_python_manifest_probe_extracts_project_metadata`.
```python
async def test_python_manifest_probe_extracts_project_metadata(tmp_path) -> None:
    # arrange: a RepoSnapshot with a valid pyproject.toml [project] table
    #          (name, version, dependencies = ["requests>=2.0"]).
    # act: await PythonManifestProbe().run(repo, ctx).
    # assert: the slice carries name/version and the declared dependency list; confidence == "high".
```
Also `test_python_manifest_probe_rejects_oversized_before_parse` — a >5 MiB `pyproject.toml` → `SizeCapExceeded` caught, `python.manifest_oversized` warning, `confidence="low"`, no exception escapes. Both fail today.

### Green — make it pass
Smallest probe: a `task_specific` `Probe` that byte-caps and depth-caps then `tomllib.loads` the `pyproject.toml`, extracts the `[project]` table, and emits a slice. Caps before parse; typed-exception catch returns the honest-low partial fact.

### Refactor — clean up
Extract the `[project]`-table extraction into pure helpers. Add type hints, a docstring tracing ADR-0007, and confirm the depth cap fires on a billion-laughs input *before* full materialization. Keep the catch-site ID construction matching `node_manifest.py`'s `_error_id` discipline.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/probes/python/manifest.py` | `PythonManifestProbe` implementation. |
| `src/codegenie/probes/__init__.py` | One additive import line registering the probe. |
| `tests/unit/probes/python/test_python_manifest_probe.py` | The red test + oversized / billion-laughs / malformed cases. |

## Out of scope
- Structural `setup.py`/`setup.cfg` parsing — S4-06 (this probe parses `pyproject.toml`; `setup.py` is S4-06's territory).
- Dep-graph resolution from `requirements.txt`/`poetry.lock`/`uv.lock` — Step 5 (`PythonManifestProbe` extracts *declared* manifest metadata, not the resolved graph).
- The Python manifest sub-schema — S4-08 (it depends on this story's slice shape).
- The import-graph probe — S4-07.

## Notes for the implementer
- The byte cap **and** the depth cap must precede `tomllib.loads` — a billion-laughs TOML is defeated by the depth cap, an oversized file by the byte cap; both checks come *before* the parser sees the bytes (ADR-0007 edge case #4).
- Reuse `SizeCapExceeded` / `DepthCapExceeded` from `codegenie.errors` — do not invent a new cap class (ADR-0007: inherit the Phase 1 tested boundary).
- A capped probe returns an honest `confidence="low"` partial fact with a `_WARNING_IDS` entry — never a crash, never a silent omission (honest-confidence, commitment 3).
- This story's slice shape is the contract S4-08's sub-schema pins — keep the slice shape deliberate and stable; do not let it drift after S4-08 lands.
- `tier="task_specific"` + `applies_to_languages=["python"]` is mandatory — without it the probe runs on every repo and the `language_filter` cannot gate it.
