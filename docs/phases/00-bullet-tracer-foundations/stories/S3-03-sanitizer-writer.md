# Story S3-03 — Output sanitizer + atomic writer

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** M
**Depends on:** S2-05
**ADRs honored:** ADR-0008, ADR-0011

## Context

ADR-0008 designates `OutputSanitizer.scrub` as the **single path** from a `ProbeOutput` to a persisted byte: a two-pass chokepoint (field-name regex, then absolute-path → relative-path scrubbing) that the synthesis chose over a three-pass design with synchronous `gitleaks` (rejected on cost grounds for the continuous-gather model). The Writer is the only place YAML serialization happens — `yaml.CSafeDumper` with pure-Python fallback, atomic raw-then-yaml publish, symlink refusal, and post-write `os.chmod` to `0600`/`0700` per ADR-0011. Without this story, the coordinator (S3-05) has no place to send sanitized output, and Phase 11's PR commits would leak `/Users/<contributor>/` paths into a real repo.

This story sits between S3-02 (validator) and S3-05 (coordinator wiring). The sanitizer's pass-1 is the **defense-in-depth repeat** of the validator's secret-field-name regex (same `SECRET_FIELD_PATTERN`, two passes), per ADR-0008 §Decision.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design / Output writer + sanitizer` — two-pass sanitizer contract, atomic publish, CSafe fallback
  - `../phase-arch-design.md §Edge cases` rows 7, 13 — symlink-target refusal, `pyyaml` C extension unavailable
  - `../phase-arch-design.md §Scenarios / Scenario 4` — defense-in-depth field-name pass
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — single chokepoint, two-pass, no synchronous gitleaks
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — `0600`/`0700`, re-apply via `os.chmod` after every write
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0006-continuous-deterministic-gather.md` — cost model the synchronous-gitleaks rejection serves
- **Source design:**
  - `../final-design.md §2.8` — Output writer + sanitizer (synthesis source)
- **Existing code (if any):**
  - `src/codegenie/coordinator/validator.py` (S3-02) — exports `SECRET_FIELD_PATTERN`; sanitizer imports the same constant
  - `src/codegenie/errors.py` — `SecretLikelyFieldNameError`, `SymlinkRefusedError`
  - `src/codegenie/probes/base.py` — `ProbeOutput` dataclass; sanitizer consumes this shape

## Goal

`OutputSanitizer.scrub(output, repo_root)` returns a `SanitizedProbeOutput` with secret-named keys rejected (defense in depth) and all `/Users/`, `/home/`, `/root/`, `<analyzed-repo-abs>/` strings rewritten relative to the repo root; `Writer.write(envelope, raw_artifacts, output_dir)` atomically publishes `repo-context.yaml` + raw artifacts with `0600` files / `0700` directories, refusing to overwrite a symlink target.

## Acceptance criteria

- [ ] `src/codegenie/output/sanitizer.py` exports `OutputSanitizer.scrub(output: ProbeOutput, repo_root: Path) -> SanitizedProbeOutput` and the `SanitizedProbeOutput` frozen dataclass.
- [ ] Pass 1 (field-name regex) imports `SECRET_FIELD_PATTERN` from `coordinator.validator` (single source of truth per ADR-0008); a key matching the pattern raises `SecretLikelyFieldNameError`.
- [ ] Pass 2 (path scrub) rewrites every string in `schema_slice` matching `^(/Users/|/home/|/root/|<analyzed-repo-abs>/)` to a path relative to `repo_root`; the scrub walks dicts and lists recursively.
- [ ] `scrub` is **idempotent**: `scrub(scrub(out, r), r)` produces the same result as `scrub(out, r)`.
- [ ] `src/codegenie/output/writer.py` exports `Writer.write(envelope: dict, raw_artifacts: list[tuple[str, bytes]], output_dir: Path) -> None`.
- [ ] Writer uses `yaml.CSafeDumper`; on `ImportError` falls back to `yaml.SafeDumper` and logs `writer.csafe.unavailable` once (edge case #13).
- [ ] Atomic publish: raw artifacts written first under `output_dir/raw/`; envelope written as `repo-context.yaml.tmp` then `os.fsync` then `os.replace` to `repo-context.yaml`.
- [ ] If `repo-context.yaml` already exists as a symlink, Writer raises `SymlinkRefusedError` (no write attempted) — edge case #7.
- [ ] After every write, `os.chmod` re-applies `0600` to all files and `0700` to `output_dir` and its subdirs (ADR-0011).
- [ ] `src/codegenie/output/paths.py` exports helpers for the `<repo>/.codegenie/context/` layout (`context_dir`, `raw_dir`, `yaml_path`, `runs_dir`).
- [ ] All tests below pass; `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` clean on touched files.

## Implementation outline

1. Author `src/codegenie/output/__init__.py` (empty package marker).
2. Author `src/codegenie/output/paths.py` with the four layout helpers — pure functions, no IO.
3. Author `src/codegenie/output/sanitizer.py`:
   - `SanitizedProbeOutput` frozen dataclass (mirrors `ProbeOutput` shape but signals "sanitized" in the type).
   - `OutputSanitizer.scrub`: import `SECRET_FIELD_PATTERN` from `coordinator.validator`; walk `schema_slice` recursively running pass 1 (key check) and pass 2 (string rewrite).
   - The path-scrub regex: build `re.compile(r"^(/Users/|/home/|/root/|" + re.escape(str(repo_root.resolve())) + ")")` per-call (the analyzed-repo prefix is runtime-resolved).
4. Author `src/codegenie/output/writer.py`:
   - `Writer.write`: pre-write symlink check on the destination; atomic raw-then-yaml publish; chmod re-apply post-write.
   - Lazy import of `yaml`; on `ImportError` for `CSafeDumper`, fall back to `SafeDumper` and log once via a module-level `_csafe_warned` flag.
5. Write tests for the public surface (sanitizer + writer + paths).

## TDD plan — red / green / refactor

This story has four anchored behaviors: (a) pass-1 secret rejection, (b) pass-2 path scrub + idempotence, (c) Writer atomic + modes, (d) Writer CSafe fallback + symlink refusal.

### Red — write the failing tests first

Test file paths: `tests/unit/test_output_sanitizer.py`, `tests/unit/test_output_writer.py`.

```python
# tests/unit/test_output_sanitizer.py
from pathlib import Path
from codegenie.errors import SecretLikelyFieldNameError

def test_sanitizer_rejects_secret_shaped_field_name():
    # arrange: ProbeOutput(schema_slice={"github_token": "ghp_abc"}, ...)
    # act: OutputSanitizer().scrub(out, repo_root=Path("/tmp/repo"))
    # assert: raises SecretLikelyFieldNameError
    ...

def test_sanitizer_scrubs_absolute_path_to_relative(tmp_path):
    # arrange: schema_slice = {"file": str(tmp_path / "src" / "a.js")}
    # act: scrub(out, repo_root=tmp_path)
    # assert: scrubbed_output.schema_slice["file"] == "src/a.js"
    ...

def test_sanitizer_scrubs_user_home_prefix(tmp_path):
    # arrange: schema_slice contains "/Users/danny/foo/bar"
    # act: scrub(out, repo_root=tmp_path)
    # assert: the "/Users/..." prefix has been rewritten relative or stripped
    ...

def test_sanitizer_walks_nested_dicts_and_lists(tmp_path):
    # arrange: schema_slice = {"a": {"b": [str(tmp_path / "x")]}}
    # act: scrub(...)
    # assert: deeply nested string was rewritten
    ...

def test_sanitizer_is_idempotent(tmp_path):
    out = ...  # any valid ProbeOutput with absolute paths
    once = scrub(out, repo_root=tmp_path)
    twice = scrub(once_as_probe_output, repo_root=tmp_path)
    assert once == twice
```

```python
# tests/unit/test_output_writer.py
from codegenie.errors import SymlinkRefusedError

def test_writer_atomic_replace_no_partial_file(tmp_path, monkeypatch):
    # arrange: patch os.replace to raise; call Writer.write(...)
    # assert: repo-context.yaml does NOT exist; .tmp may; subsequent reads see no envelope
    ...

def test_writer_files_are_0600_dirs_0700_post_write(tmp_path):
    Writer().write(envelope={"schema_version": "0.1.0", ...}, raw_artifacts=[], output_dir=tmp_path)
    yaml_file = tmp_path / "repo-context.yaml"
    assert oct(yaml_file.stat().st_mode)[-3:] == "600"
    assert oct(tmp_path.stat().st_mode)[-3:] == "700"

def test_writer_refuses_symlink_target(tmp_path):
    # arrange: pre-create repo-context.yaml as a symlink
    (tmp_path / "repo-context.yaml").symlink_to("/etc/passwd")
    # act + assert
    with pytest.raises(SymlinkRefusedError):
        Writer().write(envelope={...}, raw_artifacts=[], output_dir=tmp_path)

def test_writer_falls_back_to_safedumper_on_csafe_unavailable(tmp_path, monkeypatch, caplog):
    # arrange: monkeypatch the CSafeDumper import to ImportError
    # act: Writer().write(...)
    # assert: write succeeds; caplog contains "writer.csafe.unavailable" event exactly once
    ...

def test_writer_publishes_raw_artifacts_before_yaml(tmp_path):
    # arrange: include a raw artifact and an envelope.
    # act: write(...)
    # assert: tmp_path / "raw" / "<name>.json" exists; yaml exists; both present after the call returns.
    ...
```

Run all; confirm `ImportError`/`AttributeError`/`AssertionError`. Commit the failing tests.

### Green — make it pass

1. `output/paths.py`: trivial helpers.
2. `output/sanitizer.py`: minimal recursive walker; pass-1 raises on match; pass-2 builds a per-call compiled regex and `re.sub`s strings.
3. `output/writer.py`: pre-check `Path.is_symlink()`; atomic write via `<dest>.tmp` → `fsync` → `os.replace`; chmod re-apply; lazy `yaml.CSafeDumper` import with fallback.

Resist adding `gitleaks` synchronously — ADR-0008 §Decision is explicit.

### Refactor — clean up

- Type hints throughout. `mypy --strict` clean.
- Docstrings on `scrub`, `write`, and `SanitizedProbeOutput`. Module docstring on `sanitizer.py` cites ADR-0008; on `writer.py` cites ADR-0011.
- Confirm pass-1's secret-regex import path is `from codegenie.coordinator.validator import SECRET_FIELD_PATTERN` (single source).
- Confirm `_csafe_warned` flag prevents log spam across many writes in one process.
- Add structlog event names: `writer.symlink.refused`, `writer.csafe.unavailable`, `sanitizer.path.rewritten` (DEBUG level), `sanitizer.secret.rejected`.
- Edge case #6 (CI cache restore): the chmod re-apply must walk the entire `output_dir` tree, not just the file just written, because the restore may have flattened directories above. Use a small `_fix_modes(path)` helper.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/output/__init__.py` | New — package marker |
| `src/codegenie/output/sanitizer.py` | New — `OutputSanitizer.scrub`, two-pass per ADR-0008 |
| `src/codegenie/output/writer.py` | New — atomic publish, CSafe fallback, symlink refusal, chmod discipline |
| `src/codegenie/output/paths.py` | New — `<repo>/.codegenie/context/` layout helpers |
| `tests/unit/test_output_sanitizer.py` | New — anchors secret rejection, path scrub, nested walk, idempotence |
| `tests/unit/test_output_writer.py` | New — anchors atomic write, modes, symlink refusal, CSafe fallback |

## Out of scope

- **Coordinator dispatch wiring** (calling `scrub` inside `gather()`) — S3-05.
- **`AuditWriter.record` writing run-records** — S3-06.
- **Synchronous `gitleaks`** — explicitly rejected by ADR-0008 §Decision; not added now, not added in Phase 0.
- **Mount-point coverage beyond `/Users`, `/home`, `/root`** — `phase-arch-design.md §Component design` notes `/mnt/...` etc. are deferred to follow-up PRs.
- **`schema-version.txt` sidecar** — handled by S4-02 (CLI startup writes it; not part of `Writer.write`).

## Notes for the implementer

- **Defense in depth, not redundancy.** Pass-1's secret-name check is the same as `_ProbeOutputValidator`'s field-validator — same regex, two passes (ADR-0008 §Tradeoffs). If a future bug routes around the validator, the sanitizer catches it. Do not "optimize away" the second pass by skipping it when the type signals "already validated"; the signal is in the *type*, the check is the second wall.
- The path-scrub regex must use `re.escape(str(repo_root.resolve()))` to safely incorporate the runtime-resolved repo root into the alternation. Don't string-concatenate without escaping — `repo_root` may contain regex metacharacters.
- Per `phase-arch-design.md §Edge cases` row 13, `yaml.CSafeDumper` may be unavailable on macOS without libyaml. The fallback is `yaml.SafeDumper` (pure Python). Do **not** fall through to `yaml.Dumper` — that's `forbidden-patterns`-banned and unsafe.
- Per ADR-0011, `os.chmod` must be re-applied after every write, including after `os.replace`. The CI `actions/cache` restore (S5-01's territory) flattens modes; this Writer is the one that re-asserts them. Verify with a test post-`write()`.
- The `SECRET_FIELD_PATTERN` should be imported from `coordinator.validator` (S3-02), not redefined here. Drift across two regex definitions is exactly the failure mode the single-source-of-truth model forecloses (`final-design.md §L5`).
- `SanitizedProbeOutput` is a *typed signal* that scrubbing ran. It mirrors `ProbeOutput`'s fields but lives in `output/sanitizer.py`; only the sanitizer produces it. The Writer's signature takes a `SanitizedProbeOutput` (or an `envelope: dict` derived from many of them), not a `ProbeOutput` — this is the typed enforcement ADR-0008 §Consequences calls out.
- `repo-context.yaml.invalid` (the schema-fail variant) is the CLI's job (S4-02), not the Writer's. The Writer always writes `repo-context.yaml`.
