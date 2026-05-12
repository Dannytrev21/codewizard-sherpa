# Story S2-03 — Hashing module (BLAKE3 + SHA-256 chokepoint)

**Step:** Step 2 — Plant the frozen contracts (probe ABC, hashing, exec allowlist, schema, error hierarchy)
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0001

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

## Goal

`from codegenie.hashing import content_hash, identity_hash, content_hash_of_inputs` succeeds; both `content_hash(some_path)` and `identity_hash("a","b")` return prefix-tagged hex strings (`"blake3:<64-hex>"` / `"sha256:<64-hex>"`) that are deterministic across runs, and `content_hash_of_inputs([p1, p2])` produces the same hash as `content_hash_of_inputs([p2, p1])` (sort-stable).

## Acceptance criteria

- [ ] `src/codegenie/hashing.py` exports exactly three public functions: `content_hash(path: Path) -> str`, `identity_hash(*parts: str) -> str`, `content_hash_of_inputs(paths: Iterable[Path]) -> str`. Module `__all__` lists only these three names.
- [ ] `content_hash` returns a string with literal prefix `"blake3:"` followed by 64 lowercase hex characters; `identity_hash` returns `"sha256:"` followed by 64 lowercase hex characters; both prefixes are part of the contract (ADR-0001 §Consequences) and must appear in the test assertions.
- [ ] `blake3` is imported **lazily** inside `content_hash` (and any helper it calls), not at module scope — `import codegenie.hashing` must not import `blake3`. `hashlib.sha256` may be imported at module scope (stdlib, no cold-start cost).
- [ ] `content_hash_of_inputs` is sort-stable: the inputs are sorted by `(str(path), size)` tuples before hashing, so input list order does not change the output hash.
- [ ] `hashing.py` is the **only** file in `src/codegenie/` importing `blake3` or `hashlib.sha256` — verifiable by an AST scan or grep (the same discipline `tests/adv/test_no_shell_true.py` will enforce for `subprocess.run` in S2-04; an analogous check is acceptable but not required as a separate test in Phase 0).
- [ ] `tests/unit/test_hashing.py` asserts: determinism (same input → same hex twice), prefix tagging, sort-stability of `content_hash_of_inputs`, and that `import codegenie.hashing` does **not** pull `blake3` into `sys.modules`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/hashing.py`, and `pytest tests/unit/test_hashing.py -q` are clean.

## Implementation outline

1. Write the failing test file (`tests/unit/test_hashing.py`) covering the four behaviors (determinism, prefix, sort-stability, lazy-import-of-`blake3`). Confirm `ImportError`.
2. Create `src/codegenie/hashing.py`. `import hashlib` at top; declare `__all__`; declare a module docstring naming ADR-0001 and the chokepoint discipline.
3. Implement `identity_hash(*parts: str) -> str`: join parts with a separator that cannot occur inside a part value (use `"\x1f"` — ASCII unit separator — to avoid collisions if a part contains spaces or pipes), encode UTF-8, `hashlib.sha256(...).hexdigest()`, prefix `"sha256:"`.
4. Implement `content_hash(path: Path) -> str`: lazy `from blake3 import blake3 as _blake3` inside the function body; stream the file in 64 KB chunks into a `_blake3()` hasher; return `f"blake3:{hasher.hexdigest()}"`.
5. Implement `content_hash_of_inputs(paths: Iterable[Path]) -> str`: build a sorted list of `(str(path), path.stat().st_size)` tuples; serialize each tuple as `f"{path_str}\x1f{size}"`; concatenate with `"\x1e"` (ASCII record separator); BLAKE3 the resulting bytes; return `f"blake3:{hasher.hexdigest()}"`. (Hashes the *manifest* of inputs, not the inputs' contents — that's the cache-key-fingerprint shape, not the file-content shape.)
6. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/hashing.py`, `pytest tests/unit/test_hashing.py -q`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_hashing.py`.

Four behaviors anchor this story; pin them with four short tests, not one big one.

```python
# tests/unit/test_hashing.py
import sys
from pathlib import Path

def test_content_hash_is_blake3_prefixed_and_deterministic(tmp_path: Path):
    # arrange: write a file with known bytes
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world\n")
    # act: hash twice
    from codegenie.hashing import content_hash
    h1, h2 = content_hash(f), content_hash(f)
    # assert: deterministic + prefix-tagged
    assert h1 == h2
    assert h1.startswith("blake3:")
    assert len(h1) == len("blake3:") + 64  # 64 hex chars

def test_identity_hash_is_sha256_prefixed_and_deterministic():
    # arrange: a stable tuple of parts
    parts = ("language_detection", "1.0", "v0.1.0", "blake3:deadbeef")
    # act
    from codegenie.hashing import identity_hash
    h1, h2 = identity_hash(*parts), identity_hash(*parts)
    # assert
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 64

def test_content_hash_of_inputs_is_sort_stable(tmp_path: Path):
    # arrange: two files; the order they appear in the iterable must not matter
    p1, p2 = tmp_path / "a.txt", tmp_path / "b.txt"
    p1.write_bytes(b"alpha"); p2.write_bytes(b"beta")
    # act
    from codegenie.hashing import content_hash_of_inputs
    forward = content_hash_of_inputs([p1, p2])
    reverse = content_hash_of_inputs([p2, p1])
    # assert: equal because the implementation sorts (path, size) before hashing
    assert forward == reverse

def test_blake3_is_not_eagerly_imported():
    # Cold-start invariant: `codegenie.hashing` import must NOT import `blake3`.
    # The CLI `--help` path leans on this (import-linter is the structural defense
    # but this is the unit-level pin).
    sys.modules.pop("blake3", None)
    sys.modules.pop("codegenie.hashing", None)
    import codegenie.hashing  # noqa: F401
    assert "blake3" not in sys.modules
```

Run; expect `ImportError`. Commit as the red marker.

### Green — make it pass

`src/codegenie/hashing.py`:

- Module docstring naming ADR-0001 and the chokepoint discipline.
- `import hashlib`, `from pathlib import Path`, `from typing import Iterable`.
- `__all__ = ["content_hash", "identity_hash", "content_hash_of_inputs"]`.
- `identity_hash(*parts: str) -> str`: `joined = "\x1f".join(parts).encode("utf-8"); return f"sha256:{hashlib.sha256(joined).hexdigest()}"`.
- `content_hash(path: Path) -> str`: lazy `from blake3 import blake3 as _blake3`; open the file in binary mode; stream 64 KB chunks into `hasher = _blake3()`; return `f"blake3:{hasher.hexdigest()}"`.
- `content_hash_of_inputs(paths: Iterable[Path]) -> str`: build `sorted((str(p), p.stat().st_size) for p in paths)`; serialize each `(p, s)` as `f"{p}\x1f{s}".encode("utf-8")`; join with `b"\x1e"`; lazy `_blake3()` hash; return prefix-tagged hex.

### Refactor — clean up

- Type hints on every public symbol (`Path`, `Iterable[Path]`, `str`).
- Docstrings on each public function naming the return-prefix contract.
- The `\x1f` / `\x1e` separator choice is a documentation point — add a one-line comment noting that ASCII unit/record separators cannot appear in path strings or numeric size strings.
- `mypy --strict` may need `blake3`'s typing stubs; `blake3>=1.0` ships them. If it doesn't, add a `# type: ignore[import-not-found]` *only* on the lazy `from blake3 import blake3 as _blake3` line, and document why in the comment.
- Confirm `content_hash` handles files larger than the chunk size (the 64 KB stream pattern); add a fixture in the test if `mypy --strict` insists.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/hashing.py` | New — the BLAKE3 + SHA-256 chokepoint per ADR-0001 |
| `tests/unit/test_hashing.py` | New — pins determinism, prefix tagging, sort-stability, and lazy-import |

## Out of scope

- **`CacheStore.key_for` integration** — handled by S3-01; this story exports the primitives `keys.py` will compose.
- **`blob_sha256` of sanitized output for the audit anchor** — handled by S3-06 (`AuditWriter`); uses `identity_hash` here but adds the blob-bytes hash on top.
- **`per_probe_schema_version` / `envelope_schema_version`** — handled by S3-01 (`cache/keys.py`); this story does not know about schema files.
- **An AST-scan test enforcing "only hashing.py imports blake3/hashlib.sha256"** — the chokepoint discipline is enforced by code review and the `forbidden-patterns` hook (S1-04); a dedicated AST test is *not* required in Phase 0 (deferred as a Phase 1 nicety).
- **HMAC over cache contents** — explicitly deferred to Phase 14 per `phase-arch-design.md §Non-goals` row 4.

## Notes for the implementer

- **The prefix is contract.** Returning `"<64-hex>"` instead of `"blake3:<64-hex>"` looks neater but breaks ADR-0001's "self-describing on-disk artifact" property and forces every consumer to know the algorithm out-of-band. Keep the prefix; the tests will catch you if you drop it.
- **BLAKE3 must be lazy-imported.** The `--help` cold-start budget (advisory ≤ 80 ms macOS / ≤ 150 ms Linux CI, `phase-arch-design.md §Component design — CLI`) leans on this. `import-linter` (S1-05) will structurally block `blake3` from `cli.py`/`__init__.py`, but the lazy-import inside `content_hash` is what makes the rest of the gather path zero-pay-until-used.
- **Don't mix the two hashes.** `content_hash_of_inputs` is BLAKE3 over a sorted *manifest* of inputs; the cache key tuple's `identity_hash` is SHA-256 over the `(name, version, schema_version, manifest_hash)` parts. The two algorithms intersect at `key_for(probe, snapshot, task)` in S3-01, where the BLAKE3 manifest hash becomes one of the SHA-256 identity-hash inputs. The split is the whole point of ADR-0001; resist "consistency" arguments to unify them.
- **Separator choice (`\x1f` unit, `\x1e` record).** These ASCII control characters cannot appear in `str(Path)` outputs on POSIX or Windows (paths can't legally contain them) and cannot appear in stringified integer sizes. Using `|` or `:` as a separator opens a separator-collision attack (a maliciously-named file path could include the separator and shift hash boundaries). The control chars close that vector.
- **Stream files in chunks.** Don't read the whole file into memory for `content_hash`. Phase 0's `LanguageDetectionProbe` only walks file *metadata* — no probe in Phase 0 actually hashes a real source file's bytes — but the function is on the cache-key hot path for Phase 1+'s probes. 64 KB is the conventional chunk size; resist tuning it without a benchmark.
- **`os.stat` errors propagate.** If `path.stat()` raises `FileNotFoundError` mid-`content_hash_of_inputs`, let it propagate — `CacheStore` will catch it and treat it as a miss (`phase-arch-design.md §Component design — CacheStore` failure behavior). Don't try to "be helpful" by skipping missing files; that would silently change the cache key.
- **Cross-cutting per the manifest's "Definition of done":** `ruff format`, `ruff check`, `mypy --strict`, all green on this file alone — the chokepoint discipline starts with not breaking the build on its own merit.
