# Story S1-06 — Gate YAML catalog schema + empty `stage6_validate.yaml` stub

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-02, S1-04
**ADRs honored:** ADR-0006, ADR-0014, ADR-0015

## Context

Gate logic in Phase 5 is configured as **data** — YAML catalogs under `gates/catalog/` define each gate's required signals, retry policy, and per-attempt sandbox overrides. This satisfies the "organizational uniqueness as data, not prompts" load-bearing commitment from `CLAUDE.md`. This story ships the JSON Schema that pins the catalog shape, a loader that validates against it, and an empty-but-schema-valid `stage6_validate.yaml` stub so Step 3's `SandboxSpecBuilder` (S3-01) has a real file to consume.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` — full populated YAML showing every key the schema must accept; this story ships only the stub, but the *schema* must allow this full shape.
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` — `gates/catalog/<gate_id>.yaml` shape; per-attempt overrides; phases; env_allowlist reference.
  - `../phase-arch-design.md §Edge case 13` — invalid YAML against `_schema.json` raises `GateCatalogInvalid`; CLI exit 2 before any gate runs.
  - `../phase-arch-design.md §Open questions §4` — one catalog or two (`stage6_validate.yaml` + `stage6_validate_loose.yaml`); this story ships one stub; S3-05 populates both.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `Gate` is an ABC; YAML loader produces a concrete `StrictAndGate` subclass instance (real instantiation lands in S4-05; here we only validate shape).
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `required_signals` enumerates `SignalKind` strings; loader does not coerce signal-kind names that contain banned substrings.
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `retry_policy.non_retryable_failures` may include `trace`; this story's stub leaves the policy lists empty so the schema is exercised but no logic is implied.
- **Source design:**
  - `../final-design.md §Component-5` — YAML catalog rationale.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullet 5 + Step 1 done-criteria bullet 1.

## Goal

Ship `src/codegenie/gates/catalog/_schema.json`, `src/codegenie/gates/catalog_loader.py` (validates against the schema and surfaces `GateCatalogInvalid` on mismatch), and an empty-but-schema-valid `src/codegenie/gates/catalog/stage6_validate.yaml` stub.

## Acceptance criteria

- [ ] `src/codegenie/gates/catalog/_schema.json` is valid JSON Schema (draft 2020-12); validates against itself via `jsonschema.Draft202012Validator.check_schema`.
- [ ] The schema requires top-level keys `gate_id` (string), `transition` (string ∈ `{"stage6_validate","stage6_validate_loose"}`), `required_signals` (array of strings), `retry_policy` (object with `max_attempts: int`, `retryable_failures: array[string]`, `non_retryable_failures: array[string]`, `timeout_retryable: bool`), `sandbox` (object with `base_image`, `time_budget_seconds`, `memory_limit_mib`, `pids_limit`, `env_allowlist`, `phases`). Each `phases[]` entry requires `name`, `network` ∈ `{"none","scoped"}`, `cmd: array[string]`, with optional `egress_allowlist`, `enable_trace`. An optional top-level `attempt_overrides` maps string keys (attempt numbers) to partial sandbox blocks.
- [ ] `catalog_loader.load(path: Path) -> CatalogEntry` reads a YAML file, validates against the schema, and returns a typed `CatalogEntry` Pydantic model (the model is frozen and `extra="forbid"`).
- [ ] `catalog_loader.load_all(catalog_dir: Path) -> dict[str, CatalogEntry]` loads every `.yaml` file in `catalog_dir` (excluding files prefixed with `_`).
- [ ] Loading a YAML with an unknown top-level key raises `GateCatalogInvalid` with a message naming the offending key and file path.
- [ ] Loading a YAML missing a required key raises `GateCatalogInvalid`.
- [ ] `stage6_validate.yaml` stub validates against the schema (passes `load` cleanly); its `required_signals` is `[]` and `phases` is `[]` (empty but schema-valid).
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/gates/catalog_loader.py`, `pytest tests/gates/test_catalog_schema.py tests/gates/test_catalog_loader.py` all pass.

## Implementation outline

1. Write `src/codegenie/gates/catalog/_schema.json` as a JSON Schema draft 2020-12 document (filename prefixed `_` so `load_all` skips it).
2. Write `src/codegenie/gates/catalog/stage6_validate.yaml` minimal stub.
3. Create `src/codegenie/gates/catalog_loader.py`:
   - Pydantic model `CatalogEntry` mirroring the schema (frozen, extra-forbid).
   - `_SCHEMA_PATH = Path(__file__).parent / "catalog" / "_schema.json"`.
   - `_validator = jsonschema.Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()))`.
   - `load(path)`: `yaml.safe_load`; pass through `_validator.validate(...)` — on `jsonschema.ValidationError` raise `GateCatalogInvalid(f"{path}: {err.message}")`; build the `CatalogEntry`.
   - `load_all(dir)`: iterate `dir.glob("*.yaml")`, skip `_*.yaml`, build dict keyed by `gate_id`.
4. Write the two test files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/gates/test_catalog_schema.py`, `tests/gates/test_catalog_loader.py`.

```python
# tests/gates/test_catalog_schema.py
import json
from pathlib import Path
import jsonschema

SCHEMA = Path("src/codegenie/gates/catalog/_schema.json")

def test_schema_is_valid_draft_2020_12():
    s = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(s)

def test_schema_validates_full_example_from_arch_doc():
    s = json.loads(SCHEMA.read_text())
    example = {
        "gate_id": "stage6_validate",
        "transition": "stage6_validate",
        "required_signals": ["build", "install", "tests", "trace", "policy", "cve_delta"],
        "retry_policy": {
            "max_attempts": 3,
            "retryable_failures": ["build", "install", "tests", "policy", "cve_delta"],
            "non_retryable_failures": ["trace"],
            "timeout_retryable": False,
        },
        "sandbox": {
            "base_image": "cgr.dev/chainguard/node@sha256:abc",
            "time_budget_seconds": 600,
            "memory_limit_mib": 2048,
            "pids_limit": 1024,
            "env_allowlist": ["PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY"],
            "phases": [
                {"name": "install", "network": "scoped",
                 "egress_allowlist": ["registry.npmjs.org"],
                 "cmd": ["sh", "-c", "cd /work && npm ci --ignore-scripts"]},
                {"name": "test", "network": "none", "enable_trace": True,
                 "cmd": ["sh", "-c", "cd /work && npm test"]},
            ],
        },
        "attempt_overrides": {
            "2": {"phases": [{"name": "test", "network": "none",
                              "cmd": ["sh", "-c", "cd /work && npm test -- --verbose"]}]},
        },
    }
    jsonschema.Draft202012Validator(s).validate(example)

def test_schema_rejects_unknown_top_level_key():
    s = json.loads(SCHEMA.read_text())
    bad = {"gate_id": "x", "transition": "stage6_validate",
           "required_signals": [], "retry_policy": {
               "max_attempts": 1, "retryable_failures": [], "non_retryable_failures": [],
               "timeout_retryable": False},
           "sandbox": {"base_image": "x", "time_budget_seconds": 1,
                       "memory_limit_mib": 1, "pids_limit": 1,
                       "env_allowlist": [], "phases": []},
           "stowaway": "boom"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(s).validate(bad)

def test_schema_rejects_unknown_transition_value():
    s = json.loads(SCHEMA.read_text())
    bad = {"gate_id": "x", "transition": "stage7_distroless",  # not in enum
           "required_signals": [], "retry_policy": {
               "max_attempts": 1, "retryable_failures": [], "non_retryable_failures": [],
               "timeout_retryable": False},
           "sandbox": {"base_image": "x", "time_budget_seconds": 1,
                       "memory_limit_mib": 1, "pids_limit": 1,
                       "env_allowlist": [], "phases": []}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(s).validate(bad)
```

```python
# tests/gates/test_catalog_loader.py
import pytest
from pathlib import Path
from codegenie.gates.catalog_loader import load, load_all
from codegenie.gates.errors import GateCatalogInvalid

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "src/codegenie/gates/catalog"

def test_stub_yaml_loads_cleanly():
    entry = load(CATALOG_DIR / "stage6_validate.yaml")
    assert entry.gate_id == "stage6_validate"

def test_load_all_skips_underscore_prefixed_files():
    result = load_all(CATALOG_DIR)
    assert "stage6_validate" in result
    # _schema.json is JSON, not YAML; still ensure no "_*" yaml leak
    assert not any(k.startswith("_") for k in result)

def test_invalid_yaml_raises_gate_catalog_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("gate_id: x\ntransition: not_a_valid_value\n")
    with pytest.raises(GateCatalogInvalid) as exc:
        load(bad)
    assert "bad.yaml" in str(exc.value)

def test_unknown_top_level_key_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "gate_id: x\ntransition: stage6_validate\nrequired_signals: []\n"
        "retry_policy: {max_attempts: 1, retryable_failures: [], non_retryable_failures: [], timeout_retryable: false}\n"
        "sandbox: {base_image: x, time_budget_seconds: 1, memory_limit_mib: 1, pids_limit: 1, env_allowlist: [], phases: []}\n"
        "extra_garbage: true\n"
    )
    with pytest.raises(GateCatalogInvalid):
        load(bad)

def test_catalog_entry_is_frozen():
    entry = load(CATALOG_DIR / "stage6_validate.yaml")
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        entry.gate_id = "other"
```

Run; confirm failures (file not found / import error), commit, then implement.

### Green — make it pass

Write the JSON schema with `"additionalProperties": false` at every object level (top-level, `retry_policy`, `sandbox`, each `phases[]` entry, `attempt_overrides` values). The schema enforces:
- `transition`: `{"enum": ["stage6_validate", "stage6_validate_loose"]}`.
- `phases[].network`: `{"enum": ["none", "scoped"]}`.
- `retry_policy.max_attempts`: `{"type": "integer", "minimum": 1}`.

Write the stub `stage6_validate.yaml` with the minimum schema-valid shape — all arrays empty, `base_image` set to a placeholder digest like `"cgr.dev/chainguard/node@sha256:0000000000000000000000000000000000000000000000000000000000000000"`.

`catalog_loader.py`:
- `CatalogEntry(BaseModel)` mirrors the schema; nested classes `RetryPolicyEntry`, `SandboxEntry`, `PhaseEntry` similarly frozen + extra-forbid.
- `load`: open file, `yaml.safe_load`, `_validator.validate`, `CatalogEntry.model_validate(data)`, catch both `jsonschema.ValidationError` and `pydantic.ValidationError` → raise `GateCatalogInvalid`.

### Refactor — clean up

- Read the schema **once** at module import; cache the `Draft202012Validator` instance.
- `load_all` returns `dict[str, CatalogEntry]` keyed by `gate_id`; duplicate `gate_id` across files raises `GateCatalogInvalid`.
- Edge case (arch §Edge case 13): error message includes the offending key path inside the YAML; use `err.absolute_path` from `jsonschema` and join with `/`.
- The schema file lives **inside** the package (`src/codegenie/gates/catalog/_schema.json`) so it ships with the wheel; do not put it under `docs/`.
- ADR-0014 inheritance: `required_signals` is `array[string]` — open kind registry. The schema does NOT enumerate kinds (would close the registry); validation that each name is a registered kind is `SandboxSpecBuilder`'s job (S3-01).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/catalog/_schema.json` | New file — JSON Schema for gate catalog entries |
| `src/codegenie/gates/catalog/stage6_validate.yaml` | New file — empty-but-valid stub (S3-05 populates) |
| `src/codegenie/gates/catalog_loader.py` | New file — load/validate/return `CatalogEntry` Pydantic model |
| `tests/gates/test_catalog_schema.py` | New test — schema validates itself + a full example; rejects unknown keys |
| `tests/gates/test_catalog_loader.py` | New test — load stub, error paths, frozen entry |

## Out of scope

- **Populating `stage6_validate.yaml` with real `required_signals` / phases** — S3-05.
- **`stage6_validate_loose.yaml`** — S3-05.
- **`SandboxSpecBuilder.for_gate`** — S3-01.
- **`StrictAndGate.from_yaml`** — S4-05 (or wherever the YAML → Gate instance translation lands).
- **Catalog hot-reload / watcher** — not a Phase 5 feature.
- **Digest pinning of `sandbox-policy.yaml`** — S3-05 (different file; this story handles gate catalog only).

## Notes for the implementer

- Use `jsonschema` library; the project already imports it (per `CLAUDE.md` — `RepoContext` validation). Pin Draft 2020-12.
- `additionalProperties: false` MUST be set at every object level — without it, the "unknown top-level key" test passes trivially because `jsonschema` allows unknown keys by default.
- The Pydantic `CatalogEntry` model is structural insurance against `jsonschema` drift. The double-check (schema first, Pydantic second) is intentional belt-and-suspenders; do not collapse them.
- YAML files load via `yaml.safe_load` — never `yaml.load`. The schema rejects anything `safe_load` cannot parse (it never returns objects with attributes Pydantic doesn't expect).
- The stub's `base_image` placeholder digest is intentionally invalid (`0`-repeated) — S3-05 replaces it with the real Chainguard digest. Document this in a comment at the top of `stage6_validate.yaml`.
- The error message for `GateCatalogInvalid` should always include the file path and the YAML key path; the operator will read it as a CLI-exit-2 message (arch §Edge case 13).
- 90/80 coverage floor: cover schema-rejection paths, file-not-found path, duplicate-`gate_id` path in `load_all`.
