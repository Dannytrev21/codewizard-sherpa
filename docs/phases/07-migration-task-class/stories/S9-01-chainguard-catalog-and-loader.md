# Story S9-01 — Chainguard CVE-to-image recommendation catalog (frozen YAML) + Pydantic loader

**Step:** Step 9 — CVE-to-image catalog YAML + loader + file-hash fence
**Status:** Ready
**Effort:** M
**Depends on:** S1-01 (`ImageDigest` / `ImageRef` / `CveId` newtypes with `sha256:` smart-constructor enforcement)
**ADRs honored:** Phase 7 ADR-0010 (catalog ships as plugin-internal frozen YAML, not SQLite, not Sigstore), Phase 7 ADR-0011 (no Chainguard credential class — public images only), Phase 7 ADR-0004 (typed-vocabulary discipline — `ImageDigest` smart constructor enforces `sha256:`), Phase 7 ADR-0005 (plugin-internal home — catalog lives under the plugin tree, not under `src/codegenie/`)

## Context

Phase 7's headline transform — `DockerfileBaseImageSwapTransform` (S10-01) — needs to know, for a given CVE, which Chainguard distroless image to swap a vulnerable base into. The roadmap said one line: "a CVE-to-image-recommendation lookup table." `final-design.md §Synthesis ledger row 4` (score 13/15) took the best-practices-first answer over performance-first's SQLite-migration-into-Phase-3-`VulnIndex` proposal (rejected per critic Perf-4 — conflates two unrelated lookup domains) and over security-first's seven-component Sigstore-bundled signed-artifact apparatus (rejected per critic Sec-3 — architectural decree without ADR amendment for what was a one-line roadmap item).

ADR-0010 ratifies the answer: the catalog ships as `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` — a frozen YAML file inside the plugin tree (ADR-0005 — plugin-internal, not a top-level `src/codegenie/` artifact), refreshed via CODEOWNERS-reviewed PR (S9-03 documents the workflow), tamper-pinned via a CI file-hash fence (S9-02 lands the fence). No Sigstore, no STS, no live Chainguard registry API, no quarantine tier in Phase 7. ADR-0011 separately rejects the Chainguard credential class entirely — Chainguard's `cgr.dev/chainguard/*` distroless images are public and pullable unauthenticated; the security-first apparatus defended a credential that needn't exist.

This story is the first of the three Step 9 stories. It lands the canonical YAML file with at least one seeded row (the e2e fixture's CVE + Chainguard `node` digest used by S12-02), the Pydantic loader that validates the file at plugin-load time, and the unit-test coverage that pins happy-load, malformed-entry rejection, and missing-`sha256:`-digest rejection (via the `ImageDigest` smart constructor from S1-01).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §10 — `DistrolessMigrationPlugin`` — the catalog is named as a `data/` artifact under the plugin tree; consumed at apply-time by `DockerfileBaseImageSwapTransform`.
  - `../phase-arch-design.md §Edge cases` — "Poisoned catalog YAML" is explicitly enumerated as a defended threat; defense is the file-hash fence (S9-02) + Pydantic `extra="forbid"` rejection (this story).
  - `../phase-arch-design.md §Tradeoffs (consolidated)` row "Frozen YAML CVE-to-image lookup".
- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — the catalog's home, the schema shape, the refresh-process pointer, and the Sigstore-deferral note.
  - `../ADRs/0011-no-chainguard-credential-class.md` — Phase 7 ships no auth surface for Chainguard; all referenced digests are pulled unauthenticated.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the plugin-internal-home discipline this story honors (`data/` and `loader.py` both live under `plugins/distroless-migration--node--npm/`).
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — `ImageDigest` lives in `codegenie.types.identifiers` (per S1-01); the loader imports it; the catalog never re-defines it.
- **Production ADRs:**
  - `../../../production/design.md §2.6 — Organizational uniqueness as data, not prompts` — the parent rule this story instantiates: YAML lives as config, refreshed by humans.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/types/identifiers.py` after S1-01 — `CveId`, `ImageRef`, `ImageDigest` newtypes and `parse_image_digest` smart constructor (returns `Err` for any value not prefixed `sha256:`).
  - `src/codegenie/result.py` — canonical `Result[T, E]` (Phase-2 S1-04 home). The loader returns `Result[ChainguardCatalog, ParseError]`; do not fork.
  - `src/codegenie/types/errors.py` after Phase 3 S1-01 — `ParseError` frozen Pydantic model. The loader's error variants reuse this shape.
  - `src/codegenie/tccm/loader.py` — precedent for a YAML-→-Pydantic loader that returns `Result[..., ...]`. Mirror the file/line-diagnostic style on parse failures.
  - `src/codegenie/conventions/loader.py` — second YAML-→-Pydantic loader precedent; observe how malformed-row errors are surfaced.
- **Roadmap context:**
  - `docs/roadmap.md` Phase 7 — names the catalog as a one-line "Tooling & setup" deliverable; the rest of the story flows from ADR-0010 / ADR-0011 / ADR-0005.

## Goal

Land the canonical Chainguard CVE-to-image recommendation catalog as a frozen YAML file under the Phase 7 plugin's `data/` directory, plus a Pydantic-validated loader that returns `Result[ChainguardCatalog, ParseError]` and rejects any entry whose `image_digest` is not a `sha256:`-prefixed digest (via the `ImageDigest` smart constructor from S1-01). The catalog seeds with at least one row — the e2e fixture's CVE + Chainguard `node` recommendation digest used by S12-02 — so downstream Step 10 transforms have a non-empty lookup target on day one.

## Acceptance criteria

### Catalog file + schema

- [ ] AC-1 — `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` exists. The file is YAML with one top-level key, `entries:`, whose value is a list of mapping nodes; each entry has exactly four keys (`cve_id`, `recommended_chainguard_image`, `image_digest`, `notes`) and no others.
- [ ] AC-2 — At least one seeded row exists. The seeded row carries (a) the CVE id the S12-02 e2e fixture pins (`node-vulnerable-alpine/`), (b) `recommended_chainguard_image: cgr.dev/chainguard/node`, (c) an `image_digest` of shape `sha256:<64-hex>`, (d) a `notes:` string of ≤ 200 chars naming the publication date / advisory source. (The exact CVE id is fixture-coupled — pin to the S12-01/S12-02 fixture's vulnerability; the seeded `image_digest` may be a placeholder hex value updated when S12 lands, but it MUST be `sha256:`-prefixed at S9-01-time so the loader does not reject it.)
- [ ] AC-3 — The YAML file is UTF-8, LF line endings, ends with a single trailing newline, contains no tab characters, and parses under PyYAML `safe_load`. No `!!python/object` tags. (Verified by a unit test that asserts byte-level invariants — surface-friendly to the S9-02 hash fence.)
- [ ] AC-4 — A neighboring `plugins/distroless-migration--node--npm/data/README.md` (or schema-block at the top of the YAML, choose one — keep with codebase precedent) documents the schema in human form, names ADR-0010 as the rationale, names S9-02 as the tamper defense, and names S9-03 as the refresh process.

### Pydantic models + loader contract

- [ ] AC-5 — `plugins/distroless-migration--node--npm/data/__init__.py` exists and is empty (package marker only).
- [ ] AC-6 — `plugins/distroless-migration--node--npm/data/loader.py` exports a frozen Pydantic `ChainguardCatalogEntry(BaseModel)` with fields `cve_id: CveId`, `recommended_chainguard_image: ImageRef`, `image_digest: ImageDigest`, `notes: str`; `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-7 — `loader.py` exports a frozen Pydantic `ChainguardCatalog(BaseModel)` with one field `entries: tuple[ChainguardCatalogEntry, ...]` (immutable tuple, not `list`); `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-8 — `loader.py` exports `load_chainguard_catalog(path: Path) -> Result[ChainguardCatalog, ParseError]`. Pure function: opens `path`, reads bytes, `yaml.safe_load`s, validates via `ChainguardCatalog.model_validate(...)`, returns `Ok(catalog)` on success; on any `yaml.YAMLError`, `ValidationError`, or `OSError` returns `Err(ParseError(message=..., value=str(path)))`. The error `message` includes file path and (for `ValidationError`) the offending field name + line/column when PyYAML supplies one.
- [ ] AC-9 — `loader.py` exports a module-level helper `default_catalog_path() -> Path` returning the resolved absolute path to the shipped YAML; this is the single entry point Step 10 transforms use (no string-literal path arithmetic at call sites).

### Smart-constructor enforcement (the `sha256:` invariant)

- [ ] AC-10 — Every `ChainguardCatalogEntry.image_digest` is constructed via the `ImageDigest` smart constructor from S1-01. The Pydantic field uses a validator (or `BeforeValidator`) that calls `parse_image_digest(...)` and propagates the `ParseError` on `Err`. (No re-implementation of the `sha256:` regex inside the loader — ADR-0004 typed-vocabulary discipline forbids duplicating parse logic.)
- [ ] AC-11 — A test loads a YAML where one entry's `image_digest` is `"deadbeef..."` (no `sha256:` prefix); `load_chainguard_catalog` returns `Err(ParseError(...))` whose `message` names the offending field; the test asserts the error message names both the field (`image_digest`) and the entry's `cve_id` for human-friendly diagnosis.
- [ ] AC-12 — A test loads a YAML where one entry has an extra unknown key (`foo: bar`); the loader returns `Err(ParseError(...))` whose `message` names the extra key — this exercises `extra="forbid"`.

### Round-trip + error coverage

- [ ] AC-13 — `tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py` covers (a) happy load of the shipped YAML returns `Ok(ChainguardCatalog)` with `len(entries) >= 1`, (b) every entry's `image_digest` is an `ImageDigest`-typed value (round-trip), (c) the seeded row's `cve_id` matches the S12-02 fixture's CVE id by string equality, (d) malformed YAML (deliberately-broken syntax) → `Err(ParseError(...))` with a message mentioning the line number, (e) missing top-level `entries:` key → `Err(ParseError(...))`, (f) `entries:` present but empty (`entries: []`) → `Ok(ChainguardCatalog(entries=()))` (empty catalog is legal — Step 10 will degrade to `not_applicable`).
- [ ] AC-14 — `tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py::test_default_catalog_path_resolves` asserts `default_catalog_path()` exists, is absolute, and `load_chainguard_catalog(default_catalog_path())` returns `Ok`.

### Strict typing + structural conformance

- [ ] AC-15 — `mypy --strict plugins/distroless-migration--node--npm/data` clean. No `Any`, no untyped dicts, no `dict[str, Any]` on the public surface.
- [ ] AC-16 — `ruff format`, `ruff check`, `make lint-imports` all green. The loader does NOT import from `src/codegenie/plugins/` (port-before-adapter direction); it imports only from `codegenie.types.identifiers`, `codegenie.types.errors`, `codegenie.result`, `pydantic`, `pathlib`, and `yaml`.
- [ ] AC-17 — `make check` green (full local gate including Phase 3–6.5 regression suite — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-18 — The byte-edit allowlist fence (S5-01) reports no edits to Phase 0–6.5 locked files; this story only adds new files under `plugins/distroless-migration--node--npm/data/` and under `tests/unit/plugins/distroless_migration_node_npm/`.

## Implementation outline

1. **Create the data package.** `plugins/distroless-migration--node--npm/data/__init__.py` (empty). Confirm the parent `plugins/distroless-migration--node--npm/` already exists from S4-02; if not, this story is blocked on that step landing.
2. **Author the YAML.** Write `chainguard_image_recommendation_table.yaml` with one seeded entry pointing at the S12-02 fixture's CVE. Use a placeholder `sha256:<64-zero-hex>` digest if the real one isn't yet available — the loader must accept any `sha256:`-prefixed 64-hex value; correctness of the digest is fixture data, not loader logic. Document the source of the seeded row in a comment block at the top of the file naming ADR-0010.
3. **Define the Pydantic models.** `loader.py` imports `CveId`, `ImageRef`, `ImageDigest`, `parse_image_digest` from `codegenie.types.identifiers`. Define `ChainguardCatalogEntry` with the four fields; route `image_digest` through a `BeforeValidator` that calls `parse_image_digest` and re-raises `ParseError` as a Pydantic `ValueError`. Define `ChainguardCatalog` with `entries: tuple[ChainguardCatalogEntry, ...]`.
4. **Implement `load_chainguard_catalog(path)`.** Open file, `yaml.safe_load`, model-validate, return `Ok / Err`. Wrap all three exception classes (`yaml.YAMLError`, `ValidationError`, `OSError`) in a single `try / except` arms-of-three; emit `ParseError(message=..., value=str(path))`. Keep the function ≤ 30 LOC.
5. **Implement `default_catalog_path()`.** One-liner using `Path(__file__).parent / "chainguard_image_recommendation_table.yaml"`.
6. **Write the unit tests.** Cover happy / malformed-yaml / missing-prefix / extra-key / empty-list / round-trip cases. Use a `tmp_path`-based helper that writes test YAML to disk and calls `load_chainguard_catalog`. For the missing-prefix case, the test writes `image_digest: "deadbeef..."` (no `sha256:` prefix) and asserts the `Err`'s `message` names `image_digest` and the entry's `cve_id`.
7. **`mypy --strict` clean-up.** No `Any`. Pydantic's `BeforeValidator` import path is `pydantic.BeforeValidator` (v2). `tuple[ChainguardCatalogEntry, ...]` works under strict mode.
8. **Run `make check`.** Confirm Phase 3–6.5 regression suite green. The Phase 7 byte-edit allowlist fence (S5-01) should report no flagged edits since this story only adds new files.

## TDD plan (red → green → refactor)

### Red — failing test first

Author `tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py::test_load_chainguard_catalog_happy_path` BEFORE the loader exists:

```python
from pathlib import Path
from plugins.distroless_migration_node_npm.data.loader import (
    load_chainguard_catalog,
    default_catalog_path,
)
from codegenie.result import Ok

def test_load_chainguard_catalog_happy_path() -> None:
    result = load_chainguard_catalog(default_catalog_path())
    assert isinstance(result, Ok)
    assert len(result.value.entries) >= 1
    entry = result.value.entries[0]
    assert str(entry.image_digest).startswith("sha256:")
```

Run: `pytest tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py -x` — expect `ModuleNotFoundError` (loader module does not exist). This is the red bar.

### Green — minimum code

Implement the YAML + the loader + `default_catalog_path()` per the implementation outline. Re-run the test. Iterate until green. Add the malformed / missing-prefix / extra-key tests one at a time; each becomes red, then green.

### Refactor

- Extract the `BeforeValidator` for `image_digest` into a module-level helper if a second smart-constructor-routed field appears (it does not in Phase 7; rule-of-three is not yet triggered — leave inline).
- Confirm the loader is ≤ 30 LOC; if longer, factor out the exception-handling arm into a private helper.
- Pin the `tuple[...]` not `list[...]` decision: `frozen=True` Pydantic models still allow `list` field types but the tuple shape rules out mutation by downstream consumers entirely. Document in a one-line module-level docstring.

## Files to touch

**New files:**
- `plugins/distroless-migration--node--npm/data/__init__.py`
- `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml`
- `plugins/distroless-migration--node--npm/data/loader.py`
- `plugins/distroless-migration--node--npm/data/README.md` (or in-YAML header block — pick one; precedent in `plugins/vulnerability-remediation--node--npm/` decides)
- `tests/unit/plugins/distroless_migration_node_npm/__init__.py` (if not already present from S3-03 / S4-02)
- `tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py`

**Edited files:** None. This story does not edit any Phase 0–6.5 file; no byte-edit-allowlist row is consumed.

## Out of scope

- The file-hash fence (`tests/fence/test_phase7_chainguard_lookup_table_loads.py`) — S9-02's job.
- The catalog refresh process documentation (`docs/phases/07-migration-task-class/catalog-refresh-process.md`) — S9-03's job.
- Any Sigstore / cosign / STS / OIDC / GPG verification machinery — explicitly deferred per ADR-0010 (deferred-Sigstore-upgrade clause) and ADR-0011 (no Chainguard credential class).
- A live Chainguard registry API client. Pulls of `cgr.dev/chainguard/*` images happen at `DistrolessBuildGate`-time (S10-04) via Phase 2's existing registry-pull capability; this story ships only the lookup table.
- `DockerfileBaseImageSwapTransform` consumer wiring — S10-01 imports `default_catalog_path` + `load_chainguard_catalog` from this story.
- Pre-populating the catalog with multiple CVEs / multiple base-image-variants. One seeded row is sufficient for S12-02; richer content is data-collection work owned by the catalog-refresh-process operator workflow (S9-03), not by this story.

## Notes for the implementer

- **Do not duplicate the `sha256:` regex.** ADR-0004 typed-vocabulary discipline: the only `sha256:` parser is `parse_image_digest` in `codegenie.types.identifiers` (S1-01). Route through it via `BeforeValidator`. If you find yourself writing a regex inside `loader.py`, stop — that is a Rule-8 violation against S1-01.
- **`tuple` over `list` for `entries:`.** Frozen Pydantic models accept `list` field types but consumers can still mutate the list reference outside the model. `tuple[...]` rules out the bug class entirely. Two-character cost; large-class-of-bugs payoff.
- **`extra="forbid"` is load-bearing.** ADR-0010 names the poisoned-YAML threat model explicitly. The Pydantic `extra="forbid"` rejection is one of the two defenses (the other is the S9-02 file-hash fence). A drift to `extra="allow"` is an ADR violation.
- **`yaml.safe_load`, never `yaml.load`.** The repo's `forbidden-patterns` pre-commit hook bans the latter (along with `pickle.loads`, etc.). `safe_load` is the only correct choice and produces no `!!python/object`-tag attack surface.
- **Seeded-row CVE id is fixture-coupled.** S12-01 lands the fixture portfolio. Until S12-01 ships, pick a plausible CVE id (e.g., the CVE that motivates the S12-02 e2e narrative — pick from the published Chainguard advisories matching `node:lts-alpine`) and document the choice in a comment. S12-01 may amend this story's seeded row when it lands; that amendment is a one-line YAML edit + a refreshed S9-02 hash (the legitimate CODEOWNERS refresh path documented in S9-03).
- **`Result` import path.** `codegenie.result` is canonical (Phase 2 S1-04). Do not import `Result` from `codegenie.types.result`; that module does not exist (Phase 3 S1-01 validation explicitly rejected creating it).
- **Plugin-internal home is non-negotiable.** ADR-0005 + ADR-0010. The catalog does NOT live under `src/codegenie/`. Importing the catalog loader from `src/codegenie/` would invert the dependency direction (the primitive imports from the plugin); `make lint-imports` would catch it, but the design is wrong before the linter ever runs.
- **No `Any` in the public surface.** S1-06's `test_no_any_in_provenance_surface.py` is primitive-only, but `mypy --strict` on the loader is the door. If you find yourself reaching for `Any`, the right move is to define a tighter Pydantic model.
- **File ends with one trailing newline.** Both for POSIX hygiene and to make the S9-02 hash deterministic across editors that auto-trim.
- **Catalog grows by addition.** Future Chainguard recommendations append new rows to `entries:`; the schema does not need to grow. If a future CVE needs a per-row field the schema doesn't have (e.g., `migration_notes_url`), that's a Phase-7-amend or Phase-8 conversation — open an ADR, not a quiet schema edit.
