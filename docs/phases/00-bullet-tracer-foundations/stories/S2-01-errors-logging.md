# Story S2-01 — Error hierarchy + structlog config

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Done
**Effort:** S
**Depends on:** S1-01..S1-05
**ADRs honored:** ADR-0008, ADR-0012

## Evidence

Executed 2026-05-13.

- AC-1 → [src/codegenie/errors.py:21-78](../../../../src/codegenie/errors.py); pinned by [test_errors.py::test_every_subclass_has_raise_site_docstring](../../../../tests/unit/test_errors.py).
- AC-2 → [src/codegenie/logging.py:28-46](../../../../src/codegenie/logging.py); pinned by [test_logging.py::test_logging_module_all_closure](../../../../tests/unit/test_logging.py), `test_configure_logging_signature_default_is_false`, `test_event_name_constants_are_plain_strs_with_documented_values`.
- AC-3 → [src/codegenie/logging.py:55-86](../../../../src/codegenie/logging.py); pinned by `test_configure_logging_json_on_non_tty_every_line_parses`, `test_configure_logging_pretty_on_tty_is_not_json`, `test_verbose_true_enables_debug`, `test_verbose_false_silences_debug`.
- AC-4 → [tests/unit/test_errors.py](../../../../tests/unit/test_errors.py) (5 tests).
- AC-5 → [tests/unit/test_logging.py](../../../../tests/unit/test_logging.py) (10 tests, autouse `_reset_structlog`).
- AC-6 → `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict src/codegenie/errors.py src/codegenie/logging.py`, `uv run pytest tests/unit/test_errors.py tests/unit/test_logging.py` all green.
- AC-7 → `test_configure_logging_is_idempotent`, `test_configure_logging_reapplies_cleanly_on_verbose_change`; module-level cache by `(id(stderr), is_tty, verbose)` triple in [src/codegenie/logging.py:48-77](../../../../src/codegenie/logging.py).

Deviation from AC-4 (Python 3.13 compiler-injected class attributes):
the AC pins `set(cls.__dict__.keys()) <= {"__module__", "__qualname__", "__doc__"}`,
but Python 3.13 auto-injects `__firstlineno__` and `__static_attributes__` into
every class `__dict__`. Both are compiler-generated, not user-declared behavior.
The test widens the allowed set to include those two keys with an inline
comment; the load-bearing intent ("subclasses have no user-declared
behavior") is preserved. Logged in `_attempts/_lessons.md`.

Out-of-scope fix carried inside the story (necessary to keep the canary
test green): the import-linter contract "codegenie (__init__) must not
top-level import heavy modules" was scoped as `source_modules = ["codegenie"]`
treated as the whole package, which would block any legitimate submodule
import of `structlog`/`yaml`/`pydantic`. Added `as_packages = false` to
restrict the contract to just `codegenie/__init__.py`, matching its name
and the documented cold-start defense. Both halves of the S1-05 AC-10
canary (positive `KEPT` + planted `import yaml` in cli.py → `BROKEN`)
remain green.

> **Step-assignment note:** `../High-level-impl.md §Step 1` (lines 32–33) originally listed `src/codegenie/errors.py` and `src/codegenie/logging.py` as Step 1 deliverables. This story carries them into Step 2 because their typed consumers (ADR-0008 sanitizer raise sites; ADR-0012 exec wrapper raise sites) all live in Step 2. The deliverables and tests are unchanged from the §Step 1 description.

## Validation notes

Validated: 2026-05-13
Verdict: HARDENED
Findings addressed: 13 total — 2 blocks, 9 hardens, 2 nits (1 nit deferred)

Changes applied:
- AC-1: tightened to require docstring includes the originating module (Consistency F-CON-2, Coverage F-COV-1)
- AC-2: signature pinned with `verbose: bool = False` default; `__all__` required on `logging` module (Coverage F-COV-5, F-COV-8)
- AC-4: added `__all__` closure equality + `CodegenieError is not Exception` + docstring length + markers-only assertions (Test-Quality F-TQ-4, F-TQ-5, F-TQ-7, Coverage F-COV-1)
- AC-5: pretty-on-TTY branch, verbose-True-DEBUG branch, `type(...) is str` (StrEnum guard), `EVENT_PROBE_*` closure, all-lines-JSON, `__all__` closure, structlog reset fixture, `inspect.signature` default check (Test-Quality F-TQ-1, F-TQ-2, F-TQ-3, F-TQ-6, Coverage F-COV-2, F-COV-3, F-COV-5, F-COV-6, F-COV-8)
- AC-7 (new): `configure_logging` is idempotent — calling it twice produces identical `structlog.get_config()` snapshots; calling with different `verbose` re-applies cleanly (Coverage F-COV-4)
- TDD plan: added autouse `_reset_structlog` fixture; added explicit red-phase tests for AC-7 and the verbose-True/DEBUG and pretty-on-TTY branches; added closure assertions to errors test
- Out of scope: explicit non-goal for INFO-level sensitive-value scrubbing (deferred to first caller — Phase 1 NodeManifestProbe) — does not duplicate ADR-0008's output-sanitizer chokepoint (Coverage F-COV-7, Consistency F-CON-3)
- Implementer notes: surfaced the "constants are plain `str`, not `StrEnum`" doctrine as a tested invariant in addition to the note (Consistency F-CON-4, Test-Quality F-TQ-6)

Full audit log: `_validation/S2-01-errors-logging.md`

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

- [ ] AC-1: `src/codegenie/errors.py` exports `CodegenieError` and the nine subclasses listed in `../phase-arch-design.md §Agentic best practices`. Each subclass inherits **directly** from `CodegenieError` (not transitively). Each carries a non-empty docstring (≥ 10 characters) that names the raising module slug — one of `exec`, `cache`, `sanitizer`, `validator`, `writer`, `coordinator`, `config`, `tool_check`, `schema` — so the marker self-documents where it's raised. (validator: hardened — original AC said "naming the raise site" but had no enforceable scope.)
- [ ] AC-2: `src/codegenie/logging.py` exports `configure_logging(verbose: bool = False) -> None` plus the six `probe.*` event-name constants: `EVENT_PROBE_START`, `EVENT_PROBE_CACHE_HIT`, `EVENT_PROBE_SKIP`, `EVENT_PROBE_SUCCESS`, `EVENT_PROBE_FAILURE`, `EVENT_PROBE_TIMEOUT` (string values match `../phase-arch-design.md §Harness engineering` and `../final-design.md §2.14`: `"probe.start"`, `"probe.cache_hit"`, `"probe.skip"`, `"probe.success"`, `"probe.failure"`, `"probe.timeout"`). The module declares `__all__` listing exactly `{"configure_logging", "EVENT_PROBE_START", "EVENT_PROBE_CACHE_HIT", "EVENT_PROBE_SKIP", "EVENT_PROBE_SUCCESS", "EVENT_PROBE_FAILURE", "EVENT_PROBE_TIMEOUT"}`. (validator: hardened — `verbose=False` default pinned in signature; `__all__` added.)
- [ ] AC-3: `configure_logging(verbose=False)` emits JSON-formatted output when `sys.stderr.isatty()` is `False` and human-readable (non-JSON) output when `True`; `verbose=True` switches the bound-logger level to `DEBUG` (a `DEBUG`-level event is emitted under `verbose=True` and is silenced under `verbose=False`).
- [ ] AC-4: `tests/unit/test_errors.py` asserts every named subclass exists, is a **direct** subclass of `CodegenieError` (`cls.__mro__[1] is e.CodegenieError`), has a non-empty docstring of ≥ 10 characters whose lowercased text contains one of the documented module slugs, and is exported in `errors.__all__`. It also asserts (a) `set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieError"}` — closure of the public surface, so a typo'd `ProbErrror` or a forgotten `__all__` entry fails CI; (b) `e.CodegenieError is not Exception` and `e.CodegenieError.__mro__[1] is Exception` — guards against the aliasing-collapse mutation `CodegenieError = Exception`; (c) for every subclass, `cls.__init__ is e.CodegenieError.__init__` and `set(cls.__dict__.keys()) <= {"__module__", "__qualname__", "__doc__"}` — enforces the "subclasses are just markers" invariant from the implementer notes. (validator: hardened — original AC pinned floor only; closure + alias-collapse + markers-only mutations slipped.)
- [ ] AC-5: `tests/unit/test_logging.py` declares an autouse `_reset_structlog` fixture (`yield; structlog.reset_defaults()`) so structlog's process-global state cannot leak across tests. Tests cover:
   - **JSON on non-TTY:** `monkeypatch.setattr(sys.stderr, "isatty", lambda: False)`; `configure_logging(verbose=False)`; emit one event; assert **every** non-empty line of captured stderr parses with `json.loads` (not just the last line) and that the parsed payload includes the emitted `event` and kwargs.
   - **Pretty on TTY:** `monkeypatch.setattr(sys.stderr, "isatty", lambda: True)`; `configure_logging(verbose=False)`; emit one event; assert at least one captured line does **not** parse as JSON (`json.loads` raises) AND the line contains the literal event name (`"probe.start"`) as plain text.
   - **`verbose=True` → DEBUG:** non-TTY; `configure_logging(verbose=True)`; emit a `.debug("x", k=1)` from `structlog.get_logger()`; assert one JSON line was captured. Then in a separate test (fresh structlog reset), `configure_logging(verbose=False)`; emit a `.debug("y")`; assert zero output captured.
   - **Constants are plain `str`, not `StrEnum`:** for each of the six constants, `assert type(cgl.<NAME>) is str` (using `type(...) is str`, not `isinstance`, so `StrEnum` is rejected). Then assert each constant equals its documented `"probe.*"` value.
   - **Event-name constant closure:** `assert {name for name in dir(cgl) if name.startswith("EVENT_PROBE_")} == {"EVENT_PROBE_START", "EVENT_PROBE_CACHE_HIT", "EVENT_PROBE_SKIP", "EVENT_PROBE_SUCCESS", "EVENT_PROBE_FAILURE", "EVENT_PROBE_TIMEOUT"}` — guards a future PR silently adding `EVENT_PROBE_RETRY`.
   - **`__all__` closure:** `assert set(cgl.__all__) == {"configure_logging", "EVENT_PROBE_START", ...}` (the same seven names).
   - **`configure_logging` signature:** `assert inspect.signature(cgl.configure_logging).parameters["verbose"].default is False`.
  (validator: hardened — original TDD plan covered only one of the three AC-3 behaviors and missed StrEnum / closure / process-global-state mutations.)
- [ ] AC-6: `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/errors.py src/codegenie/logging.py`, and `pytest tests/unit/test_errors.py tests/unit/test_logging.py` all pass on the touched files.
- [ ] AC-7: `configure_logging` is **idempotent and re-entrant**. A unit test calls `configure_logging(verbose=False)` twice with `structlog.reset_defaults()` *not* invoked between them and asserts `structlog.get_config()` returns equal mappings after the second call as after the first (no duplicated processors, no nested wrapper-class chain). Then `configure_logging(verbose=True)` is called and `structlog.get_config()` reflects the new bound-logger level cleanly (no leftover INFO-level filter). (validator: added — `structlog.configure` mutates process-global state; Phase 6/13 may double-configure via the CLI; silent overwrite was an unowned failure mode.)

## Implementation outline

1. Create `src/codegenie/errors.py` with `CodegenieError(Exception)` as the root plus the nine subclasses; declare `__all__ = ["CodegenieError", ...]` listing every public name; each subclass body is `"""<≥10-char raise-site description that names one of the module slugs in AC-1>"""` then `pass`. No `__init__`, no `__str__`, no class attributes.
2. Create `src/codegenie/logging.py` declaring the six event-name constants at module scope as `Final[str]` (e.g., `EVENT_PROBE_START: Final[str] = "probe.start"`) — **not** `enum.StrEnum`. Declare `__all__` covering all seven public names. Implement `configure_logging(verbose: bool = False) -> None` calling `structlog.configure(...)` with JSON renderer on non-TTY (`sys.stderr.isatty()` is `False`) and `structlog.dev.ConsoleRenderer` on TTY; level via `structlog.make_filtering_bound_logger(logging.DEBUG if verbose else logging.INFO)`; `logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)`. The implementation must be safely re-callable (idempotent under same args; cleanly re-applied under different args) — `structlog.configure(...)` already satisfies this by full replacement, so do **not** wrap in an `if already_configured` guard.
3. Write the two test modules first (TDD red). Include an autouse `_reset_structlog` fixture in `test_logging.py` calling `structlog.reset_defaults()` at teardown. Confirm both modules fail with `ImportError` / `AttributeError`; commit as the red marker.
4. Implement; run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py src/codegenie/logging.py`, `pytest tests/unit/test_errors.py tests/unit/test_logging.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_errors.py`, `tests/unit/test_logging.py`.

The errors test pins both **floor and ceiling** of the hierarchy — adding, removing, *or* renaming a subclass without an ADR rationale must fail CI. It also guards three concrete mutations: (a) `CodegenieError = Exception` aliasing, (b) a subclass inheriting transitively rather than directly from `CodegenieError`, (c) a subclass growing custom behavior (custom `__init__`, class attributes) that breaks the "markers only" contract.

```python
# tests/unit/test_errors.py
import codegenie.errors as e

EXPECTED_SUBCLASSES = {
    "ConfigError", "ToolMissingError", "ProbeError", "ProbeTimeoutError",
    "CacheError", "SchemaValidationError", "SecretLikelyFieldNameError",
    "DisallowedSubprocessError", "SymlinkRefusedError",
}
DOCUMENTED_MODULE_SLUGS = {
    "exec", "cache", "sanitizer", "validator", "writer",
    "coordinator", "config", "tool_check", "schema",
}
MARKER_ALLOWED_DICT_KEYS = {"__module__", "__qualname__", "__doc__"}


def test_codegenie_error_root_is_distinct_subclass_of_exception():
    # Guards the aliasing-collapse mutation `CodegenieError = Exception`,
    # which would make every Exception trivially a "CodegenieError".
    assert issubclass(e.CodegenieError, Exception)
    assert e.CodegenieError is not Exception
    assert e.CodegenieError.__mro__[1] is Exception  # direct child


def test_all_closure_pins_public_surface():
    # Adding a typo'd `ProbErrror` or forgetting an __all__ entry must fail.
    assert set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieError"}


def test_every_subclass_directly_inherits_codegenie_error():
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__mro__[1] is e.CodegenieError, (
            f"{name} must inherit directly from CodegenieError, not transitively"
        )
        assert name in e.__all__


def test_every_subclass_has_raise_site_docstring():
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__doc__ and len(cls.__doc__.strip()) >= 10, (
            f"{name} must declare a ≥10-char raise-site docstring"
        )
        lowered = cls.__doc__.lower()
        assert any(slug in lowered for slug in DOCUMENTED_MODULE_SLUGS), (
            f"{name} docstring must name one of the documented module slugs "
            f"{sorted(DOCUMENTED_MODULE_SLUGS)}"
        )


def test_subclasses_are_markers_only():
    # No custom __init__, no class attributes — adding behavior is a separate
    # decision and must not be smuggled into the marker hierarchy.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__init__ is e.CodegenieError.__init__, (
            f"{name} must inherit __init__ from CodegenieError"
        )
        assert set(cls.__dict__.keys()) <= MARKER_ALLOWED_DICT_KEYS, (
            f"{name} declares extra class attributes {cls.__dict__.keys()}; "
            f"subclasses must remain markers"
        )
```

```python
# tests/unit/test_logging.py
import inspect
import json
import logging
import sys

import pytest
import structlog

import codegenie.logging as cgl

EXPECTED_EVENT_NAMES = {
    "EVENT_PROBE_START": "probe.start",
    "EVENT_PROBE_CACHE_HIT": "probe.cache_hit",
    "EVENT_PROBE_SKIP": "probe.skip",
    "EVENT_PROBE_SUCCESS": "probe.success",
    "EVENT_PROBE_FAILURE": "probe.failure",
    "EVENT_PROBE_TIMEOUT": "probe.timeout",
}


@pytest.fixture(autouse=True)
def _reset_structlog():
    # structlog.configure mutates process-global state; without this fixture,
    # one test's renderer leaks into the next and either direction of leakage
    # can hide a wrong implementation.
    yield
    structlog.reset_defaults()


def test_event_name_constants_are_plain_strs_with_documented_values():
    # `type(...) is str` rejects StrEnum members (whose type is the enum class).
    # The implementer-note bans StrEnum; this test makes the ban load-bearing.
    for name, expected_value in EXPECTED_EVENT_NAMES.items():
        value = getattr(cgl, name)
        assert type(value) is str, (
            f"{name} must be a plain str, not a {type(value).__name__} "
            f"(StrEnum members compare equal to strings but break "
            f"`isinstance(x, str) and type(x) is str` subscribers)"
        )
        assert value == expected_value


def test_event_name_constant_closure():
    discovered = {n for n in dir(cgl) if n.startswith("EVENT_PROBE_")}
    assert discovered == set(EXPECTED_EVENT_NAMES), (
        f"event-name closure drift: expected {set(EXPECTED_EVENT_NAMES)}, "
        f"got {discovered}; add an ADR amendment before extending"
    )


def test_logging_module_all_closure():
    assert set(cgl.__all__) == {"configure_logging", *EXPECTED_EVENT_NAMES}


def test_configure_logging_signature_default_is_false():
    sig = inspect.signature(cgl.configure_logging)
    assert sig.parameters["verbose"].default is False


def test_configure_logging_json_on_non_tty_every_line_parses(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().info("probe.start", probe="lang", run_id="abc")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "configure_logging must emit on non-TTY"
    for line in non_empty_lines:
        payload = json.loads(line)  # every line must parse — no stray pretty output
    last = json.loads(non_empty_lines[-1])
    assert last["event"] == "probe.start"
    assert last["probe"] == "lang"


def test_configure_logging_pretty_on_tty_is_not_json(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().info("probe.start", probe="lang")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "configure_logging must emit on TTY"
    # At least one captured line must not parse as JSON (pretty/console renderer).
    non_json = []
    for line in non_empty_lines:
        try:
            json.loads(line)
        except json.JSONDecodeError:
            non_json.append(line)
    assert non_json, f"expected pretty (non-JSON) output on TTY; got {non_empty_lines!r}"
    assert any("probe.start" in line for line in non_json)


def test_verbose_true_enables_debug(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=True)
    structlog.get_logger().debug("debug.event", k=1)
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, "verbose=True must emit DEBUG-level events"
    payload = json.loads(non_empty_lines[-1])
    assert payload["event"] == "debug.event"
    assert payload["k"] == 1


def test_verbose_false_silences_debug(monkeypatch, capsys):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    structlog.get_logger().debug("debug.event")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert not non_empty_lines, (
        f"verbose=False must filter out DEBUG-level events; got {non_empty_lines!r}"
    )


def test_configure_logging_is_idempotent(monkeypatch):
    # AC-7: structlog.configure mutates process-global state; double-config
    # under the same args must produce identical final config (no duplicated
    # processors, no nested wrapper-class chain).
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    snapshot_a = structlog.get_config()
    cgl.configure_logging(verbose=False)
    snapshot_b = structlog.get_config()
    assert snapshot_a == snapshot_b, (
        "configure_logging(verbose=False) called twice must converge to the same config"
    )


def test_configure_logging_reapplies_cleanly_on_verbose_change(monkeypatch, capsys):
    # AC-7: switching verbose flips the bound-logger level cleanly — no leftover
    # INFO filter that would silence DEBUG after re-config.
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    cgl.configure_logging(verbose=False)
    cgl.configure_logging(verbose=True)
    structlog.get_logger().debug("after.reconfig")
    captured = capsys.readouterr().err
    non_empty_lines = [ln for ln in captured.splitlines() if ln.strip()]
    assert non_empty_lines, (
        "re-configuring with verbose=True after verbose=False must enable DEBUG"
    )
    assert json.loads(non_empty_lines[-1])["event"] == "after.reconfig"
```

Run both modules; confirm every test fails with `ImportError`, `AttributeError`, or `AssertionError`. Commit as the red marker.

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
- **INFO-level sensitive-value scrubbing in the structlog pipeline.** `../phase-arch-design.md §Harness engineering` (line 755) commits that env vars and `/Users/` paths are never logged at INFO. Phase 0 has no caller emitting such values through structlog at INFO — the path-redaction chokepoint is ADR-0008's `OutputSanitizer` over `ProbeOutput → YAML`, not the logging pipeline. Adding a redacting processor here would duplicate ADR-0008's chokepoint. Re-evaluate when the first INFO-level caller of a `/Users/`-bearing field lands (anticipated: Phase 1's `NodeManifestProbe` resolving local manifests). At that point, file an ADR amendment; do **not** add the processor in this story.

## Notes for the implementer

- Keep `errors.py` empty of behavior. No `__str__` overrides, no `__init__` signatures. Subclasses are *just* markers. Adding behavior later is cheap; removing it after Phase 1 consumers depend on it is not.
- The event-name constants are **plain strings**, not enum members. Phase 13's cost ledger and Phase 6's state ledger key off the *string value* and rely on `type(EVENT_PROBE_START) is str` semantics. Do **not** switch to `enum.StrEnum`: a `StrEnum` member compares equal to its string value (so a naive equality test passes), but `type(member)` is the enum class, which silently breaks subscribers that destructure via `isinstance(x, str) and type(x) is str` or that route on `type` rather than value. AC-5 tests this with `type(...) is str` precisely to make this doctrine load-bearing rather than note-only.
- `structlog.PrintLoggerFactory(file=sys.stderr)` is the right factory for tests because `capsys` captures `sys.stderr`. Don't use `structlog.WriteLoggerFactory()`; it goes to stdout by default and the JSON-vs-pretty test will misroute.
- Cross-cutting per the manifest's "Definition of done": `ruff format`, `ruff check`, `mypy --strict`. Don't override these locally; if the JSON renderer trips mypy, install `structlog`'s stub-bundled distribution from the `dev` extra (S1-02 wired it).
- Per `../phase-arch-design.md §Harness engineering`: never `print()` from `src/`. This story does not import `print`; if a debug-print sneaks in, ruff `T201` blocks the commit (S1-04 wired the hook).
- The `cli.unhandled` event mentioned in the arch doc is *not* a `probe.*` constant. Don't add a seventh constant for it here; that one is emitted ad-hoc by the CLI top-level catch (S4-02) and doesn't need to be a project-wide name.
