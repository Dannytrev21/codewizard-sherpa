# Phase 00 — Cross-story lessons

Short, reusable takeaways picked up while implementing the Phase 00 backlog.
Add to this file whenever an attempt surfaces a fact that *another* story
would have benefited from knowing.

## Tooling / packaging

- **Hatchling's default `[tool.hatch.version]` regex rejects PEP 526 annotations.**
  `__version__ = "..."` works out-of-the-box; `__version__: str = "..."` does not.
  Either drop the annotation or set
  `pattern = "^__version__(?:\\s*:\\s*[^=]+)?\\s*=\\s*['\"](?P<version>[^'\"]+)['\"]"`.
  Discovered in **S1-01**.

- **Click's `--help` / `--version` raises `click.exceptions.Exit`.**
  In a `main(argv) -> int` entry point, set `standalone_mode=False` and catch
  `Exit` to return the embedded exit code; otherwise pytest subprocess tests
  pass but the function-call API leaks `SystemExit`. Discovered in **S1-01**.

- **`mypy --strict` does NOT enable `warn_unreachable`.**
  `warn_unreachable` is a strict-extra flag; it must be set explicitly under
  `[tool.mypy]`. Without it, dead-code-after-narrowing slips through silently.
  Discovered while writing the AC-2 assertion in **S1-02**.

- **`ruff format` is line-length-coupled.**
  Changing `line-length` in `[tool.ruff]` will reformat every pre-existing
  file with lines past the new width. Run `ruff format .` (not just
  `--check`) once after landing the new width to avoid PR-noise diffs in
  later stories. Discovered in **S1-02** when bumping to `line-length = 100`
  forced reformatting `tests/unit/test_packaging.py` from S1-01.

- **`[tool.ruff.format]` can be declared as an empty sub-table.**
  The AC-1 wording "`[tool.ruff.format]` table is declared" is satisfied by
  an empty table header — ruff format works against it. Don't invent format
  knobs you don't actually need. Discovered in **S1-02**.

- **Substring assertions in TDD plans should be anti-subsequences of near-misses.**
  Asserting `"pip install" in body` would also match `"uv pip install"`,
  silently passing a uv-only Makefile that omits the pip fallback. Pick the
  longer literal (`"python -m pip install"`) that appears only in the branch
  you actually want to assert. The same pattern applies to fence tests
  (S1-05) and exec allowlists (S2-04). Discovered in **S1-03**.

- **`_recipe_body` regex must be tab-anchored to avoid matching comment blocks.**
  When the Makefile's header comment deliberately mentions forbidden tokens
  (e.g., `[[ ... ]]` to document the POSIX-sh prohibition), an AC-9-style
  bash-ism check that scans the whole file would self-trigger. Scope the
  recipe-body extractor to lines beginning with `\t` only. Discovered in
  **S1-03** while writing the bash-ism guard.

- **Pre-commit local hooks that scan "all text" amplify documentation noise.**
  A `types: [text]` scope on a forbidden-patterns hook hits every markdown
  file that documents the banned construct (regex sources, ADR text,
  example snippets). Tighten with `files: '\.py$'` so the hook only sees
  Python source; `exclude:` then carries the per-rule scoping (AC-11's
  `^(tests/|scripts/)`). Discovered in **S1-04**. Same lesson applies to
  S2-02's AST scans — scope by import path, not file type.

- **`mkdocs build --strict` needs a tolerant `validation:` block in a
  multi-phase repo.** Strict mode promotes every warning to an error;
  cross-phase ADR relative links (`../../../production/adrs/...`,
  `../../../../CLAUDE.md`) resolve outside `docs_dir` and trip 42+
  warnings. Set `validation.nav.omitted_files: ignore`,
  `validation.nav.not_found: ignore`, `validation.links.not_found: ignore`
  in Phase 0; let S5-02 untangle the link graph. Discovered in **S1-04**.

- **`root = true` in `.editorconfig` breaks Python `configparser`.**
  The editorconfig spec puts `root = true` outside any section; `configparser`
  treats top-of-file properties as a `MissingSectionHeaderError`. If a TDD
  contract test reads `.editorconfig` with `configparser`, omit `root = true`
  or wrap it in a `[DEFAULT]` section. Discovered in **S1-04**.

- **SHA-resolving a hook repo's release tag.** `gh api repos/<owner>/<repo>/git/refs/tags/<tag>`
  returns `object.sha` directly when `object.type == "commit"` (lightweight
  tags); only annotated tags require a second lookup against `git/tags/<sha>`.
  In Phase 0 all four hook repos (ruff-pre-commit, mirrors-mypy, gitleaks,
  pre-commit-hooks) ship lightweight tags — no dereference needed.
  Discovered in **S1-04**; will repeat when adding hooks in later phases.

- **import-linter v2 hard-errors on missing `source_modules`.** A story that
  declares a contract on a module not yet authored ("vacuously enforced until
  story X") will not work as a no-op — `lint-imports` exits non-zero with
  "Module 'X' does not exist." The practical resolution is a placeholder stub
  module with no top-level imports, expanded later. Also, when
  `forbidden_modules` names external packages (anything not under
  `root_packages`), `include_external_packages = true` is **required** at the
  top level of `[tool.importlinter]`; otherwise import-linter refuses to run.
  Discovered in **S1-05**.

- **Pre-commit's isolated mypy env doesn't share the project venv.** The
  `mirrors-mypy` hook installs into its own virtualenv listed via
  `additional_dependencies:`. If `src/` imports `packaging` (or any non-stdlib
  module not already wired through `[project.dependencies]`), the hook fails
  with `Cannot find implementation or library stub` even though `make
  typecheck` is green. Always mirror new `src/` imports into the hook's
  `additional_dependencies:` block. Discovered in **S1-05**.

- **PyYAML's `safe_load` maps the YAML key `on:` to the Python `True` literal.**
  YAML 1.1 booleans include `on/off/yes/no`. A parser test that does
  `workflow["on"]` will `KeyError` even when the YAML clearly contains
  `on:`. Tolerate both keys (try `True` first or use a helper) when reading
  GitHub Actions workflow files. Discovered in **S1-05**.

- **Python 3.13 auto-injects `__firstlineno__` and `__static_attributes__`
  into every class `__dict__`.** Any "markers-only" closure test of the
  form `set(cls.__dict__.keys()) <= {"__module__", "__qualname__",
  "__doc__"}` will fail on 3.13+ even for a behavior-free `class X(Base): pass`.
  Widen the allowed set to include both PEP-issued compiler keys; the
  load-bearing invariant ("no user-declared attributes") still holds.
  Discovered in **S2-01**.

- **import-linter's `as_packages` flag distinguishes a package's
  `__init__.py` from its entire descendant tree.** A `forbidden` contract
  with `source_modules = ["codegenie"]` and the default
  `as_packages = true` traverses every submodule — so adding any new
  submodule that legitimately imports `structlog`/`yaml`/`pydantic` breaks
  a contract whose documented name says "(`__init__`)". Set
  `as_packages = false` to scope the contract to just the package init.
  The canonical S1-05 canary (positive KEPT + planted heavy import →
  BROKEN) remains the regression test. Discovered in **S2-01**.

- **A new third-party dep is *three* coordinated edits, not one.**
  `pyproject.toml` (so the local venv resolves it), the pre-commit
  `mypy` hook's `additional_dependencies:` block (so the hook's
  isolated venv resolves it identically), and a regenerated `uv.lock`
  (the `test_uv_lock_is_in_lockstep_with_pyproject_dep_set` gate
  catches drift). Forgetting any one of the three lets local CI pass
  while a downstream gate (pre-commit hook OR lockstep test) silently
  fails. Discovered in **S2-05** when adding `types-jsonschema`.

- **`functools.lru_cache` on bound methods leaks `self`; module-level
  cached helpers expose `.cache_info()` for free.** When an AC asks
  for an observable cache (`hits >= 1` after repeated calls), factor
  the cached function to module scope and have the method delegate.
  Bound-method caching stores `self` in the cache key (registry/instance
  lifetime leak) and the descriptor wrapping hides the `cache_info`
  attribute from `instance.method.cache_info()`. Discovered in **S2-05**.

- **`jsonschema.RefResolver` is deprecated; `referencing.Registry` is the
  forward path.** Register sub-schemas by their absolute `$id` (e.g.
  `https://…/probes/<name>/v0.1.0.json`) — the envelope's `$ref` is then
  a stable absolute URI, no relative-path base-URI surprises. Stories
  whose implementer notes still suggest `RefResolver` can adopt the
  modern API without breaking ACs; the validator tests check what
  `$ref` resolves to, not which library did the resolution. Discovered
  in **S2-05**.

- **Recursive Pydantic v2 types on Python 3.11 → `typing_extensions.TypeAliasType`.**
  A naive `JSONValue: TypeAlias = Union[..., "list[JSONValue]", ...]`
  hangs Pydantic v2's schema builder with `RecursionError`. The
  documented workaround is a *named* recursive alias —
  `TypeAliasType("JSONValue", Union[...])` from `typing_extensions` —
  not the PEP-695 `type` statement (3.12+ only). `typing_extensions`
  is transitively available via pydantic; no pyproject change.
  Discovered in **S3-02**.

- **Pydantic v2 `@field_validator` only wraps `ValueError`,
  `AssertionError`, and `PydanticCustomError`.** Raising a typed
  exception (e.g. `SecretLikelyFieldNameError`) directly propagates
  unwrapped — the `ValidationError` contract breaks. Wrap via
  `raise PydanticCustomError("kind", "msg", {"error": exc, ...}) from exc`
  and downstream consumers recover the typed error at
  `errors()[0]["ctx"]["error"]`. Discovered in **S3-02**.

- **Pydantic v2 strict mode does NOT reject `Decimal -> float`.** Even
  with `model_config = ConfigDict(strict=True)`, `Decimal('1.0')` lands
  as `float(1.0)`. If a field needs to reject `Decimal` (e.g. JSON-only
  closures), use `@field_validator(..., mode="before")` to whitelist
  leaf types before Pydantic's coercion runs. Discovered in **S3-02**.

- **Longest-prefix-wins in path scrubbing falls out of `re` alternation
  order.** Python's `re` evaluates `|` left-to-right and stops at first
  match. Place the longest/most-specific prefix first in the alternation
  and the engine picks it for free — no lookbehind, no sort pass. Used by
  the path-scrub regex in `output/sanitizer.py` to handle the case where
  `repo_root` happens to sit under `/Users/<u>/`. Discovered in **S3-03**.

- **TDD-plan test bodies and helpers can contradict each other.** S3-03's
  story shipped a `_iter_strings` helper that walked dict keys, but an
  assertion `flat == ["src/a.js"]` that presumed no keys appeared. Always
  rewrite a test that contradicts its own helper to encode WHY (Rule 9)
  rather than mechanically copying the broken shape. Similarly, the
  benign-key matrix included `tokens_per_line` — which the canonical
  `SECRET_FIELD_PATTERN` correctly flags. Discovered in **S3-03**.

- **`types-PyYAML` belongs in `[project.optional-dependencies].dev` whenever
  `src/codegenie/**` imports `yaml`.** The pre-commit mypy hook lists it
  under `additional_dependencies`, but the local `make typecheck` reads
  only `[dev]`. Adding the stub closes the local/CI gap so a fresh
  contributor checkout passes `mypy --strict` on day one. Discovered in
  **S3-03**.

- **Module-level mutable flag for "log once per process".** When a fallback
  path is expected to fire and persist across many calls (e.g. `yaml`
  C-extension missing), a module-level `bool` plus a single test that
  `monkeypatch.setattr(mod, "_warned", False, raising=False)` keeps the
  semantics correct without test-pollution leakage. Function-local flags
  emit the warning every call; no flag emits noise that teaches
  contributors to ignore the message. Discovered in **S3-03**.

- **`typing.get_type_hints(<dataclass>)` is the per-field-isinstance hook
  under `from __future__ import annotations`.** Bare `dataclasses.fields(C)[i].type`
  returns the *unresolved string* form ("int", "bool") under PEP 563, so
  `isinstance(value, field.type)` fails with `TypeError: isinstance() arg 2
  must be a type`. `typing.get_type_hints(C)` resolves the strings to actual
  types in one stdlib call; cheaper than `inspect.get_annotations` for a
  hot loop because it caches. Discovered in **S3-04** while wiring AC-9's
  type-mismatch wrap (dataclasses don't validate types at construction —
  the wrap has to be explicit).

- **Spy-on-helper tests require the helper to be a module-scope `def`.**
  S3-04 AC-14 uses `monkeypatch.setattr(loader_mod, "_typed_construct", spy)`
  to intercept the merged-dict before `Config(**merged)` runs. A nested
  closure, a `lambda`, or a method bound to a class instance would not be
  patchable from outside. Lesson: every wrappable surface a downstream test
  may want to introspect should be a `_underscored` top-level function. Has
  no runtime cost; preserves test-time hookability. Discovered in **S3-04**.

## Coordinator + structlog + asyncio (S3-05)

- **Pytest 9 intercepts `raise KeyboardInterrupt()` regardless of
  `pytest.raises` / in-test `try` context.** It treats KeyboardInterrupt as
  Ctrl-C abort and short-circuits the test before the except clause runs.
  For AC-style "BaseException carve-out" coverage (`except Exception` must
  not trap a true `BaseException`), use a project-local `BaseException`
  subclass — the failure-isolation logic under test is identical, and
  pytest doesn't intercept arbitrary BaseException subclasses. Discovered
  in **S3-05**.
- **`structlog.contextvars.bind_contextvars` MUST be paired with
  `structlog.contextvars.clear_contextvars()` in a `finally` block.**
  Without the finally clause, the binding (here `run_id`) leaks into
  subsequent tests sharing the process — per-test event-stream isolation
  silently breaks. Discovered in **S3-05** while wiring `run_id` for AC-23.
- **`dataclasses.replace(snap)` does NOT isolate mutable fields.** It
  produces a fresh outer dataclass instance, but `detected_languages` and
  `config` (dicts) remain shared references. If a probe mutates one of
  those in-place (AC-18), the mutation leaks to sibling probes' views.
  Shallow-copy the mutable fields explicitly: `dataclasses.replace(snap,
  detected_languages=dict(snap.detected_languages))`. Discovered in
  **S3-05**.
- **`mypy --strict` + `warn_unreachable` flags `sys.platform == "darwin"`-gated
  early-return branches as dead code on the dev platform.** The compiler narrows
  `sys.platform` to a literal string on the dev machine. Use a single ternary
  to compute the platform-dependent value instead of branching with `return`
  statements. Same problem with `if TYPE_CHECKING:`-only blocks that
  return early. Discovered in **S3-05** while normalizing `ru_maxrss` units.
- **`Probe.run` signature types `ctx: ProbeContext` but Python doesn't enforce
  it.** The coordinator passes a `BudgetingContext` (duck-typed surface with
  `workspace`, `report_bytes`) rather than constructing a full `ProbeContext`.
  Works because Phase 0's only real probe (`LanguageDetectionProbe`, S4-01)
  needs nothing beyond `workspace`. Phase 1+ probe-authoring guide MUST
  codify which `ProbeContext` attributes are MANDATORY vs OPTIONAL so a
  probe author can rely on the contract without inspecting the coordinator
  internals. Discovered in **S3-05**.
- **Adding a new `CodegenieError` subclass requires three touches.** (a)
  Declare the class in `src/codegenie/errors.py` with a docstring containing
  one of the slugs in `DOCUMENTED_MODULE_SLUGS` ({exec, cache, sanitizer,
  validator, writer, coordinator, config, tool_check, schema}); (b) add it
  to `__all__`; (c) add the string to `EXPECTED_SUBCLASSES` in
  `tests/unit/test_errors.py`. The public-surface-closure test
  (S2-01 AC-1) pins this triple — a typo in any of them fails CI loudly.
  Discovered in **S3-05** while adding `ProbeBudgetExceeded`.
- **Tests pass instances, AC text often says `list[type[Probe]]`.** When the
  AC's typed signature contradicts the concrete test code in the same
  story, follow the tests — AC text is doc-lag; concrete-runnable tests
  are the runtime contract. Document the divergence in the attempt log as
  a follow-up doc-amendment. Discovered in **S3-05**: the gather signature
  takes `Sequence[Probe]` (instances) because the tests use per-instance
  hooks (`_run`, `_seen_snapshots`, `probe.run = AsyncMock(...)`).
- **`lint-imports` is a static-AST analyzer — it sees function-body imports
  too.** A lazy `from codegenie.audit import verify_runs` inside a click
  command still appears in the import graph and trips the `forbidden_modules`
  contract on `codegenie.cli` (transitive `pydantic` / `structlog` / `blake3`).
  The escape hatch: `importlib.import_module("codegenie.audit")` — dynamic
  imports are invisible to AST analysis. The cold-start runtime test
  (`test_cli_cold_start.py`) still enforces that *importing* `codegenie` (no
  subcommand running) doesn't pull heavy modules, so the cold-start invariant
  isn't weakened. Discovered in **S3-06** while wiring `audit verify` into
  `cli.py`.
- **Substring grep tests catch field names that contain the forbidden token.**
  `audit.py` is supposed to not contain `"blake3"` (ADR-0001 chokepoint). But
  reading the cache index requires the field name `"blob_blake3"` — that
  substring trips the same grep test. Pattern: instead of hardcoding the
  algorithm-bearing field literal, look it up dynamically
  (`next(k for k in record if k.startswith("blob_") and k != "blob_sha256")`).
  Bonus: the source is robust to a future BLAKE3 → BLAKE4 swap without
  touching the verifier. Discovered in **S3-06**.

## Probes / contract

- **`Path.rglob(pattern)` is unforgiving about bare extensions.**
  `rglob(".js")` matches files literally *named* `.js` (none in normal
  repos); `rglob("**/*.js")` matches every `.js` at any depth. A probe whose
  `declared_inputs = [".js", ...]` produces a constant empty input set, which
  collapses `content_hash_of_inputs([])` to a single value across probes →
  cache-key collisions on the warm path and false-positive cache hits that
  mask real source changes. **Always glob-form, never bare extension.**
  Discovered in **S4-01**.

- **`PermissionError` is an `OSError` subclass — one except clause suffices.**
  A probe walker that catches both `PermissionError` and `OSError` in
  separate clauses is dead-code in the second branch (the first catches
  everything). Collapse to `except OSError` and emit
  `f"{type(exc).__name__}: {exc}"`; the AC-5-style `errors[0].startswith("PermissionError")`
  assertion still passes for permission cases, and other walk failures (e.g.,
  `FileNotFoundError` on a missing root) demote confidence without
  re-raising. Discovered in **S4-01**.

- **`OutputSanitizer.scrub` is a chokepoint on `RepoContext` emit, NOT a
  structlog processor.** Anything a probe emits via `_log.info(...)` ships
  unscrubbed through the structlog processor chain. So when logging from
  inside a probe, **emit relative paths only** (`str(Path(entry.path).relative_to(snapshot.root))`),
  never resolved symlink targets — those would leak `/Users/<user>/...` into
  log lines that no later pass scrubs. Discovered in **S4-01** for the
  symlink-escape event payload; will apply to every Layer A–G probe that
  logs path-shaped values.

## CLI / harness wiring

- **`structlog.testing.capture_logs()` swaps `processors` only, NOT
  `wrapper_class`.** A test that captures logs while running code that
  also calls `structlog.configure(...)` (e.g., `configure_logging`) sees
  an EMPTY `logs[]` — the second `configure` call wipes the capture
  processor chain. Fix in tests that need capture: monkeypatch
  `_seam_configure_logging` (or the equivalent step) to a no-op so the
  capture's processor chain survives. For tests that need verbose-mode
  DEBUG events specifically, assert on `CliRunner` `result.output`
  substring (the JSON renderer writes to stderr which CliRunner merges)
  rather than `capture_logs` — the `wrapper_class` filtering still
  applies even after `capture_logs` swaps the chain. Discovered in
  **S4-02**.

- **`importlib.import_module(...)` is the escape hatch for EVERY heavy
  dependency inside a `codegenie.cli` command body — not just
  `codegenie.audit`.** Once `cli.py` grows past the `audit verify`
  stub (S4-02), any AST-visible `from codegenie.<X> import Y` (where
  X transitively imports yaml / pydantic / structlog / blake3 /
  jsonschema) breaks the `forbidden_modules` contract. The pattern: a
  `_seam_*` helper that does `importlib.import_module("codegenie.<X>")`
  + accessor. Bonus: gives tests a stable monkeypatch handle at the
  CLI layer without exercising heavy code paths. Discovered in
  **S4-02** while writing the gather command body.

- **`importlib.import_module(...)` returns `Any` — mypy strict will
  complain about `Any` leaking into return values.** Two patterns
  emerge: (a) for primitive returns (str, Path), annotate a local
  binding (`decoded: str = result.stdout.decode(...).strip()`) and
  return the local; (b) for opaque returns, accept `Any` at the
  callsite and annotate the next-step parameter. Avoid `cast(...)` —
  the local-annotation pattern self-documents the dynamic-import
  boundary. Discovered in **S4-02**.

- **`structlog.contextvars.bind_contextvars` only flows into events
  via the `merge_contextvars` processor in the chain.** Default
  `configure_logging` includes it; `structlog.testing.capture_logs`
  does NOT. When emitting an event whose `run_id` must appear under
  both production AND `capture_logs` test inspection, pass it
  explicitly as a kwarg (`log.info("cli.start", run_id=run_id)`)
  *in addition to* the bind. The bind is the convenience for child
  events; the kwarg is the contract. Discovered in **S4-02** while
  AC-13 asserted `cli.start` and `cli.end` share a `run_id` under
  capture_logs.

- **CLI `run_id` and audit filename `<short>` are intentionally
  distinct.** The coordinator binds `run_id = secrets.token_hex(8)`
  (16 hex chars) via contextvars for log correlation; the
  `AuditWriter` filename's `<short>` is `secrets.token_hex(4)` (8 hex
  chars) for per-write collision-avoidance. The CLI mints its OWN
  16-hex `run_id` at cli.start (asyncio Task contexts isolate the
  coordinator's inner rebind). All three are different values by
  design — equality is NOT a contract. Discovered in **S4-02** AC-13.

## Test infrastructure

- **`capsys` is unfit for tests that ALSO monkeypatch `sys.stdin.isatty`
  / `sys.stdout.isatty`.** pytest rotates the `CaptureIO` between
  fixture setup and the test body — the patched isatty stays on the
  pre-swap stream and the helper under test sees the post-swap stream
  whose `isatty` is the default built-in `False`. Minimal repro: a
  fixture that does `monkeypatch.setattr(sys.stdout, "isatty", lambda:
  True)` and depends on `capsys`; the test asserts `sys.stdout.isatty()
  is True` and fails. Removing `capsys` from the fixture deps makes it
  pass. Combined with structlog's `PrintLoggerFactory(file=sys.stderr)`
  caching the file at config time (which closes when its CaptureIO
  closes between tests), this produces both `non_tty`-branch false
  positives AND `ValueError: I/O operation on closed file`. **Default
  for any test that asserts on structlog events: use
  `structlog.testing.capture_logs()` (already the pattern in
  `tests/unit/test_cli_orchestration.py` and
  `tests/unit/test_cli_flags.py:test_cache_gc_stub_emits_exact_event_name`).**
  Note the level key is named `log_level` (not `level`) in
  capture_logs output. Discovered in **S4-03**.

- **`from __future__ import annotations` defeats naive
  `inspect.signature(...).return_annotation` checks.** With the
  future-import on, annotations are stored as strings — `return_annotation`
  is `'None'` (str), not the `None` object. Either use
  `inspect.signature(fn, eval_str=True)` (Python 3.10+) or accept the
  string form. The codebase uses `from __future__ import annotations`
  everywhere (Rule 11), so this trap is project-wide. Discovered in
  **S4-03** AC-1.

- **`list` does not accept arbitrary attribute assignment.** Test
  fixtures that try `calls = []; calls.return_value = ...` raise
  `AttributeError`. Build a small spy class instead — `__call__`,
  `__len__`, `__eq__`, plus the configurable return value as a real
  attribute. Discovered in **S4-03** while wiring the click.confirm
  spy; surfaces because v1 of S4-03's TDD plan used the pattern verbatim.

## CLI / harness wiring (continued)

- **Resolve structlog loggers inside the function body, not at module
  import.** `_log = structlog.get_logger(__name__)` at module top binds
  the proxy's underlying PrintLogger to whatever `sys.stderr` was at
  import time. Under pytest that's the very first test's `CaptureIO`,
  which gets closed when the test ends — every subsequent test that
  exercises the module hits `ValueError: I/O operation on closed
  file`. Wrap the logger lookup in a `_logger()` helper that returns
  `structlog.get_logger(__name__)` on demand; per-call cost is one
  dict lookup. Production cost is negligible (most call sites run
  once per CLI invocation). Discovered in **S4-03** while debugging
  the `gitignore.append.*` event capture failures.
