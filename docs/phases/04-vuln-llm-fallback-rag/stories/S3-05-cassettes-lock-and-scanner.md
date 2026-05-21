# Story S3-05 — `cassettes.lock` BLAKE3 manifest + `tests/security/test_cassettes_clean.py` CI scanner

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-04 (`verify_cassette` walker + sanitizer), S3-02 (cassette scenario markers only; real cassette bytes are still deferred until S3-06)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline; layered control: sanitize + scanner + manifest + nightly), production-style content-addressed manifest convention (`embeddings_model.lock`, `tools/grammars.lock` precedent)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 18 — 3 blocks, 11 hardens, 4 nits

Changes applied:
- **Fixed the story-order block:** S3-02 explicitly deferred live cassette YAML until S3-04/S3-05/S3-06 exist. S3-05 now supports an empty initial `cassettes.lock` and commits real entries only if cassettes already exist.
- **Corrected the hash chokepoint:** this repo exports `codegenie.hashing.content_hash(path) -> "blake3:<hex>"`, not `codegenie.hashing.blake3`. `compute_cassette_digest` must reuse that helper and strip the prefix; direct `blake3` imports are forbidden.
- **Made lockfile failures representable:** `LockfileMalformedDetail` is the frozen Pydantic payload; `LockfileMalformed` is a thin exception wrapper exposing `.reason`, `.line_number`, and `.line_content`. This matches the repo's "Pydantic detail + raised wrapper" precedent.
- **Hardened scanner diagnostics:** the CI walker must aggregate sanitizer, drift, orphan, stale, missing-lock, and malformed-lock findings before failing, so one bad cassette cannot hide the next one.
- **Moved future-workflow claims out of S3-05:** `make refresh-cassettes`, CODEOWNERS, and the runbook remain S3-06; this story ships the CLI/pre-commit surfaces that S3-06 will call.

Full audit log: [`_validation/S3-05-cassettes-lock-and-scanner.md`](_validation/S3-05-cassettes-lock-and-scanner.md)

## Context

Cassettes are checked-in source code, but unlike Python source they are *binary-ish* YAML blobs that diffs reviewer eyes glaze over. The sanitizer (S3-04) is the first defense layer; this story lands the **scanner + manifest** layers — the CI hard-fail backstop and the per-cassette BLAKE3 record that Phase 6.5's bench harness will consume per case.

The two layers split cleanly:

- **`tests/security/test_cassettes_clean.py`** — walks every cassette under `tests/cassettes/`, calls `verify_cassette(path)` from S3-04, fails CI on any leaked pattern (header, body, or shaped token). This is the *secret-hygiene* control.
- **`tests/cassettes/anthropic/cassettes.lock`** — content-addressed manifest with one line per cassette: `<relpath>  <blake3-hex>`. The CI walker recomputes BLAKE3 of every cassette and asserts byte-for-byte match with the lock. This is the *integrity* control — it makes "I just regenerated and pushed without re-recording the lock" fail loudly. Because S3-02 was hardened to defer real cassette bytes until the full discipline stack exists, S3-05 must also accept the zero-cassette bootstrap: an empty lock file is valid until S3-06's refresh workflow records the first live cassette.

Per ADR-0014 §Decision items 2–4 and §Consequences: the manifest format follows the existing `embeddings_model.lock` / `tools/grammars.lock` Phase-0/1 precedent. CI failure on a mismatch points to `make refresh-cassettes` (which S3-06 lands) as the recovery path; this story only ships the `python -m codegenie cassette rebuild-lockfile [--check]` primitive that workflow will call.

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
  - `src/codegenie/hashing.py` — Phase 0's `content_hash(path) -> "blake3:<hex>"` helper; reuse it and strip the prefix, do not import `blake3` directly.
  - `tools/grammars.lock` — precedent format for a content-addressed lock file in this repo (one line per resource).
  - `tests/unit/test_pyproject_fence.py` and Phase-1 `embeddings_model.lock` precedent — match the existing repo's "lock file diff = ADR amendment" mental model.
  - The `forbidden-patterns` and `gitleaks` pre-commit hooks — verify the deliberately-dirty fixture file naming convention does not weaken the firewall. `forbidden-patterns` currently scans Python only and excludes `tests/`; if `gitleaks` needs an allowlist, scope it narrowly to the dirty-fixture directory and prove a negative control still fails outside it.
- **External:** Phase 6.5 plan (`docs/roadmap.md`) — bench harness reads per-case cassette hashes.

## Goal

Ship the BLAKE3-rolled `tests/cassettes/anthropic/cassettes.lock` manifest (valid even as the initial zero-cassette empty lock), the CI walker `tests/security/test_cassettes_clean.py` that hard-fails on any sanitizer violation, the lock-mismatch check that fails CI on un-committed re-records, and deliberately-dirty fixture cassettes that prove the scanner catches leaks (inverted test asserts `passed is False`).

## Acceptance criteria

### Manifest format + generator

- [ ] AC-1 — `tests/cassettes/anthropic/cassettes.lock` exists as a plain-text file. If `tests/cassettes/anthropic/` contains zero `*.yaml` cassettes, the lock file is valid as the empty string. Otherwise it has one line per cassette in the format `<relpath>  <blake3-hex>` (two-space separator; POSIX relpath relative to `tests/cassettes/anthropic/`; no absolute paths, `..`, backslashes, or empty path segments; BLAKE3 hex lowercased; 64 chars). Non-empty lock files have a trailing newline at EOF. Lines sorted lexicographically by relpath. Blank lines and comments are invalid.
- [ ] AC-2 — `src/codegenie/fallback/cassette/manifest.py` exports:
  - `compute_cassette_digest(path: Path) -> str` — BLAKE3 of cassette file bytes (no normalization; the cassette YAML is the canonical form). It calls `codegenie.hashing.content_hash(path)`, strips the `blake3:` prefix, and returns the lowercased 64-hex digest. `manifest.py` never imports `blake3` directly.
  - `load_lockfile(path: Path) -> Mapping[str, str]` — parses the lock file into an immutable mapping (`MappingProxyType`) of `{relpath: blake3_hex}`. Empty file -> empty mapping. Raises `LockfileMalformed` on missing file or syntax error (missing separator, invalid relpath, wrong-length hex, non-hex chars, duplicate relpath, unsorted, trailing garbage).
  - `rebuild_lockfile(cassettes_dir: Path) -> str` — recursively walks `cassettes_dir.rglob("*.yaml")`, computes BLAKE3 per cassette, returns the formatted lockfile contents (sorted, trailing newline when non-empty; empty string when no cassettes exist). Pure with respect to writes: reads cassette bytes but does not write the lock.
- [ ] AC-3 — `LockfileMalformedDetail` is a frozen-extra-forbid Pydantic model with `reason: Literal["missing_lockfile", "missing_separator", "bad_relpath", "bad_hex_length", "bad_hex_chars", "duplicate_relpath", "unsorted_lines", "trailing_garbage"]`, `line_number: int`, `line_content: str`. `LockfileMalformed(Exception)` is a thin wrapper carrying `.detail: LockfileMalformedDetail` and read-only convenience properties `.reason`, `.line_number`, `.line_content`. The malformed-cases are parametrized in unit tests. Do not make a Pydantic `BaseModel` directly raiseable; it is not an exception.
- [ ] AC-4 — `python -m codegenie cassette rebuild-lockfile [--check]` (new CLI subcommand) targets `tests/cassettes/anthropic/cassettes.lock` by default. Write mode writes the rebuilt lock to disk and is idempotent on already-consistent state. `--check` mode performs no writes and exits non-zero on drift. Both modes **refuse** to proceed if any cassette currently has a sanitizer violation (calls `verify_cassette` first; if any cassette is dirty, prints all violations and exits non-zero). This makes the CLI safe to run; you cannot accidentally lock in a dirty cassette.

### CI scanner (the hard-fail backstop)

- [ ] AC-5 — `tests/security/test_cassettes_clean.py` walks `tests/cassettes/` recursively (via `pathlib.Path.rglob("*.yaml")`); for each cassette:
  - Calls `verify_cassette(path)` from S3-04.
  - Collects every violation across every cassette before failing. One dirty file must not hide another dirty file.
  - On `passed=False`, the test **fails the entire CI build** with a diagnostic listing cassette relpath, interaction index, kind, header/pattern when present, and snippet.
- [ ] AC-6 — The walker also enforces the lock invariant for `tests/cassettes/anthropic/`: for each `*.yaml` cassette, the computed BLAKE3 must equal the entry in `cassettes.lock`. Mismatch → `pytest.fail(...)` with diagnostic `"cassette body changed without lock update — run `python -m codegenie cassette rebuild-lockfile` and commit the result, then resubmit with cassette-review CODEOWNERS approval"`. The diagnostic includes every drifted relpath, not only the first.
- [ ] AC-7 — The walker fails if a cassette exists on disk but has **no entry** in the lock (orphan cassette), and fails if the lock has an entry whose cassette no longer exists (stale entry). Both are loud errors with named diagnostic strings (`cassette.lock_orphan`, `cassette.lock_stale`) and include every offending relpath.
- [ ] AC-8 — The walker fails if `cassettes.lock` is missing or malformed (parser raises `LockfileMalformed`). The failure message includes `reason`, `line_number`, and `line_content`.

### Deliberately-violating fixture (proves the scanner catches leaks)

- [ ] AC-9 — `tests/security/fixtures/intentionally_dirty_cassettes/with_sk_ant.yaml` exists; contains an interaction whose request `Authorization` header is `Bearer sk-ant-FIXTURE-NOT-REAL-1234567890abcdef`. This fixture lives **outside** the `tests/cassettes/` tree the CI walker scans (so the main walker stays green); a *separate* inverted test (`tests/security/test_scanner_catches_planted_secrets.py`) loads each fixture and asserts `verify_cassette(fixture).passed is False`.
- [ ] AC-10 — Three more dirty fixtures, each demonstrating a different leak shape:
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_cookie.yaml` — `Cookie` header leak.
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_body_base64.yaml` — body contains a 60-char base64-shaped string.
  - `tests/security/fixtures/intentionally_dirty_cassettes/with_claude_underscore_prefix.yaml` — body contains `claude_secret_token_abcdef...`.
  Each must fail `verify_cassette` (one inverted assertion per file).
- [ ] AC-11 — The deliberately-dirty fixtures do not weaken pre-commit coverage. The current `forbidden-patterns` hook scans only Python and excludes `tests/`, so do **not** add a broad `forbidden-patterns` carve-out for YAML fixtures. Add a behavioral test or documented command proving `pre-commit run forbidden-patterns --files tests/security/fixtures/intentionally_dirty_cassettes/with_sk_ant.yaml` is a no-op for the expected reason. If `gitleaks` (not `forbidden-patterns`) flags the fake `sk-ant-` fixture, add the narrowest possible fixture-path allowlist and a negative-control test/command proving the same fake token outside that directory is still rejected. Document the chosen approach in the fixture directory's `README.md`.

### Lock-update workflow

- [ ] AC-12 — S3-05 supplies the lock-update primitive that S3-06's `make refresh-cassettes` workflow will call: `python -m codegenie cassette rebuild-lockfile --check` exits non-zero on drift and prints the exact recovery instruction from AC-6. This story does **not** add the `make refresh-cassettes` target; S3-06 decides whether to auto-run rebuild or print the instruction.
- [ ] AC-13 — `pre-commit` (project's `.pre-commit-config.yaml`) gains a check that re-runs `python -m codegenie cassette rebuild-lockfile --check` (the `--check` flag fails non-zero on drift rather than rewriting) so contributors catch the mismatch before push.

### Phase 6.5 contract pre-commitment

- [ ] AC-14 — The `cassettes.lock` format is documented in `docs/operations/cassettes.md` (file landed by S3-06 — coordinate; if S3-06 hasn't shipped, leave a docstring in `manifest.py` that S3-06 will lift) as: empty file when no cassettes exist; otherwise `<relpath>  <blake3-hex>\n`, sorted, two-space separator, trailing newline. Phase 6.5 reads this format byte-for-byte; deviation is an ADR amendment.
- [ ] AC-15 — `tests/integration/test_phase5_contract_snapshot.py` (refreshed in S7-10) will capture the `cassettes.lock` format among its stable contracts. This story does not modify that test directly but ships the format `cassettes.lock` such that S7-10 can lock it.

### Cross-cutting

- [ ] AC-16 — `mypy --strict src/codegenie/fallback/cassette/` clean. `ruff check`, `ruff format --check` clean.
- [ ] AC-17 — Module-level `_WARNING_IDS: Final[frozenset[str]]` for `manifest.py` is `frozenset({"cassette.lock_malformed", "cassette.lock_drift", "cassette.lock_orphan", "cassette.lock_stale"})` (four distinct error IDs the scanner emits).
- [ ] AC-18 — TDD red test exists, was demonstrably failing before implementation, now green.

### Validator-added hardening

- [ ] AC-19 — `tests/security/test_cassettes_clean.py` uses test-local pure collector helpers rather than inline `assert` inside loops:
  - `_collect_sanitizer_findings(cassettes_dir: Path) -> tuple[str, ...]`
  - `_collect_lock_findings(anthropic_dir: Path) -> tuple[str, ...]`
  The top-level pytest tests fail once with `pytest.fail("\n".join(findings))` only after collecting all findings. Unit-style tests exercise these helpers against `tmp_path` directories for clean, dirty, drift, orphan, stale, missing-lock, and malformed-lock cases.
- [ ] AC-20 — A source-scan test asserts `src/codegenie/fallback/cassette/manifest.py` contains no `import blake3` / `from blake3` and calls `codegenie.hashing.content_hash`. This preserves the Phase-0 hashing chokepoint while still returning the unprefixed 64-hex lockfile digest.
- [ ] AC-21 — `load_lockfile` rejects unsafe relpaths (`/abs.yaml`, `../escape.yaml`, `nested/../escape.yaml`, `nested\\windows.yaml`, empty relpath) with `reason == "bad_relpath"`. This prevents the stale-entry check from accidentally resolving outside `tests/cassettes/anthropic/`.
- [ ] AC-22 — The initial bootstrap is tested explicitly: with `tests/cassettes/anthropic/` containing no `*.yaml`, `rebuild_lockfile(...) == ""`, `load_lockfile(cassettes.lock)` returns an empty mapping, and the scanner emits no findings. If cassettes already exist by the time the executor runs, this test still creates its own empty temp directory so the zero-cassette path remains covered.
- [ ] AC-23 — CLI tests cover `--check` no-write semantics: when the on-disk lock is stale, `--check` exits non-zero and leaves file bytes unchanged; write mode updates the file; a second write is byte-idempotent.

## Implementation outline

1. Create `src/codegenie/fallback/cassette/manifest.py` with `compute_cassette_digest`, `load_lockfile`, `rebuild_lockfile`, `LockfileMalformedDetail`, and `LockfileMalformed`.
2. Wire the `cassette` subcommand into `src/codegenie/cli.py`: `python -m codegenie cassette rebuild-lockfile [--check]`.
3. Author `tests/security/test_cassettes_clean.py` — the walker (sanitizer + lock checks) with pure collector helpers and aggregate diagnostics.
4. Author the deliberately-dirty fixtures + the inverted test.
5. Prove the dirty fixtures do not weaken pre-commit coverage. Do not add a broad `forbidden-patterns` exclusion; if `gitleaks` needs an allowlist, scope it to `tests/security/fixtures/intentionally_dirty_cassettes/` and prove the negative control.
6. Add the `pre-commit` `--check` hook entry.
7. Generate the initial `tests/cassettes/anthropic/cassettes.lock`: empty file if no cassettes exist yet, otherwise generated from the current sanitized cassette set. Do not record live cassettes in this story.

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
    with pytest.raises(TypeError):
        parsed["c.yaml"] = "2" * 64


def test_empty_lockfile_is_valid_bootstrap(tmp_path):
    lf = tmp_path / "cassettes.lock"
    lf.write_text("")
    assert load_lockfile(lf) == {}
    assert rebuild_lockfile(tmp_path) == ""


@pytest.mark.parametrize("content,reason", [
    ("a.yaml " + "0" * 64 + "\n", "missing_separator"),    # one space, not two
    ("a.yaml  " + "0" * 63 + "\n", "bad_hex_length"),
    ("a.yaml  " + "g" * 64 + "\n", "bad_hex_chars"),
    ("../escape.yaml  " + "0" * 64 + "\n", "bad_relpath"),
    ("a.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "duplicate_relpath"),
    ("b.yaml  " + "0" * 64 + "\na.yaml  " + "1" * 64 + "\n", "unsorted_lines"),
    ("a.yaml  " + "0" * 64 + "\n\n", "trailing_garbage"),
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


def test_manifest_uses_hashing_chokepoint_not_direct_blake3():
    src = Path("src/codegenie/fallback/cassette/manifest.py").read_text()
    assert "from blake3" not in src
    assert "import blake3" not in src
    assert "content_hash(" in src
```

```python
# tests/security/test_cassettes_clean.py
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CASSETTES_DIR = REPO_ROOT / "tests" / "cassettes"


def test_every_cassette_passes_sanitizer():
    findings = _collect_sanitizer_findings(CASSETTES_DIR)
    if findings:
        pytest.fail("\n".join(findings))


def test_lock_matches_disk():
    findings = _collect_lock_findings(CASSETTES_DIR / "anthropic")
    if findings:
        pytest.fail("\n".join(findings))
```

Additional red tests (same files unless noted):

- `test_collect_lock_findings_reports_all_drift_orphan_and_stale` — temp `anthropic/` dir with one drifted cassette, one orphan cassette, and one stale lock entry; assert all three diagnostics appear in the returned findings tuple.
- `test_collect_lock_findings_reports_missing_and_malformed_lock` — missing lock and malformed lock each produce one loud finding with the `LockfileMalformed.reason`.
- `test_rebuild_lockfile_check_mode_does_not_write` — invoke the CLI with a stale lock under an isolated filesystem; `--check` exits non-zero and lock bytes are unchanged; write mode updates; second write is idempotent.
- `test_empty_anthropic_dir_is_green` — temp `anthropic/` dir with empty `cassettes.lock` and no YAML files produces no lock findings.

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

Author `manifest.py`; wire the CLI; create `tests/cassettes/anthropic/cassettes.lock` as an empty lock if no sanitized cassette YAML exists yet, otherwise generate it from the current cassette set. Do not record live cassettes in S3-05.

### Refactor — clean up

- Extract `_validate_lock_lines(lines: list[str]) -> Mapping[str, str]` as a pure helper (so the malformed cases are one code path). Wrap the result in `MappingProxyType` at the public boundary.
- Verify `LockfileMalformed.reason` exhaustiveness via `assert_never` in any consumer.
- Add `--check` mode to `cassette rebuild-lockfile` (no-write; exit non-zero on drift); used by `pre-commit`.
- Keep `test_cassettes_clean.py`'s collector helpers pure: no filesystem writes, no `pytest.fail` inside helpers, no early return after first finding.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/cassette/manifest.py` | The BLAKE3 manifest module (this story's primary deliverable). |
| `src/codegenie/cli.py` | `cassette rebuild-lockfile [--check]` subcommand. |
| `tests/security/test_cassettes_clean.py` | The CI walker (sanitizer + lock match). |
| `tests/security/test_cassette_lock_invariants.py` | Unit-style tests for the scanner helper diagnostics over temp dirs. |
| `tests/security/test_scanner_catches_planted_secrets.py` | Inverted assertion: dirty fixtures fail verify. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_sk_ant.yaml` | Deliberately-violating fixture (sk-ant header). |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_cookie.yaml` | Cookie header leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_body_base64.yaml` | Body base64-shaped leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/with_claude_underscore_prefix.yaml` | `claude_*` body leak. |
| `tests/security/fixtures/intentionally_dirty_cassettes/README.md` | Explain the fixture's purpose; document the pre-commit / gitleaks posture. |
| `tests/cassettes/anthropic/cassettes.lock` | Initial lock: empty if no cassettes exist yet, otherwise generated from current sanitized cassettes. |
| `tests/unit/fallback/test_cassette_manifest.py` | Unit tests for manifest module. |
| `tests/fence/test_cassette_manifest_hash_chokepoint.py` | Source-scan guard that `manifest.py` routes BLAKE3 through `codegenie.hashing.content_hash`. |
| `.pre-commit-config.yaml` | Add `cassette rebuild-lockfile --check` hook (if not part of S3-06). |

## Out of scope

- `make refresh-cassettes` Makefile target (S3-06).
- CODEOWNERS entry (S3-06).
- Runbook `docs/operations/cassettes.md` (S3-06).
- Nightly drift job CI workflow (Phase 6.5).
- Recording new cassettes (operator workflow once S3-06 ergonomic is shipped). S3-05 may generate a lock over cassette files that already exist, but it must not create live cassette YAML.

## Notes for the implementer

- The `cassettes.lock` format is **load-bearing for Phase 6.5** — its line shape is locked by the phase-5-contract snapshot (S7-10). Any deviation (e.g., switching to TOML or JSON) is an ADR amendment, not a refactor.
- Use `codegenie.hashing.content_hash(path).removeprefix("blake3:")` (Phase 0 helper) — do not re-import `blake3` directly here, that would bypass an existing single-import-point convention. The lock file stores unprefixed 64-hex because ADR-0014's stable line format says `<relpath>  <blake3-hex>`.
- The walker (`test_cassettes_clean.py`) is `module`-level test, not `function`-level — `pytest` collection traverses the cassettes once per session. Watch out for `pytest-xdist`: it splits per-test-id; ensure the walker's diagnostics name the cassette so a failure is reproducible.
- The deliberately-dirty fixtures **must not** weaken the pre-commit firewall. The existing `forbidden-patterns` hook is scoped to Python and excludes `tests/`, so a YAML-specific carve-out there would be noise. If the `gitleaks` hook catches the fake key, add the narrowest fixture-only allowlist and prove a negative control outside that fixture directory still fails.
- The `--check` mode of `cassette rebuild-lockfile` is the pre-commit hook target; it must be **fast** (BLAKE3 of small YAML files is microseconds). Do not regress.
- When generating the initial lock at story-end, do **not** assume S3-02 produced live cassette bytes. Order: S3-04 ships hooks → S3-05 ships scanner + empty-lock bootstrap → S3-06 lands `make refresh-cassettes` → operator records cassettes through sanitizer → operator runs `python -m codegenie cassette rebuild-lockfile`, the lock file is committed alongside. If cassette YAML already exists when S3-05 executes, lock it; otherwise commit the empty lock.
- If you need to coordinate with S3-04 mid-story: the `verify_cassette(path) -> CassetteVerification` shape from S3-04 is what this story's scanner consumes. If S3-04's `CassetteVerification` exposes `.passed: bool` and `.violations: tuple[Violation, ...]`, this story is unblocked. Surface any shape mismatch immediately (Global Rule 7 — don't average).
