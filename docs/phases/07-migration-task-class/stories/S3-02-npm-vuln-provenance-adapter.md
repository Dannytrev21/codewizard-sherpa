# Story S3-02 — `NpmVulnProvenanceAdapter` body + DI kwargs

**Step:** Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)
**Status:** BLOCKED (2026-05-20; see [`_attempts/S3-02-npm-vuln-provenance-adapter.md`](_attempts/S3-02-npm-vuln-provenance-adapter.md))

> **BLOCKED — do not execute until resolved.** S3-02 has unsatisfiable
> preconditions: (A) the `plugins/vulnerability-remediation--node--npm/`
> Phase 3 plugin directory does not exist — Phase 3 is designed but not
> implemented; (B) `bench/vuln-remediation/` cassettes do not exist; (C–E)
> the landed `attribute(...)` contract, `Provenance` variant fields, and
> `AdapterConfidence` shape diverged from this story's `repo_context` /
> lockfile-walk / payload-confidence design; (F) S3-01's integration test
> queries the same package for both the direct and transitive scenarios
> (contradictory); (G) AC-12 (S3-01 tests GREEN) contradicts this story's own
> Out-of-scope deferral of `api.py` wiring to S3-03. Resolution: implement
> Phase 3 first, then rewrite this story against the landed contract. Full
> diagnostic + ordered resolution path in the attempt log.
**Effort:** M
**Depends on:** S3-01 (the contract test exists in red/xfail state — this story turns its three positive-path scenarios green); S2-01 (`@register_provenance_adapter` decorator + `Layer` / `Ecosystem` enums); S2-02 (`AdapterFactory` Protocol with the closed `{sbom_reader, logger, image_manifest_cache}` DI kwarg vocabulary); S1-03 (seven-variant `Provenance` union with `AppDirect` / `AppTransitive` / `Unknown` constructable); S1-04 (`VulnProvenanceAdapter` Protocol + `ProvenanceError` / `AdapterError` hierarchy); S1-05 (`SyftSbom` reader for cross-verification via the verifier landing in S4-01 — defensive against absence in this story)
**ADRs honored:** [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) (the decorator registers the **class**, not an instance; construction happens at dispatch time via `AdapterFactory`); [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) (the adapter consumes the primitive's `attribute(...) -> Provenance` Protocol; returns one of seven variants); [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (adapter lives under the plugin directory, NOT under `src/codegenie/` — even though it consumes a `src/codegenie/primitives/` Protocol); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — **this story creates `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`, which is Phase 7 byte-edit allowlist row #1 (an entire new file under an existing Phase 3 plugin directory; the directory is not itself a Phase 3 file, but the plugin tree as a whole is Phase 0–6.5 surface — see ADR-0009 row 1 verbatim)**

## Context

S3-01 wrote the integration test red-first; this story turns its three positive-path scenarios green by landing the actual adapter body. The adapter is small in line count but load-bearing: it is the **first concrete implementation** of the `VulnProvenanceAdapter` Protocol, the first thing the registry resolves to a real class, and the first byte-edit territory Phase 7 enters (consuming allowlist row #1 per Phase 7 ADR-0009 enumeration).

The adapter is **promoted from the Phase 3 refuse-mode shape** — the existing Phase 3 plugin already walks `package-lock.json` for the recipe layer's purposes (e.g., `NpmMajorBumpRefuseRecipe` reads the same trees to decide refuse). The S3-02 adapter must NOT depend on Phase 3 private helpers. It must duplicate (read: independently re-derive) the dep-tree reading discipline. The reason: editing Phase 3 plugin code to expose internals would consume a non-existent allowlist row. Per `High-level-impl.md §"Step 3 — Risks specific to this step"`:

> If a Phase 3 internal API doesn't satisfy `NpmVulnProvenanceAdapter`'s read needs, surface as a follow-up cleanup ticket — do NOT refactor Phase 3 code in this step.

The adapter reads `package.json` + `package-lock.json` from the gathered `RepoContext` (already-shipped Phase 1 probes — `NodeManifest`, `NodeBuildSystem`). The lockfile walk classifies the query result:

| Outcome | Condition | Returned variant |
|---|---|---|
| `AppDirect(package_id, version, ...)` | Chain from `package.json` root → target package has length 1 (direct dep) | One of seven `Provenance` variants |
| `AppTransitive(package_id, version, chain=[...])` | Chain length > 1 (the package is reached only via transitive deps) | Carries the full resolution chain for debuggability |
| `Unknown(reason="sbom_layer_attribution_absent")` | The package does not appear in `package-lock.json` at all | Defensive default — better to honestly say "I don't see it" than guess |
| `Unknown(reason="adapter_error", details={...})` | Lockfile parse failure | The only typed-exception path; raised as `AdapterError` → assembly converts |

The adapter does NO I/O at construction. All DI kwargs are stored references. `attribute(...)` is the only impure method, and even it only reads pre-gathered `RepoContext` slices via the injected `sbom_reader` / `image_manifest_cache` — no filesystem access from inside the adapter. This is the Phase 0 "functional core / imperative shell" discipline.

The adapter's `_WARNING_IDS` module-level `Final[frozenset[str]]` is the Phase 0 / Phase 1 convention (CLAUDE.md "Warning + error IDs"). It must contain `"vuln_provenance.adapter_error"` and validate via `raise AssertionError(...)` at import time — **bare `assert` is forbidden by the `forbidden-patterns` pre-commit hook**.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design §7a NpmVulnProvenanceAdapter"` (lines ~742–750) — the canonical spec verbatim.
  - `../phase-arch-design.md §"Component design §1 VulnProvenancePrimitive"` (lines ~520–610) — the `Provenance` union surface the adapter must return.
  - `../phase-arch-design.md §"Scenario A — App-only CVE"` (sequence diagram) — the `attribute(...)` call site.
  - `../phase-arch-design.md §"Decision points"` row for `Unknown` reasons — `sbom_layer_attribution_absent` is the canonical "I don't see this in the SBOM" reason.
  - `../phase-arch-design.md §"Failure behavior"` row in §7a — lockfile parse error → `AdapterError` → assembly converts to `Unknown(reason="adapter_error")`.
- **Phase 7 ADRs:**
  - [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) — `Provenance` union home + variants.
  - [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) — adapter under plugin, not under `src/codegenie/`.
  - [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — registry stores classes; construction via `AdapterFactory` at dispatch time.
  - [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — this story creates an allowlisted file (row #1).
- **High-level impl:** `../High-level-impl.md §"Step 3 — Features delivered"` (lines 96–101) — the bullet-by-bullet spec. **The implementer should read it verbatim**.
- **Phase 3 reference (read-only):**
  - `plugins/vulnerability-remediation--node--npm/recipes/` — existing recipe code that walks `package-lock.json`. **Do not import from this directory**; the adapter must re-derive its own lockfile walk. The reference is for understanding the lockfile shape only.
  - `docs/phases/03-vuln-deterministic-recipe/ADRs/0033-newtype-identifiers.md` (if it exists) — Phase 3's newtype discipline; Phase 7 ADR-0004 extends.
- **Existing primitive surface (consumed):**
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — `VulnProvenanceAdapter`, `AdapterFactory`.
  - `src/codegenie/primitives/vuln_provenance/types.py` — `AppDirect`, `AppTransitive`, `Unknown`.
  - `src/codegenie/primitives/vuln_provenance/registry.py` — `register_provenance_adapter`, `Layer`, `Ecosystem`.
  - `src/codegenie/primitives/vuln_provenance/errors.py` — `AdapterError`.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `ImageRef`.
- **Forbidden-patterns / convention:**
  - `CLAUDE.md §"Conventions"` — `_WARNING_IDS: Final[frozenset[str]]` + `raise AssertionError(...)` validation (NOT bare `assert`).
  - `CLAUDE.md §"Functional core / imperative shell"` — no I/O at construction; pure helpers carry the logic.

## Goal

Land `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` containing `NpmVulnProvenanceAdapter` — a class satisfying `VulnProvenanceAdapter`, decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`, reading `package.json` + `package-lock.json` from gathered `RepoContext`, returning typed `AppDirect | AppTransitive | Unknown(reason)` variants. After this story lands, the three positive-path scenarios in `tests/integration/test_provenance_assembly_via_plugins.py` (S3-01) flip from `xfail` to green; the red-state scenario inverts (it will now FAIL because the adapter IS registered) — S3-02's PR removes its `xfail` markers AND deletes the red-state scenario.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` exists (new file; empty or with re-export per existing plugin conventions — match `recipes/__init__.py` style).
- [ ] `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` exists (new file; **this is the byte-edit allowlist row #1 per Phase 7 ADR-0009**).
- [ ] `NpmVulnProvenanceAdapter` is a class implementing `VulnProvenanceAdapter` (runtime-checkable Protocol from S1-04 — verified by an `isinstance` test).
- [ ] Decorated with `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` at class definition; the decorator stores the **class** in `_REGISTRY[(Layer.APP, Ecosystem.NPM)]` (ADR-0007). A unit test asserts `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter` (class identity, not instance).
- [ ] Constructor signature: `def __init__(self, *, sbom_reader: SyftSbomReader, logger: Logger, image_manifest_cache: ImageManifestCache) -> None`. All three kwargs are keyword-only; raw `str` is type-illegal at every typed seam (Phase 7 ADR-0004 newtype discipline). **No positional args, no `*args`, no `**kwargs`.** A unit test asserts `inspect.signature(NpmVulnProvenanceAdapter.__init__)` matches this shape.
- [ ] Constructor does NO I/O. All kwargs are stored as `self._sbom_reader = sbom_reader` etc. A unit test patches `Path.read_text` (and `open`) to raise `RuntimeError("I/O at construction")`, instantiates the adapter, and asserts no exception (i.e., no file is touched at `__init__`).
- [ ] `attribute(self, *, cve_id: CveId, package_id: PackageId, image_ref: ImageRef, sbom: SyftSbom, repo_context: RepoContext) -> Provenance` is the only impure method on the public surface. Arguments are keyword-only; signature is byte-pinned by a fence test or contract assertion (the integration test in S3-01 is the canonical contract; this story may add a unit-level `inspect.signature` smoke).
- [ ] `attribute(...)` returns variants:
  - `AppDirect(package_id, version, locked_version, location)` when the resolved chain from `package.json` root has length 1.
  - `AppTransitive(package_id, version, locked_version, location, chain=[...])` when the chain has length > 1; `chain` is a non-empty tuple of `PackageId` values starting with the direct dep and ending with the queried package (NOT including the root package itself).
  - `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})` when the package does not appear in `package-lock.json` at all.
  - `Unknown(reason="adapter_error", details={"error": str(...)})` is **NEVER** returned directly by the adapter — instead, the adapter raises `AdapterError("...")` and the primitive's `assemble_provenance` converts (per S2-04). A unit test confirms: feed a deliberately-malformed `package-lock.json` (e.g., truncated JSON); assert `AdapterError` is raised (not `Unknown` returned).
- [ ] `confidence(self) -> AdapterConfidence` returns `AdapterConfidence.High` when the lockfile parsed cleanly and the queried `package_id` was resolved; `AdapterConfidence.Degraded(reason="package_not_in_lockfile")` when the lockfile is fresh but the queried package is absent; `AdapterConfidence.Unavailable(reason="lockfile_missing")` when there is no `package-lock.json` in the `RepoContext` at all (the `NodeManifest` probe ran but found no lockfile). The confidence values are pinned in S1-02; this story consumes them.
- [ ] Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"vuln_provenance.adapter_error"})` is declared at module top. Validation: a runtime check at import time uses `raise AssertionError("...")` (NOT bare `assert`) to verify each ID matches the canonical `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex. A fence test under `tests/fence/` (extending existing `_WARNING_IDS` validators) confirms this module is registered.
- [ ] No `subprocess.run`, `os.system`, `os.popen`, `shell=True`, `eval(`, `exec(`, `__import__(`, `pickle.loads` anywhere in the adapter — verified by the existing `forbidden-patterns` pre-commit hook running on the new file. No bare `assert` (forbidden by the same hook).
- [ ] **Functional core / imperative shell:** the lockfile walk is a pure helper module-private function (e.g., `_walk_lockfile_chain(lockfile_dict, target_package_id) -> tuple[PackageId, ...] | None`); `attribute(...)` is the only impure entry point. A test calls the pure helper with hand-built dicts and asserts deterministic output.
- [ ] All three positive-path tests in S3-01's `tests/integration/test_provenance_assembly_via_plugins.py` go GREEN. The `xfail(strict=True)` markers are removed from those three scenarios in this PR. The red-state scenario `test_red_state_when_no_npm_adapter_registered` is DELETED in this PR (the contract has been pinned; the canary is no longer needed).
- [ ] New unit tests under `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` cover:
  - Direct-dep happy path → `AppDirect` with correct `package_id`/`version`/`locked_version`/`location` fields.
  - Transitive-dep happy path → `AppTransitive` with `chain` length ≥ 2 and correct head/tail.
  - Absent package → `Unknown(reason="sbom_layer_attribution_absent")` with `details["package_id"]` set.
  - Lockfile parse error → `AdapterError` raised (NOT `Unknown` returned — Rule 12 fail-loud at the adapter boundary).
  - DI kwargs stored without mutation (test inspects `self._sbom_reader is sbom_reader`).
  - No I/O at construction (test patches `Path.read_text` to raise; instantiate; assert no raise).
  - `confidence()` returns each of the three `AdapterConfidence` variants under the documented conditions.
  - `_WARNING_IDS` module-level constant has shape `frozenset({"vuln_provenance.adapter_error"})` and IDs match the regex.
- [ ] `mypy --strict plugins/vulnerability-remediation--node--npm/adapters` clean — including the new `npm_provenance.py`.
- [ ] `ruff format`, `ruff check plugins/vulnerability-remediation--node--npm/adapters` clean.
- [ ] **Phase 3–6.5 regression suite green** (`make check`) — this story creates a NEW file under the Phase 3 plugin directory; the existing Phase 3 plugin behavior must be byte-identical against the `bench/vuln-remediation/` cassette replay (the adapter is never invoked during Phase 3 recipe dispatch unless TCCM wiring activates it; S3-03 owns the TCCM line). The cassette replay byte-equality (ε ≤ $0.01) is the load-bearing assertion.
- [ ] `make lint-imports` green: no new LLM SDK import; the adapter may import from `codegenie.primitives.vuln_provenance.*`, `codegenie.types.*`, `codegenie.parsers.safe_json` (existing Phase 3 helper), and `pydantic` — and nothing else.
- [ ] Story Status updated to `Done` after all the above check out.

## Implementation outline

1. **Skeleton.** Create `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` (empty). Create `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` with the module-level `_WARNING_IDS` constant + `raise AssertionError(...)` validation block (mirror Phase 0 `_WARNING_IDS` validation pattern from any existing probe — `src/codegenie/probes/language_detection.py` is a clean template).
2. **Class signature.**
   ```python
   @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
   class NpmVulnProvenanceAdapter:
       def __init__(self, *, sbom_reader: SyftSbomReader, logger: Logger,
                    image_manifest_cache: ImageManifestCache) -> None:
           self._sbom_reader = sbom_reader
           self._logger = logger
           self._image_manifest_cache = image_manifest_cache
   ```
3. **Pure lockfile-walk helper.**
   ```python
   def _walk_lockfile_chain(
       lockfile: Mapping[str, object],
       target: PackageId,
   ) -> tuple[PackageId, ...] | None:
       """Return the resolution chain from root to `target`, or None if absent.

       Pure function — no I/O. Walks the npm v2/v3 lockfile `"packages"` map
       (key = "node_modules/foo" path, value = entry with "dependencies"
       and "version"). Returns a tuple of PackageId values: tuple length 1
       means direct dep; length > 1 means transitive.
       """
   ```
   This helper is the **load-bearing pure core**. Test it independently with hand-built dicts.
4. **`attribute(...)` method.**
   ```python
   def attribute(self, *, cve_id: CveId, package_id: PackageId, image_ref: ImageRef,
                 sbom: SyftSbom, repo_context: RepoContext) -> Provenance:
       try:
           lockfile = self._read_lockfile(repo_context)  # may raise AdapterError
       except json.JSONDecodeError as e:
           raise AdapterError("vuln_provenance.adapter_error",
                              details={"error": str(e)}) from e
       chain = _walk_lockfile_chain(lockfile, package_id)
       if chain is None:
           return Unknown(reason="sbom_layer_attribution_absent",
                          details={"package_id": str(package_id)})
       version = _lookup_version(lockfile, chain[-1])
       if len(chain) == 1:
           return AppDirect(package_id=chain[-1], version=version, ...)
       return AppTransitive(package_id=chain[-1], version=version, chain=chain, ...)
   ```
5. **`confidence(...)` method.** Returns the documented `AdapterConfidence` variants based on the same lockfile state — must NOT re-walk; cache the prior `attribute(...)` outcome via a small `_last_outcome: Optional[Provenance]` field, OR compute confidence from a separate cheap read. Pick whichever passes `mypy --strict` cleanly without `Optional`-juggling complexity; if in doubt, read the lockfile twice (it's small).
6. **Cross-verification via `sbom_verifier`.** Defensive: if `S4-01` (`sbom_verifier.py`) has shipped at execution time, call `cross_check_sbom_layer_attribution(sbom, image_manifest)`; if `Verification.Mismatch(...)`, downgrade the result to `Unknown(reason="sbom_layer_attribution_absent")` regardless of the lockfile walk. If `S4-01` has NOT yet shipped (Phase 7 may sequence Steps 3 and 4 in parallel), the adapter must **degrade cleanly to lockfile-only attribution** — guarded by a typed import with `try: from codegenie.primitives.vuln_provenance.sbom_verifier import ... except ImportError: ...` pattern, OR by accepting an injected `verifier: SbomVerifier | None = None` DI kwarg with a `None` default. **Pick the DI variant** — `ImportError`-handling at module-load is fragile.
7. **Wire S3-01's xfails to green.** Remove `xfail(strict=True)` markers from the three positive-path tests; delete `test_red_state_when_no_npm_adapter_registered`. Run the suite; confirm all three pass.

## Test-driven development plan

**Red.** Before writing the adapter body, write the unit tests in `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py`. Each test is a focused assertion of one acceptance criterion. The tests fail at first (`ModuleNotFoundError: plugins.vulnerability_remediation__node__npm.adapters.npm_provenance`). Commit this red state.

**Green.** Write the adapter body just-enough to make each unit test pass. The integration tests from S3-01 are the cross-component witness — once the unit tests are green, REMOVE the `xfail` markers from S3-01's three positive scenarios; run the integration suite; confirm three pass. Then delete the red-state scenario.

**Refactor.** Extract the pure lockfile-walk helper into `plugins/vulnerability-remediation--node--npm/adapters/_lockfile_walk.py` if `npm_provenance.py` exceeds ~150 LOC. Re-run `mypy --strict` + `ruff check` + the full unit + integration suite. The integration test from S3-01 is the integration safety net — if it's still green after refactor, the contract is intact.

## Files to touch

- `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` (new — empty or minimal re-exports).
- `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` (new — **byte-edit allowlist row #1**).
- `plugins/vulnerability-remediation--node--npm/adapters/_lockfile_walk.py` (new, optional — only if the refactor step extracts the pure helper).
- `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` (new).
- `tests/unit/plugins/vulnerability_remediation_node_npm/__init__.py` (new if absent).
- `tests/integration/test_provenance_assembly_via_plugins.py` (EDIT: remove three `xfail` markers; delete `test_red_state_when_no_npm_adapter_registered`).

## Out of scope

- `plugins/vulnerability-remediation--node--npm/api.py` — the import-wiring line is S3-03's row #2 byte-edit. This story's adapter is registered only when S3-03's `api.py` import fires, but that wiring is a separate ADR-0009-tracked allowance.
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` — S3-03 owns the one new entry (aligned with S8-02 schema).
- `BaseImageVulnProvenanceAdapter` / `AlpineVulnProvenanceAdapter` — Step 4.
- `sbom_verifier.py` implementation — S4-01. This story uses a DI-injected `verifier: SbomVerifier | None = None` to degrade cleanly when it's absent.
- Property tests over the adapter (Hypothesis SBOM-tampering) — S4-04 owns; this story's tests are example-based.
- Performance bench — S12-05 owns the p99 ≤ 50 ms assertion.

## Notes for the implementer

- **The "promoted from Phase 3 refuse-mode shape" framing is a HINT, not an instruction to import Phase 3 helpers.** Read `plugins/vulnerability-remediation--node--npm/recipes/` to understand the lockfile shape; then re-derive your own walker. Importing from Phase 3 recipe internals would either (a) require a byte-edit to Phase 3 plugin code (not allowlisted), or (b) lock the adapter to Phase 3 internals that change independently. Both are wrong.
- **`AppDirect.location` and `AppTransitive.location` fields** — these refer to where IN the repo the dep is declared (`package.json` line/path). The exact field shape is fixed by S1-03's union definition. If the union definition has an optional/required mismatch with what the adapter can fill in, surface in the attempt log — do NOT widen the type unilaterally.
- **`AppTransitive.chain` field is the resolution chain from root → target.** This is debuggability data, NOT a promise about the dep-graph topology (which is `dep_graph` probe territory). Length 1 means direct (use `AppDirect`); length 2 means one hop (e.g., root → express → lodash); length N means N-1 hops. **The chain does NOT include the root package itself** — convention pinned here.
- **Re bare `assert`:** `python -m codegenie ...` startup runs each module's import-time validation; bare `assert` is stripped in `-O` mode. Use `if not <cond>: raise AssertionError("...")`. The `forbidden-patterns` pre-commit hook catches violations.
- **Re the integration test in S3-01:** the moment you remove the three `xfail` markers and the tests pass, the contract is satisfied. If the contract test changes shape because of an unforeseen need ("the adapter actually needs access to the resolved npm semver tree from the registry"), that IS a contract change — surface in the attempt log + propose a follow-up to S3-01. Do NOT silently widen S3-01's test fixtures to accommodate.
- **Re cassette replay byte-equality:** S3-02 creates a NEW file. The adapter is not registered into Phase 3's recipe registry; it's registered into the **primitive's** `_REGISTRY` (a different registry). Phase 3 plugin behavior should be unaffected. If `bench/vuln-remediation/` replay drifts by even 1 byte, something is wrong — the diff will name the file and the byte; surface immediately.
- **Re `RepoContext` reading:** the adapter consumes the gathered context, NOT live filesystem. Inject a `repo_context` parameter to `attribute(...)` per the signature above. The caller (`assemble_provenance` indirectly via `AdapterFactory`) is responsible for passing the up-to-date snapshot. If the existing `assemble_provenance` signature (from S2-04) doesn't pass `repo_context`, surface — this is a contract gap S2-04 should have closed.
