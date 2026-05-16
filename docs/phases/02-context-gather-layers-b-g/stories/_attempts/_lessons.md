# Cross-story lessons — Phase 02 stories

Append-only. Each entry: lesson · source story · how to apply it on the next attempt.

## L1 — `uv.lock` parity test trips on any new `[project.optional-dependencies]` entry
- **Source:** S1-01 (added `hypothesis` to `[dev]`).
- **Symptom:** `tests/unit/test_makefile_targets.py::test_uv_lock_is_in_lockstep_with_pyproject_dep_set` fails with `missing packages: ['<new-pkg>']`.
- **Fix:** After editing `pyproject.toml`'s dep set, run `uv lock` and commit the regenerated `uv.lock` in the same commit.
- **Why it matters:** Phase 2 stories add ≥ 7 new packages (per phase-arch §Step 1). Forgetting `uv lock` will break every story's CI until the next `uv lock` ships.

## L2 — Ruff's `UP007` + `UP017` rewrite Pydantic-discriminator-union sources
- **Source:** S1-01.
- **Symptom:** Story TDD-plan code blocks use `Union[X, Y]` and `timezone.utc` literally; ruff auto-rewrites to `X | Y` and `datetime.UTC` (rules `UP007`, `UP017` are enabled at `[tool.ruff.lint] select`).
- **Fix:** Apply ruff `--fix` after dropping in the story's prescribed code; the rewrites are safe under Pydantic v2 discriminated unions and Python 3.11+. Don't fight the linter; the codebase convention wins.
- **Why it matters:** Saves a round-trip on every Phase 2 story that copy-pastes story-prescribed type-alias blocks.

## L3 — Stale local venv hides missing `[dev]` extras
- **Source:** S1-01 (`hypothesis` and `import-linter` were both missing locally).
- **Symptom:** `pytest` collection fails on `import hypothesis`; `lint-imports` console script not on PATH.
- **Fix:** Before starting a story that adds a new tool to `[dev]`, run `.venv/bin/pip install -e .[dev]` (or `uv sync --extra dev`) so the venv reflects the pyproject. The CI fence catches the gap, but local cycles compound.
- **Why it matters:** Every Phase 2 story that uses Hypothesis (per phase-arch §"Testing strategy") or a new linter will hit this.

## L4 — `@runtime_checkable` `isinstance` silently mutates target classes' `__dict__`
- **Source:** S1-03 (adapter Protocols + `test_no_phase2_module_implements_adapter_protocol_dynamic`).
- **Symptom:** `tests/unit/test_errors.py::test_subclasses_are_markers_only` fails with `MalformedJSONError declares extra class attributes … '__annotations__'`. Reproduces only when `tests/unit/adapters/test_protocols.py` runs first.
- **Fix:** Any pkgutil-style walk that ends in `isinstance(inst, AnyRuntimeCheckableProtocol)` MUST filter out classes that cannot possibly satisfy the protocol *before* the isinstance call. For adapter-tier protocols, `issubclass(cls, BaseException)` is the right pre-filter — exceptions cannot satisfy `confidence()`/`consumers()`/etc., and skipping them sidesteps the side effect entirely.
- **Why it matters:** Phase 2's S4-01/02 will revisit dynamic protocol-conformance scans (`AdapterConfidence` consumers in `IndexHealthProbe`-adjacent code). The same trap fires there.

## L6 — Test subpackage name collides with stdlib (`types`, `pathlib`, …) → leave it without `__init__.py`
- **Source:** S1-05 (`tests/unit/types/` for the ADR-0033 newtypes).
- **Symptom:** `pytest tests/unit/types/` errors with `ModuleNotFoundError: No module named 'types.test_identifiers'; 'types' is not a package`. The stdlib `types` module wins the lookup when `__init__.py` is present.
- **Fix:** Do **not** add `__init__.py` to test subpackages whose name shadows a stdlib module. Pytest's rootdir-relative collection works without it (every other test subpackage in this repo has `__init__.py` only because its name doesn't collide).
- **Why it matters:** Any future Phase-2 test subpackage named after a stdlib module (`types`, `string`, `array`, `json`, …) will hit the same trap. The fix is structural; converting the test file imports to absolute paths does not avoid the collision because pytest registers the package itself.

## L7 — Surgical type-alias backfills are the right fix when a Phase-2 story imports a Phase-1-owned name that doesn't exist yet
- **Source:** S1-05 (`PackageManager` referenced by AC-2/AC-5 but not previously exported by `codegenie.probes.node_build_system`).
- **Symptom:** `from codegenie.probes.node_build_system import PackageManager` fails at import time; story tests don't even reach AC-1.
- **Fix:** Add a one-line `PackageManager: TypeAlias = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` to the Phase-1 module that *owns* the concept (`node_build_system.py`), mirroring the JSON schema enum. Do **not** redefine the alias inside `codegenie/types/` — that violates AC-4 and production ADR-0033. Leave existing `str | None` signatures untouched (`Literal | None` is a structural subtype of `str | None`); the cleanup belongs to a separate Phase-1 ADR amendment.
- **Why it matters:** S1-04 (TCCM model loader) and S1-02 (freshness registry) both import `IndexName` from this story. Any future Phase-2 story that references a Phase-1-owned typed name needs the same surgical-backfill pattern, not a kernel-tier redefinition.

## L8 — Source-file docstrings wrap at column-80; substring assertions must normalize whitespace
- **Source:** S1-06 (`test_exec_module_docstring_phase2_present`).
- **Symptom:** `assert "ten Layer B/C/G tools" in codegenie.exec.__doc__` fails even though the docstring contains the phrase, because Python preserves the source-file `\n` between "B/C/G" and "tools".
- **Fix:** Before the substring check, normalize whitespace with `" ".join(doc.split())`. The pretty-printed phrase you'd read in Sphinx output is the right mental model — but `__doc__` is the raw source text.
- **Why it matters:** Any future docstring-pin AC (S1-07's `run_external_cli`, S5-02's `RuntimeTraceProbe`, etc.) will hit this trap. The fix is structural; pinning shorter substrings just delays the trap until the phrase grows.

## L9 — ADR meta-tests that ban a historical string need rewording in *all* legacy references
- **Source:** S1-06 (`test_adr_0001_enumerates_all_new_binaries`).
- **Symptom:** Pass-2 AC-2's "the string `eight new entries` is absent" assertion failed because (a) the Amendment paragraph historically narrated "the original Decision named eight…" and (b) two §Consequences bullets still said "eight named entries" / "eight new entries" — drift from the original eight-binary scope.
- **Fix:** When the meta-test forbids a substring, rewrite *every* legacy occurrence in the ADR, not just the Decision paragraph. Use semantically equivalent phrasings ("the original Decision named only the named-trigger binaries", "by the ten named entries") rather than count words.
- **Why it matters:** Phase 2 has 10 ADRs; every one will eventually have an amendment whose old wording lives elsewhere in the file. The meta-test pattern is sound, but the executor must `grep` the ADR for *all* legacy phrasings before declaring green.

## L10 — `mock.AsyncMock.await_args` is typed `_Call | None`; mypy strict requires explicit `assert ... is not None`
- **Source:** S1-06 (Pass-2 spawn-spy refactor).
- **Symptom:** `mypy --strict` errors with `Item "None" of "_Call | None" has no attribute "kwargs"` on `spy.await_args.kwargs["env"]`.
- **Fix:** Insert `assert spy.await_args is not None` immediately before the `.kwargs` access. Doubles as a regression guard — if the spy was never awaited, the test was wrong.
- **Why it matters:** Every Phase 2 test asserting on `spy.await_args` (S1-07's `run_external_cli` tests, S5-02's `docker`/`strace` spawn assertions, etc.) needs the same `assert ... is not None` line. Family-precedent files get away without it because their mypy scope is older.

## L5 — Pytest collects any `Test*` class imported into a test file's namespace
- **Source:** S1-03 (`TestInventoryAdapter` raised `PytestCollectionWarning: cannot collect test class … has a __init__ constructor`).
- **Symptom:** Importing `TestInventoryAdapter` (or any `Test*`-named class) into `tests/**/*.py` warns at collection time even when no test instantiates it.
- **Fix:** **Alias on import in the test file** — `from codegenie.adapters import TestInventoryAdapter as InventoryAdapter`. Do **not** set `__test__ = False` on the Protocol class (either inside or after the body): on Python 3.11 (CI), assigning `__test__` post-class-body adds it to `_get_protocol_attrs`, breaking `isinstance` for any stub that doesn't declare `__test__`. CI was green on Python 3.13 (local) and red on Python 3.11 (CI) — the `_get_protocol_attrs` implementation diverges across minor versions.
- **Why it matters:** Any future domain type that begins with `Test` (e.g., `TestMatrix`, `TestSuiteId`) needs the import-alias fix in test files, not a runtime mutation of the source class. Setting `__test__` on a Protocol is a portability trap.

## L11 — Story-sketch RED test that decorates inside `with pytest.raises` leaks `UnboundLocalError`
- **Source:** S1-02 (AC-3 duplicate-name rejection test).
- **Symptom:** `with pytest.raises(...): @reg.register(name) def check_b(...): ...` — the decorator raises before binding `check_b`, then the post-`raises` assertion `f".{check_b.__qualname__}" in msg` blows up with `UnboundLocalError: cannot access local variable 'check_b'`.
- **Fix:** Define the function above the `with` block (`def check_b(...): ...`), then call the decorator imperatively inside (`reg.register(name)(check_b)`). The decorator-time semantics survive (qualname still includes the test function as enclosing scope) and the post-block reference is bound.
- **Why it matters:** Phase 2's other registry stories (S1-10 `depgraph` registry; the post-S4 freshness-source registrations) will copy the same duplicate-name pattern. Apply the imperative-call fix on first pass.

## L12 — Phase-N exception-marker additions cascade into two `__all__`-closure tests
- **Source:** S1-02 (`FreshnessRegistryError` addition).
- **Symptom:** Two pre-existing test files break the moment a new marker lands in `codegenie.errors`:
  - `tests/unit/test_errors.py::test_all_closure_pins_public_surface` (pins the EXACT `__all__` set against `EXPECTED_SUBCLASSES`).
  - `tests/unit/test_errors.py::test_every_subclass_has_raise_site_docstring` (requires the docstring to name a `DOCUMENTED_MODULE_SLUGS` entry).
- **Fix:** Add `PHASE_N_NEW = {...}` and `EXPECTED_SUBCLASSES = ... | PHASE_N_NEW` in `tests/unit/test_errors.py`; add the new module's directory slug (`"indices"` for S1-02; `"depgraph"` for S1-10; `"tccm"` for S1-04; etc.) to `DOCUMENTED_MODULE_SLUGS`.
- **Why it matters:** Every Phase-2 marker addition (S1-04 `TCCMLoadError`, S1-10 `DepGraphRegistryError`, S2-01 `SkillsLoadError`, S2-02 `ConventionsError`, S5-01 / S6-06 outcome-types markers, etc.) will trip both. Plan the test edit alongside the source edit.

## L13 — Re-export of new package surface narrows existing equality assertions on `__all__`
- **Source:** S1-02 (`codegenie.indices.__init__` extended with the registry surface).
- **Symptom:** `tests/unit/indices/test_freshness.py::test_all_exports_full_variant_set` asserted `set(m.__all__) == {<S1-01 names>}`; equality fails the moment any sibling story extends the package.
- **Fix:** Loosen the assertion to a subset on the *story-specific* names (`s1_01_names <= set(m.__all__)`). The new sibling story checks its own surface independently. Keeps each story's `__all__` AC scoped to its own deliverable.
- **Why it matters:** Same trap will fire when S1-04 (TCCM model + queries + loader) re-exports from `codegenie.tccm.__init__`, and again at S5-01 (`scenario_result` + `scanner_outcome`). Narrow each per-story assertion to a subset on the story-owned names.

## L14 — `Annotated[Union[Generic[T], …], Field(...)]` aliases are NOT subscriptable
- **Source:** S1-04 (`Result[T, E] = Annotated[Ok[T] | Err[E], Field(discriminator="kind")]`).
- **Symptom:** `TypeAdapter(Result[int, str])` raises `TypeError: typing.Annotated[…] is not a generic class`. Python 3.13's `typing` module rejects subscripting an `Annotated[Union]` alias even when both branches are `Generic`. Tests that try `Result[int, str]` to round-trip a concrete pair will not collect.
- **Fix:** Drop the subscript. Round-trip via the concrete classes directly: `Ok[int].model_validate_json(Ok[int](value=42).model_dump_json())`. Pydantic preserves the generic argument internally for validation; the discriminator-based polymorphic decode is exercised by `TypeAdapter(Result)` (unsubscripted) when needed.
- **Why it matters:** Every Phase-2 loader story that consumes `Result` (S2-01 `SkillsLoader.load`, S2-02 `ConventionsCatalogLoader.load`, future S6-04 external-docs loaders) will be tempted to write `TypeAdapter(Result[Skill, SkillsLoadError])` for tests. It will fail at collection time. The right pattern is concrete-variant round-trip plus a *separate* `Result` polymorphic decode test (unsubscripted adapter, manual `isinstance` check).

## L15 — Alias-on-import for `Test*` types: the *alias name* matters, not just the act of aliasing
- **Source:** S1-04 (`TestsExercising` Pydantic class).
- **Symptom:** Aliased as `from codegenie.tccm import TestsExercising as TestsExercisingQuery` — pytest **still** emitted `PytestCollectionWarning: cannot collect test class 'TestsExercising' …`. The collector's regex is on the *local name in the module's namespace*; `TestsExercisingQuery` still starts with `Test`.
- **Fix:** Choose a non-`Test`-prefixed alias name. For S1-04 the chosen alias was `ExerciseTestsQuery`. Stage 1's L5 lesson recommended aliasing — extend it: the alias name must also fail pytest's `Test*` regex.
- **Why it matters:** Any Phase-2 domain type whose name starts with `Test` (`TestMatrix`, `TestSuiteId`, `TestRunner`, `TestVerdict`, `TestExercising`-family) needs both the alias *and* a non-`Test`-prefixed alias name. The cost of getting it wrong is a spurious warning that does not fail CI but produces noise on every story that imports the class. Get it right on the first commit.

## L16 — Pydantic v2 `union_tag_invalid` puts the discriminator name in `ctx`, not `loc`
- **Source:** S1-04 (`TCCMLoader._classify` translation table).
- **Symptom:** First `_classify` implementation checked `loc[-1] == "compute"` per the story sketch. Pydantic 2.13 actually returns `loc = ('derived_queries', 0)` (the *list index*, not the discriminator field name) on `union_tag_invalid`. The discriminator identity lives in `ctx['discriminator']` as the literal string `"'compute'"` (yes, with embedded single-quotes — Pydantic renders the field name with quotes inside `ctx`). Two `unknown_query_primitive` tests failed under the initial implementation.
- **Fix:** When `type == "union_tag_invalid"`, check `ctx.get("discriminator") in {"'compute'", "compute"}`. Keep the `literal_error` arm checking `loc[-1] == "compute"` as a defensive fallback for the rare codepath where Pydantic emits `literal_error` instead of `union_tag_invalid`. Pin both behaviors in a docstring as the public translation contract — Rule 12: if a Pydantic upgrade breaks AC-8, fix the translation, not the test.
- **Why it matters:** Every future Phase-2 sum-type loader (`SkillsLoader.load` returning `Result[Skill, SkillsLoadError]` with the same `kind` discriminator, S5-01 `scanner_outcome`, S6-06 curated-scanner outcomes) will need the same translation pattern. The shape of Pydantic's error dict is the load-bearing contract; do not infer from the story sketch alone.

## L17 — `Annotated[Union, ...]` aliases composed of generic models break `unwrap()`/`unwrap_err()` mypy signatures
- **Source:** S1-04 (`Ok.unwrap_err` and `Err.unwrap` mypy errors).
- **Symptom:** `mypy --strict` reports `error: A function returning TypeVar should receive at least one argument containing the same TypeVar [type-var]` on always-raises methods that declared `-> E` or `-> T`.
- **Fix:** Methods that always raise should declare `-> NoReturn`. Semantically accurate (the function never returns) and mypy-clean.
- **Why it matters:** Any future `Result`-shaped API where one variant lacks a value will have always-raises helpers. `NoReturn` is the right type; do not work around by adding fake `-> object` or `-> Any` returns.

## L18 — `add_multi_constructor` callbacks receive 3 args, not 2
- **Source:** S1-04 (`_safe_load_mkdocs` helper for parsing `mkdocs.yml`'s `!!python/name:` tags).
- **Symptom:** `TypeError: _ignore_python_name() takes 2 positional arguments but 3 were given` when calling `_MkdocsLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", fn)` with `fn(loader, node)`.
- **Fix:** The callback signature is `(loader, tag_suffix, node) -> Any`. PyYAML's multi-constructor passes the *tag suffix* (everything after the prefix) as the middle argument; this is documented but easy to overlook.
- **Why it matters:** Any future probe / loader that needs to register a YAML constructor for a tag family — including S6-04 external docs loaders that might encounter custom MkDocs/MkDocs-Material tags — needs the 3-arg signature. Single-tag `add_constructor` *is* 2-arg, so the trap is the multi-vs-single split.

## L19 — `mypy --strict` narrows `sys.platform` via `Literal`; indirect through a helper to avoid `unreachable`
- **Source:** S1-07 (`_maybe_wrap_with_bwrap`).
- **Symptom:** `src/codegenie/exec.py:448: error: Statement is unreachable [unreachable]` — mypy on darwin narrows `sys.platform` to the literal `"darwin"`, so `if not sys.platform.startswith("linux"): ... return ...` is "always taken" at type-check time, making the post-`return` `if shutil.which("bwrap") is None:` block unreachable.
- **Fix:** Indirect through `def _platform_is_linux() -> bool: return sys.platform.startswith("linux")`. Mypy cannot narrow through function boundaries, so the post-check branch is reachable. Runtime semantics are identical and `monkeypatch.setattr(sys, "platform", "darwin")` still works (the helper reads `sys.platform` at call time).
- **Why it matters:** Phase 5 (microVM, network namespaces) and any future Layer-C probe (S5-02 `RuntimeTraceProbe`, S5-05 `RuntimeTraceFreshness`) that branches on `sys.platform` under `mypy --strict` will hit the same trap. Reach for the helper on first cycle.

## L20 — `codegenie.exec` cannot top-level import `codegenie.types.identifiers` (circular)
- **Source:** S1-07 (added `ProbeId` annotation to `run_external_cli`).
- **Symptom:** `ImportError: cannot import name 'PackageManager' from partially initialized module 'codegenie.probes.node_build_system' (most likely due to a circular import)`. Chain: `codegenie.exec` → `codegenie.types.identifiers` (re-exports `PackageManager`) → `codegenie.probes.node_build_system` (imports `codegenie.exec`).
- **Fix:** Put the import under `TYPE_CHECKING`. `from __future__ import annotations` is already in `exec.py`, so the deferred annotation is a string at runtime — no actual lookup happens. Only valid when the imported name is used **only in annotations** (`probe_name: ProbeId`); if you ever need to *call* `ProbeId(...)` inside `exec.py`, this trick fails and you must restructure.
- **Why it matters:** Any future `exec.py` extension that wants strict-mypy on a kernel-tier newtype identifier (Phase 2 S5-02's `RuntimeTraceProbe`, Phase 5's microVM wrapper) needs the same `TYPE_CHECKING` pattern. The S1-05 newtype family lives in a module that itself transitively pulls `exec.py`; this is structural.

## L21 — Adding a new runtime dep is a 4-file commit, not a 1-file commit
- **Source:** S1-10 (`networkx` joined the runtime closure).
- **Symptom:** Adding `networkx>=3.2` to `[project].dependencies` broke three tests at once: `test_runtime_dependencies_are_exactly_adr_0006_closure` (pins the closure as a frozenset), `tests/unit/depgraph/test_registry.py` strict-mypy run (`networkx` lacks `py.typed`), and `uv.lock`-parity (L1).
- **Fix:** Land all four edits in the same commit: (a) `pyproject.toml [project].dependencies` widening, (b) `tests/unit/test_packaging.py RUNTIME_DEPS` frozenset widening with a rationale comment, (c) `[[tool.mypy.overrides]]` entry with `ignore_missing_imports = true` for packages without `py.typed`, (d) `uv lock` regen.
- **Why it matters:** Phase 2's remaining stories add several runtime deps (S4-03 grammars lockfile, S4-04 tree-sitter, S5-04 SBOM/CVE scanners). Each will trip the same quadruple. The frozenset-pin in `test_packaging.py` IS the ADR-0006 fence — widen it explicitly with a one-line rationale comment, not silently.

## L22 — Marker docstrings can't contain decorator-application tokens guarded by a zero-registration AC
- **Source:** S1-10 (`@register_dep_graph_strategy` in `DepGraphRegistryError` docstring tripped AC-6's source scan).
- **Symptom:** `test_zero_strategies_registered_in_phase2` flagged `src/codegenie/errors.py` as an offender because its marker docstring described the registry by writing `@register_foo`. The scan is a literal substring search by design (mutation-resistant); the false-positive came from documentation, not code.
- **Fix:** Phrase docstrings around the bare function name (e.g., `register_dep_graph_strategy`) without the `@`. Add an inline note explaining the omission so a future doc-edit pass doesn't "fix" it back.
- **Why it matters:** Every Phase-2 marker whose registry has a zero-registration-in-current-phase AC (S2-01 `SkillsLoadError` + `@register_skill`, S6-04 external-docs loader, etc.) will hit the same trap if the docstring includes `@`. Use the bare name; the prose still makes sense.

## L23 — `cast(<Literal alias>, "value")` is redundant under mypy --strict
- **Source:** S1-10 (test fixtures for `PackageManager` Literal binding).
- **Symptom:** `cast(PackageManager, "pnpm")` raised `redundant-cast` because string literals narrow directly to `Literal["pnpm", ...]` once the LHS has an annotation.
- **Fix:** Use `NAME: PackageManager = "pnpm"` — direct annotation, no cast. The narrow-from-literal is unambiguous under `--strict`.
- **Why it matters:** Any Phase-2 test that pins `Literal["..."]` values (S2-01 `SkillId`-as-Literal, S4-03 grammar-name Literals, etc.) will trip the same redundant-cast lint. The story TDD plans inherited the `cast()` pattern defensively; mypy `--strict` is stricter than the plan assumed.

## L24 — `list[T]` is invariant; copy strategy signatures from the alias exactly
- **Source:** S1-10 (`DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], DiGraph]`; tests wrote strategies with `list[dict[str, object]]`).
- **Symptom:** `Argument 1 has incompatible type "Callable[..., list[dict[str, object]], Any]"; expected "Callable[..., list[Mapping[str, Any]], Any]"`. `list` is invariant — `list[dict[str, object]]` is NOT a subtype of `list[Mapping[str, Any]]` even though `dict[str, object]` is a subtype of `Mapping[str, Any]`.
- **Fix:** Match the alias' inner type exactly. The story TDD plan's `list[dict[str, object]]` is a structural superset but mypy strict rejects it. For test fixtures, prefer `list[Mapping[str, Any]] = [{"name": "@org/a"}]` — Python doesn't care, mypy does.
- **Why it matters:** Every Phase-2 registry/strategy alias that uses `list[T]` (S4-05 dep graph strategy consumer; future S5-02 `RuntimeTraceProbe` runner args) will hit the same trap. Use `Sequence[T]` if you want covariance; use `list[T]` and copy the inner type exactly if you don't.

## L25 — `dataclass(slots=True)` + `from __future__ import annotations` needs `sys.modules` registration when loaded via `spec_from_file_location`
- **Source:** S1-11 (`tests/unit/pre_commit/test_forbidden_patterns_rule_shape.py` introspecting `scripts/check_forbidden_patterns.py`).
- **Symptom:** `AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `dataclasses._is_type` during slot synthesis.
- **Fix:** When loading a non-package script via `importlib.util.spec_from_file_location` + `exec_module`, register the module in `sys.modules[name] = mod` BEFORE `spec.loader.exec_module(mod)`. Slot synthesis under string-form annotations resolves via `sys.modules[cls.__module__].__dict__`; no registration → `None.__dict__` → AttributeError.
- **Why it matters:** Any future Phase-2 (or Phase-3) test that introspects a `scripts/` file holding a `dataclass(slots=True)` will hit this. The script does NOT need to weaken `slots=True` — the test bends.

## L26 — `forbidden-patterns` Phase-2+ rules MUST scope via `applies_when`, not pre-commit YAML
- **Source:** S1-11 (Phase-2 `model_construct` ban under seven packages).
- **Symptom:** N/A — this is a discipline lesson the story §AC-1 prose already pins, not a runtime symptom.
- **Fix:** Path-scope rules inside `scripts/check_forbidden_patterns.py` via the rule's `applies_when` predicate. NEVER scope via `.pre-commit-config.yaml`'s `files:`/`exclude:` regex.
- **Why it matters:** The test surface (subprocess invocation in `tmp_path`) and the runtime surface (pre-commit invocation on staged files) MUST be the same. YAML scoping bypasses the test surface and produces silent rule-coverage gaps; structural Open/Closed (AC-15) breaks. Every future path-scoped rule (Phase-3 `httpx` ban under `plugins/`, future SBOM-scoped rules) inherits the discipline.

## L27 — `zip(strict=True)` over a Literal-tagged tuple is the wrong default when the caller's list length varies
- **Source:** S2-01 (`SkillsLoader.load_all` iterating `zip(TIERS, self._search_paths)` over `TIERS: tuple[Tier, ...]` of length 3).
- **Symptom:** `ValueError: zip() argument 2 is shorter than argument 1` on every test passing fewer than 3 search paths. AC-5 (single-tier symlink fixture) and the original AC-4 draft both passed shorter lists.
- **Fix:** Use non-strict `zip` and let the caller's list length define the iteration. Tier identity is still typed via `Tier: TypeAlias = Literal[...]` — the type system carries the tag even when the runtime tuple is shorter. Document the truncation in the call site (`# noqa: B905 — intentional truncation`).
- **Why it matters:** Every future kernel-side loader that maps a positional argument list onto a fixed Literal-tagged tuple (ConventionsCatalogLoader, future tier-tagged catalogs) hits the same trap. Strict-zip is correct ONLY when both lengths are statically known equal; the test-surface default is variable-length input.

## L28 — Two-stage "read into buffer, then scan the buffer" doubles the memory peak
- **Source:** S2-01 (`_read_frontmatter_bytes` → `_split_frontmatter`).
- **Symptom:** AC-7 budget (`< 256 KB peak on 100 MB body`) failed at 2.1 MB. Root cause: `b"".join(chunks)` allocated the scan window a second time after the chunk-list was assembled.
- **Fix:** Collapse into a single streaming scanner (`_scan_frontmatter`) that appends to a single `bytearray` and early-exits at the closing fence. For a normal SKILL.md with ~70-byte frontmatter, the scanner buffers only ~4 KiB; for the 1 MiB unterminated cap, peak stays under 1.1 MiB.
- **Why it matters:** Every Phase-2/3 loader that scans-then-parses (S2-02 `ConventionsCatalogLoader`, S4-04 tree-sitter import-graph reader, S6-04 external-docs opt-in reader) should default to the streaming shape unless the input is provably bounded by a hard byte cap that already fits in budget.

## L29 — Every `os.read` site needs its own `OSError` handler, not just `os.open`
- **Source:** S2-01 (AC-20 directory-as-SKILL.md fixture).
- **Symptom:** `IsADirectoryError` bubbled out of `_read_frontmatter_bytes` because the loader only caught `OSError` on `os.open`. On macOS, opening a directory read-only succeeds; the failure surfaces at the first `os.read`.
- **Fix:** Wrap the read+hash block in a second `try/except OSError`, translating to `IoFailure(errno_name=...)` — matches the open-time discipline. Two-layer handler shape is what AC-20 actually pins.
- **Why it matters:** Catching only at the open call leaks every read-time errno (TOCTOU file disappearance, EISDIR, EACCES, partial-read EIO) as an unhandled exception, breaking the partial-success invariant. Phase-2 multi-file loaders MUST handle BOTH open- and read-time OS errors; one without the other is a false sense of robustness.

## L30 — Pydantic v2 discriminator-tag failures locate at the list slot, not `kind`
- **Source:** S2-02 (`ConventionsCatalogLoader._classify_validation_error`).
- **Symptom:** AC-8 (`unknown pattern kind`) and AC-13b (`partial success under mixed-quality catalogs`) misclassified the failure as `SchemaError` instead of `UnknownPatternType` because the row's `loc` did not end in `"kind"`. Pydantic v2 reports `loc=['rules', 0]` (or `[<idx>, '<variant_kind>']`) with `type='union_tag_invalid'` and the offending tag in `ctx.tag`.
- **Fix:** Filter rows by `type ∈ {union_tag_invalid, union_tag_not_found}` (independent of `loc`); extract the tag from `ctx.tag` (fallback: `input['kind']` when `ctx` is absent). Document the Pydantic v2 contract in a comment — the introspection shape has been revised twice and is likely to drift again.
- **Why it matters:** Every Phase-2+ loader that wraps a Pydantic discriminated union and emits typed per-file errors needs the same classifier — getting the `loc` semantics wrong silently demotes every tag failure to a generic schema error and breaks operator triage.

## L31 — `ValidationError.errors()` may carry non-JSON-serialisable values from `model_validator` failures
- **Source:** S2-02 (`SchemaError.details` serialization through structlog).
- **Symptom:** `pydantic_core.PydanticSerializationError: Unable to serialize unknown type: <class 'ValueError'>` raised from `_logger.warning(_EVENT_LOAD_FAILED, **err.model_dump(mode="json"))` when a regex `model_validator(mode="after")` re-raised `re.error` as `ValueError`. Pydantic stuffed the `ValueError` *object* into `errors()[i].ctx.error`; storing the row directly let construction succeed but blew up at dump.
- **Fix:** Round-trip the rows through `exc.json()` (Pydantic's JSON-safe serializer) and `json.loads` back to Python — one line, alias-resistant. The resulting `list[dict[str, object]]` carries only str/int/list/dict primitives.
- **Why it matters:** Every Pydantic discriminated-union loader that surfaces `ValidationError.errors()` to a logger or wire format must apply the same round-trip. Storing the raw rows is a latent bomb that detonates the first time a downstream `model_dump(mode="json")` is called.

## L32 — Pydantic `frozen=True` + per-instance memo cache wants `PrivateAttr`
- **Source:** S2-02 (`Catalog._memo` for `apply()` idempotency under repeated calls — AC-12).
- **Symptom:** A `_memo: dict[...]` as a regular field broke `extra="forbid"`-style serialization and forced `arbitrary_types_allowed=True`; `object.__setattr__` from inside `apply` was structurally noisy and tripped frozen-write warnings.
- **Fix:** Declare `_memo: dict[int, list[ConventionResult]] = PrivateAttr(default_factory=dict)`. `PrivateAttr` is excluded from serialization, equality, and the frozen write-block; mutating the dict in place (`self._memo[key] = ...`) is allowed by design. Key on `id(repo)` for per-snapshot memoization; a fresh snapshot wires a fresh evaluation.
- **Why it matters:** Every Phase-2+ pure-functional Pydantic model that needs per-instance memoization (catalog evaluators, future planner pre-computation caches) should reach for `PrivateAttr` first.

## L10 — Entropy fallback double-fires on post-redacted strings
- **Source:** S3-01.
- **Symptom:** A long string carrying a named secret (`"Authorization: token ghp_<36>"`) yields two findings — the GitHub-token match plus an entropy hit on the post-replacement string (the 8-hex fingerprint is high-entropy). Tests AC-15b / AC-27 / AC-34 fail with `findings_count` off by one.
- **Fix:** In `_redact_string`, set `matched_any_named = True` when any named pattern's `re.subn` returns `n > 0`; skip the entropy fallback entirely on that leaf. Entropy is the catch-all for unknown shapes, not a redundant second pass over redacted output. Documented in `sanitizer.py` module docstring.
- **Why it matters:** S3-03 reads `findings_count` for the `secrets_redacted_count` structured-event field; the CLI summary depends on a one-finding-per-cleartext invariant.

## L11 — Pydantic v2 + recursive `JSONValue` requires `TypeAliasType`, not plain union
- **Source:** S3-02 (`RedactedSlice.slice: dict[str, JSONValue]`).
- **Symptom:** `RecursionError: maximum recursion depth exceeded` in Pydantic's `_generate_schema._union_schema` on the first instantiation of any Pydantic model with a `JSONValue`-typed field. The Phase-1 alias form `JSONValue = bool | int | float | str | None | list["JSONValue"] | dict[str, "JSONValue"]` works fine as a return-type annotation but not as a Pydantic schema source — forward-string references aren't resolved to a named alias.
- **Fix:** Redefine `JSONValue` in `src/codegenie/parsers/__init__.py` via `typing_extensions.TypeAliasType("JSONValue", "bool | int | float | str | None | list[JSONValue] | dict[str, JSONValue]")`. Static type-checking semantics are unchanged. PEP 695 `type JSONValue = ...` is **not** an option because the project pins `requires-python = ">=3.11"`.
- **Why it matters:** Any future Phase-2 / Phase-3 Pydantic model that carries a JSONValue field (RAG ingest, audit-anchor, persistent telemetry) hits the same wall otherwise.

## L12 — Mutation regexes must be unable-to-match the canonical, not merely "weaker"
- **Source:** S3-01 (six pattern-class mutation tests).
- **Symptom:** The story's prescribed mutation `AKIA[0-9A-Z]{15}` (one fewer required char) is *more permissive* than the production `AKIA[0-9A-Z]{16}` and still matches the 19-char prefix of the 20-char canonical, so `re.sub` redacts and the mutation-test assertion (`canonical in result`) fails.
- **Fix:** Mutate to a pattern that fundamentally cannot match the canonical: length-quantified rules → `{N+1}` (require one more char than the canonical has); literal-prefix rules (JWT) → swap the literal; multi-line block (RSA) → `[^\n]` between BEGIN/END so a newline breaks the match.
- **Why it matters:** Every Phase-2 mutation-test story (S6-07 gitleaks fixtures, S5-04 SBOM regex pack, etc.) inherits the precision discipline: "weaker" is ambiguous; "unable-to-match" is testable.

## L13 — Pydantic v2 `@field_validator` on a `list[T]` field receives the whole list
- **Source:** S3-02 (`fingerprints` validator).
- **Symptom:** A `def _validate_fingerprints(cls, v: str) -> str` validator declared on a `list[str]` field fails mypy strict because Pydantic v2 `mode="after"` (the default) passes the post-coerced field value — the whole list — not per-element strings.
- **Fix:** Type as `def _validate_fingerprints(cls, v: list[str]) -> list[str]` and iterate inside the validator. `isinstance(fp, str)` is defensive against non-str coercions.
- **Why it matters:** Any future Phase-2 / Phase-3 field validator targeting a `list[T]` field (the fingerprint family expanding into RAG ingest, audit-anchor, etc.) inherits the discipline.

## L33 — `import-linter` does not honor `if TYPE_CHECKING:` blocks
- **Source:** S3-03 (`codegenie.cli` annotation referencing `RedactedSlice`).
- **Symptom:** `lint-imports` fails the `codegenie.cli must not top-level import heavy modules` contract with `codegenie.cli -> codegenie.output.redacted_slice -> pydantic` even though the only import path in `cli.py` is inside an `if TYPE_CHECKING:` block. `grimp` (import-linter's analyzer) walks the AST and records every import statement regardless of runtime guard.
- **Fix:** Add `ignore_imports = ["codegenie.cli -> codegenie.output.redacted_slice"]` to the contract (with a comment naming the `TYPE_CHECKING`-only justification). The runtime cold-start property (`import codegenie.cli` does not eagerly load pydantic) is preserved by the `TYPE_CHECKING` guard; the static whitelist is just bridging the spirit-vs-letter gap.
- **Why it matters:** Every future Phase-2/3 story that annotates a kernel-tier module (cli, exec, errors) with a Pydantic / structlog / yaml class will hit this. The fix is structural; ripping out `TYPE_CHECKING` in favor of string-literal annotations only kicks the problem one tool downstream (ruff F821).

## L34 — `typing.get_type_hints` on a `TYPE_CHECKING`-only annotation needs `localns`
- **Source:** S3-03 (test pinning `_seam_*_envelope` annotation propagation).
- **Symptom:** `typing.get_type_hints(cli_mod._seam_write_envelope)` raises `NameError: name 'RedactedSlice' is not defined` because the class is imported under `if TYPE_CHECKING:` (which evaluates to `False` at runtime — see L33). PEP 563 deferred evaluation just preserves the string; resolution still needs the class visible in some namespace.
- **Fix:** Pass `localns={"RedactedSlice": RedactedSlice}` to `get_type_hints`. The test file imports the class normally (tests have no cold-start restriction); the localns dict bridges the deferred forward reference back to the live class.
- **Why it matters:** Any future test that asserts on the type-annotations of a kernel-tier function whose annotation comes from a `TYPE_CHECKING` import needs the same localns trick. Without it, the test passes in module-loading order quirks (sometimes works on Python 3.11 if the import happened earlier) but fails reliably on 3.13. Pass the localns dict on first cycle.

## L35 — `ContextVar` is the right primitive for per-call state in a pure functional module
- **Source:** S3-03 (`envelope_redactor` three-pass composition).
- **Symptom:** The three pass functions in `_PASSES` share an accumulating `list[SecretFinding]` but their `Protocol`-typed signature is `dict -> dict`. Module-level mutable state breaks DP4 (pure functional core). Passing state through the Protocol breaks DP1 (mockability — the spy test monkeypatches `_PASSES` with `Mock(wraps=...)` and the wrapped originals must still see the state).
- **Fix:** Bind state via `contextvars.ContextVar` set at the top of `_redact_envelope` and reset in the `finally`. Pure functional core preserved (no I/O, no globals), per-call state thread-safe + reentrant via the token/reset pattern, mocks pass through unchanged because the state lives outside the pass signature.
- **Why it matters:** Any future Phase-2/3 multi-pass pipeline that wants pure-functional passes + shared accumulation (the RAG-scrubber composition, audit-anchor multi-stage build, future per-task-class redactors) inherits the discipline. `ContextVar` beats `threading.local` because it works under asyncio without leaking across tasks; it beats a module-level `list` because tests can't run in parallel without bleed.

## L14 — `mypy --strict tests/...` standalone errors on codegenie imports; pre-commit hook is the canonical AC-11 satisfaction
- **Source:** S4-02 (AC-11 wanted `mypy --strict tests/adv/phase02/test_stale_scip_fixture.py`).
- **Symptom:** Standalone `uv run mypy --strict tests/adv/phase02/test_stale_scip_fixture.py` errors with `Skipping analyzing "codegenie.*": module is installed, but missing library stubs or py.typed marker` for every `from codegenie...` import.
- **Fix:** The project's mypy contract is `mypy --strict src/` via the pre-commit hook (`.pre-commit-config.yaml`). Run `uv run pre-commit run mypy --files <test-file>` (or `--all-files`) — the hook resolves the source tree correctly. Alternatively `cd src && uv run mypy --strict --explicit-package-bases ../tests/...` works.
- **Why it matters:** Every Phase-2 story whose AC-N says "mypy --strict <test-file>" will hit the same surprise; cite pre-commit as the AC-satisfaction path, not standalone mypy.

## L15 — `tests/fixtures/portfolio/<fixture>` seed-vs-runtime split is the load-bearing pattern, not vendoring `.git/`
- **Source:** S4-02 (stale-scip fixture).
- **Symptom:** Vendoring a nested `.git/` is mechanically impossible (Git refuses to track it as files); the repo-wide `.gitignore` already excludes `.codegenie/` everywhere, so any runtime artifact is gitignored.
- **Fix:** Track only the *seed* material (`_seed/<template>.json` with substitution tokens, `regenerate.sh`, `README.md`, content files for the commits, fixture-local `.gitignore`). Make `.git/` + `.codegenie/` runtime-materialized by `regenerate.sh`. This is Functional-Core / Imperative-Shell at the fixture boundary (DP2).
- **Why it matters:** S5-05 (image-digest-drift), S5-06 (adversarial-dockerfile), S6-07 (secret-in-source), S7-02 (fixtures batch two) will all need the same pattern. Apply it on first pass.

## L16 — `pytest-timeout` is NOT on the dev-dep list (Phase 0/1); use a `time.perf_counter` budget instead
- **Source:** S4-02 (AC-10 wanted `@pytest.mark.timeout(10)`).
- **Symptom:** `@pytest.mark.timeout(10)` silently does nothing if `pytest-timeout` isn't installed (it's not a registered marker; the decorator becomes a no-op via the `unknown-marker` strict path).
- **Fix:** Start `time.perf_counter()` at the test entry, assert `(time.perf_counter() - started) < BUDGET` at the end. The story permits the substitution explicitly; carry forward to S5-05/S6-07 etc. Don't add `pytest-timeout` as a dep without an ADR — the existing `--cov-fail-under` + adversarial budgets cover the same surface.
- **Why it matters:** Every future adversarial in `tests/adv/phase02/` that pins a walltime AC will face this choice.
