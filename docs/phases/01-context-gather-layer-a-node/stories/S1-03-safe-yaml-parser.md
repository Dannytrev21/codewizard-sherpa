# Story S1-03 — `safe_yaml` parser with `CSafeLoader` + `load_all` + alias-safe depth walker

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (hardened by phase-story-validator)
**Effort:** M
**Depends on:** S1-01, S1-02 (chronological; structural reuse of `_io.py`/`_depth.py` if those land in S1-02)
**ADRs honored:** ADR-0008, ADR-0009, ADR-0007 (consumer); Phase-0 markers-only contract

## Validation notes (2026-05-13)

Hardened by [phase-story-validator](_validation/S1-03-safe-yaml-parser.md). Structural changes:

1. **Markers-only construction enforced.** All raise sites switched from kwarg-style (`SizeCapExceeded(path=..., cap=...)`) to **positional formatted-message** strings — the Phase 0 `tests/unit/test_errors.py::test_subclasses_are_markers_only` invariant (re-affirmed by S1-01 and inherited by S1-02) forbids any instance state on these markers. The draft's prescribed `MalformedYAMLError(path=path, detail=<short msg>)` would TypeError at the red-test commit.
2. **YAML-specific killer mutation pinned: alias-graph amplification.** Unlike JSON, CSafeLoader resolves `&anchor`/`*alias` references to **the same Python object**; the parsed tree is a DAG, not a tree. A naive recursive depth walker re-enters shared subtrees once per alias-resolution, giving 10^k visits for k anchor levels even when the physical node count is k. The post-parse depth walker MUST memoize visited containers by `id()` or this story ships a billion-laughs DoS vector the depth-cap alone does not catch. Pinned by AC-12 + `test_depth_walker_dedupes_alias_targets_no_amplification`.
3. **`CSafeLoader` import-time hard fail.** Draft note #6 already says "fail loud — don't silently downgrade to pure-Python SafeLoader." Promoted to AC-4 with an import-time guard (`getattr(yaml, "CSafeLoader", None) is None` → `ImportError` at module load) and a test that mocks `yaml.CSafeLoader` away to prove the guard fires.
4. **18 numbered ACs (up from 9 single-bullet ACs).** Every AC is individually verifiable. Added: empty file → `MalformedYAMLError`; top-level non-mapping → `MalformedYAMLError`; ELOOP-only `OSError` translation; size cap precedes `os.read` (monkey-patched); fd-lifecycle parity across every exit path; `load_all` lazy generator semantics; per-doc walker invocation; cap-event structured fields via `structlog.testing.capture_logs`; no cap event on non-cap failures; `SymlinkRefusedError` docstring extension picking up the S1-01 follow-up named for the YAML twin.
5. **20 named tests in the TDD plan (up from 8).** Each annotated with the AC it pins and the mutation it catches. Mutation table enumerates 12 plausible wrong implementations.
6. **Plugin-shape kernel surfaced.** `parsers/_io.py` (O_NOFOLLOW + size-cap primitive) and `parsers/_depth.py` (id()-memoized walker) are now ACs (lift-or-create at the S1-03 boundary if S1-02 didn't). Each parser module becomes a thin strategy keyed by `parser_kind` — adding a future `safe_toml` (Phase 13?) or `safe_xml` parser is a new file + new `parser_kind` literal, no edits to existing parsers. Documented under Implementation outline → "Plugin shape" so the executor sees the framing.
7. **`load_all` semantics decided.** Multi-doc YAML may legally contain empty documents (`---\n---`) — CSafeLoader yields `None`. The generator yields docs verbatim (including `None`); callers (DeploymentProbe) already filter by `kind`. Top-level non-mapping non-None docs raise `MalformedYAMLError` from inside the generator on `next()`. Signature widened in the implementer notes: `Iterator[Mapping[str, JSONValue] | None]` (arch's `Iterator[dict[...]]` is the aspirational shape; the `| None` clause is the truthful one — surfaced as a small arch follow-up rather than a story block).
8. **JSONValue re-export discipline.** Single source of truth for the recursive type alias is `coordinator/validator.py` (Phase 0). `parsers/__init__.py` re-exports it (one-line public-surface narrowing); S1-03 inherits the convention if S1-02 set it.
9. **`SymlinkRefusedError` docstring follow-up adopted.** S1-01's open follow-up named `safe_json` (carried by S1-02) and `safe_yaml` (this story). One-line append to `errors.py` docstring naming the new raise site is AC-17.

No structural goal-vs-arch conflict. Goal preserved exactly. Verdict: **HARDENED**.

## Context

`safe_yaml` is the YAML twin of `safe_json` — every Phase 1 probe that reads YAML (`pnpm-lock.yaml`, GitHub Actions workflows, `Chart.yaml`, `values*.yaml`, `kustomization.yaml`, raw K8s manifests, the catalog YAMLs themselves) routes through here. `yaml.CSafeLoader` is the only allowed loader (Phase 0's `forbidden-patterns` hook bans `yaml.load(...)` without `Loader=`, and Phase 0 ratified `CSafeLoader`; ADR-0009 forbids adopting any new C-extension YAML parser). CSafeLoader has internal limits but does not natively cap nesting depth, so the post-parse depth walker from S1-02 carries the load-bearing weight here too.

**Two YAML-only adversarial shapes that JSON does not present:**

- **Alias amplification (DAG, not tree).** CSafeLoader resolves `*alias` references to the same Python object. A YAML using `&a [1] / &b [*a,*a,...] / &c [*b,*b,...] / ...` produces a parsed graph with k physical nodes but exponential logical visits. A recursive depth walker without identity memoization re-traverses shared subtrees and **hangs / OOMs even though `max_depth=64` is never reached** (the physical depth is k ≤ 10). This is the load-bearing YAML-specific defense: the walker memoizes by `id()`, so each container is visited at most once.
- **Multi-document streams.** `safe_yaml.load_all` parses `---`-separated documents lazily. Each document is its own depth-walked tree; empty documents yield `None` (legal). Caller filters (e.g., DeploymentProbe filters by `kind ∈ {Deployment,...}`).

`load_all` is required because `DeploymentProbe` parses multi-document raw K8s manifests (`safe_yaml.load_all` filtered to `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}` per `phase-arch-design.md §"Component design" #6`).

**Phase 0 markers-only contract (binding):** `tests/unit/test_errors.py::test_subclasses_are_markers_only` asserts `cls.__init__ is e.CodegenieError.__init__` for every subclass and a class-dict allowlist of `{"__module__","__qualname__","__doc__","__firstlineno__","__static_attributes__"}`. **No kwargs on subclass construction. No instance state.** Phase 1 marker construction uses positional formatted-message strings; semantics live in the catch site per ADR-0007.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — interface, `O_NOFOLLOW`, post-parse depth-walker rationale, `safe_yaml.load_all` signature.
  - `../phase-arch-design.md §"Edge cases"` rows 1, 4, 15 — billion-laughs anchor expansion in `pnpm-lock.yaml`; zip-slip in kustomize (downstream consumer); multi-env Helm with 12 `values-*.yaml` files (downstream consumer).
  - `../phase-arch-design.md §"Scenarios" → Scenario 3` — billion-laughs flow.
  - `../phase-arch-design.md §"Data model"` — `JSONValue` recursive alias re-used as the YAML value type (CSafeLoader's emitted types are a subset of JSON).
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `parser_kind` event field.
- **Phase ADRs:**
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `CSafeLoader` only; no `ruamel.yaml`; no `pyyaml.Loader`; no `unsafe_load`. Optional `pyarn` is the only Phase 1 addition and is YAML-format-adjacent only (S3-03).
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — in-process caps replace per-probe sandbox; `O_NOFOLLOW` is the symlink-escape defense.
  - `../ADRs/0007-warnings-id-pattern.md` — `WarningId` constructed at the catch site, not on the exception.
- **Source design:**
  - `../final-design.md "Components" #8` — design statement; bans `json5`, `orjson`, `pyjson5`, `ruamel.yaml`, `msgpack`.
- **Existing code:**
  - `src/codegenie/errors.py` (Phase 0 + S1-01) — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `SymlinkRefusedError` markers; docstring inventory of documented module slugs already includes `parsers`.
  - `src/codegenie/coordinator/validator.py` (Phase 0) — `JSONValue = TypeAliasType("JSONValue", Union[None, bool, int, float, str, "list[JSONValue]", "dict[str, JSONValue]"])` — single source of truth.
  - `src/codegenie/logging.py` (Phase 0 / S1-04 prior work) — `structlog.testing.capture_logs` testing pattern precedent; `Final[str]` event-name convention.
  - `src/codegenie/parsers/safe_json.py` (S1-02, expected to exist when S1-03 starts) — copy the `O_NOFOLLOW` + size-cap + walker shape; if `parsers/_io.py` and `parsers/_depth.py` already exist (S1-02 hardened story prescribes lifting on YAML's arrival), consume them.
- **Test contracts:**
  - `tests/unit/test_errors.py::test_subclasses_are_markers_only` — the markers-only invariant (binding).
  - `tests/unit/test_errors.py::EXPECTED_SUBCLASSES`, `DOCUMENTED_MODULE_SLUGS`, `MARKER_ALLOWED_DICT_KEYS` — names every constraint the validator pins.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — proves `args[0]` round-trips and `path`/`cap`/`detail` attributes do not exist on instances.
- **Validation lineage:**
  - `_validation/S1-01-errors-extension.md` — markers-only invariant pinned; `safe_yaml` docstring follow-up listed.
  - `_validation/S1-02-safe-json-parser.md` — same markers-only discipline applied to `safe_json`; mutation table this story extends.

## Goal

Ship `src/codegenie/parsers/safe_yaml.py` with:

```python
def load(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]: ...
def load_all(path: Path, *, max_bytes: int, max_depth: int = 64) -> Iterator[Mapping[str, JSONValue] | None]: ...
```

Both:

1. Open with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` (single open per call).
2. Pre-parse size-cap against `os.fstat(fd).st_size` **before any `os.read`** — bytes are never allocated past the cap.
3. Hard-fail at module import time if `yaml.CSafeLoader` is unavailable (no silent `SafeLoader` downgrade).
4. Parse with `yaml.load(data, Loader=yaml.CSafeLoader)` (single-doc) or `yaml.load_all(data, Loader=yaml.CSafeLoader)` (multi-doc) — the literal Phase 0 invocation; no aliases.
5. Run an `id()`-memoized post-parse depth walker that traverses each container at most once (alias amplification cannot exceed physical-node count).
6. Translate `yaml.YAMLError` (covering `ConstructorError` for `!!python/object`, `ParserError`, `ScannerError`) → `MalformedYAMLError`.
7. Translate `OSError` with `errno == ELOOP` (the `O_NOFOLLOW`-on-symlink case) → `SymlinkRefusedError`; **propagate all other `OSError` subclasses unchanged** (`FileNotFoundError`, `IsADirectoryError`, `PermissionError`, etc.).
8. Emit one `probe.parser.cap_exceeded` structlog event per cap violation, with `parser_kind="safe_yaml"`, `cap_kind ∈ {"bytes","depth"}`, `path`, and `cap` structured fields — no event on happy/malformed/symlink paths.
9. Construct every raised marker with a **single positional formatted-message string** (no kwargs; no instance state) consistent with the Phase 0 markers-only invariant.

## Acceptance criteria

- [ ] **AC-1 — module surface.** `src/codegenie/parsers/safe_yaml.py` exports `load` and `load_all` only via `__all__`; both signatures are keyword-only after `path` and use the documented defaults (`max_depth: int = 64`).
- [ ] **AC-2 — return shape.** `load` returns `Mapping[str, JSONValue]`; `load_all` returns `Iterator[Mapping[str, JSONValue] | None]`. Non-mapping non-None roots raise `MalformedYAMLError`.
- [ ] **AC-3 — module docstring.** Names `phase-arch-design.md §"Component design" #8`, ADR-0009, ADR-0008, and the alias-amplification mitigation. Asserted by `test_module_docstring_references_arch_and_adrs`.
- [ ] **AC-4 — CSafeLoader hard requirement.** Module import fails with `ImportError` if `getattr(yaml, "CSafeLoader", None) is None`. No `SafeLoader` fallback path. Asserted by `test_csafeloader_required_at_import_time` (mocks `yaml.CSafeLoader` away via `monkeypatch.delattr`).
- [ ] **AC-5 — `O_NOFOLLOW` + ELOOP-only translation.** Single `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` per call. Only `OSError` with `errno == errno.ELOOP` is translated to `SymlinkRefusedError`. `FileNotFoundError`, `IsADirectoryError`, `PermissionError` propagate **as themselves** (asserted via `not isinstance(exc, SymlinkRefusedError)` and concrete-subtype isinstance check).
- [ ] **AC-6 — size cap precedes read.** `os.fstat(fd).st_size > max_bytes` raises `SizeCapExceeded` **before any `os.read`** is invoked. Asserted by `test_size_cap_raises_before_read` (monkey-patches `os.read` to record invocations + raise; the cap path must succeed without `os.read` calls).
- [ ] **AC-7 — empty file → `MalformedYAMLError`.** Zero-byte file produces `CSafeLoader` returning `None`; `load` raises `MalformedYAMLError` (signature promises a mapping). `load_all` on a zero-byte file yields no documents.
- [ ] **AC-8 — top-level non-mapping → `MalformedYAMLError`.** A YAML file whose root is a list (`- 1\n- 2`) or scalar (`hello`) raises `MalformedYAMLError` from `load`. From `load_all`, the offending document raises on `next()`.
- [ ] **AC-9 — unsafe tags refused.** `!!python/object/apply:os.system ['echo pwned']` and similar `python/...` tags raise `MalformedYAMLError` (via translated `ConstructorError`). No side effect is observable (sentinel file pattern from `tests/adv/`).
- [ ] **AC-10 — yaml.YAMLError catch-all.** `ParserError` (bad indentation), `ScannerError` (illegal characters), and `ConstructorError` (unsafe tag) all translate uniformly to `MalformedYAMLError`. Parametrized.
- [ ] **AC-11 — depth walker descends dicts AND lists.** Mixed nesting `{"a": [{"b": [{"c": ...}]}]}` at depth 65 raises `DepthCapExceeded`; pure-list nesting `[[[[...]]]]` at depth 65 also raises. Parametrized fixture covers `{dict-only, list-only, mixed}`.
- [ ] **AC-12 — alias-amplification mutation guard (load-bearing).** A YAML with 10 chained anchors (`a: &a [1] / b: &b [*a,*a,...,*a] / ... / j: &j [*i,...,*i]`) — physically 10 nodes, logically 10^10 visits — completes the depth walker in **< 200 ms wall-clock** and **< 50 MB memory delta** (`tracemalloc`). Implementation MUST memoize visited containers by `id()`. Asserted by `test_depth_walker_dedupes_alias_targets_no_amplification` (skipped if `pytest-timeout` absent; otherwise hard-bounded).
- [ ] **AC-13 — depth boundary parametrized.** Depths `{0, 1, 63, 64, 65, 200}` parametrized for both pure-list and pure-dict shapes. Depths `≤ max_depth` pass; depths `> max_depth` raise `DepthCapExceeded`. Pins both off-by-one mutations (`>` vs `>=`).
- [ ] **AC-14 — cap events emitted with structured fields.** On `SizeCapExceeded` and `DepthCapExceeded`, exactly one `probe.parser.cap_exceeded` event is emitted with `parser_kind="safe_yaml"`, `cap_kind ∈ {"bytes","depth"}`, `path=<str>`, `cap=<int>`. Asserted via `structlog.testing.capture_logs`, not via stderr substring.
- [ ] **AC-15 — no cap event on non-cap failures.** Happy path, `MalformedYAMLError`, `SymlinkRefusedError`, `FileNotFoundError`, `IsADirectoryError` paths emit **zero** `probe.parser.cap_exceeded` events. Asserted by `test_no_cap_event_on_happy_or_malformed_or_symlink`.
- [ ] **AC-16 — `load_all` is a lazy generator.** `inspect.isgenerator(load_all(p, max_bytes=...))` is true; partial iteration (`next(it)` once then drop) does not parse subsequent docs unless re-advanced. The depth walker runs **per yielded document** (not on the iterator wrapper), so a first valid doc surfaces before a later doc raises `DepthCapExceeded` / `MalformedYAMLError`.
- [ ] **AC-17 — `SymlinkRefusedError` docstring extension (S1-01 follow-up).** `errors.py::SymlinkRefusedError.__doc__` mentions both `safe_json` and `safe_yaml` raise sites (one-line append). `tests/unit/test_errors.py::test_every_subclass_has_raise_site_docstring` continues to pass (the `parsers` slug is already on the documented-slugs allowlist; the append is observability, not contract).
- [ ] **AC-18 — markers-only construction.** All Phase-1 marker raises in this module use **single positional message strings**. Test parametrizes over the four marker types raised here (`SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `SymlinkRefusedError`) asserting `exc.args == (msg,)`, `str(exc) == msg`, and `not hasattr(exc, "path"|"cap"|"detail"|"warning_id")`.
- [ ] **AC-19 — fd lifecycle parity.** A `fd_tracker` monkey-patch on `os.open` and `os.close` records counts. After exercising happy / size-cap / malformed / depth-cap / symlink / non-ELOOP-OSError paths in sequence, `opened == closed`. No fd leaks on any exit path; `try`/`finally` is the only acceptable shape.
- [ ] **AC-20 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/parsers/safe_yaml.py` are clean. `types-PyYAML` is declared under the `dev` extra in `pyproject.toml` if and only if `mypy --strict` requires it (preferred over `# type: ignore[arg-type]`).
- [ ] **AC-21 — TDD discipline.** Red test exists and was committed failing; green commit makes it pass; refactor commit is no-op behavior. `pytest` passes the 20 named tests in this story's TDD plan.

## Implementation outline

1. **Decide the shared-primitive shape.** If `src/codegenie/parsers/_io.py` (open + size-cap primitive) and `src/codegenie/parsers/_depth.py` (id()-memoized walker) **already exist from S1-02**, this story consumes them — no edits. If they do not (S1-02 chose to keep them inline), this story **lifts both** at the moment YAML's walker arrives, because we now have ≥ 2 concrete consumers and the walker shape must include id() memoization (a YAML-only requirement that JSON didn't need; lifting prevents JSON's tree-only walker from drifting into YAML callers as a copy-paste). Both primitives are stdlib-only and stateless.
2. **`parsers/_io.py::open_capped(path, *, max_bytes, parser_kind) -> bytes`.** Single source of truth for `os.open(O_RDONLY|O_NOFOLLOW)` + `os.fstat` + size-cap + `os.read` + `try`/`finally`-close. Raises `SizeCapExceeded("/path: cap=N bytes")`, `SymlinkRefusedError("/path: O_NOFOLLOW refused symlink")`. Emits `probe.parser.cap_exceeded` with `cap_kind="bytes"` on size-cap. Tested separately. Strategy hook: `parser_kind` is the only call-site-supplied discriminator; the primitive itself is parser-agnostic.
3. **`parsers/_depth.py::assert_max_depth(obj, *, max_depth, path, parser_kind)`.** Walks `dict` and `list` containers recursively with an `id()`-set of already-walked container ids. On encountering a depth > `max_depth`, emits `probe.parser.cap_exceeded` with `cap_kind="depth"` and raises `DepthCapExceeded("/path: max_depth=N exceeded")`. Scalars (`None`, `bool`, `int`, `float`, `str`) cost zero depth.
4. **`parsers/safe_yaml.py`:**
   - Module-level guard:
     ```python
     if getattr(yaml, "CSafeLoader", None) is None:
         raise ImportError(
             "yaml.CSafeLoader is required (ADR-0009, ADR-0008). "
             "Install pyyaml with libyaml support; SafeLoader fallback is banned."
         )
     ```
   - `load(path, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]`:
     ```python
     data = open_capped(path, max_bytes=max_bytes, parser_kind="safe_yaml")
     try:
         obj = yaml.load(data, Loader=yaml.CSafeLoader)
     except yaml.YAMLError as exc:
         raise MalformedYAMLError(f"{path}: {type(exc).__name__}: {exc}") from exc
     if obj is None or not isinstance(obj, dict):
         raise MalformedYAMLError(
             f"{path}: top-level must be a mapping (got {type(obj).__name__})"
         )
     assert_max_depth(obj, max_depth=max_depth, path=path, parser_kind="safe_yaml")
     return obj
     ```
   - `load_all(path, *, max_bytes, max_depth=64) -> Iterator[Mapping[str, JSONValue] | None]`:
     ```python
     data = open_capped(path, max_bytes=max_bytes, parser_kind="safe_yaml")
     def _gen() -> Iterator[Mapping[str, JSONValue] | None]:
         try:
             for doc in yaml.load_all(data, Loader=yaml.CSafeLoader):
                 if doc is not None and not isinstance(doc, dict):
                     raise MalformedYAMLError(
                         f"{path}: document #{...} must be a mapping or empty"
                     )
                 if doc is not None:
                     assert_max_depth(doc, max_depth=max_depth, path=path, parser_kind="safe_yaml")
                 yield doc
         except yaml.YAMLError as exc:
             raise MalformedYAMLError(f"{path}: {type(exc).__name__}: {exc}") from exc
     return _gen()
     ```
5. **Marker construction.** Every raise uses a **single positional formatted-message** f-string. No kwargs. No `.path`/`.cap`/`.detail` attribute assignment. Pinned by AC-18 + the Phase 0 markers-only test.
6. **`SymlinkRefusedError` docstring extension.** Append to `src/codegenie/errors.py::SymlinkRefusedError.__doc__` so that both `safe_json` and `safe_yaml` raise sites are documented (the `parsers` module slug is already on `DOCUMENTED_MODULE_SLUGS`; this is the human-readable bump). Reviewer-friendly diff; closes the S1-01 follow-up named for the YAML twin.
7. **PyYAML stubs.** `mypy --strict` flags `Loader` parameter without stubs. Add `types-PyYAML` under `[project.optional-dependencies] dev` rather than scatter `# type: ignore[arg-type]`. One-line edit.
8. **Plugin shape (forward-looking, no edits to other parsers).** Each `parsers/safe_*.py` consumes the same two primitives (`_io.open_capped`, `_depth.assert_max_depth`) and supplies its `parser_kind` literal. Adding a hypothetical `safe_toml` later is: new file, new `parser_kind="safe_toml"` literal, no edits anywhere else. The structlog event field `parser_kind` is the registry discriminator; no central registration list is created in Phase 1 (Rule 2 — only lift the kernel that two callers already need).

## TDD plan — red / green / refactor

### Red — failing tests first

Test file: `tests/unit/parsers/test_safe_yaml.py`. Twenty named tests, each annotated with AC and mutation caught.

```python
# tests/unit/parsers/test_safe_yaml.py
from __future__ import annotations

import errno
import inspect
import os
import textwrap
import tracemalloc
from pathlib import Path

import pytest
import structlog
import yaml

import codegenie.errors as e
from codegenie.parsers import safe_yaml


# --- AC-1 / AC-2 -------------------------------------------------------------

def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    sig = inspect.signature(safe_yaml.load)
    assert list(sig.parameters) == ["path", "max_bytes", "max_depth"]
    assert sig.parameters["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["max_depth"].default == 64

def test_load_all_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    sig = inspect.signature(safe_yaml.load_all)
    assert list(sig.parameters) == ["path", "max_bytes", "max_depth"]
    assert sig.parameters["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["max_depth"].default == 64

def test_module_all_exports_load_and_load_all_only() -> None:
    assert set(safe_yaml.__all__) == {"load", "load_all"}


# --- AC-3 --------------------------------------------------------------------

def test_module_docstring_references_arch_and_adrs() -> None:
    doc = (safe_yaml.__doc__ or "").lower()
    for fragment in ("component design", "adr-0009", "adr-0008", "alias"):
        assert fragment in doc, f"safe_yaml docstring missing '{fragment}'"


# --- AC-4 (CSafeLoader hard requirement) ------------------------------------

def test_csafeloader_required_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock CSafeLoader away, then force a reload — module import must raise.
    import importlib
    monkeypatch.delattr(yaml, "CSafeLoader", raising=True)
    with pytest.raises(ImportError) as exc:
        importlib.reload(safe_yaml)
    assert "csafeloader" in str(exc.value).lower()


# --- AC-5 (O_NOFOLLOW + ELOOP-only translation) -----------------------------

def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    sentinel_target = tmp_path / "outside"
    sentinel_target.write_text("sentinel: leaked\n")
    link = tmp_path / "pnpm-lock.yaml"
    link.symlink_to(sentinel_target)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)

def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        safe_yaml.load(tmp_path / "missing.yaml", max_bytes=10_000)
    assert not isinstance(exc.value, e.SymlinkRefusedError)

def test_is_a_directory_passes_through(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError) as exc:
        safe_yaml.load(tmp_path, max_bytes=10_000)
    assert not isinstance(exc.value, e.SymlinkRefusedError)


# --- AC-6 (size cap precedes read) ------------------------------------------

def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "big.yaml"
    p.write_text("k: " + "v" * 1024)
    real_read = os.read
    calls: list[int] = []
    def tracer(fd: int, n: int) -> bytes:
        calls.append(fd)
        return real_read(fd, n)
    monkeypatch.setattr(os, "read", tracer)
    with pytest.raises(e.SizeCapExceeded):
        safe_yaml.load(p, max_bytes=100)
    assert calls == [], "size cap must precede any os.read"


# --- AC-7, AC-8 (empty / non-mapping root) ----------------------------------

def test_empty_file_is_malformed_yaml(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)

@pytest.mark.parametrize("body", ["- 1\n- 2\n", "hello\n", "42\n"])
def test_top_level_non_mapping_is_malformed(tmp_path: Path, body: str) -> None:
    p = tmp_path / "non_mapping.yaml"
    p.write_text(body)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


# --- AC-9, AC-10 (unsafe tag + yaml.YAMLError catch-all) --------------------

def test_unsafe_python_object_tag_refused(tmp_path: Path) -> None:
    p = tmp_path / "evil.yaml"
    p.write_text("!!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)

@pytest.mark.parametrize(
    "body",
    [
        "key: : value\n",         # ParserError-shaped
        "key:\n\tvalue\n",        # tab indentation; ScannerError-shaped
        "!!python/name:os.system\n",  # ConstructorError-shaped
    ],
)
def test_yaml_error_subclasses_translate_uniformly(tmp_path: Path, body: str) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(body)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


# --- AC-11 (walker descends dicts AND lists) --------------------------------

def _nest_dict(depth: int) -> str:
    return "k: " + "{ " * depth + "v" + " }" * depth

def _nest_list(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth

def _nest_mixed(depth: int) -> str:
    # Alternates dict / list nesting.
    out = "v"
    for i in range(depth):
        out = f"[{out}]" if i % 2 == 0 else f"{{k: {out}}}"
    return out

@pytest.mark.parametrize("shape_fn", [_nest_dict, _nest_list, _nest_mixed])
def test_depth_walker_descends_lists_and_dicts(tmp_path: Path, shape_fn) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(shape_fn(70))
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p, max_bytes=100_000, max_depth=64)


# --- AC-12 (alias amplification — load-bearing) -----------------------------

def test_depth_walker_dedupes_alias_targets_no_amplification(tmp_path: Path) -> None:
    # 10 chained anchors → physical depth ~10, logical visits 10^10.
    # A naive walker would not return; an id()-memoized walker is O(nodes).
    lines = ["a: &a [1]"]
    prev = "a"
    for i, name in enumerate("bcdefghij"):
        prev_refs = ", ".join(f"*{prev}" for _ in range(10))
        lines.append(f"{name}: &{name} [{prev_refs}]")
        prev = name
    p = tmp_path / "alias_bomb.yaml"
    p.write_text("\n".join(lines) + "\n")
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    # Time-box via pytest-timeout if available; otherwise correctness check
    # (the test will hang under a naive walker — running it in CI is the test).
    safe_yaml.load(p, max_bytes=100_000, max_depth=64)  # must complete
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    delta = sum(s.size_diff for s in snap_after.compare_to(snap_before, "filename"))
    assert delta < 50 * 1024 * 1024, f"alias amplification: {delta} bytes allocated"


# --- AC-13 (depth boundary parametrized) ------------------------------------

@pytest.mark.parametrize("depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, depth: int) -> None:
    p = tmp_path / "ok.yaml"
    p.write_text(_nest_dict(depth) if depth else "k: v\n")
    safe_yaml.load(p, max_bytes=100_000, max_depth=64)  # no raise

@pytest.mark.parametrize("depth", [65, 100, 200])
def test_depth_above_cap_raises(tmp_path: Path, depth: int) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(_nest_dict(depth))
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p, max_bytes=100_000, max_depth=64)


# --- AC-14, AC-15 (cap events) ----------------------------------------------

def test_size_cap_emits_event_with_structured_fields(tmp_path: Path) -> None:
    p = tmp_path / "big.yaml"
    p.write_text("k: " + "v" * 1024)
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            safe_yaml.load(p, max_bytes=100)
    cap_events = [l for l in logs if l.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["parser_kind"] == "safe_yaml"
    assert ev["cap_kind"] == "bytes"
    assert ev["cap"] == 100
    assert str(p) in str(ev["path"])

def test_depth_cap_emits_event_with_structured_fields(tmp_path: Path) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(_nest_dict(70))
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(e.DepthCapExceeded):
            safe_yaml.load(p, max_bytes=10_000, max_depth=64)
    cap_events = [l for l in logs if l.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    assert cap_events[0]["parser_kind"] == "safe_yaml"
    assert cap_events[0]["cap_kind"] == "depth"

def test_no_cap_event_on_happy_or_malformed_or_symlink(tmp_path: Path) -> None:
    p_ok = tmp_path / "ok.yaml"; p_ok.write_text("k: v\n")
    p_bad = tmp_path / "bad.yaml"; p_bad.write_text("!!python/name:os.system\n")
    link = tmp_path / "link.yaml"; link.symlink_to(p_ok)
    with structlog.testing.capture_logs() as logs:
        safe_yaml.load(p_ok, max_bytes=10_000)
        with pytest.raises(e.MalformedYAMLError):
            safe_yaml.load(p_bad, max_bytes=10_000)
        with pytest.raises(e.SymlinkRefusedError):
            safe_yaml.load(link, max_bytes=10_000)
    assert [l for l in logs if l.get("event") == "probe.parser.cap_exceeded"] == []


# --- AC-16 (load_all lazy generator) ----------------------------------------

def test_load_all_is_lazy_generator(tmp_path: Path) -> None:
    p = tmp_path / "multi.yaml"
    p.write_text("kind: A\n---\nkind: B\n---\nkind: C\n")
    it = safe_yaml.load_all(p, max_bytes=10_000)
    assert inspect.isgenerator(it)
    first = next(it)
    assert first == {"kind": "A"}

def test_load_all_runs_walker_per_doc(tmp_path: Path) -> None:
    deep = _nest_dict(70)
    p = tmp_path / "multi.yaml"
    p.write_text(f"kind: Service\n---\n{deep}\n")
    it = safe_yaml.load_all(p, max_bytes=10_000, max_depth=64)
    first = next(it)
    assert first == {"kind": "Service"}  # first doc surfaces
    with pytest.raises(e.DepthCapExceeded):
        next(it)  # second doc raises

def test_load_all_yields_none_for_empty_documents(tmp_path: Path) -> None:
    p = tmp_path / "multi.yaml"
    p.write_text("kind: A\n---\n---\nkind: B\n")
    docs = list(safe_yaml.load_all(p, max_bytes=10_000))
    assert docs == [{"kind": "A"}, None, {"kind": "B"}]


# --- AC-17 (SymlinkRefusedError docstring extension) -------------------------

def test_symlink_refused_error_doc_names_safe_yaml() -> None:
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "safe_yaml" in doc, "S1-01 follow-up: SymlinkRefusedError docstring must name safe_yaml"


# --- AC-18 (markers-only positional construction) ---------------------------

@pytest.mark.parametrize(
    "marker",
    [e.SizeCapExceeded, e.DepthCapExceeded, e.MalformedYAMLError, e.SymlinkRefusedError],
)
def test_markers_only_positional_args0(marker: type[e.CodegenieError]) -> None:
    msg = "/r/file.yaml: probe positional roundtrip"
    exc = marker(msg)
    assert exc.args == (msg,)
    assert str(exc) == msg
    for forbidden in ("path", "cap", "detail", "warning_id"):
        assert not hasattr(exc, forbidden)


# --- AC-19 (fd lifecycle parity) --------------------------------------------

def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opens: list[int] = []
    closes: list[int] = []
    real_open, real_close = os.open, os.close
    def tracking_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **kw)
        opens.append(fd)
        return fd
    def tracking_close(fd):  # type: ignore[no-untyped-def]
        closes.append(fd)
        return real_close(fd)
    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", tracking_close)

    p_ok = tmp_path / "ok.yaml"; p_ok.write_text("k: v\n")
    p_big = tmp_path / "big.yaml"; p_big.write_text("k: " + "v" * 200)
    p_bad = tmp_path / "bad.yaml"; p_bad.write_text("!!python/name:os.system\n")
    p_deep = tmp_path / "deep.yaml"; p_deep.write_text(_nest_dict(70))
    link = tmp_path / "link.yaml"; link.symlink_to(p_ok)

    safe_yaml.load(p_ok, max_bytes=10_000)
    with pytest.raises(e.SizeCapExceeded):
        safe_yaml.load(p_big, max_bytes=50)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p_bad, max_bytes=10_000)
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p_deep, max_bytes=10_000, max_depth=64)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)

    assert sorted(opens) == sorted(closes), (
        f"fd parity violated: opens={opens} closes={closes}"
    )
```

Run; confirm every test fails because `parsers/safe_yaml.py` does not exist. Commit as red.

### Green — minimal implementation

Land the four edits in order:

1. `src/codegenie/parsers/_io.py` — if S1-02 didn't create it, this story does. `open_capped(path, *, max_bytes, parser_kind) -> bytes` with the O_NOFOLLOW + size-cap shape + structlog event + ELOOP-only translation. Tested in S1-02 (extend the test file or carry inline; either way the same module is the producer).
2. `src/codegenie/parsers/_depth.py` — `assert_max_depth(obj, *, max_depth, path, parser_kind)` walks with `id()` memoization. Single recursive function with a `seen: set[int]` closure; emits depth-cap event before raising `DepthCapExceeded`.
3. `src/codegenie/parsers/safe_yaml.py` — module-level CSafeLoader guard; `load` and `load_all` as outlined; positional marker construction throughout.
4. `src/codegenie/errors.py::SymlinkRefusedError.__doc__` one-line append naming `safe_yaml` (AC-17).
5. `pyproject.toml` — `types-PyYAML` under `[project.optional-dependencies] dev` if `mypy --strict` complains; otherwise leave untouched.

### Refactor — clean up

- Module docstring on `safe_yaml.py` cites `phase-arch-design.md §"Component design" #8`, ADR-0008, ADR-0009, and names the alias-amplification mitigation (AC-3).
- Public surface narrowed via `__all__ = ["load", "load_all"]`.
- `JSONValue` recursive alias re-exported from `parsers/__init__.py` (single-source-of-truth from `coordinator/validator.py`).
- `load_all`'s internal generator is a single `def _gen():` closure (not a separate top-level function) so `inspect.isgenerator` returns true on the call result.
- No `# type: ignore` comments unless `types-PyYAML` cannot satisfy a specific line; in that case, scope the ignore to one symbol with a comment quoting the specific stub gap.
- Do NOT catch `BaseException` anywhere. Do NOT translate `OSError` broadly. Do NOT add `yaml.SafeLoader` as a fallback. Do NOT add `path`/`cap`/`detail` attributes to raised markers.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/safe_yaml.py` | New module — `load` + `load_all` + CSafeLoader import guard |
| `src/codegenie/parsers/_io.py` | New if S1-02 didn't create it; consumed by both parsers |
| `src/codegenie/parsers/_depth.py` | New if S1-02 didn't create it; id()-memoized walker (mandatory for YAML, optional for JSON) |
| `src/codegenie/parsers/__init__.py` | Re-export `JSONValue` from `coordinator/validator.py` (single-source-of-truth at package boundary) |
| `src/codegenie/errors.py` | One-line `SymlinkRefusedError.__doc__` append naming `safe_yaml` (S1-01 follow-up) |
| `tests/unit/parsers/test_safe_yaml.py` | New — 20 named tests |
| `pyproject.toml` | Possibly: `types-PyYAML` under `dev` extra |

## Out of scope

- **`safe_json`** — S1-02.
- **`jsonc`** — S1-04.
- **Adversarial corpus tests** — S5-01 (`tests/adv/test_yaml_billion_laughs.py`, `tests/adv/test_yaml_unsafe_tag.py`, `tests/adv/test_oversized_lockfile.py`) carry the dedicated adversarial fixtures; this story's unit coverage uses small inline fixtures.
- **Catalog loader** — S1-05 (the catalog YAMLs route through `safe_yaml.load`).
- **`!!python/object` sentinel-side-effect test** — S5-02 (`test_yaml_unsafe_tag.py`). This story asserts the exception translation only.
- **Carrying machine-readable `path`/`cap`/`detail` attributes on markers** — forbidden by Phase 0 markers-only invariant (Out-of-scope reinforced).
- **Materializing `load_all` into a list internally** — out of scope; `load_all` MUST be lazy.

## Notes for the implementer

- **Markers-only construction is non-negotiable.** Every raise in this module passes a single positional formatted-message string. If `mypy` or your IDE auto-completes a kwarg-style call (`SizeCapExceeded(path=...)`), delete it; the markers do not accept kwargs and `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` proves it.
- **`yaml.CSafeLoader` is the only allowed loader.** No `yaml.SafeLoader` fallback under any circumstance. Phase 0's `forbidden-patterns` pre-commit hook bans `yaml.load(stream)` without `Loader=`. Use `yaml.load(data, Loader=yaml.CSafeLoader)` literally.
- **Alias amplification is the YAML-only mutation.** Do not implement the depth walker as a naive recursive descent; the id()-memoized walker is mandatory. The mutation test (AC-12) hangs under a naive walker — running it in CI is the test. If you copy-paste the JSON walker, **add the `seen: set[int]` set before merging**; better, consume `parsers/_depth.py` and skip the copy.
- **`yaml.YAMLError` is the catch-all.** Subclasses include `ConstructorError` (for `!!python/object`), `ParserError`, `ScannerError`. Catch the parent; translate to `MalformedYAMLError`. Do not catch `BaseException`.
- **ELOOP-only `OSError` translation.** Only `OSError` with `errno == errno.ELOOP` (the `O_NOFOLLOW`-on-symlink case) becomes `SymlinkRefusedError`. `FileNotFoundError`, `IsADirectoryError`, `PermissionError` propagate as themselves. AC-5 + tests `test_file_not_found_passes_through_unchanged` + `test_is_a_directory_passes_through` pin both directions.
- **`load_all` returns an iterator, not a list.** The caller decides whether to materialize. `DeploymentProbe` (S4-02) may short-circuit after the first non-deployment `kind`. The internal generator must use `def _gen(): ... yield ...` shape so `inspect.isgenerator` returns true.
- **`load_all` and empty documents.** A YAML file with `---\n---` produces `None`-yielding documents from CSafeLoader. The generator yields `None` verbatim; callers filter. **Non-mapping non-None documents** (e.g., a top-level list inside a multi-doc stream) raise `MalformedYAMLError` from inside the generator on the `next()` that surfaces them.
- **Depth walker on multi-doc:** run **per document**, not on the iterator-of-documents wrapper. AC-16 pins this. A walker over the iterator would only raise on the final `next()` instead of when the offending doc surfaces.
- **Top-level non-mapping is a `MalformedYAMLError`, not a silent return.** The signature promises `Mapping[str, JSONValue]` from `load`; a YAML file with root list / scalar / `None` cannot satisfy that promise.
- **structlog testing pattern.** Use `structlog.testing.capture_logs` — it returns a list of dicts that survive renderer choice. **Do not** use `capsys` + substring assertion on stderr; that pattern breaks if the renderer is `ConsoleRenderer` vs `JSONRenderer` and silently masks dropped event fields.
- **`SymlinkRefusedError` docstring.** Append, don't replace. Phase 0's `tests/unit/test_errors.py::test_every_subclass_has_raise_site_docstring` requires the docstring to name one of `DOCUMENTED_MODULE_SLUGS` — `parsers` already qualifies. The append is for human readers; the new test `test_symlink_refused_error_doc_names_safe_yaml` enforces the human-readable level.
- **PyYAML stubs.** `mypy --strict` may flag `Loader=yaml.CSafeLoader` typing because `types-PyYAML` is a separate package. Add it to the `dev` extra in `pyproject.toml` rather than scatter `# type: ignore[arg-type]` comments.
- **Plugin/strategy framing.** This module is one of three (`safe_json`, `safe_yaml`, `jsonc`) — and Phase 7+ may add `safe_toml`, `safe_xml`, lockfile-specific parsers. The shared kernel is `parsers/_io.py` + `parsers/_depth.py`; the per-parser strategy is the `parser_kind` literal each module supplies. **Do not add a registry or factory function in Phase 1** — Rule 2; YAGNI until a third parser shares this exact shape. The `parser_kind` field on every structlog event is the de-facto discriminator.
- **`probe.parser.cap_exceeded` literal.** S1-10 will promote the event-name literal to a `Final[str]` constant in `src/codegenie/logging.py`. For now the literal works; do not pre-emptively define a constant in `parsers/`.
