# Story S7-04 — Adversarial corpus: hostile-skills + concurrent-gather + no-inmemory-leak + phase3-handoff-skipped

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** HARDENED (validated 2026-05-18)
**Effort:** M
**Depends on:** S7-03 (~70 goldens exist on disk; regen script proven byte-deterministic across two runs — the adversarial corpus exercises code paths that touch the same writer chokepoint the goldens audit)
**ADRs honored:** ADR-0005 (no plaintext persisted — `test_no_inmemory_secret_leak.py` is the type-level "redactor was called" boundary proof), ADR-0006 (`IndexFreshness` location — `test_phase3_handoff_smoke.py` references the Protocol contract that 02-ADR-0006/02-ADR-0007 lock), ADR-0007 (no plugin loader in Phase 2 — `test_phase3_handoff_smoke.py` is grep-discoverable so Phase 3's author finds it on first repo scan), ADR-0009 (pytest-xdist veto — `test_concurrent_gather_race.py` uses `subprocess.Popen` for two-process concurrency, NOT pytest-level parallelism), ADR-0010 (`RedactedSlice` smart constructor — the no-inmemory-leak test verifies the smart-constructor invariant via AST).

## Validation notes (2026-05-18, phase-story-validator)

The original draft assumed an architecture that does not match the actual codebase. Verified-against-source edits:

- **`RedactedSlice` has TWO production constructor sites, not one.** `sanitizer.redact_secrets` (per-probe-slice path) AND `envelope_redactor._build_redacted_slice_pass` (envelope path the CLI actually uses via `cli._seam_redact_envelope` → `envelope_redactor._redact_envelope` → `Writer.write`). AC-15 was rewritten to assert an explicit two-site closed set within the `codegenie.output` package, plus a documented allowlist for `tests/unit/output/` fixtures that legitimately construct `RedactedSlice` to test its own invariants.
- **`OutputSanitizer.scrub` returns `SanitizedProbeOutput`, NOT `RedactedSlice`.** AC-16 was rewritten to assert (a) `Writer.write`'s first non-self parameter is annotated `RedactedSlice` (true at `src/codegenie/output/writer.py:158`); (b) `envelope_redactor._redact_envelope`'s return annotation is `RedactedSlice`. The false "scrub returns RedactedSlice" claim is gone.
- **`Writer.write` is called from the CLI's top-level gather command (`cli.py:397`), not from `OutputSanitizer.scrub`.** AC-17 was rewritten to assert the actual closed call-site set rooted in `cli.py`.
- **No advisory lock at `.codegenie/cache/.lock` exists.** The actual Phase-0 concurrency contract per Phase-0 `phase-arch-design.md §789` edge-case 12 + Phase-0 S5-01 is `O_APPEND` record-level atomicity for records ≤ `PIPE_BUF=4096` plus atomic blob writes via `<dest>.tmp → os.replace`. AC-7 through AC-13 were rewritten around the actual invariants the test must prove, with `tests/unit/test_cache_concurrent.py` named as the Phase-0 precedent the new test extends.
- **AC-23's example Protocol signature was aspirational.** Replaced with the verbatim shape from `src/codegenie/adapters/protocols.py:77`.
- **AC-18 referenced `pyproject.toml` for the `model_construct` ban.** Corrected to `scripts/check_forbidden_patterns.py` (`_PHASE2_BANNED_PACKAGES` includes `"output"`).
- **Two new ACs (AC-30, AC-31)** address coverage gaps: non-UTF8 / control-byte hostile YAML, and post-race JSONL-index parseability.
- **Notes-for-implementer extended** with: aliased-import resilience for the AST walker; wall-clock enforcement mechanism for AC-4; mypy drift trip-wire embedding; and the explicit two-site `ALLOWED_CONSTRUCTOR_SITES` allowlist constant.

Full audit log: `_validation/S7-04-adversarial-corpus-completion.md`.

## Context

This story lands the **remaining adversarial corpus** under `tests/adv/phase02/`. Four tests, each addressing a load-bearing risk-or-gap the Phase 2 design names explicitly:

1. **`test_hostile_skills_yaml.py`** — ≥ 8 hostile YAML cases against `SkillsLoader` (S2-01). Tests defense against `!!python/object` (RCE attempt), billion-laughs (entity expansion), deep-nesting (recursion/stack), symlink-escape filenames, NUL-byte-in-name, oversized files. None executes user code. None mutates host state. All paths produce typed `Result.Err(SkillsLoadError(reason=...))` or are refused at `O_NOFOLLOW` open time.
2. **`test_concurrent_gather_race.py`** — two concurrent `codegenie gather` invocations against the same fixture. The actual Phase-0 concurrency contract (`phase-arch-design.md §789` edge-case 12, Phase-0 S5-01 `tests/unit/test_cache_concurrent.py`) is **`O_APPEND` record-level atomicity for records ≤ `PIPE_BUF=4096`** plus **atomic blob writes via `<dest>.tmp → os.replace`** — **NOT** a `.codegenie/cache/.lock` advisory lock (no such primitive exists in `src/codegenie/`; verified by `grep -rn "flock\|filelock\|portalocker" src/codegenie/` → empty). The test asserts that two concurrent gathers produce a consistent `index.jsonl` (every line parses as JSON) and consistent blobs (every file's content-hash matches its filename). The test is **deterministic** despite testing a concurrency surface — it uses real subprocess concurrency + explicit signal coordination if needed, not random timing.
3. **`test_no_inmemory_secret_leak.py`** — **Gap 5 defense** + **Risk #6 defense**. Uses AST inspection to verify that (a) `RedactedSlice` construction is restricted to the two-site closed set within `codegenie.output` — `sanitizer.redact_secrets` (per-probe-slice path) AND `envelope_redactor._build_redacted_slice_pass` (envelope path the CLI's `_seam_redact_envelope` uses); (b) `Writer.write`'s signature accepts only `RedactedSlice` (already true at `writer.py:158`); (c) `envelope_redactor._redact_envelope`'s return annotation is `RedactedSlice`; (d) `Writer.write` is called only from the CLI's gather seam (`cli.py:397`) — adding a third call site fails the test. This is a **structural** boundary test, not a behavioral one — it reads source AST + signatures rather than executing the pipeline. Without it, a future contributor adding `RedactedSlice.from_existing(...)` in a random probe module silently breaks the type-level guarantee.
4. **`test_phase3_handoff_smoke.py`** — **Gap 1 defense**. Landed `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`. Phase 3's first author finds the test on first repo scan (`grep -r "enabled when Phase 3 plugin lands"`); unskips it at the Phase-3-entry-gate review; the test then asserts the four adapter `Protocol`s from S1-03 are importable AND their signatures match Phase 3's first plugin's expectations. Any Protocol drift between Phase 2 and Phase 3 triggers an ADR amendment to 02-ADR-0006/02-ADR-0007, surfaced loudly at the entry-gate.

The synthesis ledger pins three risks this story directly defends:

- **Risk #2 (Probe ABC not edited).** Adversarial corpus must not trip an unintended `ProbeContext`/`Probe` ABC widening. Tests run against the frozen contract.
- **Risk #4 (`mypy --warn-unreachable` enforcement).** Adversarial tests in this story exercise the typed `Result` paths; mypy-unreachable false-positives would mask test failures. The structural test in particular relies on AST inspection of typed code.
- **Risk #6 (`RedactedSlice` smart-constructor silent break).** `test_no_inmemory_secret_leak.py` is the front-line defense. The AST call-site count of `RedactedSlice` construction in production code (`src/codegenie/`) must equal **exactly two**, and those two sites are the documented closed set: `sanitizer.redact_secrets` + `envelope_redactor._build_redacted_slice_pass`. A third production-code construction site means the smart-constructor guarantee is broken; adding one requires an ADR amendment to 02-ADR-0010. Test-fixture constructions under `tests/unit/output/` are explicitly allowlisted (those tests exist to exercise the smart constructor's invariants directly and are the canonical anti-regression for the model itself).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap analysis" → Gap 1` (Adapter Protocol drift — `test_phase3_handoff_smoke.py` is the named trip-wire).
  - `../phase-arch-design.md §"Gap analysis" → Gap 5` (No-explicit Phase-4 RAG-store handoff contract — `test_no_inmemory_secret_leak.py` is the named boundary test).
  - `../phase-arch-design.md §"Gap analysis" → Gap 4` (`RedactedSlice` smart-constructor — ADR-0010 amendment).
  - `../phase-arch-design.md §"Testing strategy" → "Adversarial tests"` — the test inventory.
  - `../phase-arch-design.md §"Implementation risks"` #2, #4, #6, #8.
- **Phase ADRs:** ADR-0005 (no plaintext persistence), ADR-0006 (`IndexFreshness` location — Protocol contract anchor), ADR-0007 (no plugin loader in Phase 2 — the Phase-3 handoff trip-wire's rationale), ADR-0009 (pytest-xdist veto — concurrency tests live at subprocess level), ADR-0010 (`RedactedSlice` smart constructor).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — adversarial-corpus bullet list, `inspect`-based discipline.
- **Source design:** `../final-design.md §"Gaps"` table + `§"Phase-2 → Phase-3 handoff"` checklist.
- **Existing code:**
  - `src/codegenie/skills/loader.py` (S2-01 — the `SkillsLoader` under test).
  - `src/codegenie/output/sanitizer.py` (S3-01 — `SecretRedactor`; first `RedactedSlice` constructor at line ~434).
  - `src/codegenie/output/envelope_redactor.py` (the **second** `RedactedSlice` constructor at `_build_redacted_slice_pass`, ~line 247 — the envelope-level path the CLI uses via `cli._seam_redact_envelope`).
  - `src/codegenie/output/redacted_slice.py` (S3-02 — `RedactedSlice` smart constructor model).
  - `src/codegenie/output/writer.py:153–175` (S3-03 — `Writer.write(envelope: RedactedSlice, …)`; the type-system defense).
  - `src/codegenie/cli.py:349–397` (the only `Writer.write` call site; `_seam_redact_envelope` builds the `RedactedSlice` via `envelope_redactor._redact_envelope`).
  - `src/codegenie/adapters/protocols.py:37–121` (S1-03 — the four `@runtime_checkable` Protocols this story's Phase-3 handoff test references; **actual** signatures land here, copy verbatim into AC-23's frozen tuple).
  - `src/codegenie/cache/store.py:170–337` (Phase 0 — `CacheStore.put` is `O_APPEND` + atomic blob write via `<dest>.tmp → os.replace`; **NOT** a `.codegenie/cache/.lock` advisory lock).
  - `scripts/check_forbidden_patterns.py:55–80, 247–253` (the `model_construct` ban; `_PHASE2_BANNED_PACKAGES` includes `"output"`).
  - `tests/adv/phase02/test_stale_scip_fixture.py` (S4-02 — adversarial-test directory convention).
  - `tests/adv/phase02/test_secret_in_source.py` (S6-07 — the **behavioral** secret-leak test this story's **structural** test complements).
  - `tests/unit/test_cache_concurrent.py` (Phase-0 S5-01 — the **precedent** `test_concurrent_gather_race.py` extends to a two-gather scenario; uses `subprocess.Popen` two-process invocation per ADR-0009).
  - `tests/unit/output/test_redacted_slice.py` (the 20+ legitimate test-fixture constructors that motivate the test-allowlist in AC-15; these tests exercise the smart-constructor model directly).

## Goal

Four adversarial tests exist under `tests/adv/phase02/`:

1. `test_hostile_skills_yaml.py` — ≥ 8 cases, each producing typed `Result.Err` from `SkillsLoader` or refused at `O_NOFOLLOW`.
2. `test_concurrent_gather_race.py` — two concurrent gathers; advisory lock holds; cache is consistent (no half-written blob).
3. `test_no_inmemory_secret_leak.py` — `inspect`-based structural test; `redact_secrets` is the single `RedactedSlice` call site; every artifact reachable from `OutputSanitizer.scrub` to writer passes through it.
4. `test_phase3_handoff_smoke.py` — skipped per `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands")`; grep-discoverable; asserts (when unskipped) that the four `Protocol`s import unchanged and signatures match Phase-3's-first-plugin expectations.

All four go into the `adv-phase02` CI job (wired in S8-03) as part of the load-bearing gate.

## Acceptance criteria

**`test_hostile_skills_yaml.py` — ≥ 8 cases**

- [ ] **AC-1.** `tests/adv/phase02/test_hostile_skills_yaml.py` exists; covers ≥ 8 distinct hostile cases:
  - **Case 1 — `!!python/object`.** A skill file containing `!!python/object:os.system args: ["touch /tmp/pwned"]`. Loader returns `Result.Err(SkillsLoadError(reason="unsafe_yaml"))`. No `/tmp/pwned` exists after the test (assertion).
  - **Case 2 — `!!python/object/apply` variant.** Same defense; same outcome.
  - **Case 3 — billion-laughs.** YAML entity-expansion bomb. Loader caps `safe_yaml.load`'s `max_bytes` (S3 reference from Phase 1) AND `safe_yaml`'s entity-expansion is disabled. Loader returns `Result.Err(SkillsLoadError(reason="schema"))` OR caps out and returns `Result.Err(reason="oversized")`. Wall-clock < 1 s (the cap-out is fast).
  - **Case 4 — deep nesting.** 1000 levels of nested `{a: {a: {a: ...}}}`. Loader returns `Result.Err(reason="depth_exceeded")` OR `reason="schema"`. Wall-clock < 1 s. Test asserts no `RecursionError` escapes.
  - **Case 5 — symlink-escape filename.** Plant a symlink at `<tier>/skill-A.yaml → /etc/passwd` (or any out-of-tree path). Loader's `O_NOFOLLOW` open refuses with `ELOOP`; `Result.Err(SkillsLoadError(reason="symlink_refused", path=...))`.
  - **Case 6 — NUL-byte in filename.** A filename literally containing a NUL byte (constructed via `os.symlink` or low-level `os.open` if the filesystem allows; otherwise the test skips with a clear reason). Loader rejects via `Result.Err(reason="invalid_filename")` OR `OSError` is caught at the loader boundary and surfaced as `Result.Err`.
  - **Case 7 — oversized file** (50 MB + 1 byte; just past `safe_yaml.load`'s declared cap). Loader returns `Result.Err(reason="oversized")`. Wall-clock < 5 s.
  - **Case 8 — duplicate-key YAML.** `{a: 1, a: 2}`. Per Phase-1 `safe_yaml` discipline, duplicate keys produce `Result.Err(reason="schema")`. Loader propagates.
  - **(Recommended) Case 9 — yaml-bomb via alias chain.** Long chain of `&a *b`-style references; combined size cap or alias-count cap rejects it.
  - **(Recommended) Case 10 — non-UTF8 / control-byte payload.** A YAML file whose bytes are not valid UTF-8 (e.g., raw `\xff\xfe` BOM with mixed-encoding scalars), OR a UTF-8 file containing control bytes (`\x00`–`\x08`, `\x0b`–`\x1f`, excluding `\t` `\n` `\r`) inside string scalars. Loader returns `Result.Err(SkillsLoadError(reason="schema"))` or `reason="io_failure"` per the closed `SkillsLoadError` reason set in `src/codegenie/skills/loader.py`. Wall-clock < 1 s.
- [ ] **AC-2 — no user code executes.** For each case, after the test runs, no file under `/tmp/`, `/var/folders/`, `$HOME` was created by the YAML's payload. The `!!python/object` cases assert no `/tmp/pwned-<random>` exists.
- [ ] **AC-3 — no host-state mutation.** No environment variable was set; no signal was raised. (Defense against esoteric YAML payloads that exercise `__reduce__` chains via `safe_yaml` parsers other than the Phase-1-blessed one.)
- [ ] **AC-4 — wall-clock per case < 5 s.** Each parametrized case completes in under 5 s. (Otherwise an attacker DoSes the gatherer with a crafted hostile skill file.)
- [ ] **AC-5 — typed `Result.Err` paths.** Every hostile case produces a `Result.Err(SkillsLoadError(reason=<one of allowlisted reasons>))`. The allowlisted-reasons set is grep-discoverable in `src/codegenie/skills/loader.py`; the test asserts the reason against the closed set.
- [ ] **AC-6 — fixture under `tests/adv/phase02/fixtures/hostile_skills/`.** Each hostile YAML case lives as a separate file under `tests/adv/phase02/fixtures/hostile_skills/<case-name>.yaml` (the symlink and NUL-byte cases land under a sibling `_create_at_test_time.py` fixture-builder that constructs the path at test time — symlinks and NUL-byte names are not safely committable to git on all platforms). The fixture builder cleans up in a pytest fixture teardown.

**`test_concurrent_gather_race.py` — Phase-0 `O_APPEND` atomicity + atomic blob writes**

> **Validation note:** the original story referenced a `.codegenie/cache/.lock` advisory lock. **No such primitive exists** in `src/codegenie/` (verified by grep: no `fcntl.flock`, no `filelock`, no `portalocker` in production code). The actual Phase-0 contract per `phase-arch-design.md §789` edge-case 12 and S5-01 is **`O_APPEND` record-level atomicity for records ≤ `PIPE_BUF=4096`** plus **atomic blob writes via `<dest>.tmp → os.replace`**. Phase-0 S5-01's `tests/unit/test_cache_concurrent.py` is the precedent — this test extends that pattern to the full `codegenie gather` CLI surface.

- [ ] **AC-7.** `tests/adv/phase02/test_concurrent_gather_race.py` exists; launches two concurrent `codegenie gather` invocations against the **same** fixture (`tests/fixtures/portfolio/minimal-ts/`) via `subprocess.Popen` (NOT `multiprocessing`, NOT `asyncio.gather` — independent OS processes are what exercises the `O_APPEND` kernel-atomicity guarantee per S5-01's Notes-for-implementer rationale).
- [ ] **AC-8 — `.codegenie/cache/index.jsonl` parses line-by-line post-race.** After both processes exit, opening `.codegenie/cache/index.jsonl` and iterating line-by-line: every line is valid JSON (`json.loads(line)` succeeds; no torn records). This is the actual Phase-0 `O_APPEND` invariant. No advisory-lock assertion (none exists).
- [ ] **AC-9 — blob consistency post-race.** Every file under `.codegenie/cache/blobs/` is internally consistent: blob filename starts with `content_hash(file_bytes)[:N]` for the documented N; no `.tmp` file remains (atomic-replace contract held); no zero-byte files. Verified by walking the tree.
- [ ] **AC-10 — `repo-context.yaml` consistency.** Whichever process completed last produces a `repo-context.yaml` that round-trips through `yaml.safe_load` (no exception) and matches one of: A's-final-output OR B's-final-output (no half-merged hybrid).
- [ ] **AC-11 — deterministic.** The test passes 100 / 100 runs on the implementer's machine + CI runner. **NOT** flake-tolerant. Implementer enforces via either (a) `pytest --count=100` if `pytest-repeat` is admitted, or (b) a one-shot `for i in $(seq 100); do pytest tests/adv/phase02/test_concurrent_gather_race.py || break; done` recipe documented in the PR. If flaky, surface as a real concurrency bug — do NOT mark as `@pytest.mark.flaky`. Most-likely root cause when flaky: blob `os.replace` not fsync'd before index-line append.
- [ ] **AC-12 — wall-clock < 60 s.** The test completes (both processes terminate) within 60 s. Two cold gathers against `minimal-ts` should fit easily; if not, the timeout indicates a pathology, not a test problem.
- [ ] **AC-13 — `ADR-0009` honored at this test.** The test uses `subprocess.Popen` for two-process concurrency, NOT `pytest-xdist`. Pytest-xdist remains vetoed repo-wide; this AC scopes the commitment to this specific test.
- [ ] **AC-31 — post-race JSONL count matches expectation.** After both gathers exit, `.codegenie/cache/index.jsonl` has at least `N_unique_keys` lines (where `N_unique_keys` is the number of cache keys exercised by `minimal-ts`); duplicates are permitted (both processes may have written the same key — both records are valid JSON; consumer dedups by key). The test asserts no line was silently lost to torn-write corruption.

**`test_no_inmemory_secret_leak.py` — Gap 5 + Risk #6 + ADR-0010 structural test**

- [ ] **AC-14.** `tests/adv/phase02/test_no_inmemory_secret_leak.py` exists; uses Python's stdlib `ast` module (NOT `mock`, NOT `inspect.getsource` regex, NOT `pytest-asyncio` execution) to verify the four structural invariants below.
- [ ] **AC-15 — `RedactedSlice` construction is restricted to a closed two-site set inside the `codegenie.output` package.** The test:
  - Declares `ALLOWED_CONSTRUCTOR_SITES: Final[frozenset[tuple[str, str]]]` at module top — the two permitted production sites as `(relative_file_path, qualified_function_name)` pairs:
    - `("src/codegenie/output/sanitizer.py", "redact_secrets")`
    - `("src/codegenie/output/envelope_redactor.py", "_build_redacted_slice_pass")`
  - Declares `ALLOWED_TEST_CONSTRUCTOR_DIRS: Final[frozenset[str]] = frozenset({"tests/unit/output"})` — the documented test allowlist (`tests/unit/output/test_redacted_slice.py` and siblings exist to exercise the smart constructor's invariants directly; they are the canonical anti-regression for the `RedactedSlice` model itself).
  - Uses `ast` to parse every Python source file under `src/codegenie/` and `tests/` (excluding `_validation/`, `_attempts/`, `__pycache__/`, and the test file itself).
  - Builds a per-module **import alias map** (`{local_name: real_name}`) from every `ast.ImportFrom` and `ast.Import` whose target is `codegenie.output.redacted_slice.RedactedSlice` — so that `from codegenie.output.redacted_slice import RedactedSlice as _RS; _RS(...)` is correctly resolved as a `RedactedSlice` construction. **Aliased imports must NOT slip past the walker.**
  - For every `Call` node whose `func` (after alias resolution) constructs `RedactedSlice` — either bare-name, `.model_validate(...)`, `.model_validate_json(...)`, or `.model_construct(...)` — assert the enclosing `(file, function)` pair is in `ALLOWED_CONSTRUCTOR_SITES` (production code) OR the file lives under `ALLOWED_TEST_CONSTRUCTOR_DIRS` (test fixtures). Any other site FAILS with the AC-19 message.
  - Defense-in-depth: also assert each of the two allowed production sites actually contains at least one construction (regression guard against silent removal of the redactor — same shape as the original AC-15 second-half assertion).
  - Adding a third production site is an **ADR amendment to 02-ADR-0010**, not a code edit; the test's failure message says so.
- [ ] **AC-16 — writer signature + envelope-redactor return shape pin `RedactedSlice` as the only artifact reaching the writer.** The test:
  - Parses `src/codegenie/output/writer.py`. Asserts `Writer.write`'s first non-self parameter (`envelope`) has annotation `RedactedSlice` (this is already true at `src/codegenie/output/writer.py:158`; the test pins the contract against future loosening). A writer signature accepting `dict[str, JSONValue]` would FAIL.
  - Parses `src/codegenie/output/envelope_redactor.py`. Asserts `_redact_envelope`'s return annotation is `RedactedSlice`. The CLI's `_seam_redact_envelope` is the composition seam; if `_redact_envelope` ever returns a `dict`, the writer's signature would refuse it at runtime, but a contributor could weaken the writer signature first — this AC pins both sides.
  - **Removed false claim**: the original story asserted `OutputSanitizer.scrub` returns `RedactedSlice`. It does not (it returns `SanitizedProbeOutput` per `sanitizer.py:208–241`). The actual envelope-level redaction lives in `envelope_redactor._redact_envelope`. Validation 2026-05-18 corrected this.
- [ ] **AC-17 — closed set of `Writer.write` call sites.** The test AST-walks all of `src/codegenie/`. Asserts `Writer.write` is called from exactly the documented CLI seams in `src/codegenie/cli.py` (one for the envelope at `cli.py:397`; an audit / verify seam if present). The test declares `ALLOWED_WRITER_CALL_SITES: Final[frozenset[tuple[str, str]]]` and fails if the AST walk discovers any `Call` to `Writer.write` (or `Writer().write`, or `_writer.write` where `_writer` resolves to `Writer`) outside that set. Adding a third call site is an explicit edit to this AC's allowlist constant — a deliberate code review event.
- [ ] **AC-18 — `model_construct` banned under `src/codegenie/output/`.** Inherited from S1-11's `forbidden-patterns` extension; this test asserts the ban is in place by:
  - Reading `scripts/check_forbidden_patterns.py` (the **actual** ban site per S1-11 + 02-ADR-0010; NOT `pyproject.toml` — validation 2026-05-18 corrected this) and asserting `"output"` is in the rule's `_PHASE2_BANNED_PACKAGES` frozenset.
  - AST-walking `src/codegenie/output/` and confirming zero `model_construct(...)` call sites and zero `model_construct=` kwarg / assignment occurrences.
  - This is defense-in-depth — the pre-commit hook (`scripts/check_forbidden_patterns.py`) is the front-line; this test catches the pre-commit-bypass case (e.g., `--no-verify` commit landing on a feature branch).
- [ ] **AC-19 — failure messages name the offending file + line + the named remediation.** If a future contributor adds `RedactedSlice.from_existing(...)` at `tests/integration/test_X.py:42`, the test fails with the literal message: `"RedactedSlice constructed at tests/integration/test_X.py:42 (call to 'RedactedSlice.from_existing') is outside the documented two-site closed set (sanitizer.redact_secrets + envelope_redactor._build_redacted_slice_pass) and the tests/unit/output/ allowlist. The smart-constructor invariant (02-ADR-0010, S3-02, Gap 4) requires construction to be restricted to the redaction pipeline. To add a third construction site, amend 02-ADR-0010 and update ALLOWED_CONSTRUCTOR_SITES in this test file. See docs/phases/02-context-gather-layers-b-g/ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md."`
- [ ] **AC-20 — passes `mypy --strict`.** No `Any` outside the `ast.NodeVisitor`'s necessary `Any` returns; even those carry explicit type narrowing.

**`test_phase3_handoff_smoke.py` — Gap 1 trip-wire, landed `@pytest.mark.skip`**

- [ ] **AC-21.** `tests/adv/phase02/test_phase3_handoff_smoke.py` exists.
- [ ] **AC-22 — skipped, grep-discoverable.** The test is decorated with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands — see docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md and ../High-level-impl.md §Step 7 Phase-3-handoff bullet")`. The `reason=` string is literal and grep-discoverable; a Phase-3 author running `grep -r "enabled when Phase 3 plugin lands" tests/` finds it instantly.
- [ ] **AC-23 — contents (skipped but written).** The test, when unskipped, asserts:
  - The four `Protocol`s `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter` are importable from `codegenie.adapters.protocols` (their exact import paths are pinned in S1-03).
  - Each Protocol's runtime structural conformance is verifiable via `isinstance(stub_object, ProtocolClass)` where `stub_object` is a minimal mock implementing the Protocol's method signatures.
  - The `AdapterConfidence` discriminated union has exactly three variants: `Trusted`, `Degraded`, `Unavailable`.
  - The Protocol method signatures match the **verbatim** shapes currently in `src/codegenie/adapters/protocols.py` (copy at test-write time; validation 2026-05-18 corrected the original aspirational example). Embed the four signatures as a frozen tuple in the test file, e.g.:
    ```python
    _FROZEN_S1_03_SIGNATURES: Final[tuple[tuple[str, str, str], ...]] = (
        ("DepGraphAdapter", "consumers", "(self, pkg: str) -> list[str]"),
        ("DepGraphAdapter", "producers", "(self, pkg: str) -> list[str]"),
        ("DepGraphAdapter", "confidence", "(self) -> AdapterConfidence"),
        ("ImportGraphAdapter", "reverse_lookup", "(self, module: str) -> list[str]"),
        ("ImportGraphAdapter", "confidence", "(self) -> AdapterConfidence"),
        ("ScipAdapter", "refs", "(self, symbol: str) -> list[Occurrence]"),
        ("ScipAdapter", "confidence", "(self) -> AdapterConfidence"),
        ("TestInventoryAdapter", "tests_exercising", "(self, symbol: str) -> list[TestId]"),
        ("TestInventoryAdapter", "confidence", "(self) -> AdapterConfidence"),
    )
    ```
    Drift on any signature → test fails at unskip-time → Phase-3 author must amend 02-ADR-0006/02-ADR-0007 explicitly.
- [ ] **AC-24 — comment block explains the trip-wire purpose.** Top of file: a comment block names Gap 1, names ADR-0007, names the Phase-3 entry-gate-review process (S8-04 lands the named issue), and instructs the Phase-3 author on the unskip ritual ("If your first plugin patches one of these Protocols, that's a contract amendment — DO NOT silently change the Protocol; file an ADR amendment to 02-ADR-0006/02-ADR-0007 first, then update this test, THEN unskip.").
- [ ] **AC-25 — passes `mypy --strict`** even while skipped, AND a deliberate Protocol drift breaks mypy on this file (the silent-drift defense). Mypy type-checks skipped tests; the Protocol-conformance assertion code must type-check against the current S1-03 Protocols. The test file MUST embed a `Protocol`-typed helper of the form `def _frozen_dep_graph_signature(adapter: DepGraphAdapter) -> None: reveal_type(adapter.consumers); reveal_type(adapter.producers); ...` (or equivalent `cast(DepGraphAdapter, _stub)` chain) whose parameter / call-site annotations re-state every S1-03 contract by name. If any S1-03 Protocol signature changes, mypy MUST fail on this file (e.g., the call to `adapter.consumers(pkg=...)` would surface the new keyword-only parameter shape). This is the type-system trip-wire — it fires **before** unskip, at every CI run, against the current S1-03 Protocols. Document the trip-wire in the test's top-of-file comment block.
- [ ] **AC-30 — `RedactedSlice` import resolver handles aliased imports.** The AST walker in `test_no_inmemory_secret_leak.py` MUST correctly classify a construction made via `from codegenie.output.redacted_slice import RedactedSlice as _RS; _RS(...)` as a `RedactedSlice` construction. The test includes an inline regression case (a temp module string parsed via `ast.parse`) that exercises the aliased-import path through the walker. Without this, a contributor who aliases the import silently slips past the structural test.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-26 — every test passes `mypy --strict`.**
- [ ] **AC-27 — no flakes.** Each adversarial test passes 100/100 runs on CI. If `test_concurrent_gather_race.py` exhibits any flake, the implementer MUST stabilize via explicit signal synchronization before merging.
- [ ] **AC-28 — fixtures are minimal.** `tests/adv/phase02/fixtures/hostile_skills/` does not exceed ~10 small YAML files. The symlink + NUL-byte cases are built at test time (not committed) per AC-6.
- [ ] **AC-29 — log-emission assertions where relevant.** `test_hostile_skills_yaml.py` asserts each `Result.Err` is also emitted as a structured log event (e.g., `probe.skill.load_refused` with a `reason` field) — per the cross-cutting structlog discipline.

## Implementation outline

1. **TDD red — write `test_hostile_skills_yaml.py` first.** Plant ≥ 8 parametrized cases; each invokes `SkillsLoader.load_all()` against a tier-rooted at `tests/adv/phase02/fixtures/hostile_skills/`; asserts `Result.Err`. With no fixture files yet, each case fails red (no skill file found).
2. Plant the hostile-YAML fixtures under `tests/adv/phase02/fixtures/hostile_skills/` per AC-1's case list. Plant `_create_at_test_time.py` for the symlink + NUL-byte cases. Confirm each fixture file is parseable-as-YAML by an attacker tool (so we're testing real hostile input, not malformed-text edge cases — except where malformed-text IS the case, like duplicate keys).
3. Run `pytest tests/adv/phase02/test_hostile_skills_yaml.py -v`. Adjust the `SkillsLoader` or `safe_yaml` chokepoint as needed (if a case slips through to RCE or to wall-clock-cap-violation, fix the production code — the test caught a real bug). Green.
4. **TDD red — write `test_concurrent_gather_race.py`.** Use `subprocess.Popen` to launch two `codegenie gather tests/fixtures/portfolio/minimal-ts/` invocations (precedent: Phase-0 S5-01 `tests/unit/test_cache_concurrent.py`). Assert the Phase-0 `O_APPEND` invariants (AC-8: every `index.jsonl` line parses; AC-9: every blob filename matches its content hash; AC-31: line count ≥ N_unique_keys). Do NOT assert any `.codegenie/cache/.lock` behavior — no such primitive exists.
5. If the test is flaky, **do not paper over it with an advisory lock**. Flakes mean either a real `O_APPEND` violation (record > `PIPE_BUF`) or a non-atomic write somewhere in the cache path — fix the bug. If you genuinely need deterministic ordering between A and B (e.g., for a follow-up assertion), use explicit signal synchronization: Process A pauses on `SIGUSR1` immediately after a documented checkpoint; the test sends `SIGUSR1` to A; A continues. This is windowing, not race-tolerance.
6. Run 100 times. Confirm 100/100 pass. Green.
7. **TDD red — write `test_no_inmemory_secret_leak.py`.** Build the AST-walker that finds `RedactedSlice` construction call sites. With the production code as-is (per S3-01/S3-02/S3-03), the test should pass on first run — there should be exactly one call site, inside `redact_secrets`. If the count is wrong, debug the production code, not the test.
8. **Verify the failure mode**: temporarily add `RedactedSlice(slice={}, findings_count=0, fingerprints=[])` to a scratch file under `tests/_scratch/`. Run the test; observe it fails with the expected message (AC-19). Delete the scratch file. Re-run; observe green. Document the deliberate-fail-then-pass observation in PR.
9. **TDD red — write `test_phase3_handoff_smoke.py`.** Write the test body (per AC-23). Decorate with `@pytest.mark.skip(reason="enabled when Phase 3 plugin lands — see ...")` per AC-22. Write the comment block per AC-24.
10. **Verify the unskip path.** Temporarily remove the `@pytest.mark.skip` decorator. Run the test. With S1-03's Protocols in place, the test should pass. Confirm. Re-apply the skip decorator. Run again. Pytest records the skip; the test counts as passing (pytest convention).
11. Final pass: `mypy --strict`, `ruff check`, `ruff format --check`. Run all four adversarial tests. Run the full Phase 2 test suite. Green.

## TDD plan — red / green / refactor

### Red — failing adversarial tests first

`test_no_inmemory_secret_leak.py` AST-walker skeleton (hardened 2026-05-18):

```python
# tests/adv/phase02/test_no_inmemory_secret_leak.py
"""Structural boundary test — Gap 5, Risk #6, ADR-0010.

The smart-constructor invariant: RedactedSlice may only be constructed from the documented
two-site closed set inside the codegenie.output redaction pipeline, plus the
tests/unit/output/ allowlist for the model's own anti-regression tests. Adding a third
production-code construction site silently breaks the type-level "redactor was called"
guarantee — this test fails loudly if that happens.

The two documented production sites:
  - codegenie.output.sanitizer.redact_secrets         (per-probe-slice path)
  - codegenie.output.envelope_redactor._build_redacted_slice_pass  (envelope path; CLI uses)

Adding a third site requires an explicit ADR amendment to 02-ADR-0010, then editing
ALLOWED_CONSTRUCTOR_SITES below.
"""
from __future__ import annotations
import ast
from pathlib import Path
from typing import Final, NamedTuple

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # tests/adv/phase02/ -> repo root
_SRC = _REPO_ROOT / "src"
_TESTS = _REPO_ROOT / "tests"

_REDACTED_SLICE_QUALNAME: Final[str] = "codegenie.output.redacted_slice.RedactedSlice"

# Closed two-site set. Adding a third entry = ADR amendment.
ALLOWED_CONSTRUCTOR_SITES: Final[frozenset[tuple[str, str]]] = frozenset({
    ("src/codegenie/output/sanitizer.py", "redact_secrets"),
    ("src/codegenie/output/envelope_redactor.py", "_build_redacted_slice_pass"),
})

# Test allowlist — the model's own anti-regression tests legitimately construct
# RedactedSlice. Any test under this directory may construct.
ALLOWED_TEST_CONSTRUCTOR_DIRS: Final[frozenset[str]] = frozenset({
    "tests/unit/output",
})


class _CallSite(NamedTuple):
    file: str           # relative to repo root, POSIX-style separators
    line: int
    enclosing_func: str # qualified name of the nearest enclosing FunctionDef / AsyncFunctionDef
    call_text: str


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    """Return {local_name: real_qualified_name} for every import in the module.

    Resolves `from codegenie.output.redacted_slice import RedactedSlice as _RS`
    to {'_RS': 'codegenie.output.redacted_slice.RedactedSlice'}.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _resolves_to_redacted_slice(call: ast.Call, aliases: dict[str, str]) -> bool:
    func = call.func
    # Bare-name: RedactedSlice(...) or _RS(...) where _RS aliases RedactedSlice
    if isinstance(func, ast.Name):
        return aliases.get(func.id, "") == _REDACTED_SLICE_QUALNAME
    # Attribute: RedactedSlice.model_validate(...), _RS.model_construct(...), etc.
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base_qual = aliases.get(func.value.id, "")
        return base_qual == _REDACTED_SLICE_QUALNAME and func.attr in {
            "model_validate", "model_validate_json", "model_construct"
        }
    return False


def _enclosing_func_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    cur: ast.AST | None = node
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur.name
        cur = parents.get(cur)
    return "<module>"


def _find_construction_sites(root: Path) -> list[_CallSite]:
    sites: list[_CallSite] = []
    for py in root.rglob("*.py"):
        if any(p in {"_validation", "_attempts", "__pycache__"} for p in py.parts):
            continue
        if py == Path(__file__):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (SyntaxError, UnicodeDecodeError):
            continue
        aliases = _build_alias_map(tree)
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _resolves_to_redacted_slice(node, aliases):
                rel = py.relative_to(_REPO_ROOT).as_posix()
                sites.append(_CallSite(
                    file=rel,
                    line=node.lineno,
                    enclosing_func=_enclosing_func_name(node, parents),
                    call_text=ast.unparse(node),
                ))
    return sites


def _is_allowed(site: _CallSite) -> bool:
    if (site.file, site.enclosing_func) in ALLOWED_CONSTRUCTOR_SITES:
        return True
    if any(site.file.startswith(d + "/") for d in ALLOWED_TEST_CONSTRUCTOR_DIRS):
        return True
    return False


def test_redacted_slice_construction_is_restricted_to_documented_sites() -> None:
    """AC-15 + AC-19 + AC-30 — closed two-site set, with aliased-import resilience."""
    sites = _find_construction_sites(_SRC) + _find_construction_sites(_TESTS)
    offending = [s for s in sites if not _is_allowed(s)]
    assert not offending, "\n".join(
        f"RedactedSlice constructed at {s.file}:{s.line} (call to '{s.call_text}') is outside the "
        f"documented two-site closed set (sanitizer.redact_secrets + "
        f"envelope_redactor._build_redacted_slice_pass) and the tests/unit/output/ allowlist. "
        f"The smart-constructor invariant (02-ADR-0010, S3-02, Gap 4) requires construction to be "
        f"restricted to the redaction pipeline. To add a third construction site, amend 02-ADR-0010 "
        f"and update ALLOWED_CONSTRUCTOR_SITES in this test file. See "
        f"docs/phases/02-context-gather-layers-b-g/ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md."
        for s in offending
    )
    # Defense-in-depth: each documented production site must contain at least one construction
    # (regression guard against silent removal of either redaction path).
    for (file, func) in ALLOWED_CONSTRUCTOR_SITES:
        present = [s for s in sites if s.file == file and s.enclosing_func == func]
        assert present, (
            f"Expected at least one RedactedSlice construction inside {file}::{func}; "
            f"the redactor at this site appears to have been removed. Either redaction path "
            f"silently disappearing breaks 02-ADR-0005 + 02-ADR-0010."
        )
```

`test_hostile_skills_yaml.py` parametrized skeleton:

```python
# tests/adv/phase02/test_hostile_skills_yaml.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pytest
from codegenie.skills.loader import SkillsLoader, SkillsLoadError
from codegenie.result import Result  # Phase-0 Result type

_HOSTILE = Path(__file__).parent / "fixtures" / "hostile_skills"

@dataclass(frozen=True)
class _HostileCase:
    name: str
    fixture_relpath: str  # under _HOSTILE
    expected_reason: str  # one of the SkillsLoadError reason values

_CASES = (
    _HostileCase("python_object",        "case1_python_object.yaml",     "unsafe_yaml"),
    _HostileCase("python_object_apply",  "case2_python_object_apply.yaml","unsafe_yaml"),
    _HostileCase("billion_laughs",       "case3_billion_laughs.yaml",    "oversized"),  # or "schema"
    _HostileCase("deep_nesting",         "case4_deep_nesting.yaml",      "schema"),    # or "depth_exceeded"
    # Cases 5 (symlink) + 6 (NUL-byte) built at test time, see below
    _HostileCase("oversized",            "case7_oversized.yaml",         "oversized"),
    _HostileCase("duplicate_key",        "case8_duplicate_key.yaml",     "schema"),
)

@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.name)
def test_hostile_skill_yaml_refused(case: _HostileCase, tmp_path) -> None:
    """Loader returns typed Result.Err; no user code executes; wall-clock < 5 s."""
    # Copy fixture into a fresh tier dir
    tier = tmp_path / "skills"
    tier.mkdir()
    src = _HOSTILE / case.fixture_relpath
    dest = tier / "skill-A.yaml"
    dest.write_bytes(src.read_bytes())

    pwned = Path("/tmp/pwned-hostile-skills-test")
    assert not pwned.exists(), "stale marker from prior run — clean and retry"

    loader = SkillsLoader(search_paths=[tier])
    result = loader.load_all()

    assert result.is_err(), f"expected Result.Err for {case.name}, got {result!r}"
    err = result.unwrap_err()
    assert isinstance(err, SkillsLoadError)
    assert err.reason == case.expected_reason, f"expected reason={case.expected_reason!r}, got {err.reason!r}"
    assert not pwned.exists(), f"!!python/object exec'd in case {case.name} — security regression"


def test_symlink_escape_refused(tmp_path) -> None:
    """Case 5 — symlink-escape filename. Built at test time (not committable to git)."""
    tier = tmp_path / "skills"
    tier.mkdir()
    target = tmp_path / "out-of-tree.yaml"
    target.write_text("name: out-of-tree\n")
    (tier / "skill-A.yaml").symlink_to(target)

    loader = SkillsLoader(search_paths=[tier])
    result = loader.load_all()

    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, SkillsLoadError)
    assert err.reason == "symlink_refused"
```

`test_concurrent_gather_race.py` skeleton (hardened 2026-05-18 — asserts the actual Phase-0 `O_APPEND` + atomic-blob contract; no `.codegenie/cache/.lock` references):

```python
# tests/adv/phase02/test_concurrent_gather_race.py
"""Concurrent-gather adversarial — extends Phase-0 S5-01's tests/unit/test_cache_concurrent.py
to the full `codegenie gather` CLI surface.

The Phase-0 concurrency contract per phase-arch-design.md §789 edge-case 12:
  - .codegenie/cache/index.jsonl appends are atomic per-record (records ≤ PIPE_BUF=4096B).
  - Blob writes are atomic via <dest>.tmp → os.replace.
  - NO advisory lock; NO .codegenie/cache/.lock primitive.

We assert these invariants directly after two concurrent gathers — every jsonl line parses,
every blob filename matches its content hash, no .tmp remnants.
"""
from __future__ import annotations
import json
import subprocess
import sys
import time
import shutil
from pathlib import Path
import yaml
from codegenie.hashing import content_hash  # actual helper name varies; pick the Phase-0 one

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "portfolio" / "minimal-ts"


def test_concurrent_gathers_do_not_corrupt_cache(tmp_path: Path) -> None:
    # Work on a copy so we don't dirty the canonical fixture
    workdir = tmp_path / "minimal-ts"
    shutil.copytree(_FIXTURE, workdir)

    def _launch() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-m", "codegenie", "gather", str(workdir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    a = _launch()
    time.sleep(0.05)  # explicit windowing — give A a brief head-start on cache-dir creation
    b = _launch()

    out_a, err_a = a.communicate(timeout=60)
    out_b, err_b = b.communicate(timeout=60)

    # AC-12: both processes terminated within budget — already asserted by communicate(timeout=60)

    # AC-8: every line of .codegenie/cache/index.jsonl is valid JSON (the O_APPEND invariant)
    index_path = workdir / ".codegenie" / "cache" / "index.jsonl"
    assert index_path.exists(), f"index.jsonl missing after concurrent gathers; A={err_a!r} B={err_b!r}"
    lines = index_path.read_text(encoding="utf-8").splitlines()
    assert lines, "index.jsonl exists but is empty — neither gather wrote any cache record"
    for i, line in enumerate(lines):
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"index.jsonl line {i+1} is not valid JSON — O_APPEND atomicity violated "
                f"(record likely exceeded PIPE_BUF=4096B). Line bytes: {line[:200]!r}..."
            ) from e

    # AC-31: line count is at least the number of unique cache keys exercised by minimal-ts.
    # Duplicates (same key written by both A and B) are PERMITTED — both records are valid JSON;
    # consumers dedup by the "key" field.
    seen_keys = {json.loads(line).get("key") for line in lines}
    assert seen_keys, "index.jsonl lines had no 'key' fields — schema regression?"

    # AC-9: every blob filename matches its content hash; no .tmp remnants; no zero-byte files
    blobs_root = workdir / ".codegenie" / "cache" / "blobs"
    assert blobs_root.exists(), "cache/blobs/ missing"
    for blob in blobs_root.rglob("*"):
        if not blob.is_file():
            continue
        assert not blob.name.endswith(".tmp"), (
            f"leftover .tmp file at {blob} — atomic os.replace was interrupted; "
            f"either a real bug or test teardown ordering issue"
        )
        size = blob.stat().st_size
        assert size > 0, f"zero-byte blob at {blob} — atomic-write violated"
        expected = content_hash(blob.read_bytes())
        assert blob.name.startswith(expected[:16]), (
            f"corrupt blob: {blob} (filename does not match content hash; "
            f"got {blob.name!r}, expected prefix {expected[:16]!r})"
        )

    # AC-10: repo-context.yaml round-trips; matches one of A's or B's final outputs
    ctx_path = workdir / ".codegenie" / "context" / "repo-context.yaml"
    assert ctx_path.exists()
    parsed = yaml.safe_load(ctx_path.read_text())  # no exception
    assert isinstance(parsed, dict) and "probes" in parsed, (
        "repo-context.yaml parsed but schema was malformed — half-merged hybrid?"
    )
```

### Green — make it pass

Plant fixtures, run tests, iterate until all four are green and stable.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Future contributor adds `RedactedSlice.from_existing(...)` at `tests/integration/test_X.py:42` | `test_redacted_slice_construction_is_restricted_to_documented_sites` — fails with the file:line + remediation pointer + ADR link |
| Future contributor aliases the import (`from … import RedactedSlice as _RS; _RS(...)`) outside the allowlist to "dodge" the structural test | Walker's alias-resolution pass (AC-30) classifies `_RS` correctly; test still fails |
| Someone "fixes" `safe_yaml.load` to allow `!!python/object` (regression) | `test_hostile_skill_yaml_refused[python_object]` — `Result.Err` becomes `Result.Ok`, `/tmp/pwned-*` exists, assertion fails |
| Someone changes the cache's record format and a record now exceeds `PIPE_BUF=4096`B, breaking `O_APPEND` atomicity | `test_concurrent_gathers_do_not_corrupt_cache` — `json.loads(line)` raises on a torn record |
| Atomic-blob-write contract violated (e.g., `<dest>.tmp → os.replace` replaced with direct `f.write`) | `test_concurrent_gathers_do_not_corrupt_cache` — `.tmp` remnants discovered OR blob filename does not match its content hash |
| `SkillsLoader` swallows `OSError(EILSEQ)` for NUL-byte filenames silently | `test_symlink_escape_refused`'s NUL-byte variant — but only if implementer wrote it; otherwise the bug ships |
| Future contributor edits S1-03 Protocols (`DepGraphAdapter.consumers(self, pkg: str)` → `pkg: bytes`) | mypy fails on `test_phase3_handoff_smoke.py`'s `_frozen_dep_graph_signature` helper (AC-25) at the **next CI run**, before unskip; AND `test_phase3_handoff_smoke.py` (when unskipped at Phase 3 entry-gate) catches the signature mismatch via the frozen-signature tuple |
| Future contributor deletes the skip marker in `test_phase3_handoff_smoke.py` and the test fails on master | CI fails on master; the test is unskipped prematurely — the comment block (AC-24) explicitly forbids this without an ADR amendment, and the failure points to the ADR |
| Either `redact_secrets` or `envelope_redactor._build_redacted_slice_pass` is silently removed | Defense-in-depth assertion in the AST test (per-allowed-site `assert present` loop) fires on the missing site |
| A scanner probe (`gitleaks`) bypasses the redactor and writes plaintext to `raw/gitleaks.json` | `tests/golden/test_no_plaintext_in_goldens.py` (S7-03) catches the plaintext in the golden; `test_secret_in_source.py` (S6-07) catches it behaviorally; this story's `test_no_inmemory_secret_leak.py` catches the **structural** path (writer signature would refuse a raw dict; envelope_redactor return shape pinned to RedactedSlice) |
| Future contributor adds a third `Writer.write` call site (e.g., a debug logger path) | `test_writer_call_sites_are_closed_set` (AC-17) — fails with the file:line of the unauthorized call site |

### Refactor — clean up

- `test_no_inmemory_secret_leak.py`'s AST walker is reusable; consider whether to extract it to `tests/_helpers/ast_call_site_finder.py`. **Defer** — only one consumer; extract at the second (if a future ADR mandates a similar "X is the only constructor of Y" invariant, that's the third + lifts).
- `test_hostile_skills_yaml.py`'s `_HostileCase` is the canonical-empty-set predicate. Each case's `expected_reason` is pinned against the closed set declared in `SkillsLoader.SkillsLoadError`. If the closed set grows, the cases here grow accordingly.
- `test_concurrent_gather_race.py`'s `time.sleep(0.1)` is the explicit-windowing primitive, NOT race-tolerance. If the test becomes flaky on a slower CI runner, the fix is signal synchronization (SIGUSR1 handshake), NOT longer sleeps.
- The four tests live side-by-side under `tests/adv/phase02/`; they share fixture-directory conventions (`tests/adv/phase02/fixtures/<test-name>/`); the README at `tests/adv/phase02/README.md` (if it exists from S4-02; if not, plant it) names the load-bearing tests.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/phase02/test_hostile_skills_yaml.py` | ≥ 8 hostile-YAML cases |
| `tests/adv/phase02/fixtures/hostile_skills/case{1..8}_*.yaml` | Hostile fixture files (cases 5 + 6 built at test time) |
| `tests/adv/phase02/test_concurrent_gather_race.py` | Two concurrent gathers; advisory-lock holds; cache consistent |
| `tests/adv/phase02/test_no_inmemory_secret_leak.py` | **Gap 5 + Risk #6 + ADR-0010** — `inspect`-based structural boundary test |
| `tests/adv/phase02/test_phase3_handoff_smoke.py` | **Gap 1** — skipped trip-wire; grep-discoverable; Phase-3 author finds it on first repo scan |
| `tests/adv/phase02/README.md` (extend if exists, plant if not) | Documents the four load-bearing adversarials + the `adv-phase02` CI job's role |

## Out of scope

- **Property tests + portfolio sweep integration** — S7-05.
- **CI wiring** (`adv-phase02` job that runs these four + the earlier ones from S4-02 / S5-05 / S5-06 / S6-07) — S8-03.
- **Phase-3-handoff issues filing** — S8-04 (this story lands only the skipped test; S8-04 files the GitHub issue Phase-3's author follows).
- **`test_secret_in_source.py`** — owned by S6-07; complements this story's **structural** counterpart but lives there.
- **Behavioral concurrency tests against actual `pytest-xdist` parallelism** — out per ADR-0009.
- **A `tests/_helpers/ast_call_site_finder.py` extraction** — premature; one consumer.

## Notes for the implementer

- **Risk #6 is the load-bearing risk this story defends.** `test_no_inmemory_secret_leak.py`'s AST walker is the front-line guard against a future contributor silently breaking the smart-constructor invariant. **Spend extra time on the failure-message ergonomics (AC-19).** A CI failure message that points to the exact file:line PLUS the ADR PLUS the remediation step is what turns a "what does this mean?" CI red into a "oh I see, let me fix it" fix in 30 seconds. The named remediation is non-negotiable.
- **The deliberate fail-then-pass verification (outline step 8) is mandatory.** Add a scratch `RedactedSlice(...)` call somewhere outside `codegenie.output.sanitizer`, run the test, observe the failure with the AC-19 message, fix the code, observe green. Document the round-trip in the PR description. Without this, the test could be subtly wrong (e.g., AST walker missing a call form) and pass-by-default.
- **`test_concurrent_gather_race.py` flake-tolerance is forbidden.** If you cannot get 100/100 passes locally and on CI, do NOT mark it as `@pytest.mark.flaky` or `xfail`. The flake indicates a real bug in the advisory-lock contract; fix the bug. The most common cause is the lock being released before the cache write fully fsyncs — investigate `cache.py`'s flush discipline.
- **`test_phase3_handoff_smoke.py`'s skip marker MUST be `@pytest.mark.skip(reason="...")`**, NOT `@pytest.mark.skipif(...)`. The skipif form makes the un-skip an environmental concern; the plain `skip` makes it a deliberate code edit Phase-3's author performs. The grep-discoverable string is the artifact.
- **AC-23's Protocol-conformance assertion can be left as code-but-skipped.** The test body must type-check (`mypy --strict`) even while skipped; this enforces that the four Protocols stay importable at their pinned paths AND that any signature change in S1-03 forces an explicit edit to this test file (preventing silent drift). If the test file no longer compiles because a Protocol moved, **that** is the contract trip-wire firing — even before Phase 3 unskips.
- **The hostile-YAML fixtures must be small.** Billion-laughs in particular: keep the entity count under 10 (the parser caps it quickly; you don't need 1000 entities to trigger the defense). Deep nesting: 1000 levels is enough to trip stack-or-cap defenses without producing a 10 MB fixture file. Document the size + the cap in each fixture's top-of-file YAML comment.
- **No `mock.patch` anywhere in these tests.** Per the project convention (and CLAUDE.md's "tests verify intent, not just behavior"). The tests exercise real production code paths — the loader, the `O_APPEND` cache contract, the AST of the production code, the four Protocols. Mocks would mask the regression cases these tests are designed to catch.

### Validation-added implementer guidance (2026-05-18)

- **Two-site allowlist as a `Final` constant, not a regex.** The original story said "redact_secrets is the SOLE constructor of `RedactedSlice`." It isn't — `envelope_redactor._build_redacted_slice_pass` is the second site, by design (CLI envelope-level redaction path). Implement `ALLOWED_CONSTRUCTOR_SITES: Final[frozenset[tuple[str, str]]]` as a module-level constant at the top of `test_no_inmemory_secret_leak.py`. The two entries are documented; adding a third is an ADR amendment, not a code edit. This pattern (a `Final` tuple of `(file, qualifier)` pairs as the closed set) is the right shape for a structural-invariant test and composes with future "X is the only constructor of Y" invariants — when a third structural-invariant test arrives, lift the AST walker + the allowlist shape to `tests/_helpers/structural_invariants.py` and pass each test's allowlist constant in. **Defer the lift until N=3** (Rule 2 / rule of three); today's deferred-extraction note in Refactor §1 is correct.

- **Aliased-import resilience in the AST walker.** `_is_redacted_slice_call(node)` as drafted only checks `isinstance(func.value, ast.Name) and func.value.id == "RedactedSlice"`. This will silently miss `from codegenie.output.redacted_slice import RedactedSlice as _RS; _RS(...)`. Walker must first build a per-module import alias map from `ast.ImportFrom` + `ast.Import` nodes (`{local_name: real_qualified_name}`) and resolve `Call.func` against it. Add the inline regression case from AC-30 to lock the behavior down — without it, the mutation "alias the import to dodge the structural check" lands with no test failure.

- **Wall-clock enforcement for AC-4 without adding `pytest-timeout`.** Do NOT introduce `pytest-timeout` as a dep just for this test (Phase-2 fence discipline). Each hostile-YAML case wraps its `loader.load_all()` call between `t0 = time.monotonic()` / `assert time.monotonic() - t0 < 5.0` book-ends. If a case exceeds 5 s, the loader has a real DoS surface — fix the loader, not the test.

- **mypy drift trip-wire (AC-25 expansion).** The Protocol-typed helper `_frozen_dep_graph_signature(adapter: DepGraphAdapter) -> None: ...` lives near the top of `test_phase3_handoff_smoke.py`, OUTSIDE the `@pytest.mark.skip`-decorated function body (decorators don't affect mypy reachability — module-level code type-checks always). The body uses every method name the test cares about (`adapter.consumers(...)`, `adapter.producers(...)`, `adapter.confidence()`, etc.). Any S1-03 signature change forces this file to fail mypy at the next CI run — even before unskip. **This is the contract trip-wire firing through the type system rather than through pytest.**

- **`O_APPEND` invariant > advisory lock.** The original story referenced `.codegenie/cache/.lock` and `fcntl.flock` — neither exists. The actual Phase-0 contract is `O_APPEND` atomicity for records ≤ `PIPE_BUF=4096` (proven in Phase-0 S5-01 `tests/unit/test_cache_concurrent.py`) + atomic blob writes via `<dest>.tmp → os.replace`. The concurrent-gather test asserts these invariants directly (every line of `index.jsonl` parses; every blob's filename matches its content hash; no `.tmp` files remain). **Do NOT introduce a lock primitive to "fix" flakes** — the lock would be a real architectural change requiring a Phase-0 ADR amendment. Flakes mean either (a) a real `O_APPEND` violation (record size exceeded `PIPE_BUF`), or (b) a real atomic-write violation (someone added a non-atomic write path). Fix the bug; don't add a lock.

- **`Writer.write` call-site allowlist.** AC-17's `ALLOWED_WRITER_CALL_SITES` is a `Final[frozenset[tuple[str, str]]]` declared at the top of the test. Today the set contains exactly the CLI seam at `cli.py:397` (and a verify seam if S4-02 / S8-03 added one). Adding a third call site is an explicit edit to this constant — the diff in PR review is the load-bearing artifact. This is the same pattern as `ALLOWED_CONSTRUCTOR_SITES` above (Open/Closed via a registered closed set, lifted into a registry only at N=3).

### Patterns DELIBERATELY deferred (per Rule 2 + Rule 3)

- **A reusable AST `_call_site_finder.py`** — one consumer; lift at the second.
- **A behavioral skill-loader-hostile-input test that asserts `redact_secrets` was called via a mock spy** — defer; the structural AST test in this story + the behavioral end-to-end test in S6-07 (`test_secret_in_source.py`) together cover the surface; a mock-spy variant adds nothing observable.
- **A second concurrency test against Layer-C `runtime_trace` parallel scenarios** — out; `runtime_trace` is sequential per scenario by design (S5-02 contract). The advisory-lock is the only concurrency surface to exercise.
- **A `test_protocol_drift_at_phase2_boundary.py` companion** that re-asserts S1-03's Protocols at the Phase-2-boundary (without waiting for Phase 3) — defer; the `test_phase3_handoff_smoke.py`'s type-check-while-skipped already enforces drift-detection without redundancy.
