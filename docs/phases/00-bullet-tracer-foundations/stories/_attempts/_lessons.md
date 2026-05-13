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
