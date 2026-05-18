# Story S2-02 — `PluginManifest` Pydantic model + YAML loader returning `Result`

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (newtypes + free-function smart constructors), S2-01 (`src/codegenie/plugins/__init__.py`, `tests/unit/plugins/__init__.py`, `tests/unit/plugins/conftest.py`, `tests/fixtures/plugins/__init__.py`)
**ADRs honored:** ADR-0002, ADR-0004, ADR-0010, ADR-0011, production ADR-0031, Phase-1 ADR-0009 (single safe-yaml chokepoint)

## Validation notes (2026-05-18)

Hardened from `Ready` → `HARDENED` by `phase-story-validator`. Full audit at `_validation/S2-02-plugin-manifest-pydantic.md`. Substantive changes from the original draft:

- **Route through `safe_yaml.load` chokepoint** (Design-Patterns F1 / Test-Quality F8 — `block`). The original prescribed a hand-rolled `path.open("rb")` + `yaml.safe_load(raw)` + manual `stat().st_size > 1 << 20` cap, re-introducing the alias-amplification + symlink + non-mapping-top-level vulnerabilities that `codegenie.parsers.safe_yaml.load` (Phase 1 ADR-0009) already closes. The loader now calls `safe_yaml.load(path, max_bytes=1 << 20)` and catches the typed exceptions it defines.
- **Tagged-union `ManifestError`** (Design-Patterns F2 / Test-Quality F9 — `block`). The original `ManifestError(reason: Literal[4 strings], detail: str, path: Path | None)` is anaemic — ADR-0010 §Decision 3 mandates tagged-union sum types on every state machine. Replaced with `SizeCapExceeded | MalformedYaml | SchemaViolation | IoError` (Pydantic discriminated union on `kind`), each variant carrying exactly the evidence it needs. Consumers `match err:` exhaustively under `mypy --strict`.
- **`signature: str | None` field dropped** (Consistency F3 — `block`). Production ADR-0031 §Plugin manifest has no `signature` field; ADR-0011 §Decision puts the integrity check in the sibling file `plugins/PLUGINS.lock`, not in the per-plugin manifest. The original story invented a manifest-level field with no source-of-truth backing. Phase 11 Sigstore work substitutes the *loader's* verification adapter, not a manifest field.
- **`scope` shape divergence with arch documented** (Consistency F1 — `block`). Phase-arch §Data model line 755 shows `PluginManifest.scope: PluginScope` (the post-lift sum-type). S2-02 ships `scope: ManifestScope` (the raw `str | list[str]` form per production ADR-0031 §Plugin manifest YAML). S2-04 produces a `ResolvedManifest` whose `scope: PluginScope` lift converts at resolution time. Arch §Data model is wrong by this much; tracked as an arch follow-up in the validation report.
- **`precedence` default = `50`** (Consistency F2 — `block`). Three-way conflict: arch line 756 says `= 0`; story said `= 50`; production ADR-0031 line 108 comment says "default 50". Production-ADR wins (it is the canonical YAML contract). Arch line 756 is wrong; arch follow-up logged.
- **PluginId / PrimitiveName / ProbeId lift via free-function parsers** (Consistency F6 / Design-Patterns F4). `NewType` cannot host classmethods (S1-01 Notes §"Arch ↔ NewType API drift"). Use `codegenie.types.parsers.parse_plugin_id(s) -> Result[PluginId, ParseError]` for `name` and every `extends` entry; `PrimitiveName` and `ProbeId` keys on `ManifestContributes.{adapters,probes}` are typed but lifted by Pydantic identity (newtype is runtime-identity to `str`).
- **`ManifestRequirements` shape pinned** (Consistency F5). `external_tools: list[str] = []`, `optional: list[str] = []` per production ADR-0031 lines 102-106.
- **Per-error-mode red tests** (Coverage F12 / Test-Quality F2). Single red test was thin for four error modes; the TDD plan now ships one named red test per failure mode plus a happy-path round-trip red test.
- **Defaults pinned by AC** (Coverage F6). New AC asserts a minimal-YAML load materialises every documented default via literal equality.
- **Real YAML round-trip, not JSON** (Coverage F8 / Test-Quality F3). The original `model_dump_json` round-trip tested `yaml.safe_load(json_bytes)`; replaced with `yaml.safe_dump(model.model_dump(mode="json"))` + a hand-authored block-style fixture.
- **Hypothesis property test promoted to AC** (Test-Quality F12). Was "optional, low priority"; promoted to required because it catches the entire class of "I added a field but forgot to handle round-trip" mutants in one shot.
- **PEP-440 dropped** (Design-Patterns F7). `version` is `Annotated[str, StringConstraints(min_length=1)]` — non-empty only. No Phase 3 consumer compares versions semantically; Phase 11 substitutes a real PEP-440 check.
- **`_read_capped_bytes` Refactor step dropped** (Design-Patterns F9). `safe_yaml.load` is the chokepoint; the Refactor section now scopes only to the in-file `_render_field_errors` helper.
- **Open/Closed extension seam documented** (Design-Patterns F6). `extra="forbid"` is the intended discipline; future manifest-field additions (Phase 7 distroless `contributes.containers`) are explicit, ADR-gated edits to this file — not a smell.
- **Precedent citation corrected** (Consistency F8). The original cited "Phase 2 S3-03" which doesn't exist; the real precedents are Phase 2 `S2-02-conventions-catalog-loader.md` (1 MiB on catalog YAML) and `S1-04-tccm-model-loader.md` (1 MiB on TCCM YAML).

## Context

Every plugin under `plugins/{slug}/` carries a `plugin.yaml` whose shape is fixed by production ADR-0031 §Plugin manifest. Phase 3 ships the **typed loader** for that file: a frozen Pydantic `PluginManifest` model with `extra="forbid"` (so a typo in a manifest field surfaces as a parse error at load time, not as silent ignored config), and a `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` smart constructor that routes through the `safe_yaml.load` chokepoint (Phase 1 ADR-0009) and returns the discriminated `Ok`/`Err` from `codegenie.result.Result` rather than raising. This story lands the **schema + loader only** — the filesystem walk that *finds* manifests and the integrity-check that *verifies* the surrounding tree are S2-03; the resolver that consumes `scope`/`precedence`/`extends` and lifts `ManifestScope → PluginScope` is S2-04.

The manifest is also the place ADR-0004's discipline lands at the data level: the `contributes.tccm` reference points to the plugin's `tccm.yaml`, where task-class-specific capabilities (`provides.vuln_index_capabilities`, etc.) live — **not** on the kernel `Plugin` Protocol. Per ADR-0011, the per-plugin integrity check lives in the sibling `plugins/PLUGINS.lock` file (S2-03), **not** in the manifest itself — Phase 11 Sigstore substitutes the loader's verification adapter, leaving the manifest schema untouched.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — `Plugin.manifest: PluginManifest` is the typed attribute.
  - `../phase-arch-design.md §Data model` lines 750-757 — `PluginManifest` skeleton (`name`, `version`, `scope`, `precedence`, `extends`). **Note:** the arch shows `scope: PluginScope` (post-lift sum-type) and `precedence: int = 0`; both are wrong for the *load-time* shape. This story implements the **production ADR-0031 §Plugin manifest** canonical surface (raw `ManifestScope`; `precedence: int = 50`; `contributes`; `requirements`). Arch follow-up logged in `_validation/S2-02-plugin-manifest-pydantic.md §Arch amendments`.
  - `../phase-arch-design.md §Edge cases` — malformed YAML rejection; unknown-field rejection (`extra="forbid"`).
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — manifest validation is **a loader concern, not a registry one** ("Keep [the registry] dumb; validate on use").
  - `../ADRs/0004-plugin-private-capabilities-via-tccm.md` — `contributes.tccm` references the plugin's TCCM file; capability namespaces live there, not in the manifest.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — smart constructor + tagged-union discipline; `ManifestError` is a state machine and must be a tagged union.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `PLUGINS.lock` is the **sibling-file** integrity check, NOT a manifest field. No `signature` field on `PluginManifest`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Plugin manifest (lines 75-109) — the canonical YAML shape; ship every documented field; `precedence` default `50`.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` — the **chokepoint**; `safe_yaml.load(path, max_bytes=...)` raises `SizeCapExceeded` *before any bytes are read*, `MalformedYAMLError` (empty file / yaml errors / non-mapping top-level), `SymlinkRefusedError`, and bubbles `OSError`. No bypass allowed by the `forbidden-patterns` pre-commit hook.
  - `src/codegenie/result.py` — the `Result` sum type (`from codegenie.result import Result, Ok, Err`).
  - `src/codegenie/tccm/loader.py` — the canonical sibling loader; mirror its `_classify(ValidationError) → typed reason` translation table, its `safe_yaml.load` routing, its multi-red-test discipline, and its AST-walk fence preventing raw `yaml` imports.
  - `src/codegenie/types/identifiers.py` + `src/codegenie/types/parsers.py` (S1-01) — `PluginId`, `PrimitiveName`, `ProbeId` newtypes + `parse_plugin_id(s) -> Result[PluginId, ParseError]` free-function smart constructors. `NewType` cannot host classmethods; the lift is a free function.
  - `src/codegenie/plugins/registry.py` (S2-01) — the `Plugin` Protocol's `manifest` attribute references this model.
  - Phase 2 precedent: `S2-02-conventions-catalog-loader.md` (1 MiB max_bytes on catalog YAML) and `S1-04-tccm-model-loader.md` (1 MiB on TCCM YAML, the seven-reason tagged-union translation pattern).

## Goal

Ship a `PluginManifest` Pydantic model (frozen, `extra="forbid"`) covering every production-ADR-0031-documented manifest field, plus `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` that loads YAML via the `safe_yaml.load(path, max_bytes=1 << 20)` chokepoint, lifts `name`/`extends` strings to `PluginId` via the S1-01 free-function smart constructor, validates the result via Pydantic, and returns a tagged-union `Result` carrying typed error variants — **never raising** for any documented failure mode.

## Acceptance criteria

### Schema surface

- [ ] **AC-1** — `src/codegenie/plugins/manifest.py` exports `PluginManifest`, `ManifestScope`, `ManifestContributes`, `ManifestRequirements`, and the four `ManifestError` variants (`SizeCapExceeded`, `MalformedYaml`, `SchemaViolation`, `IoError`) plus the `ManifestError` discriminated-union alias. Every Pydantic model uses `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] **AC-2** — `PluginManifest` covers exactly: `name: PluginId`, `version: Annotated[str, StringConstraints(min_length=1)]` (non-empty; semantic PEP-440 validation deferred to Phase 11), `scope: ManifestScope`, `extends: tuple[PluginId, ...] = ()`, `precedence: int = 50` (matches production ADR-0031 default), `contributes: ManifestContributes`, `requirements: ManifestRequirements = ManifestRequirements()`. **No `signature` field** (per ADR-0011 the integrity check is `plugins/PLUGINS.lock`, S2-03).
- [ ] **AC-3** — `ManifestScope` covers: `task_class: str | list[str]`, `languages: str | list[str]`, `build_systems: str | list[str]` — where `"*"` is the wildcard literal carried as a raw string. **Sum-type lift to `PluginScope` happens in S2-04**, not here. Each field accepts either a single string or a list of strings; mixed types raise schema_violation.
- [ ] **AC-4** — `ManifestContributes` covers: `adapters: dict[PrimitiveName, str] = {}` (primitive-name → `module:Class` string), `tccm: str = "./tccm.yaml"`, `subgraph: str = "./subgraph/"`, `skills: str = "./skills/"`, `recipes: str = "./recipes/"`, `probes: tuple[ProbeId, ...] = ()`. (Validating `module:Class` format on `adapters` values is S2-04's job — keep the loader dumb per ADR-0002.)
- [ ] **AC-5** — `ManifestRequirements` covers: `external_tools: tuple[str, ...] = ()`, `optional: tuple[str, ...] = ()`. Both `frozen=True, extra="forbid"`. Matches production ADR-0031 lines 102-106.

### Error model — tagged union (ADR-0010 §Decision 3)

- [ ] **AC-6** — `ManifestError` is a Pydantic discriminated union (`Field(discriminator="kind")`) over four variants, each carrying its evidence:
  - `SizeCapExceeded(kind: Literal["size_cap_exceeded"], path: Path, actual_bytes: int, cap: int)`
  - `MalformedYaml(kind: Literal["malformed_yaml"], path: Path, message: str)`
  - `SchemaViolation(kind: Literal["schema_violation"], path: Path, field_errors: tuple[str, ...])` — `field_errors` rendered from `pydantic.ValidationError.errors()` via `".".join(str(p) for p in e["loc"])`.
  - `IoError(kind: Literal["io_error"], path: Path, errno: int, message: str)`
- [ ] **AC-7** — A `match err: case SizeCapExceeded(): ... case MalformedYaml(): ... case SchemaViolation(): ... case IoError(): ...` over an instance of the union type-checks under `mypy --strict` with `assert_never(err)` after the four cases (exhaustiveness gate). At least one such match block lives in the test suite.

### Loader behaviour

- [ ] **AC-8** — `PluginManifest.from_yaml(cls, path: Path) -> Result[PluginManifest, ManifestError]` (classmethod) routes through `codegenie.parsers.safe_yaml.load(path, max_bytes=1 << 20)`. **No raw `yaml.*` imports** in `manifest.py`; AST-walk fence test enforces.
- [ ] **AC-9** — Translation table from raw exceptions to `ManifestError` variants is pinned (matches `tccm/loader.py:_classify` discipline):
  - `SizeCapExceeded` from `safe_yaml` → `Err(SizeCapExceeded(path, actual_bytes=path.stat().st_size, cap=1 << 20))` (re-stat for `actual_bytes`; if re-stat itself raises, fall through to `IoError`).
  - `MalformedYAMLError` from `safe_yaml` → `Err(MalformedYaml(path, message=str(exc)))`. Covers: empty file, syntactically-broken YAML, **top-level non-mapping** (scalar, list, `null`).
  - `SymlinkRefusedError` from `safe_yaml` → `Err(IoError(path, errno=errno.ELOOP, message="symlink refused"))`. (Per ADR-0011 honest-framing — symlinks are a TOCTOU vector; `safe_yaml` refuses them at the chokepoint, the loader surfaces it under `io_error`.)
  - `OSError` (any subclass: `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, etc.) → `Err(IoError(path, errno=exc.errno, message=str(exc)))`.
  - `pydantic.ValidationError` from `PluginManifest.model_validate(data)` → `Err(SchemaViolation(path, field_errors=tuple(".".join(str(p) for p in e["loc"]) for e in exc.errors())))`.
- [ ] **AC-10** — `name` lift: after Pydantic validates the raw dict, `name: PluginId` is lifted from `str` via `codegenie.types.parsers.parse_plugin_id`. Lift failure → `Err(SchemaViolation(path, field_errors=("name",)))`. No `cast()`.
- [ ] **AC-11** — `extends` lift: each entry in the YAML list is lifted via `parse_plugin_id`. First-failure short-circuits to `Err(SchemaViolation(path, field_errors=("extends",)))` with the offending index documented in `SchemaViolation.message` extension if added later (not required this story).
- [ ] **AC-12** — **`from_yaml` never raises** for any input. A property test (Hypothesis, see TDD plan) feeds arbitrary bytes via `tmp_path.write_bytes` and asserts `from_yaml(path)` returns a `Result` for every input — never escapes an exception. Catches missed `except` arms.

### Defaults — pinned by literal equality

- [ ] **AC-13** — Loading a minimal valid YAML (`name`, `version`, `scope.*`, `contributes: {}`) materialises every documented default exactly:
  - `m.precedence == 50` (NOT 0 — arch §C2 line 756 contradicts production-ADR-0031; production-ADR wins).
  - `m.extends == ()`.
  - `m.requirements == ManifestRequirements()` AND `m.requirements.external_tools == ()` AND `m.requirements.optional == ()`.
  - `m.contributes.tccm == "./tccm.yaml"` AND `.subgraph == "./subgraph/"` AND `.skills == "./skills/"` AND `.recipes == "./recipes/"` AND `.probes == ()` AND `.adapters == {}`.

### `extra="forbid"` at every submodel boundary

- [ ] **AC-14** — Unknown-field rejection is enforced at the top level AND on every submodel (`ManifestScope`, `ManifestContributes`, `ManifestRequirements`). One parametrized test per submodel + one at the top level — four cases total. Each catches the case where a refactor accidentally drops `extra="forbid"` from a submodel.

### Round-trip fidelity

- [ ] **AC-15** — YAML round-trip preserves equality: `m == PluginManifest.from_yaml(write(yaml.safe_dump(m.model_dump(mode="json")))).unwrap()` for a fully-populated manifest. **Not** `model_dump_json` (which trivially round-trips through JSON-via-YAML). One concrete hand-authored block-style YAML fixture also round-trips — exercises block sequences, block mappings, and null sugar (`~`).
- [ ] **AC-16** — Hypothesis property test: for any randomly generated valid manifest (`name`, `version`, varying `precedence` ∈ ℕ, varying `extends` length 0–5, all submodel defaults vs populated), `from_yaml(yaml.safe_dump(m.model_dump(mode="json")))` reconstructs `m` exactly. At least 100 examples.

### TDD red-first discipline

- [ ] **AC-17** — Five distinct red tests committed before any green code, one per failure mode + one happy:
  - `test_unknown_field_returns_err_schema_violation`
  - `test_malformed_yaml_returns_err_malformed_yaml` (covers empty file + invalid syntax + non-mapping top-level + null document — parametrized)
  - `test_oversized_file_returns_err_size_cap_exceeded`
  - `test_io_error_routes_to_err_io_error` (covers missing path + permission-denied + IsADirectoryError + broken symlink — parametrized; `pytest.skip` on Windows where `chmod 000` is moot)
  - `test_happy_path_round_trip` (the fully-populated YAML fixture round-trip from AC-15)

### Static + chokepoint fences

- [ ] **AC-18** — AST-walk source-scan fence test (`test_manifest_module_does_not_bypass_safe_yaml`) asserts `src/codegenie/plugins/manifest.py` does not import `yaml`, `pyyaml`, `yaml.Loader`, `yaml.FullLoader`, or `yaml.SafeLoader`, and contains no string literal `"safe_load"`. Mirrors the pattern at `tests/unit/tccm/test_loader.py` (search for the analogous fence).
- [ ] **AC-19** — `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/manifest.py`, `tests/unit/plugins/test_manifest.py`, and `tests/fixtures/plugins/sample_plugin_yaml.py`. No `# type: ignore`. No `Any`. No `dict[str, Any]`.

## Implementation outline

1. **Define submodels.** `ManifestScope`, `ManifestContributes`, `ManifestRequirements` — three frozen Pydantic models with `extra="forbid"`. `ManifestScope.task_class | languages | build_systems: str | list[str]` (raw — sum-type lift is S2-04). `ManifestContributes.adapters: dict[PrimitiveName, str]` (Pydantic v2 accepts `NewType` keys via identity). `ManifestContributes.probes: tuple[ProbeId, ...]` (immutable default — Pydantic v2 handles `tuple[T, ...]` defaults; mutability footgun avoided).
2. **Define `PluginManifest`.** Top-level model composing the submodels. `name: PluginId`, `version: Annotated[str, StringConstraints(min_length=1)]`, `extends: tuple[PluginId, ...] = ()`, `precedence: int = 50`. Use `@field_validator("name", mode="after")` and `@field_validator("extends", mode="after", each_item=True)` to lift each `str` through `parse_plugin_id`; on `Err(ParseError)`, the validator `raise ValueError(...)` which Pydantic wraps into the outer `ValidationError`, which `from_yaml` then translates to `SchemaViolation`.
3. **Define `ManifestError` tagged union.** Four Pydantic models (`SizeCapExceeded`, `MalformedYaml`, `SchemaViolation`, `IoError`), each `frozen=True, extra="forbid"`, each carrying its `kind: Literal[...]` discriminator. `ManifestError = Annotated[SizeCapExceeded | MalformedYaml | SchemaViolation | IoError, Field(discriminator="kind")]`.
4. **Implement `from_yaml(cls, path: Path) -> Result[PluginManifest, ManifestError]`:**
   - Call `safe_yaml.load(path, max_bytes=1 << 20)` inside one `try` block.
   - `except SizeCapExceeded as e:` → re-stat (guarded) to extract `actual_bytes`; return `Err(SizeCapExceeded(path, actual_bytes, cap=1 << 20))`. If re-stat itself raises, fall through to the `OSError` arm.
   - `except SymlinkRefusedError as e:` → `Err(IoError(path, errno=errno.ELOOP, message="symlink refused"))`.
   - `except MalformedYAMLError as e:` → `Err(MalformedYaml(path, message=str(e)))`.
   - `except OSError as e:` → `Err(IoError(path, errno=e.errno or 0, message=str(e)))`. Order: comes after `SizeCapExceeded`/`SymlinkRefusedError` so those typed wrappers win.
   - On success, the `safe_yaml.load` return value is `Mapping[str, JSONValue]`. Call `PluginManifest.model_validate(dict(data))`.
   - `except pydantic.ValidationError as e:` → render `field_errors = tuple(".".join(str(p) for p in err["loc"]) for err in e.errors())`; return `Err(SchemaViolation(path, field_errors))`.
   - Else `Ok(manifest)`.
5. **Sample-fixture helper at `tests/fixtures/plugins/sample_plugin_yaml.py`:** functions to write valid + each invalid shape into a `tmp_path`. `write_minimal(tmp_path) -> Path`, `write_full(tmp_path) -> Path`, `write_with_typo(tmp_path, submodel: str) -> Path`, `write_malformed(tmp_path, kind: str) -> Path`, `write_oversized(tmp_path) -> Path`, etc. Helpers return `Path`. No imports from `codegenie.plugins.manifest` (avoid circular-import smell in fixtures).
6. **Tests (in this order — red first):** See TDD plan.

## TDD plan — red / green / refactor

### Red — five failing tests committed first (AC-17)

Test file path: `tests/unit/plugins/test_manifest.py`

#### 1) `test_unknown_field_returns_err_schema_violation` — top level

```python
from pathlib import Path

from codegenie.plugins.manifest import ManifestError, PluginManifest, SchemaViolation


def test_unknown_field_returns_err_schema_violation(tmp_path: Path) -> None:
    """`extra="forbid"` is the load-bearing schema discipline (ADR-0002 §Pattern fit
    + ADR-0031 §Schema enforcement). A typo in `precedence` must not silently
    fall back to the default — it must surface as a typed Err at load time."""
    path = tmp_path / "plugin.yaml"
    path.write_text(
        """\
name: vulnerability-remediation--node--npm
version: 0.1.0
scope:
  task_class: vulnerability-remediation
  languages: [javascript]
  build_systems: [npm]
precedance: 50          # typo — should NOT be silently accepted
contributes:
  tccm: ./tccm.yaml
""",
        encoding="utf-8",
    )

    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SchemaViolation)
    assert "precedance" in " ".join(err.field_errors)
```

#### 2) `test_unknown_field_rejected_in_each_submodel` — parametrized over submodels

```python
import pytest

@pytest.mark.parametrize(
    "submodel,yaml_patch,expected_substr",
    [
        ("contributes",  "contributes:\n  tccmm: ./tccm.yaml\n",        "tccmm"),
        ("requirements", "requirements:\n  external_toolz: [npm]\n",   "external_toolz"),
        ("scope",        "scope:\n  task_classs: vuln\n  languages: '*'\n  build_systems: '*'\n", "task_classs"),
    ],
    ids=["contributes", "requirements", "scope"],
)
def test_unknown_field_rejected_in_each_submodel(tmp_path, submodel, yaml_patch, expected_substr):
    """Every submodel must independently enforce `extra="forbid"`. A refactor that
    drops `model_config = ConfigDict(extra="forbid")` from any submodel survives
    the top-level test (1) above — only this per-submodel sweep catches it."""
    ...  # build YAML body with the patched submodel; assert SchemaViolation + substring
```

#### 3) `test_malformed_yaml_returns_err_malformed_yaml` — parametrized

```python
@pytest.mark.parametrize(
    "body,case_id",
    [
        (b"",                                    "empty_file"),
        (b"name: foo\n  : invalid-indent\n",     "invalid_syntax"),
        (b"- a\n- b\n",                          "top_level_list"),
        (b'"hello"\n',                           "top_level_scalar"),
        (b"null\n",                              "null_document"),
    ],
    ids=["empty_file", "invalid_syntax", "top_level_list", "top_level_scalar", "null_document"],
)
def test_malformed_yaml_returns_err_malformed_yaml(tmp_path, body, case_id):
    """Every non-mapping or syntactically broken YAML input must surface as a
    typed `MalformedYaml` variant — never a `SchemaViolation`. The discriminator
    is load-bearing for Phase 4's fail-loud handling (per Phase 4 README on the
    `NotApplicable` trigger)."""
    ...
```

#### 4) `test_oversized_file_returns_err_size_cap_exceeded`

```python
def test_oversized_file_returns_err_size_cap_exceeded(tmp_path, monkeypatch):
    """`safe_yaml.load` enforces the cap via `os.fstat(fd).st_size` *before* any
    bytes are read (Phase 1 ADR-0009 §safe_yaml — alias-amplification defense).
    A naive impl that reads-then-checks burns memory on a 2 GiB hostile file.
    We assert the size-cap path returns `SizeCapExceeded` AND that the actual
    bytes were not consumed (chokepoint short-circuits)."""
    path = tmp_path / "big.yaml"
    path.write_bytes(b"x" * (2 << 20))   # 2 MiB > 1 MiB cap

    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SizeCapExceeded)
    assert err.path == path
    assert err.cap == 1 << 20
    assert err.actual_bytes >= 2 << 20    # exact actual; doesn't read the file
```

#### 5) `test_io_error_routes_to_err_io_error` — parametrized

```python
import os
import stat
import sys

@pytest.mark.parametrize(
    "fixture_factory,case_id",
    [
        (lambda p: p / "does_not_exist.yaml",              "missing_path"),
        (lambda p: p,                                       "is_a_directory"),
        # permission-denied & broken-symlink populated by helper functions
        # that pytest.skip on Windows where chmod / symlink semantics differ.
    ],
    ids=["missing_path", "is_a_directory"],
)
def test_io_error_routes_to_err_io_error(tmp_path, fixture_factory, case_id):
    """`from_yaml` never raises; every OSError subclass (FileNotFoundError,
    PermissionError, IsADirectoryError, ELOOP) routes to a typed `IoError`
    variant carrying the errno."""
    path = fixture_factory(tmp_path)
    result = PluginManifest.from_yaml(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IoError)
    assert err.errno != 0


def test_permission_denied_routes_to_io_error(tmp_path):
    if sys.platform.startswith("win"):
        pytest.skip("chmod 000 semantics differ on Windows")
    path = tmp_path / "no_read.yaml"
    path.write_text("name: x\nversion: 0.1.0\nscope: {task_class: t, languages: '*', build_systems: '*'}\ncontributes: {}\n")
    path.chmod(0)
    try:
        result = PluginManifest.from_yaml(path)
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert result.is_err()
    assert isinstance(result.unwrap_err(), IoError)
```

#### 6) `test_happy_path_round_trip` — hand-authored block-style YAML

```python
def test_happy_path_round_trip(tmp_path):
    """A fully-populated, hand-authored, block-style YAML fixture round-trips
    to byte-identical reconstruction. Catches mutants that mishandle YAML's
    block-style sequences (`extends:\n  - foo`) vs JSON-flow sugar."""
    yaml_body = """\
name: vulnerability-remediation--node--npm
version: 0.1.0
scope:
  task_class: vulnerability-remediation
  languages: [javascript, typescript]
  build_systems: [npm]
extends:
  - vulnerability-remediation--node--star
precedence: 100
contributes:
  adapters:
    dep_graph: adapters.npm_dep_graph:NpmDepGraphAdapter
    scip: adapters.node_scip:NodeScipAdapter
  tccm: ./tccm.yaml
  subgraph: ./subgraph/
  skills: ./skills/
  recipes: ./recipes/
  probes:
    - NpmLockfileProbe
    - PackageJsonProbe
requirements:
  external_tools:
    - npm
  optional:
    - corepack
"""
    path = tmp_path / "plugin.yaml"
    path.write_text(yaml_body, encoding="utf-8")

    result = PluginManifest.from_yaml(path)
    assert result.is_ok()
    m = result.unwrap()
    assert m.precedence == 100
    assert m.extends == (PluginId("vulnerability-remediation--node--star"),)
    assert m.contributes.tccm == "./tccm.yaml"
    assert m.requirements.external_tools == ("npm",)

    # Round-trip via safe_dump → load → equality.
    import yaml as _yaml
    round_trip_path = tmp_path / "round_trip.yaml"
    round_trip_path.write_text(_yaml.safe_dump(m.model_dump(mode="json"), sort_keys=False))
    m2 = PluginManifest.from_yaml(round_trip_path).unwrap()
    assert m2 == m
```

### Green — minimal pass

- Submodels + `PluginManifest` Pydantic shape (Implementation §1, §2).
- `ManifestError` tagged union (Implementation §3).
- `from_yaml` translation table (Implementation §4).
- Field validators for `name` / `extends` lift via `parse_plugin_id`.

### Refactor

- **`_render_field_errors(ve: pydantic.ValidationError) -> tuple[str, ...]`** — file-local helper extracting the `loc` rendering. Do NOT add I/O helpers; `safe_yaml.load` is the chokepoint.
- **Defaults-pin test** (AC-13): `test_minimal_yaml_pins_documented_defaults` asserts every literal default by equality. Catches "I changed a default" mutants in one shot.
- **Field-flip metamorphic test** (Test-Quality F10): `test_field_change_breaks_equality` parametrized over a few `(field, mutator)` pairs — asserts `m != m.model_copy(update={field: new_value})` and `hash(m) != hash(...)`. Pins `frozen=True` participates in equality.
- **`test_frozen_rejects_mutation`** asserts `m.precedence = 99` raises (`ValidationError` or `TypeError`).
- **Hypothesis property test (AC-16)** — required, not optional. Promote from refactor to green if executor budget allows; otherwise land here. Strategy generates `precedence` ∈ [0, 10_000], `extends` length 0–5, `signature`/version varying within their constraints. Asserts round-trip equality.
- **Never-raises property** (AC-12): `@given(st.binary(min_size=0, max_size=8192))` writes the bytes to `tmp_path / "f.yaml"`, calls `PluginManifest.from_yaml(path)`, asserts `isinstance(result, (Ok, Err))` — never escapes. Catches missed `except` arms across the broadest input space.
- **Exhaustive-match callsite test** (AC-7): a non-test helper in the test module performs a `match err: case SizeCapExceeded(): ...; case MalformedYaml(): ...; case SchemaViolation(): ...; case IoError(): ...; case _: assert_never(err)` — `mypy --strict` enforces. Pins the tagged-union contract.
- **AST-walk fence test** (AC-18): `test_manifest_module_does_not_bypass_safe_yaml` parses `src/codegenie/plugins/manifest.py` via `ast.parse(...)` and asserts no `Import`/`ImportFrom` references the `yaml` module.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/manifest.py` | NEW — Pydantic models (`PluginManifest`, `ManifestScope`, `ManifestContributes`, `ManifestRequirements`), tagged-union `ManifestError`, `from_yaml` classmethod, file-local `_render_field_errors` helper. |
| `tests/unit/plugins/test_manifest.py` | NEW — five red tests + defaults-pin + frozen-rejects + field-flip + Hypothesis round-trip + Hypothesis never-raises + exhaustive-match callsite + AST-walk fence. |
| `tests/fixtures/plugins/sample_plugin_yaml.py` | NEW — `write_minimal`, `write_full`, `write_with_typo(submodel)`, `write_malformed(kind)`, `write_oversized`, `write_with_invalid_plugin_id` helpers. No imports from `codegenie.plugins.manifest`. |

**Preconditions from S2-01 + S1-01 (must be `GREEN` before this story starts):**
- `src/codegenie/plugins/__init__.py` exists (S2-01).
- `tests/unit/plugins/__init__.py` + `tests/unit/plugins/conftest.py` exist (S2-01).
- `tests/fixtures/plugins/__init__.py` exists (S2-01).
- `src/codegenie/types/identifiers.py` exports `PluginId`, `PrimitiveName`, `ProbeId` (S1-01).
- `src/codegenie/types/parsers.py` exports `parse_plugin_id(s) -> Result[PluginId, ParseError]` (S1-01).
- `src/codegenie/parsers/safe_yaml.py` exposes `load(path, *, max_bytes, max_depth=64)` (Phase 1).
- Do NOT recreate or blank any of the above; `mypy --strict` will surface any drift.

## Out of scope

- **Filesystem walk over `plugins/*/plugin.yaml`** — handled by S2-03.
- **`PLUGINS.lock` integrity check** — handled by S2-03 (the manifest loader is purely about a single YAML file). Per ADR-0011 the integrity check is a *sibling-file* mechanism, not a manifest field.
- **Sum-type lift `ManifestScope → PluginScope`** — handled by S2-04. Here scope is still raw `str | list[str]`. S2-04 produces a `ResolvedManifest` (separate model) whose `scope: PluginScope` is the post-lift form the arch §C2 line 755 pseudocode refers to.
- **`extends`-chain walking / cycle detection** — handled by S2-04. Here `extends` is just a `tuple[PluginId, ...]`.
- **PEP-440 semantic version validation** — Phase 11 (Sigstore + version comparison). Phase 3 treats `version` as opaque non-empty string.
- **Plugin signature / Sigstore verification** — Phase 11. The manifest has no `signature` field (per ADR-0011 the integrity check is sibling-file `plugins/PLUGINS.lock`).
- **TCCM loader (`tccm.yaml` parsing)** — Step 3.
- **`contributes.adapters` value-format validation (`module:Class`)** — S2-04's resolver concern (per ADR-0002 §"Keep [the registry] dumb; validate on use"). Loader rejects empty-string values via Pydantic but does not parse the `module:Class` shape.

## Notes for the implementer

### §1 — Chokepoint discipline

Use `from codegenie.parsers.safe_yaml import load as safe_yaml_load`. Do **not** import `yaml` directly; the AST-walk fence test (AC-18) catches it. Phase 1 ADR-0009 documents *why* the chokepoint exists (alias-amplification / billion-laughs / symlink TOCTOU). Inheriting `safe_yaml`'s defenses is the load-bearing design move; the original draft's hand-rolled `yaml.safe_load(path.read_bytes())` re-opened the attack class.

### §2 — Translation table is the contract

The four-arm translation in `from_yaml` is the entire user-visible behaviour. Pin it in code AND in a `_classify`-equivalent docstring (mirror `tccm/loader.py:9-23` for prose style). A Pydantic minor upgrade that re-formats `ValidationError.__str__` must not break the AC — we read `.errors()[*].loc` (stable Pydantic v2 API), never `str(e)`. Add a `# Pydantic v2 ErrorDetails['loc'] is stable across minor versions; if Pydantic 3 lands, update this translation, do not relax the test (Rule 12 — fail loud).` comment above the rendering.

### §3 — Tagged union over anaemic Pydantic — why

ADR-0010 §Decision 3 names this pattern verbatim. The four error modes carry different evidence (`SizeCapExceeded` carries `actual_bytes`+`cap`; `MalformedYaml` carries free-form message; `SchemaViolation` carries `field_errors`; `IoError` carries `errno`). A single `Pydantic(reason: Literal, detail: str)` would force every variant through a stringly-typed `detail` — exactly the failure mode ADR-0010 §Pattern fit row 1 rejects. Consumer-side `match err:` becomes exhaustive under `mypy --strict` (`assert_never(err)` after the four arms is a type error if a variant is added without updating consumers — the kernel-protection mechanism ADR-0010 §Reversibility names).

### §4 — Smart-constructor lift via free function, NOT classmethod

`PluginId` is `NewType("PluginId", str)`; `NewType` cannot host classmethods (S1-01 Notes §"Arch ↔ NewType API drift"). The lift is `from codegenie.types.parsers import parse_plugin_id` → returns `Result[PluginId, ParseError]`. Inside the `@field_validator("name", mode="after")` body, call `parse_plugin_id(value)`; on `Err`, `raise ValueError(parse_error_message)` so Pydantic wraps it into the outer `ValidationError` that the `from_yaml` translation arm catches. Do NOT `cast(PluginId, value)` — that defeats the discipline ADR-0010 §Decision 2 puts in place.

### §5 — Open/Closed extension seam for future manifest fields

`extra="forbid"` is the intended discipline (ADR-0010 §Tradeoffs row 5). Adding a Phase 7 field — e.g., `contributes.containers: ContainerContributes` for Chainguard distroless plugins — is an explicit, ADR-worthy edit to **this file**; not a smell. The file is the canonical source of truth for the manifest schema, mirroring `production/adrs/0031-plugin-architecture.md`. The Open/Closed seam in Phase 3 is the body-shape of each existing `contributes.{tccm,subgraph,skills,recipes,probes,adapters}` field (each sub-model can grow internally); cross-field additions are deliberately ADR-gated. A reviewer encountering `extra="forbid"` blocking a desired manifest extension should write an ADR amending production ADR-0031, not flip to `extra="allow"` (silent drift) or add a `dict[str, JSONValue]` escape hatch (defeats the type-checker).

### §6 — Why no separate `PluginManifestLoader` class

TCCM ships `class TCCMLoader` separately because its `_classify(ValidationError) → reason` translation is non-trivial (7-way table). S2-02's translation is 4-way and shallow; co-locating `from_yaml` as a classmethod on `PluginManifest` keeps the imports tighter and saves a file. The functional-core fence on `manifest.py` is downgraded to: imports from `codegenie.*` only — `result`, `types.identifiers`, `types.parsers`, `parsers.safe_yaml`. No probes, no orchestrator, no event log. The AST-walk fence (AC-18) AND a sibling import-allowlist test enforce this.

### §7 — Pydantic v2 `NewType` keys in `dict`

`ManifestContributes.adapters: dict[PrimitiveName, str]` works because `NewType` is runtime-identity to `str`; Pydantic v2 accepts the raw `str` keys from YAML and the type-checker sees `PrimitiveName` at every read site. If `model_validate` rejects `NewType`-key dicts in the version pinned by `pyproject.toml`, the executor adds a `@field_validator("adapters", mode="before")` that wraps each key in `PrimitiveName(k)` — but the AC test should reveal-type the dict at a callsite to confirm the keys are `PrimitiveName`-typed under `mypy --strict`.

### §8 — Precedent citations

The 1 MiB cap (`1 << 20`) follows the codebase convention: Phase 2 `S2-02-conventions-catalog-loader.md` (1 MiB on catalog YAML), Phase 2 `S1-04-tccm-model-loader.md` (1 MiB on TCCM YAML), Phase 3 `S3-03-vuln-index-ingest-cli.md` (1 MiB on CVE payloads). Cite Phase 2 `S2-02-conventions-catalog-loader.md` as the closest analogue (catalog YAML loader; same shape as this loader). Add a `# 1 MiB cap matches Phase 2 conventions-catalog-loader precedent; cf. ADR-0010 §Smart constructor.` comment above the constant.

### §9 — Functional core / imperative shell

The only impure function in `manifest.py` is `PluginManifest.from_yaml` (file I/O via `safe_yaml.load`). Field validators, helper rendering, and submodel validation are pure. The story deliberately co-locates them in one file because (a) splitting `_models.py` / `_io.py` at this size is YAGNI per Rule 2 (three similar lines is better than premature abstraction), and (b) `manifest.py` is the canonical single-source-of-truth for the manifest schema — a reviewer should not have to chase across files to confirm what `plugin.yaml` looks like.

### §10 — Rule 9 — Tests verify intent, not just behaviour

Every assertion in the test suite should encode *why* the behaviour matters, not *what* it does. Examples:
- `test_unknown_field_returns_err_schema_violation` — *why*: `extra="forbid"` is the schema-drift defence; without it, a typo silently degrades to default and Phase 7's distroless plugin author thinks their new `contributes.containers` field is loaded.
- `test_oversized_file_returns_err_size_cap_exceeded` — *why*: a 2 GiB hostile manifest must not OOM the loader.
- `test_malformed_yaml_returns_err_malformed_yaml[null_document]` — *why*: an editor that auto-saves `null` over a manifest must surface as a typed error, not a confusing schema_violation.
- `test_io_error_routes_to_err_io_error[is_a_directory]` — *why*: passing a directory path is a CLI argument bug; the user needs to see `IoError(EISDIR)`, not a swallowed `IsADirectoryError`.

Every test docstring should answer "what regression does this catch?"
