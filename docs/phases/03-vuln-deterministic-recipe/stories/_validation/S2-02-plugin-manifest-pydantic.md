# Validation report — S2-02 — `PluginManifest` Pydantic model + YAML loader

**Validated:** 2026-05-18
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S2-02-plugin-manifest-pydantic.md`

---

## Context brief

S2-02 ships the **typed loader** for `plugin.yaml` files: a frozen Pydantic `PluginManifest` (with `extra="forbid"`) covering every production-ADR-0031-documented manifest field, plus `PluginManifest.from_yaml(path) -> Result[PluginManifest, ManifestError]` that loads YAML, validates, lifts `name`/`extends` strings to `PluginId`, and returns a discriminated `Ok`/`Err` rather than raising. The filesystem walk that *finds* manifests is S2-03; the resolver consuming `scope`/`precedence`/`extends` is S2-04.

This story is the **second loader** to land the Phase-3 plugin contract (after S2-01's kernel `PluginRegistry`). It is also the *first* place the tagged-union error-discipline lands in Phase 3 (Phase 2 `S2-02-conventions-catalog-loader.md` is the sibling precedent on the loader-with-typed-errors family).

**Load-bearing context:**
- production ADR-0031 §Plugin manifest (lines 75-109) — the canonical YAML contract; `precedence` default is `50`.
- ADR-0002 §Decision: "Keep [the registry] dumb; validate on use." Manifest validation belongs to the loader (this story), not to the registry (S2-01).
- ADR-0004: `contributes.tccm` is a *path-reference* to the plugin's TCCM; capability namespaces live in TCCM, not on the kernel Plugin Protocol.
- ADR-0010 §Decision 3: tagged-union sum types on every state machine; the four error modes ARE a state machine.
- ADR-0011 §Decision: `PLUGINS.lock` is a *sibling-file* integrity check (S2-03), NOT a per-manifest `signature` field. No manifest `signature`.
- Phase 1 ADR-0009: `codegenie.parsers.safe_yaml.load(path, max_bytes=...)` is the YAML chokepoint; every loader routes through it.
- Sibling precedents: `src/codegenie/tccm/loader.py` (closest analogue — `from_yaml`-shaped loader returning `Result[T, TCCMLoadError]` via `safe_yaml.load`); Phase 2 `S2-02-conventions-catalog-loader.md` (loader-with-typed-tagged-union-errors family).

**Original story strengths:**
- Correctly cited ADR-0002 / ADR-0004 / ADR-0010 / ADR-0011 across Context, References, Notes, ACs.
- Correctly out-of-scoped the resolver work (S2-04) and the filesystem walk (S2-03).
- Got the `Result` over raising discipline right (matches `codegenie.result` + S1-04 TCCMLoader pattern).
- Got the `frozen=True, extra="forbid"` Pydantic discipline right.
- Identified the four-error-mode structure even if not as a tagged union.
- Out-of-scope section accurately separated S2-02 from S2-03/S2-04.
- Correctly anchored the 1 MiB cap to a codebase convention (even if the citation was slightly wrong).

**Original story weaknesses (resolved here):**
- Loader bypassed the `codegenie.parsers.safe_yaml.load` chokepoint — re-implemented hand-rolled `path.open("rb")` + `yaml.safe_load(raw)` + `stat().st_size > 1<<20`. Re-opened the alias-amplification + symlink + non-mapping-top-level vulnerabilities Phase 1 ADR-0009 closed. (Design-Patterns F1 / Test-Quality F8 — `block`.)
- `ManifestError` modelled as anaemic `Pydantic(reason: Literal[4], detail: str, path: Path | None)` — violates ADR-0010 §Decision 3 mandate of tagged-union sum types on every state machine. Each variant carries different evidence; stringly-typed `detail` is the failure mode the ADR rejects. (Design-Patterns F2 / Test-Quality F9 — `block`.)
- Manifest had a `signature: str | None = None` field — but production ADR-0031 has no `signature` field, and ADR-0011 explicitly puts the integrity check in the *sibling file* `plugins/PLUGINS.lock`. The field was invented by the story. (Consistency F3 — `block`.)
- `scope` shape contradicted phase-arch §Data model line 755 (`scope: PluginScope`). Story was right to defer the sum-type lift to S2-04 (production ADR-0031 §YAML example shows raw `str | list[str]`), but the contradiction was undocumented. (Consistency F1 — `block`.)
- `precedence: int = 50` was right per production ADR-0031 §Plugin manifest comment but contradicted phase-arch line 756 (`precedence: int = 0`). Three-way conflict undocumented. (Consistency F2 — `block`.)
- Notes line 143 "lift via the S1-01 smart constructor" was misleading — `PluginId` is `NewType`, smart constructors are free functions `codegenie.types.parsers.parse_plugin_id(s) -> Result[PluginId, ParseError]`, not classmethods. (Consistency F6 — `harden`.)
- AC line 41 had `adapters: dict[str, str]` — should be `dict[PrimitiveName, str]` per ADR-0010 newtype discipline. Same for `probes: list[str]` → `tuple[ProbeId, ...]`. (Consistency F11 / Design-Patterns F4 — `harden`.)
- `ManifestRequirements` was referenced by name with `= ManifestRequirements()` default but its field shape was never enumerated. Production ADR-0031 lines 102-106 documents `external_tools: list` + `optional: list`. (Consistency F5 — `harden`.)
- AC line 46 "TDD red test (`test_unknown_field_returns_err`) committed and green" — single red test for four distinct error modes; misses mutation-resistance for io_error, malformed_yaml, size_cap_exceeded. (Coverage F12 / Test-Quality F2 / Consistency F10 — `harden`.)
- No AC for the `io_error` reason — Implementation outline mentioned it but no AC enforced. A mutant that routes `OSError` through `size_cap_exceeded` survives. (Coverage F1 — `block`.)
- No ACs for non-mapping top-level YAML (empty file, scalar, list, null). The most common malformed YAML in the wild. (Coverage F2 — `block`.)
- No AC asserting `name: PluginId` lift on load — Notes mentioned it but no test enforced; mutant `cast(PluginId, raw_name)` survives. (Coverage F3 / Test-Quality F6 — `block` / `harden`.)
- "PEP-440-ish, validate non-empty" was vague — no concrete acceptance criterion for what passes/fails. (Coverage F5 / Design-Patterns F7 — `harden` / `nit`.)
- No AC pinned the documented defaults from a minimal YAML load. A mutant `precedence: int = 0` survives every named test. (Coverage F6 / Test-Quality F4 — `harden`.)
- Size-cap AC didn't say "short-circuit before reading bytes". Naive `read-then-check` impl survives. (Coverage F7 / Test-Quality F7 — `harden`.)
- Round-trip used `model_dump_json()` → JSON-via-YAML. Doesn't exercise real block-style YAML; mutants in the YAML path survive. (Coverage F8 / Test-Quality F3 — `harden`.)
- `extra="forbid"` red test only at top level — submodel `extra="allow"` mutants survive. (Coverage F9 / Test-Quality F5 — `harden`.)
- Hypothesis property test marked "low priority" — should be required given the never-raises invariant and the wide field-addition mutant class it catches. (Test-Quality F12 — `nit`-elevated.)
- "Phase 2 S3-03" precedent citation pointed at a story that doesn't exist (the actual Phase 2 precedents are S2-02 conventions-catalog-loader and S1-04 TCCM loader). (Consistency F8 — `harden`.)
- `_read_capped_bytes` Refactor §1 reinvents `parsers._io.open_capped` which is already used by `safe_yaml.load`. Drop entirely. (Design-Patterns F9 — `nit`.)
- Open/Closed extension path (Phase 7 distroless adding `contributes.containers`) not documented; reviewer hitting `extra="forbid"` will misread it as a smell. (Design-Patterns F6 — `harden`.)
- Classmethod-on-schema vs separate loader class divergence from `TCCMLoader` not justified. (Design-Patterns F3 — `harden`.)
- `OSError` catch breadth (FileNotFoundError, PermissionError, IsADirectoryError, ELOOP) not enumerated. (Consistency F12 — `nit`.)

---

## Stage 2 — Four critic reports

### Coverage critic — 12 findings

| ID | Severity | Title | Resolution |
| --- | -------- | ----- | ---------- |
| F1 | block | `reason="io_error"` declared but no AC verifies it | Applied — new AC-9 + AC-17 parametrized `test_io_error_routes_to_err_io_error` covers missing_path / is_a_directory / permission_denied / broken_symlink (latter two skipped on Windows). |
| F2 | block | Non-mapping top-level YAML unhandled in ACs | Applied — `safe_yaml.load` chokepoint refuses non-mapping at the parser level; new AC-17 parametrized `test_malformed_yaml_returns_err_malformed_yaml` covers empty_file / invalid_syntax / top_level_list / top_level_scalar / null_document. |
| F3 | block | `name: PluginId` smart-constructor lift has no AC | Applied — AC-10 mandates `parse_plugin_id` lift via `@field_validator("name", mode="after")`; invalid `name: ""` returns `Err(SchemaViolation(field_errors=("name",)))`. |
| F4 | harden | `extends: list[PluginId]` element validation unspecified | Applied — AC-11 mandates per-element `parse_plugin_id` lift; first-failure → `Err(SchemaViolation(field_errors=("extends",)))`. |
| F5 | harden | "PEP-440-ish, non-empty" for `version` is vague | Applied — Design-Patterns F7 chosen: drop "PEP-440-ish", `version: Annotated[str, StringConstraints(min_length=1)]` non-empty only. PEP-440 deferred to Phase 11. |
| F6 | harden | Defaults not pinned by ACs | Applied — AC-13 mandates literal-equality assertions on every documented default from a minimal YAML load; defaults-pin test added to Refactor. |
| F7 | harden | Size-cap path doesn't assert "stat-before-read" | Applied — `safe_yaml.load` enforces via `os.fstat(fd).st_size` *before* any bytes are read (Phase 1 ADR-0009 mechanism); routing through it satisfies the AC by construction; test docstring documents the chokepoint reliance. |
| F8 | harden | Round-trip uses `model_dump_json`, not YAML | Applied — AC-15 mandates `yaml.safe_dump(m.model_dump(mode="json"))`; AC-16 Hypothesis property test required; hand-authored block-style fixture in TDD §6. |
| F9 | harden | `extra="forbid"` enforced only at top level, not at submodels | Applied — AC-14 + TDD §2 parametrized `test_unknown_field_rejected_in_each_submodel` covers contributes / requirements / scope. |
| F10 | nit | `contributes.adapters` value-format unverified | Applied as Out-of-scope clarification — `module:Class` validation is S2-04's resolver concern (loader stays dumb per ADR-0002); Pydantic rejects empty strings via type. |
| F11 | nit | `ManifestError.reason` exhaustiveness unverified | Applied — replaced anaemic `reason: Literal` with tagged union (Design-Patterns F2); AC-7 mandates `match` + `assert_never` callsite test that gates exhaustiveness at `mypy --strict`. |
| F12 | nit | Single red test insufficient for AC-family coverage | Applied — AC-17 mandates five distinct red tests (one per error mode + happy round-trip). |

### Test-Quality critic — 12 findings

| ID | Severity | Title | Resolution |
| --- | -------- | ----- | ---------- |
| F1 | block | `from_yaml` "never raises" invariant has zero tests | Applied — AC-12 mandates Hypothesis property test (`@given(st.binary())`) writing arbitrary bytes and asserting `isinstance(result, (Ok, Err))` — never escapes. |
| F2 | block | `reason` discriminator tested in only one branch; cross-input → cross-reason matrix missing | Applied — AC-17 + TDD §3/§4/§5 parametrized tests bind each input class to its exact `ManifestError` variant; mutant `"schema_violation"` catch-all survives none of them. |
| F3 | block | Round-trip uses `model_dump_json()`, not real YAML | Applied — AC-15: `yaml.safe_dump(m.model_dump(mode="json"))`; happy-path fixture is hand-authored block-style YAML. |
| F4 | harden | No default-values test; `precedence = 50` hardcoded-default mutant survives | Applied — AC-13 + `test_minimal_yaml_pins_documented_defaults` in Refactor section. |
| F5 | harden | `extra="forbid"` tested at top level only; submodel mutants survive | Applied — TDD §2 parametrized over submodels. |
| F6 | harden | `name: PluginId` smart-constructor lift untested; `cast()` mutant survives | Applied — AC-10 + Implementation outline §2 wires `parse_plugin_id` via `@field_validator("name", mode="after")`; explicit "no `cast()`" Notes §4 paragraph. |
| F7 | harden | Size-cap test can't disambiguate "stat-then-skip" vs "read-then-cap" | Applied — `safe_yaml.load` is the chokepoint; the chokepoint enforces stat-before-read via `os.fstat(fd).st_size` *before reading any bytes*; test docstring documents this reliance + AC-9 size-cap re-stat for `actual_bytes`. |
| F8 | block (cross-cut Consistency) | Bypasses sibling `codegenie.parsers.safe_yaml` chokepoint | Applied — entire `from_yaml` reroute through `safe_yaml.load(path, max_bytes=1 << 20)`; AC-18 AST-walk fence prevents `import yaml` regression. |
| F9 | harden | `reason: Literal[...]` vs tagged-union — mutation-resistance gap | Applied — replaced with tagged-union `ManifestError = SizeCapExceeded | MalformedYaml | SchemaViolation | IoError`; AC-7 exhaustive-`match` callsite test. |
| F10 | nit | No metamorphic single-field-flip test; `__eq__` / `frozen=True` mutants survive | Applied — `test_field_change_breaks_equality` + `test_frozen_rejects_mutation` in Refactor. |
| F11 | nit | `signature` field never set to non-None in any test | **Field dropped entirely** per Consistency F3 (not in canon). Test no longer needed. |
| F12 | nit | Missing test scaffolding; conftest sharing with S2-01 | Applied — Preconditions block in Files-to-touch enumerates S2-01-provided infrastructure; Hypothesis property test (AC-16) promoted from refactor to required. |

### Consistency critic — 12 findings

| ID | Severity | Title | Resolution |
| --- | -------- | ----- | ---------- |
| F1 | block | Arch's `PluginManifest.scope: PluginScope` contradicts story's `scope: ManifestScope` | Applied — Notes-for-implementer + Validation-notes header + References annotation document the divergence. S2-04 produces a `ResolvedManifest` whose `scope: PluginScope` is the lifted form. **Arch follow-up logged below.** |
| F2 | block | `precedence` default — three-way divergence | Applied — production ADR-0031 §Plugin manifest comment "default 50" wins (canonical YAML contract). Story matches. **Arch follow-up logged below** (line 756 wrong by 50). |
| F3 | block | `signature: str \| None` field not in any canonical source | Applied — **field dropped entirely**. Per ADR-0011 the integrity check is `plugins/PLUGINS.lock` (sibling file, S2-03). Phase 11 Sigstore substitutes the *loader's* verification adapter, not a manifest field. |
| F4 | harden | Arch lists no `contributes`/`requirements`/`signature` on `PluginManifest` | Applied — story implements the full production ADR-0031 surface (`name, version, scope, extends, precedence, contributes, requirements`); arch §Data model is under-specified relative to production-ADR. **Arch follow-up logged below.** |
| F5 | harden | `ManifestRequirements` shape unspecified | Applied — AC-5 pins `external_tools: tuple[str, ...] = ()` + `optional: tuple[str, ...] = ()` per production ADR-0031 lines 102-106. |
| F6 | harden | "Lift via the S1-01 smart constructor" misleading | Applied — Notes §4 names `codegenie.types.parsers.parse_plugin_id` free function explicitly; flags that `NewType` cannot host classmethods. |
| F7 | harden | Files-to-touch depends on S2-01 preconditions | Applied — explicit Preconditions block in Files-to-touch enumerates the four S2-01-provided files + the two S1-01-provided modules + the Phase-1 chokepoint. |
| F8 | harden | "Phase 2 S3-03 uses same 1 MiB cap" — citation wrong | Applied — Notes §8 rewrites the citation: Phase 2 `S2-02-conventions-catalog-loader.md` + `S1-04-tccm-model-loader.md` + Phase 3 `S3-03-vuln-index-ingest-cli.md`. Phase 2 S2-02 is the closest analogue. |
| F9 | nit | `ManifestError.reason: Literal[...]` is anaemic | Applied — replaced with tagged union per ADR-0010 §Decision 3 (cross-resolved with Design-Patterns F2). |
| F10 | nit | Single red TDD test thin for 4 error modes | Applied — AC-17 + TDD §1-6: five red tests upfront. |
| F11 | nit | `contributes.adapters: dict[str, str]` should be `dict[PrimitiveName, str]` | Applied — AC-4 uses `PrimitiveName`; `probes: tuple[ProbeId, ...]` also lifted. |
| F12 | nit | `OSError` breadth & `yaml.safe_load(bytes)` | Applied — AC-9 enumerates `FileNotFoundError`/`PermissionError`/`IsADirectoryError`/`ELOOP`; `safe_yaml.load` handles bytes-vs-str internally (the loader doesn't see raw bytes). |

### Design-Patterns critic — 9 findings

| ID | Severity | Title | Resolution |
| --- | -------- | ----- | ---------- |
| F1 | block | Story bypasses `safe_yaml.load` chokepoint | Applied — entire `from_yaml` rewrite routes through `safe_yaml.load(path, max_bytes=1 << 20)`; AC-18 AST-walk fence; Notes §1 documents the chokepoint discipline. |
| F2 | block | `ManifestError` anaemic Pydantic — ADR-0010 mandates tagged union | Applied — replaced with four-variant discriminated union (`SizeCapExceeded`, `MalformedYaml`, `SchemaViolation`, `IoError`), each carrying its evidence. AC-7 exhaustive-match callsite gates `mypy --strict` exhaustiveness. |
| F3 | harden | `@classmethod from_yaml` diverges from `TCCMLoader` separate-class | Applied as Notes §6 justification: TCCMLoader's 7-way `_classify` warranted a separate class; S2-02's 4-way table doesn't. Classmethod-on-schema chosen; functional-core fence downgraded to import-allowlist. |
| F4 | harden | `adapters: dict[str, str]` is primitive obsession | Applied — AC-4 uses `dict[PrimitiveName, str]`; `probes: tuple[ProbeId, ...]`. Pydantic v2 accepts NewType keys via identity. |
| F5 | harden | Pydantic-v2 translation table unpinned | Applied — Notes §2 pins `ValidationError.errors()[*].loc` (stable v2 API) and forbids reading `str(e)`. Implementation outline §4 names the rendering. |
| F6 | harden | Open/Closed seam for future fields undocumented | Applied — Notes §5 paragraph: `extra="forbid"` is the intended discipline; Phase 7 distroless adding `contributes.containers` is an ADR-gated edit to this file, not a smell. |
| F7 | nit | `version: Annotated[str, AfterValidator(...)]` validator unpinned | Applied — drop "PEP-440-ish"; `Annotated[str, StringConstraints(min_length=1)]` non-empty only. PEP-440 deferred to Phase 11 (Out-of-scope). |
| F8 | nit | `name: PluginId` lift inside Pydantic with `extra="forbid"` unspecified | Applied — Notes §4 + AC-10 fully pin: `@field_validator("name", mode="after")` → `parse_plugin_id(value)` → `raise ValueError(...)` on Err so Pydantic wraps into `ValidationError`. No `cast()`. |
| F9 | nit | `_read_capped_bytes` helper reinvents `parsers._io.open_capped` | Applied — Refactor §1 line deleted; Refactor scope now only `_render_field_errors(ve) -> tuple[str, ...]` helper for Pydantic error rendering. |

---

## Stage 3 — Research (skipped)

No critic finding was tagged `NEEDS RESEARCH`. All findings resolved against in-repo precedents (`tccm/loader.py`, `parsers/safe_yaml.py`, Phase 2 `S2-02-conventions-catalog-loader.md`) and existing ADRs.

---

## Conflict resolution

Priority: Consistency > Coverage > Test-Quality > Design-Patterns.

| Conflict | Resolution |
| -------- | ---------- |
| Coverage F1 (add io_error AC) vs Design-Patterns F2 (tagged union) | Both apply — `IoError` becomes a discrete variant of the tagged union; AC-9 + AC-17 cover the test side. |
| Design-Patterns F1 (route through `safe_yaml.load`) vs Coverage F7 (stat-before-read AC) | F1 wins — `safe_yaml.load` enforces stat-before-read by construction. Test docstring documents the reliance; no separate AC needed. |
| Design-Patterns F3 (separate loader class) vs Simplicity (Rule 2) | YAGNI wins — TCCMLoader's separation was justified by a non-trivial `_classify`; S2-02's 4-way table is shallow. Classmethod-on-schema with Notes §6 justification. |
| Consistency F1 (arch says `scope: PluginScope`) vs Consistency F4 (arch under-specifies manifest) | Story implements production ADR-0031 surface (the canonical YAML contract); arch §Data model is wrong / under-specified and gets follow-up amendment logged below. |
| Consistency F2 (arch `precedence = 0`) vs Story (`= 50`) vs ADR-0031 (`= 50`) | production ADR-0031 wins (canonical YAML contract). Arch line 756 follow-up logged. |
| Consistency F3 (drop signature field) vs Design-Patterns honest-framing | Drop wins — production ADR-0031 has no `signature` field; ADR-0011 puts the integrity check in `plugins/PLUGINS.lock` (sibling file, S2-03). The "honest framing" is satisfied by the sibling-file mechanism, not by a per-manifest field. |
| Test-Quality F11 (test signature round-trip) | Moot — field dropped per Consistency F3. |

---

## Arch follow-up items (logged for separate cleanup ticket)

These are arch-design contradictions S2-02 surfaces but does NOT fix in-line (Rule 3 — surgical changes). They warrant a separate doc-only edit to `docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md`:

1. **`phase-arch-design.md` line 756: `precedence: int = 0` → `= 50`** (matches production ADR-0031 §Plugin manifest example comment "default 50").
2. **`phase-arch-design.md` line 755: `scope: PluginScope` → `scope: ManifestScope`** on the load-time `PluginManifest`. Document the post-lift `ResolvedManifest.scope: PluginScope` as a separate model produced by S2-04 resolution.
3. **`phase-arch-design.md` §Data model `PluginManifest` block (lines 750-757)**: enumerate `contributes: ManifestContributes`, `requirements: ManifestRequirements = ManifestRequirements()` per production ADR-0031 §Plugin manifest. The arch is under-specified relative to the production-ADR canon.

These are documentation-only edits to a sibling file; not in S2-02's blast radius. The story implementer can pick them up as a follow-up commit or leave for a dedicated arch-amendment ticket.

---

## Story before / after — selected snippets

### Before — single red test

```markdown
- [ ] TDD red test (`test_unknown_field_returns_err`) committed and green.
```

### After — five red tests, AC-17

```markdown
- [ ] AC-17 — Five distinct red tests committed before any green code, one per failure mode + one happy:
  - `test_unknown_field_returns_err_schema_violation`
  - `test_malformed_yaml_returns_err_malformed_yaml` (parametrized empty/invalid/list/scalar/null)
  - `test_oversized_file_returns_err_size_cap_exceeded`
  - `test_io_error_routes_to_err_io_error` (parametrized missing/dir/perm/symlink)
  - `test_happy_path_round_trip` (block-style YAML fixture)
```

### Before — anaemic `ManifestError`

```markdown
Define `ManifestError`: frozen Pydantic with
`reason: Literal["size_cap_exceeded","malformed_yaml","schema_violation","io_error"]`
+ `detail: str` + `path: Path | None`.
```

### After — tagged-union `ManifestError`

```markdown
- [ ] AC-6 — `ManifestError` is a Pydantic discriminated union over four variants,
  each carrying its evidence:
  - SizeCapExceeded(path, actual_bytes, cap)
  - MalformedYaml(path, message)
  - SchemaViolation(path, field_errors: tuple[str, ...])
  - IoError(path, errno, message)
- [ ] AC-7 — `match err:` over the union type-checks under mypy --strict with
  `assert_never(err)` after the four cases (exhaustiveness gate).
```

### Before — bypass the chokepoint

```python
with path.open("rb") as f: raw = f.read()
data = yaml.safe_load(raw)
```

### After — route through the chokepoint

```python
from codegenie.parsers.safe_yaml import load as safe_yaml_load
...
data = safe_yaml_load(path, max_bytes=1 << 20)
```

### Before — `signature: str | None` field

```markdown
`signature: str | None = None` (ADR-0011 stub)
```

### After — field dropped, ADR-0011 mechanism documented

```markdown
**No `signature` field.** Per ADR-0011 the per-plugin integrity check lives in
the sibling `plugins/PLUGINS.lock` file (S2-03), not in the manifest. Phase 11
Sigstore substitutes the loader's verification adapter, leaving the manifest
schema untouched.
```

---

## Verdict

**HARDENED.** The story had real but fixable weaknesses across all four critic lenses. Substantive edits applied in place; story status moved from `Ready` to `HARDENED`. Acceptance criteria now collectively guarantee the goal; every AC is individually verifiable; the TDD plan would catch a wrong implementation in each named failure mode; the prescribed implementation routes through the existing chokepoint instead of duplicating it; and the tagged-union `ManifestError` satisfies ADR-0010 §Decision 3 mandate. Three arch-design contradictions surfaced for follow-up (not in S2-02's scope to fix).

The story is ready for `phase-story-executor`.
