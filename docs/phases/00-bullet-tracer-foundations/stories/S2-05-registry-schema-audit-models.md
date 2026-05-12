# Story S2-05 — Registry + JSON Schema envelope + audit models

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Ready
**Effort:** M
**Depends on:** S2-02, S2-03, S2-04
**ADRs honored:** ADR-0004, ADR-0007, ADR-0013

## Context

This story lands the three remaining Step 2 contracts so Step 3 can wire them into the harness. **Registry** (`probes/registry.py` + the `@register_probe` decorator) is the explicit-imports collection point — no `importlib.metadata` entry-point scan (perf + supply-chain), one decorator at decoration time, `for_task` cached via `functools.lru_cache`. **Schema** is the layered Draft 2020-12 envelope (`additionalProperties: false` at root, `true` under `probes.*`, per-probe sub-schemas via `$ref` — ADR-0013) plus the first per-probe sub-schema (`language_detection.schema.json`) that establishes the convention for Phase 1's six probes. **Audit models** are the Pydantic `RunRecord` + `ProbeExecutionRecord` with the dual `cache_key` + `blob_sha256` anchors from Gap 2 (ADR-0004) that Phase 11's PR provenance and Phase 13's cost ledger consume without extension. The `templates/adr-amendment.md` PR template lands here too — the snapshot test from S2-02 already names it.

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
- [ ] `Registry.for_task` filters by `applies_to_tasks` (`"*"` in the list = matches any task) and `applies_to_languages` (`"*"` = matches any language, otherwise intersects the requested `frozenset` with the declared list). Cached via `functools.lru_cache(maxsize=32)` keyed on `(task, frozenset(languages))`.
- [ ] Duplicate-name registration raises `ProbeError` **at decoration time** (i.e., during module import) with a message naming both the new and existing classes.
- [ ] `src/codegenie/probes/__init__.py` uses **explicit imports** (e.g., `from . import base` plus, post-S4-01, `from . import language_detection`); no `importlib.metadata`, no entry-point scan.
- [ ] `src/codegenie/schema/repo_context.schema.json` exists with `$schema: "https://json-schema.org/draft/2020-12/schema"`, `$id` containing `v0.1.0`, `additionalProperties: false` at the envelope root, required keys `["schema_version", "generated_at", "repo", "probes"]`, and the `probes` property has `"additionalProperties": true`.
- [ ] `src/codegenie/schema/probes/language_detection.schema.json` exists with `$id` containing `language_detection/v0.1.0`, schema for `{"counts": {<lang>: <int>}, "primary": <str>}` per `phase-arch-design.md §Data model`. The envelope schema composes this via `$ref`.
- [ ] `src/codegenie/schema/validator.py` exports `validate(repo_context: dict) -> None` raising `SchemaValidationError` with the failing JSON Pointer in the message. The compiled `Draft202012Validator` is cached via `functools.lru_cache` (module-scope `_validator()`).
- [ ] `src/codegenie/audit.py` exports Pydantic v2 models `ProbeExecutionRecord` and `RunRecord`. `ProbeExecutionRecord` fields: `name: str`, `version: str`, `cache_hit: bool`, `wall_clock_ms: int`, `exit_status: Literal["ok", "error", "timeout", "skipped"]`, **`cache_key: str`**, **`blob_sha256: str`**. `RunRecord` fields per `phase-arch-design.md §Data model`. Both have `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] `templates/adr-amendment.md` exists with a four-step checklist (a) edit `localv2.md`, (b) run `scripts/regen_probe_contract_snapshot.py`, (c) update the implementation if structural drift surfaces, (d) reference ADR-0007 in the PR. S2-02's snapshot-test failure message points at this exact path.
- [ ] `tests/unit/test_registry.py` covers: `@register_probe` registers a class, duplicate-name rejection at decoration time, `for_task` filtering with `["*"]` semantics on both task and language axes, `lru_cache` hit on repeated calls.
- [ ] `tests/unit/test_schema_validation.py` covers: a hand-crafted minimal envelope passes; a top-level extra key fails with a JSON-pointer message; an unknown sub-key under `probes.unknown_probe.field` passes (loose at `probes.*`); a bad type inside `probes.language_detection` (e.g., `counts` is a list, not an object) fails per the sub-schema.
- [ ] `tests/unit/test_audit_models.py` covers: `ProbeExecutionRecord` requires both `cache_key` and `blob_sha256` (omitting either raises a Pydantic `ValidationError`); `extra="forbid"` rejects unknown fields; `exit_status` literal enforcement.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/{probes,schema,audit.py}`, and the three new test files all pass.

## Implementation outline

1. Write all four test files first (`test_registry.py`, `test_schema_validation.py`, `test_audit_models.py`, plus one trivial existence-check for `templates/adr-amendment.md`). Confirm `ImportError` / `FileNotFoundError`. Commit as red.
2. Author `src/codegenie/probes/registry.py`. Inside `Registry.__init__` declare `self._probes: list[type[Probe]] = []` (instance-level so tests can construct independent registries). `register(cls)` checks for duplicate `cls.name`, appends, returns `cls`. `for_task(task, languages)` is `lru_cache(maxsize=32)`-decorated method (or wraps a helper to make it cacheable by `frozenset` key). Module-level `default_registry = Registry()`; `register_probe = default_registry.register`.
3. Update `src/codegenie/probes/__init__.py` (created stub in S2-02): add `from . import registry` and a placeholder `from . import language_detection  # registered in S4-01` comment that S4-01 will uncomment.
4. Author `src/codegenie/schema/__init__.py` (package marker; empty) and `src/codegenie/schema/repo_context.schema.json` (envelope) and `src/codegenie/schema/probes/__init__.py` (empty) and `src/codegenie/schema/probes/language_detection.schema.json` (per-probe sub-schema). Use absolute `$ref` (`"$ref": "./probes/language_detection.schema.json"`) and load both via `jsonschema`'s `RefResolver` configured with a base URI of the schema directory.
5. Author `src/codegenie/schema/validator.py`. Module-scope `@functools.lru_cache(maxsize=1) def _validator() -> jsonschema.Draft202012Validator` loads the envelope, sets up the `$ref` resolver, returns the compiled validator. `def validate(repo_context: dict) -> None` calls `_validator().validate(repo_context)`; on `jsonschema.ValidationError`, raises `SchemaValidationError(f"validation failed at {err.json_path}: {err.message}")`.
6. Author `src/codegenie/audit.py`. Two Pydantic v2 models. `ProbeExecutionRecord` and `RunRecord` per `phase-arch-design.md §Data model`. `model_config = ConfigDict(frozen=True, extra="forbid")` on both. **Do not** ship `AuditWriter.record(...)` body in this story — that's S3-06; just define the models and a stub `class AuditWriter` with a `record(...)` method that raises `NotImplementedError("see S3-06")` if anyone calls it prematurely. (Or omit the class entirely and have S3-06 author it from scratch — implementer's choice; the manifest places `AuditWriter.record` body in S3-06.)
7. Author `templates/adr-amendment.md` (top-level repo dir, not `src/`). Four-step PR-author checklist; one short paragraph at the top explaining the workflow. The path is the literal string `templates/adr-amendment.md` matching S2-02's failure message.
8. Run formatter, linter, type checker, the three test files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test files: `tests/unit/test_registry.py`, `tests/unit/test_schema_validation.py`, `tests/unit/test_audit_models.py`. Each one anchors a distinct subsystem; keep them short.

```python
# tests/unit/test_registry.py
import pytest

def test_register_probe_decorator_adds_to_default_registry():
    from codegenie.probes.registry import register_probe, default_registry
    from codegenie.probes.base import Probe
    # arrange: a synthetic probe class
    @register_probe
    class FakeProbe(Probe):
        name = "fake_one"; version = "1.0"; layer = "A"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        declared_inputs = []; requires = []
        async def run(self, snapshot, ctx):  # type: ignore[override]
            raise NotImplementedError
    # assert: present in the default registry
    assert FakeProbe in default_registry.all_probes()

def test_duplicate_name_rejected_at_decoration_time():
    from codegenie.probes.registry import Registry
    from codegenie.probes.base import Probe
    from codegenie.errors import ProbeError
    reg = Registry()
    class A(Probe):
        name = "dup"; version = "1"; layer = "A"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        declared_inputs = []; requires = []
        async def run(self, snapshot, ctx): raise NotImplementedError
    reg.register(A)
    class B(Probe):
        name = "dup"; version = "1"; layer = "A"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        declared_inputs = []; requires = []
        async def run(self, snapshot, ctx): raise NotImplementedError
    with pytest.raises(ProbeError):
        reg.register(B)

def test_for_task_filters_by_star_semantics():
    # `applies_to_tasks=["*"]` and `applies_to_languages=["*"]` always match.
    # A probe with `applies_to_languages=["javascript"]` matches when "javascript" in requested set.
    ...  # detail in implementation
```

```python
# tests/unit/test_schema_validation.py
def test_minimal_envelope_passes():
    from codegenie.schema.validator import validate
    validate({
        "schema_version": "0.1.0",
        "generated_at": "2026-05-11T12:00:00Z",
        "repo": {"root": "/tmp/x", "git_commit": None},
        "probes": {},
    })  # no raise

def test_top_level_extra_key_fails():
    from codegenie.schema.validator import validate
    from codegenie.errors import SchemaValidationError
    import pytest
    with pytest.raises(SchemaValidationError) as exc:
        validate({
            "schema_version": "0.1.0",
            "generated_at": "2026-05-11T12:00:00Z",
            "repo": {"root": "/tmp/x", "git_commit": None},
            "probes": {},
            "rogue_top_level_field": True,
        })
    assert "rogue_top_level_field" in str(exc.value) or "additional" in str(exc.value).lower()

def test_unknown_probe_namespace_key_passes():
    # `additionalProperties: true` under `probes.*` — extension by addition (ADR-0013)
    from codegenie.schema.validator import validate
    validate({
        "schema_version": "0.1.0",
        "generated_at": "2026-05-11T12:00:00Z",
        "repo": {"root": "/tmp/x", "git_commit": None},
        "probes": {"future_probe_not_yet_defined": {"anything": "goes"}},
    })  # no raise
```

```python
# tests/unit/test_audit_models.py
def test_probe_execution_record_requires_cache_key_and_blob_sha256():
    from codegenie.audit import ProbeExecutionRecord
    import pytest
    from pydantic import ValidationError
    # arrange: omit cache_key
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(
            name="x", version="1", cache_hit=False, wall_clock_ms=10,
            exit_status="ok", blob_sha256="sha256:" + "0" * 64,
            # cache_key missing
        )
    # arrange: omit blob_sha256
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(
            name="x", version="1", cache_hit=False, wall_clock_ms=10,
            exit_status="ok", cache_key="sha256:" + "0" * 64,
            # blob_sha256 missing
        )

def test_extra_forbid_rejects_unknown_field():
    from codegenie.audit import ProbeExecutionRecord
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(
            name="x", version="1", cache_hit=False, wall_clock_ms=10,
            exit_status="ok", cache_key="sha256:" + "0" * 64,
            blob_sha256="sha256:" + "0" * 64,
            unexpected_field="bad",
        )
```

Plus a one-line file-existence test for `templates/adr-amendment.md`.

Run all four; expect failures. Commit as red marker.

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
| `templates/adr-amendment.md` | New — PR-author checklist for `localv2.md §4` amendments |
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
