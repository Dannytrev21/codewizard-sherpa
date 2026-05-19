# Validation report — S7-01 (`vulnerability-remediation--node--npm` scaffold)

**Validated:** 2026-05-19
**Validator:** `phase-story-validator` skill (automated, scheduled task `story-validation-corrector`)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S7-01-vuln-node-npm-plugin-scaffold.md`
**Verdict:** **HARDENED** — substantial edits applied. Story now traces to real S2-02/S2-03/S2-04/S3-03 code surfaces. One architectural gap (resolver's TCCM placeholder vs. the real TCCM model) surfaced and documented as AC-13 (deferred).

## Why HARDENED, not RESCUE

The story's *goal* is sound and achievable. The defects were all in technical detail (wrong field paths, wrong class names, wrong API names, mutation-vulnerable tests) — not in scope, intent, or architectural alignment. Each defect was concretely fixable by reference to the existing code; no defect required the goal to be reshaped. Per the validator's verdict rubric, this is HARDENED.

## Context Brief

- **Story snapshot.** Land the first concrete production plugin under `plugins/vulnerability-remediation--node--npm/`: manifest, TCCM, api.py with `register_plugin(plugin)` at module import time, `PLUGINS.lock` row, and prove the resolver returns a `ConcreteResolution` for the scope (specificity-3 beats the universal `(*,*,*)` fallback at specificity-0).
- **Sibling-family lineage.** This is the **1st** concrete production plugin. S7-04 (synthetic third) hits rule-of-three. S7-03 ships the real universal-fallback plugin; until then, tests register `make_universal_fallback()` from `tests/fixtures/plugins/universal_fallback_fixture.py`.
- **Load-bearing commitments implicated.** "Extension by addition" (CLAUDE.md) — zero edits to kernel. "Facts, not judgments" — the plugin contributes TCCM and adapter pointers, no business logic. ADR-0002 (kernel-frozen), ADR-0003 (specificity-then-precedence resolution), ADR-0004 (TCCM `provides` is the kernel's escape hatch from task-class knowledge), ADR-0011 (`PLUGINS.lock` integrity-check framing).

## Critic findings (consolidated)

Four critics ran in parallel: Coverage (`CV`), Test-Quality (`TQ`), Consistency (`CN`), Design-Patterns (`DP`). Findings consolidated and de-duplicated below.

### Block-severity (all addressed by the edit)

| ID | Finding | Resolution |
|---|---|---|
| CN-1 | `scope` shown as a scalar slug in story prose; real `ManifestScope` is a nested submodel with `task_class | languages | build_systems` fields. | Rewrote AC-1 + Implementation outline §2 to show the canonical nested-dict YAML. |
| CN-2 | Top-level `tccm: tccm.yaml` field doesn't exist; real schema has `contributes.tccm` (default `./tccm.yaml`). | AC-1 now states "no top-level `tccm:` key" and prescribes omitting it (default applies). |
| CN-3 / CV-4 | Story declared `codegenie.vuln_index.{nvd,ghsa,osv}:{Nvd,Ghsa,Osv}Parser` — real symbols are `codegenie.vuln_index.feeds.{nvd,ghsa,osv}:{Nvd,Ghsa,Osv}Feed`. | AC-3 + tccm.yaml example fixed to real symbols. AC-3 also adds a runtime resolution check (`importlib.import_module + getattr`). |
| CN-4 / CV-5 | Integration test referenced `compute_plugin_tree_sha256` / `read_plugins_lock`; real APIs are `compute_plugin_tree_digest` and `LockFile.from_path` (both `Result`-returning). | Rewrote AC-4 + the lockfile test using real names and `.unwrap()` per the `Result` contract. |
| CN-5 / TQ-1 | "Must NOT return UniversalFallbackResolution" was vacuous (nothing registered to compete). | AC-6 + the resolution test now register `make_universal_fallback()` into a fresh `PluginRegistry` before asserting concrete-wins. |
| CN-7 / CV-2 | Test accessed `plugin.manifest.tccm.provides` — `manifest.tccm` is a path string. | AC-7 + tests access `ConcreteResolution.composed_tccm.provides` (via the resolver, per ADR-0004). The manifest-level `tccm` field is correctly identified as a path. |
| CN-10 | Story note: "Python module name will need underscoring per loader's slug-to-module mapping". | Wrong — the loader uses the literal hyphenated slug. Updated the Implementation outline note and validation-notes block to cite `loader.py:289-293` + `test_loader.py:176-188`. |
| DP-1 | Class-body `PluginManifest.from_yaml(...).unwrap()` at class statement defeats `Result` discipline. | Refactored Implementation outline to use a `@dataclass(frozen=True)` with manifest injected via constructor; `_load_manifest()` helper translates `Err` → `RuntimeError` with an explicit failure-routing note. |
| DP-2 | Implementation outline shipped brittle `__file__.replace("api.py", "plugin.yaml")` then "fixed it in refactor" — Rule-3 violation. | Removed entirely. Implementation outline uses `pathlib.Path(__file__).parent / "plugin.yaml"` from the start. |
| DP-9 | Story imports `PluginSubgraph` from `codegenie.plugins.protocols` — it's TYPE_CHECKING-only and not in `__all__`. | Removed from imports; `build_subgraph` return annotation is `Any` (deferred to S6-04). Notes-for-implementer documents this. |
| TQ-2 | No test verifies `precedence: 100` was honored — implementer could silently rely on schema default 50. | Added AC-1 field-level assertion `manifest.precedence == 100` AND AC-12 (peer-at-default-50 must lose to us). |
| TQ-3 | `assert resolution.composed_tccm.must_read` is weakest possible non-emptiness. | Plus the resolver's `ComposedTccm` placeholder doesn't even have a `must_read` field (S3-01's real TCCM does, but the resolver hasn't been upgraded). Split into AC-7 (`provides` observable today via the resolver's placeholder) and AC-13 (deferred `must_read`/`should_read` end-to-end). |
| TQ-4 | Three-entry assertion via membership only — mutation that adds a fourth entry slips by. | AC-3 now asserts `set(vic.keys()) == {"nvd_parser", "ghsa_parser", "osv_parser"}` (exactly). |

### Harden-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| CV-1 | `extends == ()` and `extends_chain` length-1 unasserted. | AC-1 + AC-6 added explicit assertions. |
| CV-3 | `must_read` ContextQuery primitive validity unenforced. | AC-3 pins `primitive == "dep_graph.consumers"` exactly; AC-11 (new) tests typo-rejection via Pydantic ValidationError. |
| CV-6 | Loader discovery mechanism unverified. | AC-5 explicitly runs `load_plugins(...)` against a fresh registry and asserts the registration outcome. |
| CV-7 / TQ-10 | Single-registration idempotency unasserted. | AC-10 added: second `register_plugin` raises `PluginAlreadyRegistered`. |
| CV-9 | Malformed `tccm.yaml` rejection uncovered. | AC-11 added (typed `ValidationError` for unknown primitive). |
| CV-10 | Round-trip between manifest scope vs. PluginScope undefined. | AC-6 now asserts each scope dim as `Concrete` with its literal value (no `specificity()` proxy that hides per-dim mutations). |
| CV-12 / CN-11 | `subgraph/__init__.py` in files-to-touch but no AC and no real precedent. | Removed from Implementation outline + Files-to-touch (YAGNI per Rule 2 — the manifest default `contributes.subgraph: "./subgraph/"` is a path-pointer, not a required filesystem entry). |
| CN-6 | "@register_plugin" prose in ADRs-honored line contradicted ADR-0002's "function call, NOT decorator". | Replaced prose with "the `register_plugin(plugin)` **function call**". |
| CN-8 | `node` vs `javascript` language token undecided. | Picked `javascript` for the manifest's inner `languages:` field (matches Layer A's `LanguageDetection` output AND existing loader-fixture precedent); kept `--node--` in the directory slug for operator readability. Notes-for-implementer documents the split. |
| CN-9 | `precedence: 100` unmotivated. | Kept at 100 with a Validation notes explanation ("audit anchor for 'concrete plugins use higher precedence than the universal fallback's 0'"). Adding AC-12 (precedence is honored, not defaulted) gives the value observable meaning. |
| DP-3 | Plugin-instance shape diverged from established `@dataclass(frozen=True)` fixture. | Implementation outline §4 now mirrors `universal_fallback_fixture._UniversalFallbackPlugin`. |
| DP-5 | Empty-dict returns must be typed. | Implementation outline uses `_adapters: dict[PrimitiveName, Adapter] = field(default_factory=dict)`. |
| DP-6 | `dep_graph.consumers(...)` primitive choice unverified. | AC-3 pins `primitive == "dep_graph.consumers"` exactly (membership in `_KNOWN_PRIMITIVES` is enforced by Pydantic). |
| DP-7 | `PLUGINS.lock` row value type ambiguous (`str` vs `BlobDigest`). | AC-4 + lockfile test now lift through `BlobDigest` via the existing `LockFile.from_path` API. |
| TQ-5 | End-to-end "composed_tccm actually flows from tccm.yaml" not asserted. | AC-7 reads the resolver's composed-TCCM after registration and asserts the `provides` key-set matches the YAML. |
| TQ-6 | `extends == ()` un-pinned. | Pinned in AC-1 and AC-6. |
| TQ-7 | Lockfile fixed-point identity-test catches nothing. | AC-5 + the loader integration test cover symlink/schema/integrity in one positive `load_plugins` call. |
| TQ-8 | Hypothesis property opportunity (tree-digest determinism). | Added separate property test file (mirrors `tests/unit/plugins/test_loader_digest_property.py`'s precedent). |

### Nit-severity (mostly addressed; one deferred)

| ID | Finding | Resolution |
|---|---|---|
| CN-11 | `subgraph/__init__.py` ambiguity. | Removed per CV-12 above. |
| CN-12 | `contributes.tccm` listed explicitly is harmless but redundant. | Implementation outline omits it; default applies. |
| DP-4 | Empty `subgraph/__init__.py` directory + unclear `build_subgraph` default. | `subgraph/` removed (Rule 2); `build_subgraph` documented as `NotImplementedError` until S6-04 ships the real type and import. |
| DP-8 | `register_plugin` import-time unconditional call. | Notes-for-implementer documents this explicitly. |
| DP-10 | Rule-of-three for `PluginScaffold` helper. | Notes-for-implementer documents the threshold (S7-04 audit) and the in-file documentation pattern. |
| DP-11 | CODEOWNERS verification underspecified. | AC-9 gives the exact `grep -F` command. |
| CV-13 | "Exit code 4 on integrity mismatch" not retested. | Explicitly deferred to S2-03's existing coverage (no AC here — S2-03 already pins this; re-testing would duplicate). |
| TQ-9 | `specificity()` assertion is a count, mutates can hide. | AC-6 now asserts each scope dim as `Concrete` with its literal value, not the count. |

## Conflicts surfaced

- **Resolver's TCCM placeholder vs. real `TCCM` model.** The resolver's `ComposedTccm` (`src/codegenie/plugins/resolver.py:120-134`) is a Step-2 placeholder with only `provides`/`requires`. The real `TCCM` (with `must_read`/`should_read`/`may_read`) lives in `codegenie.plugins.tccm`. The resolver loads each plugin's TCCM contribution via `getattr(plugin, "_composed_tccm", None)`. This forces S7-01's plugin to expose `_composed_tccm` directly (a placeholder workaround) until a follow-up story upgrades the resolver. Resolution: surfaced as **AC-13 (DEFERRED)** in the hardened story; the dependency is called out explicitly so the next executor doesn't try to satisfy AC-13 prematurely.
- **`PluginScope` vs. `ManifestScope` confusion.** The story mixed the sum-type algebra (`PluginScope` with `Concrete`/`Wildcard`) and the YAML submodel (`ManifestScope` with raw `str | list[str]`). Resolution: every AC now names which type it asserts against, and the language token (`javascript`) is pinned to match Layer A.
- **`@register_plugin` decorator vs. function call.** Prose in ADRs-honored line contradicted the rest of the story (which correctly used the function-call form). Resolution: prose updated to remove the `@`.

## Architectural opportunities surfaced (for the implementer, not as ACs)

- **Rule-of-three trigger for a `PluginScaffold` helper.** The current story is the 1st concrete production plugin. S7-04 (synthetic third) hits 3. If the copy-paste overlap with `api.py` exceeds ~60% at that point, lift a `make_plugin(manifest_path) -> Plugin` factory then. **Not now** — per Rule 2 (Simplicity First) and the established pattern in `src/codegenie/plugins/registry.py:39-48` where the kernel registry's rule-of-three extract was explicitly deferred.
- **Functional core / imperative shell.** The plugin's `_load_manifest` is the only impure code (filesystem read). Everything else is pure data (`PluginManifest`, `@dataclass(frozen=True)` plugin instance). This split is the established discipline; preserve it.
- **Tagged union discipline.** The story's `PluginResolution = ConcreteResolution | UniversalFallbackResolution` is the canonical sum-type. Tests use `isinstance` checks rather than truthy/falsey heuristics — preserve.

## Files changed

- `docs/phases/03-vuln-deterministic-recipe/stories/S7-01-vuln-node-npm-plugin-scaffold.md` — substantial edits (header status updated; new Validation notes block; ACs rewritten; Implementation outline rewritten; TDD plan rewritten with real APIs; Files-to-touch updated; Notes-for-implementer rewritten).
- `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S7-01-vuln-node-npm-plugin-scaffold.md` — this report.

## Verdict

**HARDENED.** Ready for the executor pipeline. Note the AC-13 deferral — the executor should NOT attempt to satisfy AC-13 until a follow-up story upgrades the resolver to use the real `TCCM`.
