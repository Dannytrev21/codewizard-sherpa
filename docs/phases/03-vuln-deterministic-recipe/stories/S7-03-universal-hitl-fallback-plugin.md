# Story S7-03 — `plugins/universal--*--*/` — universal HITL fallback plugin (NFKC-sanitized handoff)

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** HARDENED (validated 2026-05-19 — see [`_validation/S7-03-universal-hitl-fallback-plugin.md`](_validation/S7-03-universal-hitl-fallback-plugin.md))
**Effort:** M (was M; the build_subgraph-vs-orchestrator-node reconciliation is reframing, not added scope)
**Depends on:** S6-04 (the orchestrator's `IngestCveNode` short-circuits with `RequiresHumanReview` on `UniversalFallbackResolution`, and the orchestrator exits 7 — **this story amends `IngestCveNode` to write the handoff; see Validation notes §1**), S6-05 (`codegenie remediate` CLI subcommand + `--plugins-root` / `CODEGENIE_PLUGINS_ROOT` — every integration test in the TDD plan runs `codegenie remediate`), S2-04 (the resolver returns `UniversalFallbackResolution` when no concrete plugin matches **iff the universal plugin is registered**), S6-01 (the `RequiresHumanReview` `WorkflowInternalEvent` variant + `EventLog.emit_internal`), S6-03 (`SubgraphNode` / `SubgraphState` — note `SubgraphState` carries **no** `jail` / `event_log` field; both are constructor-injected into nodes per S6-04)
**ADRs honored:** [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (**the load-bearing ADR for this story** — the universal fallback IS a registered plugin under `plugins/universal--*--*/`, NOT a code branch in the resolver; specificity-0 `(*, *, *)` scope guarantees lowest sort priority; loader exits 4 on a *concrete* plugin's import failure BEFORE the resolver runs, so the universal is NEVER silently substituted), [ADR-0002](../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md) (`register_plugin(plugin)` is a **function call** — NOT a decorator — against `default_registry` at module-import time; same machinery as the npm plugin), [ADR-0011](../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (the handoff markdown is written via `SandboxedPath` with `O_NOFOLLOW`; `PLUGINS.lock` row regen for this plugin)

## Validation notes (2026-05-19)

Hardened by `phase-story-validator` (automated scheduled task). Full audit: [`_validation/S7-03-universal-hitl-fallback-plugin.md`](_validation/S7-03-universal-hitl-fallback-plugin.md). Verdict **HARDENED** — the *goal* (universal fallback is a registered plugin; sanitized handoff written; workflow exits 7; never silently substituted) is sound and traces to ADR-0003 + arch G7. The defects were (a) one structural wiring contradiction with the already-hardened S6-04, and (b) pervasive API drift against the real as-built code surfaces. Block-tier closures:

1. **`build_subgraph` is NOT on the `codegenie remediate` hot path (B1/B2).** S6-04 §Notes "D-P1" pins: *"Plugin.build_subgraph() is intentionally NOT called in Phase 3 — the 5 nodes ARE orchestrator-owned scaffolding."* S6-04's `IngestCveNode`, on a `UniversalFallbackResolution`, returns `ShortCircuit(RequiresHumanReview(reason="no_concrete_match"))` **directly**. So this story's one-node `build_subgraph` subgraph is exercised **only** by the contract bake test `tests/integration/test_three_plugin_contract.py` (arch line 1045; High-level-impl Step 7 line 205) — never by `codegenie remediate`. **Reconciliation:** this story (a) ships the universal plugin so the *resolver* returns `UniversalFallbackResolution`; (b) ships `build_subgraph` returning a one-node subgraph **for the bake test only**; (c) ships `write_handoff(...)` + `sanitize_for_handoff(...)` as importable functions; and (d) **amends S6-04's `IngestCveNode`** to call `write_handoff(...)` and set `handoff_path` on the `RequiresHumanReview` outcome so the real CLI path writes the file and exits 7. S6-04 is hardened-but-not-yet-built — the amendment is an explicit, declared edit, not a silent override.
2. **`SubgraphState` has no `jail` / `event_log` (B4).** S6-03 AC-9 pins `SubgraphState` fields exactly (`workflow_id`, `cve`, `resolution`, `bundle`, `recipe_outcome`, `transform`, `trust_outcome`, `branch`). The handoff writer must receive the jail (`SandboxedPath` jail root) and `EventLog` as **explicit parameters / constructor-injected dependencies** — never read off `state` (S6-04's node pattern: every node takes `event_log` via `__init__`).
3. **`import codegenie.plugins.subgraph` is fenced out of plugin folders (B3).** High-level-impl Step 7 line 270: *"no `import codegenie.plugins.subgraph` from plugin folders."* `SubgraphState` lives only in that module. The bake-test one-node subgraph node therefore guards the `SubgraphState`/`NodeTransition` imports under `if TYPE_CHECKING:` (or annotates `Any`); `ShortCircuit` is imported from `codegenie.transforms.outcomes` (allowed) when a value is needed.
4. **API drift fixed (B5–B9, H1, H4).** `UniversalFallbackResolution.reason` is `Literal["no_concrete_match"]` — a plain string, not an object with `.kind`. `manifest.scope` is a `ManifestScope` (raw `str | list[str]` dims) with **no** `specificity()` — lift via `lift_manifest_scope` first. `RemediationOutcome` is a `TypeAlias`; `RequiresHumanReview` is constructed directly (no `RemediationOutcome.` prefix). There is no `NoConcreteMatch` symbol — `reason` is the string `"no_concrete_match"` (`HumanReviewReason` Literal). `RequiresHumanReview.handoff_path` is `str | None` — pass `str(sandboxed_path)`. The import-failure rejection variant is `PluginImportError` (`kind="plugin_import_error"`); `PluginRejected` is the union alias; exit-4 mapping is `exit_code_for_rejection`. `PluginSubgraph` is `TYPE_CHECKING`-only in `protocols.py` and not in `__all__` — `build_subgraph`'s return is annotated `Any`.
5. **Two `RequiresHumanReview` types, two `PluginRegistryCorrupted` types (B9, H2).** `RequiresHumanReview` exists both as a `RemediationOutcome` variant (`codegenie.transforms.outcomes`) **and** as a `WorkflowInternalEvent` variant (`codegenie.plugins.events`, S6-01). `PluginRegistryCorrupted` exists both as a `CodegenieError` exception (`codegenie.plugins.errors`) **and** as a `WorkflowSpanningEvent` variant (`codegenie.plugins.events`, S6-01). Every reference in this story names which one it means.

## Context

Production ADR-0031 (§"No-match fallback") commits: *"no specific plugin matches is never a silent failure."* Phase 3's ADR-0003 implements that commitment by making the universal fallback **a normal registered plugin loaded by the same machinery as every other plugin**, with scope `(*, *, *)` (three `Wildcard` dims, specificity 0). The resolver sorts by `(specificity desc, precedence desc, name asc)` so the universal naturally lands LAST; when the head of the sorted list is the universal, the resolver returns the **typed variant** `UniversalFallbackResolution(reason="no_concrete_match")` — distinguishable at compile time from `ConcreteResolution`. There is no `if plugin.is_fallback:` branch anywhere in the resolver; the discriminator lives in the return type.

This story lands the plugin directory + manifest + the sanitizer/writer helpers such that:
1. The registered universal plugin makes the resolver return `UniversalFallbackResolution` when no concrete plugin matches the workflow's scope (per ADR-0003).
2. A **sanitized markdown handoff** is written to `<repo>/.codegenie/handoff/<workflow_id>.md` — sanitization is **NFKC normalization + ANSI escape strip + bidi-control strip + zero-width strip** (the baseline established in `phase-arch-design.md §"Open questions deferred to implementation"`).
3. A `RequiresHumanReview` workflow-internal event is emitted.
4. A `RequiresHumanReview` `RemediationOutcome` (`reason="no_concrete_match"`, `handoff_path=<str>`) reaches the orchestrator.
5. The CLI exits 7 (per architecture §Decision points — "No plugin matches → universal fallback fires → `RequiresHumanReview` → exit 7. Never 'no match' exit").

> **Wiring correction (see Validation notes §1).** The arch's Scenario B draws the universal plugin's *subgraph* doing steps 2–4. The as-hardened S6-04 instead handles the universal-fallback short-circuit inside the orchestrator-owned `IngestCveNode` (S6-04 §Notes "D-P1" — `Plugin.build_subgraph()` is not called by the Phase-3 orchestrator). This story therefore ships steps 2–3 as importable helpers (`sanitize_for_handoff` / `write_handoff`), amends `IngestCveNode` to call them, and keeps a one-node `build_subgraph` only for the `test_three_plugin_contract.py` bake test.

**The most subtle invariant this story must protect (ADR-0003 + Edge case E10):** if a *concrete* plugin matches the scope but fails to load (e.g., its `import_module` raises), the loader exits 4 with the `PluginImportError` variant of `PluginRejected` **before resolution even runs** — the universal fallback is NOT silently substituted. Edge case E10 is the contract; the negative test `tests/integration/test_universal_fallback_never_silent.py` (called out in `High-level-impl.md §Step 7 Done criteria` bullet 4) is the gate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenarios B` — the universal-fallback sequence diagram (CLI → orchestrator → resolver returns `UniversalFallbackResolution` → universal plugin's subgraph writes sanitized markdown → emits `RequiresHumanReview` → returns `RemediationOutcome.RequiresHumanReview` → exit 7).
  - `../phase-arch-design.md §Edge cases E2` (Yarn Berry → universal) and **`E10` (concrete plugin import-error short-circuits BEFORE resolver runs)**.
  - `../phase-arch-design.md §Component design C2` (`resolve()` algorithm: "head plugin's id is `universal--*--*`, return `UniversalFallbackResolution`").
  - `../phase-arch-design.md §Decision points` (exit 7 mapping).
  - `../phase-arch-design.md §"Open questions deferred to implementation"` — "Sanitization of HITL `.codegenie/handoff/*.md`. Synthesis adopts security's NFKC + ANSI/bidi/zero-width strip; implementation may need to add more once we see real HITL content."
- **Phase ADRs:**
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — the load-bearing ADR for this story. **Read all 67 lines.** Especially §Decision (the algorithm), §Tradeoffs (loader startup check that `default_registry.get(PluginId("universal--*--*"))` must succeed), §Consequences (every consumer must `match` over `PluginResolution`).
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — handoff markdown is written via `SandboxedPath` with `O_NOFOLLOW`; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — `§No-match fallback`; "loaded by the same mechanism."
  - `../../../production/adrs/0009-humans-always-merge.md` — the universal plugin's existence is the explicit type-level enforcement of "no autonomous merge ever."
- **Source for the resolver invariant the negative test rests on:**
  - `src/codegenie/plugins/loader.py` (from S2-03) — `importlib.import_module(...)` per plugin tree; an `ImportError` here is translated to the `PluginImportError` variant of `PluginRejected` (`Err`-returned, exit 4 via `exit_code_for_rejection`) before `default_registry.resolve(...)` is ever called.
- **Sanitization precedent (if any):** search the repo for existing NFKC normalization helpers — `unicodedata.normalize("NFKC", s)` is stdlib. ANSI/bidi/zero-width strip is regex-based. If no helper exists, this story creates `src/codegenie/plugins/handoff_sanitize.py`.

## Goal

Land `plugins/universal--*--*/{plugin.yaml,tccm.yaml,api.py,subgraph/...}` plus a sanitizer helper and handoff writer at `src/codegenie/plugins/handoff_sanitize.py` and `src/codegenie/plugins/handoff_writer.py`, such that:
1. The plugin loads, registers via the `register_plugin(plugin)` **function call** (ADR-0002 — not a decorator), and is resolvable as `UniversalFallbackResolution` when no concrete plugin matches.
2. `sanitize_for_handoff(s)` (pure, stdlib-only) and `write_handoff(...)` (writes the sanitized markdown to `<repo>/.codegenie/handoff/<workflow_id>.md` via `SandboxedPath` + `O_NOFOLLOW`) are importable functions — **not** buried inside a plugin subgraph.
3. S6-04's `IngestCveNode` is amended to call `write_handoff(...)` and set `handoff_path` on the `RequiresHumanReview` outcome it already returns on `UniversalFallbackResolution`, so the real `codegenie remediate` path writes the file and the orchestrator exits 7. (S6-04's `IngestCveNode` is the canonical HITL short-circuit in Phase 3 — `Plugin.build_subgraph()` is NOT invoked by the orchestrator; see Validation notes §1.)
4. `build_subgraph(registry)` returns a one-node `PluginSubgraph` whose single node also writes the sanitized handoff — this satisfies the `tests/integration/test_three_plugin_contract.py` bake test that exercises every `Plugin` contract surface, but is **not** on the `codegenie remediate` hot path.
5. **Crucially:** the negative test proves that when a *concrete* plugin's import fails, the loader exits 4 (`PluginImportError`) **before** resolution and the universal is NOT silently substituted.

## Acceptance criteria

### Plugin directory + registration

- [ ] **AC-1** `plugins/universal--*--*/plugin.yaml` is a valid `PluginManifest` (the nested `ManifestScope` shape S7-01 pinned — `scope:` is a submodel with `task_class | languages | build_systems`, **not** a scalar slug): `name: universal--*--*`, `version: 0.1.0`, `scope: {task_class: "*", languages: "*", build_systems: "*"}`, `precedence: 0` (lowest — concrete plugins use higher precedence; ties between wildcard plugins broken by precedence then name), `extends: []`. No top-level `tccm:` key (the manifest default `contributes.tccm: "./tccm.yaml"` applies — same as S7-01).
- [ ] **AC-2** `plugins/universal--*--*/tccm.yaml` is a minimal valid TCCM: empty `must_read`, `should_read`, `may_read`, `provides`, `requires`. The universal does no context gathering; it escalates.
- [ ] **AC-3** `plugins/universal--*--*/api.py` declares the plugin and calls `register_plugin(plugin)` (the **function call** — ADR-0002; not `@register_plugin`) at module-import time. The plugin instance is a `@dataclass(frozen=True)` mirroring `universal_fallback_fixture._UniversalFallbackPlugin` (the established shape — S7-01 §Implementation outline). `adapters()` returns `{}` (typed `dict[PrimitiveName, Adapter]`); `transforms()` returns `{}`.
- [ ] **AC-4** Running `load_plugins(plugin_root, ...)` against a fresh `PluginRegistry` registers `PluginId("universal--*--*")`; `registry.get(PluginId("universal--*--*"))` succeeds. The loader's `importlib.import_module("plugins.universal--*--*.api")` resolves the literal-`*` directory name (filesystem lookup — the same mechanism that handles the hyphenated `vulnerability-remediation--node--npm` slug per S7-01 CN-10; confirm against S2-03's slug→module mapping, do **not** invent a new convention).
- [ ] **AC-5** `plugins/PLUGINS.lock` contains a row for `universal--*--*` whose value lifts through `BlobDigest` via the existing `LockFile.from_path` API (S7-01 DP-7 precedent).

### Resolution (the resolver, not a code branch)

- [ ] **AC-6** With the universal plugin registered into a `PluginRegistry`, `registry.resolve(PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap())` returns a `UniversalFallbackResolution` instance (`isinstance` check, not truthiness). `resolution.reason == "no_concrete_match"` (a plain string — `UniversalFallbackResolution.reason` is `Literal["no_concrete_match"]`, **not** an object with `.kind`). `resolution.candidates_considered` is the alphabetised tuple of registered concrete `PluginId`s (excludes `universal--*--*` itself).
- [ ] **AC-7** The universal manifest's scope, lifted via `lift_manifest_scope(plugin.manifest.scope)` (from `codegenie.plugins.resolver`), yields exactly one `PluginScope` whose `specificity() == 0` (three `Wildcard` dims). **Do not** call `plugin.manifest.scope.specificity()` — `manifest.scope` is a `ManifestScope` (raw `str | list[str]` dims) and has no `specificity()`; `specificity()` is a `PluginScope` method (S7-01 CN-7 precedent).
- [ ] **AC-8** With the universal plugin AND a concrete plugin (`vulnerability-remediation--node--npm`, or a fixture) registered, `registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap())` returns a `ConcreteResolution` — the universal (specificity 0) loses to the concrete (specificity 3). Proves the universal never shadows a real match.

### Sanitizer (pure, stdlib-only)

- [ ] **AC-9** `src/codegenie/plugins/handoff_sanitize.py` exposes `sanitize_for_handoff(s: str) -> str` — pure, stdlib-only, no I/O, no module-level mutable state; all regexes compiled at module scope. It:
  1. Applies `unicodedata.normalize("NFKC", s)`.
  2. Strips ANSI escape sequences: CSI (`\x1b[ … final-byte`), OSC (`\x1b] … \x07` or `\x1b] … \x1b\\`), and any remaining bare `\x1b` introducer.
  3. Strips Unicode bidi-control characters — the four overrides `U+202A`–`U+202E` and the two isolates `U+2066`–`U+2069`.
  4. Strips zero-width characters `U+200B`, `U+200C`, `U+200D`, `U+FEFF`.
- [ ] **AC-10** `sanitize_for_handoff` is **idempotent**: `sanitize_for_handoff(sanitize_for_handoff(s)) == sanitize_for_handoff(s)` for all inputs — covered by a Hypothesis property test (`st.text()`).
- [ ] **AC-11** Per-category unit tests with adversarial fixtures, each constructed so a CSI-only (or otherwise partial) implementation **fails**: an ANSI-injecting CVE description that includes **both** a CSI sequence **and** an OSC sequence; a bidi-override-injecting package name; a zero-width-padded version string. All adversarial control characters in test sources are written as explicit `\u…` / `\x…` escapes (never literal bidi/zero-width bytes in the `.py` file).

### Handoff writer + the real `codegenie remediate` path

- [ ] **AC-12** `src/codegenie/plugins/handoff_writer.py` exposes `write_handoff(*, jail: Path, workflow_id: WorkflowId, markdown: str, event_log: EventLog) -> str` (or equivalent explicit-parameter signature — **no** dependency read off `SubgraphState`). It: sanitizes `markdown` via `sanitize_for_handoff`; resolves `SandboxedPath.create(jail, f"handoff/{workflow_id}.md")` and `.unwrap()`s the `Result`; writes via `.open("w")` (always `O_NOFOLLOW` per ADR-0011); on `OSError(errno=ELOOP)` from a symlink TOCTOU emits the `FilesystemRaceDetected` `WorkflowInternalEvent` (S6-01) and re-raises a typed error; returns `str(sandboxed_path)`.
- [ ] **AC-13** S6-04's `IngestCveNode` is amended: on `UniversalFallbackResolution` it calls `write_handoff(...)` (rendering a markdown summary of the CVE, the scope that fell through, and `resolution.candidates_considered`), then returns `ShortCircuit(RequiresHumanReview(reason="no_concrete_match", handoff_path=<written path>))`. `RequiresHumanReview` here is the `RemediationOutcome` variant from `codegenie.transforms.outcomes` — constructed directly (no `RemediationOutcome.` prefix; S6-04 §Notes line 613). `handoff_path` is a `str` (`RequiresHumanReview.handoff_path: str | None`).
- [ ] **AC-14** Running `codegenie remediate ./tests/fixtures/repos/cargo-fixture --cve <valid-CVE-present-in-the-test-index>` exits **7**; `<repo>/.codegenie/handoff/<workflow_id>.md` exists with non-empty content; the content contains the CVE id and contains no `\x1b` byte (sanitization proven end-to-end). The CVE id is syntactically valid (`CveId`-parseable, e.g. `CVE-2024-00000`) and is seeded into the test `VulnIndex` so `IngestCveNode`'s CVE lookup succeeds and the workflow reaches plugin resolution (a CVE-index miss would `Escalate("vuln_index_corrupted")`, not route to the universal fallback).
- [ ] **AC-15** A `WorkflowInternalEvent` recording the human-review escalation is emitted on the internal stream during the universal-fallback path (the `RequiresHumanReview` variant from S6-01's taxonomy — distinct from the `RemediationOutcome` variant of the same name). Its payload fields are whatever S6-01 ships; this story does not invent fields on it.

### `build_subgraph` bake-test surface

- [ ] **AC-16** `plugins/universal--*--*/api.py`'s `build_subgraph(registry)` returns a one-node `PluginSubgraph`-shaped object whose single node, when run, sanitizes + writes a handoff and yields a `ShortCircuit` carrying a `RequiresHumanReview` `RemediationOutcome`. Return type is annotated `Any` (`PluginSubgraph` is `TYPE_CHECKING`-only in `protocols.py`, not in `__all__` — S7-01 DP-9). The node module does **not** `import codegenie.plugins.subgraph` (High-level-impl Step 7 line 270 fence); `SubgraphState`/`NodeTransition` annotations, if present, are `TYPE_CHECKING`-guarded.
- [ ] **AC-17** `tests/integration/test_three_plugin_contract.py` (or this story's slice of it) calls `universal_plugin.build_subgraph(registry)` and asserts the returned subgraph runs its node to a `ShortCircuit(RequiresHumanReview(...))`. This is the **only** invocation of the universal's `build_subgraph` — the orchestrator does not call it (S6-04 D-P1).

### Never-silent invariant — the gate

- [ ] **AC-18 — Negative test `tests/integration/test_universal_fallback_never_silent.py`.** A fixture concrete plugin under `tests/fixtures/plugins/broken_import_setup/broken-import--node--npm/` has an `api.py` that raises `ImportError("synthetic broken plugin")` at module-import time, plus a `PLUGINS.lock` matching that tree. Running the loader (or `codegenie remediate ./tests/fixtures/repos/express-cve-2024-21501 --cve CVE-2024-21501 --plugins-root <fixture>`) exits **4** — the loader translates the `ImportError` to the `PluginImportError` variant of `PluginRejected` (`kind="plugin_import_error"`; `exit_code_for_rejection(...) == 4`) **before** `resolve()` runs. NOT exit 7. No `.codegenie/handoff/*.md` is written (the universal path never ran). Edge case E10 is the contract.
- [ ] **AC-19** Universal-plugin-missing invariant: with the universal plugin **not** registered and no concrete plugin matching the scope, `registry.resolve(...)` raises `PluginRegistryCorrupted` (the `codegenie.plugins.errors` exception — `reason="missing_universal"`; already enforced by the as-built resolver, `resolver.py:524`). A unit test pins this. (The story does **not** add a separate loader-startup check — the resolver already makes "universal absent" a loud failure; re-checking at loader time would duplicate. See Validation notes / Notes for the implementer.)

### Bar ACs

- [ ] **AC-20** No LLM SDK import added under `plugins/universal--*--*/`, in `handoff_sanitize.py`, or in `handoff_writer.py` (verified via `make fence` + `make lint-imports`).
- [ ] **AC-21** The red tests from §TDD plan exist, were committed in a failing state, and are now green.
- [ ] **AC-22** `ruff format --check`, `ruff check`, `mypy --strict` clean on all touched files; full `pytest` suite green (no regressions, including S6-04's `IngestCveNode` tests after the AC-13 amendment).

## Implementation outline

1. **`src/codegenie/plugins/handoff_sanitize.py`** — `sanitize_for_handoff(s: str) -> str`. Pure, stdlib-only, module-level compiled regexes. NFKC normalize → strip ANSI (CSI + OSC + bare `\x1b`) → strip bidi controls + zero-width via a fixed `frozenset` of codepoints (`str.translate`). ~15 lines. Test independently (AC-9/10/11).
2. **`src/codegenie/plugins/handoff_writer.py`** — `write_handoff(*, jail, workflow_id, markdown, event_log) -> str`. Sanitize → `SandboxedPath.create(jail, f"handoff/{workflow_id}.md").unwrap()` → `.open("w")` write → return `str(path)`. Wrap the `open`/write in `try/except OSError` and re-raise after `event_log.emit_internal(FilesystemRaceDetected(...))` on `errno == ELOOP` (ADR-0011 — symlink TOCTOU). All collaborators are explicit parameters; **nothing** is read off `SubgraphState`.
3. **Create the plugin directory tree** `plugins/universal--*--*/`. The directory name uses literal hyphens and stars; shell globbing in scripts must quote it. The loader maps the literal slug to the import path (`importlib.import_module("plugins.universal--*--*.api")` — filesystem lookup, same mechanism as the hyphenated npm slug per S7-01 CN-10). **Don't** invent a new module-name convention; confirm against S2-03's loader.
4. **`plugin.yaml`** — minimal valid manifest. Nested `scope:` submodel with all three dims `"*"` (S7-01 pinned `ManifestScope` is a submodel, not a slug). `precedence: 0`. `extends: []`. No top-level `tccm:` key (manifest default `contributes.tccm` applies).
5. **`tccm.yaml`** — minimal: empty `must_read`, `should_read`, `may_read`, `provides`, `requires`.
6. **`api.py`** — `@dataclass(frozen=True)` plugin instance mirroring `tests/fixtures/plugins/universal_fallback_fixture._UniversalFallbackPlugin`; `_load_manifest()` helper translates an `Err` from `PluginManifest.from_yaml` into a `RuntimeError`; module-level `register_plugin(plugin)` **function call**. `adapters()` / `transforms()` return typed empty dicts. `build_subgraph(registry) -> Any` returns the one-node bake-test subgraph (step 7).
7. **`subgraph/handoff_node.py`** — the one bake-test node. It does **not** import `codegenie.plugins.subgraph` (Step-7 fence). It is constructor-injected with whatever it needs (`jail`, `workflow_id`, `event_log`) — these come from `build_subgraph`'s caller wiring in the bake test, not from `SubgraphState`. Sketch:
   ```python
   from codegenie.transforms.outcomes import RequiresHumanReview, ShortCircuit
   from codegenie.plugins.handoff_writer import write_handoff

   class UniversalFallbackNode:
       def __init__(self, *, jail: Path, workflow_id: WorkflowId,
                    event_log: EventLog, candidates: tuple[PluginId, ...]) -> None:
           self._jail = jail
           self._workflow_id = workflow_id
           self._event_log = event_log
           self._candidates = candidates

       async def run(self, state: Any) -> Any:   # SubgraphState/NodeTransition not imported (Step-7 fence)
           md = _render_handoff_markdown(self._workflow_id, self._candidates)
           handoff_path = write_handoff(
               jail=self._jail, workflow_id=self._workflow_id,
               markdown=md, event_log=self._event_log,
           )
           return ShortCircuit(outcome=RequiresHumanReview(
               reason="no_concrete_match", handoff_path=handoff_path,
           ))
   ```
8. **Amend S6-04's `IngestCveNode`** (`src/codegenie/transforms/nodes/ingest_cve.py`). S6-04 already returns `ShortCircuit(RequiresHumanReview(reason="no_concrete_match"))` on `UniversalFallbackResolution`; this story changes that arm to first call `write_handoff(jail=..., workflow_id=state.workflow_id, markdown=_render_handoff_markdown(...), event_log=self._event_log)` and pass the returned `str` as `handoff_path=`. `IngestCveNode` already holds `event_log` (constructor-injected per S6-04 AC-8); the jail root is the repo path the orchestrator was invoked against. Update S6-04's `test_run_returns_requires_human_review_when_resolution_is_universal` so its `RequiresHumanReview` expectation carries a non-`None` `handoff_path`.
9. **`PLUGINS.lock` regen** — add the `universal--*--*` row (value via `LockFile.from_path` / `compute_plugin_tree_digest`).
10. **Negative-test fixture.** Create `tests/fixtures/plugins/broken_import_setup/broken-import--node--npm/{plugin.yaml,api.py}` where `api.py` body raises `ImportError("synthetic broken plugin")` at module-import time, plus a `PLUGINS.lock` matching that tree. The loader's `importlib.import_module(...)` raises; the loader translates to the `PluginImportError` variant of `PluginRejected`; the CLI maps it via `exit_code_for_rejection` to exit 4.

## TDD plan — red / green / refactor

### Red

**Unit tests — registration, resolution, sanitizer.** Test file `tests/unit/plugins/test_universal_fallback_plugin.py`. Construct a fresh `PluginRegistry()` and `load_plugins(...)` into it (do **not** assert against the process-wide `default_registry` — fixture isolation per ADR-0002):

```python
# tests/unit/plugins/test_universal_fallback_plugin.py
from codegenie.plugins.resolver import (
    ConcreteResolution, UniversalFallbackResolution, lift_manifest_scope,
)
from codegenie.plugins.scope import PluginScope
from codegenie.types.identifiers import PluginId


def test_universal_plugin_registered_with_wildcard_scope(loaded_registry):
    plugin = loaded_registry.get(PluginId("universal--*--*"))
    lifted = lift_manifest_scope(plugin.manifest.scope)   # ManifestScope -> tuple[PluginScope]
    assert len(lifted) == 1
    assert lifted[0].specificity() == 0                   # three Wildcard dims (AC-7)


def test_resolver_returns_universal_fallback_for_unmatched_scope(loaded_registry):
    scope = PluginScope.parse("vulnerability-remediation--rust--cargo").unwrap()
    resolution = loaded_registry.resolve(scope)
    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.reason == "no_concrete_match"        # plain str — AC-6


def test_universal_never_shadows_a_concrete_match(loaded_registry_with_npm):
    scope = PluginScope.parse("vulnerability-remediation--node--npm").unwrap()
    resolution = loaded_registry_with_npm.resolve(scope)
    assert isinstance(resolution, ConcreteResolution)      # AC-8
```

**Sanitizer tests** — `tests/unit/plugins/test_handoff_sanitize.py`. All adversarial control characters are explicit escapes; the ANSI test carries **both** CSI and OSC so a CSI-only impl fails:

```python
import unicodedata
import pytest
from hypothesis import given, strategies as st
from codegenie.plugins.handoff_sanitize import sanitize_for_handoff

def test_sanitize_strips_ansi_csi_and_osc():
    raw = "pkg \x1b[31mred\x1b[0m and \x1b]8;;http://evil\x07link\x1b]8;;\x07 tail"
    out = sanitize_for_handoff(raw)
    assert "\x1b" not in out
    assert "red" in out and "link" in out and "tail" in out

def test_sanitize_strips_bidi_override_characters():
    raw = "package ‮good‬"          # RLO + PDF
    out = sanitize_for_handoff(raw)
    assert "‮" not in out and "‬" not in out

def test_sanitize_strips_zero_width():
    raw = "ver​sion-1.0﻿"
    out = sanitize_for_handoff(raw)
    assert "​" not in out and "﻿" not in out

def test_sanitize_applies_nfkc_normalization():
    raw = "fiﬁnale"                       # U+FB01 = ligature fi
    assert sanitize_for_handoff(raw) == unicodedata.normalize("NFKC", raw)

@given(st.text())
def test_sanitize_is_idempotent(s):            # AC-10
    once = sanitize_for_handoff(s)
    assert sanitize_for_handoff(once) == once
```

**Negative integration test** — `tests/integration/test_universal_fallback_never_silent.py` (AC-18). The handoff-absence assertion targets the *analyzed repo's* `.codegenie/`, never a CWD-relative path:

```python
import subprocess, sys
from pathlib import Path

def test_concrete_plugin_import_error_exits_4_not_7(tmp_path):
    """ADR-0003 + Edge case E10: a concrete plugin's import failure exits 4
    (PluginImportError) BEFORE resolution — universal NEVER substituted."""
    repo = Path("tests/fixtures/repos/express-cve-2024-21501")
    fixture_plugins = Path("tests/fixtures/plugins/broken_import_setup").resolve()
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", str(repo),
         "--cve", "CVE-2024-21501", "--plugins-root", str(fixture_plugins)],
        capture_output=True, text=True,
    )
    assert result.returncode == 4                          # NOT 7
    assert "plugin_import_error" in result.stderr.lower() or "PluginImportError" in result.stderr
    assert not list((repo / ".codegenie" / "handoff").glob("*.md"))
```

**Happy-path integration test** — `tests/integration/test_universal_fallback.py` (AC-14). The CVE is `CveId`-parseable and seeded into the test index:

```python
def test_cargo_repo_routes_to_universal_fallback_and_exits_7():
    repo = Path("tests/fixtures/repos/cargo-fixture")
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", str(repo),
         "--cve", "CVE-2024-00000"],          # syntactically valid; seeded in the test VulnIndex
        capture_output=True, text=True,
    )
    assert result.returncode == 7
    handoffs = list((repo / ".codegenie" / "handoff").glob("*.md"))
    assert len(handoffs) == 1
    content = handoffs[0].read_text()
    assert "CVE-2024-00000" in content
    assert "\x1b" not in content                            # sanitization proven end-to-end
```

Run; confirm `ModuleNotFoundError`/`ImportError` on `codegenie.plugins.handoff_sanitize`, `PluginNotRegistered` on `registry.get(PluginId("universal--*--*"))`, and non-7 exit codes on the integration tests; commit the red.

### Green

Land, in dependency order: the sanitizer → the handoff writer → the plugin tree (`plugin.yaml`, `tccm.yaml`, `api.py`, the bake-test node) → the `PLUGINS.lock` row → the `cargo-fixture/` and `broken_import_setup/` fixtures → the `IngestCveNode` amendment (AC-13).

Smallest shape:
- `sanitize_for_handoff` ~15 lines: NFKC normalize, regex-strip ANSI (CSI + OSC + bare `\x1b`), `str.translate` over a fixed `frozenset` of bidi + zero-width codepoints.
- `write_handoff` ~15 lines: sanitize → `SandboxedPath.create(...).unwrap()` → `.open("w")` write → `try/except OSError` ELOOP guard → return `str(path)`.
- `UniversalFallbackNode` ~15 lines: constructor stores injected deps; `run()` renders markdown, calls `write_handoff`, returns `ShortCircuit(outcome=RequiresHumanReview(...))`.
- `api.py` ~15 lines.
- The `IngestCveNode` amendment is ~3 lines inside the existing `UniversalFallbackResolution` arm.

### Refactor

- Move the markdown template into a Jinja-free f-string helper `_render_handoff_markdown(workflow_id, cve, scope, candidates)` at module scope (shared by `api.py`'s bake-test node and `IngestCveNode`).
- Confirm `mypy --strict` clean. The bake-test node returns a `ShortCircuit` carrying a `RequiresHumanReview` `RemediationOutcome`; `IngestCveNode` returns the same. `NodeTransition = Advance | ShortCircuit | Escalate` (S6-03).
- Document in each new module's docstring that this plugin's existence is the type-level enforcement of production ADR-0009 (humans always merge) at the "no concrete plugin" boundary.
- Add a `WARNING` structlog line where the universal path fires, reporting the scope that fell through and `candidates_considered` — operator visibility into "why did I land in HITL." (Log line, not an AC — logs aren't contracts; story-smell "asserting on logs".)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/handoff_sanitize.py` | New — pure `sanitize_for_handoff(s) -> str` (NFKC + ANSI CSI/OSC + bidi/zero-width strip) |
| `src/codegenie/plugins/handoff_writer.py` | New — `write_handoff(*, jail, workflow_id, markdown, event_log) -> str`; `SandboxedPath` + `O_NOFOLLOW` + ELOOP→`FilesystemRaceDetected` |
| `plugins/universal--*--*/plugin.yaml` | New — `PluginManifest` with nested all-wildcard `scope:` submodel, `precedence: 0`, `extends: []` |
| `plugins/universal--*--*/tccm.yaml` | New — minimal TCCM (all sections empty; universal does not gather context) |
| `plugins/universal--*--*/api.py` | New — `@dataclass(frozen=True)` plugin + `register_plugin(plugin)` function call + `build_subgraph(registry) -> Any` |
| `plugins/universal--*--*/subgraph/__init__.py` | New — re-exports `UniversalFallbackNode` |
| `plugins/universal--*--*/subgraph/handoff_node.py` | New — `UniversalFallbackNode` bake-test node; constructor-injected deps; **no** `import codegenie.plugins.subgraph` |
| `src/codegenie/transforms/nodes/ingest_cve.py` | **Amend (S6-04)** — the `UniversalFallbackResolution` arm calls `write_handoff(...)` and sets `handoff_path` on the `RequiresHumanReview` outcome (AC-13) |
| `plugins/PLUGINS.lock` | Modified — add row for `universal--*--*` |
| `tests/fixtures/repos/cargo-fixture/` | New — minimal Cargo repo fixture for the universal-fallback happy-path integration test |
| `tests/fixtures/plugins/broken_import_setup/broken-import--node--npm/` | New — fixture plugin tree whose `api.py` raises `ImportError` at import time + a `PLUGINS.lock` matching that tree |
| `tests/unit/plugins/test_universal_fallback_plugin.py` | New — registration + resolution (`UniversalFallbackResolution` / `ConcreteResolution`) + `lift_manifest_scope` specificity |
| `tests/unit/plugins/test_handoff_sanitize.py` | New — per-category sanitization tests (CSI+OSC, bidi, zero-width, NFKC) + Hypothesis idempotence |
| `tests/unit/plugins/test_handoff_writer.py` | New — `write_handoff` writes via `SandboxedPath`; ELOOP path emits `FilesystemRaceDetected` |
| `tests/unit/plugins/test_universal_missing_raises.py` | New — AC-19: resolver raises `PluginRegistryCorrupted` (errors exception) when universal absent + no concrete match |
| `tests/integration/test_universal_fallback.py` | New — `codegenie remediate` cargo-fixture → exit 7 + handoff written (AC-14) |
| `tests/integration/test_universal_fallback_never_silent.py` | New — **the negative test** — concrete plugin import failure exits 4 (`PluginImportError`), NOT 7 (AC-18) |
| `tests/integration/test_three_plugin_contract.py` | Amend (or this story's slice) — exercise `universal_plugin.build_subgraph(registry)` (AC-17) |
| `tests/unit/transforms/nodes/test_ingest_cve.py` | Amend (S6-04) — `RequiresHumanReview` expectation now carries a non-`None` `handoff_path` |

## Out of scope

- **S6-04's orchestrator + the other four subgraph nodes.** S6-04 ships `RemediationOrchestrator` and `IngestCveNode`/`MatchRecipeNode`/`ApplyRecipeNode`/`Stage6ValidateNode`/`WriteBranchNode`. This story only **amends** `IngestCveNode`'s `UniversalFallbackResolution` arm (AC-13) — it does not re-author the node or touch the other four.
- **Markdown HTML-embed neutralization** — `phase-arch-design.md §Open questions` explicitly defers: "Synthesis adopts security's NFKC + ANSI/bidi/zero-width strip; implementation may need to add more (e.g., markdown HTML-embed neutralization) once we see real HITL content." This story ships the baseline; future hardening is its own story.
- **Yarn Berry routing test (`tests/integration/test_yarn_berry_routed_to_universal.py`)** — that's S8-04's adversarial coverage. This story ships the universal plugin; the routing-against-Yarn-Berry case is part of the adversarial portfolio.
- **`extends`-chain composition with the universal as a base** — the universal does not appear in any concrete plugin's `extends` chain in Phase 3; concrete plugins compose only with each other (if at all — Phase 3 uses depth-0 chains exclusively per S7-01 + S7-02).
- **Bench / performance** — universal-fallback path is rare; no bench needed in Phase 3. Phase 9 may add `bench_universal_resolution_latency` if relevant.
- **Bench-replayable emission** — S9-04's surface.
- **Sigstore signing** of the universal plugin — Phase 11.

## Notes for the implementer

- **READ ADR-0003 IN FULL, but read S6-04 §Notes "D-P1" too.** ADR-0003 says the universal fallback is a registered plugin whose subgraph escalates — and at the *resolver* layer it is exactly that. But S6-04 (HARDENED) decided that in **Phase 3 the orchestrator does not call `Plugin.build_subgraph()`** — the 5 nodes are orchestrator-owned. The reconciliation this story implements: the universal plugin's `build_subgraph` one-node subgraph exists and is exercised by the `test_three_plugin_contract.py` bake test (so the `Plugin` contract surface is real), but the *operational* HITL handoff on the `codegenie remediate` path is done by S6-04's `IngestCveNode` short-circuit, which this story amends to call `write_handoff(...)`. Both routes share `sanitize_for_handoff` + `write_handoff` — one helper pair, two callers. This is the Rule-7 "two patterns contradict — pick one, document the other" outcome: the as-built S6-04 wins for the hot path; the arch's plugin-subgraph framing survives as the bake-test contract.
- **The negative test is the gate.** Edge case E10: a concrete plugin's import failure exits 4 (`PluginImportError`) BEFORE resolution — universal is NOT substituted. If your green code returns exit 7 instead, the implementation is wrong, not the test.
- **`SubgraphState` carries NO `jail` and NO `event_log`.** S6-03 AC-9 pins its fields exactly. The handoff writer and the bake-test node receive `jail` / `workflow_id` / `event_log` as **explicit parameters or constructor-injected dependencies** — the same pattern every S6-04 node uses (`IngestCveNode(vuln_index, registry, event_log)`, etc.). Do not try to widen `SubgraphState` — S6-03 §Notes forbids it; field additions are reserved for Phase-4/7 *additive optional* fields.
- **Plugin folders may not `import codegenie.plugins.subgraph`** (High-level-impl Step 7 line 270 import-linter fence). `ShortCircuit` / `RequiresHumanReview` / `RemediationOutcome` come from `codegenie.transforms.outcomes` (allowed). `SubgraphState` / `NodeTransition` live only in `codegenie.plugins.subgraph` — the bake-test node guards them under `if TYPE_CHECKING:` or annotates `Any`. `make lint-imports` is the gate.
- **Two `RequiresHumanReview` classes — name them.** The `RemediationOutcome` variant (`codegenie.transforms.outcomes.RequiresHumanReview`: `kind`, `reason: HumanReviewReason`, `handoff_path: str | None`) is what you put inside a `ShortCircuit`. The `WorkflowInternalEvent` variant (`codegenie.plugins.events.RequiresHumanReview`, S6-01) is what you `emit_internal(...)`. They are different classes with different fields. There is **no `NoConcreteMatch` symbol** — `reason` is the string `"no_concrete_match"`.
- **Two `PluginRegistryCorrupted` too.** A `CodegenieError` exception (`codegenie.plugins.errors`) AND a `WorkflowSpanningEvent` variant (`codegenie.plugins.events`, S6-01). AC-19 means the **exception** — the as-built resolver already raises it (`resolver.py:524`, `reason="missing_universal"`). Do NOT add a separate loader-startup check: the resolver already makes "universal absent" a loud failure; a duplicate loader check is redundant scope (Rule 2). The original story's "loader startup check" AC has been dropped for this reason.
- **`manifest.scope` is a `ManifestScope`, not a `PluginScope`.** It has raw `str | list[str]` dims and **no** `specificity()`. Lift it via `lift_manifest_scope(plugin.manifest.scope)` (from `codegenie.plugins.resolver`) to get `tuple[PluginScope, ...]`, then call `.specificity()`. S7-01 hit this exact confusion (CN-7).
- **`handoff_path` is a `str`.** `RequiresHumanReview.handoff_path: str | None`. `write_handoff` returns `str(sandboxed_path)`; never pass a `SandboxedPath` object into the outcome.
- **The handoff path uses `SandboxedPath`, not `pathlib.Path` directly.** Per ADR-0011, `SandboxedPath.open(...)` is always `O_NOFOLLOW`; a symlink swap between `create()` and `open()` raises `OSError(errno=ELOOP)`. `write_handoff` catches it and emits `FilesystemRaceDetected` (the S6-01 `WorkflowInternalEvent`). Symlink TOCTOU on the handoff directory is a real attack vector — don't skip the guard.
- **`sanitize_for_handoff` is stdlib-only and pure.** Regexes compiled at module scope; no state; no I/O. The idempotence property (AC-10) holds because NFKC normalization and each strip pass are individually idempotent — keep it that way.
- **The CVE in the happy-path test must parse AND exist in the index.** `IngestCveNode` looks up the CVE in `VulnIndex` *before* resolving the plugin; a lookup miss `Escalate`s with `vuln_index_corrupted` (exit ≠ 7), not the universal fallback. Use a `CveId`-parseable id (`CVE-YYYY-NNNNN`) seeded into the test index. The universal fallback is about *plugin-scope* mismatch (Rust/Cargo matches no concrete plugin), not a CVE miss.
- **Precedence `0` is fine** — the universal is the only specificity-0 plugin in Phase 3; precedence ties are not possible yet. Phase 7+ may register other wildcard plugins, at which point ADR-0003's name-sort tiebreaker kicks in.
- **No `extends`** for the universal — it is the base of nothing. Keep `extends: []`.
- **The directory name `universal--*--*` has literal `*` characters.** Filesystems allow it; `importlib.import_module("plugins.universal--*--*.api")` resolves it the same way the hyphenated npm slug resolves (S7-01 CN-10 confirmed the loader uses the literal slug). Confirm against S2-03's loader rather than assuming; shell scripts must quote the path.
- **Resist gold-plating.** No retry. No "maybe a concrete plugin matches if I squint." If the resolver returned `UniversalFallbackResolution`, the workflow ends in HITL. The handoff markdown explains *what was tried and why nothing matched*, sized small (≤ 8 KB target; align with `AttemptSummary.prior_failure_summary` cap from S1-04).
