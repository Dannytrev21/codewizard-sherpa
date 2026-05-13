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
