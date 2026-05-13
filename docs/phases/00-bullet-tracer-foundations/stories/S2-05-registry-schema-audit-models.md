# Story S2-05 — Registry + JSON Schema envelope + audit models

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Done (2026-05-13 — phase-story-executor attempt 1, GREEN)

## Evidence (closed 2026-05-13)

- **Implementation:**
  - [src/codegenie/probes/registry.py](../../../../src/codegenie/probes/registry.py) — `register_probe`, `Registry`, `default_registry`, module-level `_filter` lru_cache helper.
  - [src/codegenie/probes/__init__.py](../../../../src/codegenie/probes/__init__.py) — explicit `from codegenie.probes import base, registry`; commented placeholder for S4-01's `language_detection`.
  - [src/codegenie/schema/__init__.py](../../../../src/codegenie/schema/__init__.py) — package marker.
  - [src/codegenie/schema/repo_context.schema.json](../../../../src/codegenie/schema/repo_context.schema.json) — envelope; `$id` carries `v0.1.0`; root `additionalProperties: false`; `probes.additionalProperties: true`.
  - [src/codegenie/schema/probes/__init__.py](../../../../src/codegenie/schema/probes/__init__.py) — package marker.
  - [src/codegenie/schema/probes/language_detection.schema.json](../../../../src/codegenie/schema/probes/language_detection.schema.json) — first per-probe sub-schema; `$id` carries `language_detection/v0.1.0`; strict at slice.
  - [src/codegenie/schema/validator.py](../../../../src/codegenie/schema/validator.py) — `validate(...)`, cached `_validator()` via `functools.lru_cache(maxsize=1)`, `referencing.Registry` for `$ref` resolution.
  - [src/codegenie/audit.py](../../../../src/codegenie/audit.py) — Pydantic v2 `ProbeExecutionRecord` + `RunRecord` with `frozen=True, extra="forbid"`; `AuditWriter.record` stub raising `NotImplementedError` (S3-06 owns the body).
- **Tests (27 new, all green):**
  - [tests/unit/test_registry.py](../../../../tests/unit/test_registry.py) — 11 tests pinning AC-1, AC-2 (5-row filter matrix), AC-3, AC-4, AC-8 (template existence), AC-9 (decorator return, lru cache hit, empty-language set).
  - [tests/unit/test_schema_validation.py](../../../../tests/unit/test_schema_validation.py) — 10 tests pinning AC-5, AC-6, AC-7, AC-10, AC-13.
  - [tests/unit/test_audit_models.py](../../../../tests/unit/test_audit_models.py) — 6 tests pinning AC-11.
- **Gates (all green):**
  - Full suite: 183 passed (was 156 before this story; 27 new).
  - Coverage: 94.02 % (gate ≥ 85 %); registry/validator at 100 %, audit at 96 % (uncovered line is the deliberate `AuditWriter.record` `NotImplementedError` — S3-06).
  - `ruff check src/ tests/`: clean.
  - `ruff format --check`: clean.
  - `mypy --strict src/`: 16 source files, no issues.
  - `lint-imports --no-cache`: 2 kept, 0 broken.
  - `pre-commit run --all-files`: every hook passes (including mypy in isolated venv after `types-jsonschema` was added to the hook's `additional_dependencies`).
- **Coordinated dep update:** `pyproject.toml` `[dev]` extras + `.pre-commit-config.yaml` mypy hook + `uv.lock` all carry the new `types-jsonschema` stub package (jsonschema is not py.typed).
- **Attempt log:** [`_attempts/S2-05.md`](_attempts/S2-05.md). Cross-story lesson appended to [`_attempts/_lessons.md`](_attempts/_lessons.md) (three-edit rule for new third-party deps; module-level cached helper rule; `referencing.Registry` over deprecated `RefResolver`).

---

**Original status (pre-execution):** Ready (HARDENED)
**Effort:** M
**Depends on:** S2-02, S2-03, S2-04
**ADRs honored:** ADR-0003, ADR-0004, ADR-0007, ADR-0013

## Validation notes

Validated: 2026-05-13
Verdict: HARDENED
Findings addressed: 31 total (4 block, 22 harden, 5 nit/informational)

Changes applied:
- **Context paragraph rewritten** — removed the claim that this story ships `templates/adr-amendment.md`; the template was delivered by S2-02 (commit `1ed09a6`) with the canonical five-step checklist that the snapshot-failure message points at. Coverage F1 + Consistency F1.
- **AC-2 hardened** — pinned a concrete `for_task` filter-matrix table (5 rows: star-on-both, task-mismatch, lang-restricted-vs-unknown, lang-restricted-vs-match, intersection-with-extra-langs) replacing prose-only filter rules. Coverage F3 + Test-Quality F1.
- **AC-7 hardened** — pinned the `RunRecord.os_kernel_sha` field name (Data model is the canonical schema source; arch §Component design's use of `os_kernel` is inconsistent — flagged as a follow-up arch correction). Pinned `Skipped` exit_status sentinel: `blob_sha256=""` per ADR-0004 §Consequences. Coverage F8/F9 + Consistency F2.
- **AC-8 rewritten** — verifies the already-existing `templates/adr-amendment.md` (S2-02 deliverable, five-step checklist) is present; no longer claims this story creates it. Coverage F1 + Consistency F1.
- **AC-9 strengthened** — added: `register_probe(cls) is cls` return-value pin, `_filter.cache_info().hits ≥ 1` lru-cache observability pin, parametrized `for_task` filter matrix replacing the `...` stub. Test-Quality F1/F7/F8.
- **AC-10 strengthened** — added: envelope `$id` contains `v0.1.0`, sub-schema `$id` contains `language_detection/v0.1.0` (ADR-0003 requirement for S3-01's `per_probe_schema_version`), `$ref`-resolution happy-path payload, sub-schema-strictness convention pin. Coverage F6/F7 + Test-Quality F3/F10.
- **AC-11 strengthened** — added: Pydantic `frozen=True` mutation-raises pin, `exit_status` literal-rejection concrete test, `RunRecord` happy-path + `extra="forbid"` rejection, `Skipped` sentinel acceptance. Coverage F12 + Test-Quality F4/F5/F9.
- **AC-13 added (new)** — schema validator `_validator()` lru_cache hit pin (catches the no-cache mutant that costs ~30 ms per validate). Coverage F5 + Test-Quality F2.
- **TDD plan red-section snippets rewritten** — replaced `...  # detail in implementation` stub with concrete `pytest.mark.parametrize` for `for_task`; added cache_info introspection helpers; added `_validator()` cache hit test; added `frozen=True` mutation-raises test; added `register_probe` return-value test; added `$ref` resolution happy-path + invalid-payload tests; added `RunRecord` happy-path + literal-rejection test.
- **Implementation outline step 7 updated** — no longer instructs to author the template; instead instructs to verify the existing file's presence.
- **Files-to-touch annotated** — `templates/adr-amendment.md` row marked as already-shipped (S2-02); not to be created or overwritten.
- **Implementer notes expanded** — added the `Probe.version` convention note: the frozen ABC has no `version` attribute (ADR-0007); every probe subclass declares it as a class attribute by convention, and S3-01's `cache_key(...)` reads `cls.version`. Adding `version` to the ABC requires the ADR-amendment workflow.

Surfaced inconsistencies (out of scope to fix here — see `_validation/S2-05-registry-schema-audit-models.md`):
- **`AuditWriter.record` body** — High-level-impl Step 2 lists the body as a Step 2 deliverable (line 67); the story manifest README.md and S3-06 both put it in Step 3. The manifest is authoritative; High-level-impl needs a corrective sweep.
- **`templates/adr-amendment.md`** — manifest README.md still lists the template under S2-05's deliverables; S2-02 already delivered it. The manifest description is stale.
- **`RunRecord` field name** — arch §Component design says `os_kernel`; arch §Data model says `os_kernel_sha`. This story pins `os_kernel_sha` (Data model is the canonical schema); the §Component design line needs a follow-up edit.
- **`Probe.version`** — used by `ProbeExecutionRecord.version` and S3-01's `cache_key(...)` but not declared on the frozen `Probe` ABC. Every probe declares it as a class attribute by convention; the gap is dormant until S3-01 lands and is documented in implementer notes.

Full audit log: [`_validation/S2-05-registry-schema-audit-models.md`](_validation/S2-05-registry-schema-audit-models.md).

## Context

This story lands the three remaining Step 2 contracts so Step 3 can wire them into the harness. **Registry** (`probes/registry.py` + the `@register_probe` decorator) is the explicit-imports collection point — no `importlib.metadata` entry-point scan (perf + supply-chain), one decorator at decoration time, `for_task` cached via `functools.lru_cache`. **Schema** is the layered Draft 2020-12 envelope (`additionalProperties: false` at root, `true` under `probes.*`, per-probe sub-schemas via `$ref` — ADR-0013) plus the first per-probe sub-schema (`language_detection.schema.json`) that establishes the convention for Phase 1's six probes. **Audit models** are the Pydantic `RunRecord` + `ProbeExecutionRecord` with the dual `cache_key` + `blob_sha256` anchors from Gap 2 (ADR-0004) that Phase 11's PR provenance and Phase 13's cost ledger consume without extension. The `templates/adr-amendment.md` PR template was already delivered by S2-02 (commit `1ed09a6`, five-step checklist); this story only verifies it remains present.

This is the synthesis story for Step 2: every chokepoint primitive lands before Step 3 starts wiring them. It's also the longest dependency tail in Step 2 (depends on the three prior Step 2 stories).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Probe + Registry` — `Registry` class shape; `@register_probe` decorator; `for_task` filtering by `applies_to_tasks` and `applies_to_languages` with `["*"]` semantics; `lru_cache(maxsize=32)`; duplicate-name registration raises at decoration time; module-level `default_registry`; explicit imports in `probes/__init__.py` (no entry-point scan).
  - `../phase-arch-design.md §Component design — Schema validator` — `jsonschema.Draft202012Validator` compiled once at module scope behind `functools.lru_cache`; `additionalProperties: false` at root, `true` under `probes.*`; per-probe sub-schemas composed via `$ref`; raises `SchemaValidationError` with JSON Pointer of failure.
  - `../phase-arch-design.md §Component design — Audit writer` — `RunRecord` and `ProbeExecutionRecord` shapes; `<output_dir>/runs/<utc-iso>-<short-hash>.json` at mode `0600`; `os_kernel` redacts hostname.
  - `../phase-arch-design.md §Data model` — the four code blocks specifying envelope JSON Schema, `ProbeExecutionRecord`, `RunRecord`; the layered `additionalProperties` example.
  - `../phase-arch-design.md §Gap analysis Gap 2` — the under-specification this story's audit anchors close (`cache_key` and `blob_sha256` per probe, **both** fields, not "either one").
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0013-layered-additional-properties-schema.md` — ADR-0013 — schema layering: `false` at envelope, `true` under `probes.*`, per-probe sub-schemas constrain their own slice; adding a probe is a new file + one `$ref` line, never an envelope edit.
  - `../ADRs/0004-probe-execution-audit-anchor.md` — ADR-0004 — `ProbeExecutionRecord` carries **both** `cache_key` (SHA-256 identity tuple) and `blob_sha256` (SHA-256 of the sanitized blob bytes); `codegenie audit verify` re-reads and recomputes both.
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — names `templates/adr-amendment.md` as the PR template the snapshot test points at on drift; this story ships the template.
  - `../ADRs/0003-two-level-cache-key-schema-versioning.md` — ADR-0003 — `language_detection.schema.json` ships with a versioned `$id` (`v0.1.0`) so S3-01's `per_probe_schema_version(probe)` can read it.
- **Source design:**
  - `../final-design.md §2.4` — Registry; `for_task` filtering rules.
  - `../final-design.md §2.9` — Schema validation; layered `additionalProperties` policy.
  - `../final-design.md §2.12` — Audit record; whole-YAML `yaml_sha256` (which this story extends with per-probe anchors per Gap 2).
- **Existing code (if any):**
  - `src/codegenie/probes/base.py` (S2-02) — `Probe` ABC; `for_task` filters on its class attributes (`applies_to_tasks`, `applies_to_languages`).
  - `src/codegenie/hashing.py` (S2-03) — `identity_hash` for cache_key; `content_hash` for blob_sha256 *will not* use this — see implementer notes (blob_sha256 is SHA-256, computed directly via `hashlib.sha256`).
  - `src/codegenie/errors.py` (S2-01) — `ProbeError`, `SchemaValidationError`.

## Goal

Three import paths succeed: `from codegenie.probes.registry import register_probe, Registry, default_registry`; `from codegenie.schema.validator import validate` (validating a hand-built minimal envelope succeeds, with a top-level extra key failing and an unknown sub-key under `probes.*` passing); `from codegenie.audit import RunRecord, ProbeExecutionRecord` (both Pydantic models, with `cache_key` and `blob_sha256` on `ProbeExecutionRecord`). And `templates/adr-amendment.md` exists with the four-step checklist S2-02's snapshot-failure message points at.

## Acceptance criteria

- [ ] `src/codegenie/probes/registry.py` exports `register_probe(cls) -> type[Probe]` (decorator), `Registry` class with `register(cls)`, `all_probes() -> tuple[type[Probe], ...]`, `for_task(task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]`, and module-level `default_registry: Registry`. `register_probe(cls)` is sugar for `default_registry.register(cls)`.
- [ ] `Registry.for_task` filters by `applies_to_tasks` (`"*"` in the list = matches any task) and `applies_to_languages` (`"*"` = matches any language, otherwise intersects the requested `frozenset` with the declared list). Cached via `functools.lru_cache(maxsize=32)` keyed on `(task, frozenset(languages))`. The contract is pinned by this filter-matrix (validator: hardened — replaces prose-only rules with mutation-resistant table):

  | probe `applies_to_tasks` | probe `applies_to_languages` | call `task` | call `languages` | included? |
  |---|---|---|---|---|
  | `["*"]` | `["*"]` | `"vuln_remediation"` | `frozenset({"unknown"})` | **yes** |
  | `["vuln_remediation"]` | `["*"]` | `"distroless_migration"` | `frozenset({"unknown"})` | **no** (task mismatch) |
  | `["*"]` | `["javascript"]` | `"vuln_remediation"` | `frozenset({"unknown"})` | **no** (lang restricted, no match) |
  | `["*"]` | `["javascript"]` | `"vuln_remediation"` | `frozenset({"javascript"})` | **yes** (lang intersects) |
  | `["*"]` | `["javascript", "python"]` | `"vuln_remediation"` | `frozenset({"javascript", "go"})` | **yes** (non-empty intersection) |
- [ ] Duplicate-name registration raises `ProbeError` **at decoration time** (i.e., during module import) with a message naming both the new and existing classes.
- [ ] `src/codegenie/probes/__init__.py` uses **explicit imports** (e.g., `from . import base` plus, post-S4-01, `from . import language_detection`); no `importlib.metadata`, no entry-point scan.
- [ ] `src/codegenie/schema/repo_context.schema.json` exists with `$schema: "https://json-schema.org/draft/2020-12/schema"`, `$id` containing `v0.1.0`, `additionalProperties: false` at the envelope root, required keys `["schema_version", "generated_at", "repo", "probes"]`, and the `probes` property has `"additionalProperties": true`.
- [ ] `src/codegenie/schema/probes/language_detection.schema.json` exists with `$id` containing `language_detection/v0.1.0`, schema for `{"counts": {<lang>: <int>}, "primary": <str>}` per `phase-arch-design.md §Data model`. The envelope schema composes this via `$ref`.
- [ ] `src/codegenie/schema/validator.py` exports `validate(repo_context: dict) -> None` raising `SchemaValidationError` with the failing JSON Pointer in the message. The compiled `Draft202012Validator` is cached via `functools.lru_cache` (module-scope `_validator()`).
- [ ] `src/codegenie/audit.py` exports Pydantic v2 models `ProbeExecutionRecord` and `RunRecord`. `ProbeExecutionRecord` fields: `name: str`, `version: str`, `cache_hit: bool`, `wall_clock_ms: int`, `exit_status: Literal["ok", "error", "timeout", "skipped"]`, **`cache_key: str`**, **`blob_sha256: str`** (per ADR-0004 §Consequences: when `exit_status == "skipped"`, `blob_sha256` is the empty-string sentinel `""` — the model accepts this; non-skipped statuses ship a real `"sha256:<64-hex>"`). `RunRecord` fields per `phase-arch-design.md §Data model`, with the field name **`os_kernel_sha: str`** (Data model is canonical; arch §Component design's `os_kernel` is inconsistent — surfaced as a follow-up arch correction in Validation notes). Concretely: `cli_version: str`, `sherpa_commit: str`, `python_version: str`, **`os_kernel_sha: str`**, `probes: list[ProbeExecutionRecord]`, `tool_versions: dict[str, str]`, `yaml_sha256: str`. Both models have `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] `templates/adr-amendment.md` is **already present** at the repo root (delivered by S2-02 at commit `1ed09a6` with the canonical five-step checklist (a)–(e) that S2-02's snapshot-test failure message points at — see `_validation/S2-04-exec-allowlist.md` for the parallel-validation pattern). This story only verifies the file exists; it must **not** be re-authored or overwritten (validator: rewritten — original AC claimed this story creates the file with a four-step checklist; the file already exists with five steps).
- [ ] `tests/unit/test_registry.py` covers (validator: hardened — added return-value, parametrized filter matrix, and cache_info hit pin to catch obvious mutants):
  - `@register_probe` registers a class **and returns the class object unchanged** (`register_probe(Foo) is Foo`) — catches the `def register_probe(cls): default_registry.register(cls); return None` mutant.
  - Duplicate-name rejection at decoration time: a synthetic decoration that triggers the same `cls.name` twice raises `ProbeError` whose message names both classes.
  - `for_task` filter matrix from AC-2 implemented as a `pytest.mark.parametrize` table: every row of the five-row table above asserted in a single parametrized test.
  - `for_task` `lru_cache` is observable: after two identical `for_task(task, langs)` calls on the same `Registry` instance, the cached helper's `.cache_info().hits ≥ 1`. The module-level helper exposes `cache_info` for this assertion (`Registry._for_task_cache_info()` or direct module-level `_filter.cache_info()`).
  - `for_task("vuln_remediation", frozenset())` (empty language set) is a non-crashing call; result is consistent with the matrix.
- [ ] `tests/unit/test_schema_validation.py` covers (validator: hardened — added `$id` version pins, `$ref` resolution happy-path, sub-schema strictness convention, and `_validator()` cache-hit pin):
  - A hand-crafted minimal envelope passes.
  - A top-level extra key fails with a `SchemaValidationError` whose message includes both the offending key (`rogue_top_level_field`) and the substring `additionalProperties` (or the JSON-pointer `''` for root scope).
  - An unknown sub-key under `probes.future_probe_not_yet_defined.field` **passes** (loose at `probes.*` — ADR-0013).
  - A **valid** payload using the `language_detection` sub-schema passes — i.e., `probes.language_detection = {"counts": {"javascript": 3}, "primary": "javascript"}` validates successfully via `$ref` resolution (catches the un-wired-resolver mutant).
  - A bad type inside `probes.language_detection` (e.g., `counts` is a list, not an object; or `primary` is an integer) raises `SchemaValidationError` with the failing JSON Pointer pointing into the sub-schema path.
  - **Sub-schema strictness convention pinned**: `language_detection.schema.json` declares `additionalProperties: false` at the probe-slice level (ADR-0013 says sub-schemas MAY be strict at the probe author's discretion; Phase 0's reference sub-schema sets the precedent to **be strict**, which Phase 1 probes inherit by convention). An unknown sub-key under `probes.language_detection.unknown_extra_field` **fails** validation. *If the implementer chooses loose, the AC must be inverted in writing and surfaced as a convention deviation.*
  - **Envelope `$id` pinned**: the loaded envelope schema's `$id` string contains the substring `v0.1.0` (ADR-0003 — S3-01's `per_probe_schema_version` will read this).
  - **Sub-schema `$id` pinned**: the loaded `language_detection.schema.json`'s `$id` contains the substring `language_detection/v0.1.0` (ADR-0003 — surgical cache invalidation depends on per-probe `$id` versioning).
- [ ] `tests/unit/test_audit_models.py` covers (validator: hardened — added `frozen=True` mutation pin, explicit literal-rejection, `RunRecord` happy-path, `Skipped` sentinel acceptance):
  - `ProbeExecutionRecord` requires both `cache_key` and `blob_sha256` (omitting either raises `pydantic.ValidationError`).
  - `extra="forbid"` rejects unknown fields on both `ProbeExecutionRecord` and `RunRecord`.
  - `exit_status` literal enforcement: constructing with `exit_status="bogus"` raises `pydantic.ValidationError` (catches a bare `exit_status: str` mutant).
  - `frozen=True` mutation pin: constructing a record then attempting `record.cache_key = "sha256:..."` raises `pydantic.ValidationError` (catches the `model_config = ConfigDict(extra="forbid")` mutant that drops `frozen=True`).
  - `RunRecord` happy-path: a record constructed with all required fields (including `os_kernel_sha`) validates successfully; `model_dump()` round-trips.
  - **`Skipped` sentinel accepted**: `ProbeExecutionRecord(..., exit_status="skipped", cache_key="sha256:" + "0"*64, blob_sha256="")` validates successfully (per ADR-0004 §Consequences).
- [ ] **`tests/unit/test_schema_validation.py::test_validator_is_cached`** (new AC — see AC-13): catches the no-cache mutant that would cost ~30 ms per validate call. After two `validate(...)` calls, `from codegenie.schema.validator import _validator; assert _validator.cache_info().hits ≥ 1`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/{probes,schema,audit.py}`, and the three new test files all pass.
- [ ] **AC-13 (new): `validator.py`'s `_validator()` is cached**. The module-level `_validator()` function carries an `lru_cache` (or `functools.cache`) decorator; after two `validate(...)` calls, `_validator.cache_info().hits` is `≥ 1`. (validator: added — Coverage F5 + Test-Quality F2; the original story said the validator was cached but never tested it, so the no-cache mutant would have silently shipped.)

## Implementation outline

1. Write the three new test files first (`test_registry.py`, `test_schema_validation.py`, `test_audit_models.py`). Add a one-line existence-check assertion for `templates/adr-amendment.md` inside `test_audit_models.py` (or a sibling file) — the file already exists from S2-02 so this assertion is green from the start; it exists to fail-loud if someone accidentally deletes the template. Confirm `ImportError` on the three new modules. Commit as red.
2. Author `src/codegenie/probes/registry.py`. Inside `Registry.__init__` declare `self._probes: list[type[Probe]] = []` (instance-level so tests can construct independent registries). `register(cls)` checks for duplicate `cls.name`, appends, returns `cls`. `for_task(task, languages)` is `lru_cache(maxsize=32)`-decorated method (or wraps a helper to make it cacheable by `frozenset` key). Module-level `default_registry = Registry()`; `register_probe = default_registry.register`.
3. Update `src/codegenie/probes/__init__.py` (created stub in S2-02): add `from . import registry` and a placeholder `from . import language_detection  # registered in S4-01` comment that S4-01 will uncomment.
4. Author `src/codegenie/schema/__init__.py` (package marker; empty) and `src/codegenie/schema/repo_context.schema.json` (envelope) and `src/codegenie/schema/probes/__init__.py` (empty) and `src/codegenie/schema/probes/language_detection.schema.json` (per-probe sub-schema). Use absolute `$ref` (`"$ref": "./probes/language_detection.schema.json"`) and load both via `jsonschema`'s `RefResolver` configured with a base URI of the schema directory.
5. Author `src/codegenie/schema/validator.py`. Module-scope `@functools.lru_cache(maxsize=1) def _validator() -> jsonschema.Draft202012Validator` loads the envelope, sets up the `$ref` resolver, returns the compiled validator. `def validate(repo_context: dict) -> None` calls `_validator().validate(repo_context)`; on `jsonschema.ValidationError`, raises `SchemaValidationError(f"validation failed at {err.json_path}: {err.message}")`.
6. Author `src/codegenie/audit.py`. Two Pydantic v2 models. `ProbeExecutionRecord` and `RunRecord` per `phase-arch-design.md §Data model`. `model_config = ConfigDict(frozen=True, extra="forbid")` on both. **Do not** ship `AuditWriter.record(...)` body in this story — that's S3-06; just define the models and a stub `class AuditWriter` with a `record(...)` method that raises `NotImplementedError("see S3-06")` if anyone calls it prematurely. (Or omit the class entirely and have S3-06 author it from scratch — implementer's choice; the manifest places `AuditWriter.record` body in S3-06.)
7. **Do not author `templates/adr-amendment.md`.** It already exists at the repo root from S2-02 (commit `1ed09a6`) with the canonical five-step checklist `(a)`–`(e)`. The story-manifest README.md still lists this file under S2-05 — that description is stale and is a separate doc-correction (out of scope here). Verify the file is present (one-line `assert (REPO_ROOT / "templates/adr-amendment.md").exists()`).
8. Run formatter, linter, type checker, the three test files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test files: `tests/unit/test_registry.py`, `tests/unit/test_schema_validation.py`, `tests/unit/test_audit_models.py`. Each one anchors a distinct subsystem; keep them short.

```python
# tests/unit/test_registry.py
import pytest

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe
from codegenie.probes.registry import Registry, default_registry, register_probe


def _make_probe(
    name: str,
    *,
    tasks: list[str] = ["*"],
    langs: list[str] = ["*"],
) -> type[Probe]:
    """Synthesize a concrete Probe subclass with the requested filter attrs."""
    class _P(Probe):
        pass
    _P.name = name
    _P.version = "1.0"  # convention — not on the frozen ABC
    _P.layer = "A"; _P.tier = "base"
    _P.applies_to_tasks = tasks; _P.applies_to_languages = langs
    _P.declared_inputs = []; _P.requires = []
    async def run(self, snapshot, ctx): raise NotImplementedError
    _P.run = run  # type: ignore[assignment]
    return _P


def test_register_probe_decorator_adds_to_default_registry_and_returns_class():
    @register_probe
    class FakeProbe(Probe):
        name = "fake_one"; version = "1.0"; layer = "A"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        declared_inputs = []; requires = []
        async def run(self, snapshot, ctx):  # type: ignore[override]
            raise NotImplementedError
    # Decorator returns the class unchanged (catches the "decorator returns None" mutant).
    assert FakeProbe.__name__ == "FakeProbe"
    assert FakeProbe in default_registry.all_probes()


def test_duplicate_name_rejected_at_decoration_time_names_both_classes():
    reg = Registry()
    A = _make_probe("dup")
    reg.register(A)
    B = _make_probe("dup")
    with pytest.raises(ProbeError, match=r"dup"):
        reg.register(B)


@pytest.mark.parametrize(
    "p_tasks,p_langs,task,langs,expected",
    [
        (["*"], ["*"], "vuln_remediation", frozenset({"unknown"}), True),
        (["vuln_remediation"], ["*"], "distroless_migration", frozenset({"unknown"}), False),
        (["*"], ["javascript"], "vuln_remediation", frozenset({"unknown"}), False),
        (["*"], ["javascript"], "vuln_remediation", frozenset({"javascript"}), True),
        (["*"], ["javascript", "python"], "vuln_remediation", frozenset({"javascript", "go"}), True),
    ],
)
def test_for_task_filter_matrix(p_tasks, p_langs, task, langs, expected):
    reg = Registry()
    P = _make_probe("matrix_probe", tasks=p_tasks, langs=p_langs)
    reg.register(P)
    result = reg.for_task(task, langs)
    assert (P in result) is expected


def test_for_task_lru_cache_hits_on_repeated_calls():
    """Catches the no-cache mutant: a `for_task` that re-computes every call."""
    # The module-level cached helper must be observable. The implementer is free
    # to choose the exposure shape — direct `_filter.cache_info()` access, or
    # `Registry._for_task_cache_info()` classmethod — but SOMETHING observable
    # must exist and report `hits ≥ 1` after two identical calls.
    from codegenie.probes import registry as reg_mod

    reg = Registry()
    P = _make_probe("cache_probe")
    reg.register(P)
    reg.for_task("vuln_remediation", frozenset({"unknown"}))
    reg.for_task("vuln_remediation", frozenset({"unknown"}))
    info = reg_mod._filter.cache_info()  # module-level helper per implementer note
    assert info.hits >= 1
```

```python
# tests/unit/test_schema_validation.py
import json
from pathlib import Path

import pytest

from codegenie.errors import SchemaValidationError
from codegenie.schema import validator as validator_mod
from codegenie.schema.validator import validate


_MINIMAL: dict = {
    "schema_version": "0.1.0",
    "generated_at": "2026-05-11T12:00:00Z",
    "repo": {"root": "/tmp/x", "git_commit": None},
    "probes": {},
}


def test_minimal_envelope_passes():
    validate(_MINIMAL)  # no raise


def test_top_level_extra_key_fails():
    payload = {**_MINIMAL, "rogue_top_level_field": True}
    with pytest.raises(SchemaValidationError) as exc:
        validate(payload)
    # JSON-pointer or message must name the rogue key OR mention additionalProperties.
    assert (
        "rogue_top_level_field" in str(exc.value)
        or "additionalproperties" in str(exc.value).lower()
    )


def test_unknown_probe_namespace_key_passes():
    """`additionalProperties: true` under `probes.*` — extension by addition (ADR-0013)."""
    validate({**_MINIMAL, "probes": {"future_probe_not_yet_defined": {"anything": "goes"}}})


def test_language_detection_slice_valid_payload_passes():
    """`$ref` resolution to the sub-schema actually wires up (catches un-wired-resolver mutant)."""
    validate({
        **_MINIMAL,
        "probes": {"language_detection": {"counts": {"javascript": 3}, "primary": "javascript"}},
    })  # no raise


def test_language_detection_slice_invalid_primary_type_fails():
    with pytest.raises(SchemaValidationError, match=r"primary"):
        validate({
            **_MINIMAL,
            "probes": {"language_detection": {"counts": {}, "primary": 42}},
        })


def test_language_detection_slice_invalid_counts_shape_fails():
    """`counts` must be `dict[str, int]` per the sub-schema, not a list."""
    with pytest.raises(SchemaValidationError):
        validate({
            **_MINIMAL,
            "probes": {"language_detection": {"counts": ["javascript"], "primary": "javascript"}},
        })


def test_language_detection_unknown_sub_key_fails_when_subschema_is_strict():
    """Phase 0's `language_detection.schema.json` sets the precedent: strict at the probe slice."""
    with pytest.raises(SchemaValidationError):
        validate({
            **_MINIMAL,
            "probes": {
                "language_detection": {
                    "counts": {"javascript": 1},
                    "primary": "javascript",
                    "unknown_extra_field": "should reject",
                },
            },
        })


def test_envelope_schema_id_is_versioned():
    """ADR-0003: S3-01's `per_probe_schema_version(probe)` reads `$id` to scope cache invalidation."""
    schema_path = Path(__file__).parents[2] / "src/codegenie/schema/repo_context.schema.json"
    schema = json.loads(schema_path.read_text())
    assert "v0.1.0" in schema["$id"]


def test_language_detection_subschema_id_is_versioned():
    schema_path = (
        Path(__file__).parents[2]
        / "src/codegenie/schema/probes/language_detection.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert "language_detection/v0.1.0" in schema["$id"]


def test_validator_is_cached():
    """Catches the no-cache mutant: a `_validator()` that compiles every call (~30 ms)."""
    validator_mod._validator.cache_clear()  # reset for deterministic baseline
    validate(_MINIMAL)
    validate(_MINIMAL)
    info = validator_mod._validator.cache_info()
    assert info.hits >= 1
```

```python
# tests/unit/test_audit_models.py
import pytest
from pydantic import ValidationError

from codegenie.audit import ProbeExecutionRecord, RunRecord

_SHA = "sha256:" + "0" * 64


def _exec_kwargs(**overrides) -> dict:
    base = dict(
        name="x", version="1", cache_hit=False, wall_clock_ms=10,
        exit_status="ok", cache_key=_SHA, blob_sha256=_SHA,
    )
    base.update(overrides)
    return base


def test_probe_execution_record_requires_cache_key_and_blob_sha256():
    # omit cache_key
    bad = _exec_kwargs(); bad.pop("cache_key")
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**bad)
    # omit blob_sha256
    bad = _exec_kwargs(); bad.pop("blob_sha256")
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**bad)


def test_extra_forbid_rejects_unknown_field_on_probe_execution_record():
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**_exec_kwargs(unexpected_field="bad"))


def test_exit_status_literal_rejection():
    """Catches a bare `exit_status: str` mutant."""
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**_exec_kwargs(exit_status="bogus"))


def test_frozen_mutation_raises():
    """Catches the `frozen=True` → `frozen=False` mutant."""
    record = ProbeExecutionRecord(**_exec_kwargs())
    with pytest.raises(ValidationError):
        record.cache_key = "sha256:" + "f" * 64  # type: ignore[misc]


def test_skipped_accepts_empty_blob_sha256_sentinel():
    """ADR-0004 §Consequences: skipped executions carry `blob_sha256=""` sentinel."""
    record = ProbeExecutionRecord(**_exec_kwargs(exit_status="skipped", blob_sha256=""))
    assert record.exit_status == "skipped"
    assert record.blob_sha256 == ""


def test_run_record_happy_path_and_extra_forbid():
    record = RunRecord(
        cli_version="0.1.0",
        sherpa_commit="abc1234",
        python_version="3.11.10",
        os_kernel_sha="sha256:" + "a" * 64,
        probes=[ProbeExecutionRecord(**_exec_kwargs())],
        tool_versions={"git": "2.45.0"},
        yaml_sha256="sha256:" + "b" * 64,
    )
    assert record.os_kernel_sha.startswith("sha256:")
    assert record.probes[0].name == "x"
    with pytest.raises(ValidationError):
        RunRecord(  # type: ignore[call-arg]
            cli_version="0.1.0",
            sherpa_commit="abc1234",
            python_version="3.11.10",
            os_kernel_sha="sha256:" + "a" * 64,
            probes=[],
            tool_versions={},
            yaml_sha256="sha256:" + "b" * 64,
            unexpected_field="reject me",
        )
```

Plus a one-line file-existence test for `templates/adr-amendment.md` that asserts the **existing** file (delivered by S2-02) is still present at the repo root — this story does not create it (validator: clarified — original red-marker step instructed authoring; AC-8 now verifies-only).

Run all five; expect failures. Commit as red marker.

### Green — make it pass

Minimal-shape implementation per the outline. The `Registry`'s `for_task` cache wants a hashable key — `task: str` and `languages: frozenset[str]` both hash, so `@lru_cache(maxsize=32)` on a plain function that the method delegates to (or `@functools.lru_cache` directly on a method with `self` as cache key, which works because each `Registry` instance is itself hashable by identity — but easier: factor out a module-level cached helper).

For schema loading, `jsonschema.Draft202012Validator(schema, resolver=jsonschema.RefResolver(base_uri=f"file://{schema_dir}/", referrer=schema))` is the simplest path.

For Pydantic v2, models look like:
```python
class ProbeExecutionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    version: str
    cache_hit: bool
    wall_clock_ms: int
    exit_status: Literal["ok", "error", "timeout", "skipped"]
    cache_key: str
    blob_sha256: str
```

### Refactor — clean up

- Type hints everywhere; `mypy --strict` clean.
- Module docstrings naming the relevant ADR (ADR-0013 for schema, ADR-0004 for audit, ADR-0007 for `templates/adr-amendment.md`).
- `Registry.for_task` docstring: explain `["*"]` semantics and the `lru_cache` strategy.
- `validator.py` error message format pinned: `f"validation failed at {err.json_path}: {err.message}"` — Phase 1+ probes' invalid outputs will surface here.
- `audit.py` model docstrings: name `cache_key` and `blob_sha256` as Gap-2-fix audit anchors per ADR-0004.
- `templates/adr-amendment.md`: short, scannable; the four checklist items mirror ADR-0007 §Consequences exactly.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/registry.py` | New — `@register_probe`, `Registry`, `default_registry`; duplicate-name reject |
| `src/codegenie/probes/__init__.py` | Update — explicit imports for `base` and `registry` (and a placeholder comment for `language_detection`) |
| `src/codegenie/schema/__init__.py` | New — package marker |
| `src/codegenie/schema/repo_context.schema.json` | New — envelope JSON Schema per ADR-0013 |
| `src/codegenie/schema/probes/__init__.py` | New — package marker |
| `src/codegenie/schema/probes/language_detection.schema.json` | New — first per-probe sub-schema; `$id` versioned `v0.1.0` |
| `src/codegenie/schema/validator.py` | New — `validate(repo_context)` with cached `Draft202012Validator` |
| `src/codegenie/audit.py` | New — Pydantic `RunRecord` + `ProbeExecutionRecord` with dual audit anchors |
| ~~`templates/adr-amendment.md`~~ | **Already exists** (S2-02 commit `1ed09a6`, five-step checklist). Do NOT modify or overwrite — verify-only. (validator: annotated — Consistency F1) |
| `tests/unit/test_registry.py` | New — pins `@register_probe`, duplicate rejection, `for_task` filtering, lru cache |
| `tests/unit/test_schema_validation.py` | New — pins layered `additionalProperties` policy |
| `tests/unit/test_audit_models.py` | New — pins dual audit anchors + `extra="forbid"` |

## Out of scope

- **`AuditWriter.record(...)` body** — handled by S3-06 (writes `runs/<utc-iso>-<short>.json` mode `0600`).
- **`codegenie audit verify` subcommand** — handled by S3-06 and S4-02 (CLI wiring).
- **`cache/keys.py` reading `$id` from sub-schemas** — handled by S3-01 (`per_probe_schema_version(probe)`); this story ships the sub-schema *file* with the correct `$id`; the reader function comes later.
- **`_ProbeOutputValidator` Pydantic model** — handled by S3-02 (validator under `coordinator/`, not `audit.py`); ADR-0010 keeps it internal to the coordinator.
- **`.github/ISSUE_TEMPLATE/adr-amendment.md`** — different file, different audience; the issue template is handled by S5-02. `templates/adr-amendment.md` (this story) is the in-repo PR-author checklist the snapshot test points at.
- **`tests/adv/test_no_shell_true.py` / `test_no_network_imports.py` / `test_yaml_unsafe_load.py`** — handled by S4-05 per the manifest. Some High-level-impl bullets list these under Step 2 but the manifest is authoritative.
- **`Probe.declared_resource_budget`** — handled by S3-05 (coordinator + Gap 3); the Probe ABC frozen by S2-02 is the closed surface, and adding the budget there now would trigger the snapshot test.

## Notes for the implementer

- **The Probe ABC frozen by S2-02 must not change.** This story uses the ABC and registers against it but never modifies `src/codegenie/probes/base.py`. The snapshot test from S2-02 will fail loud if you so much as add a comment to `base.py`. If `Registry.register(cls)` needs to look up something on the `Probe` class that isn't declared, *that's a sign the call should walk class attributes, not edit the contract.*
- **`Probe.version` is a convention, not part of the ABC.** The frozen `Probe` ABC in `base.py` declares `name`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy` — but **not** `version`. `ProbeExecutionRecord.version` and S3-01's `cache_key = identity_hash(probe.name, probe.version, schema_version, content_hash_of_inputs)` both read `cls.version` (every probe class declares it as a class attribute, e.g. `version = "1.0"`). Under `mypy --strict`, reading `cls.version` on a `type[Probe]` will need an explicit `getattr(cls, "version")` (with a sensible fallback) or a `cast`. Adding `version: str` to the ABC requires the ADR-amendment workflow per ADR-0007 — out of scope here. Document the convention in `Registry.register`'s docstring; don't enforce it as a runtime check inside `register` itself (the duplicate-name check is enough for Phase 0).
- **`for_task`'s `["*"]` semantics matter for `RepoSnapshot.detected_languages`.** Phase 0's bullet tracer dispatches with `frozenset({"unknown"})` (no detection yet). A probe declaring `applies_to_languages=["*"]` matches; a probe declaring `applies_to_languages=["javascript"]` does *not* match `{"unknown"}` and won't be dispatched. The prelude pass (S3-05, Gap 4) is what enriches the snapshot before downstream probes filter. Don't reinvent that here; just implement the filter correctly.
- **`lru_cache` on a method requires care.** The cleanest pattern is to factor out a module-level helper `@lru_cache(maxsize=32) def _filter(probes: tuple[type[Probe], ...], task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]` and have `Registry.for_task(task, languages)` call `_filter(tuple(self._probes), task, languages)`. Plain `@lru_cache` on a bound method works in Python 3.11+ but stores `self` in the cache, which leaks the registry until clear. Module-level helper is safer.
- **Envelope `$ref` resolution requires a `base_uri`.** The simplest way is `jsonschema.RefResolver(base_uri=f"file://{schema_dir}/", referrer=envelope_schema)`. Don't try to construct the resolved schema by hand-inlining sub-schemas; `jsonschema` handles `$ref` natively and the layered-additionalProperties policy depends on the library doing the right thing.
- **Per ADR-0004, `blob_sha256` is SHA-256 of the *sanitized* blob bytes** — not the raw probe output bytes and not the BLAKE3 content hash of inputs. This story only defines the field; the actual computation lives in S3-06 (`AuditWriter`). Document the field's semantics in the Pydantic model's docstring so the S3-06 implementer doesn't conflate the three hashes (input-content-BLAKE3 vs. identity-tuple-SHA-256 vs. sanitized-blob-SHA-256).
- **`extra="forbid"` on both audit models is load-bearing.** Phase 11's PR provenance and Phase 13's cost ledger key off these field names; an extra field silently appearing in the audit JSON (from a code path that forgets to use the model) would be undetectable without `forbid`. Don't switch to `extra="ignore"` for "flexibility."
- **`templates/adr-amendment.md` is *not* `.github/ISSUE_TEMPLATE/adr-amendment.md`.** Different files, different audiences. The one here is for `localv2.md §4` editors (PR authors); the issue template (S5-02) is for filing the amendment as a GitHub issue. S2-02's failure message points at the *templates/* path explicitly.
- **`json-schema.org/draft/2020-12` is the right meta-schema URI.** Some examples online mention `draft-2020-12` (with a hyphen) — that's wrong. Use the slash form. `jsonschema>=4.21` validates against the slash form.
- **Idempotence on registry imports.** Re-importing a module that decorates `@register_probe` MUST NOT cause duplicate-name errors. Python's import system memoizes modules, so this is naturally idempotent — but if someone uses `importlib.reload()`, the duplicate-name check will fire. That's the correct behavior; document it but don't try to "fix" it.
- **`pyproject.toml` `[tool.setuptools.package-data]` or `[tool.hatch.build.targets.wheel.force-include]` may need to add `src/codegenie/schema/**/*.json`** so the JSON files ship in the installed wheel. Phase 0 runs from the source tree so this isn't a Phase-0 blocker, but flag it in the PR — Phase 1 will hit it when an installed `codegenie` is run against a `.codegenie/` directory.
- **Cross-cutting per the manifest's "Definition of done":** ruff format, ruff check, mypy --strict on `src/codegenie/{probes,schema,audit.py}`. The `mypy --strict` on Pydantic v2 models may surface friction with `model_config = ConfigDict(...)` annotations; install the `pydantic.mypy` plugin (S1-02 wired it).
