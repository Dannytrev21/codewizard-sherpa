# Story S3-09 — `transforms/lockfile/canonicalizer.py` — LC_ALL=C + key sort + LF + idempotence

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** M
**Depends on:** S3-08
**ADRs honored:** ADR-0011

## Context

The lockfile canonicalizer is the **byte-stability insurance** for `package-lock.json`. All three Phase-3 design lenses (performance/security/best-practices) implicitly assumed `npm` produces deterministic output across runs and minor-version drift; the critic flagged this as a shared blind spot (`final-design.md §"Shared blind spots #4"`). The canonicalizer absorbs:

1. `LC_ALL`-dependent sorting drift in npm's internal hash-map iteration order.
2. Top-level key ordering differences across npm minor versions.
3. CRLF vs LF line-ending drift (Windows runners).
4. Sub-object key ordering for `packages` and `dependencies` nested maps.

The result is byte-stable lockfile output that the determinism canary in S7-03 asserts is **identical across 5× runs**. Hypothesis-tested idempotence (`canonicalize(canonicalize(x)) == canonicalize(x)`) is the load-bearing invariant.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #6 (LockfileCanonicalizer)` — full internal-design + idempotence test.
  - `../phase-arch-design.md §"Cross-cutting concerns" lockfile canonicalization invariant` — LC_ALL=C + top-level key sort + LF discipline.
  - `../phase-arch-design.md §"Goals" #20` — npm digest pin + canonicalization deterministic-diff invariant.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — primary contract.
- **Source design:**
  - `../final-design.md §"Components" #4` tail — canonicalization step.
- **Existing code:**
  - `src/codegenie/transforms/lockfile/resolver.py` (S3-08) — produces the bytes this canonicalizer consumes.
  - Phase-2 hard caps on JSON parse depth — inherited (≤ 100 nesting levels, ≤ 50 MB input).

## Goal

Ship `src/codegenie/transforms/lockfile/canonicalizer.py` exporting `LockfileCanonicalizer.canonicalize(bytes) -> bytes` — a pure function that produces byte-identical output across runs given the same input. Idempotence and stability are pinned by Hypothesis property tests.

## Acceptance criteria

- [ ] `src/codegenie/transforms/lockfile/canonicalizer.py` exports `LockfileCanonicalizer.canonicalize(b: bytes) -> bytes` as a `@staticmethod` (no instance state).
- [ ] Input parsing: `json.loads(b, ...)` with Phase-2's depth/size caps (depth ≤ 100, size ≤ 50 MB). Oversize → `LockfileCanonicalizationFailed(reason="oversize", observed_size=...)`. Depth-overflow → `LockfileCanonicalizationFailed(reason="depth_overflow")`.
- [ ] Top-level keys sorted lexically (`name`, `version`, `lockfileVersion`, `requires`, `packages`, `dependencies`, ...).
- [ ] Sub-objects under `packages` and `dependencies` sorted deterministically by key path (recursive sort).
- [ ] Output emitted with: `LC_ALL=C` semantics (no locale-dependent string sort), LF line endings, no trailing whitespace, `ensure_ascii=False`, separators `(",", ":")` (no extra space after comma; canonical compact form), terminating LF.
- [ ] `LockfileCanonicalizer.canonicalize(canonicalize(x)) == canonicalize(x)` — idempotence holds.
- [ ] `tests/unit/transforms/lockfile/test_canonicalizer.py` ≥ 4 tests:
  1. CRLF input → LF output.
  2. Top-level keys in arbitrary input order → consistent output order.
  3. Sub-object keys (`packages."express"`, `packages."body-parser"`) sorted deterministically.
  4. Oversize input (> 50 MB) → `LockfileCanonicalizationFailed(reason="oversize")`.
- [ ] `tests/property/test_canonicalizer_idempotent.py` — Hypothesis property: `canonicalize(canonicalize(x)) == canonicalize(x)` over ≥ 200 generated lockfile-shaped JSON inputs.
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/unit/transforms/lockfile/test_canonicalizer.py` + `tests/property/test_canonicalizer_idempotent.py` first (red).
2. Implement `src/codegenie/transforms/lockfile/canonicalizer.py`:
   - `class LockfileCanonicalizer`:
     - `_MAX_BYTES = 50 * 1024 * 1024`
     - `_MAX_DEPTH = 100`
     - `@staticmethod def canonicalize(b: bytes) -> bytes:`
       ```text
       1. if len(b) > _MAX_BYTES: raise LockfileCanonicalizationFailed("oversize", ...)
       2. text = b.decode("utf-8")  # npm always emits UTF-8 for lockfiles
       3. parsed = json.loads(text, object_pairs_hook=dict)
       4. _check_depth(parsed, _MAX_DEPTH)  # raises on overflow
       5. canonical = _sort_recursive(parsed)
       6. out = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")) + "\n"
       7. return out.encode("utf-8")
       ```
   - `_sort_recursive(obj)` — for dicts, return `{k: _sort_recursive(v) for k in sorted(obj.keys())}`; for lists, return `[_sort_recursive(x) for x in obj]` (preserve list order); for scalars, return as-is.
   - `_check_depth(obj, max_depth, current=0)` — recursive depth-only walk; raises on overflow.
3. Define `LockfileCanonicalizationFailed` in `src/codegenie/errors.py`.
4. Run unit + property suites.

## TDD plan — red / green / refactor

### Red
Path: `tests/property/test_canonicalizer_idempotent.py`
```python
import json

import hypothesis.strategies as st
from hypothesis import given, settings

from codegenie.transforms.lockfile.canonicalizer import LockfileCanonicalizer


_json_scalar = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=20))

_lockfile_like = st.recursive(
    _json_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=5),
    ),
    max_leaves=30,
)


@settings(max_examples=200, deadline=None)
@given(lockfile_like=_lockfile_like)
def test_canonicalize_is_idempotent(lockfile_like):
    raw = json.dumps({"name": "x", "lockfileVersion": 3, "packages": lockfile_like}).encode("utf-8")
    once = LockfileCanonicalizer.canonicalize(raw)
    twice = LockfileCanonicalizer.canonicalize(once)
    assert once == twice
```

Path: `tests/unit/transforms/lockfile/test_canonicalizer.py`
```python
import pytest
from codegenie.transforms.lockfile.canonicalizer import LockfileCanonicalizer
from codegenie.errors import LockfileCanonicalizationFailed


def test_crlf_input_normalized_to_lf():
    crlf_in = b'{"a":1,"b":2}\r\n'
    out = LockfileCanonicalizer.canonicalize(crlf_in)
    assert b"\r" not in out
    assert out.endswith(b"\n")


def test_top_level_keys_sorted():
    a = b'{"b":2,"a":1,"c":3}'
    b = b'{"a":1,"c":3,"b":2}'
    assert LockfileCanonicalizer.canonicalize(a) == LockfileCanonicalizer.canonicalize(b)


def test_packages_sub_object_sorted():
    a = b'{"packages":{"z":{"v":1},"a":{"v":2}}}'
    b = b'{"packages":{"a":{"v":2},"z":{"v":1}}}'
    assert LockfileCanonicalizer.canonicalize(a) == LockfileCanonicalizer.canonicalize(b)


def test_oversize_input_raises():
    big = b'{"x":"' + b"a" * (51 * 1024 * 1024) + b'"}'
    with pytest.raises(LockfileCanonicalizationFailed) as exc:
        LockfileCanonicalizer.canonicalize(big)
    assert exc.value.reason == "oversize"
```

### Green
Pure function in ~80 LOC. No I/O, no state. The `_sort_recursive` walk is the entire algorithm.

### Refactor
- Resist extracting a generic "canonical JSON" helper; lockfile canonicalization is narrow and the helper invites reuse for unrelated payloads (e.g., audit events, where the depth cap is different).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/lockfile/canonicalizer.py` | New — `LockfileCanonicalizer` |
| `src/codegenie/errors.py` | Add `LockfileCanonicalizationFailed` |
| `tests/unit/transforms/lockfile/test_canonicalizer.py` | New — ≥ 4 tests |
| `tests/property/test_canonicalizer_idempotent.py` | New — Hypothesis property |

## Out of scope

- **Lockfile policy scan (registry redirects, missing integrity)** — handled by S4-01.
- **Lockfile generation** — handled by S3-08.
- **Determinism canary 5× byte-identical** — handled by S7-03 (which exercises the resolver + canonicalizer end-to-end).
- **The transform that calls this canonicalizer** — handled by S5-01.

## Notes for the implementer
- The Hypothesis idempotence property is **the** load-bearing test in this story. If it ever fails, the canonicalizer is buggy — do not relax the property to make a failing case pass (suppress the case in the strategy if it's a pathological input outside lockfile shape, but do not make `canonicalize(canonicalize(x)) != canonicalize(x)` an acceptable state).
- Python's `json.dumps(sort_keys=True)` does **most** of the work for top-level + nested dict sorting; the explicit `_sort_recursive` walk is belt-and-suspenders for the case where `object_pairs_hook` is overridden upstream.
- `LC_ALL=C` is achieved via Python's default sort (which is locale-independent for ASCII strings under `sorted(keys)`); the canonicalizer does NOT call `subprocess.run(env={"LC_ALL": "C"})` — that would imply external sorting. The semantics of LC_ALL=C are *built into* using Python's default `sorted()`.
- The trailing LF (`+ "\n"`) is mandatory — POSIX text files end with a newline, and git's diff machinery treats missing-final-newline as a special case that surfaces noisily in patches. Closing this is a 1-character invariant; pin it explicitly.
- The depth cap (100) and size cap (50 MB) inherit Phase-2's hard caps. Real-world lockfiles for monorepos can hit 20–30 MB; 50 MB is generous. If a fixture in S7-01 exceeds 50 MB it's a sign the fixture is mis-sized.
- The canonicalizer is **pure** — no logging, no audit events, no I/O. Consumers (S5-01's transform) emit the audit event for the lockfile-write side effect.
- Per Rule 12: `LockfileCanonicalizationFailed.reason` is a closed `Literal["oversize","depth_overflow","invalid_json","invalid_utf8"]` — pick a reason for every failure path; never raise a bare `ValueError`.
