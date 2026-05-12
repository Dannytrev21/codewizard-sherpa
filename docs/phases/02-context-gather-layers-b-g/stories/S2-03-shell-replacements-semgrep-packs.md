# Story S2-03 — `shell_replacements/node.yaml` + `semgrep_rule_packs.yaml` catalogs

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** M
**Depends on:** S1-08 (`tools/digests.yaml` pin manifest — Semgrep rule-pack-version digests cross-referenced); S2-02 (sets the closed-enum + `additionalProperties: false` precedent + `CatalogLoadError`)
**ADRs honored:** ADR-0008 (closed-enum + CI parity lint discipline generalized to a second catalog), ADR-0004 (`tools/digests.yaml` pin manifest), Phase 1 ADR-0006 (catalog-versioning pattern)

## Context

Two more catalogs land in Phase 2, both following the ADR-0008 closed-enum discipline:

1. **`shell_replacements/node.yaml`** — consumed by `ShellUsageProbe` (C5) in Step 5. Each entry maps a shell-builtin invocation pattern (e.g., `cat`, `sed`, `awk`) to a Node-native replacement (e.g., `fs.readFile`, `String.prototype.replace`) so the Planner can later produce structural rewrites. The `detect.type` style of dispatch generalizes: the catalog declares the kind of replacement (`exec_call_replacement`, `pipeline_replacement`, etc.) and the probe dispatches via `match/case` — the S2-04 parity lint enforces both directions.
2. **`semgrep_rule_packs.yaml`** — declares which Semgrep rule packs apply per `task_type`. Consumed by `SemgrepProbe` (G1) in Step 7. Each pack has a `rule_pack_version` digest that **must** appear in `tools/digests.yaml` (ADR-0004) — unpinned ⇒ hard-fail at startup.

Both catalogs plant `schema_version: "v1"` per the S2-07 policy and hard-fail on schema mismatch per the S2-02 precedent.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #4` — establishes the closed-enum + lint pattern this story extends.
- **Architecture:** `../phase-arch-design.md §"Component design" #11` (`ShellUsageProbe`) — consumer of `shell_replacements/node.yaml`.
- **Architecture:** `../phase-arch-design.md §"Component design" #13` (`SemgrepProbe`) — consumer of `semgrep_rule_packs.yaml`; `rule_pack_version` cross-check against `tools/digests.yaml`.
- **Phase ADRs:**
  - `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — the discipline this story extends.
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — Semgrep rule-pack-version digests live here; unpinned ⇒ degraded or hard-fail.
- **Production ADRs:** `../../../production/design.md §2` — "organizational uniqueness as data, not prompts".
- **Source design:** `../final-design.md "Components" §5.3` (conventions parent), `§5.5` (Semgrep rule packs).
- **Existing code:** `src/codegenie/catalogs/` planted by S2-02 — re-use `_load_catalog(...)`, `CatalogLoadError`, `MappingProxyType` wrap.

## Goal

Land `src/codegenie/catalogs/shell_replacements/{_schema.json, node.yaml}` and `src/codegenie/catalogs/semgrep_rule_packs.yaml` + `_schema.json` such that both load cleanly via the S2-02 loader, both declare `schema_version: "v1"`, both enforce `additionalProperties: false` at every level, and the Semgrep catalog's `rule_pack_version` entries are cross-referenced against `tools/digests.yaml` with hard-fail on missing pins.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/shell_replacements/_schema.json` declares `schema_version: { enum: ["v1"] }`, `catalog_version: { type: "integer" }`, `additionalProperties: false` at every level, and a **closed enum** on the replacement entry's `type` field — initial values: `["exec_call_replacement", "pipeline_replacement", "file_io_replacement"]` (three seed values; extensible by addition under ADR-0008).
- [ ] `src/codegenie/catalogs/shell_replacements/node.yaml` declares `schema_version: "v1"`, `catalog_version: 1`, and seeds at least one entry per enum value (3+ entries total). Each entry has `shell_idiom: str`, `replacement: str`, and a 1–2 sentence `rationale`.
- [ ] `src/codegenie/catalogs/semgrep_rule_packs.yaml` declares `schema_version: "v1"`, `catalog_version: 1`, and lists rule packs. Each pack has `name: str`, `rule_pack_version: str`, `task_types: list[str]`. `task_types` items constrained by a closed enum: `["vulnerability_remediation", "distroless_migration", "*"]` (the Phase 2 + Phase 7 + wildcard set).
- [ ] `src/codegenie/catalogs/semgrep_rule_packs.yaml` seeds at least one pack relevant to vulnerability remediation (e.g., `name: "p/owasp-top-ten"`).
- [ ] At load time, every `rule_pack_version` is cross-referenced against `tools/digests.yaml` (under a `semgrep_rule_packs:` section). Missing pin → `CatalogLoadError` with the exact pack name; CLI exits 2.
- [ ] Both catalogs loaded via `_load_catalog(...)` from S2-02 — `MappingProxyType`-wrapped, hard-fail on YAML/schema violation.
- [ ] TDD red landed first: `tests/unit/catalogs/test_shell_replacements_schema.py` and `tests/unit/catalogs/test_semgrep_rule_packs.py` initially fail.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on touched modules.

## Implementation outline

1. Create `src/codegenie/catalogs/shell_replacements/_schema.json` — Draft 2020-12; closed enum on the replacement entry's `type` field with the three seed values; `additionalProperties: false` everywhere; `pattern` constraint on entry `id` mirroring the conventions pattern.
2. Create `src/codegenie/catalogs/shell_replacements/node.yaml` with seed entries covering each enum value. Add the `# Schema-evolution policy: …` cross-link comment.
3. Create `src/codegenie/catalogs/semgrep_rule_packs.yaml` and `src/codegenie/catalogs/semgrep_rule_packs.schema.json` (or `_schema.json` if you co-locate — match the conventions catalog pattern). Closed enum on `task_types[]` items. Add the cross-link comment.
4. Extend `src/codegenie/catalogs/loader.py`:
   - `def load_shell_replacements_catalog(language: str) -> Mapping[str, Any]`.
   - `def load_semgrep_rule_packs() -> Mapping[str, Any]`. In this loader, after schema validation, iterate `rule_packs[*].rule_pack_version` and cross-reference against `tools/digests.yaml`; missing pin → `CatalogLoadError("semgrep rule pack X has no digest pinned in tools/digests.yaml")`.
5. Update `tools/digests.yaml` (planted by S1-08) to include a `semgrep_rule_packs:` section with placeholder digest entries for every seeded pack — the Step-2 PR ships both halves so CI is green.
6. Export the two new loaders from `src/codegenie/catalogs/__init__.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:

- `tests/unit/catalogs/test_shell_replacements_schema.py`
- `tests/unit/catalogs/test_semgrep_rule_packs.py`

```python
# tests/unit/catalogs/test_shell_replacements_schema.py
import pytest

def test_node_shell_replacements_loads() -> None:
    catalog = load_shell_replacements_catalog("node")
    assert catalog["schema_version"] == "v1"
    allowed = {"exec_call_replacement", "pipeline_replacement", "file_io_replacement"}
    for entry in catalog["replacements"]:
        assert entry["type"] in allowed

def test_unknown_replacement_type_rejected(tmp_path) -> None:
    with pytest.raises(CatalogLoadError):
        ...

def test_extra_field_under_replacement_rejected(tmp_path) -> None:
    with pytest.raises(CatalogLoadError):
        ...

# tests/unit/catalogs/test_semgrep_rule_packs.py
def test_semgrep_rule_packs_loads() -> None:
    packs = load_semgrep_rule_packs()
    assert packs["schema_version"] == "v1"
    allowed_task_types = {"vulnerability_remediation", "distroless_migration", "*"}
    for pack in packs["rule_packs"]:
        for t in pack["task_types"]:
            assert t in allowed_task_types

def test_unpinned_rule_pack_version_rejected(tmp_path, monkeypatch) -> None:
    # arrange: a synthetic semgrep_rule_packs.yaml referencing a rule_pack_version
    #          that is NOT in tools/digests.yaml
    # act + assert: CatalogLoadError with the pack name in the message
    with pytest.raises(CatalogLoadError, match="no digest pinned"):
        ...

def test_unknown_task_type_rejected(tmp_path) -> None:
    with pytest.raises(CatalogLoadError):
        ...
```

Run; confirm red; commit; then Green.

### Green — make it pass

Smallest impl: ship the two `_schema.json` files + the two YAML seeds + the two loaders. Cross-reference logic for Semgrep is a simple dict lookup against the parsed `tools/digests.yaml`.

### Refactor — clean up

- Factor the `tools/digests.yaml` reader as a singleton in `src/codegenie/tools/digests.py` (assume S1-08 planted it; if not, plant a minimal one) so both this catalog loader and the Skills loader (S2-01) share one parser.
- Add a `# Schema-evolution policy: …` cross-link comment at the root of each new YAML/JSON file.
- Docstrings on the two loaders naming the closed-enum invariant and the cross-reference contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/shell_replacements/_schema.json` | Closed-enum `type` field; `additionalProperties: false`. |
| `src/codegenie/catalogs/shell_replacements/node.yaml` | Seed with 3+ entries (one per enum value). |
| `src/codegenie/catalogs/semgrep_rule_packs.yaml` | Closed-enum `task_types`; cross-reference to `tools/digests.yaml`. |
| `src/codegenie/catalogs/semgrep_rule_packs.schema.json` | Draft 2020-12; `additionalProperties: false`; `schema_version` literal. |
| `src/codegenie/catalogs/loader.py` | Two new functions: `load_shell_replacements_catalog`, `load_semgrep_rule_packs`. |
| `src/codegenie/catalogs/__init__.py` | Export the two new loaders. |
| `tools/digests.yaml` | Add `semgrep_rule_packs:` section with placeholder digests for seeded packs. |
| `tests/unit/catalogs/test_shell_replacements_schema.py` | Happy path + unknown type + extra field. |
| `tests/unit/catalogs/test_semgrep_rule_packs.py` | Happy path + unpinned rule pack + unknown task_type. |
| `tests/unit/catalogs/fixtures/*.yaml` | Adversarial fixtures. |

## Out of scope

- **`ShellUsageProbe` (C5)** — handled by Step 5. This story plants the catalog only; the probe's `_apply_detector` `match/case` and S2-04's parity lint integration extend to it then.
- **`SemgrepProbe` (G1)** — handled by Step 7. This story plants the rule-pack list only.
- **Real digests for the seeded packs** — placeholder digests in `tools/digests.yaml` are fine for Phase 2; Phase 3 + 7 will pin real ones when the probes run.
- **Parity lint for `shell_replacements`** — S2-04 extends its lint to cover this catalog when `ShellUsageProbe` lands in Step 5; this story keeps the schema closed.
- **`SCHEMA-EVOLUTION-POLICY.md`** — handled by S2-07.
- **`python.yaml`, `java.yaml` shell replacements** — Phase 11+ language additions.

## Notes for the implementer

- **Two closed enums in one PR — keep them independent.** The `shell_replacements` `type` enum and the `semgrep_rule_packs` `task_types` enum are *separate*; future additions to one must not implicitly require the other. Document each enum's grow-path in its `_schema.json` root `$comment`.
- **`task_types: ["*"]` is a wildcard.** Allow it as an enum member; consumer probes interpret `"*"` as "applies to every task type". Don't validate against a list that excludes it.
- **`rule_pack_version` is a string, not a semver tuple.** Semgrep packs use versioned hashes; keep the type loose at the schema (`string`) but pin the contents in `tools/digests.yaml`.
- **Placeholder digests in `tools/digests.yaml`.** Use a clearly synthetic format like `sha256:placeholder-phase2-step2-<pack-name>` so a grep for `placeholder` surfaces them when Phase 3 swaps in real values. Don't use empty strings — those round-trip through YAML as `None`.
- **Cross-reference must happen at load time, not at probe runtime.** Catching an unpinned rule-pack at runtime means a partial gather already ran; catching at startup follows Rule 12 (fail loud).
- **Don't merge the two catalogs into one file.** They're consumed by different probes (`ShellUsageProbe` vs `SemgrepProbe`) and grow on different cadences (shell-replacements grows with Phase 7 distroless work; rule-packs grow with each new task class). Two files, one loader pattern.
