# Story S3-05 — `cassettes.lock` BLAKE3 manifest + `tests/security/test_cassettes_clean.py` CI scanner

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** M
**Depends on:** S3-04 (`verify_cassette` walker + sanitizer), S3-02 (first two real cassettes exist to enter into the lock)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline; layered control: sanitize + scanner + manifest + nightly), production-style content-addressed manifest convention (`embeddings_model.lock`, `tools/grammars.lock` precedent)

## Context

Cassettes are checked-in source code, but unlike Python source they are *binary-ish* YAML blobs that diffs reviewer eyes glaze over. The sanitizer (S3-04) is the first defense layer; this story lands the **scanner + manifest** layers — the CI hard-fail backstop and the per-cassette BLAKE3 record that Phase 6.5's bench harness will consume per case.

The two layers split cleanly:

- **`tests/security/test_cassettes_clean.py`** — walks every cassette under `tests/cassettes/`, calls `verify_cassette(path)` from S3-04, fails CI on any leaked pattern (header, body, or shaped token). This is the *secret-hygiene* control.
- **`tests/cassettes/anthropic/cassettes.lock`** — content-addressed manifest with one line per cassette: `<relpath>  <blake3-hex>`. The CI walker recomputes BLAKE3 of every cassette and asserts byte-for-byte match with the lock. This is the *integrity* control — it makes "I just regenerated and pushed without re-recording the lock" fail loudly.

Per ADR-0014 §Decision items 2–4 and §Consequences: the manifest format follows the existing `embeddings_model.lock` / `tools/grammars.lock` Phase-0/1 precedent. CI failure on a mismatch points to `make refresh-cassettes` (which S3-06 lands) as the recovery path.

A **deliberately-violating fixture cassette** is the load-bearing assurance — the CI scanner cannot be trusted unless we prove it fails on a planted secret. The fixture lives under `tests/security/fixtures/intentionally_dirty_cassettes/` and is *consumed* by an inverted test that asserts `verify_cassette(fixture).passed is False`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` — sub-section "CI security scanner".
  - `../phase-arch-design.md §Goals — G11` — `cassettes.lock` BLAKE3 manifest is the Phase 6.5 contract.
  - `../phase-arch-design.md §Stable contracts` — `cassettes.lock` line format is in the Phase-5-snapshot list (i.e., its shape is locked from Phase 4 onward).
- **Phase ADRs:**
  - `../ADRs/0014-cassette-discipline-security-control.md` §Decision items 2 + 4 — scanner + manifest format; §Consequences "`tests/security/test_cassettes_clean.py` runs in every CI build; failure = hard CI block."
- **Source design:** `../final-design.md §Component 13 — CassetteSanitizer`.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/hashing.py` — Phase 0's `blake3(...)` helper; reuse, do not fork.
  - `tools/grammars.lock` — precedent format for a content-addressed lock file in this repo (one line per resource).
  - `tests/unit/test_pyproject_fence.py` and Phase-1 `embeddings_model.lock` precedent — match the existing repo's "lock file diff = ADR amendment" mental model.
  - The `forbidden-patterns` pre-commit hook — verify the deliberately-dirty fixture file naming convention does not trigger the hook on `sk-ant-` strings (the fixture lives under `tests/security/fixtures/` which is the documented carve-out; if not, the hook may need a path exclusion).
- **External:** Phase 6.5 plan (`docs/roadmap.md`) — bench harness reads per-case cassette hashes.

## Goal

Ship the BLAKE3-rolled `tests/cassettes/anthropic/cassettes.lock` manifest, the CI walker `tests/security/test_cassettes_clean.py` that hard-fails on any sanitizer violation, the lock-mismatch check that fails CI on un-committed re-records, and a deliberately-dirty fixture cassette that proves the scanner catches leaks (inverted test asserts `passed is False`).

## Acceptance criteria

### Manifest format + generator

- [ ] AC-1 — `tests/cassettes/anthropic/cassettes.lock` exists as a plain-text file with one line per cassette in the format `<relpath>  <blake3-hex>` (two-space separator; relpath relative to `tests/cassettes/anthropic/`; BLAKE3 hex lowercased; 64 chars). Trailing newline at EOF. Lines sorted lexicographically by relpath.
- [ ] AC-2 — `src/codegenie/fallback/cassette/manifest.py` exports:
  - `compute_cassette_digest(path: Path) -> str` — BLAKE3 of cassette file bytes (no normalization; the cassette YAML is the canonical form). Returns hex string.
  - `load_lockfile(path: Path) -> Mapping[str, str]` — parses the lock file into `{relpath: blake3_hex}`. Raises `LockfileMalformed` on syntax error (missing separator, wrong-length hex, duplicate relpath, unsorted).
  - `rebuild_lockfile(cassettes_dir: Path) -> str` — walks `cassettes_dir`, computes BLAKE3 per cassette, returns the formatted lockfile contents (sorted, trailing newline). Pure: no disk write.
- [ ] AC-3 — `LockfileMalformed` is a frozen-extra-forbid Pydantic error class with `reason: Literal["missing_separator", "bad_hex_length", "duplicate_relpath", "unsorted_lines", "trailing_garbage"]`, `line_number: int`, `line_content: str`. The malformed-cases are parametrized in unit tests.
- [ ] AC-4 — `python -m codegenie cassette rebuild-lockfile` (new CLI subcommand) writes the rebuilt `cassettes.lock` to disk; idempotent on already-consistent state. **Refuses** to write if any cassette currently has a sanitizer violation (calls `verify_cassette` first; if any cassette is dirty, prints violations and exits non-zero). This makes the CLI safe to run; you cannot accidentally lock in a dirty cassette.

### CI scanner (the hard-fail backstop)

- [ ] AC-5 — `tests/security/test_cassettes_clean.py` walks `tests/cassettes/` recursively (via `pathlib.Path.rglob("*.yaml")`); for each cassette:
  - Calls `verify_cassette(path)` from S3-04.
  - On `passed=False`, the test **fails the entire CI build** with a diagnostic listing every violation (interaction index, kind, snippet).
- [ ] AC-6 — The walker also enforces the lock invariant: for each cassette under `tests/cassettes/anthropic/`, the computed BLAKE3 must equal the entry in `cassettes.lock`. Mismatch → `pytest.fail(...)` with diagnostic `"cassette body changed without lock update — run `python -m codegenie cassette rebuild-lockfile` and commit the result, then resubmit with cassette-review CODEOWNERS approval"`.
- [ ] AC-7 — The walker fails if a cassette exists on disk but has **no entry** in the lock (orphan cassette), and fails if the lock has an entry whose cassette no longer exists (stale entry). Both are loud errors with named diagnostic strings.
- [ ] AC-8 — The walker fails if `cassettes.lock` itself is malformed (parser raises `LockfileMalformed`).

### Deliberately-violating fixture (proves the scanner catches leaks)

- [ ] AC-9 — `tests/security/fixtures/intentionally_dirty_cassettes/with_sk_ant.yaml` exists; contains an interaction whose request `Authorization` header is `Bearer sk-ant-FIXTURE-NOT-REAL-1234567890abcdef`. This fixture lives **outside** the `tests/cassettes/` tree the CI walker scans (so the main walker stays green); a *separate* inverted test (`tests/security/test_scanner_catches_planted_secrets.py`) loads each fixture and asserts `verify_cassette(fixture).passed is False`.
- [ ] AC-10 — Three more dirty fixtures, each demonstrating a different leak shape:
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_cookie.yaml` — `Cookie` header leak.
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_body_base64.yaml` — body contains a 60-char base64-shaped string.
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_claude_underscore_prefix.yaml` — body contains `claude_secret_token_abcdef...`.
  Each must fail `verify_cassette` (one inverted assertion per file).
- [ ] AC-11 — The `forbidden-patterns` pre-commit hook is **not tripped** by these fixtures (either because the hook excludes `tests/security/fixtures/intentionally_dirty_cassettes/` by path, or because the `sk-ant-` literal is split across lines / encoded such that the hook's regex doesn't match while the cassette YAML still parses to a sensitive interaction). Document the chosen approach in the fixture directory's `README.md`.

### Lock-update workflow

- [ ] AC-12 — When `make refresh-cassettes` (S3-06) regenerates a cassette, the workflow either (a) automatically runs `python -m codegenie cassette rebuild-lockfile` and commits the updated lock alongside, or (b) prints a clear instruction to do so. The CI scanner (AC-6) catches the case where the operator forgot.
- [ ] AC-13 — `pre-commit` (project's `.pre-commit-config.yaml`) gains a check that re-runs `python -m codegenie cassette rebuild-lockfile --check` (the `--check` flag fails non-zero on drift rather than rewriting) so contributors catch the mismatch before push.

### Phase 6.5 contract pre-commitment

- [ ] AC-14 — The `cassettes.lock` format is documented in `docs/operations/cassettes.md` (file landed by S3-06 — coordinate; if S3-06 hasn't shipped, leave a docstring in `manifest.py` that S3-06 will lift) as: `<relpath>  <blake3-hex>\n`, sorted, two-space separator, trailing newline. Phase 6.5 reads this format byte-for-byte; deviation is an ADR amendment.
- [ ] AC-15 — `tests/integration/test_phase5_contract_snapshot.py` (refreshed in S7-10) will capture the `cassettes.lock` format among its stable contracts. This story does not modify that test directly but ships the format `cassettes.lock` such that S7-10 can lock it.

### Cross-cutting

- [ ] AC-16 — `mypy --strict src/codegenie/fallback/cassette/` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-17 — Module-level `_WARNING_IDS: Final[frozenset[str]]` for `manifest.py` is `frozenset({"cassette.lock_malformed", "cassette.lock_drift", "cassette.lock_orphan", "cassette.lock_stale"})` (four distinct error IDs the scanner emits).
- [ ] AC-18 — TDD red test exists, was demonstrably failing before implementation, now green.

## Implementation outline

1. Create `src/codegenie/fallback/cassette/manifest.py` with `compute_cassette_digest`, `load_lockfile`, `rebuild_lockfile`, `LockfileMalformed`.
2. Wire the `cassette` subcommand into `src/codegenie/cli.py`: `python -m codegenie cassette rebuild-lockfile [--check]`.
3. Author `tests/security/test_cassettes_clean.py` — the walker (sanitizer + lock checks).
4. Author the deliberately-dirty fixtures + the inverted test.
5. Decide the `forbidden-patterns` hook posture (path exclusion vs encoded fixtures); update `.pre-commit-config.yaml` if needed; document.
6. Add the `pre-commit` `--check` hook entry.
7. Generate the initial `tests/cassettes/anthropic/cassettes.lock` from S3-02's two cassettes (operator runs the CLI; commits the result).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_cassette_manifest.py
from pathlib import Path
import pytest
from codegenie.fallback.cassette.manifest import (
    compute_cassette_digest,
    load_lockfile,
    rebuild_lockfile,
    LockfileMalformed,
)


def test_compute_digest_is_deterministic(tmp_path):
    p = tmp_path / "c.yaml"; p.write_bytes(b"interactions: []\n")
    assert compute_cassette_digest(p) == compute_cassette_digest(p)


def test_compute_digest_changes_on_byte_diff(tmp_path):
    p1 = tmp_path / "c1.yaml"; p1.write_bytes(b"interactions: []\n")
    p2 = tmp_path / "c2.yaml"; p2.write_bytes(b"interactions: [{}]\n")
    assert compute_cassette_digest(p1) != compute_cassette_digest(p2)


def test_load_lockfile_parses_two_space_separator(tmp_path):
    lf = tmp_path / "cassettes.lock"
    lf.write_text("a.yaml  " + "0" * 64 + "\nb.yaml  " + "1" * 64 + "\n")
    parsed = load_lockfile(lf)
    assert parsed == {"a.yaml": "0" * 64, "b.yaml": "1" * 64}


@pytest.mark.parametrize("content,reason", [
    ("a.yaml " + "0" * 64 + "\n", "missing_separator"),    # one space, not two
    ("a.yaml  " + "0" * 63 + "\n", "bad_hex_length"),
    ("a.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "duplicate_relpath"),
    ("b.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "unsorted_lines"),
])
def test_load_lockfile_rejects_malformed(tmp_path, content, reason):
    lf = tmp_path / "cassettes.lock"; lf.write_text(content)
    with pytest.raises(LockfileMalformed) as exc:
        load_lockfile(lf)
    assert exc.value.reason == reason


def test_rebuild_lockfile_is_sorted_and_terminated(tmp_path):
    (tmp_path / "b.yaml").write_bytes(b"x")
    (tmp_path / "a.yaml").write_bytes(b"y")
    out = rebuild_lockfile(tmp_path)
    lines = out.splitlines(keepends=True)
    assert lines[0].startswith("a.yaml  ") and lines[1].startswith("b.yaml  ")
    assert out.endswith("\n")
```

```python
# tests/security/test_cassettes_clean.py
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CASSETTES_DIR = REPO_ROOT / "tests" / "cassettes"


def test_every_cassette_passes_sanitizer():
    from codegenie.fallback.cassette.sanitizer import verify_cassette
    for cassette in CASSETTES_DIR.rglob("*.yaml"):
        v = verify_cassette(cassette)
        assert v.passed, f"{cassette}: {v.violations!r}"


def test_lock_matches_disk():
    from codegenie.fallback.cassette.manifest import (
        load_lockfile, compute_cassette_digest,
    )
    anth_dir = CASSETTES_DIR / "anthropic"
    lock = load_lockfile(anth_dir / "cassettes.lock")
    for cassette in anth_dir.rglob("*.yaml"):
        rel = str(cassette.relative_to(anth_dir))
        assert rel in lock, f"orphan cassette: {rel}"
        assert compute_cassette_digest(cassette) == lock[rel], f"drift: {rel}"
    for rel in lock:
        assert (anth_dir / rel).exists(), f"stale entry: {rel}"
```

```python
# tests/security/test_scanner_catches_planted_secrets.py
import pytest
from pathlib import Path
from codegenie.fallback.cassette.sanitizer import verify_cassette


FIXTURES = Path(__file__).parent / "fixtures" / "intentionally_dirty_cassettes"


@pytest.mark.parametrize("name", [
    "with_sk_ant.yaml",
    "with_cookie.yaml",
    "with_body_base64.yaml",
    "with_claude_underscore_prefix.yaml",
])
def test_dirty_fixture_fails_verification(name):
    v = verify_cassette(FIXTURES / name)
    assert v.passed is False
    assert len(v.violations) >= 1
```

### Green — make it pass

Author `manifest.py`; wire the CLI; generate the initial lock from S3-02's recorded cassettes; commit.

### Refactor — clean up

- Extract `_validate_lock_lines(lines: list[str]) -> dict[str, str]` as a pure helper (so the malformed cases are one code path).
- Verify `LockfileMalformed.reason` exhaustiveness via `assert_never` in any consumer.
- Add `--check` mode to `cassette rebuild-lockfile` (no-write; exit non-zero on drift); used by `pre-commit`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/cassette/manifest.py` | The BLAKE3 manifest module (this story's primary deliverable). |
| `src/codegenie/cli.py` | `cassette rebuild-lockfile [--check]` subcommand. |
| `tests/security/test_cassettes_clean.py` | The CI walker (sanitizer + lock match). |
| `tests/security/test_scanner_catches_planted_secrets.py` | Inverted assertion: dirty fixtures fail verify. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_sk_ant.yaml` | Deliberately-violating fixture (sk-ant header). |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_cookie.yaml` | Cookie header leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_body_base64.yaml` | Body base64-shaped leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_claude_underscore_prefix.yaml` | `claude_*` body leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/README.md` | Explain the fixture's purpose; document `forbidden-patterns` carve-out. |
| `tests/cassettes/anthropic/cassettes.lock` | Initial lock (generated from S3-02 cassettes). |
| `tests/unit/fallback/test_cassette_manifest.py` | Unit tests for manifest module. |
| `.pre-commit-config.yaml` | Add `cassette rebuild-lockfile --check` hook (if not part of S3-06). |

## Out of scope

- `make refresh-cassettes` Makefile target (S3-06).
- CODEOWNERS entry (S3-06).
- Runbook `docs/operations/cassettes.md` (S3-06).
- Nightly drift job CI workflow (Phase 6.5).
- Recording new cassettes (operator workflow once S3-06 ergonomic is shipped).

## Notes for the implementer

- The `cassettes.lock` format is **load-bearing for Phase 6.5** — its line shape is locked by the phase-5-contract snapshot (S7-10). Any deviation (e.g., switching to TOML or JSON) is an ADR amendment, not a refactor.
- Use `codegenie.hashing.blake3` (Phase 0 helper) — do not re-import `blake3` directly here, that would bypass an existing single-import-point convention. If the helper doesn't exist with that exact name, mirror the existing `hashing.py` convention.
- The walker (`test_cassettes_clean.py`) is `module`-level test, not `function`-level — `pytest` collection traverses the cassettes once per session. Watch out for `pytest-xdist`: it splits per-test-id; ensure the walker's diagnostics name the cassette so a failure is reproducible.
- The deliberately-dirty fixtures **must not** trip the `forbidden-patterns` pre-commit hook. Two options:
  1. Add an exclusion path in `.pre-commit-config.yaml` for `tests/security/fixtures/intentionally_dirty_cassettes/`.
  2. Generate the fixture bodies at test setup time (so the literal `sk-ant-...` never appears on-disk in `git`). Option 1 is simpler and explicit; option 2 is more clever but adds runtime cost.
  Pick option 1; document in the fixture directory's `README.md`.
- The `--check` mode of `cassette rebuild-lockfile` is the pre-commit hook target; it must be **fast** (BLAKE3 of small YAML files is microseconds). Do not regress.
- When generating the initial lock at story-end, do it **after** S3-02's two cassettes are recorded and sanitizer-scanned. Order: S3-04 ships hooks → S3-06 lands `make refresh-cassettes` → operator runs the refresh, sanitizer fires, two cassettes land on disk clean → operator runs `python -m codegenie cassette rebuild-lockfile`, the lock file is committed alongside.
- If you need to coordinate with S3-04 mid-story: the `verify_cassette(path) -> CassetteVerification` shape from S3-04 is what this story's scanner consumes. If S3-04's `CassetteVerification` exposes `.passed: bool` and `.violations: tuple[Violation, ...]`, this story is unblocked. Surface any shape mismatch immediately (Global Rule 7 — don't average).
