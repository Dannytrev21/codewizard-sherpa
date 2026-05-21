# Story S14-01 — Build-toolchain classification catalogs (frozen YAML) + Pydantic loader + file-hash fence

**Step:** Step 14 — Build-toolchain classification + native modules (G3)
**Status:** Ready
**Effort:** M
**Depends on:** S13-03 (the Step-13 ADR-0029 byte-edit-allowlist amendment landed — `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` already enumerates the Amendment-A allowance rows, so the new `data/` catalogs this story ships are pre-permitted; S13-03 also stabilizes the Phase 7 plugin `data/` directory created by S9-01)
**ADRs honored:** Phase 7 ADR-0020 (build-time-only toolchain vs runtime libraries is a frozen data catalog, not a heuristic — the headline decision this story implements), Phase 7 ADR-0029 (the byte-edit allowlist enumerates every Amendment-A source-file addition — the two catalog YAMLs ride row category 7 of ADR-0029), Phase 7 ADR-0010 (frozen-catalog discipline precedent — plugin-internal YAML, CODEOWNERS-gated, file-hash fenced), Phase 7 ADR-0005 (plugin-internal home — catalogs live under the plugin tree, never under `src/codegenie/`), Phase 7 ADR-0009 (the byte-edit allowlist this story's files are pre-permitted by, via ADR-0029), Phase 3 ADR-0011 (honest framing — the hash fence is integrity attestation, not a cryptographic signature)

## Context

`final-design.md §Amendment A §A.2` gap G3: the multi-stage refactor recipe (`DockerfileMultiStageRefactorTransform`, design-of-record §10) must place each dependency in the correct Dockerfile stage. Build-time-only toolchain — `gcc`, `g++`, `make`, `python3`, `*-dev` / `*-headers` packages — belongs in the `cgr.dev/chainguard/node:*-dev` builder stage and **must not** leak into the distroless runner. Runtime libraries — `libssl`, `libstdc++`, `ca-certificates` — belong in the runner. A misclassification ships either a bloated image (toolchain leaked into the runner) or a `dlopen` failure at runtime (a runtime library dropped). The recipe also needs a third class: `diagnostic` packages (`curl`, `bash`, `strace`) belong in *neither* production stage and signal a refactor smell the PR description should surface.

`apk add` / `apt-get install` package names do not announce their nature. `gcc` is build-time; `gcompat` is runtime; `python3` is build-time *for node-gyp* but could be a runtime dep elsewhere. ADR-0020 §Options-considered rejects the naive reading — "names containing `dev` or `gcc` are build-time" — as a heuristic (Option A): fragile, false-positive prone (`libdevmapper` is a runtime library; `nodejs-dev` overlaps both meanings), and unauditable — an operator cannot see *why* a package was staged where it was. ADR-0020 §Decision adopts Option B: two frozen YAML classification catalogs, one per package manager, each a flat map of package name → `build_toolchain | runtime_library | diagnostic`, CODEOWNERS-gated and file-hash fenced. The catalogs load through the established catalog-loader seam — no per-call file parse, no branching `if/elif` on package name. This mirrors the codebase's standing marker-catalog discipline (`_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE`) and Phase 7 ADR-0010's CVE-to-image YAML.

This story is the first of the two Step 14 stories. It lands the two canonical YAML catalogs (`apk_classification.yaml`, `apt_classification.yaml`), each seeded with the common cases; the Pydantic loader (`frozen=True, extra="forbid"`) that returns `Result[ToolchainCatalog, ParseError]` and rejects any entry whose classification value is not one of the three known dispositions; and the file-hash fence that mirrors S9-02's shape so an unreviewed catalog edit is a CI break. S14-02 (the native-module slice) depends on this story landing.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §17` — "Build-toolchain classification catalog + native-module slice" — names the two data files by path, the three-way classification, the catalog-loader seam ("Classification is data, not heuristic"), and the consuming multi-stage recipe.
  - `../phase-arch-design.md §Component design — Amendment A` preamble — "Each obeys the frozen Probe ABC (production ADR-0007) or the established registry/strategy seams" — the catalog-loader seam is the established seam this story extends.
  - `../final-design.md §Amendment A §A.2` gap G3 row — disposition GATHER, component "`apk/apt` classification catalog + `NodeManifestProbe` native-module slice", ADR 0020, Step 14.
  - `../final-design.md §Amendment A §A.4` — "the gather probes (Steps 13–15) must land *before* the recipe stories (existing Step 10) execute — the recipes consume the new slices."
- **Phase ADRs:**
  - `../ADRs/0020-build-toolchain-classification-catalog.md` — the headline decision: §Decision (two catalogs, three-way classification, catalog-loader seam, file-hash fence), §Options-considered (Option A heuristic rejected, Option C runtime introspection rejected), §Consequences (net-new files under CODEOWNERS, file-hash fence asserts content hash, golden fixtures), §Pattern-fit (Strategy via data / marker catalog), §Reversibility (catalogs are data — a misclassification is a one-row PR plus a hash re-baseline).
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md §Decision row 7` — "New data catalogs under the plugin's `data/` directory — `apk_classification.yaml`, `apt_classification.yaml`, and any Amendment-A marker catalogs; wholly new files." This story's catalogs ride that pre-permitted row.
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — the frozen-catalog discipline precedent: plugin-internal YAML, `extra="forbid"` Pydantic rejection, file-hash fence as the named tamper defense.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the plugin-internal-home discipline: `data/` and the loader both live under `plugins/distroless-migration--node--npm/`, never under `src/codegenie/`.
- **Production ADRs:**
  - `../../../production/design.md §2.6 — Organizational uniqueness as data, not prompts` — the parent rule this story instantiates: classification lives as config, refreshed by humans via CODEOWNERS-reviewed PR.
- **Sibling stories:**
  - `S9-01-chainguard-catalog-and-loader.md` — the frozen-YAML-plus-Pydantic-loader precedent this story mirrors exactly. The `data/__init__.py`, the `BaseModel(frozen=True, extra="forbid")` shape, the `Result[..., ParseError]` return, `default_*_path()` — all carry forward.
  - `S9-02-chainguard-catalog-file-hash-fence.md` — the file-hash-fence pattern this story's fence mirrors: a single-file file-bytes hash (`hashlib.sha256(path.read_bytes())`), pinned constant, honest-framing module docstring, planted-violation evidence. This story ships its own fence in one go (no S5-04-style placeholder split — the catalogs and their fence land together).
  - `S14-02-native-modules-slice.md` — the second Step 14 story; depends on this one. It adds the `native_modules` slice field; the multi-stage recipe consumes *both* this story's catalogs and S14-02's slice.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `plugins/distroless-migration--node--npm/data/loader.py` (from S9-01) — the YAML→Pydantic loader precedent. Mirror the file/line-diagnostic style on parse failures, the three-armed `try/except` (`yaml.YAMLError`, `ValidationError`, `OSError`), the `default_*_path()` helper.
  - `src/codegenie/conventions/loader.py` — the established catalog-loader seam: a multi-file YAML→Pydantic loader returning a `Result`-shaped outcome. Observe how malformed-row errors are surfaced and how `safe_yaml` is the parse chokepoint.
  - `src/codegenie/tccm/loader.py` — second YAML→Pydantic loader precedent; the file/line-diagnostic style.
  - `src/codegenie/result.py` — canonical `Result[T, E]` (`Ok` / `Err`). The loader returns `Result[ToolchainCatalog, ParseError]`; do not fork.
  - `src/codegenie/types/errors.py` — `ParseError` frozen Pydantic model. The loader's error variants reuse this shape.
  - `src/codegenie/types/identifiers.py` — the newtype-identifier home. This story adds `PackageName` and `Classification` newtypes here is **wrong** — see Notes; the newtypes live plugin-internally next to the loader.
  - `tests/fence/test_phase7_chainguard_lookup_table_loads.py` (from S9-02) — the catalog file-hash fence shape this story mirrors.
- **Roadmap context:**
  - `docs/roadmap.md` Phase 7 — names the distroless-migration task class; Amendment A deepens its gather pipeline.

## Goal

Land two frozen YAML build-toolchain classification catalogs under the Phase 7 plugin's `data/` directory (`apk_classification.yaml`, `apt_classification.yaml`), each mapping a package name to one of `build_toolchain | runtime_library | diagnostic`; a Pydantic-validated loader (`frozen=True, extra="forbid"`) that returns `Result[ToolchainCatalog, ParseError]` and rejects any entry whose classification value is not one of the three known dispositions; and a file-hash fence (mirroring S9-02) that pins each catalog's content hash so an unreviewed edit is a CI break. The catalogs are seeded with the common cases so the Step-14-onward multi-stage recipe has a non-empty classification target on day one.

## Acceptance criteria

### Catalog files + schema

- [ ] AC-1 — `plugins/distroless-migration--node--npm/data/apk_classification.yaml` and `plugins/distroless-migration--node--npm/data/apt_classification.yaml` both exist. Each is YAML with one top-level key, `packages:`, whose value is a list of mapping nodes; each entry has exactly two keys (`name`, `classification`) and no others.
- [ ] AC-2 — Each catalog's `classification` value, on every entry, is one of exactly three string literals: `build_toolchain`, `runtime_library`, `diagnostic`. No fourth value appears in either shipped file. (Verified by a unit test that walks every entry of both shipped catalogs and asserts membership in the three-element frozen set.)
- [ ] AC-3 — `apk_classification.yaml` is seeded with at least the common Alpine cases: `gcc`, `g++`, `make`, `python3`, `linux-headers`, `musl-dev`, `libc-dev` → `build_toolchain`; `libssl3`, `ca-certificates`, `libstdc++` → `runtime_library`; `curl`, `bash` → `diagnostic`. `apt_classification.yaml` is seeded with the Debian equivalents: `gcc`, `g++`, `make`, `python3`, `linux-libc-dev`, `build-essential` → `build_toolchain`; `libssl3`, `ca-certificates`, `libstdc++6` → `runtime_library`; `curl`, `bash` → `diagnostic`. (Exact package-name spellings are distro-coupled — `libssl3` on Alpine vs `libssl3` on Debian, `linux-headers` vs `linux-libc-dev`; pin each to the real upstream package name.)
- [ ] AC-4 — Within each catalog, every `name` is unique — no package appears twice (a package cannot be both `build_toolchain` and `runtime_library`). The loader enforces this (AC-9); a unit test asserts a deliberately-duplicated-name catalog is rejected.
- [ ] AC-5 — Both YAML files are UTF-8, LF line endings, end with a single trailing newline, contain no tab characters, and parse under PyYAML `safe_load`. No `!!python/object` tags. (Verified by a unit test that asserts byte-level invariants — surface-friendly to the file-hash fence.)
- [ ] AC-6 — A schema-block comment at the top of each YAML (or a neighboring `plugins/distroless-migration--node--npm/data/README.md` section — match S9-01's choice) documents the schema in human form, names ADR-0020 as the rationale, names the file-hash fence as the tamper defense, and states that the three classification values are a closed set.

### Newtypes + Pydantic models + loader contract

- [ ] AC-7 — `plugins/distroless-migration--node--npm/data/toolchain_catalog.py` (or `toolchain_loader.py` — match S9-01's `loader.py` naming if a single Phase 7 catalog loader file is the precedent; otherwise a dedicated module) exports a `PackageName` newtype (`NewType("PackageName", str)`) and a `Classification` sum type — a `Literal["build_toolchain", "runtime_library", "diagnostic"]` type alias plus a module-level `Final` frozenset `_KNOWN_CLASSIFICATIONS` of the three values. No raw `str` for either domain concept on the public surface (newtype-identifier discipline; ADR-0020 §Pattern-fit "newtype + sum-type domain-modeling discipline").
- [ ] AC-8 — The module exports a frozen Pydantic `ToolchainCatalogEntry(BaseModel)` with fields `name: PackageName`, `classification: Classification`; `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-9 — The module exports a frozen Pydantic `ToolchainCatalog(BaseModel)` with one field `packages: tuple[ToolchainCatalogEntry, ...]` (immutable tuple, not `list`); `model_config = ConfigDict(frozen=True, extra="forbid")`. A `model_validator` (or equivalent) rejects a catalog with duplicate `name` values, emitting a validation error naming the duplicated package.
- [ ] AC-10 — The module exports `load_toolchain_catalog(path: Path) -> Result[ToolchainCatalog, ParseError]`. Pure function: opens `path`, reads bytes, `yaml.safe_load`s, validates via `ToolchainCatalog.model_validate(...)`, returns `Ok(catalog)` on success; on any `yaml.YAMLError`, `ValidationError`, or `OSError` returns `Err(ParseError(message=..., value=str(path)))`. The error `message` includes the file path and (for `ValidationError`) the offending field name + entry `name` when available.
- [ ] AC-11 — The module exports two module-level helpers `default_apk_catalog_path() -> Path` and `default_apt_catalog_path() -> Path`, each returning the resolved absolute path to its shipped YAML; these are the single entry points the multi-stage recipe uses (no string-literal path arithmetic at call sites).
- [ ] AC-12 — The module exports a typed lookup helper `classify(catalog: ToolchainCatalog, package: PackageName) -> Classification | None` — a pure dict-backed lookup returning the classification for a known package or `None` for an unclassified one. `None` is the honest signal for "unclassified" (ADR-0020 §Tradeoffs — "a missing package is a gather gap, surfaced as `unclassified` rather than guessed"); the recipe surfaces `None` as a WARN, never a guess.

### Unknown-classification rejection (the closed-set invariant)

- [ ] AC-13 — A test loads a YAML where one entry's `classification` is `"build-time"` (a plausible-but-wrong value not in the closed set); `load_toolchain_catalog` returns `Err(ParseError(...))` whose `message` names both the offending field (`classification`) and the entry's `name` for human-friendly diagnosis. This exercises the `Literal` sum type — Pydantic rejects any value outside the three literals.
- [ ] AC-14 — A test loads a YAML where one entry has an extra unknown key (`stage: builder`); the loader returns `Err(ParseError(...))` whose `message` names the extra key — this exercises `extra="forbid"`.
- [ ] AC-15 — A test loads a YAML missing the top-level `packages:` key → `Err(ParseError(...))`; a test loads `packages: []` (present but empty) → `Ok(ToolchainCatalog(packages=()))` (an empty catalog is legal — every package is then `unclassified` and the recipe degrades to WARN).

### File-hash fence (tamper detection — mirrors S9-02)

- [ ] AC-16 — `tests/fence/test_phase7_toolchain_classification_catalogs.py` exists and pins each catalog's content hash. It defines `_APK_CATALOG_SHA256_PINNED` and `_APT_CATALOG_SHA256_PINNED` (each the actual `"sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()` of the shipped file), and a `test_<apk|apt>_catalog_hash_matches_pinned` per catalog that recomputes the hash and asserts equality, naming both expected and observed digests in the failure message.
- [ ] AC-17 — The fence module docstring uses the S9-02 honest-framing wording: this is **integrity attestation, not a cryptographic signature** (Phase 3 ADR-0011 carry-forward). It does NOT use "signed," "signature," "cryptographically verified," "tamper-proof," or "non-repudiable." It states the refresh path: a CODEOWNERS-gated PR edits the catalog YAML and the pinned-hash constant in lockstep. It uses a single-file file-bytes hash, not `compute_plugin_tree_digest` (the catalogs are individual files), and the docstring documents that choice.
- [ ] AC-18 — The fence carries a third test `test_toolchain_catalogs_load_clean` that calls `load_toolchain_catalog(default_apk_catalog_path())` and `load_toolchain_catalog(default_apt_catalog_path())` and asserts both return `Ok`. Belt-and-braces: the hash test catches byte-level tamper, the loader test catches a schema regression that happens to keep the file present.
- [ ] AC-19 — Planted-violation evidence (Rule 12 fail-loud): on a throwaway branch, mutate one byte of `apk_classification.yaml` (e.g. flip a character in one `name`); run `pytest tests/fence/test_phase7_toolchain_classification_catalogs.py`; `test_apk_catalog_hash_matches_pinned` fails naming expected-vs-observed. Revert; run again; green. Record the red git SHA + green git SHA + captured terminal output in `_attempts/S14-01.md` as a 5–10 line evidence block.

### Strict typing + structural conformance

- [ ] AC-20 — `mypy --strict` clean on the catalog loader module and the fence file. No `Any`, no untyped dicts, no `dict[str, Any]` on the public surface.
- [ ] AC-21 — `ruff format`, `ruff check`, `make lint-imports` all green. The loader imports only from `codegenie.result`, `codegenie.types.errors`, `pydantic`, `pathlib`, `typing`, and `yaml` (the parse chokepoint) — it does NOT import from `src/codegenie/plugins/` (port-before-adapter direction).
- [ ] AC-22 — `make fence`, `make check` both green (full local gate including the Phase 3–6.5 regression suite — hard pre-merge gate per Phase 7 ADR-0009). The new fence file is collected by `make fence`.
- [ ] AC-23 — The byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) reports no flagged edits: this story adds only new files under `plugins/distroless-migration--node--npm/data/` (pre-permitted by ADR-0029 row 7) and under `tests/` (which the allowlist does not gate). No Phase 0–6.5 / Phase 3 file is byte-edited.

## Implementation outline

1. **Confirm the `data/` package and the ADR-0029 allowlist row exist.** `plugins/distroless-migration--node--npm/data/__init__.py` already exists from S9-01. Confirm `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` already carries ADR-0029 row category 7 (S13-03's job) — the two new catalog YAMLs are pre-permitted; if the row is absent, this story is blocked on S13-03 landing.
2. **Author the two YAML catalogs.** Write `apk_classification.yaml` and `apt_classification.yaml` per AC-3's seed lists. One top-level `packages:` key; each entry exactly `{name, classification}`. Add a schema-block comment at the top of each naming ADR-0020 and the closed three-value set. Use the real upstream package-name spellings per distro (`linux-headers` on Alpine, `linux-libc-dev` / `build-essential` on Debian).
3. **Define the newtypes + sum type.** In the loader module: `PackageName = NewType("PackageName", str)`; `Classification = Literal["build_toolchain", "runtime_library", "diagnostic"]`; `_KNOWN_CLASSIFICATIONS: Final[frozenset[str]] = frozenset({"build_toolchain", "runtime_library", "diagnostic"})`.
4. **Define the Pydantic models.** `ToolchainCatalogEntry` with `name: PackageName`, `classification: Classification`, `model_config = ConfigDict(frozen=True, extra="forbid")`. `ToolchainCatalog` with `packages: tuple[ToolchainCatalogEntry, ...]`, same config, plus a `model_validator(mode="after")` that builds a set of names and raises a `ValueError` naming any duplicate.
5. **Implement `load_toolchain_catalog(path)`.** Open file, `yaml.safe_load`, `model_validate`, return `Ok` / `Err`. Wrap `yaml.YAMLError`, `ValidationError`, `OSError` in one three-armed `try/except`; emit `ParseError(message=..., value=str(path))`. Keep ≤ 35 LOC.
6. **Implement `default_apk_catalog_path()` / `default_apt_catalog_path()`.** One-liners: `Path(__file__).parent / "apk_classification.yaml"` and `.../"apt_classification.yaml"`.
7. **Implement `classify(catalog, package)`.** A pure helper that builds a `dict[PackageName, Classification]` from `catalog.packages` and returns `.get(package)` — `None` for an unclassified package. (Build the dict at call time; the catalogs are small. If a future profiling pass shows it matters, memoize behind a frozen wrapper — rule-of-three not yet triggered.)
8. **Write the loader unit tests.** Cover happy load of both shipped catalogs; unknown-classification rejection (AC-13); extra-key rejection (AC-14); missing-`packages` and empty-`packages` (AC-15); duplicate-name rejection (AC-4); `classify` returns the right disposition for a seeded package and `None` for an unknown one. Use a `tmp_path`-based helper that writes test YAML to disk.
9. **Author the file-hash fence.** `tests/fence/test_phase7_toolchain_classification_catalogs.py`: compute each catalog's `hashlib.sha256(path.read_bytes()).hexdigest()`, pin as `_APK_CATALOG_SHA256_PINNED` / `_APT_CATALOG_SHA256_PINNED` (`sha256:`-prefixed), add the two hash-match tests + the loader-round-trip test. Module docstring per AC-17 — mirror `plugins/PLUGINS.lock.README.md §"Honest framing"`.
10. **Plant the violation (AC-19).** Throwaway branch; mutate one byte of `apk_classification.yaml`; run the fence; capture the failure; revert; run again; capture the pass. Record red SHA + green SHA + output in `_attempts/S14-01.md`.
11. **Run `make check`.** Confirm the Phase 3–6.5 regression suite is green and the byte-edit allowlist fence reports no flagged edits.

## TDD plan — red / green / refactor

### Red — failing test first

Author `tests/unit/plugins/distroless_migration_node_npm/test_toolchain_catalog_loader.py::test_unknown_classification_is_rejected` BEFORE the loader exists:

```python
from pathlib import Path

import pytest

from plugins.distroless_migration_node_npm.data.toolchain_catalog import (
    load_toolchain_catalog,
)
from codegenie.result import Err


def test_unknown_classification_is_rejected(tmp_path: Path) -> None:
    """A classification value outside the closed three-value set is a hard
    Err — ADR-0020 forbids a heuristic guess, so an unknown disposition
    must fail loudly, naming the offending field and package."""
    bad = tmp_path / "apk_classification.yaml"
    bad.write_text(
        "packages:\n"
        "  - name: gcc\n"
        "    classification: build-time\n",  # not in {build_toolchain,...}
        encoding="utf-8",
    )
    result = load_toolchain_catalog(bad)
    assert isinstance(result, Err)
    assert "classification" in result.error.message
    assert "gcc" in result.error.message
```

Run: `pytest tests/unit/plugins/distroless_migration_node_npm/test_toolchain_catalog_loader.py -x` — expect `ModuleNotFoundError` (the loader module does not exist). This is the red bar. The test encodes *intent* (ADR-0020's no-heuristic rule), not just behavior — it would fail if the loader silently coerced `build-time` to `build_toolchain`.

### Green — minimum code

Implement the two YAML catalogs + the newtypes + the Pydantic models + `load_toolchain_catalog` + `default_*_path()` + `classify` per the implementation outline. Re-run the test. Iterate until green. Add the extra-key, missing-`packages`, empty-`packages`, duplicate-name, and `classify`-lookup tests one at a time; each becomes red, then green. Then author the file-hash fence and run the planted-violation cycle.

### Refactor

- Extract the three-armed `try/except` exception-handling arm into a private helper only if `load_toolchain_catalog` exceeds 35 LOC.
- Confirm `Classification` is a `Literal`, not a string-typed enum class — the `Literal` sum type is the lightest shape Pydantic validates against the closed set; an `Enum` would add ceremony for no gain (ADR-0020 §Pattern-fit "sum-type domain-modeling").
- Pin the `tuple` not `list` decision for `packages:` in a one-line module docstring note — frozen models accept `list` field types but consumers can still mutate the list reference; `tuple` rules out the bug class.
- Confirm `classify` returns `Classification | None`, never raises — `None` is the honest "unclassified" signal the recipe handles as a WARN.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/data/apk_classification.yaml` | **New.** Frozen Alpine `apk` package → classification catalog, seeded with the common cases. CODEOWNERS-gated. |
| `plugins/distroless-migration--node--npm/data/apt_classification.yaml` | **New.** Frozen Debian `apt` package → classification catalog, seeded with the common cases. CODEOWNERS-gated. |
| `plugins/distroless-migration--node--npm/data/toolchain_catalog.py` | **New.** `PackageName` / `Classification` newtypes, `ToolchainCatalogEntry` / `ToolchainCatalog` frozen Pydantic models, `load_toolchain_catalog`, `default_apk_catalog_path` / `default_apt_catalog_path`, `classify`. |
| `plugins/distroless-migration--node--npm/data/README.md` | **Edit** (or in-YAML header blocks — match S9-01's choice) — document the classification schema, name ADR-0020, name the file-hash fence. |
| `tests/unit/plugins/distroless_migration_node_npm/test_toolchain_catalog_loader.py` | **New.** Loader unit tests: happy load, unknown-classification rejection, extra-key rejection, missing/empty `packages`, duplicate-name rejection, `classify` lookup. |
| `tests/fence/test_phase7_toolchain_classification_catalogs.py` | **New.** File-hash fence: pins each catalog's sha256; honest-framing docstring; loader-round-trip test. Mirrors S9-02. |
| `_attempts/S14-01.md` | **New.** Append-only attempt log: AC-19 planted-violation evidence (red SHA + green SHA + terminal output). |

**Edited files:** None under `src/codegenie/`. This story does not byte-edit any Phase 0–6.5 / Phase 3 file; the catalog YAMLs are pre-permitted by ADR-0029 row category 7.

## Out of scope

- **The `native_modules` slice extension to `NodeManifestProbe`.** S14-02's job. This story ships only the classification catalogs; S14-02 adds the slice field and the multi-stage recipe consumes both.
- **The multi-stage refactor recipe's consumption of the catalogs.** `DockerfileMultiStageRefactorTransform` (design-of-record §10) imports `load_toolchain_catalog` + `classify` + `default_*_path` from this story; that wiring is the recipe story's job, not this one.
- **Resolving which packages a given Dockerfile actually installs.** This story ships the *classification* — the recipe walks the resolved `apk`/`apt` install set against the catalogs. The install-set extraction is a Dockerfile-parse concern owned by the recipe.
- **Any Sigstore / cosign / signed-artifact machinery.** Explicitly deferred per Phase 7 ADR-0010; the file-hash fence is the named tamper defense, and that is deliberate (ADR-0020 §Decision mirrors the S9-02 hash-fence pattern, not a signature).
- **Pre-populating the catalogs exhaustively.** The seed set (AC-3) covers the common cases needed by the Step-14 golden fixtures. Richer coverage is catalog-curation work owned by the CODEOWNERS-reviewed refresh path (ADR-0020 §Tradeoffs — "the catalog must be curated and kept current"), not by this story.
- **A lock-file regeneration CLI for the catalog hashes.** Manual `hashlib.sha256(...)` + paste-into-constant is the documented Phase 7 mechanism (carried forward from S9-02). Automated tooling is Phase 11 territory.

## Notes for the implementer

- **Classification is data, not branching code.** ADR-0020 §Decision and §Pattern-fit are explicit: the build-vs-runtime policy is a frozen map iterated at one call site, never an `if/elif` on package name. If you find yourself writing `if "gcc" in name or name.endswith("-dev")`, stop — that is the Option-A heuristic ADR-0020 §Options-considered rejected. The catalog rows are the policy.
- **`diagnostic` is a first-class third value, not an afterthought.** ADR-0020 §Tradeoffs names it explicitly: `curl`/`bash`/`strace`-class packages belong in *neither* production stage. A two-value `build | runtime` model would force a wrong guess for these; the three-value sum type names the "belongs in neither" case honestly.
- **`None` from `classify` is the honest "unclassified" signal.** ADR-0020 §Tradeoffs: "a missing package is a gather gap, surfaced as `unclassified` rather than guessed." Do not make `classify` raise on an unknown package, and do not default an unknown package to `runtime_library` "to be safe" — that is a silent guess. The recipe handles `None` as a WARN in the PR description.
- **`extra="forbid"` is load-bearing.** Mirrors S9-01's poisoned-YAML defense. A drift to `extra="allow"` would let an unreviewed catalog edit smuggle in a key the loader ignores. Pair it with the file-hash fence — together they are the two defenses ADR-0020 §Consequences names.
- **`yaml.safe_load`, never `yaml.load`.** The repo's `forbidden-patterns` pre-commit hook bans the latter. `safe_load` is the only correct choice and produces no `!!python/object`-tag attack surface. The `codegenie.parsers.safe_yaml` chokepoint is the established seam if a shared wrapper is wanted — match the `conventions/loader.py` precedent.
- **Two catalogs, one loader.** `apk_classification.yaml` and `apt_classification.yaml` share the exact same schema; a single `load_toolchain_catalog(path)` loads either. Do not write `load_apk_catalog` / `load_apt_catalog` as separate functions — that is duplication. The two `default_*_path()` helpers are the only per-distro surface.
- **Newtypes live plugin-internally.** `PackageName` and `Classification` are Phase-7-plugin domain concepts; they live next to the loader, NOT in `codegenie.types.identifiers`. Adding them to the core `identifiers` module would invert the dependency direction (the core primitive importing a plugin concept) — `make lint-imports` would catch it, but the design is wrong before the linter runs. (Contrast S9-01's `ImageDigest`, which *is* a core primitive because Phase 3 also uses it.)
- **`tuple` over `list` for `packages:`.** Frozen Pydantic models accept `list` field types but consumers can still mutate the list reference outside the model. `tuple[...]` rules out the bug class entirely. Two-character cost; large-class-of-bugs payoff. Mirrors S9-01's `entries:` decision.
- **The file-hash fence is integrity attestation, not a signature.** Phase 3 ADR-0011 carry-forward, identical to S9-02. Read `plugins/PLUGINS.lock.README.md §"Honest framing"` before writing the fence docstring. Do NOT use "signed," "signature," "tamper-proof," or "non-repudiable." The social anchor is `.github/CODEOWNERS` requiring a named reviewer on the catalog paths; a determined adversary with merge rights defeats the fence by editing both files in one PR — say so, do not over-claim.
- **Single-file hash, not tree-walk.** Each catalog is one file; hash each file's bytes directly with `hashlib.sha256(path.read_bytes())`. Do NOT use `compute_plugin_tree_digest` — that is a directory-walk hash for `PLUGINS.lock` and over-collects under refactors, defeating the per-file tamper-detection purpose. AC-17 makes the docstring document this choice; mirror S9-02 §AC-2.
- **Catalogs grow by addition.** A new Alpine/Debian package is a new row in `packages:`; the schema never grows. If a future package needs a per-row field the schema lacks (e.g. `notes`), that is an ADR-amend conversation — open one, not a quiet schema edit. ADR-0020 §Reversibility: "correcting a misclassification is a one-row PR plus a hash re-baseline, no code change."
- **The ADR-0029 allowlist row is pre-permitted, not amended here.** ADR-0029 §Decision row category 7 already names `apk_classification.yaml` and `apt_classification.yaml`. S13-03 lands the allowlist amendment; this story consumes it. Do NOT add an allowlist row in this story — if the byte-edit fence flags the new YAMLs, S13-03 did not land its row and that is the conversation to surface (Rule 12), not a reason to silently add a row here.
