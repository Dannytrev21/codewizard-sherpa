# Validation report — S7-04 adversarial-corpus-completion

**Verdict:** HARDENED
**Date:** 2026-05-18
**Validator:** phase-story-validator
**Story file:** `../S7-04-adversarial-corpus-completion.md`

## Context brief

The story lands four adversarial tests under `tests/adv/phase02/`:

1. `test_hostile_skills_yaml.py` (≥ 8 hostile-YAML cases against `SkillsLoader`)
2. `test_concurrent_gather_race.py` (two concurrent `codegenie gather` invocations)
3. `test_no_inmemory_secret_leak.py` (`inspect`/AST structural test — `RedactedSlice` smart-constructor invariant)
4. `test_phase3_handoff_smoke.py` (skipped Gap 1 trip-wire for Phase-3 Protocol drift)

Story is in **Step 7** of Phase 2's High-level-impl.md (fixture portfolio + goldens + remaining adversarial corpus). Depends on S7-03 (regen script + ~70 goldens). Honors ADRs 0005, 0006, 0007, 0009, 0010.

## Critic findings

### Consistency (CRITICAL — drives most edits)

The story's AC-15 / AC-16 / AC-17 and AC-7 / AC-8 / AC-9 / AC-10 were written against an **architecture that does not match the actual codebase**. Five concrete drift points discovered by reading source:

| # | Story claim | Actual code (verified 2026-05-18) | Severity |
|---|---|---|---|
| C1 | `redact_secrets` in `codegenie.output.sanitizer` is the **sole** `RedactedSlice` constructor. | There are **two** production construction sites: `sanitizer.redact_secrets()` (`src/codegenie/output/sanitizer.py:434`) AND `envelope_redactor._build_redacted_slice_pass()` (`src/codegenie/output/envelope_redactor.py:247`). The latter is the envelope-level redaction path the CLI actually uses (cli.py:358–359 → `_redact_envelope` → `Writer.write`). | **block** |
| C2 | The test file "imports `RedactedSlice` for type-narrowing AST checks but does NOT construct one." | `tests/unit/output/test_redacted_slice.py` has 20+ direct constructions of `RedactedSlice(slice=..., findings_count=..., fingerprints=...)` — by design, these unit tests exercise the smart constructor's invariants. The story's text-file allowlist must be widened to permit test-fixture construction under `tests/unit/output/`. | **block** |
| C3 | `OutputSanitizer.scrub` returns a `RedactedSlice` (AC-16 walks its `return` paths to assert this). | `OutputSanitizer.scrub` returns a `SanitizedProbeOutput` (`sanitizer.py:208–241`) — NOT a `RedactedSlice`. The envelope-level redaction (which DOES return `RedactedSlice`) lives in `envelope_redactor._redact_envelope`. The story confuses two distinct pipeline stages. | **block** |
| C4 | The writer is "called only from inside `codegenie.output.sanitizer.OutputSanitizer.scrub`" (AC-17). | `Writer.write` is called from `src/codegenie/cli.py:397` (the CLI's top-level gather command) with an envelope built by `_seam_redact_envelope` → `envelope_redactor._redact_envelope` → `RedactedSlice`. AC-17's "scrub" call site does not exist. | **block** |
| C5 | "Phase-0 advisory lock at `.codegenie/cache/.lock`" is the synchronization primitive (AC-7, AC-8, AC-13, Notes). | No advisory lock primitive exists in the codebase. `fcntl.flock` / `filelock` / `portalocker` are absent from `src/codegenie/`. The actual Phase-0 concurrency contract per Phase-0 ADR / edge-case #12 / S5-01 is **`O_APPEND` record-level atomicity for records ≤ `PIPE_BUF=4096`** plus **atomic blob writes via `<dest>.tmp → os.replace`**. The proof-of-art test is `tests/unit/test_cache_concurrent.py`, not a lock-contention test. | **block** |
| C6 | AC-23's example signature for `DepGraphAdapter.consumers`: `consumers(self, pkg: PackageId, *, transitively: bool = False) -> AdapterConfidence`. | Actual signature (`src/codegenie/adapters/protocols.py:77`): `consumers(self, pkg: str) -> list[str]`. Story's example is aspirational and would mislead the implementer. The intent (drift detection via frozen-signature tuple) is correct; the example is wrong. | **harden** |
| C7 | AC-18: assert the ban "by reading `pyproject.toml` (or the equivalent pre-commit config)". | The ban lives in `scripts/check_forbidden_patterns.py` (rule `model_construct (Phase 2 packages)`, `_PHASE2_BANNED_PACKAGES` includes `"output"`). pyproject.toml carries no such rule. | **harden** |

### Coverage

- **Strong overall** — 29 ACs across four tests, with explicit case enumeration for the hostile-YAML corpus and explicit failure-message ergonomics (AC-19) for the AST walker.
- **Gap CV1**: Hostile-YAML AC-1 doesn't enumerate **non-UTF8 / control-byte / BOM-prefixed YAML** — a realistic supply-chain hostile case that breaks `yaml.safe_load` differently from the named cases. Add as recommended Case 10.
- **Gap CV2**: Concurrent-gather block has no AC asserting **JSONL index parseability** post-race (every line is valid JSON — the actual Phase-0 invariant per `phase-arch-design.md §789`). The current AC-9 only walks blob files. Add an AC that opens `.codegenie/cache/index.jsonl`, iterates line-by-line, and asserts `json.loads` succeeds for every line.
- **Gap CV3**: AC-25 says "passes `mypy --strict` even while skipped" — but doesn't explicitly assert that **changing an S1-03 Protocol signature breaks mypy on this file** (the silent-drift defense). Add an explicit Notes-for-implementer paragraph stating the test file embeds a `cast(DepGraphAdapter, _stub)` or an explicit Protocol-typed `_validate_protocol_shape(...)` helper whose argument types pin the signatures by name — so a signature change forces a deliberate edit to this file.
- **No coverage gap** on the four other dimensions (hostile YAML cases, concurrency post-conditions, smart-constructor structural invariant, Protocol-drift trip-wire) — those are well-specified.

### Test quality

- **AST walker quality**: `_is_redacted_slice_call` checks `isinstance(func.value, ast.Name) and func.value.id == "RedactedSlice"`. This will **miss aliased imports** like `from codegenie.output.redacted_slice import RedactedSlice as _RS` followed by `_RS(...)`. A future contributor who legitimately aliases the import (e.g., for shadowing in a test) silently slips past the structural test. Two options for the implementer:
  - **Resolver pass** — first walk all `ast.ImportFrom` nodes and build a local-name → real-name map per module, then resolve `Call.func` against it.
  - **Conservative ban** — also check `func.id` against the set `{"RedactedSlice"} ∪ {alias names found in import map}`.
  The story should NOT silently leave this gap; add it to Notes-for-implementer with a one-line mutation: "if a contributor adds `from ... import RedactedSlice as _RS; _RS(...)` outside the allowlist, the test must still fail."
- **Mutation-resistance witness table** is strong — lists 8 concrete mutations and the test that catches each. Good.
- **AC-4 (wall-clock per case < 5 s)**: no enforcement mechanism is named. Recommend `@pytest.mark.timeout(5)` per case (via `pytest-timeout`) — but `pytest-timeout` may not be in deps. Alternative: each test records `t0 = time.monotonic()` and asserts `time.monotonic() - t0 < 5.0` at end. Surface as Notes-for-implementer.
- **AC-11 (100/100 runs, deterministic)**: how is this measured? The story says "passes 100 / 100 runs on the implementer's machine + CI runner." Recommend the implementer add a `make test-flake-check ITER=100 TEST=tests/adv/phase02/test_concurrent_gather_race.py` recipe OR an inline `pytest --count=100` (via `pytest-repeat`) verification. Add to Notes-for-implementer; do not turn into an AC (mechanism is implementer's call).
- **No `mock.patch`** discipline is explicit in Notes — good. Story already addresses Rule 9 well.

### Design patterns

- The story already invokes the right patterns by name: smart constructor (ADR-0010), tagged union (`Result.Err(SkillsLoadError(reason=...))`), AST-as-structural-assertion. Good.
- The AST walker IS a candidate for extraction to `tests/_helpers/ast_call_site_finder.py` — but story explicitly defers per rule of three (only one consumer). **Correct per Rule 2.**
- **Open/Closed at the hostile-YAML corpus**: parametrized list of `_HostileCase` tuples is the right shape — adding a new case is "add a row" not "edit a switch." Good.
- **One latent design improvement to surface to implementer (not as AC)**: when a third "X must be constructed only by Y" structural invariant arrives in the codebase, lift the AST walker into a tiny registry — `@register_construction_boundary(target_cls, allowed_modules, remediation_pointer)` — and consolidate. Today's story defers correctly; the Notes section already mentions it (Refactor §1). **No edit needed.**
- **No anti-patterns introduced.** No primitive obsession (uses `ProbeId`, typed `Result`). No hidden state. No deep inheritance.

## Research

No `NEEDS RESEARCH` findings — every issue is fixable from in-repo evidence.

## Edits applied to the story

Eight edit-sites, each tightening a concrete failure mode:

1. **Header / Context** — Replace "Phase-0 advisory lock at `.codegenie/cache/.lock` is the synchronization primitive" with the actual Phase-0 concurrency contract: `O_APPEND` record-level atomicity (records ≤ `PIPE_BUF`) + atomic blob writes via `<dest>.tmp → os.replace`. Cite `phase-arch-design.md §789` edge-case 12 and Phase-0 S5-01's `tests/unit/test_cache_concurrent.py` as precedent.

2. **AC-15** (the SOLE constructor claim) — Widen the rule. New text: `RedactedSlice` construction is restricted to the `codegenie.output` package — specifically `sanitizer.redact_secrets` and `envelope_redactor._build_redacted_slice_pass`. Any construction outside `src/codegenie/output/` in production code fails. Test files under `tests/unit/output/` are permitted via a documented allowlist (the unit tests for `RedactedSlice` itself must construct it). The test asserts the explicit two-site closed set rather than a "single site" claim that doesn't match reality.

3. **AC-16** (scrub → writer reachability) — Replace with the actual composition: `cli.py:_seam_redact_envelope` calls `envelope_redactor._redact_envelope`, which returns a `RedactedSlice`; that `RedactedSlice` is then passed to `Writer.write` (signature pinned in `writer.py:158`). Test asserts (a) `Writer.write`'s first non-self parameter is annotated `RedactedSlice` (already true at `writer.py:158`); (b) `envelope_redactor._redact_envelope`'s return annotation is `RedactedSlice`. Remove the false claim that `OutputSanitizer.scrub` returns `RedactedSlice`.

4. **AC-17** (closed call-site set) — Update to: `Writer.write` is called from exactly two top-level CLI seams in `cli.py` (one for the envelope, audit at the verify path). The test AST-walks `src/codegenie/cli.py` AND the rest of `src/codegenie/`, asserting the writer's entry function is called from the named CLI gather seam (and verify seam, if it exists) and NO OTHER call site. Any third call site fails.

5. **AC-18** (model_construct ban) — Fix location reference: "Read `scripts/check_forbidden_patterns.py` (the actual ban site per S1-11 + 02-ADR-0010) and assert `model_construct` is named in the `_PHASE2_BANNED_PACKAGES` rule for the `output` package." Drop the misleading `pyproject.toml` parenthetical.

6. **AC-7 / AC-8 / AC-9 / AC-10 / AC-13** (concurrent gather block) — Realign to actual concurrency primitive:
   - **AC-7**: Two concurrent `codegenie gather` invocations via `subprocess.Popen` (precedent: Phase-0 S5-01 `tests/unit/test_cache_concurrent.py`).
   - **AC-8**: After both processes exit, the `.codegenie/cache/index.jsonl` parses line-by-line (each line is valid JSON; no torn records). This is the actual Phase-0 `O_APPEND` invariant per edge-case 12.
   - **AC-9**: Every blob under `.codegenie/cache/blobs/` is internally consistent (blob filename matches `content_hash(file_bytes)`; no `.tmp` file remains; no zero-byte files). Verifies the atomic-blob-write contract.
   - **AC-10**: The final `repo-context.yaml` round-trips through `yaml.safe_load` and matches one of A's-final-output OR B's-final-output (no half-merged hybrid).
   - **AC-13**: Replace "ADR-0009 honored: pytest-xdist remains vetoed" with the same statement scoped to **this test** (the test uses `subprocess.Popen`, NOT pytest-xdist).
   - Drop the "advisory lock holds (Process B blocks waiting OR fails-loud)" framing — it described a primitive that doesn't exist.

7. **AC-23** (Protocol signature example) — Replace `consumers(self, pkg: PackageId, *, transitively: bool = False) -> AdapterConfidence` with the **actual** S1-03 signature: `DepGraphAdapter.consumers(self, pkg: str) -> list[str]`. The intent (drift detection via frozen signature tuple) is unchanged; only the example is corrected. Add a comment block listing the four actual Protocol signatures verbatim from `src/codegenie/adapters/protocols.py:77–121` so the implementer copies the right shape.

8. **New AC-30 (split out from AC-1)** — Recommended Case 10 (non-UTF8 / control-byte YAML): a YAML file whose bytes are not valid UTF-8 OR contain a UTF-8 BOM followed by NUL bytes inside string scalars. Loader returns `Result.Err(SkillsLoadError(reason="schema"))` or `reason="io_failure"`. Wall-clock < 1 s.

9. **New AC-31** — Concurrent-gather JSONL parseability (Gap CV2): after both gathers exit, every line of `.codegenie/cache/index.jsonl` is parseable JSON (no torn records). This is the actual `O_APPEND` invariant the test must prove.

10. **Notes for the implementer — add three paragraphs**:
    - **Aliased-import resilience** for the AST walker (TQ above).
    - **Wall-clock enforcement** mechanism for AC-4 (`time.monotonic()` deltas; do NOT depend on `pytest-timeout` unless dep added).
    - **mypy drift trip-wire** (CV3): the test file MUST embed an explicit Protocol-typed helper (`def _frozen_dep_graph_signature(adapter: DepGraphAdapter) -> None: ...` whose param annotations re-state the contract) so that ANY S1-03 signature change forces a mypy break on this file.
    - **Two-site allowlist** (CONSISTENCY C1, C2): the AST walker must be passed `ALLOWED_CONSTRUCTOR_SITES: Final[frozenset[str]] = frozenset({...})` containing the explicit two production sites + the test allowlist. Adding a third production site is an ADR amendment, not a code edit.

11. **Implementation outline step 1** — Add explicit reference to `tests/unit/test_cache_concurrent.py` as the Phase-0 precedent the concurrent-gather test extends.

12. **References — where to look** — Add `src/codegenie/output/envelope_redactor.py` (the second `RedactedSlice` constructor) and `tests/unit/test_cache_concurrent.py` (the Phase-0 concurrency-primitive precedent).

13. **Status line** — append "Validation: HARDENED 2026-05-18" so future readers can tell the story has been through this skill.

## Final verdict

**HARDENED** — story's goal, scope, and 4-test decomposition are sound. The implementation prescription was written against an outdated/imagined codebase shape (single `RedactedSlice` constructor; advisory lock at `.codegenie/cache/.lock`; `scrub` returning `RedactedSlice`); without these edits the executor would write tests that fail-on-first-run for the wrong reason (file/function not found) and would never exercise the actual invariants the story exists to defend.

Edits realign every AC to the codebase as it exists today (verified by direct file reads). The four tests this story lands remain load-bearing, and their failure modes are now actually testable.

## Sources consulted

- `docs/phases/02-context-gather-layers-b-g/phase-arch-design.md §"Gap analysis" Gaps 1, 4, 5; §"Adversarial tests"`
- `docs/phases/02-context-gather-layers-b-g/High-level-impl.md §"Step 7"`
- `docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md`
- `docs/phases/02-context-gather-layers-b-g/ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md`
- `src/codegenie/output/sanitizer.py:208,408–440`
- `src/codegenie/output/envelope_redactor.py:237–251`
- `src/codegenie/output/writer.py:153–175`
- `src/codegenie/output/redacted_slice.py`
- `src/codegenie/adapters/protocols.py:67–121`
- `src/codegenie/skills/loader.py:108–141`
- `src/codegenie/cache/store.py:170–337`
- `src/codegenie/cli.py:349–397`
- `scripts/check_forbidden_patterns.py:55–80, 247–253`
- `docs/phases/00-bullet-tracer-foundations/stories/S5-01-bench-concurrent-cache.md`
- `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md §789` (edge case #12)
- `tests/unit/output/test_redacted_slice.py` (the 20+ legitimate test-fixture constructors that prove C2)
