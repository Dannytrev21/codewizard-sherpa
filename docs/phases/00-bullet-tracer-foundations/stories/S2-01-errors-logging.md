# Story S2-01 — Error hierarchy + structlog config

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0008, ADR-0012

## Context

This story plants the two cross-cutting primitives every later story in Phase 0 imports: the `CodegenieError` hierarchy and the `structlog` configuration. The exception subclasses encode the documented exit-code table (0/1/2/3/5/6) in the CLI and let every chokepoint (`exec.py`, `cache/store.py`, `output/sanitizer.py`, etc.) raise typed failures. The `probe.*` lifecycle event-name constants are the contract every later phase subscribes to — Phase 6's SHERPA state machine and Phase 13's cost ledger both attach to these names *unchanged*.

It is foundational: nothing else in Step 2 can compile without `errors.py`, and nothing in Steps 3–4 logs without `logging.py`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Harness engineering` — `structlog` JSON-on-non-TTY / pretty-on-TTY; lifecycle event-name constants are contract; `print()` is banned in `src/` (ruff `T201`).
  - `../phase-arch-design.md §Agentic best practices` — error-escalation hierarchy: `ConfigError`, `ToolMissingError`, `ProbeError`, `ProbeTimeoutError`, `CacheError`, `SchemaValidationError`, `SecretLikelyFieldNameError`, `DisallowedSubprocessError`, `SymlinkRefusedError`.
  - `../phase-arch-design.md §Component design — CLI` — exit-code table and `cli.unhandled` event.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — names `SecretLikelyFieldNameError` and `SymlinkRefusedError` as the typed failures emitted from sanitizer / writer chokepoints.
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — names `DisallowedSubprocessError` and `ToolMissingError` as the typed failures raised from `exec.run_allowlisted`.
- **Source design:**
  - `../High-level-impl.md §Step 1` — bullet listing the nine error subclasses and the `configure_logging(verbose)` callable signature.

## Goal

`from codegenie.errors import CodegenieError` and `from codegenie.logging import configure_logging, EVENT_PROBE_START` succeed; `configure_logging(verbose=False)` emits JSON on non-TTY stderr and pretty output on TTY.

## Acceptance criteria

- [ ] `src/codegenie/errors.py` exports `CodegenieError` and the nine subclasses listed in `../phase-arch-design.md §Agentic best practices` (each subclass inherits from `CodegenieError`, each carries a docstring naming the raise site).
- [ ] `src/codegenie/logging.py` exports `configure_logging(verbose: bool) -> None` plus the six `probe.*` event-name constants: `EVENT_PROBE_START`, `EVENT_PROBE_CACHE_HIT`, `EVENT_PROBE_SKIP`, `EVENT_PROBE_SUCCESS`, `EVENT_PROBE_FAILURE`, `EVENT_PROBE_TIMEOUT` (string values match `phase-arch-design.md §Harness engineering`: `"probe.start"`, `"probe.cache_hit"`, `"probe.skip"`, `"probe.success"`, `"probe.failure"`, `"probe.timeout"`).
- [ ] `configure_logging(verbose=False)` emits JSON-formatted output when `sys.stderr.isatty()` is `False` and pretty-formatted output when `True`; `verbose=True` switches level to `DEBUG`.
- [ ] `tests/unit/test_errors.py` asserts every named subclass exists, is a subclass of `CodegenieError`, and is exported in `errors.__all__`.
- [ ] `tests/unit/test_logging.py` asserts JSON vs pretty output via `capsys` + `monkeypatch.setattr(sys.stderr, "isatty", ...)`, asserts level becomes `DEBUG` under `verbose=True`, and asserts the six event-name constants resolve to the documented string values.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/errors.py` with `CodegenieError(Exception)` as the root plus the nine subclasses; declare `__all__` listing every public name; each subclass body is `"""<one-line raise-site description>"""` then `pass`.
2. Create `src/codegenie/logging.py` declaring the six event-name constants at module scope, then `configure_logging(verbose: bool)` that calls `structlog.configure(...)` with JSON renderer on non-TTY and `structlog.dev.ConsoleRenderer` on TTY; level via `logging.DEBUG if verbose else logging.INFO`.
3. Write the two test modules first (TDD red), confirm they fail with `ImportError`, then implement.
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py src/codegenie/logging.py`, `pytest tests/unit/test_errors.py tests/unit/test_logging.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_errors.py`, `tests/unit/test_logging.py`.

The errors test pins the *closure* of the hierarchy — adding or removing a subclass without an ADR rationale must fail CI.

```python
# tests/unit/test_errors.py
import codegenie.errors as e

EXPECTED_SUBCLASSES = {
    "ConfigError", "ToolMissingError", "ProbeError", "ProbeTimeoutError",
    "CacheError", "SchemaValidationError", "SecretLikelyFieldNameError",
    "DisallowedSubprocessError", "SymlinkRefusedError",
}

def test_codegenie_error_root_exists():
    # arrange: import the module
    # act/assert: CodegenieError is the root of the hierarchy
    assert issubclass(e.CodegenieError, Exception)

def test_every_subclass_inherits_codegenie_error():
    # arrange: enumerate the documented subclass names
    # act: resolve each name on the module
    # assert: each is a CodegenieError subclass and listed in __all__
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert issubclass(cls, e.CodegenieError)
        assert name in e.__all__
```

```python
# tests/unit/test_logging.py
import json
import logging
import sys
import structlog
import codegenie.logging as cgl

def test_event_name_constants_match_arch_doc():
    # The six probe.* event names are contract per phase-arch-design.md §Harness engineering.
    assert cgl.EVENT_PROBE_START == "probe.start"
    assert cgl.EVENT_PROBE_CACHE_HIT == "probe.cache_hit"
    assert cgl.EVENT_PROBE_SKIP == "probe.skip"
    assert cgl.EVENT_PROBE_SUCCESS == "probe.success"
    assert cgl.EVENT_PROBE_FAILURE == "probe.failure"
    assert cgl.EVENT_PROBE_TIMEOUT == "probe.timeout"

def test_configure_logging_json_on_non_tty(monkeypatch, capsys):
    # arrange: pretend stderr is not a tty
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    # act: emit a structured event
    structlog.get_logger().info("probe.start", probe="lang", run_id="abc")
    # assert: stderr output is JSON-parseable
    captured = capsys.readouterr().err
    payload = json.loads(captured.strip().splitlines()[-1])
    assert payload["event"] == "probe.start"
    assert payload["probe"] == "lang"
```

Run both; confirm `ImportError` / `AttributeError`. Commit as the red marker.

### Green — make it pass

`errors.py`: declare `class CodegenieError(Exception): """Root of the codegenie error hierarchy."""` then nine `class X(CodegenieError): """<raise site>"""` lines. Set `__all__ = ["CodegenieError", ...]` listing all ten names.

`logging.py`: declare the six string constants. Write `configure_logging` calling `structlog.configure(processors=[...], wrapper_class=structlog.make_filtering_bound_logger(level), logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))` where `processors` is `[structlog.processors.JSONRenderer()]` when non-TTY and the dev ConsoleRenderer when TTY.

### Refactor — clean up

- Add type hints (`configure_logging(verbose: bool) -> None`).
- Add module docstrings naming `phase-arch-design.md §Harness engineering` and `§Agentic best practices` as sources.
- Add a `Final` annotation to each event-name constant (`EVENT_PROBE_START: Final[str] = "probe.start"`).
- Confirm `ruff format` does not reflow the constant block; if it does, add `# fmt: off`/`# fmt: on` (last resort only).
- Confirm `mypy --strict src/codegenie/logging.py` is clean (`structlog` stubs may need `structlog>=24` from the `dev` extra).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | New file — `CodegenieError` root + nine subclass stubs |
| `src/codegenie/logging.py` | New file — `configure_logging` + six `probe.*` event-name constants |
| `tests/unit/test_errors.py` | New file — pins the subclass closure |
| `tests/unit/test_logging.py` | New file — JSON-on-non-TTY / pretty-on-TTY + constants |

## Out of scope

- **`exec.run_allowlisted` raising `DisallowedSubprocessError` / `ToolMissingError`** — handled by S2-04.
- **`OutputSanitizer.scrub` raising `SecretLikelyFieldNameError`** — handled by S3-03 (Step 3); the validator-side raise lives in S3-02.
- **Run-id injection on every structlog event** — the *bind* call lives wherever the run starts (CLI in S4-02); this story only ships `configure_logging` + the event-name constants.
- **`cli.unhandled` event** — the top-level CLI catch is wired in S4-02.

## Notes for the implementer

- Keep `errors.py` empty of behavior. No `__str__` overrides, no `__init__` signatures. Subclasses are *just* markers. Adding behavior later is cheap; removing it after Phase 1 consumers depend on it is not.
- The event-name constants are **strings**, not enum members. Phase 13's cost ledger and Phase 6's state ledger key off the *string value*. Don't switch to `enum.StrEnum` — even with `.value` access, breaking the import shape breaks downstream subscribers.
- `structlog.PrintLoggerFactory(file=sys.stderr)` is the right factory for tests because `capsys` captures `sys.stderr`. Don't use `structlog.WriteLoggerFactory()`; it goes to stdout by default and the JSON-vs-pretty test will misroute.
- Cross-cutting per the manifest's "Definition of done": `ruff format`, `ruff check`, `mypy --strict`. Don't override these locally; if the JSON renderer trips mypy, install `structlog`'s stub-bundled distribution from the `dev` extra (S1-02 wired it).
- Per `../phase-arch-design.md §Harness engineering`: never `print()` from `src/`. This story does not import `print`; if a debug-print sneaks in, ruff `T201` blocks the commit (S1-04 wired the hook).
- The `cli.unhandled` event mentioned in the arch doc is *not* a `probe.*` constant. Don't add a seventh constant for it here; that one is emitted ad-hoc by the CLI top-level catch (S4-02) and doesn't need to be a project-wide name.
