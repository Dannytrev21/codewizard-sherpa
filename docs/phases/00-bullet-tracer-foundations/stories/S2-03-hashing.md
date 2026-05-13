# Story S2-03 — Hashing module (BLAKE3 + SHA-256 chokepoint)

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Ready (Validated 2026-05-13 — HARDENED)
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0001

## Validation notes (2026-05-13)

Hardened by `phase-story-validator`. Full audit log: [`_validation/S2-03-hashing.md`](_validation/S2-03-hashing.md). Headline changes:

- **AC count:** 7 → 14. Original ACs preserved (renumbered) and split where they bundled multiple verifiable claims.
- **TDD plan:** 4 anchor tests → 13 tests across three tiers (anchor, mutation-killer, edge-case). Adds known-vector pins, manifest-vs-content semantics, chunk-streaming pin, separator-collision pin, distinguishability, empty-input behavior, lowercase regex, `__all__` closure, `FileNotFoundError` propagation, same-size sort-stability, function-call lazy-load.
- **Goal widened** to include the chokepoint discipline (AC-5 was an orphan in the goal-trace).
- **AC-3 scope corrected**: lazy import is required inside `content_hash` AND `content_hash_of_inputs` (both public BLAKE3 surfaces), not just inside `content_hash` and its helpers.
- **AC-2 tightened** from "64 lowercase hex characters" prose into a verifiable `^(blake3|sha256):[0-9a-f]{64}$` regex assertion.
- **Out-of-scope corrected**: the original story claimed S1-04's `forbidden-patterns` hook enforces the `blake3`/`hashlib.sha256` chokepoint. It does not — S1-04's 11 banned patterns are `print(`, `yaml.load(` without `Loader=`, `shell=True`, `yaml.Dumper`, `os.system(`, `os.popen(`, `pickle.loads(`, `eval(`, `exec(`, `__import__(`, and the `subprocess.run(...,shell=)` variant. No automated enforcement of the hashing chokepoint ships in Phase 0; code review carries the rule, and an AST-scan analog is deferred to Phase 1 (recorded in Out-of-scope).
- **Cross-story consistency check** with S3-06 verified: S3-06 canonicalizes the sanitized blob to a JSON string (`json.dumps(..., sort_keys=True, separators=(",", ":"))`) **before** passing it to `identity_hash` — so the `*parts: str` signature of `identity_hash` works for S3-06's `blob_sha256` path. No fourth public function is required.

## Context

`src/codegenie/hashing.py` is the **single source of truth** for every hash decision in the codebase. The headline conflict from `final-design.md §L3 row 1` — performance lens wanted `xxh3-128` for speed, security and best-practices defaulted to SHA-256 — was resolved by ADR-0001's split: BLAKE3 (cryptographic *and* ~3 GB/s) for bulk content hashing of inputs, SHA-256 (audit-anchor stable; `localv2.md §8`-compatible) for the cache-key identity tuple and audit anchor. The "no other file imports `blake3` or `hashlib.sha256`" rule is the chokepoint discipline that makes future algorithm migrations a one-file diff. Every cache key, every audit anchor, and (transitively) every Phase 11 PR-provenance citation and Phase 13 cost-ledger attribution flows through this module.

Foundational: S2-05's registry and audit models, S3-01's cache store, S3-06's audit writer, and the entirety of Phase 11/13/14's anchoring all import from here.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Hashing` — public API signatures (`content_hash`, `identity_hash`, `content_hash_of_inputs`), the prefix-tagged return shape (`"blake3:<hex>"` / `"sha256:<hex>"`), the lazy-import of `blake3` to keep `--help` cold-start clean.
  - `../phase-arch-design.md §Component design — CacheStore` — names the exact `key_for` derivation `identity_hash(probe.name, probe.version, schema_version, content_hash_of_inputs)` that S3-01 consumes.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — first row recapping the BLAKE3/SHA-256 split rationale.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-cache-content-hash-algorithm.md` — ADR-0001 — the decision this story implements: BLAKE3 for content (bulk), SHA-256 for identity (tuple + audit); algorithm prefix in the on-disk artifact; "exactly one module" chokepoint discipline.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — cache integrity is load-bearing for the no-LLM commitment.
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — Phase 14's webhook fan-out depends on the BLAKE3 speed argument *and* the SHA-256 collision resistance.
- **Source design:**
  - `../final-design.md §2.7` — Cache layer; the explicit resolution of the `L3 row 1` conflict.
  - `../../../localv2.md §8` — SHA-256 specified for cache keys; compatibility surface for the identity tuple.
- **Existing code (if any):**
  - `src/codegenie/errors.py` — `CacheError` available if a hash failure needs to surface (in practice, `FileNotFoundError` propagates and `CacheStore` catches).
- **Downstream consumer (cross-check only — do NOT edit):**
  - `S3-06-audit-writer-verify.md §AC, §Implementation outline §2` — confirms S3-06 routes `blob_sha256` through `identity_hash(canonical_json_str)`, validating that this story's `*parts: str` signature suffices and no fourth public function is needed in Phase 0.

## Goal

`from codegenie.hashing import content_hash, identity_hash, content_hash_of_inputs` succeeds; `content_hash(some_path)` and `identity_hash("a","b")` return prefix-tagged hex strings matching `^(blake3|sha256):[0-9a-f]{64}$` that are deterministic across runs (same input → same hex); `content_hash_of_inputs([p1, p2])` produces the same hash as `content_hash_of_inputs([p2, p1])` (sort-stable on `(str(path), st_size)`) and hashes a *manifest* of inputs (not their byte contents); **and** `src/codegenie/hashing.py` is the only file in `src/codegenie/` that imports `blake3` or `hashlib.sha256` (the ADR-0001 chokepoint discipline).

## Acceptance criteria

- [ ] **AC-1 (public surface, locked).** `src/codegenie/hashing.py` exports exactly three public functions with these signatures and no others:
  ```python
  def content_hash(path: Path) -> str          # returns "blake3:<64-hex>"
  def identity_hash(*parts: str) -> str        # returns "sha256:<64-hex>"
  def content_hash_of_inputs(paths: Iterable[Path]) -> str  # returns "blake3:<64-hex>"
  ```
  Module declares `__all__ = ["content_hash", "identity_hash", "content_hash_of_inputs"]` and the test asserts `set(hashing.__all__)` equals exactly that set (no missing, no extra). Any module-level helper is prefixed with `_` and excluded.
- [ ] **AC-2 (prefix-tagged lowercase hex contract).** Every return value from `content_hash` and `content_hash_of_inputs` matches the regex `^blake3:[0-9a-f]{64}$`; every return value from `identity_hash` matches `^sha256:[0-9a-f]{64}$`. The lowercase requirement is part of the contract (ADR-0001 §Consequences relies on textual stability of the on-disk artifact across CPython upgrades); tests use `re.fullmatch` and additionally assert `digest.islower()` to catch a future `hexdigest().upper()` "improvement".
- [ ] **AC-3 (lazy BLAKE3 import — both public BLAKE3 functions).** `blake3` must be imported **lazily inside each function body** for both `content_hash` and `content_hash_of_inputs` (and any private helper either calls). `import codegenie.hashing` must not transitively import `blake3` (`"blake3" not in sys.modules` immediately after `import codegenie.hashing` in a clean interpreter). `hashlib` (stdlib) may be imported at module top.
- [ ] **AC-4 (lazy import — call-time activation pinned).** A test asserts both halves of the lazy contract: (a) `blake3` is absent from `sys.modules` immediately after `import codegenie.hashing`; (b) `blake3` is present in `sys.modules` immediately after the first call to `content_hash(...)`. The test isolates itself in a fresh interpreter (`subprocess.run([sys.executable, "-c", ...])`) to be immune to test-order pollution.
- [ ] **AC-5 (sort-stability on (path, size)).** `content_hash_of_inputs` builds a list of `(str(path), path.stat().st_size)` tuples, sorts ascending, and hashes a deterministic byte serialization of the sorted manifest. The result is identical across any permutation of the input iterable. Tested with: (a) a two-element swap on files with **distinct names and distinct sizes**, (b) a two-element swap on files with **distinct names and identical sizes** (kills a sort-by-size-only mutant), and (c) a three-element permutation (kills a "swap-once-then-stable" mutant).
- [ ] **AC-6 (manifest-vs-content semantics).** `content_hash_of_inputs` hashes the `(str(path), st_size)` *manifest* — **not** the file contents. Two files at identical paths with identical sizes but different bytes produce the **same** hash (proves manifest semantics); a single file's hash changes when its size changes (proves size is part of the manifest); a single file's hash does **not** change when its content mutates without changing size (the documented manifest-only semantic — counterintuitive but load-bearing for the cache-key fingerprint shape).
- [ ] **AC-7 (separator-collision resistance).** `identity_hash` joins parts with a separator that cannot appear inside any `str` part value (`\x1f` ASCII unit separator) so that distinct part-tuples never collide via boundary-shift attacks. Tested behaviorally: `identity_hash("ab", "c") != identity_hash("a", "bc")` and `identity_hash("a", "", "b") != identity_hash("a", "b")`. The separator byte itself is an implementation detail; the **invariant** is that distinct part-tuples produce distinct hashes.
- [ ] **AC-8 (distinguishability — different inputs → different hashes).** Hashing different inputs must produce different hex digests (catches a "return a constant of the correct shape" mutant). Tests pin: (a) `content_hash(file_with_alpha) != content_hash(file_with_beta)`, (b) `identity_hash("a","b") != identity_hash("a","c")`, (c) order-sensitivity: `identity_hash("a","b") != identity_hash("b","a")`.
- [ ] **AC-9 (known-vector pins).** Tests pin at least one known vector per algorithm to catch any "return zero hash of right shape" mutant: (a) `content_hash(tmp_file_with_b"abc")` equals `f"blake3:{blake3.blake3(b'abc').hexdigest()}"` (computed inline by the test calling the library directly — the test is allowed to import `blake3` because `tests/` is outside the chokepoint scope); (b) `identity_hash("a","b","c")` equals `f"sha256:{hashlib.sha256(b'a\\x1fb\\x1fc').hexdigest()}"` (pins the separator choice AND the algorithm AND the prefix at one shot).
- [ ] **AC-10 (streaming chunk-boundary correctness).** `content_hash` streams the file in 64 KB chunks (does not `read()` the whole file into memory). Pinned by a test that writes a >128 KB file (two chunk boundaries crossed) and asserts the hash equals BLAKE3 of the same bytes computed via a single-shot library call. A `read()`-everything mutant fails this if the chunk size is wrong, and a 64-byte-truncating mutant fails outright.
- [ ] **AC-11 (empty-input behavior pinned).** `content_hash_of_inputs([])` must return a deterministic, prefix-tagged hash (the BLAKE3 of an empty manifest). The hash equals itself across calls; it is **not** equal to `content_hash_of_inputs([p_with_no_bytes])` for any real path. `identity_hash()` (zero parts) is *also* legal and deterministic, but its return value is **distinct** from `identity_hash("")` (one empty part) — pinned by a test, because the cache-key derivation can legitimately compose zero or one empty strings, and silently collapsing the two would change cache identity.
- [ ] **AC-12 (`FileNotFoundError` propagation).** If any path in the iterable passed to `content_hash_of_inputs` does not exist, `path.stat()` raises `FileNotFoundError`, which propagates uncaught to the caller (per `phase-arch-design.md §Component design — Hashing` failure behavior — `CacheStore` will catch and treat as miss). Pinned by a test asserting `pytest.raises(FileNotFoundError)` on a non-existent path. **The function must not** silently skip the missing file, return a fallback hash, or wrap the error — silent skipping would change the cache key without a recorded reason.
- [ ] **AC-13 (chokepoint discipline — documented, not auto-enforced in Phase 0).** `hashing.py` is the **only** file in `src/codegenie/` importing `blake3` or `hashlib.sha256`. Phase 0 enforces this by code review only. An AST-scan analog (the parallel of `tests/adv/test_no_shell_true.py`) is **explicitly deferred to Phase 1** and recorded in Out-of-scope below. A grep check (`! git grep -nE '^(from blake3|import blake3|import hashlib\.sha256|from hashlib import sha256)' -- src/codegenie/ ':!src/codegenie/hashing.py'` returns 0 hits) is the manual verification on every PR until that AST test lands.
- [ ] **AC-14 (gates clean).** `ruff check`, `ruff format --check`, `mypy --strict` (run package-wide, not just on `hashing.py`, to catch cross-module typing regressions), and `pytest tests/unit/test_hashing.py -q` are all green; package-level coverage gate `--cov-fail-under=85` is met (the new test file lifts coverage of `hashing.py` toward 100%).

## Implementation outline

1. Write the failing test file (`tests/unit/test_hashing.py`) covering all 13 behaviors enumerated in AC-1..AC-12 and AC-14 (the chokepoint AC-13 is review-only in Phase 0; do not add an AST test for it). Confirm `ImportError`.
2. Create `src/codegenie/hashing.py`. `import hashlib` and `from pathlib import Path` at module top; `from typing import Iterable` at module top; declare `__all__`; module docstring names ADR-0001, the chokepoint discipline, and the lazy-import contract on `blake3`.
3. Implement `identity_hash(*parts: str) -> str`: join parts with `"\x1f"` (ASCII unit separator — chosen because it cannot legally appear in `str(Path)` outputs on POSIX or Windows and cannot appear in stringified integer sizes), UTF-8 encode, `hashlib.sha256(...).hexdigest()`, prefix `"sha256:"`. `identity_hash()` (zero parts) hashes the empty byte string; `identity_hash("")` (one empty part) hashes a single empty part (which is also the empty byte string under `"\x1f".join(("",))`) — these collide *by construction* with the SHA-256 of `b""`. **To preserve AC-11's "distinct from each other" requirement**, prepend a one-byte arity marker `bytes([len(parts) & 0xff])` to the joined bytes, *or* equivalently use the count of `\x1e` record separators as an arity witness. (Implementer choice; the test in AC-11 just demands the two hashes differ.)
4. Implement `content_hash(path: Path) -> str`: lazy `from blake3 import blake3 as _blake3` inside the function body; open the file in binary mode (`with path.open("rb") as f`); stream `f.read(65536)` in a loop into a `_blake3()` hasher until exhausted; return `f"blake3:{hasher.hexdigest()}"`.
5. Implement `content_hash_of_inputs(paths: Iterable[Path]) -> str`: **lazy** `from blake3 import blake3 as _blake3` inside this function body (AC-3 — peer public function, not a helper); build `sorted_manifest = sorted((str(p), p.stat().st_size) for p in paths)` (any `FileNotFoundError` from `stat()` propagates per AC-12); serialize each `(p, s)` tuple as `f"{p}\x1f{s}".encode("utf-8")`; join the per-tuple byte strings with `b"\x1e"` (ASCII record separator); BLAKE3 the resulting bytes (empty bytes for the empty-list case); return `f"blake3:{hasher.hexdigest()}"`. (Hashes the *manifest* of inputs — `(path, size)` pairs — **not** the bytes of the inputs themselves; AC-6 is the load-bearing semantic.)
6. Run `ruff format`, `ruff check`, `mypy --strict` (package scope), `pytest tests/unit/test_hashing.py -q`. Run `git grep -nE '^(from blake3|import blake3)' -- src/codegenie/ ':!src/codegenie/hashing.py'` and confirm zero output (AC-13 manual gate).

## TDD plan — red / green / refactor

### Red — write the failing test file first

Test file path: `tests/unit/test_hashing.py`.

Three tiers — anchor tests (one per AC), mutation-killer tests (kill common stub mutants), edge-case tests (boundary behavior).

```python
# tests/unit/test_hashing.py
import hashlib
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Tier 1 — anchor tests (AC-1..AC-3 public surface + prefix contract)
# ---------------------------------------------------------------------------

def test_module_all_closure_is_exactly_three_public_functions() -> None:
    """AC-1: __all__ pins the public surface — no missing, no extra."""
    import codegenie.hashing as h
    assert set(h.__all__) == {"content_hash", "identity_hash", "content_hash_of_inputs"}

def test_content_hash_matches_prefix_regex_and_is_deterministic(tmp_path: Path) -> None:
    """AC-2 + determinism part of Goal."""
    from codegenie.hashing import content_hash
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world\n")
    h1, h2 = content_hash(f), content_hash(f)
    assert h1 == h2
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", h1)

def test_identity_hash_matches_prefix_regex_and_is_deterministic() -> None:
    """AC-2 + determinism part of Goal."""
    from codegenie.hashing import identity_hash
    parts = ("language_detection", "1.0", "v0.1.0", "blake3:deadbeef")
    h1, h2 = identity_hash(*parts), identity_hash(*parts)
    assert h1 == h2
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", h1)

def test_hex_digests_are_lowercase() -> None:
    """AC-2 — kills a hexdigest().upper() "improvement"."""
    from codegenie.hashing import identity_hash
    digest = identity_hash("x").removeprefix("sha256:")
    assert digest == digest.lower()

# ---------------------------------------------------------------------------
# Tier 1 — anchor tests (AC-4 lazy import — both halves)
# ---------------------------------------------------------------------------

def test_blake3_lazy_import_isolated_in_fresh_interpreter() -> None:
    """AC-3 + AC-4: in a fresh interpreter, importing codegenie.hashing must NOT
    load blake3, but calling content_hash must. Subprocess isolates from any
    blake3 already loaded into this pytest session."""
    code = textwrap.dedent(
        """
        import sys, tempfile, pathlib
        assert "blake3" not in sys.modules
        import codegenie.hashing as h
        assert "blake3" not in sys.modules, "import-time leakage of blake3"
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(b"x"); tmp.flush()
            h.content_hash(pathlib.Path(tmp.name))
        assert "blake3" in sys.modules, "call-time lazy import did not fire"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

def test_content_hash_of_inputs_also_lazy_imports_blake3(tmp_path: Path) -> None:
    """AC-3: content_hash_of_inputs is a peer public function that uses BLAKE3 —
    must lazy-import too. Fresh subprocess proves the import is gated on the
    function call, not the module import."""
    f = tmp_path / "f"
    f.write_bytes(b"")
    code = textwrap.dedent(
        f"""
        import sys, pathlib
        import codegenie.hashing as h
        assert "blake3" not in sys.modules
        h.content_hash_of_inputs([pathlib.Path({str(f)!r})])
        assert "blake3" in sys.modules
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

# ---------------------------------------------------------------------------
# Tier 2 — mutation-killers (known vectors, distinguishability, separator)
# ---------------------------------------------------------------------------

def test_content_hash_matches_blake3_library_known_vector(tmp_path: Path) -> None:
    """AC-9: kills a 'return blake3:0000...' stub mutant. Test imports blake3
    directly — that's legal because tests/ is outside the chokepoint scope."""
    from blake3 import blake3 as _blake3
    from codegenie.hashing import content_hash
    f = tmp_path / "f"
    payload = b"abc"
    f.write_bytes(payload)
    expected = f"blake3:{_blake3(payload).hexdigest()}"
    assert content_hash(f) == expected

def test_identity_hash_matches_sha256_with_unit_separator_known_vector() -> None:
    """AC-9 + AC-7: pins prefix, algorithm, AND the \\x1f separator at one shot.
    A mutant using "|" as separator fails. A mutant returning "sha256:00..00"
    fails."""
    from codegenie.hashing import identity_hash
    expected_digest = hashlib.sha256(b"a\x1fb\x1fc").hexdigest()
    assert identity_hash("a", "b", "c") == f"sha256:{expected_digest}"

def test_content_hash_distinguishes_different_files(tmp_path: Path) -> None:
    """AC-8: kills a 'always return same hex' mutant."""
    from codegenie.hashing import content_hash
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"alpha")
    b.write_bytes(b"beta!")  # same size as "alpha"
    assert content_hash(a) != content_hash(b)

def test_identity_hash_is_order_sensitive_and_distinguishes_parts() -> None:
    """AC-8."""
    from codegenie.hashing import identity_hash
    assert identity_hash("a", "b") != identity_hash("a", "c")
    assert identity_hash("a", "b") != identity_hash("b", "a")  # order matters

def test_identity_hash_resists_separator_collision_attacks() -> None:
    """AC-7: boundary-shift attack — distinct part-tuples that would collide
    under a naive '|'.join must NOT collide under the chosen separator."""
    from codegenie.hashing import identity_hash
    assert identity_hash("ab", "c") != identity_hash("a", "bc")
    assert identity_hash("a", "", "b") != identity_hash("a", "b")

# ---------------------------------------------------------------------------
# Tier 2 — content_hash_of_inputs: sort-stability + manifest semantics
# ---------------------------------------------------------------------------

def test_content_hash_of_inputs_is_sort_stable_distinct_names_distinct_sizes(
    tmp_path: Path,
) -> None:
    """AC-5 (a) — original two-element swap."""
    from codegenie.hashing import content_hash_of_inputs
    p1, p2 = tmp_path / "a.txt", tmp_path / "b.txt"
    p1.write_bytes(b"alpha")     # size 5
    p2.write_bytes(b"beta")      # size 4
    assert content_hash_of_inputs([p1, p2]) == content_hash_of_inputs([p2, p1])

def test_content_hash_of_inputs_sort_stable_with_equal_sizes(tmp_path: Path) -> None:
    """AC-5 (b) — kills a 'sort by size only' mutant."""
    from codegenie.hashing import content_hash_of_inputs
    p1, p2 = tmp_path / "z.txt", tmp_path / "a.txt"
    p1.write_bytes(b"xxxxx")     # size 5
    p2.write_bytes(b"yyyyy")     # size 5 (same!)
    assert content_hash_of_inputs([p1, p2]) == content_hash_of_inputs([p2, p1])

def test_content_hash_of_inputs_sort_stable_three_element_permutation(
    tmp_path: Path,
) -> None:
    """AC-5 (c) — kills a 'swap once then stable' mutant. Three paths, every
    permutation must yield the same hash."""
    import itertools
    from codegenie.hashing import content_hash_of_inputs
    paths = []
    for name, payload in (("a", b"1"), ("b", b"22"), ("c", b"333")):
        f = tmp_path / name
        f.write_bytes(payload)
        paths.append(f)
    baseline = content_hash_of_inputs(paths)
    for perm in itertools.permutations(paths):
        assert content_hash_of_inputs(list(perm)) == baseline

def test_content_hash_of_inputs_hashes_manifest_not_bytes(tmp_path: Path) -> None:
    """AC-6: same (path, size), different bytes → SAME hash. This is the
    documented manifest semantic; a naive 'BLAKE3 over file contents'
    implementation would fail this and silently change cache identity."""
    from codegenie.hashing import content_hash_of_inputs
    p = tmp_path / "a.txt"
    p.write_bytes(b"first")              # 5 bytes
    h1 = content_hash_of_inputs([p])
    p.write_bytes(b"OTHER")              # 5 bytes, different content
    h2 = content_hash_of_inputs([p])
    assert h1 == h2, "content_hash_of_inputs hashes (path,size) manifest, not bytes"

def test_content_hash_of_inputs_changes_with_size(tmp_path: Path) -> None:
    """AC-6 sibling — size IS part of the manifest; changing size MUST change
    the hash."""
    from codegenie.hashing import content_hash_of_inputs
    p = tmp_path / "a.txt"
    p.write_bytes(b"short")
    h1 = content_hash_of_inputs([p])
    p.write_bytes(b"a longer payload")
    assert content_hash_of_inputs([p]) != h1

# ---------------------------------------------------------------------------
# Tier 2 — content_hash streaming
# ---------------------------------------------------------------------------

def test_content_hash_streams_files_spanning_chunk_boundary(tmp_path: Path) -> None:
    """AC-10: file > 64 KB chunk size must hash correctly. A read(64)-truncating
    mutant fails; a read()-everything mutant passes this test but is acceptable
    (the streaming requirement is for memory ceiling, not correctness — the
    test exists primarily to assert correctness across chunk boundaries)."""
    from blake3 import blake3 as _blake3
    from codegenie.hashing import content_hash
    payload = (b"x" * 100_000) + (b"y" * 100_000)  # 200_000 bytes ≈ 3 chunks
    p = tmp_path / "big"
    p.write_bytes(payload)
    assert content_hash(p) == f"blake3:{_blake3(payload).hexdigest()}"

# ---------------------------------------------------------------------------
# Tier 3 — edge cases
# ---------------------------------------------------------------------------

def test_content_hash_of_inputs_empty_list_is_legal_and_deterministic() -> None:
    """AC-11: empty manifest is a valid input; returns a deterministic
    prefix-tagged hash."""
    from codegenie.hashing import content_hash_of_inputs
    h = content_hash_of_inputs([])
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", h)
    assert content_hash_of_inputs([]) == h

def test_identity_hash_zero_parts_distinct_from_one_empty_part() -> None:
    """AC-11: identity_hash() and identity_hash("") must NOT collide — both
    are legitimate compositions of the cache-key tuple and silently collapsing
    them would change cache identity."""
    from codegenie.hashing import identity_hash
    assert identity_hash() != identity_hash("")

def test_content_hash_of_inputs_propagates_filenotfounderror(tmp_path: Path) -> None:
    """AC-12: missing path → FileNotFoundError, uncaught. No silent skip,
    no fallback hash."""
    from codegenie.hashing import content_hash_of_inputs
    with pytest.raises(FileNotFoundError):
        content_hash_of_inputs([tmp_path / "does-not-exist"])
```

Run; expect `ImportError`. Commit as the red marker.

### Green — make it pass

`src/codegenie/hashing.py`:

- Module docstring naming ADR-0001 and the chokepoint discipline; one sentence on the lazy-`blake3` contract; one sentence on the `\x1f` / `\x1e` separator rationale.
- `import hashlib`, `from pathlib import Path`, `from typing import Iterable` at module top.
- `__all__ = ["content_hash", "identity_hash", "content_hash_of_inputs"]`.
- `identity_hash(*parts: str) -> str`:
  - Arity-witness prefix to distinguish zero-arg from one-empty-arg per AC-11 — recommended form: `arity_byte = bytes([min(len(parts), 255)])` (or another scheme; just satisfy AC-11's distinctness invariant).
  - `joined = "\x1f".join(parts).encode("utf-8")`.
  - `digest = hashlib.sha256(arity_byte + joined).hexdigest()`.
  - `return f"sha256:{digest}"`.
- `content_hash(path: Path) -> str`:
  - Lazy: `from blake3 import blake3 as _blake3` inside the function body.
  - `hasher = _blake3()`.
  - `with path.open("rb") as f:` loop `chunk = f.read(65536)`; `while chunk: hasher.update(chunk); chunk = f.read(65536)`.
  - `return f"blake3:{hasher.hexdigest()}"`.
- `content_hash_of_inputs(paths: Iterable[Path]) -> str`:
  - Lazy: `from blake3 import blake3 as _blake3` inside this function body (AC-3 — peer public BLAKE3 surface).
  - `manifest = sorted((str(p), p.stat().st_size) for p in paths)` — `FileNotFoundError` from `stat()` propagates uncaught (AC-12).
  - Serialize: `b"\x1e".join(f"{p}\x1f{s}".encode("utf-8") for p, s in manifest)`. (Empty manifest → empty bytes; AC-11 deterministic.)
  - `return f"blake3:{_blake3(serialized).hexdigest()}"`.

### Refactor — clean up

- Type hints on every public symbol (`Path`, `Iterable[Path]`, `str`).
- Docstrings on each public function naming the return-prefix contract, the algorithm, and (for `content_hash_of_inputs`) the manifest-vs-content semantic.
- The `\x1f` / `\x1e` separator choice is a documentation point — add a one-line comment naming the threat model (boundary-shift attack via a `|`-containing path or part).
- `mypy --strict` may need `blake3`'s typing stubs; `blake3>=1.0` ships them. If a strict-mode complaint appears on the lazy import, add `# type: ignore[import-not-found]` *only* on the lazy `from blake3 import blake3 as _blake3` lines (one in each of the two BLAKE3 functions) and document why.
- Confirm the `subprocess.run`-based lazy-import tests work locally and in CI (the harness must allow `sys.executable` invocations).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/hashing.py` | New — the BLAKE3 + SHA-256 chokepoint per ADR-0001 |
| `tests/unit/test_hashing.py` | New — pins all 14 ACs across three tiers |

## Out of scope

- **`CacheStore.key_for` integration** — handled by S3-01; this story exports the primitives `cache/keys.py` will compose.
- **`blob_sha256` of sanitized output for the audit anchor** — handled by S3-06 (`AuditWriter`); routes through `identity_hash(canonical_json_str)` (cross-checked).
- **`per_probe_schema_version` / `envelope_schema_version`** — handled by S3-01 (`cache/keys.py`); this story does not know about schema files.
- **AST-scan test enforcing "only `hashing.py` imports `blake3`/`hashlib.sha256`"** — the chokepoint discipline is enforced by **code review** in Phase 0; the `forbidden-patterns` hook (S1-04) does **not** include `blake3` or `hashlib.sha256` in its 11-pattern set (verified). An analog of `tests/adv/test_no_shell_true.py` for the hashing chokepoint is a Phase 1 deferred-add (track in `_lessons.md`). The manual gate on every PR is `! git grep -nE '^(from blake3|import blake3|from hashlib import sha256)' -- src/codegenie/ ':!src/codegenie/hashing.py'` returns zero hits.
- **HMAC over cache contents** — explicitly deferred to Phase 14 per `phase-arch-design.md §Non-goals` row 4.
- **Path canonicalization** — the function uses `str(path)` as-is; callers are responsible for passing canonical paths (`Path.resolve()` if absolute identity is required). Not load-bearing for Phase 0's `LanguageDetectionProbe`; flagged for the gather coordinator's contract in Phase 1.

## Notes for the implementer

- **The prefix is contract.** Returning `"<64-hex>"` instead of `"blake3:<64-hex>"` looks neater but breaks ADR-0001's "self-describing on-disk artifact" property and forces every consumer to know the algorithm out-of-band. Keep the prefix; AC-2's regex assertion will catch you.
- **BLAKE3 must be lazy-imported in *both* public BLAKE3 functions.** The `--help` cold-start budget (advisory ≤ 80 ms macOS / ≤ 150 ms Linux CI, `phase-arch-design.md §Component design — CLI`) leans on this. `import-linter` (S1-05) is the structural defense at the CLI/`__init__` boundary; the lazy-imports inside `content_hash` and `content_hash_of_inputs` are what make every other module on the gather hot path zero-pay-until-used. AC-3 + AC-4 enforce both halves.
- **Don't mix the two hashes.** `content_hash_of_inputs` is BLAKE3 over a sorted *manifest* of inputs (AC-6 — explicitly **not** the file contents); the cache key tuple's `identity_hash` is SHA-256 over the `(name, version, schema_version, manifest_hash)` parts. The two algorithms intersect at `key_for(probe, snapshot, task)` in S3-01, where the BLAKE3 manifest hash becomes one of the SHA-256 identity-hash inputs. The split is the whole point of ADR-0001; resist "consistency" arguments to unify them.
- **Separator choice (`\x1f` unit, `\x1e` record).** These ASCII control characters cannot appear in `str(Path)` outputs on POSIX or Windows (paths can't legally contain them) and cannot appear in stringified integer sizes. Using `|` or `:` as a separator opens a separator-collision attack (a maliciously-named file path could include the separator and shift hash boundaries). AC-7's test pins the boundary-shift invariant behaviorally without naming the byte.
- **Stream files in chunks.** Don't read the whole file into memory for `content_hash`. Phase 0's `LanguageDetectionProbe` only walks file *metadata* — no probe in Phase 0 actually hashes a real source file's bytes — but the function is on the cache-key hot path for Phase 1+'s probes. 64 KB is the conventional chunk size; resist tuning it without a benchmark. AC-10 pins correctness across chunk boundaries.
- **`os.stat` errors propagate.** AC-12. If `path.stat()` raises `FileNotFoundError` mid-`content_hash_of_inputs`, let it propagate — `CacheStore` will catch it and treat it as a miss (`phase-arch-design.md §Component design — CacheStore` failure behavior). Don't try to "be helpful" by skipping missing files; that would silently change the cache key.
- **Arity witness for `identity_hash`.** AC-11 demands `identity_hash()` ≠ `identity_hash("")`. Naively, `"\x1f".join(())` and `"\x1f".join(("",))` both produce `""`, so the SHA-256 inputs collide. Prepending a one-byte arity counter (or any scheme that injects the part-count into the hashed bytes) closes that gap. Pick the simplest scheme that passes the test; the *behavior* (distinctness) is the contract, not the encoding.
- **Cross-cutting per the manifest's "Definition of done":** `ruff format`, `ruff check`, `mypy --strict` (package scope), all green on this file alone — the chokepoint discipline starts with not breaking the build on its own merit.
- **Manual chokepoint gate** (until Phase 1 adds the AST test): run `git grep -nE '^(from blake3|import blake3|from hashlib import sha256)' -- src/codegenie/ ':!src/codegenie/hashing.py'` before every PR opening — must return zero. Add this to the PR checklist when this story lands.
