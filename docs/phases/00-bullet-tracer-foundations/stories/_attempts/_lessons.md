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
