# Story S1-03 — `safe_yaml` parser with `CSafeLoader` + `load_all` + post-parse depth walker

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0008, ADR-0009, ADR-0007

## Context

`safe_yaml` is the YAML twin of `safe_json` — every Phase 1 probe that reads YAML (`pnpm-lock.yaml`, GitHub Actions workflows, `Chart.yaml`, `values*.yaml`, `kustomization.yaml`, raw K8s manifests, the catalog YAMLs themselves) routes through here. `yaml.CSafeLoader` is the only allowed loader (Phase 0's `forbidden-patterns` hook bans `yaml.load(...)` without `Loader=`, and Phase 0 ratified `CSafeLoader`; ADR-0009 forbids adopting any new C-extension YAML parser). CSafeLoader has internal limits but does not natively cap nesting depth, so the post-parse depth walker from S1-02 carries the load-bearing weight here too.

`load_all` is required because `DeploymentProbe` parses multi-document raw K8s manifests (`safe_yaml.load_all` filtered to `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}` per `phase-arch-design.md §"Component design" #6`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — interface, post-parse depth walker rationale (CSafeLoader doesn't cap natively), and the `safe_yaml.load_all` signature for multi-document parsing.
  - `../phase-arch-design.md §"Edge cases"` rows 1, 4 — billion-laughs anchor expansion in `pnpm-lock.yaml`; zip-slip mitigation in kustomize.
  - `../phase-arch-design.md §"Scenarios" → Scenario 3` — billion-laughs flow.
- **Phase ADRs:**
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — ADR-0009 — `CSafeLoader` only; no `ruamel.yaml`, no `pyyaml.Loader`, no `unsafe_load`.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — in-process caps replace per-probe sandbox.
- **Source design:**
  - `../final-design.md §"Components" #8` — the design statement.
- **Existing code:**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — copy the `O_NOFOLLOW` open + size check pattern; the depth walker is the same shape.
  - `src/codegenie/errors.py` (S1-01) — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedYAMLError`, `SymlinkRefusedError`.

## Goal

Ship `src/codegenie/parsers/safe_yaml.py` with `load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` and `load_all(path, *, max_bytes, max_depth=64) -> Iterator[dict[str, JSONValue]]`, both `O_NOFOLLOW` + size-capped + depth-capped, parsed exclusively with `yaml.CSafeLoader`.

## Acceptance criteria

- [ ] `src/codegenie/parsers/safe_yaml.py` exports `load` and `load_all` with the documented signatures.
- [ ] Both use `yaml.CSafeLoader` (no `yaml.Loader`, `yaml.UnsafeLoader`, `yaml.load(...)` without `Loader=`, no `yaml.unsafe_load`).
- [ ] Both open with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` and size-check on `os.fstat(fd).st_size` before any read.
- [ ] Both run the post-parse depth walker; multi-document `load_all` runs the walker on each yielded document.
- [ ] `!!python/object` and similar unsafe tags are refused by `CSafeLoader` and translated to `MalformedYAMLError(path=path, detail=<short msg>)`.
- [ ] Emits `probe.parser.cap_exceeded` with `parser_kind="safe_yaml"` on cap violation.
- [ ] Unit tests cover: happy path single-doc, happy path multi-doc, `SizeCapExceeded` pre-parse, `DepthCapExceeded` on a billion-laughs-shaped input, `MalformedYAMLError` on `!!python/object`, `SymlinkRefusedError`, `FileNotFoundError` passthrough.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/parsers/safe_yaml.py`. Reuse the `_assert_depth` walker shape from S1-02 (consider lifting to `parsers/_depth.py` if there is exact duplication, but the rule per Rule 7 is to prefer one file over premature shared abstraction — only lift if the two walkers diverge zero in behavior).
2. `load(path, *, max_bytes, max_depth=64)`:
   - `os.open` + `os.fstat` + pre-parse size cap (raise `SizeCapExceeded`).
   - `data = os.read(fd, size)`; close fd in `finally`.
   - `obj = yaml.load(data, Loader=yaml.CSafeLoader)` — wrap in `try` translating `yaml.YAMLError` → `MalformedYAMLError`.
   - Post-parse depth walker; raise `DepthCapExceeded` on overflow.
   - Return `obj`.
3. `load_all(path, *, max_bytes, max_depth=64)`:
   - Same open + size-cap.
   - `for doc in yaml.load_all(data, Loader=yaml.CSafeLoader):` → run depth walker per doc → `yield doc`.
   - Same exception translation.
4. Write `tests/unit/parsers/test_safe_yaml.py` with the eight test cases.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/parsers/test_safe_yaml.py`.

```python
# tests/unit/parsers/test_safe_yaml.py
import textwrap
from pathlib import Path

import pytest

import codegenie.errors as e
from codegenie.parsers import safe_yaml


def test_happy_path_single_doc(tmp_path):
    p = tmp_path / "pnpm-lock.yaml"
    p.write_text("lockfileVersion: '9.0'\npackages: {}\n")
    out = safe_yaml.load(p, max_bytes=10_000)
    assert out["lockfileVersion"] == "9.0"

def test_happy_path_multi_doc(tmp_path):
    p = tmp_path / "raw.yaml"
    p.write_text(textwrap.dedent("""\
        kind: Deployment
        ---
        kind: Service
    """))
    docs = list(safe_yaml.load_all(p, max_bytes=10_000))
    assert [d["kind"] for d in docs] == ["Deployment", "Service"]

def test_size_cap_pre_parse(tmp_path):
    p = tmp_path / "big.yaml"
    p.write_text("k: " + "v" * 1024)
    with pytest.raises(e.SizeCapExceeded) as exc:
        safe_yaml.load(p, max_bytes=100)
    assert exc.value.cap == 100

def test_depth_cap_on_billion_laughs_shape(tmp_path):
    # adversarial: 70 nested mappings (CSafeLoader will parse; depth walker catches)
    inner = "k: " + "{ " * 70 + "v" + " }" * 70
    p = tmp_path / "deep.yaml"
    p.write_text(inner)
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p, max_bytes=10_000, max_depth=64)

def test_unsafe_python_object_tag_refused(tmp_path):
    p = tmp_path / "evil.yaml"
    p.write_text("!!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)

def test_symlink_refused(tmp_path):
    target = tmp_path / "outside"
    target.write_text("k: v\n")
    link = tmp_path / "pnpm-lock.yaml"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)

def test_file_not_found_passes_through(tmp_path):
    with pytest.raises(FileNotFoundError):
        safe_yaml.load(tmp_path / "missing.yaml", max_bytes=10_000)

def test_load_all_depth_walker_runs_per_doc(tmp_path):
    # one good doc + one over-depth doc
    deep = "k: " + "{ " * 70 + "v" + " }" * 70
    p = tmp_path / "multi.yaml"
    p.write_text(f"kind: Service\n---\n{deep}\n")
    docs_iter = safe_yaml.load_all(p, max_bytes=10_000, max_depth=64)
    first = next(docs_iter)
    assert first["kind"] == "Service"
    with pytest.raises(e.DepthCapExceeded):
        next(docs_iter)
```

Run; confirm `ModuleNotFoundError`. Commit as red.

### Green — minimal impl

Implement both functions following the S1-02 pattern. `load_all` returns a generator; raise `DepthCapExceeded` from inside the generator on the offending document. Use `yaml.YAMLError` as the catch-all for `MalformedYAMLError` (CSafeLoader's `!!python/object` refusal raises `yaml.constructor.ConstructorError`, a `YAMLError` subclass).

### Refactor — clean up

- Module docstring naming `phase-arch-design.md §"Component design" #8`, ADR-0009 (CSafeLoader-only), ADR-0008.
- The post-parse depth walker — if exact-equal to `safe_json`'s, lift to `src/codegenie/parsers/_depth.py` with a single `assert_max_depth(obj, max_depth, path)` callable. If even slightly different (e.g., YAML's None handling), keep separate per Rule 7 (don't average two patterns that disagree).
- Type hints on iterator return: `Iterator[dict[str, JSONValue]]` — use `collections.abc.Iterator`.
- Confirm `mypy --strict` is clean — PyYAML stubs (`types-PyYAML`) may need to be in the `dev` extra already; if not, add to `pyproject.toml` as part of this story (acceptance criterion).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/safe_yaml.py` | New module — `load` + `load_all` |
| `src/codegenie/parsers/_depth.py` | New (optional) — shared depth walker if and only if both parsers' walkers are identical |
| `tests/unit/parsers/test_safe_yaml.py` | New — 8 test cases |
| `pyproject.toml` | Possibly: add `types-PyYAML` under `dev` extra if `mypy --strict` requires it |

## Out of scope

- **`safe_json`** — S1-02.
- **`jsonc`** — S1-04.
- **Adversarial corpus tests** — S5-01 (`test_yaml_billion_laughs.py`, `test_yaml_unsafe_tag.py`, `test_oversized_lockfile.py`). This story carries unit coverage via small in-test fixtures.
- **Catalog loader** — S1-05 (the catalog YAMLs route through `safe_yaml.load`).

## Notes for the implementer

- **`yaml.CSafeLoader` is the only allowed loader.** Phase 0 has a `forbidden-patterns` pre-commit hook that bans `yaml.load(stream)` without `Loader=`. Use `yaml.load(data, Loader=yaml.CSafeLoader)` literally; do not import `CSafeLoader` from a side-module just to make a one-letter alias.
- **`yaml.YAMLError` is the catch-all.** Subclasses include `ConstructorError` (for `!!python/object`), `ParserError`, `ScannerError`, etc. Catch the parent; translate to `MalformedYAMLError`.
- **`load_all` returns an iterator, not a list.** The caller decides whether to materialize. Don't `return list(...)` in this story — `DeploymentProbe` (S4-02) may want to short-circuit after the first non-deployment `kind`.
- **Depth walker on multi-doc:** run **per document**, not on the iterator-of-documents wrapper. Otherwise a single deep document in a 100-document file will raise on the 100th `next()` call instead of when it surfaces.
- **Don't add `Loader=yaml.SafeLoader` as a fallback** if CSafeLoader is unavailable — Phase 0's `pyyaml` dependency includes the C extension on the supported platforms (Linux + macOS). If it's missing, fail loud (raise `ImportError`) at module import time rather than silently downgrading to the pure-Python `SafeLoader` (which is slower and has subtly different behavior).
- **PyYAML stubs:** `mypy --strict` may flag `Loader` parameter typing. Either add `types-PyYAML` to dev deps or `# type: ignore[arg-type]` on the single `yaml.load(...)` line with a comment. Prefer the former.
- The structlog event uses the literal `"probe.parser.cap_exceeded"` and the `parser_kind="safe_yaml"` field. S1-10 promotes the event name to a `Final[str]` constant.
